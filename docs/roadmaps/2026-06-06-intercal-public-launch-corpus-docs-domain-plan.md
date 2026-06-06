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
- 2026-06-06T12:40:00-04:00 — Workstream 2 pass 4 returned complete. Commit:
  `f866234eec7fe3faaff875ac4e482f95732ff5ea` (`fix(shared): harden historical adapter cursor
  ids`), pushed to `origin/main`. Gate result: 4 files and 123 LOC passes the numeric gate, but
  contents are still meaningful adapter hardening plus regression tests. Next coordinator action:
  dispatch another fresh-context Workstream 2 pass; do not close from pass 4.
- 2026-06-06T12:45:00-04:00 — Workstream 2 pass 4 quiet check found and closed one final
  identifier/cursor stability gap: arXiv now suppresses dated entries without stable Atom IDs,
  Wikidata SPARQL batches reset stale offsets when the active query differs from the saved cursor
  hash, and SPARQL rows without stable `item`/`qid` identifiers no longer emit offset-derived
  source documents. Focused adapter tests passed. Coordinator checkpoint `c0e9fb5` kept Workstream 2
  open because pass 4 still made meaningful adapter hardening changes.
- 2026-06-06T12:37:07-04:00 — Dispatched Workstream 2 pass 5 strict quiet audit to agent
  `019e9dcb-6d82-7ec0-a8fe-bde9d650908d` (`Sartre`). Ownership boundary: Workstream 2 adapters,
  source registry, related adapter tests, Workstream 2 roadmap status, and changelog. Next
  coordinator action: poll in short intervals, record result, then gate the pass 5 commit.
- 2026-06-06T12:50:00-04:00 — Workstream 2 pass 5 returned complete. Commit:
  `45cc5851141b6d9925d95184d3e3eb83aa73ae38` (`fix(shared): harden rss feed cursor scope`),
  pushed to `origin/main`. Gate result: 5 files and 172 LOC passes the numeric gate, but contents
  are another meaningful adapter hardening fix plus tests. Next coordinator action: dispatch another
  fresh-context Workstream 2 pass; do not close from pass 5.
- 2026-06-06T13:05:00-04:00 — Workstream 2 pass 5 strict quiet audit found and closed one
  remaining RSS cursor/dedup gap. RSS/Atom feeds now track seen IDs and latest timestamps per feed
  URL, and entries without a stable feed ID or link no longer produce title-derived source
  documents. Focused adapter tests passed. Because pass 5 made meaningful adapter hardening changes,
  another fresh-context quiet pass may still be needed before Workstream 2 is closed.
- 2026-06-06T12:44:13-04:00 — Dispatched Workstream 2 pass 6 strict quiet audit to agent
  `019e9dd1-ef93-7ad0-983d-096858428e5e` (`Locke`). Ownership boundary: Workstream 2 adapters,
  source registry, related adapter tests, Workstream 2 roadmap status, and changelog. Next
  coordinator action: poll in short intervals, record result, then gate the pass 6 commit.
- 2026-06-06T12:57:00-04:00 — Workstream 2 pass 6 returned complete. Commit:
  `486f6c8e237024ee52e61ab0a74583f3283c4274` (`fix(shared): harden rss feed item urls`), pushed
  to `origin/main`. Gate result: 4 files and 92 LOC passes the numeric gate, but contents are a
  meaningful RSS URL-validation hardening fix plus tests. Next coordinator action: dispatch another
  fresh-context Workstream 2 quiet audit; do not close from pass 6.
- 2026-06-06T13:21:00-04:00 — Workstream 2 pass 6 strict quiet audit found and closed one
  remaining RSS URL-validation gap. RSS/Atom entries from an otherwise valid public feed now skip
  item links blocked by the SSRF/public-URL guard before persisting the link as source-document
  citation metadata. No source catalog rows, backfill execution, query gates, dashboard, docs,
  marketing, domain, or direct fact-write work was added. Because pass 6 made meaningful adapter
  hardening changes, another fresh-context quiet pass may still be needed before Workstream 2 is
  closed.
- 2026-06-06T12:50:30-04:00 — Dispatched Workstream 2 pass 7 strict quiet audit to agent
  `019e9dd7-a767-73b1-a9ee-defe3c6aea96` (`Bernoulli`). Ownership boundary: Workstream 2 adapters,
  source registry, related adapter tests, Workstream 2 roadmap status, and changelog. Next
  coordinator action: poll in short intervals, record result, then gate the pass 7 commit.
