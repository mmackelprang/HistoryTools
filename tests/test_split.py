"""
Tests for split_propose.py and split_apply.py — pure logic functions (no AI calls).
"""

import sys
from pathlib import Path

import pytest
import fitz  # PyMuPDF

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "familyarchive"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from split_propose import parse_transcript_pages, get_page_preview, format_page_range
from split_apply import extract_pdf_pages, extract_transcript_pages, create_split_transcript


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_transcript_body(page_texts):
    """Build a transcript body with ## Page N markers.

    Args:
        page_texts: Dict of {page_num: text} or list of texts (1-indexed).
    """
    if isinstance(page_texts, list):
        page_texts = {i + 1: t for i, t in enumerate(page_texts)}

    lines = []
    for num in sorted(page_texts.keys()):
        lines.append(f"## Page {num}")
        lines.append("")
        lines.append(page_texts[num])
        lines.append("")
    return "\n".join(lines)


def _make_test_pdf(path, num_pages=3, text_per_page=None):
    """Create a test PDF with the given number of pages.

    Args:
        path: Path for the output PDF.
        num_pages: Number of pages to create.
        text_per_page: Optional dict {page_num: text} for page content.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)
        text = (text_per_page or {}).get(i + 1, f"Content of page {i + 1}")
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return path


# ── parse_transcript_pages() ────────────────────────────────────────────────

class TestParseTranscriptPages:
    def test_parse_multiple_pages(self):
        body = _make_transcript_body({
            1: "Dear Bob, how are you?",
            2: "I hope this letter finds you well.",
            3: "Love, Alice",
        })
        pages = parse_transcript_pages(body)
        assert len(pages) == 3
        assert 1 in pages
        assert 2 in pages
        assert 3 in pages
        assert "Dear Bob" in pages[1]
        assert "Love, Alice" in pages[3]

    def test_parse_single_page_with_marker(self):
        body = "## Page 1\n\nThis is the only page.\n"
        pages = parse_transcript_pages(body)
        assert len(pages) == 1
        assert 1 in pages
        assert "only page" in pages[1]

    def test_parse_no_markers_returns_page_1(self):
        body = "This transcript has no page markers.\nJust plain text."
        pages = parse_transcript_pages(body)
        assert len(pages) == 1
        assert 1 in pages
        assert "no page markers" in pages[1]

    def test_parse_empty_body(self):
        pages = parse_transcript_pages("")
        assert pages == {}

    def test_parse_none_body(self):
        pages = parse_transcript_pages(None)
        assert pages == {}

    def test_parse_whitespace_only(self):
        pages = parse_transcript_pages("   \n\n  ")
        assert pages == {}

    def test_non_sequential_page_numbers(self):
        body = "## Page 3\n\nThird page text.\n\n## Page 7\n\nSeventh page text.\n"
        pages = parse_transcript_pages(body)
        assert len(pages) == 2
        assert 3 in pages
        assert 7 in pages
        assert "Third" in pages[3]
        assert "Seventh" in pages[7]

    def test_preserves_multiline_page_content(self):
        body = "## Page 1\n\nLine one.\nLine two.\nLine three.\n\n## Page 2\n\nPage two.\n"
        pages = parse_transcript_pages(body)
        assert "Line one." in pages[1]
        assert "Line two." in pages[1]
        assert "Line three." in pages[1]

    def test_formatted_page_markers(self):
        """Handles *Page N* markers from the mechanical formatter."""
        body = "---\n*Page 1*\nFirst page text.\n\n---\n*Page 2*\nSecond page text."
        pages = parse_transcript_pages(body)
        assert len(pages) == 2
        assert "First page" in pages[1]
        assert "Second page" in pages[2]

    def test_implied_page_1_before_page_2(self):
        """Content before the first page marker is page 1."""
        body = "Hope Johnson\n1010 E. Orange\nTempe, Az\n\n---\n*Page 2*\nDear Mark,"
        pages = parse_transcript_pages(body)
        assert 1 in pages
        assert "Hope Johnson" in pages[1]
        assert 2 in pages
        assert "Dear Mark" in pages[2]

    def test_implied_page_1_with_summary_before_markers(self):
        """Content before first marker (including AI summary) captured as page 1."""
        body = "> Summary of the document.\n\nActual page 1 content here.\n\n---\n*Page 2*\nPage two text."
        pages = parse_transcript_pages(body)
        assert 1 in pages
        assert "page 1 content" in pages[1]
        assert 2 in pages

    def test_mixed_raw_and_formatted_markers(self):
        """Handles mix of ## Page N and *Page N* (shouldn't happen but be safe)."""
        body = "## Page 1\nFirst.\n\n---\n*Page 2*\nSecond."
        pages = parse_transcript_pages(body)
        assert 1 in pages
        assert 2 in pages


