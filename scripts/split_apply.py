#!/usr/bin/env python3
"""
Apply Split Proposals (Phase 2)
- Reads _split-proposals.json (after human review)
- Extracts PDF pages into individual files using PyMuPDF
- Extracts transcript text for each segment (free, no AI)
- Creates new .transcript.md files with split provenance
- Logs all changes to _split-log.json

Usage:
    python split_apply.py                                    # apply all approved splits
    python split_apply.py --dry-run                          # preview changes
    python split_apply.py --file _split-proposals.json       # custom proposals file
    python split_apply.py --retranscribe                     # skip transcript extraction
    python split_apply.py --archive-original                 # move originals to _compilations/
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

TODAY = datetime.now().strftime("%Y-%m-%d")


def extract_pdf_pages(source_pdf, page_numbers, output_path):
    """Extract specific pages from a PDF into a new PDF file.

    Args:
        source_pdf: Path to the source PDF file.
        page_numbers: List of 1-indexed page numbers to extract.
        output_path: Path where the new PDF will be written.

    Returns:
        Number of pages extracted.
    """
    source_pdf = Path(source_pdf)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(source_pdf))
    new_doc = fitz.open()

    for page_num in sorted(page_numbers):
        # Convert 1-indexed to 0-indexed
        idx = page_num - 1
        if 0 <= idx < len(doc):
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)

    new_doc.save(str(output_path))
    page_count = len(new_doc)
    new_doc.close()
    doc.close()

    return page_count


def extract_transcript_pages(transcript_body, page_numbers):
    """Extract text for specific pages from a transcript and renumber.

    Parses a transcript body with ## Page N markers, extracts the requested
    pages, and renumbers them starting from 1.

    Args:
        transcript_body: Full transcript body text (after frontmatter).
        page_numbers: List of 1-indexed page numbers to extract.

    Returns:
        Extracted and renumbered transcript text.
    """
    if not transcript_body or not transcript_body.strip():
        return ""

    # Import from split_propose for shared logic
    from split_propose import parse_transcript_pages

    all_pages = parse_transcript_pages(transcript_body)

    if not all_pages:
        return ""

    # Extract requested pages and renumber
    lines = []
    new_page_num = 1
    for original_page in sorted(page_numbers):
        if original_page in all_pages:
            lines.append(f"## Page {new_page_num}")
            lines.append("")
            lines.append(all_pages[original_page])
            lines.append("")
            new_page_num += 1

    return "\n".join(lines).strip()


def create_split_transcript(source_frontmatter, extracted_text, segment, source_filename):
    """Create a .transcript.md file for a split segment.

    Args:
        source_frontmatter: Original frontmatter text (between --- markers).
        extracted_text: Extracted and renumbered page text.
        segment: Segment dict from proposals (with proposed_name, pages, etc.).
        source_filename: Original compilation filename.

    Returns:
        Complete transcript file content as a string.
    """
    proposed_name = segment.get("proposed_name", "unknown.pdf")
    pages = segment.get("pages", [])
    description = segment.get("description", "")

    # Count words in extracted text
    word_count = len(extracted_text.split()) if extracted_text else 0
    page_count = len(pages)

    # Build new frontmatter
    fm_lines = [
        "---",
        f"source_file: {proposed_name}",
        f"page_count: {page_count}",
        f"word_count: {word_count}",
        f"transcription_method: split (from {source_filename})",
        f"transcription_confidence: medium",
    ]

    if description:
        fm_lines.append(f"description: {description}")

    fm_lines.append("---")
    fm_lines.append("")

    body = "\n".join(fm_lines)
    if extracted_text:
        body += extracted_text + "\n"

    return body


def apply_single_split(source_pdf, source_transcript, segment, dest_root, dry_run=False, retranscribe=False):
    """Extract PDF + transcript for one segment.

    Args:
        source_pdf: Path to the source compilation PDF.
        source_transcript: Path to the source transcript file.
        segment: Segment dict from proposals.
        dest_root: Archive root path.
        dry_run: If True, don't create files.
        retranscribe: If True, skip transcript extraction.

    Returns:
        Result dict with status and details.
    """
    pages = segment.get("pages", [])
    proposed_name = segment.get("proposed_name", "unknown.pdf")
    proposed_folder = segment.get("proposed_folder", "")

    # Build output paths
    output_dir = dest_root / proposed_folder if proposed_folder else source_pdf.parent
    output_pdf = output_dir / proposed_name
    output_transcript = output_pdf.with_suffix(".transcript.md")

    result = {
        "timestamp": datetime.now().isoformat(),
        "source_file": str(source_pdf.relative_to(dest_root)).replace("\\", "/") if source_pdf.is_relative_to(dest_root) else str(source_pdf),
        "output_file": str(output_pdf.relative_to(dest_root)).replace("\\", "/") if output_pdf.is_relative_to(dest_root) else str(output_pdf),
        "pages": pages,
        "page_count": len(pages),
        "status": "ok",
        "transcript_created": False,
    }

    # Skip if output already exists
    if output_pdf.exists():
        result["status"] = "skipped"
        result["reason"] = f"Output already exists: {output_pdf.name}"
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["transcript_created"] = not retranscribe
        return result

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract PDF pages
    try:
        extracted_count = extract_pdf_pages(source_pdf, pages, output_pdf)
        result["page_count"] = extracted_count
    except Exception as e:
        result["status"] = "error"
        result["reason"] = f"PDF extraction failed: {e}"
        return result

    # Extract transcript (unless --retranscribe)
    if not retranscribe and source_transcript and source_transcript.exists():
        try:
            # Read source transcript
            content = source_transcript.read_text(encoding="utf-8", errors="replace")
            parts = content.split("---", 2)
            source_frontmatter = parts[1] if len(parts) >= 3 else ""
            body = parts[2].strip() if len(parts) >= 3 else content.strip()

            # Extract pages
            extracted_text = extract_transcript_pages(body, pages)

            # Create new transcript
            transcript_content = create_split_transcript(
                source_frontmatter, extracted_text, segment, source_pdf.name
            )
            output_transcript.write_text(transcript_content, encoding="utf-8")
            result["transcript_created"] = True
        except Exception as e:
            result["transcript_error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Apply reviewed split proposals")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--file", default=None, help="Path to proposals JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without splitting")
    parser.add_argument(
        "--retranscribe", action="store_true",
        help="Skip transcript extraction (re-transcribe split PDFs later)"
    )
    parser.add_argument(
        "--archive-original", action="store_true",
        help="Move originals to _compilations/ subfolder after splitting"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]

    # Load proposals
    proposals_path = Path(args.file) if args.file else dest_root / "_split-proposals.json"
    if not proposals_path.exists():
        print(f"ERROR: Proposals file not found: {proposals_path}")
        print("Run split propose first: family-archive split")
        sys.exit(1)

    with open(proposals_path, "r", encoding="utf-8") as f:
        proposals = json.load(f)

    if not proposals:
        print("No proposals to apply.")
        return

    print(f"Found {len(proposals)} source files with split proposals")

    if args.dry_run:
        print("\n--- DRY RUN (no files created) ---")

    results = []
    ok_count = 0
    skip_count = 0
    error_count = 0

    for p in proposals:
        source_file = p["source_file"]
        source_pages = p["source_pages"]
        segments = p.get("segments", [])

        # Filter to approved, non-skip segments
        approved = [s for s in segments if s.get("approved", True) and not s.get("skip", False)]
        skipped_count = len(segments) - len(approved)

        if not approved:
            print(f"\n{source_file}: no approved segments (all skipped)")
            continue

        print(f"\n{source_file} ({source_pages} pages -> {len(approved)} segments, {skipped_count} skipped)")

        source_pdf = dest_root / source_file
        source_transcript = source_pdf.with_suffix(".transcript.md")

        if not source_pdf.exists():
            print(f"  ERROR: Source PDF not found: {source_file}")
            error_count += 1
            continue

        for j, segment in enumerate(approved, 1):
            proposed_name = segment["proposed_name"]
            page_str = ", ".join(str(pg) for pg in segment["pages"])
            print(f"  [{j}/{len(approved)}] pages {page_str} -> {proposed_name}", end="")

            result = apply_single_split(
                source_pdf, source_transcript, segment, dest_root,
                dry_run=args.dry_run, retranscribe=args.retranscribe
            )
            results.append(result)

            if result["status"] in ("ok", "dry_run"):
                ok_count += 1
                extra = ""
                if result.get("transcript_created"):
                    extra = " (+transcript)"
                print(f" [OK]{extra}")
            elif result["status"] == "skipped":
                skip_count += 1
                print(f" [SKIPPED: {result.get('reason', '')}]")
            else:
                error_count += 1
                print(f" [ERROR: {result.get('reason', '')}]")

        # Archive original if requested
        if args.archive_original and not args.dry_run:
            compilations_dir = source_pdf.parent / "_compilations"
            compilations_dir.mkdir(exist_ok=True)

            try:
                # Move PDF
                new_pdf = compilations_dir / source_pdf.name
                if not new_pdf.exists():
                    source_pdf.rename(new_pdf)
                    print(f"  Archived: {source_pdf.name} -> _compilations/")

                # Move transcript
                if source_transcript.exists():
                    new_transcript = compilations_dir / source_transcript.name
                    if not new_transcript.exists():
                        source_transcript.rename(new_transcript)
                        print(f"  Archived: {source_transcript.name} -> _compilations/")
            except Exception as e:
                print(f"  WARNING: Could not archive original: {e}")
        elif args.archive_original and args.dry_run:
            print(f"  Would archive: {source_pdf.name} -> _compilations/")

    print(f"\n{'=' * 60}")
    action = "Would create" if args.dry_run else "Created"
    print(f"{action}: {ok_count} files, skipped: {skip_count}, errors: {error_count}")

    if not args.dry_run and results:
        # Write split log
        log_path = dest_root / "_split-log.json"

        existing_log = []
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    existing_log = json.load(f)
            except (json.JSONDecodeError, IOError):
                existing_log = []

        successful = [r for r in results if r["status"] == "ok"]
        existing_log.extend(successful)

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(existing_log, f, indent=2, ensure_ascii=False)
        print(f"Split log saved to {log_path} ({len(existing_log)} total entries)")


if __name__ == "__main__":
    main()
