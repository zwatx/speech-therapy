import assert from "node:assert/strict";
import test from "node:test";

import { ArtifactRegistryService } from "./artifact-registry.ts";
import { PlatformDataError } from "./errors.ts";
import {
  ManagedArtifactObjectService,
  type ManagedArtifactObjectAdapter,
} from "./managed-artifact-objects.ts";
import { applyFoundationMigration } from "./migrate.ts";
import { PGliteDatabase } from "./pglite.ts";
import { PlatformDataService } from "./service.ts";
import type {
  ActorContext,
  ManagedArtifactObjectObservationReceipt,
  ManagedArtifactObjectInspectionClaim,
} from "./types.ts";

const ownerA: ActorContext = { actorId: "actor-owner-a", tenantId: "tenant-a", role: "owner" };
const reviewerA: ActorContext = { actorId: "actor-reviewer-a", tenantId: "tenant-a", role: "reviewer" };
const clinicianA: ActorContext = { actorId: "actor-clinician-a", tenantId: "tenant-a", role: "clinician" };
const ownerB: ActorContext = { actorId: "actor-owner-b", tenantId: "tenant-b", role: "owner" };

async function fixture() {
  const database = new PGliteDatabase();
  await applyFoundationMigration(database);
  await database.query(
    `INSERT INTO tenants (id, display_name, external_organization_hash) VALUES
      ('tenant-a', 'Clinic A', $1), ('tenant-b', 'Clinic B', $2)`,
    ["a".repeat(64), "b".repeat(64)],
  );
  await database.query(
    `INSERT INTO actors (id, external_subject_hash) VALUES
      ('actor-owner-a', $1), ('actor-reviewer-a', $2),
      ('actor-clinician-a', $3), ('actor-owner-b', $4)`,
    ["c".repeat(64), "d".repeat(64), "e".repeat(64), "f".repeat(64)],
  );
  await database.query(
    `INSERT INTO tenant_memberships (tenant_id, actor_id, role) VALUES
      ('tenant-a', 'actor-owner-a', 'owner'),
      ('tenant-a', 'actor-reviewer-a', 'reviewer'),
      ('tenant-a', 'actor-clinician-a', 'clinician'),
      ('tenant-b', 'actor-owner-b', 'owner')`,
  );
  await database.query(
    "INSERT INTO learners (id, tenant_id, display_label) VALUES ('learner-a', 'tenant-a', 'Learner A')",
  );
  const platform = new PlatformDataService(database);
  const consent = await platform.createConsentSnapshot(clinicianA, {
    learnerId: "learner-a",
    noticeVersion: "research-v1",
    audioProcessing: true,
    videoProcessing: false,
    clinicianReview: true,
    researchUse: true,
    assentStatus: "affirmed",
  });
  const artifact = await new ArtifactRegistryService(database).registerDataset(reviewerA, {
    artifactId: "dataset-managed-v1",
    kind: "dataset",
    version: "dataset-v1",
    sha256: "1".repeat(64),
    dependencies: [{
      learnerId: "learner-a",
      consentSnapshotId: consent.id,
      processingPurpose: "audio-research",
    }],
  });
  const service = new ManagedArtifactObjectService(
    database,
    () => new Date("2026-07-10T22:00:30.000Z"),
  );
  return { database, platform, artifact, service };
}

function observation(
  binding: ManagedArtifactObjectInspectionClaim,
  overrides: Partial<ManagedArtifactObjectObservationReceipt> = {},
): ManagedArtifactObjectObservationReceipt {
  return {
    bindingId: binding.bindingId,
    providerId: binding.providerId,
    objectReferenceSha256: binding.objectReferenceSha256,
    objectExists: true,
    observedSha256: binding.expectedSha256,
    accessState: "available",
    checkedAt: "2026-07-10T22:00:00.000Z",
    receiptReference: `receipt/${binding.bindingId}`,
    receiptSha256: "2".repeat(64),
    ...overrides,
  };
}

function adapter(
  create: (binding: ManagedArtifactObjectInspectionClaim) => ManagedArtifactObjectObservationReceipt,
): ManagedArtifactObjectAdapter {
  return { inspect: async (binding) => create(binding) };
}

