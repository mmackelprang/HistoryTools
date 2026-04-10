#!/usr/bin/env python3
"""
Bootstrap — Scan, classify, and process an entire source folder into an organized archive.

Phase 1 (scan): Recursively walk a source directory, classify every file by type,
filename patterns, and folder context. Produce _bootstrap-plan.json for review.

Phase 2 (execute): Read the approved plan and run the full processing pipeline:
copy → transcribe → format → rename → date-detect → report.

Usage:
    python bootstrap.py /path/to/source --scan                # scan and classify
    python bootstrap.py /path/to/archive.zip --scan           # scan a ZIP file as source
    python bootstrap.py /path/to/source --scan --mode merge   # merge into existing
    python bootstrap.py --execute                              # run the approved plan
    python bootstrap.py /path/to/source                        # interactive: scan + approve + execute
    python bootstrap.py --dry-run /path/to/source --scan       # preview scan

ZIP support:
    - Source can be a .zip file — extracted to a temp directory for scanning
    - ZIPs found inside the source are extracted recursively (handles zip-in-zip)
    - Nested extraction limited to 5 levels deep (reduces risk of deeply nested archives)
    - Source files and folders are NEVER modified — extraction happens in temp dirs
"""

import os
import re
import sys
import json
import shutil
import hashlib
import zipfile
import tempfile
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config, load_taxonomy, DEFAULT_TAXONOMY

TODAY = datetime.now().strftime("%Y-%m-%d")
SCRIPTS_DIR = Path(__file__).parent

# ── File type classification (taxonomy-driven) ────────────────────────────────


def _build_ext_map(taxonomy):
    """Build extension → type-name lookup from taxonomy file_types."""
    ext_map = {}
    for type_name, info in taxonomy["file_types"].items():
        for ext in info["extensions"]:
            ext_map[ext.lower()] = type_name
    return ext_map


def get_file_type(ext, taxonomy=None, _cache={}):
    """Classify a file by its extension. Caches the ext_map per taxonomy id."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY
    ext = ext.lower()
    cache_key = id(taxonomy)
    if cache_key not in _cache:
        _cache[cache_key] = _build_ext_map(taxonomy)
    return _cache[cache_key].get(ext, "unknown")


# ── Folder hint classification (taxonomy-driven) ──────────────────────────────


def _build_folder_hints(taxonomy):
    """Build keyword → dest_folder lookup from taxonomy folders.
    Keywords are lowercased to ensure case-insensitive matching."""
    hints = {}
    for dest_folder, info in taxonomy["folders"].items():
        for keyword in info.get("keywords", []):
            hints[keyword.lower()] = dest_folder
    return hints


def _build_filename_patterns(taxonomy):
    """Build keyword → dest_folder lookup from taxonomy folders (filename_keywords).
    Keywords are lowercased to ensure case-insensitive matching."""
    patterns = {}
    for dest_folder, info in taxonomy["folders"].items():
        for keyword in info.get("filename_keywords", []):
            patterns[keyword.lower()] = dest_folder
    return patterns


def classify_by_folder_hints(source_path, source_root, taxonomy=None):
    """Use source folder names to suggest classification."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY
    folder_hints = _build_folder_hints(taxonomy)

    try:
        rel = source_path.relative_to(source_root)
    except ValueError:
        return None, "none"

    # Check each folder component for hints
    for part in rel.parts[:-1]:  # exclude the filename
        part_lower = part.lower()
        for keyword, dest_folder in folder_hints.items():
            if keyword in part_lower:
                return dest_folder, "folder_hint"

    return None, "none"


def classify_by_filename(filename, taxonomy=None):
    """Use filename patterns to suggest classification."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY
    filename_patterns = _build_filename_patterns(taxonomy)

    stem_lower = Path(filename).stem.lower().replace("-", " ").replace("_", " ")
    for keyword, dest_folder in filename_patterns.items():
        if keyword in stem_lower:
            return dest_folder, "filename_pattern"
    return None, "none"


def classify_by_type_default(file_type, taxonomy=None):
    """Default classification based on file type alone."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY

    # Build defaults from taxonomy file_types route_to
    defaults = {"unknown": "Unprocessed"}
    for type_name, info in taxonomy["file_types"].items():
        route = info.get("route_to")
        if route:
            defaults[type_name] = route

    dest = defaults.get(file_type)
    if dest:
        return dest, "type_default"
    return None, "none"


