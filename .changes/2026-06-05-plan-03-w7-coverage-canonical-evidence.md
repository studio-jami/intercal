# Plan 03 W7 — coverage reads canonical claim_evidence (not denormalized source_document_ids)

Date: 2026-06-05
Type: fix
Packages: @intercal/core (consumed by @intercal/api, @intercal/mcp-server)

## Summary

Audit pass 3 over the W7 freshness/coverage report. The evidence-depth `coverage` numerator and the
distinct-source breadth count are now computed from the **canonical `claim_evidence` join table**
instead of the denormalized `claims.source_document_ids` array. No contract change, no change to the
pure `assembleFreshness` logic or its tests, and — verified on production — no change to current
coverage values. This is a correctness/robustness fix: the metric now reads the authoritative
provenance table.

## Why

- The schema is explicit: migration `db/migrations/0013_claims.sql` labels `claims.source_document_ids`
  a "denormalized fast lookup; canonical is claim_evidence", and `claim_evidence`'s table comment
  states the invariant "every claim surfaced publicly must have at least one evidence row."
- The AGENTS.md provenance rule is defined on `claim_evidence` ("every public fact must trace to
  claim evidence → source documents"). Coverage exists to measure that provenance honestly, so it
  must read the canonical table, not a denormalized convenience column.
- The extract pipeline (`services/extract/src/intercal_extract/jobs.py`) writes `source_document_ids`
  (in the `INSERT INTO claims`) and the `claim_evidence` rows in **separate, non-transactional
  statements**, so the two representations CAN diverge. A coverage metric basing provenance honesty
  on the non-canonical side is fragile.

## Changes

- **`packages/core/src/queries.ts`** — `getFreshness` now LEFT JOINs `claim_evidence` onto active
  claims for the target entity. A claim counts as evidenced iff it has ≥1 canonical evidence row;
  corroboration breadth = distinct `claim_evidence.document_id`. Replaces the prior loop over
  `claims.source_document_ids`. The pure `assembleFreshness` call site and its inputs
  (`activeClaimCount` / `evidencedClaimCount` / `distinctSourceCount`) are unchanged in shape.
- **`packages/core/src/db/types.ts`** — added a read-only `ClaimEvidenceTable` Kysely interface
  (mirrors migration 0013) and registered `claim_evidence` on the `Database` interface. Read-only
  mirror only; SQL migrations remain the schema source of truth.

## Tests

- `packages/core/src/freshness.test.ts` (14) unchanged and green — the pure assembler is unaffected;
  the fetch change is exercised by the live Neon verification (same fetch/pure split as
  delta.test.ts / verify.test.ts).

## Verification

- `pnpm lint` — clean (1 info = pre-existing biome.json schema-version drift).
- `pnpm typecheck` — all 6 TS packages incl. the Next.js dashboard.
- `pnpm --filter @intercal/core build` — clean.
- `pnpm test` — `@intercal/core` 71 (14 freshness), `@intercal/api` 35, `@intercal/mcp-server` 7.
- **Live (production Neon, project `fancy-boat-93020425`):** the denormalized array and canonical
  `claim_evidence` are currently identical — 114/114 active claims evidenced both ways, zero
  per-claim set-difference — so the switch preserves today's values exactly while reading the
  authoritative table. Coverage via the canonical path: `Antoine du Hamel` 6/6 → `1.0` thin;
  `rust` / `Rustdoc` → `1.0` thin; `kubernetes` (0 claims) → `0` no-recorded-knowledge; unknown
  topic → `0`. No fabricated coverage in any case.
