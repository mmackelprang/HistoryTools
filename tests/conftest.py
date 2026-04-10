"""
Common fixtures and helpers for HistoryTools test suite.
"""

import sys
import zipfile
from pathlib import Path

import pytest

# Make the scripts directory importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_file(path: Path, content: str = "test content") -> Path:
    """Create a file with given content, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_zip(zip_path: Path, members: dict) -> Path:
    """Create a ZIP file.

    Args:
        zip_path: Where to write the ZIP.
        members:  Mapping of {arcname: content_string}.  Pass content=None to
                  create a directory entry.
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "w") as z:
        for arcname, content in members.items():
            if content is None:
                z.mkdir(arcname)
            else:
                z.writestr(arcname, content)
    return zip_path


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def source_dir(tmp_path):
    """Return a fresh empty directory to use as a source root."""
    d = tmp_path / "source"
    d.mkdir()
    return d


@pytest.fixture()
def dest_dir(tmp_path):
    """Return a fresh empty directory to use as a destination root."""
    d = tmp_path / "dest"
    d.mkdir()
    return d
