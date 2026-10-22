CREATE TABLE IF NOT EXISTS managed_artifact_objects (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'),
  tenant_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  provider_id TEXT NOT NULL CHECK (
    provider_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
  ),
  object_reference_sha256 TEXT NOT NULL CHECK (
    object_reference_sha256 ~ '^[a-f0-9]{64}$'
  ),
  provider_object_version TEXT NOT NULL CHECK (
    provider_object_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$'
  ),
  expected_sha256 TEXT NOT NULL CHECK (expected_sha256 ~ '^[a-f0-9]{64}$'),
  registered_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (tenant_id, registered_by_actor_id)
    REFERENCES tenant_memberships (tenant_id, actor_id),
  FOREIGN KEY (artifact_id, tenant_id) REFERENCES ml_artifacts(id, tenant_id),
  UNIQUE (id, tenant_id, artifact_id),
  UNIQUE (tenant_id, artifact_id, provider_id),
  UNIQUE (tenant_id, provider_id, object_reference_sha256)
);

CREATE TABLE IF NOT EXISTS managed_artifact_object_observations (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'),
  binding_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  artifact_id TEXT NOT NULL,
  artifact_status TEXT NOT NULL CHECK (
    artifact_status IN ('active', 'quarantined', 'retired')
  ),
  object_exists BOOLEAN NOT NULL,
  observed_sha256 TEXT CHECK (observed_sha256 ~ '^[a-f0-9]{64}$'),
  access_state TEXT NOT NULL CHECK (
    access_state IN ('available', 'revoked', 'unavailable')
  ),
  outcome TEXT NOT NULL CHECK (
    outcome IN ('consistent', 'missing', 'digest-mismatch', 'access-mismatch')
  ),
  provider_checked_at TIMESTAMPTZ NOT NULL,
  receipt_reference TEXT NOT NULL CHECK (char_length(receipt_reference) BETWEEN 1 AND 200),
  receipt_sha256 TEXT NOT NULL CHECK (receipt_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (tenant_id, recorded_by_actor_id)
    REFERENCES tenant_memberships (tenant_id, actor_id),
  FOREIGN KEY (binding_id, tenant_id, artifact_id)
    REFERENCES managed_artifact_objects (id, tenant_id, artifact_id),
  FOREIGN KEY (artifact_id, tenant_id) REFERENCES ml_artifacts(id, tenant_id),
  CHECK (
    (object_exists AND observed_sha256 IS NOT NULL AND access_state <> 'unavailable')
    OR
    (NOT object_exists AND observed_sha256 IS NULL AND access_state = 'unavailable'
      AND outcome = 'missing')
  )
);

CREATE INDEX IF NOT EXISTS managed_artifact_object_observations_latest_idx
  ON managed_artifact_object_observations (tenant_id, binding_id, recorded_at DESC);

DROP TRIGGER IF EXISTS managed_artifact_objects_append_only ON managed_artifact_objects;
CREATE TRIGGER managed_artifact_objects_append_only
BEFORE UPDATE OR DELETE ON managed_artifact_objects
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS managed_artifact_objects_prevent_truncate ON managed_artifact_objects;
CREATE TRIGGER managed_artifact_objects_prevent_truncate
BEFORE TRUNCATE ON managed_artifact_objects
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS managed_artifact_object_observations_append_only
  ON managed_artifact_object_observations;
CREATE TRIGGER managed_artifact_object_observations_append_only
BEFORE UPDATE OR DELETE ON managed_artifact_object_observations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS managed_artifact_object_observations_prevent_truncate
  ON managed_artifact_object_observations;
CREATE TRIGGER managed_artifact_object_observations_prevent_truncate
BEFORE TRUNCATE ON managed_artifact_object_observations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
