"""S3-compatible object storage adapter (MinIO locally, Cloudflare R2 / AWS S3 in prod).

Requires: `intercal-shared[storage-s3]` (aioboto3).

The adapter is fully async via aioboto3.  Path-style addressing is controlled
by `S3_FORCE_PATH_STYLE` (required for MinIO and most non-AWS endpoints).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from intercal_shared.ports.storage import StorageError, StorageNotFoundError

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)


class S3StorageAdapter:
    """StoragePort implementation backed by an S3-compatible object store.

    Parameters
    ----------
    endpoint_url:
        Full endpoint URL, e.g. ``http://localhost:9000`` for MinIO or
        ``https://<account>.r2.cloudflarestorage.com`` for Cloudflare R2.
    region:
        AWS region string; use ``"auto"`` for R2.
    bucket:
        Target bucket name.
    access_key_id / secret_access_key:
        Credentials.
    force_path_style:
        Set True for MinIO and R2; False for native AWS S3.
    """

    def __init__(
        self,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        *,
        force_path_style: bool = True,
    ) -> None:
        try:
            import aioboto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "aioboto3 is required for the S3 storage adapter. "
                "Install it with: pip install 'intercal-shared[storage-s3]'"
            ) from exc

        self._bucket = bucket
        self._session: Any = aioboto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        self._endpoint_url = endpoint_url
        self._force_path_style = force_path_style

    def _client(self) -> Any:
        """Return a context-managed S3 client."""
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            config=self._make_config(),
        )

    def _make_config(self) -> Any:
        from botocore.config import Config  # type: ignore[import-untyped]

        return Config(s3={"addressing_style": "path" if self._force_path_style else "virtual"})

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = metadata
        try:
            async with self._client() as s3:
                await s3.put_object(**kwargs)
            _log.debug("Stored object s3://%s/%s (%d bytes)", self._bucket, key, len(data))
        except Exception as exc:
            raise StorageError(f"S3 put failed for key {key!r}: {exc}") from exc

    async def get(self, key: str) -> bytes:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                return await response["Body"].read()  # type: ignore[no-any-return]
        except Exception as exc:
            msg = str(exc)
            if "NoSuchKey" in msg or "404" in msg:
                raise StorageNotFoundError(f"Object not found: s3://{self._bucket}/{key}") from exc
            raise StorageError(f"S3 get failed for key {key!r}: {exc}") from exc

    async def exists(self, key: str) -> bool:
        try:
            async with self._client() as s3:
                await s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:
            if "404" in str(exc) or "NoSuchKey" in str(exc) or "Not Found" in str(exc):
                return False
            raise StorageError(f"S3 head_object failed for key {key!r}: {exc}") from exc

    async def url(self, key: str, *, expires_in: int = 3600) -> str:
        try:
            async with self._client() as s3:
                return await s3.generate_presigned_url(  # type: ignore[no-any-return]
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
        except Exception as exc:
            raise StorageError(f"S3 presign failed for key {key!r}: {exc}") from exc

    async def delete(self, key: str) -> None:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"S3 delete failed for key {key!r}: {exc}") from exc
