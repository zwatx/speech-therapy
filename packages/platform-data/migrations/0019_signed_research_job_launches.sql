ALTER TABLE research_workload_identities
  DROP CONSTRAINT research_workload_identities_purpose_check,
  ADD CONSTRAINT research_workload_identities_purpose_check CHECK (
    purpose IN (
      'research-job-runner', 'research-job-scheduler', 'research-job-provider'
    )
  );

CREATE TABLE research_job_launch_attestations (
  launch_id TEXT PRIMARY KEY CHECK (
    launch_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  dispatch_id TEXT NOT NULL,
  dispatch_revision BIGINT NOT NULL CHECK (dispatch_revision > 0),
  assigned_workload_id TEXT NOT NULL,
  runner_image_digest TEXT NOT NULL CHECK (
    runner_image_digest ~ '^sha256:[a-f0-9]{64}$'
  ),
  process_reference_sha256 TEXT NOT NULL CHECK (
    process_reference_sha256 ~ '^[a-f0-9]{64}$'
  ),
  execution_identity_sha256 TEXT NOT NULL CHECK (
    execution_identity_sha256 ~ '^[a-f0-9]{64}$'
  ),
  network_policy_sha256 TEXT NOT NULL CHECK (
    network_policy_sha256 ~ '^[a-f0-9]{64}$'
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
  UNIQUE (dispatch_id, job_id, tenant_id, dispatch_revision),
  UNIQUE (
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    assigned_workload_id
  ),
  UNIQUE (
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    assigned_workload_id, envelope_sha256
  ),
  FOREIGN KEY (
    dispatch_id, job_id, tenant_id, dispatch_revision,
    assigned_workload_id, envelope_sha256
  ) REFERENCES research_job_dispatches(
    dispatch_id, job_id, tenant_id, dispatch_revision,
    assigned_workload_id, envelope_sha256
  ),
  FOREIGN KEY (
    tenant_id, attested_by_provider_workload_id,
    signing_key_id, public_key_sha256
  ) REFERENCES research_workload_signing_keys(
    tenant_id, workload_id, signing_key_id, public_key_sha256
  )
);

ALTER TABLE research_job_execution_gates
  ADD COLUMN active_launch_id TEXT,
  ADD CONSTRAINT research_job_execution_gate_active_launch_fk
  FOREIGN KEY (
    active_launch_id, job_id, tenant_id, active_dispatch_id,
    dispatch_revision, active_dispatch_workload_id
  ) REFERENCES research_job_launch_attestations(
    launch_id, job_id, tenant_id, dispatch_id,
    dispatch_revision, assigned_workload_id
  );

ALTER TABLE research_job_execution_claims
  ADD COLUMN launch_id TEXT,
  ADD CONSTRAINT research_job_execution_claim_launch_binding CHECK (
    launch_id IS NULL OR (dispatch_id IS NOT NULL AND dispatch_revision IS NOT NULL)
  ) NOT VALID,
  ADD CONSTRAINT research_job_execution_claim_launch_fk
  FOREIGN KEY (
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    claimed_by_workload_id, envelope_sha256
  ) REFERENCES research_job_launch_attestations(
    launch_id, job_id, tenant_id, dispatch_id, dispatch_revision,
    assigned_workload_id, envelope_sha256
  ) NOT VALID;

CREATE OR REPLACE FUNCTION cadence_validate_research_job_launch_attestation()
RETURNS TRIGGER AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM research_workload_identities AS provider
    WHERE provider.tenant_id = NEW.tenant_id
      AND provider.workload_id = NEW.attested_by_provider_workload_id
      AND provider.purpose = 'research-job-provider'
  ) OR NOT EXISTS (
    SELECT 1
    FROM research_job_dispatches AS dispatch
    INNER JOIN research_job_execution_gates AS gate
      ON gate.job_id = dispatch.job_id AND gate.tenant_id = dispatch.tenant_id
     AND gate.active_dispatch_id = dispatch.dispatch_id
     AND gate.dispatch_revision = dispatch.dispatch_revision
     AND gate.active_dispatch_workload_id = dispatch.assigned_workload_id
    INNER JOIN research_job_requests AS request
      ON request.id = dispatch.job_id AND request.tenant_id = dispatch.tenant_id
    INNER JOIN research_workload_identities AS runner
      ON runner.tenant_id = dispatch.tenant_id
     AND runner.workload_id = dispatch.assigned_workload_id
     AND runner.purpose = 'research-job-runner'
    WHERE dispatch.dispatch_id = NEW.dispatch_id
      AND dispatch.job_id = NEW.job_id AND dispatch.tenant_id = NEW.tenant_id
      AND dispatch.dispatch_revision = NEW.dispatch_revision
      AND dispatch.assigned_workload_id = NEW.assigned_workload_id
      AND dispatch.envelope_sha256 = NEW.envelope_sha256
      AND dispatch.recorded_at <= NEW.attestation_issued_at
      AND dispatch.expires_at > NEW.attestation_issued_at
      AND dispatch.expires_at > CURRENT_TIMESTAMP
      AND request.runner_image_digest = NEW.runner_image_digest
      AND NOT gate.claimed AND NOT gate.cancellation_requested
      AND gate.terminal_status IS NULL
  ) THEN
    RAISE EXCEPTION 'research job launch attestation is stale or invalid';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_launch_attestations_validate
BEFORE INSERT ON research_job_launch_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_validate_research_job_launch_attestation();

CREATE OR REPLACE FUNCTION cadence_advance_research_job_launch_gate()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE research_job_execution_gates AS gate
  SET active_launch_id = NEW.launch_id,
      updated_at = CURRENT_TIMESTAMP
  WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
    AND gate.active_dispatch_id = NEW.dispatch_id
    AND gate.dispatch_revision = NEW.dispatch_revision
    AND gate.active_dispatch_workload_id = NEW.assigned_workload_id
    AND gate.active_launch_id IS NULL
    AND NOT gate.claimed AND NOT gate.cancellation_requested
    AND gate.terminal_status IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'research job launch transition is illegal';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_launch_attestations_advance_gate
AFTER INSERT ON research_job_launch_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_advance_research_job_launch_gate();
CREATE TRIGGER research_job_launch_attestations_append_only
BEFORE UPDATE OR DELETE ON research_job_launch_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_launch_attestations_prevent_truncate
BEFORE TRUNCATE ON research_job_launch_attestations
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
    OR NEW.launch_id IS NULL
  THEN
    RAISE EXCEPTION 'new research job claims require a signed provider-launched workload identity';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cadence_advance_research_job_heartbeat_gate()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE research_job_execution_gates AS gate
  SET last_heartbeat_sequence = NEW.heartbeat_sequence,
      last_heartbeat_id = NEW.heartbeat_id,
      last_heartbeat_at = NEW.attestation_issued_at,
      lease_expires_at = CURRENT_TIMESTAMP
        + (gate.lease_duration_seconds * INTERVAL '1 second'),
      updated_at = CURRENT_TIMESTAMP
  WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
    AND gate.claimed AND gate.terminal_status IS NULL
    AND gate.last_heartbeat_sequence = NEW.heartbeat_sequence - 1
    AND (gate.last_heartbeat_at IS NULL
      OR NEW.attestation_issued_at >= gate.last_heartbeat_at)
    AND EXISTS (
      SELECT 1 FROM research_job_execution_claims AS claim
      LEFT JOIN research_job_launch_attestations AS launch
        ON launch.launch_id = claim.launch_id
       AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
      WHERE claim.claim_id = NEW.claim_id AND claim.job_id = NEW.job_id
        AND claim.tenant_id = NEW.tenant_id
        AND claim.claimed_at <= NEW.attestation_issued_at
        AND (claim.launch_id IS NULL
          OR launch.process_reference_sha256 = NEW.process_reference_sha256)
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

CREATE OR REPLACE FUNCTION cadence_validate_launch_bound_cancellation_acknowledgement()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM research_job_execution_claims AS claim
    WHERE claim.claim_id = NEW.claim_id AND claim.job_id = NEW.job_id
      AND claim.tenant_id = NEW.tenant_id AND claim.launch_id IS NOT NULL
  ) AND NOT EXISTS (
    SELECT 1 FROM research_job_execution_claims AS claim
    INNER JOIN research_job_launch_attestations AS launch
      ON launch.launch_id = claim.launch_id
     AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
    WHERE claim.claim_id = NEW.claim_id AND claim.job_id = NEW.job_id
      AND claim.tenant_id = NEW.tenant_id
      AND NEW.termination_outcome = 'process-stopped'
      AND NEW.process_reference_sha256 = launch.process_reference_sha256
  ) THEN
    RAISE EXCEPTION 'launched research jobs require matching stopped-process evidence';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_cancellation_acknowledgements_validate_launch
BEFORE INSERT ON research_job_cancellation_acknowledgements
FOR EACH ROW EXECUTE FUNCTION
  cadence_validate_launch_bound_cancellation_acknowledgement();

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
      active_launch_id = NULL,
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
        OR NEW.terminal_status IS NOT NULL OR OLD.active_launch_id IS NOT NULL
        OR NEW.active_launch_id IS NOT NULL))
    OR (NEW.dispatch_revision = OLD.dispatch_revision
      AND (NEW.active_dispatch_id IS DISTINCT FROM OLD.active_dispatch_id
        OR NEW.active_dispatch_workload_id IS DISTINCT
          FROM OLD.active_dispatch_workload_id
        OR NEW.active_dispatch_expires_at IS DISTINCT
          FROM OLD.active_dispatch_expires_at))
    OR (NEW.dispatch_revision = OLD.dispatch_revision
      AND OLD.active_launch_id IS NOT NULL
      AND NEW.active_launch_id IS DISTINCT FROM OLD.active_launch_id)
    OR (NEW.dispatch_revision = OLD.dispatch_revision
      AND OLD.active_launch_id IS NULL AND NEW.active_launch_id IS NOT NULL
      AND (OLD.claimed OR NEW.claimed OR NEW.cancellation_requested
        OR NEW.terminal_status IS NOT NULL))
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
