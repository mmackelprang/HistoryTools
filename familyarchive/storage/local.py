"""Local filesystem storage backend."""

from pathlib import Path
from .base import StorageBackend


class LocalStorage(StorageBackend):
    """Storage backend for local filesystem.

    All paths are relative to the root directory.
    """

    def __init__(self, root: str | Path):
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def read(self, path: str) -> bytes:
        return (self._root / path).read_bytes()

    def write(self, path: str, data: bytes) -> None:
        full_path = self._root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)

    def exists(self, path: str) -> bool:
        return (self._root / path).exists()

    def delete(self, path: str) -> None:
        full_path = self._root / path
        if full_path.exists():
            full_path.unlink()

    def list_files(self, prefix: str) -> list[str]:
        search_root = self._root / prefix if prefix else self._root
        if not search_root.exists():
            return []
        return [
            str(p.relative_to(self._root)).replace("\\", "/")
            for p in search_root.rglob("*")
            if p.is_file()
        ]

    def resolve(self, path: str) -> str | None:
        full_path = self._root / path
        if full_path.exists():
            return str(full_path.resolve())
        return None

    def is_reachable(self) -> bool:
        return self._root.exists()
