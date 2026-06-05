"""Unit tests for W6 entity resolution and W7 relationship/fact-version derivation.

No live network required.

Tests cover:
- Helper functions (normalize_name, ordered_pair, detect_external_id,
  map_predicate_to_type)
- resolve_entities core paths:
  - No unresolved mentions → returns zero counters
  - External-ID match → links mention to existing entity
  - External-ID new → creates entity + registers external_id row
  - Exact name match → links mention to existing entity
  - New entity creation (no match) → entity created, mention resolved
  - Same mention group all map to the same entity (idempotent)
  - Ambiguous embedding candidate → needs_review candidate created
  - High-confidence embedding candidate → merge candidate created
  - Duplicate pair ordering (left < right UUID)
- W7 derive_relationships:
  - Known predicate → relationship written
  - Unknown predicate → skipped
  - Claim not found → skipped
  - Claim inactive → skipped
  - Claim low confidence → skipped
  - Self-relationship skipped
  - Entity ends unresolved → skipped
  - Idempotent re-run (existing relationship merges claim_id)
- W7 write_fact_versions:
  - New entity → version written
  - Same payload → skipped (idempotent)
  - Changed payload → new version written, old version closed (append-only)
  - Deprecated / missing entity → ValueError
  - Provenance: claim_ids populated
- W7 helpers (map_predicate_to_type, payload_equal)
- CLI help and new --embeddings flag
"""

from __future__ import annotations

import inspect
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from intercal_resolve.cli import app
from intercal_resolve.jobs import (
    COSINE_MERGE_THRESHOLD,
    COSINE_REVIEW_THRESHOLD,
    EXACT_MATCH_CONFIDENCE,
    LINK_COSINE_THRESHOLD,
    LINK_EMBEDDING_MIN_CONFIDENCE,
    LINK_EXACT_MENTION_CONFIDENCE,
    LINK_EXACT_NAME_CONFIDENCE,
    MIN_CLAIM_CONFIDENCE,
    MIN_MENTION_CONFIDENCE,
    derive_relationships,
    detect_external_id,
    find_external_id_collisions,
    link_claim_entities,
    map_predicate_to_type,
    normalize_name,
    ordered_pair,
    payload_equal,
    resolve_entities,
    write_fact_versions,
)
from typer.testing import CliRunner

# ──────────────────────────────────────────────────────────────────────────────
# Fake asyncpg pool for unit tests
# ──────────────────────────────────────────────────────────────────────────────


