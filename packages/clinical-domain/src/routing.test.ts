import assert from "node:assert/strict";
import test from "node:test";

import {
  AttemptValidationError,
  parseAttemptEvaluationRequest,
} from "./validation.ts";
import { defaultThresholdPolicy, routeAttempt } from "./routing.ts";
import { targetProtocols } from "./protocols.ts";
import type { AttemptEvaluationRequest } from "./types.ts";

function attempt(
  overrides: Partial<AttemptEvaluationRequest> = {},
): AttemptEvaluationRequest {
  return {
    attemptId: "attempt-001",
    protocolId: "bilabial-closure-v1",
    quality: { audioScore: 0.96, videoScore: 0.93, reasonCodes: [] },
    audio: {
      pCorrect: 0.93,
      pError: 0.04,
      calibrated: true,
      ambiguous: false,
    },
    consent: {
      audioProcessing: true,
      videoProcessing: true,
      clinicianReview: true,
      researchUse: false,
    },
    ...overrides,
  };
}

function approvedProtocolRegistry() {
  return {
    version: "test-validated-v1",
    protocols: {
      ...targetProtocols,
      "bilabial-closure-v1": {
        ...targetProtocols["bilabial-closure-v1"],
        status: "validated" as const,
      },
    },
  };
}

test("confident correct attempts skip deep vision", () => {
  assert.deepEqual(routeAttempt(attempt()), {
    kind: "correct",
    runDeepVision: false,
    reason: "confident-correct",
    protocolId: "bilabial-closure-v1",
    protocolRegistryVersion: "foundation-v1",
    thresholdVersion: "foundation-v1",
    clinicianReviewPermitted: true,
    researchUsePermitted: false,
  });
});

test("poor capture requests a retry without scoring an error", () => {
  const decision = routeAttempt(
    attempt({
      quality: {
        audioScore: 0.41,
        videoScore: 0.9,
        reasonCodes: ["background-noise"],
      },
    }),
  );
  assert.equal(decision.kind, "retry-capture");
  assert.equal(decision.runDeepVision, false);
});

test("uncalibrated evidence cannot pass", () => {
  const decision = routeAttempt(
    attempt({
      audio: {
        pCorrect: 0.98,
        pError: 0.01,
        calibrated: false,
        ambiguous: false,
      },
    }),
  );
  assert.equal(decision.kind, "retry-or-abstain");
});

test("ambiguous calibrated evidence cannot pass", () => {
  const decision = routeAttempt(
    attempt({
      audio: {
        pCorrect: 0.98,
        pError: 0.01,
        calibrated: true,
        ambiguous: true,
      },
    }),
  );
  assert.equal(decision.kind, "retry-or-abstain");
});

test("audio processing consent is required before evaluation", () => {
  const decision = routeAttempt(
    attempt({
      consent: {
        audioProcessing: false,
        videoProcessing: true,
        clinicianReview: true,
        researchUse: false,
      },
    }),
  );
  assert.equal(decision.kind, "blocked-consent");
  assert.equal(decision.runDeepVision, false);
});

test("downstream consent choices are explicit on every decision", () => {
  const decision = routeAttempt(
    attempt({
      consent: {
        audioProcessing: true,
        videoProcessing: true,
        clinicianReview: false,
        researchUse: true,
      },
    }),
  );

  assert.equal(decision.clinicianReviewPermitted, false);
  assert.equal(decision.researchUsePermitted, true);
});

test("explicit audio capture blockers cannot be scored correct", () => {
  for (const reasonCode of ["audio-clipping", "multiple-speakers"] as const) {
    const decision = routeAttempt(
      attempt({
        quality: {
          audioScore: 0.98,
          videoScore: 0.92,
          reasonCodes: [reasonCode],
        },
      }),
    );
    assert.equal(decision.kind, "retry-capture");
  }
});

test("background noise relies on calibrated quality rather than a hard block", () => {
  const decision = routeAttempt(
    attempt({
      quality: {
        audioScore: 0.96,
        videoScore: 0.92,
        reasonCodes: ["background-noise"],
      },
    }),
  );
  assert.equal(decision.kind, "correct");
});

test("candidate visual protocols cannot invoke production vision", () => {
  const decision = routeAttempt(
    attempt({
      audio: {
        pCorrect: 0.08,
        pError: 0.9,
        calibrated: true,
        ambiguous: false,
        likelyError: "omission",
      },
    }),
  );
  assert.equal(decision.kind, "audio-cue-or-review");
  assert.equal(decision.reason, "visual-protocol-not-eligible");
});

test("approved confident mismatches invoke selective vision", () => {
  const decision = routeAttempt(
    attempt({
      audio: {
        pCorrect: 0.08,
        pError: 0.9,
        calibrated: true,
        ambiguous: false,
        likelyError: "omission",
      },
    }),
    defaultThresholdPolicy,
    approvedProtocolRegistry(),
  );
  assert.equal(decision.kind, "needs-deep-analysis");
  assert.equal(decision.runDeepVision, true);
  assert.equal(decision.protocolRegistryVersion, "test-validated-v1");
});

