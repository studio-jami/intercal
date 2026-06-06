# Deployment, CD, Auth & Secrets Implementation Plan

Date: 2026-06-04
Status: [ ] Active draft
Source reports: `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`; decisions `docs/decisions/0001-foundation-stack.md`, `0002-final-hosting-topology.md`; `docs/operations/resource-budget.md`
Owner: Program orchestration
Surface: secret management & fan-out, Vercel app+MCP deploy, GitHub Actions + Cloud Run pipeline CD, REST/MCP auth, backups, budget enforcement
Maps to: Program Phase D (threaded through B/C)

## Purpose

Make Intercal fully wired, reproducibly deployable, safe to expose, and self-governing on cost.
Owns the connective tissue the feature plans assume: one source of truth for secrets fanned to
every environment, app+MCP on Vercel, the Python pipeline on GitHub Actions → Cloud Run, REST
and MCP authentication, backups/restore proof, and the budget-enforcement hooks from
`docs/operations/resource-budget.md`.

## Status Legend

- [ ] Not started · [~] In progress · [x] Complete · [!] Blocked or requires decision

## Source Findings

- The app + REST API are already live on Vercel (`lntercal.vercel.app`); MCP is built but not yet
  mounted on the domain. Neon/R2/Upstash/Gemini/Vertex/GCloud are connected and verified.
- Secrets currently live in local `.env` + Vercel env + GitHub Actions secrets, fanned manually
  via API/CLI. There is no committed, repeatable fan-out tool yet.
- GitHub repo is **public** → Actions minutes are unlimited; Cloud Run/Vertex run on the yrka.io
  project (SA = owner, all APIs enabled).
- The MCP server is stateless Streamable HTTP (mountable as a Vercel route or a Cloud Run service).

## Locked Decisions

- Secrets have ONE source (a local/CI secret store); a fan-out script propagates to `.env`,
  Vercel env, GitHub Actions secrets, and Cloud Run env. No secret in tracked files.
- App + MCP deploy to Vercel (one domain): REST at `/api/v1/*`, MCP at `/api/mcp`.
- Pipeline CD: GitHub Actions scheduled workflows (default) + Cloud Run Jobs (heavy/on-demand),
  both invoking the same `python -m intercal_<svc> <job>` CLIs.
- REST auth = hashed, scoped API keys; MCP auth = OAuth 2.1 resource server.
- Cadence/throttle and provider fallback honor `docs/operations/resource-budget.md`.

## Scope Boundaries

- No secret values in git, logs, or output. `.env.example` is the only tracked env file.
- Non-commercial posture holds; any monetization/donation surface stays feature-flagged off.
- This plan owns deploy/auth/secrets/budget plumbing — not pipeline algorithms (Plan 02) or
  query bodies (Plan 03).

## Repo Guidance

- Fan-out + deploy scripts live under `scripts/ops/`; never echo secret values.
- Auth lives behind the existing ports/middleware in `packages/api` + `packages/mcp-server`.
- Cloud Run images are the existing `docker/mcp.Dockerfile` and `docker/workers.Dockerfile`
  (cloud-built via Cloud Build; never required locally).

## Target Shape

```text
scripts/ops/
  secrets-fanout.mjs        # one source -> Vercel env + GitHub secrets + Cloud Run env
  deploy-cloud-run.mjs      # build+deploy MCP service and pipeline job images
.github/workflows/
  ci.yml                    # exists
  pipeline.yml              # scheduled batch (cadence from resource-budget)
  deploy-cloud-run.yml      # on push: build+deploy Cloud Run (workers + MCP fallback)
packages/dashboard/app/api/mcp/route.ts   # MCP mounted on Vercel
packages/api/src/auth/      # API-key middleware (hash+scope+rate limit)
packages/mcp-server/src/auth/             # OAuth 2.1 resource-server
docs/operations/
  deployment.md  secrets.md  backups.md   # runbooks
```

