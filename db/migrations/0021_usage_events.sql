-- 0021_usage_events.sql
-- Usage events record API and MCP tool calls for billing, rate limiting, and analytics.
-- These are operational records, not audit logs. For audit trail see audit_events.

CREATE TABLE IF NOT EXISTS usage_events (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id          uuid        REFERENCES api_keys(id) ON DELETE SET NULL,

    -- Request identity
    tool_name           text        NOT NULL,   -- MCP tool or REST endpoint name, e.g. 'get_delta', 'GET /entities'
    request_id          text,                   -- correlation ID from the request (e.g. trace ID)

    -- Outcome
    status_code         integer,                -- HTTP status or MCP result code
    latency_ms          integer,                -- request duration in milliseconds
    error_code          text,                   -- application error code if any

    -- Token tracking (for digest/synthesis endpoints)
    token_budget        integer,
    tokens_used         integer,

    -- Rough content counts for the response
    entity_count        integer,
    claim_count         integer,
    document_count      integer,

    -- Caller context
    ip_address          text,                   -- stored as text; apply anonymization policy at ingest
    user_agent          text,

    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Partitioning by time is recommended at scale; for now a simple index is sufficient.
CREATE INDEX IF NOT EXISTS idx_usage_events_api_key    ON usage_events (api_key_id, created_at DESC)
    WHERE api_key_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usage_events_tool       ON usage_events (tool_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events (created_at DESC);

COMMENT ON TABLE usage_events IS
    'Operational records of API and MCP tool calls. Used for rate limiting, billing, and analytics. '
    'Not a security audit log — see audit_events for that. '
    'ip_address should be anonymized or hashed per privacy policy.';
