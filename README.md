# HistoryTools

A CLI toolkit for digitizing, organizing, transcribing, and searching family archives — scanned documents, photos, audio recordings, and more. Turn a box of old scans, cassette tapes, and photos into a searchable, organized, transcribed digital archive.

## What It Does

| Step | Script | What Happens |
|------|--------|-------------|
| 0 | `bootstrap.py` | Scan, classify, and process an entire source folder in one command |
| 1 | `verify_tools.py` | Checks that all required tools are installed |
| 2 | `organize.py` | Classifies files by name/type, renames with dates, copies to organized folders |
| 3 | `transcribe_pdfs.py` | Extracts text from PDFs (native text or Tesseract OCR) |
| 4 | `transcribe_pdfs_gemini.py` | Transcribes PDFs using Google Gemini AI vision (great for handwriting) |
| 5 | `transcribe_audio.py` | Transcribes audio locally with OpenAI Whisper |
| 6 | `transcribe_audio_assemblyai.py` | Transcribes audio with AssemblyAI (speaker diarization) |
| 7 | `format_transcripts.py` | Adds summaries, headers, and markdown formatting to transcripts |
| 8 | `label_speakers.py` | Assigns real names to Speaker A/B/C labels in audio transcripts |
| 9 | `propose_renames.py` | Proposes descriptive filenames for generic files using AI |
| 10 | `apply_renames.py` | Applies reviewed rename proposals |
| 11 | `detect_dates.py` | Detects dates in undated files and proposes renames |
| 12 | `catalog_photos.py` | Reads EXIF data, generates photo catalog |
| 13 | `handle_duplicates.py` | Finds identical files by MD5 hash, moves dupes |
| 14 | `generate_report.py` | Produces archive summary with statistics |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/mmackelprang/HistoryTools.git
cd HistoryTools

# 2. Install Python dependencies
pip install PyMuPDF exifread openai-whisper Pillow google-genai assemblyai python-dotenv anthropic

# 3. Install system tools
# Tesseract OCR: https://github.com/tesseract-ocr/tesseract
# FFmpeg: https://ffmpeg.org/download.html

# 4. Verify everything is installed
python scripts/verify_tools.py

# 5. Set up configuration
cp config.example.json config.json
# Edit config.json with your source and destination paths

# 6. Set up API keys (optional, for AI features)
cp .env.example .env
# Edit .env with your API keys (see docs/SETUP-API-KEYS.md)

# 7. Bootstrap — scan, classify, and process everything
python scripts/bootstrap.py /path/to/your/scans --scan    # scan and classify (writes plan)
python scripts/bootstrap.py --execute                     # run the full pipeline
```

## Bootstrap (One-Command Processing)

The fastest way to process a folder of scans, recordings, and photos:

```bash
# Scan source folder and preview classification
python scripts/bootstrap.py /path/to/scans --scan

# Review _bootstrap-plan.json (edit classifications if needed)

# Execute the full pipeline
python scripts/bootstrap.py --execute

# Or do it interactively (scan + approve + execute)
python scripts/bootstrap.py /path/to/scans

# Merge new files into an existing archive
python scripts/bootstrap.py /path/to/new-scans --scan --mode merge
```

Bootstrap is fully restartable — if interrupted, just run `--execute` again.
It skips already-copied files, already-transcribed files, and already-formatted
transcripts, picking up where it left off.

## AI-Powered Features

These features require API keys (see [docs/SETUP-API-KEYS.md](docs/SETUP-API-KEYS.md)):

| Script | Service | What It Does | Estimated Cost |
|--------|---------|-------------|---------------|
| `transcribe_pdfs_gemini.py` | Google Gemini | AI vision for handwriting OCR | ~$0.50-1.00 per 1000 pages |
| `transcribe_audio_assemblyai.py` | AssemblyAI | Speaker-diarized audio transcription | ~$0.01/minute |
| `format_transcripts.py` | Anthropic Claude | Markdown formatting + summaries | ~$0.10-0.20 per 500 files |
| `propose_renames.py` | Google Gemini | AI-suggested filenames | ~$0.10-0.30 per 500 files |
| `detect_dates.py` | Google Gemini | Date detection in undated files | ~$0.05-0.10 per 200 files |

## Two Modes

### Standalone Mode (`"mode": "standalone"`)
Creates a fresh organized archive from scratch. Use for:
- A new collection of scanned documents
- Starting your first digital archive
- Testing on a small batch before committing

### Merge Mode (`"mode": "merge"`)
Adds new files into an existing organized archive. Use for:
- Adding a new batch of scans
- Combining multiple family archives
- Incremental processing as new documents are found

## Configuration

Edit `config.json` (copy from `config.example.json`):

```json
{
  "source_root": "/path/to/source/files",
  "dest_root": "/path/to/Organized",
  "mode": "standalone",
  "whisper_model": "base",
  "transcribe_folders": ["Letters", "Journals", "Cards", "Documents/Writings"]
}
```

## File Naming Convention

All files are renamed to: `YYYY-MM-DD_descriptive-slug.ext`

- Dates sourced from: filename > EXIF > content analysis
- Unknown dates: `undated_slug.ext`
- Partial dates: `1983-06-00_slug.ext` (month known, day unknown)

## Required Tools

| Tool | Install | Purpose |
|------|---------|---------|
| Python 3.10+ | — | Script runtime |
| Pillow | `pip install Pillow` | Image processing |
| PyMuPDF | `pip install PyMuPDF` | PDF text extraction & page rendering |
| exifread | `pip install exifread` | EXIF metadata from photos |
| Tesseract | [tesseract-ocr](https://github.com/tesseract-ocr/tesseract) | OCR for scanned documents |
| FFmpeg | [ffmpeg.org](https://ffmpeg.org/download.html) | Audio duration/metadata |

### Optional (for AI features)

| Tool | Install | Purpose |
|------|---------|---------|
| google-genai | `pip install google-genai` | Gemini AI for handwriting OCR |
| assemblyai | `pip install assemblyai` | Audio transcription with speaker ID |
| anthropic | `pip install anthropic` | Transcript formatting with Claude |
| python-dotenv | `pip install python-dotenv` | Load API keys from .env |
| Whisper | `pip install openai-whisper` | Local audio transcription |

## Safety

- **Source files are never modified or deleted** — all operations produce copies
- **Duplicates are moved, never deleted** — review at your leisure
- **Unclassifiable files go to NeedsReview** — nothing is silently discarded
- **All operations support `--dry-run`** — preview before committing
- **All operations are restartable** — interrupted jobs resume where they left off
- **Proposals require review** — renames, date changes, and splits are proposed then applied

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
