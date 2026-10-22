import { createHash } from "node:crypto";

import {
  parseAttemptEvaluationRequest,
  routeAttempt,
  type AttemptEvaluationRequest,
  type TargetProtocolRegistry,
  type ThresholdPolicy,
} from "@speech-therapy/clinical-domain";

import type { VisualCueAnnotationBundle, VisualCueLabel } from "./annotation-types.ts";
import {
  assertAuthorizedVisualDataset,
  bindVisualAnnotationsToDataset,
  visualDatasetAnnotationIndexSha256,
  type AuthorizedVisualDataset,
} from "./dataset-manifest.ts";
import type { VisualDatasetAnnotationIndex } from "./dataset-types.ts";

export type ClinicalDecisionOutcome = "correct" | "error" | "abstain";
export type ProspectiveClinicalDecision = "pass" | "analyze" | "abstain";
export type FusedCueAction = "bilabial-closure" | "none";

export interface ProspectiveClinicalDecisionIndex {
  readonly schemaVersion: "prospective-clinical-decision-index-v1";
  readonly manifestSha256: string;
  readonly policyVersion: string;
  readonly qualifiedReviewerEvidenceSha256: string;
  readonly blindedToModelOutputs: true;
  readonly independentlyAdjudicated: true;
  readonly authorizedAt: string;
  readonly items: readonly {
    readonly itemID: string;
    readonly decision: ProspectiveClinicalDecision;
    readonly labelBundleSha256: string;
  }[];
  readonly sha256: string;
}

export interface SelectiveVisionEvaluationSample {
  readonly itemID: string;
  readonly attempt: AttemptEvaluationRequest;
  readonly audioOnlyOutcome: ClinicalDecisionOutcome;
  readonly fusedOutcome: ClinicalDecisionOutcome;
  readonly fusedCue: FusedCueAction;
  readonly visualInvocationCount: number;
  readonly visualOutcome: VisualCueLabel | "not-run";
  readonly audioLatencyMilliseconds: number;
  readonly visualLatencyMilliseconds: number;
  readonly estimatedAudioCostUsd: number;
  readonly estimatedVisualCostUsd: number;
  readonly subgroup: Readonly<Record<string, string>>;
}

export interface ProspectiveEvaluationRunIndex {
  readonly schemaVersion: "prospective-evaluation-run-index-v1";
  readonly manifestSha256: string;
  readonly evaluationPolicySha256: string;
  readonly clinicalDecisionIndexSha256: string;
  readonly authorizedAt: string;
  readonly sealedAt: string;
  readonly captureSystemEvidenceSha256: string;
  readonly independentlyExported: true;
  readonly items: readonly {
    readonly itemID: string;
    readonly sampleSha256: string;
  }[];
  readonly sha256: string;
}

export interface SelectiveVisionEvaluationThresholds {
  readonly minimumProspectiveSamples: number;
  readonly minimumCorrectReferences: number;
  readonly minimumErrorReferences: number;
  readonly minimumDistinctProspectiveSites: number;
  readonly minimumDistinctHardware: number;
  readonly minimumSubgroupSize: number;
  readonly minimumSubgroupCorrectReferences: number;
  readonly minimumSubgroupErrorReferences: number;
  readonly maximumDeepVisionInvocationRate: number;
  readonly minimumEligibleMismatchInvocationRate: number;
  readonly minimumObservableDeepSampleRate: number;
  readonly minimumVisualCueAccuracy: number;
  readonly maximumFusedFalsePassRate: number;
  readonly maximumFusedFalseCueRate: number;
  readonly minimumFusedCoverage: number;
  readonly maximumErrorRecallRegression: number;
  readonly maximumHarmfulRegressionRate: number;
  readonly maximumP95VisualLatencyMilliseconds: number;
  readonly maximumAverageVisualCostUsdWhenRun: number;
  readonly minimumPairedNetImprovementRate: number;
  readonly maximumMcNemarPValue: number;
}

export const recommendedSelectiveVisionEvaluationThresholds:
SelectiveVisionEvaluationThresholds = {
  minimumProspectiveSamples: 100,
  minimumCorrectReferences: 30,
  minimumErrorReferences: 30,
  minimumDistinctProspectiveSites: 2,
  minimumDistinctHardware: 2,
  minimumSubgroupSize: 20,
  minimumSubgroupCorrectReferences: 5,
  minimumSubgroupErrorReferences: 5,
  maximumDeepVisionInvocationRate: 0.4,
  minimumEligibleMismatchInvocationRate: 1,
  minimumObservableDeepSampleRate: 0.8,
  minimumVisualCueAccuracy: 0.85,
  maximumFusedFalsePassRate: 0.05,
  maximumFusedFalseCueRate: 0.05,
  minimumFusedCoverage: 0.8,
  maximumErrorRecallRegression: 0,
  maximumHarmfulRegressionRate: 0,
  maximumP95VisualLatencyMilliseconds: 250,
  maximumAverageVisualCostUsdWhenRun: 0.01,
  minimumPairedNetImprovementRate: 0.05,
  maximumMcNemarPValue: 0.05,
};

export interface SelectiveVisionEvaluationPolicy {
  readonly schemaVersion: "selective-vision-evaluation-policy-v1";
  readonly version: string;
  readonly lockedAt: string;
  readonly approvalEvidenceSha256: string;
  readonly clinicalDecisionPolicyVersion: string;
  readonly audioModelArtifactSha256: string;
  readonly visualModelArtifactSha256: string;
  readonly fusionPolicySha256: string;
  readonly routingThresholds: ThresholdPolicy;
  readonly evaluationRegistry: TargetProtocolRegistry;
  readonly subgroupKeys: readonly string[];
  readonly thresholds: SelectiveVisionEvaluationThresholds;
  readonly sha256: string;
}

export interface SelectiveVisionDecisionMetrics {
  readonly sampleCount: number;
  readonly referenceAbstainCount: number;
  readonly decidedCount: number;
  readonly correctReferenceCount: number;
  readonly errorReferenceCount: number;
  readonly coverage: number;
  readonly accuracy: number | null;
  readonly falsePassRate: number | null;
  readonly falseRejectRate: number | null;
  readonly errorRecall: number | null;
  readonly abstentionRate: number;
}

