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
  type SourcesParams,
  searchEvidence,
  type VerifyClaimParams,
  verifyClaim,
} from '@intercal/core';
import { getJsonSchema, V1_TOOLS } from '@intercal/shared';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

type ToolFn = (db: Db, params: Record<string, unknown>) => Promise<unknown>;

const HANDLERS: Record<string, ToolFn> = {
  get_delta: (db, p) => getDelta(db, p as unknown as DeltaParams),
  get_entity: (db, p) => getEntity(db, p as unknown as EntityParams),
  search_evidence: (db, p) => searchEvidence(db, p as unknown as EvidenceParams),
  verify_claim: (db, p) => verifyClaim(db, p as unknown as VerifyClaimParams),
  get_sources: (db, p) => getSources(db, p as unknown as SourcesParams),
  get_freshness: (db, p) => getFreshness(db, p as unknown as FreshnessParams),
};

/** Build an MCP server exposing the V1 tools, backed by the shared query layer. */
export function buildMcpServer(db: Db): Server {
  const server = new Server(
    { name: 'intercal', version: '0.1.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: V1_TOOLS.map((t) => ({
      name: t.name,
      description: t.description,
      // The MCP tool input schema IS the generated contract JSON Schema — single source.
      inputSchema: getJsonSchema(t.inputSchema) as { type: 'object' },
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const fn = HANDLERS[req.params.name];
    if (!fn) {
      return {
        content: [{ type: 'text', text: `Unknown tool: ${req.params.name}` }],
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
      const message = err instanceof Error ? err.message : 'Unknown error';
      return { content: [{ type: 'text', text: message }], isError: true };
    }
  });

  return server;
}
