# Foundation And Contracts Implementation Plan

Date: 2026-05-21
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/user-notes/brainstorm.md`
Owner: Main orchestration agent
Surface: repository foundation, engineering rules, architecture docs, database schema, shared contracts, local verification

## Purpose

Establish Intercal's clean engineering foundation before product work lands. This plan owns the monorepo scaffold, durable repo rules, architecture documentation, SQL-first schema foundation, runtime-neutral contracts, and verification ladders that every later plan consumes.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- `docs/research/2026-05-21-intercal-foundation-report.md` defines Intercal as a greenfield temporal knowledge substrate, not a Changelog or Sherlock retrofit.
- `docs/research/2026-05-21-intercal-foundation-report.md` locks Python for ingestion/extraction/resolution/embeddings/synthesis and TypeScript for REST/MCP/SDK/dashboard.
- `docs/research/2026-05-21-intercal-foundation-report.md` requires Postgres with pgvector as the canonical datastore and SQL-first migrations.
- `docs/research/2026-05-21-intercal-foundation-report.md` requires JSON Schema/OpenAPI-first public contracts and provider-agnostic model/embedding boundaries.
- Current repository contents are docs-only under `docs/`; no Git repository is initialized yet.
- `docs/engineering/standards/planning-style.md` is the reusable plan format for all active plans.

## Locked Decisions

- Use `pnpm` workspaces for the TypeScript monorepo.
- Use `uv` for Python package and environment management.
- Use Postgres + pgvector as canonical storage.
- Use SQL-first migrations; ORM/query helpers must not hide schema ownership.
- Use JSON Schema/OpenAPI as public contract source of truth.
- Keep Vertex, Azure, OpenAI, Anthropic, and local providers behind replaceable provider adapters.
- Keep local, VPS, and managed deployment paths portable from the start.

## Non-Goals

- [ ] Do not implement ingestion, extraction, MCP tools, dashboard UX, subscriptions, or hosted deployment beyond foundation proof.
- [ ] Do not copy code from `C:\Users\james\projects\changelog` or `C:\Users\james\projects\sherlock`.
- [ ] Do not make live provider credentials required for tests.
- [ ] Do not expose secrets or account-specific setup in committed files.
- [ ] Do not treat dated plans as durable operating rules after completion.

## Repo Guidance

- Use Windows-native commands for local setup and verification.
- Keep `AGENTS.md` succinct and enforceable; durable details belong in `docs/engineering`, `docs/architecture`, `docs/operations`, or `docs/security`.
- Keep active plans in `docs/roadmaps/`; completed dated plans move to `docs/_legacy/roadmaps/`.
- Initialize changelog policy in this plan so later production-meaningful changes have a release source of truth.
- Every schema table introduced here needs migration verification on clean and seeded databases.
- Generated contracts must have a documented generation command and drift check.

## Target Repository Shape

```text
intercal/
  AGENTS.md
  README.md
  package.json
  pnpm-workspace.yaml
  pyproject.toml
  uv.lock
  docker/compose.yaml
  docs/
    architecture/
    decisions/
    engineering/
    operations/
    plans/
    reports/
    security/
  packages/
    api/
    mcp-server/
    sdk/
    shared/
    dashboard/
  services/
    ingest/
    extract/
    resolve/
    synthesize/
  db/
    migrations/
    seeds/
  scripts/
    verify/
    dev/
