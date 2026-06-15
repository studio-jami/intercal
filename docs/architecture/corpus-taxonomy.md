# AI-History Corpus Taxonomy

Status: Current target taxonomy for corpus backfill and public coverage claims.
Last updated: 2026-06-06

This document defines the source classes and topic clusters Intercal uses for the
GPT-era AI-history corpus. It is a planning contract for adapters, source rows,
policy defaults, and acceptance queries. It does not claim that every adapter or
source row exists today. The live source registry remains the executable truth
for implemented adapters.

## Scope

The corpus target is consequential AI, ML, agent, infrastructure, research,
regulatory, and developer-ecosystem change from November 2022 onward, with
ongoing refresh after the historical backfill catches up.

The first proof is deliberately smaller: GPT, Claude, Gemini, Llama, and MCP
timelines from November 2022 onward. It validates the same source classes,
provenance rules, and REST/MCP query paths that the full corpus uses.

## Source Classes

Every source row must declare one source class in `sources.metadata.source_class`
once historical sources are added. `sources.source_type` remains the broad
storage-level type (`api`, `registry`, `rss`, `dump`, etc.); `source_class`
describes the corpus role and policy default.

The **access tier** (`sources.metadata.access_tier`, one of `S`/`A`/`B`/`C`)
is the orthogonal, license-driven axis that sets the *redistribution* defaults
(`redistribution_allowed`, `summary_allowed`, `citation_only`). Source class
describes the corpus *role*; access tier describes what the *license* lets the
corpus do with the fact. The canonical tier definitions, the CC0-first
principle, the Tier X exclusion list (Grokipedia, Google KG API, GDELT, raw web
crawl), and the structure-now/data-gated-later policy live in
[`../operations/source-policy.md`](../operations/source-policy.md) and govern
these defaults. Tier S (CC0 — e.g. Wikidata, OpenAlex) is the
fact-redistributable spine for `research_paper`, `ml_research`, and
`benchmark`/`evaluation_benchmarks` work; Tier B (CC BY-SA — e.g. Wikipedia
revisions feeding `mediawiki_revision`) stays summary/cite-only.

