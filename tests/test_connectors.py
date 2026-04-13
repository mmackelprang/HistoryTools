"""Tests for connector base class and registry."""

import pytest

from familyarchive.connectors.base import (
    Connector,
    AuthType,
    DataType,
    Collection,
    Item,
    ConnectorRegistry,
)
from familyarchive.connectors import list_connectors, get_connector


def test_connector_is_abstract():
    """Connector cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Connector()


def test_concrete_connector():
    """A concrete connector implementing all methods can be instantiated."""

    class FakeConnector(Connector):
        name = "fake"
        display_name = "Fake Source"
        auth_type = AuthType.FILE_IMPORT
        data_types = [DataType.DOCUMENTS]

        def get_auth_url(self): return ""
        def handle_callback(self, code): return {}
        def refresh_token(self, creds): return creds
        def test_connection(self, creds): return True
        def list_collections(self, creds): return []
        def list_items(self, creds, collection_id, page_token=None): return []
        def get_item_preview(self, creds, item_id): return None
        def download_items(self, creds, item_ids, on_progress=None): return []
        def map_to_entities(self, item): return []
        def map_to_archive_file(self, item): return None

    conn = FakeConnector()
    assert conn.name == "fake"
    assert conn.display_name == "Fake Source"
    assert conn.auth_type == AuthType.FILE_IMPORT


def test_registry_register_and_list():
    """Connectors can be registered and listed."""
    registry = ConnectorRegistry()

    class TestConn(Connector):
        name = "test_source"
        display_name = "Test Source"
        auth_type = AuthType.API_KEY
        data_types = [DataType.PHOTOS]

        def get_auth_url(self): return ""
        def handle_callback(self, code): return {}
        def refresh_token(self, creds): return creds
        def test_connection(self, creds): return True
        def list_collections(self, creds): return []
        def list_items(self, creds, collection_id, page_token=None): return []
        def get_item_preview(self, creds, item_id): return None
        def download_items(self, creds, item_ids, on_progress=None): return []
        def map_to_entities(self, item): return []
        def map_to_archive_file(self, item): return None

    registry.register(TestConn)
    assert "test_source" in registry.list_names()
    assert registry.get("test_source") is TestConn


def test_registry_get_unknown():
    """Getting an unregistered connector returns None."""
    registry = ConnectorRegistry()
    assert registry.get("nonexistent") is None


def test_auth_type_enum():
    """AuthType enum has expected values."""
    assert AuthType.OAUTH2.value == "oauth2"
    assert AuthType.API_KEY.value == "api_key"
    assert AuthType.FILE_IMPORT.value == "file_import"
    assert AuthType.BROWSER_SESSION.value == "browser_session"


def test_data_type_enum():
    """DataType enum has expected values."""
    assert DataType.PHOTOS.value == "photos"
    assert DataType.MESSAGES.value == "messages"
    assert DataType.PEOPLE.value == "people"
    assert DataType.DOCUMENTS.value == "documents"
    assert DataType.ARTIFACTS.value == "artifacts"


def test_collection_dataclass():
    """Collection holds connector browsing data."""
    coll = Collection(id="album-1", name="Vacation 2024", item_count=42)
    assert coll.id == "album-1"
    assert coll.item_count == 42


def test_item_dataclass():
    """Item holds a single importable record."""
    item = Item(
        id="photo-123",
        name="sunset.jpg",
        item_type=DataType.PHOTOS,
        date="2024-07-04",
        thumbnail_url="https://example.com/thumb.jpg",
    )
    assert item.id == "photo-123"
    assert item.item_type == DataType.PHOTOS
