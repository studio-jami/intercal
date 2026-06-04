-- 0012_mentions.sql
-- Mentions are text spans in source documents that appear to refer to an entity, role, office,
-- product, place, concept, event, law, or source.
--
-- Mentions are NOT entities. They are evidence candidates.
-- This separation prevents weak extraction from polluting canonical entity records.

CREATE TABLE IF NOT EXISTS mentions (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         uuid        NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    chunk_id            uuid        REFERENCES document_chunks(id) ON DELETE SET NULL,

    -- The span within the document
    text_span           text        NOT NULL,   -- raw text of the mention
    char_offset_start   integer,
    char_offset_end     integer,

    -- Extraction metadata
    extractor           text        NOT NULL,   -- 'spacy_ner', 'llm_extract_v1', 'rule_regex', etc.
    extraction_confidence numeric(3,2) NOT NULL DEFAULT 0.0 CHECK (extraction_confidence BETWEEN 0 AND 1),

    -- Proposed type from extraction (not yet resolved to a canonical entity type)
    proposed_type       text,       -- 'PERSON', 'ORG', 'GPE', 'ROLE', etc. (extractor-specific)

    -- Resolution: link to canonical entity once resolved (NULL = unresolved)
    entity_id           uuid        REFERENCES entities(id) ON DELETE SET NULL,
    resolution_status   text        NOT NULL DEFAULT 'unresolved'
                            CHECK (resolution_status IN ('unresolved', 'resolved', 'rejected', 'ambiguous')),
    resolved_at         timestamptz,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mentions_document_id       ON mentions (document_id);
CREATE INDEX IF NOT EXISTS idx_mentions_entity_id         ON mentions (entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mentions_unresolved        ON mentions (document_id, resolution_status)
    WHERE resolution_status = 'unresolved';
CREATE INDEX IF NOT EXISTS idx_mentions_chunk_id          ON mentions (chunk_id) WHERE chunk_id IS NOT NULL;

COMMENT ON TABLE mentions IS
    'Text spans extracted from documents that may refer to an entity. '
    'Mentions are evidence candidates, not canonical records. '
    'entity_id is set only after the resolution pipeline confirms the link.';
