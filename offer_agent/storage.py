"""Storage backend interface.

The spec requires saving through "the administrator-configured
authenticated organizational storage action" only — never personal
storage, email, local paths, public storage, anonymous links, or an
unapproved fallback, and never a public link or broadened permission.

No destination is defined here. A real deployment must plug in a
``StorageBackend`` implementation that talks to whatever authenticated
organizational storage the administrator has configured (e.g. a SharePoint
/ OneDrive / Google Drive connector reached through the platform the agent
runs on). If no such backend is configured, ``NotConfiguredStorageBackend``
is used and every call fails loudly, per "If no approved destination
exists or access fails, stop and report the storage error."
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class StorageError(RuntimeError):
    """Raised when the storage backend is not configured or a call fails."""


@dataclass
class StoredFile:
    filename: str
    secure_url: str
    destination_id: str


class StorageBackend(Protocol):
    """Contract a real organizational-storage connector must implement."""

    def exists(self, filename: str) -> bool:
        """True if a file with this name already exists at the destination."""
        ...

    def save(self, local_path: Path, filename: str) -> StoredFile:
        """Upload the local file and return its stored filename and secure URL.

        Implementations must use authenticated access and must never
        create a public/anonymous link or broaden sharing permissions.
        """
        ...

    def destination_identifier(self) -> str:
        """A non-sensitive label identifying the configured destination
        (e.g. a site/library name) for the audit record — never a raw
        path, credential, or connection string."""
        ...


class NotConfiguredStorageBackend:
    """Default backend: fails clearly instead of inventing a destination."""

    def exists(self, filename: str) -> bool:
        raise StorageError(
            "No administrator-configured authenticated organizational storage "
            "is set up. Stopping rather than falling back to local paths, "
            "personal storage, or a public link."
        )

    def save(self, local_path: Path, filename: str) -> StoredFile:
        raise StorageError(
            "No administrator-configured authenticated organizational storage "
            "is set up. Stopping rather than falling back to local paths, "
            "personal storage, or a public link."
        )

    def destination_identifier(self) -> str:
        raise StorageError("No storage backend is configured.")


class LocalDevStorageBackend:
    """Filesystem-backed stub for local development and automated tests only.

    This is NOT an approved organizational storage destination. Do not use
    it to satisfy the "authenticated organizational storage" requirement in
    a real deployment — swap in a real ``StorageBackend`` implementation
    (e.g. a SharePoint/OneDrive/Google Drive connector) before handling
    real candidate data.
    """

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def exists(self, filename: str) -> bool:
        return (self.directory / filename).exists()

    def save(self, local_path: Path, filename: str) -> StoredFile:
        destination = self.directory / filename
        if destination.exists():
            raise StorageError(f"Refusing to overwrite existing file: {filename}")
        destination.write_bytes(Path(local_path).read_bytes())
        return StoredFile(
            filename=filename,
            secure_url=f"file://{destination.resolve()}",
            destination_id=str(self.directory),
        )

    def destination_identifier(self) -> str:
        return f"local-dev:{self.directory.name}"
