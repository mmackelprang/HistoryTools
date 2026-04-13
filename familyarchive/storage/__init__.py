"""
Storage abstraction for the Family Archive.

Provides a uniform interface for reading/writing archive files
regardless of whether they live on local disk or cloud storage.

Usage:
    from familyarchive.storage import get_storage, LocalStorage

    storage = get_storage({"type": "local", "root": "/path/to/archive"})
    storage.write("Letters/letter.pdf", data)
    content = storage.read("Letters/letter.pdf")
"""

from .base import StorageBackend
from .local import LocalStorage

__all__ = ["StorageBackend", "LocalStorage", "get_storage"]


def get_storage(config: dict) -> StorageBackend:
    """Create a storage backend from configuration.

    Args:
        config: Dict with "type" key. For local: {"type": "local", "root": "/path"}.

    Returns:
        A StorageBackend instance.
    """
    storage_type = config.get("type", "local")
    if storage_type == "local":
        return LocalStorage(root=config["root"])
    else:
        raise ValueError(
            f"Unknown storage type: {storage_type!r}. "
            f"Available: local. (S3 support planned for cloud mode.)"
        )
