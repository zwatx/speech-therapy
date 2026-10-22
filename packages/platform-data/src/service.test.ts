import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import type { DatabaseClient, QueryResult } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import { applyFoundationMigration } from "./migrate.ts";
import { PGliteDatabase } from "./pglite.ts";
import {
  maximumActiveLearnerDeviceSessions,
  maximumActorTokenGenerationsPerHour,
  maximumAssignmentReadsPerDeviceSessionPerHour,
  maximumAttemptUploadsPerDeviceSessionPerHour,
  maximumLearnerTokenGenerationsPerHour,
} from "./device-session-policy.ts";
import { PlatformDataService } from "./service.ts";
import type { ActorContext, ConsentSnapshotInput } from "./types.ts";

const ownerA: ActorContext = {
  actorId: "actor-owner-a",
  tenantId: "tenant-a",
  role: "owner",
};
const clinicianA: ActorContext = {
  actorId: "actor-clinician-a",
  tenantId: "tenant-a",
  role: "clinician",
};
const reviewerA: ActorContext = {
  actorId: "actor-reviewer-a",
  tenantId: "tenant-a",
  role: "reviewer",
};
const subjectHashA = "a".repeat(64);
const organizationHashA = "b".repeat(64);
const clinicianHashA = "e".repeat(64);
const reviewerHashA = "f".repeat(64);
const ownerHashB = "1".repeat(64);

const grantedConsent: ConsentSnapshotInput = {
  learnerId: "learner-a",
  noticeVersion: "notice-v1",
  audioProcessing: true,
  videoProcessing: false,
  clinicianReview: true,
  researchUse: false,
  assentStatus: "affirmed",
};

async function createDatabase(): Promise<PGliteDatabase> {
  const database = new PGliteDatabase();
  await applyFoundationMigration(database);
  await seed(database);
  return database;
}

async function seed(database: PGliteDatabase): Promise<void> {
  await database.query(
    `INSERT INTO tenants (id, display_name, external_organization_hash)
     VALUES
       ('tenant-a', 'Clinic A', $1),
       ('tenant-b', 'Clinic B', $2)`,
    [organizationHashA, "c".repeat(64)],
  );
  await database.query(
    `INSERT INTO actors (id, external_subject_hash)
     VALUES
       ('actor-owner-a', $1),
       ('actor-clinician-a', $2),
       ('actor-reviewer-a', $3),
       ('actor-owner-b', $4)`,
    [subjectHashA, clinicianHashA, reviewerHashA, ownerHashB],
  );
  await database.query(
    `INSERT INTO tenant_memberships (tenant_id, actor_id, role)
     VALUES
       ('tenant-a', 'actor-owner-a', 'owner'),
       ('tenant-a', 'actor-clinician-a', 'clinician'),
       ('tenant-a', 'actor-reviewer-a', 'reviewer'),
       ('tenant-b', 'actor-owner-b', 'owner')`,
  );
  await database.query(
    `INSERT INTO learners (id, tenant_id, display_label)
     VALUES
       ('learner-a', 'tenant-a', 'Learner A'),
       ('learner-b', 'tenant-b', 'Learner B')`,
  );
}

function expectPlatformError(code: PlatformDataError["code"]) {
  return (error: unknown): boolean =>
    error instanceof PlatformDataError && error.code === code;
}

function expectPostgresCode(code: string) {
  return (error: unknown): boolean =>
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === code;
}

async function createFoundationAssignment(
  service: PlatformDataService,
  learnerId: string = "learner-a",
) {
  return service.createPracticeAssignment(clinicianA, {
    learnerId,
    exerciseId: "foundation-ball-initial-b-v1",
    attemptTarget: 20,
    retryLimit: 2,
  });
}