export interface SelectiveVisionRoutingMetrics {
  readonly deepVisionInvocationCount: number;
  readonly deepVisionInvocationRate: number;
  readonly confidentCorrectCount: number;
  readonly confidentCorrectVisionInvocationCount: number;
  readonly uncertainCount: number;
  readonly uncertainVisionInvocationCount: number;
  readonly eligibleMismatchCount: number;
  readonly eligibleMismatchInvocationRate: number | null;
  readonly observableDeepSampleRate: number | null;
  readonly visualCueAccuracy: number | null;
  readonly falseCueRate: number | null;
  readonly cueEmissionCount: number;
  readonly falseCueCount: number;
  readonly harmfulRegressionCount: number;
  readonly harmfulRegressionRate: number;
  readonly avoidedInvocationCount: number;
  readonly avoidedInvocationRate: number | null;
  readonly averageAudioLatencyMilliseconds: number;
  readonly averageVisualLatencyMillisecondsWhenRun: number | null;
  readonly p95VisualLatencyMilliseconds: number | null;
  readonly averageAudioCostUsd: number;
  readonly averageVisualCostUsdWhenRun: number | null;
  readonly totalEstimatedCostUsd: number;
}

export interface SelectiveVisionSubgroupMetrics {
  readonly sampleCount: number;
  readonly routing: Pick<
    SelectiveVisionRoutingMetrics,
    "deepVisionInvocationRate" | "harmfulRegressionRate" | "falseCueRate"
  >;
  readonly audioOnly: SelectiveVisionDecisionMetrics;
  readonly fused: SelectiveVisionDecisionMetrics;
}

export interface SelectiveVisionEvaluationCheck {
  readonly id: string;
  readonly passed: boolean;
  readonly measured: number | string;
  readonly required: number | string;
}

export interface SelectiveVisionEvaluationReport {
  readonly schemaVersion: "selective-vision-evaluation-report-v1";
  readonly evaluationPolicyVersion: string;
  readonly evaluationPolicySha256: string;
  readonly evaluationPolicyLockedAt: string;
  readonly routingThresholdVersion: string;
  readonly protocolRegistryVersion: string;
  readonly routingSimulation: true;
  readonly manifestSha256: string;
  readonly annotationIndexSha256: string;
  readonly clinicalDecisionIndexSha256: string;
  readonly evaluationRunIndexSha256: string;
  readonly evaluationRunSealedAt: string;
  readonly authorizedAt: string;
  readonly evaluatedAt: string;
  readonly sampleEvidenceSha256: string;
  readonly routing: SelectiveVisionRoutingMetrics;
  readonly audioOnly: SelectiveVisionDecisionMetrics;
  readonly fused: SelectiveVisionDecisionMetrics;
  readonly errorRecallDelta: number | null;
  readonly pairedComparison: {
    readonly binaryReferenceCount: number;
    readonly audioOnlyCorrectFusedWrong: number;
    readonly audioOnlyWrongFusedCorrect: number;
    readonly netImprovementRate: number;
    readonly exactMcNemarPValue: number;
  };
  readonly subgroups: Readonly<Record<string, SelectiveVisionSubgroupMetrics>>;
  readonly checks: readonly SelectiveVisionEvaluationCheck[];
  readonly status: "pass" | "fail";
  readonly researchAdvancementEligible: boolean;
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly productionGateEligible: false;
  readonly limitations: readonly string[];
}

const sampleKeys = [
  "itemID", "attempt", "audioOnlyOutcome", "fusedOutcome", "fusedCue",
  "visualInvocationCount", "visualOutcome",
  "audioLatencyMilliseconds", "visualLatencyMilliseconds", "estimatedAudioCostUsd",
  "estimatedVisualCostUsd", "subgroup",
] as const;
const policyKeys = [
  "schemaVersion", "version", "lockedAt", "approvalEvidenceSha256",
  "clinicalDecisionPolicyVersion", "audioModelArtifactSha256",
  "visualModelArtifactSha256", "fusionPolicySha256", "routingThresholds",
  "evaluationRegistry", "subgroupKeys", "thresholds", "sha256",
] as const;
const thresholdKeys = [
  "minimumProspectiveSamples", "minimumCorrectReferences", "minimumErrorReferences",
  "minimumDistinctProspectiveSites", "minimumDistinctHardware", "minimumSubgroupSize",
  "minimumSubgroupCorrectReferences", "minimumSubgroupErrorReferences",
  "maximumDeepVisionInvocationRate", "minimumEligibleMismatchInvocationRate",
  "minimumObservableDeepSampleRate", "minimumVisualCueAccuracy",
  "maximumFusedFalsePassRate", "maximumFusedFalseCueRate", "minimumFusedCoverage",
  "maximumErrorRecallRegression", "maximumHarmfulRegressionRate",
  "maximumP95VisualLatencyMilliseconds", "maximumAverageVisualCostUsdWhenRun",
  "minimumPairedNetImprovementRate", "maximumMcNemarPValue",
] as const;

export function prospectiveClinicalDecisionIndexSha256(
  index: Omit<ProspectiveClinicalDecisionIndex, "sha256">,
): string {
  return digest({
    schemaVersion: index.schemaVersion,
    manifestSha256: index.manifestSha256,
    policyVersion: index.policyVersion,
    qualifiedReviewerEvidenceSha256: index.qualifiedReviewerEvidenceSha256,
    blindedToModelOutputs: index.blindedToModelOutputs,
    independentlyAdjudicated: index.independentlyAdjudicated,
    authorizedAt: index.authorizedAt,
    items: [...index.items].sort(byItemID).map((item) => ({
      itemID: item.itemID,
      decision: item.decision,
      labelBundleSha256: item.labelBundleSha256,
    })),
  });
}

export function prospectiveEvaluationRunIndexSha256(
  index: Omit<ProspectiveEvaluationRunIndex, "sha256">,
): string {
  return digest({
    schemaVersion: index.schemaVersion,
    manifestSha256: index.manifestSha256,
    evaluationPolicySha256: index.evaluationPolicySha256,
    clinicalDecisionIndexSha256: index.clinicalDecisionIndexSha256,
    authorizedAt: index.authorizedAt,
    sealedAt: index.sealedAt,
    captureSystemEvidenceSha256: index.captureSystemEvidenceSha256,
    independentlyExported: index.independentlyExported,
    items: [...index.items].sort(byItemID).map((item) => ({
      itemID: item.itemID,
      sampleSha256: item.sampleSha256,
    })),
  });
}

