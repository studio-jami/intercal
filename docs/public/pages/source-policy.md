# Source Policy

Source policy controls what Intercal may fetch, store, and expose.

## Source-row posture

Every source row carries license and redistribution posture:

- `license_spdx`
- `license_notes`
- `redistribution_allowed`
- `summary_allowed`
- `citation_only`
- `rate_limit_requests_per_minute`

The policy booleans are snapshotted onto each `source_documents` row at ingest time. That snapshot travels with the immutable evidence unit and controls exposure.

## Before store

Citation-only sources do not persist full body text. Sources without redistribution approval do not archive raw bytes to object storage. Intercal can still retain source metadata and cited derived facts where policy allows.

## Before expose

Public responses may show citation metadata and policy-allowed derived snippets. They must not show raw source bodies. Restricted body text is neither emitted as a snippet nor searchable as an existence oracle.

## Fetch safety

Built-in source adapters validate configured endpoints through the shared SSRF guard before fetch. The guard allows only `http` and `https`, rejects private/metadata/link-local/reserved destinations, pins connections to validated IPs, revalidates redirects, and enforces timeouts and body-size caps.

## Public page rule

Dashboard pages consume the served shape from the query layer. They do not reimplement source policy and do not invent fallback source text when a citation body is unavailable.
