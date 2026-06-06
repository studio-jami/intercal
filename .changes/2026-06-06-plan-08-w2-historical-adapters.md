# Plan 08 Workstream 2 Historical Adapter Foundation

- Added historical source adapters for registry releases, arXiv, RSS/Atom feeds, Wikidata SPARQL
  batches, and MediaWiki revisions behind the shared `SourcePort`.
- Registered the historical adapters in the shared source registry and extended GitHub releases
  with date-window filtering, per-repo historical pagination cursors, and a per-run page cap.
- Hardened pass-2 adapter behavior so invalid configured date bounds fail closed, bounded
  historical registry/RSS/GitHub runs exclude undated records, GitHub repo identifiers are validated
  before request construction, and Wikidata SPARQL cursor query hashes are stable across processes.
- Added focused Python tests for adapter registration, source-policy ingestion, SSRF rejection,
  cursor behavior, and normalized `RawDocument` output.
