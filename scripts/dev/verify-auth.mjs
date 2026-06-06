#!/usr/bin/env node

// Live REST auth + rate-limit verification (Plan 07 W5 / Plan 04 W1).
//
// Exercises the full middleware against a REAL database (a throwaway Neon branch): issues a key,
// then drives the Hono app in-process via app.request() with valid / invalid / revoked / expired
// keys (401/403), an exhausted rate-limit window (429 + headers), the anonymous posture, and
// confirms usage_events rows landed. NEVER prints the raw key or the DATABASE_URL.
//
// Usage: DATABASE_URL=<neon-branch-url> node scripts/dev/verify-auth.mjs
// (Run against a disposable branch; it issues + revokes test keys and writes usage_events rows.)

import { createApp } from '@intercal/api';
import {
  authenticateKey,
  createDb,
  issueApiKey,
  MemoryRateLimitStore,
  revokeApiKey,
} from '@intercal/core';

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  console.error('[verify-auth] DATABASE_URL is required (point at a throwaway Neon branch).');
  process.exit(2);
}

const db = createDb(databaseUrl);
// Tight limits so the 429 path is reached in a few calls; shared in-memory store for determinism.
const app = createApp(db, {
  rateLimitStore: new MemoryRateLimitStore(),
  anonPerMinute: 3,
  keyedPerMinuteDefault: 5,
});

let pass = 0;
let fail = 0;
function check(name, cond, extra = '') {
  if (cond) {
    pass++;
    console.log(`  PASS  ${name}${extra ? ` — ${extra}` : ''}`);
  } else {
    fail++;
    console.log(`  FAIL  ${name}${extra ? ` — ${extra}` : ''}`);
  }
}

async function req(path, headers) {
  const res = await app.request(`http://localhost${path}`, { headers });
  let body = {};
  try {
    body = await res.json();
  } catch {
    /* non-json */
  }
  return { status: res.status, body, headers: res.headers };
}

const READ_PATH = '/v1/freshness?topic_or_entity=rust';