## Cross-Stream Dependency Map

Secret fan-out → (Vercel app+MCP deploy ∥ pipeline CD on Actions/Cloud Run) → auth (REST keys,
MCP OAuth) → backups/restore → budget enforcement + cost monitoring (with Plan 04 observability).

## Workstream 1: Secret management & fan-out

Goal: One source of truth for secrets, propagated everywhere by a repeatable script.

Status: [x] Complete (2026-06-05) — Vercel + GitHub Actions fanned live; Cloud Run deferred to W4
(no service exists yet). Runbook: `docs/operations/secrets.md`.

Implementation tasks:

- [x] `scripts/ops/secrets-fanout.mjs`: reads the tracked manifest `scripts/ops/secrets.manifest.json`
      (NAMES + per-target mapping + lane; validated by `secrets.manifest.schema.json`) and the
      gitignored local `.env` (the only place values live). Pushes to Vercel env (REST API),
      GitHub Actions secrets (`gh secret set`), and Cloud Run env (`gcloud run ... --set-env-vars`,
      deferred until a service exists). Idempotent (Vercel reconciles split per-target rows into one
      unified entry; `gh`/`gcloud` overwrite), never prints values (NAME + target + action only;
      errors redacted), supports `--target vercel|github|cloudrun|all` and `--dry-run`, and lists the
      NAMES present at each target after a real run to confirm landing.
- [x] Documented the two secret lanes — `app-runtime` (the fan-out payload) vs `operator` (the
      credentials that authenticate the push; `targets: []`, never fanned) — in
      `docs/operations/secrets.md`, and clarified the operator lane (names only) in `.env.example`.
- [x] Verified each target reflects the source after a run: Vercel 4 names (prod/preview/dev);
      GitHub 23 app-runtime names (25 present incl. 2 operator-lane set earlier); Cloud Run deferred.
      Audit-2: re-laned `GCLOUD_REGION` app-runtime→operator (orphan; only the gcloud-CLI deploy uses
      it) + schema now enforces operator⇒`targets:[]`.

Exit criteria:

- [x] Changing a secret in one place (`.env`) + running the script updates all (available)
      environments with no manual steps. Cloud Run lands automatically once a service exists.

Suggested verification: `node scripts/ops/secrets-fanout.mjs --dry-run`; confirm `gh secret list`, Vercel env, Cloud Run env.

## Workstream 2: App + MCP on Vercel

Goal: Dashboard + REST + MCP on one domain, with safe promotion/rollback.

Status: [~] MCP mount complete (2026-06-05); deployment-runbook docs + rollback test pending.

Implementation tasks:

- [x] Mounted MCP at `packages/dashboard/app/api/mcp/route.ts` (POST + GET) as a stateless
      Streamable HTTP endpoint. Uses a new `handleMcpRequest(db, request)` in
      `@intercal/mcp-server` (built on the SDK's `WebStandardStreamableHTTPServerTransport`,
      `sessionIdGenerator: undefined` + `enableJsonResponse: true`) over `buildMcpServer` and the
      shared Neon-backed query layer. `runtime = 'nodejs'` (pg needs sockets), `force-dynamic`,
      `maxDuration = 30`. Sits beside the REST mount on one domain. Auth is W6 — clean seam, none
      added.
- [x] Required runtime env: the route reads `DATABASE_URL` via `@intercal/core` `loadConfig` (same
      as REST); already set on Vercel. LLM/Upstash come with W5/W6 synthesis bodies.
- [ ] Document preview-per-PR → prod-on-main flow, custom-domain cutover, and rollback in `docs/operations/deployment.md`.

Exit criteria:

- [x] `/api/mcp` serves the V1 tools to a real MCP client — verified locally against production
      Neon (initialize + tools/list + `get_entity`/`search_evidence` returning real data); live on
      the deployed domain after the prod redeploy on push.
