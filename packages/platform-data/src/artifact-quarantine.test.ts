import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import test from "node:test";

import {
  ArtifactQuarantineAdapterError,
  ArtifactQuarantineReconciler,
  ArtifactQuarantineService,
  canonicalArtifactQuarantineReceiptPayload,
  Ed25519ArtifactQuarantineReceiptVerifier,
  VerifyingArtifactQuarantineAdapter,
} from "./artifact-quarantine.ts";
import { ArtifactReceiptSigningKeyService } from "./artifact-receipt-keys.ts";
import { ArtifactOperationsService } from "./artifact-operations.ts";
import { ArtifactRegistryService } from "./artifact-registry.ts";
import { PlatformDataError } from "./errors.ts";
import { applyFoundationMigration } from "./migrate.ts";
import { PGliteDatabase } from "./pglite.ts";
import { PlatformDataService } from "./service.ts";
import type {
  ActorContext,
  ArtifactQuarantineActionClaim,
  ArtifactQuarantineActionReceipt,
  SignedArtifactQuarantineActionReceipt,
} from "./types.ts";

const owner: ActorContext = { actorId: "actor-owner-a", tenantId: "tenant-a", role: "owner" };
const reviewer: ActorContext = { actorId: "actor-reviewer-a", tenantId: "tenant-a", role: "reviewer" };
const clinician: ActorContext = { actorId: "actor-clinician-a", tenantId: "tenant-a", role: "clinician" };

async function fixture() {
  const database = new PGliteDatabase();
  await applyFoundationMigration(database);
  await database.query(
    "INSERT INTO tenants (id, display_name, external_organization_hash) VALUES ('tenant-a', 'Clinic A', $1)",
    ["a".repeat(64)],
  );
  await database.query(
    `INSERT INTO actors (id, external_subject_hash) VALUES
      ('actor-owner-a', $1), ('actor-reviewer-a', $2), ('actor-clinician-a', $3)`,
    ["b".repeat(64), "c".repeat(64), "d".repeat(64)],
  );
  await database.query(
    `INSERT INTO tenant_memberships (tenant_id, actor_id, role) VALUES
      ('tenant-a', 'actor-owner-a', 'owner'),
      ('tenant-a', 'actor-reviewer-a', 'reviewer'),
      ('tenant-a', 'actor-clinician-a', 'clinician')`,
  );
  await database.query(
    `INSERT INTO learners (id, tenant_id, display_label) VALUES
      ('learner-a', 'tenant-a', 'Learner A'),
      ('learner-c', 'tenant-a', 'Learner C')`,
  );
  const platform = new PlatformDataService(database);
  const registry = new ArtifactRegistryService(database);
  const consent = await platform.createConsentSnapshot(clinician, {
    learnerId: "learner-a",
    noticeVersion: "research-v1",
    audioProcessing: true,
    videoProcessing: false,
    clinicianReview: true,
    researchUse: true,
    assentStatus: "affirmed",
  });
  const consentC = await platform.createConsentSnapshot(clinician, {
    learnerId: "learner-c",
    noticeVersion: "research-v1",
    audioProcessing: true,
    videoProcessing: false,
    clinicianReview: true,
    researchUse: true,
    assentStatus: "affirmed",
  });
  const dataset = await registry.registerDataset(reviewer, {
    artifactId: "dataset-audio-v1",
    kind: "dataset",
    version: "dataset-v1",
    sha256: "1".repeat(64),
    dependencies: [{
      learnerId: "learner-a",
      consentSnapshotId: consent.id,
      processingPurpose: "audio-research",
    }, {
      learnerId: "learner-c",
      consentSnapshotId: consentC.id,
      processingPurpose: "audio-research",
    }],
  });
  return { database, platform, registry, dataset };
}

async function quarantineDatasetOnly() {
  const context = await fixture();
  const deletionReceipt = await context.platform.deleteLearner(owner, "learner-a");
  return { ...context, deletionReceipt };
}

