ALTER TABLE learners
  ADD COLUMN IF NOT EXISTS current_consent_version INTEGER NOT NULL DEFAULT 0
  CHECK (current_consent_version >= 0);

UPDATE learners AS learner
SET current_consent_version = latest.version
FROM (
  SELECT tenant_id, learner_id, MAX(version) AS version
  FROM consent_snapshots
  GROUP BY tenant_id, learner_id
) AS latest
WHERE learner.tenant_id = latest.tenant_id
  AND learner.id = latest.learner_id
  AND learner.current_consent_version <> latest.version;

CREATE TABLE IF NOT EXISTS ml_artifacts (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  kind TEXT NOT NULL CHECK (kind IN (
    'dataset', 'feature-cache', 'checkpoint', 'calibration',
    'evaluation-report', 'deployment'
  )),
  version TEXT NOT NULL CHECK (version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'),
  sha256 TEXT NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (
    status IN ('active', 'quarantined', 'retired')
  ),
  release_posture TEXT NOT NULL CHECK (release_posture = 'research-only'),
  learner_feedback_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (
    learner_feedback_eligible = FALSE
  ),
  created_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  quarantined_at TIMESTAMPTZ,
  quarantine_reason TEXT CHECK (
    quarantine_reason IN ('consent-superseded', 'learner-deleted', 'ancestor-quarantined')
  ),
  UNIQUE (tenant_id, sha256),
  UNIQUE (id, tenant_id),
  CHECK (
    (status = 'quarantined' AND quarantined_at IS NOT NULL AND quarantine_reason IS NOT NULL)
    OR
    (status <> 'quarantined' AND quarantined_at IS NULL AND quarantine_reason IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS artifact_lineage_edges (
  tenant_id TEXT NOT NULL,
  parent_artifact_id TEXT NOT NULL,
  child_artifact_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, parent_artifact_id, child_artifact_id),
  FOREIGN KEY (parent_artifact_id, tenant_id)
    REFERENCES ml_artifacts(id, tenant_id),
  FOREIGN KEY (child_artifact_id, tenant_id)
    REFERENCES ml_artifacts(id, tenant_id),
  CHECK (parent_artifact_id <> child_artifact_id)
);

CREATE TABLE IF NOT EXISTS artifact_consent_dependencies (
  artifact_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  consent_snapshot_id TEXT NOT NULL,
  processing_purpose TEXT NOT NULL CHECK (
    processing_purpose IN ('audio-research', 'visual-research')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (artifact_id, tenant_id, learner_id, processing_purpose),
  FOREIGN KEY (artifact_id, tenant_id) REFERENCES ml_artifacts(id, tenant_id),
  FOREIGN KEY (consent_snapshot_id, tenant_id, learner_id)
    REFERENCES consent_snapshots(id, tenant_id, learner_id)
);

CREATE TABLE IF NOT EXISTS artifact_quarantine_events (
  sequence_id BIGSERIAL PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (
    reason IN ('consent-superseded', 'learner-deleted', 'ancestor-quarantined')
  ),
  source_learner_id TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (artifact_id, tenant_id) REFERENCES ml_artifacts(id, tenant_id)
);

CREATE INDEX IF NOT EXISTS artifact_lineage_parent_idx
  ON artifact_lineage_edges (tenant_id, parent_artifact_id);
CREATE INDEX IF NOT EXISTS artifact_consent_learner_idx
  ON artifact_consent_dependencies (tenant_id, learner_id);
CREATE INDEX IF NOT EXISTS artifact_status_idx
  ON ml_artifacts (tenant_id, status, kind);

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
  ), changed AS (
    UPDATE ml_artifacts AS artifact
    SET status = 'quarantined',
        quarantined_at = CURRENT_TIMESTAMP,
        quarantine_reason = CASE
          WHEN artifact.id IN (SELECT id FROM direct_artifacts) THEN direct_reason
          ELSE 'ancestor-quarantined'
        END
    FROM impacted
    WHERE artifact.tenant_id = affected_tenant_id
      AND artifact.id = impacted.id
      AND artifact.status = 'active'
    RETURNING artifact.id, artifact.tenant_id, artifact.quarantine_reason
  )
  INSERT INTO artifact_quarantine_events (
    artifact_id, tenant_id, reason, source_learner_id
  )
  SELECT id, tenant_id, quarantine_reason, affected_learner_id
  FROM changed;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cadence_quarantine_on_consent_supersession()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE learners
  SET current_consent_version = NEW.version
  WHERE tenant_id = NEW.tenant_id
    AND id = NEW.learner_id
    AND current_consent_version < NEW.version;
  IF NEW.version > 1 THEN
    PERFORM cadence_quarantine_artifacts_for_learner(
      NEW.tenant_id, NEW.learner_id, 'consent-superseded'
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cadence_prevent_artifact_lineage_cycle()
RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    WITH RECURSIVE descendants(id) AS (
      SELECT NEW.child_artifact_id
      UNION
      SELECT edge.child_artifact_id
      FROM descendants
      INNER JOIN artifact_lineage_edges AS edge
        ON edge.tenant_id = NEW.tenant_id
       AND edge.parent_artifact_id = descendants.id
    )
    SELECT 1 FROM descendants WHERE id = NEW.parent_artifact_id
  ) THEN
    RAISE EXCEPTION 'artifact lineage must be acyclic';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS artifact_lineage_edges_prevent_cycle
  ON artifact_lineage_edges;
CREATE TRIGGER artifact_lineage_edges_prevent_cycle
BEFORE INSERT ON artifact_lineage_edges
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_artifact_lineage_cycle();

DROP TRIGGER IF EXISTS artifact_quarantine_on_consent ON consent_snapshots;
CREATE TRIGGER artifact_quarantine_on_consent
AFTER INSERT ON consent_snapshots
FOR EACH ROW EXECUTE FUNCTION cadence_quarantine_on_consent_supersession();

CREATE OR REPLACE FUNCTION cadence_quarantine_on_learner_deletion()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
    PERFORM cadence_quarantine_artifacts_for_learner(
      NEW.tenant_id, NEW.id, 'learner-deleted'
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS artifact_quarantine_on_deletion ON learners;
CREATE TRIGGER artifact_quarantine_on_deletion
AFTER UPDATE OF deleted_at ON learners
FOR EACH ROW EXECUTE FUNCTION cadence_quarantine_on_learner_deletion();

DROP TRIGGER IF EXISTS artifact_lineage_edges_append_only ON artifact_lineage_edges;
CREATE TRIGGER artifact_lineage_edges_append_only
BEFORE UPDATE OR DELETE ON artifact_lineage_edges
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_consent_dependencies_append_only
  ON artifact_consent_dependencies;
CREATE TRIGGER artifact_consent_dependencies_append_only
BEFORE UPDATE OR DELETE ON artifact_consent_dependencies
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_quarantine_events_append_only
  ON artifact_quarantine_events;
CREATE TRIGGER artifact_quarantine_events_append_only
BEFORE UPDATE OR DELETE ON artifact_quarantine_events
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_lineage_edges_prevent_truncate
  ON artifact_lineage_edges;
CREATE TRIGGER artifact_lineage_edges_prevent_truncate
BEFORE TRUNCATE ON artifact_lineage_edges
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_consent_dependencies_prevent_truncate
  ON artifact_consent_dependencies;
CREATE TRIGGER artifact_consent_dependencies_prevent_truncate
BEFORE TRUNCATE ON artifact_consent_dependencies
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS artifact_quarantine_events_prevent_truncate
  ON artifact_quarantine_events;
CREATE TRIGGER artifact_quarantine_events_prevent_truncate
BEFORE TRUNCATE ON artifact_quarantine_events
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
