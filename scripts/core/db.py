"""
SQLite index with full-text search for the Family Archive.

Provides a rebuildable SQLite database that indexes all files and transcript
text in the archive, enabling instant full-text search via the CLI.

The database is a cache — delete .archive.db and reindex to recreate.
Filesystem .transcript.md files are the source of truth.
"""

import os
import re
import sqlite3
import hashlib
from pathlib import Path

# Schema version — bump when schema changes
SCHEMA_VERSION = 2

# Date prefix pattern: YYYY-MM-DD_ at start of filename
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
UNDATED_PREFIX_RE = re.compile(r"^undated_")

# Extension → file type mapping (matches taxonomy in config.py)
_EXT_TYPE_MAP = {
    # audio
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio",
    ".ogg": "audio", ".flac": "audio", ".wma": "audio",
    # video
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video",
    ".wmv": "video",
    # photo
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".tiff": "photo",
    ".tif": "photo", ".bmp": "photo", ".heic": "photo",
    # document
    ".pdf": "document", ".doc": "document", ".docx": "document",
    ".txt": "document", ".rtf": "document",
    # spreadsheet
    ".xls": "spreadsheet", ".xlsx": "spreadsheet", ".csv": "spreadsheet",
    # email
    ".eml": "email", ".mbox": "email", ".pst": "email",
    # genealogy
    ".gedcom": "genealogy", ".ged": "genealogy",
}


def _get_file_type(filename):
    """Classify a file by its extension."""
    name = filename.lower()
    if name.endswith(".transcript.md"):
        return "transcript"
    ext = os.path.splitext(name)[1]
    # .md files that aren't .transcript.md are documents (README, etc.)
    if ext == ".md":
        return "document"
    return _EXT_TYPE_MAP.get(ext, "unknown")


def _get_date_prefix(filename):
    """Extract date prefix from filename, or 'undated' if undated_ prefix, else None."""
    m = DATE_PREFIX_RE.match(filename)
    if m:
        return m.group(1)
    if UNDATED_PREFIX_RE.match(filename):
        return "undated"
    return None


def _rel_path(dest_root, file_path):
    """Get relative path from dest_root, using forward slashes."""
    try:
        rel = Path(file_path).relative_to(Path(dest_root))
    except ValueError:
        # If file_path is not under dest_root, use the full path
        rel = Path(file_path)
    return str(rel).replace("\\", "/")


def _parse_folder_subfolder(rel_path_str):
    """Extract folder (first component) and subfolder (second component) from relative path."""
    parts = rel_path_str.split("/")
    folder = parts[0] if len(parts) > 1 else ""
    subfolder = parts[1] if len(parts) > 2 else None
    return folder, subfolder


_MD5_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB — skip hashing large files (videos, etc.)


def _file_md5(file_path):
    """Compute MD5 hash of a file. Skips files larger than 50 MB."""
    try:
        if file_path.stat().st_size > _MD5_SIZE_LIMIT:
            return None
    except OSError:
        return None
    h = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        return None


def parse_frontmatter(content):
    """Parse YAML frontmatter and body from a transcript file.

    Returns (fm_dict, body) where fm_dict is a dict of frontmatter fields
    and body is the text after the closing ---.
    """
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    fm_text = parts[1].strip()
    body = parts[2].strip()

    fm_dict = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm_dict[key.strip()] = val.strip()

    return fm_dict, body


# ── Database lifecycle ─────────────────────────────────────────────────────


