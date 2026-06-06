# Plan 07 W4 — Pipeline CD on Cloud Run Jobs (heavy / on-demand)

Date: 2026-06-06
Type: feat (ops/ci)
Packages: docker, scripts/ops, .github/workflows, services/shared, docs/operations

## Summary

The Intercal pipeline now also runs as a **Cloud Run Job** for heavy/on-demand runs — the same
portable `intercal-pipeline` CLI as the GitHub Actions scheduled path (W3), built once into an
Artifact Registry image and executed on demand. Built and verified for real against live infra
(project `rich-wavelet-496206-h7`, region `us-central1`). The routine 6-hourly schedule stays on
free Actions; Cloud Run is reserved for ad-hoc/heavier runs (documented split).

## Changes

- **`docker/workers.Dockerfile`:** fixed the `uv sync` extras gap (added `--all-extras` — without
  it the run fails at adapter construction, `ImportError: aioboto3`, the same gap W3 hit); pinned
  base + `uv 0.10.9`; entrypoint is now `intercal-pipeline` (CMD `run-all`).
- **`docker/cloudbuild.workers.yaml` (new):** Cloud Build config → Artifact Registry repo
  `intercal` (`us-central1-docker.pkg.dev/.../intercal/pipeline`), immutable git-SHA tag + `latest`.
- **`scripts/ops/deploy-cloud-run.mjs` (new; `pnpm ops:deploy-cloud-run`):** idempotent operator
  deploy — ensures the AR repo, the least-privilege runtime SA (`aiplatform.user`,
  `secretmanager.secretAccessor`, `logging.logWriter`, repo-scoped `artifactregistry.reader`),
  syncs sensitive `.env` values into **Secret Manager** (`intercal-*`; piped via stdin, never
  logged), and creates/updates the Cloud Run Job (non-secret config via `--set-env-vars`, secrets
  via `--set-secrets`). `--dry-run` / `--build-only` / `--deploy-only`. Never prints a secret value.
- **`.github/workflows/deploy-cloud-run.yml` (new):** the build+roll half — on push to main
  touching the worker image / `services/**` / `uv.lock`, authenticates with `GCP_SA_KEY`, Cloud
  Builds the image, and rolls the job to the new SHA. Never sees `.env` or a secret value; the
  job's env / `--set-secrets` bindings persist across image rolls.
- **Cloud Run region knob:** `CLOUD_RUN_REGION` (default `us-central1`) is separate from the W1
  fan-out's operator-lane `GCLOUD_REGION`; documented in `.env.example`.
- **Security fix (`services/shared`):** `intercal_shared.db` logged the full Postgres DSN
  **including the password** at pool creation/close, and `queue_redis` logged the Upstash URL+token
  — a secrets-in-logs violation across Cloud Run / Actions / local. Added
  `intercal_shared.redaction.redact_url` (masks userinfo, keeps host/db/params) and applied it at
  every URL log site. 5 new unit tests.
- **Docs:** `docs/operations/pipeline-cd.md` gained the full Cloud Run deploy/run/verify steps and
  the Actions-vs-Cloud-Run split table; Plan 07 W4 marked complete.

## Verification

- **Cloud Build:** `docker/workers.Dockerfile` built and pushed to AR (`pipeline:677219a` +
  `latest`, ~282 MiB) — build `26e39176…` SUCCESS.
- **Actual Cloud Run Job execution:** `gcloud run jobs execute intercal-pipeline` → execution
  `intercal-pipeline-r9vgn` **succeeded** (`status=succeeded total_errors=0`), pointed at a
  throwaway Neon branch (small cap `--max-documents 2`). Real data landed through the full
  ingest→extract→resolve→derive→version chain (source_documents 8→10, mentions →910, entities →173,
  fact_versions →173; wikidata source ingested 2 genuinely new docs). Execution logs re-scanned —
  no secret value present (the redaction fix verified live). Throwaway branch + verify secret deleted.
- **Python gate (changed files):** ruff + ruff-format clean; pyright 0 errors; `pytest
  services/shared/tests/test_redaction.py` 5/5 green.

## Notes

- **Cloud Scheduler deferred by design:** Actions cron owns the routine schedule; adding a
  Scheduler→Job trigger would double-run it. One-liner to add later if a heavier cadence outgrows
  Actions (documented in `pipeline-cd.md`).
- **MCP fallback Service deferred:** MCP is live on Vercel (W2); the Cloud Run MCP service is only
  a fallback. The deploy script extends cleanly to add it when needed.
- LLM stays `gemini` (API key) like the proven path; `LLM_PRIMARY=vertex` + the SA's
  `aiplatform.user` role make a Vertex switch a one-flag env change (ADC from the job SA, no key file).
