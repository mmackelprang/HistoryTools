# Idempotent Ingestion and Duplicate Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect exact and near-duplicate files in the archive, present them for user review via proposal files, and manage quarantine lifecycle with TTL-based purging — while making ingestion idempotent through provenance tracking.

**Architecture:** Two new modules (`duplicate_detect.py` for detection/proposals, `duplicate_manage.py` for quarantine/restore/purge) backed by three new SQLite tables (`provenance`, `fingerprints`, `quarantine`). Detection integrates into the ingest pipeline and is available standalone via `family-archive duplicates`.

**Tech Stack:** Python 3.10+, SQLite/FTS5 (existing), PyMuPDF (existing), Pillow (existing), imagehash (new dependency)

**Design spec:** `docs/2026-04-11-duplicate-detection-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/db.py` | Schema v2: add `provenance`, `fingerprints`, `quarantine` tables |
| `scripts/duplicate_detect.py` | Detection strategies (MD5, text similarity, perceptual hash), quality scoring, proposal generation |
| `scripts/duplicate_manage.py` | Quarantine, restore, purge, TTL enforcement, status |
| `scripts/cli.py` | Wire up `duplicates` subcommand, replace old `handle_duplicates` dispatch |
| `scripts/ingest.py` | Replace merge-mode duplicate logic with provenance-based detection, write provenance on execute |
| `scripts/split_apply.py` | Write provenance records when creating split children |
| `pyproject.toml` | Add `imagehash` dependency |
| `tests/test_duplicate_detect.py` | Detection tests |
| `tests/test_duplicate_manage.py` | Lifecycle tests |
| `tests/test_db.py` | Schema v2 migration tests |

---

### Task 1: Schema v2 — Add provenance, fingerprints, quarantine tables

**Files:**
- Modify: `scripts/db.py:17` (SCHEMA_VERSION), `scripts/db.py:169-223` (init_schema)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for new tables**

Add to `tests/test_db.py`:

```python
class TestSchemaV2:
    """Test schema v2 additions."""

    def test_provenance_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provenance'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_fingerprints_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fingerprints'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_quarantine_table_exists(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='quarantine'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)

    def test_schema_version_is_2(self, tmp_path):
        conn = get_db(tmp_path)
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        close_db(conn)
        assert version == 2

    def test_provenance_insert(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Letters" / "letter.pdf", "content")
        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)
        conn.execute("""
            INSERT INTO provenance (file_id, source_path, source_hash, operation, detail)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, "/src/letter.pdf", "abc123", "ingest", None))
        conn.commit()
        cursor = conn.execute("SELECT * FROM provenance WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        assert row["operation"] == "ingest"
        assert row["source_path"] == "/src/letter.pdf"
        close_db(conn)

    def test_provenance_parent_child(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        parent = make_file(dest / "Letters" / "compilation.pdf", "big pdf")
        child = make_file(dest / "Letters" / "letter1.pdf", "page 1")
        conn = get_db(dest)
        parent_id = index_file(conn, dest, parent)
        child_id = index_file(conn, dest, child)
        conn.execute("""
            INSERT INTO provenance (file_id, parent_file_id, operation, detail)
            VALUES (?, ?, ?, ?)
        """, (child_id, parent_id, "split", '{"pages": "1-3"}'))
        conn.commit()
        cursor = conn.execute("SELECT * FROM provenance WHERE file_id = ?", (child_id,))
        row = cursor.fetchone()
        assert row["parent_file_id"] == parent_id
        assert row["operation"] == "split"
        close_db(conn)

    def test_fingerprints_insert(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Photos" / "photo.jpg", "\x00")
        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)
        conn.execute("""
            INSERT INTO fingerprints (file_id, hash_type, hash_value, page_number)
            VALUES (?, ?, ?, ?)
        """, (file_id, "phash", "abcdef1234567890", 1))
        conn.commit()
        cursor = conn.execute("SELECT * FROM fingerprints WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        assert row["hash_type"] == "phash"
        assert row["hash_value"] == "abcdef1234567890"
        close_db(conn)

    def test_fingerprints_unique_constraint(self, tmp_path):
        import sqlite3
        dest = tmp_path / "archive"
        dest.mkdir()
        fpath = make_file(dest / "Photos" / "photo.jpg", "\x00")
        conn = get_db(dest)
        file_id = index_file(conn, dest, fpath)
        conn.execute("""
            INSERT INTO fingerprints (file_id, hash_type, hash_value, page_number)
            VALUES (?, ?, ?, ?)
        """, (file_id, "phash", "aaaa", 1))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO fingerprints (file_id, hash_type, hash_value, page_number)
                VALUES (?, ?, ?, ?)
            """, (file_id, "phash", "bbbb", 1))
        close_db(conn)

    def test_quarantine_insert(self, tmp_path):
        conn = get_db(tmp_path)
        conn.execute("""
            INSERT INTO quarantine (original_path, quarantine_path, duplicate_of,
                                    reason, purge_after, file_hash, file_size)
            VALUES (?, ?, ?, ?, datetime('now', '+14 days'), ?, ?)
        """, ("Letters/letter.pdf", "_duplicates/Letters/letter.pdf",
              "Letters/letter-orig.pdf", "exact_match", "abc123", 1000))
        conn.commit()
        cursor = conn.execute("SELECT * FROM quarantine")
        row = cursor.fetchone()
        assert row["reason"] == "exact_match"
        assert row["original_path"] == "Letters/letter.pdf"
        close_db(conn)

    def test_v1_db_upgrades_to_v2(self, tmp_path):
        """A database created with schema v1 should upgrade to v2."""
        import sqlite3
        db_path = tmp_path / ".archive.db"
        # Create a minimal v1 database
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                folder TEXT NOT NULL,
                subfolder TEXT,
                file_type TEXT,
                size_bytes INTEGER,
                date_prefix TEXT,
                md5_hash TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            PRAGMA user_version = 1;
        """)
        conn.commit()
        conn.close()
        # Open with get_db — should upgrade to v2
        conn = get_db(tmp_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 2
        # New tables should exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provenance'"
        )
        assert cursor.fetchone() is not None
        close_db(conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py::TestSchemaV2 -v`
Expected: FAIL — tables don't exist, version is 1

- [ ] **Step 3: Implement schema v2**

In `scripts/db.py`, change `SCHEMA_VERSION`:

```python
SCHEMA_VERSION = 2
```

In `scripts/db.py`, update `init_schema()` — add the new tables after the existing `CREATE TABLE IF NOT EXISTS` block and before the FTS5 table creation. Add these after line 207 (after the closing `""")` of the existing `executescript`):

```python
    # Schema v2: provenance, fingerprints, quarantine
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS provenance (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id),
            parent_file_id INTEGER REFERENCES files(id),
            source_path TEXT,
            source_hash TEXT,
            operation TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fingerprints (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id),
            hash_type TEXT NOT NULL,
            hash_value TEXT NOT NULL,
            page_number INTEGER DEFAULT 1,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_id, hash_type, page_number)
        );

        CREATE TABLE IF NOT EXISTS quarantine (
            id INTEGER PRIMARY KEY,
            original_path TEXT NOT NULL,
            quarantine_path TEXT NOT NULL,
            duplicate_of TEXT,
            reason TEXT,
            quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            purge_after TIMESTAMP NOT NULL,
            file_hash TEXT,
            file_size INTEGER
        );
    """)
```

Also update the existing `test_schema_version_set` test in `TestSchema` — change `assert version == 1` to `assert version == 2`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All tests PASS (including existing tests — schema v2 is backward compatible)

- [ ] **Step 5: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add schema v2 with provenance, fingerprints, quarantine tables

New tables for duplicate detection and idempotent ingestion:
- provenance: tracks file lineage (ingest, split, rename) with parent-child relationships
- fingerprints: stores perceptual hashes for near-duplicate detection
- quarantine: tracks quarantined files with TTL for purging
- Backward compatible: existing v1 databases upgrade automatically"
```

---

### Task 2: Add `imagehash` dependency

**Files:**
- Modify: `pyproject.toml:23-27`

- [ ] **Step 1: Add imagehash to dependencies**

In `pyproject.toml`, add `imagehash` to the `dependencies` list:

```toml
dependencies = [
    "PyMuPDF>=1.23.0",
    "Pillow>=10.0.0",
    "python-dotenv>=1.0.0",
    "imagehash>=4.3.0",
]
```

- [ ] **Step 2: Install and verify**

Run: `pip install -e ".[all]"`
Run: `python -c "import imagehash; print(imagehash.__version__)"`
Expected: Version prints without error

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add imagehash dependency for perceptual duplicate detection"
```

---

### Task 3: Detection module — exact MD5 matching

**Files:**
- Create: `scripts/duplicate_detect.py`
- Create: `tests/test_duplicate_detect.py`

- [ ] **Step 1: Write failing tests for exact duplicate detection**

