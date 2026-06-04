---
date: 2026-06-04
type: foundation
---

Repository reset and full foundation scaffold (Plan 00).

- Quarantined stray "Zavi" docs; repaired all broken cross-references; de-Zavi'd the
  engineering standards; standardized docs conventions (`docs/roadmaps`, `docs/decisions`).
- Recorded the June-2026 foundation stack as decision record D1–D16.
- Scaffolded the adapter-first monorepo: pnpm TS workspace (`@intercal/shared|core|api|
  mcp-server|sdk|dashboard`) + uv Python workspace (`intercal_shared` + ingest/extract/
  resolve/synthesize) with ports for storage, embeddings, llm, queue, and scheduler.
- Contracts pipeline: TypeSpec → OpenAPI 3.1 + JSON Schema → TS types + Pydantic, with a drift
  check. MCP tool inputs and REST validation consume the same generated schemas.
- SQL-first schema (26 tables, pgvector halfvec + HNSW, bitemporal fact versions, reversible
  merges) with a migration runner and seed vocabularies.
- V1 read queries (`get_entity`, `get_sources`, `get_freshness`, `search_evidence`) implemented
  through one shared query layer; `get_delta`/`verify_claim` deferred to Plan 03 with explicit
  markers. Pipeline algorithm bodies deferred to Plan 02.
- Verification ladder (`pnpm verify`), CI workflow, and `docker-compose` for local parity.
