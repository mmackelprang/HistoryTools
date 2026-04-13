"""Shim — real implementation in scripts/core/config.py"""
try:
    from .core.config import *  # noqa: F401,F403
except ImportError:
    from core.config import *  # noqa: F401,F403