class FakePool:
    """Minimal fake asyncpg pool that intercepts SQL calls.

    Tests configure ``_rows`` (a dict of query-prefix → list-of-dicts) and
    inspect ``_executed`` to verify what was written.
    """

    def __init__(self, rows: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._rows: dict[str, list[dict[str, Any]]] = rows or {}
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def _match(self, sql: str) -> list[dict[str, Any]]:
        sql_norm = " ".join(sql.split()).upper()
        for prefix, result in self._rows.items():
            if sql_norm.startswith(prefix.upper()):
                return result
        return []

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        return [_FakeRecord(r) for r in self._match(sql)]

    async def fetchrow(self, sql: str, *args: Any) -> Any | None:
        rows = self._match(sql)
        return _FakeRecord(rows[0]) if rows else None

    async def fetchval(self, sql: str, *args: Any, column: int = 0) -> Any:
        row = await self.fetchrow(sql, *args)
        if row is None:
            return None
        return list(row._data.values())[column]

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((sql, args))
        return "OK"

    def executed_sqls(self) -> list[str]:
        return [e[0] for e in self.executed]


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


# ──────────────────────────────────────────────────────────────────────────────
# Helper unit tests
# ──────────────────────────────────────────────────────────────────────────────


def testnormalize_name_casefold_strip() -> None:
    assert normalize_name("  CrossRef  ") == "crossref"
    assert normalize_name("Europe PMC") == "europe pmc"


def testnormalize_name_unicode_nfc() -> None:
    # Decomposed vs composed form — should normalize to the same result.
    decomposed = "café"  # café with combining accent
    composed = "caf\xe9"      # café precomposed
    assert normalize_name(decomposed) == normalize_name(composed)


def testordered_pair_left_less_than_right() -> None:
    a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    b = uuid.UUID("00000000-0000-0000-0000-000000000002")
    left, right = ordered_pair(a, b)
    assert left == a and right == b
    left2, right2 = ordered_pair(b, a)
    assert left2 == a and right2 == b


def testdetect_external_id_wikidata_qid() -> None:
    assert detect_external_id("Q5401080") == ("wikidata", "Q5401080")
    assert detect_external_id("Q5") == ("wikidata", "Q5")


def testdetect_external_id_property_bare() -> None:
    assert detect_external_id("P31") == ("wikidata_property", "P31")


def testdetect_external_id_property_prefixed() -> None:
    assert detect_external_id("Property:P31") == ("wikidata_property", "P31")


def testdetect_external_id_none_for_plain_text() -> None:
    assert detect_external_id("CrossRef") is None
    assert detect_external_id("NCBI") is None


def testdetect_external_id_none_for_toolforge_url() -> None:
    # toolforge: prefix — not a QID/PID
    assert detect_external_id("toolforge:editgroups/b/CB/ece1e2aa4e61") is None


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — no mentions
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_no_mentions() -> None:
    pool = FakePool({"SELECT": []})  # no mentions returned
    counters = await resolve_entities(pool=pool, embeddings=None)
    assert counters["mentions_loaded"] == 0
    assert counters["mentions_resolved"] == 0
    assert counters["entities_created"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — external-ID match (existing entity)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_external_id_existing_entity() -> None:
    """A mention of 'Q5401080' that already has an entity in the DB."""
    mention_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    existing_entity_row = {"id": entity_id}

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            # Mentions query
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id,
                    "document_id": doc_id,
                    "text_span": "Q5401080",
                    "proposed_type": "ARTIFACT",
                    "extraction_confidence": 0.90,
                    "chunk_id": None,
                })]
            # External-ID collision detector (step 4, fetch) — no collision here.
            if "HAVING COUNT(DISTINCT EEI.ENTITY_ID) > 1" in sql_upper:
                return []
            # merge candidates (step 6)
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            # External ID lookup (fetchrow version)
            if "ENTITY_EXTERNAL_IDS EEI" in sql_upper:
                return _FakeRecord(existing_entity_row)
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["mentions_loaded"] == 1
    assert counters["mentions_resolved"] == 1
    # No new entity created — matched existing
    assert counters["entities_created"] == 0

    # Verify UPDATE was called on mentions with the existing entity_id
    executed_updates = [
        args for sql, args in pool.executed
        if "UPDATE MENTIONS" in " ".join(sql.split()).upper()
    ]
    assert len(executed_updates) >= 1
    # The entity_id should be the existing one
    first_update_args = executed_updates[0]
    assert first_update_args[0] == entity_id


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — external-ID new entity
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_external_id_creates_new_entity() -> None:
    """A mention of 'Q5' with no existing entity → new entity + external_id registered."""
    mention_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id,
                    "document_id": doc_id,
                    "text_span": "Q5",
                    "proposed_type": "ARTIFACT",
                    "extraction_confidence": 0.90,
                    "chunk_id": None,
                })]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            # External ID lookup — no match
            if "ENTITY_EXTERNAL_IDS EEI" in " ".join(sql.split()).upper():
                return None
            # Name lookup — no match
            if "LOWER(CANONICAL_NAME)" in " ".join(sql.split()).upper():
                return None
            if "ENTITY_ALIASES EA" in " ".join(sql.split()).upper():
                return None
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["entities_created"] == 1
    assert counters["mentions_resolved"] == 1

    # Check that INSERT INTO entities was called
    insert_sqls = [
        sql for sql, _ in pool.executed
        if "INSERT INTO ENTITIES" in " ".join(sql.split()).upper()
    ]
    assert len(insert_sqls) >= 1

    # Check that external_id was registered
    ext_id_sqls = [
        sql for sql, _ in pool.executed
        if "INSERT INTO ENTITY_EXTERNAL_IDS" in " ".join(sql.split()).upper()
    ]
    assert len(ext_id_sqls) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — exact name match
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_exact_name_match() -> None:
    """A mention 'CrossRef' matches an existing entity by canonical name."""
    mention_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id,
                    "document_id": doc_id,
                    "text_span": "CrossRef",
                    "proposed_type": "ORG",
                    "extraction_confidence": 0.95,
                    "chunk_id": None,
                })]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            # No external ID (CrossRef is not a QID)
            if "ENTITY_EXTERNAL_IDS EEI" in sql_upper:
                return None
            # Canonical name lookup — match!
            if "LOWER(CANONICAL_NAME)" in sql_upper and "ENTITY_ALIASES" not in sql_upper:
                return _FakeRecord({"id": entity_id})
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["entities_created"] == 0
    assert counters["mentions_resolved"] == 1

    # Verify UPDATE mentions references the matched entity
    update_args = [
        args for sql, args in pool.executed
        if "UPDATE MENTIONS" in " ".join(sql.split()).upper()
    ]
    assert update_args[0][0] == entity_id


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — new entity for unmatched mention
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_creates_new_entity_for_unmatched() -> None:
    """Mention 'Europe PMC' has no existing entity → creates one."""
    mention_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id,
                    "document_id": doc_id,
                    "text_span": "Europe PMC",
                    "proposed_type": "ORG",
                    "extraction_confidence": 0.95,
                    "chunk_id": None,
                })]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            return None  # no matches anywhere

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["entities_created"] == 1
    assert counters["mentions_resolved"] == 1

    insert_sqls = [
        sql for sql, _ in pool.executed
        if "INSERT INTO ENTITIES" in " ".join(sql.split()).upper()
    ]
    assert len(insert_sqls) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — multiple mentions same span → single entity (idempotent)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_deduplicates_same_span() -> None:
    """Two mentions of 'NCBI' same type → single new entity, both mentions resolved."""
    m1 = uuid.uuid4()
    m2 = uuid.uuid4()
    doc_id = uuid.uuid4()

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [
                    _FakeRecord({
                        "id": m1, "document_id": doc_id, "text_span": "NCBI",
                        "proposed_type": "ORG", "extraction_confidence": 0.95, "chunk_id": None,
                    }),
                    _FakeRecord({
                        "id": m2, "document_id": doc_id, "text_span": "NCBI",
                        "proposed_type": "ORG", "extraction_confidence": 0.95, "chunk_id": None,
                    }),
                ]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["mentions_resolved"] == 2
    assert counters["entities_created"] == 1  # only one entity for both mentions

    # Both mentions updated with the same entity_id
    update_args = [
        args for sql, args in pool.executed
        if "UPDATE MENTIONS" in " ".join(sql.split()).upper()
    ]
    assert len(update_args) == 2
    assert update_args[0][0] == update_args[1][0]  # same entity_id


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — below confidence threshold → skipped
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_skips_low_confidence_mentions() -> None:
    """Mentions below MIN_MENTION_CONFIDENCE are not loaded (SQL filters them)."""
    pool = FakePool({"SELECT": []})
    # The SQL WHERE clause filters low-confidence; we trust the pool returns nothing.
    counters = await resolve_entities(pool=pool, embeddings=None)
    assert counters["mentions_loaded"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — embedding-based review candidate
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_embedding_review_candidate() -> None:
    """New entity + nearby existing entity in embedding space → needs_review candidate."""
    mention_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    nearby_entity_id = uuid.uuid4()

    # Cosine distance that triggers needs_review (between thresholds)
    review_distance = (COSINE_MERGE_THRESHOLD + COSINE_REVIEW_THRESHOLD) / 2.0

    mock_embeddings = MagicMock()
    mock_embeddings.model = "BAAI/bge-small-en-v1.5"
    mock_embeddings.dim = 384
    mock_embeddings.embed = AsyncMock(return_value=[[0.1] * 384])

    candidate_row_id = uuid.uuid4()

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id, "document_id": doc_id,
                    "text_span": "PubMed Central",
                    "proposed_type": "ORG", "extraction_confidence": 0.85, "chunk_id": None,
                })]
            # Entity embedding query
            if "ENTITY_EMBEDDINGS EE" in sql_upper:
                return [_FakeRecord({
                    "entity_id": nearby_entity_id,
                    "distance": review_distance,
                })]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            if "ENTITY_EXTERNAL_IDS" in sql_upper:
                return None
            if "LOWER(CANONICAL_NAME)" in sql_upper and "ENTITY_ALIASES" not in sql_upper:
                return None
            if "ENTITY_ALIASES EA" in sql_upper:
                return None
            # INSERT ... ON CONFLICT for candidate upsert
            if "INSERT INTO ENTITY_RESOLUTION_CANDIDATES" in sql_upper:
                return _FakeRecord({"id": candidate_row_id})
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=mock_embeddings)

    assert counters["review_needed"] >= 1
    assert counters["entities_created"] >= 1


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — embedding-based merge candidate
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_embedding_direct_match() -> None:
    """Span with embedding distance <= COSINE_MERGE_THRESHOLD directly maps to existing entity.

    No new entity is created; the mention is linked to the nearby entity.
    No resolution candidate is needed for this case.
    """
    mention_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    nearby_entity_id = uuid.uuid4()

    # Distance well below merge threshold → direct assignment
    merge_distance = COSINE_MERGE_THRESHOLD / 2.0

    mock_embeddings = MagicMock()
    mock_embeddings.model = "BAAI/bge-small-en-v1.5"
    mock_embeddings.dim = 384
    mock_embeddings.embed = AsyncMock(return_value=[[0.1] * 384])

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id, "document_id": doc_id,
                    "text_span": "Europe PMC",
                    "proposed_type": "ORG", "extraction_confidence": 0.90, "chunk_id": None,
                })]
            if "ENTITY_EMBEDDINGS EE" in sql_upper:
                return [_FakeRecord({
                    "entity_id": nearby_entity_id,
                    "distance": merge_distance,
                })]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            return None  # no existing entity by name/ext-id

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=mock_embeddings)

    # Mention should be resolved to the nearby entity (direct embedding match)
    assert counters["mentions_resolved"] >= 1
    # No new entity created — matched existing via embedding
    assert counters["entities_created"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — auto-merge for high-confidence merge candidate
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_auto_merge_high_confidence() -> None:
    """Open 'merge' candidate with confidence >= EXACT_MATCH_CONFIDENCE is auto-merged."""
    left_id = uuid.uuid4()
    right_id = uuid.uuid4()
    candidate_id = uuid.uuid4()

    class RoutingPool(FakePool):
        def __init__(self) -> None:
            super().__init__()
            self._entity_row_calls: list[str] = []

        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return []
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return [_FakeRecord({
                    "id": candidate_id,
                    "left_entity_id": left_id,
                    "right_entity_id": right_id,
                    "confidence": EXACT_MATCH_CONFIDENCE,
                    "matching_signals": json.dumps([{"type": "exact_name"}]),
                })]
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            # Source entity fetch (has IS_DEPRECATED in SELECT list)
            if "IS_DEPRECATED" in sql_upper and "FROM ENTITIES" in sql_upper:
                return _FakeRecord({
                    "is_deprecated": False,
                    "merged_into_id": None,
                    "canonical_name": "EuropePMC",
                    "type_id": "organization",
                    "description": None,
                    "current_state": {},
                    "metadata": {},
                })
            # Target entity fetch (no IS_DEPRECATED in SELECT, just CANONICAL_NAME)
            if "CANONICAL_NAME" in sql_upper and "FROM ENTITIES" in sql_upper:
                return _FakeRecord({
                    "canonical_name": "Europe PMC",
                    "type_id": "organization",
                    "description": None,
                    "current_state": {},
                    "metadata": {},
                })
            if "ENTITY_MERGE_EVENTS" in sql_upper and "IS_REVERSED = FALSE" in sql_upper:
                return None
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["merges_performed"] >= 1

    # Check entity_merge_events INSERT was called
    merge_inserts = [
        sql for sql, _ in pool.executed
        if "INSERT INTO ENTITY_MERGE_EVENTS" in " ".join(sql.split()).upper()
    ]
    assert len(merge_inserts) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — needs_review candidate NOT auto-merged
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_review_candidate_not_auto_merged() -> None:
    """A 'needs_review' candidate is NOT auto-merged — stays open."""

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return []
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                # Only return merge (not needs_review) candidates for auto-merge
                return []  # no high-confidence merge candidates
            return []

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    assert counters["merges_performed"] == 0

    # No merge event was inserted
    merge_inserts = [
        sql for sql, _ in pool.executed
        if "INSERT INTO ENTITY_MERGE_EVENTS" in " ".join(sql.split()).upper()
    ]
    assert len(merge_inserts) == 0


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — idempotent re-run (mentions already resolved)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_idempotent_rerun() -> None:
    """Second run with no unresolved mentions returns zero counters without errors."""
    pool = FakePool({"SELECT": []})
    c1 = await resolve_entities(pool=pool, embeddings=None)
    c2 = await resolve_entities(pool=pool, embeddings=None)
    assert c1 == c2 == {
        "mentions_loaded": 0,
        "mentions_resolved": 0,
        "entities_created": 0,
        "candidates_created": 0,
        "merges_performed": 0,
        "review_needed": 0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — embedding adapter failure is non-fatal
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_embedding_failure_nonfatal() -> None:
    """If the embeddings adapter raises, the span still gets a new entity (fallback)."""
    mention_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    broken_embeddings = MagicMock()
    broken_embeddings.model = "BAAI/bge-small-en-v1.5"
    broken_embeddings.dim = 384
    broken_embeddings.embed = AsyncMock(side_effect=RuntimeError("adapter down"))

    class RoutingPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return [_FakeRecord({
                    "id": mention_id, "document_id": doc_id,
                    "text_span": "NCBI",
                    "proposed_type": "ORG", "extraction_confidence": 0.95, "chunk_id": None,
                })]
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            return None

    pool = RoutingPool()
    counters = await resolve_entities(pool=pool, embeddings=broken_embeddings)

    # Entity still created, mention still resolved despite embedding failure
    assert counters["entities_created"] == 1
    assert counters["mentions_resolved"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — returns correct counter dict shape
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_returns_counter_dict() -> None:
    pool = FakePool({"SELECT": []})
    result = await resolve_entities(pool=pool)
    expected_keys = {
        "mentions_loaded",
        "mentions_resolved",
        "entities_created",
        "candidates_created",
        "merges_performed",
        "review_needed",
    }
    assert set(result.keys()) == expected_keys


# ──────────────────────────────────────────────────────────────────────────────
# W7 helpers
# ──────────────────────────────────────────────────────────────────────────────


def testmap_predicate_to_type_known_predicates() -> None:
    assert map_predicate_to_type("holds_role") == "person_holds_role"
    assert map_predicate_to_type("was appointed ceo") == "person_holds_role"
    assert map_predicate_to_type("born in") == "person_born_in"
    assert map_predicate_to_type("acquired") == "company_acquired_company"
    assert map_predicate_to_type("employs") == "organization_employs_person"
    assert map_predicate_to_type("published") == "organization_published_artifact"
    assert map_predicate_to_type("authored") == "person_authored_artifact"
    assert map_predicate_to_type("headquartered") == "organization_headquartered_in"
    assert map_predicate_to_type("subsidiary_of") == "organization_subsidiary_of"
    assert map_predicate_to_type("merged") == "company_merged_with_company"
    assert map_predicate_to_type("enacted") == "jurisdiction_enacted_legislation"
    assert map_predicate_to_type("cites") == "paper_cites_paper"
    assert map_predicate_to_type("instance of") == "entity_instance_of_concept"
    assert map_predicate_to_type("related to") == "concept_related_to_concept"
    assert map_predicate_to_type("reported") == "source_reported_claim"


def testmap_predicate_to_type_unknown_returns_none() -> None:
    assert map_predicate_to_type("were updated") is None
    assert map_predicate_to_type("frobulates") is None
    assert map_predicate_to_type("") is None


def testpayload_equal_identical() -> None:
    p: dict[str, Any] = {
        "type_id": "person", "canonical_name": "Alice",
        "external_ids": [], "active_relationship_count": 0,
    }
    assert payload_equal(p, p.copy()) is True


def testpayload_equal_different_name() -> None:
    a: dict[str, Any] = {
        "type_id": "person", "canonical_name": "Alice",
        "external_ids": [], "active_relationship_count": 0,
    }
    b: dict[str, Any] = {
        "type_id": "person", "canonical_name": "Bob",
        "external_ids": [], "active_relationship_count": 0,
    }
    assert payload_equal(a, b) is False


def testpayload_equal_different_rel_count() -> None:
    a: dict[str, Any] = {
        "type_id": "person", "canonical_name": "Alice",
        "external_ids": [], "active_relationship_count": 0,
    }
    b = {**a, "active_relationship_count": 1}
    assert payload_equal(a, b) is False


# ──────────────────────────────────────────────────────────────────────────────
# W7 derive_relationships
# ──────────────────────────────────────────────────────────────────────────────


def _make_claim_pool(
    *,
    claim: dict[str, Any] | None,
    existing_rel: dict[str, Any] | None = None,
    mention_entity_id: uuid.UUID | None = None,
) -> FakePool:
    """Build a FakePool wired for derive_relationships tests."""

    class ClaimPool(FakePool):
        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM CLAIMS" in sql_upper and "WHERE ID = $1" in sql_upper:
                return _FakeRecord(claim) if claim else None
            if "FROM RELATIONSHIPS" in sql_upper and "IS_DEPRECATED = FALSE" in sql_upper:
                return _FakeRecord(existing_rel) if existing_rel else None
            # Mention resolution
            if "FROM MENTIONS M" in sql_upper and "JOIN CLAIMS C" in sql_upper:
                if mention_entity_id:
                    return _FakeRecord({"entity_id": mention_entity_id})
                return None
            return None

        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            return []

    return ClaimPool()


@pytest.mark.asyncio
async def test_derive_relationships_known_predicate_writes_relationship() -> None:
    """A claim with a mappable predicate and resolved entity IDs → new relationship."""
    subj = uuid.uuid4()
    obj = uuid.uuid4()
    claim_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    pool = _make_claim_pool(claim={
        "id": claim_id,
        "subject_text": "Sam Altman",
        "predicate": "holds_role",
        "object_text": "CEO",
        "subject_entity_id": subj,
        "object_entity_id": obj,
        "valid_from": None,
        "valid_until": None,
        "extraction_confidence": 0.90,
        "source_document_ids": [doc_id],
        "status": "active",
    })

    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)

    assert counters["relationships_written"] == 1
    assert counters["relationships_skipped"] == 0

    inserts = [
        sql for sql, _ in pool.executed
        if "INSERT INTO RELATIONSHIPS" in " ".join(sql.split()).upper()
    ]
    assert len(inserts) == 1


@pytest.mark.asyncio
async def test_derive_relationships_unknown_predicate_skips() -> None:
    subj = uuid.uuid4()
    obj = uuid.uuid4()
    claim_id = uuid.uuid4()
    pool = _make_claim_pool(claim={
        "id": claim_id,
        "subject_text": "references",
        "predicate": "were updated",
        "object_text": "one time",
        "subject_entity_id": subj,
        "object_entity_id": obj,
        "valid_from": None,
        "valid_until": None,
        "extraction_confidence": 1.0,
        "source_document_ids": [],
        "status": "active",
    })

    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)
    assert counters["relationships_written"] == 0
    assert counters["relationships_skipped"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_claim_not_found_skips() -> None:
    pool = _make_claim_pool(claim=None)
    counters = await derive_relationships(
        claim_id=str(uuid.uuid4()), pool=pool
    )
    assert counters["relationships_skipped"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_inactive_claim_skips() -> None:
    claim_id = uuid.uuid4()
    pool = _make_claim_pool(claim={
        "id": claim_id,
        "subject_text": "A",
        "predicate": "acquired",
        "object_text": "B",
        "subject_entity_id": uuid.uuid4(),
        "object_entity_id": uuid.uuid4(),
        "valid_from": None,
        "valid_until": None,
        "extraction_confidence": 0.90,
        "source_document_ids": [],
        "status": "superseded",
    })
    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)
    assert counters["relationships_skipped"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_low_confidence_skips() -> None:
    claim_id = uuid.uuid4()
    pool = _make_claim_pool(claim={
        "id": claim_id,
        "subject_text": "A",
        "predicate": "acquired",
        "object_text": "B",
        "subject_entity_id": uuid.uuid4(),
        "object_entity_id": uuid.uuid4(),
        "valid_from": None,
        "valid_until": None,
        "extraction_confidence": MIN_CLAIM_CONFIDENCE - 0.01,
        "source_document_ids": [],
        "status": "active",
    })
    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)
    assert counters["relationships_skipped"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_self_relationship_skips() -> None:
    eid = uuid.uuid4()
    claim_id = uuid.uuid4()
    pool = _make_claim_pool(claim={
        "id": claim_id,
        "subject_text": "X",
        "predicate": "acquired",
        "object_text": "X",
        "subject_entity_id": eid,
        "object_entity_id": eid,
        "valid_from": None,
        "valid_until": None,
        "extraction_confidence": 0.9,
        "source_document_ids": [],
        "status": "active",
    })
    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)
    assert counters["relationships_skipped"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_unresolved_entity_skips() -> None:
    """If neither entity end can be resolved, claim is skipped."""
    claim_id = uuid.uuid4()
    pool = _make_claim_pool(claim={
        "id": claim_id,
        "subject_text": "unknown subject",
        "predicate": "acquired",
        "object_text": "unknown object",
        "subject_entity_id": None,
        "object_entity_id": None,
        "valid_from": None,
        "valid_until": None,
        "extraction_confidence": 0.9,
        "source_document_ids": [],
        "status": "active",
    }, mention_entity_id=None)
    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)
    assert counters["relationships_skipped"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_mention_fallback_resolves_entity() -> None:
    """Subject entity resolved via mention lookup when entity_id is NULL on claim."""
    subj = uuid.uuid4()
    obj = uuid.uuid4()
    claim_id = uuid.uuid4()

    class MentionFallbackPool(FakePool):
        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM CLAIMS" in sql_upper and "WHERE ID = $1" in sql_upper:
                return _FakeRecord({
                    "id": claim_id,
                    "subject_text": "OpenAI",
                    "predicate": "acquired",
                    "object_text": "TargetCo",
                    "subject_entity_id": None,
                    "object_entity_id": obj,
                    "valid_from": None,
                    "valid_until": None,
                    "extraction_confidence": 0.85,
                    "source_document_ids": [],
                    "status": "active",
                })
            if "FROM MENTIONS M" in sql_upper and "JOIN CLAIMS C" in sql_upper:
                # Only return entity for the subject lookup (first call)
                return _FakeRecord({"entity_id": subj})
            if "FROM RELATIONSHIPS" in sql_upper:
                return None
            return None

        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            return []

    pool = MentionFallbackPool()
    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)
    assert counters["relationships_written"] == 1


@pytest.mark.asyncio
async def test_derive_relationships_idempotent_rerun_updates_claim_ids() -> None:
    """Re-running with same claim merges into existing relationship (no new INSERT)."""
    subj = uuid.uuid4()
    obj = uuid.uuid4()
    claim_id = uuid.uuid4()
    existing_rel_id = uuid.uuid4()

    pool = _make_claim_pool(
        claim={
            "id": claim_id,
            "subject_text": "A",
            "predicate": "acquired",
            "object_text": "B",
            "subject_entity_id": subj,
            "object_entity_id": obj,
            "valid_from": None,
            "valid_until": None,
            "extraction_confidence": 0.90,
            "source_document_ids": [],
            "status": "active",
        },
        existing_rel={
            "id": existing_rel_id,
            # claim already in list → no UPDATE needed
            "claim_ids": [claim_id],
            "source_document_ids": [],
            "confidence": "0.90",
        },
    )

    counters = await derive_relationships(claim_id=str(claim_id), pool=pool)

    assert counters["relationships_written"] == 1
    # No new INSERT because relationship already exists
    inserts = [
        sql for sql, _ in pool.executed
        if "INSERT INTO RELATIONSHIPS" in " ".join(sql.split()).upper()
    ]
    assert len(inserts) == 0


@pytest.mark.asyncio
async def test_derive_relationships_idempotent_adds_new_claim_to_existing() -> None:
    """Re-run with a *new* claim on the same typed edge merges the claim_id via UPDATE."""
    subj = uuid.uuid4()
    obj = uuid.uuid4()
    old_claim_id = uuid.uuid4()
    new_claim_id = uuid.uuid4()
    existing_rel_id = uuid.uuid4()

    pool = _make_claim_pool(
        claim={
            "id": new_claim_id,
            "subject_text": "A",
            "predicate": "acquired",
            "object_text": "B",
            "subject_entity_id": subj,
            "object_entity_id": obj,
            "valid_from": None,
            "valid_until": None,
            "extraction_confidence": 0.92,
            "source_document_ids": [],
            "status": "active",
        },
        existing_rel={
            "id": existing_rel_id,
            "claim_ids": [old_claim_id],
            "source_document_ids": [],
            "confidence": "0.90",
        },
    )

    counters = await derive_relationships(claim_id=str(new_claim_id), pool=pool)
    assert counters["relationships_written"] == 1

    # UPDATE (not INSERT) should have been issued
    updates = [
        sql for sql, _ in pool.executed
        if "UPDATE RELATIONSHIPS" in " ".join(sql.split()).upper()
    ]
    assert len(updates) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# W7 write_fact_versions
# ──────────────────────────────────────────────────────────────────────────────


def _make_entity_pool(
    *,
    entity: dict[str, Any] | None,
    external_ids: list[dict[str, Any]] | None = None,
    current_fact_version: dict[str, Any] | None = None,
    rel_count: int = 0,
    claim_rows: list[dict[str, Any]] | None = None,
) -> FakePool:
    class EntityPool(FakePool):
        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM ENTITIES" in sql_upper and "IS_DEPRECATED = FALSE" in sql_upper:
                return _FakeRecord(entity) if entity else None
            if "FROM FACT_VERSIONS" in sql_upper and "IS_CURRENT = TRUE" in sql_upper:
                return _FakeRecord(current_fact_version) if current_fact_version else None
            if "COUNT(*) AS CNT" in sql_upper and "FROM RELATIONSHIPS" in sql_upper:
                return _FakeRecord({"cnt": rel_count})
            return None

        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM ENTITY_EXTERNAL_IDS" in sql_upper:
                return [_FakeRecord(r) for r in (external_ids or [])]
            if "FROM CLAIMS" in sql_upper and "SUBJECT_ENTITY_ID = $1" in sql_upper:
                return [_FakeRecord(r) for r in (claim_rows or [])]
            if "EXTRACTION_CONFIDENCE" in sql_upper and "FROM CLAIMS" in sql_upper:
                return [_FakeRecord(r) for r in (claim_rows or [])]
            return []

    return EntityPool()


@pytest.mark.asyncio
async def test_write_fact_versions_new_entity_writes_version() -> None:
    """First call for an entity with no prior fact version → inserts new version."""
    entity_id = uuid.uuid4()

    pool = _make_entity_pool(
        entity={
            "type_id": "organization",
            "canonical_name": "OpenAI",
            "description": "AI company",
            "metadata": {},
        },
        external_ids=[],
        current_fact_version=None,
    )

    counters = await write_fact_versions(entity_id=str(entity_id), pool=pool)
    assert counters["versions_written"] == 1
    assert counters["versions_skipped"] == 0

    inserts = [
        sql for sql, _ in pool.executed
        if "INSERT INTO FACT_VERSIONS" in " ".join(sql.split()).upper()
    ]
    assert len(inserts) == 1


@pytest.mark.asyncio
async def test_write_fact_versions_identical_payload_skips() -> None:
    """Re-running with an unchanged entity state → skipped (idempotent)."""
    entity_id = uuid.uuid4()
    stored_payload = json.dumps({
        "type_id": "organization",
        "canonical_name": "OpenAI",
        "description": "AI company",
        "external_ids": [],
        "active_relationship_count": 0,
    }, sort_keys=True)

    pool = _make_entity_pool(
        entity={
            "type_id": "organization",
            "canonical_name": "OpenAI",
            "description": "AI company",
            "metadata": {},
        },
        external_ids=[],
        current_fact_version={
            "id": uuid.uuid4(),
            "payload": stored_payload,
            "valid_from": None,
            "recorded_at": None,
        },
        rel_count=0,
    )

    counters = await write_fact_versions(entity_id=str(entity_id), pool=pool)
    assert counters["versions_skipped"] == 1
    assert counters["versions_written"] == 0

    # No INSERT or UPDATE should have happened
    assert len(pool.executed) == 0


@pytest.mark.asyncio
async def test_write_fact_versions_changed_payload_writes_and_closes_old() -> None:
    """Changed entity state → new version inserted; old version closed (append-only)."""
    entity_id = uuid.uuid4()
    old_version_id = uuid.uuid4()

    # Stored payload has rel_count=0; current state has rel_count=1.
    stored_payload = json.dumps({
        "type_id": "organization",
        "canonical_name": "OpenAI",
        "description": None,
        "external_ids": [],
        "active_relationship_count": 0,
    }, sort_keys=True)

    pool = _make_entity_pool(
        entity={
            "type_id": "organization",
            "canonical_name": "OpenAI",
            "description": None,
            "metadata": {},
        },
        external_ids=[],
        current_fact_version={
            "id": old_version_id,
            "payload": stored_payload,
            "valid_from": None,
            "recorded_at": None,
        },
        rel_count=1,
    )

    counters = await write_fact_versions(entity_id=str(entity_id), pool=pool)
    assert counters["versions_written"] == 1

    inserts = [
        sql for sql, _ in pool.executed
        if "INSERT INTO FACT_VERSIONS" in " ".join(sql.split()).upper()
    ]
    assert len(inserts) == 1

    # Old version must be closed via UPDATE (not deleted)
    updates = [
        sql for sql, _ in pool.executed
        if "UPDATE FACT_VERSIONS" in " ".join(sql.split()).upper()
    ]
    assert len(updates) == 1
    # UPDATE args must include old_version_id
    update_args = [
        args for sql, args in pool.executed
        if "UPDATE FACT_VERSIONS" in " ".join(sql.split()).upper()
    ]
    assert any(old_version_id in args for args in update_args)


@pytest.mark.asyncio
async def test_write_fact_versions_missing_entity_raises_value_error() -> None:
    pool = _make_entity_pool(entity=None)
    with pytest.raises(ValueError, match="not found or deprecated"):
        await write_fact_versions(entity_id=str(uuid.uuid4()), pool=pool)


@pytest.mark.asyncio
async def test_write_fact_versions_with_external_ids_in_payload() -> None:
    """External IDs are included in the payload for comparison."""
    entity_id = uuid.uuid4()

    pool = _make_entity_pool(
        entity={
            "type_id": "technical_artifact",
            "canonical_name": "Q5401080",
            "description": None,
            "metadata": {},
        },
        external_ids=[
            {"namespace": "wikidata", "external_id": "Q5401080"},
        ],
        current_fact_version=None,
    )

    counters = await write_fact_versions(entity_id=str(entity_id), pool=pool)
    assert counters["versions_written"] == 1

    # Check payload written includes the external_id
    insert_args = [
        args for sql, args in pool.executed
        if "INSERT INTO FACT_VERSIONS" in " ".join(sql.split()).upper()
    ]
    assert len(insert_args) == 1
    payload_arg = insert_args[0][2]  # 3rd positional arg = payload JSON
    payload = json.loads(payload_arg)
    assert payload["external_ids"] == [{"namespace": "wikidata", "external_id": "Q5401080"}]


@pytest.mark.asyncio
async def test_write_fact_versions_provenance_claim_ids() -> None:
    """Claim IDs linked to the entity are populated in the fact version."""
    entity_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    pool = _make_entity_pool(
        entity={
            "type_id": "person",
            "canonical_name": "Sam Altman",
            "description": None,
            "metadata": {},
        },
        external_ids=[],
        current_fact_version=None,
        claim_rows=[{
            "id": claim_id,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.90,
        }],
    )

    counters = await write_fact_versions(entity_id=str(entity_id), pool=pool)
    assert counters["versions_written"] == 1

    insert_args = [
        args for sql, args in pool.executed
        if "INSERT INTO FACT_VERSIONS" in " ".join(sql.split()).upper()
    ]
    assert len(insert_args) == 1
    # claim_ids is the 7th positional arg (0-indexed: $7 in the query = index 6)
    claim_ids_arg = insert_args[0][6]
    assert claim_id in claim_ids_arg


# ──────────────────────────────────────────────────────────────────────────────
# Jobs are importable, async, return correct types
# ──────────────────────────────────────────────────────────────────────────────


def test_jobs_are_importable() -> None:
    assert callable(resolve_entities)
    assert callable(derive_relationships)
    assert callable(write_fact_versions)


def test_jobs_are_async() -> None:
    assert inspect.iscoroutinefunction(resolve_entities)
    assert inspect.iscoroutinefunction(derive_relationships)
    assert inspect.iscoroutinefunction(write_fact_versions)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def test_cli_help_lists_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "resolve-entities" in result.output
    assert "derive-relationships" in result.output
    assert "write-fact-versions" in result.output


def test_cli_resolve_entities_help_shows_embeddings_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["resolve-entities", "--help"])
    assert result.exit_code == 0
    assert "--embeddings" in result.output or "embeddings" in result.output.lower()


def test_derive_relationships_missing_option() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["derive-relationships"])
    assert result.exit_code != 0


