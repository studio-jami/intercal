# Workstream 8 Pass 1

Thread: `019ea05e-b300-7052-b922-4e26eb0f8cb6`

Commit: `f4bfdf2a1cdbe2e63b5a90e455a614f34d26a7b6`

Subject: `docs(operations): record intercal domain routing proof`

Gate: B

Pass 1 verified the official Intercal domain topology and updated operations docs:

- Vercel project `studio-jami/intercal` uses root directory `packages/dashboard`.
- `intercal.jami.studio` is attached to the Ready production deployment.
- Cloudflare authoritative nameservers answer `intercal.jami.studio` as CNAME
  `25b8236304cda166.vercel-dns-017.com` with TTL `600`.
- TLS is live for `CN=intercal.jami.studio`.
- `/`, `/docs`, `/api/openapi.json`, `/api/v1/freshness`, and route-appropriate MCP checks passed
  against the official domain.
- The Cloudflare DNS-read permission gap and non-blocking Jami Studio apex warning are documented
  without storing secrets.

The pass changed 4 files with 146 insertions and 29 deletions. The work is docs/changelog-only, but
it records production-meaningful provider proof and runbook status, so the coordinator gate is B.
Mandatory pass 2 was dispatched to thread `019ea06c-3eed-79f2-bcb3-4ba431700d5c`.

Verification reported:

- `pnpm docs:check`
- `git diff --check`
- `git diff --cached --check`
- touched/staged diff secret-pattern scans

Unrelated deleted `mcps/Neon/tools/*.json` files remained dirty and were not staged or touched.
