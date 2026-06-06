/**
 * Unit tests for the auth primitives and the rate-limit store — the pure, DB-free surface.
 * Key verification against a live DB and the middleware wiring are covered by the API package's
 * middleware tests (fake Db) and the live Neon integration verification.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRateLimitStore } from '../ratelimit/memory.js';
import { generateApiKey, hashApiKey, hashesEqual, KEY_PREFIX, parseBearer } from './keys.js';
import { hasScope, READ_SCOPE, SCOPES } from './scopes.js';

describe('generateApiKey', () => {
  it('produces a prefixed, high-entropy raw key and a stable SHA-256 hash', () => {
    const k = generateApiKey();
    expect(k.raw.startsWith(KEY_PREFIX)).toBe(true);
    expect(k.prefix).toBe(KEY_PREFIX);
    // 32 bytes base62 → 32 chars after the prefix.
    expect(k.raw.length).toBe(KEY_PREFIX.length + 32);
    expect(k.hash).toBe(hashApiKey(k.raw));
    expect(k.hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it('never repeats a key across calls', () => {
    const seen = new Set<string>();
    for (let i = 0; i < 200; i++) seen.add(generateApiKey().raw);
    expect(seen.size).toBe(200);
  });
});

describe('hashesEqual', () => {
  it('is true for identical hex digests and false otherwise', () => {
    const a = hashApiKey('ical_sk_one');
    const b = hashApiKey('ical_sk_one');
    const c = hashApiKey('ical_sk_two');
    expect(hashesEqual(a, b)).toBe(true);
    expect(hashesEqual(a, c)).toBe(false);
  });

  it('is false for empty or malformed input', () => {
    expect(hashesEqual('', '')).toBe(false);
    expect(hashesEqual('zz', 'zz')).toBe(false); // not valid hex bytes of equal length to a digest
  });
});

describe('parseBearer', () => {
  it('extracts the token from a well-formed header (case/space tolerant)', () => {
    expect(parseBearer('Bearer ical_sk_abc')).toBe('ical_sk_abc');
    expect(parseBearer('  bearer   ical_sk_abc  ')).toBe('ical_sk_abc');
  });
  it('returns null for missing or malformed headers', () => {
    expect(parseBearer(undefined)).toBeNull();
    expect(parseBearer(null)).toBeNull();
    expect(parseBearer('')).toBeNull();
    expect(parseBearer('Basic abc')).toBeNull();
    expect(parseBearer('Bearer')).toBeNull();
  });
});

describe('hasScope', () => {
  it('grants on exact match', () => {
    expect(hasScope([READ_SCOPE], READ_SCOPE)).toBe(true);
  });
  it('denies when the scope is absent', () => {
    expect(hasScope([SCOPES.SUBMIT_FEEDBACK], READ_SCOPE)).toBe(false);
    expect(hasScope([], READ_SCOPE)).toBe(false);
  });
  it('treats admin as a superscope', () => {
    expect(hasScope([SCOPES.ADMIN], READ_SCOPE)).toBe(true);
    expect(hasScope([SCOPES.ADMIN], SCOPES.MANAGE_SUBSCRIPTIONS)).toBe(true);
  });
});

describe('MemoryRateLimitStore', () => {
  it('counts upward within a window and reports a reset', async () => {
    const store = new MemoryRateLimitStore();
    const a = await store.incr('k', 60);
    const b = await store.incr('k', 60);
    expect(a.count).toBe(1);
    expect(b.count).toBe(2);
    expect(b.resetSeconds).toBeGreaterThan(0);
    expect(b.resetSeconds).toBeLessThanOrEqual(60);
  });

  it('isolates distinct keys', async () => {
    const store = new MemoryRateLimitStore();
    await store.incr('a', 60);
    const second = await store.incr('b', 60);
    expect(second.count).toBe(1);
  });

  it('resets the counter after the window elapses', async () => {
    vi.useFakeTimers();
    const store = new MemoryRateLimitStore();
    const first = await store.incr('k', 60);
    expect(first.count).toBe(1);
    // Advance past the window: the next increment opens a fresh window at count 1.
    vi.advanceTimersByTime(61_000);
    const after = await store.incr('k', 60);
    expect(after.count).toBe(1);
  });
});

afterEach(() => {
  vi.useRealTimers();
});
