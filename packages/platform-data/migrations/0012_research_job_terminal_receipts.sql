ALTER TABLE research_job_execution_gates
  ADD COLUMN IF NOT EXISTS terminal_status TEXT CHECK (
    terminal_status IN ('succeeded', 'failed', 'cancelled')
  ),
  ADD COLUMN IF NOT EXISTS terminal_receipt_id TEXT CHECK (
    terminal_receipt_id IS NULL
    OR terminal_receipt_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  ADD CONSTRAINT research_job_execution_gate_terminal_pair CHECK (
    (terminal_status IS NULL AND terminal_receipt_id IS NULL)
    OR (terminal_status IS NOT NULL AND terminal_receipt_id IS NOT NULL)
  );

ALTER TABLE research_job_execution_claims
  ADD CONSTRAINT research_job_execution_claim_identity
  UNIQUE (claim_id, job_id, tenant_id),
  ADD CONSTRAINT research_job_execution_claim_envelope_identity
  UNIQUE (claim_id, job_id, tenant_id, envelope_sha256);

ALTER TABLE research_job_requests
  ADD CONSTRAINT research_job_reserved_output_identity
  UNIQUE (id, tenant_id, output_id, output_kind, output_version),
  ADD CONSTRAINT research_job_output_artifact_identifier_length
  CHECK (char_length(output_id) <= 64);

ALTER TABLE ml_artifacts
  ADD CONSTRAINT ml_artifact_complete_identity
  UNIQUE (id, tenant_id, kind, version, sha256);

ALTER TABLE managed_artifact_objects
  ADD CONSTRAINT managed_artifact_object_complete_identity
  UNIQUE (id, tenant_id, artifact_id, expected_sha256);

CREATE TABLE research_job_terminal_receipts (
  receipt_id TEXT PRIMARY KEY CHECK (
    receipt_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  terminal_status TEXT NOT NULL CHECK (
    terminal_status IN ('succeeded', 'failed', 'cancelled')
  ),
  terminal_payload_sha256 TEXT NOT NULL CHECK (
    terminal_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  output_artifact_id TEXT,
  output_binding_id TEXT,
  requested_output_kind TEXT CHECK (requested_output_kind IN (
    'managed-dataset-export', 'feature-cache', 'checkpoint',
    'calibration', 'evaluation-report'
  )),
  output_artifact_kind TEXT CHECK (output_artifact_kind IN (
    'dataset', 'feature-cache', 'checkpoint', 'calibration', 'evaluation-report'
  )),
  output_version TEXT CHECK (
    output_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
  ),
  output_sha256 TEXT CHECK (output_sha256 ~ '^[a-f0-9]{64}$'),
  failure_code TEXT CHECK (
    failure_code IN ('runner-failed', 'output-validation-failed', 'cancellation-observed')
  ),
  failure_detail_sha256 TEXT CHECK (
    failure_detail_sha256 ~ '^[a-f0-9]{64}$'
  ),
  completed_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id),
  UNIQUE (claim_id),
  UNIQUE (receipt_id, job_id, tenant_id, terminal_status),
  FOREIGN KEY (job_id, tenant_id) REFERENCES research_job_requests(id, tenant_id),
  FOREIGN KEY (claim_id, job_id, tenant_id, envelope_sha256)
    REFERENCES research_job_execution_claims(
      claim_id, job_id, tenant_id, envelope_sha256
    ),
  FOREIGN KEY (tenant_id, completed_by_actor_id)
    REFERENCES tenant_memberships(tenant_id, actor_id),
  FOREIGN KEY (output_artifact_id, tenant_id)
    REFERENCES ml_artifacts(id, tenant_id),
  FOREIGN KEY (
    job_id, tenant_id, output_artifact_id, requested_output_kind, output_version
  ) REFERENCES research_job_requests(
    id, tenant_id, output_id, output_kind, output_version
  ),
  FOREIGN KEY (
    output_artifact_id, tenant_id, output_artifact_kind, output_version,
    output_sha256
  ) REFERENCES ml_artifacts(id, tenant_id, kind, version, sha256),
  FOREIGN KEY (
    output_binding_id, tenant_id, output_artifact_id, output_sha256
  ) REFERENCES managed_artifact_objects(
    id, tenant_id, artifact_id, expected_sha256
  ),
  CHECK (
    (terminal_status = 'succeeded'
      AND output_artifact_id IS NOT NULL
      AND output_binding_id IS NOT NULL
      AND requested_output_kind IS NOT NULL
      AND output_artifact_kind IS NOT NULL
      AND output_version IS NOT NULL
      AND output_sha256 IS NOT NULL
      AND failure_code IS NULL
      AND failure_detail_sha256 IS NULL)
    OR
    (terminal_status IN ('failed', 'cancelled')
      AND output_artifact_id IS NULL
      AND output_binding_id IS NULL
      AND requested_output_kind IS NULL
      AND output_artifact_kind IS NULL
      AND output_version IS NULL
      AND output_sha256 IS NULL
      AND failure_code IS NOT NULL
      AND failure_detail_sha256 IS NOT NULL)
  ),
  CHECK (
    (terminal_status = 'succeeded' AND failure_code IS NULL)
    OR (terminal_status = 'failed'
      AND failure_code IN ('runner-failed', 'output-validation-failed'))
    OR (terminal_status = 'cancelled' AND failure_code = 'cancellation-observed')
  ),
  CHECK (
    terminal_status <> 'succeeded'
    OR (requested_output_kind = 'managed-dataset-export'
      AND output_artifact_kind = 'dataset')
    OR requested_output_kind = output_artifact_kind
  )
);

ALTER TABLE research_job_execution_gates
  ADD CONSTRAINT research_job_execution_gate_claimed_terminal CHECK (
    terminal_status IS NULL OR claimed
  ),
  ADD CONSTRAINT research_job_execution_gate_terminal_receipt_fk
  FOREIGN KEY (terminal_receipt_id, job_id, tenant_id, terminal_status)
  REFERENCES research_job_terminal_receipts(
    receipt_id, job_id, tenant_id, terminal_status
  );

CREATE TRIGGER research_job_terminal_receipts_append_only
BEFORE UPDATE OR DELETE ON research_job_terminal_receipts
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_terminal_receipts_prevent_truncate
BEFORE TRUNCATE ON research_job_terminal_receipts
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

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
      (NEW.terminal_status = 'cancelled' AND gate.cancellation_requested)
      OR (NEW.terminal_status IN ('succeeded', 'failed')
        AND NOT gate.cancellation_requested)
    );
  IF NOT FOUND THEN
    RAISE EXCEPTION 'research job terminal transition is illegal';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_terminal_receipts_advance_gate
AFTER INSERT ON research_job_terminal_receipts
FOR EACH ROW EXECUTE FUNCTION cadence_advance_research_job_terminal_gate();

CREATE OR REPLACE FUNCTION cadence_preserve_research_job_execution_gate()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.job_id IS DISTINCT FROM OLD.job_id
    OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR (OLD.claimed AND NOT NEW.claimed)
    OR (OLD.cancellation_requested AND NOT NEW.cancellation_requested)
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
  WITH gated AS (
    UPDATE research_job_execution_gates AS gate
    SET cancellation_requested = TRUE, updated_at = CURRENT_TIMESTAMP
    WHERE gate.tenant_id = NEW.tenant_id
      AND gate.terminal_status IS NULL
      AND EXISTS (
        SELECT 1 FROM research_job_inputs AS input
        WHERE input.job_id = gate.job_id AND input.tenant_id = gate.tenant_id
          AND input.artifact_id = NEW.artifact_id
      )
    RETURNING gate.job_id, gate.tenant_id
  )
  INSERT INTO research_job_cancellations (
    job_id, tenant_id, source, reason, requested_by_actor_id
  )
  SELECT gated.job_id, gated.tenant_id,
    'input-quarantined', 'input-quarantined', NULL
  FROM gated
  ON CONFLICT (job_id, tenant_id, source) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cadence_cancel_research_jobs_for_provider_drift()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.outcome <> 'consistent' THEN
    WITH gated AS (
      UPDATE research_job_execution_gates AS gate
      SET cancellation_requested = TRUE, updated_at = CURRENT_TIMESTAMP
      WHERE gate.tenant_id = NEW.tenant_id
        AND gate.terminal_status IS NULL
        AND EXISTS (
          SELECT 1 FROM research_job_inputs AS input
          WHERE input.job_id = gate.job_id AND input.tenant_id = gate.tenant_id
            AND input.binding_id = NEW.binding_id
            AND input.artifact_id = NEW.artifact_id
        )
      RETURNING gate.job_id, gate.tenant_id
    )
    INSERT INTO research_job_cancellations (
      job_id, tenant_id, source, reason, requested_by_actor_id
    )
    SELECT gated.job_id, gated.tenant_id,
      'provider-drift', 'provider-drift', NULL
    FROM gated
    ON CONFLICT (job_id, tenant_id, source) DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
