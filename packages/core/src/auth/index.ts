/** Auth: API-key primitives, server-side verification, operator lifecycle, and usage recording. */

export type { IssuedKey, IssueKeyInput, KeySummary } from './admin.js';
export { issueApiKey, listApiKeys, revokeApiKey } from './admin.js';
export type { GeneratedKey } from './keys.js';
export { generateApiKey, hashApiKey, hashesEqual, KEY_PREFIX, parseBearer } from './keys.js';
export type { Scope } from './scopes.js';
export { hasScope, READ_SCOPE, SCOPES } from './scopes.js';
export type { UsageEvent } from './usage.js';
export { recordUsageEvent } from './usage.js';
export type { AuthenticatedKey } from './verify.js';
export { authenticateHeader, authenticateKey } from './verify.js';
