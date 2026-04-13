"""Verify that core library modules are importable from familyarchive.core."""


def test_config_importable():
    from familyarchive.core.config import load_config, load_taxonomy, DEFAULT_TAXONOMY
    assert callable(load_config)


def test_db_importable():
    from familyarchive.core.db import get_db, search, get_stats
    assert callable(get_db)


def test_ai_client_importable():
    from familyarchive.core.ai_client import get_ai_client, call_text
    assert callable(get_ai_client)


def test_cost_tracker_importable():
    from familyarchive.core.cost_tracker import CostTracker
    assert CostTracker is not None


def test_extract_importable():
    from familyarchive.core.extract import extract_file, get_supported_extensions
    assert callable(extract_file)


def test_quality_check_importable():
    from familyarchive.core.quality_check import assess_text_quality
    assert callable(assess_text_quality)


def test_rate_limiter_importable():
    from familyarchive.core.rate_limiter import RateLimiter
    assert RateLimiter is not None
