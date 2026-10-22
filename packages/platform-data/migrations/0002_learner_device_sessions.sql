CREATE TABLE IF NOT EXISTS learner_device_sessions (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[a-f0-9]{64}$'),
  consent_snapshot_id TEXT NOT NULL,
  created_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  CHECK (expires_at > created_at),
  UNIQUE (id, tenant_id, learner_id),
  FOREIGN KEY (learner_id, tenant_id) REFERENCES learners(id, tenant_id),
  FOREIGN KEY (consent_snapshot_id, tenant_id, learner_id)
    REFERENCES consent_snapshots(id, tenant_id, learner_id)
);

CREATE INDEX IF NOT EXISTS learner_device_sessions_lookup_idx
  ON learner_device_sessions (token_hash, expires_at)
  WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS learner_device_sessions_learner_idx
  ON learner_device_sessions (tenant_id, learner_id, created_at DESC);
