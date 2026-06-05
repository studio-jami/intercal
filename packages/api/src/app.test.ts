/**
 * REST API route tests — W2 hardening.
 *
 * Covers the HTTP layer: validation (400), deferred stubs (501), JSON 404 for unknown
 * routes, infrastructure endpoints (/health, /openapi.json), and the sources UUID guard.
 *
 * These tests use `null as unknown as Db` because every covered path either:
 *   a) fails Ajv validation before reaching the DB, or
 *   b) throws `NotImplementedError` before touching the DB (verify_claim, a Plan 03 W6 seam), or
 *   c) is served directly from the app without a DB call (/health, /openapi.json, notFound).
 *
 * get_delta is now DB-backed (Plan 03 W5); its success path is covered by the live Neon
 * integration verification, so only its validation (400) cases live here.
 *
 * Integration tests against a live DB belong in a separate fixture; do not add them here.
 */

import type { Db } from '@intercal/core';
import { Hono } from 'hono';
import { describe, expect, it } from 'vitest';
import { createApp } from './app.js';

// biome-ignore lint/suspicious/noExplicitAny: intentional null DB for request-validation-only tests
const nullDb = null as any as Db;
const app = createApp(nullDb);

/** Fire a GET against the Hono app. */
async function get(path: string, headers?: Record<string, string>) {
  const res = await app.request(`http://localhost${path}`, { headers });
  const body = (await res.json()) as Record<string, unknown>;
  return { status: res.status, body, ct: res.headers.get('content-type'), res };
}

// ---------------------------------------------------------------------------
// Infrastructure
// ---------------------------------------------------------------------------

describe('GET /health', () => {
  it('returns 200 { status: ok }', async () => {
    const { status, body } = await get('/health');
    expect(status).toBe(200);
    expect(body).toEqual({ status: 'ok' });
  });
});

describe('GET /openapi.json', () => {
  it('returns 200 with a valid OpenAPI document', async () => {
    const { status, body } = await get('/openapi.json');
    expect(status).toBe(200);
    expect(body).toMatchObject({
      openapi: expect.stringMatching(/^3\./),
      paths: expect.objectContaining({ '/v1/entity': expect.any(Object) }),
    });
  });
});

// ---------------------------------------------------------------------------
// JSON 404 for unknown routes
// ---------------------------------------------------------------------------

describe('unknown route', () => {
  it('returns 404 with JSON ApiError body (not text/plain)', async () => {
    const { status, body, ct } = await get('/v1/notaroute');
    expect(status).toBe(404);
    expect(ct).toMatch('application/json');
    expect(body).toMatchObject({ code: 'not_found', message: expect.any(String) });
  });

  it('returns 404 JSON for a top-level unknown path', async () => {
    const { status, body } = await get('/completely-unknown');
    expect(status).toBe(404);
    expect(body).toMatchObject({ code: 'not_found' });
  });
});

// ---------------------------------------------------------------------------
// Mounted under a prefix — production shape (dashboard does new Hono().route('/api', app))
//
// Hono lets the PARENT router own the `notFound` fallback, so a sub-app's `notFound` never
// fires for unmatched sub-paths. These assert the JSON ApiError 404 still reaches the contract
// surface when mounted, and that the scoped catch-all does NOT swallow a sibling surface
// (e.g. the MCP server at `/api/mcp`).
// ---------------------------------------------------------------------------

