# AGENTS.md — Intercal operating rules

Intercal is an open, provenance-backed **temporal knowledge substrate** for agents and
LLM apps: source documents → claims → resolved entities → typed temporal relationships →
append-only bitemporal fact versions, served over **MCP + REST**. Read this before editing.

## Source of truth (in priority order)

1. **The live code**: migrations (`db/`), contracts (`packages/shared`), adapter ports,
   the MCP/REST surface, and tests own executable truth.
2. **Architecture docs** (`docs/architecture/`) explain ownership and data flow.
3. **Decision records** (`docs/decisions/`) record durable choices and their rationale.
4. **Research reports** under `docs/research/` define the product thesis, domain model, and
   current stack baseline.
5. **Active roadmap** (`docs/roadmaps/`) is a guide, not proof — verify against code.

Never treat a brainstorm, report, or dated plan as implemented behavior unless the code
confirms it.

## Ownership boundaries

- `packages/shared` — contracts: **TypeSpec is the single source**; OpenAPI 3.1 + JSON
  Schema + TS types + Pydantic models are **generated**. Never hand-edit generated files.
- `packages/core` — shared DB access (Kysely, read-side) + the query-service layer used by
  both API and MCP. One query layer, no duplicated semantics.
- `packages/api` (Hono REST), `packages/mcp-server` (official MCP SDK, Streamable HTTP),
  `packages/sdk` (typed client), `packages/dashboard` (Next.js, **read-only**).
- `services/{ingest,extract,resolve,synthesize}` (Python/uv) — the pipeline. `services/shared`
  (`intercal_shared`) owns the **adapter ports** and default adapters.
- `db/` — **SQL-first** migrations own schema, constraints, indexes, and seed vocabularies.
  No ORM hides schema ownership.

## Hard rules

- **Adapters for every external dependency** (DB, vector index, object storage [S3 API],
  queue/cache, embeddings, LLM, scheduler). Provider logic never crosses the port boundary.
  The product must be deploy-target agnostic and provider-swappable without a migration.
- **No mocks, placeholders, broad compatibility shims, or hidden demo data.** Work that
  belongs to a later plan is marked `NotImplementedError("Plan NN — …")`, not faked.
- **No copying code** from the `changelog` or `sherlock` reference projects without explicit
  approval. They are references only.
- **Secrets** live in the host secret store; `.env` is dev-only and never committed
  (`.env.example` is the only tracked env file). Never write a secret into code, docs,
  contracts, fixtures, logs, or output.
- **Provenance**: every publicly served fact must trace to claim evidence → source documents.
  Append-only fact history; conservative entity resolution (false merges are corruption).
- **Verify drift-prone external facts** (models, APIs, MCP spec version, pricing, licensing)
  against official sources before locking them into code or durable docs.
- **First principles.** When a constraint, error, or surprise appears, ask why it exists and
  keep asking several layers deep until the cause leaves our control before choosing a deep
  refactor or a tactical patch. Never trade away integrity, security, correctness, or
  evidence quality for speed.
- **No-cost constraint.** Stay within approved subscriptions, credits, and free tiers per
  `docs/operations/resource-budget.md`; stop and report rather than incur spend.

## Verification ladder

Run the narrowest complete set for what you touched; `pnpm verify` runs the full gate.

- TypeScript: `pnpm lint` · `pnpm typecheck` · `pnpm test` · `pnpm build`
- Contracts: `pnpm contracts:check` (regenerate + drift check)
- Python: `pnpm py:lint` · `pnpm py:typecheck` · `pnpm py:test` (Ruff / Pyright / pytest)
- Database: `pnpm db:migrate:clean` · `pnpm db:migrate:seeded` · `pnpm db:check`
  (requires Docker Postgres via `docker compose -f docker/compose.yaml up -d`)

## Docs & changelog

- Docs standards live in `docs/_standards/` (symlink to the canonical
  `_ops/planning/_standards/`). Follow the dev-docs standard for internal docs and the
  user-manual standard for this repo's self-owned user docs.
- Active plans in `docs/roadmaps/`; retire completed dated plans to `docs/_legacy/roadmaps/`.
- Add a `.changes/` fragment when production-meaningful code, contracts, CI, security, or
  ops behavior changes. Keep durable docs describing **actual** behavior.

## Closeout

Confirm no secrets in tracked files/output; keep roadmap and durable docs accurate; leave
unrelated changes untouched; report verification run + result and any command that could not
run because the surface does not exist yet; stage only intentional changes; conventional
commit subject + body.
