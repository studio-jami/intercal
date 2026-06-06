/**
 * Secret fan-out — one canonical source (the gitignored local `.env`) propagated to every target:
 * Vercel project env, GitHub Actions repo secrets, and (when it exists) Cloud Run service env.
 *
 * The script reads NAMES + target mapping from `scripts/ops/secrets.manifest.json` and pulls the
 * matching VALUES from `.env`. App-runtime secrets are the fan-out payload; operator-lane
 * credentials (Vercel token, gh PAT, GCP SA) authenticate the fan-out itself and are NEVER fanned
 * into the app env (manifest `targets: []`).
 *
 * HARD RULE: this script never prints a secret value. Logs show NAME + target + action only.
 *
 * Usage:
 *   node scripts/ops/secrets-fanout.mjs [--target vercel|github|cloudrun|all] [--dry-run]
 *
 * Auth (operator lane, read from `.env`, never logged, never fanned):
 *   Vercel    : VERCEL_TOKEN (+ VERCEL_PROJECT_ID, VERCEL_TEAM_ID) via REST API.
 *   GitHub    : `gh` CLI auth (keyring) or GH_TOKEN env; repo from GITHUB_REPO.
 *   Cloud Run : `gcloud` CLI active account; deferred until a service exists (Plan 07 W4).
 */
import { execFile } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const ENV_PATH = resolve(REPO_ROOT, '.env');
const MANIFEST_PATH = resolve(HERE, 'secrets.manifest.json');
const VALID_TARGETS = ['vercel', 'github', 'cloudrun'];

// ---- args -------------------------------------------------------------------
function parseArgs(argv) {
  let target = 'all';
  let dryRun = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--dry-run') dryRun = true;
    else if (arg === '--target') target = argv[++i];
    else if (arg.startsWith('--target=')) target = arg.slice('--target='.length);
    else {
      console.error(`Unknown argument: ${arg}`);
      process.exit(2);
    }
  }
  if (target !== 'all' && !VALID_TARGETS.includes(target)) {
    console.error(`--target must be one of: ${VALID_TARGETS.join('|')}|all`);
    process.exit(2);
  }
  return { targets: target === 'all' ? VALID_TARGETS : [target], dryRun };
}

// ---- .env (minimal parser; no dependency) -----------------------------------
function loadDotenv(path) {
  let raw;
  try {
    raw = readFileSync(path, 'utf8');
  } catch {
    console.error(`Cannot read source secrets file: ${path}`);
    console.error('Create a local `.env` (gitignored) from `.env.example` first.');
    process.exit(1);
  }
  const out = new Map();
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) out.set(key, value);
  }
  return out;
}

