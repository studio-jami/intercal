-- 0019_subscriptions.sql
-- Subscriptions record interest in entities, topics, relationship types, claim patterns, or sources.
-- They support polling (freshness check) and will support webhooks in a later plan volume.
--
-- This is a meaningful product differentiator: agents can be notified when knowledge changes
-- instead of asking broad refresh questions repeatedly.

CREATE TABLE IF NOT EXISTS subscriptions (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Subscriber identity
    -- api_key_id links to api_keys when auth is implemented; may be NULL for system subscriptions
    api_key_id          uuid,       -- FK to api_keys added after that table is created

    -- What is subscribed to (at least one target must be set)
    topic_id            uuid        REFERENCES topics(id) ON DELETE CASCADE,
    entity_id           uuid        REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type_id text       REFERENCES relationship_types(id) ON DELETE CASCADE,
    source_id           uuid        REFERENCES sources(id) ON DELETE CASCADE,
    claim_pattern       jsonb,      -- structured filter pattern (subject/predicate/object constraints)

    -- Delivery preferences
    min_importance      numeric(3,2) NOT NULL DEFAULT 0.0 CHECK (min_importance BETWEEN 0 AND 1),
    token_budget        integer,
    delivery_method     text        NOT NULL DEFAULT 'polling'
                            CHECK (delivery_method IN ('polling', 'webhook')),
    webhook_url         text,       -- set for webhook delivery
    webhook_secret_hash text,       -- HMAC secret, stored as hash (never plaintext)

    -- State
    is_active           boolean     NOT NULL DEFAULT true,
    last_delivered_at   timestamptz,
    last_checked_at     timestamptz,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- At least one target must be specified
    CONSTRAINT chk_subscription_has_target
        CHECK (
            topic_id IS NOT NULL OR
            entity_id IS NOT NULL OR
            relationship_type_id IS NOT NULL OR
            source_id IS NOT NULL OR
            claim_pattern IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_api_key   ON subscriptions (api_key_id) WHERE api_key_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_subscriptions_topic     ON subscriptions (topic_id) WHERE topic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_subscriptions_entity    ON subscriptions (entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_subscriptions_active    ON subscriptions (is_active, last_checked_at NULLS FIRST)
    WHERE is_active = true;

COMMENT ON TABLE subscriptions IS
    'Interest registrations for entities, topics, relationship types, sources, or claim patterns. '
    'Supports polling now; webhook delivery planned for plan 04. '
    'webhook_secret_hash stores the HMAC secret hash — never the plaintext value.';
