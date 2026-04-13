# SP-0A: Package Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform HistoryTools from a collection of scripts into a pip-installable `familyarchive` package with progress callbacks, storage abstraction, entity schema, and connector base class.

**Architecture:** Rename `scripts/` → `familyarchive/`, update all imports and entry points, then add new modules (progress, storage, entities, connectors) as focused subpackages. Existing shim files are removed since the rename is a clean break. All pipeline scripts become importable modules. Tests are updated to use new import paths.

**Tech Stack:** Python 3.10+, SQLite, setuptools, pytest

---

## File Structure

### Renamed (scripts/ → familyarchive/)

| Old Path | New Path | Notes |
|----------|----------|-------|
| `scripts/__init__.py` | `familyarchive/__init__.py` | Update version, add public API |
| `scripts/core/__init__.py` | `familyarchive/core/__init__.py` | Same |
| `scripts/core/config.py` | `familyarchive/core/config.py` | Update TOOLKIT_DIR logic |
| `scripts/core/db.py` | `familyarchive/core/db.py` | Add entity tables (Task 5) |
| `scripts/core/ai_client.py` | `familyarchive/core/ai_client.py` | Move real impl here (un-reverse shim) |
| `scripts/core/cost_tracker.py` | `familyarchive/core/cost_tracker.py` | Same |
| `scripts/core/rate_limiter.py` | `familyarchive/core/rate_limiter.py` | Same |
| `scripts/core/extract.py` | `familyarchive/core/extract.py` | Same |
| `scripts/core/quality_check.py` | `familyarchive/core/quality_check.py` | Same |
| `scripts/cli.py` | `familyarchive/cli.py` | Update imports |
| `scripts/ingest.py` | `familyarchive/ingest.py` | Update imports |
| `scripts/organize.py` | `familyarchive/organize.py` | Update imports |
| `scripts/*.py` (all others) | `familyarchive/*.py` | Update imports |

### Deleted (shims no longer needed)

| File | Reason |
|------|--------|
| `scripts/config.py` (shim) | Direct import from `familyarchive.core.config` |
| `scripts/db.py` (shim) | Direct import from `familyarchive.core.db` |
| `scripts/cost_tracker.py` (shim) | Direct import from `familyarchive.core.cost_tracker` |
| `scripts/rate_limiter.py` (shim) | Direct import from `familyarchive.core.rate_limiter` |
| `scripts/quality_check.py` (shim) | Direct import from `familyarchive.core.quality_check` |
| `scripts/core/ai_client.py` (reverse shim) | Real impl moves to core |

### New Files

| File | Purpose |
|------|---------|
| `familyarchive/progress.py` | ProgressEvent dataclass + callback type alias |
| `familyarchive/storage/__init__.py` | Public API for storage |
| `familyarchive/storage/base.py` | StorageBackend ABC |
| `familyarchive/storage/local.py` | Local filesystem implementation |
| `familyarchive/entities/__init__.py` | Public API for entities |
| `familyarchive/entities/models.py` | Entity dataclasses |
| `familyarchive/entities/db.py` | Entity CRUD + schema migration |
| `familyarchive/connectors/__init__.py` | Public API + registry |
| `familyarchive/connectors/base.py` | Connector ABC + data models |
| `tests/test_progress.py` | Tests for progress module |
| `tests/test_storage.py` | Tests for storage abstraction |
| `tests/test_entities.py` | Tests for entity schema + CRUD |
| `tests/test_connectors.py` | Tests for connector base class + registry |

---

## Task 1: Rename scripts/ → familyarchive/ and fix all imports

**Files:**
- Rename: `scripts/` → `familyarchive/` (entire directory)
- Modify: `pyproject.toml`
- Modify: `tests/conftest.py`
- Modify: All test files with `scripts` imports or `SCRIPTS_DIR`
- Delete: Shim files (config.py, db.py, cost_tracker.py, rate_limiter.py, quality_check.py at package root)
- Modify: `familyarchive/core/ai_client.py` (move real impl here from parent)
- Delete: `familyarchive/ai_client.py` (was the real impl, now in core/)

- [ ] **Step 1: Rename the directory**

```bash
cd D:/HistoryTools
git mv scripts familyarchive
```

- [ ] **Step 2: Move ai_client real implementation into core**

The current setup has a reverse shim: `scripts/ai_client.py` has the real code, `scripts/core/ai_client.py` re-exports it. Fix this by moving the real implementation into core.

```bash
# Copy the real implementation over the shim
cp familyarchive/ai_client.py familyarchive/core/ai_client.py.real
```

Then replace `familyarchive/core/ai_client.py` with the contents of `familyarchive/ai_client.py` (the real implementation). The file currently at `familyarchive/ai_client.py` (270+ lines) becomes the core module. Update any internal imports within it from `from core.` to `from .` (relative within core/).

- [ ] **Step 3: Convert ai_client.py at package root to a shim pointing to core**

Replace `familyarchive/ai_client.py` with:

```python
"""Shim — real implementation in familyarchive/core/ai_client.py"""
from .core.ai_client import *  # noqa: F401,F403
```

- [ ] **Step 4: Delete all other shim files at package root**

These shim files exist because `scripts/` had both library code in `core/` and shim files at the root for backward compatibility. After the rename, pipeline scripts import from `familyarchive.core.*` directly. The remaining shims at the package root are only needed for the `from ai_client import X` pattern used by some scripts.

Delete these files — they re-export from core/ which pipeline scripts can import directly:

```bash
rm familyarchive/config.py      # shim → core.config
rm familyarchive/db.py           # shim → core.db
rm familyarchive/cost_tracker.py # shim → core.cost_tracker
rm familyarchive/rate_limiter.py # shim → core.rate_limiter
rm familyarchive/quality_check.py # shim → core.quality_check
```

**WAIT** — before deleting, check which pipeline scripts use bare imports like `from config import load_config` via `sys.path.insert`. Those scripts add their own directory to sys.path, then import bare module names. After the rename these bare imports will resolve to the shim files.

**Decision:** Keep the shim files for now. The pipeline scripts have `sys.path.insert(0, str(Path(__file__).parent))` which makes bare imports resolve to files in `familyarchive/`. The shims must stay so `from config import load_config` still works from within the package. This is the safe approach — we can remove them in a future cleanup once all pipeline scripts are updated to use proper package imports.

- [ ] **Step 5: Update pyproject.toml**

```toml
[project]
name = "familyarchive"
version = "0.3.0"
description = "Toolkit for digitizing, organizing, transcribing, and searching family archives"

[project.scripts]
family-archive = "familyarchive.cli:main"

[tool.setuptools.packages.find]
include = ["familyarchive*"]

[tool.setuptools.package-data]
familyarchive = ["*.py"]
```

- [ ] **Step 6: Update familyarchive/__init__.py**

```python
"""
Family Archive Toolkit — familyarchive package.

Installable library for digitizing, organizing, transcribing,
and searching family archives.

Install: pip install git+https://github.com/mmackelprang/HistoryTools.git
"""

__version__ = "0.3.0"
```

- [ ] **Step 7: Update familyarchive/core/__init__.py**

```python
"""
Core library for the Family Archive Toolkit.

Shared infrastructure modules used by pipeline scripts and the web UI.
Import from submodules directly: from familyarchive.core.config import load_config
"""
```

- [ ] **Step 8: Update TOOLKIT_DIR in familyarchive/core/config.py**

Change line 10:

```python
# Before:
TOOLKIT_DIR = Path(__file__).resolve().parent.parent.parent

# After:
TOOLKIT_DIR = Path(__file__).resolve().parent.parent.parent
# familyarchive/core/config.py → parent.parent.parent = project root
# This is unchanged because the depth is the same:
# scripts/core/config.py (3 levels up = project root)
# familyarchive/core/config.py (3 levels up = project root)
```

Verify this is correct — the path depth from `familyarchive/core/config.py` to the project root (where `config.json` lives) is the same as before. No change needed.

- [ ] **Step 9: Update tests/conftest.py**

```python
"""
Common fixtures and helpers for HistoryTools test suite.
"""

import sys
import zipfile
from pathlib import Path

import pytest

# Make the familyarchive package directory importable for bare imports
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "familyarchive"
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
                z.writestr(arcname.rstrip("/") + "/", "")
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
```

- [ ] **Step 10: Update all test files — replace `scripts` references**

Apply these replacements across ALL test files:

| Pattern | Replacement |
|---------|-------------|
| `from scripts.core.extract import` | `from familyarchive.core.extract import` |
| `from scripts.db import` | `from familyarchive.core.db import` |
| `from scripts.duplicate_detect import` | `from familyarchive.duplicate_detect import` |
| `from scripts.duplicate_manage import` | `from familyarchive.duplicate_manage import` |
| `from scripts.gemini_batch import` | `from familyarchive.gemini_batch import` |
| `from scripts.init_wizard import` | `from familyarchive.init_wizard import` |
| `from scripts.rate_limiter import` | `from familyarchive.core.rate_limiter import` |
| `SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"` | `SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "familyarchive"` |
| `"scripts.cli"` (in test_cli.py subprocess calls) | `"familyarchive.cli"` |

For `test_core_imports.py` — this file tests shim equivalence between `scripts.*` and `scripts.core.*`. It must be **rewritten** to test that `familyarchive.core.*` modules are importable:

```python
"""Verify that core library modules are importable from familyarchive.core."""

def test_config_importable():
    from familyarchive.core.config import load_config, load_taxonomy, DEFAULT_TAXONOMY
    assert callable(load_config)

def test_db_importable():
    from familyarchive.core.db import get_db, search, get_stats
    assert callable(get_db)

def test_ai_client_importable():
    from familyarchive.core.ai_client import get_ai_client, call_text
    assert callable(get_ai_client)

def test_cost_tracker_importable():
    from familyarchive.core.cost_tracker import CostTracker
    assert CostTracker is not None

def test_extract_importable():
    from familyarchive.core.extract import extract_file, get_supported_extensions
    assert callable(extract_file)

def test_quality_check_importable():
    from familyarchive.core.quality_check import assess_text_quality
    assert callable(assess_text_quality)

def test_rate_limiter_importable():
    from familyarchive.core.rate_limiter import RateLimiter
    assert RateLimiter is not None
```

- [ ] **Step 11: Update internal imports in pipeline scripts**

Each pipeline script in `familyarchive/` has `sys.path.insert(0, str(Path(__file__).parent))`. This still works after the rename because it adds the `familyarchive/` directory to sys.path, allowing bare imports like `from config import load_config` to resolve to the shim files.

**No changes needed to pipeline scripts for this step.** The bare imports continue to work via shims + sys.path. A future cleanup task can migrate them to proper package imports.

- [ ] **Step 12: Update the ingest.py SCRIPTS_DIR constant**

In `familyarchive/ingest.py`, find:
```python
SCRIPTS_DIR = Path(__file__).parent
```
This is fine — it points to the `familyarchive/` directory. But verify that `run_script()` still finds scripts at the correct path. Since `run_script()` does `SCRIPTS_DIR / script_name`, and the scripts are now in `familyarchive/`, this still works.

Also in `familyarchive/ingest.py`, find the subprocess call for duplicates:
```python
_subprocess.run(
    [sys.executable, "-m", "scripts.cli", "duplicates", "--scan"] + config_args,
    cwd=str(Path(__file__).resolve().parent.parent),
)
```
Change to:
```python
_subprocess.run(
    [sys.executable, "-m", "familyarchive.cli", "duplicates", "--scan"] + config_args,
    cwd=str(Path(__file__).resolve().parent.parent),
)
```

- [ ] **Step 13: Run all tests**

```bash
cd D:/HistoryTools
python -m pytest tests/ -v
```

Expected: All existing tests pass. Fix any import errors that surface.

- [ ] **Step 14: Test pip install**

```bash
cd D:/HistoryTools
pip install -e .
family-archive --help
```

Expected: CLI help output shows all commands.

- [ ] **Step 15: Commit**

```bash
git add -A
git commit -m "refactor: rename scripts/ to familyarchive/ package

- Rename scripts/ → familyarchive/ for pip-installable package
- Update pyproject.toml: package name → familyarchive, version → 0.3.0
- Move ai_client real implementation into core/ (un-reverse the shim)
- Keep shim files at package root for backward compat with bare imports
- Update all test imports from scripts.* to familyarchive.*
- Update conftest.py SCRIPTS_DIR to point to familyarchive/
- Rewrite test_core_imports.py for new import paths
- Update ingest.py subprocess call to use familyarchive.cli"
```

---

## Task 2: Progress Callback Protocol

**Files:**
- Create: `familyarchive/progress.py`
- Create: `tests/test_progress.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_progress.py`:

```python
"""Tests for the progress callback protocol."""

from familyarchive.progress import ProgressEvent, ProgressCallback


def test_progress_event_creation():
    """ProgressEvent can be created with required fields."""
    event = ProgressEvent(
        stage="transcribe",
        stage_number=2,
        total_stages=9,
        status="processing",
    )
    assert event.stage == "transcribe"
    assert event.stage_number == 2
    assert event.total_stages == 9
    assert event.status == "processing"
    assert event.file_path is None
    assert event.current is None
    assert event.total is None
    assert event.message is None
    assert event.detail is None


def test_progress_event_with_all_fields():
    """ProgressEvent accepts all optional fields."""
    event = ProgressEvent(
        stage="copy",
        stage_number=1,
        total_stages=9,
        status="processing",
        file_path="/archive/Letters/letter.pdf",
        current=47,
        total=500,
        message="Copying file 47 of 500",
        detail={"bytes_copied": 1024},
    )
    assert event.file_path == "/archive/Letters/letter.pdf"
    assert event.current == 47
    assert event.total == 500
    assert event.message == "Copying file 47 of 500"
    assert event.detail == {"bytes_copied": 1024}


def test_progress_event_status_values():
    """ProgressEvent status field accepts all valid values."""
    for status in ("started", "processing", "completed", "error", "skipped"):
        event = ProgressEvent(
            stage="test", stage_number=1, total_stages=1, status=status
        )
        assert event.status == status


def test_progress_callback_type():
    """ProgressCallback type alias works with a real function."""
    received = []

    def my_callback(event: ProgressEvent) -> None:
        received.append(event)

    callback: ProgressCallback = my_callback
    event = ProgressEvent(
        stage="format", stage_number=6, total_stages=9, status="started"
    )
    callback(event)
    assert len(received) == 1
    assert received[0].stage == "format"


def test_progress_event_to_dict():
    """ProgressEvent can be serialized to a dict for SSE/JSON."""
    event = ProgressEvent(
        stage="transcribe",
        stage_number=2,
        total_stages=9,
        status="processing",
        file_path="letter.pdf",
        current=3,
        total=10,
        message="Transcribing page 3",
    )
    d = event.to_dict()
    assert d["stage"] == "transcribe"
    assert d["stage_number"] == 2
    assert d["current"] == 3
    assert d["file_path"] == "letter.pdf"
    assert "detail" not in d or d["detail"] is None


def test_print_callback():
    """Built-in print_progress callback prints to stdout."""
    from familyarchive.progress import print_progress
    import io
    import sys

    event = ProgressEvent(
        stage="copy",
        stage_number=1,
        total_stages=9,
        status="processing",
        file_path="letter.pdf",
        current=3,
        total=10,
        message="Copying file 3 of 10",
    )

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        print_progress(event)
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "copy" in output.lower() or "Copying" in output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_progress.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'familyarchive.progress'`

