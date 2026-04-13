#!/usr/bin/env python3
"""
Archive Organizer — File Classification and Copying
Classifies files by name/path patterns, renames them, and copies to an organized taxonomy.

Usage:
    python organize.py                    # uses config.json
    python organize.py --config path.json # uses specified config
    python organize.py --dry-run          # preview without copying
"""

import os
import re
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Add toolkit scripts to path
sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

# ── Date extraction ─────────────────────────────────────────────────────────

def parse_date_from_filename(filename):
    """Extract date from various filename patterns. Returns (year, month, day) or None."""
    stem = Path(filename).stem

    # YYYYMMDD (e.g., "Letter 19830603 PersonA - PersonB")
    m = re.search(r'(\d{4})(\d{2})(\d{2})', stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1800 <= y <= 2030 and 0 <= mo <= 12 and 0 <= d <= 31:
            return (y, mo, d)

    # MMDDYYYY (e.g., "02222023" or "02222023_001")
    m = re.match(r'^(\d{2})(\d{2})(\d{4})(?:_|$)', stem)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1800 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return (y, mo, d)

    # YYYY_MM_DD_HH_MM_SS (scanner timestamp)
    m = re.match(r'^(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})', stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2030:
            return (y, mo, d)

    # YYYYMMxx (partial date)
    m = re.search(r'(\d{4})(\d{2})xx', stem)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1800 <= y <= 2030 and 1 <= mo <= 12:
            return (y, mo, 0)

    # YYYY-YYYY range (use first year)
    m = re.search(r'((?:19|20)\d{2})-((?:19|20)\d{2})', stem)
    if m:
        return (int(m.group(1)), 0, 0)

    # Standalone YYYY
    m = re.search(r'\b((?:19|20)\d{2})\b', stem)
    if m:
        return (int(m.group(1)), 0, 0)

    return None

def format_date(date_tuple):
    if date_tuple is None:
        return "undated"
    y, m, d = date_tuple
    if m == 0 and d == 0:
        return f"{y:04d}-00-00"
    if d == 0:
        return f"{y:04d}-{m:02d}-00"
    return f"{y:04d}-{m:02d}-{d:02d}"

def get_year_folder(date_tuple):
    if date_tuple is None:
        return "Undated"
    return str(date_tuple[0])

# ── Slug generation ─────────────────────────────────────────────────────────

def make_slug(text, max_len=60):
    """Convert text to a filename-safe slug."""
    text = text.lower()
    text = re.sub(r'\.\w+$', '', text)
    text = re.sub(r'\d{8}', '', text)
    text = re.sub(r'\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}(_\d+)?', '', text)
    text = re.sub(r'\d{4}xx\w*', '', text)
    text = re.sub(r'[_\s]+', '-', text)
    text = re.sub(r'[^a-z0-9-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    if len(text) > max_len:
        text = text[:max_len].rsplit('-', 1)[0]
    return text or "unknown"

# ── Classification rules ────────────────────────────────────────────────────

# Each rule: (pattern_type, pattern, category, dest_template)
# pattern_type: "prefix" (filename startswith), "contains" (filename contains),
#               "folder" (source folder matches), "ext" (extension matches)
# dest_template can use {year} placeholder

DEFAULT_RULES = [
    # Filename prefix rules
    ("prefix", "letter",     "letter",   "Letters/{year}"),
    ("prefix", "postcard",   "letter",   "Letters/{year}"),
    ("prefix", "journal",    "journal",  "Journals/{year}"),
    ("prefix", "card ",      "card",     "Cards/{year}"),
    ("prefix", "newspaper",  "document", "Documents/Newspapers"),
    ("prefix", "obituary",   "document", "Documents/Certificates"),

    # Filename contains rules
    ("contains", "certificate",  "document", "Documents/Certificates"),
    ("contains", "ordination",   "document", "Documents/Certificates"),
    ("contains", "announcement", "document", "Documents/Announcements"),
    ("contains", "report card",  "document", "Documents/SchoolRecords"),
    ("contains", "homework",     "document", "Documents/SchoolRecords"),
    ("contains", "graduation",   "document", "Documents/SchoolRecords"),
    ("contains", "transcript",   "document", "Documents/SchoolRecords"),
    ("contains", "diploma",      "document", "Documents/SchoolRecords"),
    ("contains", "receipt",      "financial", "Financial/BillsAndReceipts"),
    ("contains", "invoice",      "financial", "Financial/BillsAndReceipts"),
    ("contains", "statement",    "financial", "Financial/BillsAndReceipts"),
    ("contains", "insurance",    "financial", "Financial/Insurance"),
    ("contains", "tax",          "financial", "Financial/Taxes"),
    ("contains", "mortgage",     "financial", "Financial/HomeRecords"),

    # Extension rules
    ("ext", ".mp3",  "audio",  "AudioRecordings"),
    ("ext", ".wav",  "audio",  "AudioRecordings"),
    ("ext", ".m4a",  "audio",  "AudioRecordings"),
    ("ext", ".flac", "audio",  "AudioRecordings"),
    ("ext", ".jpg",  "photo",  "Photos"),
    ("ext", ".jpeg", "photo",  "Photos"),
    ("ext", ".png",  "photo",  "Photos"),
    ("ext", ".tif",  "photo",  "Photos"),
    ("ext", ".tiff", "photo",  "Photos"),
    ("ext", ".bmp",  "photo",  "Photos"),
    ("ext", ".heic", "photo",  "Photos"),
    ("ext", ".mp4",  "video",  "Video"),
    ("ext", ".mov",  "video",  "Video"),
    ("ext", ".avi",  "video",  "Video"),
    ("ext", ".mkv",  "video",  "Video"),
]

def classify_file(filepath, source_root, rules=None):
    """
    Classify a file based on its name, extension, and source path.
    Returns: (category, dest_subfolder, new_filename)
    """
    if rules is None:
        rules = DEFAULT_RULES

    stem = filepath.stem
    ext = filepath.suffix.lower()
    stem_lower = stem.lower()
    date = parse_date_from_filename(filepath.name)
    date_str = format_date(date)
    year = get_year_folder(date)
    slug = make_slug(stem)

    new_name = f"{date_str}_{slug}{ext}" if date else f"undated_{slug}{ext}"

    # Try source folder routing first
    try:
        rel = filepath.relative_to(source_root)
        parts = list(rel.parts)
        top_folder = parts[0] if len(parts) > 1 else None
    except ValueError:
        top_folder = None

    # Apply rules in order
    for rule_type, pattern, category, dest_template in rules:
        dest = dest_template.replace("{year}", year)

        if rule_type == "prefix" and stem_lower.startswith(pattern):
            return (category, dest, new_name)
        elif rule_type == "contains" and pattern in stem_lower:
            return (category, dest, new_name)
        elif rule_type == "ext" and ext == pattern:
            return (category, dest, new_name)
        elif rule_type == "folder" and top_folder and top_folder.lower() == pattern.lower():
            return (category, dest, new_name)

    # Default: NeedsReview
    return ("needs_review", "NeedsReview", new_name)

# ── File discovery ──────────────────────────────────────────────────────────

def discover_files(source_root, dest_root, exclude_dirs, exclude_exts):
    """Find all content files, excluding metadata and system files."""
    files = []
    for root, dirs, filenames in os.walk(source_root):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        # Skip if inside dest_root
        try:
            root_path.relative_to(dest_root)
            continue
        except ValueError:
            pass

        for fname in filenames:
            fpath = root_path / fname
            if fpath.suffix.lower() in exclude_exts:
                continue
            files.append(fpath)
    return files

# ── Deduplication of destination names ──────────────────────────────────────

def deduplicate_names(file_map):
    """Ensure no two files map to the same destination path."""
    seen = {}
    for i, (src, dest) in enumerate(file_map):
        dest_str = str(dest).lower()  # case-insensitive on Windows
        if dest_str in seen:
            base = dest.stem
            ext = dest.suffix
            counter = 2
            while str(dest.parent / f"{base}-{counter}{ext}").lower() in seen:
                counter += 1
            new_dest = dest.parent / f"{base}-{counter}{ext}"
            file_map[i] = (src, new_dest)
            seen[str(new_dest).lower()] = src
        else:
            seen[dest_str] = src
    return file_map

# ── Folder structure creation ───────────────────────────────────────────────

STANDARD_FOLDERS = [
    "Letters/Undated",
    "Journals/Undated",
    "Cards/Undated",
    "Photos",
    "AudioRecordings",
    "Video",
    "Documents/Certificates",
    "Documents/SchoolRecords",
    "Documents/Newspapers",
    "Documents/Announcements",
    "Documents/Church",
    "Documents/Work",
    "Documents/Genealogy",
    "Documents/Writings",
    "Documents/Misc",
    "Financial/BillsAndReceipts",
    "Financial/Insurance",
    "Financial/Investments",
    "Financial/Taxes",
    "Financial/CarRecords",
    "Financial/HomeRecords",
    "Medical",
    "Recipes",
    "Manuals",
    "FamilyMembers",
    "Duplicates",
    "NeedsReview",
]

def create_folder_structure(dest_root):
    """Create the standard organized folder structure."""
    for folder in STANDARD_FOLDERS:
        (dest_root / folder).mkdir(parents=True, exist_ok=True)

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Archive Organizer — classify and copy files")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Preview without copying")
    args = parser.parse_args()

    config = load_config(args.config)
    source_root = config["source_root"]
    dest_root = config["dest_root"]
    mode = config.get("mode", "standalone")

    print(f"Source: {source_root}")
    print(f"Destination: {dest_root}")
    print(f"Mode: {mode}")
    print()

    # Create folder structure
    if not args.dry_run:
        create_folder_structure(dest_root)

    # Discover files
    print("Discovering files...")
    files = discover_files(source_root, dest_root, config["exclude_dirs"], config["exclude_exts"])
    print(f"Found {len(files)} content files")

    # Load custom rules if any
    rules = DEFAULT_RULES.copy()
    for pattern, (cat, folder) in config.get("custom_categories", {}).items():
        if pattern.startswith("_"):
            continue  # skip example entries
        rules.insert(0, ("contains", pattern.lower(), cat, folder))

    # Classify files
    file_map = []
    stats = {}
    for fpath in files:
        category, dest_subfolder, new_filename = classify_file(fpath, source_root, rules)
        dest_path = dest_root / dest_subfolder / new_filename
        file_map.append((fpath, dest_path))
        stats[category] = stats.get(category, 0) + 1

    file_map = deduplicate_names(file_map)

    print(f"\nClassification summary:")
    for cat, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print(f"  TOTAL: {sum(stats.values())}")

    # In merge mode, check for conflicts with existing files
    if mode == "merge":
        conflicts = [(s, d) for s, d in file_map if d.exists()]
        if conflicts:
            print(f"\n  WARNING: {len(conflicts)} files would overwrite existing files in merge mode.")
            print(f"  These will be skipped. Check _merge-conflicts.json for details.")
            if not args.dry_run:
                with open(dest_root / "_merge-conflicts.json", 'w', encoding='utf-8') as f:
                    json.dump([(str(s), str(d)) for s, d in conflicts], f, indent=2)
            file_map = [(s, d) for s, d in file_map if not d.exists()]

    # Save mapping
    if not args.dry_run:
        mapping_file = dest_root / "_file-mapping.json"
        with open(mapping_file, 'w', encoding='utf-8') as f:
            json.dump([(str(s), str(d)) for s, d in file_map], f, indent=2, ensure_ascii=False)
        print(f"\nMapping saved to {mapping_file}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would copy {len(file_map)} files. No changes made.")
        # Show sample mappings
        for src, dest in file_map[:20]:
            print(f"  {src.name} -> {dest.relative_to(dest_root)}")
        if len(file_map) > 20:
            print(f"  ... and {len(file_map) - 20} more")
        return file_map, stats, []

    # Execute copies
    print(f"\nCopying {len(file_map)} files...")
    copied = 0
    errors = []
    for src, dest in file_map:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            copied += 1
            if copied % 100 == 0:
                print(f"  Copied {copied}/{len(file_map)}...")
        except Exception as e:
            errors.append((str(src), str(dest), str(e)))

    print(f"\nDone! Copied {copied} files.")
    if errors:
        print(f"Errors ({len(errors)}):")
        for src, dest, err in errors[:10]:
            print(f"  {src} -> {err}")
        with open(dest_root / "_copy-errors.json", 'w') as f:
            json.dump(errors, f, indent=2)

    return file_map, stats, errors

if __name__ == "__main__":
    main()
