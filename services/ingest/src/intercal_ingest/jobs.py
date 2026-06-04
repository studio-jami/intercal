"""Ingestion job functions.

Every job is:
- An async function accepting typed keyword arguments.
- Idempotent: re-running on already-processed input must not duplicate records.
- Invocable from the CLI (``python -m intercal_ingest <job>``) or by the
  scheduler adapter (``await scheduler.run_now(job_fn, **kwargs)``).
- Deployed via GitHub Actions scheduled workflows, Modal, or VPS cron — all
  of which call the same CLI entrypoints.

Jobs that require deep algorithm work beyond the current foundation scope
raise ``NotImplementedError`` with a message identifying the Plan-02 work
remaining.  Jobs whose infrastructure wiring is complete are fully implemented.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

_log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# ingest_source
# ──────────────────────────────────────────────────────────────────────────────


async def ingest_source(
    *,
    source_id: str,
    pool: Any,
    storage: Any,
    http_client: Any | None = None,
) -> None:
    """Fetch and persist raw documents for *source_id*.

    Idempotent: documents with a matching content hash are skipped.

    Steps:
    1. Load source config from `sources` table.
    2. Dispatch to the appropriate source adapter (RSS, API, dump, …).
    3. For each fetched document:
       a. Compute SHA-256 content hash.
       b. Insert into `source_documents` with ON CONFLICT DO NOTHING.
       c. Persist raw bytes to object storage under ``raw/<source_id>/<hash>``.
    4. Record the ingestion run in `ingestion_runs`.

    Args:
        source_id: UUID of the source record to ingest.
        pool: asyncpg connection pool.
        storage: StoragePort implementation.
        http_client: Optional httpx.AsyncClient for HTTP sources.

    Raises:
        NotImplementedError: Source adapter dispatch (per-adapter fetch logic)
            is Plan-02 scope.  The infrastructure wiring (hash, upsert,
            run record) is fully stubbed and ready for adapter injection.
    """
    _log.info("ingest_source: source_id=%s", source_id)
    raise NotImplementedError(
        "Plan 02 — ingest_source: per-adapter fetch logic (RSS, Wikidata, GitHub, "
        "arXiv, etc.) not yet implemented.  Infrastructure stubs (hash, upsert, "
        "run_record) are ready.  See services/ingest/src/intercal_ingest/jobs.py."
    )


# ──────────────────────────────────────────────────────────────────────────────
# normalize_document
# ──────────────────────────────────────────────────────────────────────────────


async def normalize_document(
    *,
    document_id: str,
    pool: Any,
    storage: Any,
) -> None:
    """Normalise a raw source document into clean text and structured metadata.

    Idempotent: if `source_documents.normalized_at` is already set the
    document is skipped unless forced.

    Steps:
    1. Load raw content from object storage.
    2. Apply language detection, boilerplate removal, and Unicode normalisation.
    3. Chunk the cleaned text into `document_chunks` rows.
    4. Update `source_documents.normalized_text` and `normalized_at`.

    Args:
        document_id: UUID of the `source_documents` row.
        pool: asyncpg connection pool.
        storage: StoragePort implementation.

    Raises:
        NotImplementedError: Text normalisation pipeline (language detection,
            boilerplate stripping, chunking strategy) is Plan-02 scope.
    """
    _log.info("normalize_document: document_id=%s", document_id)
    raise NotImplementedError(
        "Plan 02 — normalize_document: language detection, boilerplate removal, "
        "and chunk splitting not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# score_source_health
# ──────────────────────────────────────────────────────────────────────────────


async def score_source_health(
    *,
    source_id: str,
    pool: Any,
    lookback_days: int = 7,
) -> None:
    """Recompute the health score for *source_id* from recent ingestion run history.

    Idempotent: always overwrites `sources.health_score` with the freshly
    computed value.

    Health score factors (all Plan-02 tuning):
    - Fraction of successful runs in the lookback window.
    - Mean document count per run.
    - Consecutive failure streak.

    Args:
        source_id: UUID of the source to score.
        pool: asyncpg connection pool.
        lookback_days: How many days of run history to consider.

    Raises:
        NotImplementedError: Scoring formula and `sources.health_score` column
            require the Plan-02 schema migration to be applied first.
    """
    _log.info("score_source_health: source_id=%s lookback_days=%d", source_id, lookback_days)
    raise NotImplementedError(
        "Plan 02 — score_source_health: scoring formula and DB column not yet implemented."
    )


# ──────────────────────────────────────────────────────────────────────────────
# cleanup_expired_cache
# ──────────────────────────────────────────────────────────────────────────────


async def cleanup_expired_cache(
    *,
    pool: Any,
    storage: Any,
    max_age_days: int = 30,
) -> None:
    """Delete expired digest cache entries and their associated storage objects.

    Idempotent: safe to run repeatedly; already-deleted entries are simply not found.

    Steps:
    1. Query `digests` for rows where `expires_at < now()`.
    2. Delete the corresponding storage object under ``digests/<digest_id>``.
    3. Delete the `digests` row.

    Args:
        pool: asyncpg connection pool.
        storage: StoragePort implementation.
        max_age_days: Fallback TTL for digests with no explicit `expires_at`.

    Raises:
        NotImplementedError: `digests` table and `expires_at` column require the
            Plan-02 schema migration to be applied first.
    """
    _log.info("cleanup_expired_cache: max_age_days=%d", max_age_days)
    raise NotImplementedError(
        "Plan 02 — cleanup_expired_cache: digests table not yet created; "
        "implement after Plan-02 schema migration."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:  # pyright: ignore[reportUnusedFunction]
    """Return the SHA-256 hex digest of *data* (used for content-hashing documents)."""
    return hashlib.sha256(data).hexdigest()
