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

- The current built-in source adapters are `wikidata_changes_v1` and `github_releases_v1` in `services/shared/src/intercal_shared/source_registry.py`.
- Current seed sources are Wikidata recent changes and featured GitHub releases in `db/seeds/0003_sources.sql`; they are useful but not enough for a GPT-era historical corpus.
- `docs/research/2026-06-06-baseline-knowledge-seeding.md` correctly identifies the main gap: historical backfill adapters and backfill execution paths, not schema.
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

- [ ] Workstream 3 backfill execution and Workstream 4 query proof.

Repo guidance:

- Adapters fetch and normalize source documents. Extraction, resolution, relationship derivation, and fact-version writes stay in the pipeline.

Primary areas:

- `services/shared/src/intercal_shared/adapters`
- `services/shared/src/intercal_shared/source_registry.py`
- `services/ingest`
- `services/pipeline`
- `services/shared/tests`

Implementation tasks:

- [ ] Add `registry_releases_v1` for PyPI, npm, Hugging Face model registry, and comparable versioned registries.
- [ ] Add `arxiv_v1` for bounded category/date search and abstract-first ingestion.
- [ ] Add `rss_feed_v1` for lab blogs, standards feeds, changelogs, and project announcements.
- [ ] Add `wikidata_sparql_batch_v1` for entity spine bootstrap.
- [ ] Add `mediawiki_revisions_v1` for timestamped page revisions and diff-aware source documents.
- [ ] Extend `github_releases_v1` only if the existing shape supports proper historical pagination and per-repo policy; otherwise replace the shape cleanly.
- [ ] Add adapter conformance, SSRF/source-policy, pagination, dedup, and cursor tests.

Exit criteria:

- [ ] Historical adapters can fetch November 2022 onward documents into the existing pipeline with source policy metadata intact.
- [ ] No adapter writes canonical facts directly.

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
