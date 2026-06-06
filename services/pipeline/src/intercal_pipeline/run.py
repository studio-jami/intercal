"""Pipeline orchestrator — Plan 02 W8.

``run_pipeline`` chains the workers in stage order:

  ingest_source → normalize_document → extract_mentions → extract_claims
  → embed_chunks → embed_claims → resolve_entities → link_claim_entities
  → derive_relationships (per linked claim) → write_fact_versions (per entity)

Design constraints:
- Idempotent end-to-end: every stage is individually idempotent; re-running
  the whole pipeline does not duplicate canonical records.
- Resumable: if a stage fails the run is recorded as ``failed``; re-running
  picks up from where each idempotent stage left it (normalize skips already-
  normalised docs, resolve skips already-resolved mentions, etc.).
- Resource-budget aware: respects ``INGEST_MAX_DOCS_PER_RUN``,
  ``LLM_DAILY_REQUEST_BUDGET``, ``EXTRACT_ONLY_CHANGED``.
- Stage failure isolation: a single-document failure is non-fatal (logged,
  counted in the run health summary); the stage continues with the next item.
- Later-plan work left explicit: ``compute_freshness``, ``synthesize_digest``,
  and ``dispatch_subscriptions`` are ``NotImplementedError`` stubs per the
  plan assignment below.

Synthesis stubs (Plan 03 / Plan 04):
  ``compute_freshness``      — Plan 03
  ``synthesize_digest``      — Plan 03
  ``dispatch_subscriptions`` — Plan 04
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import uuid
from typing import Any

# Cross-service stage functions — imported at module level so tests can patch
# them via ``patch("intercal_pipeline.run.<name>")``.
from intercal_extract.jobs import embed_chunks, embed_claims, extract_claims, extract_mentions
from intercal_ingest.jobs import ingest_source, normalize_document
from intercal_resolve.jobs import (
    derive_relationships,
    link_claim_entities,
    resolve_entities,
    write_fact_versions,
)

_log = logging.getLogger(__name__)

# Safety cap on the resolve/link draining loops.  Each iteration consumes one
# batch (default 100-200 rows); 2000 iterations covers ~200k-400k pending rows
# per run — far above any single budget-bounded ingest — while guaranteeing
# termination if a stage ever fails to make progress.
_MAX_DRAIN_ITERATIONS = 2000


# ──────────────────────────────────────────────────────────────────────────────
# Run health summary
# ──────────────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class PipelineRunHealth:
    """Counters and timing for a single pipeline run."""

    run_id: str
    source_id: str
    started_at: datetime.datetime
    finished_at: datetime.datetime | None = None

    # Stage counters
    docs_fetched: int = 0
    docs_new: int = 0
    docs_skipped_ingest: int = 0
    docs_policy_blocked: int = 0
    docs_normalized: int = 0
    docs_skipped_normalize: int = 0
    mentions_extracted: int = 0
    claims_extracted: int = 0
    docs_skipped_extract: int = 0
    chunks_embedded: int = 0
    claims_embedded: int = 0
    entities_created: int = 0
    entities_merged: int = 0
    review_candidates: int = 0
    claims_linked: int = 0
    relationships_written: int = 0
    relationships_skipped: int = 0
    fact_versions_written: int = 0
    fact_versions_skipped: int = 0

    # Error counts per stage
    errors_ingest: int = 0
    errors_normalize: int = 0
    errors_extract: int = 0
    errors_embed: int = 0
    errors_resolve: int = 0
    errors_derive: int = 0
    errors_version: int = 0

    status: str = "running"  # running | succeeded | failed | partial
    mode: str = "scheduled"
    source_slug: str | None = None
    source_class: str | None = None
    backfill_start_date: str | None = None
    backfill_end_date: str | None = None

    def finish(self, *, status: str = "succeeded") -> None:
        self.finished_at = datetime.datetime.now(tz=datetime.UTC)
        self.status = status

    def to_dict(self) -> dict[str, object]:
        d = dataclasses.asdict(self)
        # Serialize datetimes to ISO strings for JSON/logging
        for k in ("started_at", "finished_at"):
            if isinstance(d[k], datetime.datetime):
                d[k] = d[k].isoformat()
        return d


# ──────────────────────────────────────────────────────────────────────────────
# Later-plan stubs (explicit NotImplementedError)
# ──────────────────────────────────────────────────────────────────────────────


async def compute_freshness(*, entity_id: str, pool: Any) -> None:
    """Recompute entity freshness score.

    Raises:
        NotImplementedError: Freshness formula and ``topics.freshness_score``
            column are Plan 03 scope.
    """
    raise NotImplementedError(
        "Plan 03 — compute_freshness: freshness formula and topics.freshness_score "
        "column deferred to Plan 03 (agent-facing surface)."
    )


async def synthesize_digest(
    *,
    entity_id: str,
    since_date: str,
    token_budget: int,
    pool: Any,
    llm: Any,
    storage: Any,
) -> str:
    """Synthesise a token-budgeted digest for an entity.

    Raises:
        NotImplementedError: Evidence assembly and LLM synthesis are Plan 03 scope.
    """
    raise NotImplementedError(
        "Plan 03 — synthesize_digest: evidence assembly, LLM synthesis prompt, "
        "token budgeting, and digest cache deferred to Plan 03."
    )


async def dispatch_subscriptions(*, entity_id: str, pool: Any, queue: Any) -> int:
    """Enqueue subscriber notifications for a changed entity.

    Raises:
        NotImplementedError: Subscription matching and outbox dispatch are Plan 04 scope.
    """
    raise NotImplementedError(
        "Plan 04 — dispatch_subscriptions: subscription matching, outbox deduplication, "
        "and webhook/polling dispatch deferred to Plan 04."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Core orchestrator
# ──────────────────────────────────────────────────────────────────────────────


async def run_pipeline(
    *,
    source_id: str,
    pool: Any,
    storage: Any,
    llm: Any,
    embeddings: Any,
    max_documents: int = 200,
    max_chunks_per_doc: int = 20,
    chunk_size: int = 1500,
    chunk_overlap: int = 200,
    embed_batch_size: int = 64,
    resolve_batch_size: int = 100,
    link_batch_size: int = 200,
    use_embeddings_for_resolve: bool = True,
    use_embeddings_for_link: bool = True,
    extract_force: bool = False,
    ingest_trigger: str = "scheduled",
    adapter_config_overrides: dict[str, object] | None = None,
    source_slug: str | None = None,
    source_class: str | None = None,
) -> PipelineRunHealth:
    """Run the full pipeline for a single source, end-to-end.

    Chains stages in order; each stage is idempotent so re-running is safe.
    A failure in any per-document stage is logged and counted but does not
    abort the run for remaining documents.

    **Idempotent re-run / non-determinism guard.** Mention and claim
    extraction call the LLM, whose output is not byte-stable across calls
    (and degrades to the rule-only baseline on a transient provider 503).
    Re-extracting an already-processed document would therefore replace its
    mentions/claims with a *different* set, which the resolve stage would turn
    into *new* canonical entities — i.e. a re-run would grow the entity count.
    To honour the W8 contract ("runs twice without duplicate canonical
    records"), the orchestrator skips extraction for any document that already
    has mentions, unless *extract_force* is set.  Set *extract_force=True* to
    deliberately re-extract (e.g. after an extractor/prompt upgrade).

    The pipeline terminates at ``write_fact_versions``; later-plan synthesis
    steps (``compute_freshness``, ``synthesize_digest``, ``dispatch_subscriptions``)
    are explicitly not called here — they belong to Plans 03 / 04.

    Args:
        source_id: UUID of the ``sources`` row to process.
        pool: asyncpg connection pool.
        storage: StoragePort adapter for raw archival.
        llm: LlmPort adapter for extraction.
        embeddings: EmbeddingsPort adapter for chunk/claim/entity vectors.
        max_documents: Hard cap on documents per run (INGEST_MAX_DOCS_PER_RUN).
        max_chunks_per_doc: Budget cap on LLM chunk extraction per document.
        chunk_size: Target chars per chunk passed to the normalizer.
        chunk_overlap: Character overlap between consecutive chunks.
        embed_batch_size: Embedding adapter batch size.
        resolve_batch_size: Entity resolution mention batch size.
        link_batch_size: Claim-entity linking batch size.
        use_embeddings_for_resolve: Pass embeddings adapter to resolve_entities.
        use_embeddings_for_link: Pass embeddings adapter to link_claim_entities.
        extract_force: Re-extract mentions/claims even for documents that
            already have mentions.  Default False keeps re-runs idempotent.

    Returns:
        :class:`PipelineRunHealth` with per-stage counters and final status.
    """
    health = PipelineRunHealth(
        run_id=str(uuid.uuid4()),
        source_id=source_id,
        started_at=datetime.datetime.now(tz=datetime.UTC),
        mode=ingest_trigger,
        source_slug=source_slug,
        source_class=source_class,
        backfill_start_date=(
            str(adapter_config_overrides.get("start_date"))
            if adapter_config_overrides and adapter_config_overrides.get("start_date")
            else None
        ),
        backfill_end_date=(
            str(adapter_config_overrides.get("end_date"))
            if adapter_config_overrides and adapter_config_overrides.get("end_date")
            else None
        ),
    )

    _log.info(
        "pipeline run_id=%s source_id=%s started",
        health.run_id,
        source_id,
    )

    # ── Stage 1: Ingest ───────────────────────────────────────────────────────
    try:
        ingest_counters = await ingest_source(
            source_id=source_id,
            pool=pool,
            storage=storage,
            max_documents=max_documents,
            adapter_config_overrides=adapter_config_overrides,
            trigger=ingest_trigger,
        )
        health.docs_fetched = ingest_counters.get("fetched", 0)
        health.docs_new = ingest_counters.get("new", 0)
        health.docs_skipped_ingest = ingest_counters.get("skipped", 0)
        health.docs_policy_blocked = ingest_counters.get("policy_blocked", 0)
        health.errors_ingest = ingest_counters.get("errors", 0)
        _log.info("pipeline stage=ingest %s", ingest_counters)
    except Exception as exc:
        _log.error("pipeline stage=ingest FAILED: %s", exc)
        health.errors_ingest += 1
        health.finish(status="failed")
        return health

    # Fetch the document IDs that were ingested (new this run) and any
    # un-normalised documents from prior partial runs.
    doc_ids: list[str] = [
        str(r["id"])
        for r in await pool.fetch(
            """
            SELECT id FROM source_documents
            WHERE source_id = $1
            ORDER BY ingested_at DESC
            LIMIT $2
            """,
            uuid.UUID(source_id),
            max_documents,
        )
    ]

    if not doc_ids:
        _log.info("pipeline source_id=%s: no documents to process", source_id)
        health.finish(status="succeeded")
        return health

    # ── Stage 2: Normalize ────────────────────────────────────────────────────
    for doc_id in doc_ids:
        try:
            result = await normalize_document(
                document_id=doc_id,
                pool=pool,
                storage=storage,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            if result.get("skipped"):
                health.docs_skipped_normalize += 1
            else:
                health.docs_normalized += 1
        except Exception as exc:
            _log.error("pipeline stage=normalize doc_id=%s FAILED: %s", doc_id, exc)
            health.errors_normalize += 1

    _log.info(
        "pipeline stage=normalize normalized=%d skipped=%d errors=%d",
        health.docs_normalized,
        health.docs_skipped_normalize,
        health.errors_normalize,
    )

    # ── Stage 3: Extract mentions and claims ──────────────────────────────────
    # Idempotent-skip: a document that already has mentions has been extracted
    # by a prior run.  Re-extracting it would produce a *different* (LLM
    # non-deterministic) mention/claim set and thus new entities on re-run, so
    # we skip it unless ``extract_force`` is set.  This is what keeps the
    # full-pipeline re-run free of duplicate canonical records.
    already_extracted: set[str] = set()
    if not extract_force:
        already_extracted = {
            str(r["document_id"])
            for r in await pool.fetch(
                """
                SELECT DISTINCT document_id FROM mentions
                WHERE document_id = ANY($1::uuid[])
                """,
                [uuid.UUID(d) for d in doc_ids],
            )
        }

    for doc_id in doc_ids:
        if doc_id in already_extracted:
            health.docs_skipped_extract += 1
            continue

        try:
            mention_counters = await extract_mentions(document_id=doc_id, pool=pool, llm=llm)
            health.mentions_extracted += mention_counters.get("persisted", 0)
        except Exception as exc:
            _log.error("pipeline stage=extract_mentions doc_id=%s FAILED: %s", doc_id, exc)
            health.errors_extract += 1

        try:
            claim_counters = await extract_claims(
                document_id=doc_id,
                pool=pool,
                llm=llm,
                max_chunks=max_chunks_per_doc,
            )
            health.claims_extracted += claim_counters.get("claims_persisted", 0)
        except Exception as exc:
            _log.error("pipeline stage=extract_claims doc_id=%s FAILED: %s", doc_id, exc)
            health.errors_extract += 1

    _log.info(
        "pipeline stage=extract mentions=%d claims=%d skipped_docs=%d errors=%d",
        health.mentions_extracted,
        health.claims_extracted,
        health.docs_skipped_extract,
        health.errors_extract,
    )

    # ── Stage 4: Embed chunks and claims ──────────────────────────────────────
    for doc_id in doc_ids:
        try:
            chunk_counters = await embed_chunks(
                document_id=doc_id,
                pool=pool,
                embeddings=embeddings,
                batch_size=embed_batch_size,
            )
            health.chunks_embedded += chunk_counters.get("chunks_embedded", 0)
        except Exception as exc:
            _log.error("pipeline stage=embed_chunks doc_id=%s FAILED: %s", doc_id, exc)
            health.errors_embed += 1

        try:
            claim_embed_counters = await embed_claims(
                document_id=doc_id,
                pool=pool,
                embeddings=embeddings,
                batch_size=embed_batch_size,
            )
            health.claims_embedded += claim_embed_counters.get("claims_embedded", 0)
        except Exception as exc:
            _log.error("pipeline stage=embed_claims doc_id=%s FAILED: %s", doc_id, exc)
            health.errors_embed += 1

    _log.info(
        "pipeline stage=embed chunks=%d claims=%d errors=%d",
        health.chunks_embedded,
        health.claims_embedded,
        health.errors_embed,
    )

    # ── Stage 5: Resolve entities ─────────────────────────────────────────────
    # ``resolve_entities`` processes ONE batch of unresolved mentions per call.
    # A real run produces far more mentions than one batch, so the orchestrator
    # must drain: loop until a pass loads no unresolved mentions.  Without this,
    # a single call leaves most mentions unresolved and the *next* whole-pipeline
    # run resolves them into new entities — i.e. the re-run is not idempotent.
    # A hard iteration cap guards against a pathological non-terminating batch.
    try:
        for _ in range(_MAX_DRAIN_ITERATIONS):
            resolve_counters = await resolve_entities(
                pool=pool,
                embeddings=embeddings if use_embeddings_for_resolve else None,
                batch_size=resolve_batch_size,
            )
            health.entities_created += resolve_counters.get("entities_created", 0)
            health.entities_merged += resolve_counters.get("merges_performed", 0)
            health.review_candidates += resolve_counters.get("candidates_created", 0)
            _log.info("pipeline stage=resolve_entities %s", resolve_counters)
            if resolve_counters.get("mentions_loaded", 0) == 0:
                break
        else:
            _log.warning(
                "pipeline stage=resolve_entities hit drain cap (%d); "
                "unresolved mentions may remain",
                _MAX_DRAIN_ITERATIONS,
            )
    except Exception as exc:
        _log.error("pipeline stage=resolve_entities FAILED: %s", exc)
        health.errors_resolve += 1

    # ── Stage 6: Link claim entities ──────────────────────────────────────────
    # Draining contract: ``link_claim_entities`` processes one stable-ordered
    # batch of claims-with-a-NULL-end per call.  Unlike resolve (every loaded
    # mention is consumed), some claim ends are *legitimately unlinkable*
    # (conservative: left NULL) — they keep their NULL ends and would re-load
    # forever under a bare ``LIMIT``.  Terminating on ``claims_updated == 0``
    # would instead stop early whenever a full batch of unlinkable claims sorts
    # ahead of linkable ones, leaving linkable claims for a *later* run (an
    # idempotency break at scale).  Both failure modes are avoided by paging:
    # advance the offset past the claims that *stayed* unlinked in each batch
    # (``claims_loaded - claims_updated``) — linked claims drop out of the
    # WHERE set so they don't shift the cursor — and stop when a batch loads
    # fewer than ``batch_size`` rows (end of the set reached) or loads nothing.
    try:
        link_offset = 0
        for _ in range(_MAX_DRAIN_ITERATIONS):
            link_counters = await link_claim_entities(
                pool=pool,
                embeddings=embeddings if use_embeddings_for_link else None,
                batch_size=link_batch_size,
                offset=link_offset,
            )
            loaded = link_counters.get("claims_loaded", 0)
            updated = link_counters.get("claims_updated", 0)
            health.claims_linked += updated
            _log.info("pipeline stage=link_claim_entities %s", link_counters)
            # Step the cursor past the claims that remained unlinked (still in
            # the set); linked claims left the set and shifted positions left.
            link_offset += loaded - updated
            if loaded == 0 or loaded < link_batch_size:
                break
        else:
            _log.warning(
                "pipeline stage=link_claim_entities hit drain cap (%d)",
                _MAX_DRAIN_ITERATIONS,
            )
    except Exception as exc:
        _log.error("pipeline stage=link_claim_entities FAILED: %s", exc)
        health.errors_resolve += 1

    # ── Stage 7: Derive relationships ─────────────────────────────────────────
    # Operate on all fully-linked active claims (across all sources in scope,
    # since the resolve/link stages are batch and not source-scoped).
    linked_claim_ids: list[str] = [
        str(r["id"])
        for r in await pool.fetch(
            """
            SELECT id FROM claims
            WHERE status = 'active'
              AND subject_entity_id IS NOT NULL
              AND object_entity_id IS NOT NULL
            """
        )
    ]

    for claim_id in linked_claim_ids:
        try:
            derive_counters = await derive_relationships(claim_id=claim_id, pool=pool)
            health.relationships_written += derive_counters.get("relationships_written", 0)
            health.relationships_skipped += derive_counters.get("relationships_skipped", 0)
        except Exception as exc:
            _log.error("pipeline stage=derive_relationships claim_id=%s FAILED: %s", claim_id, exc)
            health.errors_derive += 1

    _log.info(
        "pipeline stage=derive_relationships written=%d skipped=%d errors=%d",
        health.relationships_written,
        health.relationships_skipped,
        health.errors_derive,
    )

    # ── Stage 8: Write fact versions ──────────────────────────────────────────
    # Version all non-deprecated entities that have at least one resolved mention
    # (this run may have created or updated entity state).
    entity_ids: list[str] = [
        str(r["id"])
        for r in await pool.fetch(
            """
            SELECT DISTINCT e.id
            FROM entities e
            JOIN mentions m ON m.entity_id = e.id
            WHERE e.is_deprecated = false
            """
        )
    ]

    for entity_id in entity_ids:
        try:
            version_counters = await write_fact_versions(entity_id=entity_id, pool=pool)
            health.fact_versions_written += version_counters.get("versions_written", 0)
            health.fact_versions_skipped += version_counters.get("versions_skipped", 0)
        except Exception as exc:
            _log.error("pipeline stage=write_fact_versions entity_id=%s FAILED: %s", entity_id, exc)
            health.errors_version += 1

    _log.info(
        "pipeline stage=write_fact_versions written=%d skipped=%d errors=%d",
        health.fact_versions_written,
        health.fact_versions_skipped,
        health.errors_version,
    )

    # ── Determine final status ────────────────────────────────────────────────
    total_errors = (
        health.errors_ingest
        + health.errors_normalize
        + health.errors_extract
        + health.errors_embed
        + health.errors_resolve
        + health.errors_derive
        + health.errors_version
    )
    if total_errors == 0:
        health.finish(status="succeeded")
    elif health.docs_new > 0 or health.docs_normalized > 0:
        # Partial success: some useful work was done despite errors.
        health.finish(status="partial")
    else:
        health.finish(status="failed")

    _log.info(
        "pipeline run_id=%s status=%s total_errors=%d summary=%s",
        health.run_id,
        health.status,
        total_errors,
        {k: v for k, v in health.to_dict().items() if isinstance(v, int) and v != 0},
    )

    return health
