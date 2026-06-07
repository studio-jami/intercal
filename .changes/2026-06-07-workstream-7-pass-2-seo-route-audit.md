# Workstream 7 pass 2 SEO route audit

- Tracked the public `/coverage` dashboard route that SEO metadata, sitemap, docs inventory, and
  AI exports already reference.
- Narrowed coverage-output ignores so a real dashboard route named `coverage` is not hidden, and
  hardened `pnpm docs:check` to fail when manifest-owned dashboard routes are git-ignored.