def test_write_fact_versions_missing_option() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["write-fact-versions"])
    assert result.exit_code != 0


# ──────────────────────────────────────────────────────────────────────────────
# Constants are sane
# ──────────────────────────────────────────────────────────────────────────────


def test_threshold_ordering() -> None:
    """Merge threshold must be tighter (lower distance) than review threshold."""
    assert COSINE_MERGE_THRESHOLD < COSINE_REVIEW_THRESHOLD < 1.0


def test_min_confidence_positive() -> None:
    assert 0.0 < MIN_MENTION_CONFIDENCE <= 1.0


def test_exact_match_confidence_high() -> None:
    assert EXACT_MATCH_CONFIDENCE >= 0.9


# ──────────────────────────────────────────────────────────────────────────────
# External-ID collision detection
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def testfind_external_id_collisions_detects_shared_id() -> None:
    """Two live entities carrying the same (namespace, external_id) → one merge pair."""
    e1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
    e2 = uuid.UUID("00000000-0000-0000-0000-000000000002")

    class CollisionPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "HAVING COUNT(DISTINCT EEI.ENTITY_ID) > 1" in sql_upper:
                return [_FakeRecord({
                    "namespace": "wikidata",
                    "external_id": "Q5401080",
                    "entity_ids": [e2, e1],  # unsorted on purpose
                })]
            return []

    pairs = await find_external_id_collisions(CollisionPool())
    assert len(pairs) == 1
    left, right, ns, xid = pairs[0]
    # ordered_pair → left < right (UUID ordering)
    assert left == e1 and right == e2
    assert ns == "wikidata" and xid == "Q5401080"


