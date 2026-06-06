# Pipeline CD — GitHub Actions (scheduled batch)

How the Intercal pipeline runs itself on a schedule, for free, within budget. This is the
**default** pipeline runner (decision D11 / Plan 07 W3). Cloud Run Jobs (Plan 07 W4) are a
parallel, on-demand path that invokes the *same* portable CLI — neither is a re-implementation.

## What runs

`.github/workflows/pipeline.yml` runs the portable orchestrator CLI:

```
uv run intercal-pipeline run-all              # every active, non-paused source
uv run intercal-pipeline run --source-id <id> # a single source
```

The CLI chains `ingest → normalize → extract → embed → resolve → link → derive → version`
(`services/pipeline`, `intercal_pipeline.run.run_pipeline`). Every stage is idempotent, so a
re-run never duplicates canonical records and only ingests genuinely new/changed documents
(`EXTRACT_ONLY_CHANGED`, dedup by `content_hash`, mention-skip on already-extracted docs).

## Schedule

- **Cadence:** every 6 hours — `cron: "17 */6 * * *"`. This tracks
  `docs/operations/resource-budget.md` (`INGEST_CRON=0 */6 * * *`).
- **Minute offset:** `:17`, not `:00`. GitHub may drop schedules queued at the top of the hour
  under load ([schedule event caveats](https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule)).
- **Static expression:** GitHub parses `cron` before any secret/var is available, so the cadence
  is pinned in the workflow file. Changing it is a one-line edit that should stay in sync with
  `INGEST_CRON` / `resource-budget.md`.
- **Public-repo note:** the repo is public, so Actions Linux minutes are unlimited; scheduled
  workflows are auto-disabled only after **60 days** of no repository activity (not a concern for
  an active program). Schedules fire from the **default branch** (`main`) only.

## Manual runs (`workflow_dispatch`)

Inputs (Actions UI or `gh workflow run pipeline.yml`):

| input                   | default    | purpose                                                        |
| ----------------------- | ---------- | -------------------------------------------------------------- |
| `mode`                  | `run-all`  | `run-all` (all active sources) or `run` (one source)           |
| `source_id`             | —          | source UUID, required when `mode=run`                          |
| `max_documents`         | `0`        | per-source doc cap for this run (`0` = `INGEST_MAX_DOCS_PER_RUN`) |
| `no_embeddings`         | `false`    | skip embedding-based resolve/link (faster; exact-match only)   |
| `database_url_override` | —          | point the run at a **throwaway Neon branch** for a safe test   |

`database_url_override` is the safe-test seam: dispatch against a disposable Neon branch DSN
(asyncpg-compatible, e.g. `postgresql://…?sslmode=require`) to exercise the full path end-to-end
without touching prod or burning the prod budget. The override is a `string` input that lands only
in the job's `DATABASE_URL` env for that run; it is never written to a tracked file.

## Budget & safety controls

- **Per-run cap:** `INGEST_MAX_DOCS_PER_RUN` (repo var, default `200`).
- **LLM:** `LLM_DAILY_REQUEST_BUDGET` (default `2000`), `LLM_MAX_OUTPUT_TOKENS` (`2048`),
  `LLM_PRIMARY=vertex`, `EXTRACT_ONLY_CHANGED=true`. The worker constructs LLMs through the shared
  budgeted runtime wrapper: the request budget is seeded from same-day real usage rows and covers
  primary + fallback attempts, Vertex is preferred, Gemini is the fallback, and successful responses
  append real request/token usage rows for Plan 04 provider-consumption cards. Embeddings are local
  fastembed (zero cost).
- **Concurrency guard:** `concurrency: { group: intercal-pipeline, cancel-in-progress: false }` —
  a scheduled and a manual run never execute concurrently; a mid-flight (idempotent) run is allowed
  to finish and the next queues behind it.
- **Timeout:** `timeout-minutes: 30`.
- **Least privilege:** `permissions: { contents: read }` — the job only reads the checked-out tree.

