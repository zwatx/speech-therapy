import { createHash, randomUUID } from "node:crypto";

import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ArtifactQuarantineActionType,
  ArtifactQuarantineAlertEvidence,
  ArtifactQuarantineHealth,
  DeletionDrillReport,
} from "./types.ts";

const opaqueIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$/;
const actionTypes: readonly ArtifactQuarantineActionType[] = [
  "revoke-artifact-access",
  "purge-subject-data",
  "purge-feature-cache",
  "disable-deployment",
  "schedule-retraining",
  "schedule-reevaluation",
];

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function validateActor(actor: ActorContext): void {
  if (!opaqueIdentifier.test(actor.actorId) || !opaqueIdentifier.test(actor.tenantId)) {
    throw new PlatformDataError("invalid-identifier", "Actor and tenant identifiers must be opaque tokens.");
  }
}

function integer(value: number | string): number {
  return Number(value);
}

function actionCountRecord(value: Record<string, number> | string): Record<ArtifactQuarantineActionType, number> {
  const parsed = typeof value === "string" ? JSON.parse(value) as Record<string, number> : value;
  return Object.fromEntries(actionTypes.map((type) => [type, Number(parsed[type] ?? 0)])) as Record<ArtifactQuarantineActionType, number>;
}

export class ArtifactOperationsService {
  readonly #database: DatabaseClient;

  constructor(database: DatabaseClient) {
    this.#database = database;
  }