test("managed object registration is tenant-scoped, consent-bound, and stores no locator", async (t) => {
  const { database, artifact, service } = await fixture();
  t.after(() => database.close());
  const input = {
    bindingId: "binding-managed-v1",
    artifactId: artifact.id,
    providerId: "provider-test",
    objectReferenceSha256: "3".repeat(64),
    providerObjectVersion: "version:immutable-v1",
  } as const;

  await assert.rejects(
    service.register(clinicianA, input),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    service.register(ownerB, input),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const binding = await service.register(ownerA, input);
  assert.equal(binding.expectedSha256, artifact.sha256);
  assert.equal(binding.artifactStatus, "active");
  assert.equal(binding.objectReferenceSha256, input.objectReferenceSha256);
  assert.doesNotMatch(JSON.stringify(binding), /url|uri|bucket|path/i);
  const columns = await database.query<{ column_name: string }>(
    `SELECT column_name FROM information_schema.columns
     WHERE table_name = 'managed_artifact_objects' ORDER BY column_name`,
  );
  assert.ok(columns.rows.some((row) => row.column_name === "object_reference_sha256"));
  assert.ok(columns.rows.every((row) => !/url|uri|bucket|path/i.test(row.column_name)));
});

test("reconciliation detects digest, access, missing-object, and quarantine state", async (t) => {
  const { database, platform, artifact, service } = await fixture();
  t.after(() => database.close());
  const binding = await service.register(reviewerA, {
    bindingId: "binding-managed-v1",
    artifactId: artifact.id,
    providerId: "provider-test",
    objectReferenceSha256: "3".repeat(64),
    providerObjectVersion: "version:immutable-v1",
  });

  let adapterClaim: ManagedArtifactObjectInspectionClaim | undefined;
  const consistent = await service.reconcile(ownerA, binding.bindingId, adapter((current) => {
    adapterClaim = current;
    return observation(current);
  }));
  assert.equal(consistent.outcome, "consistent");
  assert.equal(consistent.productionGateEligible, false);
  assert.deepEqual(Object.keys(adapterClaim ?? {}).sort(), [
    "bindingId",
    "expectedSha256",
    "objectReferenceSha256",
    "providerId",
    "providerObjectVersion",
  ]);
  assert.doesNotMatch(
    JSON.stringify(adapterClaim),
    /artifactId|artifactKind|artifactStatus|registeredAt|tenantId/,
  );

  const mismatch = await service.reconcile(reviewerA, binding.bindingId, adapter(
    (current) => observation(current, { observedSha256: "4".repeat(64) }),
  ));
  assert.equal(mismatch.outcome, "digest-mismatch");

  await assert.rejects(
    service.reconcile(ownerA, binding.bindingId, adapter((current) =>
      observation(current, { providerId: "provider-other" })
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  for (const checkedAt of ["2026-07-10T21:40:00.000Z", "2026-07-10T22:02:00.000Z"]) {
    await assert.rejects(
      service.reconcile(ownerA, binding.bindingId, adapter((current) =>
        observation(current, { checkedAt })
      )),
      (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
    );
  }

  await platform.deleteLearner(ownerA, "learner-a");
  const accessMismatch = await service.reconcile(ownerA, binding.bindingId, adapter(
    (current) => observation(current),
  ));
  assert.equal(accessMismatch.artifactStatus, "quarantined");
  assert.equal(accessMismatch.outcome, "access-mismatch");
  const revoked = await service.reconcile(ownerA, binding.bindingId, adapter(
    (current) => observation(current, { accessState: "revoked" }),
  ));
  assert.equal(revoked.outcome, "consistent");
  const missing = await service.reconcile(ownerA, binding.bindingId, adapter(
    (current) => ({
      bindingId: current.bindingId,
      providerId: current.providerId,
      objectReferenceSha256: current.objectReferenceSha256,
      objectExists: false,
      accessState: "unavailable",
      checkedAt: "2026-07-10T22:00:00.000Z",
      receiptReference: `receipt/${current.bindingId}/missing`,
      receiptSha256: "5".repeat(64),
    }),
  ));
  assert.equal(missing.outcome, "missing");

  const evidence = await database.query<{ outcome: string; count: number }>(
    `SELECT outcome, COUNT(*)::INTEGER AS count
     FROM managed_artifact_object_observations GROUP BY outcome ORDER BY outcome`,
  );
  assert.deepEqual(evidence.rows, [
    { outcome: "access-mismatch", count: 1 },
    { outcome: "consistent", count: 2 },
    { outcome: "digest-mismatch", count: 1 },
    { outcome: "missing", count: 1 },
  ]);
  await assert.rejects(
    database.query("UPDATE managed_artifact_object_observations SET outcome = 'consistent'"),
    /append-only/,
  );
  await assert.rejects(
    database.query("DELETE FROM managed_artifact_objects"),
    /append-only/,
  );
  await assert.rejects(
    service.reconcile(ownerB, binding.bindingId, adapter((current) => observation(current))),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});
