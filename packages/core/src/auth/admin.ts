/**
 * Operator-only key lifecycle: issue, revoke, and list API keys. Used by the `scripts/ops` admin
 * CLI. No auth-bypass backdoors and no hardcoded keys — every key is CSPRNG-generated, its raw form
 * returned to the caller exactly once, and only the hash persisted.
 */
import type { Db } from '../db/client.js';
import { NotFoundError } from '../errors.js';
import { generateApiKey } from './keys.js';

export interface IssueKeyInput {
  name: string;
  scopes: string[];
  ownerType?: 'user' | 'service' | 'system';
  ownerId?: string | null;
  requestsPerMinute?: number | null;
  requestsPerDay?: number | null;
  /** Absolute expiry; omit for a non-expiring key. */
  expiresAt?: Date | null;
  metadata?: Record<string, unknown>;
}

export interface IssuedKey {
  id: string;
  name: string;
  /** The raw key — show ONCE, never logged or stored. */
  raw: string;
  prefix: string;
  scopes: string[];
  expiresAt: Date | null;
}

/** Issue a new key. Returns the raw key (display once) plus the persisted metadata. */
export async function issueApiKey(db: Db, input: IssueKeyInput): Promise<IssuedKey> {
  const { raw, hash, prefix } = generateApiKey();
  const row = await db
    .insertInto('api_keys')
    .values({
      name: input.name,
      key_prefix: prefix,
      key_hash: hash,
      scopes: JSON.stringify(input.scopes),
      owner_type: input.ownerType ?? 'user',
      owner_id: input.ownerId ?? null,
      requests_per_minute: input.requestsPerMinute ?? null,
      requests_per_day: input.requestsPerDay ?? null,
      expires_at: input.expiresAt ?? null,
      metadata: JSON.stringify(input.metadata ?? {}),
    })
    .returning(['id', 'name', 'key_prefix', 'expires_at'])
    .executeTakeFirstOrThrow();

  return {
    id: row.id,
    name: row.name,
    raw,
    prefix: row.key_prefix,
    scopes: input.scopes,
    expiresAt: row.expires_at,
  };
}

/** Revoke a key by id. Sets the authoritative `revoked_at` and deactivates. Idempotent-safe. */
export async function revokeApiKey(
  db: Db,
  id: string,
  opts: { revokedBy?: string; reason?: string } = {},
): Promise<void> {
  const res = await db
    .updateTable('api_keys')
    .set({
      revoked_at: new Date(),
      is_active: false,
      revoked_by: opts.revokedBy ?? null,
      revocation_reason: opts.reason ?? null,
      updated_at: new Date(),
    })
    .where('id', '=', id)
    .executeTakeFirst();
  if (res.numUpdatedRows === 0n) {
    throw new NotFoundError(`No API key with id ${id}.`);
  }
}

export interface KeySummary {
  id: string;
  name: string;
  keyPrefix: string;
  scopes: string[];
  ownerType: string;
  ownerId: string | null;
  isActive: boolean;
  expiresAt: Date | null;
  lastUsedAt: Date | null;
  revokedAt: Date | null;
  createdAt: Date;
}

/** List keys (metadata only — never any hash or raw material). Newest first. */
export async function listApiKeys(db: Db): Promise<KeySummary[]> {
  const rows = await db
    .selectFrom('api_keys')
    .select([
      'id',
      'name',
      'key_prefix',
      'scopes',
      'owner_type',
      'owner_id',
      'is_active',
      'expires_at',
      'last_used_at',
      'revoked_at',
      'created_at',
    ])
    .orderBy('created_at', 'desc')
    .execute();

  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    keyPrefix: r.key_prefix,
    scopes: Array.isArray(r.scopes) ? (r.scopes as string[]) : [],
    ownerType: r.owner_type,
    ownerId: r.owner_id,
    isActive: r.is_active,
    expiresAt: r.expires_at,
    lastUsedAt: r.last_used_at,
    revokedAt: r.revoked_at,
    createdAt: r.created_at,
  }));
}
