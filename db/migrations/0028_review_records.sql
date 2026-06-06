-- 0028_review_records.sql
-- Plan 04 W4: bounded public feedback/review records.
--
-- Public feedback is an operations/review input, not a canonical graph mutation. This table stores
-- the received review record and its workflow status; trust-sensitive creation is also recorded in
-- audit_events by the application in the same transaction.

CREATE TABLE IF NOT EXISTS review_records (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    target_type         text        NOT NULL
                            CHECK (target_type IN ('entity', 'claim', 'source', 'digest', 'freshness', 'coverage')),
    target_id           text        NOT NULL,

    concern_type        text        NOT NULL
                            CHECK (concern_type IN (
                                'incorrect',
                                'outdated',
                                'missing_evidence',
                                'missing_coverage',
                                'source_quality',
                                'contradiction',
                                'other'
                            )),
    summary             text        NOT NULL CHECK (char_length(summary) BETWEEN 1 AND 240),
    details             text        CHECK (details IS NULL OR char_length(details) <= 4000),

    status              text        NOT NULL DEFAULT 'received'
                            CHECK (status IN ('received', 'reviewing', 'resolved', 'rejected')),

    reporter_type       text        NOT NULL DEFAULT 'anonymous'
                            CHECK (reporter_type IN ('anonymous', 'api_key')),
    reporter_id         text,
    request_id          text,
    metadata            jsonb       NOT NULL DEFAULT '{}',

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    reviewed_at         timestamptz,
    resolved_at         timestamptz,

    CHECK ((reporter_type = 'anonymous' AND reporter_id IS NULL)
        OR (reporter_type = 'api_key' AND reporter_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_review_records_target
    ON review_records (target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_records_status
    ON review_records (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_records_reporter
    ON review_records (reporter_type, reporter_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_records_created_at
    ON review_records (created_at DESC);

COMMENT ON TABLE review_records IS
    'Bounded feedback and review records. Public submissions create rows here and audit_events rows, '
    'but never mutate canonical graph tables.';

COMMENT ON COLUMN review_records.target_type IS
    'Review target class: entity, claim, source, digest, freshness, or coverage.';

COMMENT ON COLUMN review_records.status IS
    'Operator workflow status. Public feedback creates received records only; later review surfaces may move status.';
