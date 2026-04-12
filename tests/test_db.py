"""
Tests for the SQLite index module (scripts/db.py).
"""

from pathlib import Path

import pytest

import sqlite3

from scripts.db import (
    get_db,
    init_schema,
    close_db,
    index_file,
    index_transcript,
    reindex_all,
    check_index,
    search,
    get_stats,
    update_file_index,
    update_transcript_index,
    parse_frontmatter,
    _get_file_type,
    _get_date_prefix,
    _parse_folder_subfolder,
)


# ── Helpers ────────────────────────────────────────────────────────────────

SAMPLE_TRANSCRIPT = """\
---
source_file: 1984-03-15_letter.pdf
transcription_confidence: high
transcription_method: ai-vision (gemini-2.5-flash)
word_count: 42
formatting: cleaned
transcription_date: 2026-04-10
---

Dear Alice,

We drove to Springfield last week and visited the old house on Maple Street.
The garden was beautiful. Hope you are doing well.

Love, Bob
"""

SAMPLE_TRANSCRIPT_LOW = """\
---
source_file: undated_note.pdf
transcription_confidence: low
transcription_method: ocr
word_count: 15
transcription_date: 2026-04-09
---

Some short note text that is hard to read.
"""

SAMPLE_TRANSCRIPT_AUDIO = """\
---
source_file: 1984-06-14_tape.mp3
transcription_confidence: medium
transcription_method: assemblyai
word_count: 100
transcription_date: 2026-04-08
---

**Speaker A** (00:00): When we went to Springfield that time, it was really something.
We spent the whole afternoon at the park.

**Speaker B** (01:23): I remember that. The weather was perfect.
"""


