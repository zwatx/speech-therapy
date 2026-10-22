import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  defaultThresholdPolicy,
  targetProtocolRegistry,
  type AttemptEvaluationRequest,
} from "@speech-therapy/clinical-domain";

import type { VisualCueAnnotationBundle, VisualCueLabel } from "./annotation-types.ts";
import {
  authorizeVisualDatasetUse,
  consentEligibilitySha256,
  deletionLineageSha256,
  visualDatasetManifestSha256,
  verifyLockedVisualDatasetManifest,
} from "./dataset-manifest.ts";
import type {
  ConsentEligibilitySnapshot,
  DeletionLineageSnapshot,
  LockedVisualDatasetManifest,
  VisualDatasetManifestItem,
  VisualDatasetSplit,
} from "./dataset-types.ts";
import {
  evaluateSelectiveVisionRouting,
  prospectiveClinicalDecisionIndexSha256,
  prospectiveEvaluationRunIndexSha256,
  selectiveVisionEvaluationSampleSha256,
  selectiveVisionEvaluationPolicySha256,
  type ProspectiveEvaluationRunIndex,
  type ProspectiveClinicalDecisionIndex,
  type SelectiveVisionEvaluationPolicy,
  type SelectiveVisionEvaluationSample,
} from "./selective-routing.ts";

test("selective routing proves bypass, exact invocation, and paired utility without release claims", () => {
  const fixture = evaluationFixture();
  const report = evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    fixture.runIndex,
    fixture.policy,
    "2026-07-10T18:30:00.000Z",
  );

  assert.equal(report.status, "pass");
  assert.equal(report.routingSimulation, true);
  assert.equal(report.routing.deepVisionInvocationCount, 2);
  assert.equal(report.routing.avoidedInvocationCount, 2);
  assert.equal(report.routing.confidentCorrectVisionInvocationCount, 0);
  assert.equal(report.routing.uncertainVisionInvocationCount, 0);
  assert.equal(report.routing.eligibleMismatchInvocationRate, 1);
  assert.equal(report.routing.visualCueAccuracy, 1);
  assert.equal(report.audioOnly.falseRejectRate, 0.5);
  assert.equal(report.fused.falseRejectRate, 0);
  assert.equal(report.pairedComparison.audioOnlyWrongFusedCorrect, 1);
  assert.equal(report.pairedComparison.audioOnlyCorrectFusedWrong, 0);
  assert.equal(report.pairedComparison.netImprovementRate, 1 / 3);
  assert.equal(report.pairedComparison.exactMcNemarPValue, 1);
  assert.equal(report.releasePosture, "research-only");
  assert.equal(report.learnerFeedbackEligible, false);
  assert.equal(report.productionGateEligible, false);
});

test("evaluation artifacts require exact prospective coverage and valid hashes", () => {
  const fixture = evaluationFixture();
  const missingBase = {
    ...withoutSha(fixture.clinicalIndex),
    items: fixture.clinicalIndex.items.slice(1),
  };
  const missing = {
    ...missingBase,
    sha256: prospectiveClinicalDecisionIndexSha256(missingBase),
  };
  assert.throws(() => evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    missing,
    runIndexFor(fixture, fixture.samples, fixture.policy, missing),
    fixture.policy,
    "2026-07-10T18:30:00.000Z",
  ), /Clinical decisions must cover every prospective item exactly once/);

  assert.throws(() => evaluateSelectiveVisionRouting(
    fixture.samples.slice(1),
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    fixture.runIndex,
    fixture.policy,
    "2026-07-10T18:30:00.000Z",
  ), /Evaluation samples must cover every prospective item exactly once/);

  const tamperedPolicy = { ...fixture.policy, audioModelArtifactSha256: digest("tampered") };
  assert.throws(() => evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    fixture.runIndex,
    tamperedPolicy,
    "2026-07-10T18:30:00.000Z",
  ), /hash-bound selective vision policy/);

  const extraFieldPolicy = {
    ...fixture.policy,
    postHocOverride: true,
  } as SelectiveVisionEvaluationPolicy;
  assert.throws(() => evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    fixture.runIndex,
    extraFieldPolicy,
    "2026-07-10T18:30:00.000Z",
  ), /hash-bound selective vision policy/);

  const extraSubgroup = fixture.samples.map((sample) => ({
    ...sample,
    subgroup: { ...sample.subgroup, unapprovedDimension: "value" },
  }));
  assert.throws(() => evaluateFixture(
    fixture,
    extraSubgroup,
    runIndexFor(fixture, extraSubgroup),
  ), /invalid evidence/);

  const substituted = fixture.samples.map((sample) => sample.itemID === "prospective-0003"
    ? { ...sample, estimatedAudioCostUsd: sample.estimatedAudioCostUsd + 0.25 }
    : sample);
  assert.throws(() => evaluateFixture(fixture, substituted),
    /match the pre-bound run evidence hashes/);
});