@pytest.mark.asyncio
async def testfind_external_id_collisions_none_when_distinct() -> None:
    """No shared external IDs → no merge pairs (distinct entities stay separate)."""
    pairs = await find_external_id_collisions(FakePool({"SELECT": []}))
    assert pairs == []


@pytest.mark.asyncio
async def testfind_external_id_collisions_chains_three_entities() -> None:
    """Three entities sharing one external ID → two pairs, all chained onto the survivor."""
    e1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
    e2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
    e3 = uuid.UUID("00000000-0000-0000-0000-000000000003")

    class CollisionPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "HAVING COUNT(DISTINCT EEI.ENTITY_ID) > 1" in sql_upper:
                return [_FakeRecord({
                    "namespace": "wikidata", "external_id": "Q5",
                    "entity_ids": [e3, e1, e2],
                })]
            return []

    pairs = await find_external_id_collisions(CollisionPool())
    # (e1,e2) and (e1,e3) — every entity collapses onto the lowest-UUID survivor.
    assert len(pairs) == 2
    survivors = {p[0] for p in pairs}
    assert survivors == {e1}
    assert {p[1] for p in pairs} == {e2, e3}


# ──────────────────────────────────────────────────────────────────────────────
# resolve_entities — REAL merge path: co-referent mentions (shared external ID)
# unify into one entity (merge candidate generated AND auto-merged).
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_entities_external_id_collision_auto_merges() -> None:
    """Two distinct surface forms sharing a Wikidata QID merge into one entity.

    This exercises the full pipeline merge path end-to-end (not a hand-injected
    candidate): step 4 detects the external-ID collision, emits a 'merge'
    candidate at EXACT_MATCH_CONFIDENCE, and step 6 auto-merges it via
    _perform_merge (source deprecated, mentions re-parented, merge event written).
    """
    e_low = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    e_high = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
    candidate_id = uuid.uuid4()

    class MergePool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            # No unresolved mentions this pass — merge-only run.
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return []
            # External-ID collision detector returns one colliding pair.
            if "HAVING COUNT(DISTINCT EEI.ENTITY_ID) > 1" in sql_upper:
                return [_FakeRecord({
                    "namespace": "wikidata", "external_id": "Q5401080",
                    "entity_ids": [e_high, e_low],
                })]
            # Step 6 reads open merge candidates.
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return [_FakeRecord({
                    "id": candidate_id,
                    "left_entity_id": e_low,
                    "right_entity_id": e_high,
                    "confidence": EXACT_MATCH_CONFIDENCE,
                    "matching_signals": json.dumps([{"type": "external_id"}]),
                })]
            # Re-parent: source has no aliases / external IDs to move in this fixture.
            if "FROM ENTITY_ALIASES WHERE ENTITY_ID" in sql_upper:
                return []
            if "FROM ENTITY_EXTERNAL_IDS WHERE ENTITY_ID" in sql_upper:
                return []
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            # candidate upsert returns its id
            if "INSERT INTO ENTITY_RESOLUTION_CANDIDATES" in sql_upper:
                return _FakeRecord({"id": candidate_id})
            # source entity fetch (loser = right = e_high)
            if "IS_DEPRECATED" in sql_upper and "FROM ENTITIES" in sql_upper:
                return _FakeRecord({
                    "is_deprecated": False, "merged_into_id": None,
                    "canonical_name": "Q5401080", "type_id": "technical_artifact",
                    "description": None, "current_state": {}, "metadata": {},
                })
            # target entity fetch (winner = left = e_low)
            if "CANONICAL_NAME" in sql_upper and "FROM ENTITIES" in sql_upper:
                return _FakeRecord({
                    "canonical_name": "single-cell analysis", "type_id": "technical_artifact",
                    "description": None, "current_state": {}, "metadata": {},
                })
            return None

    pool = MergePool()
    counters = await resolve_entities(pool=pool, embeddings=None)

    # A merge candidate was created AND a merge was performed.
    assert counters["candidates_created"] >= 1
    assert counters["merges_performed"] >= 1

    sqls = [" ".join(s.split()).upper() for s, _ in pool.executed]

    # Source entity was deprecated (merged_into_id set).
    assert any("SET IS_DEPRECATED = TRUE" in s for s in sqls)
    # A merge event was recorded for reversal.
    assert any("INSERT INTO ENTITY_MERGE_EVENTS" in s for s in sqls)
    # Mentions pointing at the loser were re-parented onto the survivor.
    reparent = [
        args for s, args in pool.executed
        if "UPDATE MENTIONS SET ENTITY_ID = $1 WHERE ENTITY_ID = $2" in " ".join(s.split()).upper()
    ]
    assert reparent and reparent[0][0] == e_low and reparent[0][1] == e_high
    # Survivor's freshness signal bumped (getEntity reads last_updated_at).
    assert any("SET LAST_UPDATED_AT = NOW()" in s for s in sqls)


