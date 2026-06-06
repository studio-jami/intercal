# REST Auth & Rate Limits

How the public REST surface (`/api/v1/*`) authenticates callers, scopes access, limits request
rate, and records usage. This is the durable runbook for Plan 07 W5 (REST auth) consolidated with
the REST portion of Plan 04 W1 (rate limits + usage events).

> Scope: REST only. MCP (`/api/mcp`) auth is OAuth 2.1 resource-server, a separate stream
> (Plan 07 W6) — its seam is intentionally untouched here.

## Posture: public read, keys raise limits

Intercal is a **public read substrate**. The `/v1/*` surface is read-only, so:

- **Anonymous reads are allowed** under a tight per-IP rate limit. No key is required to read.
- **A valid API key raises the rate limit** and is the identity that future write/operator surfaces
  (feedback, subscriptions, admin) gate on via scopes.
- A **bad credential is an error, not an anonymous request**: presenting an invalid / revoked /
  expired key returns `401`, it does not silently fall back to the anonymous limit.

Infra routes (`/health`, `/openapi.json`) are open and unmetered; only `/v1/*` is gated.

## API keys (hashed + scoped)

- Keys are CSPRNG-generated: `ical_sk_<32-char base62>` (256 bits of entropy). The visible
  `ical_sk_` prefix is recorded for display and is **not** secret.
- **Only the SHA-256 hash is stored** (`api_keys.key_hash`, UNIQUE). The raw key is shown **once**
  at issuance and is never recoverable. SHA-256 (not a slow KDF) is correct here: the secret is a
  256-bit random token, so brute force is infeasible and a slow KDF would only tax every request.
- A key is usable only when `is_active = true` **and** `revoked_at IS NULL` **and**
  (`expires_at IS NULL OR expires_at > now()`). Revocation wins regardless of `is_active`.
- Scopes are a jsonb string array. Vocabulary (`packages/core/src/auth/scopes.ts`):
  - `read` — the `/v1/*` read surface (required for keyed read requests).
  - `submit:feedback`, `manage:subscriptions` — reserved for later plans (Plan 04 W4/W5).
  - `admin` — operator superscope (implies all). Never granted to public callers.

Schema: `db/migrations/0020_api_keys.sql` (already applied to the live Neon DB).

## Issuing & revoking keys (operator CLI)

`scripts/ops/keys.mjs` (alias `pnpm ops:keys`) is the operator-only lifecycle tool. It is a thin
wrapper over the audited `@intercal/core` functions — no key/hash logic is duplicated, there are no
hardcoded keys, and no auth-bypass path. It reads `DATABASE_URL` from the env or local `.env`, so
run it where that points at the target DB (a Neon branch for testing, prod for real issuance).

```sh
# Issue (the raw key is printed ONCE — copy it now; it is not stored):
pnpm ops:keys issue --name "agent X" --scopes read [--rpm 240] [--expires-days 90] \
                    [--owner-type service] [--owner-id team-7]

# List (metadata only — never any hash or raw material):
pnpm ops:keys list

# Revoke (sets the authoritative revoked_at + deactivates):
pnpm ops:keys revoke --id <uuid> --reason "rotated" --by "<operator>"
```

**Rotation** = issue a new key, hand it off, then revoke the old id. Never write a raw key to a
tracked file, log, or chat.

## Rate limits

Fixed 60-second window, enforced via a provider-agnostic store port
(`packages/core/src/ratelimit/`):

- **Port:** `RateLimitStorePort.incr(key, windowSeconds)` — atomic increment + window TTL.
- **Adapters:** `UpstashRateLimitStore` (Upstash Redis **REST** API; one shared counter across all
  instances — the production posture) and `MemoryRateLimitStore` (in-process fallback for local dev /
  single instance / tests; a real limiter with single-process scope, not a no-op).
- **Selection:** `createRateLimitStore()` returns Upstash when **both** `UPSTASH_REDIS_REST_URL`
  and `UPSTASH_REDIS_REST_TOKEN` are set, else the in-process store. No provider logic crosses the
  port boundary — switching stores is a config change, never a code change.

Default policy (`packages/api/src/auth/policy.ts`):

