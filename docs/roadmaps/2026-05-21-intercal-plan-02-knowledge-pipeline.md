# Knowledge Pipeline Implementation Plan

Date: 2026-05-21
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/architecture/pipeline.md`, `docs/architecture/data-model.md`
Owner: Main orchestration agent
Surface: ingestion, normalization, extraction, providers, embeddings, entity resolution, relationships, fact versions, orchestration

## Purpose

Build the complete source-to-fact pipeline. This plan owns how documents enter Intercal, become validated claims, resolve into canonical entities, generate embeddings, derive relationships, and produce append-only bitemporal fact versions.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- Plan 01 must provide migrations, source tables, claim tables, embedding tables, relationship types, fact versions, contracts, and local verification.
- The foundation report requires claims to be first-class and relationships/fact versions to be derived from claims.
- The foundation report requires embeddings as production capability with provider/model metadata.
- Vertex and Azure credentials may be available for live provider verification, but tests must work without live keys.
- Public answers must preserve source evidence and source policy constraints.

## Locked Decisions

- The pipeline writes to Postgres through documented repositories/services.
- Extraction model outputs are proposals until schema validation succeeds.
- Embeddings support document, chunk, entity, and claim owners.
- Entity resolution is conservative; false merges are worse than missed merges.
- Roles/offices are separate from people and organizations.
- Provider adapters are replaceable and cannot leak provider-specific payloads into canonical records.

## Non-Goals

- [ ] Do not implement REST/MCP tools in this plan.
- [ ] Do not implement public UI.
- [ ] Do not require live model or embedding providers for automated tests.
- [ ] Do not mutate canonical facts from unvalidated extraction output.
- [ ] Do not expose source text when source policy forbids it.

## Repo Guidance

- Pipeline modules belong under `services/ingest`, `services/extract`, `services/resolve`, and `services/synthesize` until a durable architecture doc says otherwise.
- Shared payloads must use contracts from Plan 01.
- Schema changes need migration IDs, data-model doc updates, and DB verification.
- Provider integration must include mock/local providers.
- Windows-native commands remain the local verification path.

## Target Product Shape

Intercal can ingest configured sources, normalize and deduplicate documents, extract mentions and claims, embed searchable records, resolve entities, derive temporal relationships, and write fact versions with complete provenance.

## Cross-Stream Dependency Map

Source adapters -> document normalization -> mention extraction -> claim extraction -> provider abstraction -> embeddings -> entity resolution -> relationship derivation -> fact versions -> orchestration -> final pipeline proof.

## Workstream 1: Source Adapters And Ingestion Runs

Goal: Make source ingestion idempotent, auditable, and policy-aware.

Depends on:

- [ ] Plan 01 `sources`, `source_documents`, and `ingestion_runs` schema.

Enables:

- [ ] Workstream 2 document normalization.

Repo guidance:

- Source adapters must not own canonical parsing beyond fetch and source metadata.

Primary areas:

- `services/ingest`
- `db/migrations`
- `docs/architecture/pipeline.md`

Implementation tasks:

- [ ] Add source registry and adapter interface.
- [ ] Add retry, backoff, rate-limit, and source health recording.
- [ ] Add policy fields for storage, citation, and redistribution.
- [ ] Add structured knowledge, current-event/source-document, technical-currency, and fixture adapters.
- [ ] Add ingestion run tests for success, failure, retry, and dedupe.

Exit criteria:

- [ ] Re-running ingestion does not duplicate source documents.

Suggested verification:

- `uv run pytest services/ingest/tests`
- `pnpm db:migrate:seeded`

## Workstream 2: Document Normalization And Chunking

Goal: Persist clean source documents and chunks with deterministic hashes.

Depends on:

- [ ] Workstream 1 source adapter outputs.

Enables:

- [ ] Workstream 3 mention extraction.
- [ ] Workstream 6 embeddings.

Repo guidance:

- Raw archival storage must respect source policy.

Primary areas:

- `services/ingest`
- `services/extract`
- `db/migrations`

Implementation tasks:

- [ ] Add URL, title, content, language, and metadata normalization.
- [ ] Add hash-based document and chunk dedupe.
- [ ] Add object storage abstraction for raw content where allowed.
- [ ] Add source-policy enforcement tests.

Exit criteria:

- [ ] Fixture and real source documents produce stable document/chunk records.

Suggested verification:

- `uv run pytest services/ingest/tests services/extract/tests`

## Workstream 3: Mention And Claim Extraction

Goal: Extract validated mentions and atomic claims from normalized documents.

Depends on:

- [ ] Workstream 2 normalized chunks.
- [ ] Plan 01 claim and mention contracts.

Enables:

- [ ] Workstream 7 entity resolution.
- [ ] Workstream 8 relationship derivation.

Repo guidance:

- Mentions are evidence candidates, not canonical entities.

Primary areas:

- `services/extract`
- `packages/shared`
- `docs/architecture/data-model.md`

Implementation tasks:

- [ ] Add mention extraction for people, organizations, places, roles/offices, products, concepts, events, legislation, sources, and technical artifacts.
- [ ] Add claim extraction with subject, predicate, object, qualifiers, valid time, source spans, confidence, and extraction method.
- [ ] Add invalid-output quarantine for malformed model results.
- [ ] Add contradiction candidate key extraction.

Exit criteria:

- [ ] Fixture documents produce expected mentions and claims with source evidence.

Suggested verification:

- `uv run pytest services/extract/tests`
- `pnpm contracts:check`

## Workstream 4: Provider Abstraction

Goal: Route model and embedding calls through replaceable providers.

Depends on:

- [ ] Plan 01 provider-boundary docs and contracts.

Enables:

- [ ] Workstream 3 LLM-assisted extraction.
- [ ] Workstream 6 embeddings.
- [ ] Plan 03 synthesis.

Repo guidance:

- Live Vertex and Azure calls are optional verification, not required test dependencies.

Primary areas:

- `services/extract`
- `services/synthesize`
- `packages/shared`
- `docs/architecture/provider-boundaries.md`

Implementation tasks:

- [ ] Add provider interface, capability registry, and usage logging.
- [ ] Add local/mock provider.
- [ ] Add OpenAI-compatible adapter shape where useful.
- [ ] Add Google Vertex adapter hook.
- [ ] Add Azure adapter hook if supported by available credentials.
- [ ] Add rate-limit and provider-error classification.

Exit criteria:

- [ ] Provider can be swapped without changing extraction, embedding, or synthesis callers.

Suggested verification:

- `uv run pytest services/*/tests -k provider`

## Workstream 5: Embeddings And Hybrid Retrieval Indexes

Goal: Generate, persist, refresh, and query embeddings for documents, chunks, entities, and claims.

Depends on:

- [ ] Workstream 2 chunks.
- [ ] Workstream 3 claims.
- [ ] Workstream 4 provider abstraction.

Enables:

- [ ] Workstream 7 entity resolution scoring.
- [ ] Plan 03 evidence search and digest assembly.

Repo guidance:

- Embeddings improve retrieval; they are never canonical truth.

Primary areas:

- `services/extract`
- `services/resolve`
- `db/migrations`
- `docs/architecture/data-model.md`

Implementation tasks:

- [ ] Add embedding provider interface.
- [ ] Add embedding records with owner type, owner ID, provider, model, dimension, and refresh metadata.
- [ ] Add vector indexes.
- [ ] Add backfill and refresh jobs.
- [ ] Add lexical/vector hybrid search foundation.
- [ ] Add deterministic test embeddings.

Exit criteria:

- [ ] Search can retrieve fixture documents/claims through hybrid lexical and vector paths.

Suggested verification:

- `uv run pytest services/extract/tests services/resolve/tests -k embedding`
- `pnpm db:schema:check`

## Workstream 6: Entity Resolution

Goal: Create conservative, auditable, reversible entity resolution.

Depends on:

- [ ] Workstream 3 mentions/claims.
- [ ] Workstream 5 embeddings.

Enables:

- [ ] Workstream 7 relationship derivation.
- [ ] Plan 04 review workflows.

Repo guidance:

- Auto-merge only where evidence is strong; ambiguous cases enter review.

Primary areas:

- `services/resolve`
- `db/migrations`
- `docs/architecture/data-model.md`

Implementation tasks:

- [ ] Add exact external-ID merge.
- [ ] Add exact normalized-name merge within compatible type.
- [ ] Add role/office separation rules.
- [ ] Add candidate scoring with positive and negative evidence.
- [ ] Add reversible merge events and split/unmerge foundation.
- [ ] Add audit event writes.

Exit criteria:

- [ ] Tests prove exact merge, ambiguous review, and role/office separation.

Suggested verification:

- `uv run pytest services/resolve/tests`

## Workstream 7: Relationships And Fact Versions

Goal: Derive temporal relationships and append-only fact versions from validated claims.

Depends on:

- [ ] Workstream 3 claims.
- [ ] Workstream 6 resolved entities.

Enables:

- [ ] Plan 03 deltas, entity lookups, timelines, and verification.

Repo guidance:

- Relationships must be explainable from claim evidence.

Primary areas:

- `services/resolve`
- `services/synthesize`
- `db/migrations`
- `docs/architecture/data-model.md`

Implementation tasks:

- [ ] Map validated claims to seeded relationship types.
- [ ] Add validity windows, recorded time, confidence, and source evidence.
- [ ] Add contradiction handling.
- [ ] Add append-only fact version writer.
- [ ] Add point-in-time read helper.

Exit criteria:

- [ ] Fixture claims produce expected relationships and fact versions.

Suggested verification:

- `uv run pytest services/resolve/tests services/synthesize/tests`
- `pnpm db:migrate:seeded`

## Workstream 8: Pipeline Orchestration

Goal: Run the full pipeline locally and through queue-compatible job boundaries.

Depends on:

- [ ] Workstreams 1-7.

Enables:

- [ ] Plan 03 agent query fixture.
- [ ] Plan 04 scheduling and deployment.

Repo guidance:

- Jobs must be idempotent and safe to retry.

Primary areas:

- `services/ingest`
- `services/extract`
- `services/resolve`
- `services/synthesize`
- `scripts/dev`

Implementation tasks:

- [ ] Add CLI pipeline runner.
- [ ] Add job registry and local scheduler.
- [ ] Add queue abstraction.
- [ ] Add retry, quarantine, and dead-letter records.
- [ ] Add run health summaries.

Exit criteria:

- [ ] Full fixture pipeline runs from source document to fact version twice without duplicate canonical records.

Suggested verification:

- `uv run intercal-pipeline run --fixture`
- `uv run pytest services`

## Final Verification And Closeout

- `pnpm format:check`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest services`
- `pnpm db:migrate:seeded`
- `pnpm contracts:check`
- `uv run intercal-pipeline run --fixture`
- Optional live provider smoke tests for Vertex/Azure when credentials are configured.
- Update architecture docs, operations docs, provider docs, and this plan's implementation notes.
- Add changelog fragment for schema, pipeline, provider, and operations changes.
- Stop local services or document why they remain running.
- Stage intentional files only, commit, and push.

## Acceptance Criteria

- [ ] Real and fixture source documents ingest idempotently.
- [ ] Mentions and claims are validated and evidence-linked.
- [ ] Embeddings exist for planned owner types.
- [ ] Entity resolution is conservative, audited, and reversible.
- [ ] Relationships and fact versions are derived from claims.
- [ ] Full pipeline proof passes.

## Implementation Order

1. Source adapters and ingestion runs.
2. Document normalization and chunking.
3. Mention and claim extraction.
4. Provider abstraction.
5. Embeddings and hybrid retrieval indexes.
6. Entity resolution.
7. Relationships and fact versions.
8. Pipeline orchestration.
9. Final verification, docs, changelog, commit, and push.

## Future Expansion

- Add additional source adapters after source policy and ingestion invariants are proven.
- Add specialized domain extractors only after the generic claim path is stable.
