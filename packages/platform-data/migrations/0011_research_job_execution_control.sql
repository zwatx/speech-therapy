CREATE TABLE IF NOT EXISTS research_job_execution_gates (
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claimed BOOLEAN NOT NULL DEFAULT FALSE,
  cancellation_requested BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (job_id, tenant_id),
  FOREIGN KEY (job_id, tenant_id) REFERENCES research_job_requests(id, tenant_id)
);

CREATE TABLE IF NOT EXISTS research_job_cancellations (
  sequence_id BIGSERIAL PRIMARY KEY,
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN (
    'operator', 'input-quarantined', 'provider-drift'
  )),
  reason TEXT NOT NULL CHECK (reason IN (
    'operator-stop', 'incident', 'provider-drift', 'input-quarantined'
  )),
  requested_by_actor_id TEXT REFERENCES actors(id),
  cancelled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id, source),
  FOREIGN KEY (job_id, tenant_id) REFERENCES research_job_requests(id, tenant_id),
  FOREIGN KEY (tenant_id, requested_by_actor_id)
    REFERENCES tenant_memberships (tenant_id, actor_id),
  CHECK (
    (source = 'operator' AND requested_by_actor_id IS NOT NULL
      AND reason IN ('operator-stop', 'incident'))
    OR
    (source = 'input-quarantined' AND requested_by_actor_id IS NULL
      AND reason = 'input-quarantined')
    OR
    (source = 'provider-drift' AND requested_by_actor_id IS NULL
      AND reason = 'provider-drift')
  )
);

CREATE TABLE IF NOT EXISTS research_job_execution_claims (
  claim_id TEXT PRIMARY KEY CHECK (claim_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'),
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  claimed_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_id, tenant_id),
  FOREIGN KEY (job_id, tenant_id) REFERENCES research_job_approvals(job_id, tenant_id),
  FOREIGN KEY (tenant_id, claimed_by_actor_id)
    REFERENCES tenant_memberships (tenant_id, actor_id)
);

CREATE OR REPLACE FUNCTION cadence_preserve_research_job_execution_gate()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.job_id IS DISTINCT FROM OLD.job_id
    OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR (OLD.claimed AND NOT NEW.claimed)
    OR (OLD.cancellation_requested AND NOT NEW.cancellation_requested)
  THEN
    RAISE EXCEPTION 'research job execution gate is monotonic';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS research_job_execution_gates_monotonic
  ON research_job_execution_gates;
CREATE TRIGGER research_job_execution_gates_monotonic
BEFORE UPDATE ON research_job_execution_gates
FOR EACH ROW EXECUTE FUNCTION cadence_preserve_research_job_execution_gate();

DROP TRIGGER IF EXISTS research_job_execution_gates_prevent_delete
  ON research_job_execution_gates;
CREATE TRIGGER research_job_execution_gates_prevent_delete
BEFORE DELETE ON research_job_execution_gates
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS research_job_execution_gates_prevent_truncate
  ON research_job_execution_gates;
CREATE TRIGGER research_job_execution_gates_prevent_truncate
BEFORE TRUNCATE ON research_job_execution_gates
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS research_job_cancellations_append_only
  ON research_job_cancellations;
CREATE TRIGGER research_job_cancellations_append_only
BEFORE UPDATE OR DELETE ON research_job_cancellations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
DROP TRIGGER IF EXISTS research_job_cancellations_prevent_truncate
  ON research_job_cancellations;
CREATE TRIGGER research_job_cancellations_prevent_truncate
BEFORE TRUNCATE ON research_job_cancellations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS research_job_execution_claims_append_only
  ON research_job_execution_claims;
CREATE TRIGGER research_job_execution_claims_append_only
BEFORE UPDATE OR DELETE ON research_job_execution_claims
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
DROP TRIGGER IF EXISTS research_job_execution_claims_prevent_truncate
  ON research_job_execution_claims;
CREATE TRIGGER research_job_execution_claims_prevent_truncate
BEFORE TRUNCATE ON research_job_execution_claims
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

CREATE OR REPLACE FUNCTION cadence_cancel_research_jobs_for_quarantined_artifact()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE research_job_execution_gates AS gate
  SET cancellation_requested = TRUE, updated_at = CURRENT_TIMESTAMP
  WHERE gate.tenant_id = NEW.tenant_id
    AND EXISTS (
      SELECT 1 FROM research_job_inputs AS input
      WHERE input.job_id = gate.job_id AND input.tenant_id = gate.tenant_id
        AND input.artifact_id = NEW.artifact_id
    );
  INSERT INTO research_job_cancellations (
    job_id, tenant_id, source, reason, requested_by_actor_id
  )
  SELECT DISTINCT input.job_id, input.tenant_id,
    'input-quarantined', 'input-quarantined', NULL
  FROM research_job_inputs AS input
  WHERE input.tenant_id = NEW.tenant_id
    AND input.artifact_id = NEW.artifact_id
  ON CONFLICT (job_id, tenant_id, source) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS research_jobs_cancel_on_artifact_quarantine
  ON artifact_quarantine_events;
CREATE TRIGGER research_jobs_cancel_on_artifact_quarantine
AFTER INSERT ON artifact_quarantine_events
FOR EACH ROW EXECUTE FUNCTION cadence_cancel_research_jobs_for_quarantined_artifact();

CREATE OR REPLACE FUNCTION cadence_cancel_research_jobs_for_provider_drift()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.outcome <> 'consistent' THEN
    UPDATE research_job_execution_gates AS gate
    SET cancellation_requested = TRUE, updated_at = CURRENT_TIMESTAMP
    WHERE gate.tenant_id = NEW.tenant_id
      AND EXISTS (
        SELECT 1 FROM research_job_inputs AS input
        WHERE input.job_id = gate.job_id AND input.tenant_id = gate.tenant_id
          AND input.binding_id = NEW.binding_id
          AND input.artifact_id = NEW.artifact_id
      );
    INSERT INTO research_job_cancellations (
      job_id, tenant_id, source, reason, requested_by_actor_id
    )
    SELECT DISTINCT input.job_id, input.tenant_id,
      'provider-drift', 'provider-drift', NULL
    FROM research_job_inputs AS input
    WHERE input.tenant_id = NEW.tenant_id
      AND input.binding_id = NEW.binding_id
      AND input.artifact_id = NEW.artifact_id
    ON CONFLICT (job_id, tenant_id, source) DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS research_jobs_cancel_on_provider_drift
  ON managed_artifact_object_observations;
CREATE TRIGGER research_jobs_cancel_on_provider_drift
AFTER INSERT ON managed_artifact_object_observations
FOR EACH ROW EXECUTE FUNCTION cadence_cancel_research_jobs_for_provider_drift();