export function targetProtocolRegistrySha256(registry: TargetProtocolRegistry): string {
  return digest({
    version: registry.version,
    protocols: Object.fromEntries(Object.entries(registry.protocols)
      .sort(([left], [right]) => compareText(left, right))
      .map(([id, protocol]) => [id, {
        id: protocol.id,
        label: protocol.label,
        phonemes: [...protocol.phonemes],
        status: protocol.status,
        visualCue: protocol.visualCue,
      }])),
  });
}

export function selectiveVisionEvaluationPolicySha256(
  policy: Omit<SelectiveVisionEvaluationPolicy, "sha256">,
): string {
  return digest({
    schemaVersion: policy.schemaVersion,
    version: policy.version,
    lockedAt: policy.lockedAt,
    approvalEvidenceSha256: policy.approvalEvidenceSha256,
    clinicalDecisionPolicyVersion: policy.clinicalDecisionPolicyVersion,
    audioModelArtifactSha256: policy.audioModelArtifactSha256,
    visualModelArtifactSha256: policy.visualModelArtifactSha256,
    fusionPolicySha256: policy.fusionPolicySha256,
    routingThresholds: {
      version: policy.routingThresholds.version,
      audioQualityFloor: policy.routingThresholds.audioQualityFloor,
      videoQualityFloor: policy.routingThresholds.videoQualityFloor,
      passThreshold: policy.routingThresholds.passThreshold,
      analysisThreshold: policy.routingThresholds.analysisThreshold,
    },
    evaluationRegistrySha256: targetProtocolRegistrySha256(policy.evaluationRegistry),
    subgroupKeys: [...policy.subgroupKeys].sort(compareText),
    thresholds: Object.fromEntries(thresholdKeys.map((key) => [key, policy.thresholds[key]])),
  });
}

export function selectiveVisionEvaluationSampleSha256(
  sample: SelectiveVisionEvaluationSample,
): string {
  return digest(canonicalSample(sample));
}

