"""
Duplicate detection for the Family Archive.

Provides three detection strategies (exact MD5, text similarity, perceptual hash),
quality scoring, and proposal file generation. This module is stateless — it reads
from the database and filesystem, runs comparisons, and returns duplicate groups.
"""

from collections import defaultdict
from pathlib import Path


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
