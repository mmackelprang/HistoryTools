"""Shim — real implementation in scripts/core/rate_limiter.py"""
try:
    from .core.rate_limiter import *  # noqa: F401,F403
except ImportError:
    from scripts.core.rate_limiter import *  # noqa: F401,F403
