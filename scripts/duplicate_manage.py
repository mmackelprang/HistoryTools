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
    """Move approved duplicate files to _duplicates/ and record them in the quarantine table.

    Reads _duplicate-proposals.json from dest_root. For each approved group,
    non-keep files are moved to _duplicates/<original_relative_path>. Associated
    .transcript.md files are moved alongside their source. Each quarantined file
    is recorded in the quarantine table with a 14-day TTL.

    Args:
        conn: SQLite connection.
        dest_root: Path to the archive root directory.
        dry_run: If True, print what would happen but make no changes.

    Returns:
        dict with keys: quarantined, skipped, errors.
    """
    dest_root = Path(dest_root)
    proposals_path = dest_root / "_duplicate-proposals.json"

    if not proposals_path.exists():
        print("No _duplicate-proposals.json found. Run duplicate detection first.")
        return {"quarantined": 0, "skipped": 0, "errors": 0}

    with open(proposals_path, encoding="utf-8") as f:
        data = json.load(f)

    groups = data.get("groups", [])
    quarantined = 0
    skipped = 0
    errors = 0

    for group in groups:
        if not group.get("approved", False):
            skipped_in_group = len(group.get("files", [])) - 1
            skipped += max(skipped_in_group, 0)
            continue

        keep_path = group.get("keep", "")
        reason = group.get("match_type", "unknown")
        files = group.get("files", [])

        for file_entry in files:
            file_rel = file_entry.get("path", "")
            if file_rel == keep_path:
                continue

            abs_path = dest_root / file_rel

            if not abs_path.exists():
                print(f"  Skipping (not found): {file_rel}")
                skipped += 1
                continue

            quarantine_rel = "_duplicates/" + file_rel
            quarantine_abs = dest_root / quarantine_rel

            if dry_run:
                print(f"  [dry-run] Would quarantine: {file_rel} -> {quarantine_rel}")
                quarantined += 1
                continue

            try:
                quarantine_abs.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(abs_path), str(quarantine_abs))
                print(f"  Quarantined: {file_rel} -> {quarantine_rel}")

                # Move associated transcript if it exists
                stem = abs_path.stem
                transcript_name = stem + ".transcript.md"
                transcript_abs = abs_path.parent / transcript_name
                transcript_quarantine_abs = None
                if transcript_abs.exists():
                    transcript_rel = str(
                        transcript_abs.relative_to(dest_root)
                    ).replace("\\", "/")
                    transcript_quarantine_abs = dest_root / "_duplicates" / transcript_rel
                    transcript_quarantine_abs.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(transcript_abs), str(transcript_quarantine_abs))
                    print(f"  Quarantined transcript: {transcript_rel}")

                # Look up file_hash and file_size from the files table
                row = conn.execute(
                    "SELECT md5_hash, size_bytes FROM files WHERE path = ?",
                    (file_rel,),
                ).fetchone()
                file_hash = row["md5_hash"] if row else None
                file_size = row["size_bytes"] if row else None

                # Record in quarantine table
                conn.execute(
                    """
                    INSERT INTO quarantine
                        (original_path, quarantine_path, duplicate_of, reason,
                         purge_after, file_hash, file_size)
                    VALUES (?, ?, ?, ?, datetime('now', ?), ?, ?)
                    """,
                    (
                        file_rel,
                        quarantine_rel,
                        keep_path,
                        reason,
                        f"+{DEFAULT_TTL_DAYS} days",
                        file_hash,
                        file_size,
                    ),
                )
                conn.commit()
                quarantined += 1

            except Exception as exc:
                print(f"  Error quarantining {file_rel}: {exc}")
                errors += 1

    print(f"Quarantine complete: {quarantined} quarantined, {skipped} skipped, {errors} errors")
    return {"quarantined": quarantined, "skipped": skipped, "errors": errors}


def restore_file(conn, dest_root, quarantine_path):
    """Move a quarantined file back to its original location.

    Looks up the quarantine record by quarantine_path, moves the file from
    _duplicates/ back to original_path, restores associated transcript if
    present, and removes the quarantine DB record.

    Args:
        conn: SQLite connection.
        dest_root: Path to the archive root directory.
        quarantine_path: The relative quarantine path (as stored in the quarantine table).
    """
    dest_root = Path(dest_root)

    row = conn.execute(
        "SELECT id, original_path, quarantine_path FROM quarantine WHERE quarantine_path = ?",
        (quarantine_path,),
    ).fetchone()

    if row is None:
        print(f"No quarantine record found for: {quarantine_path}")
        return

    record_id = row["id"]
    original_path = row["original_path"]
    q_path = row["quarantine_path"]

    quarantine_abs = dest_root / q_path
    original_abs = dest_root / original_path

    if not quarantine_abs.exists():
        print(f"Quarantined file not found on disk: {quarantine_abs}")
        return

    # Restore the main file
    original_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(quarantine_abs), str(original_abs))
    print(f"Restored: {q_path} -> {original_path}")

    # Restore associated transcript if it exists in quarantine
    q_stem = quarantine_abs.stem
    transcript_quarantine_abs = quarantine_abs.parent / (q_stem + ".transcript.md")
    if transcript_quarantine_abs.exists():
        original_stem = original_abs.stem
        transcript_original_abs = original_abs.parent / (original_stem + ".transcript.md")
        transcript_original_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(transcript_quarantine_abs), str(transcript_original_abs))
        print(f"Restored transcript: {transcript_quarantine_abs.name}")

    # Delete the quarantine record
    conn.execute("DELETE FROM quarantine WHERE id = ?", (record_id,))
    conn.commit()
    print(f"Quarantine record removed for: {original_path}")