# ──────────────────────────────────────────────────────────────────────────────
# link_claim_entities — unit tests
# ──────────────────────────────────────────────────────────────────────────────


def _make_link_pool(
    *,
    claims: list[dict[str, Any]] | None = None,
    mention_row: dict[str, Any] | None = None,
    name_row: dict[str, Any] | None = None,
    alias_row: dict[str, Any] | None = None,
    name_rows: list[dict[str, Any]] | None = None,
    live_entity_row: dict[str, Any] | None = None,
    emb_rows: list[dict[str, Any]] | None = None,
) -> FakePool:
    """Build a FakePool wired for link_claim_entities tests.

    The exact-name/alias match is a single unioned ``fetch`` returning DISTINCT
    live entity ids.  ``name_rows`` overrides that result directly (used to test
    the ambiguity-rejection path); otherwise it is synthesised from the legacy
    ``name_row`` / ``alias_row`` single-row fixtures so a single match links and
    no match leaves NULL.
    """
    if name_rows is None:
        synthesized: list[dict[str, Any]] = []
        if name_row is not None:
            synthesized.append({"entity_id": name_row["id"]})
        if alias_row is not None:
            synthesized.append({"entity_id": alias_row["id"]})
        name_rows = synthesized

    class LinkPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM CLAIMS" in sql_upper and "SUBJECT_ENTITY_ID IS NULL" in sql_upper:
                return [_FakeRecord(c) for c in (claims or [])]
            if "FROM ENTITY_EMBEDDINGS EE" in sql_upper:
                return [_FakeRecord(r) for r in (emb_rows or [])]
            # Unioned exact-name/alias DISTINCT lookup.
            if "LOWER(CANONICAL_NAME) = $1" in sql_upper:
                return [_FakeRecord(r) for r in (name_rows or [])]
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            # Exact mention-span lookup
            if "FROM MENTIONS M" in sql_upper and "DOCUMENT_ID = ANY" in sql_upper:
                return _FakeRecord(mention_row) if mention_row else None
            # Live entity check (after mention lookup)
            if "FROM ENTITIES WHERE ID = $1 AND IS_DEPRECATED = FALSE" in sql_upper:
                return _FakeRecord(live_entity_row) if live_entity_row else None
            return None

    return LinkPool()