Create `tests/test_duplicate_detect.py`:

```python
"""
Tests for the duplicate detection module (scripts/duplicate_detect.py).
"""

from pathlib import Path

import pytest

from scripts.db import get_db, close_db, index_file, index_transcript
from scripts.duplicate_detect import find_exact_duplicates


# ── Helpers ────────────────────────────────────────────────────────────────

def make_file(path: Path, content: str = "test content") -> Path:
    """Create a file with given content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ── Exact duplicate tests ────────────────────────────────────────────────


class TestExactDuplicates:
    """Test MD5-based exact duplicate detection."""

    def test_no_duplicates(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.pdf", "content a")
        make_file(dest / "Letters" / "b.pdf", "content b")
        conn = get_db(dest)
        index_file(conn, dest, dest / "Letters" / "a.pdf")
        index_file(conn, dest, dest / "Letters" / "b.pdf")
        groups = find_exact_duplicates(conn)
        close_db(conn)
        assert groups == []

    def test_finds_exact_duplicates(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.pdf", "same content")
        make_file(dest / "Photos" / "a-copy.pdf", "same content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "Letters" / "a.pdf")
        index_file(conn, dest, dest / "Photos" / "a-copy.pdf")
        groups = find_exact_duplicates(conn)
        close_db(conn)
        assert len(groups) == 1
        assert len(groups[0]["files"]) == 2

    def test_group_has_correct_fields(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "dup")
        make_file(dest / "b.pdf", "dup")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        groups = find_exact_duplicates(conn)
        close_db(conn)
        g = groups[0]
        assert g["match_type"] == "exact"
        assert g["similarity"] == 1.0
        assert all("path" in f for f in g["files"])
        assert all("size_bytes" in f for f in g["files"])
        assert all("file_id" in f for f in g["files"])

    def test_excludes_provenance_siblings(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        # Parent and two children with same content (simulating a split)
        make_file(dest / "Letters" / "compilation.pdf", "same content")
        make_file(dest / "Letters" / "letter1.pdf", "same content")
        make_file(dest / "Letters" / "letter2.pdf", "same content")
        conn = get_db(dest)
        parent_id = index_file(conn, dest, dest / "Letters" / "compilation.pdf")
        child1_id = index_file(conn, dest, dest / "Letters" / "letter1.pdf")
        child2_id = index_file(conn, dest, dest / "Letters" / "letter2.pdf")
        # Record provenance: both children split from parent
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation) VALUES (?, ?, ?)",
            (child1_id, parent_id, "split")
        )
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation) VALUES (?, ?, ?)",
            (child2_id, parent_id, "split")
        )
        conn.commit()
        groups = find_exact_duplicates(conn)
        close_db(conn)
        # No groups — all three files are provenance-related
        assert groups == []

    def test_multiple_duplicate_groups(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a1.pdf", "content A")
        make_file(dest / "a2.pdf", "content A")
        make_file(dest / "b1.pdf", "content B")
        make_file(dest / "b2.pdf", "content B")
        make_file(dest / "unique.pdf", "unique")
        conn = get_db(dest)
        for f in dest.glob("*.pdf"):
            index_file(conn, dest, f)
        groups = find_exact_duplicates(conn)
        close_db(conn)
        assert len(groups) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_duplicate_detect.py::TestExactDuplicates -v`
Expected: FAIL — `duplicate_detect` module doesn't exist

- [ ] **Step 3: Implement find_exact_duplicates**

Create `scripts/duplicate_detect.py`:

```python
"""
Duplicate detection for the Family Archive.

Provides three detection strategies (exact MD5, text similarity, perceptual hash),
quality scoring, and proposal file generation. This module is stateless — it reads
from the database and filesystem, runs comparisons, and returns duplicate groups.
"""

import json
from pathlib import Path
from datetime import datetime


def _get_provenance_relations(conn):
    """Build a set of (file_id, file_id) pairs that are provenance-related.

    Two files are related if:
    - One is the parent of the other (parent_file_id relationship)
    - Both share the same parent_file_id (siblings from the same split)
    """
    related = set()

    rows = conn.execute(
        "SELECT file_id, parent_file_id FROM provenance WHERE parent_file_id IS NOT NULL"
    ).fetchall()

    # Parent-child pairs
    parent_children = {}
    for row in rows:
        child = row["file_id"]
        parent = row["parent_file_id"]
        related.add((min(child, parent), max(child, parent)))
        parent_children.setdefault(parent, []).append(child)

    # Sibling pairs (children of the same parent)
    for children in parent_children.values():
        for i in range(len(children)):
            for j in range(i + 1, len(children)):
                a, b = children[i], children[j]
                related.add((min(a, b), max(a, b)))

    return related


def find_exact_duplicates(conn):
    """Find files with identical MD5 hashes.

    Returns list of duplicate groups. Each group is a dict:
        {
            "match_type": "exact",
            "similarity": 1.0,
            "files": [{"file_id": int, "path": str, "size_bytes": int, ...}, ...]
        }

    Excludes provenance-related files (parent-child, split siblings).
    """
    # Find all hashes that appear more than once
    cursor = conn.execute("""
        SELECT md5_hash, COUNT(*) as cnt
        FROM files
        WHERE md5_hash IS NOT NULL
        GROUP BY md5_hash
        HAVING cnt > 1
    """)
    duplicate_hashes = [row["md5_hash"] for row in cursor.fetchall()]

    if not duplicate_hashes:
        return []

    provenance_related = _get_provenance_relations(conn)

    groups = []
    for md5 in duplicate_hashes:
        cursor = conn.execute(
            "SELECT id, path, filename, folder, file_type, size_bytes, date_prefix, indexed_at "
            "FROM files WHERE md5_hash = ?",
            (md5,)
        )
        files = []
        for row in cursor.fetchall():
            files.append({
                "file_id": row["id"],
                "path": row["path"],
                "filename": row["filename"],
                "folder": row["folder"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"] or 0,
                "date_prefix": row["date_prefix"],
                "indexed_at": row["indexed_at"],
            })

        # Filter out provenance-related pairs
        # Keep only files that aren't provenance-related to ALL other files in the group
        filtered = []
        file_ids = [f["file_id"] for f in files]
        for f in files:
            is_related_to_all_others = True
            for other_id in file_ids:
                if other_id == f["file_id"]:
                    continue
                pair = (min(f["file_id"], other_id), max(f["file_id"], other_id))
                if pair not in provenance_related:
                    is_related_to_all_others = False
                    break
            if not is_related_to_all_others:
                filtered.append(f)

        # Need at least 2 unrelated files to form a duplicate group
        if len(filtered) >= 2:
            groups.append({
                "match_type": "exact",
                "similarity": 1.0,
                "files": filtered,
            })

    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_detect.py::TestExactDuplicates -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/duplicate_detect.py tests/test_duplicate_detect.py
git commit -m "feat: add exact MD5 duplicate detection with provenance exclusion

- find_exact_duplicates() groups files by identical MD5 hash
- Excludes provenance-related files (parent-child, split siblings)
- Returns structured groups with file metadata for proposal generation"
```

---

### Task 4: Detection module — text similarity

**Files:**
- Modify: `scripts/duplicate_detect.py`
- Modify: `tests/test_duplicate_detect.py`

- [ ] **Step 1: Write failing tests for text similarity**

Add to `tests/test_duplicate_detect.py`:

```python
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


class TestTextSimilarity:
    """Test transcript text similarity detection."""

    def test_identical_text_detected(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.transcript.md", TRANSCRIPT_A)
        make_file(dest / "Letters" / "b.transcript.md", TRANSCRIPT_B_SIMILAR)
        conn = get_db(dest)
        index_file(conn, dest, dest / "Letters" / "a.transcript.md")
        index_file(conn, dest, dest / "Letters" / "b.transcript.md")
        index_transcript(conn, dest, dest / "Letters" / "a.transcript.md")
        index_transcript(conn, dest, dest / "Letters" / "b.transcript.md")
        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)
        assert len(groups) == 1
        assert groups[0]["match_type"] == "text_similar"
        assert groups[0]["similarity"] >= 0.90

    def test_different_text_not_detected(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.transcript.md", TRANSCRIPT_A)
        make_file(dest / "Letters" / "c.transcript.md", TRANSCRIPT_C_DIFFERENT)
        conn = get_db(dest)
        index_file(conn, dest, dest / "Letters" / "a.transcript.md")
        index_file(conn, dest, dest / "Letters" / "c.transcript.md")
        index_transcript(conn, dest, dest / "Letters" / "a.transcript.md")
        index_transcript(conn, dest, dest / "Letters" / "c.transcript.md")
        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)
        assert groups == []

    def test_excludes_provenance_siblings(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.transcript.md", TRANSCRIPT_A)
        make_file(dest / "b.transcript.md", TRANSCRIPT_B_SIMILAR)
        conn = get_db(dest)
        id_a = index_file(conn, dest, dest / "a.transcript.md")
        id_b = index_file(conn, dest, dest / "b.transcript.md")
        index_transcript(conn, dest, dest / "a.transcript.md")
        index_transcript(conn, dest, dest / "b.transcript.md")
        # Mark as siblings
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation) VALUES (?, ?, ?)",
            (id_a, 999, "split")
        )
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation) VALUES (?, ?, ?)",
            (id_b, 999, "split")
        )
        conn.commit()
        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)
        assert groups == []

    def test_custom_threshold(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.transcript.md", TRANSCRIPT_A)
        make_file(dest / "Letters" / "c.transcript.md", TRANSCRIPT_C_DIFFERENT)
        conn = get_db(dest)
        index_file(conn, dest, dest / "Letters" / "a.transcript.md")
        index_file(conn, dest, dest / "Letters" / "c.transcript.md")
        index_transcript(conn, dest, dest / "Letters" / "a.transcript.md")
        index_transcript(conn, dest, dest / "Letters" / "c.transcript.md")
        # With very low threshold, different texts might still match
        groups = find_text_similar(conn, threshold=0.01)
        close_db(conn)
        # At 0.01 threshold, anything with word overlap matches
        assert len(groups) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_duplicate_detect.py::TestTextSimilarity -v`
