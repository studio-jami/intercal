import type { Db } from '@intercal/core';
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js';
import { buildMcpServer } from './server.js';

/**
 * Handle one MCP Streamable HTTP request using the Web-standard transport.
 *
 * Returns a Web `Response`, so it drops straight into a Next.js App Router route handler, a
 * Hono handler, or any Web-standard runtime (Vercel functions, Cloudflare Workers, Deno, Bun).
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
export async function handleMcpRequest(db: Db, request: Request): Promise<Response> {
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
