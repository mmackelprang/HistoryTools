"""
Tests for the duplicate lifecycle management module (scripts/duplicate_manage.py).
"""

import json
from pathlib import Path

import pytest

from scripts.db import get_db, close_db, index_file
from scripts.duplicate_manage import (
    apply_quarantine,
    restore_file,
    purge_expired,
    get_quarantine_status,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_file(path, content="test content"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_proposals(dest, groups):
    data = {"generated": "2026-04-11T00:00:00", "groups": groups}
    with open(dest / "_duplicate-proposals.json", "w") as f:
        json.dump(data, f)


# ── TestQuarantine ────────────────────────────────────────────────────────────


class TestQuarantine:

    def test_apply_moves_file(self, tmp_path):
        """Non-keep file is moved to _duplicates/; keep file remains in place."""
        dest = tmp_path / "archive"
        dest.mkdir()

        keep = make_file(dest / "folder_a" / "keep.txt", "shared content")
        dupe = make_file(dest / "folder_b" / "dupe.txt", "shared content")

        conn = get_db(dest)
        index_file(conn, dest, keep)
        index_file(conn, dest, dupe)

        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "exact",
                "similarity": 1.0,
                "keep": "folder_a/keep.txt",
                "approved": True,
                "files": [
                    {"path": "folder_a/keep.txt", "recommended": True},
                    {"path": "folder_b/dupe.txt", "recommended": False},
                ],
            }
        ])

        result = apply_quarantine(conn, dest)
        close_db(conn)

        assert result["quarantined"] == 1
        assert keep.exists(), "Keep file should remain"
        assert not dupe.exists(), "Dupe file should be moved"
        assert (dest / "_duplicates" / "folder_b" / "dupe.txt").exists()

    def test_apply_skips_unapproved(self, tmp_path):
        """Groups with approved=False are skipped; file remains in place."""
        dest = tmp_path / "archive"
        dest.mkdir()

        keep = make_file(dest / "folder_a" / "keep.txt", "shared content")
        dupe = make_file(dest / "folder_b" / "dupe.txt", "shared content")

        conn = get_db(dest)
        index_file(conn, dest, keep)
        index_file(conn, dest, dupe)

        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "exact",
                "similarity": 1.0,
                "keep": "folder_a/keep.txt",
                "approved": False,
                "files": [
                    {"path": "folder_a/keep.txt", "recommended": True},
                    {"path": "folder_b/dupe.txt", "recommended": False},
                ],
            }
        ])

        result = apply_quarantine(conn, dest)
        close_db(conn)

        assert result["quarantined"] == 0
        assert dupe.exists(), "Unapproved dupe should remain in place"

    def test_apply_moves_transcript_with_source(self, tmp_path):
        """When a dupe has an associated .transcript.md, both are moved to _duplicates/."""
        dest = tmp_path / "archive"
        dest.mkdir()

        keep = make_file(dest / "folder_a" / "keep.txt", "shared content")
        dupe = make_file(dest / "folder_b" / "dupe.txt", "shared content")
        transcript = make_file(
            dest / "folder_b" / "dupe.transcript.md",
            "---\nsource_file: dupe.txt\n---\nsome transcript text"
        )

        conn = get_db(dest)
        index_file(conn, dest, keep)
        index_file(conn, dest, dupe)
        index_file(conn, dest, transcript)

        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "exact",
                "similarity": 1.0,
                "keep": "folder_a/keep.txt",
                "approved": True,
                "files": [
                    {"path": "folder_a/keep.txt", "recommended": True},
                    {"path": "folder_b/dupe.txt", "recommended": False},
                ],
            }
        ])

        result = apply_quarantine(conn, dest)
        close_db(conn)

        assert result["quarantined"] == 1
        assert not dupe.exists()
        assert not transcript.exists()
        assert (dest / "_duplicates" / "folder_b" / "dupe.txt").exists()
        assert (dest / "_duplicates" / "folder_b" / "dupe.transcript.md").exists()

    def test_apply_records_in_quarantine_table(self, tmp_path):
        """Quarantine table has a row with correct original_path, duplicate_of, and reason."""
        dest = tmp_path / "archive"
        dest.mkdir()

        keep = make_file(dest / "folder_a" / "keep.txt", "shared content")
        dupe = make_file(dest / "folder_b" / "dupe.txt", "shared content")

        conn = get_db(dest)
        index_file(conn, dest, keep)
        index_file(conn, dest, dupe)

        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "text_similar",
                "similarity": 0.95,
                "keep": "folder_a/keep.txt",
                "approved": True,
                "files": [
                    {"path": "folder_a/keep.txt", "recommended": True},
                    {"path": "folder_b/dupe.txt", "recommended": False},
                ],
            }
        ])

        apply_quarantine(conn, dest)

        row = conn.execute(
            "SELECT original_path, duplicate_of, reason FROM quarantine WHERE original_path = ?",
            ("folder_b/dupe.txt",),
        ).fetchone()
        close_db(conn)

        assert row is not None
        assert row["original_path"] == "folder_b/dupe.txt"
        assert row["duplicate_of"] == "folder_a/keep.txt"
        assert row["reason"] == "text_similar"


# ── TestRestore ───────────────────────────────────────────────────────────────


