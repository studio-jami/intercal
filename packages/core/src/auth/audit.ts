/**
 * Audit-event recording — the trust ledger of who did what to trust-sensitive state.
 *
 * Distinct from `usage_events` (per-request telemetry): audit events are the security/trust record
 * of mutations to trust-sensitive state (API-key issuance/revocation today; feedback, review and
 * operator decisions, and source-policy changes as those surfaces land). Rows are append-only —
 * the DB rejects UPDATE/DELETE/TRUNCATE (migrations 0026/0027) — so this module only ever INSERTs.
 *
 * Two recording modes, deliberately different from usage recording:
 *   - `recordAuditEvent` is BEST-EFFORT (swallows errors) for emission alongside an action whose
 *     own success is already the source of truth and whose audit write must not break the request.
 *   - `recordAuditEventStrict` THROWS on failure, for callers that want the audit write to be part
 *     of the action's transactional guarantee (e.g. inside a tx with the mutation it records).
 *
 * Secrets posture: NEVER pass a raw key, hash, token, password, or any secret material in
 * `beforeState`/`afterState`/`metadata`/`rationale`. Helpers redact a known set of secret-bearing
 * keys defensively, but the contract is "identity ids and safe metadata only" (cf. AGENTS.md).
 */
import type { Db } from '../db/client.js';

/** Who performed the action. Mirrors the `audit_events.actor_type` CHECK in migration 0022. */
export type AuditActorType = 'api_key' | 'system' | 'pipeline' | 'human' | 'admin';

/** Risk classification. Mirrors the `audit_events.severity` CHECK in migration 0022. */
export type AuditSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

/**
 * Dot-namespaced action vocabulary. Only the actions whose emit point exists NOW are live; the
 * rest are declared so later workstreams emit a consistent string rather than inventing their own.
 * Wired now: `api_key.issue`, `api_key.revoke` (Plan 04 W3 / W1 lifecycle).
 * Reserved seams (emitted by their owning workstream, NOT faked here):
 *   - feedback.* — Plan 04 W4 (feedback/review records)
 *   - review.* — Plan 04 W4 / Plan 06 (operator/review console)
 *   - source.policy.* — Plan 04 W2 / Plan 06 (source policy changes, allowlist)
 *   - entity.merge / entity.merge.reverse / claim.retract / entity_resolution.* — Plan 02/Plan 06
 *   - subscription.* — Plan 04 W5
 */
export const AUDIT_ACTIONS = {
  API_KEY_ISSUE: 'api_key.issue',
  API_KEY_REVOKE: 'api_key.revoke',
  FEEDBACK_SUBMIT: 'feedback.submit',
  SUBSCRIPTION_CREATE: 'subscription.create',
  SUBSCRIPTION_DELETE: 'subscription.delete',
} as const;

export type AuditAction = (typeof AUDIT_ACTIONS)[keyof typeof AUDIT_ACTIONS] | (string & {});

export interface AuditActor {
  type: AuditActorType;
  /** Identity id: api_keys.id (uuid text), operator/user id, or job name. Never a secret. */
  id: string;
  /** Already-anonymized caller IP, or null. Same posture as usage_events. */
  ip?: string | null;
}

export interface AuditEventInput {
  actor: AuditActor;
  action: AuditAction;
  /** What the action acted on, e.g. 'api_key'. */
  targetType: string;
  /** The target's id (uuid text / slug). Never a secret. */
  targetId: string;
  /** JSON snapshot of the target before the action; omit if not applicable. NO secret values. */
  beforeState?: Record<string, unknown> | null;
  /** JSON snapshot of the target after the action; omit if not applicable. NO secret values. */
  afterState?: Record<string, unknown> | null;
  /** Human-readable note (e.g. revocation reason). NO secret values. */
  rationale?: string | null;
  /** Correlation id linking this audit row to a usage_events row / trace. */
  requestId?: string | null;
  severity?: AuditSeverity;
  /** Safe, non-secret structured context. */
  metadata?: Record<string, unknown>;
}

/**
 * Keys that must never carry a value into the audit ledger; their values are dropped. Matches as a
 * substring, case-insensitive, so renamed variants (`refreshToken`, `db_password`, `xApiKey`,
 * `connectionString`) are still caught. The ledger should only ever carry identity ids and safe
 * metadata, so this errs toward redaction.
 */
