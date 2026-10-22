CREATE TABLE IF NOT EXISTS practice_attempt_analyses (
  attempt_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  learner_id TEXT NOT NULL,
  consent_snapshot_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('scored-ambiguous', 'unavailable')),
  release_posture TEXT NOT NULL CHECK (release_posture = 'benchmark-only'),
  learner_feedback_eligible BOOLEAN NOT NULL DEFAULT FALSE CHECK (
    learner_feedback_eligible = FALSE
  ),
  checkpoint_id TEXT NOT NULL CHECK (char_length(checkpoint_id) BETWEEN 1 AND 200),
  checkpoint_revision TEXT NOT NULL CHECK (checkpoint_revision ~ '^[a-f0-9]{40}$'),
  runtime TEXT NOT NULL CHECK (char_length(runtime) BETWEEN 1 AND 120),
  model_file_sha256 TEXT NOT NULL CHECK (model_file_sha256 ~ '^[a-f0-9]{64}$'),
  vocabulary_file_sha256 TEXT NOT NULL CHECK (
    vocabulary_file_sha256 ~ '^[a-f0-9]{64}$'
  ),
  lexicon_version TEXT NOT NULL CHECK (
    lexicon_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
  ),
  calibration_version TEXT NOT NULL CHECK (
    calibration_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
  ),
  scoring_policy_version TEXT NOT NULL CHECK (
    scoring_policy_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'
  ),
  p_correct DOUBLE PRECISION CHECK (p_correct BETWEEN 0 AND 1),
  p_error DOUBLE PRECISION CHECK (p_error BETWEEN 0 AND 1),
  hypothesis_coverage DOUBLE PRECISION CHECK (hypothesis_coverage BETWEEN 0 AND 1),
  calibrated BOOLEAN,
  ambiguous BOOLEAN,
  failure_code TEXT CHECK (failure_code IN ('benchmark-unavailable')),
  inference_milliseconds INTEGER NOT NULL CHECK (
    inference_milliseconds BETWEEN 0 AND 300000
  ),
  received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (status = 'scored-ambiguous'
      AND p_correct IS NOT NULL
      AND p_error IS NOT NULL
      AND p_correct + p_error <= 1.000001
      AND hypothesis_coverage IS NOT NULL
      AND calibrated = FALSE
      AND ambiguous = TRUE
      AND failure_code IS NULL)
    OR
    (status = 'unavailable'
      AND p_correct IS NULL
      AND p_error IS NULL
      AND hypothesis_coverage IS NULL
      AND calibrated IS NULL
      AND ambiguous IS NULL
      AND failure_code = 'benchmark-unavailable')
  ),
  FOREIGN KEY (attempt_id, tenant_id, learner_id, consent_snapshot_id)
    REFERENCES practice_attempts(id, tenant_id, learner_id, consent_snapshot_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS practice_attempt_analyses_learner_time_idx
  ON practice_attempt_analyses (tenant_id, learner_id, received_at DESC);

DROP TRIGGER IF EXISTS practice_attempt_analyses_prevent_update
  ON practice_attempt_analyses;
CREATE TRIGGER practice_attempt_analyses_prevent_update
BEFORE UPDATE ON practice_attempt_analyses
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
