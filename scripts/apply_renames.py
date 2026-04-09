#!/usr/bin/env python3
"""
Apply Rename Proposals (Phase 2)
- Reads _rename-proposals.json (after human review)
- Renames files and their companion .transcript.md files
- Updates source_file: field in transcript YAML frontmatter
- Logs all changes to _rename-log.json

Usage:
    python apply_renames.py                                    # apply all approved proposals
    python apply_renames.py --dry-run                          # preview changes
    python apply_renames.py --file _rename-proposals.json      # custom proposals file
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

TODAY = datetime.now().strftime("%Y-%m-%d")


def update_frontmatter_source(md_path, old_name, new_name):
    """Update the source_file: field in a transcript's YAML frontmatter."""
    content = md_path.read_text(encoding="utf-8")
    updated = content.replace(
        f"source_file: {old_name}",
        f"source_file: {new_name}",
    )
    if updated != content:
        md_path.write_text(updated, encoding="utf-8")
        return True
    return False


def apply_single_rename(dest_root, proposal, dry_run=False):
    """Apply a single rename: file + transcript + frontmatter."""
    current_path = dest_root / proposal["current_path"]
    proposed_path = dest_root / proposal["proposed_path"]

    if not current_path.exists():
        return {"status": "skipped", "reason": f"File not found: {proposal['current_path']}"}

    if proposed_path.exists() and proposed_path != current_path:
        return {"status": "skipped", "reason": f"Target already exists: {proposal['proposed_path']}"}

    old_name = current_path.name
    new_name = proposed_path.name

    # Companion transcript paths
    old_transcript = current_path.with_suffix(".transcript.md")
    new_transcript = proposed_path.with_suffix(".transcript.md")
    has_transcript = old_transcript.exists()

    result = {
        "timestamp": datetime.now().isoformat(),
        "old_path": proposal["current_path"],
        "new_path": proposal["proposed_path"],
        "transcript_renamed": False,
        "frontmatter_updated": False,
        "status": "ok",
    }

    if dry_run:
        result["status"] = "dry_run"
        result["transcript_renamed"] = has_transcript
        return result

    # Ensure target directory exists (in case folder structure changed)
    proposed_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Rename the source file
    current_path.rename(proposed_path)

    # 2. Rename companion transcript if it exists
    if has_transcript:
        old_transcript.rename(new_transcript)
        result["transcript_renamed"] = True

        # 3. Update source_file: in frontmatter
        # The new_name for source_file should match the renamed source file (not the transcript)
        source_old = old_name  # e.g., "2015-09-17_unknown-2.pdf"
        source_new = new_name  # e.g., "2015-09-17_joshua-eagle-scout-certificate.pdf"
        updated = update_frontmatter_source(new_transcript, source_old, source_new)
        result["frontmatter_updated"] = updated

    return result


def main():
    parser = argparse.ArgumentParser(description="Apply reviewed rename proposals")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--file", default=None, help="Path to proposals JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without renaming")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]

    # Load proposals
    proposals_path = Path(args.file) if args.file else dest_root / "_rename-proposals.json"
    if not proposals_path.exists():
        print(f"ERROR: Proposals file not found: {proposals_path}")
        print("Run propose_renames.py first to generate proposals.")
        sys.exit(1)

    with open(proposals_path, "r", encoding="utf-8") as f:
        proposals = json.load(f)

    # Filter to approved only
    approved = [p for p in proposals if p.get("approved", True)]
    skipped_approval = len(proposals) - len(approved)

    if not approved:
        print("No approved proposals to apply.")
        return

    print(f"Found {len(approved)} approved proposals ({skipped_approval} skipped)")

    if args.dry_run:
        print("\n--- DRY RUN (no files renamed) ---")

    results = []
    ok_count = 0
    skip_count = 0

    for i, proposal in enumerate(approved, 1):
        current = proposal["current_name"]
        proposed = proposal["proposed_name"]
        print(f"[{i}/{len(approved)}] {current} -> {proposed}", end="")

        result = apply_single_rename(dest_root, proposal, args.dry_run)
        results.append(result)

        if result["status"] in ("ok", "dry_run"):
            ok_count += 1
            extra = ""
            if result["transcript_renamed"]:
                extra = " (+transcript"
                if result["frontmatter_updated"]:
                    extra += ", frontmatter updated"
                extra += ")"
            print(f" [OK]{extra}")
        else:
            skip_count += 1
            print(f" [SKIPPED: {result['reason']}]")

    print(f"\n{'=' * 60}")
    action = "Would rename" if args.dry_run else "Renamed"
    print(f"{action}: {ok_count} files, skipped: {skip_count}")

    if not args.dry_run:
        # Write rename log
        log_path = dest_root / "_rename-log.json"

        # Append to existing log if present
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
        print(f"Rename log saved to {log_path} ({len(existing_log)} total entries)")


if __name__ == "__main__":
    main()
