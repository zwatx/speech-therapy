ALTER TABLE learner_device_sessions
  ADD COLUMN IF NOT EXISTS active_slot SMALLINT;

DO $$
BEGIN
  IF EXISTS (
    WITH latest_consent AS (
      SELECT DISTINCT ON (tenant_id, learner_id)
        id, tenant_id, learner_id, audio_processing, assent_status
      FROM consent_snapshots
      ORDER BY tenant_id, learner_id, version DESC
    )
    SELECT 1
    FROM learner_device_sessions AS session
    INNER JOIN latest_consent AS consent
      ON consent.tenant_id = session.tenant_id
     AND consent.learner_id = session.learner_id
     AND consent.id = session.consent_snapshot_id
    WHERE session.revoked_at IS NULL
      AND session.expires_at > CURRENT_TIMESTAMP
      AND consent.audio_processing = TRUE
      AND consent.assent_status IN ('affirmed', 'not-applicable')
    GROUP BY session.tenant_id, session.learner_id
    HAVING COUNT(*) > 5
  ) THEN
    RAISE EXCEPTION 'device-session active-slot migration requires at most five current grants per learner';
  END IF;
END
$$;

WITH latest_consent AS (
  SELECT DISTINCT ON (tenant_id, learner_id)
    id, tenant_id, learner_id, audio_processing, assent_status
  FROM consent_snapshots
  ORDER BY tenant_id, learner_id, version DESC
), ranked AS (
  SELECT
    session.id,
    ROW_NUMBER() OVER (
      PARTITION BY session.tenant_id, session.learner_id
      ORDER BY session.created_at, session.id
    )::SMALLINT AS active_slot
  FROM learner_device_sessions AS session
  INNER JOIN latest_consent AS consent
    ON consent.tenant_id = session.tenant_id
   AND consent.learner_id = session.learner_id
   AND consent.id = session.consent_snapshot_id
  WHERE session.revoked_at IS NULL
    AND session.expires_at > CURRENT_TIMESTAMP
    AND consent.audio_processing = TRUE
    AND consent.assent_status IN ('affirmed', 'not-applicable')
    AND to_regclass('learner_device_sessions_active_slot_idx') IS NULL
)
UPDATE learner_device_sessions AS session
SET active_slot = ranked.active_slot
FROM ranked
WHERE session.id = ranked.id;

ALTER TABLE learner_device_sessions
  DROP CONSTRAINT IF EXISTS learner_device_sessions_active_slot_range;

ALTER TABLE learner_device_sessions
  ADD CONSTRAINT learner_device_sessions_active_slot_range
  CHECK (active_slot IS NULL OR active_slot BETWEEN 1 AND 5);

CREATE UNIQUE INDEX IF NOT EXISTS learner_device_sessions_active_slot_idx
  ON learner_device_sessions (tenant_id, learner_id, active_slot)
  WHERE active_slot IS NOT NULL;