# ── get_page_preview() ──────────────────────────────────────────────────────

class TestGetPagePreview:
    def test_extract_first_line(self):
        text = "Dear Bob, I wanted to write.\nThis is the second line."
        preview = get_page_preview(text)
        assert preview == "Dear Bob, I wanted to write."

    def test_truncate_long_text(self):
        text = "A" * 100
        preview = get_page_preview(text, max_chars=60)
        assert len(preview) == 60
        assert preview.endswith("...")

    def test_blank_page(self):
        assert get_page_preview("") == "[blank]"
        assert get_page_preview(None) == "[blank]"
        assert get_page_preview("   \n\n  ") == "[blank]"

    def test_skips_empty_lines(self):
        text = "\n\n\nActual content here.\n"
        preview = get_page_preview(text)
        assert preview == "Actual content here."

    def test_short_text_no_truncation(self):
        text = "Short text."
        preview = get_page_preview(text, max_chars=60)
        assert preview == "Short text."

    def test_exact_boundary(self):
        text = "A" * 60
        preview = get_page_preview(text, max_chars=60)
        assert preview == "A" * 60  # exactly at limit, no truncation


# ── format_page_range() ─────────────────────────────────────────────────────

class TestFormatPageRange:
    def test_contiguous_range(self):
        assert format_page_range([1, 2, 3]) == "1-3"

    def test_single_page(self):
        assert format_page_range([5]) == "5"

    def test_non_contiguous(self):
        assert format_page_range([1, 2, 3, 5, 7, 8, 9]) == "1-3, 5, 7-9"

    def test_empty(self):
        assert format_page_range([]) == ""

    def test_two_pages(self):
        assert format_page_range([1, 2]) == "1-2"

    def test_unsorted_input(self):
        assert format_page_range([3, 1, 2]) == "1-3"


# ── extract_transcript_pages() ──────────────────────────────────────────────

class TestExtractTranscriptPages:
    def test_extract_subset(self):
        body = _make_transcript_body([
            "Page one text.",
            "Page two text.",
            "Page three text.",
            "Page four text.",
            "Page five text.",
        ])
        result = extract_transcript_pages(body, [1, 2, 3])
        assert "## Page 1" in result
        assert "## Page 2" in result
        assert "## Page 3" in result
        assert "Page one text." in result
        assert "Page two text." in result
        assert "Page three text." in result
        # Should NOT contain page 4 or 5
        assert "Page four" not in result
        assert "Page five" not in result

    def test_renumber_pages(self):
        body = _make_transcript_body([
            "Page one text.",
            "Page two text.",
            "Page three text.",
            "Page four text.",
            "Page five text.",
        ])
        # Extract pages 3-5, should be renumbered to 1-3
        result = extract_transcript_pages(body, [3, 4, 5])
        assert "## Page 1" in result
        assert "## Page 2" in result
        assert "## Page 3" in result
        assert "Page three text." in result
        assert "Page four text." in result
        assert "Page five text." in result
        # Original numbering should not appear
        assert "## Page 3\n" not in result.split("## Page 1")[0]  # no "## Page 3" before "## Page 1"

    def test_nonexistent_pages(self):
        body = _make_transcript_body([
            "Page one text.",
            "Page two text.",
        ])
        # Request pages that don't exist
        result = extract_transcript_pages(body, [5, 6, 7])
        # Should return empty or minimal content
        assert "## Page" not in result or result.strip() == ""

    def test_partial_overlap(self):
        body = _make_transcript_body([
            "Page one text.",
            "Page two text.",
            "Page three text.",
        ])
        # Request mix of existing and non-existing
        result = extract_transcript_pages(body, [2, 5])
        assert "## Page 1" in result  # page 2 renumbered to 1
        assert "Page two text." in result
        assert "## Page 2" not in result  # page 5 doesn't exist

    def test_empty_body(self):
        result = extract_transcript_pages("", [1, 2])
        assert result == ""

    def test_none_body(self):
        result = extract_transcript_pages(None, [1, 2])
        assert result == ""

    def test_single_page_extraction(self):
        body = _make_transcript_body([
            "First page.",
            "Second page.",
            "Third page.",
        ])
        result = extract_transcript_pages(body, [2])
        assert "## Page 1" in result
        assert "Second page." in result


# ── extract_pdf_pages() ─────────────────────────────────────────────────────

