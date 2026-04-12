"""
Tests for the duplicate detection module (scripts/duplicate_detect.py).
"""

import json
from pathlib import Path
import pytest
from scripts.db import get_db, close_db, index_file, index_transcript
from scripts.duplicate_detect import (
    find_exact_duplicates,
    find_text_similar,
    compute_phash,
    find_perceptual_duplicates,
    score_quality,
    generate_proposals,
    scan_duplicates,
    check_ingest_duplicates,
)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


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


def make_file(path: Path, content: str = "test content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestExactDuplicates:

    def test_no_duplicates(self, tmp_path):
        """Two files with different content produce no duplicate groups."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "file_a.txt", "content alpha")
        make_file(dest / "folder_b" / "file_b.txt", "content beta")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "file_a.txt")
        index_file(conn, dest, dest / "folder_b" / "file_b.txt")

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert groups == []

    def test_finds_exact_duplicates(self, tmp_path):
        """Two files with identical content produce one group with two entries."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "copy1.txt", "identical content")
        make_file(dest / "folder_b" / "copy2.txt", "identical content")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "copy1.txt")
        index_file(conn, dest, dest / "folder_b" / "copy2.txt")

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert len(groups) == 1
        assert len(groups[0]["files"]) == 2

    def test_group_has_correct_fields(self, tmp_path):
        """Group dict has match_type, similarity, and files with all required fields."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "doc1.txt", "shared content")
        make_file(dest / "folder_b" / "doc2.txt", "shared content")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "doc1.txt")
        index_file(conn, dest, dest / "folder_b" / "doc2.txt")

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert len(groups) == 1
        group = groups[0]

        assert group["match_type"] == "exact"
        assert group["similarity"] == 1.0
        assert "files" in group

        required_fields = {"file_id", "path", "filename", "folder", "file_type",
                           "size_bytes", "date_prefix", "indexed_at"}
        for file_entry in group["files"]:
            assert required_fields == set(file_entry.keys())

    def test_excludes_provenance_siblings(self, tmp_path):
        """Parent + two children with same content are excluded via provenance."""
        dest = tmp_path / "archive"
        dest.mkdir()

        # All three have identical content so they share an MD5
        shared = "same bytes for all"
        parent_path = make_file(dest / "Docs" / "parent.pdf", shared)
        child1_path = make_file(dest / "Docs" / "child1.pdf", shared)
        child2_path = make_file(dest / "Docs" / "child2.pdf", shared)

        conn = get_db(dest)
        parent_id = index_file(conn, dest, parent_path)
        child1_id = index_file(conn, dest, child1_path)
        child2_id = index_file(conn, dest, child2_path)

        # Record both children as splits from the parent
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation, detail) VALUES (?, ?, ?, ?)",
            (child1_id, parent_id, "split", "page 1"),
        )
        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation, detail) VALUES (?, ?, ?, ?)",
            (child2_id, parent_id, "split", "page 2"),
        )
        conn.commit()

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert groups == []

    def test_multiple_duplicate_groups(self, tmp_path):
        """Two pairs of duplicates plus one unique file yields exactly two groups."""
        dest = tmp_path / "archive"
        dest.mkdir()

        # Pair A
        make_file(dest / "folder_a" / "a1.txt", "content group A")
        make_file(dest / "folder_b" / "a2.txt", "content group A")
        # Pair B
        make_file(dest / "folder_a" / "b1.txt", "content group B")
        make_file(dest / "folder_b" / "b2.txt", "content group B")
        # Unique
        make_file(dest / "folder_c" / "unique.txt", "unique content nobody else has")

        conn = get_db(dest)
        for name, folder in [
            ("a1.txt", "folder_a"), ("a2.txt", "folder_b"),
            ("b1.txt", "folder_a"), ("b2.txt", "folder_b"),
            ("unique.txt", "folder_c"),
        ]:
            index_file(conn, dest, dest / folder / name)

        groups = find_exact_duplicates(conn)
        close_db(conn)

        assert len(groups) == 2
        for group in groups:
            assert len(group["files"]) == 2


class TestTextSimilarity:

    def _setup_archive(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        return dest

    def test_identical_text_detected(self, tmp_path):
        """Two transcripts with identical bodies produce one group with similarity >= 0.90."""
        dest = self._setup_archive(tmp_path)

        pdf_a = make_file(dest / "folder_a" / "letter.pdf", "dummy")
        pdf_b = make_file(dest / "folder_b" / "letter-copy.pdf", "dummy copy")
        t_a = make_file(dest / "folder_a" / "letter.pdf.transcript.md", TRANSCRIPT_A)
        t_b = make_file(dest / "folder_b" / "letter-copy.pdf.transcript.md", TRANSCRIPT_B_SIMILAR)

        conn = get_db(dest)
        index_file(conn, dest, pdf_a)
        index_file(conn, dest, pdf_b)
        index_transcript(conn, dest, t_a)
        index_transcript(conn, dest, t_b)

        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)

        assert len(groups) == 1
        assert groups[0]["match_type"] == "text_similar"
        assert groups[0]["similarity"] >= 0.90

    def test_different_text_not_detected(self, tmp_path):
        """Two transcripts with different bodies produce no groups at threshold 0.90."""
        dest = self._setup_archive(tmp_path)

        pdf_a = make_file(dest / "folder_a" / "letter.pdf", "dummy")
        pdf_c = make_file(dest / "folder_b" / "note.pdf", "dummy note")
        t_a = make_file(dest / "folder_a" / "letter.pdf.transcript.md", TRANSCRIPT_A)
        t_c = make_file(dest / "folder_b" / "note.pdf.transcript.md", TRANSCRIPT_C_DIFFERENT)

        conn = get_db(dest)
        index_file(conn, dest, pdf_a)
        index_file(conn, dest, pdf_c)
        index_transcript(conn, dest, t_a)
        index_transcript(conn, dest, t_c)

        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)

        assert groups == []

    def test_excludes_provenance_siblings(self, tmp_path):
        """Two identical transcripts whose files are provenance siblings produce no groups."""
        dest = self._setup_archive(tmp_path)

        parent_pdf = make_file(dest / "Docs" / "parent.pdf", "original")
        t_parent = make_file(dest / "Docs" / "parent.pdf.transcript.md", TRANSCRIPT_A)
        t_child = make_file(dest / "Docs" / "child.pdf.transcript.md", TRANSCRIPT_B_SIMILAR)

        conn = get_db(dest)
        parent_id = index_file(conn, dest, parent_pdf)
        index_transcript(conn, dest, t_parent)
        index_transcript(conn, dest, t_child)

        # The transcripts_content rows are keyed by the transcript file's file_id,
        # so provenance must be recorded between the transcript file_ids.
        t_parent_id = conn.execute(
            "SELECT id FROM files WHERE path = ?",
            ("Docs/parent.pdf.transcript.md",),
        ).fetchone()["id"]
        t_child_id = conn.execute(
            "SELECT id FROM files WHERE path = ?",
            ("Docs/child.pdf.transcript.md",),
        ).fetchone()["id"]

        conn.execute(
            "INSERT INTO provenance (file_id, parent_file_id, operation, detail) VALUES (?, ?, ?, ?)",
            (t_child_id, t_parent_id, "split", "page 1"),
        )
        conn.commit()

        groups = find_text_similar(conn, threshold=0.90)
        close_db(conn)

        assert groups == []

    def test_custom_threshold(self, tmp_path):
        """Two transcripts with any word overlap match at a very low threshold."""
        dest = self._setup_archive(tmp_path)

        pdf_a = make_file(dest / "folder_a" / "letter.pdf", "dummy")
        pdf_c = make_file(dest / "folder_b" / "note.pdf", "dummy note")
        t_a = make_file(dest / "folder_a" / "letter.pdf.transcript.md", TRANSCRIPT_A)
        t_c = make_file(dest / "folder_b" / "note.pdf.transcript.md", TRANSCRIPT_C_DIFFERENT)

        conn = get_db(dest)
        index_file(conn, dest, pdf_a)
        index_file(conn, dest, pdf_c)
        index_transcript(conn, dest, t_a)
        index_transcript(conn, dest, t_c)

        groups = find_text_similar(conn, threshold=0.01)
        close_db(conn)

        assert len(groups) == 1
        assert groups[0]["match_type"] == "text_similar"


def make_test_image(path, color=(255, 0, 0), size=(100, 100)):
    """Create a simple test image."""
    img = Image.new("RGB", size, color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))
    return path


def make_checkerboard_image(path, size=(100, 100)):
    """Create a fine checkerboard image — perceptually distinct from solid-color images."""
    img = Image.new("RGB", size, (0, 0, 0))
    for y in range(size[1]):
        for x in range(size[0]):
            if (x + y) % 2 == 0:
                img.putpixel((x, y), (255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))
    return path


@pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
class TestPerceptualHash:

    def test_compute_phash_returns_string(self, tmp_path):
        """compute_phash returns a hex string of length 16 for a valid image."""
        img_path = make_test_image(tmp_path / "test.png", color=(255, 0, 0))
        result = compute_phash(img_path)
        assert isinstance(result, str)
        assert len(result) == 16

    def test_identical_images_same_hash(self, tmp_path):
        """Two images with the same color produce the same perceptual hash."""
        img_a = make_test_image(tmp_path / "a.png", color=(128, 64, 32))
        img_b = make_test_image(tmp_path / "b.png", color=(128, 64, 32))
        assert compute_phash(img_a) == compute_phash(img_b)

    def test_different_images_different_hash(self, tmp_path):
        """A checkerboard and a solid black image produce different perceptual hashes."""
        checker = make_checkerboard_image(tmp_path / "checker.png")
        solid = make_test_image(tmp_path / "solid.png", color=(0, 0, 0))
        assert compute_phash(checker) != compute_phash(solid)

    def test_finds_perceptual_duplicates(self, tmp_path):
        """Two identical images indexed as photos produce one group with match_type='perceptual'."""
        dest = tmp_path / "archive"
        dest.mkdir()

        img_a = make_test_image(dest / "folder_a" / "photo1.png", color=(200, 150, 100))
        img_b = make_test_image(dest / "folder_b" / "photo2.png", color=(200, 150, 100))

        conn = get_db(dest)
        index_file(conn, dest, img_a)
        index_file(conn, dest, img_b)

        groups = find_perceptual_duplicates(conn, dest)
        close_db(conn)

        assert len(groups) == 1
        assert groups[0]["match_type"] == "perceptual"
        assert len(groups[0]["files"]) == 2

    def test_different_images_not_grouped(self, tmp_path):
        """A checkerboard and a solid black image are not grouped (Hamming distance > 8)."""
        dest = tmp_path / "archive"
        dest.mkdir()

        checker = make_checkerboard_image(dest / "folder_a" / "checker.png")
        solid = make_test_image(dest / "folder_b" / "solid.png", color=(0, 0, 0))

        conn = get_db(dest)
        index_file(conn, dest, checker)
        index_file(conn, dest, solid)

        groups = find_perceptual_duplicates(conn, dest, max_distance=8)
        close_db(conn)

        assert groups == []

    def test_stores_fingerprint_in_db(self, tmp_path):
        """After running detection, a fingerprint row exists in the DB for each photo."""
        dest = tmp_path / "archive"
        dest.mkdir()

        img = make_test_image(dest / "folder_a" / "photo.png", color=(100, 200, 50))

        conn = get_db(dest)
        file_id = index_file(conn, dest, img)

        find_perceptual_duplicates(conn, dest)

        row = conn.execute(
            "SELECT hash_value FROM fingerprints WHERE file_id = ? AND hash_type = 'phash'",
            (file_id,),
        ).fetchone()
        close_db(conn)

        assert row is not None
        assert isinstance(row["hash_value"], str)
        assert len(row["hash_value"]) == 16


class TestQualityScoring:

    def test_higher_confidence_scores_higher(self):
        """A high-confidence file is sorted before a low-confidence file."""
        files = [
            {"size_bytes": 100, "word_count": 10, "confidence": "low", "indexed_at": "2024-01-01"},
            {"size_bytes": 100, "word_count": 10, "confidence": "high", "indexed_at": "2024-01-01"},
        ]
        result = score_quality(files)
        assert result[0]["confidence"] == "high"

    def test_higher_word_count_scores_higher(self):
        """When confidence is equal, a higher word_count wins."""
        files = [
            {"size_bytes": 100, "word_count": 5, "confidence": "medium", "indexed_at": "2024-01-01"},
            {"size_bytes": 100, "word_count": 50, "confidence": "medium", "indexed_at": "2024-01-01"},
        ]
        result = score_quality(files)
        assert result[0]["word_count"] == 50

    def test_earlier_ingested_breaks_tie(self):
        """When quality scores are identical, earlier indexed_at wins."""
        files = [
            {"size_bytes": 100, "word_count": 10, "confidence": "high", "indexed_at": "2024-06-01"},
            {"size_bytes": 100, "word_count": 10, "confidence": "high", "indexed_at": "2024-01-01"},
        ]
        result = score_quality(files)
        assert result[0]["indexed_at"] == "2024-01-01"


class TestProposalGeneration:

    def _make_group(self):
        return {
            "match_type": "exact",
            "similarity": 1.0,
            "files": [
                {
                    "file_id": 1,
                    "path": "folder_a/doc.txt",
                    "size_bytes": 200,
                    "word_count": 20,
                    "confidence": "high",
                    "indexed_at": "2024-01-01T00:00:00",
                },
                {
                    "file_id": 2,
                    "path": "folder_b/doc.txt",
                    "size_bytes": 200,
                    "word_count": 20,
                    "confidence": "low",
                    "indexed_at": "2024-06-01T00:00:00",
                },
            ],
        }

    def test_generate_proposals_creates_files(self, tmp_path):
        """generate_proposals writes both JSON and Markdown files."""
        groups = [self._make_group()]
        generate_proposals(groups, tmp_path)
        assert (tmp_path / "_duplicate-proposals.json").exists()
        assert (tmp_path / "_duplicate-proposals.md").exists()

    def test_proposals_json_structure(self, tmp_path):
        """The generated JSON has generated, groups, and each group has id, keep, approved, files."""
        groups = [self._make_group()]
        generate_proposals(groups, tmp_path)
        data = json.loads((tmp_path / "_duplicate-proposals.json").read_text(encoding="utf-8"))
        assert "generated" in data
        assert "groups" in data
        assert len(data["groups"]) == 1
        group = data["groups"][0]
        assert "id" in group
        assert "keep" in group
        assert "approved" in group
        assert "files" in group
        assert len(group["files"]) == 2


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
        make_file(
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
        result = apply_single_split(pdf_path, dest / "Letters" / "compilation.transcript.md", segment, dest)
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


class TestScanDuplicates:

    def test_scan_runs_all_strategies(self, tmp_path):
        """Two files with identical content produce at least one duplicate group."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "copy1.txt", "identical content here")
        make_file(dest / "folder_b" / "copy2.txt", "identical content here")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "copy1.txt")
        index_file(conn, dest, dest / "folder_b" / "copy2.txt")

        groups = scan_duplicates(conn, dest)
        close_db(conn)

        assert len(groups) >= 1

    def test_scan_no_duplicates(self, tmp_path):
        """Two completely unique files return no groups."""
        dest = tmp_path / "archive"
        dest.mkdir()

        make_file(dest / "folder_a" / "alpha.txt", "unique content alpha 12345")
        make_file(dest / "folder_b" / "beta.txt", "unique content beta 67890")

        conn = get_db(dest)
        index_file(conn, dest, dest / "folder_a" / "alpha.txt")
        index_file(conn, dest, dest / "folder_b" / "beta.txt")

        groups = scan_duplicates(conn, dest)
        close_db(conn)

        assert groups == []


