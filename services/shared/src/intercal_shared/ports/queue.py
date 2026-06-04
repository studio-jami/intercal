"""QueuePort — provider-agnostic message queue interface."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class QueuePort(Protocol):
    """Message queue port.

    Supports at-least-once delivery semantics: a dequeued message must be
    acknowledged (`ack`) to remove it from the queue, or it will be redelivered
    after the visibility timeout.
    """

    async def enqueue(
        self,
        queue_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
    ) -> str:
        """Enqueue *payload* onto *queue_name*.

        Args:
            queue_name: Logical queue name (adapter maps to a Redis key, Postgres table, etc.).
            payload: JSON-serialisable message body.
            delay_seconds: Seconds before the message becomes visible.

        Returns:
            A message ID string (provider-specific format, opaque to callers).

        Raises:
            QueueError: on backend failures.
        """
        ...

    async def dequeue(
        self,
        queue_name: str,
        *,
        max_messages: int = 1,
        visibility_timeout: int = 30,
    ) -> list[QueueMessage]:
        """Dequeue up to *max_messages* from *queue_name*.

        Returns an empty list when the queue is empty.

        Raises:
            QueueError: on backend failures.
        """
        ...

    async def ack(self, queue_name: str, receipt_handle: str) -> None:
        """Acknowledge and delete the message identified by *receipt_handle*.

        Raises:
            QueueError: on backend failures.
        """
        ...

    async def nack(self, queue_name: str, receipt_handle: str) -> None:
        """Negative-acknowledge *receipt_handle*: make it immediately re-deliverable.

        Raises:
            QueueError: on backend failures.
        """
        ...


class QueueMessage:
    """A dequeued message with opaque receipt handle for ack/nack."""

    __slots__ = ("approximate_receive_count", "message_id", "payload", "receipt_handle")

    def __init__(
        self,
        message_id: str,
        receipt_handle: str,
        payload: dict[str, Any],
        approximate_receive_count: int = 1,
    ) -> None:
        self.message_id = message_id
        self.receipt_handle = receipt_handle
        self.payload = payload
        self.approximate_receive_count = approximate_receive_count

    def __repr__(self) -> str:
        return f"QueueMessage(id={self.message_id!r}, receives={self.approximate_receive_count})"


class QueueError(Exception):
    """Raised by queue adapters on non-recoverable backend errors."""
