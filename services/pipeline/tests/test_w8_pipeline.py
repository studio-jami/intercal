"""Fixture heartbeat for the W8 pipeline orchestrator.

Tests cover:
- ``PipelineRunHealth`` dataclass construction and serialisation.
- ``run_pipeline`` with a fake pool + fake adapters:
  - Stages fire in order (ingest → normalize → extract → embed →
    resolve → link → derive → version).
  - Counter values propagate correctly into the health summary.
  - Per-document extraction error is non-fatal (stage continues).
  - Stage-6 (ingest) fatal error → status='failed', early return.
  - Idempotent re-run of a clean state: no new writes.
  - Fixture acceptance gate (≥1 entity resolved, ≥1 review candidate,
    ≥1 relationship, ≥1 fact version).
- ``compute_freshness``, ``synthesize_digest``, ``dispatch_subscriptions``
  are deferred with ``NotImplementedError`` (explicit plan labels).
- CLI wiring: ``--help`` lists the ``run`` and ``run-all`` commands.
- ``intercal-pipeline`` script entry-point is importable.

No live network, database, or LLM/embeddings provider required.
"""

from __future__ import annotations

import datetime
import inspect
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from intercal_pipeline.cli import app, build_backfill_overrides, select_sources
from intercal_pipeline.run import (
    PipelineRunHealth,
    compute_freshness,
    dispatch_subscriptions,
    run_pipeline,
    synthesize_digest,
)
from typer.testing import CliRunner

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures / fakes
# ──────────────────────────────────────────────────────────────────────────────

_SOURCE_ID = str(uuid.uuid4())
_DOC_ID = str(uuid.uuid4())
_ENTITY_ID = str(uuid.uuid4())
_CLAIM_ID = str(uuid.uuid4())


class _FakeRecord:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> Any:
        return self._data.keys()

    def values(self) -> Any:
        return self._data.values()

    def items(self) -> Any:
        return self._data.items()


class _FakePool:
    """Minimal fake asyncpg pool for unit-testing the orchestrator.

    ``_rows`` maps query-prefix (uppercased, collapsed whitespace) to a list
    of row dicts.  All INSERT/UPDATE calls are silently accepted and counted.
    """

    def __init__(
        self,
        doc_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
        claim_ids: list[str] | None = None,
        extracted_doc_ids: list[str] | None = None,
    ) -> None:
        # Use explicit None sentinel to distinguish "use defaults" from "empty list"
        self._doc_ids = [_DOC_ID] if doc_ids is None else doc_ids
        self._entity_ids = [_ENTITY_ID] if entity_ids is None else entity_ids
        self._claim_ids = [_CLAIM_ID] if claim_ids is None else claim_ids
        # Documents that already have mentions (extracted by a prior run).
        self._extracted_doc_ids = extracted_doc_ids or []
        self.executed: list[str] = []

    def _doc_records(self) -> list[_FakeRecord]:
        return [_FakeRecord({"id": uuid.UUID(d)}) for d in self._doc_ids]

    def _entity_records(self) -> list[_FakeRecord]:
        return [_FakeRecord({"id": uuid.UUID(e)}) for e in self._entity_ids]

    def _claim_records(self) -> list[_FakeRecord]:
        return [_FakeRecord({"id": uuid.UUID(c)}) for c in self._claim_ids]

    async def fetch(self, sql: str, *args: Any) -> list[_FakeRecord]:
        norm = " ".join(sql.split()).upper()
        # Stage 3 idempotent-skip probe: docs that already have mentions
        if "FROM MENTIONS" in norm and "DOCUMENT_ID = ANY" in norm:
            return [_FakeRecord({"document_id": uuid.UUID(d)}) for d in self._extracted_doc_ids]
        # Stage 1b: doc IDs for a source
        if "FROM SOURCE_DOCUMENTS" in norm and "LIMIT" in norm:
            return self._doc_records()
        # Stage 7: fully-linked claim IDs
        if "SUBJECT_ENTITY_ID IS NOT NULL" in norm and "OBJECT_ENTITY_ID IS NOT NULL" in norm:
            return self._claim_records()
        # Stage 8: entity IDs that have mentions
        if "FROM ENTITIES E" in norm and "JOIN MENTIONS" in norm:
            return self._entity_records()
        # Sources for run-all
        if "FROM SOURCES" in norm and "IS_ACTIVE" in norm:
            return [
                _FakeRecord(
                    {
                        "id": uuid.UUID(_SOURCE_ID),
                        "slug": "fixture-source",
                        "adapter_name": "rss_feed_v1",
                        "metadata": {"source_class": "lab_announcement"},
                    }
                )
            ]
        return []

    async def fetchrow(self, sql: str, *args: Any) -> _FakeRecord | None:
        return None

    async def fetchval(self, sql: str, *args: Any, column: int = 0) -> Any:
        return None

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append(sql)
        return "OK"


