# Public Launch, Corpus, Docs, And Domain Implementation Plan

Date: 2026-06-06
Status: [ ] Active draft
Source reports: `docs/research/2026-05-21-intercal-foundation-report.md`, `docs/research/2026-06-04-intercal-revisit-audit-and-dev-environment.md`, `docs/research/2026-06-06-baseline-knowledge-seeding.md`, decisions `docs/decisions/0001-foundation-stack.md` and `docs/decisions/0002-final-hosting-topology.md`, Plans 03, 04, 06, and 07
Owner: Main orchestration agent
Surface: broad AI-history corpus backfill, public knowledge experience, docs/Mintlify readiness, Intercal marketing/AI SEO, Vercel/Cloudflare domain routing

## Purpose

Build the public-facing Intercal launch path end to end: a broad, provenance-backed AI-history corpus; a useful read-only human knowledge surface; AI-friendly docs; Intercal marketing/search surfaces; and clean domain routing through Cloudflare DNS and Vercel. Jami Studio site work is outside this repo and outside this plan; only non-blocking domain/cross-link context is recorded here so Intercal fits cleanly when the studio site exists. This plan is not a narrow proof plan. The first proof exists only to validate the machinery before the corpus expands to the real target: a broad timeline of consequential AI, ML, model, agent, infrastructure, research, regulatory, and developer-ecosystem change from the GPT era onward.

## Operating Ethos

This plan should be executed from first principles, with the live architecture and code as the source of truth. Do not preserve code, routing, data shapes, UI shells, shims, barrels, compatibility layers, or provider choices merely because they already exist. If a challenge appears, ask why it exists until the answer is rooted in an external constraint, a deliberate architecture decision, or a source-truth contract. If the answer is only "because we previously shaped it that way," reassess the shape before building on it.

Intercal is greenfield enough that arbitrary incrementalism is a liability. Execution may be sequenced for verification and risk control, but the target is the final end-state system. Avoid building temporary surfaces that will predictably become refactors.

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked or requires decision

## Source Findings

- The built-in source adapters now include `wikidata_changes_v1`, `github_releases_v1`,
  `registry_releases_v1`, `arxiv_v1`, `rss_feed_v1`, `wikidata_sparql_batch_v1`, and
  `mediawiki_revisions_v1` in `services/shared/src/intercal_shared/source_registry.py`.
- Current seed sources are still Wikidata recent changes and featured GitHub releases in
  `db/seeds/0003_sources.sql`; source-row catalog expansion and execution belong to later
  Workstream 3/4 passes, not this adapter-foundation slice.
- `docs/research/2026-06-06-baseline-knowledge-seeding.md` correctly identified the main gap as
  historical backfill adapters and backfill execution paths. Workstream 2 pass 1 adds the adapter
  foundation; Workstream 3 still owns production backfill execution.
- The first useful proof should validate GPT, Claude, Gemini, Llama, and MCP timeline queries from November 2022 onward, but the product target is broader AI-history coverage, not only those five spines.
- The current dashboard has a home page, `/entity`, and `/entity/[name]` in `packages/dashboard/app`; it is a real SDK-backed shell, not the final public knowledge experience.
- Plan 06 describes the needed public surface: entity/topic/claim/evidence pages, graph and timeline explorer, briefing/search/comparison, contradiction/freshness views, subscriptions, feedback/reporting, and operator/review surfaces.
- Docs are useful for engineering but not ready as a public Mintlify/docs surface. There is no current `docs.json`, `llms.txt`, `llms-full.txt`, MDX docs app, public docs IA, docs copy pipeline, or per-page LLM text export.
- `docs/README.md` does not yet list the baseline seeding report.
- The accepted hosted topology is Vercel for dashboard/REST/MCP, Neon for Postgres, GitHub Actions and Cloud Run Jobs for pipeline execution, Upstash for queue/cache, and Cloudflare R2 behind the S3 adapter.
- `jami.studio` is already connected to Cloudflare DNS and R2 is live. Bluehost remains the registrar only while Cloudflare nameservers are authoritative.
- `intercal.jami.studio` is attached to the Intercal Vercel project, verified live, and is now the official Intercal public domain. Existing Vercel/legacy domain redirects remain in place to avoid breaking current links.
- `www.jami.studio` has no live site in this repo and is not an Intercal blocker. Future studio-site work belongs outside this repo.
- Domain routing should keep Cloudflare as DNS/R2/control layer and Vercel as app host for now. Moving compute to Cloudflare Workers is a later provider swap, not a prerequisite.

## Locked Decisions

