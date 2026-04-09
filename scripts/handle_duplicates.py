#!/usr/bin/env python3
"""
Duplicate Detection and Handling (Generalized)
Finds files with identical content (MD5 hash) and moves duplicates to Duplicates/.

Usage:
    python handle_duplicates.py                    # uses config.json
    python handle_duplicates.py --config path.json
    python handle_duplicates.py --dry-run          # preview only
"""

import os
import sys
import hashlib
import shutil
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

TODAY = datetime.now().strftime("%Y-%m-%d")

def file_hash(filepath, chunk_size=8192):
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Duplicate Handler")
    parser.add_argument("--config", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]
    dupes_dir = dest_root / "Duplicates"
    dupes_dir.mkdir(parents=True, exist_ok=True)

    print("Scanning for duplicates...")

    # Group by (size, extension) for efficiency
    size_groups = {}
    for root, dirs, files in os.walk(dest_root):
        root_path = Path(root)
        if "Duplicates" in root_path.parts or "_scripts" in root_path.parts or "Toolkit" in root_path.parts:
            continue
        for f in files:
            fp = root_path / f
            if fp.suffix.lower() in ('.md', '.json'):
                continue
            try:
                size = fp.stat().st_size
                key = (size, fp.suffix.lower())
                size_groups.setdefault(key, []).append(fp)
            except OSError:
                pass

    candidates = {k: v for k, v in size_groups.items() if len(v) > 1}
    print(f"Found {len(candidates)} size/ext groups to check")

    duplicates = []
    for (size, ext), files in candidates.items():
        hash_groups = {}
        for f in files:
            try:
                h = file_hash(f)
                hash_groups.setdefault(h, []).append(f)
            except Exception:
                pass

        for h, group in hash_groups.items():
            if len(group) > 1:
                canonical = sorted(group, key=lambda f: str(f))[0]
                for dupe in group[1:]:
                    duplicates.append((dupe, canonical, h))

    print(f"Found {len(duplicates)} duplicate files")

    report_lines = [f"# Duplicates Report\n\nGenerated: {TODAY}\nTotal duplicates: {len(duplicates)}\n"]

    if duplicates:
        report_lines.append("| Duplicate | Canonical Version | Hash |")
        report_lines.append("|-----------|-------------------|------|")

        moved = 0
        for dupe, canonical, h in duplicates:
            rel_dupe = dupe.relative_to(dest_root)
            rel_canon = canonical.relative_to(dest_root)
            report_lines.append(f"| {rel_dupe} | {rel_canon} | {h[:12]}... |")

            if not args.dry_run:
                dest = dupes_dir / dupe.name
                counter = 2
                while dest.exists():
                    dest = dupes_dir / f"{dupe.stem}-{counter}{dupe.suffix}"
                    counter += 1
                try:
                    shutil.move(str(dupe), str(dest))
                    moved += 1
                except Exception as e:
                    print(f"  Error: {e}")

        if args.dry_run:
            print(f"[DRY RUN] Would move {len(duplicates)} files")
        else:
            print(f"Moved {moved} files to Duplicates/")
    else:
        report_lines.append("\nNo duplicate files found.\n")

    with open(dupes_dir / "_duplicates-report.md", 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))

if __name__ == "__main__":
    main()
