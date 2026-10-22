import { createHash } from "node:crypto";

import type {
  EvaluationManifestItem,
  EvaluationArtifactVersions,
  EvaluationMetrics,
  EvaluationReport,
  EvaluationSample,
  EvaluationThresholds,
  LockedEvaluationManifest,
} from "./types.ts";

const verifiedManifestMarker: unique symbol = Symbol("verified-evaluation-manifest");

export interface VerifiedEvaluationManifest {
  readonly manifest: LockedEvaluationManifest;
  readonly sha256: string;
  readonly testAttemptIds: ReadonlySet<string>;
  readonly [verifiedManifestMarker]: true;
}

export function evaluationManifestSha256(
  items: readonly EvaluationManifestItem[],
): string {
  const canonicalItems = [...items]
    .sort((left, right) =>
      left.attemptId < right.attemptId
        ? -1
        : left.attemptId > right.attemptId
          ? 1
          : 0,
    )
    .map((item) => ({
      attemptId: item.attemptId,
      speakerHash: item.speakerHash,
      householdHash: item.householdHash,
      split: item.split,
      targetProtocolId: item.targetProtocolId,
    }));
  return createHash("sha256").update(JSON.stringify(canonicalItems), "utf8").digest("hex");
}

function requireProbability(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new TypeError(`${label} must be a probability.`);
  }
}

function validatePartition(
  items: readonly EvaluationManifestItem[],
  key: "speakerHash" | "householdHash",
): void {
  const splitByIdentity = new Map<string, string>();
  for (const item of items) {
    const existing = splitByIdentity.get(item[key]);
    if (existing && existing !== item.split) {
      throw new TypeError(`${key} cannot appear in more than one dataset split.`);
    }
    splitByIdentity.set(item[key], item.split);
  }
}

export function validateLockedEvaluationManifest(
  manifest: LockedEvaluationManifest,
): VerifiedEvaluationManifest {
  if (
    !manifest.version ||
    !/^[a-f0-9]{64}$/.test(manifest.sha256) ||
    Number.isNaN(Date.parse(manifest.lockedAt)) ||
    manifest.items.length === 0
  ) {
    throw new TypeError("The locked evaluation manifest metadata is invalid.");
  }
  const attemptIds = new Set<string>();
  const presentSplits = new Set<string>();
  for (const item of manifest.items) {
    if (
      !item.attemptId ||
      !/^[a-f0-9]{64}$/.test(item.speakerHash) ||
      !/^[a-f0-9]{64}$/.test(item.householdHash) ||
      !item.targetProtocolId ||
      !["train", "calibration", "test"].includes(item.split) ||
      attemptIds.has(item.attemptId)
    ) {
      throw new TypeError("The evaluation manifest contains an invalid item.");
    }
    attemptIds.add(item.attemptId);
    presentSplits.add(item.split);
  }
  for (const split of ["train", "calibration", "test"]) {
    if (!presentSplits.has(split)) {
      throw new TypeError(`The evaluation manifest is missing the ${split} split.`);
    }
  }
  validatePartition(manifest.items, "speakerHash");
  validatePartition(manifest.items, "householdHash");
  if (evaluationManifestSha256(manifest.items) !== manifest.sha256) {
    throw new TypeError("The evaluation manifest hash does not match its items.");
  }
  return Object.freeze({
    manifest,
    sha256: manifest.sha256,
    testAttemptIds: new Set(
      manifest.items
        .filter((item) => item.split === "test")
        .map((item) => item.attemptId),
    ),
    [verifiedManifestMarker]: true as const,
  });
}

function percentile95(values: readonly number[]): number {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? 0;
}

function measuredRate(numerator: number, denominator: number): number | null {
  return denominator === 0 ? null : numerator / denominator;
}

function conditionalExpectedCalibrationError(
  samples: readonly EvaluationSample[],
): number | null {
  const measured = samples
    .filter((sample) => !sample.ambiguous)
    .flatMap((sample) => {
      const coveredMass = sample.pCorrect + sample.pError;
      return coveredMass === 0
        ? []
        : [{ sample, confidence: sample.pCorrect / coveredMass }];
    });
  if (measured.length === 0) return null;
  const bins = 10;
  let weightedError = 0;
  for (let bin = 0; bin < bins; bin += 1) {
    const lower = bin / bins;
    const upper = (bin + 1) / bins;
    const selected = measured.filter(
      ({ confidence }) =>
        confidence >= lower &&
        (bin === bins - 1 ? confidence <= upper : confidence < upper),
    );
    if (selected.length === 0) continue;
    const confidence =
      selected.reduce((sum, item) => sum + item.confidence, 0) /
      selected.length;
    const accuracy =
      selected.filter(({ sample }) => sample.label === "correct").length /
      selected.length;
    weightedError +=
      (selected.length / measured.length) * Math.abs(confidence - accuracy);
  }
  return weightedError;
}