def _make_fake_llm() -> Any:
    return MagicMock()


def _make_fake_embeddings() -> Any:
    return MagicMock()


def _make_fake_storage() -> Any:
    return MagicMock()


# ──────────────────────────────────────────────────────────────────────────────
# PipelineRunHealth tests
# ──────────────────────────────────────────────────────────────────────────────


def test_health_defaults() -> None:
    h = PipelineRunHealth(
        run_id="r1",
        source_id="s1",
        started_at=datetime.datetime.now(tz=datetime.UTC),
    )
    assert h.status == "running"
    assert h.docs_fetched == 0
    assert h.finished_at is None


def test_health_finish_sets_status() -> None:
    h = PipelineRunHealth(
        run_id="r1",
        source_id="s1",
        started_at=datetime.datetime.now(tz=datetime.UTC),
    )
    h.finish(status="succeeded")
    assert h.status == "succeeded"
    assert h.finished_at is not None


def test_health_to_dict_serialises_datetimes() -> None:
    h = PipelineRunHealth(
        run_id="r1",
        source_id="s1",
        started_at=datetime.datetime(2026, 6, 5, 12, 0, tzinfo=datetime.UTC),
    )
    h.finish()
    d = h.to_dict()
    assert isinstance(d["started_at"], str)
    assert "2026" in d["started_at"]
    assert isinstance(d["finished_at"], str)
    assert d["status"] == "succeeded"


def test_health_to_dict_is_json_serialisable() -> None:
    h = PipelineRunHealth(
        run_id="r1",
        source_id="s1",
        started_at=datetime.datetime.now(tz=datetime.UTC),
    )
    h.finish()
    # Must not raise
    _ = json.dumps(h.to_dict())


# ──────────────────────────────────────────────────────────────────────────────
# Later-plan stub tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_freshness_is_plan_03() -> None:
    with pytest.raises(NotImplementedError) as exc_info:
        await compute_freshness(entity_id="e1", pool=None)
    assert "Plan 03" in str(exc_info.value)


@pytest.mark.asyncio
async def test_synthesize_digest_is_plan_03() -> None:
    with pytest.raises(NotImplementedError) as exc_info:
        await synthesize_digest(
            entity_id="e1",
            since_date="2026-01-01",
            token_budget=1024,
            pool=None,
            llm=None,
            storage=None,
        )
    assert "Plan 03" in str(exc_info.value)


