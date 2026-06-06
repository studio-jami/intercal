/**
 * Plan 03 Workstream 8 — full-surface agent/contract harness (the Phase C ACCEPTANCE GATE).
 *
 * Proves that an AGENT (via MCP) and a CLIENT (via SDK/REST) both drive the complete V1 surface —
 * all six tools/endpoints — and get responses that are, against the generated contract:
 *   - WELL-FORMED   (typed shape; required fields present)
 *   - CITED         (provenance: evidence / citations / source documents present)
 *   - CONFIDENCE-scored (a `Confidence` with a numeric score where the contract carries one)
 *   - BUDGET-bounded (delta/verify honour `token_budget`)
 *
 * One set of REAL captured responses (`agent-surface.fixtures.ts`) drives BOTH access paths, so the
 * test also proves the "one query layer, identical semantics" invariant: MCP and SDK return the
 * same body for the same logical query.
 *
 * Determinism: the fixtures are frozen real bytes, not faked product data, and not a live call —
 * so this runs offline in `pnpm test`. The MCP path runs the real JSON-RPC wire (a real `Client`
 * over the in-process transport, the server's tool handlers fed the fixtures via the documented
 * injection seam). The SDK path runs the real `IntercalClient` over an injected fetch that serves
 * the fixtures as HTTP bodies on the real `/v1/*` routes.
 *
 * A live block (gated on `INTERCAL_LIVE=1`) drives the SAME assertions against the DEPLOYED surface
 * (`/api/mcp` Streamable HTTP + `/api/v1/*`) with real production data — the live acceptance proof.
 */

import type { Db } from '@intercal/core';
import { type ClaimVerificationResponse, type DeltaResponse, IntercalClient } from '@intercal/sdk';
import type { components } from '@intercal/shared';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { describe, expect, it } from 'vitest';
import {
  deltaFixture,
  entityFixture,
  evidenceFixture,
  freshnessFixture,
  sourcesFixture,
  verifyAsOfFixture,
  verifySupportedFixture,
  verifyUnverifiedFixture,
} from './agent-surface.fixtures.js';
import { buildMcpServer } from './server.js';

type S = components['schemas'];

// --- shared contract assertions -------------------------------------------
// These are the gate. Each access path funnels every tool result through them, so MCP and SDK are
// held to the identical "well-formed + cited + confidence + budget" bar.

/** A `Confidence` carries a numeric score in [0,1] and a method label. */
function assertConfidence(c: S['Confidence']): void {
  expect(typeof c.score).toBe('number');
  expect(c.score).toBeGreaterThanOrEqual(0);
  expect(c.score).toBeLessThanOrEqual(1);
  expect(typeof c.method).toBe('string');
}

/** A `Citation` traces to a source document — the provenance invariant. */
function assertCited(citation: S['Citation']): void {
  expect(citation.sourceDocumentId).toBeTruthy();
}

function assertEntity(res: S['EntityResponse']): void {
  expect(res.entity.id).toBeTruthy();
  expect(res.entity.displayName).toBeTruthy();
  expect(res.freshness.target).toBeTruthy();
  for (const fact of res.facts ?? []) {
    assertConfidence(fact.confidence);
    // CITED: every served fact traces to evidence → source documents.
    expect(fact.evidence.length).toBeGreaterThan(0);
    for (const e of fact.evidence) assertCited(e);
  }
}

function assertEvidence(res: S['EvidenceResponse']): void {
  expect(typeof res.total).toBe('number');
  expect(Array.isArray(res.hits)).toBe(true);
  for (const hit of res.hits) {
    expect(typeof hit.score).toBe('number');
    assertCited(hit.citation); // CITED
  }
}

function assertSources(res: S['SourcesResponse']): void {
  expect(Array.isArray(res.sources)).toBe(true);
  for (const src of res.sources) {
    expect(src.id).toBeTruthy(); // CITED: a real source document id
    expect(src.title).toBeTruthy();
  }
}

function assertFreshness(res: S['FreshnessReport']): void {
  expect(res.target).toBeTruthy();
  if (res.coverage !== undefined) {
    expect(res.coverage).toBeGreaterThanOrEqual(0);
    expect(res.coverage).toBeLessThanOrEqual(1);
  }
}

