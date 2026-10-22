import assert from "node:assert/strict";
import { generateKeyPairSync, sign, type KeyObject } from "node:crypto";
import test from "node:test";

import { ArtifactReceiptSigningKeyService } from "./artifact-receipt-keys.ts";
import {
  ArtifactQuarantineAdapterError,
  canonicalArtifactQuarantineReceiptPayload,
} from "./artifact-quarantine.ts";
import { PlatformDataError } from "./errors.ts";
import { applyFoundationMigration } from "./migrate.ts";
import { PGliteDatabase } from "./pglite.ts";
import type {
  ActorContext,
  ArtifactQuarantineActionClaim,
  SignedArtifactQuarantineActionReceipt,
} from "./types.ts";

const ownerA: ActorContext = { actorId: "actor-owner-a", tenantId: "tenant-a", role: "owner" };
const reviewerA: ActorContext = { actorId: "actor-reviewer-a", tenantId: "tenant-a", role: "reviewer" };
const clinicianA: ActorContext = { actorId: "actor-clinician-a", tenantId: "tenant-a", role: "clinician" };
const ownerB: ActorContext = { actorId: "actor-owner-b", tenantId: "tenant-b", role: "owner" };

const claim: ArtifactQuarantineActionClaim = {
  actionId: "action-receipt-test",
  tenantId: "tenant-a",
  artifactId: "artifact-receipt-test",
  artifactKind: "dataset",
  artifactSha256: "a".repeat(64),
  sourceLearnerId: "learner-receipt-test",
  actionType: "purge-subject-data",
  quarantineReason: "learner-deleted",
  idempotencyKey: "idempotency-receipt-test",
  attemptNumber: 1,
  leaseToken: "lease-token-test",
  leaseExpiresAt: "2026-07-10T22:01:00.000Z",
};

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
  return { database, service: new ArtifactReceiptSigningKeyService(database) };
}

function publicPem(publicKey: KeyObject): string {
  return publicKey.export({ type: "spki", format: "pem" }).toString();
}

function signedReceipt(
  privateKey: KeyObject,
  signingKeyId: string,
  providerId = "provider-test",
): SignedArtifactQuarantineActionReceipt {
  const receipt = {
    actionId: claim.actionId,
    idempotencyKey: claim.idempotencyKey,
    artifactSha256: claim.artifactSha256,
    actionType: claim.actionType,
    receiptReference: `receipt/${signingKeyId}`,
    receiptSha256: "b".repeat(64),
    outcome: "performed",
  } as const;
  const envelope = {
    schemaVersion: "artifact-quarantine-receipt-signature-v1",
    providerId,
    signingKeyId,
    algorithm: "Ed25519",
    issuedAt: "2026-07-10T22:00:00.000Z",
  } as const;
  return {
    ...receipt,
    signatureEnvelope: {
      ...envelope,
      signature: sign(
        null,
        Buffer.from(canonicalArtifactQuarantineReceiptPayload(receipt, envelope)),
        privateKey,
      ).toString("base64url"),
    },
  };
}

