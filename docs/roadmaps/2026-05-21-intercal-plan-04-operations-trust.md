# Operations, Trust, And Review Loops Implementation Plan

Date: 2026-05-21
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/architecture/deployment-topology.md`, `docs/architecture/provider-boundaries.md`
Owner: Main orchestration agent
Surface: auth, rate limits, source policy, audit events, subscriptions, feedback/review records, observability, deployment, account setup

## Purpose

Build the operational and trust systems required to run Intercal as a reliable open knowledge service. This plan owns access control, source policy, auditability, subscriptions, bounded feedback/review loops, observability, deployment paths, backups, and one-time account/CLI setup runbooks.

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
- Deployment must support local, low-cost VPS, and managed production paths.
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
- Operations scripts must be Windows-native friendly where local execution is expected.
- API/MCP behavior changes require contract and snapshot updates.
- Changelog fragments are required for security, deployment, operations, package, CI, or schema changes.

## Target Product Shape

Intercal can be operated locally, on a VPS, or through managed services with auth, source policy enforcement, audit events, subscriptions, feedback review records, observability, backups, restore proof, and documented account setup.

## Cross-Stream Dependency Map

Auth/rate limits -> source policy -> audit events -> feedback/review records -> subscriptions -> observability -> deployment paths -> account setup -> final closeout.

## Workstream 1: Auth And Rate Limits

Goal: Protect REST and MCP access with scoped keys and measurable usage.

Depends on:

- [ ] Plan 03 REST/MCP endpoints.
- [ ] Plan 01 `api_keys` and `usage_events` schema.

Enables:

- [ ] Workstream 6 observability.
- [ ] Plan 05 security review.

Repo guidance:

- Local bypass must be explicit and unavailable in production mode.

Primary areas:

- `packages/api`
- `packages/mcp-server`
- `packages/shared`
- `docs/security`

Implementation tasks:

- [ ] Add API key creation, hashing, validation, and scopes.
- [ ] Add shared REST/MCP auth middleware.
- [ ] Add rate-limit policy and usage event recording.
- [ ] Add key rotation and local dev bypass docs.

Exit criteria:

- [ ] Auth and rate-limit tests cover allowed, denied, exhausted, and local-dev cases.

Suggested verification:

- `pnpm test -- auth`
- `pnpm test -- rate-limit`

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
- [ ] Add CLI or database views for key health checks.
- [ ] Add dashboard cards where useful and backed by real data.

Exit criteria:

- [ ] Operator can inspect source health, failed jobs, usage, freshness, and provider cost signals.

Suggested verification:

- `pnpm ops:health`
- `pnpm test -- observability`

## Workstream 7: Deployment Paths And Backups

Goal: Prove local, VPS, and managed deployment paths with backup/restore.

Depends on:

- [ ] Workstreams 1-6.

Enables:

- [ ] Plan 05 deployment and release audit.

Repo guidance:

- Provider-specific instructions need replacement paths.

Primary areas:

- `docs/operations/deployment.md`
- `docs/operations/backups.md`
- `scripts/deploy`

Implementation tasks:

- [ ] Document and prove local Docker Compose deployment.
- [ ] Document and prove single-VPS deployment.
- [ ] Document managed production deployment path.
- [ ] Add DNS, TLS, env, health check, migration, upgrade, backup, and restore instructions.
- [ ] Add backup/restore test command.

Exit criteria:

- [ ] Backup and restore are proven for at least local and one hosted path when credentials are available.

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

- [ ] Add prerequisites for domain/DNS, SSH keys, VPS, database, object storage, model providers, Google Vertex, Azure if usable, and CLI auth.
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