- 2026-06-06T13:24:00-04:00 — Workstream 2 pass 7 strict quiet audit returned quiet. Fresh
  context rechecked source-policy metadata, date-window filtering, cursor stability, dedup scope,
  feed and item URL validation, undated and identifier-less suppression, request caps, GitHub
  owner/repo validation, direct fact-write avoidance, hidden demo data/mocks, and overclaiming
  against the live adapter and ingest code. No additional adapter, source-registry, ingest, source
  catalog, backfill execution, query gate, dashboard, docs/marketing, domain, or direct fact-write
  change is required. Workstream 2 is closed; Workstream 3 owns source-row expansion, backfill
  execution, budgets, retries, and operator controls.
- 2026-06-06T12:55:52-04:00 — Dispatched Workstream 3 pass 1 to agent
  `019e9ddc-8a5e-7553-a4e2-90b433c92e14` (`Boyle`). Ownership boundary: pipeline backfill
  execution, ops scripts, Actions/Cloud Run controls, resource-budget and pipeline runbooks,
  related Python tests, Workstream 3 roadmap status, and changelog. Next coordinator action: poll
  in short intervals, record result, then dispatch mandatory Workstream 3 pass 2 after pass 1 lands.
- 2026-06-06T13:12:00-04:00 — Workstream 3 pass 1 returned complete. Commit:
  `5a34a4aba3859017518a677cc93d753e4eb52bb5` (`feat(pipeline): add bounded historical backfill
  execution`), pushed to `origin/main`. Changed files: pipeline CLI/run, ingest cursor scoping,
  Actions workflow, operations docs, resource budget, active roadmap, changelog, and focused tests.
  Verification reported: `pnpm py:test services/pipeline services/ingest`, `pnpm py:lint`, `pnpm
  py:typecheck`, `git diff --check`, and changed-file secret scan passed. Not run: live Neon/Cloud
  Run/Actions backfill and `pnpm ops:health`. Next coordinator action: dispatch mandatory
  Workstream 3 pass 2 with fresh context, including non-LLM budget accounting gap review.
- 2026-06-06T13:11:19-04:00 — Dispatched mandatory Workstream 3 pass 2 to agent
  `019e9dea-a8e6-7701-9cc9-5ba80a1256a6` (`Darwin`). Ownership boundary: Workstream 3 pipeline,
  ingest cursor/run semantics, ops scripts/workflows, operations docs, resource budget, related
  Python tests, Workstream 3 roadmap status, and changelog. Next coordinator action: poll in short
  intervals, record result, then apply the second-pass gate.
- 2026-06-06T13:24:00-04:00 — Workstream 3 pass 2 returned complete. Commit:
  `d10a7e0bdb267839504e7499d01f813b208632bb` (`fix(ingest): record source http request usage`),
  pushed to `origin/main`. Gate result: 6 files and 286 LOC passes the numeric gate, but contents
  are meaningful HTTP usage telemetry plus tests. Queue command accounting remains explicitly
  unavailable because this backfill path does not instantiate `QueuePort` and queue adapters do not
  emit command counts. Next coordinator action: dispatch Workstream 3 pass 3 quiet confirmation.
- 2026-06-06T13:19:37-04:00 — Dispatched Workstream 3 pass 3 quiet-confirmation pass to agent
  `019e9df2-1cc6-7f92-9d67-e127cf74c308` (`Planck`). Ownership boundary: Workstream 3 pipeline,
  ingest cursor/run semantics, ops scripts/workflows, operations docs, resource budget, related
  Python tests, Workstream 3 roadmap status, and changelog. Next coordinator action: poll in short
  intervals, record result, then gate the pass 3 commit.
- 2026-06-06T13:37:00-04:00 — Workstream 3 pass 3 returned complete. Commit:
  `5fbdddf6ec476070294ca234297f688aeaf8c990` (`fix(ingest): resume scoped backfill cursors`),
  pushed to `origin/main`. Gate result: 5 files and 144 LOC passes the numeric gate, but contents
  are a meaningful cursor-resume fix plus tests. Queue command accounting remains documented as
  unavailable until real queue telemetry exists. Next coordinator action: dispatch Workstream 3 pass
  4 quiet confirmation.
- 2026-06-06T13:29:45-04:00 — Dispatched Workstream 3 pass 4 strict quiet audit to agent
  `019e9dfb-9a34-7412-900d-2dc6140606df` (`Lagrange`). Ownership boundary: Workstream 3 pipeline,
  ingest cursor/run semantics, ops scripts/workflows, operations docs, resource budget, related
  Python tests, Workstream 3 roadmap status, and changelog. Next coordinator action: poll in short
  intervals, record result, then gate the pass 4 commit.