Override the in-code defaults without a code change by setting GitHub **repository variables**
(`vars.*`): `INGEST_MAX_DOCS_PER_RUN`, `EXTRACT_ONLY_CHANGED`, `LLM_DAILY_REQUEST_BUDGET`,
`LLM_MAX_OUTPUT_TOKENS`, `LLM_PRIMARY`, `EMBEDDINGS_BATCH_SIZE`.

## Secrets & auth

All runtime env comes from GitHub Actions **secrets**, populated by the secret fan-out
(`scripts/ops/secrets-fanout.mjs`, Plan 07 W1; see `docs/operations/secrets.md`). The workflow
consumes them by name — it holds no values.

- **Neon (`DATABASE_URL`):** the canonical store. Overridable per manual run (see above).
- **R2 / S3 (`S3_*`, `STORAGE_PROVIDER`):** raw-document archival.
- **Upstash (`REDIS_URL`, `UPSTASH_REDIS_REST_*`, `QUEUE_PROVIDER`):** queue/cache.
- **LLM:** `LLM_PROVIDER` selects the adapter. For **Vertex** (primary), the workflow writes the
  fanned `GOOGLE_SERVICE_ACCOUNT_KEY` (SA JSON) to a `chmod 600` file under `$RUNNER_TEMP` and points
  `GOOGLE_APPLICATION_CREDENTIALS` at it (standard ADC). For the **Gemini** fallback, `GEMINI_API_KEY`
  is used directly. The key file lives only in the runner's ephemeral workspace, is never echoed, and
  is shredded by an `if: always()` cleanup step so the credential never outlives the job (defense in
  depth — matters for any self-hosted/reused runner; GitHub-hosted runners are destroyed anyway).

**No secret value is ever printed.** The CLI's health summary (counters + timing + status) is the
only run output, surfaced to the job's **step summary**; logs go to stderr. The job exits non-zero
on a failed run so real errors fail loudly.

## Observability

The CLI emits a JSON `PipelineRunHealth` summary (docs fetched/new, mentions/claims extracted,
entities created/merged, relationships, fact versions, per-stage error counts, final status). The
workflow tees this into `$GITHUB_STEP_SUMMARY` so each run's counts are visible on the run page.
A `failed` status (or any unhandled error) returns a non-zero exit and marks the run red.

## Verifying a change to the workflow

1. Push the workflow to `main` (dispatch/schedule resolve the file from the default branch).
2. Create a throwaway Neon branch; get its asyncpg-compatible DSN.
3. `gh workflow run pipeline.yml -f mode=run-all -f max_documents=<small> -f database_url_override=<branch-dsn>`
4. `gh run watch <run-id>` → green; confirm row deltas on the branch; delete the branch.
5. Optionally dispatch a small **prod** run to confirm idempotency (re-run lands no duplicates).

## Cloud Run Jobs (Plan 07 W4) — heavy / on-demand runner

Cloud Run Jobs run the identical `intercal-pipeline` CLI from `docker/workers.Dockerfile` for
heavier/on-demand cadences. Same portable worker, different runner — not a re-implementation.

### What is deployed

- **Image:** `docker/workers.Dockerfile` (pinned `python:3.12-slim` + `uv 0.10.9`,
  `uv sync --all-packages --all-extras --frozen`, entrypoint `intercal-pipeline`). Built by
  **Cloud Build** (`docker/cloudbuild.workers.yaml`) and pushed to **Artifact Registry**
  (`us-central1-docker.pkg.dev/<project>/intercal/pipeline`), tagged with the immutable git SHA
  plus `latest`.
- **Cloud Run Job** `intercal-pipeline` (region `us-central1`): `run-all` by default; each
  execution may override args (`--args="run-all,--max-documents,5"`). 1 vCPU / 2Gi,
  `--max-retries=0`, `--task-timeout=1800s`, `--parallelism=1`.
