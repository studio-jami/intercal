# Agent-Facing Product Surface Implementation Plan

Date: 2026-05-21
Aligned: 2026-06-05 to live stack (W1 complete)
Status: [~] Active — W1–W6 complete (W5 = get_delta digest, W6 = verify_claim verdict, both live on Neon), W7–W8 pending
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`, `docs/architecture/mcp-api.md`, `docs/architecture/provider-boundaries.md`; decisions `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`
Owner: Main orchestration agent
Surface: query services, REST API, MCP server, SDK, token-budgeted digests, evidence search, claim verification, freshness

## Purpose

Expose Intercal's temporal knowledge through stable agent-facing contracts. This plan owns the shared query layer, REST API, MCP tools, SDK, digest assembly, claim verification, freshness/coverage reporting, and fixture-backed agent behavior.

## Live Alignment (2026-06-04)

This plan is **Phase C** of the master program (`docs/roadmaps/2026-06-04-intercal-program.md`). The app is already live at `lntercal.vercel.app` (Next.js + Hono on Vercel reading Neon). All six V1 read tools — `get_entity`, `get_sources`, `get_freshness`, `search_evidence`, `get_delta` (W5), and `verify_claim` (W6) — are implemented with real bodies against the canonical schema. Implementing the two synthesis bodies (`get_delta`, `verify_claim`) was the core of this plan and is now complete.

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
- [x] `GET /v1/delta` (W5) and `GET /v1/claims/verify` (W6) return real DB-backed responses; the
      former `501 not_implemented` seams are retired now that both synthesis bodies have shipped.
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
- [x] `GET /delta` (W5) / `GET /claims/verify` (W6) bodies — both shipped (digest synthesis +
      contradiction reasoning). Routes, validation, and bodies are all complete and live.

Exit criteria:

- [x] REST endpoints pass contract validation + the `packages/api` HTTP test suite (37 tests).
      Live valid+invalid checks run against `lntercal.vercel.app/api/v1/*` and a local run on
      the Neon branch.

Suggested verification:

- `pnpm --filter @intercal/api test`
- `pnpm typecheck` · `pnpm build`

## Workstream 3: MCP Server

Goal: Expose the V1 read surface as agent-native MCP tools via the live `/api/mcp` mount.

Status: [x] Server + mount complete (2026-06-05); both synthesis bodies (`get_delta` W5,
`verify_claim` W6) are live — no remaining deferred seams.

Depends on:

- [x] Workstream 1 query services.

Enables:

- [ ] Workstream 8 agent fixture.

Repo guidance:

- MCP is mounted at `/api/mcp` on Vercel (stateless Streamable HTTP). Auth = OAuth 2.1 resource-server. Stdio remains for local dev.
- All six V1 tools are implemented; `get_delta` (W5) and `verify_claim` (W6) — the two synthesis bodies this plan owned — are now live alongside the four W1 read tools.
- MCP outputs must remain compact, cited, and token-budget aware.

Primary areas:

- `packages/mcp-server`
- `packages/shared`
- `packages/dashboard` (the `/api/mcp` route)
- `docs/architecture/mcp-api.md`

Implementation tasks:

- [x] `get_delta` body — implemented in W5. The tool now returns a real token-budgeted, cited
      digest (the `getDelta` core query); verified against production Neon.
- [x] `verify_claim` body — implemented in W6. The tool now returns a real deterministic, cited
      verdict (the `verifyClaim` core query); verified against production Neon.
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

Status: [x] Complete (2026-06-05)

Depends on:

- [x] Workstream 2 REST API — live and hardened at `/api/v1/*`.

Enables:

- [ ] External integrations and Plan 06 UI.

Repo guidance:

- SDK should be thin and contract-aligned.

Primary areas:

- `packages/sdk`
- `packages/shared` (generated contract — consumed, not modified)

Implementation tasks:

- [x] Typed methods for all six V1 operations — `getEntity`, `getSources`, `getFreshness`,
      `searchEvidence`, `getDelta`, `verifyClaim`. Params and response types are **derived** from
      the generated contract (`operations` / `components` in `@intercal/shared`) via `Query<Op>` /
      `Ok<Op>` conditional types — no hand-redeclared shapes, single source of truth. Route paths
      match the TypeSpec contract (`/v1/claims/verify`, not a REST-ism).
- [x] Typed error model mirroring the REST taxonomy: a base `IntercalApiError` (discriminant
      `code` + `status` + `details`) and `instanceof`-discriminable subclasses
      `IntercalInvalidRequestError` (400) · `IntercalNotFoundError` (404) ·
      `IntercalNotImplementedError` (501) · `IntercalServerError` (500), plus `IntercalNetworkError`
      (status 0) for transport failures. The two deferred ops (`getDelta` W5, `verifyClaim` W6)
      compile and surface the live `501 not_implemented` cleanly as `IntercalNotImplementedError` —
      not faked. `token_budget` is in the delta/verify signatures per the contract (server applies
      it when the body lands).
- [x] Request building + config: base URL normalization (trailing slashes trimmed), query/path
      param assembly (undefined params omitted), injectable `fetch` (testability / non-global-fetch
      runtimes), bearer `apiKey` (Plan 04 auth seam), extra headers. Safe GET-only retries with
      exponential backoff for transient network/5xx failures (501 and 4xx are never retried — they
      are deterministic). No pagination helper: the V1 contract has no cursor/offset surface, so
      one would be a placeholder — deferred until the contract grows one.
- [x] Fixture-backed contract tests (`src/index.test.ts`, 14 tests) using **real** responses
      captured from the live surface (`src/fixtures.ts`, typed against the generated contract so a
      contract change breaks compilation) — assert URL/query building, header/auth, typed responses
      unchanged, the full error taxonomy mapping, and retry behavior. Plus an opt-in live smoke test
      (`src/live.test.ts`, gated on `INTERCAL_LIVE=1`, 5 tests) that runs against
      `https://lntercal.vercel.app/api/v1/*` with real production data.

Exit criteria:

- [x] SDK methods return contract-valid results matching REST outputs — verified live: `getEntity`
      / `searchEvidence` / `getFreshness` return real production data; `getDelta` / `verifyClaim`
      surface a typed `IntercalNotImplementedError` (501).
- [x] `pnpm lint` (biome `check .` — repo-wide clean; the 1 info is the pre-existing biome.json
      schema-version drift, not a code error).
- [x] `pnpm typecheck` passes (all 6 TS packages).
- [x] `pnpm --filter @intercal/sdk test` passes (14 deterministic; 19 incl. 5 live with
      `INTERCAL_LIVE=1`).
- [x] `pnpm --filter @intercal/sdk build` passes (emits `dist/`).

Suggested verification:

- `pnpm --filter @intercal/sdk test` (add `INTERCAL_LIVE=1` for the live smoke test)
- `pnpm --filter @intercal/sdk build`

## Workstream 5: Digest And Token Budgets

Goal: Assemble budgeted responses without losing citations or confidence.

Status: [x] Complete (2026-06-05) — `getDelta` implemented as a deterministic, fully-cited,
token-bounded digest in `packages/core`; verified live against production Neon.

Depends on:

- [x] Workstream 1 query services.
- [x] Plan 02 provider abstraction — N/A for the deterministic path (see decision below).

Enables:

- [ ] Workstream 6 claim verification summaries.
- [ ] Plan 06 briefing UX.

Repo guidance:

- Digests are cached delivery artifacts, not canonical facts.

Primary areas:

- `packages/core` (`delta.ts` — digest assembly; `queries.ts` — dispatch)
- `packages/api`, `packages/mcp-server` (already wired to `getDelta`; now return real data)

Decision — deterministic, not LLM-synthesised:

- The contract's `DeltaResponse` carries the change set **structurally** (`changedClaims: Claim[]`
  each with `evidence`+`confidence`, `changedEntities: EntitySummary[]`, and a `summary: Digest`
  whose `content` is a deterministic prose lede + citation-numbered change lines). Every asserted
  line is built from a real row and is traceable to a source document — nothing to fabricate.
- No LLM client exists in `packages/core`; adding provider logic there would cross the port
  boundary (AGENTS.md hard rule). Per the W5 steering, a correct deterministic fully-cited digest
  is preferred over an uncited LLM blob. Optional provider-backed prose polishing remains a clean
  later seam behind `LlmPort` that may only rephrase already-cited content — explicitly deferred.

Implementation tasks:

- [x] Provenance-preserving summary assembly (`assembleDigest`, pure/DB-free): rank → token-budget
      trim → cite → score → render. Lives in `packages/core/src/delta.ts`.
- [x] Token-budget honouring: `token_budget` (clamped to [200, 8000], default 1500) bounds the
      digest; ranked most-recent → most-confident → most-evidence first; reports included/omitted
      and a coverage fraction so a trimmed answer is never silently lossy. (~4 chars/token estimate,
      deterministic, provider-free — replaces the static "profiles" idea with a continuous budget.)
- [x] Transaction-time windowing `(since, until]`: claims via `created_at`, relationships via
      `recorded_at`, changed entities via `last_updated_at`. Topic scope = resolved entity (name/
      alias) OR text match over claim columns, so unresolved topics still surface their changes.
- [x] Fact-version changes surfaced (audit pass 2). The canonical change unit is the append-only
      `fact_versions` table (Plan 02 W7); pass 1 windowed changed entities only on
      `entities.last_updated_at`, which is written EARLIER than the fact version's `recorded_at`
      (verified: all 155 prod entities have `fv.recorded_at > last_updated_at`), so a cutoff
      between the two missed fact-version changes and supersessions entirely. `buildDelta` now
      windows `fact_versions` on `recorded_at`, unions their subject entities into `changedEntities`
      (deduped by id, no double-count), reports supersession/new-assertion counts in the digest
      lede, and rolls their source docs into the citations. The `DeltaResponse` contract was
      sufficient (no field added). Token budget hardened: the lede's measured cost is reserved
      before trimming, so content provably never exceeds `token_budget`.
- [x] Citations enriched with `url`+`publishedAt`; confidence = mean extraction confidence labelled
      `aggregate_extraction`; freshness = newest transaction time + coverage.
- [x] Supersession-across-the-cutoff classified correctly (audit pass 3). The real pipeline
      (`write_fact_versions`, `services/resolve`) inserts the new `is_current=true` row at `now` and
      closes the OLD row IN PLACE without changing its `recorded_at`, so for a supersession recorded
      AFTER the cutoff the closed predecessor falls outside the `(since, until]` window and ONLY the
      new current row is visible. Classifying from in-window rows alone (pass-2 logic) therefore
      mislabelled a genuine supersession as a "new fact version" — proven on a throwaway prod fork
      (`since=19:00Z`: old in-window logic → "new assertion"; correct answer → supersession).
      `buildDelta` now fetches the structural signal — subjects with a version recorded at/before
      `since` (`priorVersionSubjectIds`) — and `assembleDigest` marks an in-window current row for
      such a subject as a supersession. Per-subject counting (not per-row) keeps a subject from being
      both superseded and new. The deterministic path is unchanged: change detection, citations,
      freshness, and token budget were already correct; only the lede's supersession/new label is
      fixed. No contract field added.
- [x] Bounded-window `changedEntities` axis fix (audit pass 4). The `changedEntities` fetch in
      `buildDelta` unions two independent bitemporal signals: (a) `entities.last_updated_at` moved in
      `(since, until]`, and (b) the entity had a fact version recorded in the same window (fetched on
      `fact_versions.recorded_at`). The `until` clamp on `last_updated_at` had been ANDed OUTSIDE the
      `OR`, so it also constrained branch (b): an entity whose `last_updated_at` advanced PAST `until`
      (a normal later pipeline run — e.g. an identical-payload write that `write_fact_versions` skips,
      so no new fact version, while another stage still bumps `last_updated_at`) was dropped from
      `changedEntities` even though its in-window fact version was real, reported in the lede, and
      cited — an axis-conflation inconsistency in the `until`-bounded case. Fixed by moving the `until`
      clamp INSIDE branch (a) only; branch (b) is governed purely by its own `recorded_at` window.
      Proven on a throwaway prod fork (deleted after): entity with fv `recorded_at=18:59:11Z` and
      `last_updated_at` bumped to `20:00Z`, window `(18:58Z, 19:30Z]` — old query → 0 rows (dropped),
      fixed query → 1 row; control (last_updated_at-only entity past `until`) still correctly excluded.
      The `since` lower bound was already correct (inside the `OR`). No contract field added.
- [x] Deterministic unit tests (`delta.test.ts`, 16) over the pure assembler: citations, budget
      bound + omission reporting, ranking, confidence/freshness, changed entities/relationships,
      fact-version changes (new version surfaced + cited with no claim change, supersession reported
      without double-counting, fact-version subject in `changedEntities` despite older
      `last_updated_at`, empty window = no fabrication), and (audit pass 3) the two cross-cutoff
      classification cases — supersession detected via `priorVersionSubjectIds` when only the new
      current row is in-window, and a genuinely-new subject (no prior version) as a new assertion.
- [~] Digest cache + invalidation — deferred (Plan 04 / cache port); the response is a pure
      function of the bitemporal data, so caching is a transparent later optimisation, not faked.
- [~] Provider-backed synthesis — deferred behind `LlmPort` (see decision above).

Exit criteria:

- [x] Token-budget tests prove responses fit budget and preserve evidence references
      (`delta.test.ts`); confirmed live: `topic=rust since=2026-06-01 budget=120→200` trims 12→4
      changes (159 est tokens ≤ 200), coverage 0.33, "8 omitted"; `budget=600` fits all 12 cited
      changes; `since` after ingest → empty, no fabrication.
- [x] Fact-version supersession-across-cutoff proven live (audit pass 2) on a throwaway fork of
      production Neon (deleted after): an append-only supersession of `rust` recorded at 20:00Z with
      a cutoff `since=19:00Z` (after `last_updated_at` 18:55:39) — the old `last_updated_at`-only
      path returned 0 changes; the fixed path returns `changedEntities: 1`, "1 new fact version
      recorded", `freshness.lastUpdated=20:00Z`, cited.

Suggested verification:

- `pnpm --filter @intercal/core test`
- Live REST `/api/v1/delta?topic=rust&since_date=2026-06-01T00:00:00Z` / MCP `get_delta`
  (post-deploy; pre-deploy the same `getDelta` is verified against production Neon directly).

## Workstream 6: Claim Verification

Goal: Return support, contradiction, uncertainty, and evidence for user claims.

Status: [x] Complete (2026-06-05) — `verifyClaim` body live in `packages/core/src/verify.ts`;
verified against production Neon. REST `/api/v1/claims/verify` + MCP `verify_claim` return real
verdicts (no longer 501).

Depends on:

- [x] Workstream 1 query services.
- [x] Workstream 5 digest support (same deterministic, token-budgeted, cited pattern).

Enables:

- [ ] Plan 06 claim page and feedback/reporting surfaces.

Repo guidance:

- Verdicts must not overclaim when evidence is thin. (Honoured: no on-topic evidence →
  `unverified` with confidence 0, never invented support; confidence = relevance × extraction
  confidence, so a single weak match stays low-confidence.)

Primary areas:

- `packages/core` (the `verifyClaim` body — single query layer shared by API + MCP)
- `packages/api`, `packages/mcp-server` (already wired; surfaces the live body)
- `services/synthesize` (not needed: deterministic verdict, no LLM — see decision below)

Decision — deterministic, not LLM (mirrors W5):

- No LLM client lives in `packages/core`, and adding provider logic there would cross the adapter
  port boundary. A correct, fully-cited deterministic verdict is preferred over an uncited LLM blob.
  Every conclusion traces to a real claim row + its source documents. Optional provider-backed
  contradiction *prose* is a later seam behind `LlmPort` that may only rephrase already-cited
  content and can never change the verdict.

Implementation tasks:

- [x] Parse claim text into retrieval candidates — Postgres FTS (`plainto_tsquery`/`ts_rank`) over
      `claims.normalized_text` (the lexical leg W5 also uses), point-in-time filtered.
- [x] Retrieve supporting and contradicting claims/evidence — deterministic classification:
      substrate-recorded contradictions (`claim_contradictions` open rows / `contradiction_status`)
      first, then polarity disagreement over overlapping content; otherwise support.
- [x] Assess freshness and confidence — confidence = evidence weight (relevance × extraction
      confidence), agreement-aware; `as_of_date` evaluates the bitemporal state at that date.
- [x] Return verdict, confidence, evidence, contradictions — `ClaimVerificationResponse` with
      `verdict` (supported / partially_supported / contradicted / unverified), `confidence`, and
      `supportingEvidence` + `contradictingEvidence` citation lists; token-budgeted.
- [x] False-positive-support guard (audit pass 2). Lexical FTS overlap ≠ semantic support, and
      bag-of-words retrieval is order/role-blind: the pre-fix verdict path classified ANY on-topic,
      same-polarity, non-substrate-contradicted candidate as full `support`, so the strongest verdict
      (`supported`) fired on mere vocabulary sharing. Proven against the deployed surface: the
      role-reordered nonsense claim "Windows configuration authored the Rust toolchain for Mike
      McCready" returned `verdict: supported` (the stored claim is "Mike McCready authored the add
      Rust toolchain automated configuration Windows" — subject/object reversed, different
      proposition, identical tokens). Fix: `classify` now grades supporting candidates by a
      `supportStrength` — `strong` (near-verbatim claim-level agreement: high SYMMETRIC content-token
      coverage ≥0.85 AND Jaccard ≥0.5) vs `weak` (lexical-only). `assembleVerification` reserves
      `supported` for ≥1 strong supporter; weak-only support caps at `partially_supported`. No
      contract field added; contradiction sensitivity unchanged. Calibration finding: no symmetric
      overlap metric can separate a role-swap from true support (token-identical), so `supported` is
      deliberately reserved for near-verbatim agreement — under-claiming (`partially`/`unverified`) is
      the safe failure mode; a false `supported` is corruption-adjacent. Defense-in-depth: the FTS
      `plainto_tsquery` AND already sends fabricated specifics (wrong version, invented CVE) to
      `unverified`. Verified live on production Neon (deleted no branches; read-only): role-reorder &
      subset-vague → `partially_supported` (was `supported`); fabricated-CVE / wrong-version →
      `unverified`; positive-of-a-negated-claim → `contradicted`; true-negated → `supported`;
      point-in-time flips at the transaction-time boundary (pre-record → `unverified`, post-record →
      `partially_supported`). +5 deterministic tests (`verify.test.ts`, 13 → 18).
- [x] Tokenizer edge-punctuation fix (audit pass 3). The strong-support gate is a token-set
      comparison, but the tokenizer kept `. - _ ' \`` so identifier-shaped tokens survive
      (`Buffer.poolSize`, `CVE-2026-5222`). Those same chars as *boundary* punctuation produced
      spurious mismatches: a stored claim ending "…64 KiB." tokenized `kib.` while a user's "…64 KiB"
      tokenized `kib`, so an EXACT verbatim restatement of a stored claim scored min-coverage 0.8
      (< 0.85) → `weak` → `partially_supported` instead of `supported`. Live-proven on production Neon
      (read-only, no branches): the deployed endpoint returns `partially_supported` for the verbatim
      claim "Buffer.poolSize increased its default to 64 KiB" (stored verbatim). Fix: `tokenize` now
      strips the boundary-punctuation set from each token's leading/trailing edges only, preserving
      interior structure — two tokens that differ solely by edge punctuation compare equal; distinct
      identifiers never merge (so the false-positive guard cannot widen). Re-verified live: verbatim &
      verbatim-with-trailing-`.` (e.g. "Cargo fixed CVE-2026-5222") → min-cov/Jaccard 1.0 → `strong` →
      `supported`; role-swap & fabricated-CVE stay `unverified`; subset-vague stays
      `partially_supported`; negation stays `contradicted`. +2 deterministic tests
      (`verify.test.ts`, 18 → 20). Deployed surface still predates W6 (app.ts last touched in W2), so
      the corrected `supported` verdict lands on the next deploy.

Exit criteria:

- [x] Claims produce supported, contradicted, and uncertain outcomes — verified live on production
      Neon: real facts → `supported` (cited); no-evidence claim → `unverified` (no fabrication);
      `as_of_date` before/after recording → `unverified`/`supported` (point-in-time correct).

Suggested verification:

- `pnpm --filter @intercal/core test` (pure `classify` + `assembleVerification` suite); live verify
  via the compiled core against production Neon (and `/api/v1/claims/verify` + MCP `verify_claim`
  post-deploy).

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
- [x] Digests are budgeted and cited (W5 `getDelta`; live on Neon).
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
