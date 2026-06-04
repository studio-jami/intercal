-- 0007_document_chunks.sql
-- Documents are split into overlapping chunks for embedding and retrieval.
-- Each chunk references its parent document and carries its span within it.

CREATE TABLE IF NOT EXISTS document_chunks (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         uuid        NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,

    -- Position within the document
    chunk_index         integer     NOT NULL,             -- 0-based ordinal
    char_offset_start   integer,                          -- character offset of chunk start in cleaned_text
    char_offset_end     integer,

    chunk_text          text        NOT NULL,
    token_count         integer,                          -- estimated token count for budget management

    metadata            jsonb       NOT NULL DEFAULT '{}',-- chunker-specific metadata (strategy, overlap, etc.)
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_document_chunk UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks (document_id, chunk_index);

COMMENT ON TABLE document_chunks IS
    'Sub-document spans produced by the chunking step. Each chunk is the atomic unit for embedding. '
    'chunk_index is 0-based and unique per document.';
