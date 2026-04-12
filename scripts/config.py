"""Shim — real implementation in scripts/core/config.py"""
try:
    from .core.config import *  # noqa: F401,F403
except ImportError:
    # Fallback for bare sys.path imports (e.g. `from config import ...`)
    from scripts.core.config import *  # noqa: F401,F403
