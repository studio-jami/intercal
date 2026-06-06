#!/usr/bin/env node
// Cloud Run deploy — build the portable pipeline-worker image and deploy it as a Cloud Run Job
// (Plan 07 W4). The Job runs the SAME `intercal-pipeline` CLI as the GitHub Actions scheduled
// path (W3) and as local dev — one portable worker, three runners. This is the heavy/on-demand
// path; the routine 6-hourly schedule stays on free Actions (see docs/operations/pipeline-cd.md).
//
// What it does (idempotent; safe to re-run):
//   1. Ensures the Artifact Registry repo exists.
//   2. Cloud Build`s docker/workers.Dockerfile -> AR (immutable git-SHA tag + `latest`).
//   3. Ensures the least-privilege runtime service account + IAM exist.
//   4. Syncs the SENSITIVE runtime values from the local .env into Secret Manager
//      (one version per run; values piped via stdin, NEVER on the command line / in logs).
//   5. Creates or updates the Cloud Run Job: non-secret config via --set-env-vars, sensitive
//      values via --set-secrets (Secret Manager refs — never plaintext env).
//
// HARD RULE: never prints a secret value. Logs show NAME + action only.
//
// Usage:
//   node scripts/ops/deploy-cloud-run.mjs [--build-only | --deploy-only] [--tag <git-sha>] [--dry-run]
//
// Auth: the active `gcloud` account (operator lane) must be able to run Cloud Build, push to AR,
// manage the SA/IAM, and write Secret Manager. In CI this is the `google-github-actions/auth`
// identity (GCP_SA_KEY); locally it is your `gcloud auth login` account.
//
// Config (read from .env, non-secret): GCLOUD_PROJECT_ID, GCLOUD_REGION (deploy region), plus the
// app-runtime selectors/budget knobs. Sensitive values (DATABASE_URL, S3_*, REDIS_URL, Upstash,
// GEMINI_API_KEY) are fanned to Secret Manager. See docs/operations/pipeline-cd.md.
import { execFile, execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const ENV_PATH = resolve(REPO_ROOT, '.env');

// Fixed names (keep in sync with docs/operations/pipeline-cd.md).
const AR_REPO = 'intercal';
const IMAGE_NAME = 'pipeline';
const JOB_NAME = 'intercal-pipeline';
const SA_ID = 'intercal-pipeline';
const SECRET_PREFIX = 'intercal-';

// Sensitive runtime values → Secret Manager (NAME -> .env key). Bound via --set-secrets.
const SECRET_ENV = [
  'DATABASE_URL',
  'S3_ENDPOINT',
  'S3_BUCKET',
  'S3_ACCESS_KEY_ID',
  'S3_SECRET_ACCESS_KEY',
  'REDIS_URL',
  'UPSTASH_REDIS_REST_URL',
  'UPSTASH_REDIS_REST_TOKEN',
  'GEMINI_API_KEY',
];

// Non-secret config → plaintext --set-env-vars. Values pulled from .env with these defaults so a
// fresh deploy is self-describing and matches resource-budget.md / the W3 Actions path.
const ENV_DEFAULTS = {
  STORAGE_PROVIDER: 's3',
  S3_REGION: 'auto',
  S3_FORCE_PATH_STYLE: 'true',
  QUEUE_PROVIDER: 'redis',
  EMBEDDINGS_PROVIDER: 'local',
  EMBEDDINGS_MODEL: 'BAAI/bge-small-en-v1.5',
  EMBEDDINGS_DIM: '384',
  LLM_PROVIDER: 'gemini',
  LLM_MODEL: 'gemini-2.5-flash',
  VERTEX_LOCATION: 'us-east4',
  EXTRACT_ONLY_CHANGED: 'true',
  LLM_DAILY_REQUEST_BUDGET: '2000',
  LLM_MAX_OUTPUT_TOKENS: '2048',
  LLM_PRIMARY: 'vertex',
  EMBEDDINGS_BATCH_SIZE: '64',
  INGEST_MAX_DOCS_PER_RUN: '200',
  LOG_LEVEL: 'info',
};

// ---- args -------------------------------------------------------------------
function parseArgs(argv) {
  const opts = { buildOnly: false, deployOnly: false, tag: null, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--build-only') opts.buildOnly = true;
    else if (a === '--deploy-only') opts.deployOnly = true;
    else if (a === '--dry-run') opts.dryRun = true;
    else if (a === '--tag') opts.tag = argv[++i];
    else if (a.startsWith('--tag=')) opts.tag = a.slice('--tag='.length);
    else {
      console.error(`Unknown argument: ${a}`);
      process.exit(2);
    }
  }
  if (opts.buildOnly && opts.deployOnly) {
    console.error('--build-only and --deploy-only are mutually exclusive.');
    process.exit(2);
  }
  return opts;
}

// ---- .env (minimal parser; no dependency) -----------------------------------
function loadDotenv(path) {
  let raw;
  try {
    raw = readFileSync(path, 'utf8');
  } catch {
    console.error(`Cannot read ${path}. Create a local .env (gitignored) from .env.example first.`);
    process.exit(1);
  }
  const out = new Map();
  for (const line of raw.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq === -1) continue;
    const key = t.slice(0, eq).trim();
    let val = t.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (key) out.set(key, val);
  }
  return out;
}