test("consent snapshots are versioned, superseding, audited, and immutable", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await assert.rejects(
    service.createConsentSnapshot(clinicianA, {
      ...grantedConsent,
      videoProcessing: true,
    }),
    expectPlatformError("invalid-consent"),
  );

  const first = await service.createConsentSnapshot(clinicianA, grantedConsent);
  const withdrawn = await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    audioProcessing: false,
    clinicianReview: false,
    assentStatus: "withdrawn",
  });

  assert.equal(first.version, 1);
  assert.equal(withdrawn.version, 2);
  assert.equal(withdrawn.supersedesSnapshotId, first.id);
  await assert.rejects(
    database.query(
      `INSERT INTO consent_snapshots (
         id, tenant_id, learner_id, version, notice_version,
         audio_processing, video_processing, clinician_review, research_use,
         assent_status, captured_by_actor_id
       ) VALUES (
         'snapshot-duplicate', 'tenant-a', 'learner-a', 1, 'notice-v1',
         TRUE, FALSE, TRUE, FALSE, 'affirmed', 'actor-clinician-a'
       )`,
    ),
    expectPostgresCode("23505"),
  );
  await assert.rejects(
    database.query(
      "UPDATE consent_snapshots SET research_use = TRUE WHERE id = $1",
      [first.id],
    ),
    /append-only/,
  );
  const audit = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM audit_events
     WHERE tenant_id = 'tenant-a' AND action = 'consent.snapshot.created'`,
  );
  assert.equal(audit.rows[0]?.count, 2);
  for (const table of [
    "consent_snapshots",
    "audit_events",
    "data_subject_requests",
  ]) {
    await assert.rejects(
      database.query(
        table === "consent_snapshots"
          ? "TRUNCATE consent_snapshots CASCADE"
          : `TRUNCATE ${table}`,
      ),
      /append-only/,
    );
  }
});

test("a 23505 unique violation becomes a safe consent conflict", async () => {
  const uniquenessError = Object.assign(new Error("duplicate key"), {
    code: "23505",
  });
  const database: DatabaseClient = {
    query: async () => {
      throw uniquenessError;
    },
  };
  const service = new PlatformDataService(database);

  await assert.rejects(
    service.createConsentSnapshot(clinicianA, grantedConsent),
    expectPlatformError("conflict"),
  );
});

test("active-slot collisions retry with a fresh issuance statement", async () => {
  let issuanceCalls = 0;
  const database: DatabaseClient = {
    query: async <Row extends Record<string, unknown>>(
      text: string,
    ): Promise<QueryResult<Row>> => {
      if (text.includes("device_access_rate_buckets")) {
        const rows = [
          {
            authorized: true,
            target_exists: true,
            allowed: true,
            retry_after_seconds: null,
          },
        ];
        return { rows: rows as unknown as Row[] };
      }
      if (text.includes("learner.device-session.created")) {
        issuanceCalls += 1;
        if (issuanceCalls === 1) {
          throw Object.assign(new Error("active slot collision"), {
            code: "23505",
            constraint: "learner_device_sessions_active_slot_idx",
          });
        }
        const rows = [
            {
              id: "device-session-retry",
              learner_id: "learner-a",
              expires_at: "2026-07-12T00:00:00.000Z",
              consent_snapshot_id: "consent-retry",
              authorized: true,
              target_exists: true,
              consent_eligible: true,
              active_count: 1,
            },
          ];
        return { rows: rows as unknown as Row[] };
      }
      const rows = [
          {
            session_id: "device-session-retry",
            tenant_id: "tenant-a",
            learner_id: "learner-a",
            consent_snapshot_id: "consent-retry",
            audio_processing: true,
            video_processing: false,
            clinician_review: true,
            research_use: false,
            allowed: true,
            retry_after_seconds: null,
          },
        ];
      return { rows: rows as unknown as Row[] };
    },
  };
  const service = new PlatformDataService(database);

  const receipt = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
    24,
  );
  assert.equal(issuanceCalls, 2);
  assert.equal(receipt.id, "device-session-retry");
});

test("external identity and organization hashes resolve only active membership", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  assert.deepEqual(
    await service.resolveActorContext(subjectHashA, organizationHashA),
    ownerA,
  );
  assert.equal(
    await service.resolveActorContext(subjectHashA, "c".repeat(64)),
    undefined,
  );
  await database.query(
    `UPDATE tenant_memberships
     SET status = 'suspended'
     WHERE tenant_id = 'tenant-a' AND actor_id = 'actor-owner-a'`,
  );
  assert.equal(
    await service.resolveActorContext(subjectHashA, organizationHashA),
    undefined,
  );
});

test("learner workspace reads and provisioning stay tenant-scoped and audited", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  const created = await service.createLearner(clinicianA, "  Casey   P.  ");
  assert.equal(created.displayLabel, "Casey P.");
  assert.match(created.id, /^[a-f0-9-]{36}$/);
  await assert.rejects(
    service.createLearner(reviewerA, "Not allowed"),
    expectPlatformError("access-denied"),
  );

  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const assignment = await createFoundationAssignment(service);
  const device = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  const context = await service.resolveLearnerDeviceSession(device.token);
  assert.ok(context);
  await service.recordPracticeAttempt(context, {
    attemptId: "attempt-workspace-001",
    assignmentId: assignment.id,
    repetitionIndex: 1,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent",
    durationMilliseconds: 980,
    sampleRateHertz: 16_000,
    rmsDbfs: -21,
    peakAmplitude: 0.7,
    reasonCodes: [],
  });

  const learners = await service.listLearners(reviewerA);
  assert.deepEqual(
    learners.map((learner) => learner.displayLabel),
    ["Casey P.", "Learner A"],
  );
  const learnerA = learners.find((learner) => learner.id === "learner-a");
  assert.equal(learnerA?.attemptCount, 1);
  assert.equal(learnerA?.activeDeviceSessionCount, 1);
  assert.equal(learnerA?.latestConsent?.audioProcessing, true);
  assert.ok(learnerA?.lastPracticeAt);

  const detail = await service.getLearner(reviewerA, "learner-a");
  assert.equal(detail.consentSnapshots.length, 1);
  assert.equal(detail.recentAttempts.length, 1);
  assert.equal(detail.recentAttempts[0]?.attemptId, "attempt-workspace-001");
  assert.equal(detail.recentAttempts[0]?.prompt, "ball");
  assert.equal(detail.recentAttempts[0]?.targetLabel, "Beginning /b/");
  assert.equal(detail.recentAttempts[0]?.benchmarkStatus, undefined);
  const reviewable = await service.listReviewableAttempts(reviewerA);
  assert.deepEqual(reviewable, [
    {
      attemptId: "attempt-workspace-001",
      learnerId: "learner-a",
      learnerDisplayLabel: "Learner A",
      consentSnapshotId: assignment.consentSnapshotId,
      consentVersion: 1,
      assignmentId: assignment.id,
      exerciseId: "foundation-ball-initial-b-v1",
      protocolId: "bilabial-closure-v1",
      prompt: "ball",
      targetLabel: "Beginning /b/",
      repetitionIndex: 1,
      retryIndex: 0,
      status: "accepted-silent",
      durationMilliseconds: 980,
      reasonCodes: [],
      receivedAt: reviewable[0]?.receivedAt,
    },
  ]);
  assert.match(reviewable[0]?.receivedAt ?? "", /^\d{4}-\d{2}-\d{2}T/);
  assert.deepEqual(
    await service.listReviewableAttempts({
      actorId: "actor-owner-b",
      tenantId: "tenant-b",
      role: "owner",
    }),
    [],
  );
  await assert.rejects(
    service.listReviewableAttempts({
      actorId: "actor-support-a",
      tenantId: "tenant-a",
      role: "support",
    }),
    expectPlatformError("access-denied"),
  );
  await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    noticeVersion: "notice-v2",
  });
  assert.deepEqual(await service.listReviewableAttempts(reviewerA), []);
  assert.deepEqual(
    (await service.getLearner(reviewerA, "learner-a")).recentAttempts,
    [],
  );
  await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    audioProcessing: false,
    clinicianReview: false,
    assentStatus: "withdrawn",
  });
  const afterWithdrawal = await service.listLearners(clinicianA);
  assert.equal(
    afterWithdrawal.find((learner) => learner.id === "learner-a")
      ?.activeDeviceSessionCount,
    0,
  );
  assert.deepEqual(await service.listReviewableAttempts(reviewerA), []);
  assert.deepEqual(
    (await service.getLearner(reviewerA, "learner-a")).recentAttempts,
    [],
  );
  await assert.rejects(
    service.getLearner(reviewerA, "learner-b"),
    expectPlatformError("access-denied"),
  );

  const audit = await database.query<{ action: string }>(
    `SELECT action FROM audit_events
     WHERE actor_id IN ('actor-clinician-a', 'actor-reviewer-a')
       AND action IN ('learner.created', 'learner.list.read', 'learner.read')
     ORDER BY action`,
  );
  assert.deepEqual(
    audit.rows.map((row) => row.action),
    [
      "learner.created",
      "learner.list.read",
      "learner.list.read",
      "learner.read",
      "learner.read",
      "learner.read",
    ],
  );
  const reviewAudit = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM audit_events
     WHERE tenant_id = 'tenant-a'
       AND actor_id = 'actor-reviewer-a'
       AND action = 'practice-attempt.review-list.read'`,
  );
  assert.equal(reviewAudit.rows[0]?.count, 3);
});

test("learner detail retains consent-authorized legacy captures without an assignment", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  const consent = await service.createConsentSnapshot(clinicianA, grantedConsent);
  const device = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  await database.query(
    `INSERT INTO practice_attempts (
       id, tenant_id, learner_id, device_session_id, consent_snapshot_id,
       assignment_id, exercise_id, protocol_id, status, duration_milliseconds,
       sample_rate_hertz, rms_dbfs, peak_amplitude
     ) VALUES (
       'attempt-legacy-001', 'tenant-a', 'learner-a', $1, $2,
       NULL, 'foundation-ball-initial-b-v1', 'bilabial-closure-v1',
       'accepted-silent', 980, 16000, -21, 0.7
     )`,
    [device.id, consent.id],
  );

  const detail = await service.getLearner(reviewerA, "learner-a");
  assert.equal(detail.attemptCount, 1);
  assert.equal(detail.recentAttempts.length, 1);
  assert.equal(detail.recentAttempts[0]?.attemptId, "attempt-legacy-001");
  assert.equal(detail.recentAttempts[0]?.prompt, undefined);
  assert.equal(detail.recentAttempts[0]?.targetLabel, undefined);
  assert.equal(detail.recentAttempts[0]?.status, "accepted-silent");

  await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    noticeVersion: "notice-v2",
  });
  assert.deepEqual((await service.getLearner(reviewerA, "learner-a")).recentAttempts, []);
});

