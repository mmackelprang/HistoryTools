# Ingest Command — Design Spec

## Goal

A single command that scans a source directory, classifies every file using filename patterns, folder context, and file type, produces a reviewable plan, then executes the full processing pipeline: copy, transcribe, format, rename, and date-detect. Supports both standalone (new archive) and merge (add to existing) modes.

## Architecture

Ingest is a two-phase command following the same propose-then-apply pattern as rename and date detection:

- **Phase 1 (`--scan`)**: Walk source directory, classify files, produce `_ingest-plan.json` for review
- **Phase 2 (`--execute`)**: Read approved plan, run the full processing pipeline with stage-by-stage progress

Both phases use the core library functions. The CLI prints progress; the future web UI will render the same data as interactive tables and progress bars.

## CLI Interface

```bash
# Phase 1: Scan and classify
family-archive ingest /path/to/source --scan                # standalone mode
family-archive ingest /path/to/source --scan --mode merge   # merge into existing

# Phase 2: Execute the approved plan
family-archive ingest --execute
family-archive ingest --execute --skip-transcribe   # copy only
family-archive ingest --execute --skip-format       # skip formatting

# Or interactive (scan + pause for approval + execute)
family-archive ingest /path/to/source

# Preview
family-archive ingest /path/to/source --scan --dry-run
```

## Phase 1: Scan and Classify

### Process

1. Recursively walk the source directory (respecting `exclude_dirs` and `exclude_exts` from config)
2. For each file, determine:
   - **File type** from extension
   - **Category** from built-in filename and folder keyword patterns
   - **Folder hints** — source folder names like "Letters", "Photos", "Medical" boost classification confidence
   - **Date** extracted from filename if present (YYYYMMDD, YYYY-MM-DD, "Jan 2021" patterns)
   - **Proposed destination** folder and filename following naming conventions
3. Files it can't classify → route to `NeedsReview/`
4. File types it can't process → route to `Unprocessed/` with documentation
5. In merge mode: detect potential duplicates against existing archive by MD5 hash
6. Write `_ingest-plan.json`

### Known File Types and Processing Pipelines

| Extension | Type | Classification | Processing Pipeline |
|-----------|------|---------------|-------------------|
| `.pdf` | Document | Filename + folder hints | Copy → Transcribe (Gemini/Tesseract) → Format → Rename → Date-detect |
| `.mp3, .wav, .m4a, .aac, .ogg, .flac, .wma` | Audio | Filename + folder hints | Copy → Transcribe (AssemblyAI/Whisper) → Format → Rename |
| `.mp4, .mov, .avi, .mkv, .wmv` | Video | Filename + folder hints | Copy → (future: transcribe) |
| `.jpg, .jpeg, .png, .tiff, .bmp, .heic` | Photo | EXIF + folder hints | Copy → Catalog EXIF |
| `.eml, .mbox, .pst` | Email archive | File type | Copy to `_imports/EmailArchives/` |
| `.xml` (SMS backup) | SMS export | File type | Copy to `_imports/SMSExports/` (future — currently routed to Unprocessed) |
| `.gedcom, .ged` | Genealogy | File type | Copy to `_imports/` |
| `.doc, .docx, .txt, .rtf` | Text document | Filename + folder hints | Copy → Classify like PDF |
| `.xls, .xlsx, .csv` | Spreadsheet | None — requires user classification | Copy to `NeedsReview/` with log entry |
| All others | Unknown | None | Copy to `Unprocessed/` with log entry |

### Classification with Folder Hints

Source folder names inform classification without overriding it:

```
Source: "Letters from Mom/scan001.pdf"
  → Folder hint "Letters" matches Correspondence/Letters
  → High confidence classification

Source: "Old Stuff/misc/doc.pdf"
  → No useful folder hint
  → Falls back to filename pattern matching
  → If no match: NeedsReview/
```

Folder hint matching is case-insensitive and uses the `classify_patterns` from taxonomy.json. A folder called "medical records" matches the Medical category because "medical" is in its patterns.