Expected: FAIL — `find_text_similar` not defined

- [ ] **Step 3: Implement find_text_similar**

Add to `scripts/duplicate_detect.py`:

```python
def _jaccard_similarity(text_a, text_b):
    """Compute token-level Jaccard similarity between two texts.

    Returns float between 0.0 (no overlap) and 1.0 (identical token sets).
    """
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def find_text_similar(conn, threshold=0.90, already_grouped_ids=None):
    """Find transcripts with similar text content using Jaccard similarity.

    Args:
        conn: SQLite connection.
        threshold: Minimum Jaccard similarity to flag as duplicate (default 0.90).
        already_grouped_ids: Set of file_ids already in exact-match groups (skip these).

    Returns list of duplicate groups with match_type "text_similar".
    """
    if already_grouped_ids is None:
        already_grouped_ids = set()

    # Load all transcript bodies
    cursor = conn.execute("""
        SELECT tc.file_id, tc.path, tc.body, f.filename, f.folder, f.file_type,
               f.size_bytes, f.date_prefix, f.indexed_at
        FROM transcripts_content tc
        JOIN files f ON f.id = tc.file_id
        WHERE tc.body IS NOT NULL AND length(tc.body) > 0
    """)
    transcripts = []
    for row in cursor.fetchall():
        if row["file_id"] not in already_grouped_ids:
            transcripts.append({
                "file_id": row["file_id"],
                "path": row["path"],
                "body": row["body"],
                "filename": row["filename"],
                "folder": row["folder"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"] or 0,
                "date_prefix": row["date_prefix"],
                "indexed_at": row["indexed_at"],
            })

    if len(transcripts) < 2:
        return []

    provenance_related = _get_provenance_relations(conn)

    # Compare all pairs (O(n^2) — fine for typical archive sizes of <5000 transcripts)
    # Use union-find to build groups from pairwise matches
    parent = {t["file_id"]: t["file_id"] for t in transcripts}
    similarity_scores = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(transcripts)):
        for j in range(i + 1, len(transcripts)):
            a, b = transcripts[i], transcripts[j]
            pair = (min(a["file_id"], b["file_id"]), max(a["file_id"], b["file_id"]))
            if pair in provenance_related:
                continue
            sim = _jaccard_similarity(a["body"], b["body"])
            if sim >= threshold:
                union(a["file_id"], b["file_id"])
                similarity_scores[pair] = sim

    # Collect groups
    group_map = {}
    transcript_by_id = {t["file_id"]: t for t in transcripts}
    for t in transcripts:
        root = find(t["file_id"])
        if root != t["file_id"] or any(find(o["file_id"]) == root for o in transcripts if o["file_id"] != t["file_id"]):
            group_map.setdefault(root, []).append(t["file_id"])

    groups = []
    for root, file_ids in group_map.items():
        if len(file_ids) < 2:
            continue
        # Compute group similarity as the minimum pairwise similarity
        min_sim = 1.0
        for i in range(len(file_ids)):
            for j in range(i + 1, len(file_ids)):
                pair = (min(file_ids[i], file_ids[j]), max(file_ids[i], file_ids[j]))
                if pair in similarity_scores:
                    min_sim = min(min_sim, similarity_scores[pair])
        files = []
        for fid in file_ids:
            t = transcript_by_id[fid]
            files.append({
                "file_id": t["file_id"],
                "path": t["path"],
                "filename": t["filename"],
                "folder": t["folder"],
                "file_type": t["file_type"],
                "size_bytes": t["size_bytes"],
                "date_prefix": t["date_prefix"],
                "indexed_at": t["indexed_at"],
            })
        groups.append({
            "match_type": "text_similar",
            "similarity": round(min_sim, 3),
            "files": files,
        })

    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_detect.py::TestTextSimilarity -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/duplicate_detect.py tests/test_duplicate_detect.py
git commit -m "feat: add text similarity duplicate detection via Jaccard

- find_text_similar() compares transcript bodies using token-level Jaccard
- Configurable threshold (default 0.90)
- Union-find grouping for transitive matches
- Excludes provenance-related files"
```

---

### Task 5: Detection module — perceptual hashing

**Files:**
- Modify: `scripts/duplicate_detect.py`
- Modify: `tests/test_duplicate_detect.py`

- [ ] **Step 1: Write failing tests for perceptual hash detection**

Add to `tests/test_duplicate_detect.py`:

```python
from scripts.duplicate_detect import (
    find_exact_duplicates,
    find_text_similar,
    compute_phash,
    find_perceptual_duplicates,
)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def make_test_image(path, color=(255, 0, 0), size=(100, 100)):
    """Create a simple test image."""
    img = Image.new("RGB", size, color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))
    return path


class TestPerceptualHash:
    """Test perceptual hashing for near-duplicate images."""

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_compute_phash_returns_string(self, tmp_path):
        img_path = make_test_image(tmp_path / "photo.jpg")
        result = compute_phash(img_path)
        assert isinstance(result, str)
        assert len(result) == 16  # 64-bit hash as hex

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_identical_images_same_hash(self, tmp_path):
        img_a = make_test_image(tmp_path / "a.jpg", color=(100, 150, 200))
        img_b = make_test_image(tmp_path / "b.jpg", color=(100, 150, 200))
        assert compute_phash(img_a) == compute_phash(img_b)

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_different_images_different_hash(self, tmp_path):
        img_a = make_test_image(tmp_path / "a.jpg", color=(255, 0, 0))
        img_b = make_test_image(tmp_path / "b.jpg", color=(0, 0, 255))
        assert compute_phash(img_a) != compute_phash(img_b)

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_finds_perceptual_duplicates(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_test_image(dest / "Photos" / "a.jpg", color=(100, 150, 200))
        make_test_image(dest / "Photos" / "b.jpg", color=(100, 150, 200))
        conn = get_db(dest)
        index_file(conn, dest, dest / "Photos" / "a.jpg")
        index_file(conn, dest, dest / "Photos" / "b.jpg")
        groups = find_perceptual_duplicates(conn, dest)
        close_db(conn)
        assert len(groups) == 1
        assert groups[0]["match_type"] == "perceptual"

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_different_images_not_grouped(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_test_image(dest / "Photos" / "a.jpg", color=(255, 0, 0))
        make_test_image(dest / "Photos" / "b.jpg", color=(0, 0, 255))
        conn = get_db(dest)
        index_file(conn, dest, dest / "Photos" / "a.jpg")
        index_file(conn, dest, dest / "Photos" / "b.jpg")
        groups = find_perceptual_duplicates(conn, dest)
        close_db(conn)
        assert groups == []

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_stores_fingerprint_in_db(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_test_image(dest / "Photos" / "a.jpg", color=(100, 150, 200))
        conn = get_db(dest)
        file_id = index_file(conn, dest, dest / "Photos" / "a.jpg")
        find_perceptual_duplicates(conn, dest)
        cursor = conn.execute(
            "SELECT * FROM fingerprints WHERE file_id = ? AND hash_type = 'phash'",
            (file_id,)
        )
        row = cursor.fetchone()
        close_db(conn)
        assert row is not None
        assert row["hash_value"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_duplicate_detect.py::TestPerceptualHash -v`
Expected: FAIL — `compute_phash` and `find_perceptual_duplicates` not defined

- [ ] **Step 3: Implement perceptual hashing**

Add to `scripts/duplicate_detect.py`:

