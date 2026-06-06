import { type Db, hashApiKey, MemoryRateLimitStore } from '@intercal/core';
import { describe, expect, it } from 'vitest';
import { createApp } from './app.js';

interface FakeState {
  entities: Array<{ id: string; canonical_name: string }>;
  claims: Array<{ id: string; normalized_text: string }>;
  sources: Array<{ id: string; name: string }>;
  digests: Array<{ id: string }>;
  keys: Array<{
    id: string;
    key_hash: string;
    scopes: string[];
    is_active: boolean;
    revoked_at: Date | null;
    expires_at: Date | null;
    requests_per_minute: number | null;
  }>;
  reviewRecords: Array<Record<string, unknown>>;
  auditEvents: Array<Record<string, unknown>>;
  usageEvents: Array<Record<string, unknown>>;
}

function makeFakeDb(state: FakeState): Db {
  const db = {
    transaction() {
      return {
        execute: async (fn: (tx: unknown) => unknown) => fn(db),
      };
    },
    selectFrom(table: string) {
      let whereCol: string | undefined;
      let whereVal: unknown;
      const builder = {
        select() {
          return builder;
        },
        selectAll() {
          return builder;
        },
        where(col: string, _op: string, val: unknown) {
          whereCol = col;
          whereVal = val;
          return builder;
        },
        async executeTakeFirst() {
          if (table === 'api_keys') return state.keys.find((k) => k.key_hash === whereVal);
          if (table === 'entities') return state.entities.find((r) => r.id === whereVal);
          if (table === 'claims') return state.claims.find((r) => r.id === whereVal);
          if (table === 'sources') return state.sources.find((r) => r.id === whereVal);
          if (table === 'digests') return state.digests.find((r) => r.id === whereVal);
          throw new Error(`unexpected selectFrom(${table}) where ${whereCol}`);
        },
      };
      return builder;
    },
    updateTable() {
      const builder = {
        set() {
          return builder;
        },
        where() {
          return builder;
        },
        async execute() {
          return [];
        },
      };
      return builder;
    },
    insertInto(table: string) {
      let row: Record<string, unknown> = {};
      const builder = {
        values(value: Record<string, unknown>) {
          row = value;
          return builder;
        },
        returning() {
          return builder;
        },
        async execute() {
          if (table === 'usage_events') {
            state.usageEvents.push(row);
            return [];
          }
          if (table === 'audit_events') {
            state.auditEvents.push({ id: 'audit-1', ...row });
            return [];
          }
          throw new Error(`unexpected insert execute(${table})`);
        },
        async executeTakeFirstOrThrow() {
          if (table !== 'review_records') throw new Error(`unexpected insert returning(${table})`);
          const saved = {
            id: '11111111-1111-4111-8111-111111111111',
            status: 'received',
            created_at: new Date('2026-06-06T12:00:00.000Z'),
            ...row,
          };
          state.reviewRecords.push(saved);
          return saved;
        },
      };
      return builder;
    },
  };
  return db as unknown as Db;
}

function initialState(): FakeState {
  return {
    entities: [{ id: '22222222-2222-4222-8222-222222222222', canonical_name: 'Rust' }],
    claims: [{ id: '33333333-3333-4333-8333-333333333333', normalized_text: 'Rust 1.96 exists' }],
    sources: [{ id: '55555555-5555-4555-8555-555555555555', name: 'Rust releases' }],
    digests: [{ id: '44444444-4444-4444-8444-444444444444' }],
    keys: [],
    reviewRecords: [],
    auditEvents: [],
    usageEvents: [],
  };
}

