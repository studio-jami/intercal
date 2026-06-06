-- 0030_observability.sql
-- Plan 04 Workstream 6: operator observability views and provider-consumption records.
--
-- The views below expose health, freshness, quality, latency, queue/outbox, and budget signals
-- from real state that already exists. Provider platform billing/usage APIs are intentionally not
-- called from SQL; provider adapters or ops import jobs can append measurements to
-- provider_usage_events when a real provider reading exists.

CREATE TABLE IF NOT EXISTS observability_provider_budget_allowances (
    provider            text        NOT NULL,
    allowance_key       text        NOT NULL,
    metric_name         text        NOT NULL,
    metric_unit         text        NOT NULL,
    allowance_period    text        NOT NULL CHECK (allowance_period IN ('day', 'month', 'unlimited', 'credit_pool', 'unknown')),
    allowance_quantity  numeric,
    binding             boolean     NOT NULL DEFAULT true,
    warning_ratio       numeric(4,3) NOT NULL DEFAULT 0.700 CHECK (warning_ratio > 0 AND warning_ratio <= 1),
    source_document     text        NOT NULL DEFAULT 'docs/operations/resource-budget.md',
    notes               text,
    updated_at          timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (provider, allowance_key),
    CHECK (allowance_quantity IS NULL OR allowance_quantity >= 0)
);

INSERT INTO observability_provider_budget_allowances
    (provider, allowance_key, metric_name, metric_unit, allowance_period, allowance_quantity, binding, notes)
VALUES
    ('github_actions', 'public_linux_minutes', 'linux_minutes', 'minutes', 'unlimited', NULL, false,
        'Public repository Linux minutes are documented as unlimited; private fallback is not modeled here.'),
    ('neon', 'compute_month', 'compute_cu_hours', 'cu_hours', 'month', 100, true,
        'June 2026 free-tier budget from resource-budget.md.'),
    ('neon', 'storage_branch', 'storage_bytes', 'bytes', 'month', 536870912, true,
        '0.5 GB per branch.'),
    ('upstash', 'commands_month', 'commands', 'commands', 'month', 500000, true,
        'Monthly command allowance.'),
    ('upstash', 'storage', 'storage_bytes', 'bytes', 'month', 268435456, true,
        '256 MB storage allowance.'),
    ('upstash', 'bandwidth', 'bandwidth_bytes', 'bytes', 'unknown', NULL, true,
        'Bandwidth readings may be imported when provider telemetry is available; resource-budget.md does not pin a stable allowance.'),
    ('r2', 'storage', 'storage_bytes', 'bytes', 'month', 10737418240, true,
        '10 GB storage allowance.'),
    ('r2', 'class_a_ops_month', 'class_a_ops', 'operations', 'month', 1000000, true,
        'Class-A write/list operation allowance.'),
    ('r2', 'class_b_ops_month', 'class_b_ops', 'operations', 'month', 10000000, true,
        'Class-B read operation allowance.'),
    ('r2', 'egress', 'egress_bytes', 'bytes', 'unlimited', NULL, false,
        'Resource budget records R2 egress as zero-dollar/unmetered for this plan.'),
    ('vertex', 'daily_token_cap', 'tokens', 'tokens', 'unknown', NULL, true,
        'Actual Vertex/Gemini quota or remaining trial credit must be imported from provider billing/quota data.'),
    ('vertex', 'daily_requests', 'requests', 'requests', 'day', 2000, true,
        'Default LLM_DAILY_REQUEST_BUDGET knob from resource-budget.md; override by updating this row if configured differently.'),
    ('gemini', 'daily_token_cap', 'tokens', 'tokens', 'unknown', NULL, true,
        'Actual Gemini AI Studio daily token cap must be imported from provider quota data.'),
    ('gemini', 'daily_requests', 'requests', 'requests', 'day', 2000, true,
        'Default LLM_DAILY_REQUEST_BUDGET knob from resource-budget.md; override by updating this row if configured differently.'),
    ('vercel', 'function_gb_hours', 'function_gb_hours', 'gb_hours', 'month', 100, true,
        'Approximate Hobby function execution budget from resource-budget.md.'),
    ('vercel', 'transfer', 'transfer_bytes', 'bytes', 'month', 107374182400, true,
        'Approximate 100 GB transfer budget from resource-budget.md.'),
    ('vercel', 'build_minutes', 'build_minutes', 'minutes', 'unknown', NULL, true,
        'Build-minute allowance is noted in resource-budget.md but must be verified in the provider account before use.'),
    ('cloud_run', 'requests_month', 'requests', 'requests', 'month', 2000000, true,
        'Always-free request allowance from resource-budget.md.'),
    ('cloud_run', 'vcpu_seconds_month', 'vcpu_seconds', 'seconds', 'month', 180000, true,
        'Always-free vCPU-seconds allowance from resource-budget.md.'),
    ('cloud_run', 'gb_seconds_month', 'gb_seconds', 'seconds', 'month', 360000, true,
        'Always-free GB-seconds allowance from resource-budget.md.'),
    ('cloud_run', 'egress', 'egress_bytes', 'bytes', 'month', 1073741824, true,
        '1 GB egress allowance from resource-budget.md.')
