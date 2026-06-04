"""StoragePort — provider-agnostic object storage interface.

Implementations must not leak provider-specific types through these signatures.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StoragePort(Protocol):
    """Object storage port.

    All methods are async.  Implementations back this with S3/R2/MinIO.
    Provider-specific configuration (endpoint, credentials, bucket) is handled
    inside the adapter; nothing provider-specific crosses this boundary.
    """

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload *data* under *key*.

        Raises:
            StorageError: if the upload fails.
        """
        ...

    async def get(self, key: str) -> bytes:
        """Download the object at *key*.

        Raises:
            StorageNotFoundError: if *key* does not exist.
            StorageError: on other failures.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Return True if an object exists at *key*."""
        ...

    async def url(self, key: str, *, expires_in: int = 3600) -> str:
        """Return a pre-signed URL for *key* valid for *expires_in* seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Delete the object at *key* (idempotent — no error if absent)."""
        ...


class StorageError(Exception):
    """Raised by storage adapter on non-recoverable errors."""


class StorageNotFoundError(StorageError):
    """Raised when the requested key does not exist."""
