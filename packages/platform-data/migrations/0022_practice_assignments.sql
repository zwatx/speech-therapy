CREATE TABLE IF NOT EXISTS practice_assignments (
  id TEXT PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  consent_snapshot_id TEXT NOT NULL,
  exercise_registry_version TEXT NOT NULL
    CHECK (exercise_registry_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'),
  exercise_definition_sha256 TEXT NOT NULL
    CHECK (exercise_definition_sha256 ~ '^[a-f0-9]{64}$'),
  exercise_id TEXT NOT NULL
    CHECK (exercise_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{3,79}$'),
  protocol_id TEXT NOT NULL
    CHECK (protocol_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$'),
  prompt TEXT NOT NULL CHECK (char_length(prompt) BETWEEN 1 AND 80),
  target_label TEXT NOT NULL CHECK (char_length(target_label) BETWEEN 1 AND 120),
  attempt_target INTEGER NOT NULL CHECK (attempt_target BETWEEN 1 AND 20),
  retry_limit INTEGER NOT NULL CHECK (retry_limit BETWEEN 0 AND 2),
  visual_processing BOOLEAN NOT NULL DEFAULT FALSE CHECK (visual_processing = FALSE),
  release_posture TEXT NOT NULL DEFAULT 'candidate-silent-only'
    CHECK (release_posture = 'candidate-silent-only'),
  assigned_by_actor_id TEXT NOT NULL REFERENCES actors(id),
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  supersedes_assignment_id TEXT,
  UNIQUE (id, tenant_id, learner_id),
  UNIQUE (tenant_id, learner_id, version),
  FOREIGN KEY (learner_id, tenant_id) REFERENCES learners(id, tenant_id),
  FOREIGN KEY (consent_snapshot_id, tenant_id, learner_id)
    REFERENCES consent_snapshots(id, tenant_id, learner_id),
  FOREIGN KEY (supersedes_assignment_id, tenant_id, learner_id)
    REFERENCES practice_assignments(id, tenant_id, learner_id)
);

CREATE INDEX IF NOT EXISTS practice_assignments_learner_version_idx
  ON practice_assignments (tenant_id, learner_id, version DESC);

DROP TRIGGER IF EXISTS practice_assignments_append_only ON practice_assignments;
CREATE TRIGGER practice_assignments_append_only
BEFORE UPDATE OR DELETE ON practice_assignments
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();

DROP TRIGGER IF EXISTS practice_assignments_prevent_truncate ON practice_assignments;
CREATE TRIGGER practice_assignments_prevent_truncate
BEFORE TRUNCATE ON practice_assignments
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();

ALTER TABLE practice_attempts
  ADD COLUMN IF NOT EXISTS assignment_id TEXT;
ALTER TABLE practice_attempts
  ADD COLUMN IF NOT EXISTS repetition_index INTEGER;
ALTER TABLE practice_attempts
  ADD COLUMN IF NOT EXISTS retry_index INTEGER;

ALTER TABLE practice_attempts
  DROP CONSTRAINT IF EXISTS practice_attempts_repetition_index_check;
ALTER TABLE practice_attempts
  ADD CONSTRAINT practice_attempts_repetition_index_check
  CHECK (repetition_index IS NULL OR repetition_index BETWEEN 1 AND 20);
ALTER TABLE practice_attempts
  DROP CONSTRAINT IF EXISTS practice_attempts_retry_index_check;
ALTER TABLE practice_attempts
  ADD CONSTRAINT practice_attempts_retry_index_check
  CHECK (retry_index IS NULL OR retry_index BETWEEN 0 AND 2);

ALTER TABLE practice_attempts
  DROP CONSTRAINT IF EXISTS practice_attempts_assignment_fk;
ALTER TABLE practice_attempts
  ADD CONSTRAINT practice_attempts_assignment_fk
  FOREIGN KEY (assignment_id, tenant_id, learner_id)
  REFERENCES practice_assignments(id, tenant_id, learner_id);

CREATE INDEX IF NOT EXISTS practice_attempts_assignment_idx
  ON practice_attempts (tenant_id, assignment_id, received_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS practice_attempts_assignment_slot_idx
  ON practice_attempts (
    tenant_id, assignment_id, repetition_index, retry_index
  )
  WHERE assignment_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS practice_attempts_accepted_repetition_idx
  ON practice_attempts (tenant_id, assignment_id, repetition_index)
  WHERE assignment_id IS NOT NULL AND status = 'accepted-silent';
