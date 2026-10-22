import type { LearnerDetail } from "@speech-therapy/platform-data";
import { learnerRows } from "./demo-data";

// Only the development-only preview imports these fictional records.
export const previewLearnerRecords: readonly LearnerDetail[] = learnerRows.map((row) => {
  const retryExample = row.id === "demo-learner-02";
  const exampleReceivedAt = retryExample
    ? "2026-09-21T14:18:00.000Z"
    : row.id === "demo-learner-01"
      ? "2026-09-21T14:30:00.000Z"
      : "2026-09-19T14:30:00.000Z";
  const consent = {
    id: `${row.id}-consent-2`, version: 2, noticeVersion: "cadence-practice-notice-v1",
    capturedAt: "2026-09-20T12:00:00.000Z", audioProcessing: true,
    videoProcessing: false, clinicianReview: true, researchUse: false,
    assentStatus: "affirmed" as const,
  };
  return {
    id: row.id, displayLabel: row.displayName, createdAt: "2026-09-18T12:00:00.000Z",
    attemptCount: row.attempts, activeDeviceSessionCount: 0,
    ...(row.attempts > 0 ? { lastPracticeAt: exampleReceivedAt } : {}),
    latestConsent: consent,
    consentSnapshots: [consent, { ...consent, id: `${row.id}-consent-1`, version: 1,
      capturedAt: "2026-09-18T12:00:00.000Z", clinicianReview: false }],
    recentAttempts: (row.id === "demo-learner-01" || row.id === "demo-learner-02") ? [{
      attemptId: `${row.id}-example-attempt`, exerciseId: "foundation-ball-initial-b-v1",
      protocolId: "bilabial-closure-v1", assignmentId: `${row.id}-example-assignment`,
      prompt: "ball", targetLabel: "Beginning /b/",
      repetitionIndex: retryExample ? 2 : 1, retryIndex: retryExample ? 1 : 0,
      status: retryExample ? "retry-capture" as const : "accepted-silent" as const,
      durationMilliseconds: retryExample ? 1250 : 1420,
      reasonCodes: retryExample ? ["background-noise" as const] : [],
      receivedAt: exampleReceivedAt,
    }] : [],
  };
});
