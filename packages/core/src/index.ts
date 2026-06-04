/** @intercal/core — shared DB access + the query-service layer used by API and MCP. */

export type { CoreConfig } from './config.js';
export { loadConfig } from './config.js';
export type { Db } from './db/client.js';
export { createDb } from './db/client.js';
export type { Database } from './db/types.js';
export {
  IntercalError,
  InvalidRequestError,
  NotFoundError,
  NotImplementedError,
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