```python
import imagehash
from PIL import Image


# Photo extensions that can be perceptually hashed directly
_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".heic", ".webp"}


def compute_phash(file_path):
    """Compute perceptual hash (pHash) for an image file.

    Args:
        file_path: Path to the image file.

    Returns:
        Hex string of the 64-bit perceptual hash, or None on error.
    """
    try:
        img = Image.open(str(file_path))
        h = imagehash.phash(img)
        return str(h)
    except Exception:
        return None


def _hamming_distance(hash_a, hash_b):
    """Compute Hamming distance between two hex hash strings."""
    if not hash_a or not hash_b or len(hash_a) != len(hash_b):
        return 64  # max distance
    int_a = int(hash_a, 16)
    int_b = int(hash_b, 16)
    return bin(int_a ^ int_b).count("1")


def find_perceptual_duplicates(conn, dest_root, max_distance=8, already_grouped_ids=None):
    """Find visually similar images using perceptual hashing.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory (to resolve file paths).
        max_distance: Maximum Hamming distance to consider a match (default 8).
        already_grouped_ids: Set of file_ids already grouped (skip these).

    Returns list of duplicate groups with match_type "perceptual".
    """
    dest_root = Path(dest_root)
    if already_grouped_ids is None:
        already_grouped_ids = set()

    # Find all photo files not already grouped
    cursor = conn.execute("""
        SELECT id, path, filename, folder, file_type, size_bytes, date_prefix, indexed_at
        FROM files
        WHERE file_type = 'photo'
    """)
    photos = []
    for row in cursor.fetchall():
        if row["id"] not in already_grouped_ids:
            photos.append(dict(row))

    if len(photos) < 2:
        return []

    provenance_related = _get_provenance_relations(conn)

    # Compute or retrieve perceptual hashes
    hashes = {}
    for photo in photos:
        file_id = photo["id"]
        # Check if already computed
        cursor = conn.execute(
            "SELECT hash_value FROM fingerprints WHERE file_id = ? AND hash_type = 'phash' AND page_number = 1",
            (file_id,)
        )
        row = cursor.fetchone()
        if row:
            hashes[file_id] = row["hash_value"]
        else:
            # Compute and store
            file_path = dest_root / photo["path"]
            h = compute_phash(file_path)
            if h:
                hashes[file_id] = h
                conn.execute(
                    "INSERT OR REPLACE INTO fingerprints (file_id, hash_type, hash_value, page_number) "
                    "VALUES (?, 'phash', ?, 1)",
                    (file_id, h)
                )
    conn.commit()

    # Compare all pairs
    photo_by_id = {p["id"]: p for p in photos}
    parent = {p["id"]: p["id"] for p in photos if p["id"] in hashes}
    pair_distances = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    photo_ids = [p["id"] for p in photos if p["id"] in hashes]
    for i in range(len(photo_ids)):
        for j in range(i + 1, len(photo_ids)):
            a, b = photo_ids[i], photo_ids[j]
            pair = (min(a, b), max(a, b))
            if pair in provenance_related:
                continue
            dist = _hamming_distance(hashes[a], hashes[b])
            if dist <= max_distance:
                union(a, b)
                pair_distances[pair] = dist

    # Collect groups
    group_map = {}
    for pid in photo_ids:
        root = find(pid)
        group_map.setdefault(root, []).append(pid)

    groups = []
    for root, file_ids in group_map.items():
        if len(file_ids) < 2:
            continue
        # Compute similarity as 1 - (max_distance_in_group / 64)
        max_dist = 0
        for i in range(len(file_ids)):
            for j in range(i + 1, len(file_ids)):
                pair = (min(file_ids[i], file_ids[j]), max(file_ids[i], file_ids[j]))
                if pair in pair_distances:
                    max_dist = max(max_dist, pair_distances[pair])
        similarity = round(1.0 - (max_dist / 64.0), 3)

        files = []
        for fid in file_ids:
            p = photo_by_id[fid]
            files.append({
                "file_id": p["id"],
                "path": p["path"],
                "filename": p["filename"],
                "folder": p["folder"],
                "file_type": p["file_type"],
                "size_bytes": p["size_bytes"] or 0,
                "date_prefix": p["date_prefix"],
                "indexed_at": p["indexed_at"],
            })
        groups.append({
            "match_type": "perceptual",
            "similarity": similarity,
            "files": files,
        })

    return groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_detect.py::TestPerceptualHash -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/duplicate_detect.py tests/test_duplicate_detect.py
git commit -m "feat: add perceptual hash duplicate detection for photos

- compute_phash() uses imagehash library for 64-bit perceptual hashing
- find_perceptual_duplicates() compares photos by Hamming distance
- Stores fingerprints in DB for reuse across scans
- Configurable max_distance threshold (default 8 bits)"
```

---

### Task 6: Quality scoring and proposal generation

**Files:**
- Modify: `scripts/duplicate_detect.py`
- Modify: `tests/test_duplicate_detect.py`

- [ ] **Step 1: Write failing tests for quality scoring and proposals**

Add to `tests/test_duplicate_detect.py`:

```python
from scripts.duplicate_detect import (
    find_exact_duplicates,
    find_text_similar,
    compute_phash,
    find_perceptual_duplicates,
    score_quality,
    generate_proposals,
    scan_duplicates,
)


class TestQualityScoring:
    """Test quality scoring for duplicate groups."""

    def test_higher_confidence_scores_higher(self):
        files = [
            {"file_id": 1, "path": "a.pdf", "size_bytes": 100, "word_count": 50, "confidence": "high", "indexed_at": "2026-04-01"},
            {"file_id": 2, "path": "b.pdf", "size_bytes": 100, "word_count": 50, "confidence": "low", "indexed_at": "2026-04-02"},
        ]
        scored = score_quality(files)
        assert scored[0]["path"] == "a.pdf"  # high confidence wins

    def test_higher_word_count_scores_higher(self):
        files = [
            {"file_id": 1, "path": "a.pdf", "size_bytes": 100, "word_count": 10, "confidence": "high", "indexed_at": "2026-04-01"},
            {"file_id": 2, "path": "b.pdf", "size_bytes": 100, "word_count": 100, "confidence": "high", "indexed_at": "2026-04-01"},
        ]
        scored = score_quality(files)
        assert scored[0]["path"] == "b.pdf"  # more words wins

    def test_earlier_ingested_breaks_tie(self):
        files = [
            {"file_id": 1, "path": "a.pdf", "size_bytes": 100, "word_count": 50, "confidence": "high", "indexed_at": "2026-04-02"},
            {"file_id": 2, "path": "b.pdf", "size_bytes": 100, "word_count": 50, "confidence": "high", "indexed_at": "2026-04-01"},
        ]
        scored = score_quality(files)
        assert scored[0]["path"] == "b.pdf"  # earlier date wins tie


class TestProposalGeneration:
    """Test proposal file generation."""

    def test_generate_proposals_creates_files(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "same")
        make_file(dest / "b.pdf", "same")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        groups = find_exact_duplicates(conn)
        close_db(conn)
        generate_proposals(groups, dest)
        assert (dest / "_duplicate-proposals.json").exists()
        assert (dest / "_duplicate-proposals.md").exists()

    def test_proposals_json_structure(self, tmp_path):
        import json
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "same")
        make_file(dest / "b.pdf", "same")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        groups = find_exact_duplicates(conn)
        close_db(conn)
        generate_proposals(groups, dest)
        with open(dest / "_duplicate-proposals.json") as f:
            data = json.load(f)
        assert "generated" in data
        assert "groups" in data
        assert len(data["groups"]) == 1
        g = data["groups"][0]
        assert "id" in g
        assert "keep" in g
        assert "approved" in g
        assert "files" in g


class TestScanDuplicates:
    """Test the top-level scan_duplicates function."""

    def test_scan_runs_all_strategies(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "same content")
        make_file(dest / "b.pdf", "same content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        groups = scan_duplicates(conn, dest)
        close_db(conn)
        assert len(groups) >= 1

    def test_scan_no_duplicates(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "unique a")
        make_file(dest / "b.pdf", "unique b")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        groups = scan_duplicates(conn, dest)
        close_db(conn)
        assert groups == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_duplicate_detect.py::TestQualityScoring tests/test_duplicate_detect.py::TestProposalGeneration tests/test_duplicate_detect.py::TestScanDuplicates -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement quality scoring, proposal generation, and scan_duplicates**

Add to `scripts/duplicate_detect.py`:

```python
_CONFIDENCE_SCORES = {"high": 3, "medium": 2, "low": 1}


