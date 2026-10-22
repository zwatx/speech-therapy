import { randomUUID } from "node:crypto";

import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ArtifactRecord,
  ArtifactUseAuthorization,
  DerivedArtifactRegistration,
  DatasetArtifactRegistration,
} from "./types.ts";

const opaqueIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/;
const versionPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const sha256Pattern = /^[a-f0-9]{64}$/;

interface ArtifactRow extends Record<string, unknown> {
  id: string;
  tenant_id: string;
  kind: ArtifactRecord["kind"];
  version: string;
  sha256: string;
  status: ArtifactRecord["status"];
  release_posture: "research-only";
  learner_feedback_eligible: false;
  created_at: string | Date;
  quarantined_at: string | Date | null;
  quarantine_reason:
    | "consent-superseded"
    | "learner-deleted"
    | "ancestor-quarantined"
    | null;
  dependency_count: number;
}

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function validateActor(actor: ActorContext): void {
  if (!opaqueIdentifier.test(actor.actorId) || !opaqueIdentifier.test(actor.tenantId)) {
    throw new PlatformDataError("invalid-identifier", "Actor and tenant identifiers must be opaque tokens.");
  }
}

function validateArtifactIdentity(input: {
  readonly artifactId: string;
  readonly version: string;
  readonly sha256: string;
}): void {
  if (!opaqueIdentifier.test(input.artifactId)) {
    throw new PlatformDataError("invalid-identifier", "Artifact identifiers must be opaque tokens.");
  }
  if (!versionPattern.test(input.version) || !sha256Pattern.test(input.sha256)) {
    throw new PlatformDataError("invalid-artifact", "Artifact version and SHA-256 provenance are required.");
  }
}

function uniqueValues(values: readonly string[], label: string): void {
  if (values.length === 0 || new Set(values).size !== values.length) {
    throw new PlatformDataError("invalid-artifact", `${label} must be non-empty and unique.`);
  }
  if (values.some((value) => !opaqueIdentifier.test(value))) {
    throw new PlatformDataError("invalid-identifier", `${label} must contain opaque tokens.`);
  }
}

function mapArtifact(row: ArtifactRow): ArtifactRecord {
  const quarantineReason = row.quarantine_reason;
  return {
    id: row.id,
    tenantId: row.tenant_id,
    kind: row.kind,
    version: row.version,
    sha256: row.sha256,
    status: row.status,
    releasePosture: row.release_posture,
    learnerFeedbackEligible: row.learner_feedback_eligible,
    createdAt: timestamp(row.created_at),
    dependencyCount: Number(row.dependency_count),
    ...(row.quarantined_at === null ? {} : { quarantinedAt: timestamp(row.quarantined_at) }),
    ...(quarantineReason === null ? {} : { quarantineReason }),
  };
}

export class ArtifactRegistryService {
  readonly #database: DatabaseClient;

  constructor(database: DatabaseClient) {
    this.#database = database;
  }

