"""
Shared configuration for the Archive Organizer Toolkit.
Edit config.json in the Toolkit root to set paths and options.
Edit taxonomy.json to customize file classification rules.
"""

import json
from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent.parent.parent
# When installed as a package, TOOLKIT_DIR should be the current working directory
# if no config.json is found at the parent level
if not (TOOLKIT_DIR / "config.json").exists() and not (TOOLKIT_DIR / "config.example.json").exists():
    TOOLKIT_DIR = Path.cwd()

# ── Default taxonomy (fallback when taxonomy.json is absent) ──────────────────

DEFAULT_TAXONOMY = {
    "version": 1,
    "file_types": {
        "audio": {
            "extensions": [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"],
            "route_to": "Media/Audio/FamilyRecordings",
        },
        "video": {
            "extensions": [".mp4", ".mov", ".avi", ".mkv", ".wmv"],
            "route_to": "Media/Video",
        },
        "photo": {
            "extensions": [".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".heic"],
            "route_to": "Media/Photos",
        },
        "document": {
            "extensions": [".pdf", ".doc", ".docx", ".txt", ".rtf"],
        },
        "spreadsheet": {
            "extensions": [".xls", ".xlsx", ".csv"],
            "route_to": "NeedsReview",
        },
        "email": {
            "extensions": [".eml", ".mbox", ".pst"],
            "route_to": "_imports/EmailArchives",
        },
        "genealogy": {
            "extensions": [".gedcom", ".ged"],
            "route_to": "_imports",
        },
    },
    "folders": {
        "Correspondence/Letters": {
            "keywords": ["letter", "letters", "correspondence"],
            "filename_keywords": ["letter"],
            "description": "Personal correspondence and letters",
        },
        "Correspondence/Cards": {
            "keywords": ["card", "cards", "postcard"],
            "filename_keywords": ["postcard", "card"],
            "description": "Greeting cards and postcards",
        },
        "Journals": {
            "keywords": ["journal", "journals", "diary", "diaries"],
            "filename_keywords": ["journal", "diary"],
            "description": "Diaries and journals",
        },
        "Documents/Church": {
            "keywords": ["church", "religious"],
            "description": "Church and religious documents",
        },
        "Documents/Education": {
            "keywords": ["school", "education", "homework"],
            "description": "School and education documents",
        },
        "Documents/Legal": {
            "keywords": ["legal", "certificate"],
            "description": "Legal documents and certificates",
        },
        "Documents/Employment": {
            "keywords": ["employment", "work"],
            "description": "Employment and work documents",
        },
        "Documents/Writings": {
            "keywords": ["writing", "writings", "essay"],
            "description": "Personal writings and essays",
        },
        "Documents/Recipes": {
            "keywords": ["recipe", "recipes", "cookbook"],
            "filename_keywords": ["recipe"],
            "description": "Recipes and cookbooks",
        },
        "Financial": {
            "keywords": ["financial", "finance"],
            "description": "Financial documents",
        },
        "Financial/Taxes": {
            "keywords": ["tax", "taxes"],
            "description": "Tax documents",
        },
        "Financial/Insurance": {
            "keywords": ["insurance"],
            "description": "Insurance documents",
        },
        "Financial/BillsAndReceipts": {
            "keywords": ["bill", "bills", "receipt", "receipts"],
            "description": "Bills and receipts",
        },
        "Medical": {
            "keywords": ["medical", "health"],
            "description": "Medical and health records",
        },
        "Medical/Dental": {
            "keywords": ["dental"],
            "description": "Dental records",
        },
        "Media/Photos": {
            "keywords": ["photo", "photos", "picture", "pictures"],
            "description": "Photographs",
        },
        "Media/Audio/FamilyRecordings": {
            "keywords": ["audio", "recording", "recordings"],
            "description": "Family audio recordings",
        },
        "Media/Audio/CassetteTapes": {
            "keywords": ["tape", "tapes", "cassette"],
            "description": "Cassette tape recordings",
        },
        "Media/Audio/Songs": {
            "keywords": ["music", "song", "songs"],
            "description": "Music and songs",
        },
        "Media/Video": {
            "keywords": ["video", "videos", "movie", "movies"],
            "description": "Video recordings",
        },
        "Memories": {
            "keywords": ["memory", "memories", "memorial", "obituary"],
            "filename_keywords": ["obituary", "eulogy", "memoir"],
            "description": "Memorials, obituaries, and eulogies",
        },
    },
    "processing_pipelines": {
        "document": ["copy", "transcribe", "format", "rename", "detect_date"],
        "audio": ["copy", "transcribe_audio", "format", "rename"],
        "photo": ["copy", "catalog_photos"],
        "video": ["copy"],
        "default": ["copy"],
    },
}


def load_taxonomy(taxonomy_path=None):
    """Load taxonomy configuration from taxonomy.json.

    Falls back to DEFAULT_TAXONOMY when the file is absent.
    """
    if taxonomy_path is None:
        taxonomy_path = TOOLKIT_DIR / "taxonomy.json"

    if not Path(taxonomy_path).exists():
        import copy
        return copy.deepcopy(DEFAULT_TAXONOMY)

    with open(taxonomy_path, 'r', encoding='utf-8') as f:
        return json.load(f)
def find_tesseract():
    """Find the Tesseract executable, checking common install locations on Windows."""
    import shutil as _shutil
    import platform

    # Check PATH first
    found = _shutil.which("tesseract")
    if found:
        return found

    # Check common Windows install locations
    if platform.system() == "Windows":
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        ]
        for p in common_paths:
            if Path(p).exists():
                return str(p)

    # Fallback — let subprocess try and fail with a clear error
    return "tesseract"


DEFAULT_CONFIG = {
    "source_root": "",           # REQUIRED: path to source files
    "dest_root": "",             # REQUIRED: path to output organized folder
    "mode": "standalone",        # "standalone" = new archive, "merge" = add to existing
    "temp_dir": None,            # optional: base dir for temp files (default: dest_root)
    "exclude_dirs": [".organizer", ".trashbox", "Organized", "Pics2PDF", "_historytools_temp"],
    "exclude_exts": [".ini", ".lnk", ".aup3", ".db", ".tmp"],
    "tesseract_path": find_tesseract(),  # auto-detect on Windows
    "whisper_model": "base",     # "tiny", "base", "small", "medium", "large"
    "transcribe_folders": [
        "Letters", "Journals", "Cards",
        "Documents/Writings", "Documents/Church",
        "FamilyMembers", "NeedsReview"
    ],
    "skip_existing_transcripts": True,
    "custom_categories": {},     # filename pattern -> (category, subfolder) overrides
    "db_path": None,             # optional: path to .archive.db (default: dest_root/.archive.db)
    "requests_per_minute": 400,  # API rate limit (Gemini paid tier allows 2000)
    "parallel_workers": 10,      # concurrent PDFs in --fast mode
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
