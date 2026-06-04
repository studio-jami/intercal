-- 0020_api_keys.sql
-- API keys for authenticating callers to the REST API and MCP server.
--
-- SECURITY INVARIANTS:
--   1. Only the key hash is stored (SHA-256 hex of the raw key). The raw key is shown
--      to the user exactly once at creation and never stored.
--   2. scopes is a jsonb array of string scope identifiers (e.g. ["read:entities", "read:claims"]).
--   3. last_used_at is updated on each successful authentication; this is a best-effort
--      update (clock skew, caching layer) rather than a hard guarantee.
--   4. Revoked keys must not be usable; revoked_at is the canonical revocation timestamp.

CREATE TABLE IF NOT EXISTS api_keys (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Display identifier (not the raw key — shown to user for recognition)
    name                text        NOT NULL,           -- e.g. 'Production agent key'
    key_prefix          text        NOT NULL,           -- first 8 chars of the raw key for display, e.g. 'ical_sk_'

    -- Security: hash only, never plaintext
    key_hash            text        NOT NULL UNIQUE,    -- SHA-256(raw_key) as hex

    -- Authorization
    scopes              jsonb       NOT NULL DEFAULT '[]',  -- e.g. ["read:entities","read:claims","submit:source"]

    -- Ownership
    owner_type          text        NOT NULL DEFAULT 'user'
                            CHECK (owner_type IN ('user', 'service', 'system')),
    owner_id            text,       -- external user/service identifier

    -- Rate limiting hints (enforced at API layer)
    requests_per_minute integer,
    requests_per_day    integer,

    -- Lifecycle
    is_active           boolean     NOT NULL DEFAULT true,
    expires_at          timestamptz,                    -- NULL = no expiry
    last_used_at        timestamptz,
    revoked_at          timestamptz,
    revoked_by          text,
    revocation_reason   text,

    metadata            jsonb       NOT NULL DEFAULT '{}',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Lookup by hash on every authenticated request
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash    ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active      ON api_keys (is_active, expires_at NULLS LAST)
    WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_api_keys_owner       ON api_keys (owner_type, owner_id) WHERE owner_id IS NOT NULL;

-- Now that api_keys exists, add the FK from subscriptions
ALTER TABLE subscriptions
    ADD CONSTRAINT fk_subscriptions_api_key
        FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE SET NULL;

COMMENT ON TABLE api_keys IS
    'API key records. ONLY the SHA-256 hash is stored — raw keys are displayed once at creation. '
    'scopes is a jsonb array of string scope identifiers. '
    'revoked_at is the authoritative revocation timestamp; revoked keys must be rejected regardless of is_active.';

COMMENT ON COLUMN api_keys.key_hash IS
    'SHA-256 hex of the raw API key. UNIQUE. Raw key is never stored.';

COMMENT ON COLUMN api_keys.scopes IS
    'jsonb array of scope strings, e.g. ["read:entities","read:claims","submit:source"]. '
    'Validated at API layer on each request.';