- [ ] Prod promotion + rollback documented and tested.

Suggested verification: MCP client lists/calls tools against the deployed `/api/mcp` (e.g.
`node scripts/dev/verify-mcp.mjs https://<domain>/api/mcp`); REST `/api/v1/*` unchanged.

## Workstream 3: Pipeline CD — GitHub Actions (scheduled batch)

Goal: Recurring ingestion/extraction/etc. on free public-repo Actions, within budget cadence.

Status: [x] Complete (2026-06-05) — scheduled CD live. Runbook: `docs/operations/pipeline-cd.md`.
The schedule is enabled (Plan 02 pipeline runs end-to-end via `intercal-pipeline run|run-all`).
actionlint clean; verified by an actual `gh workflow run` against a throwaway Neon branch (small cap)
and a small idempotent prod re-run — real data landed, no duplicate canonical records, no secrets in logs.
Audit-2 (2026-06-05): **shred the Vertex SA-key file on `if: always()`** so the credential's lifetime is
bounded on success/failure/timeout (defense in depth for self-hosted/reused runners; GitHub-hosted runners
are ephemeral anyway). Rest of the workflow audited clean — no `set -x` on secret steps, `database_url_override`
never echoed, health summary is counters-only, schedule/concurrency/timeout sane, `permissions` minimal,
`setup-uv` exact-pinned + `--frozen`, non-zero exit on failure, same CLI as the W4 Cloud Run path.

Implementation tasks:

- [x] Rewrote `.github/workflows/pipeline.yml` to drive the real orchestrator (`uv run
      intercal-pipeline run-all` / `run --source-id`), not the old per-service stub. Schedule **enabled**
      `cron: "17 */6 * * *"` (6-hourly per `resource-budget.md` / `INGEST_CRON`; minute offset off `:00`
      to dodge top-of-hour drops). `setup-uv@v8.2.0` (pinned — v8+ drops the moving major tag) +
      `uv sync --all-packages --frozen`. All app-runtime
      secrets wired by NAME from the W1 fan-out; Vertex ADC built from `GOOGLE_SERVICE_ACCOUNT_KEY`
      (SA JSON → `chmod 600` `$RUNNER_TEMP` file → `GOOGLE_APPLICATION_CREDENTIALS`), Gemini fallback via
      `GEMINI_API_KEY`. Budget knobs overridable via repo `vars.*` (defaults match `resource-budget.md`).
- [x] `workflow_dispatch` inputs for ad-hoc runs: `mode` (run-all|run), `source_id`, `max_documents`,
      `no_embeddings`, and `database_url_override` (the safe-test seam → throwaway Neon branch).
- [x] Short & idempotent: `concurrency: {group: intercal-pipeline, cancel-in-progress: false}` (no
      overlapping runs; mid-flight run finishes, next queues), `timeout-minutes: 30`, least-privilege
      `permissions: {contents: read}`. Health summary (counts + status) teed to `$GITHUB_STEP_SUMMARY`;
      non-zero exit on a `failed` run so real errors fail loudly. No secret value is ever printed.

Exit criteria:

- [x] A scheduled run executes a real job within budget and is idempotent on re-run. Verified via a real
      dispatched Actions run (branch-targeted, small cap → green, rows landed) + a small prod re-run
      (idempotent: no duplicate canonical records).

Suggested verification: dispatch a job; confirm Neon/R2/Upstash deltas and no duplicate work on re-run.

## Workstream 4: Pipeline CD — Cloud Run Jobs

Goal: Heavy/on-demand pipeline + MCP fallback on Cloud Run via Cloud Build + Artifact Registry.

Status: [x] Complete (2026-06-05) — pipeline Cloud Run Job live & executed against real infra.
Runbook: `docs/operations/pipeline-cd.md` ("Cloud Run Jobs" + the Actions-vs-Cloud-Run split).
Built & verified for real (project `rich-wavelet-496206-h7`, region `us-central1`):

