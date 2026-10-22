ALTER TABLE research_workload_identities
  DROP CONSTRAINT research_workload_identities_purpose_check,
  ADD CONSTRAINT research_workload_identities_purpose_check CHECK (
    purpose IN (
      'research-job-runner', 'research-job-scheduler',
      'research-job-provider', 'research-job-alert-delivery'
    )
  );

ALTER TABLE research_job_liveness_snapshots
  ADD CONSTRAINT research_job_liveness_snapshot_alert_identity
  UNIQUE (
    snapshot_id, job_id, tenant_id, claim_id,
    status, cancellation_revision, generated_at
  );

CREATE TABLE research_job_alert_delivery_attestations (
  delivery_id TEXT PRIMARY KEY CHECK (
    delivery_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$'
  ),
  snapshot_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  snapshot_status TEXT NOT NULL CHECK (
    snapshot_status IN ('overdue', 'cancellation-pending', 'cancellation-observed')
  ),
  cancellation_revision BIGINT NOT NULL CHECK (cancellation_revision >= 0),
  snapshot_generated_at TIMESTAMPTZ NOT NULL,
  snapshot_payload_sha256 TEXT NOT NULL CHECK (
    snapshot_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  channel_reference_sha256 TEXT NOT NULL CHECK (
    channel_reference_sha256 ~ '^[a-f0-9]{64}$'
  ),
  delivery_receipt_sha256 TEXT NOT NULL CHECK (
    delivery_receipt_sha256 ~ '^[a-f0-9]{64}$'
  ),
  outcome TEXT NOT NULL CHECK (outcome = 'delivered'),
  attested_by_workload_id TEXT NOT NULL,
  signing_key_id TEXT NOT NULL,
  signature_algorithm TEXT NOT NULL CHECK (signature_algorithm = 'Ed25519'),
  public_key_sha256 TEXT NOT NULL CHECK (public_key_sha256 ~ '^[a-f0-9]{64}$'),
  attestation_issued_at TIMESTAMPTZ NOT NULL,
  attestation_payload_sha256 TEXT NOT NULL CHECK (
    attestation_payload_sha256 ~ '^[a-f0-9]{64}$'
  ),
  signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (snapshot_id, tenant_id),
  FOREIGN KEY (
    snapshot_id, job_id, tenant_id, claim_id,
    snapshot_status, cancellation_revision, snapshot_generated_at
  ) REFERENCES research_job_liveness_snapshots(
    snapshot_id, job_id, tenant_id, claim_id,
    status, cancellation_revision, generated_at
  ),
  FOREIGN KEY (
    tenant_id, attested_by_workload_id, signing_key_id, public_key_sha256
  ) REFERENCES research_workload_signing_keys(
    tenant_id, workload_id, signing_key_id, public_key_sha256
  ),
  CHECK (attestation_issued_at >= snapshot_generated_at)
);

CREATE OR REPLACE FUNCTION cadence_validate_research_job_alert_delivery()
RETURNS TRIGGER AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM research_job_liveness_snapshots AS snapshot
    WHERE snapshot.snapshot_id = NEW.snapshot_id
      AND snapshot.job_id = NEW.job_id AND snapshot.tenant_id = NEW.tenant_id
      AND snapshot.claim_id = NEW.claim_id
      AND snapshot.status = NEW.snapshot_status
      AND snapshot.cancellation_revision = NEW.cancellation_revision
      AND snapshot.generated_at = NEW.snapshot_generated_at
      AND snapshot.alert_required
  ) OR NOT EXISTS (
    SELECT 1 FROM research_workload_identities AS delivery
    WHERE delivery.tenant_id = NEW.tenant_id
      AND delivery.workload_id = NEW.attested_by_workload_id
      AND delivery.purpose = 'research-job-alert-delivery'
  ) THEN
    RAISE EXCEPTION 'alert delivery must bind an alert-required liveness snapshot';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_job_alert_delivery_validate
BEFORE INSERT ON research_job_alert_delivery_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_validate_research_job_alert_delivery();
CREATE TRIGGER research_job_alert_delivery_append_only
BEFORE UPDATE OR DELETE ON research_job_alert_delivery_attestations
FOR EACH ROW EXECUTE FUNCTION cadence_prevent_mutation();
CREATE TRIGGER research_job_alert_delivery_prevent_truncate
BEFORE TRUNCATE ON research_job_alert_delivery_attestations
FOR EACH STATEMENT EXECUTE FUNCTION cadence_prevent_mutation();
