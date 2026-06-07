# Account And CLI Setup

This runbook is the dedicated account setup session for Intercal operators. It is intentionally
secret-safe: it records accounts, access paths, environment variable names, and proof commands, but
never credential values. Values live in the host secret store and the gitignored local `.env`; names
and target mapping live in `.env.example` and `scripts/ops/secrets.manifest.json`.

Use this alongside:

- `docs/operations/deployment.md` for hosted/VPS/self-host deployment paths.
- `docs/operations/secrets.md` for secret fan-out and rotation.
- `docs/operations/backups.md` for Neon backup/restore proof.
- `docs/operations/resource-budget.md` for free-tier/cost guardrails.

## Ground Rules

- Do not paste credentials into docs, chat, shell transcripts, command-line arguments, issue text,
  CI logs, or changelog fragments.
- Use `.env` only as the local source of secret values. Verify it remains ignored:

```powershell
git check-ignore .env
```

- Use `.env.example` and `scripts/ops/secrets.manifest.json` to confirm required names. The
  manifest is names and targets only; it must not contain values.
- Prefer proof commands that list account/resource metadata and variable names. Do not run commands
  that print secret values unless the CLI has a hide/redact option.
- If a proof needs live provider access, record the exact missing auth, role, or CLI in the
  operator handoff instead of claiming it passed.

## Required Operator Access

The setup operator needs:

- Domain/DNS registrar or DNS provider access for the production domain.
- GitHub access to `JamiStudio/intercal` with Actions, repository secrets, variables, workflow
  dispatch, and branch-protection visibility.
- Vercel access to the Intercal project and team, including domains and environment variables.
- Neon project access for branch creation, connection strings, PITR/restore, and role rotation.
- Cloudflare account access for R2 bucket administration and R2 API tokens.
- Upstash access for Redis database creation, token rotation, and usage checks.
- Google Cloud project access for Vertex AI/Gemini, Cloud Build, Artifact Registry, Cloud Run Jobs,
  Secret Manager, service accounts, IAM, and billing/quota visibility.
- SSH key control for any VPS path, plus root/sudo or deploy-user access on the host.

If any of those are missing, W8 is still useful: complete the local/CLI checks, then leave a handoff
line naming the missing account and the operation blocked by it.

## Local CLI Baseline

Install or make available on PATH:

- Node and `pnpm` matching `package.json`.
- Python `uv`.
- Git and GitHub CLI `gh`.
- Vercel CLI.
- Google Cloud CLI `gcloud`.
- Cloudflare Wrangler.
- Upstash CLI or REST/API access.
- Neon CLI or Neon console/API access.
- PostgreSQL client tools `pg_dump`, `pg_restore`, and optionally `psql`.
- AWS CLI only if using the R2 second-copy backup upload path.

Proof commands:

```powershell
node --version
pnpm --version
uv --version
git --version
gh --version
vercel --version
gcloud --version
wrangler --version
upstash --version
neon --version
pg_dump --version
pg_restore --version
aws --version
```

If a CLI is intentionally not installed because the console/API is the chosen operator path, record
that exception in the handoff.

## Domain And DNS

Prerequisites:

- Production domain selected. Current official Intercal domain: `intercal.jami.studio`.
- DNS ownership available through Cloudflare for the parent `jami.studio` zone.
- Vercel project has the domain attached or is ready to attach it. Current project:
  `studio-jami/intercal`.
- `PUBLIC_API_BASE_URL` and optional operator-lane `VERCEL_DOMAIN` are set in `.env` after the domain
  is known.

Setup:

1. Add the domain to the Vercel project.
2. Add only the DNS records Vercel reports for that domain. Do not hard-code records into this repo.
3. Wait for Vercel domain verification and TLS issuance.
4. Fan out runtime URL names through `docs/operations/secrets.md`.

Proof commands:

```powershell
vercel domains ls
vercel domains inspect jami.studio
vercel inspect https://intercal.jami.studio
nslookup -type=ns jami.studio
Resolve-DnsName -Server elliott.ns.cloudflare.com -Name intercal.jami.studio -Type CNAME
Resolve-DnsName -Server irena.ns.cloudflare.com -Name intercal.jami.studio -Type CNAME
Invoke-WebRequest https://intercal.jami.studio/ -UseBasicParsing
Invoke-WebRequest https://intercal.jami.studio/docs -UseBasicParsing
Invoke-WebRequest https://intercal.jami.studio/api/openapi.json -UseBasicParsing
Invoke-WebRequest https://intercal.jami.studio/api/v1/freshness?topic_or_entity=MCP%20protocol -UseBasicParsing
node scripts/dev/verify-mcp.mjs https://intercal.jami.studio/api/mcp
```

Current proof from 2026-06-07:

- Vercel project `intercal` is in account scope `studio-jami`; `intercal.jami.studio` is attached to
  the project and aliases a Ready production deployment.
- Cloudflare authoritative nameservers for `jami.studio` answer `intercal.jami.studio` as a CNAME to
  `25b8236304cda166.vercel-dns-017.com` with TTL `600`.
- TLS and live route smokes passed for `/`, `/docs`, `/api/openapi.json`,
  `/api/v1/freshness?topic_or_entity=MCP%20protocol`, and MCP initialize/tools calls at `/api/mcp`.
- `vercel domains inspect jami.studio` warns about the parent apex configuration. That is external
  Jami Studio site work and does not block the Intercal subdomain.
- Pass 1 found Wrangler auth for Cloudflare account `jami-studio`, but that token could not read DNS
  records through the Cloudflare REST DNS endpoint. Pass 2 did not have a `wrangler` executable or
  Cloudflare token env in the shell, so dashboard/API-side record metadata remains operator-gated.
  If dashboard-side record metadata is required, use Cloudflare Dashboard > `jami.studio` > DNS >
  Records, or issue an operator token with `Zone.DNS Read` for the `jami.studio` zone.

## SSH Keys And VPS

The VPS path is an alternative deployment lane, not the maintainer default. It still needs a clean
handoff so another operator can verify access later.

Prerequisites:

- A named local SSH key dedicated to Intercal operations, preferably hardware-backed or passphrase
  protected.
- Public key installed for the VPS deploy/root account.
- Hostname, user, port, and fingerprint recorded in the operator password manager or infrastructure
  inventory, not in this repo if sensitive.

Proof commands:

```powershell
Get-ChildItem $env:USERPROFILE\.ssh
ssh -T git@github.com
ssh -o IdentitiesOnly=yes <deploy-user>@<vps-host> "hostname; whoami; uname -a"
ssh -o IdentitiesOnly=yes <deploy-user>@<vps-host> "systemctl --version"
```

Operator-gated: the live VPS proof requires a provisioned host and authorized key. If no VPS is in
use, record "not provisioned; managed hosted path is primary" in the handoff.

## Neon Database

Prerequisites:

- Neon project and production branch exist.
- Operator can create/delete branches and view connection strings.
- Runtime `DATABASE_URL` and optional `DATABASE_URL_UNPOOLED` are stored in `.env` and fanned to
  Vercel/GitHub/Cloud Run targets per the manifest.
- Operator-only `NEON_API_KEY` and `NEON_PROJECT_ID` stay in `.env` or the secret manager only.

Proof commands:

```powershell
neon projects list
neon branches list --project-id $env:NEON_PROJECT_ID --output json
pnpm db:check
pnpm ops:health -- --section freshness
pnpm ops:backup -- --dry-run
```

For restore proof, follow `docs/operations/backups.md`; it requires `RESTORE_DATABASE_URL` pointed
at a fresh throwaway branch.

Operator-gated: `pnpm db:check` and health checks require a verified target `DATABASE_URL`. Do not
use a mutable unknown `.env` database for destructive or restore commands.

## Cloudflare R2 Storage

Prerequisites:

- Cloudflare account and R2 bucket exist.
- Runtime names set in `.env`: `STORAGE_PROVIDER=s3`, `S3_ENDPOINT`, `S3_REGION`, `S3_BUCKET`,
  `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_FORCE_PATH_STYLE`.