export function evaluateSelectiveVisionRouting(
  samples: readonly SelectiveVisionEvaluationSample[],
  authorizedDataset: AuthorizedVisualDataset,
  annotationBundles: readonly VisualCueAnnotationBundle[],
  clinicalDecisionIndex: ProspectiveClinicalDecisionIndex,
  runIndex: ProspectiveEvaluationRunIndex,
  policy: SelectiveVisionEvaluationPolicy,
  evaluatedAt: string,
): SelectiveVisionEvaluationReport {
  assertAuthorizedVisualDataset(authorizedDataset);
  validateTimestamp(evaluatedAt, "evaluatedAt");
  validatePolicy(policy);
  validateClinicalDecisionIndex(authorizedDataset, clinicalDecisionIndex, policy);
  const annotationIndex = bindVisualAnnotationsToDataset(
    authorizedDataset,
    annotationBundles,
  );
  validateAnnotationIndex(authorizedDataset, annotationIndex);

  const manifest = authorizedDataset.verifiedManifest.manifest;
  if (Date.parse(policy.lockedAt) > Math.min(...manifest.items
    .filter((item) => item.split === "prospective-test")
    .map((item) => Date.parse(item.capturedAt)))) {
    throw new TypeError("The evaluation policy must be locked before prospective capture.");
  }
  if (Date.parse(evaluatedAt) < Date.parse(authorizedDataset.authorizedAt)) {
    throw new TypeError("Evaluation cannot predate current dataset authorization.");
  }
  if (manifest.cueFamily !== "bilabial-closure") {
    throw new TypeError("Selective routing currently supports only bilabial closure.");
  }
  const protocol = policy.evaluationRegistry.protocols["bilabial-closure-v1"];
  if (protocol.status !== "validated" || protocol.visualCue !== "bilabial-closure") {
    throw new TypeError("The evaluation-only registry must enable the bilabial protocol.");
  }

  const prospectiveItems = manifest.items.filter((item) => item.split === "prospective-test");
  const prospectiveIDs = new Set(prospectiveItems.map((item) => item.itemID));
  validateRunIndex(
    authorizedDataset,
    clinicalDecisionIndex,
    runIndex,
    policy,
    samples,
    prospectiveIDs,
    evaluatedAt,
  );
  requireExactIDs(samples.map((sample) => sample.itemID), prospectiveIDs, "Evaluation samples");
  requireExactIDs(clinicalDecisionIndex.items.map((item) => item.itemID), prospectiveIDs,
    "Clinical decisions");
  const annotationByID = new Map(annotationIndex.items.map((item) => [item.itemID, item]));
  const clinicalByID = new Map(clinicalDecisionIndex.items.map((item) => [item.itemID, item]));

  const routed: RoutedSample[] = samples.map((sample) => {
    validateSample(sample, policy.subgroupKeys);
    if (sample.attempt.attemptId !== sample.itemID) {
      throw new TypeError("Attempt IDs must equal their manifest item IDs.");
    }
    if (sample.attempt.protocolId !== "bilabial-closure-v1") {
      throw new TypeError("Every sample must use the locked bilabial protocol.");
    }
    const decision = routeAttempt(
      sample.attempt,
      policy.routingThresholds,
      policy.evaluationRegistry,
    );
    if (sample.audioOnlyOutcome !== audioOutcomeForDecision(decision.kind)) {
      throw new TypeError("Audio-only outcomes must match the versioned routing decision.");
    }
    if (decision.runDeepVision) {
      if (sample.visualInvocationCount !== 1
        || sample.visualOutcome === "not-run"
        || sample.visualLatencyMilliseconds <= 0
        || sample.estimatedVisualCostUsd < 0) {
        throw new TypeError("Eligible deep-vision routes require measured visual evidence.");
      }
    } else if (sample.visualInvocationCount !== 0
      || sample.visualOutcome !== "not-run"
      || sample.fusedCue !== "none"
      || sample.visualLatencyMilliseconds !== 0
      || sample.estimatedVisualCostUsd !== 0
      || sample.fusedOutcome !== sample.audioOnlyOutcome) {
      throw new TypeError("Bypassed visual routes cannot contain fused-only evidence or cost.");
    }
    const annotation = annotationByID.get(sample.itemID);
    const clinical = clinicalByID.get(sample.itemID);
    if (!annotation || !clinical) throw new TypeError("Every item requires bound reference evidence.");
    if (decision.runDeepVision
      && (annotation.finalLabel === "indeterminate" || annotation.finalLabel === "unobservable"
        || sample.visualOutcome === "indeterminate" || sample.visualOutcome === "unobservable")
      && sample.fusedOutcome !== "abstain") {
      throw new TypeError("Indeterminate or unobservable visual evidence must force abstention.");
    }
    if (sample.fusedCue === "bilabial-closure"
      && (!decision.runDeepVision
        || sample.visualOutcome !== "closure-not-observed"
        || sample.fusedOutcome !== "error")) {
      throw new TypeError("A visual cue requires an eligible non-closure model result and error decision.");
    }
    if (sample.fusedOutcome !== "error" && sample.fusedCue !== "none") {
      throw new TypeError("Abstain and correct outcomes cannot emit a corrective cue.");
    }
    if (clinical.decision === "abstain" && sample.fusedOutcome !== "abstain") {
      throw new TypeError("An adjudicated clinical abstention cannot produce a fused decision.");
    }
    return { sample, decision, annotation, clinical };
  });

  const audioOnly = decisionMetrics(routed, "audioOnlyOutcome");
  const fused = decisionMetrics(routed, "fusedOutcome");
  const routing = routingMetrics(routed);
  const pairedComparison = pairedMetrics(routed);
  const errorRecallDelta = audioOnly.errorRecall === null || fused.errorRecall === null
    ? null : fused.errorRecall - audioOnly.errorRecall;
  const thresholds = policy.thresholds;
  const sites = new Set(prospectiveItems.map((item) => item.siteHash));
  const hardware = new Set(prospectiveItems.map((item) => item.hardwareIdentifier));
  const checks: SelectiveVisionEvaluationCheck[] = [
    check("prospective-sample-count", samples.length >= thresholds.minimumProspectiveSamples,
      samples.length, thresholds.minimumProspectiveSamples),
    check("correct-reference-count", audioOnly.correctReferenceCount >= thresholds.minimumCorrectReferences,
      audioOnly.correctReferenceCount, thresholds.minimumCorrectReferences),
    check("error-reference-count", audioOnly.errorReferenceCount >= thresholds.minimumErrorReferences,
      audioOnly.errorReferenceCount, thresholds.minimumErrorReferences),
    check("prospective-site-coverage", sites.size >= thresholds.minimumDistinctProspectiveSites,
      sites.size, thresholds.minimumDistinctProspectiveSites),
    check("hardware-coverage", hardware.size >= thresholds.minimumDistinctHardware,
      hardware.size, thresholds.minimumDistinctHardware),
    check("confident-correct-vision-bypass", routing.confidentCorrectVisionInvocationCount === 0,
      routing.confidentCorrectVisionInvocationCount, 0),
    check("uncertain-vision-bypass", routing.uncertainVisionInvocationCount === 0,
      routing.uncertainVisionInvocationCount, 0),
    check("eligible-mismatch-invocation",
      routing.eligibleMismatchInvocationRate !== null
        && routing.eligibleMismatchInvocationRate >= thresholds.minimumEligibleMismatchInvocationRate,
      routing.eligibleMismatchInvocationRate ?? "unmeasured",
      thresholds.minimumEligibleMismatchInvocationRate),
    check("deep-vision-invocation-rate",
      routing.deepVisionInvocationRate <= thresholds.maximumDeepVisionInvocationRate,
      routing.deepVisionInvocationRate, thresholds.maximumDeepVisionInvocationRate),
    check("observable-deep-sample-rate",
      routing.observableDeepSampleRate !== null
        && routing.observableDeepSampleRate >= thresholds.minimumObservableDeepSampleRate,
      routing.observableDeepSampleRate ?? "unmeasured", thresholds.minimumObservableDeepSampleRate),
    check("visual-cue-accuracy", routing.visualCueAccuracy !== null
      && routing.visualCueAccuracy >= thresholds.minimumVisualCueAccuracy,
      routing.visualCueAccuracy ?? "unmeasured", thresholds.minimumVisualCueAccuracy),
    check("fused-false-pass-rate", fused.falsePassRate !== null
      && fused.falsePassRate <= thresholds.maximumFusedFalsePassRate,
      fused.falsePassRate ?? "unmeasured", thresholds.maximumFusedFalsePassRate),
    check("fused-false-cue-rate", routing.falseCueRate !== null
      && routing.falseCueRate <= thresholds.maximumFusedFalseCueRate,
      routing.falseCueRate ?? "unmeasured", thresholds.maximumFusedFalseCueRate),
    check("fused-coverage", fused.coverage >= thresholds.minimumFusedCoverage,
      fused.coverage, thresholds.minimumFusedCoverage),
    check("error-recall-noninferiority", errorRecallDelta !== null
      && errorRecallDelta >= -thresholds.maximumErrorRecallRegression,
      errorRecallDelta ?? "unmeasured", `>= -${thresholds.maximumErrorRecallRegression}`),
    check("harmful-regression-rate",
      routing.harmfulRegressionRate <= thresholds.maximumHarmfulRegressionRate,
      routing.harmfulRegressionRate, thresholds.maximumHarmfulRegressionRate),
    check("visual-latency-budget", routing.p95VisualLatencyMilliseconds !== null
      && routing.p95VisualLatencyMilliseconds <= thresholds.maximumP95VisualLatencyMilliseconds,
      routing.p95VisualLatencyMilliseconds ?? "unmeasured",
      thresholds.maximumP95VisualLatencyMilliseconds),
    check("visual-cost-budget", routing.averageVisualCostUsdWhenRun !== null
      && routing.averageVisualCostUsdWhenRun <= thresholds.maximumAverageVisualCostUsdWhenRun,
      routing.averageVisualCostUsdWhenRun ?? "unmeasured",
      thresholds.maximumAverageVisualCostUsdWhenRun),
    check("paired-net-improvement",
      pairedComparison.netImprovementRate >= thresholds.minimumPairedNetImprovementRate,
      pairedComparison.netImprovementRate, thresholds.minimumPairedNetImprovementRate),
    check("paired-mcnemar-significance",
      pairedComparison.exactMcNemarPValue <= thresholds.maximumMcNemarPValue,
      pairedComparison.exactMcNemarPValue, thresholds.maximumMcNemarPValue),
  ];
  const subgroups = subgroupMetrics(routed, policy.subgroupKeys);
  for (const [key, value] of Object.entries(subgroups)) {
    checks.push(check(`subgroup-${key}-sample-count`,
      value.sampleCount >= thresholds.minimumSubgroupSize,
      value.sampleCount, thresholds.minimumSubgroupSize));
    checks.push(check(`subgroup-${key}-correct-reference-count`,
      value.fused.correctReferenceCount >= thresholds.minimumSubgroupCorrectReferences,
      value.fused.correctReferenceCount, thresholds.minimumSubgroupCorrectReferences));
    checks.push(check(`subgroup-${key}-error-reference-count`,
      value.fused.errorReferenceCount >= thresholds.minimumSubgroupErrorReferences,
      value.fused.errorReferenceCount, thresholds.minimumSubgroupErrorReferences));
    checks.push(check(`subgroup-${key}-false-pass-rate`,
      value.fused.falsePassRate !== null
        && value.fused.falsePassRate <= thresholds.maximumFusedFalsePassRate,
      value.fused.falsePassRate ?? "unmeasured", thresholds.maximumFusedFalsePassRate));
    checks.push(check(`subgroup-${key}-false-cue-rate`,
      value.routing.falseCueRate !== null
        && value.routing.falseCueRate <= thresholds.maximumFusedFalseCueRate,
      value.routing.falseCueRate ?? "unmeasured", thresholds.maximumFusedFalseCueRate));
    checks.push(check(`subgroup-${key}-harmful-regression-rate`,
      value.routing.harmfulRegressionRate <= thresholds.maximumHarmfulRegressionRate,
      value.routing.harmfulRegressionRate, thresholds.maximumHarmfulRegressionRate));
    const subgroupRecallDelta = value.audioOnly.errorRecall === null
      || value.fused.errorRecall === null ? null
      : value.fused.errorRecall - value.audioOnly.errorRecall;
    checks.push(check(`subgroup-${key}-error-recall-noninferiority`,
      subgroupRecallDelta !== null
        && subgroupRecallDelta >= -thresholds.maximumErrorRecallRegression,
      subgroupRecallDelta ?? "unmeasured", `>= -${thresholds.maximumErrorRecallRegression}`));
  }
  const status = checks.every((item) => item.passed) ? "pass" : "fail";
  return {
    schemaVersion: "selective-vision-evaluation-report-v1",
    evaluationPolicyVersion: policy.version,
    evaluationPolicySha256: policy.sha256,
    evaluationPolicyLockedAt: policy.lockedAt,
    routingThresholdVersion: policy.routingThresholds.version,
    protocolRegistryVersion: policy.evaluationRegistry.version,
    routingSimulation: true,
    manifestSha256: manifest.sha256,
    annotationIndexSha256: annotationIndex.sha256,
    clinicalDecisionIndexSha256: clinicalDecisionIndex.sha256,
    evaluationRunIndexSha256: runIndex.sha256,
    evaluationRunSealedAt: runIndex.sealedAt,
    authorizedAt: authorizedDataset.authorizedAt,
    evaluatedAt,
    sampleEvidenceSha256: samplesSha256(samples),
    routing,
    audioOnly,
    fused,
    errorRecallDelta,
    pairedComparison,
    subgroups,
    checks,
    status,
    researchAdvancementEligible: status === "pass",
    releasePosture: "research-only",
    learnerFeedbackEligible: false,
    productionGateEligible: false,
    limitations: [
      "This report uses an evaluation-only protocol registry; shipped routing remains unchanged.",
      "A passing synthetic or retrospective report cannot substitute for prospective blinded SLP evidence.",
      "Physical-device feasibility, accessibility, privacy, latency, subgroup, and clinical gates remain independent.",
    ],
  };
}