function receipt(action: ArtifactQuarantineActionClaim, outcome: ArtifactQuarantineActionReceipt["outcome"] = "performed") {
  return {
    actionId: action.actionId,
    idempotencyKey: action.idempotencyKey,
    artifactSha256: action.artifactSha256,
    actionType: action.actionType,
    receiptReference: `receipt/${action.actionId}`,
    receiptSha256: "e".repeat(64),
    outcome,
  } as const;
}

function signedReceipt(
  action: ArtifactQuarantineActionClaim,
  privateKey: ReturnType<typeof generateKeyPairSync>["privateKey"],
  issuedAt = "2026-07-10T22:00:00.000Z",
): SignedArtifactQuarantineActionReceipt {
  const unsigned = receipt(action);
  const envelope = {
    schemaVersion: "artifact-quarantine-receipt-signature-v1",
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    algorithm: "Ed25519",
    issuedAt,
  } as const;
  const signature = sign(
    null,
    Buffer.from(canonicalArtifactQuarantineReceiptPayload(unsigned, envelope), "utf8"),
    privateKey,
  ).toString("base64url");
  return { ...unsigned, signatureEnvelope: { ...envelope, signature } };
}

test("quarantine creates the complete kind-specific action outbox transactionally", async (t) => {
  const { database, platform, registry, dataset } = await fixture();
  t.after(() => database.close());
  const features = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "features-audio-v1", kind: "feature-cache", version: "v1",
    sha256: "2".repeat(64), parentArtifactIds: [dataset.id],
  });
  const checkpoint = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "checkpoint-audio-v1", kind: "checkpoint", version: "v1",
    sha256: "3".repeat(64), parentArtifactIds: [features.id],
  });
  const calibration = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "calibration-audio-v1", kind: "calibration", version: "v1",
    sha256: "6".repeat(64), parentArtifactIds: [checkpoint.id],
  });
  const evaluation = await registry.registerDerivedArtifact(reviewer, {
    artifactId: "evaluation-audio-v1", kind: "evaluation-report", version: "v1",
    sha256: "4".repeat(64), parentArtifactIds: [calibration.id],
  });
  const deployment = await registry.registerDerivedArtifact(owner, {
    artifactId: "deployment-audio-v1", kind: "deployment", version: "v1",
    sha256: "5".repeat(64), parentArtifactIds: [evaluation.id],
  });

  await platform.deleteLearner(owner, "learner-a");

  const actions = await database.query<{ artifact_id: string; action_type: string; status: string }>(
    `SELECT artifact_id, action_type, status FROM artifact_quarantine_actions
     ORDER BY artifact_id, action_type`,
  );
  assert.deepEqual(actions.rows, [
    { artifact_id: calibration.id, action_type: "revoke-artifact-access", status: "pending" },
    { artifact_id: calibration.id, action_type: "schedule-retraining", status: "pending" },
    { artifact_id: checkpoint.id, action_type: "revoke-artifact-access", status: "pending" },
    { artifact_id: checkpoint.id, action_type: "schedule-retraining", status: "pending" },
    { artifact_id: dataset.id, action_type: "purge-subject-data", status: "pending" },
    { artifact_id: dataset.id, action_type: "revoke-artifact-access", status: "pending" },
    { artifact_id: deployment.id, action_type: "disable-deployment", status: "pending" },
    { artifact_id: deployment.id, action_type: "revoke-artifact-access", status: "pending" },
    { artifact_id: evaluation.id, action_type: "revoke-artifact-access", status: "pending" },
    { artifact_id: evaluation.id, action_type: "schedule-reevaluation", status: "pending" },
    { artifact_id: features.id, action_type: "purge-feature-cache", status: "pending" },
    { artifact_id: features.id, action_type: "revoke-artifact-access", status: "pending" },
  ]);
});

