import type { RateLimitResult, RateLimitStorePort } from './port.js';

/**
 * In-process fixed-window rate-limit store. The default fallback when no Upstash REST credentials
 * are configured (local dev, single-instance, or tests).
 *
 * Honest about its limits: counters live only in this process's memory, so in a multi-instance
 * deployment (e.g. several Vercel function instances) each instance limits independently. For the
 * pilot's bursty single-region traffic that is acceptable; for strict global limits, configure the
 * Upstash adapter (one shared counter across instances). This is NOT a mock — it is a real,
 * correct single-process limiter, just with single-process scope.
 */
export class MemoryRateLimitStore implements RateLimitStorePort {
  private readonly windows = new Map<string, { count: number; expiresAt: number }>();

  async incr(key: string, windowSeconds: number): Promise<RateLimitResult> {
    const now = Date.now();
    const existing = this.windows.get(key);
    if (!existing || existing.expiresAt <= now) {
      const expiresAt = now + windowSeconds * 1000;
      this.windows.set(key, { count: 1, expiresAt });
      this.sweep(now);
      return { count: 1, resetSeconds: windowSeconds };
    }
    existing.count += 1;
    return {
      count: existing.count,
      resetSeconds: Math.max(1, Math.ceil((existing.expiresAt - now) / 1000)),
    };
  }

  /** Opportunistically drop expired windows so the map cannot grow without bound. */
  private sweep(now: number): void {
    if (this.windows.size < 1024) return;
    for (const [k, v] of this.windows) {
      if (v.expiresAt <= now) this.windows.delete(k);
    }
  }
}
