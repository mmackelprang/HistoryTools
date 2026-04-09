#!/usr/bin/env python3
"""
Photo Catalog Generator (Generalized)
Catalogs all photos with EXIF data and generates Photos/_index.md.

Usage:
    python catalog_photos.py                    # uses config.json
    python catalog_photos.py --config path.json
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

try:
    import exifread
except ImportError:
    exifread = None

TODAY = datetime.now().strftime("%Y-%m-%d")
PHOTO_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.heic', '.webp'}

def get_exif_date(filepath):
    if exifread is None:
        return None
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=False)
        for tag in ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']:
            if tag in tags:
                parts = str(tags[tag]).split(" ")[0].split(":")
                if len(parts) == 3:
                    return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except Exception:
        pass
    return None

def get_exif_info(filepath):
    info = {}
    if exifread is None:
        return info
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=False)
        if 'Image ImageWidth' in tags:
            info['width'] = str(tags['Image ImageWidth'])
        if 'Image ImageLength' in tags:
            info['height'] = str(tags['Image ImageLength'])
    except Exception:
        pass
    return info

def main():
    parser = argparse.ArgumentParser(description="Photo Catalog Generator")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]
    photos_root = dest_root / "Photos"

    if not photos_root.exists():
        print("No Photos/ folder found. Nothing to catalog.")
        return

    # Find all photos recursively under Photos/
    all_photos = sorted([p for p in photos_root.rglob("*") if p.is_file() and p.suffix.lower() in PHOTO_EXTS])
    print(f"Found {len(all_photos)} photos")

    catalog = [f"# Photo Archive Catalog\n\nGenerated: {TODAY}\nTotal photos: {len(all_photos)}\n"]

    # Group by immediate subfolder
    groups = {}
    for photo in all_photos:
        try:
            rel = photo.relative_to(photos_root)
            subfolder = rel.parts[0] if len(rel.parts) > 1 else "Root"
        except ValueError:
            subfolder = "Root"
        groups.setdefault(subfolder, []).append(photo)

    for subfolder in sorted(groups.keys()):
        photos = groups[subfolder]
        catalog.append(f"\n## {subfolder} ({len(photos)} photos)\n")
        catalog.append("| # | Filename | EXIF Date | Resolution | Size |")
        catalog.append("|---|----------|-----------|------------|------|")

        for i, photo in enumerate(photos, 1):
            exif_date = get_exif_date(photo) or "—"
            info = get_exif_info(photo)
            res = f"{info.get('width','?')}x{info.get('height','?')}" if 'width' in info else "—"
            size_kb = photo.stat().st_size // 1024
            catalog.append(f"| {i} | {photo.name} | {exif_date} | {res} | {size_kb}KB |")

            if i % 500 == 0:
                print(f"  Cataloged {i}/{len(photos)} in {subfolder}")

        print(f"  Cataloged {len(photos)} in {subfolder}")

    index_path = photos_root / "_index.md"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(catalog))
    print(f"\nCatalog written to {index_path}")

if __name__ == "__main__":
    main()