function loadManifest(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/** Normalize a GitHub repo reference (URL or owner/repo) to the `owner/repo` form `gh` expects. */
function normalizeRepo(ref) {
  if (!ref) return ref;
  const match = ref.match(/github\.com[/:]([^/]+\/[^/]+?)(?:\.git)?\/?$/);
  return (match ? match[1] : ref).replace(/\.git$/, '');
}

// ---- planning ---------------------------------------------------------------
/** Build the list of {name, optional} entries that target `target`, from app-runtime lane only. */
function plannedFor(manifest, target) {
  return manifest.secrets.filter(
    (s) => s.lane === 'app-runtime' && (s.targets ?? []).includes(target),
  );
}

/** Resolve values from env; split into present/missing-required/skipped-optional (NO values returned to logs). */
function resolveValues(planned, env) {
  const present = [];
  const missingRequired = [];
  const skippedOptional = [];
  for (const s of planned) {
    const value = env.get(s.name);
    if (value === undefined || value === '') {
      if (s.optional) skippedOptional.push(s.name);
      else missingRequired.push(s.name);
    } else {
      present.push({ name: s.name, value });
    }
  }
  return { present, missingRequired, skippedOptional };
}

// ---- Vercel -----------------------------------------------------------------
function vercelBase(env) {
  const token = env.get('VERCEL_TOKEN');
  const projectId = env.get('VERCEL_PROJECT_ID');
  const teamId = env.get('VERCEL_TEAM_ID');
  const teamQ = teamId ? `&teamId=${encodeURIComponent(teamId)}` : '';
  return { token, projectId, teamId, teamQ };
}

/** Fetch existing env entries grouped by key -> [{id, target}]. */
async function vercelExisting(token, projectId, teamQ) {
  const res = await fetch(
    `https://api.vercel.com/v10/projects/${encodeURIComponent(projectId)}/env?decrypt=false${teamQ}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) return new Map();
  const body = await res.json();
  const envs = body.envs ?? body.env ?? [];
  const byKey = new Map();
  for (const e of envs) {
    if (!byKey.has(e.key)) byKey.set(e.key, []);
    byKey.get(e.key).push({ id: e.id, target: e.target ?? [] });
  }
  return byKey;
}

const sameTargets = (a, b) =>
  a.length === b.length && [...a].sort().join() === [...b].sort().join();

/**
 * Idempotent reconcile: for each name, if a single existing entry already covers exactly the
 * desired target set we leave it (re-running won't churn unchanged values needlessly via PATCH);
 * otherwise we delete any existing entries for that key and POST one unified entry. This handles
 * the common case where a key was created as separate per-target rows (ENV_CONFLICT on upsert).
 */
async function fanoutVercel(present, env, vercelTargets, dryRun) {
  const { token, projectId, teamQ } = vercelBase(env);
  if (!token || !projectId) {
    return { ok: false, blocker: 'VERCEL_TOKEN and/or VERCEL_PROJECT_ID missing from .env' };
  }
  const existing = dryRun ? new Map() : await vercelExisting(token, projectId, teamQ);
  const done = [];
  for (const { name, value } of present) {
    const cur = existing.get(name) ?? [];
    const unified = cur.length === 1 && sameTargets(cur[0].target, vercelTargets);
    if (dryRun) {
      console.log(`  [vercel] would set ${name} -> [${vercelTargets.join(',')}]`);
      done.push(name);
      continue;
    }
    // Always PATCH/replace value to keep the source authoritative; delete stale per-target rows.
    for (const e of unified ? [] : cur) {
      const del = await fetch(
        `https://api.vercel.com/v9/projects/${encodeURIComponent(projectId)}/env/${e.id}?${teamQ.slice(1)}`,
        { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } },
      );
      if (!del.ok && del.status !== 404) {
        console.error(`  [vercel] FAILED ${name}: delete ${del.status}`);
        return { ok: false, blocker: `Vercel delete failed for ${name} (${del.status})`, done };
      }
    }
    const res = unified
      ? await fetch(
          `https://api.vercel.com/v9/projects/${encodeURIComponent(projectId)}/env/${cur[0].id}?${teamQ.slice(1)}`,
          {
            method: 'PATCH',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ value }),
          },
        )
      : await fetch(
          `https://api.vercel.com/v10/projects/${encodeURIComponent(projectId)}/env?${teamQ.slice(1)}`,
          {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: name, value, type: 'encrypted', target: vercelTargets }),
          },
        );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const code = body?.error?.code ?? res.status;
      console.error(`  [vercel] FAILED ${name}: ${code}`);
      return { ok: false, blocker: `Vercel set failed for ${name} (${code})`, done };
    }
    console.log(`  [vercel] set ${name} -> [${vercelTargets.join(',')}]`);
    done.push(name);
  }
  return { ok: true, done };
}

