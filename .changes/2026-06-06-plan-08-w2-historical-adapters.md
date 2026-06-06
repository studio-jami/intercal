# Plan 08 Workstream 2 Historical Adapter Foundation

- Added historical source adapters for registry releases, arXiv, RSS/Atom feeds, Wikidata SPARQL
  batches, and MediaWiki revisions behind the shared `SourcePort`.
- Registered the historical adapters in the shared source registry and extended GitHub releases
  with date-window filtering, per-repo historical pagination cursors, and a per-run page cap.
- Hardened pass-2 adapter behavior so invalid configured date bounds fail closed, bounded
  historical registry/RSS/GitHub runs exclude undated records, GitHub repo identifiers are validated
  before request construction, and Wikidata SPARQL cursor query hashes are stable across processes.
- Hardened pass-3 quiet-confirmation behavior so arXiv and MediaWiki revision adapters locally
  enforce historical date windows, suppress undated or identifier-less historical records, cap
  MediaWiki per-page pagination, and keep registry cursor ordering deterministic for same-timestamp
  releases.
- Hardened pass-4 quiet-check behavior so arXiv suppresses dated entries without stable Atom IDs,
  Wikidata SPARQL batches reset stale offsets when the query changes, and SPARQL rows without
  stable `item`/`qid` identifiers do not produce offset-derived source documents.
- Added focused Python tests for adapter registration, source-policy ingestion, SSRF rejection,
  cursor behavior, and normalized `RawDocument` output.
