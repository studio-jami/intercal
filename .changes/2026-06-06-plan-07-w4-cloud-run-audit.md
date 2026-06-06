# Plan 07 W4 Cloud Run CD — audit-2: leaked-credential purge + corrected proof

Date: 2026-06-06
Type: security
Services: intercal-pipeline (Cloud Run Job), ops

## Summary

Second fresh-context audit of W4 (Pipeline CD — Cloud Run Jobs). Pass 1 landed the
worker image, Cloud Build → Artifact Registry, the least-privilege Cloud Run Job +
runtime SA, the `deploy-cloud-run.mjs` operator script, the `deploy-cloud-run.yml`
build+roll workflow, and a URL-redaction fix (`intercal_shared.redaction.redact_url`)
for DSN/Redis secrets-in-logs. This pass audited the whole surface for
correctness/cohesion/security and found one real, live security defect: the cited
proof execution had leaked a live credential into persistent Cloud Logging. No
source/config change was needed — the committed code, image, SA, secret wiring, and
workflows are all correct — but the live logs and the durable roadmap proof were not.

## Security finding + remediation

- **A live DB credential leaked into Cloud Logging.** The W4 proof execution
  (`intercal-pipeline-r9vgn`) ran the **pre-redaction** image digest
  (`sha256:e0e5b3…`, tag `677219a`); the redaction fix shipped in a *separate* image
  (`sha256:536f0c…`, tags `fc3785b`/`latest`, built ~20 min later) that was never
  execution-verified. So `r9vgn` logged the full throwaway-branch DSN at asyncpg pool
  create/close. Because Neon shares the `neondb_owner` password across all branches,
  the logged value is a **live, currently-valid** credential — not a dead one.
- **Purged** the leaked entries by deleting the `intercal-pipeline` stderr log stream
  (`gcloud logging logs delete run.googleapis.com%2Fstderr`; this job is the only
  writer and stderr regenerates per run) → post-purge `npg_` leak re-scan empty.
- **Re-verified on the fixed image** (see below): pool log lines now read
  `postgresql://neondb_owner:***@…` (password masked).
- **Recommended (operator, out of W4 scope):** rotate the `neondb_owner` password and
  re-run the W1 secret fan-out, as defense-in-depth for the window the value was
  exposed. Not done here because it is prod-impacting.

## Verified correct — no change

- **Redaction completeness (Python pipeline runner).** The only credential-bearing
  log sites are `db.py` (DSN, create+close) and `queue_redis.py` (`redis_url`), both
  redacted via `redact_url`. S3 adapter logs bucket/key only (no endpoint/keys);
  source adapters log public API URLs without the token (token lives in headers);
  `factory.py` logs only that an SA-key path was promoted, never the path/contents;
  `_llm_common` retry logs `type(exc).__name__` only; CLI `print`s are
  counters/health/status. `UPSTASH_REDIS_REST_*` is not read by any Python code
  (no `Settings` field; `extra="ignore"`) — consumed only by the TS rate-limit
  adapter (W5).
- **Secret wiring.** All 9 sensitive values delivered via `--set-secrets`
  (`secretKeyRef` → Secret Manager `intercal-*`); `gcloud run jobs describe` shows no
  plaintext secret in env. Non-secret selectors/budget knobs via `--set-env-vars`.
- **Least-privilege SA.** `intercal-pipeline@…` holds exactly `aiplatform.user`,
  `secretmanager.secretAccessor`, `logging.logWriter` (project) + repo-scoped
  `artifactregistry.reader`; no editor/owner. Vertex ADC via Workload Identity (no
  key file). (Note: `secretAccessor` is project-level, not scoped to `intercal-*` —
  acceptable for a single-tenant project; tightening to per-secret bindings is a
  future hardening.)
- **Image + job config.** Pinned `python:3.12-slim` + `uv 0.10.9`,
  `uv sync --all-packages --all-extras --frozen`, immutable git-SHA + `latest` tags;
  1 vCPU / 2Gi, `--max-retries=0`, `--task-timeout=1800s`, `--parallelism=1` — within
  resource-budget caps.
- **Deploy script + CD workflow.** `deploy-cloud-run.mjs` idempotent (describe→
  create/update), secret values piped via stdin (never argv/logs). `deploy-cloud-run.yml`
  auth via `GCP_SA_KEY`, `permissions: contents: read`, build+roll only (never sees
  `.env`/secrets). `actionlint` clean on both workflows.
- **No double-schedule.** Zero Cloud Scheduler jobs in the project; the Actions cron
  (W3) owns the 6-hourly schedule, Cloud Run is on-demand only.

## Live verification

Fixed image (`pipeline:latest`, `sha256:536f0c…`) against a throwaway Neon branch
(`--max-documents 2`), branch + verify secret deleted after:

- **Execution `intercal-pipeline-hnwdm` succeeded** (`status=succeeded
  total_errors=0`); real data landed (branch totals: source_documents 10, mentions
  913, entities 177, fact_versions 177; wikidata ingested 2 new docs through the full
  ingest→extract→resolve→derive→version chain).
- **Logs clean:** pool lines redacted (`neondb_owner:***@host`), `npg_` scan empty.
- Job restored to the prod `DATABASE_URL` Secret Manager binding.
- `pnpm py:lint` / `pnpm py:typecheck` clean (0 errors); `pnpm py:test` 378 pass
  (incl. 5 redaction tests).
