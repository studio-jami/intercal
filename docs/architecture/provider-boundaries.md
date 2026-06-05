# Provider Boundaries (Adapters)

Every external dependency sits behind a port. Provider logic never crosses the port boundary,
so Intercal is **deploy-target agnostic and provider-swappable without a migration**. Selection
is by environment (see `.env.example`); the Python `intercal_shared.factory` returns the
configured adapter for each port.

| Port | Interface (Python) | Default adapter | Other adapters | Selected by |
| --- | --- | --- | --- | --- |
| Database | `intercal_shared.db` (asyncpg pool); Kysely on the TS read side | Postgres + pgvector | Neon / Supabase / VPS — any Postgres | `DATABASE_URL` |
| Object storage | `StoragePort` | S3 adapter (MinIO local) | Cloudflare R2 / AWS S3 / any S3-compatible | `STORAGE_PROVIDER`, `S3_*` |
| Queue / cache | `QueuePort` | Redis/Valkey | Postgres (pgmq-style) | `QUEUE_PROVIDER`, `REDIS_URL` |
| Embeddings | `EmbeddingsPort` | local fastembed (ONNX, bge-small-en-v1.5, 384-dim, halfvec) | OpenAI (hosted) | `EMBEDDINGS_PROVIDER`, `EMBEDDINGS_MODEL`, `EMBEDDINGS_DIM` |
| LLM (extract/synthesize) | `LlmPort` | Vertex AI (primary, ADC/SA key) via `GeminiLlmAdapter(vertexai=True)` | Gemini API key (fallback), Groq, Anthropic, OpenAI | `LLM_PROVIDER`, `LLM_MODEL`, `VERTEX_PROJECT`, `VERTEX_LOCATION` |
| Scheduler | `SchedulerPort` | local invoke | GitHub Actions / Modal / cron call the same worker CLIs | `SCHEDULER_PROVIDER` |

## LLM provider selection (Vertex / Gemini dual-mode)

`GeminiLlmAdapter` implements `LlmPort` for both modes — same adapter class, selected by config:

- **`LLM_PROVIDER=vertex`** (primary): uses `google-genai` `Client(vertexai=True, project=..., location=...)`.
  Credentials via ADC — set `GOOGLE_APPLICATION_CREDENTIALS` to a SA JSON key, or use `gcloud auth
  application-default login` in dev.  Requires `VERTEX_PROJECT` (e.g. `rich-wavelet-496206-h7`) and
  `VERTEX_LOCATION` (default `us-east4`).  Primary per the program posture (yrka.io trial credits).
- **`LLM_PROVIDER=gemini`** (fallback): uses `Client(api_key=...)`.  Requires `GEMINI_API_KEY`.
  Falls back to postpay daily allowance when Vertex credits are exhausted or ADC unavailable.

Model names are identical across both modes (e.g. `gemini-2.5-flash`) — the SDK routes correctly
based on the `vertexai` flag.  Switching between modes is a single env-var change; no code change.

`LLM_PROVIDER=groq|anthropic|openai` route to their own adapter classes; all implement `LlmPort`.

## LLM port contract guarantees

`LlmPort` (`intercal_shared.ports.llm`) guarantees the following to every caller, regardless
of provider, so extraction (W3) and synthesis (Plan 03) need not reinvent them:

- **Schema-validated structured extraction.** `extract_structured(schema, prompt)` returns a
  `StructuredResult` whose `.data` has been validated against the caller's JSON Schema (subset:
  type / required / properties / items / enum / nullable). The Gemini/Vertex adapter additionally
  requests the SDK's native server-side `response_schema` enforcement. Wrong-shaped output never
  reaches canonical records — it raises `LlmExtractionError`.
- **Bounded retries.** Malformed/invalid output and transient rate-limit/timeout failures retry a
  small fixed number of times with backoff before raising.
- **Typed error taxonomy.** `LlmError` is the base; `LlmAuthError` and `LlmBudgetExceededError` are
  fatal, `LlmRateLimitError` / `LlmTimeoutError` are retryable, `LlmExtractionError` signals
  malformed output. Callers branch on these instead of parsing strings.
- **Usage accounting.** `LlmResponse` and `StructuredResult` both carry `input_tokens` /
  `output_tokens` for cost tracking.
- **Daily request budget at the boundary.** A `RequestBudget` (default `InMemoryRequestBudget` from
  `LLM_DAILY_REQUEST_BUDGET`) is consulted before each call; the per-call output cap
  (`LLM_MAX_OUTPUT_TOKENS`) and timeout (`LLM_TIMEOUT_SECONDS`) are wired by `make_llm`. See
  [`../operations/resource-budget.md`](../operations/resource-budget.md).

For Vertex, `VERTEX_PROJECT` falls back to `GCLOUD_PROJECT_ID`, and `GOOGLE_APPLICATION_CREDENTIALS`
falls back to `GOOGLE_SERVICE_ACCOUNT_KEY` (path only), so a single service-account `.env` drives
Vertex without duplicating values.

## Embeddings adapter

`LocalEmbeddingsAdapter` (fastembed/ONNX) is the zero-cost default.  It exposes `.model` and `.dim`
properties — callers **must** store both alongside every vector row so a model change can be detected
and re-embedding triggered.  See [data-model.md](data-model.md) for the vector-space safety rule.

Both embeddings adapters **guarantee that the vectors `embed()` returns are exactly `.dim` long** — a
mismatch raises `EmbeddingsError` rather than silently persisting a wrong-length vector. For hosted
OpenAI v3 models a custom `EMBEDDINGS_DIM` smaller than the model's native size is forwarded to the API
as the `dimensions` parameter (Matryoshka truncation); a custom dimension on a model that does not
support truncation (`text-embedding-ada-002`) or one larger than the native size is rejected at
construction. This keeps the advertised `.dim`, the actual vector length, and the per-row metadata in
lockstep — the invariant W5 sizes its pgvector columns against.

## Rules

- **No provider payloads in canonical records.** Adapters translate to/from the contract and
  domain types; raw provider responses never reach Postgres tables or the public API.
- **Credentials are a runtime concern.** A real adapter that needs an API key raises a clear
  error when the key is absent — that is a configuration state, not a placeholder.
- **Vector-space safety.** Embeddings rows carry `model` + `dim`. Changing the embedding model
  changes the vector space; it requires a re-embed and (for a different dimension) a new
  column/table. The adapter alone does not protect against this — see
  [`data-model.md`](data-model.md).
- **TS deploy portability.** The REST API uses Hono (Node/Vercel/Cloudflare/Bun) and the MCP
  server uses the standard Streamable HTTP transport, so the front door is a deploy target, not
  an architectural dependency.

See [`../decisions/0001-foundation-stack.md`](../decisions/0001-foundation-stack.md) for the
provider choices and their rationale, and [`deployment-topology.md`](deployment-topology.md)
for how the same ports map onto local / pilot / managed environments.