test("research and hidden-articulator targets never invoke production vision", () => {
  const registry = {
    version: "test-hidden-articulator-v1",
    protocols: {
      ...targetProtocols,
      "l-tip-lift-research-v1": {
        ...targetProtocols["l-tip-lift-research-v1"],
        status: "validated" as const,
      },
    },
  };
  const decision = routeAttempt(
    attempt({
      protocolId: "l-tip-lift-research-v1",
      audio: {
        pCorrect: 0.05,
        pError: 0.92,
        calibrated: true,
        ambiguous: false,
      },
    }),
    defaultThresholdPolicy,
    registry,
  );
  assert.equal(decision.kind, "audio-cue-or-review");
  assert.equal(decision.reason, "visual-protocol-not-eligible");
});

test("poor video evidence degrades to non-visual feedback", () => {
  const decision = routeAttempt(
    attempt({
      audio: {
        pCorrect: 0.05,
        pError: 0.92,
        calibrated: true,
        ambiguous: false,
      },
      quality: {
        audioScore: 0.96,
        videoScore: 0.95,
        reasonCodes: ["mouth-occluded"],
      },
    }),
    defaultThresholdPolicy,
    approvedProtocolRegistry(),
  );
  assert.equal(decision.kind, "audio-cue-or-review");
  assert.equal(decision.reason, "video-quality-below-floor");
  assert.equal(decision.runDeepVision, false);
});

test("video consent is required before deep analysis", () => {
  const decision = routeAttempt(
    attempt({
      audio: {
        pCorrect: 0.05,
        pError: 0.92,
        calibrated: true,
        ambiguous: false,
      },
      consent: {
        audioProcessing: true,
        videoProcessing: false,
        clinicianReview: true,
        researchUse: false,
      },
    }),
    defaultThresholdPolicy,
    approvedProtocolRegistry(),
  );
  assert.equal(decision.kind, "audio-cue-or-review");
  assert.equal(decision.reason, "video-processing-not-consented");
});

test("request parsing rejects out-of-range evidence", () => {
  assert.throws(
    () =>
      parseAttemptEvaluationRequest({
        ...attempt(),
        audio: { ...attempt().audio, pCorrect: 1.2 },
      }),
    AttemptValidationError,
  );
});

test("request parsing rejects impossible probability totals", () => {
  assert.throws(
    () =>
      parseAttemptEvaluationRequest({
        ...attempt(),
        audio: { ...attempt().audio, pCorrect: 0.8, pError: 0.4 },
      }),
    /cannot sum to more than 1/,
  );
});

test("request parsing rejects non-string likely errors", () => {
  assert.throws(
    () =>
      parseAttemptEvaluationRequest({
        ...attempt(),
        audio: { ...attempt().audio, likelyError: ["omission"] },
      }),
    /likelyError is not supported/,
  );
});

test("request parsing rejects contradictory video evidence", () => {
  assert.throws(
    () =>
      parseAttemptEvaluationRequest({
        ...attempt(),
        quality: {
          audioScore: 0.9,
          videoScore: 0.9,
          reasonCodes: ["video-unavailable"],
        },
      }),
    /videoScore cannot be provided/,
  );
});

test("request parsing rejects duplicate capture reasons", () => {
  assert.throws(
    () =>
      parseAttemptEvaluationRequest({
        ...attempt(),
        quality: {
          audioScore: 0.9,
          reasonCodes: ["background-noise", "background-noise"],
        },
      }),
    /cannot contain duplicates/,
  );
});

test("request parsing rejects undeclared contract fields", () => {
  assert.throws(
    () =>
      parseAttemptEvaluationRequest({
        ...attempt(),
        learnerName: "Patient Name",
      }),
    /unsupported fields/,
  );
});

test("request parsing requires an opaque attempt token", () => {
  assert.throws(
    () => parseAttemptEvaluationRequest({ ...attempt(), attemptId: "Avery May" }),
    /opaque token/,
  );
});

test("no shipped protocol is production-validated", () => {
  for (const protocol of Object.values(targetProtocols)) {
    assert.notEqual(protocol.status, "validated");
  }
});

test("no shipped protocol can invoke deep vision", () => {
  for (const protocolId of Object.keys(targetProtocols) as Array<
    keyof typeof targetProtocols
  >) {
    const decision = routeAttempt(
      attempt({
        protocolId,
        audio: {
          pCorrect: 0.05,
          pError: 0.92,
          calibrated: true,
          ambiguous: false,
        },
      }),
    );
    assert.equal(decision.runDeepVision, false, protocolId);
  }
});
