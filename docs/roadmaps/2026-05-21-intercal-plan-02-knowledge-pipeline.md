# Knowledge Pipeline Implementation Plan

Date: 2026-05-21
Aligned: 2026-06-04 to live stack
Status: [~] Active — W1 complete (2026-06-04); W2 complete (2026-06-05); W3 complete (2026-06-05); W4 complete (2026-06-05); W5 complete (2026-06-05)
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`, `docs/architecture/pipeline.md`, `docs/architecture/data-model.md`; decisions `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`
Owner: Main orchestration agent
Surface: ingestion, normalization, extraction, providers, embeddings, entity resolution, relationships, fact versions, orchestration

## Purpose

Build the complete source-to-fact pipeline. This plan owns how documents enter Intercal, become validated claims, resolve into canonical entities, generate embeddings, derive relationships, and produce append-only bitemporal fact versions.

## Live Alignment (2026-06-04)

This plan is **Phase B** of the master program (`docs/roadmaps/2026-06-04-intercal-program.md`). It builds on the live substrate: Neon (Postgres 18 + pgvector 0.8.1) is the running DB; the full schema and seed vocabularies are already applied; all pipeline service seams exist with `NotImplementedError` bodies awaiting this plan.

Concrete providers behind their ports (decisions `0001`/`0002`):
- **DB:** Neon. Dev uses a Neon branch. Migrations run via `node scripts/dev/migrate.mjs --seed` against `DATABASE_URL`. No local Docker in the maintainers' flow; `docker compose` is an optional self-host path only.
- **Storage:** Cloudflare R2 (S3 API) behind `StoragePort`; GCS is the zero-friction fallback while R2 token is pending — swap is a config change.
- **Queue/cache:** Upstash Redis (TCP) behind `QueuePort`; `pgmq` Postgres fallback.
- **Embeddings:** local fastembed/ONNX (bge-small, 384-dim, halfvec) behind `EmbeddingsPort` — zero-cost, in-worker default.
- **LLM:** Vertex AI (yrka.io SA / ADC) primary behind `LlmPort`; Gemini API key (postpay) fallback; Groq/Anthropic/OpenAI also behind the port.
- **Workers:** GitHub Actions scheduled workflows (public repo, free) for batch; Cloud Run Jobs (`rich-wavelet-496206-h7`) for on-demand/heavy. Same `python -m intercal_<svc> <job>` CLIs on both.
- **Worker cadence and resource budget:** ingestion runs on a schedule, not continuously. Batch sizes, LLM call volume, and embedding workloads must respect `docs/operations/resource-budget.md` (free-tier allowances; embeddings local/free; LLM via Vertex with daily cap + Gemini fallback; R2/Upstash within free limits).

See also: `docs/decisions/0001-foundation-stack.md`, `docs/decisions/0002-final-hosting-topology.md`, `docs/operations/resource-budget.md`, `docs/roadmaps/2026-06-04-intercal-program.md`.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- Plan 01 must provide migrations, source tables, claim tables, embedding tables, relationship types, fact versions, contracts, and local verification.
- The foundation report requires claims to be first-class and relationships/fact versions to be derived from claims.
- The foundation report requires embeddings as production capability with provider/model metadata.
- Vertex AI (yrka.io SA / ADC) is the primary LLM provider; Gemini API key (postpay) is the fallback. Tests must work without live keys; live Vertex smoke tests are optional verification when ADC is configured.
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
- Windows-native commands remain the local verification path. DB verification runs against `DATABASE_URL` (a Neon branch) — not a local Docker database.

## Target Product Shape

Intercal can ingest configured sources, normalize and deduplicate documents, extract mentions and claims, embed searchable records, resolve entities, derive temporal relationships, and write fact versions with complete provenance.

## Cross-Stream Dependency Map

Source adapters -> document normalization -> mention extraction -> claim extraction -> provider abstraction -> embeddings -> entity resolution -> relationship derivation -> fact versions -> orchestration -> final pipeline proof.

## Workstream 1: Source Adapters And Ingestion Runs

Goal: Make source ingestion idempotent, auditable, and policy-aware.

**Status: [x] Complete — 2026-06-04**

Depends on:

- [x] Plan 01 `sources`, `source_documents`, and `ingestion_runs` schema.

Enables:

- [x] Workstream 2 document normalization.

Repo guidance:

- Source adapters must not own canonical parsing beyond fetch and source metadata.

Primary areas:

- `services/ingest`
- `services/shared` (ports + adapters)
- `db/migrations`, `db/seeds`
- `docs/architecture/pipeline.md`

Implementation tasks:

- [x] Add source registry (`intercal_shared.source_registry.SourceRegistry`) and adapter
  interface (`intercal_shared.ports.source.SourcePort` / `RawDocument`).
- [x] Add Wikidata recent-changes adapter (`wikidata_changes_v1`) — fetches via MediaWiki
  recentchanges API (newest-first, `rcdir=older`); optionally enriches with Wikipedia REST
  summary. CC0, redistribution=true. Incremental polling uses a **timestamp** cursor
  (`{"last_timestamp": ...}` → next run's `rcend`), not `rccontinue` (which only paginates
  within a single query and would re-crawl history if replayed across runs). `rccontinue`
  is still used for intra-run paging. Verified against the live MediaWiki API:RecentChanges docs.
- [x] Add GitHub releases adapter (`github_releases_v1`) — fetches release notes for a
  configurable list of repos; respects pre-release/draft filters. Rate-limit detection
  hardened to the documented signals: 429, or 403/429 with `x-ratelimit-remaining: 0` /
  `retry-after`, or the body marker. A borrowed `http_client`'s headers are no longer mutated
  (auth/version headers are passed per-request) so a shared client can't leak GitHub auth.
- [x] Implement `ingest_source` job body: source row lookup, adapter dispatch, SHA-256
  content hash, `ON CONFLICT DO NOTHING` upsert, raw storage (if redistribution allowed) with
  the resulting object key written back to `source_documents.raw_storage_key`, `content_length`
  recorded, `published_at` parsed to an aware datetime (asyncpg rejects a bare string for
  `timestamptz` even with a `::timestamptz` cast), cross-run cursor persisted via a `cursor_sink`,
  `ingestion_runs` lifecycle (running → succeeded/failed), `consecutive_failures` tracking.
- [x] Implement `score_source_health` job body: compute reliability_score from run history
  + consecutive failure streak; persist to `sources.reliability_score`.
- [x] Add ingestion throttle knobs to `Settings` (`INGEST_MAX_DOCS_PER_RUN`, etc.) and
  document `GITHUB_TOKEN` in `.env.example` (resource-budget.md compliance).
- [x] Add `source-http` optional dep to `intercal-shared` for httpx-based source adapters.
- [x] Seed `db/seeds/0003_sources.sql` with `wikidata-recent-changes` and
  `github-releases-featured` starter source rows.
- [x] 49 unit tests cover registry, adapters (mock HTTP, cursor sink, rate-limit headers,
  borrowed-client isolation), `ingest_source` (fake pool, raw-key write-back), timestamp
  parsing, and `score_source_health`. All pass; no live network required.
- [x] Audit pass (2026-06-04, second fresh context) fixed: cursor never persisted; raw object
  key + `content_length` never written; `published_at` string rejected by asyncpg (caught only
  by the live run, not the mocked tests); GitHub primary-rate-limit 403-without-body-marker;
  borrowed-client header mutation. API usage re-verified against MediaWiki + GitHub docs.
- [x] Verified LIVE against Neon branch `br-still-water-ajmss6b6`: both adapters ingested real
  documents (Wikidata 53, GitHub 11) end-to-end — DB insert, R2 raw archival for
  redistribution-allowed sources, key write-back, incremental cursor advance, and
  `score_source_health` (1.00). GitHub re-run proved dedup: 12 fetched / 0 new / 12 skipped.
  GitHub (redistribution=false) correctly stored 0 raw keys; Wikidata (CC0) stored all.
  Branch reset to clean seed state after verification.

Exit criteria:

- [x] Re-running ingestion does not duplicate source documents (`content_hash` UNIQUE +
  `ON CONFLICT DO NOTHING`) — proven live (GitHub re-run: 0 new / 12 skipped).

Suggested verification:

- `uv run pytest services/ingest/tests`
- `pnpm db:migrate:seeded` (runs against `DATABASE_URL` — a Neon branch)

## Workstream 2: Document Normalization And Chunking

Goal: Persist clean source documents and chunks with deterministic hashes.

**Status: [x] Complete — 2026-06-05**

Depends on:

- [x] Workstream 1 source adapter outputs.

Enables:

- [x] Workstream 3 mention extraction.
- [x] Workstream 5 embeddings (chunks → chunk_embeddings).

Repo guidance:

- Raw archival storage must respect source policy.

Primary areas:

- `services/ingest`
- `services/extract`
- `db/migrations`

Implementation tasks:

- [x] Add `db/migrations/0023_source_documents_normalized.sql` — adds `normalized_at
  timestamptz` and `chunk_count integer` columns to `source_documents`; partial index
  on `normalized_at IS NULL` for efficient queue scans. Idempotent (`ADD COLUMN IF
  NOT EXISTS`).
- [x] Add `services/ingest/src/intercal_ingest/normalizer.py` — pure-Python,
  deterministic, no external service calls:
  - `normalize_text(raw, content_type)` — routes JSON (stdlib flattener), HTML
    (stdlib `html.parser` stripper skipping script/style), plain/markdown (entity
    unescape), or unknown (JSON probe then HTML fallback) through whitespace collapse
    and Unicode NFC normalisation.
  - `detect_language(text)` — Unicode-block frequency heuristic (BCP 47); correct
    for English-dominant W1 seed (Wikidata/GitHub); returns `"en"` as safe default;
    swappable via port when multi-lingual coverage matters.
  - `chunk_text(text, chunk_size, chunk_overlap)` — sentence-boundary-aware sliding
    window; deterministic; merges trailing chunks shorter than `MIN_CHUNK_SIZE`;
    emits `ChunkResult` with offsets and token estimates.
- [x] Implement `normalize_document` job body in `services/ingest/src/intercal_ingest/jobs.py`:
  - Idempotent: skips if `normalized_at IS NOT NULL` (unless `force=True`).
  - Derives body from `cleaned_text` or falls back to raw storage bytes.
  - Content-type routing: checks `metadata.content_type` first, then sniffs JSON,
    falls back to plain text.
  - Writes normalised text + detected language + byte length back to
    `source_documents`.
  - Upserts `document_chunks` rows with `ON CONFLICT (document_id, chunk_index) DO
    UPDATE` for safe re-runs.
  - Marks `normalized_at = now()` and `chunk_count = <n>`.
- [x] Add `normalize-document` CLI command to `services/ingest/src/intercal_ingest/cli.py`
  with `--document-id`, `--force`, `--chunk-size`, `--chunk-overlap` options.
- [x] 43 unit tests in `services/ingest/tests/test_w2_normalize.py` covering
  `normalize_text` (HTML, JSON, plain, markdown, edge cases), `detect_language`
  (English, Chinese, Arabic, Cyrillic, short/empty text), `chunk_text` (empty,
  single, multi-chunk, offsets, determinism, index uniqueness, merge of short
  trailing chunks), and `normalize_document` job (fake pool: missing row, skip,
  force, empty body, plain text, HTML, JSON, language detection, storage fetch,
  storage failure graceful, idempotent re-run, JSON sniff without explicit
  content_type). All 114 service tests pass.
- [x] Add `scripts/dev/verify_w2_normalize.py` integration helper for live Neon runs.
- [x] Verified LIVE against Neon branch `br-still-water-ajmss6b6`: normalized all 5
  W1-ingested Wikidata documents (Arabic and English), language detection (ar/en
  correct), chunks written to `document_chunks`, `normalized_at` + `chunk_count` set.
  Idempotent re-run: all 5 skipped, existing chunk rows preserved. Both passes: PASS.
- [x] Audit pass (2026-06-05, second fresh context) fixed three correctness/cohesion
  defects the first pass missed (all data-dependent, so the small-doc live run did not
  surface them):
  1. **Oversized chunks.** `chunk_text` emitted a single giant chunk for any document
     with no sentence boundaries (boundary-free / minified text) or for a single
     sentence longer than `chunk_size` — would blow past the embedding context window
     (W5/W6). Added `_hard_split_segment`: oversized segments are split on whitespace
     (hard char-cut for an oversized lone token) before windowing, preserving absolute
     offsets. No chunk can now exceed `chunk_size` (+ a small join slack).
  2. **Stale chunks on re-normalise.** A forced re-run (or a smaller `chunk_size`) that
     produced fewer chunks left orphan `document_chunks` rows at higher indices
     (`ON CONFLICT` only overwrites 0..n-1), corrupting `chunk_count` and the W3
     extraction input. Added a `DELETE … WHERE chunk_index >= n` after the upsert and a
     full `_clear_chunks` on the 0-chunk paths. Proven live: 7→1 chunks drops 6 orphans.
  3. **JSON mis-routing.** `normalize_document` sniffed only the first 4 KB, so a valid
     JSON document larger than 4 KB mis-parsed as `text/plain` and leaked raw JSON into
     chunks; a bare scalar body was also mis-classified as JSON. W1 `ingest_source` now
     persists the adapter's `content_type` into `source_documents.metadata` (deterministic
     routing); the sniff fallback (`_sniff_content_type`) parses the whole body and only
     accepts object/array JSON.
- [x] +8 regression tests (122 service tests pass). Re-verified LIVE on
  `br-still-water-ajmss6b6`: force re-normalise all 5 docs, `chunks_in_db ==
  sum(chunk_count)`, idempotent re-run skips all, shrink-renormalise leaves no orphans.
  Branch restored to consistent 5/5 state.

Exit criteria:

- [x] Fixture and real source documents produce stable document/chunk records.

Suggested verification:

- `pnpm py:lint && pnpm py:typecheck && pnpm py:test`
- `DATABASE_URL=<neon-branch> uv run python scripts/dev/verify_w2_normalize.py`

## Workstream 3: Mention And Claim Extraction

Goal: Extract validated mentions and atomic claims from normalized documents.

**Status: [x] Complete — 2026-06-05**

Depends on:

- [x] Workstream 2 normalized chunks (`document_chunks`, `cleaned_text`).
- [x] Plan 01 claim and mention contracts (`mentions`, `claims`, `claim_evidence` schema).

Enables:

- [x] Workstream 5 embeddings (claims → claim_embeddings).
- [ ] Workstream 6 entity resolution.
- [ ] Workstream 7 relationship derivation.

Repo guidance:

- Inputs are `source_documents.cleaned_text` + `document_chunks` (NOT `normalized_text` —
  the old docstring was wrong; corrected here).
- Mentions are evidence candidates, not canonical entities.

Primary areas:

- `services/extract`
- `db/migrations` (0012, 0013)

Implementation tasks:

- [x] Add `MENTIONS_SCHEMA` and `CLAIMS_SCHEMA` JSON Schemas in `services/extract/src/intercal_extract/jobs.py`
  for structured LLM extraction with server-side (Gemini `response_schema`) + client-side
  schema validation (W4 port). Schema uses plain `"string"` for nullable date fields for
  Gemini SDK compatibility; `parse_valid_time()` treats empty strings as `None`.
- [x] Implement `extract_mentions` job body:
  - Loads `cleaned_text` + `document_chunks` (ordered by `chunk_index`).
  - Falls back to a virtual single-chunk when no chunk rows exist (idempotent vs. W2 run order).
  - Applies rule-based NER baseline per chunk (regex vocabulary: QIDs, property IDs, URLs,
    person names, org patterns, country abbreviations) via `rule_based_mentions()`.
  - Optionally augments with LLM-based span extraction via
    `llm.extract_structured(MENTIONS_SCHEMA, prompt)` — one call per chunk.
  - Merges rule + LLM candidates; LLM wins for the same (char_start, char_end) span.
  - Translates chunk-local offsets to document-level offsets (provenance).
  - Clamps confidence to [0.0, 1.0]; drops spans with invalid/inverted offsets.
  - Idempotent: `DELETE FROM mentions WHERE document_id = $1` before bulk-insert.
  - Writes to `mentions` with `chunk_id` FK and document-level char offsets.
- [x] Implement `extract_claims` job body:
  - Loads `document_chunks` (capped by `max_chunks` — default 20 — for budget control).
  - Calls `llm.extract_structured(CLAIMS_SCHEMA, prompt)` per chunk; token usage logged.
  - Validates structured output via W4 port (server + client side); per-chunk LLM failure
    is non-fatal (logged; continues to next chunk).
  - Idempotent: `DELETE FROM claims WHERE $1 = ANY(source_document_ids)` before insert
    (cascade deletes `claim_evidence`).
  - Writes to `claims` with subject/predicate/object, qualifiers, normalized_text,
    valid_from/until (parsed via `parse_valid_time()`), confidence, extractor.
  - Populates `raw_spans` JSONB with `{document_id, chunk_id, char_start, char_end, text}`
    for full provenance traceability.
  - Populates `claim_evidence` with `char_offset_start/end` and `quote_excerpt` (only when
    `redistribution_allowed = true`).
  - Writes `raw_quote` only when `redistribution_allowed = true` (source policy compliance).
- [x] Added `resolve_entities` and `derive_relationships` stubs with explicit
  `NotImplementedError("Plan 02 W6/W7/W8 — …")` for deferred workstreams.
- [x] Updated CLI (`services/extract/src/intercal_extract/cli.py`): `extract-mentions`
  command wires the LLM adapter; `extract-claims` adds `--max-chunks` option (budget guard).
- [x] Added `scripts/dev/verify_w3_extract.py` integration smoke test.
- [x] 49 unit tests in `services/extract/tests/test_w3_extract.py` covering: schema field
  presence, rule-based NER (QID, property ID, URL, person name, GPE), helpers
  (clamp_confidence, safe_int_offset, parse_valid_time), extract_mentions (no-doc, no-text,
  rule-only, LLM augment, LLM-wins-same-span, LLM-failure-fallback, invalid-offset-dropped,
  virtual-chunk-fallback, doc-offset-applied, idempotent-delete), extract_claims (no-doc,
  no-text, single-claim, idempotent-delete, LLM-failure-nonfatal, missing-fields-skipped,
  no-raw-quote-when-restricted, virtual-chunk-fallback, max-chunks, token-accumulation,
  raw-spans-provenance), CLI wiring (help, missing args, max-chunks option).
- [x] All 237 service tests pass; `pnpm py:lint` + `pnpm py:typecheck` clean (0 errors).
- [x] Live verified (2026-06-05) against Neon branch `br-still-water-ajmss6b6`:
  - 2 English Wikidata documents processed.
  - `extract_mentions`: 6 + 5 mentions persisted with document-level char offsets; mix of
    `rule_regex_v1` and `llm_extract_v1` extractors.
  - `extract_claims`: 1 claim + 1 evidence row persisted; `raw_spans` carries `chunk_id` +
    char offsets; `quote_excerpt` present (redistribution=true for Wikidata/CC0 docs).
  - Provider: `gemini-2.5-flash` (Gemini API key fallback; 326 in / 69 out tokens for 1 claim).
  - Idempotent re-run: delete+replace confirmed by counter parity (DB count == persisted counter).

- [x] Audit pass (2026-06-05, second fresh context) closed two correctness defects and
  one extraction-quality defect the first pass missed. All within the W3 lane (the
  embeddings/W4 change is the minimal seam fix that unblocks W3 claim quality):
  1. **Provenance offset corruption (the critical one).** `extract_mentions` /
     `extract_claims` computed document-level char offsets as `chunk.char_offset_start +
     llm_local_offset`. But `document_chunks.chunk_text` is a re-joined, whitespace-collapsed
     variant of its source region (the chunker strips sentence edges and joins sentences with
     a single space), so chunk-text offsets do **not** line up with `cleaned_text` wherever the
     region contained a newline or repeated whitespace. Every persisted span past such a point
     drifted — `cleaned_text[start:end]` no longer reconstructed the mention/quote. False
     provenance is corruption. Fixed with `anchor_span()`: the verbatim span text is located
     within the chunk's known region of `cleaned_text` (exact, then whitespace-flexible, then
     whole-document fallback), so the persisted offsets satisfy the only invariant that matters
     — `cleaned_text[start:end]` reconstructs the span. Unanchorable spans are **dropped**, never
     stored with a fabricated offset. Claim `raw_quote` is now the anchored slice (matches the
     stored offsets exactly). Live-confirmed on real W2 chunks (whitespace-drift present): 0
     span-reconstruction failures across 20 mentions + 9 claims on both providers. The first
     pass's small live run did not surface it because its chunks happened to be single-region.
  2. **Claim under-extraction from output truncation.** On the 2.5 "thinking" models, reasoning
     tokens are drawn from the same `max_output_tokens` budget; a thinking spike truncated the
     structured-extraction JSON mid-object, so the whole chunk parse-failed (after retries) and
     yielded **zero** claims — the real reason pass 1 got only 1 claim from 2 docs. Fixed by
     setting `thinking_config.thinking_budget=0` on `extract_structured` in the Gemini/Vertex
     adapter (verified against google-genai 2.8.0): the full budget goes to the answer, making
     schema-bound extraction deterministic. Live: 1→9 claims on Vertex for the same content.
  3. **Claim prompt sharpened** to decompose compound sentences into atomic claims and extract
     liberally (explicitly factual-only; no fabrication, no inference beyond the text).
- [x] +8 W3 regression tests (245 service tests pass) pin the anchoring invariant
  (`cleaned_text[start:end] == text_span` under whitespace drift), unanchorable-span drop,
  anchored-quote/offset agreement, and NULL-span-on-unanchorable. `pnpm py:lint` +
  `pnpm py:typecheck` clean (0 errors).
- [x] Re-verified LIVE (2026-06-05) on a dedicated Neon verification branch using the **real**
  W2 normalizer to produce real drifted chunks, then the real W3 jobs through the live LLM port:
  - **Vertex (primary)**: 20 mentions + 9 claims persisted, 0 span-reconstruction failures
    (2974 in / 1100 out tokens, 5 chunks).
  - **Gemini-key (fallback)**: 20 mentions + 3 claims, 0 span-reconstruction failures.
  - Idempotent re-run: DB counts == persisted counts (no duplication).
  - Error taxonomy exercised live: Vertex 429 → `LlmRateLimitError` (retried, graceful per-chunk
    degrade); Gemini 503 → transient, non-fatal. Verification branch deleted after the run.

- [x] Audit pass (2026-06-05, third fresh context) closed one residual provenance defect the
  prior passes missed, staying strictly in the W3 lane:
  - **Repeated-span offset collapse.** When the same span text appeared more than once in a
    chunk (e.g. an entity named twice), `anchor_span()` returned the *first* occurrence for
    every copy, so the second-plus mentions were persisted with a fabricated offset pointing at
    the first hit. Fixed by threading an `occupied` accumulator through `anchor_span()` (exact
    and whitespace-flexible matchers now skip already-claimed ranges) and having
    `extract_mentions` claim successive occurrences left-to-right per distinct span text. The
    claims path was already immune (it slices each evidence quote by the LLM's reported offsets
    before anchoring). +2 regression tests pin the anchor-advances-to-next-occurrence behaviour
    and the distinct-offset persistence (247 service tests pass; lint + typecheck clean).
  - Re-verified LIVE on a throwaway Neon branch (forked from the W2-seeded verification branch)
    through the real LLM port (Gemini `gemini-2.5-flash`, live HTTP 200): 10 mentions persisted
    across 2 docs, **10/10 span-reconstruction OK, 0 failures**; idempotent re-run held the
    per-doc count at 5 (delete+replace, no accumulation). Throwaway branch deleted after the run.

Exit criteria:

- [x] Fixture documents produce expected mentions and claims with source evidence.
- [x] Source spans (chunk_id + char offsets) trace every claim back to its evidence text —
  offsets reconstruct the verbatim span from `cleaned_text` (anchored, drift-proof).
- [x] Extraction is idempotent (safe to retry with same inputs).

Suggested verification:

- `pnpm py:lint && pnpm py:typecheck && pnpm py:test`
- `DATABASE_URL=<neon-branch> uv run python scripts/dev/verify_w3_extract.py`

## Workstream 4: Provider Abstraction

Goal: Route model and embedding calls through replaceable providers.

**Status: [x] Complete — 2026-06-05**

Depends on:

- [x] Plan 01 provider-boundary docs and contracts.

Enables:

- [ ] Workstream 3 LLM-assisted extraction.
- [ ] Workstream 6 embeddings.
- [ ] Plan 03 synthesis.

Repo guidance:

- Live Vertex AI calls are optional verification, not required test dependencies. Tests must work with mock/local providers.

Primary areas:

- `services/shared` (ports + adapters + config + factory)
- `docs/architecture/provider-boundaries.md`

Implementation tasks:

- [x] `LlmPort` exists with `complete` + `extract_structured` methods and `LlmResponse` / error types.
- [x] `EmbeddingsPort` exists with `model`, `dim`, `embed` and `EmbeddingsError`.
- [x] `GeminiLlmAdapter` extended to support **Vertex AI mode** (`vertexai=True`, `project`, `location`)
  via `google-genai` v2 SDK — same adapter class, two modes selected by config.
  Primary = Vertex (yrka.io SA, ADC, trial credits); fallback = Gemini API key (postpay daily allowance).
- [x] Gemini API key mode retained as `LLM_PROVIDER=gemini` fallback path.
- [x] `LocalEmbeddingsAdapter` (fastembed/ONNX, `BAAI/bge-small-en-v1.5`, 384-dim) is the zero-cost
  default behind `EmbeddingsPort`. Exposes `.model` + `.dim` for per-vector metadata recording.
- [x] Groq (`GroqLlmAdapter`), Anthropic (`AnthropicLlmAdapter`), OpenAI (`OpenAILlmAdapter`) are
  real port-conformant adapters; all implement `LlmPort`.
- [x] `OpenAIEmbeddingsAdapter` is a real port-conformant adapter; implements `EmbeddingsPort`.
- [x] `Settings` extended: `vertex_project`, `vertex_location`; `llm_provider` literal extended to
  include `"vertex"`. `VERTEX_PROJECT` / `VERTEX_LOCATION` / `GOOGLE_APPLICATION_CREDENTIALS`
  documented in `.env.example`.
- [x] `factory.make_llm` routes `LLM_PROVIDER=vertex` to `GeminiLlmAdapter(vertexai=True, ...)`.
- [x] 35 W4 unit tests in `services/shared/tests/test_w4_providers.py` — Settings, construction
  (both modes), complete/extract_structured via mock, error cases, LlmPort/EmbeddingsPort structural
  compliance. No live network required.
- [x] Live verified (2026-06-05): Vertex AI `complete()` → text='OK' (7 in / 1 out tokens);
  `extract_structured()` → `{'answer': 'yes'}`; fastembed `embed(2 texts)` → 2 × 384-dim vectors.
  Provider: `gemini-2.5-flash` on `rich-wavelet-496206-h7` (`us-east4`), SA ADC.
- [x] `provider-boundaries.md` updated with Vertex/Gemini dual-mode design and embeddings metadata rule.
- [x] Audit pass (2026-06-05, second fresh context) closed the contract-robustness gaps the
  first pass left (the steering's required W4 surface). All in `services/shared`, port seam intact:
  1. **Schema validation + native structured output.** `extract_structured` now returns a
     `StructuredResult` (validated `.data` + token usage) instead of a bare dict. The Gemini/Vertex
     adapter passes the JSON Schema natively via the SDK's `response_schema` (server-side
     enforcement, google-genai 2.8.0 — verified against official docs), and **every** adapter then
     validates the parsed object client-side against the caller's schema (dependency-free subset
     validator: type/required/properties/items/enum/nullable). Pass 1 only embedded the schema in
     prompt text and never validated — wrong-shaped JSON would have leaked into W3 claim persistence.
  2. **Bounded retries.** Malformed / schema-invalid output and transient rate-limit / timeout
     errors retry (2 extra tries, exponential backoff) in a shared `_llm_common` helper used by all
     adapters; persistent failure raises `LlmExtractionError`.
  3. **Error taxonomy.** Added `LlmAuthError`, `LlmRateLimitError`, `LlmTimeoutError`,
     `LlmBudgetExceededError` (all under `LlmError`); each adapter classifies SDK exceptions so
     W3/W5 can tell retryable from fatal.
  4. **Daily-budget enforcement hook.** `RequestBudget` protocol + `InMemoryRequestBudget` (from
     `LLM_DAILY_REQUEST_BUDGET`) consulted before every call at the port boundary; `make_llm`
     wires it (and `make_request_budget`). Was previously config-only dead weight.
  5. **Token/timeout caps wired.** `LLM_MAX_OUTPUT_TOKENS` is the default output cap (callers pass
     `max_tokens=None` to use it); new `LLM_TIMEOUT_SECONDS` applies a per-call timeout. `make_llm`
     injects both.
  6. **Config validation.** `Settings` model-validator rejects `vertex` without a resolvable
     project, non-positive `EMBEDDINGS_DIM` / token caps / timeout. Added `resolved_vertex_project`
     (falls back to `GCLOUD_PROJECT_ID`) and `resolved_adc_credentials` (falls back to
     `GOOGLE_SERVICE_ACCOUNT_KEY`) so a single SA-key `.env` drives Vertex; `make_llm` promotes the
     SA-key path to `GOOGLE_APPLICATION_CREDENTIALS` for ADC (path only, never contents).
- [x] +24 net W4 tests (181 service tests pass); `pnpm py:lint` + `pnpm py:typecheck` clean (0 errors).
- [x] Re-verified LIVE (2026-06-05, 2nd pass): Vertex `complete()`='OK' (7/1 tok) +
  schema-validated `extract_structured()`→`{'answer':'yes'}` (16/6 tok); Gemini-API-key fallback
  `complete()`='OK'; fastembed 2×384-dim — all through the ports, same `gemini-2.5-flash`. Provider
  swap = one env var. (Note: the dev `.env` SA-key path is mangled by dotenv backslash-escape
  parsing — a dev-env data issue, not a code defect; flagged separately. Vertex verified by passing
  the path via the process env.)
- [x] Audit pass (2026-06-05, third fresh context) closed one real vector-space-safety gap the
  prior passes missed (LLM surface was sound; this was on the embeddings side):
  1. **OpenAI custom dimension was advertised but never requested.** `make_embeddings` always passes
     `EMBEDDINGS_DIM` (default 384) to `OpenAIEmbeddingsAdapter`, which reported `.dim=384` but never
     forwarded `dimensions=` to the API — so the API would have returned native-dim (1536) vectors
     while every persisted row recorded `dim=384`, silently corrupting the model/dim metadata W5
     stores and sizes its pgvector column against. The adapter now forwards `dimensions` for v3
     models (verified against the official OpenAI embeddings guide), and rejects a custom dim on
     `ada-002` (no truncation support) or one larger than native at construction.
  2. **No post-call dim verification (both adapters).** Local + OpenAI `embed()` now assert the
     returned vector length equals the advertised `.dim`, raising `EmbeddingsError` instead of
     leaking a wrong-length vector downstream.
- [x] +8 net W4 tests (189 service tests pass); `pnpm py:lint` + `pnpm py:typecheck` clean (0 errors).
  Re-verified LIVE (2026-06-05, 3rd pass): Vertex `complete()`='OK' (7/1 tok) + schema-validated
  `extract_structured()`→`{'answer':'yes'}` (16/6 tok); Gemini-API-key fallback `complete()`='OK';
  fastembed 2×384-dim (dim guard satisfied) — all through the ports, `gemini-2.5-flash`.

Exit criteria:

- [x] Provider can be swapped without changing extraction, embedding, or synthesis callers.
- [x] Vertex AI and Gemini API key modes both callable through the same `LlmPort` interface.
- [x] All 157 service tests pass; `pnpm py:lint` + `pnpm py:typecheck` clean (0 errors).

Suggested verification:

- `pnpm py:lint && pnpm py:typecheck && pnpm py:test`
- `GOOGLE_APPLICATION_CREDENTIALS=<sa-key.json> LLM_PROVIDER=vertex VERTEX_PROJECT=<proj> uv run python scripts/dev/verify_w4_providers.py`

## Workstream 5: Embeddings And Hybrid Retrieval Indexes

Goal: Generate, persist, refresh, and query embeddings for documents, chunks, entities, and claims.

**Status: [x] Complete — 2026-06-05**

Depends on:

- [x] Workstream 2 chunks.
- [x] Workstream 3 claims.
- [x] Workstream 4 provider abstraction.

Enables:

- [ ] Workstream 7 entity resolution scoring.
- [ ] Plan 03 evidence search and digest assembly.

Repo guidance:

- Embeddings improve retrieval; they are never canonical truth.

Primary areas:

- `services/extract`
- `db/migrations`

Implementation tasks:

- [x] Migration `0024_embeddings_version_and_fts.sql`: adds `embedding_version text NOT NULL
  DEFAULT 'unknown'` column to `chunk_embeddings`, `document_embeddings`, and
  `claim_embeddings` (model + dim + version together identify the vector space for
  re-embedding detection); adds `idx_document_chunks_fts` GIN FTS index on
  `document_chunks.chunk_text` for the lexical retrieval leg.  Idempotent (`ADD COLUMN
  IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).  Applied to Neon branch
  `br-still-water-ajmss6b6`.
