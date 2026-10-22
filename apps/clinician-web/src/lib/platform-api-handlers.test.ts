import assert from "node:assert/strict";
import test from "node:test";

import type {
  ActorContext,
  ConsentSnapshotInput,
  ConsentSnapshotRecord,
  DeletionReceipt,
  LearnerDetail,
  LearnerDeviceSessionReceipt,
  LearnerDeviceSessionRevocationReceipt,
  LearnerDeviceSessionRotationReceipt,
  LearnerDeviceSessionSummary,
  LearnerExport,
  LearnerRecord,
  LearnerSummary,
  PracticeAssignmentInput,
  PracticeAssignmentRecord,
} from "@speech-therapy/platform-data";
import { PlatformDataError } from "@speech-therapy/platform-data";

import { apiErrorResponse } from "./api-response.ts";
import {
  handleConsentPost,
  handleDeletionPost,
  handleDeviceSessionDelete,
  handleDeviceSessionList,
  handleDeviceSessionPost,
  handleDeviceSessionRotate,
  handleLearnerCreate,
  handleLearnerExport,
  handleLearnerGet,
  handleLearnerList,
  handlePracticeAssignmentPost,
  type PlatformApiDependencies,
} from "./platform-api-handlers.ts";

const actor: ActorContext = {
  actorId: "actor-test",
  tenantId: "tenant-test",
  role: "clinician",
};

class FakePlatformService {
  consentInput?: ConsentSnapshotInput;
  consentError?: Error;
  deletionCalls = 0;
  deviceSessionError?: Error;
  deviceSessionLifetime: number | undefined;
  revokedDeviceSession?: { learnerId: string; sessionId: string };
  rotatedDeviceSession?: {
    learnerId: string;
    sessionId: string;
    lifetimeHours: number | undefined;
  };
  createdLabel?: string;
  assignmentInput?: PracticeAssignmentInput;

  async createLearner(
    _actor: ActorContext,
    displayLabel: string,
  ): Promise<LearnerRecord> {
    this.createdLabel = displayLabel;
    return {
      id: "learner-created-test",
      displayLabel,
      createdAt: "2026-07-10T00:00:00.000Z",
    };
  }

  async listLearners(): Promise<readonly LearnerSummary[]> {
    return [
      {
        id: "learner-test",
        displayLabel: "Learner Test",
        createdAt: "2026-07-10T00:00:00.000Z",
        attemptCount: 0,
        activeDeviceSessionCount: 0,
      },
    ];
  }

  async getLearner(): Promise<LearnerDetail> {
    return {
      id: "learner-test",
      displayLabel: "Learner Test",
      createdAt: "2026-07-10T00:00:00.000Z",
      attemptCount: 0,
      activeDeviceSessionCount: 0,
      consentSnapshots: [],
      recentAttempts: [],
    };
  }

  async createConsentSnapshot(
    _actor: ActorContext,
    input: ConsentSnapshotInput,
  ): Promise<ConsentSnapshotRecord> {
    if (this.consentError) {
      throw this.consentError;
    }
    this.consentInput = input;
    return {
      ...input,
      id: "snapshot-test",
      tenantId: actor.tenantId,
      version: 1,
      capturedByActorId: actor.actorId,
      capturedAt: "2026-07-10T00:00:00.000Z",
    };
  }

  async exportLearner(): Promise<LearnerExport> {
    return {
      requestId: "request-export-test",
      learner: {
        id: "learner-test",
        displayLabel: "Learner Test",
        createdAt: "2026-07-10T00:00:00.000Z",
      },
      consentSnapshots: [],
      practiceAssignments: [],
      practiceAttempts: [],
      practiceAttemptAnalyses: [],
      researchArtifactImpacts: [],
    };
  }

  async deleteLearner(): Promise<DeletionReceipt> {
    this.deletionCalls += 1;
    return {
      requestId: "request-delete-test",
      learnerId: "learner-test",
      deletedAt: "2026-07-10T00:00:00.000Z",
      retainedRecords: [
        "consent-snapshots",
        "practice-assignments",
        "audit-events",
        "artifact-lineage",
        "quarantine-evidence",
      ],
    };
  }

  async issueLearnerDeviceSession(
    _actor: ActorContext,
    _learnerId: string,
    lifetimeHours?: number,
  ): Promise<LearnerDeviceSessionReceipt> {
    if (this.deviceSessionError) {
      throw this.deviceSessionError;
    }
    this.deviceSessionLifetime = lifetimeHours;
    return {
      id: "device-session-test",
      learnerId: "learner-test",
      token: "x".repeat(43),
      expiresAt: "2026-07-11T00:00:00.000Z",
      consentSnapshotId: "consent-test",
    };
  }

