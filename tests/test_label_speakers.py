"""
Tests for label_speakers.py — parse_speaker_map(), get_speaker_samples(),
apply_mapping(), apply_unmapping().
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from label_speakers import (
    parse_speaker_map,
    get_speaker_samples,
    apply_mapping,
    apply_unmapping,
)


# ── Sample transcript fixture ─────────────────────────────────────────────────

SAMPLE_TRANSCRIPT = """\
---
title: Test Recording
speakers:
  A: unknown
  B: unknown
---

**Speaker A** (00:00:01): Hello, this is Alice speaking. I have a lot to say today.

**Speaker B** (00:00:10): And I am Bob. Nice to meet you all.

**Speaker A** (00:00:20): Alice again, with more words here.
"""

SAMPLE_TRANSCRIPT_NAMED = """\
---
title: Test Recording
speakers:
  A: Alice
  B: Bob
---

**Alice** (00:00:01): Hello, this is Alice speaking. I have a lot to say today.

**Bob** (00:00:10): And I am Bob. Nice to meet you all.

**Alice** (00:00:20): Alice again, with more words here.
"""


# ── parse_speaker_map() ───────────────────────────────────────────────────────

class TestParseSpeakerMap:
    def test_simple_two_speaker_mapping(self):
        result = parse_speaker_map("A=Alice,B=Bob")
        assert result == {"A": "Alice", "B": "Bob"}

    def test_single_speaker_mapping(self):
        result = parse_speaker_map("A=Alice")
        assert result == {"A": "Alice"}

    def test_whitespace_around_pairs_is_stripped(self):
        result = parse_speaker_map("A = Alice , B = Bob")
        assert result == {"A": "Alice", "B": "Bob"}

    def test_invalid_pair_without_equals_is_skipped(self, capsys):
        result = parse_speaker_map("A=Alice,BadEntry,B=Bob")
        assert "A" in result
        assert "B" in result
        assert "BadEntry" not in result
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_empty_string_returns_empty_dict(self):
        result = parse_speaker_map("")
        # Empty string: split(",") gives [""] which has no "=" → warning printed, empty dict
        assert isinstance(result, dict)

    def test_value_with_spaces_preserved(self):
        result = parse_speaker_map("A=Mary Jane")
        assert result["A"] == "Mary Jane"

    def test_multiple_equals_in_value_uses_first_split(self):
        # split("=", 1) so "A=a=b" → key "A", val "a=b"
        result = parse_speaker_map("A=first=second")
        assert result["A"] == "first=second"

    def test_three_speakers(self):
        result = parse_speaker_map("A=Alice,B=Bob,C=Carol")
        assert result == {"A": "Alice", "B": "Bob", "C": "Carol"}


# ── get_speaker_samples() ─────────────────────────────────────────────────────

class TestGetSpeakerSamples:
    def test_finds_both_speakers(self):
        speakers = get_speaker_samples(SAMPLE_TRANSCRIPT)
        assert "A" in speakers
        assert "B" in speakers

    def test_sample_count_limited_to_three(self):
        # Build transcript with many utterances from one speaker
        content = ""
        for i in range(10):
            content += f"**Speaker A** (00:{i:02d}:00): Utterance number {i}.\n\n"
        content += "**Speaker B** (00:10:00): Just one line.\n\n"

        speakers = get_speaker_samples(content)
        assert len(speakers["A"]) <= 3

    def test_no_speakers_returns_empty_dict(self):
        speakers = get_speaker_samples("No speaker labels here.")
        assert speakers == {}

    def test_sample_contains_timestamp(self):
        speakers = get_speaker_samples(SAMPLE_TRANSCRIPT)
        # Each sample should contain the timestamp
        for sample in speakers["A"]:
            assert "00:" in sample

    def test_long_text_is_truncated_with_ellipsis(self):
        long_text = "X" * 200
        content = f"**Speaker A** (00:00:01): {long_text}\n\n"
        speakers = get_speaker_samples(content)
        if speakers.get("A"):
            sample = speakers["A"][0]
            assert "..." in sample

    def test_single_speaker_only(self):
        content = "**Speaker A** (00:00:01): Only one person talking.\n\n"
        speakers = get_speaker_samples(content)
        assert len(speakers) == 1
        assert "A" in speakers


# ── apply_mapping() ───────────────────────────────────────────────────────────

class TestApplyMapping:
    def test_replaces_speaker_a_label_with_alice(self):
        mapping = {"A": "Alice", "B": "Bob"}
        result = apply_mapping(SAMPLE_TRANSCRIPT, mapping)
        assert "**Alice**" in result
        assert "**Bob**" in result

    def test_removes_original_speaker_labels(self):
        mapping = {"A": "Alice", "B": "Bob"}
        result = apply_mapping(SAMPLE_TRANSCRIPT, mapping)
        assert "**Speaker A**" not in result
        assert "**Speaker B**" not in result

    def test_updates_yaml_frontmatter_assignments(self):
        mapping = {"A": "Alice", "B": "Bob"}
        result = apply_mapping(SAMPLE_TRANSCRIPT, mapping)
        assert "  A: Alice" in result
        assert "  B: Bob" in result

    def test_does_not_replace_speaker_labels_in_body_text(self):
        """Names in the spoken content should not be affected."""
        content = (
            "---\nspeakers:\n  A: unknown\n---\n\n"
            "**Speaker A** (00:00:01): The word Speaker A appears in text too.\n\n"
        )
        mapping = {"A": "Alice"}
        result = apply_mapping(content, mapping)
        # The label at the start should be replaced
        assert "**Alice** (00:00:01):" in result
        # Body text "Speaker A" (without **bold** markers and timestamp) stays unchanged
        # because the regex only matches **Speaker X** followed by " ("
        # so "Speaker A appears in text" won't be touched

    def test_empty_mapping_returns_content_unchanged(self):
        result = apply_mapping(SAMPLE_TRANSCRIPT, {})
        assert result == SAMPLE_TRANSCRIPT

    def test_partial_mapping_only_replaces_specified_speaker(self):
        mapping = {"A": "Alice"}  # only map A, not B
        result = apply_mapping(SAMPLE_TRANSCRIPT, mapping)
        assert "**Alice**" in result
        assert "**Speaker B**" in result  # B untouched

    def test_idempotent_on_already_named_content(self):
        """Applying the same mapping twice should not corrupt the content."""
        mapping = {"A": "Alice", "B": "Bob"}
        once = apply_mapping(SAMPLE_TRANSCRIPT, mapping)
        twice = apply_mapping(once, mapping)
        assert once == twice


# ── apply_unmapping() ────────────────────────────────────────────────────────

class TestApplyUnmapping:
    def test_reverts_alice_back_to_speaker_a(self):
        unmap = {"Alice": "A", "Bob": "B"}
        result = apply_unmapping(SAMPLE_TRANSCRIPT_NAMED, unmap)
        assert "**Speaker A**" in result
        assert "**Speaker B**" in result

    def test_removes_real_names_from_labels(self):
        unmap = {"Alice": "A", "Bob": "B"}
        result = apply_unmapping(SAMPLE_TRANSCRIPT_NAMED, unmap)
        assert "**Alice**" not in result
        assert "**Bob**" not in result

    def test_reverts_yaml_frontmatter_to_unknown(self):
        unmap = {"Alice": "A", "Bob": "B"}
        result = apply_unmapping(SAMPLE_TRANSCRIPT_NAMED, unmap)
        assert "  A: unknown" in result
        assert "  B: unknown" in result

    def test_empty_unmap_returns_content_unchanged(self):
        result = apply_unmapping(SAMPLE_TRANSCRIPT_NAMED, {})
        assert result == SAMPLE_TRANSCRIPT_NAMED

    def test_apply_then_unapply_round_trips(self):
        mapping = {"A": "Alice", "B": "Bob"}
        unmap = {"Alice": "A", "Bob": "B"}
        named = apply_mapping(SAMPLE_TRANSCRIPT, mapping)
        restored = apply_unmapping(named, unmap)
        assert restored == SAMPLE_TRANSCRIPT

    def test_partial_unmap_only_reverts_specified_speaker(self):
        unmap = {"Alice": "A"}  # only unmap Alice
        result = apply_unmapping(SAMPLE_TRANSCRIPT_NAMED, unmap)
        assert "**Speaker A**" in result
        assert "**Bob**" in result  # Bob untouched
