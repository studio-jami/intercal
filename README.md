# Intercal

**An open, provenance-backed temporal knowledge substrate for agents and LLM applications.**

Intercal answers a precise question that retrieval and stale model weights cannot:

> Given a topic, entity, claim, or model cutoff date — what has changed since then, what
> evidence supports it, how confident is the system, and how compactly can that update be
> delivered?

It maintains a continuously updated, source-grounded knowledge layer — source documents →
extracted claims → resolved entities → typed temporal relationships → **append-only
bitemporal fact versions** — queryable by date, topic, entity, relationship, claim,
confidence, and token budget, over **MCP and a REST API**.

This is not a news scraper, a digest blog, a generic vector-DB wrapper, or a private
notebook. See [`docs/research/2026-05-21-intercal-foundation-report.md`](docs/research/2026-05-21-intercal-foundation-report.md)
for the full thesis and domain model.

## Architecture at a glance

- **Python services** (`uv`): ingestion, extraction/claim-modeling, entity resolution,
  embeddings, synthesis — the pipeline.
- **TypeScript packages** (`pnpm`): a shared query layer, a Hono **REST API**, an **MCP
  server** (official SDK, Streamable HTTP), a typed **SDK**, and a read-only **dashboard**
  (Next.js).
- **Postgres + pgvector** is the single canonical store (SQL-first migrations).
- **Adapters for every external dependency** (DB, vector index, object storage [S3 API],
  queue/cache, embeddings, LLM, scheduler). Provider logic never crosses the port boundary,
  so Intercal is **deploy-target agnostic and provider-swappable without migrations.**

Decisions and their rationale: [`docs/decisions/0001-foundation-stack.md`](docs/decisions/0001-foundation-stack.md).

## Repository map

```text
packages/
  shared/      @intercal/shared      — contracts: TypeSpec source → generated OpenAPI/JSON-Schema/TS types
  core/        @intercal/core        — shared DB access (Kysely) + the query-service layer
  api/         @intercal/api         — Hono REST API (deploy-agnostic)
  mcp-server/  @intercal/mcp-server  — MCP server (official SDK, Streamable HTTP)
  sdk/         @intercal/sdk         — typed client SDK
  dashboard/   @intercal/dashboard   — Next.js read-only knowledge experience
services/
  shared/      intercal_shared       — adapter ports + default adapters + db pool + generated Pydantic
  ingest/  extract/  resolve/  synthesize/   — the Python pipeline workers
db/
  migrations/  seeds/                — SQL-first schema + seed vocabularies
scripts/
  verify/  dev/  workers/            — verification, local dev, portable worker entrypoints
docs/                                — architecture, decisions, engineering standards, operations, roadmaps, research
```

## Quick start

Prerequisites: **Node 24** (`.nvmrc`), **pnpm 10+**, **uv**, and **Docker** (for local
Postgres/Redis/MinIO).

```bash
pnpm install                 # TypeScript workspace
uv sync                      # Python workspace
cp .env.example .env         # local config (no secrets committed)
docker compose up -d         # Postgres+pgvector, Valkey, MinIO
pnpm contracts:build         # TypeSpec -> OpenAPI/JSON-Schema -> TS + Pydantic
pnpm db:migrate:seeded       # apply schema + seed vocabularies
pnpm verify                  # full gate: lint, typecheck, tests, contracts, db
```

## Command index

| Command | What it does |
| --- | --- |
| `pnpm verify` | Full local gate (TS + Python + contracts + DB). |
| `pnpm lint` / `pnpm format` | Biome lint / format (TypeScript). |
| `pnpm typecheck` / `pnpm test` | TS typecheck / tests. |
| `pnpm contracts:build` / `pnpm contracts:check` | Regenerate contracts / drift check. |
| `pnpm db:migrate:clean` / `:seeded` / `pnpm db:check` | Apply migrations (fresh / seeded) / schema check. |
| `pnpm py:lint` / `py:typecheck` / `py:test` | Ruff / Pyright / pytest (Python). |
| `pnpm dev` | Run the dashboard locally. |

## Default workflow

1. Read the owning docs and code before changing anything ([`AGENTS.md`](AGENTS.md)).
2. Use a feasibility/research report for unclear vendor/architecture/source-policy questions
   (saved under `docs/research/`, format in `docs/engineering/standards/report-style.md`).
3. Convert accepted direction into a roadmap (`docs/roadmaps/`) before broad implementation.
4. Implement through the owning packages, services, contracts, migrations, and tests.
5. Update durable docs and add a `.changes/` fragment when behavior changes.
6. Run the narrowest complete verification ladder before closeout.

See [`AGENTS.md`](AGENTS.md) for the full operating rules and [`docs/README.md`](docs/README.md)
for the documentation map.

## License

Apache-2.0. Open source. Non-commercial during the pilot; any monetization/donation surface
is feature-flagged off until a domain and commercial-friendly host are in place.
