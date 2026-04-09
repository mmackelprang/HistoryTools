"""
Shared configuration for the Archive Organizer Toolkit.
Edit config.json in the Toolkit root to set paths and options.
"""

import json
from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = {
    "source_root": "",           # REQUIRED: path to source files
    "dest_root": "",             # REQUIRED: path to output organized folder
    "mode": "standalone",        # "standalone" = new archive, "merge" = add to existing
    "exclude_dirs": [".organizer", ".trashbox", "Organized", "Pics2PDF"],
    "exclude_exts": [".ini", ".lnk", ".aup3", ".db", ".tmp"],
    "tesseract_path": "tesseract",
    "whisper_model": "base",     # "tiny", "base", "small", "medium", "large"
    "transcribe_folders": [
        "Letters", "Journals", "Cards",
        "Documents/Writings", "Documents/Church",
        "FamilyMembers", "NeedsReview"
    ],
    "skip_existing_transcripts": True,
    "custom_categories": {}      # filename pattern -> (category, subfolder) overrides
}

def load_config(config_path=None):
    """Load configuration from config.json."""
    if config_path is None:
        config_path = TOOLKIT_DIR / "config.json"

    config = DEFAULT_CONFIG.copy()

    if Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
        config.update(user_config)

    # Validate required fields
    if not config["source_root"]:
        raise ValueError("source_root must be set in config.json")
    if not config["dest_root"]:
        raise ValueError("dest_root must be set in config.json")

    config["source_root"] = Path(config["source_root"])
    config["dest_root"] = Path(config["dest_root"])
    config["exclude_dirs"] = set(config["exclude_dirs"])
    config["exclude_exts"] = set(config["exclude_exts"])

    return config

def save_example_config():
    """Write an example config.json."""
    example = {
        "source_root": "/path/to/source/files",
        "dest_root": "/path/to/Organized",
        "mode": "standalone",
        "exclude_dirs": [".organizer", ".trashbox", "Organized", "Pics2PDF"],
        "exclude_exts": [".ini", ".lnk", ".aup3", ".db", ".tmp"],
        "tesseract_path": "tesseract",
        "whisper_model": "base",
        "transcribe_folders": [
            "Letters", "Journals", "Cards",
            "Documents/Writings", "Documents/Church",
            "FamilyMembers", "NeedsReview"
        ],
        "skip_existing_transcripts": True,
        "custom_categories": {
            "_example_pattern_": ["category", "Subfolder/Path"]
        }
    }
    path = TOOLKIT_DIR / "config.example.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(example, f, indent=2)
    return path

def load_env():
    """Load API keys from .env file in Toolkit root."""
    from dotenv import load_dotenv
    env_path = TOOLKIT_DIR / ".env"
    if not env_path.exists():
        print(f"WARNING: {env_path} not found. Copy .env.example to .env and add your API keys.")
        print(f"See SETUP-API-KEYS.md for instructions.")
        return False
    load_dotenv(env_path, override=True)
    return True