class TestExtractPdfPages:
    def test_extract_subset_of_pages(self, tmp_path):
        source = _make_test_pdf(tmp_path / "source.pdf", num_pages=5)
        output = tmp_path / "output.pdf"

        count = extract_pdf_pages(source, [1, 3, 5], output)

        assert output.exists()
        assert count == 3

        # Verify page count in output PDF
        doc = fitz.open(str(output))
        assert len(doc) == 3
        doc.close()

    def test_extract_single_page(self, tmp_path):
        source = _make_test_pdf(tmp_path / "source.pdf", num_pages=10)
        output = tmp_path / "single.pdf"

        count = extract_pdf_pages(source, [7], output)

        assert output.exists()
        assert count == 1

        doc = fitz.open(str(output))
        assert len(doc) == 1
        doc.close()

    def test_extract_all_pages(self, tmp_path):
        source = _make_test_pdf(tmp_path / "source.pdf", num_pages=3)
        output = tmp_path / "all.pdf"

        count = extract_pdf_pages(source, [1, 2, 3], output)

        assert count == 3
        doc = fitz.open(str(output))
        assert len(doc) == 3
        doc.close()

    def test_out_of_range_pages_ignored(self, tmp_path):
        source = _make_test_pdf(tmp_path / "source.pdf", num_pages=3)
        output = tmp_path / "partial.pdf"

        # Page 5 doesn't exist in a 3-page PDF
        count = extract_pdf_pages(source, [1, 2, 5], output)

        assert count == 2  # Only pages 1 and 2 extracted

    def test_creates_parent_directory(self, tmp_path):
        source = _make_test_pdf(tmp_path / "source.pdf", num_pages=2)
        output = tmp_path / "subdir" / "deep" / "output.pdf"

        extract_pdf_pages(source, [1], output)

        assert output.exists()

    def test_pages_preserved_in_order(self, tmp_path):
        source = _make_test_pdf(
            tmp_path / "source.pdf", num_pages=5,
            text_per_page={1: "FIRST", 2: "SECOND", 3: "THIRD", 4: "FOURTH", 5: "FIFTH"}
        )
        output = tmp_path / "ordered.pdf"

        extract_pdf_pages(source, [3, 1, 5], output)

        doc = fitz.open(str(output))
        assert len(doc) == 3
        # Pages should be sorted: 1, 3, 5
        text0 = doc[0].get_text().strip()
        text1 = doc[1].get_text().strip()
        text2 = doc[2].get_text().strip()
        assert "FIRST" in text0
        assert "THIRD" in text1
        assert "FIFTH" in text2
        doc.close()


# ── create_split_transcript() ────────────────────────────────────────────────

class TestCreateSplitTranscript:
    def test_includes_transcription_method_split(self):
        segment = {
            "proposed_name": "1984-03-15_letter-alice.pdf",
            "pages": [1, 2, 3],
            "description": "Letter from Alice",
        }
        result = create_split_transcript(
            "## Page 1\n\nDear Bob.\n", segment, "compilation.pdf"
        )
        assert "transcription_method: split (from compilation.pdf)" in result

    def test_source_file_references_new_filename(self):
        segment = {
            "proposed_name": "1984-03-15_letter-alice.pdf",
            "pages": [1],
            "description": "Letter",
        }
        result = create_split_transcript("Hello.", segment, "compilation.pdf")
        assert "source_file: 1984-03-15_letter-alice.pdf" in result

    def test_correct_page_count(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [3, 4, 5],
            "description": "",
        }
        result = create_split_transcript("Some text here.", segment, "source.pdf")
        assert "page_count: 3" in result

    def test_correct_word_count(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1],
            "description": "",
        }
        text = "one two three four five"
        result = create_split_transcript(text, segment, "source.pdf")
        assert "word_count: 5" in result

    def test_includes_description(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1],
            "description": "Letter from Alice about spring",
        }
        result = create_split_transcript("text", segment, "source.pdf")
        assert "description: Letter from Alice about spring" in result

    def test_empty_description_omitted(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1],
            "description": "",
        }
        result = create_split_transcript("text", segment, "source.pdf")
        assert "description:" not in result

    def test_frontmatter_delimiters_present(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1],
            "description": "",
        }
        result = create_split_transcript("Body text.", segment, "source.pdf")
        assert result.startswith("---\n")
        assert "\n---\n" in result

    def test_body_text_included(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1, 2],
            "description": "",
        }
        result = create_split_transcript(
            "## Page 1\n\nHello world.\n", segment, "source.pdf"
        )
        # The extracted_text is passed directly, so it should appear in output
        assert "Hello world." in result

    def test_empty_extracted_text(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1],
            "description": "",
        }
        result = create_split_transcript("", segment, "source.pdf")
        assert "word_count: 0" in result

    def test_confidence_is_medium(self):
        segment = {
            "proposed_name": "test.pdf",
            "pages": [1],
            "description": "",
        }
        result = create_split_transcript("text", segment, "source.pdf")
        assert "transcription_confidence: medium" in result
