# Core Library Extraction — Design Spec

## Goal

Extract shared infrastructure modules from the flat `scripts/` package into a `scripts/core/` subpackage, creating a clean importable library layer. Pipeline scripts and tests continue to work unchanged via one-liner shim files.

## Architecture

```
scripts/
  core/                    # NEW — shared library modules
    __init__.py            # minimal package marker
    config.py              # config loading, taxonomy, env
    db.py                  # SQLite schema, indexing, search, FTS
    ai_client.py           # unified AI client abstraction
    cost_tracker.py        # API cost tracking
    rate_limiter.py        # token bucket rate limiter
    quality_check.py       # transcript quality assessment
  config.py                # SHIM: from .core.config import *
  db.py                    # SHIM: from .core.db import *
  ai_client.py             # SHIM: from .core.ai_client import *
  cost_tracker.py          # SHIM: from .core.cost_tracker import *
  rate_limiter.py          # SHIM: from .core.rate_limiter import *
  quality_check.py         # SHIM: from .core.quality_check import *
  cli.py                   # unchanged pipeline scripts
  ingest.py                # ...
  ...
```

## Design Principles

- **Zero breakage** — shim files re-export everything from `core/`, so all existing imports (bare `from config import`, relative `from .config import`, test `from scripts.config import`) continue to work unchanged.
- **Minimal churn** — only the 6 infrastructure modules move. All 19+ pipeline scripts, all test files, `pyproject.toml`, and CI are unchanged.
- **Incremental migration** — pipeline scripts can be updated to import directly from `scripts.core` over time, one file at a time. No big-bang migration required.
- **Future rename** — `scripts/` will be renamed to `familyarchive/` when building the Phase 3 web UI. This refactor makes that rename easier by establishing the library/CLI separation first.

## What Moves to `scripts/core/`

| Module | Lines | Role |
|--------|-------|------|
| `config.py` | ~230 | Config loading, taxonomy, env — used by every script |
| `db.py` | ~718 | SQLite schema, indexing, search, FTS — used by CLI, ingest, duplicates, batch |
| `ai_client.py` | ~180 | Unified AI client abstraction — used by transcribe, format, rename, split |
| `cost_tracker.py` | ~120 | API cost tracking — used by ai_client |
| `rate_limiter.py` | ~40 | Token bucket rate limiter — used by transcribe, batch |
| `quality_check.py` | ~100 | Transcript quality assessment — used by transcribe_pdfs |

## What Stays in `scripts/`

All pipeline scripts (unchanged): `cli.py`, `ingest.py`, `organize.py`, `transcribe_pdfs.py`, `transcribe_pdfs_gemini.py`, `gemini_batch.py`, `transcribe_audio.py`, `transcribe_audio_assemblyai.py`, `format_transcripts.py`, `propose_renames.py`, `apply_renames.py`, `detect_dates.py`, `split_propose.py`, `split_apply.py`, `duplicate_detect.py`, `duplicate_manage.py`, `catalog_photos.py`, `generate_report.py`, `init_wizard.py`, `verify_tools.py`, `run_all.py`, `label_speakers.py`

## Shim Pattern

Each original file becomes a one-liner that re-exports from core:

```python
"""Shim — real implementation in scripts/core/config.py"""
from .core.config import *  # noqa: F401,F403
```

The `# noqa` comments suppress linting warnings about wildcard imports — appropriate since shims are intentionally re-exporting everything.

## Internal Import Changes

Core modules that import from each other need their bare imports updated to relative imports:

- `core/ai_client.py`: `from config import load_env` → `from .config import load_env`
- `core/ai_client.py`: `from cost_tracker import get_tracker` → `from .cost_tracker import get_tracker`
- `core/db.py`: no cross-core imports (standalone)
- `core/config.py`: no cross-core imports (standalone)
- `core/cost_tracker.py`: no cross-core imports (standalone)
- `core/rate_limiter.py`: no cross-core imports (standalone)
- `core/quality_check.py`: verify and update if needed

Also remove `sys.path.insert` lines from core modules — they're no longer needed inside a proper package.

## Test Impact

**No existing test changes.** All tests import from `scripts.db`, `scripts.config`, etc., which still work via shims.

**New test file:** `tests/test_core_imports.py` — smoke test verifying:
- Core modules importable directly: `from scripts.core.config import load_config`
- Shims work: `from scripts.config import load_config`
- Both resolve to the same objects

## File Map

### New files
- `scripts/core/__init__.py` — minimal package marker
- `scripts/core/config.py` — moved from `scripts/config.py`
- `scripts/core/db.py` — moved from `scripts/db.py`
- `scripts/core/ai_client.py` — moved from `scripts/ai_client.py`
- `scripts/core/cost_tracker.py` — moved from `scripts/cost_tracker.py`
- `scripts/core/rate_limiter.py` — moved from `scripts/rate_limiter.py`
- `scripts/core/quality_check.py` — moved from `scripts/quality_check.py`
- `tests/test_core_imports.py` — import smoke tests

### Modified files (become shims)
- `scripts/config.py`
- `scripts/db.py`
- `scripts/ai_client.py`
- `scripts/cost_tracker.py`
- `scripts/rate_limiter.py`
- `scripts/quality_check.py`

### Modified files (internal imports)
- `scripts/core/ai_client.py` — relative imports for config and cost_tracker

### Unchanged
- All pipeline scripts (19+ files)
- All existing test files
- `pyproject.toml`
- CI configuration
