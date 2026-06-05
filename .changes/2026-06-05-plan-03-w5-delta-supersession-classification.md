# Plan 03 W5 audit — get_delta classifies supersession-across-the-cutoff correctly

Date: 2026-06-05
Type: fix
Packages: @intercal/core (consumed by @intercal/api, @intercal/mcp-server)

## Summary

Third fresh-context audit of W5 (`getDelta`). Found and fixed a **fact-version
classification gap**: a genuine supersession recorded *after* the delta cutoff was
mislabelled in the digest lede as a "new fact version recorded" instead of a
supersession. Change detection, citations, freshness, and token budget were already
correct; only the supersession-vs-new prose label was wrong.

## Finding (the gap)

The real pipeline (`write_fact_versions`, `services/resolve`) records a supersession
append-only: it inserts the new `is_current=true` row at `now` and **closes the OLD row
in place** (`is_current=false`, `superseded_by_id=new`) **without changing the old row's
`recorded_at`**. So for a supersession recorded after the cutoff, the closed predecessor's
`recorded_at` predates `since` and falls **outside** the `(since, until]` window — only the
new current row (`is_current=true`, `superseded_by_id=null`) is visible. The pass-2
classifier keyed supersession detection entirely off in-window closed rows, so it saw only
the new current row and reported "new fact version recorded" for what was really a
supersession. (The pass-2 unit test happened to place *both* old and new rows in-window,
which only occurs when the supersession's recording — not just its closing — lands in the
window; it did not model the canonical cross-cutoff case.)

Proven on a throwaway fork of production Neon: a real supersession of `rust`
(`recorded_at=2026-06-05T20:00Z`, old row closed) with cutoff `since=19:00Z` — the
in-window-only logic classified it as a new assertion; the correct answer is a supersession.

## Fix

No contract change required.

- **`packages/core/src/delta.ts`** — `buildDelta` now fetches the structural cross-cutoff
  signal: the set of in-window fact-version subjects that already had a version recorded
  **at/before `since`** (`priorVersionSubjectIds`). `assembleDigest` marks an in-window
  current row whose subject is in that set as a **supersession** (it replaced a pre-cutoff
  version), in addition to the existing in-window-closed-row signal. Classification is now
  **per subject** (not per row), so a subject is never counted as both superseded and new,
  and a subject with no prior version is correctly a new assertion.

## Tests

- `packages/core/src/delta.test.ts` (+2, now 16): a supersession-across-the-cutoff with
  only the new current row in-window is classified as superseded (not "new fact version")
  via `priorVersionSubjectIds`; a genuinely-new subject (no prior version) is classified as
  a new assertion (not superseded). Existing fact-version + budget + citation tests
  unchanged.

## Verification

- `pnpm lint` clean (1 pre-existing biome.json info), `pnpm typecheck` (6 packages),
  `pnpm test` (core 28, api 37, mcp-server 8, sdk, dashboard), `pnpm build` (all incl.
  dashboard).
- Contract untouched — no TypeSpec change.
- **Live (throwaway fork of production Neon, deleted after):** the fixed `buildDelta` query
  path run against a real supersession (`since=19:00Z`) now returns `superseded_subjects=1`
  with `priorVersionSubjects=1` providing the signal (was `new_assertion=1` before),
  `freshness.lastUpdated=2026-06-05T20:00Z`, cited.
- **Deployed:** `GET /api/v1/delta?topic=rust&since_date=2026-06-01T00:00:00Z` returns real
  production data — 12 cited claim changes, 7 changed entities, confidence 0.99, coverage 1,
  freshness "today". The classification fix goes live on the next Vercel redeploy.
