# Operations Transparency

Intercal is designed to run on swappable provider-backed ports while exposing honest operational state.

## Hosted topology

The accepted hosted topology is:

- Vercel for dashboard, REST, OpenAPI, and MCP on one domain.
- Neon Postgres with pgvector for canonical storage.
- GitHub Actions for routine scheduled pipeline runs.
- Cloud Run Jobs for heavy or on-demand pipeline execution.
- Cloudflare R2 behind the S3 storage adapter.
- Upstash Redis behind queue/cache and rate-limit ports.

Provider swaps should be configuration and adapter changes, not schema rewrites.

## Budgets

Resource budget controls live in `docs/operations/resource-budget.md` and env-driven knobs. Backfill and scheduled ingestion should use bounded source counts, document counts, LLM request budgets, and local embeddings where possible.

## Observability

Operator health reads come from SQL-owned views and append-only usage tables. Missing provider telemetry is reported as unavailable, not as zero. Do not insert guessed provider usage.

## Secret lanes

App runtime secrets live only in `.env`, Vercel env, GitHub Actions secrets, Cloud Run Secret Manager, and provider secret stores. Operator credentials such as Vercel, Cloudflare, Neon, and GCloud control-plane tokens are not product runtime auth.

## Smoke checks

```powershell
Invoke-WebRequest "https://intercal.jami.studio/api/openapi.json" -UseBasicParsing
Invoke-WebRequest "https://intercal.jami.studio/api/v1/freshness?topic_or_entity=MCP%20protocol" -UseBasicParsing
node scripts/dev/verify-mcp.mjs "https://intercal.jami.studio/api/mcp"
```

Run corpus quality gates separately when validating coverage claims.
