/**
 * MCP server tests — drive a real MCP `Client` against `buildMcpServer` over the in-process
 * transport pair. This exercises the actual JSON-RPC wire path (initialize → tools/list →
 * tools/call), not the handlers in isolation.
 *
 * A null DB is used: the covered tool call (`verify_claim`, still a Plan 03 W6 deferred seam)
 * raises `NotImplementedError` before touching the DB, and `tools/list` never queries. DB-backed
 * tool calls (`get_entity`, `search_evidence`, `get_delta`, …) are covered by the integration
 * verification against Neon, not here.
 */

import type { Db } from '@intercal/core';
import { V1_TOOLS } from '@intercal/shared';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { describe, expect, it } from 'vitest';
import { buildMcpServer } from './server.js';

// biome-ignore lint/suspicious/noExplicitAny: null DB; covered paths never reach the query layer.
const nullDb = null as any as Db;

async function connectClient(): Promise<Client> {
  const server = buildMcpServer(nullDb);
  const client = new Client({ name: 'test-client', version: '0.0.0' }, { capabilities: {} });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
  return client;
}

describe('MCP initialize', () => {
  it('negotiates and reports the server identity + tools capability', async () => {
    const client = await connectClient();
    expect(client.getServerVersion()).toMatchObject({ name: 'intercal' });
    expect(client.getServerCapabilities()).toMatchObject({ tools: expect.any(Object) });
    await client.close();
  });
});

describe('tools/list', () => {
  it('lists exactly the V1 tool surface with contract-derived input schemas', async () => {
    const client = await connectClient();
    const { tools } = await client.listTools();

    const names = tools.map((t) => t.name).sort();
    expect(names).toEqual([...V1_TOOLS].map((t) => t.name).sort());

    for (const tool of tools) {
      expect(tool.description).toBeTruthy();
      // Every tool input schema is the generated JSON Schema object.
      expect(tool.inputSchema).toMatchObject({ type: 'object' });
    }
    await client.close();
  });

  it('exposes get_entity with its required name_or_id param from the contract', async () => {
    const client = await connectClient();
    const { tools } = await client.listTools();
    const entity = tools.find((t) => t.name === 'get_entity');
    expect(entity?.inputSchema?.properties).toHaveProperty('name_or_id');
    await client.close();
  });
});

describe('tools/call — deferred seam (Plan 03 W6)', () => {
  it('verify_claim returns an isError result carrying the not_implemented code', async () => {
    const client = await connectClient();
    const res = await client.callTool({
      name: 'verify_claim',
      arguments: { claim_text: 'Rust has version 1.96.0' },
    });
    expect(res.isError).toBe(true);
    expect(res.structuredContent).toMatchObject({ code: 'not_implemented' });
    await client.close();
  });
});

describe('tools/call — unknown tool', () => {
  it('returns an isError result with an invalid_request code', async () => {
    const client = await connectClient();
    const res = await client.callTool({ name: 'no_such_tool', arguments: {} });
    expect(res.isError).toBe(true);
    expect(res.structuredContent).toMatchObject({ code: 'invalid_request' });
    await client.close();
  });
});
