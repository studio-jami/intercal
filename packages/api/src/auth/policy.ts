/**
 * Rate-limit policy for the REST surface.
 *
 * Public-read posture (Plan 04 W1): the substrate is a public read API. Anonymous callers are
 * allowed to read under a TIGHT per-IP limit; presenting a valid key raises the limit (and is the
 * identity future write/operator surfaces gate on). A key may carry its own `requests_per_minute`
 * override (from `api_keys`); otherwise the default keyed limit applies.
 *
 * Limits are deliberately modest to honor docs/operations/resource-budget.md (Upstash 500k cmds/mo
 * ≈ 16k/day; each limited request costs ~3 Upstash commands). The window is fixed at 60s so the
 * standard `RateLimit-*` headers report a clean per-minute budget.
 */
export const RATE_WINDOW_SECONDS = 60;

/** Anonymous (no key): conservative per-IP budget — enough to browse, not to scrape. */
export const ANON_PER_MINUTE = 30;

/** Default for an authenticated key with no per-key override. */
export const KEYED_PER_MINUTE_DEFAULT = 120;

/** Resolve the effective per-minute limit for a request. */
export function perMinuteLimit(keyOverride: number | null | undefined, keyed: boolean): number {
  if (keyed) return keyOverride && keyOverride > 0 ? keyOverride : KEYED_PER_MINUTE_DEFAULT;
  return ANON_PER_MINUTE;
}