- [x] `embed_chunks` job (`services/extract/src/intercal_extract/jobs.py`):
  - Reads `document_chunks` for *document_id* ordered by `chunk_index`.
  - Skips chunks already embedded for the same model (idempotent; `--force` re-embeds).
  - Truncates chunk text to 2000 chars at a word boundary (`truncate_for_embedding`) to
    stay within bge-small's context window.
  - Batches embedding calls via `EmbeddingsPort.embed()` (local fastembed default,
    batch_size=64).
  - Upserts to `chunk_embeddings` with `ON CONFLICT (chunk_id, model) DO UPDATE`, writing
    model + dim + `embedding_version = 'v1'`.  Filters empty-text chunks (would produce
    zero-norm vectors, useless for cosine similarity).
  - Per-batch adapter failures are non-fatal (logged; continues to next batch).
- [x] `embed_claims` job: same pattern for `claims.normalized_text` → `claim_embeddings`.
  Reads active claims by `source_document_ids` array containment.
- [x] `hybrid_search` function: shared retrieval primitive (Plan 03 evidence search will
  use this).
  - **Vector leg**: embeds the query text, queries `chunk_embeddings <=> halfvec` (HNSW
    cosine distance), retrieves up to `limit × 5` candidates.
  - **Lexical leg**: `plainto_tsquery('english', query)` against the GIN FTS index on
    `document_chunks.chunk_text`, ranked by `ts_rank`.
  - **RRF fusion**: Reciprocal Rank Fusion (k=60, default) with configurable
    `vector_weight=0.7` and `fts_weight=0.3`.  A chunk appearing in both legs scores
    higher than one in a single leg.  Returns `limit` results with per-chunk metadata
    (rrf_score, vector_rank, fts_rank, vector_distance, fts_ts_rank).
