
-- Ledger idempotency theo tài khoản; commit cùng thay đổi nghiệp vụ.
CREATE TABLE IF NOT EXISTS moviers.idempotency_keys (
    user_id bigint NOT NULL REFERENCES moviers.app_users(user_id) ON DELETE CASCADE,
    key_hash text NOT NULL CHECK (key_hash ~ '^[a-f0-9]{64}$'),
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[a-f0-9]{64}$'),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY(user_id,key_hash)
);
CREATE INDEX IF NOT EXISTS idempotency_expires_idx ON moviers.idempotency_keys(expires_at);
ALTER TABLE moviers.idempotency_keys ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON moviers.idempotency_keys FROM PUBLIC,anon,authenticated;
INSERT INTO moviers.schema_version(version) VALUES ('003_idempotency') ON CONFLICT DO NOTHING;