def score_quality(files):
    """Score and sort files by quality. Highest quality first.

    Quality formula:
    - Transcript confidence: high=3, medium=2, low=1, none=0
    - Word count: normalized (file's / max in group), weight 2
    - File size: normalized (file's / max in group), weight 1
    - Ties broken by earliest indexed_at

    Args:
        files: List of file dicts with size_bytes, word_count, confidence, indexed_at.

    Returns:
        Same list sorted by quality score descending.
    """
    max_words = max((f.get("word_count") or 0) for f in files) or 1
    max_size = max((f.get("size_bytes") or 0) for f in files) or 1

    def quality_key(f):
        conf_score = _CONFIDENCE_SCORES.get(f.get("confidence", ""), 0)
        word_score = ((f.get("word_count") or 0) / max_words) * 2
        size_score = ((f.get("size_bytes") or 0) / max_size) * 1
        total = conf_score + word_score + size_score
        # Negate indexed_at for tie-breaking (earlier = better)
        return (total, -(f.get("indexed_at") or "9999"))

    return sorted(files, key=quality_key, reverse=True)


def _enrich_files_with_transcript_data(conn, files):
    """Add word_count and confidence from transcripts table to file dicts."""
    for f in files:
        cursor = conn.execute(
            "SELECT word_count, confidence FROM transcripts WHERE file_id = ?",
            (f["file_id"],)
        )
        row = cursor.fetchone()
        if row:
            f["word_count"] = row["word_count"] or 0
            f["confidence"] = row["confidence"]
        else:
            f.setdefault("word_count", 0)
            f.setdefault("confidence", None)
    return files


def generate_proposals(groups, dest_root):
    """Write _duplicate-proposals.json and _duplicate-proposals.md.

    Args:
        groups: List of duplicate groups from detection functions.
        dest_root: Archive root directory.
    """
    dest_root = Path(dest_root)
    now = datetime.now().isoformat(timespec="seconds")

    proposals = {
        "generated": now,
        "groups": [],
    }

    for i, group in enumerate(groups, 1):
        files = group["files"]
        keep = files[0]["path"]  # first file is highest quality (pre-sorted)

        proposal_group = {
            "id": f"dup-{i:03d}",
            "match_type": group["match_type"],
            "similarity": group["similarity"],
            "files": [],
            "keep": keep,
            "approved": True,
        }

        for f in files:
            proposal_group["files"].append({
                "path": f["path"],
                "size_bytes": f.get("size_bytes", 0),
                "word_count": f.get("word_count", 0),
                "confidence": f.get("confidence"),
                "ingested_at": f.get("indexed_at"),
                "recommended": f["path"] == keep,
            })

        proposals["groups"].append(proposal_group)

    # Write JSON
    json_path = dest_root / "_duplicate-proposals.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(proposals, f, indent=2, ensure_ascii=False)

    # Write Markdown
    md_lines = [
        "# Duplicate Proposals\n",
        f"Generated: {now[:10]}",
    ]

    type_counts = {}
    for g in proposals["groups"]:
        type_counts[g["match_type"]] = type_counts.get(g["match_type"], 0) + 1
    counts_str = ", ".join(f"{v} {k}" for k, v in sorted(type_counts.items()))
    md_lines.append(f"Groups: {len(proposals['groups'])} ({counts_str})\n")

    for g in proposals["groups"]:
        match_label = g["match_type"].replace("_", " ").title()
        sim_pct = int(g["similarity"] * 100)
        md_lines.append(f"## Group {g['id']} — {match_label} ({sim_pct}%)")
        md_lines.append(f"**Keep:** {g['keep']}")
        md_lines.append("| File | Size | Words | Confidence | Ingested |")
        md_lines.append("|------|------|-------|------------|----------|")
        for f in g["files"]:
            name = Path(f["path"]).name
            if f["recommended"]:
                name = f"**{name}**"
            size_kb = f["size_bytes"] // 1024
            md_lines.append(
                f"| {name} | {size_kb} KB | {f.get('word_count', 0)} | "
                f"{f.get('confidence') or 'n/a'} | {(f.get('ingested_at') or 'unknown')[:10]} |"
            )
        md_lines.append("")

    md_path = dest_root / "_duplicate-proposals.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")


def scan_duplicates(conn, dest_root, threshold=0.90, folder=None, scan_type=None):
    """Run all detection strategies and return combined groups.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
        threshold: Text similarity threshold (default 0.90).
        folder: Optional folder filter.
        scan_type: Optional filter: "exact" or "similar" (None = all).

    Returns:
        List of all duplicate groups, sorted by match_type then similarity.
    """
    all_groups = []
    grouped_ids = set()

    # Strategy 1: Exact MD5
    if scan_type in (None, "exact"):
        exact_groups = find_exact_duplicates(conn)
        for g in exact_groups:
            _enrich_files_with_transcript_data(conn, g["files"])
            g["files"] = score_quality(g["files"])
        all_groups.extend(exact_groups)
        for g in exact_groups:
            for f in g["files"]:
                grouped_ids.add(f["file_id"])

    # Strategy 2: Text similarity
    if scan_type in (None, "similar"):
        text_groups = find_text_similar(conn, threshold=threshold, already_grouped_ids=grouped_ids)
        for g in text_groups:
            _enrich_files_with_transcript_data(conn, g["files"])
            g["files"] = score_quality(g["files"])
        all_groups.extend(text_groups)
        for g in text_groups:
            for f in g["files"]:
                grouped_ids.add(f["file_id"])

    # Strategy 3: Perceptual hashing
    if scan_type in (None, "similar"):
        perceptual_groups = find_perceptual_duplicates(
            conn, dest_root, already_grouped_ids=grouped_ids
        )
        for g in perceptual_groups:
            _enrich_files_with_transcript_data(conn, g["files"])
            g["files"] = score_quality(g["files"])
        all_groups.extend(perceptual_groups)

    # Filter by folder if requested
    if folder:
        all_groups = [
            g for g in all_groups
            if any(f.get("folder") == folder for f in g["files"])
        ]

    return all_groups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_detect.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/duplicate_detect.py tests/test_duplicate_detect.py
git commit -m "feat: add quality scoring, proposal generation, and scan orchestration

- score_quality() ranks files by confidence, word count, file size, age
- generate_proposals() writes _duplicate-proposals.json and .md
- scan_duplicates() orchestrates all three detection strategies
- Supports folder and type filtering"
```

---

### Task 7: Lifecycle module — quarantine, restore, purge, status

**Files:**
- Create: `scripts/duplicate_manage.py`
- Create: `tests/test_duplicate_manage.py`

- [ ] **Step 1: Write failing tests for quarantine lifecycle**

Create `tests/test_duplicate_manage.py`:

```python
"""
Tests for the duplicate lifecycle module (scripts/duplicate_manage.py).
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


def make_file(path: Path, content: str = "test content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_proposals(dest, groups):
    """Write a _duplicate-proposals.json file."""
    data = {"generated": "2026-04-11T00:00:00", "groups": groups}
    proposals_path = dest / "_duplicate-proposals.json"
    with open(proposals_path, "w") as f:
        json.dump(data, f)
    return proposals_path


class TestQuarantine:
    """Test quarantine (apply) operations."""

    def test_apply_moves_file(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        keep = make_file(dest / "Letters" / "a.pdf", "content")
        dupe = make_file(dest / "Letters" / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, keep)
        index_file(conn, dest, dupe)
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "Letters/a.pdf", "approved": True,
            "files": [
                {"path": "Letters/a.pdf", "recommended": True},
                {"path": "Letters/b.pdf", "recommended": False},
            ],
        }])
        result = apply_quarantine(conn, dest)
        close_db(conn)
        assert result["quarantined"] == 1
        assert not dupe.exists()
        assert (dest / "_duplicates" / "Letters" / "b.pdf").exists()

    def test_apply_skips_unapproved(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": False,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        result = apply_quarantine(conn, dest)
        close_db(conn)
        assert result["quarantined"] == 0
        assert (dest / "b.pdf").exists()

    def test_apply_moves_transcript_with_source(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "Letters" / "a.pdf", "content")
        make_file(dest / "Letters" / "b.pdf", "content")
        make_file(dest / "Letters" / "b.transcript.md", "transcript of b")
        conn = get_db(dest)
        index_file(conn, dest, dest / "Letters" / "a.pdf")
        index_file(conn, dest, dest / "Letters" / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "Letters/a.pdf", "approved": True,
            "files": [
                {"path": "Letters/a.pdf", "recommended": True},
                {"path": "Letters/b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        close_db(conn)
        assert (dest / "_duplicates" / "Letters" / "b.transcript.md").exists()

    def test_apply_records_in_quarantine_table(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        cursor = conn.execute("SELECT * FROM quarantine")
        row = cursor.fetchone()
        close_db(conn)
        assert row is not None
        assert row["original_path"] == "b.pdf"
        assert row["duplicate_of"] == "a.pdf"
        assert row["reason"] == "exact"


class TestRestore:
    """Test restoring quarantined files."""

    def test_restore_moves_file_back(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        dupe = make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        assert not dupe.exists()
        restore_file(conn, dest, "_duplicates/b.pdf")
        close_db(conn)
        assert dupe.exists()

    def test_restore_removes_quarantine_record(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        restore_file(conn, dest, "_duplicates/b.pdf")
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM quarantine")
        close_db(conn)
        assert cursor.fetchone()["cnt"] == 0


class TestPurge:
    """Test purging expired quarantine entries."""

    def test_purge_deletes_expired(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        # Backdate purge_after to the past
        conn.execute("UPDATE quarantine SET purge_after = datetime('now', '-1 day')")
        conn.commit()
        result = purge_expired(conn, dest)
        close_db(conn)
        assert result["purged"] == 1
        assert not (dest / "_duplicates" / "b.pdf").exists()

    def test_purge_skips_unexpired(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        result = purge_expired(conn, dest)
        close_db(conn)
        assert result["purged"] == 0
        assert (dest / "_duplicates" / "b.pdf").exists()

    def test_purge_all_ignores_ttl(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        result = purge_expired(conn, dest, purge_all=True)
        close_db(conn)
        assert result["purged"] == 1


class TestStatus:
    """Test quarantine status reporting."""

    def test_status_empty(self, tmp_path):
        conn = get_db(tmp_path)
        status = get_quarantine_status(conn)
        close_db(conn)
        assert status["total_files"] == 0
        assert status["total_size_bytes"] == 0
        assert status["expired"] == 0

    def test_status_with_entries(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        make_file(dest / "a.pdf", "content")
        make_file(dest / "b.pdf", "content")
        conn = get_db(dest)
        index_file(conn, dest, dest / "a.pdf")
        index_file(conn, dest, dest / "b.pdf")
        make_proposals(dest, [{
            "id": "dup-001", "match_type": "exact", "similarity": 1.0,
            "keep": "a.pdf", "approved": True,
            "files": [
                {"path": "a.pdf", "recommended": True},
                {"path": "b.pdf", "recommended": False},
            ],
        }])
        apply_quarantine(conn, dest)
        status = get_quarantine_status(conn)
        close_db(conn)
        assert status["total_files"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_duplicate_manage.py -v`
Expected: FAIL — `duplicate_manage` module doesn't exist

- [ ] **Step 3: Implement duplicate_manage.py**

Create `scripts/duplicate_manage.py`:

```python
"""
Duplicate lifecycle management for the Family Archive.

