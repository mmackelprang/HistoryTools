# Document Splitting — Design Spec

## Goal

A two-phase propose-then-apply command that identifies document boundaries in large compilation PDFs and splits them into individual files with extracted transcripts. Uses existing transcripts for boundary detection (free text-only AI call) and transcript extraction (free, no re-transcription needed).

## Architecture

Same propose-then-apply pattern as rename and date detection. Two scripts:
- `split_propose.py` — analyze transcripts, identify boundaries, write proposals
- `split_apply.py` — extract pages and transcripts from source, create individual files

Both use the existing `ai_client.py` for AI calls and `config.py` for configuration.

## CLI Interface

```bash
family-archive split                                    # propose splits for all large files
family-archive split --file path/to/compilation.pdf     # propose for one file
family-archive split --min-pages 10                     # only files with 10+ pages (default: 5)
family-archive split --apply                            # apply approved splits
family-archive split --apply --retranscribe             # re-transcribe instead of extracting
family-archive split --apply --archive-original         # move original to _compilations/
family-archive split --dry-run                          # preview without changes
```

## Phase 1: Propose (`split_propose.py`)

### Process

1. Find PDFs with page count >= `--min-pages` (default 5)
2. For each, read the `.transcript.md` (which has `## Page N` markers)
3. Send transcript text to AI with boundary detection prompt
4. AI returns segments with page ranges, detected dates, and descriptions
5. Extract the first ~60 characters of each segment's text as a preview
6. Write `_split-proposals.json` and `_split-proposals.md`

### AI Prompt

```
You are analyzing a transcript of a compilation PDF containing multiple documents
(letters, journal entries, or mixed documents) scanned into a single file.

Identify the boundaries between individual documents. Look for:
- Letter markers: salutations ("Dear ..."), sign-offs ("Love, ..."), dates, address blocks
- Journal entries: date headers, entry separators
- Blank or separator pages
- Shifts in author voice, topic, or handwriting style (noted in image descriptions)
- Page headers/footers that change between documents

For each segment, provide:
- Page numbers (1-indexed, matching the ## Page N markers in the transcript)
- Detected date (YYYY-MM-DD format, use 00 for unknown parts)
- A short descriptive filename slug
- A one-line description
- Whether pages should be skipped (blank separators)

Transcript:
{transcript_text}

Respond with JSON only:
{
  "segments": [
    {
      "pages": [1, 2, 3],
      "date": "1984-03-15",
      "slug": "letter-alice-bob-spring-update",
      "description": "Letter from Alice about spring semester",
      "skip": false
    }
  ]
}
```

### Proposals JSON (`_split-proposals.json`)

```json
[
  {
    "source_file": "Letters/1984/1984-00-00_family-correspondence-vol1.pdf",
    "source_pages": 139,
    "segments": [
      {
        "pages": [1, 2, 3],
        "detected_date": "1984-03-15",
        "proposed_name": "1984-03-15_letter-alice-bob-spring-update.pdf",
        "proposed_folder": "Letters/1984/",
        "description": "Letter from Alice about spring semester",
        "preview": "Dear Bob, I wanted to write to you about...",
        "skip": false,
        "approved": true
      }
    ]
  }
]
```

### Proposals Markdown (`_split-proposals.md`)

```markdown
# Split Proposals

## Letters/1984/1984-00-00_family-correspondence-vol1.pdf (139 pages -> 30 segments)

| # | Pages | Date | Proposed Name | Preview |
|---|-------|------|--------------|---------|
| 1 | 1-3 | 1984-03-15 | letter-alice-bob-spring-update.pdf | "Dear Bob, I wanted to write..." |
| 2 | 4-5 | 1984-04-02 | letter-bob-alice-travels-update.pdf | "Dear Alice, Today we had a..." |
| 3 | 6 | — | *(blank separator — skip)* | [blank] |

Edit _split-proposals.json to change names, adjust page ranges, or set "approved": false.
Then run: family-archive split --apply
```

### Files to scan

Finds PDFs in all transcribe_folders that have:
- Page count >= min_pages (default 5)
- An existing `.transcript.md` with page markers
- No existing split log entry (haven't been split before)

If a file has no transcript, it is skipped with a note (user should transcribe first).

## Phase 2: Apply (`split_apply.py`)

### Process

For each source file with approved segments:

1. **Extract PDF pages** — Use PyMuPDF to extract each segment's pages into a new PDF
2. **Extract transcript** — Parse the source `.transcript.md`, extract text for the segment's pages, renumber page markers (Page 1, 2, 3 instead of original page numbers)
3. **Create transcript** — Write a new `.transcript.md` for each segment with:
   - Updated frontmatter (new source_file, page_count, word_count)
   - `transcription_method: split (from <original_filename>)` to indicate origin
   - Extracted and renumbered page text
4. **Create destination folders** — Year folders as needed
5. **Log** — Record in `_split-log.json`

### Transcript extraction logic

```python
def extract_transcript_pages(full_transcript_body, page_numbers):
    """Extract text for specific pages from a transcript with ## Page N markers.
    Renumbers pages starting from 1."""
    # Parse out each page's content by splitting on ## Page N markers
    # Return only the requested pages, renumbered sequentially
```

This is **free** — no AI call needed. Just string parsing.

### --retranscribe flag

When `--retranscribe` is passed, skip transcript extraction and instead run the free
transcription pipeline (native + Tesseract) on each split PDF. Use this when the
original compilation transcript is low quality.

### --archive-original flag

When `--archive-original` is passed, move the original compilation PDF and its
transcript to a `_compilations/` subfolder within the same directory. The original
is never deleted.

### Restartability

- Proposals file persists between runs
- Apply checks if each split PDF already exists (skips if so)
- Split log tracks completed splits
- If interrupted, `--apply` again picks up where it left off

## Incremental saving

Like rename proposals, split proposals are saved incrementally after each file
is analyzed, so a crash doesn't lose all progress.

## Safety

- Original compilation PDF is never modified or deleted
- Split files are copies (new PDFs extracted from the original)
- Proposals reviewed before applying
- `--dry-run` on both phases
- `_split-log.json` records every operation
- Extracted transcripts marked with `transcription_method: split` for traceability

## Note for Phase 3 (subscription UI)

The CLI split is functional but limited by lack of visual verification. The web-based
splitter will provide:
- Page thumbnail grid with draggable split boundaries
- AI-proposed segments highlighted with color coding
- Per-segment preview with proposed name and date
- Side-by-side view: page thumbnails + transcript text
- Approve/edit/merge/split individual segments

The `_split-proposals.json` format is designed to be consumed by the web UI
as well as the CLI.
