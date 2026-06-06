import { createHash } from 'node:crypto';
import type { components } from '@intercal/shared';
import type { Selectable } from 'kysely';
import { AUDIT_ACTIONS, type AuditActor, recordAuditEventStrict } from './auth/audit.js';
import type { Db } from './db/client.js';
import type { SubscriptionNotificationsTable, SubscriptionsTable } from './db/types.js';
import { buildDelta } from './delta.js';
import { ForbiddenError, InvalidRequestError, NotFoundError } from './errors.js';

type DeltaResponse = components['schemas']['DeltaResponse'];
type SubscriptionRow = Selectable<SubscriptionsTable>;
type SubscriptionNotificationRow = Selectable<SubscriptionNotificationsTable>;

export type SubscriptionDeliveryMethod = 'polling' | 'webhook';
export type SubscriptionTargetKind = 'topic' | 'entity' | 'relationship' | 'claim_pattern';

export interface CreateSubscriptionInput {
  apiKeyId: string;
  actor: AuditActor;
  target: {
    kind: SubscriptionTargetKind;
    topicId?: string;
    entityId?: string;
    relationshipTypeId?: string;
    claimPattern?: Record<string, unknown>;
  };
  deliveryMethod: SubscriptionDeliveryMethod;
  webhookUrl?: string;
  webhookSecret?: string;
  minImportance?: number;
  tokenBudget?: number;
  metadata?: Record<string, unknown>;
}

