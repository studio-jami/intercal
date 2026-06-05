# Intercal Revisit: Roadmap Audit, Assumption Cleanup, and Dev-Environment Feasibility Report

Date: 2026-06-04
Status: Draft for review — decisions open (see §12)
Request: Revisit the project. Audit the roadmaps, remove ambiguity, align with latest official (June 2026) practices, and define a proper dev environment. Constraints: no-cost development/pilot phase (no cost until scale); no major migrations or refactors (always flexible, behind proper adapters); will become a standalone product on its own domain, initially on a free domain such as `intercal.vercel.app`. Follow james/dev rules and principles.
Source scope: Local `intercal.dev` docs tree; the project's own engineering standards; web verification of drift-prone provider facts (June 2026); two research subagents (roadmap audit + stack audit).
Owner: Revisit / orchestration agent

---

## 1. Executive Summary

Intercal is a **well-conceived project with a strong foundation report and a sound domain model** (a provenance-backed, bitemporal temporal-knowledge substrate for agents, served over MCP + REST). The core thesis, the system primitives (source → document → mention → claim → entity → relationship → fact version), and the provider-agnostic posture are all in good shape and worth keeping essentially as-is. The revisit is feasible and does not require rethinking the product.

However, three classes of problem must be resolved before any code is scaffolded:

1. **Repository contamination (highest priority).** `docs/engineering/` is polluted with documents from a *different* project — **"Zavi", a Tauri 2 desktop voice-host app** that drives an external "Hermes" agent brain. `DECISIONS.md`, `agents/goal.md`, `agents/orchestration-reliability.md`, and parts of the three `standards/` files are Zavi artifacts (they reference `C:\Users\james\projects\zavi\`, Tauri plugins, the Hermes gateway, and "a local-first desktop app with no database"). None of this applies to Intercal, which is a Postgres-backed web/API monorepo. Left in place, these are actively misleading source-of-truth documents.

2. **Internal ambiguity.** The roadmaps contain **broken path references** (they point at `docs/reports/…` and `docs/plans/…` and `docs/research/brainstorm.md` and `docs/engineering/planning-style.md`, none of which exist at those paths) and **~8 undecided technical forks** that span multiple plans (queue, scheduler, frontend framework, object storage, default embeddings, default LLM, contract source-of-truth, and lint/format). `README.md` also references an `AGENTS.md` and a `docs/README.md` that do not exist. The repo is not a git repository.

3. **Stale assumptions and one hard constraint conflict.** The plans are ~1 year old and name no versions; several choices need re-pinning to June 2026 reality. Most importantly, **the "free on `intercal.vercel.app`" assumption conflicts with Vercel's Terms**: the Hobby (free) plan is *restricted to non-commercial personal use only* — verified verbatim on the official Fair Use page (last updated 2026-02-27), where even *"asking for donations"* counts as commercial. A `*.vercel.app` URL is fine for a non-commercial demo, but the production/standalone-product surface cannot legally run on Hobby.

**Recommendation:** Keep the product thesis and domain model. Quarantine the Zavi docs, fix every broken reference, and **resolve the open forks with the June-2026 decision set in §11**. Scaffold a clean, adapter-first pnpm + uv monorepo. Critically, **decouple "zero cost" from "Vercel Hobby"**: the zero-cost pilot is genuinely achievable — Postgres+pgvector on Neon free, object storage on Cloudflare R2 free, queue on Upstash free, heavy Python workers on GitHub Actions (free for public OSS repos), local/free embeddings, and a free LLM default behind an adapter — but the *commercial* production deployment needs a commercial-friendly host (Vercel Pro or Cloudflare/Render-class), planned for "at scale," not day one.

The no-lock-in constraint is **genuinely satisfiable** because every load-bearing choice is an open standard: Postgres+pgvector, the S3 API, OpenAPI/JSON-Schema contracts, the MCP open protocol, and provider adapters for LLM/embeddings. That is the project's biggest architectural strength and should be preserved exactly.

---

## 2. Question Being Answered

Can Intercal be cleanly resumed in June 2026 such that:

- the roadmaps are internally consistent and free of ambiguity;
- every technology assumption matches current official guidance;
- a proper, reproducible dev environment exists;
- the whole development + pilot phase costs **$0** and incurs no vendor lock-in (everything behind adapters, no forced migration later);
- it can grow into a standalone product on its own domain?

And: what is the concrete, ordered next step to get there?

---

## 3. Source Scope And Method

**Local files read (in full):**
- `README.md`
- `docs/research/2026-05-21-intercal-foundation-report.md` (canonical source report)
- `docs/research/hosting-costs.md`
- `docs/roadmaps/2026-05-21-intercal-plan-01…06-*.md` (all six)
- `docs/engineering/DECISIONS.md`
- `docs/engineering/standards/{docs-standards,planning-style,report-style}.md`
- `docs/engineering/agents/{goal,orchestration-reliability}.md`
- `docs/user-notes/brainstorm.md` (empty)

**Repo state checks:** directory tree, `.agents/` (empty `.skills/`), `.changes/` (empty), `.github/` (empty), git status (**not a git repository**).

**External verification (June 2026):** stack audit across Node/pnpm/TypeScript/Biome, uv/Ruff/ty/Pydantic, Postgres 18/pgvector 0.8.2, free-tier managed Postgres (Neon, Supabase, Prisma Postgres), Vercel Hobby limits + Fluid Compute, Python-on-Vercel, free scheduled-worker options (GitHub Actions, Modal, Cloudflare, Render, Fly), Cloudflare R2, Upstash, Next.js 16/React 19, Tailwind v4/shadcn, contract tooling (TypeSpec/Zod 4/Pydantic), MCP spec 2025-11-25 + transports + auth, free/local embeddings, and free LLM tiers. The single highest-impact claim — **Vercel Hobby non-commercial restriction** — was independently confirmed against `https://vercel.com/docs/limits/fair-use-guidelines` (last_updated 2026-02-27).

**Not checked (out of scope / no access):** live provider accounts, credentials, dashboards, or quotas; the referenced `changelog` and `sherlock` reference codebases; the broader `C:\Users\james\dev\docs` knowledge base (separate org docs, not Intercal source-of-truth). Free-tier numeric limits are drift-prone and should be re-verified at account-setup time.

---

## 4. Current Project State

### 4.1 What exists and is good
- The repository is **docs-only**, pre-code — the ideal moment to correct foundations before anything is locked in.
- `docs/research/2026-05-21-intercal-foundation-report.md` is a **strong, coherent source report**: clear thesis, well-modeled primitives, explicit non-goals, sensible data model (~24 tables), a small/excellent V1 MCP+REST surface, and 10 well-reasoned open decisions. **Keep it as the canonical source.**
- The six roadmaps are individually well-structured (purpose, locked decisions, dependency-ordered workstreams, exit criteria) and conform to the project's own `planning-style.md`.
- The provider-agnostic, adapter-first intent is present throughout — exactly aligned with the no-lock-in constraint.

### 4.2 Problem A — "Zavi" contamination of `docs/engineering/`
These files belong to a different project and must not govern Intercal:

| File | Reality | Action |
| --- | --- | --- |
| `docs/engineering/DECISIONS.md` | 100% Zavi: D1–D17 about Hermes, Tauri 2, wake-word/STT/TTS, realtime S2S, OS keychain. References `zavi`, `github.com/jamie-yrka/zavi`. | **Remove from Intercal** (archive elsewhere). Intercal's decisions go in a fresh `docs/decisions/`. |
| `docs/engineering/agents/goal.md` | 100% Zavi orchestrator prompt; paths to `C:\Users\james\projects\zavi\…`; W1–W12 voice-host streams. | **Remove.** |
| `docs/engineering/agents/orchestration-reliability.md` | Generic-ish but written for the Zavi goal run. | **Remove or rewrite** if a generic orchestration guide is wanted. |
| `docs/engineering/standards/planning-style.md` | Mostly reusable, but Zavi-specific lines: "Zavi is a local-first desktop app with no database," `cargo`/Tauri verification, IPC contracts. | **Keep + de-Zavi:** replace desktop/Rust/Tauri assumptions with Intercal's Postgres/TS/Python verification ladder. |
| `docs/engineering/standards/docs-standards.md` | Reusable shape, but cites "Hermes gateway method tables," "Tauri plugin versions," "crate pins." | **Keep + de-Zavi.** |
| `docs/engineering/standards/report-style.md` | Generic and project-neutral. | **Keep as-is** (this report follows it). |

> Note: the Zavi `DECISIONS.md` is dated 2026-06-04 — newer than the Intercal docs — which strongly suggests these were copied in during unrelated work and were never meant to be Intercal's source of truth.

### 4.3 Problem B — Broken/inconsistent references
The roadmaps and README point at paths that do not exist as written:

| Reference in docs | Actual location | Fix |
| --- | --- | --- |
| `docs/reports/2026-05-21-intercal-foundation-report.md` (all 6 plans cite this as the source report) | `docs/research/2026-05-21-intercal-foundation-report.md` | Repoint plans to `docs/research/…`, **or** move the report to `docs/reports/` and standardize. |
| `docs/research/brainstorm.md` (plan 01 source) | `docs/user-notes/brainstorm.md` (and it is **empty**) | Repoint or delete the citation. |
| `docs/engineering/planning-style.md` (plan 01) | `docs/engineering/standards/planning-style.md` | Repoint. |
| `docs/plans/…` (foundation report §"Implementation Plan Set"; plan 01 repo guidance) | `docs/roadmaps/…` | Standardize on **`docs/roadmaps/`** (and `docs/_legacy/roadmaps/` for retirement). The report and plan 05 use `docs/plans/` / `docs/_legacy/plans/` inconsistently. |
| `AGENTS.md`, `docs/README.md` (referenced by `README.md`) | **Do not exist** | Create both (they are Workstream 2 deliverables anyway). |
| `engineeering/` (typo in foundation report's repo-shape block) | — | Fix to `engineering/`. |
| Foundation report repo-shape lists `bylaws/`, `membership/`, `admin/`, `communications/` doc dirs | — | These look like an org-template carryover; **drop** the ones that don't fit a knowledge-graph product. |

### 4.4 Problem C — Undecided forks (ambiguity to remove)
Named only abstractly across plans, never resolved. Each is resolved in §11:

1. **Queue/cache technology** ("queue abstraction," plans 02/04/05) — never instantiated.
2. **Scheduler** ("local scheduler," plan 02) — never named.
3. **Frontend framework** (`packages/dashboard`, plans 04/05/06) — never named.
4. **Object storage provider** ("object storage abstraction," plan 02) — never named.
5. **Default embeddings provider** (Vertex/Azure "optional," primary unstated).
6. **Default LLM provider** (Vertex/Azure/OpenAI-compatible options, default unstated).
7. **Contract source of truth** (OpenAPI for REST, "MCP schema snapshots," shared validators "implied Zod/Pydantic" but never pinned).
8. **Lint/format toolchain** (Ruff named for Python; TS side only says ESLint/Prettier "equivalent").

### 4.5 Other structural notes
- The foundation report and `hosting-costs.md` already model three deployment paths (local / low-cost VPS / managed) and insist on substitutable service contracts — **this is correct and should be kept**; it just needs concrete defaults and the Vercel-Hobby correction.
- `.changes/`, `.github/`, and `.agents/.skills/` exist but are empty — placeholders for changelog fragments, CI, and repo skills.

---

## 5. Official / External Findings (June 2026)

Condensed; each line is "current fact → implication for zero-cost + no-lock-in." Drift-prone items flagged ⚠️.

**A. TS / monorepo**
- **Node 24 (Active LTS)** is the target; Node 22 maintenance, Node 26 current (LTS Oct 2026). Pin via `.nvmrc`/`engines`.
- **pnpm 11.x**, first-class workspaces + **catalogs**. Plain pnpm workspaces is the right default for ~10 packages; add **Turborepo later** purely as an optional local cache/task-runner (keep Remote Cache off to avoid lock-in). Nx is overkill.
- **TypeScript 5.9** is the supported baseline; **TS 7 / "tsgo" (Go-native) is beta** (Apr 2026), ~10× faster, GA expected mid/late 2026 — adopt opportunistically for fast checks, don't make it the only checker yet. ⚠️
- **Biome v2.x** (type-aware, one Rust tool for lint+format) is the recommended greenfield default over ESLint+Prettier; keep ESLint only for a specific plugin if needed.

**B. Python**
- **uv** is the de-facto standard project/package manager. **Ruff** standard for lint+format.
- **Astral `ty` type checker is still beta** (0.0.x) — keep **Pyright (or mypy)** as the gating checker; `ty` advisory only. ⚠️
- **Pydantic v2** stable; strong contract candidate.

**C. Database / vectors (constraint-critical, all open-standard → portable)**
- **PostgreSQL 18**; **pgvector 0.8.2** with HNSW, **iterative index scans**, **halfvec** (2-byte floats, halves index size at ~1536 dims, indexes up to 4,000 dims). Use **HNSW + halfvec**.
- Free managed Postgres+pgvector: ⚠️ all numbers drift —
  - **Neon free:** 0.5 GB/project, **100 CU-hrs/mo**, max 2 CU, 10 branches, no card; **auto scale-to-zero (~5 min)** and **auto-resume**. **Best fit.**
  - **Supabase free:** 500 MB DB, 2 active projects; **pauses after 7 days of no queries** (manual unpause). Viable but the pause is a real risk for an intermittent pilot — needs a keep-alive.
  - **Prisma Postgres / Vercel-Postgres (= Neon) / Xata / Nile** are secondary; Tigris is object storage, not Postgres.
  - Because it's all standard Postgres+pgvector behind a DB adapter, migration between any of these is `pg_dump`/`pg_restore` — **no lock-in.**
- **pgvectorscale** (DiskANN) is **not installable on free tiers** → keep it out of the pilot; revisit at million-vector scale behind the vector adapter.

**D. Hosting (zero-cost)**
- **Vercel Hobby is non-commercial only** (verified 2026-02-27; donations count as commercial). Limits incl. 100 GB-Hrs function execution, 60s max function duration. **Commercial/production needs Pro (~$20/mo) or another host.** ⚠️ **constraint conflict, see §10.**
- **Python on Vercel** is beta (FastAPI/Flask), 500 MB bundle, plan-capped duration → fine for *light* API endpoints, **not** for heavy/long ingestion/extraction/embedding workers.
- **Free heavy/scheduled Python workers:** **GitHub Actions scheduled workflows** are the best zero-cost fit — **unlimited minutes on public OSS repos** (5-min cron granularity, UTC, auto-disables after 60 days inactivity → add a keep-alive). **Modal** ($30/mo free credits, Python-native, GPU) is the spillover. Cloudflare Python Workers (Pyodide) only for *light* tasks. **Render free** spins down after 15 min idle and its free Postgres expires at 90 days (don't use as canonical store). **Fly.io has no free tier for new users** — remove from "free" assumptions. ⚠️
- **Cloudflare R2 free:** 10 GB storage, 1M Class-A + 10M Class-B ops/mo, **zero egress**, S3-compatible → ideal object-storage default behind an S3 adapter.
- **Upstash Redis free:** 256 MB, **500k commands/mo** (changed Mar 2025), up to 10 DBs. Fine for pilot; keep behind a queue/cache adapter (swap to self-hosted Redis or Postgres-based `pgmq` if limits bite). ⚠️

**E. App / frontend**
- **Next.js 16** (App Router default, Turbopack default, React Compiler stable; stable Adapter API aids portability) + **React 19.2**. **Tailwind v4** (CSS-first) + **shadcn/ui** (components copied into repo → you own the code, no dep lock-in). Graph viz via MIT libs (Cytoscape/Sigma/react-force-graph).

**F. Contracts (TS↔Python parity)**
- Keep the wire artifact **format-neutral: JSON Schema / OpenAPI**. Two sane single-source patterns:
  - **TypeSpec → OpenAPI → generate TS types + Pydantic models** (best for a public-API product; strongest single source).
  - **Zod 4-first** (`z.toJSONSchema()` is now native/stable) → export JSON Schema → generate Pydantic. Lighter, TS-centric.
  - Avoid making Zod *or* Pydantic the sole source without exporting a neutral schema (that's the drift risk).

**G. MCP (agent-facing core)**
- Current spec **2025-11-25** (a 2026-07-28 RC in progress ⚠️). Transports: **stdio + Streamable HTTP**; **HTTP+SSE is deprecated** — new servers use Streamable HTTP. Auth: **OAuth 2.1**, server as resource server. Official **TS SDK `@modelcontextprotocol/sdk` v1.29.x** (SDK v2 ~July 2026 ⚠️). Build on the official SDK over Streamable HTTP; OAuth for the public deployment.

**H. AI (zero-cost-capable, adapter-based)**
- **Embeddings:** local **fastembed/ONNX** models (`bge-small` 384-dim, `bge-base`/Nomic v2 768-dim) — **zero-cost default**, runs in Actions/Modal, pgvector-friendly with halfvec. ⚠️ embedding model = vector space: **version embeddings + store model name per vector** (the adapter alone doesn't protect against a model swap).
- **LLM extraction adapter with a free default is viable:** default to a free tier (**Gemini Flash** ~1,500 req/day, or **Groq** free) with **Claude 4.x / OpenAI** as paid quality fallbacks; Anthropic's "Claude for Open Source" program may grant Intercal free Claude as an OSS project. ⚠️ free LLM tiers are volatile — the multi-provider adapter is the mitigation.

---

## 6. Industry-Standard Shape (the north star)

The conventional June-2026 shape for an **open-source, agent-facing, provider-agnostic data product** that must run free first and scale later:

- **pnpm workspaces** (+ catalogs) TS monorepo; **uv** Python services; Node 24 / TS 5.9; **Biome** (TS) + **Ruff/Pyright** (Py).
- **Postgres 18 + pgvector** as the single canonical store; **SQL-first migrations**; thin typed query helpers (Drizzle or Kysely) that never hide schema ownership.
- **Contracts spec-first** (TypeSpec/OpenAPI or Zod-4 → JSON Schema) generating both runtimes; snapshot + drift checks.
- **MCP server (official TS SDK, Streamable HTTP, OAuth 2.1)** and a **REST API** over one shared query-service layer; a typed **SDK**; a **Next.js 16 + Tailwind v4 + shadcn** read-only dashboard.
- **Adapters for every external dependency:** DB, vector index, object storage (S3 API), queue/cache, embeddings, LLM, scheduler — provider logic never crosses the port boundary.
- **Zero-cost pilot topology:** Neon (DB) · Cloudflare R2 (objects) · Upstash (queue/cache) · GitHub Actions/Modal (heavy Python workers) · local/free embeddings · free-tier LLM default · a free-host front door — with the same service contracts pointing at paid/managed equivalents at scale.
- **Local parity via `docker compose`** (Postgres+pgvector, Redis/Valkey, MinIO) so dev == pilot == prod by contract, not by provider.

Intercal's foundation report already matches this shape; the gap is concrete defaults + the hosting correction.

---

## 7. Implementation Options (dev environment + hosting posture)

### Option 1 — Pure free-tier "managed-mosaic" (recommended for pilot)
Local `docker compose` for dev; pilot on **Neon + R2 + Upstash + GitHub Actions workers + free-tier LLM/local embeddings**, front door on a commercial-friendly free/cheap host. Everything behind adapters.
- *Fits:* the no-cost + no-lock-in constraints exactly, while the product is pre-revenue.
- *Tradeoffs:* several providers to wire (mitigated by adapters + compose parity); free-tier limits need keep-alives (Neon auto-resumes; Supabase/GH-Actions need pings).
- *Cost:* **$0** + optional ~$10–20/yr domain. *Reversibility:* high — all open standards.

### Option 2 — Single low-cost VPS (one box)
Hetzner/DO/Vultr droplet running Postgres+pgvector, Redis/Valkey, MinIO, API/MCP, and a systemd-scheduled Python worker; Cloudflare DNS in front.
- *Fits:* maximum control, fewest moving SaaS parts, no per-provider free-tier quirks, trivially commercial-legal.
- *Tradeoffs:* **not $0** (~$4–6/mo), and you own backups/uptime/patching.
- *Cost:* ~$5–7/mo. *Reversibility:* high (it's just Postgres + S3 API + Redis).

### Option 3 — Vercel-centric
Dashboard + light API on Vercel, Postgres via the Vercel↔Neon integration.
- *Fits:* best frontend DX.
- *Tradeoffs:* **Hobby is non-commercial only → needs Pro ($20/mo) for the real product**; Vercel can't host the heavy Python pipeline (use Actions/Modal anyway). Risks coupling billing/identity to one vendor.
- *Cost:* $0 only while non-commercial; $20/mo+ at product stage. *Reversibility:* medium (keep Next's Adapter API + your own API layer to stay portable).

**Recommendation:** **Option 1 for the zero-cost pilot**, with Option 2 documented as the "one-box" alternative and the deliberate fallback the moment a single bill is acceptable; treat Vercel as *a* deployable front-door target (great for the demo on `intercal.vercel.app`), not the platform the architecture depends on.

---

## 8. Technical Implications

- **Architecture:** unchanged in spirit — reinforces the existing adapter posture. Adds explicit ports for **scheduler** and **queue** (currently only abstract) and an explicit **S3-compatible storage** port.
- **Data model:** unchanged. One addition: **embeddings rows must carry model name + dimension + version** (vector-space safety). pgvector **halfvec** is a storage decision, not a schema-shape change.
- **Contracts:** pick one spec-first source (§11 D9); generate TS + Python; add snapshot + drift gates. Removes the "implied Zod/Pydantic" ambiguity.
- **MCP/API:** target MCP **Streamable HTTP + OAuth 2.1** on the official TS SDK; keep stdio for local. Pin the SDK and re-check after the July-2026 spec RC.
- **Workers:** the heavy Python pipeline runs as **CLI-invocable functions** so the same entrypoints run under GitHub Actions, Modal, or a VPS cron with no rewrite — this is what makes the scheduler choice non-locking.
- **Security:** unchanged requirements (hashed scoped API keys, rate limits, SSRF protection for submitted URLs, source-policy/license metadata, audit events). MCP OAuth is the new concrete auth surface.
- **Verification:** the foundation report's gate ladder stays; replace the Zavi `cargo`/Tauri verification language in `planning-style.md` with the TS/Python/DB/contract ladder already in plan 01.

---

## 9. Project Implications

- **Scope:** no product re-scope. The work is hygiene + decisions + scaffold, then resume plan 01.
- **Sequencing:** a small **Plan 00 "Repository Reset & Decisions"** should precede the existing plan 01 — it owns: git init, Zavi quarantine, reference repair, decision records, `AGENTS.md` + `docs/README.md`, and the resolved defaults. Plans 02–06 are otherwise sound and only need their references + named-provider blanks filled from the decision set.
- **Docs:** standardize on `docs/roadmaps/` (active) + `docs/_legacy/roadmaps/` (retired); create `docs/decisions/` for Intercal (not the Zavi DECISIONS.md); create the missing top-level docs.
- **Ownership surfaces:** add `scripts/` lanes for workers/cron + contract generation; `db/` SQL-first migrations remain the schema owner.
- **User-facing claims:** until a commercial host is in place, the public surface must be a **non-commercial demo** (no payments, ads, affiliate links, or donations) to stay within Vercel Hobby ToS — or move the front door off Hobby.
- **Maintainability:** pinning versions now (Node 24, TS 5.9, MCP SDK, pgvector 0.8.2) + scheduling a July-2026 re-check (TS 7, MCP spec RC/SDK v2) avoids silent drift.

---

## 10. Risks And Constraints

1. **Vercel Hobby ≠ commercial (highest impact, confirmed).** The "standalone product on its own domain" goal is commercial; donations included. *Mitigation:* keep the public pilot strictly non-commercial **or** host the product front-door on Pro/another commercial-friendly host. Decide before publishing anything monetizable. (§12 Q1)
2. **Free-tier limit churn (⚠️).** Neon CU-hrs and Supabase pause window both changed within 12 months; Fly removed its free tier; Upstash repriced in 2025. *Mitigation:* re-verify all free-tier numbers at account setup; keep strict adapters so any forced move is a config + `pg_dump` away.
3. **Mid-2026 version cliffs (⚠️).** TS 7/tsgo GA, MCP spec 2026-07-28 RC + SDK v2 all land soon after any pin. *Mitigation:* pin now, schedule a re-check.
4. **Embedding vector-space lock-in.** Swapping embedding models silently breaks similarity. *Mitigation:* version embeddings + store model identifier per vector; re-embed on change.
5. **Volatile free LLM tiers.** *Mitigation:* multi-provider LLM adapter with a free default and paid fallbacks; never hard-depend on one free tier.
6. **Supabase/GitHub-Actions idle-pausing.** Supabase pauses after 7 days; Actions disable after 60 days inactivity. *Mitigation:* keep-alive pings / scheduled no-op; or prefer Neon (auto-resume).
7. **`ty` (Python) and tsgo are beta.** *Mitigation:* keep Pyright + TS 5.9 `tsc` authoritative for gating.
8. **Zavi-doc confusion if left in place.** *Mitigation:* quarantine immediately (§12 Q3).
9. **Source license/redistribution policy (carried from foundation report).** Still a real constraint for ingestion. *Mitigation:* per-source policy metadata before broad ingestion (already planned).

**Assumptions needing confirmation:** commercial intent + timing (Q1); whether the OSS repo will be **public** (unlocks free GitHub Actions compute and the Anthropic OSS program — material to the zero-cost plan); whether to delete vs archive Zavi docs (Q3); contract approach (Q4).

---

## 11. Recommended Direction — Resolved Decision Set (June 2026)

Adopt these as Intercal decision records, replacing every "TBD/abstract" fork. All are reversible behind adapters.

| # | Fork | Decision | Why | Reversibility |
| --- | --- | --- | --- | --- |
| D1 | Node / TS | **Node 24 LTS, TypeScript 5.9** (pin; eval tsgo for fast checks) | current LTS + supported baseline | re-pin July 2026 |
| D2 | Monorepo | **pnpm 11 workspaces + catalogs**; Turborepo optional later, local cache only | right-sized; no Remote-Cache lock-in | add Turbo anytime |
| D3 | TS lint/format | **Biome v2** (ESLint only per-plugin if needed) | one fast Rust tool, greenfield | standard config |
| D4 | Python | **uv + Ruff + Pyright** (ty advisory) | de-facto standard; stable gating | trivial |
| D5 | DB + vectors | **Postgres 18 + pgvector 0.8.2 (HNSW + halfvec)**; **SQL-first migrations**; **Drizzle/Kysely** for typed TS reads, direct SQL/SQLAlchemy Core for Python writes | open standard = portable canonical store | `pg_dump` |
| D6 | Pilot DB host | **Neon free** (Supabase as documented alt with keep-alive) | auto-resume, branching, no card | adapter + dump |
| D7 | Object storage | **Cloudflare R2 free** behind an **S3-API adapter**; **MinIO** locally | zero egress, S3-compatible | swap endpoint |
| D8 | Queue/cache | **Upstash Redis free** behind a **queue/cache adapter**; **Redis/Valkey** locally; `pgmq` noted as Postgres-native fallback | free, swappable | adapter |
| D9 | Contracts | **Spec-first**: **TypeSpec → OpenAPI/JSON-Schema → generate TS + Pydantic** (Zod-4-first acceptable if team prefers TS-authoring) — confirm in Q4 | neutral wire artifact, no TS/Py drift | regenerate |
| D10 | MCP | **Official `@modelcontextprotocol/sdk`, Streamable HTTP, OAuth 2.1**; stdio for local; spec **2025-11-25** | current standard; SSE deprecated | open protocol |
| D11 | Scheduler / heavy workers | **GitHub Actions scheduled workflows** (public repo) as zero-cost default; **Modal** spillover; **VPS cron** as one-box alt — all via **CLI-invocable worker entrypoints** behind a scheduler port | free for OSS; no rewrite to move | port |
| D12 | Embeddings | **Local fastembed/ONNX (`bge`/Nomic, halfvec)** default behind an **embeddings adapter**; hosted optional; **store model+dim+version per vector** | zero-cost, pgvector-fit | re-embed |
| D13 | LLM extraction/synthesis | **Provider adapter** with a **free default (Gemini Flash / Groq)** + Claude 4.x/OpenAI paid fallbacks; explore Anthropic OSS program | zero-cost default, no lock-in | adapter |
| D14 | Frontend | **Next.js 16 (App Router) + React 19 + Tailwind v4 + shadcn/ui** for `packages/dashboard` (read-only, plan 06) | conventional, portable, you own components | Next Adapter API |
| D15 | Pilot hosting posture | **Free managed-mosaic (Option 1)**; **VPS one-box (Option 2)** documented as the first paid step; Vercel = a front-door target, **non-commercial only on Hobby** | satisfies $0 + no-lock-in; respects ToS | service contracts |
| D16 | Docs convention | Active plans in **`docs/roadmaps/`**, retire to **`docs/_legacy/roadmaps/`**; Intercal decisions in **`docs/decisions/`** | one consistent convention | — |

### Dev-environment setup plan (concrete, ordered) — proposed "Plan 00"
1. `git init`; add `.gitignore`, `.nvmrc` (Node 24), `.editorconfig`; (decide public vs private — Q2).
2. **Quarantine Zavi docs** (Q3): move `DECISIONS.md`, `agents/goal.md`, `agents/orchestration-reliability.md` out of Intercal; de-Zavi `planning-style.md` + `docs-standards.md`; keep `report-style.md`.
3. **Repair references** per §4.3; fix `engineeering/` typo; prune org-template doc dirs; standardize on `docs/roadmaps/`.
4. Create **`AGENTS.md`** (succinct, enforceable) + **`docs/README.md`** (docs index) + **`docs/decisions/`** with D1–D16 as records.
5. Scaffold the monorepo: root `package.json`, `pnpm-workspace.yaml` (+ catalog), `pyproject.toml` + `uv.lock`, `docker/compose.yaml` (Postgres+pgvector, Redis/Valkey, MinIO), `packages/{api,mcp-server,sdk,shared,dashboard}`, `services/{ingest,extract,resolve,synthesize}`, `db/{migrations,seeds}`, `scripts/{verify,dev,workers}`.
6. Wire the **verification ladder** (Biome, Ruff, Pyright, contract drift, migration clean/seeded) as `pnpm verify`; add a minimal CI workflow.
7. Repoint plans 01–06 at the corrected paths and fill the named-provider blanks from D1–D16. Re-pin plan 01 as the active foundation plan.

This sequence respects james/dev principles (read owners first → report → decision → roadmap → implement → verify) and the project's own `report-style.md`/`planning-style.md`.

---

## 12. Decision Points

### Q1 — Commercial intent & front-door hosting
Options: **A.** Keep the public pilot strictly non-commercial (no payments/ads/affiliate/donations) and use `intercal.vercel.app` on Vercel Hobby for the demo. **B.** Plan the product front-door on a commercial-friendly host now (Vercel Pro ~$20/mo, or Cloudflare/Render-class).
Tradeoffs: A = truly $0 but ToS-bound to non-commercial and no donations; B = ToS-clean for a real product but breaks the "no cost until scale" rule.
**Recommendation:** **A for the pilot, B at the first sign of monetization/donations.** Keep the front-door behind a host-agnostic API/SDK so the move is a deploy target, not a refactor.
Implication if different: choosing B now means accepting the first recurring bill earlier than "at scale."

### Q2 — Repository visibility
Options: **A.** Public OSS repo. **B.** Private (for now).
Tradeoffs: Public **unlocks free unlimited GitHub Actions compute** (the zero-cost heavy-worker plan) and the Anthropic "Claude for Open Source" program; Private costs Actions minutes and forfeits the OSS LLM grant.
**Recommendation:** **Public**, given the project is "oss/intercal.dev" and the zero-cost worker plan depends on it. If private is required short-term, budget Actions minutes or use Modal.
Implication if different: the scheduler/worker default (D11) and the free-LLM story (D13) get more expensive.

### Q3 — Zavi documents
Options: **A.** Delete from Intercal. **B.** Move to an archive outside the repo (e.g., the zavi project). **C.** Keep but clearly mark non-canonical.
**Recommendation:** **B** (preserve them where they belong — they're a real, newer Zavi decision log) and keep only de-Zavi'd, reusable standards in Intercal.
Implication if different: C risks future agents treating Tauri/Hermes decisions as Intercal's source of truth.

### Q4 — Contract source of truth
Options: **A.** TypeSpec → OpenAPI → generate TS + Pydantic. **B.** Zod-4-first → JSON Schema → generate Pydantic.
Tradeoffs: A = strongest single source for a public-API product, slightly more upfront; B = lighter, TS-centric authoring.
**Recommendation:** **A** for a public API/SDK product; **B** acceptable if you want to author primarily in TypeScript.
Implication if different: B keeps TS as the de-facto authority and treats Python as generated — fine as long as the neutral JSON Schema is always exported (never Zod-only).

### Q5 — Scope of this revisit's *execution*
Options: **A.** Report only (this document) — you review decisions first. **B.** Report + execute the non-destructive parts of Plan 00 now (git init, reference repair, scaffold, missing docs) and leave Zavi-doc moves + provider account setup for your confirmation.
**Recommendation:** **A → then B** once Q1–Q4 are answered, so no decision is baked in prematurely.

---

## 13. Decision Questions For Discussion

1. **Commercial/hosting:** Non-commercial pilot on Vercel Hobby now (truly $0), or stand up a commercial-friendly front-door (≈$20/mo) from the start? *(Rec: non-commercial pilot now, switch at monetization.)*
2. **Repo visibility:** Make `intercal.dev` a **public** OSS repo (unlocks free CI compute + OSS LLM credits)? *(Rec: yes.)*
3. **Zavi docs:** OK to **move** the Zavi `DECISIONS.md`/`goal.md`/orchestration docs out of Intercal and keep only de-Zavi'd standards? *(Rec: yes.)*
4. **Contracts:** **TypeSpec→OpenAPI** (spec-first) or **Zod-4-first**? *(Rec: TypeSpec for a public API.)*
5. **Execution scope:** Want me to proceed to scaffold + repair (Plan 00) after you answer 1–4, or keep this report-only for now? *(Rec: report first, then execute.)*

---

## 14. Next Step If Accepted

1. Record decisions D1–D16 (§11) as `docs/decisions/*.md` once Q1–Q4 are settled.
2. Author **Plan 00 — Repository Reset & Decisions** in `docs/roadmaps/` (git init, Zavi quarantine, reference repair, missing docs, scaffold, verification ladder).
3. Execute Plan 00's non-destructive steps; perform Zavi-doc moves per Q3.
4. Repoint and lightly revise plans 01–06 to the corrected paths + named providers; re-activate plan 01 as the foundation build.
5. Schedule a **July–August 2026 re-verification** of drift-prone pins (TS 7/tsgo GA, MCP spec 2026-07-28 RC + SDK v2, Neon/Supabase/Upstash free-tier limits).

I can proceed to step 2–3 on request.

---

## 15. Sources

**Local:** `README.md`; `docs/research/2026-05-21-intercal-foundation-report.md`; `docs/research/hosting-costs.md`; `docs/roadmaps/2026-05-21-intercal-plan-01…06-*.md`; `docs/engineering/DECISIONS.md`; `docs/engineering/standards/{docs-standards,planning-style,report-style}.md`; `docs/engineering/agents/{goal,orchestration-reliability}.md`; `docs/user-notes/brainstorm.md`.

**External (official, June 2026; drift-prone items dated):**
- Node.js releases: https://nodejs.org/en/about/previous-releases
- pnpm 11 / workspaces: https://pnpm.io/workspaces · https://pnpm.io/blog/releases/11.3
- TypeScript 7 beta: https://devblogs.microsoft.com/typescript/announcing-typescript-7-0-beta/ · TS 5.9: https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-9.html
- Biome: https://biomejs.dev
- uv: https://docs.astral.sh/uv/ · Ruff: https://docs.astral.sh/ruff/ · ty (beta): https://docs.astral.sh/ty/
- Pydantic v2: https://docs.pydantic.dev/latest/changelog/
- pgvector 0.8.x: https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md · https://www.postgresql.org/about/news/pgvector-080-released-2952/
- Neon plans: https://neon.com/docs/introduction/plans · https://neon.com/pricing
- Supabase pricing: https://supabase.com/pricing
- Prisma Postgres: https://www.prisma.io/pricing
- pgvectorscale: https://github.com/timescale/pgvectorscale
- **Vercel Hobby non-commercial (verified 2026-02-27):** https://vercel.com/docs/limits/fair-use-guidelines · Hobby plan: https://vercel.com/docs/plans/hobby · Function limits: https://vercel.com/docs/functions/limitations · Python runtime: https://vercel.com/docs/functions/runtimes/python
- GitHub Actions limits/billing: https://docs.github.com/en/actions/reference/limits · https://docs.github.com/en/actions/concepts/billing-and-usage
- Modal pricing: https://modal.com/pricing · Render free: https://render.com/docs/free · Fly pricing: https://fly.io/docs/about/pricing/
- Cloudflare R2 pricing: https://developers.cloudflare.com/r2/pricing/
- Upstash pricing: https://upstash.com/docs/redis/overall/pricing · https://upstash.com/blog/redis-new-pricing
- Next.js 16: https://nextjs.org/blog/next-16 · Tailwind v4 + shadcn: https://ui.shadcn.com/docs/tailwind-v4
- Contracts: https://zod.dev/json-schema · https://typespec.io
- MCP spec 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25 · transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports · TS SDK: https://github.com/modelcontextprotocol/typescript-sdk
- Embeddings: https://github.com/qdrant/fastembed
