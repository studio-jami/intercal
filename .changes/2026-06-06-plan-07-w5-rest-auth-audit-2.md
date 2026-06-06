# Plan 07 W5 + Plan 04 W1 (REST) — auth/rate-limit audit-2 hardening

Date: 2026-06-06
Type: fix
Packages: @intercal/api, @intercal/core, docs/operations

## Summary

Second fresh-context security/cohesion pass over the REST auth + rate-limit stream (pass 1 landed at
`a8916b1`). Two real hardenings and one anonymization-correctness fix; no contract or behavior change
to the public posture (anonymous reads, 401/403/429, MCP seam all unchanged and re-verified).

## Changes

- **Trusted client IP for per-IP limiting** (`packages/api/src/auth/middleware.ts`): the per-IP
  bucket now resolves the trusted client IP — prefer Vercel's platform-controlled `x-real-ip`, and
  when falling back to `x-forwarded-for` take the **right-most** hop (the address the nearest trusted
  proxy observed), never the spoofable left-most client-claimed value. A forged left-most
  `x-forwarded-for` can no longer mint a fresh bucket to evade the anonymous limit. (Vercel overwrites
  these headers, so the live surface was not exploitable; this removes the spoofable-on-an-appending-
  proxy pattern and the misleading "left-most" assumption.)
- **Rate-limit counter self-heal** (`packages/core/src/ratelimit/upstash.ts`): if a counter is found
  with no TTL (PTTL `-1`/`-2` — partial earlier write, vanished key, or a manual `PERSIST`), the
  adapter re-arms the window with one extra `EXPIRE`. Without this a TTL-less counter increments
  forever and never resets → permanent 429 lockout for that IP/key bucket. Also surfaces an `EXPIRE`
  command error instead of silently ignoring it. Steady-state cost is unchanged (the repair is a rare
  path); the pipeline body was factored into a private `pipeline()` helper.
- **IPv6 anonymization fix** (`middleware.ts` `anonymizeIp`): compressed `::` addresses were mangled
  (splicing across the `::` zero-run). Now derives the /48 from the groups left of `::` and returns
  null for addresses with no meaningful network prefix (e.g. `::1`). IPv4 path also validated.

## Verification

- `pnpm lint` · `pnpm typecheck` · `pnpm test` · `pnpm build` — all clean. New tests: 7 core
  (`upstash.test.ts`: pipeline shape, normal count, self-heal on PTTL -1/-2, INCR/EXPIRE/HTTP error
  paths, URL trailing-slash) + 3 api (`middleware.test.ts`: `x-real-ip` bucketing, spoofed left-most
  XFF cannot mint a bucket, IPv4 /24 anonymization). Core 90 pass, api 50 pass.
- **LIVE** against a throwaway Neon branch (deleted after): `scripts/dev/verify-auth.mjs` → **17/17**
  (hashed-only storage; valid 200; invalid/expired/revoked → 401; missing-scope → 403; over-limit →
  429 + `Retry-After` + `RateLimit-Remaining: 0`; anonymous admitted; `usage_events` incl. keyed +
  rate_limited).
- **LIVE deployed surface** (`lntercal.vercel.app`, currently running `a8916b1`): anonymous
  `/api/v1/freshness` → 200 with `RateLimit-Limit: 30`; invalid key → 401 `unauthorized`;
  `/api/mcp` `initialize` → 200 (MCP seam not touched by the REST middleware).

## Notes

- No secret/key value written to any tracked file or output. Contracts untouched (free-string
  `ApiError.code`). MCP OAuth (Plan 07 W6) intentionally untouched.