| Caller | Limit | Bucket |
| --- | --- | --- |
| Anonymous | **30 / min** per IP | `rl:ip:<ip>` |
| Keyed (default) | **120 / min** | `rl:key:<id>` |
| Keyed (override) | `api_keys.requests_per_minute` when set | `rl:key:<id>` |

These honor `docs/operations/resource-budget.md`: each limited request costs ~3 Upstash commands
(INCR + EXPIRE NX + PTTL, one pipelined round-trip), keeping the surface well under the 500k cmd/mo
Upstash allowance. Tune limits in `policy.ts` or raise a specific key via `requests_per_minute`.

If a counter is ever found with no TTL (PTTL `-1`/`-2` — e.g. a partial earlier write or a manual
`PERSIST`), the Upstash adapter re-arms the window with one extra `EXPIRE` so a bucket can never get
stuck incrementing forever (permanent 429). This is a rare repair path, not the steady-state cost.

### Trusted client IP (anti-spoofing)

The per-IP bucket keys off the **trusted** client IP, never an attacker-supplied value. On the
live Vercel deployment the platform overwrites `x-forwarded-for` / `x-real-ip` with the real client
IP and does not forward externally supplied values, so they are not client-spoofable there
(`packages/api/src/auth/middleware.ts`). The resolver prefers Vercel's single trusted `x-real-ip`;
if it must fall back to `x-forwarded-for` it takes the **right-most** hop (the address the nearest
trusted proxy observed), never the left-most (which on an appending proxy is the spoofable
client-claimed value). A forged left-most `x-forwarded-for` therefore cannot mint a fresh bucket to
evade the anonymous limit.

### Headers

Every `/v1/*` response carries both the IETF draft and `X-`-prefixed aliases:

```
RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset       (Reset = seconds to window reset)
X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
```

On a `429` the response adds `Retry-After: <seconds>`. The error body is the standard taxonomy:
`{ "code": "rate_limited", "message": "...", "details": { "retryAfter": N, "limit": N } }`.

### Fail-open

A rate-limit **store outage never takes the read surface down**: if `incr` throws, the request is
allowed through (without rate headers). **Auth failures are never fail-open** — a bad key is always
rejected.

## Usage events

Every request records exactly one `usage_events` row (best-effort; a recording failure never breaks
the request) for Plan 04 W6 observability:

- Recorded for **all** outcomes — `200`, `401`, `403`, `429`, `5xx` — so the abuse/traffic signal is
  complete. Error outcomes carry `error_code` (and `status_code` null, since the central error
  handler renders the response); success carries `status_code`.
- Fields: `api_key_id` (null for anonymous), `tool_name` (`"GET /v1/<route>"`), `status_code`,
  `error_code`, `latency_ms`, and an **anonymized** caller IP (IPv4 → /24, IPv6 → /48) + user agent.
- **No PII beyond the key id** and the anonymized network prefix. The raw key is never stored.

Schema: `db/migrations/0021_usage_events.sql`.

## Error taxonomy (status mapping)

`packages/api/src/app.ts` maps error codes to HTTP status; the SDK (`@intercal/sdk`) mirrors them as
typed errors:

| Code | Status | Meaning |
| --- | --- | --- |
| `invalid_request` | 400 | params failed contract validation |
| `unauthorized` | 401 | missing / invalid / revoked / expired key |
| `forbidden` | 403 | valid key, missing required scope |
| `not_found` | 404 | no match |
| `rate_limited` | 429 | over the window (`Retry-After` set) |
| `internal_error` | 500 | unexpected failure |

## Local dev

With no Upstash REST creds in `.env`, the in-process store is used automatically — a real per-minute
limiter scoped to the single dev process. No explicit "bypass" flag exists; to exercise higher
limits locally, issue a key (`pnpm ops:keys issue`) and send `Authorization: Bearer <key>`, or
raise the constants in `policy.ts`. There is no production auth-bypass path.

## Live verification

`scripts/dev/verify-auth.mjs` drives the full middleware in-process against a real DB (use a
disposable Neon branch). It issues keys, then asserts valid/invalid/revoked/expired (401/403),
the 429 + headers path, the anonymous posture, hashed-only storage, and `usage_events` recording:

```sh
DATABASE_URL=<neon-branch-url> node scripts/dev/verify-auth.mjs
```
