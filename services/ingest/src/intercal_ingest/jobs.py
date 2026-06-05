"""Ingestion job functions.

Every job is:
- An async function accepting typed keyword arguments.
- Idempotent: re-running on already-processed input must not duplicate records.
- Invocable from the CLI (``python -m intercal_ingest <job>``) or by the
  scheduler adapter (``await scheduler.run_now(job_fn, **kwargs)``).
- Deployed via GitHub Actions scheduled workflows or Cloud Run Jobs —
  all of which call the same CLI entrypoints.

W1 (Plan 02) scope: ``ingest_source`` and ``score_source_health`` are fully
implemented.  ``normalize_document`` and ``cleanup_expired_cache`` remain
``NotImplementedError`` stubs awaiting their workstream bodies (W2 and later).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import uuid
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
    max_documents: int = 200,
    registry: Any | None = None,
) -> dict[str, int]:
    """Fetch and persist raw documents for *source_id*.

    Idempotent: documents with a matching content_hash are skipped via
    ``ON CONFLICT (content_hash) DO NOTHING``.

    Steps:
    1. Load source config from ``sources`` table; validate it is active.
    2. Look up the adapter in the source registry by ``adapter_name``.
    3. Create an ``ingestion_runs`` row (status=running).
    4. For each document yielded by the adapter:
       a. Compute SHA-256 of raw content bytes.
       b. ``INSERT INTO source_documents … ON CONFLICT DO NOTHING``.
       c. If newly inserted and storage is available, persist raw bytes under
          ``raw/<source_id>/<content_hash>``.
    5. Update ``sources.last_run_at`` and ``ingestion_runs`` to succeeded/failed.

    Args:
        source_id: UUID of the source record to ingest.
        pool: asyncpg connection pool.
        storage: StoragePort implementation (or None to skip raw archival).
        http_client: Optional httpx.AsyncClient for HTTP sources.
        max_documents: Hard cap overriding INGEST_MAX_DOCS_PER_RUN for this call.
        registry: SourceRegistry to use.  If None the module-level singleton is used.

    Returns:
        Dict with counters: ``fetched``, ``new``, ``skipped``, ``errors``.

    Raises:
        ValueError: If the source row is missing or inactive.
        SourceFetchError: On non-retryable adapter fetch failures (run is
            recorded as failed before re-raising).
    """
    from intercal_shared.ports.source import SourceFetchError
    from intercal_shared.source_registry import registry as _default_registry

    _reg = registry if registry is not None else _default_registry
    if not _reg.all_names():
        _reg.register_all_defaults()

    _log.info("ingest_source: source_id=%s max_documents=%d", source_id, max_documents)

    # ── 1. Load source row ───────────────────────────────────────────────────
    source_row = await pool.fetchrow(
        "SELECT id, slug, adapter_name, adapter_config, is_active, is_paused, "
        "       redistribution_allowed, citation_only, rate_limit_requests_per_minute "
        "FROM sources WHERE id = $1",
        uuid.UUID(source_id),
    )
    if source_row is None:
        raise ValueError(f"Source not found: {source_id!r}")
    if not source_row["is_active"]:
        raise ValueError(f"Source {source_id!r} ({source_row['slug']!r}) is inactive")
    if source_row["is_paused"]:
        _log.info(
            "ingest_source: source %r (%r) is paused; skipping",
            source_id,
            source_row["slug"],
        )
        return {"fetched": 0, "new": 0, "skipped": 0, "errors": 0}

    adapter_name: str = source_row["adapter_name"]
    adapter_config_raw = source_row["adapter_config"]
    adapter_config: dict[str, object] = (
        dict(adapter_config_raw)
        if isinstance(adapter_config_raw, dict)
        else json.loads(adapter_config_raw)
        if isinstance(adapter_config_raw, str)
        else {}
    )
    redistribution_allowed: bool = bool(source_row["redistribution_allowed"])
    citation_only: bool = bool(source_row["citation_only"])

    # ── 2. Look up adapter ────────────────────────────────────────────────────
    adapter = _reg.get(adapter_name)

    # ── 3. Read last cursor state from most-recent run ────────────────────────
    last_run_row = await pool.fetchrow(
        "SELECT cursor_state FROM ingestion_runs "
        "WHERE source_id = $1 AND status = 'succeeded' "
        "ORDER BY started_at DESC LIMIT 1",
        uuid.UUID(source_id),
    )
    cursor_state: dict[str, object] | None = None
    if last_run_row and last_run_row["cursor_state"]:
        raw_cs = last_run_row["cursor_state"]
        cursor_state = (
            dict(raw_cs)
            if isinstance(raw_cs, dict)
            else json.loads(raw_cs)
            if isinstance(raw_cs, str)
            else None
        )

    # ── 4. Create ingestion_run row ───────────────────────────────────────────
    run_id: uuid.UUID = await pool.fetchval(
        """
        INSERT INTO ingestion_runs
            (source_id, status, started_at, trigger)
        VALUES ($1, 'running', now(), 'scheduled')
        RETURNING id
        """,
        uuid.UUID(source_id),
    )
    _log.info("ingest_source: run_id=%s adapter=%r", run_id, adapter_name)

    counters = {"fetched": 0, "new": 0, "skipped": 0, "errors": 0}
    # Mutable sink the adapter fills with the pagination token to resume from.
    final_cursor: dict[str, object] = dict(cursor_state) if cursor_state else {}
    run_error: str | None = None

    try:
        async for doc in adapter.fetch(
            adapter_config=adapter_config,
            cursor_state=cursor_state,
            max_documents=max_documents,
            http_client=http_client,
            cursor_sink=final_cursor,
        ):
            counters["fetched"] += 1
            content_hash = _sha256(doc.content)
            cleaned_text = (
                # For citation_only sources we don't persist full text;
                # store None and let normalization decide later (W2).
                None if citation_only else doc.content.decode("utf-8", errors="replace")
            )
            content_length = len(cleaned_text.encode("utf-8")) if cleaned_text is not None else None

            # ── Upsert source_document row ─────────────────────────────────────
            # Insert first so ON CONFLICT tells us whether this content is new;
            # only new content triggers an object-storage write (avoids redundant
            # R2 puts on every duplicate — see docs/operations/resource-budget.md).
            try:
                new_id = await pool.fetchval(
                    """
                    INSERT INTO source_documents (
                        source_id, ingestion_run_id,
                        content_hash, external_id, url, title, language,
                        published_at, cleaned_text, content_length,
                        document_type, redistribution_allowed, citation_only,
                        metadata
                    ) VALUES (
                        $1, $2,
                        $3, $4, $5, $6, $7,
                        $8, $9, $10,
                        $11, $12, $13,
                        $14::jsonb
                    )
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING id
                    """,
                    uuid.UUID(source_id),
                    run_id,
                    content_hash,
                    doc.external_id,
                    doc.url,
                    doc.title,
                    doc.language,
                    _parse_timestamp(doc.published_at),
                    cleaned_text,
                    content_length,
                    _infer_document_type(doc),
                    redistribution_allowed,
                    citation_only,
                    json.dumps(dict(doc.metadata)),
                )
            except Exception as db_exc:
                _log.warning(
                    "ingest_source: DB insert failed for hash=%s: %s",
                    content_hash,
                    db_exc,
                )
                counters["errors"] += 1
                continue

            if new_id is None:
                # ON CONFLICT — document already exists.
                counters["skipped"] += 1
                _log.debug(
                    "ingest_source: skipped duplicate hash=%s external_id=%s",
                    content_hash,
                    doc.external_id,
                )
                continue

            counters["new"] += 1

            # ── Persist raw bytes for new docs only (if storage + redistribution
            #    allowed), then record the resulting key on the document row. ──
            if storage is not None and redistribution_allowed:
                storage_key = f"raw/{source_id}/{content_hash}"
                try:
                    await storage.put(
                        storage_key,
                        doc.content,
                        content_type=doc.content_type,
                        metadata={
                            "source_id": source_id,
                            "content_hash": content_hash,
                            "adapter": adapter_name,
                        },
                    )
                    await pool.execute(
                        "UPDATE source_documents SET raw_storage_key = $2 WHERE id = $1",
                        new_id,
                        storage_key,
                    )
                    _log.debug("ingest_source: stored raw bytes at %s", storage_key)
                except Exception as stor_exc:
                    _log.warning(
                        "ingest_source: storage.put failed for key %s: %s",
                        storage_key,
                        stor_exc,
                    )
                    # Storage failure is non-fatal: the document row already exists
                    # with raw_storage_key NULL, so a later run can backfill it.

        # ── Update run: succeeded ─────────────────────────────────────────────
        await pool.execute(
            """
            UPDATE ingestion_runs SET
                status = 'succeeded',
                finished_at = now(),
                documents_fetched = $2,
                documents_new = $3,
                documents_skipped = $4,
                documents_error = $5,
                cursor_state = $6::jsonb
            WHERE id = $1
            """,
            run_id,
            counters["fetched"],
            counters["new"],
            counters["skipped"],
            counters["errors"],
            json.dumps(final_cursor) if final_cursor else None,
        )
        _log.debug("ingest_source: persisted cursor_state=%s", final_cursor or None)

        # Update source last_run_at + reset consecutive_failures on success.
        await pool.execute(
            """
            UPDATE sources SET
                last_run_at = now(),
                next_run_at = NULL,
                consecutive_failures = 0
            WHERE id = $1
            """,
            uuid.UUID(source_id),
        )

    except SourceFetchError as fetch_exc:
        run_error = str(fetch_exc)
        _log.error("ingest_source: adapter fetch error: %s", run_error)
        await _mark_run_failed(pool, run_id, counters, run_error)
        await _increment_consecutive_failures(pool, source_id)
        raise

    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        _log.error("ingest_source: unexpected error: %s", run_error, exc_info=True)
        await _mark_run_failed(pool, run_id, counters, run_error)
        await _increment_consecutive_failures(pool, source_id)
        raise

    _log.info(
        "ingest_source: completed source_id=%s run_id=%s %s",
        source_id,
        run_id,
        counters,
    )
    return counters


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

    Idempotent: if ``source_documents.normalized_at`` is already set the
    document is skipped unless forced.

    Raises:
        NotImplementedError: Text normalisation pipeline (language detection,
            boilerplate stripping, chunking strategy) is Plan-02 W2 scope.
    """
    _log.info("normalize_document: document_id=%s", document_id)
    raise NotImplementedError(
        "Plan 02 W2 — normalize_document: language detection, boilerplate removal, "
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
) -> float:
    """Recompute and persist the health score for *source_id*.

    Idempotent: always overwrites ``sources.reliability_score`` with the
    freshly computed value.

    Scoring formula (0.0-1.00):
    - Base score = fraction of runs that succeeded in the lookback window.
    - Penalty for consecutive failure streak (-0.10 per failure, floored at 0).
    - If no runs exist in the window, returns ``None`` (score unchanged).

    Args:
        source_id: UUID of the source to score.
        pool: asyncpg connection pool.
        lookback_days: How many days of run history to consider.

    Returns:
        The computed score (0.0-1.0), or -1.0 if no recent run data exists.
    """
    _log.info(
        "score_source_health: source_id=%s lookback_days=%d",
        source_id,
        lookback_days,
    )

    # Query run history in the lookback window.
    runs = await pool.fetch(
        """
        SELECT status
        FROM ingestion_runs
        WHERE source_id = $1
          AND started_at >= now() - ($2 || ' days')::interval
        ORDER BY started_at DESC
        """,
        uuid.UUID(source_id),
        str(lookback_days),
    )

    if not runs:
        _log.info(
            "score_source_health: no runs found for source_id=%s in last %d days; "
            "skipping score update",
            source_id,
            lookback_days,
        )
        return -1.0

    total = len(runs)
    succeeded = sum(1 for r in runs if r["status"] == "succeeded")
    base_score = succeeded / total if total > 0 else 0.0

    # Apply streak penalty.
    consecutive_failures_row = await pool.fetchrow(
        "SELECT consecutive_failures FROM sources WHERE id = $1",
        uuid.UUID(source_id),
    )
    streak = (
        int(consecutive_failures_row["consecutive_failures"]) if consecutive_failures_row else 0
    )
    penalty = min(streak * 0.10, base_score)  # Don't go negative.
    score = round(max(0.0, base_score - penalty), 2)

    # Persist.
    await pool.execute(
        "UPDATE sources SET reliability_score = $2, updated_at = now() WHERE id = $1",
        uuid.UUID(source_id),
        score,
    )
    _log.info(
        "score_source_health: source_id=%s score=%.2f (base=%.2f streak=%d)",
        source_id,
        score,
        base_score,
        streak,
    )
    return score


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

    Raises:
        NotImplementedError: ``digests.expires_at`` TTL logic and object-
            storage cleanup belong to a later workstream (W2/Plan 03 synthesis).
    """
    _log.info("cleanup_expired_cache: max_age_days=%d", max_age_days)
    raise NotImplementedError(
        "Plan 02 / Plan 03 — cleanup_expired_cache: digest TTL logic not yet implemented. "
        "Implement after the digests table is populated by the synthesis workstream."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data* (used for content-hashing documents)."""
    return hashlib.sha256(data).hexdigest()


