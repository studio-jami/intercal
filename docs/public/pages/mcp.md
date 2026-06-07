# MCP

Intercal exposes MCP over Streamable HTTP at:

```text
https://intercal.jami.studio/api/mcp
```

The MCP server is stateless on the Vercel route. Each request builds a fresh server/transport over the shared query layer, so there is no per-session state to pin to a serverless instance.

## Tools

The V1 tool list is owned by `packages/shared/src/index.ts` and uses generated JSON Schemas for inputs:

- `get_delta`
- `get_entity`
- `search_evidence`
- `verify_claim`
- `get_sources`
- `get_freshness`

Every tool maps to the same query semantics as its REST counterpart. Structured failures use the same error taxonomy as REST in the MCP tool result.

## Authentication

MCP uses an OAuth 2.1 resource-server posture when `MCP_OAUTH_ISSUER` is configured. When no Authorization Server is configured, the current public-read posture allows anonymous reads. Invalid tokens never fail open when auth is enabled.

Protected Resource Metadata is served from the well-known routes only when MCP OAuth is configured:

- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-protected-resource/api/mcp`

## Local smoke

```powershell
node scripts/dev/verify-mcp.mjs https://intercal.jami.studio/api/mcp
```

Run this against a deployed or local endpoint. It proves transport availability; it does not replace live corpus quality gates.
