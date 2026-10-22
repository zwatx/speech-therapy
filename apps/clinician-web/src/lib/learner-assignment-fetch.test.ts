import assert from "node:assert/strict";
import test from "node:test";

import type {
  ActivePracticeAssignment,
  LearnerDeviceContext,
} from "@speech-therapy/platform-data";
import { PlatformDataError } from "@speech-therapy/platform-data";

import { handleLearnerAssignmentFetch } from "./learner-assignment-fetch.ts";

const token = "x".repeat(43);
const context: LearnerDeviceContext = {
  sessionId: "session-test",
  tenantId: "tenant-test",
  learnerId: "learner-test",
  consentSnapshotId: "snapshot-test",
  audioProcessing: true,
  videoProcessing: false,
  clinicianReview: false,
  researchUse: false,
};
const assignment: ActivePracticeAssignment = {
  id: "assignment-test",
  tenantId: "tenant-test",
  learnerId: "learner-test",
  version: 2,
  consentSnapshotId: "snapshot-test",
  exerciseRegistryVersion: "foundation-exercises-v1",
  exerciseDefinitionSha256: "a".repeat(64),
  exerciseId: "foundation-ball-initial-b-v1",
  protocolId: "bilabial-closure-v1",
  prompt: "ball",
  targetLabel: "Beginning /b/",
  attemptTarget: 5,
  retryLimit: 1,
  visualProcessing: false,
  releasePosture: "candidate-silent-only",
  assignedByActorId: "actor-clinician",
  assignedAt: "2026-07-10T00:00:00.000Z",
  progress: {
    status: "ready",
    acceptedRepetitions: 0,
    repetitionIndex: 1,
    retryIndex: 0,
  },
};

class FakeAssignmentService {
  activeSession = true;
  activeAssignment = true;
  authorizationError?: Error;
  receivedToken?: string;
  receivedOperation?: string;
  receivedContext?: LearnerDeviceContext;

  async authorizeLearnerDeviceRequest(
    receivedToken: string,
    operation: "assignment-read",
  ): Promise<LearnerDeviceContext | undefined> {
    if (this.authorizationError) throw this.authorizationError;
    this.receivedToken = receivedToken;
    this.receivedOperation = operation;
    return this.activeSession ? context : undefined;
  }

  async getActivePracticeAssignment(
    receivedContext: LearnerDeviceContext,
  ): Promise<ActivePracticeAssignment | undefined> {
    this.receivedContext = receivedContext;
    return this.activeAssignment ? assignment : undefined;
  }
}

function request(authorization = `CadenceDevice ${token}`): Request {
  return new Request("https://api.example.test/api/v1/learner-assignment", {
    headers: { authorization },
  });
}

test("device assignment fetch returns only bounded silent practice configuration", async () => {
  const service = new FakeAssignmentService();
  const response = await handleLearnerAssignmentFetch(request(), {
    getService: () => service,
  });
  const body = (await response.json()) as Record<string, unknown>;

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.equal(service.receivedToken, token);
  assert.equal(service.receivedOperation, "assignment-read");
  assert.deepEqual(service.receivedContext, context);
  assert.equal(body.assignmentId, assignment.id);
  assert.equal(body.attemptTarget, 5);
  assert.deepEqual(body.progress, assignment.progress);
  assert.equal(body.visualProcessingEnabled, false);
  assert.equal(body.feedbackAvailable, false);
  assert.equal(body.releasePosture, "candidate-silent-only");
  assert.equal("learnerId" in body, false);
  assert.equal("tenantId" in body, false);
  assert.equal("assignedByActorId" in body, false);
});

test("authenticated devices receive no-content when no current assignment exists", async () => {
  const service = new FakeAssignmentService();
  service.activeAssignment = false;
  const response = await handleLearnerAssignmentFetch(request(), {
    getService: () => service,
  });
  assert.equal(response.status, 204);
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.equal(await response.text(), "");
});

test("missing, malformed, and expired device sessions fail as unauthorized", async () => {
  for (const authorization of ["", "Bearer token", "CadenceDevice short"]) {
    const response = await handleLearnerAssignmentFetch(request(authorization), {
      getService: () => new FakeAssignmentService(),
    });
    assert.equal(response.status, 401);
  }
  const service = new FakeAssignmentService();
  service.activeSession = false;
  const expired = await handleLearnerAssignmentFetch(request(), {
    getService: () => service,
  });
  assert.equal(expired.status, 401);
});

test("assignment request limits return a private 429 with Retry-After", async () => {
  const service = new FakeAssignmentService();
  service.authorizationError = new PlatformDataError(
    "rate-limited",
    "This practice device has reached its hourly request limit. Try again after the current UTC hour.",
    { retryAfterSeconds: 83 },
  );
  const response = await handleLearnerAssignmentFetch(request(), {
    getService: () => service,
  });

  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), "83");
  assert.match(response.headers.get("cache-control") ?? "", /no-store/);
});
