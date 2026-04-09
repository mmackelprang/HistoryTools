# Processing Workflow

This guide walks through the recommended order for processing a family archive.

## Prerequisites

1. Install all tools: `python scripts/verify_tools.py`
2. Configure paths: edit `config.json`
3. Set up API keys (optional): see [SETUP-API-KEYS.md](SETUP-API-KEYS.md)

## Step-by-Step

### 1. Organize Files

```bash
# Preview classification
python scripts/organize.py --dry-run

# Run organization
python scripts/organize.py
```

Files are classified by filename patterns and file type, renamed with date prefixes,
and copied to the appropriate folders.

### 2. Transcribe PDFs

**Option A: Local OCR (free, works for printed text)**
```bash
python scripts/transcribe_pdfs.py
```

**Option B: Gemini AI Vision (paid, excellent for handwriting)**
```bash
python scripts/transcribe_pdfs_gemini.py --dry-run  # preview + cost estimate
python scripts/transcribe_pdfs_gemini.py             # run
```

### 3. Transcribe Audio

**Option A: Local Whisper (free, CPU-intensive)**
```bash
python scripts/transcribe_audio.py
```

**Option B: AssemblyAI (paid, speaker diarization)**
```bash
python scripts/transcribe_audio_assemblyai.py --dry-run  # preview + cost
python scripts/transcribe_audio_assemblyai.py             # run
```

### 4. Label Speakers (audio only)

After AssemblyAI transcription, assign real names to speakers:

```bash
# Interactive mode — shows samples, prompts for names
python scripts/label_speakers.py path/to/transcript.md

# Batch mode
python scripts/label_speakers.py --dir AudioRecordings --map "A=Alice,B=Bob"
```

### 5. Format Transcripts

Add summaries, markdown headers, and clean formatting:

```bash
python scripts/format_transcripts.py --dry-run
python scripts/format_transcripts.py
```

### 6. Rename Generic Files

```bash
# Generate rename proposals
python scripts/propose_renames.py --dry-run  # preview
python scripts/propose_renames.py            # generate proposals

# Review _rename-proposals.md
# Edit _rename-proposals.json if needed (set "approved": false to skip)

# Apply approved renames
python scripts/apply_renames.py --dry-run    # preview
python scripts/apply_renames.py              # apply
```

### 7. Detect Dates in Undated Files

```bash
python scripts/detect_dates.py               # propose dates
# Review _date-proposals.json
python scripts/detect_dates.py --apply       # apply approved dates
```

### 8. Catalog Photos and Detect Duplicates

```bash
python scripts/catalog_photos.py
python scripts/handle_duplicates.py
```

### 9. Generate Report

```bash
python scripts/generate_report.py
```

## Tips

- **Start with `--dry-run`** on every command to preview what will happen
- **Process in batches** using `--folder` to limit to one folder at a time
- **Use `--force`** to reprocess files that already have transcripts
- **All operations are restartable** — if interrupted, just run again
- **Source files are never modified** — all work produces copies in the destination
