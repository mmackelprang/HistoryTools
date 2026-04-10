"""
Tests for quality_check.py -- transcription quality assessment.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from quality_check import assess_text_quality, should_retranscribe


# ── assess_text_quality() ─────────────────────────────────────────────────────

class TestAssessTextQuality:
    def test_good_english_text(self):
        """Well-formed English prose is rated 'good'."""
        text = (
            "Dear Mother, I hope this letter finds you well. "
            "The children have been doing great in school this year. "
            "We went to the church last Sunday and the service was lovely. "
            "Father said he would come visit us next month. "
            "I love you very much and think about you every day."
        )
        result = assess_text_quality(text)
        assert result["quality"] == "good"
        assert result["dict_word_ratio"] > 0.3
        assert "text appears readable" in result["reasons"]

    def test_garbage_text(self):
        """OCR garbage is rated 'poor'."""
        text = (
            "xfz7 kqm2 bvn8 plr3 wjt9 hdg4 ycx6 msn1 "
            "rtq5 bkz7 fwp2 hlm8 jvn3 dgt9 xcq4 yrz6 "
            "nks1 btp5 fhw2 qlm8 jvr3 dxg9 ycz4 msn6 "
            "wkt1 bfp5 hlq2 jvm8 dxr3 ycg9 nsz4 mtk6"
        )
        result = assess_text_quality(text)
        assert result["quality"] == "poor"

    def test_empty_text(self):
        """Empty text is rated 'poor'."""
        result = assess_text_quality("")
        assert result["quality"] == "poor"
        assert result["word_count"] == 0
        assert "empty text" in result["reasons"]

    def test_none_text(self):
        """None text is rated 'poor'."""
        result = assess_text_quality(None)
        assert result["quality"] == "poor"
        assert "empty text" in result["reasons"]

    def test_whitespace_only(self):
        """Whitespace-only text is rated 'poor'."""
        result = assess_text_quality("   \n\t  \n  ")
        assert result["quality"] == "poor"
        assert "empty text" in result["reasons"]

    def test_too_few_words(self):
        """Text with fewer than 10 words is rated 'poor'."""
        result = assess_text_quality("hello world")
        assert result["quality"] == "poor"
        assert "too few words" in result["reasons"]

    def test_repetitive_text(self):
        """Highly repetitive text is rated 'poor'."""
        # Simulate bad OCR that repeats the same characters
        text = " ".join(["the"] * 50)
        result = assess_text_quality(text)
        assert result["quality"] == "poor"
        assert any("repetitive" in r for r in result["reasons"])

    def test_high_special_char_ratio(self):
        """Text with excessive special characters is flagged as 'suspect'."""
        # Many real words but lots of special chars
        words = "the and for with but not from they have this".split()
        # Pad with special chars to push ratio > 0.3
        text = " ".join(words) + " @@@ ### $$$ %%% ^^^ &&& *** ((( ))) !!!"
        text += " @@@ ### $$$ %%% ^^^ &&& *** ((( ))) !!!"
        result = assess_text_quality(text)
        assert result["quality"] in ("suspect", "poor")

    def test_long_average_word_length(self):
        """Text with unusually long average word length is flagged."""
        # Generate words that are all very long (but not dictionary words)
        long_words = ["abcdefghijklmnop"] * 25
        text = " ".join(long_words)
        result = assess_text_quality(text)
        assert result["quality"] in ("suspect", "poor")
        assert any("long average word length" in r for r in result["reasons"])

    def test_returns_all_fields(self):
        """assess_text_quality returns all expected fields."""
        text = "the quick brown fox jumps over the lazy dog and the cat too"
        result = assess_text_quality(text)
        assert "quality" in result
        assert "word_count" in result
        assert "dict_word_ratio" in result
        assert "avg_word_length" in result
        assert "special_char_ratio" in result
        assert "reasons" in result
        assert isinstance(result["reasons"], list)

    def test_mixed_quality_text(self):
        """Text with some readable words mixed with gibberish is 'suspect'."""
        # Enough real words to not be "poor" but too few to be "good"
        text = (
            "the xfz kqm bvn plr wjt hdg ycx msn and "
            "rtq bkz fwp hlm jvn dgt xcq yrz for nks "
            "btp fhw qlm jvr dxg ycz msn wkt bfp hlq"
        )
        result = assess_text_quality(text)
        # Should be suspect or poor -- not good
        assert result["quality"] != "good"

    def test_ocr_failure_markers_rated_poor(self):
        """Text containing [OCR failed: ...] markers is always 'poor'."""
        text = (
            "## Page 1\n"
            "[OCR failed: [WinError 2] The system cannot find the file specified]\n"
            "## Page 2\n"
            "[OCR failed: [WinError 2] The system cannot find the file specified]\n"
        )
        result = assess_text_quality(text)
        assert result["quality"] == "poor"
        assert any("OCR failure" in r or "marker" in r for r in result["reasons"])

    def test_blank_page_markers_rated_poor(self):
        """Text containing [Page appears blank or illegible] markers is 'poor'."""
        text = (
            "## Page 1\n"
            "[Page appears blank or illegible]\n"
            "## Page 2\n"
            "[Page appears blank or illegible]\n"
        )
        result = assess_text_quality(text)
        assert result["quality"] == "poor"

    def test_mixed_ocr_failures_and_text(self):
        """Even one OCR failure marker makes the quality 'poor'."""
        text = (
            "This is some good text from page one of the document. "
            "It has many real words and reads well.\n"
            "[OCR failed: timeout]\n"
            "More good text here."
        )
        result = assess_text_quality(text)
        assert result["quality"] == "poor"


# ── should_retranscribe() ────────────────────────────────────────────────────

class TestShouldRetranscribe:
    def test_nonexistent_file(self, tmp_path):
        """Missing transcript file returns True."""
        fake_path = tmp_path / "does_not_exist.transcript.md"
        retranscribe, assessment = should_retranscribe(fake_path)
        assert retranscribe is True
        assert "no transcript exists" in assessment["reasons"]

    def test_good_transcript(self, tmp_path):
        """Good quality transcript returns False (no retranscription needed)."""
        transcript = tmp_path / "good.transcript.md"
        content = """---
