"""
Tests for ai_client.py -- unified AI client abstraction.
"""

import sys
import os
import importlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Check which vendor SDKs are available (for conditional skipping)
_has_genai = importlib.util.find_spec("google.genai") is not None or importlib.util.find_spec("google") is not None
_has_openai = importlib.util.find_spec("openai") is not None
_has_anthropic = importlib.util.find_spec("anthropic") is not None

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ai_client import get_ai_client, parse_json_response


# ── get_ai_client() ──────────────────────────────────────────────────────────

class TestGetAiClient:
    def test_raises_value_error_when_no_keys_set(self):
        """get_ai_client() raises ValueError when no API keys are in env."""
        with patch.dict(os.environ, {}, clear=True):
            # Also suppress load_env from loading a real .env
            with patch("ai_client.load_env"):
                with pytest.raises(ValueError, match="No AI API key found"):
                    get_ai_client()

    def test_raises_value_error_for_unknown_vendor(self):
        """get_ai_client() raises ValueError for an unknown vendor name."""
        with patch("ai_client.load_env"):
            with pytest.raises(ValueError, match="Unknown vendor"):
                get_ai_client(vendor="deepseek")

    def test_explicit_vendor_gemini_without_key_raises(self):
        """Requesting gemini explicitly without a key raises ValueError (key checked before SDK import)."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("ai_client.load_env"):
                with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
                    get_ai_client(vendor="gemini")

    def test_explicit_vendor_openai_without_key_raises(self):
        """Requesting openai explicitly without a key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("ai_client.load_env"):
                with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
                    get_ai_client(vendor="openai")

    def test_explicit_vendor_anthropic_without_key_raises(self):
        """Requesting anthropic explicitly without a key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("ai_client.load_env"):
                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
                    get_ai_client(vendor="anthropic")

    @pytest.mark.skipif(not _has_genai, reason="google-genai not installed")
    def test_auto_detect_gemini_when_key_set(self):
        """Auto-detection returns gemini when GEMINI_API_KEY is set."""
        env = {"GEMINI_API_KEY": "test-key-123"}
        with patch.dict(os.environ, env, clear=True):
            with patch("ai_client.load_env"):
                with patch("google.genai.Client") as mock_client:
                    mock_client.return_value = MagicMock()
                    client, vendor = get_ai_client()
                    assert vendor == "gemini"

    @pytest.mark.skipif(not _has_openai, reason="openai not installed")
    def test_auto_detect_openai_when_key_set(self):
        """Auto-detection returns openai when only OPENAI_API_KEY is set."""
        env = {"OPENAI_API_KEY": "test-key-456"}
        with patch.dict(os.environ, env, clear=True):
            with patch("ai_client.load_env"):
                with patch("openai.OpenAI") as mock_client:
                    mock_client.return_value = MagicMock()
                    client, vendor = get_ai_client()
                    assert vendor == "openai"

    @pytest.mark.skipif(not _has_anthropic, reason="anthropic not installed")
    def test_auto_detect_anthropic_when_key_set(self):
        """Auto-detection returns anthropic when only ANTHROPIC_API_KEY is set."""
        env = {"ANTHROPIC_API_KEY": "test-key-789"}
        with patch.dict(os.environ, env, clear=True):
            with patch("ai_client.load_env"):
                with patch("anthropic.Anthropic") as mock_client:
                    mock_client.return_value = MagicMock()
                    client, vendor = get_ai_client()
                    assert vendor == "anthropic"

    @pytest.mark.skipif(not _has_genai, reason="google-genai not installed")
    def test_gemini_takes_priority_over_openai_in_auto_detect(self):
        """When both GEMINI and OPENAI keys are set, gemini is preferred."""
        env = {"GEMINI_API_KEY": "gem-key", "OPENAI_API_KEY": "oai-key"}
        with patch.dict(os.environ, env, clear=True):
            with patch("ai_client.load_env"):
                with patch("google.genai.Client") as mock_client:
                    mock_client.return_value = MagicMock()
                    client, vendor = get_ai_client()
                    assert vendor == "gemini"


# ── parse_json_response() ────────────────────────────────────────────────────

class TestParseJsonResponse:
    def test_parses_clean_json(self):
        """parse_json_response() handles clean JSON objects."""
        result = parse_json_response('{"slug": "test-slug", "reasoning": "because"}')
        assert result == {"slug": "test-slug", "reasoning": "because"}

    def test_parses_code_fenced_json(self):
        """parse_json_response() strips ```json fences."""
        text = '```json\n{"slug": "hello-world", "reasoning": "greeting"}\n```'
        result = parse_json_response(text)
        assert result == {"slug": "hello-world", "reasoning": "greeting"}

    def test_parses_json_with_whitespace(self):
        """parse_json_response() handles leading/trailing whitespace."""
        text = '  \n  {"key": "value"}  \n  '
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_extracts_json_from_surrounding_text(self):
        """parse_json_response() extracts JSON from surrounding text."""
        text = 'Here is the result: {"slug": "found-it"} Hope that helps!'
        result = parse_json_response(text)
        assert result == {"slug": "found-it"}

    def test_returns_none_for_malformed_json(self):
        """parse_json_response() returns None for completely unparseable text."""
        result = parse_json_response("This is not JSON at all, no braces here.")
        assert result is None

    def test_returns_none_for_invalid_json_in_braces(self):
        """parse_json_response() returns None when braces contain invalid JSON."""
        result = parse_json_response("{not: valid: json: [}")
        assert result is None

    def test_parses_nested_json(self):
        """parse_json_response() handles nested JSON objects."""
        text = '{"outer": {"inner": "value"}, "list": [1, 2, 3]}'
        result = parse_json_response(text)
        assert result == {"outer": {"inner": "value"}, "list": [1, 2, 3]}

    def test_handles_empty_string(self):
        """parse_json_response() returns None for empty string."""
        result = parse_json_response("")
        assert result is None
