import assert from "node:assert/strict";
import test from "node:test";

import { handleTrustedEvaluation } from "../../../../lib/trusted-evaluation.ts";

const serviceToken = "test-scorer-token-that-is-at-least-32-bytes";

const validAttempt = {
  attemptId: "attempt-api-001",
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
};

function jsonRequest(body: unknown, token: string = serviceToken): Request {
  return new Request("http://localhost/api/attempts/evaluate", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

test("trusted evaluation returns a versioned decision", async () => {
  const response = await handleTrustedEvaluation(
    jsonRequest(validAttempt),
    serviceToken,
  );
  const body = (await response.json()) as {
    decision: { kind: string; protocolRegistryVersion: string };
  };

  assert.equal(response.status, 200);
  assert.equal(body.decision.kind, "correct");
  assert.equal(body.decision.protocolRegistryVersion, "foundation-v1");
});

test("trusted evaluation returns 422 only for domain validation failures", async () => {
  const response = await handleTrustedEvaluation(
    jsonRequest({ ...validAttempt, audio: { ...validAttempt.audio, pError: 2 } }),
    serviceToken,
  );
  const body = (await response.json()) as { error: string };

  assert.equal(response.status, 422);
  assert.equal(body.error, "invalid-attempt");
});

test("trusted evaluation requires JSON content", async () => {
  const response = await handleTrustedEvaluation(
    new Request("http://localhost/api/attempts/evaluate", {
      method: "POST",
      headers: { authorization: `Bearer ${serviceToken}` },
      body: "attempt-api-001",
    }),
    serviceToken,
  );

  assert.equal(response.status, 415);
});

test("trusted evaluation returns 400 for malformed JSON", async () => {
  const response = await handleTrustedEvaluation(
    new Request("http://localhost/api/attempts/evaluate", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${serviceToken}`,
      },
      body: "{",
    }),
    serviceToken,
  );

  assert.equal(response.status, 400);
});

test("trusted evaluation rejects unsupported protocols", async () => {
  const response = await handleTrustedEvaluation(
    jsonRequest({ ...validAttempt, protocolId: "unapproved-v1" }),
    serviceToken,
  );

  assert.equal(response.status, 422);
});

test("learner requests cannot assert their own clinical evidence", async () => {
  const response = await handleTrustedEvaluation(
    new Request("http://localhost/api/attempts/evaluate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(validAttempt),
    }),
    serviceToken,
  );

  assert.equal(response.status, 401);
});

test("the scorer boundary fails closed when its service token is unsafe", async () => {
  const response = await handleTrustedEvaluation(
    jsonRequest(validAttempt),
    "short",
  );

  assert.equal(response.status, 503);
});
