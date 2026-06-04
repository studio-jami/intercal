-- 0004_sources.sql
-- Sources are configured origins of data (RSS, API, dump, repository, government feed, etc.).
-- Source records carry reliability metadata, adapter config, license/redistribution policy,
-- run cadence, and historical health.

CREATE TABLE IF NOT EXISTS sources (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                text        NOT NULL UNIQUE,      -- short stable identifier, e.g. 'wikidata-changes'
    name                text        NOT NULL,
    description         text,
    source_type         text        NOT NULL,             -- 'rss', 'api', 'dump', 'registry', 'user_submitted', etc.
    adapter_name        text        NOT NULL,             -- internal adapter identifier, e.g. 'wikidata_changes_v1'
    adapter_config      jsonb       NOT NULL DEFAULT '{}',-- per-adapter settings (URLs, auth refs, filters)

    -- Ingestion cadence
    run_cadence_seconds integer,                          -- NULL = on-demand only
    last_run_at         timestamptz,
    next_run_at         timestamptz,

    -- Reliability signals
    reliability_score   numeric(3,2),                     -- 0.00–1.00; updated by pipeline
    consecutive_failures integer     NOT NULL DEFAULT 0,

    -- License / redistribution policy
    -- Controls what the pipeline may do with fetched content.
    license_spdx        text,                             -- SPDX identifier if known, e.g. 'CC-BY-4.0'
    redistribution_allowed boolean   NOT NULL DEFAULT false,
    summary_allowed     boolean      NOT NULL DEFAULT true,
    citation_only       boolean      NOT NULL DEFAULT false,
    license_notes       text,                             -- free text for partial/edge-case policies

    -- Rate limiting
    rate_limit_requests_per_minute integer,
    rate_limit_notes    text,

    -- Lifecycle
    is_active           boolean      NOT NULL DEFAULT true,
    is_paused           boolean      NOT NULL DEFAULT false,
    pause_reason        text,

    metadata            jsonb        NOT NULL DEFAULT '{}',-- arbitrary adapter metadata
    created_at          timestamptz  NOT NULL DEFAULT now(),
    updated_at          timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sources_slug       ON sources (slug);
CREATE INDEX IF NOT EXISTS idx_sources_is_active  ON sources (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sources_next_run   ON sources (next_run_at) WHERE is_active = true AND is_paused = false;

COMMENT ON TABLE sources IS
    'Configured origins of data. One row per source adapter instance. '
    'redistribution_allowed/citation_only enforce source policy before broad ingestion.';