- `intercal.jami.studio` is the official Intercal public product surface.
- Intercal docs initially live at `https://intercal.jami.studio/docs`, not `docs.intercal.jami.studio`.
- Intercal REST, OpenAPI, and MCP remain same-origin under the Intercal Vercel project unless a later decision record proves a split is better.
- Jami Studio apex/`www` routing and site implementation are separate work outside this repo. Their absence must not block Intercal corpus, docs, public UI, or launch work.
- Intercal marketing, public explorer, docs, REST, and MCP may live in the Intercal repo when they share product data, contracts, and release cadence.
- Mintlify may be introduced for rendering and docs UX, but the repo must own the source content, IA, generated OpenAPI placement, `llms.txt`, and copy/export checks.
- Structured backfill must still create provenance-bearing source documents, claims, evidence links, and fact versions. Do not insert shortcut facts that bypass the provenance chain.
- The first proof is a gate, not the target. After it passes, expand to broad AI-history coverage across model architectures, ML advances, development cycles, agent/tooling shifts, standards, benchmarks, regulation, deployment/runtime changes, and ecosystem releases.

## Scope Boundaries

- Public pages are read-only over canonical Intercal data. Feedback/reporting writes review records only and must not mutate canonical graph data.
- Source policy applies to every public page, docs example, export, widget, and marketing claim.
- Secrets stay in `.env`, Vercel env, GitHub Actions secrets, Cloud Run Secret Manager, and provider secret stores. No DNS token, Vercel token, R2 key, database URL with credentials, or provider key may enter tracked docs, fixtures, logs, or output.
- Domain records are managed in Cloudflare DNS while Cloudflare nameservers are authoritative. Do not add runtime DNS records in Bluehost.
- Keep Cloudflare proxying DNS-only during initial Vercel domain verification. Enable orange-cloud proxying only after explicit compatibility checks.
- Do not create a UI-only knowledge model, markdown-only data story, or marketing claims that cannot be backed by API/MCP behavior.
- Do not hand-edit generated contracts from `packages/shared/generated`.

## Repo Guidance

- Corpus adapters belong behind `SourcePort` / `source_registry` in `services/shared/src/intercal_shared/adapters`.
- Pipeline execution must reuse `intercal-pipeline` and service CLIs, with Actions for routine schedules and Cloud Run Jobs for heavy/on-demand backfill.
- Data model changes belong in SQL-first migrations under `db/migrations`; seed vocabularies belong in `db/seeds`.
- Public product UI belongs under `packages/dashboard` unless a new deployable app is justified by ownership and cadence.
- Jami Studio marketing belongs outside this repo and must not be treated as an Intercal workstream or blocker.
- Intercal docs may begin inside `packages/dashboard` as `/docs` or move to a dedicated `packages/docs` only if that removes real complexity and preserves same-origin public routing.
- Contracted API/MCP examples must come from `packages/shared`, `packages/sdk`, `packages/api`, and `packages/mcp-server`.
- Add `.changes/` fragments when implementation changes production behavior, docs publishing, CI, security, ops, contracts, or public routing.

## Target Product Shape

Intercal public launch has:

- A broad GPT-era AI-history corpus, spanning November 2022 through current day and continuously refreshed.
- Provenance-backed facts for model releases, model architecture changes, inference/runtime advances, ML research, agent protocols, SDK and framework releases, benchmarks, regulation, deployment infrastructure, and consequential ecosystem shifts.
- Historical backfill adapters for structured registries, research feeds, release streams, web/RSS sources, Wikidata/SPARQL batches, and MediaWiki/Wikipedia revisions.
- `get_delta`, `verify_claim`, `get_entity`, `search_evidence`, `get_freshness`, and source coverage working against the broad corpus over REST, SDK, and MCP.
- Public pages at `intercal.jami.studio` for landing, entities, topics, claims, evidence, graph/timeline, briefings, deltas, freshness, subscriptions, feedback, source coverage, docs, API examples, OpenAPI, and MCP connection guidance.
- Non-blocking outbound/inbound link slots for a future Jami Studio site, without requiring that site to exist before Intercal ships.
- AI-friendly docs with `llms.txt`, `llms-full.txt`, page-level copyable Markdown, generated OpenAPI access, canonical examples, sitemap, robots, metadata, and drift checks.
- Cloudflare DNS records for `intercal`, Vercel domain verification, TLS, old Intercal domain redirects, and canonical redirect behavior documented.

## Cross-Stream Dependency Map

Corpus architecture -> historical adapters -> backfill execution -> query quality gates -> public UI/data access -> docs and examples -> Intercal marketing/SEO -> domain verification -> release audit.

The first proof consumes the same adapters, provenance rules, and public query paths as the full corpus. It does not introduce a disposable data path.

## Orchestration Checkpoints

- 2026-06-06T11:33:19-04:00 — Dispatched Workstream 1 pass 1 to agent
  `019e9d90-f975-7b60-8f19-55813c32ff71` (`Wegener`). Ownership boundary:
  corpus taxonomy/source-policy docs, baseline seeding report alignment, seed vocabularies only if
  required by taxonomy, and small source-registry alignment only if source-truth drift is found.
  Next coordinator action: poll in short intervals, record result in
  `docs/engineering/agents/orchestrator-logs/`, then dispatch Workstream 1 pass 2 after the pass 1
  commit/result lands.