- [ ] **Step 3: Write the implementation**

Create `familyarchive/progress.py`:

```python
"""
Progress callback protocol for pipeline operations.

Defines a standard event format that pipeline functions emit to report
progress. The CLI uses print_progress(); the web UI uses an SSE-emitting
callback. Both consume the same library functions.

Usage:
    from familyarchive.progress import ProgressEvent, ProgressCallback

    def my_pipeline(config, on_progress: ProgressCallback = None):
        if on_progress:
            on_progress(ProgressEvent(
                stage="transcribe", stage_number=2, total_stages=9,
                status="processing", file_path="letter.pdf",
                current=3, total=10, message="Transcribing page 3",
            ))
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Optional


@dataclass
class ProgressEvent:
    """A single progress update from a pipeline stage."""

    stage: str
    """Pipeline stage name: copy, transcribe, format, rename, etc."""

    stage_number: int
    """1-based index of the current stage."""

    total_stages: int
    """Total number of stages in the pipeline."""

    status: str
    """One of: started, processing, completed, error, skipped."""

    file_path: Optional[str] = None
    """Path of the file currently being processed."""

    current: Optional[int] = None
    """1-based index of the current item within this stage."""

    total: Optional[int] = None
    """Total items in this stage."""

    message: Optional[str] = None
    """Human-readable status message."""

    detail: Optional[dict] = None
    """Stage-specific metadata (e.g., bytes_copied, error_message)."""

    def to_dict(self) -> dict:
        """Serialize to a dict for JSON/SSE transmission."""
        return asdict(self)


# Type alias for progress callback functions
ProgressCallback = Callable[[ProgressEvent], None]


def print_progress(event: ProgressEvent) -> None:
    """Default progress callback that prints to stdout.

    Used by the CLI. Web UI replaces this with an SSE-emitting callback.
    """
    prefix = f"[{event.stage_number}/{event.total_stages}] {event.stage}"

    if event.status == "started":
        print(f"\n{'=' * 60}")
        print(f"{prefix}: Starting")
        print(f"{'=' * 60}")
    elif event.status == "processing":
        parts = [prefix]
        if event.current is not None and event.total is not None:
            parts.append(f"({event.current}/{event.total})")
        if event.message:
            parts.append(f"— {event.message}")
        elif event.file_path:
            parts.append(f"— {event.file_path}")
        print("  ".join(parts))
    elif event.status == "completed":
        print(f"{prefix}: Done")
    elif event.status == "error":
        msg = event.message or event.file_path or "unknown error"
        print(f"{prefix}: ERROR — {msg}")
    elif event.status == "skipped":
        msg = event.message or "nothing to do"
        print(f"{prefix}: Skipped — {msg}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_progress.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add familyarchive/progress.py tests/test_progress.py
git commit -m "feat: add progress callback protocol

- ProgressEvent dataclass with stage, status, file, and counter fields
- ProgressCallback type alias for pipeline integration
- print_progress() default callback for CLI output
- to_dict() for JSON/SSE serialization in web UI
- Full test coverage for event creation, serialization, and callbacks"
```

---

## Task 3: Storage Abstraction

**Files:**
- Create: `familyarchive/storage/__init__.py`
- Create: `familyarchive/storage/base.py`
- Create: `familyarchive/storage/local.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_storage.py`:

```python
"""Tests for storage abstraction layer."""

import pytest
from pathlib import Path

from familyarchive.storage import get_storage, LocalStorage
from familyarchive.storage.base import StorageBackend


def test_storage_backend_is_abstract():
    """StorageBackend cannot be instantiated directly."""
    with pytest.raises(TypeError):
        StorageBackend()


def test_local_storage_implements_interface(tmp_path):
    """LocalStorage implements all StorageBackend methods."""
    storage = LocalStorage(root=tmp_path)
    assert isinstance(storage, StorageBackend)


def test_local_storage_read_write(tmp_path):
    """LocalStorage can write and read files."""
    storage = LocalStorage(root=tmp_path)
    storage.write("test/hello.txt", b"hello world")
    data = storage.read("test/hello.txt")
    assert data == b"hello world"


def test_local_storage_exists(tmp_path):
    """LocalStorage.exists() reports file presence correctly."""
    storage = LocalStorage(root=tmp_path)
    assert not storage.exists("missing.txt")
    storage.write("present.txt", b"here")
    assert storage.exists("present.txt")


def test_local_storage_delete(tmp_path):
    """LocalStorage.delete() removes files."""
    storage = LocalStorage(root=tmp_path)
    storage.write("doomed.txt", b"bye")
    assert storage.exists("doomed.txt")
    storage.delete("doomed.txt")
    assert not storage.exists("doomed.txt")


def test_local_storage_list(tmp_path):
    """LocalStorage.list_files() returns relative paths."""
    storage = LocalStorage(root=tmp_path)
    storage.write("a.txt", b"a")
    storage.write("sub/b.txt", b"b")
    storage.write("sub/c.txt", b"c")

    files = sorted(storage.list_files(""))
    assert "a.txt" in files
    assert "sub/b.txt" in files or "sub\\b.txt" in files

    sub_files = sorted(storage.list_files("sub"))
    assert len(sub_files) == 2


def test_local_storage_resolve(tmp_path):
    """LocalStorage.resolve() returns absolute filesystem path."""
    storage = LocalStorage(root=tmp_path)
    storage.write("doc.pdf", b"pdf data")
    resolved = storage.resolve("doc.pdf")
    assert resolved is not None
    assert Path(resolved).exists()
    assert Path(resolved).read_bytes() == b"pdf data"


def test_local_storage_resolve_missing(tmp_path):
    """LocalStorage.resolve() returns None for missing files."""
    storage = LocalStorage(root=tmp_path)
    assert storage.resolve("nope.txt") is None


def test_local_storage_is_reachable(tmp_path):
    """LocalStorage.is_reachable() checks if root exists."""
    storage = LocalStorage(root=tmp_path)
    assert storage.is_reachable()

    gone_storage = LocalStorage(root=tmp_path / "nonexistent")
    assert not gone_storage.is_reachable()


def test_get_storage_returns_local(tmp_path):
    """get_storage() returns LocalStorage for local config."""
    storage = get_storage({"type": "local", "root": str(tmp_path)})
    assert isinstance(storage, LocalStorage)


def test_get_storage_unknown_type():
    """get_storage() raises for unknown storage types."""
    with pytest.raises(ValueError, match="Unknown storage type"):
        get_storage({"type": "s3", "bucket": "test"})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create the storage package**

Create `familyarchive/storage/__init__.py`:

```python
"""
Storage abstraction for the Family Archive.

Provides a uniform interface for reading/writing archive files
regardless of whether they live on local disk or cloud storage.

Usage:
    from familyarchive.storage import get_storage, LocalStorage

    storage = get_storage({"type": "local", "root": "/path/to/archive"})
    storage.write("Letters/letter.pdf", data)
    content = storage.read("Letters/letter.pdf")
"""

