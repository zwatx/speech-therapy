import assert from "node:assert/strict";
import test from "node:test";

import { ArtifactRegistryService } from "./artifact-registry.ts";
import { PlatformDataError } from "./errors.ts";
import { applyFoundationMigration } from "./migrate.ts";
import { PGliteDatabase } from "./pglite.ts";
import { PlatformDataService } from "./service.ts";
import type { ActorContext, ConsentSnapshotInput } from "./types.ts";

const owner: ActorContext = { actorId: "actor-owner-a", tenantId: "tenant-a", role: "owner" };
const reviewer: ActorContext = { actorId: "actor-reviewer-a", tenantId: "tenant-a", role: "reviewer" };
const clinician: ActorContext = { actorId: "actor-clinician-a", tenantId: "tenant-a", role: "clinician" };
const foreignOwner: ActorContext = { actorId: "actor-owner-b", tenantId: "tenant-b", role: "owner" };

const researchConsent: ConsentSnapshotInput = {
  learnerId: "learner-a",
  noticeVersion: "research-v1",
  audioProcessing: true,
  videoProcessing: false,
  clinicianReview: true,
  researchUse: true,
  assentStatus: "affirmed",
};

async function databaseFixture(): Promise<PGliteDatabase> {
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
    `INSERT INTO learners (id, tenant_id, display_label) VALUES
      ('learner-a', 'tenant-a', 'Learner A'),
      ('learner-b', 'tenant-b', 'Learner B')`,
  );
  return database;
}

function platformError(code: PlatformDataError["code"]) {
  return (error: unknown): boolean => error instanceof PlatformDataError && error.code === code;
}

async function registerDataset(
  registry: ArtifactRegistryService,
  consentSnapshotId: string,
  artifactId = "dataset-audio-v1",
) {
  return registry.registerDataset(reviewer, {
    artifactId,
    kind: "dataset",
    version: "audio-dataset-v1",
    sha256: "1".repeat(64),
    dependencies: [{
      learnerId: "learner-a",
      consentSnapshotId,
      processingPurpose: "audio-research",
    }],
  });
}

