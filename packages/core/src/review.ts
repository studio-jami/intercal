import { AUDIT_ACTIONS, type AuditActor, recordAuditEventStrict } from './auth/audit.js';
import type { Db } from './db/client.js';
import { InvalidRequestError, NotFoundError } from './errors.js';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type FeedbackTargetType =
  | 'entity'
  | 'claim'
  | 'source'
  | 'digest'
  | 'freshness'
  | 'coverage';
export type FeedbackConcernType =
  | 'incorrect'
  | 'outdated'
  | 'missing_evidence'
  | 'missing_coverage'
  | 'source_quality'
  | 'contradiction'
  | 'other';
export type ReviewStatus = 'received' | 'reviewing' | 'resolved' | 'rejected';

export interface SubmitFeedbackParams {
  targetType: FeedbackTargetType;
  targetId: string;
  concernType: FeedbackConcernType;
  summary: string;
  details?: string;
}

export interface SubmitFeedbackContext {
  actor: AuditActor;
  reporter:
    | { type: 'anonymous'; id?: null }
    | {
        type: 'api_key';
        id: string;
      };
  requestId?: string | null;
}

export interface ReviewRecord {
  id: string;
  targetType: FeedbackTargetType;
  targetId: string;
  concernType: FeedbackConcernType;
  status: ReviewStatus;
  summary: string;
  details?: string;
  createdAt: Date;
}

export interface FeedbackResponse {
  review: ReviewRecord;
}

async function ensureTargetExists(db: Db, targetType: FeedbackTargetType, targetId: string) {
  switch (targetType) {
    case 'entity': {
      if (!UUID_RE.test(targetId))
        throw new InvalidRequestError('entity feedback target must be a UUID');
      const row = await db
        .selectFrom('entities')
        .select('id')
        .where('id', '=', targetId)
        .executeTakeFirst();
      if (!row) throw new NotFoundError('Feedback target entity was not found');
      return;
    }
    case 'claim': {
      if (!UUID_RE.test(targetId))
        throw new InvalidRequestError('claim feedback target must be a UUID');
      const row = await db
        .selectFrom('claims')
        .select('id')
        .where('id', '=', targetId)
        .executeTakeFirst();
      if (!row) throw new NotFoundError('Feedback target claim was not found');
      return;
    }
    case 'source': {
      const row = await db
        .selectFrom('sources')
        .select('id')
        .where('id', '=', targetId)
        .executeTakeFirst();
      if (!row) throw new NotFoundError('Feedback target source was not found');
      return;
    }
    case 'digest': {
      if (!UUID_RE.test(targetId))
        throw new InvalidRequestError('digest feedback target must be a UUID');
      const row = await db
        .selectFrom('digests')
        .select('id')
        .where('id', '=', targetId)
        .executeTakeFirst();
      if (!row) throw new NotFoundError('Feedback target digest was not found');
      return;
    }
    case 'freshness':
    case 'coverage':
      if (!targetId.trim()) {
        throw new InvalidRequestError(`${targetType} feedback target must not be empty`);
      }
      return;
  }
}

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

function toReview(row: {
  id: string;
  target_type: string;
  target_id: string;
  concern_type: string;
  status: string;
  summary: string;
  details: string | null;
  created_at: Date;
}): ReviewRecord {
  return {
    id: row.id,
    targetType: row.target_type as FeedbackTargetType,
    targetId: row.target_id,
    concernType: row.concern_type as FeedbackConcernType,
    status: row.status as ReviewStatus,
    summary: row.summary,
    ...(row.details ? { details: row.details } : {}),
    createdAt: row.created_at,
  };
}

export async function submitFeedback(
  db: Db,
  params: SubmitFeedbackParams,
  context: SubmitFeedbackContext,
): Promise<FeedbackResponse> {
  const summary = normalizeText(params.summary);
  const details = params.details === undefined ? null : params.details.trim();
  const targetId = normalizeText(params.targetId);

  if (summary.length === 0) throw new InvalidRequestError('feedback summary must not be empty');
  if (summary.length > 240)
    throw new InvalidRequestError('feedback summary exceeds 240 characters');
  if (details !== null && details.length > 4000) {
    throw new InvalidRequestError('feedback details exceeds 4000 characters');
  }
  if (targetId.length === 0) throw new InvalidRequestError('feedback targetId must not be empty');

  return db.transaction().execute(async (tx) => {
    await ensureTargetExists(tx as Db, params.targetType, targetId);

    const row = await tx
      .insertInto('review_records')
      .values({
        target_type: params.targetType,
        target_id: targetId,
        concern_type: params.concernType,
        summary,
        details,
        reporter_type: context.reporter.type,
        reporter_id: context.reporter.type === 'api_key' ? context.reporter.id : null,
        request_id: context.requestId ?? null,
        metadata: JSON.stringify({ source: 'public_api' }),
      })
      .returning([
        'id',
        'target_type',
        'target_id',
        'concern_type',
        'status',
        'summary',
        'details',
        'created_at',
      ])
      .executeTakeFirstOrThrow();

    await recordAuditEventStrict(tx as Db, {
      actor: context.actor,
      action: AUDIT_ACTIONS.FEEDBACK_SUBMIT,
      targetType: 'review_record',
      targetId: row.id,
      afterState: {
        id: row.id,
        targetType: row.target_type,
        targetId: row.target_id,
        concernType: row.concern_type,
        status: row.status,
      },
      requestId: context.requestId ?? null,
      severity: 'low',
      metadata: {
        targetType: row.target_type,
        targetId: row.target_id,
        reporterType: context.reporter.type,
      },
    });

    return { review: toReview(row) };
  });
}
