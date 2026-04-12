"""Shim — real implementation in scripts/ai_client.py (reversed due to test patching)"""
try:
    from ..ai_client import *  # noqa: F401,F403
except ImportError:
    from ai_client import *  # noqa: F401,F403
