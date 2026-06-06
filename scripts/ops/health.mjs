#!/usr/bin/env node
// Intercal operator health CLI (Plan 04 W6).
//
// Reads only observability views and never prints credentials. Provider rows with no imported
// measurement are reported as unavailable, not as zero usage.

import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const ENV_PATH = resolve(REPO_ROOT, '.env');

const DEFAULT_LIMIT = 20;
const SECTIONS = new Set(['summary', 'sources', 'freshness', 'failures', 'usage', 'providers']);

function parseFlags(argv) {
  const flags = { section: 'summary', limit: DEFAULT_LIMIT, json: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--') {
      continue;
    }
    if (arg === '--json') {
      flags.json = true;
      continue;
    }
    if (arg === '--help' || arg === '-h') {
      flags.help = true;
      continue;
    }
    if (arg === '--list-sections') {
      flags.listSections = true;
      continue;
    }
    if (arg === '--print-sql') {
      flags.printSql = true;
      continue;
    }
    if (arg === '--section' || arg === '-s') {
      flags.section = argv[++i];
      continue;
    }
    if (arg.startsWith('--section=')) {
      flags.section = arg.slice('--section='.length);
      continue;
    }
    if (arg === '--limit') {
      flags.limit = Number.parseInt(argv[++i] ?? '', 10);
      continue;
    }
    if (arg.startsWith('--limit=')) {
      flags.limit = Number.parseInt(arg.slice('--limit='.length), 10);
      continue;
    }
    throw new Error(`unknown argument: ${arg}`);
  }
  if (!SECTIONS.has(flags.section)) {
    throw new Error(`unknown section ${JSON.stringify(flags.section)}; use --list-sections`);
  }
  if (!Number.isInteger(flags.limit) || flags.limit < 1 || flags.limit > 500) {
    throw new Error('--limit must be an integer between 1 and 500');
  }
  return flags;
}

function printHelp() {
  console.log(`Usage:
  pnpm ops:health [--section summary|sources|freshness|failures|usage|providers] [--json] [--limit N]
  pnpm ops:health --list-sections
  pnpm ops:health --print-sql

Environment:
  DATABASE_URL is read from the shell first, then .env. The URL is never printed.

Sections:
  summary     Key health/quality/queue/provider rollups
  sources     Per-source health and latest ingestion state
  freshness   Source/evidence/claim/fact/digest recency
  failures    Failed ingestion and subscription jobs
  usage       REST/MCP latency and error buckets from usage_events
  providers   Provider consumption versus docs/operations/resource-budget.md allowances
`);
}

function loadDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  if (!existsSync(ENV_PATH)) return undefined;
  for (const line of readFileSync(ENV_PATH, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*DATABASE_URL\s*=\s*(.+?)\s*$/);
    if (match) return match[1].replace(/^["']|["']$/g, '');
  }
  return undefined;
}

function queries(limit) {
  return {
    summary: [
      {
        name: 'pipeline',
        sql: `SELECT area, metric, value, unit
              FROM observability_pipeline_metrics
              ORDER BY area, metric`,
        params: [],
      },
      {
        name: 'source_states',
        sql: `SELECT health_state, count(*)::integer AS count
              FROM observability_source_health
              GROUP BY health_state
              ORDER BY health_state`,
        params: [],
      },
      {
        name: 'provider_states',
        sql: `SELECT budget_state, count(*)::integer AS count
              FROM observability_provider_consumption
              GROUP BY budget_state
              ORDER BY budget_state`,
        params: [],
      },
    ],
    sources: [
      {
        name: 'sources',
        sql: `SELECT slug, name, health_state, is_active, is_paused, reliability_score,
                     consecutive_failures, latest_run_status, last_success_at, last_failed_at,
                     next_run_at, documents_new_24h, documents_error_24h
              FROM observability_source_health
              ORDER BY
                CASE health_state
                  WHEN 'degraded' THEN 0
                  WHEN 'due' THEN 1
                  WHEN 'paused' THEN 2
                  WHEN 'inactive' THEN 3
                  ELSE 4
                END,
                slug
              LIMIT $1`,
        params: [limit],
      },
    ],
    freshness: [
      {
        name: 'freshness',
        sql: `SELECT subject_type, subject_key, subject_label, freshness_state,
                     age_minutes, last_observed_at, next_run_at
              FROM observability_freshness
              ORDER BY
                CASE freshness_state
                  WHEN 'stale' THEN 0
                  WHEN 'due' THEN 1
                  WHEN 'unknown' THEN 2
                  ELSE 3
                END,
                age_minutes DESC NULLS FIRST
              LIMIT $1`,
        params: [limit],
      },
    ],
    failures: [
      {
        name: 'failures',
        sql: `SELECT job_type, job_id, owner_slug, status, created_at, error_message
              FROM observability_failed_jobs
              ORDER BY created_at DESC
              LIMIT $1`,
        params: [limit],
      },
    ],
    usage: [
      {
        name: 'usage_latency',
        sql: `SELECT bucket_hour, surface, tool_name, request_count, error_count,
                     avg_latency_ms, p95_latency_ms, tokens_used, token_budget
              FROM observability_usage_latency
              ORDER BY bucket_hour DESC, surface, tool_name
              LIMIT $1`,
        params: [limit],
      },
    ],
    providers: [
      {
        name: 'providers',
        sql: `SELECT provider, allowance_key, metric_name, metric_unit, allowance_period,
                     allowance_quantity, quantity_used, used_pct, cost_usd, budget_state,
                     last_observed_at, unavailable_reason
              FROM observability_provider_consumption
              ORDER BY
                CASE budget_state
                  WHEN 'exceeded' THEN 0
                  WHEN 'warning' THEN 1
                  WHEN 'unavailable' THEN 2
                  ELSE 3
                END,
                provider,
                allowance_key
              LIMIT $1`,
        params: [limit],
      },
    ],
  };
}

function printSql() {
  for (const [section, specs] of Object.entries(queries(DEFAULT_LIMIT))) {
    console.log(`-- ${section}`);
    for (const spec of specs) console.log(`${spec.sql.trim()};\n`);
  }
}

function cleanRows(rows) {
  return rows.map((row) =>
    Object.fromEntries(
      Object.entries(row).map(([key, value]) => [
        key,
        typeof value === 'bigint' ? value.toString() : value,
      ]),
    ),
  );
}

function formatValue(value) {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) return value.toISOString();
  return String(value);
}

function printTable(name, rows) {
  console.log(`\n${name}`);
  if (rows.length === 0) {
    console.log('  no rows');
    return;
  }
  const columns = Object.keys(rows[0]);
  const widths = Object.fromEntries(
    columns.map((column) => [
      column,
      Math.min(48, Math.max(column.length, ...rows.map((row) => formatValue(row[column]).length))),
    ]),
  );
  console.log(columns.map((column) => column.padEnd(widths[column])).join('  '));
  console.log(columns.map((column) => '-'.repeat(widths[column])).join('  '));
  for (const row of rows) {
    console.log(
      columns
        .map((column) => {
          const value = formatValue(row[column]);
          const clipped =
            value.length > widths[column] ? `${value.slice(0, widths[column] - 3)}...` : value;
          return clipped.padEnd(widths[column]);
        })
        .join('  '),
    );
  }
}

async function main() {
  const flags = parseFlags(process.argv.slice(2));
  if (flags.help) {
    printHelp();
    return;
  }
  if (flags.listSections) {
    console.log([...SECTIONS].join('\n'));
    return;
  }
  if (flags.printSql) {
    printSql();
    return;
  }

  const databaseUrl = loadDatabaseUrl();
  if (!databaseUrl) {
    throw new Error('DATABASE_URL is not set in the environment or .env');
  }

  let pg;
  try {
    pg = (await import('pg')).default;
  } catch {
    throw new Error('the "pg" package is not installed; run pnpm install');
  }

  const client = new pg.Client({ connectionString: databaseUrl });
  await client.connect();
  try {
    const output = {};
    for (const spec of queries(flags.limit)[flags.section]) {
      const result = await client.query(spec.sql, spec.params);
      output[spec.name] = cleanRows(result.rows);
    }
    if (flags.json) {
      console.log(JSON.stringify(output, null, 2));
      return;
    }
    for (const [name, rows] of Object.entries(output)) printTable(name, rows);
  } finally {
    await client.end();
  }
}

main().catch((err) => {
  console.error(`[ops:health] ${err.message}`);
  process.exit(1);
});
