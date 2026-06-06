# Plan 07 W3 — Pipeline CD on GitHub Actions (scheduled batch)

Date: 2026-06-05
Type: feat (ops/ci)
Packages: .github/workflows, docs/operations

## Summary

The Intercal pipeline now runs itself on a schedule, for free, on the public repo's Actions
minutes — the default pipeline runner (decision D11 / Plan 07 W3). `.github/workflows/pipeline.yml`
was rewritten to drive the real portable orchestrator (`uv run intercal-pipeline run-all` /
`run --source-id`) instead of the old per-service stub, with the schedule **enabled** now that the
Plan 02 pipeline runs end-to-end.

## Changes

- **`pipeline.yml` (rewrite):**
  - **Schedule enabled:** `cron: "17 */6 * * *"` — 6-hourly per `docs/operations/resource-budget.md`
    (`INGEST_CRON=0 */6 * * *`), minute offset off `:00` to avoid GitHub's top-of-hour schedule drops.
  - **Real CLI:** `setup-uv@v8` (was v5) + `uv sync --all-packages --frozen` + `uv run intercal-pipeline`.
  - **`workflow_dispatch` inputs:** `mode` (run-all|run), `source_id`, `max_documents`, `no_embeddings`,
    and `database_url_override` (safe-test seam → throwaway Neon branch).
  - **Safety:** `concurrency {group: intercal-pipeline, cancel-in-progress: false}` (no overlap; finish
    in-flight, queue next), `timeout-minutes: 30`, least-privilege `permissions: {contents: read}`.
  - **Secrets/auth:** all app-runtime env wired by NAME from the W1 fan-out; Vertex ADC built from
    `GOOGLE_SERVICE_ACCOUNT_KEY` (SA JSON → `chmod 600` `$RUNNER_TEMP` file → `GOOGLE_APPLICATION_CREDENTIALS`),
    Gemini fallback via `GEMINI_API_KEY`. Budget knobs overridable via repo `vars.*`.
  - **Observability:** the CLI `PipelineRunHealth` JSON (counts + per-stage errors + status) is teed to
    `$GITHUB_STEP_SUMMARY`; the job exits non-zero on a `failed` run. No secret value is ever printed.
- **`docs/operations/pipeline-cd.md` (new):** durable runbook — schedule, manual inputs, budget/safety
  controls, secrets/auth, observability, the verify procedure, and the Cloud Run (W4) relationship.

## Verification

- **actionlint 1.7.7:** `pipeline.yml` clean (exit 0).
- **Actual Actions run:** dispatched via `gh workflow run` against a disposable Neon branch
  (`database_url_override`, small `max_documents`) → green; real rows landed on the branch. Followed by a
  small **prod** re-run confirming idempotency (no duplicate canonical records). No secret value appears
  in any tracked file, log, or step summary; the throwaway branch was deleted after the test.

## Notes

- Cloud Run Jobs (Plan 07 W4) are a separate, on-demand path over the *same* `intercal-pipeline` CLI
  (`docker/workers.Dockerfile`); this workstream does not build that path.
- The repo is public → Actions minutes are unlimited; scheduled workflows fire from `main` and
  auto-disable only after 60 days of repo inactivity (not a concern for an active program).
