/**
 * Live MCP OAuth 2.1 resource-server verification (Plan 07 W6).
 *
 * Drives the REAL production code path (`handleMcpRequest` from `@intercal/mcp-server`, the same
 * function the Vercel `/api/mcp` route calls) against a REAL database, in both auth modes:
 *
 *   A. Auth DISABLED (no AS) — public-read posture: initialize / tools/list / tools/call(get_entity)
 *      all succeed anonymously, exactly as the surface is live today.
 *   B. Auth ENABLED — with a locally-minted RS256 JWT verified against a LOCAL JWKS injected as the
 *      gate verifier (stands in for the external Authorization Server, which is the integration seam):
 *        - no token            → 401 + WWW-Authenticate(resource_metadata, scope)
 *        - wrong-audience token → 401 (RFC 8707 audience binding)
 *        - valid token          → tools/call(get_entity) authorized
 *      Also builds + checks the Protected Resource Metadata (RFC 9728) document.
 *
 * No secrets are printed. Requires DATABASE_URL in env or .env (a Neon branch or prod). Run:
 *   node scripts/dev/verify-mcp-auth.mjs
 */
import { readFileSync } from 'node:fs';
import { createDb } from '@intercal/core';
import {
  buildProtectedResourceMetadata,
  gateMcpRequest,
  handleMcpRequest,
  JwksTokenVerifier,
} from '@intercal/mcp-server';
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT } from 'jose';

// --- Minimal .env loader (DATABASE_URL only; never printed) ---
function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  try {
    for (const line of readFileSync('.env', 'utf8').split('\n')) {
      const m = /^\s*DATABASE_URL\s*=\s*(.+)\s*$/.exec(line);
      if (m) return m[1].replace(/^["']|["']$/g, '');
    }
  } catch {
    /* no .env */
  }
  throw new Error('DATABASE_URL not set (env or .env).');
}

const ISSUER = 'https://auth.local.test';
const RESOURCE = 'http://localhost:3100/api/mcp';
const RESOURCE_METADATA_URL = 'http://localhost:3100/.well-known/oauth-protected-resource';
const CONFIG = {
  resource: RESOURCE,
  authorizationServers: [ISSUER],
  scopesSupported: ['read'],
  requiredScopes: ['read'],
  algorithms: ['RS256'],
};

let pass = 0;
let fail = 0;
function check(name, cond) {
  if (cond) {
    pass++;
    console.log(`  ok   ${name}`);
  } else {
    fail++;
    console.log(`  FAIL ${name}`);
  }
}

function mcpReq(body, authorization) {
  const headers = {
    'content-type': 'application/json',
    accept: 'application/json, text/event-stream',
    'mcp-protocol-version': '2025-06-18',
  };
  if (authorization) headers.authorization = authorization;
  return new Request(RESOURCE, { method: 'POST', headers, body: JSON.stringify(body) });
}
async function rpc(res) {
  return JSON.parse(await res.text());
}

const db = createDb(loadDatabaseUrl());

// --- A. Auth DISABLED (gate deps null → anonymous) ---
console.log('[A] auth disabled (public-read posture)');
const disabledDeps = { config: null, verifier: null, resourceMetadataUrl: RESOURCE_METADATA_URL };

const initRes = await handleMcpRequest(
  db,
  mcpReq({
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'v', version: '0' },
    },
  }),
  disabledDeps,
);
const init = await rpc(initRes);
check(
  'initialize → 200 + serverInfo intercal',
  initRes.status === 200 && init.result?.serverInfo?.name === 'intercal',
);

const listRes = await handleMcpRequest(
  db,
  mcpReq({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} }),
  disabledDeps,
);
const list = await rpc(listRes);
check('tools/list → 6 tools (anonymous)', list.result?.tools?.length === 6);

