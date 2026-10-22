ALTER TABLE research_job_launch_attestations
  ADD CONSTRAINT research_job_launch_process_identity
  UNIQUE (
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    assigned_workload_id, process_reference_sha256, envelope_sha256
  );

CREATE TABLE research_job_external_termination_attestations (
  termination_attestation_id TEXT PRIMARY KEY CHECK (
    termination_attestation_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  launch_id TEXT NOT NULL,
  dispatch_id TEXT NOT NULL,
  dispatch_revision BIGINT NOT NULL CHECK (dispatch_revision > 0),
  assigned_workload_id TEXT NOT NULL,
  cancellation_revision BIGINT NOT NULL CHECK (cancellation_revision > 0),
  cancellation_sequence_id BIGINT NOT NULL,
  cancellation_source TEXT NOT NULL CHECK (
    cancellation_source IN ('operator', 'input-quarantined', 'provider-drift')
  ),
  cancellation_reason TEXT NOT NULL CHECK (
    cancellation_reason IN (
      'operator-stop', 'incident', 'provider-drift', 'input-quarantined'
    )
  ),
  outcome TEXT NOT NULL CHECK (outcome = 'process-stopped'),
  process_reference_sha256 TEXT NOT NULL CHECK (
    process_reference_sha256 ~ '^[a-f0-9]{64}$'
  ),
  termination_evidence_sha256 TEXT NOT NULL CHECK (
    termination_evidence_sha256 ~ '^[a-f0-9]{64}$'
  ),
  attested_by_provider_workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  signature_algorithm TEXT NOT NULL CHECK (signature_algorithm = 'Ed25519'),
  public_key_sha256 TEXT NOT NULL CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  attestation_issued_at TIMESTAMPTZ NOT NULL,
  attestation_payload_sha256 TEXT NOT NULL CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id, cancellation_revision),
  UNIQUE (
    termination_attestation_id, job_id, tenant_id,
    claim_id, cancellation_revision
  ),
  FOREIGN KEY (
    claim_id, job_id, tenant_id, envelope_sha256, assigned_workload_id
  ) REFERENCES research_job_execution_claims(
    claim_id, job_id, tenant_id, envelope_sha256, claimed_by_workload_id
  ),
  FOREIGN KEY (
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    assigned_workload_id, process_reference_sha256, envelope_sha256
  ) REFERENCES research_job_launch_attestations(
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    assigned_workload_id, process_reference_sha256, envelope_sha256
  ),
  FOREIGN KEY (
    cancellation_sequence_id, job_id, tenant_id,
    cancellation_source, cancellation_reason
  ) REFERENCES research_job_cancellations(
    sequence_id, job_id, tenant_id, source, reason
  ),
  FOREIGN KEY (
    tenant_id, attested_by_provider_workload_id,
    signing_key_id, public_key_sha256
  ) REFERENCES research_workload_signing_keys(
    tenant_id, workload_id, signing_key_id, public_key_sha256
  )
);

CREATE OR REPLACE FUNCTION cadence_validate_external_research_job_termination()
RETURNS TRIGGER AS $$
DECLARE
  effective_sequence BIGINT;
  effective_cancelled_at TIMESTAMPTZ;
  latest_cancelled_at TIMESTAMPTZ;
BEGIN
  SELECT cancellation.sequence_id, cancellation.cancelled_at
    INTO effective_sequence, effective_cancelled_at
  FROM research_job_cancellations AS cancellation
  WHERE cancellation.job_id = NEW.job_id AND cancellation.tenant_id = NEW.tenant_id
  ORDER BY CASE cancellation.source
    WHEN 'input-quarantined' THEN 3
    WHEN 'provider-drift' THEN 2
    ELSE 1 END DESC,
    cancellation.cancelled_at DESC, cancellation.sequence_id DESC
  LIMIT 1;
  SELECT MAX(cancellation.cancelled_at) INTO latest_cancelled_at
  FROM research_job_cancellations AS cancellation
  WHERE cancellation.job_id = NEW.job_id AND cancellation.tenant_id = NEW.tenant_id;

  IF effective_sequence IS DISTINCT FROM NEW.cancellation_sequence_id
    OR NEW.attestation_issued_at < effective_cancelled_at
    OR NEW.attestation_issued_at < latest_cancelled_at
    OR NOT EXISTS (
      SELECT 1 FROM research_workload_identities AS provider
      WHERE provider.tenant_id = NEW.tenant_id
        AND provider.workload_id = NEW.attested_by_provider_workload_id
        AND provider.purpose = 'research-job-provider'
    ) OR NOT EXISTS (
      SELECT 1
      FROM research_job_execution_claims AS claim
      INNER JOIN research_job_launch_attestations AS launch
        ON launch.launch_id = claim.launch_id
       AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
      INNER JOIN research_job_execution_gates AS gate
        ON gate.job_id = claim.job_id AND gate.tenant_id = claim.tenant_id
      WHERE claim.claim_id = NEW.claim_id AND claim.job_id = NEW.job_id
        AND claim.tenant_id = NEW.tenant_id
        AND claim.envelope_sha256 = NEW.envelope_sha256
        AND claim.claimed_by_workload_id = NEW.assigned_workload_id
        AND claim.dispatch_id = NEW.dispatch_id
        AND claim.dispatch_revision = NEW.dispatch_revision
        AND launch.process_reference_sha256 = NEW.process_reference_sha256
        AND launch.recorded_at <= NEW.attestation_issued_at
        AND claim.claimed_at <= NEW.attestation_issued_at
        AND gate.claimed AND gate.cancellation_requested
        AND gate.cancellation_revision = NEW.cancellation_revision
        AND gate.terminal_status IS NULL
    )
  THEN
    RAISE EXCEPTION 'external termination must bind the effective active cancellation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_external_termination_validate
