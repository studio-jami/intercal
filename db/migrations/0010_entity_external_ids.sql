-- 0010_entity_external_ids.sql
-- Stable identifiers from external systems (Wikidata QID, ORCID, LEI, GitHub org, DOI, etc.).
-- These are the primary high-confidence signals for entity resolution.

CREATE TABLE IF NOT EXISTS entity_external_ids (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       uuid        NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    namespace       text        NOT NULL,   -- e.g. 'wikidata', 'orcid', 'lei', 'github_org', 'doi', 'ror'
    external_id     text        NOT NULL,   -- the identifier value within the namespace
    url             text,                   -- canonical URL for this external record, if applicable
    confidence      numeric(3,2) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    is_verified     boolean     NOT NULL DEFAULT false,
    source          text,                   -- where this mapping came from
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    -- One external ID per namespace per entity
    CONSTRAINT uq_entity_external_id UNIQUE (entity_id, namespace, external_id)
);

-- Lookup: find entity by external namespace+id (e.g. during resolution)
CREATE INDEX IF NOT EXISTS idx_entity_external_ids_namespace ON entity_external_ids (namespace, external_id);
CREATE INDEX IF NOT EXISTS idx_entity_external_ids_entity    ON entity_external_ids (entity_id);

COMMENT ON TABLE entity_external_ids IS
    'Stable identifiers from external authority systems. Primary high-confidence input for entity resolution. '
    'Unique per (entity_id, namespace, external_id).';
