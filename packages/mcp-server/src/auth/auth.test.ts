/**
 * MCP OAuth 2.1 resource-server tests (Plan 07 W6).
 *
 * Covers the four spec-critical behaviours:
 *   - Config seam: auth disabled when no AS is configured; enabled + derived audience when it is.
 *   - Protected Resource Metadata (RFC 9728) document shape.
 *   - The resource-server gate: anonymous when disabled; 401 (+ `WWW-Authenticate` with
 *     `resource_metadata`) when a token is missing/invalid; 403 `insufficient_scope` for a valid
 *     token lacking a scope; authorized for a valid, in-scope, audience-bound token.
 *   - Real JWT verification (`JwksTokenVerifier`) against a LOCAL key set: signature, issuer,
 *     audience binding (RFC 8707), and expiry — including rejection of a wrong-audience token.
 */

import type { OAuthTokenVerifier } from '@modelcontextprotocol/sdk/server/auth/provider.js';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import { createLocalJWKSet, exportJWK, generateKeyPair, type JWK, SignJWT } from 'jose';
import { beforeAll, describe, expect, it } from 'vitest';
import { loadMcpAuthConfig, type McpAuthConfig } from './config.js';
import { buildProtectedResourceMetadata } from './metadata.js';
import { gateMcpRequest } from './resource-server.js';
import { JwksTokenVerifier } from './verifier.js';

const ISSUER = 'https://auth.example.test';
const RESOURCE = 'https://intercal.example.test/api/mcp';
const RESOURCE_METADATA_URL = 'https://intercal.example.test/.well-known/oauth-protected-resource';

const CONFIG: McpAuthConfig = {
  resource: RESOURCE,
  authorizationServers: [ISSUER],
  scopesSupported: ['read'],
  requiredScopes: ['read'],
  algorithms: ['RS256'],
};

function mcpRequest(authorization?: string): Request {
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (authorization) headers.authorization = authorization;
  return new Request('https://intercal.example.test/api/mcp', { method: 'POST', headers });
}

// A stub verifier that returns a fixed principal — used to exercise the gate's scope/short-circuit
// logic without crypto. The real signature path is covered in the JwksTokenVerifier suite below.
function stubVerifier(scopes: string[]): OAuthTokenVerifier {
  return {
    async verifyAccessToken(token: string): Promise<AuthInfo> {
      return {
        token,
        clientId: 'client-1',
        scopes,
        expiresAt: Math.floor(Date.now() / 1000) + 600,
        resource: new URL(RESOURCE),
      };
    },
  };
}

describe('loadMcpAuthConfig — AS integration seam', () => {
  it('returns null (auth disabled) when no issuer is configured', () => {
    expect(loadMcpAuthConfig({})).toBeNull();
  });

  it('enables auth and derives the canonical resource from PUBLIC_API_BASE_URL', () => {
    const cfg = loadMcpAuthConfig({
      MCP_OAUTH_ISSUER: ISSUER,
      PUBLIC_API_BASE_URL: 'https://intercal.example.test/',
    });
    expect(cfg).not.toBeNull();
    expect(cfg?.resource).toBe(RESOURCE); // trailing slash stripped, /api/mcp appended
    expect(cfg?.authorizationServers).toEqual([ISSUER]);
    expect(cfg?.requiredScopes).toEqual(['read']);
  });

  it('prefers an explicit MCP_OAUTH_AUDIENCE over the derived URL', () => {
    const cfg = loadMcpAuthConfig({
      MCP_OAUTH_ISSUER: ISSUER,
      MCP_OAUTH_AUDIENCE: 'https://mcp.example.test',
      PUBLIC_API_BASE_URL: 'https://ignored.example.test',
    });
    expect(cfg?.resource).toBe('https://mcp.example.test');
  });

  it('throws when an issuer is set but no audience can be determined (half-config)', () => {
    expect(() => loadMcpAuthConfig({ MCP_OAUTH_ISSUER: ISSUER })).toThrow(/audience/i);
  });

  it('defaults the JWS alg allowlist to RS256 and honours an override', () => {
    const def = loadMcpAuthConfig({ MCP_OAUTH_ISSUER: ISSUER, MCP_OAUTH_AUDIENCE: RESOURCE });
    expect(def?.algorithms).toEqual(['RS256']);
    const override = loadMcpAuthConfig({
      MCP_OAUTH_ISSUER: ISSUER,
      MCP_OAUTH_AUDIENCE: RESOURCE,
      MCP_OAUTH_ALGORITHMS: 'ES256, RS256',
    });
    expect(override?.algorithms).toEqual(['ES256', 'RS256']);
  });
});

