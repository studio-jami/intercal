/**
 * @intercal/shared — the generated contract surface.
 *
 * TypeSpec (`typespec/main.tsp`) is the single source of truth. This module re-exports the
 * generated TypeScript types and provides typed access to the generated OpenAPI document and
 * JSON Schemas (used for MCP tool input schemas and REST request validation).
 *
 * Do not hand-edit `src/generated/*` or `generated/*` — run `pnpm contracts:build`.
 */
import { jsonSchemas, openapiDocument } from './generated/artifacts.gen.js';

// Generated OpenAPI 3.1 path/operation/component types.
export type * from './generated/types.gen.js';

/** The full generated OpenAPI 3.1 document (embedded — no filesystem, edge-safe). */
export function getOpenApiDocument(): Record<string, unknown> {
  return openapiDocument as unknown as Record<string, unknown>;
}

/**
 * Load a generated JSON Schema by its TypeSpec model name (e.g. `"DeltaQuery"`).
 * Backs both MCP tool input schemas and REST request validation.
 */
export function getJsonSchema(modelName: string): Record<string, unknown> {
  const schema = jsonSchemas[modelName];
  if (!schema) throw new Error(`Unknown contract schema: ${modelName}`);
  return schema;
}

/** All generated JSON Schemas keyed by TypeSpec model name. */
export function getJsonSchemas(): Record<string, Record<string, unknown>> {
  return jsonSchemas;
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
