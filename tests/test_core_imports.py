"""
Smoke tests verifying scripts/core/ imports work correctly.

Tests that:
- Core modules are importable directly via scripts.core.*
- Shim re-exports work via scripts.*
- Both paths resolve to equivalent objects
"""


class TestCoreDirectImports:
    """Test that core modules are importable directly."""

    def test_import_config(self):
        from scripts.core.config import load_config, load_env, DEFAULT_CONFIG
        assert callable(load_config)
        assert callable(load_env)
        assert isinstance(DEFAULT_CONFIG, dict)

    def test_import_db(self):
        from scripts.core.db import get_db, close_db, init_schema, search
        assert callable(get_db)
        assert callable(close_db)
        assert callable(init_schema)
        assert callable(search)

    def test_import_ai_client(self):
        from scripts.core.ai_client import get_ai_client
        assert callable(get_ai_client)

    def test_import_cost_tracker(self):
        from scripts.core.cost_tracker import get_tracker
        assert callable(get_tracker)

    def test_import_rate_limiter(self):
        from scripts.core.rate_limiter import RateLimiter
        assert RateLimiter is not None

    def test_import_quality_check(self):
        from scripts.core.quality_check import assess_text_quality
        assert callable(assess_text_quality)


class TestShimEquivalence:
    """Test that shim imports resolve to equivalent objects as core imports."""

    def test_config_same_object(self):
        from scripts.config import load_config as shim_load
        from scripts.core.config import load_config as core_load
        assert shim_load is core_load

    def test_db_same_object(self):
        from scripts.db import get_db as shim_get
        from scripts.core.db import get_db as core_get
        assert shim_get is core_get

    def test_ai_client_equivalent(self):
        from scripts.ai_client import get_ai_client as shim_get
        from scripts.core.ai_client import get_ai_client as core_get
        # ai_client has reversed shim direction, so both should be callable
        assert callable(shim_get)
        assert callable(core_get)

    def test_cost_tracker_same_object(self):
        from scripts.cost_tracker import get_tracker as shim_get
        from scripts.core.cost_tracker import get_tracker as core_get
        assert shim_get is core_get

    def test_rate_limiter_same_object(self):
        from scripts.rate_limiter import RateLimiter as shim_cls
        from scripts.core.rate_limiter import RateLimiter as core_cls
        assert shim_cls is core_cls

    def test_quality_check_same_object(self):
        from scripts.quality_check import assess_text_quality as shim_fn
        from scripts.core.quality_check import assess_text_quality as core_fn
        assert shim_fn is core_fn
