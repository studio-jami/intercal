"""Redis queue adapter (default; compatible with Upstash, Redis, Valkey).

Requires: `intercal-shared[queue-redis]` (redis).

Implements a simple FIFO queue using Redis List operations:
- LPUSH  → enqueue (left push)
- BRPOPLPUSH → atomic dequeue + add to processing list (visibility-timeout pattern)
- LREM   → ack (remove from processing list)
- RPUSH  → nack (return to main queue from processing list)

This is intentionally minimal and well-suited for the pilot.  Swap for
a proper Streams / pgmq implementation if ordering guarantees or dead-letter
queues are required.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from intercal_shared.ports.queue import QueueError, QueueMessage
from intercal_shared.redaction import redact_url

_log = logging.getLogger(__name__)

_PROCESSING_SUFFIX = ":processing"


class RedisQueueAdapter:
    """QueuePort implementation backed by Redis List operations.

    Parameters
    ----------
    redis_url:
        Redis / Upstash / Valkey connection URL, e.g. ``redis://localhost:6379``.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        try:
            from redis.asyncio import Redis as AsyncRedis  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "redis is required for the Redis queue adapter. "
                "Install it with: pip install 'intercal-shared[queue-redis]'"
            ) from exc

        self._redis: Any = AsyncRedis.from_url(redis_url, decode_responses=True)
        _log.info("Redis queue adapter initialised (url=%s)", redact_url(redis_url))

    async def enqueue(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
    ) -> str:
        if delay_seconds > 0:
            # Simple delay: not implemented natively in List queues.
            # Use a Sorted Set with score=now+delay if delay is important.
            _log.warning(
                "RedisQueueAdapter: delay_seconds=%d ignored (not supported in List-based queue)",
                delay_seconds,
            )
        message_id = str(uuid.uuid4())
        envelope = json.dumps({"message_id": message_id, "payload": payload, "receive_count": 0})
        try:
            await self._redis.lpush(queue_name, envelope)
        except Exception as exc:
            raise QueueError(f"Redis enqueue failed on queue {queue_name!r}: {exc}") from exc
        return message_id

    async def dequeue(
        self,
        queue_name: str,
        *,
        max_messages: int = 1,
        visibility_timeout: int = 30,
    ) -> list[QueueMessage]:
        processing_key = queue_name + _PROCESSING_SUFFIX
        messages: list[QueueMessage] = []
        try:
            for _ in range(max_messages):
                raw = await self._redis.rpoplpush(queue_name, processing_key)
                if raw is None:
                    break
                try:
                    envelope: dict[str, Any] = json.loads(raw)
                    envelope["receive_count"] = envelope.get("receive_count", 0) + 1
                    messages.append(
                        QueueMessage(
                            message_id=envelope["message_id"],
                            receipt_handle=raw,  # use the serialised envelope as the handle
                            payload=envelope["payload"],
                            approximate_receive_count=envelope["receive_count"],
                        )
                    )
                except (json.JSONDecodeError, KeyError) as parse_exc:
                    _log.error("Malformed message in queue %r: %s", queue_name, parse_exc)
        except Exception as exc:
            raise QueueError(f"Redis dequeue failed on queue {queue_name!r}: {exc}") from exc
        return messages

    async def ack(self, queue_name: str, receipt_handle: str) -> None:
        processing_key = queue_name + _PROCESSING_SUFFIX
        try:
            await self._redis.lrem(processing_key, 1, receipt_handle)
        except Exception as exc:
            raise QueueError(f"Redis ack failed on queue {queue_name!r}: {exc}") from exc

    async def nack(self, queue_name: str, receipt_handle: str) -> None:
        processing_key = queue_name + _PROCESSING_SUFFIX
        try:
            removed = await self._redis.lrem(processing_key, 1, receipt_handle)
            if removed:
                await self._redis.lpush(queue_name, receipt_handle)
        except Exception as exc:
            raise QueueError(f"Redis nack failed on queue {queue_name!r}: {exc}") from exc