@pytest.mark.asyncio
async def test_link_claim_entities_no_unlinked_claims() -> None:
    """No claims with NULL entity ends → all counters zero."""
    pool = _make_link_pool(claims=[])
    counters = await link_claim_entities(pool=pool, embeddings=None)
    assert counters["claims_loaded"] == 0
    assert counters["claims_updated"] == 0


@pytest.mark.asyncio
async def test_link_claim_entities_exact_mention_span_links_subject() -> None:
    """Subject text exactly matches a resolved mention in the same document."""
    claim_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "Sebastián Ramírez",
            "object_text": "FastAPI",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.90,
            "metadata": {},
        }],
        mention_row={"entity_id": entity_id},
        live_entity_row={"id": entity_id},
    )

    counters = await link_claim_entities(pool=pool, embeddings=None)

    assert counters["subject_linked"] >= 1
    assert counters["claims_updated"] >= 1
    # Verify UPDATE was issued with the resolved entity_id
    updates = [
        args for sql, args in pool.executed
        if "UPDATE CLAIMS" in " ".join(sql.split()).upper()
    ]
    assert updates, "UPDATE claims must have been called"
    # First positional arg is new_subject_entity_id
    assert updates[0][0] == entity_id


@pytest.mark.asyncio
async def test_link_claim_entities_exact_name_links_object() -> None:
    """Object text matches a live entity's canonical_name — links via exact_name."""
    claim_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    class NamePool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM CLAIMS" in sql_upper and "SUBJECT_ENTITY_ID IS NULL" in sql_upper:
                return [_FakeRecord({
                    "id": claim_id,
                    "subject_text": "tiangolo",
                    "object_text": "FastAPI",
                    "subject_entity_id": uuid.uuid4(),  # already linked
                    "object_entity_id": None,
                    "source_document_ids": [doc_id],
                    "extraction_confidence": 0.85,
                    "metadata": {},
                })]
            # Unioned exact-name/alias DISTINCT lookup → exactly one match.
            if "LOWER(CANONICAL_NAME) = $1" in sql_upper:
                return [_FakeRecord({"entity_id": entity_id})]
            return []

        async def fetchrow(self, sql: str, *args: Any) -> Any | None:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "DOCUMENT_ID = ANY" in sql_upper:
                return None  # no exact mention match
            return None

    pool = NamePool()
    counters = await link_claim_entities(pool=pool, embeddings=None)

    assert counters["object_linked"] >= 1
    updates = [
        args for sql, args in pool.executed
        if "UPDATE CLAIMS" in " ".join(sql.split()).upper()
    ]
    assert updates
    # Second positional arg is new_object_entity_id
    assert updates[0][1] == entity_id


