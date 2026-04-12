"""Shim — real implementation in scripts/ai_client.py"""
try:
    from ..ai_client import *  # noqa: F401,F403
except ImportError:
    from scripts.ai_client import *  # noqa: F401,F403
