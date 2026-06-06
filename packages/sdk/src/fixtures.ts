/**
 * Contract fixtures — real responses captured from the live V1 surface
 * (`https://lntercal.vercel.app/api/v1/*`) against production Neon data, frozen for deterministic
 * contract tests. These are typed against the generated contract (`@intercal/shared`), so a
 * contract change that breaks the SDK breaks compilation here too — the fixtures are a typed
 * tripwire, not faked product data.
 *
 * Regenerate by re-querying the live endpoints if the contract or shape changes; do not hand-edit
 * to satisfy a test.
 */
import type {
  EntityResponse,
  EvidenceResponse,
  FreshnessReport,
  IntercalComponents,
  SourcesResponse,
} from './index.js';

type ApiError = IntercalComponents['schemas']['ApiError'];

/** GET /v1/entity?name_or_id=rust */
export const entityFixture: EntityResponse = {
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
export const evidenceFixture: EvidenceResponse = {
  hits: [
    {
      documentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08',
      snippet:
        '94052`](https://github.com/nodejs/node/commit/5f4d794052)] - **build,win**: add Rust toolchain automated configuration Windows',
      score: 0.5,
      citation: {
        sourceDocumentId: 'eb07e354-c582-4f53-8c31-177d1ef2bf08',
        url: 'https://github.com/nodejs/node/releases/tag/v26.3.0',
        publishedAt: '2026-06-01T13:10:59.000Z',
      },
    },
    {
      documentId: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
      snippet: 'https://github.com/rust-lang/rust/releases/tag/1.96.0 rustbot',
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

/** GET /v1/freshness?topic_or_entity=rust */
export const freshnessFixture: FreshnessReport = {
  target: 'rust',
  lastUpdated: '2026-06-05T18:55:39.009Z',
  staleness: 'today',
};

/** GET /v1/sources?entity_or_claim_id=… — empty-but-valid SourcesResponse shape. */
export const sourcesFixture: SourcesResponse = {
  sources: [
    {
      id: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
      sourceId: 'rust-lang/rust',
      title: 'Rust 1.96.0',
      url: 'https://github.com/rust-lang/rust/releases/tag/1.96.0',
      publishedAt: '2026-05-28T17:50:42.000Z',
      ingestedAt: '2026-06-05T18:53:05.931Z',
      contentHash: 'sha256:fixture',
    },
  ],
};

/** A frozen error response: HTTP status + the `ApiError` body the surface served. */
interface ErrorFixture {
  status: number;
  body: ApiError;
}

/**
 * Error bodies captured live, one per taxonomy code the surface emits. Keyed by an explicit object
 * type (not `Record<string, …>`) so each access is statically known-present — tests read them
 * without non-null assertions.
 */
export const errorFixtures: {
  invalid_request: ErrorFixture;
  not_found: ErrorFixture;
  not_implemented: ErrorFixture;
  internal_error: ErrorFixture;
} = {
  invalid_request: {
    status: 400,
    body: {
      code: 'invalid_request',
      message: 'Invalid query parameters',
      details: { issues: [{ path: '/since_date', message: 'must match format "date-time"' }] },
    },
  },
  not_found: {
    status: 404,
    body: { code: 'not_found', message: 'No entity found for "zzz-nonexistent-xyz-123"' },
  },
  // 501 taxonomy mapping. The V1 synthesis bodies (get_delta W5, verify_claim W6) are now LIVE, so
  // no current endpoint serves this — it remains the captured shape of the `not_implemented` code so
  // the SDK's error mapping stays covered for any future deferred operation.
  not_implemented: {
    status: 501,
    body: {
      code: 'not_implemented',
      message: 'Plan NN — <operation>: deferred body not yet implemented.',
    },
  },
  internal_error: {
    status: 500,
    body: { code: 'internal_error', message: 'Unexpected failure' },
  },
};
