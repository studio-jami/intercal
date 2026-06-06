/**
 * Web-transport tests — drive `handleMcpRequest` with real Web `Request` objects and assert the
 * returned Web `Response` is a valid JSON-RPC MCP response. This is the exact path the Vercel
 * `/api/mcp` route handler uses, so it proves the serverless mount works without a live server.
 *
 * Null DB: `initialize` and `tools/list` never query the DB, and the unknown-tool `tools/call` is
 * rejected before any handler runs. DB-backed tool calls (incl. `verify_claim`, Plan 03 W6) are
 * covered by the live Neon integration verification, not here.
 */

import type { Db } from '@intercal/core';
import type { OAuthTokenVerifier } from '@modelcontextprotocol/sdk/server/auth/provider.js';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import { describe, expect, it } from 'vitest';
import type { GateDeps, McpAuthConfig } from './auth/index.js';
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

// --- OAuth 2.1 resource-server gate wired into the web handler (Plan 07 W6) ---

const RESOURCE = 'https://intercal.example.test/api/mcp';
const RESOURCE_METADATA_URL = 'https://intercal.example.test/.well-known/oauth-protected-resource';
const ENABLED_CONFIG: McpAuthConfig = {
  resource: RESOURCE,
  authorizationServers: ['https://auth.example.test'],
  scopesSupported: ['read'],
  requiredScopes: ['read'],
  algorithms: ['RS256'],
};

function enabledGate(scopes: string[] | null): GateDeps {
  // scopes === null → verifier always rejects (simulates an invalid token).
  const verifier: OAuthTokenVerifier = {
    async verifyAccessToken(token: string): Promise<AuthInfo> {
      if (scopes === null) throw new Error('invalid token');
      return {
        token,
        clientId: 'c1',
        scopes,
        expiresAt: Math.floor(Date.now() / 1000) + 600,
        resource: new URL(RESOURCE),
      };
    },
  };
  return { config: ENABLED_CONFIG, verifier, resourceMetadataUrl: RESOURCE_METADATA_URL };
}

describe('handleMcpRequest — OAuth gate (auth enabled)', () => {
  it('rejects an unauthenticated request with 401 + WWW-Authenticate before any JSON-RPC handling', async () => {
    const res = await handleMcpRequest(
      nullDb,
      mcpRequest({ jsonrpc: '2.0', id: 9, method: 'tools/list', params: {} }),
      enabledGate(['read']),
    );
    expect(res.status).toBe(401);
    const header = res.headers.get('www-authenticate') ?? '';
    expect(header).toContain('Bearer');
    expect(header).toContain(`resource_metadata="${RESOURCE_METADATA_URL}"`);
  });

  it('rejects a request bearing an invalid token with 401', async () => {
    const req = new Request('http://localhost/api/mcp', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
        'mcp-protocol-version': PROTOCOL_VERSION,
        authorization: 'Bearer not-a-real-token',
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 10, method: 'tools/list', params: {} }),
    });
    const res = await handleMcpRequest(nullDb, req, enabledGate(null));
    expect(res.status).toBe(401);
  });

  it('allows a valid, in-scope token through to tools/list', async () => {
    const req = new Request('http://localhost/api/mcp', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
        'mcp-protocol-version': PROTOCOL_VERSION,
        authorization: 'Bearer valid-token',
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 11, method: 'tools/list', params: {} }),
    });
    const res = await handleMcpRequest(nullDb, req, enabledGate(['read']));
    expect(res.status).toBe(200);
    const body = await readJsonRpc(res);
    const result = body.result as { tools: Array<{ name: string }> };
    expect(result.tools.map((t) => t.name)).toContain('get_entity');
  });
});

describe('handleMcpRequest — tools/call unknown tool', () => {
  it('an unknown tool name yields an invalid_request tool error result (no DB access)', async () => {
    const res = await handleMcpRequest(
      nullDb,
      mcpRequest({
        jsonrpc: '2.0',
        id: 3,
        method: 'tools/call',
        params: {
          name: 'no_such_tool',
          arguments: {},
        },
      }),
    );
    expect(res.status).toBe(200);
    const body = await readJsonRpc(res);
    const result = body.result as { isError?: boolean; structuredContent?: { code?: string } };
    expect(result.isError).toBe(true);
    expect(result.structuredContent?.code).toBe('invalid_request');
  });
});
