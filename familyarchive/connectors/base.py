"""Connector base class and data models for external service integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class AuthType(Enum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    FILE_IMPORT = "file_import"
    BROWSER_SESSION = "browser_session"


class DataType(Enum):
    PHOTOS = "photos"
    MESSAGES = "messages"
    PEOPLE = "people"
    DOCUMENTS = "documents"
    ARTIFACTS = "artifacts"


@dataclass
class Collection:
    """A browsable group of items (album, folder, thread, etc.)."""
    id: str
    name: str
    item_count: int = 0
    metadata: Optional[dict] = None


@dataclass
class Item:
    """A single importable record from an external service."""
    id: str
    name: str
    item_type: DataType
    date: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: Optional[dict] = None


@dataclass
class DownloadedItem:
    """An item that has been downloaded and is ready for ingestion."""
    item: Item
    local_path: str
    data: Optional[bytes] = None


class Connector(ABC):
    """Base class for external service connectors.

    Each connector implements this interface to enable browsing, selecting,
    and importing data from an external service into the archive.

    Subclasses must set the class attributes: name, display_name, auth_type, data_types.
    """

    name: str
    display_name: str
    auth_type: AuthType
    data_types: list[DataType]

    # ── Auth lifecycle ───────────────────────────────────────────────

    @abstractmethod
    def get_auth_url(self) -> str:
        """Return the OAuth redirect URL (or empty string for non-OAuth)."""

    @abstractmethod
    def handle_callback(self, code: str) -> dict:
        """Exchange an auth code for credentials."""

    @abstractmethod
    def refresh_token(self, creds: dict) -> dict:
        """Refresh expired credentials."""

    @abstractmethod
    def test_connection(self, creds: dict) -> bool:
        """Verify that credentials are valid."""

    # ── Browse & discover ────────────────────────────────────────────

    @abstractmethod
    def list_collections(self, creds: dict) -> list[Collection]:
        """List available collections (albums, folders, threads)."""

    @abstractmethod
    def list_items(
        self, creds: dict, collection_id: str, page_token: str | None = None
    ) -> list[Item]:
        """List items in a collection."""

    @abstractmethod
    def get_item_preview(self, creds: dict, item_id: str) -> Any:
        """Get a preview (thumbnail + metadata) for a single item."""

    # ── Import ───────────────────────────────────────────────────────

    @abstractmethod
    def download_items(
        self, creds: dict, item_ids: list[str], on_progress=None
    ) -> list[DownloadedItem]:
        """Download selected items for ingestion."""

    # ── Map to archive ───────────────────────────────────────────────

    @abstractmethod
    def map_to_entities(self, item: Item) -> list[dict]:
        """Extract entity data (people, places, dates) from an item."""

    @abstractmethod
    def map_to_archive_file(self, item: DownloadedItem) -> Any:
        """Convert a downloaded item to the standard ingest format."""


class ConnectorRegistry:
    """Registry of available connectors.

    Connectors register themselves via register(). The web UI queries
    the registry to show available connectors in the 'Add Source' interface.
    """

    def __init__(self):
        self._connectors: dict[str, type[Connector]] = {}

    def register(self, connector_class: type[Connector]) -> type[Connector]:
        """Register a connector class. Can be used as a decorator."""
        self._connectors[connector_class.name] = connector_class
        return connector_class

    def get(self, name: str) -> type[Connector] | None:
        """Get a connector class by name."""
        return self._connectors.get(name)

    def list_names(self) -> list[str]:
        """List all registered connector names."""
        return list(self._connectors.keys())

    def list_all(self) -> list[dict]:
        """List all connectors with metadata."""
        return [
            {
                "name": cls.name,
                "display_name": cls.display_name,
                "auth_type": cls.auth_type.value,
                "data_types": [dt.value for dt in cls.data_types],
            }
            for cls in self._connectors.values()
        ]


# Global registry instance
_registry = ConnectorRegistry()


def register_connector(cls: type[Connector]) -> type[Connector]:
    """Decorator to register a connector with the global registry."""
    _registry.register(cls)
    return cls