test("rotation overlap trusts both active keys, then revocation removes only the old key", async (t) => {
  const { database, service } = await fixture();
  t.after(() => database.close());
  const oldPair = generateKeyPairSync("ed25519");
  const newPair = generateKeyPairSync("ed25519");
  const foreignPair = generateKeyPairSync("ed25519");

  await assert.rejects(
    service.register(clinicianA, {
      providerId: "provider-test", signingKeyId: "key-old",
      publicKeyPem: publicPem(oldPair.publicKey),
      validFrom: "2026-01-01T00:00:00.000Z", validUntil: "2027-01-01T00:00:00.000Z",
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await service.register(ownerA, {
    providerId: "provider-test", signingKeyId: "key-old",
    publicKeyPem: publicPem(oldPair.publicKey),
    validFrom: "2026-01-01T00:00:00.000Z", validUntil: "2027-01-01T00:00:00.000Z",
  });
  await service.register(ownerA, {
    providerId: "provider-test", signingKeyId: "key-new",
    publicKeyPem: publicPem(newPair.publicKey),
    validFrom: "2026-06-01T00:00:00.000Z", validUntil: "2027-06-01T00:00:00.000Z",
  });
  await service.register(ownerB, {
    providerId: "provider-test", signingKeyId: "key-foreign",
    publicKeyPem: publicPem(foreignPair.publicKey),
    validFrom: "2026-01-01T00:00:00.000Z", validUntil: "2027-01-01T00:00:00.000Z",
  });

  const listed = await service.list(reviewerA);
  assert.deepEqual(listed.map((key) => [key.signingKeyId, key.status]), [
    ["key-old", "active"],
    ["key-new", "active"],
  ]);
  assert.ok(listed.every((key) => key.publicKeySha256.match(/^[a-f0-9]{64}$/)));
  assert.doesNotMatch(JSON.stringify(listed), /BEGIN PUBLIC KEY/);

  const overlapVerifier = await service.createVerifier(reviewerA, {
    now: () => new Date("2026-07-10T22:00:30.000Z"),
  });
  assert.equal(overlapVerifier.verify(claim, signedReceipt(oldPair.privateKey, "key-old")).outcome, "performed");
  assert.equal(overlapVerifier.verify(claim, signedReceipt(newPair.privateKey, "key-new")).outcome, "performed");
  assert.throws(
    () => overlapVerifier.verify(
      claim,
      signedReceipt(foreignPair.privateKey, "key-foreign"),
    ),
    ArtifactQuarantineAdapterError,
  );

  await assert.rejects(
    service.revoke(reviewerA, "provider-test", "key-old", "rotated"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const revoked = await service.revoke(ownerA, "provider-test", "key-old", "rotated");
  assert.equal(revoked.status, "revoked");
  assert.equal(revoked.revocationReason, "rotated");
  await assert.rejects(
    service.revoke(ownerA, "provider-test", "key-old", "rotated"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  await assert.rejects(
    service.revoke(ownerB, "provider-test", "key-old", "provider-disabled"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  const postRotationVerifier = await service.createVerifier(ownerA, {
    now: () => new Date("2026-07-10T22:00:30.000Z"),
  });
  assert.throws(
    () => postRotationVerifier.verify(claim, signedReceipt(oldPair.privateKey, "key-old")),
    ArtifactQuarantineAdapterError,
  );
  assert.equal(postRotationVerifier.verify(
    claim,
    signedReceipt(newPair.privateKey, "key-new"),
  ).outcome, "performed");
  const tenantCounts = await database.query<{ tenant_id: string; count: number }>(
    `SELECT tenant_id, COUNT(*)::INTEGER AS count
     FROM artifact_receipt_signing_keys GROUP BY tenant_id ORDER BY tenant_id`,
  );
  assert.deepEqual(tenantCounts.rows, [
    { tenant_id: "tenant-a", count: 2 },
    { tenant_id: "tenant-b", count: 1 },
  ]);
  const audits = await database.query<{ action: string; count: number }>(
    `SELECT action, COUNT(*)::INTEGER AS count FROM audit_events
     WHERE tenant_id = 'tenant-a' AND action LIKE 'artifact.receipt-signing-key%'
     GROUP BY action ORDER BY action`,
  );
  assert.deepEqual(audits.rows, [
    { action: "artifact.receipt-signing-key.registered", count: 2 },
    { action: "artifact.receipt-signing-key.revoked", count: 1 },
    { action: "artifact.receipt-signing-keys.listed", count: 1 },
    { action: "artifact.receipt-signing-keys.loaded", count: 2 },
  ]);

  await assert.rejects(
    database.query("UPDATE artifact_receipt_signing_keys SET signing_key_id = 'key-changed'"),
    /append-only/,
  );
  await assert.rejects(
    database.query("DELETE FROM artifact_receipt_signing_key_revocations"),
    /append-only/,
  );
});

test("scheduled, expired, duplicate, malformed, and empty active key sets fail safely", async (t) => {
  const { database, service } = await fixture();
  t.after(() => database.close());
  const scheduled = generateKeyPairSync("ed25519");
  const expired = generateKeyPairSync("ed25519");
  await service.register(ownerA, {
    providerId: "provider-test", signingKeyId: "key-scheduled",
    publicKeyPem: publicPem(scheduled.publicKey),
    validFrom: "2028-01-01T00:00:00.000Z", validUntil: "2029-01-01T00:00:00.000Z",
  });
  await service.register(ownerA, {
    providerId: "provider-test", signingKeyId: "key-expired",
    publicKeyPem: publicPem(expired.publicKey),
    validFrom: "2024-01-01T00:00:00.000Z", validUntil: "2025-01-01T00:00:00.000Z",
  });
  assert.deepEqual((await service.list(ownerA)).map((key) => key.status), ["expired", "scheduled"]);
  await assert.rejects(
    service.createVerifier(ownerA),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await assert.rejects(
    service.register(ownerA, {
      providerId: "provider-test", signingKeyId: "key-duplicate-material",
      publicKeyPem: publicPem(scheduled.publicKey),
      validFrom: "2028-01-01T00:00:00.000Z", validUntil: "2029-01-01T00:00:00.000Z",
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  const rsa = generateKeyPairSync("rsa", { modulusLength: 2048 });
  await assert.rejects(
    service.register(ownerA, {
      providerId: "provider-test", signingKeyId: "key-rsa",
      publicKeyPem: publicPem(rsa.publicKey),
      validFrom: "2026-01-01T00:00:00.000Z", validUntil: "2027-01-01T00:00:00.000Z",
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
});