async function listVercel(env) {
  const token = env.get('VERCEL_TOKEN');
  const projectId = env.get('VERCEL_PROJECT_ID');
  const teamId = env.get('VERCEL_TEAM_ID');
  const teamQuery = teamId ? `?teamId=${encodeURIComponent(teamId)}` : '';
  const res = await fetch(
    `https://api.vercel.com/v10/projects/${encodeURIComponent(projectId)}/env${teamQuery}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) return [];
  const body = await res.json();
  const envs = body.envs ?? body.env ?? [];
  return [...new Set(envs.map((e) => e.key))].sort();
}

// ---- GitHub Actions ---------------------------------------------------------
async function fanoutGithub(present, env, dryRun) {
  const repo = normalizeRepo(env.get('GITHUB_REPO'));
  if (!repo) return { ok: false, blocker: 'GITHUB_REPO missing from .env' };
  // gh CLI auth (keyring) authenticates; GH_TOKEN env overrides if the manifest provides one.
  const ghEnv = { ...process.env };
  const pat = env.get('GITHUB_TOKEN');
  if (pat) ghEnv.GH_TOKEN = pat;
  const done = [];
  for (const { name, value } of present) {
    if (dryRun) {
      console.log(`  [github] would set ${name} -> ${repo} (Actions secret)`);
      done.push(name);
      continue;
    }
    try {
      await execFileAsync('gh', ['secret', 'set', name, '--repo', repo, '--body', value], {
        env: ghEnv,
      });
      console.log(`  [github] set ${name} -> ${repo}`);
      done.push(name);
    } catch (err) {
      console.error(`  [github] FAILED ${name}: ${redactError(err)}`);
      return { ok: false, blocker: `gh secret set failed for ${name}`, done };
    }
  }
  return { ok: true, done };
}

async function listGithub(env) {
  const repo = normalizeRepo(env.get('GITHUB_REPO'));
  const ghEnv = { ...process.env };
  const pat = env.get('GITHUB_TOKEN');
  if (pat) ghEnv.GH_TOKEN = pat;
  try {
    const { stdout } = await execFileAsync(
      'gh',
      ['secret', 'list', '--repo', repo, '--json', 'name'],
      { env: ghEnv },
    );
    return JSON.parse(stdout)
      .map((s) => s.name)
      .sort();
  } catch {
    return [];
  }
}

// ---- Cloud Run --------------------------------------------------------------
async function fanoutCloudRun(present, env, dryRun) {
  const service = env.get('CLOUD_RUN_SERVICE');
  const region = env.get('GCLOUD_REGION');
  const project = env.get('GCLOUD_PROJECT_ID');
  if (!service) {
    return {
      ok: false,
      deferred: true,
      blocker:
        'No Cloud Run service yet (set CLOUD_RUN_SERVICE in .env once Plan 07 W4 deploys one). ' +
        `${present.length} app-runtime names are mapped to cloudrun and ready to fan out.`,
    };
  }
  if (!region || !project) {
    return { ok: false, blocker: 'GCLOUD_REGION and/or GCLOUD_PROJECT_ID missing from .env' };
  }
  // One atomic update: --set-env-vars carries every name=value (values never logged).
  const pairs = present.map(({ name, value }) => `${name}=${value}`);
  if (dryRun) {
    for (const { name } of present) console.log(`  [cloudrun] would set ${name} -> ${service}`);
    return { ok: true, done: present.map((p) => p.name) };
  }
  try {
    await execFileAsync('gcloud', [
      'run',
      'services',
      'update',
      service,
      '--region',
      region,
      '--project',
      project,
      `--set-env-vars=${pairs.join(',')}`,
    ]);
    for (const { name } of present) console.log(`  [cloudrun] set ${name} -> ${service}`);
    return { ok: true, done: present.map((p) => p.name) };
  } catch (err) {
    console.error(`  [cloudrun] FAILED: ${redactError(err)}`);
    return { ok: false, blocker: 'gcloud run services update failed' };
  }
}

// ---- redaction --------------------------------------------------------------
/** Never leak values via subprocess error output. Keep only the first line, sans body. */
function redactError(err) {
  const msg = String(err?.message ?? err);
  return msg.split('\n')[0].replace(/--body\s+\S+/g, '--body ***');
}

// ---- main -------------------------------------------------------------------
async function main() {
  const { targets, dryRun } = parseArgs(process.argv.slice(2));
  const env = loadDotenv(ENV_PATH);
  const manifest = loadManifest(MANIFEST_PATH);
  const vercelTargets = manifest.vercelTargets ?? ['production', 'preview', 'development'];

  console.log(`Intercal secret fan-out${dryRun ? ' (DRY RUN — no writes)' : ''}`);
  console.log(`Source: .env  ·  Targets: ${targets.join(', ')}\n`);

  const blockers = [];
  const verify = [];

  for (const target of targets) {
    const planned = plannedFor(manifest, target);
    const { present, missingRequired, skippedOptional } = resolveValues(planned, env);
    console.log(`== ${target} ==`);
    console.log(
      `  planned: ${planned.length}  ·  present: ${present.length}  ·  ` +
        `missing(required): ${missingRequired.length}  ·  skipped(optional): ${skippedOptional.length}`,
    );
    if (missingRequired.length) {
      console.log(`  missing required NAMES (not in .env): ${missingRequired.join(', ')}`);
      blockers.push(`${target}: missing required ${missingRequired.join(', ')} in .env`);
    }
    if (skippedOptional.length) {
      console.log(`  skipped optional NAMES (absent in .env): ${skippedOptional.join(', ')}`);
    }

    let result;
    if (target === 'vercel') result = await fanoutVercel(present, env, vercelTargets, dryRun);
    else if (target === 'github') result = await fanoutGithub(present, env, dryRun);
    else result = await fanoutCloudRun(present, env, dryRun);

    if (!result.ok) {
      const label = result.deferred ? 'DEFERRED' : 'BLOCKER';
      console.log(`  ${label}: ${result.blocker}`);
      blockers.push(`${target}: ${result.blocker}`);
    }
    if (!dryRun && result.ok) verify.push(target);
    console.log('');
  }

  // Verify: list NAMES present at each target after a real run (names only, never values).
  if (verify.length) {
    console.log('== verify (listing NAMES present at each target) ==');
    for (const target of verify) {
      if (target === 'vercel') {
        const names = await listVercel(env);
        console.log(`  [vercel] ${names.length} names: ${names.join(', ')}`);
      } else if (target === 'github') {
        const names = await listGithub(env);
        console.log(`  [github] ${names.length} names: ${names.join(', ')}`);
      }
    }
    console.log('');
  }

  if (blockers.length) {
    console.log(`Completed with ${blockers.length} blocker(s)/deferral(s):`);
    for (const b of blockers) console.log(`  - ${b}`);
  } else {
    console.log(dryRun ? 'Dry run complete. No writes performed.' : 'Fan-out complete.');
  }
}

await main();
