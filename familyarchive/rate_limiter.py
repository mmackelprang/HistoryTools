"""Shim — real implementation in familyarchive/core/rate_limiter.py"""
try:
    from .core.rate_limiter import *  # noqa: F401,F403
except ImportError:
    from core.rate_limiter import *  # noqa: F401,F403