test("dataset registration and use require current purpose-specific research consent", async (t) => {
  const database = await databaseFixture();
  t.after(() => database.close());
  const platform = new PlatformDataService(database);
  const registry = new ArtifactRegistryService(database);
  const consent = await platform.createConsentSnapshot(clinician, researchConsent);

  await assert.rejects(
    registry.registerDataset(clinician, {
      artifactId: "dataset-clinician",
      kind: "dataset",
      version: "v1",
      sha256: "2".repeat(64),
      dependencies: [{ learnerId: "learner-a", consentSnapshotId: consent.id, processingPurpose: "audio-research" }],
    }),
    platformError("access-denied"),
  );
  await assert.rejects(
    registry.registerDataset(foreignOwner, {
      artifactId: "dataset-foreign",
      kind: "dataset",
      version: "v1",
      sha256: "3".repeat(64),
      dependencies: [{ learnerId: "learner-a", consentSnapshotId: consent.id, processingPurpose: "audio-research" }],
    }),
    platformError("access-denied"),
  );
  await assert.rejects(
    registry.registerDataset(reviewer, {
      artifactId: "dataset-visual",
      kind: "dataset",
      version: "v1",
      sha256: "4".repeat(64),
      dependencies: [{ learnerId: "learner-a", consentSnapshotId: consent.id, processingPurpose: "visual-research" }],
    }),
    platformError("access-denied"),
  );

  const dataset = await registerDataset(registry, consent.id);
  assert.equal(dataset.status, "active");
  assert.equal(dataset.dependencyCount, 1);
  assert.equal(dataset.releasePosture, "research-only");
  assert.equal(dataset.learnerFeedbackEligible, false);
  const authorization = await registry.authorizeUse(owner, dataset.id);
  assert.equal(authorization.artifact.id, dataset.id);
  assert.match(authorization.authorizationId, /^[a-f0-9-]{36}$/);

  const useAudit = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM audit_events
     WHERE action = 'artifact.use.authorized' AND resource_id = $1`,
    [dataset.id],
  );
  assert.equal(useAudit.rows[0]?.count, 1);
});

test("derived artifacts inherit consent lineage and supersession quarantines every descendant", async (t) => {
  const database = await databaseFixture();
  t.after(() => database.close());
  const platform = new PlatformDataService(database);
  const registry = new ArtifactRegistryService(database);
  const consent = await platform.createConsentSnapshot(clinician, researchConsent);
  const dataset = await registerDataset(registry, consent.id);
  const features = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "features-audio-v1",
    kind: "feature-cache",
    version: "features-v1",
    sha256: "5".repeat(64),
    parentArtifactIds: [dataset.id],
  });
  const checkpoint = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "checkpoint-audio-v1",
    kind: "checkpoint",
    version: "checkpoint-v1",
    sha256: "6".repeat(64),
    parentArtifactIds: [features.id],
  });
  const deployment = await registry.registerDerivedArtifact(owner, {
    artifactId: "deployment-audio-v1",
    kind: "deployment",
    version: "deployment-v1",
    sha256: "7".repeat(64),
    parentArtifactIds: [checkpoint.id],
  });
  assert.equal(deployment.dependencyCount, 1);
  await registry.authorizeUse(reviewer, deployment.id);
  await assert.rejects(
    database.query(
      `INSERT INTO artifact_lineage_edges (
         tenant_id, parent_artifact_id, child_artifact_id
       ) VALUES ('tenant-a', $1, $2)`,
      [deployment.id, dataset.id],
    ),
    /artifact lineage must be acyclic/,
  );

  await platform.createConsentSnapshot(clinician, {
    ...researchConsent,
    noticeVersion: "research-v2",
  });

  const consentGeneration = await database.query<{ current_consent_version: number }>(
    "SELECT current_consent_version FROM learners WHERE id = 'learner-a'",
  );
  assert.equal(consentGeneration.rows[0]?.current_consent_version, 2);

  const statuses = await database.query<{
    id: string;
    status: string;
    quarantine_reason: string;
  }>(
    `SELECT id, status, quarantine_reason FROM ml_artifacts
     WHERE tenant_id = 'tenant-a' ORDER BY id`,
  );
  assert.deepEqual(statuses.rows, [
    { id: checkpoint.id, status: "quarantined", quarantine_reason: "ancestor-quarantined" },
    { id: dataset.id, status: "quarantined", quarantine_reason: "consent-superseded" },
    { id: deployment.id, status: "quarantined", quarantine_reason: "ancestor-quarantined" },
    { id: features.id, status: "quarantined", quarantine_reason: "ancestor-quarantined" },
  ]);
  const events = await database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM artifact_quarantine_events",
  );
  assert.equal(events.rows[0]?.count, 4);
  await assert.rejects(registry.authorizeUse(owner, deployment.id), platformError("access-denied"));
  await database.query(
    `UPDATE ml_artifacts SET status = 'active', quarantined_at = NULL,
       quarantine_reason = NULL WHERE id = $1`,
    [checkpoint.id],
  );
  await assert.rejects(registry.authorizeUse(owner, checkpoint.id), platformError("access-denied"));
  await assert.rejects(
    registry.registerDerivedArtifact(owner, {
      artifactId: "report-after-quarantine",
      kind: "evaluation-report",
      version: "v1",
      sha256: "8".repeat(64),
      parentArtifactIds: [checkpoint.id],
    }),
    platformError("access-denied"),
  );
});

test("learner deletion quarantines source datasets and all derived artifacts transactionally", async (t) => {
  const database = await databaseFixture();
  t.after(() => database.close());
  const platform = new PlatformDataService(database);
  const registry = new ArtifactRegistryService(database);
  const consent = await platform.createConsentSnapshot(clinician, researchConsent);
  const dataset = await registerDataset(registry, consent.id);
  const report = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "evaluation-audio-v1",
    kind: "evaluation-report",
    version: "evaluation-v1",
    sha256: "9".repeat(64),
    parentArtifactIds: [dataset.id],
  });

  await platform.deleteLearner(owner, "learner-a");

  const rows = await database.query<{ id: string; quarantine_reason: string }>(
    "SELECT id, quarantine_reason FROM ml_artifacts ORDER BY id",
  );
  assert.deepEqual(rows.rows, [
    { id: dataset.id, quarantine_reason: "learner-deleted" },
    { id: report.id, quarantine_reason: "ancestor-quarantined" },
  ]);
  await assert.rejects(registry.authorizeUse(reviewer, report.id), platformError("access-denied"));
});

test("registry rejects malformed, duplicate, stale, and parentless lineage", async (t) => {
  const database = await databaseFixture();
  t.after(() => database.close());
  const platform = new PlatformDataService(database);
  const registry = new ArtifactRegistryService(database);
  const first = await platform.createConsentSnapshot(clinician, researchConsent);
  const latest = await platform.createConsentSnapshot(clinician, { ...researchConsent, noticeVersion: "research-v2" });

  await assert.rejects(registerDataset(registry, first.id), platformError("access-denied"));
  await assert.rejects(
    registry.registerDataset(reviewer, {
      artifactId: "dataset-duplicate-deps",
      kind: "dataset",
      version: "v1",
      sha256: "a".repeat(64),
      dependencies: [
        { learnerId: "learner-a", consentSnapshotId: latest.id, processingPurpose: "audio-research" },
        { learnerId: "learner-a", consentSnapshotId: latest.id, processingPurpose: "audio-research" },
      ],
    }),
    platformError("invalid-artifact"),
  );
  await assert.rejects(
    registry.registerDerivedArtifact(owner, {
      artifactId: "orphan-checkpoint",
      kind: "checkpoint",
      version: "v1",
      sha256: "b".repeat(64),
      parentArtifactIds: [],
    }),
    platformError("invalid-artifact"),
  );
});
