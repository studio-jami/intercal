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

Implementation tasks:

- [ ] `scripts/ops/secrets-fanout.mjs`: read a local secret manifest (gitignored), push to Vercel
      env (API), GitHub Actions secrets (`gh`/API), and Cloud Run env/Secret Manager; idempotent,
      never prints values, supports `--target vercel|github|cloudrun|all` and `--dry-run`.
- [ ] Document the secret lanes (app-runtime vs ops/automation) in `docs/operations/secrets.md`.
- [ ] Verify each target reflects the source after a run.

Exit criteria:

- [ ] Changing a secret in one place + running the script updates all environments with no manual steps.

Suggested verification: `node scripts/ops/secrets-fanout.mjs --dry-run`; confirm `gh secret list`, Vercel env, Cloud Run env.

## Workstream 2: App + MCP on Vercel

Goal: Dashboard + REST + MCP on one domain, with safe promotion/rollback.

Implementation tasks:

- [ ] Mount MCP at `packages/dashboard/app/api/mcp/route.ts` (stateless Streamable HTTP via the
      existing `buildMcpServer`), sharing the Neon-backed query layer.
- [ ] Ensure required runtime env on Vercel (DATABASE_URL set; add LLM/Upstash when Phase C synthesis needs them).
- [ ] Document preview-per-PR → prod-on-main flow, custom-domain cutover, and rollback in `docs/operations/deployment.md`.

Exit criteria:

- [ ] `https://<domain>/api/mcp` serves the V1 tools to an MCP client; prod promotion + rollback documented and tested.

Suggested verification: MCP client lists/calls tools against the deployed `/api/mcp`; REST `/api/v1/*` unchanged.

## Workstream 3: Pipeline CD — GitHub Actions (scheduled batch)

Goal: Recurring ingestion/extraction/etc. on free public-repo Actions, within budget cadence.

Implementation tasks:

- [ ] Finalize `.github/workflows/pipeline.yml`: cron from `INGEST_CRON`, per-run caps
      (`INGEST_MAX_DOCS_PER_RUN`), all secrets wired; enable the schedule once Plan 02 job bodies exist.
- [ ] Add a manual `workflow_dispatch` matrix for ad-hoc single-job runs.
- [ ] Keep jobs short and idempotent; respect `docs/operations/resource-budget.md`.

Exit criteria:

- [ ] A scheduled run executes a real job within budget and is idempotent on re-run.

Suggested verification: dispatch a job; confirm Neon/R2/Upstash deltas and no duplicate work on re-run.

## Workstream 4: Pipeline CD — Cloud Run Jobs

Goal: Heavy/on-demand pipeline + MCP fallback on Cloud Run via Cloud Build + Artifact Registry.

Implementation tasks:

- [ ] `scripts/ops/deploy-cloud-run.mjs` + `.github/workflows/deploy-cloud-run.yml`: Cloud Build
      the `docker/workers.Dockerfile` (and `docker/mcp.Dockerfile`) to Artifact Registry; deploy
      as Cloud Run **Jobs** (pipeline) and an optional Cloud Run **Service** (MCP fallback).
- [ ] Cloud Scheduler triggers for heavier cadences that outgrow Actions; env via Secret Manager.
- [ ] Wire the SA (already owner) auth in CI via `GCP_SA_KEY`.

Exit criteria:

- [ ] A Cloud Run Job runs a pipeline job against live infra; image build is reproducible from CI.

Suggested verification: trigger the Cloud Run Job; confirm parity with the Actions path.

## Workstream 5: REST auth — API keys

Goal: Hashed, scoped API keys + rate limits on the REST surface.

Implementation tasks:

- [ ] API-key middleware in `packages/api`: hash lookup against `api_keys`, scope checks, usage
      recording (`usage_events`), per-key rate limiting (Upstash or pgmq-backed).
- [ ] Key issuance/rotation/revocation path (operator only).
- [ ] Contract: `Authorization: Bearer <key>`; tests for authn/authz/limits.

Exit criteria:

- [ ] Unauthenticated/over-limit requests are rejected; valid scoped keys pass; usage recorded.

## Workstream 6: MCP auth — OAuth 2.1

Goal: MCP server as an OAuth 2.1 resource server per the current spec.

Implementation tasks:

- [ ] Protect `/api/mcp` with OAuth 2.1 resource-server validation (access-token verification,
      scopes), aligned to MCP spec 2025-11-25 (re-verify against any RC at build time).
- [ ] Document client onboarding; tests for token validation + scope enforcement.

Exit criteria:

- [ ] MCP tools require a valid token; scopes enforced; unauthenticated calls rejected.

## Workstream 7: Backups & restore proof

Goal: Provable recovery of the canonical store.

Implementation tasks:

- [ ] Document Neon branching + point-in-time restore; add a periodic `pg_dump` to R2 as a
      portable second copy (free egress).
- [ ] Restore-proof runbook: restore a dump into a fresh Neon branch and run the fixture heartbeat.
- [ ] `docs/operations/backups.md`.

Exit criteria:

- [ ] A documented restore reproduces a working DB and passes the heartbeat.

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
