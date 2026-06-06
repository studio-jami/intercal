/**
 * Server-side API-key verification against the `api_keys` table.
 *
 * Resolves an `Authorization: Bearer <key>` to an authenticated principal, or throws the mapped
 * error from the taxonomy:
 *   - missing / malformed / unknown / revoked / expired / inactive → `UnauthorizedError` (401)
 *
 * Scope enforcement (403) is the caller's job (the middleware compares the resolved scopes against
 * the operation's required scope) so this stays a pure "is this key valid right now" check. The
 * lookup is by SHA-256 hash (indexed, UNIQUE), with a constant-time hash re-comparison as defense
 * in depth. A revoked key is rejected regardless of `is_active` (the schema's documented invariant).
 */
import type { Db } from '../db/client.js';
import { UnauthorizedError } from '../errors.js';
import { hashApiKey, hashesEqual, parseBearer } from './keys.js';

/** The authenticated caller resolved from a valid key. Safe to attach to the request context. */
export interface AuthenticatedKey {
  id: string;
  name: string;
  scopes: string[];
  ownerType: string;
  ownerId: string | null;
  requestsPerMinute: number | null;
  requestsPerDay: number | null;
}

function parseScopes(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.filter((s): s is string => typeof s === 'string');
  // jsonb may surface as a string in some driver paths; tolerate both.
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter((s) => typeof s === 'string') : [];
    } catch {
      return [];
    }
  }
  return [];
}

/**
 * Resolve a raw bearer key to its principal, enforcing existence, active state, revocation, and
 * expiry. Throws `UnauthorizedError` on any failure. Best-effort updates `last_used_at`.
 */
export async function authenticateKey(db: Db, rawKey: string): Promise<AuthenticatedKey> {
  const hash = hashApiKey(rawKey);
  const row = await db
    .selectFrom('api_keys')
    .selectAll()
    .where('key_hash', '=', hash)
    .executeTakeFirst();

  if (!row || !hashesEqual(row.key_hash, hash)) {
    throw new UnauthorizedError('Invalid API key.');
  }
  if (row.revoked_at) {
    throw new UnauthorizedError('API key has been revoked.');
  }
  if (!row.is_active) {
    throw new UnauthorizedError('API key is inactive.');
  }
  if (row.expires_at && row.expires_at.getTime() <= Date.now()) {
    throw new UnauthorizedError('API key has expired.');
  }

  // Best-effort last-used stamp; never block or fail the request on this write.
  db.updateTable('api_keys')
    .set({ last_used_at: new Date() })
    .where('id', '=', row.id)
    .execute()
    .catch(() => {
      /* clock-skew / caching tolerance — see schema comment */
    });

  return {
    id: row.id,
    name: row.name,
    scopes: parseScopes(row.scopes),
    ownerType: row.owner_type,
    ownerId: row.owner_id,
    requestsPerMinute: row.requests_per_minute,
    requestsPerDay: row.requests_per_day,
  };
}

/** Resolve an Authorization header to a principal, or `null` when no credential is presented. */
export async function authenticateHeader(
  db: Db,
  authorization: string | null | undefined,
): Promise<AuthenticatedKey | null> {
  const raw = parseBearer(authorization);
  if (!raw) return null;
  return authenticateKey(db, raw);
}
