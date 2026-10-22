import assert from "node:assert/strict";
import test from "node:test";

import type {
  ActorContext,
  LearnerSummary,
  PracticeAssignmentSummary,
  ReviewAttemptSummary,
} from "@speech-therapy/platform-data";

import { loadOverviewData, projectOverviewData } from "./overview-data.ts";

const actor: ActorContext = { actorId: "actor-owner", tenantId: "tenant-a", role: "owner" };
const learner: LearnerSummary = {
  id: "learner-a", displayLabel: "Current Learner", createdAt: "2026-09-20T12:00:00.000Z",
  attemptCount: 230, lastPracticeAt: "2026-09-22T14:30:00.000Z", activeDeviceSessionCount: 1,
  latestConsent: {
    id: "consent-current", version: 2, noticeVersion: "notice-v1", capturedAt: "2026-09-21T12:00:00.000Z",
    audioProcessing: true, videoProcessing: false, clinicianReview: true, researchUse: false,
    assentStatus: "affirmed",
  },
};
const assignment: PracticeAssignmentSummary = {
  id: "assignment-a", learnerId: learner.id, learnerDisplayLabel: learner.displayLabel,
  tenantId: actor.tenantId, version: 1, consentSnapshotId: "consent-current",
  exerciseRegistryVersion: "registry-v1", exerciseDefinitionSha256: "a".repeat(64),
  exerciseId: "assigned-exercise", protocolId: "assigned-protocol", prompt: "ball",
  targetLabel: "Beginning /b/", attemptTarget: 6, retryLimit: 1, visualProcessing: false,
  releasePosture: "candidate-silent-only", assignedByActorId: actor.actorId,
  assignedAt: "2026-09-21T12:00:00.000Z",
};
const attempt: ReviewAttemptSummary = {
  attemptId: "attempt-a", learnerId: learner.id, learnerDisplayLabel: learner.displayLabel,
  consentSnapshotId: "consent-current", consentVersion: 2, assignmentId: assignment.id,
  exerciseId: assignment.exerciseId, protocolId: assignment.protocolId,
  prompt: assignment.prompt, targetLabel: assignment.targetLabel,
  repetitionIndex: 1, retryIndex: 0, status: "accepted-silent",
  durationMilliseconds: 1200, reasonCodes: [], receivedAt: "2026-09-22T14:30:00.000Z",
};

test("empty live overview stays empty without illustrative learner or target fallback", () => {
  const data = projectOverviewData(actor, [], [assignment], [attempt]);
  assert.equal(data.mode, "live");
  assert.deepEqual(data.learners, []);
  assert.doesNotMatch(JSON.stringify(data), /Avery|Jordan|demo-learner|On track/);
});

test("current assignments and authorized review evidence produce factual summaries", () => {
  const row = projectOverviewData(actor, [learner], [assignment], [attempt]).learners[0]!;
  assert.equal(row.displayName, learner.displayLabel);
  assert.equal(row.initials, "CL");
  assert.equal(row.target, "Beginning /b/");
  assert.equal(row.phone, "/b/");
  assert.match(row.targetDetail, /“ball” · 6 repetitions · 1 retry/);
  assert.equal(row.attempts, 230);
  assert.equal(row.lastPractice, "Sep 22, 2026");
  assert.match(row.lastPracticeDetail, /2:30 PM UTC$/);
  assert.equal(row.reviewAvailable, true);
  assert.equal(row.status, "Review available");
  assert.match(row.evidence, /^1 attempt appears.*latest 100 authorized review records/);
  assert.doesNotMatch(row.status, /On track|correct|completed/i);
});