async function main() {
  console.log('[verify-auth] live REST auth + rate-limit verification\n');

  // --- Issue keys (raw keys held in memory only; never logged) ---
  const good = await issueApiKey(db, { name: 'verify good', scopes: ['read'] });
  const noRead = await issueApiKey(db, { name: 'verify noread', scopes: ['submit:feedback'] });
  const toRevoke = await issueApiKey(db, { name: 'verify revoke', scopes: ['read'] });
  const expired = await issueApiKey(db, {
    name: 'verify expired',
    scopes: ['read'],
    expiresAt: new Date(Date.now() - 60_000),
  });
  console.log(
    `[issue] created 4 test keys (ids: ${[good, noRead, toRevoke, expired].map((k) => k.id).join(', ')})`,
  );

  // Confirm only the hash is stored (no raw material in the row).
  const stored = await db
    .selectFrom('api_keys')
    .select(['key_hash', 'key_prefix'])
    .where('id', '=', good.id)
    .executeTakeFirstOrThrow();
  check('stored row holds a 64-hex hash, not the raw key', /^[0-9a-f]{64}$/.test(stored.key_hash));
  check('raw key never equals stored hash', good.raw !== stored.key_hash);

  // Core verification resolves a valid key.
  const principal = await authenticateKey(db, good.raw);
  check('authenticateKey resolves a valid key with scopes', principal.scopes.includes('read'));

  // --- HTTP: anonymous allowed ---
  const anon = await req(READ_PATH);
  check('anonymous read is admitted (not 401)', anon.status !== 401, `status=${anon.status}`);
  check(
    'anonymous response carries RateLimit-Limit=3',
    anon.headers.get('RateLimit-Limit') === '3',
  );

  // --- HTTP: valid key admitted with higher limit ---
  const keyed = await req(READ_PATH, { Authorization: `Bearer ${good.raw}` });
  check(
    'valid key is admitted (not 401/403)',
    keyed.status !== 401 && keyed.status !== 403,
    `status=${keyed.status}`,
  );
  check('valid key gets keyed limit=5', keyed.headers.get('RateLimit-Limit') === '5');

  // --- HTTP: invalid key → 401 ---
  const bad = await req(READ_PATH, { Authorization: 'Bearer ical_sk_does_not_exist' });
  check('invalid key → 401 unauthorized', bad.status === 401 && bad.body.code === 'unauthorized');

  // --- HTTP: missing-scope key → 403 ---
  const forbidden = await req(READ_PATH, { Authorization: `Bearer ${noRead.raw}` });
  check(
    'key without read scope → 403 forbidden',
    forbidden.status === 403 && forbidden.body.code === 'forbidden',
  );

  // --- HTTP: expired key → 401 ---
  const exp = await req(READ_PATH, { Authorization: `Bearer ${expired.raw}` });
  check(
    'expired key → 401 unauthorized',
    exp.status === 401 && /expired/i.test(exp.body.message ?? ''),
  );

  // --- HTTP: revoked key → 401 ---
  await revokeApiKey(db, toRevoke.id, { revokedBy: 'verify', reason: 'verification' });
  const rev = await req(READ_PATH, { Authorization: `Bearer ${toRevoke.raw}` });
  check(
    'revoked key → 401 unauthorized',
    rev.status === 401 && /revoked/i.test(rev.body.message ?? ''),
  );

  // --- HTTP: anonymous rate limit → 429 + headers ---
  // Anon already used 1 (the anon read above). Limit is 3.
  await req('/v1/freshness?topic_or_entity=a'); // 2
  await req('/v1/freshness?topic_or_entity=b'); // 3
  const over = await req('/v1/freshness?topic_or_entity=c'); // 4 → over
  check(
    'anonymous over-limit → 429 rate_limited',
    over.status === 429 && over.body.code === 'rate_limited',
  );
  check(
    '429 carries Retry-After',
    !!over.headers.get('Retry-After'),
    `retry-after=${over.headers.get('Retry-After')}`,
  );
  check('429 carries RateLimit-Remaining=0', over.headers.get('RateLimit-Remaining') === '0');

  // --- usage_events recorded ---
  // Give the best-effort async inserts a moment to flush.
  await new Promise((r) => setTimeout(r, 800));
  const counts = await db
    .selectFrom('usage_events')
    .select((eb) => eb.fn.countAll().as('n'))
    .where('tool_name', 'like', 'GET /v1/freshness%')
    .where('created_at', '>', new Date(Date.now() - 120_000))
    .executeTakeFirstOrThrow();
  const n = Number(counts.n);
  check('usage_events rows recorded for this run', n >= 6, `rows=${n}`);

  const throttled = await db
    .selectFrom('usage_events')
    .select((eb) => eb.fn.countAll().as('n'))
    .where('error_code', '=', 'rate_limited')
    .where('created_at', '>', new Date(Date.now() - 120_000))
    .executeTakeFirstOrThrow();
  check(
    'a rate_limited usage_event was recorded',
    Number(throttled.n) >= 1,
    `rows=${Number(throttled.n)}`,
  );

  const keyedRows = await db
    .selectFrom('usage_events')
    .select((eb) => eb.fn.countAll().as('n'))
    .where('api_key_id', '=', good.id)
    .executeTakeFirstOrThrow();
  check(
    'keyed request recorded with api_key_id',
    Number(keyedRows.n) >= 1,
    `rows=${Number(keyedRows.n)}`,
  );

  console.log(`\n[verify-auth] ${pass} passed, ${fail} failed`);
  await db.destroy();
  process.exit(fail === 0 ? 0 : 1);
}

main().catch(async (err) => {
  console.error(`[verify-auth] error: ${err.message}`);
  await db.destroy().catch(() => {});
  process.exit(1);
});
