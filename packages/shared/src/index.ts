/**
 * @intercal/shared — the generated contract surface.
 *
 * TypeSpec (`typespec/main.tsp`) is the single source of truth. This module re-exports the
 * generated TypeScript types and provides typed access to the generated OpenAPI document and
 * JSON Schemas (used for MCP tool input schemas and REST request validation).
 *
 * Do not hand-edit `src/generated/*` or `generated/*` — run `pnpm contracts:build`.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// Generated OpenAPI 3.1 path/operation/component types.
export type * from './generated/types.gen.js';

/** Directory holding generated data artifacts (relative to the compiled module). */
const generatedDir = new URL('../generated/', import.meta.url);

function readJson(relativePath: string): unknown {
  const url = new URL(relativePath, generatedDir);
  return JSON.parse(readFileSync(fileURLToPath(url), 'utf8'));
}

/** The full generated OpenAPI 3.1 document. */
export function getOpenApiDocument(): Record<string, unknown> {
  return readJson('openapi/openapi.json') as Record<string, unknown>;
}

/**
 * Load a generated JSON Schema by its TypeSpec model name (e.g. `"DeltaQuery"`).
 * The JSON Schema emitter writes one file per model under `generated/json-schema/`.
 */
export function getJsonSchema(modelName: string): Record<string, unknown> {
  return readJson(`json-schema/${modelName}.json`) as Record<string, unknown>;
}

/**
 * The V1 agent-facing tool surface. Hand-authored, stable metadata that binds each MCP tool
 * to its REST route and its generated JSON-Schema input model. Response shapes come from the
 * generated OpenAPI types. Keep in sync with `typespec/main.tsp`.
 */
export const V1_TOOLS = [
  {
    name: 'get_delta',
    route: '/v1/delta',
    inputSchema: 'DeltaQuery',
    description:
      'What changed about a topic since a date, with evidence, confidence, and a token-budgeted summary.',
  },
  {
    name: 'get_entity',
    route: '/v1/entity',
    inputSchema: 'EntityQuery',
    description: 'Entity state, relationships, and fact history, optionally at a point in time.',
  },
  {
    name: 'search_evidence',
    route: '/v1/evidence',
    inputSchema: 'EvidenceQuery',
    description: 'Search source-grounded evidence by query, date range, and sources.',
  },
  {
    name: 'verify_claim',
    route: '/v1/claims/verify',
    inputSchema: 'VerifyClaimQuery',
    description: 'Verify a claim against recorded evidence as of a date.',
  },
  {
    name: 'get_sources',
    route: '/v1/sources',
    inputSchema: 'SourcesQuery',
    description: 'List the source documents backing an entity or claim.',
  },
  {
    name: 'get_freshness',
    route: '/v1/freshness',
    inputSchema: 'FreshnessQuery',
    description: "Report how fresh Intercal's knowledge is for a topic or entity.",
  },
] as const;

export type V1ToolName = (typeof V1_TOOLS)[number]['name'];
