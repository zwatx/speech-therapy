import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEvaluationReport,
  evaluationManifestSha256,
  validateLockedEvaluationManifest,
} from "./evaluation.ts";
import type {
  EvaluationSample,
  LockedEvaluationManifest,
} from "./types.ts";

const artifactVersions = {
  lexiconVersion: "lexicon-v1",
  calibrationVersion: "calibration-v1",
  scoringPolicyVersion: "scoring-v1",
} as const;

function manifestFor(testAttemptIds: readonly string[]): LockedEvaluationManifest {
  const items: LockedEvaluationManifest["items"] = [
    {
      attemptId: "attempt-train",
      speakerHash: "1".repeat(64),
      householdHash: "2".repeat(64),
      split: "train",
      targetProtocolId: "audio-only-v1",
    },
    {
      attemptId: "attempt-calibration",
      speakerHash: "3".repeat(64),
      householdHash: "4".repeat(64),
      split: "calibration",
      targetProtocolId: "audio-only-v1",
    },
    ...testAttemptIds.map((attemptId, index) => ({
      attemptId,
      speakerHash: "56789abcdef0"[index]!.repeat(64),
      householdHash: "abcdef056789"[index]!.repeat(64),
      split: "test" as const,
      targetProtocolId: "audio-only-v1",
    })),
  ];
  return {
    version: "evaluation-v1",
    sha256: evaluationManifestSha256(items),
    lockedAt: "2026-07-10T00:00:00.000Z",
    items,
  };
}

const manifest = manifestFor(["attempt-test"]);

test("locked manifests require speaker- and household-independent splits", () => {
  assert.doesNotThrow(() => validateLockedEvaluationManifest(manifest));
  assert.throws(
    () =>
      validateLockedEvaluationManifest({
        ...manifest,
        items: [
          ...manifest.items,
          {
            attemptId: "attempt-leaked",
            speakerHash: "1".repeat(64),
            householdHash: "7".repeat(64),
            split: "test",
            targetProtocolId: "audio-only-v1",
          },
        ],
      }),
    /speakerHash/,
  );
  assert.throws(
    () =>
      validateLockedEvaluationManifest({
        ...manifest,
        sha256: "0".repeat(64),
      }),
    /hash does not match/,
  );
  assert.throws(
    () =>
      validateLockedEvaluationManifest({
        ...manifest,
        items: manifest.items.map((item) =>
          item.attemptId === "attempt-test"
            ? { ...item, householdHash: "2".repeat(64) }
            : item,
        ),
      }),
    /householdHash/,
  );
});

test("manifest hashes are independent of item input order", () => {
  const items = manifestFor(["attempt-a-b", "attempt-ab"] ).items;
  assert.equal(
    evaluationManifestSha256(items),
    evaluationManifestSha256([...items].reverse()),
  );
});

function sample(
  attemptId: string,
  label: EvaluationSample["label"],
  pCorrect: number,
  pError: number,
  ambiguous: boolean,
  ageBand: string,
  latencyMilliseconds: number,
): EvaluationSample {
  return {
    attemptId,
    label,
    pCorrect,
    pError,
    ambiguous,
    latencyMilliseconds,
    estimatedCostUsd: 0.002,
    subgroup: { ageBand },
  };
}

test("evaluation reports false decisions, abstention, calibration, latency, cost, and subgroups", () => {
  const samples = [
    sample("correct-pass", "correct", 0.9, 0.05, false, "6-8", 100),
    sample("error-false-pass", "error", 0.9, 0.05, false, "6-8", 200),
    sample("correct-false-reject", "correct", 0.1, 0.8, false, "9-11", 300),
    sample("error-analyze", "error", 0.1, 0.8, false, "9-11", 400),
    sample("correct-abstain", "correct", 0.45, 0.35, true, "6-8", 500),
  ];
  const verifiedManifest = validateLockedEvaluationManifest(
    manifestFor(samples.map((item) => item.attemptId)),
  );
  const report = buildEvaluationReport(
    samples,
    { version: "threshold-v1", passThreshold: 0.85, analysisThreshold: 0.7 },
    ["ageBand"],
    verifiedManifest,
    artifactVersions,
  );

  assert.equal(report.overall.sampleCount, 5);
  assert.equal(report.overall.falsePassRate, 0.5);
  assert.equal(report.overall.falseRejectRate, 1 / 3);
  assert.equal(report.overall.abstentionRate, 0.2);
  assert.equal(report.overall.p95LatencyMilliseconds, 500);
  assert.equal(report.overall.averageCostUsd, 0.002);
  assert.ok(
    report.overall.conditionalExpectedCalibrationError !== null &&
      report.overall.conditionalExpectedCalibrationError >= 0,
  );
  assert.equal(report.manifestSha256, verifiedManifest.manifest.sha256);
  assert.equal(report.thresholdVersion, "threshold-v1");
  assert.equal(report.subgroups["ageBand=6-8"]?.sampleCount, 3);
  assert.equal(report.subgroups["ageBand=9-11"]?.sampleCount, 2);
});

test("evaluation rejects impossible evidence totals", () => {
  const verifiedManifest = validateLockedEvaluationManifest(
    manifestFor(["invalid"]),
  );
  assert.throws(
    () =>
      buildEvaluationReport(
        [sample("invalid", "correct", 0.8, 0.4, false, "6-8", 100)],
        { version: "threshold-v1", passThreshold: 0.85, analysisThreshold: 0.7 },
        [],
        verifiedManifest,
        artifactVersions,
      ),
    /invalid evidence/,
  );
});

test("unmeasured error rates are null rather than reported as zero", () => {
  const samples = [
    sample("correct-one", "correct", 0.9, 0.05, false, "6-8", 100),
    sample("correct-two", "correct", 0.4, 0.3, true, "6-8", 120),
  ];
  const report = buildEvaluationReport(
    samples,
    { version: "threshold-v1", passThreshold: 0.85, analysisThreshold: 0.7 },
    ["ageBand"],
    validateLockedEvaluationManifest(
      manifestFor(samples.map((item) => item.attemptId)),
    ),
    artifactVersions,
  );

  assert.equal(report.overall.errorCount, 0);
  assert.equal(report.overall.falsePassRate, null);
  assert.equal(report.overall.falseRejectRate, 0);
});

test("conditional ECE is not penalized by unmodeled probability mass", () => {
  const samples = [
    sample("correct-covered", "correct", 0.8, 0, false, "6-8", 100),
    sample("error-covered", "error", 0, 0.8, false, "6-8", 100),
  ];
  const report = buildEvaluationReport(
    samples,
    { version: "threshold-v1", passThreshold: 0.75, analysisThreshold: 0.75 },
    [],
    validateLockedEvaluationManifest(
      manifestFor(samples.map((item) => item.attemptId)),
    ),
    artifactVersions,
  );

  assert.equal(report.overall.conditionalExpectedCalibrationError, 0);
});

test("pass and analysis thresholds cannot select the same evidence", () => {
  const samples = [
    sample("overlap", "correct", 0.5, 0.5, false, "6-8", 100),
  ];
  assert.throws(
    () =>
      buildEvaluationReport(
        samples,
        { version: "threshold-v1", passThreshold: 0.5, analysisThreshold: 0.5 },
        [],
        validateLockedEvaluationManifest(manifestFor(["overlap"])),
        artifactVersions,
      ),
    /must not overlap/,
  );
});