- **Runtime service account** `intercal-pipeline@<project>.iam.gserviceaccount.com`,
  least-privilege: `aiplatform.user` (Vertex ADC via Workload Identity — no key file),
  `secretmanager.secretAccessor`, `logging.logWriter`, and repo-scoped `artifactregistry.reader`.
- **Env wiring:** non-secret selectors / budget knobs as plaintext `--set-env-vars`; sensitive
  values (`DATABASE_URL`, `S3_*`, `REDIS_URL`, Upstash, `GEMINI_API_KEY`) via `--set-secrets`
  bound to **Secret Manager** secrets named `intercal-<NAME>`. Plaintext env never carries a
  secret. LLM stays `gemini` (API key) like the Actions path; `LLM_PRIMARY=vertex` + the SA's
  `aiplatform.user` role make a Vertex switch a one-flag env change (ADC from the job's SA).

### Deploy (operator)

First-time provisioning + any config/secret change — from a host with `gcloud` auth and the
local `.env`:

```
pnpm ops:deploy-cloud-run            # AR repo + Cloud Build + SA/IAM + Secret Manager + job
node scripts/ops/deploy-cloud-run.mjs --dry-run     # preview, no writes
node scripts/ops/deploy-cloud-run.mjs --build-only  # rebuild image only
```

The script reads `GCLOUD_PROJECT_ID` and `CLOUD_RUN_REGION` (default `us-central1`) from `.env`,
pipes secret values to Secret Manager via stdin (never on the command line / in logs), and is
idempotent. `GCLOUD_REGION` is a *separate* operator-lane knob used only by the W1 secret fan-out's
`gcloud run services update`; the Cloud Run Job region is `CLOUD_RUN_REGION`.

### Deploy (CI)

`.github/workflows/deploy-cloud-run.yml` is the **build + roll** half: on a push to `main` that
touches `docker/workers.Dockerfile`, `docker/cloudbuild.workers.yaml`, `services/**`, or `uv.lock`,
it authenticates with `GCP_SA_KEY` (`google-github-actions/auth@v2`), Cloud Builds the image to AR,
and rolls the existing job to the new SHA. It never sees `.env` or a secret value — the job's env /
`--set-secrets` bindings (provisioned by the operator script) persist across image rolls. A
`workflow_dispatch` input `execute_after_deploy` runs a small smoke execution after the roll.

### Run / verify

```
gcloud run jobs execute intercal-pipeline --region us-central1            # all active sources
gcloud run jobs execute intercal-pipeline --region us-central1 \
  --args="run-all,--max-documents,5"                                      # small on-demand run
```

For a SAFE test, rebind `DATABASE_URL` to a throwaway-Neon-branch Secret Manager version
(`gcloud run jobs update … --update-secrets=DATABASE_URL=<verify-secret>:latest`), execute, then
restore the prod binding and delete the branch + verify secret. The job emits the same
`PipelineRunHealth` summary and exits non-zero on a failed run.

## Actions vs Cloud Run (the split)

| | GitHub Actions (`pipeline.yml`, W3) | Cloud Run Job (`intercal-pipeline`, W4) |
| --- | --- | --- |
| Role | **Routine scheduled default** (free public-repo minutes) | **Heavy / on-demand** runner |
| Trigger | `cron: "17 */6 * * *"` + `workflow_dispatch` | manual `gcloud run jobs execute` / CI dispatch |
| Worker | `uv run intercal-pipeline` on the runner | same CLI, baked into the AR image |
| Secrets | GitHub Actions secrets (W1 fan-out) | Secret Manager (`--set-secrets`) |
| Vertex ADC | SA-key file (shredded `if: always()`) | job SA / Workload Identity (no key file) |

The 6-hourly schedule lives **only** on Actions to avoid double-running. Cloud Run is reserved for
ad-hoc / heavier runs that would strain a runner. Both invoke the identical idempotent CLI, so
either can safely follow the other (dedup by `content_hash`; no duplicate canonical records).
