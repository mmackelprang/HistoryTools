"""Shim — real implementation in familyarchive/core/ai_client.py"""
try:
    from .core.ai_client import *  # noqa: F401,F403
except ImportError:
    from core.ai_client import *  # noqa: F401,F403
