# Workstream 8 domain routing proof

- Documented the verified `intercal.jami.studio` Vercel project, root directory, aliases, Cloudflare
  DNS target, TLS state, and official-domain route smoke results.
- Added secret-safe operator notes for the Cloudflare DNS-read permission gap and the non-blocking
  `jami.studio` apex/`www` routing warning.
- Added a pass-2 confirmation note that authoritative DNS, TLS, REST/OpenAPI/docs, and MCP smokes
  still pass while Cloudflare dashboard/API record metadata remains operator-gated in this shell.
