#!/usr/bin/env python3
"""
Document Text Extraction — Extract text from Office documents.

Walks the archive, finds supported document files (DOC, DOCX, XLS, XLSX),
extracts text, and creates companion .transcript.md files.

Usage:
    python extract_docs.py                          # all folders
    python extract_docs.py --folder NeedsReview     # one folder
    python extract_docs.py --file path/to/doc.docx  # single file
    python extract_docs.py --dry-run                # preview only
    python extract_docs.py --force                  # overwrite existing
"""

import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config
from core.extract import extract_file, get_supported_extensions, create_extract_transcript


def collect_files(dest_root, folder=None, target_file=None):
    """Collect extractable files from the archive."""
    supported = get_supported_extensions()

    if target_file:
        p = Path(target_file)
        if not p.is_absolute():
            p = dest_root / p
        if p.exists() and p.suffix.lower() in supported:
            return [p]
        return []

    skip_dirs = {".organizer", ".trashbox", "__pycache__", "_historytools_temp", "_duplicates", "_compilations"}
    files = []

    for dirpath, dirnames, filenames in os.walk(str(dest_root)):
        dirpath = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]

        if folder:
            try:
                rel = dirpath.relative_to(dest_root)
                if not str(rel).replace("\\", "/").startswith(folder):
                    continue
            except ValueError:
                continue

        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            fpath = dirpath / fname
            if fpath.suffix.lower() in supported:
                files.append(fpath)

    return files


def run_extraction(dest_root, folder=None, target_file=None, force=False, dry_run=False):
    """Run extraction on all supported files.

    Args:
        dest_root: Archive root directory.
        folder: Optional folder filter.
        target_file: Optional single file path.
        force: Overwrite existing transcripts.
        dry_run: Preview without extracting.

    Returns:
        List of result dicts.
    """
    dest_root = Path(dest_root)
    files = collect_files(dest_root, folder, target_file)

    if not force:
        filtered = []
        for f in files:
            md = f.with_suffix(".transcript.md")
            if not md.exists():
                filtered.append(f)
        skipped = len(files) - len(filtered)
        files = filtered
        if skipped:
            print(f"Skipping {skipped} files with existing transcripts (use --force to overwrite)")

    if not files:
        print("No files found to extract.")
        return []

    print(f"Found {len(files)} files to extract")

    if dry_run:
        print("\n--- DRY RUN (no files created) ---")
        for f in files:
            rel = f.relative_to(dest_root) if f.is_relative_to(dest_root) else f
            existing = f.with_suffix(".transcript.md").exists()
            status = "EXISTS (will overwrite)" if existing else "new"
            print(f"  {rel} [{status}]")
        return []

    results = []
    for i, fpath in enumerate(files, 1):
        rel = fpath.relative_to(dest_root) if fpath.is_relative_to(dest_root) else fpath
        try:
            text, metadata = extract_file(fpath)
            md_path = create_extract_transcript(fpath, text, metadata, dest_root)
            word_count = metadata.get("word_count", 0)
            print(f"  [{i}/{len(files)}] {rel}: {word_count} words ({metadata['format']})")
            results.append({
                "file": str(rel),
                "words": word_count,
                "format": metadata["format"],
                "status": "ok",
            })
        except Exception as e:
            print(f"  [{i}/{len(files)}] {rel}: ERROR — {e}")
            results.append({
                "file": str(rel),
                "status": "error",
                "error": str(e),
            })

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    total_words = sum(r.get("words", 0) for r in results)
    print(f"\nComplete: {ok} extracted, {err} errors, {total_words:,} words total")

    return results


def main():
    parser = argparse.ArgumentParser(description="Extract text from Office documents")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--folder", default=None, help="Only extract from this subfolder")
    parser.add_argument("--file", default=None, help="Extract a single file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing transcripts")
    parser.add_argument("--dry-run", action="store_true", help="Preview without extracting")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]

    run_extraction(dest_root, folder=args.folder, target_file=args.file,
                   force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
