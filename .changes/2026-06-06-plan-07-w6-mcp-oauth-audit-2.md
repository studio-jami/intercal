# Plan 07 W6 + Plan 04 W1 (MCP) — MCP OAuth audit-2: JWS alg pinning

Date: 2026-06-06
Type: fix
Packages: @intercal/mcp-server, scripts/dev, docs/operations, .env.example

## Summary

Second fresh-context security/cohesion pass over the MCP OAuth 2.1 resource server (pass 1 landed at
`ea5b8b0`). One real hardening — pinning the JWS signing-algorithm allowlist — plus tests, docs, and
roadmap. The rest of the resource-server surface audited clean: no auth bypass when an AS is
configured (the gate runs in `handleMcpRequest` before any JSON-RPC, for POST and GET alike;
anonymous mode applies only when no AS is wired); `iss`/`aud` (RFC 8707)/`exp`/`nbf` all enforced;
`alg: none` already rejected by `jose`; PRM (RFC 9728) + `WWW-Authenticate` spec-correct; the
external AS is an honest env seam, not faked. No contract or public-posture change.

> Re-verified (2026-06-06) against the official MCP Authorization spec for `2025-06-18` and
> `2025-11-25`, plus RFC 9728 / 8707 / 8414 / 9068 / OAuth 2.1, and `jose`'s `jwtVerify` semantics.

## Changes

- **JWS `alg` allowlist pinned** (`packages/mcp-server/src/auth/verifier.ts` + `config.ts`):
  `jwtVerify` is now called with an explicit `algorithms` allowlist (`MCP_OAUTH_ALGORITHMS`, default
  `RS256` via `MCP_DEFAULT_ALGORITHMS`). Without it, `jose` accepts **any** algorithm the resolved
  JWKS key supports — an RSA key also satisfies `PS256/PS384/PS512` — widening the surface to
  algorithm substitution. A token whose header `alg` is outside the list is rejected before signature
  math (`401`). `McpAuthConfig` gains a required `algorithms` field; `loadMcpAuthConfig` parses
  `MCP_OAUTH_ALGORITHMS` (comma/space list) and defaults to `RS256`. The runbook had always claimed
  "RS256 JWT access tokens" — this makes the code enforce that claim.
- **Tests** (`packages/mcp-server/src/auth/auth.test.ts`): config default + override for the alg list;
  a **validly-signed** PS256 token (its public key in the JWKS, so the signature is genuine) is
  rejected under the RS256-only allowlist — proving rejection is the alg gate, not a signature
  failure — and accepted when the allowlist is widened to PS256.
- **Live harness** (`scripts/dev/verify-mcp-auth.mjs`): adds the same PS256-rejection check (8 checks).
- **Docs** `docs/operations/mcp-auth.md` (alg-pinning bullet + seam env + verification counts);
  `.env.example` (`MCP_OAUTH_ALGORITHMS`); Plan 07 W6 roadmap status.

## Verification

- `pnpm lint` · `pnpm typecheck` (6 pkgs) · `pnpm test` · `pnpm build` — all clean. mcp-server auth
  unit 17 (was 14) + web gate 6; full workspace suite green.
- **Contracts untouched** — MCP auth is transport-level; no TypeSpec change, no regeneration.
- **LIVE** (real Neon DB): `node scripts/dev/verify-mcp-auth.mjs` → **8/8** (was 7/7; added
  out-of-allowlist-alg → 401). Auth-disabled anonymous initialize/tools-list/tools-call still pass;
  auth-enabled PRM resolves, no-token → 401 + `WWW-Authenticate`, wrong-aud → 401, PS256 (out of
  allowlist) → 401, valid → tools/call authorized. No token/secret value written to any tracked
  file/output.

## Notes

- Override `MCP_OAUTH_ALGORITHMS` only if the AS signs with a different asymmetric alg (e.g. `ES256`).
- REST auth (Plan 07 W5) intentionally untouched. The tracked orchestrator log and `.env` untouched.
