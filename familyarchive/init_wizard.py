#!/usr/bin/env python3
"""
Interactive Setup Wizard for HistoryTools

Guides first-time users through configuration:
1. Where are your source files?
2. Where should the organized archive go?
3. (Optional) Scan source to suggest taxonomy folders
4. Set up API keys
5. Verify tools

Usage:
    python init_wizard.py
    family-archive init
"""

import os
import sys
import json
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import TOOLKIT_DIR, DEFAULT_CONFIG, DEFAULT_TAXONOMY, find_tesseract


def prompt_input(message, default=None):
    """Prompt user for input with optional default."""
    if default:
        display = f"{message} [{default}]: "
    else:
        display = f"{message}: "
    value = input(display).strip()
    return value if value else default


def prompt_yes_no(message, default=True):
    """Prompt user for yes/no with default."""
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{message} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def scan_source_for_suggestions(source_path):
    """Quick scan of source directory to suggest what's in there."""
    source = Path(source_path)
    if not source.exists():
        return {}

    counts = {"pdf": 0, "audio": 0, "photo": 0, "video": 0, "other": 0}
    audio_exts = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".wmv"}
    photo_exts = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".heic"}

    for f in source.rglob("*"):
        if f.is_file():
            ext = f.suffix.lower()
            if ext == ".pdf":
                counts["pdf"] += 1
            elif ext in audio_exts:
                counts["audio"] += 1
            elif ext in photo_exts:
                counts["photo"] += 1
            elif ext in video_exts:
                counts["video"] += 1
            else:
                counts["other"] += 1

    return counts


def create_folder_structure(dest_root, taxonomy):
    """Create the archive folder structure from taxonomy."""
    dest = Path(dest_root)
    dest.mkdir(parents=True, exist_ok=True)

    folders_created = 0
    for folder_name in taxonomy.get("folders", {}):
        folder_path = dest / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        folders_created += 1

    # Always create these system folders
    for system_folder in ["NeedsReview", "Unprocessed", "Duplicates"]:
        (dest / system_folder).mkdir(parents=True, exist_ok=True)

    return folders_created


