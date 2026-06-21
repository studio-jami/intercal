# Revive CI verification

- Restored TypeScript package runtime type contexts for SDK, API, and MCP server checks.
- Hardened CI and `pnpm verify` to build generated contracts/shared/core/SDK/API/MCP outputs before consumers typecheck.
- Installed all Python workspace packages and extras in CI so strict Pyright and pytest see adapter dependencies.
- Kept `docs/_standards` as a dev symlink while excluding it from Biome traversal.
- Pinned `js-yaml` to the compatible patched 4.2.0 release for contracts generation.
- Forced composite package builds so stale incremental state cannot mask missing `dist` outputs.
- Sorted embedded generated contract JSON so `contracts:check` is deterministic across platforms.
- Made CLI option assertions independent of Rich's terminal help rendering.
