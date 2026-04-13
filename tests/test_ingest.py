"""
Tests for ingest.py pure-logic functions.

All tests are offline (no API calls) and use tmp_path for filesystem work.
"""

import sys
import zipfile
import io
from pathlib import Path

import pytest

# Ensure familyarchive/ is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "familyarchive"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ingest import (
    get_file_type,
    classify_file,
    classify_by_folder_hints,
    classify_by_filename,
    classify_by_type_default,
    parse_date_from_filename,
    make_slug,
    _safe_file_size,
    _safe_extract_zip,
    extract_zips_recursive,
    prepare_source,
    scan_source,
    get_processing_pipeline,
)

from pathlib import Path as _Path
import zipfile as _zipfile


def make_file(path, content="test content"):
    """Create a file with given content, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_zip(zip_path, members):
    """Create a ZIP file. members is {arcname: content_string}."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with _zipfile.ZipFile(str(zip_path), "w") as z:
        for arcname, content in members.items():
            if content is None:
                continue  # skip directory entries
            z.writestr(arcname, content)
    return zip_path


# ── get_file_type() ───────────────────────────────────────────────────────────

class TestGetFileType:
    def test_pdf_is_document(self):
        assert get_file_type(".pdf") == "document"

    def test_mp3_is_audio(self):
        assert get_file_type(".mp3") == "audio"

    def test_jpg_is_photo(self):
        assert get_file_type(".jpg") == "photo"

    def test_mp4_is_video(self):
        assert get_file_type(".mp4") == "video"

    def test_xlsx_is_spreadsheet(self):
        assert get_file_type(".xlsx") == "spreadsheet"

    def test_eml_is_email(self):
        assert get_file_type(".eml") == "email"

    def test_gedcom_is_genealogy(self):
        assert get_file_type(".gedcom") == "genealogy"

    def test_unknown_extension_returns_unknown(self):
        assert get_file_type(".xyz") == "unknown"

    def test_uppercase_zip_extension_is_unknown(self):
        # .ZIP is not in any known set — extension is lowercased inside but .zip not in type sets
        assert get_file_type(".ZIP") == "unknown"

    def test_empty_extension_returns_unknown(self):
        assert get_file_type("") == "unknown"

    def test_wav_is_audio(self):
        assert get_file_type(".wav") == "audio"

    def test_docx_is_document(self):
        assert get_file_type(".docx") == "document"

    def test_csv_is_spreadsheet(self):
        assert get_file_type(".csv") == "spreadsheet"

    def test_ged_is_genealogy(self):
        assert get_file_type(".ged") == "genealogy"

    def test_heic_is_photo(self):
        assert get_file_type(".heic") == "photo"

    def test_mov_is_video(self):
        assert get_file_type(".mov") == "video"


# ── classify_file() ───────────────────────────────────────────────────────────

