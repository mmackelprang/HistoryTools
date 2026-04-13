"""
Tests for apply_renames.py — update_frontmatter_source() and apply_single_rename().
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "familyarchive"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from apply_renames import update_frontmatter_source, apply_single_rename


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_transcript(path: Path, source_filename: str, extra_content: str = "") -> Path:
    """Write a minimal .transcript.md file with a source_file field."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\ntitle: Test\nsource_file: {source_filename}\n---\n\n"
        f"Transcript content.{extra_content}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _make_proposal(current_path: str, proposed_path: str,
                   current_name: str = None, proposed_name: str = None) -> dict:
    """Build a minimal rename proposal dict."""
    return {
        "current_path": current_path,
        "proposed_path": proposed_path,
        "current_name": current_name or Path(current_path).name,
        "proposed_name": proposed_name or Path(proposed_path).name,
        "approved": True,
    }


# ── update_frontmatter_source() ───────────────────────────────────────────────

class TestUpdateFrontmatterSource:
    def test_updates_source_file_field(self, tmp_path):
        md = _make_transcript(tmp_path / "file.transcript.md", "old_name.pdf")
        result = update_frontmatter_source(md, "old_name.pdf", "new_name.pdf")
        assert result is True
        content = md.read_text(encoding="utf-8")
        assert "source_file: new_name.pdf" in content

    def test_returns_false_when_source_file_not_found(self, tmp_path):
        md = tmp_path / "file.transcript.md"
        md.write_text("---\ntitle: Test\n---\nNo source_file here.\n", encoding="utf-8")
        result = update_frontmatter_source(md, "missing.pdf", "new.pdf")
        assert result is False

    def test_original_content_replaced_correctly(self, tmp_path):
        md = _make_transcript(tmp_path / "file.transcript.md", "scan001.pdf")
        update_frontmatter_source(md, "scan001.pdf", "2015-09-17_certificate.pdf")
        content = md.read_text(encoding="utf-8")
        assert "source_file: 2015-09-17_certificate.pdf" in content
        assert "source_file: scan001.pdf" not in content

    def test_does_not_modify_file_when_field_absent(self, tmp_path):
        original = "---\ntitle: Test\n---\nBody.\n"
        md = tmp_path / "file.transcript.md"
        md.write_text(original, encoding="utf-8")
        update_frontmatter_source(md, "nonexistent.pdf", "new.pdf")
        assert md.read_text(encoding="utf-8") == original

    def test_replaces_all_occurrences_including_body(self, tmp_path):
        """Documents that str.replace updates ALL occurrences, including body text."""
        content = (
            "---\nsource_file: old.pdf\n---\n\n"
            "We reference old.pdf in the body text too.\n"
        )
        md = tmp_path / "file.transcript.md"
        md.write_text(content, encoding="utf-8")
        update_frontmatter_source(md, "old.pdf", "new.pdf")
        result = md.read_text(encoding="utf-8")
        # The frontmatter line is updated
        assert "source_file: new.pdf" in result
        # Note: update_frontmatter_source does a plain string replace, so body
        # occurrences are also replaced — this test documents current behavior
        # rather than asserting body preservation (the function uses str.replace)

    def test_handles_path_like_filenames(self, tmp_path):
        md = _make_transcript(tmp_path / "file.transcript.md", "2020-01-15_scan.pdf")
        result = update_frontmatter_source(md, "2020-01-15_scan.pdf", "2020-01-15_letter-home.pdf")
        assert result is True


# ── apply_single_rename() ─────────────────────────────────────────────────────

class TestApplySingleRename:
    def test_renames_file_successfully(self, tmp_path):
        dest_root = tmp_path / "dest"
        (dest_root / "Letters" / "2020").mkdir(parents=True)
        src = dest_root / "Letters" / "2020" / "scan001.pdf"
        src.write_text("pdf content", encoding="utf-8")

        proposal = _make_proposal(
            current_path="Letters/2020/scan001.pdf",
            proposed_path="Letters/2020/2020-01-15_letter-home.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["status"] == "ok"
        assert not src.exists()
        assert (dest_root / "Letters" / "2020" / "2020-01-15_letter-home.pdf").exists()

    def test_skips_when_source_file_not_found(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()

        proposal = _make_proposal(
            current_path="Letters/missing.pdf",
            proposed_path="Letters/new.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["status"] == "skipped"
        assert "not found" in result["reason"].lower() or "File not found" in result["reason"]

    def test_skips_when_target_already_exists(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "old.pdf"
        tgt = dest_root / "new.pdf"
        src.write_text("source", encoding="utf-8")
        tgt.write_text("existing target", encoding="utf-8")

        proposal = _make_proposal(
            current_path="old.pdf",
            proposed_path="new.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["status"] == "skipped"
        assert "already exists" in result["reason"].lower() or "already exists" in result["reason"]
        # Original files should be untouched
        assert src.exists()
        assert tgt.read_text(encoding="utf-8") == "existing target"

    def test_renames_companion_transcript(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")
        transcript = dest_root / "scan001.transcript.md"
        _make_transcript(transcript, "scan001.pdf")

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["status"] == "ok"
        assert result["transcript_renamed"] is True
        assert not transcript.exists()
        assert (dest_root / "2020-01-15_letter.transcript.md").exists()

    def test_updates_frontmatter_in_renamed_transcript(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")
        transcript = dest_root / "scan001.transcript.md"
        _make_transcript(transcript, "scan001.pdf")

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["frontmatter_updated"] is True
        new_transcript = dest_root / "2020-01-15_letter.transcript.md"
        content = new_transcript.read_text(encoding="utf-8")
        assert "source_file: 2020-01-15_letter.pdf" in content

    def test_no_transcript_rename_when_transcript_absent(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")
        # No companion transcript

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["status"] == "ok"
        assert result["transcript_renamed"] is False
        assert result["frontmatter_updated"] is False

    def test_dry_run_does_not_rename_file(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal, dry_run=True)

        assert result["status"] == "dry_run"
        assert src.exists()  # file not actually renamed
        assert not (dest_root / "2020-01-15_letter.pdf").exists()

    def test_dry_run_reports_transcript_would_be_renamed(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")
        transcript = dest_root / "scan001.transcript.md"
        _make_transcript(transcript, "scan001.pdf")

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal, dry_run=True)

        assert result["status"] == "dry_run"
        assert result["transcript_renamed"] is True  # would be renamed

    def test_result_contains_old_and_new_path(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert "old_path" in result
        assert "new_path" in result
        assert result["old_path"] == "scan001.pdf"
        assert result["new_path"] == "2020-01-15_letter.pdf"

    def test_same_source_and_target_path_is_allowed(self, tmp_path):
        """Renaming to the same path (no-op rename) should not be flagged as 'exists'."""
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")

        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="scan001.pdf",  # same name
        )
        result = apply_single_rename(dest_root, proposal)
        # proposed_path == current_path → condition `proposed_path != current_path` is False
        # so it won't be flagged as "already exists"
        assert result["status"] == "ok"

    def test_creates_parent_directory_for_proposed_path(self, tmp_path):
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        src = dest_root / "scan001.pdf"
        src.write_text("pdf", encoding="utf-8")

        # Target is in a subdirectory that doesn't exist yet
        proposal = _make_proposal(
            current_path="scan001.pdf",
            proposed_path="NewSubfolder/2020-01-15_letter.pdf",
        )
        result = apply_single_rename(dest_root, proposal)

        assert result["status"] == "ok"
        assert (dest_root / "NewSubfolder" / "2020-01-15_letter.pdf").exists()
