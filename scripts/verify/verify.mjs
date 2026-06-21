#!/usr/bin/env node
// Full local verification gate for Intercal.
// Runs the TypeScript, contracts, Python, and database checks and prints a summary.
// Steps marked `optional` are skipped (not failed) when their surface is unavailable
// (e.g. the DB check when Docker/Postgres isn't running) — they exit with code 2 or 3.

import { spawnSync } from 'node:child_process';

const steps = [
  { name: 'biome lint/format', cmd: 'pnpm lint' },
  { name: 'public docs', cmd: 'pnpm docs:check' },
  { name: 'contracts build', cmd: 'pnpm contracts:build' },
  { name: 'shared build', cmd: 'pnpm --filter @intercal/shared build' },
  { name: 'core build', cmd: 'pnpm --filter @intercal/core build' },
  { name: 'sdk build', cmd: 'pnpm --filter @intercal/sdk build' },
  { name: 'ts typecheck', cmd: 'pnpm typecheck' },
  { name: 'contracts drift', cmd: 'pnpm contracts:check' },
  { name: 'ts tests', cmd: 'pnpm test' },
  { name: 'ts build', cmd: 'pnpm build' },
  { name: 'ruff lint', cmd: 'pnpm py:lint' },
  { name: 'pyright', cmd: 'pnpm py:typecheck' },
  { name: 'pytest', cmd: 'pnpm py:test' },
  { name: 'db schema check', cmd: 'pnpm db:check', optional: true, skipCodes: [2, 3] },
];

const results = [];
for (const step of steps) {
  console.log(`\n=== ${step.name} → ${step.cmd} ===`);
  const r = spawnSync(step.cmd, { stdio: 'inherit', shell: true });
  const code = r.status ?? 1;
  let status = code === 0 ? 'pass' : 'fail';
  if (code !== 0 && step.optional && step.skipCodes?.includes(code)) status = 'skip';
  results.push({ name: step.name, status, code });
}

console.log('\n──────── verify summary ────────');
for (const r of results) {
  const mark = r.status === 'pass' ? '✓' : r.status === 'skip' ? '∼' : '✗';
  console.log(
    `  ${mark} ${r.name}${r.status === 'skip' ? ' (skipped — surface unavailable)' : ''}`,
  );
}

const failed = results.filter((r) => r.status === 'fail');
if (failed.length > 0) {
  console.error(`\nverify FAILED: ${failed.map((r) => r.name).join(', ')}`);
  process.exit(1);
}
console.log('\nverify OK');
