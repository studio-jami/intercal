# Plan 03 W5 audit — get_delta surfaces fact-version changes (supersessions)

Date: 2026-06-05
Type: fix
Packages: @intercal/core (consumed by @intercal/api, @intercal/mcp-server)

## Summary

Second fresh-context audit of W5 (`getDelta`). Found and fixed a **change-detection correctness
gap**: pass 1 windowed changed entities only on `entities.last_updated_at`, but the substrate's
canonical change unit is the append-only `fact_versions` table (Plan 02 W7). A new fact version —
or a supersession of an older one — recorded since the cutoff is a real change even when the
underlying entity row is older, and pass 1 missed it entirely.

## Finding (the gap)

`write_fact_versions` runs as the **final** pipeline stage, so a fact version's `recorded_at` is
reliably **later** than its subject entity's `last_updated_at`. Confirmed against production Neon:
**all 155 entities** have their latest fact-version `recorded_at` after their `last_updated_at`.
A delta cutoff placed between those two timestamps therefore silently dropped the entity from
`changedEntities` even though Intercal recorded a fact version about it inside the window — and
supersessions (the highest-signal "what changed" event) were never reported at all.

## Fix

The contract's `DeltaResponse` has no fact-version field, so fact-version changes are mapped into
the shape it does carry — no contract change required:

- **`packages/core/src/delta.ts`** — `buildDelta` now fetches `fact_versions` with `recorded_at`
  in `(since, until]`, `fact_subject_type='entity'`, scoped to the topic entities + entities
  referenced by changed claims (candidate cap 200). Changed entities are the **union** of
  `last_updated_at`-detected and fact-version-subject entities, **deduped by id** (no
  double-count). `assembleDigest`:
  - classifies in-window versions into supersessions (`is_current=false` / `superseded_by_id` set
    — a closed row = one supersession event) vs new assertions (current rows whose subject has no
    closed predecessor in-window), and reports both counts in the digest lede;
  - rolls fact-version `source_document_ids` into the digest citations, so the lede note is itself
    traceable (never an un-cited assertion);
  - includes fact-version `recorded_at` in the `freshness.lastUpdated` (newest transaction time).
  - **Token-budget hardening:** the lede is now built before trimming and its *measured* token
    cost (plus a small footer allowance) is reserved, replacing the fixed 80-token guess — so the
    rendered content provably never exceeds `token_budget` even as the lede grows with the
    fact-version note.
- **`packages/core/src/db/types.ts`** — added the `fact_versions` Kysely table interface (typed
  reads only; `db/` migrations remain the schema source of truth).

## Tests

- `packages/core/src/delta.test.ts` (+4, now 14): a new fact version in the window surfaces a
  change + cites its provenance even with zero claim changes; a closed (`is_current=false`)
  in-window version is reported as a supersession and not double-counted as a new assertion; a
  fact-version subject appears in `changedEntities` even when `last_updated_at` predates the
  cutoff; empty window with no fact versions still reports no changes (no fabrication).

## Verification

- `pnpm lint` clean (1 pre-existing biome.json info), `pnpm typecheck` (6 packages),
  `pnpm test` (core 26, api 38, mcp-server 8, sdk 14), `pnpm build` (all incl. dashboard).
- Contract untouched — `pnpm contracts:check` not required (no TypeSpec change).
- **Live (throwaway fork of production Neon, deleted after):** crafted a real append-only
  supersession of the `rust` entity's fact version (`recorded_at=2026-06-05T20:00Z`, old row
  closed) and ran the compiled `getDelta`. Cutoff `since=2026-06-05T19:00Z` (after
  `rust.last_updated_at` 18:55:39, before the new version) — the `last_updated_at`-only path
  returned **0 changes**; the fixed path returns `changedEntities: 1`, lede "1 new fact version
  recorded", `freshness.lastUpdated=2026-06-05T20:00Z`, cited. Token-bound (`budget=200`) trimmed
  12→4 claims (159 est ≤ 200, coverage 0.33, "8 omitted") and the lede correctly read "1 fact
  superseded, 6 new fact versions recorded". Empty window → "No recorded changes", no fabrication.
