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
