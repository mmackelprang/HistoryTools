# Idempotent Ingestion and Duplicate Detection — Design Spec

## Goal

A unified system for preventing duplicate files from entering the archive, detecting duplicates that already exist, and managing their lifecycle through quarantine with a user review workflow. The system guarantees idempotent ingestion (re-running ingest on the same source is a no-op) and provides provenance tracking so any file can be traced back to its origin.

## Architecture

Two new modules with clear separation of concerns:

- **`scripts/duplicate_detect.py`** — Detection only. Computes fingerprints (MD5, perceptual hash, text similarity), finds duplicate groups, scores quality, generates proposals. Stateless: reads from DB/filesystem, writes proposals.
- **`scripts/duplicate_manage.py`** — Lifecycle only. Quarantine, restore, purge, TTL enforcement. Manages the `_duplicates/` folder and tracks quarantine metadata in SQLite.

Three new SQLite tables (`provenance`, `fingerprints`, `quarantine`) extend the existing database schema.

Detection integrates into the ingest pipeline (catch duplicates before they enter the archive) and is available as a standalone scan (catch duplicates that accumulated over time).

## Design Principles

- **Proposal/review/apply pattern** — Matches the existing rename and split workflows. Generate proposals, let the user review and edit, then apply.
- **SQLite as state backend** — Proposals are backed by SQLite state. JSON/markdown files are the human-readable review layer generated from and edited back into that state. Long-term direction: migrate all proposal systems (splits, renames, ingest) to SQLite backing.
- **Provenance over flat files** — Track file lineage (ingest, split, rename) in SQLite so any file can be traced back to its origin. This replaces scattered state in JSON proposal files.
- **Quarantine with TTL** — Duplicates are moved to `_duplicates/`, not deleted. Default 14-day TTL before auto-purge eligibility. Explicit `--purge` command to delete; no background auto-deletion.

## Schema Extensions

Three new tables added to the existing SQLite database. Schema version bumps from 1 to 2.

### `provenance` — File lineage tracking

Tracks the origin and transformation history of every file. Replaces the need for a separate ingest log and connects split children to their parent documents.

