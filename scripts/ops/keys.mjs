#!/usr/bin/env node
// Operator API-key admin CLI (Plan 07 W5).
//
// Issues, revokes, and lists hashed scoped API keys for the REST surface. Thin wrapper over the
// audited lifecycle in @intercal/core (generateApiKey / issueApiKey / revokeApiKey / listApiKeys) —
// no hashing or key logic is duplicated here, and there are NO hardcoded keys or auth-bypass paths.
//
// The raw key is printed EXACTLY ONCE at issuance (only its SHA-256 hash is stored) and never
// logged again. Operator-only: run it where DATABASE_URL points at the target Neon branch/prod.
//
//   node scripts/ops/keys.mjs issue --name "<label>" [--scopes read,submit:feedback]
//                                   [--owner-type user|service|system] [--owner-id <id>]
//                                   [--rpm <n>] [--rpd <n>] [--expires-days <n>]
//   node scripts/ops/keys.mjs revoke --id <uuid> [--reason "<text>"] [--by "<operator>"]
//   node scripts/ops/keys.mjs list
//
// Reads DATABASE_URL from the environment or a local .env (same loader posture as migrate.mjs).

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createDb, issueApiKey, listApiKeys, revokeApiKey, SCOPES } from '@intercal/core';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');

function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  const envPath = join(repoRoot, '.env');
  if (existsSync(envPath)) {
    for (const line of readFileSync(envPath, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^\s*DATABASE_URL\s*=\s*(.+?)\s*$/);
      if (m) return m[1].replace(/^["']|["']$/g, '');
    }
  }
  return undefined;
}

/** Parse `--flag value` / `--flag=value` pairs into an object. */
function parseFlags(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const eq = a.indexOf('=');
    if (eq >= 0) {
      out[a.slice(2, eq)] = a.slice(eq + 1);
    } else {
      const next = argv[i + 1];
      if (next && !next.startsWith('--')) {
        out[a.slice(2)] = next;
        i++;
      } else {
        out[a.slice(2)] = true;
      }
    }
  }
  return out;
}

function usage(msg) {
  if (msg) console.error(`[keys] ${msg}\n`);
  console.error(
    [
      'Usage:',
      '  keys issue  --name "<label>" [--scopes read,submit:feedback] [--owner-type user]',
      '              [--owner-id <id>] [--rpm <n>] [--rpd <n>] [--expires-days <n>]',
      '  keys revoke --id <uuid> [--reason "<text>"] [--by "<operator>"]',
      '  keys list',
      '',
      `Known scopes: ${Object.values(SCOPES).join(', ')}`,
    ].join('\n'),
  );
  process.exit(2);
}

function fmt(d) {
  return d ? new Date(d).toISOString() : '—';
}

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  if (!command || command === 'help' || command === '--help') usage();

  const databaseUrl = loadDatabaseUrl();
  if (!databaseUrl) {
    console.error('[keys] DATABASE_URL is not set (env or .env).');
    process.exit(2);
  }
  const flags = parseFlags(rest);
  const db = createDb(databaseUrl);

  try {
    if (command === 'issue') {
      if (!flags.name) usage('issue requires --name');
      const scopes = (flags.scopes ? String(flags.scopes) : SCOPES.READ)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const expiresAt = flags['expires-days']
        ? new Date(Date.now() + Number(flags['expires-days']) * 86_400_000)
        : null;
      const issued = await issueApiKey(db, {
        name: String(flags.name),
        scopes,
        ownerType: flags['owner-type'] ? String(flags['owner-type']) : 'user',
        ownerId: flags['owner-id'] ? String(flags['owner-id']) : null,
        requestsPerMinute: flags.rpm ? Number(flags.rpm) : null,
        requestsPerDay: flags.rpd ? Number(flags.rpd) : null,
        expiresAt,
      });
      // The ONLY place the raw key is ever shown. Copy it now — it is not recoverable.
      console.log('[keys] issued — copy the raw key now; it is shown ONCE and not stored:\n');
      console.log(`  id:      ${issued.id}`);
      console.log(`  name:    ${issued.name}`);
      console.log(`  scopes:  ${issued.scopes.join(', ')}`);
      console.log(`  expires: ${fmt(issued.expiresAt)}`);
      console.log(`\n  KEY:     ${issued.raw}\n`);
      return;
    }

    if (command === 'revoke') {
      if (!flags.id) usage('revoke requires --id');
      await revokeApiKey(db, String(flags.id), {
        revokedBy: flags.by ? String(flags.by) : 'ops-cli',
        reason: flags.reason ? String(flags.reason) : undefined,
      });
      console.log(`[keys] revoked ${flags.id}`);
      return;
    }

    if (command === 'list') {
      const keys = await listApiKeys(db);
      if (keys.length === 0) {
        console.log('[keys] no keys.');
        return;
      }
      for (const k of keys) {
        const state = k.revokedAt ? 'REVOKED' : k.isActive ? 'active' : 'inactive';
        console.log(
          `${k.id}  ${state.padEnd(8)}  ${k.keyPrefix}…  [${k.scopes.join(',')}]  ${k.name}` +
            `  (used: ${fmt(k.lastUsedAt)}, expires: ${fmt(k.expiresAt)})`,
        );
      }
      return;
    }

    usage(`unknown command: ${command}`);
  } finally {
    await db.destroy();
  }
}

main().catch((err) => {
  console.error(`[keys] ${err.message}`);
  process.exit(1);
});