### NeedsReview vs Unprocessed

- **NeedsReview/** — Known file types we can store and process, but can't auto-classify. Spreadsheets, ambiguous documents. User classifies these manually.
- **Unprocessed/** — File types we don't have tooling for. PowerPoint, Numbers, proprietary formats. Stored for future processing when tooling is added.

### Plan Output (`_ingest-plan.json`)

```json
{
  "source_root": "/path/to/source",
  "dest_root": "/path/to/Organized",
  "mode": "standalone",
  "scan_date": "2026-04-09",
  "summary": {
    "total_files": 573,
    "by_type": {"pdf": 340, "audio": 35, "photo": 180, "unknown": 18},
    "by_destination": {"Correspondence/Letters": 84, "Journals": 16, "Media/Photos": 180},
    "needs_review": 12,
    "unprocessable": 18,
    "duplicates_detected": 3
  },
  "files": [
    {
      "source_path": "Letters from Mom/scan001.pdf",
      "dest_folder": "Correspondence/Letters",
      "dest_subfolder": "Undated",
      "proposed_name": "undated_scan001.pdf",
      "file_type": "pdf",
      "classification_source": "folder_hint + pattern",
      "classification_confidence": "high",
      "detected_date": null,
      "processing": ["copy", "transcribe_gemini", "format", "rename", "detect_date"],
      "approved": true
    },
    {
      "source_path": "budget.xlsx",
      "dest_folder": "NeedsReview",
      "proposed_name": "budget.xlsx",
      "file_type": "spreadsheet",
      "classification_source": "needs_user_classification",
      "processing": ["copy"],
      "notes": "Spreadsheet — requires manual classification",
      "approved": true
    },
    {
      "source_path": "random_file.xyz",
      "dest_folder": "Unprocessed",
      "proposed_name": "random_file.xyz",
      "file_type": "unknown",
      "classification_source": "unknown_extension",
      "processing": ["copy"],
      "notes": "Unknown file type .xyz — no processing tooling available",
      "approved": true
    }
  ],
  "unprocessed_types": {
    ".xyz": {"count": 2, "example": "random_file.xyz"},
    ".pptx": {"count": 1, "example": "presentation.pptx"}
  },
  "needs_review_types": {
    ".xlsx": {"count": 3, "example": "budget.xlsx"},
    ".csv": {"count": 1, "example": "contacts.csv"}
  }
}
```

### Phase 1 CLI Output

```
Scanning /path/to/source...

Found 573 files in 45 folders

Classification Summary:
  Correspondence/Letters    84 files (72 from folder hints, 12 from patterns)
  Journals                  16 files
  Media/Photos             180 files (all .jpg/.png)
  Media/Audio               35 files
  Documents/Church          22 files
  Financial                 45 files
  Medical                   18 files
  NeedsReview               15 files (spreadsheets and unclassifiable documents)
  Unprocessed               18 files (unknown file types)

NeedsReview (requires manual classification):
  3x .xlsx, 1x .csv — spreadsheets
  11x .pdf — could not determine category from filename

Unknown file types (stored in Unprocessed/):
  .xyz    2 files
  .pptx   1 file
  .Numbers 3 files

Potential duplicates: 3 files (will be verified after copy)

Processing plan:
  340 PDFs → transcribe with Gemini (~$1.20)
   35 audio files → transcribe with AssemblyAI (~$7.00)
  180 photos → catalog EXIF
  All transcripts → format, propose renames, detect dates

Plan saved to _ingest-plan.json
Review and edit, then run: family-archive ingest --execute
```

## Phase 2: Execute

Reads `_ingest-plan.json` and runs each processing stage sequentially:

1. **Copy** — Copy all approved files to their destination folders with proper naming
2. **Transcribe PDFs** — Run Gemini/Tesseract on new PDFs (restartable, skips existing)
3. **Transcribe Audio** — Run AssemblyAI/Whisper on new audio files (restartable)
4. **Catalog Photos** — Run EXIF extraction on new photos
5. **Detect Duplicates** — Check for duplicates across old + new files
6. **Format Transcripts** — Add summaries and markdown formatting (restartable)
7. **Propose Renames** — Generate descriptive names for generic files (incremental)
8. **Detect Dates** — Find dates in undated files (incremental)
9. **Generate Report** — Produce archive summary

Each stage:
- Reports progress (file counts, current file)
- Logs errors but continues to next file
- Does not block subsequent stages on failure
- Uses existing restartable scripts (skip existing, incremental saving)

### Execution Output

```
=== Stage 1: Copy Files ===
Copying 573 files...
  [573/573] Done. 570 copied, 3 skipped (duplicates)

=== Stage 2: Transcribe PDFs (Gemini) ===
Found 340 PDFs to transcribe
  [340/340] Done. 338 succeeded, 2 errors

=== Stage 3: Transcribe Audio (AssemblyAI) ===
Found 35 audio files
  [35/35] Done. 35 succeeded

=== Stage 4: Catalog Photos ===
Found 180 photos
  [180/180] Done. 180 cataloged

=== Stage 5: Detect Duplicates ===
Found 3 duplicate sets. Moved to Duplicates/

=== Stage 6: Format Transcripts ===
Found 373 transcripts to format
  [373/373] Done. 370 formatted, 3 errors

=== Stage 7: Propose Renames ===
Generated 45 rename proposals
  Saved to _rename-proposals.json
  Review and apply: family-archive rename --apply

=== Stage 8: Detect Dates ===
Found 89 undated files with transcripts
  Detected dates for 67 files
  Saved to _date-proposals.json
  Review and apply: family-archive detect-dates --apply

=== Stage 9: Generate Report ===
Archive summary saved to _archive-summary.md

============================================================
Ingest complete!
  570 files organized
  373 transcripts created
  370 transcripts formatted
  45 rename proposals ready for review
  67 date proposals ready for review
  15 files in NeedsReview (manual classification needed)
  18 files in Unprocessed (unknown types)
```

Note: rename and date proposals are generated but NOT auto-applied. The user reviews and applies them separately, maintaining the propose-then-apply pattern.

## Merge Mode

When `--mode merge`:
- Scans the existing archive to build a file inventory (by MD5 hash)
- Checks each source file against the inventory
- Duplicates are flagged in the plan with `"approved": false` by default
- Merge conflicts (same destination path, different content) are flagged for manual resolution
- A `_merge-conflicts.json` log is written for any conflicts
- All other behavior is identical to standalone mode

## Restartability

- `_ingest-plan.json` persists between runs
- `--execute` checks if each file has already been copied (dest exists + same size)
- Each processing stage uses existing restartable scripts:
  - Transcription skips files with existing successful `.transcript.md`
  - Formatting skips files with `formatting: cleaned`
  - Rename proposals load existing proposals and skip already-proposed files
  - Date detection loads existing proposals and skips already-proposed files
- If interrupted at any point, `--execute` again picks up where it left off

## Web UI Mapping (Phase 3)

The same two phases map to the web UI:

**Phase 1 (Scan)** → Interactive classification table:
- File grid with source path, proposed destination, confidence
- Inline dropdowns to change classification
- Bulk select/approve/reject
- Cost estimates for transcription

**Phase 2 (Execute)** → Progress dashboard:
- Stage-by-stage progress bars
- Per-file status updates via WebSocket
- Pause/cancel buttons
- Error log with retry options

The `_ingest-plan.json` serves as the data contract between scan and execute, whether the review happens in a terminal or a browser.

## Safety

- Source files are never modified or deleted
- Plan is reviewed before execution
- `--dry-run` available on both `--scan` and `--execute`
- Unprocessable files are documented, not silently dropped
- NeedsReview files are stored with notes about why they need classification
- Merge mode defaults duplicates to not-approved
- All processing stages are independently restartable