- 2026-06-06T11:42:00-04:00 — Workstream 1 pass 1 returned complete. Commit:
  `29e67ebfc7b574c3c8655e321eb1fcfc773cbed1` (`chore(docs): define corpus
  taxonomy source policy`), pushed to `origin/main`. Changed files: corpus taxonomy doc, source
  policy doc, baseline seeding report, active roadmap, and one changelog fragment. Verification:
  read back changed Markdown, `git diff --check`, and lightweight secret-pattern scan; `pnpm
  docs:check` unavailable because no script exists. No blocker reported. Next coordinator action:
  dispatch mandatory Workstream 1 pass 2 with fresh context.
- 2026-06-06T12:08:00-04:00 — Workstream 1 pass 1 completed by this agent. Added the durable
  corpus taxonomy in `docs/architecture/corpus-taxonomy.md`, aligned source-policy class defaults
  and the baseline seeding report, and confirmed no seed or source-registry changes are required
  for this pass because current vocabularies cover the taxonomy and only two adapters are live.
  Future implementation remains in Workstreams 2 through 4.
- 2026-06-06T11:41:15-04:00 — Dispatched mandatory Workstream 1 pass 2 to agent
  `019e9d98-46e8-74e2-a5f2-423c03eaf218` (`Dirac`). Ownership boundary: Workstream 1 taxonomy,
  source-policy, seed-vocabulary conclusions, baseline report alignment, and roadmap status only.
  Next coordinator action: poll in short intervals, record result in
  `docs/engineering/agents/orchestrator-logs/`, then apply the second-pass gate.
- 2026-06-06T12:12:00-04:00 — Workstream 1 pass 2 audit returned complete. Fresh-context review
  checked the durable taxonomy, source-policy defaults, baseline seeding report, source registry,
  seed vocabularies, and migration-owned schema surfaces against the live repository. No seed,
  source-registry, contract, adapter, or migration change is required for Workstream 1: the current
  docs define the source-class owner/adapter strategy/policy/display rules, full-corpus breadth
  beyond the first proof, seed-vocabulary conclusion, first-proof query set, and full-corpus
  acceptance query set without claiming unimplemented adapters or seeded topic coverage. Remaining
  implementation belongs to Workstreams 2 through 4.
- 2026-06-06T12:15:00-04:00 — Applied second-pass gate for Workstream 1. Commit
  `d7923948c33554c7bf9c3268aa04aa040e07f486` changed 2 files and 61 LOC, so it passed the
  numeric gate. Contents classified as C — tests/checks plus small doc/orchestration cleanup.
  Workstream 1 is closed; Workstream 2 dependency is satisfied.
- 2026-06-06T11:46:46-04:00 — Dispatched Workstream 2 pass 1 to agent
  `019e9d9d-4c64-7993-ae9b-0717e42574c8` (`Tesla`). Ownership boundary: historical source
  adapters, source registry, closely related ingest/pipeline registration if required, shared
  Python tests, Workstream 2 roadmap status, and changelog. Next coordinator action: poll in short
  intervals, record result in `docs/engineering/agents/orchestrator-logs/`, then dispatch mandatory
  Workstream 2 pass 2 after pass 1 lands.
- 2026-06-06T11:55:04-04:00 — Workstream 2 pass 1 agent
  `019e9d9d-4c64-7993-ae9b-0717e42574c8` was closed as a stale tool-session handle after repeated
  timed polls and a queued status nudge returned no checkpoint. Previous status was `running`; no
  result or changes were accepted from that handle. Next coordinator action: dispatch replacement
  Workstream 2 pass 1 from current repo state.
- 2026-06-06T11:56:08-04:00 — Dispatched replacement Workstream 2 pass 1 to agent
  `019e9da5-e21a-7082-8766-e449c1c7549e` (`Russell`). Ownership boundary matches the original
  Workstream 2 pass 1 adapter/source-registry/shared-test boundary. Next coordinator action: poll
  in short intervals, record result in `docs/engineering/agents/orchestrator-logs/`, then dispatch
  mandatory Workstream 2 pass 2 after pass 1 lands.
- 2026-06-06T12:03:00-04:00 — Replacement Workstream 2 pass 1 agent
  `019e9da5-e21a-7082-8766-e449c1c7549e` was closed as a stale tool-session handle after repeated
  timed polls and a queued status nudge returned no checkpoint. Previous status was `running`; no
  result or changes were accepted from that handle. Next coordinator action: dispatch a tighter
  Workstream 2 pass 1 adapter-foundation slice from current repo state.
- 2026-06-06T12:04:21-04:00 — Dispatched bounded Workstream 2 pass 1 replacement to agent
  `019e9dad-6cb8-7183-816a-f9161c3f449e` (`Erdos`). Ownership boundary: adapter foundation,
  source registry, shared adapter tests, Workstream 2 roadmap status, and changelog. Scope is a
  commit-sized adapter-foundation slice; remaining Workstream 2 adapters may be carried into pass 2
  if the slice would otherwise become oversized. Next coordinator action: poll in short intervals.
