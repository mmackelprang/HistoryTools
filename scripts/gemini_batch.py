"""
Gemini Batch API integration for the Family Archive.

Submits PDF transcription jobs to Gemini's batch endpoint for 50% cost savings.
One batch job per PDF. Results are collected asynchronously via --collect.
"""

import base64
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))


def _rel_path(dest_root, file_path):
    """Get forward-slash relative path from dest_root."""
    try:
        rel = Path(file_path).relative_to(Path(dest_root))
    except ValueError:
        rel = Path(file_path)
    return str(rel).replace("\\", "/")


def submit_batch(client, model, pdf_path, dest_root, conn, dpi=200):
    """Submit a PDF for batch transcription via Gemini Batch API.

    Renders each page to an image, builds batch requests, and submits
    to Gemini. Records the batch job in the batches SQLite table.

    Args:
        client: google.genai.Client instance.
        model: Model name (e.g., "gemini-2.5-flash").
        pdf_path: Path to the PDF file.
        dest_root: Archive root directory.
        conn: SQLite connection.
        dpi: Render DPI for page images (default 200).

    Returns:
        Batch job name string, or None if skipped.
    """
    pdf_path = Path(pdf_path)
    rel = _rel_path(dest_root, pdf_path)

    # Check if already submitted (not yet collected)
    cursor = conn.execute(
        "SELECT batch_id FROM batches WHERE pdf_path = ? AND status IN ('submitted', 'succeeded')",
        (rel,)
    )
    if cursor.fetchone():
        print(f"  Skipping (already submitted): {rel}")
        return None

    # Render pages
    from transcribe_pdfs_gemini import render_page_to_image, TRANSCRIPTION_PROMPT
    import fitz

    doc = fitz.open(str(pdf_path))
    page_count = len(doc)

    # Build inline requests — one per page
    inline_requests = []

    for page_num in range(page_count):
        image_bytes = render_page_to_image(doc, page_num, dpi=dpi)
        mime_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"
        b64_data = base64.b64encode(image_bytes).decode("ascii")

        inline_requests.append({
            "contents": [{
                "parts": [
                    {"text": TRANSCRIPTION_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                ],
                "role": "user",
            }]
        })

    doc.close()

    # Submit batch
    batch_job = client.batches.create(
        model=model,
        src=inline_requests,
        config={"display_name": pdf_path.name},
    )

    batch_id = batch_job.name

    # Record in database
    conn.execute("""
        INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
        VALUES (?, ?, ?, ?, 'submitted')
    """, (batch_id, rel, model, page_count))
    conn.commit()

    print(f"  Submitted: {rel} ({page_count} pages) -> {batch_id}")
    return batch_id


# Gemini job state -> our status mapping
_STATE_MAP = {
    "JOB_STATE_SUCCEEDED": "succeeded",
    "JOB_STATE_FAILED": "failed",
    "JOB_STATE_EXPIRED": "expired",
    "JOB_STATE_CANCELLED": "cancelled",
}


def check_status(client, conn):
    """Check status of all pending batch jobs.

    Queries the batches table for submitted jobs, checks each with the
    Gemini API, and updates status in SQLite.

    Args:
        client: google.genai.Client instance.
        conn: SQLite connection.

    Returns:
        Dict with counts: {"pending": int, "succeeded": int, "failed": int, "expired": int}
    """
    cursor = conn.execute(
        "SELECT batch_id, pdf_path FROM batches WHERE status = 'submitted'"
    )
    pending_batches = cursor.fetchall()

    counts = {"pending": 0, "succeeded": 0, "failed": 0, "expired": 0, "cancelled": 0}

    for row in pending_batches:
        batch_id = row["batch_id"]
        pdf_path = row["pdf_path"]

        try:
            job = client.batches.get(name=batch_id)
            state_name = job.state.name
            new_status = _STATE_MAP.get(state_name)

            if new_status:
                error_msg = None
                if new_status == "failed" and hasattr(job, "error") and job.error:
                    error_msg = str(getattr(job.error, "message", job.error))

                conn.execute("""
                    UPDATE batches SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ?
                    WHERE batch_id = ?
                """, (new_status, error_msg, batch_id))
                conn.commit()
                counts[new_status] = counts.get(new_status, 0) + 1
                print(f"  {pdf_path}: {new_status}")
            else:
                counts["pending"] += 1
                print(f"  {pdf_path}: pending ({state_name})")

        except Exception as e:
            print(f"  {pdf_path}: error checking status ({e})")
            counts["pending"] += 1

    total = sum(counts.values())
    print(f"\nBatch status: {total} jobs — "
          f"{counts['pending']} pending, {counts['succeeded']} succeeded, "
          f"{counts['failed']} failed")

    return counts


def collect_results(client, conn, dest_root):
    """Collect results from succeeded batch jobs and write transcript files.

    For each succeeded batch, retrieves the per-page responses, assembles
    them in order, and creates the .transcript.md file using the same
    function as the real-time path.

    Args:
        client: google.genai.Client instance.
        conn: SQLite connection.
        dest_root: Archive root directory.

    Returns:
        Number of transcripts collected.
    """
    from transcribe_pdfs_gemini import create_transcript_md

    dest_root = Path(dest_root)
    cursor = conn.execute(
        "SELECT batch_id, pdf_path, model, page_count FROM batches WHERE status = 'succeeded'"
    )
    succeeded = cursor.fetchall()

    if not succeeded:
        print("No completed batch jobs to collect.")
        return 0

    collected = 0

    for row in succeeded:
        batch_id = row["batch_id"]
        pdf_path_rel = row["pdf_path"]
        model = row["model"]
        page_count = row["page_count"]
        pdf_path = dest_root / pdf_path_rel

        try:
            job = client.batches.get(name=batch_id)

            # Extract page texts from inline responses
            page_texts = []
            if job.dest and job.dest.inlined_responses:
                for resp in job.dest.inlined_responses:
                    if resp.error:
                        page_texts.append("[Page transcription failed]")
                    elif resp.response and resp.response.text:
                        page_texts.append(resp.response.text.strip())
                    else:
                        page_texts.append("[Page appears blank or illegible]")

            if not page_texts:
                print(f"  {pdf_path_rel}: no responses found")
                continue

            # Create transcript using the shared function
            md_path, confidence, word_count = create_transcript_md(
                pdf_path, page_texts, model, dest_root
            )

            # Mark as collected
            conn.execute("""
                UPDATE batches SET status = 'collected', completed_at = CURRENT_TIMESTAMP
                WHERE batch_id = ?
            """, (batch_id,))
            conn.commit()

            collected += 1
            print(f"  {pdf_path_rel}: {word_count} words, confidence={confidence}")

        except Exception as e:
            print(f"  {pdf_path_rel}: error collecting ({e})")

    print(f"\nCollected {collected} transcripts")
    return collected