def _parse_timestamp(value: str | None) -> _dt.datetime | None:
    """Parse an adapter's ISO-8601 ``published_at`` string into an aware datetime.

    asyncpg binds ``timestamptz`` parameters from ``datetime`` objects, not
    strings (the ``::timestamptz`` cast in the query does not coerce a bound
    ``str``).  Adapters emit RFC 3339 / ISO-8601 strings, commonly with a
    trailing ``Z``; we normalise that to ``+00:00`` for ``fromisoformat``.
    Returns ``None`` for empty/unparseable values so ingestion never fails on a
    malformed source timestamp.
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        _log.debug("ingest_source: unparseable published_at %r; storing NULL", value)
        return None


def _infer_document_type(doc: Any) -> str:
    """Return a best-guess ``document_type`` string from adapter metadata."""
    adapter = (doc.metadata or {}).get("adapter", "")
    if "wikidata" in adapter:
        return "api_record"
    if "github" in adapter:
        return "release_notes"
    return "article"


async def _mark_run_failed(
    pool: Any,
    run_id: uuid.UUID,
    counters: dict[str, int],
    error_message: str,
) -> None:
    """Update ingestion_run to failed status."""
    try:
        await pool.execute(
            """
            UPDATE ingestion_runs SET
                status = 'failed',
                finished_at = now(),
                documents_fetched = $2,
                documents_new = $3,
                documents_skipped = $4,
                documents_error = $5,
                error_message = $6
            WHERE id = $1
            """,
            run_id,
            counters.get("fetched", 0),
            counters.get("new", 0),
            counters.get("skipped", 0),
            counters.get("errors", 0),
            error_message[:2000],
        )
    except Exception as exc:
        _log.error("_mark_run_failed: could not update run row: %s", exc)


async def _increment_consecutive_failures(pool: Any, source_id: str) -> None:
    """Increment ``sources.consecutive_failures`` by 1."""
    try:
        await pool.execute(
            "UPDATE sources SET consecutive_failures = consecutive_failures + 1, "
            "updated_at = now() WHERE id = $1",
            uuid.UUID(source_id),
        )
    except Exception as exc:
        _log.error("_increment_consecutive_failures: %s", exc)
