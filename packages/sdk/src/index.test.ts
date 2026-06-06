/**
 * Fixture-backed contract tests for the SDK.
 *
 * An injected `fetch` serves the real-data fixtures in `fixtures.ts` (captured from the live V1
 * surface) and records the outgoing request, so each test asserts three things against the
 * generated contract: (1) the SDK builds the correct URL + query string, (2) it returns the typed
 * contract response unchanged, and (3) it maps the REST error taxonomy to the right typed error.
 *
 * No mocks hide behavior — the fixtures are real responses, and the request the SDK emits is the
 * one the live API accepts (covered separately by the live smoke test, gated on a network flag).
 */
import { describe, expect, it } from 'vitest';
import {
  entityFixture,
  errorFixtures,
  evidenceFixture,
  freshnessFixture,
  sourcesFixture,
} from './fixtures.js';
import {
  IntercalApiError,
  IntercalClient,
  IntercalInvalidRequestError,
  IntercalNetworkError,
  IntercalNotFoundError,
  IntercalNotImplementedError,
  IntercalServerError,
} from './index.js';

const BASE = 'https://example.test/api';

/** A fetch stub that records the last request and returns a fixed JSON response. */
function stubFetch(status: number, body: unknown) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const impl: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  };
  /** The single recorded request; throws if none happened, so tests avoid non-null assertions. */
  const lastCall = () => {
    const call = calls.at(-1);
    if (!call) throw new Error('stubFetch: expected a request but none was made');
    return call;
  };
  return { impl, calls, lastCall };
}

describe('IntercalClient — request building', () => {
  it('trims trailing slashes from baseUrl and builds the entity URL with query params', async () => {
    const { impl, lastCall } = stubFetch(200, entityFixture);
    const client = new IntercalClient({ baseUrl: `${BASE}//`, fetch: impl });
    await client.getEntity({ name_or_id: 'rust', at_date: '2026-01-01T00:00:00Z' });

    const url = new URL(lastCall().url);
    expect(url.origin + url.pathname).toBe(`${BASE}/v1/entity`);
    expect(url.searchParams.get('name_or_id')).toBe('rust');
    expect(url.searchParams.get('at_date')).toBe('2026-01-01T00:00:00Z');
  });

  it('omits undefined optional params from the query string', async () => {
    const { impl, lastCall } = stubFetch(200, evidenceFixture);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    await client.searchEvidence({ query: 'rust' });

    const url = new URL(lastCall().url);
    expect(url.searchParams.get('query')).toBe('rust');
    expect(url.searchParams.has('limit')).toBe(false);
    expect(url.searchParams.has('from_date')).toBe(false);
  });

  it('sends accept + bearer auth + extra headers', async () => {
    const { impl, lastCall } = stubFetch(200, freshnessFixture);
    const client = new IntercalClient({
      baseUrl: BASE,
      fetch: impl,
      apiKey: 'secret-token',
      headers: { 'x-trace': 'abc' },
    });
    await client.getFreshness({ topic_or_entity: 'rust' });

    const headers = new Headers(lastCall().init?.headers);
    expect(headers.get('accept')).toBe('application/json');
    expect(headers.get('authorization')).toBe('Bearer secret-token');
    expect(headers.get('x-trace')).toBe('abc');
  });

  it('POSTs feedback as bounded JSON with bearer auth', async () => {
    const body = {
      review: {
        id: '11111111-1111-4111-8111-111111111111',
        targetType: 'entity',
        targetId: '22222222-2222-4222-8222-222222222222',
        concernType: 'outdated',
        status: 'received',
        summary: 'Display name appears stale',
        createdAt: '2026-06-06T12:00:00Z',
      },
    };
    const { impl, lastCall } = stubFetch(200, body);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl, apiKey: 'secret-token' });
    const res = await client.submitFeedback({
      targetType: 'entity',
      targetId: '22222222-2222-4222-8222-222222222222',
      concernType: 'outdated',
      summary: 'Display name appears stale',
    });

    expect(res).toEqual(body);
    const call = lastCall();
    expect(call.url).toBe(`${BASE}/v1/feedback`);
    expect(call.init?.method).toBe('POST');
    const headers = new Headers(call.init?.headers);
    expect(headers.get('accept')).toBe('application/json');
    expect(headers.get('content-type')).toBe('application/json');
    expect(headers.get('authorization')).toBe('Bearer secret-token');
    expect(JSON.parse(String(call.init?.body))).toMatchObject({
      targetType: 'entity',
      concernType: 'outdated',
    });
  });
});

