Plan 04 W8 fixes the operator health CLI to accept pnpm's `--` argument separator.

- `scripts/ops/health.mjs` now ignores standalone `--`, matching the backup, deploy, and
  secret-fanout CLIs and making documented commands such as
  `pnpm ops:health -- --section freshness` parse correctly.
- Verification used parser/help/SQL paths only; no provider writes or live secret values were used.