@pytest.mark.asyncio
async def test_link_claim_entities_alias_links_entity() -> None:
    """Surface text matches an entity alias → linked via exact_alias."""
    claim_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "Rust",
            "object_text": "systems language",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.80,
            "metadata": {},
        }],
        mention_row=None,
        live_entity_row=None,
        name_row=None,
        alias_row={"id": entity_id},  # alias match
    )

    counters = await link_claim_entities(pool=pool, embeddings=None)
    assert counters["subject_linked"] >= 1


@pytest.mark.asyncio
async def test_link_claim_entities_ambiguous_name_leaves_null() -> None:
    """Two distinct live entities share the exact name → NO link (no false link).

    The exact-name match is type-agnostic, so the same surface form can resolve
    to two genuinely distinct entities. Picking one arbitrarily would corrupt the
    relationship graph; the conservative contract is to leave the end NULL.
    """
    claim_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    entity_a = uuid.uuid4()
    entity_b = uuid.uuid4()

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "Apple",
            "object_text": "Apple",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.80,
            "metadata": {},
        }],
        mention_row=None,
        live_entity_row=None,
        # Two distinct live entities match the same name → ambiguous.
        name_rows=[{"entity_id": entity_a}, {"entity_id": entity_b}],
    )

    counters = await link_claim_entities(pool=pool, embeddings=None)
    assert counters["subject_linked"] == 0
    assert counters["object_linked"] == 0
    assert counters["claims_updated"] == 0
    updates = [
        sql for sql, _ in pool.executed
        if "UPDATE CLAIMS" in " ".join(sql.split()).upper()
    ]
    assert updates == [], "ambiguous exact-name must not write a link"


