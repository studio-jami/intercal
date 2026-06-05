# Plan 02 W1 — Source Adapters and Ingestion Runs

Date: 2026-06-04
Type: feature
Services: intercal-ingest, intercal-shared
Schema: db/seeds/0003_sources.sql

## Summary

Implements Workstream 1 of Plan 02 (Knowledge Pipeline): real source adapter
infrastructure, Wikidata + GitHub starter adapters, and the live ingest_source
and score_source_health job bodies.

## Changes

### intercal-shared (ports + adapters + config)

- `ports/source.py` — new `SourcePort` base class + `RawDocument` dataclass
  (content bytes, external_id, url, title, published_at, language, content_type,
  metadata). Defines the fetch async-generator contract.
- `source_registry.py` — new `SourceRegistry` (in-process adapter map).
  `register()` / `get()` / `all_names()` / `register_all_defaults()`.
  Module-level `registry` singleton.
- `adapters/source_wikidata.py` — `WikidataChangesAdapter` (`wikidata_changes_v1`):
  MediaWiki recentchanges API with optional Wikipedia REST summary enrichment.
  Respects max_documents, pagination via `rccontinue`, User-Agent policy.
- `adapters/source_github.py` — `GitHubReleasesAdapter` (`github_releases_v1`):
  GitHub REST API releases for a configurable repo list. Pre-release filter, draft
  skip, optional token auth, per-repo budget distribution, Link header pagination.
- `config.py` — added ingestion throttle knobs: `INGEST_CRON`,
  `INGEST_MAX_DOCS_PER_RUN` (default 200), `EXTRACT_ONLY_CHANGED`,
  `LLM_DAILY_REQUEST_BUDGET`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_PRIMARY`,
  `EMBEDDINGS_BATCH_SIZE`.
- `pyproject.toml` — added `source-http = ["httpx>=0.27.0"]` optional dep.

### intercal-ingest (jobs + CLI)

- `jobs.py` — `ingest_source` implemented: source row lookup, registry dispatch,
  SHA-256 content hash, `ON CONFLICT DO NOTHING` upsert, optional raw storage
  (redistribution-gated), ingestion_run lifecycle (running → succeeded/failed),
  consecutive_failures tracking. Returns counters dict.
- `jobs.py` — `score_source_health` implemented: fraction-of-runs base score +
  consecutive-failure streak penalty; persists to `sources.reliability_score`.
- `jobs.py` — `normalize_document` and `cleanup_expired_cache` remain
  `NotImplementedError` stubs (W2 / Plan 03).
- `cli.py` — `ingest-source` command gains `--max-documents` flag; prints
  counters on completion.

### DB seeds

- `db/seeds/0003_sources.sql` — seeds `wikidata-recent-changes` (CC0,
  redistribution=true, 6h cadence) and `github-releases-featured` (10 repos,
  1d cadence, redistribution=false by default).

### Env + docs

- `.env.example` — documented all ingestion throttle knobs.
- `docs/roadmaps/2026-05-21-intercal-plan-02-knowledge-pipeline.md` — W1
  marked complete with full implementation notes.

## Tests

- 49 tests in `services/ingest/tests/test_w1_source_adapters.py` covering:
  registry CRUD, adapter name contracts, RawDocument defaults, Wikidata mock-HTTP
  (yield, rate-limit, server-error, max-docs, cursor-sink, rcend resume), GitHub
  mock-HTTP (yield, prerelease filter, no-repos, rate-limit, 403-header rate-limit,
  borrowed-client header isolation), `_parse_timestamp`, ingest_source (inactive,
  missing, paused, success, dedupe, raw-key write-back), score_source_health.
- Ruff: clean. Pyright: 0 errors. All service tests pass.

## Audit pass (2026-06-04, second fresh context)

Audited W1 against the live repo + API docs; fixed correctness gaps and verified live.

- **`published_at` type bug (caught only live):** asyncpg rejects a bare string for a
  `timestamptz` parameter even with a `::timestamptz` cast in the query. Added
  `_parse_timestamp` (ISO-8601 / trailing-Z → aware datetime; `None` on garbage) and
  bind a `datetime`. Mocked tests had masked this; the live Neon run surfaced it.
- **Cursor never persisted:** `ingest_source` always wrote `cursor_state = NULL`. Added a
  `cursor_sink` dict to the `SourcePort.fetch` contract; the job seeds it from the prior
  run and persists it on success.
- **Wikidata cursor semantics corrected:** switched cross-run resume from `rccontinue`
  (which only paginates within one newest-first query and would re-crawl history) to a
  `{"last_timestamp": ...}` cursor replayed as `rcend`. `rccontinue` still drives intra-run
  paging. Re-verified against MediaWiki API:RecentChanges docs.
- **Provenance gaps:** the job stored raw bytes but never recorded `raw_storage_key`, and
  never set `content_length`. Both now written (raw key via a post-insert UPDATE so only
  new, non-duplicate docs trigger an object-storage write — respects resource-budget).
- **GitHub rate-limit detection hardened:** a primary-limit 403 carries
  `x-ratelimit-remaining: 0` without a body marker; now detected via the documented header
  signals (429, `x-ratelimit-remaining == 0`, `retry-after`) plus the body fallback.
- **Borrowed-client leak:** the GitHub adapter mutated a shared `http_client`'s headers
  with its auth/version; now passed per-request so a shared client can't leak GitHub auth.
- **`.env.example`:** documented optional `GITHUB_TOKEN` for the releases adapter.

### Live verification (Neon branch `br-still-water-ajmss6b6`)

Ran both adapters end-to-end against the live branch: Wikidata 53 docs + GitHub 11 docs,
real DB inserts, R2 raw archival for redistribution-allowed sources with key write-back,
incremental cursor advance, and `score_source_health` = 1.00. GitHub re-run proved
idempotency (12 fetched / 0 new / 12 skipped). Source-policy gate confirmed: GitHub
(`redistribution=false`) stored 0 raw keys, Wikidata (CC0) stored all. Branch reset to
clean seed state afterward.
