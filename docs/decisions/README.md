# Decision Records

Durable architectural decisions for Intercal. Each record captures **what** was decided,
**why**, and **what changes if reversed**, so the reasoning survives handoff. The live repo
and active roadmap remain the source of truth; these records explain the reasoning, not the
implementation.

## Convention

- One numbered file per decision or per cohesive decision set: `NNNN-short-slug.md`.
- A record is **Accepted**, **Superseded by NNNN**, or **Proposed**.
- Promote a decision here once accepted; do not leave forks implicit in prose.
- When a source-truth fact changes, supersede the record with a new one rather than editing
  history.

## Index

- [`0001-foundation-stack.md`](0001-foundation-stack.md) — D1–D16, the June-2026 foundation
  stack and adapter baseline (Node/TS, pnpm, Biome, uv/Ruff/Pyright, Postgres+pgvector,
  Neon, R2, Upstash, TypeSpec contracts, MCP, scheduler/workers, embeddings, LLM, Next.js,
  hosting posture, docs convention).
