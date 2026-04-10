#!/usr/bin/env python3
"""
Transcript Formatter — mechanical formatting with optional AI summary.

Default mode (free, no API calls):
- Replaces ## Page N markers with clean --- page breaks
- Normalizes whitespace and paragraph breaks
- Strips common scan artifacts (barcodes, copyright boilerplate)
- Marks files with formatting: cleaned in frontmatter

Optional AI mode (--with-summary):
- Adds a 2-4 sentence summary blockquote at the top
- Adds topic headers for long audio transcripts
- Requires API key (Anthropic, Gemini, or OpenAI)

Usage:
    python format_transcripts.py                                    # mechanical (free)
    python format_transcripts.py --with-summary                     # + AI summary
    python format_transcripts.py --folder Journals                  # one folder
    python format_transcripts.py --file path/to/file.transcript.md  # single file
    python format_transcripts.py --force                            # re-format cleaned files
    python format_transcripts.py --dry-run                          # list files
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

TODAY = datetime.now().strftime("%Y-%m-%d")

# ── Scan artifact patterns to strip ─────────────────────────────────────────

ARTIFACT_PATTERNS = [
    # Barcodes
    re.compile(r"^\s*\d{10,}\s*$", re.MULTILINE),
    # ISBN numbers
    re.compile(r"^\s*ISBN[\s:-]*[\d-]+\s*$", re.MULTILINE),
    # Copyright lines
    re.compile(r"^\s*©.*(?:CORP|INC|LLC|LTD|CO\.).*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*(?:©|Copyright)\s*(?:19|20)\d{2}.*$", re.MULTILINE | re.IGNORECASE),
    # Printer registration marks / codes
    re.compile(r"^\s*[A-Z0-9]{2,4}\s+[A-Z0-9]{2}\s*$", re.MULTILINE),
    # "Printed in" lines
    re.compile(r"^\s*Printed in.*$", re.MULTILINE | re.IGNORECASE),
]


# ── Mechanical formatting functions ─────────────────────────────────────────

def format_page_breaks(body):
    """Replace ## Page N markers with --- horizontal rules and italic page refs."""
    def page_replacement(match):
        page_num = match.group(1)
        return f"\n---\n*Page {page_num}*\n"

    return re.sub(r"\n?## Page (\d+)\n?", page_replacement, body)


def normalize_whitespace(body):
    """Clean up excessive whitespace while preserving paragraph structure."""
    # Collapse 3+ consecutive blank lines to 2
    body = re.sub(r"\n{4,}", "\n\n\n", body)
    # Remove trailing whitespace from lines
    body = re.sub(r"[ \t]+$", "", body, flags=re.MULTILINE)
    # Ensure single newline at end
    body = body.strip() + "\n"
    return body


def strip_artifacts(body):
    """Remove common scan artifacts (barcodes, copyright, printer codes)."""
    for pattern in ARTIFACT_PATTERNS:
        body = pattern.sub("", body)
    return body


def break_long_speaker_blocks(body, max_words=250):
    """Break very long speaker blocks into paragraphs at sentence boundaries.

    Only applies to audio transcript format (**Speaker X** (timestamp): text).
    Inserts paragraph breaks at sentence endings near the word limit.
    """
    # Match speaker blocks: **Speaker X** (timestamp): followed by text
    speaker_pattern = re.compile(
        r"(\*\*[^*]+\*\* \([^)]+\):)\s*(.+?)(?=\n\n\*\*[^*]+\*\* \(|\Z)",
        re.DOTALL,
    )

    def split_block(match):
        label = match.group(1)
        text = match.group(2).strip()
        words = text.split()

        if len(words) <= max_words:
            return f"{label} {text}"

        # Split at sentence boundaries near the limit
        paragraphs = []
        current = []
        word_count = 0

        for word in words:
            current.append(word)
            word_count += 1

            if word_count >= max_words and word.rstrip().endswith((".", "!", "?", '."', "!'", '?"')):
                paragraphs.append(" ".join(current))
                current = []
                word_count = 0

        if current:
            paragraphs.append(" ".join(current))

        # First paragraph keeps the speaker label
        result = f"{label} {paragraphs[0]}"
        for p in paragraphs[1:]:
            result += f"\n\n{p}"
        return result

    return speaker_pattern.sub(split_block, body)