test("a later withdrawal creates new subject-specific actions for an already quarantined dataset", async (t) => {
  const { database, platform } = await quarantineDatasetOnly();
  t.after(() => database.close());

  await platform.createConsentSnapshot(clinician, {
    learnerId: "learner-c",
    noticeVersion: "research-v2",
    audioProcessing: false,
    videoProcessing: false,
    clinicianReview: false,
    researchUse: false,
    assentStatus: "withdrawn",
  });

  const actions = await database.query<{ source_learner_id: string; count: number }>(
    `SELECT source_learner_id, COUNT(*)::INTEGER AS count
     FROM artifact_quarantine_actions
     GROUP BY source_learner_id ORDER BY source_learner_id`,
  );
  assert.deepEqual(actions.rows, [
    { source_learner_id: "learner-a", count: 2 },
    { source_learner_id: "learner-c", count: 2 },
  ]);
});

test("the reconciler drains actions with stable idempotency keys and verified receipts", async (t) => {
  const { database } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const seen: ArtifactQuarantineActionClaim[] = [];
  const service = new ArtifactQuarantineService(database);
  const reconciler = new ArtifactQuarantineReconciler(service, {
    execute: async (action) => {
      seen.push(action);
      return receipt(action);
    },
  });

  assert.equal((await reconciler.runOnce("worker-alpha")).status, "succeeded");
  assert.equal((await reconciler.runOnce("worker-alpha")).status, "succeeded");
  assert.deepEqual(await reconciler.runOnce("worker-alpha"), { status: "idle" });
  assert.equal(new Set(seen.map((action) => action.idempotencyKey)).size, 2);
  assert.ok(seen.every((action) => action.sourceLearnerId === "learner-a"));

  const state = await database.query<{ succeeded: number; event_count: number }>(
    `SELECT
      (SELECT COUNT(*)::INTEGER FROM artifact_quarantine_actions WHERE status = 'succeeded') AS succeeded,
      (SELECT COUNT(*)::INTEGER FROM artifact_quarantine_action_events) AS event_count`,
  );
  assert.deepEqual(state.rows[0], { succeeded: 2, event_count: 4 });
  await assert.rejects(
    database.query("UPDATE artifact_quarantine_action_events SET worker_id = 'worker-beta'"),
    /append-only/,
  );
  await assert.rejects(
    database.query("UPDATE artifact_quarantine_actions SET artifact_id = 'wrong-artifact'"),
    /identity is immutable/,
  );
});

test("retries preserve idempotency and expired leases reject stale acknowledgements", async (t) => {
  const { database } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const service = new ArtifactQuarantineService(database);
  const first = await service.claimNext("worker-alpha", 5);
  assert.ok(first);
  const disposition = await service.recordFailure(
    "worker-alpha", first, "external-unavailable", true,
  );
  assert.equal(disposition, "retry-scheduled");
  await database.query(
    `UPDATE artifact_quarantine_actions
     SET available_at = CASE WHEN id = $1 THEN CURRENT_TIMESTAMP
       ELSE CURRENT_TIMESTAMP + INTERVAL '1 hour' END`,
    [first.actionId],
  );
  const retry = await service.claimNext("worker-beta", 5);
  assert.ok(retry);
  assert.equal(retry.actionId, first.actionId);
  assert.equal(retry.idempotencyKey, first.idempotencyKey);
  assert.equal(retry.attemptNumber, 2);
  await database.query(
    "UPDATE artifact_quarantine_actions SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id = $1",
    [retry.actionId],
  );
  const reclaimed = await service.claimNext("worker-gamma", 5);
  assert.ok(reclaimed);
  assert.equal(reclaimed.actionId, first.actionId);
  assert.equal(reclaimed.attemptNumber, 3);
  await assert.rejects(
    service.recordSuccess("worker-beta", retry, receipt(retry, "already-satisfied")),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  await service.recordSuccess("worker-gamma", reclaimed, receipt(reclaimed, "already-satisfied"));

  await database.query(
    "UPDATE artifact_quarantine_actions SET available_at = CURRENT_TIMESTAMP WHERE status = 'pending'",
  );
  const exhausted = await service.claimNext("worker-delta", 5);
  assert.ok(exhausted);
  await database.query(
    `UPDATE artifact_quarantine_actions SET attempt_count = 8,
       lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id = $1`,
    [exhausted.actionId],
  );
  assert.equal(await service.claimNext("worker-epsilon", 5), undefined);
  const exhaustedState = await database.query<{ status: string }>(
    "SELECT status FROM artifact_quarantine_actions WHERE id = $1",
    [exhausted.actionId],
  );
  assert.equal(exhaustedState.rows[0]?.status, "dead-letter");
});

test("malformed receipts and permanent adapter failures dead-letter actions", async (t) => {
  const { database } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const service = new ArtifactQuarantineService(database);
  const malformed = new ArtifactQuarantineReconciler(service, {
    execute: async (action) => ({ ...receipt(action), receiptSha256: "not-a-hash" }),
  });
  assert.equal((await malformed.runOnce("worker-alpha")).status, "dead-lettered");

  const permanent = new ArtifactQuarantineReconciler(service, {
    execute: async () => {
      throw new ArtifactQuarantineAdapterError("permanent-rejection", false);
    },
  });
  assert.equal((await permanent.runOnce("worker-alpha")).status, "dead-lettered");
  const dead = await database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM artifact_quarantine_actions WHERE status = 'dead-letter'",
  );
  assert.equal(dead.rows[0]?.count, 2);
});

