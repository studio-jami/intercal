# Plan 07 W5 + Plan 04 W1 (REST) — Hashed scoped API keys, rate limits, usage events

Date: 2026-06-06
Type: feat
Packages: @intercal/core, @intercal/api, @intercal/sdk, scripts/ops, db (existing schema),
docs/operations

## Summary

The public REST surface (`/api/v1/*`) is now authenticated, scoped, rate-limited, and metered.
Anonymous reads remain allowed under a tight per-IP limit (public-read posture); a valid hashed,
scoped API key raises the limit and unlocks scoped surfaces. Every request records one
`usage_events` row for Plan 04 W6 observability. MCP auth (Plan 07 W6) is untouched.

## Changes

- **`@intercal/core` auth layer** (`src/auth/`): CSPRNG key generation (`ical_sk_<base62>`, 256-bit),
  SHA-256 hashing (raw key shown once, only the hash persisted), constant-time compare, bearer
  parsing; server-side `authenticateKey`/`authenticateHeader` (existence + active + revoked + expiry
  checks → `UnauthorizedError`); operator lifecycle `issueApiKey`/`revokeApiKey`/`listApiKeys`;
  scope vocabulary + `hasScope` (admin superscope); best-effort `recordUsageEvent`.
- **Rate-limit store port + adapters** (`src/ratelimit/`): provider-agnostic `RateLimitStorePort`
  (`incr(key, windowSeconds)`); `UpstashRateLimitStore` (Upstash Redis REST, one pipelined
  INCR+EXPIRE-NX+PTTL round-trip — shared counter across instances) and `MemoryRateLimitStore`
  (in-process fallback); `createRateLimitStore()` selects by env. No provider logic past the port.
- **New error types** `UnauthorizedError` (401), `ForbiddenError` (403), `RateLimitedError` (429)
  in `@intercal/core`; mapped in `packages/api/src/app.ts` and mirrored as typed SDK errors.
- **`@intercal/api` middleware** (`src/auth/`): mounted on `/v1/*` — resolves bearer key (401 on a
  bad credential, never a silent downgrade), enforces the `read` scope (403), per-key/per-IP fixed
  60s-window rate limiting (429 + `Retry-After` + `RateLimit-*`/`X-RateLimit-*` headers, fail-open on
  store outage), and records a `usage_events` row for every outcome with an anonymized IP
  (IPv4 /24, IPv6 /48). Default limits: anon 30/min, keyed 120/min (per-key override honored).
  CORS now allowlists `Authorization` and exposes the rate-limit headers.
- **`@intercal/core` Kysely types**: added `api_keys` + `usage_events` table interfaces (insert-aware
  `Generated`/`ColumnType` markers) mirroring the existing `db/migrations/0020`/`0021` schema.
- **Operator CLI** `scripts/ops/keys.mjs` (`pnpm ops:keys issue|list|revoke`): thin wrapper over the
  core lifecycle; prints the raw key exactly once, never logs it again; no hardcoded keys / bypass.
- **Live-verify harness** `scripts/dev/verify-auth.mjs`: drives the full middleware against a real DB.
- **Docs** `docs/operations/auth-and-rate-limits.md`: durable runbook (posture, keys, CLI, limits,
  headers, usage events, taxonomy, local dev, verification).

## Verification

- `pnpm lint` · `pnpm typecheck` · `pnpm test` · `pnpm build` — all clean. New tests: 12 core auth
  (keys/scopes/store) + 12 api middleware (anon/valid/invalid/revoked/expired/scope/429/usage).
- **Contracts untouched** (the `ApiError.code` field is a free string; the new codes need no TypeSpec
  change) — no regeneration required.
- **LIVE** against a throwaway Neon branch (created from prod default, deleted after):
  `api_keys`/`usage_events` present; `scripts/dev/verify-auth.mjs` → **17/17 pass** (hashed-only
  storage; valid 200; invalid/expired/revoked → 401; missing-scope → 403; over-limit → 429 with
  `Retry-After` + `RateLimit-Remaining: 0`; anonymous admitted; `usage_events` rows incl. keyed +
  rate_limited). `pnpm ops:keys issue/list/revoke` exercised end-to-end. No secret/key value written
  to any tracked file or output.

## Notes

- SHA-256 (not a slow KDF) is the correct hash for a 256-bit random bearer token; matches the
  schema's documented invariant.
- Rate limits honor `docs/operations/resource-budget.md` (~3 Upstash cmds/limited request).
- Deferred (explicit): MCP OAuth (Plan 07 W6), feedback/subscription scopes' enforcing endpoints
  (Plan 04 W4/W5), the observability cards that read `usage_events` (Plan 04 W6).
