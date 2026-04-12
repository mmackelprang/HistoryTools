# Gemini Batch Processing and Parallel Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gemini Batch API support for 50% cheaper PDF transcription, with cross-PDF parallelism for real-time mode and a submit/status/collect workflow for batch jobs.

**Architecture:** Three modules: `rate_limiter.py` (reusable token bucket), `gemini_batch.py` (batch submit/status/collect), and enhanced `transcribe_pdfs_gemini.py` (cross-PDF parallelism, batch default). Batch jobs are tracked in a `batches` SQLite table. One batch job per PDF.

**Tech Stack:** Python 3.10+, google-genai SDK (existing), SQLite (existing), PyMuPDF (existing), ThreadPoolExecutor

**Design spec:** `docs/2026-04-11-gemini-batch-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/rate_limiter.py` | Reusable thread-safe token bucket rate limiter |
| `scripts/gemini_batch.py` | Gemini Batch API: submit, check status, collect results |
| `scripts/transcribe_pdfs_gemini.py` | Enhanced with `--fast`/`--status`/`--collect`, cross-PDF parallelism, rate limiter |
| `scripts/db.py` | Add `batches` table to init_schema |
| `scripts/config.py` | Add `requests_per_minute` and `parallel_workers` defaults |
| `scripts/cli.py` | Pass new flags through to transcribe command |
| `tests/test_rate_limiter.py` | Rate limiter unit tests |
| `tests/test_gemini_batch.py` | Batch module tests (mocked API) |
| `docs/WORKFLOW.md` | Update transcription section with batch workflow |

---

### Task 1: Rate limiter module

**Files:**
- Create: `scripts/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests for rate limiter**

Create `tests/test_rate_limiter.py`:

```python
"""
Tests for the rate limiter module (scripts/rate_limiter.py).
"""

import time
import threading

import pytest

from scripts.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test token bucket rate limiter."""

    def test_acquire_succeeds_immediately_when_tokens_available(self):
        limiter = RateLimiter(requests_per_minute=600)  # 10 per second
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # should be nearly instant

    def test_acquire_blocks_when_tokens_exhausted(self):
        limiter = RateLimiter(requests_per_minute=60)  # 1 per second
        limiter.acquire()  # use the initial token
        start = time.monotonic()
        limiter.acquire()  # should wait ~1 second
        elapsed = time.monotonic() - start
        assert elapsed >= 0.8  # allow some tolerance

    def test_multiple_acquires_within_rate(self):
        limiter = RateLimiter(requests_per_minute=6000)  # 100 per second
        for _ in range(10):
            limiter.acquire()
        # Should complete very quickly at this rate
        # Just verify no exceptions

    def test_thread_safety(self):
        limiter = RateLimiter(requests_per_minute=6000)
        results = []

        def worker():
            limiter.acquire()
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(results) == 20

    def test_custom_rpm(self):
        limiter = RateLimiter(requests_per_minute=120)
        assert limiter.requests_per_minute == 120
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rate_limiter.py -v`
Expected: FAIL — `rate_limiter` module doesn't exist

- [ ] **Step 3: Implement rate limiter**

Create `scripts/rate_limiter.py`:

```python
"""
Reusable token bucket rate limiter.