def get_db(dest_root, config=None):
    """Open or create the archive database, initialize schema, return connection.

    Args:
        dest_root: Path to the archive root directory.
        config: Optional config dict. If config["db_path"] is set, use that path.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    if config and config.get("db_path"):
        db_path = Path(config["db_path"])
    else:
        db_path = Path(dest_root) / ".archive.db"

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        wal_result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if wal_result and wal_result[0].lower() != "wal":
            print(f"Warning: WAL mode not enabled (got {wal_result[0]})")
        init_schema(conn)
        return conn
    except sqlite3.DatabaseError as e:
        print(f"Database appears corrupt: {e}")
        print(f"Delete {db_path} and run 'family-archive reindex' to rebuild.")
        raise


def init_schema(conn):
    """Create tables if they don't exist. Set schema version.
    Checks existing version for forward compatibility."""
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is newer than code version {SCHEMA_VERSION}. "
            "Please update HistoryTools."
        )
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
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

        CREATE TABLE IF NOT EXISTS transcripts (
            file_id INTEGER PRIMARY KEY REFERENCES files(id),
            summary TEXT,
            confidence TEXT,
            method TEXT,
            word_count INTEGER,
            formatting TEXT,
            transcription_date TEXT
        );

        CREATE TABLE IF NOT EXISTS transcripts_content (
            rowid INTEGER PRIMARY KEY,
            file_id INTEGER REFERENCES files(id),
            path TEXT,
            body TEXT
        );
    """)

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

        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            model TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            page_start INTEGER NOT NULL DEFAULT 0,
            chunk_pages INTEGER,
            status TEXT NOT NULL DEFAULT 'submitted',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            UNIQUE(batch_id)
        );

        CREATE INDEX IF NOT EXISTS idx_provenance_source_hash
            ON provenance(source_hash);
        CREATE INDEX IF NOT EXISTS idx_provenance_parent
            ON provenance(parent_file_id);
    """)

    # Migrate batches table if missing chunking columns (added after initial release)
    cursor = conn.execute("PRAGMA table_info(batches)")
    batch_cols = {row[1] for row in cursor.fetchall()}
    if "batches" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
        if "page_start" not in batch_cols:
            conn.execute("ALTER TABLE batches ADD COLUMN page_start INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE batches ADD COLUMN chunk_pages INTEGER")
            conn.commit()

    # Create FTS5 table if it doesn't exist
    # Check if it already exists first to avoid error
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts_fts'"
    )
    if cursor.fetchone() is None:
        conn.execute("""
            CREATE VIRTUAL TABLE transcripts_fts USING fts5(
                path,
                body,
                content='transcripts_content',
                content_rowid='rowid'
            )
        """)

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def close_db(conn):
    """Close the database connection."""
    if conn:
        conn.close()


# ── Indexing ───────────────────────────────────────────────────────────────


def index_file(conn, dest_root, file_path, _commit=True):
    """Insert or update a single file in the files table.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
        file_path: Absolute or relative path to the file.
        _commit: If True (default), commit after upsert. Set False for batch operations.

    Returns:
        The file's row id.
    """
    file_path = Path(file_path)
    rel = _rel_path(dest_root, file_path)
    filename = file_path.name
    folder, subfolder = _parse_folder_subfolder(rel)
    file_type = _get_file_type(filename)
    date_prefix = _get_date_prefix(filename)

    try:
        size_bytes = file_path.stat().st_size
    except OSError:
        size_bytes = 0

    md5 = _file_md5(file_path)

    conn.execute("""
        INSERT INTO files (path, filename, folder, subfolder, file_type,
                           size_bytes, date_prefix, md5_hash, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(path) DO UPDATE SET
            filename = excluded.filename,
            folder = excluded.folder,
            subfolder = excluded.subfolder,
            file_type = excluded.file_type,
            size_bytes = excluded.size_bytes,
            date_prefix = excluded.date_prefix,
            md5_hash = excluded.md5_hash,
            indexed_at = excluded.indexed_at
    """, (rel, filename, folder, subfolder, file_type, size_bytes, date_prefix, md5))
    if _commit:
        conn.commit()

    # Return the row id
    cursor = conn.execute("SELECT id FROM files WHERE path = ?", (rel,))
    row = cursor.fetchone()
    return row["id"] if row else None


def index_transcript(conn, dest_root, transcript_path, _commit=True, _maintain_fts=True):
    """Parse a .transcript.md file and update transcripts + FTS tables.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
        transcript_path: Path to the .transcript.md file.
        _commit: If True (default), commit after update. Set False for batch operations.
        _maintain_fts: If True (default), maintain FTS index incrementally.
            Set False during bulk reindex when a final FTS rebuild will follow.
    """
    transcript_path = Path(transcript_path)
    rel = _rel_path(dest_root, transcript_path)

    # Ensure the file is indexed in the files table first
    file_id = index_file(conn, dest_root, transcript_path, _commit=_commit)
    if file_id is None:
        return

    # Read and parse the transcript
    try:
        content = transcript_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return

    fm_dict, body = parse_frontmatter(content)

    confidence = fm_dict.get("transcription_confidence", None)
    method = fm_dict.get("transcription_method", None)
    formatting = fm_dict.get("formatting", None)
    transcription_date = fm_dict.get("transcription_date", None)

    # Word count from frontmatter or compute from body
    word_count_str = fm_dict.get("word_count", None)
    if word_count_str and word_count_str.isdigit():
        word_count = int(word_count_str)
    else:
        word_count = len(body.split()) if body else 0

    # Update transcripts table
    conn.execute("""
        INSERT OR REPLACE INTO transcripts (file_id, summary, confidence, method,
                                            word_count, formatting, transcription_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (file_id, None, confidence, method, word_count, formatting, transcription_date))

    # Update the backing table (transcripts_content) and optionally maintain FTS
    cursor = conn.execute(
        "SELECT rowid, path, body FROM transcripts_content WHERE file_id = ?", (file_id,)
    )
    old_row = cursor.fetchone()
    if old_row:
        old_rowid = old_row["rowid"]
        if _maintain_fts:
            old_path = old_row["path"] or ""
            old_body = old_row["body"] or ""
            conn.execute(
                "INSERT INTO transcripts_fts(transcripts_fts, rowid, path, body) VALUES('delete', ?, ?, ?)",
                (old_rowid, old_path, old_body)
            )
        conn.execute(
            "UPDATE transcripts_content SET path = ?, body = ? WHERE rowid = ?",
            (rel, body, old_rowid)
        )
        if _maintain_fts:
            conn.execute(
                "INSERT INTO transcripts_fts(rowid, path, body) VALUES(?, ?, ?)",
                (old_rowid, rel, body)
            )
    else:
        conn.execute("""
            INSERT INTO transcripts_content (file_id, path, body)
            VALUES (?, ?, ?)
        """, (file_id, rel, body))
        if _maintain_fts:
            cursor = conn.execute(
                "SELECT rowid FROM transcripts_content WHERE file_id = ?", (file_id,)
            )
            new_row = cursor.fetchone()
            if new_row:
                conn.execute(
                    "INSERT INTO transcripts_fts(rowid, path, body) VALUES(?, ?, ?)",
                    (new_row["rowid"], rel, body)
                )

    if _commit:
        conn.commit()


def reindex_all(conn, dest_root):
    """Walk the filesystem and index all files and transcripts.

    Removes orphan entries (DB entries with no corresponding file on disk).
    Prints progress during the operation.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
    """
    dest_root = Path(dest_root)
    print(f"Reindexing: {dest_root}")

    # Collect all files
    all_files = []
    transcript_files = []
    skip_dirs = {".organizer", ".trashbox", "__pycache__", "_historytools_temp"}

    for dirpath, dirnames, filenames in os.walk(str(dest_root)):
        # Skip hidden/system directories
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]

        for fname in filenames:
            # Skip hidden files and the database files themselves
            if fname.startswith("."):
                continue
            fpath = Path(dirpath) / fname
            all_files.append(fpath)
            if fname.endswith(".transcript.md"):
                transcript_files.append(fpath)

    total_files = len(all_files)
    total_transcripts = len(transcript_files)
    print(f"Found {total_files} files, {total_transcripts} transcripts")

    # Index all files (batch commit for performance)
    for i, fpath in enumerate(all_files, 1):
        if i % 200 == 0 or i == total_files:
            print(f"  Files: {i}/{total_files}")
        index_file(conn, dest_root, fpath, _commit=False)
    conn.commit()

    # Index all transcripts (skip per-entry FTS — rebuilt at end)
    for i, tpath in enumerate(transcript_files, 1):
        if i % 50 == 0 or i == total_transcripts:
            print(f"  Transcripts: {i}/{total_transcripts}")
        index_transcript(conn, dest_root, tpath, _commit=False, _maintain_fts=False)
    conn.commit()

    # Remove orphans — DB entries for files no longer on disk
    cursor = conn.execute("SELECT id, path FROM files")
    orphan_ids = []
    for row in cursor.fetchall():
        full_path = dest_root / row["path"]
        if not full_path.exists():
            orphan_ids.append(row["id"])

    if orphan_ids:
        placeholders = ",".join("?" * len(orphan_ids))
        conn.execute(f"DELETE FROM transcripts WHERE file_id IN ({placeholders})", orphan_ids)
        conn.execute(f"DELETE FROM transcripts_content WHERE file_id IN ({placeholders})", orphan_ids)
        conn.execute(f"DELETE FROM files WHERE id IN ({placeholders})", orphan_ids)
        conn.commit()
        print(f"  Removed {len(orphan_ids)} orphan entries")

    # Rebuild the full FTS index to ensure consistency
    conn.execute("INSERT INTO transcripts_fts(transcripts_fts) VALUES('rebuild')")
    conn.commit()

    # Print summary
    stats = get_stats(conn)
    print(f"\nIndex complete:")
    print(f"  Files:       {stats['total_files']}")
    print(f"  Transcripts: {stats['total_transcripts']}")
    print(f"  Total words: {stats['total_words']:,}")


