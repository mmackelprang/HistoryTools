#!/usr/bin/env python3
"""
PDF Transcription with Google Gemini (AI Vision)
- Renders each PDF page to an image
- Sends to Gemini for faithful word-for-word transcription
- Handles handwriting, printed text, and embedded images
- Generates companion .transcript.md files

Usage:
    python transcribe_pdfs_gemini.py                          # all configured folders
    python transcribe_pdfs_gemini.py --folder Journals        # one folder only
    python transcribe_pdfs_gemini.py --file path/to/file.pdf  # single file
    python transcribe_pdfs_gemini.py --dry-run                # preview, no API calls
    python transcribe_pdfs_gemini.py --model gemini-2.5-pro   # override model
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config, load_env

TODAY = datetime.now().strftime("%Y-%m-%d")
DEFAULT_MODEL = "gemini-2.5-flash"

TRANSCRIPTION_PROMPT = """You are a precise document transcriber. Transcribe this page EXACTLY as written, word for word.

Rules:
- Reproduce the text FAITHFULLY — do not correct spelling, grammar, or punctuation
- Preserve paragraph breaks and line structure where visible
- For handwritten text, do your best to read every word. If a word is truly illegible, write [illegible]
- If the page contains drawings, photos, doodles, or non-text visual elements, describe them inline as: ![Description of the visual element]
- If the page is blank, write: [Blank page]
- Do NOT add commentary, analysis, summaries, or notes of your own
- Do NOT wrap the output in markdown code blocks
- Output ONLY the transcribed content"""


MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4MB max per page image
DEFAULT_DPI = 200                  # 200 DPI is the sweet spot for AI text recognition


def render_page_to_image(doc, page_num, dpi=None):
    """Render a single PDF page to image bytes, reducing DPI if image is too large.

    Args:
        doc: Open fitz.Document
        page_num: Page index
        dpi: Starting DPI (default: DEFAULT_DPI). Use 300 for highest quality.

    Returns image bytes (PNG, or JPEG if PNG is too large at all DPI levels)."""
    page = doc[page_num]
    start_dpi = max(72, min(dpi or DEFAULT_DPI, 600))  # clamp to sane range

    # Build DPI fallback chain from requested DPI down to 150
    dpi_chain = sorted(set([start_dpi, 200, 150]), reverse=True)
    dpi_chain = [d for d in dpi_chain if d <= start_dpi]
    lowest_dpi = dpi_chain[-1] if dpi_chain else 150

    for try_dpi in dpi_chain:
        mat = fitz.Matrix(try_dpi / 72, try_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        if len(png_bytes) <= MAX_IMAGE_BYTES:
            return png_bytes

    # If still too large at lowest attempted DPI, convert to JPEG at that DPI
    mat = fitz.Matrix(lowest_dpi / 72, lowest_dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    try:
        from PIL import Image
        import io
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except ImportError:
        return png_bytes  # fallback to large PNG


def get_page_count(pdf_path):
    """Get number of pages in a PDF. Returns 0 if file is corrupt."""
    try:
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


RETRYABLE_CODES = {429, 503, 500, 502, 504}
MAX_RETRIES = 3


def transcribe_page_gemini(client, model_name, image_bytes):
    """Send a page image to Gemini and get transcription, with retries for transient errors."""
    from google.genai import types

    # Detect JPEG vs PNG
    mime_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[TRANSCRIPTION_PROMPT, image_part],
            )
            if response.text is None:
                return "[Page appears blank or illegible]"
            return response.text.strip()
        except Exception as e:
            err_str = str(e)
            is_retryable = any(str(code) in err_str for code in RETRYABLE_CODES)
            if is_retryable and attempt < MAX_RETRIES:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after {wait}s ({err_str[:60]}...)")
                time.sleep(wait)
                continue
            raise  # non-retryable or out of retries


def infer_metadata(pdf_path, dest_root):
    """Infer metadata from the organized path and filename."""
    stem = pdf_path.stem
    parts = stem.split("_", 1)
    date_str = parts[0] if len(parts) > 1 else "undated"

    try:
        rel = pdf_path.relative_to(dest_root)
        folder = rel.parts[0] if rel.parts else ""
    except ValueError:
        folder = ""

    doc_type = "document"
    if folder == "Letters":
        doc_type = "letter"
    elif folder == "Journals":
        doc_type = "journal"
    elif folder == "Cards":
        doc_type = "card"

    return {"date": date_str, "doc_type": doc_type, "folder": folder}


def get_pages_dir(pdf_path):
    """Get the incremental pages directory for a PDF."""
    return pdf_path.parent / "_pages" / pdf_path.stem


def save_page(pdf_path, page_num, text):
    """Save a single page's transcription to disk for incremental progress."""
    pages_dir = get_pages_dir(pdf_path)
    pages_dir.mkdir(parents=True, exist_ok=True)
    page_file = pages_dir / f"page_{page_num:04d}.txt"
    page_file.write_text(text, encoding="utf-8")


