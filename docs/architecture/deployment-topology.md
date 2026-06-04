# Deployment Topology

Intercal depends on **service contracts, not hosts.** The same code runs across three paths by
swapping adapter configuration (`.env`) — never by changing application code. Zero-cost for
development and pilot; portable to managed production at scale.

## The three paths

| Concern | Local (dev) | Pilot (zero-cost) | Managed (at scale) |
| --- | --- | --- | --- |
| Postgres + pgvector | `docker compose` (pgvector image) | **Neon free** (auto-resume) / Supabase | managed Postgres |
| Object storage (S3 API) | MinIO | **Cloudflare R2 free** (zero egress) | R2 / S3 |
| Queue / cache | Valkey | **Upstash free** / `pgmq` | managed Redis |
| REST API + MCP | `tsx`/node | **Vercel or Cloudflare Pages free** (Hono is portable) | Pro/Enterprise host or VPS |
| Heavy Python workers | local CLI | **GitHub Actions** scheduled (free for public OSS) / Modal | dedicated workers / Cloud Run |
| Embeddings | local fastembed | local fastembed (in the worker) | hosted optional |
| LLM | free tier | free tier (Gemini/Groq) | paid provider as needed |
| Dashboard | `next dev` | Vercel / Cloudflare Pages free | same |

A single low-cost VPS running all of the above (Postgres, Valkey, MinIO, API/MCP, cron workers)
is the documented "one-box" alternative and the first paid step.

## Notes on the zero-cost pilot

- **Deploy target is interchangeable.** The API is Hono (Node/Vercel/Cloudflare/Bun); the MCP
  server uses standard Streamable HTTP. `intercal.vercel.app` or a Cloudflare Pages URL are
  equally valid front doors. Going live needs only a domain + env config.
- **Vercel Hobby is non-commercial-only** (verified June 2026). Intercal is open source and
  non-commercial during the pilot; any monetization/donation surface is a feature flag, hidden
  until a domain and commercial-friendly host are in place. This is a flag flip, never a
  re-architecture. See [`../decisions/0001-foundation-stack.md`](../decisions/0001-foundation-stack.md) (D15).
- **Free-tier limits drift** (Neon CU-hours, Supabase 7-day pause, Upstash command caps). Because
  the canonical store is plain Postgres+pgvector behind a DB adapter, any forced migration is a
  `pg_dump`/`pg_restore`, not a refactor. Re-verify free-tier numbers at account-setup time.

## Migrations & backups

- Schema is SQL-first (`db/migrations`); apply with `pnpm db:migrate:seeded`. Forward-fix policy
  (no down-migrations) — see [`../../db/README.md`](../../db/README.md).
- Backups, restore proof, and the managed-deployment runbook are owned by the operations plan
  (Plan 04).
