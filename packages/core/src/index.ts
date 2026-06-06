/** @intercal/core — shared DB access + the query-service layer used by API and MCP. */

// Auth: key primitives, verification, operator lifecycle, usage recording, scopes.
export type {
  AuthenticatedKey,
  GeneratedKey,
  IssuedKey,
  IssueKeyInput,
  KeySummary,
  Scope,
  UsageEvent,
} from './auth/index.js';
export {
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
  READ_SCOPE,
  recordUsageEvent,
  revokeApiKey,
  SCOPES,
} from './auth/index.js';
export type { CoreConfig } from './config.js';
export { loadConfig } from './config.js';
export type { Db } from './db/client.js';
export { createDb } from './db/client.js';
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
  EntityParams,
  EvidenceParams,
  FreshnessParams,
  SourcesParams,
  VerifyClaimParams,
} from './queries.js';
export {
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
