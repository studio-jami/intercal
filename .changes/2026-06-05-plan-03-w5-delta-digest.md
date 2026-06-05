# Plan 03 W5 — get_delta token-budgeted, cited change digest

Date: 2026-06-05
Type: feat
Packages: @intercal/core (consumed by @intercal/api, @intercal/mcp-server)

## Summary

Implemented the deferred `getDelta` query body — the "what changed about a topic since my cutoff"
digest. It returns a compact, token-bounded, fully-cited, confidence-scored, freshness-aware
`DeltaResponse` over the claims/entities/relationships whose **transaction time** falls in
`(since_date, until_date]`, scoped to a topic. REST `/api/v1/delta` and MCP `get_delta` now return
real data instead of `501 not_implemented`. `verify_claim` (W6) remains an honest deferred seam.

## Decision — deterministic, not LLM-synthesised

The contract's `DeltaResponse` carries the change set **structurally** (`changedClaims: Claim[]`
each with its own `evidence`+`confidence`, `changedEntities: EntitySummary[]`, and a
`summary: Digest` whose `content` is a deterministic prose lede + citation-numbered change lines).
Every asserted line is built from a real row and traces to a source document — nothing to
fabricate. No LLM client exists in `packages/core`, and adding provider logic there would cross the
adapter port boundary (AGENTS.md hard rule). Per the W5 steering, a correct deterministic fully-
cited digest is preferred over an uncited LLM blob. Optional provider-backed prose polishing is a
clean later seam behind `LlmPort` that may only rephrase already-cited content.

## Changes

- **`packages/core/src/delta.ts` (new).** `buildDelta` (DB fetch) + pure, DB-free `assembleDigest`
  (rank → token-budget trim → cite → score → render).
  - **Temporal axis:** claims via `created_at` (their transaction-time column), relationships via
    `recorded_at`, changed entities via `last_updated_at`; window `(since, until]`.
  - **Scope:** resolves `topic` to entity IDs (canonical name + alias), OR matches claim text, so
    unresolved topics still surface their changed claims.
  - **Token budget:** honours `token_budget` (clamped [200, 8000], default 1500); ranks
    most-recent → most-confident → most-evidence; trims when the next line would exceed budget;
    reports included-vs-omitted and a coverage fraction (never silently lossy). ~4 chars/token
    deterministic estimate.
  - **Provenance:** digest-level citations enriched with `url`+`publishedAt`; each `Claim` keeps
    its own `evidence`. Confidence = mean extraction confidence, method `aggregate_extraction`.
    Freshness = newest transaction time + coverage.
- **`packages/core/src/queries.ts`.** `getDelta` is now a thin dispatch to `buildDelta`;
  `DeltaParams` moved to `delta.ts` and re-exported (single definition).
- **`packages/mcp-server/src/server.ts`.** Server `instructions` updated: `get_delta` is live,
  only `verify_claim` is deferred.

## Tests

- `packages/core/src/delta.test.ts` (10) — pure `assembleDigest`: every included claim cited +
  digest citations carry url/publishedAt; no fabrication on empty change set (0 confidence);
  budget bound + omission reporting + coverage; ranking (recency, confidence tiebreak); mean
  confidence + freshness; compact changed-entity summaries + relationship-change prose note.
- Updated the two MCP deferred-seam tests (`server.test.ts`, `web.test.ts`) and the API delta
  tests (`app.test.ts`) to assert against `verify_claim` (still deferred); `get_delta`'s success
  path is DB-backed and covered by the live Neon verification, not the null-DB suites.

## Verification

- `pnpm lint` — repo-wide clean (1 info = pre-existing biome.json schema-version drift).
- `pnpm typecheck` — all 6 TS packages.
- `pnpm test` — core 22 (incl. 10 new delta), api 38, mcp-server 8, sdk 14.
- `pnpm build` — all packages incl. the Next.js dashboard (mounts `/api/v1` + `/api/mcp`).
- `pnpm contracts:check` — no drift (contract untouched; the existing `DeltaResponse` shape was
  sufficient).
- **Live (production Neon, real Plan-02 Node/Rust/K8s data):** `getDelta` run via the compiled
  core. `topic=rust since=2026-06-01 budget=600` → 12 cited changes, 315 est tokens ≤ 600,
  confidence 0.99, coverage 1, every claim cited. `budget=120→clamped 200` → trims 12→4 (143 est
  tokens ≤ 200), coverage 0.33, "8 omitted". `topic=node` → 8 cited changes. `since=2026-06-10`
  (after ingest) → empty set, no fabrication. Deployed `/api/v1/delta` + MCP `get_delta` go live
  on the next Vercel deploy of main (same code path).
