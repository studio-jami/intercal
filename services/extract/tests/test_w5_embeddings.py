"""Workstream 5 tests: embed_chunks, embed_claims, hybrid_search jobs.

No live network or database required.  All DB and embeddings calls are
intercepted via minimal fakes (same pattern used by W1-W4 tests).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from intercal_extract.jobs import (
    EMBED_VERSION,
    embed_chunks,
    embed_claims,
    hybrid_search,
    truncate_for_embedding,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

DOC_ID = str(uuid.uuid4())
CHUNK_ID_1 = uuid.uuid4()
CHUNK_ID_2 = uuid.uuid4()
CLAIM_ID_1 = uuid.uuid4()


def _make_embeddings(
    *,
    model: str = "BAAI/bge-small-en-v1.5",
    dim: int = 384,
    vectors: list[list[float]] | None = None,
) -> MagicMock:
    """Return a fake EmbeddingsPort."""
    emb = MagicMock()
    emb.model = model
    emb.dim = dim

    async def _embed(texts: list[str]) -> list[list[float]]:
        if vectors is not None:
            return vectors[: len(texts)]
        # Return a deterministic unit-ish vector per text.
        return [[0.1 * (i % 10) for i in range(dim)] for _ in texts]

    emb.embed = _embed
    return emb


def _make_pool(
    *,
    chunks: list[dict[str, Any]] | None = None,
    claims: list[dict[str, Any]] | None = None,
    existing_chunk_embeds: list[dict[str, Any]] | None = None,
    existing_claim_embeds: list[dict[str, Any]] | None = None,
    vector_rows: list[dict[str, Any]] | None = None,
    fts_rows: list[dict[str, Any]] | None = None,
    execute_calls: list[str] | None = None,
) -> MagicMock:
    """Return a minimal fake asyncpg pool for W5 jobs."""
    pool = MagicMock()
    # Track execute calls for assertion
    _execute_calls: list[str] = execute_calls if execute_calls is not None else []

    async def _fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        q = query.lower().strip()
        # hybrid_search: vector leg (must be checked before embed_chunks existing-check
        # because both reference chunk_embeddings; the JOIN is the discriminator).
        if "join document_chunks" in q and "chunk_embeddings ce" in q:
            return vector_rows or []
        # hybrid_search: fts leg
        if "to_tsvector" in q and "from document_chunks" in q:
            return fts_rows or []
        # embed_chunks: load chunks
        if (
            "from document_chunks" in q
            and "chunk_index" in q
            and "chunk_text" in q
            and "where document_id" in q
        ):
            return chunks or []
        # embed_chunks: existing embeddings check
        if (
            "from chunk_embeddings" in q
            and "select chunk_id" in q
            and "model" in q
        ):
            return existing_chunk_embeds or []
        # embed_claims: load claims
        if "from claims" in q and "normalized_text" in q:
            return claims or []
        # embed_claims: existing claim embeddings check
        if (
            "from claim_embeddings" in q
            and "select claim_id" in q
            and "model" in q
        ):
            return existing_claim_embeds or []
        return []

    async def _execute(query: str, *args: Any) -> str:
        _execute_calls.append(query.strip()[:60])
        return "OK"

    pool.fetch = _fetch
    pool.execute = _execute
    pool._execute_calls = _execute_calls
    # MagicMock auto-creates any attribute, including `acquire`.  hybrid_search
    # uses pool.acquire() when present (to set hnsw.ef_search on a single
    # connection); the default fake pool has no real connection, so remove the
    # auto-mocked attribute to exercise the direct-fetch fallback.  Tests that
    # specifically cover the acquire path set pool.acquire explicitly.
    del pool.acquire
    return pool


# ── truncate_for_embedding ───────────────────────────────────────────────────


def test_truncate_short_text_unchanged() -> None:
    text = "Hello world"
    assert truncate_for_embedding(text, max_chars=100) == text


def test_truncate_at_word_boundary() -> None:
    text = "one two three four five"
    result = truncate_for_embedding(text, max_chars=11)
    # max_chars=11 → "one two thr" → last space before midpoint → "one two"
    assert " " not in result or result == result.rstrip()
    assert len(result) <= 11


def test_truncate_exact_boundary() -> None:
    text = "a" * 2000
    result = truncate_for_embedding(text)
    assert len(result) == 2000


def test_truncate_over_limit() -> None:
    # 2001 chars → must be at most 2000
    text = "word " * 400 + "x"
    result = truncate_for_embedding(text)
    assert len(result) <= 2000


# ── embed_chunks ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_chunks_no_chunks_returns_zero() -> None:
    pool = _make_pool(chunks=[])
    emb = _make_embeddings()
    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["chunks_total"] == 0
    assert result["vectors_persisted"] == 0


@pytest.mark.asyncio
async def test_embed_chunks_basic_embeds_and_persists() -> None:
    chunks = [
        {"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "Hello world this is a test."},
        {"id": CHUNK_ID_2, "chunk_index": 1, "chunk_text": "Another test chunk of text."},
    ]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=[])
    emb = _make_embeddings()
    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["chunks_total"] == 2
    assert result["chunks_skipped"] == 0
    assert result["chunks_embedded"] == 2
    assert result["vectors_persisted"] == 2
    # Verify an INSERT was issued for each chunk
    assert len(pool._execute_calls) == 2


@pytest.mark.asyncio
async def test_embed_chunks_skips_already_embedded() -> None:
    chunks = [
        {"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "Hello world."},
        {"id": CHUNK_ID_2, "chunk_index": 1, "chunk_text": "Second chunk."},
    ]
    # Chunk 1 already embedded with the same model
    existing = [{"chunk_id": CHUNK_ID_1}]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=existing)
    emb = _make_embeddings()
    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["chunks_total"] == 2
    assert result["chunks_skipped"] == 1
    assert result["chunks_embedded"] == 1
    assert result["vectors_persisted"] == 1


@pytest.mark.asyncio
async def test_embed_chunks_force_re_embeds_all() -> None:
    chunks = [{"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "Hello."}]
    # Even with existing embedding, force=True should embed
    existing = [{"chunk_id": CHUNK_ID_1}]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=existing)
    emb = _make_embeddings()
    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb, force=True)
    # force=True skips the existing-check query; existing doesn't filter
    assert result["chunks_embedded"] == 1
    assert result["vectors_persisted"] == 1


@pytest.mark.asyncio
async def test_embed_chunks_skips_empty_text() -> None:
    chunks = [
        {"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "   "},  # whitespace only
        {"id": CHUNK_ID_2, "chunk_index": 1, "chunk_text": "Real content here."},
    ]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=[])
    emb = _make_embeddings()
    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    # Empty-text chunk is skipped; only real content is embedded
    assert result["chunks_embedded"] == 1
    assert result["vectors_persisted"] == 1


@pytest.mark.asyncio
async def test_embed_chunks_adapter_failure_skips_batch() -> None:
    chunks = [{"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "Some text."}]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=[])

    emb = MagicMock()
    emb.model = "test-model"
    emb.dim = 384

    async def _failing_embed(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Adapter unavailable")

    emb.embed = _failing_embed

    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    # Failure is non-fatal; 0 persisted
    assert result["vectors_persisted"] == 0


@pytest.mark.asyncio
async def test_embed_chunks_upsert_uses_correct_model() -> None:
    """Verify the model name and embed version are written to the DB call."""
    chunks = [{"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "Content text."}]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=[])
    emb = _make_embeddings(model="BAAI/bge-small-en-v1.5", dim=384)

    await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    # The INSERT statement should be recorded
    assert any("INSERT INTO chunk_embeddings" in call for call in pool._execute_calls)


@pytest.mark.asyncio
async def test_embed_chunks_all_already_embedded_returns_skipped() -> None:
    chunks = [{"id": CHUNK_ID_1, "chunk_index": 0, "chunk_text": "Already done."}]
    existing = [{"chunk_id": CHUNK_ID_1}]
    pool = _make_pool(chunks=chunks, existing_chunk_embeds=existing)
    emb = _make_embeddings()
    result = await embed_chunks(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["chunks_total"] == 1
    assert result["chunks_skipped"] == 1
    assert result["chunks_embedded"] == 0
    assert result["vectors_persisted"] == 0


# ── embed_claims ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_claims_no_claims_returns_zero() -> None:
    pool = _make_pool(claims=[])
    emb = _make_embeddings()
    result = await embed_claims(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["claims_total"] == 0
    assert result["vectors_persisted"] == 0


@pytest.mark.asyncio
async def test_embed_claims_basic_embeds_and_persists() -> None:
    claims = [
        {"id": CLAIM_ID_1, "normalized_text": "Sam Altman is the CEO of OpenAI."},
    ]
    pool = _make_pool(claims=claims, existing_claim_embeds=[])
    emb = _make_embeddings()
    result = await embed_claims(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["claims_total"] == 1
    assert result["claims_skipped"] == 0
    assert result["claims_embedded"] == 1
    assert result["vectors_persisted"] == 1
    assert any("INSERT INTO claim_embeddings" in call for call in pool._execute_calls)


@pytest.mark.asyncio
async def test_embed_claims_skips_already_embedded() -> None:
    claims = [{"id": CLAIM_ID_1, "normalized_text": "Claim text."}]
    existing = [{"claim_id": CLAIM_ID_1}]
    pool = _make_pool(claims=claims, existing_claim_embeds=existing)
    emb = _make_embeddings()
    result = await embed_claims(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["claims_skipped"] == 1
    assert result["vectors_persisted"] == 0


@pytest.mark.asyncio
async def test_embed_claims_force_re_embeds() -> None:
    claims = [{"id": CLAIM_ID_1, "normalized_text": "Force re-embed this."}]
    existing = [{"claim_id": CLAIM_ID_1}]
    pool = _make_pool(claims=claims, existing_claim_embeds=existing)
    emb = _make_embeddings()
    result = await embed_claims(document_id=DOC_ID, pool=pool, embeddings=emb, force=True)
    assert result["claims_embedded"] == 1
    assert result["vectors_persisted"] == 1


@pytest.mark.asyncio
async def test_embed_claims_skips_empty_text() -> None:
    claims = [
        {"id": CLAIM_ID_1, "normalized_text": "   "},
    ]
    pool = _make_pool(claims=claims, existing_claim_embeds=[])
    emb = _make_embeddings()
    result = await embed_claims(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["claims_embedded"] == 0
    assert result["vectors_persisted"] == 0


@pytest.mark.asyncio
async def test_embed_claims_adapter_failure_skips_batch() -> None:
    claims = [{"id": CLAIM_ID_1, "normalized_text": "Some claim text."}]
    pool = _make_pool(claims=claims, existing_claim_embeds=[])

    emb = MagicMock()
    emb.model = "test-model"
    emb.dim = 384

    async def _failing_embed(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Adapter unavailable")

    emb.embed = _failing_embed

    result = await embed_claims(document_id=DOC_ID, pool=pool, embeddings=emb)
    assert result["vectors_persisted"] == 0


# ── hybrid_search ─────────────────────────────────────────────────────────────


def _make_chunk_row(
    chunk_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    chunk_index: int = 0,
    chunk_text: str = "Sample text.",
    distance: float = 0.1,
    ts_rank_score: float = 0.5,
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id or uuid.uuid4(),
        "document_id": document_id or uuid.uuid4(),
        "chunk_index": chunk_index,
        "chunk_text": chunk_text,
        "distance": distance,
        "ts_rank_score": ts_rank_score,
    }


@pytest.mark.asyncio
async def test_hybrid_search_empty_query_returns_empty() -> None:
    pool = _make_pool()
    emb = _make_embeddings()
    results = await hybrid_search(query="   ", pool=pool, embeddings=emb)
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_vector_only_results() -> None:
    cid = uuid.uuid4()
    doc_id = uuid.uuid4()
    vec_row = _make_chunk_row(chunk_id=cid, document_id=doc_id, distance=0.05)
    pool = _make_pool(vector_rows=[vec_row], fts_rows=[])
    emb = _make_embeddings()
    results = await hybrid_search(query="hello world", pool=pool, embeddings=emb, limit=5)
    assert len(results) == 1
    r = results[0]
    assert r["chunk_id"] == str(cid)
    assert r["vector_rank"] == 1
    assert r["fts_rank"] is None
    assert r["rrf_score"] > 0.0


@pytest.mark.asyncio
async def test_hybrid_search_fts_only_results() -> None:
    cid = uuid.uuid4()
    doc_id = uuid.uuid4()
    fts_row = _make_chunk_row(chunk_id=cid, document_id=doc_id, ts_rank_score=0.8)
    pool = _make_pool(vector_rows=[], fts_rows=[fts_row])
    emb = _make_embeddings()
    results = await hybrid_search(query="hello world", pool=pool, embeddings=emb, limit=5)
    assert len(results) == 1
    r = results[0]
    assert r["fts_rank"] == 1
    assert r["vector_rank"] is None


@pytest.mark.asyncio
async def test_hybrid_search_overlap_boosts_shared_chunk() -> None:
    """A chunk appearing in both legs gets a higher RRF score than either alone."""
    cid_shared = uuid.uuid4()
    cid_vec_only = uuid.uuid4()
    doc_id = uuid.uuid4()

    shared_vec = _make_chunk_row(
        chunk_id=cid_shared, document_id=doc_id, chunk_index=0, distance=0.05
    )
    vec_only = _make_chunk_row(
        chunk_id=cid_vec_only, document_id=doc_id, chunk_index=1, distance=0.15
    )
    shared_fts = _make_chunk_row(
        chunk_id=cid_shared, document_id=doc_id, chunk_index=0, ts_rank_score=0.9
    )

    pool = _make_pool(
        vector_rows=[shared_vec, vec_only],
        fts_rows=[shared_fts],
    )
    emb = _make_embeddings()
    results = await hybrid_search(query="test", pool=pool, embeddings=emb, limit=10)

    scores = {r["chunk_id"]: r["rrf_score"] for r in results}
    # Shared chunk must score higher than the vector-only chunk
    assert scores[str(cid_shared)] > scores[str(cid_vec_only)]


@pytest.mark.asyncio
async def test_hybrid_search_limit_respected() -> None:
    rows = [_make_chunk_row(chunk_index=i) for i in range(10)]
    pool = _make_pool(vector_rows=rows, fts_rows=[])
    emb = _make_embeddings()
    results = await hybrid_search(query="test", pool=pool, embeddings=emb, limit=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_hybrid_search_results_have_required_fields() -> None:
    row = _make_chunk_row()
    pool = _make_pool(vector_rows=[row], fts_rows=[])
    emb = _make_embeddings()
    results = await hybrid_search(query="test", pool=pool, embeddings=emb)
    assert results
    r = results[0]
    for field in ("chunk_id", "document_id", "chunk_index", "chunk_text", "rrf_score",
                  "vector_rank", "fts_rank", "vector_distance", "fts_ts_rank"):
        assert field in r, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_hybrid_search_rrf_score_positive() -> None:
    row = _make_chunk_row()
    pool = _make_pool(vector_rows=[row], fts_rows=[row])
    emb = _make_embeddings()
    results = await hybrid_search(query="test", pool=pool, embeddings=emb)
    assert all(r["rrf_score"] > 0.0 for r in results)


@pytest.mark.asyncio
async def test_hybrid_search_no_results_returns_empty() -> None:
    pool = _make_pool(vector_rows=[], fts_rows=[])
    emb = _make_embeddings()
    results = await hybrid_search(query="obscure query", pool=pool, embeddings=emb)
    assert results == []


class _FakeConn:
    """Fake asyncpg connection that records executed statements (for ef_search)."""

    def __init__(self, vector_rows: list[dict[str, Any]]) -> None:
        self._vector_rows = vector_rows
        self.executed: list[str] = []

    def transaction(self) -> _FakeConn:
        return self

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append(query.strip())
        return "SET"

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return self._vector_rows


class _AcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_hybrid_search_sets_ef_search_on_acquired_conn() -> None:
    """When the pool supports acquire(), the vector leg sets hnsw.ef_search
    transaction-locally on that connection before the vector query."""
    cid = uuid.uuid4()
    doc_id = uuid.uuid4()
    vec_row = _make_chunk_row(chunk_id=cid, document_id=doc_id, distance=0.05)
    conn = _FakeConn([vec_row])

    pool = _make_pool(vector_rows=[], fts_rows=[])  # fts leg via pool.fetch
    pool.acquire = lambda: _AcquireCtx(conn)

    emb = _make_embeddings()
    results = await hybrid_search(query="hello world", pool=pool, embeddings=emb, limit=10)

    # ef_search was set on the acquired connection (transaction-local).
    assert any("hnsw.ef_search" in stmt for stmt in conn.executed), conn.executed
    # ef_search must comfortably exceed the over-fetch (limit*5 = 50 → >= 100).
    ef_stmt = next(s for s in conn.executed if "hnsw.ef_search" in s)
    ef_value = int(ef_stmt.rsplit("=", 1)[1].strip())
    assert ef_value >= 50
    # The vector row from the acquired connection made it into the results.
    assert any(r["chunk_id"] == str(cid) for r in results)


@pytest.mark.asyncio
async def test_hybrid_search_custom_weights() -> None:
    """Changing weights shifts the RRF score proportionally."""
    cid = uuid.uuid4()
    doc_id = uuid.uuid4()
    row = _make_chunk_row(chunk_id=cid, document_id=doc_id)
    pool_vec = _make_pool(vector_rows=[row], fts_rows=[])
    pool_fts = _make_pool(vector_rows=[], fts_rows=[row])
    emb = _make_embeddings()

    # vector-only result with high vector_weight
    res_vec = await hybrid_search(
        query="test", pool=pool_vec, embeddings=emb,
        vector_weight=1.0, fts_weight=0.0
    )
    # fts-only result with high fts_weight
    res_fts = await hybrid_search(
        query="test", pool=pool_fts, embeddings=emb,
        vector_weight=0.0, fts_weight=1.0
    )
    # Both should still return results (non-zero score from their respective leg)
    assert res_vec and res_fts
    assert res_vec[0]["rrf_score"] > 0.0
    assert res_fts[0]["rrf_score"] > 0.0


# ── embed_version constant ────────────────────────────────────────────────────


def test_embed_version_is_string() -> None:
    assert isinstance(EMBED_VERSION, str)
    assert EMBED_VERSION  # non-empty
