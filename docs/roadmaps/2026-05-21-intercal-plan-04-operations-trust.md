# Operations, Trust, And Review Loops Implementation Plan

Date: 2026-05-21
Aligned: 2026-06-04 to live stack
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`, `docs/architecture/deployment-topology.md`, `docs/architecture/provider-boundaries.md`; decisions `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`
Owner: Main orchestration agent
Surface: auth, rate limits, source policy, audit events, subscriptions, feedback/review records, observability, deployment, account setup

## Purpose

Build the operational and trust systems required to run Intercal as a reliable open knowledge service. This plan owns access control, source policy, auditability, subscriptions, bounded feedback/review loops, observability, deployment paths, backups, and one-time account/CLI setup runbooks.

## Live Alignment (2026-06-04)

This plan is **Phase D** of the master program (jointly with Plan 07 which owns deploy/CD/secret-fan-out; see `docs/roadmaps/2026-06-04-intercal-program.md`). The app and API are already live on Vercel reading Neon.

Concrete providers and topology (decisions `0001`/`0002`):
- **Auth:** API keys (hashed + scoped) for REST; OAuth 2.1 resource-server for MCP at `/api/mcp`. Plan 07 owns the deploy/CD/secret-fan-out automation (one source fanned to local `.env`, Vercel env, GitHub Actions secrets, Cloud Run env).
- **DB:** Neon direct. No local Docker in the maintainers' flow; `docker compose` is optional self-host. Ops DB checks run against `DATABASE_URL` (a Neon branch or prod).
- **Queue/cache:** Upstash Redis (TCP) behind `QueuePort`.
- **Storage:** Cloudflare R2 (S3 API) behind `StoragePort`.
- **Workers/scheduler:** GitHub Actions scheduled workflows (batch) + Cloud Run Jobs (on-demand). Cadence respects `docs/operations/resource-budget.md`.
- **Observability:** must include per-provider consumption vs. the free-tier budget (Neon, R2, Upstash, Vertex AI / Gemini daily cap, GitHub Actions minutes) in addition to source/run health, latency/error, and freshness metrics.

See also: `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`, `docs/operations/resource-budget.md`, `docs/roadmaps/2026-06-04-intercal-program.md`.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- Plans 01-03 provide schema, pipeline, API, MCP, SDK, providers, embeddings, and query surfaces.
- The foundation report requires source storage/citation/redistribution policy.
- Public user-facing surfaces remain read-only for canonical graph data.
- Users may submit feedback or flags, but public users must not directly mutate sources, claims, entities, merges, or relationships.
- Deployment must support the decided topology: app+MCP on Vercel, pipeline on GitHub Actions + Cloud Run Jobs. VPS one-box is documented as an alternative self-host path. Plan 07 owns deploy/CD/secret-fan-out automation.
- A dedicated human/agent account setup session is expected for cloud accounts, domains, CLIs, and secrets.

## Locked Decisions

- API keys are hashed and scoped.
- Source policy is enforced before content is stored or exposed.
- Feedback creates review records; it does not mutate canonical graph data.
- Subscriptions can notify agents/users without requiring broad polling.
- Audit events are required for trust-sensitive actions.
- Deployment docs must remain provider-portable.

## Non-Goals

- [ ] Do not build the full public interactive UX in this plan.
- [ ] Do not allow public users to submit direct graph mutations.
- [ ] Do not commit provider credentials or account-specific secrets.
- [ ] Do not make a single hosting provider part of the product architecture.
- [ ] Do not skip backup/restore proof for hosted paths.

## Repo Guidance

- Security and deployment rules belong in durable docs, not dated plans.
- Provider-specific setup belongs in runbooks with substitution points.
- Operations scripts must be Windows-native friendly where local execution is expected. DB checks run against `DATABASE_URL` (a Neon branch) — not a local Docker database.
- API/MCP behavior changes require contract and snapshot updates.
- Changelog fragments are required for security, deployment, operations, package, CI, or schema changes.

## Target Product Shape

Intercal can be operated locally, on a VPS, or through managed services with auth, source policy enforcement, audit events, subscriptions, feedback review records, observability, backups, restore proof, and documented account setup.

## Cross-Stream Dependency Map

Auth/rate limits -> source policy -> audit events -> feedback/review records -> subscriptions -> observability -> deployment paths -> account setup -> final closeout.

## Workstream 1: Auth And Rate Limits

Goal: Protect REST and MCP access with scoped keys and measurable usage. REST uses hashed scoped API keys; MCP at `/api/mcp` uses OAuth 2.1 resource-server (per decision 0001 D10).

Status: [~] REST portion **complete** (2026-06-06, jointly with Plan 07 W5) — hashed scoped keys,
rate limits, usage events live on `/api/v1/*`; runbook `docs/operations/auth-and-rate-limits.md`.
MCP OAuth 2.1 is a separate stream (Plan 07 W6) — **not yet** done.

Depends on:

- [x] Plan 03 REST/MCP endpoints.
- [x] Plan 01 `api_keys` and `usage_events` schema.

Enables:

- [ ] Workstream 6 observability (now has `usage_events` to read).
- [ ] Plan 05 security review.

Repo guidance:

- Local bypass must be explicit and unavailable in production mode. (No bypass path exists; local
  dev simply uses the in-process rate-limit store and can issue a key for higher limits.)

Primary areas:

- `packages/api`
- `packages/mcp-server`
- `packages/shared`
- `docs/security`

Implementation tasks:

- [x] Add API key creation, hashing, validation, and scopes. (REST — `@intercal/core/src/auth/`.)
- [~] Add shared REST/MCP auth middleware. (REST middleware done in `packages/api/src/auth/`; the
      MCP server uses OAuth 2.1, wired in Plan 07 W6 — by design the two surfaces do not share one
      middleware.)
- [x] Add rate-limit policy and usage event recording. (Port + Upstash/in-memory adapters; per-key
      and per-IP policy honoring `resource-budget.md`; `usage_events` row per request.)
- [x] Add key rotation and local dev docs. (`docs/operations/auth-and-rate-limits.md` +
      `scripts/ops/keys.mjs` rotation flow.)

Exit criteria:

- [x] REST auth and rate-limit tests cover allowed, denied (401/403), exhausted (429), anonymous,
      and local-dev cases (24 unit tests + a 17/17 live Neon-branch verification). MCP OAuth exit
      criteria remain with Plan 07 W6.

Suggested verification:

- `pnpm test` (api + core auth/rate-limit suites)
- `DATABASE_URL=<neon-branch> node scripts/dev/verify-auth.mjs` (live)

## Workstream 2: Source Policy And Trust

Goal: Enforce storage, citation, redistribution, and reliability policy per source.

Depends on:

- [ ] Plan 02 source registry.

Enables:

- [ ] Workstream 3 audit events.
- [ ] Plan 06 canonical public dataset boundaries.

Repo guidance:

- Public responses must not expose source text beyond source policy.

Primary areas:

- `services/ingest`
- `packages/api`
- `packages/mcp-server`
- `docs/operations/source-policy.md`

Implementation tasks:

- [ ] Add source policy enforcement in ingestion and response assembly.
- [ ] Add source allowlist controls.
- [ ] Add source reliability scoring.
- [ ] Add source health history.
- [ ] Add citation-origin/citation-laundering detection foundation.

Exit criteria:

- [ ] Restricted sources can be cited or summarized only according to policy.

Suggested verification:

- `uv run pytest services/ingest/tests -k source_policy`
- `pnpm test -- source-policy`

## Workstream 3: Audit Events

Goal: Record trust-sensitive actions in queryable audit logs.

Depends on:

- [ ] Plan 01 `audit_events` schema.
- [ ] Workstream 1 auth identities.

Enables:

- [ ] Workstream 4 feedback/review records.
- [ ] Plan 05 security audit.

Repo guidance:

- Audit logs should record actor, action, target, timestamp, and safe metadata.

Primary areas:

- `packages/shared`
- `packages/api`
- `services/resolve`
- `docs/security/audit-events.md`

Implementation tasks:

- [ ] Add audit writer and shared event types.
- [ ] Record entity merges, splits/unmerges, claim corrections, source review actions, provider config changes, subscription changes, admin actions, and manual overrides.
- [ ] Add audit query helpers for operations.

Exit criteria:

- [ ] Trust-sensitive fixtures write expected audit events.

Suggested verification:

- `pnpm test -- audit`
- `uv run pytest services/resolve/tests -k audit`

## Workstream 4: Feedback And Review Records

Goal: Accept bounded feedback without public canonical mutations.

Depends on:

- [ ] Workstream 3 audit events.
- [ ] Plan 03 claim/entity/source response IDs.

Enables:

- [ ] Plan 06 feedback/reporting UX.

Repo guidance:

- Feedback can create review records only; operator-governed systems decide later action.

Primary areas:

- `packages/api`
- `packages/shared`
- `docs/operations/review-workflows.md`

Implementation tasks:

- [ ] Add feedback/report issue endpoint.
- [ ] Add review record schema if not already covered by audit/review tables.
- [ ] Add targets for entity, claim, source, digest, freshness, and coverage concerns.
- [ ] Add status workflow for received, reviewing, resolved, rejected.
- [ ] Add tests proving feedback does not mutate canonical records.

Exit criteria:

- [ ] Public feedback creates audited review records and leaves canonical graph unchanged.

Suggested verification:

- `pnpm test -- feedback`

## Workstream 5: Subscriptions

Goal: Notify interested consumers when relevant knowledge changes.

Depends on:

- [ ] Plan 03 freshness/delta query services.
- [ ] Workstream 1 auth.

Enables:

- [ ] Plan 06 subscription management UI.

Repo guidance:

- Webhook delivery must avoid leaking secrets or unrestricted internal payloads.

Primary areas:

- `packages/api`
- `services/synthesize`
- `docs/operations/subscriptions.md`

Implementation tasks:

- [ ] Add topic, entity, relationship, and claim-pattern subscriptions.
- [ ] Add polling and webhook delivery surfaces.
- [ ] Add minimum importance thresholds and token-budgeted notification payloads.
- [ ] Add retry/backoff and delivery logs.

Exit criteria:

- [ ] Fixture entity/topic changes produce expected subscription notifications.

Suggested verification:

- `pnpm test -- subscriptions`

## Workstream 6: Observability

Goal: Make system health, quality, cost, and freshness visible.

Depends on:

- [ ] Plans 02-03 data and API surfaces.
- [ ] Workstreams 1-5 usage/audit/subscription records.

Enables:

- [ ] Plan 05 scale and cost review.

Repo guidance:

- Start with database views and CLI commands; UI cards are allowed when they read real state.

Primary areas:

- `scripts/ops`
- `packages/dashboard`
- `docs/operations/observability.md`

Implementation tasks:

- [ ] Add ingestion, worker, queue, failed job, extraction, claim, resolution, merge/split, embedding, digest cache, API/MCP latency, provider usage/cost, and freshness metrics.
- [ ] Add per-provider consumption tracking vs. free-tier allowances: Neon compute/storage, Cloudflare R2 operations/egress, Upstash Redis commands/bandwidth, Vertex AI / Gemini daily token cap, GitHub Actions minutes. Surface these against the limits in `docs/operations/resource-budget.md`.
- [ ] Add CLI or database views for key health checks.
- [ ] Add dashboard cards where useful and backed by real data.

Exit criteria:

- [ ] Operator can inspect source health, failed jobs, usage, freshness, and per-provider cost/consumption signals against the resource budget.

Suggested verification:

- `pnpm ops:health`
- `pnpm test -- observability`

## Workstream 7: Deployment Paths And Backups

Goal: Document and prove the live and alternative deployment paths with backup/restore.

Depends on:

- [ ] Workstreams 1-6.

Enables:

- [ ] Plan 05 deployment and release audit.

Repo guidance:

- The primary deployment topology is decided (decisions `0001`/`0002`): app+MCP on Vercel, pipeline on GitHub Actions + Cloud Run Jobs, DB on Neon. Plan 07 owns the deploy/CD/secret-fan-out automation. This workstream documents and proves that path, plus the VPS and self-host alternatives.
- `docker compose` remains in the repo as a self-host/other-users path. Maintainers develop directly against Neon — no local Docker required.

Primary areas:

- `docs/operations/deployment.md`
- `docs/operations/backups.md`
- `scripts/deploy`

Implementation tasks:

- [ ] Document and prove the live deployment path: Vercel (app+MCP+REST) + Neon (DB) + GitHub Actions (batch pipeline) + Cloud Run Jobs (on-demand) + Upstash + R2.
- [ ] Document optional self-host path using `docker compose` (for other users; maintainers use Neon direct).
- [ ] Document single-VPS deployment as a paid-tier alternative.
- [ ] Add DNS, TLS, env, health check, migration, upgrade, backup, and restore instructions.
- [ ] Add backup/restore test command (Neon branch + dump).

Exit criteria:

- [ ] Backup and restore are proven for the live Neon path; VPS path is documented.

Suggested verification:

- `pnpm deploy:check`
- `pnpm backup:test`

## Workstream 8: Account And CLI Setup Runbook

Goal: Document the dedicated account setup session so later agents can operate without repeated access friction.

Depends on:

- [ ] Workstream 7 deployment requirements.

Enables:

- [ ] Managed provider verification in Plans 04-05.

Repo guidance:

- Do not commit secrets; document where they live and how to verify access.

Primary areas:

- `docs/operations/account-setup.md`
- `docs/security/secrets.md`

Implementation tasks:

- [ ] Add prerequisites for domain/DNS, SSH keys, VPS, Neon (DB), Cloudflare R2 (storage), Upstash (queue), Vertex AI / Gemini (LLM), GCloud Cloud Run / Cloud Build, GitHub Actions, Vercel, and CLI auth.
- [ ] Add proof commands for each account/tool.
- [ ] Add secret handoff and rotation policy.

Exit criteria:

- [ ] A single setup session can configure required accounts and leave verifiable docs for future work.

Suggested verification:

- Manual proof command checklist in `docs/operations/account-setup.md`.

## Final Verification And Closeout

- `pnpm format:check`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest`
- `pnpm contracts:check`
- `pnpm ops:health`
- `pnpm deploy:check`
- `pnpm backup:test`
- Update security, operations, deployment, source policy, account setup, and observability docs.
- Add changelog fragment.
- Stop local services or document why they remain running.
- Stage intentional files only, commit, and push.

## Acceptance Criteria

- [ ] Auth and rate limits protect REST/MCP.
- [ ] Source policy is enforced in ingestion and responses.
- [ ] Audit events cover trust-sensitive actions.
- [ ] Feedback creates review records without public graph mutation.
- [ ] Subscriptions deliver test payloads.
- [ ] Observability exposes real health and cost signals.
- [ ] Deployment and backup/restore paths are documented and proven.

## Implementation Order

1. Auth and rate limits.
2. Source policy and trust.
3. Audit events.
4. Feedback and review records.
5. Subscriptions.
6. Observability.
7. Deployment paths and backups.
8. Account and CLI setup runbook.
9. Final verification, docs, changelog, commit, and push.

## Future Expansion

- Add moderation workflows for trusted maintainers after feedback/review records are proven.
- Add hosted public instance operations after source and trust boundaries are fully verified.