from .base import StorageBackend
from .local import LocalStorage

__all__ = ["StorageBackend", "LocalStorage", "get_storage"]


def get_storage(config: dict) -> StorageBackend:
    """Create a storage backend from configuration.

    Args:
        config: Dict with "type" key. For local: {"type": "local", "root": "/path"}.

    Returns:
        A StorageBackend instance.
    """
    storage_type = config.get("type", "local")
    if storage_type == "local":
        return LocalStorage(root=config["root"])
    else:
        raise ValueError(
            f"Unknown storage type: {storage_type!r}. "
            f"Available: local. (S3 support planned for cloud mode.)"
        )
```

Create `familyarchive/storage/base.py`:

```python
"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Interface for archive file storage.

    All paths are relative to the storage root (e.g., "Letters/letter.pdf").
    Implementations handle the actual I/O (local disk, S3, etc.).
    """

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read a file and return its contents as bytes."""

    @abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Write data to a file, creating parent directories as needed."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check whether a file exists."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete a file. No error if it doesn't exist."""

    @abstractmethod
    def list_files(self, prefix: str) -> list[str]:
        """List files under a prefix, returning relative paths."""

    @abstractmethod
    def resolve(self, path: str) -> str | None:
        """Resolve to an absolute path or URL for direct access.

        Returns None if the file doesn't exist or the source is unreachable.
        For local storage: returns filesystem path.
        For S3: returns a presigned URL.
        """

    @abstractmethod
    def is_reachable(self) -> bool:
        """Check whether the storage backend is accessible.

        For local: checks if root directory exists.
        For S3: checks if bucket is accessible.
        """
```

Create `familyarchive/storage/local.py`:

```python
"""Local filesystem storage backend."""

from pathlib import Path
from .base import StorageBackend


class LocalStorage(StorageBackend):
    """Storage backend for local filesystem.

    All paths are relative to the root directory.
    """

    def __init__(self, root: str | Path):
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def read(self, path: str) -> bytes:
        return (self._root / path).read_bytes()

    def write(self, path: str, data: bytes) -> None:
        full_path = self._root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)

    def exists(self, path: str) -> bool:
        return (self._root / path).exists()

    def delete(self, path: str) -> None:
        full_path = self._root / path
        if full_path.exists():
            full_path.unlink()

    def list_files(self, prefix: str) -> list[str]:
        search_root = self._root / prefix if prefix else self._root
        if not search_root.exists():
            return []
        return [
            str(p.relative_to(self._root)).replace("\\", "/")
            for p in search_root.rglob("*")
            if p.is_file()
        ]

    def resolve(self, path: str) -> str | None:
        full_path = self._root / path
        if full_path.exists():
            return str(full_path.resolve())
        return None

    def is_reachable(self) -> bool:
        return self._root.exists()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add familyarchive/storage/ tests/test_storage.py
git commit -m "feat: add storage abstraction layer

- StorageBackend ABC defining read/write/exists/delete/list/resolve interface
- LocalStorage implementation for filesystem-based archives
- is_reachable() for graceful degradation when source unavailable
- resolve() returns absolute path (local) or presigned URL (future S3)
- get_storage() factory function driven by config dict
- Full test coverage for LocalStorage operations"
```

---

## Task 4: Entity Schema and CRUD

**Files:**
- Create: `familyarchive/entities/__init__.py`
- Create: `familyarchive/entities/models.py`
- Create: `familyarchive/entities/db.py`
- Modify: `familyarchive/core/db.py` (bump SCHEMA_VERSION, add migration)
- Create: `tests/test_entities.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entities.py`:

```python
"""Tests for entity schema and CRUD operations."""

import sqlite3
import pytest
from pathlib import Path

from familyarchive.core.db import get_db, close_db
from familyarchive.entities.models import Person, Location, Event, Timeframe, Tag
from familyarchive.entities.db import (
    init_entity_schema,
    create_person,
    get_person,
    update_person,
    delete_person,
    list_people,
    create_location,
    get_location,
    list_locations,
    create_event,
    get_event,
    list_events,
    create_timeframe,
    get_timeframe,
    create_tag,
    get_tag,
    get_or_create_tag,
    list_tags,
    link_entity_to_file,
    get_file_entities,
    get_entity_files,
    unlink_entity_from_file,
    create_relationship,
    get_relationships,
)


@pytest.fixture()
def db(tmp_path):
    """Create a test database with entity schema."""
    dest = tmp_path / "archive"
    dest.mkdir()
    conn = get_db(str(dest))
    init_entity_schema(conn)
    yield conn
    close_db(conn)


# ── Person CRUD ──────────────────────────────────────────────────────────

def test_create_and_get_person(db):
    pid = create_person(db, name="Rose Smith", birth_date="1920-03-15", birth_date_precision="exact")
    person = get_person(db, pid)
    assert person.name == "Rose Smith"
    assert person.birth_date == "1920-03-15"
    assert person.birth_date_precision == "exact"
    assert person.id == pid


def test_person_approximate_dates(db):
    """People can have approximate birth/death dates."""
    pid = create_person(
        db, name="Great Grandpa",
        birth_date="1880-01-01", birth_date_precision="year",
        death_date="1960-01-01", death_date_precision="decade",
    )
    person = get_person(db, pid)
    assert person.birth_date_precision == "year"
    assert person.death_date_precision == "decade"


def test_update_person(db):
    pid = create_person(db, name="Rose Smith")
    update_person(db, pid, death_date="2005-11-20", notes="Grandmother")
    person = get_person(db, pid)
    assert person.death_date == "2005-11-20"
    assert person.notes == "Grandmother"
    assert person.name == "Rose Smith"


def test_delete_person(db):
    pid = create_person(db, name="Temporary")
    delete_person(db, pid)
    assert get_person(db, pid) is None


def test_list_people(db):
    create_person(db, name="Alice")
    create_person(db, name="Bob")
    create_person(db, name="Charlie")
    people = list_people(db)
    assert len(people) == 3
    names = [p.name for p in people]
    assert "Alice" in names


def test_list_people_search(db):
    create_person(db, name="Alice Smith")
    create_person(db, name="Bob Jones")
    results = list_people(db, search="smith")
    assert len(results) == 1
    assert results[0].name == "Alice Smith"


# ── Location CRUD ────────────────────────────────────────────────────────

def test_create_and_get_location(db):
    lid = create_location(db, name="Springfield, IL", state="Illinois", precision="city")
    loc = get_location(db, lid)
    assert loc.name == "Springfield, IL"
    assert loc.state == "Illinois"
    assert loc.precision == "city"


def test_location_approximate(db):
    """Locations can have approximate precision."""
    lid = create_location(db, name="Somewhere in Utah", state="Utah", precision="state")
    loc = get_location(db, lid)
    assert loc.precision == "state"
    assert loc.city is None


def test_list_locations(db):
    create_location(db, name="Springfield")
    create_location(db, name="Shelbyville")
    locs = list_locations(db)
    assert len(locs) == 2


# ── Event CRUD ───────────────────────────────────────────────────────────

def test_create_and_get_event(db):
    lid = create_location(db, name="Grandma's house")
    eid = create_event(
        db, name="1996 Family Reunion",
        event_type="reunion",
        start_date="1996-07-04",
        end_date="1996-07-06",
        location_id=lid,
    )
    event = get_event(db, eid)
    assert event.name == "1996 Family Reunion"
    assert event.event_type == "reunion"
    assert event.location_id == lid