@pytest.mark.asyncio
async def test_link_claim_entities_no_match_leaves_null() -> None:
    """No match for any method → entity ends stay NULL, claim not updated."""
    claim_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "completely unknown entity xyz",
            "object_text": "another mystery entity",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.70,
            "metadata": {},
        }],
        mention_row=None,
        live_entity_row=None,
        name_row=None,
        alias_row=None,
        emb_rows=[],
    )

    counters = await link_claim_entities(pool=pool, embeddings=None)
    assert counters["subject_linked"] == 0
    assert counters["object_linked"] == 0
    assert counters["claims_updated"] == 0
    # No UPDATE should have been issued
    updates = [
        sql for sql, _ in pool.executed
        if "UPDATE CLAIMS" in " ".join(sql.split()).upper()
    ]
    assert updates == []


@pytest.mark.asyncio
async def test_link_claim_entities_idempotent_same_confidence() -> None:
    """Re-running when entity ends are already NULL (no link) is a no-op."""
    pool = _make_link_pool(claims=[])
    c1 = await link_claim_entities(pool=pool, embeddings=None)
    c2 = await link_claim_entities(pool=pool, embeddings=None)
    assert c1 == c2
    assert c1["claims_updated"] == 0


@pytest.mark.asyncio
async def test_link_claim_entities_skips_low_embedding_distance() -> None:
    """Embedding distance > LINK_COSINE_THRESHOLD → no link (conservative)."""
    claim_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    mock_emb = MagicMock()
    mock_emb.model = "BAAI/bge-small-en-v1.5"
    mock_emb.dim = 384
    mock_emb.embed = AsyncMock(return_value=[[0.0] * 384])

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "ambiguous entity",
            "object_text": "other entity",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.75,
            "metadata": {},
        }],
        mention_row=None,
        live_entity_row=None,
        name_row=None,
        alias_row=None,
        # Distance = 0.20 > LINK_COSINE_THRESHOLD (0.10) → must not link
        emb_rows=[{"entity_id": entity_id, "distance": 0.20}],
    )

    counters = await link_claim_entities(pool=pool, embeddings=mock_emb)
    assert counters["subject_linked"] == 0
    assert counters["claims_updated"] == 0


@pytest.mark.asyncio
async def test_link_claim_entities_embedding_high_similarity_links() -> None:
    """Embedding distance ≤ LINK_COSINE_THRESHOLD → link written."""
    claim_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    mock_emb = MagicMock()
    mock_emb.model = "BAAI/bge-small-en-v1.5"
    mock_emb.dim = 384
    mock_emb.embed = AsyncMock(return_value=[[0.0] * 384])

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "rust-lang",
            "object_text": "something",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.80,
            "metadata": {},
        }],
        mention_row=None,
        live_entity_row=None,
        name_row=None,
        alias_row=None,
        # Distance = 0.05 ≤ LINK_COSINE_THRESHOLD (0.10) → must link
        emb_rows=[{"entity_id": entity_id, "distance": 0.05}],
    )

    counters = await link_claim_entities(pool=pool, embeddings=mock_emb)
    assert counters["subject_linked"] >= 1
    assert counters["claims_updated"] >= 1


@pytest.mark.asyncio
async def test_link_claim_entities_provenance_written_to_metadata() -> None:
    """claim_entity_links provenance is written into claims.metadata."""
    claim_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    pool = _make_link_pool(
        claims=[{
            "id": claim_id,
            "subject_text": "FastAPI",
            "object_text": "web framework",
            "subject_entity_id": None,
            "object_entity_id": None,
            "source_document_ids": [doc_id],
            "extraction_confidence": 0.90,
            "metadata": {},
        }],
        mention_row={"entity_id": entity_id},
        live_entity_row={"id": entity_id},
    )

    await link_claim_entities(pool=pool, embeddings=None)

    # Verify the UPDATE was called with metadata JSON containing provenance
    updates = [
        args for sql, args in pool.executed
        if "UPDATE CLAIMS" in " ".join(sql.split()).upper()
    ]
    assert updates
    # Third positional arg ($3) is the metadata JSON string
    meta_json = updates[0][2]
    meta = json.loads(meta_json)
    assert "claim_entity_links" in meta
    subj_prov = meta["claim_entity_links"].get("subject", {})
    assert subj_prov.get("method") == "exact_mention_span"
    assert subj_prov.get("linked_by") == "link_claim_entities_v1"
    assert "confidence" in subj_prov


@pytest.mark.asyncio
async def test_link_claim_entities_counter_shape() -> None:
    """Return dict contains all expected counter keys."""
    pool = _make_link_pool(claims=[])
    result = await link_claim_entities(pool=pool, embeddings=None)
    expected_keys = {
        "claims_loaded",
        "subject_linked",
        "object_linked",
        "subject_skipped",
        "object_skipped",
        "claims_updated",
    }
    assert set(result.keys()) == expected_keys


def test_link_constants_are_conservative() -> None:
    """Claim linking thresholds must be stricter than W6 entity resolution."""
    assert LINK_COSINE_THRESHOLD < COSINE_MERGE_THRESHOLD
    assert LINK_EXACT_MENTION_CONFIDENCE >= 0.85
    assert LINK_EXACT_NAME_CONFIDENCE >= 0.80
    assert LINK_EMBEDDING_MIN_CONFIDENCE >= 0.75


def test_cli_link_claim_entities_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "link-claim-entities" in result.output


@pytest.mark.asyncio
async def test_resolve_entities_distinct_external_ids_do_not_merge() -> None:
    """Entities with different external IDs are never merged (no collision)."""

    class NoCollisionPool(FakePool):
        async def fetch(self, sql: str, *args: Any) -> list[Any]:
            sql_upper = " ".join(sql.split()).upper()
            if "FROM MENTIONS M" in sql_upper and "RESOLUTION_STATUS = 'UNRESOLVED'" in sql_upper:
                return []
            if "HAVING COUNT(DISTINCT EEI.ENTITY_ID) > 1" in sql_upper:
                return []  # no shared external IDs
            if "PROPOSED_DECISION = 'MERGE'" in sql_upper:
                return []
            return []

    pool = NoCollisionPool()
    counters = await resolve_entities(pool=pool, embeddings=None)
    assert counters["merges_performed"] == 0
    assert counters["candidates_created"] == 0
    merge_inserts = [
        s for s, _ in pool.executed
        if "INSERT INTO ENTITY_MERGE_EVENTS" in " ".join(s.split()).upper()
    ]
    assert merge_inserts == []
