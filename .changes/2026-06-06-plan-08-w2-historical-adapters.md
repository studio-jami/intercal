# Plan 08 Workstream 2 Historical Adapter Foundation

- Added historical source adapters for registry releases, arXiv, RSS/Atom feeds, Wikidata SPARQL
  batches, and MediaWiki revisions behind the shared `SourcePort`.
- Registered the historical adapters in the shared source registry and extended GitHub releases
  with date-window filtering, per-repo historical pagination cursors, and a per-run page cap.
- Added focused Python tests for adapter registration, source-policy ingestion, SSRF rejection,
  cursor behavior, and normalized `RawDocument` output.
