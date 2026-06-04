-- 0017_topics.sql
-- Topics are normalized query surfaces that map to entities, claims, documents,
-- relationships, and summaries.
--
-- Topics may be: user-defined, system-derived, or materialized from repeated demand.
-- They are useful for cached digests but are NOT the source of truth.
--
-- topic_memberships: join table linking topics to their member entities, claims, etc.

-- ---------------------------------------------------------------------------
-- topics
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topics (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                text        NOT NULL UNIQUE,    -- stable URL-safe identifier
    name                text        NOT NULL,
    description         text,
    topic_type          text        NOT NULL DEFAULT 'user_defined'
                            CHECK (topic_type IN ('user_defined', 'system_derived', 'materialized')),

    -- Freshness: when the topic graph was last updated
    last_updated_at     timestamptz,
    freshness_score     numeric(3,2) CHECK (freshness_score BETWEEN 0 AND 1),

    is_public           boolean     NOT NULL DEFAULT true,
    is_archived         boolean     NOT NULL DEFAULT false,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topics_slug      ON topics (slug);
CREATE INDEX IF NOT EXISTS idx_topics_active    ON topics (last_updated_at DESC NULLS LAST)
    WHERE is_archived = false;

COMMENT ON TABLE topics IS
    'Normalized query surfaces: named collections of entities, claims, documents, and relationships. '
    'Topics are NOT canonical facts — they are convenient views for digest generation and subscriptions.';

-- ---------------------------------------------------------------------------
-- topic_memberships
-- Links topics to their member resources (polymorphic via member_type + member_id).
-- member_type: 'entity', 'claim', 'document', 'relationship'
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topic_memberships (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id        uuid        NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    member_type     text        NOT NULL
                        CHECK (member_type IN ('entity', 'claim', 'document', 'relationship')),
    member_id       uuid        NOT NULL,   -- FK validated at application layer (polymorphic)
    relevance_score numeric(3,2) CHECK (relevance_score BETWEEN 0 AND 1),
    added_by        text        NOT NULL DEFAULT 'system',  -- 'system', 'user', 'pipeline'
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_topic_membership UNIQUE (topic_id, member_type, member_id)
);

CREATE INDEX IF NOT EXISTS idx_topic_memberships_topic     ON topic_memberships (topic_id, member_type);
CREATE INDEX IF NOT EXISTS idx_topic_memberships_member    ON topic_memberships (member_type, member_id);

COMMENT ON TABLE topic_memberships IS
    'Polymorphic join table: links topics to entities, claims, documents, or relationships. '
    'member_id FK is validated at application layer due to polymorphism.';