- Operator-only `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` stay out of app runtime.
- Bucket is private by default; backup prefix is restricted if `BACKUP_S3_*` is used.

Proof commands:

```powershell
wrangler whoami
wrangler r2 bucket list
wrangler r2 bucket info <bucket> --json
pnpm ops:backup -- --dry-run --upload-r2
```

Optional S3 API metadata proof, with credentials supplied through environment variables only:

```powershell
aws s3 ls s3://<bucket> --endpoint-url <r2-s3-endpoint>
```

Operator-gated: bucket list/info needs Cloudflare auth; real upload proof requires AWS CLI plus R2
S3 credentials.

## Upstash Queue And Rate-Limit Store

Prerequisites:

- Upstash Redis database exists.
- Runtime names set in `.env`: `QUEUE_PROVIDER=redis`, `REDIS_URL`, and/or
  `UPSTASH_REDIS_REST_URL` plus `UPSTASH_REDIS_REST_TOKEN`.
- Upstash developer credentials stay operator-only and are not listed in the manifest as runtime
  payload.

Proof commands:

```powershell
upstash redis list
upstash redis get --db-id <db-id> --hide-credentials
upstash redis stats --db-id <db-id>
pnpm ops:health -- --section providers
```

Runtime token proof must avoid printing token values. If testing the REST endpoint, use a temporary
operator shell and do not echo the token:

```powershell
Invoke-RestMethod "$env:UPSTASH_REDIS_REST_URL/ping" -Method Post -Headers @{ Authorization = "Bearer $env:UPSTASH_REDIS_REST_TOKEN" }
```

Operator-gated: Upstash API/CLI access is required for database metadata and stats.

## Vertex AI And Gemini LLM

Prerequisites:

- Google Cloud project has billing/quota posture confirmed for the budget in
  `docs/operations/resource-budget.md`.
- Vertex AI is enabled in the chosen project/region.
- Runtime names set in `.env`: `LLM_PROVIDER=vertex`, `LLM_MODEL`, `LLM_PRIMARY=vertex`,
  `VERTEX_PROJECT` or `GCLOUD_PROJECT_ID`, `VERTEX_LOCATION`, and either ADC or
  `GOOGLE_SERVICE_ACCOUNT_KEY`.
- `GEMINI_API_KEY` is set as fallback when the Gemini API key path is used.

Proof commands:

```powershell
gcloud auth list
gcloud config list
gcloud services list --enabled --filter="name:aiplatform.googleapis.com"
gcloud ai models list --region=$env:VERTEX_LOCATION --project=$env:GCLOUD_PROJECT_ID --limit=5
pnpm ops:health -- --section providers
```

Gemini API-key proof is operator-gated because a real request consumes quota. If run, keep prompts
short and do not print keys:

```powershell
uv run python -c "import os; assert os.environ.get('GEMINI_API_KEY'); print('GEMINI_API_KEY present')"
```

Operator-gated: live Vertex/Gemini calls require authenticated GCloud/AI Studio access and may use
quota or credits.

## GCloud Cloud Run, Cloud Build, Artifact Registry, And Secret Manager

Prerequisites:

- `GCLOUD_PROJECT_ID` and `CLOUD_RUN_REGION` are set.
- APIs enabled: Cloud Run, Cloud Build, Artifact Registry, Secret Manager, IAM, and Vertex AI when
  using Vertex.
- Runtime service account and GitHub deploy service account exist with least privilege documented in
  `docs/operations/pipeline-cd.md`.
- `GCP_SA_KEY` is stored manually as a GitHub Actions secret for CI build/roll; it is not fanned by
  `scripts/ops/secrets-fanout.mjs`.

Proof commands:

```powershell
gcloud auth list
gcloud config get project
gcloud services list --enabled --filter="name:(run.googleapis.com OR cloudbuild.googleapis.com OR artifactregistry.googleapis.com OR secretmanager.googleapis.com)"
gcloud run jobs describe intercal-pipeline --region $env:CLOUD_RUN_REGION --project $env:GCLOUD_PROJECT_ID
gcloud builds list --project $env:GCLOUD_PROJECT_ID --limit=5
gcloud artifacts repositories list --location $env:CLOUD_RUN_REGION --project $env:GCLOUD_PROJECT_ID
gcloud secrets list --filter="name:intercal-" --project $env:GCLOUD_PROJECT_ID
pnpm ops:deploy-cloud-run -- --dry-run
```

Small live execution proof, only when a verified throwaway DB or production-safe cap is approved:

```powershell
gcloud run jobs execute intercal-pipeline --region $env:CLOUD_RUN_REGION --project $env:GCLOUD_PROJECT_ID --args="run-all,--max-documents,5" --wait
```

Operator-gated: real deploys, secret updates, and job executions require authenticated GCloud access.

## GitHub Actions

Prerequisites:

- `gh` is authenticated to GitHub.
- Repo is `JamiStudio/intercal`.
- Actions are enabled.
- Runtime secrets and variables are present by name only; values are never printed.
- Workflows `.github/workflows/pipeline.yml` and `.github/workflows/deploy-cloud-run.yml` are
  visible and dispatchable.

Proof commands:

```powershell
gh auth status
gh repo view JamiStudio/intercal --json nameWithOwner,visibility,defaultBranchRef
gh workflow list --repo JamiStudio/intercal
gh secret list --repo JamiStudio/intercal
gh variable list --repo JamiStudio/intercal
pnpm ops:secrets-fanout -- --target github --dry-run
```

Safe workflow-dispatch proof requires a throwaway Neon branch DSN and should not print it. Use the
Actions UI or set it in the current shell, then run:

```powershell
gh workflow run pipeline.yml --repo JamiStudio/intercal -f mode=run-all -f max_documents=5 -f database_url_override="$env:RESTORE_DATABASE_URL"
```

Operator-gated: live workflow dispatch writes to the target database named by the selected secret or
override. Use a throwaway branch for proof.

## Vercel

Prerequisites:

- Vercel project is linked to the GitHub repo.
- Root Directory is `packages/dashboard`.
- Domain `intercal.jami.studio` is attached for production Intercal traffic.
- `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, optional `VERCEL_TEAM_ID`/`VERCEL_TEAM_SLUG`, and optional
  `VERCEL_DOMAIN` remain operator-lane.
- App-runtime names required by the dashboard/API/MCP are fanned from `.env`.

Proof commands:

```powershell
vercel whoami
vercel project ls
vercel project inspect intercal
vercel inspect https://intercal.jami.studio
vercel env ls production
vercel env ls preview
vercel domains ls
vercel domains inspect jami.studio
pnpm ops:secrets-fanout -- --target vercel --dry-run
Invoke-WebRequest https://intercal.jami.studio/api/openapi.json -UseBasicParsing
Invoke-WebRequest https://intercal.jami.studio/api/v1/freshness?topic_or_entity=MCP%20protocol -UseBasicParsing
```

Current proof from 2026-06-07:

- `vercel whoami` returned `studio-jami`.
- `vercel project ls` listed project `intercal` with latest production URL
  `https://intercal.jami.studio`.
- `vercel project inspect intercal` reported Root Directory `packages/dashboard`, Node.js `24.x`,
  Framework Preset `Next.js`, and owner `jami-studio`.
- `vercel inspect https://intercal.jami.studio` reported a Ready production deployment and aliases
  for the official domain plus existing compatibility URLs.

Operator-gated: environment value listing requires Vercel project/team access and must not print
secret values. Live smoke checks require a deployed URL.

## Secret Fan-Out Handoff

At the end of account setup, leave this state for later agents:

- `.env` exists locally and is ignored.
- `.env.example` contains every required name and no value.
- `scripts/ops/secrets.manifest.json` maps runtime names to `vercel`, `github`, and/or `cloudrun`
  targets and maps operator-only names to `targets: []`.