export interface SubscriptionRecord {
  id: string;
  target: {
    kind: SubscriptionTargetKind;
    topicId?: string;
    entityId?: string;
    relationshipTypeId?: string;
    claimPattern?: unknown;
  };
  deliveryMethod: SubscriptionDeliveryMethod;
  webhookUrl?: string;
  minImportance: number;
  tokenBudget: number;
  isActive: boolean;
  lastDeliveredAt?: string;
  lastCheckedAt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface EnqueueSubscriptionChangeInput {
  actor: AuditActor;
  dispatchScope:
    | { type: 'api_key'; apiKeyId: string }
    | { type: 'internal_all_active'; reason: string };
  changeKind: SubscriptionTargetKind;
  topicId?: string;
  entityId?: string;
  relationshipTypeId?: string;
  claimPattern?: Record<string, unknown>;
  sinceDate: string;
  untilDate?: string;
}

export interface PollSubscriptionInput {
  apiKeyId: string;
  subscriptionId: string;
  limit?: number;
}

export interface SubscriptionNotificationRecord {
  id: string;
  subscriptionId: string;
  changeKind: SubscriptionTargetKind;
  targetLabel: string;
  since: string;
  until: string;
  minImportance: number;
  maxImportance: number;
  tokenBudget: number;
  payload: unknown;
  status: string;
  createdAt: string;
  deliveredAt?: string;
}

type ClaimPattern = Record<string, unknown>;

export interface WebhookDeliveryRequest {
  url: string;
  notificationId: string;
  subscriptionId: string;
  payload: unknown;
}

export interface WebhookDeliveryResult {
  ok: boolean;
  status?: number;
  errorCode?: string;
  errorMessage?: string;
}

export interface WebhookDeliveryPort {
  deliver(request: WebhookDeliveryRequest): Promise<WebhookDeliveryResult>;
}

const DEFAULT_TOKEN_BUDGET = 1500;
const MIN_TOKEN_BUDGET = 200;
const MAX_TOKEN_BUDGET = 8000;
const DEFAULT_MIN_IMPORTANCE = 0;
const MAX_POLL_LIMIT = 100;
const MAX_WEBHOOK_ATTEMPTS = 5;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function clampBudget(value: number | undefined | null): number {
  if (value == null || !Number.isFinite(value)) return DEFAULT_TOKEN_BUDGET;
  return Math.min(MAX_TOKEN_BUDGET, Math.max(MIN_TOKEN_BUDGET, Math.floor(value)));
}

function clampImportance(value: number | undefined | null): number {
  if (value == null || !Number.isFinite(value)) return DEFAULT_MIN_IMPORTANCE;
  return Math.min(1, Math.max(0, Number(value)));
}

function hashWebhookSecret(secret: string): string {
  return createHash('sha256').update(secret, 'utf8').digest('hex');
}

function parseClaimPattern(value: unknown): unknown {
  if (typeof value === 'string') {
    try {
      return JSON.parse(value) as unknown;
    } catch {
      return value;
    }
  }
  return value;
}

function isRecord(value: unknown): value is ClaimPattern {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isNonEmptyPattern(value: unknown): value is ClaimPattern {
  return isRecord(value) && Object.keys(value).length > 0;
}

function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

function validateUuidTarget(kind: SubscriptionTargetKind, value: string): void {
  if ((kind === 'topic' || kind === 'entity') && !isUuid(value)) {
    throw new InvalidRequestError(`${kind} subscription target must be a UUID.`);
  }
}

function claimPatternMatches(subscriptionPattern: unknown, changePattern: unknown): boolean {
  if (!isNonEmptyPattern(subscriptionPattern) || !isNonEmptyPattern(changePattern)) return false;
  return Object.entries(subscriptionPattern).every(
    ([key, value]) =>
      Object.hasOwn(changePattern, key) &&
      JSON.stringify((changePattern as ClaimPattern)[key]) === JSON.stringify(value),
  );
}

function targetKind(row: SubscriptionRow): SubscriptionTargetKind {
  if (row.topic_id) return 'topic';
  if (row.entity_id) return 'entity';
  if (row.relationship_type_id) return 'relationship';
  return 'claim_pattern';
}

function mapSubscription(row: SubscriptionRow): SubscriptionRecord {
  const kind = targetKind(row);
  return {
    id: row.id,
    target: {
      kind,
      ...(row.topic_id ? { topicId: row.topic_id } : {}),
      ...(row.entity_id ? { entityId: row.entity_id } : {}),
      ...(row.relationship_type_id ? { relationshipTypeId: row.relationship_type_id } : {}),
      ...(row.claim_pattern ? { claimPattern: parseClaimPattern(row.claim_pattern) } : {}),
    },
    deliveryMethod: row.delivery_method as unknown as SubscriptionDeliveryMethod,
    ...(row.webhook_url ? { webhookUrl: row.webhook_url } : {}),
    minImportance: Number(row.min_importance),
    tokenBudget: clampBudget(row.token_budget),
    isActive: row.is_active,
    ...(row.last_delivered_at ? { lastDeliveredAt: row.last_delivered_at.toISOString() } : {}),
    ...(row.last_checked_at ? { lastCheckedAt: row.last_checked_at.toISOString() } : {}),
    createdAt: row.created_at.toISOString(),
    updatedAt: row.updated_at.toISOString(),
  };
}

function maxDeltaImportance(delta: DeltaResponse): number {
  const entitySignal = delta.changedEntities.length > 0 ? 1 : 0;
  const claimSignal = delta.changedClaims.reduce(
    (max, claim) => Math.max(max, claim.confidence?.score ?? 0),
    0,
  );
  return Math.max(entitySignal, claimSignal, delta.confidence?.score ?? 0);
}

function notificationPayload(delta: DeltaResponse) {
  return {
    topic: delta.topic,
    since: delta.since,
    until: delta.until,
    summary: delta.summary,
    changedClaimIds: delta.changedClaims.map((claim) => claim.id),
    changedEntities: delta.changedEntities,
    confidence: delta.confidence,
    freshness: delta.freshness,
  };
}

function mapNotification(row: SubscriptionNotificationRow): SubscriptionNotificationRecord {
  return {
    id: row.id,
    subscriptionId: row.subscription_id,
    changeKind: row.change_kind as SubscriptionTargetKind,
    targetLabel: row.target_label,
    since: row.since_date.toISOString(),
    until: row.until_date.toISOString(),
    minImportance: Number(row.min_importance),
    maxImportance: Number(row.max_importance),
    tokenBudget: row.token_budget,
    payload: typeof row.payload === 'string' ? JSON.parse(row.payload) : row.payload,
    status: row.status,
    createdAt: row.created_at.toISOString(),
    ...(row.delivered_at ? { deliveredAt: row.delivered_at.toISOString() } : {}),
  };
}

async function targetLabelForSubscription(db: Db, row: SubscriptionRow): Promise<string> {
  if (row.entity_id) {
    const entity = await db
      .selectFrom('entities')
      .select('canonical_name')
      .where('id', '=', row.entity_id)
      .executeTakeFirst();
    return entity?.canonical_name ?? row.entity_id;
  }
  if (row.topic_id) {
    const topic = await db
      .selectFrom('topics')
      .select('name')
      .where('id', '=', row.topic_id)
      .executeTakeFirst();
    return topic?.name ?? row.topic_id;
  }
  if (row.relationship_type_id) return row.relationship_type_id;
  const pattern = parseClaimPattern(row.claim_pattern);
  if (pattern && typeof pattern === 'object') {
    const p = pattern as Record<string, unknown>;
    return [p.subject, p.predicate, p.object].filter(Boolean).join(' ') || 'claim pattern';
  }
  return 'claim pattern';
}

function validateCreate(input: CreateSubscriptionInput): void {
  const allowedTargetKeys = new Set([
    'kind',
    'topicId',
    'entityId',
    'relationshipTypeId',
    'claimPattern',
  ]);
  for (const key of Object.keys(input.target as Record<string, unknown>)) {
    if (!allowedTargetKeys.has(key)) {
      throw new InvalidRequestError(`Unknown subscription target field: ${key}.`);
    }
  }
  const targetFields = {
    topic: input.target.topicId,
    entity: input.target.entityId,
    relationship: input.target.relationshipTypeId,
    claim_pattern: input.target.claimPattern,
  } satisfies Record<SubscriptionTargetKind, unknown>;
  const supplied = Object.entries(targetFields).filter(([, value]) => value != null);
  if (supplied.length !== 1 || supplied[0]?.[0] !== input.target.kind) {
    throw new InvalidRequestError(
      'Exactly one subscription target matching target.kind is required.',
    );
  }
  if (input.target.kind !== 'claim_pattern' && !isNonEmptyString(supplied[0]?.[1])) {
    throw new InvalidRequestError('Subscription target IDs must be non-empty strings.');
  }
  if (input.target.kind !== 'claim_pattern') {
    validateUuidTarget(input.target.kind, supplied[0]?.[1] as string);
  }
  if (input.target.kind === 'claim_pattern' && !isNonEmptyPattern(input.target.claimPattern)) {
    throw new InvalidRequestError('claimPattern must be a non-empty object.');
  }
  if (input.deliveryMethod === 'polling' && (input.webhookUrl || input.webhookSecret)) {
    throw new InvalidRequestError('Webhook URL and secret are only accepted for webhook delivery.');
  }
  if (input.deliveryMethod === 'webhook') {
    if (!input.webhookUrl)
      throw new InvalidRequestError('webhookUrl is required for webhook delivery.');
    let url: URL;
    try {
      url = new URL(input.webhookUrl);
    } catch {
      throw new InvalidRequestError('webhookUrl must be a valid https URL.');
    }
    if (url.protocol !== 'https:') throw new InvalidRequestError('webhookUrl must use https.');
    if (input.webhookSecret && input.webhookSecret.length < 16) {
      throw new InvalidRequestError('webhookSecret must be at least 16 characters.');
    }
  }
}

function validateDispatch(input: EnqueueSubscriptionChangeInput): void {
  if (!input.dispatchScope) {
    throw new InvalidRequestError('Subscription dispatch requires an explicit dispatch scope.');
  }
  if (input.dispatchScope.type === 'api_key' && !isNonEmptyString(input.dispatchScope.apiKeyId)) {
    throw new InvalidRequestError('API-key dispatch scope requires a non-empty apiKeyId.');
  }
  if (
    input.dispatchScope.type === 'internal_all_active' &&
    !isNonEmptyString(input.dispatchScope.reason)
  ) {
    throw new InvalidRequestError('Internal all-active dispatch scope requires a reason.');
  }
  const allowedDispatchKeys = new Set([
    'actor',
    'dispatchScope',
    'changeKind',
    'topicId',
    'entityId',
    'relationshipTypeId',
    'claimPattern',
    'sinceDate',
    'untilDate',
  ]);
  for (const key of Object.keys(input as unknown as Record<string, unknown>)) {
    if (!allowedDispatchKeys.has(key)) {
      throw new InvalidRequestError(`Unknown subscription dispatch field: ${key}.`);
    }
  }
  const targetFields = {
    topic: input.topicId,
    entity: input.entityId,
    relationship: input.relationshipTypeId,
    claim_pattern: input.claimPattern,
  } satisfies Record<SubscriptionTargetKind, unknown>;
  const supplied = Object.entries(targetFields).filter(([, value]) => value != null);
  if (supplied.length !== 1 || supplied[0]?.[0] !== input.changeKind) {
    throw new InvalidRequestError('Exactly one dispatch target matching changeKind is required.');
  }
  if (input.changeKind !== 'claim_pattern' && !isNonEmptyString(supplied[0]?.[1])) {
    throw new InvalidRequestError('Dispatch target IDs must be non-empty strings.');
  }
  if (input.changeKind !== 'claim_pattern') {
    validateUuidTarget(input.changeKind, supplied[0]?.[1] as string);
  }
  if (input.changeKind === 'claim_pattern' && !isNonEmptyPattern(input.claimPattern)) {
    throw new InvalidRequestError('claimPattern must be a non-empty object.');
  }
}

export async function createSubscription(
  db: Db,
  input: CreateSubscriptionInput,
): Promise<SubscriptionRecord> {
  validateCreate(input);
  const minImportance = clampImportance(input.minImportance);
  const tokenBudget = clampBudget(input.tokenBudget);
  const row = await db.transaction().execute(async (tx) => {
    const inserted = await tx
      .insertInto('subscriptions')
      .values({
        api_key_id: input.apiKeyId,
        topic_id: input.target.topicId ?? null,
        entity_id: input.target.entityId ?? null,
        relationship_type_id: input.target.relationshipTypeId ?? null,
        claim_pattern: input.target.claimPattern ? JSON.stringify(input.target.claimPattern) : null,
        min_importance: minImportance,
        token_budget: tokenBudget,
        delivery_method: input.deliveryMethod,
        webhook_url: input.deliveryMethod === 'webhook' ? (input.webhookUrl ?? null) : null,
        webhook_secret_hash: input.webhookSecret ? hashWebhookSecret(input.webhookSecret) : null,
        metadata: JSON.stringify(input.metadata ?? {}),
      })
      .returningAll()
      .executeTakeFirstOrThrow();
    await recordAuditEventStrict(tx, {
      actor: input.actor,
      action: AUDIT_ACTIONS.SUBSCRIPTION_CREATE,
      targetType: 'subscription',
      targetId: inserted.id,
      afterState: {
        deliveryMethod: inserted.delivery_method,
        targetKind: targetKind(inserted),
        minImportance,
        tokenBudget,
        hasWebhookSecret: Boolean(inserted.webhook_secret_hash),
      },
      severity: 'medium',
    });
    return inserted;
  });
  return mapSubscription(row);
}

export async function listSubscriptions(db: Db, apiKeyId: string): Promise<SubscriptionRecord[]> {
  const rows = await db
    .selectFrom('subscriptions')
    .selectAll()
    .where('api_key_id', '=', apiKeyId)
    .where('is_active', '=', true)
    .orderBy('created_at', 'desc')
    .limit(100)
    .execute();
  return rows.map(mapSubscription);
}

export async function deactivateSubscription(
  db: Db,
  apiKeyId: string,
  actor: AuditActor,
  subscriptionId: string,
): Promise<SubscriptionRecord> {
  if (!isUuid(subscriptionId)) {
    throw new InvalidRequestError('subscriptionId must be a UUID.');
  }
  const existing = await db
    .selectFrom('subscriptions')
    .selectAll()
    .where('id', '=', subscriptionId)
    .executeTakeFirst();
  if (!existing) throw new NotFoundError('Subscription not found.');
  if (existing.api_key_id !== apiKeyId)
    throw new ForbiddenError('Subscription belongs to another key.');
  const updated = await db.transaction().execute(async (tx) => {
    const row = await tx
      .updateTable('subscriptions')
      .set({ is_active: false, updated_at: new Date() })
      .where('id', '=', subscriptionId)
      .returningAll()
      .executeTakeFirstOrThrow();
    await recordAuditEventStrict(tx, {
      actor,
      action: AUDIT_ACTIONS.SUBSCRIPTION_DELETE,
      targetType: 'subscription',
      targetId: subscriptionId,
      beforeState: { isActive: existing.is_active },
      afterState: { isActive: false },
      severity: 'medium',
    });
    return row;
  });
  return mapSubscription(updated);
}

export async function enqueueSubscriptionNotifications(
  db: Db,
  input: EnqueueSubscriptionChangeInput,
): Promise<{ enqueued: number; skipped: number }> {
  validateDispatch(input);
  let q = db.selectFrom('subscriptions').selectAll().where('is_active', '=', true);
  if (input.dispatchScope.type === 'api_key') {
    q = q.where('api_key_id', '=', input.dispatchScope.apiKeyId);
  }
  if (input.changeKind === 'topic') q = q.where('topic_id', '=', input.topicId ?? '');
  if (input.changeKind === 'entity') q = q.where('entity_id', '=', input.entityId ?? '');
  if (input.changeKind === 'relationship') {
    q = q.where('relationship_type_id', '=', input.relationshipTypeId ?? '');
  }
  if (input.changeKind === 'claim_pattern') {
    q = q.where('claim_pattern', 'is not', null);
  }
  const rows = await q.limit(500).execute();
  let enqueued = 0;
  let skipped = 0;
  for (const sub of rows) {
    if (
      input.changeKind === 'claim_pattern' &&
      !claimPatternMatches(parseClaimPattern(sub.claim_pattern), input.claimPattern)
    ) {
      skipped += 1;
      continue;
    }
    const targetLabel = await targetLabelForSubscription(db, sub);
    const tokenBudget = clampBudget(sub.token_budget);
    const delta = await buildDelta(db, {
      topic: targetLabel,
      since_date: input.sinceDate,
      until_date: input.untilDate,
      token_budget: tokenBudget,
    });
    const maxImportance = maxDeltaImportance(delta);
    const minImportance = Number(sub.min_importance);
    if (maxImportance < minImportance || delta.summary.citations.length === 0) {
      skipped += 1;
      continue;
    }
    await db
      .insertInto('subscription_notifications')
      .values({
        subscription_id: sub.id,
        api_key_id: sub.api_key_id,
        change_kind: input.changeKind,
        target_label: targetLabel,
        since_date: new Date(input.sinceDate),
        until_date: input.untilDate ? new Date(input.untilDate) : new Date(),
        min_importance: minImportance,
        token_budget: tokenBudget,
        max_importance: maxImportance,
        payload: JSON.stringify(notificationPayload(delta)),
        delivery_method: sub.delivery_method,
        next_attempt_at: sub.delivery_method === 'webhook' ? new Date() : null,
      })
      .execute();
    enqueued += 1;
  }
  return { enqueued, skipped };
}

export async function pollSubscriptionNotifications(
  db: Db,
  input: PollSubscriptionInput,
): Promise<SubscriptionNotificationRecord[]> {
  if (!isUuid(input.subscriptionId)) {
    throw new InvalidRequestError('subscriptionId must be a UUID.');
  }
  const subscription = await db
    .selectFrom('subscriptions')
    .selectAll()
    .where('id', '=', input.subscriptionId)
    .executeTakeFirst();
  if (!subscription) throw new NotFoundError('Subscription not found.');
  if (subscription.api_key_id !== input.apiKeyId) {
    throw new ForbiddenError('Subscription belongs to another key.');
  }
  if (!subscription.is_active) throw new NotFoundError('Subscription not found.');
  const limit = Math.min(MAX_POLL_LIMIT, Math.max(1, input.limit ?? 20));
  const rows = await db
    .selectFrom('subscription_notifications')
    .selectAll()
    .where('subscription_id', '=', input.subscriptionId)
    .where('delivery_method', '=', 'polling')
    .where('status', '=', 'pending')
    .orderBy('created_at', 'asc')
    .limit(limit)
    .execute();
  const now = new Date();
  await db.transaction().execute(async (tx) => {
    if (rows.length > 0) {
      await tx
        .updateTable('subscription_notifications')
        .set({ status: 'delivered', delivered_at: now, updated_at: now })
        .where(
          'id',
          'in',
          rows.map((row) => row.id),
        )
        .execute();
      for (const row of rows) {
        await tx
          .insertInto('subscription_delivery_logs')
          .values({
            notification_id: row.id,
            subscription_id: row.subscription_id,
            delivery_method: 'polling',
            attempt_number: 0,
            status: 'delivered',
          })
          .execute();
      }
    }
    await tx
      .updateTable('subscriptions')
      .set({
        last_checked_at: now,
        last_delivered_at: rows.length > 0 ? now : subscription.last_delivered_at,
        updated_at: now,
      })
      .where('id', '=', input.subscriptionId)
      .execute();
  });
  return rows.map((row) => mapNotification({ ...row, status: 'delivered', delivered_at: now }));
}

function nextAttemptAt(attempt: number, now = new Date()): Date | null {
  if (attempt >= MAX_WEBHOOK_ATTEMPTS) return null;
  const delaySeconds = Math.min(3600, 2 ** Math.max(0, attempt - 1) * 60);
  return new Date(now.getTime() + delaySeconds * 1000);
}

export async function deliverDueWebhookNotifications(
  db: Db,
  port: WebhookDeliveryPort,
  options: { limit?: number; now?: Date } = {},
): Promise<{ delivered: number; failed: number; skipped: number }> {
  const now = options.now ?? new Date();
  const limit = Math.min(100, Math.max(1, options.limit ?? 25));
  const rows = await db
    .selectFrom('subscription_notifications')
    .innerJoin('subscriptions', 'subscriptions.id', 'subscription_notifications.subscription_id')
    .select([
      'subscription_notifications.id as notification_id',
      'subscription_notifications.subscription_id as subscription_id',
      'subscription_notifications.payload as payload',
      'subscription_notifications.attempt_count as attempt_count',
      'subscriptions.webhook_url as webhook_url',
    ])
    .where('subscription_notifications.delivery_method', '=', 'webhook')
    .where('subscription_notifications.status', 'in', ['pending', 'failed'])
    .where('subscriptions.is_active', '=', true)
    .where((eb) =>
      eb.or([
        eb('subscription_notifications.next_attempt_at', 'is', null),
        eb('subscription_notifications.next_attempt_at', '<=', now),
      ]),
    )
    .orderBy('subscription_notifications.created_at', 'asc')
    .limit(limit)
    .execute();

  let delivered = 0;
  let failed = 0;
  let skipped = 0;
  for (const row of rows) {
    if (!row.webhook_url) {
      await db
        .updateTable('subscription_notifications')
        .set({
          status: 'skipped',
          error_code: 'missing_webhook_url',
          error_message: 'Webhook subscription has no URL.',
          updated_at: now,
        })
        .where('id', '=', row.notification_id)
        .execute();
      await db
        .insertInto('subscription_delivery_logs')
        .values({
          notification_id: row.notification_id,
          subscription_id: row.subscription_id,
          delivery_method: 'webhook',
          attempt_number: row.attempt_count,
          status: 'skipped',
          error_code: 'missing_webhook_url',
          error_message: 'Webhook subscription has no URL.',
        })
        .execute();
      skipped += 1;
      continue;
    }

    const attempt = row.attempt_count + 1;
    const result = await port.deliver({
      url: row.webhook_url,
      notificationId: row.notification_id,
      subscriptionId: row.subscription_id,
      payload: typeof row.payload === 'string' ? JSON.parse(row.payload) : row.payload,
    });
    if (result.ok) {
      await db.transaction().execute(async (tx) => {
        await tx
          .updateTable('subscription_notifications')
          .set({
            status: 'delivered',
            attempt_count: attempt,
            last_attempt_at: now,
            delivered_at: now,
            error_code: null,
            error_message: null,
            next_attempt_at: null,
            updated_at: now,
          })
          .where('id', '=', row.notification_id)
          .execute();
        await tx
          .insertInto('subscription_delivery_logs')
          .values({
            notification_id: row.notification_id,
            subscription_id: row.subscription_id,
            delivery_method: 'webhook',
            attempt_number: attempt,
            status: 'delivered',
            http_status: result.status ?? null,
          })
          .execute();
      });
      delivered += 1;
      continue;
    }

    const retryAt = nextAttemptAt(attempt, now);
    const finalFailure = retryAt === null;
    await db.transaction().execute(async (tx) => {
      await tx
        .updateTable('subscription_notifications')
        .set({
          status: finalFailure ? 'failed' : 'pending',
          attempt_count: attempt,
          last_attempt_at: now,
          next_attempt_at: retryAt,
          error_code: result.errorCode ?? 'webhook_delivery_failed',
          error_message: result.errorMessage ?? null,
          updated_at: now,
        })
        .where('id', '=', row.notification_id)
        .execute();
      await tx
        .insertInto('subscription_delivery_logs')
        .values({
          notification_id: row.notification_id,
          subscription_id: row.subscription_id,
          delivery_method: 'webhook',
          attempt_number: attempt,
          status: 'failed',
          http_status: result.status ?? null,
          error_code: result.errorCode ?? 'webhook_delivery_failed',
          error_message: result.errorMessage ?? null,
          next_attempt_at: retryAt,
        })
        .execute();
    });
    failed += 1;
  }

  return { delivered, failed, skipped };
}
