/**
 * REST auth + rate-limit + usage middleware tests.
 *
 * These exercise the full middleware decision tree (anonymous allow, valid key, invalid/revoked/
 * expired key → 401, missing scope → 403, over-limit → 429 + headers, usage recording) against a
 * hand-rolled fake `Db` that implements only the query chains the auth path uses. The live Neon
 * integration verification covers the real DB path end-to-end.
 */
import { type Db, hashApiKey, MemoryRateLimitStore } from '@intercal/core';
import { describe, expect, it } from 'vitest';
import { createApp } from '../app.js';

interface FakeKeyRow {
  id: string;
  name: string;
  key_prefix: string;
  key_hash: string;
  scopes: string[];
  owner_type: string;
  owner_id: string | null;
  requests_per_minute: number | null;
  requests_per_day: number | null;
  is_active: boolean;
  expires_at: Date | null;
  last_used_at: Date | null;
  revoked_at: Date | null;
}

/** Captured usage rows for assertions. */
interface FakeState {
  keys: FakeKeyRow[];
  usage: Array<Record<string, unknown>>;
}

/**
 * Minimal fake Kysely Db covering exactly the chains the auth path uses:
 *   selectFrom('api_keys').selectAll().where('key_hash','=',h).executeTakeFirst()
 *   updateTable('api_keys').set(...).where('id','=',id).execute()       (best-effort last_used)
 *   insertInto('usage_events').values(row).execute()                    (usage recording)
 */
function makeFakeDb(state: FakeState): Db {
  const db = {
    selectFrom(table: string) {
      if (table !== 'api_keys') throw new Error(`unexpected selectFrom(${table})`);
      let hash: string | undefined;
      const builder = {
        selectAll() {
          return builder;
        },
        where(col: string, _op: string, val: unknown) {
          if (col === 'key_hash') hash = val as string;
          return builder;
        },
        async executeTakeFirst() {
          return state.keys.find((k) => k.key_hash === hash);
        },
      };
      return builder;
    },
    updateTable(table: string) {
      if (table !== 'api_keys') throw new Error(`unexpected updateTable(${table})`);
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
      if (table !== 'usage_events') throw new Error(`unexpected insertInto(${table})`);
      const builder = {
        values(row: Record<string, unknown>) {
          state.usage.push(row);
          return builder;
        },
        async execute() {
          return [];
        },
      };
      return builder;
    },
  };
  return db as unknown as Db;
}

function keyRow(raw: string, over: Partial<FakeKeyRow> = {}): FakeKeyRow {
  return {
    id: 'key-1',
    name: 'test key',
    key_prefix: 'ical_sk_',
    key_hash: hashApiKey(raw),
    scopes: ['read'],
    owner_type: 'user',
    owner_id: null,
    requests_per_minute: null,
    requests_per_day: null,
    is_active: true,
    expires_at: null,
    last_used_at: null,
    revoked_at: null,
    ...over,
  };
}

/** Build an app with a fresh in-memory store and a tiny anon limit for deterministic 429 tests. */
function appWith(
  state: FakeState,
  opts?: { anonPerMinute?: number; keyedPerMinuteDefault?: number },
) {
  return createApp(makeFakeDb(state), {
    rateLimitStore: new MemoryRateLimitStore(),
    anonPerMinute: opts?.anonPerMinute ?? 1000,
    keyedPerMinuteDefault: opts?.keyedPerMinuteDefault ?? 1000,
  });
}

async function call(
  app: ReturnType<typeof createApp>,
  path: string,
  headers?: Record<string, string>,
) {
  const res = await app.request(`http://localhost${path}`, { headers });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { status: res.status, body, res };
}

describe('anonymous read posture', () => {
  it('allows an anonymous read (no Authorization) and sets rate-limit headers', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state);
    // /v1/freshness with no params → 400 from validation, but the middleware must still admit it
    // (anonymous is allowed) and set rate-limit headers before the handler runs.
    const { res } = await call(app, '/v1/freshness?topic_or_entity=rust');
    expect(res.headers.get('RateLimit-Limit')).toBe('1000');
    expect(Number(res.headers.get('RateLimit-Remaining'))).toBeLessThan(1000);
  });
});

