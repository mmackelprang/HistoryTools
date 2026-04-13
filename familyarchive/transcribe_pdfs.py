#!/usr/bin/env python3
"""
PDF Transcription Script (Generalized)
- Extracts text from PDFs using PyMuPDF (native text layer)
- Falls back to Tesseract OCR for scanned/image-only PDFs
- Generates companion .transcript.md files

Usage:
    python transcribe_pdfs.py                    # uses config.json
    python transcribe_pdfs.py --config path.json
    python transcribe_pdfs.py --folder Letters   # only transcribe one folder
"""

import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config
from quality_check import assess_text_quality

TODAY = datetime.now().strftime("%Y-%m-%d")

def extract_text_pymupdf(pdf_path):
    """Extract text using PyMuPDF native text layer."""
    doc = fitz.open(str(pdf_path))
    pages = [page.get_text().strip() for page in doc]
    doc.close()
    return pages

def extract_text_tesseract(pdf_path, tesseract_path):
    """Extract text using Tesseract OCR via PyMuPDF image rendering."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page_num, page in enumerate(doc):
        mat = fitz.Matrix(300/72, 300/72)
        pix = page.get_pixmap(matrix=mat)
        img_path = pdf_path.parent / f"_temp_ocr_{page_num}.png"
        pix.save(str(img_path))
        try:
            result = subprocess.run(
                [tesseract_path, str(img_path), "stdout", "-l", "eng"],
                capture_output=True, timeout=120,
                encoding='utf-8', errors='replace'
            )
            pages.append(result.stdout.strip())
        except Exception as e:
            pages.append(f"[OCR failed: {e}]")
        finally:
            if img_path.exists():
                img_path.unlink()
    doc.close()
    return pages

def extract_text(pdf_path, tesseract_path):
    """Try native text extraction, fall back to OCR.

    Uses quality assessment to detect garbage text from native extraction
    (e.g., garbled output from handwritten documents with embedded fonts).
    """
    pages = extract_text_pymupdf(pdf_path)
    total_text = " ".join(pages)
    word_count = len(total_text.split())

    if word_count > 20:
        # Check quality of native extraction
        assessment = assess_text_quality(total_text)
        if assessment["quality"] == "good":
            return pages, "native", word_count
        # "suspect" or "poor" -- fall through to Tesseract
        # Native extraction produced garbage (common with handwritten docs)

    pages = extract_text_tesseract(pdf_path, tesseract_path)
    total_text = " ".join(pages)
    word_count = len(total_text.split())
    return pages, "ocr", word_count

def infer_metadata(pdf_path, dest_root):
    """Infer metadata from the organized path and filename."""
    stem = pdf_path.stem
    parts = stem.split("_", 1)
    date_str = parts[0] if len(parts) > 1 else "undated"
    slug = parts[1] if len(parts) > 1 else stem

    try:
        rel = pdf_path.relative_to(dest_root)
        folder = rel.parts[0] if rel.parts else ""
    except ValueError:
        folder = ""

    slug_lower = slug.lower().replace("-", " ")
    doc_type = "document"
    sender = ""
    recipient = ""

    if folder == "Letters":
        doc_type = "letter"
    elif folder == "Journals":
        doc_type = "journal"
    elif folder == "Cards":
        doc_type = "card"

    return {"date": date_str, "sender": sender, "recipient": recipient,
            "doc_type": doc_type, "folder": folder}

def create_transcript_md(pdf_path, pages, method, word_count, dest_root):
    """Create a companion .transcript.md file."""
    meta = infer_metadata(pdf_path, dest_root)
    md_path = pdf_path.with_suffix(".transcript.md")

    # Assess confidence using quality check
    total_text = " ".join(pages)
    assessment = assess_text_quality(total_text)
    if method == "native" and assessment["quality"] == "good" and word_count > 100:
        confidence = "high"
    elif assessment["quality"] in ("good", "suspect") and word_count > 50:
        confidence = "medium"
    else:
        confidence = "low"

    body_parts = []
    for i, page_text in enumerate(pages):
        if len(pages) > 1:
            body_parts.append(f"\n## Page {i+1}\n")
        body_parts.append(page_text if page_text.strip() else "[Page appears blank or illegible]")

    content = f"""---
source_file: {pdf_path.name}
transcription_date: {TODAY}
transcription_confidence: {confidence}
transcription_method: {method} ({"PyMuPDF" if method == "native" else "Tesseract OCR"})
estimated_date: {meta['date']}
document_type: {meta['doc_type']}
sender: {meta['sender'] or 'unknown'}
recipient: {meta['recipient'] or 'unknown'}
page_count: {len(pages)}
word_count: {word_count}
notes: Auto-transcribed from {pdf_path.name}
---

{"".join(body_parts)}
"""
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return md_path, confidence

def main():
    parser = argparse.ArgumentParser(description="PDF Transcription")
    parser.add_argument("--config", default=None)
    parser.add_argument("--folder", default=None, help="Only transcribe PDFs in this subfolder")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]
    tesseract_path = config["tesseract_path"]
    transcribe_folders = config["transcribe_folders"]
    skip_existing = config["skip_existing_transcripts"]

    if args.folder:
        transcribe_folders = [args.folder]

    # Find PDFs in transcription-worthy folders
    all_pdfs = sorted(dest_root.rglob("*.pdf"))
    pdfs = []
    for pdf in all_pdfs:
        rel = str(pdf.relative_to(dest_root)).replace("\\", "/")
        for folder in transcribe_folders:
            if rel.startswith(folder):
                pdfs.append(pdf)
                break

    if skip_existing:
        pdfs = [p for p in pdfs if not p.with_suffix(".transcript.md").exists()]

    print(f"Found {len(pdfs)} PDFs to transcribe")

    results = []
    confidence_counts = {"high": 0, "medium": 0, "low": 0}

    for i, pdf in enumerate(pdfs, 1):
        rel = pdf.relative_to(dest_root)
        print(f"[{i}/{len(pdfs)}] {rel}")
        try:
            pages, method, word_count = extract_text(pdf, tesseract_path)
            _, confidence = create_transcript_md(pdf, pages, method, word_count, dest_root)
            confidence_counts[confidence] += 1
            print(f"  {method} | {word_count} words | {confidence}")
            results.append({"file": str(rel), "method": method, "words": word_count,
                          "pages": len(pages), "confidence": confidence, "status": "ok"})
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"file": str(rel), "status": "error", "error": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"\n{'='*60}")
    print(f"Complete: {ok} succeeded, {err} failed")
    print(f"Confidence: high={confidence_counts['high']}, medium={confidence_counts['medium']}, low={confidence_counts['low']}")

    with open(dest_root / "_pdf-results.json", 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
