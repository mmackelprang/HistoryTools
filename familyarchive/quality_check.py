"""Shim — real implementation in familyarchive/core/quality_check.py"""
try:
    from .core.quality_check import *  # noqa: F401,F403
except ImportError:
    from core.quality_check import *  # noqa: F401,F403
