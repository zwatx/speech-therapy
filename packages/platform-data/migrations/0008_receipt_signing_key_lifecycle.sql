CREATE TABLE IF NOT EXISTS artifact_receipt_signing_keys (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  provider_id TEXT NOT NULL CHECK (
    provider_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
  ),
  signing_key_id TEXT NOT NULL CHECK (
    signing_key_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
  ),
  algorithm TEXT NOT NULL CHECK (algorithm = 'Ed25519'),
  public_key_pem TEXT NOT NULL CHECK (char_length(public_key_pem) BETWEEN 80 AND 1000),
  public_key_sha256 TEXT NOT NULL CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  valid_from TIMESTAMPTZ NOT NULL,
  valid_until TIMESTAMPTZ NOT NULL,
  registered_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, provider_id, signing_key_id),
  CHECK (valid_until > valid_from),
  UNIQUE (tenant_id, provider_id, public_key_sha256)
);

CREATE TABLE IF NOT EXISTS artifact_receipt_signing_key_revocations (
  tenant_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (
    reason IN ('rotated', 'compromised', 'provider-disabled')
  ),
  revoked_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, provider_id, signing_key_id),
  FOREIGN KEY (tenant_id, provider_id, signing_key_id)
    REFERENCES artifact_receipt_signing_keys (
      tenant_id, provider_id, signing_key_id
    )
);

CREATE INDEX IF NOT EXISTS artifact_receipt_signing_keys_active_idx
  ON artifact_receipt_signing_keys (tenant_id, valid_from, valid_until);

DROP TRIGGER IF EXISTS artifact_receipt_signing_keys_append_only
  ON artifact_receipt_signing_keys;
CREATE TRIGGER artifact_receipt_signing_keys_append_only
BEFORE UPDATE OR DELETE ON artifact_receipt_signing_keys
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_receipt_signing_keys_prevent_truncate
  ON artifact_receipt_signing_keys;
CREATE TRIGGER artifact_receipt_signing_keys_prevent_truncate
BEFORE TRUNCATE ON artifact_receipt_signing_keys
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_receipt_signing_key_revocations_append_only
  ON artifact_receipt_signing_key_revocations;
CREATE TRIGGER artifact_receipt_signing_key_revocations_append_only
BEFORE UPDATE OR DELETE ON artifact_receipt_signing_key_revocations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_receipt_signing_key_revocations_prevent_truncate
  ON artifact_receipt_signing_key_revocations;
CREATE TRIGGER artifact_receipt_signing_key_revocations_prevent_truncate
BEFORE TRUNCATE ON artifact_receipt_signing_key_revocations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
