"""Synthesis job functions.

Every job is:
- An async function accepting typed keyword arguments.
- Idempotent: re-running must not produce duplicate digests, duplicate freshness
  scores, or double-fire notifications.
- Invocable from the CLI or by the scheduler adapter.

Design principles:
- Digests are delivery artifacts (cached agent-facing synthesis), not canonical facts.
- Token budgets constrain digest size; citations and provenance must be preserved.
- Freshness scores are derived from the knowledge graph, not from external signals.
- Subscribers are notified at most once per knowledge-change event.
"""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# build_digest
# ──────────────────────────────────────────────────────────────────────────────


async def build_digest(
    *,
    topic_or_entity_id: str,
    since_date: str,
    token_budget: int = 1024,
    pool: Any,
    llm: Any,
    storage: Any,
) -> str:
    """Generate and cache a token-budgeted digest for a topic or entity.

    Idempotent: if a valid unexpired digest exists for the same
    (topic_or_entity_id, since_date, token_budget) key, return it from cache
    without calling the LLM again.

    Steps:
    1. Check `digests` cache for a valid unexpired entry.
    2. If cache miss: query fact versions and claims for the topic/entity since *since_date*.
    3. Call `llm.complete()` with the retrieved evidence and token budget.
    4. Persist the digest to object storage under ``digests/<digest_id>``.
    5. Insert a `digests` row pointing at the storage object.
    6. Return the digest text.

    Args:
        topic_or_entity_id: UUID of the topic or entity to synthesise.
        since_date: ISO-8601 date string; include changes since this date.
        token_budget: Maximum tokens for the digest output.
        pool: asyncpg connection pool.
        llm: LlmPort adapter for synthesis.
        storage: StoragePort for caching digest objects.

    Returns:
        The digest text.

    Raises:
        NotImplementedError: Evidence assembly, LLM synthesis prompt, token
            budgeting, and cache persistence are Plan-02 scope.
    """
    _log.info(
        "build_digest: id=%s since=%s budget=%d", topic_or_entity_id, since_date, token_budget
    )
    raise NotImplementedError(
        "Plan 02 — build_digest: evidence assembly from fact_versions/claims, "
        "LLM synthesis prompt, token budgeting, and digest cache not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# recompute_freshness
# ──────────────────────────────────────────────────────────────────────────────


async def recompute_freshness(
    *,
    topic_or_entity_id: str,
    pool: Any,
) -> float:
    """Recompute the freshness score for a topic or entity.

    Idempotent: always overwrites the stored freshness score.

    Freshness factors (formula is Plan-02 tuning):
    - Time since most recent fact version for the entity/topic.
    - Number of new claims since last digest.
    - Source health scores of contributing sources.
    - Subscription demand (higher demand → higher refresh priority).

    Args:
        topic_or_entity_id: UUID of the topic or entity to score.
        pool: asyncpg connection pool.

    Returns:
        The computed freshness score (0.0-1.0).

    Raises:
        NotImplementedError: Freshness formula and `topics.freshness_score`
            column require Plan-02 schema migration.
    """
    _log.info("recompute_freshness: id=%s", topic_or_entity_id)
    raise NotImplementedError(
        "Plan 02 — recompute_freshness: freshness formula and DB column not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# notify_subscribers
# ──────────────────────────────────────────────────────────────────────────────


async def notify_subscribers(
    *,
    entity_or_topic_id: str,
    pool: Any,
    queue: Any,
) -> int:
    """Enqueue notifications for all active subscribers watching *entity_or_topic_id*.

    Idempotent: each knowledge-change event should produce at most one
    notification per subscription.  A `notified_at` timestamp on the
    subscription or an outbox event record prevents double-firing.

    Steps:
    1. Query `subscriptions` for active subscribers watching the target.
    2. For each subscriber, check whether a notification for the latest
       knowledge change has already been enqueued.
    3. Enqueue outstanding notifications onto the queue.
    4. Record notification events in an outbox table.

    Args:
        entity_or_topic_id: UUID of the entity or topic that changed.
        pool: asyncpg connection pool.
        queue: QueuePort for enqueueing notification events.

    Returns:
        Number of notifications enqueued.

    Raises:
        NotImplementedError: Subscription matching, outbox pattern, and
            webhook/polling dispatch are Plan-02 scope.
    """
    _log.info("notify_subscribers: id=%s", entity_or_topic_id)
    raise NotImplementedError(
        "Plan 02 — notify_subscribers: subscription matching, outbox deduplication, "
        "and webhook/polling dispatch not yet implemented."
    )