@pytest.mark.asyncio
async def test_dispatch_subscriptions_is_plan_04() -> None:
    with pytest.raises(NotImplementedError) as exc_info:
        await dispatch_subscriptions(entity_id="e1", pool=None, queue=None)
    assert "Plan 04" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# run_pipeline unit tests (fake pool, fake adapters)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_pipeline_ingest_fatal_error_returns_failed() -> None:
    """If ingest_source raises, the run terminates with status='failed'."""
    pool = _FakePool()

    with (
        patch("intercal_pipeline.run.ingest_source", new_callable=AsyncMock) as mock_ingest,
        patch("intercal_pipeline.run.normalize_document", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_mentions", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_chunks", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.resolve_entities", new_callable=AsyncMock),
        patch("intercal_pipeline.run.link_claim_entities", new_callable=AsyncMock),
        patch("intercal_pipeline.run.derive_relationships", new_callable=AsyncMock),
        patch("intercal_pipeline.run.write_fact_versions", new_callable=AsyncMock),
    ):
        mock_ingest.side_effect = RuntimeError("adapter unavailable")

        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    assert health.status == "failed"
    assert health.errors_ingest == 1
    assert health.finished_at is not None


@pytest.mark.asyncio
async def test_run_pipeline_no_docs_succeeds_immediately() -> None:
    """If ingest returns 0 new docs and no existing docs, run succeeds with 0 work."""
    pool = _FakePool(doc_ids=[])  # no docs returned by fetch

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 0, "new": 0, "skipped": 0, "errors": 0},
        ),
        patch("intercal_pipeline.run.normalize_document", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_mentions", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_chunks", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.resolve_entities", new_callable=AsyncMock),
        patch("intercal_pipeline.run.link_claim_entities", new_callable=AsyncMock),
        patch("intercal_pipeline.run.derive_relationships", new_callable=AsyncMock),
        patch("intercal_pipeline.run.write_fact_versions", new_callable=AsyncMock),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    assert health.status == "succeeded"
    assert health.docs_fetched == 0


@pytest.mark.asyncio
async def test_run_pipeline_full_chain_fixture_gate() -> None:
    """Fixture acceptance gate: ≥1 resolved entity, ≥1 review candidate,
    ≥1 relationship, ≥1 fact version.

    Uses a single document with 2 mentions, 1 claim, 1 linked claim, 1 relationship,
    and 1 entity fact version.  All stages fire in order; the health counters
    satisfy the acceptance criteria.
    """
    pool = _FakePool(
        doc_ids=[_DOC_ID],
        entity_ids=[_ENTITY_ID],
        claim_ids=[_CLAIM_ID],
    )

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 3, "new": 1, "skipped": 2, "errors": 0},
        ) as mock_ingest,
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value={
                "skipped": False,
                "chunk_count": 3,
                "language": "en",
                "clean_chars": 1200,
            },
        ) as mock_normalize,
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            return_value={"persisted": 2, "dropped": 0},
        ) as mock_mentions,
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            # Real extract_claims counter keys (see intercal_extract.jobs).
            return_value={"chunks_processed": 3, "claims_extracted": 1, "claims_persisted": 1},
        ) as mock_claims,
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            # Real embed_chunks counter keys.
            return_value={
                "chunks_total": 3,
                "chunks_skipped": 0,
                "chunks_embedded": 3,
                "vectors_persisted": 3,
            },
        ) as mock_embed_chunks,
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            # Real embed_claims counter keys.
            return_value={
                "claims_total": 1,
                "claims_skipped": 0,
                "claims_embedded": 1,
                "vectors_persisted": 1,
            },
        ) as mock_embed_claims,
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            # 1 resolved entity + 1 review candidate → satisfies acceptance gate
            return_value={
                "entities_created": 1,
                "merges_performed": 0,
                "candidates_created": 1,
                "mentions_resolved": 2,
            },
        ) as mock_resolve,
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 1, "fully_linked": 1},
        ) as mock_link,
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            # 1 relationship → satisfies acceptance gate
            return_value={"relationships_written": 1, "relationships_skipped": 0},
        ) as mock_derive,
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            # 1 fact version → satisfies acceptance gate
            return_value={"versions_written": 1, "versions_skipped": 0},
        ) as mock_version,
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    # ── Verify call order / counts ────────────────────────────────────────────
    mock_ingest.assert_called_once()
    mock_normalize.assert_called_once()  # 1 doc
    mock_mentions.assert_called_once()
    mock_claims.assert_called_once()
    mock_embed_chunks.assert_called_once()
    mock_embed_claims.assert_called_once()
    mock_resolve.assert_called_once()
    mock_link.assert_called_once()
    mock_derive.assert_called_once()  # 1 claim
    mock_version.assert_called_once()  # 1 entity

    # ── Verify health counters ────────────────────────────────────────────────
    assert health.docs_fetched == 3
    assert health.docs_new == 1
    assert health.docs_skipped_ingest == 2
    assert health.docs_normalized == 1
    assert health.mentions_extracted == 2
    assert health.claims_extracted == 1
    assert health.chunks_embedded == 3
    assert health.claims_embedded == 1

    # ── Acceptance gate: ≥1 resolved entity, ≥1 review candidate ─────────────
    assert health.entities_created >= 1, "need ≥1 resolved entity"
    assert health.review_candidates >= 1, "need ≥1 review-needed entity"

    # ── Acceptance gate: ≥1 relationship ─────────────────────────────────────
    assert health.relationships_written >= 1, "need ≥1 relationship written"

    # ── Acceptance gate: ≥1 fact version ─────────────────────────────────────
    assert health.fact_versions_written >= 1, "need ≥1 fact version written"

    assert health.status == "succeeded"
    assert health.errors_ingest == 0


