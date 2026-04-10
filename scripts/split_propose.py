#!/usr/bin/env python3
"""
Split Proposal Generator (Phase 1)
- Finds large compilation PDFs with existing transcripts
- Sends transcript text to AI for document boundary detection
- Produces _split-proposals.json and _split-proposals.md for review

Usage:
    python split_propose.py                              # all large files
    python split_propose.py --file path/to/compilation.pdf  # one file
    python split_propose.py --min-pages 10               # only files with 10+ pages
    python split_propose.py --dry-run                    # list files, no API calls
    python split_propose.py --model gemini-2.5-pro       # override model
"""

import re
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config
from ai_client import get_ai_client, call_text, parse_json_response

TODAY = datetime.now().strftime("%Y-%m-%d")
DEFAULT_MIN_PAGES = 5


def find_splittable_pdfs(dest_root, min_pages=5, transcribe_folders=None):
    """Find PDFs with page count >= min_pages that have transcripts.

    Args:
        dest_root: Path to archive root.
        min_pages: Minimum page count threshold.
        transcribe_folders: List of folder names to scan (from config).

    Returns:
        List of (pdf_path, page_count) tuples.
    """
    if transcribe_folders is None:
        transcribe_folders = [
            "Letters", "Journals", "Cards",
            "Documents/Writings", "Documents/Church",
            "FamilyMembers", "NeedsReview",
        ]

    # Load split log to skip already-split files
    already_split = set()
    split_log_path = dest_root / "_split-log.json"
    if split_log_path.exists():
        try:
            with open(split_log_path, "r", encoding="utf-8") as f:
                log_entries = json.load(f)
            already_split = {e.get("source_file", "") for e in log_entries}
        except (json.JSONDecodeError, IOError):
            pass

    results = []
    for folder in transcribe_folders:
        folder_path = dest_root / folder
        if not folder_path.exists():
            continue

        for pdf_path in sorted(folder_path.rglob("*.pdf")):
            if pdf_path.name.startswith("_"):
                continue

            # Skip files that have already been split
            rel_path = str(pdf_path.relative_to(dest_root)).replace("\\", "/")
            if rel_path in already_split:
                continue

            # Check for existing transcript
            transcript_path = pdf_path.with_suffix(".transcript.md")
            if not transcript_path.exists():
                continue

            # Check page count
            try:
                with fitz.open(str(pdf_path)) as doc:
                    page_count = len(doc)
            except Exception:
                continue

            if page_count >= min_pages:
                results.append((pdf_path, page_count))

    return results


def parse_transcript_pages(transcript_body):
    """Parse transcript body into dict of {page_num: text}.

    Handles transcripts with ## Page N markers. If no markers are found,
    returns {1: full_text}.

    Args:
        transcript_body: The body text of a transcript (after frontmatter).

    Returns:
        Dict mapping page numbers (int) to their text content.
    """
    if not transcript_body or not transcript_body.strip():
        return {}

    # Split on ## Page N markers
    page_pattern = re.compile(r"^## Page (\d+)\s*$", re.MULTILINE)
    matches = list(page_pattern.finditer(transcript_body))

    if not matches:
        # No page markers — treat entire body as page 1
        return {1: transcript_body.strip()}

    pages = {}
    for i, match in enumerate(matches):
        page_num = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(transcript_body)
        pages[page_num] = transcript_body[start:end].strip()

    return pages


def get_page_preview(page_text, max_chars=60):
    """Get first line/chars of a page's text for preview.

    Args:
        page_text: Full text of a single page.
        max_chars: Maximum characters to return.

    Returns:
        Preview string, truncated with ellipsis if needed.
    """
    if not page_text or not page_text.strip():
        return "[blank]"

    # Get first non-empty line
    for line in page_text.strip().split("\n"):
        line = line.strip()
        if line:
            if len(line) > max_chars:
                return line[:max_chars - 3] + "..."
            return line

    return "[blank]"


