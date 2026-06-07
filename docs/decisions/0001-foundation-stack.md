# 0001 — Foundation Stack & Adapter Baseline (D1–D16)

Status: **Accepted** — 2026-06-04
Source: `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md` (verified against official June-2026 sources)
Supersedes: the abstract/undecided forks left open across the 2026-05-21 roadmaps and the foundation report's "Open Decisions".
Refined by: `0002-final-hosting-topology.md` and `0003-public-launch-provider-posture.md`.

These were decided together as the foundation baseline. Each is reversible behind an adapter
or a version pin. Re-verify drift-prone items (marked ⚠️) at the scheduled July–Aug 2026 check.

| # | Decision | Why | If reversed |
| --- | --- | --- | --- |
| D1 | **Node 24 LTS · TypeScript 5.9** (eval `tsgo`/TS 7 for fast checks; keep `tsc` authoritative) ⚠️ | current Active LTS + supported baseline | re-pin; same language semantics |
| D2 | **pnpm 10/11 workspaces + catalog**; Turborepo optional later as local cache only | right-sized for ~10 packages; no Remote-Cache lock-in | add Turbo anytime; no rewrite |
| D3 | **Biome v2** for TS lint+format (ESLint only per-plugin if ever needed) | one fast tool, greenfield | standard config; swap freely |
| D4 | **uv + Ruff + Pyright** for Python (Astral `ty` advisory until 1.0) ⚠️ | de-facto standard; stable gating | trivial |
| D5 | **Postgres 18 + pgvector 0.8.x (HNSW + halfvec)**; **SQL-first migrations**; **Kysely** typed reads (TS), direct SQL / SQLAlchemy-Core writes (Py) | DB is the product core; open standard = portable; ORM must not hide schema | `pg_dump`/`pg_restore` |
| D6 | Pilot DB host: **Neon free** (Supabase documented alt + keep-alive) ⚠️ | auto-resume, branching, no card | adapter + dump |
| D7 | Object storage: **Cloudflare R2 free** behind an **S3-API adapter**; **MinIO** locally ⚠️ | zero egress, S3-compatible | swap endpoint only |
| D8 | Queue/cache: **Upstash Redis free** behind a **queue/cache adapter**; **Valkey** locally; `pgmq` Postgres fallback ⚠️ | free, swappable | adapter |
| D9 | Contracts: **TypeSpec → OpenAPI 3.1 + JSON Schema → generate TS types + Pydantic**; MCP tool input schemas and REST validation consume the same JSON Schema | one neutral wire artifact, zero TS/Python drift | regenerate from spec |
| D10 | MCP: **official `@modelcontextprotocol/sdk`, Streamable HTTP transport, OAuth 2.1** resource-server auth; stdio for local; spec **2025-11-25** ⚠️ | current standard; HTTP+SSE deprecated | open protocol |
| D11 | Scheduler / heavy workers: **GitHub Actions scheduled workflows** (public repo, zero-cost) default; **Modal** spillover; VPS cron alt — all via **CLI-invocable worker entrypoints** behind a scheduler port ⚠️ | free for OSS; no rewrite to move host | port |
| D12 | Embeddings: **local fastembed/ONNX (bge-small, 384-dim, halfvec)** default behind an **embeddings adapter**; hosted optional; **store model + dim + version per vector** | zero-cost, pgvector-fit; vector space is model-bound | re-embed on model change |
| D13 | LLM extraction/synthesis: **provider adapter** with a **free default (Gemini Flash / Groq)** + Claude 4.x / OpenAI paid fallbacks ⚠️ | zero-cost default, no lock-in | adapter |
| D14 | Frontend: **Next.js 16 (App Router) + React 19 + Tailwind v4 + shadcn/ui**, read-only dashboard | conventional, portable; shadcn components are owned in-repo | Next Adapter API keeps host portable |
| D15 | Hosting posture: **service-contract portable** — free pilot mosaic (Neon · R2 · Upstash · Actions/Modal · local embeddings · free LLM) with a front door that can move after host-specific proof. The app depends on **service contracts, not a host**, but the current public front door is the Vercel/Next.js mount proven in `0003`. | satisfies zero-cost + no-lock-in; Vercel Hobby is non-commercial only, so monetization/donation surfaces stay feature-flagged off until a commercial-friendly posture is explicit | prove a new front-door host, then move traffic; adapter-backed dependencies remain config/port changes |
| D16 | Docs: active plans in `docs/roadmaps/`, retire to `docs/_legacy/roadmaps/`; decisions in `docs/decisions/`; one consistent convention | removes the `docs/plans` vs `docs/roadmaps` and `docs/reports` vs `docs/research` drift | — |

## Notes

- **Portable by contract, proven by host.** The REST API is a **Hono** app factory and MCP uses a
  standard Streamable HTTP transport; the DB/storage/queue/embeddings/LLM/scheduler are all behind
  ports; contracts are a neutral spec. The current public launch still runs through the proven
  Vercel/Next.js front door. Any Cloudflare Workers/Pages or other compute move must prove mount,
  runtime, routing, and trusted-header behavior before production traffic moves there.
- **Commercial/Vercel-Hobby note (D15).** Intercal is open source and non-commercial during
  the pilot. Donations or any monetization are a feature-flagged surface, hidden until a
  domain + commercial-friendly host are in place — this is a flag flip, never a re-architecture.
- **Vector-space safety (D12).** Changing the embedding model changes the vector space.
  Embeddings rows carry `model` + `dim`; a different-dimension model needs a new column/table
  and a re-embed. The adapter alone does not protect against this.
