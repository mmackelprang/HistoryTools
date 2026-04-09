#!/usr/bin/env python3
"""
Date Detection for Undated Files
- Reads transcripts of undated files and asks AI to detect dates
- Produces _date-proposals.json for review
- apply mode renames files with detected dates and moves to year folders

Usage:
    python detect_dates.py                    # propose dates for all undated files
    python detect_dates.py --folder Letters   # one folder
    python detect_dates.py --apply            # apply approved date proposals
    python detect_dates.py --dry-run          # preview without API calls
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config, load_env

TODAY = datetime.now().strftime("%Y-%m-%d")
DEFAULT_MODEL = "gemini-2.5-flash"
REQUESTS_PER_MINUTE = 200

DATE_PROMPT = """You are analyzing a transcript from a family archive to determine when the document was created.

Look for:
- Explicit dates written in the document (letter dates, journal entry headers, "December 5, 1983")
- References to specific events with known dates (holidays, birthdays with ages, school years)
- Contextual clues (mentions of ages, grades, seasons combined with other date references)

Document type: {doc_type}
Current filename: {filename}
Folder: {folder}

Transcript (first 3000 characters):
{body}

If you can determine a date or approximate date, respond with JSON:
{{"date": "YYYY-MM-DD", "confidence": "high|medium|low", "reasoning": "why you chose this date"}}

Use "00" for unknown month or day (e.g., "1983-00-00" for just a year, "1983-06-00" for month without day).

If you CANNOT determine any date, respond with:
{{"date": null, "confidence": "none", "reasoning": "why no date could be determined"}}

Respond with JSON only, no other text."""


RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3


def parse_frontmatter(content):
    """Parse YAML frontmatter and body from a transcript file."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_dict = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm_dict[key.strip()] = val.strip()
    return fm_dict, parts[2].strip()