const SECRET_KEY_RE =
  /(secret|token|password|passwd|pwd|api[_-]?key|access[_-]?key|private[_-]?key|hash|raw|authorization|bearer|credential|cookie|session|dsn|conn(?:ection)?[_-]?(?:string|str|uri|url)|salt|signature)/i;

/**
 * Defensively strip secret-bearing keys from a state/metadata object before it is persisted. This
 * is a guardrail, not a license to pass secrets — callers must already avoid them. Returns a plain
 * JSON-safe object (shallow + nested), replacing redacted values with the literal '[redacted]'.
 */
function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = SECRET_KEY_RE.test(k) ? '[redacted]' : redact(v);
    }
    return out;
  }
  return value;
}

function jsonOrNull(value: Record<string, unknown> | null | undefined): string | null {
  if (value == null) return null;
  return JSON.stringify(redact(value));
}

function buildRow(event: AuditEventInput) {
  return {
    actor_type: event.actor.type,
    actor_id: event.actor.id,
    actor_ip: event.actor.ip ?? null,
    action: event.action,
    target_type: event.targetType,
    target_id: event.targetId,
    before_state: jsonOrNull(event.beforeState),
    after_state: jsonOrNull(event.afterState),
    rationale: event.rationale ?? null,
    request_id: event.requestId ?? null,
    severity: event.severity ?? 'info',
    metadata: JSON.stringify(redact(event.metadata ?? {})),
  };
}

/**
 * Append one audit row. BEST-EFFORT: swallows errors so an audit-write failure never breaks the
 * action it records (the action's own success is the source of truth). Use this for emission that
 * runs after an already-committed mutation.
 */
export async function recordAuditEvent(db: Db, event: AuditEventInput): Promise<void> {
  try {
    await db.insertInto('audit_events').values(buildRow(event)).execute();
  } catch {
    // Append-only ledger write is best-effort here; never fail the underlying action on it.
  }
}

/**
 * Append one audit row, THROWING on failure. Use inside a transaction with the mutation it records
 * when the audit write should be part of the same atomic guarantee. `db` may be a transaction.
 */
export async function recordAuditEventStrict(db: Db, event: AuditEventInput): Promise<void> {
  await db.insertInto('audit_events').values(buildRow(event)).execute();
}

export interface AuditEventRecord {
  id: string;
  actorType: string;
  actorId: string;
  actorIp: string | null;
  action: string;
  targetType: string;
  targetId: string;
  beforeState: unknown;
  afterState: unknown;
  rationale: string | null;
  requestId: string | null;
  severity: string;
  metadata: unknown;
  createdAt: Date;
}

export interface QueryAuditEventsFilter {
  actorType?: string;
  actorId?: string;
  action?: string;
  targetType?: string;
  targetId?: string;
  /** Only rows at or above this severity is not supported (severity is categorical); filter exact. */
  severity?: string;
  /** Newest-first page size. Defaults to 100, capped at 1000. */
  limit?: number;
}

/**
 * Read audit events for operations (Plan 04 W6 observability + Plan 05 security review). Newest
 * first. Pure read against the append-only ledger.
 */
export async function queryAuditEvents(
  db: Db,
  filter: QueryAuditEventsFilter = {},
): Promise<AuditEventRecord[]> {
  let q = db.selectFrom('audit_events').selectAll().orderBy('created_at', 'desc');
  if (filter.actorType) q = q.where('actor_type', '=', filter.actorType);
  if (filter.actorId) q = q.where('actor_id', '=', filter.actorId);
  if (filter.action) q = q.where('action', '=', filter.action);
  if (filter.targetType) q = q.where('target_type', '=', filter.targetType);
  if (filter.targetId) q = q.where('target_id', '=', filter.targetId);
  if (filter.severity) q = q.where('severity', '=', filter.severity);
  q = q.limit(Math.min(Math.max(filter.limit ?? 100, 1), 1000));

  const rows = await q.execute();
  return rows.map((r) => ({
    id: r.id,
    actorType: r.actor_type,
    actorId: r.actor_id,
    actorIp: r.actor_ip,
    action: r.action,
    targetType: r.target_type,
    targetId: r.target_id,
    beforeState: r.before_state,
    afterState: r.after_state,
    rationale: r.rationale,
    requestId: r.request_id,
    severity: r.severity,
    metadata: r.metadata,
    createdAt: r.created_at,
  }));
}