- 2026-06-06T12:12:00-04:00 — Workstream 2 pass 1 replacement returned complete. Commit:
  `a387755976cad39dee1cfe210b16b4d53d07137c` (`feat(shared): add historical source adapters`),
  pushed to `origin/main`. Changed files: historical adapters, GitHub source pagination/date-window
  support, source registry, source-policy docs, active roadmap, changelog, and focused shared/ingest
  tests. Verification reported: focused `pnpm py:test` passed 40 tests, `pnpm py:lint` passed,
  `pnpm py:typecheck` passed with warning-only existing type debt, diff checks passed, and changed
  file secret scan passed. Next coordinator action: dispatch mandatory Workstream 2 pass 2 with
  fresh context.
- 2026-06-06T12:06:46-04:00 — Workstream 2 pass 1 adapter-foundation slice implemented from the
  live repository state. Added registry, arXiv, RSS/Atom, Wikidata SPARQL batch, and MediaWiki
  revision adapters behind `SourcePort`; extended GitHub releases for historical date windows,
  per-repo page cursors, and bounded per-run page walking; registered all adapters in
  `SourceRegistry`; added focused adapter, cursor, SSRF, and source-policy ingestion tests. This
  pass does not add source rows or backfill execution; those remain Workstream 3/4 responsibilities.
- 2026-06-06T12:12:25-04:00 — Dispatched mandatory Workstream 2 pass 2 to agent
  `019e9db4-dbe5-7083-829b-e8745aa32f82` (`Pasteur`). Ownership boundary: Workstream 2 adapters,
  source registry, adapter/ingest tests, Workstream 2 roadmap status, and changelog. Fresh-context
  audit targets include source policy metadata, SSRF/URL validation, pagination/cursors, dedup,
  bounded date windows, direct fact-write avoidance, and overclaiming. Next coordinator action:
  poll in short intervals, record result, then apply the second-pass gate.
- 2026-06-06T12:24:00-04:00 — Workstream 2 pass 2 returned complete. Commit:
  `6e1155fe53f76033daf316b5658f22d4cc00ac01` (`fix(shared): harden historical adapter bounds`),
  pushed to `origin/main`. Changed files: historical adapters, GitHub adapter, focused historical
  adapter tests, active roadmap, and changelog. Verification reported: focused Python tests,
  `pnpm py:lint`, `pnpm py:typecheck`, `git diff --check`, and changed-file secret scan passed.
  Second-pass gate: 5 files and 269 LOC passes numeric gate; contents classified as B because this
  pass added meaningful adapter hardening plus regression tests. Next coordinator action: dispatch
  one more fresh-context Workstream 2 pass to confirm quiet.
- 2026-06-06T12:16:31-04:00 — Workstream 2 pass 2 fresh-context audit found cohesive adapter
  coverage with no direct fact writes, but tightened historical-bound correctness before closeout:
  invalid configured date bounds now fail closed, bounded registry/RSS/GitHub historical runs exclude
  undated records, GitHub repo identifiers are validated before request construction, and Wikidata
  SPARQL cursor hashes are stable across processes. No source catalog rows, backfill execution, query
  proof, dashboard, docs, marketing, or domain work was added.
- 2026-06-06T12:21:45-04:00 — Dispatched Workstream 2 pass 3 quiet-confirmation pass to agent
  `019e9dbd-5a85-7003-a7ed-c9fb2c74b260` (`Aquinas`). Ownership boundary: Workstream 2 adapters,
  source registry, related adapter tests, Workstream 2 roadmap status, and changelog. Next
  coordinator action: poll in short intervals, record result, then gate the quiet-confirmation
  commit.
- 2026-06-06T12:32:00-04:00 — Workstream 2 pass 3 returned complete. Commit:
  `2cea5538e8fd180b52c9c0ff33df61c6462f70f3` (`fix(shared): harden historical adapter window
  checks`), pushed to `origin/main`. Gate result: 4 files and 197 LOC passes the numeric gate, but
  contents are still meaningful adapter hardening plus regression tests, not a quiet closeout.
  Next coordinator action: dispatch another fresh-context Workstream 2 pass.
- 2026-06-06T12:25:16-04:00 — Workstream 2 pass 3 quiet-confirmation audit found one remaining
  adapter-foundation gap and fixed it in scope: arXiv and MediaWiki revision adapters now locally
  enforce historical date windows, suppress undated or identifier-less historical records, cap
  MediaWiki per-page pagination when skipped rows would otherwise keep walking pages, and sort
  registry releases deterministically when timestamps tie. No source catalog rows, backfill
  execution, query gates, dashboard, docs, marketing, or domain work was added.
- 2026-06-06T12:29:07-04:00 — Dispatched Workstream 2 pass 4 quiet-check pass to agent
  `019e9dc4-1aa9-71a0-aee5-4dbc0c112c6f` (`Confucius`). Ownership boundary: Workstream 2
  adapters, source registry, related adapter tests, Workstream 2 roadmap status, and changelog.
  Next coordinator action: poll in short intervals, record result, then gate the pass 4 commit.