```sql
CREATE TABLE provenance (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id),
    parent_file_id INTEGER REFERENCES files(id),  -- NULL for top-level ingested files
    source_path TEXT,                -- original source (pre-ingest) path
    source_hash TEXT,                -- MD5 of the original source file
    operation TEXT NOT NULL,         -- "ingest", "split", "rename", "format"
    detail TEXT,                     -- JSON: {"pages": "5-8"} for splits, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key relationships:**
- `file_id` points to the file in the `files` table
- `parent_file_id` points to the parent file (e.g., the compilation PDF that was split)
- `operation` records what created this file ("ingest", "split", "rename", "format")
- `detail` stores operation-specific metadata as JSON (e.g., page ranges for splits)

**Provenance-aware duplicate detection:** Files related by provenance (parent-child, split siblings sharing a `parent_file_id`) are excluded from duplicate detection to prevent false positives.

### `fingerprints` — Perceptual hashes

Stores perceptual hashes for near-duplicate detection, separate from `files` to allow multiple hash types per file and per-page hashing for PDFs.

```sql
CREATE TABLE fingerprints (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id),
    hash_type TEXT NOT NULL,          -- "md5", "phash", "dhash"
    hash_value TEXT NOT NULL,
    page_number INTEGER DEFAULT 1,    -- for multi-page PDFs
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_id, hash_type, page_number)
);
```

### `quarantine` — Quarantined file tracking

Tracks files that have been moved to `_duplicates/` and their TTL for purging.

```sql
CREATE TABLE quarantine (
    id INTEGER PRIMARY KEY,
    original_path TEXT NOT NULL,       -- where it was in the archive
    quarantine_path TEXT NOT NULL,     -- path in _duplicates/
    duplicate_of TEXT,                 -- path of the "keep" file
    reason TEXT,                       -- "exact_match", "text_similar", "perceptual"
    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    purge_after TIMESTAMP NOT NULL,   -- quarantined_at + 14 days (default TTL)
    file_hash TEXT,
    file_size INTEGER
);
```

## Detection Module (`scripts/duplicate_detect.py`)

Three detection strategies, run in order from cheapest to most expensive. Each strategy skips files related by provenance (parent-child, split siblings).

### Strategy 1: Exact match (MD5)

- Compare `md5_hash` from the existing `files` table
- Files with identical hashes are exact duplicates — group immediately
- Cost: zero (hashes already computed during indexing)

### Strategy 2: Text similarity (transcripts)

- For files with transcripts, compare transcript bodies
- Token-level Jaccard similarity: (set intersection of words) / (set union of words)
- Threshold: >= 0.90 similarity flags a potential duplicate (configurable)
- Cost: low (reads from existing `transcripts_content` table, pure Python)

### Strategy 3: Perceptual hashing (images and PDF confirmation)

- **Photos** (jpg, png, tiff, etc.): compute pHash directly from the image file using `imagehash` + `Pillow`
- **PDFs** flagged by text similarity but needing confirmation: render first page via PyMuPDF (`fitz`, already a project dependency), compute pHash
- Store hashes in `fingerprints` table for reuse
- Hamming distance threshold: <= 8 bits difference flags a match (tunable)
- Cost: moderate (reads image data, computes hashes). Only runs on files not already grouped by strategies 1 or 2
- New dependency: `imagehash` (pure Python, depends on `Pillow` which is already installed)

### Detection output

Each detected group contains:
- List of file paths in the group
- Match type: `exact`, `text_similar`, `perceptual`
- Similarity score
- Per-file quality metrics: file size, page count (PDFs), word count, transcript confidence
- Recommended "keep" file based on quality score

**Quality score formula:** Sum of weighted signals, highest score wins:
- Transcript confidence: high=3, medium=2, low=1, none=0
- Word count: normalized (file's word count / max word count in group), weight 2
- File size: normalized (file's size / max size in group), weight 1
- Ties broken by earliest `ingested_at` (stability — prefer the file already in the archive longer)

The user can override the recommendation by editing the proposals before applying.

## Proposal Generation and Review

### `_duplicate-proposals.json`

Machine-readable, user-editable:

```json
{
  "generated": "2026-04-11T14:30:00",
  "groups": [
    {
      "id": "dup-001",
      "match_type": "exact",
      "similarity": 1.0,
      "files": [
        {
          "path": "Letters/1984/1984-03-15_letter-alice.pdf",
          "size_bytes": 245000,
          "word_count": 842,
          "confidence": "high",
          "ingested_at": "2026-04-01",
          "recommended": true
        },
        {
          "path": "Letters/1984/1984-03-15_letter-alice-copy.pdf",
          "size_bytes": 245000,
          "word_count": 842,
          "confidence": "high",
          "ingested_at": "2026-04-08",
          "recommended": false
        }
      ],
      "keep": "Letters/1984/1984-03-15_letter-alice.pdf",
      "approved": true
    }
  ]
}
```

### `_duplicate-proposals.md`

Human-readable summary:

```markdown
# Duplicate Proposals

Generated: 2026-04-11
Groups: 12 (8 exact, 3 text-similar, 1 perceptual)

