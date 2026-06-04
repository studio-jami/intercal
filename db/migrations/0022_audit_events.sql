-- 0022_audit_events.sql
-- Audit events capture the who/what/why for security-relevant and data-quality actions:
--   - Entity merges and reversals
--   - Claim corrections and retractions
--   - Source submissions and approvals
--   - Admin actions (key revocation, scope changes, source policy updates)
--   - Entity resolution decisions (especially human overrides)
--
-- Audit events are append-only. A trigger could enforce this; enforced by policy for now.
-- before_state and after_state store JSON snapshots of the affected record.

CREATE TABLE IF NOT EXISTS audit_events (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Actor
    actor_type          text        NOT NULL
                            CHECK (actor_type IN ('api_key', 'system', 'pipeline', 'human', 'admin')),
    actor_id            text        NOT NULL,   -- api_keys.id (uuid as text), job name, or user identifier
    actor_ip            text,

    -- Action
    action              text        NOT NULL,   -- e.g. 'entity.merge', 'claim.retract', 'source.approve',
                                               --      'api_key.revoke', 'entity_resolution.human_override'

    -- Target resource
    target_type         text        NOT NULL,   -- e.g. 'entity', 'claim', 'source', 'api_key', 'relationship'
    target_id           text        NOT NULL,   -- UUID as text (polymorphic)

    -- State snapshots (NULL if not applicable)
    before_state        jsonb,      -- JSON of the record before the action
    after_state         jsonb,      -- JSON of the record after the action

    -- Human-readable rationale or notes
    rationale           text,

    -- Request correlation (optional, for linking audit to usage_events)
    request_id          text,

    -- Risk classification: 'info', 'low', 'medium', 'high', 'critical'
    severity            text        NOT NULL DEFAULT 'info'
                            CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Query paths: by actor, by target, by action type, by time
CREATE INDEX IF NOT EXISTS idx_audit_events_actor      ON audit_events (actor_type, actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_target     ON audit_events (target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_action     ON audit_events (action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_severity   ON audit_events (severity, created_at DESC)
    WHERE severity IN ('high', 'critical');
CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events (created_at DESC);

COMMENT ON TABLE audit_events IS
    'Append-only security and data-quality audit log. Captures actor, action, target, before/after state, '
    'and rationale for merges, corrections, source submissions, key operations, and admin actions. '
    'Never update or delete rows.';

COMMENT ON COLUMN audit_events.action IS
    'Dot-namespaced action string, e.g. entity.merge, entity.merge.reverse, claim.retract, '
    'source.submit, source.approve, api_key.revoke, entity_resolution.decide.';
