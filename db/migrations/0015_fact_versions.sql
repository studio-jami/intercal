-- 0015_fact_versions.sql
-- Fact versions are append-only records of what Intercal believed at a point in time.
--
-- BITEMPORAL MODEL:
--   valid_from / valid_until  — when the fact is (or was) true IN THE WORLD
--   recorded_at               — when Intercal LEARNED or RECORDED it
--
-- These two axes are independent:
--   - A historical fact (valid 1990–2000) may be recorded today (recorded_at = now).
--   - A fact recorded today may be corrected later by inserting a new version with a
--     different valid interval, NOT by updating existing rows.
--
-- APPEND-ONLY INVARIANT:
--   No UPDATE or DELETE on fact_versions. Corrections create new rows and mark the
--   superseded row via superseded_by_id. This is enforced by application policy and
--   documented here; a trigger could optionally enforce it at the DB layer.
--
-- fact_subject_type / fact_subject_id identify what the fact is about:
--   'entity'       → entities.id
--   'relationship' → relationships.id
--   'claim'        → claims.id

CREATE TABLE IF NOT EXISTS fact_versions (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What this fact version describes
    fact_subject_type   text        NOT NULL
                            CHECK (fact_subject_type IN ('entity', 'relationship', 'claim')),
    fact_subject_id     uuid        NOT NULL,   -- FK validated at application layer (polymorphic)

    -- The fact payload: a JSON snapshot of the relevant state at this version
    payload             jsonb       NOT NULL,

    -- Bitemporal columns
    -- valid_from: when this fact became true in the world (NULL = unknown/open start)
    valid_from          timestamptz,
    -- valid_until: when this fact stopped being true (NULL = still true / open interval)
    valid_until         timestamptz,
    -- recorded_at: when Intercal recorded this version (immutable after insert)
    recorded_at         timestamptz NOT NULL DEFAULT now(),

    -- Provenance
    source_document_ids uuid[]      NOT NULL DEFAULT '{}',
    claim_ids           uuid[]      NOT NULL DEFAULT '{}',

    -- Confidence at time of recording
    confidence          numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),

    -- Lifecycle: superseded rows remain; they are the historical record
    is_current          boolean     NOT NULL DEFAULT true,
    superseded_by_id    uuid        REFERENCES fact_versions(id) ON DELETE SET NULL,
    superseded_at       timestamptz,

    -- Who/what produced this version
    produced_by         text        NOT NULL DEFAULT 'pipeline', -- 'pipeline', 'human', 'correction'

    CONSTRAINT chk_fact_version_valid_time
        CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
);

-- Point-in-time queries: "what did Intercal know about X at recorded_at T with valid time V?"
CREATE INDEX IF NOT EXISTS idx_fact_versions_subject      ON fact_versions (fact_subject_type, fact_subject_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_versions_current      ON fact_versions (fact_subject_type, fact_subject_id)
    WHERE is_current = true;
CREATE INDEX IF NOT EXISTS idx_fact_versions_valid_from   ON fact_versions (valid_from DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_fact_versions_valid_until  ON fact_versions (valid_until DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_fact_versions_recorded_at  ON fact_versions (recorded_at DESC);

COMMENT ON TABLE fact_versions IS
    'Append-only bitemporal history of what Intercal believes. '
    'NEVER update or delete rows. Corrections insert a new row + set superseded_by_id on the old one. '
    'valid_from/valid_until = world truth interval. recorded_at = Intercal learn time. '
    'is_current = false rows are the historical archive; never discard them.';

COMMENT ON COLUMN fact_versions.valid_from IS
    'When this fact became true in the world. NULL = unknown start. '
    'Distinct from recorded_at (when Intercal learned it).';

COMMENT ON COLUMN fact_versions.recorded_at IS
    'When Intercal recorded this version. Set at insert; must never be updated.';
