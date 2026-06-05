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

- 23 new tests in `services/ingest/tests/test_w1_source_adapters.py` covering:
  registry CRUD, adapter name contracts, RawDocument defaults, Wikidata mock-HTTP
  (yield, rate-limit, server-error, max-docs), GitHub mock-HTTP (yield, prerelease
  filter, no-repos, rate-limit), ingest_source (inactive, missing, paused, success,
  dedupe), score_source_health (no-runs, all-succeeded, penalty).
- All 63 service tests pass. Ruff: clean. Pyright: 0 errors.
- `pnpm db:migrate:seeded` verified against Neon branch `br-still-water-ajmss6b6`.