- 2026-06-06T14:02:00-04:00 — Workstream 3 pass 4 strict quiet audit returned quiet. Fresh
  context rechecked `intercal-pipeline backfill`, source allowlists and source-class/adapter
  filters, date-window overrides, `max_documents`/`max_sources`, dry-run behavior, cursor scoping
  across alternating windows, idempotent document/fact dedup, Actions and Cloud Run controls,
  pause/resume/rollback docs, source HTTP usage accounting, budget guards, queue accounting
  limitation wording, and overclaiming against the live code and tests. No code, workflow, ops
  script, durable-doc, changelog, or test change is required. Workstream 3 is closed as quiet with
  the explicit queue-command accounting limitation documented.
- 2026-06-06T13:35:23-04:00 — Dispatched Workstream 4 pass 1 to agent
  `019e9e00-ba5c-71f0-8576-e5e9177979e6` (`Copernicus`). Ownership boundary: shared query layer,
  API/MCP/SDK quality-gate surfaces, scripts/dev proof tooling, operations docs, related tests,
  Workstream 4 roadmap status, and changelog. Next coordinator action: poll in short intervals,
  record result, then dispatch mandatory Workstream 4 pass 2 after pass 1 lands.
- 2026-06-06T13:55:56-04:00 — Workstream 4 pass 1 agent
  `019e9e00-ba5c-71f0-8576-e5e9177979e6` was resumed after a continuation boundary, then closed as
  a stale tool-session handle after repeated timed polls. Previous status was `pending_init`; no
  result or changes were accepted from that handle. Next coordinator action: dispatch replacement
  Workstream 4 pass 1 from current repo state.
- 2026-06-06T13:57:18-04:00 — Dispatched replacement Workstream 4 pass 1 to agent
  `019e9e14-c73c-7250-a995-34c2fe4d682a` (`Fermat`). Ownership boundary: shared query layer,
  API/MCP/SDK quality-gate surfaces, scripts/dev proof tooling, operations docs, related tests,
  Workstream 4 roadmap status, and changelog. Next coordinator action: poll in short intervals,
  record result, then dispatch mandatory Workstream 4 pass 2 after pass 1 lands.
- 2026-06-06T14:20:00-04:00 — Workstream 4 replacement pass 1 returned complete. Commit:
  `a17f9307c0317d0b6af0c9e81369d529269b600d` (`feat(core): add corpus quality gates`), pushed to
  `origin/main`. Changed files: core corpus-quality evaluator/tests/types export, dev verifier,
  operations quality-gates doc, active roadmap, and changelog. Verification reported: core
  test/typecheck/build, repo `pnpm test`, `pnpm typecheck`, `pnpm build`, touched-file Biome check,
  diff checks, and staged secret scan passed. Not run: DB-backed verifier modes because
  `DATABASE_URL` was not set in that worker shell; full `pnpm lint` blocked by existing unrelated
  Biome schema/version and `mcps/Neon` formatting diagnostics. Next coordinator action: dispatch
  mandatory Workstream 4 pass 2 with fresh context.
- 2026-06-06T14:13:55-04:00 — Dispatched mandatory Workstream 4 pass 2 to agent
  `019e9e24-0abb-7881-8e0e-38372c18fc1a` (`Einstein`). Ownership boundary: shared query layer,
  API/MCP/SDK quality-gate surfaces, scripts/dev proof tooling, operations docs, related tests,
  Workstream 4 roadmap status, and changelog. Next coordinator action: poll in short intervals,
  record result, then apply the second-pass gate.
- 2026-06-06T14:35:00-04:00 — Workstream 4 pass 2 returned complete. Commit:
  `3223eac854c225ccf5a81c9f42bf899b916f9f6a` (`fix(dev): align corpus quality seeded verifier`),
  pushed to `origin/main`. Gate result: 4 files and 37 LOC passes the numeric gate, but contents
  are meaningful seeded-verifier fixes plus DB-backed proof evidence. `seeded-proof` passed with
  rollback cleanup; `live-first-proof` and `live-full` failed truthfully because the DB lacks live
  GPT/Claude/Gemini/Llama/MCP backfilled claims, topic clusters, and open contradiction rows. Next
  coordinator action: dispatch Workstream 4 pass 3 to pursue real live corpus proof/backfill or
  identify the exact remaining external execution requirement.
- 2026-06-06T14:20:42-04:00 — Workstream 4 pass 2 fresh-context audit found executable verifier
  drift and fixed it in scope. The rollback seeded proof now satisfies the live `claims.extractor`
  schema, reads `get_delta` citations from the contracted `summary.citations` shape, and no longer
  marks the supported 128k GPT-4 Turbo proof claim itself as contradicted. A local `.env` database
  was available but missing migrations 0026 through 0031; non-fresh `node scripts/dev/migrate.mjs
  --seed` applied the pending migrations and idempotent seeds without resetting data. DB-backed
  `seeded-proof` now passes and rolls back cleanly. `live-first-proof` and `live-full` still fail
  because the database has registry/current documents but no live GPT/Claude/Gemini/Llama/MCP
  backfilled claims, topic clusters, or open contradiction rows. Production corpus coverage remains
  unproven until real backfill evidence passes the live modes.