def format_body_mechanical(body, transcript_type):
    """Apply all mechanical formatting to a transcript body.

    Args:
        body: Raw transcript body text.
        transcript_type: "pdf" or "audio"

    Returns:
        Formatted body text.
    """
    if transcript_type == "pdf":
        body = format_page_breaks(body)
        body = strip_artifacts(body)

    if transcript_type == "audio":
        body = break_long_speaker_blocks(body)

    body = normalize_whitespace(body)
    return body


# ── Frontmatter handling ────────────────────────────────────────────────────

def parse_frontmatter(content):
    """Parse YAML frontmatter and body from a transcript file."""
    if not content.startswith("---"):
        return "", {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return "", {}, content

    fm_text = parts[1].strip()
    body = parts[2].strip()

    fm_dict = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm_dict[key.strip()] = val.strip()

    return fm_text, fm_dict, body


def detect_type(fm_dict):
    """Detect transcript type from frontmatter fields."""
    method = fm_dict.get("transcription_method", "")
    tool = fm_dict.get("transcription_tool", "")

    if "AssemblyAI" in tool or "Whisper" in tool:
        return "audio"
    if "ai-vision" in method or "native" in method or "ocr" in method or "split" in method:
        return "pdf"
    return "pdf"


def rebuild_file(fm_text, formatted_body, summary=None, title=None, original_title_line=None):
    """Rebuild the transcript file with formatting: cleaned added."""
    if "formatting:" not in fm_text:
        fm_text += "\nformatting: cleaned"
    else:
        fm_text = re.sub(r"formatting:.*", "formatting: cleaned", fm_text)

    parts = [f"---\n{fm_text}\n---\n"]

    if summary:
        parts.append(f"\n{summary}\n")

    if title:
        parts.append(f"\n# {title}\n")
    elif original_title_line:
        parts.append(f"\n{original_title_line}\n")

    if formatted_body:
        parts.append(f"\n{formatted_body}\n")

    return "\n".join(parts)


# ── Optional AI summary ─────────────────────────────────────────────────────

def generate_ai_summary(body, fm_dict, transcript_type):
    """Generate an AI summary for a transcript. Requires API key.

    Returns summary blockquote string, or None on failure.
    """
    from config import load_env
    load_env()

    try:
        from ai_client import get_ai_client, call_text, parse_json_response
    except Exception:
        print("    WARNING: AI client not available for summary generation")
        return None

    source_file = fm_dict.get("source_file", "unknown")

    if transcript_type == "audio":
        prompt = f"""Read this audio transcript and write a 2-4 sentence summary as a markdown blockquote (lines starting with >). Mention who is speaking, what they discuss, and any notable moments.

Source: {source_file}
Transcript (first 3000 chars):
{body[:3000]}

Return ONLY the blockquote summary, nothing else."""
    else:
        prompt = f"""Read this document transcript and write a 2-4 sentence summary as a markdown blockquote (lines starting with >). Mention who wrote it, what it's about, when, and any notable content.

Source: {source_file}
Transcript (first 3000 chars):
{body[:3000]}

Return ONLY the blockquote summary, nothing else."""

    try:
        client, vendor = get_ai_client()
        summary = call_text(client, vendor, prompt, max_tokens=500,
                           pipeline_step="format_summary", file_path=source_file)
        if summary and summary.startswith(">"):
            return summary.strip()
        elif summary:
            # Wrap in blockquote if AI forgot
            lines = summary.strip().split("\n")
            return "\n".join(f"> {line}" for line in lines)
    except Exception as e:
        print(f"    WARNING: Summary generation failed: {e}")

    return None


# ── File collection ─────────────────────────────────────────────────────────

def collect_transcripts(dest_root, target_folder=None, target_file=None, force=False):
    """Collect transcript files to process."""
    if target_file:
        p = Path(target_file)
        if not p.is_absolute():
            p = dest_root / p
        if not p.exists():
            print(f"ERROR: File not found: {p}")
            return []
        return [p]

    if target_folder:
        search_root = dest_root / target_folder
    else:
        search_root = dest_root

    all_transcripts = sorted(search_root.rglob("*.transcript.md"))

    result = []
    for t in all_transcripts:
        content = t.read_text(encoding="utf-8", errors="replace")
        if "transcription_confidence: pending" in content:
            continue
        if not force and "formatting: cleaned" in content:
            continue
        result.append(t)

    return result


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Format transcripts — mechanical cleanup (free) with optional AI summary"
    )
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--folder", default=None, help="Only format transcripts in this subfolder")
    parser.add_argument("--file", default=None, help="Format a single transcript file")
    parser.add_argument("--with-summary", action="store_true",
                        help="Add AI-generated summary (requires API key, costs money)")
    parser.add_argument("--force", action="store_true", help="Re-format already-cleaned files")
    parser.add_argument("--dry-run", action="store_true", help="List files without formatting")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]

    transcripts = collect_transcripts(dest_root, args.folder, args.file, args.force)

    if not transcripts:
        print("No transcripts to format.")
        return

    mode = "mechanical + AI summary" if args.with_summary else "mechanical (free)"
    print(f"Found {len(transcripts)} transcripts to format")
    print(f"Mode: {mode}")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        by_folder = {}
        for t in transcripts:
            try:
                rel = t.relative_to(dest_root)
                folder = str(rel).split("\\")[0].split("/")[0]
            except ValueError:
                folder = "other"
            by_folder.setdefault(folder, []).append(t)

        for folder, files in sorted(by_folder.items()):
            print(f"\n  {folder}: {len(files)} files")
            for f in files[:3]:
                rel = f.relative_to(dest_root) if f.is_relative_to(dest_root) else f
                print(f"    {rel}")
            if len(files) > 3:
                print(f"    ... and {len(files) - 3} more")
        return

    results = {"ok": 0, "error": 0, "skipped": 0}

    for i, t in enumerate(transcripts, 1):
        rel = t.relative_to(dest_root) if t.is_relative_to(dest_root) else t
        content = t.read_text(encoding="utf-8", errors="replace")
        fm_text, fm_dict, body = parse_frontmatter(content)
        transcript_type = detect_type(fm_dict)

        print(f"[{i}/{len(transcripts)}] {rel} [{transcript_type}]")

        if not body.strip():
            print(f"  SKIP: empty body")
            results["skipped"] += 1
            continue

        try:
            # Mechanical formatting (free)
            formatted_body = format_body_mechanical(body, transcript_type)

            # Optional AI summary
            summary = None
            if args.with_summary:
                summary = generate_ai_summary(body, fm_dict, transcript_type)
                if summary:
                    print(f"  + AI summary added")

            # Extract original title line for PDF transcripts
            original_title_line = None
            title = None
            if transcript_type == "pdf":
                title_match = re.match(r"^(# .+)$", body, re.MULTILINE)
                if title_match:
                    original_title_line = title_match.group(1)
            elif transcript_type == "audio":
                title_match = re.match(r"^(# .+)$", body, re.MULTILINE)
                if title_match:
                    original_title_line = title_match.group(1)

            new_content = rebuild_file(fm_text, formatted_body, summary, title, original_title_line)
            t.write_text(new_content, encoding="utf-8")

            word_count = len(formatted_body.split())
            extra = " + summary" if summary else ""
            print(f"  Done: {word_count} words{extra}")
            results["ok"] += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            results["error"] += 1

    print(f"\n{'=' * 60}")
    print(f"Complete: {results['ok']} formatted, {results['error']} errors, {results['skipped']} skipped")
    if not args.with_summary:
        print(f"Tip: Add --with-summary for AI-generated summaries (requires API key)")


if __name__ == "__main__":
    main()