test("route execution fails closed on skipped, bypassed, and unobservable vision", () => {
  const fixture = evaluationFixture();
  const skipped = fixture.samples.map((sample) => sample.itemID === "prospective-0003"
    ? { ...sample, visualOutcome: "not-run" as const, visualLatencyMilliseconds: 0 }
    : sample);
  assert.throws(() => evaluateFixture(
    fixture,
    skipped,
    runIndexFor(fixture, skipped),
  ), /require measured visual evidence/);

  const bypassed = fixture.samples.map((sample) => sample.itemID === "prospective-0001"
    ? { ...sample, visualOutcome: "closure-observed" as const, visualLatencyMilliseconds: 5 }
    : sample);
  assert.throws(() => evaluateFixture(
    fixture,
    bypassed,
    runIndexFor(fixture, bypassed),
  ), /Bypassed visual routes/);

  const bundles = fixture.bundles.map((bundle) => bundle.itemID === "prospective-0003"
    ? agreeingBundle(bundle.itemID, 30, "unobservable")
    : bundle);
  const unsafeFusion = fixture.samples.map((sample) => sample.itemID === "prospective-0003"
    ? { ...sample, visualOutcome: "unobservable" as const, fusedOutcome: "correct" as const }
    : sample);
  assert.throws(() => evaluateSelectiveVisionRouting(
    unsafeFusion,
    fixture.authorized,
    bundles,
    fixture.clinicalIndex,
    runIndexFor(fixture, unsafeFusion),
    fixture.policy,
    "2026-07-10T18:30:00.000Z",
  ), /must force abstention/);

  const uncertainModel = fixture.samples.map((sample) => sample.itemID === "prospective-0003"
    ? { ...sample, visualOutcome: "indeterminate" as const }
    : sample);
  assert.throws(() => evaluateFixture(
    fixture,
    uncertainModel,
    runIndexFor(fixture, uncertainModel),
  ), /must force abstention/);

  const repeated = fixture.samples.map((sample) => sample.itemID === "prospective-0003"
    ? { ...sample, visualInvocationCount: 2 }
    : sample);
  assert.throws(() => evaluateFixture(
    fixture,
    repeated,
    runIndexFor(fixture, repeated),
  ), /require measured visual evidence/);
});

test("cue safety is measured from explicit emitted actions", () => {
  const fixture = evaluationFixture();
  const falseCue = fixture.samples.map((sample) => sample.itemID === "prospective-0003"
    ? {
        ...sample,
        visualOutcome: "closure-not-observed" as const,
        fusedOutcome: "error" as const,
        fusedCue: "bilabial-closure" as const,
      }
    : sample);
  const report = evaluateFixture(
    fixture,
    falseCue,
    runIndexFor(fixture, falseCue),
  );
  assert.equal(report.routing.cueEmissionCount, 2);
  assert.equal(report.routing.falseCueCount, 1);
  assert.equal(report.routing.falseCueRate, 0.5);
  assert.equal(report.checks.find((item) => item.id === "fused-false-cue-rate")?.passed, false);
  assert.equal(report.status, "fail");

  const bypassCue = fixture.samples.map((sample) => sample.itemID === "prospective-0001"
    ? { ...sample, fusedCue: "bilabial-closure" as const }
    : sample);
  assert.throws(() => evaluateFixture(
    fixture,
    bypassCue,
    runIndexFor(fixture, bypassCue),
  ), /Bypassed visual routes/);
});

test("the shipped candidate registry cannot silently become production evidence", () => {
  const fixture = evaluationFixture();
  const base = {
    ...withoutSha(fixture.policy),
    evaluationRegistry: targetProtocolRegistry,
  };
  const candidatePolicy = {
    ...base,
    sha256: selectiveVisionEvaluationPolicySha256(base),
  };
  assert.throws(() => evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    fixture.runIndex,
    candidatePolicy,
    "2026-07-10T18:30:00.000Z",
  ), /evaluation-only registry must enable/);
  assert.equal(targetProtocolRegistry.protocols["bilabial-closure-v1"].status, "candidate");
});

