/**
 * Web-transport tests — drive `handleMcpRequest` with real Web `Request` objects and assert the
 * returned Web `Response` is a valid JSON-RPC MCP response. This is the exact path the Vercel
 * `/api/mcp` route handler uses, so it proves the serverless mount works without a live server.
 *
 * Null DB: `initialize` and `tools/list` never query the DB, and `verify_claim` (a Plan 03 W6
 * deferred seam) raises `NotImplementedError` before touching it.
 */

import type { Db } from '@intercal/core';
import { describe, expect, it } from 'vitest';
import { handleMcpRequest } from './web.js';

// biome-ignore lint/suspicious/noExplicitAny: null DB; covered paths never reach the query layer.
const nullDb = null as any as Db;

const PROTOCOL_VERSION = '2025-06-18';

function mcpRequest(body: unknown): Request {
  return new Request('http://localhost/api/mcp', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      // Streamable HTTP clients advertise both JSON and SSE; the server picks JSON here.
      accept: 'application/json, text/event-stream',
      'mcp-protocol-version': PROTOCOL_VERSION,
    },
    body: JSON.stringify(body),
  });
}

/** Parse the JSON-RPC payload from a (JSON-mode) Streamable HTTP response. */
async function readJsonRpc(res: Response): Promise<Record<string, unknown>> {
  const ct = res.headers.get('content-type') ?? '';
  const raw = await res.text();
  if (ct.includes('text/event-stream')) {
    // SSE framing fallback: extract the first `data:` line. (We expect JSON mode, but be robust.)
    const line = raw.split('\n').find((l) => l.startsWith('data:'));
    return JSON.parse((line ?? '').slice('data:'.length).trim());
  }
  return JSON.parse(raw);
}

describe('handleMcpRequest — initialize', () => {
  it('returns a JSON-RPC initialize result with serverInfo + protocolVersion', async () => {
    const res = await handleMcpRequest(
      nullDb,
      mcpRequest({
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
          protocolVersion: PROTOCOL_VERSION,
          capabilities: {},
          clientInfo: { name: 'web-test', version: '0.0.0' },
        },
      }),
    );
    expect(res.status).toBe(200);
    const body = await readJsonRpc(res);
    expect(body).toMatchObject({ jsonrpc: '2.0', id: 1 });
    const result = body.result as Record<string, unknown>;
    expect(result.serverInfo).toMatchObject({ name: 'intercal' });
    expect(result.protocolVersion).toBeTruthy();
    expect(result.capabilities).toMatchObject({ tools: expect.any(Object) });
  });
});

describe('handleMcpRequest — tools/list', () => {
  it('returns all V1 tools', async () => {
    const res = await handleMcpRequest(
      nullDb,
      mcpRequest({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} }),
    );
    expect(res.status).toBe(200);
    const body = await readJsonRpc(res);
    const result = body.result as { tools: Array<{ name: string }> };
    const names = result.tools.map((t) => t.name);
    expect(names).toContain('get_entity');
    expect(names).toContain('search_evidence');
    expect(result.tools).toHaveLength(6);
  });
});

describe('handleMcpRequest — tools/call deferred seam', () => {
  it('verify_claim call yields a not_implemented tool error result', async () => {
    const res = await handleMcpRequest(
      nullDb,
      mcpRequest({
        jsonrpc: '2.0',
        id: 3,
        method: 'tools/call',
        params: {
          name: 'verify_claim',
          arguments: { claim_text: 'Rust has version 1.96.0' },
        },
      }),
    );
    expect(res.status).toBe(200);
    const body = await readJsonRpc(res);
    const result = body.result as { isError?: boolean; structuredContent?: { code?: string } };
    expect(result.isError).toBe(true);
    expect(result.structuredContent?.code).toBe('not_implemented');
  });
});
