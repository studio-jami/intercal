# Interactive Knowledge Experience Implementation Plan

Date: 2026-05-21
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, Plans 01-05 closeout notes, durable API/MCP/query docs
Owner: Main orchestration agent
Surface: read-only public knowledge experience, graph/timeline explorer, briefing/search interface, evidence views, source coverage, subscriptions, feedback/reporting, operator review surfaces

## Purpose

Build the complete read-only human experience for Intercal's temporal knowledge graph after the backend systems are fully green. This plan owns every user-facing surface needed to explore, verify, compare, subscribe, and report feedback on Intercal knowledge without creating a second source of truth or allowing public graph mutation.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- Plan 05 must prove production readiness before this plan starts.
- Intercal's UI should expose primitives directly: entities, claims, sources, evidence, relationships, timelines, contradictions, freshness, deltas, confidence, subscriptions, feedback, and canonical public dataset coverage.
- Public users can read canonical graph data and submit bounded feedback/reporting records.
- Public users cannot directly submit corrections, sources, merges, claims, or graph mutations.
- The user explicitly wants graph/timeline explorer, briefing/search interface, and operator/review console included in the full end-state.

## Locked Decisions

- Public canonical graph experience is read-only.
- Feedback/reporting creates review records; it does not mutate canonical graph data.
- The UI uses the same query/API services as agents.
- There is no UI-only data model.
- Plan for a canonical public dataset; do not rely on disposable sample data as the product story.

## Non-Goals

- [ ] Do not build this before Plan 05 release gates are green.
- [ ] Do not add public write access to canonical entities, claims, sources, relationships, or fact versions.
- [ ] Do not bypass source policy for visual inspection.
- [ ] Do not create separate UI truth, local-only graph state, or untracked corrections.
- [ ] Do not expose provider credentials, private operational data, or restricted source text.

## Repo Guidance

- UI surfaces belong under `packages/dashboard` or the eventual documented frontend package.
- Shared route/query services should reuse `packages/api`, `packages/sdk`, and `packages/shared` contracts.
- Use full frontend verification including browser checks when a real app exists.
- Keep UI claims evidence-linked.
- Feedback/reporting must reuse Plan 04 review/audit records.

## Target Product Shape

Intercal has a complete read-only human interface with:

- entity pages
- topic pages
- claim pages
- source/evidence pages
- graph explorer
- timeline explorer
- briefing/search interface
- delta comparison interface
- contradiction views
- freshness/coverage views
- subscription management
- feedback/reporting forms
- operator/review console
- operations/admin views
- shareable public pages and embeddable read-only surfaces where source policy allows

## Cross-Stream Dependency Map

User workflows -> information architecture -> shared data access -> graph/timeline -> briefing/search/comparison -> feedback/reporting -> subscriptions -> canonical public dataset surfaces -> operator/admin -> frontend verification.

## Workstream 1: User Workflows And Information Architecture

Goal: Define every human workflow and map it to existing primitives and APIs.

Depends on:

- [ ] Plan 05 production readiness.
- [ ] Plan 03 query/API/SDK surfaces.

Enables:

- [ ] Workstreams 2-9.

Repo guidance:

- No UI workflow should require a new canonical data path unless documented and audited.

Primary areas:

- `packages/dashboard`
- `docs/architecture/interactive-experience.md`
- `docs/operations/review-workflows.md`

Implementation tasks:

- [ ] Map workflows for exploring entities, topics, claims, sources, evidence, graph relationships, timelines, deltas, contradictions, subscriptions, feedback, coverage, and operations.
- [ ] Define route map and surface ownership.
- [ ] Define read-only/public vs operator/admin boundaries.
- [ ] Add UX architecture doc.

Exit criteria:

- [ ] Every planned UI route maps to an existing API/query primitive or a documented new read-only service.

Suggested verification:

- `pnpm docs:check`

## Workstream 2: Shared Frontend Data Access

Goal: Build UI data access on existing contracts without duplicate semantics.

Depends on:

- [ ] Workstream 1 route/workflow map.
- [ ] Plan 03 SDK.

Enables:

- [ ] Workstreams 3-9.

Repo guidance:

- Prefer SDK/query clients over ad hoc fetch logic.

Primary areas:

- `packages/dashboard`
- `packages/sdk`
- `packages/shared`

Implementation tasks:

- [ ] Add typed data hooks/clients for entities, topics, claims, evidence, deltas, freshness, subscriptions, and feedback/reporting.
- [ ] Add loading, empty, stale, error, and source-policy states.
- [ ] Add tests for response contract handling.