def build_split_prompt(transcript_text, source_file):
    """Build the AI prompt for document boundary detection.

    Args:
        transcript_text: Full transcript body text.
        source_file: Filename of the source PDF (for context).

    Returns:
        Prompt string.
    """
    return f"""You are analyzing a transcript of a compilation PDF containing multiple documents
(letters, journal entries, or mixed documents) scanned into a single file.

The source file is: {source_file}

Identify the boundaries between individual documents. Look for:
- Letter markers: salutations ("Dear ..."), sign-offs ("Love, ..."), dates, address blocks
- Journal entries: date headers, entry separators
- Blank or separator pages
- Shifts in author voice, topic, or handwriting style (noted in image descriptions)
- Page headers/footers that change between documents

For each segment, provide:
- Page numbers (1-indexed, matching the ## Page N markers in the transcript)
- Detected date (YYYY-MM-DD format, use 00 for unknown parts)
- A short descriptive filename slug (lowercase-kebab-case, under 8 words)
- A one-line description
- Whether pages should be skipped (blank separators)

Transcript:
{transcript_text}

Respond with JSON only:
{{
  "segments": [
    {{
      "pages": [1, 2, 3],
      "date": "1984-03-15",
      "slug": "letter-alice-bob-spring-update",
      "description": "Letter from Alice about spring semester",
      "skip": false
    }}
  ]
}}"""


def propose_splits_for_file(transcript_text, source_file, client, vendor, model):
    """Send transcript to AI for boundary detection and parse response.

    Args:
        transcript_text: Full transcript body text.
        source_file: Filename of the source PDF.
        client: AI client from get_ai_client().
        vendor: AI vendor name.
        model: Model name to use.

    Returns:
        List of segment dicts, or None on failure.
    """
    prompt = build_split_prompt(transcript_text, source_file)
    response_text = call_text(client, vendor, prompt, model=model, max_tokens=8192)
    data = parse_json_response(response_text)

    if not data or "segments" not in data:
        return None

    return data["segments"]


def format_page_range(pages):
    """Format a list of page numbers as a compact range string.

    Example: [1, 2, 3, 5, 7, 8, 9] -> "1-3, 5, 7-9"
    """
    if not pages:
        return ""

    pages = sorted(pages)
    ranges = []
    start = pages[0]
    end = pages[0]

    for p in pages[1:]:
        if p == end + 1:
            end = p
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = p

    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)


def build_proposal_entry(source_file, source_pages, segments, transcript_pages, dest_root, pdf_path):
    """Build a proposal entry for one source file.

    Args:
        source_file: Relative path to the source PDF.
        source_pages: Total page count of the source PDF.
        segments: List of segment dicts from AI.
        transcript_pages: Dict of {page_num: text} from parse_transcript_pages.
        dest_root: Archive root path.
        pdf_path: Absolute path to the source PDF.

    Returns:
        Dict with source_file, source_pages, and enriched segments list.
    """
    enriched_segments = []

    for seg in segments:
        pages = seg.get("pages", [])
        date = seg.get("date", "undated")
        slug = seg.get("slug", "unknown")
        description = seg.get("description", "")
        skip = seg.get("skip", False)

        # Sanitize slug (fallback to "unknown" if empty after sanitization)
        slug = re.sub(r"[^a-z0-9-]", "-", slug.lower())
        slug = re.sub(r"-+", "-", slug).strip("-")
        if not slug:
            slug = "unknown"

        # Validate and sanitize date (prevent path traversal from AI)
        if date and date != "undated":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                date = "undated"

        # Build proposed name
        if date and date != "undated":
            proposed_name = f"{date}_{slug}.pdf"
        else:
            proposed_name = f"undated_{slug}.pdf"

        # Determine proposed folder (same folder as source)
        try:
            rel = pdf_path.relative_to(dest_root)
            proposed_folder = str(rel.parent).replace("\\", "/")
            if proposed_folder == ".":
                proposed_folder = ""
        except ValueError:
            proposed_folder = ""

        # Build preview from first page of segment
        preview = ""
        if pages and transcript_pages:
            first_page = min(pages)
            page_text = transcript_pages.get(first_page, "")
            preview = get_page_preview(page_text)

        enriched_segments.append({
            "pages": pages,
            "detected_date": date,
            "proposed_name": proposed_name,
            "proposed_folder": proposed_folder + "/" if proposed_folder else "",
            "description": description,
            "preview": preview,
            "skip": skip,
            "approved": not skip,
        })

    return {
        "source_file": source_file,
        "source_pages": source_pages,
        "segments": enriched_segments,
    }