def classify_file(source_path, source_root, taxonomy=None):
    """Classify a file using all available signals. Returns (dest_folder, classification_source, confidence)."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY
    ext = source_path.suffix.lower()
    file_type = get_file_type(ext, taxonomy)

    # Spreadsheets always go to NeedsReview
    if file_type == "spreadsheet":
        return "NeedsReview", "needs_user_classification", "low"

    # Unknown types go to Unprocessed
    if file_type == "unknown":
        return "Unprocessed", "unknown_extension", "low"

    # Email and genealogy go to imports
    if file_type in ("email", "genealogy"):
        dest, source = classify_by_type_default(file_type, taxonomy)
        return dest, source, "high"

    # Try folder hints first (strongest signal)
    dest, source = classify_by_folder_hints(source_path, source_root, taxonomy)
    if dest:
        return dest, source, "high"

    # Try filename patterns
    dest, source = classify_by_filename(source_path.name, taxonomy)
    if dest:
        return dest, source, "medium"

    # Fall back to type defaults
    dest, source = classify_by_type_default(file_type, taxonomy)
    if dest:
        return dest, source, "medium"

    # Can't classify
    return "NeedsReview", "unclassifiable", "low"


# ── Date extraction ─────────────────────────────────────────────────────────

def parse_date_from_filename(filename):
    """Extract date from filename. Returns 'YYYY-MM-DD' or 'undated'."""
    stem = Path(filename).stem

    # YYYYMMDD
    m = re.search(r'(\d{4})(\d{2})(\d{2})', stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1800 <= y <= 2030 and 0 <= mo <= 12 and 0 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # MMDDYYYY
    m = re.match(r'^(\d{2})(\d{2})(\d{4})(?:_|$)', stem)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1800 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # YYYY_MM_DD_HH_MM_SS (scanner timestamp)
    m = re.match(r'^(\d{4})_(\d{2})_(\d{2})_\d{2}_\d{2}_\d{2}', stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2030:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # Patterns like "Something - Jan 2021" or "Something JAN 2021"
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    m = re.search(r'(\w{3})\s*(\d{4})', stem, re.IGNORECASE)
    if m and m.group(1).lower() in months:
        mo = months[m.group(1).lower()]
        y = int(m.group(2))
        if 1800 <= y <= 2030:
            return f"{y:04d}-{mo:02d}-00"

    # Just a year
    m = re.search(r'((?:19|20)\d{2})', stem)
    if m:
        y = int(m.group(1))
        if 1900 <= y <= 2030:
            return f"{y:04d}-00-00"

    return "undated"


def make_slug(filename):
    """Convert a filename to a kebab-case slug."""
    stem = Path(filename).stem
    # Remove date-like prefixes
    stem = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}[-_]?', '', stem)
    stem = re.sub(r'^\d{8}[-_]?', '', stem)
    stem = re.sub(r'^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}[-_]?', '', stem)
    # Convert to slug
    slug = stem.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug or "unnamed"


def _safe_file_size(filepath):
    """Get file size, returning 0 on any error (broken symlink, permissions, etc.)."""
    try:
        return filepath.stat().st_size
    except (OSError, PermissionError):
        return 0


# ── MD5 hashing for duplicate detection ─────────────────────────────────────

def md5_hash(filepath, chunk_size=8192):
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ── Processing pipeline mapping ─────────────────────────────────────────────

def get_processing_pipeline(file_type, dest_folder, taxonomy=None):
    """Determine which processing steps apply to this file."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY
    pipelines = taxonomy.get("processing_pipelines", {})

    # Files in NeedsReview or Unprocessed only get copied (except photos which
    # always get cataloged regardless of destination)
    if file_type == "photo":
        return list(pipelines.get("photo", ["copy", "catalog_photos"]))

    if dest_folder in ("NeedsReview", "Unprocessed"):
        return ["copy"]

    if file_type in pipelines:
        return list(pipelines[file_type])

    return list(pipelines.get("default", ["copy"]))


