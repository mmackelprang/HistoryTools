"""
Tests for the duplicate detection module (scripts/duplicate_detect.py).
"""

from pathlib import Path
import pytest
from scripts.db import get_db, close_db, index_file, index_transcript
from scripts.duplicate_detect import find_exact_duplicates, find_text_similar


TRANSCRIPT_A = """\
---
source_file: letter.pdf
transcription_confidence: high
word_count: 20
---

Dear Alice, we drove to Springfield last week and visited the old house on Maple Street.
"""

TRANSCRIPT_B_SIMILAR = """\
---
source_file: letter-copy.pdf
transcription_confidence: medium
word_count: 20
---

Dear Alice, we drove to Springfield last week and visited the old house on Maple Street.
"""

TRANSCRIPT_C_DIFFERENT = """\
---
source_file: note.pdf
transcription_confidence: high
word_count: 15
---

The weather has been lovely this summer. We went to the beach every weekend.
"""


def make_file(path: Path, content: str = "test content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestExactDuplicates:

    def test_no_duplicates(self, tmp_path):
        """Two files with different content produce no duplicate groups."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "file_a.txt", "content alpha")
        make_file(dest / "folder_b" / "file_b.txt", "content beta")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "file_a.txt")
        index_file(conn, dest, dest / "folder_b" / "file_b.txt")

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert groups == []

    def test_finds_exact_duplicates(self, tmp_path):
        """Two files with identical content produce one group with two entries."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "copy1.txt", "identical content")
        make_file(dest / "folder_b" / "copy2.txt", "identical content")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "copy1.txt")
        index_file(conn, dest, dest / "folder_b" / "copy2.txt")

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert len(groups) == 1
        assert len(groups[0]["files"]) == 2

    def test_group_has_correct_fields(self, tmp_path):
        """Group dict has match_type, similarity, and files with all required fields."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "doc1.txt", "shared content")
        make_file(dest / "folder_b" / "doc2.txt", "shared content")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "doc1.txt")
        index_file(conn, dest, dest / "folder_b" / "doc2.txt")

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert len(groups) == 1
        group = groups[0]

        assert group["match_type"] == "exact"
        assert group["similarity"] == 1.0
        assert "files" in group

        required_fields = {"file_id", "path", "filename", "folder", "file_type",
                           "size_bytes", "date_prefix", "indexed_at"}
        for file_entry in group["files"]:
            assert required_fields == set(file_entry.keys())

    def test_excludes_provenance_siblings(self, tmp_path):
        """Parent + two children with same content are excluded via provenance."""
        dest = tmp_path / "archive"
        dest.mkdir()

        # All three have identical content so they share an MD5
        shared = "same bytes for all"
        parent_path = make_file(dest / "Docs" / "parent.pdf", shared)
        child1_path = make_file(dest / "Docs" / "child1.pdf", shared)
        child2_path = make_file(dest / "Docs" / "child2.pdf", shared)

        conn = get_db(dest)
        parent_id = index_file(conn, dest, parent_path)
        child1_id = index_file(conn, dest, child1_path)
        child2_id = index_file(conn, dest, child2_path)

        # Record both children as splits from the parent
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation, detail) VALUES (?, ?, ?, ?)",
            (child1_id, parent_id, "split", "page 1"),
        )
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation, detail) VALUES (?, ?, ?, ?)",
            (child2_id, parent_id, "split", "page 2"),
        )
        conn.commit()

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert groups == []

    def test_multiple_duplicate_groups(self, tmp_path):
        """Two pairs of duplicates plus one unique file yields exactly two groups."""
        dest = tmp_path / "archive"
        dest.mkdir()

        # Pair A
        make_file(dest / "folder_a" / "a1.txt", "content group A")
        make_file(dest / "folder_b" / "a2.txt", "content group A")
        # Pair B
        make_file(dest / "folder_a" / "b1.txt", "content group B")
        make_file(dest / "folder_b" / "b2.txt", "content group B")
        # Unique
        make_file(dest / "folder_c" / "unique.txt", "unique content nobody else has")

        conn = get_db(dest)
        for name, folder in [
            ("a1.txt", "folder_a"), ("a2.txt", "folder_b"),
            ("b1.txt", "folder_a"), ("b2.txt", "folder_b"),
            ("unique.txt", "folder_c"),
        ]:
            index_file(conn, dest, dest / folder / name)

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert len(groups) == 2
        for group in groups:
            assert len(group["files"]) == 2


class TestTextSimilarity:

    def _setup_archive(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        return dest

    def test_identical_text_detected(self, tmp_path):
        """Two transcripts with identical bodies produce one group with similarity >= 0.90."""
        dest = self._setup_archive(tmp_path)

        pdf_a = make_file(dest / "folder_a" / "letter.pdf", "dummy")
        pdf_b = make_file(dest / "folder_b" / "letter-copy.pdf", "dummy copy")
        t_a = make_file(dest / "folder_a" / "letter.pdf.transcript.md", TRANSCRIPT_A)
        t_b = make_file(dest / "folder_b" / "letter-copy.pdf.transcript.md", TRANSCRIPT_B_SIMILAR)

        conn = get_db(dest)
        index_file(conn, dest, pdf_a)
        index_file(conn, dest, pdf_b)
        index_transcript(conn, dest, t_a)
        index_transcript(conn, dest, t_b)

        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)

        assert len(groups) == 1
        assert groups[0]["match_type"] == "text_similar"
        assert groups[0]["similarity"] >= 0.90

    def test_different_text_not_detected(self, tmp_path):
        """Two transcripts with different bodies produce no groups at threshold 0.90."""
        dest = self._setup_archive(tmp_path)

        pdf_a = make_file(dest / "folder_a" / "letter.pdf", "dummy")
        pdf_c = make_file(dest / "folder_b" / "note.pdf", "dummy note")
        t_a = make_file(dest / "folder_a" / "letter.pdf.transcript.md", TRANSCRIPT_A)
        t_c = make_file(dest / "folder_b" / "note.pdf.transcript.md", TRANSCRIPT_C_DIFFERENT)

        conn = get_db(dest)
        index_file(conn, dest, pdf_a)
        index_file(conn, dest, pdf_c)
        index_transcript(conn, dest, t_a)
        index_transcript(conn, dest, t_c)

        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)

        assert groups == []

    def test_excludes_provenance_siblings(self, tmp_path):
        """Two identical transcripts whose files are provenance siblings produce no groups."""
        dest = self._setup_archive(tmp_path)

        parent_pdf = make_file(dest / "Docs" / "parent.pdf", "original")
        t_parent = make_file(dest / "Docs" / "parent.pdf.transcript.md", TRANSCRIPT_A)
        t_child = make_file(dest / "Docs" / "child.pdf.transcript.md", TRANSCRIPT_B_SIMILAR)

        conn = get_db(dest)
        parent_id = index_file(conn, dest, parent_pdf)
        index_transcript(conn, dest, t_parent)
        index_transcript(conn, dest, t_child)

        # The transcripts_content rows are keyed by the transcript file's file_id,
        # so provenance must be recorded between the transcript file_ids.
        t_parent_id = conn.execute(
            "SELECT id FROM files WHERE path = ?",
            ("Docs/parent.pdf.transcript.md",),
        ).fetchone()["id"]
        t_child_id = conn.execute(
            "SELECT id FROM files WHERE path = ?",
            ("Docs/child.pdf.transcript.md",),
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation, detail) VALUES (?, ?, ?, ?)",
            (t_child_id, t_parent_id, "split", "page 1"),
        )
        conn.commit()

        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)

        assert groups == []

    def test_custom_threshold(self, tmp_path):
        """Two transcripts with any word overlap match at a very low threshold."""
        dest = self._setup_archive(tmp_path)

        pdf_a = make_file(dest / "folder_a" / "letter.pdf", "dummy")
        pdf_c = make_file(dest / "folder_b" / "note.pdf", "dummy note")
        t_a = make_file(dest / "folder_a" / "letter.pdf.transcript.md", TRANSCRIPT_A)
        t_c = make_file(dest / "folder_b" / "note.pdf.transcript.md", TRANSCRIPT_C_DIFFERENT)

        conn = get_db(dest)
        index_file(conn, dest, pdf_a)
        index_file(conn, dest, pdf_c)
        index_transcript(conn, dest, t_a)
        index_transcript(conn, dest, t_c)

        groups = find_text_similar(conn, threshold=0.01)
        close_db(conn)

        assert len(groups) == 1
        assert groups[0]["match_type"] == "text_similar"