test("another learner's assignment or review record cannot populate this learner", () => {
  const row = projectOverviewData(actor, [learner], [
    { ...assignment, learnerId: "other-learner" },
  ], [{ ...attempt, learnerId: "other-learner" }]).learners[0]!;
  assert.equal(row.target, "No current assignment");
  assert.equal(row.phone, null);
  assert.equal(row.reviewAvailable, false);
  assert.doesNotMatch(row.targetDetail, /ball|Beginning \/b\//);
  assert.match(row.evidence, /not a complete practice history/);
});

test("a superseded consent snapshot never supplies a current target or review badge", () => {
  const row = projectOverviewData(actor, [learner], [
    { ...assignment, consentSnapshotId: "consent-old" },
  ], [{ ...attempt, consentSnapshotId: "consent-old" }]).learners[0]!;
  assert.equal(row.target, "No current assignment");
  assert.equal(row.phone, null);
  assert.match(row.targetDetail, /earlier consent choice/);
  assert.equal(row.reviewAvailable, false);
});

test("audio permission and assent must allow the displayed practice assignment", () => {
  for (const consent of [
    { ...learner.latestConsent!, audioProcessing: false },
    { ...learner.latestConsent!, assentStatus: "declined" as const },
    { ...learner.latestConsent!, assentStatus: "withdrawn" as const },
  ]) {
    const row = projectOverviewData(actor, [{ ...learner, latestConsent: consent }], [assignment], []).learners[0]!;
    assert.equal(row.target, "No current assignment");
    assert.equal(row.phone, null);
    assert.match(row.targetDetail, /audio consent and assent are required/);
  }
  const withoutConsent: LearnerSummary = {
    id: learner.id, displayLabel: learner.displayLabel, createdAt: learner.createdAt,
    attemptCount: 0, activeDeviceSessionCount: 0,
  };
  const row = projectOverviewData(actor, [withoutConsent], [assignment], [attempt]).learners[0]!;
  assert.equal(row.target, "No current assignment");
  assert.equal(row.reviewAvailable, false);
  assert.equal(row.lastPracticeDetail, "No practice recorded");
});

test("review permission is separate from practice totals and authorized assignments", () => {
  const row = projectOverviewData(actor, [{
    ...learner, latestConsent: { ...learner.latestConsent!, clinicianReview: false },
  }], [assignment], [attempt]).learners[0]!;
  assert.equal(row.attempts, 230);
  assert.equal(row.target, assignment.targetLabel);
  assert.equal(row.reviewAvailable, false);
  assert.match(row.evidence, /review is not enabled/);
  assert.doesNotMatch(row.evidence, /1 attempt appears/);
});

test("absence from the capped review list never means unstarted or clinically on track", () => {
  const row = projectOverviewData(actor, [learner], [assignment], []).learners[0]!;
  assert.equal(row.attempts, 230);
  assert.equal(row.status, "No review listed");
  assert.match(row.evidence, /latest 100/);
  assert.match(row.evidence, /not a complete practice history/);
  const invalidDate = projectOverviewData(actor, [{ ...learner, lastPracticeAt: "invalid" }], [], []).learners[0]!;
  assert.equal(invalidDate.lastPracticeDetail, "Date unavailable");
});

test("only owners and clinicians receive the manage-assignments presentation", () => {
  for (const role of ["owner", "clinician", "reviewer", "support"] as const) {
    const data = projectOverviewData({ ...actor, role }, [], [], []);
    assert.equal(data.canManageAssignments, role === "owner" || role === "clinician");
  }
});

test("live loading calls each tenant-authorized bulk read once with the same actor", async () => {
  const calls: string[] = [];
  const data = await loadOverviewData(actor, {
    listLearners: async (receivedActor) => { assert.equal(receivedActor, actor); calls.push("learners"); return [learner]; },
    listPracticeAssignments: async (receivedActor) => { assert.equal(receivedActor, actor); calls.push("assignments"); return [assignment]; },
    listReviewableAttempts: async (receivedActor) => { assert.equal(receivedActor, actor); calls.push("attempts"); return [attempt]; },
  });
  assert.deepEqual(calls.sort(), ["assignments", "attempts", "learners"]);
  assert.equal(data.learners.length, 1);
  const accessError = new Error("access denied");
  await assert.rejects(loadOverviewData(actor, {
    listLearners: async () => { throw accessError; },
    listPracticeAssignments: async () => [],
    listReviewableAttempts: async () => [],
  }), (error: unknown) => error === accessError);
});