class TestIngestProvenance:

    def test_source_hash_in_provenance_detected(self, tmp_path):
        """A file indexed with a provenance source_hash is detected as a duplicate."""
        dest = tmp_path / "archive"
        dest.mkdir()

        file_path = make_file(dest / "folder_a" / "original.txt", "source content abc")

        conn = get_db(dest)
        file_id = index_file(conn, dest, file_path)

        source_hash = "aabbccddeeff0011"
        conn.execute(
            "INSERT INTO provenance (file_id, source_hash, operation, detail) VALUES (?, ?, ?, ?)",
            (file_id, source_hash, "ingest", "test"),
        )
        conn.commit()

        result = check_ingest_duplicates(conn, source_hash)
        close_db(conn)

        assert result is not None
        assert result["path"] == "folder_a/original.txt"

    def test_unknown_hash_not_detected(self, tmp_path):
        """A hash that does not exist in provenance or files returns None."""
        dest = tmp_path / "archive"
        dest.mkdir()

        conn = get_db(dest)
        result = check_ingest_duplicates(conn, "deadbeefdeadbeef")
        close_db(conn)

        assert result is None


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
        assert (dest / "_duplicate-proposals.md").exists()

        # Apply quarantine
        result = apply_quarantine(conn, dest)
        assert result["quarantined"] == 1

        # Check status
        status = get_quarantine_status(conn)
        assert status["total_files"] == 1

        # Force purge by backdating TTL
        conn.execute("UPDATE quarantine SET purge_after = datetime('now', '-1 day')")
        conn.commit()
        purge_result = purge_expired(conn, dest)
        assert purge_result["purged"] == 1

        # Status should be empty
        status = get_quarantine_status(conn)
        assert status["total_files"] == 0

        close_db(conn)