describe('buildProtectedResourceMetadata — RFC 9728', () => {
  it('advertises the resource, authorization servers, scopes, and header-only bearer method', () => {
    const doc = buildProtectedResourceMetadata(CONFIG);
    expect(doc.resource).toBe(RESOURCE);
    expect(doc.authorization_servers).toEqual([ISSUER]);
    expect(doc.scopes_supported).toEqual(['read']);
    expect(doc.bearer_methods_supported).toEqual(['header']);
  });
});

describe('gateMcpRequest — resource-server gate', () => {
  it('allows anonymous when auth is disabled (public-read posture)', async () => {
    const res = await gateMcpRequest(mcpRequest(), {
      config: null,
      verifier: null,
      resourceMetadataUrl: RESOURCE_METADATA_URL,
    });
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.principal.kind).toBe('anonymous');
  });

  it('rejects a missing token with 401 + WWW-Authenticate(resource_metadata)', async () => {
    const res = await gateMcpRequest(mcpRequest(), {
      config: CONFIG,
      verifier: stubVerifier(['read']),
      resourceMetadataUrl: RESOURCE_METADATA_URL,
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.response.status).toBe(401);
      const header = res.response.headers.get('www-authenticate') ?? '';
      expect(header).toContain('Bearer');
      expect(header).toContain(`resource_metadata="${RESOURCE_METADATA_URL}"`);
      expect(header).toContain('error="invalid_token"');
      expect(header).toContain('scope="read"');
    }
  });

  it('rejects an invalid token with 401', async () => {
    const failing: OAuthTokenVerifier = {
      async verifyAccessToken() {
        throw new Error('bad signature');
      },
    };
    const res = await gateMcpRequest(mcpRequest('Bearer garbage'), {
      config: CONFIG,
      verifier: failing,
      resourceMetadataUrl: RESOURCE_METADATA_URL,
    });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.response.status).toBe(401);
  });

  it('rejects a valid token missing a required scope with 403 insufficient_scope', async () => {
    const res = await gateMcpRequest(mcpRequest('Bearer ok'), {
      config: CONFIG,
      verifier: stubVerifier([]), // valid token, but no `read` scope
      resourceMetadataUrl: RESOURCE_METADATA_URL,
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.response.status).toBe(403);
      expect(res.response.headers.get('www-authenticate')).toContain('error="insufficient_scope"');
    }
  });

  it('authorizes a valid, in-scope token', async () => {
    const res = await gateMcpRequest(mcpRequest('Bearer ok'), {
      config: CONFIG,
      verifier: stubVerifier(['read']),
      resourceMetadataUrl: RESOURCE_METADATA_URL,
    });
    expect(res.ok).toBe(true);
    if (res.ok && res.principal.kind === 'authorized') {
      expect(res.principal.auth.clientId).toBe('client-1');
      expect(res.principal.auth.scopes).toContain('read');
    } else {
      throw new Error('expected authorized principal');
    }
  });
});