  async listLearnerDeviceSessions(
    _actor: ActorContext,
    learnerId: string,
  ): Promise<readonly LearnerDeviceSessionSummary[]> {
    return [
      {
        id: "device-session-test",
        learnerId,
        consentSnapshotId: "consent-test",
        consentVersion: 1,
        createdAt: "2026-07-10T00:00:00.000Z",
        expiresAt: "2026-07-11T00:00:00.000Z",
        status: "active",
      },
    ];
  }

  async revokeLearnerDeviceSession(
    _actor: ActorContext,
    learnerId: string,
    sessionId: string,
  ): Promise<LearnerDeviceSessionRevocationReceipt> {
    this.revokedDeviceSession = { learnerId, sessionId };
    return {
      id: sessionId,
      learnerId,
      revokedAt: "2026-07-10T01:00:00.000Z",
      alreadyRevoked: false,
    };
  }

  async rotateLearnerDeviceSession(
    _actor: ActorContext,
    learnerId: string,
    sessionId: string,
    lifetimeHours?: number,
  ): Promise<LearnerDeviceSessionRotationReceipt> {
    if (this.deviceSessionError) {
      throw this.deviceSessionError;
    }
    this.rotatedDeviceSession = { learnerId, sessionId, lifetimeHours };
    return {
      id: "device-session-replacement",
      learnerId,
      token: "y".repeat(43),
      expiresAt: "2026-07-11T08:00:00.000Z",
      consentSnapshotId: "consent-test",
      rotatedFromSessionId: sessionId,
      rotatedAt: "2026-07-10T01:00:00.000Z",
    };
  }

  async createPracticeAssignment(
    _actor: ActorContext,
    input: PracticeAssignmentInput,
  ): Promise<PracticeAssignmentRecord> {
    this.assignmentInput = input;
    return {
      id: "assignment-test",
      tenantId: actor.tenantId,
      learnerId: input.learnerId,
      version: 1,
      consentSnapshotId: "snapshot-test",
      exerciseRegistryVersion: "foundation-exercises-v1",
      exerciseDefinitionSha256: "a".repeat(64),
      exerciseId: input.exerciseId,
      protocolId: "bilabial-closure-v1",
      prompt: "ball",
      targetLabel: "Beginning /b/",
      attemptTarget: input.attemptTarget,
      retryLimit: input.retryLimit,
      visualProcessing: false,
      releasePosture: "candidate-silent-only",
      assignedByActorId: actor.actorId,
      assignedAt: "2026-07-10T00:00:00.000Z",
    };
  }
}

function dependencies(service = new FakePlatformService()): {
  dependencies: PlatformApiDependencies;
  service: FakePlatformService;
} {
  return {
    service,
    dependencies: {
      requireActor: async () => actor,
      getService: () => service,
    },
  };
}

