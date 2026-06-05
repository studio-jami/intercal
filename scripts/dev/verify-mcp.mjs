/**
 * Live MCP verification — connects a real MCP client to a running Streamable HTTP endpoint and
 * performs initialize + tools/list + real tool calls against production data. No secrets printed.
 *
 * Usage: node scripts/dev/verify-mcp.mjs [url]   (default http://localhost:3100/api/mcp)
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const url = process.argv[2] ?? 'http://localhost:3100/api/mcp';

function preview(value, max = 600) {
  const s = JSON.stringify(value);
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

const transport = new StreamableHTTPClientTransport(new URL(url));
const client = new Client({ name: 'intercal-verify', version: '0.0.0' }, { capabilities: {} });

await client.connect(transport);
console.log('[initialize] serverInfo:', preview(client.getServerVersion()));
console.log('[initialize] capabilities:', preview(client.getServerCapabilities()));

const { tools } = await client.listTools();
console.log(`[tools/list] ${tools.length} tools:`, tools.map((t) => t.name).join(', '));

const entity = await client.callTool({ name: 'get_entity', arguments: { name_or_id: 'rust' } });
console.log('[get_entity rust] isError:', entity.isError ?? false);
console.log('[get_entity rust] result:', preview(entity.structuredContent));

const evidence = await client.callTool({
  name: 'search_evidence',
  arguments: { query: 'rust', limit: 3 },
});
console.log('[search_evidence rust] isError:', evidence.isError ?? false);
console.log('[search_evidence rust] result:', preview(evidence.structuredContent));

const delta = await client.callTool({
  name: 'get_delta',
  arguments: { topic: 'rust', since_date: '2026-01-01T00:00:00Z' },
});
console.log('[get_delta] isError:', delta.isError, '— code:', delta.structuredContent?.code);

await client.close();
console.log('[done] live MCP verification complete');
