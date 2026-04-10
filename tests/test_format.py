"""
Tests for format_transcripts.py — mechanical formatting functions.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from format_transcripts import (
    format_page_breaks,
    normalize_whitespace,
    strip_artifacts,
    break_long_speaker_blocks,
    format_body_mechanical,
    parse_frontmatter,
    detect_type,
    rebuild_file,
)


class TestFormatPageBreaks:
    def test_replaces_page_marker_with_hr(self):
        body = "Some text\n## Page 1\nMore text"
        result = format_page_breaks(body)
        assert "---" in result
        assert "*Page 1*" in result
        assert "## Page 1" not in result

    def test_multiple_pages(self):
        body = "## Page 1\nFirst\n## Page 2\nSecond\n## Page 3\nThird"
        result = format_page_breaks(body)
        assert "*Page 1*" in result
        assert "*Page 2*" in result
        assert "*Page 3*" in result
        assert result.count("---") == 3

    def test_no_pages(self):
        body = "Just plain text with no page markers"
        result = format_page_breaks(body)
        assert result == body

    def test_preserves_surrounding_text(self):
        body = "Before\n## Page 5\nAfter"
        result = format_page_breaks(body)
        assert "Before" in result
        assert "After" in result


class TestNormalizeWhitespace:
    def test_collapses_excessive_blank_lines(self):
        body = "Text\n\n\n\n\n\nMore text"
        result = normalize_whitespace(body)
        assert "\n\n\n\n" not in result
        assert "Text" in result
        assert "More text" in result

    def test_strips_trailing_whitespace(self):
        body = "Line with trailing spaces   \nAnother line  "
        result = normalize_whitespace(body)
        assert "   \n" not in result

    def test_ends_with_single_newline(self):
        body = "Text\n\n\n"
        result = normalize_whitespace(body)
        assert result.endswith("\n")
        assert not result.endswith("\n\n")

    def test_preserves_single_blank_lines(self):
        body = "Paragraph one\n\nParagraph two"
        result = normalize_whitespace(body)
        assert "Paragraph one\n\nParagraph two" in result


class TestStripArtifacts:
    def test_strips_barcode_numbers(self):
        body = "Real text\n1234567890123\nMore text"
        result = strip_artifacts(body)
        assert "1234567890123" not in result
        assert "Real text" in result

    def test_strips_isbn(self):
        body = "Text\nISBN 978-0-123-45678-9\nMore"
        result = strip_artifacts(body)
        assert "ISBN" not in result

    def test_strips_copyright(self):
        body = "Text\n© 2024 SOME CORP.\nMore"
        result = strip_artifacts(body)
        assert "CORP" not in result

    def test_preserves_normal_text(self):
        body = "Dear Bob, I wanted to write to you about our trip."
        result = strip_artifacts(body)
        assert result.strip() == body.strip()

    def test_strips_printed_in(self):
        body = "Text\nPrinted in the U.S.A.\nMore"
        result = strip_artifacts(body)
        assert "Printed in" not in result


class TestBreakLongSpeakerBlocks:
    def test_short_block_unchanged(self):
        body = "**Speaker A** (0:00 - 0:30): This is a short block of text."
        result = break_long_speaker_blocks(body, max_words=50)
        assert result.strip() == body.strip()

    def test_long_block_split_at_sentence(self):
        words = " ".join(["word"] * 200)
        sentence = words + ". " + words + ". End."
        body = f"**Speaker A** (0:00 - 5:00): {sentence}"
        result = break_long_speaker_blocks(body, max_words=100)
        # Should have paragraph breaks
        assert "\n\n" in result
        # Speaker label should only appear once
        assert result.count("**Speaker A**") == 1

    def test_no_speaker_labels_unchanged(self):
        body = "This is just plain text without any speaker labels."
        result = break_long_speaker_blocks(body)
        assert result == body


class TestFormatBodyMechanical:
    def test_pdf_formatting(self):
        body = "## Page 1\nText\n\nISBN 123-456\n## Page 2\nMore"
        result = format_body_mechanical(body, "pdf")
        assert "*Page 1*" in result
        assert "ISBN" not in result
        assert "---" in result

    def test_audio_formatting(self):
        words = " ".join(["word"] * 300)
        body = f"**Speaker A** (0:00 - 10:00): {words}. End of speech."
        result = format_body_mechanical(body, "audio")
        # Should try to break long blocks
        assert "**Speaker A**" in result


class TestParseFrontmatter:
    def test_parses_frontmatter(self):
        content = "---\nsource_file: test.pdf\nconfidence: high\n---\nBody text"
        fm_text, fm_dict, body = parse_frontmatter(content)
        assert fm_dict["source_file"] == "test.pdf"
        assert body == "Body text"

    def test_no_frontmatter(self):
        content = "Just body text"
        fm_text, fm_dict, body = parse_frontmatter(content)
        assert fm_text == ""
        assert body == content


class TestDetectType:
    def test_audio_assemblyai(self):
        assert detect_type({"transcription_tool": "AssemblyAI (speaker diarization)"}) == "audio"

    def test_audio_whisper(self):
        assert detect_type({"transcription_tool": "OpenAI Whisper (base model)"}) == "audio"

    def test_pdf_gemini(self):
        assert detect_type({"transcription_method": "ai-vision (gemini-2.5-flash)"}) == "pdf"

    def test_pdf_native(self):
        assert detect_type({"transcription_method": "native (PyMuPDF)"}) == "pdf"

    def test_pdf_split(self):
        assert detect_type({"transcription_method": "split (from compilation.pdf)"}) == "pdf"

    def test_default_is_pdf(self):
        assert detect_type({}) == "pdf"


class TestRebuildFile:
    def test_adds_formatting_cleaned(self):
        result = rebuild_file("source_file: test.pdf", "Body text")
        assert "formatting: cleaned" in result

    def test_includes_body(self):
        result = rebuild_file("source_file: test.pdf", "Body text here")
        assert "Body text here" in result

    def test_includes_summary_when_provided(self):
        result = rebuild_file("source_file: test.pdf", "Body", summary="> A summary.")
        assert "> A summary." in result

    def test_no_summary_by_default(self):
        result = rebuild_file("source_file: test.pdf", "Body")
        assert ">" not in result.split("---")[-1][:20]

    def test_preserves_title(self):
        result = rebuild_file("source_file: test.pdf", "Body", original_title_line="# My Title")
        assert "# My Title" in result
