-- 0003_relationship_types.sql
-- Strict reference table for typed temporal edges.
-- Populated by seeds/0002_relationship_types.sql.
-- Every row in `relationships` must FK into this table.

CREATE TABLE IF NOT EXISTS relationship_types (
    id                  text        PRIMARY KEY,          -- e.g. 'person_holds_role'
    label               text        NOT NULL,             -- e.g. 'Person Holds Role'
    description         text,
    -- Whether the relationship is directional (subject → object).
    -- All defined types are directional; kept explicit for future undirected edges.
    is_directional      boolean     NOT NULL DEFAULT true,
    -- Whether at most one active interval may exist per (subject, object) pair.
    -- Enforced at application layer; stored here as declarative intent.
    is_exclusive        boolean     NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE relationship_types IS
    'Strict vocabulary of typed temporal edges. FK-enforced by relationships.type_id. '
    'Add new types via migration + seed.';