describe('invalid / revoked / expired keys → 401', () => {
  it('rejects an unknown key', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state);
    const { status, body } = await call(app, '/v1/freshness?topic_or_entity=rust', {
      Authorization: 'Bearer ical_sk_unknown',
    });
    expect(status).toBe(401);
    expect(body.code).toBe('unauthorized');
  });

  it('rejects a revoked key', async () => {
    const raw = 'ical_sk_revoked';
    const state: FakeState = { keys: [keyRow(raw, { revoked_at: new Date() })], usage: [] };
    const app = appWith(state);
    const { status, body } = await call(app, '/v1/freshness?topic_or_entity=rust', {
      Authorization: `Bearer ${raw}`,
    });
    expect(status).toBe(401);
    expect(body.code).toBe('unauthorized');
    expect(String(body.message)).toMatch(/revoked/i);
  });

  it('rejects an expired key', async () => {
    const raw = 'ical_sk_expired';
    const state: FakeState = {
      keys: [keyRow(raw, { expires_at: new Date(Date.now() - 1000) })],
      usage: [],
    };
    const app = appWith(state);
    const { status, body } = await call(app, '/v1/freshness?topic_or_entity=rust', {
      Authorization: `Bearer ${raw}`,
    });
    expect(status).toBe(401);
    expect(String(body.message)).toMatch(/expired/i);
  });

  it('rejects an inactive key', async () => {
    const raw = 'ical_sk_inactive';
    const state: FakeState = { keys: [keyRow(raw, { is_active: false })], usage: [] };
    const app = appWith(state);
    const { status } = await call(app, '/v1/freshness?topic_or_entity=rust', {
      Authorization: `Bearer ${raw}`,
    });
    expect(status).toBe(401);
  });
});

describe('scope enforcement → 403', () => {
  it('rejects a valid key that lacks the read scope', async () => {
    const raw = 'ical_sk_noread';
    const state: FakeState = { keys: [keyRow(raw, { scopes: ['submit:feedback'] })], usage: [] };
    const app = appWith(state);
    const { status, body } = await call(app, '/v1/freshness?topic_or_entity=rust', {
      Authorization: `Bearer ${raw}`,
    });
    expect(status).toBe(403);
    expect(body.code).toBe('forbidden');
  });

  it('admits a valid read-scoped key (reaches the handler — 400 here, not 401/403)', async () => {
    const raw = 'ical_sk_good';
    const state: FakeState = { keys: [keyRow(raw)], usage: [] };
    const app = appWith(state);
    // Missing required param → handler-level 400, proving auth+scope passed.
    const { status } = await call(app, '/v1/freshness', { Authorization: `Bearer ${raw}` });
    expect(status).toBe(400);
  });

  it('requires a key for subscription management routes', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state);
    const { status, body } = await call(app, '/v1/subscriptions');
    expect(status).toBe(401);
    expect(body.code).toBe('unauthorized');
    expect(body.details).toMatchObject({ requiredScope: 'manage:subscriptions' });
  });

  it('rejects a read-only key on subscription management routes', async () => {
    const raw = 'ical_sk_read_only';
    const state: FakeState = { keys: [keyRow(raw)], usage: [] };
    const app = appWith(state);
    const { status, body } = await call(app, '/v1/subscriptions', {
      Authorization: `Bearer ${raw}`,
    });
    expect(status).toBe(403);
    expect(body.code).toBe('forbidden');
    expect(body.details).toMatchObject({ requiredScope: 'manage:subscriptions' });
  });

  it('admits a manage:subscriptions key to the subscription handler', async () => {
    const raw = 'ical_sk_manage_subs';
    const state: FakeState = {
      keys: [keyRow(raw, { scopes: ['manage:subscriptions'] })],
      usage: [],
    };
    const app = appWith(state);
    const { status } = await call(app, '/v1/subscriptions', { Authorization: `Bearer ${raw}` });
    // The fake DB intentionally only implements auth tables; a 500 proves auth/scope admitted the
    // request and the real handler tried to read subscriptions.
    expect(status).toBe(500);
  });
});