def test_list_events(db):
    create_event(db, name="Wedding")
    create_event(db, name="Funeral")
    events = list_events(db)
    assert len(events) == 2


# ── Timeframe CRUD ───────────────────────────────────────────────────────

def test_create_and_get_timeframe(db):
    pid = create_person(db, name="Mark")
    tid = create_timeframe(
        db, name="7th Grade",
        start_date="1989-09-01",
        end_date="1990-06-15",
        person_id=pid,
    )
    tf = get_timeframe(db, tid)
    assert tf.name == "7th Grade"
    assert tf.person_id == pid


# ── Tag CRUD ─────────────────────────────────────────────────────────────

def test_create_and_get_tag(db):
    tid = create_tag(db, name="Scout Camp", color="#2ecc71")
    tag = get_tag(db, tid)
    assert tag.name == "Scout Camp"
    assert tag.color == "#2ecc71"


def test_get_or_create_tag(db):
    tid1 = get_or_create_tag(db, name="Family Reunion")
    tid2 = get_or_create_tag(db, name="Family Reunion")
    assert tid1 == tid2


def test_list_tags(db):
    create_tag(db, name="Tag A")
    create_tag(db, name="Tag B")
    tags = list_tags(db)
    assert len(tags) == 2


# ── Entity ↔ File Linking ────────────────────────────────────────────────

def test_link_entity_to_file(db):
    pid = create_person(db, name="Rose")
    # Insert a fake file record
    db.execute(
        "INSERT INTO files (path, filename, folder, file_type, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Letters/letter.pdf", "letter.pdf", "Letters", "document", 1024),
    )
    file_id = db.execute("SELECT id FROM files WHERE path = ?", ("Letters/letter.pdf",)).fetchone()[0]

    link_entity_to_file(db, "person", pid, file_id, confidence="manual")

    # Check from file side
    entities = get_file_entities(db, file_id)
    assert len(entities) == 1
    assert entities[0]["entity_type"] == "person"
    assert entities[0]["entity_id"] == pid

    # Check from entity side
    files = get_entity_files(db, "person", pid)
    assert len(files) == 1
    assert files[0]["file_id"] == file_id


def test_unlink_entity_from_file(db):
    pid = create_person(db, name="Rose")
    db.execute(
        "INSERT INTO files (path, filename, folder, file_type, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Letters/letter.pdf", "letter.pdf", "Letters", "document", 1024),
    )
    file_id = db.execute("SELECT id FROM files WHERE path = ?", ("Letters/letter.pdf",)).fetchone()[0]

    link_entity_to_file(db, "person", pid, file_id)
    unlink_entity_from_file(db, "person", pid, file_id)
    assert len(get_file_entities(db, file_id)) == 0


# ── Relationships ────────────────────────────────────────────────────────

def test_create_relationship(db):
    pid1 = create_person(db, name="Rose Smith")
    pid2 = create_person(db, name="Mark Smith")
    create_relationship(db, pid1, pid2, "parent")

    rels = get_relationships(db, pid1)
    assert len(rels) == 1
    assert rels[0]["related_person_id"] == pid2
    assert rels[0]["relationship_type"] == "parent"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_entities.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'familyarchive.entities'`

- [ ] **Step 3: Create entity models**

Create `familyarchive/entities/__init__.py`:

```python
"""
Entity management for the Family Archive.

Provides people, locations, events, timeframes, and tags as first-class
archive metadata. Entities are stored in .archive.db alongside files
and transcripts.

Usage:
    from familyarchive.entities import create_person, link_entity_to_file
"""

from .db import (
    init_entity_schema,
    create_person, get_person, update_person, delete_person, list_people,
    create_location, get_location, list_locations,
    create_event, get_event, list_events,
    create_timeframe, get_timeframe,
    create_tag, get_tag, get_or_create_tag, list_tags,
    link_entity_to_file, get_file_entities, get_entity_files, unlink_entity_from_file,
    create_relationship, get_relationships,
)
from .models import Person, Location, Event, Timeframe, Tag

__all__ = [
    "init_entity_schema",
    "Person", "create_person", "get_person", "update_person", "delete_person", "list_people",
    "Location", "create_location", "get_location", "list_locations",
    "Event", "create_event", "get_event", "list_events",
    "Timeframe", "create_timeframe", "get_timeframe",
    "Tag", "create_tag", "get_tag", "get_or_create_tag", "list_tags",
    "link_entity_to_file", "get_file_entities", "get_entity_files", "unlink_entity_from_file",
    "create_relationship", "get_relationships",
]
```

Create `familyarchive/entities/models.py`:

```python
"""Entity dataclasses for the Family Archive."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Person:
    id: int
    name: str
    alternate_names: Optional[list[str]] = None
    birth_date: Optional[str] = None
    birth_date_precision: Optional[str] = None   # "exact", "month", "year", "decade", "approximate"
    death_date: Optional[str] = None
    death_date_precision: Optional[str] = None
    notes: Optional[str] = None
    source_connector: Optional[str] = None
    external_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Location:
    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    precision: Optional[str] = None  # "exact", "city", "state", "country", "approximate"
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Event:
    id: int
    name: str
    event_type: Optional[str] = None
    start_date: Optional[str] = None
    start_date_precision: Optional[str] = None  # "exact", "month", "year", "decade", "approximate"
    end_date: Optional[str] = None
    end_date_precision: Optional[str] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Timeframe:
    id: int
    name: str
    start_date: Optional[str] = None
    start_date_precision: Optional[str] = None  # "exact", "month", "year", "decade", "approximate"
    end_date: Optional[str] = None
    end_date_precision: Optional[str] = None
    person_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Tag:
    id: int
    name: str
    color: Optional[str] = None
    created_at: Optional[str] = None
```

- [ ] **Step 4: Create entity database operations**

Create `familyarchive/entities/db.py`:

```python
"""Entity CRUD operations and schema management."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .models import Person, Location, Event, Timeframe, Tag


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schema ───────────────────────────────────────────────────────────────