function validatePolicy(policy: SelectiveVisionEvaluationPolicy): void {
  if (!exactKeys(policy, policyKeys)
    || policy.schemaVersion !== "selective-vision-evaluation-policy-v1"
    || !identifier(policy.version)
    || !canonicalTimestamp(policy.lockedAt)
    || !hash(policy.approvalEvidenceSha256)
    || !identifier(policy.clinicalDecisionPolicyVersion)
    || !hash(policy.audioModelArtifactSha256)
    || !hash(policy.visualModelArtifactSha256)
    || !hash(policy.fusionPolicySha256)
    || !identifier(policy.routingThresholds?.version)
    || !identifier(policy.evaluationRegistry?.version)
    || !exactKeys(policy.routingThresholds, ["version", "audioQualityFloor",
      "videoQualityFloor", "passThreshold", "analysisThreshold"])
    || !validEvaluationRegistry(policy.evaluationRegistry)
    || new Set(policy.subgroupKeys).size !== policy.subgroupKeys.length
    || policy.subgroupKeys.some((key) => !/^[A-Za-z][A-Za-z0-9_-]{1,39}$/.test(key))
    || selectiveVisionEvaluationPolicySha256(policy) !== policy.sha256) {
    throw new TypeError("A valid hash-bound selective vision policy is required.");
  }
  const routing = policy.routingThresholds;
  if (![routing.audioQualityFloor, routing.videoQualityFloor, routing.passThreshold,
    routing.analysisThreshold].every(probability)) {
    throw new TypeError("Routing thresholds must be probabilities.");
  }
  validateThresholds(policy.thresholds);
}

function validateClinicalDecisionIndex(
  dataset: AuthorizedVisualDataset,
  index: ProspectiveClinicalDecisionIndex,
  policy: SelectiveVisionEvaluationPolicy,
): void {
  if (!exactKeys(index, ["schemaVersion", "manifestSha256", "policyVersion",
    "qualifiedReviewerEvidenceSha256", "blindedToModelOutputs",
    "independentlyAdjudicated", "authorizedAt", "items", "sha256"])
    || index.schemaVersion !== "prospective-clinical-decision-index-v1"
    || index.manifestSha256 !== dataset.verifiedManifest.sha256
    || index.policyVersion !== policy.clinicalDecisionPolicyVersion
    || !hash(index.qualifiedReviewerEvidenceSha256)
    || index.blindedToModelOutputs !== true
    || index.independentlyAdjudicated !== true
    || index.authorizedAt !== dataset.authorizedAt
    || prospectiveClinicalDecisionIndexSha256(index) !== index.sha256
    || !Array.isArray(index.items)
    || index.items.some((item) => !exactKeys(item,
      ["itemID", "decision", "labelBundleSha256"])
      || !identifier(item.itemID)
      || !(["pass", "analyze", "abstain"] as const).includes(item.decision)
      || !hash(item.labelBundleSha256))) {
    throw new TypeError("A current blinded, adjudicated clinical decision index is required.");
  }
}

