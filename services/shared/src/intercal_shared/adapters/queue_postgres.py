"""Postgres-backed queue adapter (pgmq-style fallback).

Uses a single `intercal_queue` table in the same Postgres database.
No extra extensions required.  Suitable when Redis is unavailable or
for environments where a single-service setup is preferred.

Schema (must be applied via migration before use):

    CREATE TABLE IF NOT EXISTS intercal_queue (
        id             BIGSERIAL PRIMARY KEY,
        queue_name     TEXT        NOT NULL,
        message_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
        payload        JSONB       NOT NULL,
        enqueued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        visible_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        receive_count  INT         NOT NULL DEFAULT 0,
        processing     BOOLEAN     NOT NULL DEFAULT FALSE,
        processed_at   TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_intercal_queue_pop
        ON intercal_queue (queue_name, visible_at)
        WHERE NOT processing AND processed_at IS NULL;
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from intercal_shared.ports.queue import QueueError, QueueMessage

_log = logging.getLogger(__name__)


class PostgresQueueAdapter:
    """QueuePort implementation backed by a Postgres table.

    Parameters
    ----------
    pool:
        An asyncpg connection pool (obtained via ``db.get_pool()``).
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def enqueue(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
    ) -> str:
        visible_at = datetime.now(tz=UTC) + timedelta(seconds=delay_seconds)
        message_id = str(uuid.uuid4())
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO intercal_queue
                        (queue_name, message_id, payload, visible_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    queue_name,
                    message_id,
                    json.dumps(payload),
                    visible_at,
                )
        except Exception as exc:
            raise QueueError(f"Postgres enqueue failed on queue {queue_name!r}: {exc}") from exc
        return message_id

    async def dequeue(
        self,
        queue_name: str,
        *,
        max_messages: int = 1,
        visibility_timeout: int = 30,
    ) -> list[QueueMessage]:
        now = datetime.now(tz=UTC)
        visible_until = now + timedelta(seconds=visibility_timeout)
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    UPDATE intercal_queue
                    SET processing    = TRUE,
                        visible_at    = $4,
                        receive_count = receive_count + 1
                    WHERE id IN (
                        SELECT id FROM intercal_queue
                        WHERE queue_name = $1
                          AND visible_at <= $2
                          AND NOT processing
                          AND processed_at IS NULL
                        ORDER BY visible_at
                        LIMIT $3
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, message_id, payload, receive_count
                    """,
                    queue_name,
                    now,
                    max_messages,
                    visible_until,
                )
        except Exception as exc:
            raise QueueError(f"Postgres dequeue failed on queue {queue_name!r}: {exc}") from exc

        messages: list[QueueMessage] = []
        for row in rows:
            try:
                payload: dict[str, Any] = json.loads(row["payload"])
            except json.JSONDecodeError:
                payload = {}
            messages.append(
                QueueMessage(
                    message_id=str(row["message_id"]),
                    receipt_handle=str(row["id"]),
                    payload=payload,
                    approximate_receive_count=row["receive_count"],
                )
            )
        return messages

    async def ack(self, queue_name: str, receipt_handle: str) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE intercal_queue
                    SET processing   = FALSE,
                        processed_at = now()
                    WHERE id = $1 AND queue_name = $2
                    """,
                    int(receipt_handle),
                    queue_name,
                )
        except Exception as exc:
            raise QueueError(f"Postgres ack failed: {exc}") from exc

    async def nack(self, queue_name: str, receipt_handle: str) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE intercal_queue
                    SET processing = FALSE,
                        visible_at = now()
                    WHERE id = $1 AND queue_name = $2
                    """,
                    int(receipt_handle),
                    queue_name,
                )
        except Exception as exc:
            raise QueueError(f"Postgres nack failed: {exc}") from exc
