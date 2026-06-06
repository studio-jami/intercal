# Orchestrator Run Log — 2026-06-04 Program (Phases B–F)

Authoritative resumable ledger for this goal run. Resume from the checkpoint table + `git log`.
Source of truth = live repo. Model policy: pass 1 = Sonnet 4.6, pass 2+ = Opus 4.8.

## Program sequence

- Phase B = Plan 02 (knowledge pipeline, W1→W8 linear) + Plan 07 W3/W4 (worker CD)
- Phase C = Plan 03 (agent surface, W1→W8) + Plan 07 W2 (MCP on Vercel `/api/mcp`)
- Phase D = Plan 04 (operations & trust, W1→W8) + Plan 07 W1/W5/W6/W7/W8
- Phase E = Plan 06 (interactive experience, W1→W10)
- Phase F = Plan 05 (production saturation & release audit, W1→W8)

Independent early unblock: Plan 07 W2 (mount `buildMcpServer()` at dashboard `/api/mcp`) — no pipeline dep.

## Baseline (start of run)

- HEAD: e4acbea — docs(agents): two-model flow. Working tree clean.
- Phase A complete and live (`lntercal.vercel.app`, Neon, REST mounted).
- Plan 02: all 11 Python job bodies = `NotImplementedError("Plan 02 …")`. Not started.
- Plan 03: query layer 4/6 done; `getDelta`/`verifyClaim` = `NotImplementedError("Plan 03")` at `packages/core/src/queries.ts:229,244`. REST+MCP wired but MCP not mounted on Vercel. SDK scaffold only.
- Plan 07: W2 partial (MCP not mounted), W3 partial (cron disabled), rest not started. `scripts/ops/` absent.
- Plans 04/05/06: not started (blocked downstream).

## Checkpoint table

