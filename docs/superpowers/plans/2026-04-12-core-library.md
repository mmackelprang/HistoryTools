# Core Library Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract 6 shared infrastructure modules into `scripts/core/` subpackage with shim files for backward compatibility, achieving zero breakage across all pipeline scripts and tests.

**Architecture:** Move `config.py`, `db.py`, `ai_client.py`, `cost_tracker.py`, `rate_limiter.py`, `quality_check.py` into `scripts/core/`. Replace originals with one-liner shim files that re-export everything. Fix internal imports within core modules. All existing imports continue to work unchanged.

**Tech Stack:** Python 3.10+, no new dependencies

**Design spec:** `docs/2026-04-12-core-library-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/core/__init__.py` | Minimal package marker |
| `scripts/core/config.py` | Config loading, taxonomy, env (moved from scripts/) |
| `scripts/core/db.py` | SQLite schema, indexing, search, FTS (moved from scripts/) |
| `scripts/core/ai_client.py` | Unified AI client abstraction (moved from scripts/) |
| `scripts/core/cost_tracker.py` | API cost tracking (moved from scripts/) |
| `scripts/core/rate_limiter.py` | Token bucket rate limiter (moved from scripts/) |
| `scripts/core/quality_check.py` | Transcript quality assessment (moved from scripts/) |
| `scripts/config.py` | Shim: re-exports from core |
| `scripts/db.py` | Shim: re-exports from core |
| `scripts/ai_client.py` | Shim: re-exports from core |
| `scripts/cost_tracker.py` | Shim: re-exports from core |
| `scripts/rate_limiter.py` | Shim: re-exports from core |
| `scripts/quality_check.py` | Shim: re-exports from core |
| `tests/test_core_imports.py` | Import smoke tests |

---

### Task 1: Create core package and move config.py

**Files:**
- Create: `scripts/core/__init__.py`
- Create: `scripts/core/config.py` (copy from `scripts/config.py`)
- Modify: `scripts/config.py` (replace with shim)

- [ ] **Step 1: Create the core package directory and __init__.py**

Create `scripts/core/__init__.py`:

```python
"""
Core library for the Family Archive Toolkit.

Shared infrastructure modules used by pipeline scripts and the CLI.
Import from submodules directly: from scripts.core.config import load_config
"""
```

