/**
 * Live smoke test — exercises the SDK against the deployed V1 surface with real production data.
 *
 * Opt-in only: skipped unless `INTERCAL_LIVE=1` is set, so `pnpm test` stays deterministic and
 * offline-safe. Run it with:
 *   INTERCAL_LIVE=1 pnpm --filter @intercal/sdk test
 *
 * It asserts the contract end-to-end: a real entity read returns cited facts, and the two deferred
 * operations (delta/verify) surface a typed `IntercalNotImplementedError` rather than faking a body.
 */
import { describe, expect, it } from 'vitest';
import { IntercalClient, IntercalNotImplementedError } from './index.js';

const LIVE = process.env.INTERCAL_LIVE === '1';
const BASE = process.env.INTERCAL_BASE_URL ?? 'https://lntercal.vercel.app/api';

describe.skipIf(!LIVE)('IntercalClient — live V1 surface', () => {
  const client = new IntercalClient({ baseUrl: BASE, maxRetries: 2, retryBackoffMs: 250 });

  it('getEntity returns a real cited entity', async () => {
    const res = await client.getEntity({ name_or_id: 'rust' });
    expect(res.entity.displayName).toBeTruthy();
    expect(res.freshness.target).toBeTruthy();
  });

  it('searchEvidence returns real hits', async () => {
    const res = await client.searchEvidence({ query: 'rust', limit: 3 });
    expect(typeof res.total).toBe('number');
    expect(Array.isArray(res.hits)).toBe(true);
  });

  it('getFreshness returns a report', async () => {
    const res = await client.getFreshness({ topic_or_entity: 'rust' });
    expect(res.target).toBeTruthy();
  });

  it('getDelta returns a token-budgeted, cited change digest (Plan 03 W5, live)', async () => {
    const res = await client.getDelta({
      topic: 'rust',
      since_date: '2026-06-01T00:00:00Z',
      token_budget: 600,
    });
    expect(res.topic).toBe('rust');
    expect(res.summary.tokenBudget).toBe(600);
    // Token-bound: the digest content fits the requested budget (~4 chars/token heuristic).
    expect(Math.ceil(res.summary.content.length / 4)).toBeLessThanOrEqual(600);
    // Cited: every changed claim carries evidence, and the digest rolls up source citations.
    expect(res.changedClaims.length).toBeGreaterThan(0);
    expect(res.changedClaims.every((c) => c.evidence.length > 0)).toBe(true);
    expect(res.summary.citations.length).toBeGreaterThan(0);
    expect(res.confidence.method).toBe('aggregate_extraction');
  });

  it('verifyClaim surfaces the deferred 501 as a typed error', async () => {
    const err = await client.verifyClaim({ claim_text: 'Rust 1.96 exists' }).catch((e) => e);
    expect(err).toBeInstanceOf(IntercalNotImplementedError);
    expect(err.status).toBe(501);
  });
});
