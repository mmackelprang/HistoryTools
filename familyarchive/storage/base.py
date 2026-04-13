"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Interface for archive file storage.

    All paths are relative to the storage root (e.g., "Letters/letter.pdf").
    Implementations handle the actual I/O (local disk, S3, etc.).
    """

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read a file and return its contents as bytes."""

    @abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Write data to a file, creating parent directories as needed."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check whether a file exists."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete a file. No error if it doesn't exist."""

    @abstractmethod
    def list_files(self, prefix: str) -> list[str]:
        """List files under a prefix, returning relative paths."""

    @abstractmethod
    def resolve(self, path: str) -> str | None:
        """Resolve to an absolute path or URL for direct access.

        Returns None if the file doesn't exist or the source is unreachable.
        For local storage: returns filesystem path.
        For S3: returns a presigned URL.
        """

    @abstractmethod
    def is_reachable(self) -> bool:
        """Check whether the storage backend is accessible.

        For local: checks if root directory exists.
        For S3: checks if bucket is accessible.
        """
