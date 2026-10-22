import { randomUUID } from "node:crypto";

import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ManagedArtifactObjectObservationReceipt,
  ManagedArtifactObjectInspectionClaim,
  ManagedArtifactObjectReconciliationRecord,
  ManagedArtifactObjectRecord,
  ManagedArtifactObjectRegistration,
} from "./types.ts";

const opaqueIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$/;
const providerIdentifier = /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/;
const objectVersion = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;
const sha256 = /^[a-f0-9]{64}$/;
const receiptReference = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$/;

interface BindingRow extends Record<string, unknown> {
  id: string;
  artifact_id: string;
  artifact_kind: ManagedArtifactObjectRecord["artifactKind"];
  artifact_status: ManagedArtifactObjectRecord["artifactStatus"];
  provider_id: string;
  object_reference_sha256: string;
  provider_object_version: string;
  expected_sha256: string;
  registered_at: string | Date;
}

interface ObservationRow extends Record<string, unknown> {
  id: string;
  binding_id: string;
  artifact_id: string;
  artifact_status: ManagedArtifactObjectReconciliationRecord["artifactStatus"];
  object_exists: boolean;
  observed_sha256: string | null;
  access_state: ManagedArtifactObjectReconciliationRecord["accessState"];
  outcome: ManagedArtifactObjectReconciliationRecord["outcome"];
  provider_checked_at: string | Date;
  recorded_at: string | Date;
}

export interface ManagedArtifactObjectAdapter {
  inspect(claim: ManagedArtifactObjectInspectionClaim): Promise<ManagedArtifactObjectObservationReceipt>;
}

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function validateActor(actor: ActorContext): void {
  if (!opaqueIdentifier.test(actor.actorId) || !opaqueIdentifier.test(actor.tenantId)) {
    throw new PlatformDataError("invalid-identifier", "Actor and tenant identifiers must be opaque tokens.");
  }
}

function mapBinding(row: BindingRow): ManagedArtifactObjectRecord {
  return {
    bindingId: row.id,
    artifactId: row.artifact_id,
    artifactKind: row.artifact_kind,
    artifactStatus: row.artifact_status,
    providerId: row.provider_id,
    objectReferenceSha256: row.object_reference_sha256,
    providerObjectVersion: row.provider_object_version,
    expectedSha256: row.expected_sha256,
    registeredAt: timestamp(row.registered_at),
  };
}

function mapObservation(row: ObservationRow): ManagedArtifactObjectReconciliationRecord {
  return {
    observationId: row.id,
    bindingId: row.binding_id,
    artifactId: row.artifact_id,
    artifactStatus: row.artifact_status,
    objectExists: row.object_exists,
    ...(row.observed_sha256 === null ? {} : { observedSha256: row.observed_sha256 }),
    accessState: row.access_state,
    outcome: row.outcome,
    checkedAt: timestamp(row.provider_checked_at),
    recordedAt: timestamp(row.recorded_at),
    evidencePosture: "local-foundation",
    productionGateEligible: false,
  };
}

export class ManagedArtifactObjectService {
  readonly #database: DatabaseClient;
  readonly #now: () => Date;

  constructor(database: DatabaseClient, now: () => Date = () => new Date()) {
    this.#database = database;
    this.#now = now;
  }

