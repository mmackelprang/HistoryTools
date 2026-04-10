# HistoryTools — Product Vision and Roadmap

## Vision

A CLI-first toolkit for digitizing, organizing, transcribing, and searching family archives — scanned documents, photos, audio recordings, video, email, and more. Everything is doable from the CLI, with all configuration driven by JSON files. The architecture cleanly separates the core library from the CLI interface, enabling a web UI to be layered on top without duplicating logic.

The target user is someone with a box (or hard drive) of scanned family documents, old photos, cassette tape recordings, and home videos who wants to turn that pile into a searchable, organized, transcribed digital archive.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Web UI (Phase 3)              │
│         FastAPI + htmx, served locally          │
├─────────────────────────────────────────────────┤
│                CLI (Phase 1-2)                  │
│         family-archive <command> [args]          │
├─────────────────────────────────────────────────┤
│              Core Library (Phase 2)             │
│   organize | transcribe | format | rename |     │
│   import | photos | report | config             │
├─────────────────────────────────────────────────┤
│              Config Layer                       │
│   config.json + .env + taxonomy.json            │
├─────────────────────────────────────────────────┤
│              Filesystem                         │
│   Source files → Organized archive              │
│   .transcript.md | _proposals.json | _log.json  │
└─────────────────────────────────────────────────┘
```

**Key principle:** The core library does all the work. The CLI and web UI are thin wrappers that call library functions and display results. No business logic lives in the CLI or web UI layers.

## Configuration System

All configuration lives in JSON files at the toolkit root. Both CLI and web UI read/write the same files.

### config.json — Main configuration

```json
{
  "source_root": "/path/to/source/files",
  "dest_root": "/path/to/Organized",
  "mode": "standalone",
  "exclude_dirs": [".organizer", ".trashbox", "Organized"],
  "exclude_exts": [".ini", ".lnk", ".db", ".tmp"],
  "transcription": {
    "pdf_engine": "gemini",
    "pdf_model": "gemini-2.5-flash",
    "audio_engine": "assemblyai",
    "format_engine": "anthropic",
    "format_model": "claude-haiku-4-5-20251001",
    "skip_existing": true,
    "parallel_workers": 10,
    "requests_per_minute": 200
  },
  "rename": {
    "auto_detect_dates": true,
    "move_from_undated": true
  }
}
```

### taxonomy.json — Folder structure and classification rules

This is the key file that makes the toolkit generic. It defines the folder hierarchy, naming
conventions per folder, and classification rules for routing files.

**Design principles for the taxonomy:**

1. **Organized by content type, not person** — A letter goes in Letters/, a photo goes in Photos/,
   regardless of who it's from. People are tracked via metadata (SQLite, frontmatter), not folders.
   This avoids the "does a child's report card go in FamilyMembers/child/ or Documents/Education?"
   problem.

2. **Physical and digital sources are peers** — Scanned letters and email threads are both
   correspondence. Cassette tapes and voicemail are both audio. The taxonomy treats them equally,
   with `source_type` metadata distinguishing origin.

3. **Extensible without restructuring** — New data types (SMS, social media, location history) get
   their own top-level folders. Existing folders never need to be reorganized when new types are added.

4. **Imports are separate from organized content** — Raw data dumps (Google Takeout, SMS exports,
   email archives) go in `_imports/` and are processed into the main taxonomy. This keeps messy
   source data separate from curated content.

5. **Year subfolders are optional per category** — Letters and Journals benefit from year folders.
   Recipes and Documents/Legal do not. The taxonomy controls this per folder.

```json
{
  "version": 2,
  "folders": {

    "_imports": {
      "description": "Raw data imports before processing (Google Takeout, email archives, SMS exports, etc.)",
      "system": true,
      "subfolders": {
        "GoogleTakeout": { "description": "Google Maps Timeline, Photos, etc." },
        "EmailArchives": { "description": "Raw .mbox, .pst, .eml files" },
        "SMSExports": { "description": "SMS/text message export files" },
        "SocialMedia": { "description": "Facebook, Instagram exports" }
      }
    },

    "Correspondence": {
      "description": "All personal correspondence — letters, cards, email, SMS",
      "subfolders": {
        "Letters": {
          "description": "Physical letters and postcards",
          "by_year": true,
          "has_undated": true,
          "naming": {
            "pattern": "{type}-{sender}-{recipient}",
            "examples": ["letter-alice-bob", "postcard-bob-alice"]
          },
          "classify_patterns": ["letter", "postcard", "correspondence"]
        },
        "Cards": {
          "description": "Greeting cards",
          "by_year": true,
          "has_undated": true,
          "naming": {
            "pattern": "{type}-{occasion}-{sender}-{recipient}",
            "examples": ["card-birthday-alice-bob", "card-valentines-bob-alice"]
          },
          "classify_patterns": ["card", "birthday", "valentine", "christmas card"]
        },
        "Email": {
          "description": "Preserved email correspondence (imported from archives)",
          "by_year": true,
          "classify_patterns": ["email"],
          "phase": 5
        },
        "SMS": {
          "description": "Text message conversations",
          "by_contact": true,
          "classify_patterns": ["sms", "text message"],
          "phase": 5
        }
      }
    },

    "Journals": {
      "description": "Diaries, journals, and personal reflections",
      "by_year": true,
      "has_undated": true,
      "naming": {
        "pattern": "{type}-{person}-{topic}",
        "examples": ["journal-alice-travels", "journal-bob-1974"]
      },
      "classify_patterns": ["journal", "diary"]
    },

    "Documents": {
      "description": "Official and personal documents",
      "subfolders": {
        "Church": {
          "description": "Religious records and documents",
          "classify_patterns": ["church", "tithing", "baptism", "ordination", "temple", "missionary", "bishop", "ward", "stake"]
        },
        "Education": {
          "description": "School records, report cards, diplomas, homework",
          "classify_patterns": ["school", "grade", "diploma", "homework", "report card", "graduation", "scholarship"]
        },
        "Legal": {
          "description": "Certificates, deeds, wills, licenses",
          "classify_patterns": ["birth certificate", "death certificate", "marriage", "deed", "will", "guardianship", "license"]
        },
        "Employment": {
          "description": "Work-related documents",
          "classify_patterns": ["resume", "pay stub", "review", "employment", "business card"]
        },
        "Writings": {
          "description": "Essays, stories, poems, creative writing",
          "classify_patterns": ["essay", "story", "poem", "notes", "book report", "paper"]
        },
        "Recipes": {
          "description": "Recipes and cookbooks",
          "classify_patterns": ["recipe", "cookbook"],
          "naming": { "pattern": "recipe-{dish}", "examples": ["recipe-banana-bread"] }
        }
      }
    },

    "Financial": {
      "description": "Financial records",
      "subfolders": {
        "Taxes": { "classify_patterns": ["tax", "1040", "W-2"] },
        "Insurance": { "classify_patterns": ["insurance", "policy", "claim"] },
        "BillsAndReceipts": { "classify_patterns": ["bill", "receipt", "invoice", "statement", "check"] }
      },
      "naming": {
        "pattern": "{type}-{institution}-{topic}",
        "examples": ["statement-merrill-lynch-q1", "receipt-honda-service"]
      }
    },

    "Medical": {
      "description": "Medical and dental records",
      "subfolders": {
        "Dental": { "classify_patterns": ["dental", "dentist"] },
        "Insurance": { "classify_patterns": ["medical insurance", "health insurance"] },
        "Records": { "classify_patterns": ["surgery", "hospital", "prescription", "lab result"] }
      },
      "naming": {
        "pattern": "{type}-{person}-{topic}",
        "examples": ["dental-xray-alice", "prescription-bob-checkup"]
      }
    },

    "Media": {
      "description": "All media — photos, audio, video",
      "subfolders": {
        "Photos": {
          "description": "Photographs from all sources",
          "subfolders": {
            "ScannedPhotos": { "description": "Digitized physical photos" },
            "DigitalPhotos": { "description": "Photos from phones/cameras" },
            "Albums": { "description": "Curated photo albums (user-organized)", "dynamic_subfolders": true }
          },
          "file_extensions": [".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".heic"],
          "phase": 4
        },
        "Audio": {
          "description": "Audio recordings from all sources",
          "subfolders": {
            "CassetteTapes": { "classify_patterns": ["tape", "cassette", "audiotape"] },
            "FamilyRecordings": { "classify_patterns": ["audio", "recording", "podcast"] },
            "Voicemail": { "classify_patterns": ["voicemail", "vm"], "phase": 5 },
            "Songs": { "classify_patterns": ["sings", "song", "music", "performance"] }
          }
        },
        "Video": {
          "description": "Video recordings and home movies",
          "by_year": true,
          "classify_patterns": ["video", "movie", "film"],
          "file_extensions": [".mp4", ".mov", ".avi", ".mkv", ".wmv"],
          "phase": 2
        }
      }
    },

    "Memories": {
      "description": "Written recollections, family stories, memory books, obituaries",
      "classify_patterns": ["memory", "memories", "remembrance", "obituary", "eulogy", "life story"]
    },

    "LocationHistory": {
      "description": "Geographic life data — Google Timeline, travel logs",
      "system": true,
      "phase": 5
    },

    "FamilyTree": {
      "description": "Genealogy data — GEDCOM files, FamilySearch exports",
      "system": true,
      "phase": 7
    },

    "NeedsReview": {
      "description": "Files that could not be automatically classified"
    },

    "Duplicates": {
      "description": "Detected duplicate files",
      "system": true
    }
  },

  "data_sources": {
    "description": "Registry of importable data types and their handlers",
    "sources": {
      "scanned_documents": { "handler": "organize", "phase": 1 },
      "audio_cassettes": { "handler": "transcribe.audio", "phase": 1 },
      "digital_photos": { "handler": "photos.catalog", "phase": 4 },
      "home_video": { "handler": "transcribe.video", "phase": 2 },
      "email_mbox": { "handler": "import.email", "phase": 5 },
      "email_pst": { "handler": "import.email", "phase": 5 },
      "sms_android_xml": { "handler": "import.sms", "phase": 5 },
      "sms_imessage": { "handler": "import.sms", "phase": 5 },
      "google_takeout": { "handler": "import.google", "phase": 5 },
      "facebook_export": { "handler": "import.social", "phase": 5 },
      "gedcom": { "handler": "import.genealogy", "phase": 7 },
      "familysearch": { "handler": "import.familysearch", "phase": 7 }
    }
  }
}
```

**Key changes from v1:**

- **Correspondence** groups Letters, Cards, Email, and SMS together — they're all person-to-person communication, just different media
- **Media** groups Photos, Audio, and Video — unified browsing across visual/audio media
- **`_imports/`** holds raw data dumps before processing — keeps messy source data separate
- **`phase` markers** indicate when each folder/feature becomes active — the toolkit gracefully ignores folders it can't handle yet
- **`data_sources` registry** maps import types to handler modules — makes the CLI extensible via `family-archive import --type email_mbox inbox.mbox`
- **`system: true`** marks folders managed by the toolkit (Duplicates, _imports, LocationHistory) vs user-facing content folders
- **`version: 2`** enables schema migration if taxonomy structure changes in future versions
- **Recipes moved under Documents** — they're documents, not a top-level category
- **FamilyMembers removed** — people are tracked in SQLite metadata, not folder structure. Any document can be linked to any number of people without needing to choose one folder.
```

### .env — API keys (secrets, never committed)

```ini
GEMINI_API_KEY=
ASSEMBLYAI_API_KEY=
ANTHROPIC_API_KEY=
```

## CLI Design

Single entry point: `family-archive <command> [options]`

### Commands

```
# Core workflow (Phase 1)
family-archive init                    # Interactive setup wizard
family-archive organize [--dry-run]    # Classify and copy files
family-archive transcribe [--dry-run]  # Transcribe PDFs and audio
family-archive format [--dry-run]      # Format transcripts with summaries
family-archive rename [--dry-run]      # Propose descriptive filenames
family-archive rename --apply          # Apply approved renames
family-archive split [--dry-run]       # Propose splitting compilation PDFs
family-archive split --apply           # Apply approved splits
family-archive speakers               # Manage speaker labels in audio
family-archive report                  # Generate archive summary
family-archive verify                  # Check tool dependencies
family-archive config                  # View/edit configuration
family-archive config set key value    # Set a config value
family-archive status                  # Show pipeline progress

# Search and index (Phase 2)
family-archive search "query"          # Full-text search across all transcripts
family-archive reindex                 # Rebuild SQLite index from filesystem

# Import data sources (Phase 2+)
family-archive import --type video /path/to/movies/       # Import and transcribe video
family-archive import --type email /path/to/archive.mbox  # Import email archive
family-archive import --type sms /path/to/sms-backup.xml  # Import SMS messages
family-archive import --type google-takeout /path/to/     # Import Google Takeout data
family-archive import --type gedcom /path/to/family.ged   # Import family tree (Phase 7)
family-archive import --list                               # Show available import types

# Photos (Phase 4)
family-archive photos catalog          # EXIF extraction, build index
family-archive photos describe         # AI scene descriptions
family-archive photos faces            # Face detection and recognition
family-archive photos tag              # Tag/untag photos

# Web UI (Phase 3)
family-archive serve                   # Start web UI at localhost:8080

# Timeline and connections (Phase 6+)
family-archive timeline                # Generate timeline from all sources
family-archive connections             # Show people/event connections
family-archive narrative               # AI-generated life story chapters (Phase 7)
```

The CLI is designed to grow. The `import` command uses a plugin-style `--type` flag so new
data sources can be added without changing the CLI structure. Each import type maps to a
handler module in the `data_sources` registry in taxonomy.json. Adding a new data type
means: write a handler module, register it in taxonomy.json, done — no CLI changes needed.

Similarly, the taxonomy.json `phase` markers let the toolkit gracefully handle folders it
doesn't support yet. A Phase 1 installation sees `"phase": 5` on the SMS folder and simply
skips it. When the user upgrades to a version that supports Phase 5, the folder activates
automatically.

### Global Options

```
--config PATH      # Path to config.json (default: ./config.json)
--source PATH      # Override source_root
--dest PATH        # Override dest_root
--dry-run          # Preview without changes
--force            # Override skip-existing behavior
--folder NAME      # Limit to specific folder
--file PATH        # Process single file
--verbose          # Detailed output
--quiet            # Minimal output
```

### Init Wizard Flow

```
$ family-archive init

Welcome to the Family Archive Toolkit!
Let's set up your archive.

Where are your source files?
> /path/to/source/files

Where should the organized archive go?
> /path/to/source/files/Organized

I'll scan your source files to suggest categories...
Found: 573 PDFs, 35 audio files, 2824 photos, 0 videos

Suggested folder structure:
  ✓ Letters (detected letter-like filenames)
  ✓ Journals (detected journal entries)
  ✓ Cards (detected greeting cards)
  ✓ Documents (general documents)
  ✓ Photos (2824 image files)
  ✓ AudioRecordings (35 audio files)
  ✗ VideoRecordings (no video files found)
  ✓ FamilyMembers (per-person folders)
  ✗ Recipes (not detected)
  ✗ Email (no email archives found)

Add or remove categories? [Enter to accept]
> +Recipes
> -VideoRecordings

API Keys (optional, for AI-powered features):
  Gemini API key (PDF transcription): [paste key]
  AssemblyAI API key (audio transcription): [paste key]
  Anthropic API key (transcript formatting): [paste key]

Configuration saved to config.json
Taxonomy saved to taxonomy.json

Ready! Run 'family-archive organize --dry-run' to preview.
```

## Core Library Structure

```python
# src/family_archive/__init__.py
from .config import Config, Taxonomy
from .pipeline import Pipeline

# Usage from code:
config = Config.load("config.json")
taxonomy = Taxonomy.load("taxonomy.json")
pipeline = Pipeline(config, taxonomy)

# Run specific steps
pipeline.organize(dry_run=True)
pipeline.transcribe(folder="Journals")
pipeline.format(file="path/to/transcript.md")
pipeline.propose_renames()
pipeline.apply_renames()
```

### Module Responsibilities

```
src/family_archive/
├── __init__.py
├── config.py              # Config + Taxonomy loading/validation/defaults
├── pipeline.py            # Orchestrator — runs steps in order
├── progress.py            # Progress callbacks (CLI prints, web sends WebSocket)
│
├── organize/
│   ├── __init__.py
│   ├── classifier.py      # Route files to folders based on taxonomy rules
│   ├── renamer.py         # Date extraction, slug generation
│   └── dedup.py           # MD5/perceptual hash duplicate detection
│
├── transcribe/
│   ├── __init__.py
│   ├── base.py            # Abstract transcriber interface
│   ├── pdf_tesseract.py   # Local OCR
│   ├── pdf_gemini.py      # Gemini vision (handwriting)
│   ├── audio_whisper.py   # Local Whisper
│   ├── audio_assemblyai.py # AssemblyAI (speaker diarization)
│   └── video.py           # Extract audio + keyframes, transcribe both
│
├── format/
│   ├── __init__.py
│   ├── formatter.py       # Format transcripts (Anthropic/Gemini/local)
│   ├── chunker.py         # Split large transcripts into chunks
│   └── speakers.py        # Speaker label management
│
├── rename/
│   ├── __init__.py
│   ├── proposer.py        # AI-powered rename proposals
│   ├── applier.py         # Apply approved renames
│   └── date_detector.py   # Detect dates in undated files
│
├── import_/               # Underscore to avoid Python keyword
│   ├── __init__.py
│   ├── email.py           # .eml, .mbox, .pst import
│   ├── sms.py             # SMS export parsing
│   └── voicemail.py       # Voicemail file routing
│
├── photos/
│   ├── __init__.py
│   ├── catalog.py         # EXIF extraction, index generation
│   ├── describe.py        # AI scene descriptions
│   ├── faces.py           # Face detection/recognition
│   └── date_estimate.py   # AI-based date estimation from visual cues
│
├── report/
│   ├── __init__.py
│   └── summary.py         # Archive statistics and summary generation
│
└── web/                   # Phase 3
    ├── __init__.py
    ├── app.py             # FastAPI application
    ├── routes/            # API endpoints
    ├── static/            # CSS, JS (htmx)
    └── templates/         # Jinja2 HTML templates
```

### Progress System

The progress system is the key abstraction that lets both CLI and web UI work:

```python
# progress.py
class ProgressCallback:
    """Abstract progress reporter. CLI and web UI provide implementations."""
    def on_file_start(self, file_path, total_files, current_index): ...
    def on_file_progress(self, file_path, detail): ...  # e.g., "Page 5/89"
    def on_file_done(self, file_path, status, detail): ...
    def on_step_done(self, step_name, results): ...
    def on_error(self, file_path, error): ...

class CLIProgress(ProgressCallback):
    """Prints progress to stdout."""
    def on_file_start(self, file_path, total, idx):
        print(f"[{idx}/{total}] {file_path}")

class WebSocketProgress(ProgressCallback):
    """Sends progress via WebSocket to web UI."""
    def on_file_start(self, file_path, total, idx):
        self.ws.send_json({"type": "progress", "file": str(file_path), "index": idx, "total": total})
```

Every library function accepts an optional `progress` callback:

```python
def transcribe_pdf(pdf_path, config, progress=None):
    if progress:
        progress.on_file_start(pdf_path, ...)
    for page in pages:
        text = gemini_transcribe(page)
        if progress:
            progress.on_file_progress(pdf_path, f"Page {page_num}/{total}")
    if progress:
        progress.on_file_done(pdf_path, "ok", f"{word_count} words")
```

## SQLite Index Layer

SQLite serves as a **cache/index** over the filesystem. The markdown files and JSON configs remain the source of truth. The DB can be deleted and rebuilt at any time via `family-archive reindex`.

### Database location

`Organized/.archive.db` — single file, no server process.

### Schema

```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,         -- relative to dest_root
    filename TEXT NOT NULL,
    folder TEXT NOT NULL,              -- top-level folder (Letters, Journals, etc.)
    subfolder TEXT,                    -- year or subfolder
    file_type TEXT,                    -- pdf, mp3, jpg, etc.
    size_bytes INTEGER,
    date_prefix TEXT,                  -- YYYY-MM-DD or "undated"
    md5_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE transcripts USING fts5(
    file_id,
    summary,
    full_text,
    content='transcripts_data'
);

CREATE TABLE transcripts_data (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    summary TEXT,
    full_text TEXT,
    confidence TEXT,
    method TEXT,                       -- ai-vision, native, ocr, assemblyai, whisper
    word_count INTEGER,
    formatting TEXT,                   -- null or "cleaned"
    transcription_date TEXT
);

CREATE TABLE speakers (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id),
    speaker_label TEXT,               -- A, B, C
    speaker_name TEXT,                -- Alice, Bob, etc.
    utterance_count INTEGER
);

CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    relationship TEXT,                -- e.g., "spouse", "child", "parent"
    notes TEXT
);

CREATE TABLE file_people (
    file_id INTEGER REFERENCES files(id),
    person_id INTEGER REFERENCES people(id),
    role TEXT,                        -- sender, recipient, subject, speaker
    PRIMARY KEY (file_id, person_id, role)
);

CREATE TABLE photos (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    exif_date TEXT,
    camera TEXT,
    description TEXT,                 -- AI-generated scene description
    location TEXT,
    faces_detected INTEGER DEFAULT 0
);

CREATE TABLE tags (
    file_id INTEGER REFERENCES files(id),
    tag TEXT NOT NULL,
    source TEXT,                      -- "auto" or "user"
    PRIMARY KEY (file_id, tag)
);
```

### Key features

- **Full-text search** via FTS5: `family-archive search "keyword"` searches all transcripts instantly
- **Faceted queries**: all letters from a given person, all documents from a given year, all audio with 3+ speakers
- **Rebuild guarantee**: `family-archive reindex` scans the filesystem and rebuilds the entire DB from .transcript.md files and EXIF data. Safe to delete .archive.db at any time.
- **Incremental updates**: when a file is transcribed or renamed, the DB is updated in-place. Full reindex only needed if DB is lost or schema changes.
- **Scales to millions** of files — SQLite handles this easily

### CLI commands

```
family-archive search "query"          # Full-text search across all transcripts
family-archive search --person Alice   # Filter by person
family-archive search --folder Letters # Filter by folder
family-archive search --year 1983      # Filter by year
family-archive search --type audio     # Filter by media type
family-archive reindex                 # Rebuild DB from filesystem
family-archive reindex --check         # Verify DB matches filesystem
family-archive stats                   # Archive statistics from DB
```

## Web UI Design (Phase 3)

### Technology

- **Backend**: FastAPI (Python, async, WebSocket support)
- **Frontend**: htmx + Jinja2 templates (no build step, no npm)
- **SQLite** — index layer for fast queries, rebuilt from filesystem
- **Runs locally** — `family-archive serve` opens http://localhost:8080

### Screens

**1. Dashboard**
- Archive stats (file counts by type, transcription coverage, recent activity)
- Quick actions (run transcription, format, rename)
- Pipeline status (what's running, progress bars)

**2. Setup / Settings**
- Visual taxonomy editor (add/remove/rename folders, drag to reorder)
- API key management (enter keys, test connectivity)
- Transcription settings (engine selection, model, parallelism)
- All settings read/write config.json and taxonomy.json directly

**3. Import**
- Drag-and-drop file upload area
- Auto-classification preview (shows which folder each file would go to)
- Override classification before committing
- Progress feedback as files are copied + transcribed

**4. Browse / Read**
- File tree navigation matching the archive structure
- Transcript viewer with rendered markdown
- Side-by-side view: original PDF/image + transcript
- Audio player with transcript following along

**5. Rename Review**
- Table of proposals with current name, proposed name, reasoning
- Inline edit for proposed names
- Approve/reject checkboxes
- "Apply All Approved" button
- Shows folder moves for undated files with detected dates

**6. Photos** (future)
- Gallery grid view
- AI descriptions shown on hover
- Face tagging interface
- Filter by date, people, location

**7. Timeline** (future)
- Chronological view across all media types
- Zoom from decades to individual days
- Click any item to view its transcript

### API Endpoints

```
GET  /api/status                    # Pipeline status, archive stats
GET  /api/files?folder=Letters      # List files in a folder
GET  /api/transcript/{path}         # Read a transcript
POST /api/transcribe                # Start transcription job
POST /api/format                    # Start formatting job
GET  /api/rename/proposals          # Get current proposals
POST /api/rename/apply              # Apply approved renames
GET  /api/config                    # Read config
PUT  /api/config                    # Update config
GET  /api/taxonomy                  # Read taxonomy
PUT  /api/taxonomy                  # Update taxonomy
WS   /ws/progress                   # WebSocket for live progress
```

## Phasing

### Phase 1: Generalize CLI (ship to GitHub)
- Refactor config to use taxonomy.json for folder structure
- Remove all personal/family-specific references
- Add `family-archive init` wizard
- Add `pyproject.toml`, LICENSE (MIT), generic README
- Publish to GitHub as `family-archive-toolkit`
- Estimated: 2-3 sessions

### Phase 2: Library refactor + SQLite + new media + document splitting
- Extract core library from scripts
- Add progress callback system
- Add SQLite index layer with FTS5 full-text search
- Add `family-archive search` and `reindex` commands
- Add document splitting (see below)
- Add video transcription (ffmpeg + existing audio pipeline)
- Add email import (.eml, .mbox)
- Add photo AI descriptions
- Test suite
- Publish to PyPI
- Estimated: 4-5 sessions

### Phase 3: Web UI
- FastAPI backend with WebSocket progress
- htmx frontend (no build step)
- Dashboard, import, browse, rename review screens
- Settings UI that reads/writes config.json + taxonomy.json
- Document splitter UI with visual page selection
- Estimated: 3-4 sessions

### Phase 4: Advanced features
- Face detection/recognition in photos
- SMS import
- Timeline view
- Search across all transcripts
- AI-powered "ask questions about your archive" (RAG)

## Document Splitting

### Problem

Many family archives contain compilation PDFs — dozens of individual letters, journal entries,
or documents scanned into a single large file. Examples:

- "family-correspondence-vol1.pdf" (139 pages, ~30 individual letters)
- "letters-1983-outbound.pdf" (multiple parts, 50+ pages each)
- "journal-year1.pdf" (89 pages, entries spanning 9 months)

These are hard to search, link to, or browse individually. Splitting them into separate
files makes each letter/entry independently searchable and renameable.

### Approach: AI-Assisted Splitting

The splitting process is a two-phase propose-then-apply workflow (same pattern as renaming):

**Phase 1: `family-archive split --propose`**

1. Read the transcript of the compilation PDF
2. Send to AI with instructions to identify document boundaries:
   - For letters: find salutations ("Dear Alice"), sign-offs ("Love, Bob"), dates, page breaks
   - For journals: find dated entries
   - For mixed documents: identify each distinct document
3. AI returns a split proposal: list of segments with page ranges, dates, and suggested filenames
4. Write `_split-proposals.json` for review

```json
[
  {
    "source_file": "Letters/1984/1984-00-00_family-correspondence-vol1.pdf",
    "segments": [
      {
        "pages": [1, 2, 3],
        "detected_date": "1984-03-15",
        "proposed_name": "1984-03-15_letter-alice-bob-spring-update.pdf",
        "proposed_folder": "Letters/1984/",
        "description": "Family member writes about spring semester and being apart",
        "approved": true
      },
      {
        "pages": [4, 5],
        "detected_date": "1984-04-02",
        "proposed_name": "1984-04-02_letter-bob-alice-travels-update.pdf",
        "proposed_folder": "Letters/1984/",
        "description": "Family member describes travels abroad",
        "approved": true
      }
    ]
  }
]
```

**Phase 2: `family-archive split --apply`**

1. Read the approved proposals
2. For each segment, extract the specified pages from the source PDF using PyMuPDF
3. Save as a new PDF in the proposed location
4. Run transcription on the new individual PDFs
5. Format the new transcripts
6. Optionally keep or archive the original compilation PDF
7. Log all changes to `_split-log.json`

### CLI Interface

```
family-archive split                              # propose splits for all large compilations
family-archive split --file path/to/compilation.pdf  # propose splits for one file
family-archive split --min-pages 20               # only consider files with 20+ pages
family-archive split --apply                      # apply approved splits
family-archive split --dry-run                    # preview without changes
```

### Detection Heuristics

The AI identifies boundaries using:

- **Letter markers**: salutations, dates at top of letters, sign-offs, address blocks
- **Journal entries**: date headers, "Dear Journal" / "Dear Diary" patterns
- **Page content shifts**: abrupt change in handwriting, paper color, orientation
- **Blank separator pages**: pages that are blank or near-blank between documents
- **Transcript structure**: the existing transcript with page markers helps the AI locate boundaries

### Web UI (Phase 3)

The split review screen would show:
- Thumbnail grid of all pages in the compilation
- AI-proposed segment boundaries highlighted with color coding
- Drag handles to adjust boundaries
- Per-segment preview with proposed name and date
- Approve/edit/merge/split individual segments

### Safety

- Original compilation PDF is never modified or deleted
- Split files are copies (new PDFs extracted from the original)
- Proposals reviewed before applying (same as rename workflow)
- Log tracks every split operation for auditability
- Original can be archived to a `_compilations/` folder after splitting

## Long-Term Vision: A Connected Life History

The near-term goal is organizing and transcribing a family archive. The long-term vision
is much larger: **a tool that weaves together every type of personal and family data into
a rich, interconnected life history with timelines, maps, relationships, and narrative.**

### Data Sources (expanding over time)

| Source | Data Type | What It Provides |
|--------|-----------|-----------------|
| Scanned documents | PDFs, images | Letters, journals, cards, certificates, records |
| Audio recordings | MP3, WAV, M4A | Cassette tapes, family recordings, voicemail, podcasts |
| Video recordings | MP4, MOV, AVI | Home movies, VHS digitizations, phone videos |
| Photos | JPG, PNG, TIFF | Timestamp, location (GPS), faces, scene descriptions |
| Email archives | .eml, .mbox, .pst | Correspondence with dates, people, threads, attachments |
| SMS/text messages | XML, CSV, JSON exports | Conversations with timestamps, phone numbers → contacts |
| Google Maps Timeline | Google Takeout JSON | Location history — where someone was on any given day |
| Social media exports | Facebook, Instagram | Posts, messages, photos with timestamps and people |
| Calendar data | .ics, Google Calendar | Events, appointments, milestones |
| Genealogy data | GEDCOM files | Family tree structure, birth/death/marriage dates |
| Medical records | PDFs, portal exports | Health timeline |
| Financial records | Statements, tax returns | Life milestones (home purchases, career changes) |

### The Correlation Engine

The real power comes from **correlating across data sources by date, person, and location.**

Examples of what this enables:

- **"What was happening on a given date?"**
  → A family member wrote a letter while traveling abroad. A spouse's journal mentions missing them.
  Google Timeline shows their location. A photo from that week captures daily life.

- **"Show me everything about a major life event"**
  → Journal entries about the decision. Letters to family announcing it. Google Timeline
  showing the journey. Photos of the new place. SMS messages about settling in. Email
  threads about the new opportunity.

- **"What was a family member's final year like?"**
  → Medical records timeline. Journal entries. Family recordings. Cards from friends.
  Photos. Text messages. A complete picture assembled from every data source.

### The Timeline / Life History UI

The web UI evolves from a simple file browser into a **life history application**:

**Timeline View**
- Horizontal timeline spanning decades, zoomable to individual days
- Events from ALL data sources rendered as dots/cards on the timeline
- Color-coded by type (blue=letters, green=audio, yellow=photos, etc.)
- Click any event to read/view/listen
- Filter by person, type, location, keyword

**Map View**
- Geographic visualization of life events using Google Maps Timeline data
- Photo locations plotted on map
- Letter origins/destinations (if addresses are extracted)
- Migration patterns and life moves visible at a glance

**People Graph**
- Visual family tree / relationship web
- For any person, show all documents mentioning them
- Show connections: "Two family members appear together in hundreds of documents"
- Face recognition links photos to people automatically

**Narrative Generation**
- AI-generated life story chapters from correlated data
- Example: "Family Member's Years Abroad (decade)" — assembled from letters, journal entries, audio tapes, photos
- User can edit/curate the AI-generated narrative
- Export as a book/PDF for printing or sharing with family

### The Hyper-Personal-Web

The deepest architectural concept is the **hyper-personal-web** — the inverse of the
world-wide-web. Where the WWW links between websites, the hyper-personal-web links
between moments in a family's history across every type of artifact.

Every artifact is a node. Every mention of a person, place, time, or event creates a
**deep link** — not just "this file mentions Alice" but "Alice is mentioned at page 3,
paragraph 2 of this letter" or "Alice speaks at timestamp 4:32 in this recording" or
"Alice appears in the upper-left quadrant of this photo."

**Core dimensions:** People, Places, Times, Events. These are the axes of the mesh.
Any artifact can connect to multiple entities on each dimension simultaneously. A single
letter might reference 5 people, 3 places, and 2 events.

**Traversal is bidirectional:** From a person → find all artifacts. From a place → find
everyone who was there. From an event → find all related artifacts across every media type.
From a moment in an audio recording → find the letter being discussed.

**The system is extensible:** People, places, times, and events are the initial dimensions,
but the architecture supports adding new dimensions (organizations, objects, themes,
emotions) without schema changes — just new entity types and reference types.

### Data Model: Entities, References, and Anchors

The data model has three layers:

1. **Entities** — the things being connected (people, places, events, etc.)
2. **References** — connections between artifacts and entities
3. **Anchors** — precise locations within artifacts where references occur

```sql
-- ── Artifacts (files in the archive) ───────────────────────────────────────

CREATE TABLE artifacts (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id),
    artifact_type TEXT,                 -- letter, journal_entry, photo, audio_segment, etc.
    event_date DATE,
    event_date_end DATE,                -- for ranges (journal spanning months)
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    summary TEXT,
    UNIQUE(file_id, artifact_type, event_date)
);

-- ── Entities (the nodes in the mesh) ───────────────────────────────────────

CREATE TABLE entities (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,          -- person, place, event, organization, theme, ...
    name TEXT NOT NULL,
    description TEXT,
    metadata JSON,                      -- flexible key-value for type-specific data
    UNIQUE(entity_type, name)
);

-- Person-specific data (extends entities where entity_type='person')
CREATE TABLE people (
    entity_id INTEGER PRIMARY KEY REFERENCES entities(id),
    birth_date DATE,
    death_date DATE,
    familysearch_id TEXT               -- for Phase 7 FamilySearch integration
);

-- Place-specific data
CREATE TABLE places (
    entity_id INTEGER PRIMARY KEY REFERENCES entities(id),
    latitude REAL,
    longitude REAL,
    address TEXT
);

-- Relationships between entities (person↔person, person↔organization, etc.)
CREATE TABLE entity_relationships (
    entity_a INTEGER REFERENCES entities(id),
    entity_b INTEGER REFERENCES entities(id),
    relationship TEXT,                  -- spouse, parent, child, sibling, member_of, ...
    start_date DATE,
    end_date DATE,
    PRIMARY KEY (entity_a, entity_b, relationship)
);

-- ── References (connections between artifacts and entities) ─────────────────

CREATE TABLE references (
    id INTEGER PRIMARY KEY,
    artifact_id INTEGER REFERENCES artifacts(id),
    entity_id INTEGER REFERENCES entities(id),
    ref_type TEXT,                      -- author, recipient, subject, speaker, location,
                                       -- mentioned, photographed, present, ...
    confidence REAL DEFAULT 1.0,        -- 0.0-1.0, for AI-detected references
    source TEXT,                        -- manual, ai_transcript, ai_vision, exif, ...
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Anchors (precise locations within artifacts) ───────────────────────────
-- These are the "hyperlinks" of the personal web — they point to specific
-- moments/locations within source material.

CREATE TABLE anchors (
    id INTEGER PRIMARY KEY,
    reference_id INTEGER REFERENCES references(id),
    anchor_type TEXT NOT NULL,          -- page, timestamp, coordinates, paragraph, line
    -- Page-based (PDFs, documents)
    page_number INTEGER,
    paragraph_offset INTEGER,
    -- Time-based (audio, video)
    start_time_ms INTEGER,
    end_time_ms INTEGER,
    -- Spatial (photos, scanned documents)
    x_pct REAL,                         -- 0.0-1.0 percentage coordinates
    y_pct REAL,
    width_pct REAL,
    height_pct REAL,
    -- Text-based (transcripts)
    text_offset INTEGER,                -- character offset into transcript
    text_length INTEGER,
    snippet TEXT                         -- short excerpt for preview
);

-- ── Location history (continuous timeline) ─────────────────────────────────

CREATE TABLE location_history (
    id INTEGER PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id),  -- which person
    timestamp DATETIME,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    source TEXT                          -- google_timeline, photo_exif, manual
);
```

**How the mesh works in practice:**

A letter from Alice to Bob, written on March 15, 1984, mentioning a trip to Springfield:

```
artifact: letter (file_id=42, date=1984-03-15)
  ├─ reference → entity:Alice (ref_type=author)
  │   └─ anchor: page 1, paragraph 1 (return address)
  ├─ reference → entity:Bob (ref_type=recipient)
  │   └─ anchor: page 1, paragraph 1 (greeting "Dear Bob")
  ├─ reference → entity:Springfield (ref_type=location_mentioned)
  │   └─ anchor: page 2, paragraph 3 ("we drove to Springfield last week")
  └─ reference → entity:ChristmasVisit1983 (ref_type=event_mentioned)
      └─ anchor: page 2, paragraph 5 ("remember when we all got together")
```

An audio recording where Alice talks about the same trip at timestamp 4:32:

```
artifact: audio_segment (file_id=87, date=1984-06-14)
  ├─ reference → entity:Alice (ref_type=speaker)
  │   └─ anchor: timestamp 0:00 - 60:12
  ├─ reference → entity:Springfield (ref_type=location_mentioned)
  │   └─ anchor: timestamp 4:32 - 4:58 ("...when we went to Springfield...")
  └─ reference → entity:ChristmasVisit1983 (ref_type=event_mentioned)
      └─ anchor: timestamp 4:32 - 5:15
```

**Querying the mesh:**

```sql
-- "Show me everything about Springfield"
SELECT a.*, ref.ref_type, anch.snippet
FROM artifacts a
JOIN references ref ON ref.artifact_id = a.id
JOIN entities e ON ref.entity_id = e.id
LEFT JOIN anchors anch ON anch.reference_id = ref.id
WHERE e.name = 'Springfield' AND e.entity_type = 'place';

-- "What was Alice doing in March 1984?"
SELECT a.*, ref.ref_type, anch.snippet
FROM artifacts a
JOIN references ref ON ref.artifact_id = a.id
JOIN entities e ON ref.entity_id = e.id
LEFT JOIN anchors anch ON anch.reference_id = ref.id
WHERE e.name = 'Alice' AND a.event_date BETWEEN '1984-03-01' AND '1984-03-31';

-- "Find the audio moment where Alice talks about what Bob wrote in this letter"
-- (cross-artifact linking via shared entity references)
SELECT a2.*, anch2.start_time_ms, anch2.snippet
FROM references ref1
JOIN references ref2 ON ref1.entity_id = ref2.entity_id  -- same entity
JOIN artifacts a2 ON ref2.artifact_id = a2.id
JOIN anchors anch2 ON anch2.reference_id = ref2.id
WHERE ref1.artifact_id = 42  -- the letter
  AND a2.artifact_type = 'audio_segment'
  AND anch2.anchor_type = 'timestamp';
```

### HistoryTools Cloud — Managed AI Gateway

The open-source toolkit is fully functional with self-managed API keys. For users who
want a simpler experience, **HistoryTools Cloud** is a planned managed AI gateway that
provides a single API key for all AI features.

**How it works:**

```
User's machine                        HistoryTools Cloud
+------------------+                  +---------------------+
| HistoryTools CLI |  -- HTTPS -->    | AI Gateway          |
|                  |                  |                     |
| HISTORYTOOLS_    |                  | Smart routing:      |
|   API_KEY=ht_... |                  | - Cheapest model    |
+------------------+                  | - Auto-failover     |
                                      | - Rate balancing    |
                                      | - Usage metering    |
                                      |                     |
                                      | Backends:           |
                                      | +- Gemini           |
                                      | +- OpenAI           |
                                      | +- Anthropic        |
                                      | +- (future vendors) |
                                      +---------------------+
```

**Benefits for users:**
- One API key instead of three (or four)
- No need to manage billing across multiple AI providers
- Automatic failover (if Gemini is down, requests route to OpenAI)
- Smart model selection (cheapest available model for each task type)
- Usage dashboard and spending controls

**Business model (open core):**
- The CLI toolkit (this repo) remains free and open-source through Phase 2
- HistoryTools Cloud (private repo) includes the managed AI gateway, web UI, and all Phase 3+ features
- Users choose: CLI with self-managed keys (free) or subscription for the full experience
- Data is fully portable — no lock-in, archives work with both CLI and subscription

**Implementation:**
- A `cloud` vendor in `ai_client.py` routes requests to the gateway via simple REST API
- The gateway manages backend API keys centrally (users never see them)
- The gateway selects the cheapest available backend per request type
- Usage is metered per user for subscription billing

**Planned pricing tiers:**

| Tier | Price | Requests/month | Best for |
|------|-------|---------------|----------|
| Free | $0 | Local tools only | Users who manage their own API keys |
| Starter | ~$5/mo | ~500 | Small archives, getting started |
| Standard | ~$15/mo | ~5,000 | Most family archives |
| Unlimited | ~$30/mo | Unlimited | Power users, large archives |

### Entity Extraction Pipeline

A critical pipeline component for building the hyper-personal-web: automatically
extracting structured entities (people, places, dates, events) from transcripts and
linking them back to specific locations in the source material.

**How it works:**

1. Read a formatted transcript
2. Send to AI with entity extraction prompt
3. AI returns structured JSON with entities and their locations (anchors)
4. Store in SQLite (entities, references, anchors tables)

**Example output for a letter:**

```json
{
  "entities": [
    {"type": "person", "name": "Alice", "role": "author", "anchor": {"page": 1, "paragraph": 1}},
    {"type": "person", "name": "Bob", "role": "recipient", "anchor": {"page": 1, "paragraph": 1}},
    {"type": "place", "name": "Springfield", "anchor": {"page": 2, "paragraph": 3, "snippet": "we drove to Springfield"}},
    {"type": "event", "name": "Christmas gathering", "date": "1983-12-25", "anchor": {"page": 2, "paragraph": 5}}
  ]
}
```

**CLI:**

```
family-archive extract-entities                    # all transcripts
family-archive extract-entities --folder Letters   # one folder
family-archive extract-entities --file path.md     # single file
```

This feeds directly into the SQLite correlation engine and enables the timeline,
map, and people graph views.

### Phasing for the Vision

The project follows an **open core** model. The open-source CLI toolkit (this repo)
handles the core archival workflow. Premium features — the web UI, advanced
visualizations, managed AI, and collaboration tools — are part of the subscription
service (private repo). Selected features from the subscription side may be
incorporated back into the open-source CLI over time.

#### Open Source (this repo) — Free, CLI-focused

- **Phase 1** (current): Core archive toolkit — organize, transcribe, format, rename, bootstrap
- **Phase 2**: Library refactor, SQLite index with full-text search, entity extraction (people/places/events from transcripts), document splitting, video transcription, email import. Cloud gateway stub.

Phase 2 completes the open-source foundation. The CLI will be a fully capable
archival tool with local search, entity extraction, and support for all major
media types. Power users and developers can do everything from the command line.

#### Subscription Service (private repo) — Paid, UI-focused

- **Phase 3**: Web UI for browsing, searching, and managing the archive. HistoryTools Cloud AI gateway launch.
- **Phase 4**: Photo AI (scene descriptions, face recognition, date estimation)
- **Phase 5**: Data import hub — Google Timeline, SMS, social media, calendar. Correlation engine connecting people/places/events across all media.
- **Phase 6**: Timeline view, interactive map, people graph — the life history visualization
- **Phase 7**: AI narrative generation — auto-assembled life story chapters. FamilySearch integration (import family trees, link archive items to FamilySearch person records, contribute photos/stories back to FamilySearch Memories)
- **Phase 8**: Multi-family support, sharing, collaboration — families connecting their archives. Deeper FamilySearch integration with bidirectional sync.

The subscription service builds on the open-source core library. The same
`ai_client.py`, taxonomy system, and file format conventions are shared between
both. Data is always portable — archives created with the subscription service
can be managed with the CLI and vice versa.

#### What stays open vs. what's subscription

| Feature | Open Source (CLI) | Subscription (Web UI) |
|---------|------------------|-----------------------|
| File organization | Yes | Yes |
| Transcription (local + AI) | Yes (self-managed keys) | Yes (managed, one key) |
| Formatting and renaming | Yes | Yes |
| Entity extraction | Yes (CLI) | Yes (visual UI) |
| Full-text search | Yes (CLI) | Yes (search bar) |
| Document splitting | Yes (CLI) | Yes (visual page selector) |
| Photo AI descriptions | Selected features | Full gallery + face tagging |
| Timeline / map / people graph | No | Yes |
| Narrative generation | No | Yes |
| FamilySearch integration | No | Yes |
| Multi-family collaboration | No | Yes |
| Managed AI gateway | No (self-managed keys) | Yes (one key, auto-routing) |

The architecture decisions made now (filesystem as truth, SQLite as index, pluggable data
sources, event-based correlation model, unified AI client) are designed to support both
the open-source CLI and the subscription service without requiring separate codebases.

## Design Principles

1. **CLI-first** — everything in the open-source repo works from the terminal. The web UI (subscription) is a convenience layer, never a requirement.
2. **Config-driven** — all behavior controlled by JSON files. No hardcoded paths, folder names, or taxonomies.
3. **Restartable** — every operation saves progress incrementally. Interruptions lose at most one file's work.
4. **Source files are sacred** — never modified or deleted. All work produces copies.
5. **AI-optional** — local tools (Tesseract, Whisper) work without API keys. AI features are upgrades, not requirements.
6. **Filesystem is truth, SQLite is speed** — Transcripts are markdown files. Proposals are JSON. The SQLite index is a rebuildable cache for search and fast queries. Delete the .db file and lose nothing.
7. **Pluggable engines** — transcription, formatting, and rename proposal all support multiple backends. Config selects which to use.
8. **Data portability** — archives are fully portable between CLI and subscription service. No vendor lock-in. Your data is always yours.
9. **Forward compatible** — the taxonomy, config, and CLI are designed to grow without breaking changes:
   - taxonomy.json has `version` and `phase` markers so new data types activate gracefully on upgrade
   - The `import --type` CLI pattern is extensible without changing the CLI itself
   - SQLite schema uses a generic `events` table that accommodates any data source
   - Markdown transcripts work for any content type (documents, audio, video, email, SMS)
   - The correlation engine (dates + people + locations) is data-source agnostic
   - New phases add capabilities; they never require reorganizing existing archives