def call_gemini(client, model, prompt):
    """Call Gemini with retries."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=model, contents=[prompt])
            if response.text is None:
                return None
            cleaned = response.text.strip()
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            if attempt < MAX_RETRIES:
                time.sleep(2)
                continue
            return None
        except Exception as e:
            if any(str(c) in str(e) for c in RETRYABLE_CODES) and attempt < MAX_RETRIES:
                wait = 2 ** attempt * 5
                print(f"    Retry {attempt+1}/{MAX_RETRIES} after {wait}s...")
                time.sleep(wait)
                continue
            raise


def collect_undated_files(dest_root, target_folder=None):
    """Find all undated files with transcripts."""
    if target_folder:
        search_root = dest_root / target_folder
    else:
        search_root = dest_root

    undated = []
    for f in sorted(search_root.rglob("*")):
        if f.is_dir():
            continue
        if f.suffix == ".md" or f.suffix == ".json":
            continue
        if "Photos" in str(f) or "Duplicates" in str(f) or "_pages" in str(f):
            continue
        if not f.name.startswith("undated_"):
            continue
        # Must have a transcript
        md = f.with_suffix(".transcript.md")
        if not md.exists():
            continue
        content = md.read_text(encoding="utf-8", errors="replace")
        if "transcription_confidence: pending" in content:
            continue
        undated.append(f)
    return undated


def propose_dates(args, config, dest_root):
    """Generate date proposals for undated files."""
    if not load_env():
        sys.exit(1)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in .env file.")
        sys.exit(1)

    files = collect_undated_files(dest_root, args.folder)
    if not files:
        print("No undated files with transcripts found.")
        return

    # Load existing proposals for incremental resume
    json_path = dest_root / "_date-proposals.json"
    proposals = []
    already_proposed = set()
    if json_path.exists():
        try:
            proposals = json.load(open(json_path, "r", encoding="utf-8"))
            already_proposed = {p["current_path"] for p in proposals}
            if already_proposed:
                print(f"Loaded {len(proposals)} existing proposals — skipping already-proposed files")
        except (json.JSONDecodeError, IOError):
            proposals = []

    files = [f for f in files if str(f.relative_to(dest_root)).replace("\\", "/") not in already_proposed]

    if not files:
        print("All undated files already have date proposals.")
        return

    print(f"Found {len(files)} undated files to analyze for dates")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for f in files[:20]:
            print(f"  {f.relative_to(dest_root)}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return

    from google import genai
    client = genai.Client(api_key=api_key)

    max_workers = 10
    detected = 0

    def analyze_one(f):
        rel = f.relative_to(dest_root)
        md = f.with_suffix(".transcript.md")
        content = md.read_text(encoding="utf-8", errors="replace")
        fm_dict, body = parse_frontmatter(content)

        folder_key = str(rel).replace("\\", "/").split("/")[0]
        prompt = DATE_PROMPT.format(
            doc_type=fm_dict.get("document_type", "document"),
            filename=f.name,
            folder=folder_key,
            body=body[:3000],
        )

        result = call_gemini(client, args.model, prompt)
        if not result:
            return f, None

        detected_date = result.get("date")
        confidence = result.get("confidence", "none")
        reasoning = result.get("reasoning", "")

        if not detected_date or confidence == "none":
            return f, None

        # Validate date format
        if not re.match(r"\d{4}-\d{2}-\d{2}", detected_date):
            return f, None

        year = detected_date[:4]

        # Determine new path — move from Undated to year folder if applicable
        new_name = f.name.replace("undated_", f"{detected_date}_")
        target_parent = f.parent
        if "Undated" in str(f.parent):
            target_parent = Path(str(f.parent).replace("Undated", year))

        proposal = {
            "current_path": str(rel).replace("\\", "/"),
            "current_name": f.name,
            "detected_date": detected_date,
            "confidence": confidence,
            "proposed_name": new_name,
            "proposed_path": str((target_parent / new_name).relative_to(dest_root)).replace("\\", "/"),
            "folder_move": str(target_parent) != str(f.parent),
            "reasoning": reasoning,
            "approved": True,
        }
        return f, proposal

    print(f"Analyzing with {max_workers} parallel workers...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_one, f): f for f in files}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            f, proposal = future.result()
            rel = f.relative_to(dest_root)
            if proposal:
                proposals.append(proposal)
                detected += 1
                move = " [MOVE]" if proposal.get("folder_move") else ""
                print(f"  [{done_count}/{len(files)}] {rel} -> {proposal['detected_date']}{move} ({proposal['confidence']}: {proposal['reasoning'][:60]})")

                # Save incrementally
                with open(json_path, "w", encoding="utf-8") as jf:
                    json.dump(proposals, jf, indent=2, ensure_ascii=False)
            else:
                print(f"  [{done_count}/{len(files)}] {rel} — no date found")

    # Write final
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(proposals, jf, indent=2, ensure_ascii=False)

    dated = [p for p in proposals if p.get("detected_date")]
    moves = [p for p in proposals if p.get("folder_move")]
    print(f"\n{'=' * 60}")
    print(f"Detected dates for {len(dated)} files ({len(moves)} include folder moves)")
    print(f"Review: {json_path}")
    print(f"Apply: python detect_dates.py --apply")


def apply_dates(args, config, dest_root):
    """Apply approved date proposals."""
    json_path = Path(args.file) if args.file else dest_root / "_date-proposals.json"
    if not json_path.exists():
        print(f"ERROR: Proposals file not found: {json_path}")
        print("Run detect_dates.py first to generate proposals.")
        sys.exit(1)

    proposals = json.load(open(json_path, "r", encoding="utf-8"))
    approved = [p for p in proposals if p.get("approved", True) and p.get("detected_date")]
    skipped_approval = len(proposals) - len(approved)

    if not approved:
        print("No approved date proposals to apply.")
        return

    print(f"Found {len(approved)} approved date proposals ({skipped_approval} skipped)")

    if args.dry_run:
        print("\n--- DRY RUN ---")

    ok_count = 0
    skip_count = 0
    results = []

    for i, p in enumerate(approved, 1):
        current = dest_root / p["current_path"]
        proposed = dest_root / p["proposed_path"]
        print(f"[{i}/{len(approved)}] {p['current_name']} -> {p['proposed_name']}", end="")

        if not current.exists():
            print(f" [SKIPPED: not found]")
            skip_count += 1
            continue

        if proposed.exists() and proposed != current:
            print(f" [SKIPPED: target exists]")
            skip_count += 1
            continue

        if args.dry_run:
            move = " (MOVE)" if p.get("folder_move") else ""
            print(f" [OK]{move}")
            ok_count += 1
            continue

        # Create target directory if needed
        proposed.parent.mkdir(parents=True, exist_ok=True)

        # Rename file
        current.rename(proposed)

        # Rename transcript
        old_md = current.with_suffix(".transcript.md")
        new_md = proposed.with_suffix(".transcript.md")
        transcript_renamed = False
        frontmatter_updated = False

        if old_md.exists():
            old_md.rename(new_md)
            transcript_renamed = True

            # Update source_file in frontmatter
            content = new_md.read_text(encoding="utf-8")
            updated = content.replace(
                f"source_file: {p['current_name']}",
                f"source_file: {p['proposed_name']}",
            )
            if updated != content:
                new_md.write_text(updated, encoding="utf-8")
                frontmatter_updated = True

        move = " (MOVED)" if p.get("folder_move") else ""
        extra = ""
        if transcript_renamed:
            extra = " (+transcript"
            if frontmatter_updated:
                extra += ", frontmatter"
            extra += ")"
        print(f" [OK]{move}{extra}")
        ok_count += 1

        results.append({
            "timestamp": datetime.now().isoformat(),
            "old_path": p["current_path"],
            "new_path": p["proposed_path"],
            "detected_date": p["detected_date"],
            "folder_move": p.get("folder_move", False),
        })

    print(f"\n{'=' * 60}")
    action = "Would rename" if args.dry_run else "Renamed"
    print(f"{action}: {ok_count} files, skipped: {skip_count}")

    if not args.dry_run and results:
        log_path = dest_root / "_date-rename-log.json"
        existing = []
        if log_path.exists():
            try:
                existing = json.load(open(log_path, "r", encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        existing.extend(results)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        print(f"Log saved to {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Detect dates in undated files and propose renames")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--folder", default=None, help="Only scan this subfolder")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--apply", action="store_true", help="Apply approved date proposals")
    parser.add_argument("--file", default=None, help="Path to proposals JSON (for --apply)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]

    if args.apply:
        apply_dates(args, config, dest_root)
    else:
        propose_dates(args, config, dest_root)


if __name__ == "__main__":
    main()