Handles quarantine, restore, purge, and status for duplicate files.
Quarantined files are moved to _duplicates/ with a 14-day TTL.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

DEFAULT_TTL_DAYS = 14


def apply_quarantine(conn, dest_root, dry_run=False):
    """Read _duplicate-proposals.json and quarantine non-keep files from approved groups.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
        dry_run: If True, don't move files.

    Returns:
        Dict with counts: {"quarantined": int, "skipped": int, "errors": int}
    """
    dest_root = Path(dest_root)
    proposals_path = dest_root / "_duplicate-proposals.json"

    if not proposals_path.exists():
        print("No proposals found. Run 'family-archive duplicates --scan' first.")
        return {"quarantined": 0, "skipped": 0, "errors": 0}

    with open(proposals_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    quarantine_dir = dest_root / "_duplicates"
    quarantined = 0
    skipped = 0
    errors = 0

    for group in data.get("groups", []):
        if not group.get("approved", False):
            skipped += len(group["files"]) - 1
            continue

        keep_path = group["keep"]
        match_type = group.get("match_type", "unknown")

        for file_info in group["files"]:
            file_path = file_info["path"]
            if file_path == keep_path:
                continue

            source = dest_root / file_path
            if not source.exists():
                skipped += 1
                continue

            # Quarantine destination preserves folder structure
            q_path = quarantine_dir / file_path

            if dry_run:
                print(f"  Would quarantine: {file_path}")
                quarantined += 1
                continue

            try:
                q_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(q_path))

                # Move associated transcript if it exists
                transcript = source.parent / (source.stem + ".transcript.md")
                if transcript.exists():
                    q_transcript = q_path.parent / transcript.name
                    shutil.move(str(transcript), str(q_transcript))

                # Record in quarantine table
                file_hash = None
                file_size = None
                cursor = conn.execute(
                    "SELECT md5_hash, size_bytes FROM files WHERE path = ?", (file_path,)
                )
                row = cursor.fetchone()
                if row:
                    file_hash = row["md5_hash"]
                    file_size = row["size_bytes"]

                conn.execute("""
                    INSERT INTO quarantine
                        (original_path, quarantine_path, duplicate_of, reason,
                         purge_after, file_hash, file_size)
                    VALUES (?, ?, ?, ?, datetime('now', '+{} days'), ?, ?)
                """.format(DEFAULT_TTL_DAYS),
                    (file_path, str(Path("_duplicates") / file_path), keep_path,
                     match_type, file_hash, file_size)
                )
                conn.commit()

                quarantined += 1
                print(f"  Quarantined: {file_path}")

            except Exception as e:
                errors += 1
                print(f"  Error quarantining {file_path}: {e}")

    action = "Would quarantine" if dry_run else "Quarantined"
    print(f"\n{action}: {quarantined}, skipped: {skipped}, errors: {errors}")
    return {"quarantined": quarantined, "skipped": skipped, "errors": errors}