class TestRestore:

    def _quarantine_one(self, dest, conn, dupe_rel, keep_rel="folder_a/keep.txt"):
        """Helper: create and quarantine a file, return its quarantine path."""
        keep_abs = dest / keep_rel
        dupe_abs = dest / dupe_rel
        make_file(keep_abs, "shared content")
        make_file(dupe_abs, "shared content")
        index_file(conn, dest, keep_abs)
        index_file(conn, dest, dupe_abs)

        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "exact",
                "similarity": 1.0,
                "keep": keep_rel,
                "approved": True,
                "files": [
                    {"path": keep_rel, "recommended": True},
                    {"path": dupe_rel, "recommended": False},
                ],
            }
        ])
        apply_quarantine(conn, dest)
        return "_duplicates/" + dupe_rel

    def test_restore_moves_file_back(self, tmp_path):
        """After restore, the file is back at its original path."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        q_path = self._quarantine_one(dest, conn, "folder_b/dupe.txt")
        dupe_abs = dest / "folder_b" / "dupe.txt"

        assert not dupe_abs.exists(), "Should be in quarantine before restore"

        restore_file(conn, dest, q_path)
        close_db(conn)

        assert dupe_abs.exists(), "File should be back at original path after restore"

    def test_restore_removes_quarantine_record(self, tmp_path):
        """After restore, the quarantine table is empty."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        q_path = self._quarantine_one(dest, conn, "folder_b/dupe.txt")
        restore_file(conn, dest, q_path)

        count = conn.execute("SELECT COUNT(*) as cnt FROM quarantine").fetchone()["cnt"]
        close_db(conn)

        assert count == 0


# ── TestPurge ─────────────────────────────────────────────────────────────────


class TestPurge:

    def _quarantine_file(self, dest, conn, dupe_rel="folder_b/dupe.txt",
                         keep_rel="folder_a/keep.txt"):
        """Helper: create and quarantine a file, return quarantine path string."""
        make_file(dest / keep_rel, "shared content")
        make_file(dest / dupe_rel, "shared content")
        index_file(conn, dest, dest / keep_rel)
        index_file(conn, dest, dest / dupe_rel)
        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "exact",
                "similarity": 1.0,
                "keep": keep_rel,
                "approved": True,
                "files": [
                    {"path": keep_rel, "recommended": True},
                    {"path": dupe_rel, "recommended": False},
                ],
            }
        ])
        apply_quarantine(conn, dest)
        return "_duplicates/" + dupe_rel

    def test_purge_deletes_expired(self, tmp_path):
        """An expired quarantine entry (purge_after in the past) is purged."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        q_path = self._quarantine_file(dest, conn)

        # Backdate purge_after to the past
        conn.execute(
            "UPDATE quarantine SET purge_after = datetime('now', '-1 day')"
        )
        conn.commit()

        result = purge_expired(conn, dest)
        close_db(conn)

        assert result["purged"] == 1
        assert not (dest / q_path).exists()

    def test_purge_skips_unexpired(self, tmp_path):
        """An unexpired quarantine entry (future TTL) is not purged."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        q_path = self._quarantine_file(dest, conn)

        # Ensure TTL is in the future (default is +14 days, so this is a sanity check)
        conn.execute(
            "UPDATE quarantine SET purge_after = datetime('now', '+30 days')"
        )
        conn.commit()

        result = purge_expired(conn, dest)
        close_db(conn)

        assert result["purged"] == 0
        assert (dest / q_path).exists(), "Unexpired file should still exist"

    def test_purge_all_ignores_ttl(self, tmp_path):
        """purge_all=True deletes all quarantined files even if TTL is in the future."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        q_path = self._quarantine_file(dest, conn)

        # Ensure TTL is far in the future
        conn.execute(
            "UPDATE quarantine SET purge_after = datetime('now', '+365 days')"
        )
        conn.commit()

        result = purge_expired(conn, dest, purge_all=True)
        close_db(conn)

        assert result["purged"] == 1
        assert not (dest / q_path).exists()


# ── TestStatus ────────────────────────────────────────────────────────────────


class TestStatus:

    def test_status_empty(self, tmp_path):
        """When no quarantine entries exist, all values are zero."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        status = get_quarantine_status(conn)
        close_db(conn)

        assert status["total_files"] == 0
        assert status["total_size_bytes"] == 0
        assert status["expired"] == 0
        assert status["by_reason"] == {}

    def test_status_with_entries(self, tmp_path):
        """After quarantining one file, total_files is 1."""
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)

        keep = make_file(dest / "folder_a" / "keep.txt", "shared content")
        dupe = make_file(dest / "folder_b" / "dupe.txt", "shared content")
        index_file(conn, dest, keep)
        index_file(conn, dest, dupe)

        make_proposals(dest, [
            {
                "id": "dup-001",
                "match_type": "exact",
                "similarity": 1.0,
                "keep": "folder_a/keep.txt",
                "approved": True,
                "files": [
                    {"path": "folder_a/keep.txt", "recommended": True},
                    {"path": "folder_b/dupe.txt", "recommended": False},
                ],
            }
        ])
        apply_quarantine(conn, dest)

        status = get_quarantine_status(conn)
        close_db(conn)

        assert status["total_files"] == 1