def main():
    print()
    print("=" * 60)
    print("  HistoryTools Setup Wizard")
    print("=" * 60)
    print()
    print("This wizard will help you set up HistoryTools for your")
    print("family archive. You can re-run it anytime to change settings.")
    print()

    # Check if config already exists
    config_path = TOOLKIT_DIR / "config.json"
    if config_path.exists():
        if not prompt_yes_no("config.json already exists. Overwrite?", default=False):
            print("Setup cancelled. Your existing config is unchanged.")
            return

    # Step 1: Source files
    print("\n--- Step 1: Source Files ---\n")
    print("Where are the files you want to organize?")
    print("This can be a folder of scanned documents, photos, audio, etc.")
    source_root = prompt_input("Source folder path")

    if not source_root:
        print("ERROR: Source folder is required.")
        sys.exit(1)

    source_path = Path(source_root).resolve()
    if not source_path.exists():
        print(f"WARNING: {source_path} does not exist yet. That's OK — you can")
        print("create it later or point to a different location.")
    else:
        # Quick scan
        print(f"\nScanning {source_path}...")
        counts = scan_source_for_suggestions(source_path)
        total = sum(counts.values())
        if total > 0:
            print(f"Found {total} files:")
            if counts["pdf"]:
                print(f"  {counts['pdf']} PDFs (documents, letters, etc.)")
            if counts["photo"]:
                print(f"  {counts['photo']} photos")
            if counts["audio"]:
                print(f"  {counts['audio']} audio recordings")
            if counts["video"]:
                print(f"  {counts['video']} videos")
            if counts["other"]:
                print(f"  {counts['other']} other files")

    # Step 2: Destination
    print("\n--- Step 2: Organized Archive Location ---\n")
    default_dest = str(source_path / "Organized") if source_path.exists() else ""
    print("Where should the organized archive be created?")
    dest_root = prompt_input("Destination folder path", default=default_dest)

    if not dest_root:
        print("ERROR: Destination folder is required.")
        sys.exit(1)

    # Step 3: Mode
    print("\n--- Step 3: Mode ---\n")
    dest_path = Path(dest_root).resolve()
    if dest_path.exists() and any(dest_path.iterdir()):
        print("The destination folder already has files.")
        mode = "merge" if prompt_yes_no("Merge new files into existing archive?") else "standalone"
    else:
        mode = "standalone"
        print(f"Mode: standalone (creating new archive)")

    # Step 4: API Keys
    print("\n--- Step 4: AI Features (Optional) ---\n")
    print("AI features improve transcription quality, especially for")
    print("handwritten documents. They require API keys and have small costs.")
    print("You can skip this and add keys later.")
    print()

    env_vars = {}

    if prompt_yes_no("Set up AI features now?", default=True):
        print()
        print("Get a Gemini API key at: https://aistudio.google.com/apikey")
        gemini_key = prompt_input("Gemini API key (Enter to skip)")
        if gemini_key:
            env_vars["GEMINI_API_KEY"] = gemini_key

        print()
        print("Get an AssemblyAI key at: https://www.assemblyai.com/app/account")
        assemblyai_key = prompt_input("AssemblyAI API key (Enter to skip)")
        if assemblyai_key:
            env_vars["ASSEMBLYAI_API_KEY"] = assemblyai_key

        print()
        print("Get an Anthropic key at: https://console.anthropic.com")
        anthropic_key = prompt_input("Anthropic API key (Enter to skip)")
        if anthropic_key:
            env_vars["ANTHROPIC_API_KEY"] = anthropic_key

        print()
        print("Get an OpenAI key at: https://platform.openai.com/api-keys")
        openai_key = prompt_input("OpenAI API key (Enter to skip)")
        if openai_key:
            env_vars["OPENAI_API_KEY"] = openai_key

    # Step 5: Write config
    print("\n--- Writing Configuration ---\n")

    # config.json
    config = {
        "source_root": str(source_path),
        "dest_root": str(dest_path),
        "mode": mode,
        "temp_dir": None,
        "exclude_dirs": list(DEFAULT_CONFIG["exclude_dirs"]) if isinstance(DEFAULT_CONFIG["exclude_dirs"], set) else DEFAULT_CONFIG["exclude_dirs"],
        "exclude_exts": list(DEFAULT_CONFIG["exclude_exts"]) if isinstance(DEFAULT_CONFIG["exclude_exts"], set) else DEFAULT_CONFIG["exclude_exts"],
        "tesseract_path": find_tesseract(),
        "whisper_model": "base",
        "transcribe_folders": [
            "Correspondence/Letters", "Journals", "Correspondence/Cards",
            "Documents/Writings", "Documents/Church",
            "Memories", "NeedsReview"
        ],
        "skip_existing_transcripts": True,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"  Created: {config_path}")

    # .env
    env_path = TOOLKIT_DIR / ".env"
    env_example = TOOLKIT_DIR / ".env.example"
    if env_vars:
        # Read example and fill in keys
        if env_example.exists():
            env_content = env_example.read_text(encoding="utf-8")
        else:
            env_content = ""

        for key, value in env_vars.items():
            if f"{key}=" in env_content:
                # Replace the empty value
                env_content = env_content.replace(f"{key}=", f"{key}={value}")
            else:
                env_content += f"\n{key}={value}\n"

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        print(f"  Created: {env_path} ({len(env_vars)} key(s) configured)")
    elif not env_path.exists() and env_example.exists():
        shutil.copy2(str(env_example), str(env_path))
        print(f"  Created: {env_path} (no keys — add later)")

    # taxonomy.json (copy default if not exists)
    taxonomy_path = TOOLKIT_DIR / "taxonomy.json"
    if not taxonomy_path.exists():
        # Write default taxonomy
        with open(taxonomy_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_TAXONOMY, f, indent=2)
        print(f"  Created: {taxonomy_path}")
    else:
        print(f"  Exists:  {taxonomy_path} (keeping your customizations)")

    # Create folder structure
    folders = create_folder_structure(dest_path, DEFAULT_TAXONOMY)
    print(f"  Created: {dest_path} ({folders} folders)")

    # Step 6: Verify
    print("\n--- Verification ---\n")

    # Check tesseract
    tess = find_tesseract()
    if tess != "tesseract" and Path(tess).exists():
        print(f"  Tesseract: found at {tess}")
    else:
        print(f"  Tesseract: not found (OCR will be skipped)")
        print(f"    Install from: https://github.com/tesseract-ocr/tesseract")

    # Check API keys
    configured_keys = []
    if env_vars.get("GEMINI_API_KEY"):
        configured_keys.append("Gemini")
    if env_vars.get("ASSEMBLYAI_API_KEY"):
        configured_keys.append("AssemblyAI")
    if env_vars.get("ANTHROPIC_API_KEY"):
        configured_keys.append("Anthropic")
    if env_vars.get("OPENAI_API_KEY"):
        configured_keys.append("OpenAI")

    if configured_keys:
        print(f"  AI keys:  {', '.join(configured_keys)}")
    else:
        print(f"  AI keys:  none (local tools only — add keys later in .env)")

    # Done!
    print()
    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print(f"  1. Ingest your files:  family-archive ingest {source_path}")
    print(f"  2. Or scan first:     family-archive ingest {source_path} --scan")
    print(f"  3. Verify tools:      family-archive verify")
    print()
    if not configured_keys:
        print("Tip: Add API keys to .env for AI-powered transcription.")
        print("     See: docs/SETUP-API-KEYS.md")
        print()


if __name__ == "__main__":
    main()
