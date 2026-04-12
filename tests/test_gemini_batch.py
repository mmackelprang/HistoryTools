"""
Tests for the Gemini batch processing module (scripts/gemini_batch.py).

All tests mock the Gemini API — no real API calls are made.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.db import get_db, close_db
from scripts.gemini_batch import submit_batch, check_status


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