async function postFeedback(
  app: ReturnType<typeof createApp>,
  body: unknown,
  headers?: Record<string, string>,
) {
  const res = await app.request('http://localhost/v1/feedback', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
  return { res, body: (await res.json()) as Record<string, unknown> };
}

async function postSubscription(
  app: ReturnType<typeof createApp>,
  body: unknown,
  headers?: Record<string, string>,
) {
  const res = await app.request('http://localhost/v1/subscriptions', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
  return { res, body: (await res.json()) as Record<string, unknown> };
}

describe('POST /v1/feedback', () => {
  it('creates an audited review record and leaves canonical records unchanged', async () => {
    const state = initialState();
    const canonicalBefore = JSON.stringify({
      entities: state.entities,
      claims: state.claims,
      sources: state.sources,
      digests: state.digests,
    });
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postFeedback(
      app,
      {
        targetType: 'entity',
        targetId: '22222222-2222-4222-8222-222222222222',
        concernType: 'outdated',
        summary: 'Display name appears stale',
        details: 'Please review the entity state against newer evidence.',
      },
      { 'x-request-id': 'req-feedback-1' },
    );

    expect(res.status).toBe(200);
    expect(body.review).toMatchObject({
      id: '11111111-1111-4111-8111-111111111111',
      targetType: 'entity',
      targetId: '22222222-2222-4222-8222-222222222222',
      concernType: 'outdated',
      status: 'received',
    });
    expect(state.reviewRecords).toHaveLength(1);
    expect(state.auditEvents).toHaveLength(1);
    expect(state.auditEvents[0]).toMatchObject({
      action: 'feedback.submit',
      target_type: 'review_record',
      target_id: '11111111-1111-4111-8111-111111111111',
      request_id: 'req-feedback-1',
      severity: 'low',
    });
    expect(
      JSON.stringify({
        entities: state.entities,
        claims: state.claims,
        sources: state.sources,
        digests: state.digests,
      }),
    ).toBe(canonicalBefore);
  });

  it('accepts freshness and coverage review targets as bounded non-canonical target strings', async () => {
    const state = initialState();
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const freshness = await postFeedback(app, {
      targetType: 'freshness',
      targetId: 'rust',
      concernType: 'outdated',
      summary: 'Freshness looks stale',
    });
    const coverage = await postFeedback(app, {
      targetType: 'coverage',
      targetId: 'rust-lang/rust',
      concernType: 'missing_coverage',
      summary: 'Missing release source coverage',
    });

    expect(freshness.res.status).toBe(200);
    expect(coverage.res.status).toBe(200);
    expect(state.reviewRecords.map((r) => r.target_type)).toEqual(['freshness', 'coverage']);
  });

  it('requires submit:feedback when a keyed caller submits feedback', async () => {
    const raw = 'ical_sk_feedback';
    const state = initialState();
    state.keys.push({
      id: 'key-1',
      key_hash: hashApiKey(raw),
      scopes: ['read'],
      is_active: true,
      revoked_at: null,
      expires_at: null,
      requests_per_minute: null,
    });
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postFeedback(
      app,
      {
        targetType: 'source',
        targetId: '55555555-5555-4555-8555-555555555555',
        concernType: 'source_quality',
        summary: 'Review source reliability',
      },
      { authorization: `Bearer ${raw}` },
    );

    expect(res.status).toBe(403);
    expect(body.code).toBe('forbidden');
    expect(body.details).toMatchObject({ requiredScope: 'submit:feedback' });
    expect(state.reviewRecords).toHaveLength(0);
  });

  it('rejects an unknown canonical target before creating review or audit rows', async () => {
    const state = initialState();
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postFeedback(app, {
      targetType: 'claim',
      targetId: '99999999-9999-4999-8999-999999999999',
      concernType: 'incorrect',
      summary: 'Claim appears wrong',
    });

    expect(res.status).toBe(404);
    expect(body.code).toBe('not_found');
    expect(state.reviewRecords).toHaveLength(0);
    expect(state.auditEvents).toHaveLength(0);
  });

  it('rejects a non-UUID source target before reaching the database insert path', async () => {
    const state = initialState();
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postFeedback(app, {
      targetType: 'source',
      targetId: 'rust-lang/rust',
      concernType: 'source_quality',
      summary: 'Review source reliability',
    });

    expect(res.status).toBe(400);
    expect(body.code).toBe('invalid_request');
    expect(state.reviewRecords).toHaveLength(0);
    expect(state.auditEvents).toHaveLength(0);
  });

  it('rejects unbounded request ids before storing review or audit rows', async () => {
    const state = initialState();
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postFeedback(
      app,
      {
        targetType: 'entity',
        targetId: '22222222-2222-4222-8222-222222222222',
        concernType: 'outdated',
        summary: 'Display name appears stale',
      },
      { 'x-request-id': 'r'.repeat(129) },
    );

    expect(res.status).toBe(400);
    expect(body.code).toBe('invalid_request');
    expect(state.reviewRecords).toHaveLength(0);
    expect(state.auditEvents).toHaveLength(0);
  });

  it('rejects off-contract bodies', async () => {
    const state = initialState();
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postFeedback(app, {
      targetType: 'entity',
      targetId: '22222222-2222-4222-8222-222222222222',
      concernType: 'outdated',
      summary: '',
      mutateCanonicalGraph: true,
    });

    expect(res.status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});

describe('POST /v1/subscriptions', () => {
  it('rejects a target field that does not match target.kind', async () => {
    const raw = 'ical_sk_manage_subscriptions';
    const state = initialState();
    state.keys.push({
      id: '55555555-5555-4555-8555-555555555555',
      key_hash: hashApiKey(raw),
      scopes: ['manage:subscriptions'],
      is_active: true,
      revoked_at: null,
      expires_at: null,
      requests_per_minute: null,
    });
    const app = createApp(makeFakeDb(state), {
      rateLimitStore: new MemoryRateLimitStore(),
      anonPerMinute: 1000,
    });

    const { res, body } = await postSubscription(
      app,
      {
        target: { kind: 'topic', entityId: '22222222-2222-4222-8222-222222222222' },
        deliveryMethod: 'polling',
      },
      { authorization: `Bearer ${raw}` },
    );

    expect(res.status).toBe(400);
    expect(body.code).toBe('invalid_request');
  });
});