function gitShortSha() {
  try {
    return execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: REPO_ROOT })
      .toString()
      .trim();
  } catch {
    return 'manual';
  }
}

/** Run gcloud, never echoing args that might carry a value. */
async function gcloud(args, { project, region } = {}) {
  const full = [...args];
  if (project) full.push('--project', project);
  if (region) full.push('--region', region);
  await execFileAsync('gcloud', full, { cwd: REPO_ROOT });
}

async function gcloudOk(args) {
  try {
    await execFileAsync('gcloud', args, { cwd: REPO_ROOT });
    return true;
  } catch {
    return false;
  }
}

// ---- steps ------------------------------------------------------------------
async function ensureArRepo(project, region, dryRun) {
  const exists = await gcloudOk([
    'artifacts',
    'repositories',
    'describe',
    AR_REPO,
    '--location',
    region,
    '--project',
    project,
  ]);
  if (exists) return console.log(`  [ar] repo ${AR_REPO} present (${region})`);
  if (dryRun) return console.log(`  [ar] would create repo ${AR_REPO} (${region})`);
  await gcloud([
    'artifacts',
    'repositories',
    'create',
    AR_REPO,
    '--repository-format=docker',
    '--location',
    region,
    '--description=Intercal Cloud Run worker/pipeline images (Plan 07 W4)',
    '--project',
    project,
  ]);
  console.log(`  [ar] created repo ${AR_REPO} (${region})`);
}

function imageBase(project, region) {
  return `${region}-docker.pkg.dev/${project}/${AR_REPO}/${IMAGE_NAME}`;
}

async function cloudBuild(project, region, image, tag, dryRun) {
  if (dryRun) return console.log(`  [build] would Cloud Build ${image}:${tag} (+ :latest)`);
  console.log(`  [build] Cloud Build ${image}:${tag} (+ :latest) ...`);
  await gcloud([
    'builds',
    'submit',
    '--config',
    'docker/cloudbuild.workers.yaml',
    '--substitutions',
    `_IMAGE=${image},_TAG=${tag}`,
    '--region',
    region,
    '--project',
    project,
  ]);
  console.log(`  [build] pushed ${image}:${tag}`);
}

async function ensureServiceAccount(project, region, dryRun) {
  const saEmail = `${SA_ID}@${project}.iam.gserviceaccount.com`;
  const exists = await gcloudOk([
    'iam',
    'service-accounts',
    'describe',
    saEmail,
    '--project',
    project,
  ]);
  if (!exists) {
    if (dryRun) {
      console.log(`  [sa] would create ${saEmail} + grant least-priv roles`);
      return saEmail;
    }
    await gcloud([
      'iam',
      'service-accounts',
      'create',
      SA_ID,
      '--display-name=Intercal pipeline (Cloud Run Job, Plan 07 W4)',
      '--project',
      project,
    ]);
    console.log(`  [sa] created ${saEmail}`);
  } else {
    console.log(`  [sa] ${saEmail} present`);
  }
  // Least-privilege project roles + repo-scoped AR read (idempotent — re-binding is a no-op).
  const roles = [
    'roles/aiplatform.user',
    'roles/secretmanager.secretAccessor',
    'roles/logging.logWriter',
  ];
  for (const role of roles) {
    if (dryRun) {
      console.log(`  [sa] would ensure ${role}`);
      continue;
    }
    await gcloud([
      'projects',
      'add-iam-policy-binding',
      project,
      `--member=serviceAccount:${saEmail}`,
      `--role=${role}`,
      '--condition=None',
      '--quiet',
    ]);
  }
  if (!dryRun) {
    await gcloud([
      'artifacts',
      'repositories',
      'add-iam-policy-binding',
      AR_REPO,
      '--location',
      region,
      `--member=serviceAccount:${saEmail}`,
      '--role=roles/artifactregistry.reader',
      '--project',
      project,
    ]);
  }
  console.log(`  [sa] least-privilege roles ensured`);
  return saEmail;
}

