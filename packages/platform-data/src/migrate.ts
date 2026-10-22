import { readFile } from "node:fs/promises";

import type { MigrationDatabaseClient } from "./database.ts";

const migrationUrls = [
  new URL("../migrations/0001_identity_consent_audit.sql", import.meta.url),
  new URL("../migrations/0002_learner_device_sessions.sql", import.meta.url),
  new URL("../migrations/0003_practice_attempts.sql", import.meta.url),
  new URL("../migrations/0004_practice_attempt_analyses.sql", import.meta.url),
  new URL("../migrations/0005_artifact_registry.sql", import.meta.url),
  new URL("../migrations/0006_artifact_quarantine_actions.sql", import.meta.url),
  new URL("../migrations/0007_signed_quarantine_receipts.sql", import.meta.url),
  new URL("../migrations/0008_receipt_signing_key_lifecycle.sql", import.meta.url),
  new URL("../migrations/0009_managed_artifact_objects.sql", import.meta.url),
  new URL("../migrations/0010_research_job_authorizations.sql", import.meta.url),
  new URL("../migrations/0011_research_job_execution_control.sql", import.meta.url),
  new URL("../migrations/0012_research_job_terminal_receipts.sql", import.meta.url),
  new URL("../migrations/0013_research_workload_identities.sql", import.meta.url),
  new URL("../migrations/0014_signed_research_job_terminals.sql", import.meta.url),
  new URL("../migrations/0015_research_job_cancellation_acknowledgements.sql", import.meta.url),
  new URL("../migrations/0016_research_job_heartbeats.sql", import.meta.url),
  new URL("../migrations/0017_research_job_liveness_monitoring.sql", import.meta.url),
  new URL("../migrations/0018_signed_research_job_dispatches.sql", import.meta.url),
  new URL("../migrations/0019_signed_research_job_launches.sql", import.meta.url),
  new URL("../migrations/0020_external_research_job_termination.sql", import.meta.url),
  new URL("../migrations/0021_authenticated_research_job_alerts.sql", import.meta.url),
  new URL("../migrations/0022_practice_assignments.sql", import.meta.url),
  new URL("../migrations/0023_device_session_active_slots.sql", import.meta.url),
  new URL("../migrations/0024_device_access_rate_buckets.sql", import.meta.url),
  new URL("../migrations/0025_learner_device_request_rate_buckets.sql", import.meta.url),
] as const;

export async function applyFoundationMigration(
  database: MigrationDatabaseClient,
): Promise<void> {
  for (const migrationUrl of migrationUrls) {
    const sql = await readFile(migrationUrl, "utf8");
    await database.executeScript(sql);
  }
}