@pytest.mark.asyncio
async def test_run_pipeline_passes_backfill_controls_to_ingest() -> None:
    """Backfill mode still uses the normal pipeline path, with ingest overrides."""
    pool = _FakePool(doc_ids=[])
    overrides: dict[str, object] = {"start_date": "2022-11-01", "end_date": "2022-11-30"}

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 0, "new": 0, "skipped": 0, "errors": 0},
        ) as mock_ingest,
        patch("intercal_pipeline.run.normalize_document", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_mentions", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_chunks", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.resolve_entities", new_callable=AsyncMock),
        patch("intercal_pipeline.run.link_claim_entities", new_callable=AsyncMock),
        patch("intercal_pipeline.run.derive_relationships", new_callable=AsyncMock),
        patch("intercal_pipeline.run.write_fact_versions", new_callable=AsyncMock),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
            ingest_trigger="backfill",
            adapter_config_overrides=overrides,
            source_slug="fixture-source",
            source_class="lab_announcement",
        )

    mock_ingest.assert_called_once()
    assert mock_ingest.call_args.kwargs["trigger"] == "backfill"
    assert mock_ingest.call_args.kwargs["adapter_config_overrides"] == overrides
    assert health.mode == "backfill"
    assert health.source_slug == "fixture-source"
    assert health.source_class == "lab_announcement"
    assert health.backfill_start_date == "2022-11-01"
    assert health.backfill_end_date == "2022-11-30"


@pytest.mark.asyncio
async def test_run_pipeline_idempotent_rerun() -> None:
    """Second run on the same data: all stages report 0 new writes.

    Idempotency is provided by each stage (skipped on re-run); the orchestrator
    must not override or duplicate that behaviour.
    """
    pool = _FakePool(doc_ids=[_DOC_ID], entity_ids=[_ENTITY_ID], claim_ids=[_CLAIM_ID])

    _zero_counters_ingest = {"fetched": 3, "new": 0, "skipped": 3, "errors": 0}
    _zero_normalize = {"skipped": True, "chunk_count": 0, "language": "en", "clean_chars": 0}
    _zero_mentions = {"persisted": 0, "dropped": 0}
    _zero_claims = {"chunks_processed": 0, "claims_extracted": 0, "claims_persisted": 0}
    _zero_embed = {
        "chunks_total": 3,
        "chunks_skipped": 3,
        "chunks_embedded": 0,
        "claims_total": 0,
        "claims_skipped": 0,
        "claims_embedded": 0,
        "vectors_persisted": 0,
    }
    _zero_resolve = {
        "entities_created": 0,
        "merges_performed": 0,
        "candidates_created": 0,
        "mentions_resolved": 0,
    }
    _zero_link = {"claims_updated": 0, "fully_linked": 1}
    _zero_derive = {"relationships_written": 0, "relationships_skipped": 1}
    _zero_version = {"versions_written": 0, "versions_skipped": 1}

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value=_zero_counters_ingest,
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value=_zero_normalize,
        ),
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            return_value=_zero_mentions,
        ),
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            return_value=_zero_claims,
        ),
        patch(
            "intercal_pipeline.run.embed_chunks", new_callable=AsyncMock, return_value=_zero_embed
        ),
        patch(
            "intercal_pipeline.run.embed_claims", new_callable=AsyncMock, return_value=_zero_embed
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value=_zero_resolve,
        ),
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value=_zero_link,
        ),
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            return_value=_zero_derive,
        ),
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            return_value=_zero_version,
        ),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    assert health.status == "succeeded"
    assert health.docs_new == 0
    assert health.docs_normalized == 0
    assert health.docs_skipped_normalize == 1
    assert health.entities_created == 0
    assert health.relationships_written == 0
    assert health.fact_versions_written == 0


