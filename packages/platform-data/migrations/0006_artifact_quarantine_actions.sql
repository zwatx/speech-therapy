CREATE UNIQUE INDEX IF NOT EXISTS artifact_quarantine_events_identity_idx
  ON artifact_quarantine_events (
    sequence_id, artifact_id, tenant_id, source_learner_id
  );

CREATE TABLE IF NOT EXISTS artifact_quarantine_actions (
  id TEXT PRIMARY KEY CHECK (char_length(id) BETWEEN 4 AND 160),
  quarantine_event_sequence_id BIGINT NOT NULL,
  tenant_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  source_learner_id TEXT NOT NULL,
  action_type TEXT NOT NULL CHECK (action_type IN (
    'revoke-artifact-access',
    'purge-subject-data',
    'purge-feature-cache',
    'disable-deployment',
    'schedule-retraining',
    'schedule-reevaluation'
  )),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'processing', 'succeeded', 'dead-letter')
  ),
  idempotency_key TEXT NOT NULL UNIQUE CHECK (
    char_length(idempotency_key) BETWEEN 4 AND 180
  ),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 8),
  available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  leased_by TEXT,
  lease_token_sha256 TEXT CHECK (lease_token_sha256 ~ '^[a-f0-9]{64}$'),
  lease_expires_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  receipt_reference TEXT CHECK (char_length(receipt_reference) BETWEEN 1 AND 200),
  receipt_sha256 TEXT CHECK (receipt_sha256 ~ '^[a-f0-9]{64}$'),
  receipt_outcome TEXT CHECK (receipt_outcome IN ('performed', 'already-satisfied')),
  last_error_code TEXT CHECK (last_error_code IN (
    'external-unavailable', 'verification-failed', 'permanent-rejection'
  )),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (artifact_id, tenant_id) REFERENCES ml_artifacts(id, tenant_id),
  FOREIGN KEY (
    quarantine_event_sequence_id, artifact_id, tenant_id, source_learner_id
  ) REFERENCES artifact_quarantine_events (
    sequence_id, artifact_id, tenant_id, source_learner_id
  ),
  UNIQUE (quarantine_event_sequence_id, action_type),
  CHECK (
    (status = 'processing'
      AND leased_by IS NOT NULL
      AND lease_token_sha256 IS NOT NULL
      AND lease_expires_at IS NOT NULL
      AND completed_at IS NULL)
    OR
    (status <> 'processing'
      AND leased_by IS NULL
      AND lease_token_sha256 IS NULL
      AND lease_expires_at IS NULL)
  ),
  CHECK (
    (status = 'succeeded'
      AND completed_at IS NOT NULL
      AND receipt_reference IS NOT NULL
      AND receipt_sha256 IS NOT NULL
      AND receipt_outcome IS NOT NULL
      AND last_error_code IS NULL)
    OR
    (status <> 'succeeded'
      AND completed_at IS NULL
      AND receipt_reference IS NULL
      AND receipt_sha256 IS NULL
      AND receipt_outcome IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS artifact_quarantine_action_events (
  sequence_id BIGSERIAL PRIMARY KEY,
  action_id TEXT NOT NULL REFERENCES artifact_quarantine_actions(id),
  attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 1 AND 8),
  event_type TEXT NOT NULL CHECK (
    event_type IN ('claimed', 'succeeded', 'retry-scheduled', 'dead-lettered')
  ),
  worker_id TEXT NOT NULL CHECK (char_length(worker_id) BETWEEN 4 AND 80),
  error_code TEXT CHECK (error_code IN (
    'external-unavailable', 'verification-failed', 'permanent-rejection'
  )),
  receipt_reference TEXT CHECK (char_length(receipt_reference) BETWEEN 1 AND 200),
  receipt_sha256 TEXT CHECK (receipt_sha256 ~ '^[a-f0-9]{64}$'),
  receipt_outcome TEXT CHECK (receipt_outcome IN ('performed', 'already-satisfied')),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (event_type = 'succeeded'
      AND receipt_reference IS NOT NULL
      AND receipt_sha256 IS NOT NULL
      AND receipt_outcome IS NOT NULL
      AND error_code IS NULL)
    OR
    (event_type IN ('retry-scheduled', 'dead-lettered')
      AND error_code IS NOT NULL
      AND receipt_reference IS NULL
      AND receipt_sha256 IS NULL
      AND receipt_outcome IS NULL)
    OR
    (event_type = 'claimed'
      AND error_code IS NULL
      AND receipt_reference IS NULL
      AND receipt_sha256 IS NULL
      AND receipt_outcome IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS artifact_quarantine_actions_ready_idx
  ON artifact_quarantine_actions (status, available_at, created_at)
  WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS artifact_quarantine_action_events_action_idx
  ON artifact_quarantine_action_events (action_id, sequence_id);

CREATE OR REPLACE FUNCTION cadence_preserve_quarantine_action_identity()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id
    OR NEW.quarantine_event_sequence_id IS DISTINCT FROM OLD.quarantine_event_sequence_id
    OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
    OR NEW.artifact_id IS DISTINCT FROM OLD.artifact_id
    OR NEW.source_learner_id IS DISTINCT FROM OLD.source_learner_id
    OR NEW.action_type IS DISTINCT FROM OLD.action_type
    OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
    OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN
    RAISE EXCEPTION 'artifact quarantine action identity is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS artifact_quarantine_actions_preserve_identity
  ON artifact_quarantine_actions;
CREATE TRIGGER artifact_quarantine_actions_preserve_identity
BEFORE UPDATE ON artifact_quarantine_actions
FOR EACH ROW EXECUTE FUNCTION cadence_preserve_quarantine_action_identity();

DROP TRIGGER IF EXISTS artifact_quarantine_actions_prevent_delete
  ON artifact_quarantine_actions;
CREATE TRIGGER artifact_quarantine_actions_prevent_delete
BEFORE DELETE ON artifact_quarantine_actions
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_quarantine_actions_prevent_truncate
  ON artifact_quarantine_actions;
CREATE TRIGGER artifact_quarantine_actions_prevent_truncate
BEFORE TRUNCATE ON artifact_quarantine_actions
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

CREATE OR REPLACE FUNCTION cadence_quarantine_artifacts_for_learner(
  affected_tenant_id TEXT,
  affected_learner_id TEXT,
  direct_reason TEXT
) RETURNS VOID AS $$
BEGIN
  WITH RECURSIVE direct_artifacts(id) AS (
    SELECT dependency.artifact_id
    FROM artifact_consent_dependencies AS dependency
    INNER JOIN ml_artifacts AS artifact
      ON artifact.id = dependency.artifact_id
     AND artifact.tenant_id = dependency.tenant_id
    WHERE dependency.tenant_id = affected_tenant_id
      AND dependency.learner_id = affected_learner_id
      AND artifact.kind = 'dataset'
  ), impacted(id) AS (
    SELECT id FROM direct_artifacts
    UNION
    SELECT edge.child_artifact_id
    FROM impacted
    INNER JOIN artifact_lineage_edges AS edge
      ON edge.tenant_id = affected_tenant_id
     AND edge.parent_artifact_id = impacted.id
  ), impacted_artifact AS (
    SELECT artifact.id, artifact.tenant_id, artifact.kind,
      CASE
        WHEN artifact.id IN (SELECT id FROM direct_artifacts) THEN direct_reason
        ELSE 'ancestor-quarantined'
      END AS event_reason
    FROM ml_artifacts AS artifact
    INNER JOIN impacted ON impacted.id = artifact.id
    WHERE artifact.tenant_id = affected_tenant_id
  ), changed AS (
    UPDATE ml_artifacts AS artifact
    SET status = 'quarantined',
        quarantined_at = CURRENT_TIMESTAMP,
        quarantine_reason = impacted_artifact.event_reason
    FROM impacted_artifact
    WHERE artifact.tenant_id = impacted_artifact.tenant_id
      AND artifact.id = impacted_artifact.id
      AND artifact.status = 'active'
    RETURNING artifact.id
  ), quarantine_event AS (
    INSERT INTO artifact_quarantine_events (
      artifact_id, tenant_id, reason, source_learner_id
    )
    SELECT id, tenant_id, event_reason, affected_learner_id
    FROM impacted_artifact
    RETURNING sequence_id, artifact_id, tenant_id, source_learner_id
  ), event_artifact AS (
    SELECT quarantine_event.*, artifact.kind
    FROM quarantine_event
    INNER JOIN ml_artifacts AS artifact
      ON artifact.id = quarantine_event.artifact_id
     AND artifact.tenant_id = quarantine_event.tenant_id
  ), required_action AS (
    SELECT event_artifact.*, action_type
    FROM event_artifact
    CROSS JOIN LATERAL unnest(
      CASE event_artifact.kind
        WHEN 'dataset' THEN ARRAY['revoke-artifact-access', 'purge-subject-data']
        WHEN 'feature-cache' THEN ARRAY['revoke-artifact-access', 'purge-feature-cache']
        WHEN 'checkpoint' THEN ARRAY['revoke-artifact-access', 'schedule-retraining']
        WHEN 'calibration' THEN ARRAY['revoke-artifact-access', 'schedule-retraining']
        WHEN 'evaluation-report' THEN ARRAY['revoke-artifact-access', 'schedule-reevaluation']
        WHEN 'deployment' THEN ARRAY['revoke-artifact-access', 'disable-deployment']
      END
    ) AS action_type
  )
  INSERT INTO artifact_quarantine_actions (
    id, quarantine_event_sequence_id, tenant_id, artifact_id,
    source_learner_id, action_type, idempotency_key
  )
  SELECT
    'action-' || sequence_id::TEXT || '-' || action_type,
    sequence_id, tenant_id, artifact_id, source_learner_id, action_type,
    'quarantine-' || sequence_id::TEXT || '-' || action_type
  FROM required_action;
END;
$$ LANGUAGE plpgsql;

WITH event_artifact AS (
  SELECT quarantine.sequence_id, quarantine.artifact_id,
    quarantine.tenant_id, quarantine.source_learner_id, artifact.kind
  FROM artifact_quarantine_events AS quarantine
  INNER JOIN ml_artifacts AS artifact
    ON artifact.id = quarantine.artifact_id
   AND artifact.tenant_id = quarantine.tenant_id
), required_action AS (
  SELECT event_artifact.*, action_type
  FROM event_artifact
  CROSS JOIN LATERAL unnest(
    CASE event_artifact.kind
      WHEN 'dataset' THEN ARRAY['revoke-artifact-access', 'purge-subject-data']
      WHEN 'feature-cache' THEN ARRAY['revoke-artifact-access', 'purge-feature-cache']
      WHEN 'checkpoint' THEN ARRAY['revoke-artifact-access', 'schedule-retraining']
      WHEN 'calibration' THEN ARRAY['revoke-artifact-access', 'schedule-retraining']
      WHEN 'evaluation-report' THEN ARRAY['revoke-artifact-access', 'schedule-reevaluation']
      WHEN 'deployment' THEN ARRAY['revoke-artifact-access', 'disable-deployment']
    END
  ) AS action_type
)
INSERT INTO artifact_quarantine_actions (
  id, quarantine_event_sequence_id, tenant_id, artifact_id,
  source_learner_id, action_type, idempotency_key
)
SELECT
  'action-' || sequence_id::TEXT || '-' || action_type,
  sequence_id, tenant_id, artifact_id, source_learner_id, action_type,
  'quarantine-' || sequence_id::TEXT || '-' || action_type
FROM required_action
ON CONFLICT (quarantine_event_sequence_id, action_type) DO NOTHING;

DROP TRIGGER IF EXISTS artifact_quarantine_action_events_append_only
  ON artifact_quarantine_action_events;
CREATE TRIGGER artifact_quarantine_action_events_append_only
BEFORE UPDATE OR DELETE ON artifact_quarantine_action_events
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_quarantine_action_events_prevent_truncate
  ON artifact_quarantine_action_events;
CREATE TRIGGER artifact_quarantine_action_events_prevent_truncate
BEFORE TRUNCATE ON artifact_quarantine_action_events
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
