import { createDb, loadConfig } from '@intercal/core';
import { handleMcpRequest } from '@intercal/mcp-server';

// Intercal MCP server, mounted on the one Vercel domain alongside the UI (`/`) and the REST API
// (`/api/v1/*`). Agents connect to a single Streamable HTTP endpoint: `<domain>/api/mcp`.
//
// Stateless Streamable HTTP: each request builds a fresh MCP server + transport over the shared
// Neon-backed query layer (`@intercal/core`), so there is no per-session server state to break on
// serverless. Auth (OAuth 2.1 resource server) is Plan 07 W6 — this is a clean, unauthenticated
// seam until then.
//
// Node runtime is required: the query layer uses `pg` (TCP sockets), which the Edge runtime
// cannot provide. `force-dynamic` opts out of any caching of the JSON-RPC responses.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 30;

// The DB pool is created once per cold start (module scope) and reused across invocations; only
// the MCP server/transport are per-request. Lazy so a missing DATABASE_URL surfaces on first
// request rather than at module load.
let db: ReturnType<typeof createDb> | null = null;
function getDb(): ReturnType<typeof createDb> {
  if (!db) db = createDb(loadConfig().databaseUrl);
  return db;
}

export function POST(req: Request): Promise<Response> {
  return handleMcpRequest(getDb(), req);
}

// GET is part of the Streamable HTTP transport (clients may open a standalone stream). In
// stateless JSON mode the transport responds appropriately; exposing it keeps the endpoint
// spec-complete for clients that probe with GET.
export function GET(req: Request): Promise<Response> {
  return handleMcpRequest(getDb(), req);
}