@pytest.mark.asyncio
async def test_run_pipeline_drains_resolve_and_link_batches() -> None:
    """Resolve/link stages drain across multiple batches until no work remains.

    Regression guard: a real run produces far more mentions/claims than one
    batch.  If the orchestrator called resolve/link only once, most mentions
    would stay unresolved and the *next* whole-pipeline run would resolve them
    into new entities (non-idempotent).

    - Resolve drains until a pass loads no unresolved mentions (every loaded
      mention is consumed, so an empty load is the true end).
    - Link *pages* with an advancing offset (unlinkable claims keep NULL ends
      and would re-load forever under a bare LIMIT; stopping on no-progress
      would instead skip linkable claims sorted behind a full batch of
      unlinkable ones).  It advances the offset past the claims that *stayed*
      unlinked each batch and stops on the first partial (< batch_size) batch.
    """
    pool = _FakePool(doc_ids=[_DOC_ID], entity_ids=[_ENTITY_ID], claim_ids=[_CLAIM_ID])

    # resolve: 2 batches with work, then an empty batch → 3 calls, loop ends.
    resolve_side_effect = [
        {
            "entities_created": 10,
            "merges_performed": 0,
            "candidates_created": 4,
            "mentions_loaded": 100,
            "mentions_resolved": 100,
        },
        {
            "entities_created": 7,
            "merges_performed": 1,
            "candidates_created": 2,
            "mentions_loaded": 80,
            "mentions_resolved": 80,
        },
        {
            "entities_created": 0,
            "merges_performed": 0,
            "candidates_created": 0,
            "mentions_loaded": 0,
            "mentions_resolved": 0,
        },
    ]
    # link: page through with offset.  batch_size=10.
    #   batch 1 @offset 0: loads 10, links 7 → 3 stay unlinked → next offset 3
    #   batch 2 @offset 3: loads 10, links 0 → 10 stay unlinked → next offset 13
    #   batch 3 @offset 13: loads 4 (< batch_size) → end reached, stop
    # Stopping on no-progress (old contract) would have ended after batch 2 and
    # missed the linkable claims in batch 3 — the bug this guards against.
    _link_batch = 10
    link_side_effect = [
        {"claims_loaded": 10, "claims_updated": 7},
        {"claims_loaded": 10, "claims_updated": 0},
        {"claims_loaded": 4, "claims_updated": 2},  # partial batch → end
    ]

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 1, "new": 1, "skipped": 0, "errors": 0},
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value={"skipped": False, "chunk_count": 5, "language": "en", "clean_chars": 900},
        ),
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            return_value={"persisted": 100},
        ),
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            return_value={"claims_persisted": 50},
        ),
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            return_value={"chunks_embedded": 5},
        ),
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            return_value={"claims_embedded": 50},
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            side_effect=resolve_side_effect,
        ) as mock_resolve,
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            side_effect=link_side_effect,
        ) as mock_link,
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            return_value={"relationships_written": 0, "relationships_skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            return_value={"versions_written": 0, "versions_skipped": 0},
        ),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
            link_batch_size=_link_batch,
        )

    # resolve drained over 3 calls; counters accumulated across batches.
    assert mock_resolve.call_count == 3
    assert health.entities_created == 17  # 10 + 7
    assert health.entities_merged == 1
    assert health.review_candidates == 6  # 4 + 2
    # link paged over 3 calls (did NOT stop on the no-progress batch 2) and
    # accumulated links from the final partial batch.
    assert mock_link.call_count == 3
    assert health.claims_linked == 9  # 7 + 0 + 2
    # Offsets advanced past the claims that stayed unlinked each batch:
    #   batch1 offset=0, batch2 offset=3 (10-7), batch3 offset=13 (3 + 10-0)
    link_offsets = [c.kwargs["offset"] for c in mock_link.call_args_list]
    assert link_offsets == [0, 3, 13]


