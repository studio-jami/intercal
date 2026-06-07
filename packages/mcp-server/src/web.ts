import type { Db } from '@intercal/core';
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js';
import { type GateDeps, gateMcpRequest, resolveGateDeps } from './auth/index.js';
import { buildMcpServer } from './server.js';

/**
 * Handle one MCP Streamable HTTP request using the Web-standard transport.
 *
 * Returns a Web `Response`, so it drops straight into the current Next.js App Router route handler
 * or another Web-standard host adapter after that host has proven the required DB/runtime behavior.
 *
 * OAuth 2.1 resource-server protection (Plan 07 W6) runs FIRST, before any JSON-RPC handling:
 *  - When an Authorization Server is configured (`MCP_OAUTH_ISSUER`), bearer access tokens are
 *    validated (audience-bound, RFC 8707/9068) and missing/invalid tokens are rejected with a
 *    spec-correct 401 + `WWW-Authenticate` pointing at the Protected Resource Metadata.
 *  - When no AS is configured, the gate resolves to ANONYMOUS and the surface keeps its public-read
 *    posture (MCP authorization is OPTIONAL per spec) — the live default today.
 * `deps` is injectable for tests; production resolves it from the request origin + environment.
 *
 * Stateless by design, for serverless:
 *  - `sessionIdGenerator: undefined` disables MCP session management (no in-memory session map).
 *  - `enableJsonResponse: true` returns a single buffered JSON-RPC response instead of opening a
 *    long-lived SSE stream. On serverless the function returns once the response is fully
 *    materialized, which (a) fits the request/response execution model, and (b) makes per-request
 *    teardown deterministic — there is no dangling stream to keep alive after `handleRequest`
 *    resolves. The Streamable HTTP spec permits the server to answer a POST with either a JSON
 *    body or an SSE stream; JSON is the correct stateless choice here.
 *  - A fresh server + transport is created per request and torn down in `finally`, so nothing
 *    leaks across invocations.
 *
 * The DB handle is injected (a long-lived pool created once per cold start); only the MCP
 * server/transport are per-request.
 */
export async function handleMcpRequest(
  db: Db,
  request: Request,
  deps?: GateDeps,
): Promise<Response> {
  // 1. OAuth 2.1 resource-server gate. Short-circuit on 401/403; otherwise proceed (anonymous or
  //    authorized). The resolved principal is not yet needed by the read tools (public-read graph),
  //    but the gate is the enforcement point and the seam where per-principal policy will attach.
  const gate = await gateMcpRequest(request, deps ?? resolveGateDeps(request.url));
  if (!gate.ok) return gate.response;

  const server = buildMcpServer(db);
  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  try {
    await server.connect(transport);
    // With enableJsonResponse, this resolves only once every JSON-RPC response is ready, so the
    // returned Response is fully buffered and safe to hand back before teardown.
    return await transport.handleRequest(request);
  } finally {
    void transport.close();
    void server.close();
  }
}