# ── ZIP handling ────────────────────────────────────────────────────────────

def _find_zip_files(directory):
    """Find all ZIP files in a directory, case-insensitive."""
    return [f for f in Path(directory).rglob("*")
            if f.is_file() and f.suffix.lower() == ".zip"]


def _safe_extract_zip(zip_path, extract_dir):
    """Extract a ZIP file safely, guarding against Zip Slip (path traversal).
    Returns True on success, False on failure."""
    extract_dir = Path(extract_dir).resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), 'r') as z:
        for member in z.namelist():
            # Resolve the target path and ensure it stays under extract_dir
            target = (extract_dir / member).resolve()
            try:
                target.relative_to(extract_dir)
            except ValueError:
                print(f"  WARNING: Skipping suspicious ZIP entry (path traversal): {member}")
                continue
            z.extract(member, str(extract_dir))


def extract_zips_recursive(directory, depth=0, max_depth=5):
    """Recursively extract all ZIP files found in a directory tree.
    Extracts each ZIP into a subfolder, then scans extracted contents for more ZIPs.
    Limits recursion depth to reduce risk of deeply nested archives."""
    if depth >= max_depth:
        print(f"  WARNING: Max ZIP nesting depth ({max_depth}) reached, skipping deeper ZIPs")
        return 0

    extracted = 0
    zip_files = _find_zip_files(directory)

    for zf in zip_files:
        # Use a dedicated extraction folder name to avoid conflicts with
        # existing folders that happen to share the ZIP's stem name
        extract_dir = zf.parent / f"_extracted_{zf.stem}"
        if extract_dir.exists():
            continue  # already extracted

        try:
            print(f"  Extracting ZIP: {zf.name} ({_safe_file_size(zf) // 1024}KB)")
            _safe_extract_zip(zf, extract_dir)
            extracted += 1

            # Recursively check extracted contents for more ZIPs
            nested = extract_zips_recursive(extract_dir, depth + 1, max_depth)
            extracted += nested

        except zipfile.BadZipFile:
            print(f"  WARNING: {zf.name} is not a valid ZIP file, skipping")
        except Exception as e:
            print(f"  WARNING: Failed to extract {zf.name}: {e}")

    return extracted


def prepare_source(source_path, temp_base=None):
    """Prepare source for scanning. If source is a ZIP file or a directory
    containing ZIPs, extract to a temp directory so the original source is
    never modified. Returns (effective_source_root, temp_dir_or_None).
    Caller must clean up temp_dir when done.

    Args:
        source_path: Path to source directory or ZIP file.
        temp_base: Base directory for temp files. If None, uses system default.
                   If set, creates _historytools_temp/ under this path."""
    source_path = Path(source_path)

    def _make_temp_dir():
        """Create a temp directory in the configured location."""
        if temp_base:
            base = Path(temp_base) / "_historytools_temp"
            base.mkdir(parents=True, exist_ok=True)
            return str(base)
        return tempfile.mkdtemp(prefix="historytools_")

    if source_path.is_file() and source_path.suffix.lower() == ".zip":
        # Source is a ZIP file — extract to temp directory
        temp_dir = _make_temp_dir()
        print(f"Source is a ZIP file — extracting to {temp_dir}")
        try:
            _safe_extract_zip(source_path, temp_dir)
        except zipfile.BadZipFile:
            print(f"ERROR: {source_path} is not a valid ZIP file")
            shutil.rmtree(temp_dir)
            sys.exit(1)

        # Check for nested ZIPs
        nested = extract_zips_recursive(temp_dir)
        if nested:
            print(f"  Extracted {nested} nested ZIP(s)")

        return Path(temp_dir), temp_dir

    if source_path.is_dir():
        # Source is a directory — check for ZIPs inside it
        zip_files = _find_zip_files(source_path)
        if zip_files:
            # Copy source to temp dir so we don't modify the original
            print(f"Found {len(zip_files)} ZIP file(s) in source — copying to temp dir for extraction...")
            temp_dir = _make_temp_dir()
            shutil.copytree(str(source_path), os.path.join(temp_dir, "source"),
                            dirs_exist_ok=True)
            work_dir = Path(temp_dir) / "source"
            extracted = extract_zips_recursive(work_dir)
            if extracted:
                print(f"  Extracted {extracted} ZIP(s)")
            return work_dir, temp_dir
        return source_path, None

    if source_path.is_file():
        print(f"ERROR: {source_path} is not a ZIP file or directory")
        sys.exit(1)

    return source_path, None


