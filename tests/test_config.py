"""
Tests for config.py — load_config() and DEFAULT_CONFIG.
"""

import sys
import json
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config import load_config, DEFAULT_CONFIG


# ── DEFAULT_CONFIG ─────────────────────────────────────────────────────────────

class TestDefaultConfig:
    def test_has_source_root_key(self):
        assert "source_root" in DEFAULT_CONFIG

    def test_has_dest_root_key(self):
        assert "dest_root" in DEFAULT_CONFIG

    def test_has_mode_key(self):
        assert "mode" in DEFAULT_CONFIG

    def test_has_exclude_dirs_key(self):
        assert "exclude_dirs" in DEFAULT_CONFIG

    def test_has_exclude_exts_key(self):
        assert "exclude_exts" in DEFAULT_CONFIG

    def test_has_whisper_model_key(self):
        assert "whisper_model" in DEFAULT_CONFIG

    def test_has_tesseract_path_key(self):
        assert "tesseract_path" in DEFAULT_CONFIG

    def test_has_transcribe_folders_key(self):
        assert "transcribe_folders" in DEFAULT_CONFIG

    def test_has_skip_existing_transcripts_key(self):
        assert "skip_existing_transcripts" in DEFAULT_CONFIG

    def test_has_custom_categories_key(self):
        assert "custom_categories" in DEFAULT_CONFIG

    def test_default_mode_is_standalone(self):
        assert DEFAULT_CONFIG["mode"] == "standalone"

    def test_exclude_dirs_is_a_list(self):
        assert isinstance(DEFAULT_CONFIG["exclude_dirs"], list)

    def test_exclude_exts_is_a_list(self):
        assert isinstance(DEFAULT_CONFIG["exclude_exts"], list)


# ── load_config() ─────────────────────────────────────────────────────────────

class TestLoadConfig:
    def _write_config(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_load_valid_config_returns_dict(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
        })
        config = load_config(cfg_path)
        assert isinstance(config, dict)

    def test_load_config_missing_source_root_raises_value_error(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {"dest_root": str(tmp_path / "dest")})
        with pytest.raises(ValueError, match="source_root"):
            load_config(cfg_path)

    def test_load_config_missing_dest_root_raises_value_error(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {"source_root": str(tmp_path / "source")})
        with pytest.raises(ValueError, match="dest_root"):
            load_config(cfg_path)

    def test_load_config_empty_source_root_raises_value_error(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": "",
            "dest_root": str(tmp_path / "dest"),
        })
        with pytest.raises(ValueError):
            load_config(cfg_path)

    def test_load_config_merges_user_over_defaults(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
            "whisper_model": "large",
        })
        config = load_config(cfg_path)
        assert config["whisper_model"] == "large"

    def test_load_config_default_whisper_model_preserved_when_not_overridden(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
        })
        config = load_config(cfg_path)
        assert config["whisper_model"] == DEFAULT_CONFIG["whisper_model"]

    def test_load_config_converts_source_root_to_path(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
        })
        config = load_config(cfg_path)
        assert isinstance(config["source_root"], Path)

    def test_load_config_converts_dest_root_to_path(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
        })
        config = load_config(cfg_path)
        assert isinstance(config["dest_root"], Path)

    def test_load_config_converts_exclude_dirs_to_set(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
            "exclude_dirs": ["foo", "bar"],
        })
        config = load_config(cfg_path)
        assert isinstance(config["exclude_dirs"], set)
        assert "foo" in config["exclude_dirs"]

    def test_load_config_converts_exclude_exts_to_set(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
            "exclude_exts": [".ini", ".tmp"],
        })
        config = load_config(cfg_path)
        assert isinstance(config["exclude_exts"], set)
        assert ".ini" in config["exclude_exts"]

    def test_load_config_uses_defaults_when_file_missing(self, tmp_path):
        """When config file does not exist, defaults are used but validation still fails."""
        missing = tmp_path / "nonexistent.json"
        # source_root is empty in defaults → raises ValueError
        with pytest.raises(ValueError):
            load_config(missing)

    def test_load_config_custom_mode_is_preserved(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
            "mode": "merge",
        })
        config = load_config(cfg_path)
        assert config["mode"] == "merge"

    def test_load_config_extra_keys_are_preserved(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        self._write_config(cfg_path, {
            "source_root": str(tmp_path / "source"),
            "dest_root": str(tmp_path / "dest"),
            "my_custom_key": "my_value",
        })
        config = load_config(cfg_path)
        assert config["my_custom_key"] == "my_value"


class TestFindTesseract:
    """Tests for find_tesseract() auto-detection."""

    def test_returns_string(self):
        from config import find_tesseract
        result = find_tesseract()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_executable_path_or_command_name(self):
        from config import find_tesseract
        result = find_tesseract()
        # Should be either "tesseract" (on PATH) or a full path
        assert result == "tesseract" or Path(result).name.startswith("tesseract")