## Group dup-001 — Exact Match (100%)
**Keep:** Letters/1984/1984-03-15_letter-alice.pdf
| File | Size | Words | Confidence | Ingested |
|------|------|-------|------------|----------|
| **1984-03-15_letter-alice.pdf** | 245 KB | 842 | high | 2026-04-01 |
| 1984-03-15_letter-alice-copy.pdf | 245 KB | 842 | high | 2026-04-08 |
```

### User workflow

1. `family-archive duplicates --scan` — runs detection, writes proposals
2. User reviews `_duplicate-proposals.md`, edits `_duplicate-proposals.json` (change `keep`, set `approved: false` to skip)
3. `family-archive duplicates --apply` — quarantines the non-keep files from approved groups
4. `family-archive duplicates --purge` — permanently deletes quarantined files past TTL

## Lifecycle Module (`scripts/duplicate_manage.py`)

### Quarantine

- Reads approved groups from `_duplicate-proposals.json`
- Moves non-keep files to `_duplicates/` folder under the archive root
- Preserves folder structure: `_duplicates/Letters/1984/file.pdf`
- Records each quarantined file in the `quarantine` SQLite table with `purge_after = quarantined_at + 14 days`
- Updates the `files` table path to reflect the new location
- Preserves associated `.transcript.md` files — they move with their source file

### Restore

- `family-archive duplicates --restore <path>` — moves a quarantined file back to its original location
- Removes the `quarantine` table entry
- Updates the `files` table path back

### Purge

- `family-archive duplicates --purge` — permanently deletes all quarantined files past their `purge_after` timestamp
- Removes associated `quarantine`, `files`, `transcripts`, `fingerprints`, and `provenance` rows
- `family-archive duplicates --purge --all` — purge everything in quarantine regardless of TTL

### Status

- `family-archive duplicates --status` — shows quarantine summary: file count, total size, how many past TTL and ready to purge

## Ingest Integration

### At scan time (`--scan`)

- After classifying source files, compute MD5 hashes for each
- Check each hash against the existing `files` table and `provenance` table
- If a source file's hash matches an existing archive file:
  - `"status": "duplicate"` in the ingest plan
  - `"duplicate_of": "Letters/1984/letter.pdf"`
  - `"approved": false` (user must explicitly approve to ingest a known duplicate)
- Replaces the current merge-mode duplicate logic in `ingest.py`

### At execute time (`--execute`)

- For each file copied into the archive, write a `provenance` record:
  - `operation = "ingest"`
  - `source_path` = original source file path
  - `source_hash` = MD5 of the source file

### Idempotency guarantees

- Re-running `ingest --scan` on the same source produces the same plan (deterministic)
- Re-running `ingest --execute` on an already-executed plan skips files already in the archive (checks provenance by source hash)
- Files added outside the pipeline are caught by standalone `family-archive duplicates --scan`

### Split integration

- When `split_apply.py` creates child PDFs, it writes a `provenance` record:
  - `operation = "split"`
  - `parent_file_id` = the compilation PDF's file ID
  - `detail = {"pages": "5-8"}`
- This is a new call added to `split_apply.py`

## CLI Commands

### New: `family-archive duplicates`

```
family-archive duplicates --scan                    # detect duplicates, write proposals
family-archive duplicates --scan --dry-run           # preview what would be detected
family-archive duplicates --apply                    # quarantine approved duplicates
family-archive duplicates --apply --dry-run          # preview quarantine actions
family-archive duplicates --status                   # show quarantine summary
family-archive duplicates --restore <path>           # restore a specific file
family-archive duplicates --purge                    # delete files past 14-day TTL
family-archive duplicates --purge --all              # delete all quarantined files
```

### Scan options

```
--folder Letters                   # limit scan to one folder
--type exact                       # only exact matches
--type similar                     # only near-duplicates
--threshold 0.85                   # text similarity threshold (default 0.90)
```

### Modified existing commands

- `family-archive ingest --scan` — duplicate detection integrated automatically
- `family-archive reindex --fingerprints` — compute and store perceptual hashes during reindex (opt-in)

### Removed

- `scripts/handle_duplicates.py` — fully superseded. Remove along with `Duplicates/` folder convention (replaced by `_duplicates/`).

## File Map

### New files

- `scripts/duplicate_detect.py` — detection strategies, fingerprint computation, proposal generation
- `scripts/duplicate_manage.py` — quarantine, restore, purge, TTL, status
- `tests/test_duplicate_detect.py` — detection tests
- `tests/test_duplicate_manage.py` — lifecycle tests

### Modified files

- `scripts/db.py` — add `provenance`, `fingerprints`, `quarantine` tables; bump `SCHEMA_VERSION` to 2
- `scripts/cli.py` — add `duplicates` subcommand with all flags
- `scripts/ingest.py` — replace merge-mode duplicate logic, write provenance records
- `scripts/split_apply.py` — write provenance records for split children
- `pyproject.toml` — add `imagehash` dependency
- `docs/WORKFLOW.md` — add duplicates step

### Removed files

- `scripts/handle_duplicates.py` — superseded

## Future Considerations

### Web UI (Phase 3)

- Browse quarantined files with previews
- One-click restore or delete per file
- Re-ingest a quarantined file to a different location (handling filename collisions)
- Bulk approve/reject from the quarantine view
- Visual side-by-side comparison for near-duplicates

### SQLite as universal state backend

Long-term direction: migrate all proposal systems (splits, renames, ingest plans) from JSON files to SQLite-backed state. JSON/markdown files become the human-readable review layer generated from and edited back into the database. This improves queryability, scalability, and cross-feature integration.
