-- 0029_subscription_notifications.sql
-- Plan 04 Workstream 5: bounded subscription notification outbox and delivery logs.
--
-- `subscriptions` (0019) owns registrations. This migration adds the append-only notification
-- records consumers can poll and webhook dispatchers can deliver. Payloads are public-contract
-- shaped summaries, not unrestricted internal row snapshots.

CREATE TABLE IF NOT EXISTS subscription_notifications (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id      uuid        NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    api_key_id           uuid        REFERENCES api_keys(id) ON DELETE SET NULL,

    -- What triggered this notification.
    change_kind          text        NOT NULL
                             CHECK (change_kind IN ('topic', 'entity', 'relationship', 'claim_pattern')),
    target_label         text        NOT NULL,
    since_date           timestamptz NOT NULL,
    until_date           timestamptz NOT NULL DEFAULT now(),

    -- Delivery controls copied from the subscription at enqueue time.
    min_importance       numeric(3,2) NOT NULL CHECK (min_importance BETWEEN 0 AND 1),
    token_budget         integer      NOT NULL CHECK (token_budget BETWEEN 200 AND 8000),
    max_importance       numeric(5,4) NOT NULL CHECK (max_importance BETWEEN 0 AND 1),

    -- Public notification payload. Must not contain webhook secrets, raw internal DB rows, or
    -- source body text beyond the existing public contract's citation/snippet policy.
    payload              jsonb       NOT NULL,

    delivery_method      text        NOT NULL CHECK (delivery_method IN ('polling', 'webhook')),
    status               text        NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'delivered', 'failed', 'skipped')),
    attempt_count        integer     NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at      timestamptz,
    last_attempt_at      timestamptz,
    delivered_at         timestamptz,
    error_code           text,
    error_message        text,

    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_subscription_notifications_payload_object
        CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_subscription_notifications_subscription
    ON subscription_notifications (subscription_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_notifications_polling
    ON subscription_notifications (subscription_id, status, created_at DESC)
    WHERE delivery_method = 'polling';
CREATE INDEX IF NOT EXISTS idx_subscription_notifications_webhook_due
    ON subscription_notifications (next_attempt_at NULLS FIRST, created_at)
    WHERE delivery_method = 'webhook' AND status IN ('pending', 'failed');

CREATE TABLE IF NOT EXISTS subscription_delivery_logs (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id      uuid        NOT NULL REFERENCES subscription_notifications(id) ON DELETE CASCADE,
    subscription_id      uuid        NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    delivery_method      text        NOT NULL CHECK (delivery_method IN ('polling', 'webhook')),
    attempt_number       integer     NOT NULL CHECK (attempt_number >= 0),
    status               text        NOT NULL CHECK (status IN ('queued', 'delivered', 'failed', 'skipped')),
    http_status          integer,
    error_code           text,
    error_message        text,
    next_attempt_at      timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscription_delivery_logs_notification
    ON subscription_delivery_logs (notification_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_delivery_logs_subscription
    ON subscription_delivery_logs (subscription_id, created_at DESC);

COMMENT ON TABLE subscription_notifications IS
    'Bounded subscription notification outbox. Payloads are public contract shaped and token-budgeted.';

COMMENT ON TABLE subscription_delivery_logs IS
    'Delivery attempt ledger for subscription polling/webhook notifications. No webhook secrets are stored.';
