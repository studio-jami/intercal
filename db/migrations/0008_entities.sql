-- 0008_entities.sql
-- Entities are canonical things: persons, organizations, roles, offices, products, places, events,
-- concepts, legislation, technical artifacts, sources, datasets, and jurisdictions.
--
-- ROLE / OFFICE SEPARATION:
--   "CEO of OpenAI" and "US Secretary of State" are NOT aliases for their current holder.
--   They are entities of type 'role' or 'office', with temporal occupancy captured in relationships.
--   This is a hard architectural requirement for historical correctness.
--
-- MERGE / DEPRECATION:
--   When two entities are merged, the loser is marked deprecated (is_deprecated = true,
--   merged_into_id → winner). The winner absorbs the loser's aliases and external IDs.
--   Merge history lives in entity_merge_events; this supports full reversal.

CREATE TABLE IF NOT EXISTS entities (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Type (FK to strict reference table — never free text)
    type_id             text        NOT NULL REFERENCES entity_types(id) ON DELETE RESTRICT,

    -- Display
    canonical_name      text        NOT NULL,
    description         text,

    -- Denormalized current state (updated by pipeline; source of truth is fact_versions)
    current_state       jsonb       NOT NULL DEFAULT '{}',

    -- Importance signal for prioritisation
    importance_score    numeric(5,4) NOT NULL DEFAULT 0.0, -- 0.0–1.0

    -- Temporal provenance
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_updated_at     timestamptz NOT NULL DEFAULT now(),

    -- Merge / deprecation metadata
    -- When is_deprecated = true, this entity has been absorbed into merged_into_id.
    -- Queries should filter WHERE is_deprecated = false unless explicitly traversing merge history.
    is_deprecated       boolean     NOT NULL DEFAULT false,
    merged_into_id      uuid        REFERENCES entities(id) ON DELETE SET NULL,
    deprecated_at       timestamptz,
    deprecation_reason  text,       -- 'merged', 'duplicate', 'error', 'split', etc.

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Core query paths
CREATE INDEX IF NOT EXISTS idx_entities_type_id           ON entities (type_id);
CREATE INDEX IF NOT EXISTS idx_entities_canonical_name    ON entities (lower(canonical_name));
CREATE INDEX IF NOT EXISTS idx_entities_is_deprecated     ON entities (is_deprecated) WHERE is_deprecated = false;
CREATE INDEX IF NOT EXISTS idx_entities_importance        ON entities (importance_score DESC) WHERE is_deprecated = false;
CREATE INDEX IF NOT EXISTS idx_entities_merged_into       ON entities (merged_into_id) WHERE merged_into_id IS NOT NULL;
-- Full-text search on canonical name
CREATE INDEX IF NOT EXISTS idx_entities_name_fts          ON entities USING gin(to_tsvector('english', canonical_name));

COMMENT ON TABLE entities IS
    'Canonical things: persons, orgs, roles, offices, products, places, events, concepts, legislation, '
    'technical artifacts, sources, datasets, jurisdictions. '
    'Roles/offices are separate entity types — not aliases for their occupants. '
    'is_deprecated + merged_into_id support reversible merges; see entity_merge_events.';

COMMENT ON COLUMN entities.current_state IS
    'Denormalized snapshot of the current known state. The canonical source of truth '
    'for historical state is fact_versions.';