def load_completed_pages(pdf_path, page_count):
    """Load any previously completed pages. Returns dict of {page_num: text}."""
    pages_dir = get_pages_dir(pdf_path)
    completed = {}
    if not pages_dir.exists():
        return completed
    for page_num in range(page_count):
        page_file = pages_dir / f"page_{page_num:04d}.txt"
        if page_file.exists():
            completed[page_num] = page_file.read_text(encoding="utf-8")
    return completed


def cleanup_pages(pdf_path):
    """Remove the incremental pages directory after successful assembly."""
    pages_dir = get_pages_dir(pdf_path)
    if pages_dir.exists():
        for f in pages_dir.iterdir():
            f.unlink()
        pages_dir.rmdir()
        # Remove _pages dir if empty
        parent = pages_dir.parent
        if parent.name == "_pages" and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def create_transcript_md(pdf_path, page_texts, model_name, dest_root):
    """Create a companion .transcript.md file."""
    meta = infer_metadata(pdf_path, dest_root)
    md_path = pdf_path.with_suffix(".transcript.md")
    total_text = "\n\n".join(page_texts)
    word_count = len(total_text.split())

    if word_count > 100:
        confidence = "high"
    elif word_count > 30:
        confidence = "medium"
    else:
        confidence = "low"

    body_parts = []
    for i, page_text in enumerate(page_texts):
        if len(page_texts) > 1:
            body_parts.append(f"\n## Page {i + 1}\n")
        body_parts.append(
            page_text if page_text.strip() else "[Page appears blank or illegible]"
        )

    content = f"""---
source_file: {pdf_path.name}
transcription_date: {TODAY}
transcription_confidence: {confidence}
transcription_method: ai-vision ({model_name})
estimated_date: {meta['date']}
document_type: {meta['doc_type']}
page_count: {len(page_texts)}
word_count: {word_count}
notes: Transcribed from {pdf_path.name} using Google Gemini
---

{"".join(body_parts)}
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    return md_path, confidence, word_count


def collect_pdfs(dest_root, transcribe_folders, target_folder=None, target_file=None):
    """Collect PDFs to process based on arguments."""
    if target_file:
        p = Path(target_file)
        if not p.is_absolute():
            p = dest_root / p
        if not p.exists():
            print(f"ERROR: File not found: {p}")
            return []
        return [p]

    folders = [target_folder] if target_folder else transcribe_folders
    all_pdfs = sorted(dest_root.rglob("*.pdf"))
    pdfs = []
    for pdf in all_pdfs:
        rel = str(pdf.relative_to(dest_root)).replace("\\", "/")
        for folder in folders:
            if rel.startswith(folder):
                pdfs.append(pdf)
                break
    return pdfs


def main():
    parser = argparse.ArgumentParser(description="PDF Transcription with Google Gemini")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--folder", default=None, help="Only transcribe PDFs in this subfolder")
    parser.add_argument("--file", default=None, help="Transcribe a single PDF file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, choices=range(72, 601),
                        metavar="DPI",
                        help=f"Render DPI for page images (default: {DEFAULT_DPI}, use 300 for highest quality, range: 72-600)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing transcripts")
    parser.add_argument("--low-confidence-only", action="store_true",
                        help="Only transcribe PDFs with low-confidence existing transcripts")
    parser.add_argument("--dry-run", action="store_true", help="List files without transcribing")
    args = parser.parse_args()

    # Load environment and config
    if not args.dry_run:
        if not load_env():
            sys.exit(1)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set in .env file.")
            print("See SETUP-API-KEYS.md for instructions.")
            sys.exit(1)

    config = load_config(args.config)
    dest_root = config["dest_root"]
    transcribe_folders = config["transcribe_folders"]

    pdfs = collect_pdfs(dest_root, transcribe_folders, args.folder, args.file)

    # Filter PDFs based on existing transcript state
    if not args.force:
        before = len(pdfs)
        filtered = []
        for p in pdfs:
            md = p.with_suffix(".transcript.md")
            if not md.exists():
                if not args.low_confidence_only:
                    filtered.append(p)  # no transcript yet (skip in low-confidence mode)
            else:
                content = md.read_text(encoding="utf-8", errors="replace")
                if "transcription_confidence: pending" in content or "transcription failed" in content:
                    filtered.append(p)  # error stub — always retry
                elif "[OCR failed:" in content or "[Page appears blank or illegible]" in content:
                    filtered.append(p)  # OCR failures — needs AI
                elif args.low_confidence_only and "transcription_confidence: low" in content:
                    filtered.append(p)  # low confidence — AI can do better
                # else: medium/high confidence — skip
        pdfs = filtered
        skipped = before - len(pdfs)
        if skipped:
            mode = "low-confidence" if args.low_confidence_only else "successful"
            print(f"Skipping {skipped} files (not {mode}, use --force to overwrite)")

    if not pdfs:
        print("No PDFs found to transcribe.")
        return

    # Count total pages for cost estimate
    total_pages = 0
    for pdf in pdfs:
        try:
            total_pages += get_page_count(pdf)
        except Exception:
            total_pages += 1  # assume at least 1

    print(f"Found {len(pdfs)} PDFs ({total_pages} total pages) to transcribe")
    print(f"Model: {args.model}")
    est_cost = total_pages * 0.0003  # rough estimate for Flash
    if "pro" in args.model.lower():
        est_cost = total_pages * 0.003
    print(f"Estimated cost: ${est_cost:.2f}")

    if args.dry_run:
        print("\n--- DRY RUN (no API calls) ---")
        for pdf in pdfs:
            rel = pdf.relative_to(dest_root) if pdf.is_relative_to(dest_root) else pdf
            pages = get_page_count(pdf)
            existing = pdf.with_suffix(".transcript.md").exists()
            status = "EXISTS (will overwrite)" if existing else "new"
            print(f"  {rel} ({pages} pages) [{status}]")
        print(f"\nTotal: {len(pdfs)} files, {total_pages} pages")
        return

    # Initialize Gemini client
    from google import genai
    client = genai.Client(api_key=api_key)

    results = []
    confidence_counts = {"high": 0, "medium": 0, "low": 0}
    request_times = []

    for i, pdf in enumerate(pdfs, 1):
        rel = pdf.relative_to(dest_root) if pdf.is_relative_to(dest_root) else pdf
        page_count = get_page_count(pdf)
        print(f"\n[{i}/{len(pdfs)}] {rel} ({page_count} pages)")

        try:
            # Check for previously completed pages (incremental resume)
            completed = load_completed_pages(pdf, page_count)
            remaining_pages = [pn for pn in range(page_count) if pn not in completed]

            if completed:
                print(f"  Resuming: {len(completed)} pages cached, {len(remaining_pages)} remaining")

            # Render only pages that need processing
            doc = fitz.open(str(pdf))
            page_images = {}
            for page_num in remaining_pages:
                page_images[page_num] = render_page_to_image(doc, page_num, dpi=args.dpi)
            doc.close()

            # Process remaining pages in parallel (up to 10 concurrent API calls)
            page_texts = {pn: text for pn, text in completed.items()}
            max_workers = min(10, len(remaining_pages)) if remaining_pages else 1

            def process_page(page_num):
                return page_num, transcribe_page_gemini(client, args.model, page_images[page_num])

            if remaining_pages:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(process_page, pn): pn for pn in remaining_pages}
                    done_count = len(completed)
                    for future in as_completed(futures):
                        pn, text = future.result()
                        page_texts[pn] = text
                        save_page(pdf, pn, text)  # save incrementally
                        done_count += 1
                        if page_count > 1:
                            print(f"  Page {pn + 1}/{page_count}: {len(text.split())} words ({done_count}/{page_count} done)")

            # Assemble all pages in order
            ordered_texts = [page_texts[pn] for pn in range(page_count)]

            md_path, confidence, word_count = create_transcript_md(
                pdf, ordered_texts, args.model, dest_root
            )
            cleanup_pages(pdf)  # remove temp page files after successful assembly
            confidence_counts[confidence] += 1
            print(f"  Done: {word_count} words, confidence={confidence}")
            results.append({
                "file": str(rel),
                "pages": page_count,
                "words": word_count,
                "confidence": confidence,
                "model": args.model,
                "status": "ok",
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            # Don't overwrite page progress — only write error stub if no pages saved
            pages_dir = get_pages_dir(pdf)
            saved_pages = len(list(pages_dir.iterdir())) if pages_dir.exists() else 0
            if saved_pages > 0:
                print(f"  {saved_pages}/{page_count} pages saved — will resume on next run")
            # Write error stub
            md_path = pdf.with_suffix(".transcript.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(
                    f"---\nsource_file: {pdf.name}\ntranscription_date: {TODAY}\n"
                    f"transcription_confidence: pending\npage_count: {page_count}\n"
                    f"notes: Gemini transcription failed — {e} ({saved_pages}/{page_count} pages saved)\n---\n\n"
                    f"[Transcription failed — {saved_pages}/{page_count} pages completed, will resume on retry]\n"
                )
            results.append({
                "file": str(rel),
                "pages": page_count,
                "status": "error",
                "error": str(e),
            })

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    total_words = sum(r.get("words", 0) for r in results)
    print(f"\n{'=' * 60}")
    print(f"Complete: {ok} succeeded, {err} failed")
    print(f"Total words transcribed: {total_words:,}")
    print(f"Confidence: high={confidence_counts['high']}, medium={confidence_counts['medium']}, low={confidence_counts['low']}")

    results_path = dest_root / "_gemini-pdf-results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {results_path}")


if __name__ == "__main__":
    main()