- [x] CLI commands `embed-chunks` and `embed-claims` added to
  `services/extract/src/intercal_extract/cli.py` with `--document-id`, `--batch-size`,
  `--force` options.  Provider selected via `EMBEDDINGS_PROVIDER` / `EMBEDDINGS_MODEL`.
- [x] `EMBED_VERSION = "v1"` and `truncate_for_embedding()` are module-level public
  symbols for testability and callers.
- [x] 28 unit tests in `services/extract/tests/test_w5_embeddings.py`:
  `truncate_for_embedding` (short/exact/over-limit/word-boundary), `embed_chunks`
  (no-chunks, basic embed+persist, skip-already-embedded, force-re-embed,
  empty-text-skipped, adapter-failure-nonfatal, correct-model-written,
  all-skipped), `embed_claims` (no-claims, basic, skip, force, empty-text,
  adapter-failure), `hybrid_search` (empty-query, vector-only, fts-only,
  overlap-boosts-shared, limit-respected, required-fields, positive-rrf-score,
  no-results, custom-weights, ef-search-on-acquired-conn), `EMBED_VERSION` type check.
  All 276 service tests pass; `pnpm py:lint` + `pnpm py:typecheck` clean (0 errors).
- [x] `scripts/dev/verify_w5_embeddings.py` integration smoke test.
- [x] Live verified (2026-06-05) against Neon branch `br-still-water-ajmss6b6`:
  - 5 chunks embedded (all 5 normalised documents, mixed en/ar): 5 `chunk_embeddings`
    rows, model=`BAAI/bge-small-en-v1.5`, dim=384, embedding_version=`v1`.
  - Idempotent re-run: all 5 skipped (no duplicates).
  - 1 claim embedded: 1 `claim_embeddings` row, same model/dim/version.
  - HNSW index (`halfvec_cosine_ops`) confirmed present on `chunk_embeddings`.
  - FTS GIN index confirmed present on `document_chunks.chunk_text`.
  - `hybrid_search` returned 5 ranked results for 3 sample queries; top result
    consistent with document content; RRF scores positive and ordered.
  - Smoke test: PASS.

