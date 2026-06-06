/**
 * @intercal/sdk — a thin, fully-typed client over the Intercal V1 REST API.
 *
 * The contract is the single source of truth: every request parameter and response shape is
 * derived from the generated OpenAPI types in `@intercal/shared` (`operations` / `components`).
 * The SDK declares no domain shapes of its own — it only adds transport concerns (URL building,
 * fetch injection, retries) and a typed error model that mirrors the REST error taxonomy.
 *
 * Deferred surface: `getDelta` and `verifyClaim` are real, typed methods, but their server-side
 * bodies are owned by later workstreams (Plan 03 W5/W6). Until those land, the live API answers
 * `501 not_implemented`; the SDK surfaces that as a typed {@link IntercalNotImplementedError}
 * rather than faking a result.
 */
import type { components, operations } from '@intercal/shared';

type Schemas = components['schemas'];

/** Query parameters for an operation, derived from the generated contract. */
type Query<Op extends keyof operations> = operations[Op] extends {
  parameters: { query: infer Q };
}
  ? Q
  : never;

/** The 200 response body for an operation, derived from the generated contract. */
type Ok<Op extends keyof operations> = operations[Op] extends {
  responses: { 200: { content: { 'application/json': infer R } } };
}
  ? R
  : never;

// Public request parameter types — aliases over the generated contract (not redeclarations).
export type DeltaParams = Query<'getDelta'>;
export type EntityParams = Query<'getEntity'>;
export type EvidenceParams = Query<'searchEvidence'>;
export type VerifyClaimParams = Query<'verifyClaim'>;
export type SourcesParams = Query<'getSources'>;
export type FreshnessParams = Query<'getFreshness'>;

// Public response types — aliases over the generated contract.
export type DeltaResponse = Ok<'getDelta'>;
export type EntityResponse = Ok<'getEntity'>;
export type EvidenceResponse = Ok<'searchEvidence'>;
export type ClaimVerificationResponse = Ok<'verifyClaim'>;
export type SourcesResponse = Ok<'getSources'>;
export type FreshnessReport = Ok<'getFreshness'>;

/** The REST error taxonomy, as served in the `ApiError.code` field. */
export type IntercalErrorCode =
  | 'invalid_request'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'rate_limited'
  | 'not_implemented'
  | 'internal_error'
  | 'network_error';

/**
 * Base class for every error the SDK throws. `code` is the discriminant: narrow on it (or use
 * `instanceof` on a subclass) to handle specific failures. `status` is the HTTP status (`0` for a
 * transport failure that never reached the server).
 */
export class IntercalApiError extends Error {
  readonly code: IntercalErrorCode | (string & {});
  readonly status: number;
  readonly details: Schemas['ApiError']['details'];

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Schemas['ApiError']['details'],
  ) {
    super(message);
    this.name = 'IntercalApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/** 400 — query parameters failed contract validation (see `details.issues`). */
export class IntercalInvalidRequestError extends IntercalApiError {
  override readonly code = 'invalid_request';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'invalid_request', message, details);
    this.name = 'IntercalInvalidRequestError';
  }
}

/** 401 — no credential, or the key is invalid/revoked/expired. */
export class IntercalUnauthorizedError extends IntercalApiError {
  override readonly code = 'unauthorized';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'unauthorized', message, details);
    this.name = 'IntercalUnauthorizedError';
  }
}

/** 403 — authenticated, but the key lacks the required scope. */
export class IntercalForbiddenError extends IntercalApiError {
  override readonly code = 'forbidden';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'forbidden', message, details);
    this.name = 'IntercalForbiddenError';
  }
}

/** 404 — no entity/claim/source matched the request. */
export class IntercalNotFoundError extends IntercalApiError {
  override readonly code = 'not_found';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'not_found', message, details);
    this.name = 'IntercalNotFoundError';
  }
}

/** 429 — the caller exceeded its rate-limit policy. `details.retryAfter` is seconds (when present). */
export class IntercalRateLimitedError extends IntercalApiError {
  override readonly code = 'rate_limited';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'rate_limited', message, details);
    this.name = 'IntercalRateLimitedError';
  }
}