test("Ed25519 receipts bind the full action and persist verification evidence", async (t) => {
  const { database, deletionReceipt } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const now = new Date("2026-07-10T22:00:30.000Z");
  const verifier = new Ed25519ArtifactQuarantineReceiptVerifier([{
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
  }], { now: () => now });
  const registeredKey = await new ArtifactReceiptSigningKeyService(database).register(owner, {
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: "2026-01-01T00:00:00.000Z",
    validUntil: "2027-01-01T00:00:00.000Z",
  });
  const reconciler = new ArtifactQuarantineReconciler(
    new ArtifactQuarantineService(database),
    new VerifyingArtifactQuarantineAdapter({
      execute: async (action) => signedReceipt(action, privateKey),
    }, verifier),
  );

  assert.equal((await reconciler.runOnce("worker-alpha")).status, "succeeded");
  const persisted = await database.query<{
    receipt_provider_id: string;
    receipt_signing_key_id: string;
    receipt_public_key_sha256: string;
    receipt_signature_algorithm: string;
    receipt_issued_at: string | Date;
    receipt_signature_sha256: string;
  }>(
    `SELECT receipt_provider_id, receipt_signing_key_id, receipt_public_key_sha256,
       receipt_signature_algorithm, receipt_issued_at, receipt_signature_sha256
     FROM artifact_quarantine_actions WHERE status = 'succeeded'`,
  );
  assert.equal(persisted.rows[0]?.receipt_provider_id, "provider-test");
  assert.equal(persisted.rows[0]?.receipt_signing_key_id, "key-test-v1");
  assert.equal(persisted.rows[0]?.receipt_public_key_sha256, registeredKey.publicKeySha256);
  assert.equal(persisted.rows[0]?.receipt_signature_algorithm, "Ed25519");
  assert.equal(new Date(persisted.rows[0]?.receipt_issued_at ?? 0).toISOString(), "2026-07-10T22:00:00.000Z");
  assert.match(persisted.rows[0]?.receipt_signature_sha256 ?? "", /^[a-f0-9]{64}$/);
  const event = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM artifact_quarantine_action_events
     WHERE event_type = 'succeeded' AND receipt_provider_id = 'provider-test'
       AND receipt_signature_sha256 IS NOT NULL`,
  );
  assert.equal(event.rows[0]?.count, 1);
  const drill = await new ArtifactOperationsService(database).buildDeletionDrillReport(
    owner, deletionReceipt.requestId,
  );
  assert.equal(drill.counts.signedReceipts, 1);
  assert.equal(drill.foundationChecksPassed, false);
});

test("revocation after verification blocks signed-success persistence atomically", async (t) => {
  const { database } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const keys = new ArtifactReceiptSigningKeyService(database);
  await keys.register(owner, {
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: "2026-01-01T00:00:00.000Z",
    validUntil: "2027-01-01T00:00:00.000Z",
  });
  const service = new ArtifactQuarantineService(database);
  const action = await service.claimNext("worker-alpha");
  assert.ok(action);
  const verifier = await keys.createVerifier(owner, {
    now: () => new Date("2026-07-10T22:00:30.000Z"),
  });
  const verified = verifier.verify(action, signedReceipt(action, privateKey));

  await keys.revoke(owner, "provider-test", "key-test-v1", "compromised");
  await assert.rejects(
    service.recordSuccess("worker-alpha", action, verified),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  assert.equal(
    await service.recordFailure("worker-alpha", action, "verification-failed", false),
    "dead-lettered",
  );
});

test("a verifier using different key material under a registered key ID cannot persist", async (t) => {
  const { database } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const registeredPair = generateKeyPairSync("ed25519");
  const mismatchedPair = generateKeyPairSync("ed25519");
  await new ArtifactReceiptSigningKeyService(database).register(owner, {
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    publicKeyPem: registeredPair.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: "2026-01-01T00:00:00.000Z",
    validUntil: "2027-01-01T00:00:00.000Z",
  });
  const verifier = new Ed25519ArtifactQuarantineReceiptVerifier([{
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    publicKeyPem: mismatchedPair.publicKey.export({ type: "spki", format: "pem" }).toString(),
  }], { now: () => new Date("2026-07-10T22:00:30.000Z") });
  const service = new ArtifactQuarantineService(database);
  const action = await service.claimNext("worker-alpha");
  assert.ok(action);
  const verified = verifier.verify(action, signedReceipt(action, mismatchedPair.privateKey));

  await assert.rejects(
    service.recordSuccess("worker-alpha", action, verified),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  assert.equal(
    await service.recordFailure("worker-alpha", action, "verification-failed", false),
    "dead-lettered",
  );
});

test("tampered, stale, unknown-key, malformed, unregistered, and forged receipt evidence fail closed", async (t) => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const verifier = new Ed25519ArtifactQuarantineReceiptVerifier([{
    providerId: "provider-test",
    signingKeyId: "key-test-v1",
    publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
  }], { now: () => new Date("2026-07-10T22:00:30.000Z"), maxReceiptAgeSeconds: 60 });

  for (const mode of [
    "tampered", "stale", "unknown-key", "missing-envelope", "invalid-envelope",
    "unregistered",
  ] as const) {
    const { database } = await quarantineDatasetOnly();
    t.after(() => database.close());
    const reconciler = new ArtifactQuarantineReconciler(
      new ArtifactQuarantineService(database),
      new VerifyingArtifactQuarantineAdapter({
        execute: async (action) => {
          if (mode === "missing-envelope") {
            return {} as SignedArtifactQuarantineActionReceipt;
          }
          const valid = signedReceipt(
            action,
            privateKey,
            mode === "stale" ? "2026-07-10T21:58:00.000Z" : undefined,
          );
          if (mode === "tampered") return { ...valid, outcome: "already-satisfied" };
          if (mode === "unknown-key") {
            return {
              ...valid,
              signatureEnvelope: { ...valid.signatureEnvelope, signingKeyId: "key-unknown" },
            };
          }
          if (mode === "invalid-envelope") {
            return {
              ...valid,
              signatureEnvelope: {
                ...valid.signatureEnvelope,
                issuedAt: 42,
                signature: null,
              },
            } as unknown as SignedArtifactQuarantineActionReceipt;
          }
          return valid;
        },
      }, verifier),
    );
    assert.equal((await reconciler.runOnce("worker-alpha")).status, "dead-lettered");
  }

  const { database } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const service = new ArtifactQuarantineService(database);
  const claim = await service.claimNext("worker-alpha");
  assert.ok(claim);
  const verified = verifier.verify(claim, signedReceipt(claim, privateKey));
  assert.throws(() => {
    (verified as { outcome: string }).outcome = "already-satisfied";
  }, TypeError);
  assert.throws(() => {
    (verified.verification as { providerId: string }).providerId = "provider-forged";
  }, TypeError);
  await assert.rejects(
    service.recordSuccess("worker-alpha", claim, {
      ...receipt(claim),
      verification: {
        providerId: "provider-test",
        signingKeyId: "key-test-v1",
        algorithm: "Ed25519",
        publicKeySha256: "c".repeat(64),
        issuedAt: "2026-07-10T22:00:00.000Z",
        signatureSha256: "f".repeat(64),
      },
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
});

test("authorized queue health distinguishes healthy, overdue, and dead-letter states", async (t) => {
  const { database, platform } = await fixture();
  t.after(() => database.close());
  const operations = new ArtifactOperationsService(database);

  const empty = await operations.getQuarantineHealth(owner, 60);
  assert.equal(empty.status, "healthy");
  assert.equal(empty.pendingCount, 0);
  assert.equal(empty.oldestReadySeconds, null);
  await platform.deleteLearner(owner, "learner-a");
  const initial = await operations.getQuarantineHealth(owner, 60);
  assert.equal(initial.pendingCount, 2);
  assert.equal(initial.countsByActionType["purge-subject-data"], 1);
  await assert.rejects(
    operations.getQuarantineHealth(clinician),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  await database.query(
    "UPDATE artifact_quarantine_actions SET available_at = CURRENT_TIMESTAMP - INTERVAL '2 minutes'",
  );
  const overdue = await operations.getQuarantineHealth(reviewer, 60);
  assert.equal(overdue.status, "attention");
  assert.equal(overdue.overdueReadyCount, 2);

  const reconciler = new ArtifactQuarantineReconciler(
    new ArtifactQuarantineService(database),
    { execute: async () => { throw new ArtifactQuarantineAdapterError("permanent-rejection", false); } },
  );
  assert.equal((await reconciler.runOnce("worker-alpha")).status, "dead-lettered");
  const critical = await operations.getQuarantineHealth(owner, 60);
  assert.equal(critical.status, "critical");
  assert.equal(critical.deadLetterCount, 1);
});

test("alert evidence is audited, deterministic in scope, and never claims delivery", async (t) => {
  const { database, platform } = await fixture();
  t.after(() => database.close());
  const operations = new ArtifactOperationsService(database);

  const healthy = await operations.buildQuarantineAlertEvidence(owner, 60);
  assert.equal(healthy.alertRequired, false);
  assert.deepEqual(healthy.reasons, []);
  assert.equal(healthy.deliveryEvidencePresent, false);
  assert.equal(healthy.productionGateEligible, false);

  await platform.deleteLearner(owner, "learner-a");
  await database.query(
    "UPDATE artifact_quarantine_actions SET available_at = CURRENT_TIMESTAMP - INTERVAL '2 minutes'",
  );
  const overdue = await operations.buildQuarantineAlertEvidence(reviewer, 60);
  assert.equal(overdue.status, "attention");
  assert.deepEqual(overdue.reasons, ["overdue-ready"]);
  assert.match(overdue.fingerprintSha256, /^[a-f0-9]{64}$/);
  assert.ok(overdue.missingProductionEvidence.includes("authenticated alert-channel delivery receipt"));

  const audit = await database.query<{
    count: number;
    delivery_present: boolean;
    production_eligible: boolean;
  }>(
    `SELECT COUNT(*)::INTEGER AS count,
       bool_or((metadata->>'delivery_evidence_present')::BOOLEAN) AS delivery_present,
       bool_or((metadata->>'production_gate_eligible')::BOOLEAN) AS production_eligible
     FROM audit_events WHERE action = 'artifact.quarantine-alert-evidence.created'`,
  );
  assert.equal(audit.rows[0]?.count, 2);
  assert.equal(audit.rows[0]?.delivery_present, false);
  assert.equal(audit.rows[0]?.production_eligible, false);
  await assert.rejects(
    operations.buildQuarantineAlertEvidence(clinician, 60),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});

test("deletion drill reports incomplete work then passes local checks without claiming production evidence", async (t) => {
  const { database, deletionReceipt } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const operations = new ArtifactOperationsService(database);
  const before = await operations.buildDeletionDrillReport(
    owner, deletionReceipt.requestId, 300,
  );
  assert.equal(before.foundationChecksPassed, false);
  assert.equal(before.checks.transientClinicalDataPurged, true);
  assert.equal(before.checks.lineageFullyQuarantined, true);
  assert.equal(before.checks.requiredActionsSucceeded, false);
  assert.equal(before.counts.unresolvedActions, 2);

  const service = new ArtifactQuarantineService(database);
  const reconciler = new ArtifactQuarantineReconciler(service, {
    execute: async (action) => receipt(action),
  });
  assert.equal((await reconciler.runOnce("worker-alpha")).status, "succeeded");
  assert.equal((await reconciler.runOnce("worker-alpha")).status, "succeeded");

  const after = await operations.buildDeletionDrillReport(
    reviewer, deletionReceipt.requestId, 300,
  );
  assert.equal(after.foundationChecksPassed, true);
  assert.equal(after.productionGateEligible, false);
  assert.equal(after.evidencePosture, "local-foundation");
  assert.equal(after.counts.expectedArtifacts, 1);
  assert.equal(after.counts.succeededActions, 2);
  assert.ok(after.missingProductionEvidence.includes(
    "provider-backed signed action receipts from the managed environment",
  ));
});

test("deletion drill rejects unexpected actions on its deletion event", async (t) => {
  const { database, deletionReceipt } = await quarantineDatasetOnly();
  t.after(() => database.close());
  const event = await database.query<{ sequence_id: number }>(
    `SELECT sequence_id FROM artifact_quarantine_events
     WHERE source_learner_id = 'learner-a' AND reason = 'learner-deleted'`,
  );
  const sequenceId = event.rows[0]?.sequence_id;
  assert.ok(sequenceId);
  await database.query(
    `INSERT INTO artifact_quarantine_actions (
       id, quarantine_event_sequence_id, tenant_id, artifact_id,
       source_learner_id, action_type, idempotency_key
     ) VALUES ($1, $2, 'tenant-a', 'dataset-audio-v1', 'learner-a',
       'schedule-retraining', $3)`,
    [`action-${sequenceId}-unexpected`, sequenceId, `quarantine-${sequenceId}-unexpected`],
  );

  const report = await new ArtifactOperationsService(database).buildDeletionDrillReport(
    owner, deletionReceipt.requestId,
  );
  assert.equal(report.counts.unexpectedActions, 1);
  assert.equal(report.checks.requiredActionsSucceeded, false);
  assert.equal(report.foundationChecksPassed, false);
});

test("deletion drill binds to deletion events after an earlier consent quarantine", async (t) => {
  const { database, platform } = await fixture();
  t.after(() => database.close());
  await platform.createConsentSnapshot(clinician, {
    learnerId: "learner-a",
    noticeVersion: "research-v2",
    audioProcessing: false,
    videoProcessing: false,
    clinicianReview: false,
    researchUse: false,
    assentStatus: "withdrawn",
  });
  const deletionReceipt = await platform.deleteLearner(owner, "learner-a");
  const report = await new ArtifactOperationsService(database).buildDeletionDrillReport(
    reviewer, deletionReceipt.requestId,
  );
  assert.equal(report.counts.expectedArtifacts, 1);
  assert.equal(report.counts.quarantineEvents, 1);
  assert.equal(report.counts.expectedActions, 2);
  assert.equal(report.counts.unresolvedActions, 2);
});

test("deletion drill treats a learner with no research artifacts as vacuously complete", async (t) => {
  const { database, platform } = await fixture();
  t.after(() => database.close());
  await database.query(
    "INSERT INTO learners (id, tenant_id, display_label) VALUES ('learner-empty', 'tenant-a', 'Learner Empty')",
  );
  const deletionReceipt = await platform.deleteLearner(owner, "learner-empty");
  const report = await new ArtifactOperationsService(database).buildDeletionDrillReport(
    owner, deletionReceipt.requestId,
  );
  assert.equal(report.counts.expectedArtifacts, 0);
  assert.equal(report.counts.expectedActions, 0);
  assert.equal(report.maximumCompletionSeconds, null);
  assert.equal(report.foundationChecksPassed, true);
});

test("learner exports disclose only subject-scoped retained artifact and quarantine evidence", async (t) => {
  const { database, platform } = await fixture();
  t.after(() => database.close());

  const active = await platform.exportLearner(clinician, "learner-a");
  assert.equal(active.researchArtifactImpacts.length, 1);
  assert.deepEqual(active.researchArtifactImpacts[0], {
    artifactId: "dataset-audio-v1",
    kind: "dataset",
    version: "dataset-v1",
    status: "active",
    releasePosture: "research-only",
    learnerFeedbackEligible: false,
    consentSnapshotIds: [active.consentSnapshots[0]?.id],
    processingPurposes: ["audio-research"],
    subjectQuarantineEvents: [],
  });

  await platform.deleteLearner(owner, "learner-a");
  const quarantined = await platform.exportLearner(owner, "learner-a");
  const impact = quarantined.researchArtifactImpacts[0];
  assert.equal(impact?.status, "quarantined");
  assert.equal(impact?.subjectQuarantineEvents.length, 1);
  assert.equal(impact?.subjectQuarantineEvents[0]?.reason, "learner-deleted");
  assert.deepEqual(
    impact?.subjectQuarantineEvents[0]?.actions.map((action) => ({
      type: action.actionType,
      status: action.status,
      receiptRecorded: action.receiptRecorded,
    })),
    [
      { type: "purge-subject-data", status: "pending", receiptRecorded: false },
      { type: "revoke-artifact-access", status: "pending", receiptRecorded: false },
    ],
  );
  const quarantineService = new ArtifactQuarantineService(database);
  const successful = new ArtifactQuarantineReconciler(quarantineService, {
    execute: async (action) => receipt(action),
  });
  assert.equal((await successful.runOnce("worker-alpha")).status, "succeeded");
  const failed = new ArtifactQuarantineReconciler(quarantineService, {
    execute: async () => {
      throw new ArtifactQuarantineAdapterError("permanent-rejection", false);
    },
  });
  assert.equal((await failed.runOnce("worker-alpha")).status, "dead-lettered");
  const finalExport = await platform.exportLearner(owner, "learner-a");
  assert.deepEqual(
    finalExport.researchArtifactImpacts[0]?.subjectQuarantineEvents[0]?.actions.map(
      (action) => ({
        status: action.status,
        receiptRecorded: action.receiptRecorded,
        lastErrorCode: action.lastErrorCode,
      }),
    ),
    [
      { status: "succeeded", receiptRecorded: true, lastErrorCode: undefined },
      { status: "dead-letter", receiptRecorded: false, lastErrorCode: "permanent-rejection" },
    ],
  );
  const serialized = JSON.stringify(finalExport);
  assert.doesNotMatch(
    serialized,
    /sha256|receiptReference|receiptSha256|idempotencyKey|leasedBy|leaseToken|workerId|sourceLearnerId/,
  );

  const otherSubject = await platform.exportLearner(clinician, "learner-c");
  assert.equal(otherSubject.researchArtifactImpacts[0]?.status, "quarantined");
  assert.deepEqual(otherSubject.researchArtifactImpacts[0]?.subjectQuarantineEvents, []);
  const exportRequest = await database.query<{ count: number }>(
    `SELECT (receipt->>'research_artifact_impact_count')::INTEGER AS count
     FROM data_subject_requests WHERE id = $1`,
    [quarantined.requestId],
  );
  assert.equal(exportRequest.rows[0]?.count, 1);
});
