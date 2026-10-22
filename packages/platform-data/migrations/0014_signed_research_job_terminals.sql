ALTER TABLE ml_artifacts
  ALTER COLUMN created_by_actor_id DROP NOT NULL,
  ADD COLUMN created_by_workload_id TEXT,
  ADD CONSTRAINT ml_artifacts_workload_creator_fk
    FOREIGN KEY (tenant_id, created_by_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  ADD CONSTRAINT ml_artifacts_creator_principal_check CHECK (
    (created_by_actor_id IS NOT NULL AND created_by_workload_id IS NULL)
    OR (created_by_actor_id IS NULL AND created_by_workload_id IS NOT NULL)
  );

ALTER TABLE managed_artifact_objects
  ALTER COLUMN registered_by_actor_id DROP NOT NULL,
  ADD COLUMN registered_by_workload_id TEXT,
  ADD CONSTRAINT managed_artifact_objects_workload_creator_fk
    FOREIGN KEY (tenant_id, registered_by_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  ADD CONSTRAINT managed_artifact_objects_creator_principal_check CHECK (
    (registered_by_actor_id IS NOT NULL AND registered_by_workload_id IS NULL)
    OR (registered_by_actor_id IS NULL AND registered_by_workload_id IS NOT NULL)
  );

ALTER TABLE managed_artifact_object_observations
  ALTER COLUMN recorded_by_actor_id DROP NOT NULL,
  ADD COLUMN recorded_by_workload_id TEXT,
  ADD CONSTRAINT managed_artifact_observations_workload_creator_fk
    FOREIGN KEY (tenant_id, recorded_by_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  ADD CONSTRAINT managed_artifact_observations_creator_principal_check CHECK (
    (recorded_by_actor_id IS NOT NULL AND recorded_by_workload_id IS NULL)
    OR (recorded_by_actor_id IS NULL AND recorded_by_workload_id IS NOT NULL)
  );

ALTER TABLE research_job_terminal_receipts
  ALTER COLUMN completed_by_actor_id DROP NOT NULL,
  ADD COLUMN completed_by_workload_id TEXT,
  ADD COLUMN signing_key_id TEXT,
  ADD COLUMN signature_algorithm TEXT CHECK (signature_algorithm = 'Ed25519'),
  ADD COLUMN public_key_sha256 TEXT CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  ADD COLUMN attestation_issued_at TIMESTAMPTZ,
  ADD COLUMN attestation_payload_sha256 TEXT CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  ADD COLUMN signature_sha256 TEXT CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  ADD CONSTRAINT research_job_terminal_workload_fk
    FOREIGN KEY (tenant_id, completed_by_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  ADD CONSTRAINT research_job_terminal_signing_key_fk
    FOREIGN KEY (
      tenant_id, completed_by_workload_id, signing_key_id, public_key_sha256
    ) REFERENCES research_workload_signing_keys(
      tenant_id, workload_id, signing_key_id, public_key_sha256
    ),
  ADD CONSTRAINT research_job_terminal_principal_check CHECK (
    (completed_by_actor_id IS NOT NULL
      AND completed_by_workload_id IS NULL
      AND signing_key_id IS NULL
      AND signature_algorithm IS NULL
      AND public_key_sha256 IS NULL
      AND attestation_issued_at IS NULL
      AND attestation_payload_sha256 IS NULL
      AND signature_sha256 IS NULL)
    OR
    (completed_by_actor_id IS NULL
      AND completed_by_workload_id IS NOT NULL
      AND signing_key_id IS NOT NULL
      AND signature_algorithm = 'Ed25519'
      AND public_key_sha256 IS NOT NULL
      AND attestation_issued_at IS NOT NULL
      AND attestation_payload_sha256 IS NOT NULL
      AND signature_sha256 IS NOT NULL)
  );

ALTER TABLE research_job_execution_claims
  ADD CONSTRAINT research_job_execution_claim_terminal_workload_identity
  UNIQUE (
    claim_id, job_id, tenant_id, envelope_sha256, claimed_by_workload_id
  );

ALTER TABLE research_job_terminal_receipts
  ADD CONSTRAINT research_job_terminal_claim_workload_fk
  FOREIGN KEY (
    claim_id, job_id, tenant_id, envelope_sha256, completed_by_workload_id
  ) REFERENCES research_job_execution_claims(
    claim_id, job_id, tenant_id, envelope_sha256, claimed_by_workload_id
  );

CREATE OR REPLACE FUNCTION cadence_require_signed_research_workload_terminal()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.completed_by_workload_id IS NULL
    OR NEW.signing_key_id IS NULL
    OR NEW.signature_algorithm <> 'Ed25519'
    OR NEW.attestation_payload_sha256 IS NULL
    OR NEW.signature_sha256 IS NULL
  THEN
    RAISE EXCEPTION 'new research job terminals require a signed workload identity';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_terminal_receipts_require_signed_workload
BEFORE INSERT ON research_job_terminal_receipts
FOR EACH ROW EXECUTE FUNCTION cadence_require_signed_research_workload_terminal();
