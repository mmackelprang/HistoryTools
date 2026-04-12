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
