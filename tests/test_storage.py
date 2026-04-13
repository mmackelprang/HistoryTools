"""Tests for storage abstraction layer."""

import pytest
from pathlib import Path

from familyarchive.storage import get_storage, LocalStorage
from familyarchive.storage.base import StorageBackend


def test_storage_backend_is_abstract():
    """StorageBackend cannot be instantiated directly."""
    with pytest.raises(TypeError):
        StorageBackend()


def test_local_storage_implements_interface(tmp_path):
    """LocalStorage implements all StorageBackend methods."""
    storage = LocalStorage(root=tmp_path)
    assert isinstance(storage, StorageBackend)


def test_local_storage_read_write(tmp_path):
    """LocalStorage can write and read files."""
    storage = LocalStorage(root=tmp_path)
    storage.write("test/hello.txt", b"hello world")
    data = storage.read("test/hello.txt")
    assert data == b"hello world"


def test_local_storage_exists(tmp_path):
    """LocalStorage.exists() reports file presence correctly."""
    storage = LocalStorage(root=tmp_path)
    assert not storage.exists("missing.txt")
    storage.write("present.txt", b"here")
    assert storage.exists("present.txt")


def test_local_storage_delete(tmp_path):
    """LocalStorage.delete() removes files."""
    storage = LocalStorage(root=tmp_path)
    storage.write("doomed.txt", b"bye")
    assert storage.exists("doomed.txt")
    storage.delete("doomed.txt")
    assert not storage.exists("doomed.txt")


def test_local_storage_list(tmp_path):
    """LocalStorage.list_files() returns relative paths."""
    storage = LocalStorage(root=tmp_path)
    storage.write("a.txt", b"a")
    storage.write("sub/b.txt", b"b")
    storage.write("sub/c.txt", b"c")

    files = sorted(storage.list_files(""))
    assert "a.txt" in files
    assert "sub/b.txt" in files or "sub\\b.txt" in files

    sub_files = sorted(storage.list_files("sub"))
    assert len(sub_files) == 2


def test_local_storage_resolve(tmp_path):
    """LocalStorage.resolve() returns absolute filesystem path."""
    storage = LocalStorage(root=tmp_path)
    storage.write("doc.pdf", b"pdf data")
    resolved = storage.resolve("doc.pdf")
    assert resolved is not None
    assert Path(resolved).exists()
    assert Path(resolved).read_bytes() == b"pdf data"


def test_local_storage_resolve_missing(tmp_path):
    """LocalStorage.resolve() returns None for missing files."""
    storage = LocalStorage(root=tmp_path)
    assert storage.resolve("nope.txt") is None


def test_local_storage_is_reachable(tmp_path):
    """LocalStorage.is_reachable() checks if root exists."""
    storage = LocalStorage(root=tmp_path)
    assert storage.is_reachable()

    gone_storage = LocalStorage(root=tmp_path / "nonexistent")
    assert not gone_storage.is_reachable()


def test_get_storage_returns_local(tmp_path):
    """get_storage() returns LocalStorage for local config."""
    storage = get_storage({"type": "local", "root": str(tmp_path)})
    assert isinstance(storage, LocalStorage)


def test_get_storage_unknown_type():
    """get_storage() raises for unknown storage types."""
    with pytest.raises(ValueError, match="Unknown storage type"):
        get_storage({"type": "s3", "bucket": "test"})
