"""
Gemini Batch API integration for the Family Archive.

Submits PDF transcription jobs to Gemini's batch endpoint for 50% cost savings.
One batch job per PDF (or multiple chunks for large PDFs).
Results are collected asynchronously via --collect.
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 18MB limit per chunk (leaves headroom for base64 overhead and prompt text)
_CHUNK_SIZE_LIMIT = 18 * 1024 * 1024


def _rel_path(dest_root, file_path):
    """Get forward-slash relative path from dest_root."""
    try:
        rel = Path(file_path).relative_to(Path(dest_root))
    except ValueError:
        rel = Path(file_path)
    return str(rel).replace("\\", "/")


def _build_request(image_bytes, prompt):
    """Build a single inline batch request dict from image bytes."""
    mime_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"
    b64_data = base64.b64encode(image_bytes).decode("ascii")
    return {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}},
            ],
            "role": "user",
        }]
    }, len(b64_data)


def submit_batch(client, model, pdf_path, dest_root, conn, dpi=200):
    """Submit a PDF for batch transcription via Gemini Batch API.

    Renders each page to an image and submits batch requests. Large PDFs
    are automatically split into multiple chunks under 18MB each.

    Args:
        client: google.genai.Client instance.
        model: Model name (e.g., "gemini-2.5-flash").
        pdf_path: Path to the PDF file.
        dest_root: Archive root directory.
        conn: SQLite connection.
        dpi: Render DPI for page images (default 200).

    Returns:
        List of batch job name strings, or None if skipped.
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

    # Render pages and build requests, chunking by size
    from transcribe_pdfs_gemini import render_page_to_image, TRANSCRIPTION_PROMPT
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        page_count = len(doc)

        # Build per-page requests and track sizes
        page_requests = []
        page_sizes = []
        for page_num in range(page_count):
            image_bytes = render_page_to_image(doc, page_num, dpi=dpi)
            request, b64_size = _build_request(image_bytes, TRANSCRIPTION_PROMPT)
            page_requests.append(request)
            page_sizes.append(b64_size)
    finally:
        doc.close()

    # Split into chunks under the size limit
    chunks = []  # list of (page_start, requests_list)
    current_chunk = []
    current_size = 0
    chunk_start = 0

    for i, (request, size) in enumerate(zip(page_requests, page_sizes)):
        if current_chunk and current_size + size > _CHUNK_SIZE_LIMIT:
            # Flush current chunk
            chunks.append((chunk_start, current_chunk))
            current_chunk = []
            current_size = 0
            chunk_start = i

        current_chunk.append(request)
        current_size += size

    if current_chunk:
        chunks.append((chunk_start, current_chunk))

    # Submit each chunk as a separate batch job
    batch_ids = []
    chunk_label = f" ({len(chunks)} chunks)" if len(chunks) > 1 else ""

    for chunk_idx, (page_start, chunk_requests) in enumerate(chunks):
        chunk_pages = len(chunk_requests)

        if len(chunks) > 1:
            display_name = f"{pdf_path.name} [pages {page_start+1}-{page_start+chunk_pages}]"
        else:
            display_name = pdf_path.name

        batch_job = client.batches.create(
            model=model,
            src=chunk_requests,
            config={"display_name": display_name},
        )

        batch_id = batch_job.name

        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, page_start, chunk_pages, status)
            VALUES (?, ?, ?, ?, ?, ?, 'submitted')
        """, (batch_id, rel, model, page_count, page_start, chunk_pages))
        conn.commit()

        batch_ids.append(batch_id)

    print(f"  Submitted: {rel} ({page_count} pages{chunk_label}) -> {len(batch_ids)} job(s)")
    return batch_ids


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
        "SELECT batch_id, pdf_path, page_start, chunk_pages FROM batches WHERE status = 'submitted'"
    )
    pending_batches = cursor.fetchall()

    counts = {"pending": 0, "succeeded": 0, "failed": 0, "expired": 0, "cancelled": 0}

    for row in pending_batches:
        batch_id = row["batch_id"]
        pdf_path = row["pdf_path"]
        chunk_info = ""
        if row["chunk_pages"] and row["page_start"] > 0:
            chunk_info = f" [pages {row['page_start']+1}-{row['page_start']+row['chunk_pages']}]"

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
                print(f"  {pdf_path}{chunk_info}: {new_status}")
            else:
                counts["pending"] += 1
                print(f"  {pdf_path}{chunk_info}: pending ({state_name})")

        except Exception as e:
            print(f"  {pdf_path}{chunk_info}: error checking status ({e})")
            counts["pending"] += 1

    total = sum(counts.values())
    print(f"\nBatch status: {total} jobs — "
          f"{counts['pending']} pending, {counts['succeeded']} succeeded, "
          f"{counts['failed']} failed")

    return counts


def collect_results(client, conn, dest_root):
    """Collect results from succeeded batch jobs and write transcript files.

    For multi-chunk PDFs, waits until ALL chunks have succeeded before
    assembling. Gathers page texts from all chunks in page order and
    creates a single .transcript.md file.

    Args:
        client: google.genai.Client instance.
        conn: SQLite connection.
        dest_root: Archive root directory.

    Returns:
        Number of transcripts collected.
    """
    from transcribe_pdfs_gemini import create_transcript_md

    dest_root = Path(dest_root)

    # Find PDFs where all chunks have succeeded (none still submitted/pending)
    cursor = conn.execute("""
        SELECT pdf_path, model, page_count
        FROM batches
        WHERE status = 'succeeded'
        GROUP BY pdf_path
    """)
    candidates = cursor.fetchall()

    if not candidates:
        print("No completed batch jobs to collect.")
        return 0

    collected = 0

    for row in candidates:
        pdf_path_rel = row["pdf_path"]
        model = row["model"]
        total_pages = row["page_count"]
        pdf_path = dest_root / pdf_path_rel

        # Check if any chunks for this PDF are still pending
        pending = conn.execute(
            "SELECT COUNT(*) as cnt FROM batches WHERE pdf_path = ? AND status = 'submitted'",
            (pdf_path_rel,)
        ).fetchone()["cnt"]

        if pending > 0:
            print(f"  {pdf_path_rel}: waiting for {pending} chunk(s) to complete")
            continue

        # Get all succeeded chunks for this PDF, ordered by page_start
        chunks = conn.execute("""
            SELECT batch_id, page_start, chunk_pages
            FROM batches
            WHERE pdf_path = ? AND status = 'succeeded'
            ORDER BY page_start
        """, (pdf_path_rel,)).fetchall()

        try:
            # Gather page texts from all chunks in order
            all_page_texts = {}

            for chunk in chunks:
                batch_id = chunk["batch_id"]
                page_start = chunk["page_start"]

                job = client.batches.get(name=batch_id)

                dest = getattr(job, "dest", None)
                if dest and getattr(dest, "inlined_responses", None):
                    for i, resp in enumerate(dest.inlined_responses):
                        page_num = page_start + i
                        if resp.error:
                            all_page_texts[page_num] = "[Page transcription failed]"
                        elif resp.response and resp.response.text:
                            all_page_texts[page_num] = resp.response.text.strip()
                        else:
                            all_page_texts[page_num] = "[Page appears blank or illegible]"

            if not all_page_texts:
                print(f"  {pdf_path_rel}: no responses found")
                continue

            # Assemble pages in order
            page_texts = [
                all_page_texts.get(pn, "[Page missing from batch response]")
                for pn in range(total_pages)
            ]

            # Create transcript using the shared function
            md_path, confidence, word_count = create_transcript_md(
                pdf_path, page_texts, model, dest_root
            )

            # Mark all chunks as collected
            for chunk in chunks:
                conn.execute("""
                    UPDATE batches SET status = 'collected', completed_at = CURRENT_TIMESTAMP
                    WHERE batch_id = ?
                """, (chunk["batch_id"],))
            conn.commit()

            chunk_info = f" ({len(chunks)} chunks)" if len(chunks) > 1 else ""
            collected += 1
            print(f"  {pdf_path_rel}{chunk_info}: {word_count} words, confidence={confidence}")

        except Exception as e:
            print(f"  {pdf_path_rel}: error collecting ({e})")

    print(f"\nCollected {collected} transcripts")
    return collected