  async register(
    actor: ActorContext,
    input: ManagedArtifactObjectRegistration,
  ): Promise<ManagedArtifactObjectRecord> {
    validateActor(actor);
    if (!opaqueIdentifier.test(input.bindingId) || !opaqueIdentifier.test(input.artifactId)) {
      throw new PlatformDataError("invalid-identifier", "Binding and artifact identifiers must be opaque tokens.");
    }
    if (!providerIdentifier.test(input.providerId)
      || !sha256.test(input.objectReferenceSha256)
      || !objectVersion.test(input.providerObjectVersion)) {
      throw new PlatformDataError("invalid-artifact", "Managed object provider metadata is invalid.");
    }
    const auditId = randomUUID();
    const result = await this.#database.query<BindingRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), dependency AS (
        SELECT * FROM artifact_consent_dependencies
        WHERE tenant_id = $1 AND artifact_id = $4
      ), locked_learner AS MATERIALIZED (
        SELECT learner.* FROM learners AS learner
        INNER JOIN (SELECT DISTINCT learner_id FROM dependency) AS subject
          ON subject.learner_id = learner.id
        WHERE learner.tenant_id = $1
        ORDER BY learner.id
        FOR UPDATE OF learner
      ), eligible_artifact AS (
        SELECT artifact.* FROM ml_artifacts AS artifact
        WHERE artifact.tenant_id = $1 AND artifact.id = $4
          AND artifact.status = 'active'
          AND EXISTS (SELECT 1 FROM authorized)
          AND EXISTS (SELECT 1 FROM dependency)
          AND NOT EXISTS (
            SELECT 1 FROM dependency
            LEFT JOIN locked_learner AS learner
              ON learner.id = dependency.learner_id
             AND learner.tenant_id = dependency.tenant_id
            LEFT JOIN consent_snapshots AS consent
              ON consent.id = dependency.consent_snapshot_id
             AND consent.tenant_id = dependency.tenant_id
             AND consent.learner_id = dependency.learner_id
            WHERE learner.id IS NULL OR learner.deleted_at IS NOT NULL
              OR learner.current_consent_version <> consent.version
              OR consent.id IS NULL OR consent.research_use = FALSE
              OR consent.assent_status NOT IN ('affirmed', 'not-applicable')
              OR CASE dependency.processing_purpose
                WHEN 'audio-research' THEN NOT consent.audio_processing
                WHEN 'visual-research' THEN NOT consent.video_processing
                ELSE TRUE
              END
          )
      ), inserted AS (
        INSERT INTO managed_artifact_objects (
          id, tenant_id, artifact_id, provider_id, object_reference_sha256,
          provider_object_version, expected_sha256, registered_by_actor_id
        )
        SELECT $3, $1, artifact.id, $5, $6, $7, artifact.sha256, $2
        FROM eligible_artifact AS artifact
        ON CONFLICT DO NOTHING
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $8, $1, $2, 'artifact.managed-object.registered',
          'managed_artifact_object', id,
          jsonb_build_object(
            'artifact_id', artifact_id,
            'provider_id', provider_id,
            'object_reference_sha256', object_reference_sha256
          )
        FROM inserted RETURNING id
      )
      SELECT inserted.id, inserted.artifact_id, artifact.kind AS artifact_kind,
        artifact.status AS artifact_status, inserted.provider_id,
        inserted.object_reference_sha256, inserted.provider_object_version,
        inserted.expected_sha256, inserted.registered_at,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM inserted
      INNER JOIN ml_artifacts AS artifact
        ON artifact.id = inserted.artifact_id AND artifact.tenant_id = $1
      `,
      [actor.tenantId, actor.actorId, input.bindingId, input.artifactId,
        input.providerId, input.objectReferenceSha256,
        input.providerObjectVersion, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Managed object registration requires an authorized active artifact with current consent.");
    }
    return mapBinding(row);
  }

  async reconcile(
    actor: ActorContext,
    bindingId: string,
    adapter: ManagedArtifactObjectAdapter,
  ): Promise<ManagedArtifactObjectReconciliationRecord> {
    validateActor(actor);
    if (!opaqueIdentifier.test(bindingId)) {
      throw new PlatformDataError("invalid-identifier", "Managed object binding identifiers must be opaque tokens.");
    }
    const bindingResult = await this.#database.query<BindingRow>(
      `
      SELECT binding.id, binding.artifact_id, artifact.kind AS artifact_kind,
        artifact.status AS artifact_status, binding.provider_id,
        binding.object_reference_sha256, binding.provider_object_version,
        binding.expected_sha256, binding.registered_at
      FROM managed_artifact_objects AS binding
      INNER JOIN ml_artifacts AS artifact
        ON artifact.id = binding.artifact_id AND artifact.tenant_id = binding.tenant_id
      WHERE binding.id = $3 AND binding.tenant_id = $1
        AND EXISTS (
          SELECT 1 FROM tenant_memberships
          WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
            AND role IN ('owner', 'reviewer')
        )
      `,
      [actor.tenantId, actor.actorId, bindingId],
    );
    const bindingRow = bindingResult.rows[0];
    if (!bindingRow) {
      throw new PlatformDataError("access-denied", "The managed object binding is unavailable to this actor.");
    }
    const binding = mapBinding(bindingRow);
    const inspectionClaim: ManagedArtifactObjectInspectionClaim = Object.freeze({
      bindingId: binding.bindingId,
      providerId: binding.providerId,
      objectReferenceSha256: binding.objectReferenceSha256,
      providerObjectVersion: binding.providerObjectVersion,
      expectedSha256: binding.expectedSha256,
    });
    const observation = await adapter.inspect(inspectionClaim);
    this.#validateObservation(binding, observation);

    const observationId = randomUUID();
    const auditId = randomUUID();
    const result = await this.#database.query<ObservationRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), current_binding AS (
        SELECT binding.*, artifact.status AS artifact_status
        FROM managed_artifact_objects AS binding
        INNER JOIN ml_artifacts AS artifact
          ON artifact.id = binding.artifact_id AND artifact.tenant_id = binding.tenant_id
        WHERE binding.id = $3 AND binding.tenant_id = $1
          AND EXISTS (SELECT 1 FROM authorized)
      ), inserted AS (
        INSERT INTO managed_artifact_object_observations (
          id, binding_id, tenant_id, artifact_id, artifact_status,
          object_exists, observed_sha256, access_state, outcome,
          provider_checked_at, receipt_reference, receipt_sha256,
          recorded_by_actor_id
        )
        SELECT $4, binding.id, $1, binding.artifact_id, binding.artifact_status,
          $5, $6, $7,
          CASE
            WHEN NOT $5::BOOLEAN THEN 'missing'
            WHEN $6 <> binding.expected_sha256 THEN 'digest-mismatch'
            WHEN binding.artifact_status = 'active' AND $7 <> 'available'
              THEN 'access-mismatch'
            WHEN binding.artifact_status <> 'active' AND $7 <> 'revoked'
              THEN 'access-mismatch'
            ELSE 'consistent'
          END,
          $8, $9, $10, $2
        FROM current_binding AS binding
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $11, $1, $2, 'artifact.managed-object.reconciled',
          'managed_artifact_object', binding_id,
          jsonb_build_object(
            'observation_id', id,
            'artifact_id', artifact_id,
            'artifact_status', artifact_status,
            'outcome', outcome
          )
        FROM inserted RETURNING id
      )
      SELECT inserted.*, (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM inserted
      `,
      [actor.tenantId, actor.actorId, bindingId, observationId,
        observation.objectExists, observation.observedSha256 ?? null,
        observation.accessState, observation.checkedAt,
        observation.receiptReference, observation.receiptSha256, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The managed object reconciliation lost authorization.");
    }
    return mapObservation(row);
  }

  #validateObservation(
    binding: ManagedArtifactObjectRecord,
    observation: ManagedArtifactObjectObservationReceipt,
  ): void {
    const checkedAt = new Date(observation.checkedAt);
    const now = this.#now().getTime();
    const shapeValid = observation.bindingId === binding.bindingId
      && observation.providerId === binding.providerId
      && observation.objectReferenceSha256 === binding.objectReferenceSha256
      && typeof observation.objectExists === "boolean"
      && receiptReference.test(observation.receiptReference)
      && sha256.test(observation.receiptSha256)
      && Number.isFinite(checkedAt.getTime())
      && checkedAt.toISOString() === observation.checkedAt
      && checkedAt.getTime() >= now - 900_000
      && checkedAt.getTime() <= now + 60_000;
    const objectShapeValid = observation.objectExists
      ? observation.observedSha256 !== undefined
        && sha256.test(observation.observedSha256)
        && ["available", "revoked"].includes(observation.accessState)
      : observation.observedSha256 === undefined
        && observation.accessState === "unavailable";
    if (!shapeValid || !objectShapeValid) {
      throw new PlatformDataError("invalid-artifact", "The managed object observation failed verification.");
    }
  }
}
