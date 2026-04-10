"""
Tests for the family-archive CLI entry point.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Repo root — works both locally and in CI
REPO_ROOT = str(Path(__file__).resolve().parent.parent)


class TestCLIImport:
    """Test that CLI module can be imported."""

    def test_main_importable(self):
        from scripts.cli import main
        assert callable(main)

    def test_version_importable(self):
        from scripts import __version__
        assert __version__ == "0.1.0"


class TestCLIVersion:
    """Test --version flag."""

    def test_version_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.cli", "--version"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout


class TestCLIHelp:
    """Test --help flag."""

    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.cli", "--help"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0
        assert "family-archive" in result.stdout
        assert "bootstrap" in result.stdout
        assert "organize" in result.stdout
        assert "verify" in result.stdout

    def test_no_args_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.cli"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        # Should exit with code 1 (no command given) and show help
        assert result.returncode == 1
        assert "family-archive" in result.stdout or "usage" in result.stdout.lower()


class TestPlaceholderCommands:
    """Test that placeholder commands print 'Coming soon'."""

    @pytest.mark.parametrize("cmd", ["split", "search", "serve"])
    def test_placeholder_prints_coming_soon(self, cmd):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.cli", cmd],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0
        assert "Coming soon" in result.stdout
