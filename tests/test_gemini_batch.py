"""
Tests for the Gemini batch processing module (scripts/gemini_batch.py).

All tests mock the Gemini API — no real API calls are made.
"""

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

        batch_ids = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)

        assert batch_ids == ["batches/batch-test-123"]
        cursor = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_ids[0],))
        row = cursor.fetchone()
        assert row is not None
        assert row["pdf_path"] == "Letters/letter.pdf"
        assert row["status"] == "submitted"
        assert row["page_count"] == 2
        assert row["page_start"] == 0
        assert row["chunk_pages"] == 2
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


class TestChunking:
    """Test automatic chunking of large PDFs."""

    def test_small_pdf_single_chunk(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "letter.pdf", pages=2)
        conn = get_db(dest)

        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "batches/single"
        mock_client.batches.create.return_value = mock_job

        batch_ids = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)

        assert len(batch_ids) == 1
        mock_client.batches.create.assert_called_once()
        close_db(conn)

    @patch("scripts.gemini_batch._CHUNK_SIZE_LIMIT", 500)
    def test_large_pdf_multiple_chunks(self, tmp_path):
        """With a tiny chunk limit, even small pages should split into chunks."""
        dest = tmp_path / "archive"
        dest.mkdir()
        pdf = make_test_pdf(dest / "letter.pdf", pages=5)
        conn = get_db(dest)

        mock_client = MagicMock()
        call_count = 0

        def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            job = MagicMock()
            job.name = f"batches/chunk-{call_count}"
            return job

        mock_client.batches.create.side_effect = mock_create

        batch_ids = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)

        assert len(batch_ids) > 1  # should be split into multiple chunks
        assert mock_client.batches.create.call_count == len(batch_ids)

        # Verify all chunks are in the DB with correct page_start values
        cursor = conn.execute(
            "SELECT page_start, chunk_pages FROM batches WHERE pdf_path = ? ORDER BY page_start",
            ("letter.pdf",)
        )
        rows = cursor.fetchall()
        assert len(rows) == len(batch_ids)
        assert rows[0]["page_start"] == 0  # first chunk starts at 0
        # All chunks should cover all 5 pages
        total_chunk_pages = sum(r["chunk_pages"] for r in rows)
        assert total_chunk_pages == 5
        close_db(conn)

    @patch("scripts.gemini_batch._CHUNK_SIZE_LIMIT", 500)
    def test_collect_multi_chunk_reassembles_pages(self, tmp_path):
        """Test that collect_results reassembles pages from multiple chunks."""
        dest = tmp_path / "archive"
        dest.mkdir()
        make_test_pdf(dest / "letter.pdf", pages=4)
        conn = get_db(dest)

        # Simulate two chunks: pages 0-1 and pages 2-3
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, page_start, chunk_pages, status)
            VALUES (?, ?, ?, ?, ?, ?, 'succeeded')
        """, ("batches/c1", "letter.pdf", "gemini-2.5-flash", 4, 0, 2))
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, page_start, chunk_pages, status)
            VALUES (?, ?, ?, ?, ?, ?, 'succeeded')
        """, ("batches/c2", "letter.pdf", "gemini-2.5-flash", 4, 2, 2))
        conn.commit()

        mock_client = MagicMock()

        def mock_get(name):
            job = MagicMock()
            if name == "batches/c1":
                r1 = MagicMock()
                r1.response.text = "Page one text"
                r1.error = None
                r2 = MagicMock()
                r2.response.text = "Page two text"
                r2.error = None
                job.dest.inlined_responses = [r1, r2]
            elif name == "batches/c2":
                r3 = MagicMock()
                r3.response.text = "Page three text"
                r3.error = None
                r4 = MagicMock()
                r4.response.text = "Page four text"
                r4.error = None
                job.dest.inlined_responses = [r3, r4]
            return job

        mock_client.batches.get.side_effect = mock_get

        count = collect_results(mock_client, conn, dest)
        assert count == 1

        transcript = dest / "letter.transcript.md"
        assert transcript.exists()
        content = transcript.read_text(encoding="utf-8")
        # Verify all pages are present in order
        assert "Page one text" in content
        assert "Page two text" in content
        assert "Page three text" in content
        assert "Page four text" in content
        # Verify page ordering (page one before page four)
        assert content.index("Page one") < content.index("Page four")

        # Both chunks marked as collected
        cursor = conn.execute("SELECT status FROM batches WHERE pdf_path = 'letter.pdf'")
        for row in cursor.fetchall():
            assert row["status"] == "collected"
        close_db(conn)

    @patch("scripts.gemini_batch._CHUNK_SIZE_LIMIT", 500)
    def test_collect_waits_for_all_chunks(self, tmp_path):
        """Don't collect until all chunks have succeeded."""
        dest = tmp_path / "archive"
        dest.mkdir()
        make_test_pdf(dest / "letter.pdf", pages=4)
        conn = get_db(dest)

        # Chunk 1 succeeded, chunk 2 still submitted
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, page_start, chunk_pages, status)
            VALUES (?, ?, ?, ?, ?, ?, 'succeeded')
        """, ("batches/c1", "letter.pdf", "gemini-2.5-flash", 4, 0, 2))
        conn.execute("""
            INSERT INTO batches (batch_id, pdf_path, model, page_count, page_start, chunk_pages, status)
            VALUES (?, ?, ?, ?, ?, ?, 'submitted')
        """, ("batches/c2", "letter.pdf", "gemini-2.5-flash", 4, 2, 2))
        conn.commit()

        mock_client = MagicMock()
        count = collect_results(mock_client, conn, dest)

        assert count == 0  # should not collect — chunk 2 still pending
        assert not (dest / "letter.transcript.md").exists()
        close_db(conn)


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

        batch_ids = submit_batch(mock_client, "gemini-2.5-flash", pdf, dest, conn)
        assert batch_ids == ["batches/test-e2e"]
        batch_id = batch_ids[0]

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
