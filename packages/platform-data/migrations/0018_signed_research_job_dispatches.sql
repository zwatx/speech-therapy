ALTER TABLE research_workload_identities
  DROP CONSTRAINT research_workload_identities_purpose_check,
  ADD CONSTRAINT research_workload_identities_purpose_check CHECK (
    purpose IN ('research-job-runner', 'research-job-scheduler')
  );

ALTER TABLE research_job_approvals
  ADD CONSTRAINT research_job_approval_envelope_identity
  UNIQUE (job_id, tenant_id, envelope_sha256);

ALTER TABLE research_job_execution_gates
  ADD COLUMN dispatch_revision BIGINT NOT NULL DEFAULT 0 CHECK (
    dispatch_revision >= 0
  ),
  ADD COLUMN active_dispatch_id TEXT,
  ADD COLUMN active_dispatch_workload_id TEXT,
  ADD COLUMN active_dispatch_expires_at TIMESTAMPTZ,
  ADD CONSTRAINT research_job_execution_gate_dispatch_tuple CHECK (
    (dispatch_revision = 0
      AND active_dispatch_id IS NULL
      AND active_dispatch_workload_id IS NULL
      AND active_dispatch_expires_at IS NULL)
    OR (dispatch_revision > 0
      AND active_dispatch_id IS NOT NULL
      AND active_dispatch_workload_id IS NOT NULL
      AND active_dispatch_expires_at IS NOT NULL)
  );

CREATE TABLE research_job_dispatches (
  dispatch_id TEXT PRIMARY KEY CHECK (
    dispatch_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  dispatch_revision BIGINT NOT NULL CHECK (dispatch_revision > 0),
  assigned_workload_id TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  dispatched_by_workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  signature_algorithm TEXT NOT NULL CHECK (signature_algorithm = 'Ed25519'),
  public_key_sha256 TEXT NOT NULL CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  attestation_issued_at TIMESTAMPTZ NOT NULL,
  attestation_payload_sha256 TEXT NOT NULL CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id, dispatch_revision),
  UNIQUE (
    dispatch_id, job_id, tenant_id, dispatch_revision, assigned_workload_id
  ),
  UNIQUE (
    dispatch_id, job_id, tenant_id, dispatch_revision,
    assigned_workload_id, envelope_sha256
  ),
  FOREIGN KEY (job_id, tenant_id, envelope_sha256)
    REFERENCES research_job_approvals(job_id, tenant_id, envelope_sha256),
  FOREIGN KEY (tenant_id, assigned_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  FOREIGN KEY (
    tenant_id, dispatched_by_workload_id, signing_key_id, public_key_sha256
  ) REFERENCES research_workload_signing_keys(
    tenant_id, workload_id, signing_key_id, public_key_sha256
  ),
  CHECK (expires_at > attestation_issued_at),
  CHECK (expires_at <= attestation_issued_at + INTERVAL '15 minutes')
);

ALTER TABLE research_job_execution_gates
  ADD CONSTRAINT research_job_execution_gate_active_dispatch_fk
  FOREIGN KEY (
    active_dispatch_id, job_id, tenant_id, dispatch_revision,
    active_dispatch_workload_id
  ) REFERENCES research_job_dispatches(
    dispatch_id, job_id, tenant_id, dispatch_revision, assigned_workload_id
  );

ALTER TABLE research_job_execution_claims
  ADD COLUMN dispatch_id TEXT,
  ADD COLUMN dispatch_revision BIGINT CHECK (dispatch_revision > 0),
  ADD CONSTRAINT research_job_execution_claim_dispatch_pair CHECK (
    (dispatch_id IS NULL AND dispatch_revision IS NULL)
    OR (dispatch_id IS NOT NULL AND dispatch_revision IS NOT NULL)
  ) NOT VALID,
  ADD CONSTRAINT research_job_execution_claim_dispatch_fk
  FOREIGN KEY (
    dispatch_id, job_id, tenant_id, dispatch_revision,
    claimed_by_workload_id, envelope_sha256
  ) REFERENCES research_job_dispatches(
    dispatch_id, job_id, tenant_id, dispatch_revision,
    assigned_workload_id, envelope_sha256
  ) NOT VALID;

CREATE OR REPLACE FUNCTION cadence_advance_research_job_dispatch_gate()
RETURNS TRIGGER AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM research_workload_identities AS scheduler
    WHERE scheduler.tenant_id = NEW.tenant_id
      AND scheduler.workload_id = NEW.dispatched_by_workload_id
      AND scheduler.purpose = 'research-job-scheduler'
  ) OR NOT EXISTS (
    SELECT 1 FROM research_workload_identities AS runner
    WHERE runner.tenant_id = NEW.tenant_id
      AND runner.workload_id = NEW.assigned_workload_id
      AND runner.purpose = 'research-job-runner'
  ) THEN
    RAISE EXCEPTION 'research job dispatch principals are invalid';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM research_job_approvals AS approval
    WHERE approval.job_id = NEW.job_id AND approval.tenant_id = NEW.tenant_id
      AND approval.envelope_sha256 = NEW.envelope_sha256
      AND approval.approved_at <= NEW.attestation_issued_at
  ) THEN
    RAISE EXCEPTION 'research job dispatch predates approval';
  END IF;

  UPDATE research_job_execution_gates AS gate
  SET dispatch_revision = NEW.dispatch_revision,
      active_dispatch_id = NEW.dispatch_id,
      active_dispatch_workload_id = NEW.assigned_workload_id,
      active_dispatch_expires_at = NEW.expires_at,
      updated_at = CURRENT_TIMESTAMP
  WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
    AND NOT gate.claimed AND NOT gate.cancellation_requested
    AND gate.terminal_status IS NULL
    AND gate.dispatch_revision = NEW.dispatch_revision - 1
    AND NEW.expires_at > CURRENT_TIMESTAMP;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'research job dispatch transition is illegal';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_dispatches_advance_gate
