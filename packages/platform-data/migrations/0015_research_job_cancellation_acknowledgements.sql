ALTER TABLE research_job_cancellations
  ADD CONSTRAINT research_job_cancellation_complete_identity
  UNIQUE (sequence_id, job_id, tenant_id, source, reason);

ALTER TABLE research_job_execution_gates
  ADD COLUMN cancellation_revision BIGINT NOT NULL DEFAULT 0 CHECK (
    cancellation_revision >= 0
  );

WITH revisions AS (
  SELECT job_id, tenant_id, COUNT(*)::BIGINT AS cancellation_revision
  FROM research_job_cancellations
  GROUP BY job_id, tenant_id
)
UPDATE research_job_execution_gates AS gate
SET cancellation_revision = revisions.cancellation_revision
FROM revisions
WHERE gate.job_id = revisions.job_id AND gate.tenant_id = revisions.tenant_id;

CREATE TABLE research_job_cancellation_acknowledgements (
  acknowledgement_id TEXT PRIMARY KEY CHECK (
    acknowledgement_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
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
  termination_outcome TEXT NOT NULL CHECK (
    termination_outcome IN ('not-started', 'process-stopped')
  ),
  process_reference_sha256 TEXT CHECK (
    process_reference_sha256 ~ '^[a-f0-9]{64}$'
  ),
  termination_evidence_sha256 TEXT NOT NULL CHECK (
    termination_evidence_sha256 ~ '^[a-f0-9]{64}$'
  ),
  acknowledged_by_workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  signature_algorithm TEXT NOT NULL CHECK (signature_algorithm = 'Ed25519'),
  public_key_sha256 TEXT NOT NULL CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  attestation_issued_at TIMESTAMPTZ NOT NULL,
  attestation_payload_sha256 TEXT NOT NULL CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id, cancellation_sequence_id),
  UNIQUE (
    acknowledgement_id, job_id, tenant_id, claim_id, cancellation_revision
  ),
  FOREIGN KEY (
    cancellation_sequence_id, job_id, tenant_id,
    cancellation_source, cancellation_reason
  ) REFERENCES research_job_cancellations(
    sequence_id, job_id, tenant_id, source, reason
  ),
  FOREIGN KEY (
    claim_id, job_id, tenant_id, envelope_sha256, acknowledged_by_workload_id
  ) REFERENCES research_job_execution_claims(
    claim_id, job_id, tenant_id, envelope_sha256, claimed_by_workload_id
  ),
  FOREIGN KEY (tenant_id, acknowledged_by_workload_id)
    REFERENCES research_workload_identities(tenant_id, workload_id),
  FOREIGN KEY (
    tenant_id, acknowledged_by_workload_id, signing_key_id, public_key_sha256
  ) REFERENCES research_workload_signing_keys(
    tenant_id, workload_id, signing_key_id, public_key_sha256
  ),
  CHECK (
    (termination_outcome = 'not-started' AND process_reference_sha256 IS NULL)
    OR (termination_outcome = 'process-stopped' AND process_reference_sha256 IS NOT NULL)
  )
);

CREATE OR REPLACE FUNCTION cadence_validate_research_job_cancellation_acknowledgement()
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
      SELECT 1 FROM research_job_execution_gates AS gate
      WHERE gate.job_id = NEW.job_id AND gate.tenant_id = NEW.tenant_id
        AND gate.claimed AND gate.cancellation_requested
        AND gate.cancellation_revision = NEW.cancellation_revision
        AND gate.terminal_status IS NULL
    )
  THEN
    RAISE EXCEPTION 'cancellation acknowledgement must bind the effective active cancellation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_cancellation_acknowledgements_validate
BEFORE INSERT ON research_job_cancellation_acknowledgements
FOR EACH ROW EXECUTE FUNCTION cadence_validate_research_job_cancellation_acknowledgement();
CREATE TRIGGER research_job_cancellation_acknowledgements_append_only
BEFORE UPDATE OR DELETE ON research_job_cancellation_acknowledgements
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_cancellation_acknowledgements_prevent_truncate
BEFORE TRUNCATE ON research_job_cancellation_acknowledgements
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