| Source class | Owner | Adapter strategy | Default source policy | Public display rule |
| --- | --- | --- | --- | --- |
| `model_release` | Pipeline/source registry | Registry, RSS, GitHub release, or lab API adapter for dated model/product releases. | Verify per origin before activation; default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`. | Show title, source, date, cited claims, and summaries; never show full body unless redistribution is explicitly verified. |
| `model_card` | Pipeline/source registry | Registry adapter for Hugging Face and comparable model registries. | Verify per card/source; default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`. | Show metadata-backed facts, cited summaries, and registry link; raw card text only when allowed. |
| `lab_announcement` | Pipeline/source registry | RSS/feed/history adapter for lab blogs, changelogs, and official announcements. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; tighten to citation-only when terms require it. | Show cited summary and claim evidence; no copied article body by default. |
| `research_paper` | Pipeline/source registry | arXiv or DOI/metadata adapter; abstract-first ingestion before PDF/full text. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; PDF text requires explicit license review. | Show title, authors when extracted, abstract-derived summaries, citations, and DOI/arXiv links. |
| `standard_spec` | Pipeline/source registry | Spec repository, standards feed, or tagged release adapter. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; per-spec license can relax or tighten. | Show versioned spec changes, citations, and summaries; avoid full spec redistribution unless verified. |
| `sdk_framework_release` | Pipeline/source registry | GitHub releases and package registry adapter for SDKs/frameworks/tools. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; per-repo/package license may relax. | Show release title/version/date, cited changes, package/repo link, and summaries. |
| `benchmark` | Pipeline/source registry | Paper, leaderboard, dataset, or project-release adapter. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; dataset redistribution is never assumed. | Show benchmark definition, scores/changes only when evidence supports them, and cited source links. |
| `regulation` | Pipeline/source registry | Government, EUR-Lex, Federal Register, court, or policy feed adapter. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; citation-only when jurisdiction terms require it. | Show enactment/status claims, dated citations, summaries, and jurisdiction; no legal advice framing. |
| `runtime_infrastructure` | Pipeline/source registry | GitHub releases, package registries, cloud/runtime release feeds, and standards sources. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`. | Show cited runtime/deployment capability changes and versioned evidence. |
| `mediawiki_revision` | Pipeline/source registry | MediaWiki revision adapter for bounded anchor pages and revision windows. | Default `redistribution_allowed=false`, `summary_allowed=true`, `citation_only=false`; attribution/license details stay in source metadata. | Show revision timestamp, page title, cited diff-derived summary, and source link; no full article/diff body by default. |

Policy defaults are conservative. A source row may loosen them only after the
operator records a concrete license reason in `license_spdx` or `license_notes`.
A source row may always tighten them to `citation_only=true`.

## Topic Clusters

Topic clusters are corpus planning surfaces, not canonical facts. They map to
`topics` and `topic_memberships` only after Workstream 4 proves coverage.

| Cluster | Corpus role | First representative entities/topics |
| --- | --- | --- |
| `frontier_models` | Closed and hosted frontier model families and launches. | GPT, Claude, Gemini, o-series. |
| `open_weights` | Open-weight and source-available model families, model cards, releases, and lineage. | Llama, Mistral/Mixtral, DeepSeek, Hugging Face model registry. |
| `model_architecture` | Architecture, context window, multimodality, tool-use, MoE, quantization, and training/inference changes. | Transformer variants, MoE, long-context, function calling. |
| `ml_research` | Research papers and technical advances that become part of agent/developer practice. | arXiv `cs.CL`, `cs.AI`, `cs.LG`, `stat.ML` anchors. |
| `agent_protocols` | Agent protocols, tool interfaces, function calling, MCP, and interoperability specs. | MCP, OpenAPI tool calling, SDK servers. |
| `rag_memory` | Retrieval, embeddings, vector databases, long-term memory, and grounding. | RAG, embeddings, vector stores, memory systems. |
| `developer_tooling` | SDKs, frameworks, coding assistants, agent frameworks, orchestration libraries. | LangChain, LlamaIndex, Vercel AI SDK, OpenAI/Anthropic SDKs. |
| `evaluation_benchmarks` | Benchmarks, leaderboards, evaluation datasets, and measurable capability claims. | MMLU, HumanEval, SWE-bench, GPQA. |
| `regulation_safety` | Regulation, safety standards, policy events, public-sector guidance, and formal obligations. | EU AI Act, US AI executive orders, AI Safety Summit. |
| `inference_runtime_infrastructure` | Runtime, serving, hardware/software inference stack, deployment, and cost/latency shifts. | llama.cpp, Ollama, vLLM, Kubernetes/runtime releases. |

## Seed Vocabulary Needs

The current seed vocabularies are sufficient for Workstream 1:

- Entity types already cover organizations, people, products, concepts,
  legislation, technical artifacts, datasets, jurisdictions, events, sources,
  roles, and offices.
- Relationship types already cover publication/release, authorship,
  legislation/jurisdiction, conceptual relation, source reporting, claim
  support/contradiction, and role/office occupancy.
- Review statuses already exist in the relevant schema tables:
  `entity_resolution_candidates.proposed_decision`, `mentions.resolution_status`,
  `claim_contradictions.resolution_status`, and `review_records.status`.

No seed file changes are required for this pass. Future work may add seeded
`topics` rows for the clusters above after Workstream 4 defines measurable
coverage gates; until then, topic clusters stay as taxonomy, not fake seeded
state.

## First-Proof Query Set

The first proof is complete only when these queries return cited, dated results
from real source documents through REST, SDK, and MCP:

1. `get_entity("ChatGPT", at_date="2023-03-01")` shows launch-era state with
   source evidence.
2. `get_entity("Claude", at_date="2024-03-01")` shows model-family state with
   source evidence.
3. `get_entity("Gemini", at_date="2024-02-15")` shows model-family state with
   source evidence.
4. `get_entity("Llama", at_date="2024-04-18")` shows open-weight release state
   with source evidence.
5. `get_freshness("MCP protocol")` reports coverage/freshness from spec or SDK
   release evidence.
6. `get_delta("frontier LLMs", since="2023-03-01")` returns budget-bounded,
   cited model changes.
7. `verify_claim("GPT-4 Turbo supports a 128k context window",
   as_of="2024-04-01")` returns support/contradiction status with evidence.
8. `search_evidence("EU AI Act high-risk", date_range="2023-01-01/2024-12-31")`
   returns regulation evidence without unsupported legal interpretation.

## Full-Corpus Acceptance Query Set

The full corpus is acceptable when it answers all first-proof queries plus:

1. `get_delta("open weight models", since="2023-07-01")` across model cards,
   lab announcements, GitHub releases, and research evidence.
2. `get_delta("agent protocols", since="2024-01-01")` across MCP/spec/SDK
   evidence.
3. `get_delta("RAG and memory", since="2023-01-01")` across research,
   framework, and infrastructure sources.
4. `verify_claim("Llama 3.1 introduced a 405B open-weight model",
   as_of="2024-08-01")` with source-backed support or contradiction.
5. `verify_claim("The EU AI Act entered into force in 2024",
   as_of="2025-01-01")` with jurisdictional evidence and no legal-advice copy.
6. `get_freshness("inference runtime infrastructure")` showing source-class
   coverage and stale/unknown gaps.
7. `search_evidence("SWE-bench agent benchmark", date_range="2023-01-01/2026-06-06")`
   across paper/benchmark/developer-tooling sources.
8. A coverage report grouped by source class, topic cluster, date range, entity
   count, citation depth, contradiction state, and review-needed rate.

Public coverage claims must be no broader than the classes, clusters, and query
gates that have passed against the live corpus.
