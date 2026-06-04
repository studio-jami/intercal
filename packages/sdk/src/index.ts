/**
 * @intercal/sdk — a thin, typed client over the Intercal REST API.
 * Response and parameter types come from the generated contract (@intercal/shared); the SDK
 * adds no semantics of its own.
 */
import type { components } from '@intercal/shared';

type S = components['schemas'];

export class IntercalApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'IntercalApiError';
  }
}

export interface IntercalClientOptions {
  baseUrl: string;
  fetch?: typeof fetch;
  apiKey?: string;
}

export interface DeltaParams {
  topic: string;
  since_date: string;
  token_budget?: number;
  until_date?: string;
}
export interface EntityParams {
  name_or_id: string;
  at_date?: string;
  token_budget?: number;
}
export interface EvidenceParams {
  query: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
}
export interface VerifyClaimParams {
  claim_text: string;
  as_of_date?: string;
  token_budget?: number;
}
export interface SourcesParams {
  entity_or_claim_id: string;
  limit?: number;
}
export interface FreshnessParams {
  topic_or_entity: string;
}

export class IntercalClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly apiKey: string | undefined;

  constructor(options: IntercalClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this.fetchImpl = options.fetch ?? fetch;
    this.apiKey = options.apiKey;
  }

  private async get<T>(path: string, params: Record<string, unknown>): Promise<T> {
    const url = new URL(this.baseUrl + path);
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
    const headers: Record<string, string> = { accept: 'application/json' };
    if (this.apiKey) headers.authorization = `Bearer ${this.apiKey}`;

    const res = await this.fetchImpl(url, { headers });
    const body = (await res.json()) as unknown;
    if (!res.ok) {
      const e = body as Partial<S['ApiError']>;
      throw new IntercalApiError(
        res.status,
        e.code ?? 'error',
        e.message ?? res.statusText,
        e.details,
      );
    }
    return body as T;
  }

  getDelta(params: DeltaParams): Promise<S['DeltaResponse']> {
    return this.get('/v1/delta', { ...params });
  }
  getEntity(params: EntityParams): Promise<S['EntityResponse']> {
    return this.get('/v1/entity', { ...params });
  }
  searchEvidence(params: EvidenceParams): Promise<S['EvidenceResponse']> {
    return this.get('/v1/evidence', { ...params });
  }
  verifyClaim(params: VerifyClaimParams): Promise<S['ClaimVerificationResponse']> {
    return this.get('/v1/claims/verify', { ...params });
  }
  getSources(params: SourcesParams): Promise<S['SourcesResponse']> {
    return this.get('/v1/sources', { ...params });
  }
  getFreshness(params: FreshnessParams): Promise<S['FreshnessReport']> {
    return this.get('/v1/freshness', { ...params });
  }
}

export type { components as IntercalComponents } from '@intercal/shared';