test("learner device sessions require current consent and never store raw tokens", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await assert.rejects(
    service.issueLearnerDeviceSession(clinicianA, "learner-a"),
    expectPlatformError("access-denied"),
  );
  const consent = await service.createConsentSnapshot(clinicianA, grantedConsent);
  const receipt = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
    2,
  );

  assert.match(receipt.token, /^[A-Za-z0-9_-]{43}$/);
  assert.equal(receipt.consentSnapshotId, consent.id);
  assert.deepEqual(await service.resolveLearnerDeviceSession(receipt.token), {
    sessionId: receipt.id,
    tenantId: "tenant-a",
    learnerId: "learner-a",
    consentSnapshotId: consent.id,
    audioProcessing: true,
    videoProcessing: false,
    clinicianReview: true,
    researchUse: false,
  });
  const stored = await database.query<{ token_hash: string }>(
    "SELECT token_hash FROM learner_device_sessions WHERE id = $1",
    [receipt.id],
  );
  assert.match(stored.rows[0]?.token_hash ?? "", /^[a-f0-9]{64}$/);
  assert.notEqual(stored.rows[0]?.token_hash, receipt.token);
  const listed = await service.listLearnerDeviceSessions(reviewerA, "learner-a");
  assert.deepEqual(listed, [
    {
      id: receipt.id,
      learnerId: "learner-a",
      consentSnapshotId: consent.id,
      consentVersion: 1,
      createdAt: listed[0]?.createdAt,
      expiresAt: receipt.expiresAt,
      status: "active",
    },
  ]);
  assert.equal(JSON.stringify(listed).includes(receipt.token), false);
  await assert.rejects(
    service.listLearnerDeviceSessions(ownerA, "learner-b"),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.revokeLearnerDeviceSession(reviewerA, "learner-a", receipt.id),
    expectPlatformError("access-denied"),
  );
  const revocations = await Promise.all([
    service.revokeLearnerDeviceSession(ownerA, "learner-a", receipt.id),
    service.revokeLearnerDeviceSession(clinicianA, "learner-a", receipt.id),
  ]);
  assert.deepEqual(
    revocations.map((value) => value.alreadyRevoked).sort(),
    [false, true],
  );
  assert.equal(revocations[0]?.revokedAt, revocations[1]?.revokedAt);
  assert.equal(await service.resolveLearnerDeviceSession(receipt.token), undefined);
  const repeated = await service.revokeLearnerDeviceSession(
    clinicianA,
    "learner-a",
    receipt.id,
  );
  assert.equal(repeated.alreadyRevoked, true);
  const revoked = await service.listLearnerDeviceSessions(reviewerA, "learner-a");
  assert.equal(revoked[0]?.status, "revoked");
  assert.equal(revoked[0]?.revokedAt, repeated.revokedAt);

  const renewedDevice = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
    8,
  );
  await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    noticeVersion: "notice-v2",
  });
  const invalidated = await service.listLearnerDeviceSessions(
    reviewerA,
    "learner-a",
  );
  assert.equal(
    invalidated.find((session) => session.id === renewedDevice.id)?.status,
    "consent-invalidated",
  );
  assert.equal(
    await service.resolveLearnerDeviceSession(renewedDevice.token),
    undefined,
  );
  const expiredDevice = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
    1,
  );
  await database.query(
    `UPDATE learner_device_sessions
     SET created_at = CURRENT_TIMESTAMP - INTERVAL '2 hours',
         expires_at = CURRENT_TIMESTAMP - INTERVAL '1 hour'
     WHERE id = $1`,
    [expiredDevice.id],
  );
  const withExpired = await service.listLearnerDeviceSessions(
    reviewerA,
    "learner-a",
  );
  assert.equal(
    withExpired.find((session) => session.id === expiredDevice.id)?.status,
    "expired",
  );
  assert.equal(
    await service.resolveLearnerDeviceSession(expiredDevice.token),
    undefined,
  );
  const revocationAudit = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM audit_events
     WHERE action = 'learner.device-session.revoked'
       AND resource_id = $1`,
    [receipt.id],
  );
  assert.equal(revocationAudit.rows[0]?.count, 1);
  assert.equal(
    await service.resolveLearnerDeviceSession("x".repeat(43)),
    undefined,
  );
  await assert.rejects(
    service.issueLearnerDeviceSession(reviewerA, "learner-a"),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.issueLearnerDeviceSession(ownerA, "learner-b"),
    expectPlatformError("access-denied"),
  );
  await database.query(
    `UPDATE tenant_memberships
     SET status = 'suspended'
     WHERE tenant_id = 'tenant-a' AND actor_id = 'actor-clinician-a'`,
  );
  await assert.rejects(
    service.issueLearnerDeviceSession(clinicianA, "learner-a"),
    expectPlatformError("access-denied"),
  );
});

test("device session history never hides an older active grant", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  const consent = await service.createConsentSnapshot(clinicianA, grantedConsent);
  const active = await Promise.all([
    service.issueLearnerDeviceSession(clinicianA, "learner-a", 72),
    service.issueLearnerDeviceSession(clinicianA, "learner-a", 72),
    service.issueLearnerDeviceSession(clinicianA, "learner-a", 72),
  ]);
  for (const [index, session] of active.entries()) {
    await database.query(
      `UPDATE learner_device_sessions
       SET created_at = CURRENT_TIMESTAMP - ($2 * INTERVAL '1 hour'),
           expires_at = CURRENT_TIMESTAMP + INTERVAL '24 hours'
       WHERE id = $1`,
      [session.id, index + 10],
    );
  }
  for (let index = 0; index < 30; index += 1) {
    await database.query(
      `INSERT INTO learner_device_sessions (
         id, tenant_id, learner_id, token_hash, consent_snapshot_id,
         created_by_actor_id, created_at, expires_at, revoked_at
       ) VALUES (
         $1, 'tenant-a', 'learner-a', $2, $3, 'actor-clinician-a',
         CURRENT_TIMESTAMP - ($4 * INTERVAL '1 minute'),
         CURRENT_TIMESTAMP + INTERVAL '24 hours', CURRENT_TIMESTAMP
       )`,
      [
        `history-session-${String(index).padStart(2, "0")}`,
        (index + 100).toString(16).padStart(64, "0"),
        consent.id,
        index,
      ],
    );
  }

  const visible = await service.listLearnerDeviceSessions(reviewerA, "learner-a");
  assert.equal(visible.length, 28);
  assert.equal(visible.filter((session) => session.status === "active").length, 3);
  assert.equal(visible.filter((session) => session.status === "revoked").length, 25);
  assert.deepEqual(
    visible
      .filter((session) => session.status === "active")
      .map((session) => session.id)
      .sort(),
    active.map((session) => session.id).sort(),
  );
  assert.doesNotMatch(JSON.stringify(visible), /token|[a-f0-9]{64}/i);
  const listAudit = await database.query<{
    metadata: Record<string, unknown> | string;
  }>(
    `SELECT metadata
     FROM audit_events
     WHERE action = 'learner.device-session.list.read'
       AND actor_id = 'actor-reviewer-a'
     ORDER BY occurred_at DESC
     LIMIT 1`,
  );
  const metadata =
    typeof listAudit.rows[0]?.metadata === "string"
      ? (JSON.parse(listAudit.rows[0].metadata) as Record<string, unknown>)
      : listAudit.rows[0]?.metadata;
  assert.deepEqual(metadata, {
    learner_id: "learner-a",
    inactive_history_limit: 25,
    result_count: 28,
    active_count: 3,
  });

  await Promise.all(
    active.map((session) =>
      service.revokeLearnerDeviceSession(ownerA, "learner-a", session.id),
    ),
  );
  for (const session of active) {
    assert.equal(
      await service.resolveLearnerDeviceSession(session.token),
      undefined,
    );
  }
});

test("device revocation closes every attempt that starts afterward", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const assignment = await createFoundationAssignment(service);
  const device = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  const context = await service.resolveLearnerDeviceSession(device.token);
  assert.ok(context);
  const attempt = {
    attemptId: "attempt-revocation-race",
    assignmentId: assignment.id,
    repetitionIndex: 1,
    retryIndex: 0,
    exerciseId: assignment.exerciseId,
    protocolId: assignment.protocolId,
    status: "accepted-silent" as const,
    durationMilliseconds: 900,
    sampleRateHertz: 16_000 as const,
    rmsDbfs: -20,
    peakAmplitude: 0.7,
    reasonCodes: [] as const,
  };

  const [revocation, inFlightAttempt] = await Promise.allSettled([
    service.revokeLearnerDeviceSession(ownerA, "learner-a", device.id),
    service.recordPracticeAttempt(context, attempt),
  ]);
  assert.equal(revocation.status, "fulfilled");
  if (inFlightAttempt.status === "rejected") {
    assert.ok(
      inFlightAttempt.reason instanceof PlatformDataError &&
        inFlightAttempt.reason.code === "access-denied",
    );
  }
  assert.equal(await service.resolveLearnerDeviceSession(device.token), undefined);
  await assert.rejects(
    service.recordPracticeAttempt(context, attempt),
    expectPlatformError("access-denied"),
  );
  const stored = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM practice_attempts
     WHERE id = $1`,
    [attempt.attemptId],
  );
  assert.ok((stored.rows[0]?.count ?? 0) <= 1);
});