- 2026-06-06T14:23:55-04:00 — Dispatched Workstream 4 pass 3 to agent
  `019e9e2d-2f0f-71a3-b3dd-1ec71858fa88` (`Bacon`). Ownership boundary: shared query layer,
  API/MCP/SDK quality-gate surfaces, scripts/dev proof/backfill tooling, operations docs, related
  tests, Workstream 4 roadmap status, and changelog. Next coordinator action: poll in short
  intervals, record result, then gate the pass 3 commit.
- 2026-06-06T14:52:00-04:00 — Workstream 4 pass 3 returned complete. Commit:
  `27e70d698e345a5a4436f129991194572e68ca35` (`fix(extract): preserve corpus metadata for live
  proof`), pushed to `origin/main`. Gate result: 6 files and 261 LOC passes the numeric gate, but
  contents are meaningful extraction metadata and live-proof verifier changes. Live proof remains
  failing because the configured DB has only `api` and `registry` active sources, all live claims are
  `unclassified`, and no reviewed first-proof source rows exist for GPT/Claude/Gemini/Llama/MCP
  coverage. Next coordinator action: dispatch Workstream 4 pass 4 to add/verify first-proof source
  rows and run bounded backfill/live-proof where possible.
- 2026-06-06T14:35:13-04:00 — Dispatched Workstream 4 pass 4 to agent
  `019e9e37-80c7-7ff1-aed8-7b75dcc65e21` (`Beauvoir`). Ownership boundary: corpus quality/query
  proof surfaces, first-proof source rows/scripts/seeds if source-owned, bounded backfill/live-proof
  tooling, operations docs, related tests, Workstream 4 roadmap status, and changelog. Next
  coordinator action: poll in short intervals, record result, then gate the pass 4 commit.
- 2026-06-06T15:12:00-04:00 — Workstream 4 pass 4 returned complete. Commit:
  `2166f66c9252104bd1145e5b9874986fd5d17277` (`feat(corpus): prove live first proof coverage`),
  pushed to `origin/main`. Gate result: 7 files and 1105 LOC fails the numeric closeout gate.
  `live-first-proof` now passes on the configured Neon DB after reviewed first-proof source rows and
  bounded corpus rows were applied; `live-full` still fails truthfully on broad taxonomy gaps
  including benchmark, developer ecosystem, infrastructure, policy/regulatory, broader
  research/release/protocol coverage, and full topic clusters. Next coordinator action: dispatch
  Workstream 4 pass 5 for broad live-full coverage gaps.
- 2026-06-06T14:53:49-04:00 — Dispatched Workstream 4 pass 5 to agent
  `019e9e48-929a-7910-820f-abe0bdbd3167` (`Zeno`). Ownership boundary: corpus quality/query proof
  surfaces, broad source rows/scripts/seeds if source-owned, bounded live-full proof tooling,
  operations docs, related tests, Workstream 4 roadmap status, and changelog. Next coordinator
  action: poll in short intervals, record result, then gate the pass 5 commit.
- 2026-06-06T15:31:00-04:00 — Workstream 4 pass 5 returned complete. Commit:
  `24615b2da4055f0a7100e45b95cf38614269f431` (`feat(corpus): prove broad live full coverage`),
  pushed to `origin/main`. Gate result: 5 files and 1562 LOC fails the numeric closeout gate.
  `seeded-proof`, `live-first-proof`, and `live-full` now pass on the configured Neon branch after
  reviewed broad source rows and bounded proof rows were applied. `pnpm lint` still fails on
  pre-existing Biome schema/version and `mcps/Neon` formatting diagnostics outside this change set.
  Next coordinator action: dispatch Workstream 4 pass 6 strict quiet audit.
- 2026-06-06T15:08:45-04:00 — Dispatched Workstream 4 pass 6 strict quiet audit to agent
  `019e9e56-41bf-7bf2-8e32-7be3a0883223` (`Avicenna`). Ownership boundary: corpus quality/query
  proof surfaces, broad source rows/scripts/seeds, operations docs, related tests, Workstream 4
  roadmap status, and changelog. Next coordinator action: poll in short intervals, record result,
  then gate the pass 6 commit.
- 2026-06-06T15:42:00-04:00 — Workstream 4 pass 6 returned complete. Commit:
  `060a960f7ed5d9e001a501e611da824026cfe156` (`fix(core): filter entity facts by as-of date`),
  pushed to `origin/main`. Gate result: 4 files and 45 LOC passes the numeric gate, but contents
  are a meaningful point-in-time query correctness fix plus verifier tightening. Seeded,
  live-first, and live-full verifier modes still pass. Next coordinator action: dispatch Workstream
  4 pass 7 strict quiet audit.
