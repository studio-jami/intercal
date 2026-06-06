# Resource & Cost Budget

How much of each free/credit allowance we have, what consumes it, and the cadences/throttles
that keep Intercal running "as much as we usefully can" while staying free until real scale.
Drift-prone — re-verify provider numbers at the dates noted (baseline: June 2026).

## Principle

Spend the **free and the already-paid-for** first; make the **finite dollar** thing (LLM
inference) the only real budget to manage; throttle by **cadence + batch size + dedup**, not by
crippling the product. Every limit below maps to an env-driven knob so we tune without code changes.

## Allowances (per service)

| Service | Free / credit allowance (June 2026) | What consumes it | Binding? |
| --- | --- | --- | --- |
| **GitHub Actions** | **Public repo → unlimited Linux minutes** (the repo is public). *Private fallback: 2,000 min/mo Free / 3,000 Pro.* | Pipeline batch jobs, CI | **No** (public) — but keep jobs short & concurrency low out of courtesy |
| **Neon** (Postgres+pgvector) | ~**100 CU-hours/mo** compute, **0.5 GB** storage/branch, autosuspend ~5 min idle, 10 branches | App queries + pipeline writes (CU-hrs accrue only while active) | **Yes** (CU-hours) |
| **Upstash Redis** | **500k commands/mo**, 256 MB | Queue + cache operations | **Yes** (command count) |
| **Cloudflare R2** | **10 GB** storage, **1M Class-A ops/mo** (writes/lists), **10M Class-B ops/mo** (reads), **$0 egress** | Raw document archival | Generous; writes are the cap |
| **Vercel** (Hobby) | ~**100 GB-hrs** function exec, ~100 GB transfer, build mins; non-commercial | App + REST API + MCP requests | Comfortable at pilot |
| **Cloud Run** (always-free) | **2M req/mo, 180k vCPU-sec, 360k GB-sec, 1 GB egress** then trial credits | On-demand/heavy pipeline jobs, MCP fallback | Comfortable; spills to credits |
| **Vertex AI** (yrka.io) | **GCP trial credits** (finite $; verify remaining in console) | **Primary LLM inference** | **Yes — the real $ budget** |
| **Gemini API** (postpay tier-1) | Tier-1 daily/RPM limits (verify in AI Studio) | **Fallback LLM inference** | Yes (daily) |
| **Embeddings** (local fastembed) | unlimited (CPU only, runs in the worker) | extraction/resolution embeddings | **No cost** — prefer always |

## Consumption plan (stay within, run usefully)

- **Ingestion is scheduled, not continuous.** Default cadence: a handful of sources, **hourly→daily**
  via GitHub Actions cron (free). Each run is short and idempotent (dedup by `content_hash`), so
  re-runs are cheap and Neon CU-hours only accrue during the burst.
- **Embeddings always local** (fastembed) → zero API spend; runs on free Actions/Cloud Run CPU.
- **LLM is the budget.** Default extraction/synthesis to **Vertex Gemini Flash** (cheap, trial
  credits); fall back to the **Gemini postpay key** when credits run low or for dev. Controls:
  only extract on **new/changed** documents; **batch** claims per document; **cap tokens/doc**;
  enforce a **daily request/token budget**; cache digests. Never re-extract unchanged docs.
- **Neon CU-hours:** keep scale-to-zero on; use short-lived pipeline connections (don't hold
  pools open in batch jobs); the app is bursty and autosuspends. ~100 CU-hrs ≈ plenty for a
  bursty pilot if nothing idles a connection open.
- **Upstash 500k/mo (~16k/day):** use Redis only where it earns it. For low-volume queueing,
  prefer the **Postgres `pgmq` adapter** to spare Upstash commands; set cache TTLs; avoid
  per-item Redis chatter.
- **R2:** one PUT per raw doc, batched; reads cached. 1M writes/mo covers heavy ingestion.

## Throttle knobs (env-driven; pipeline/app must honor)

```
INGEST_CRON=0 */6 * * *          # default cadence (6h); tighten/loosen freely
INGEST_MAX_DOCS_PER_RUN=200      # cap work per scheduled run
EXTRACT_ONLY_CHANGED=true        # never re-extract unchanged (content_hash) docs
LLM_DAILY_REQUEST_BUDGET=2000    # hard daily cap across providers
LLM_MAX_OUTPUT_TOKENS=2048       # per call
LLM_PRIMARY=vertex               # vertex → gemini fallback order
EMBEDDINGS_BATCH_SIZE=64         # local, free; batch for throughput
QUEUE_PROVIDER=redis             # switch to 'postgres' (pgmq) to spare Upstash commands
```

These are enforced in `services/shared` config plus the worker CLIs. The worker runtime builds LLMs
through the budgeted shared factory: one daily request budget is seeded from same-day
`provider_usage_events` and then shared across provider attempts, `LLM_PRIMARY=vertex` prefers Vertex
and falls back to Gemini on provider auth/quota/timeout failures, `LLM_MAX_OUTPUT_TOKENS` caps each LLM
call, and successful provider responses append real request/token measurements to
`provider_usage_events` when the observability migration is present. Unknown token counts remain
unavailable; they are not zero-filled.

## Monitoring (owned by Plan 04 observability)

- SQL/CLI first: `pnpm ops:health --section providers` reads
  `observability_provider_consumption`, backed by `provider_usage_events` plus the allowance rows
  initialized from this file.
- Per-provider consumption cards may read the same view later: Neon CU-hours/storage, Upstash
  commands/storage, R2 ops/storage/egress, Vertex/Gemini requests/tokens, GitHub Actions minutes,
  Vercel function GB-hours, and Cloud Run request/compute usage.
- Missing provider telemetry is reported as `unavailable`, not zero. Operators must import real
  provider measurements before treating a budget row as observed.
- Alert thresholds at ~70% of each binding allowance. The worker runtime reads
  `observability_provider_consumption` for Vertex/Gemini daily-request rows: `warning` providers are
  deprioritized behind fallback, and `exceeded` providers are excluded. It also seeds the local
  `LLM_DAILY_REQUEST_BUDGET` counter from today's real Vertex/Gemini request rows so reruns on the
  same UTC day do not reset the cap. If the view/table is not migrated or has no real usage events
  yet, the process-local `LLM_DAILY_REQUEST_BUDGET` remains the hard guard for that worker run.

## Scale triggers (when to spend)

| Signal | Action | Rough cost |
| --- | --- | --- |
| Neon CU-hours > ~80/mo or storage > 0.5 GB | Neon Launch plan | ~$5–19/mo |
| Upstash > 500k cmds/mo consistently | Upstash pay-as-you-go or self-host Redis | ~$0.20/100k or VPS |
| Vertex trial credits exhausted | Gemini postpay primary, or GCP billing | usage-based |
| Vercel non-commercial limits / go commercial | Vercel Pro (or move to Cloudflare) | ~$20/mo |
| R2 > 10 GB or > 1M writes/mo | R2 paid (still cheap, $0 egress) | ~$0.015/GB |

Everything above sits behind a port or a plan upgrade — **scaling is a config/plan change, never
a migration.**