Thread-safe, configurable RPM, pure Python. Use for any API that
has rate limits (Gemini, OpenAI, Anthropic, AssemblyAI).
"""

import time
import threading


class RateLimiter:
    """Token bucket rate limiter.

    Usage:
        limiter = RateLimiter(requests_per_minute=400)
        limiter.acquire()  # blocks until a token is available
    """

    def __init__(self, requests_per_minute=400):
        self.requests_per_minute = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._lock = threading.Lock()
        self._next_allowed = time.monotonic()

    def acquire(self):
        """Block until a request token is available."""
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                sleep_time = self._next_allowed - now
                self._next_allowed += self._interval
            else:
                sleep_time = 0
                self._next_allowed = now + self._interval

        if sleep_time > 0:
            time.sleep(sleep_time)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rate_limiter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: add reusable token bucket rate limiter

- Thread-safe RateLimiter with configurable RPM
- Pure Python, time.monotonic() based
- Reusable for Gemini, OpenAI, Anthropic, and other rate-limited APIs"
```

---

### Task 2: Add batches table to schema

**Files:**
- Modify: `scripts/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing test for batches table**

Add to `tests/test_db.py`:

```python
class TestBatchesTable:
    """Test batches table for Gemini batch job tracking."""

    def test_batches_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batches'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_batches_insert_and_query(self, tmp_path):
        conn = get_db(tmp_path)
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
            VALUES (?, ?, ?, ?, ?)
        """, ("batch-abc123", "Letters/letter.pdf", "gemini-2.5-flash", 5, "submitted"))
        conn.commit()
        cursor = conn.execute("SELECT * FROM batches WHERE batch_id = ?", ("batch-abc123",))
        row = cursor.fetchone()
        assert row["pdf_path"] == "Letters/letter.pdf"
        assert row["model"] == "gemini-2.5-flash"
        assert row["page_count"] == 5
        assert row["status"] == "submitted"
        close_db(conn)

    def test_batches_unique_batch_id(self, tmp_path):
        import sqlite3
        conn = get_db(tmp_path)
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count)
            VALUES (?, ?, ?, ?)
        """, ("batch-123", "a.pdf", "gemini-2.5-flash", 1))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO batches (batch_id, pdf_path, model, page_count)
                VALUES (?, ?, ?, ?)
            """, ("batch-123", "b.pdf", "gemini-2.5-flash", 2))
        close_db(conn)

    def test_batches_status_update(self, tmp_path):
        conn = get_db(tmp_path)
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count)
            VALUES (?, ?, ?, ?)
        """, ("batch-456", "letter.pdf", "gemini-2.5-flash", 3))
        conn.commit()
        conn.execute("""
            UPDATE batches SET status = 'succeeded', completed_at = CURRENT_TIMESTAMP
            WHERE batch_id = ?
        """, ("batch-456",))
        conn.commit()
        cursor = conn.execute("SELECT status, completed_at FROM batches WHERE batch_id = ?", ("batch-456",))
        row = cursor.fetchone()
        assert row["status"] == "succeeded"
        assert row["completed_at"] is not None
        close_db(conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py::TestBatchesTable -v`
Expected: FAIL — batches table doesn't exist

- [ ] **Step 3: Add batches table to init_schema**

In `scripts/db.py`, add the batches table to the schema v2 `executescript` block (after the quarantine table, before the closing `"""`):

```sql
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            model TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            UNIQUE(batch_id)
        );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add batches table for Gemini batch job tracking

- Tracks batch_id, pdf_path, model, page_count, status, timestamps
- UNIQUE constraint on batch_id
- Status lifecycle: submitted -> succeeded/failed/expired -> collected"
```

---

### Task 3: Config defaults for rate limiting and parallelism

**Files:**
- Modify: `scripts/config.py`
- Modify: `scripts/transcribe_pdfs_gemini.py`

- [ ] **Step 1: Add config defaults**

In `scripts/config.py`, add two new keys to `DEFAULT_CONFIG` (after `"db_path": None`):

```python
    "requests_per_minute": 400,  # API rate limit (Gemini paid tier allows 2000)
    "parallel_workers": 10,      # concurrent PDFs in --fast mode
```

- [ ] **Step 2: Update transcribe_pdfs_gemini.py to remove hardcoded constant**

In `scripts/transcribe_pdfs_gemini.py`, remove the unused constant on line 33:

```python
REQUESTS_PER_MINUTE = 200  # paid tier allows 2000 RPM; 200 is conservative
```

Delete this line entirely — rate limiting will come from the config via `RateLimiter`.

- [ ] **Step 3: Run existing tests**

Run: `python -m pytest tests/ --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/config.py scripts/transcribe_pdfs_gemini.py
git commit -m "feat: add requests_per_minute and parallel_workers config defaults