def check_index(conn, dest_root):
    """Compare DB against filesystem and report drift.

    Reports missing files (on disk but not in DB), extra files (in DB but not
    on disk), and counts.

    Args:
        conn: SQLite connection.
        dest_root: Archive root directory.
    """
    dest_root = Path(dest_root)
    print(f"Checking index: {dest_root}")

    # Get all files on disk
    skip_dirs = {".organizer", ".trashbox", "__pycache__", "_historytools_temp"}
    disk_files = set()
    for dirpath, dirnames, filenames in os.walk(str(dest_root)):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for fname in filenames:
            if fname.startswith("."):
                continue
            fpath = Path(dirpath) / fname
            rel = _rel_path(dest_root, fpath)
            disk_files.add(rel)

    # Get all files in DB
    cursor = conn.execute("SELECT path FROM files")
    db_files = set(row["path"] for row in cursor.fetchall())

    missing = disk_files - db_files
    extra = db_files - disk_files

    if not missing and not extra:
        print("Index is up to date.")
    else:
        if missing:
            print(f"\nMissing from index ({len(missing)} files):")
            for p in sorted(missing)[:20]:
                print(f"  + {p}")
            if len(missing) > 20:
                print(f"  ... and {len(missing) - 20} more")

        if extra:
            print(f"\nOrphan entries ({len(extra)} files):")
            for p in sorted(extra)[:20]:
                print(f"  - {p}")
            if len(extra) > 20:
                print(f"  ... and {len(extra) - 20} more")

    print(f"\nDisk: {len(disk_files)} files, DB: {len(db_files)} files")
    if missing or extra:
        print("Run 'family-archive reindex' to fix.")


