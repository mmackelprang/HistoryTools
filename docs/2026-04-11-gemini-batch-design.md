# Gemini Batch Processing and Parallel Transcription — Design Spec

## Goal

Add Gemini Batch API support for 50% cost savings on PDF transcription, improve real-time transcription with cross-PDF parallelism and proper rate limiting, and provide a clean submit/status/collect workflow for batch jobs.

## Architecture

- **`scripts/gemini_batch.py`** — Batch API submission, status checking, result collection. One batch job per PDF.
- **`scripts/rate_limiter.py`** — Reusable token bucket rate limiter for any API. Thread-safe, configurable RPM.
- **`scripts/transcribe_pdfs_gemini.py`** — Enhanced with `--fast` flag for real-time cross-PDF parallelism, batch mode as default, and `--status`/`--collect` commands.

Batch mode is the default (`family-archive transcribe`). Real-time mode is opt-in (`--fast`). Both paths share page rendering, transcript assembly, and rate limiting.

## Design Principles

- **Batch by default, fast on demand** — batch saves 50% and is the right choice for most jobs. `--fast` is there when you need immediate results.
- **One batch = one PDF** — natural mapping to the per-file transcript model. Failures are isolated. Results are easy to track and assemble.
- **Reuse, don't duplicate** — `gemini_batch.py` imports `render_page_to_image` and `create_transcript_md` from the existing transcription module.
- **Submit and walk away** — batch jobs are fire-and-forget. Come back, check status, collect results.

## Schema Extension

One new table added to `init_schema()` in `db.py`. No schema version bump needed — this is an additive `CREATE TABLE IF NOT EXISTS`.

```sql
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY,
    batch_id TEXT NOT NULL,              -- Gemini API batch job name
    pdf_path TEXT NOT NULL,              -- relative path to the PDF
    model TEXT NOT NULL,                 -- model used (e.g., "gemini-2.5-flash")
    page_count INTEGER NOT NULL,         -- number of pages submitted
    status TEXT NOT NULL DEFAULT 'submitted',  -- submitted, succeeded, failed, expired, cancelled, collected
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    UNIQUE(batch_id)
);
```

Status lifecycle: `submitted` -> `succeeded`/`failed`/`expired`/`cancelled` -> `collected` (results written to transcript file).

## Rate Limiter (`scripts/rate_limiter.py`)

A reusable token bucket rate limiter:

```python
limiter = RateLimiter(requests_per_minute=400)
limiter.acquire()  # blocks until a token is available
```

- Thread-safe using `threading.Lock`
- RPM read from `config.json` at `transcription.requests_per_minute` (default 400)
- Pure Python, `time.monotonic()` based, no external dependencies
- Under 40 lines
- Used by both `--fast` real-time path and batch submission

## Batch Module (`scripts/gemini_batch.py`)

### `submit_batch(client, model, pdf_path, dest_root, conn, dpi=200)`

- Renders all pages to images via `render_page_to_image` (imported from `transcribe_pdfs_gemini`)
- Builds a list of `GenerateContentRequest` dicts, each containing the transcription prompt and one page image
- If total request size <= 20MB: uses inline batch (`client.batches.create(src=inline_requests)`)
- If total request size > 20MB: writes requests to JSONL, uploads via Gemini Files API, submits file-based batch
- Records the batch job in the `batches` SQLite table with `status = 'submitted'`
- Returns the Gemini batch job name

### `check_status(client, conn)`

- Queries `batches` table for all rows with `status = 'submitted'`
- For each, calls `client.batches.get(name=batch_id)`
- Updates status in SQLite based on Gemini's job state mapping:
  - `JOB_STATE_SUCCEEDED` -> `succeeded`
  - `JOB_STATE_FAILED` -> `failed`
  - `JOB_STATE_EXPIRED` -> `expired`
  - `JOB_STATE_CANCELLED` -> `cancelled`
  - `JOB_STATE_PENDING` / `JOB_STATE_RUNNING` -> stays `submitted`
- Prints summary: pending, succeeded, failed counts
- Returns dict of counts

### `collect_results(client, conn, dest_root)`

- Queries `batches` table for all rows with `status = 'succeeded'`
- For each batch job:
  - Retrieves results from `batch_job.dest.inlined_responses` (inline batches) or downloads result file (file-based batches)
  - Extracts per-page transcription text, orders by page number
  - Calls `create_transcript_md()` to assemble the `.transcript.md` file (same function as real-time path)
  - Updates status to `collected` and sets `completed_at`