AFTER INSERT ON research_job_dispatches
FOR EACH ROW EXECUTE FUNCTION cadence_advance_research_job_dispatch_gate();
CREATE TRIGGER research_job_dispatches_append_only
BEFORE UPDATE OR DELETE ON research_job_dispatches
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_dispatches_prevent_truncate
BEFORE TRUNCATE ON research_job_dispatches
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

CREATE OR REPLACE FUNCTION cadence_require_signed_research_workload_claim()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.claimed_by_workload_id IS NULL
    OR NEW.signing_key_id IS NULL
    OR NEW.signature_algorithm <> 'Ed25519'
    OR NEW.attestation_payload_sha256 IS NULL
    OR NEW.signature_sha256 IS NULL
    OR NEW.dispatch_id IS NULL
    OR NEW.dispatch_revision IS NULL
  THEN
    RAISE EXCEPTION 'new research job claims require a signed dispatched workload identity';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
    OR NEW.dispatch_revision < OLD.dispatch_revision
    OR NEW.dispatch_revision > OLD.dispatch_revision + 1
    OR (NEW.dispatch_revision > OLD.dispatch_revision
      AND (OLD.claimed OR NEW.claimed OR NEW.cancellation_requested
        OR NEW.terminal_status IS NOT NULL))
    OR (NEW.dispatch_revision = OLD.dispatch_revision
      AND (NEW.active_dispatch_id IS DISTINCT FROM OLD.active_dispatch_id
        OR NEW.active_dispatch_workload_id IS DISTINCT
          FROM OLD.active_dispatch_workload_id
        OR NEW.active_dispatch_expires_at IS DISTINCT
          FROM OLD.active_dispatch_expires_at))
    OR (NEW.lease_duration_seconds IS DISTINCT FROM OLD.lease_duration_seconds
      AND (OLD.claimed OR NOT NEW.claimed))
    OR (OLD.lease_started_at IS NOT NULL
      AND NEW.lease_started_at IS DISTINCT FROM OLD.lease_started_at)
    OR (OLD.lease_expires_at IS NOT NULL
      AND NEW.lease_expires_at < OLD.lease_expires_at)
    OR (NEW.lease_expires_at > OLD.lease_expires_at
      AND NEW.last_heartbeat_sequence <= OLD.last_heartbeat_sequence)
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