# ── Search ─────────────────────────────────────────────────────────────────


def search(conn, query, folder=None, file_type=None, year=None, limit=10):
    """Full-text search across transcript bodies.

    Args:
        conn: SQLite connection.
        query: FTS5 search query string.
        folder: Optional folder filter (top-level folder name).
        file_type: Optional file type filter (e.g., "audio", "document").
        year: Optional year filter (matches date_prefix starting with this year).
        limit: Maximum number of results (default 10).

    Returns:
        List of dicts with keys: path, snippet, date_prefix, word_count, file_type.
    """
    if not query or not query.strip():
        return []

    # Build the query with optional filters
    sql = """
        SELECT
            f.path,
            f.date_prefix,
            f.file_type,
            f.folder,
            t.word_count,
            snippet(transcripts_fts, 1, '...', '...', '...', 20) AS snippet
        FROM transcripts_fts fts
        JOIN transcripts_content tc ON tc.rowid = fts.rowid
        JOIN files f ON f.id = tc.file_id
        JOIN transcripts t ON t.file_id = f.id
        WHERE transcripts_fts MATCH ?
    """
    params = [query]

    if folder:
        sql += " AND f.folder = ?"
        params.append(folder)

    if file_type:
        sql += " AND f.file_type = ?"
        params.append(file_type)

    if year:
        sql += " AND f.date_prefix LIKE ?"
        params.append(f"{year}%")

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    try:
        cursor = conn.execute(sql, params)
    except sqlite3.OperationalError as exc:
        # Only swallow FTS query-syntax errors; re-raise real DB problems
        msg = str(exc).lower()
        if any(marker in msg for marker in (
            "fts5: syntax error",
            "unterminated string",
            "malformed match expression",
        )):
            return []
        raise

    results = []
    for row in cursor.fetchall():
        results.append({
            "path": row["path"],
            "snippet": row["snippet"] or "",
            "date_prefix": row["date_prefix"] or "undated",
            "word_count": row["word_count"] or 0,
            "file_type": row["file_type"] or "unknown",
            "folder": row["folder"] or "",
        })

    return results