ALTER TABLE research_job_terminal_receipts
  ADD COLUMN cancellation_acknowledgement_id TEXT,
  ADD COLUMN cancellation_revision BIGINT CHECK (cancellation_revision > 0),
  ADD CONSTRAINT research_job_terminal_cancellation_binding CHECK (
    (terminal_status = 'cancelled'
      AND cancellation_acknowledgement_id IS NOT NULL
      AND cancellation_revision IS NOT NULL)
    OR (terminal_status <> 'cancelled'
      AND cancellation_acknowledgement_id IS NULL
      AND cancellation_revision IS NULL)
  ) NOT VALID,
  ADD CONSTRAINT research_job_terminal_cancellation_acknowledgement_fk
  FOREIGN KEY (
    cancellation_acknowledgement_id, job_id, tenant_id, claim_id,
    cancellation_revision
  ) REFERENCES research_job_cancellation_acknowledgements(
    acknowledgement_id, job_id, tenant_id, claim_id, cancellation_revision
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

CREATE OR REPLACE FUNCTION cadence_cancel_research_jobs_for_quarantined_artifact()
RETURNS TRIGGER AS $$
BEGIN
  WITH candidates AS MATERIALIZED (
    SELECT gate.job_id, gate.tenant_id
    FROM research_job_execution_gates AS gate
    WHERE gate.tenant_id = NEW.tenant_id
      AND gate.terminal_status IS NULL
      AND EXISTS (
        SELECT 1 FROM research_job_inputs AS input
        WHERE input.job_id = gate.job_id AND input.tenant_id = gate.tenant_id
          AND input.artifact_id = NEW.artifact_id
      )
    FOR UPDATE OF gate
  ), cancelled AS (
    INSERT INTO research_job_cancellations (
      job_id, tenant_id, source, reason, requested_by_actor_id
    )
    SELECT candidates.job_id, candidates.tenant_id,
      'input-quarantined', 'input-quarantined', NULL
    FROM candidates
    ON CONFLICT (job_id, tenant_id, source) DO NOTHING
    RETURNING job_id, tenant_id
  )
  UPDATE research_job_execution_gates AS gate
  SET cancellation_requested = TRUE,
      cancellation_revision = gate.cancellation_revision + 1,
      updated_at = CURRENT_TIMESTAMP
  FROM cancelled
  WHERE gate.job_id = cancelled.job_id AND gate.tenant_id = cancelled.tenant_id
    AND gate.terminal_status IS NULL;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cadence_cancel_research_jobs_for_provider_drift()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.outcome <> 'consistent' THEN
    WITH candidates AS MATERIALIZED (
      SELECT gate.job_id, gate.tenant_id
      FROM research_job_execution_gates AS gate
      WHERE gate.tenant_id = NEW.tenant_id
        AND gate.terminal_status IS NULL
        AND EXISTS (
          SELECT 1 FROM research_job_inputs AS input
          WHERE input.job_id = gate.job_id AND input.tenant_id = gate.tenant_id
            AND input.binding_id = NEW.binding_id
            AND input.artifact_id = NEW.artifact_id
        )
      FOR UPDATE OF gate
    ), cancelled AS (
      INSERT INTO research_job_cancellations (
        job_id, tenant_id, source, reason, requested_by_actor_id
      )
      SELECT candidates.job_id, candidates.tenant_id,
        'provider-drift', 'provider-drift', NULL
      FROM candidates
      ON CONFLICT (job_id, tenant_id, source) DO NOTHING
      RETURNING job_id, tenant_id
    )
    UPDATE research_job_execution_gates AS gate
    SET cancellation_requested = TRUE,
        cancellation_revision = gate.cancellation_revision + 1,
        updated_at = CURRENT_TIMESTAMP
    FROM cancelled
    WHERE gate.job_id = cancelled.job_id AND gate.tenant_id = cancelled.tenant_id
      AND gate.terminal_status IS NULL;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
