# Plan 03 W5 audit — get_delta keeps fact-version entities in a bounded (until) window

Date: 2026-06-05
Type: fix
Packages: @intercal/core (consumed by @intercal/api, @intercal/mcp-server)

## Summary

Fourth fresh-context audit of W5 (`getDelta`). Found and fixed a **bitemporal
axis-conflation gap** in the bounded-window (`until_date` supplied) case: an entity with
a legitimately in-window fact version was dropped from `changedEntities` whenever its
`last_updated_at` had advanced past `until`, even though its fact-version change was
counted in the digest lede and its source docs were cited. The unbounded case (no
`until`) and the `since` lower bound were already correct.

## Finding (the gap)

`buildDelta`'s `changedEntities` fetch unions two **independent** bitemporal signals:

- (a) `entities.last_updated_at` moved within `(since, until]`, and
- (b) the entity had a fact version recorded within the same window — fetched separately on
  `fact_versions.recorded_at`, the authoritative change axis.

The `until` clamp `where('last_updated_at', '<=', until)` had been ANDed **outside** the
`OR`, so it also constrained branch (b). `last_updated_at` and `recorded_at` are independent
axes: a later pipeline run can bump `last_updated_at` past `until` without producing a new
in-window fact version — most commonly an identical-payload write, which
`write_fact_versions` (`services/resolve`) **skips** (no new fact version) while another
stage still advances `last_updated_at`. In that normal case the in-window fact version is a
real change, but the buggy clamp excluded its subject from `changedEntities` — so the digest
reported "N new fact version(s) recorded" in the lede and cited the backing docs, yet omitted
the corresponding entity. An internal inconsistency, and a silent miss of a fact-version
change in the `until`-bounded window.

## Fix

No contract change required.

- **`packages/core/src/delta.ts`** — moved the `until` clamp **inside** branch (a) only:
  `touched = until ? (last_updated_at > since AND last_updated_at <= until) : last_updated_at > since`.
  Branch (b) (`id IN fvSubjectIds`) is now governed purely by the fact-version `recorded_at`
  window already applied upstream, independent of the `last_updated_at` clamp. The `since`
  lower bound was already correctly inside the `OR`.

## Tests

- `packages/core/src/delta.test.ts` unchanged (28 in @intercal/core still pass). The fix is
  in the SQL-fetch path (`buildDelta`), which — per the established W5 convention — is proven
  live on Neon; the pure assembler (`assembleDigest`) keeps its deterministic unit coverage.

## Verification

- `pnpm lint` clean (1 pre-existing biome.json schema-version info), `pnpm typecheck`
  (6 packages), `pnpm test` (core 28, api 38, mcp-server 8, sdk 14, dashboard 0),
  `pnpm build` (all incl. dashboard).
- Contract untouched — no TypeSpec change.
- **Live (throwaway fork of production Neon, deleted after):** a real entity with fact
  version `recorded_at=2026-06-05T18:59:11Z` and `last_updated_at` bumped to `20:00:00Z`,
  window `(18:58Z, 19:30Z]` — the OLD query returned **0** rows (the fact-version subject
  was dropped), the FIXED query returns **1**. A control (a `last_updated_at`-only candidate
  whose timestamp is past `until` and which is not a fact-version subject) stays correctly
  **excluded** — the fix is tight, not over-broad. Goes live on the next Vercel redeploy.