# ── Scan phase ──────────────────────────────────────────────────────────────

def scan_source(source_root, dest_root, mode, exclude_dirs, exclude_exts, taxonomy=None):
    """Scan source directory and classify all files. Returns plan dict."""
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY
    source_root = Path(source_root)
    dest_root = Path(dest_root)

    # In merge mode, build hash inventory of existing archive
    existing_hashes = {}
    if mode == "merge" and dest_root.exists():
        print("Building inventory of existing archive for merge...")
        for f in dest_root.rglob("*"):
            if f.is_file() and f.suffix.lower() not in {".md", ".json"}:
                try:
                    existing_hashes[md5_hash(f)] = str(f.relative_to(dest_root))
                except Exception:
                    pass
        print(f"  {len(existing_hashes)} files indexed")

    files = []
    by_type = {}
    by_dest = {}
    unprocessed_types = {}
    needs_review_types = {}
    dupes = 0

    for root, dirs, filenames in os.walk(source_root):
        # Filter excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for filename in sorted(filenames):
            filepath = Path(root) / filename
            ext = filepath.suffix.lower()

            if ext in exclude_exts:
                continue

            # Skip ZIP files (already extracted by prepare_source)
            if ext == ".zip":
                continue

            file_type = get_file_type(ext, taxonomy)
            dest_folder, class_source, confidence = classify_file(filepath, source_root, taxonomy)
            date_prefix = parse_date_from_filename(filename)
            slug = make_slug(filename)
            proposed_name = f"{date_prefix}_{slug}{ext}" if slug else f"{date_prefix}{ext}"

            # Determine subfolder (year or Undated)
            dest_subfolder = None
            if date_prefix != "undated" and date_prefix[:4] != "0000":
                dest_subfolder = date_prefix[:4]
            elif dest_folder not in ("NeedsReview", "Unprocessed", "_imports/EmailArchives", "_imports/SMSExports", "_imports"):
                dest_subfolder = "Undated"

            processing = get_processing_pipeline(file_type, dest_folder, taxonomy)

            # Check for duplicates in merge mode
            is_duplicate = False
            duplicate_of = None
            if mode == "merge" and existing_hashes:
                try:
                    file_hash = md5_hash(filepath)
                    if file_hash in existing_hashes:
                        is_duplicate = True
                        duplicate_of = existing_hashes[file_hash]
                        dupes += 1
                except Exception:
                    pass

            entry = {
                "source_path": str(filepath.relative_to(source_root)).replace("\\", "/"),
                "dest_folder": dest_folder,
                "dest_subfolder": dest_subfolder,
                "proposed_name": proposed_name,
                "file_type": file_type,
                "file_size": _safe_file_size(filepath),
                "classification_source": class_source,
                "classification_confidence": confidence,
                "detected_date": date_prefix if date_prefix != "undated" else None,
                "processing": processing,
                "approved": not is_duplicate,  # duplicates default to not approved
            }

            if is_duplicate:
                entry["duplicate_of"] = duplicate_of
                entry["notes"] = f"Duplicate of {duplicate_of}"

            if file_type == "unknown":
                ext_key = ext or "(no extension)"
                unprocessed_types.setdefault(ext_key, {"count": 0, "example": filename})
                unprocessed_types[ext_key]["count"] += 1

            if dest_folder == "NeedsReview":
                ext_key = ext or "(no extension)"
                needs_review_types.setdefault(ext_key, {"count": 0, "example": filename})
                needs_review_types[ext_key]["count"] += 1

            if file_type == "spreadsheet":
                entry["notes"] = "Spreadsheet — requires manual classification"
            elif file_type == "unknown":
                entry["notes"] = f"Unknown file type {ext} — no processing tooling available"

            files.append(entry)

            by_type[file_type] = by_type.get(file_type, 0) + 1
            by_dest[dest_folder] = by_dest.get(dest_folder, 0) + 1

    plan = {
        "source_root": str(source_root),
        "dest_root": str(dest_root),
        "mode": mode,
        "scan_date": TODAY,
        "summary": {
            "total_files": len(files),
            "by_type": by_type,
            "by_destination": dict(sorted(by_dest.items())),
            "needs_review": sum(1 for f in files if f["dest_folder"] == "NeedsReview"),
            "unprocessable": sum(1 for f in files if f["dest_folder"] == "Unprocessed"),
            "duplicates_detected": dupes,
        },
        "files": files,
        "unprocessed_types": unprocessed_types,
        "needs_review_types": needs_review_types,
    }

    return plan


