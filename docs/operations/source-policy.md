# Source Policy & SSRF Protection

How Intercal decides what it may **fetch**, **store**, and **expose** for each source, and how the
substrate guards every externally-influenced outbound fetch against Server-Side Request Forgery
(SSRF). This is the durable runbook for **Plan 04 Workstream 2 (Source policy & trust)**.

> Scope: the ingestion fetch path (`services/ingest`, `services/shared` source adapters) and the
> response-assembly layer (`packages/core` query layer). The contract boundary (TypeSpec →
> generated) and the port/adapter seams are unchanged.

## Source policy model

Every source row (`sources`, migration `0004`) carries an explicit license/redistribution posture.
The pipeline enforces it at two points: **before store** (ingestion) and **before expose**
(response assembly). The relevant columns:

| Column | Meaning | Enforced where |
| --- | --- | --- |
| `license_spdx` / `license_notes` | The source's license (SPDX id if known) and free-text caveats. | Operator-set; informs the booleans below. |
| `redistribution_allowed` | May we store the **raw bytes** (object storage) and redistribute them? | Ingestion: raw archival only happens when `true` (see below). |
| `summary_allowed` | May the substrate emit a **derived summary/snippet** of the body? | Response assembly: gates evidence body snippets. |
| `citation_only` | Body must never be exposed — cite the URL/title only. | Ingestion (no full text stored) **and** response assembly. |
| `rate_limit_requests_per_minute` | Per-source politeness cap. | Operator/adapter guidance; adapters carry a User-Agent and the caller handles upstream 429s. |

Policy is **snapshotted onto each `source_documents` row at ingest time**
(`redistribution_allowed`, `summary_allowed`, `citation_only`) so it travels with the immutable
evidence unit. A later edit to the parent source row cannot retroactively change what was already
stored or how an already-stored document may be served — the snapshot is the authority for that row.

### Enforcement: before store (ingestion)

`services/ingest/jobs.py::ingest_source`:

- **`citation_only` sources** — full body text is **not** persisted (`cleaned_text` is stored
  `NULL`); only metadata (URL, title, timestamps, hashes) is kept. The document is citable but its
  body never enters the store.
- **`redistribution_allowed = false`** — the raw bytes are **not** written to object storage (R2).
  Only the derived row (subject to the rules above) is kept. Raw archival is gated on
  `storage is not None and redistribution_allowed`.
- The policy booleans are denormalised onto the `source_documents` row in the same insert.

### Enforcement: before expose (response assembly)

`packages/core/queries.ts`:

- **Evidence body snippets** are gated by `bodySnippetAllowed(policy)`, a pure, unit-tested
  predicate: a snippet (a derived summary of the body) is emitted **only** when the document is
  **not** `citation_only` **and** `summary_allowed` is `true`. Otherwise the response falls back to
  the **title** (citation metadata), which carries no body text. The truth table:

  | `citation_only` | `summary_allowed` | Body snippet? |
  | --- | --- | --- |
  | false | true | yes |
  | false | false | no (title only) |
  | true | (any) | no (title only) |

- The deterministic delta digest (`packages/core/delta.ts`) is built from already-extracted,
  structurally-stored claim fields and never re-derives text from a restricted source body, so it
  carries no additional source-text exposure beyond the citations it already grounds.

## SSRF protection for fetched URLs

Source endpoints are configured in `sources.adapter_config` (e.g. `wikidata_api_url`,
`github_api_url`). Today those are operator-set; once a **user-submitted source URL** surface exists
(Plan 04 W4 feedback / Plan 06), the same fetch path will carry attacker-influenced URLs. Any such
fetch is funnelled through the reusable guard in **`services/shared/intercal_shared/ssrf.py`** — a
port/util that owns one cross-cutting safety concern and contains no provider logic.

The guard is aligned with the **OWASP SSRF Prevention Cheat Sheet**. It enforces:

- **Scheme allowlist** — only `http` / `https`. `file:`, `gopher:`, `ftp:`, `data:`, `ldap:`, … are
  rejected.
