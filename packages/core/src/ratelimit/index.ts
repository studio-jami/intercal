/**
 * Rate-limit store selection — the single edge where the concrete provider is chosen.
 *
 * Adapter pattern (AGENTS.md): the rest of the codebase depends only on `RateLimitStorePort`. This
 * factory reads the environment and returns Upstash (shared, multi-instance) when REST credentials
 * are present, else the in-process fallback. No provider logic leaks past this boundary.
 */
import { MemoryRateLimitStore } from './memory.js';
import type { RateLimitStorePort } from './port.js';
import { UpstashRateLimitStore } from './upstash.js';

export { MemoryRateLimitStore } from './memory.js';
export type { RateLimitResult, RateLimitStorePort } from './port.js';
export { UpstashRateLimitStore } from './upstash.js';

export interface RateLimitStoreEnv {
  UPSTASH_REDIS_REST_URL?: string;
  UPSTASH_REDIS_REST_TOKEN?: string;
}

/**
 * Build the rate-limit store from the environment.
 *
 * - Both `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` set → Upstash REST (shared counter
 *   across all instances; the production posture).
 * - Otherwise → in-process fallback (local dev / single instance / tests). This is a real limiter
 *   with single-process scope, not a no-op.
 */
export function createRateLimitStore(env: RateLimitStoreEnv = process.env): RateLimitStorePort {
  const url = env.UPSTASH_REDIS_REST_URL;
  const token = env.UPSTASH_REDIS_REST_TOKEN;
  if (url && token) return new UpstashRateLimitStore(url, token);
  return new MemoryRateLimitStore();
}