ENTITY_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS entities_people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    alternate_names TEXT,
    birth_date TEXT,
    birth_date_precision TEXT,
    death_date TEXT,
    death_date_precision TEXT,
    notes TEXT,
    source_connector TEXT,
    external_id TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entities_locations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    latitude REAL,
    longitude REAL,
    precision TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entities_events (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    event_type TEXT,
    start_date TEXT,
    start_date_precision TEXT,
    end_date TEXT,
    end_date_precision TEXT,
    location_id INTEGER REFERENCES entities_locations(id),
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entities_timeframes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT,
    start_date_precision TEXT,
    end_date TEXT,
    end_date_precision TEXT,
    person_id INTEGER REFERENCES entities_people(id),
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS entity_files (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL REFERENCES files(id),
    confidence TEXT,
    created_at TEXT,
    UNIQUE(entity_type, entity_id, file_id)
);

CREATE TABLE IF NOT EXISTS people_relationships (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES entities_people(id),
    related_person_id INTEGER NOT NULL REFERENCES entities_people(id),
    relationship_type TEXT NOT NULL,
    created_at TEXT,
    UNIQUE(person_id, related_person_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS connected_sources (
    id INTEGER PRIMARY KEY,
    connector_name TEXT NOT NULL,
    display_name TEXT,
    status TEXT DEFAULT 'active',
    last_sync_at TEXT,
    item_count INTEGER DEFAULT 0,
    created_at TEXT
);
"""


def init_entity_schema(conn: sqlite3.Connection) -> None:
    """Create entity tables if they don't exist."""
    conn.executescript(ENTITY_TABLES_SQL)
    conn.commit()


# ── Person CRUD ──────────────────────────────────────────────────────────

def create_person(
    conn: sqlite3.Connection,
    name: str,
    alternate_names: list[str] | None = None,
    birth_date: str | None = None,
    birth_date_precision: str | None = None,
    death_date: str | None = None,
    death_date_precision: str | None = None,
    notes: str | None = None,
    source_connector: str | None = None,
    external_id: str | None = None,
) -> int:
    now = _now()
    alt_json = json.dumps(alternate_names) if alternate_names else None
    cur = conn.execute(
        "INSERT INTO entities_people "
        "(name, alternate_names, birth_date, birth_date_precision, "
        "death_date, death_date_precision, notes, "
        "source_connector, external_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, alt_json, birth_date, birth_date_precision,
         death_date, death_date_precision, notes,
         source_connector, external_id, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_person(conn: sqlite3.Connection, person_id: int) -> Person | None:
    row = conn.execute(
        "SELECT * FROM entities_people WHERE id = ?", (person_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_person(row)


def update_person(conn: sqlite3.Connection, person_id: int, **kwargs) -> None:
    allowed = {"name", "alternate_names", "birth_date", "birth_date_precision",
               "death_date", "death_date_precision", "notes", "source_connector", "external_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if "alternate_names" in updates and isinstance(updates["alternate_names"], list):
        updates["alternate_names"] = json.dumps(updates["alternate_names"])
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [person_id]
    conn.execute(f"UPDATE entities_people SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_person(conn: sqlite3.Connection, person_id: int) -> None:
    conn.execute("DELETE FROM entity_files WHERE entity_type = 'person' AND entity_id = ?", (person_id,))
    conn.execute("DELETE FROM people_relationships WHERE person_id = ? OR related_person_id = ?", (person_id, person_id))
    conn.execute("DELETE FROM entities_people WHERE id = ?", (person_id,))
    conn.commit()


def list_people(conn: sqlite3.Connection, search: str | None = None) -> list[Person]:
    if search:
        rows = conn.execute(
            "SELECT * FROM entities_people WHERE name LIKE ? ORDER BY name",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entities_people ORDER BY name").fetchall()
    return [_row_to_person(r) for r in rows]


def _row_to_person(row) -> Person:
    alt = json.loads(row[2]) if row[2] else None
    return Person(
        id=row[0], name=row[1], alternate_names=alt,
        birth_date=row[3], birth_date_precision=row[4],
        death_date=row[5], death_date_precision=row[6],
        notes=row[7], source_connector=row[8], external_id=row[9],
        created_at=row[10], updated_at=row[11],
    )


# ── Location CRUD ────────────────────────────────────────────────────────

def create_location(
    conn: sqlite3.Connection,
    name: str,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    precision: str | None = None,
    notes: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO entities_locations "
        "(name, address, city, state, country, latitude, longitude, precision, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, address, city, state, country, latitude, longitude, precision, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_location(conn: sqlite3.Connection, location_id: int) -> Location | None:
    row = conn.execute(
        "SELECT * FROM entities_locations WHERE id = ?", (location_id,)
    ).fetchone()
    if not row:
        return None
    return Location(
        id=row[0], name=row[1], address=row[2], city=row[3],
        state=row[4], country=row[5], latitude=row[6], longitude=row[7],
        precision=row[8], notes=row[9], created_at=row[10], updated_at=row[11],
    )


def list_locations(conn: sqlite3.Connection, search: str | None = None) -> list[Location]:
    if search:
        rows = conn.execute(
            "SELECT * FROM entities_locations WHERE name LIKE ? ORDER BY name",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entities_locations ORDER BY name").fetchall()
    return [
        Location(id=r[0], name=r[1], address=r[2], city=r[3], state=r[4],
                 country=r[5], latitude=r[6], longitude=r[7], precision=r[8],
                 notes=r[9], created_at=r[10], updated_at=r[11])
        for r in rows
    ]


# ── Event CRUD ───────────────────────────────────────────────────────────

def create_event(
    conn: sqlite3.Connection,
    name: str,
    event_type: str | None = None,
    start_date: str | None = None,
    start_date_precision: str | None = None,
    end_date: str | None = None,
    end_date_precision: str | None = None,
    location_id: int | None = None,
    notes: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO entities_events "
        "(name, event_type, start_date, start_date_precision, "
        "end_date, end_date_precision, location_id, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, event_type, start_date, start_date_precision,
         end_date, end_date_precision, location_id, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_event(conn: sqlite3.Connection, event_id: int) -> Event | None:
    row = conn.execute(
        "SELECT * FROM entities_events WHERE id = ?", (event_id,)
    ).fetchone()
    if not row:
        return None
    return Event(
        id=row[0], name=row[1], event_type=row[2], start_date=row[3],
        start_date_precision=row[4], end_date=row[5], end_date_precision=row[6],
        location_id=row[7], notes=row[8],
        created_at=row[9], updated_at=row[10],
    )


def list_events(conn: sqlite3.Connection, search: str | None = None) -> list[Event]:
    if search:
        rows = conn.execute(
            "SELECT * FROM entities_events WHERE name LIKE ? ORDER BY start_date",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entities_events ORDER BY start_date").fetchall()
    return [
        Event(id=r[0], name=r[1], event_type=r[2], start_date=r[3],
              start_date_precision=r[4], end_date=r[5], end_date_precision=r[6],
              location_id=r[7], notes=r[8],
              created_at=r[9], updated_at=r[10])
        for r in rows
    ]


# ── Timeframe CRUD ───────────────────────────────────────────────────────

def create_timeframe(
    conn: sqlite3.Connection,
    name: str,
    start_date: str | None = None,
    start_date_precision: str | None = None,
    end_date: str | None = None,
    end_date_precision: str | None = None,
    person_id: int | None = None,
    notes: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO entities_timeframes "
        "(name, start_date, start_date_precision, end_date, end_date_precision, "
        "person_id, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, start_date, start_date_precision, end_date, end_date_precision,
         person_id, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_timeframe(conn: sqlite3.Connection, timeframe_id: int) -> Timeframe | None:
    row = conn.execute(
        "SELECT * FROM entities_timeframes WHERE id = ?", (timeframe_id,)
    ).fetchone()
    if not row:
        return None
    return Timeframe(
        id=row[0], name=row[1], start_date=row[2], start_date_precision=row[3],
        end_date=row[4], end_date_precision=row[5],
        person_id=row[6], notes=row[7], created_at=row[8], updated_at=row[9],
    )


# ── Tag CRUD ─────────────────────────────────────────────────────────────

def create_tag(
    conn: sqlite3.Connection,
    name: str,
    color: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO tags (name, color, created_at) VALUES (?, ?, ?)",
        (name, color, now),
    )
    conn.commit()
    return cur.lastrowid


def get_tag(conn: sqlite3.Connection, tag_id: int) -> Tag | None:
    row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not row:
        return None
    return Tag(id=row[0], name=row[1], color=row[2], created_at=row[3])


def get_or_create_tag(conn: sqlite3.Connection, name: str, color: str | None = None) -> int:
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    return create_tag(conn, name=name, color=color)


def list_tags(conn: sqlite3.Connection) -> list[Tag]:
    rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
    return [Tag(id=r[0], name=r[1], color=r[2], created_at=r[3]) for r in rows]


# ── Entity ↔ File Linking ────────────────────────────────────────────────

def link_entity_to_file(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    file_id: int,
    confidence: str = "manual",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO entity_files "
        "(entity_type, entity_id, file_id, confidence, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity_type, entity_id, file_id, confidence, _now()),
    )
    conn.commit()


def unlink_entity_from_file(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    file_id: int,
) -> None:
    conn.execute(
        "DELETE FROM entity_files "
        "WHERE entity_type = ? AND entity_id = ? AND file_id = ?",
        (entity_type, entity_id, file_id),
    )
    conn.commit()


def get_file_entities(conn: sqlite3.Connection, file_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT entity_type, entity_id, confidence, created_at "
        "FROM entity_files WHERE file_id = ?",
        (file_id,),
    ).fetchall()
    return [
        {"entity_type": r[0], "entity_id": r[1], "confidence": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_entity_files(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT file_id, confidence, created_at "
        "FROM entity_files WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchall()
    return [
        {"file_id": r[0], "confidence": r[1], "created_at": r[2]}
        for r in rows
    ]


# ── Relationships ────────────────────────────────────────────────────────

def create_relationship(
    conn: sqlite3.Connection,
    person_id: int,
    related_person_id: int,
    relationship_type: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO people_relationships "
        "(person_id, related_person_id, relationship_type, created_at) "
        "VALUES (?, ?, ?, ?)",
        (person_id, related_person_id, relationship_type, _now()),
    )
    conn.commit()


def get_relationships(conn: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT related_person_id, relationship_type, created_at "
        "FROM people_relationships WHERE person_id = ?",
        (person_id,),
    ).fetchall()
    return [
        {"related_person_id": r[0], "relationship_type": r[1], "created_at": r[2]}
        for r in rows
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_entities.py -v
```

Expected: All entity tests PASS.

- [ ] **Step 6: Integrate entity schema into core db init**

Modify `familyarchive/core/db.py` — in the `init_schema()` function, after existing table creation, add:

```python
# At the end of init_schema(), add:
from familyarchive.entities.db import init_entity_schema
init_entity_schema(conn)
```

Also bump `SCHEMA_VERSION = 3` at the top of the file.

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS, including existing db tests.

- [ ] **Step 8: Commit**

```bash
git add familyarchive/entities/ tests/test_entities.py familyarchive/core/db.py
git commit -m "feat: add entity schema — people, locations, events, timeframes, tags

- Person CRUD with alternate names, birth/death dates, connector source
- Location CRUD with optional geocoding fields
- Event CRUD with type, date range, and location reference
- Timeframe CRUD for date range labels (e.g., '7th Grade')
- Tag CRUD with get_or_create for idempotent tagging
- Entity ↔ file junction table with confidence tracking
- People relationships table (parent, child, spouse, sibling)
- Connected sources table for connector metadata
- Schema auto-initialized via init_entity_schema()
- Integrated into core db init, schema version bumped to 3
- Full test coverage for all CRUD operations and linking"
```

---

## Task 5: Connector Base Class and Registry

**Files:**
- Create: `familyarchive/connectors/__init__.py`
- Create: `familyarchive/connectors/base.py`
- Create: `tests/test_connectors.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_connectors.py`:

```python
"""Tests for connector base class and registry."""

import pytest

from familyarchive.connectors.base import (
    Connector,
    AuthType,
    DataType,
    Collection,
    Item,
    ConnectorRegistry,
)
from familyarchive.connectors import list_connectors, get_connector


def test_connector_is_abstract():
    """Connector cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Connector()


def test_concrete_connector():
    """A concrete connector implementing all methods can be instantiated."""

    class FakeConnector(Connector):
        name = "fake"
        display_name = "Fake Source"
        auth_type = AuthType.FILE_IMPORT
        data_types = [DataType.DOCUMENTS]

        def get_auth_url(self): return ""
        def handle_callback(self, code): return {}
        def refresh_token(self, creds): return creds
        def test_connection(self, creds): return True
        def list_collections(self, creds): return []
        def list_items(self, creds, collection_id, page_token=None): return []
        def get_item_preview(self, creds, item_id): return None
        def download_items(self, creds, item_ids, on_progress=None): return []
        def map_to_entities(self, item): return []
        def map_to_archive_file(self, item): return None

    conn = FakeConnector()
    assert conn.name == "fake"
    assert conn.display_name == "Fake Source"
    assert conn.auth_type == AuthType.FILE_IMPORT


def test_registry_register_and_list():
    """Connectors can be registered and listed."""
    registry = ConnectorRegistry()

    class TestConn(Connector):
        name = "test_source"
        display_name = "Test Source"
        auth_type = AuthType.API_KEY
        data_types = [DataType.PHOTOS]

        def get_auth_url(self): return ""
        def handle_callback(self, code): return {}
        def refresh_token(self, creds): return creds
        def test_connection(self, creds): return True
        def list_collections(self, creds): return []
        def list_items(self, creds, collection_id, page_token=None): return []
        def get_item_preview(self, creds, item_id): return None
        def download_items(self, creds, item_ids, on_progress=None): return []
        def map_to_entities(self, item): return []
        def map_to_archive_file(self, item): return None

    registry.register(TestConn)
    assert "test_source" in registry.list_names()
    assert registry.get("test_source") is TestConn


def test_registry_get_unknown():
    """Getting an unregistered connector returns None."""
    registry = ConnectorRegistry()
    assert registry.get("nonexistent") is None


def test_auth_type_enum():
    """AuthType enum has expected values."""
    assert AuthType.OAUTH2.value == "oauth2"
    assert AuthType.API_KEY.value == "api_key"
    assert AuthType.FILE_IMPORT.value == "file_import"
    assert AuthType.BROWSER_SESSION.value == "browser_session"


def test_data_type_enum():
    """DataType enum has expected values."""
    assert DataType.PHOTOS.value == "photos"
    assert DataType.MESSAGES.value == "messages"
    assert DataType.PEOPLE.value == "people"
    assert DataType.DOCUMENTS.value == "documents"
    assert DataType.ARTIFACTS.value == "artifacts"


def test_collection_dataclass():
    """Collection holds connector browsing data."""
    coll = Collection(id="album-1", name="Vacation 2024", item_count=42)
    assert coll.id == "album-1"
    assert coll.item_count == 42


def test_item_dataclass():
    """Item holds a single importable record."""
    item = Item(
        id="photo-123",
        name="sunset.jpg",
        item_type=DataType.PHOTOS,
        date="2024-07-04",
        thumbnail_url="https://example.com/thumb.jpg",
    )
    assert item.id == "photo-123"
    assert item.item_type == DataType.PHOTOS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_connectors.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create the connectors package**

Create `familyarchive/connectors/base.py`:

```python
"""Connector base class and data models for external service integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class AuthType(Enum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    FILE_IMPORT = "file_import"
    BROWSER_SESSION = "browser_session"


class DataType(Enum):
    PHOTOS = "photos"
    MESSAGES = "messages"
    PEOPLE = "people"
    DOCUMENTS = "documents"
    ARTIFACTS = "artifacts"


@dataclass
class Collection:
    """A browsable group of items (album, folder, thread, etc.)."""
    id: str
    name: str
    item_count: int = 0
    metadata: Optional[dict] = None


@dataclass
class Item:
    """A single importable record from an external service."""
    id: str
    name: str
    item_type: DataType
    date: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: Optional[dict] = None


@dataclass
class DownloadedItem:
    """An item that has been downloaded and is ready for ingestion."""
    item: Item
    local_path: str
    data: Optional[bytes] = None


class Connector(ABC):
    """Base class for external service connectors.

    Each connector implements this interface to enable browsing, selecting,
    and importing data from an external service into the archive.

    Subclasses must set the class attributes: name, display_name, auth_type, data_types.
    """

    name: str
    display_name: str
    auth_type: AuthType
    data_types: list[DataType]

    # ── Auth lifecycle ───────────────────────────────────────────────

    @abstractmethod
    def get_auth_url(self) -> str:
        """Return the OAuth redirect URL (or empty string for non-OAuth)."""

    @abstractmethod
    def handle_callback(self, code: str) -> dict:
        """Exchange an auth code for credentials."""

    @abstractmethod
    def refresh_token(self, creds: dict) -> dict:
        """Refresh expired credentials."""

    @abstractmethod
    def test_connection(self, creds: dict) -> bool:
        """Verify that credentials are valid."""

    # ── Browse & discover ────────────────────────────────────────────

    @abstractmethod
    def list_collections(self, creds: dict) -> list[Collection]:
        """List available collections (albums, folders, threads)."""

    @abstractmethod
    def list_items(
        self, creds: dict, collection_id: str, page_token: str | None = None
    ) -> list[Item]:
        """List items in a collection."""

    @abstractmethod
    def get_item_preview(self, creds: dict, item_id: str) -> Any:
        """Get a preview (thumbnail + metadata) for a single item."""

    # ── Import ───────────────────────────────────────────────────────

    @abstractmethod
    def download_items(
        self, creds: dict, item_ids: list[str], on_progress=None
    ) -> list[DownloadedItem]:
        """Download selected items for ingestion."""

    # ── Map to archive ───────────────────────────────────────────────

    @abstractmethod
    def map_to_entities(self, item: Item) -> list[dict]:
        """Extract entity data (people, places, dates) from an item."""

    @abstractmethod
    def map_to_archive_file(self, item: DownloadedItem) -> Any:
        """Convert a downloaded item to the standard ingest format."""


class ConnectorRegistry:
    """Registry of available connectors.

    Connectors register themselves via register(). The web UI queries
    the registry to show available connectors in the 'Add Source' interface.
    """

    def __init__(self):
        self._connectors: dict[str, type[Connector]] = {}

    def register(self, connector_class: type[Connector]) -> type[Connector]:
        """Register a connector class. Can be used as a decorator."""
        self._connectors[connector_class.name] = connector_class
        return connector_class

    def get(self, name: str) -> type[Connector] | None:
        """Get a connector class by name."""
        return self._connectors.get(name)

    def list_names(self) -> list[str]:
        """List all registered connector names."""
        return list(self._connectors.keys())

    def list_all(self) -> list[dict]:
        """List all connectors with metadata."""
        return [
            {
                "name": cls.name,
                "display_name": cls.display_name,
                "auth_type": cls.auth_type.value,
                "data_types": [dt.value for dt in cls.data_types],
            }
            for cls in self._connectors.values()
        ]


# Global registry instance
_registry = ConnectorRegistry()


def register_connector(cls: type[Connector]) -> type[Connector]:
    """Decorator to register a connector with the global registry."""
    _registry.register(cls)
    return cls
```

Create `familyarchive/connectors/__init__.py`:

```python
"""
Connector framework for external service integration.

Provides a pluggable system for importing data from external services
(Google Photos, FamilySearch, Facebook, etc.) into the archive.

Usage:
    from familyarchive.connectors import list_connectors, get_connector
    from familyarchive.connectors.base import Connector, register_connector
"""

from .base import (
    Connector,
    ConnectorRegistry,
    AuthType,
    DataType,
    Collection,
    Item,
    DownloadedItem,
    _registry,
    register_connector,
)

__all__ = [
    "Connector", "ConnectorRegistry", "AuthType", "DataType",
    "Collection", "Item", "DownloadedItem",
    "register_connector", "list_connectors", "get_connector",
]


def list_connectors() -> list[dict]:
    """List all registered connectors with metadata."""
    return _registry.list_all()


def get_connector(name: str) -> type[Connector] | None:
    """Get a registered connector class by name."""
    return _registry.get(name)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_connectors.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add familyarchive/connectors/ tests/test_connectors.py
git commit -m "feat: add connector base class and registry

- Connector ABC defining auth, browse, download, and mapping interface
- AuthType enum: OAUTH2, API_KEY, FILE_IMPORT, BROWSER_SESSION
- DataType enum: PHOTOS, MESSAGES, PEOPLE, DOCUMENTS, ARTIFACTS
- Collection and Item dataclasses for browsing external sources
- ConnectorRegistry with register/get/list operations
- register_connector decorator for auto-registration
- Global registry + list_connectors()/get_connector() module functions
- Full test coverage for ABC enforcement, registry, and data models"
```

---

## Task 6: Verify full test suite and pip installability

**Files:**
- No new files — integration verification

- [ ] **Step 1: Run full test suite**

```bash
cd D:/HistoryTools
python -m pytest tests/ -v
```

Expected: ALL tests pass. If any fail, fix the import issues before proceeding.

- [ ] **Step 2: Test pip install in editable mode**

```bash
pip install -e ".[all]"
```

Expected: Installs successfully with all dependencies.

- [ ] **Step 3: Verify CLI still works**

```bash
family-archive --help
```

Expected: Shows all commands (ingest, transcribe, search, etc.).

- [ ] **Step 4: Verify library imports work**

```bash
python -c "
from familyarchive.core.config import load_config, load_taxonomy
from familyarchive.core.db import get_db, search, get_stats
from familyarchive.core.ai_client import get_ai_client
from familyarchive.core.extract import extract_file
from familyarchive.core.cost_tracker import CostTracker
from familyarchive.core.rate_limiter import RateLimiter
from familyarchive.core.quality_check import assess_text_quality
from familyarchive.progress import ProgressEvent, print_progress
from familyarchive.storage import get_storage, LocalStorage
from familyarchive.entities import create_person, create_tag, link_entity_to_file
from familyarchive.connectors import list_connectors, get_connector
print('All imports successful')
print(f'Version: {__import__(\"familyarchive\").__version__}')
"
```

Expected: `All imports successful` and `Version: 0.3.0`.

- [ ] **Step 5: Test install from git (simulates what HyperPersonalWeb will do)**

```bash
pip install git+file:///D:/HistoryTools
python -c "import familyarchive; print(familyarchive.__version__)"
```

Expected: `0.3.0`

Then reinstall in editable mode for continued development:

```bash
pip install -e ".[all]"
```

- [ ] **Step 6: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: resolve any import/install issues from package rename"
```

Only commit if there were fixes. If everything passed clean, skip this step.

---

## Summary

| Task | What it does | Files created/modified |
|------|--------------|-----------------------|
| 1 | Rename scripts/ → familyarchive/, fix all imports | ~30 files renamed, pyproject.toml, all tests |
| 2 | Progress callback protocol | `progress.py`, `test_progress.py` |
| 3 | Storage abstraction | `storage/` (3 files), `test_storage.py` |
| 4 | Entity schema + CRUD | `entities/` (3 files), `test_entities.py`, `core/db.py` |
| 5 | Connector base class + registry | `connectors/` (2 files), `test_connectors.py` |
| 6 | Integration verification | No new files — full test + install check |

After SP-0A is complete:
- `pip install git+https://github.com/mmackelprang/HistoryTools.git` works
- All existing tests pass under new import paths
- New modules (progress, storage, entities, connectors) are tested and functional
- HyperPersonalWeb can declare `familyarchive` as a dependency and import everything it needs