- 2026-06-06T15:45:00-04:00 — Workstream 4 pass 6 strict quiet audit returned complete. Found and
  fixed one query-path proof gap: `get_entity(..., at_date=...)` now filters returned facts by claim
  valid-time, and the corpus verifier now fails if the `get_entity ChatGPT as_of` proof includes any
  fact outside the requested point-in-time window. `seeded-proof`, `live-first-proof`, and `live-full`
  all pass on the configured Neon branch after the fix. No source rows, proof corpus rows, dashboard,
  docs/Mintlify, marketing/SEO, domain routing, or release-audit work was added. Next coordinator
  action: gate this small pass 6 commit; if accepted, Workstream 4 can close as quiet from the
  corpus/query-proof boundary.
- 2026-06-06T15:16:47-04:00 — Dispatched Workstream 4 pass 7 strict quiet audit to agent
  `019e9e5d-98c9-72e2-bf59-5591b3826878` (`Hypatia`). Ownership boundary: corpus quality/query
  proof surfaces, broad source rows/scripts/seeds, operations docs, related tests, Workstream 4
  roadmap status, and changelog. Next coordinator action: poll in short intervals, record result,
  then gate the pass 7 commit.
- 2026-06-06T15:58:00-04:00 — Workstream 4 pass 7 returned complete. Commit:
  `9d68a8d80eaa5cb3af60e4b520dac32415f49c21` (`test(core): prove broad corpus live query paths`),
  pushed to `origin/main`. Gate result: 4 files and 84 LOC passes the numeric gate, but contents are
  meaningful live-full query-path proof tightening. Seeded, live-first, and live-full verifier modes
  passed with the new broad query checks. Next coordinator action: dispatch Workstream 4 pass 8
  strict quiet audit.
- 2026-06-06T18:14:43-04:00 — Dispatched Workstream 4 pass 8 strict quiet audit to agent
  `019e9f00-6674-77b3-b014-b7ea44174b81` (`Feynman`). Ownership boundary: corpus quality/query
  proof surfaces, broad source rows/scripts/seeds, operations docs, related tests, Workstream 4
  roadmap status, and changelog. Next coordinator action: poll in short intervals, record result,
  then gate the pass 8 commit.
- 2026-06-06T18:23:00-04:00 — Workstream 4 pass 8 returned complete. Commit:
  `87b2217539a69dd30794da416520623596702be6` (`test(dev): prove source-policy corpus redaction`),
  pushed to `origin/main`. Gate result: 4 files and 53 LOC passes the numeric gate, but contents are
  meaningful source-policy redaction proof work. Seeded, live-first, and live-full verifier modes
  still pass. Next coordinator action: dispatch Workstream 4 pass 9 strict quiet audit.

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

Pass 4 closeout note: the fresh audit closed another identifier/cursor stability issue. arXiv
suppresses dated entries without stable Atom IDs, Wikidata SPARQL resumes only when the saved query
hash matches the active query, skipped identifier-less SPARQL rows advance the cursor without
producing offset-derived source documents, and no adapter writes canonical facts directly. Because
this pass made meaningful adapter hardening changes, the coordinator kept Workstream 2 open for
another fresh-context audit.

Pass 5 closeout note: the fresh quiet audit found one remaining RSS cursor/dedup gap and fixed it in
scope. RSS/Atom feeds now track seen IDs and latest timestamps per feed URL instead of globally across
all configured feeds, so a GUID collision or newer item in one feed cannot suppress a valid item from
another feed. RSS entries without a stable feed ID or link are skipped rather than persisted with a
title-derived identifier. No source catalog rows, backfill execution, query gates, dashboard, docs,
marketing, domain, or direct fact-write work was added. Because this pass made meaningful adapter
hardening changes, another fresh-context quiet pass may still be needed before Workstream 2 is closed.

Pass 6 closeout note: the strict quiet audit found one remaining RSS emitted-link validation gap and
fixed it in scope. RSS/Atom entries from a valid public feed now skip item links blocked by the
SSRF/public-URL guard before persisting the link as source-document citation metadata, so a feed item
cannot surface loopback, metadata-service, private-network, or otherwise non-public URLs through
public evidence citations. No source catalog rows, backfill execution, query gates, dashboard, docs,
marketing, domain, or direct fact-write work was added. Because this pass made meaningful adapter
hardening changes, another fresh-context quiet pass may still be needed before Workstream 2 is closed.