- **Resolve-then-validate every IP** — the hostname is resolved to **all** A/AAAA records and
  **every** address is checked. A public hostname whose DNS answer is a private IP (the classic
  DNS-rebinding setup) is rejected; if any one of multiple addresses is blocked, the host is blocked.
- **Blocked ranges** (deny, with a precise reason): loopback (`127.0.0.0/8`, `::1`), the
  **cloud-metadata** address `169.254.169.254` (AWS/GCP/Azure IMDS, reported as `cloud_metadata`),
  link-local (`169.254.0.0/16`, `fe80::/10`), private (RFC1918 `10/8`·`172.16/12`·`192.168/16`,
  IPv6 ULA `fc00::/7`), multicast (`224.0.0.0/4`, `ff00::/8`), unspecified (`0.0.0.0` / `::`),
  reserved, and anything not globally routable. IPv6 that **embeds** an IPv4 (`::ffff:10.0.0.1`,
  6to4, Teredo) is unwrapped and the inner address re-checked.
- **Alternate IP encodings** — decimal (`2130706433`), hex (`0x7f000001`), octal (`0177.0.0.1`) and
  short forms are canonicalised (via `ipaddress` / `inet_aton`) to the real address before the
  range check, so a numeric-encoding bypass of a textual blocklist is closed. (The OS resolver also
  canonicalises these — this is defence-in-depth.)
- **DNS-rebinding defence (connection pinning)** — `create_guarded_client()` returns an
  `httpx.AsyncClient` whose transport validates the URL, then **pins the socket to the exact IP
  that passed validation** (preserving the `Host` header and TLS SNI to the real hostname). The OS
  never gets a second chance to resolve the name to a different address, closing the
  resolve→connect TOCTOU window.
- **Redirect re-validation** — the guarded client does **not** auto-follow redirects;
  `guarded_get()` follows them manually, **re-validating each `Location`** through the same policy up
  to a bounded hop count, so a validated public URL cannot 302 the fetcher to a private/metadata
  address.
- **Timeouts & size caps** — per-request connect/read timeouts and a `max_bytes` body cap enforced
  automatically by the guarded client's pinning transport on **every** response (an over-cap
  `Content-Length` is rejected up front, and the response stream is wrapped so a lying/absent
  `Content-Length` still trips the cap mid-body — covering the buffered `.json()`/`.text` reads the
  adapters use), so a hostile or pathological endpoint cannot hang a worker or exhaust memory. The
  standalone streaming `read_capped` helper remains for callers driving a borrowed client.

### Where it is wired

The built-in source adapters (`source_wikidata.py`, `source_github.py`) pre-validate their
configured endpoint URLs through the guard **before any fetch fires**, and — when they own their
HTTP client — build it via `create_guarded_client()` so every connection they open is IP-pinned and
scheme-checked. A blocked URL surfaces as a `SourceFetchError` (the run is recorded failed; nothing
is fetched). A **borrowed** client (injected by a caller or a test transport) is trusted as the
caller's responsibility, but the configured URLs are still pre-validated.

### Deferred seam (no fake)

There is **no user-submitted-URL ingestion endpoint yet** — the public REST/MCP surface is
read-only (Plan 04 W4 owns feedback; Plan 06 owns the interactive submission UX). The SSRF guard is
implemented now as the reusable util at the fetch boundary so that surface, when added, simply
validates the submitted URL through `resolve_and_validate()` / `create_guarded_client()` before
persisting or fetching it. Until then the seam is left clean — not stubbed with fake behaviour.

## Verification

- Unit: `uv run pytest services/shared/tests/test_ssrf.py` — the full hostile matrix (loopback,
  `0.0.0.0`, `169.254.169.254`, RFC1918, `::1`, `fc00::/7`, `fe80::/10`, decimal/octal/hex
  encodings, DNS→private, mixed records, redirect→private, oversized body) plus legitimate public
  URLs and the adapter-integration rejections.
- Unit: `pnpm --filter @intercal/core test` (`source-policy.test.ts`) — the `bodySnippetAllowed`
  truth table.
- Live (run locally with network): a real `https://api.github.com` fetch succeeds through the
  IP-pinning guarded client while `169.254.169.254`, `127.0.0.1` and `10.0.0.1` are blocked at the
  socket boundary.
