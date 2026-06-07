# Introduction

Intercal is an open, provenance-backed temporal knowledge substrate for agents and LLM apps. It turns source documents into extracted claims, resolved entities, typed temporal relationships, and append-only bitemporal fact versions.

The public product surface is same-origin on `https://intercal.jami.studio`:

- Human routes under `/` for entities, topics, graph/timeline exploration, evidence search, deltas, claim verification, freshness, coverage, subscriptions, feedback, and operator readouts.
- REST under `/api/v1/*`.
- Generated OpenAPI at `/api/openapi.json`.
- MCP Streamable HTTP at `/api/mcp`.
- Documentation under `/docs`.
- Agent-readable exports at `/llms.txt` and `/llms-full.txt`.
- Crawl metadata at `/sitemap.xml`, `/robots.txt`, canonical page metadata, structured data, and
  a source-owned share image route for OpenGraph/Twitter previews.

Intercal does not maintain a separate docs-only knowledge model. Public UI, REST, SDK, and MCP all read the same contracts and query layer. If a public page cannot back a statement with evidence, it must show an explicit unknown, unavailable, stale, thin, or coverage-gap state.

The `/ai-history` page gives crawlers and agents a concise public explanation of Intercal's role
without duplicating the docs export or claiming broader coverage than the live corpus gates prove.

## Current launch posture

The live code proves the V1 query surface: `get_entity`, `get_sources`, `get_freshness`, `search_evidence`, `get_delta`, and `verify_claim`. The corpus has a bounded reviewed broad AI-history proof slice and quality gates; it is not a claim of continuous full-web saturation. Public coverage language should stay no broader than the last passing live corpus gate.

## Source of truth

- TypeSpec in `packages/shared/typespec/main.tsp` owns the contract.
- SQL migrations in `db/` own schema, constraints, indexes, and seeds.
- `@intercal/core` owns read semantics shared by REST, SDK, MCP, and dashboard pages.
- `services/shared` owns adapter ports and provider-swappable source/LLM/storage/queue boundaries.
- Durable docs explain the live system; they do not replace it.