def purge_expired(conn, dest_root, purge_all=False):
    """Permanently delete files past their TTL from _duplicates/.

    If purge_all is True, deletes all quarantined files regardless of TTL.
    Otherwise only deletes those whose purge_after <= now. Removes DB records
    from quarantine, files, transcripts, transcripts_content, fingerprints,
    and provenance tables. Cleans up empty directories in _duplicates/.

    Args:
        conn: SQLite connection.
        dest_root: Path to the archive root directory.
        purge_all: If True, ignore TTL and purge everything.

    Returns:
        dict with key: purged (count of files deleted).
    """
    dest_root = Path(dest_root)

    if purge_all:
        rows = conn.execute(
            "SELECT id, original_path, quarantine_path FROM quarantine"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, original_path, quarantine_path FROM quarantine "
            "WHERE purge_after <= datetime('now')"
        ).fetchall()

    purged = 0

    for row in rows:
        record_id = row["id"]
        original_path = row["original_path"]
        q_path = row["quarantine_path"]

        quarantine_abs = dest_root / q_path

        # Delete the quarantined file
        if quarantine_abs.exists():
            quarantine_abs.unlink()
            print(f"  Purged: {q_path}")
        else:
            print(f"  Already gone: {q_path}")

        # Delete associated transcript if present
        q_stem = quarantine_abs.stem
        transcript_abs = quarantine_abs.parent / (q_stem + ".transcript.md")
        if transcript_abs.exists():
            transcript_abs.unlink()
            print(f"  Purged transcript: {transcript_abs.name}")

        # Clean up DB records for the original path
        file_row = conn.execute(
            "SELECT id FROM files WHERE path = ?", (original_path,)
        ).fetchone()
        if file_row:
            fid = file_row["id"]
            conn.execute("DELETE FROM transcripts WHERE file_id = ?", (fid,))
            conn.execute("DELETE FROM transcripts_content WHERE file_id = ?", (fid,))
            conn.execute("DELETE FROM fingerprints WHERE file_id = ?", (fid,))
            conn.execute("DELETE FROM provenance WHERE file_id = ?", (fid,))
            conn.execute("DELETE FROM files WHERE id = ?", (fid,))

        # Also clean up DB records for the quarantine path itself (may differ)
        q_file_row = conn.execute(
            "SELECT id FROM files WHERE path = ?", (q_path,)
        ).fetchone()
        if q_file_row:
            qfid = q_file_row["id"]
            conn.execute("DELETE FROM transcripts WHERE file_id = ?", (qfid,))
            conn.execute("DELETE FROM transcripts_content WHERE file_id = ?", (qfid,))
            conn.execute("DELETE FROM fingerprints WHERE file_id = ?", (qfid,))
            conn.execute("DELETE FROM provenance WHERE file_id = ?", (qfid,))
            conn.execute("DELETE FROM files WHERE id = ?", (qfid,))

        conn.execute("DELETE FROM quarantine WHERE id = ?", (record_id,))
        conn.commit()
        purged += 1

    # Clean up empty directories in _duplicates/
    duplicates_dir = dest_root / "_duplicates"
    if duplicates_dir.exists():
        for dirpath in sorted(duplicates_dir.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    dirpath.rmdir()  # Only succeeds if empty
                except OSError:
                    pass  # Not empty, leave it

    print(f"Purge complete: {purged} file(s) purged")
    return {"purged": purged}


def get_quarantine_status(conn):
    """Return summary statistics about the quarantine table.

    Returns:
        dict with keys:
            total_files: total number of quarantined files,
            total_size_bytes: sum of file_size for all quarantined files,
            expired: count of files whose purge_after <= now,
            by_reason: dict mapping reason -> count.
    """
    row = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(file_size), 0) as total_size FROM quarantine"
    ).fetchone()
    total_files = row["cnt"]
    total_size_bytes = row["total_size"]

    expired_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM quarantine WHERE purge_after <= datetime('now')"
    ).fetchone()
    expired = expired_row["cnt"]

    reason_rows = conn.execute(
        "SELECT reason, COUNT(*) as cnt FROM quarantine GROUP BY reason"
    ).fetchall()
    by_reason = {r["reason"]: r["cnt"] for r in reason_rows}

    return {
        "total_files": total_files,
        "total_size_bytes": total_size_bytes,
        "expired": expired,
        "by_reason": by_reason,
    }
