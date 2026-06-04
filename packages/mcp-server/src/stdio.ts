#!/usr/bin/env node
import { createDb, loadConfig } from '@intercal/core';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { buildMcpServer } from './server.js';

// Local / embedded transport. Streamable HTTP (http.ts) is the primary remote transport.
const config = loadConfig();
const db = createDb(config.databaseUrl);
const server = buildMcpServer(db);
const transport = new StdioServerTransport();

await server.connect(transport);
