/**
 * Audience-bound JWT access-token verification for the MCP resource server.
 *
 * Implements the SDK's slim {@link OAuthTokenVerifier} contract (`verifyAccessToken`) so the result
 * drops into the standard MCP `AuthInfo` shape. Verification is delegated to `jose` — the vetted
 * JOSE library the MCP SDK itself depends on — so NO crypto is hand-rolled here:
 *
 *   - The token is a JWS verified against the Authorization Server's published JWKS (RFC 7517),
 *     fetched and cached by `jose.createRemoteJWKSet` (public keys only; the resource server never
 *     holds a signing key).
 *   - `iss` is pinned to the configured issuer, `aud` is pinned to THIS server's canonical resource
 *     identifier (RFC 8707 audience binding — the spec's central MUST: reject tokens not issued for
 *     us), and `exp`/`nbf` are enforced by `jose` with a small clock tolerance.
 *
 * Any failure is surfaced as the SDK's `InvalidTokenError`, which the resource-server gate renders
 * as a spec-correct `401` with a `WWW-Authenticate` challenge. Verification timing does not branch
 * on secret material (signature check is constant-work in `jose`; we add no early-out on token
 * contents), so this introduces no auth-timing side channel.
 */

import { InvalidTokenError } from '@modelcontextprotocol/sdk/server/auth/errors.js';
import type { OAuthTokenVerifier } from '@modelcontextprotocol/sdk/server/auth/provider.js';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import { createRemoteJWKSet, type JWTPayload, type JWTVerifyGetKey, jwtVerify } from 'jose';
import { MCP_DEFAULT_ALGORITHMS, type McpAuthConfig } from './config.js';

/** Default RFC 8414 JWKS location relative to an issuer when none is configured explicitly. */
function deriveJwksUri(issuer: string): string {
  const base = issuer.endsWith('/') ? issuer.slice(0, -1) : issuer;
  return `${base}/.well-known/jwks.json`;
}

/** Normalize the JWT `scope` (space-delimited string, OAuth standard) or `scopes` (array) claim. */
function extractScopes(payload: JWTPayload): string[] {
  const scope = payload.scope;
  if (typeof scope === 'string') return scope.split(/\s+/).filter(Boolean);
  const scopes = (payload as { scopes?: unknown }).scopes;
  if (Array.isArray(scopes)) return scopes.filter((s): s is string => typeof s === 'string');
  return [];
}

/**
 * A `jose`-backed JWT verifier bound to one Authorization Server + this resource's audience.
 *
 * The JWKS is created once (per process / cold start) and reused; `jose` caches keys and refreshes
 * on rotation, so verification stays cheap and serverless-safe (no per-request key fetch in steady
 * state).
 */
export class JwksTokenVerifier implements OAuthTokenVerifier {
  private readonly jwks: JWTVerifyGetKey;
  private readonly issuer: string;
  private readonly audience: string;
  private readonly algorithms: string[];

  /**
   * @param config resolved resource-server config (issuer + audience + JWKS URI).
   * @param keyResolver optional key-resolution function (a `jose` `JWTVerifyGetKey`). Defaults to a
   *   remote JWKS fetched from the AS. Injected ONLY by tests (a local key set) to exercise the real
   *   signature/audience/expiry verification path offline; production always uses the remote JWKS.
   */
  constructor(config: McpAuthConfig, keyResolver?: JWTVerifyGetKey) {
    const issuer = config.authorizationServers[0];
    if (!issuer) throw new Error('JwksTokenVerifier requires at least one authorization server.');
    this.issuer = issuer;
    this.audience = config.resource;
    // Pin the accepted JWS algorithms. Without this, `jose` accepts ANY alg the resolved key
    // supports (e.g. an RSA JWKS key also satisfies PS256/PS384/PS512), widening the attack surface
    // to algorithm substitution. RFC 9068 / OAuth 2.1 want the RS to constrain this explicitly.
    this.algorithms =
      config.algorithms.length > 0 ? config.algorithms : [...MCP_DEFAULT_ALGORITHMS];
    this.jwks = keyResolver ?? createRemoteJWKSet(new URL(config.jwksUri ?? deriveJwksUri(issuer)));
  }

  async verifyAccessToken(token: string): Promise<AuthInfo> {
    let payload: JWTPayload;
    try {
      // `jwtVerify` enforces signature (against the JWKS), `iss`, `aud`, and time claims. Audience
      // pinning here is the RFC 8707 / spec MUST: a token whose `aud` is not this resource is rejected.
      ({ payload } = await jwtVerify(token, this.jwks, {
        algorithms: this.algorithms,
        issuer: this.issuer,
        audience: this.audience,
        clockTolerance: 5,
      }));
    } catch (err) {
      // Collapse every verification failure (bad signature, wrong iss/aud, expired, malformed) into
      // a single InvalidTokenError → 401. We do not leak which check failed.
      const reason = err instanceof Error ? err.message : 'token verification failed';
      throw new InvalidTokenError(`Invalid access token: ${reason}`);
    }

    if (!payload.exp) {
      // The SDK's bearer contract requires an expiry; an everlasting access token is a misconfig.
      throw new InvalidTokenError('Access token has no expiration (exp) claim.');
    }

    return {
      token,
      clientId: typeof payload.client_id === 'string' ? payload.client_id : (payload.sub ?? ''),
      scopes: extractScopes(payload),
      expiresAt: payload.exp,
      resource: new URL(this.audience),
      extra: payload.sub ? { sub: payload.sub } : undefined,
    };
  }
}