/**
 * 501 — the endpoint exists in the contract but its body is deferred to a later workstream
 * (currently `getDelta` and `verifyClaim`). This is an honest seam, not a bug.
 */
export class IntercalNotImplementedError extends IntercalApiError {
  override readonly code = 'not_implemented';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'not_implemented', message, details);
    this.name = 'IntercalNotImplementedError';
  }
}

/** 500 (or any unmapped status) — an unexpected server-side failure. */
export class IntercalServerError extends IntercalApiError {
  override readonly code = 'internal_error';
  constructor(status: number, message: string, details?: Schemas['ApiError']['details']) {
    super(status, 'internal_error', message, details);
    this.name = 'IntercalServerError';
  }
}

/** Transport failure: the request never produced a parseable HTTP response (DNS, TCP, abort). */
export class IntercalNetworkError extends IntercalApiError {
  override readonly code = 'network_error';
  constructor(message: string, cause?: unknown) {
    super(0, 'network_error', message);
    this.name = 'IntercalNetworkError';
    if (cause !== undefined) this.cause = cause;
  }
}

/** Build the typed error for a non-2xx response body. */
function errorFor(status: number, body: Partial<Schemas['ApiError']>): IntercalApiError {
  const code = body.code ?? 'internal_error';
  const message = body.message ?? `Request failed with status ${status}`;
  const details = body.details;
  switch (code) {
    case 'invalid_request':
      return new IntercalInvalidRequestError(status, message, details);
    case 'unauthorized':
      return new IntercalUnauthorizedError(status, message, details);
    case 'forbidden':
      return new IntercalForbiddenError(status, message, details);
    case 'not_found':
      return new IntercalNotFoundError(status, message, details);
    case 'rate_limited':
      return new IntercalRateLimitedError(status, message, details);
    case 'not_implemented':
      return new IntercalNotImplementedError(status, message, details);
    case 'internal_error':
      return new IntercalServerError(status, message, details);
    default:
      return new IntercalApiError(status, code, message, details);
  }
}

export interface IntercalClientOptions {
  /** Base URL of the API, e.g. `https://lntercal.vercel.app/api`. Trailing slash is trimmed. */
  baseUrl: string;
  /** Injectable fetch (for tests / non-global-fetch runtimes). Defaults to the global `fetch`. */
  fetch?: typeof fetch;
  /**
   * Bearer API key. Sent as `Authorization: Bearer …` when set. A valid key raises the rate limit
   * and unlocks scoped surfaces; anonymous (unset) calls are allowed under a tighter per-IP limit.
   */
  apiKey?: string;
  /** Extra headers merged into every request. */
  headers?: Record<string, string>;
  /**
   * Max automatic retries for transient failures (network errors and 5xx). GET-only and safe by
   * construction — the V1 surface is read-only. Defaults to `0` (no retries).
   */
  maxRetries?: number;
  /** Base backoff in ms between retries (doubled each attempt). Defaults to `200`. */
  retryBackoffMs?: number;
}

