import { createHash, randomBytes, randomUUID } from "node:crypto";

import {
  foundationExerciseRegistryVersion,
  getFoundationExercise,
} from "@speech-therapy/clinical-domain";

import type { DatabaseClient, QueryResult } from "./database.ts";
import {
  maximumActiveLearnerDeviceSessions,
  maximumActorTokenGenerationsPerHour,
  maximumAssignmentReadsPerDeviceSessionPerHour,
  maximumAttemptUploadsPerDeviceSessionPerHour,
  maximumLearnerTokenGenerationsPerHour,
} from "./device-session-policy.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ActivePracticeAssignment,
  ConsentSnapshotInput,
  ConsentSnapshotRecord,
  DeletionReceipt,
  LearnerAttemptSummary,
  LearnerConsentSummary,
  LearnerDetail,
  LearnerExport,
  LearnerRecord,
  LearnerSummary,
  PracticeAssignmentInput,
  PracticeAssignmentRecord,
  PracticeAssignmentSummary,
  PracticeAttemptExportRecord,
  PracticeAttemptAnalysisExportRecord,
  PracticeAttemptAnalysisInput,
  LearnerDeviceContext,
  LearnerDeviceRequestOperation,
  LearnerDeviceSessionReceipt,
  LearnerDeviceSessionRevocationReceipt,
  LearnerDeviceSessionRotationReceipt,
  LearnerDeviceSessionSummary,
  PracticeAttemptInput,
  PracticeAttemptReceipt,
  ResearchArtifactImpactExportRecord,
  ReviewAttemptSummary,
} from "./types.ts";

const opaqueIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/;
const noticeVersion = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const sha256 = /^[a-f0-9]{64}$/;
const gitRevision = /^[a-f0-9]{40}$/;
const provenanceText = /^[A-Za-z0-9@][A-Za-z0-9@/_.+-]{0,199}$/;


interface ConsentRow extends Record<string, unknown> {
  id: string;
  tenant_id: string;
  learner_id: string;
  version: number;
  notice_version: string;
  audio_processing: boolean;
  video_processing: boolean;
  clinician_review: boolean;
  research_use: boolean;
  assent_status: ConsentSnapshotRecord["assentStatus"];
  captured_by_actor_id: string;
  captured_at: string | Date;
  supersedes_snapshot_id: string | null;
}

interface PracticeAssignmentRow extends Record<string, unknown> {
  id: string;
  tenant_id: string;
  learner_id: string;
  version: number;
  consent_snapshot_id: string;
  exercise_registry_version: string;
  exercise_definition_sha256: string;
  exercise_id: string;
  protocol_id: string;
  prompt: string;
  target_label: string;
  attempt_target: number;
  retry_limit: number;
  visual_processing: false;
  release_posture: "candidate-silent-only";
  assigned_by_actor_id: string;
  assigned_at: string | Date;
  supersedes_assignment_id: string | null;
}

interface ActivePracticeAssignmentRow extends PracticeAssignmentRow {
  accepted_repetitions: number;
  next_repetition_index: number | null;
  next_retry_index: number | null;
}

interface DeviceSessionIssuanceRow extends Record<string, unknown> {
  id: string | null;
  learner_id: string | null;
  expires_at: string | Date | null;
  consent_snapshot_id: string | null;
  authorized: boolean;
  target_exists: boolean;
  consent_eligible: boolean;
  active_count: number;
}

interface DeviceTokenRateLimitRow extends Record<string, unknown> {
  authorized: boolean;
  target_exists: boolean;
  allowed: boolean;
  retry_after_seconds: number | null;
}

interface LearnerDeviceAuthorizationRow extends Record<string, unknown> {
  session_id: string;
  tenant_id: string;
  learner_id: string;
  consent_snapshot_id: string;
  audio_processing: true;
  video_processing: boolean;
  clinician_review: boolean;
  research_use: boolean;
  allowed: boolean;
  retry_after_seconds: number | null;
}

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function tokenHash(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

function postgresErrorCode(error: unknown): string | undefined {
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string"
  ) {
    return error.code;
  }
  return undefined;
}

function postgresErrorConstraint(error: unknown): string | undefined {
  if (
    typeof error === "object" &&
    error !== null &&
    "constraint" in error &&
    typeof error.constraint === "string"
  ) {
    return error.constraint;
  }
  return undefined;
}

function mapConsent(row: ConsentRow): ConsentSnapshotRecord {
  return {
    id: row.id,
    tenantId: row.tenant_id,
    learnerId: row.learner_id,
    version: row.version,
    noticeVersion: row.notice_version,
    audioProcessing: row.audio_processing,
    videoProcessing: row.video_processing,
    clinicianReview: row.clinician_review,
    researchUse: row.research_use,
    assentStatus: row.assent_status,
    capturedByActorId: row.captured_by_actor_id,
    capturedAt: timestamp(row.captured_at),
    ...(row.supersedes_snapshot_id === null
      ? {}
      : { supersedesSnapshotId: row.supersedes_snapshot_id }),
  };
}

function mapPracticeAssignment(
  row: PracticeAssignmentRow,
): PracticeAssignmentRecord {
  return {
    id: row.id,
    tenantId: row.tenant_id,
    learnerId: row.learner_id,
    version: row.version,
    consentSnapshotId: row.consent_snapshot_id,
    exerciseRegistryVersion: row.exercise_registry_version,
    exerciseDefinitionSha256: row.exercise_definition_sha256,
    exerciseId: row.exercise_id,
    protocolId: row.protocol_id,
    prompt: row.prompt,
    targetLabel: row.target_label,
    attemptTarget: row.attempt_target,
    retryLimit: row.retry_limit,
    visualProcessing: false,
    releasePosture: "candidate-silent-only",
    assignedByActorId: row.assigned_by_actor_id,
    assignedAt: timestamp(row.assigned_at),
    ...(row.supersedes_assignment_id === null
      ? {}
      : { supersedesAssignmentId: row.supersedes_assignment_id }),
  };
}

function mapActivePracticeAssignment(
  row: ActivePracticeAssignmentRow,
): ActivePracticeAssignment {
  const assignment = mapPracticeAssignment(row);
  if (row.next_repetition_index === null) {
    return {
      ...assignment,
      progress: {
        status: "completed",
        acceptedRepetitions: row.accepted_repetitions,
      },
    };
  }
  if (
    row.next_retry_index === null ||
    row.next_retry_index > assignment.retryLimit
  ) {
    return {
      ...assignment,
      progress: {
        status: "retry-limit-reached",
        acceptedRepetitions: row.accepted_repetitions,
        repetitionIndex: row.next_repetition_index,
      },
    };
  }
  return {
    ...assignment,
    progress: {
      status: "ready",
      acceptedRepetitions: row.accepted_repetitions,
      repetitionIndex: row.next_repetition_index,
      retryIndex: row.next_retry_index,
    },
  };
}

function validateActor(actor: ActorContext): void {
  if (
    !opaqueIdentifier.test(actor.actorId) ||
    !opaqueIdentifier.test(actor.tenantId) ||
    !["owner", "clinician", "reviewer", "support"].includes(actor.role)
  ) {
    throw new PlatformDataError(
      "invalid-identifier",
      "Actor and tenant identifiers must be opaque tokens.",
    );
  }
}

function normalizedDisplayLabel(value: string): string {
  const label = value.trim().replace(/\s+/g, " ");
  if (
    label.length === 0 ||
    label.length > 120 ||
    /[\u0000-\u001f\u007f]/.test(label)
  ) {
    throw new PlatformDataError(
      "invalid-identifier",
      "Learner display labels must contain 1 to 120 visible characters.",
    );
  }
  return label;
}

type LearnerConsentJson = Omit<LearnerConsentSummary, "capturedAt"> & {
  capturedAt: string | Date;
};

type LearnerSummaryJson = Omit<
  LearnerSummary,
  "createdAt" | "lastPracticeAt" | "latestConsent"
> & {
  createdAt: string | Date;
  lastPracticeAt?: string | Date;
  latestConsent?: LearnerConsentJson;
};

type LearnerAttemptJson = Omit<LearnerAttemptSummary, "receivedAt"> & {
  receivedAt: string | Date;
};

type ReviewAttemptJson = Omit<ReviewAttemptSummary, "receivedAt"> & {
  receivedAt: string | Date;
};

type LearnerDeviceSessionSummaryJson = Omit<
  LearnerDeviceSessionSummary,
  "createdAt" | "expiresAt" | "revokedAt"
> & {
  createdAt: string | Date;
  expiresAt: string | Date;
  revokedAt?: string | Date;
};

function mapConsentSummary(value: LearnerConsentJson): LearnerConsentSummary {
  return { ...value, capturedAt: timestamp(value.capturedAt) };
}

function mapLearnerSummary(value: LearnerSummaryJson): LearnerSummary {
  return {
    id: value.id,
    displayLabel: value.displayLabel,
    createdAt: timestamp(value.createdAt),
    attemptCount: value.attemptCount,
    activeDeviceSessionCount: value.activeDeviceSessionCount,
    ...(value.lastPracticeAt === undefined
      ? {}
      : { lastPracticeAt: timestamp(value.lastPracticeAt) }),
    ...(value.latestConsent === undefined
      ? {}
      : { latestConsent: mapConsentSummary(value.latestConsent) }),
  };
}

function jsonArray<T>(value: readonly T[] | string): readonly T[] {
  return typeof value === "string" ? (JSON.parse(value) as T[]) : value;
}

function validateConsent(input: ConsentSnapshotInput): void {
  if (!opaqueIdentifier.test(input.learnerId)) {
    throw new PlatformDataError(
      "invalid-identifier",
      "Learner identifiers must be opaque tokens.",
    );
  }
  if (!noticeVersion.test(input.noticeVersion)) {
    throw new PlatformDataError(
      "invalid-consent",
      "A safe consent notice version is required.",
    );
  }
  if (input.videoProcessing) {
    throw new PlatformDataError(
      "invalid-consent",
      "Visual processing is unavailable until a reviewed protocol is enabled.",
    );
  }
  if (
    ["declined", "withdrawn"].includes(input.assentStatus) &&
    (input.audioProcessing ||
      input.videoProcessing ||
      input.clinicianReview ||
      input.researchUse)
  ) {
    throw new PlatformDataError(
      "invalid-consent",
      "Declined or withdrawn assent must disable every processing purpose.",
    );
  }
}

function validateDeviceSessionLifetime(lifetimeHours: number): void {
  if (
    !Number.isInteger(lifetimeHours) ||
    lifetimeHours < 1 ||
    lifetimeHours > 72
  ) {
    throw new PlatformDataError(
      "invalid-identifier",
      "Learner device sessions must last between 1 and 72 hours.",
    );
  }
}

export class PlatformDataService {
  readonly #database: DatabaseClient;

  constructor(database: DatabaseClient) {
    this.#database = database;
  }