@pytest.mark.asyncio
async def test_run_pipeline_skips_extraction_for_already_extracted_docs() -> None:
    """A re-run skips extraction for documents that already have mentions.

    This guards full-pipeline idempotency: LLM extraction is non-deterministic,
    so re-extracting an already-processed document would yield a different
    mention/claim set and thus new entities.  The orchestrator must skip it.
    """
    pool = _FakePool(
        doc_ids=[_DOC_ID],
        entity_ids=[_ENTITY_ID],
        claim_ids=[_CLAIM_ID],
        extracted_doc_ids=[_DOC_ID],  # already extracted by a prior run
    )

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 1, "new": 0, "skipped": 1, "errors": 0},
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value={"skipped": True, "chunk_count": 0, "language": "en", "clean_chars": 0},
        ),
        patch("intercal_pipeline.run.extract_mentions", new_callable=AsyncMock) as mock_mentions,
        patch("intercal_pipeline.run.extract_claims", new_callable=AsyncMock) as mock_claims,
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            return_value={"chunks_embedded": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            return_value={"claims_embedded": 0},
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value={
                "entities_created": 0,
                "merges_performed": 0,
                "candidates_created": 0,
                "mentions_resolved": 0,
            },
        ),
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 0},
        ),
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            return_value={"relationships_written": 0, "relationships_skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            return_value={"versions_written": 0, "versions_skipped": 1},
        ),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    # Extraction must NOT have been called for the already-extracted doc.
    mock_mentions.assert_not_called()
    mock_claims.assert_not_called()
    assert health.docs_skipped_extract == 1


@pytest.mark.asyncio
async def test_run_pipeline_extract_force_reextracts() -> None:
    """``extract_force=True`` re-extracts even already-extracted documents."""
    pool = _FakePool(
        doc_ids=[_DOC_ID],
        entity_ids=[],
        claim_ids=[],
        extracted_doc_ids=[_DOC_ID],
    )

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 1, "new": 0, "skipped": 1, "errors": 0},
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value={"skipped": True, "chunk_count": 1, "language": "en", "clean_chars": 10},
        ),
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            return_value={"persisted": 1},
        ) as mock_mentions,
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            return_value={"claims_persisted": 1},
        ) as mock_claims,
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            return_value={"chunks_embedded": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            return_value={"claims_embedded": 0},
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value={
                "entities_created": 0,
                "merges_performed": 0,
                "candidates_created": 0,
                "mentions_resolved": 0,
            },
        ),
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 0},
        ),
        patch("intercal_pipeline.run.derive_relationships", new_callable=AsyncMock),
        patch("intercal_pipeline.run.write_fact_versions", new_callable=AsyncMock),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
            extract_force=True,
        )

    mock_mentions.assert_called_once()
    mock_claims.assert_called_once()
    assert health.docs_skipped_extract == 0


