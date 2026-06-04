# Implementation Planning Style

Use this format for reusable implementation plans that need to guide real work, survive handoff, and retire cleanly once complete. Plans should be specific enough to execute without rediscovery, but not so broad that they become a second product spec.

## Plan Shape

Start each plan with:

- `# <Domain Or Feature> Implementation Plan`
- `Date`, `Status`, `Source reports`, `Owner`, and `Surface`
- A short `Purpose` section that states the outcome and scope
- `Status Legend` using `[ ]`, `[~]`, `[x]`, and `[!]`

Then include these sections in order:

1. `Source Findings`: facts discovered from code, docs, data, tests, product behavior, or source reports.
2. `Locked Decisions`: choices that stay stable during implementation and
   change only when source-truth facts change.
3. `Scope Boundaries`: concise boundaries for security, runtime exposure,
   provider behavior, migrations, and customer-visible claims.
4. `Repo Guidance`: local rules that shape the implementation, such as owning packages/services, port/adapter seams, the API/MCP contract boundary, migration ownership, changelog requirements, test strategy, and command expectations.
5. `Target Repository Shape` or `Target Product Shape`: concrete files, packages, services, port interfaces, MCP tools, REST endpoints, data contracts, UI surfaces, or operating model.
6. `Cross-Stream Dependency Map`: a short dependency graph that explains which streams must land first and which streams consume their outputs.
7. `Workstream N: <Name>` sections with goal, dependencies, primary areas, implementation tasks, exit criteria, and suggested verification.
8. `Final Verification And Closeout`: all required commands, cleanup, changelog, staging, commit, and push expectations.
9. `Acceptance Criteria`: the complete definition of done.
10. `Implementation Order`: a dependency-ordered numbered sequence for the agent or engineer.
11. `Expansion Track`: optional ideas for follow-up implementation.

## Workstream Template

Each workstream should be independently executable and reviewable.

```markdown
## Workstream N: <Name>

Goal: <one-sentence outcome>

Depends on:

- [ ] Workstream X output or existing module/contract that must exist first.

Enables:

- [ ] Workstream Y or product capability that will consume this result.

Repo guidance:

- Follow the established owner package/service, port/adapter seam, contract
  boundary, or verification rule relevant here.

Primary areas:

- `path/or/package`
- `another/path`

Implementation tasks:

- [ ] Concrete task with an observable result.
- [ ] Another concrete task.

Exit criteria:

- [ ] The durable state that confirms this stream is done.

Suggested verification:

- `pnpm test -- <focused>`
- `pnpm lint`  /  `uv run pytest <focused>`
```

Add dated implementation notes inside a workstream only while executing or
retiring the plan. Keep those notes factual: what changed, what was verified,
and what moves into follow-up implementation.

## Writing Rules

- Search before locking the plan. Cite local source reports, docs, packages, services, scripts, migrations, or tests by path.
- Design streams to flow in dependency order. Foundations, schema, contracts, or shared helpers should come before API, MCP, SDK, dashboard, and final verification streams that depend on them.
- Only use checklists for open tasks, not lists and commands.
- Call out cross-dependencies in each stream. Name upstream prerequisites and downstream consumers so agents know what can run in parallel and what runs in sequence.
- Keep plans under `docs/roadmaps/` while active. Move completed dated plans to `docs/_legacy/roadmaps/` after durable docs and changelog fragments carry the ongoing operating rules.
- Keep top-level docs stable. `README.md`, `docs/README.md`, and `AGENTS.md` should point to durable directories or canonical planning guidance, not individual dated plans.
- Prefer durable policies in engineering, operations, architecture, or security docs. A retired plan is history, not the living contract.
- Write tasks as verifiable outcomes, not vague intentions. Use "Add contract tests for the entity payload..." instead of "improve tests."
- Keep streams complete. A stream should include implementation, tests, docs/changelog when needed, and verification for the behavior it owns.
- Include repo guidance where it matters: package/service split, port/adapter seams, the API/MCP contract boundary, SQL-first migration ownership, contract drift checks, fixture heartbeat verification, and test limits.
- Name scope early: what ships now, what uses metered cloud provider access, what uses explicit operator action, what stays local/free-tier, and how secrets stay in the host secret store and out of tracked files.
- Intercal is a Postgres-backed, provider-agnostic web/API monorepo. When a plan changes a persisted contract (a migration, a TypeSpec/OpenAPI contract, a seed vocabulary, an MCP tool schema, a usage/telemetry shape), record its shape and the verification that proves it on a clean and a seeded database.
- Include changelog requirements when production-meaningful code, docs, scripts, package metadata, CI, security, or operations behavior changes.
- End with final cleanup and publishing expectations so the plan naturally reaches committed, pushed work.

## Retirement Rules

When the plan is complete:

- Update checkboxes and closeout notes truthfully.
- Move dated plans and dated source reports to `docs/_legacy/`.
- Promote any permanent rules to durable docs.
- Keep changelog fragments as the release source of truth.
- Keep active docs pointed at current operating guidance.
