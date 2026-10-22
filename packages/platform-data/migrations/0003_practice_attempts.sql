CREATE TABLE IF NOT EXISTS practice_attempts (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  device_session_id TEXT NOT NULL,
  consent_snapshot_id TEXT NOT NULL,
  exercise_id TEXT NOT NULL CHECK (exercise_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{3,79}$'),
  protocol_id TEXT NOT NULL CHECK (protocol_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  status TEXT NOT NULL CHECK (status IN ('accepted-silent', 'retry-capture')),
  duration_milliseconds INTEGER NOT NULL CHECK (
    duration_milliseconds BETWEEN 1 AND 6250
  ),
  sample_rate_hertz INTEGER NOT NULL CHECK (sample_rate_hertz = 16000),
  rms_dbfs DOUBLE PRECISION NOT NULL CHECK (rms_dbfs BETWEEN -160 AND 0),
  peak_amplitude DOUBLE PRECISION NOT NULL CHECK (peak_amplitude BETWEEN 0 AND 1),
  reason_codes JSONB NOT NULL DEFAULT '[]'::JSONB CHECK (
    jsonb_typeof(reason_codes) = 'array'
  ),
  media_retained BOOLEAN NOT NULL DEFAULT FALSE CHECK (media_retained = FALSE),
  received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (learner_id, tenant_id) REFERENCES learners(id, tenant_id),
  FOREIGN KEY (device_session_id, tenant_id, learner_id)
    REFERENCES learner_device_sessions(id, tenant_id, learner_id)
    ON DELETE CASCADE,
  FOREIGN KEY (consent_snapshot_id, tenant_id, learner_id)
    REFERENCES consent_snapshots(id, tenant_id, learner_id),
  UNIQUE (id, tenant_id, learner_id, consent_snapshot_id)
);

CREATE INDEX IF NOT EXISTS practice_attempts_learner_time_idx
  ON practice_attempts (tenant_id, learner_id, received_at DESC);

DROP TRIGGER IF EXISTS practice_attempts_prevent_update ON practice_attempts;
CREATE TRIGGER practice_attempts_prevent_update
BEFORE UPDATE ON practice_attempts
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
