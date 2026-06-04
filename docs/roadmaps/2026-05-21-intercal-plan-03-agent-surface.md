# Agent-Facing Product Surface Implementation Plan

Date: 2026-05-21
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/architecture/mcp-api.md`, `docs/architecture/provider-boundaries.md`
Owner: Main orchestration agent
Surface: query services, REST API, MCP server, SDK, token-budgeted digests, evidence search, claim verification, freshness

## Purpose

Expose Intercal's temporal knowledge through stable agent-facing contracts. This plan owns the shared query layer, REST API, MCP tools, SDK, digest assembly, claim verification, freshness/coverage reporting, and fixture-backed agent behavior.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- Plan 02 must provide source documents, claims, entities, embeddings, relationships, and fact versions.
- The foundation report defines the V1 tool surface: `get_delta`, `get_entity`, `search_evidence`, `verify_claim`, `get_sources`, and `get_freshness`.
- MCP and REST must share services rather than implementing separate behavior.
- Digests are delivery artifacts, not canonical facts.

## Locked Decisions

- MCP and REST use one shared query service layer.
- Responses include citations, confidence, freshness, and evidence references where applicable.
- Token-budgeted outputs must preserve provenance.
- Public contracts are OpenAPI/JSON Schema-first.
- SDK behavior follows REST contracts and does not introduce separate semantics.

## Non-Goals

- [ ] Do not mutate canonical graph data through public query tools.
- [ ] Do not implement public interactive UI in this plan.
- [ ] Do not bypass source policy to satisfy a query.
- [ ] Do not make model synthesis required for all responses when cached/evidence-only responses suffice.

## Repo Guidance

- REST routes belong under `packages/api`.
- MCP tools belong under `packages/mcp-server`.
- Shared query behavior belongs in an owning service/package documented by `docs/architecture/system-map.md`.
- Contract changes require OpenAPI/MCP snapshot updates.
- Agent fixtures must run without live model credentials.

## Target Product Shape

Agents can ask what changed, inspect entities, search evidence, verify claims, list sources, and assess freshness through MCP or REST with consistent, typed, cited responses.

## Cross-Stream Dependency Map

Query service -> REST API -> MCP server -> SDK -> digest synthesis -> claim verification -> freshness/coverage -> agent fixture -> final closeout.

## Workstream 1: Query Service Layer

Goal: Centralize all read behavior used by REST, MCP, SDK examples, and later UI.

Depends on:

- [ ] Plan 02 relationship and fact-version outputs.

Enables:

- [ ] Workstreams 2-8.
- [ ] Plan 06 interactive read-only experience.

Repo guidance:

- No duplicated query logic between REST and MCP.

Primary areas:

- `packages/shared`
- `packages/api`
- `packages/mcp-server`

Implementation tasks:

- [ ] Add entity lookup service.
- [ ] Add topic resolution service.
- [ ] Add hybrid lexical/vector evidence search.
- [ ] Add claim lookup and relationship traversal.
- [ ] Add point-in-time fact state and delta assembly.
- [ ] Add freshness calculation.

Exit criteria:

- [ ] Query services return contract-valid results against fixture pipeline data.

Suggested verification:

- `pnpm test -- query`
- `pnpm contracts:check`

## Workstream 2: REST API

Goal: Expose the V1 read surface through documented REST endpoints.

Depends on:

- [ ] Workstream 1 query services.

Enables:

- [ ] Workstream 4 SDK.
- [ ] Workstream 8 agent fixture.

Repo guidance:

- Runtime validation must use shared contracts.

Primary areas:

- `packages/api`
- `packages/shared`
- `docs/architecture/mcp-api.md`

Implementation tasks:

- [ ] Add `GET /delta`.
- [ ] Add `GET /entities/:id`.
- [ ] Add `GET /search/evidence`.
- [ ] Add `POST /claims/verify`.
- [ ] Add `GET /sources`.
- [ ] Add `GET /freshness`.
- [ ] Add health/status endpoints.
- [ ] Add pagination, error envelopes, and rate-limit hooks.

Exit criteria:

- [ ] REST endpoints pass contract and fixture tests.

Suggested verification:

- `pnpm test -- api`
- `pnpm openapi:check`

## Workstream 3: MCP Server

Goal: Expose the V1 read surface as agent-native MCP tools.

Depends on:

- [ ] Workstream 1 query services.

Enables:

- [ ] Workstream 8 agent fixture.

Repo guidance:

- MCP outputs must remain compact, cited, and token-budget aware.

Primary areas:

- `packages/mcp-server`
- `packages/shared`
- `docs/architecture/mcp-api.md`

Implementation tasks:

- [ ] Add `get_delta`.
- [ ] Add `get_entity`.
- [ ] Add `search_evidence`.
- [ ] Add `verify_claim`.
- [ ] Add `get_sources`.
- [ ] Add `get_freshness`.
- [ ] Add MCP schema snapshots.

Exit criteria:

- [ ] MCP tools return the same semantic results as REST for fixture queries.

Suggested verification:

- `pnpm test -- mcp-server`
- `pnpm mcp:snapshot:check`

## Workstream 4: TypeScript SDK

Goal: Provide typed client access to the REST API.

Depends on:

- [ ] Workstream 2 REST API.

Enables:

- [ ] External integrations and Plan 06 UI.

Repo guidance:

- SDK should be thin and contract-aligned.

Primary areas:

- `packages/sdk`
- `packages/shared`

Implementation tasks:

- [ ] Add typed methods for all V1 endpoints.
- [ ] Add auth, retries, pagination helpers, and error handling.
- [ ] Add examples that run against local fixture data.

Exit criteria:

- [ ] SDK examples run and match REST contract outputs.

Suggested verification:

- `pnpm test -- sdk`
- `pnpm build --filter @intercal/sdk`

## Workstream 5: Digest And Token Budgets

Goal: Assemble budgeted responses without losing citations or confidence.

Depends on:

- [ ] Workstream 1 query services.
- [ ] Plan 02 provider abstraction.

Enables:

- [ ] Workstream 6 claim verification summaries.
- [ ] Plan 06 briefing UX.

Repo guidance:

- Digests are cached delivery artifacts, not canonical facts.

Primary areas:

- `services/synthesize`
- `packages/api`
- `packages/mcp-server`

Implementation tasks:

- [ ] Add compact, standard, expanded, and full/evidence-rich budget profiles.
- [ ] Add digest cache and invalidation rules.
- [ ] Add provenance-preserving summary assembly.
- [ ] Add deterministic fixture digest outputs.
- [ ] Add provider-backed synthesis when configured.

Exit criteria:

- [ ] Token-budget tests prove responses fit budget and preserve evidence references.

Suggested verification:

- `pnpm test -- digest`
- `uv run pytest services/synthesize/tests`

## Workstream 6: Claim Verification

Goal: Return support, contradiction, uncertainty, and evidence for user claims.

Depends on:

- [ ] Workstream 1 query services.
- [ ] Workstream 5 digest support.

Enables:

- [ ] Plan 06 claim page and feedback/reporting surfaces.

Repo guidance:

- Verdicts must not overclaim when evidence is thin.

Primary areas:

- `packages/api`
- `packages/mcp-server`
- `services/synthesize`

Implementation tasks:

- [ ] Parse claim text into retrieval candidates.
- [ ] Retrieve supporting and contradicting claims/evidence.
- [ ] Assess freshness and confidence.
- [ ] Return verdict, confidence, evidence, contradictions, and caveats.

Exit criteria:

- [ ] Fixture claims produce supported, contradicted, and uncertain outcomes.

Suggested verification:

- `pnpm test -- verify-claim`

## Workstream 7: Freshness And Coverage

Goal: Tell agents what Intercal knows, how fresh it is, and where coverage is weak.

Depends on:

- [ ] Workstream 1 query services.
- [ ] Plan 02 source health and fact versions.

Enables:

- [ ] Plan 04 observability.
- [ ] Plan 06 coverage views.

Repo guidance:

- Known gaps should be explicit in responses.

Primary areas:

- `packages/api`
- `packages/mcp-server`
- `services/synthesize`

Implementation tasks:

- [ ] Add entity/topic last-updated calculations.
- [ ] Add source coverage by area.
- [ ] Add stale entity detection.
- [ ] Add confidence/freshness warnings.
- [ ] Add response fields for known gaps.

Exit criteria:

- [ ] Freshness responses distinguish strong, stale, and thin coverage.

Suggested verification:

- `pnpm test -- freshness`

## Workstream 8: Agent Fixture

Goal: Prove an agent can get a cited update through REST and MCP.

Depends on:

- [ ] Workstreams 1-7.

Enables:

- [ ] Plan 05 release audit.

Repo guidance:

- Fixture must not depend on live provider keys.

Primary areas:

- `packages/api`
- `packages/mcp-server`
- `packages/sdk`
- `services/synthesize`

Implementation tasks:

- [ ] Add fixture query for "what changed about this topic since this date, in 500 tokens, with sources".
- [ ] Assert topic resolution, fact retrieval, evidence retrieval, digest assembly, citations, confidence, freshness, and budget fit.
- [ ] Run fixture through REST and MCP.

Exit criteria:

- [ ] REST and MCP return contract-valid, cited, budgeted answers for the same fixture.

Suggested verification:

- `pnpm test -- agent-fixture`

## Final Verification And Closeout

- `pnpm format:check`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `pnpm openapi:check`
- `pnpm mcp:snapshot:check`
- `pnpm contracts:check`
- `pnpm build --filter @intercal/api`
- `pnpm build --filter @intercal/mcp-server`
- `pnpm build --filter @intercal/sdk`
- `uv run pytest services/synthesize/tests`
- Update API/MCP docs, SDK docs, operations docs, and this plan's implementation notes.
- Add changelog fragment.
- Stop local servers or document why they remain running.
- Stage intentional files only, commit, and push.

## Acceptance Criteria

- [ ] REST and MCP expose all V1 tools/endpoints.
- [ ] SDK examples run.
- [ ] Digests are budgeted and cited.
- [ ] Claim verification handles support, contradiction, and uncertainty.
- [ ] Freshness/coverage is visible in responses.
- [ ] Agent fixture passes through REST and MCP.

## Implementation Order

1. Query service layer.
2. REST API.
3. MCP server.
4. TypeScript SDK.
5. Digest and token budgets.
6. Claim verification.
7. Freshness and coverage.
8. Agent fixture.
9. Final verification, docs, changelog, commit, and push.

## Future Expansion

- Add GraphQL only if REST/MCP cannot serve graph traversal ergonomically.
- Add more MCP tools after V1 tools prove stable.