- **Image:** `docker/workers.Dockerfile` — fixed the same `uv sync` extras gap W3 hit
  (`--all-extras`; ImportError: aioboto3) + pinned `uv 0.10.9` + `intercal-pipeline` entrypoint.
  Cloud-built via `docker/cloudbuild.workers.yaml` → Artifact Registry repo `intercal`
  (`us-central1-docker.pkg.dev/.../intercal/pipeline`, ~282 MiB; immutable git-SHA tag + `latest`).
- **Cloud Run Job** `intercal-pipeline` (not a service): runs the same portable CLI as W3
  (`run-all` default; args overridable per execution). 1 vCPU / 2Gi, `--max-retries=0`,
  `--task-timeout=1800s`. Non-secret config via `--set-env-vars`; sensitive values via
  `--set-secrets` from **Secret Manager** (`intercal-*` — DB, R2/S3, Upstash, Gemini) — never
  plaintext env. Least-privilege runtime SA `intercal-pipeline@…` (`aiplatform.user` for the
  Vertex ADC path via Workload Identity, `secretmanager.secretAccessor`, `logging.logWriter`,
  repo-scoped `artifactregistry.reader`). LLM stays `gemini` (API key) like the proven path;
  `LLM_PRIMARY=vertex` posture + the SA role make a Vertex switch one env flag (no key file).
- **Reproducible CD:** `scripts/ops/deploy-cloud-run.mjs` (`pnpm ops:deploy-cloud-run`) does
  first-time provisioning (AR repo, SA+IAM, `.env`→Secret Manager, job create/update; values
  piped via stdin, never logged). `.github/workflows/deploy-cloud-run.yml` is the build+roll half
  on push to main (auth via `GCP_SA_KEY`) — rebuilds the image and rolls the job to the new SHA.
- **Security fix (found via the live verify):** `intercal_shared.db` logged the **full DSN
  (with password)** at pool creation/close, and `queue_redis` logged the Redis/Upstash URL —
  a secrets-in-logs violation across all three runners. Added `intercal_shared.redaction.redact_url`
  and masked both (5 unit tests).
- **Audit-2 (2026-06-06) — leaked credential purged + proof corrected.** The W4 proof execution
  cited below (`intercal-pipeline-r9vgn`) actually ran the **pre-redaction** image digest
  (`sha256:e0e5b3…`, tag `677219a`, built 23:30); the redaction fix landed in a separate image
  (`sha256:536f0c…`, tags `fc3785b`/`latest`, built 23:50, 20 min later) that was **never
  execution-verified**. As a result `r9vgn` leaked the throwaway-branch DSN — and because Neon
  shares the `neondb_owner` password project-wide, that is a **live credential** — into persistent
  Cloud Logging (`run.googleapis.com/stderr`, 2 entries). Remediation: purged the entire
  `intercal-pipeline` stderr log stream (`gcloud logging logs delete`; only writer is this job,
  stderr regenerates) → leak re-scan empty; and re-ran the job on the **fixed** `latest` image
  against a fresh throwaway branch — logs now show `…neondb_owner:***@host…` (redacted), no `npg_`.
  NOTE: the leaked value was the live `neondb_owner` password; **rotating it** (then re-running the
  W1 secret fan-out) is recommended as defense-in-depth and is left to the operator (prod-impacting,
  out of W4 scope).

Implementation tasks:

- [x] `scripts/ops/deploy-cloud-run.mjs` + `.github/workflows/deploy-cloud-run.yml` +
      `docker/cloudbuild.workers.yaml`: Cloud Build `docker/workers.Dockerfile` to Artifact
      Registry; deploy as a Cloud Run **Job** (pipeline). MCP fallback **Service** + the
      `docker/mcp.Dockerfile` build are deferred (MCP is live on Vercel, W2 — the Cloud Run MCP
      service is only a fallback; the same script extends cleanly when needed).