test("predeclared gates fail as report checks instead of being silently relaxed", () => {
  const fixture = evaluationFixture();
  const base = {
    ...withoutSha(fixture.policy),
    thresholds: {
      ...fixture.policy.thresholds,
      minimumProspectiveSamples: 100,
      maximumMcNemarPValue: 0.05,
    },
  };
  const strictPolicy = { ...base, sha256: selectiveVisionEvaluationPolicySha256(base) };
  const report = evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    runIndexFor(fixture, fixture.samples, strictPolicy),
    strictPolicy,
    "2026-07-10T18:30:00.000Z",
  );
  assert.equal(report.status, "fail");
  assert.equal(report.researchAdvancementEligible, false);
  assert.equal(report.checks.find((item) => item.id === "prospective-sample-count")?.passed, false);
  assert.equal(report.checks.find((item) => item.id === "paired-mcnemar-significance")?.passed, false);

  const budgetBase = {
    ...withoutSha(fixture.policy),
    thresholds: {
      ...fixture.policy.thresholds,
      maximumP95VisualLatencyMilliseconds: 17,
      maximumAverageVisualCostUsdWhenRun: 0.003,
      minimumSubgroupCorrectReferences: 3,
    },
  };
  const budgetPolicy = { ...budgetBase, sha256: selectiveVisionEvaluationPolicySha256(budgetBase) };
  const budgetReport = evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    runIndexFor(fixture, fixture.samples, budgetPolicy),
    budgetPolicy,
    "2026-07-10T18:30:00.000Z",
  );
  assert.equal(budgetReport.checks.find((item) => item.id === "visual-latency-budget")?.passed, false);
  assert.equal(budgetReport.checks.find((item) => item.id === "visual-cost-budget")?.passed, false);
  assert.equal(budgetReport.checks.find(
    (item) => item.id === "subgroup-ageBand=all-correct-reference-count")?.passed, false);

  assert.throws(() => evaluateSelectiveVisionRouting(
    fixture.samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    fixture.runIndex,
    fixture.policy,
    "2026-07-10T18:19:59.999Z",
  ), /Evaluation cannot predate current dataset authorization/);
});

test("canonical hashes ignore JSON property insertion order", () => {
  const fixture = evaluationFixture();
  const policy = fixture.policy;
  const reorderedPolicy = {
    thresholds: { ...policy.thresholds },
    subgroupKeys: [...policy.subgroupKeys],
    evaluationRegistry: {
      protocols: { ...policy.evaluationRegistry.protocols },
      version: policy.evaluationRegistry.version,
    },
    routingThresholds: {
      analysisThreshold: policy.routingThresholds.analysisThreshold,
      passThreshold: policy.routingThresholds.passThreshold,
      videoQualityFloor: policy.routingThresholds.videoQualityFloor,
      audioQualityFloor: policy.routingThresholds.audioQualityFloor,
      version: policy.routingThresholds.version,
    },
    fusionPolicySha256: policy.fusionPolicySha256,
    visualModelArtifactSha256: policy.visualModelArtifactSha256,
    audioModelArtifactSha256: policy.audioModelArtifactSha256,
    clinicalDecisionPolicyVersion: policy.clinicalDecisionPolicyVersion,
    approvalEvidenceSha256: policy.approvalEvidenceSha256,
    lockedAt: policy.lockedAt,
    version: policy.version,
    schemaVersion: policy.schemaVersion,
  } satisfies Omit<SelectiveVisionEvaluationPolicy, "sha256">;
  assert.equal(selectiveVisionEvaluationPolicySha256(reorderedPolicy), policy.sha256);

  const original = fixture.samples[2]!;
  const reorderedSample: SelectiveVisionEvaluationSample = {
    subgroup: { ageBand: original.subgroup.ageBand! },
    estimatedVisualCostUsd: original.estimatedVisualCostUsd,
    estimatedAudioCostUsd: original.estimatedAudioCostUsd,
    visualLatencyMilliseconds: original.visualLatencyMilliseconds,
    audioLatencyMilliseconds: original.audioLatencyMilliseconds,
    visualOutcome: original.visualOutcome,
    visualInvocationCount: original.visualInvocationCount,
    fusedCue: original.fusedCue,
    fusedOutcome: original.fusedOutcome,
    audioOnlyOutcome: original.audioOnlyOutcome,
    attempt: {
      consent: { ...original.attempt.consent },
      audio: { ...original.attempt.audio },
      quality: { ...original.attempt.quality },
      protocolId: original.attempt.protocolId,
      attemptId: original.attempt.attemptId,
    },
    itemID: original.itemID,
  };
  assert.equal(
    selectiveVisionEvaluationSampleSha256(reorderedSample),
    selectiveVisionEvaluationSampleSha256(original),
  );
});

