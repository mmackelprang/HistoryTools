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
# 1. Verify all tools are installed
family-archive verify

# 2. Set up configuration
cp config.example.json config.json
# Edit config.json with your source and destination paths

# 3. Set up API keys (optional, for AI features)
cp .env.example .env
# Edit .env with your API keys (see docs/SETUP-API-KEYS.md)

# 4. Process your archive
family-archive bootstrap /path/to/your/scans
```

## Commands

### Bootstrap — Process Everything at Once

The fastest way to process a folder of scans, recordings, and photos:

```bash
# Scan and classify all files, produce a plan for review
family-archive bootstrap /path/to/scans --scan

# Review _bootstrap-plan.json (edit classifications if needed)

# Execute the full pipeline (copy, transcribe, format, rename)
family-archive bootstrap --execute

# Or do it interactively (scan → approve → execute)
family-archive bootstrap /path/to/scans

# Merge new files into an existing archive
family-archive bootstrap /path/to/new-scans --scan --mode merge

# Source can be a ZIP file (nested ZIPs are handled too)
family-archive bootstrap /path/to/archive.zip --scan
```

Bootstrap is fully restartable — if interrupted, run `--execute` again.

### Individual Steps

You can also run each step individually for more control:

```bash
# Organize files into the archive structure
family-archive organize --dry-run        # preview
family-archive organize                  # run

# Transcribe PDFs — tiered approach (free first, AI only when needed)
python scripts/transcribe_pdfs.py        # free: native text + Tesseract OCR
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
family-archive format

# Propose descriptive filenames for generic files
family-archive rename --dry-run          # preview
family-archive rename                    # generate proposals
# Review _rename-proposals.md, then:
family-archive rename --apply            # apply approved renames

# Detect dates in undated files
family-archive detect-dates              # generate proposals
family-archive detect-dates --apply      # apply approved dates

# Catalog photos, detect duplicates, generate report
family-archive photos
family-archive duplicates
family-archive report

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

The bootstrap pipeline runs all three tiers automatically. When running manually:

```bash
python scripts/transcribe_pdfs.py                    # free: tiers 1 + 2
family-archive transcribe --low-confidence-only       # paid: tier 3 for low-confidence only
```

## AI-Powered Features

These features require API keys (see [docs/SETUP-API-KEYS.md](docs/SETUP-API-KEYS.md)):

| Command | Service | What It Does | Estimated Cost |
|---------|---------|-------------|---------------|
| `family-archive transcribe` | Google Gemini | AI vision for handwriting OCR | ~$0.50-1.00 per 1000 pages |
| `family-archive transcribe --low-confidence-only` | Google Gemini | AI only for low-confidence files | Much less (only handwriting) |
| `family-archive transcribe-audio` | AssemblyAI | Speaker-diarized audio transcription | ~$0.01/minute |
| `family-archive format` | Anthropic Claude | Markdown formatting + summaries | ~$0.10-0.20 per 500 files |
| `family-archive rename` | Google Gemini | AI-suggested filenames | ~$0.10-0.30 per 500 files |
| `family-archive detect-dates` | Google Gemini | Date detection in undated files | ~$0.05-0.10 per 200 files |

All AI features are optional. Without API keys, local tools (Tesseract OCR, Whisper) are used instead.

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
| assemblyai | Audio transcription with speaker ID |
| anthropic | Transcript formatting with Claude |
| openai-whisper | Local audio transcription |
| exifread | EXIF metadata from photos |

System tools (install separately): [Tesseract OCR](https://github.com/tesseract-ocr/tesseract), [FFmpeg](https://ffmpeg.org/download.html)

## Documentation

| File | Contents |
|------|----------|
| [docs/SETUP-API-KEYS.md](docs/SETUP-API-KEYS.md) | API key setup for Gemini, AssemblyAI, and Anthropic |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Step-by-step processing guide |
| [docs/VISION.md](docs/VISION.md) | Long-term product vision and roadmap |

## Roadmap

- **Phase 1** (current): CLI toolkit for documents, audio, and basic organization
- **Phase 2**: Library refactor, SQLite index, video transcription, email import, document splitting
- **Phase 3**: Web UI for browsing, searching, and managing the archive
- **Phase 4**: Photo AI (scene descriptions, face recognition, date estimation)
- **Phase 5**: SMS import, Google Timeline, email import — correlation engine
- **Phase 6**: Timeline view, map view, people graph — life history visualization
- **Phase 7**: Narrative generation, FamilySearch integration
- **Phase 8**: Multi-family support, sharing, collaboration

## License

MIT License — see [LICENSE](LICENSE)