describe('mounted under /api prefix', () => {
  // biome-ignore lint/suspicious/noExplicitAny: null DB; these paths never reach the query layer
  const mounted = new Hono().route('/api', createApp(null as any));

  it('returns JSON 404 for an unknown /api/v1/* route (not Hono text/plain)', async () => {
    const res = await mounted.request('http://localhost/api/v1/notaroute');
    const body = (await res.json()) as Record<string, unknown>;
    expect(res.status).toBe(404);
    expect(res.headers.get('content-type')).toMatch('application/json');
    expect(body).toMatchObject({ code: 'not_found' });
  });

  it('still serves a real /api/v1/* route shape (400 validation, not a swallowed 404)', async () => {
    const res = await mounted.request('http://localhost/api/v1/entity');
    const body = (await res.json()) as Record<string, unknown>;
    expect(res.status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('does NOT intercept a sibling /api/mcp surface (scoped to /v1/*)', async () => {
    // No /api/mcp is registered here, so it falls through to the parent's default 404 —
    // proving createApp's catch-all did not claim the path. (text/plain, not JSON.)
    const res = await mounted.request('http://localhost/api/mcp');
    expect(res.status).toBe(404);
    expect(res.headers.get('content-type') ?? '').not.toMatch('application/json');
  });
});

// ---------------------------------------------------------------------------
// GET /v1/delta — requires topic + since_date (date-time)
// ---------------------------------------------------------------------------

describe('GET /v1/delta', () => {
  it('400 when topic is missing', async () => {
    const { status, body } = await get('/v1/delta?since_date=2026-01-01T00:00:00Z');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when since_date is missing', async () => {
    const { status, body } = await get('/v1/delta?topic=rust');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when since_date is a bare date (not date-time)', async () => {
    const { status, body } = await get('/v1/delta?topic=rust&since_date=2026-01-01');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
    const details = body.details as Record<string, unknown>;
    const issues = details.issues as Array<Record<string, unknown>>;
    expect(issues[0]?.message).toMatch(/date-time/);
  });

  it('400 when until_date is a bare date (not date-time)', async () => {
    const { status, body } = await get(
      '/v1/delta?topic=rust&since_date=2026-01-01T00:00:00Z&until_date=2026-06-01',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  // The success path (valid params → 200 token-budgeted digest) is DB-backed (Plan 03 W5) and is
  // covered by the live Neon integration verification, not this validation-only suite (null DB).

  it('400 when token_budget is not an integer', async () => {
    const { status, body } = await get(
      '/v1/delta?topic=rust&since_date=2026-01-01T00:00:00Z&token_budget=abc',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// GET /v1/entity — requires name_or_id
// ---------------------------------------------------------------------------

describe('GET /v1/entity', () => {
  it('400 when name_or_id is missing', async () => {
    const { status, body } = await get('/v1/entity');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when at_date is a bare date (not date-time)', async () => {
    const { status, body } = await get('/v1/entity?name_or_id=rust&at_date=2026-01-01');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
    const details = body.details as Record<string, unknown>;
    const issues = details.issues as Array<Record<string, unknown>>;
    expect(issues[0]?.message).toMatch(/date-time/);
  });

  it('400 when token_budget is not an integer', async () => {
    const { status, body } = await get('/v1/entity?name_or_id=rust&token_budget=abc');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// GET /v1/evidence — requires query; limit in [1, 100]
// ---------------------------------------------------------------------------

describe('GET /v1/evidence', () => {
  it('400 when query param is missing', async () => {
    const { status, body } = await get('/v1/evidence');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when limit exceeds maximum (100)', async () => {
    const { status, body } = await get('/v1/evidence?query=rust&limit=200');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when limit is below minimum (1)', async () => {
    const { status, body } = await get('/v1/evidence?query=rust&limit=0');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when from_date is a bare date (not date-time)', async () => {
    const { status, body } = await get('/v1/evidence?query=rust&from_date=2026-01-01');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when to_date is a bare date (not date-time)', async () => {
    const { status, body } = await get('/v1/evidence?query=rust&to_date=2026-06-01');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// GET /v1/claims/verify — requires claim_text; body deferred to Plan 03 W6
// ---------------------------------------------------------------------------

describe('GET /v1/claims/verify', () => {
  it('400 when claim_text is missing', async () => {
    const { status, body } = await get('/v1/claims/verify');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when as_of_date is a bare date (not date-time)', async () => {
    const { status, body } = await get(
      '/v1/claims/verify?claim_text=Rust+has+version+1.96.0&as_of_date=2026-01-01',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
    const details = body.details as Record<string, unknown>;
    const issues = details.issues as Array<Record<string, unknown>>;
    expect(issues[0]?.message).toMatch(/date-time/);
  });

  it('501 when params are valid (body deferred to Plan 03 W6)', async () => {
    const { status, body } = await get('/v1/claims/verify?claim_text=Rust+has+version+1.96.0');
    expect(status).toBe(501);
    expect(body.code).toBe('not_implemented');
  });

  it('501 with optional as_of_date and token_budget', async () => {
    const { status, body } = await get(
      '/v1/claims/verify?claim_text=Rust+has+version+1.96.0&as_of_date=2026-01-01T00:00:00Z&token_budget=300',
    );
    expect(status).toBe(501);
    expect(body.code).toBe('not_implemented');
  });

  it('400 when token_budget is not an integer', async () => {
    const { status, body } = await get(
      '/v1/claims/verify?claim_text=Rust+has+version+1.96.0&token_budget=abc',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// GET /v1/sources — requires entity_or_claim_id; must be a UUID
// ---------------------------------------------------------------------------

describe('GET /v1/sources', () => {
  it('400 when entity_or_claim_id is missing', async () => {
    const { status, body } = await get('/v1/sources');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when entity_or_claim_id is not a UUID (free text)', async () => {
    const { status, body } = await get('/v1/sources?entity_or_claim_id=rust');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
    expect(body.message).toMatch(/UUID/);
  });

  it('400 when entity_or_claim_id is not a UUID (partial UUID-like string)', async () => {
    const { status, body } = await get('/v1/sources?entity_or_claim_id=not-a-uuid');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
    expect(body.message).toMatch(/UUID/);
  });

  it('400 when limit exceeds maximum (100)', async () => {
    const { status, body } = await get(
      '/v1/sources?entity_or_claim_id=35f09cce-63e3-45bb-9699-cba7dc1ae7e9&limit=200',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });

  it('400 when limit is below minimum (1)', async () => {
    const { status, body } = await get(
      '/v1/sources?entity_or_claim_id=35f09cce-63e3-45bb-9699-cba7dc1ae7e9&limit=0',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// GET /v1/freshness — requires topic_or_entity
// ---------------------------------------------------------------------------

describe('GET /v1/freshness', () => {
  it('400 when topic_or_entity is missing', async () => {
    const { status, body } = await get('/v1/freshness');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// Unknown query parameters — rejected (contract enumerates the exact params)
// ---------------------------------------------------------------------------

describe('unknown query parameters', () => {
  it('400 when an off-contract param is supplied to a valid request', async () => {
    const { status, body } = await get('/v1/freshness?topic_or_entity=rust&bogus=1');
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
    const details = body.details as Record<string, unknown>;
    const issues = details.issues as Array<Record<string, unknown>>;
    expect(issues.some((i) => String(i.message).includes('bogus'))).toBe(true);
  });

  it('400 when an off-contract param is supplied alongside required params', async () => {
    const { status, body } = await get(
      '/v1/delta?topic=rust&since_date=2026-01-01T00:00:00Z&page=2',
    );
    expect(status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

// ---------------------------------------------------------------------------
// CORS — agent-facing read surface allows cross-origin GET
// ---------------------------------------------------------------------------

describe('CORS', () => {
  it('echoes an allow-origin header on a /v1 request', async () => {
    const { res } = await get('/v1/freshness', { Origin: 'https://example.com' });
    expect(res.headers.get('access-control-allow-origin')).toBe('*');
  });

  it('answers a CORS preflight (OPTIONS) on a /v1 route', async () => {
    const res = await app.request('http://localhost/v1/entity', {
      method: 'OPTIONS',
      headers: {
        Origin: 'https://example.com',
        'Access-Control-Request-Method': 'GET',
      },
    });
    expect(res.status).toBe(204);
    expect(res.headers.get('access-control-allow-origin')).toBe('*');
    expect(res.headers.get('access-control-allow-methods')).toMatch(/GET/);
  });
});

// ---------------------------------------------------------------------------
// Error shape taxonomy
// ---------------------------------------------------------------------------

describe('error shape', () => {
  it('400 errors always include code and message', async () => {
    const { body } = await get('/v1/entity');
    expect(body).toHaveProperty('code', 'invalid_request');
    expect(body).toHaveProperty('message');
    expect(typeof body.message).toBe('string');
  });

  it('400 errors for param issues include details.issues array', async () => {
    const { body } = await get('/v1/entity');
    expect(body).toHaveProperty('details');
    const details = body.details as Record<string, unknown>;
    expect(Array.isArray(details.issues)).toBe(true);
    const issues = details.issues as Array<Record<string, unknown>>;
    expect(issues[0]).toHaveProperty('path');
    expect(issues[0]).toHaveProperty('message');
  });

  it('501 errors include code and message', async () => {
    // verify_claim is still the W6 deferred seam (raises NotImplementedError before the DB);
    // get_delta is now DB-backed (W5), so it is no longer a null-DB 501 path.
    const { body } = await get('/v1/claims/verify?claim_text=Rust+has+version+1.96.0');
    expect(body).toHaveProperty('code', 'not_implemented');
    expect(body).toHaveProperty('message');
    expect(typeof body.message).toBe('string');
  });
});
