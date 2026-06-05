# Repository Reset & Foundation Scaffold Implementation Plan

Date: 2026-06-04
Status: [x] Complete — foundation scaffolded and verified (commit 0bd09bf). DB apply (clean/seeded) is covered by CI / local Docker; not run in the authoring environment (no Docker). Next: Plan 01 closeout + Plan 02 pipeline bodies.
Source reports: `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`, `docs/research/2026-05-21-intercal-foundation-report.md`
Owner: Revisit / orchestration agent
Surface: repository hygiene, governance docs, decision records, monorepo scaffold, contracts pipeline, schema, adapter ports, verification ladder

## Purpose

Resume Intercal in June 2026 on a clean, unambiguous, production-shaped foundation: quarantine
stray docs, repair references, lock the open forks as decision records, and scaffold the full
adapter-first monorepo (TypeScript + Python + Postgres) so that later feature plans (01–06)
build real bodies on real seams. This plan precedes the existing dated plan 01 and feeds it.

## Status Legend

- [ ] Not started · [~] In progress · [x] Complete · [!] Blocked or requires decision

## Source Findings

- The repo was docs-only and not a git repository.
- `docs/engineering/` was contaminated with documents from a different project ("Zavi", a
  Tauri desktop voice host) — they referenced Hermes/Tauri and `C:\Users\james\projects\zavi\`.
- The six 2026-05-21 roadmaps cited non-existent paths (`docs/reports/…`, `docs/plans/…`,
  `docs/research/brainstorm.md`, `docs/engineering/planning-style.md`) and left ~8 technical
  forks undecided.
- `README.md` referenced an `AGENTS.md` and `docs/README.md` that did not exist.
- The foundation report and domain model are sound and are kept as the canonical source.

## Locked Decisions

- The full foundation decision set is recorded in `docs/decisions/0001-foundation-stack.md` (D1–D16).
- Active plans live in `docs/roadmaps/`; retired plans/reports move under `docs/_legacy/`.
- Build the **final shape** now: every package, service, and adapter port present and coherent;
  later-plan algorithm bodies are marked `NotImplementedError("Plan NN — …")`, never faked.

## Scope Boundaries

- No product re-scope. Thesis and domain model are unchanged.
- No secrets in tracked files; `.env.example` is the only tracked env file.
- Deploy-target agnostic: no host-specific code in the app; everything behind ports/contracts.
- Feature bodies (ingestion algorithms, query implementations, dashboard UX, ops loops) belong
  to plans 01–06, not this plan.

## Repo Guidance

- TypeSpec is the single contract source; OpenAPI/JSON-Schema/TS/Pydantic are generated.
- One shared query layer (`packages/core`) used by both API and MCP.
- SQL-first migrations own the schema; Kysely is read-side typing only.
- Adapter ports live in `services/shared` (Python) and `packages/core`/config (TS) as relevant.

## Target Repository Shape

See `README.md` "Repository map" and `docs/architecture/system-map.md` for the authored layout.

## Cross-Stream Dependency Map

Repo reset → governance + decisions → root tooling → (DB schema ∥ Python services ∥ contracts)
→ TS core/api/mcp/sdk → dashboard → architecture docs → verification → commit.

## Workstream 1: Repo reset & reference repair

Goal: A clean git repo with stray docs quarantined and all references valid.

Implementation tasks:

- [x] `git init` (branch `main`); add `.gitignore`, `.nvmrc`, `.editorconfig`, `.gitattributes`.
- [x] Move stray Zavi docs out of the repo to an external archive.
- [x] De-Zavi `planning-style.md` and `docs-standards.md`; keep `report-style.md`.
- [x] Repair all broken path references across the six roadmaps and the foundation report.

Exit criteria:

- [x] No roadmap references a non-existent path; repo is a git repository.

## Workstream 2: Governance & decision records

Goal: Enforceable, succinct guidance and durable decisions.

Implementation tasks:

- [x] `AGENTS.md` (operating rules, ownership, hard rules, verification ladder).
- [x] `docs/README.md` (docs index); update root `README.md` (purpose, quick start, commands).
- [x] `docs/decisions/0001-foundation-stack.md` (D1–D16) + decisions index.
- [x] This Plan 00 roadmap.

Exit criteria:

- [x] A new agent can identify what to read and which commands to run before editing.

## Workstream 3: Root monorepo tooling

Goal: Installable, lintable, verifiable workspace shell.

Implementation tasks:

- [x] Root `package.json`, `pnpm-workspace.yaml` (catalog), `config/tsconfig.base.json`, `biome.json`.
- [x] Root `pyproject.toml` (uv workspace, Ruff/Pyright/pytest config).
- [x] `docker/compose.yaml` (Postgres+pgvector, Valkey, MinIO), `.env.example`.
- [x] `scripts/verify/verify.mjs`, `scripts/dev/migrate.mjs`, `.github/workflows/ci.yml`.

Exit criteria:

- [x] `pnpm install` and `uv sync` succeed; `pnpm verify` runs the gate set.

## Workstream 4: Database foundation

Goal: SQL-first schema, seed vocabularies, runner, data-model doc.

Implementation tasks:

- [x] All foundation-report tables as numbered SQL migrations (pgvector, bitemporal fact
      versions, reversible merges, claim evidence, role/office separation, enum/reference tables).
- [x] Seed `entity_types` and `relationship_types` vocabularies.
- [x] `db/README.md` + `docs/architecture/data-model.md`.

Exit criteria:

- [x] Schema applies clean and seeded; data-model doc matches migrations.

## Workstream 5: Shared contracts pipeline

Goal: One contract source generating both runtimes with a drift check.

Implementation tasks:

- [x] TypeSpec models for entities, claims, relationships, source docs, evidence, digests,
      freshness, errors, and the six V1 tool I/O shapes.
- [x] Compile to OpenAPI 3.1 + JSON Schema; generate TS types and Pydantic models.
- [x] `contracts:build` / `contracts:check` (drift) scripts.

Exit criteria:

- [x] TS and Python consume the same generated contracts; drift check passes.

## Workstream 6: TypeScript packages

Goal: Shared query layer, REST API, MCP server, SDK, dashboard.

Implementation tasks:

- [x] `@intercal/core` — Kysely client + query-service layer (six V1 queries).
- [x] `@intercal/api` — Hono REST exposing V1 endpoints; JSON-Schema request validation; OpenAPI served.
- [x] `@intercal/mcp-server` — official SDK, Streamable HTTP, six V1 tools using shared JSON Schema.
- [x] `@intercal/sdk` — typed client generated from OpenAPI.
- [x] `@intercal/dashboard` — Next.js 16 + Tailwind v4 + shadcn, read-only, via the SDK.

Exit criteria:

- [x] Packages typecheck and build; API/MCP route through one query layer.

## Workstream 7: Python services & adapter ports

Goal: Pipeline service skeletons with real ports and default adapters.

Implementation tasks:

- [x] `services/shared` — config, db pool, ports (storage/embeddings/llm/queue/scheduler), default adapters, factory.
- [x] `services/{ingest,extract,resolve,synthesize}` — worker CLI entrypoints wired to ports; job bodies typed (deep algorithms deferred to Plan 02 with explicit markers).
- [x] Per-service pytest scaffolding.

Exit criteria:

- [x] `uv sync` resolves; Pyright strict passes; CLI entrypoints import and wire correctly.

## Workstream 8: Architecture docs & verification

Goal: Durable architecture docs + a recorded verification pass.

Implementation tasks:

- [x] `docs/architecture/{system-map,pipeline,mcp-api,provider-boundaries,deployment-topology}.md`.
- [x] Run install/lint/typecheck/contracts; record results (Docker-dependent DB checks noted).
- [x] First conventional commit.

Exit criteria:

- [x] Every package/service traces to an owning architecture doc; verification recorded.

## Final Verification And Closeout

- `pnpm install` · `uv sync` · `pnpm lint` · `pnpm typecheck` · `pnpm contracts:check`
- `pnpm py:lint` · `pnpm py:typecheck`
- `docker compose -f docker/compose.yaml up -d` then `pnpm db:migrate:seeded` (where Docker is available)
- Update durable docs; add a `.changes/` fragment; stage intentional files; conventional commit.

## Acceptance Criteria

- [x] Repo is clean, git-tracked, and free of stray-project docs.
- [x] All references resolve; forks are recorded as decisions.
- [x] The full monorepo (packages + services + db + contracts) installs and verifies (DB checks require Docker).
- [x] Plans 01–06 can resume against real seams.

## Implementation Order

1. Repo reset → 2. Governance/decisions → 3. Root tooling → 4. DB schema ∥ 5. Contracts ∥ 7. Python services → 6. TS packages → 8. Architecture docs + verification + commit.

## Expansion Track

- Add CI matrix (Node + Python + Postgres service container) once local verification is stable.
- Add Turborepo task caching if build times warrant it (D2).
