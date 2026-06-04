#!/usr/bin/env node
// Compile the TypeSpec contract to OpenAPI 3.1 + JSON Schema, then generate TS types and
// (if uv is available) Pydantic v2 models. TypeSpec is the single source; everything else
// is generated and must not be hand-edited.

import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = resolve(here, '..');
const repoRoot = resolve(pkgRoot, '..', '..');

function run(cmd, args, opts = {}) {
  const printable = `${cmd} ${args.join(' ')}`;
  console.log(`\n$ ${printable}`);
  const r = spawnSync(cmd, args, { stdio: 'inherit', shell: true, cwd: pkgRoot, ...opts });
  return r.status ?? 1;
}

// 1) TypeSpec -> OpenAPI 3.1 + JSON Schema (emitters configured in tspconfig.yaml)
if (run('pnpm', ['exec', 'tsp', 'compile', 'typespec/main.tsp']) !== 0) {
  console.error('[contracts] TypeSpec compile failed.');
  process.exit(1);
}

const openapiJson = join(pkgRoot, 'generated', 'openapi', 'openapi.json');
if (!existsSync(openapiJson)) {
  console.error(`[contracts] expected ${openapiJson} after compile — not found.`);
  process.exit(1);
}

// 2) OpenAPI -> TypeScript types (committed under src so tsc compiles them)
mkdirSync(join(pkgRoot, 'src', 'generated'), { recursive: true });
if (
  run('pnpm', [
    'exec',
    'openapi-typescript',
    'generated/openapi/openapi.json',
    '-o',
    'src/generated/types.gen.ts',
  ]) !== 0
) {
  console.error('[contracts] openapi-typescript failed.');
  process.exit(1);
}

// 3) OpenAPI -> Pydantic v2 (optional; needs uv. TS-only contributors can skip.)
const pyOut = join(
  repoRoot,
  'services',
  'shared',
  'src',
  'intercal_shared',
  'contracts',
  'models.py',
);
if (existsSync(dirname(pyOut))) {
  const code = run(
    'uv',
    [
      'run',
      '--with',
      'datamodel-code-generator',
      'datamodel-codegen',
      '--input',
      'packages/shared/generated/openapi/openapi.json',
      '--input-file-type',
      'openapi',
      '--output',
      'services/shared/src/intercal_shared/contracts/models.py',
      '--output-model-type',
      'pydantic_v2.BaseModel',
      '--target-python-version',
      '3.12',
      '--use-standard-collections',
      '--use-union-operator',
    ],
    { cwd: repoRoot },
  );
  if (code !== 0) {
    console.warn(
      '[contracts] Pydantic generation skipped/failed (is uv installed? run `uv sync`). ' +
        'TypeScript contracts are still up to date.',
    );
  } else {
    console.log('[contracts] Pydantic models generated.');
  }
} else {
  console.warn('[contracts] services/shared not present yet — skipping Pydantic generation.');
}

console.log('\n[contracts] build complete.');
