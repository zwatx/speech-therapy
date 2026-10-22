ALTER TABLE artifact_quarantine_actions
  ADD COLUMN IF NOT EXISTS receipt_provider_id TEXT,
  ADD COLUMN IF NOT EXISTS receipt_signing_key_id TEXT,
  ADD COLUMN IF NOT EXISTS receipt_public_key_sha256 TEXT,
  ADD COLUMN IF NOT EXISTS receipt_signature_algorithm TEXT,
  ADD COLUMN IF NOT EXISTS receipt_issued_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS receipt_signature_sha256 TEXT;

DO $$
BEGIN
IF NOT EXISTS (
  SELECT 1 FROM pg_constraint
  WHERE conname = 'artifact_quarantine_actions_receipt_verification_check'
) THEN
ALTER TABLE artifact_quarantine_actions
  ADD CONSTRAINT artifact_quarantine_actions_receipt_verification_check CHECK (
    (receipt_provider_id IS NULL
      AND receipt_signing_key_id IS NULL
      AND receipt_public_key_sha256 IS NULL
      AND receipt_signature_algorithm IS NULL
      AND receipt_issued_at IS NULL
      AND receipt_signature_sha256 IS NULL)
    OR
    (status = 'succeeded'
      AND receipt_provider_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
      AND receipt_signing_key_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
      AND receipt_public_key_sha256 ~ '^[a-f0-9]{64}$'
      AND receipt_signature_algorithm = 'Ed25519'
      AND receipt_issued_at IS NOT NULL
      AND receipt_signature_sha256 ~ '^[a-f0-9]{64}$')
  );
END IF;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE artifact_quarantine_action_events
  ADD COLUMN IF NOT EXISTS receipt_provider_id TEXT,
  ADD COLUMN IF NOT EXISTS receipt_signing_key_id TEXT,
  ADD COLUMN IF NOT EXISTS receipt_public_key_sha256 TEXT,
  ADD COLUMN IF NOT EXISTS receipt_signature_algorithm TEXT,
  ADD COLUMN IF NOT EXISTS receipt_issued_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS receipt_signature_sha256 TEXT;

DO $$
BEGIN
IF NOT EXISTS (
  SELECT 1 FROM pg_constraint
  WHERE conname = 'artifact_quarantine_action_events_receipt_verification_check'
) THEN
ALTER TABLE artifact_quarantine_action_events
  ADD CONSTRAINT artifact_quarantine_action_events_receipt_verification_check CHECK (
    (receipt_provider_id IS NULL
      AND receipt_signing_key_id IS NULL
      AND receipt_public_key_sha256 IS NULL
      AND receipt_signature_algorithm IS NULL
      AND receipt_issued_at IS NULL
      AND receipt_signature_sha256 IS NULL)
    OR
    (event_type = 'succeeded'
      AND receipt_provider_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
      AND receipt_signing_key_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$'
      AND receipt_public_key_sha256 ~ '^[a-f0-9]{64}$'
      AND receipt_signature_algorithm = 'Ed25519'
      AND receipt_issued_at IS NOT NULL
      AND receipt_signature_sha256 ~ '^[a-f0-9]{64}$')
  );
END IF;
END;
$$ LANGUAGE plpgsql;