def get_stats(conn):
    """Return archive statistics from the database.

    Returns:
        Dict with keys: total_files, files_by_type, total_transcripts,
        transcripts_by_confidence, total_words, last_indexed.
    """
    stats = {}

    # Total files
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM files")
    stats["total_files"] = cursor.fetchone()["cnt"]

    # Files by type
    cursor = conn.execute(
        "SELECT file_type, COUNT(*) as cnt FROM files GROUP BY file_type ORDER BY cnt DESC"
    )
    stats["files_by_type"] = {row["file_type"]: row["cnt"] for row in cursor.fetchall()}

    # Total transcripts
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM transcripts")
    stats["total_transcripts"] = cursor.fetchone()["cnt"]

    # Transcripts by confidence
    cursor = conn.execute(
        "SELECT confidence, COUNT(*) as cnt FROM transcripts GROUP BY confidence ORDER BY cnt DESC"
    )
    stats["transcripts_by_confidence"] = {
        (row["confidence"] or "unknown"): row["cnt"] for row in cursor.fetchall()
    }

    # Total words
    cursor = conn.execute("SELECT COALESCE(SUM(word_count), 0) as total FROM transcripts")
    stats["total_words"] = cursor.fetchone()["total"]

    # Last indexed timestamp
    cursor = conn.execute("SELECT MAX(indexed_at) as last_ts FROM files")
    row = cursor.fetchone()
    stats["last_indexed"] = row["last_ts"] if row else None

    return stats


# ── Convenience wrappers ───────────────────────────────────────────────────


def update_file_index(dest_root, file_path):
    """Convenience: open DB, index one file, close DB.

    For use by other pipeline scripts after processing a file.
    """
    conn = get_db(dest_root)
    try:
        index_file(conn, dest_root, file_path)
    finally:
        close_db(conn)


def update_transcript_index(dest_root, transcript_path):
    """Convenience: open DB, index one transcript, close DB.

    For use by other pipeline scripts after creating/updating a transcript.
    """
    conn = get_db(dest_root)
    try:
        index_transcript(conn, dest_root, transcript_path)
    finally:
        close_db(conn)
