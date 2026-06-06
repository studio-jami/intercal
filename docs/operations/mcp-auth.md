# MCP Auth — OAuth 2.1 Resource Server

How the MCP surface (`/api/mcp`, stateless Streamable HTTP) authenticates callers. This is the
durable runbook for Plan 07 W6 (MCP auth) / the MCP portion of Plan 04 W1. It is the MCP counterpart
to `docs/operations/auth-and-rate-limits.md` (REST API keys); the two surfaces use different
mechanisms by design and do not share one middleware.

> Spec verified (2026-06-05) against the official MCP Authorization spec for the protocol versions
> the server negotiates (`2025-06-18` and `2025-11-25`), plus RFC 9728 / RFC 8707 / RFC 8414 / OAuth
> 2.1. Re-verify these drift-prone facts at the scheduled check (AGENTS.md).

## Model: MCP server is an OAuth 2.1 Resource Server

Per the MCP Authorization spec, a protected MCP server is an **OAuth 2.1 resource server**: it does
not issue tokens, it **validates** access tokens issued by an **Authorization Server (AS)**. The AS
is explicitly out of scope of the MCP spec ("may be hosted with the resource server or a separate
entity") — so Intercal implements the resource-server side in full and treats the AS as a
**configurable integration seam** (see "Authorization Server seam" below).

MCP authorization is **OPTIONAL** in the spec. Intercal uses that to run two modes:

| Mode | When | Behaviour |
| --- | --- | --- |
| **Disabled** (public-read) | no AS configured (`MCP_OAUTH_ISSUER` unset) — the live default today | Anonymous reads allowed; the surface is open, exactly as the REST `/v1/*` surface is. No token required. |
| **Enabled** (resource server) | an AS is configured | A valid, audience-bound bearer access token is **required** on the tool surface. Missing/invalid → `401`; valid but missing scope → `403`. |

This mirrors the REST public-read posture (`docs/operations/auth-and-rate-limits.md`): the substrate
is a public read surface, and OAuth raises the bar from anonymous to scoped identity. "Disabled" is
**not a bypass** — there is no code path that accepts an invalid token while auth is on; it simply
means no AS has been wired yet. Turning auth on is a **config change (env only)**, never a code change.

## What the resource server enforces (enabled mode)

Implemented in `packages/mcp-server/src/auth/` and run by `handleMcpRequest` **before** any JSON-RPC
handling (`packages/mcp-server/src/web.ts`):

- **Bearer token required.** `Authorization: Bearer <token>` (header only; tokens in the query
  string are rejected — `bearer_methods_supported: ["header"]`). Missing → `401`.
- **Token validation** (`JwksTokenVerifier`, built on `jose` — the vetted JOSE library the MCP SDK
  itself depends on; no hand-rolled crypto):
  - **Signature** verified against the AS's published **JWKS** (RFC 7517), fetched + cached by
    `jose.createRemoteJWKSet` (public keys only; the resource server holds no signing key).
  - **Algorithm** pinned to an explicit allowlist (`MCP_OAUTH_ALGORITHMS`, default `RS256`). The
    token's header `alg` MUST be in the list or it is rejected before signature math. This closes
    algorithm-substitution: without it, `jose` accepts any alg the resolved JWKS key supports (an RSA
    key also satisfies `PS256/PS384/PS512`). `alg: none` is never accepted. Widen the list only if
    your AS signs with a different asymmetric alg (e.g. `ES256`).
  - **Issuer** (`iss`) pinned to the configured AS.
  - **Audience** (`aud`) pinned to this server's canonical resource identifier — the central spec
    MUST (**RFC 8707** audience binding / RFC 9068): a token not issued for this resource is rejected.
    This prevents token-replay across services and the confused-deputy class of attacks.
  - **Expiry/nbf** enforced (5s clock tolerance). A token with no `exp` is rejected.
  - Any failure → `401` with a single opaque reason (we do not leak which check failed); timing does
    not branch on secret material.
- **Scope** enforcement: the required scope (`read` by default) must be present, else `403`
  `insufficient_scope`. Configurable via `MCP_OAUTH_REQUIRED_SCOPES`.

### Error responses (spec-correct)

`401` (missing/invalid token):

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="…", scope="read",
                  resource_metadata="https://<domain>/.well-known/oauth-protected-resource"
```

`403` (valid token, missing scope):

```
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", error_description="…", scope="read",
                  resource_metadata="https://<domain>/.well-known/oauth-protected-resource"
```

The `resource_metadata` parameter (RFC 9728 §5.1) points the client at the Protected Resource
Metadata document, which is how it discovers the AS and bootstraps the OAuth flow.

## Discovery: Protected Resource Metadata (RFC 9728)

The MCP server publishes a **Protected Resource Metadata** document so clients can discover the AS.
Served at both well-known locations the spec directs clients to probe:

- `/.well-known/oauth-protected-resource` (root)
- `/.well-known/oauth-protected-resource/api/mcp` (path-suffixed for the MCP endpoint, 2025-11-25)

Routes: `packages/dashboard/app/.well-known/oauth-protected-resource/route.ts` and
`.../api/mcp/route.ts`. The document (built by `buildProtectedResourceMetadata`):

```json
{
  "resource": "https://<domain>/api/mcp",
  "authorization_servers": ["https://<your-as-issuer>"],
  "scopes_supported": ["read"],
  "bearer_methods_supported": ["header"],
  "resource_name": "Intercal MCP"
}
```

When auth is **disabled**, these endpoints return `404` (there is no protected resource to
advertise) — the correct signal for the public-read posture.

The full client-side OAuth flow (AS metadata discovery RFC 8414, PKCE, RFC 8707 `resource` parameter,
dynamic/CIMD client registration) is the **client's and AS's** responsibility per spec; the resource
server's job is the validation + discovery document above.

## Authorization Server seam (how to enable auth)

The AS is wired entirely through environment variables (`packages/mcp-server/src/auth/config.ts`).
Set these on Vercel (via the secret fan-out, `docs/operations/secrets.md`) to turn auth on:

```
MCP_OAUTH_ISSUER=https://<as-issuer>          # required to enable; RFC 8414 issuer URL
MCP_OAUTH_AUDIENCE=https://<domain>/api/mcp   # canonical resource URI (token aud). If unset,
                                              #   derived as <PUBLIC_API_BASE_URL>/api/mcp
MCP_OAUTH_JWKS_URI=https://<as>/…/jwks.json   # optional; defaults to <issuer>/.well-known/jwks.json
MCP_OAUTH_SCOPES_SUPPORTED=read               # optional; advertised in PRM (default: read)
MCP_OAUTH_REQUIRED_SCOPES=read                # optional; scope gate (default: read; empty = no gate)
MCP_OAUTH_ALGORITHMS=RS256                     # optional; pinned JWS alg allowlist (default: RS256)
```

Any OAuth 2.1 / OIDC AS that issues **RS256 JWT access tokens** with the correct `iss`/`aud`/`exp`
and publishes a JWKS works — e.g. Auth0, Okta, Keycloak, Stytch, WorkOS, Clerk, or a self-hosted AS.
No secret lives in the resource server: issuer/JWKS/audience are public identifiers and signatures
are checked against public keys. **Never** put an AS client secret or signing key in tracked files.

> Half-config guard: setting `MCP_OAUTH_ISSUER` without a determinable audience (no
> `MCP_OAUTH_AUDIENCE` and no `PUBLIC_API_BASE_URL`) throws at startup — a misconfigured resource
> server fails loud rather than silently falling back to anonymous.

## Statelessness / serverless

The gate adds no per-session state. The JWKS verifier is created once per cold start (cached by the
resolved resource id) and reused across invocations; `jose` caches keys and refreshes on rotation, so
there is no per-request key fetch in steady state. This fits the stateless Streamable HTTP mount
(`sessionIdGenerator: undefined`, `enableJsonResponse: true`) on Vercel functions.

## Verification

In-process against a real DB (drives the production `handleMcpRequest` path; mints a test token with
a local key set standing in for the AS — no live AS or network needed; never prints secrets):

```sh
node scripts/dev/verify-mcp-auth.mjs        # needs DATABASE_URL (env or .env)
```

It asserts (live, 8 checks): auth-disabled initialize / tools-list / tools-call still work
(anonymous); and auth-enabled PRM document resolves, no-token → 401 + `WWW-Authenticate`,
wrong-audience token → 401 (RFC 8707), a validly-signed token whose `alg` is outside the allowlist
(PS256 vs the RS256 default) → 401 (algorithm pinning), valid token → `tools/call` authorized.

Unit/integration tests: `packages/mcp-server/src/auth/auth.test.ts` (config seam incl. the alg
allowlist, PRM, gate 401/403/anon/authorized, real JWT signature/issuer/audience/expiry, and
algorithm pinning — a validly-signed out-of-allowlist token is rejected) and `web.test.ts` (gate
wired into the handler). Existing initialize/tools-list/unknown-tool tests confirm the surface is
unchanged in disabled mode.

The anonymous MCP surface (`node scripts/dev/verify-mcp.mjs <url>`) continues to work unchanged when
no AS is configured.
