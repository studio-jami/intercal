-- 0016_embeddings.sql
-- Embedding tables for documents, chunks, entities, and claims.
--
-- EMBEDDING INVARIANTS:
--   1. Every embedding row MUST carry `model` (text) and `dim` (int) — they identify the vector space.
--   2. Changing the model or dimension requires a new embedding run (old rows become stale).
--      A different dimension model MUST use a new table or column — vectors from different
--      spaces cannot be mixed in the same HNSW index.
--   3. Embeddings are provider-agnostic; the model column is the only coupling.
--   4. Default model: bge-small-en-v1.5 (384 dims), stored as halfvec(384).
--      For 768-dim models (bge-base, nomic-embed-v2): add a halfvec(768) column/table.
--
-- HNSW indexes use halfvec_cosine_ops (cosine similarity).
-- halfvec = 2-byte float storage; halves index size vs full float4 vector at no material recall loss.
--
-- DESIGN NOTE: Three separate tables (document, chunk, entity, claim) because:
--   - each owner type has different cardinality and query patterns
--   - separate HNSW indexes allow model-version migration without downtime on unaffected tables
--   - a "different dimension model requires a new column/table" is trivially satisfied per table

-- ---------------------------------------------------------------------------
-- document_embeddings
-- Embedding of the full cleaned_text of a source document (or a truncated window).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_embeddings (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     uuid        NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,

    -- Vector space identity — MUST always be filled
    model           text        NOT NULL,   -- e.g. 'bge-small-en-v1.5', 'nomic-embed-text-v2'
    dim             integer     NOT NULL,   -- number of dimensions, e.g. 384

    -- Default embedding column: halfvec(384) for bge-small-en-v1.5.
    -- IMPORTANT: A different-dimension model requires a new column or table.
    -- Do NOT insert a 768-dim vector into this column.
    embedding       halfvec(384) NOT NULL,

    created_at      timestamptz NOT NULL DEFAULT now(),

    -- One embedding per (document, model) to support multi-model scenarios
    CONSTRAINT uq_document_embedding UNIQUE (document_id, model)
);

CREATE INDEX IF NOT EXISTS idx_doc_embeddings_document  ON document_embeddings (document_id);
CREATE INDEX IF NOT EXISTS idx_doc_embeddings_hnsw
    ON document_embeddings USING hnsw (embedding halfvec_cosine_ops);

COMMENT ON TABLE document_embeddings IS
    'Embeddings for source_documents. model + dim identify the vector space. '
    'Default: bge-small-en-v1.5 / halfvec(384). '
    'A different-dimension model requires a new column or table — do NOT mix vector spaces.';

COMMENT ON COLUMN document_embeddings.model IS
    'Embedding model identifier. Changing the model invalidates existing vectors. '
    'Store the exact versioned model string used at embedding time.';

-- ---------------------------------------------------------------------------
-- chunk_embeddings
-- Embedding of individual document chunks (primary retrieval unit).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        uuid        NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,

    model           text        NOT NULL,
    dim             integer     NOT NULL,
    embedding       halfvec(384) NOT NULL,

    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_chunk_embedding UNIQUE (chunk_id, model)
);

CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_chunk   ON chunk_embeddings (chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
    ON chunk_embeddings USING hnsw (embedding halfvec_cosine_ops);

COMMENT ON TABLE chunk_embeddings IS
    'Embeddings for document_chunks. Primary unit for semantic retrieval. '
    'Default: bge-small-en-v1.5 / halfvec(384). Same model/dim rules as document_embeddings.';

-- ---------------------------------------------------------------------------
-- entity_embeddings
-- Embedding of entity canonical names + descriptions (for entity search and resolution).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_embeddings (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       uuid        NOT NULL REFERENCES entities(id) ON DELETE CASCADE,

    model           text        NOT NULL,
    dim             integer     NOT NULL,
    embedding       halfvec(384) NOT NULL,

    -- The text that was embedded (snapshot; entity descriptions may change)
    embedded_text   text        NOT NULL,

    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_entity_embedding UNIQUE (entity_id, model)
);

CREATE INDEX IF NOT EXISTS idx_entity_embeddings_entity ON entity_embeddings (entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_embeddings_hnsw
    ON entity_embeddings USING hnsw (embedding halfvec_cosine_ops);

COMMENT ON TABLE entity_embeddings IS
    'Embeddings for canonical entities (name + description text). '
    'Used for semantic entity search and entity resolution clustering. '
    'Default: bge-small-en-v1.5 / halfvec(384).';

-- ---------------------------------------------------------------------------
-- claim_embeddings
-- Embedding of claim normalized_text (for semantic claim search and dedup).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim_embeddings (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id        uuid        NOT NULL REFERENCES claims(id) ON DELETE CASCADE,

    model           text        NOT NULL,
    dim             integer     NOT NULL,
    embedding       halfvec(384) NOT NULL,

    -- The text that was embedded
    embedded_text   text        NOT NULL,

    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_claim_embedding UNIQUE (claim_id, model)
);

CREATE INDEX IF NOT EXISTS idx_claim_embeddings_claim   ON claim_embeddings (claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_embeddings_hnsw
    ON claim_embeddings USING hnsw (embedding halfvec_cosine_ops);

COMMENT ON TABLE claim_embeddings IS
    'Embeddings for claim normalized_text. Used for semantic claim search, near-duplicate detection, '
    'and contradiction candidate generation. Default: bge-small-en-v1.5 / halfvec(384).';
