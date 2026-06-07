# Workstream 6 Pass 2

- Agent: current fresh-context pass
- Status: complete
- Classification: B - completion plus focused drift-check hardening

## Changed files

- `docs.json`
- `llms.txt`
- `packages/dashboard/lib/public-docs.ts`
- `scripts/docs/check-public-docs.mjs`
- `docs/roadmaps/2026-06-06-intercal-public-launch-corpus-docs-domain-plan.md`
- `.changes/2026-06-06-public-docs-ai-exports.md`

## Result

Pass 2 kept the pass 1 public docs IA, `/docs` rendering, generated OpenAPI placement, and AI
exports intact. The remaining implementation gap was drift-control strength:

- `pnpm docs:check` now compares the manifest against the actual dashboard page-route tree.
- The check now compares the manifest against the exact Markdown files under `docs/public/pages`.
- REST docs must mention every generated OpenAPI path.
- REST example request paths and query parameter names are checked against generated OpenAPI.
- MCP docs are checked against the shared V1 tool inventory.
- Mintlify asset paths in `docs.json` fail if the referenced files do not exist.

The stale `/logo/light.svg` and `/logo/dark.svg` references were removed from `docs.json`; no
repo-owned logo assets exist yet, and Mintlify's current docs list `logo` as optional.

## Verification

- `pnpm docs:check` passed.
- `git diff --check` passed.
- `pnpm --filter @intercal/dashboard typecheck` passed.
- `pnpm lint` passed with the existing Biome schema-version info only.

No unavailable commands or Workstream 6 blockers were found. Pre-existing unrelated
`mcps/Neon/tools/*.json` deletions remain dirty and were not staged.
