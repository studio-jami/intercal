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
| Embeddings | `EmbeddingsPort` | local fastembed (ONNX, bge-small, 384-dim) | OpenAI (hosted) | `EMBEDDINGS_PROVIDER`, `EMBEDDINGS_MODEL` |
| LLM (extract/synthesize) | `LlmPort` | Gemini (free tier) | Groq, Anthropic, OpenAI | `LLM_PROVIDER`, `LLM_MODEL` |
| Scheduler | `SchedulerPort` | local invoke | GitHub Actions / Modal / cron call the same worker CLIs | `SCHEDULER_PROVIDER` |

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
