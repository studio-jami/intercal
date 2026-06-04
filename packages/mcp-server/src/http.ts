import http from 'node:http';
import { createDb, loadConfig } from '@intercal/core';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { buildMcpServer } from './server.js';

// Streamable HTTP is the current MCP transport (HTTP+SSE is deprecated). Stateless mode:
// a fresh server+transport per request keeps the deployment horizontally scalable.
const config = loadConfig();
const db = createDb(config.databaseUrl);

const httpServer = http.createServer(async (req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' }).end('{"status":"ok"}');
    return;
  }
  if (req.method === 'POST' && req.url === '/mcp') {
    const server = buildMcpServer(db);
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    res.on('close', () => {
      void transport.close();
      void server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(req, res);
    return;
  }
  res.writeHead(404, { 'content-type': 'application/json' }).end('{"error":"not_found"}');
});

httpServer.listen(config.mcpPort, () => {
  console.log(`[intercal-mcp] Streamable HTTP on http://localhost:${config.mcpPort}/mcp`);
});
