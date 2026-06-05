# Agent-Facing Product Surface Implementation Plan

Date: 2026-05-21
Aligned: 2026-06-05 to live stack (W1 complete)
Status: [~] Active — W1–W2 complete (REST surface hardened), W3–W8 pending
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`, `docs/architecture/mcp-api.md`, `docs/architecture/provider-boundaries.md`; decisions `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`
Owner: Main orchestration agent
Surface: query services, REST API, MCP server, SDK, token-budgeted digests, evidence search, claim verification, freshness

## Purpose

Expose Intercal's temporal knowledge through stable agent-facing contracts. This plan owns the shared query layer, REST API, MCP tools, SDK, digest assembly, claim verification, freshness/coverage reporting, and fixture-backed agent behavior.

## Live Alignment (2026-06-04)

This plan is **Phase C** of the master program (`docs/roadmaps/2026-06-04-intercal-program.md`). The app is already live at `lntercal.vercel.app` (Next.js + Hono on Vercel reading Neon). The V1 read tools `get_entity`, `get_sources`, `get_freshness`, and `search_evidence` are implemented; `get_delta` and `verify_claim` are real seams with deferred bodies (`NotImplementedError`) — implementing those two query bodies is the core of this plan.

Concrete providers and topology (decisions `0001`/`0002`):
- **MCP:** mounted at `/api/mcp` on Vercel, stateless Streamable HTTP transport (OAuth 2.1 resource-server auth). Stdio remains available for local use. Agents connect to one URL: `lntercal.vercel.app/api/mcp`.
- **REST:** live at `/api/v1/*` on the same Vercel project.
- **DB:** Neon direct — no local Docker in the maintainers' flow. DB checks run against `DATABASE_URL` (a Neon branch).
- **LLM synthesis (digests/verify):** Vertex AI (yrka.io SA / ADC) primary behind `LlmPort`; Gemini API key fallback.
- **Embeddings (evidence search):** local fastembed default behind `EmbeddingsPort`.

See also: `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`, `docs/operations/resource-budget.md`, `docs/roadmaps/2026-06-04-intercal-program.md`.

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

Status: [x] Complete (2026-06-05)

Depends on:

- [x] Plan 02 relationship and fact-version outputs — real data live in Neon.

Enables:

- [ ] Workstreams 2-8.
- [ ] Plan 06 interactive read-only experience.

Repo guidance:

- No duplicated query logic between REST and MCP.

Primary areas:

- `packages/core` (queries.ts, mappers.ts, db/types.ts)
- `packages/shared` (generated contracts — not modified; no TypeSpec change needed)

Implementation tasks:

- [x] Entity lookup service (`getEntity`) — real reads, aliases, point-in-time relationships, facts.
- [x] Topic/entity resolution (`findEntityRow`) — name, UUID, alias paths.
- [x] Lexical evidence search (`searchEvidence`) — ILIKE on title + cleaned_text, source-policy snippet.
- [x] Claim lookup and sources (`getSources`) — claim-level and entity-level source traversal.
- [x] Freshness calculation (`getFreshness`) — entity last_updated_at + global ingestion fallback.
- [x] Merged-id resolution — UUID lookup transparently follows merged_into_id chain to survivor;
      broken/cyclic chains surface as NotFoundError with mergedIntoId detail. Decision rationale
      in `resolveIfMerged` docblock in queries.ts.
- [x] mapRelationship status bug fixed — `valid_until !== null` (not bare truthiness, which was
      wrong for far-future Date objects).
- [x] EntitiesTable types completed — `deprecated_at` and `deprecation_reason` added to match schema.
- [x] Alias lookup hardened — is_deprecated=false guard on the entity join.
- [x] getDelta / verifyClaim left as honest `NotImplementedError("Plan 03 …")` seams.
- [x] Contract-alignment fix (audit pass 2) — `mapEntity` no longer emits an off-contract
      `externalIds[].url`. The TypeSpec `ExternalId` is exactly `{ system, id }`; the DB row's
      `url` is real provenance but not part of the public contract, and a conditional-spread had
      been smuggling it past TS excess-property checking into both REST and MCP responses.
      Removed; regression-guarded by a new `mapEntity` test.

Exit criteria:

- [x] Query services return contract-valid results against live Plan 02 production data.
- [x] `pnpm lint` passes (biome.json schema version info is pre-existing drift, not a code error).
- [x] `pnpm typecheck` passes (all 6 packages).
- [x] `pnpm test` passes (12 tests in @intercal/core: 10 mapClaim/mapRelationship + 2 new
      mapEntity contract-alignment assertions).
- [x] `pnpm build` passes (all packages including Next.js dashboard).
- [x] `pnpm contracts:check` passes — no drift; W1 did not modify the contract.
- [x] Consumer parity confirmed — REST (`packages/api/src/app.ts`) and MCP
      (`packages/mcp-server/src/server.ts`) both dispatch straight into the same `@intercal/core`
      query functions. One set of semantics, zero duplicated query logic.
- [x] `resolveIfMerged` verified on a throwaway Neon fork (deleted after): simple merge → survivor,
      multi-hop chain → final survivor, self-cycle and self-merge → `NotFoundError` with
      `mergedIntoId`, unknown UUID → `NotFoundError`. Every id-accepting read path (`getEntity`,
      `getFreshness`) routes through `findEntityRow` → `resolveIfMerged`.
- [x] Live API verification: `GET /api/v1/entity?name_or_id=rust` returns correct EntityResponse
      with real claims; `GET /api/v1/evidence?query=rust` returns real hits from production Neon;
      `GET /api/v1/freshness?topic_or_entity=rust` and `/api/v1/sources?entity_or_claim_id=...`
      return correct data. Error taxonomy verified: `GET /api/v1/delta` with a bare date →
      400 `invalid_request` (contract `since_date` is `date-time`); with a full RFC3339 timestamp →
      501 `not_implemented`. Validation precedes deferral, as designed.

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

- [x] All 6 V1 routes wired against the shared query layer and confirmed contract-valid:
      `GET /v1/{delta,entity,evidence,claims/verify,sources,freshness}` (live `/api/v1/*`).
      Route paths follow the TypeSpec contract, not REST-isms like `/entities/:id`.
- [x] `GET /v1/delta` and `GET /v1/claims/verify` return `501 not_implemented` via the core
      `NotImplementedError` seams — bodies are the W5/W6 deliverables, honestly deferred.
- [x] Input validation against the generated contract (Ajv over the TypeSpec JSON Schemas):
      dates enforced as `date-time`, integers/limit bounds (`limit ∈ [1,100]`), required params.
- [x] Unknown query parameters rejected with `400 invalid_request` (`additionalProperties:false`
      injected onto a clone of each query schema — the generated artifact is never mutated).
- [x] `entity_or_claim_id` UUID guard at the REST boundary: a non-UUID returns `400` instead of
      leaking the DB-level `500 invalid input syntax for type uuid` (verified against prod).
- [x] Consistent error taxonomy with JSON `ApiError` bodies and a central `onError`:
      400 invalid_request · 404 not_found · 501 not_implemented · 500 internal_error.
- [x] JSON 404 for unmatched routes (replaces Hono's default `text/plain`). Implemented as a
      scoped `app.all('/v1/*', …)` catch-all plus `app.notFound` — the catch-all is required
      because in production the app is mounted under a prefix (`new Hono().route('/api', app)`)
      and Hono lets the parent own `notFound`, so a sub-app `notFound` never fires for unmatched
      `/api/v1/*`. Scoped to `/v1/*` so it never intercepts the sibling `/api/mcp` (W3) surface.
- [x] Health endpoint (`GET /health`) and OpenAPI document (`GET /openapi.json`).
- [x] CORS on the read-only `/v1/*` surface (`origin:*`, GET/OPTIONS) for browser SDK/agent
      clients. Auth + rate limits are Plan 04 — left as clean seams, not implemented here.
- [~] `GET /delta` / `POST /claims/verify` bodies — deferred to W5/W6 (digest synthesis +
      contradiction reasoning). Routes + validation are complete; only the bodies remain.

Exit criteria:

- [x] REST endpoints pass contract validation + the `packages/api` HTTP test suite (37 tests).
      Live valid+invalid checks run against `lntercal.vercel.app/api/v1/*` and a local run on
      the Neon branch.

Suggested verification:

- `pnpm --filter @intercal/api test`
- `pnpm typecheck` · `pnpm build`

## Workstream 3: MCP Server

Goal: Expose the V1 read surface as agent-native MCP tools via the live `/api/mcp` mount.

Status: [~] Server + mount complete (2026-06-05); the two synthesis bodies (`get_delta` W5,
`verify_claim` W6) remain honest deferred seams.

Depends on:

- [x] Workstream 1 query services.

Enables:

- [ ] Workstream 8 agent fixture.

Repo guidance:

- MCP is mounted at `/api/mcp` on Vercel (stateless Streamable HTTP). Auth = OAuth 2.1 resource-server. Stdio remains for local dev.
- `get_entity`, `get_sources`, `get_freshness`, and `search_evidence` are already implemented; `get_delta` and `verify_claim` are the two deferred bodies this plan must implement.
- MCP outputs must remain compact, cited, and token-budget aware.

Primary areas:

- `packages/mcp-server`
- `packages/shared`
- `packages/dashboard` (the `/api/mcp` route)
- `docs/architecture/mcp-api.md`

Implementation tasks:

- [~] `get_delta` body — deferred to W5 (digest synthesis). The tool is registered; calling it
      returns a clear `not_implemented` MCP tool error (structuredContent `code:not_implemented`),
      not a fake result. Body is the W5 deliverable.
- [~] `verify_claim` body — deferred to W6 (contradiction reasoning). Same honest-seam treatment.
- [x] Confirmed `get_entity`, `search_evidence`, `get_sources`, `get_freshness` are wired and
      contract-valid — verified by a live MCP client against production Neon (real entity + facts
      + evidence returned). One query layer; identical semantics to REST.
- [x] MCP server hardened: official SDK (`@modelcontextprotocol/sdk@1.29.0`, protocol ≤
      `2025-11-25`); `IntercalError` taxonomy (`not_found`/`invalid_request`/`not_implemented`)
      mapped into the tool result's `structuredContent.code`; stateless by construction (no
      per-session state); tool input schemas are the generated contract JSON Schemas (single
      source). Server `instructions` added.
- [x] V1 tool surface covered by real-client tests (`server.test.ts` via in-process transport,
      `web.test.ts` via Web `Request`/`Response`) — these are the executable schema check in lieu
      of a separate snapshot file. (The plan's suggested `pnpm mcp:snapshot:check` script does not
      exist; the tests assert the registered tool set + per-tool input-schema shape instead.)

Exit criteria:

- [x] MCP tools return the same semantic results as REST for live queries (verified: `get_entity`
      / `search_evidence` return the same production data the REST surface returns).

Suggested verification:

- `pnpm --filter @intercal/mcp-server test`
- Live MCP client (`scripts/dev/verify-mcp.mjs`) against `/api/mcp` (local `next dev` or the
  deployed domain) — initialize + tools/list + a real tool call.

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
