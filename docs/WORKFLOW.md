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

**Step 2: AI transcription (batch mode — 50% cheaper, default)**
```bash
family-archive transcribe                            # submit batch jobs (default)
family-archive transcribe --folder Letters           # limit to one folder
family-archive transcribe --low-confidence-only      # only low-confidence files
family-archive transcribe --dry-run                  # preview, no API calls

# Check status and collect results
family-archive transcribe --status                   # see pending/completed jobs
family-archive transcribe --collect                  # write transcripts from completed jobs
```

Batch mode submits PDFs to Gemini's batch endpoint at 50% cost. Jobs complete
within 24 hours (usually much faster). Submit, check status, collect results.

**Step 2 (alternative): Real-time AI transcription (immediate results)**
```bash
family-archive transcribe --fast                     # real-time, cross-PDF parallelism
family-archive transcribe --fast --force             # overwrite existing transcripts
```

Use `--fast` when you need results immediately. Costs 2x batch mode but returns
results in minutes instead of hours.

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

### 7. Split Compilation PDFs

If you have large PDFs containing multiple letters or journal entries in one file:

```bash
# Preview which files are candidates for splitting
family-archive split --dry-run

# Generate split proposals (AI detects document boundaries)
family-archive split

# Review _split-proposals.md
# Edit _split-proposals.json if needed (set "approved": false to skip segments)

# Apply approved splits
family-archive split --apply --dry-run     # preview
family-archive split --apply               # apply

# Optionally move originals to _compilations/ subfolder
family-archive split --apply --archive-original
```

Splitting uses existing transcripts for boundary detection (text-only AI call),
and transcript extraction is free (string parsing, no re-transcription needed).

### 8. Detect Dates in Undated Files

```bash
family-archive detect-dates              # propose dates
# Review _date-proposals.json
family-archive detect-dates --apply      # apply approved dates
```

### 9. Detect and Manage Duplicates

```bash
# Scan for duplicates (exact MD5, text similarity, perceptual hash)
family-archive duplicates --scan
family-archive duplicates --scan --dry-run           # preview only
family-archive duplicates --scan --type exact         # only exact matches
family-archive duplicates --scan --folder Letters     # limit to folder

# Review _duplicate-proposals.md, edit _duplicate-proposals.json if needed

# Quarantine approved duplicates (moves to _duplicates/)
family-archive duplicates --apply
family-archive duplicates --apply --dry-run

# Check quarantine status
family-archive duplicates --status

# Restore a quarantined file
family-archive duplicates --restore _duplicates/Letters/letter.pdf

# Purge quarantined files past 14-day TTL
family-archive duplicates --purge
family-archive duplicates --purge --all              # purge regardless of TTL
```

Duplicates are quarantined to `_duplicates/` for 14 days before permanent deletion.
Files related by provenance (e.g., split from the same compilation PDF) are excluded
from duplicate detection.

### 10. Catalog Photos

```bash
family-archive photos
```

### 11. Build Search Index

```bash
# Full rebuild of the search index
family-archive reindex

# Verify the index matches the filesystem
family-archive reindex --check

# Search across all transcripts
family-archive search "Springfield"
family-archive search "keyword" --folder Letters --year 1984

# View archive statistics
family-archive stats
```

The search index is a SQLite database (`.archive.db`) that indexes all files and
transcript text. It's a rebuildable cache — delete and reindex anytime.

### 12. Generate Report

```bash
family-archive report
```

### 13. Review AI Costs

After running AI-powered commands, review what you spent:

```bash
family-archive costs              # summary by pipeline step
family-archive costs --detail     # include per-session breakdown
```

Costs are tracked automatically in `_costs.json` in the archive root.
Each AI API call records token usage and estimated cost by model.

## Tips

- **Start with `--dry-run`** on every command to preview what will happen
- **Process in batches** using `--folder` to limit to one folder at a time
- **Use `--force`** to reprocess files that already have transcripts
- **All operations are restartable** — if interrupted, just run again
- **Source files are never modified** — all work produces copies in the destination
