# Processing Workflow

This guide walks through the recommended order for processing a family archive.

## Getting Started

```bash
pip install -e ".[all]"     # install
family-archive init          # interactive setup wizard
```

The init wizard creates your `config.json`, `.env` (API keys), and archive folder structure.

## Step-by-Step

### 0. Ingest (Recommended for New Archives)

If you're starting from scratch with a folder of scans, use ingest to do everything at once:

```bash
family-archive ingest /path/to/source --scan    # classify and preview
family-archive ingest --execute                  # run full pipeline
```

Ingest runs all the steps below automatically. You can also run each step individually
if you prefer more control.

### 1. Organize Files

```bash
# Preview classification
family-archive organize --dry-run

# Run organization
family-archive organize
```

Files are classified by filename patterns and file type, renamed with date prefixes,
and copied to the appropriate folders.

### 2. Transcribe PDFs

Transcription uses a tiered approach to minimize costs:

**Step 1: Free local transcription (native text + Tesseract OCR)**
```bash
python scripts/transcribe_pdfs.py
```

This handles all PDFs with embedded text and printed/typed scanned documents for free.

**Step 2: AI for remaining low-confidence files (paid, for handwriting)**
```bash
family-archive transcribe --low-confidence-only --dry-run   # preview what needs AI
family-archive transcribe --low-confidence-only              # run AI on handwritten docs only
```

**Or transcribe everything with AI (paid)**
```bash
family-archive transcribe --force        # AI transcription for all PDFs
```

### 3. Transcribe Audio

**Option A: AssemblyAI (paid, speaker diarization)**
```bash
family-archive transcribe-audio --dry-run   # preview + cost
family-archive transcribe-audio             # run
```

**Option B: Local Whisper (free, CPU-intensive)**
```bash
python scripts/transcribe_audio.py
```

### 4. Label Speakers (audio only)

After audio transcription, assign real names to speakers:

```bash
# Interactive mode — shows samples, prompts for names
family-archive speakers path/to/transcript.md

# Batch mode
family-archive speakers --dir AudioRecordings --map "A=Alice,B=Bob"
```

### 5. Format Transcripts

Add summaries, markdown headers, and clean formatting:

```bash
family-archive format --dry-run
family-archive format
```

### 6. Rename Generic Files

```bash
# Generate rename proposals
family-archive rename --dry-run     # preview
family-archive rename               # generate proposals

# Review _rename-proposals.md
# Edit _rename-proposals.json if needed (set "approved": false to skip)

# Apply approved renames
family-archive rename --apply --dry-run     # preview
family-archive rename --apply               # apply
```

### 7. Detect Dates in Undated Files

```bash
family-archive detect-dates              # propose dates
# Review _date-proposals.json
family-archive detect-dates --apply      # apply approved dates
```

### 8. Catalog Photos and Detect Duplicates

```bash
family-archive photos
family-archive duplicates
```

### 9. Generate Report

```bash
family-archive report
```

## Tips

- **Start with `--dry-run`** on every command to preview what will happen
- **Process in batches** using `--folder` to limit to one folder at a time
- **Use `--force`** to reprocess files that already have transcripts
- **All operations are restartable** — if interrupted, just run again
- **Source files are never modified** — all work produces copies in the destination