- requests_per_minute default 400 (up from hardcoded 200)
- parallel_workers default 10 for cross-PDF concurrency
- Remove hardcoded REQUESTS_PER_MINUTE constant from transcribe_pdfs_gemini.py"
```

---

### Task 4: Batch module — submit_batch

**Files:**
- Create: `scripts/gemini_batch.py`
- Create: `tests/test_gemini_batch.py`

- [ ] **Step 1: Write failing tests for batch submission**

Create `tests/test_gemini_batch.py`:

```python
"""
Tests for the Gemini batch processing module (scripts/gemini_batch.py).

All tests mock the Gemini API — no real API calls are made.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.db import get_db, close_db
from scripts.gemini_batch import submit_batch, check_status, collect_results


def make_file(path: Path, content: str = "test content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_test_pdf(path: Path, pages: int = 3) -> Path:
    """Create a minimal PDF with the given number of pages."""
    import fitz
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(fitz.Point(72, 72), f"Page {i+1} test content")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


class TestSubmitBatch:
    """Test batch job submission."""

    def test_submit_creates_batch_record(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "Letters" / "letter.pdf", pages=2)
        conn = get_db(dest)

        mock_client = MagicMock()
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/batch-test-123"
        mock_client.batches.create.return_value = mock_batch_job

        batch_id = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)

        assert batch_id == "batches/batch-test-123"
        cursor = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["pdf_path"] == "Letters/letter.pdf"
        assert row["status"] == "submitted"
        assert row["page_count"] == 2
        close_db(conn)

    def test_submit_calls_gemini_api(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "Letters" / "letter.pdf", pages=1)
        conn = get_db(dest)

        mock_client = MagicMock()
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/batch-abc"
        mock_client.batches.create.return_value = mock_batch_job

        submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)

        mock_client.batches.create.assert_called_once()
        call_kwargs = mock_client.batches.create.call_args
        assert call_kwargs.kwargs["model"] == "gemini-2.5-flash"
        close_db(conn)

    def test_submit_skips_already_submitted(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "Letters" / "letter.pdf", pages=1)
        conn = get_db(dest)

        # Pre-insert a batch record for this PDF
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
            VALUES (?, ?, ?, ?, ?)
        """, ("batches/existing", "Letters/letter.pdf", "gemini-2.5-flash", 1, "submitted"))
        conn.commit()

        mock_client = MagicMock()
        result = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)

        assert result is None  # skipped
        mock_client.batches.create.assert_not_called()
        close_db(conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gemini_batch.py::TestSubmitBatch -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement submit_batch**

Create `scripts/gemini_batch.py`:

```python
"""
Gemini Batch API integration for the Family Archive.

Submits PDF transcription jobs to Gemini's batch endpoint for 50% cost savings.
One batch job per PDF. Results are collected asynchronously via --collect.
"""

import base64
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))


def _rel_path(dest_root, file_path):
    """Get forward-slash relative path from dest_root."""
    try:
        rel = Path(file_path).relative_to(Path(dest_root))
    except ValueError:
        rel = Path(file_path)
    return str(rel).replace("\\", "/")


def submit_batch(client, model, pdf_path, dest_root, conn, dpi=200):
    """Submit a PDF for batch transcription via Gemini Batch API.

    Renders each page to an image, builds batch requests, and submits
    to Gemini. Records the batch job in the batches SQLite table.

    Args:
        client: google.genai.Client instance.
        model: Model name (e.g., "gemini-2.5-flash").
        pdf_path: Path to the PDF file.
        dest_root: Archive root directory.
        conn: SQLite connection.
        dpi: Render DPI for page images (default 200).

    Returns:
        Batch job name string, or None if skipped.
    """
    pdf_path = Path(pdf_path)
    rel = _rel_path(dest_root, pdf_path)

    # Check if already submitted (not yet collected)
    cursor = conn.execute(
        "SELECT batch_id FROM batches WHERE pdf_path = ? AND status IN ('submitted', 'succeeded')",
        (rel,)
    )
    if cursor.fetchone():
        print(f"  Skipping (already submitted): {rel}")
        return None

    # Render pages
    from transcribe_pdfs_gemini import render_page_to_image, TRANSCRIPTION_PROMPT
    import fitz

    doc = fitz.open(str(pdf_path))
    page_count = len(doc)

    # Build inline requests — one per page
    inline_requests = []
    total_size = 0

    for page_num in range(page_count):
        image_bytes = render_page_to_image(doc, page_num, dpi=dpi)
        total_size += len(image_bytes)

        mime_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"
        b64_data = base64.b64encode(image_bytes).decode("ascii")

        inline_requests.append({
            "contents": [{
                "parts": [
                    {"text": TRANSCRIPTION_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": b64_data}},
                ],
                "role": "user",
            }]
        })

    doc.close()

    # Submit batch
    batch_job = client.batches.create(
        model=model,
        src=inline_requests,
        config={"display_name": pdf_path.name},
    )

    batch_id = batch_job.name

    # Record in database
    conn.execute("""
        INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
        VALUES (?, ?, ?, ?, 'submitted')
    """, (batch_id, rel, model, page_count))
    conn.commit()

    print(f"  Submitted: {rel} ({page_count} pages) -> {batch_id}")
    return batch_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gemini_batch.py::TestSubmitBatch -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/gemini_batch.py tests/test_gemini_batch.py
git commit -m "feat: add Gemini batch submission (submit_batch)

- Renders PDF pages to images, builds inline batch requests
- Submits to Gemini Batch API (client.batches.create)
- Records batch job in SQLite batches table
- Skips PDFs that are already submitted"
```

---

### Task 5: Batch module — check_status

**Files:**
- Modify: `scripts/gemini_batch.py`
- Modify: `tests/test_gemini_batch.py`

- [ ] **Step 1: Write failing tests for status checking**

Add to `tests/test_gemini_batch.py`:

```python
class TestCheckStatus:
    """Test batch job status checking."""

    def _insert_batch(self, conn, batch_id, pdf_path, status="submitted"):
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
            VALUES (?, ?, ?, ?, ?)
        """, (batch_id, pdf_path, "gemini-2.5-flash", 3, status))
        conn.commit()

    def test_updates_succeeded_status(self, tmp_path):
        conn = get_db(tmp_path)
        self._insert_batch(conn, "batches/b1", "letter.pdf")

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_client.batches.get.return_value = mock_job

        counts = check_status(mock_client, conn)

        cursor = conn.execute("SELECT status FROM batches WHERE batch_id = ?", ("batches/b1",))
        assert cursor.fetchone()["status"] == "succeeded"
        assert counts["succeeded"] == 1
        close_db(conn)

    def test_updates_failed_status(self, tmp_path):
        conn = get_db(tmp_path)
        self._insert_batch(conn, "batches/b2", "letter.pdf")

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_FAILED"
        mock_job.error = MagicMock(message="Rate limit exceeded")
        mock_client.batches.get.return_value = mock_job

        counts = check_status(mock_client, conn)

        cursor = conn.execute("SELECT status, error_message FROM batches WHERE batch_id = ?", ("batches/b2",))
        row = cursor.fetchone()
        assert row["status"] == "failed"
        assert "Rate limit" in row["error_message"]
        assert counts["failed"] == 1
        close_db(conn)

    def test_leaves_pending_as_submitted(self, tmp_path):
        conn = get_db(tmp_path)
        self._insert_batch(conn, "batches/b3", "letter.pdf")

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_RUNNING"
        mock_client.batches.get.return_value = mock_job

        counts = check_status(mock_client, conn)

        cursor = conn.execute("SELECT status FROM batches WHERE batch_id = ?", ("batches/b3",))
        assert cursor.fetchone()["status"] == "submitted"
        assert counts["pending"] == 1
        close_db(conn)

    def test_skips_already_collected(self, tmp_path):
        conn = get_db(tmp_path)
        self._insert_batch(conn, "batches/b4", "letter.pdf", status="collected")

        mock_client = MagicMock()
        counts = check_status(mock_client, conn)

        mock_client.batches.get.assert_not_called()
        close_db(conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gemini_batch.py::TestCheckStatus -v`
Expected: FAIL — `check_status` not defined

- [ ] **Step 3: Implement check_status**

Add to `scripts/gemini_batch.py`:

```python
# Gemini job state -> our status mapping
_STATE_MAP = {
    "JOB_STATE_SUCCEEDED": "succeeded",
    "JOB_STATE_FAILED": "failed",
    "JOB_STATE_EXPIRED": "expired",
    "JOB_STATE_CANCELLED": "cancelled",
}


def check_status(client, conn):
    """Check status of all pending batch jobs.

    Queries the batches table for submitted jobs, checks each with the
    Gemini API, and updates status in SQLite.

    Args:
        client: google.genai.Client instance.
        conn: SQLite connection.

    Returns:
        Dict with counts: {"pending": int, "succeeded": int, "failed": int, "expired": int}
    """
    cursor = conn.execute(
        "SELECT batch_id, pdf_path FROM batches WHERE status = 'submitted'"
    )
    pending_batches = cursor.fetchall()

    counts = {"pending": 0, "succeeded": 0, "failed": 0, "expired": 0, "cancelled": 0}

    for row in pending_batches:
        batch_id = row["batch_id"]
        pdf_path = row["pdf_path"]

        try:
            job = client.batches.get(name=batch_id)
            state_name = job.state.name
            new_status = _STATE_MAP.get(state_name)

            if new_status:
                error_msg = None
                if new_status == "failed" and hasattr(job, "error") and job.error:
                    error_msg = str(getattr(job.error, "message", job.error))

                conn.execute("""
                    UPDATE batches SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ?
                    WHERE batch_id = ?
                """, (new_status, error_msg, batch_id))
                conn.commit()
                counts[new_status] = counts.get(new_status, 0) + 1
                print(f"  {pdf_path}: {new_status}")
            else:
                counts["pending"] += 1
                print(f"  {pdf_path}: pending ({state_name})")

        except Exception as e:
            print(f"  {pdf_path}: error checking status ({e})")
            counts["pending"] += 1

    total = sum(counts.values())
    print(f"\nBatch status: {total} jobs — "
          f"{counts['pending']} pending, {counts['succeeded']} succeeded, "
          f"{counts['failed']} failed")

    return counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gemini_batch.py::TestCheckStatus -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/gemini_batch.py tests/test_gemini_batch.py
git commit -m "feat: add batch status checking (check_status)

- Queries Gemini API for pending batch job states
- Maps JOB_STATE_SUCCEEDED/FAILED/EXPIRED/CANCELLED to DB status
- Captures error messages for failed jobs
- Prints summary of pending/succeeded/failed counts"
```

---

### Task 6: Batch module — collect_results

**Files:**
- Modify: `scripts/gemini_batch.py`
- Modify: `tests/test_gemini_batch.py`

- [ ] **Step 1: Write failing tests for result collection**

Add to `tests/test_gemini_batch.py`:

```python
class TestCollectResults:
    """Test collecting batch results and writing transcripts."""

    def _insert_succeeded(self, conn, batch_id, pdf_path, page_count=2):
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
            VALUES (?, ?, ?, ?, 'succeeded')
        """, (batch_id, pdf_path, "gemini-2.5-flash", page_count))
        conn.commit()

    def test_collect_writes_transcript(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "Letters" / "letter.pdf", pages=2)
        conn = get_db(dest)
        self._insert_succeeded(conn, "batches/b1", "Letters/letter.pdf", 2)

        # Mock client with inline responses
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_response_1 = MagicMock()
        mock_response_1.response.text = "Page 1 transcribed text"
        mock_response_1.error = None
        mock_response_2 = MagicMock()
        mock_response_2.response.text = "Page 2 transcribed text"
        mock_response_2.error = None
        mock_job.dest.inlined_responses = [mock_response_1, mock_response_2]
        mock_client.batches.get.return_value = mock_job

        count = collect_results(mock_client, conn, dest)

        assert count == 1
        transcript = dest / "Letters" / "letter.transcript.md"
        assert transcript.exists()
        content = transcript.read_text(encoding="utf-8")
        assert "Page 1 transcribed text" in content
        assert "Page 2 transcribed text" in content
        close_db(conn)

    def test_collect_updates_status_to_collected(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_test_pdf(dest / "Letters" / "letter.pdf", pages=1)
        conn = get_db(dest)
        self._insert_succeeded(conn, "batches/b1", "Letters/letter.pdf", 1)

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_response = MagicMock()
        mock_response.response.text = "Transcribed content"
        mock_response.error = None
        mock_job.dest.inlined_responses = [mock_response]
        mock_client.batches.get.return_value = mock_job

        collect_results(mock_client, conn, dest)

        cursor = conn.execute("SELECT status FROM batches WHERE batch_id = ?", ("batches/b1",))
        assert cursor.fetchone()["status"] == "collected"
        close_db(conn)

    def test_collect_skips_non_succeeded(self, tmp_path):
        conn = get_db(tmp_path)
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, status)
            VALUES (?, ?, ?, ?, 'submitted')
        """, ("batches/b1", "letter.pdf", "gemini-2.5-flash", 1))
        conn.commit()

        mock_client = MagicMock()
        count = collect_results(mock_client, conn, tmp_path)

        assert count == 0
        mock_client.batches.get.assert_not_called()
        close_db(conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gemini_batch.py::TestCollectResults -v`
Expected: FAIL — `collect_results` not defined

- [ ] **Step 3: Implement collect_results**

Add to `scripts/gemini_batch.py`:

```python
def collect_results(client, conn, dest_root):
    """Collect results from succeeded batch jobs and write transcript files.

    For each succeeded batch, retrieves the per-page responses, assembles
    them in order, and creates the .transcript.md file using the same
    function as the real-time path.

    Args:
        client: google.genai.Client instance.
        conn: SQLite connection.
        dest_root: Archive root directory.

    Returns:
        Number of transcripts collected.
    """
    from transcribe_pdfs_gemini import create_transcript_md

    dest_root = Path(dest_root)
    cursor = conn.execute(
        "SELECT batch_id, pdf_path, model, page_count FROM batches WHERE status = 'succeeded'"
    )
    succeeded = cursor.fetchall()

    if not succeeded:
        print("No completed batch jobs to collect.")
        return 0

    collected = 0

    for row in succeeded:
        batch_id = row["batch_id"]
        pdf_path_rel = row["pdf_path"]
        model = row["model"]
        page_count = row["page_count"]
        pdf_path = dest_root / pdf_path_rel

        try:
            job = client.batches.get(name=batch_id)

            # Extract page texts from inline responses
            page_texts = []
            if job.dest and job.dest.inlined_responses:
                for resp in job.dest.inlined_responses:
                    if resp.error:
                        page_texts.append("[Page transcription failed]")
                    elif resp.response and resp.response.text:
                        page_texts.append(resp.response.text.strip())
                    else:
                        page_texts.append("[Page appears blank or illegible]")

            if not page_texts:
                print(f"  {pdf_path_rel}: no responses found")
                continue

            # Create transcript using the shared function
            md_path, confidence, word_count = create_transcript_md(
                pdf_path, page_texts, model, dest_root
            )

            # Mark as collected
            conn.execute("""
                UPDATE batches SET status = 'collected', completed_at = CURRENT_TIMESTAMP
                WHERE batch_id = ?
            """, (batch_id,))
            conn.commit()

            collected += 1
            print(f"  {pdf_path_rel}: {word_count} words, confidence={confidence}")

        except Exception as e:
            print(f"  {pdf_path_rel}: error collecting ({e})")

    print(f"\nCollected {collected} transcripts")
    return collected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gemini_batch.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/gemini_batch.py tests/test_gemini_batch.py
git commit -m "feat: add batch result collection (collect_results)

- Retrieves per-page responses from completed Gemini batch jobs
- Assembles pages and writes .transcript.md using shared create_transcript_md
- Updates batch status to 'collected' after successful transcript creation
- Handles per-page errors gracefully"
```

---

### Task 7: Cross-PDF parallelism and rate limiting in --fast mode

**Files:**
- Modify: `scripts/transcribe_pdfs_gemini.py`

- [ ] **Step 1: Add --fast flag and rate limiter integration**

In `scripts/transcribe_pdfs_gemini.py`, in the `main()` function:

Add `--fast` to the argument parser (after the existing `--dry-run` arg):

```python
    parser.add_argument("--fast", action="store_true",
                        help="Real-time transcription with cross-PDF parallelism (default is batch mode)")
```

After config is loaded (after `config = load_config(args.config)`), create the rate limiter:

```python
    from rate_limiter import RateLimiter
    rpm = config.get("requests_per_minute", 400)
    limiter = RateLimiter(requests_per_minute=rpm)
```

- [ ] **Step 2: Add rate limiter to page transcription**

Modify the `process_page` inner function (around line 377) to acquire a rate limit token before each API call. Change:

```python
            def process_page(page_num):
                return page_num, transcribe_page_gemini(client, args.model, page_images[page_num])
```

To:

```python
            def process_page(page_num):
                limiter.acquire()
                return page_num, transcribe_page_gemini(client, args.model, page_images[page_num])
```

Note: `limiter` is captured from the enclosing scope.

- [ ] **Step 3: Wrap the PDF loop in cross-PDF parallelism for --fast mode**

Refactor the existing for loop (`for i, pdf in enumerate(pdfs, 1):`) into a function `process_single_pdf(pdf, index, total, client, model, dpi, dest_root, limiter)` that contains the existing per-PDF processing logic (lines ~352-430). Then in `main()`:

For `--fast` mode, use `ThreadPoolExecutor` with `parallel_workers` from config:

```python
    if args.fast or not hasattr(args, 'fast'):
        # Real-time mode (--fast or legacy behavior)
        workers = config.get("parallel_workers", 10)
        if len(pdfs) == 1:
            workers = 1

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    process_single_pdf, pdf, i, len(pdfs),
                    client, args.model, args.dpi, dest_root, limiter
                ): pdf
                for i, pdf in enumerate(pdfs, 1)
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                    if result["status"] == "ok":
                        confidence_counts[result["confidence"]] += 1
```

- [ ] **Step 4: Run existing tests**

Run: `python -m pytest tests/ --tb=short`
Expected: All PASS (no tests call `main()` directly, so the refactor is safe)

- [ ] **Step 5: Commit**

```bash
git add scripts/transcribe_pdfs_gemini.py
git commit -m "feat: add cross-PDF parallelism and rate limiting for --fast mode

- --fast flag for real-time transcription with cross-PDF concurrency
- Shared RateLimiter governs total API calls across all threads
- parallel_workers config controls cross-PDF concurrency (default 10)
- Refactored per-PDF processing into process_single_pdf function"
```

---

### Task 8: Batch mode as default in transcribe CLI

**Files:**
- Modify: `scripts/transcribe_pdfs_gemini.py`
- Modify: `scripts/cli.py`

- [ ] **Step 1: Add --status and --collect flags**

In `scripts/transcribe_pdfs_gemini.py`, add to the argument parser:

```python
    parser.add_argument("--status", action="store_true",
                        help="Check status of pending batch jobs")
    parser.add_argument("--collect", action="store_true",
                        help="Collect results from completed batch jobs")
```

- [ ] **Step 2: Add batch dispatch logic to main()**

After the dry-run check and before the "Initialize Gemini client" section, add batch routing:

```python
    # Initialize Gemini client (needed for all non-dry-run modes)
    from google import genai
    client = genai.Client(api_key=api_key)

    # Handle --status
    if args.status:
        from gemini_batch import check_status
        from db import get_db, close_db
        conn = get_db(dest_root)
        check_status(client, conn)
        close_db(conn)
        return

    # Handle --collect
    if args.collect:
        from gemini_batch import collect_results
        from db import get_db, close_db
        conn = get_db(dest_root)
        collect_results(client, conn, dest_root)
        close_db(conn)
        return

    # Default: batch mode (unless --fast)
    if not args.fast:
        from gemini_batch import submit_batch
        from db import get_db, close_db
        conn = get_db(dest_root)
        print(f"\nSubmitting {len(pdfs)} PDFs for batch transcription...")
        print(f"Model: {args.model} (50% batch discount)")
        submitted = 0
        for pdf in pdfs:
            rel = pdf.relative_to(dest_root) if pdf.is_relative_to(dest_root) else pdf
            result = submit_batch(client, args.model, pdf, dest_root, conn, dpi=args.dpi)
            if result:
                submitted += 1
        close_db(conn)
        print(f"\nSubmitted {submitted} batch jobs.")
        print("Check status:    family-archive transcribe --status")
        print("Collect results: family-archive transcribe --collect")
        return
```

Move the existing real-time processing code to run only when `args.fast` is set.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/transcribe_pdfs_gemini.py scripts/cli.py
git commit -m "feat: make batch mode the default for transcription

- family-archive transcribe submits batch jobs by default (50% cost savings)
- --fast flag for real-time cross-PDF parallelism
- --status checks pending batch jobs
- --collect retrieves completed results and writes transcripts
- Batch submit -> status -> collect workflow"
```

---

### Task 9: Update docs

**Files:**
- Modify: `docs/WORKFLOW.md`

- [ ] **Step 1: Update transcription section in WORKFLOW.md**

Find the existing "2. Transcribe PDFs" section and update it to include batch workflow:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/WORKFLOW.md
git commit -m "docs: update workflow with batch transcription commands

- Batch mode as default with submit/status/collect workflow
- --fast for real-time transcription
- Updated cost guidance (batch = 50% savings)"
```

---

### Task 10: Integration test

**Files:**
- Modify: `tests/test_gemini_batch.py`

- [ ] **Step 1: Write end-to-end integration test**

Add to `tests/test_gemini_batch.py`:

```python
class TestEndToEnd:
    """End-to-end integration test for the batch workflow."""

    def test_submit_check_collect_workflow(self, tmp_path):
        """Submit -> check status -> collect results."""
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "Letters" / "letter.pdf", pages=2)
        conn = get_db(dest)

        # Step 1: Submit
        mock_client = MagicMock()
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/test-e2e"
        mock_client.batches.create.return_value = mock_batch_job

        batch_id = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)
        assert batch_id == "batches/test-e2e"

        # Verify submitted in DB
        cursor = conn.execute("SELECT status FROM batches WHERE batch_id = ?", (batch_id,))
        assert cursor.fetchone()["status"] == "submitted"

        # Step 2: Check status (simulate succeeded)
        mock_succeeded_job = MagicMock()
        mock_succeeded_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_client.batches.get.return_value = mock_succeeded_job

        counts = check_status(mock_client, conn)
        assert counts["succeeded"] == 1

        cursor = conn.execute("SELECT status FROM batches WHERE batch_id = ?", (batch_id,))
        assert cursor.fetchone()["status"] == "succeeded"

        # Step 3: Collect results
        mock_result_job = MagicMock()
        resp1 = MagicMock()
        resp1.response.text = "Dear Alice, page one text"
        resp1.error = None
        resp2 = MagicMock()
        resp2.response.text = "Page two text, love Bob"
        resp2.error = None
        mock_result_job.dest.inlined_responses = [resp1, resp2]
        mock_client.batches.get.return_value = mock_result_job

        collected = collect_results(mock_client, conn, dest)
        assert collected == 1

        # Verify transcript exists
        transcript = dest / "Letters" / "letter.transcript.md"
        assert transcript.exists()
        content = transcript.read_text(encoding="utf-8")
        assert "Dear Alice" in content
        assert "love Bob" in content

        # Verify status is collected
        cursor = conn.execute("SELECT status FROM batches WHERE batch_id = ?", (batch_id,))
        assert cursor.fetchone()["status"] == "collected"

        close_db(conn)
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/test_gemini_batch.py -v`
Expected: All PASS

Run: `python -m pytest --tb=short`
Expected: Full suite PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gemini_batch.py
git commit -m "test: add end-to-end integration test for batch workflow

- Tests full lifecycle: submit -> check status -> collect results
- Verifies transcript file is created with correct content
- Verifies batch status transitions through submitted -> succeeded -> collected"
```
