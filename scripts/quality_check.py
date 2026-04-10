"""
Transcription Quality Assessment

Checks whether extracted text is actually readable (not OCR garbage).
Used by transcribe_pdfs.py to decide if native extraction is good enough
or if AI transcription is needed.
"""

import re
from pathlib import Path


# Common English words for dictionary check
# Minimum set -- just enough to detect gibberish vs real text
COMMON_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their",
    "what", "so", "up", "out", "if", "about", "who", "get", "which", "go",
    "me", "when", "make", "can", "like", "time", "no", "just", "him",
    "know", "take", "people", "into", "year", "your", "good", "some",
    "could", "them", "see", "other", "than", "then", "now", "look",
    "only", "come", "its", "over", "think", "also", "back", "after",
    "use", "two", "how", "our", "work", "first", "well", "way", "even",
    "new", "want", "because", "any", "these", "give", "day", "most", "us",
    "was", "were", "been", "had", "are", "is", "has", "did", "does",
    "am", "may", "should", "much", "very", "own", "still", "down",
    "dear", "love", "hope", "life", "family", "home", "school", "church",
    "mother", "father", "brother", "sister", "children", "letter", "write",
    "wrote", "read", "said", "told", "went", "came", "got", "put", "made",
    "left", "right", "hand", "long", "last", "great", "little", "old",
    "young", "big", "small", "every", "each", "next", "both", "more",
    "many", "before", "between", "through", "during", "never", "always",
    "together", "something", "nothing", "everything", "everyone",
}


def assess_text_quality(text):
    """Assess whether extracted text is readable or garbage.

    Returns a dict with:
        - quality: "good", "suspect", or "poor"
        - word_count: total words
        - dict_word_ratio: ratio of dictionary words (0.0-1.0)
        - avg_word_length: average word length
        - special_char_ratio: ratio of non-alphanumeric characters
        - reasons: list of reasons for the quality assessment
    """
    if not text or not text.strip():
        return {
            "quality": "poor",
            "word_count": 0,
            "dict_word_ratio": 0.0,
            "avg_word_length": 0.0,
            "special_char_ratio": 1.0,
            "reasons": ["empty text"],
        }

    words = text.split()
    word_count = len(words)

    if word_count < 10:
        return {
            "quality": "poor",
            "word_count": word_count,
            "dict_word_ratio": 0.0,
            "avg_word_length": 0.0,
            "special_char_ratio": 0.0,
            "reasons": ["too few words"],
        }

    # Dictionary word ratio
    clean_words = [re.sub(r"[^a-z]", "", w.lower()) for w in words]
    clean_words = [w for w in clean_words if len(w) > 1]
    if clean_words:
        dict_hits = sum(1 for w in clean_words if w in COMMON_WORDS)
        dict_ratio = dict_hits / len(clean_words)
    else:
        dict_ratio = 0.0

    # Average word length
    word_lengths = [len(w) for w in words if w.strip()]
    avg_length = sum(word_lengths) / len(word_lengths) if word_lengths else 0

    # Special character ratio
    total_chars = len(text)
    alpha_chars = sum(1 for c in text if c.isalnum() or c.isspace())
    special_ratio = 1 - (alpha_chars / total_chars) if total_chars > 0 else 0

    # Assess quality
    quality = "good"
    reasons = []

    if dict_ratio < 0.10:
        quality = "poor"
        reasons.append(f"very few recognizable words ({dict_ratio:.0%})")
    elif dict_ratio < 0.25:
        quality = "suspect"
        reasons.append(f"low dictionary word ratio ({dict_ratio:.0%})")

    if avg_length > 8:
        if quality != "poor":
            quality = "suspect"
        reasons.append(f"unusually long average word length ({avg_length:.1f})")

    if special_ratio > 0.15:
        if quality != "poor":
            quality = "suspect"
        reasons.append(f"high special character ratio ({special_ratio:.0%})")

    # Check for repeated patterns (common in bad OCR)
    if word_count > 20:
        unique_words = set(w.lower() for w in words)
        unique_ratio = len(unique_words) / word_count
        if unique_ratio < 0.2:
            quality = "poor"
            reasons.append(f"very repetitive text ({unique_ratio:.0%} unique)")

    if not reasons:
        reasons.append("text appears readable")

    return {
        "quality": quality,
        "word_count": word_count,
        "dict_word_ratio": round(dict_ratio, 3),
        "avg_word_length": round(avg_length, 1),
        "special_char_ratio": round(special_ratio, 3),
        "reasons": reasons,
    }


def should_retranscribe(transcript_path):
    """Check if an existing transcript should be re-transcribed with AI.

    Reads the transcript, assesses quality, and returns True if the
    transcription appears to be garbage (native extraction of handwritten text).

    Returns (should_retranscribe: bool, assessment: dict)
    """
    path = Path(transcript_path)
    if not path.exists():
        return True, {"quality": "poor", "reasons": ["no transcript exists"]}

    content = path.read_text(encoding="utf-8", errors="replace")

    # Check if already AI-transcribed (don't re-assess)
    if "ai-vision" in content or "transcription_method: split" in content:
        return False, {"quality": "good", "reasons": ["already AI-transcribed"]}

    # Extract body text (after frontmatter)
    parts = content.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else content

    # Remove page markers for assessment
    body = re.sub(r"## Page \d+", "", body)

    assessment = assess_text_quality(body)
    return assessment["quality"] in ("poor", "suspect"), assessment
