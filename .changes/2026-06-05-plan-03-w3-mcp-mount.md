# Plan 03 W3 + Plan 07 W2 — MCP server hardening + Vercel `/api/mcp` mount

Date: 2026-06-05
Type: feat
Packages: @intercal/mcp-server, @intercal/dashboard

## Summary

Hardened the MCP server and mounted it at `/api/mcp` on the Vercel/Next.js app, so agents
reach the V1 tool surface at one URL (`<domain>/api/mcp`) over stateless Streamable HTTP,
backed by the same `@intercal/core` query layer as REST. No auth yet (OAuth 2.1 is Plan 07
W6 — left as a clean seam). The two deferred query bodies (`get_delta`, `verify_claim`)
remain honest `NotImplementedError` seams (Plan 03 W5/W6); they surface as a clear
`not_implemented` MCP tool error, not a fake result.

## Changes

- **Web-standard transport for serverless.** Verified against the installed SDK
  (`@modelcontextprotocol/sdk@1.29.0`, MCP protocol up to `2025-11-25`): the SDK ships
  `WebStandardStreamableHTTPServerTransport`, whose `handleRequest(req: Request): Promise<Response>`
  maps directly onto a Next.js App Router route handler. New
  `packages/mcp-server/src/web.ts` exposes `handleMcpRequest(db, request)` — stateless
  (`sessionIdGenerator: undefined`) and `enableJsonResponse: true` so each serverless
  invocation returns a fully-buffered JSON-RPC response with deterministic per-request
  teardown (no dangling SSE stream). A fresh server + transport is built per request; only
  the DB pool is long-lived.
- **Vercel mount.** `packages/dashboard/app/api/mcp/route.ts` (POST + GET) on
  `runtime = 'nodejs'` (the `pg` driver needs TCP sockets; Edge can't), `dynamic =
  'force-dynamic'`, `maxDuration = 30`. Sits beside the existing REST mount
  (`/api/[[...route]]`) on one domain. `@intercal/mcp-server` added to the dashboard deps +
  `transpilePackages`.
- **Error taxonomy preserved across the boundary.** `buildMcpServer` now maps
  `IntercalError` subclasses (`not_found` / `invalid_request` / `not_implemented`) into the
  tool result's `structuredContent.code` + text, so MCP clients see the same taxonomy REST
  maps to HTTP status. Added server `instructions`. Statelessness documented at the call
  site.

## Tests

- `packages/mcp-server/src/server.test.ts` — a real MCP `Client` over the in-process
  transport: initialize, tools/list (asserts exactly the 6 V1 tools + contract-derived input
  schemas), tools/call deferred-seam errors, unknown-tool error. (6 tests)
- `packages/mcp-server/src/web.test.ts` — drives `handleMcpRequest` with real Web `Request`s
  (the exact Vercel route path): initialize, tools/list, deferred get_delta error. (3 tests)
- Full gate green: `pnpm lint`, `pnpm typecheck`, `pnpm test` (mcp-server 9 / api 40 /
  core 12 / sdk), `pnpm build` (Next.js emits `/api/mcp` as a dynamic Node function).
  Contracts untouched — no `contracts:check` needed.

## Live verification

Ran a real MCP client (`@modelcontextprotocol/sdk` `StreamableHTTPClientTransport`) against
a local `next dev` `/api/mcp` reading the production Neon branch (`scripts/dev/verify-mcp.mjs`):

- **initialize** → `intercal@0.1.0`, tools capability.
- **tools/list** → all 6 V1 tools.
- **get_entity rust** → real entity `35f09cce-…` with fact "Rust has version 1.96.0" +
  evidence provenance.
- **search_evidence rust** → real hits from production source docs (Node.js v26.3.0 release,
  rust-lang GitHub).
- **get_delta** → `isError: true`, code `not_implemented` (deferred seam intact).

Verified locally because this commit is what adds `/api/mcp` to the deployment; it will be
live on Vercel after the prod redeploy on push.
