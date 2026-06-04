# Documentation Standards

Durable docs should make Intercal easier to operate without becoming a second
implementation surface. The live repo remains the source of truth.

## Ownership

- Code contracts (TypeSpec source and generated OpenAPI/JSON Schema), database
  migrations, the MCP tool surface, the REST API surface, adapter port
  interfaces, tests, and runtime artifacts own executable truth.
- System/architecture docs explain ownership, data flow, and execution paths.
- Operations docs explain how to perform a task safely.
- Adapter/provider docs explain a port's purpose, the providers behind it, setup
  state, and runtime expectations.
- Research/feasibility docs are source reports, not task lists or operating policy.
- Roadmaps hold active implementation steps and retire to `docs/_legacy/roadmaps/`.

## Link Policy

- Prefer links to stable directories and source-owned files.
- Avoid links from durable docs to dated roadmap files. The `docs/roadmaps/`
  directory can hold the active plan; durable docs should not hardcode a dated
  plan as current guidance.
- Legacy links are allowed only when a doc is explicitly describing history.
- Do not add subdirectory README files except where a directory owns executable
  truth (e.g. `db/README.md`). Use `docs/README.md` as the docs index.

## Drift Controls

- Do not duplicate adapter rosters, model/provider lists, the MCP tool table,
  pinned dependency versions, free-tier limits, or volatile status tables in
  durable docs.
- If a value is expected to change with setup or runtime status, point to the
  port/adapter source, the official provider docs, or a status artifact instead.
- Verify drift-prone external facts against official provider sources before
  changing model, API, protocol-version, pricing, licensing, or provider-access
  claims. (See the dated revisit report for the June 2026 baseline and the
  scheduled re-verification.)
- Do not promote a model, adapter, provider, MCP spec version, or dependency
  version claim to stable without recorded evidence.

## Status Handling

- Status docs record commands, dates, outputs, provider-access failures, and
  safety checks when they matter.
- Status docs are not the primary operating guide. If a status record creates a
  lasting rule, promote the rule into a system or operations doc.
- Never write API keys, tokens, signed URLs, connection strings carrying
  credentials, or any secret into docs, fixtures, adapter config, contracts,
  metadata, screenshots, or logs.

## Retirement

- Move completed or superseded plans to `docs/_legacy/roadmaps/`.
- Move obsolete research or task notes to `docs/_legacy/research/`.
- When retiring a doc, repair active links and keep only the stable rule in the
  durable doc that owns it.
- Do not leave hidden open decisions in prose. Put them in an active roadmap,
  report, status note, or decision record.
