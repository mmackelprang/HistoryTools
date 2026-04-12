"""
Duplicate detection for the Family Archive.

Provides three detection strategies (exact MD5, text similarity, perceptual hash),
quality scoring, and proposal file generation. This module is stateless — it reads
from the database and filesystem, runs comparisons, and returns duplicate groups.
"""

from collections import defaultdict
from pathlib import Path

import imagehash
from PIL import Image

_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".heic", ".webp"}


def _jaccard_similarity(text_a, text_b):
    """Compute token-level Jaccard similarity between two strings.

    Tokens are whitespace-split, lowercased words converted to sets.
    Returns len(intersection) / len(union), or 0.0 if either set is empty.
    """
    set_a = set(text_a.lower().split())
    set_b = set(text_b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def find_text_similar(conn, threshold=0.90, already_grouped_ids=None):
    """Find files whose transcript bodies are textually similar via Jaccard similarity.

    Args:
        conn: SQLite connection.
        threshold: Minimum Jaccard similarity to consider a match (default 0.90).
        already_grouped_ids: Optional set of file_ids to skip (e.g. already grouped
            by exact match).

    Returns a list of groups, each a dict:
        {
            "match_type": "text_similar",
            "similarity": <min pairwise sim among files in the group>,
            "files": [
                {
                    "file_id": int,
                    "path": str,
                    "filename": str,
                    "folder": str,
                    "file_type": str,
                    "size_bytes": int,
                    "date_prefix": str or None,
                    "indexed_at": str,
                },
                ...
            ]
        }
    """
    skip_ids = already_grouped_ids or set()
    provenance_relations = _get_provenance_relations(conn)

    # Load all transcript bodies joined with file metadata
    cursor = conn.execute(
        """
        SELECT f.id AS file_id, f.path, f.filename, f.folder, f.file_type,
               f.size_bytes, f.date_prefix, f.indexed_at,
               tc.body
        FROM transcripts_content tc
        JOIN files f ON f.id = tc.file_id
        WHERE tc.body IS NOT NULL AND tc.body != ''
        """
    )
    rows = cursor.fetchall()

    # Filter out already-grouped files
    candidates = [
        {
            "file_id": row["file_id"],
            "path": row["path"],
            "filename": row["filename"],
            "folder": row["folder"],
            "file_type": row["file_type"],
            "size_bytes": row["size_bytes"],
            "date_prefix": row["date_prefix"],
            "indexed_at": row["indexed_at"],
            "body": row["body"],
        }
        for row in rows
        if row["file_id"] not in skip_ids
    ]

    n = len(candidates)

    # Union-find data structure
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    # O(n^2) pairwise comparison — union matching pairs
    for i in range(n):
        for j in range(i + 1, n):
            fid_i = candidates[i]["file_id"]
            fid_j = candidates[j]["file_id"]

            # Skip provenance-related pairs
            if (fid_i, fid_j) in provenance_relations:
                continue

            sim = _jaccard_similarity(candidates[i]["body"], candidates[j]["body"])
            if sim >= threshold:
                union(i, j)

    # Collect groups by root
    groups_by_root = defaultdict(list)
    for idx in range(n):
        groups_by_root[find(idx)].append(idx)

    # Build result groups — only include roots with 2+ members
    results = []
    for root, members in groups_by_root.items():
        if len(members) < 2:
            continue

        # Compute the minimum pairwise similarity across all pairs in the group
        min_sim = 1.0
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                fid_a = candidates[members[a]]["file_id"]
                fid_b = candidates[members[b]]["file_id"]
                sim = _jaccard_similarity(
                    candidates[members[a]]["body"],
                    candidates[members[b]]["body"],
                )
                min_sim = min(min_sim, sim)

        file_entries = [
            {k: v for k, v in candidates[idx].items() if k != "body"}
            for idx in members
        ]

        results.append(
            {
                "match_type": "text_similar",
                "similarity": min_sim,
                "files": file_entries,
            }
        )

    return results


def _get_provenance_relations(conn):
    """Return a set of (file_id, file_id) tuples for provenance-related files.

    Two files are considered related if:
    - One is the parent of the other (parent_file_id relationship), or
    - Both share the same parent_file_id (siblings from the same split).

    Both orderings are included so the relation is symmetric.
    """
    relations = set()

    # Parent-child pairs: file has a parent_file_id
    cursor = conn.execute(
        "SELECT file_id, parent_file_id FROM provenance WHERE parent_file_id IS NOT NULL"
    )
    for row in cursor.fetchall():
        child_id = row["file_id"]
        parent_id = row["parent_file_id"]
        relations.add((child_id, parent_id))
        relations.add((parent_id, child_id))

    # Sibling pairs: two files sharing the same parent_file_id
    cursor = conn.execute(
        """
        SELECT a.file_id AS fid_a, b.file_id AS fid_b
        FROM provenance a
        JOIN provenance b
          ON a.parent_file_id = b.parent_file_id
         AND a.file_id < b.file_id
        WHERE a.parent_file_id IS NOT NULL
        """
    )
    for row in cursor.fetchall():
        relations.add((row["fid_a"], row["fid_b"]))
        relations.add((row["fid_b"], row["fid_a"]))

    return relations


def find_exact_duplicates(conn):
    """Find files that share the same MD5 hash, excluding provenance-related pairs.

    Returns a list of duplicate groups. Each group is a dict:
        {
            "match_type": "exact",
            "similarity": 1.0,
            "files": [
                {
                    "file_id": int,
                    "path": str,
                    "filename": str,
                    "folder": str,
                    "file_type": str,
                    "size_bytes": int,
                    "date_prefix": str or None,
                    "indexed_at": str,
                },
                ...
            ]
        }

    Files with md5_hash IS NULL are skipped. A group needs at least 2 unrelated
    files to qualify.
    """
    provenance_relations = _get_provenance_relations(conn)

    # Find MD5 hashes that appear more than once (NULL excluded by SQLite comparison)
    cursor = conn.execute(
        """
        SELECT md5_hash
        FROM files
        WHERE md5_hash IS NOT NULL
        GROUP BY md5_hash
        HAVING COUNT(*) > 1
        """
    )
    duplicate_hashes = [row["md5_hash"] for row in cursor.fetchall()]

    groups = []

    for md5 in duplicate_hashes:
        cursor = conn.execute(
            """
            SELECT id, path, filename, folder, file_type,
                   size_bytes, date_prefix, indexed_at
            FROM files
            WHERE md5_hash = ?
            """,
            (md5,),
        )
        all_files = [
            {
                "file_id": row["id"],
                "path": row["path"],
                "filename": row["filename"],
                "folder": row["folder"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"],
                "date_prefix": row["date_prefix"],
                "indexed_at": row["indexed_at"],
            }
            for row in cursor.fetchall()
        ]

        # Provenance filtering: keep a file only if it has at least one
        # unrelated file in the group.
        kept = []
        for file in all_files:
            fid = file["file_id"]
            other_ids = [f["file_id"] for f in all_files if f["file_id"] != fid]
            # Check whether this file is provenance-related to ALL others
            related_to_all = all((fid, other) in provenance_relations for other in other_ids)
            if not related_to_all:
                kept.append(file)

        if len(kept) >= 2:
            groups.append(
                {
                    "match_type": "exact",
                    "similarity": 1.0,
                    "files": kept,
                }
            )

    return groups


def compute_phash(file_path):
    """Compute a perceptual hash for an image file.

    Opens the image with PIL and computes a 64-bit perceptual hash using
    imagehash.phash().

    Args:
        file_path: Path (str or Path) to the image file.

    Returns:
        A 16-character hex string representing the hash, or None on any error.
    """
    try:
        img = Image.open(str(file_path))
        h = imagehash.phash(img)
        return str(h)
    except Exception:
        return None


def _hamming_distance(hash_a, hash_b):
    """Compute the Hamming distance between two hex hash strings.

    Converts both strings to integers, XORs them, then counts set bits.

    Args:
        hash_a: Hex string for first hash.
        hash_b: Hex string for second hash.

    Returns:
        Integer Hamming distance (number of differing bits), or 64 (maximum)
        if either hash is None or the strings have different lengths.
    """
    if hash_a is None or hash_b is None or len(hash_a) != len(hash_b):
        return 64
    xor = int(hash_a, 16) ^ int(hash_b, 16)
    return bin(xor).count("1")


def find_perceptual_duplicates(conn, dest_root, max_distance=8, already_grouped_ids=None):
    """Find photo files whose perceptual hashes are within max_distance of each other.

    For each photo in the database:
    - Checks the fingerprints table for a stored phash; computes and stores it if missing.
    - Compares all pairs by Hamming distance, skipping provenance-related pairs.
    - Uses union-find to group near-matches.

    Args:
        conn: SQLite connection.
        dest_root: Path to the archive root (used to resolve absolute file paths).
        max_distance: Maximum Hamming distance to consider a match (default 8).
        already_grouped_ids: Optional set of file_ids to skip.

    Returns:
        A list of groups, each a dict:
            {
                "match_type": "perceptual",
                "similarity": <float, rounded to 3 decimal places>,
                "files": [
                    {
                        "file_id": int,
                        "path": str,
                        "filename": str,
                        "folder": str,
                        "file_type": str,
                        "size_bytes": int,
                        "date_prefix": str or None,
                        "indexed_at": str,
                    },
                    ...
                ]
            }
    """
    skip_ids = already_grouped_ids or set()
    provenance_relations = _get_provenance_relations(conn)
    dest_root = Path(dest_root)

    # Load all photo records
    cursor = conn.execute(
        """
        SELECT id, path, filename, folder, file_type,
               size_bytes, date_prefix, indexed_at
        FROM files
        WHERE file_type = 'photo'
        """
    )
    all_photos = cursor.fetchall()

    candidates = []
    for row in all_photos:
        if row["id"] in skip_ids:
            continue
        candidates.append(
            {
                "file_id": row["id"],
                "path": row["path"],
                "filename": row["filename"],
                "folder": row["folder"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"],
                "date_prefix": row["date_prefix"],
                "indexed_at": row["indexed_at"],
            }
        )

    # Resolve phashes — check DB first, compute and store if missing
    phashes = {}
    for c in candidates:
        fid = c["file_id"]
        row = conn.execute(
            "SELECT hash_value FROM fingerprints WHERE file_id = ? AND hash_type = 'phash'",
            (fid,),
        ).fetchone()
        if row:
            phashes[fid] = row["hash_value"]
        else:
            abs_path = dest_root / c["path"]
            h = compute_phash(abs_path)
            phashes[fid] = h
            if h is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fingerprints (file_id, hash_type, hash_value, page_number)
                    VALUES (?, 'phash', ?, 1)
                    """,
                    (fid, h),
                )
    conn.commit()

    n = len(candidates)

    # Union-find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    # Track max distance within each eventual group for similarity computation
    pair_distances = {}

    for i in range(n):
        for j in range(i + 1, n):
            fid_i = candidates[i]["file_id"]
            fid_j = candidates[j]["file_id"]

            # Skip provenance-related pairs
            if (fid_i, fid_j) in provenance_relations:
                continue

            dist = _hamming_distance(phashes.get(fid_i), phashes.get(fid_j))
            if dist <= max_distance:
                union(i, j)
                key = (find(i), find(j))
                pair_distances[key] = max(pair_distances.get(key, 0), dist)

    # Collect groups by root
    groups_by_root = defaultdict(list)
    for idx in range(n):
        groups_by_root[find(idx)].append(idx)

    results = []
    for root, members in groups_by_root.items():
        if len(members) < 2:
            continue

        # Compute the maximum pairwise distance within the group
        max_dist_in_group = 0
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                fid_a = candidates[members[a]]["file_id"]
                fid_b = candidates[members[b]]["file_id"]
                dist = _hamming_distance(phashes.get(fid_a), phashes.get(fid_b))
                max_dist_in_group = max(max_dist_in_group, dist)

        similarity = round(1.0 - (max_dist_in_group / 64.0), 3)
        file_entries = [
            {k: v for k, v in candidates[idx].items()}
            for idx in members
        ]

        results.append(
            {
                "match_type": "perceptual",
                "similarity": similarity,
                "files": file_entries,
            }
        )

    return results