def print_scan_summary(plan):
    """Print a human-readable scan summary."""
    s = plan["summary"]
    print(f"\nFound {s['total_files']} files\n")

    print("Classification Summary:")
    for dest, count in sorted(s["by_destination"].items()):
        print(f"  {dest:40s} {count} files")

    if plan["needs_review_types"]:
        print(f"\nNeedsReview (requires manual classification):")
        for ext, info in plan["needs_review_types"].items():
            print(f"  {info['count']}x {ext} — e.g., {info['example']}")

    if plan["unprocessed_types"]:
        print(f"\nUnknown file types (stored in Unprocessed/):")
        for ext, info in plan["unprocessed_types"].items():
            print(f"  {ext:12s} {info['count']} files — e.g., {info['example']}")

    if s["duplicates_detected"]:
        print(f"\nPotential duplicates: {s['duplicates_detected']} files (marked not-approved)")

    # Estimate processing costs
    pdf_count = sum(1 for f in plan["files"] if f["file_type"] == "document" and "transcribe" in f.get("processing", []))
    audio_count = sum(1 for f in plan["files"] if f["file_type"] == "audio" and "transcribe_audio" in f.get("processing", []))
    if pdf_count or audio_count:
        print(f"\nProcessing plan:")
        if pdf_count:
            print(f"  {pdf_count} documents -> transcribe + format + rename")
        if audio_count:
            print(f"  {audio_count} audio files -> transcribe + format + rename")


# ── Execute phase ───────────────────────────────────────────────────────────

def copy_files(plan):
    """Copy all approved files to their destinations."""
    dest_root = Path(plan["dest_root"])
    source_root = Path(plan["source_root"])
    approved = [f for f in plan["files"] if f.get("approved", True)]

    copied = 0
    skipped = 0

    for i, entry in enumerate(approved, 1):
        src = source_root / entry["source_path"]
        dest_folder = dest_root / entry["dest_folder"]
        if entry.get("dest_subfolder"):
            dest_folder = dest_folder / entry["dest_subfolder"]
        dest = dest_folder / entry["proposed_name"]

        if dest.exists():
            # Check if this is a collision (different source) vs already-copied (same source)
            if src.exists() and dest.stat().st_size != src.stat().st_size:
                print(f"  WARNING: Destination collision — {entry['proposed_name']} already exists with different content")
            skipped += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(src), str(dest))
            copied += 1
            if i % 50 == 0 or i == len(approved):
                print(f"  [{i}/{len(approved)}] {copied} copied, {skipped} skipped")
        except Exception as e:
            print(f"  ERROR copying {entry['source_path']}: {e}")
            skipped += 1

    print(f"  Done: {copied} copied, {skipped} skipped")
    return copied


def run_script(script_name, extra_args=None):
    """Run a toolkit script and return success."""
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd)
    return result.returncode == 0


