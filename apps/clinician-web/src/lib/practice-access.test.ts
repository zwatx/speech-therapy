import assert from "node:assert/strict";
import test from "node:test";

import type { LearnerConsentSummary } from "@speech-therapy/platform-data";

import { practiceAccess } from "./practice-access.ts";

const consent: LearnerConsentSummary = {
  id: "consent-1",
  version: 1,
  noticeVersion: "practice-v1",
  audioProcessing: true,
  videoProcessing: false,
  clinicianReview: true,
  researchUse: false,
  assentStatus: "affirmed",
  capturedAt: "2026-09-23T12:00:00.000Z",
};

test("practice access never calls audio-only consent ready when assent blocks device use", () => {
  assert.deepEqual(practiceAccess(undefined), {
    label: "Consent needed", className: "status-review", eligible: false,
  });
  for (const assentStatus of ["declined", "withdrawn"] as const) {
    assert.deepEqual(practiceAccess({ ...consent, assentStatus }), {
      label: "Practice paused", className: "status-review", eligible: false,
    });
  }
  assert.deepEqual(practiceAccess({ ...consent, audioProcessing: false }), {
    label: "Processing off", className: "status-not-started", eligible: false,
  });
  for (const assentStatus of ["affirmed", "not-applicable"] as const) {
    assert.deepEqual(practiceAccess({ ...consent, assentStatus }), {
      label: "Audio permitted", className: "status-neutral", eligible: true,
    });
  }
});
