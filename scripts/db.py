"""Shim — real implementation in scripts/core/db.py"""
try:
    from .core.db import *  # noqa: F401,F403
    from .core.db import _get_file_type, _get_date_prefix, _parse_folder_subfolder  # noqa: F401
except ImportError:
    from scripts.core.db import *  # noqa: F401,F403
    from scripts.core.db import _get_file_type, _get_date_prefix, _parse_folder_subfolder  # noqa: F401