function evaluateFixture(
  fixture: ReturnType<typeof evaluationFixture>,
  samples: readonly SelectiveVisionEvaluationSample[],
  runIndex: ProspectiveEvaluationRunIndex = fixture.runIndex,
) {
  return evaluateSelectiveVisionRouting(
    samples,
    fixture.authorized,
    fixture.bundles,
    fixture.clinicalIndex,
    runIndex,
    fixture.policy,
    "2026-07-10T18:30:00.000Z",
  );
}

function evaluationFixture() {
  const lockedAt = "2026-07-10T18:10:00.000Z";
  const authorizedAt = "2026-07-10T18:20:00.000Z";
  const splits: readonly VisualDatasetSplit[] = [
    "train", "calibration", "test",
    "prospective-test", "prospective-test", "prospective-test", "prospective-test",
  ];
  const items = splits.map((split, index): VisualDatasetManifestItem => ({
    itemID: split === "prospective-test"
      ? `prospective-${String(index - 2).padStart(4, "0")}`
      : `foundation-${String(index + 1).padStart(4, "0")}`,
    speakerHash: digest(`speaker-${index}`),
    householdHash: digest(`household-${index}`),
    siteHash: digest(`site-${index}`),
    deletionSubjectHash: digest(`deletion-${index}`),
    consentSnapshotHash: digest(`consent-${index}`),
    consentNoticeVersion: "research-consent-v1",
    assentStatus: "affirmed",
    videoProcessing: true,
    clinicianReview: true,
    researchUse: true,
    split,
    hardwareIdentifier: index % 2 === 0 ? "iPhone17,1" : "iPad14,5",
    systemVersion: "26.2",
    capturedAt: `2026-07-10T18:0${index}:00.000Z`,
    targetWindowVersion: "bilabial-window-v1",
    annotationRequired: true,
  }));
  const lockDeletion = lineage(lockedAt);
  const lockConsent = eligibility(lockedAt, items);
  const manifestBase = {
    schemaVersion: "visual-dataset-manifest-v1" as const,
    version: "selective-routing-prospective-v1",
    lockedAt,
    cueFamily: "bilabial-closure" as const,
    labelPolicyVersion: "bilabial-closure-observation-v1" as const,
    collectionProtocolVersion: "bilabial-collection-v1",
    deletionLedgerSha256AtLock: lockDeletion.sha256,
    consentLedgerSha256AtLock: lockConsent.sha256,
    releasePosture: "research-only" as const,
    learnerFeedbackEligible: false as const,
    rawMediaIncluded: false as const,
    rawLandmarksIncluded: false as const,
    items,
  };
  const manifest: LockedVisualDatasetManifest = {
    ...manifestBase,
    sha256: visualDatasetManifestSha256(manifestBase),
  };
  const verified = verifyLockedVisualDatasetManifest(manifest, lockDeletion, lockConsent);
  const authorized = authorizeVisualDatasetUse(
    verified,
    lineage(authorizedAt),
    eligibility(authorizedAt, items),
    authorizedAt,
  );
  const labels: Record<string, VisualCueLabel> = {
    "prospective-0001": "closure-observed",
    "prospective-0002": "indeterminate",
    "prospective-0003": "closure-observed",
    "prospective-0004": "closure-not-observed",
  };
  const bundles = items.map((item, index) => agreeingBundle(
    item.itemID,
    index,
    labels[item.itemID] ?? "closure-observed",
  ));
  const registry = {
    ...targetProtocolRegistry,
    version: "bilabial-evaluation-registry-v1",
    protocols: {
      ...targetProtocolRegistry.protocols,
      "bilabial-closure-v1": {
        ...targetProtocolRegistry.protocols["bilabial-closure-v1"],
        status: "validated" as const,
      },
    },
  };
  const policyBase = {
    schemaVersion: "selective-vision-evaluation-policy-v1" as const,
    version: "selective-routing-evaluation-v1",
    lockedAt: "2026-07-10T17:30:00.000Z",
    approvalEvidenceSha256: digest("approved-statistical-analysis-plan"),
    clinicalDecisionPolicyVersion: "slp-prospective-decision-v1",
    audioModelArtifactSha256: digest("audio-model"),
    visualModelArtifactSha256: digest("visual-model"),
    fusionPolicySha256: digest("fusion-policy"),
    routingThresholds: defaultThresholdPolicy,
    evaluationRegistry: registry,
    subgroupKeys: ["ageBand"],
    thresholds: {
      minimumProspectiveSamples: 4,
      minimumCorrectReferences: 1,
      minimumErrorReferences: 1,
      minimumDistinctProspectiveSites: 2,
      minimumDistinctHardware: 2,
      minimumSubgroupSize: 1,
      minimumSubgroupCorrectReferences: 1,
      minimumSubgroupErrorReferences: 1,
      maximumDeepVisionInvocationRate: 0.5,
      minimumEligibleMismatchInvocationRate: 1,
      minimumObservableDeepSampleRate: 1,
      minimumVisualCueAccuracy: 1,
      maximumFusedFalsePassRate: 0,
      maximumFusedFalseCueRate: 0,
      minimumFusedCoverage: 1,
      maximumErrorRecallRegression: 0,
      maximumHarmfulRegressionRate: 0,
      maximumP95VisualLatencyMilliseconds: 20,
      maximumAverageVisualCostUsdWhenRun: 0.004,
      minimumPairedNetImprovementRate: 0.25,
      maximumMcNemarPValue: 1,
    },
  } satisfies Omit<SelectiveVisionEvaluationPolicy, "sha256">;
  const policy: SelectiveVisionEvaluationPolicy = {
    ...policyBase,
    sha256: selectiveVisionEvaluationPolicySha256(policyBase),
  };
  const clinicalBase = {
    schemaVersion: "prospective-clinical-decision-index-v1" as const,
    manifestSha256: manifest.sha256,
    policyVersion: policy.clinicalDecisionPolicyVersion,
    qualifiedReviewerEvidenceSha256: digest("qualified-slp-reviewers"),
    blindedToModelOutputs: true as const,
    independentlyAdjudicated: true as const,
    authorizedAt,
    items: [
      clinicalItem("prospective-0001", "pass"),
      clinicalItem("prospective-0002", "abstain"),
      clinicalItem("prospective-0003", "pass"),
      clinicalItem("prospective-0004", "analyze"),
    ],
  };
  const clinicalIndex: ProspectiveClinicalDecisionIndex = {
    ...clinicalBase,
    sha256: prospectiveClinicalDecisionIndexSha256(clinicalBase),
  };
  const samples: readonly SelectiveVisionEvaluationSample[] = [
    sample("prospective-0001", "correct", "correct", "none", "not-run", correctAttempt("prospective-0001")),
    sample("prospective-0002", "abstain", "abstain", "none", "not-run", uncertainAttempt("prospective-0002")),
    sample("prospective-0003", "error", "correct", "none", "closure-observed", mismatchAttempt("prospective-0003")),
    sample("prospective-0004", "error", "error", "bilabial-closure", "closure-not-observed", mismatchAttempt("prospective-0004")),
  ];
  const partial = { authorized, bundles, clinicalIndex, policy, samples };
  const runIndex = runIndexFor(partial, samples);
  return { ...partial, runIndex };
}

