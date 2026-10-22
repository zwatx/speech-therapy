CREATE TABLE research_workload_identities (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  workload_id TEXT NOT NULL CHECK (
    workload_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
  ),
  purpose TEXT NOT NULL CHECK (purpose = 'research-job-runner'),
  registered_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, workload_id),
  FOREIGN KEY (tenant_id, registered_by_actor_id)
    REFERENCES tenant_memberships(tenant_id, actor_id)
);

CREATE TABLE research_workload_identity_revocations (
  tenant_id TEXT NOT NULL,
  workload_id TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (reason IN ('rotated', 'compromised', 'disabled')),
  revoked_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, workload_id),
  FOREIGN KEY (tenant_id, workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  FOREIGN KEY (tenant_id, revoked_by_actor_id)
    REFERENCES tenant_memberships(tenant_id, actor_id)
);

CREATE TABLE research_workload_signing_keys (
  tenant_id TEXT NOT NULL,
  workload_id TEXT NOT NULL,
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
  PRIMARY KEY (tenant_id, workload_id, signing_key_id),
  UNIQUE (tenant_id, workload_id, public_key_sha256),
  UNIQUE (tenant_id, workload_id, signing_key_id, public_key_sha256),
  FOREIGN KEY (tenant_id, workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  FOREIGN KEY (tenant_id, registered_by_actor_id)
    REFERENCES tenant_memberships(tenant_id, actor_id),
  CHECK (valid_until > valid_from)
);

CREATE TABLE research_workload_signing_key_revocations (
  tenant_id TEXT NOT NULL,
  workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (reason IN ('rotated', 'compromised', 'disabled')),
  revoked_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, workload_id, signing_key_id),
  FOREIGN KEY (tenant_id, workload_id, signing_key_id)
    REFERENCES research_workload_signing_keys(tenant_id, workload_id, signing_key_id),
  FOREIGN KEY (tenant_id, revoked_by_actor_id)
    REFERENCES tenant_memberships(tenant_id, actor_id)
);

CREATE TABLE research_workload_identity_gates (
  tenant_id TEXT NOT NULL,
  workload_id TEXT NOT NULL,
  revoked BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, workload_id),
  FOREIGN KEY (tenant_id, workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id)
);

CREATE TABLE research_workload_signing_key_gates (
  tenant_id TEXT NOT NULL,
  workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  revoked BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, workload_id, signing_key_id),
  FOREIGN KEY (tenant_id, workload_id, signing_key_id)
    REFERENCES research_workload_signing_keys(tenant_id, workload_id, signing_key_id)
);

CREATE OR REPLACE FUNCTION cadence_preserve_research_workload_identity_gate()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR NEW.workload_id IS DISTINCT FROM OLD.workload_id
    OR (OLD.revoked AND NOT NEW.revoked)
  THEN
    RAISE EXCEPTION 'research workload identity gate is monotonic';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cadence_preserve_research_workload_key_gate()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR NEW.workload_id IS DISTINCT FROM OLD.workload_id
    OR NEW.signing_key_id IS DISTINCT FROM OLD.signing_key_id
    OR (OLD.revoked AND NOT NEW.revoked)
  THEN
    RAISE EXCEPTION 'research workload signing key gate is monotonic';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_workload_identity_gates_monotonic
BEFORE UPDATE ON research_workload_identity_gates
FOR EACH ROW EXECUTE FUNCTION cadence_preserve_research_workload_identity_gate();
CREATE TRIGGER research_workload_key_gates_monotonic
BEFORE UPDATE ON research_workload_signing_key_gates
FOR EACH ROW EXECUTE FUNCTION cadence_preserve_research_workload_key_gate();
CREATE TRIGGER research_workload_identity_gates_prevent_delete
BEFORE DELETE ON research_workload_identity_gates
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_identity_gates_prevent_truncate
BEFORE TRUNCATE ON research_workload_identity_gates
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_key_gates_prevent_delete
BEFORE DELETE ON research_workload_signing_key_gates
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_key_gates_prevent_truncate
BEFORE TRUNCATE ON research_workload_signing_key_gates
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