function validateRunIndex(
  dataset: AuthorizedVisualDataset,
  clinicalIndex: ProspectiveClinicalDecisionIndex,
  index: ProspectiveEvaluationRunIndex,
  policy: SelectiveVisionEvaluationPolicy,
  samples: readonly SelectiveVisionEvaluationSample[],
  prospectiveIDs: ReadonlySet<string>,
  evaluatedAt: string,
): void {
  if (!exactKeys(index, ["schemaVersion", "manifestSha256", "evaluationPolicySha256",
    "clinicalDecisionIndexSha256", "authorizedAt", "sealedAt",
    "captureSystemEvidenceSha256", "independentlyExported", "items", "sha256"])
    || index.schemaVersion !== "prospective-evaluation-run-index-v1"
    || index.manifestSha256 !== dataset.verifiedManifest.sha256
    || index.evaluationPolicySha256 !== policy.sha256
    || index.clinicalDecisionIndexSha256 !== clinicalIndex.sha256
    || index.authorizedAt !== dataset.authorizedAt
    || !canonicalTimestamp(index.sealedAt)
    || Date.parse(index.sealedAt) < Date.parse(dataset.authorizedAt)
    || Date.parse(index.sealedAt) > Date.parse(evaluatedAt)
    || !hash(index.captureSystemEvidenceSha256)
    || index.independentlyExported !== true
    || !Array.isArray(index.items)
    || index.items.some((item) => !exactKeys(item, ["itemID", "sampleSha256"])
      || !identifier(item.itemID) || !hash(item.sampleSha256))
    || prospectiveEvaluationRunIndexSha256(index) !== index.sha256) {
    throw new TypeError("A current independently exported evaluation run index is required.");
  }
  requireExactIDs(index.items.map((item) => item.itemID), prospectiveIDs,
    "Evaluation run evidence");
  const expectedByID = new Map(index.items.map((item) => [item.itemID, item.sampleSha256]));
  if (samples.some((sample) =>
    expectedByID.get(sample.itemID) !== selectiveVisionEvaluationSampleSha256(sample))) {
    throw new TypeError("Evaluation samples must match the pre-bound run evidence hashes.");
  }
}

function validateAnnotationIndex(
  dataset: AuthorizedVisualDataset,
  index: VisualDatasetAnnotationIndex,
): void {
  const manifest = dataset.verifiedManifest.manifest;
  if (index.schemaVersion !== "visual-dataset-annotation-index-v1"
    || index.manifestSha256 !== manifest.sha256
    || index.deletionLedgerSha256 !== dataset.currentDeletionLedger.sha256
    || index.consentLedgerSha256 !== dataset.currentConsentLedger.sha256
    || index.authorizedAt !== dataset.authorizedAt
    || index.labelPolicyVersion !== manifest.labelPolicyVersion
    || index.releasePosture !== "research-only"
    || index.learnerFeedbackEligible !== false
    || visualDatasetAnnotationIndexSha256(index) !== index.sha256
    || index.items.length !== manifest.items.length) {
    throw new TypeError("A current exact annotation index is required.");
  }
  requireExactIDs(index.items.map((item) => item.itemID),
    new Set(manifest.items.map((item) => item.itemID)), "Annotations");
}

function validateSample(
  sample: SelectiveVisionEvaluationSample,
  subgroupKeys: readonly string[],
): void {
  const unknown = Object.keys(sample).filter(
    (key) => !(sampleKeys as readonly string[]).includes(key),
  );
  if (unknown.length > 0) throw new TypeError(`Evaluation sample has unknown fields: ${unknown.join(", ")}.`);
  parseAttemptEvaluationRequest(sample.attempt);
  if (!identifier(sample.itemID)
    || !(["correct", "error", "abstain"] as const).includes(sample.audioOnlyOutcome)
    || !(["correct", "error", "abstain"] as const).includes(sample.fusedOutcome)
    || !(["bilabial-closure", "none"] as const).includes(sample.fusedCue)
    || !Number.isSafeInteger(sample.visualInvocationCount)
    || sample.visualInvocationCount < 0
    || !(["closure-observed", "closure-not-observed", "indeterminate", "unobservable", "not-run"] as const)
      .includes(sample.visualOutcome)
    || !nonnegative(sample.audioLatencyMilliseconds)
    || !nonnegative(sample.visualLatencyMilliseconds)
    || !nonnegative(sample.estimatedAudioCostUsd)
    || !nonnegative(sample.estimatedVisualCostUsd)
    || typeof sample.subgroup !== "object" || sample.subgroup === null
    || Object.entries(sample.subgroup).some(([key, value]) =>
      !/^[A-Za-z][A-Za-z0-9_-]{1,39}$/.test(key)
      || typeof value !== "string" || value.length < 1 || value.length > 40)
    || subgroupKeys.some((key) => sample.subgroup[key] === undefined)
    || Object.keys(sample.subgroup).some((key) => !subgroupKeys.includes(key))) {
    throw new TypeError("An evaluation sample contains invalid evidence.");
  }
}

function validateThresholds(thresholds: SelectiveVisionEvaluationThresholds): void {
  if (!exactKeys(thresholds, thresholdKeys)
    || !positiveInteger(thresholds.minimumProspectiveSamples)
    || !positiveInteger(thresholds.minimumCorrectReferences)
    || !positiveInteger(thresholds.minimumErrorReferences)
    || !positiveInteger(thresholds.minimumDistinctProspectiveSites)
    || !positiveInteger(thresholds.minimumDistinctHardware)
    || !positiveInteger(thresholds.minimumSubgroupSize)
    || !positiveInteger(thresholds.minimumSubgroupCorrectReferences)
    || !positiveInteger(thresholds.minimumSubgroupErrorReferences)
    || ![thresholds.maximumDeepVisionInvocationRate,
      thresholds.minimumEligibleMismatchInvocationRate,
      thresholds.minimumObservableDeepSampleRate, thresholds.minimumVisualCueAccuracy,
      thresholds.maximumFusedFalsePassRate, thresholds.maximumFusedFalseCueRate,
      thresholds.minimumFusedCoverage, thresholds.maximumErrorRecallRegression,
      thresholds.maximumHarmfulRegressionRate,
      thresholds.minimumPairedNetImprovementRate, thresholds.maximumMcNemarPValue]
      .every(probability)
    || !nonnegative(thresholds.maximumP95VisualLatencyMilliseconds)
    || !nonnegative(thresholds.maximumAverageVisualCostUsdWhenRun)) {
    throw new TypeError("Selective vision thresholds are invalid.");
  }
}

