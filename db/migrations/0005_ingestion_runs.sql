-- 0005_ingestion_runs.sql
-- Ingestion runs record every attempt to pull data from a source.
-- Every ingest_source job must create a run row; run status is updated as the job proceeds.
-- Idempotency: pipeline workers check for an in-progress run before starting a new one.

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           uuid        NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,

    -- Status lifecycle: pending → running → succeeded | failed | skipped
    status              text        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')),

    -- Timing
    started_at          timestamptz,
    finished_at         timestamptz,

    -- Outcome counters (updated by the adapter as it progresses)
    documents_fetched   integer     NOT NULL DEFAULT 0,
    documents_new       integer     NOT NULL DEFAULT 0,
    documents_skipped   integer     NOT NULL DEFAULT 0,
    documents_error     integer     NOT NULL DEFAULT 0,

    -- Pagination / cursor so failed runs can resume
    cursor_state        jsonb,                            -- adapter-specific pagination token

    -- Diagnostics
    error_message       text,
    error_detail        jsonb,
    logs                jsonb       NOT NULL DEFAULT '[]',-- structured log lines, if captured

    -- Trigger: 'scheduled', 'manual', 'api', 'retry'
    trigger             text        NOT NULL DEFAULT 'scheduled',

    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source_id ON ingestion_runs (source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status    ON ingestion_runs (status) WHERE status IN ('pending', 'running');

COMMENT ON TABLE ingestion_runs IS
    'One row per ingestion attempt. Jobs must set status=running on start and succeeded/failed on finish. '
    'cursor_state enables resumable adapters.';