- 2026-06-06T12:45:00-04:00 — Workstream 2 pass 4 quiet check found and closed one final
  identifier/cursor stability gap: arXiv now suppresses dated entries without stable Atom IDs,
  Wikidata SPARQL batches reset stale offsets when the active query differs from the saved cursor
  hash, and SPARQL rows without stable `item`/`qid` identifiers no longer emit offset-derived
  source documents. Focused adapter tests passed. Workstream 2 is quiet after this pass; source
  catalog rows, backfill execution, budgets, retries, and operator controls remain Workstream 3
  scope.

## Workstream 1: Corpus Scope And Source Taxonomy

Goal: Define the final AI-history corpus taxonomy and source policy before adding adapters or pages.

Depends on:

- [x] Existing schema, source policy docs, and baseline seeding report.

Enables:

- [x] Workstreams 2, 3, 4, 5, and public coverage claims.

Repo guidance:

- Treat this as the corpus contract for source classes, not a marketing topic list.

Primary areas:

- `docs/architecture`
- `docs/operations/source-policy.md`
- `docs/research/2026-06-06-baseline-knowledge-seeding.md`
- `db/seeds`
- `services/shared/src/intercal_shared/source_registry.py`

Implementation tasks:

- [x] Define final source classes: model releases, model cards, lab announcements, research papers, standards/specs, SDK/framework releases, benchmarks, regulation, runtime/deployment infrastructure, and Wikipedia/MediaWiki revisions.
- [x] Define source policy defaults per class, including redistribution, summary, citation-only, retention, and public display behavior.
- [x] Define corpus topic clusters for frontier models, open weights, model architecture, ML research, agent protocols, RAG/memory, developer tooling, evaluation/benchmarks, regulation/safety, and inference/runtime infrastructure.
- [x] Identify required seed vocab additions for entities, relationships, source types, and review statuses.
- [x] Document the first proof query set and the full-corpus acceptance query set.

Exit criteria:

- [x] Every source class has an owner, adapter strategy, source policy, and public display rule.
- [x] The full-corpus target is broader than the first proof and can drive implementation without rediscovery.

Suggested verification:

- `pnpm docs:check` when available
- `pnpm db:check` if seed or migration changes are included

## Workstream 2: Historical Adapter Foundation

Goal: Add first-class historical backfill adapters that populate source documents without bypassing provenance.

Depends on:

- [x] Workstream 1 source taxonomy.

Enables:

- [x] Workstream 3 backfill execution and Workstream 4 query proof.

Repo guidance:

- Adapters fetch and normalize source documents. Extraction, resolution, relationship derivation, and fact-version writes stay in the pipeline.

Primary areas:

- `services/shared/src/intercal_shared/adapters`
- `services/shared/src/intercal_shared/source_registry.py`
- `services/ingest`
- `services/pipeline`
- `services/shared/tests`

Implementation tasks:

- [x] Add `registry_releases_v1` for PyPI, npm, and Hugging Face model registry; comparable registry variants remain per-origin follow-up work.
- [x] Add `arxiv_v1` for bounded category/date search and abstract-first ingestion.
- [x] Add `rss_feed_v1` for lab blogs, standards feeds, changelogs, and project announcements.
- [x] Add `wikidata_sparql_batch_v1` for entity spine bootstrap.
- [x] Add `mediawiki_revisions_v1` for timestamped page revisions and diff-aware source documents.
- [x] Extend `github_releases_v1` only if the existing shape supports proper historical pagination and per-repo policy; otherwise replace the shape cleanly.
- [x] Add adapter conformance, SSRF/source-policy, pagination, dedup, and cursor tests.

Exit criteria:

- [x] Historical adapters can fetch November 2022 onward documents into the existing pipeline with source policy metadata intact.
- [x] No adapter writes canonical facts directly.

Pass 1 closeout note: the adapter foundation is in place and verified with focused Python tests.
Comparable registry variants beyond PyPI/npm/Hugging Face remain follow-up adapter work if needed.
No source catalog rows, backfill runner, Cloud Run job, or query-quality proof was added in this
slice. Workstream 3 owns execution, budget, retries, and operator controls; Workstream 4 owns corpus
coverage and query proof.

Pass 2 closeout note: the fresh-context audit kept the Workstream 2 adapter foundation in place and
landed bounded-window hardening for date validation, undated historical records, GitHub repo
identifier validation, and deterministic SPARQL cursor hashing. Workstream 3 still owns source-row
catalog expansion and backfill execution.

Pass 3 closeout note: the quiet-confirmation audit found and closed the remaining bounded-window
adapter gap for arXiv and MediaWiki revision records, including local out-of-window/undated filtering,
missing revision-id suppression, bounded MediaWiki page walking, and deterministic registry ordering
for same-timestamp releases. Workstream 3 still owns source-row catalog expansion, backfill execution,
budgets, retries, and operator controls.

