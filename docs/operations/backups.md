# Backups & Restore Proof

Intercal's canonical store is plain Postgres + pgvector. Recovery has two lanes:

- **Neon branch / point-in-time restore:** fastest operator recovery for the hosted production
  database. Neon branches are isolated copy-on-write clones, and Neon can create or restore a
  branch at a selected point within the project's restore window.
- **Portable second copy:** `pg_dump` custom-format archives, optionally uploaded to an
  S3-compatible bucket such as Cloudflare R2. This proves the data can leave Neon and restore into
  any compatible Postgres target with pgvector.

The backup archive contains canonical graph data and evidence metadata. Treat it as sensitive:
store it in a restricted bucket/prefix, do not attach public object policies, and never print
database URLs, access keys, tokens, or signed URLs.

References: [Neon branching and point-in-time restore](https://neon.com/docs/introduction/point-in-time-restore),
[Neon branch restore API](https://api-docs.neon.tech/reference/restoreprojectbranch),
[PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[PostgreSQL pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

## Required Tools

- `pg_dump` and `pg_restore` from PostgreSQL client tools.
- Node dependencies installed (`pnpm install`) for the read-only heartbeat.
- Optional R2 upload: AWS CLI configured by environment variables from `.env`; the script maps
  `S3_*` / `BACKUP_S3_*` names to `AWS_*` for the child process.
- Neon operator access for branch creation, PITR, and branch deletion. Keep `NEON_API_KEY` and
  `NEON_PROJECT_ID` in the operator lane only.

## Environment Names

Source database:

- `DATABASE_URL_UNPOOLED` preferred for dumps and long-running restore operations.
- `DATABASE_URL` fallback.

Restore proof target:

- `RESTORE_DATABASE_URL` must point at a fresh throwaway Neon branch or equivalent target database.
  Never set it to production.

Optional second-copy upload:

- `BACKUP_S3_BUCKET` defaults to `S3_BUCKET`.
- `BACKUP_S3_PREFIX` defaults to `database-dumps`.
- `BACKUP_S3_ENDPOINT` defaults to `S3_ENDPOINT`.
- `BACKUP_S3_REGION` defaults to `S3_REGION` or `auto`.
- `BACKUP_S3_ACCESS_KEY_ID` / `BACKUP_S3_SECRET_ACCESS_KEY` default to `S3_ACCESS_KEY_ID` /
  `S3_SECRET_ACCESS_KEY`.

These names are operator-only. They are not fanned into Vercel, GitHub Actions, or Cloud Run
runtime env unless a future backup scheduler explicitly owns that target.

## Create A Portable Backup

Dry run:

```powershell
pnpm ops:backup -- --dry-run --upload-r2
```

Create a local custom-format archive:

```powershell
pnpm ops:backup
```

Create and upload the archive to the configured R2/S3 backup prefix:

```powershell
pnpm ops:backup -- --upload-r2
```

The script runs:

```text
pg_dump --format=custom --no-owner --no-privileges --file <dump> <source-url>
```

It writes under `.backups/` by default. `.backups/` must remain gitignored; do not stage dumps.
The optional upload uses `aws s3 cp <dump> s3://<bucket>/<prefix>/<dump> --endpoint-url <endpoint>`
with credentials passed through process env, never command arguments.

## Restore-Proof Runbook

1. Create a fresh Neon branch from the production branch in the Neon console, Neon CLI, or Neon API.
   For a PITR drill, create the branch from the selected past timestamp within the restore window.
2. Copy the branch's direct Postgres connection string into local `RESTORE_DATABASE_URL`. Do not
   print it in chat, docs, shell transcripts, or logs.
3. Restore a dump and run the heartbeat:

```powershell
pnpm ops:restore-proof -- --dump .backups\intercal-YYYY-MM-DDTHH-MM-SS-sssZ.dump
```

Or pass the target explicitly without writing it into `.env`:

```powershell
node scripts/ops/backup-restore.mjs restore-proof --dump .backups\intercal-YYYY-MM-DDTHH-MM-SS-sssZ.dump --target-url "<throwaway-branch-dsn>"
```

The restore command is:

```text
pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction --exit-on-error --dbname <target-url> <dump>
```

4. The script then runs a read-only heartbeat against the restored target. It verifies:

- pgvector is installed.
- migrations are recorded.
- seeded sources exist.
- source documents, claims, entities, relationships, and fact versions are present.
- at least one claim has evidence provenance back to a source document.
- at least one fact version has the bitemporal recorded-at axis plus a valid subject pointer.

5. Delete the throwaway branch after the proof. Keep the dump only for the intended retention window.

Run the heartbeat against an already-restored target without restoring again:

```powershell
node scripts/ops/backup-restore.mjs restore-proof --dump .backups\intercal-YYYY-MM-DDTHH-MM-SS-sssZ.dump --skip-restore
```

Or against any configured target:

```powershell
node scripts/ops/backup-restore.mjs health --target-url "<target-dsn>"
```

## Neon PITR Recovery

For an operational incident where the production branch is damaged:

1. Stop writers first: pause scheduled GitHub Actions pipeline runs and avoid Cloud Run Job
   executions while recovery is in progress.
2. In Neon, create a branch from the last known-good timestamp or restore an affected branch to a
   selected timestamp. Prefer creating a separate recovery branch first so production remains
   inspectable until the recovered state is verified.
3. Point `RESTORE_DATABASE_URL` at the recovery branch and run:

```powershell
node scripts/ops/backup-restore.mjs health
```

4. If the recovery branch is the chosen state, promote by updating the one source secret
   (`DATABASE_URL` / `DATABASE_URL_UNPOOLED`) and re-running the secret fan-out and redeploy steps
   in `docs/operations/secrets.md`.
5. Re-enable writers after REST, MCP, and the pipeline smoke checks pass on the recovered branch.

## Cadence

- Run a `pg_dump` second-copy backup after production-meaningful schema or data-pipeline changes and
  before risky operator work.
- Run a restore proof into a throwaway branch after backup script changes, DB migrations, or Neon
  branch/PITR changes.
- Use R2 for the second copy when the bucket and token are available. R2 has zero egress in the
  current topology; still keep dump cadence bounded by storage growth and the resource budget.

## Failure Handling

- Missing `pg_dump` / `pg_restore`: install PostgreSQL client tools and re-run.
- Restore target is not fresh: use a new branch. The restore uses `--clean --if-exists`, but a
  disposable target avoids accidentally mixing restored and pre-existing data.
- Heartbeat fails on missing graph rows: the dump restored, but it does not contain the live fixture
  heartbeat shape. Re-run a capped pipeline proof on a throwaway branch, then take a new backup.
- Upload fails: keep the local dump, fix the R2/S3 operator env, and re-run with `--upload-r2`.
