/**
 * UpstashRateLimitStore unit tests — exercise the REST pipeline shape, normal counting, and the
 * self-heal of a counter that has lost its TTL, all against a fake `fetch`. No network is touched.
 */
import { describe, expect, it, vi } from 'vitest';
import { UpstashRateLimitStore } from './upstash.js';

/** Build a fake fetch that returns Upstash pipeline results in command order, and records calls. */
function fakeFetch(responses: Array<Array<{ result?: number; error?: string }>>) {
  const calls: Array<unknown> = [];
  let i = 0;
  const impl = (async (_url: string, init: RequestInit) => {
    calls.push(JSON.parse(String(init.body)));
    const body = responses[i++] ?? [];
    return new Response(JSON.stringify(body), { status: 200 });
  }) as unknown as typeof fetch;
  return { impl, calls };
}

describe('UpstashRateLimitStore', () => {
  it('issues INCR + EXPIRE NX + PTTL and reports count + reset from PTTL', async () => {
    const { impl, calls } = fakeFetch([[{ result: 1 }, { result: 1 }, { result: 45_000 }]]);
    const store = new UpstashRateLimitStore('https://x.upstash.io/', 'tok', impl);
    const out = await store.incr('rl:ip:1.2.3.4', 60);
    expect(out.count).toBe(1);
    expect(out.resetSeconds).toBe(45);
    // One pipeline call with the three expected commands (no self-heal needed).
    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual([
      ['INCR', 'rl:ip:1.2.3.4'],
      ['EXPIRE', 'rl:ip:1.2.3.4', '60', 'NX'],
      ['PTTL', 'rl:ip:1.2.3.4'],
    ]);
  });

  it('self-heals a counter with no TTL (PTTL -1) by re-arming the window', async () => {
    const { impl, calls } = fakeFetch([
      // INCR ok, EXPIRE NX no-op (0), PTTL -1 → key exists but has no expiry.
      [{ result: 7 }, { result: 0 }, { result: -1 }],
      // Repair EXPIRE.
      [{ result: 1 }],
    ]);
    const store = new UpstashRateLimitStore('https://x.upstash.io', 'tok', impl);
    const out = await store.incr('rl:ip:bad', 60);
    expect(out.count).toBe(7);
    // Reset reported as the full window after the repair.
    expect(out.resetSeconds).toBe(60);
    expect(calls).toHaveLength(2);
    expect(calls[1]).toEqual([['EXPIRE', 'rl:ip:bad', '60']]);
  });

  it('self-heals when the key vanished mid-pipeline (PTTL -2)', async () => {
    const { impl, calls } = fakeFetch([
      [{ result: 1 }, { result: 0 }, { result: -2 }],
      [{ result: 1 }],
    ]);
    const store = new UpstashRateLimitStore('https://x.upstash.io', 'tok', impl);
    const out = await store.incr('rl:ip:gone', 60);
    expect(out.resetSeconds).toBe(60);
    expect(calls).toHaveLength(2);
  });

  it('throws on an INCR command error (so the caller can fail-open)', async () => {
    const { impl } = fakeFetch([[{ error: 'WRONGTYPE' }, { result: 0 }, { result: -1 }]]);
    const store = new UpstashRateLimitStore('https://x.upstash.io', 'tok', impl);
    await expect(store.incr('k', 60)).rejects.toThrow(/INCR error/);
  });

  it('throws on an EXPIRE command error', async () => {
    const { impl } = fakeFetch([[{ result: 1 }, { error: 'ERR' }, { result: 1000 }]]);
    const store = new UpstashRateLimitStore('https://x.upstash.io', 'tok', impl);
    await expect(store.incr('k', 60)).rejects.toThrow(/EXPIRE error/);
  });

  it('throws on a non-200 pipeline response', async () => {
    const impl = (async () => new Response('nope', { status: 500 })) as unknown as typeof fetch;
    const store = new UpstashRateLimitStore('https://x.upstash.io', 'tok', impl);
    await expect(store.incr('k', 60)).rejects.toThrow(/HTTP 500/);
  });

  it('strips a trailing slash from the REST URL', async () => {
    const spy = vi.fn(
      async () =>
        new Response(JSON.stringify([{ result: 1 }, { result: 1 }, { result: 60_000 }]), {
          status: 200,
        }),
    ) as unknown as typeof fetch;
    const store = new UpstashRateLimitStore('https://x.upstash.io///', 'tok', spy);
    await store.incr('k', 60);
    expect((spy as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      'https://x.upstash.io/pipeline',
    );
  });
});
