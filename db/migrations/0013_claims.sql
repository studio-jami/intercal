-- 0013_claims.sql
-- Claims are atomic factual assertions extracted from one or more source documents.
-- Example: "Sam Altman holds the role of CEO at OpenAI as of 2026-05-21."
--
-- Claims carry:
--   - subject / predicate / object (entity IDs or plain text for unresolved subjects)
--   - qualifiers (jsonb) for additional context (e.g. location, manner, degree)
--   - bitemporal valid time (valid_from / valid_until) — when the assertion is true in the world
--   - confidence score and extraction method
--   - contradiction state and lifecycle status
--   - normalized text and optional raw quote/spans
--   - link to claim_evidence → source_documents (invariant: every public claim needs evidence)
--
-- claim_evidence: join table linking claims to their supporting source documents.
-- claim_contradictions: records pairs of claims that contradict each other.

-- ---------------------------------------------------------------------------
-- claims
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claims (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The factual assertion in structured form
    -- subject_entity_id may be NULL if the subject is not yet resolved to a canonical entity
    subject_entity_id   uuid        REFERENCES entities(id) ON DELETE SET NULL,
    subject_text        text        NOT NULL,   -- always filled: the raw text subject (canonical name or raw span)
    predicate           text        NOT NULL,   -- e.g. 'holds_role', 'founded', 'acquired', 'stated'
    object_entity_id    uuid        REFERENCES entities(id) ON DELETE SET NULL,
    object_text         text        NOT NULL,   -- always filled: raw text object

    -- Additional structured qualifiers (location, manner, certainty, units, etc.)
    qualifiers          jsonb       NOT NULL DEFAULT '{}',

    -- Normalized text: a canonical natural-language restatement of the claim
    normalized_text     text        NOT NULL,

    -- Raw evidence quote from source (may be NULL for redistribution-restricted sources)
    raw_quote           text,
    raw_spans           jsonb,      -- [{document_id, char_start, char_end, text}, ...]

    -- Bitemporal: valid time in the world
    valid_from          timestamptz,            -- when this claim became true (NULL = unknown/open)
    valid_until         timestamptz,            -- when it stopped being true (NULL = still true / open interval)

    -- Extraction provenance
    extractor           text        NOT NULL,   -- 'llm_extract_v1', 'rule_extract', 'human', etc.
    extraction_confidence numeric(3,2) NOT NULL DEFAULT 0.0 CHECK (extraction_confidence BETWEEN 0 AND 1),
    source_document_ids uuid[]      NOT NULL DEFAULT '{}', -- denormalized fast lookup; canonical is claim_evidence

    -- Contradiction / lifecycle state
    -- contradiction_status: 'none' = no known contradictions; 'has_contradiction' = see claim_contradictions
    contradiction_status text       NOT NULL DEFAULT 'none'
                            CHECK (contradiction_status IN ('none', 'has_contradiction', 'resolved')),

    -- Lifecycle: 'active' = currently valid; 'superseded' = a newer claim replaces it;
    --            'retracted' = removed from evidence; 'draft' = not yet published
    status              text        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'superseded', 'retracted', 'draft')),
    superseded_by_id    uuid        REFERENCES claims(id) ON DELETE SET NULL,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Core query paths
CREATE INDEX IF NOT EXISTS idx_claims_subject_entity   ON claims (subject_entity_id) WHERE subject_entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_claims_object_entity    ON claims (object_entity_id) WHERE object_entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_claims_predicate        ON claims (predicate);
CREATE INDEX IF NOT EXISTS idx_claims_status           ON claims (status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_claims_valid_from       ON claims (valid_from DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_claims_normalized_fts   ON claims USING gin(to_tsvector('english', normalized_text));
-- Point-in-time query: claims active during a given valid interval
CREATE INDEX IF NOT EXISTS idx_claims_valid_time       ON claims (valid_from, valid_until);

COMMENT ON TABLE claims IS
    'First-class atomic factual assertions. Subject/predicate/object with bitemporal valid time, '
    'qualifiers, confidence, contradiction state, and lifecycle status. '
    'Every claim used publicly must be linked to claim_evidence → source_documents.';

-- ---------------------------------------------------------------------------
-- claim_evidence
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim_evidence (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id        uuid        NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    document_id     uuid        NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,

    -- How strongly this document supports the claim
    support_strength text        NOT NULL DEFAULT 'supports'
                        CHECK (support_strength IN ('supports', 'partially_supports', 'contradicts', 'neutral')),
    confidence      numeric(3,2) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),

    -- Optional span pointer into the document
    char_offset_start integer,
    char_offset_end   integer,
    quote_excerpt     text,

    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_claim_evidence UNIQUE (claim_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim_id    ON claim_evidence (claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_document_id ON claim_evidence (document_id);

COMMENT ON TABLE claim_evidence IS
    'Join table linking claims to their supporting source documents. '
    'Invariant: every claim surfaced publicly must have at least one evidence row. '
    'ON DELETE RESTRICT on document_id prevents orphaning evidence.';

-- ---------------------------------------------------------------------------
-- claim_contradictions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim_contradictions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_a_id      uuid        NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    claim_b_id      uuid        NOT NULL REFERENCES claims(id) ON DELETE CASCADE,

    -- How we determined the contradiction
    detection_method text       NOT NULL DEFAULT 'rule'
                        CHECK (detection_method IN ('rule', 'model', 'human')),
    confidence      numeric(3,2) NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0 AND 1),
    description     text,           -- human-readable explanation of the contradiction

    -- Resolution
    resolution_status text      NOT NULL DEFAULT 'open'
                        CHECK (resolution_status IN ('open', 'resolved', 'dismissed')),
    resolved_claim_id uuid      REFERENCES claims(id) ON DELETE SET NULL,  -- the claim considered correct
    resolved_at     timestamptz,
    resolved_by     text,

    created_at      timestamptz NOT NULL DEFAULT now(),

    -- Canonical ordering: always store a < b by claim UUID to avoid duplicate pairs
    CONSTRAINT uq_claim_contradiction UNIQUE (claim_a_id, claim_b_id),
    CONSTRAINT chk_contradiction_different CHECK (claim_a_id <> claim_b_id)
);

CREATE INDEX IF NOT EXISTS idx_claim_contradictions_a  ON claim_contradictions (claim_a_id);
CREATE INDEX IF NOT EXISTS idx_claim_contradictions_b  ON claim_contradictions (claim_b_id);
CREATE INDEX IF NOT EXISTS idx_claim_contradictions_open ON claim_contradictions (resolution_status)
    WHERE resolution_status = 'open';

COMMENT ON TABLE claim_contradictions IS
    'Pairs of claims that assert incompatible facts. Used to flag confidence reduction and '
    'surface review queues. claim_a_id < claim_b_id (UUID ordering) prevents duplicate pairs.';
