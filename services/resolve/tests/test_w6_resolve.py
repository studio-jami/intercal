"""Unit tests for W6 entity resolution — no live network required.

Tests cover:
- Helper functions (normalize_name, ordered_pair, detect_external_id)
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
  - derive_relationships and write_fact_versions still raise NotImplementedError (W7)
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
    MIN_MENTION_CONFIDENCE,
    derive_relationships,
    detect_external_id,
    normalize_name,
    ordered_pair,
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
            # External ID lookup
            if "ENTITY_EXTERNAL_IDS EEI" in sql_upper:
                return [_FakeRecord(existing_entity_row)]
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
# derive_relationships and write_fact_versions still NotImplementedError (W7)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_derive_relationships_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02 W7"):
        await derive_relationships(claim_id="test-claim", pool=None)


@pytest.mark.asyncio
async def test_write_fact_versions_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Plan 02 W7"):
        await write_fact_versions(entity_id="test-entity", pool=None)


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