- [~] Cloud Scheduler: **deferred by design.** The free GitHub Actions cron (W3) owns the routine
      6-hourly schedule; Cloud Run is the heavy/on-demand path triggered manually
      (`gcloud run jobs execute`) or from CI. Adding a Scheduler→Job trigger would double-run the
      routine schedule — documented split in `pipeline-cd.md`. (One-liner to add if a heavier
      cadence ever outgrows Actions: `gcloud scheduler jobs create http … --uri …jobs/…:run`.)
- [x] Wire the CI SA auth via `GCP_SA_KEY` (`google-github-actions/auth@v2`); runtime env via
      Secret Manager (`--set-secrets`). Env is bound at the job, not echoed in CI.

Exit criteria:

- [x] A Cloud Run Job runs a pipeline job against live infra; image build is reproducible from CI.
      **Authoritative proof (audit-2, fixed image):** `gcloud run jobs execute intercal-pipeline`
      on image `pipeline:latest` (`sha256:536f0c…`, the redaction-fixed digest) → execution
      `intercal-pipeline-hnwdm` **succeeded** (`status=succeeded total_errors=0`) against a throwaway
      Neon branch (`--max-documents 2`); real data landed (branch totals: source_documents 10,
      mentions 913, entities 177, fact_versions 177; wikidata ingested 2 new docs through the full
      ingest→extract→resolve→derive→version chain). **Logs clean** — pool lines show
      `postgresql://neondb_owner:***@…` (password masked); `npg_` leak scan empty. Job restored to
      the prod `DATABASE_URL` Secret Manager binding; throwaway branch + verify secret deleted.
      (The earlier `intercal-pipeline-r9vgn` run is superseded — it used the pre-fix image and is
      recorded under the audit-2 security note above.)

Suggested verification: trigger the Cloud Run Job; confirm parity with the Actions path.

## Workstream 5: REST auth — API keys

Goal: Hashed, scoped API keys + rate limits on the REST surface.

Status: [x] Complete (2026-06-06). Runbook: `docs/operations/auth-and-rate-limits.md`. Live-verified
against a throwaway Neon branch (17/17). MCP auth (W6) seam left clean/untouched. Audit-2 (2026-06-06):
hardened the rate-limit IP-trust (prefer Vercel's trusted `x-real-ip`; never the spoofable left-most
`x-forwarded-for`), self-heal a TTL-less Upstash counter (no permanent-429 lockout) + surface EXPIRE
errors, and fixed IPv6 `::` anonymization. Re-verified live (Neon 17/17; deployed anon 200 + headers,
invalid key 401, `/api/mcp` initialize 200).

Implementation tasks:

- [x] API-key middleware in `packages/api` (`src/auth/`): SHA-256 hash lookup against `api_keys`,
      scope checks (`read`; 403 on missing), `usage_events` recording for every outcome (anonymized
      IP, no PII beyond key id), per-key/per-IP fixed-window rate limiting behind a `RateLimitStorePort`
      (`@intercal/core/src/ratelimit/`) — Upstash Redis REST adapter (shared counter) with an
      in-process fallback; 429 + `Retry-After` + `RateLimit-*`/`X-RateLimit-*` headers; fail-open on
      store outage; auth never fail-open. Public-read posture: anonymous reads allowed (tight per-IP
      limit), a valid key raises the limit. Honors `docs/operations/resource-budget.md`.
- [x] Key issuance/rotation/revocation path (operator only): `scripts/ops/keys.mjs`
      (`pnpm ops:keys issue|list|revoke`), a thin wrapper over audited `@intercal/core` lifecycle
      functions — raw key shown once, only the hash stored, no hardcoded keys / bypass.
