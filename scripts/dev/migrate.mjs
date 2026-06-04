#!/usr/bin/env node
// SQL-first migration runner for Intercal.
// Applies db/migrations/*.sql in filename order; db/seeds/*.sql are idempotent seeds.
//
//   node scripts/dev/migrate.mjs            apply pending migrations
//   node scripts/dev/migrate.mjs --fresh    drop public schema, then apply all
//   node scripts/dev/migrate.mjs --fresh --seed   apply all + seeds
//   node scripts/dev/migrate.mjs --seed     apply pending + seeds
//   node scripts/dev/migrate.mjs --check    fail if any migration is unapplied
//
// Reads DATABASE_URL from the environment or a local .env. No ORM.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');
const migrationsDir = join(repoRoot, 'db', 'migrations');
const seedsDir = join(repoRoot, 'db', 'seeds');

const args = new Set(process.argv.slice(2));
const FRESH = args.has('--fresh');
const SEED = args.has('--seed');
const CHECK = args.has('--check');

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

function sqlFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.sql'))
    .sort();
}

async function main() {
  const databaseUrl = loadDatabaseUrl();
  if (!databaseUrl) {
    console.error('[migrate] DATABASE_URL is not set (env or .env). Skipping.');
    process.exit(2);
  }

  let pg;
  try {
    pg = (await import('pg')).default;
  } catch {
    console.error('[migrate] The "pg" package is not installed. Run `pnpm install`.');
    process.exit(2);
  }

  const client = new pg.Client({ connectionString: databaseUrl });
  try {
    await client.connect();
  } catch (err) {
    console.error(`[migrate] Could not connect to Postgres: ${err.message}`);
    console.error(
      '[migrate] Is `docker compose up -d` running, or DATABASE_URL pointed at a live DB?',
    );
    process.exit(3);
  }

  try {
    if (FRESH && !CHECK) {
      console.log('[migrate] --fresh: resetting public schema');
      await client.query('DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;');
    }

    await client.query(
      'CREATE TABLE IF NOT EXISTS _migrations (filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());',
    );

    const applied = new Set(
      (await client.query('SELECT filename FROM _migrations')).rows.map((r) => r.filename),
    );
    const all = sqlFiles(migrationsDir);
    const pending = all.filter((f) => !applied.has(f));

    if (CHECK) {
      if (pending.length === 0) {
        console.log(`[migrate] up to date (${all.length} migrations applied)`);
        process.exit(0);
      }
      console.error(`[migrate] ${pending.length} unapplied migration(s): ${pending.join(', ')}`);
      process.exit(1);
    }

    if (all.length === 0) {
      console.log('[migrate] no migrations found in db/migrations yet.');
    }

    for (const file of pending) {
      const sql = readFileSync(join(migrationsDir, file), 'utf8');
      process.stdout.write(`[migrate] applying ${file} ... `);
      await client.query('BEGIN');
      try {
        await client.query(sql);
        await client.query('INSERT INTO _migrations (filename) VALUES ($1)', [file]);
        await client.query('COMMIT');
        console.log('ok');
      } catch (err) {
        await client.query('ROLLBACK');
        console.log('FAILED');
        throw new Error(`Migration ${file} failed: ${err.message}`);
      }
    }

    if (SEED) {
      for (const file of sqlFiles(seedsDir)) {
        const sql = readFileSync(join(seedsDir, file), 'utf8');
        process.stdout.write(`[seed] applying ${file} ... `);
        await client.query(sql);
        console.log('ok');
      }
    }

    console.log('[migrate] done.');
  } finally {
    await client.end();
  }
}

main().catch((err) => {
  console.error(`[migrate] ${err.message}`);
  process.exit(1);
});