Pass 4 closeout note: the historical adapter foundation is quiet after closing the final
identifier/cursor stability issue found in fresh audit. arXiv suppresses dated entries without stable
Atom IDs, Wikidata SPARQL resumes only when the saved query hash matches the active query, skipped
identifier-less SPARQL rows advance the cursor without producing offset-derived source documents, and
no adapter writes canonical facts directly. Workstream 3 still owns source-row catalog expansion,
backfill execution, budgets, retries, and operator controls.

Suggested verification:

- `pnpm py:test services/shared services/ingest services/pipeline`
- `pnpm py:lint`
- `pnpm py:typecheck`

## Workstream 3: Backfill Execution And Budgeting

Goal: Run historical backfill as a real production-grade pipeline path with budget, retries, observability, and operator controls.

Depends on:

- [ ] Workstream 2 adapters.
- [ ] Existing Actions and Cloud Run job topology.

Enables:

- [ ] Workstream 4 corpus quality gates.

Repo guidance:

- Use the same pipeline CLIs and adapter ports as scheduled ingestion. Do not create a separate backfill runner with different semantics.

Primary areas:

- `services/pipeline`
- `scripts/ops`
- `.github/workflows`
- `docs/operations/pipeline-cd.md`
- `docs/operations/resource-budget.md`

Implementation tasks:

- [ ] Add date-windowed backfill modes and source allowlists to `intercal-pipeline`.
- [ ] Add bounded Cloud Run Job execution for historical backfill with `max_documents`, date range, source class, and dry-run controls.
- [ ] Add resumable cursor tracking and idempotent dedup proof for large historical runs.
- [ ] Add provider budget guards for LLM extraction, embeddings, HTTP calls, and queue usage.
- [ ] Add observability records for source counts, extraction counts, fact writes, skipped documents, policy blocks, token usage, and failures.
- [ ] Add operator runbook entries for first proof, full corpus expansion, pause/resume, rollback, and cost review.

Exit criteria:

- [ ] A backfill run can be started, paused, resumed, audited, and repeated without duplicate facts or policy drift.

Suggested verification:

- `pnpm py:test services/pipeline services/ingest services/extract services/resolve services/synthesize`
- `pnpm ops:health`
- `pnpm db:check`

## Workstream 4: Corpus Quality Gates And Broad AI-History Expansion

Goal: Prove the first timeline, then expand to broad AI-history coverage with measurable query quality.

Depends on:

- [ ] Workstream 3 backfill execution.
- [ ] Plan 03 REST/MCP/SDK query surfaces.

Enables:

- [ ] Workstream 5 public UI and Workstream 6 docs examples.

Repo guidance:

- The first proof must use the same source classes and query paths as the full corpus.

Primary areas:

- `packages/core`
- `packages/api`
- `packages/mcp-server`
- `packages/sdk`
- `scripts/dev`
- `docs/operations`

Implementation tasks:

- [ ] Prove GPT, Claude, Gemini, Llama, and MCP timelines from November 2022 onward.
- [ ] Prove `get_delta("frontier LLMs", since=2023-03-01)` returns cited, budget-bounded changes from backfilled evidence.
- [ ] Prove `verify_claim` with `as_of` behavior against historical evidence and contradictions.
- [ ] Expand from first proof into the full corpus taxonomy: model architecture, ML research, development cycles, agent/tooling shifts, benchmarks, regulation, infrastructure, and open-weight ecosystem changes.
- [ ] Add corpus coverage and freshness gates for source class, topic cluster, date range, entity coverage, citation depth, contradiction state, and review-needed rate.
- [ ] Add adversarial and stale-data checks for claims that changed over time.

Exit criteria:

- [ ] Public claims about Intercal's historical coverage are backed by measurable corpus coverage and query evidence.
- [ ] The corpus supports broad AI-history deltas, not only the initial proof entities.

Suggested verification:

- `pnpm test`
- `pnpm py:test`
- `node scripts/dev/verify-mcp.mjs <base>/api/mcp`
- focused live REST/SDK checks against a seeded or production branch

## Workstream 5: Public Intercal Knowledge Experience

Goal: Replace the thin dashboard shell with the full read-only public product surface.

Depends on:

- [ ] Workstream 4 quality gates.
- [ ] Plan 06 route/workflow ownership.

Enables:

- [ ] Workstream 6 docs examples, Workstream 7 Intercal marketing/SEO, and Workstream 8 domain verification.

Repo guidance:

- Every displayed fact must have an evidence path or an explicit unknown/coverage state.

Primary areas:

- `packages/dashboard`
- `packages/sdk`
- `packages/shared`
- `docs/architecture`

Implementation tasks:

- [ ] Build Intercal landing at `/` on `intercal.jami.studio`.
- [ ] Build entity, topic, claim, evidence, source, freshness, and coverage pages.
- [ ] Build graph and timeline explorer with point-in-time controls, confidence, contradiction, and source-origin overlays.
- [ ] Build briefing/search/comparison pages around `get_delta`, `verify_claim`, `search_evidence`, and `get_freshness`.
- [ ] Build subscription and feedback/reporting flows that reuse audited review records.
- [ ] Build operator/review surfaces behind auth for source health, ingestion runs, feedback, audit events, usage, budget, and coverage.
- [ ] Add mobile, accessibility, empty, stale, loading, and source-policy states.

Exit criteria:

- [ ] `intercal.jami.studio` is useful as a public human experience, not only an API shell.

Suggested verification:

- `pnpm --filter @intercal/dashboard test`
- `pnpm --filter @intercal/dashboard build`
- browser verification across desktop and mobile
- `pnpm contracts:check`

## Workstream 6: Docs, Mintlify Readiness, And AI-Friendly Exports

Goal: Publish docs that are useful to humans and agents, with source-owned content and LLM-readable exports.

Depends on:

- [ ] Workstream 4 query proof.
- [ ] Workstream 5 public route ownership.

Enables:

- [ ] Workstream 7 Intercal marketing and AI SEO.

Repo guidance:

- Docs should describe actual behavior and link to generated contracts rather than duplicating volatile schemas.

Primary areas:

- `docs`
- `packages/dashboard`
- `packages/shared/generated/openapi/openapi.json`
- `scripts`

Implementation tasks:

- [ ] Define public docs IA for introduction, concepts, quickstart, MCP, REST, SDK, authentication, examples, source policy, provenance, backfill/corpus coverage, and operations transparency.
- [ ] Add Mintlify-compatible `docs.json` or equivalent source-owned config if Mintlify is selected.
- [ ] Add `/docs` route or docs package rendering at `intercal.jami.studio/docs`.
- [ ] Add `llms.txt` and `llms-full.txt`.
- [ ] Add copyable Markdown or text export for every public docs page.
- [ ] Add generated OpenAPI placement and SDK/MCP examples that are verified against contracts.
- [ ] Add docs drift checks for route inventory, OpenAPI availability, examples, links, and AI export coverage.
- [ ] Update `docs/README.md` with the baseline seeding report and this roadmap.

Exit criteria:

- [ ] Docs are ready to connect to Mintlify or serve from the Intercal app without losing source ownership or AI-readable exports.

Suggested verification:

- `pnpm contracts:check`
- `pnpm docs:check`
- `pnpm lint`

## Workstream 7: Intercal Marketing And AI SEO

Goal: Launch Intercal product marketing and AI SEO surfaces without turning product UI into generic landing-page copy.

Depends on:

- [ ] Workstream 5 Intercal public surface shape.
- [ ] Workstream 6 docs/export shape.

Enables:

- [ ] Workstream 8 domain verification.

Repo guidance:

- Jami Studio marketing is separate outside this repo. Include only non-blocking links/copy hooks that let a future studio site point to Intercal.

Primary areas:

- `packages/dashboard`
- `docs`

Implementation tasks:

- [ ] Build Intercal marketing copy around temporal knowledge substrate, cutoff deltas, claim verification as of a date, provenance, MCP, REST, and broad AI-history corpus.
- [ ] Add non-blocking link/copy slots for a future Jami Studio site without requiring `www.jami.studio` to be live.
- [ ] Add sitemap, robots, canonical metadata, OpenGraph/Twitter metadata, structured data where useful, and stable share images.
- [ ] Add AI SEO surfaces: `llms.txt`, copyable page text, canonical docs examples, public entity/topic pages, and crawlable public explanations.
- [ ] Add route and metadata tests for public pages.

Exit criteria:

- [ ] `intercal.jami.studio` has a crawlable, canonical public Intercal role, and any future Jami Studio references are non-blocking.

Suggested verification:

- `pnpm --filter @intercal/dashboard build`
- link, sitemap, metadata, and browser checks

## Workstream 8: Domain Routing, Vercel Projects, And Cloudflare DNS

Goal: Verify and document the Intercal domain without moving compute prematurely or depending on unrelated studio-site work.

Depends on:

- [ ] Workstream 5 or 7 deployable Intercal public pages.

Enables:

- [ ] Public launch smoke checks and release audit.

Repo guidance:

- Cloudflare owns DNS. Vercel owns app hosting. Bluehost remains registrar only while Cloudflare nameservers are authoritative.

Primary areas:

- Vercel project settings
- Cloudflare DNS
- `docs/operations/deployment.md`
- `docs/operations/account-setup.md`

Implementation tasks:

- [ ] Confirm Vercel project `intercal` uses root directory `packages/dashboard`.
- [x] Attach `intercal.jami.studio` to the Intercal Vercel project.
- [x] Add Vercel-provided DNS records for `intercal` in Cloudflare and verify the live domain.
- [ ] Smoke Vercel TLS, `/`, `/docs`, `/api/openapi.json`, `/api/v1/freshness`, and `/api/mcp` on the official Intercal domain.
- [ ] Document the Intercal domain and routing runbook without storing provider secrets.
- [ ] Note that `www.jami.studio` routing/site work is external and non-blocking.