describe('JwksTokenVerifier — real JWT verification (local key set)', () => {
  let privateKey: Awaited<ReturnType<typeof generateKeyPair>>['privateKey'];
  let psPrivateKey: Awaited<ReturnType<typeof generateKeyPair>>['privateKey'];
  let jwks: { keys: JWK[] };
  let verifier: JwksTokenVerifier;

  beforeAll(async () => {
    const pair = await generateKeyPair('RS256');
    privateKey = pair.privateKey;
    const pub = await exportJWK(pair.publicKey);
    pub.kid = 'test-key';
    pub.alg = 'RS256';
    // A second, PS256 key under a DISTINCT kid — its public half is in the JWKS, so a PS256 token is
    // a VALID signature. Rejection then proves the alg allowlist (not a signature failure) is at work.
    const psPair = await generateKeyPair('PS256');
    psPrivateKey = psPair.privateKey;
    const psPub = await exportJWK(psPair.publicKey);
    psPub.kid = 'ps-key';
    psPub.alg = 'PS256';
    jwks = { keys: [pub, psPub] };
    verifier = new JwksTokenVerifier(CONFIG, createLocalJWKSet(jwks));
  });

  async function mint(opts: {
    audience?: string;
    issuer?: string;
    scope?: string;
    /** Sign with the PS256 key (header alg PS256, kid ps-key) instead of the default RS256 key. */
    ps?: boolean;
    /** Absolute exp (seconds since epoch). Defaults to 10 minutes out. */
    exp?: number;
  }): Promise<string> {
    const now = Math.floor(Date.now() / 1000);
    const alg = opts.ps ? 'PS256' : 'RS256';
    const kid = opts.ps ? 'ps-key' : 'test-key';
    return new SignJWT({ scope: opts.scope ?? 'read' })
      .setProtectedHeader({ alg, kid })
      .setSubject('user-1')
      .setIssuer(opts.issuer ?? ISSUER)
      .setAudience(opts.audience ?? RESOURCE)
      .setIssuedAt(now - 600)
      .setExpirationTime(opts.exp ?? now + 600)
      .sign(opts.ps ? psPrivateKey : privateKey);
  }

  it('accepts a correctly-signed, audience-bound token and extracts scopes', async () => {
    const token = await mint({ scope: 'read extra' });
    const info = await verifier.verifyAccessToken(token);
    expect(info.scopes).toEqual(['read', 'extra']);
    expect(info.resource?.toString()).toBe(RESOURCE);
    expect(info.expiresAt).toBeGreaterThan(Math.floor(Date.now() / 1000));
  });

  it('rejects a token issued for a different audience (RFC 8707 audience binding)', async () => {
    const token = await mint({ audience: 'https://other.example.test/api/mcp' });
    await expect(verifier.verifyAccessToken(token)).rejects.toThrow(/invalid access token/i);
  });

  it('rejects a token from a different issuer', async () => {
    const token = await mint({ issuer: 'https://evil.example.test' });
    await expect(verifier.verifyAccessToken(token)).rejects.toThrow(/invalid access token/i);
  });

  it('rejects an expired token', async () => {
    // exp well beyond the 5s clock tolerance.
    const token = await mint({ exp: Math.floor(Date.now() / 1000) - 120 });
    await expect(verifier.verifyAccessToken(token)).rejects.toThrow(/invalid access token/i);
  });

  it('rejects a validly-signed token whose alg is outside the allowlist (RS256-only)', async () => {
    // A genuinely valid PS256 signature (its public key is in the JWKS). Without an explicit
    // allowlist `jose` would accept it; the pinned RS256-only list must reject it — algorithm pinning.
    const token = await mint({ ps: true });
    await expect(verifier.verifyAccessToken(token)).rejects.toThrow(/invalid access token/i);
  });

  it('accepts the configured alg when the allowlist is widened (e.g. PS256)', async () => {
    const psVerifier = new JwksTokenVerifier(
      { ...CONFIG, algorithms: ['PS256'] },
      createLocalJWKSet(jwks),
    );
    const token = await mint({ ps: true });
    const info = await psVerifier.verifyAccessToken(token);
    expect(info.scopes).toContain('read');
  });
});