def execute_plan(plan, skip_transcribe=False, skip_format=False, config_path_override=None):
    """Execute all stages of the bootstrap plan."""
    dest_root = Path(plan["dest_root"])

    # If source was a ZIP, re-extract it for the copy stage
    temp_dir = None
    source_zip = plan.get("source_extracted_from")
    if source_zip and Path(source_zip).exists():
        temp_base = str(dest_root)
        source_root, temp_dir = prepare_source(Path(source_zip), temp_base=temp_base)
        # Update plan's source_root to point to the re-extracted location
        plan["source_root"] = str(source_root)

    # Ensure config.json exists for downstream scripts
    config_path = Path(config_path_override) if config_path_override else SCRIPTS_DIR.parent / "config.json"
    if not config_path.exists():
        temp_config = {
            "source_root": plan["source_root"],
            "dest_root": plan["dest_root"],
            "mode": plan["mode"],
        }
        with open(config_path, "w") as f:
            json.dump(temp_config, f, indent=2)
        print(f"Created temporary config.json")

    # Pass config path to all downstream scripts
    config_args = ["--config", str(config_path)] if config_path_override else []

    # Stage 1: Copy
    print(f"\n{'=' * 60}")
    print("Stage 1: Copy Files")
    print(f"{'=' * 60}")
    copied = copy_files(plan)

    # Note: do NOT exit early if copied == 0 — downstream stages need to run
    # on previously-copied-but-unprocessed files (crash recovery scenario)

    # Stage 2: Transcribe PDFs
    if not skip_transcribe:
        has_pdfs = any(
            f["file_type"] == "document" and "transcribe" in f.get("processing", [])
            for f in plan["files"] if f.get("approved", True)
        )
        if has_pdfs:
            print(f"\n{'=' * 60}")
            print("Stage 2: Transcribe PDFs")
            print(f"{'=' * 60}")
            run_script("transcribe_pdfs_gemini.py", config_args)

    # Stage 3: Transcribe Audio
    if not skip_transcribe:
        has_audio = any(
            f["file_type"] == "audio" and "transcribe_audio" in f.get("processing", [])
            for f in plan["files"] if f.get("approved", True)
        )
        if has_audio:
            print(f"\n{'=' * 60}")
            print("Stage 3: Transcribe Audio")
            print(f"{'=' * 60}")
            run_script("transcribe_audio_assemblyai.py", config_args)

    # Stage 4: Catalog Photos
    has_photos = any(f["file_type"] == "photo" for f in plan["files"] if f.get("approved", True))
    if has_photos:
        print(f"\n{'=' * 60}")
        print("Stage 4: Catalog Photos")
        print(f"{'=' * 60}")
        run_script("catalog_photos.py", config_args)

    # Stage 5: Detect Duplicates
    print(f"\n{'=' * 60}")
    print("Stage 5: Detect Duplicates")
    print(f"{'=' * 60}")
    run_script("handle_duplicates.py", config_args)

    # Stage 6: Format Transcripts
    if not skip_format:
        print(f"\n{'=' * 60}")
        print("Stage 6: Format Transcripts")
        print(f"{'=' * 60}")
        run_script("format_transcripts.py", config_args)

    # Stage 7: Propose Renames
    print(f"\n{'=' * 60}")
    print("Stage 7: Propose Renames")
    print(f"{'=' * 60}")
    run_script("propose_renames.py", config_args)

    # Stage 8: Detect Dates
    print(f"\n{'=' * 60}")
    print("Stage 8: Detect Dates")
    print(f"{'=' * 60}")
    run_script("detect_dates.py", config_args)

    # Stage 9: Generate Report
    print(f"\n{'=' * 60}")
    print("Stage 9: Generate Report")
    print(f"{'=' * 60}")
    run_script("generate_report.py", config_args)

    # Final summary
    print(f"\n{'=' * 60}")
    print("Bootstrap complete!")
    print(f"{'=' * 60}")
    print(f"\nNext steps:")
    print(f"  1. Review rename proposals: _rename-proposals.md")
    print(f"     Apply: python scripts/apply_renames.py")
    print(f"  2. Review date proposals: _date-proposals.json")
    print(f"     Apply: python scripts/detect_dates.py --apply")
    print(f"  3. Classify files in NeedsReview/ manually")
    print(f"  4. Check Unprocessed/ for files needing future tooling")

    # Clean up temp extraction directory if we re-extracted a ZIP
    if temp_dir and Path(temp_dir).exists():
        print(f"\nCleaning up temporary extraction directory...")
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap — scan, classify, and process a source folder into an organized archive"
    )
    parser.add_argument("source", nargs="?", help="Source directory to scan")
    parser.add_argument("--scan", action="store_true", help="Scan and classify only (produce plan)")
    parser.add_argument("--execute", action="store_true", help="Execute an existing plan")
    parser.add_argument("--mode", default="standalone", choices=["standalone", "merge"],
                        help="standalone (new archive) or merge (add to existing)")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--taxonomy", default=None, help="Path to taxonomy.json")
    parser.add_argument("--skip-transcribe", action="store_true", help="Skip transcription stages")
    parser.add_argument("--skip-format", action="store_true", help="Skip formatting stage")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    # Load taxonomy for classification rules
    taxonomy = load_taxonomy(args.taxonomy)

    # Load config for dest_root and exclusions
    temp_base = None
    try:
        config = load_config(args.config)
        dest_root = config["dest_root"]
        exclude_dirs = config["exclude_dirs"]
        exclude_exts = config["exclude_exts"]
        temp_base = config.get("temp_dir")  # optional: base dir for temp files
        if temp_base is None:
            # Default to dest_root/_historytools_temp if not specified
            temp_base = str(dest_root)
    except (ValueError, FileNotFoundError):
        if args.source:
            dest_root = Path(args.source) / "Organized"
            exclude_dirs = {".organizer", ".trashbox", "Organized", "__pycache__", "_historytools_temp"}
            exclude_exts = {".ini", ".lnk", ".aup3", ".db", ".tmp"}
            temp_base = str(dest_root)
        elif args.execute:
            # In execute mode, we'll get dest_root from the plan file
            dest_root = None
        else:
            print("ERROR: Provide a source directory or create config.json")
            sys.exit(1)

    # Execute mode — load plan first, derive dest_root from it
    if args.execute:
        # Try to find plan file
        if dest_root:
            plan_path = Path(dest_root) / "_bootstrap-plan.json"
        else:
            plan_path = Path("_bootstrap-plan.json")

        if not plan_path.exists():
            print(f"ERROR: No plan found at {plan_path}")
            print("Run with --scan first to generate a plan.")
            sys.exit(1)

        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        if args.dry_run:
            approved = [f for f in plan["files"] if f.get("approved", True)]
            print(f"Would process {len(approved)} files")
            return

        execute_plan(plan, args.skip_transcribe, args.skip_format, args.config)
        return

    # Scan mode (or interactive)
    if not args.source:
        print("ERROR: Provide a source directory to scan.")
        parser.print_help()
        sys.exit(1)

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"ERROR: Source not found: {source_path}")
        sys.exit(1)

    # Handle ZIP files and extract nested ZIPs
    source_root, temp_dir = prepare_source(source_path, temp_base=temp_base)

    try:
        print(f"Scanning {source_root}...")
        plan = scan_source(source_root, dest_root, args.mode, exclude_dirs, exclude_exts, taxonomy)

        # Record if source required extraction (for the plan metadata)
        if temp_dir:
            plan["source_extracted_from"] = str(source_path)
            plan["extraction_type"] = "zip" if source_path.suffix.lower() == ".zip" else "directory_with_zips"

        # Update plan path now that we know dest_root
        plan_path = Path(plan["dest_root"]) / "_bootstrap-plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)

        print_scan_summary(plan)

        if args.dry_run:
            print(f"\n--- DRY RUN: no plan saved ---")
            return

        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
        print(f"\nPlan saved to {plan_path}")

        if args.scan:
            print(f"Review the plan, then run: python scripts/bootstrap.py --execute")
            return

        # Interactive mode: ask for approval then execute
        print(f"\nProceed with processing? [y/N] ", end="")
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = "n"

        if answer in ("y", "yes"):
            execute_plan(plan, args.skip_transcribe, args.skip_format, args.config)
        else:
            print(f"Plan saved. Run later with: python scripts/bootstrap.py --execute")

    finally:
        # Clean up temp directory if we extracted from a ZIP
        if temp_dir and Path(temp_dir).exists():
            print(f"Cleaning up temporary extraction directory...")
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
