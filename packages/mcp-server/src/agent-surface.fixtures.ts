/**
 * Full-surface agent fixtures — REAL responses captured from the deployed V1 surface
 * (`https://lntercal.vercel.app/api/v1/*` against production Neon), frozen for deterministic
 * contract/agent tests (Plan 03 W8).
 *
 * These are the bytes the live API actually served, not faked product data. They are typed against
 * the generated contract (`@intercal/shared`), so a contract change that breaks the surface breaks
 * compilation here too — the fixtures are a typed tripwire. The same fixtures drive BOTH access
 * paths in `agent-surface.test.ts`: the MCP wire path (a real MCP client over the in-process
 * transport, server handlers fed these results) and the SDK/REST path (the typed client over an
 * injected fetch serving these as HTTP bodies). Driving both from one capture is what proves the
 * "one query layer, identical semantics" invariant.
 *
 * Regenerate by re-querying the live endpoints if the contract or shape changes; never hand-edit a
 * value to satisfy a test.
 */
import type { components } from '@intercal/shared';

type S = components['schemas'];

/** GET /v1/entity?name_or_id=rust */
export const entityFixture: S['EntityResponse'] = {
  entity: {
    id: '35f09cce-63e3-45bb-9699-cba7dc1ae7e9',
    type: 'product',
    displayName: 'rust',
    aliases: [],
    externalIds: [],
    importance: 0,
    firstSeen: '2026-06-05T18:55:39.009Z',
    lastUpdated: '2026-06-05T18:55:39.009Z',
    state: {},
  },
  relationships: [],
  facts: [
    {
      id: '23d5567a-2297-4a08-a8d3-0dac6fb4355a',
      subject: 'Rust',
      predicate: 'has_version',
      object: '1.96.0',
      qualifiers: {},
      normalizedText: 'Rust has version 1.96.0.',
      recordedAt: '2026-06-05T18:53:05.931Z',
      confidence: { score: 1, method: 'extraction' },
      status: 'active',
      contradiction: 'none',
      evidence: [{ sourceDocumentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367' }],
    },
  ],
  freshness: {
    target: 'rust',
    lastUpdated: '2026-06-05T18:55:39.009Z',
    staleness: 'today',
  },
};

/** GET /v1/evidence?query=rust&limit=2 */
export const evidenceFixture: S['EvidenceResponse'] = {
  hits: [
    {
      documentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08',
      snippet:
        '94052`](https://github.com/nodejs/node/commit/5f4d794052)] - **build,win**: add Rust toolchain automated configuration Windows (Mike McCready) [#63381](https://github.com/nodejs/node/pull/63381)',
      score: 0.5,
      citation: {
        sourceDocumentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08',
        url: 'https://github.com/nodejs/node/releases/tag/v26.3.0',
        publishedAt: '2026-06-01T13:10:59.000Z',
      },
    },
    {
      documentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
      snippet: 'https://github.com/rust-lang/rust/releases/tag/1.96.0 rustbot MDQ6VXNlcjQ3OTc5MjIz',
      score: 1,
      citation: {
        sourceDocumentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
        url: 'https://github.com/rust-lang/rust/releases/tag/1.96.0',
        publishedAt: '2026-05-28T17:50:42.000Z',
      },
    },
  ],
  total: 2,
};

/** GET /v1/sources?entity_or_claim_id=35f09cce-… (the rust entity) */
export const sourcesFixture: S['SourcesResponse'] = {
  sources: [
    {
      id: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
      sourceId: '15c5e7a0-6c0f-4f6c-97a4-add89d011086',
      title: 'rust-lang/rust Rust 1.96.0',
      url: 'https://github.com/rust-lang/rust/releases/tag/1.96.0',
      publishedAt: '2026-05-28T17:50:42.000Z',
      ingestedAt: '2026-06-05T18:51:40.288Z',
      language: 'en',
      contentHash: '4b0bd6b96c79cd3b7a3fbc8020544791c5536a34dffecb2af539bddfde623373',
    },
  ],
};

/** GET /v1/freshness?topic_or_entity=rust */
export const freshnessFixture: S['FreshnessReport'] = {
  target: 'rust',
  lastUpdated: '2026-06-05T18:58:44.405Z',
  coverage: 1,
  staleness: 'today; thin coverage (1 source)',
};

/**
 * GET /v1/delta?topic=rust&since_date=2026-06-04T00:00:00Z&token_budget=120
 *
 * A real budget-bounded digest: 12 changes detected, only the top 4 rendered to fit the (clamped,
 * min 200) token budget, "8 omitted" reported, coverage 0.333 — proving the budget is honoured
 * without silently dropping provenance. Every changed claim carries evidence; the summary rolls up
 * source citations and an aggregate confidence.
 */
export const deltaFixture: S['DeltaResponse'] = {
  topic: 'rust',
  since: '2026-06-04T00:00:00.000Z',
  summary: {
    topicOrEntity: 'rust',
    tokenBudget: 200,
    content:
      '12 claim changes recorded about "rust" since 2026-06-04 (plus 7 new fact versions recorded); scope: 1 resolved entity.\n1. [2026-06-05] 05a7b0a301 adds Rust toolchain general install instructions. (confidence 1.00)\n2. [2026-06-05] 9849690a1d edits Rust toolchain general install instructions. (confidence 1.00)\n3. [2026-06-05] Mike McCready authored the add Rust toolchain automated configuration Windows. (confidence 0.90)\n4. [2026-06-05] aarch64 softfloat targets have rustc_abi set to "softfloat". (confidence 1.00)\n4 of 12 changes shown within the 200-token budget; 8 omitted (most-recent/most-confident first).',
    citations: [
      {
        sourceDocumentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08',
        url: 'https://github.com/nodejs/node/releases/tag/v26.3.0',
        publishedAt: '2026-06-01T13:10:59.000Z',
      },
      {
        sourceDocumentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
        url: 'https://github.com/rust-lang/rust/releases/tag/1.96.0',
        publishedAt: '2026-05-28T17:50:42.000Z',
      },
    ],
    freshness: {
      target: 'rust',
      lastUpdated: '2026-06-05T18:58:54.605Z',
      coverage: 0.3333333333333333,
      staleness: 'today',
    },
    generatedAt: '2026-06-06T00:14:04.209Z',
  },
  changedClaims: [
    {
      id: '0efced53-7f7d-4281-98c2-e1cfd96666e1',
      subject: '05a7b0a301',
      predicate: 'adds',
      object: 'Rust toolchain general install instructions',
      qualifiers: {},
      normalizedText: '05a7b0a301 adds Rust toolchain general install instructions.',
      recordedAt: '2026-06-05T18:55:18.256Z',
      confidence: { score: 1, method: 'extraction' },
      status: 'active',
      contradiction: 'none',
      evidence: [{ sourceDocumentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08' }],
    },
    {
      id: '8a52b2e0-8db5-4659-a674-122f1264cc25',
      subject: '9849690a1d',
      predicate: 'edits',
      object: 'Rust toolchain general install instructions',
      qualifiers: {},
      normalizedText: '9849690a1d edits Rust toolchain general install instructions.',
      recordedAt: '2026-06-05T18:55:17.830Z',
      confidence: { score: 1, method: 'extraction' },
      status: 'active',
      contradiction: 'none',
      evidence: [{ sourceDocumentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08' }],
    },
    {
      id: 'e42e59e6-c9ac-457b-a09b-f42b212f1910',
      subject: 'Mike McCready',
      predicate: 'authored',
      object: 'add Rust toolchain automated configuration Windows',
      qualifiers: {},
      normalizedText:
        'Mike McCready authored the add Rust toolchain automated configuration Windows.',
      recordedAt: '2026-06-05T18:55:15.995Z',
      confidence: { score: 0.9, method: 'extraction' },
      status: 'active',
      contradiction: 'none',
      evidence: [{ sourceDocumentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08' }],
    },
    {
      id: 'be07146f-4dbc-42b1-b397-d520d4d69a9d',
      subject: 'aarch64 softfloat targets',
      predicate: 'has_property',
      object: 'rustc_abi set to "softfloat"',
      qualifiers: {},
      normalizedText: 'aarch64 softfloat targets have rustc_abi set to "softfloat".',
      recordedAt: '2026-06-05T18:53:09.352Z',
      confidence: { score: 1, method: 'extraction' },
      status: 'active',
      contradiction: 'none',
      evidence: [{ sourceDocumentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367' }],
    },
  ],
  changedEntities: [
    {
      id: '037db329-a75d-471b-a5b1-2d9a30ce4988',
      type: 'concept',
      displayName: 'Stop passing `--allow-undefined` on wasm targets',
    },
    { id: '527b4f5b-d949-457d-b6cf-029da0fa7727', type: 'person', displayName: 'Mike McCready' },
    { id: '1ac14459-3745-41c6-972f-ed0f8c1dcf51', type: 'product', displayName: 'Rustdoc' },
    { id: '7f4a165e-7150-4abe-b7d6-20c48bb90b89', type: 'organization', displayName: 'Rustdoc' },
    { id: '7ebfbb02-59d5-449f-a907-c658b95c5873', type: 'organization', displayName: 'Cargo' },
    { id: 'bd4454b0-356a-4d52-b76d-5b06980569c3', type: 'person', displayName: 'rustbot' },
    { id: '35f09cce-63e3-45bb-9699-cba7dc1ae7e9', type: 'product', displayName: 'rust' },
  ],
  confidence: { score: 0.975, method: 'aggregate_extraction' },
  freshness: {
    target: 'rust',
    lastUpdated: '2026-06-05T18:58:54.605Z',
    coverage: 0.3333333333333333,
    staleness: 'today',
  },
};

/**
 * GET /v1/claims/verify?claim_text=Rust%20has%20version%201.96.0
 *
 * A real, fully-cited `supported` verdict: confidence is evidence-weighted (relevance × extraction
 * confidence), supporting evidence traces to a source document, no contradictions.
 */
export const verifySupportedFixture: S['ClaimVerificationResponse'] = {
  claimText: 'Rust has version 1.96.0',
  verdict: 'supported',
  confidence: { score: 0.2107, method: 'evidence_match' },
  supportingEvidence: [
    {
      sourceDocumentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
      url: 'https://github.com/rust-lang/rust/releases/tag/1.96.0',
      publishedAt: '2026-05-28T17:50:42.000Z',
    },
  ],
  contradictingEvidence: [],
};

/**
 * GET /v1/claims/verify?claim_text=The%20moon%20is%20made%20of%20cheese
 *
 * A real `unverified` verdict with NO fabricated support — the honesty invariant: thin/absent
 * evidence yields confidence 0 and empty evidence lists, never invented backing.
 */
export const verifyUnverifiedFixture: S['ClaimVerificationResponse'] = {
  claimText: 'The moon is made of cheese',
  verdict: 'unverified',
  confidence: { score: 0, method: 'evidence_match' },
  supportingEvidence: [],
  contradictingEvidence: [],
};

/**
 * GET /v1/claims/verify?claim_text=Rust%20has%20version%201.96.0&as_of_date=2020-01-01T00:00:00Z
 *
 * The SAME claim that is `supported` today, evaluated point-in-time BEFORE it was recorded → a real
 * `unverified` verdict. Proves bitemporal correctness: the verdict respects `as_of_date`.
 */
export const verifyAsOfFixture: S['ClaimVerificationResponse'] = {
  claimText: 'Rust has version 1.96.0',
  verdict: 'unverified',
  confidence: { score: 0, method: 'evidence_match' },
  supportingEvidence: [],
  contradictingEvidence: [],
  asOf: '2020-01-01T00:00:00.000Z',
};
