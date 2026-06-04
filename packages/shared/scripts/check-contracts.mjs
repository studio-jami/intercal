#!/usr/bin/env node
// Drift check: regenerate contracts and fail if the committed artifacts differ from source.
// Run after editing typespec/main.tsp — keeps generated TS/OpenAPI/JSON-Schema/Pydantic honest.

import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = resolve(here, '..');
const repoRoot = resolve(pkgRoot, '..', '..');

// 1) Regenerate from source.
const build = spawnSync('node', ['scripts/build-contracts.mjs'], {
  stdio: 'inherit',
  shell: true,
  cwd: pkgRoot,
});
if ((build.status ?? 1) !== 0) {
  console.error('[contracts:check] build failed.');
  process.exit(1);
}

// 2) Compare committed artifacts against the freshly generated ones.
const paths = [
  'packages/shared/generated',
  'packages/shared/src/generated',
  'services/shared/src/intercal_shared/contracts/models.py',
];
const diff = spawnSync('git', ['diff', '--stat', '--', ...paths], {
  encoding: 'utf8',
  cwd: repoRoot,
});
const out = (diff.stdout ?? '').trim();
if (out) {
  console.error('\n[contracts:check] DRIFT DETECTED — generated artifacts are out of date:');
  console.error(out);
  console.error('\nRun `pnpm contracts:build` and commit the regenerated files.');
  process.exit(1);
}
console.log('[contracts:check] no drift — generated artifacts match the TypeSpec source.');