function sample(
  itemID: string,
  audioOnlyOutcome: "correct" | "error" | "abstain",
  fusedOutcome: "correct" | "error" | "abstain",
  fusedCue: "bilabial-closure" | "none",
  visualOutcome: VisualCueLabel | "not-run",
  attempt: AttemptEvaluationRequest,
): SelectiveVisionEvaluationSample {
  const ran = visualOutcome !== "not-run";
  return {
    itemID,
    attempt,
    audioOnlyOutcome,
    fusedOutcome,
    fusedCue,
    visualInvocationCount: ran ? 1 : 0,
    visualOutcome,
    audioLatencyMilliseconds: 35,
    visualLatencyMilliseconds: ran ? 18 : 0,
    estimatedAudioCostUsd: 0.001,
    estimatedVisualCostUsd: ran ? 0.004 : 0,
    subgroup: { ageBand: "all" },
  };
}

function baseAttempt(attemptId: string): AttemptEvaluationRequest {
  return {
    attemptId,
    protocolId: "bilabial-closure-v1",
    quality: { audioScore: 0.96, videoScore: 0.95, reasonCodes: [] },
    audio: { pCorrect: 0.05, pError: 0.95, calibrated: true, ambiguous: false },
    consent: {
      audioProcessing: true,
      videoProcessing: true,
      clinicianReview: true,
      researchUse: true,
    },
  };
}

