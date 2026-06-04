-- 0018_digests.sql
-- Digests are agent-facing syntheses generated from evidence and graph state.
-- They are cached by topic/entity/query, date range, and token budget.
-- Digests are DELIVERY ARTIFACTS, not canonical facts — never used as evidence.
--
-- Key invariant: every digest stores the evidence IDs and claim IDs it was built from,
-- so staleness can be detected and citations can be verified.

CREATE TABLE IF NOT EXISTS digests (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What this digest covers (at least one of topic_id / entity_id / query_text must be set)
    topic_id            uuid        REFERENCES topics(id) ON DELETE SET NULL,
    entity_id           uuid        REFERENCES entities(id) ON DELETE SET NULL,
    query_text          text,                       -- for ad-hoc query-driven digests

    -- Date range for the digest content
    from_date           timestamptz,
    until_date          timestamptz,

    -- Token budget used to produce this digest
    token_budget        integer,
    token_count_actual  integer,                    -- actual tokens in the output

    -- The synthesised content
    content             text        NOT NULL,
    content_format      text        NOT NULL DEFAULT 'markdown'
                            CHECK (content_format IN ('markdown', 'plain', 'json')),

    -- Provenance: the evidence this digest was built from (for staleness detection + citations)
    source_document_ids uuid[]      NOT NULL DEFAULT '{}',
    claim_ids           uuid[]      NOT NULL DEFAULT '{}',
    fact_version_ids    uuid[]      NOT NULL DEFAULT '{}',

    -- Synthesis metadata
    model               text,                       -- LLM model used for synthesis
    synthesizer_version text,                       -- synthesizer job version

    -- Cache lifecycle
    is_stale            boolean     NOT NULL DEFAULT false,  -- set true when underlying facts change
    stale_reason        text,
    expires_at          timestamptz,

    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_digests_topic     ON digests (topic_id, created_at DESC) WHERE topic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_digests_entity    ON digests (entity_id, created_at DESC) WHERE entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_digests_not_stale ON digests (topic_id, entity_id, created_at DESC) WHERE is_stale = false;

COMMENT ON TABLE digests IS
    'Cached agent-facing syntheses. Delivery artifacts only — never canonical facts or evidence. '
    'source_document_ids + claim_ids enable staleness detection and citation verification. '
    'is_stale is set by the pipeline when underlying facts change.';
