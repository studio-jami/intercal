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
    const out = await this.pipeline([
      ['INCR', key],
      ['EXPIRE', key, String(windowSeconds), 'NX'],
      ['PTTL', key],
    ]);
    const incr = out[0];
    const expire = out[1];
    const pttl = out[2];
    if (incr?.error) throw new Error(`Upstash INCR error: ${incr.error}`);
    if (expire?.error) throw new Error(`Upstash EXPIRE error: ${expire.error}`);
    const count = Number(incr?.result ?? 0);
    let pttlMs = Number(pttl?.result ?? -1);

    // Self-heal a counter that has no TTL. PTTL is -1 (key exists, no expiry — EXPIRE NX never
    // armed it, e.g. a partial earlier write or a manual PERSIST) or -2 (key vanished between INCR
    // and PTTL). Without a TTL the counter would increment forever and never reset, permanently
    // locking out that IP/key bucket. Re-arm the window so a stuck bucket always recovers. This is
    // the rare path (one extra command only when a TTL is genuinely missing), so it does not move
    // the steady-state Upstash command budget (docs/operations/resource-budget.md).
    if (pttlMs < 0) {
      const repair = await this.pipeline([['EXPIRE', key, String(windowSeconds)]]);
      if (repair[0]?.error) throw new Error(`Upstash EXPIRE(repair) error: ${repair[0].error}`);
      pttlMs = windowSeconds * 1000;
    }
    const resetSeconds = pttlMs > 0 ? Math.ceil(pttlMs / 1000) : windowSeconds;
    return { count, resetSeconds };
  }

  /** POST a command array to Upstash's REST pipeline; returns results in command order. */
  private async pipeline(
    commands: ReadonlyArray<ReadonlyArray<string>>,
  ): Promise<Array<{ result?: number; error?: string }>> {
    const res = await this.fetchImpl(`${this.restUrl}/pipeline`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${this.restToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify(commands),
    });
    if (!res.ok) {
      throw new Error(`Upstash rate-limit pipeline failed: HTTP ${res.status}`);
    }
    // Pipeline returns an array of { result } | { error } in command order.
    return (await res.json()) as Array<{ result?: number; error?: string }>;
  }
}
