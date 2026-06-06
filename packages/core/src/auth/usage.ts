/**
 * Usage-event recording. One row per request into `usage_events` for Plan 04 W6 observability to
 * consume later. No PII beyond the key id — `ip_address` is anonymized at the boundary before it
 * reaches here (see the API middleware), and we never store the raw key or any header secret.
 *
 * Recording is best-effort: a failure to write a usage row must NEVER fail the underlying request.
 */
import type { Db } from '../db/client.js';

export interface UsageEvent {
  /** The authenticated key id, or null for anonymous calls. */
  apiKeyId: string | null;
  /** REST endpoint or MCP tool name, e.g. 'GET /v1/entity'. */
  toolName: string;
  requestId?: string | null;
  statusCode?: number | null;
  latencyMs?: number | null;
  errorCode?: string | null;
  tokenBudget?: number | null;
  tokensUsed?: number | null;
  entityCount?: number | null;
  claimCount?: number | null;
  documentCount?: number | null;
  /** Already-anonymized caller context (e.g. a truncated/hashed IP), or null. */
  ipAddress?: string | null;
  userAgent?: string | null;
}

/**
 * Insert a usage event. Returns a promise that resolves on success and swallows errors (logged by
 * the caller if desired) so observability recording can never break a served request.
 */
export async function recordUsageEvent(db: Db, event: UsageEvent): Promise<void> {
  try {
    await db
      .insertInto('usage_events')
      .values({
        api_key_id: event.apiKeyId,
        tool_name: event.toolName,
        request_id: event.requestId ?? null,
        status_code: event.statusCode ?? null,
        latency_ms: event.latencyMs ?? null,
        error_code: event.errorCode ?? null,
        token_budget: event.tokenBudget ?? null,
        tokens_used: event.tokensUsed ?? null,
        entity_count: event.entityCount ?? null,
        claim_count: event.claimCount ?? null,
        document_count: event.documentCount ?? null,
        ip_address: event.ipAddress ?? null,
        user_agent: event.userAgent ?? null,
      })
      .execute();
  } catch {
    // Best-effort: never let observability writes break the request path.
  }
}