```

## Cross-Stream Dependency Map

Repository scaffold -> repo rules -> architecture docs -> decision records -> database foundation -> shared contracts -> verification ladder -> fixture heartbeat -> final closeout.

## Workstream 1: Repository Scaffold

Goal: Create the installable monorepo shell and local service layout.

Depends on:

- [ ] Current docs scaffold under `docs/`.

Enables:

- [ ] Workstream 2 repo rules.
- [ ] Workstream 7 verification commands.

Repo guidance:

- Keep package boundaries aligned with `docs/research/2026-05-21-intercal-foundation-report.md`.

Primary areas:

- `package.json`
- `pnpm-workspace.yaml`
- `pyproject.toml`
- `docker/compose.yaml`
- `packages/*`
- `services/*`
- `db/*`
- `scripts/*`

Implementation tasks:

- [ ] Initialize Git if the repository remains uninitialized.
- [ ] Add TypeScript workspace package manifests for API, MCP, SDK, shared contracts, and dashboard.
- [ ] Add Python package/service structure managed by `uv`.
- [ ] Add Docker Compose for local Postgres, pgvector, Redis/Valkey, and object-storage-compatible local service.
- [ ] Add shared env examples without secrets.
- [ ] Add root commands for install, dev, and verification.

Exit criteria:

- [ ] Fresh checkout can install TypeScript and Python dependencies.
- [ ] Local infrastructure starts and exposes health checks.

Suggested verification:

- `pnpm install`
- `uv sync`
- `docker compose config`
- `docker compose -f docker/compose.yaml up -d`

## Workstream 2: Repo Rules And Durable Guidance

Goal: Create enforceable project guidance for agents and contributors.

Depends on:

- [ ] Workstream 1 repository paths.

Enables:

- [ ] All later plans.

Repo guidance:

- `AGENTS.md` must stay short; deep rules live in durable docs.

Primary areas:

- `AGENTS.md`
- `README.md`
- `docs/engineering/standards/planning-style.md`
- `docs/operations/development.md`
- `docs/security/secrets.md`

Implementation tasks:

- [ ] Add `AGENTS.md` with source-of-truth docs, ownership boundaries, no-copy rule, verification ladder, docs requirements, generated-file policy, secrets policy, and closeout requirements.
- [ ] Add `README.md` with project purpose, setup, command index, and docs map.
- [ ] Add development operations doc with Windows-native command expectations.
- [ ] Add secrets handling doc.

Exit criteria:

- [ ] A new agent can identify what to read and which commands to run before editing.

Suggested verification:

- Manual doc review against `docs/engineering/standards/planning-style.md`.

## Workstream 3: Architecture And Decision Records

Goal: Promote accepted architecture into durable docs and decision records.

Depends on:

- [ ] Workstream 2 repo guidance.

Enables:

- [ ] Workstream 5 database foundation.
- [ ] Plans 02-06.

Repo guidance:

- Dated plans can cite durable docs, but durable docs must not depend on plan files for operating rules.

Primary areas:

- `docs/architecture/system-map.md`
- `docs/architecture/data-model.md`
- `docs/architecture/pipeline.md`
- `docs/architecture/mcp-api.md`
- `docs/architecture/provider-boundaries.md`
- `docs/architecture/deployment-topology.md`
- `docs/decisions/*.md`

Implementation tasks:

- [ ] Add system map with package/service ownership.
- [ ] Add data model doc with table responsibilities and invariants.
- [ ] Add pipeline doc from source adapter through fact version.
- [ ] Add MCP/API contract doc.
- [ ] Add provider boundary doc for model, embedding, search, storage, queue, and hosting adapters.
- [ ] Add deployment topology doc covering local, VPS, and managed paths.
- [ ] Add decision records for the locked decisions in this plan.

Exit criteria:

- [ ] Durable docs describe the intended production architecture and current implementation status.

Suggested verification:

- Manual trace from every package/service to an owning architecture doc.

## Workstream 4: Database Foundation

Goal: Create the canonical SQL schema, seeds, and migration checks.

Depends on:

- [ ] Workstream 3 data model decisions.

Enables:

- [ ] Workstream 5 shared contracts.
- [ ] Plan 02 pipeline implementation.

Repo guidance:

- Include migration IDs once the migration convention is established.
- Every schema change needs clean and seeded database verification.

Primary areas:

- `db/migrations`
- `db/seeds`
- `db/schema`
- `scripts/verify`
- `docs/architecture/data-model.md`

Implementation tasks:

- [ ] Add migrations for sources, source documents, chunks, embeddings, ingestion runs, entities, aliases, external IDs, resolution candidates, merge events, mentions, claims, claim evidence, contradictions, relationship types, relationships, fact versions, topics, digests, subscriptions, API keys, usage events, and audit events.
- [ ] Seed entity and relationship type vocabularies.
- [ ] Add pgvector extension setup.
- [ ] Add constraints for document hashes, append-only fact versions, source evidence, and reversible merge bookkeeping.
- [ ] Add clean DB and seeded DB migration scripts.

Exit criteria:

- [ ] Schema applies from scratch and with seed data.
- [ ] Data model docs match actual migrations.

Suggested verification:

- `pnpm db:migrate:clean`
- `pnpm db:migrate:seeded`
- `pnpm db:schema:check`

## Workstream 5: Shared Contracts

Goal: Create runtime-neutral contracts and generated/wrapped validators.

Depends on:

- [ ] Workstream 4 database foundation.

Enables:

- [ ] Plan 02 provider and pipeline payloads.
- [ ] Plan 03 REST/MCP contracts.

Repo guidance:

- Contract source of truth belongs in `packages/shared` or an equivalent documented contract folder.

Primary areas:

- `packages/shared`
- `packages/api`
- `packages/mcp-server`
- `services/*`
- `docs/architecture/mcp-api.md`

Implementation tasks:

- [ ] Add JSON Schema/OpenAPI contracts for entities, claims, relationships, source documents, evidence, digests, freshness, errors, and provider envelopes.
- [ ] Add TypeScript validators/types.
- [ ] Add Python validators/types.
- [ ] Add contract generation and drift check scripts.
- [ ] Add contract snapshot tests.

Exit criteria:

- [ ] TypeScript and Python consume the same contract source without drift.

Suggested verification:

- `pnpm contracts:generate`
- `pnpm contracts:check`
- `pnpm test -- contracts`
- `uv run pytest services/*/tests`

## Workstream 6: Verification Ladder And Fixture Heartbeat

Goal: Create the commands and fixture path later streams must keep green.

Depends on:

- [ ] Workstream 5 shared contracts.

Enables:

- [ ] Plan 02 end-to-end pipeline verification.
- [ ] Plan 05 release audit.

Repo guidance:

- Verification commands should be local and CI-suitable.

Primary areas:

- `scripts/verify`
- `packages/*/tests`
- `services/*/tests`
- `db/seeds`
- `docs/operations/development.md`

Implementation tasks:

- [ ] Add TypeScript format, lint, typecheck, test, and build commands.
- [ ] Add Python format, lint, typecheck, and test commands.
- [ ] Add migration, schema, and contract verification commands.
- [ ] Add fixture seed documents and expected output contracts for mentions, claims, resolution candidates, relationships, fact versions, and `get_delta`.
- [ ] Add a single full local verification command.

Exit criteria:

- [ ] Foundation verification command runs the complete current gate set.

Suggested verification:

- `pnpm verify`

## Final Verification And Closeout

- `pnpm install`
- `uv sync`
- `docker compose -f docker/compose.yaml up -d`
- `pnpm format:check`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest`
- `pnpm db:migrate:clean`
- `pnpm db:migrate:seeded`
- `pnpm contracts:check`
- `pnpm verify`
- Update `README.md`, `AGENTS.md`, architecture docs, operations docs, decision records, and this plan's dated notes.
- Add changelog fragment if changelog policy exists by closeout.
- Stop local services or document why they remain running.
- Stage intentional files only.
- Commit with a conventional subject and push once the repo has a remote.

## Acceptance Criteria

- [ ] Repository foundation installs and runs local infrastructure.
- [ ] `AGENTS.md` and durable docs define enforceable rules.
- [ ] Database schema, seeds, contracts, and verification commands exist.
- [ ] TypeScript and Python validators share the same contract source.
- [ ] Fixture heartbeat exists and is documented.
- [ ] No source report or plan artifact is used as a permanent operating rule.

## Implementation Order

1. Repository scaffold.
2. Repo rules and durable guidance.
3. Architecture docs and decision records.
4. Database foundation.
5. Shared contracts.
6. Verification ladder and fixture heartbeat.
7. Final verification, docs, changelog, commit, and push.

## Future Expansion

- Add task caching only after workspace scale justifies it.
- Add CI provider configuration after local verification is stable.
- Add managed deployment automation in Plan 04.
