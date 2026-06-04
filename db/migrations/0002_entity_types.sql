-- 0002_entity_types.sql
-- Strict reference table for entity types.
-- Populated by seeds/0001_entity_types.sql; never free text in entity rows.
-- Add new types here (with a migration) when the taxonomy genuinely expands.

CREATE TABLE IF NOT EXISTS entity_types (
    id          text        PRIMARY KEY,              -- e.g. 'person', 'organization'
    label       text        NOT NULL,                 -- human-readable display label
    description text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE entity_types IS
    'Stable reference table for canonical entity type identifiers. '
    'FK-enforced by entities.type_id. Add new types via migration + seed, never free text.';
