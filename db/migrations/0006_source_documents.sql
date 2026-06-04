-- 0006_source_documents.sql
-- Source documents are immutable evidence units: articles, API records, papers, release notes, etc.
-- Once inserted, a document row must not be mutated (content_hash is the immutability anchor).
-- Raw content lives in object storage; cleaned text and metadata live here.

CREATE TABLE IF NOT EXISTS source_documents (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           uuid        NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    ingestion_run_id    uuid        REFERENCES ingestion_runs(id) ON DELETE SET NULL,

    -- Deduplication invariant: the SHA-256 hex of the normalised cleaned body.
    -- UNIQUE ensures the pipeline cannot insert the same content twice.
    content_hash        text        NOT NULL UNIQUE,

    -- Identity
    external_id         text,                             -- source's own identifier (URL, DOI, wikidata QID, etc.)
    url                 text,                             -- canonical URL if known
    title               text,
    language            text        NOT NULL DEFAULT 'en',-- BCP 47 language tag

    -- Timestamps — both stored because queries may filter on either
    published_at        timestamptz,                      -- when the source published this document
    ingested_at         timestamptz NOT NULL DEFAULT now(),-- when Intercal first saw it

    -- Content storage
    -- cleaned_text holds the normalized, extraction-ready body (may be truncated for restricted sources).
    -- For citation_only sources, cleaned_text may be NULL and only metadata is stored.
    cleaned_text        text,
    raw_storage_key     text,                             -- object-storage key for the raw blob (may be NULL)
    content_length      integer,                          -- byte length of cleaned_text for budget estimates

    -- Classification
    document_type       text,                             -- 'article', 'api_record', 'paper_abstract', etc.
    topics_hint         text[],                           -- adapter-extracted topic tags (not canonical)

    -- Source policy snapshot at ingest time (denormalised from sources for immutability)
    redistribution_allowed boolean   NOT NULL DEFAULT false,
    citation_only       boolean      NOT NULL DEFAULT false,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Core query paths
CREATE INDEX IF NOT EXISTS idx_source_documents_source_id     ON source_documents (source_id, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_documents_published_at  ON source_documents (published_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_source_documents_ingested_at   ON source_documents (ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_documents_external_id   ON source_documents (source_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_source_documents_ingestion_run ON source_documents (ingestion_run_id) WHERE ingestion_run_id IS NOT NULL;

COMMENT ON TABLE source_documents IS
    'Immutable evidence units. content_hash (SHA-256 of cleaned body) enforces deduplication. '
    'Raw content is in object storage; cleaned_text is the extraction-ready normalised copy.';

COMMENT ON COLUMN source_documents.content_hash IS
    'SHA-256 hex of the normalised cleaned body. UNIQUE constraint = global dedup invariant.';
