ALTER TABLE research_job_execution_gates
  ADD COLUMN last_heartbeat_sequence BIGINT NOT NULL DEFAULT 0 CHECK (
    last_heartbeat_sequence >= 0
  ),
  ADD COLUMN last_heartbeat_id TEXT,
  ADD COLUMN last_heartbeat_at TIMESTAMPTZ,
  ADD CONSTRAINT research_job_execution_gate_heartbeat_tuple CHECK (
    (last_heartbeat_sequence = 0
      AND last_heartbeat_id IS NULL AND last_heartbeat_at IS NULL)
    OR (last_heartbeat_sequence > 0
      AND last_heartbeat_id IS NOT NULL AND last_heartbeat_at IS NOT NULL)
  );

CREATE TABLE research_job_heartbeats (
  heartbeat_id TEXT PRIMARY KEY CHECK (
    heartbeat_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  heartbeat_sequence BIGINT NOT NULL CHECK (heartbeat_sequence > 0),
  runner_state TEXT NOT NULL CHECK (
    runner_state IN ('running', 'cancellation-observed')
  ),
  cancellation_revision BIGINT NOT NULL CHECK (cancellation_revision >= 0),
  process_reference_sha256 TEXT NOT NULL CHECK (
    process_reference_sha256 ~ '^[a-f0-9]{64}$'
  ),
  liveness_evidence_sha256 TEXT NOT NULL CHECK (
    liveness_evidence_sha256 ~ '^[a-f0-9]{64}$'
  ),
  reported_by_workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  signature_algorithm TEXT NOT NULL CHECK (signature_algorithm = 'Ed25519'),
  public_key_sha256 TEXT NOT NULL CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  attestation_issued_at TIMESTAMPTZ NOT NULL,
  attestation_payload_sha256 TEXT NOT NULL CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id, claim_id, heartbeat_sequence),
  UNIQUE (heartbeat_id, job_id, tenant_id, heartbeat_sequence),
  FOREIGN KEY (
    claim_id, job_id, tenant_id, envelope_sha256, reported_by_workload_id
  ) REFERENCES research_job_execution_claims(
    claim_id, job_id, tenant_id, envelope_sha256, claimed_by_workload_id
  ),
  FOREIGN KEY (
    tenant_id, reported_by_workload_id, signing_key_id, public_key_sha256
  ) REFERENCES research_workload_signing_keys(
    tenant_id, workload_id, signing_key_id, public_key_sha256
  ),
  CHECK (
    (runner_state = 'running' AND cancellation_revision = 0)
    OR (runner_state = 'cancellation-observed' AND cancellation_revision > 0)
  )
);

ALTER TABLE research_job_execution_gates
  ADD CONSTRAINT research_job_execution_gate_last_heartbeat_fk
  FOREIGN KEY (
    last_heartbeat_id, job_id, tenant_id, last_heartbeat_sequence
  ) REFERENCES research_job_heartbeats(
    heartbeat_id, job_id, tenant_id, heartbeat_sequence
  );

CREATE OR REPLACE FUNCTION cadence_advance_research_job_heartbeat_gate()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE research_job_execution_gates AS gate
  SET last_heartbeat_sequence = NEW.heartbeat_sequence,
      last_heartbeat_id = NEW.heartbeat_id,
      last_heartbeat_at = NEW.attestation_issued_at,
      updated_at = CURRENT_TIMESTAMP
  WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
    AND gate.claimed AND gate.terminal_status IS NULL
    AND gate.last_heartbeat_sequence = NEW.heartbeat_sequence - 1
    AND (gate.last_heartbeat_at IS NULL
      OR NEW.attestation_issued_at >= gate.last_heartbeat_at)
    AND EXISTS (
      SELECT 1 FROM research_job_execution_claims AS claim
      WHERE claim.claim_id = NEW.claim_id AND claim.job_id = NEW.job_id
        AND claim.tenant_id = NEW.tenant_id
        AND claim.claimed_at <= NEW.attestation_issued_at
    )
    AND (
      (NEW.runner_state = 'running'
        AND NOT gate.cancellation_requested
        AND NEW.cancellation_revision = 0)
      OR (NEW.runner_state = 'cancellation-observed'
        AND gate.cancellation_requested
        AND NEW.cancellation_revision = gate.cancellation_revision
        AND NEW.attestation_issued_at >= (
          SELECT MAX(cancellation.cancelled_at)
          FROM research_job_cancellations AS cancellation
          WHERE cancellation.job_id = NEW.job_id
            AND cancellation.tenant_id = NEW.tenant_id
        ))
    );
  IF NOT FOUND THEN
    RAISE EXCEPTION 'research job heartbeat transition is illegal';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_heartbeats_advance_gate
AFTER INSERT ON research_job_heartbeats
FOR EACH ROW EXECUTE FUNCTION cadence_advance_research_job_heartbeat_gate();
CREATE TRIGGER research_job_heartbeats_append_only
BEFORE UPDATE OR DELETE ON research_job_heartbeats
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_heartbeats_prevent_truncate
BEFORE TRUNCATE ON research_job_heartbeats
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

CREATE OR REPLACE FUNCTION cadence_preserve_research_job_execution_gate()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.job_id IS DISTINCT FROM OLD.job_id
    OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR (OLD.claimed AND NOT NEW.claimed)
    OR (OLD.cancellation_requested AND NOT NEW.cancellation_requested)
    OR NEW.cancellation_revision < OLD.cancellation_revision
    OR (NEW.cancellation_revision > OLD.cancellation_revision
      AND NOT NEW.cancellation_requested)
    OR NEW.last_heartbeat_sequence < OLD.last_heartbeat_sequence
    OR NEW.last_heartbeat_sequence > OLD.last_heartbeat_sequence + 1
    OR (OLD.last_heartbeat_at IS NOT NULL
      AND NEW.last_heartbeat_at < OLD.last_heartbeat_at)
    OR (NEW.last_heartbeat_sequence = OLD.last_heartbeat_sequence
      AND (NEW.last_heartbeat_id IS DISTINCT FROM OLD.last_heartbeat_id
        OR NEW.last_heartbeat_at IS DISTINCT FROM OLD.last_heartbeat_at))
    OR (OLD.terminal_status IS NOT NULL
      AND NEW.terminal_status IS DISTINCT FROM OLD.terminal_status)
    OR (OLD.terminal_receipt_id IS NOT NULL
      AND NEW.terminal_receipt_id IS DISTINCT FROM OLD.terminal_receipt_id)
  THEN
    RAISE EXCEPTION 'research job execution gate is monotonic';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
