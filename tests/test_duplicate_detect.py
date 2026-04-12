"""
Tests for the duplicate detection module (scripts/duplicate_detect.py).
"""

from pathlib import Path
import pytest
from scripts.db import get_db, close_db, index_file, index_transcript
from scripts.duplicate_detect import find_exact_duplicates


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