Exit criteria:

- [ ] `intercal.jami.studio` resolves through Cloudflare DNS to the Vercel-hosted Intercal project with TLS and canonical behavior proven.

Suggested verification:

- `Invoke-WebRequest https://intercal.jami.studio -UseBasicParsing`
- `Invoke-WebRequest https://intercal.jami.studio/api/openapi.json -UseBasicParsing`
- `node scripts/dev/verify-mcp.mjs https://intercal.jami.studio/api/mcp`

## Workstream 9: Release Audit And Provider Posture

Goal: Confirm the public launch stack is coherent, portable, and not blocked by avoidable host decisions.

Depends on:

- [ ] Workstreams 1 through 8.

Enables:

- [ ] Launch closeout and future own-domain decision.

Repo guidance:

- Use Vercel for velocity now. Treat Cloudflare compute as a later provider swap requiring proof, not as an emotional milestone.

Primary areas:

- `docs/decisions`
- `docs/architecture/deployment-topology.md`
- `docs/operations`
- `scripts/ops`

Implementation tasks:

- [ ] Audit whether any code depends on Vercel-specific behavior beyond deployment config.
- [ ] Confirm Hono/API/MCP portability claims remain true after public pages and docs land.
- [ ] Confirm Cloudflare R2 storage is live behind the S3 adapter.
- [ ] Confirm no public page leaks source text against policy.
- [ ] Confirm no marketing claim exceeds corpus coverage or API/MCP behavior.
- [ ] Decide whether to keep `intercal.jami.studio`, purchase an Intercal-owned domain, or prepare Cloudflare compute proof as a separate decision record.

Exit criteria:

- [ ] Public launch is complete on the chosen topology, and future host/domain moves are explicit decisions rather than hidden pressure.

Suggested verification:

- `pnpm verify`
- full browser verification
- secret scan over tracked files
- provider smoke checks where operator access is available

## Final Verification And Closeout

- `pnpm format:check`
- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `pnpm build`
- `pnpm contracts:check`
- `pnpm py:format:check`
- `pnpm py:lint`
- `pnpm py:typecheck`
- `pnpm py:test`
- `pnpm db:check`
- `pnpm ops:health`
- Browser verification for `intercal.jami.studio` across desktop and mobile.
- Live REST, OpenAPI, and MCP smoke checks against `intercal.jami.studio`.
- Docs link/export/sitemap/robots/metadata checks.
- Secret scan over tracked files and generated public outputs.
- Update durable docs that describe actual behavior.
- Add `.changes/` fragments for production-meaningful implementation.
- Stage only intentional files.
- Commit with a conventional subject and body.
- Push after verification and review.

## Acceptance Criteria

- [ ] Broad GPT-era AI-history backfill exists and is continuously refreshable.
- [ ] Every public fact traces to source documents, claims, evidence, and fact versions or displays an explicit unknown/coverage state.
- [ ] REST, SDK, and MCP return useful deltas and claim verification over the backfilled corpus.
- [ ] `intercal.jami.studio` serves the Intercal public product surface, docs, REST, OpenAPI, and MCP from the accepted Vercel topology.
- [ ] Docs are ready for Mintlify or same-origin rendering and include `llms.txt`, `llms-full.txt`, copyable page text, and verified examples.
- [ ] Marketing and AI SEO surfaces are crawlable, canonical, and backed by actual product behavior.
- [ ] Cloudflare DNS and R2 are used where they help now; compute migration remains an explicit future proof, not a current blocker.
- [ ] Durable docs, decisions, and runbooks reflect the real deployed behavior.

## Implementation Order

1. Define corpus taxonomy and source-policy defaults.
2. Build historical adapters to the final source shapes.
3. Add production-grade backfill execution and budget controls.
4. Prove the first GPT/Claude/Gemini/Llama/MCP timeline through real REST/MCP/SDK queries.
5. Expand into broad AI-history corpus coverage and quality gates.
6. Build Intercal public knowledge surfaces in `packages/dashboard`.
7. Build docs/Mintlify readiness and AI-readable exports.
8. Build Intercal marketing/AI SEO surfaces with non-blocking hooks for future Jami Studio links.
9. Verify the Intercal Cloudflare/Vercel domain and smoke live routes.
10. Run release audit, update durable docs, add changelog fragments, commit, and push.

## Expansion Track

- Intercal-owned domain purchase and cutover, with `docs.intercal.<tld>`, `api.intercal.<tld>`, and `mcp.intercal.<tld>` considered only after the current subdomain path proves product value.
- Cloudflare Workers or Pages compute proof for the Hono/API surface if Vercel becomes a cost, policy, or performance constraint.
- Public embeddable graph/delta widgets where source policy allows.
- Dataset snapshots and reproducible corpus manifests for researchers and agents.
