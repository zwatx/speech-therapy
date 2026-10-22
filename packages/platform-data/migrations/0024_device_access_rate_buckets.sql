CREATE TABLE IF NOT EXISTS device_access_rate_buckets (
  tenant_id TEXT NOT NULL REFERENCES tenants(id),
  scope_type TEXT NOT NULL CHECK (scope_type IN ('actor', 'learner')),
  scope_id TEXT NOT NULL CHECK (scope_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  operation TEXT NOT NULL CHECK (operation = 'token-generation'),
  window_started_at TIMESTAMPTZ NOT NULL,
  request_limit INTEGER NOT NULL CHECK (request_limit BETWEEN 1 AND 1000),
  accepted_count INTEGER NOT NULL CHECK (accepted_count BETWEEN 0 AND request_limit),
  rejected_count INTEGER NOT NULL CHECK (rejected_count >= 0),
  last_request_id TEXT NOT NULL CHECK (
    last_request_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'
  ),
  last_request_allowed BOOLEAN NOT NULL,
  last_requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (
    tenant_id, scope_type, scope_id, operation, window_started_at
  )
);

CREATE INDEX IF NOT EXISTS device_access_rate_buckets_recent_idx
  ON device_access_rate_buckets (tenant_id, operation, window_started_at DESC);