function metrics(
  samples: readonly EvaluationSample[],
  thresholds: EvaluationThresholds,
): EvaluationMetrics {
  const errors = samples.filter((sample) => sample.label === "error");
  const correct = samples.filter((sample) => sample.label === "correct");
  const pass = samples.filter(
    (sample) => !sample.ambiguous && sample.pCorrect >= thresholds.passThreshold,
  );
  const analyze = samples.filter(
    (sample) =>
      !sample.ambiguous && sample.pError >= thresholds.analysisThreshold,
  );
  const decisions = new Set([...pass, ...analyze]);
  return {
    sampleCount: samples.length,
    correctCount: correct.length,
    errorCount: errors.length,
    decidedCount: decisions.size,
    falsePassRate: measuredRate(
      pass.filter((sample) => sample.label === "error").length,
      errors.length,
    ),
    falseRejectRate: measuredRate(
      analyze.filter((sample) => sample.label === "correct").length,
      correct.length,
    ),
    abstentionRate: (samples.length - decisions.size) / samples.length,
    conditionalExpectedCalibrationError:
      conditionalExpectedCalibrationError(samples),
    p95LatencyMilliseconds: percentile95(
      samples.map((sample) => sample.latencyMilliseconds),
    ),
    averageCostUsd:
      samples.reduce((sum, sample) => sum + sample.estimatedCostUsd, 0) /
      samples.length,
  };
}

export function buildEvaluationReport(
  samples: readonly EvaluationSample[],
  thresholds: EvaluationThresholds,
  subgroupKeys: readonly string[],
  verifiedManifest: VerifiedEvaluationManifest,
  artifacts: EvaluationArtifactVersions,
): EvaluationReport {
  if (!thresholds.version) throw new TypeError("A threshold version is required.");
  if (
    !artifacts.lexiconVersion ||
    !artifacts.calibrationVersion ||
    !artifacts.scoringPolicyVersion
  ) {
    throw new TypeError("Evaluation artifact versions are required.");
  }
  requireProbability(thresholds.passThreshold, "Pass threshold");
  requireProbability(thresholds.analysisThreshold, "Analysis threshold");
  if (thresholds.passThreshold + thresholds.analysisThreshold <= 1) {
    throw new TypeError("Pass and analysis thresholds must not overlap.");
  }
  if (samples.length === 0) throw new TypeError("Evaluation samples are required.");
  const sampleIds = new Set<string>();
  for (const sample of samples) {
    requireProbability(sample.pCorrect, "pCorrect");
    requireProbability(sample.pError, "pError");
    if (
      sample.pCorrect + sample.pError > 1 + 1e-9 ||
      !["correct", "error"].includes(sample.label) ||
      typeof sample.ambiguous !== "boolean" ||
      sample.latencyMilliseconds < 0 ||
      sample.estimatedCostUsd < 0 ||
      sampleIds.has(sample.attemptId) ||
      !verifiedManifest.testAttemptIds.has(sample.attemptId)
    ) {
      throw new TypeError("An evaluation sample contains invalid evidence.");
    }
    sampleIds.add(sample.attemptId);
  }
  if (sampleIds.size !== verifiedManifest.testAttemptIds.size) {
    throw new TypeError("The evaluation report must include every locked test attempt.");
  }

  const subgroups: Record<string, EvaluationMetrics> = {};
  for (const key of subgroupKeys) {
    const values = new Set(samples.map((sample) => sample.subgroup[key] ?? "unknown"));
    for (const value of values) {
      const selected = samples.filter(
        (sample) => (sample.subgroup[key] ?? "unknown") === value,
      );
      subgroups[`${key}=${value}`] = metrics(selected, thresholds);
    }
  }
  return {
    manifestSha256: verifiedManifest.sha256,
    thresholdVersion: thresholds.version,
    lexiconVersion: artifacts.lexiconVersion,
    calibrationVersion: artifacts.calibrationVersion,
    scoringPolicyVersion: artifacts.scoringPolicyVersion,
    overall: metrics(samples, thresholds),
    subgroups,
  };
}