- [x] Audit pass (2026-06-05, second fresh context) closed one HNSW query-recall gap and
  confirmed the rest of W5 is sound (no other change). Strictly in the W5 lane:
  1. **`hnsw.ef_search` was never set (the real gap).** `hybrid_search` over-fetches
     `limit * 5` candidates for RRF fusion, but pgvector's HNSW `ef_search` defaults to 40
     (verified against the official pgvector 0.8.x "Query Options" docs). With `limit > 8`
     the vector leg silently returned fewer candidates than the over-fetch — capped recall,
     no error. Fixed: the vector leg now acquires a single connection, opens a transaction,
     and issues `SET LOCAL hnsw.ef_search = max(40, over_fetch * 2)` before the cosine query
     (ef_search must be set on the *same* connection as the query; a pooled `pool.fetch` may
     land on a different backend, so a session-level SET would not reliably apply). `SET LOCAL`
     resets at transaction end — no leakage to the next borrower. Pools without `acquire`
     (unit-test fakes) keep the direct-fetch fallback. +1 W5 test (276 service tests pass).
  2. **Verified correct, no change:** opclass↔operator match (`halfvec_cosine_ops` ↔ `<=>`,
     cosine — bge-small wants cosine ✓); `halfvec(384)` dims ✓; HNSW m=16/ef_construction=64
     defaults ✓; UNIQUE(chunk_id|claim_id, model) + `ON CONFLICT DO UPDATE` upsert (changed
     `EMBED_VERSION`/runtime replaces in place; changed model = new row) ✓; model+dim+version
     persisted per row across all 3 embedding tables ✓.
  3. **TS query-layer alignment (finding, no change):** `packages/core` `searchEvidence` is the
     real V1 lexical-only `ILIKE` read; it reads **no** vectors today. Upgrading it to hybrid
     lexical/vector evidence search is an explicit **Plan 03** task (plan-03 W "Add hybrid
     lexical/vector evidence search"), not W5. W5's schema additions (`embedding_version`, chunk
     FTS index) touch no column the TS layer reads, so there is no drift and no operator/index
     mismatch to fix there. Editing it now would be Plan 03 scope creep — deliberately left alone.