test("device issuance is capped and rotation atomically replaces one active grant", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  const consent = await service.createConsentSnapshot(clinicianA, grantedConsent);
  const issuance = await Promise.allSettled(
    Array.from({ length: maximumActiveLearnerDeviceSessions + 1 }, () =>
      service.issueLearnerDeviceSession(clinicianA, "learner-a", 24),
    ),
  );
  const issued = issuance.flatMap((result) =>
    result.status === "fulfilled" ? [result.value] : [],
  );
  const rejected = issuance.flatMap((result) =>
    result.status === "rejected" ? [result.reason] : [],
  );
  assert.equal(issued.length, maximumActiveLearnerDeviceSessions);
  assert.equal(rejected.length, 1);
  assert.ok(
    rejected[0] instanceof PlatformDataError && rejected[0].code === "conflict",
  );
  assert.equal(
    (await service.listLearnerDeviceSessions(reviewerA, "learner-a")).filter(
      (session) => session.status === "active",
    ).length,
    maximumActiveLearnerDeviceSessions,
  );
  const initialSlots = await database.query<{ active_slot: number }>(
    `SELECT active_slot
     FROM learner_device_sessions
     WHERE tenant_id = 'tenant-a'
       AND learner_id = 'learner-a'
       AND active_slot IS NOT NULL
     ORDER BY active_slot`,
  );
  assert.deepEqual(
    initialSlots.rows.map((row) => row.active_slot),
    [1, 2, 3, 4, 5],
  );
  await assert.rejects(
    database.query(
      `INSERT INTO learner_device_sessions (
         id, tenant_id, learner_id, token_hash, consent_snapshot_id,
         created_by_actor_id, expires_at, active_slot
       ) VALUES (
         'device-slot-overflow', 'tenant-a', 'learner-a', $1, $2,
         'actor-clinician-a', CURRENT_TIMESTAMP + INTERVAL '1 hour', 1
       )`,
      ["9".repeat(64), consent.id],
    ),
    expectPostgresCode("23505"),
  );

  const source = issued[0];
  assert.ok(source);
  await assert.rejects(
    service.rotateLearnerDeviceSession(reviewerA, "learner-a", source.id, 8),
    expectPlatformError("access-denied"),
  );
  const replacement = await service.rotateLearnerDeviceSession(
    ownerA,
    "learner-a",
    source.id,
    8,
  );
  assert.equal(replacement.rotatedFromSessionId, source.id);
  assert.equal(replacement.consentSnapshotId, consent.id);
  assert.match(replacement.token, /^[A-Za-z0-9_-]{43}$/);
  assert.equal(await service.resolveLearnerDeviceSession(source.token), undefined);
  assert.deepEqual(await service.resolveLearnerDeviceSession(replacement.token), {
    sessionId: replacement.id,
    tenantId: "tenant-a",
    learnerId: "learner-a",
    consentSnapshotId: consent.id,
    audioProcessing: true,
    videoProcessing: false,
    clinicianReview: true,
    researchUse: false,
  });
  const afterRotation = await service.listLearnerDeviceSessions(
    reviewerA,
    "learner-a",
  );
  assert.equal(
    afterRotation.filter((session) => session.status === "active").length,
    maximumActiveLearnerDeviceSessions,
  );
  assert.equal(
    afterRotation.find((session) => session.id === source.id)?.status,
    "revoked",
  );
  assert.equal(
    afterRotation.find((session) => session.id === replacement.id)?.status,
    "active",
  );
  const rotatedSlots = await database.query<{ active_slot: number }>(
    `SELECT active_slot
     FROM learner_device_sessions
     WHERE tenant_id = 'tenant-a'
       AND learner_id = 'learner-a'
       AND active_slot IS NOT NULL
     ORDER BY active_slot`,
  );
  assert.deepEqual(
    rotatedSlots.rows.map((row) => row.active_slot),
    [1, 2, 3, 4, 5],
  );
  await assert.rejects(
    service.rotateLearnerDeviceSession(ownerA, "learner-a", source.id, 8),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.issueLearnerDeviceSession(ownerA, "learner-a", 24),
    expectPlatformError("conflict"),
  );

  const audits = await database.query<{
    action: string;
    metadata: Record<string, unknown> | string;
  }>(
    `SELECT action, metadata
     FROM audit_events
     WHERE action IN (
       'learner.device-session.created',
       'learner.device-session.rotated'
     )
     ORDER BY occurred_at, action`,
  );
  assert.equal(
    audits.rows.filter((row) => row.action === "learner.device-session.created")
      .length,
    maximumActiveLearnerDeviceSessions,
  );
  const issuanceMetadata = audits.rows
    .filter((row) => row.action === "learner.device-session.created")
    .map((row) =>
      typeof row.metadata === "string"
        ? (JSON.parse(row.metadata) as Record<string, unknown>)
        : row.metadata,
    );
  assert.deepEqual(
    issuanceMetadata
      .map((metadata) => metadata.active_count_after as number)
      .sort((left, right) => left - right),
    [1, 2, 3, 4, 5],
  );
  assert.ok(
    issuanceMetadata.every(
      (metadata) =>
        metadata.active_limit === maximumActiveLearnerDeviceSessions,
    ),
  );
  const rotationAudit = audits.rows.find(
    (row) => row.action === "learner.device-session.rotated",
  );
  assert.ok(rotationAudit);
  const rotationMetadata =
    typeof rotationAudit.metadata === "string"
      ? (JSON.parse(rotationAudit.metadata) as Record<string, unknown>)
      : rotationAudit.metadata;
  assert.equal(rotationMetadata.rotated_from_session_id, source.id);
  assert.equal(rotationMetadata.replacement_session_id, replacement.id);
  assert.doesNotMatch(JSON.stringify(rotationMetadata), /token|[a-f0-9]{64}/i);

  await service.revokeLearnerDeviceSession(
    ownerA,
    "learner-a",
    issued[1]?.id ?? "missing-session",
  );
  const afterRevoke = await service.issueLearnerDeviceSession(
    ownerA,
    "learner-a",
    24,
  );
  assert.ok(afterRevoke.id);
});

test("rotation rolls back the old-token revoke when replacement auditing fails", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const source = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
    24,
  );
  await database.executeScript(`
    CREATE OR REPLACE FUNCTION fail_device_rotation_audit()
    RETURNS TRIGGER AS $$
    BEGIN
      IF NEW.action = 'learner.device-session.rotated' THEN
        RAISE EXCEPTION 'forced rotation audit failure';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER fail_device_rotation_audit
    BEFORE INSERT ON audit_events
    FOR EACH ROW EXECUTE FUNCTION fail_device_rotation_audit();
  `);

  await assert.rejects(
    service.rotateLearnerDeviceSession(ownerA, "learner-a", source.id, 8),
    /forced rotation audit failure/,
  );
  assert.ok(await service.resolveLearnerDeviceSession(source.token));
  const sessions = await database.query<{
    id: string;
    revoked_at: string | null;
    active_slot: number | null;
  }>(
    `SELECT id, revoked_at, active_slot
     FROM learner_device_sessions
     WHERE tenant_id = 'tenant-a' AND learner_id = 'learner-a'`,
  );
  assert.deepEqual(sessions.rows, [
    { id: source.id, revoked_at: null, active_slot: 1 },
  ]);
});

