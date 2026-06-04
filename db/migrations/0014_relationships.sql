-- 0014_relationships.sql
-- Relationships are typed temporal edges between entities, derived from claims and evidence.
--
-- Every relationship:
--   - references relationship_types (strict FK — no free-text type)
--   - carries bitemporal columns: valid_from / valid_until / recorded_at
--   - carries confidence and source document IDs
--   - may carry a properties jsonb for type-specific attributes
--
-- Overlap exclusivity for exclusive relationship types (is_exclusive = true in relationship_types)
-- is enforced at the application layer: the pipeline must check for overlapping active intervals
-- before inserting. The relationship_types.is_exclusive flag documents the intent.

CREATE TABLE IF NOT EXISTS relationships (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Type (FK to strict reference table)
    type_id             text        NOT NULL REFERENCES relationship_types(id) ON DELETE RESTRICT,

    -- Subject and object entities
    subject_entity_id   uuid        NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    object_entity_id    uuid        NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,

    -- Bitemporal: valid time in the world
    valid_from          timestamptz,            -- when this edge became true (NULL = unknown/open start)
    valid_until         timestamptz,            -- when it stopped being true (NULL = still active)

    -- Recorded time: when Intercal first recorded this edge
    recorded_at         timestamptz NOT NULL DEFAULT now(),

    -- Confidence in this relationship assertion
    confidence          numeric(3,2) NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0 AND 1),

    -- Source provenance
    source_document_ids uuid[]      NOT NULL DEFAULT '{}', -- fast lookup; canonical is relationship_claim_sources
    claim_ids           uuid[]      NOT NULL DEFAULT '{}', -- claims that produced this relationship

    -- Type-specific attributes (e.g. title for person_holds_role, deal_value for acquisition)
    properties          jsonb       NOT NULL DEFAULT '{}',

    -- Lifecycle
    is_active           boolean     NOT NULL DEFAULT true,
    is_deprecated       boolean     NOT NULL DEFAULT false,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_relationship_different CHECK (subject_entity_id <> object_entity_id),
    CONSTRAINT chk_relationship_valid_time CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
);

-- Core query paths
CREATE INDEX IF NOT EXISTS idx_relationships_type_id        ON relationships (type_id);
CREATE INDEX IF NOT EXISTS idx_relationships_subject        ON relationships (subject_entity_id, type_id);
CREATE INDEX IF NOT EXISTS idx_relationships_object         ON relationships (object_entity_id, type_id);
CREATE INDEX IF NOT EXISTS idx_relationships_active         ON relationships (subject_entity_id, object_entity_id, type_id)
    WHERE is_active = true AND is_deprecated = false;
-- Point-in-time query: edges valid at a given moment
CREATE INDEX IF NOT EXISTS idx_relationships_valid_time     ON relationships (valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_relationships_recorded_at    ON relationships (recorded_at DESC);

COMMENT ON TABLE relationships IS
    'Typed temporal edges between canonical entities. Derived from claims. '
    'type_id is FK-enforced against relationship_types. '
    'valid_from/valid_until = world time; recorded_at = when Intercal learned it. '
    'Overlap exclusivity for exclusive types is enforced at application layer (see relationship_types.is_exclusive).';
