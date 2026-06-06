# Plan 04 W2 Source Policy & Trust — SSRF fetch guard + summary-policy enforcement

Date: 2026-06-06
Type: security
Services: intercal-shared, intercal-ingest, @intercal/core
Schema: db/migrations/0025_source_documents_summary_policy.sql

## Summary

Closes Plan 04 Workstream 2 (Source policy & trust). Builds on Plan 02 W1 (sources already carried
`redistribution_allowed`/`citation_only` and raw archival was already gated): adds a reusable
SSRF-safe fetch guard for every externally-influenced outbound URL, and closes the one remaining
source-policy enforcement gap (`summary_allowed` was defined and seeded but never honored). Stays in
the W2 lane; the TypeSpec→generated contract boundary and the port/adapter seams are untouched;
later-plan work (user-submission endpoint, source allowlist UI, citation-laundering detection) is
left as a clean seam, not faked.

## Change

- **SSRF fetch guard (new): `services/shared/intercal_shared/ssrf.py`.** A port/util behind which
  all externally-influenced HTTP fetches funnel, aligned with the OWASP SSRF Prevention Cheat Sheet:
  - scheme allowlist (`http`/`https` only);
  - resolve the hostname to **all** A/AAAA records and validate **every** IP — a public name whose
    DNS answer is private (DNS rebinding) is rejected;
  - blocks loopback, `0.0.0.0`/`::`, the cloud-metadata address `169.254.169.254` (AWS/GCP/Azure),
    link-local (`169.254.0.0/16`, `fe80::/10`), RFC1918, IPv6 ULA `fc00::/7`, multicast, reserved,
    and non-global; unwraps IPv4-mapped / 6to4 / Teredo IPv6 to re-check the embedded IPv4;
  - canonicalises decimal/octal/hex IPv4 encodings so a numeric-encoding bypass is closed;
  - **pins the connection to the validated IP** (preserving Host + TLS SNI) via
    `create_guarded_client()` to defeat the resolve→connect rebinding window;
  - **re-validates every redirect hop** (`guarded_get`); no transport auto-redirects;
  - per-request timeouts + a `max_bytes` body cap (`read_capped`).
- **Adapter wiring.** `source_wikidata.py` and `source_github.py` pre-validate their configured
  endpoint URLs (rejecting a malicious `adapter_config` URL with `SourceFetchError` before any
  fetch) and, when they own their HTTP client, build it via `create_guarded_client()`.
- **`summary_allowed` enforcement (gap fix).** Migration `0025` snapshots `summary_allowed` onto
  `source_documents` (default `true`); `ingest_source` writes it; `packages/core` adds the pure,
  exported `bodySnippetAllowed()` gate so an evidence body snippet is emitted only when the document
  is not `citation_only` **and** `summary_allowed` is true — otherwise the response falls back to
  the title (citation metadata, no body text).

## Verification

- `uv run pytest services/shared/tests/test_ssrf.py` — full hostile matrix (loopback, `0.0.0.0`,
  `169.254.169.254`, RFC1918, `::1`, `fc00::/7`, `fe80::/10`, decimal/octal/hex, DNS→private, mixed
  records, redirect→private, oversized body) + legitimate public URLs + adapter rejections.
- `pnpm --filter @intercal/core test` (`source-policy.test.ts`) — the body-exposure truth table.
- Full gate green: `pnpm py:lint` / `py:typecheck` (0 errors) / `py:test` (419 passed);
  `pnpm lint` / `typecheck` / `test` (all packages). Migration `0025` applied to the live Neon DB
  (`db:check`: 25 applied).
- Live: a real `https://api.github.com` fetch succeeds through the IP-pinning guarded client while
  `169.254.169.254` (cloud_metadata), `127.0.0.1` (loopback) and `10.0.0.1` (private) are blocked at
  the socket boundary.