- Prints per-file summary (word count, confidence)
- Returns count of collected transcripts

## Real-Time Improvements (`--fast`)

Enhancements to the existing `transcribe_pdfs_gemini.py`:

### Cross-PDF parallelism

- Process multiple PDFs concurrently using `ThreadPoolExecutor`
- Number of concurrent PDFs governed by `transcription.parallel_workers` in config (default 10)
- Each PDF still parallelizes its pages internally (existing behavior)
- Shared rate limiter governs total API calls across all concurrent PDFs

### Rate limiter integration

- Create a shared `RateLimiter` instance at startup, configured from `config.json`
- Call `limiter.acquire()` before each `transcribe_page_gemini()` call
- Replaces the unused `REQUESTS_PER_MINUTE = 200` constant

### Incremental resume preserved

The existing `_pages/` directory mechanism for incremental resume continues to work unchanged in `--fast` mode.

## Configuration

`transcription.requests_per_minute` in `config.json`:
- Default: 400 (updated from 200)
- Used by both batch submission and real-time rate limiting
- Gemini paid tier allows 2000 RPM; 400 is conservative but safe

`transcription.parallel_workers` in `config.json`:
- Default: 10
- Controls cross-PDF concurrency in `--fast` mode
- Already referenced in VISION.md

## CLI Commands

```
family-archive transcribe                           # batch mode (default) — submit jobs
family-archive transcribe --fast                     # real-time with cross-PDF parallelism
family-archive transcribe --status                   # check pending batch jobs
family-archive transcribe --collect                  # retrieve completed results, write transcripts
family-archive transcribe --folder Letters           # limit to folder (both modes)
family-archive transcribe --file path/to/file.pdf   # single file (both modes)
family-archive transcribe --dry-run                  # preview files, no API calls
family-archive transcribe --model gemini-2.5-pro     # override model
family-archive transcribe --dpi 300                  # override render DPI
family-archive transcribe --force                    # overwrite existing transcripts
family-archive transcribe --low-confidence-only      # only re-transcribe low confidence
```

**Default behavior change:** `family-archive transcribe` without `--fast` now submits batch jobs. The command prints a summary and exits. Use `--status` and `--collect` to retrieve results.

**Status output:**
```
Batch status:
  Submitted:  12 PDFs (342 pages)
  Succeeded:   8 PDFs (ready to collect)
  Failed:      1 PDF (Letters/1984-03-15_letter.pdf: rate limit exceeded)
  Pending:     3 PDFs
```

## File Map

### New files

- `scripts/rate_limiter.py` — token bucket rate limiter
- `scripts/gemini_batch.py` — batch submission, status, collection
- `tests/test_rate_limiter.py` — rate limiter unit tests
- `tests/test_gemini_batch.py` — batch module tests (mocked Gemini API)

### Modified files

- `scripts/db.py` — add `batches` table to `init_schema()`
- `scripts/transcribe_pdfs_gemini.py` — add `--fast`/`--status`/`--collect` flags, cross-PDF parallelism, rate limiter integration, make `render_page_to_image` and `create_transcript_md` importable
- `scripts/cli.py` — pass new flags through to transcribe command
- `scripts/config.py` — add `requests_per_minute` (default 400) and `parallel_workers` (default 10) to config defaults if not already present
- `docs/WORKFLOW.md` — update transcription section with batch workflow

### No new dependencies

`google-genai` SDK already supports the Batch API. `Pillow` and `PyMuPDF` already installed.

## Gemini Batch API Reference

- Inline batch: <= 20MB total request size, results returned inline
- File-based batch: up to 2GB JSONL file, results downloaded from Gemini Files
- 50% cost discount vs real-time API
- 24-hour target turnaround (usually much faster)
- Jobs expire after 48 hours if not completed
- Job creation is not idempotent — duplicate submissions create separate jobs
- Same modality support as interactive API (text + image input supported)
- Context caching enabled for batch requests

## Future Considerations

- Batch processing for other AI operations (format, rename, split proposals) using the same `gemini_batch.py` infrastructure
- Automatic collection: on any `family-archive` command, check for completed batches and notify the user
- Batch API support for OpenAI (similar async batch endpoint) when vendor abstraction is built
