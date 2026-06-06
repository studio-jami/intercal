import {
  type AuthenticatedKey,
  createRateLimitStore,
  createSubscription,
  type Db,
  deactivateSubscription,
  enqueueSubscriptionNotifications,
  getDelta,
  getEntity,
  getFreshness,
  getSources,
  IntercalError,
  InvalidRequestError,
  listSubscriptions,
  pollSubscriptionNotifications,
  type RateLimitStorePort,
  type SubmitFeedbackParams,
  searchEvidence,
  submitFeedback,
  verifyClaim,
} from '@intercal/core';
import { getOpenApiDocument } from '@intercal/shared';
import { type Context, Hono } from 'hono';
import { cors } from 'hono/cors';
import { authMiddleware } from './auth/middleware.js';
import { ANON_PER_MINUTE, KEYED_PER_MINUTE_DEFAULT, RATE_WINDOW_SECONDS } from './auth/policy.js';
import { bodyValidatorFor, formatErrors, validatorFor } from './validation.js';

/** Error code → HTTP status. Unmapped codes fall back to 500 (see `statusFor`). */
const STATUS: Record<string, number> = {
  invalid_request: 400,
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  rate_limited: 429,
  not_implemented: 501,
  internal_error: 500,
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function errorBody(code: string, message: string, details?: Record<string, unknown>) {
  return { code, message, ...(details ? { details } : {}) };
}

function statusFor(code: string): number {
  return STATUS[code] ?? 500;
}

function authenticatedKey(c: Context): AuthenticatedKey | null {
  return (c.get as unknown as (key: string) => AuthenticatedKey | null)('apiKey') ?? null;
}

/**
 * A per-route validation guard that runs after the contract schema passes but before the query
 * layer is called. Throw an `IntercalError` (e.g. `InvalidRequestError`) to short-circuit with a
 * mapped status; the central error handler renders it. Used where the contract type is broader
 * than what the read layer can accept (e.g. a generic-string id that must be a UUID at the DB).
 */
type Guard = (params: Record<string, unknown>) => void;

/** Build a query-param-validated GET handler bound to a core query function. */
function route<P>(
  db: Db,
  inputModel: string,
  fn: (db: Db, params: P) => Promise<unknown>,
  guard?: Guard,
) {
  const validate = validatorFor(inputModel);
  return async (c: Context): Promise<Response> => {
    const params: Record<string, unknown> = { ...c.req.query() };
    if (!validate(params)) {
      return c.json(
        errorBody('invalid_request', 'Invalid query parameters', formatErrors(validate)),
        400,
      );
    }
    guard?.(params);
    const result = await fn(db, params as P);
    return c.json(result as Record<string, unknown>, 200);
  };
}

function postJsonRoute<P>(
  db: Db,
  inputModel: string,
  fn: (db: Db, params: P, c: Context) => Promise<unknown>,
) {
  const validate = bodyValidatorFor(inputModel);
  return async (c: Context): Promise<Response> => {
    let body: unknown;
    try {
      body = await c.req.json();
    } catch {
      return c.json(errorBody('invalid_request', 'Invalid JSON request body'), 400);
    }
    if (!validate(body)) {
      return c.json(
        errorBody('invalid_request', 'Invalid request body', formatErrors(validate)),
        400,
      );
    }
    const result = await fn(db, body as P, c);
    return c.json(result as Record<string, unknown>, 200);
  };
}

/**
 * `entity_or_claim_id` must be a UUID: the core query uses it as a Postgres UUID column value.
 * The contract declares it as a generic `string` (no `format: uuid` — the TypeSpec parameter is a
 * generic ID), so Ajv does not enforce this. A non-UUID would otherwise reach the DB and surface
 * as a 500 ("invalid input syntax for type uuid"); guard at the REST boundary with a clear 400.
 */
const sourcesGuard: Guard = (params) => {
  const id = params.entity_or_claim_id as string;
  if (!UUID_RE.test(id)) {
    throw new InvalidRequestError('entity_or_claim_id must be a UUID (entity ID or claim ID)');
  }
};

export interface CreateAppOptions {
  /**
   * Rate-limit counter store (port). Defaults to `createRateLimitStore()` which selects Upstash
   * REST when its credentials are set, else an in-process fallback. Inject a store in tests.
   */
  rateLimitStore?: RateLimitStorePort;
  /** Override the anonymous per-minute limit (tests / self-host tuning). */
  anonPerMinute?: number;
  /** Override the default keyed per-minute limit. */
  keyedPerMinuteDefault?: number;
}

export function createApp(db: Db, options: CreateAppOptions = {}): Hono {
  const app = new Hono();
  const store = options.rateLimitStore ?? createRateLimitStore();
  const anonPerMinute = options.anonPerMinute ?? ANON_PER_MINUTE;
  const keyedPerMinuteDefault = options.keyedPerMinuteDefault ?? KEYED_PER_MINUTE_DEFAULT;

  // Central error taxonomy: every thrown error becomes a JSON ApiError with a mapped status,
  // so the surface never leaks a stack trace or Hono's default text/plain 500. Route handlers
  // therefore throw instead of catching — one error path for both the query layer and guards.
  app.onError((err, c) => {
    if (err instanceof IntercalError) {
      return c.json(errorBody(err.code, err.message, err.details), statusFor(err.code) as 500);
    }
    const message = err instanceof Error ? err.message : 'Unknown error';
    return c.json(errorBody('internal_error', message), 500);
  });

  // The V1 surface is agent-facing and read-only; allow cross-origin GETs so browser-based
  // SDK/agent clients can call it directly. The `Authorization` header is allowlisted so keyed
  // browser clients can raise their rate limit, and the rate-limit headers are exposed to JS.
  app.use(
    '/v1/*',
    cors({
      origin: '*',
      allowMethods: ['GET', 'POST', 'OPTIONS'],
      allowHeaders: ['Authorization', 'Content-Type'],
      exposeHeaders: [
        'RateLimit-Limit',
        'RateLimit-Remaining',
        'RateLimit-Reset',
        'X-RateLimit-Limit',
        'X-RateLimit-Remaining',
        'X-RateLimit-Reset',
        'Retry-After',
      ],
    }),
  );

  // Auth + rate-limit + usage recording on the contract surface only (infra routes stay open and
  // unmetered). Public-read posture: anonymous reads are allowed under a tight per-IP limit; a valid
  // key raises the limit and unlocks scoped surfaces. See `auth/policy.ts`.
  app.use(
    '/v1/*',
    authMiddleware({
      db,
      store,
      anonPerMinute,
      keyedPerMinuteDefault,
      windowSeconds: RATE_WINDOW_SECONDS,
    }),
  );

  app.get('/health', (c) => c.json({ status: 'ok' }));
  app.get('/openapi.json', (c) => c.json(getOpenApiDocument()));

  app.get('/v1/delta', route(db, 'DeltaQuery', getDelta));
  app.get('/v1/entity', route(db, 'EntityQuery', getEntity));
  app.get('/v1/evidence', route(db, 'EvidenceQuery', searchEvidence));
  app.get('/v1/claims/verify', route(db, 'VerifyClaimQuery', verifyClaim));
  app.get('/v1/sources', route(db, 'SourcesQuery', getSources, sourcesGuard));
  app.get('/v1/freshness', route(db, 'FreshnessQuery', getFreshness));
  app.post(
    '/v1/feedback',
    postJsonRoute<SubmitFeedbackParams>(db, 'FeedbackRequest', async (database, params, c) => {
      const principal = authenticatedKey(c);
      return submitFeedback(database, params, {
        actor: principal
          ? { type: 'api_key', id: principal.id }
          : { type: 'human', id: 'anonymous' },
        reporter: principal ? { type: 'api_key', id: principal.id } : { type: 'anonymous' },
        requestId: c.req.header('x-request-id') ?? null,
      });
    }),
  );
  app.get('/v1/subscriptions', async (c) => {
    const principal = authenticatedKey(c);
    if (!principal) throw new InvalidRequestError('Subscription management requires an API key.');
    return c.json({ subscriptions: await listSubscriptions(db, principal.id) }, 200);
  });
  app.post(
    '/v1/subscriptions',
    postJsonRoute(db, 'CreateSubscriptionRequest', async (database, params, c) => {
      const principal = authenticatedKey(c);
      if (!principal) throw new InvalidRequestError('Subscription management requires an API key.');
      const body = params as {
        target: {
          kind: 'topic' | 'entity' | 'relationship' | 'claim_pattern';
          topicId?: string;
          entityId?: string;
          relationshipTypeId?: string;
          claimPattern?: Record<string, unknown>;
        };
        deliveryMethod: 'polling' | 'webhook';
        webhookUrl?: string;
        webhookSecret?: string;
        minImportance?: number;
        tokenBudget?: number;
        metadata?: Record<string, unknown>;
      };
      const subscription = await createSubscription(database, {
        apiKeyId: principal.id,
        actor: { type: 'api_key', id: principal.id },
        target: body.target,
        deliveryMethod: body.deliveryMethod,
        webhookUrl: body.webhookUrl,
        webhookSecret: body.webhookSecret,
        minImportance: body.minImportance,
        tokenBudget: body.tokenBudget,
        metadata: body.metadata,
      });
      return { subscription };
    }),
  );
  app.post(
    '/v1/subscriptions/poll',
    postJsonRoute(db, 'PollSubscriptionRequest', async (database, params, c) => {
      const principal = authenticatedKey(c);
      if (!principal) throw new InvalidRequestError('Subscription polling requires an API key.');
      const body = params as { subscriptionId: string; limit?: number };
      return {
        notifications: await pollSubscriptionNotifications(database, {
          apiKeyId: principal.id,
          subscriptionId: body.subscriptionId,
          limit: body.limit,
        }),
      };
    }),
  );
  app.post(
    '/v1/subscriptions/dispatch',
    postJsonRoute(db, 'DispatchSubscriptionRequest', async (database, params, c) => {
      const principal = authenticatedKey(c);
      if (!principal) throw new InvalidRequestError('Subscription dispatch requires an API key.');
      const body = params as {
        changeKind: 'topic' | 'entity' | 'relationship' | 'claim_pattern';
        topicId?: string;
        entityId?: string;
        relationshipTypeId?: string;
        claimPattern?: Record<string, unknown>;
        sinceDate: string;
        untilDate?: string;
      };
      return enqueueSubscriptionNotifications(database, {
        actor: { type: 'api_key', id: principal.id },
        ...body,
      });
    }),
  );
  app.post(
    '/v1/subscriptions/delete',
    postJsonRoute(db, 'DeleteSubscriptionRequest', async (database, params, c) => {
      const principal = authenticatedKey(c);
      if (!principal) throw new InvalidRequestError('Subscription deletion requires an API key.');
      const body = params as { subscriptionId: string };
      return {
        subscription: await deactivateSubscription(
          database,
          principal.id,
          {
            type: 'api_key',
            id: principal.id,
          },
          body.subscriptionId,
        ),
      };
    }),
  );

  // Unknown route on the contract surface (`/v1/*`) → JSON ApiError 404. This is a real matched
  // route, not `app.notFound`, on purpose: in production the dashboard mounts this app under a
  // prefix via `new Hono().route('/api', createApp(db))`, and Hono lets the PARENT own the
  // `notFound` fallback — so a sub-app's `notFound` never fires for unmatched `/api/v1/*` and the
  // surface would leak Hono's default text/plain `404 Not Found`. A scoped wildcard fires
  // regardless of mount depth. It is deliberately limited to `/v1/*` so it can never intercept a
  // sibling surface mounted under the same prefix (e.g. the MCP server at `/api/mcp`).
  app.all('/v1/*', (c) => c.json(errorBody('not_found', 'Route not found'), 404));

  // When the app is the top-level router (local `server.ts`, tests), `notFound` still renders a
  // JSON ApiError for any unmatched path instead of Hono's default text/plain 404.
  app.notFound((c) => c.json(errorBody('not_found', 'Route not found'), 404));

  return app;
}
