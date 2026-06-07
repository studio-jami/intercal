# Deployment Topology

Intercal depends on **service contracts, not hosts.** Adapter-backed dependencies use the same
ports across environments; front-door compute still has host adapters and trusted-header behavior
that must be proven before a provider swap. This is the decided **current launch shape** - free now,
scales when required - see
[`../decisions/0002-final-hosting-topology.md`](../decisions/0002-final-hosting-topology.md).

## Current launch shape

| Layer | Provider | Notes |
| --- | --- | --- |
| Postgres + pgvector | **Neon** | dev = a Neon **branch**, prod = the main branch. Direct cloud — **no Docker in the dev flow.** |
| Dashboard + REST API + MCP | **Vercel** (one project, one domain) | Next.js UI at `/`; Hono API mounted at `/api/v1/*` + `/api/openapi.json`; MCP at `/api/mcp` (or the Cloud Run service). GitHub-wired with preview deploys. |
| Object storage (S3 API) | **Cloudflare R2** | zero egress; `STORAGE_PROVIDER=s3`. |
| Queue / cache | **Upstash** Redis | serverless; `QUEUE_PROVIDER=redis`. |
| Heavy Python pipeline | **GitHub Actions** (scheduled batch) → **GCloud Cloud Run** (on-demand / scale) | free on the public repo; Cloud Run for scale. Cloud-built Docker (`docker/workers.Dockerfile`). |
| Embeddings | local **fastembed** in the worker (default) | hosted optional behind the port. |
| LLM | free tier (Gemini/Groq) default | paid providers behind the same port. |
| CI/CD | GitHub → Vercel auto-deploy + Actions verify gate | `pnpm verify` in CI against a Postgres service container. |

A single low-cost VPS (or `docker compose`) running everything is the documented self-host
alternative for **other people** — it is not the maintainers' dev flow.

## Developer flow (no Docker)

1. `pnpm install && uv sync --all-packages`
2. Point `DATABASE_URL` at a **Neon branch** (create one per feature; throwaway and free).
3. `pnpm contracts:build` → `node scripts/dev/migrate.mjs --seed` (applies migrations to the
   branch — direct live DB work).
4. `pnpm dev` (dashboard + mounted API) and/or `pnpm --filter @intercal/mcp-server start`.

`docker compose -f docker/compose.yaml up -d` remains available for fully-offline/self-host work but is optional.

## Go-live

- The REST/MCP semantics are portable by contract: Hono owns the REST app factory and MCP uses
  standard Streamable HTTP. The current public deployment is still a Vercel/Next.js front door until
  another host proves its mount adapter, runtime, and trusted-header behavior. The official Intercal
  public domain is `intercal.jami.studio`, attached to the Vercel project with legacy Vercel/domain
  redirects preserved for compatibility. New Vercel hosted environments still follow the same path:
  connect the GitHub repo to Vercel, set env vars (Neon `DATABASE_URL`, R2, Upstash, LLM keys), set
  the Vercel Root Directory to `packages/dashboard`, and attach the target domain.
- The Vercel-specific code found in the release audit is limited to the current Next.js mount
  (`hono/vercel`), the dashboard's `VERCEL_URL` same-deployment fallback, route-level Node runtime
  settings for `pg`, Vercel function duration for MCP, and REST rate-limit trust in Vercel-managed
  client-IP headers. This is acceptable for the launch host. A Cloudflare Workers/Pages move needs a
  separate proof/decision before production traffic uses it.
- The operator deployment runbook is [`../operations/deployment.md`](../operations/deployment.md).
  It ties the Vercel app/MCP/REST path, GitHub Actions pipeline, Cloud Run Job, DNS/TLS,
  migrations, health checks, rollback, self-host, VPS, backup, and restore instructions back to the
  live code surfaces listed above.
- **Monetization/donations are a feature flag**, surfaced only after the domain + posture are
  settled. This is a copy/link toggle, never a re-architecture, and never blocks development.

## Migrations & backups

- SQL-first (`db/migrations`); apply with `node scripts/dev/migrate.mjs --seed` against any
  `DATABASE_URL`. Forward-fix policy — see [`../../db/README.md`](../../db/README.md).
- Neon branching + point-in-time restore and the portable `pg_dump`/R2 restore proof are documented
  in [`../operations/backups.md`](../operations/backups.md).

## Free-tier drift

Neon CU-hours, Upstash command caps, and R2 limits change. Because the canonical store is plain
Postgres+pgvector behind a DB adapter, any forced move is a `pg_dump`/`pg_restore`, not a
refactor. Re-verify free-tier numbers at setup.
