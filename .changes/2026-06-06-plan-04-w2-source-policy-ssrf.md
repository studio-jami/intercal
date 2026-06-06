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
  - per-request timeouts + a `max_bytes` body cap enforced **automatically on every response** by
    the guarded client's pinning transport (rejects an over-cap `Content-Length` up front and wraps
    the response stream so a lying/absent `Content-Length` still trips the cap mid-body, protecting
    the buffered `.json()`/`.text` reads the adapters use); the streaming `read_capped` helper
    remains for callers driving a borrowed client.
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
  `169.254.169.254`, RFC1918, `::1`, `fc00::/7`, `fe80::/10`, decimal/octal/hex/short-form/overlong,
  DNS→private, DNS→IPv4-mapped-metadata, mixed records, userinfo-in-URL, redirect→private,
  redirect→`file://`, invalid port, oversized streamed body + oversized `Content-Length`,
  within-cap pass, transport-level private block) + legitimate public URLs + adapter rejections.
  **52 tests** (41 → 52 in this audit pass).
- `pnpm --filter @intercal/core test` (`source-policy.test.ts`) — the body-exposure truth table.
- Full gate green: `pnpm py:lint` / `py:typecheck` (0 errors) / shared `py:test` (138 passed);
  `pnpm --filter @intercal/core test` (93 passed). Migration `0025` applied to the live Neon DB
  (`db:check`: 25 applied).
- Live SSRF: a real `https://api.github.com` fetch succeeds through the IP-pinning guarded client
  while `169.254.169.254` (cloud_metadata), `127.0.0.1` (loopback) and `10.0.0.1` (private) are
  blocked at the socket boundary.
- Live source-policy snippet gate (`node --env-file=.env scripts/dev/verify-source-policy.mjs`,
  rolled-back transaction against the production Neon branch): `summary_allowed` column present
  (0025 live); a permissive document emits a body snippet, while `summary_allowed=false` and
  `citation_only=true` documents fall back to title-only with **no body leak**; all probe rows
  rolled back (nothing persisted). 5/5.

## Audit-2 (2026-06-06, second fresh-context pass)

Adversarial SSRF-bypass hunt + source-policy end-to-end re-audit. One genuine gap found and fixed:
the documented `max_bytes` body cap was implemented only in the standalone `read_capped` helper,
which the adapters never call (they use buffered `client.get().json()`), so a hostile/pathological
configured endpoint could exhaust worker memory. Moved enforcement into the guarded client's
pinning transport so the cap is automatic on **every** outbound response (Content-Length pre-check
+ mid-stream wrapper). Added regression + new adversarial tests (above). Source policy confirmed
honored end-to-end on both the Python store path (snapshot written at ingest) and the TS serve path
(`bodySnippetAllowed` gates `searchEvidence`; `delta.ts`/`verify.ts` never touch `cleaned_text`),
proven live. No SSRF bypass found in scheme/redirect/encoding/userinfo/IPv6-embedding vectors.
