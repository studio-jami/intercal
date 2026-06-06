-- 0025_source_documents_summary_policy.sql
-- Plan 04 W2 (Source policy & trust): snapshot `summary_allowed` onto source_documents.
--
-- source_documents already snapshots `redistribution_allowed` and `citation_only` from the
-- parent source at ingest time (migration 0006) so policy travels with the immutable evidence
-- unit and a later source-row edit cannot retroactively change what was already stored/served.
-- `summary_allowed` was missing from that snapshot, so the response-assembly layer had no
-- per-document signal to honor a "citation OK, derived summary/snippet NOT OK" source. This
-- adds it, defaulting TRUE to match the parent `sources.summary_allowed` default and so existing
-- rows keep their prior (permissive) behaviour until re-ingested.

ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS summary_allowed boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN source_documents.summary_allowed IS
    'Source-policy snapshot at ingest time (denormalised from sources.summary_allowed). '
    'When false, the substrate must not emit a derived snippet/summary of this document body; '
    'citation (url/title) is still permitted unless citation_only also restricts it.';