- [x] Re-verified LIVE (2026-06-05, 2nd pass) on Neon branch `br-still-water-ajmss6b6`
  (pgvector 0.8.1): smoke test PASS through the new `acquire()`+`SET LOCAL ef_search` path
  against the PgBouncer pooler endpoint (5 chunk + 1 claim embeddings, model+dim+version
  consistent, idempotent re-run skips all, hybrid_search returns 5 ranked results). **EXPLAIN
  proof of index usability:** with `enable_seqscan=off` + `SET LOCAL hnsw.ef_search=100`,
  the planner uses `Index Scan using idx_chunk_embeddings_hnsw` with
  `Order By: (embedding <=> ...)` — the `<=>` operator engages the cosine HNSW index (a
  mismatched op would force a seq scan). At the live 5-row scale the default plan is a seq
  scan purely on cost (correct planner behaviour, not a defect).

Exit criteria:

- [x] Search can retrieve fixture documents/claims through hybrid lexical and vector paths.
- [x] Embeddings are idempotent (safe to retry; re-embedding same model does not duplicate rows).
- [x] Re-embedding with a changed model creates a new row per the (chunk_id, model) UNIQUE constraint.
- [x] Model + dim + version recorded per vector row (vector-space safety).

Suggested verification:

- `pnpm py:lint && pnpm py:typecheck && pnpm py:test`
- `DATABASE_URL=<neon-branch> uv run python scripts/dev/verify_w5_embeddings.py`

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
- `pnpm db:migrate:seeded` (runs against `DATABASE_URL` — a Neon branch)

## Workstream 8: Pipeline Orchestration

Goal: Run the full pipeline locally and through queue-compatible job boundaries.

Depends on:

- [ ] Workstreams 1-7.

Enables:

- [ ] Plan 03 agent query fixture.
- [ ] Plan 04 scheduling and deployment.

Repo guidance:

- Jobs must be idempotent and safe to retry.
- Worker cadence must respect `docs/operations/resource-budget.md`. Ingestion runs on a schedule (GitHub Actions scheduled workflows), not continuously. Heavy or on-demand jobs run as Cloud Run Jobs. Worker CLIs are portable: `python -m intercal_<svc> <job>` runs unchanged on both.

Primary areas:

- `services/ingest`
- `services/extract`
- `services/resolve`
- `services/synthesize`
- `scripts/dev`

Implementation tasks:

- [ ] Add CLI pipeline runner (`python -m intercal_<svc> <job>` entrypoints for each service).
- [ ] Add job registry and local scheduler.
- [ ] Add queue abstraction backed by Upstash Redis (TCP) behind `QueuePort`; `pgmq` as Postgres fallback.
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
- Optional live provider smoke tests for Vertex AI (ADC configured) and Gemini API key fallback when credentials are configured.
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
