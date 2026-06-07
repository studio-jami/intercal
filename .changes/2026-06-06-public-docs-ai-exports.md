# Public docs and AI exports

- Added source-owned public docs pages, a Mintlify-compatible `docs.json`, same-origin `/docs`
  rendering, and `/llms.txt` plus `/llms-full.txt` exports for agent ingestion.
- Added `pnpm docs:check` to verify docs route inventory, generated OpenAPI availability, checked
  REST/SDK/MCP examples, Mintlify navigation coverage, links, and AI export drift.
- Hardened `pnpm docs:check` to compare the manifest against the actual dashboard page-route tree,
  exact public Markdown inventory, all generated OpenAPI paths in REST docs, generated OpenAPI REST
  example path/query parameters, and the shared MCP V1 tool inventory. `llms.txt` now includes the
  `/docs` index route alongside source-owned docs pages.
- Removed missing placeholder logo paths from the Mintlify config and added missing-asset detection
  to the public docs checker.