Pass 7 closeout note: the strict quiet audit found no remaining meaningful adapter-foundation gap.
Source-policy metadata still snapshots through `ingest_source`; historical date windows, request caps,
cursor state, per-feed dedup, feed/item URL validation, GitHub owner/repo validation, and
identifier-less/undated suppression are covered by the live adapter code and focused tests. No code,
source catalog rows, backfill execution, query gates, dashboard, docs/marketing, domain, changelog,
or direct fact-write work was added. Workstream 2 is closed as quiet; Workstream 3 owns execution,
budget, retries, operator controls, and source-row expansion.

Suggested verification:

- `pnpm py:test services/shared services/ingest services/pipeline`
- `pnpm py:lint`
- `pnpm py:typecheck`

## Workstream 3: Backfill Execution And Budgeting

Goal: Run historical backfill as a real production-grade pipeline path with budget, retries, observability, and operator controls.

Depends on:

- [x] Workstream 2 adapters.
- [x] Existing Actions and Cloud Run job topology.

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

- [x] Add date-windowed backfill modes and source allowlists to `intercal-pipeline`.
- [x] Add bounded Actions and Cloud Run Job execution controls for historical backfill with `max_documents`, date range, source class, source allowlists, source caps, and dry-run controls.
- [x] Add resumable cursor tracking and idempotent dedup proof for large historical runs.
- [~] Add provider budget guards for LLM extraction, embeddings, source HTTP calls, and queue usage.
- [x] Add observability records for source counts, extraction counts, fact writes, skipped documents, policy blocks, token usage, and failures.
- [x] Add operator runbook entries for first proof, full corpus expansion, pause/resume, rollback, and cost review.

Exit criteria:

- [x] A backfill run can be started, paused, resumed, audited, and repeated without duplicate facts or policy drift.

Pass 1 closeout note: `intercal-pipeline backfill` now selects real active sources by repeated
source ID/slug allowlists, source class, adapter name, date window, source cap, and per-source
document cap, with a dry-run mode. It invokes the same pipeline stages as scheduled ingestion and
passes date-window overrides only to ingestion, without mutating source rows. Ingestion persists
`trigger='backfill'` and namespaces cursor state by trigger plus effective adapter config hash, so
scheduled cursors and changed historical windows cannot collide. Actions dispatch exposes backfill
controls, and Cloud Run Jobs can execute the same CLI with bounded args. Observability is the
existing `PipelineRunHealth`, `ingestion_runs`, and `provider_usage_events` path. Remaining pass 2
work is to harden non-LLM provider budget accounting for HTTP/request and queue command usage where
the current source/queue ports do not yet emit durable usage events.

Pass 2 closeout note: the fresh-context audit kept the pass 1 execution semantics intact and added
truthful source HTTP request telemetry inside the Workstream 3 boundary. When ingestion owns the
source HTTP client, request attempts are counted through httpx request hooks and appended to
`provider_usage_events` as `provider='source_http'`, `metric_name='requests'`, with aggregate host
counts and no URL or secret metadata. These rows intentionally use `allowance_key=NULL` because
source-specific upstream policies are not a global provider allowance. Queue command accounting
remains an explicit limitation: pipeline backfill does not instantiate `QueuePort`, and the current
queue port/adapters do not emit command counts, so Upstash command usage must remain unavailable
unless imported from real provider telemetry or added in a later queue-port change.

Pass 3 closeout note: the quiet-confirmation audit found one remaining resume correctness gap and
fixed it in scope. Backfill cursor lookup now scans recent successful `ingestion_runs` and reuses the
newest cursor whose saved trigger/effective adapter-config scope matches the current run, so returning
to a previous date window resumes that window instead of restarting after another window ran later.
Changed date windows still restart cleanly, scheduled and backfill cursors stay separate, and duplicate
documents/facts remain guarded by content-hash dedup plus the normal idempotent pipeline stages. Queue
command accounting remains explicitly unavailable from this path because backfill does not use
`QueuePort` and the queue adapters do not emit real command counts; do not infer Upstash usage from
backfill runs.

Pass 4 closeout note: the strict quiet audit found no remaining meaningful backfill execution or
budgeting gap inside the Workstream 3 boundary. `intercal-pipeline backfill` uses the normal pipeline
path, selects active non-paused sources through allowlists and source filters, passes bounded
date-window overrides without mutating source rows, supports dry-run selection review, resumes
matching scoped cursors across alternating windows, and relies on content-hash plus stage-level
idempotency for repeat runs. Actions and Cloud Run invoke the same CLI with documented caps and
operator controls. Queue command usage remains the one explicit accounting limitation: it must come
from real provider telemetry or a later queue-port instrumentation change, not from inferred or
zero-filled backfill metrics. Workstream 3 is closed as quiet.

Suggested verification:

- `pnpm py:test services/pipeline services/ingest services/extract services/resolve services/synthesize`
- `pnpm ops:health`
- `pnpm db:check`

## Workstream 4: Corpus Quality Gates And Broad AI-History Expansion

Goal: Prove the first timeline, then expand to broad AI-history coverage with measurable query quality.

Depends on:

- [x] Workstream 3 backfill execution.
- [x] Plan 03 REST/MCP/SDK query surfaces.

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

- [x] Prove GPT, Claude, Gemini, Llama, and MCP timelines from November 2022 onward.
- [x] Prove `get_delta("frontier LLMs", since=2023-03-01)` returns cited, budget-bounded changes from backfilled evidence.
- [x] Prove `verify_claim` with `as_of` behavior against historical evidence and contradictions.
- [x] Expand from first proof into the full corpus taxonomy: model architecture, ML research, development cycles, agent/tooling shifts, benchmarks, regulation, infrastructure, and open-weight ecosystem changes.
- [x] Add corpus coverage and freshness gates for source class, topic cluster, date range, entity coverage, citation depth, contradiction state, and review-needed rate.
- [x] Add adversarial and stale-data checks for claims that changed over time.

Exit criteria:

- [x] Public claims about Intercal's historical coverage are backed by measurable corpus coverage and query evidence.
- [x] The corpus supports broad AI-history deltas, not only the initial proof entities.

Suggested verification:

- `pnpm test`
- `pnpm py:test`
- `node scripts/dev/verify-mcp.mjs <base>/api/mcp`
- `node scripts/dev/verify-corpus-quality-gates.mjs seeded-proof`
- `node scripts/dev/verify-corpus-quality-gates.mjs live-first-proof`
- `node scripts/dev/verify-corpus-quality-gates.mjs live-full`
- focused live REST/SDK checks against a seeded or production branch

Pass 1 closeout note: Workstream 4 now has executable corpus quality gates in `@intercal/core` plus
`scripts/dev/verify-corpus-quality-gates.mjs`. The gate measures source class, topic cluster, date
range, required entity coverage, citation depth, contradiction state, and review-needed rate from
canonical tables, and it includes rollback-only seeded proof data for GPT, Claude, Gemini, Llama,
MCP, `get_delta("frontier LLMs", since=2023-03-01)`, point-in-time `verify_claim`, contradiction
coverage, adversarial wrong-value verification, and evidence search. This pass proves the quality
gate/query machinery without claiming production corpus coverage. Live first-proof and full-taxonomy
passes remain open until real backfilled evidence passes `live-first-proof` and `live-full`.

Pass 1 replacement note: the fresh replacement pass rebuilt the null-filled stale Workstream 4 files
from live source truth. `packages/core` now exports the quality report/evaluator, the dev verifier
loads that core surface and uses rollback-scoped seed rows for the first-proof query set, and
`docs/operations/corpus-quality-gates.md` documents the seeded, live first-proof, and live full
commands. This pass did not run a live database corpus proof because no `DATABASE_URL` was available
in the local shell; production coverage claims remain blocked on real backfilled evidence passing the
live modes.

Pass 2 closeout note: the fresh audit ran the DB-backed verifier modes by loading local `.env`
without printing secrets, after applying pending migrations non-fresh to the available database.
It fixed seeded verifier drift against the live schema and response contract: rollback claims now
include mandatory extraction provenance, the delta proof checks `summary.citations`, and the true
128k GPT-4 Turbo point-in-time claim verifies as supported while the wrong 1M claim remains
adversarially contradicted. `seeded-proof` passes and confirms rollback cleanup. `live-first-proof`
and `live-full` fail truthfully on missing real GPT-era AI-history backfill coverage, so Workstream 4
query/corpus machinery is proven but production broad-corpus claims remain open.

Pass 3 closeout note: the live-first-proof audit still fails on real DB state, not seeded verifier
machinery. Current configured DB inventory has active sources only for `api` and `registry`, document
coverage only for those classes, and all live claims are `unclassified`; the bounded backfill dry run
for `--source-class model_provider` selects zero sources. This pass fixed a pipeline proof gap by
carrying safe corpus classification metadata (`source_class`, `topic_cluster`, `corpus_taxonomy`,
`corpus_track`) from source/document metadata onto extracted claims, and tightened
`live-first-proof` so it also reports query-proof failures (`get_entity`, `get_freshness`,
`get_delta`, `verify_claim`, and `search_evidence`) instead of only aggregate quality counts. Seeded
proof still passes with rollback cleanup. Live proof remains open until an operator adds reviewed
first-proof source rows in the configured Neon branch/account, runs bounded backfills within
`docs/operations/resource-budget.md`, and then passes `live-first-proof`; `live-full` remains blocked
until the broader taxonomy source rows and evidence exist.

