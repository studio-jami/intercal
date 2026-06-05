import {
  type Db,
  type DeltaParams,
  type EntityParams,
  type EvidenceParams,
  type FreshnessParams,
  getDelta,
  getEntity,
  getFreshness,
  getSources,
  IntercalError,
  type SourcesParams,
  searchEvidence,
  type VerifyClaimParams,
  verifyClaim,
} from '@intercal/core';
import { getJsonSchema, V1_TOOLS } from '@intercal/shared';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  type CallToolResult,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

type ToolFn = (db: Db, params: Record<string, unknown>) => Promise<unknown>;

const HANDLERS: Record<string, ToolFn> = {
  get_delta: (db, p) => getDelta(db, p as unknown as DeltaParams),
  get_entity: (db, p) => getEntity(db, p as unknown as EntityParams),
  search_evidence: (db, p) => searchEvidence(db, p as unknown as EvidenceParams),
  verify_claim: (db, p) => verifyClaim(db, p as unknown as VerifyClaimParams),
  get_sources: (db, p) => getSources(db, p as unknown as SourcesParams),
  get_freshness: (db, p) => getFreshness(db, p as unknown as FreshnessParams),
};

/**
 * Build a tool error result that preserves the structured error taxonomy. The query layer
 * throws `IntercalError` subclasses (`not_found`, `invalid_request`, `not_implemented`) — the
 * same codes the REST surface maps to HTTP status. MCP has no status code, so we surface the
 * code + message in the text content and any details, keeping the deferred W5/W6 seams
 * (`not_implemented`) clearly distinguishable from a real failure rather than a generic string.
 */
function toErrorResult(err: unknown): CallToolResult {
  if (err instanceof IntercalError) {
    const payload: Record<string, unknown> = { code: err.code, message: err.message };
    if (err.details) payload.details = err.details;
    return {
      content: [{ type: 'text', text: `${err.code}: ${err.message}` }],
      structuredContent: payload,
      isError: true,
    };
  }
  const message = err instanceof Error ? err.message : 'Unknown error';
  return {
    content: [{ type: 'text', text: `internal_error: ${message}` }],
    structuredContent: { code: 'internal_error', message },
    isError: true,
  };
}

/**
 * Build an MCP server exposing the V1 tools, backed by the shared query layer.
 *
 * Stateless by construction: the server holds only the injected `db` handle and the static
 * tool registry — no per-session/per-connection state — so it is safe to instantiate one
 * server + transport per request on serverless (the Vercel `/api/mcp` mount does exactly this).
 */
export function buildMcpServer(db: Db): Server {
  const server = new Server(
    { name: 'intercal', version: '0.1.0' },
    {
      capabilities: { tools: {} },
      instructions:
        'Intercal is a provenance-backed temporal knowledge substrate. Tools return cited, ' +
        'freshness-aware facts traced to source evidence. get_delta and verify_claim are ' +
        'deferred (return a not_implemented error) until their synthesis bodies ship.',
    },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: V1_TOOLS.map((t) => ({
      name: t.name,
      description: t.description,
      // The MCP tool input schema IS the generated contract JSON Schema — single source.
      inputSchema: getJsonSchema(t.inputSchema) as { type: 'object' },
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req): Promise<CallToolResult> => {
    const fn = HANDLERS[req.params.name];
    if (!fn) {
      return {
        content: [{ type: 'text', text: `invalid_request: unknown tool "${req.params.name}"` }],
        structuredContent: {
          code: 'invalid_request',
          message: `Unknown tool: ${req.params.name}`,
        },
        isError: true,
      };
    }
    try {
      const result = await fn(db, (req.params.arguments ?? {}) as Record<string, unknown>);
      return {
        content: [{ type: 'text', text: JSON.stringify(result) }],
        structuredContent: result as Record<string, unknown>,
      };
    } catch (err) {
      return toErrorResult(err);
    }
  });

  return server;
}
