import { createRequire } from 'node:module';
import { getJsonSchema } from '@intercal/shared';
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
const ajv = new Ajv2020({ coerceTypes: true, strict: false, allErrors: true, useDefaults: true });
addFormats(ajv);

const cache = new Map<string, ValidateFunction>();

/** Compile (and cache) a validator for a generated JSON-Schema model, e.g. "DeltaQuery". */
export function validatorFor(modelName: string): ValidateFunction {
  const cached = cache.get(modelName);
  if (cached) return cached;
  const schema = getJsonSchema(modelName) as Record<string, unknown>;
  const validate = ajv.compile(schema);
  cache.set(modelName, validate);
  return validate;
}

export function formatErrors(validate: ValidateFunction): Record<string, unknown> {
  return {
    issues: (validate.errors ?? []).map((e) => ({
      path: e.instancePath || e.schemaPath,
      message: e.message ?? 'invalid',
    })),
  };
}