source_file: test.pdf
transcription_method: native (PyMuPDF)
---

Dear Mother, I hope this letter finds you well. The children have been
doing great in school this year. We went to the church last Sunday and
the service was lovely. Father said he would come visit us next month.
I love you very much and think about you every day. The weather has been
wonderful and the garden is blooming beautifully.
"""
        transcript.write_text(content, encoding="utf-8")
        retranscribe, assessment = should_retranscribe(transcript)
        assert retranscribe is False
        assert assessment["quality"] == "good"

    def test_ai_transcribed_skips_assessment(self, tmp_path):
        """Already AI-transcribed files are skipped (return False)."""
        transcript = tmp_path / "ai.transcript.md"
        content = """---
source_file: test.pdf
transcription_method: ai-vision (Gemini)
---

Some text here.
"""
        transcript.write_text(content, encoding="utf-8")
        retranscribe, assessment = should_retranscribe(transcript)
        assert retranscribe is False
        assert "already AI-transcribed" in assessment["reasons"]

    def test_split_transcribed_skips_assessment(self, tmp_path):
        """Split-method transcripts are skipped (return False)."""
        transcript = tmp_path / "split.transcript.md"
        content = """---
source_file: test.pdf
transcription_method: split
---

Some text here.
"""
        transcript.write_text(content, encoding="utf-8")
        retranscribe, assessment = should_retranscribe(transcript)
        assert retranscribe is False

    def test_garbage_transcript(self, tmp_path):
        """Garbage transcript returns True (needs retranscription)."""
        transcript = tmp_path / "garbage.transcript.md"
        content = """---
source_file: test.pdf
transcription_method: native (PyMuPDF)
---

xfz7 kqm2 bvn8 plr3 wjt9 hdg4 ycx6 msn1 rtq5 bkz7 fwp2 hlm8
jvn3 dgt9 xcq4 yrz6 nks1 btp5 fhw2 qlm8 jvr3 dxg9 ycz4 msn6
wkt1 bfp5 hlq2 jvm8 dxr3 ycg9 nsz4 mtk6 bfp5 hlq2 jvm8 dxr3
"""
        transcript.write_text(content, encoding="utf-8")
        retranscribe, assessment = should_retranscribe(transcript)
        assert retranscribe is True
        assert assessment["quality"] in ("poor", "suspect")