test("token generation is learner-rate-limited without blocking revocation", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await database.query("SET TIME ZONE 'Asia/Kathmandu'");
  await assert.rejects(
    service.issueLearnerDeviceSession(reviewerA, "learner-a", 24),
    expectPlatformError("access-denied"),
  );
  const unauthorizedBuckets = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM device_access_rate_buckets`,
  );
  assert.equal(unauthorizedBuckets.rows[0]?.count, 0);
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const issued = [];
  for (let index = 0; index < maximumLearnerTokenGenerationsPerHour; index += 1) {
    try {
      issued.push(
        await service.issueLearnerDeviceSession(
          clinicianA,
          "learner-a",
          24,
        ),
      );
    } catch (error) {
      assert.ok(
        error instanceof PlatformDataError && error.code === "conflict",
      );
    }
  }
  assert.equal(issued.length, maximumActiveLearnerDeviceSessions);
  await assert.rejects(
    service.issueLearnerDeviceSession(clinicianA, "learner-a", 24),
    (error: unknown) =>
      error instanceof PlatformDataError &&
      error.code === "rate-limited" &&
      typeof error.retryAfterSeconds === "number" &&
      error.retryAfterSeconds >= 1 &&
      error.retryAfterSeconds <= 3600,
  );

  const buckets = await database.query<{
    scope_type: string;
    request_limit: number;
    accepted_count: number;
    rejected_count: number;
    last_request_allowed: boolean;
  }>(
    `SELECT scope_type, request_limit, accepted_count, rejected_count,
            last_request_allowed
     FROM device_access_rate_buckets
     WHERE tenant_id = 'tenant-a' AND operation = 'token-generation'
     ORDER BY scope_type`,
  );
  assert.deepEqual(buckets.rows, [
    {
      scope_type: "actor",
      request_limit: maximumActorTokenGenerationsPerHour,
      accepted_count: maximumLearnerTokenGenerationsPerHour + 1,
      rejected_count: 0,
      last_request_allowed: true,
    },
    {
      scope_type: "learner",
      request_limit: maximumLearnerTokenGenerationsPerHour,
      accepted_count: maximumLearnerTokenGenerationsPerHour,
      rejected_count: 1,
      last_request_allowed: false,
    },
  ]);
  const windowAlignment = await database.query<{ utc_minute: number }>(
    `SELECT DISTINCT
       EXTRACT(MINUTE FROM window_started_at AT TIME ZONE 'UTC')::INTEGER
         AS utc_minute
     FROM device_access_rate_buckets
     WHERE tenant_id = 'tenant-a' AND operation = 'token-generation'`,
  );
  assert.deepEqual(windowAlignment.rows, [{ utc_minute: 0 }]);

  const source = issued[0];
  assert.ok(source);
  await assert.rejects(
    service.rotateLearnerDeviceSession(
      clinicianA,
      "learner-a",
      source.id,
      8,
    ),
    expectPlatformError("rate-limited"),
  );
  await service.revokeLearnerDeviceSession(
    clinicianA,
    "learner-a",
    source.id,
  );
  assert.equal(await service.resolveLearnerDeviceSession(source.token), undefined);
});

test("actor token budget is enforced across learners", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await database.query(
    `INSERT INTO learners (id, tenant_id, display_label)
     VALUES
       ('learner-c', 'tenant-a', 'Learner C'),
       ('learner-d', 'tenant-a', 'Learner D'),
       ('learner-e', 'tenant-a', 'Learner E')`,
  );
  for (const learnerId of ["learner-a", "learner-c", "learner-d", "learner-e"]) {
    await service.createConsentSnapshot(clinicianA, {
      ...grantedConsent,
      learnerId,
    });
  }
  for (const learnerId of ["learner-a", "learner-c", "learner-d"]) {
    for (
      let attempt = 0;
      attempt < maximumLearnerTokenGenerationsPerHour;
      attempt += 1
    ) {
      try {
        await service.issueLearnerDeviceSession(clinicianA, learnerId, 24);
      } catch (error) {
        assert.ok(
          error instanceof PlatformDataError && error.code === "conflict",
        );
      }
    }
  }

  await assert.rejects(
    service.issueLearnerDeviceSession(clinicianA, "learner-e", 24),
    expectPlatformError("rate-limited"),
  );
  const state = await database.query<{
    scope_type: string;
    accepted_count: number;
    rejected_count: number;
    scope_count: number;
  }>(
    `SELECT scope_type,
            SUM(accepted_count)::INTEGER AS accepted_count,
            SUM(rejected_count)::INTEGER AS rejected_count,
            COUNT(*)::INTEGER AS scope_count
     FROM device_access_rate_buckets
     WHERE tenant_id = 'tenant-a' AND operation = 'token-generation'
     GROUP BY scope_type
     ORDER BY scope_type`,
  );
  assert.deepEqual(state.rows, [
    {
      scope_type: "actor",
      accepted_count: maximumActorTokenGenerationsPerHour,
      rejected_count: 1,
      scope_count: 1,
    },
    {
      scope_type: "learner",
      accepted_count: maximumActorTokenGenerationsPerHour + 1,
      rejected_count: 0,
      scope_count: 4,
    },
  ]);
  const sessions = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM learner_device_sessions`,
  );
  assert.equal(
    sessions.rows[0]?.count,
    maximumActiveLearnerDeviceSessions * 3,
  );
});

test("learner device request budgets are scoped, UTC-aligned, and deletion-bound", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const device = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  assert.ok(await service.resolveLearnerDeviceSession(device.token));
  assert.equal(
    await service.authorizeLearnerDeviceRequest(
      "x".repeat(43),
      "assignment-read",
    ),
    undefined,
  );
  const untouched = await database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM learner_device_request_rate_buckets",
  );
  assert.equal(untouched.rows[0]?.count, 0);
  await assert.rejects(
    service.authorizeLearnerDeviceRequest(device.token, "unsupported" as never),
    expectPlatformError("invalid-identifier"),
  );

  await database.query("SET TIME ZONE 'Asia/Kathmandu'");
  for (
    let request = 0;
    request < maximumAssignmentReadsPerDeviceSessionPerHour;
    request += 1
  ) {
    assert.ok(
      await service.authorizeLearnerDeviceRequest(
        device.token,
        "assignment-read",
      ),
    );
  }
  await assert.rejects(
    service.authorizeLearnerDeviceRequest(device.token, "assignment-read"),
    (error: unknown) =>
      error instanceof PlatformDataError &&
      error.code === "rate-limited" &&
      typeof error.retryAfterSeconds === "number" &&
      error.retryAfterSeconds >= 1 &&
      error.retryAfterSeconds <= 3600,
  );
  assert.ok(
    await service.authorizeLearnerDeviceRequest(
      device.token,
      "attempt-upload",
    ),
  );

  const buckets = await database.query<{
    operation: string;
    request_limit: number;
    accepted_count: number;
    rejected_count: number;
    utc_minute: number;
  }>(
    `SELECT operation, request_limit, accepted_count, rejected_count,
            EXTRACT(
              MINUTE FROM window_started_at AT TIME ZONE 'UTC'
            )::INTEGER AS utc_minute
     FROM learner_device_request_rate_buckets
     WHERE tenant_id = 'tenant-a' AND session_id = $1
     ORDER BY operation`,
    [device.id],
  );
  assert.deepEqual(buckets.rows, [
    {
      operation: "assignment-read",
      request_limit: maximumAssignmentReadsPerDeviceSessionPerHour,
      accepted_count: maximumAssignmentReadsPerDeviceSessionPerHour,
      rejected_count: 1,
      utc_minute: 0,
    },
    {
      operation: "attempt-upload",
      request_limit: maximumAttemptUploadsPerDeviceSessionPerHour,
      accepted_count: 1,
      rejected_count: 0,
      utc_minute: 0,
    },
  ]);

  const second = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  await database.query(
    `INSERT INTO learner_device_request_rate_buckets (
       tenant_id, session_id, operation, window_started_at,
       request_limit, accepted_count, rejected_count,
       last_request_id, last_request_allowed, last_requested_at
     ) VALUES (
       'tenant-a', $1, 'attempt-upload',
       date_trunc('hour', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
         AT TIME ZONE 'UTC',
       1, 1, 0, 'policy-freeze-seed', TRUE, CURRENT_TIMESTAMP
     )`,
    [second.id],
  );
  await assert.rejects(
    service.authorizeLearnerDeviceRequest(second.token, "attempt-upload"),
    expectPlatformError("rate-limited"),
  );
  const frozen = await database.query<{
    request_limit: number;
    accepted_count: number;
    rejected_count: number;
  }>(
    `SELECT request_limit, accepted_count, rejected_count
     FROM learner_device_request_rate_buckets
     WHERE tenant_id = 'tenant-a' AND session_id = $1
       AND operation = 'attempt-upload'`,
    [second.id],
  );
  assert.deepEqual(frozen.rows, [
    { request_limit: 1, accepted_count: 1, rejected_count: 1 },
  ]);

  await service.revokeLearnerDeviceSession(
    clinicianA,
    "learner-a",
    device.id,
  );
  assert.equal(
    await service.authorizeLearnerDeviceRequest(
      device.token,
      "attempt-upload",
    ),
    undefined,
  );
  await service.deleteLearner(ownerA, "learner-a");
  const deleted = await database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM learner_device_request_rate_buckets",
  );
  assert.equal(deleted.rows[0]?.count, 0);
});

