"""
Connector framework for external service integration.

Provides a pluggable system for importing data from external services
(Google Photos, FamilySearch, Facebook, etc.) into the archive.

Usage:
    from familyarchive.connectors import list_connectors, get_connector
    from familyarchive.connectors.base import Connector, register_connector
"""

from .base import (
    Connector,
    ConnectorRegistry,
    AuthType,
    DataType,
    Collection,
    Item,
    DownloadedItem,
    register_connector,
)
from .base import _registry as _registry

__all__ = [
    "Connector", "ConnectorRegistry", "AuthType", "DataType",
    "Collection", "Item", "DownloadedItem",
    "register_connector", "list_connectors", "get_connector",
]


def list_connectors() -> list[dict]:
    """List all registered connectors with metadata."""
    return _registry.list_all()


def get_connector(name: str) -> type[Connector] | None:
    """Get a registered connector class by name."""
    return _registry.get(name)
