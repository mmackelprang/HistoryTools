# SQLite Index with Full-Text Search — Design Spec

## Goal

A SQLite database (`.archive.db`) that indexes all files and transcript text in the archive, enabling instant full-text search via `family-archive search "keyword"`. Built incrementally during pipeline operations and rebuildable from scratch via `family-archive reindex`.

## Architecture

- Single file: `{dest_root}/.archive.db` (configurable via `config.json` `db_path`)
- Schema: `files` table + `transcripts` table + FTS5 virtual table for search
- Populated primarily via `family-archive reindex` (full filesystem scan)
- Incrementally updated by pipeline scripts via shared `db.py` functions
- DB is a cache — delete and rebuild anytime, filesystem is truth

## Database Location

Configurable via `config.json`:
```json
{
  "db_path": null
}
```

When `null` (default), DB is created at `{dest_root}/.archive.db`.

## Schema

```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,         -- relative to dest_root
    filename TEXT NOT NULL,
    folder TEXT NOT NULL,              -- top-level folder (Letters, Journals, etc.)
    subfolder TEXT,                    -- year or subfolder
    file_type TEXT,                    -- normalized category: document, audio, photo, video, transcript, etc.
    size_bytes INTEGER,
    date_prefix TEXT,                  -- YYYY-MM-DD or "undated"
    md5_hash TEXT,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transcripts (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    summary TEXT,
    confidence TEXT,                   -- high, medium, low, pending
    method TEXT,                       -- ai-vision, native, ocr, split, assemblyai, whisper
    word_count INTEGER,
    formatting TEXT,                   -- null or "cleaned"
    transcription_date TEXT
);

-- FTS5 virtual table for full-text search across transcript bodies
CREATE VIRTUAL TABLE transcripts_fts USING fts5(
    path,                              -- file path (for display in results)
    body,                              -- full transcript text
    content='transcripts_content',
    content_rowid='rowid'
);

-- Backing table for FTS5 content (required by external-content FTS5)
CREATE TABLE transcripts_content (
    rowid INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id),
    path TEXT,
    body TEXT
);
```

## CLI Commands

### `family-archive reindex`

Full rebuild of the database from filesystem:

1. Create/open `.archive.db`
2. Walk all files under `dest_root`, insert/update `files` table
3. For each `.transcript.md`, parse frontmatter + body:
   - Insert/update `transcripts` table (confidence, method, word count, etc.)
   - Insert/update `transcripts_content` + rebuild FTS5 index
4. Remove DB entries for files no longer on disk (orphan cleanup)
5. Print summary

```bash
family-archive reindex                    # full rebuild
family-archive reindex --check            # verify DB matches filesystem, report drift
```

### `family-archive search`

Full-text search across all transcript bodies using FTS5:

```bash
family-archive search "keyword"                    # search all transcripts
family-archive search "keyword" --folder Letters    # filter by top-level folder
family-archive search "keyword" --type audio        # filter by file type
family-archive search "keyword" --year 1983         # filter by date prefix year
family-archive search "keyword" --limit 20          # limit results (default 10)
```

Output format:
```
Found 3 results for "Springfield":

  1. Letters/1984/1984-03-15_letter-alice-bob.transcript.md
     "...we drove to Springfield last week and visited..."
     (document, 1984-03-15, 842 words)

  2. AudioRecordings/CassetteTapes/1984-06-14_audio-tape.transcript.md
     "...when we went to Springfield that time..."
     (audio, 1984-06-14, 7417 words)
```

Results show:
- File path (relative to dest_root)
- Snippet with search term highlighted in context
- Metadata: file type, date, word count

### `family-archive stats`

Archive statistics from the database:

```
Archive: F:/Archive/Organized
Database: F:/Archive/Organized/.archive.db

Files:        1,278
  Documents:    336
  Audio:         34
  Photos:       749
  Video:          3
  Other:        156

Transcripts:    560
  High:         400
  Medium:       132
  Low:           28

Total words: 1,245,000
Last indexed: 2026-04-10 18:30:00
```

## Implementation: `scripts/db.py`

Single new module with clean interface:

### Database lifecycle
- `get_db(dest_root, config=None)` — open or create DB, return connection
- `init_schema(conn)` — create tables if they don't exist
- `close_db(conn)` — close connection

### Indexing
- `index_file(conn, dest_root, file_path)` — insert/update a single file in `files` table
- `index_transcript(conn, dest_root, transcript_path)` — parse frontmatter + body, update `transcripts` + FTS
- `reindex_all(conn, dest_root)` — full filesystem walk, index everything, clean orphans
- `check_index(conn, dest_root)` — compare DB against filesystem, report drift

### Search
- `search(conn, query, folder=None, file_type=None, year=None, limit=10)` — FTS5 search, return results
- `get_stats(conn)` — return dict of archive statistics

### Incremental update (for other scripts to call)
- `update_file_index(dest_root, file_path)` — convenience wrapper: open DB, index file, close
- `update_transcript_index(dest_root, transcript_path)` — convenience wrapper: open DB, index transcript, close

## Frontmatter Parsing

To populate the `transcripts` table, `db.py` parses `.transcript.md` frontmatter:

```yaml
---
source_file: letter.pdf
transcription_confidence: high
transcription_method: ai-vision (gemini-2.5-flash)
word_count: 842
formatting: cleaned
transcription_date: 2026-04-10
---
```

Extracts: confidence, method, word_count, formatting, transcription_date.
Body text (after `---`) goes into `transcripts_content` for FTS.

## Reindex Performance

For a 1,000-file archive:
- File scanning: ~1 second (just stat + path parsing)
- Transcript parsing: ~2-3 seconds (read files, parse frontmatter)
- FTS indexing: ~1 second (SQLite is fast)
- Total: ~5 seconds for a full reindex

## Incremental Update Integration

For Phase 2, key scripts will call `update_transcript_index()` after processing:
- `transcribe_pdfs.py` / `transcribe_pdfs_gemini.py` — after creating transcript
- `format_transcripts.py` — after formatting
- `split_apply.py` — after creating split transcripts
- `apply_renames.py` — after renaming (path changes)

This is wired up incrementally — scripts that don't call it yet still work,
the DB just stays stale until `reindex` runs.

## Safety

- DB is a rebuildable cache — delete `.archive.db` and `reindex` to recreate
- `reindex --check` verifies without modifying
- `.archive.db` already in `.gitignore`
- No data lives only in the DB — filesystem `.transcript.md` files are truth
- Schema versioning via `PRAGMA user_version` for future migrations

## Future Schema Extensions (not implemented now)

These tables will be added in later phases without breaking the current schema:

- `speakers` — speaker labels and names from audio transcripts
- `entities` — people, places, events (from entity extraction)
- `references` — connections between artifacts and entities
- `anchors` — precise locations within artifacts (page, timestamp, coordinates)
- `photos` — EXIF data, AI descriptions, face data
- `tags` — user-applied or AI-generated tags
- `location_history` — Google Timeline data