- Vercel and GitHub target secret names match the manifest.
- Cloud Run Job sensitive values are in Secret Manager as `intercal-<NAME>` versions managed by
  `scripts/ops/deploy-cloud-run.mjs`.
- A password-manager or host secret-store entry names the human owner, recovery email/MFA posture,
  and rotation date for each provider. Do not duplicate those details in this repo.

Proof commands:

```powershell
pnpm ops:secrets-fanout -- --dry-run
pnpm ops:secrets-fanout -- --target vercel --dry-run
pnpm ops:secrets-fanout -- --target github --dry-run
pnpm ops:deploy-cloud-run -- --dry-run
git check-ignore .env
git diff --check
```

## Rotation Policy

Rotate at the source, then fan out. Never patch one target by hand unless the owning runbook says
that target cannot be fanned.

Routine rotation:

- Rotate high-power operator credentials at least every 90 days or immediately after a maintainer
  leaves.
- Rotate app-runtime credentials after a suspected leak, provider warning, public log exposure, or
  accidental inclusion in a command argument.
- Rotate database credentials before/after risky restore drills if a credential was shared outside
  the normal secret store.

Rotation flow:

1. Disable scheduled writers when the credential controls the database, queue, storage, or worker
   runtime.
2. Rotate in the provider console/API.
3. Update only `.env` or the host secret store.
4. Run secret fan-out or the provider-specific script:

```powershell
pnpm ops:secrets-fanout
pnpm ops:deploy-cloud-run
```

5. Trigger any required redeploy/restart so runtime processes pick up the new value.
6. Run the proof command for the provider and a small Intercal smoke check.
7. Revoke/destroy old provider tokens or secret versions once the new path passes.
8. Record date, provider, names rotated, proof commands, and unavailable checks in the external
   operator handoff. Do not record values.

Provider-specific notes:

- Neon `DATABASE_URL` / `DATABASE_URL_UNPOOLED`: follow the detailed flow in
  `docs/operations/secrets.md`.
- R2: create a new R2 API token/S3 credential pair, update `S3_ACCESS_KEY_ID` /
  `S3_SECRET_ACCESS_KEY`, fan to worker targets, then revoke the old key.
- Upstash: reset the Redis password/token, update `REDIS_URL` and/or `UPSTASH_REDIS_REST_*`, fan to
  worker targets, then verify queue/rate-limit health.
- Vercel: rotate `VERCEL_TOKEN` in the operator lane, then dry-run and run the fan-out.
- GitHub Actions: rotate `gh` auth/PAT and `GCP_SA_KEY` manually in repo secrets when required.
- GCloud: rotate service account keys only when a key-based path is still required. Prefer
  Workload Identity/ADC for Cloud Run runtime, as documented in `docs/operations/pipeline-cd.md`.

## Setup Closeout Checklist

- [ ] CLI baseline proof commands passed or exact missing CLIs were recorded.
- [ ] Domain/DNS/TLS proof passed or domain ownership is explicitly missing.
- [ ] SSH/VPS proof passed or VPS is explicitly not provisioned.
- [ ] Neon project/branch proof passed against a verified DB target.
- [ ] R2 bucket proof passed.
- [ ] Upstash database proof passed.
- [ ] Vertex/Gemini auth posture proof passed.
- [ ] Cloud Run/Cloud Build/Artifact Registry/Secret Manager proof passed.
- [ ] GitHub Actions secret/workflow proof passed.
- [ ] Vercel env/domain proof passed.
- [ ] Secret fan-out dry-run passed for Vercel and GitHub; Cloud Run deploy dry-run passed.
- [ ] Handoff names owner, missing access, unavailable live calls, and next rotation dates outside
      this repo.

## Reference Baseline

The command shapes above were checked against official provider docs on 2026-06-06: Vercel CLI
environment commands, Google Cloud CLI auth/config reference, GitHub CLI manual, Cloudflare R2
Wrangler commands, Neon CLI branch commands, and Upstash CLI/Redis docs. Re-verify those external
command shapes before durable changes to this runbook.