describe('rate limiting → 429 + headers', () => {
  it('returns 429 with Retry-After and RateLimit headers once the anon window is exhausted', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state, { anonPerMinute: 2 });
    await call(app, '/v1/freshness?topic_or_entity=a'); // 1
    await call(app, '/v1/freshness?topic_or_entity=b'); // 2
    const { status, body, res } = await call(app, '/v1/freshness?topic_or_entity=c'); // 3 → over
    expect(status).toBe(429);
    expect(body.code).toBe('rate_limited');
    expect(res.headers.get('Retry-After')).toBeTruthy();
    expect(res.headers.get('RateLimit-Limit')).toBe('2');
    expect(res.headers.get('RateLimit-Remaining')).toBe('0');
  });

  it('a key gets its own higher bucket, independent of anonymous traffic', async () => {
    const raw = 'ical_sk_keyed';
    const state: FakeState = { keys: [keyRow(raw, { requests_per_minute: 5 })], usage: [] };
    const app = appWith(state, { anonPerMinute: 1 });
    await call(app, '/v1/freshness?topic_or_entity=a'); // anon: 1
    const anonOver = await call(app, '/v1/freshness?topic_or_entity=b'); // anon: over
    expect(anonOver.status).toBe(429);
    // The key has its own bucket (limit 5) — still admitted.
    const keyed = await call(app, '/v1/freshness?topic_or_entity=c', {
      Authorization: `Bearer ${raw}`,
    });
    expect(keyed.res.headers.get('RateLimit-Limit')).toBe('5');
    expect(keyed.status).not.toBe(429);
  });
});

describe('trusted client IP for per-IP limiting', () => {
  // The per-IP bucket must key off the TRUSTED client IP, not an attacker-supplied left-most
  // x-forwarded-for element. If a caller could vary the left-most XFF value, they would get a
  // fresh bucket per spoofed IP and escape the anonymous limit entirely.

  it('prefers x-real-ip and rejects further calls from the same trusted IP', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state, { anonPerMinute: 1 });
    await call(app, '/v1/freshness?topic_or_entity=a', { 'x-real-ip': '203.0.113.7' });
    const over = await call(app, '/v1/freshness?topic_or_entity=b', { 'x-real-ip': '203.0.113.7' });
    expect(over.status).toBe(429);
  });

  it('a spoofed left-most x-forwarded-for cannot mint a fresh bucket (uses right-most hop)', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state, { anonPerMinute: 1 });
    // Same trusted right-most hop (203.0.113.9), attacker varies only the spoofable left-most value.
    await call(app, '/v1/freshness?topic_or_entity=a', {
      'x-forwarded-for': '9.9.9.9, 203.0.113.9',
    });
    const over = await call(app, '/v1/freshness?topic_or_entity=b', {
      'x-forwarded-for': '8.8.8.8, 203.0.113.9', // different left-most, same trusted hop
    });
    expect(over.status).toBe(429);
  });

  it('anonymizes the stored IP to a /24 (IPv4) and keeps no full address', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state);
    await call(app, '/v1/freshness?topic_or_entity=a', { 'x-real-ip': '198.51.100.42' });
    const row = state.usage.at(-1);
    expect(row?.ip_address).toBe('198.51.100.0/24');
    expect(JSON.stringify(state.usage)).not.toContain('198.51.100.42');
  });
});

describe('usage recording', () => {
  it('records a usage_events row per request (anonymous and keyed), no raw key stored', async () => {
    const raw = 'ical_sk_usage';
    const state: FakeState = { keys: [keyRow(raw)], usage: [] };
    const app = appWith(state);
    await call(app, '/v1/freshness?topic_or_entity=rust'); // anon
    await call(app, '/v1/freshness?topic_or_entity=rust', { Authorization: `Bearer ${raw}` }); // keyed
    expect(state.usage.length).toBe(2);
    const [anon, keyed] = state.usage;
    expect(anon?.api_key_id).toBeNull();
    expect(keyed?.api_key_id).toBe('key-1');
    expect(String(anon?.tool_name)).toContain('/v1/freshness');
    // No raw key material anywhere in the recorded rows.
    for (const row of state.usage) {
      expect(JSON.stringify(row)).not.toContain(raw);
    }
  });

  it('records a 429 attempt with the rate_limited error code', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state, { anonPerMinute: 1 });
    await call(app, '/v1/freshness?topic_or_entity=a');
    await call(app, '/v1/freshness?topic_or_entity=b'); // 429
    const throttled = state.usage.find((u) => u.error_code === 'rate_limited');
    expect(throttled).toBeTruthy();
    // Error outcomes record the application error_code; status_code is null (the response is
    // rendered by the central error handler, not the metered handler).
    expect(throttled?.status_code).toBeNull();
  });

  it('records a usage row for a rejected (401) credential', async () => {
    const state: FakeState = { keys: [], usage: [] };
    const app = appWith(state);
    await call(app, '/v1/freshness?topic_or_entity=a', { Authorization: 'Bearer ical_sk_bad' });
    const denied = state.usage.find((u) => u.error_code === 'unauthorized');
    expect(denied).toBeTruthy();
    expect(denied?.api_key_id).toBeNull();
  });
});
