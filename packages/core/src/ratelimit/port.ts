/**
 * RateLimitStorePort — the provider-agnostic seam for the rate-limit counter store.
 *
 * Following the Intercal adapter rule (AGENTS.md): every external dependency sits behind a port and
 * no provider logic crosses the boundary. The REST middleware depends only on this interface; the
 * concrete store (Upstash Redis REST, or an in-process fallback) is selected at the edge by
 * `createRateLimitStore` and injected. Swapping the backing store is a config change, never a code
 * change in the auth/middleware layer.
 *
 * The store implements a single fixed-window primitive: `incr(key, windowSeconds)` atomically
 * increments a counter that the backend expires after `windowSeconds`. That is the minimal
 * operation a sliding/fixed-window limiter needs and maps cleanly onto Redis `INCR` + `EXPIRE`
 * (one round-trip via Upstash's pipeline) and onto a simple in-memory map for the fallback.
 */
export interface RateLimitResult {
  /** The counter value AFTER this increment, within the current window. */
  count: number;
  /** Whole seconds remaining until the current window resets (best-effort). */
  resetSeconds: number;
}

export interface RateLimitStorePort {
  /**
   * Atomically increment the counter at `key`, creating it with a `windowSeconds` TTL on first use.
   * Returns the post-increment count and the seconds until the window resets.
   *
   * Implementations must be fail-open at the call site's discretion: a store outage should never
   * hard-fail a read request (the middleware decides policy), so adapters surface errors by
   * throwing and the caller chooses whether to allow-through.
   */
  incr(key: string, windowSeconds: number): Promise<RateLimitResult>;
}
