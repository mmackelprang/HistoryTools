"""Shim — real implementation in scripts/core/quality_check.py"""
try:
    from .core.quality_check import *  # noqa: F401,F403
except ImportError:
    from scripts.core.quality_check import *  # noqa: F401,F403