function correctAttempt(attemptId: string): AttemptEvaluationRequest {
  return { ...baseAttempt(attemptId), audio: {
    pCorrect: 0.95, pError: 0.03, calibrated: true, ambiguous: false,
  } };
}

function uncertainAttempt(attemptId: string): AttemptEvaluationRequest {
  return { ...baseAttempt(attemptId), audio: {
    pCorrect: 0.45, pError: 0.5, calibrated: true, ambiguous: true,
  } };
}

function mismatchAttempt(attemptId: string): AttemptEvaluationRequest {
  return baseAttempt(attemptId);
}

function clinicalItem(itemID: string, decision: "pass" | "analyze" | "abstain") {
  return { itemID, decision, labelBundleSha256: digest(`clinical-${itemID}`) };
}

function runIndexFor(
  fixture: {
    readonly authorized: ReturnType<typeof authorizeVisualDatasetUse>;
    readonly clinicalIndex: ProspectiveClinicalDecisionIndex;
    readonly policy: SelectiveVisionEvaluationPolicy;
  },
  samples: readonly SelectiveVisionEvaluationSample[],
  policy: SelectiveVisionEvaluationPolicy = fixture.policy,
  clinicalIndex: ProspectiveClinicalDecisionIndex = fixture.clinicalIndex,
): ProspectiveEvaluationRunIndex {
  const base = {
    schemaVersion: "prospective-evaluation-run-index-v1" as const,
    manifestSha256: fixture.authorized.verifiedManifest.sha256,
    evaluationPolicySha256: policy.sha256,
    clinicalDecisionIndexSha256: clinicalIndex.sha256,
    authorizedAt: fixture.authorized.authorizedAt,
    sealedAt: "2026-07-10T18:25:00.000Z",
    captureSystemEvidenceSha256: digest("independent-capture-export"),
    independentlyExported: true as const,
    items: samples.map((item) => ({
      itemID: item.itemID,
      sampleSha256: selectiveVisionEvaluationSampleSha256(item),
    })),
  };
  return { ...base, sha256: prospectiveEvaluationRunIndexSha256(base) };
}

function lineage(asOf: string): DeletionLineageSnapshot {
  const base = {
    schemaVersion: "deletion-lineage-snapshot-v1" as const,
    version: "deletion-lineage-v1",
    asOf,
    revokedSubjectHashes: [],
  };
  return { ...base, sha256: deletionLineageSha256(base) };
}

function eligibility(
  asOf: string,
  items: readonly VisualDatasetManifestItem[],
): ConsentEligibilitySnapshot {
  const base = {
    schemaVersion: "consent-eligibility-snapshot-v1" as const,
    version: "consent-eligibility-v1",
    asOf,
    entries: items.map((item) => ({
      consentSnapshotHash: item.consentSnapshotHash,
      deletionSubjectHash: item.deletionSubjectHash,
      consentNoticeVersion: item.consentNoticeVersion,
      assentStatus: item.assentStatus,
      videoProcessing: true as const,
      clinicianReview: true as const,
      researchUse: true as const,
      capturedAt: "2026-07-10T17:00:00.000Z",
    })),
  };
  return { ...base, sha256: consentEligibilitySha256(base) };
}

function agreeingBundle(
  itemID: string,
  index: number,
  label: VisualCueLabel,
): VisualCueAnnotationBundle {
  const rating = (suffix: number, reviewerID: string) => ({
    schemaVersion: "visual-cue-annotation-v1" as const,
    annotationID: `00000000-0000-4000-8000-${String(index * 2 + suffix).padStart(12, "0")}`,
    itemID,
    cueFamily: "bilabial-closure" as const,
    labelPolicyVersion: "bilabial-closure-observation-v1" as const,
    reviewerID,
    annotatedAt: "2026-07-10T18:12:00.000Z",
    label,
    confidence: "high" as const,
    qualityReasons: label === "indeterminate"
      ? ["target-window-unclear" as const]
      : label === "unobservable"
        ? ["mouth-occluded" as const]
        : [],
    blinding: { modelOutputHidden: true as const, peerRatingsHidden: true as const },
  });
  return {
    schemaVersion: "visual-cue-adjudication-v1",
    itemID,
    labelPolicyVersion: "bilabial-closure-observation-v1",
    ratings: [rating(1, "reviewer-slp-001"), rating(2, "reviewer-slp-002")],
  };
}

function withoutSha<T extends { readonly sha256: string }>(value: T): Omit<T, "sha256"> {
  const { sha256: _sha256, ...rest } = value;
  return rest;
}

function digest(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}