| Time (UTC) | Plan/WS | Pass | Model | Agent id | Status | Commit | Files/LOC | Next action |
|------------|---------|------|-------|----------|--------|--------|-----------|-------------|
| init | — | — | — | orient (Explore) | returned: routing map | — | — | dispatch Plan02 W1 P1 |
| t1 | 02/W1 | P1 | Sonnet | aa95dc43fb7fa77dd | returned OK | 5266e40 | 16f +2006/-91 | dispatch W1 P2 (Opus) |
| t2 | 02/W1 | P2 | Opus | ad0a075bc854532d1 | returned OK; 6 correctness fixes+live verify | 9678e67 | 8f +472/-99 | between B/C → P3 confirm-quiet |
| t3 | 02/W1 | P3 | Opus | a2db3bf161d4a69c7 | QUIET, no change → **W1 CLOSED** | (none) | 0 | nit: score_source_health docstring (defer to cleanup) |
| t4 | 02/W2 | P1 | Sonnet | ad399e2c7066f6a81 | INTERRUPTED (session limit); uncommitted WIP left in tree | (none) | normalizer.py, 0023 migration, test_w2_normalize.py, jobs/cli mods | resume: fresh agent finishes+commits W2 P1 |
| t5 | 02/W2 | P1b | Sonnet | ac26922380c43fbf3 | returned OK; finished WIP, 114 tests, live verify | def4d22 | 8f +1365/-28 | dispatch W2 P2 (Opus) |
| t6 | 02/W2 | P2 | Opus | ae9376898da6376d3 | returned OK; 3 real defects fixed + regression tests + live verify | 77223d6 | 6f ~360 LOC | between B/C → P3 confirm-quiet |
| t7 | 02/W2 | P3 | Opus | aedaa87636eb8bc96 | QUIET → **W2 CLOSED** | (none) | 0 | reorder: W4 before W3 (port-first); W3 note: cleaned_text+document_chunks not normalized_text |
| t8 | 02/W4 | P1 | Sonnet | aaa65c7e07bdf7bf0 | returned OK; LIVE Vertex+fastembed calls pass; 157 tests | a2519ab | 9f +851/-47 | dispatch W4 P2 (Opus) |
| t9 | 02/W4 | P2 | Opus | ac220158f7db48ce6 | returned OK; added schema-validation/error-taxonomy/budget/retries; 181 tests; LIVE Vertex+Gemini+fastembed | 9c3286a | 16f +1346/-235 | FAILS numeric gate (>10f) → P3 re-gate |
| t10 | 02/W4 | P3 | Opus | aa78983a1727ecaaf | returned OK; core path clean; fixed OpenAI-embeddings dim forwarding; 189 tests; LIVE ok | 249443a | ~5f +229/-12 | numeric gate OK; between B/C → P4 confirm-quiet |
| t11 | 02/W4 | P4 | Opus | a491d8db74c415b52 | QUIET → **W4 CLOSED** (4 passes; live Vertex+Gemini+fastembed) | (none) | 0 | begin W3 (LLM port ready) |
| t12 | 02/W3 | P1 | Sonnet | af3b4df490b9d4648 | returned OK; LIVE extract 11 mentions+1 claim w/ spans; 237 tests | 7d146cc | 6f ~2042/-69 | dispatch W3 P2 (Opus) |
| t13 | 02/W3 | P2 | Opus | abde4314d1e327bc0 | returned OK; fixed CRITICAL span-offset corruption + claim under-extraction (thinking_budget=0); dual-provider live verify 0 span failures; 245 tests | a017ef8 | ~5f ~408 LOC | critical fix → P3 confirm-quiet |
| t14 | 02/W3 | P3 | Opus | a3c3a773aced793f5 | INTERRUPTED (session limit 6:20am); uncommitted WIP in jobs.py + test_w3_extract.py | (none) | WIP | resume: fresh agent finishes+commits |
| note | env | — | — | orchestrator | DONE: fixed dev .env SA-key path (forward slashes); Vertex loads from .env (verify_w4 PASS). .env stays uncommitted | — | — | — |
| t15 | 02/W3 | P3b | Opus | ae4784b947f40f87e | returned OK; fixed repeated-span offset defect; 247 tests; live 10/10 span_ok | b3d5bb2 | 3f +120/-8 | another real fix → P4 confirm-quiet |
| t16 | 02/W3 | P4 | Opus | ab7600707edce8104 | QUIET → **W3 CLOSED** (12 probes; invariant architectural) | (none) | 0 | begin W5 |
| t17 | 02/W5 | P1 | Sonnet | aaf2adc8ae2139394 | returned OK; LIVE 5 chunks embedded+HNSW+hybrid_search; 275 tests | 870b69f | 6f ~1191 LOC | dispatch W5 P2 (Opus) |
| t18 | 02/W5 | P2 | Opus | a212ff5cc6325a159 | returned OK; fixed hnsw.ef_search recall bug; EXPLAIN confirms index; TS searchEvidence lexical-only (no drift, vector=Plan03); 276 tests | 266d97f | 4f +211/-9 | real fix → P3 confirm-quiet |
| t19 | 02/W5 | P3 | Opus | a7c6e8c5726bb0f84 | QUIET → **W5 CLOSED** | (none) | 0 | begin W6 |
| t20 | 02/W6 | P1 | Sonnet | a3616873021bb93db | returned OK; LIVE 11 entities/3 review/0 false-merge/idempotent; gate satisfied; 309 tests | bbc5d3f | 6f ~2000 LOC | dispatch W6 P2 (Opus); check merge path |
| t21 | 02/W6 | P2 | Opus | aa682e3d5163d2101 | returned OK; found merge path was DEAD CODE + fixed mentions.updated_at bug; merge/non-merge/idempotency proven; 314 tests | cff37de | 4f +387/-36 | major fix → P3 confirm-quiet |
| t22 | 02/W6 | P3 | Opus | a18fb8e21db663cf1 | QUIET → **W6 CLOSED** (merge/non-merge/review/idempotency re-proven) | (none) | 0 | begin W7 |
| t23 | 02/W7 | P1 | Sonnet | a6c7313ba4b03ae8f | returned OK; LIVE 1 rel + 13 fact versions, append-only/bitemporal proof, idempotent; 333 tests. FLAG: directly inserted a claim "to satisfy gate" | 2c1dfa4 | 6f +1617/-45 | P2 scrutinize seeded-claim + nat. derivation |
| t24 | 02/W7 | P2 | Opus | a08d977a1d38fb52a | returned OK; CAUGHT pass-1 synthetic claim, removed it, restored honest state; proved W7 correct on REAL GitHub-releases pipeline (42 real claims→real rel, bitemporal+PIT+idempotent proof); docs honesty fix | 9dc317c | 1f +43/-14 | P3 confirm-quiet; then claim-link fix |
| t25 | 02/W7 | P3 | Opus | a9f3ad8b83664a83d | QUIET → **W7 CLOSED** (proven on 76 real claims; skips-not-fabricates confirmed) | (none) | 0 | begin GAP-A claim-link |
| t26 | 02/GAP-A | P1 | Sonnet | a33b68e5f356be65c | returned OK; `link_claim_entities` bridges claim→entity; LIVE real Vertex 5 claims→2 linked→1 rel end-to-end, idempotent; 345 tests | 16cd7df | 5f +947 | dispatch GAP-A P2 (Opus) |
| t27 | 02/GAP-A | P2 | Opus | ab90c5bc0e723aeeb | returned OK; fixed corruption-class ambiguity defect (same-name distinct entities); rust-lang/rust 151 claims→4 real rels; adversarial no-false-link proven; 346 tests | 12229fa | ~4f +20/-35 | corruption fix → P3 confirm-quiet |
| t28 | 02/GAP-A | P3 | Opus | af565c37bb53ec0bc | INTERRUPTED (Opus session limit, 3rd occurrence); no change committed (tree clean) | (none) | 0 | re-dispatch P3 on Sonnet |
| t29 | 02/GAP-A | P3 | Sonnet | abc22666e81571200 | QUIET → **GAP-A CLOSED** (match-order/floors/idempotency/provenance verified; adversarial no-false-link re-proven; 346 tests) | (none) | 0 | begin W8 |
| t30 | 02/W8 | P1 | Sonnet | — | dispatch REJECTED by user (inserted GAP-B first) | — | — | do GAP-B then resume W8 |
| t31 | GAP-B | P1 | Opus | ae86a05519f5e7334 | returned OK; recordedAt←created_at (opt a), live getEntity proof; closed | 92ad2b0 | 7f +119/-4 | **GAP-B CLOSED** |
| t32 | 02/W8 | P1 | Opus | a8719e19b12ef1556 | returned OK; fixed WIP (import/env, health keys, batch-drain idempotency); FULL PIPELINE LIVE ON PROD NEON (155 ent/260 review/6 rel/155 fv, idempotent); **REAL DATA ON LIVE API** (entity+rel+evidence+freshness) — Phase B gate MET | 2918a53 | ~2315 LOC | dispatch W8 P2 (Opus) |
| t33 | 02/W8 | P2 | Opus | af89b78d5e6cc8d89 | returned OK; fixed link-drain early-stop idempotency defect (offset paging); idempotency/paging/partial-failure/heartbeat re-proven; prod data legit (real Node/Rust/K8s LLM extraction); 373 tests | 5c8788f | 6f +160/-19 | real fix → P3 confirm-quiet |
| t34 | 02/W8 | P3 | Opus | a04669513e96f0f16 | QUIET → **W8 CLOSED; PLAN 02 / PHASE B FULLY COMPLETE** (idempotent, real data on live API) | (none) | 0 | open Phase C |