function audioOutcomeForDecision(kind: ReturnType<typeof routeAttempt>["kind"]): ClinicalDecisionOutcome {
  if (kind === "correct") return "correct";
  if (kind === "needs-deep-analysis" || kind === "audio-cue-or-review") return "error";
  return "abstain";
}

type RoutedSample = {
  readonly sample: SelectiveVisionEvaluationSample;
  readonly decision: ReturnType<typeof routeAttempt>;
  readonly annotation: VisualDatasetAnnotationIndex["items"][number];
  readonly clinical: ProspectiveClinicalDecisionIndex["items"][number];
};

function referenceOutcome(item: RoutedSample): Exclude<ClinicalDecisionOutcome, "abstain"> | null {
  if (item.clinical.decision === "pass") return "correct";
  if (item.clinical.decision === "analyze") return "error";
  return null;
}

function decisionMetrics(
  routed: readonly RoutedSample[],
  outcomeKey: "audioOnlyOutcome" | "fusedOutcome",
): SelectiveVisionDecisionMetrics {
  const binary = routed.filter((item) => referenceOutcome(item) !== null);
  const correct = binary.filter((item) => referenceOutcome(item) === "correct");
  const errors = binary.filter((item) => referenceOutcome(item) === "error");
  const decided = binary.filter((item) => item.sample[outcomeKey] !== "abstain");
  const accurate = decided.filter((item) => item.sample[outcomeKey] === referenceOutcome(item));
  return {
    sampleCount: routed.length,
    referenceAbstainCount: routed.length - binary.length,
    decidedCount: decided.length,
    correctReferenceCount: correct.length,
    errorReferenceCount: errors.length,
    coverage: binary.length === 0 ? 0 : decided.length / binary.length,
    accuracy: rate(accurate.length, decided.length),
    falsePassRate: rate(errors.filter((item) => item.sample[outcomeKey] === "correct").length,
      errors.length),
    falseRejectRate: rate(correct.filter((item) => item.sample[outcomeKey] === "error").length,
      correct.length),
    errorRecall: rate(errors.filter((item) => item.sample[outcomeKey] === "error").length,
      errors.length),
    abstentionRate: routed.length === 0 ? 1
      : routed.filter((item) => item.sample[outcomeKey] === "abstain").length / routed.length,
  };
}

function routingMetrics(routed: readonly RoutedSample[]): SelectiveVisionRoutingMetrics {
  const deep = routed.filter((item) => item.decision.runDeepVision);
  const confidentCorrect = routed.filter((item) => item.decision.reason === "confident-correct");
  const uncertain = routed.filter((item) => item.decision.reason === "audio-evidence-uncertain");
  const eligible = routed.filter((item) =>
    item.decision.reason === "confident-mismatch-on-supported-target");
  const observable = deep.filter((item) => item.annotation.finalLabel === "closure-observed"
    || item.annotation.finalLabel === "closure-not-observed");
  const visualCorrect = observable.filter((item) =>
    item.sample.visualOutcome === item.annotation.finalLabel);
  const harmful = routed.filter((item) => {
    const reference = referenceOutcome(item);
    return reference !== null && item.sample.audioOnlyOutcome === reference
      && item.sample.fusedOutcome !== reference;
  });
  const emittedCues = routed.filter((item) => item.sample.fusedCue === "bilabial-closure");
  const falseCues = emittedCues.filter((item) => referenceOutcome(item) !== "error"
    || item.annotation.finalLabel !== "closure-not-observed"
    || item.sample.visualOutcome !== "closure-not-observed");
  const videoConsented = routed.filter((item) => item.sample.attempt.consent.videoProcessing);
  const avoided = videoConsented.filter((item) => !item.decision.runDeepVision);
  return {
    deepVisionInvocationCount: deep.length,
    deepVisionInvocationRate: routed.length === 0 ? 0 : deep.length / routed.length,
    confidentCorrectCount: confidentCorrect.length,
    confidentCorrectVisionInvocationCount:
      confidentCorrect.filter((item) => item.sample.visualOutcome !== "not-run").length,
    uncertainCount: uncertain.length,
    uncertainVisionInvocationCount:
      uncertain.filter((item) => item.sample.visualOutcome !== "not-run").length,
    eligibleMismatchCount: eligible.length,
    eligibleMismatchInvocationRate: rate(
      eligible.filter((item) => item.sample.visualOutcome !== "not-run").length, eligible.length),
    observableDeepSampleRate: rate(observable.length, deep.length),
    visualCueAccuracy: rate(visualCorrect.length, observable.length),
    falseCueRate: rate(falseCues.length, emittedCues.length),
    cueEmissionCount: emittedCues.length,
    falseCueCount: falseCues.length,
    harmfulRegressionCount: harmful.length,
    harmfulRegressionRate: routed.length === 0 ? 0 : harmful.length / routed.length,
    avoidedInvocationCount: avoided.length,
    avoidedInvocationRate: rate(avoided.length, videoConsented.length),
    averageAudioLatencyMilliseconds: average(routed.map((item) =>
      item.sample.audioLatencyMilliseconds)) ?? 0,
    averageVisualLatencyMillisecondsWhenRun: average(deep.map((item) =>
      item.sample.visualLatencyMilliseconds)),
    p95VisualLatencyMilliseconds: percentile95(deep.map((item) =>
      item.sample.visualLatencyMilliseconds)),
    averageAudioCostUsd: average(routed.map((item) => item.sample.estimatedAudioCostUsd)) ?? 0,
    averageVisualCostUsdWhenRun: average(deep.map((item) => item.sample.estimatedVisualCostUsd)),
    totalEstimatedCostUsd: routed.reduce((sum, item) => sum
      + item.sample.estimatedAudioCostUsd + item.sample.estimatedVisualCostUsd, 0),
  };
}

function pairedMetrics(routed: readonly RoutedSample[]) {
  const binary = routed.filter((item) => referenceOutcome(item) !== null);
  let audioOnlyCorrectFusedWrong = 0;
  let audioOnlyWrongFusedCorrect = 0;
  for (const item of binary) {
    const reference = referenceOutcome(item);
    const audioCorrect = item.sample.audioOnlyOutcome === reference;
    const fusedCorrect = item.sample.fusedOutcome === reference;
    if (audioCorrect && !fusedCorrect) audioOnlyCorrectFusedWrong += 1;
    if (!audioCorrect && fusedCorrect) audioOnlyWrongFusedCorrect += 1;
  }
  return {
    binaryReferenceCount: binary.length,
    audioOnlyCorrectFusedWrong,
    audioOnlyWrongFusedCorrect,
    netImprovementRate: binary.length === 0 ? 0
      : (audioOnlyWrongFusedCorrect - audioOnlyCorrectFusedWrong) / binary.length,
    exactMcNemarPValue: exactMcNemarPValue(
      audioOnlyCorrectFusedWrong, audioOnlyWrongFusedCorrect),
  };
}