ALTER TABLE audit_events
  ALTER COLUMN actor_id DROP NOT NULL,
  ADD COLUMN workload_id TEXT,
  ADD CONSTRAINT audit_events_workload_identity_fk
    FOREIGN KEY (tenant_id, workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  ADD CONSTRAINT audit_events_principal_check CHECK (
    (actor_id IS NOT NULL AND workload_id IS NULL)
    OR (actor_id IS NULL AND workload_id IS NOT NULL)
  );

ALTER TABLE research_job_execution_claims
  ALTER COLUMN claimed_by_actor_id DROP NOT NULL,
  ADD COLUMN claimed_by_workload_id TEXT,
  ADD COLUMN signing_key_id TEXT,
  ADD COLUMN signature_algorithm TEXT CHECK (signature_algorithm = 'Ed25519'),
  ADD COLUMN public_key_sha256 TEXT CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  ADD COLUMN attestation_issued_at TIMESTAMPTZ,
  ADD COLUMN attestation_payload_sha256 TEXT CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  ADD COLUMN signature_sha256 TEXT CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  ADD CONSTRAINT research_job_execution_claim_workload_fk
    FOREIGN KEY (tenant_id, claimed_by_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  ADD CONSTRAINT research_job_execution_claim_signing_key_fk
    FOREIGN KEY (
      tenant_id, claimed_by_workload_id, signing_key_id, public_key_sha256
    ) REFERENCES research_workload_signing_keys(
      tenant_id, workload_id, signing_key_id, public_key_sha256
    ),
  ADD CONSTRAINT research_job_execution_claim_principal_check CHECK (
    (claimed_by_actor_id IS NOT NULL
      AND claimed_by_workload_id IS NULL
      AND signing_key_id IS NULL
      AND signature_algorithm IS NULL
      AND public_key_sha256 IS NULL
      AND attestation_issued_at IS NULL
      AND attestation_payload_sha256 IS NULL
      AND signature_sha256 IS NULL)
    OR
    (claimed_by_actor_id IS NULL
      AND claimed_by_workload_id IS NOT NULL
      AND signing_key_id IS NOT NULL
      AND signature_algorithm = 'Ed25519'
      AND public_key_sha256 IS NOT NULL
      AND attestation_issued_at IS NOT NULL
      AND attestation_payload_sha256 IS NOT NULL
      AND signature_sha256 IS NOT NULL)
  );

CREATE OR REPLACE FUNCTION cadence_require_signed_research_workload_claim()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.claimed_by_workload_id IS NULL
    OR NEW.signing_key_id IS NULL
    OR NEW.signature_algorithm <> 'Ed25519'
    OR NEW.attestation_payload_sha256 IS NULL
    OR NEW.signature_sha256 IS NULL
  THEN
    RAISE EXCEPTION 'new research job claims require a signed workload identity';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_execution_claims_require_signed_workload
BEFORE INSERT ON research_job_execution_claims
FOR EACH ROW EXECUTE FUNCTION cadence_require_signed_research_workload_claim();

CREATE INDEX research_workload_signing_keys_active_idx
  ON research_workload_signing_keys(tenant_id, workload_id, valid_from, valid_until);

CREATE TRIGGER research_workload_identities_append_only
BEFORE UPDATE OR DELETE ON research_workload_identities
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_identities_prevent_truncate
BEFORE TRUNCATE ON research_workload_identities
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_identity_revocations_append_only
BEFORE UPDATE OR DELETE ON research_workload_identity_revocations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_identity_revocations_prevent_truncate
BEFORE TRUNCATE ON research_workload_identity_revocations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_signing_keys_append_only
BEFORE UPDATE OR DELETE ON research_workload_signing_keys
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_signing_keys_prevent_truncate
BEFORE TRUNCATE ON research_workload_signing_keys
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_signing_key_revocations_append_only
BEFORE UPDATE OR DELETE ON research_workload_signing_key_revocations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_workload_signing_key_revocations_prevent_truncate
BEFORE TRUNCATE ON research_workload_signing_key_revocations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
