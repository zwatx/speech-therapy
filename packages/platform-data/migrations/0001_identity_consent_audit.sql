CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 120),
  external_organization_hash TEXT NOT NULL UNIQUE
    CHECK (external_organization_hash ~ '^[a-f0-9]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS actors (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  external_subject_hash TEXT NOT NULL UNIQUE
    CHECK (external_subject_hash ~ '^[a-f0-9]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  actor_id TEXT NOT NULL REFERENCES actors(id),
  role TEXT NOT NULL CHECK (role IN ('owner', 'clinician', 'reviewer', 'support')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'revoked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, actor_id)
);

CREATE TABLE IF NOT EXISTS learners (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  display_label TEXT NOT NULL CHECK (char_length(display_label) BETWEEN 1 AND 120),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at TIMESTAMPTZ,
  UNIQUE (id, tenant_id)
);

CREATE TABLE IF NOT EXISTS consent_snapshots (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  notice_version TEXT NOT NULL CHECK (char_length(notice_version) BETWEEN 1 AND 80),
  audio_processing BOOLEAN NOT NULL,
  video_processing BOOLEAN NOT NULL,
  clinician_review BOOLEAN NOT NULL,
  research_use BOOLEAN NOT NULL,
  assent_status TEXT NOT NULL CHECK (
    assent_status IN ('not-applicable', 'affirmed', 'declined', 'withdrawn')
  ),
  captured_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  supersedes_snapshot_id TEXT,
  UNIQUE (id, tenant_id, learner_id),
  FOREIGN KEY (learner_id, tenant_id) REFERENCES learners(id, tenant_id),
  FOREIGN KEY (supersedes_snapshot_id, tenant_id, learner_id)
    REFERENCES consent_snapshots(id, tenant_id, learner_id),
  UNIQUE (tenant_id, learner_id, version)
);

CREATE TABLE IF NOT EXISTS data_subject_requests (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('export', 'deletion')),
  status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
  requested_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMPTZ,
  receipt JSONB NOT NULL DEFAULT '{}'::JSONB,
  FOREIGN KEY (learner_id, tenant_id) REFERENCES learners(id, tenant_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  actor_id TEXT NOT NULL REFERENCES actors(id),
  action TEXT NOT NULL CHECK (char_length(action) BETWEEN 1 AND 100),
  resource_type TEXT NOT NULL CHECK (char_length(resource_type) BETWEEN 1 AND 60),
  resource_id TEXT NOT NULL CHECK (char_length(resource_id) BETWEEN 1 AND 80),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS consent_snapshots_learner_idx
  ON consent_snapshots (tenant_id, learner_id, version DESC);
CREATE INDEX IF NOT EXISTS tenant_memberships_actor_idx
  ON tenant_memberships (actor_id);
CREATE INDEX IF NOT EXISTS audit_events_tenant_time_idx
  ON audit_events (tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS data_subject_requests_learner_idx
  ON data_subject_requests (tenant_id, learner_id, requested_at DESC);

CREATE OR REPLACE FUNCTION cadence_prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION '% records are append-only', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS consent_snapshots_append_only ON consent_snapshots;
CREATE TRIGGER consent_snapshots_append_only
BEFORE UPDATE OR DELETE ON consent_snapshots
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS data_subject_requests_append_only ON data_subject_requests;
CREATE TRIGGER data_subject_requests_append_only
BEFORE UPDATE OR DELETE ON data_subject_requests
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS consent_snapshots_prevent_truncate ON consent_snapshots;
CREATE TRIGGER consent_snapshots_prevent_truncate
BEFORE TRUNCATE ON consent_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS audit_events_prevent_truncate ON audit_events;
CREATE TRIGGER audit_events_prevent_truncate
BEFORE TRUNCATE ON audit_events
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS data_subject_requests_prevent_truncate ON data_subject_requests;
CREATE TRIGGER data_subject_requests_prevent_truncate
BEFORE TRUNCATE ON data_subject_requests
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