### ✅ PHASE B COMPLETE — Plan 02 (all 8 WS + claim-link bridge). HEAD 5c8788f. Real data live on `lntercal.vercel.app` `/v1/*`.
Cosmetic carry: synthesize jobs.py docstring "Raises … Plan-02 scope" lines vs correct Plan 03/04 exception strings — sweep in cleanup.
Plan 02 dated plan flagged for retirement to `docs/_legacy/roadmaps/` — do at Phase F with migration consolidation.

## Phase C — Plan 03 (agent surface) + Plan 07 W2 (MCP on Vercel)

Plan 03 workstreams: W1 query layer · W2 REST · W3 MCP · W4 SDK · W5 digest/token-budget (getDelta body) · W6 claim verification (verifyClaim body) · W7 freshness/coverage · W8 agent fixture.
Much of W1–W3 already scaffolded (4/6 query fns live; REST+MCP wired). Key new work: getDelta + verifyClaim bodies, MCP mount at `/api/mcp` (Plan 07 W2), SDK methods, fixture. GAP-B (claims recordedAt) already fixed at 92ad2b0.

| t35 | 03/W1 | P1 | Sonnet | aefac10cbd04d2708 | returned OK; merged-id→resolve-to-survivor; fixed mapRelationship status bug; live REST proof; 10 tests | d4f0567 | 6f +221/-17 | dispatch W1 P2 (Opus) |
| t36 | 03/W1 | P2 | Opus | a3a3be31eaa6bd15a | returned OK; fixed contract-divergence (mapEntity externalIds.url); consumer parity confirmed; resolveIfMerged verified; contracts:check clean; 12 tests | b31dbba | ~4f +75 | real fix → P3 confirm-quiet (Sonnet) |
| t37 | 03/W1 | P3 | Sonnet | abd648f31e00c5398 | QUIET → **W1 CLOSED** (mappers contract-exact, resolveIfMerged on all id paths, parity, contracts clean) | (none) | 0 | parallel W2+W3 |
| t38 | 03/W2 | P1 | Sonnet | a7518bbdb1d604c7b | INTERRUPTED (session limit, Sonnet — limits are account-wide throughput, not model-specific); WIP: app.ts mod + app.test.ts new | (none) | WIP | resume: finish+commit |
| t39 | 03/W3 | P1 | — | — | NOT actually dispatched (only W2 call sent); deferred until W2 lands | — | — | dispatch after W2 |
| note | GAP-B | — | — | orchestrator | chip resurfaced but STALE — already fixed at 92ad2b0 (claims created_at/updated_at, orderBy created_at). No action. | — | — | — |
| t40 | 03/W2 | P1b | Sonnet | — | REJECTED by user (model-policy change → all-Opus) | — | — | re-dispatch on Opus |
| t41 | 03/W2 | P1b | Opus | a4c6d7cb3a4f6b5a2 | returned OK; fixed 2 prod defects (sources 500, unknown-param 200), error taxonomy+CORS, 37 tests | eb7edcd | ~5f +535/-31 | dispatch W2 P2 (Opus) |
| t42 | 03/W2 | P2 | Opus | adac36f5db614154e | returned OK; fixed mounted-prefix text/plain-404 leak (scoped /v1/* JSON catch-all); 40 tests; deployed-404 fix pending Vercel redeploy | 9ae1cc7 | 4f +105/-2 | real fix → P3 confirm-quiet |
| t43 | 03/W3 | P1 | — | — | CORRECTION: NOT actually dispatched (call never sent, logged in error twice) | — | — | dispatch now |
| t44 | 03/W2 | P3 | Opus | a8455717ff14b5380 | QUIET → **W2 CLOSED** (404-fix propagated to prod; /api/mcp non-intercept confirmed) | (none) | 0 | dispatch W3 |
| t45 | 03/W3 | P1 | Opus | ad87a2ec5d07878af | returned OK; MCP hardened + MOUNTED /api/mcp (Plan07 W2 too); LIVE Streamable-HTTP init+tools/list+get_entity+search_evidence on prod Neon; SDK 1.29.0 WebStandard transport, stateless Node runtime; 9 mcp tests | 7df103a | ~505 LOC | dispatch W3 P2 (Opus); verify live Vercel |
| t46 | 03/W3 | P2 | Opus | ad1aec87c130fa62d | non-terminal return (parked on deploy wait) BUT committed deploy-determinism fix; ORCHESTRATOR-VERIFIED live: deployed /api/mcp initialize+tools/list(6)+get_entity rust real data on prod | aa5f472 | deploy fix | real fix → P3 confirm-quiet (serverless pool) |
| t47 | 03/W3 | P3 | Opus | ae91853c468a34aa6 | QUIET → **W3 CLOSED + Plan07-W2 CLOSED** (pool=safe singleton, stateless, parity, deployed live w/ real data) | (none) | 0 | parallel W4+W5 |
| t48 | 03/W4 | P1 | Opus | a9ce0cfae8f5e6559 | returned OK; full typed SDK (6 methods, error model, fixture+live tests, delta/verify→typed 501); 19 tests | 9079b55 | ~6f +778/-78 | needs P2 |
| t49 | 03/W5 | P1 | Opus | ae696af1efbcd0365 | returned OK; getDelta = deterministic fully-cited token-bounded digest; LIVE prod 12 cited/315tok≤600, clamp/trim proven, empty=no-fab; retargeted stale delta-501 tests; 22 core tests | aa93079 | ~8f +760/-83 | needs P2 |
| t50 | 03/W5 | P2 | Opus | a3cdca8b394cd7e4c | returned OK; CRITICAL: pass1 missed fact_version changes (canonical change unit); now windows fact_versions on recorded_at + supersession classification; token math hardened; live supersession-across-cutoff proof; 26 core tests | 8991793 | 5f +349/-43 | critical fix → P3 confirm-quiet |
| t51 | 03/W5 | P3 | Opus | ae90d8d9a7a5283be | returned OK; fixed supersession-vs-new MISclassification across cutoff (priorVersionSubjectIds signal); live-proven; deployed /api/v1/delta real data; 28 core tests | cd104ae | ~3f +97 | another bitemporal fix → P4 confirm-quiet |
| t52 | 03/W5 | P4 | Opus | a0f3b0b2fb971f4f5 | returned OK; fixed until-clamp wrongly constraining independent fact-version axis (bounded-case drop); live 0→1; 28 core tests | 819dfd1 | 1f ~15 LOC | 4th bitemporal fix → P5 confirm-quiet+test-matrix |
| t53 | 03/W5 | P5 | Opus | a7cb27dfe91277375 | QUIET on logic + added bitemporal test matrix (16→25); live boundary µs-verified → **W5 CLOSED** | 6adddc6 | 1f +177 (tests) | back to W4 P2 |
| t54 | 03/W4 | P2 | Opus | ad31fab6d5558c2fd | QUIET → **W4 CLOSED** (SDK contract-aligned, error model, live getDelta real data + verify 501; 19 tests) | (none) | 0 | begin W6 |
| t55 | 03/W6 | P1 | Opus | aee978196298e6be6 | returned OK; verifyClaim = deterministic cited evidence-match+contradiction, point-in-time, token-budgeted; LIVE supported/unverified/as_of cases; 50 core tests | 190a496 | ~8f +913/-96 | P2: scrutinize false-positive support |
| t56 | 03/W6 | P2 | Opus | af4e9b38cc3e68237 | returned OK; CONFIRMED false-positive-support defect (lexical overlap→false supported, proven live role-swap); fixed (strong symmetric coverage≥0.85+Jaccard≥0.5 for supported, else partially_supported); +5 adversarial tests; 55 tests | 49bf87a | 4f +256/-6 | integrity fix → P3 confirm-quiet |
| t57 | 03/W6 | P3 | Opus | a3fe78cb444234d90 | returned OK; fixed tokenizer edge-punctuation artifact (verbatim restatement → supported); citation integrity 0 dangling/114 claims; +2 tests; 57 core | fb9ac4e | ~2f +44 | minor safe-dir fix → P4 confirm-quiet |
| t58 | 03/W6 | P4 | Opus | a96a54e955535a231 | QUIET → **W6 CLOSED** (adversarial-safe, deployed fixed verify live; 57 core tests) | (none) | 0 | begin W7 |
| t59 | 03/W7 | P1 | Opus | acb6be278c2b0ef2a | returned OK; getFreshness now fills coverage field (freshness+coverage, no contract change); LIVE covered→real, unknown→no-data; 69 core tests | ec7caaf | 5f | dispatch W7 P2; assess coverage-metric soundness |
| t60 | 03/W7 | P2 | Opus | ad91b0ea5a53e6793 | returned OK; REDEFINED coverage (pass1's metric dishonest — all 52 entities=0.333; now evidence-depth, corpus-invariant); staleness justified vs cadence; live-verified; 71 core tests | b50a5a2 | 5f +274/-92 | honesty fix → P3 confirm-quiet |
| t61 | 03/W7 | P3 | Opus | a0d5a2e62d5a18303 | returned OK; fixed provenance gap (coverage read denormalized source_document_ids not canonical claim_evidence); live 114/114 identical but now authoritative; 71 core tests | 287bed4 | ~3f +20net | provenance fix → P4 confirm-quiet |
| t62 | 03/W7 | P4 | Opus | a61f99d022c0ec1e6 | QUIET → **W7 CLOSED** (evidence-depth coverage canonical, recency, honest gaps, contract-exact; 71 core tests) | (none) | 0 | begin W8 |
| t63 | 03/W8 | P1 | Opus | ae448aef15f194139 | returned OK; agent-fixture harness: 6 tools × (MCP client + SDK/REST), cited/conf/budget asserts, cross-path byte-equiv, env-gated LIVE; acceptance gate PROVEN live; 21 mcp tests | 6f7b630 | ~8f +903/-32 | dispatch W8 P2 |
| t64 | 03/W8 | P2 | Opus | ad61818be3965b912 | QUIET → **W8 CLOSED; PLAN 03 / PHASE C COMPLETE** (live acceptance gate 23/23 both paths) | (none) | 0 | open Phase D |

### ✅ PHASE C COMPLETE — Plan 03 (W1–W8) + Plan 07 W2 (MCP on Vercel). getDelta + verifyClaim live & cited/budgeted; MCP at /api/mcp; SDK; freshness/coverage. Plan 03 flagged for retirement (do at Phase F).

## Phase D — Plan 04 (operations & trust) + Plan 07 (remaining: W1 secrets, W3/W4 worker CD, W5 API keys, W6 MCP OAuth, W7 backups, W8 budget)

Plan 04 WS: W1 auth+rate-limits · W2 source policy/SSRF · W3 audit events · W4 feedback/review · W5 subscriptions · W6 observability · W7 deployment paths+backups · W8 account/CLI runbook.
Plan 07 remaining: W1 secret fan-out (prereq for W3/W4/W5/W6/W7/W8; scripts/ops/ absent) · W3 Actions scheduled CD · W4 Cloud Run Jobs · W5 REST API keys · W6 MCP OAuth 2.1 · W7 backups/restore · W8 budget enforcement.
Sequence: Plan 07 W1 (secrets) first → then auth cluster (Plan04 W1 + Plan07 W5/W6) ∥ worker CD (Plan07 W3/W4) → Plan04 W2–W8 → Plan07 W7/W8.

| t65 | 07/W1 | P1 | Opus | a33c69cfcfe1744b7 | returned OK; scripts/ops/secrets-fanout.mjs + manifest; LIVE Vercel(4)+GitHub Actions(24) confirmed; Cloud Run deferred(W4); no value leak; lane-separated | 8d94d9e | ~6f +873/-6 | dispatch W1 P2 |
| t66 | 07/W1 | P2 | Opus | ad824984942d9c766 | returned OK; leakage scan CLEAN; lane-sep hardened in schema; fixed GCLOUD_REGION mis-lane; idempotency live-verified | 121405b | 4f +30/-9 | minor fix → P3 confirm-quiet |
| t67 | 07/W1 | P3 | Opus | a8f148f4fadf8234b | QUIET → **W1 CLOSED** (zero leakage, lane-sep double-enforced, idempotent, live-verified Vercel 4 + GitHub 25) | (none) | 0 | begin REST auth stream |
| t68 | 07W5+04W1(REST) | P1 | Opus | a7d06e3b22fdc2d73 | returned OK; hashed scoped API keys + RateLimitStorePort(Upstash+fallback) + usage_events + anon policy + ops:keys CLI; LIVE 17/17 throwaway branch; 24 tests | a8916b1 | 29f +1951/-23 | gate P2: timing-safe, RL races/headers, XFF trust, anon+MCP unbroken |
| t69 | 07W5+04W1(REST) | P2 | Opus | a6ff4ffed7e3901f2 | INTERRUPTED (session limit 10:10pm, now reset); no change committed | (none) | 0 | re-dispatch P2 |
| t70 | 07W5+04W1(REST) | P2 | Opus | afb695778bf0c5897 | returned OK; fixed 3 security bugs (spoofable XFF left-most→trusted IP, RL TTL-loss lockout self-heal, IPv6 :: anonymization); timing-safe confirmed; MCP bypasses REST mw; anon ok; 140 tests | 58fb16d | 8f +273/-22 | security fixes → P3 confirm-quiet |
| t71 | 07W5+04W1(REST) | P3 | Opus | ad418d8a6629e6155 | QUIET → **REST AUTH STREAM CLOSED** (Plan07 W5 + Plan04 W1 REST). Orchestrator-confirmed LIVE on lntercal: anon 200 + RateLimit-Limit:30, invalid key→401. (P3's 404 was wrong hostname `intercal` vs `lntercal`.) | (none) | 0 | begin MCP OAuth W6 |
| t72 | 07/W6 | P1 | Opus | a7e9c8e1573aab9e5 | returned OK; MCP OAuth2.1 resource server (jose JWKS, RFC9728 PRM, WWW-Auth 401/403, RFC8707 aud binding); AS = env seam (deferred honestly); anon-read preserved when no AS; spec-verified 2025-06-18/11-25; LIVE 7/7; 88 mcp tests | ea5b8b0 | ~12f +1336 | gate P2: spec compliance + no bypass |
| t73 | 07/W6 | P2 | Opus | a38a8453f357e0b89 | returned OK; fixed JWS alg-allowlist gap (alg-substitution; PS256-vs-RSA); MCP_OAUTH_ALGORITHMS default RS256; no-bypass+PRM+aud confirmed; LIVE 8/8 | dba6b87 | 9f +169/-15 | security fix → P3 confirm-quiet |
| t74 | 07/W6 | P3 | Opus | a940b6e4ba6b30ab0 | QUIET (only trivial lint sweep) → **W6 CLOSED** (MCP OAuth RS spec-correct, no bypass); LIVE 8/8 | f04d053 | 1f | **AUTH COMPLETE** (REST keys + MCP OAuth) → worker CD |
| t75 | 07/W3 | P1 | Opus | a9afb155f58c581bc | returned OK; scheduled CD (6h cron, caps, concurrency, perms, ADC); PROVEN via gh runs GREEN on Neon branch + PROD (idempotent, 5 new docs, no dupes); flagged W4 Dockerfile extras gap | 907b1d9,3b23bf3,54a347b | 5f ~340 | dispatch W3 P2 |
| t76 | 07/W3 | P2 | Opus | ab9e09ea36d646d61 | returned OK; fixed SA-key temp-file cleanup (if:always); 5 dims re-gated clean; actionlint clean | 677219a | 4f +78/-1 | minor → P3 confirm-quiet |
| t77 | 07/W3 | P3 | Opus | a29b41dd44167988c | QUIET → **W3 CLOSED** (scheduled CD live 6h, actionlint clean, secret-safe) | (none) | 0 | begin W4 Cloud Run |
| t78 | 07/W4 | P1 | Opus | aca26e3c11db24ba6 | returned OK; Cloud Run Job LIVE+PROVEN (exec r9vgn succeeded, real data landed); image→AR, least-priv SA+WIF Vertex, Secret Manager, deploy script+CD workflow; FIXED critical secrets-in-logs (DSN/Upstash redaction across all runners) | fc3785b | 14f +827/-20 | gate P2: SA/secrets/redaction/job config |
| t79 | 07/W4 | P2 | Opus | a9e2b7d97ed63bed0 | returned OK; CRITICAL: pass1 proof ran pre-redaction image → leaked Neon DSN to Cloud Logging (shared neondb_owner pw). PURGED logs, re-verified clean, re-ran fixed image hnwdm (redacted). All else clean. Recommends pw rotation | ae56e37 | 2 docs +105/-7 | ROTATE creds → then W4 P3 |
| t80 | SEC/rotate | P1 | Opus | ae087e378a6c3263f | DONE; Neon pw rotated in place, re-fanned all targets (Vercel/Actions/SecretMgr v2), OLD CRED DEAD, LIVE REST/MCP/pipeline green on new creds; runbook doc | 1ea3120 | 1 doc | exposure CLOSED → W4 P3 |
| t81 | 07/W4 | P3 | Opus | aae4b1a34c327ff27 | QUIET → **W4 CLOSED** (Cloud Run Jobs CD secret-safe, redaction complete, SA least-priv, no double-schedule; live redacted+green) | (none) | 0 | **WORKER CD DONE** → Plan04 W2 |
| t82 | 04/W2 | P1 | Opus | a2102e62d74513a52 | returned OK; SSRF guard (hostile matrix, DNS-rebind socket-pin, redirect re-validate, body cap) + source policy (summary_allowed gate, mig 0025); 41 SSRF tests; live github 200 / metadata+private blocked; 419 py tests | cb0307a | 14f +1192/-27 | gate P2: SSRF bypass + policy e2e |
| t83 | 04/W2 | P2 | Opus | af5b0c7a2bd3e82b0 | returned OK; fixed SSRF body-cap-not-enforced-on-adapter-path (mem exhaustion); cap in transport stream+CL; 52 SSRF tests; policy e2e + live snippet-gate 5/5; no bypass found | 73ce036 | 6f +457/-15 | security fix → P3 confirm-quiet |
| t84 | 04/W2 | P3 | Opus | abfb60fe1bb26d475 | QUIET → **W2 CLOSED** (SSRF no-bypass adversarial-verified; source policy e2e; live snippet-gate) | (none) | 0 | Plan04 W3 audit |
| t85 | 04/W3 | P1 | Opus | ac9677807fb46b65a | returned OK; append-only audit_events (mig 0026 trigger-enforced), recordAuditEvent+redaction, wired key issue/revoke in-tx, deferred seams; LIVE 14/14 no-secrets+mutation-rejected; 98 core tests | 729fd53 | 13f +881/-49 | gate P2 |
| t86 | 04/W3 | P2 | Opus | a0c7fea16251bdd5f | returned OK; fixed TRUNCATE-bypass (mig 0027 BEFORE TRUNCATE) + redaction gaps (dsn/conn-string/renamed); atomicity confirmed; LIVE 15/15 (U/D/TRUNCATE rejected); 99 core tests | 433f8af | 9f +175/-22 | integrity fixes → P3 confirm-quiet |
| t87 | 04/W3 | P3 | Opus | — | stale/non-resumable checkpoint from prior Claude-side session; no agent id | — | — | replaced by Codex checkpoint t88 |
| t88 | 04/W3 | P3 | inherited | 019e9b5e-21c6-7880-82ec-ee61b34af2ef | dispatched 2026-06-06T05:18Z; replacement confirm-quiet/re-gate pass for audit events; ownership: packages/core auth/audit, db audit migrations, audit docs/tests | — | — | poll until terminal, then gate W3 |
| t88r | 04/W3 | P3 | inherited | 019e9b5e-21c6-7880-82ec-ee61b34af2ef | returned OK; docs/comment alignment only; core audit tests 99 + typecheck + diff-check passed; pushed | c4a2113 | 6f +15/-10 | numeric gate OK + class C -> **W3 CLOSED** |
| t89 | 04/W4 | P1 | inherited | 019e9b5d-9e84-7201-b48f-5ad044ec376a | dispatched 2026-06-06T05:17Z; feedback/review records; ownership: contracts/API/core/db/review docs/tests as needed | — | — | poll until terminal, then dispatch W4 P2 |
| t90 | 04/W4 | P1 | inherited | 019e9b5e-826b-7483-91c9-c061f3c2c33d | duplicate dispatch detected and closed immediately; no work should be used from this agent | — | — | ignore; keep t89 as active W4 |
| t91 | 04/W5 | P1 | inherited | 019e9b5f-191b-70c1-a1de-f1012c0a5ac1 | dispatched 2026-06-06T05:19Z; subscriptions; ownership: subscription contracts/API/core/db/docs/tests, no W4/W7 edits except tiny references | — | — | poll until terminal, then dispatch W5 P2 |
| t92 | 07/W7 | P1 | inherited | 019e9b5f-744c-75b3-b759-ef27dce507ea | dispatched 2026-06-06T05:19Z; backups/restore proof; ownership: backup docs/scripts/package scripts/env examples/change fragment | — | — | poll until terminal, then dispatch W7 P2 |
| t89r | 04/W4 | P1 | inherited | 019e9b5d-9e84-7201-b48f-5ad044ec376a | returned with implementation complete but uncommitted due W4/W5 generated-contract/API interleaving; verification broad green (`pnpm contracts:build`, lint/typecheck/test/build, py gates, diff-check); DB migration not run because shell DATABASE_URL unset | — | WIP interleaved | dispatch combined W4/W5 integration/staging worker, then W4 P2 |
| t91r | 04/W5 | P1 | inherited | 019e9b5f-191b-70c1-a1de-f1012c0a5ac1 | returned with subscription implementation complete but uncommitted due W4/W5 interleaving; verification broad green (contracts build, TS checks/tests/builds, lint, py gates); db:check blocked by unapplied migrations and unknown DB target; contracts:check expected drift pre-commit | — | WIP interleaved | dispatch combined W4/W5 integration/staging worker, then W5 P2 |
| t92r | 07/W7 | P1 | inherited | 019e9b5f-744c-75b3-b759-ef27dce507ea | returned OK; backup/restore script+runbook+aliases+env placeholders; verification help/dry-run/biome/diff-check; real dump/restore unavailable (pg_dump/pg_restore/aws not on PATH, no throwaway target DSN); pushed | 77da587 | 10f +539/-8 | numeric gate OK; implementation pass -> dispatch W7 P2 |
| t93 | 04/W4+W5 | P1 integration | inherited | 019e9bb8-e241-7221-9de5-44bf368be058 | dispatched 2026-06-06T06:09Z; integrate/stage/commit interleaved W4 feedback + W5 subscriptions P1 work without expanding scope; ownership: current W4/W5 WIP, generated contracts, tests/docs/checkpoints | — | — | poll until terminal, then dispatch W4 P2 and W5 P2 as appropriate |
| t93r | 04/W4+W5 | P1 integration | inherited | 019e9bb8-e241-7221-9de5-44bf368be058 | returned OK; combined W4 feedback/review records + W5 subscriptions committed together; contracts build/check, touched package typechecks/tests, package build, pyright 0 errors, scoped Biome, staged diff-check green; db:check unavailable because no verified throwaway DB target (process DATABASE_URL unset, docker not on PATH, .env not used) | integration commit | 47f +3883/-29 | dispatch W4 P2 and W5 P2 |
| t94 | 07/W7 | P2 | inherited | 019e9bb9-3686-78d0-950a-2509d8a1182f | dispatched 2026-06-06T06:09Z; fresh-context backup/restore audit; ownership: W7 backup script/docs/package/env/changelog only | — | — | poll until terminal, then gate W7 |

**Phase D progress:** Plan07 W1✅,W3✅,W4✅,W5/04W1-REST✅,W6✅ · Plan04 W2✅ | remaining: Plan04 W3 audit, W4 feedback, W5 subs, W6 observability, W7 deploy-paths/backups(+Plan07 W7), W8 runbook; Plan07 W8 budget.

**Phase D progress:** Plan07 W1✅ secrets · REST-auth✅ · W6✅ MCP OAuth · W3✅ Actions CD · W4✅ Cloud Run | remaining: Plan07 W7 backups, W8 budget; Plan04 W2 source-policy/SSRF, W3 audit, W4 feedback, W5 subs, W6 observability, W7 deploy-paths/backups, W8 runbook.

**Carry-forward (cross-platform):** scripts/ops fan-out/deploy use `execFile('gcloud',…)` → ENOENT on Windows (.cmd shim) for `--target cloudrun`; fix before a Windows operator uses it (Cloud Run secrets currently via Secret Manager direct).

**Phase D progress:** Plan07 W1✅ secrets · REST-auth✅(W5+Plan04W1-REST) · W6✅ MCP OAuth | remaining: Plan07 W3 (Actions CD), W4 (Cloud Run Jobs), W7 (backups), W8 (budget); Plan04 W2 source-policy/SSRF, W3 audit, W4 feedback, W5 subs, W6 observability, W7 deploy-paths, W8 runbook.

**Phase D consolidation note:** REST auth (Plan07 W5 hashed scoped API keys) + rate limits (Plan04 W1 REST portion) done as ONE coherent middleware stack. MCP OAuth = Plan07 W6 (separate). Plan04 W1 MCP-rate-limit folded into W6.

**Carry-forward (later seam, Plan 05/enhancement):** verifyClaim role-swap calibration limit — a token-identical role-swap with a near-identical 2nd candidate can grade `supported`; closing needs semantic parsing behind `LlmPort`. Documented, not a blocker.

**Carry-forward (hardening):** MCP SDK `tools/call` doesn't validate args vs inputSchema → missing required arg = internal_error not invalid_request. Fold into a later hardening pass (W5/W6 surface or Plan 05).
**Phase C progress:** W1✅ W2✅ W3✅(+MCP live) | remaining: W4 SDK, W5 getDelta, W6 verifyClaim, W7 freshness/coverage, W8 fixture.

**Parallel note:** W2 (packages/api) and W3 (packages/mcp-server) independent, both on completed W1 query layer. W3 dispatch also covers Plan 07 W2 (mount MCP at dashboard `/api/mcp`).

**MODEL POLICY ADAPTATION:** Opus session limits hit 3× (1am/6:20am/12pm resets) = real throughput blocker. Confirm-quiet passes now on Sonnet; reserve Opus for primary defect-finding pass-2 audits, fall back to Sonnet if Opus rate-limited. Deviation logged per dispatch.

**Phase B progress:** W1✅ W2✅ W4✅ W3✅ W5✅ W6✅ W7✅ | remaining: GAP-A (claim→entity linking), W8 (orchestration/fixture heartbeat) + Plan07 W3/W4 (worker CD).

**MUST-ADDRESS gaps (do not settle):**
- **GAP-A (claim-end entity linking, W3/W6):** W3 leaves `claims.subject/object_entity_id` NULL and claim surface forms differ from mention spans → real pipeline derives ~0 relationships. Dispatch a focused W3/W6 wiring fix BEFORE W8 so relationships flow naturally end-to-end.
- **GAP-B (Plan 03 carry):** `ClaimsTable` TS type declares `recorded_at` but claims SQL lacks it → `getEntity` orderBy('recorded_at') runtime failure. Fix in Plan 03 query-layer pass.

**Carry-forward to Plan 04:** entity-merge reversal fidelity — exact-collision case leaves `moved_external_id_ids` empty (survivor already holds the ID); fine today, matters for the not-yet-built reversal path.

**Carry-forward to Plan 03 (query layer):** getEntity direct-by-UUID lookup of a merged-away id returns the deprecated row without chasing `merged_into_id` — decide redirect vs 410 in Plan 03.

**Phase B progress:** W1✅ W2✅ W4✅ W3✅ | remaining: W5, W6, W7, W8 + Plan07 W3/W4 (worker CD).

**Reorder note:** Phase B order adjusted to W1,W2,**W4**,W3,W5,W6,W7,W8 — W4 (LLM+embeddings ports) is a real dependency of W3 (extraction calls LLM); building W3 first would require a forbidden mock.

## Notes / blockers

- **MANDATORY Phase F (Plan 05) deliverable — migration consolidation (user-requested 2026-06-05):**
  `db/migrations/` has grown to 20+ incremental files and will exceed 30 by program end. Before release,
  consolidate into ONE clean canonical schema set (e.g. a squashed baseline + seeds), retiring the
  incremental history. MUST NOT be done mid-stream — live Neon branches + migration runner depend on the
  incremental files. Schedule as an explicit Plan 05 workstream task. Verify the canonical set migrates a
  fresh DB to byte-identical schema vs the incremental chain before retiring the old files.
- **Model policy (UPDATED 2026-06-05, user directive):** **ALL passes = Opus 4.8** (pass 1, audits, confirm-quiet).
  User observed Sonnet producing more failed commands/issues; Opus runs clean and catches the real defects.
  Session-limit pauses are account-wide throughput (hit both models) — resume from repo state, no work lost.
  Supersedes goal.md's Sonnet-p1/Opus-p2 default per explicit user instruction.
