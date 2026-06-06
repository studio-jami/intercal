# Plan 07 W1 — Secret management & fan-out

Date: 2026-06-05
Type: feat
Packages: scripts/ops (tooling), docs/operations

## Summary

One canonical secret SOURCE (the gitignored local `.env`) fanned out automatically to every
target — Vercel env, GitHub Actions secrets, and (deferred until a service exists) Cloud Run env —
by a tracked, idempotent, re-runnable, dry-run-capable script. A tracked manifest holds secret
NAMES + per-target mapping + lane (NEVER values). No secret value enters any tracked file, log, or
command output.

## Changes

- **`scripts/ops/secrets.manifest.json`** (+ `secrets.manifest.schema.json`) — canonical registry
  of secret/config NAMES, each tagged with a `lane` and the `targets` it maps to. Two lanes:
  `app-runtime` (the fan-out payload: `DATABASE_URL[_UNPOOLED]`, `S3_*`, `REDIS_URL` / Upstash,
  LLM keys / Vertex ADC, adapter selectors, budget knobs, `PUBLIC_API_BASE_URL`, `LOG_LEVEL`) and
  `operator` (credentials that authenticate the push itself — `VERCEL_TOKEN`, `gh`/`GITHUB_REPO`,
  `GCP_SA_KEY`, Neon/Cloudflare control-plane — `targets: []`, never fanned into app env).
- **`scripts/ops/secrets-fanout.mjs`** — Node, no extra deps. Reads the manifest + `.env`,
  propagates values per target. `--target vercel|github|cloudrun|all`, `--dry-run`. Idempotent:
  Vercel reconciles split per-target rows into one unified `production,preview,development` entry
  (PATCH existing / delete+POST on conflict); GitHub `gh secret set` overwrites; Cloud Run
  `--set-env-vars` atomic. Logs NAME + target + action only; subprocess errors redacted. After a
  real run it lists the NAMES present at each target to confirm landing (never values).
- **`docs/operations/secrets.md`** — runbook: source of truth, the two lanes, the tool, per-target
  mechanism + auth, idempotency notes, Cloud Run deferral, rules for adding a secret. Points to the
  manifest rather than duplicating the roster (drift control).
- **`.env.example`** — documented (names only) `DATABASE_URL_UNPOOLED`, Upstash REST names, and an
  operator/automation-lane block (Vercel/GitHub/GCloud/Neon/Cloudflare credentials) clarifying they
  authenticate the fan-out and are never fanned into the app.

## Verification

- `pnpm exec biome check scripts/ops/` — clean.
- `node scripts/ops/secrets-fanout.mjs --dry-run` — correct planned actions per target (names +
  targets, redacted); optional-absent names skipped, required names present.
- **Real fan-out** (operator permission):
  - **Vercel** (`intercal` project): set 4 names (`DATABASE_URL`, `DATABASE_URL_UNPOOLED`,
    `PUBLIC_API_BASE_URL`, `LOG_LEVEL`) across production/preview/development; verified by listing.
    Re-run confirmed idempotent (PATCH in place, no duplicate rows).
  - **GitHub Actions** (`JamiStudio/intercal`): set 24 app-runtime names; verified 26 present
    (the 2 extra — `GCP_SA_KEY`, `NEON_API_KEY` — are operator-lane, set manually earlier; the
    script does not re-fan them by design).
  - **Cloud Run**: deferred — no service exists yet (Plan 07 W4). Script reports a precise
    deferral; 25 names are mapped and ready once `CLOUD_RUN_SERVICE` is set.

## Notes

Vercel intentionally receives fewer names than the pipeline runtime: the dashboard is read-only and
reaches the API over HTTP via the SDK, so only DB + public-base-URL + log-level are runtime-relevant
there; the full payload goes to GitHub Actions / Cloud Run.
