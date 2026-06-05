# MCP & API Surface

The agent-facing contract. MCP and REST expose the **same V1 query semantics** through one
shared query layer (`@intercal/core`); they never diverge.

## Contract source

**TypeSpec (`packages/shared/typespec/main.tsp`) is the single source of truth.** It compiles
to OpenAPI 3.1 + per-model JSON Schema, from which TypeScript types and Pydantic models are
generated (`pnpm contracts:build`; drift-guarded by `pnpm contracts:check`). The REST API
validates requests against the JSON Schema; the MCP server uses the **same** JSON Schemas as
tool input schemas. No hand-written, drift-prone duplicate.

## V1 tools / endpoints

| Tool (MCP) | REST | Input schema | Status |
| --- | --- | --- | --- |
| `get_entity` | `GET /v1/entity` | `EntityQuery` | implemented (read) |
| `get_sources` | `GET /v1/sources` | `SourcesQuery` | implemented (read) |
| `get_freshness` | `GET /v1/freshness` | `FreshnessQuery` | implemented (read) |
| `search_evidence` | `GET /v1/evidence` | `EvidenceQuery` | implemented (read) |
| `get_delta` | `GET /v1/delta` | `DeltaQuery` | Plan 03 (digest synthesis) |
| `verify_claim` | `GET /v1/claims/verify` | `VerifyClaimQuery` | Plan 03 (evidence + contradiction reasoning) |

The two deferred tools return a `not_implemented` error today (HTTP 501 / MCP `isError`) with a
message naming the owning plan — an honest deferral, not a stub returning fake data. Responses
carry citations, confidence, and freshness per the foundation report.

Later tools (`get_relationships`, `get_timeline`, `get_briefing`, `subscribe`, `submit_source`,
`submit_correction`, `propose_merge`, `export_subgraph`) are added in later plans against the
same contract.

## Transports & auth

- **MCP:** Streamable HTTP is the transport. On the deployment it is **mounted at `/api/mcp`** on
  the one Vercel domain (Next.js App Router route `packages/dashboard/app/api/mcp/route.ts`, Node
  runtime) via `handleMcpRequest` (`packages/mcp-server/src/web.ts`), built on the SDK's
  `WebStandardStreamableHTTPServerTransport` — **stateless** (`sessionIdGenerator: undefined`,
  `enableJsonResponse: true`): a fresh server + transport per request, no per-session state, safe
  on serverless. A standalone Node server (`http.ts`) and stdio (`stdio.ts`) remain for local /
  Cloud Run / embedded use. (HTTP+SSE is deprecated upstream and not used.) Spec baseline
  **2025-11-25**, official `@modelcontextprotocol/sdk`. OAuth 2.1 resource-server auth is added
  for the public deployment in the operations plan (Plan 07 W6) — currently a clean, open seam.
- **REST:** Hono app (`packages/api`), `/openapi.json` served from the generated document,
  `/health` for probes. API-key auth (hashed, scoped — `api_keys` table) is wired in Plan 04.

## Error shape

All errors use the contract `ApiError` (`code`, `message`, `details?`). `@intercal/core` maps
domain errors to codes: `not_found` → 404, `invalid_request` → 400, `not_implemented` → 501.
MCP has no HTTP status, so the same codes are surfaced on the tool result: `isError: true` with
`structuredContent.code` (and the `code: message` text), keeping the deferred `get_delta` /
`verify_claim` seams (`not_implemented`) clearly distinguishable from real failures.
