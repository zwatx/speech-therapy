ALTER TABLE learner_device_sessions
  ADD CONSTRAINT learner_device_sessions_id_tenant_unique
  UNIQUE (id, tenant_id);

CREATE TABLE learner_device_request_rate_buckets (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  session_id TEXT NOT NULL,
  operation TEXT NOT NULL CHECK (
    operation IN ('assignment-read', 'attempt-upload')
  ),
  window_started_at TIMESTAMPTZ NOT NULL,
  request_limit INTEGER NOT NULL CHECK (request_limit BETWEEN 1 AND 1000),
  accepted_count INTEGER NOT NULL CHECK (
    accepted_count BETWEEN 0 AND request_limit
  ),
  rejected_count INTEGER NOT NULL CHECK (rejected_count >= 0),
  last_request_id TEXT NOT NULL CHECK (
    last_request_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'
  ),
  last_request_allowed BOOLEAN NOT NULL,
  last_requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, session_id, operation, window_started_at),
  FOREIGN KEY (session_id, tenant_id)
    REFERENCES learner_device_sessions(id, tenant_id)
    ON DELETE CASCADE
);

CREATE INDEX learner_device_request_rate_buckets_recent_idx
  ON learner_device_request_rate_buckets (
    tenant_id, operation, window_started_at DESC
  );
