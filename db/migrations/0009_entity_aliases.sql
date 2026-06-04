-- 0009_entity_aliases.sql
-- Alternative names, abbreviations, and former names for entities.
-- Used for mention matching and search disambiguation.

CREATE TABLE IF NOT EXISTS entity_aliases (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   uuid        NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias       text        NOT NULL,
    alias_type  text        NOT NULL DEFAULT 'name',  -- 'name', 'abbreviation', 'former_name', 'nickname', 'label'
    language    text        NOT NULL DEFAULT 'en',    -- BCP 47
    is_primary  boolean     NOT NULL DEFAULT false,   -- hint: preferred alternative display name
    source      text,                                 -- where this alias came from, e.g. 'wikidata', 'extraction'
    created_at  timestamptz NOT NULL DEFAULT now(),

    -- Prevent inserting the same alias string twice for the same entity
    CONSTRAINT uq_entity_alias UNIQUE (entity_id, lower(alias), language)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity_id   ON entity_aliases (entity_id);
-- Search: find entity by alias (case-insensitive)
CREATE INDEX IF NOT EXISTS idx_entity_aliases_lower_alias ON entity_aliases (lower(alias));
CREATE INDEX IF NOT EXISTS idx_entity_aliases_fts         ON entity_aliases USING gin(to_tsvector('english', alias));

COMMENT ON TABLE entity_aliases IS
    'Alternative names and labels for entities. Used for mention matching, search, and display. '
    'Unique per (entity_id, lower(alias), language).';
