# Intercal Documentation

The docs map. The live repo is the source of truth; these docs explain ownership, data
flow, decisions, and how to operate Intercal safely.

## Start here

- [`../README.md`](../README.md) — project purpose, quick start, command index.
- [`../AGENTS.md`](../AGENTS.md) — operating rules and ownership boundaries (read first).

## Architecture (durable)

- [`architecture/system-map.md`](architecture/system-map.md) — package/service ownership and boundaries.
- [`architecture/data-model.md`](architecture/data-model.md) — schema, invariants, the bitemporal model.
- [`architecture/pipeline.md`](architecture/pipeline.md) — source → claim → entity → relationship → fact version.
- [`architecture/mcp-api.md`](architecture/mcp-api.md) — the MCP tool + REST contract surface.
- [`architecture/provider-boundaries.md`](architecture/provider-boundaries.md) — the adapter ports and what sits behind each.
- [`architecture/deployment-topology.md`](architecture/deployment-topology.md) — local / pilot (free-tier) / managed paths.

## Decisions

- [`decisions/`](decisions/) — durable decision records (D1–D16 from the June-2026 revisit, and onward).

## Engineering standards

- [`engineering/standards/planning-style.md`](engineering/standards/planning-style.md) — how roadmaps are written.
- [`engineering/standards/report-style.md`](engineering/standards/report-style.md) — how feasibility/research reports are written.
- [`engineering/standards/docs-standards.md`](engineering/standards/docs-standards.md) — documentation ownership, drift control, retirement.

## Operations (durable)

- `operations/` — development setup, deployment, backups, source policy, observability,
  review workflows, account setup (authored as the relevant roadmaps land).

## Roadmaps (active, dated)

- [`roadmaps/`](roadmaps/) — active implementation plans. Completed plans retire to `_legacy/roadmaps/`.

## Research / reports (dated source material)

- [`research/2026-05-21-intercal-foundation-report.md`](research/2026-05-21-intercal-foundation-report.md) — canonical product thesis + domain model.
- [`research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`](research/2026-06-04-intercal-revisit-audit-and-dev-environment.md) — June-2026 audit, resolved decisions, dev-environment plan.
- [`research/hosting-costs.md`](research/hosting-costs.md) — hosting/service cost matrix (planning reference).

## Conventions

- Active plans live in `docs/roadmaps/`; retired plans/reports move under `docs/_legacy/`.
- Durable docs must not hardcode a dated plan as current guidance (see `docs-standards.md`).