def restore_file(conn, dest_root, quarantine_path):
    """Restore a quarantined file to its original location.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
        quarantine_path: Relative path within _duplicates/ (e.g., "_duplicates/Letters/b.pdf").
    """
    dest_root = Path(dest_root)

    # Find the quarantine record
    cursor = conn.execute(
        "SELECT * FROM quarantine WHERE quarantine_path = ?", (quarantine_path,)
    )
    row = cursor.fetchone()
    if not row:
        print(f"No quarantine record found for: {quarantine_path}")
        return

    original_path = row["original_path"]
    source = dest_root / quarantine_path
    target = dest_root / original_path

    if not source.exists():
        print(f"Quarantined file not found: {source}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))

    # Restore transcript if it exists
    source_transcript = source.parent / (source.stem + ".transcript.md")
    if source_transcript.exists():
        target_transcript = target.parent / source_transcript.name
        shutil.move(str(source_transcript), str(target_transcript))

    # Remove quarantine record
    conn.execute("DELETE FROM quarantine WHERE id = ?", (row["id"],))
    conn.commit()

    print(f"Restored: {original_path}")


def purge_expired(conn, dest_root, purge_all=False):
    """Permanently delete quarantined files past their TTL.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
        purge_all: If True, purge all quarantined files regardless of TTL.

    Returns:
        Dict with count: {"purged": int}
    """
    dest_root = Path(dest_root)

    if purge_all:
        cursor = conn.execute("SELECT * FROM quarantine")
    else:
        cursor = conn.execute(
            "SELECT * FROM quarantine WHERE purge_after <= datetime('now')"
        )

    rows = cursor.fetchall()
    purged = 0

    for row in rows:
        q_file = dest_root / row["quarantine_path"]
        try:
            if q_file.exists():
                q_file.unlink()
            # Also delete transcript
            q_transcript = q_file.parent / (q_file.stem + ".transcript.md")
            if q_transcript.exists():
                q_transcript.unlink()

            # Clean up DB records
            conn.execute("DELETE FROM quarantine WHERE id = ?", (row["id"],))

            # Clean up files/transcripts/fingerprints/provenance for this file
            file_cursor = conn.execute(
                "SELECT id FROM files WHERE path = ?", (row["original_path"],)
            )
            file_row = file_cursor.fetchone()
            if file_row:
                file_id = file_row["id"]
                conn.execute("DELETE FROM transcripts WHERE file_id = ?", (file_id,))
                conn.execute("DELETE FROM transcripts_content WHERE file_id = ?", (file_id,))
                conn.execute("DELETE FROM fingerprints WHERE file_id = ?", (file_id,))
                conn.execute("DELETE FROM provenance WHERE file_id = ?", (file_id,))
                conn.execute("DELETE FROM files WHERE id = ?", (file_id,))

            conn.commit()
            purged += 1
        except Exception as e:
            print(f"  Error purging {row['quarantine_path']}: {e}")

    # Clean up empty directories in _duplicates/
    quarantine_dir = dest_root / "_duplicates"
    if quarantine_dir.exists():
        for dirpath in sorted(quarantine_dir.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                dirpath.rmdir()

    print(f"Purged: {purged} files")
    return {"purged": purged}


def get_quarantine_status(conn):
    """Return quarantine summary statistics.

    Returns:
        Dict with: total_files, total_size_bytes, expired, by_reason.
    """
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM quarantine")
    total = cursor.fetchone()["cnt"]

    cursor = conn.execute("SELECT COALESCE(SUM(file_size), 0) as total FROM quarantine")
    total_size = cursor.fetchone()["total"]

    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM quarantine WHERE purge_after <= datetime('now')"
    )
    expired = cursor.fetchone()["cnt"]

    cursor = conn.execute(
        "SELECT reason, COUNT(*) as cnt FROM quarantine GROUP BY reason"
    )
    by_reason = {row["reason"]: row["cnt"] for row in cursor.fetchall()}

    return {
        "total_files": total,
        "total_size_bytes": total_size,
        "expired": expired,
        "by_reason": by_reason,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_manage.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/duplicate_manage.py tests/test_duplicate_manage.py
git commit -m "feat: add duplicate lifecycle management (quarantine, restore, purge)

- apply_quarantine() moves non-keep files to _duplicates/ with 14-day TTL
- restore_file() moves quarantined files back to original location
- purge_expired() permanently deletes files past TTL (or --all to force)
- get_quarantine_status() returns summary statistics
- Moves associated .transcript.md files with their source files
- Records all quarantine actions in SQLite quarantine table"
```

---

### Task 8: Wire up CLI commands

**Files:**
- Modify: `scripts/cli.py:107-111` (replace cmd_duplicates), `scripts/cli.py:338` (update help)

- [ ] **Step 1: Write failing test for new CLI dispatch**

Add to `tests/test_cli.py`:

```python
class TestDuplicatesCLI:
    """Test the duplicates subcommand dispatches correctly."""

    def test_duplicates_scan_dry_run(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.cli", "duplicates", "--scan", "--dry-run"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        # Should not crash — may fail due to no config, but shouldn't be "Coming soon"
        assert "Coming soon" not in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py::TestDuplicatesCLI -v`
Expected: FAIL — current duplicates command dispatches to old `handle_duplicates.py`

- [ ] **Step 3: Implement new cmd_duplicates**

Replace `cmd_duplicates` in `scripts/cli.py` (lines 107-111):

```python
def cmd_duplicates(args):
    """Detect, quarantine, restore, and purge duplicate files."""
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="Duplicate management")
    parser.add_argument("--config", default=None)
    parser.add_argument("--scan", action="store_true", help="Detect duplicates, write proposals")
    parser.add_argument("--apply", action="store_true", help="Quarantine approved duplicates")
    parser.add_argument("--status", action="store_true", help="Show quarantine summary")
    parser.add_argument("--restore", type=str, default=None, help="Restore a quarantined file")
    parser.add_argument("--purge", action="store_true", help="Delete files past TTL")
    parser.add_argument("--all", action="store_true", help="With --purge: ignore TTL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--folder", default=None, help="Limit scan to folder")
    parser.add_argument("--type", default=None, choices=["exact", "similar"], help="Detection type filter")
    parser.add_argument("--threshold", type=float, default=0.90, help="Text similarity threshold")
    parsed = parser.parse_args(args)

    from .config import load_config
    from .db import get_db, close_db

    config = load_config(parsed.config)
    dest_root = config["dest_root"]
    conn = get_db(dest_root, config)

    try:
        if parsed.scan:
            from .duplicate_detect import scan_duplicates, generate_proposals
            print("Scanning for duplicates...")
            groups = scan_duplicates(
                conn, dest_root,
                threshold=parsed.threshold,
                folder=parsed.folder,
                scan_type=parsed.type,
            )
            if groups:
                generate_proposals(groups, dest_root)
                print(f"\nFound {len(groups)} duplicate groups. Review:")
                print(f"  {dest_root / '_duplicate-proposals.md'}")
                print(f"\nThen run: family-archive duplicates --apply")
            else:
                print("No duplicates found.")

        elif parsed.apply:
            from .duplicate_manage import apply_quarantine
            apply_quarantine(conn, dest_root, dry_run=parsed.dry_run)

        elif parsed.status:
            from .duplicate_manage import get_quarantine_status
            status = get_quarantine_status(conn)
            print(f"\nQuarantine status:")
            print(f"  Files:   {status['total_files']}")
            size_mb = status['total_size_bytes'] / (1024 * 1024)
            print(f"  Size:    {size_mb:.1f} MB")
            print(f"  Expired: {status['expired']} (ready to purge)")
            if status.get('by_reason'):
                print(f"  By type:")
                for reason, count in status['by_reason'].items():
                    print(f"    {reason}: {count}")

        elif parsed.restore:
            from .duplicate_manage import restore_file
            restore_file(conn, dest_root, parsed.restore)

        elif parsed.purge:
            from .duplicate_manage import purge_expired
            purge_expired(conn, dest_root, purge_all=parsed.all)

        else:
            parser.print_help()

    finally:
        close_db(conn)
```

Update the help text for duplicates in the subparsers (line 338):

```python
    subparsers.add_parser('duplicates', help='Detect and manage duplicate files (--scan, --apply, --status, --purge)')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli.py tests/test_cli.py
git commit -m "feat: wire up duplicates CLI with scan, apply, status, restore, purge

- family-archive duplicates --scan: detect duplicates, write proposals
- family-archive duplicates --apply: quarantine approved duplicates
- family-archive duplicates --status: show quarantine summary
- family-archive duplicates --restore <path>: restore quarantined file
- family-archive duplicates --purge [--all]: delete expired quarantined files
- Replaces old handle_duplicates.py dispatch"
```

---

### Task 9: Ingest integration — provenance tracking and duplicate prevention

**Files:**
- Modify: `scripts/ingest.py:418-496` (replace merge-mode duplicate logic)
- Modify: `scripts/ingest.py:699-703` (replace handle_duplicates stage)

- [ ] **Step 1: Write failing test for ingest provenance**

Add to `tests/test_duplicate_detect.py`:

```python
class TestIngestProvenance:
    """Test that ingest provenance prevents re-ingestion."""

    def test_source_hash_in_provenance_detected(self, tmp_path):
        from scripts.duplicate_detect import check_ingest_duplicates
        dest = tmp_path / "archive"
        dest.mkdir()
        existing = make_file(dest / "Letters" / "letter.pdf", "original content")
        conn = get_db(dest)
        file_id = index_file(conn, dest, existing)
        # Record provenance for this file
        conn.execute(
            "INSERT INTO provenance (file_id, source_path, source_hash, operation) VALUES (?, ?, ?, ?)",
            (file_id, "/source/letter.pdf", "d41d8cd98f00b204e9800998ecf8427e", "ingest")
        )
        conn.commit()
        # Check if a file with the same hash would be detected
        result = check_ingest_duplicates(conn, "d41d8cd98f00b204e9800998ecf8427e")
        close_db(conn)
        assert result is not None
        assert result["path"] == "Letters/letter.pdf"

    def test_unknown_hash_not_detected(self, tmp_path):
        from scripts.duplicate_detect import check_ingest_duplicates
        dest = tmp_path / "archive"
        dest.mkdir()
        conn = get_db(dest)
        result = check_ingest_duplicates(conn, "0000000000000000")
        close_db(conn)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_duplicate_detect.py::TestIngestProvenance -v`
Expected: FAIL — `check_ingest_duplicates` not defined

- [ ] **Step 3: Implement check_ingest_duplicates**

Add to `scripts/duplicate_detect.py`:

```python
def check_ingest_duplicates(conn, source_hash):
    """Check if a file with this hash has already been ingested.

    Checks both the provenance table (by source_hash) and the files table (by md5_hash).

    Args:
        conn: SQLite connection.
        source_hash: MD5 hash of the source file.

    Returns:
        Dict with "path" of the existing file, or None if no match.
    """
    # Check provenance first (most authoritative)
    cursor = conn.execute("""
        SELECT f.path FROM provenance p
        JOIN files f ON f.id = p.file_id
        WHERE p.source_hash = ?
        LIMIT 1
    """, (source_hash,))
    row = cursor.fetchone()
    if row:
        return {"path": row["path"]}

    # Fall back to checking files table by md5
    cursor = conn.execute(
        "SELECT path FROM files WHERE md5_hash = ? LIMIT 1",
        (source_hash,)
    )
    row = cursor.fetchone()
    if row:
        return {"path": row["path"]}

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_detect.py::TestIngestProvenance -v`
Expected: All PASS

- [ ] **Step 5: Update ingest.py to use provenance-based detection**

In `scripts/ingest.py`, replace the merge-mode duplicate logic (lines 418-496). Replace the `existing_hashes` dict approach with provenance-based detection:

Replace lines 418-428 (the `existing_hashes` block):

```python
    # In merge mode, check for duplicates via SQLite provenance and file hashes
    use_db_detection = False
    db_conn = None
    if mode == "merge" and dest_root.exists():
        try:
            from db import get_db
            db_conn = get_db(dest_root)
            use_db_detection = True
            print("Using database for duplicate detection in merge mode")
        except Exception:
            print("Warning: could not open archive DB for duplicate detection")
```

Replace lines 467-478 (the duplicate check block):

```python
            # Check for duplicates in merge mode
            is_duplicate = False
            duplicate_of = None
            if use_db_detection:
                try:
                    from duplicate_detect import check_ingest_duplicates
                    file_hash_val = md5_hash(filepath)
                    match = check_ingest_duplicates(db_conn, file_hash_val)
                    if match:
                        is_duplicate = True
                        duplicate_of = match["path"]
                        dupes += 1
                except Exception:
                    pass
```

In `execute_plan()` (around line 635 where files are copied), add provenance recording after each successful file copy. After the `shutil.copy2` call, add:

```python
                # Record provenance
                try:
                    from db import get_db
                    from duplicate_detect import check_ingest_duplicates
                    db_conn = get_db(dest_root)
                    # Get or create file entry
                    from db import index_file
                    file_id = index_file(db_conn, dest_root, dest_path)
                    if file_id:
                        source_hash = md5_hash(source_path)
                        db_conn.execute("""
                            INSERT OR IGNORE INTO provenance
                                (file_id, source_path, source_hash, operation)
                            VALUES (?, ?, ?, 'ingest')
                        """, (file_id, str(entry["source_path"]), source_hash))
                        db_conn.commit()
                    db_conn.close()
                except Exception:
                    pass  # Provenance is best-effort during ingest
```

Replace Stage 5 in `execute_plan()` (lines 699-703) to use the new duplicate system:

```python
    # Stage 5: Detect Duplicates
    print(f"\n{'=' * 60}")
    print("Stage 5: Detect Duplicates")
    print(f"{'=' * 60}")
    run_script("cli.py", ["duplicates", "--scan"] + config_args)
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/ingest.py scripts/duplicate_detect.py tests/test_duplicate_detect.py
git commit -m "feat: integrate provenance-based duplicate detection into ingest pipeline

- Replace merge-mode hash inventory with SQLite provenance checks
- check_ingest_duplicates() checks provenance and files tables
- Record provenance on each file copy during ingest --execute
- Replace handle_duplicates.py call with new duplicates --scan in Stage 5"
```

---

### Task 10: Split provenance integration

**Files:**
- Modify: `scripts/split_apply.py:310-315` (after successful split)

- [ ] **Step 1: Write failing test for split provenance**

Add to `tests/test_duplicate_detect.py`:

```python
class TestSplitProvenance:
    """Test that split_apply records provenance."""

    def test_split_creates_provenance_record(self, tmp_path):
        import fitz
        dest = tmp_path / "archive"
        dest.mkdir()
        # Create a 3-page PDF
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            text_point = fitz.Point(72, 72)
            page.insert_text(text_point, f"Page {i+1} content")
        pdf_path = dest / "Letters" / "compilation.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(pdf_path))
        doc.close()
        # Create transcript
        transcript = make_file(
            dest / "Letters" / "compilation.transcript.md",
            "---\nsource_file: compilation.pdf\n---\n\n## Page 1\n\nPage 1 content\n\n## Page 2\n\nPage 2 content\n\n## Page 3\n\nPage 3 content\n"
        )
        # Index the parent in DB
        conn = get_db(dest)
        parent_id = index_file(conn, dest, pdf_path)
        close_db(conn)

        from scripts.split_apply import apply_single_split
        segment = {
            "pages": [1, 2],
            "proposed_name": "1984-03-15_letter.pdf",
            "proposed_folder": "Letters",
            "description": "Letter from Alice",
        }
        result = apply_single_split(pdf_path, transcript, segment, dest)
        assert result["status"] == "ok"

        # Check provenance was recorded
        conn = get_db(dest)
        cursor = conn.execute(
            "SELECT * FROM provenance WHERE operation = 'split'"
        )
        row = cursor.fetchone()
        close_db(conn)
        assert row is not None
        assert row["parent_file_id"] == parent_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_duplicate_detect.py::TestSplitProvenance -v`
Expected: FAIL — split_apply doesn't write provenance

- [ ] **Step 3: Add provenance recording to split_apply**

In `scripts/split_apply.py`, add provenance recording after a successful split. In `apply_single_split()`, after the PDF extraction succeeds and before returning the result (around line 215, after the `except Exception` block for PDF extraction), add:

```python
    # Record provenance for the split child
    try:
        from db import get_db, index_file as db_index_file
        db_conn = get_db(dest_root)
        parent_id = db_index_file(db_conn, dest_root, source_pdf)
        child_id = db_index_file(db_conn, dest_root, output_pdf)
        if parent_id and child_id:
            import json as _json
            detail = _json.dumps({"pages": pages})
            db_conn.execute("""
                INSERT OR IGNORE INTO provenance
                    (file_id, parent_file_id, operation, detail)
                VALUES (?, ?, 'split', ?)
            """, (child_id, parent_id, detail))
            db_conn.commit()
        db_conn.close()
    except Exception:
        pass  # Provenance is best-effort
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_duplicate_detect.py::TestSplitProvenance -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/split_apply.py tests/test_duplicate_detect.py
git commit -m "feat: record provenance when splitting compilation PDFs

- split_apply writes provenance records with parent_file_id and page ranges
- Enables duplicate detection to exclude split siblings from false positives
- Best-effort: split still works if DB is unavailable"
```

---

### Task 11: Remove old handle_duplicates.py and update docs

**Files:**
- Remove: `scripts/handle_duplicates.py`
- Modify: `docs/WORKFLOW.md`

- [ ] **Step 1: Remove handle_duplicates.py**

```bash
git rm scripts/handle_duplicates.py
```

- [ ] **Step 2: Update WORKFLOW.md**

In `docs/WORKFLOW.md`, replace the existing duplicates section (step 9, "Catalog Photos and Detect Duplicates") with:

```markdown
### 9. Detect and Manage Duplicates

```bash
# Scan for duplicates (exact MD5, text similarity, perceptual hash)
family-archive duplicates --scan
family-archive duplicates --scan --dry-run           # preview only
family-archive duplicates --scan --type exact         # only exact matches
family-archive duplicates --scan --folder Letters     # limit to folder

# Review _duplicate-proposals.md, edit _duplicate-proposals.json if needed

# Quarantine approved duplicates (moves to _duplicates/)
family-archive duplicates --apply
family-archive duplicates --apply --dry-run

# Check quarantine status
family-archive duplicates --status

# Restore a quarantined file
family-archive duplicates --restore _duplicates/Letters/letter.pdf

# Purge quarantined files past 14-day TTL
family-archive duplicates --purge
family-archive duplicates --purge --all              # purge regardless of TTL
```

Duplicates are quarantined to `_duplicates/` for 14 days before permanent deletion.
Files related by provenance (e.g., split from the same compilation PDF) are excluded
from duplicate detection.
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove handle_duplicates.py, update workflow docs

- Remove scripts/handle_duplicates.py (superseded by duplicate_detect + duplicate_manage)
- Update docs/WORKFLOW.md with new duplicates CLI commands
- Update step numbering in workflow"
```

---

### Task 12: Final integration test and full test run

**Files:**
- Modify: `tests/test_duplicate_detect.py` (add integration test)

- [ ] **Step 1: Write end-to-end integration test**

Add to `tests/test_duplicate_detect.py`:

```python
class TestEndToEnd:
    """End-to-end integration test for the full duplicate workflow."""

    def test_full_workflow(self, tmp_path):
        """Scan -> proposals -> apply -> status -> purge."""
        import json
        from scripts.duplicate_detect import scan_duplicates, generate_proposals
        from scripts.duplicate_manage import apply_quarantine, get_quarantine_status, purge_expired

        dest = tmp_path / "archive"
        dest.mkdir()

        # Create files: two exact duplicates, one unique
        make_file(dest / "Letters" / "letter-v1.pdf", "Dear Alice, same letter content here")
        make_file(dest / "Letters" / "letter-v2.pdf", "Dear Alice, same letter content here")
        make_file(dest / "Photos" / "sunset.jpg", "unique photo data")

        # Index
        conn = get_db(dest)
        for f in (dest / "Letters").glob("*.pdf"):
            index_file(conn, dest, f)
        index_file(conn, dest, dest / "Photos" / "sunset.jpg")

        # Scan
        groups = scan_duplicates(conn, dest)
        assert len(groups) == 1
        assert groups[0]["match_type"] == "exact"

        # Generate proposals
        generate_proposals(groups, dest)
        assert (dest / "_duplicate-proposals.json").exists()

        # Apply quarantine
        result = apply_quarantine(conn, dest)
        assert result["quarantined"] == 1

        # Check status
        status = get_quarantine_status(conn)
        assert status["total_files"] == 1

        # Force purge
        conn.execute("UPDATE quarantine SET purge_after = datetime('now', '-1 day')")
        conn.commit()
        purge_result = purge_expired(conn, dest)
        assert purge_result["purged"] == 1

        # Status should be empty
        status = get_quarantine_status(conn)
        assert status["total_files"] == 0

        close_db(conn)
```

- [ ] **Step 2: Run the integration test**

Run: `python -m pytest tests/test_duplicate_detect.py::TestEndToEnd -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_duplicate_detect.py
git commit -m "test: add end-to-end integration test for duplicate workflow

- Tests full lifecycle: scan -> proposals -> quarantine -> status -> purge
- Verifies all components work together correctly"
```
