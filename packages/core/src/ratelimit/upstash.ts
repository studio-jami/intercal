import type { RateLimitResult, RateLimitStorePort } from './port.js';

/**
 * Upstash Redis REST rate-limit store. Talks to Upstash over its HTTP REST API (no TCP socket), so
 * it works in edge/serverless runtimes and shares one counter across all app instances.
 *
 * Provider logic is confined to this adapter — the middleware sees only `RateLimitStorePort`. The
 * fixed-window primitive is one pipelined round-trip:
 *   INCR key            → atomic increment
 *   EXPIRE key sec NX   → set the TTL only on the first hit of the window (NX = don't extend it)
 *   PTTL key            → ms remaining, to report an accurate reset
 *
 * Honors the resource budget (docs/operations/resource-budget.md): three Upstash commands per
 * limited request, batched into a single pipeline call. Keep limits sane so this stays well under
 * the 500k commands/mo allowance; anonymous traffic is the main driver, hence its tighter window.
 */
export class UpstashRateLimitStore implements RateLimitStorePort {
  constructor(
    private readonly restUrl: string,
    private readonly restToken: string,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    this.restUrl = restUrl.replace(/\/+$/, '');
  }

  async incr(key: string, windowSeconds: number): Promise<RateLimitResult> {
    const res = await this.fetchImpl(`${this.restUrl}/pipeline`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${this.restToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify([
        ['INCR', key],
        ['EXPIRE', key, String(windowSeconds), 'NX'],
        ['PTTL', key],
      ]),
    });
    if (!res.ok) {
      throw new Error(`Upstash rate-limit pipeline failed: HTTP ${res.status}`);
    }
    // Pipeline returns an array of { result } | { error } in command order.
    const out = (await res.json()) as Array<{ result?: number; error?: string }>;
    const incr = out[0];
    const pttl = out[2];
    if (incr?.error) throw new Error(`Upstash INCR error: ${incr.error}`);
    const count = Number(incr?.result ?? 0);
    const pttlMs = Number(pttl?.result ?? windowSeconds * 1000);
    // PTTL is -1 (no expiry) or -2 (missing) in edge cases; fall back to the full window.
    const resetSeconds = pttlMs > 0 ? Math.ceil(pttlMs / 1000) : windowSeconds;
    return { count, resetSeconds };
  }
}