BEFORE INSERT ON research_job_external_termination_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_validate_external_research_job_termination();

CREATE OR REPLACE FUNCTION cadence_lock_external_research_job_termination()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE research_job_execution_gates AS gate
  SET updated_at = CURRENT_TIMESTAMP
  WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
    AND gate.claimed AND gate.cancellation_requested
    AND gate.cancellation_revision = NEW.cancellation_revision
    AND gate.terminal_status IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'external termination transition is stale';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_external_termination_lock_gate
AFTER INSERT ON research_job_external_termination_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_lock_external_research_job_termination();
CREATE TRIGGER research_job_external_termination_append_only
BEFORE UPDATE OR DELETE ON research_job_external_termination_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_external_termination_prevent_truncate
BEFORE TRUNCATE ON research_job_external_termination_attestations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

ALTER TABLE research_job_terminal_receipts
  ADD COLUMN external_termination_attestation_id TEXT,
  ADD COLUMN external_termination_cancellation_revision BIGINT CHECK (
    external_termination_cancellation_revision > 0
  ),
  ADD CONSTRAINT research_job_terminal_external_termination_pair CHECK (
    (external_termination_attestation_id IS NULL
      AND external_termination_cancellation_revision IS NULL)
    OR (external_termination_attestation_id IS NOT NULL
      AND external_termination_cancellation_revision IS NOT NULL)
  ) NOT VALID,
  ADD CONSTRAINT research_job_terminal_external_termination_fk
  FOREIGN KEY (
    external_termination_attestation_id, job_id, tenant_id,
    claim_id, external_termination_cancellation_revision
  ) REFERENCES research_job_external_termination_attestations(
    termination_attestation_id, job_id, tenant_id,
    claim_id, cancellation_revision
  ) NOT VALID;

CREATE OR REPLACE FUNCTION cadence_advance_research_job_terminal_gate()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE research_job_execution_gates AS gate
  SET terminal_status = NEW.terminal_status,
      terminal_receipt_id = NEW.receipt_id,
      updated_at = CURRENT_TIMESTAMP
  WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
    AND gate.claimed AND gate.terminal_status IS NULL
    AND (
      (NEW.terminal_status = 'cancelled'
        AND gate.cancellation_requested
        AND EXISTS (
          SELECT 1 FROM research_job_cancellation_acknowledgements AS acknowledgement
          WHERE acknowledgement.job_id = NEW.job_id
            AND acknowledgement.tenant_id = NEW.tenant_id
            AND acknowledgement.claim_id = NEW.claim_id
            AND acknowledgement.acknowledgement_id =
              NEW.cancellation_acknowledgement_id
            AND acknowledgement.cancellation_revision = gate.cancellation_revision
            AND acknowledgement.cancellation_revision = NEW.cancellation_revision
            AND acknowledgement.attestation_issued_at <= NEW.attestation_issued_at
            AND acknowledgement.cancellation_sequence_id = (
              SELECT cancellation.sequence_id
              FROM research_job_cancellations AS cancellation
              WHERE cancellation.job_id = NEW.job_id
                AND cancellation.tenant_id = NEW.tenant_id
              ORDER BY CASE cancellation.source
                WHEN 'input-quarantined' THEN 3
                WHEN 'provider-drift' THEN 2
                ELSE 1 END DESC,
                cancellation.cancelled_at DESC, cancellation.sequence_id DESC
              LIMIT 1
            )
        )
        AND (
          NOT EXISTS (
            SELECT 1 FROM research_job_execution_claims AS legacy_claim
            WHERE legacy_claim.claim_id = NEW.claim_id
              AND legacy_claim.job_id = NEW.job_id
              AND legacy_claim.tenant_id = NEW.tenant_id
              AND legacy_claim.launch_id IS NOT NULL
          )
          OR EXISTS (
            SELECT 1
            FROM research_job_external_termination_attestations AS termination
            WHERE termination.termination_attestation_id =
                NEW.external_termination_attestation_id
              AND termination.job_id = NEW.job_id
              AND termination.tenant_id = NEW.tenant_id
              AND termination.claim_id = NEW.claim_id
              AND termination.cancellation_revision = gate.cancellation_revision
              AND termination.cancellation_revision = NEW.cancellation_revision
              AND termination.attestation_issued_at <= NEW.attestation_issued_at
          )
        ))
      OR (NEW.terminal_status IN ('succeeded', 'failed')
        AND NOT gate.cancellation_requested)
    );
  IF NOT FOUND THEN
    RAISE EXCEPTION 'research job terminal transition is illegal';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
