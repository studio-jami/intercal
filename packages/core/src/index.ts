/** @intercal/core — shared DB access + the query-service layer used by API and MCP. */

// Auth: key primitives, verification, operator lifecycle, usage recording, scopes.
export type {
  AuditAction,
  AuditActor,
  AuditActorType,
  AuditEventInput,
  AuditEventRecord,
  AuditSeverity,
  AuthenticatedKey,
  GeneratedKey,
  IssuedKey,
  IssueKeyInput,
  KeySummary,
  QueryAuditEventsFilter,
  Scope,
  UsageEvent,
} from './auth/index.js';
export {
  AUDIT_ACTIONS,
  authenticateHeader,
  authenticateKey,
  generateApiKey,
  hashApiKey,
  hashesEqual,
  hasScope,
  issueApiKey,
  KEY_PREFIX,
  listApiKeys,
  parseBearer,
  queryAuditEvents,
  READ_SCOPE,
  recordAuditEvent,
  recordAuditEventStrict,
  recordUsageEvent,
  revokeApiKey,
  SCOPES,
} from './auth/index.js';
export type { CoreConfig } from './config.js';
export { loadConfig } from './config.js';
export type { Db } from './db/client.js';
export { createDb, sql } from './db/client.js';
export type { Database } from './db/types.js';
export {
  ForbiddenError,
  IntercalError,
  InvalidRequestError,
  NotFoundError,
  NotImplementedError,
  RateLimitedError,
  UnauthorizedError,
} from './errors.js';
export type {
  DeltaParams,
  DocumentPolicy,
  EntityParams,
  EvidenceParams,
  FreshnessParams,
  SourcesParams,
  VerifyClaimParams,
} from './queries.js';
export {
  bodySnippetAllowed,
  getDelta,
  getEntity,
  getFreshness,
  getSources,
  searchEvidence,
  verifyClaim,
} from './queries.js';
// Rate-limit store: provider-agnostic port + Upstash/in-memory adapters.
export type { RateLimitResult, RateLimitStorePort } from './ratelimit/index.js';
export {
  createRateLimitStore,
  MemoryRateLimitStore,
  UpstashRateLimitStore,
} from './ratelimit/index.js';
export type {
  FeedbackConcernType,
  FeedbackResponse,
  FeedbackTargetType,
  ReviewRecord,
  ReviewStatus,
  SubmitFeedbackContext,
  SubmitFeedbackParams,
} from './review.js';
export { submitFeedback } from './review.js';
export type {
  CreateSubscriptionInput,
  EnqueueSubscriptionChangeInput,
  PollSubscriptionInput,
  SubscriptionDeliveryMethod,
  SubscriptionNotificationRecord,
  SubscriptionRecord,
  SubscriptionTargetKind,
  WebhookDeliveryPort,
  WebhookDeliveryRequest,
  WebhookDeliveryResult,
} from './subscriptions.js';
export {
  createSubscription,
  deactivateSubscription,
  deliverDueWebhookNotifications,
  enqueueSubscriptionNotifications,
  listSubscriptions,
  pollSubscriptionNotifications,
} from './subscriptions.js';