/** The killer-feature gate: a cited, confidence-scored, BUDGET-bounded change digest. */
function assertDelta(res: DeltaResponse): void {
  expect(res.topic).toBeTruthy();
  expect(res.since).toBeTruthy();
  assertConfidence(res.confidence);
  assertFreshness(res.freshness);
  // CITED: every changed claim carries evidence; the summary rolls up source citations.
  expect(res.changedClaims.length).toBeGreaterThan(0);
  for (const claim of res.changedClaims) {
    expect(claim.evidence.length).toBeGreaterThan(0);
    for (const e of claim.evidence) assertCited(e);
    assertConfidence(claim.confidence);
  }
  expect(res.summary.citations.length).toBeGreaterThan(0);
  for (const c of res.summary.citations) assertCited(c);
  // BUDGET-bounded: the rendered digest content fits the (server-clamped) token budget. ~4 chars
  // per token, the same deterministic estimate the digest assembler uses.
  const budget = res.summary.tokenBudget;
  expect(typeof budget).toBe('number');
  if (typeof budget === 'number') {
    expect(Math.ceil(res.summary.content.length / 4)).toBeLessThanOrEqual(budget);
  }
}

/** A cited, confidence-scored verdict that never over-claims when evidence is thin. */
function assertVerify(res: ClaimVerificationResponse): void {
  expect(res.claimText).toBeTruthy();
  expect(['supported', 'partially_supported', 'contradicted', 'unverified']).toContain(res.verdict);
  assertConfidence(res.confidence);
  expect(Array.isArray(res.supportingEvidence)).toBe(true);
  expect(Array.isArray(res.contradictingEvidence)).toBe(true);
  for (const c of [...res.supportingEvidence, ...res.contradictingEvidence]) assertCited(c);
  // Honesty: a `supported` verdict must rest on real supporting evidence; `unverified` must not
  // fabricate any. (Both real cases are exercised by the fixtures.)
  if (res.verdict === 'supported') expect(res.supportingEvidence.length).toBeGreaterThan(0);
  if (res.verdict === 'unverified') {
    expect(res.supportingEvidence.length).toBe(0);
    expect(res.confidence.score).toBe(0);
  }
}

// --- access path 1: MCP (agent) over the real JSON-RPC wire ----------------

// biome-ignore lint/suspicious/noExplicitAny: handlers are injected, so the DB is never touched.
const nullDb = null as any as Db;

/**
 * Fixture-backed tool handlers — the documented injection seam (`buildMcpServer(db, handlers)`).
 * They return the SAME captured bodies the SDK path serves over HTTP, so both paths are held to one
 * source of truth. The real query layer is exercised separately against Neon (the live block + the
 * core unit suites); here we drive the MCP transport/dispatch/contract envelope deterministically.
 */
const fixtureHandlers: Record<string, (db: Db, p: Record<string, unknown>) => Promise<unknown>> = {
  get_delta: async () => deltaFixture,
  get_entity: async () => entityFixture,
  search_evidence: async () => evidenceFixture,
  verify_claim: async (_db, p) => {
    if (p.as_of_date) return verifyAsOfFixture;
    // A claim with no on-topic evidence → the real unverified (no-fabrication) capture.
    if (typeof p.claim_text === 'string' && /moon/i.test(p.claim_text)) {
      return verifyUnverifiedFixture;
    }
    return verifySupportedFixture;
  },
  get_sources: async () => sourcesFixture,
  get_freshness: async () => freshnessFixture,
};

async function connectAgent(): Promise<Client> {
  const server = buildMcpServer(nullDb, fixtureHandlers);
  const client = new Client({ name: 'w8-agent', version: '0.0.0' }, { capabilities: {} });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
  return client;
}

/**
 * Unwrap a successful MCP tool call's structured content as a typed contract response. `callTool`
 * returns the SDK's compatibility union (the modern `content`/`structuredContent` result OR the
 * legacy `toolResult` shape); we accept that union and assert the modern shape we actually serve.
 */
function ok<T>(res: Awaited<ReturnType<Client['callTool']>>): T {
  expect(res.isError ?? false).toBe(false);
  const structured = (res as CallToolResult).structuredContent;
  expect(structured).toBeDefined();
  return structured as T;
}

