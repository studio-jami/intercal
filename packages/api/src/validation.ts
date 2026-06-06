import { createRequire } from 'node:module';
import { getJsonSchema, getJsonSchemas } from '@intercal/shared';
import type { ValidateFunction } from 'ajv';

// ajv and ajv-formats are CJS; load them via createRequire so the constructor/callable
// interop is unambiguous across module settings.
const require = createRequire(import.meta.url);
const ajvMod = require('ajv/dist/2020.js');
const Ajv2020 = (ajvMod.default ?? ajvMod) as typeof import('ajv/dist/2020.js').default;
const addFormatsMod = require('ajv-formats');
const addFormats = (addFormatsMod.default ?? addFormatsMod) as typeof import('ajv-formats').default;

// One Ajv instance; query strings are coerced to the schema's scalar types. `strict: false`
// tolerates the extra annotation keywords the TypeSpec JSON-Schema emitter produces.
// `removeAdditional: false` + an injected `additionalProperties: false` (see below) makes
// unknown query params a hard 400 rather than silently forwarding them to the query layer.
const ajv = new Ajv2020({ coerceTypes: true, strict: false, allErrors: true, useDefaults: true });
addFormats(ajv);

const cache = new Map<string, ValidateFunction>();
let registeredSchemas = false;

function registerGeneratedSchemas(): void {
  if (registeredSchemas) return;
  for (const schema of Object.values(getJsonSchemas())) {
    const id = typeof schema.$id === 'string' ? schema.$id : undefined;
    if (id && !ajv.getSchema(id)) ajv.addSchema(schema, id);
  }
  registeredSchemas = true;
}

/**
 * Compile (and cache) a validator for a generated JSON-Schema query model, e.g. "DeltaQuery".
 *
 * The generated schema is the single contract source and is never mutated. We compile against a
 * shallow clone with `additionalProperties: false` injected so query params outside the contract
 * are rejected — the contract enumerates the exact params for each operation, so anything else is
 * an invalid request, not a silently-ignored extra.
 */
export function validatorFor(modelName: string): ValidateFunction {
  const cached = cache.get(modelName);
  if (cached) return cached;
  registerGeneratedSchemas();
  const schema = getJsonSchema(modelName);
  // Clone (do not mutate the shared generated artifact) and drop `$id`: Ajv would otherwise
  // register the same id twice across the two compile paths and throw.
  const { $id: _id, ...rest } = schema;
  const strictSchema = { ...rest, additionalProperties: false };
  const validate = ajv.compile(strictSchema);
  cache.set(modelName, validate);
  return validate;
}

export function bodyValidatorFor(modelName: string): ValidateFunction {
  const cacheKey = `body:${modelName}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;
  registerGeneratedSchemas();
  const { $id: _id, ...rest } = getJsonSchema(modelName);
  const strictSchema = { ...rest, additionalProperties: false };
  const validate = ajv.compile(strictSchema);
  cache.set(cacheKey, validate);
  return validate;
}

export function formatErrors(validate: ValidateFunction): Record<string, unknown> {
  return {
    issues: (validate.errors ?? []).map((e) => ({
      path: e.instancePath || e.schemaPath,
      message:
        e.keyword === 'additionalProperties' && e.params && 'additionalProperty' in e.params
          ? `unknown query parameter: ${(e.params as { additionalProperty: string }).additionalProperty}`
          : (e.message ?? 'invalid'),
    })),
  };
}