ON CONFLICT (provider, allowance_key) DO UPDATE SET
    metric_name = EXCLUDED.metric_name,
    metric_unit = EXCLUDED.metric_unit,
    allowance_period = EXCLUDED.allowance_period,
    allowance_quantity = EXCLUDED.allowance_quantity,
    binding = EXCLUDED.binding,
    warning_ratio = EXCLUDED.warning_ratio,
    source_document = EXCLUDED.source_document,
    notes = EXCLUDED.notes,
    updated_at = now();

CREATE TABLE IF NOT EXISTS provider_usage_events (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    provider            text        NOT NULL,
    allowance_key       text,
    metric_name         text        NOT NULL,
    metric_unit         text        NOT NULL,
    quantity            numeric     NOT NULL CHECK (quantity >= 0),
    cost_usd            numeric     CHECK (cost_usd IS NULL OR cost_usd >= 0),
    period_start        timestamptz,
    period_end          timestamptz,
    observed_at         timestamptz NOT NULL DEFAULT now(),
    source              text        NOT NULL,
    metadata            jsonb       NOT NULL DEFAULT '{}',

    CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
    CONSTRAINT fk_provider_usage_allowance
        FOREIGN KEY (provider, allowance_key)
        REFERENCES observability_provider_budget_allowances(provider, allowance_key)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_provider_usage_events_provider_observed
    ON provider_usage_events (provider, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_provider_usage_events_metric_period
    ON provider_usage_events (provider, metric_name, period_start DESC, observed_at DESC);

CREATE OR REPLACE VIEW observability_source_health AS
WITH run_rollups AS (
    SELECT
        source_id,
        count(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS runs_24h,
        count(*) FILTER (WHERE status = 'failed' AND created_at >= now() - interval '24 hours') AS failed_runs_24h,
        count(*) FILTER (WHERE status = 'running') AS running_runs,
        max(finished_at) FILTER (WHERE status = 'succeeded') AS last_success_at,
        max(created_at) FILTER (WHERE status = 'failed') AS last_failed_at,
        sum(documents_new) FILTER (WHERE created_at >= now() - interval '24 hours') AS documents_new_24h,
        sum(documents_error) FILTER (WHERE created_at >= now() - interval '24 hours') AS documents_error_24h
    FROM ingestion_runs
    GROUP BY source_id
),
latest_runs AS (
    SELECT DISTINCT ON (source_id)
        source_id,
        id AS latest_run_id,
        status AS latest_run_status,
        started_at AS latest_run_started_at,
        finished_at AS latest_run_finished_at,
        error_message AS latest_error_message
    FROM ingestion_runs
    ORDER BY source_id, created_at DESC
)
SELECT
    s.id AS source_id,
    s.slug,
    s.name,
    s.source_type,
    s.adapter_name,
    s.is_active,
    s.is_paused,
    s.pause_reason,
    s.reliability_score,
    s.consecutive_failures,
    s.run_cadence_seconds,
    s.last_run_at,
    s.next_run_at,
    lr.latest_run_id,
    lr.latest_run_status,
    lr.latest_run_started_at,
    lr.latest_run_finished_at,
    lr.latest_error_message,
    rr.last_success_at,
    rr.last_failed_at,
    COALESCE(rr.running_runs, 0) AS running_runs,
    COALESCE(rr.runs_24h, 0) AS runs_24h,
    COALESCE(rr.failed_runs_24h, 0) AS failed_runs_24h,
    COALESCE(rr.documents_new_24h, 0) AS documents_new_24h,
    COALESCE(rr.documents_error_24h, 0) AS documents_error_24h,
    CASE
        WHEN NOT s.is_active THEN 'inactive'
        WHEN s.is_paused THEN 'paused'
        WHEN s.consecutive_failures > 0 OR COALESCE(rr.failed_runs_24h, 0) > 0 THEN 'degraded'
        WHEN s.next_run_at IS NOT NULL AND s.next_run_at < now() THEN 'due'
        ELSE 'ok'
    END AS health_state
FROM sources s
LEFT JOIN run_rollups rr ON rr.source_id = s.id
LEFT JOIN latest_runs lr ON lr.source_id = s.id;

CREATE OR REPLACE VIEW observability_failed_jobs AS
SELECT
    'ingestion_run'::text AS job_type,
    ir.id AS job_id,
    s.slug AS owner_slug,
    ir.status,
    ir.created_at,
    ir.started_at,
    ir.finished_at,
    ir.error_message,
    ir.error_detail
FROM ingestion_runs ir
JOIN sources s ON s.id = ir.source_id
WHERE ir.status = 'failed'
UNION ALL
SELECT
    'subscription_notification'::text AS job_type,
    sn.id AS job_id,
    sn.subscription_id::text AS owner_slug,
    sn.status,
    sn.created_at,
    sn.last_attempt_at AS started_at,
    sn.updated_at AS finished_at,
    sn.error_message,
    jsonb_build_object('error_code', sn.error_code, 'attempt_count', sn.attempt_count) AS error_detail
FROM subscription_notifications sn
WHERE sn.status = 'failed'
UNION ALL
SELECT
    'subscription_delivery'::text AS job_type,
    sdl.id AS job_id,
    sdl.subscription_id::text AS owner_slug,
    sdl.status,
    sdl.created_at,
    sdl.created_at AS started_at,
    sdl.created_at AS finished_at,
    sdl.error_message,
    jsonb_build_object('error_code', sdl.error_code, 'http_status', sdl.http_status, 'attempt_number', sdl.attempt_number) AS error_detail
FROM subscription_delivery_logs sdl
WHERE sdl.status = 'failed';

CREATE OR REPLACE VIEW observability_pipeline_metrics AS
SELECT 'sources'::text AS area, 'active'::text AS metric, count(*)::numeric AS value, 'count'::text AS unit FROM sources WHERE is_active = true
UNION ALL SELECT 'sources', 'paused', count(*)::numeric, 'count' FROM sources WHERE is_paused = true
UNION ALL SELECT 'ingestion', 'pending_runs', count(*)::numeric, 'count' FROM ingestion_runs WHERE status = 'pending'
UNION ALL SELECT 'ingestion', 'running_runs', count(*)::numeric, 'count' FROM ingestion_runs WHERE status = 'running'
UNION ALL SELECT 'ingestion', 'failed_runs_24h', count(*)::numeric, 'count' FROM ingestion_runs WHERE status = 'failed' AND created_at >= now() - interval '24 hours'
UNION ALL SELECT 'extraction', 'documents_total', count(*)::numeric, 'count' FROM source_documents
UNION ALL SELECT 'extraction', 'chunks_total', count(*)::numeric, 'count' FROM document_chunks
UNION ALL SELECT 'claims', 'claims_total', count(*)::numeric, 'count' FROM claims
UNION ALL SELECT 'claims', 'active_claims', count(*)::numeric, 'count' FROM claims WHERE status = 'active'
UNION ALL SELECT 'claims', 'draft_claims', count(*)::numeric, 'count' FROM claims WHERE status = 'draft'
UNION ALL SELECT 'claims', 'claims_without_evidence', count(*)::numeric, 'count'
    FROM claims c WHERE NOT EXISTS (SELECT 1 FROM claim_evidence ce WHERE ce.claim_id = c.id)
UNION ALL SELECT 'resolution', 'open_candidates', count(*)::numeric, 'count' FROM entity_resolution_candidates WHERE decision_status = 'open'
UNION ALL SELECT 'resolution', 'needs_review_candidates', count(*)::numeric, 'count'
    FROM entity_resolution_candidates WHERE decision_status = 'open' AND proposed_decision = 'needs_review'
UNION ALL SELECT 'merge_split', 'merge_events_total', count(*)::numeric, 'count' FROM entity_merge_events
UNION ALL SELECT 'merge_split', 'reversed_merge_events', count(*)::numeric, 'count' FROM entity_merge_events WHERE is_reversed = true
UNION ALL SELECT 'embeddings', 'document_embedding_coverage_pct',
    CASE WHEN count(sd.id) = 0 THEN NULL ELSE round(100.0 * count(de.id)::numeric / count(sd.id)::numeric, 2) END, 'percent'
    FROM source_documents sd LEFT JOIN document_embeddings de ON de.document_id = sd.id
UNION ALL SELECT 'embeddings', 'chunk_embedding_coverage_pct',
    CASE WHEN count(dc.id) = 0 THEN NULL ELSE round(100.0 * count(ce.id)::numeric / count(dc.id)::numeric, 2) END, 'percent'
    FROM document_chunks dc LEFT JOIN chunk_embeddings ce ON ce.chunk_id = dc.id
UNION ALL SELECT 'embeddings', 'entity_embedding_coverage_pct',
    CASE WHEN count(e.id) = 0 THEN NULL ELSE round(100.0 * count(ee.id)::numeric / count(e.id)::numeric, 2) END, 'percent'
    FROM entities e LEFT JOIN entity_embeddings ee ON ee.entity_id = e.id WHERE e.is_deprecated = false
UNION ALL SELECT 'embeddings', 'claim_embedding_coverage_pct',
    CASE WHEN count(c.id) = 0 THEN NULL ELSE round(100.0 * count(ce.id)::numeric / count(c.id)::numeric, 2) END, 'percent'
    FROM claims c LEFT JOIN claim_embeddings ce ON ce.claim_id = c.id
UNION ALL SELECT 'digest_cache', 'digests_total', count(*)::numeric, 'count' FROM digests
UNION ALL SELECT 'digest_cache', 'stale_digests', count(*)::numeric, 'count' FROM digests WHERE is_stale = true
UNION ALL SELECT 'queue', 'pending_subscription_notifications', count(*)::numeric, 'count' FROM subscription_notifications WHERE status = 'pending'
UNION ALL SELECT 'queue', 'failed_subscription_notifications', count(*)::numeric, 'count' FROM subscription_notifications WHERE status = 'failed'
UNION ALL SELECT 'review', 'open_review_records', count(*)::numeric, 'count' FROM review_records WHERE status IN ('received', 'reviewing')
UNION ALL SELECT 'audit', 'audit_events_24h', count(*)::numeric, 'count' FROM audit_events WHERE created_at >= now() - interval '24 hours';

CREATE OR REPLACE VIEW observability_usage_latency AS
SELECT
    date_trunc('hour', created_at) AS bucket_hour,
    CASE
        WHEN lower(tool_name) LIKE 'mcp%' OR lower(tool_name) LIKE '%/mcp%' THEN 'mcp'
        ELSE 'api'
    END AS surface,
    tool_name,
    count(*) AS request_count,
    count(*) FILTER (WHERE status_code >= 400 OR error_code IS NOT NULL) AS error_count,
    round(avg(latency_ms)::numeric, 2) AS avg_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
    sum(COALESCE(tokens_used, 0)) AS tokens_used,
    sum(COALESCE(token_budget, 0)) AS token_budget
FROM usage_events
WHERE created_at >= now() - interval '7 days'
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW observability_freshness AS
SELECT
    'source'::text AS subject_type,
    s.slug AS subject_key,
    s.name AS subject_label,
    GREATEST(s.last_run_at, sh.last_success_at) AS last_observed_at,
    s.next_run_at,
    CASE
        WHEN NOT s.is_active THEN 'inactive'
        WHEN s.is_paused THEN 'paused'
        WHEN GREATEST(s.last_run_at, sh.last_success_at) IS NULL THEN 'unknown'
        WHEN s.run_cadence_seconds IS NOT NULL
            AND GREATEST(s.last_run_at, sh.last_success_at) < now() - make_interval(secs => s.run_cadence_seconds * 2)
            THEN 'stale'
        WHEN s.next_run_at IS NOT NULL AND s.next_run_at < now() THEN 'due'
        ELSE 'fresh'
    END AS freshness_state,
    CASE
        WHEN GREATEST(s.last_run_at, sh.last_success_at) IS NULL THEN NULL
        ELSE floor(extract(epoch FROM (now() - GREATEST(s.last_run_at, sh.last_success_at))) / 60)::integer
    END AS age_minutes
FROM sources s
LEFT JOIN observability_source_health sh ON sh.source_id = s.id
UNION ALL
SELECT 'documents', 'all', 'source_documents', max(ingested_at), NULL, CASE WHEN max(ingested_at) IS NULL THEN 'unknown' ELSE 'fresh' END,
    CASE WHEN max(ingested_at) IS NULL THEN NULL ELSE floor(extract(epoch FROM (now() - max(ingested_at))) / 60)::integer END
FROM source_documents
UNION ALL
SELECT 'claims', 'all', 'claims', max(created_at), NULL, CASE WHEN max(created_at) IS NULL THEN 'unknown' ELSE 'fresh' END,
    CASE WHEN max(created_at) IS NULL THEN NULL ELSE floor(extract(epoch FROM (now() - max(created_at))) / 60)::integer END
FROM claims
UNION ALL
SELECT 'facts', 'all', 'fact_versions', max(recorded_at), NULL, CASE WHEN max(recorded_at) IS NULL THEN 'unknown' ELSE 'fresh' END,
    CASE WHEN max(recorded_at) IS NULL THEN NULL ELSE floor(extract(epoch FROM (now() - max(recorded_at))) / 60)::integer END
FROM fact_versions
UNION ALL
SELECT 'digests', 'cache', 'digests', max(created_at), NULL, CASE WHEN max(created_at) IS NULL THEN 'unknown' ELSE 'fresh' END,
    CASE WHEN max(created_at) IS NULL THEN NULL ELSE floor(extract(epoch FROM (now() - max(created_at))) / 60)::integer END
FROM digests;

CREATE OR REPLACE VIEW observability_provider_consumption AS
WITH allowance_windows AS (
    SELECT
        a.*,
        CASE a.allowance_period
            WHEN 'day' THEN date_trunc('day', now())
            WHEN 'month' THEN date_trunc('month', now())
            ELSE NULL
        END AS window_start
    FROM observability_provider_budget_allowances a
),
usage_rollups AS (
    SELECT
        a.provider,
        a.allowance_key,
        sum(pue.quantity) AS quantity_used,
        sum(pue.cost_usd) AS cost_usd,
        max(pue.observed_at) AS last_observed_at
    FROM allowance_windows a
    LEFT JOIN provider_usage_events pue
        ON pue.provider = a.provider
        AND (pue.allowance_key = a.allowance_key OR (pue.allowance_key IS NULL AND pue.metric_name = a.metric_name))
        AND (
            a.window_start IS NULL
            OR pue.observed_at >= a.window_start
            OR pue.period_end >= a.window_start
        )
    GROUP BY a.provider, a.allowance_key
)
SELECT
    a.provider,
    a.allowance_key,
    a.metric_name,
    a.metric_unit,
    a.allowance_period,
    a.allowance_quantity,
    a.binding,
    CASE WHEN u.last_observed_at IS NULL THEN NULL ELSE u.quantity_used END AS quantity_used,
    CASE
        WHEN u.last_observed_at IS NULL THEN NULL
        WHEN a.allowance_quantity IS NULL THEN NULL
        ELSE round((u.quantity_used / NULLIF(a.allowance_quantity, 0)) * 100, 2)
    END AS used_pct,
    CASE WHEN u.last_observed_at IS NULL THEN NULL ELSE u.cost_usd END AS cost_usd,
    u.last_observed_at,
    CASE
        WHEN u.last_observed_at IS NULL THEN 'unavailable'
        WHEN a.allowance_quantity IS NULL THEN 'unavailable'
        WHEN u.quantity_used >= a.allowance_quantity THEN 'exceeded'
        WHEN u.quantity_used >= a.allowance_quantity * a.warning_ratio THEN 'warning'
        ELSE 'ok'
    END AS budget_state,
    CASE
        WHEN u.last_observed_at IS NULL THEN 'no provider usage event has been recorded'
        WHEN a.allowance_quantity IS NULL THEN 'allowance quantity is not configured in resource-budget.md/provider quota data'
        ELSE NULL
    END AS unavailable_reason,
    a.source_document,
    a.notes
FROM allowance_windows a
JOIN usage_rollups u ON u.provider = a.provider AND u.allowance_key = a.allowance_key;

COMMENT ON TABLE provider_usage_events IS
    'Append-only provider consumption observations imported from real provider APIs, billing exports, or adapter measurements. No credentials.';
COMMENT ON TABLE observability_provider_budget_allowances IS
    'Budget allowance snapshot linked to docs/operations/resource-budget.md; update when provider quotas are re-verified.';
COMMENT ON VIEW observability_source_health IS
    'Per-source health backed by sources and ingestion_runs.';
COMMENT ON VIEW observability_failed_jobs IS
    'Failed ingestion and subscription delivery jobs backed by real job/outbox tables.';
COMMENT ON VIEW observability_pipeline_metrics IS
    'Operator metric rollup for ingestion, extraction, claims, resolution, merge/split, embeddings, digest cache, queue, review, and audit state.';
COMMENT ON VIEW observability_usage_latency IS
    'REST/MCP usage, latency, error, and token-budget telemetry backed by usage_events.';
COMMENT ON VIEW observability_freshness IS
    'Freshness view for sources and aggregate evidence/claim/fact/digest recency.';
COMMENT ON VIEW observability_provider_consumption IS
    'Provider usage versus resource-budget allowances; unavailable rows are explicit, not zero-filled provider telemetry.';