Exit criteria:

- [ ] UI data layer handles all planned surfaces without UI-only models.

Suggested verification:

- `pnpm test -- dashboard-data`

## Workstream 3: Entity, Topic, Claim, And Evidence Pages

Goal: Expose core knowledge primitives with citations and confidence.

Depends on:

- [ ] Workstream 2 data access.

Enables:

- [ ] Workstream 4 graph/timeline.
- [ ] Workstream 5 briefing/search.

Repo guidance:

- Every displayed fact needs an evidence path or explicit unknown/coverage state.

Primary areas:

- `packages/dashboard`

Implementation tasks:

- [ ] Build entity page with state, aliases, relationships, fact history, evidence, freshness, and confidence.
- [ ] Build topic page with related entities, claims, deltas, coverage, and subscriptions.
- [ ] Build claim page with support, contradiction, source evidence, valid time, confidence, and feedback reporting.
- [ ] Build source/evidence page respecting source policy.

Exit criteria:

- [ ] Core pages render real API data with evidence and source-policy states.

Suggested verification:

- `pnpm test -- dashboard-pages`
- browser verification command established by the frontend stack

## Workstream 4: Graph And Timeline Explorer

Goal: Let users inspect temporal relationships and changes over time.

Depends on:

- [ ] Workstream 3 primitive pages.

Enables:

- [ ] Workstream 5 comparison UX.

Repo guidance:

- Graph and timeline views must remain explainable at realistic density.

Primary areas:

- `packages/dashboard`

Implementation tasks:

- [ ] Build relationship graph traversal.
- [ ] Add point-in-time controls.
- [ ] Add relationship validity windows.
- [ ] Add claim/evidence drilldown.
- [ ] Add contradiction, source-origin, confidence, and freshness overlays.
- [ ] Add exportable read-only subgraph snapshots where policy allows.

Exit criteria:

- [ ] Users can move through graph and timeline state without losing evidence context.

Suggested verification:

- `pnpm test -- dashboard-graph`
- browser screenshot/interaction checks

## Workstream 5: Briefing, Search, And Comparison

Goal: Provide human-facing search, briefing, and date-to-date delta exploration.

Depends on:

- [ ] Workstream 2 data access.
- [ ] Workstream 4 graph/timeline context.

Enables:

- [ ] Workstream 8 public dataset surfaces.

Repo guidance:

- Reuse digest/query infrastructure; do not create separate summarization behavior.

Primary areas:

- `packages/dashboard`

Implementation tasks:

- [ ] Build search interface over evidence, entities, claims, and topics.
- [ ] Build compact, standard, and deep briefing modes.
- [ ] Build date-to-date comparison.
- [ ] Add source, confidence, freshness, and coverage filters.
- [ ] Add "show evidence" and "what is uncertain" expansions.

Exit criteria:

- [ ] Search and briefings match API/MCP semantics and preserve provenance.

Suggested verification:

- `pnpm test -- dashboard-briefing`

## Workstream 6: Feedback And Reporting

Goal: Let users flag concerns without mutating canonical data.

Depends on:

- [ ] Plan 04 feedback/review records.
- [ ] Workstream 3 primitive pages.

Enables:

- [ ] Workstream 9 operator/review console.

Repo guidance:

- Feedback writes review records only.

Primary areas:

- `packages/dashboard`
- `packages/api`

Implementation tasks:

- [ ] Add feedback form.
- [ ] Add flag issue actions for entity, claim, source, digest, freshness, and coverage concerns.
- [ ] Add source review and correction review request flows.
- [ ] Add feedback status display where appropriate.
- [ ] Add audit trail visibility for operator surfaces.

Exit criteria:

- [ ] Feedback/reporting is audited and cannot mutate canonical graph records.

Suggested verification:

- `pnpm test -- dashboard-feedback`

## Workstream 7: Subscriptions

Goal: Let users manage read-only subscriptions to knowledge changes.

Depends on:

- [ ] Plan 04 subscriptions.
- [ ] Workstream 3 entity/topic pages.

Enables:

- [ ] Public and operator notification workflows.

Repo guidance:

- Subscription payloads must respect source policy and token/detail preferences.

Primary areas:

- `packages/dashboard`

Implementation tasks:

- [ ] Add subscribe/unsubscribe controls for topics and entities.
- [ ] Add subscription list and delivery status.
- [ ] Add detail-level and importance threshold controls.
- [ ] Add tests for subscription state and permission boundaries.

Exit criteria:

- [ ] Users can manage subscriptions without direct graph mutation.

Suggested verification:

- `pnpm test -- dashboard-subscriptions`

## Workstream 8: Canonical Public Dataset And Embeddable Surfaces

Goal: Publish clear read-only access paths for the canonical public dataset.

Depends on:

- [ ] Workstreams 3-7.
- [ ] Plan 04 source policy.

Enables:

- [ ] External use of public pages, widgets, and docs examples.

Repo guidance:

- Public dataset boundaries must be explicit and policy-compliant.

Primary areas:

- `packages/dashboard`
- `docs/operations/public-dataset.md`

Implementation tasks:

- [ ] Define canonical public dataset boundaries and coverage.
- [ ] Add shareable entity/topic/claim pages.
- [ ] Add embeddable delta widgets where policy allows.
- [ ] Add static export for selected graph slices where policy allows.
- [ ] Add docs examples powered by live Intercal data.

Exit criteria:

- [ ] Public dataset surfaces are documented, source-policy compliant, and read-only.

Suggested verification:

- `pnpm test -- public-surfaces`
- `pnpm docs:check`

## Workstream 9: Operator, Review, And Admin Console

Goal: Provide internal surfaces for review, operations, source health, and system trust.

Depends on:

- [ ] Workstream 6 feedback/reporting.
- [ ] Plan 04 observability.

Enables:

- [ ] Ongoing operation after public release.

Repo guidance:

- Admin surfaces must enforce auth and avoid exposing secrets.

Primary areas:

- `packages/dashboard`
- `packages/api`
- `docs/operations`

Implementation tasks:

- [ ] Add review queue for feedback records.
- [ ] Add source health and ingestion run views.
- [ ] Add resolution candidate views.
- [ ] Add audit event viewer.
- [ ] Add provider usage/cost cards.
- [ ] Add freshness and coverage operations views.

Exit criteria:

- [ ] Operators can review user feedback and system health without direct database access.

Suggested verification:

- `pnpm test -- dashboard-admin`
- `pnpm test -- auth`

## Workstream 10: Final Frontend Verification

Goal: Prove the full interactive experience works across devices and preserves API/MCP parity.

Depends on:

- [ ] Workstreams 1-9.

Enables:

- [ ] Release of the interactive experience.

Repo guidance:

- Use browser verification for significant frontend surfaces.

Primary areas:

- `packages/dashboard`
- `docs/operations`

Implementation tasks:

- [ ] Run unit, integration, browser, responsive layout, accessibility, and visual sanity checks.
- [ ] Verify no UI-only data model exists.
- [ ] Verify evidence paths for displayed facts.
- [ ] Verify feedback/reporting audit records.
- [ ] Verify source policy boundaries in public pages.
- [ ] Verify API/MCP behavior remains unchanged unless intentionally versioned.

Exit criteria:

- [ ] Full frontend verification is green and recorded.

Suggested verification:

- `pnpm test -- dashboard`
- `pnpm build --filter @intercal/dashboard`
- browser verification command established by the frontend stack

## Final Verification And Closeout

- `pnpm format:check`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `pnpm build --filter @intercal/dashboard`
- browser verification for desktop and mobile viewports
- `pnpm contracts:check`
- `pnpm docs:check`
- `pnpm changelog:check`
- update UX architecture, public dataset, operations, and feedback/review docs
- add changelog fragment
- stop local servers or document why they remain running
- stage intentional files only, commit, and push

## Acceptance Criteria

- [ ] Complete read-only public knowledge experience exists.
- [ ] Graph, timeline, briefing/search, evidence, source coverage, subscriptions, feedback/reporting, and operator/review surfaces exist.
- [ ] Every displayed fact has an evidence path or explicit coverage/unknown state.
- [ ] Feedback/reporting is audited and cannot mutate canonical data.
- [ ] Canonical public dataset boundaries are documented.
- [ ] Frontend verification passes across desktop and mobile.

## Implementation Order

1. User workflows and information architecture.
2. Shared frontend data access.
3. Entity, topic, claim, and evidence pages.
4. Graph and timeline explorer.
5. Briefing, search, and comparison.
6. Feedback and reporting.
7. Subscriptions.
8. Canonical public dataset and embeddable surfaces.
9. Operator, review, and admin console.
10. Final frontend verification.
11. Final docs, changelog, commit, and push.

## Future Expansion

- Add authenticated private saved views after public read-only surfaces are stable.
- Add collaborative review workflows for trusted maintainers after operator review has proven safe.
