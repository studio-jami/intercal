# Production Saturation And Release Audit Implementation Plan

Date: 2026-05-21
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, Plans 01-04 closeout notes, durable architecture and operations docs
Owner: Main orchestration agent
Surface: architecture parity, data quality, provider-switch proof, security review, scale/cost review, documentation parity, full verification, release readiness

## Purpose

Audit, extend, harden, and verify Intercal until the implemented system matches the intended production architecture. This plan owns closing foundation gaps rather than leaving them as notes.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- Plans 01-04 are expected to leave implementation notes and verification evidence.
- The foundation report requires final production shape, provider portability, embeddings, source policy, subscriptions, deployment, auditability, and full verification.
- Plan 06 should not start until this plan proves all systems are green.
- This repo began as docs-only; final release readiness must verify actual code, docs, operations, and deployment state.

## Locked Decisions

- Audit findings must be fixed when they are part of the intended production shape.
- Provider-switch proof is required for models, embeddings, object storage, queue/cache, app host, and database portability.
- Documentation must describe actual behavior, not aspiration.
- Full verification includes local and hosted deployment proof when credentials are available.

## Non-Goals

- [ ] Do not build Plan 06 interactive UX here.
- [ ] Do not defer known parity gaps into future notes when they belong to Plans 01-04.
- [ ] Do not treat mocks as live provider proof when credentials are available.
- [ ] Do not publish public claims that source policy or evidence cannot support.

## Repo Guidance

- Read `AGENTS.md`, durable architecture docs, operations docs, source policy docs, and all active plan closeout notes before auditing.
- Preserve unrelated user changes.
- Run Windows-native commands locally.
- Update changelog fragments for release-meaningful fixes.
- Retire completed dated plans to `docs/_legacy/roadmaps/` after durable docs carry the operating rules.

## Target Product Shape

Intercal has implemented foundations, pipeline, agent/API surface, trust/operations systems, deployment paths, and verification gates matching its durable architecture docs, with no known foundational shortcuts left behind.

## Cross-Stream Dependency Map

Architecture parity audit -> data quality audit -> provider-switch audit -> security review -> scale/cost review -> documentation parity -> full verification -> release readiness.

## Workstream 1: Architecture Parity Audit

Goal: Compare implementation to durable architecture and fix drift.

Depends on:

- [ ] Plans 01-04 closeout notes.

Enables:

- [ ] Workstreams 2-8.

Repo guidance:

- Fix drift when implementation is wrong; update docs when docs are stale.

Primary areas:

- `AGENTS.md`
- `docs/architecture`
- `docs/operations`
- `packages`
- `services`
- `db`

Implementation tasks:

- [ ] Audit package/service boundaries against system map.
- [ ] Audit schema against data model docs.
- [ ] Audit pipeline against pipeline docs.
- [ ] Audit REST/MCP/SDK against contract docs.
- [ ] Audit provider boundaries and deployment topology.
- [ ] Fix parity gaps.

Exit criteria:

- [ ] Architecture docs and implementation agree.

Suggested verification:

- `pnpm verify`
- Manual architecture checklist in closeout notes.

## Workstream 2: Data Quality Audit

Goal: Prove canonical data invariants across ingestion, claims, entities, relationships, embeddings, and facts.

Depends on:

- [ ] Workstream 1 architecture parity.

Enables:

- [ ] Workstream 7 full verification.

Repo guidance:

- Add tests for every bug or invariant gap found.

Primary areas:

- `services`
- `db`
- `packages/shared`

Implementation tasks:

- [ ] Verify source dedupe.
- [ ] Verify claim evidence completeness.
- [ ] Verify role/office separation.
- [ ] Verify entity merge reversibility.
- [ ] Verify relationship validity windows.
- [ ] Verify append-only fact versions.
- [ ] Verify contradiction handling.
- [ ] Verify source policy enforcement.
- [ ] Verify embedding metadata completeness.
- [ ] Verify freshness correctness.

Exit criteria:

- [ ] Data quality tests cover every canonical invariant.

Suggested verification:

- `uv run pytest services`
- `pnpm db:schema:check`

## Workstream 3: Provider-Switch Audit

Goal: Prove replaceability across model, embedding, storage, queue/cache, hosting, and database boundaries.

Depends on:

- [ ] Workstream 1 provider-boundary audit.

Enables:

- [ ] Workstream 5 scale/cost review.

Repo guidance:

- Use live credentials where configured; use mocks only for unavailable providers and mark that evidence clearly.

Primary areas:

- `docs/architecture/provider-boundaries.md`
- `docs/operations/account-setup.md`
- `services`
- `packages`

Implementation tasks:

- [ ] Prove model provider swap.
- [ ] Prove embedding provider swap.
- [ ] Prove object storage swap.
- [ ] Prove queue/cache swap.
- [ ] Prove app host substitution path.
- [ ] Prove database remains portable Postgres.

Exit criteria:

- [ ] Provider-switch evidence is recorded with exact commands/results.

Suggested verification:

- `pnpm provider:check`
- `uv run pytest services -k provider`

## Workstream 4: Security And Abuse Review

Goal: Close security and abuse risks before release readiness.

Depends on:

- [ ] Plans 03-04 API, auth, source submission, feedback, and deployment surfaces.

Enables:

- [ ] Workstream 8 release readiness.

Repo guidance:

- Do not log secrets, source-restricted content, or provider credentials.

Primary areas:

- `packages/api`
- `packages/mcp-server`
- `docs/security`
- `docs/operations`

Implementation tasks:

- [ ] Audit API keys and admin routes.
- [ ] Audit SSRF protections for feedback/source review surfaces.
- [ ] Audit rate limits and webhook safety.
- [ ] Audit secret handling and logs.
- [ ] Audit dependency vulnerabilities.
- [ ] Audit CORS, headers, and public response leakage.
- [ ] Fix issues found.

Exit criteria:

- [ ] Security review issues are closed or explicitly accepted with rationale.

Suggested verification:

- `pnpm security:check`
- `pnpm test -- security`

## Workstream 5: Scale And Cost Review

Goal: Produce realistic operating envelopes and fix obvious bottlenecks.

Depends on:

- [ ] Workstream 3 provider-switch audit.

Enables:

- [ ] Workstream 8 release readiness.

Repo guidance:

- Cost docs should separate local, VPS, and managed paths.

Primary areas:

- `docs/operations/deployment.md`
- `docs/operations/costs.md`
- `scripts/ops`

Implementation tasks:

- [ ] Measure ingestion throughput.
- [ ] Measure query latency.
- [ ] Estimate embedding backfill cost.
- [ ] Estimate synthesis cost.
- [ ] Measure digest cache hit rate.
- [ ] Inspect queue behavior and DB indexes.
- [ ] Estimate storage and backup growth.

Exit criteria:

- [ ] Cost envelopes and bottleneck fixes are documented.

Suggested verification:

- `pnpm ops:load-check`
- `pnpm ops:cost-report`

## Workstream 6: Documentation Parity

Goal: Make docs match the implemented system and retire dated planning guidance.

Depends on:

- [ ] Workstreams 1-5 findings.

Enables:

- [ ] Workstream 7 full verification.

Repo guidance:

- Durable docs carry future operating rules; completed plans are history.

Primary areas:

- `README.md`
- `AGENTS.md`
- `docs`

Implementation tasks:

- [ ] Update README, AGENTS, architecture docs, operations docs, deployment docs, provider setup docs, API/MCP docs, SDK docs, reports, and plan closeouts.
- [ ] Move completed dated plans and source reports to `docs/_legacy` when durable docs carry the rules.
- [ ] Add changelog fragments for release-meaningful changes.

Exit criteria:

- [ ] No active durable doc points to a retired plan for operating guidance.

Suggested verification:

- `pnpm docs:check`

## Workstream 7: Full Verification Ladder

Goal: Run the complete release gate and fix failures.

Depends on:

- [ ] Workstream 6 documentation parity.

Enables:

- [ ] Workstream 8 release readiness.

Repo guidance:

- Do not stop at partial green if full release gate is in scope.

Primary areas:

- Entire repository

Implementation tasks:

- [ ] Run format, lint, type, unit, integration, fixture, migration, schema, contract, MCP snapshot, OpenAPI, package build, deployment smoke, and backup/restore checks.
- [ ] Fix failures.
- [ ] Record exact evidence.

Exit criteria:

- [ ] Full verification ladder is green.

Suggested verification:

- `pnpm verify:release`

## Workstream 8: Release Readiness

Goal: Prepare Intercal for publication or handoff after all gates pass.

Depends on:

- [ ] Workstream 7 full verification.

Enables:

- [ ] Plan 06 interactive knowledge experience.

Repo guidance:

- Release notes should be honest about limitations and source policy boundaries.

Primary areas:

- `README.md`
- `docs/operations`
- `docs/security`
- changelog fragments

Implementation tasks:

- [ ] Add release checklist.
- [ ] Add changelog/release notes.
- [ ] Add known limitations.
- [ ] Add source policy statement.
- [ ] Add security contact/process.
- [ ] Add contribution/feedback guide.
- [ ] Add deployment guide.
- [ ] Add canonical fixture dataset instructions.
- [ ] Add example agent usage.

Exit criteria:

- [ ] Release readiness docs and evidence are complete.

Suggested verification:

- Manual release checklist review.

## Final Verification And Closeout

- `pnpm verify:release`
- `pnpm docs:check`
- `pnpm changelog:check`
- deployment smoke test for available hosted path
- backup/restore proof
- provider-switch proof
- update all closeout notes and durable docs
- retire completed plans where appropriate
- stop local services or document why they remain running
- stage intentional files only, commit, and push

## Acceptance Criteria

- [ ] Architecture parity gaps are fixed.
- [ ] Data quality invariants are tested.
- [ ] Provider-switch boundaries are proven.
- [ ] Security review is complete.
- [ ] Scale/cost envelope is documented.
- [ ] Docs match implementation.
- [ ] Full release verification is green.
- [ ] Plan 06 is unblocked.

## Implementation Order

1. Architecture parity audit.
2. Data quality audit.
3. Provider-switch audit.
4. Security and abuse review.
5. Scale and cost review.
6. Documentation parity.
7. Full verification ladder.
8. Release readiness.
9. Final commit and push.

## Future Expansion

- Expand public dataset scope after source policy and release operation are stable.
- Add additional managed deployment targets as user demand appears.