function jsonRequest(body: unknown, method = "POST"): Request {
  return new Request("https://portal.example.test/api", {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const consentBody = {
  noticeVersion: "notice-v1",
  audioProcessing: true,
  videoProcessing: false,
  clinicianReview: true,
  researchUse: false,
  assentStatus: "affirmed",
};

test("learner collection handlers return tenant data and validate creation", async () => {
  const setup = dependencies();
  const listed = await handleLearnerList(setup.dependencies);
  assert.equal(listed.status, 200);
  assert.match(listed.headers.get("cache-control") ?? "", /no-store/);
  const listedBody = (await listed.json()) as { learners: LearnerSummary[] };
  assert.equal(listedBody.learners[0]?.id, "learner-test");

  const created = await handleLearnerCreate(
    jsonRequest({ displayLabel: "Avery M." }),
    setup.dependencies,
  );
  assert.equal(created.status, 201);
  assert.equal(setup.service.createdLabel, "Avery M.");

  const rejected = await handleLearnerCreate(
    jsonRequest({ displayLabel: "Avery M.", diagnosis: "not accepted" }),
    setup.dependencies,
  );
  assert.equal(rejected.status, 422);
});

test("learner detail handler returns a private clinical record", async () => {
  const response = await handleLearnerGet(
    "learner-test",
    dependencies().dependencies,
  );
  assert.equal(response.status, 200);
  const body = (await response.json()) as { learner: LearnerDetail };
  assert.equal(body.learner.displayLabel, "Learner Test");
  assert.match(response.headers.get("cache-control") ?? "", /no-store/);
});

test("assignment handler binds the route learner and accepts only the bounded shape", async () => {
  const setup = dependencies();
  const response = await handlePracticeAssignmentPost(
    jsonRequest({
      exerciseId: "foundation-ball-initial-b-v1",
      attemptTarget: 5,
      retryLimit: 1,
      planFitConfirmed: true,
    }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(response.status, 201);
  assert.deepEqual(setup.service.assignmentInput, {
    learnerId: "learner-test",
    exerciseId: "foundation-ball-initial-b-v1",
    attemptTarget: 5,
    retryLimit: 1,
  });

  const rejected = await handlePracticeAssignmentPost(
    jsonRequest({
      exerciseId: "foundation-ball-initial-b-v1",
      attemptTarget: 5,
      retryLimit: 1,
      visualProcessing: true,
    }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(rejected.status, 422);

  const unconfirmed = await handlePracticeAssignmentPost(
    jsonRequest({
      exerciseId: "foundation-ball-initial-b-v1",
      attemptTarget: 5,
      retryLimit: 1,
    }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(unconfirmed.status, 422);
});

test("consent handler authenticates and binds learner ID from the route", async () => {
  const setup = dependencies();
  const response = await handleConsentPost(
    jsonRequest(consentBody),
    "learner-test",
    setup.dependencies,
  );

  assert.equal(response.status, 201);
  assert.equal(setup.service.consentInput?.learnerId, "learner-test");
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
});

test("consent handler rejects undeclared fields", async () => {
  const response = await handleConsentPost(
    jsonRequest({ ...consentBody, caregiverName: "Do not accept PHI here" }),
    "learner-test",
    dependencies().dependencies,
  );

  assert.equal(response.status, 422);
});

test("resource handlers return 401 when the identity provider has no session", async () => {
  const setup = dependencies();
  setup.dependencies.requireActor = async () => {
    throw Object.assign(new Error("no session"), {
      code: "authentication-required",
    });
  };

  const response = await handleConsentPost(
    jsonRequest(consentBody),
    "learner-test",
    setup.dependencies,
  );

  assert.equal(response.status, 401);
});

test("request bodies are bounded before clinical parsing", async () => {
  const response = await handleConsentPost(
    new Request("https://portal.example.test/api", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ padding: "x".repeat(17_000) }),
    }),
    "learner-test",
    dependencies().dependencies,
  );

  assert.equal(response.status, 413);
});

test("declared request size is rejected before the body is read", async () => {
  const response = await handleConsentPost(
    new Request("https://portal.example.test/api", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "content-length": "20000",
      },
      body: "{}",
    }),
    "learner-test",
    dependencies().dependencies,
  );

  assert.equal(response.status, 413);
});

test("consent bodies require JSON objects", async () => {
  for (const [request, expectedStatus] of [
    [
      new Request("https://portal.example.test/api", {
        method: "POST",
        headers: { "content-type": "text/plain" },
        body: "{}",
      }),
      415,
    ],
    [
      new Request("https://portal.example.test/api", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{",
      }),
      400,
    ],
    [jsonRequest([]), 422],
    [jsonRequest("consent"), 422],
  ] as const) {
    const response = await handleConsentPost(
      request,
      "learner-test",
      dependencies().dependencies,
    );
    assert.equal(response.status, expectedStatus);
  }
});

test("concurrent consent changes return a retryable conflict", async () => {
  const setup = dependencies();
  setup.service.consentError = new PlatformDataError(
    "conflict",
    "Consent changed concurrently. Refresh and retry.",
  );

  const response = await handleConsentPost(
    jsonRequest(consentBody),
    "learner-test",
    setup.dependencies,
  );

  assert.equal(response.status, 409);
});

test("unknown primitive errors are safely redacted", () => {
  for (const error of [null, undefined, "unexpected"]) {
    const response = apiErrorResponse(error);
    assert.equal(response.status, 500);
  }
});

test("exports are private downloads", async () => {
  const response = await handleLearnerExport(
    jsonRequest({}),
    "learner-test",
    dependencies().dependencies,
  );

  assert.equal(response.status, 200);
  assert.equal(
    response.headers.get("content-disposition"),
    'attachment; filename="cadence-learner-learner-test.json"',
  );
  assert.match(response.headers.get("cache-control") ?? "", /no-store/);
});

test("exports require a preflighted JSON POST", async () => {
  const response = await handleLearnerExport(
    new Request("https://portal.example.test/api", { method: "POST" }),
    "learner-test",
    dependencies().dependencies,
  );

  assert.equal(response.status, 415);
});

test("deletion requires explicit confirmation before calling the service", async () => {
  const setup = dependencies();
  const rejected = await handleDeletionPost(
    jsonRequest({ confirmation: "DELETE" }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(rejected.status, 422);
  assert.equal(setup.service.deletionCalls, 0);

  const accepted = await handleDeletionPost(
    jsonRequest({ confirmation: "DELETE LEARNER DATA" }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(accepted.status, 200);
  assert.equal(setup.service.deletionCalls, 1);
});

test("device sessions can be issued, listed, and explicitly revoked", async () => {
  const setup = dependencies();
  const accepted = await handleDeviceSessionPost(
    jsonRequest({ lifetimeHours: 12 }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(accepted.status, 201);
  assert.equal(setup.service.deviceSessionLifetime, 12);

  const rejected = await handleDeviceSessionPost(
    jsonRequest({ lifetimeHours: 1.5 }),
    "learner-test",
    setup.dependencies,
  );
  assert.equal(rejected.status, 422);

  const listed = await handleDeviceSessionList(
    "learner-test",
    setup.dependencies,
  );
  assert.equal(listed.status, 200);
  assert.match(listed.headers.get("cache-control") ?? "", /no-store/);
  assert.equal(
    ((await listed.json()) as { sessions: readonly LearnerDeviceSessionSummary[] })
      .sessions[0]?.status,
    "active",
  );

  const missingConfirmation = await handleDeviceSessionDelete(
    jsonRequest({ confirmation: "REVOKE" }, "DELETE"),
    "learner-test",
    "device-session-test",
    setup.dependencies,
  );
  assert.equal(missingConfirmation.status, 422);
  assert.equal(setup.service.revokedDeviceSession, undefined);

  const revoked = await handleDeviceSessionDelete(
    jsonRequest({ confirmation: "REVOKE DEVICE ACCESS" }, "DELETE"),
    "learner-test",
    "device-session-test",
    setup.dependencies,
  );
  assert.equal(revoked.status, 200);
  assert.deepEqual(setup.service.revokedDeviceSession, {
    learnerId: "learner-test",
    sessionId: "device-session-test",
  });

  const invalidRotation = await handleDeviceSessionRotate(
    jsonRequest(
      { confirmation: "ROTATE", lifetimeHours: 8 },
      "POST",
    ),
    "learner-test",
    "device-session-test",
    setup.dependencies,
  );
  assert.equal(invalidRotation.status, 422);
  assert.equal(setup.service.rotatedDeviceSession, undefined);

  const rotated = await handleDeviceSessionRotate(
    jsonRequest(
      { confirmation: "ROTATE DEVICE ACCESS", lifetimeHours: 8 },
      "POST",
    ),
    "learner-test",
    "device-session-test",
    setup.dependencies,
  );
  assert.equal(rotated.status, 201);
  assert.match(rotated.headers.get("cache-control") ?? "", /no-store/);
  assert.deepEqual(setup.service.rotatedDeviceSession, {
    learnerId: "learner-test",
    sessionId: "device-session-test",
    lifetimeHours: 8,
  });
});

test("device token rate limits return a private 429 with Retry-After", async () => {
  const setup = dependencies();
  setup.service.deviceSessionError = new PlatformDataError(
    "rate-limited",
    "Hourly device-token generation limit reached. Try again after the current UTC hour.",
    { retryAfterSeconds: 117 },
  );

  const response = await handleDeviceSessionPost(
    jsonRequest({ lifetimeHours: 24 }),
    "learner-test",
    setup.dependencies,
  );

  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), "117");
  assert.match(response.headers.get("cache-control") ?? "", /no-store/);
  assert.deepEqual(await response.json(), {
    error: "rate-limited",
    message:
      "Hourly device-token generation limit reached. Try again after the current UTC hour.",
  });

  const rotationResponse = await handleDeviceSessionRotate(
    jsonRequest(
      { confirmation: "ROTATE DEVICE ACCESS", lifetimeHours: 24 },
      "POST",
    ),
    "learner-test",
    "device-session-test",
    setup.dependencies,
  );
  assert.equal(rotationResponse.status, 429);
  assert.equal(rotationResponse.headers.get("retry-after"), "117");
  assert.match(rotationResponse.headers.get("cache-control") ?? "", /no-store/);
});