function subgroupMetrics(
  routed: readonly RoutedSample[],
  subgroupKeys: readonly string[],
): Readonly<Record<string, SelectiveVisionSubgroupMetrics>> {
  const output: Record<string, SelectiveVisionSubgroupMetrics> = {};
  for (const key of subgroupKeys) {
    const values = new Set(routed.map((item) => item.sample.subgroup[key] ?? "unknown"));
    for (const value of values) {
      const selected = routed.filter((item) => (item.sample.subgroup[key] ?? "unknown") === value);
      const routing = routingMetrics(selected);
      output[`${key}=${value}`] = {
        sampleCount: selected.length,
        routing: {
          deepVisionInvocationRate: routing.deepVisionInvocationRate,
          harmfulRegressionRate: routing.harmfulRegressionRate,
          falseCueRate: routing.falseCueRate,
        },
        audioOnly: decisionMetrics(selected, "audioOnlyOutcome"),
        fused: decisionMetrics(selected, "fusedOutcome"),
      };
    }
  }
  return output;
}

function exactMcNemarPValue(left: number, right: number): number {
  const discordant = left + right;
  if (discordant === 0) return 1;
  const lower = Math.min(left, right);
  let probability = 0;
  for (let value = 0; value <= lower; value += 1) {
    probability += Math.exp(logCombination(discordant, value)
      - discordant * Math.log(2));
  }
  return Math.min(1, 2 * probability);
}

function logCombination(total: number, selected: number): number {
  let result = 0;
  const count = Math.min(selected, total - selected);
  for (let index = 1; index <= count; index += 1) {
    result += Math.log(total - count + index) - Math.log(index);
  }
  return result;
}

function requireExactIDs(ids: readonly string[], expected: ReadonlySet<string>, label: string): void {
  if (ids.length !== expected.size || new Set(ids).size !== ids.length
    || ids.some((id) => !expected.has(id))) {
    throw new TypeError(`${label} must cover every prospective item exactly once.`);
  }
}

function samplesSha256(samples: readonly SelectiveVisionEvaluationSample[]): string {
  return digest([...samples].sort(byItemID).map(canonicalSample));
}

function canonicalSample(sample: SelectiveVisionEvaluationSample) {
  return {
    itemID: sample.itemID,
    attempt: {
      attemptId: sample.attempt.attemptId,
      protocolId: sample.attempt.protocolId,
      quality: {
        audioScore: sample.attempt.quality.audioScore,
        ...(sample.attempt.quality.videoScore === undefined
          ? {} : { videoScore: sample.attempt.quality.videoScore }),
        reasonCodes: [...sample.attempt.quality.reasonCodes],
      },
      audio: {
        pCorrect: sample.attempt.audio.pCorrect,
        pError: sample.attempt.audio.pError,
        calibrated: sample.attempt.audio.calibrated,
        ambiguous: sample.attempt.audio.ambiguous,
        ...(sample.attempt.audio.likelyError === undefined
          ? {} : { likelyError: sample.attempt.audio.likelyError }),
      },
      consent: {
        audioProcessing: sample.attempt.consent.audioProcessing,
        videoProcessing: sample.attempt.consent.videoProcessing,
        clinicianReview: sample.attempt.consent.clinicianReview,
        researchUse: sample.attempt.consent.researchUse,
      },
    },
    audioOnlyOutcome: sample.audioOnlyOutcome,
    fusedOutcome: sample.fusedOutcome,
    fusedCue: sample.fusedCue,
    visualInvocationCount: sample.visualInvocationCount,
    visualOutcome: sample.visualOutcome,
    audioLatencyMilliseconds: sample.audioLatencyMilliseconds,
    visualLatencyMilliseconds: sample.visualLatencyMilliseconds,
    estimatedAudioCostUsd: sample.estimatedAudioCostUsd,
    estimatedVisualCostUsd: sample.estimatedVisualCostUsd,
    subgroup: Object.fromEntries(Object.entries(sample.subgroup)
      .sort(([left], [right]) => compareText(left, right))),
  };
}

function check(id: string, passed: boolean, measured: number | string,
  required: number | string): SelectiveVisionEvaluationCheck {
  return { id, passed, measured, required };
}

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function byItemID(left: { readonly itemID: string }, right: { readonly itemID: string }): number {
  return compareText(left.itemID, right.itemID);
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function validateTimestamp(value: string, label: string): void {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new TypeError(`${label} must be a canonical ISO-8601 timestamp.`);
  }
}

function canonicalTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString() === value;
}

function rate(numerator: number, denominator: number): number | null {
  return denominator === 0 ? null : numerator / denominator;
}

function average(values: readonly number[]): number | null {
  return values.length === 0 ? null
    : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentile95(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? null;
}

function hash(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

function identifier(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/.test(value);
}

function nonnegative(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

function positiveInteger(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0;
}

function probability(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

function exactKeys(value: unknown, expected: readonly string[]): boolean {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length
    && actual.every((key, index) => key === wanted[index]);
}

function validEvaluationRegistry(registry: TargetProtocolRegistry): boolean {
  if (!exactKeys(registry, ["version", "protocols"])
    || typeof registry.protocols !== "object" || registry.protocols === null) return false;
  const expectedIDs = ["audio-only-v1", "bilabial-closure-v1",
    "interdental-visibility-v1", "l-tip-lift-research-v1",
    "labiodental-contact-v1"];
  if (!exactKeys(registry.protocols, expectedIDs)) return false;
  return Object.entries(registry.protocols).every(([id, protocol]) =>
    exactKeys(protocol, ["id", "label", "phonemes", "status", "visualCue"])
    && protocol.id === id
    && typeof protocol.label === "string" && protocol.label.length > 0
    && Array.isArray(protocol.phonemes)
    && protocol.phonemes.length > 0
    && protocol.phonemes.every((phoneme) => typeof phoneme === "string" && phoneme.length > 0)
    && (["candidate", "validated", "research", "audio-only"] as const)
      .includes(protocol.status));
}