async function syncSecrets(env, project, dryRun) {
  for (const name of SECRET_ENV) {
    const value = env.get(name);
    const secretId = `${SECRET_PREFIX}${name}`;
    if (value === undefined || value === '') {
      console.log(`  [secret] SKIP ${name} (absent in .env)`);
      continue;
    }
    if (dryRun) {
      console.log(`  [secret] would set ${secretId} (new version)`);
      continue;
    }
    const exists = await gcloudOk(['secrets', 'describe', secretId, '--project', project]);
    if (!exists) {
      await gcloud([
        'secrets',
        'create',
        secretId,
        '--replication-policy=automatic',
        '--project',
        project,
      ]);
    }
    // Pipe the value via stdin so it never appears as a process arg / in logs.
    await new Promise((resolveP, rejectP) => {
      const child = execFile(
        'gcloud',
        ['secrets', 'versions', 'add', secretId, '--data-file=-', '--project', project],
        (err) => (err ? rejectP(new Error(`secret add failed for ${secretId}`)) : resolveP()),
      );
      child.stdin.end(value);
    });
    console.log(`  [secret] set ${secretId} (new version)`);
  }
}

function buildEnvVarsArg(env) {
  const pairs = Object.entries(ENV_DEFAULTS).map(([k, def]) => `${k}=${env.get(k) ?? def}`);
  // GCLOUD_PROJECT_ID is needed by the Vertex path; carry it as an explicit non-secret env.
  const project = env.get('GCLOUD_PROJECT_ID');
  if (project) pairs.push(`GCLOUD_PROJECT_ID=${project}`);
  return pairs.join(',');
}

function buildSecretsArg() {
  return SECRET_ENV.map((n) => `${n}=${SECRET_PREFIX}${n}:latest`).join(',');
}

async function deployJob(env, project, region, image, tag, saEmail, dryRun) {
  const exists = await gcloudOk([
    'run',
    'jobs',
    'describe',
    JOB_NAME,
    '--region',
    region,
    '--project',
    project,
  ]);
  const verb = exists ? 'update' : 'create';
  const args = [
    'run',
    'jobs',
    verb,
    JOB_NAME,
    '--image',
    `${image}:${tag}`,
    '--region',
    region,
    '--project',
    project,
    '--service-account',
    saEmail,
    '--cpu=1',
    '--memory=2Gi',
    '--max-retries=0',
    '--parallelism=1',
    '--task-timeout=1800s',
    `--set-env-vars=${buildEnvVarsArg(env)}`,
    `--set-secrets=${buildSecretsArg()}`,
  ];
  if (dryRun) {
    console.log(`  [job] would ${verb} ${JOB_NAME} @ ${image}:${tag} (sa=${saEmail})`);
    return;
  }
  await execFileAsync('gcloud', args, { cwd: REPO_ROOT });
  console.log(`  [job] ${verb}d ${JOB_NAME} @ ${image}:${tag}`);
  console.log(`  [job] execute on demand:  gcloud run jobs execute ${JOB_NAME} --region ${region}`);
}

// ---- main -------------------------------------------------------------------
async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const env = loadDotenv(ENV_PATH);
  const project = env.get('GCLOUD_PROJECT_ID');
  // Cloud Run Job + Artifact Registry region. Dedicated knob (defaults us-central1, where the
  // project's other Cloud Run infra + the AR `intercal` repo live) — intentionally NOT
  // GCLOUD_REGION, which is the W1 fan-out's operator-lane region for `gcloud run services update`.
  const region = env.get('CLOUD_RUN_REGION') || 'us-central1';
  if (!project) {
    console.error('GCLOUD_PROJECT_ID missing from .env');
    process.exit(1);
  }
  const tag = opts.tag || gitShortSha();
  const image = imageBase(project, region);

  console.log(`Intercal Cloud Run deploy${opts.dryRun ? ' (DRY RUN — no writes)' : ''}`);
  console.log(`Project: ${project}  ·  Region: ${region}  ·  Tag: ${tag}\n`);

  if (!opts.deployOnly) {
    console.log('== artifact registry ==');
    await ensureArRepo(project, region, opts.dryRun);
    console.log('== build (Cloud Build → Artifact Registry) ==');
    await cloudBuild(project, region, image, tag, opts.dryRun);
    console.log('');
  }

  if (opts.buildOnly) {
    console.log('Build-only complete.');
    return;
  }

  console.log('== service account (least privilege) ==');
  const saEmail = await ensureServiceAccount(project, region, opts.dryRun);
  console.log('== secrets (.env → Secret Manager; values never printed) ==');
  await syncSecrets(env, project, opts.dryRun);
  console.log('== cloud run job ==');
  await deployJob(env, project, region, image, tag, saEmail, opts.dryRun);
  console.log('');
  console.log(
    opts.dryRun ? 'Dry run complete. No writes performed.' : 'Cloud Run deploy complete.',
  );
}

await main();