- [x] `Authorization: Bearer <key>`; new `unauthorized`/`forbidden`/`rate_limited` codes mapped in
      `app.ts` and mirrored as typed SDK errors. Tests: 12 core (keys/scopes/store) + 12 api
      middleware (anon/valid/invalid/revoked/expired/scope/429/usage). Contracts untouched
      (`ApiError.code` is a free string).

Exit criteria:

- [x] Unauthenticated-with-a-bad-key (401) / missing-scope (403) / over-limit (429) requests are
      rejected; anonymous reads pass under a tight limit; valid scoped keys pass with a higher limit;
      usage recorded. Live-verified end to end (issue → 200 / invalid → 401 / expired → 401 /
      revoked → 401 / no-scope → 403 / 429 + headers / `usage_events` rows).

## Workstream 6: MCP auth — OAuth 2.1

Goal: MCP server as an OAuth 2.1 resource server per the current spec.

Status: [x] Complete (2026-06-06). Runbook: `docs/operations/mcp-auth.md`. Spec re-verified against
the official MCP Authorization spec for `2025-06-18` + `2025-11-25` (+ RFC 9728/8707/8414/9068, OAuth
2.1). `/api/mcp` is now an OAuth 2.1 **resource server**; the Authorization Server is an external,
env-configured integration seam (the AS is out of scope of the MCP spec). Live-verified 7/7 against
real Neon + live HTTP for the well-known document. REST auth (W5) seam left untouched.
Audit-2 (2026-06-06): **pinned the JWS `alg` allowlist** (`MCP_OAUTH_ALGORITHMS`, default `RS256`).
Without it `jose` accepts any alg the resolved JWKS key supports (an RSA key also satisfies `PS*`) —
algorithm-substitution surface. The allowlist is now passed to `jwtVerify` and a validly-signed
out-of-allowlist token is rejected (`401`). Re-verified: unit 17 + web 6 green; live 8/8 (added the
PS256-rejection check). The rest of the resource-server surface audited clean (no bypass; audience/
iss/exp enforced; PRM + `WWW-Authenticate` spec-correct; AS deferral honest).

Implementation tasks:

- [x] Protect `/api/mcp` with OAuth 2.1 resource-server validation
      (`packages/mcp-server/src/auth/`): audience-bound bearer access-token verification via `jose`
      against the AS's JWKS (signature + `iss` + `aud` [RFC 8707] + `exp`; no hand-rolled crypto),
      `read`-scope enforcement, RFC 9728 Protected Resource Metadata served at
      `/.well-known/oauth-protected-resource` (+ path-suffixed `/api/mcp`), and a spec-correct `401`
      + `WWW-Authenticate(resource_metadata, scope)` / `403 insufficient_scope`. The gate runs in
      `handleMcpRequest` before any JSON-RPC. Aligned to MCP spec `2025-06-18`/`2025-11-25`.
- [x] Public-read posture preserved (per the plan): with no AS configured, anonymous MCP reads remain
      allowed (MCP auth is OPTIONAL per spec) — the live default; enabling auth is an env-only change
      (`MCP_OAUTH_ISSUER` …). A presented-but-bad credential is a hard 401, never a silent downgrade.
- [x] Document client onboarding (`docs/operations/mcp-auth.md` + `.env.example` seam block); tests
      for token validation + scope enforcement + alg pinning (17 unit + 3 web-handler) and a live
      harness (`scripts/dev/verify-mcp-auth.mjs`, 8 checks).

Exit criteria:

- [x] MCP tools require a valid token when an AS is configured; scopes enforced (403); unauthenticated
      calls rejected (401 + `WWW-Authenticate` → PRM); audience-mismatched tokens rejected (RFC 8707);
      initialize/tools-list/tools-call still work (anonymously when auth is disabled). Live-verified
      7/7 (real Neon) + the well-known PRM document resolves over HTTP.

Deferred (explicit seam, not faked): the external Authorization Server (token issuance, RFC 7591 /
Client ID Metadata Documents registration, RFC 8414 AS metadata) is wired via `MCP_OAUTH_*` env when
an AS is provisioned. Per-principal MCP rate limiting / usage events can attach at the gate's
resolved-principal seam (Plan 04 W6).

