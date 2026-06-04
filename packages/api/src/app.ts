import {
  type Db,
  getDelta,
  getEntity,
  getFreshness,
  getSources,
  IntercalError,
  searchEvidence,
  verifyClaim,
} from '@intercal/core';
import { getOpenApiDocument } from '@intercal/shared';
import { type Context, Hono } from 'hono';
import { formatErrors, validatorFor } from './validation.js';

const STATUS: Record<string, number> = {
  invalid_request: 400,
  not_found: 404,
  not_implemented: 501,
};

function errorBody(code: string, message: string, details?: Record<string, unknown>) {
  return { code, message, ...(details ? { details } : {}) };
}

/** Build a query-param-validated GET handler bound to a core query function. */
function route<P>(db: Db, inputModel: string, fn: (db: Db, params: P) => Promise<unknown>) {
  const validate = validatorFor(inputModel);
  return async (c: Context): Promise<Response> => {
    const params: Record<string, unknown> = { ...c.req.query() };
    if (!validate(params)) {
      return c.json(
        errorBody('invalid_request', 'Invalid query parameters', formatErrors(validate)),
        400,
      );
    }
    try {
      const result = await fn(db, params as P);
      return c.json(result as Record<string, unknown>, 200);
    } catch (err) {
      if (err instanceof IntercalError) {
        return c.json(
          errorBody(err.code, err.message, err.details),
          (STATUS[err.code] ?? 500) as 500,
        );
      }
      const message = err instanceof Error ? err.message : 'Unknown error';
      return c.json(errorBody('internal_error', message), 500);
    }
  };
}

export function createApp(db: Db): Hono {
  const app = new Hono();

  app.get('/health', (c) => c.json({ status: 'ok' }));
  app.get('/openapi.json', (c) => c.json(getOpenApiDocument()));

  app.get('/v1/delta', route(db, 'DeltaQuery', getDelta));
  app.get('/v1/entity', route(db, 'EntityQuery', getEntity));
  app.get('/v1/evidence', route(db, 'EvidenceQuery', searchEvidence));
  app.get('/v1/claims/verify', route(db, 'VerifyClaimQuery', verifyClaim));
  app.get('/v1/sources', route(db, 'SourcesQuery', getSources));
  app.get('/v1/freshness', route(db, 'FreshnessQuery', getFreshness));

  return app;
}
