-- 0023_source_documents_normalized.sql
-- W2 (Plan 02): Track normalisation completion on source_documents.
-- normalized_at: timestamp when normalize_document last succeeded for this row.
-- chunk_count:   how many document_chunks were produced (0 = not yet chunked; NULL = pending).
-- Both columns are NULL until normalize_document runs for the first time.

ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS normalized_at  timestamptz,
    ADD COLUMN IF NOT EXISTS chunk_count    integer;

CREATE INDEX IF NOT EXISTS idx_source_documents_normalized_at
    ON source_documents (normalized_at NULLS FIRST)
    WHERE normalized_at IS NULL;

COMMENT ON COLUMN source_documents.normalized_at IS
    'Timestamp when normalize_document last completed for this document (NULL = not yet normalised).';

COMMENT ON COLUMN source_documents.chunk_count IS
    'Number of document_chunks produced by the last normalisation run (NULL = not yet chunked).';