test("practice assignments are immutable, tenant-scoped, consent-bound doses", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await assert.rejects(
    createFoundationAssignment(service),
    expectPlatformError("access-denied"),
  );
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const first = await createFoundationAssignment(service);
  const second = await service.createPracticeAssignment(ownerA, {
    learnerId: "learner-a",
    exerciseId: "foundation-ball-initial-b-v1",
    attemptTarget: 5,
    retryLimit: 1,
  });

  assert.equal(first.version, 1);
  assert.equal(second.version, 2);
  assert.equal(second.supersedesAssignmentId, first.id);
  assert.equal(second.attemptTarget, 5);
  assert.equal(second.retryLimit, 1);
  assert.equal(second.visualProcessing, false);
  assert.equal(second.releasePosture, "candidate-silent-only");
  assert.equal(second.exerciseRegistryVersion, "foundation-exercises-v1");
  assert.match(second.exerciseDefinitionSha256, /^[a-f0-9]{64}$/);
  assert.equal(second.consentSnapshotId, first.consentSnapshotId);

  const assignments = await service.listPracticeAssignments(reviewerA);
  assert.equal(assignments.length, 1);
  assert.equal(assignments[0]?.id, second.id);
  assert.equal(assignments[0]?.learnerDisplayLabel, "Learner A");
  await assert.rejects(
    service.createPracticeAssignment(reviewerA, {
      learnerId: "learner-a",
      exerciseId: "foundation-ball-initial-b-v1",
      attemptTarget: 5,
      retryLimit: 1,
    }),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.createPracticeAssignment(ownerA, {
      learnerId: "learner-b",
      exerciseId: "foundation-ball-initial-b-v1",
      attemptTarget: 5,
      retryLimit: 1,
    }),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    database.query(
      "UPDATE practice_assignments SET attempt_target = 6 WHERE id = $1",
      [second.id],
    ),
    /append-only/,
  );

  const device = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  const context = await service.resolveLearnerDeviceSession(device.token);
  assert.ok(context);
  assert.equal((await service.getActivePracticeAssignment(context))?.id, second.id);

  await service.createConsentSnapshot(clinicianA, grantedConsent);
  assert.equal(await service.getActivePracticeAssignment(context), undefined);
  const refreshedDevice = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  const refreshedContext = await service.resolveLearnerDeviceSession(
    refreshedDevice.token,
  );
  assert.ok(refreshedContext);
  assert.equal(await service.getActivePracticeAssignment(refreshedContext), undefined);
  const refreshed = await createFoundationAssignment(service);
  assert.equal(
    (await service.getActivePracticeAssignment(refreshedContext))?.id,
    refreshed.id,
  );
});

test("assignment progress enforces the next slot, retry stop, resume, and completion", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const assignment = await service.createPracticeAssignment(clinicianA, {
    learnerId: "learner-a",
    exerciseId: "foundation-ball-initial-b-v1",
    attemptTarget: 2,
    retryLimit: 1,
  });
  const device = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  const context = await service.resolveLearnerDeviceSession(device.token);
  assert.ok(context);

  const input = (
    attemptId: string,
    repetitionIndex: number,
    retryIndex: number,
    status: "accepted-silent" | "retry-capture" = "accepted-silent",
  ) => ({
    attemptId,
    assignmentId: assignment.id,
    repetitionIndex,
    retryIndex,
    exerciseId: assignment.exerciseId,
    protocolId: assignment.protocolId,
    status,
    durationMilliseconds: 900,
    sampleRateHertz: 16_000 as const,
    rmsDbfs: -22,
    peakAmplitude: 0.7,
    reasonCodes:
      status === "retry-capture" ? (["audio-too-quiet"] as const) : ([] as const),
  });

  assert.deepEqual((await service.getActivePracticeAssignment(context))?.progress, {
    status: "ready",
    acceptedRepetitions: 0,
    repetitionIndex: 1,
    retryIndex: 0,
  });
  await assert.rejects(
    service.recordPracticeAttempt(context, input("attempt-out-of-order", 2, 0)),
    expectPlatformError("access-denied"),
  );
  await service.recordPracticeAttempt(
    context,
    input("attempt-retry-one", 1, 0, "retry-capture"),
  );
  assert.deepEqual((await service.getActivePracticeAssignment(context))?.progress, {
    status: "ready",
    acceptedRepetitions: 0,
    repetitionIndex: 1,
    retryIndex: 1,
  });
  await assert.rejects(
    service.recordPracticeAttempt(
      context,
      input("attempt-retry-replay-new-id", 1, 0, "retry-capture"),
    ),
    expectPlatformError("access-denied"),
  );
  await service.recordPracticeAttempt(
    context,
    input("attempt-retry-two", 1, 1, "retry-capture"),
  );
  assert.deepEqual((await service.getActivePracticeAssignment(context))?.progress, {
    status: "retry-limit-reached",
    acceptedRepetitions: 0,
    repetitionIndex: 1,
  });
  await assert.rejects(
    service.recordPracticeAttempt(
      context,
      input("attempt-after-retry-limit", 1, 1),
    ),
    expectPlatformError("access-denied"),
  );

  const replacement = await service.createPracticeAssignment(clinicianA, {
    learnerId: "learner-a",
    exerciseId: "foundation-ball-initial-b-v1",
    attemptTarget: 2,
    retryLimit: 1,
  });
  const replacementInput = (attemptId: string, repetitionIndex: number) => ({
    ...input(attemptId, repetitionIndex, 0),
    assignmentId: replacement.id,
  });
  const concurrent = await Promise.allSettled([
    service.recordPracticeAttempt(
      context,
      replacementInput("attempt-concurrent-a", 1),
    ),
    service.recordPracticeAttempt(
      context,
      replacementInput("attempt-concurrent-b", 1),
    ),
  ]);
  assert.equal(
    concurrent.filter((result) => result.status === "fulfilled").length,
    1,
  );
  assert.deepEqual((await service.getActivePracticeAssignment(context))?.progress, {
    status: "ready",
    acceptedRepetitions: 1,
    repetitionIndex: 2,
    retryIndex: 0,
  });
  const finalInput = replacementInput("attempt-final-slot", 2);
  await service.recordPracticeAttempt(context, finalInput);
  assert.deepEqual((await service.getActivePracticeAssignment(context))?.progress, {
    status: "completed",
    acceptedRepetitions: 2,
  });
  const finalReplay = await service.recordPracticeAttempt(context, finalInput);
  assert.equal(finalReplay.attemptId, finalInput.attemptId);
});