describe('IntercalClient — typed responses', () => {
  it('returns the EntityResponse fixture unchanged', async () => {
    const { impl } = stubFetch(200, entityFixture);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const res = await client.getEntity({ name_or_id: 'rust' });
    expect(res.entity.displayName).toBe('rust');
    expect(res.facts?.[0]?.evidence[0]?.sourceDocumentId).toBe(
      'de827bd8-5ffe-431e-8dfc-d3150573e367',
    );
    expect(res).toEqual(entityFixture);
  });

  it('returns the EvidenceResponse fixture with total + cited hits', async () => {
    const { impl } = stubFetch(200, evidenceFixture);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const res = await client.searchEvidence({ query: 'rust', limit: 2 });
    expect(res.total).toBe(2);
    expect(res.hits[0]?.citation.url).toContain('github.com');
  });

  it('returns the SourcesResponse fixture', async () => {
    const { impl } = stubFetch(200, sourcesFixture);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const res = await client.getSources({
      entity_or_claim_id: 'de827bd8-5ffe-431e-8dfc-d3150573e367',
    });
    expect(res.sources[0]?.sourceId).toBe('rust-lang/rust');
  });
});

describe('IntercalClient — error taxonomy', () => {
  it('maps 400 → IntercalInvalidRequestError with details.issues', async () => {
    const { status, body } = errorFixtures.invalid_request;
    const { impl } = stubFetch(status, body);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const err = await client.getDelta({ topic: 'rust', since_date: 'bad' }).catch((e) => e);
    expect(err).toBeInstanceOf(IntercalInvalidRequestError);
    expect(err.status).toBe(400);
    expect(err.code).toBe('invalid_request');
    expect((err.details as { issues: unknown[] }).issues).toHaveLength(1);
  });

  it('maps 404 → IntercalNotFoundError', async () => {
    const { status, body } = errorFixtures.not_found;
    const { impl } = stubFetch(status, body);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const err = await client.getEntity({ name_or_id: 'nope' }).catch((e) => e);
    expect(err).toBeInstanceOf(IntercalNotFoundError);
    expect(err.code).toBe('not_found');
  });

  it('maps a 501 not_implemented body → IntercalNotImplementedError', async () => {
    const { status, body } = errorFixtures.not_implemented;
    const { impl } = stubFetch(status, body);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const err = await client
      .getDelta({ topic: 'rust', since_date: '2024-01-01T00:00:00Z' })
      .catch((e) => e);
    expect(err).toBeInstanceOf(IntercalNotImplementedError);
    expect(err.status).toBe(501);
    expect(err.code).toBe('not_implemented');
  });

  it('maps 500 → IntercalServerError', async () => {
    const { status, body } = errorFixtures.internal_error;
    const { impl } = stubFetch(status, body);
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const err = await client.getFreshness({ topic_or_entity: 'x' }).catch((e) => e);
    expect(err).toBeInstanceOf(IntercalServerError);
    expect(err.status).toBe(500);
  });

  it('falls back to a generic IntercalApiError for an unmapped code', async () => {
    const { impl } = stubFetch(418, { code: 'teapot', message: 'short and stout' });
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const err = await client.getFreshness({ topic_or_entity: 'x' }).catch((e) => e);
    expect(err).toBeInstanceOf(IntercalApiError);
    expect(err).not.toBeInstanceOf(IntercalServerError);
    expect(err.code).toBe('teapot');
  });

  it('wraps a transport failure in IntercalNetworkError', async () => {
    const impl: typeof fetch = async () => {
      throw new TypeError('connection refused');
    };
    const client = new IntercalClient({ baseUrl: BASE, fetch: impl });
    const err = await client.getEntity({ name_or_id: 'rust' }).catch((e) => e);
    expect(err).toBeInstanceOf(IntercalNetworkError);
    expect(err.status).toBe(0);
    expect(err.code).toBe('network_error');
  });
});

describe('IntercalClient — retries', () => {
  it('retries transient 5xx then succeeds', async () => {
    let n = 0;
    const impl: typeof fetch = async () => {
      n += 1;
      if (n < 3) return new Response('boom', { status: 503 });
      return new Response(JSON.stringify(freshnessFixture), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    };
    const client = new IntercalClient({
      baseUrl: BASE,
      fetch: impl,
      maxRetries: 3,
      retryBackoffMs: 0,
    });
    const res = await client.getFreshness({ topic_or_entity: 'rust' });
    expect(res.target).toBe('rust');
    expect(n).toBe(3);
  });

  it('does not retry a 501 (deterministic deferred seam)', async () => {
    let n = 0;
    const impl: typeof fetch = async () => {
      n += 1;
      return new Response(JSON.stringify(errorFixtures.not_implemented.body), { status: 501 });
    };
    const client = new IntercalClient({
      baseUrl: BASE,
      fetch: impl,
      maxRetries: 3,
      retryBackoffMs: 0,
    });
    await client.getDelta({ topic: 'rust', since_date: '2024-01-01T00:00:00Z' }).catch(() => {});
    expect(n).toBe(1);
  });
});