def make_file(path: Path, content: str = "test content") -> Path:
    """Create a file with given content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ── Schema tests ───────────────────────────────────────────────────────────


class TestSchema:
    """Test schema creation."""

    def test_init_schema_creates_all_tables(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = sorted(row["name"] for row in cursor.fetchall())
        close_db(conn)

        assert "files" in tables
        assert "transcripts" in tables
        assert "transcripts_content" in tables
        assert "transcripts_fts" in tables

    def test_init_schema_idempotent(self, tmp_path):
        conn = get_db(tmp_path)
        # Call init_schema again — should not raise
        init_schema(conn)
        init_schema(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_schema_version_set(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        close_db(conn)
        assert version == 2

    def test_db_created_at_dest_root(self, tmp_path):
        conn = get_db(tmp_path)
        close_db(conn)
        assert (tmp_path / ".archive.db").exists()

    def test_db_custom_path(self, tmp_path):
        custom_path = tmp_path / "custom" / "my.db"
        config = {"db_path": str(custom_path)}
        conn = get_db(tmp_path, config)
        close_db(conn)
        assert custom_path.exists()


# ── File type helpers ──────────────────────────────────────────────────────


class TestFileTypeHelpers:
    """Test internal helper functions."""

    def test_get_file_type_document(self):
        assert _get_file_type("letter.pdf") == "document"
        assert _get_file_type("notes.txt") == "document"

    def test_get_file_type_audio(self):
        assert _get_file_type("tape.mp3") == "audio"
        assert _get_file_type("recording.wav") == "audio"

    def test_get_file_type_photo(self):
        assert _get_file_type("photo.jpg") == "photo"
        assert _get_file_type("image.png") == "photo"

    def test_get_file_type_video(self):
        assert _get_file_type("clip.mp4") == "video"

    def test_get_file_type_transcript(self):
        assert _get_file_type("letter.transcript.md") == "transcript"

    def test_get_file_type_unknown(self):
        assert _get_file_type("file.xyz") == "unknown"

    def test_get_file_type_plain_md_is_document(self):
        assert _get_file_type("readme.md") == "document"  # .md (not .transcript.md) = document

    def test_get_date_prefix_dated(self):
        assert _get_date_prefix("1984-03-15_letter.pdf") == "1984-03-15"

    def test_get_date_prefix_undated(self):
        assert _get_date_prefix("undated_note.pdf") == "undated"

    def test_get_date_prefix_none(self):
        assert _get_date_prefix("letter.pdf") is None

    def test_parse_folder_subfolder(self):
        folder, subfolder = _parse_folder_subfolder("Letters/1984/letter.pdf")
        assert folder == "Letters"
        assert subfolder == "1984"

    def test_parse_folder_subfolder_no_subfolder(self):
        folder, subfolder = _parse_folder_subfolder("Letters/letter.pdf")
        assert folder == "Letters"
        assert subfolder is None

    def test_parse_folder_subfolder_root_file(self):
        folder, subfolder = _parse_folder_subfolder("letter.pdf")
        assert folder == ""
        assert subfolder is None


# ── Frontmatter parsing ───────────────────────────────────────────────────


class TestParseFrontmatter:
    """Test frontmatter parsing."""

    def test_parse_standard_frontmatter(self):
        fm, body = parse_frontmatter(SAMPLE_TRANSCRIPT)
        assert fm["source_file"] == "1984-03-15_letter.pdf"
        assert fm["transcription_confidence"] == "high"
        assert fm["word_count"] == "42"
        assert "Springfield" in body

    def test_parse_no_frontmatter(self):
        fm, body = parse_frontmatter("Just some text without frontmatter.")
        assert fm == {}
        assert body == "Just some text without frontmatter."

    def test_parse_empty_content(self):
        fm, body = parse_frontmatter("")
        assert fm == {}
        assert body == ""


# ── index_file tests ──────────────────────────────────────────────────────


class TestIndexFile:
    """Test indexing individual files."""

    def test_index_file_basic(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "1984" / "1984-03-15_letter.pdf", "PDF content")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        cursor = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        close_db(conn)

        assert row["path"] == "Letters/1984/1984-03-15_letter.pdf"
        assert row["filename"] == "1984-03-15_letter.pdf"
        assert row["folder"] == "Letters"
        assert row["subfolder"] == "1984"
        assert row["file_type"] == "document"
        assert row["date_prefix"] == "1984-03-15"
        assert row["size_bytes"] > 0
        assert row["md5_hash"] is not None

    def test_index_file_updates_on_reindex(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "letter.pdf", "v1")

        conn = get_db(dest)
        id1 = index_file(conn, dest, fpath)

        # Update file content and reindex
        fpath.write_text("v2 with more content", encoding="utf-8")
        id2 = index_file(conn, dest, fpath)

        # Should be same row (upsert)
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
        assert cursor.fetchone()["cnt"] == 1

        cursor = conn.execute("SELECT size_bytes FROM files WHERE id = ?", (id2,))
        row = cursor.fetchone()
        assert row["size_bytes"] == len("v2 with more content")
        close_db(conn)

    def test_index_file_undated(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "undated_note.pdf", "content")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        cursor = conn.execute("SELECT date_prefix FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        close_db(conn)

        assert row["date_prefix"] == "undated"

    def test_index_file_no_date_prefix(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Photos" / "sunset.jpg", "\x00")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        cursor = conn.execute("SELECT date_prefix FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        close_db(conn)

        assert row["date_prefix"] is None

    def test_index_file_audio(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Audio" / "1984-06-14_tape.mp3", "\x00")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        cursor = conn.execute("SELECT file_type, date_prefix FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        close_db(conn)

        assert row["file_type"] == "audio"
        assert row["date_prefix"] == "1984-06-14"


# ── index_transcript tests ────────────────────────────────────────────────


class TestIndexTranscript:
    """Test indexing transcript files."""

    def test_index_transcript_parses_frontmatter(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        tpath = make_file(
            dest / "Letters" / "1984" / "1984-03-15_letter.transcript.md",
            SAMPLE_TRANSCRIPT,
        )

        conn = get_db(dest)
        index_transcript(conn, dest, tpath)

        # Check transcripts table
        cursor = conn.execute("""
            SELECT t.* FROM transcripts t
            JOIN files f ON f.id = t.file_id
            WHERE f.path = ?
        """, ("Letters/1984/1984-03-15_letter.transcript.md",))
        row = cursor.fetchone()
        close_db(conn)

        assert row is not None
        assert row["confidence"] == "high"
        assert row["method"] == "ai-vision (gemini-2.5-flash)"
        assert row["word_count"] == 42
        assert row["formatting"] == "cleaned"
        assert row["transcription_date"] == "2026-04-10"

    def test_index_transcript_body_in_fts(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        tpath = make_file(
            dest / "Letters" / "1984-03-15_letter.transcript.md",
            SAMPLE_TRANSCRIPT,
        )

        conn = get_db(dest)
        index_transcript(conn, dest, tpath)

        # Check FTS content
        cursor = conn.execute(
            "SELECT * FROM transcripts_content WHERE path = ?",
            ("Letters/1984-03-15_letter.transcript.md",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert "Springfield" in row["body"]
        close_db(conn)

    def test_index_transcript_updates_on_reindex(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        tpath = make_file(
            dest / "Letters" / "letter.transcript.md",
            SAMPLE_TRANSCRIPT,
        )

        conn = get_db(dest)
        index_transcript(conn, dest, tpath)

        # Update transcript
        tpath.write_text(SAMPLE_TRANSCRIPT_LOW, encoding="utf-8")
        index_transcript(conn, dest, tpath)

        # Should still be one entry
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM transcripts")
        assert cursor.fetchone()["cnt"] == 1

        cursor = conn.execute("""
            SELECT t.confidence FROM transcripts t
            JOIN files f ON f.id = t.file_id
            WHERE f.path = ?
        """, ("Letters/letter.transcript.md",))
        row = cursor.fetchone()
        assert row["confidence"] == "low"
        close_db(conn)


# ── reindex_all tests ─────────────────────────────────────────────────────


class TestReindexAll:
    """Test full reindexing."""

    def test_reindex_indexes_all_files(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "1984" / "letter.pdf", "pdf")
        make_file(dest / "Photos" / "photo.jpg", "\x00")
        make_file(dest / "Audio" / "tape.mp3", "\x00")

        conn = get_db(dest)
        reindex_all(conn, dest)

        cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
        assert cursor.fetchone()["cnt"] == 3
        close_db(conn)

    def test_reindex_indexes_transcripts(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "letter.pdf", "pdf")
        make_file(dest / "Letters" / "letter.transcript.md", SAMPLE_TRANSCRIPT)

        conn = get_db(dest)
        reindex_all(conn, dest)

        cursor = conn.execute("SELECT COUNT(*) as cnt FROM transcripts")
        assert cursor.fetchone()["cnt"] == 1
        close_db(conn)

    def test_reindex_removes_orphans(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "letter.pdf", "pdf")

        conn = get_db(dest)
        index_file(conn, dest, fpath)

        # Verify it's in the DB
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
        assert cursor.fetchone()["cnt"] == 1

        # Delete the file from disk
        fpath.unlink()

        # Reindex should remove the orphan
        reindex_all(conn, dest)

        cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
        assert cursor.fetchone()["cnt"] == 0
        close_db(conn)

    def test_reindex_empty_directory(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()

        conn = get_db(dest)
        reindex_all(conn, dest)

        cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
        # .archive.db is in dest but os.walk skips dotfiles via dir filter
        # Actually files in root are indexed if they aren't in skip dirs
        count = cursor.fetchone()["cnt"]
        assert count == 0  # empty dir, .archive.db is hidden (starts with .)
        close_db(conn)


# ── check_index tests ─────────────────────────────────────────────────────


class TestCheckIndex:
    """Test index checking."""

    def test_check_up_to_date(self, tmp_path, capsys):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "letter.pdf", "pdf")

        conn = get_db(dest)
        reindex_all(conn, dest)
        check_index(conn, dest)
        close_db(conn)

        captured = capsys.readouterr()
        assert "up to date" in captured.out

    def test_check_missing_files(self, tmp_path, capsys):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "letter.pdf", "pdf")

        conn = get_db(dest)
        # Don't index — DB is empty but file exists
        check_index(conn, dest)
        close_db(conn)

        captured = capsys.readouterr()
        assert "Missing" in captured.out


# ── search tests ──────────────────────────────────────────────────────────


class TestSearch:
    """Test full-text search."""

    def _setup_archive(self, dest):
        """Create a test archive with multiple transcripts."""
        make_file(
            dest / "Letters" / "1984" / "1984-03-15_letter.transcript.md",
            SAMPLE_TRANSCRIPT,
        )
        make_file(
            dest / "Letters" / "1983" / "undated_note.transcript.md",
            SAMPLE_TRANSCRIPT_LOW,
        )
        make_file(
            dest / "Audio" / "1984-06-14_tape.transcript.md",
            SAMPLE_TRANSCRIPT_AUDIO,
        )

        conn = get_db(dest)
        reindex_all(conn, dest)
        return conn

    def test_search_finds_match(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield")
        close_db(conn)

        assert len(results) >= 1
        paths = [r["path"] for r in results]
        assert any("letter" in p for p in paths)

    def test_search_returns_snippet(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield")
        close_db(conn)

        assert len(results) >= 1
        assert results[0]["snippet"]  # non-empty snippet

    def test_search_folder_filter(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield", folder="Audio")
        close_db(conn)

        for r in results:
            assert r["folder"] == "Audio"

    def test_search_type_filter(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield", file_type="transcript")
        close_db(conn)

        for r in results:
            assert r["file_type"] == "transcript"

    def test_search_year_filter(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield", year="1984")
        close_db(conn)

        for r in results:
            assert r["date_prefix"].startswith("1984")

    def test_search_limit(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield", limit=1)
        close_db(conn)

        assert len(results) <= 1

    def test_search_no_matches(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "xyznonexistent")
        close_db(conn)

        assert results == []

    def test_search_empty_query(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "")
        close_db(conn)

        assert results == []

    def test_search_result_fields(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = self._setup_archive(dest)

        results = search(conn, "Springfield")
        close_db(conn)

        assert len(results) >= 1
        r = results[0]
        assert "path" in r
        assert "snippet" in r
        assert "date_prefix" in r
        assert "word_count" in r
        assert "file_type" in r


# ── get_stats tests ───────────────────────────────────────────────────────


class TestGetStats:
    """Test statistics retrieval."""

    def test_stats_correct_counts(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "letter.pdf", "pdf")
        make_file(dest / "Photos" / "photo.jpg", "\x00")
        make_file(dest / "Letters" / "letter.transcript.md", SAMPLE_TRANSCRIPT)

        conn = get_db(dest)
        reindex_all(conn, dest)
        stats = get_stats(conn)
        close_db(conn)

        assert stats["total_files"] == 3  # pdf + jpg + transcript.md
        assert stats["total_transcripts"] == 1
        assert "document" in stats["files_by_type"]
        assert "photo" in stats["files_by_type"]

    def test_stats_word_totals(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "letter.transcript.md", SAMPLE_TRANSCRIPT)
        make_file(dest / "Audio" / "tape.transcript.md", SAMPLE_TRANSCRIPT_AUDIO)

        conn = get_db(dest)
        reindex_all(conn, dest)
        stats = get_stats(conn)
        close_db(conn)

        # Both transcripts have word_count in frontmatter (42 + 100)
        assert stats["total_words"] == 142

    def test_stats_confidence_breakdown(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.transcript.md", SAMPLE_TRANSCRIPT)
        make_file(dest / "Letters" / "b.transcript.md", SAMPLE_TRANSCRIPT_LOW)

        conn = get_db(dest)
        reindex_all(conn, dest)
        stats = get_stats(conn)
        close_db(conn)

        assert "high" in stats["transcripts_by_confidence"]
        assert "low" in stats["transcripts_by_confidence"]

    def test_stats_empty_archive(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()

        conn = get_db(dest)
        stats = get_stats(conn)
        close_db(conn)

        assert stats["total_files"] == 0
        assert stats["total_transcripts"] == 0
        assert stats["total_words"] == 0

    def test_stats_last_indexed(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "letter.pdf", "pdf")

        conn = get_db(dest)
        reindex_all(conn, dest)
        stats = get_stats(conn)
        close_db(conn)

        assert stats["last_indexed"] is not None


# ── Convenience function tests ────────────────────────────────────────────


class TestConvenienceFunctions:
    """Test update_file_index and update_transcript_index."""

    def test_update_file_index(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "letter.pdf", "pdf content")

        update_file_index(dest, fpath)

        # Verify by opening DB directly
        conn = get_db(dest)
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
        assert cursor.fetchone()["cnt"] == 1
        close_db(conn)

    def test_update_transcript_index(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        tpath = make_file(
            dest / "Letters" / "letter.transcript.md",
            SAMPLE_TRANSCRIPT,
        )

        update_transcript_index(dest, tpath)

        # Verify by opening DB directly
        conn = get_db(dest)
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM transcripts")
        assert cursor.fetchone()["cnt"] == 1

        cursor = conn.execute("SELECT COUNT(*) as cnt FROM transcripts_content")
        assert cursor.fetchone()["cnt"] == 1
        close_db(conn)

    def test_update_file_index_opens_and_closes_db(self, tmp_path):
        """Verify the convenience function opens and closes without leaving connections open."""
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "letter.pdf", "pdf")

        # Should not raise
        update_file_index(dest, fpath)
        update_file_index(dest, fpath)  # second call also works

    def test_update_transcript_index_opens_and_closes_db(self, tmp_path):
        """Verify the convenience function opens and closes without leaving connections open."""
        dest = tmp_path / "archive"
        dest.mkdir()
        tpath = make_file(
            dest / "Letters" / "letter.transcript.md",
            SAMPLE_TRANSCRIPT,
        )

        # Should not raise
        update_transcript_index(dest, tpath)
        update_transcript_index(dest, tpath)  # second call also works


# ── Schema v2 tests ───────────────────────────────────────────────────────


class TestSchemaV2:
    """Test schema v2 tables: provenance, fingerprints, quarantine."""

    def test_provenance_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provenance'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_fingerprints_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fingerprints'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_quarantine_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='quarantine'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_schema_version_is_2(self, tmp_path):
        conn = get_db(tmp_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        close_db(conn)
        assert version == 2

    def test_provenance_insert(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "letter.pdf", "content")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        conn.execute("""
            INSERT INTO provenance (file_id, source_path, source_hash, operation, detail)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, "originals/letter.pdf", "abc123", "ingest", "initial import"))
        conn.commit()

        cursor = conn.execute("SELECT * FROM provenance WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        close_db(conn)

        assert row is not None
        assert row["file_id"] == file_id
        assert row["source_path"] == "originals/letter.pdf"
        assert row["source_hash"] == "abc123"
        assert row["operation"] == "ingest"
        assert row["detail"] == "initial import"
        assert row["parent_file_id"] is None
        assert row["created_at"] is not None

    def test_provenance_parent_child(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        parent_path = make_file(dest / "Docs" / "parent.pdf", "parent content")
        child_path = make_file(dest / "Docs" / "child.pdf", "child content")

        conn = get_db(dest)
        parent_id = index_file(conn, dest, parent_path)
        child_id = index_file(conn, dest, child_path)

        conn.execute("""
            INSERT INTO provenance (file_id, parent_file_id, operation, detail)
            VALUES (?, ?, ?, ?)
        """, (child_id, parent_id, "split", "page 1 of parent"))
        conn.commit()

        cursor = conn.execute(
            "SELECT * FROM provenance WHERE file_id = ?", (child_id,)
        )
        row = cursor.fetchone()
        close_db(conn)

        assert row is not None
        assert row["file_id"] == child_id
        assert row["parent_file_id"] == parent_id
        assert row["operation"] == "split"

    def test_fingerprints_insert(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Photos" / "photo.jpg", "\x00")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        conn.execute("""
            INSERT INTO fingerprints (file_id, hash_type, hash_value, page_number)
            VALUES (?, ?, ?, ?)
        """, (file_id, "phash", "f0f0f0f0a1a1a1a1", 1))
        conn.commit()

        cursor = conn.execute(
            "SELECT * FROM fingerprints WHERE file_id = ?", (file_id,)
        )
        row = cursor.fetchone()
        close_db(conn)

        assert row is not None
        assert row["file_id"] == file_id
        assert row["hash_type"] == "phash"
        assert row["hash_value"] == "f0f0f0f0a1a1a1a1"
        assert row["page_number"] == 1
        assert row["computed_at"] is not None

    def test_fingerprints_unique_constraint(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Photos" / "photo.jpg", "\x00")

        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)

        conn.execute("""
            INSERT INTO fingerprints (file_id, hash_type, hash_value, page_number)
            VALUES (?, ?, ?, ?)
        """, (file_id, "phash", "aabbccdd11223344", 1))
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO fingerprints (file_id, hash_type, hash_value, page_number)
                VALUES (?, ?, ?, ?)
            """, (file_id, "phash", "differenthashvalue", 1))
            conn.commit()

        close_db(conn)

    def test_quarantine_insert(self, tmp_path):
        conn = get_db(tmp_path)

        conn.execute("""
            INSERT INTO quarantine (
                original_path, quarantine_path, duplicate_of, reason,
                purge_after, file_hash, file_size
            ) VALUES (?, ?, ?, ?, datetime('now', '+30 days'), ?, ?)
        """, (
            "Letters/duplicate.pdf",
            ".quarantine/2026-04-11_duplicate.pdf",
            "Letters/original.pdf",
            "exact_duplicate",
            "deadbeef12345678",
            4096,
        ))
        conn.commit()

        cursor = conn.execute("SELECT * FROM quarantine WHERE original_path = ?",
                              ("Letters/duplicate.pdf",))
        row = cursor.fetchone()
        close_db(conn)

        assert row is not None
        assert row["original_path"] == "Letters/duplicate.pdf"
        assert row["quarantine_path"] == ".quarantine/2026-04-11_duplicate.pdf"
        assert row["duplicate_of"] == "Letters/original.pdf"
        assert row["reason"] == "exact_duplicate"
        assert row["file_hash"] == "deadbeef12345678"
        assert row["file_size"] == 4096
        assert row["purge_after"] is not None
        assert row["quarantined_at"] is not None

    def test_v1_db_upgrades_to_v2(self, tmp_path):
        """A v1 database (files table only, user_version=1) upgrades to v2 seamlessly."""
        db_path = tmp_path / ".archive.db"

        # Manually create a v1 database
        v1_conn = sqlite3.connect(str(db_path))
        v1_conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                folder TEXT NOT NULL,
                subfolder TEXT,
                file_type TEXT,
                size_bytes INTEGER,
                date_prefix TEXT,
                md5_hash TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            PRAGMA user_version = 1;
        """)
        v1_conn.commit()
        v1_conn.close()

        # Open with get_db — should upgrade to v2
        conn = get_db(tmp_path)

        # Verify version is now 2
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 2

        # Verify all v2 tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        assert "provenance" in tables
        assert "fingerprints" in tables
        assert "quarantine" in tables

        # Verify the original files table still exists
        assert "files" in tables

        close_db(conn)