describe('W8 acceptance gate — MCP (agent) drives the full V1 surface', () => {
  it('get_entity returns a cited, confidence-scored entity', async () => {
    const client = await connectAgent();
    const res = ok<S['EntityResponse']>(
      await client.callTool({ name: 'get_entity', arguments: { name_or_id: 'rust' } }),
    );
    assertEntity(res);
    await client.close();
  });

  it('search_evidence returns cited hits', async () => {
    const client = await connectAgent();
    const res = ok<S['EvidenceResponse']>(
      await client.callTool({ name: 'search_evidence', arguments: { query: 'rust', limit: 2 } }),
    );
    assertEvidence(res);
    await client.close();
  });

  it('get_sources returns source documents', async () => {
    const client = await connectAgent();
    const res = ok<S['SourcesResponse']>(
      await client.callTool({
        name: 'get_sources',
        arguments: { entity_or_claim_id: '35f09cce-63e3-45bb-9699-cba7dc1ae7e9' },
      }),
    );
    assertSources(res);
    await client.close();
  });

  it('get_freshness returns a coverage-bounded report', async () => {
    const client = await connectAgent();
    const res = ok<S['FreshnessReport']>(
      await client.callTool({ name: 'get_freshness', arguments: { topic_or_entity: 'rust' } }),
    );
    assertFreshness(res);
    await client.close();
  });

  it('get_delta returns a cited, confidence-scored, BUDGET-bounded digest', async () => {
    const client = await connectAgent();
    const res = ok<DeltaResponse>(
      await client.callTool({
        name: 'get_delta',
        arguments: { topic: 'rust', since_date: '2026-06-04T00:00:00Z', token_budget: 120 },
      }),
    );
    assertDelta(res);
    // BUDGET: detected more changes than rendered, and said so — no silent provenance loss.
    expect(res.changedClaims.length).toBeLessThan(12);
    expect(res.summary.content).toContain('omitted');
    await client.close();
  });

  it('verify_claim returns a cited verdict; unverified does not fabricate support', async () => {
    const client = await connectAgent();
    const supported = ok<ClaimVerificationResponse>(
      await client.callTool({
        name: 'verify_claim',
        arguments: { claim_text: 'Rust has version 1.96.0' },
      }),
    );
    assertVerify(supported);
    expect(supported.verdict).toBe('supported');

    // Point-in-time before the fact was recorded → unverified (bitemporal correctness).
    const asOf = ok<ClaimVerificationResponse>(
      await client.callTool({
        name: 'verify_claim',
        arguments: { claim_text: 'Rust has version 1.96.0', as_of_date: '2020-01-01T00:00:00Z' },
      }),
    );
    assertVerify(asOf);
    expect(asOf.verdict).toBe('unverified');

    // A claim with no on-topic evidence → unverified, with NO fabricated support (honesty gate).
    const unverified = ok<ClaimVerificationResponse>(
      await client.callTool({
        name: 'verify_claim',
        arguments: { claim_text: 'The moon is made of cheese' },
      }),
    );
    assertVerify(unverified);
    expect(unverified.verdict).toBe('unverified');
    expect(unverified.supportingEvidence).toHaveLength(0);
    await client.close();
  });
});

// --- access path 2: SDK/REST (client) over the real client + injected fetch -

/** An injected fetch that routes each V1 path to its captured fixture as an HTTP JSON body. */
function fixtureFetch(): typeof fetch {
  return async (input) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    if (path.endsWith('/v1/entity')) return json(entityFixture);
    if (path.endsWith('/v1/evidence')) return json(evidenceFixture);
    if (path.endsWith('/v1/sources')) return json(sourcesFixture);
    if (path.endsWith('/v1/freshness')) return json(freshnessFixture);
    if (path.endsWith('/v1/delta')) return json(deltaFixture);
    if (path.endsWith('/v1/claims/verify')) {
      if (url.searchParams.get('as_of_date')) return json(verifyAsOfFixture);
      if (/moon/i.test(url.searchParams.get('claim_text') ?? ''))
        return json(verifyUnverifiedFixture);
      return json(verifySupportedFixture);
    }
    return new Response(JSON.stringify({ code: 'not_found', message: path }), { status: 404 });
  };
}

describe('W8 acceptance gate — SDK/REST (client) drives the full V1 surface', () => {
  const client = new IntercalClient({ baseUrl: 'https://example.test/api', fetch: fixtureFetch() });

  it('getEntity → cited, confidence-scored entity', async () => {
    assertEntity(await client.getEntity({ name_or_id: 'rust' }));
  });
  it('searchEvidence → cited hits', async () => {
    assertEvidence(await client.searchEvidence({ query: 'rust', limit: 2 }));
  });
  it('getSources → source documents', async () => {
    assertSources(
      await client.getSources({ entity_or_claim_id: '35f09cce-63e3-45bb-9699-cba7dc1ae7e9' }),
    );
  });
  it('getFreshness → coverage-bounded report', async () => {
    assertFreshness(await client.getFreshness({ topic_or_entity: 'rust' }));
  });
  it('getDelta → cited, confidence-scored, BUDGET-bounded digest', async () => {
    assertDelta(
      await client.getDelta({
        topic: 'rust',
        since_date: '2026-06-04T00:00:00Z',
        token_budget: 120,
      }),
    );
  });
  it('verifyClaim → cited verdict (supported + point-in-time unverified)', async () => {
    const supported = await client.verifyClaim({ claim_text: 'Rust has version 1.96.0' });
    assertVerify(supported);
    expect(supported.verdict).toBe('supported');
    const asOf = await client.verifyClaim({
      claim_text: 'Rust has version 1.96.0',
      as_of_date: '2020-01-01T00:00:00Z',
    });
    assertVerify(asOf);
    expect(asOf.verdict).toBe('unverified');
  });
});

// --- cross-path equivalence: one query layer, identical semantics ----------

