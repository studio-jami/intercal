/**
 * REST auth + rate-limit + usage middleware (Plan 07 W5 + Plan 04 W1, REST portion).
 *
 * Pipeline per `/v1/*` request:
 *   1. Resolve `Authorization: Bearer <key>` → authenticated principal, or anonymous. An invalid /
 *      revoked / expired key is a hard 401 (it is not silently downgraded to anonymous — presenting
 *      a bad credential is an error, not an anonymous request).
 *   2. Authorization: a keyed caller must hold the READ scope for the read surface (403 otherwise).
 *      Anonymous callers are allowed to read under the public-read posture.
 *   3. Rate limit via the injected `RateLimitStorePort` (Upstash REST in prod, in-memory fallback):
 *      per-key when authenticated (honoring any per-key override), else per-IP for anonymous. Over
 *      the window → 429 with `Retry-After`. Standard `RateLimit-*` headers are set on every response.
 *   4. Record a `usage_events` row (best-effort, never blocks) with the anonymized caller IP.
 *
 * The store outage posture is FAIL-OPEN: if the rate-limit store throws, the request is allowed
 * (the public read surface must not go dark because the counter store blipped) and the failure is
 * surfaced only via the absence of headers. Auth failures are never fail-open.
 */
import {
  type AuthenticatedKey,
  authenticateHeader,
  type Db,
  ForbiddenError,
  hasScope,
  IntercalError,
  RateLimitedError,
  type RateLimitStorePort,
  READ_SCOPE,
  recordUsageEvent,
} from '@intercal/core';
import type { Context, MiddlewareHandler } from 'hono';

export interface AuthMiddlewareOptions {
  db: Db;
  store: RateLimitStorePort;
  anonPerMinute: number;
  keyedPerMinuteDefault: number;
  windowSeconds: number;
}

/** Context vars the middleware attaches for handlers / observability. */
export interface AuthVars {
  apiKey: AuthenticatedKey | null;
}

/**
 * Anonymize a caller IP for storage: keep the network prefix, drop host bits. IPv4 → /24, IPv6 →
 * /48. This is enough to bucket abusers without retaining a full PII-grade address (AGENTS.md: no
 * PII beyond the key id).
 */
function anonymizeIp(ip: string | null): string | null {
  if (!ip) return null;
  const v4 = ip.split('.');
  if (v4.length === 4) return `${v4[0]}.${v4[1]}.${v4[2]}.0/24`;
  if (ip.includes(':')) {
    const groups = ip.split(':').filter(Boolean);
    return `${groups.slice(0, 3).join(':')}::/48`;
  }
  return null;
}

/** Best-effort client IP from standard proxy headers (Vercel/Cloud Run set x-forwarded-for). */
function clientIp(c: Context): string | null {
  const fwd = c.req.header('x-forwarded-for');
  if (fwd) return fwd.split(',')[0]?.trim() ?? null;
  return c.req.header('x-real-ip') ?? null;
}

function setRateHeaders(c: Context, limit: number, remaining: number, resetSeconds: number): void {
  // IETF draft `RateLimit-*` plus the widely-used `X-RateLimit-*` aliases for client compatibility.
  c.header('RateLimit-Limit', String(limit));
  c.header('RateLimit-Remaining', String(Math.max(0, remaining)));
  c.header('RateLimit-Reset', String(resetSeconds));
  c.header('X-RateLimit-Limit', String(limit));
  c.header('X-RateLimit-Remaining', String(Math.max(0, remaining)));
  c.header('X-RateLimit-Reset', String(resetSeconds));
}

/**
 * Build the auth+rate-limit+usage middleware. Mount it on the contract surface (`/v1/*`) so the
 * infra routes (`/health`, `/openapi.json`) stay open and unmetered.
 */
export function authMiddleware(opts: AuthMiddlewareOptions): MiddlewareHandler {
  const { db, store, anonPerMinute, keyedPerMinuteDefault, windowSeconds } = opts;

  return async (c, next) => {
    const start = Date.now();
    const ip = clientIp(c);
    const anonIp = anonymizeIp(ip);
    const ua = c.req.header('user-agent') ?? null;
    const toolName = `${c.req.method} ${new URL(c.req.url).pathname}`;

    // One usage row per request, recorded for EVERY outcome (200, 401, 403, 429, 5xx) so the abuse
    // and traffic signal is complete for Plan 04 W6 observability. `principal` is resolved inside
    // the try, so a 401 still records an anonymous-shaped attempt.
    let principalId: string | null = null;
    let statusCode: number | null = null;
    let errorCode: string | null = null;

    try {
      // 1. Authenticate (throws 401 on a bad credential; null = anonymous).
      const principal = await authenticateHeader(db, c.req.header('authorization'));
      c.set('apiKey', principal);
      principalId = principal?.id ?? null;

      // 2. Authorize: keyed callers need READ for the read surface. (Anonymous read is allowed.)
      if (principal && !hasScope(principal.scopes, READ_SCOPE)) {
        throw new ForbiddenError('API key lacks the required scope: read', {
          requiredScope: READ_SCOPE,
        });
      }

      // 3. Rate limit (fail-open on store error).
      const keyed = principal !== null;
      const limit = keyed
        ? principal.requestsPerMinute && principal.requestsPerMinute > 0
          ? principal.requestsPerMinute
          : keyedPerMinuteDefault
        : anonPerMinute;
      const bucket = keyed ? `rl:key:${principal.id}` : `rl:ip:${ip ?? 'unknown'}`;

      let overLimit = false;
      let resetSeconds = windowSeconds;
      try {
        const { count, resetSeconds: reset } = await store.incr(bucket, windowSeconds);
        resetSeconds = reset;
        setRateHeaders(c, limit, limit - count, reset);
        if (count > limit) overLimit = true;
      } catch {
        // Fail-open: a counter-store outage must not take down the public read surface.
      }

      if (overLimit) {
        c.header('Retry-After', String(resetSeconds));
        throw new RateLimitedError(
          'Rate limit exceeded. Slow down or use an API key for a higher limit.',
          { retryAfter: resetSeconds, limit },
        );
      }

      // 4. Run the handler.
      await next();
      statusCode = c.res.status;
    } catch (err) {
      errorCode = err instanceof IntercalError ? err.code : 'internal_error';
      throw err;
    } finally {
      void recordUsageEvent(db, {
        apiKeyId: principalId,
        toolName,
        statusCode: errorCode ? null : statusCode,
        errorCode,
        latencyMs: Date.now() - start,
        ipAddress: anonIp,
        userAgent: ua,
      });
    }
  };
}
