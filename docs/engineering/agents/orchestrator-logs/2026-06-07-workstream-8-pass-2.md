# Workstream 8 Pass 2

Thread: `019ea06c-3eed-79f2-bcb3-4ba431700d5c`

Scope: strict Workstream 8 domain-routing audit only. Workstreams 1-7 remained closed, and
Workstream 9 release audit was not implemented.

Result: C - quiet tests/docs/cleanup.

Evidence:

- `vercel whoami` returned `studio-jami`.
- `vercel project inspect intercal` reported project `studio-jami/intercal`, owner `jami-studio`,
  Root Directory `packages/dashboard`, Node.js `24.x`, and Next.js framework settings.
- `vercel project ls` listed `intercal` with latest production URL
  `https://intercal.jami.studio`.
- `vercel inspect https://intercal.jami.studio` reported a Ready production deployment for project
  `intercal` with the official domain plus existing compatibility aliases.
- `vercel domains inspect jami.studio` still warned about the parent apex; this remains external
  Jami Studio site routing and is not an Intercal subdomain blocker.
- `Resolve-DnsName -Name jami.studio -Type NS` returned Cloudflare nameservers
  `irena.ns.cloudflare.com` and `elliott.ns.cloudflare.com`.
- Both authoritative Cloudflare nameservers returned
  `intercal.jami.studio CNAME 25b8236304cda166.vercel-dns-017.com` with TTL `600`.
- The Vercel DNS target resolved to Vercel edge addresses.
- TLS presented `CN=intercal.jami.studio`, issued by Let's Encrypt, valid 2026-06-06 through
  2026-09-04.
- Official-domain smokes returned `200` for `/`, `/docs`, `/api/openapi.json`, and
  `/api/v1/freshness?topic_or_entity=MCP%20protocol`.
- Plain GET `/api/mcp` returned expected `406`; Streamable HTTP initialize POST returned `200`.
- An SDK smoke from `packages/mcp-server` listed all six MCP tools and successfully called
  `get_entity` and `search_evidence`.

Unavailable or non-blocking:

- `wrangler` was not available on PATH or through `pnpm exec`, and no Cloudflare token env was
  present in this shell. Cloudflare dashboard/API-side record metadata remains operator-gated; the
  authoritative DNS proof was still verified directly through Cloudflare nameservers.
- `node scripts/dev/verify-mcp.mjs https://intercal.jami.studio/api/mcp` failed because the root
  script location cannot resolve `@modelcontextprotocol/sdk`; the documented package-local SDK
  fallback passed.
- The broader env-gated live MCP-server test failed on the point-in-time REST/SDK assertion that
  expected `unverified` but received `supported`. That is a corpus/query-semantics dependency for
  later audit work, not a Workstream 8 domain-routing blocker.

No app code, generated contracts, Cloudflare Workers/Pages compute, Workstream 9 release audit, or
unrelated Jami Studio routing was changed. The pre-existing deleted `mcps/Neon/tools/*.json` files
remained untouched and unstaged.
