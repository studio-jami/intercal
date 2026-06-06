"""Asyncpg connection pool factory and thin repository base.

Usage
-----
    from intercal_shared.db import get_pool, BaseRepository

    pool = await get_pool(settings.database_url)
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM sources")

    await pool.close()

The module holds a single module-level pool keyed by DSN so tests can share
a pool without leaking connections across the test suite.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from intercal_shared.redaction import redact_url

_log = logging.getLogger(__name__)

# Global pool registry — avoids creating redundant pools during a process lifetime.
_pools: dict[str, asyncpg.Pool] = {}  # type: ignore[type-arg]
_pool_lock = asyncio.Lock()


async def get_pool(
    dsn: str,
    *,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 30.0,
) -> asyncpg.Pool:  # type: ignore[type-arg]
    """Return (and cache) an asyncpg connection pool for *dsn*.

    Thread-safe under the module-level asyncio.Lock.  Multiple callers with
    the same *dsn* share one pool.
    """
    async with _pool_lock:
        if dsn not in _pools:
            _log.info(
                "Creating asyncpg pool for %s (min=%d max=%d)",
                redact_url(dsn),
                min_size,
                max_size,
            )
            pool: asyncpg.Pool = await asyncpg.create_pool(  # type: ignore[type-arg]
                dsn=dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
            )
            _pools[dsn] = pool
        return _pools[dsn]


async def close_all_pools() -> None:
    """Close every cached pool — call on application shutdown or in test teardown."""
    async with _pool_lock:
        for dsn, pool in list(_pools.items()):
            await pool.close()
            _log.info("Closed asyncpg pool for %s", redact_url(dsn))
        _pools.clear()


class BaseRepository:
    """Thin base for all repository classes.

    Subclasses receive a pool on construction and can call `_conn()` to
    acquire a connection from the pool as an async context manager.

    Example
    -------
        class SourceRepository(BaseRepository):
            async def get_by_id(self, source_id: str) -> asyncpg.Record | None:
                async with self._conn() as conn:
                    return await conn.fetchrow(
                        "SELECT * FROM sources WHERE id = $1", source_id
                    )
    """

    def __init__(self, pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        self._pool = pool

    def _conn(self) -> _PoolConnectionContext:
        """Acquire a connection from the pool as an async context manager."""
        return _PoolConnectionContext(self._pool)

    async def execute(self, query: str, *args: Any) -> str:
        """Execute *query* and return its status string."""
        async with self._conn() as conn:
            return await conn.execute(query, *args)  # type: ignore[no-any-return]

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:  # type: ignore[type-arg]
        """Fetch all rows for *query*."""
        async with self._conn() as conn:
            return await conn.fetch(query, *args)  # type: ignore[no-any-return]

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:  # type: ignore[type-arg]
        """Fetch at most one row for *query*."""
        async with self._conn() as conn:
            return await conn.fetchrow(query, *args)  # type: ignore[no-any-return]

    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        """Fetch a single value from the first row of *query*."""
        async with self._conn() as conn:
            return await conn.fetchval(query, *args, column=column)


class _PoolConnectionContext:
    """Private async context manager that acquires / releases a pool connection."""

    def __init__(self, pool: asyncpg.Pool) -> None:  # type: ignore[type-arg]
        self._pool = pool
        self._conn: Any = None

    async def __aenter__(self) -> asyncpg.Connection:  # type: ignore[type-arg]
        self._conn = await self._pool.acquire()
        return self._conn  # type: ignore[return-value]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            await self._pool.release(self._conn)