def write_proposals_md(proposals, dest_root):
    """Write human-readable markdown review table with preview column.

    Args:
        proposals: List of proposal dicts.
        dest_root: Archive root path (for writing the file).

    Returns:
        Path to the written markdown file.
    """
    md_path = dest_root / "_split-proposals.md"

    total_segments = sum(len(p["segments"]) for p in proposals)
    total_files = len(proposals)

    lines = [
        f"# Split Proposals\n",
        f"Generated: {TODAY} | Files: {total_files} | Segments: {total_segments}\n",
        f"Edit `_split-proposals.json` to change names, adjust page ranges, or set `\"approved\": false`.",
        f"Then run: `family-archive split --apply`\n",
    ]

    for p in proposals:
        source = p["source_file"]
        pages = p["source_pages"]
        seg_count = len(p["segments"])
        lines.append(f"\n## {source} ({pages} pages -> {seg_count} segments)\n")
        lines.append("| # | Pages | Date | Proposed Name | Preview |")
        lines.append("|---|-------|------|--------------|---------|")

        for i, seg in enumerate(p["segments"], 1):
            page_str = format_page_range(seg["pages"])
            date = seg.get("detected_date", "\u2014")
            if seg.get("skip"):
                name = "*(skip)*"
            else:
                name = seg["proposed_name"]
            preview = seg.get("preview", "")
            # Escape pipes in preview
            preview = preview.replace("|", "\\|")
            lines.append(f'| {i} | {page_str} | {date} | {name} | "{preview}" |')

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def read_transcript_body(transcript_path):
    """Read a transcript file and return the body text (after frontmatter).

    Args:
        transcript_path: Path to the .transcript.md file.

    Returns:
        Body text string, or None if file doesn't exist.
    """
    if not transcript_path.exists():
        return None

    content = transcript_path.read_text(encoding="utf-8", errors="replace")
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()
    return content.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Propose document splits for compilation PDFs"
    )
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--file", default=None, help="Process a single PDF file")
    parser.add_argument(
        "--min-pages", type=int, default=DEFAULT_MIN_PAGES,
        help=f"Minimum page count to consider (default: {DEFAULT_MIN_PAGES})"
    )
    parser.add_argument("--model", default=None, help="AI model to use")
    parser.add_argument("--vendor", default=None, help="AI vendor (gemini, openai, anthropic)")
    parser.add_argument("--dry-run", action="store_true", help="List files without API calls")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]
    transcribe_folders = config.get("transcribe_folders", None)

    # Find splittable files
    if args.file:
        # Single file mode
        pdf_path = Path(args.file)
        if not pdf_path.is_absolute():
            pdf_path = dest_root / pdf_path
        if not pdf_path.exists():
            print(f"ERROR: File not found: {pdf_path}")
            sys.exit(1)

        transcript_path = pdf_path.with_suffix(".transcript.md")
        if not transcript_path.exists():
            print(f"ERROR: No transcript found for {pdf_path.name}")
            print("Transcribe the file first: family-archive transcribe")
            sys.exit(1)

        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            doc.close()
        except Exception as e:
            print(f"ERROR: Could not open PDF: {e}")
            sys.exit(1)

        splittable = [(pdf_path, page_count)]
    else:
        splittable = find_splittable_pdfs(dest_root, args.min_pages, transcribe_folders)

    if not splittable:
        print(f"No PDFs with >= {args.min_pages} pages and transcripts found.")
        return

    print(f"Found {len(splittable)} files with >= {args.min_pages} pages")

    if args.dry_run:
        print("\n--- DRY RUN (no API calls) ---")
        for pdf_path, page_count in splittable:
            try:
                rel = pdf_path.relative_to(dest_root)
            except ValueError:
                rel = pdf_path
            print(f"  {rel} ({page_count} pages)")
        return

    # Initialize AI client
    client, vendor = get_ai_client(args.vendor)
    model = args.model  # None means use vendor default

    # Load existing proposals for incremental resume
    json_path = dest_root / "_split-proposals.json"
    proposals = []
    already_proposed = set()
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                proposals = json.load(jf)
            already_proposed = {p["source_file"] for p in proposals}
            if already_proposed:
                print(f"Loaded {len(proposals)} existing proposals -- skipping already-proposed files")
        except (json.JSONDecodeError, IOError):
            proposals = []

    # Filter out already-proposed files
    def _safe_rel(p):
        try:
            return str(p.relative_to(dest_root)).replace("\\", "/")
        except ValueError:
            return str(p)

    splittable = [
        (pdf_path, page_count) for pdf_path, page_count in splittable
        if _safe_rel(pdf_path) not in already_proposed
    ]

    if not splittable:
        print("All eligible files already have proposals.")
        md_path = write_proposals_md(proposals, dest_root)
        print(f"Review table saved to {md_path}")
        return

    print(f"{len(splittable)} files remaining to propose")

    request_times = []
    requests_per_minute = 200

    for i, (pdf_path, page_count) in enumerate(splittable, 1):
        try:
            rel = str(pdf_path.relative_to(dest_root)).replace("\\", "/")
        except ValueError:
            rel = str(pdf_path)

        print(f"[{i}/{len(splittable)}] {rel} ({page_count} pages)")

        # Rate limiting
        now = time.time()
        request_times = [t for t in request_times if now - t < 60]
        if len(request_times) >= requests_per_minute:
            wait = 60 - (now - request_times[0]) + 0.5
            print(f"  Rate limit: waiting {wait:.0f}s...")
            time.sleep(wait)

        try:
            # Read transcript
            transcript_path = pdf_path.with_suffix(".transcript.md")
            transcript_body = read_transcript_body(transcript_path)
            if not transcript_body:
                print(f"  SKIP: Empty transcript")
                continue

            # Parse pages for preview generation
            transcript_pages = parse_transcript_pages(transcript_body)

            # Get AI split proposals
            segments = propose_splits_for_file(
                transcript_body, pdf_path.name, client, vendor, model
            )
            request_times.append(time.time())

            if not segments:
                print(f"  SKIP: AI returned no segments")
                continue

            # Build proposal entry
            entry = build_proposal_entry(
                rel, page_count, segments, transcript_pages, dest_root, pdf_path
            )
            proposals.append(entry)

            # Save incrementally
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(proposals, jf, indent=2, ensure_ascii=False)

            print(f"  -> {len(segments)} segments detected")

        except Exception as e:
            print(f"  ERROR: {e}")

    # Write final output
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(proposals, jf, indent=2, ensure_ascii=False)
    print(f"\nProposals saved to {json_path}")

    md_path = write_proposals_md(proposals, dest_root)
    print(f"Review table saved to {md_path}")

    total_segments = sum(len(p["segments"]) for p in proposals)
    print(f"\n{'=' * 60}")
    print(f"Generated {total_segments} split proposals across {len(proposals)} files")
    print(f"Next steps:")
    print(f"  1. Review _split-proposals.md (or edit _split-proposals.json)")
    print(f'  2. Set "approved": false for any segments to skip')
    print(f"  3. Run: family-archive split --apply")


if __name__ == "__main__":
    main()