/** A typed client for the Intercal V1 read surface. One method per contract operation. */
export class IntercalClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly apiKey: string | undefined;
  private readonly extraHeaders: Record<string, string>;
  private readonly maxRetries: number;
  private readonly retryBackoffMs: number;

  constructor(options: IntercalClientOptions) {
    if (!options.baseUrl) throw new Error('IntercalClient requires a baseUrl');
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    const f = options.fetch ?? globalThis.fetch;
    if (typeof f !== 'function') {
      throw new Error('No fetch implementation available; pass options.fetch');
    }
    // Preserve `this` binding for environments where global fetch is unbound.
    this.fetchImpl = f.bind(globalThis);
    this.apiKey = options.apiKey;
    this.extraHeaders = options.headers ?? {};
    this.maxRetries = Math.max(0, options.maxRetries ?? 0);
    this.retryBackoffMs = Math.max(0, options.retryBackoffMs ?? 200);
  }

  // --- V1 operations -------------------------------------------------------

  /**
   * What changed about a topic since a date. Deferred body (Plan 03 W5): the live API currently
   * answers `501`, surfaced here as {@link IntercalNotImplementedError}. `token_budget` is part of
   * the contract signature; the server applies it once the digest body lands.
   */
  getDelta(params: DeltaParams, init?: RequestInit): Promise<DeltaResponse> {
    return this.get<DeltaResponse>('/v1/delta', params, init);
  }

  /** Entity state, relationships, and fact history, optionally at a point in time. */
  getEntity(params: EntityParams, init?: RequestInit): Promise<EntityResponse> {
    return this.get<EntityResponse>('/v1/entity', params, init);
  }

  /** Lexical evidence search by query, date range, and limit. */
  searchEvidence(params: EvidenceParams, init?: RequestInit): Promise<EvidenceResponse> {
    return this.get<EvidenceResponse>('/v1/evidence', params, init);
  }

  /**
   * Verify a free-text claim against recorded evidence. Deferred body (Plan 03 W6): the live API
   * currently answers `501`, surfaced here as {@link IntercalNotImplementedError}.
   */
  verifyClaim(params: VerifyClaimParams, init?: RequestInit): Promise<ClaimVerificationResponse> {
    return this.get<ClaimVerificationResponse>('/v1/claims/verify', params, init);
  }

  /** List the source documents backing an entity or claim (`entity_or_claim_id` must be a UUID). */
  getSources(params: SourcesParams, init?: RequestInit): Promise<SourcesResponse> {
    return this.get<SourcesResponse>('/v1/sources', params, init);
  }

  /** Report how fresh Intercal's knowledge is for a topic or entity. */
  getFreshness(params: FreshnessParams, init?: RequestInit): Promise<FreshnessReport> {
    return this.get<FreshnessReport>('/v1/freshness', params, init);
  }

  // --- internals -----------------------------------------------------------

  private buildUrl(path: string, params: Record<string, unknown>): string {
    const url = new URL(this.baseUrl + path);
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
    return url.toString();
  }

  private async get<T>(
    path: string,
    params: Record<string, unknown>,
    init?: RequestInit,
  ): Promise<T> {
    const url = this.buildUrl(path, params);
    const headers = new Headers(init?.headers);
    headers.set('accept', 'application/json');
    for (const [k, v] of Object.entries(this.extraHeaders)) headers.set(k, v);
    if (this.apiKey) headers.set('authorization', `Bearer ${this.apiKey}`);

    let attempt = 0;
    // attempts = initial try + up to maxRetries retries.
    while (true) {
      let res: Response;
      try {
        res = await this.fetchImpl(url, { ...init, method: 'GET', headers });
      } catch (cause) {
        if (attempt < this.maxRetries) {
          await this.backoff(attempt++);
          continue;
        }
        throw new IntercalNetworkError(
          cause instanceof Error ? cause.message : 'Network request failed',
          cause,
        );
      }

      if (res.ok) {
        return (await res.json()) as T;
      }

      // Retry transient server errors only; client errors (4xx) and 501 are deterministic.
      if (res.status >= 500 && res.status !== 501 && attempt < this.maxRetries) {
        await this.backoff(attempt++);
        continue;
      }

      throw errorFor(res.status, await this.parseError(res));
    }
  }

  private async parseError(res: Response): Promise<Partial<Schemas['ApiError']>> {
    try {
      const body = (await res.json()) as Partial<Schemas['ApiError']>;
      if (body && typeof body === 'object') return body;
    } catch {
      // Non-JSON error body (e.g. an upstream proxy 502). Fall through to a synthetic shape.
    }
    return { code: 'internal_error', message: res.statusText || `HTTP ${res.status}` };
  }

  private backoff(attempt: number): Promise<void> {
    const ms = this.retryBackoffMs * 2 ** attempt;
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// Re-export the generated contract types for consumers that want the raw shapes.
export type {
  components as IntercalComponents,
  operations as IntercalOperations,
} from '@intercal/shared';