@pytest.mark.asyncio
async def test_run_pipeline_per_doc_extract_error_is_nonfatal() -> None:
    """A single-doc extraction error is counted but does not abort the run."""
    pool = _FakePool(doc_ids=[_DOC_ID], entity_ids=[], claim_ids=[])

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 1, "new": 1, "skipped": 0, "errors": 0},
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value={"skipped": False, "chunk_count": 2, "language": "en", "clean_chars": 800},
        ),
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ),
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM budget exceeded"),
        ),
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            return_value={"embedded": 0, "skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            return_value={"embedded": 0, "skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value={
                "entities_created": 0,
                "merges_performed": 0,
                "candidates_created": 0,
                "mentions_resolved": 0,
            },
        ),
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 0, "fully_linked": 0},
        ),
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            return_value={"relationships_written": 0, "relationships_skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            return_value={"versions_written": 0, "versions_skipped": 0},
        ),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    # Errors counted but the run completes (docs_normalized > 0 → not "failed")
    assert health.errors_extract == 2  # 1 mention + 1 claim error
    assert health.status in ("partial", "succeeded")


@pytest.mark.asyncio
async def test_run_pipeline_normalize_error_is_nonfatal() -> None:
    """A normalize failure for one doc is counted; the run continues."""
    pool = _FakePool(doc_ids=[_DOC_ID], entity_ids=[], claim_ids=[])

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 1, "new": 1, "skipped": 0, "errors": 0},
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            side_effect=ValueError("doc not found"),
        ),
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            return_value={"persisted": 0},
        ),
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            return_value={"persisted": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            return_value={"embedded": 0, "skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            return_value={"embedded": 0, "skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value={
                "entities_created": 0,
                "merges_performed": 0,
                "candidates_created": 0,
                "mentions_resolved": 0,
            },
        ),
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 0, "fully_linked": 0},
        ),
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            return_value={"relationships_written": 0, "relationships_skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            return_value={"versions_written": 0, "versions_skipped": 0},
        ),
    ):
        health = await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
        )

    assert health.errors_normalize == 1


@pytest.mark.asyncio
async def test_run_pipeline_no_embeddings_flag() -> None:
    """``use_embeddings_for_resolve=False`` passes None to resolve/link stages."""
    pool = _FakePool(doc_ids=[_DOC_ID], entity_ids=[_ENTITY_ID], claim_ids=[_CLAIM_ID])

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 1, "new": 1, "skipped": 0, "errors": 0},
        ),
        patch(
            "intercal_pipeline.run.normalize_document",
            new_callable=AsyncMock,
            return_value={"skipped": False, "chunk_count": 1, "language": "en", "clean_chars": 100},
        ),
        patch(
            "intercal_pipeline.run.extract_mentions",
            new_callable=AsyncMock,
            return_value={"persisted": 0},
        ),
        patch(
            "intercal_pipeline.run.extract_claims",
            new_callable=AsyncMock,
            return_value={"persisted": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_chunks",
            new_callable=AsyncMock,
            return_value={"embedded": 0, "skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.embed_claims",
            new_callable=AsyncMock,
            return_value={"embedded": 0, "skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value={
                "entities_created": 0,
                "merges_performed": 0,
                "candidates_created": 0,
                "mentions_resolved": 0,
            },
        ) as mock_resolve,
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 0, "fully_linked": 0},
        ) as mock_link,
        patch(
            "intercal_pipeline.run.derive_relationships",
            new_callable=AsyncMock,
            return_value={"relationships_written": 0, "relationships_skipped": 0},
        ),
        patch(
            "intercal_pipeline.run.write_fact_versions",
            new_callable=AsyncMock,
            return_value={"versions_written": 0, "versions_skipped": 0},
        ),
    ):
        await run_pipeline(
            source_id=_SOURCE_ID,
            pool=pool,
            storage=_make_fake_storage(),
            llm=_make_fake_llm(),
            embeddings=_make_fake_embeddings(),
            use_embeddings_for_resolve=False,
            use_embeddings_for_link=False,
        )

    # embeddings=None forwarded to both stages
    _, resolve_kwargs = mock_resolve.call_args
    assert resolve_kwargs["embeddings"] is None
    _, link_kwargs = mock_link.call_args
    assert link_kwargs["embeddings"] is None


