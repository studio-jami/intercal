# Plan 03 W8 — full-surface agent/contract harness (Phase C acceptance gate)

Date: 2026-06-06
Type: test
Packages: @intercal/mcp-server, @intercal/sdk

## Summary

Added the Plan 03 Workstream 8 agent/contract harness — the repeatable test that proves the Phase C
ACCEPTANCE GATE: an AGENT (MCP) and a CLIENT (SDK/REST) both drive the complete V1 surface (all six
tools/endpoints) and get responses that are, against the generated contract, WELL-FORMED, CITED
(provenance present), CONFIDENCE-scored, and BUDGET-bounded (delta/verify honour `token_budget`).
This is the final Plan 03 workstream; Plan 03 is now complete.

## Changes

- **`packages/mcp-server/src/agent-surface.test.ts`** — the harness. One set of REAL captured
  responses drives BOTH access paths through shared contract assertions, so MCP and SDK are held to
  one bar:
  - MCP (agent): a real MCP `Client` over the in-process transport (real JSON-RPC wire) calling all
    six tools, including the canonical "what changed since this date, in N tokens, with sources"
    `get_delta` query and `verify_claim` (supported-with-evidence, point-in-time `unverified`, and a
    no-evidence `unverified` that fabricates no support).
  - SDK/REST (client): the real `IntercalClient` over an injected fetch serving the same fixtures on
    the real `/v1/*` routes, across all six operations.
  - Cross-path equivalence: asserts MCP and SDK return byte-identical bodies for `get_delta` and
    `verify_claim` — the "one query layer, identical semantics" invariant.
  - Env-gated LIVE block (`INTERCAL_LIVE=1`): the SAME assertions against the DEPLOYED MCP
    (`/api/mcp` Streamable HTTP) and SDK/REST (`/api/v1/*`) with real production data.
- **`packages/mcp-server/src/agent-surface.fixtures.ts`** — REAL responses captured from
  `lntercal.vercel.app/api/v1/*` against production Neon, typed against the generated contract (a
  contract change breaks compilation — a typed tripwire, not faked product data). Includes a real
  budget-trimmed delta (4 of 12 changes rendered, "8 omitted") and supported/unverified/point-in-time
  verify captures.
- **`packages/mcp-server/src/server.ts`** — `buildMcpServer(db, handlers?)` gains an optional
  handler-injection seam (default `DEFAULT_HANDLERS` = the live DB-backed query layer; production is
  unchanged). It lets the harness drive the real MCP wire with deterministic, contract-shaped results
  without a live DB. `HANDLERS` is now the exported `DEFAULT_HANDLERS`.
- **`packages/sdk/src/live.test.ts`** — refreshed the stale W5/W6 expectations: `verifyClaim` now
  asserts the LIVE W6 verdict (supported + cited supporting evidence) and a point-in-time
  `unverified`, replacing the obsolete `501 not_implemented` expectation. `getDelta` already asserts
  the live budgeted/cited digest.
- **`packages/sdk/src/fixtures.ts` / `index.test.ts`** — the `not_implemented` error fixture is
  re-labelled as a generic taxonomy capture (the V1 synthesis bodies are live; no endpoint serves
  501 now), and the 501-mapping test asserts the code rather than the obsolete W5 message.
- **`packages/mcp-server/package.json`** — `@intercal/sdk` added as a workspace devDependency so the
  harness can drive both access paths from one package.

## Verification

- `pnpm lint` — repo-wide clean (the 1 info is the pre-existing biome.json schema-version drift).
- `pnpm typecheck` — all 6 packages.
- `pnpm test` — green: core 71, sdk 14 (+6 live skipped), api 35, mcp-server 21 (incl. the new
  agent-surface harness: 14 deterministic + 2 live skipped).
- `pnpm build` — all packages incl. the Next.js dashboard (`/api/mcp` route).
- `pnpm contracts:check` — no drift (contracts untouched).
- LIVE acceptance proof — `INTERCAL_LIVE=1 pnpm --filter @intercal/mcp-server test` and
  `INTERCAL_LIVE=1 pnpm --filter @intercal/sdk test` both green against the deployed MCP + SDK/REST:
  all six tools/operations return cited, confidence-scored, budget-bounded results for delta + verify
  + the read tools, against real production data. No secrets in code, fixtures, or output.
