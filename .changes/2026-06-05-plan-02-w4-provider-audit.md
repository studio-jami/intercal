# Plan 02 W4 — Provider abstraction audit fixes

Date: 2026-06-05
Type: fix
Services: intercal-shared

## Summary

Second fresh-context audit of Workstream 4 (provider abstraction — `LlmPort` /
`EmbeddingsPort`). The first pass landed the ports, adapters, factory routing,
and dual-mode Vertex/Gemini support, but left the contract-robustness surface
incomplete. This pass closes those gaps without touching the port/adapter seam.

## Changes (all in `services/shared`)

### LLM port contract (`ports/llm.py`)

- `extract_structured` now returns a `StructuredResult` (validated `.data` dict
  plus token usage) instead of a bare dict. Callers get schema-validated data
  and usage accounting in one object.
- Added a dependency-free JSON Schema validator (`validate_against_schema`)
  covering the extraction-schema subset: `type` (incl. list / nullable),
  `required`, `properties`, `items`, `enum`. Wrong-shaped-but-valid JSON now
  raises `LlmExtractionError` instead of leaking into W3 claim persistence.
- Error taxonomy: added `LlmAuthError`, `LlmRateLimitError`, `LlmTimeoutError`,
  `LlmBudgetExceededError` (all subclass `LlmError`) so callers branch on type,
  not message text.
- Added `RequestBudget` protocol + `InMemoryRequestBudget` (daily request cap).

### Adapters

- New `adapters/_llm_common.py` holds the shared port-side policy: budget
  consumption, timeout (`with_timeout`), JSON-object parsing, and
  validate-and-retry (`run_structured_with_retries`, bounded with backoff).
- Gemini/Vertex adapter (`llm_gemini.py`) now passes the JSON Schema natively via
  the SDK's `response_schema` (server-side enforcement; verified against
  google-genai 2.8.0) and validates client-side, retries, classifies SDK errors,
  applies a timeout, and consumes the budget.
- Groq / OpenAI / Anthropic adapters updated to the same contract
  (`StructuredResult`, validation+retries, error classification, timeout,
  budget, `default_max_tokens`).

### Config + factory

- `Settings`: added `llm_timeout_seconds`, `google_application_credentials`,
  `google_service_account_key`, `gcloud_project_id`; `resolved_vertex_project`
  (falls back to `GCLOUD_PROJECT_ID`) and `resolved_adc_credentials` (falls back
  to `GOOGLE_SERVICE_ACCOUNT_KEY`). A model validator rejects `vertex` without a
  resolvable project and non-positive `EMBEDDINGS_DIM` / token caps / timeout.
- `factory.make_llm` wires `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_SECONDS`, and a
  `RequestBudget` (new `make_request_budget`) into every adapter, and promotes a
  service-account key path into `GOOGLE_APPLICATION_CREDENTIALS` for ADC (path
  only — never the key contents).
- `.env.example`: documented `LLM_TIMEOUT_SECONDS`, `GCLOUD_PROJECT_ID`,
  `GOOGLE_SERVICE_ACCOUNT_KEY` fallbacks (names only).

## Tests

+24 net W4 tests (181 service tests pass; lint + typecheck clean): schema
validator (valid/missing/wrong-type/enum/array/nullable/integral-float),
native `response_schema` passthrough, schema-validation failure, retry-then-
succeed, request budget enforcement (incl. adapter-level), error
classification (rate-limit / auth), and config provider-mode validation.

## Live verification

All through the ports (`gemini-2.5-flash`). Vertex AI: `complete()`='OK' (7/1
tok) and schema-validated `extract_structured()`→`{'answer':'yes'}` (16/6 tok)
on `rich-wavelet-496206-h7` / `us-east4` via SA ADC; Gemini-API-key fallback
`complete()`='OK'; local fastembed 2×384-dim. Provider swap is one env var.

## Third audit pass (2026-06-05) — embeddings vector-space safety

The third fresh-context pass found the LLM surface sound and closed one real gap
on the embeddings side:

- `OpenAIEmbeddingsAdapter` advertised a custom `EMBEDDINGS_DIM` via `.dim` but
  never forwarded `dimensions=` to the API, so it would have returned native-dim
  (1536) vectors while every row recorded the configured dim — silent
  vector-space corruption. It now forwards `dimensions` for v3 models (verified
  against the official OpenAI embeddings guide) and rejects a custom dim on
  `ada-002` (no truncation) or one larger than native, at construction.
- Both embeddings adapters (`embeddings_local.py`, `embeddings_openai.py`) now
  verify the returned vector length equals the advertised `.dim`, raising
  `EmbeddingsError` instead of leaking a wrong-length vector to W5.

+8 net W4 tests (189 service tests pass; lint + typecheck clean). Re-verified
live: Vertex `complete()` + schema-validated `extract_structured()`, Gemini-key
fallback `complete()`, fastembed 2×384-dim — all through the ports.