- [ ] **Step 2: Copy config.py to core/**

```bash
cp scripts/config.py scripts/core/config.py
```

The file has no `sys.path.insert` and no cross-core imports, so no modifications needed to the copy.

- [ ] **Step 3: Replace scripts/config.py with shim**

Replace the entire contents of `scripts/config.py` with:

```python
"""Shim — real implementation in scripts/core/config.py"""
from .core.config import *  # noqa: F401,F403
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `python -m pytest tests/test_config.py tests/test_db.py tests/test_cli.py -v --tb=short`
Expected: All PASS (shim re-exports everything, all imports still work)

- [ ] **Step 5: Commit**

```bash
git add scripts/core/__init__.py scripts/core/config.py scripts/config.py
git commit -m "refactor: move config.py to scripts/core/ with shim

- Create scripts/core/ subpackage for shared library modules
- Move config.py to scripts/core/config.py (no changes to module)
- Replace scripts/config.py with one-liner shim re-export
- All existing imports continue to work unchanged"
```

---

### Task 2: Move cost_tracker.py and rate_limiter.py to core

**Files:**
- Create: `scripts/core/cost_tracker.py` (copy from `scripts/cost_tracker.py`)
- Create: `scripts/core/rate_limiter.py` (copy from `scripts/rate_limiter.py`)
- Modify: `scripts/cost_tracker.py` (replace with shim)
- Modify: `scripts/rate_limiter.py` (replace with shim)

These two modules have no cross-core imports and no `sys.path.insert` — straightforward copy + shim.

- [ ] **Step 1: Copy both files to core/**

```bash
cp scripts/cost_tracker.py scripts/core/cost_tracker.py
cp scripts/rate_limiter.py scripts/core/rate_limiter.py
```

No modifications needed to either copy.

- [ ] **Step 2: Replace scripts/cost_tracker.py with shim**

Replace the entire contents of `scripts/cost_tracker.py` with:

```python
"""Shim — real implementation in scripts/core/cost_tracker.py"""
from .core.cost_tracker import *  # noqa: F401,F403
```

- [ ] **Step 3: Replace scripts/rate_limiter.py with shim**

Replace the entire contents of `scripts/rate_limiter.py` with:

```python
"""Shim — real implementation in scripts/core/rate_limiter.py"""
from .core.rate_limiter import *  # noqa: F401,F403
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_rate_limiter.py tests/test_cost_tracker.py -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/cost_tracker.py scripts/core/rate_limiter.py scripts/cost_tracker.py scripts/rate_limiter.py
git commit -m "refactor: move cost_tracker.py and rate_limiter.py to scripts/core/

- Both modules have no cross-core imports — straightforward move
- Shim files replace originals for backward compatibility"
```

---

### Task 3: Move ai_client.py to core (with import fix)

**Files:**
- Create: `scripts/core/ai_client.py` (copy from `scripts/ai_client.py`, fix imports)
- Modify: `scripts/ai_client.py` (replace with shim)

This is the only module that needs import changes — it imports `from config import load_env` and `from cost_tracker import get_tracker`, and has a `sys.path.insert` line.

- [ ] **Step 1: Copy ai_client.py to core/**

```bash
cp scripts/ai_client.py scripts/core/ai_client.py
```

- [ ] **Step 2: Fix imports in scripts/core/ai_client.py**

In `scripts/core/ai_client.py`, make these changes:

Remove the `sys.path.insert` line (line 13):
```python
sys.path.insert(0, str(Path(__file__).parent))
```

Change the bare imports (lines 14-15):
```python
from config import load_env
from cost_tracker import get_tracker
```
To relative imports:
```python
from .config import load_env
from .cost_tracker import get_tracker
```

Also remove `import sys` and `from pathlib import Path` if they are no longer used after removing the `sys.path.insert` line. Check if `sys` or `Path` are used elsewhere in the file before removing.

- [ ] **Step 3: Replace scripts/ai_client.py with shim**

Replace the entire contents of `scripts/ai_client.py` with:

```python
"""Shim — real implementation in scripts/core/ai_client.py"""
from .core.ai_client import *  # noqa: F401,F403
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ai_client.py -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/ai_client.py scripts/ai_client.py
git commit -m "refactor: move ai_client.py to scripts/core/ with import fix

- Remove sys.path.insert hack
- Change bare imports to relative: from .config, from .cost_tracker
- Shim file replaces original for backward compatibility"
```

---

### Task 4: Move db.py and quality_check.py to core

**Files:**
- Create: `scripts/core/db.py` (copy from `scripts/db.py`)
- Create: `scripts/core/quality_check.py` (copy from `scripts/quality_check.py`)
- Modify: `scripts/db.py` (replace with shim)
- Modify: `scripts/quality_check.py` (replace with shim)

Both modules are standalone — no cross-core imports, no `sys.path.insert`.

- [ ] **Step 1: Copy both files to core/**

```bash
cp scripts/db.py scripts/core/db.py
cp scripts/quality_check.py scripts/core/quality_check.py
```

No modifications needed to either copy.

- [ ] **Step 2: Replace scripts/db.py with shim**

Replace the entire contents of `scripts/db.py` with:

```python
"""Shim — real implementation in scripts/core/db.py"""
from .core.db import *  # noqa: F401,F403
```

- [ ] **Step 3: Replace scripts/quality_check.py with shim**

Replace the entire contents of `scripts/quality_check.py` with:

```python
"""Shim — real implementation in scripts/core/quality_check.py"""
from .core.quality_check import *  # noqa: F401,F403
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_db.py tests/test_quality_check.py -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest --tb=short`
Expected: All 485+ tests PASS — this is the key validation that the full refactor works.

- [ ] **Step 6: Commit**

```bash
git add scripts/core/db.py scripts/core/quality_check.py scripts/db.py scripts/quality_check.py
git commit -m "refactor: move db.py and quality_check.py to scripts/core/

- Both modules are standalone — no import changes needed
- Shim files replace originals for backward compatibility
- Full test suite passes: all imports work via shims"
```

---

### Task 5: Add import smoke tests

**Files:**
- Create: `tests/test_core_imports.py`

- [ ] **Step 1: Write smoke tests**

Create `tests/test_core_imports.py`:

```python
"""
Smoke tests verifying scripts/core/ imports work correctly.

Tests that:
- Core modules are importable directly via scripts.core.*
- Shim re-exports work via scripts.*
- Both paths resolve to the same objects
"""


class TestCoreDirectImports:
    """Test that core modules are importable directly."""

    def test_import_config(self):
        from scripts.core.config import load_config, load_env, DEFAULT_CONFIG
        assert callable(load_config)
        assert callable(load_env)
        assert isinstance(DEFAULT_CONFIG, dict)

    def test_import_db(self):
        from scripts.core.db import get_db, close_db, init_schema, search
        assert callable(get_db)
        assert callable(close_db)
        assert callable(init_schema)
        assert callable(search)

    def test_import_ai_client(self):
        from scripts.core.ai_client import get_ai_client
        assert callable(get_ai_client)

    def test_import_cost_tracker(self):
        from scripts.core.cost_tracker import get_tracker
        assert callable(get_tracker)

    def test_import_rate_limiter(self):
        from scripts.core.rate_limiter import RateLimiter
        assert RateLimiter is not None

    def test_import_quality_check(self):
        from scripts.core.quality_check import assess_text_quality
        assert callable(assess_text_quality)


class TestShimEquivalence:
    """Test that shim imports resolve to the same objects as core imports."""

    def test_config_same_object(self):
        from scripts.config import load_config as shim_load
        from scripts.core.config import load_config as core_load
        assert shim_load is core_load

    def test_db_same_object(self):
        from scripts.db import get_db as shim_get
        from scripts.core.db import get_db as core_get
        assert shim_get is core_get

    def test_ai_client_same_object(self):
        from scripts.ai_client import get_ai_client as shim_get
        from scripts.core.ai_client import get_ai_client as core_get
        assert shim_get is core_get

    def test_cost_tracker_same_object(self):
        from scripts.cost_tracker import get_tracker as shim_get
        from scripts.core.cost_tracker import get_tracker as core_get
        assert shim_get is core_get

    def test_rate_limiter_same_object(self):
        from scripts.rate_limiter import RateLimiter as shim_cls
        from scripts.core.rate_limiter import RateLimiter as core_cls
        assert shim_cls is core_cls

    def test_quality_check_same_object(self):
        from scripts.quality_check import assess_text_quality as shim_fn
        from scripts.core.quality_check import assess_text_quality as core_fn
        assert shim_fn is core_fn
```

- [ ] **Step 2: Run smoke tests**

Run: `python -m pytest tests/test_core_imports.py -v`
Expected: All 12 PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_core_imports.py
git commit -m "test: add import smoke tests for scripts/core/ and shims

- Verify all 6 core modules importable via scripts.core.*
- Verify shim re-exports resolve to same objects as core imports
- 12 new tests confirming refactor integrity"
```