## Workstream 7: Backups & restore proof

Goal: Provable recovery of the canonical store.

Status: [~] Implemented; live proof operator-gated (2026-06-06) — durable runbook and runnable proof path landed in
`docs/operations/backups.md` + `scripts/ops/backup-restore.mjs` (`pnpm ops:backup`,
`pnpm ops:restore-proof`, `pnpm backup:test`). The runbook documents the hosted Neon recovery lane
(branching + point-in-time restore) and the portable second-copy lane (`pg_dump --format=custom`
with optional R2/S3 upload). The proof command restores a dump into an operator-supplied fresh Neon
branch or target database and then runs a read-only heartbeat for pgvector, migrations, seeded
sources, source documents, claims, claim evidence provenance, entities, relationships, and
bitemporal fact versions. This satisfies the backup/restore portion of Plan 04 W7 without taking on
the broader deployment-path docs. Live restore execution is operator-access-gated: it needs
Postgres client tools plus a real `DATABASE_URL`/`RESTORE_DATABASE_URL` and optional R2/S3 env; in
this session `pg_dump`/`pg_restore` were not on PATH, so the real restore proof was not executed.
The script help/dry-run path is safe and value-redacted.

Implementation tasks:

- [x] Document Neon branching + point-in-time restore; add a periodic `pg_dump` to R2 as a
      portable second copy (free egress).
- [x] Restore-proof runbook: restore a dump into a fresh Neon branch and run the fixture heartbeat.
- [x] `docs/operations/backups.md`.

Exit criteria:

- [!] A documented restore reproduces a working DB and passes the heartbeat. Runnable path exists;
      live execution requires `pg_dump`/`pg_restore`, operator DB credentials, and a throwaway Neon
      branch/target.

## Workstream 8: Budget enforcement & cost monitoring

Goal: The product governs its own spend per `resource-budget.md`.

Implementation tasks:

- [ ] Implement the throttle knobs (`LLM_DAILY_REQUEST_BUDGET`, `INGEST_*`, `EXTRACT_ONLY_CHANGED`,
      `QUEUE_PROVIDER` switch) in `services/shared` config + worker CLIs.
- [ ] LLM port: enforce daily budget, prefer Vertex → Gemini fallback, cap tokens/doc.
- [ ] Emit per-provider consumption metrics for Plan 04 cost cards; auto-degrade at ~70% thresholds.

Exit criteria:

- [ ] Pipeline honors cadence + daily LLM budget; consumption is observable; budgets are not exceeded.

## Final Verification And Closeout

- `node scripts/ops/secrets-fanout.mjs --dry-run`; deploy MCP route; dispatch a pipeline job (Actions + Cloud Run);
  exercise API-key + MCP-OAuth paths; run the restore-proof; confirm budget knobs honored.
- Update `docs/operations/{deployment,secrets,backups}.md` + changelog; commit; push.

## Acceptance Criteria

- [ ] One-source secret fan-out to all four environments, scripted and value-safe.
- [ ] App + MCP live on one domain with documented promotion/rollback.
- [ ] Pipeline runs on Actions (scheduled) and Cloud Run (on-demand) from CI, within budget.
- [ ] REST API keys + MCP OAuth enforced; usage + limits recorded.
- [ ] Backups with a proven restore.
- [ ] Budget throttles + cost monitoring active; free-tier allowances respected.

## Implementation Order

1. Secret fan-out → 2. App+MCP on Vercel → 3. Actions pipeline CD → 4. Cloud Run CD → 5. REST keys → 6. MCP OAuth → 7. Backups → 8. Budget enforcement.

## Expansion Track

- Per-key billing/quota tiers; staging environment; blue/green on Cloud Run; secret rotation automation.
