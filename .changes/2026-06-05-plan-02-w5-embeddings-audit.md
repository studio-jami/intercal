# Plan 02 W5 — Embeddings & hybrid retrieval audit fix

Date: 2026-06-05
Type: fix
Services: intercal-extract

## Summary

Second fresh-context audit of Workstream 5 (embeddings + hybrid retrieval
indexes). The first pass landed migration `0024` (`embedding_version` on the
three embedding tables + chunk FTS GIN index), the `embed_chunks` /
`embed_claims` / `hybrid_search` jobs, the CLIs, and 28 tests. This pass found
the embedding/versioning/metadata surface correct and closed one HNSW
query-recall gap. Stays in the W5 lane; port/adapter seam untouched.

## Change (`services/extract/src/intercal_extract/jobs.py`)

- **`hybrid_search` now sets `hnsw.ef_search` for the vector leg.** The function
  over-fetches `limit * 5` candidates for RRF fusion, but pgvector's HNSW
  `ef_search` defaults to 40 (pgvector 0.8.x), so for `limit > 8` the vector leg
  silently returned fewer candidates than the over-fetch — degraded recall with
  no error. The vector leg now acquires a single connection, opens a
  transaction, and issues `SET LOCAL hnsw.ef_search = max(40, over_fetch * 2)`
  before the cosine query. `ef_search` must be set on the same connection that
  runs the query (a pooled `pool.fetch` may land on a different backend, so a
  session-level SET would not reliably apply); `SET LOCAL` resets at transaction
  end, so nothing leaks to the next borrower. Pools without `acquire` (unit-test
  fakes) keep the direct-fetch fallback. Verified against the official pgvector
  HNSW "Query Options" docs.

## Verified correct — no change

- Index opclass ↔ query operator: `halfvec_cosine_ops` ↔ `<=>` (cosine), the
  distance bge-small-en-v1.5 is trained for.
- `halfvec(384)` dimensions; HNSW `m=16` / `ef_construction=64` defaults.
- Idempotency / versioning: `UNIQUE (chunk_id|claim_id, model)` +
  `ON CONFLICT DO UPDATE` — a changed `EMBED_VERSION`/runtime replaces in place;
  a changed model writes a new row.
- Metadata: model + dim + `embedding_version` persisted per vector row,
  consistent across `chunk_embeddings` / `document_embeddings` /
  `claim_embeddings`.
- TS query layer (`packages/core` `searchEvidence`): real V1 lexical-only
  `ILIKE` read; it reads no vectors, so the W5 schema additions cause no drift
  and there is no operator/index mismatch to fix. Upgrading evidence search to
  hybrid lexical/vector is an explicit Plan 03 task, deliberately left alone.

## Tests

+1 net W5 test (276 service tests pass; `pnpm py:lint` + `pnpm py:typecheck`
clean): the vector leg sets `hnsw.ef_search` transaction-locally on the acquired
connection and the over-fetch-scaled value comfortably exceeds the over-fetch.

## Live verification

Neon branch `br-still-water-ajmss6b6` (pgvector 0.8.1). W5 smoke test PASS
through the new `acquire()` + `SET LOCAL ef_search` path against the PgBouncer
pooler endpoint: 5 chunk + 1 claim embeddings (model/dim/version consistent),
idempotent re-run skips all, `hybrid_search` returns 5 ranked results. EXPLAIN
proof of index usability (with `enable_seqscan=off` + `SET LOCAL
hnsw.ef_search=100`): `Index Scan using idx_chunk_embeddings_hnsw` with
`Order By: (embedding <=> ...)` — the `<=>` operator engages the cosine HNSW
index. At the live 5-row scale the default plan is a seq scan purely on cost
(correct planner behaviour).
