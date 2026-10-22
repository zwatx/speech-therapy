CREATE TABLE IF NOT EXISTS research_job_requests (
  id TEXT NOT NULL CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'),
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  job_type TEXT NOT NULL CHECK (job_type IN (
    'dataset-export', 'feature-extraction', 'training', 'calibration',
    'evaluation', 'shadow-evaluation'
  )),
  output_kind TEXT NOT NULL CHECK (output_kind IN (
    'managed-dataset-export', 'feature-cache', 'checkpoint',
    'calibration', 'evaluation-report'
  )),
  output_id TEXT NOT NULL CHECK (output_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'),
  output_version TEXT NOT NULL CHECK (
    output_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
  ),
  code_revision TEXT NOT NULL CHECK (code_revision ~ '^[a-f0-9]{40}$'),
  configuration_sha256 TEXT NOT NULL CHECK (configuration_sha256 ~ '^[a-f0-9]{64}$'),
  runner_image_digest TEXT NOT NULL CHECK (runner_image_digest ~ '^sha256:[a-f0-9]{64}$'),
  intended_use TEXT NOT NULL CHECK (char_length(intended_use) BETWEEN 10 AND 500),
  exclusions JSONB NOT NULL CHECK (
    jsonb_typeof(exclusions) = 'array' AND jsonb_array_length(exclusions) BETWEEN 1 AND 20
  ),
  release_posture TEXT NOT NULL CHECK (release_posture = 'research-only'),
  learner_feedback_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (
    learner_feedback_eligible = FALSE
  ),
  requested_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (id, tenant_id),
  UNIQUE (output_id),
  FOREIGN KEY (tenant_id, requested_by_actor_id)
    REFERENCES tenant_memberships (tenant_id, actor_id),
  CHECK (expires_at > requested_at)
);

CREATE TABLE IF NOT EXISTS research_job_inputs (
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  binding_id TEXT NOT NULL,
  artifact_kind TEXT NOT NULL CHECK (artifact_kind IN (
    'dataset', 'feature-cache', 'checkpoint', 'calibration',
    'evaluation-report', 'deployment'
  )),
  artifact_sha256 TEXT NOT NULL CHECK (artifact_sha256 ~ '^[a-f0-9]{64}$'),
  provider_id TEXT NOT NULL,
  object_reference_sha256 TEXT NOT NULL CHECK (object_reference_sha256 ~ '^[a-f0-9]{64}$'),
  provider_object_version TEXT NOT NULL,
  PRIMARY KEY (job_id, tenant_id, artifact_id, binding_id),
  FOREIGN KEY (job_id, tenant_id) REFERENCES research_job_requests(id, tenant_id),
  FOREIGN KEY (artifact_id, tenant_id) REFERENCES ml_artifacts(id, tenant_id),
  FOREIGN KEY (binding_id, tenant_id, artifact_id)
    REFERENCES managed_artifact_objects (id, tenant_id, artifact_id)
);

CREATE TABLE IF NOT EXISTS research_job_approvals (
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  envelope_sha256 TEXT NOT NULL CHECK (envelope_sha256 ~ '^[a-f0-9]{64}$'),
  approved_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  approved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (job_id, tenant_id),
  FOREIGN KEY (job_id, tenant_id) REFERENCES research_job_requests(id, tenant_id),
  FOREIGN KEY (tenant_id, approved_by_actor_id)
    REFERENCES tenant_memberships (tenant_id, actor_id)
);

CREATE INDEX IF NOT EXISTS research_job_requests_expiry_idx
  ON research_job_requests (tenant_id, expires_at);

DROP TRIGGER IF EXISTS research_job_requests_append_only ON research_job_requests;
CREATE TRIGGER research_job_requests_append_only
BEFORE UPDATE OR DELETE ON research_job_requests
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
DROP TRIGGER IF EXISTS research_job_requests_prevent_truncate ON research_job_requests;
CREATE TRIGGER research_job_requests_prevent_truncate
BEFORE TRUNCATE ON research_job_requests
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS research_job_inputs_append_only ON research_job_inputs;
CREATE TRIGGER research_job_inputs_append_only
BEFORE UPDATE OR DELETE ON research_job_inputs
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
DROP TRIGGER IF EXISTS research_job_inputs_prevent_truncate ON research_job_inputs;
CREATE TRIGGER research_job_inputs_prevent_truncate
BEFORE TRUNCATE ON research_job_inputs
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS research_job_approvals_append_only ON research_job_approvals;
CREATE TRIGGER research_job_approvals_append_only
BEFORE UPDATE OR DELETE ON research_job_approvals
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
DROP TRIGGER IF EXISTS research_job_approvals_prevent_truncate ON research_job_approvals;
CREATE TRIGGER research_job_approvals_prevent_truncate
BEFORE TRUNCATE ON research_job_approvals
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