const callRes = await handleMcpRequest(
  db,
  mcpReq({
    jsonrpc: '2.0',
    id: 3,
    method: 'tools/call',
    params: { name: 'get_entity', arguments: { name_or_id: 'rust' } },
  }),
  disabledDeps,
);
const call = await rpc(callRes);
check(
  'tools/call get_entity → 200 (anonymous, real DB)',
  callRes.status === 200 && call.result !== undefined,
);

// --- B. Auth ENABLED (local JWKS stands in for the AS) ---
console.log('[B] auth enabled (OAuth 2.1 resource server)');
const { privateKey, publicKey } = await generateKeyPair('RS256');
const jwk = await exportJWK(publicKey);
jwk.kid = 'local';
jwk.alg = 'RS256';
// A second, PS256 key under a distinct kid — its public half is in the JWKS, so a PS256-signed token
// is a VALID signature. The RS256-only allowlist must still reject it (algorithm pinning).
const psPair = await generateKeyPair('PS256');
const psJwk = await exportJWK(psPair.publicKey);
psJwk.kid = 'local-ps';
psJwk.alg = 'PS256';
const verifier = new JwksTokenVerifier(CONFIG, createLocalJWKSet({ keys: [jwk, psJwk] }));
const enabledDeps = { config: CONFIG, verifier, resourceMetadataUrl: RESOURCE_METADATA_URL };

// PRM document (RFC 9728)
const prm = buildProtectedResourceMetadata(CONFIG);
check(
  '.well-known PRM doc resolves (resource + authorization_servers + scopes)',
  prm.resource === RESOURCE &&
    prm.authorization_servers[0] === ISSUER &&
    prm.scopes_supported.includes('read'),
);

// No token → 401 + WWW-Authenticate
const noTok = await handleMcpRequest(
  db,
  mcpReq({ jsonrpc: '2.0', id: 4, method: 'tools/list', params: {} }),
  enabledDeps,
);
const wwwAuth = noTok.headers.get('www-authenticate') ?? '';
check(
  'no token → 401 + WWW-Authenticate(resource_metadata)',
  noTok.status === 401 &&
    wwwAuth.includes('Bearer') &&
    wwwAuth.includes(`resource_metadata="${RESOURCE_METADATA_URL}"`),
);

async function mint({ audience = RESOURCE, scope = 'read', ps = false } = {}) {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ scope })
    .setProtectedHeader({ alg: ps ? 'PS256' : 'RS256', kid: ps ? 'local-ps' : 'local' })
    .setSubject('verify-user')
    .setIssuer(ISSUER)
    .setAudience(audience)
    .setIssuedAt(now)
    .setExpirationTime(now + 300)
    .sign(ps ? psPair.privateKey : privateKey);
}

// Wrong-audience token → 401 (RFC 8707)
const wrongAud = await mint({ audience: 'https://other.test/api/mcp' });
const wrongRes = await handleMcpRequest(
  db,
  mcpReq({ jsonrpc: '2.0', id: 5, method: 'tools/list', params: {} }, `Bearer ${wrongAud}`),
  enabledDeps,
);
check('wrong-audience token → 401', wrongRes.status === 401);

// Validly-signed PS256 token (alg outside the RS256 allowlist) → 401 (algorithm pinning)
const psTok = await mint({ ps: true });
const psRes = await handleMcpRequest(
  db,
  mcpReq({ jsonrpc: '2.0', id: 7, method: 'tools/list', params: {} }, `Bearer ${psTok}`),
  enabledDeps,
);
check('out-of-allowlist alg (PS256) token → 401', psRes.status === 401);

// Valid token → tools/call authorized
const goodTok = await mint();
const okRes = await handleMcpRequest(
  db,
  mcpReq(
    {
      jsonrpc: '2.0',
      id: 6,
      method: 'tools/call',
      params: { name: 'get_entity', arguments: { name_or_id: 'rust' } },
    },
    `Bearer ${goodTok}`,
  ),
  enabledDeps,
);
const ok = await rpc(okRes);
check('valid token → tools/call get_entity 200', okRes.status === 200 && ok.result !== undefined);

console.log(`\n[done] ${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