class TestClassifyFile:
    def test_file_in_letters_folder_goes_to_correspondence_letters(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        letters_dir = source_root / "Letters"
        letters_dir.mkdir()
        f = letters_dir / "note.pdf"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "Correspondence/Letters"

    def test_file_in_medical_records_folder_goes_to_medical(self, tmp_path):
        source_root = tmp_path / "source"
        (source_root / "Medical Records").mkdir(parents=True)
        f = source_root / "Medical Records" / "report.pdf"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "Medical"

    def test_spreadsheet_always_goes_to_needs_review(self, tmp_path):
        source_root = tmp_path / "source"
        letters_dir = source_root / "Letters"
        letters_dir.mkdir(parents=True)
        f = letters_dir / "budget.xlsx"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "NeedsReview"

    def test_unknown_extension_goes_to_unprocessed(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "mystery.xyz"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "Unprocessed"

    def test_file_with_journal_in_name_goes_to_journals(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "personal_journal_1985.pdf"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "Journals"

    def test_plain_document_with_no_hints_goes_to_needs_review(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "scan001.pdf"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "NeedsReview"

    def test_photo_file_classified_as_media_photos_by_type(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "family.jpg"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "Media/Photos"

    def test_audio_file_classified_as_media_audio(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "recording.mp3"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "Media/Audio/FamilyRecordings"

    def test_email_file_goes_to_imports(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "message.eml"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "_imports/EmailArchives"

    def test_genealogy_file_goes_to_imports(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "family_tree.gedcom"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert dest == "_imports"

    def test_confidence_is_high_for_folder_hint(self, tmp_path):
        source_root = tmp_path / "source"
        (source_root / "Letters").mkdir(parents=True)
        f = source_root / "Letters" / "note.pdf"
        f.touch()

        dest, src, conf = classify_file(f, source_root)
        assert conf == "high"

    def test_confidence_is_low_for_spreadsheet(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "data.xlsx"
        f.touch()

        _, _, conf = classify_file(f, source_root)
        assert conf == "low"


# ── classify_by_folder_hints() ────────────────────────────────────────────────

class TestClassifyByFolderHints:
    def test_letters_from_mom_folder_returns_correspondence_letters(self, tmp_path):
        source_root = tmp_path / "source"
        folder = source_root / "Letters from Mom"
        folder.mkdir(parents=True)
        f = folder / "note.pdf"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest == "Correspondence/Letters"

    def test_old_photos_folder_returns_media_photos(self, tmp_path):
        source_root = tmp_path / "source"
        folder = source_root / "Old Photos"
        folder.mkdir(parents=True)
        f = folder / "family.jpg"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest == "Media/Photos"

    def test_tax_returns_folder_returns_financial_taxes_case_insensitive(self, tmp_path):
        source_root = tmp_path / "source"
        folder = source_root / "tax returns"
        folder.mkdir(parents=True)
        f = folder / "2020.pdf"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest == "Financial/Taxes"

    def test_no_matching_folder_returns_none(self, tmp_path):
        source_root = tmp_path / "source"
        folder = source_root / "RandomStuff"
        folder.mkdir(parents=True)
        f = folder / "file.pdf"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest is None

    def test_file_directly_in_source_root_returns_none(self, tmp_path):
        source_root = tmp_path / "source"
        source_root.mkdir()
        f = source_root / "file.pdf"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest is None

    def test_nested_folder_with_hint_is_detected(self, tmp_path):
        source_root = tmp_path / "source"
        folder = source_root / "Family" / "Journals"
        folder.mkdir(parents=True)
        f = folder / "diary.pdf"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest == "Journals"

    def test_cassette_folder_returns_cassette_tapes(self, tmp_path):
        source_root = tmp_path / "source"
        folder = source_root / "cassette tapes"
        folder.mkdir(parents=True)
        f = folder / "tape01.mp3"

        dest, source = classify_by_folder_hints(f, source_root)
        assert dest == "Media/Audio/CassetteTapes"


# ── parse_date_from_filename() ────────────────────────────────────────────────

class TestParseDateFromFilename:
    def test_yyyymmdd_inline_returns_date(self):
        assert parse_date_from_filename("Letter 19830603.pdf") == "1983-06-03"

    def test_mmddyyyy_prefix_returns_date(self):
        assert parse_date_from_filename("02222023_scan.pdf") == "2023-02-22"

    def test_scanner_timestamp_format_returns_date(self):
        assert parse_date_from_filename("2015_09_20_21_44_33.pdf") == "2015-09-20"

    def test_month_name_and_year_returns_partial_date(self):
        assert parse_date_from_filename("Something Jan 2021.pdf") == "2021-01-00"

    def test_no_date_returns_undated(self):
        assert parse_date_from_filename("no date here.pdf") == "undated"

    def test_just_a_year_returns_year_only(self):
        assert parse_date_from_filename("photo_1975.jpg") == "1975-00-00"

    def test_future_date_past_2030_is_rejected(self):
        # YYYYMMDD with year 2035 — outside allowed range
        result = parse_date_from_filename("20351201.pdf")
        # Should not parse as a valid YYYYMMDD date; falls through to year search
        # 2035 > 2030 so the year search also rejects it
        assert result == "undated"

    def test_invalid_month_in_yyyymmdd_is_rejected(self):
        # Month 13 is invalid, should fall through
        result = parse_date_from_filename("19831399.pdf")
        # 1983-13-99: month 13 fails check, year search finds 1983
        assert result == "1983-00-00"

    def test_december_abbreviation_parsed(self):
        assert parse_date_from_filename("Report Dec 1999.pdf") == "1999-12-00"

    def test_yyyymmdd_at_start_of_stem(self):
        assert parse_date_from_filename("19500101_letter.pdf") == "1950-01-01"

    def test_scan_timestamp_year_range_2000_to_2030(self):
        # Scanner timestamp pattern only triggers for 2000-2030
        # For 1985, the scanner-timestamp regex does not match (year < 2000)
        # No 8-contiguous-digit YYYYMMDD exists in "1985_09_20_10_30_00"
        # so the year-only fallback fires: "1985-00-00"
        result = parse_date_from_filename("1985_09_20_10_30_00.pdf")
        assert result == "1985-00-00"

    def test_mmddyyyy_invalid_month_zero_rejected(self):
        # Month 0 is rejected by MMDDYYYY pattern (requires 1<=mo<=12)
        result = parse_date_from_filename("00012000_scan.pdf")
        # month=0 fails, falls through to year extraction
        assert result == "2000-00-00"


# ── make_slug() ───────────────────────────────────────────────────────────────

class TestMakeSlug:
    def test_removes_yyyymmdd_date_prefix(self):
        result = make_slug("19830603_letter-hope-mark.pdf")
        assert result == "letter-hope-mark"

    def test_removes_yyyy_mm_dd_date_prefix(self):
        result = make_slug("1983-06-03_letter.pdf")
        assert result == "letter"

    def test_slugifies_spaces_and_mixed_case(self):
        result = make_slug("Letter 19830603 Hope - Mark.pdf")
        # make_slug strips date prefixes but embedded dates remain as part of the slug
        assert result == "letter-19830603-hope-mark"

    def test_scan_number_filename_stays_as_slug(self):
        result = make_slug("scan001.pdf")
        assert result == "scan001"

    def test_already_slugified_stays_unchanged(self):
        result = make_slug("my-file-name.pdf")
        assert result == "my-file-name"

    def test_removes_scanner_timestamp_prefix(self):
        # The YYYY-MM-DD prefix regex fires first, stripping "2015_09_20_"
        # leaving "21_44_33_family", then the 8-digit and timestamp regexes
        # don't match the remainder — so the slug is built from "21_44_33_family"
        result = make_slug("2015_09_20_21_44_33_family.pdf")
        assert result == "21-44-33-family"

    def test_special_characters_replaced_with_hyphens(self):
        result = make_slug("Hello, World! (test).pdf")
        assert result == "hello-world-test"

    def test_empty_stem_after_date_removal_returns_unnamed(self):
        result = make_slug("19830603.pdf")
        assert result == "unnamed"

    def test_leading_trailing_hyphens_stripped(self):
        result = make_slug("  --hello--  .pdf")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_uppercase_converted_to_lowercase(self):
        result = make_slug("FAMILY.pdf")
        assert result == "family"


# ── get_processing_pipeline() ─────────────────────────────────────────────────

class TestGetProcessingPipeline:
    def test_document_in_letters_gets_full_pipeline(self):
        pipeline = get_processing_pipeline("document", "Correspondence/Letters")
        assert pipeline == ["copy", "transcribe", "format", "rename", "detect_date"]

    def test_document_in_journals_gets_full_pipeline(self):
        pipeline = get_processing_pipeline("document", "Journals")
        assert pipeline == ["copy", "transcribe", "format", "rename", "detect_date"]

    def test_audio_in_audio_folder_gets_audio_pipeline(self):
        pipeline = get_processing_pipeline("audio", "Media/Audio/FamilyRecordings")
        assert pipeline == ["copy", "transcribe_audio", "format", "rename"]

    def test_audio_in_cassette_tapes_gets_audio_pipeline(self):
        pipeline = get_processing_pipeline("audio", "Media/Audio/CassetteTapes")
        assert pipeline == ["copy", "transcribe_audio", "format", "rename"]

    def test_photo_gets_catalog_pipeline(self):
        pipeline = get_processing_pipeline("photo", "Media/Photos")
        assert pipeline == ["copy", "catalog_photos"]

    def test_spreadsheet_in_needs_review_gets_copy_only(self):
        pipeline = get_processing_pipeline("spreadsheet", "NeedsReview")
        assert pipeline == ["copy"]

    def test_unknown_in_unprocessed_gets_copy_only(self):
        pipeline = get_processing_pipeline("unknown", "Unprocessed")
        assert pipeline == ["copy"]

    def test_document_in_needs_review_gets_copy_only(self):
        pipeline = get_processing_pipeline("document", "NeedsReview")
        assert pipeline == ["copy"]

    def test_document_in_unprocessed_gets_copy_only(self):
        pipeline = get_processing_pipeline("document", "Unprocessed")
        assert pipeline == ["copy"]

    def test_video_gets_copy_only(self):
        pipeline = get_processing_pipeline("video", "Media/Video")
        assert pipeline == ["copy"]

    def test_email_gets_copy_only(self):
        pipeline = get_processing_pipeline("email", "_imports/EmailArchives")
        assert pipeline == ["copy"]

    def test_pipeline_always_starts_with_copy(self):
        for file_type in ("document", "audio", "photo", "video", "email", "spreadsheet", "unknown"):
            pipeline = get_processing_pipeline(file_type, "SomeFolder")
            assert pipeline[0] == "copy", f"Expected 'copy' first for {file_type}"


# ── _safe_file_size() ─────────────────────────────────────────────────────────

class TestSafeFileSize:
    def test_returns_correct_size_for_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        assert _safe_file_size(f) == 11

    def test_returns_zero_for_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.txt"
        assert _safe_file_size(f) == 0


# ── _safe_extract_zip() ───────────────────────────────────────────────────────

class TestSafeExtractZip:
    def test_extracts_normal_zip(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        make_zip(zip_path, {"hello.txt": "hello world", "subdir/file.txt": "nested"})
        extract_dir = tmp_path / "extracted"

        _safe_extract_zip(zip_path, extract_dir)

        assert (extract_dir / "hello.txt").exists()
        assert (extract_dir / "subdir" / "file.txt").exists()

    def test_blocks_path_traversal_entries(self, tmp_path, capsys):
        """ZIP with a path-traversal entry (../../evil.txt) should be skipped."""
        zip_path = tmp_path / "evil.zip"
        # Manually build a ZIP with a traversal entry
        with zipfile.ZipFile(str(zip_path), "w") as z:
            z.writestr("safe.txt", "safe content")
            z.writestr("../../evil.txt", "evil content")

        extract_dir = tmp_path / "extracted"
        _safe_extract_zip(zip_path, extract_dir)

        assert (extract_dir / "safe.txt").exists()
        # The evil file must NOT exist anywhere under extract_dir
        evil_files = list(extract_dir.rglob("evil.txt"))
        assert evil_files == [], f"Path traversal file was extracted: {evil_files}"

        captured = capsys.readouterr()
        # The function should print a warning about the suspicious entry
        assert "WARNING" in captured.out or "path traversal" in captured.out.lower()

    def test_creates_extraction_directory_if_missing(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        make_zip(zip_path, {"file.txt": "content"})
        extract_dir = tmp_path / "new_dir" / "deep"

        _safe_extract_zip(zip_path, extract_dir)
        assert (extract_dir / "file.txt").exists()

    def test_extracts_file_content_correctly(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        make_zip(zip_path, {"data.txt": "the content here"})
        extract_dir = tmp_path / "extracted"

        _safe_extract_zip(zip_path, extract_dir)
        assert (extract_dir / "data.txt").read_text() == "the content here"


# ── extract_zips_recursive() ──────────────────────────────────────────────────

class TestExtractZipsRecursive:
    def test_extracts_single_zip(self, tmp_path):
        inner_zip = tmp_path / "archive.zip"
        make_zip(inner_zip, {"letter.txt": "Dear Mark"})

        count = extract_zips_recursive(tmp_path)
        assert count == 1
        assert (tmp_path / "_extracted_archive" / "letter.txt").exists()

    def test_handles_nested_zip(self, tmp_path):
        # Create inner ZIP in memory
        inner_buf = io.BytesIO()
        with zipfile.ZipFile(inner_buf, "w") as iz:
            iz.writestr("deep.txt", "deep content")
        inner_bytes = inner_buf.getvalue()

        # Outer ZIP contains the inner ZIP
        outer_zip = tmp_path / "outer.zip"
        with zipfile.ZipFile(str(outer_zip), "w") as oz:
            oz.writestr("inner.zip", inner_bytes)
            oz.writestr("top.txt", "top level")

        count = extract_zips_recursive(tmp_path)
        assert count >= 2  # outer + inner
        assert (tmp_path / "_extracted_outer" / "top.txt").exists()

    def test_respects_max_depth(self, tmp_path, capsys):
        """At max_depth=0, no ZIPs should be extracted."""
        inner_zip = tmp_path / "archive.zip"
        make_zip(inner_zip, {"file.txt": "content"})

        count = extract_zips_recursive(tmp_path, depth=0, max_depth=0)
        assert count == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_skips_already_extracted_directories(self, tmp_path):
        inner_zip = tmp_path / "archive.zip"
        make_zip(inner_zip, {"file.txt": "content"})

        # Pre-create the extraction dir so it looks already done
        already = tmp_path / "_extracted_archive"
        already.mkdir()

        count = extract_zips_recursive(tmp_path)
        assert count == 0

    def test_returns_zero_when_no_zips(self, tmp_path):
        (tmp_path / "plain.txt").write_text("hello")
        count = extract_zips_recursive(tmp_path)
        assert count == 0

    def test_handles_bad_zip_gracefully(self, tmp_path, capsys):
        bad_zip = tmp_path / "corrupt.zip"
        bad_zip.write_text("this is not a zip file")

        count = extract_zips_recursive(tmp_path)
        assert count == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out


# ── prepare_source() ──────────────────────────────────────────────────────────

class TestPrepareSource:
    def test_zip_file_source_creates_temp_dir(self, tmp_path):
        zip_path = tmp_path / "source.zip"
        make_zip(zip_path, {"letter.pdf": "pdf content"})

        effective, temp_dir = prepare_source(zip_path)
        try:
            assert temp_dir is not None
            assert effective.is_dir()
            assert (effective / "letter.pdf").exists()
        finally:
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_directory_without_zips_returns_no_temp_dir(self, tmp_path):
        source = tmp_path / "plain_source"
        source.mkdir()
        (source / "letter.pdf").write_text("content")

        effective, temp_dir = prepare_source(source)
        try:
            assert temp_dir is None
            assert effective == source
        finally:
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_directory_with_zips_creates_temp_dir_and_leaves_source_unchanged(self, tmp_path):
        source = tmp_path / "source_with_zip"
        source.mkdir()
        make_zip(source / "archive.zip", {"buried.txt": "content"})
        (source / "plain.txt").write_text("plain")

        effective, temp_dir = prepare_source(source)
        try:
            assert temp_dir is not None
            # Original source untouched
            assert (source / "archive.zip").exists()
            assert (source / "plain.txt").exists()
            # Effective dir is in temp
            assert effective.is_dir()
            assert effective != source
        finally:
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_zip_source_nested_contents_accessible(self, tmp_path):
        zip_path = tmp_path / "nested.zip"
        make_zip(zip_path, {
            "subdir/photo.jpg": "jpg content",
            "subdir/letter.pdf": "pdf content",
        })

        effective, temp_dir = prepare_source(zip_path)
        try:
            assert (effective / "subdir" / "photo.jpg").exists()
            assert (effective / "subdir" / "letter.pdf").exists()
        finally:
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_temp_base_creates_dir_under_specified_path(self, tmp_path):
        zip_path = tmp_path / "source.zip"
        make_zip(zip_path, {"doc.pdf": "pdf content"})
        custom_base = tmp_path / "my_output"
        custom_base.mkdir()

        effective, temp_dir = prepare_source(zip_path, temp_base=str(custom_base))
        try:
            assert temp_dir is not None
            assert "_historytools_temp" in temp_dir
            assert str(custom_base) in temp_dir
            assert (effective / "doc.pdf").exists()
        finally:
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def test_temp_base_none_uses_system_default(self, tmp_path):
        zip_path = tmp_path / "source.zip"
        make_zip(zip_path, {"doc.pdf": "pdf content"})

        effective, temp_dir = prepare_source(zip_path, temp_base=None)
        try:
            assert temp_dir is not None
            assert "historytools" in temp_dir.lower() or "tmp" in temp_dir.lower() or "temp" in temp_dir.lower()
        finally:
            if temp_dir and Path(temp_dir).exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)


# ── scan_source() ─────────────────────────────────────────────────────────────

class TestScanSource:
    def _make_source(self, root):
        """Build a small representative source tree."""
        make_file(root / "Letters" / "letter1.pdf", "pdf")
        make_file(root / "Letters" / "letter2.pdf", "pdf")
        make_file(root / "Photos" / "family.jpg", "jpg")
        make_file(root / "data.xlsx", "xlsx")
        make_file(root / "mystery.xyz", "xyz")
        return root

    def test_scan_returns_plan_structure(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        self._make_source(source)
        dest = tmp_path / "dest"

        plan = scan_source(source, dest, "standalone", set(), set())

        assert "files" in plan
        assert "summary" in plan
        assert "source_root" in plan
        assert "dest_root" in plan

    def test_scan_counts_total_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        self._make_source(source)
        dest = tmp_path / "dest"

        plan = scan_source(source, dest, "standalone", set(), set())
        assert plan["summary"]["total_files"] == 5

    def test_scan_routes_spreadsheet_to_needs_review(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        self._make_source(source)
        dest = tmp_path / "dest"

        plan = scan_source(source, dest, "standalone", set(), set())
        spreadsheet_entries = [f for f in plan["files"] if f["file_type"] == "spreadsheet"]
        assert all(e["dest_folder"] == "NeedsReview" for e in spreadsheet_entries)

    def test_scan_routes_unknown_to_unprocessed(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        self._make_source(source)
        dest = tmp_path / "dest"

        plan = scan_source(source, dest, "standalone", set(), set())
        unknown_entries = [f for f in plan["files"] if f["file_type"] == "unknown"]
        assert all(e["dest_folder"] == "Unprocessed" for e in unknown_entries)

    def test_scan_skips_zip_files(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        make_zip(source / "archive.zip", {"buried.txt": "text"})
        make_file(source / "letter.pdf", "content")

        plan = scan_source(source, tmp_path / "dest", "standalone", set(), set())
        source_paths = [f["source_path"] for f in plan["files"]]
        assert not any(p.endswith(".zip") for p in source_paths)

    def test_scan_summary_needs_review_count(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        self._make_source(source)
        dest = tmp_path / "dest"

        plan = scan_source(source, dest, "standalone", set(), set())
        assert plan["summary"]["needs_review"] >= 1  # at least the spreadsheet

    def test_scan_summary_unprocessable_count(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        self._make_source(source)
        dest = tmp_path / "dest"

        plan = scan_source(source, dest, "standalone", set(), set())
        assert plan["summary"]["unprocessable"] >= 1  # the .xyz file

    def test_scan_excludes_specified_directories(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        make_file(source / "Letters" / "letter.pdf", "pdf")
        make_file(source / ".organizer" / "hidden.pdf", "pdf")

        plan = scan_source(source, tmp_path / "dest", "standalone", {".organizer"}, set())
        source_paths = [f["source_path"] for f in plan["files"]]
        assert not any(".organizer" in p for p in source_paths)
        assert any("Letters" in p for p in source_paths)

    def test_scan_excludes_specified_extensions(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        make_file(source / "letter.pdf", "pdf")
        make_file(source / "thumbs.ini", "ini data")

        plan = scan_source(source, tmp_path / "dest", "standalone", set(), {".ini"})
        source_paths = [f["source_path"] for f in plan["files"]]
        assert not any(p.endswith(".ini") for p in source_paths)

    def test_scan_plan_entry_has_required_fields(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        make_file(source / "letter.pdf", "content")

        plan = scan_source(source, tmp_path / "dest", "standalone", set(), set())
        entry = plan["files"][0]

        required_fields = [
            "source_path", "dest_folder", "dest_subfolder", "proposed_name",
            "file_type", "file_size", "classification_source",
            "classification_confidence", "detected_date", "processing", "approved",
        ]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    def test_scan_letters_get_full_pipeline(self, tmp_path):
        source = tmp_path / "source"
        (source / "Letters").mkdir(parents=True)
        make_file(source / "Letters" / "letter.pdf", "pdf content")

        plan = scan_source(source, tmp_path / "dest", "standalone", set(), set())
        letter_entries = [f for f in plan["files"] if "Letters" in f.get("dest_folder", "")]
        assert all("transcribe" in e["processing"] for e in letter_entries)

    def test_scan_photo_gets_catalog_pipeline(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        make_file(source / "family.jpg", "jpg content")

        plan = scan_source(source, tmp_path / "dest", "standalone", set(), set())
        photo_entries = [f for f in plan["files"] if f["file_type"] == "photo"]
        assert all("catalog_photos" in e["processing"] for e in photo_entries)

    def test_scan_by_type_summary_is_correct(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        make_file(source / "letter.pdf", "pdf")
        make_file(source / "photo.jpg", "jpg")
        make_file(source / "audio.mp3", "mp3")

        plan = scan_source(source, tmp_path / "dest", "standalone", set(), set())
        by_type = plan["summary"]["by_type"]
        assert by_type.get("document", 0) == 1
        assert by_type.get("photo", 0) == 1
        assert by_type.get("audio", 0) == 1


# ── Taxonomy-driven tests ───────────────────────────────────────────────────────

import copy

SCRIPTS_DIR_FOR_CONFIG = Path(__file__).resolve().parent.parent / "familyarchive"
if str(SCRIPTS_DIR_FOR_CONFIG) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR_FOR_CONFIG))

from config import DEFAULT_TAXONOMY, load_taxonomy


class TestCustomFileTypeExtension:
    """Test that adding a new extension via taxonomy works."""

    def test_custom_extension_recognized(self):
        """A .webp extension added to photo type is recognized."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["file_types"]["photo"]["extensions"].append(".webp")
        assert get_file_type(".webp", tax) == "photo"

    def test_custom_extension_not_in_defaults(self):
        """.webp is unknown in the default taxonomy."""
        assert get_file_type(".webp") == "unknown"

    def test_custom_new_type_category(self):
        """A wholly new file type category can be added."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["file_types"]["cad"] = {
            "extensions": [".dwg", ".dxf"],
            "route_to": "Engineering/CAD",
        }
        assert get_file_type(".dwg", tax) == "cad"
        assert get_file_type(".dxf", tax) == "cad"

    def test_custom_type_route_to_used_in_classify(self, tmp_path):
        """A custom type with route_to is used by classify_by_type_default."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["file_types"]["cad"] = {
            "extensions": [".dwg"],
            "route_to": "Engineering/CAD",
        }
        dest, source = classify_by_type_default("cad", tax)
        assert dest == "Engineering/CAD"
        assert source == "type_default"


class TestCustomFolderKeyword:
    """Test that adding a new folder keyword via taxonomy works."""

    def test_custom_folder_hint_keyword(self, tmp_path):
        """A custom keyword maps to a custom folder via folder hints."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["folders"]["Military/Service"] = {
            "keywords": ["military", "army", "navy"],
            "description": "Military service records",
        }
        source_root = tmp_path / "source"
        folder = source_root / "Military Records"
        folder.mkdir(parents=True)
        f = folder / "discharge.pdf"

        dest, source = classify_by_folder_hints(f, source_root, tax)
        assert dest == "Military/Service"
        assert source == "folder_hint"

    def test_custom_filename_keyword(self):
        """A custom filename_keyword maps to a custom folder."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["folders"]["Military/Service"] = {
            "keywords": ["military"],
            "filename_keywords": ["enlistment"],
            "description": "Military service records",
        }
        dest, source = classify_by_filename("enlistment_papers.pdf", tax)
        assert dest == "Military/Service"
        assert source == "filename_pattern"

    def test_custom_keyword_does_not_affect_defaults(self, tmp_path):
        """Default keywords still work after adding custom ones."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["folders"]["Custom/Folder"] = {
            "keywords": ["custom"],
            "description": "Custom folder",
        }
        source_root = tmp_path / "source"
        folder = source_root / "Letters"
        folder.mkdir(parents=True)
        f = folder / "note.pdf"

        dest, source = classify_by_folder_hints(f, source_root, tax)
        assert dest == "Correspondence/Letters"


class TestCustomProcessingPipeline:
    """Test that custom processing pipelines via taxonomy work."""

    def test_custom_pipeline_for_document(self):
        """A modified document pipeline is used."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["processing_pipelines"]["document"] = ["copy", "transcribe", "rename"]
        pipeline = get_processing_pipeline("document", "Correspondence/Letters", tax)
        assert pipeline == ["copy", "transcribe", "rename"]

    def test_custom_pipeline_for_new_type(self):
        """A pipeline for a new type category is used."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["processing_pipelines"]["cad"] = ["copy", "convert_to_pdf"]
        pipeline = get_processing_pipeline("cad", "Engineering/CAD", tax)
        assert pipeline == ["copy", "convert_to_pdf"]

    def test_custom_pipeline_does_not_affect_needs_review(self):
        """Files in NeedsReview still get copy-only even with custom pipelines."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        tax["processing_pipelines"]["document"] = ["copy", "transcribe", "rename"]
        pipeline = get_processing_pipeline("document", "NeedsReview", tax)
        assert pipeline == ["copy"]

    def test_default_pipeline_used_for_unknown_type(self):
        """The 'default' pipeline is used for unrecognized types."""
        tax = copy.deepcopy(DEFAULT_TAXONOMY)
        pipeline = get_processing_pipeline("some_new_type", "SomeFolder", tax)
        assert pipeline == ["copy"]


class TestTaxonomyFallsBackToDefaults:
    """Test that the system works without a taxonomy.json file."""

    def test_load_taxonomy_returns_defaults_for_missing_file(self, tmp_path):
        """load_taxonomy returns DEFAULT_TAXONOMY when file doesn't exist."""
        nonexistent = tmp_path / "does_not_exist.json"
        tax = load_taxonomy(str(nonexistent))
        assert tax["version"] == 1
        assert "file_types" in tax
        assert "folders" in tax
        assert "processing_pipelines" in tax

    def test_default_taxonomy_matches_original_file_types(self):
        """DEFAULT_TAXONOMY has all the original file type mappings."""
        tax = DEFAULT_TAXONOMY
        assert get_file_type(".pdf", tax) == "document"
        assert get_file_type(".mp3", tax) == "audio"
        assert get_file_type(".jpg", tax) == "photo"
        assert get_file_type(".mp4", tax) == "video"
        assert get_file_type(".xlsx", tax) == "spreadsheet"
        assert get_file_type(".eml", tax) == "email"
        assert get_file_type(".gedcom", tax) == "genealogy"
        assert get_file_type(".xyz", tax) == "unknown"

    def test_default_taxonomy_folder_hints_match_original(self, tmp_path):
        """DEFAULT_TAXONOMY folder hints produce the same results as the original code."""
        tax = DEFAULT_TAXONOMY
        source_root = tmp_path / "source"

        test_cases = [
            ("Letters", "Correspondence/Letters"),
            ("Cards", "Correspondence/Cards"),
            ("Journals", "Journals"),
            ("tax returns", "Financial/Taxes"),
            ("Medical Records", "Medical"),
            ("cassette tapes", "Media/Audio/CassetteTapes"),
        ]
        for folder_name, expected_dest in test_cases:
            folder = source_root / folder_name
            folder.mkdir(parents=True, exist_ok=True)
            f = folder / "file.pdf"
            dest, _ = classify_by_folder_hints(f, source_root, tax)
            assert dest == expected_dest, f"Folder '{folder_name}' expected '{expected_dest}', got '{dest}'"

    def test_default_taxonomy_filename_patterns_match_original(self):
        """DEFAULT_TAXONOMY filename patterns produce the same results as the original code."""
        tax = DEFAULT_TAXONOMY
        test_cases = [
            ("personal_letter_1985.pdf", "Correspondence/Letters"),
            ("postcard_from_paris.pdf", "Correspondence/Cards"),
            ("my_journal_2020.pdf", "Journals"),
            ("grandma_obituary.pdf", "Memories"),
            ("family_recipe.pdf", "Documents/Recipes"),
        ]
        for filename, expected_dest in test_cases:
            dest, _ = classify_by_filename(filename, tax)
            assert dest == expected_dest, f"Filename '{filename}' expected '{expected_dest}', got '{dest}'"

    def test_default_taxonomy_pipelines_match_original(self):
        """DEFAULT_TAXONOMY pipelines produce the same results as the original code."""
        tax = DEFAULT_TAXONOMY
        assert get_processing_pipeline("document", "Correspondence/Letters", tax) == \
            ["copy", "transcribe", "format", "rename", "detect_date"]
        assert get_processing_pipeline("audio", "Media/Audio/FamilyRecordings", tax) == \
            ["copy", "transcribe_audio", "format", "rename"]
        assert get_processing_pipeline("photo", "Media/Photos", tax) == \
            ["copy", "catalog_photos"]
        assert get_processing_pipeline("video", "Media/Video", tax) == ["copy"]
        assert get_processing_pipeline("document", "NeedsReview", tax) == ["copy"]

    def test_functions_work_without_taxonomy_parameter(self):
        """All functions work when taxonomy parameter is omitted (uses DEFAULT_TAXONOMY)."""
        assert get_file_type(".pdf") == "document"
        assert classify_by_filename("letter.pdf") == ("Correspondence/Letters", "filename_pattern")
        dest, src = classify_by_type_default("audio")
        assert dest == "Media/Audio/FamilyRecordings"
        pipeline = get_processing_pipeline("document", "Journals")
        assert "transcribe" in pipeline
