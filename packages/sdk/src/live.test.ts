/**
 * Live smoke test — exercises the SDK against the deployed V1 surface with real production data.
 *
 * Opt-in only: skipped unless `INTERCAL_LIVE=1` is set, so `pnpm test` stays deterministic and
 * offline-safe. Run it with:
 *   INTERCAL_LIVE=1 pnpm --filter @intercal/sdk test
 *
 * It asserts the contract end-to-end: real reads return cited facts, and the two synthesis
 * operations (delta W5 / verify W6 — now live) return cited, confidence-scored, budget-bounded
 * results against production data.
 */
import { describe, expect, it } from 'vitest';
import { IntercalClient } from './index.js';

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

  it('verifyClaim returns a cited verdict against live data (Plan 03 W6, live)', async () => {
    const res = await client.verifyClaim({ claim_text: 'Rust has version 1.96.0' });
    expect(res.claimText).toBeTruthy();
    expect(['supported', 'partially_supported', 'contradicted', 'unverified']).toContain(
      res.verdict,
    );
    expect(typeof res.confidence.score).toBe('number');
    // A `supported` verdict must rest on real cited supporting evidence — never fabricated.
    if (res.verdict === 'supported') {
      expect(res.supportingEvidence.length).toBeGreaterThan(0);
      expect(res.supportingEvidence[0]?.sourceDocumentId).toBeTruthy();
    }
  });

  it('verifyClaim is point-in-time correct: before the fact was recorded → unverified', async () => {
    const res = await client.verifyClaim({
      claim_text: 'Rust has version 1.96.0',
      as_of_date: '2020-01-01T00:00:00Z',
    });
    expect(res.verdict).toBe('unverified');
    expect(res.confidence.score).toBe(0);
  });
});
