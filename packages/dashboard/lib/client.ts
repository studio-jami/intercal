import { IntercalClient } from '@intercal/sdk';

/** Server-side API client. The dashboard reads through the same contract agents use. */
export function apiClient(): IntercalClient {
  return new IntercalClient({
    baseUrl: process.env.PUBLIC_API_BASE_URL ?? 'http://localhost:8787',
  });
}
