/**
 * API-key primitives: generation, hashing, and constant-time hash comparison.
 *
 * Security model (matches db/migrations/0020_api_keys.sql):
 *   - A raw key is a high-entropy random token, displayed to the operator EXACTLY ONCE at issuance
 *     and never stored. Only its SHA-256 hex digest is persisted (`api_keys.key_hash`, UNIQUE).
 *   - The raw key carries 256 bits of CSPRNG entropy, so SHA-256 (a fast hash) is the correct
 *     choice: slow KDFs (bcrypt/scrypt/argon2) exist to defend LOW-entropy human passwords against
 *     brute force; they add nothing against a 256-bit random secret and would only slow every
 *     authenticated request. This is the standard posture for bearer API keys (cf. GitHub, Stripe).
 *   - The on-the-wire format is `ical_sk_<base62-token>`; `ical_sk_` is the `key_prefix` recorded
 *     for display/recognition (it is NOT secret and never used in the hash lookup).
 */
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';

/** Visible, non-secret prefix recorded on the key row for display ("ical_sk_…"). */
export const KEY_PREFIX = 'ical_sk_';

/** Bytes of CSPRNG entropy in the secret portion of a key (256 bits). */
const KEY_ENTROPY_BYTES = 32;

const BASE62 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';

/** Encode bytes as base62 (URL-safe, no padding) for a compact, copy-pasteable token. */
function base62(bytes: Buffer): string {
  let out = '';
  for (const b of bytes) out += BASE62.charAt(b % 62);
  return out;
}

export interface GeneratedKey {
  /** The full raw key, shown once and never stored: `ical_sk_<token>`. */
  raw: string;
  /** SHA-256 hex of the raw key — what is persisted in `api_keys.key_hash`. */
  hash: string;
  /** The display prefix recorded in `api_keys.key_prefix`. */
  prefix: string;
}

/** Generate a fresh API key. The caller stores `hash`+`prefix` and shows `raw` to the user once. */
export function generateApiKey(): GeneratedKey {
  const token = base62(randomBytes(KEY_ENTROPY_BYTES));
  const raw = `${KEY_PREFIX}${token}`;
  return { raw, hash: hashApiKey(raw), prefix: KEY_PREFIX };
}

/** SHA-256 hex digest of a raw key. Stable: the value stored at issuance equals the lookup value. */
export function hashApiKey(raw: string): string {
  return createHash('sha256').update(raw, 'utf8').digest('hex');
}

/** Constant-time comparison of two hex digests (defense in depth around the DB lookup). */
export function hashesEqual(a: string, b: string): boolean {
  const ba = Buffer.from(a, 'hex');
  const bb = Buffer.from(b, 'hex');
  if (ba.length !== bb.length || ba.length === 0) return false;
  return timingSafeEqual(ba, bb);
}

/**
 * Extract a Bearer token from an `Authorization` header value. Returns the raw key or `null` when
 * the header is missing or not a well-formed `Bearer <token>`. Tolerant of extra whitespace and
 * case in the scheme; the token itself is returned verbatim.
 */
export function parseBearer(header: string | null | undefined): string | null {
  if (!header) return null;
  const m = /^\s*Bearer\s+(\S+)\s*$/i.exec(header);
  return m?.[1] ?? null;
}
