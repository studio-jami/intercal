-- 0011_entity_resolution.sql
-- Entity resolution candidates and merge events.
--
-- DESIGN PRINCIPLE: Conservative resolution over aggressive automation.
--   False non-merges are acceptable. False merges are data corruption.
--
-- entity_resolution_candidates: each candidate pair with its decision and signals.
-- entity_merge_events: append-only log of every merge decision, sufficient to reverse it.

-- ---------------------------------------------------------------------------
-- entity_resolution_candidates
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_resolution_candidates (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The two entities being compared (left_entity_id < right_entity_id by convention
    -- to avoid duplicate pairs; enforced by the UNIQUE constraint below)
    left_entity_id      uuid        NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    right_entity_id     uuid        NOT NULL REFERENCES entities(id) ON DELETE CASCADE,

    -- Decision: what should happen to this pair
    proposed_decision   text        NOT NULL DEFAULT 'needs_review'
                            CHECK (proposed_decision IN ('merge', 'keep_separate', 'needs_review')),
    decision_status     text        NOT NULL DEFAULT 'open'
                            CHECK (decision_status IN ('open', 'decided', 'superseded', 'reversed')),

    -- Confidence in the proposed decision (0 = no idea, 1 = certain)
    confidence          numeric(3,2) NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0 AND 1),

    -- Evidence
    matching_signals    jsonb       NOT NULL DEFAULT '[]', -- e.g. [{"type":"external_id","namespace":"wikidata","weight":1.0}]
    negative_signals    jsonb       NOT NULL DEFAULT '[]', -- signals that suggest they are NOT the same entity
    evidence_document_ids uuid[]    NOT NULL DEFAULT '{}', -- source_documents that informed this candidate

    -- Decision source
    decision_source     text        -- 'rule', 'model', 'human', 'external_id_match'
                            CHECK (decision_source IN ('rule', 'model', 'human', 'external_id_match', NULL)),
    decided_by          text,       -- actor identifier (user ID, job name) that made the decision
    decided_at          timestamptz,
    decision_rationale  text,

    -- Link to the merge event if merged
    merge_event_id      uuid,       -- set after merge; FK added after entity_merge_events table exists

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Prevent duplicate candidate pairs: always store left < right by ID ordering
    CONSTRAINT uq_resolution_candidate UNIQUE (left_entity_id, right_entity_id),
    -- An entity cannot be a candidate with itself
    CONSTRAINT chk_different_entities CHECK (left_entity_id <> right_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_erc_left_entity    ON entity_resolution_candidates (left_entity_id);
CREATE INDEX IF NOT EXISTS idx_erc_right_entity   ON entity_resolution_candidates (right_entity_id);
CREATE INDEX IF NOT EXISTS idx_erc_open_review    ON entity_resolution_candidates (decision_status, confidence DESC)
    WHERE decision_status = 'open';

COMMENT ON TABLE entity_resolution_candidates IS
    'Auditable resolution decisions for entity pairs. Conservative default: needs_review. '
    'False merges are data corruption; false non-merges are acceptable. '
    'left_entity_id < right_entity_id (UUID ordering) to prevent duplicate pairs.';

-- ---------------------------------------------------------------------------
-- entity_merge_events
-- ---------------------------------------------------------------------------
-- Append-only log. Enough bookkeeping to fully reverse any merge.
-- A merge:
--   - source_entity_id (loser) is set deprecated = true, merged_into_id → target_entity_id
--   - All aliases / external IDs from source are re-parented to target
--   - This row records the full pre-merge state for reversal

CREATE TABLE IF NOT EXISTS entity_merge_events (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id            uuid        REFERENCES entity_resolution_candidates(id) ON DELETE SET NULL,

    -- source = loser (deprecated); target = winner (absorbs)
    source_entity_id        uuid        NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    target_entity_id        uuid        NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,

    -- Pre-merge snapshots for reversal
    source_snapshot         jsonb       NOT NULL,  -- full entities row JSON at time of merge
    target_snapshot         jsonb       NOT NULL,  -- full entities row JSON at time of merge
    moved_alias_ids         uuid[]      NOT NULL DEFAULT '{}',  -- entity_aliases.id moved from source → target
    moved_external_id_ids   uuid[]      NOT NULL DEFAULT '{}',  -- entity_external_ids.id moved

    -- Decision metadata
    merged_by               text        NOT NULL,  -- actor identifier (job name, user ID)
    rationale               text,
    is_reversed             boolean     NOT NULL DEFAULT false,
    reversed_at             timestamptz,
    reversed_by             text,
    reversal_notes          text,

    created_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_merge_different CHECK (source_entity_id <> target_entity_id)
);

CREATE INDEX IF NOT EXISTS idx_eme_source_entity  ON entity_merge_events (source_entity_id);
CREATE INDEX IF NOT EXISTS idx_eme_target_entity  ON entity_merge_events (target_entity_id);
CREATE INDEX IF NOT EXISTS idx_eme_not_reversed   ON entity_merge_events (created_at DESC) WHERE is_reversed = false;

-- Back-fill the FK from entity_resolution_candidates → entity_merge_events
ALTER TABLE entity_resolution_candidates
    ADD CONSTRAINT fk_erc_merge_event
        FOREIGN KEY (merge_event_id) REFERENCES entity_merge_events(id) ON DELETE SET NULL;

COMMENT ON TABLE entity_merge_events IS
    'Append-only audit log of entity merge decisions. Stores pre-merge snapshots of both entities '
    'and lists of moved alias/external-id rows — sufficient to fully reverse any merge.';
