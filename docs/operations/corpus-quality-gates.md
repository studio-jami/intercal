# Corpus Quality Gates

Workstream 4 quality gates prove that Intercal's AI-history coverage claims are backed by
provenance-bearing rows and the shared query layer. They do not create public claims by themselves.
Use them after historical backfill runs and before exposing corpus coverage in UI, docs, marketing,
or API examples.

## Gate Modes

Run from the repo root with a Neon branch or other migrated Postgres database:

```powershell
$env:DATABASE_URL = "<neon branch url>"
pnpm --filter @intercal/core build
node scripts/dev/verify-corpus-quality-gates.mjs seeded-proof
node scripts/dev/verify-corpus-quality-gates.mjs live-first-proof
node scripts/dev/verify-corpus-quality-gates.mjs live-full
```

- `seeded-proof` inserts rollback-only source documents, claims, evidence links, fact versions,
  contradictions, and review records inside a serializable transaction. It exercises
  `get_entity`, `get_freshness`, `get_delta`, `verify_claim`, `search_evidence`, and the corpus
  gate report, then rolls the transaction back. This is the reproducible proof path when live
  backfill has not yet populated GPT-era AI-history data.
- `live-first-proof` evaluates the first GPT/Claude/Gemini/Llama/MCP proof gates against the
  existing corpus and then exercises the same query proof set as seeded mode. Use this after a
  bounded backfill proof run.
- `live-full` evaluates the broad AI-history taxonomy gates against the existing corpus. This should
  fail until source rows and backfill evidence cover every required source class, topic cluster,
  date range, entity, citation-depth, contradiction, and review-needed threshold.

The script never prints `DATABASE_URL`. Seeded mode writes only rollback-scoped probe rows and checks
that no probe source rows remain afterward.

## Metrics

`@intercal/core` owns the gate query in `queryCorpusQualityReport` so REST, MCP, SDK, and dashboard
consumers can rely on one read-side interpretation later. The report measures:

- source-class document coverage from `sources.metadata.source_class`;
- topic-cluster claim coverage from `claims.metadata.topic_cluster`;
- date-range document coverage from `source_documents.published_at`;
- entity coverage for GPT, Claude, Gemini, Llama, and MCP from active claims plus canonical
  `claim_evidence`;
- corpus citation depth and unsourced-claim rate;
- contradiction state from `claim_contradictions` and `claims.contradiction_status`;
- review-needed rate from unresolved `review_records` for claim, freshness, and coverage targets.

Public coverage language must stay no broader than the last passing live gate. A passing
`seeded-proof` run proves the gate and query machinery only; it does not prove production corpus
coverage.

## First-Proof Query Set

The seeded proof and live first-proof gate are aligned with the taxonomy query set:

- `get_entity("ChatGPT", at_date="2023-03-01")`
- `get_entity("Claude", at_date="2024-03-01")`
- `get_entity("Gemini", at_date="2024-02-15")`
- `get_entity("Llama", at_date="2024-04-18")`
- `get_freshness("MCP protocol")`
- `get_delta("frontier LLMs", since_date="2023-03-01", token_budget=300)`
- `verify_claim("GPT-4 Turbo supports a 128k context window", as_of_date="2024-04-01")`
- `verify_claim("GPT-4 Turbo supports a 1M context window", as_of_date="2024-04-01")`
- `search_evidence("MCP protocol", date range 2024-01-01 through 2026-06-06)`

The verifier requires citations on public facts and checks point-in-time behavior: the 128k GPT-4
Turbo claim is unverified before supporting evidence exists and later returns cited support in
seeded proof mode. The adversarial 1M-context claim must not return `supported`, and the corpus
quality report separately requires at least one open contradiction row.

## Live Backfill Prerequisites

`live-first-proof` needs real source rows before a backfill can produce evidence. The source catalog
must include active, non-paused rows whose `sources.metadata.source_class` and
`sources.metadata.topic_cluster` classify the first-proof corpus. At minimum, operators need source
rows for GPT/Claude/Gemini/Llama/MCP coverage across:

- `model_provider` + `frontier_llms`
- `research` + `frontier_llms` or `ml_research`
- `registry` + `open_weight_models`
- `protocol` + `model_context_protocol`
- `release_notes` + `frontier_llms`

The historical backfill path does not fabricate these rows. Operators must add reviewed public
source rows with real adapter configuration, license posture, and source-policy booleans, then run a
bounded dry run before fetching:

```powershell
$env:DATABASE_URL = "<neon branch url>"
node scripts/dev/backfill-first-proof-corpus.mjs --dry-run
node scripts/dev/backfill-first-proof-corpus.mjs --apply
node scripts/dev/backfill-broad-corpus-proof.mjs --dry-run
node scripts/dev/backfill-broad-corpus-proof.mjs --apply

uv run intercal-pipeline backfill `
  --source-class model_provider `
  --start-date 2022-11-01 `
  --end-date 2026-06-06 `
  --max-documents 5 `
  --max-sources 2 `
  --dry-run
```

`db/seeds/0004_first_proof_sources.sql` owns the reviewed first-proof source catalog. The operator
script above applies the bounded reviewed first-proof corpus rows against the intended runtime DB:
source rows, concise reviewed source-document summaries, claims, claim evidence, one stale-data
contradiction pair, and fact versions. It is deterministic and idempotent, reads `DATABASE_URL` from
the environment or local `.env`, and never prints the value.

`db/seeds/0005_broad_corpus_sources.sql` owns the reviewed broad-corpus source catalog.
`scripts/dev/backfill-broad-corpus-proof.mjs` applies the bounded reviewed broad-corpus proof rows:
source rows, concise reviewed source-document summaries, classified claims, claim evidence, and fact
versions across benchmark, developer ecosystem, infrastructure, model-provider, policy/regulatory,
protocol, release-note, and research classes. It uses the same secret-safe `.env` loading pattern,
keeps raw redistribution disabled, and is idempotent for reruns against the intended Neon branch.

Repeat the pipeline dry run for the other required source classes, then remove `--dry-run` only on
the intended Neon branch/account and only within the resource budget. The extraction path carries
safe corpus classification keys (`source_class`, `topic_cluster`, `corpus_taxonomy`,
`corpus_track`) from source/document metadata onto extracted claims so live quality gates can count
backfilled claims without copying arbitrary source metadata.

As of the 2026-06-06 Workstream 4 pass 4 proof, `live-first-proof` passes against the configured
Neon branch after applying the reviewed first-proof corpus rows. `live-full` remains a truthful
failure until broad AI-history source rows, backfilled evidence, and classified claims exist for the
full taxonomy.

As of the 2026-06-06 Workstream 4 pass 5 proof, `live-full` passes against the configured Neon
branch after applying the reviewed broad-corpus proof rows. The passing full gate includes all
required source classes, topic clusters, date ranges, first-proof entity citation counts, citation
depth, contradiction coverage, and review-needed-rate checks. Public coverage language may now cite
the passing `live-full` gate, but should still describe these rows as a bounded reviewed proof slice,
not continuous full-web saturation.

## Live Verification Remaining

After a real backfill, run:

```powershell
node scripts/dev/verify-corpus-quality-gates.mjs live-first-proof --json
node scripts/dev/verify-corpus-quality-gates.mjs live-full --json
node scripts/dev/verify-mcp.mjs https://intercal.jami.studio/api/mcp
```

The quality gate proves database/query-layer coverage. The MCP smoke proves the deployed transport
is alive, but it does not replace the live corpus gate because MCP cannot see rollback-scoped seeded
transactions.