  async resolveActorContext(
    externalSubjectHash: string,
    externalOrganizationHash: string,
  ): Promise<ActorContext | undefined> {
    if (
      !/^[a-f0-9]{64}$/.test(externalSubjectHash) ||
      !/^[a-f0-9]{64}$/.test(externalOrganizationHash)
    ) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Identity lookup hashes must be SHA-256 hex values.",
      );
    }
    const result = await this.#database.query<
      Record<string, unknown> & {
        actor_id: string;
        tenant_id: string;
        role: ActorContext["role"];
      }
    >(
      `
        SELECT membership.actor_id, membership.tenant_id, membership.role
        FROM tenant_memberships AS membership
        INNER JOIN actors ON actors.id = membership.actor_id
        INNER JOIN tenants ON tenants.id = membership.tenant_id
        WHERE actors.external_subject_hash = $1
          AND tenants.external_organization_hash = $2
          AND membership.status = 'active'
        LIMIT 1
      `,
      [externalSubjectHash, externalOrganizationHash],
    );
    const row = result.rows[0];
    return row
      ? { actorId: row.actor_id, tenantId: row.tenant_id, role: row.role }
      : undefined;
  }

  async createLearner(
    actor: ActorContext,
    displayLabel: string,
  ): Promise<LearnerRecord> {
    validateActor(actor);
    const label = normalizedDisplayLabel(displayLabel);
    const learnerId = randomUUID();
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        id: string;
        display_label: string;
        created_at: string | Date;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), inserted AS (
          INSERT INTO learners (id, tenant_id, display_label)
          SELECT $3, $1, $4
          WHERE EXISTS (SELECT 1 FROM authorized)
          RETURNING id, tenant_id, display_label, created_at
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $5, tenant_id, $2, 'learner.created', 'learner', id,
            jsonb_build_object('display_label_length', char_length(display_label))
          FROM inserted
        )
        SELECT id, display_label, created_at FROM inserted
      `,
      [actor.tenantId, actor.actorId, learnerId, label, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot create learners for this tenant.",
      );
    }
    return {
      id: row.id,
      displayLabel: row.display_label,
      createdAt: timestamp(row.created_at),
    };
  }

  async listLearners(actor: ActorContext): Promise<readonly LearnerSummary[]> {
    validateActor(actor);
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        authorized: boolean;
        learners: LearnerSummaryJson[] | string;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician', 'reviewer')
        ), learner_rows AS (
          SELECT jsonb_strip_nulls(jsonb_build_object(
            'id', learner.id,
            'displayLabel', learner.display_label,
            'createdAt', learner.created_at,
            'attemptCount', COALESCE(attempts.attempt_count, 0),
            'lastPracticeAt', attempts.last_practice_at,
            'activeDeviceSessionCount', COALESCE(sessions.active_count, 0),
            'latestConsent', CASE WHEN consent.id IS NULL THEN NULL ELSE
              jsonb_build_object(
                'id', consent.id,
                'version', consent.version,
                'noticeVersion', consent.notice_version,
                'audioProcessing', consent.audio_processing,
                'videoProcessing', consent.video_processing,
                'clinicianReview', consent.clinician_review,
                'researchUse', consent.research_use,
                'assentStatus', consent.assent_status,
                'capturedAt', consent.captured_at
              )
            END
          )) AS summary
          FROM learners AS learner
          LEFT JOIN LATERAL (
            SELECT snapshot.*
            FROM consent_snapshots AS snapshot
            WHERE snapshot.tenant_id = learner.tenant_id
              AND snapshot.learner_id = learner.id
            ORDER BY snapshot.version DESC
            LIMIT 1
          ) AS consent ON TRUE
          LEFT JOIN LATERAL (
            SELECT
              COUNT(*)::INTEGER AS attempt_count,
              MAX(received_at) AS last_practice_at
            FROM practice_attempts
            WHERE tenant_id = learner.tenant_id
              AND learner_id = learner.id
          ) AS attempts ON TRUE
          LEFT JOIN LATERAL (
            SELECT COUNT(*)::INTEGER AS active_count
            FROM learner_device_sessions
            WHERE tenant_id = learner.tenant_id
              AND learner_id = learner.id
              AND consent_snapshot_id = consent.id
              AND revoked_at IS NULL
              AND active_slot IS NOT NULL
              AND expires_at > CURRENT_TIMESTAMP
              AND consent.audio_processing = TRUE
              AND consent.assent_status IN ('affirmed', 'not-applicable')
          ) AS sessions ON TRUE
          WHERE learner.tenant_id = $1
            AND learner.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $3, $1, $2, 'learner.list.read', 'learner_collection', $1,
            '{}'::JSONB
          FROM authorized
          RETURNING id
        )
        SELECT
          EXISTS (SELECT 1 FROM authorized) AS authorized,
          COALESCE(
            (SELECT jsonb_agg(summary ORDER BY summary->>'displayLabel')
             FROM learner_rows),
            '[]'::JSONB
          ) AS learners,
          (SELECT id FROM audit LIMIT 1) AS audit_id
      `,
      [actor.tenantId, actor.actorId, auditId],
    );
    const row = result.rows[0];
    if (!row?.authorized) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot view learners for this tenant.",
      );
    }
    return jsonArray<LearnerSummaryJson>(row.learners).map(mapLearnerSummary);
  }

  async getLearner(
    actor: ActorContext,
    learnerId: string,
  ): Promise<LearnerDetail> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner identifiers must be opaque tokens.",
      );
    }
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        learner: LearnerSummaryJson;
        consents: LearnerConsentJson[] | string;
        attempts: LearnerAttemptJson[] | string;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician', 'reviewer')
        ), target AS (
          SELECT learner.*
          FROM learners AS learner
          WHERE learner.id = $3
            AND learner.tenant_id = $1
            AND learner.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
        ), consent_history AS (
          SELECT COALESCE(
            jsonb_agg(jsonb_build_object(
              'id', snapshot.id,
              'version', snapshot.version,
              'noticeVersion', snapshot.notice_version,
              'audioProcessing', snapshot.audio_processing,
              'videoProcessing', snapshot.video_processing,
              'clinicianReview', snapshot.clinician_review,
              'researchUse', snapshot.research_use,
              'assentStatus', snapshot.assent_status,
              'capturedAt', snapshot.captured_at
            ) ORDER BY snapshot.version DESC),
            '[]'::JSONB
          ) AS consents
          FROM consent_snapshots AS snapshot
          WHERE snapshot.tenant_id = $1 AND snapshot.learner_id = $3
        ), recent_attempts AS (
          SELECT COALESCE(
            jsonb_agg(item ORDER BY received_at DESC),
            '[]'::JSONB
          ) AS attempts
          FROM (
            SELECT
              attempt.received_at,
              jsonb_strip_nulls(jsonb_build_object(
                'attemptId', attempt.id,
                'exerciseId', attempt.exercise_id,
                'protocolId', attempt.protocol_id,
                'prompt', assignment.prompt,
                'targetLabel', assignment.target_label,
                'status', attempt.status,
                'durationMilliseconds', attempt.duration_milliseconds,
                'reasonCodes', attempt.reason_codes,
                'receivedAt', attempt.received_at,
                'benchmarkStatus', analysis.status
              )) AS item
            FROM practice_attempts AS attempt
            LEFT JOIN practice_assignments AS assignment
              ON assignment.tenant_id = attempt.tenant_id
             AND assignment.learner_id = attempt.learner_id
             AND assignment.id = attempt.assignment_id
            LEFT JOIN practice_attempt_analyses AS analysis
              ON analysis.attempt_id = attempt.id
            WHERE attempt.tenant_id = $1
              AND attempt.learner_id = $3
              AND attempt.consent_snapshot_id = (
                SELECT CASE
                  WHEN snapshot.clinician_review = TRUE THEN snapshot.id
                  ELSE NULL
                END
                FROM consent_snapshots AS snapshot
                WHERE snapshot.tenant_id = $1
                  AND snapshot.learner_id = $3
                ORDER BY snapshot.version DESC
                LIMIT 1
              )
            ORDER BY attempt.received_at DESC
            LIMIT 25
          ) AS limited_attempts
        ), learner_summary AS (
          SELECT jsonb_strip_nulls(jsonb_build_object(
            'id', target.id,
            'displayLabel', target.display_label,
            'createdAt', target.created_at,
            'attemptCount', (
              SELECT COUNT(*)::INTEGER FROM practice_attempts
              WHERE tenant_id = target.tenant_id AND learner_id = target.id
            ),
            'lastPracticeAt', (
              SELECT MAX(received_at) FROM practice_attempts
              WHERE tenant_id = target.tenant_id AND learner_id = target.id
            ),
            'activeDeviceSessionCount', (
              SELECT COUNT(*)::INTEGER FROM learner_device_sessions
              WHERE tenant_id = target.tenant_id
                AND learner_id = target.id
                AND revoked_at IS NULL
                AND active_slot IS NOT NULL
                AND expires_at > CURRENT_TIMESTAMP
                AND consent_snapshot_id = (
                  SELECT snapshot.id
                  FROM consent_snapshots AS snapshot
                  WHERE snapshot.tenant_id = target.tenant_id
                    AND snapshot.learner_id = target.id
                  ORDER BY snapshot.version DESC
                  LIMIT 1
                )
                AND COALESCE((
                  SELECT
                    snapshot.audio_processing = TRUE
                    AND snapshot.assent_status IN ('affirmed', 'not-applicable')
                  FROM consent_snapshots AS snapshot
                  WHERE snapshot.tenant_id = target.tenant_id
                    AND snapshot.learner_id = target.id
                  ORDER BY snapshot.version DESC
                  LIMIT 1
                ), FALSE)
            ),
            'latestConsent', (
              SELECT jsonb_build_object(
                'id', snapshot.id,
                'version', snapshot.version,
                'noticeVersion', snapshot.notice_version,
                'audioProcessing', snapshot.audio_processing,
                'videoProcessing', snapshot.video_processing,
                'clinicianReview', snapshot.clinician_review,
                'researchUse', snapshot.research_use,
                'assentStatus', snapshot.assent_status,
                'capturedAt', snapshot.captured_at
              )
              FROM consent_snapshots AS snapshot
              WHERE snapshot.tenant_id = target.tenant_id
                AND snapshot.learner_id = target.id
              ORDER BY snapshot.version DESC
              LIMIT 1
            )
          )) AS learner
          FROM target
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT $4, $1, $2, 'learner.read', 'learner', id, '{}'::JSONB
          FROM target
          RETURNING id
        )
        SELECT
          learner_summary.learner,
          consent_history.consents,
          recent_attempts.attempts,
          (SELECT id FROM audit LIMIT 1) AS audit_id
        FROM learner_summary, consent_history, recent_attempts
      `,
      [actor.tenantId, actor.actorId, learnerId, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot view this learner.",
      );
    }
    const summary = mapLearnerSummary(row.learner);
    return {
      ...summary,
      consentSnapshots: jsonArray<LearnerConsentJson>(row.consents).map(
        mapConsentSummary,
      ),
      recentAttempts: jsonArray<LearnerAttemptJson>(row.attempts).map(
        (attempt) => ({
          ...attempt,
          receivedAt: timestamp(attempt.receivedAt),
        }),
      ),
    };
  }

  async listReviewableAttempts(
    actor: ActorContext,
  ): Promise<readonly ReviewAttemptSummary[]> {
    validateActor(actor);
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        authorized: boolean;
        attempts: ReviewAttemptJson[] | string;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician', 'reviewer')
        ), reviewable_attempts AS (
          SELECT
            attempt.id AS attempt_id,
            attempt.received_at,
            jsonb_strip_nulls(jsonb_build_object(
              'attemptId', attempt.id,
              'learnerId', learner.id,
              'learnerDisplayLabel', learner.display_label,
              'consentSnapshotId', consent.id,
              'consentVersion', consent.version,
              'assignmentId', assignment.id,
              'exerciseId', attempt.exercise_id,
              'protocolId', attempt.protocol_id,
              'prompt', assignment.prompt,
              'targetLabel', assignment.target_label,
              'repetitionIndex', attempt.repetition_index,
              'retryIndex', attempt.retry_index,
              'status', attempt.status,
              'durationMilliseconds', attempt.duration_milliseconds,
              'reasonCodes', attempt.reason_codes,
              'receivedAt', attempt.received_at,
              'benchmarkStatus', analysis.status
            )) AS item
          FROM practice_attempts AS attempt
          INNER JOIN learners AS learner
            ON learner.tenant_id = attempt.tenant_id
           AND learner.id = attempt.learner_id
           AND learner.deleted_at IS NULL
          INNER JOIN LATERAL (
            SELECT snapshot.*
            FROM consent_snapshots AS snapshot
            WHERE snapshot.tenant_id = learner.tenant_id
              AND snapshot.learner_id = learner.id
            ORDER BY snapshot.version DESC
            LIMIT 1
          ) AS consent
            ON consent.id = attempt.consent_snapshot_id
           AND consent.clinician_review = TRUE
          INNER JOIN practice_assignments AS assignment
            ON assignment.tenant_id = attempt.tenant_id
           AND assignment.learner_id = attempt.learner_id
           AND assignment.id = attempt.assignment_id
          LEFT JOIN practice_attempt_analyses AS analysis
            ON analysis.attempt_id = attempt.id
          WHERE attempt.tenant_id = $1
            AND EXISTS (SELECT 1 FROM authorized)
          ORDER BY attempt.received_at DESC, attempt.id DESC
          LIMIT 100
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $3, $1, $2, 'practice-attempt.review-list.read',
            'practice_attempt_collection', $1,
            jsonb_build_object(
              'limit', 100,
              'result_count', (SELECT COUNT(*) FROM reviewable_attempts)
            )
          FROM authorized
          RETURNING id
        )
        SELECT
          EXISTS (SELECT 1 FROM authorized) AS authorized,
          COALESCE(
            (SELECT jsonb_agg(item ORDER BY received_at DESC, attempt_id DESC)
             FROM reviewable_attempts),
            '[]'::JSONB
          ) AS attempts,
          (SELECT id FROM audit LIMIT 1) AS audit_id
      `,
      [actor.tenantId, actor.actorId, auditId],
    );
    const row = result.rows[0];
    if (!row?.authorized) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot review attempts for this tenant.",
      );
    }
    return jsonArray<ReviewAttemptJson>(row.attempts).map((attempt) => ({
      ...attempt,
      receivedAt: timestamp(attempt.receivedAt),
    }));
  }

  async createConsentSnapshot(
    actor: ActorContext,
    input: ConsentSnapshotInput,
  ): Promise<ConsentSnapshotRecord> {
    validateActor(actor);
    validateConsent(input);
    const snapshotId = randomUUID();
    const auditId = randomUUID();
    let result: QueryResult<ConsentRow>;
    try {
      result = await this.#database.query<ConsentRow>(
        `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), target_learner AS (
          SELECT id, tenant_id
          FROM learners
          WHERE id = $3 AND tenant_id = $1 AND deleted_at IS NULL
          -- This serializes consent against deletion. A concurrent consent
          -- writer may still use a stale statement snapshot and receive 23505.
          FOR UPDATE
        ), inserted AS (
          INSERT INTO consent_snapshots (
            id, tenant_id, learner_id, version, notice_version,
            audio_processing, video_processing, clinician_review, research_use,
            assent_status, captured_by_actor_id, supersedes_snapshot_id
          )
          SELECT
            $4, target_learner.tenant_id, target_learner.id,
            COALESCE((
              SELECT MAX(version)
              FROM consent_snapshots
              WHERE tenant_id = $1 AND learner_id = $3
            ), 0) + 1,
            $5, $6, $7, $8, $9, $10, $2,
            (
              SELECT id
              FROM consent_snapshots
              WHERE tenant_id = $1 AND learner_id = $3
              ORDER BY version DESC
              LIMIT 1
            )
          FROM target_learner
          WHERE EXISTS (SELECT 1 FROM authorized)
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $11, tenant_id, $2, 'consent.snapshot.created', 'consent_snapshot', id,
            jsonb_build_object(
              'learner_id', learner_id,
              'version', version,
              'notice_version', notice_version
            )
          FROM inserted
        )
        SELECT * FROM inserted
        `,
        [
          actor.tenantId,
          actor.actorId,
          input.learnerId,
          snapshotId,
          input.noticeVersion,
          input.audioProcessing,
          input.videoProcessing,
          input.clinicianReview,
          input.researchUse,
          input.assentStatus,
          auditId,
        ],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError(
          "conflict",
          "Consent changed concurrently. Refresh and retry.",
        );
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot modify this learner.",
      );
    }
    return mapConsent(row);
  }

  async createPracticeAssignment(
    actor: ActorContext,
    input: PracticeAssignmentInput,
  ): Promise<PracticeAssignmentRecord> {
    validateActor(actor);
    const exercise = getFoundationExercise(input.exerciseId);
    if (
      !opaqueIdentifier.test(input.learnerId) ||
      !exercise ||
      !Number.isInteger(input.attemptTarget) ||
      input.attemptTarget < 1 ||
      input.attemptTarget > 20 ||
      !Number.isInteger(input.retryLimit) ||
      input.retryLimit < 0 ||
      input.retryLimit > 2
    ) {
      throw new PlatformDataError(
        "invalid-identifier",
        "The assignment target, dose, or retry limit is unsupported.",
      );
    }
    const assignmentId = randomUUID();
    const auditId = randomUUID();
    let result: QueryResult<PracticeAssignmentRow>;
    try {
      result = await this.#database.query<PracticeAssignmentRow>(
        `
          WITH authorized AS (
            SELECT 1
            FROM tenant_memberships
            WHERE tenant_id = $1
              AND actor_id = $2
              AND status = 'active'
              AND role IN ('owner', 'clinician')
          ), target_learner AS (
            SELECT learner.id, learner.tenant_id,
                   consent.id AS consent_snapshot_id
            FROM learners AS learner
            INNER JOIN LATERAL (
              SELECT snapshot.*
              FROM consent_snapshots AS snapshot
              WHERE snapshot.tenant_id = learner.tenant_id
                AND snapshot.learner_id = learner.id
              ORDER BY snapshot.version DESC
              LIMIT 1
            ) AS consent
              ON consent.audio_processing = TRUE
             AND consent.assent_status IN ('affirmed', 'not-applicable')
            WHERE learner.id = $3
              AND learner.tenant_id = $1
              AND learner.deleted_at IS NULL
            FOR UPDATE OF learner
          ), previous AS (
            SELECT assignment.*
            FROM practice_assignments AS assignment
            INNER JOIN target_learner
              ON target_learner.id = assignment.learner_id
             AND target_learner.tenant_id = assignment.tenant_id
            ORDER BY assignment.version DESC
            LIMIT 1
            FOR UPDATE OF assignment
          ), inserted AS (
            INSERT INTO practice_assignments (
              id, tenant_id, learner_id, version, consent_snapshot_id,
              exercise_registry_version, exercise_definition_sha256,
              exercise_id, protocol_id,
              prompt, target_label, attempt_target, retry_limit,
              visual_processing, release_posture, assigned_by_actor_id,
              supersedes_assignment_id
            )
            SELECT
              $4, target_learner.tenant_id, target_learner.id,
              COALESCE((SELECT version + 1 FROM previous), 1),
              target_learner.consent_snapshot_id, $5, $6,
              $7, $8, $9, $10, $11, $12, FALSE,
              'candidate-silent-only', $2,
              (SELECT id FROM previous)
            FROM target_learner
            WHERE EXISTS (SELECT 1 FROM authorized)
            RETURNING *
          ), audit AS (
            INSERT INTO audit_events (
              id, tenant_id, actor_id, action, resource_type, resource_id, metadata
            )
            SELECT
              $13, tenant_id, $2, 'practice-assignment.created',
              'practice_assignment', id,
              jsonb_build_object(
                'learner_id', learner_id,
                'version', version,
                'exercise_id', exercise_id,
                'attempt_target', attempt_target,
                'retry_limit', retry_limit,
                'visual_processing', visual_processing,
                'release_posture', release_posture
              )
            FROM inserted
          )
          SELECT * FROM inserted
        `,
        [
          actor.tenantId,
          actor.actorId,
          input.learnerId,
          assignmentId,
          foundationExerciseRegistryVersion,
          exercise.definitionSha256,
          exercise.id,
          exercise.protocolId,
          exercise.prompt,
          exercise.targetLabel,
          input.attemptTarget,
          input.retryLimit,
          auditId,
        ],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError(
          "conflict",
          "The assignment changed concurrently. Refresh and retry.",
        );
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "An active audio consent snapshot and clinician role are required.",
      );
    }
    return mapPracticeAssignment(row);
  }

  async listPracticeAssignments(
    actor: ActorContext,
  ): Promise<readonly PracticeAssignmentSummary[]> {
    validateActor(actor);
    const auditId = randomUUID();
    const result = await this.#database.query<
      PracticeAssignmentRow & { learner_display_label: string }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician', 'reviewer')
        ), rows AS (
          SELECT assignment.*, learner.display_label AS learner_display_label
          FROM learners AS learner
          INNER JOIN LATERAL (
            SELECT candidate.*
            FROM practice_assignments AS candidate
            WHERE candidate.tenant_id = learner.tenant_id
              AND candidate.learner_id = learner.id
            ORDER BY candidate.version DESC
            LIMIT 1
          ) AS assignment ON TRUE
          WHERE learner.tenant_id = $1
            AND learner.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $3, $1, $2, 'practice-assignment.list.read',
            'practice_assignment_collection', $1, '{}'::JSONB
          FROM authorized
        )
        SELECT * FROM rows ORDER BY learner_display_label, learner_id
      `,
      [actor.tenantId, actor.actorId, auditId],
    );
    if (
      result.rows.length === 0 &&
      !(
        await this.#database.query<{ authorized: boolean }>(
          `SELECT EXISTS (
             SELECT 1 FROM tenant_memberships
             WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
               AND role IN ('owner', 'clinician', 'reviewer')
           ) AS authorized`,
          [actor.tenantId, actor.actorId],
        )
      ).rows[0]?.authorized
    ) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot view assignments for this tenant.",
      );
    }
    return result.rows.map((row) => ({
      ...mapPracticeAssignment(row),
      learnerDisplayLabel: row.learner_display_label,
    }));
  }

  async getActivePracticeAssignment(
    context: LearnerDeviceContext,
  ): Promise<ActivePracticeAssignment | undefined> {
    if (
      !opaqueIdentifier.test(context.sessionId) ||
      !opaqueIdentifier.test(context.tenantId) ||
      !opaqueIdentifier.test(context.learnerId) ||
      !opaqueIdentifier.test(context.consentSnapshotId)
    ) {
      return undefined;
    }
    const result = await this.#database.query<ActivePracticeAssignmentRow>(
      `
        WITH active_session AS (
          SELECT session.tenant_id, session.learner_id
          FROM learner_device_sessions AS session
          INNER JOIN learners
            ON learners.id = session.learner_id
           AND learners.tenant_id = session.tenant_id
          INNER JOIN LATERAL (
            SELECT snapshot.*
            FROM consent_snapshots AS snapshot
            WHERE snapshot.tenant_id = session.tenant_id
              AND snapshot.learner_id = session.learner_id
            ORDER BY snapshot.version DESC
            LIMIT 1
          ) AS consent ON consent.id = session.consent_snapshot_id
          WHERE session.id = $1
            AND session.tenant_id = $2
            AND session.learner_id = $3
            AND session.consent_snapshot_id = $4
            AND session.revoked_at IS NULL
            AND session.active_slot IS NOT NULL
            AND session.expires_at > CURRENT_TIMESTAMP
            AND learners.deleted_at IS NULL
            AND consent.audio_processing = TRUE
            AND consent.assent_status IN ('affirmed', 'not-applicable')
        )
        SELECT
          assignment.*,
          COALESCE(accepted.accepted_repetitions, 0)::INTEGER
            AS accepted_repetitions,
          progress.next_repetition_index,
          progress.next_retry_index
        FROM practice_assignments AS assignment
        INNER JOIN active_session
          ON active_session.tenant_id = assignment.tenant_id
         AND active_session.learner_id = assignment.learner_id
         AND assignment.consent_snapshot_id = $4
        LEFT JOIN LATERAL (
          SELECT COUNT(DISTINCT attempt.repetition_index)::INTEGER
            AS accepted_repetitions
          FROM practice_attempts AS attempt
          WHERE attempt.tenant_id = assignment.tenant_id
            AND attempt.assignment_id = assignment.id
            AND attempt.status = 'accepted-silent'
        ) AS accepted ON TRUE
        LEFT JOIN LATERAL (
          SELECT
            repetition.repetition_index AS next_repetition_index,
            COALESCE(MAX(attempt.retry_index) FILTER (
              WHERE attempt.status = 'retry-capture'
            ), -1)::INTEGER + 1 AS next_retry_index
          FROM generate_series(
            1, assignment.attempt_target
          ) AS repetition(repetition_index)
          LEFT JOIN practice_attempts AS attempt
            ON attempt.tenant_id = assignment.tenant_id
           AND attempt.assignment_id = assignment.id
           AND attempt.repetition_index = repetition.repetition_index
          GROUP BY repetition.repetition_index
          HAVING COALESCE(BOOL_OR(
            attempt.status = 'accepted-silent'
          ), FALSE) = FALSE
          ORDER BY repetition.repetition_index
          LIMIT 1
        ) AS progress ON TRUE
        ORDER BY assignment.version DESC
        LIMIT 1
      `,
      [
        context.sessionId,
        context.tenantId,
        context.learnerId,
        context.consentSnapshotId,
      ],
    );
    const row = result.rows[0];
    return row ? mapActivePracticeAssignment(row) : undefined;
  }

  async #consumeDeviceTokenGenerationBudget(
    actor: ActorContext,
    learnerId: string,
  ): Promise<void> {
    const requestId = randomUUID();
    const result = await this.#database.query<DeviceTokenRateLimitRow>(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), target_learner AS (
          SELECT learner.id
          FROM learners AS learner
          WHERE learner.tenant_id = $1
            AND learner.id = $3
            AND learner.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
        ), ordered_limits AS (
          SELECT scope_type, scope_id, request_limit
          FROM (
            VALUES
              ('actor'::TEXT, $2::TEXT, $5::INTEGER),
              ('learner'::TEXT, $3::TEXT, $6::INTEGER)
          ) AS policy(scope_type, scope_id, request_limit)
          WHERE EXISTS (SELECT 1 FROM target_learner)
          ORDER BY scope_type, scope_id
        ), consumed AS (
          INSERT INTO device_access_rate_buckets (
            tenant_id, scope_type, scope_id, operation, window_started_at,
            request_limit, accepted_count, rejected_count,
            last_request_id, last_request_allowed, last_requested_at
          )
          SELECT
            $1, scope_type, scope_id, 'token-generation',
            date_trunc('hour', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
              AT TIME ZONE 'UTC',
            request_limit,
            1, 0, $4, TRUE, CURRENT_TIMESTAMP
          FROM ordered_limits
          ON CONFLICT (
            tenant_id, scope_type, scope_id, operation, window_started_at
          ) DO UPDATE SET
            request_limit = EXCLUDED.request_limit,
            accepted_count = CASE
              WHEN device_access_rate_buckets.accepted_count
                < EXCLUDED.request_limit
              THEN device_access_rate_buckets.accepted_count + 1
              ELSE device_access_rate_buckets.accepted_count
            END,
            rejected_count = CASE
              WHEN device_access_rate_buckets.accepted_count
                < EXCLUDED.request_limit
              THEN device_access_rate_buckets.rejected_count
              ELSE device_access_rate_buckets.rejected_count + 1
            END,
            last_request_id = EXCLUDED.last_request_id,
            last_request_allowed =
              device_access_rate_buckets.accepted_count
                < EXCLUDED.request_limit,
            last_requested_at = CURRENT_TIMESTAMP
          RETURNING
            last_request_allowed,
            window_started_at + INTERVAL '1 hour' AS window_ends_at
        )
        SELECT
          EXISTS (SELECT 1 FROM authorized) AS authorized,
          EXISTS (SELECT 1 FROM target_learner) AS target_exists,
          COALESCE((SELECT BOOL_AND(last_request_allowed) FROM consumed), FALSE)
            AS allowed,
          CASE
            WHEN COALESCE(
              (SELECT BOOL_AND(last_request_allowed) FROM consumed), FALSE
            ) THEN NULL
            ELSE GREATEST(
              1,
              CEIL(EXTRACT(EPOCH FROM (
                (SELECT MAX(window_ends_at) FROM consumed) - CURRENT_TIMESTAMP
              )))
            )::INTEGER
          END AS retry_after_seconds
      `,
      [
        actor.tenantId,
        actor.actorId,
        learnerId,
        requestId,
        maximumActorTokenGenerationsPerHour,
        maximumLearnerTokenGenerationsPerHour,
      ],
    );
    const row = result.rows[0];
    if (!row?.authorized || !row.target_exists) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot generate device tokens for this learner.",
      );
    }
    if (!row.allowed) {
      throw new PlatformDataError(
        "rate-limited",
        "Hourly device-token generation limit reached. Try again after the current UTC hour.",
        { retryAfterSeconds: row.retry_after_seconds ?? 3600 },
      );
    }
  }

  async issueLearnerDeviceSession(
    actor: ActorContext,
    learnerId: string,
    lifetimeHours: number = 24,
  ): Promise<LearnerDeviceSessionReceipt> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner identifiers must be opaque tokens.",
      );
    }
    validateDeviceSessionLifetime(lifetimeHours);
    await this.#consumeDeviceTokenGenerationBudget(actor, learnerId);
    const sessionId = randomUUID();
    const token = randomBytes(32).toString("base64url");
    const hash = tokenHash(token);
    const auditId = randomUUID();
    let result: QueryResult<DeviceSessionIssuanceRow> | undefined;
    for (
      let attempt = 0;
      attempt <= maximumActiveLearnerDeviceSessions;
      attempt += 1
    ) {
      try {
        result = await this.#database.query<DeviceSessionIssuanceRow>(
          `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), target_learner AS (
          SELECT id, tenant_id
          FROM learners
          WHERE id = $3
            AND tenant_id = $1
            AND deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
          FOR UPDATE
        ), latest_consent AS (
          SELECT consent.*
          FROM consent_snapshots AS consent
          INNER JOIN target_learner
            ON target_learner.id = consent.learner_id
           AND target_learner.tenant_id = consent.tenant_id
          ORDER BY consent.version DESC
          LIMIT 1
        ), released_slots AS (
          UPDATE learner_device_sessions AS session
          SET active_slot = NULL
          FROM target_learner AS learner, latest_consent AS consent
          WHERE session.tenant_id = learner.tenant_id
            AND session.learner_id = learner.id
            AND session.active_slot IS NOT NULL
            AND (
              session.revoked_at IS NOT NULL
              OR session.expires_at <= CURRENT_TIMESTAMP
              OR session.consent_snapshot_id <> consent.id
              OR consent.audio_processing IS DISTINCT FROM TRUE
              OR consent.assent_status NOT IN ('affirmed', 'not-applicable')
            )
          RETURNING session.id
        ), release_barrier AS (
          SELECT COUNT(*) AS released_count FROM released_slots
        ), occupied_slots AS (
          SELECT session.active_slot
          FROM learner_device_sessions AS session
          INNER JOIN target_learner AS learner
            ON learner.tenant_id = session.tenant_id
           AND learner.id = session.learner_id
          INNER JOIN latest_consent AS consent
            ON consent.id = session.consent_snapshot_id
          WHERE session.active_slot IS NOT NULL
            AND session.revoked_at IS NULL
            AND session.expires_at > CURRENT_TIMESTAMP
            AND consent.audio_processing = TRUE
            AND consent.assent_status IN ('affirmed', 'not-applicable')
        ), available_slot AS (
          SELECT slot.value::SMALLINT AS active_slot
          FROM generate_series(1, $7) AS slot(value)
          CROSS JOIN release_barrier
          WHERE NOT EXISTS (
            SELECT 1 FROM occupied_slots
            WHERE occupied_slots.active_slot = slot.value
          )
          ORDER BY slot.value
          LIMIT 1
        ), inserted AS (
          INSERT INTO learner_device_sessions (
            id, tenant_id, learner_id, token_hash, consent_snapshot_id,
            created_by_actor_id, expires_at, active_slot
          )
          SELECT
            $4, target_learner.tenant_id, target_learner.id, $5,
            latest_consent.id, $2,
            CURRENT_TIMESTAMP + ($6 * INTERVAL '1 hour'),
            available_slot.active_slot
          FROM target_learner, latest_consent, available_slot
          WHERE latest_consent.audio_processing = TRUE
            AND latest_consent.assent_status IN ('affirmed', 'not-applicable')
          RETURNING id, learner_id, expires_at, consent_snapshot_id
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $8, $1, $2, 'learner.device-session.created',
            'learner_device_session', id,
            jsonb_build_object(
              'learner_id', learner_id,
              'consent_snapshot_id', consent_snapshot_id,
              'expires_at', expires_at,
              'active_limit', $7,
              'active_count_after', (
                SELECT COUNT(*) + 1 FROM occupied_slots
              )
            )
          FROM inserted
          RETURNING id
        )
        SELECT
          inserted.id,
          inserted.learner_id,
          inserted.expires_at,
          inserted.consent_snapshot_id,
          EXISTS (SELECT 1 FROM authorized) AS authorized,
          EXISTS (SELECT 1 FROM target_learner) AS target_exists,
          COALESCE((
            SELECT
              audio_processing = TRUE
              AND assent_status IN ('affirmed', 'not-applicable')
            FROM latest_consent
          ), FALSE) AS consent_eligible,
          (SELECT COUNT(*)::INTEGER FROM occupied_slots) AS active_count,
          (SELECT id FROM audit LIMIT 1) AS audit_id
        FROM (VALUES (1)) AS anchor(value)
        LEFT JOIN inserted ON TRUE
          `,
          [
            actor.tenantId,
            actor.actorId,
            learnerId,
            sessionId,
            hash,
            lifetimeHours,
            maximumActiveLearnerDeviceSessions,
            auditId,
          ],
        );
        break;
      } catch (error) {
        if (
          postgresErrorCode(error) === "23505" &&
          postgresErrorConstraint(error) ===
            "learner_device_sessions_active_slot_idx"
        ) {
          if (attempt < maximumActiveLearnerDeviceSessions) continue;
          break;
        }
        throw error;
      }
    }
    if (!result) {
      throw new PlatformDataError(
        "conflict",
        "Device grant capacity changed concurrently. Refresh and retry.",
      );
    }
    const row = result.rows[0];
    if (
      row?.authorized &&
      row.target_exists &&
      row.consent_eligible &&
      row.active_count >= maximumActiveLearnerDeviceSessions
    ) {
      throw new PlatformDataError(
        "conflict",
        `A learner can have at most ${maximumActiveLearnerDeviceSessions} active device grants. Revoke or rotate an existing grant first.`,
      );
    }
    if (
      !row?.id ||
      !row.learner_id ||
      row.expires_at === null ||
      !row.consent_snapshot_id
    ) {
      throw new PlatformDataError(
        "access-denied",
        "An active consent snapshot is required for learner device access.",
      );
    }
    const receipt: LearnerDeviceSessionReceipt = {
      id: row.id,
      learnerId: row.learner_id,
      token,
      expiresAt: timestamp(row.expires_at),
      consentSnapshotId: row.consent_snapshot_id,
    };
    if (!(await this.resolveLearnerDeviceSession(receipt.token))) {
      throw new PlatformDataError(
        "conflict",
        "Consent changed while device access was issued. Refresh before trying again.",
      );
    }
    return receipt;
  }

  async rotateLearnerDeviceSession(
    actor: ActorContext,
    learnerId: string,
    sessionId: string,
    lifetimeHours: number = 24,
  ): Promise<LearnerDeviceSessionRotationReceipt> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId) || !opaqueIdentifier.test(sessionId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner and device-session identifiers must be opaque tokens.",
      );
    }
    validateDeviceSessionLifetime(lifetimeHours);
    await this.#consumeDeviceTokenGenerationBudget(actor, learnerId);
    const replacementSessionId = randomUUID();
    const replacementToken = randomBytes(32).toString("base64url");
    const replacementTokenHash = tokenHash(replacementToken);
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        id: string;
        learner_id: string;
        expires_at: string | Date;
        consent_snapshot_id: string;
        rotated_from_session_id: string;
        rotated_at: string | Date;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), target_learner AS (
          SELECT learner.id, learner.tenant_id
          FROM learners AS learner
          WHERE learner.id = $3
            AND learner.tenant_id = $1
            AND learner.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
          FOR UPDATE
        ), latest_consent AS (
          SELECT consent.*
          FROM consent_snapshots AS consent
          INNER JOIN target_learner AS learner
            ON learner.tenant_id = consent.tenant_id
           AND learner.id = consent.learner_id
          ORDER BY consent.version DESC
          LIMIT 1
        ), source_session AS (
          SELECT
            session.id,
            session.tenant_id,
            session.learner_id,
            session.active_slot
          FROM learner_device_sessions AS session
          INNER JOIN target_learner AS learner
            ON learner.tenant_id = session.tenant_id
           AND learner.id = session.learner_id
          INNER JOIN latest_consent AS consent
            ON consent.id = session.consent_snapshot_id
          WHERE session.id = $4
            AND session.revoked_at IS NULL
            AND session.expires_at > CURRENT_TIMESTAMP
            AND session.active_slot IS NOT NULL
            AND consent.audio_processing = TRUE
            AND consent.assent_status IN ('affirmed', 'not-applicable')
          FOR UPDATE OF session
        ), revoked AS (
          UPDATE learner_device_sessions AS session
          SET revoked_at = CURRENT_TIMESTAMP,
              active_slot = NULL
          FROM source_session AS source
          WHERE session.id = source.id
            AND session.tenant_id = source.tenant_id
            AND session.learner_id = source.learner_id
          RETURNING
            session.id,
            session.tenant_id,
            session.learner_id,
            session.revoked_at,
            source.active_slot AS released_active_slot
        ), inserted AS (
          INSERT INTO learner_device_sessions (
            id, tenant_id, learner_id, token_hash, consent_snapshot_id,
            created_by_actor_id, expires_at, active_slot
          )
          SELECT
            $5, revoked.tenant_id, revoked.learner_id, $6,
            consent.id, $2,
            CURRENT_TIMESTAMP + ($7 * INTERVAL '1 hour'),
            revoked.released_active_slot
          FROM revoked
          INNER JOIN latest_consent AS consent
            ON consent.tenant_id = revoked.tenant_id
           AND consent.learner_id = revoked.learner_id
          RETURNING id, tenant_id, learner_id, expires_at, consent_snapshot_id
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $8, inserted.tenant_id, $2, 'learner.device-session.rotated',
            'learner_device_session', inserted.id,
            jsonb_build_object(
              'learner_id', inserted.learner_id,
              'rotated_from_session_id', revoked.id,
              'replacement_session_id', inserted.id,
              'consent_snapshot_id', inserted.consent_snapshot_id,
              'rotated_at', revoked.revoked_at,
              'expires_at', inserted.expires_at
            )
          FROM inserted
          INNER JOIN revoked
            ON revoked.tenant_id = inserted.tenant_id
           AND revoked.learner_id = inserted.learner_id
          RETURNING id
        )
        SELECT
          inserted.id,
          inserted.learner_id,
          inserted.expires_at,
          inserted.consent_snapshot_id,
          revoked.id AS rotated_from_session_id,
          revoked.revoked_at AS rotated_at,
          (SELECT id FROM audit LIMIT 1) AS audit_id
        FROM inserted
        INNER JOIN revoked
          ON revoked.tenant_id = inserted.tenant_id
         AND revoked.learner_id = inserted.learner_id
      `,
      [
        actor.tenantId,
        actor.actorId,
        learnerId,
        sessionId,
        replacementSessionId,
        replacementTokenHash,
        lifetimeHours,
        auditId,
      ],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "Only an active current-consent device grant can be rotated.",
      );
    }
    const receipt: LearnerDeviceSessionRotationReceipt = {
      id: row.id,
      learnerId: row.learner_id,
      token: replacementToken,
      expiresAt: timestamp(row.expires_at),
      consentSnapshotId: row.consent_snapshot_id,
      rotatedFromSessionId: row.rotated_from_session_id,
      rotatedAt: timestamp(row.rotated_at),
    };
    if (!(await this.resolveLearnerDeviceSession(receipt.token))) {
      throw new PlatformDataError(
        "conflict",
        "Consent changed during rotation. Refresh device access before issuing another token.",
      );
    }
    return receipt;
  }

  async listLearnerDeviceSessions(
    actor: ActorContext,
    learnerId: string,
  ): Promise<readonly LearnerDeviceSessionSummary[]> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner identifiers must be opaque tokens.",
      );
    }
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        authorized: boolean;
        sessions: LearnerDeviceSessionSummaryJson[] | string;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician', 'reviewer')
        ), target_learner AS (
          SELECT learner.id, learner.tenant_id
          FROM learners AS learner
          WHERE learner.id = $3
            AND learner.tenant_id = $1
            AND learner.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM authorized)
        ), latest_consent AS (
          SELECT snapshot.*
          FROM consent_snapshots AS snapshot
          INNER JOIN target_learner AS learner
            ON learner.tenant_id = snapshot.tenant_id
           AND learner.id = snapshot.learner_id
          ORDER BY snapshot.version DESC
          LIMIT 1
        ), classified_sessions AS (
          SELECT
            session.id,
            session.learner_id,
            session.consent_snapshot_id,
            bound_consent.version AS consent_version,
            session.created_at,
            session.expires_at,
            session.revoked_at,
            session.active_slot,
            CASE
              WHEN session.revoked_at IS NOT NULL THEN 'revoked'
              WHEN session.expires_at <= CURRENT_TIMESTAMP THEN 'expired'
              WHEN latest_consent.id IS DISTINCT FROM session.consent_snapshot_id
                OR latest_consent.audio_processing IS DISTINCT FROM TRUE
                OR latest_consent.assent_status NOT IN ('affirmed', 'not-applicable')
                THEN 'consent-invalidated'
              WHEN session.active_slot IS NULL THEN 'inactive'
              ELSE 'active'
            END AS status
          FROM learner_device_sessions AS session
          INNER JOIN target_learner AS learner
            ON learner.tenant_id = session.tenant_id
           AND learner.id = session.learner_id
          INNER JOIN consent_snapshots AS bound_consent
            ON bound_consent.tenant_id = session.tenant_id
           AND bound_consent.learner_id = session.learner_id
           AND bound_consent.id = session.consent_snapshot_id
          LEFT JOIN latest_consent ON TRUE
        ), recent_inactive AS (
          SELECT *
          FROM classified_sessions
          WHERE status <> 'active'
          ORDER BY created_at DESC, id DESC
          LIMIT 25
        ), visible_sessions AS (
          SELECT * FROM classified_sessions WHERE status = 'active'
          UNION ALL
          SELECT * FROM recent_inactive
        ), session_rows AS (
          SELECT
            id AS session_id,
            created_at,
            status,
            jsonb_strip_nulls(jsonb_build_object(
              'id', id,
              'learnerId', learner_id,
              'consentSnapshotId', consent_snapshot_id,
              'consentVersion', consent_version,
              'createdAt', created_at,
              'expiresAt', expires_at,
              'revokedAt', revoked_at,
              'status', status
            )) AS item
          FROM visible_sessions
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $4, $1, $2, 'learner.device-session.list.read',
            'learner_device_session_collection', $3,
            jsonb_build_object(
              'learner_id', $3,
              'inactive_history_limit', 25,
              'result_count', (SELECT COUNT(*) FROM session_rows),
              'active_count', (
                SELECT COUNT(*) FROM session_rows WHERE status = 'active'
              )
            )
          FROM target_learner
          RETURNING id
        )
        SELECT
          EXISTS (SELECT 1 FROM target_learner) AS authorized,
          COALESCE(
            (SELECT jsonb_agg(item ORDER BY created_at DESC, session_id DESC)
             FROM session_rows),
            '[]'::JSONB
          ) AS sessions,
          (SELECT id FROM audit LIMIT 1) AS audit_id
      `,
      [actor.tenantId, actor.actorId, learnerId, auditId],
    );
    const row = result.rows[0];
    if (!row?.authorized) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot view device sessions for this learner.",
      );
    }
    return jsonArray<LearnerDeviceSessionSummaryJson>(row.sessions).map(
      (session) => {
        const { revokedAt, ...summary } = session;
        return {
          ...summary,
          createdAt: timestamp(summary.createdAt),
          expiresAt: timestamp(summary.expiresAt),
          ...(revokedAt === undefined
            ? {}
            : { revokedAt: timestamp(revokedAt) }),
        };
      },
    );
  }

  async revokeLearnerDeviceSession(
    actor: ActorContext,
    learnerId: string,
    sessionId: string,
  ): Promise<LearnerDeviceSessionRevocationReceipt> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId) || !opaqueIdentifier.test(sessionId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner and device-session identifiers must be opaque tokens.",
      );
    }
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        id: string;
        learner_id: string;
        revoked_at: string | Date;
        already_revoked: boolean;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), target AS (
          SELECT
            session.id,
            session.tenant_id,
            session.learner_id,
            session.revoked_at AS prior_revoked_at
          FROM learner_device_sessions AS session
          INNER JOIN learners AS learner
            ON learner.tenant_id = session.tenant_id
           AND learner.id = session.learner_id
           AND learner.deleted_at IS NULL
          WHERE session.id = $4
            AND session.tenant_id = $1
            AND session.learner_id = $3
            AND EXISTS (SELECT 1 FROM authorized)
          FOR UPDATE OF session
        ), updated AS (
          UPDATE learner_device_sessions AS session
          SET revoked_at = COALESCE(session.revoked_at, CURRENT_TIMESTAMP),
              active_slot = NULL
          FROM target
          WHERE session.id = target.id
            AND session.tenant_id = target.tenant_id
            AND session.learner_id = target.learner_id
          RETURNING
            session.id,
            session.tenant_id,
            session.learner_id,
            session.revoked_at,
            target.prior_revoked_at IS NOT NULL AS already_revoked
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $5, tenant_id, $2, 'learner.device-session.revoked',
            'learner_device_session', id,
            jsonb_build_object(
              'learner_id', learner_id,
              'revoked_at', revoked_at
            )
          FROM updated
          WHERE already_revoked = FALSE
        )
        SELECT id, learner_id, revoked_at, already_revoked
        FROM updated
      `,
      [actor.tenantId, actor.actorId, learnerId, sessionId, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot revoke this learner device session.",
      );
    }
    return {
      id: row.id,
      learnerId: row.learner_id,
      revokedAt: timestamp(row.revoked_at),
      alreadyRevoked: row.already_revoked,
    };
  }

  async resolveLearnerDeviceSession(
    token: string,
  ): Promise<LearnerDeviceContext | undefined> {
    return this.#resolveLearnerDeviceSession(token);
  }

  async authorizeLearnerDeviceRequest(
    token: string,
    operation: LearnerDeviceRequestOperation,
  ): Promise<LearnerDeviceContext | undefined> {
    if (operation !== "assignment-read" && operation !== "attempt-upload") {
      throw new PlatformDataError(
        "invalid-identifier",
        "The learner-device request operation is unsupported.",
      );
    }
    return this.#resolveLearnerDeviceSession(token, operation);
  }

  async #resolveLearnerDeviceSession(
    token: string,
    operation?: LearnerDeviceRequestOperation,
  ): Promise<LearnerDeviceContext | undefined> {
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return undefined;
    const requestLimit = operation === "assignment-read"
      ? maximumAssignmentReadsPerDeviceSessionPerHour
      : operation === "attempt-upload"
        ? maximumAttemptUploadsPerDeviceSessionPerHour
        : undefined;
    const result = await this.#database.query<LearnerDeviceAuthorizationRow>(
      `
        WITH active_session AS MATERIALIZED (
          SELECT
            session.id AS session_id,
            session.tenant_id,
            session.learner_id,
            consent.id AS consent_snapshot_id,
            consent.audio_processing,
            consent.video_processing,
            consent.clinician_review,
            consent.research_use
          FROM learner_device_sessions AS session
          INNER JOIN learners
            ON learners.id = session.learner_id
           AND learners.tenant_id = session.tenant_id
          INNER JOIN LATERAL (
            SELECT snapshot.*
            FROM consent_snapshots AS snapshot
            WHERE snapshot.tenant_id = session.tenant_id
              AND snapshot.learner_id = session.learner_id
            ORDER BY snapshot.version DESC
            LIMIT 1
          ) AS consent ON consent.id = session.consent_snapshot_id
          WHERE session.token_hash = $1
            AND session.revoked_at IS NULL
            AND session.active_slot IS NOT NULL
            AND session.expires_at > CURRENT_TIMESTAMP
            AND learners.deleted_at IS NULL
            AND consent.audio_processing = TRUE
            AND consent.assent_status IN ('affirmed', 'not-applicable')
          LIMIT 1
          FOR KEY SHARE OF session
        ), policy AS (
          SELECT $2::TEXT AS operation, $3::INTEGER AS request_limit
          WHERE $2::TEXT IS NOT NULL
        ), consumed AS (
          INSERT INTO learner_device_request_rate_buckets (
            tenant_id, session_id, operation, window_started_at,
            request_limit, accepted_count, rejected_count,
            last_request_id, last_request_allowed, last_requested_at
          )
          SELECT
            active_session.tenant_id,
            active_session.session_id,
            policy.operation,
            date_trunc('hour', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
              AT TIME ZONE 'UTC',
            policy.request_limit,
            1,
            0,
            $4,
            TRUE,
            CURRENT_TIMESTAMP
          FROM active_session
          CROSS JOIN policy
          ON CONFLICT (
            tenant_id, session_id, operation, window_started_at
          ) DO UPDATE SET
            request_limit = learner_device_request_rate_buckets.request_limit,
            accepted_count = CASE
              WHEN learner_device_request_rate_buckets.accepted_count
                < learner_device_request_rate_buckets.request_limit
              THEN learner_device_request_rate_buckets.accepted_count + 1
              ELSE learner_device_request_rate_buckets.accepted_count
            END,
            rejected_count = CASE
              WHEN learner_device_request_rate_buckets.accepted_count
                < learner_device_request_rate_buckets.request_limit
              THEN learner_device_request_rate_buckets.rejected_count
              ELSE learner_device_request_rate_buckets.rejected_count + 1
            END,
            last_request_id = EXCLUDED.last_request_id,
            last_request_allowed =
              learner_device_request_rate_buckets.accepted_count
                < learner_device_request_rate_buckets.request_limit,
            last_requested_at = CURRENT_TIMESTAMP
          RETURNING
            last_request_allowed,
            window_started_at + INTERVAL '1 hour' AS window_ends_at
        )
        SELECT
          active_session.*,
          CASE
            WHEN $2::TEXT IS NULL THEN TRUE
            ELSE COALESCE(consumed.last_request_allowed, FALSE)
          END AS allowed,
          CASE
            WHEN $2::TEXT IS NULL OR consumed.last_request_allowed THEN NULL
            ELSE GREATEST(
              1,
              CEIL(EXTRACT(EPOCH FROM (
                consumed.window_ends_at - CURRENT_TIMESTAMP
              )))
            )::INTEGER
          END AS retry_after_seconds
        FROM active_session
        LEFT JOIN consumed ON TRUE
      `,
      [tokenHash(token), operation ?? null, requestLimit ?? null, randomUUID()],
    );
    const row = result.rows[0];
    if (row && !row.allowed) {
      throw new PlatformDataError(
        "rate-limited",
        "This practice device has reached its hourly request limit. Try again after the current UTC hour.",
        { retryAfterSeconds: row.retry_after_seconds ?? 3600 },
      );
    }
    return row
      ? {
          sessionId: row.session_id,
          tenantId: row.tenant_id,
          learnerId: row.learner_id,
          consentSnapshotId: row.consent_snapshot_id,
          audioProcessing: true,
          videoProcessing: row.video_processing,
          clinicianReview: row.clinician_review,
          researchUse: row.research_use,
        }
      : undefined;
  }

  async recordPracticeAttempt(
    context: LearnerDeviceContext,
    input: PracticeAttemptInput,
  ): Promise<PracticeAttemptReceipt> {
    if (
      !opaqueIdentifier.test(context.sessionId) ||
      !opaqueIdentifier.test(context.tenantId) ||
      !opaqueIdentifier.test(context.learnerId) ||
      !opaqueIdentifier.test(context.consentSnapshotId) ||
      !opaqueIdentifier.test(input.attemptId) ||
      !opaqueIdentifier.test(input.assignmentId) ||
      !/^[A-Za-z0-9][A-Za-z0-9_.-]{3,79}$/.test(input.exerciseId) ||
      !opaqueIdentifier.test(input.protocolId)
    ) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Attempt identifiers must be opaque versioned tokens.",
      );
    }
    const allowedReasonCodes = new Set([
      "audio-clipping",
      "audio-too-quiet",
      "utterance-too-short",
      "utterance-too-long",
      "background-noise",
      "multiple-speakers",
    ]);
    if (
      !["accepted-silent", "retry-capture"].includes(input.status) ||
      !Number.isInteger(input.repetitionIndex) ||
      input.repetitionIndex < 1 ||
      input.repetitionIndex > 20 ||
      !Number.isInteger(input.retryIndex) ||
      input.retryIndex < 0 ||
      input.retryIndex > 2 ||
      !Number.isInteger(input.durationMilliseconds) ||
      input.durationMilliseconds < 1 ||
      input.durationMilliseconds > 6_250 ||
      input.sampleRateHertz !== 16_000 ||
      !Number.isFinite(input.rmsDbfs) ||
      input.rmsDbfs < -160 ||
      input.rmsDbfs > 0 ||
      !Number.isFinite(input.peakAmplitude) ||
      input.peakAmplitude < 0 ||
      input.peakAmplitude > 1 ||
      new Set(input.reasonCodes).size !== input.reasonCodes.length ||
      input.reasonCodes.some((code) => !allowedReasonCodes.has(code))
    ) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Attempt capture evidence is outside the supported range.",
      );
    }
    // Exact float comparison is intentional: every idempotent replay is
    // re-derived deterministically from the same server-inspected PCM bytes.
    // Client-supplied evidence must never cross this boundary.
    const result = await this.#database.query<
      Record<string, unknown> & {
        id: string;
        status: PracticeAttemptReceipt["status"];
        reason_codes: PracticeAttemptInput["reasonCodes"] | string;
      }
    >(
      `
        WITH active_session AS (
          SELECT session.id, session.tenant_id, session.learner_id,
                 consent.id AS consent_snapshot_id
          FROM learner_device_sessions AS session
          INNER JOIN learners
            ON learners.id = session.learner_id
           AND learners.tenant_id = session.tenant_id
          INNER JOIN LATERAL (
            SELECT snapshot.*
            FROM consent_snapshots AS snapshot
            WHERE snapshot.tenant_id = session.tenant_id
              AND snapshot.learner_id = session.learner_id
            ORDER BY snapshot.version DESC
            LIMIT 1
          ) AS consent ON consent.id = session.consent_snapshot_id
          WHERE session.id = $1
            AND session.tenant_id = $2
            AND session.learner_id = $3
            AND session.consent_snapshot_id = $4
            AND session.revoked_at IS NULL
            AND session.active_slot IS NOT NULL
            AND session.expires_at > CURRENT_TIMESTAMP
            AND learners.deleted_at IS NULL
            AND consent.audio_processing = TRUE
            AND consent.assent_status IN ('affirmed', 'not-applicable')
        ), active_assignment AS (
          SELECT assignment.*
          FROM practice_assignments AS assignment
          INNER JOIN active_session
            ON active_session.tenant_id = assignment.tenant_id
           AND active_session.learner_id = assignment.learner_id
           AND active_session.consent_snapshot_id = assignment.consent_snapshot_id
          WHERE assignment.id = $6
            AND assignment.exercise_id = $7
            AND assignment.protocol_id = $8
            AND $9 BETWEEN 1 AND assignment.attempt_target
            AND $10 BETWEEN 0 AND assignment.retry_limit
            AND NOT EXISTS (
              SELECT 1
              FROM practice_assignments AS newer
              WHERE newer.tenant_id = assignment.tenant_id
                AND newer.learner_id = assignment.learner_id
                AND newer.version > assignment.version
            )
        ), next_slot AS (
          SELECT
            assignment.id AS assignment_id,
            slot.repetition_index,
            slot.next_retry_index
          FROM active_assignment AS assignment
          INNER JOIN LATERAL (
            SELECT
              repetition.repetition_index,
              COALESCE(MAX(attempt.retry_index) FILTER (
                WHERE attempt.status = 'retry-capture'
              ), -1)::INTEGER + 1 AS next_retry_index
            FROM generate_series(
              1, assignment.attempt_target
            ) AS repetition(repetition_index)
            LEFT JOIN practice_attempts AS attempt
              ON attempt.tenant_id = assignment.tenant_id
             AND attempt.assignment_id = assignment.id
             AND attempt.repetition_index = repetition.repetition_index
            GROUP BY repetition.repetition_index
            HAVING COALESCE(BOOL_OR(
              attempt.status = 'accepted-silent'
            ), FALSE) = FALSE
            ORDER BY repetition.repetition_index
            LIMIT 1
          ) AS slot ON slot.next_retry_index <= assignment.retry_limit
        ), existing AS (
          SELECT id, status, reason_codes
          FROM practice_attempts
          WHERE id = $5
            AND tenant_id = $2
            AND learner_id = $3
            AND device_session_id = $1
            AND consent_snapshot_id = $4
            AND assignment_id = $6
            AND exercise_id = $7
            AND protocol_id = $8
            AND repetition_index = $9
            AND retry_index = $10
            AND duration_milliseconds = $11
            AND sample_rate_hertz = $12
            AND rms_dbfs = $13
            AND peak_amplitude = $14
            AND status = $15
            AND reason_codes = $16::JSONB
            AND EXISTS (SELECT 1 FROM active_assignment)
        ), inserted AS (
          INSERT INTO practice_attempts (
            id, tenant_id, learner_id, device_session_id, consent_snapshot_id,
            assignment_id, exercise_id, protocol_id, repetition_index,
            retry_index, status, duration_milliseconds,
            sample_rate_hertz, rms_dbfs, peak_amplitude, reason_codes
          )
          SELECT
            $5, tenant_id, learner_id, id, consent_snapshot_id,
            $6, $7, $8, $9, $10, $15, $11, $12, $13, $14, $16::JSONB
          FROM active_session
          INNER JOIN next_slot
            ON next_slot.assignment_id = $6
           AND next_slot.repetition_index = $9
           AND next_slot.next_retry_index = $10
          ON CONFLICT DO NOTHING
          RETURNING id, status, reason_codes
        )
        SELECT * FROM inserted
        UNION ALL
        SELECT * FROM existing
        WHERE NOT EXISTS (SELECT 1 FROM inserted)
        LIMIT 1
      `,
      [
        context.sessionId,
        context.tenantId,
        context.learnerId,
        context.consentSnapshotId,
        input.attemptId,
        input.assignmentId,
        input.exerciseId,
        input.protocolId,
        input.repetitionIndex,
        input.retryIndex,
        input.durationMilliseconds,
        input.sampleRateHertz,
        input.rmsDbfs,
        input.peakAmplitude,
        input.status,
        JSON.stringify(input.reasonCodes),
      ],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "The learner device session cannot record this attempt.",
      );
    }
    const reasonCodes =
      typeof row.reason_codes === "string"
        ? (JSON.parse(row.reason_codes) as PracticeAttemptInput["reasonCodes"])
        : row.reason_codes;
    return {
      attemptId: row.id,
      status: row.status,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes,
    };
  }

  async recordPracticeAttemptAnalysis(
    context: LearnerDeviceContext,
    input: PracticeAttemptAnalysisInput,
  ): Promise<void> {
    const scored = input.status === "scored-ambiguous";
    if (
      !opaqueIdentifier.test(context.sessionId) ||
      !opaqueIdentifier.test(context.tenantId) ||
      !opaqueIdentifier.test(context.learnerId) ||
      !opaqueIdentifier.test(context.consentSnapshotId) ||
      !opaqueIdentifier.test(input.attemptId) ||
      input.releasePosture !== "benchmark-only" ||
      input.learnerFeedbackEligible !== false ||
      !provenanceText.test(input.checkpointId) ||
      !gitRevision.test(input.checkpointRevision) ||
      !provenanceText.test(input.runtime) ||
      !sha256.test(input.modelFileSha256) ||
      !sha256.test(input.vocabularyFileSha256) ||
      !noticeVersion.test(input.lexiconVersion) ||
      !noticeVersion.test(input.calibrationVersion) ||
      !noticeVersion.test(input.scoringPolicyVersion) ||
      !Number.isInteger(input.inferenceMilliseconds) ||
      input.inferenceMilliseconds < 0 ||
      input.inferenceMilliseconds > 300_000 ||
      (scored &&
        (!Number.isFinite(input.pCorrect) ||
          input.pCorrect < 0 ||
          input.pCorrect > 1 ||
          !Number.isFinite(input.pError) ||
          input.pError < 0 ||
          input.pError > 1 ||
          input.pCorrect + input.pError > 1.000001 ||
          !Number.isFinite(input.hypothesisCoverage) ||
          input.hypothesisCoverage < 0 ||
          input.hypothesisCoverage > 1 ||
          input.calibrated !== false ||
          input.ambiguous !== true)) ||
      (!scored && input.failureCode !== "benchmark-unavailable")
    ) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Attempt analysis evidence is outside the benchmark-only boundary.",
      );
    }
    const result = await this.#database.query<{ attempt_id: string }>(
      `
        WITH active_session AS (
          SELECT session.id, session.tenant_id, session.learner_id,
                 consent.id AS consent_snapshot_id
          FROM learner_device_sessions AS session
          INNER JOIN learners
            ON learners.id = session.learner_id
           AND learners.tenant_id = session.tenant_id
          INNER JOIN LATERAL (
            SELECT snapshot.*
            FROM consent_snapshots AS snapshot
            WHERE snapshot.tenant_id = session.tenant_id
              AND snapshot.learner_id = session.learner_id
            ORDER BY snapshot.version DESC
            LIMIT 1
          ) AS consent ON consent.id = session.consent_snapshot_id
          WHERE session.id = $1
            AND session.tenant_id = $2
            AND session.learner_id = $3
            AND session.consent_snapshot_id = $4
            AND session.revoked_at IS NULL
            AND session.active_slot IS NOT NULL
            AND session.expires_at > CURRENT_TIMESTAMP
            AND learners.deleted_at IS NULL
            AND consent.audio_processing = TRUE
            AND consent.research_use = TRUE
            AND consent.assent_status IN ('affirmed', 'not-applicable')
        ), target_attempt AS (
          SELECT attempt.id, attempt.tenant_id, attempt.learner_id,
                 attempt.consent_snapshot_id
          FROM practice_attempts AS attempt
          INNER JOIN active_session AS session
            ON session.id = attempt.device_session_id
           AND session.tenant_id = attempt.tenant_id
           AND session.learner_id = attempt.learner_id
           AND session.consent_snapshot_id = attempt.consent_snapshot_id
          WHERE attempt.id = $5
        ), existing AS (
          SELECT analysis.attempt_id
          FROM practice_attempt_analyses AS analysis
          WHERE analysis.attempt_id = $5
            AND analysis.tenant_id = $2
            AND analysis.learner_id = $3
            AND analysis.consent_snapshot_id = $4
            AND analysis.status = $6
            AND analysis.release_posture = $7
            AND analysis.learner_feedback_eligible = $8
            AND analysis.checkpoint_id = $9
            AND analysis.checkpoint_revision = $10
            AND analysis.runtime = $11
            AND analysis.model_file_sha256 = $12
            AND analysis.vocabulary_file_sha256 = $13
            AND analysis.lexicon_version = $14
            AND analysis.calibration_version = $15
            AND analysis.scoring_policy_version = $16
            AND analysis.p_correct IS NOT DISTINCT FROM $17::DOUBLE PRECISION
            AND analysis.p_error IS NOT DISTINCT FROM $18::DOUBLE PRECISION
            AND analysis.hypothesis_coverage IS NOT DISTINCT FROM $19::DOUBLE PRECISION
            AND analysis.calibrated IS NOT DISTINCT FROM $20::BOOLEAN
            AND analysis.ambiguous IS NOT DISTINCT FROM $21::BOOLEAN
            AND analysis.failure_code IS NOT DISTINCT FROM $22::TEXT
            AND EXISTS (SELECT 1 FROM target_attempt)
        ), inserted AS (
          INSERT INTO practice_attempt_analyses (
            attempt_id, tenant_id, learner_id, consent_snapshot_id,
            status, release_posture, learner_feedback_eligible,
            checkpoint_id, checkpoint_revision, runtime,
            model_file_sha256, vocabulary_file_sha256,
            lexicon_version, calibration_version, scoring_policy_version,
            p_correct, p_error, hypothesis_coverage, calibrated, ambiguous,
            failure_code, inference_milliseconds
          )
          SELECT
            id, tenant_id, learner_id, consent_snapshot_id,
            $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
            $17, $18, $19, $20, $21, $22, $23
          FROM target_attempt
          ON CONFLICT (attempt_id) DO NOTHING
          RETURNING attempt_id
        )
        SELECT * FROM inserted
        UNION ALL
        SELECT * FROM existing
        WHERE NOT EXISTS (SELECT 1 FROM inserted)
        LIMIT 1
      `,
      [
        context.sessionId,
        context.tenantId,
        context.learnerId,
        context.consentSnapshotId,
        input.attemptId,
        input.status,
        input.releasePosture,
        input.learnerFeedbackEligible,
        input.checkpointId,
        input.checkpointRevision,
        input.runtime,
        input.modelFileSha256,
        input.vocabularyFileSha256,
        input.lexiconVersion,
        input.calibrationVersion,
        input.scoringPolicyVersion,
        scored ? input.pCorrect : null,
        scored ? input.pError : null,
        scored ? input.hypothesisCoverage : null,
        scored ? input.calibrated : null,
        scored ? input.ambiguous : null,
        scored ? null : input.failureCode,
        input.inferenceMilliseconds,
      ],
    );
    if (!result.rows[0]) {
      throw new PlatformDataError(
        "access-denied",
        "The learner device session cannot record this benchmark analysis.",
      );
    }
  }

  async hasPracticeAttemptAnalysis(
    context: LearnerDeviceContext,
    attemptId: string,
  ): Promise<boolean> {
    if (
      !opaqueIdentifier.test(context.sessionId) ||
      !opaqueIdentifier.test(context.tenantId) ||
      !opaqueIdentifier.test(context.learnerId) ||
      !opaqueIdentifier.test(context.consentSnapshotId) ||
      !opaqueIdentifier.test(attemptId)
    ) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Attempt analysis lookup identifiers are invalid.",
      );
    }
    const result = await this.#database.query<{ attempt_id: string }>(
      `
        SELECT analysis.attempt_id
        FROM practice_attempt_analyses AS analysis
        INNER JOIN practice_attempts AS attempt
          ON attempt.id = analysis.attempt_id
         AND attempt.tenant_id = analysis.tenant_id
         AND attempt.learner_id = analysis.learner_id
         AND attempt.consent_snapshot_id = analysis.consent_snapshot_id
        INNER JOIN learner_device_sessions AS session
          ON session.id = attempt.device_session_id
         AND session.tenant_id = attempt.tenant_id
         AND session.learner_id = attempt.learner_id
         AND session.consent_snapshot_id = attempt.consent_snapshot_id
        INNER JOIN learners
          ON learners.id = session.learner_id
         AND learners.tenant_id = session.tenant_id
        INNER JOIN LATERAL (
          SELECT snapshot.*
          FROM consent_snapshots AS snapshot
          WHERE snapshot.tenant_id = session.tenant_id
            AND snapshot.learner_id = session.learner_id
          ORDER BY snapshot.version DESC
          LIMIT 1
        ) AS consent ON consent.id = session.consent_snapshot_id
        WHERE analysis.attempt_id = $5
          AND session.id = $1
          AND session.tenant_id = $2
          AND session.learner_id = $3
          AND session.consent_snapshot_id = $4
          AND session.revoked_at IS NULL
          AND session.active_slot IS NOT NULL
          AND session.expires_at > CURRENT_TIMESTAMP
          AND learners.deleted_at IS NULL
          AND consent.audio_processing = TRUE
          AND consent.research_use = TRUE
          AND consent.assent_status IN ('affirmed', 'not-applicable')
        LIMIT 1
      `,
      [
        context.sessionId,
        context.tenantId,
        context.learnerId,
        context.consentSnapshotId,
        attemptId,
      ],
    );
    return result.rows.length === 1;
  }

  async exportLearner(
    actor: ActorContext,
    learnerId: string,
  ): Promise<LearnerExport> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner identifiers must be opaque tokens.",
      );
    }
    const requestId = randomUUID();
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        request_id: string;
        learner_id: string;
        display_label: string;
        created_at: string | Date;
        deleted_at: string | Date | null;
        snapshots: ConsentRow[] | string;
        assignments: PracticeAssignmentRow[] | string;
        attempts: PracticeAttemptExportRecord[] | string;
        analyses: PracticeAttemptAnalysisExportRecord[] | string;
        artifact_impacts: ResearchArtifactImpactExportRecord[] | string;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role IN ('owner', 'clinician')
        ), target_learner AS (
          SELECT id, tenant_id, display_label, created_at, deleted_at
          FROM learners
          WHERE id = $3 AND tenant_id = $1
        ), consents AS (
          SELECT COALESCE(
            jsonb_agg(to_jsonb(consent_snapshots) ORDER BY version),
            '[]'::JSONB
          ) AS snapshots
          FROM consent_snapshots
          WHERE tenant_id = $1 AND learner_id = $3
        ), attempts AS (
          SELECT COALESCE(
            jsonb_agg(
              jsonb_build_object(
                'attemptId', id,
                'assignmentId', assignment_id,
                'repetitionIndex', repetition_index,
                'retryIndex', retry_index,
                'deviceSessionId', device_session_id,
                'consentSnapshotId', consent_snapshot_id,
                'exerciseId', exercise_id,
                'protocolId', protocol_id,
                'status', status,
                'durationMilliseconds', duration_milliseconds,
                'sampleRateHertz', sample_rate_hertz,
                'rmsDbfs', rms_dbfs,
                'peakAmplitude', peak_amplitude,
                'reasonCodes', reason_codes,
                'mediaRetained', media_retained,
                'receivedAt', received_at
              ) ORDER BY received_at, id
            ),
            '[]'::JSONB
          ) AS attempts
          FROM practice_attempts
          WHERE tenant_id = $1 AND learner_id = $3
        ), assignments AS (
          SELECT COALESCE(
            jsonb_agg(to_jsonb(practice_assignments) ORDER BY version),
            '[]'::JSONB
          ) AS assignments
          FROM practice_assignments
          WHERE tenant_id = $1 AND learner_id = $3
        ), analyses AS (
          SELECT COALESCE(
            jsonb_agg(
              jsonb_strip_nulls(jsonb_build_object(
                'attemptId', attempt_id,
                'status', status,
                'releasePosture', release_posture,
                'learnerFeedbackEligible', learner_feedback_eligible,
                'checkpointId', checkpoint_id,
                'checkpointRevision', checkpoint_revision,
                'runtime', runtime,
                'modelFileSha256', model_file_sha256,
                'vocabularyFileSha256', vocabulary_file_sha256,
                'lexiconVersion', lexicon_version,
                'calibrationVersion', calibration_version,
                'scoringPolicyVersion', scoring_policy_version,
                'pCorrect', p_correct,
                'pError', p_error,
                'hypothesisCoverage', hypothesis_coverage,
                'calibrated', calibrated,
                'ambiguous', ambiguous,
                'failureCode', failure_code,
                'inferenceMilliseconds', inference_milliseconds,
                'receivedAt', received_at
              )) ORDER BY received_at, attempt_id
            ),
            '[]'::JSONB
          ) AS analyses
          FROM practice_attempt_analyses
          WHERE tenant_id = $1 AND learner_id = $3
        ), subject_artifact_dependencies AS (
          SELECT dependency.artifact_id,
            array_agg(DISTINCT dependency.consent_snapshot_id
              ORDER BY dependency.consent_snapshot_id) AS consent_snapshot_ids,
            array_agg(DISTINCT dependency.processing_purpose
              ORDER BY dependency.processing_purpose) AS processing_purposes
          FROM artifact_consent_dependencies AS dependency
          WHERE dependency.tenant_id = $1 AND dependency.learner_id = $3
          GROUP BY dependency.artifact_id
        ), artifact_impacts AS (
          SELECT COALESCE(
            jsonb_agg(
              jsonb_build_object(
                'artifactId', artifact.id,
                'kind', artifact.kind,
                'version', artifact.version,
                'status', artifact.status,
                'releasePosture', artifact.release_posture,
                'learnerFeedbackEligible', artifact.learner_feedback_eligible,
                'consentSnapshotIds', dependency.consent_snapshot_ids,
                'processingPurposes', dependency.processing_purposes,
                'subjectQuarantineEvents', (
                  SELECT COALESCE(
                    jsonb_agg(
                      jsonb_build_object(
                        'reason', quarantine.reason,
                        'occurredAt', quarantine.occurred_at,
                        'actions', (
                          SELECT COALESCE(
                            jsonb_agg(
                              jsonb_strip_nulls(jsonb_build_object(
                                'actionType', action.action_type,
                                'status', action.status,
                                'attemptCount', action.attempt_count,
                                'receiptRecorded', action.receipt_reference IS NOT NULL
                                  AND action.receipt_sha256 IS NOT NULL,
                                'completedAt', action.completed_at,
                                'lastErrorCode', action.last_error_code
                              )) ORDER BY action.action_type
                            ),
                            '[]'::JSONB
                          )
                          FROM artifact_quarantine_actions AS action
                          WHERE action.quarantine_event_sequence_id = quarantine.sequence_id
                            AND action.tenant_id = $1
                            AND action.source_learner_id = $3
                        )
                      ) ORDER BY quarantine.sequence_id
                    ),
                    '[]'::JSONB
                  )
                  FROM artifact_quarantine_events AS quarantine
                  WHERE quarantine.tenant_id = $1
                    AND quarantine.artifact_id = artifact.id
                    AND quarantine.source_learner_id = $3
                )
              ) ORDER BY artifact.created_at, artifact.id
            ),
            '[]'::JSONB
          ) AS impacts
          FROM subject_artifact_dependencies AS dependency
          INNER JOIN ml_artifacts AS artifact
            ON artifact.id = dependency.artifact_id AND artifact.tenant_id = $1
        ), request_insert AS (
          INSERT INTO data_subject_requests (
            id, tenant_id, learner_id, kind, status, requested_by_actor_id,
            completed_at, receipt
          )
          SELECT
            $4, target_learner.tenant_id, target_learner.id, 'export', 'completed',
            $2, CURRENT_TIMESTAMP,
            jsonb_build_object(
              'format', 'application/json',
              'consent_snapshot_count', jsonb_array_length(consents.snapshots),
              'practice_assignment_count', jsonb_array_length(assignments.assignments),
              'practice_attempt_count', jsonb_array_length(attempts.attempts),
              'practice_analysis_count', jsonb_array_length(analyses.analyses),
              'research_artifact_impact_count', jsonb_array_length(artifact_impacts.impacts)
            )
          FROM target_learner, consents, assignments, attempts, analyses,
            artifact_impacts
          WHERE EXISTS (SELECT 1 FROM authorized)
          RETURNING id
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $5, $1, $2, 'learner.export.completed', 'learner', $3,
            jsonb_build_object('request_id', id)
          FROM request_insert
        )
        SELECT
          request_insert.id AS request_id,
          target_learner.id AS learner_id,
          target_learner.display_label,
          target_learner.created_at,
          target_learner.deleted_at,
          consents.snapshots,
          assignments.assignments,
          attempts.attempts,
          analyses.analyses,
          artifact_impacts.impacts AS artifact_impacts
        FROM target_learner, consents, assignments, attempts, analyses,
          artifact_impacts, request_insert
      `,
      [actor.tenantId, actor.actorId, learnerId, requestId, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "The actor cannot export this learner.",
      );
    }
    const rawSnapshots =
      typeof row.snapshots === "string"
        ? (JSON.parse(row.snapshots) as ConsentRow[])
        : row.snapshots;
    const rawAttempts =
      typeof row.attempts === "string"
        ? (JSON.parse(row.attempts) as PracticeAttemptExportRecord[])
        : row.attempts;
    const rawAssignments =
      typeof row.assignments === "string"
        ? (JSON.parse(row.assignments) as PracticeAssignmentRow[])
        : row.assignments;
    const rawAnalyses =
      typeof row.analyses === "string"
        ? (JSON.parse(row.analyses) as PracticeAttemptAnalysisExportRecord[])
        : row.analyses;
    const rawArtifactImpacts =
      typeof row.artifact_impacts === "string"
        ? (JSON.parse(row.artifact_impacts) as ResearchArtifactImpactExportRecord[])
        : row.artifact_impacts;
    return {
      requestId: row.request_id,
      learner: {
        id: row.learner_id,
        displayLabel: row.display_label,
        createdAt: timestamp(row.created_at),
        ...(row.deleted_at === null
          ? {}
          : { deletedAt: timestamp(row.deleted_at) }),
      },
      consentSnapshots: rawSnapshots.map(mapConsent),
      practiceAssignments: rawAssignments.map(mapPracticeAssignment),
      practiceAttempts: rawAttempts,
      practiceAttemptAnalyses: rawAnalyses,
      researchArtifactImpacts: rawArtifactImpacts,
    };
  }

  async deleteLearner(
    actor: ActorContext,
    learnerId: string,
  ): Promise<DeletionReceipt> {
    validateActor(actor);
    if (!opaqueIdentifier.test(learnerId)) {
      throw new PlatformDataError(
        "invalid-identifier",
        "Learner identifiers must be opaque tokens.",
      );
    }
    const requestId = randomUUID();
    const auditId = randomUUID();
    const result = await this.#database.query<
      Record<string, unknown> & {
        learner_id: string;
        deleted_at: string | Date;
        request_id: string;
      }
    >(
      `
        WITH authorized AS (
          SELECT 1
          FROM tenant_memberships
          WHERE tenant_id = $1
            AND actor_id = $2
            AND status = 'active'
            AND role = 'owner'
        ), target_learner AS (
          SELECT id, tenant_id
          FROM learners
          WHERE id = $3 AND tenant_id = $1
          FOR UPDATE
        ), updated AS (
          UPDATE learners
          SET display_label = 'Deleted learner',
              deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP)
          WHERE id IN (SELECT id FROM target_learner)
            AND EXISTS (SELECT 1 FROM authorized)
          RETURNING id, tenant_id, deleted_at
        ), deleted_sessions AS (
          DELETE FROM learner_device_sessions
          WHERE tenant_id = $1
            AND learner_id IN (SELECT id FROM updated)
          RETURNING id
        ), deleted_learner_rate_buckets AS (
          DELETE FROM device_access_rate_buckets
          WHERE tenant_id = $1
            AND scope_type = 'learner'
            AND scope_id IN (SELECT id FROM updated)
          RETURNING scope_id
        ), request_insert AS (
          INSERT INTO data_subject_requests (
            id, tenant_id, learner_id, kind, status, requested_by_actor_id,
            completed_at, receipt
          )
          SELECT
            $4, tenant_id, id, 'deletion', 'completed', $2, CURRENT_TIMESTAMP,
            jsonb_build_object(
              'logical_deletion', true,
              'retained_records', jsonb_build_array(
                'consent-snapshots', 'practice-assignments', 'audit-events',
                'artifact-lineage', 'quarantine-evidence'
              )
            )
          FROM updated
          RETURNING id, learner_id
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          )
          SELECT
            $5, $1, $2, 'learner.deletion.completed', 'learner', learner_id,
            jsonb_build_object('request_id', id, 'logical_deletion', true)
          FROM request_insert
        )
        SELECT
          updated.id AS learner_id,
          updated.deleted_at,
          request_insert.id AS request_id
        FROM updated, request_insert
      `,
      [actor.tenantId, actor.actorId, learnerId, requestId, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "Only an active tenant owner can delete this learner.",
      );
    }
    return {
      requestId: row.request_id,
      learnerId: row.learner_id,
      deletedAt: timestamp(row.deleted_at),
      retainedRecords: [
        "consent-snapshots",
        "practice-assignments",
        "audit-events",
        "artifact-lineage",
        "quarantine-evidence",
      ],
    };
  }
}