  async getQuarantineHealth(
    actor: ActorContext,
    overdueAfterSeconds = 300,
  ): Promise<ArtifactQuarantineHealth> {
    validateActor(actor);
    if (!Number.isInteger(overdueAfterSeconds) || overdueAfterSeconds < 60 || overdueAfterSeconds > 86_400) {
      throw new PlatformDataError("invalid-artifact", "The quarantine alert threshold must be 60 to 86400 seconds.");
    }
    const auditId = randomUUID();
    const result = await this.#database.query<Record<string, unknown> & {
      authorized: boolean;
      generated_at: string | Date;
      pending_count: number;
      processing_count: number;
      succeeded_count: number;
      dead_letter_count: number;
      expired_lease_count: number;
      overdue_ready_count: number;
      oldest_ready_seconds: number | string | null;
      action_counts: Record<string, number> | string;
    }>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), tenant_actions AS (
        SELECT * FROM artifact_quarantine_actions
        WHERE tenant_id = $1 AND EXISTS (SELECT 1 FROM authorized)
      ), action_counts AS (
        SELECT COALESCE(jsonb_object_agg(action_type, count), '{}'::jsonb) AS counts
        FROM (
          SELECT action_type, COUNT(*)::INTEGER AS count
          FROM tenant_actions GROUP BY action_type
        ) AS grouped
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $4, $1, $2, 'artifact.quarantine-health.read',
          'artifact_quarantine_queue', $1,
          jsonb_build_object('overdue_after_seconds', $3::INTEGER)
        FROM authorized RETURNING id
      )
      SELECT EXISTS (SELECT 1 FROM authorized) AS authorized,
        CURRENT_TIMESTAMP AS generated_at,
        COUNT(*) FILTER (WHERE status = 'pending')::INTEGER AS pending_count,
        COUNT(*) FILTER (WHERE status = 'processing')::INTEGER AS processing_count,
        COUNT(*) FILTER (WHERE status = 'succeeded')::INTEGER AS succeeded_count,
        COUNT(*) FILTER (WHERE status = 'dead-letter')::INTEGER AS dead_letter_count,
        COUNT(*) FILTER (
          WHERE status = 'processing' AND lease_expires_at <= CURRENT_TIMESTAMP
        )::INTEGER AS expired_lease_count,
        COUNT(*) FILTER (
          WHERE status = 'pending'
            AND available_at <= CURRENT_TIMESTAMP - ($3::INTEGER * INTERVAL '1 second')
        )::INTEGER AS overdue_ready_count,
        EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MIN(created_at) FILTER (
          WHERE status IN ('pending', 'processing')
        )) AS oldest_ready_seconds,
        action_counts.counts AS action_counts,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM action_counts
      LEFT JOIN tenant_actions ON TRUE
      GROUP BY action_counts.counts
      `,
      [actor.tenantId, actor.actorId, overdueAfterSeconds, auditId],
    );
    const row = result.rows[0];
    if (!row?.authorized) {
      throw new PlatformDataError("access-denied", "Only an active owner or reviewer can inspect quarantine health.");
    }
    const deadLetterCount = integer(row.dead_letter_count);
    const expiredLeaseCount = integer(row.expired_lease_count);
    const overdueReadyCount = integer(row.overdue_ready_count);
    return {
      generatedAt: timestamp(row.generated_at),
      status: deadLetterCount > 0 || expiredLeaseCount > 0
        ? "critical"
        : overdueReadyCount > 0 ? "attention" : "healthy",
      overdueAfterSeconds,
      pendingCount: integer(row.pending_count),
      processingCount: integer(row.processing_count),
      succeededCount: integer(row.succeeded_count),
      deadLetterCount,
      expiredLeaseCount,
      overdueReadyCount,
      oldestReadySeconds: row.oldest_ready_seconds === null ? null : Number(row.oldest_ready_seconds),
      countsByActionType: actionCountRecord(row.action_counts),
    };
  }

  async buildQuarantineAlertEvidence(
    actor: ActorContext,
    overdueAfterSeconds = 300,
  ): Promise<ArtifactQuarantineAlertEvidence> {
    const health = await this.getQuarantineHealth(actor, overdueAfterSeconds);
    const reasons: ArtifactQuarantineAlertEvidence["reasons"] = [
      ...(health.deadLetterCount > 0 ? ["dead-letter" as const] : []),
      ...(health.expiredLeaseCount > 0 ? ["expired-lease" as const] : []),
      ...(health.overdueReadyCount > 0 ? ["overdue-ready" as const] : []),
    ];
    const fingerprintSha256 = createHash("sha256").update(JSON.stringify({
      tenantId: actor.tenantId,
      generatedAt: health.generatedAt,
      overdueAfterSeconds,
      deadLetters: health.deadLetterCount,
      expiredLeases: health.expiredLeaseCount,
      overdueReady: health.overdueReadyCount,
      reasons,
    })).digest("hex");
    const auditId = randomUUID();
    const audit = await this.#database.query<Record<string, unknown> & { id: string }>(
      `
      INSERT INTO audit_events (
        id, tenant_id, actor_id, action, resource_type, resource_id, metadata
      )
      SELECT $3, $1, $2, 'artifact.quarantine-alert-evidence.created',
        'artifact_quarantine_queue', $1,
        jsonb_build_object(
          'fingerprint_sha256', $4::TEXT,
          'status', $5::TEXT,
          'alert_required', $6::BOOLEAN,
          'reasons', $7::JSONB,
          'dead_letter_count', $8::INTEGER,
          'expired_lease_count', $9::INTEGER,
          'overdue_ready_count', $10::INTEGER,
          'overdue_after_seconds', $11::INTEGER,
          'delivery_evidence_present', false,
          'production_gate_eligible', false
        )
      WHERE EXISTS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      )
      RETURNING id
      `,
      [actor.tenantId, actor.actorId, auditId, fingerprintSha256,
        health.status, health.status !== "healthy", JSON.stringify(reasons),
        health.deadLetterCount, health.expiredLeaseCount, health.overdueReadyCount,
        overdueAfterSeconds],
    );
    if (!audit.rows[0]) {
      throw new PlatformDataError("access-denied", "The actor cannot create quarantine alert evidence.");
    }
    return {
      schemaVersion: "artifact-quarantine-alert-evidence-v1",
      evidencePosture: "local-foundation",
      productionGateEligible: false,
      generatedAt: health.generatedAt,
      status: health.status,
      alertRequired: health.status !== "healthy",
      reasons,
      fingerprintSha256,
      counts: {
        deadLetters: health.deadLetterCount,
        expiredLeases: health.expiredLeaseCount,
        overdueReady: health.overdueReadyCount,
      },
      deliveryEvidencePresent: false,
      missingProductionEvidence: [
        "authenticated alert-channel delivery receipt",
        "on-call acknowledgement and escalation evidence",
        "managed-environment alert test",
      ],
    };
  }

  async buildDeletionDrillReport(
    actor: ActorContext,
    deletionRequestId: string,
    completionTargetSeconds = 300,
  ): Promise<DeletionDrillReport> {
    validateActor(actor);
    if (!opaqueIdentifier.test(deletionRequestId)) {
      throw new PlatformDataError("invalid-identifier", "Deletion request identifiers must be opaque tokens.");
    }
    if (!Number.isInteger(completionTargetSeconds) || completionTargetSeconds < 1 || completionTargetSeconds > 86_400) {
      throw new PlatformDataError("invalid-artifact", "Deletion drill targets must be 1 to 86400 seconds.");
    }
    const auditId = randomUUID();
    const result = await this.#database.query<Record<string, unknown> & {
      request_id: string;
      requested_at: string | Date;
      completed_at: string | Date;
      learner_deleted: boolean;
      session_count: number;
      attempt_count: number;
      analysis_count: number;
      expected_artifact_count: number;
      quarantined_artifact_count: number;
      quarantine_event_count: number;
      expected_action_count: number;
      succeeded_action_count: number;
      unresolved_action_count: number;
      dead_letter_count: number;
      unexpected_action_count: number;
      receipt_bound_count: number;
      signed_receipt_count: number;
      maximum_completion_seconds: number | string | null;
    }>(
      `
      WITH RECURSIVE authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), target_request AS (
        SELECT request.*, learner.deleted_at
        FROM data_subject_requests AS request
        INNER JOIN learners AS learner
          ON learner.id = request.learner_id AND learner.tenant_id = request.tenant_id
        WHERE request.id = $3 AND request.tenant_id = $1
          AND request.kind = 'deletion' AND request.status = 'completed'
          AND EXISTS (SELECT 1 FROM authorized)
      ), root_artifact(id) AS (
        SELECT DISTINCT dependency.artifact_id
        FROM artifact_consent_dependencies AS dependency
        INNER JOIN target_request
          ON target_request.tenant_id = dependency.tenant_id
         AND target_request.learner_id = dependency.learner_id
      ), expected_artifact(id) AS (
        SELECT id FROM root_artifact
        UNION
        SELECT edge.child_artifact_id
        FROM expected_artifact
        INNER JOIN artifact_lineage_edges AS edge
          ON edge.tenant_id = $1 AND edge.parent_artifact_id = expected_artifact.id
      ), deletion_event AS (
        SELECT DISTINCT ON (event.artifact_id)
          event.sequence_id, event.artifact_id
        FROM artifact_quarantine_events AS event
        INNER JOIN target_request
          ON target_request.tenant_id = event.tenant_id
         AND target_request.learner_id = event.source_learner_id
         AND event.occurred_at >= target_request.requested_at
        INNER JOIN expected_artifact ON expected_artifact.id = event.artifact_id
        INNER JOIN ml_artifacts AS artifact
          ON artifact.id = event.artifact_id AND artifact.tenant_id = event.tenant_id
        WHERE event.reason = CASE artifact.kind
          WHEN 'dataset' THEN 'learner-deleted'
          ELSE 'ancestor-quarantined'
        END
        ORDER BY event.artifact_id, event.sequence_id DESC
      ), expected_action AS (
        SELECT deletion_event.sequence_id, deletion_event.artifact_id, action_type
        FROM deletion_event
        INNER JOIN ml_artifacts AS artifact
          ON artifact.id = deletion_event.artifact_id AND artifact.tenant_id = $1
        CROSS JOIN LATERAL unnest(
          CASE artifact.kind
            WHEN 'dataset' THEN ARRAY['revoke-artifact-access', 'purge-subject-data']
            WHEN 'feature-cache' THEN ARRAY['revoke-artifact-access', 'purge-feature-cache']
            WHEN 'checkpoint' THEN ARRAY['revoke-artifact-access', 'schedule-retraining']
            WHEN 'calibration' THEN ARRAY['revoke-artifact-access', 'schedule-retraining']
            WHEN 'evaluation-report' THEN ARRAY['revoke-artifact-access', 'schedule-reevaluation']
            WHEN 'deployment' THEN ARRAY['revoke-artifact-access', 'disable-deployment']
          END
        ) AS action_type
      ), matched_action AS (
        SELECT expected_action.*, action.status, action.completed_at,
          action.receipt_reference, action.receipt_sha256,
          action.receipt_provider_id, action.receipt_signing_key_id,
          action.receipt_signature_algorithm, action.receipt_signature_sha256
        FROM expected_action
        LEFT JOIN artifact_quarantine_actions AS action
         ON action.quarantine_event_sequence_id = expected_action.sequence_id
         AND action.action_type = expected_action.action_type
      ), unexpected_action AS (
        SELECT action.id
        FROM artifact_quarantine_actions AS action
        INNER JOIN deletion_event
          ON deletion_event.sequence_id = action.quarantine_event_sequence_id
        LEFT JOIN expected_action
          ON expected_action.sequence_id = action.quarantine_event_sequence_id
         AND expected_action.action_type = action.action_type
        WHERE expected_action.sequence_id IS NULL
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $5, $1, $2, 'learner.deletion-drill.read',
          'data_subject_request', id,
          jsonb_build_object('completion_target_seconds', $4::INTEGER)
        FROM target_request RETURNING id
      )
      SELECT request.id AS request_id, request.requested_at, request.completed_at,
        request.deleted_at IS NOT NULL AS learner_deleted,
        (SELECT COUNT(*)::INTEGER FROM learner_device_sessions
         WHERE tenant_id = $1 AND learner_id = request.learner_id) AS session_count,
        (SELECT COUNT(*)::INTEGER FROM practice_attempts
         WHERE tenant_id = $1 AND learner_id = request.learner_id) AS attempt_count,
        (SELECT COUNT(*)::INTEGER FROM practice_attempt_analyses
         WHERE tenant_id = $1 AND learner_id = request.learner_id) AS analysis_count,
        (SELECT COUNT(*)::INTEGER FROM expected_artifact) AS expected_artifact_count,
        (SELECT COUNT(*)::INTEGER FROM ml_artifacts AS artifact
         INNER JOIN expected_artifact ON expected_artifact.id = artifact.id
         WHERE artifact.tenant_id = $1 AND artifact.status = 'quarantined') AS quarantined_artifact_count,
        (SELECT COUNT(*)::INTEGER FROM deletion_event) AS quarantine_event_count,
        (SELECT COUNT(*)::INTEGER FROM expected_action) AS expected_action_count,
        (SELECT COUNT(*)::INTEGER FROM matched_action WHERE status = 'succeeded') AS succeeded_action_count,
        (SELECT COUNT(*)::INTEGER FROM matched_action
         WHERE status IS NULL OR status IN ('pending', 'processing')) AS unresolved_action_count,
        (SELECT COUNT(*)::INTEGER FROM matched_action WHERE status = 'dead-letter') AS dead_letter_count,
        (SELECT COUNT(*)::INTEGER FROM unexpected_action) AS unexpected_action_count,
        (SELECT COUNT(*)::INTEGER FROM matched_action
         WHERE status = 'succeeded' AND receipt_reference IS NOT NULL
           AND receipt_sha256 IS NOT NULL) AS receipt_bound_count,
        (SELECT COUNT(*)::INTEGER FROM matched_action
         WHERE status = 'succeeded'
           AND receipt_provider_id IS NOT NULL
           AND receipt_signing_key_id IS NOT NULL
           AND receipt_signature_algorithm = 'Ed25519'
           AND receipt_signature_sha256 IS NOT NULL) AS signed_receipt_count,
        (SELECT EXTRACT(EPOCH FROM MAX(completed_at) - request.completed_at)
         FROM matched_action WHERE status = 'succeeded') AS maximum_completion_seconds,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM target_request AS request
      `,
      [actor.tenantId, actor.actorId, deletionRequestId, completionTargetSeconds, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The deletion drill request is unavailable to this actor.");
    }
    const expectedArtifactCount = integer(row.expected_artifact_count);
    const expectedActionCount = integer(row.expected_action_count);
    const maximumCompletionSeconds = row.maximum_completion_seconds === null
      ? null : Number(row.maximum_completion_seconds);
    const checks = {
      learnerDeleted: row.learner_deleted,
      transientClinicalDataPurged:
        integer(row.session_count) === 0 && integer(row.attempt_count) === 0 && integer(row.analysis_count) === 0,
      lineageFullyQuarantined:
        integer(row.quarantined_artifact_count) === expectedArtifactCount
        && integer(row.quarantine_event_count) === expectedArtifactCount,
      requiredActionsSucceeded:
        integer(row.succeeded_action_count) === expectedActionCount
        && integer(row.receipt_bound_count) === expectedActionCount
        && integer(row.unresolved_action_count) === 0
        && integer(row.dead_letter_count) === 0
        && integer(row.unexpected_action_count) === 0,
      completionTargetMet:
        expectedActionCount === 0
        || (maximumCompletionSeconds !== null && maximumCompletionSeconds <= completionTargetSeconds),
    } as const;
    return {
      schemaVersion: "deletion-drill-report-v1",
      evidencePosture: "local-foundation",
      productionGateEligible: false,
      requestId: row.request_id,
      requestedAt: timestamp(row.requested_at),
      completedAt: timestamp(row.completed_at),
      completionTargetSeconds,
      maximumCompletionSeconds,
      counts: {
        expectedArtifacts: expectedArtifactCount,
        quarantinedArtifacts: integer(row.quarantined_artifact_count),
        quarantineEvents: integer(row.quarantine_event_count),
        expectedActions: expectedActionCount,
        succeededActions: integer(row.succeeded_action_count),
        unresolvedActions: integer(row.unresolved_action_count),
        deadLetters: integer(row.dead_letter_count),
        unexpectedActions: integer(row.unexpected_action_count),
        signedReceipts: integer(row.signed_receipt_count),
      },
      checks,
      foundationChecksPassed: Object.values(checks).every(Boolean),
      missingProductionEvidence: [
        "provider-backed signed action receipts from the managed environment",
        "managed Postgres concurrency evidence",
        "least-privilege and tenant-policy verification",
        "alert delivery evidence",
        "independent privacy and security review",
      ],
    };
  }
}
