"""
Tests for the init_wizard module.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.init_wizard import (
    create_folder_structure,
    prompt_input,
    prompt_yes_no,
    scan_source_for_suggestions,
)


class TestScanSourceForSuggestions:
    """Test scan_source_for_suggestions with various file types."""

    def test_empty_directory(self, tmp_path):
        counts = scan_source_for_suggestions(tmp_path)
        assert counts == {"pdf": 0, "audio": 0, "photo": 0, "video": 0, "other": 0}

    def test_nonexistent_directory(self, tmp_path):
        counts = scan_source_for_suggestions(tmp_path / "nope")
        assert counts == {}

    def test_pdf_files(self, tmp_path):
        (tmp_path / "doc1.pdf").write_bytes(b"fake pdf")
        (tmp_path / "doc2.pdf").write_bytes(b"fake pdf")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["pdf"] == 2
        assert counts["audio"] == 0

    def test_audio_files(self, tmp_path):
        (tmp_path / "song.mp3").write_bytes(b"fake mp3")
        (tmp_path / "recording.wav").write_bytes(b"fake wav")
        (tmp_path / "memo.m4a").write_bytes(b"fake m4a")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["audio"] == 3

    def test_photo_files(self, tmp_path):
        (tmp_path / "pic.jpg").write_bytes(b"fake jpg")
        (tmp_path / "pic2.jpeg").write_bytes(b"fake jpeg")
        (tmp_path / "pic3.png").write_bytes(b"fake png")
        (tmp_path / "pic4.tiff").write_bytes(b"fake tiff")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["photo"] == 4

    def test_video_files(self, tmp_path):
        (tmp_path / "movie.mp4").write_bytes(b"fake mp4")
        (tmp_path / "clip.mov").write_bytes(b"fake mov")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["video"] == 2

    def test_other_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["other"] == 2

    def test_mixed_files(self, tmp_path):
        (tmp_path / "doc.pdf").write_bytes(b"pdf")
        (tmp_path / "song.mp3").write_bytes(b"mp3")
        (tmp_path / "photo.jpg").write_bytes(b"jpg")
        (tmp_path / "clip.mp4").write_bytes(b"mp4")
        (tmp_path / "notes.txt").write_text("txt")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["pdf"] == 1
        assert counts["audio"] == 1
        assert counts["photo"] == 1
        assert counts["video"] == 1
        assert counts["other"] == 1

    def test_nested_directories(self, tmp_path):
        sub = tmp_path / "subdir" / "deep"
        sub.mkdir(parents=True)
        (sub / "nested.pdf").write_bytes(b"pdf")
        (tmp_path / "top.jpg").write_bytes(b"jpg")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["pdf"] == 1
        assert counts["photo"] == 1

    def test_case_insensitive_extensions(self, tmp_path):
        (tmp_path / "PHOTO.JPG").write_bytes(b"jpg")
        (tmp_path / "Doc.PDF").write_bytes(b"pdf")
        counts = scan_source_for_suggestions(tmp_path)
        assert counts["photo"] == 1
        assert counts["pdf"] == 1


class TestCreateFolderStructure:
    """Test create_folder_structure creates expected folders."""

    def test_creates_taxonomy_folders(self, tmp_path):
        dest = tmp_path / "archive"
        taxonomy = {
            "folders": {
                "Letters": {"keywords": ["letter"]},
                "Photos": {"keywords": ["photo"]},
                "Audio/Recordings": {"keywords": ["audio"]},
            }
        }
        count = create_folder_structure(dest, taxonomy)
        assert count == 3
        assert (dest / "Letters").is_dir()
        assert (dest / "Photos").is_dir()
        assert (dest / "Audio" / "Recordings").is_dir()

    def test_creates_system_folders(self, tmp_path):
        dest = tmp_path / "archive"
        taxonomy = {"folders": {}}
        create_folder_structure(dest, taxonomy)
        assert (dest / "NeedsReview").is_dir()
        assert (dest / "Unprocessed").is_dir()
        assert (dest / "Duplicates").is_dir()

    def test_empty_taxonomy(self, tmp_path):
        dest = tmp_path / "archive"
        count = create_folder_structure(dest, {})
        assert count == 0
        # System folders are always created
        assert (dest / "NeedsReview").is_dir()

    def test_idempotent(self, tmp_path):
        dest = tmp_path / "archive"
        taxonomy = {"folders": {"Letters": {}}}
        create_folder_structure(dest, taxonomy)
        # Run again — should not raise
        count = create_folder_structure(dest, taxonomy)
        assert count == 1
        assert (dest / "Letters").is_dir()

    def test_creates_dest_if_missing(self, tmp_path):
        dest = tmp_path / "new" / "nested" / "archive"
        taxonomy = {"folders": {"Docs": {}}}
        create_folder_structure(dest, taxonomy)
        assert dest.is_dir()
        assert (dest / "Docs").is_dir()

    def test_with_default_taxonomy(self, tmp_path):
        from scripts.config import DEFAULT_TAXONOMY
        dest = tmp_path / "archive"
        count = create_folder_structure(dest, DEFAULT_TAXONOMY)
        # Should create all folders from the default taxonomy
        assert count == len(DEFAULT_TAXONOMY["folders"])
        # Spot-check a few
        assert (dest / "Correspondence" / "Letters").is_dir()
        assert (dest / "Journals").is_dir()
        assert (dest / "Media" / "Photos").is_dir()


class TestPromptInput:
    """Test prompt_input with mocked input."""

    @patch("builtins.input", return_value="my answer")
    def test_returns_user_input(self, mock_input):
        result = prompt_input("Enter something")
        assert result == "my answer"

    @patch("builtins.input", return_value="")
    def test_returns_default_when_empty(self, mock_input):
        result = prompt_input("Enter something", default="fallback")
        assert result == "fallback"

    @patch("builtins.input", return_value="override")
    def test_user_overrides_default(self, mock_input):
        result = prompt_input("Enter something", default="fallback")
        assert result == "override"

    @patch("builtins.input", return_value="")
    def test_returns_none_no_default(self, mock_input):
        result = prompt_input("Enter something")
        assert result is None

    @patch("builtins.input", return_value="  spaced  ")
    def test_strips_whitespace(self, mock_input):
        result = prompt_input("Enter something")
        assert result == "spaced"


class TestPromptYesNo:
    """Test prompt_yes_no with mocked input."""

    @patch("builtins.input", return_value="")
    def test_default_true(self, mock_input):
        assert prompt_yes_no("Continue?", default=True) is True

    @patch("builtins.input", return_value="")
    def test_default_false(self, mock_input):
        assert prompt_yes_no("Continue?", default=False) is False

    @patch("builtins.input", return_value="y")
    def test_yes_lowercase(self, mock_input):
        assert prompt_yes_no("Continue?", default=False) is True

    @patch("builtins.input", return_value="Y")
    def test_yes_uppercase(self, mock_input):
        assert prompt_yes_no("Continue?", default=False) is True

    @patch("builtins.input", return_value="yes")
    def test_yes_full_word(self, mock_input):
        assert prompt_yes_no("Continue?", default=False) is True

    @patch("builtins.input", return_value="n")
    def test_no(self, mock_input):
        assert prompt_yes_no("Continue?", default=True) is False

    @patch("builtins.input", return_value="no")
    def test_no_full_word(self, mock_input):
        assert prompt_yes_no("Continue?", default=True) is False

    @patch("builtins.input", return_value="maybe")
    def test_invalid_treated_as_no(self, mock_input):
        assert prompt_yes_no("Continue?", default=True) is False