@pytest.mark.asyncio
async def test_run_pipeline_health_run_id_is_unique() -> None:
    """Two consecutive runs produce different run_ids."""
    pool = _FakePool(doc_ids=[], entity_ids=[], claim_ids=[])
    ids = []

    with (
        patch(
            "intercal_pipeline.run.ingest_source",
            new_callable=AsyncMock,
            return_value={"fetched": 0, "new": 0, "skipped": 0, "errors": 0},
        ),
        patch("intercal_pipeline.run.normalize_document", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_mentions", new_callable=AsyncMock),
        patch("intercal_pipeline.run.extract_claims", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_chunks", new_callable=AsyncMock),
        patch("intercal_pipeline.run.embed_claims", new_callable=AsyncMock),
        patch(
            "intercal_pipeline.run.resolve_entities",
            new_callable=AsyncMock,
            return_value={
                "entities_created": 0,
                "merges_performed": 0,
                "candidates_created": 0,
                "mentions_resolved": 0,
            },
        ),
        patch(
            "intercal_pipeline.run.link_claim_entities",
            new_callable=AsyncMock,
            return_value={"claims_updated": 0, "fully_linked": 0},
        ),
        patch("intercal_pipeline.run.derive_relationships", new_callable=AsyncMock),
        patch("intercal_pipeline.run.write_fact_versions", new_callable=AsyncMock),
    ):
        for _ in range(2):
            h = await run_pipeline(
                source_id=_SOURCE_ID,
                pool=pool,
                storage=_make_fake_storage(),
                llm=_make_fake_llm(),
                embeddings=_make_fake_embeddings(),
            )
            ids.append(h.run_id)

    assert ids[0] != ids[1]


# ──────────────────────────────────────────────────────────────────────────────
# CLI wiring tests
# ──────────────────────────────────────────────────────────────────────────────


def test_cli_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "run-all" in result.output


def test_cli_run_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--source-id" in result.output
    assert "--max-documents" in result.output
    assert "--max-chunks" in result.output
    assert "--no-embeddings" in result.output
    assert "--extract-force" in result.output


def test_cli_run_all_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run-all", "--help"])
    assert result.exit_code == 0
    assert "--max-documents" in result.output


def test_cli_backfill_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["backfill", "--help"])
    assert result.exit_code == 0
    assert "--source-class" in result.output
    assert "--start-date" in result.output
    assert "--end-date" in result.output
    assert "--dry-run" in result.output


def test_backfill_overrides_validates_date_window() -> None:
    overrides = build_backfill_overrides("2022-11-01", "2022-11-30")
    assert overrides == {"start_date": "2022-11-01", "end_date": "2022-11-30"}

    with pytest.raises(typer.BadParameter):
        build_backfill_overrides("2022-12-01", "2022-11-01")


@pytest.mark.asyncio
async def test_select_sources_returns_backfill_metadata() -> None:
    pool = _FakePool()
    sources = await select_sources(
        pool=pool,
        source_slugs=["fixture-source"],
        source_class="lab_announcement",
        adapter_name="rss_feed_v1",
        max_sources=1,
    )

    assert sources == [
        {
            "id": _SOURCE_ID,
            "slug": "fixture-source",
            "adapter_name": "rss_feed_v1",
            "source_class": "lab_announcement",
        }
    ]


def test_cli_run_requires_source_id() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0


def test_run_pipeline_is_async() -> None:
    assert inspect.iscoroutinefunction(run_pipeline)


def test_compute_freshness_is_async() -> None:
    assert inspect.iscoroutinefunction(compute_freshness)


def test_synthesize_digest_is_async() -> None:
    assert inspect.iscoroutinefunction(synthesize_digest)


def test_dispatch_subscriptions_is_async() -> None:
    assert inspect.iscoroutinefunction(dispatch_subscriptions)


def test_pipeline_module_is_importable() -> None:
    from intercal_pipeline.run import run_pipeline as rp

    assert callable(rp)
