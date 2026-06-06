/**
 * MCP OAuth 2.1 resource-server configuration — the Authorization Server (AS) integration seam.
 *
 * Per the MCP Authorization spec (2025-06-18 / 2025-11-25), the MCP server is an OAuth 2.1
 * RESOURCE SERVER; the AUTHORIZATION SERVER is explicitly out of scope of the spec ("may be hosted
 * with the resource server or a separate entity"). Plan 07 W6 owns the resource-server side in full
 * and treats the AS as a configurable, external integration point. This config is that seam:
 *
 *   - When `MCP_OAUTH_ISSUER` (+ a key source) is set, the resource server is ENABLED: it advertises
 *     the AS in its Protected Resource Metadata (RFC 9728) and validates audience-bound bearer
 *     access tokens issued by that AS (RFC 8707 / RFC 9068 `aud`), per the spec's MUSTs.
 *   - When unset, auth is DISABLED and the surface keeps its public-read posture (anonymous reads
 *     allowed) — the live default today, and spec-compliant because MCP authorization is OPTIONAL.
 *     This is NOT a bypass: there is no code path that accepts an invalid token while auth is on;
 *     "disabled" simply means the operator has not yet wired an AS. Wiring one is a config change
 *     (env only), never a code change — the same adapter posture as the rest of Intercal.
 *
 * No secrets live here: the issuer/JWKS/audience are public identifiers, and token signatures are
 * verified against the AS's published JWKS (public keys). The resource server never holds a signing
 * key and never issues tokens.
 */

/** The minimal scope an access token must carry to use the read tool surface. */
export const MCP_READ_SCOPE = 'read';

/**
 * Default JWS signing algorithm(s) accepted for access tokens. RFC 9068 access tokens are asymmetric
 * JWTs; RS256 is the near-universal AS default (Auth0/Okta/Keycloak/Entra/…). We pin an explicit
 * allowlist rather than letting the JWKS key type imply it, so a token cannot be verified under any
 * algorithm the key would technically permit (e.g. an RSA key also satisfies PS256/PS384/PS512) —
 * defence against algorithm-substitution. `none` is never accepted by `jose`. Override with
 * `MCP_OAUTH_ALGORITHMS` only if your AS signs with a different asymmetric alg (e.g. `ES256`).
 */
export const MCP_DEFAULT_ALGORITHMS = ['RS256'] as const;

/** Resolved resource-server configuration (auth enabled), or `null` when auth is disabled. */
export interface McpAuthConfig {
  /**
   * The canonical resource identifier for THIS MCP server (RFC 8707 / RFC 9728 `resource`), e.g.
   * `https://intercal.example/api/mcp`. Access tokens MUST carry this in their audience; the PRM
   * document advertises it as `resource`. No trailing slash (spec interoperability guidance).
   */
  resource: string;
  /**
   * One or more OAuth 2.1 Authorization Server issuer URLs (RFC 8414 `issuer`). Advertised in the
   * PRM `authorization_servers`; the first is used to derive the JWKS URI when one isn't given.
   */
  authorizationServers: string[];
  /** Explicit JWKS URI override. When unset it is derived from the first issuer (RFC 8414 default). */
  jwksUri?: string;
  /** Scopes the resource advertises as supported in its PRM (`scopes_supported`). */
  scopesSupported: string[];
  /**
   * Scopes a token MUST hold to call the tool surface. Empty = a valid audience-bound token is
   * sufficient (no scope gate). Mirrors the REST `read`-scope posture when populated.
   */
  requiredScopes: string[];
  /**
   * The JWS `alg` allowlist enforced during signature verification (RFC 9068 / OAuth 2.1 alg
   * pinning). A token whose header `alg` is not in this list is rejected before signature math —
   * closing algorithm-substitution within the key's applicable set. Defaults to
   * {@link MCP_DEFAULT_ALGORITHMS} (`RS256`).
   */
  algorithms: string[];
}

/** Strip a single trailing slash for canonical-URI consistency (spec guidance). */
function canonical(url: string): string {
  return url.endsWith('/') ? url.slice(0, -1) : url;
}

function splitList(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export interface McpAuthEnv {
  MCP_OAUTH_ISSUER?: string;
  MCP_OAUTH_JWKS_URI?: string;
  MCP_OAUTH_AUDIENCE?: string;
  MCP_OAUTH_SCOPES_SUPPORTED?: string;
  MCP_OAUTH_REQUIRED_SCOPES?: string;
  /** JWS alg allowlist for token verification (comma/space list); defaults to RS256. */
  MCP_OAUTH_ALGORITHMS?: string;
  /** Public base URL of the deployment; used to derive the canonical resource when no audience is set. */
  PUBLIC_API_BASE_URL?: string;
}

/**
 * Load the MCP resource-server config from the environment, or `null` when no AS is configured
 * (auth disabled → public-read posture). Selection edge: this is the ONLY place the AS wiring is
 * read; everything downstream depends on the resolved {@link McpAuthConfig} (or its absence).
 *
 * @throws if `MCP_OAUTH_ISSUER` is set but no resource audience can be determined — a half-configured
 *   resource server is a misconfiguration, not a silent fall-through to anonymous.
 */
export function loadMcpAuthConfig(env: McpAuthEnv = process.env): McpAuthConfig | null {
  const issuer = env.MCP_OAUTH_ISSUER?.trim();
  if (!issuer) return null;

  // The canonical resource identifier (token audience). Prefer the explicit audience; else derive
  // the MCP endpoint URL from the public base. Never guess silently — require one or the other.
  const explicitAudience = env.MCP_OAUTH_AUDIENCE?.trim();
  const base = env.PUBLIC_API_BASE_URL?.trim();
  const resource = explicitAudience
    ? canonical(explicitAudience)
    : base
      ? `${canonical(base)}/api/mcp`
      : undefined;
  if (!resource) {
    throw new Error(
      'MCP_OAUTH_ISSUER is set but no audience could be determined. Set MCP_OAUTH_AUDIENCE ' +
        '(the canonical resource URI of this MCP server) or PUBLIC_API_BASE_URL.',
    );
  }

  const scopesSupported = splitList(env.MCP_OAUTH_SCOPES_SUPPORTED);
  const requiredScopes = splitList(env.MCP_OAUTH_REQUIRED_SCOPES ?? MCP_READ_SCOPE);
  const algorithms = splitList(env.MCP_OAUTH_ALGORITHMS);

  return {
    resource,
    authorizationServers: splitList(issuer),
    jwksUri: env.MCP_OAUTH_JWKS_URI?.trim() || undefined,
    scopesSupported: scopesSupported.length > 0 ? scopesSupported : [MCP_READ_SCOPE],
    requiredScopes,
    algorithms: algorithms.length > 0 ? algorithms : [...MCP_DEFAULT_ALGORITHMS],
  };
}