test("new consent, expiry, and deletion invalidate learner device sessions", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const benignlySuperseded = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  assert.equal(
    await service.resolveLearnerDeviceSession(benignlySuperseded.token),
    undefined,
  );
  const superseded = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    audioProcessing: false,
    clinicianReview: false,
    assentStatus: "withdrawn",
  });
  assert.equal(
    await service.resolveLearnerDeviceSession(superseded.token),
    undefined,
  );

  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const expired = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  await database.query(
    `UPDATE learner_device_sessions
     SET created_at = CURRENT_TIMESTAMP - INTERVAL '2 hours',
         expires_at = CURRENT_TIMESTAMP - INTERVAL '1 hour'
     WHERE id = $1`,
    [expired.id],
  );
  assert.equal(await service.resolveLearnerDeviceSession(expired.token), undefined);

  const deleted = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  await service.deleteLearner(ownerA, "learner-a");
  assert.equal(await service.resolveLearnerDeviceSession(deleted.token), undefined);
  const remaining = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM learner_device_sessions WHERE id = $1`,
    [deleted.id],
  );
  assert.equal(remaining.rows[0]?.count, 0);
});

test("practice attempts are consent-bound, idempotent, and retain no media", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const assignment = await createFoundationAssignment(service);
  const device = await service.issueLearnerDeviceSession(clinicianA, "learner-a");
  const context = await service.resolveLearnerDeviceSession(device.token);
  assert.ok(context);
  const input = {
    attemptId: "attempt-device-001",
    assignmentId: assignment.id,
    repetitionIndex: 1,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent" as const,
    durationMilliseconds: 950,
    sampleRateHertz: 16_000 as const,
    rmsDbfs: -22.5,
    peakAmplitude: 0.72,
    reasonCodes: [] as const,
  };

  const first = await service.recordPracticeAttempt(context, input);
  const repeated = await service.recordPracticeAttempt(context, input);
  assert.deepEqual(repeated, first);
  assert.equal(first.feedbackAvailable, false);
  assert.equal(first.mediaRetained, false);
  await assert.rejects(
    service.recordPracticeAttempt(context, {
      ...input,
      attemptId: "attempt-device-slot-replay",
    }),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.recordPracticeAttempt(context, {
      ...input,
      attemptId: "attempt-device-unassigned",
      assignmentId: "assignment-unassigned",
      repetitionIndex: 2,
    }),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.recordPracticeAttempt(context, {
      ...input,
      attemptId: "attempt-device-dose-overflow",
      repetitionIndex: 21,
    }),
    expectPlatformError("invalid-identifier"),
  );
  const stored = await database.query<{
    count: number;
    media_retained: boolean;
  }>(
    `SELECT COUNT(*)::INTEGER AS count, BOOL_OR(media_retained) AS media_retained
     FROM practice_attempts WHERE id = $1
     GROUP BY id`,
    [input.attemptId],
  );
  assert.equal(stored.rows[0]?.count, 1);
  assert.equal(stored.rows[0]?.media_retained, false);
  await assert.rejects(
    database.query(
      "UPDATE practice_attempts SET duration_milliseconds = 951 WHERE id = $1",
      [input.attemptId],
    ),
    /append-only/,
  );
  const exported = await service.exportLearner(clinicianA, "learner-a");
  assert.equal(exported.practiceAttempts.length, 1);
  assert.deepEqual(exported.practiceAttempts[0], {
    attemptId: input.attemptId,
    assignmentId: assignment.id,
    repetitionIndex: 1,
    retryIndex: 0,
    deviceSessionId: device.id,
    consentSnapshotId: context.consentSnapshotId,
    exerciseId: input.exerciseId,
    protocolId: input.protocolId,
    status: input.status,
    durationMilliseconds: input.durationMilliseconds,
    sampleRateHertz: input.sampleRateHertz,
    rmsDbfs: input.rmsDbfs,
    peakAmplitude: input.peakAmplitude,
    reasonCodes: [],
    mediaRetained: false,
    receivedAt: exported.practiceAttempts[0]?.receivedAt,
  });
  assert.match(exported.practiceAttempts[0]?.receivedAt ?? "", /^\d{4}-\d{2}-\d{2}T/);

  await service.recordPracticeAttempt(context, {
    ...input,
    attemptId: "attempt-device-long-001",
    repetitionIndex: 2,
    status: "retry-capture",
    durationMilliseconds: 5_500,
    reasonCodes: ["utterance-too-long"],
  });

  await createFoundationAssignment(service);
  await assert.rejects(
    service.recordPracticeAttempt(context, {
      ...input,
      attemptId: "attempt-device-superseded-assignment",
      repetitionIndex: 3,
    }),
    expectPlatformError("access-denied"),
  );

  await assert.rejects(
    service.recordPracticeAttempt(context, {
      ...input,
      durationMilliseconds: 951,
    }),
    expectPlatformError("access-denied"),
  );
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  await assert.rejects(
    service.recordPracticeAttempt(context, input),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.recordPracticeAttempt(context, {
      ...input,
      attemptId: "attempt-device-002",
    }),
    expectPlatformError("access-denied"),
  );
  await service.deleteLearner(ownerA, "learner-a");
  const remainingAttempts = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM practice_attempts WHERE learner_id = 'learner-a'`,
  );
  assert.equal(remainingAttempts.rows[0]?.count, 0);
});

test("benchmark analyses require research consent and remain aggregate, append-only, and deletion-linked", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  const ordinaryAssignment = await createFoundationAssignment(service);
  const ordinaryDevice = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  const ordinaryContext = await service.resolveLearnerDeviceSession(
    ordinaryDevice.token,
  );
  assert.ok(ordinaryContext);
  await service.recordPracticeAttempt(ordinaryContext, {
    attemptId: "attempt-ordinary-001",
    assignmentId: ordinaryAssignment.id,
    repetitionIndex: 1,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent",
    durationMilliseconds: 950,
    sampleRateHertz: 16_000,
    rmsDbfs: -22.5,
    peakAmplitude: 0.72,
    reasonCodes: [],
  });
  const analysis = {
    attemptId: "attempt-ordinary-001",
    status: "scored-ambiguous" as const,
    releasePosture: "benchmark-only" as const,
    learnerFeedbackEligible: false as const,
    checkpointId: "onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX",
    checkpointRevision: "c69750f5043e5e1f8a71ab95dd3b98338c280c92",
    runtime: "@huggingface/transformers@4.2.0",
    modelFileSha256:
      "3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120",
    vocabularyFileSha256:
      "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0",
    lexiconVersion: "research-ball-initial-b-v1",
    calibrationVersion: "unvalidated-research-v0",
    scoringPolicyVersion: "benchmark-policy-v1",
    pCorrect: 0.3,
    pError: 0.2,
    hypothesisCoverage: 0.5,
    calibrated: false as const,
    ambiguous: true as const,
    inferenceMilliseconds: 120,
  };
  await assert.rejects(
    service.recordPracticeAttemptAnalysis(ordinaryContext, analysis),
    expectPlatformError("access-denied"),
  );

  await service.createConsentSnapshot(clinicianA, {
    ...grantedConsent,
    researchUse: true,
  });
  const researchAssignment = await createFoundationAssignment(service);
  const researchDevice = await service.issueLearnerDeviceSession(
    clinicianA,
    "learner-a",
  );
  const researchContext = await service.resolveLearnerDeviceSession(
    researchDevice.token,
  );
  assert.ok(researchContext);
  const researchAttemptId = "attempt-research-001";
  await service.recordPracticeAttempt(researchContext, {
    attemptId: researchAttemptId,
    assignmentId: researchAssignment.id,
    repetitionIndex: 1,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent",
    durationMilliseconds: 950,
    sampleRateHertz: 16_000,
    rmsDbfs: -22.5,
    peakAmplitude: 0.72,
    reasonCodes: [],
  });
  const researchAnalysis = { ...analysis, attemptId: researchAttemptId };
  assert.equal(
    await service.hasPracticeAttemptAnalysis(researchContext, researchAttemptId),
    false,
  );
  await service.recordPracticeAttemptAnalysis(researchContext, researchAnalysis);
  assert.equal(
    await service.hasPracticeAttemptAnalysis(researchContext, researchAttemptId),
    true,
  );
  await service.recordPracticeAttemptAnalysis(researchContext, researchAnalysis);
  await service.recordPracticeAttemptAnalysis(researchContext, {
    ...researchAnalysis,
    inferenceMilliseconds: 121,
  });
  await assert.rejects(
    service.recordPracticeAttemptAnalysis(researchContext, {
      ...researchAnalysis,
      pCorrect: 0.31,
    }),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    database.query(
      "UPDATE practice_attempt_analyses SET inference_milliseconds = 121 WHERE attempt_id = $1",
      [researchAttemptId],
    ),
    /append-only/,
  );

  const unavailableAttemptId = "attempt-research-unavailable";
  await service.recordPracticeAttempt(researchContext, {
    attemptId: unavailableAttemptId,
    assignmentId: researchAssignment.id,
    repetitionIndex: 2,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent",
    durationMilliseconds: 900,
    sampleRateHertz: 16_000,
    rmsDbfs: -24,
    peakAmplitude: 0.65,
    reasonCodes: [],
  });
  await service.recordPracticeAttemptAnalysis(researchContext, {
    attemptId: unavailableAttemptId,
    status: "unavailable",
    releasePosture: analysis.releasePosture,
    learnerFeedbackEligible: false,
    checkpointId: analysis.checkpointId,
    checkpointRevision: analysis.checkpointRevision,
    runtime: analysis.runtime,
    modelFileSha256: analysis.modelFileSha256,
    vocabularyFileSha256: analysis.vocabularyFileSha256,
    lexiconVersion: analysis.lexiconVersion,
    calibrationVersion: analysis.calibrationVersion,
    scoringPolicyVersion: analysis.scoringPolicyVersion,
    failureCode: "benchmark-unavailable",
    inferenceMilliseconds: 300_000,
  });

  const unsafeAttemptId = "attempt-research-unsafe";
  await service.recordPracticeAttempt(researchContext, {
    attemptId: unsafeAttemptId,
    assignmentId: researchAssignment.id,
    repetitionIndex: 3,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent",
    durationMilliseconds: 900,
    sampleRateHertz: 16_000,
    rmsDbfs: -24,
    peakAmplitude: 0.65,
    reasonCodes: [],
  });
  await assert.rejects(
    database.query(
      `INSERT INTO practice_attempt_analyses (
         attempt_id, tenant_id, learner_id, consent_snapshot_id,
         status, release_posture, learner_feedback_eligible,
         checkpoint_id, checkpoint_revision, runtime,
         model_file_sha256, vocabulary_file_sha256,
         lexicon_version, calibration_version, scoring_policy_version,
         failure_code, inference_milliseconds
       )
       SELECT
         id, tenant_id, learner_id, consent_snapshot_id,
         'unavailable', 'benchmark-only', TRUE,
         $2, $3, $4, $5, $6, $7, $8, $9,
         'benchmark-unavailable', 1
       FROM practice_attempts WHERE id = $1`,
      [
        unsafeAttemptId,
        analysis.checkpointId,
        analysis.checkpointRevision,
        analysis.runtime,
        analysis.modelFileSha256,
        analysis.vocabularyFileSha256,
        analysis.lexiconVersion,
        analysis.calibrationVersion,
        analysis.scoringPolicyVersion,
      ],
    ),
    expectPostgresCode("23514"),
  );
  const exported = await service.exportLearner(clinicianA, "learner-a");
  assert.equal(exported.practiceAttemptAnalyses.length, 2);
  assert.equal(
    exported.practiceAttemptAnalyses.find(
      (item) => item.attemptId === researchAttemptId,
    )?.checkpointRevision,
    researchAnalysis.checkpointRevision,
  );
  assert.equal(
    exported.practiceAttemptAnalyses.every(
      (item) => item.learnerFeedbackEligible === false,
    ),
    true,
  );
  assert.equal(
    exported.practiceAttemptAnalyses.find(
      (item) => item.attemptId === unavailableAttemptId,
    )?.failureCode,
    "benchmark-unavailable",
  );

  const revokedBeforeAnalysisId = "attempt-research-revoked-before-analysis";
  await service.recordPracticeAttempt(researchContext, {
    attemptId: revokedBeforeAnalysisId,
    assignmentId: researchAssignment.id,
    repetitionIndex: 4,
    retryIndex: 0,
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    status: "accepted-silent",
    durationMilliseconds: 920,
    sampleRateHertz: 16_000,
    rmsDbfs: -23,
    peakAmplitude: 0.68,
    reasonCodes: [],
  });
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  assert.equal(
    await service.hasPracticeAttemptAnalysis(researchContext, researchAttemptId),
    false,
  );
  await assert.rejects(
    service.recordPracticeAttemptAnalysis(researchContext, researchAnalysis),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.recordPracticeAttemptAnalysis(researchContext, {
      ...researchAnalysis,
      attemptId: revokedBeforeAnalysisId,
    }),
    expectPlatformError("access-denied"),
  );
  await service.deleteLearner(ownerA, "learner-a");
  const remaining = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM practice_attempt_analyses WHERE learner_id = 'learner-a'`,
  );
  assert.equal(remaining.rows[0]?.count, 0);
});

test("tenant and role boundaries fail closed without revealing foreign learners", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await assert.rejects(
    service.createConsentSnapshot(ownerA, {
      ...grantedConsent,
      learnerId: "learner-b",
    }),
    expectPlatformError("access-denied"),
  );
  await assert.rejects(
    service.createConsentSnapshot(reviewerA, grantedConsent),
    expectPlatformError("access-denied"),
  );
  const foreignSnapshots = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM consent_snapshots
     WHERE learner_id = 'learner-b'`,
  );
  assert.equal(foreignSnapshots.rows[0]?.count, 0);
});