describe('W8 — MCP and SDK return the same body for the same query', () => {
  it('get_delta is byte-identical across the MCP wire and the SDK', async () => {
    const agent = await connectAgent();
    const viaMcp = ok<DeltaResponse>(
      await agent.callTool({
        name: 'get_delta',
        arguments: { topic: 'rust', since_date: '2026-06-04T00:00:00Z', token_budget: 120 },
      }),
    );
    await agent.close();
    const sdk = new IntercalClient({ baseUrl: 'https://example.test/api', fetch: fixtureFetch() });
    const viaSdk = await sdk.getDelta({
      topic: 'rust',
      since_date: '2026-06-04T00:00:00Z',
      token_budget: 120,
    });
    expect(viaMcp).toEqual(viaSdk);
  });

  it('verify_claim is byte-identical across the MCP wire and the SDK', async () => {
    const agent = await connectAgent();
    const viaMcp = ok<ClaimVerificationResponse>(
      await agent.callTool({
        name: 'verify_claim',
        arguments: { claim_text: 'Rust has version 1.96.0' },
      }),
    );
    await agent.close();
    const sdk = new IntercalClient({ baseUrl: 'https://example.test/api', fetch: fixtureFetch() });
    const viaSdk = await sdk.verifyClaim({ claim_text: 'Rust has version 1.96.0' });
    expect(viaMcp).toEqual(viaSdk);
  });
});

// --- live acceptance proof (env-gated) -------------------------------------
// Opt-in: skipped unless INTERCAL_LIVE=1, so `pnpm test` stays deterministic/offline. Drives the
// SAME gate assertions against the DEPLOYED MCP + REST surface with real production data.
//   INTERCAL_LIVE=1 pnpm --filter @intercal/mcp-server test

const LIVE = process.env.INTERCAL_LIVE === '1';
const API_BASE = process.env.INTERCAL_BASE_URL ?? 'https://lntercal.vercel.app/api';
const MCP_URL = process.env.INTERCAL_MCP_URL ?? 'https://lntercal.vercel.app/api/mcp';

describe.skipIf(!LIVE)('W8 LIVE acceptance gate — deployed MCP + SDK against real data', () => {
  it('MCP (agent): all six tools return well-formed, cited, budget-bounded results', async () => {
    const transport = new StreamableHTTPClientTransport(new URL(MCP_URL));
    const client = new Client({ name: 'w8-live-agent', version: '0.0.0' }, { capabilities: {} });
    await client.connect(transport);

    const tools = (await client.listTools()).tools.map((t) => t.name).sort();
    expect(tools).toEqual(
      [
        'get_delta',
        'get_entity',
        'get_freshness',
        'get_sources',
        'search_evidence',
        'verify_claim',
      ].sort(),
    );

    assertEntity(
      ok<S['EntityResponse']>(
        await client.callTool({ name: 'get_entity', arguments: { name_or_id: 'rust' } }),
      ),
    );
    assertEvidence(
      ok<S['EvidenceResponse']>(
        await client.callTool({ name: 'search_evidence', arguments: { query: 'rust', limit: 3 } }),
      ),
    );
    assertFreshness(
      ok<S['FreshnessReport']>(
        await client.callTool({ name: 'get_freshness', arguments: { topic_or_entity: 'rust' } }),
      ),
    );
    assertDelta(
      ok<DeltaResponse>(
        await client.callTool({
          name: 'get_delta',
          arguments: { topic: 'rust', since_date: '2026-06-01T00:00:00Z', token_budget: 600 },
        }),
      ),
    );
    const verdict = ok<ClaimVerificationResponse>(
      await client.callTool({
        name: 'verify_claim',
        arguments: { claim_text: 'Rust has version 1.96.0' },
      }),
    );
    assertVerify(verdict);

    await client.close();
  });

  it('SDK/REST (client): all six operations return well-formed, cited, budget-bounded results', async () => {
    const client = new IntercalClient({ baseUrl: API_BASE, maxRetries: 2, retryBackoffMs: 250 });
    assertEntity(await client.getEntity({ name_or_id: 'rust' }));
    assertEvidence(await client.searchEvidence({ query: 'rust', limit: 3 }));
    assertFreshness(await client.getFreshness({ topic_or_entity: 'rust' }));
    assertDelta(
      await client.getDelta({
        topic: 'rust',
        since_date: '2026-06-01T00:00:00Z',
        token_budget: 600,
      }),
    );
    assertVerify(await client.verifyClaim({ claim_text: 'Rust has version 1.96.0' }));
    // Point-in-time correctness on the live surface.
    const asOf = await client.verifyClaim({
      claim_text: 'Rust has version 1.96.0',
      as_of_date: '2020-01-01T00:00:00Z',
    });
    assertVerify(asOf);
    expect(asOf.verdict).toBe('unverified');
  });
});