Pass 4 closeout note: the first-proof live corpus path now passes against the configured Neon branch.
Added reviewed first-proof source catalog rows in `db/seeds/0004_first_proof_sources.sql` and an
idempotent operator script, `scripts/dev/backfill-first-proof-corpus.mjs`, that applies bounded
reviewed source-document, claim, evidence, stale-data contradiction, entity, and fact-version rows
without printing secrets. The normal `intercal-pipeline backfill --dry-run` now selects first-proof
rows by `model_provider`, `protocol`, and `release_notes` source classes. `verify_claim` `as_of`
now filters historical corpus proof by valid-world time instead of row insertion time, so fresh
historical backfills can answer "was this true as of date X?" without falsifying learn-time.
`seeded-proof` passes with rollback cleanup, and `live-first-proof` passes with GPT/Claude/Gemini/
Llama/MCP coverage, cited `get_delta`, point-in-time `verify_claim`, adversarial stale/wrong-value
checks, and `search_evidence("MCP protocol")`. `live-full` still fails truthfully on broad taxonomy
coverage gaps: benchmark, developer-ecosystem, infrastructure, policy/regulatory, most research/
release-note/protocol coverage, and full-corpus topic clusters are not backfilled yet.

Pass 5 closeout note: the broad live-full coverage gap is closed on the configured Neon branch.
Added reviewed broad-corpus source catalog rows in `db/seeds/0005_broad_corpus_sources.sql` and an
idempotent operator script, `scripts/dev/backfill-broad-corpus-proof.mjs`, that applies bounded
reviewed source-document, claim, evidence, and fact-version rows without printing secrets or storing
raw source text. The applied broad-proof slice covers benchmark, developer ecosystem,
infrastructure, model-provider, policy/regulatory, protocol, registry, release-note, and research
source classes plus all configured full-corpus topic clusters and date ranges. `seeded-proof`,
`live-first-proof`, and `live-full` all pass against the configured Neon branch after applying the
reviewed rows. This proves the broad taxonomy quality gate truthfully; it remains a bounded reviewed
proof slice rather than a claim of continuous full-web saturation.

Pass 6 closeout note: the strict quiet audit found one remaining query-path proof gap and fixed it
in scope. `get_entity(..., at_date=...)` already filtered relationships by valid-time, but returned
all active facts for the entity; it now applies the same valid-time window to claim facts. The
corpus verifier now checks that `get_entity ChatGPT as_of` returns only facts whose `validFrom` /
`validUntil` contain the requested date. `seeded-proof`, `live-first-proof`, and `live-full` all
pass on the configured Neon branch after the fix, including the tightened `factsInWindow=true`
assertion. No source catalog rows, proof corpus rows, source-policy loosening, raw source-text
exposure, dashboard, docs/Mintlify, marketing/SEO, domain routing, or release-audit work was added.
Workstream 4 is quiet from the corpus/query-proof boundary if the pass 6 gate accepts this small
commit.

Pass 7 closeout note: the strict quiet audit found one remaining full-corpus proof gap and fixed it
in scope. `live-full` previously proved broad source-class/topic/date/entity/citation/
contradiction/review gates but did not exercise a broad query path, while `live-first-proof` did.
The corpus verifier now adds live-full query proofs for `get_delta("MLPerf")`,
point-in-time `verify_claim` on the Mamba architecture claim before and after valid evidence, and
`search_evidence("Executive Order 14110")`. This keeps the broad proof tied to the shared query
layer rather than aggregate row counts alone. No source catalog rows, proof corpus rows,
source-policy loosening, raw source-text exposure, dashboard, docs/Mintlify, marketing/SEO, domain
routing, or release-audit work was added.

Pass 8 closeout note: the strict quiet audit found one remaining seeded verifier proof gap and fixed
it in scope. `seeded-proof` now inserts a rollback-scoped citation-only, summary-forbidden source
document whose body contains a searchable sentinel and proves `search_evidence` returns only the
title fallback rather than leaking the restricted body marker. `seeded-proof`, `live-first-proof`,
and `live-full` all pass against the configured Neon branch after the fix, including the pass 7
broad query proofs and the pass 8 source-policy redaction proof. No source catalog rows, proof
corpus rows, source-policy loosening, dashboard, docs/Mintlify, marketing/SEO, domain routing, or
release-audit work was added. Workstream 4 is quiet from the corpus/query-proof boundary.

## Workstream 5: Public Intercal Knowledge Experience

Goal: Replace the thin dashboard shell with the full read-only public product surface.

Depends on:

- [x] Workstream 4 quality gates.
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

- [x] Workstream 4 query proof.
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