test("authorized exports create a request receipt and privileged-read audit event", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);
  await service.createConsentSnapshot(clinicianA, grantedConsent);

  const exported = await service.exportLearner(clinicianA, "learner-a");

  assert.equal(exported.learner.id, "learner-a");
  assert.equal(exported.consentSnapshots.length, 1);
  assert.deepEqual(exported.practiceAttempts, []);
  assert.deepEqual(exported.practiceAttemptAnalyses, []);
  assert.deepEqual(exported.researchArtifactImpacts, []);
  assert.match(exported.requestId, /^[a-f0-9-]{36}$/);
  const request = await database.query<{
    status: string;
    receipt: { research_artifact_impact_count: number } | string;
  }>(
    "SELECT status, receipt FROM data_subject_requests WHERE id = $1",
    [exported.requestId],
  );
  assert.equal(request.rows[0]?.status, "completed");
  const receipt = typeof request.rows[0]?.receipt === "string"
    ? JSON.parse(request.rows[0].receipt) as { research_artifact_impact_count: number }
    : request.rows[0]?.receipt;
  assert.equal(receipt?.research_artifact_impact_count, 0);
  await assert.rejects(
    database.query(
      "UPDATE data_subject_requests SET status = 'failed' WHERE id = $1",
      [exported.requestId],
    ),
    /append-only/,
  );
  await assert.rejects(
    database.query("DELETE FROM data_subject_requests WHERE id = $1", [
      exported.requestId,
    ]),
    /append-only/,
  );
  const audit = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM audit_events
     WHERE action = 'learner.export.completed' AND resource_id = 'learner-a'`,
  );
  assert.equal(audit.rows[0]?.count, 1);
  await assert.rejects(
    service.exportLearner(reviewerA, "learner-a"),
    expectPlatformError("access-denied"),
  );
});

test("owner deletion pseudonymizes the learner while retaining consent and audit evidence", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);
  await service.createConsentSnapshot(clinicianA, grantedConsent);
  await service.issueLearnerDeviceSession(clinicianA, "learner-a");

  await assert.rejects(
    service.deleteLearner(clinicianA, "learner-a"),
    expectPlatformError("access-denied"),
  );
  const receipt = await service.deleteLearner(ownerA, "learner-a");

  assert.equal(receipt.learnerId, "learner-a");
  assert.deepEqual(receipt.retainedRecords, [
    "consent-snapshots",
    "practice-assignments",
    "audit-events",
    "artifact-lineage",
    "quarantine-evidence",
  ]);
  const learner = await database.query<{
    display_label: string;
    deleted_at: string | Date | null;
  }>(
    "SELECT display_label, deleted_at FROM learners WHERE id = 'learner-a'",
  );
  assert.equal(learner.rows[0]?.display_label, "Deleted learner");
  assert.ok(learner.rows[0]?.deleted_at);
  const retained = await database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM consent_snapshots WHERE learner_id = 'learner-a'",
  );
  assert.equal(retained.rows[0]?.count, 1);
  const learnerRateBuckets = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM device_access_rate_buckets
     WHERE scope_type = 'learner' AND scope_id = 'learner-a'`,
  );
  assert.equal(learnerRateBuckets.rows[0]?.count, 0);
  await assert.rejects(
    service.createConsentSnapshot(clinicianA, grantedConsent),
    expectPlatformError("access-denied"),
  );
  const exported = await service.exportLearner(ownerA, "learner-a");
  assert.equal(exported.learner.displayLabel, "Deleted learner");
  assert.ok(exported.learner.deletedAt);
});

test("declined assent cannot retain an enabled processing purpose", async (t) => {
  const database = await createDatabase();
  t.after(() => database.close());
  const service = new PlatformDataService(database);

  await assert.rejects(
    service.createConsentSnapshot(clinicianA, {
      ...grantedConsent,
      assentStatus: "declined",
    }),
    expectPlatformError("invalid-consent"),
  );
});

test("the PGlite adapter persists the Postgres schema to disk for local development", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-pglite-"));
  try {
    const first = new PGliteDatabase(directory);
    await applyFoundationMigration(first);
    await first.query(
      `INSERT INTO tenants (id, display_name, external_organization_hash)
       VALUES ('tenant-persist', 'Persistent Clinic', $1)`,
      ["d".repeat(64)],
    );
    await first.close();

    const reopened = new PGliteDatabase(directory);
    const result = await reopened.query<{ display_name: string }>(
      "SELECT display_name FROM tenants WHERE id = 'tenant-persist'",
    );
    assert.equal(result.rows[0]?.display_name, "Persistent Clinic");
    await reopened.close();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
