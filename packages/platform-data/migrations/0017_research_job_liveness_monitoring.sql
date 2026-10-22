ALTER TABLE research_job_execution_gates
  ADD COLUMN lease_duration_seconds INTEGER NOT NULL DEFAULT 90 CHECK (
    lease_duration_seconds BETWEEN 1 AND 300
  ),
  ADD COLUMN lease_started_at TIMESTAMPTZ,
  ADD COLUMN lease_expires_at TIMESTAMPTZ;

UPDATE research_job_execution_gates AS gate
SET lease_started_at = claim.claimed_at,
    lease_expires_at = COALESCE(
      gate.last_heartbeat_at + (gate.lease_duration_seconds * INTERVAL '1 second'),
      claim.claimed_at + (gate.lease_duration_seconds * INTERVAL '1 second')
    )
FROM research_job_execution_claims AS claim
WHERE gate.job_id = claim.job_id AND gate.tenant_id = claim.tenant_id
  AND gate.claimed;

ALTER TABLE research_job_execution_gates
  ADD CONSTRAINT research_job_execution_gate_lease_tuple CHECK (
    (NOT claimed AND lease_started_at IS NULL AND lease_expires_at IS NULL)
    OR (claimed AND lease_started_at IS NOT NULL
      AND lease_expires_at IS NOT NULL
      AND lease_expires_at > lease_started_at)
  ) NOT VALID;

CREATE TABLE research_job_liveness_snapshots (
  snapshot_id TEXT PRIMARY KEY CHECK (
    snapshot_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'awaiting-first-heartbeat', 'fresh', 'overdue',
    'cancellation-pending', 'cancellation-observed', 'terminal'
  )),
  lease_duration_seconds INTEGER NOT NULL CHECK (
    lease_duration_seconds BETWEEN 1 AND 300
  ),
  lease_started_at TIMESTAMPTZ NOT NULL,
  lease_expires_at TIMESTAMPTZ NOT NULL,
  lease_expired BOOLEAN NOT NULL,
  last_heartbeat_id TEXT,
  last_heartbeat_sequence BIGINT NOT NULL CHECK (last_heartbeat_sequence >= 0),
  last_heartbeat_state TEXT CHECK (
    last_heartbeat_state IN ('running', 'cancellation-observed')
  ),
  last_heartbeat_cancellation_revision BIGINT CHECK (
    last_heartbeat_cancellation_revision >= 0
  ),
  cancellation_revision BIGINT NOT NULL CHECK (cancellation_revision >= 0),
  terminal_status TEXT CHECK (terminal_status IN ('succeeded', 'failed', 'cancelled')),
  alert_required BOOLEAN NOT NULL,
  generated_by_actor_id TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  external_process_liveness_verified BOOLEAN NOT NULL DEFAULT FALSE CHECK (
    NOT external_process_liveness_verified
  ),
  alert_delivery_evidence_present BOOLEAN NOT NULL DEFAULT FALSE CHECK (
    NOT alert_delivery_evidence_present
  ),
  production_gate_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (
    NOT production_gate_eligible
  ),
  FOREIGN KEY (claim_id, job_id, tenant_id)
    REFERENCES research_job_execution_claims(claim_id, job_id, tenant_id),
  FOREIGN KEY (
    last_heartbeat_id, job_id, tenant_id, last_heartbeat_sequence
  ) REFERENCES research_job_heartbeats(
    heartbeat_id, job_id, tenant_id, heartbeat_sequence
  ),
  FOREIGN KEY (tenant_id, generated_by_actor_id)
    REFERENCES tenant_memberships(tenant_id, actor_id),
  CHECK (
    (last_heartbeat_sequence = 0
      AND last_heartbeat_id IS NULL AND last_heartbeat_state IS NULL
      AND last_heartbeat_cancellation_revision IS NULL)
    OR (last_heartbeat_sequence > 0
      AND last_heartbeat_id IS NOT NULL AND last_heartbeat_state IS NOT NULL
      AND last_heartbeat_cancellation_revision IS NOT NULL)
  ),
  CHECK ((status = 'terminal') = (terminal_status IS NOT NULL))
);

CREATE TRIGGER research_job_liveness_snapshots_append_only
BEFORE UPDATE OR DELETE ON research_job_liveness_snapshots
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_liveness_snapshots_prevent_truncate
BEFORE TRUNCATE ON research_job_liveness_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

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