  async registerDataset(
    actor: ActorContext,
    input: DatasetArtifactRegistration,
  ): Promise<ArtifactRecord> {
    validateActor(actor);
    validateArtifactIdentity(input);
    if (input.dependencies.length === 0) {
      throw new PlatformDataError("invalid-artifact", "A dataset must identify every consent dependency.");
    }
    const dependencyKeys = input.dependencies.map(
      (dependency) => `${dependency.learnerId}\0${dependency.processingPurpose}`,
    );
    if (new Set(dependencyKeys).size !== dependencyKeys.length) {
      throw new PlatformDataError("invalid-artifact", "Dataset consent dependencies must be unique per learner and purpose.");
    }
    for (const dependency of input.dependencies) {
      if (!opaqueIdentifier.test(dependency.learnerId) || !opaqueIdentifier.test(dependency.consentSnapshotId)) {
        throw new PlatformDataError("invalid-identifier", "Consent dependencies must contain opaque tokens.");
      }
      if (!["audio-research", "visual-research"].includes(dependency.processingPurpose)) {
        throw new PlatformDataError("invalid-artifact", "Dataset processing purpose is unsupported.");
      }
    }

    const artifactId = input.artifactId;
    const auditId = randomUUID();
    const dependenciesJson = JSON.stringify(input.dependencies);
    const result = await this.#database.query<ArtifactRow>(
      `
      WITH requested AS (
        SELECT *
        FROM jsonb_to_recordset($7::jsonb) AS dependency(
          "learnerId" TEXT, "consentSnapshotId" TEXT, "processingPurpose" TEXT
        )
      ), authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), locked_learner AS MATERIALIZED (
        SELECT learner.id, learner.tenant_id, learner.deleted_at,
          learner.current_consent_version
        FROM learners AS learner
        INNER JOIN requested ON requested."learnerId" = learner.id
        WHERE learner.tenant_id = $1
        ORDER BY learner.id
        FOR UPDATE OF learner
      ), eligible AS (
        SELECT requested.*
        FROM requested
        INNER JOIN locked_learner AS learner
          ON learner.id = requested."learnerId"
         AND learner.tenant_id = $1
         AND learner.deleted_at IS NULL
        INNER JOIN consent_snapshots AS consent
          ON consent.id = requested."consentSnapshotId"
         AND consent.tenant_id = $1
         AND consent.learner_id = learner.id
        WHERE consent.research_use = TRUE
          AND learner.deleted_at IS NULL
          AND learner.current_consent_version = consent.version
          AND consent.assent_status IN ('affirmed', 'not-applicable')
          AND CASE requested."processingPurpose"
            WHEN 'audio-research' THEN consent.audio_processing
            WHEN 'visual-research' THEN consent.video_processing
            ELSE FALSE
          END
      ), inserted AS (
        INSERT INTO ml_artifacts (
          id, tenant_id, kind, version, sha256, release_posture,
          learner_feedback_eligible, created_by_actor_id
        )
        SELECT $3, $1, 'dataset', $4, $5, 'research-only', FALSE, $2
        WHERE EXISTS (SELECT 1 FROM authorized)
          AND (SELECT COUNT(*) FROM eligible) = $8
          AND (SELECT COUNT(*) FROM requested) = $8
        RETURNING *
      ), dependencies AS (
        INSERT INTO artifact_consent_dependencies (
          artifact_id, tenant_id, learner_id, consent_snapshot_id, processing_purpose
        )
        SELECT $3, $1, "learnerId", "consentSnapshotId", "processingPurpose"
        FROM eligible WHERE EXISTS (SELECT 1 FROM inserted)
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $6, $1, $2, 'artifact.dataset.registered', 'ml_artifact', id,
          jsonb_build_object('sha256', sha256, 'dependency_count', $8)
        FROM inserted
      )
      SELECT inserted.*, $8::INTEGER AS dependency_count
      FROM inserted
      `,
      [actor.tenantId, actor.actorId, artifactId, input.version, input.sha256, auditId, dependenciesJson, input.dependencies.length],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Dataset registration requires authorized, current research consent.");
    }
    return mapArtifact(row);
  }

  async registerDerivedArtifact(
    actor: ActorContext,
    input: DerivedArtifactRegistration,
  ): Promise<ArtifactRecord> {
    validateActor(actor);
    validateArtifactIdentity(input);
    if (!["feature-cache", "checkpoint", "calibration", "evaluation-report", "deployment"].includes(input.kind)) {
      throw new PlatformDataError("invalid-artifact", "Derived artifact kind is unsupported.");
    }
    uniqueValues(input.parentArtifactIds, "Parent artifact identifiers");
    const auditId = randomUUID();
    const result = await this.#database.query<ArtifactRow>(
      `
      WITH requested_parent AS (
        SELECT jsonb_array_elements_text($8::jsonb) AS id
      ), authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), requested_dependency AS (
        SELECT dependency.*
        FROM artifact_consent_dependencies AS dependency
        INNER JOIN requested_parent ON requested_parent.id = dependency.artifact_id
        WHERE dependency.tenant_id = $1
      ), locked_learner AS MATERIALIZED (
        SELECT learner.id, learner.tenant_id, learner.deleted_at,
          learner.current_consent_version
        FROM learners AS learner
        INNER JOIN (
          SELECT DISTINCT learner_id FROM requested_dependency
        ) AS dependency ON dependency.learner_id = learner.id
        WHERE learner.tenant_id = $1
        ORDER BY learner.id
        FOR UPDATE OF learner
      ), valid_parent AS (
        SELECT artifact.id
        FROM ml_artifacts AS artifact
        INNER JOIN requested_parent ON requested_parent.id = artifact.id
        WHERE artifact.tenant_id = $1 AND artifact.status = 'active'
          AND EXISTS (
            SELECT 1 FROM artifact_consent_dependencies AS dependency
            WHERE dependency.artifact_id = artifact.id
              AND dependency.tenant_id = artifact.tenant_id
          )
          AND NOT EXISTS (
            SELECT 1
            FROM artifact_consent_dependencies AS dependency
            LEFT JOIN locked_learner AS learner
              ON learner.id = dependency.learner_id
             AND learner.tenant_id = dependency.tenant_id
            LEFT JOIN consent_snapshots AS consent
              ON consent.id = dependency.consent_snapshot_id
             AND consent.tenant_id = dependency.tenant_id
             AND consent.learner_id = dependency.learner_id
            WHERE dependency.artifact_id = artifact.id
              AND dependency.tenant_id = artifact.tenant_id
              AND (
                learner.id IS NULL OR learner.deleted_at IS NOT NULL
                OR learner.current_consent_version <> consent.version
                OR consent.id IS NULL OR consent.research_use = FALSE
                OR consent.assent_status NOT IN ('affirmed', 'not-applicable')
                OR CASE dependency.processing_purpose
                  WHEN 'audio-research' THEN NOT consent.audio_processing
                  WHEN 'visual-research' THEN NOT consent.video_processing
                  ELSE TRUE
                END
              )
          )
      ), inserted AS (
        INSERT INTO ml_artifacts (
          id, tenant_id, kind, version, sha256, release_posture,
          learner_feedback_eligible, created_by_actor_id
        )
        SELECT $3, $1, $4, $5, $6, 'research-only', FALSE, $2
        WHERE EXISTS (SELECT 1 FROM authorized)
          AND (SELECT COUNT(*) FROM valid_parent) = $9
          AND (SELECT COUNT(*) FROM requested_parent) = $9
        RETURNING *
      ), edges AS (
        INSERT INTO artifact_lineage_edges (
          tenant_id, parent_artifact_id, child_artifact_id
        )
        SELECT $1, valid_parent.id, $3
        FROM valid_parent WHERE EXISTS (SELECT 1 FROM inserted)
      ), dependencies AS (
        INSERT INTO artifact_consent_dependencies (
          artifact_id, tenant_id, learner_id, consent_snapshot_id, processing_purpose
        )
        SELECT DISTINCT $3, dependency.tenant_id, dependency.learner_id,
          dependency.consent_snapshot_id, dependency.processing_purpose
        FROM artifact_consent_dependencies AS dependency
        INNER JOIN valid_parent ON valid_parent.id = dependency.artifact_id
        WHERE EXISTS (SELECT 1 FROM inserted)
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $7, $1, $2, 'artifact.derived.registered', 'ml_artifact', id,
          jsonb_build_object('kind', kind, 'parent_count', $9)
        FROM inserted
      )
      SELECT inserted.*, (
        SELECT COUNT(DISTINCT dependency.learner_id || ':' || dependency.processing_purpose)::INTEGER
        FROM artifact_consent_dependencies AS dependency
        INNER JOIN valid_parent ON valid_parent.id = dependency.artifact_id
      ) AS dependency_count
      FROM inserted
      `,
      [actor.tenantId, actor.actorId, input.artifactId, input.kind, input.version, input.sha256, auditId, JSON.stringify(input.parentArtifactIds), input.parentArtifactIds.length],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Derived artifacts require authorized active parent artifacts.");
    }
    return mapArtifact(row);
  }

  async authorizeUse(actor: ActorContext, artifactId: string): Promise<ArtifactUseAuthorization> {
    validateActor(actor);
    if (!opaqueIdentifier.test(artifactId)) {
      throw new PlatformDataError("invalid-identifier", "Artifact identifiers must be opaque tokens.");
    }
    const authorizationId = randomUUID();
    const auditId = randomUUID();
    const result = await this.#database.query<ArtifactRow & { authorized_at: string | Date; authorization_id: string }>(
      `
      WITH authorized_actor AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), eligible_artifact AS (
        SELECT artifact.*
        FROM ml_artifacts AS artifact
        WHERE artifact.id = $3 AND artifact.tenant_id = $1
          AND artifact.status = 'active'
          AND EXISTS (SELECT 1 FROM authorized_actor)
          AND EXISTS (
            SELECT 1 FROM artifact_consent_dependencies AS dependency
            WHERE dependency.artifact_id = artifact.id
              AND dependency.tenant_id = artifact.tenant_id
          )
          AND NOT EXISTS (
            SELECT 1
            FROM artifact_consent_dependencies AS dependency
            LEFT JOIN learners AS learner
              ON learner.id = dependency.learner_id
             AND learner.tenant_id = dependency.tenant_id
            LEFT JOIN consent_snapshots AS consent
              ON consent.id = dependency.consent_snapshot_id
             AND consent.tenant_id = dependency.tenant_id
             AND consent.learner_id = dependency.learner_id
            WHERE dependency.artifact_id = artifact.id
              AND dependency.tenant_id = artifact.tenant_id
              AND (
                learner.id IS NULL OR learner.deleted_at IS NOT NULL
                OR learner.current_consent_version <> consent.version
                OR consent.id IS NULL OR consent.research_use = FALSE
                OR consent.assent_status NOT IN ('affirmed', 'not-applicable')
                OR CASE dependency.processing_purpose
                  WHEN 'audio-research' THEN NOT consent.audio_processing
                  WHEN 'visual-research' THEN NOT consent.video_processing
                  ELSE TRUE
                END
              )
          )
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $5, $1, $2, 'artifact.use.authorized', 'ml_artifact', id,
          jsonb_build_object('authorization_id', $4::TEXT)
        FROM eligible_artifact
      )
      SELECT eligible_artifact.*, CURRENT_TIMESTAMP AS authorized_at,
        $4::TEXT AS authorization_id,
        (SELECT COUNT(*)::INTEGER FROM artifact_consent_dependencies
         WHERE artifact_id = eligible_artifact.id AND tenant_id = $1) AS dependency_count
      FROM eligible_artifact
      `,
      [actor.tenantId, actor.actorId, artifactId, authorizationId, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Artifact use requires active lineage and current research consent.");
    }
    return {
      authorizationId: row.authorization_id,
      authorizedAt: timestamp(row.authorized_at),
      artifact: mapArtifact(row),
    };
  }
}
