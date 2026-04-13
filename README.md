# HistoryTools

A CLI toolkit for digitizing, organizing, transcribing, and searching family archives — scanned documents, photos, audio recordings, and more. Turn a box of old scans, cassette tapes, and photos into a searchable, organized, transcribed digital archive.

## Installation

```bash
git clone https://github.com/mmackelprang/HistoryTools.git
cd HistoryTools
pip install -e ".[all]"
```

After installation, the `family-archive` command is available:

```bash
family-archive --help
```

### System tools (also needed)

- **Tesseract OCR**: https://github.com/tesseract-ocr/tesseract
- **FFmpeg**: https://ffmpeg.org/download.html

## Quick Start

```bash
# 1. Run the setup wizard (creates config, sets up API keys)
family-archive init

# 2. Process your archive
family-archive ingest /path/to/your/scans
```

That's it. The init wizard walks you through configuration interactively.
For manual setup, see [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Commands

### Ingest — Process Everything at Once

The fastest way to process a folder of scans, recordings, and photos:

```bash
# Scan and classify all files, produce a plan for review
family-archive ingest /path/to/scans --scan

# Review _ingest-plan.json (edit classifications if needed)

# Execute the full pipeline (copy, transcribe, format, rename)
family-archive ingest --execute

# Or do it interactively (scan → approve → execute)
family-archive ingest /path/to/scans

# Merge new files into an existing archive
family-archive ingest /path/to/new-scans --scan --mode merge

# Source can be a ZIP file (nested ZIPs are handled too)
family-archive ingest /path/to/archive.zip --scan
```

Ingest is fully restartable — if interrupted, run `--execute` again.

### Individual Steps

You can also run each step individually for more control:

```bash
# Organize files into the archive structure
family-archive organize --dry-run        # preview
family-archive organize                  # run

# Transcribe PDFs — tiered approach (free first, AI only when needed)
python -m familyarchive.transcribe_pdfs   # free: native text + Tesseract OCR
family-archive transcribe --low-confidence-only   # paid: AI only for low-confidence results
family-archive transcribe                # paid: AI for all untranscribed PDFs

# Transcribe audio (AssemblyAI — with speaker diarization)
family-archive transcribe-audio --dry-run
family-archive transcribe-audio

# Assign real names to speaker labels (e.g., Speaker A → Alice)
family-archive speakers path/to/transcript.md              # interactive
family-archive speakers --dir AudioRecordings --map "A=Alice,B=Bob"  # batch

# Format transcripts with summaries and markdown structure
family-archive format --dry-run
family-archive format                    # free mechanical cleanup
family-archive format --with-summary     # + AI summary (requires API key)

# Propose descriptive filenames for generic files
family-archive rename --dry-run          # preview
family-archive rename                    # generate proposals
# Review _rename-proposals.md, then:
family-archive rename --apply            # apply approved renames

# Detect dates in undated files
family-archive detect-dates              # generate proposals
family-archive detect-dates --apply      # apply approved dates

# Split compilation PDFs into individual documents
family-archive split --dry-run           # preview splittable files
family-archive split                     # generate split proposals
# Review _split-proposals.md, then:
family-archive split --apply --dry-run   # preview
family-archive split --apply             # apply approved splits
family-archive split --apply --archive-original  # move originals to _compilations/

# Extract text from Office documents (DOC, DOCX, XLS, XLSX)
family-archive extract --dry-run          # preview
family-archive extract                    # extract all
family-archive extract --folder NeedsReview  # one folder

# Catalog photos, detect duplicates, generate report
family-archive photos
# Detect and manage duplicate files
family-archive duplicates --scan           # detect duplicates
family-archive duplicates --apply          # quarantine approved
family-archive duplicates --status         # check quarantine
family-archive duplicates --purge          # delete past TTL
family-archive report

# Build the search index (rebuilds from filesystem)
family-archive reindex
family-archive reindex --check    # verify index matches filesystem

# Search across all transcripts
family-archive search "Springfield"
family-archive search "Springfield" --folder Letters
family-archive search "Springfield" --type audio --year 1984

# Archive statistics
family-archive stats

# Review AI API costs
family-archive costs              # summary by pipeline step
family-archive costs --detail     # per-session breakdown

# Check tool installation
family-archive verify
```

### Targeting Specific Files or Folders

Most commands support `--folder` and `--file` for targeted processing:

```bash
family-archive transcribe --folder Journals
family-archive format --file Letters/1983/letter.transcript.md
family-archive rename --folder FamilyMembers
```

## Transcription Strategy

PDF transcription uses a **tiered approach** to minimize AI costs:

1. **Native text extraction** (free, instant) — PDFs with embedded text are extracted using PyMuPDF
2. **Tesseract OCR** (free, slower) — Scanned/image PDFs are OCR'd locally
3. **Gemini AI vision** (paid, best quality) — Only used for files where steps 1-2 produced low-confidence results (typically handwritten documents)

The ingest pipeline runs all three tiers automatically. When running manually:

```bash
python -m familyarchive.transcribe_pdfs               # free: tiers 1 + 2
family-archive transcribe --low-confidence-only       # paid: tier 3 for low-confidence only
```

```bash
# Batch mode (default — 50% cheaper, processes overnight)
family-archive transcribe                  # submit batch jobs
family-archive transcribe --status         # check batch progress
family-archive transcribe --collect        # retrieve results

# Real-time mode (immediate results)
family-archive transcribe --fast           # cross-PDF parallelism
```

## AI-Powered Features

These features require API keys (see [docs/SETUP-API-KEYS.md](docs/SETUP-API-KEYS.md)):

| Command | Default Service | Alternatives | What It Does | Estimated Cost |
|---------|----------------|-------------|-------------|---------------|
| `family-archive transcribe` | Google Gemini | OpenAI GPT-4o | AI vision (batch default, 50% cheaper) | ~$0.25-0.50 per 1000 pages |
| `family-archive transcribe --low-confidence-only` | Google Gemini | OpenAI GPT-4o | AI only for low-confidence files | Much less (only handwriting) |
| `family-archive transcribe-audio` | AssemblyAI | -- | Speaker-diarized audio transcription | ~$0.01/minute |
| `family-archive format` | — (mechanical) | — | Page breaks, whitespace cleanup, artifact removal | **Free** |
| `family-archive format --with-summary` | Any AI vendor | — | + AI-generated summary at top | ~$0.10-0.20 per 500 files |
| `family-archive rename` | Google Gemini | OpenAI GPT-4o | AI-suggested filenames | ~$0.10-0.30 per 500 files |
| `family-archive detect-dates` | Google Gemini | OpenAI GPT-4o | Date detection in undated files | ~$0.05-0.10 per 200 files |
| `family-archive split` | Google Gemini | OpenAI GPT-4o | Document boundary detection | ~$0.01-0.05 per file |

All AI features are optional. Without API keys, local tools (Tesseract OCR, Whisper) are used instead.
A unified AI client (`ai_client.py`) supports Gemini, OpenAI, and Anthropic — vendor swapping
via a `--vendor` CLI flag is planned for an upcoming release.

AI costs are tracked automatically. Run `family-archive costs` to see token usage and
estimated spend across all sessions. Costs are estimates based on published per-token
pricing — compare against your vendor dashboards for exact billing.

## Modes

### Standalone (`"mode": "standalone"`)
Creates a fresh organized archive from scratch.

### Merge (`"mode": "merge"`)
Adds new files into an existing organized archive. Detects duplicates by MD5 hash.

## Configuration

### config.json — Paths and settings

```json
{
  "source_root": "/path/to/source/files",
  "dest_root": "/path/to/Organized",
  "mode": "standalone",
  "whisper_model": "base",
  "transcribe_folders": ["Letters", "Journals", "Cards", "Documents/Writings"]
}
```

### taxonomy.json — File classification rules

Controls how files are classified, which keywords trigger which folders, and which processing steps apply to each file type. Ships with sensible defaults, fully customizable.

```bash
# Add a new file extension (e.g., .webp as a photo type)
# Edit taxonomy.json → file_types → photo → extensions

# Add a new classification folder (e.g., Military records)
# Edit taxonomy.json → folders → add "Military/Service" with keywords

# Customize processing pipelines
# Edit taxonomy.json → processing_pipelines
```

See `taxonomy.example.json` for a fully commented reference. If `taxonomy.json` is missing, built-in defaults are used automatically.

### .env — API keys

```bash
cp .env.example .env
# Edit with your keys (see docs/SETUP-API-KEYS.md)
```

## File Naming Convention

All files are renamed to: `YYYY-MM-DD_descriptive-slug.ext`

- Dates sourced from: filename > EXIF > content analysis
- Unknown dates: `undated_slug.ext`
- Partial dates: `1983-06-00_slug.ext` (month known, day unknown)

## Safety

- **Source files are never modified or deleted** — all operations produce copies
- **Duplicates are moved, never deleted** — review at your leisure
- **Unclassifiable files go to NeedsReview** — nothing is silently discarded
- **All operations support `--dry-run`** — preview before committing
- **All operations are restartable** — interrupted jobs resume where they left off
- **Proposals require review** — renames, date changes, and splits are proposed then applied

## Dependencies

Installed automatically via `pip install -e ".[all]"`:

| Package | Purpose |
|---------|---------|
| PyMuPDF | PDF text extraction & page rendering |
| Pillow | Image processing |
| python-dotenv | Load API keys from .env |
| google-genai | Gemini AI for handwriting OCR |
| openai | OpenAI API (alternative to Gemini/Claude) |
| assemblyai | Audio transcription with speaker ID |
| anthropic | Transcript formatting with Claude |
| openai-whisper | Local audio transcription |
| exifread | EXIF metadata from photos |
| imagehash | Perceptual duplicate detection |
| python-docx | DOCX text extraction |
| openpyxl | XLSX spreadsheet extraction |
| xlrd | XLS (legacy) spreadsheet extraction |
| olefile | DOC (legacy Word) extraction |

System tools (install separately): [Tesseract OCR](https://github.com/tesseract-ocr/tesseract), [FFmpeg](https://ffmpeg.org/download.html)

## Documentation

| File | Contents |
|------|----------|
| [docs/SETUP-API-KEYS.md](docs/SETUP-API-KEYS.md) | API keys, costs, recommended models, vendor options |
| [docs/SYSTEM-REQUIREMENTS.md](docs/SYSTEM-REQUIREMENTS.md) | OS, Python, disk space, RAM, system tools |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Step-by-step processing guide |
| [docs/VISION.md](docs/VISION.md) | Long-term product vision and roadmap |

## Roadmap

**Open source (this repo):**
- **Phase 1** ✅: CLI toolkit for documents, audio, and basic organization
- **Phase 2** ✅: Core library, SQLite/FTS5 search, document splitting, duplicate detection, Gemini batch processing, Office document extraction
- **Phase 3**: Web UI, video transcription, email import, photo AI, embedding-based search

**Subscription service ([historytools.io](https://historytools.io)):**
- **Phase 3+**: Web UI, managed AI gateway, photo AI, timeline/map/people graph, narrative generation, FamilySearch integration, multi-family collaboration

The open-source CLI is fully functional on its own. The subscription service adds a
web UI, managed AI, and advanced visualization features. Data is fully portable between both.
See [docs/VISION.md](docs/VISION.md) for the complete roadmap.

## License

MIT License — see [LICENSE](LICENSE)
