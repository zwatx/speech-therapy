import { createHash, createPublicKey, verify as verifySignature } from "node:crypto";

import {
  buildEvaluationReport,
  type VerifiedEvaluationManifest,
} from "./evaluation.ts";
import type {
  EvaluationArtifactVersions,
  EvaluationMetrics,
  EvaluationReport,
  EvaluationSample,
  EvaluationThresholds,
  LockedEvaluationManifest,
} from "./types.ts";

export const bakeoffDimensions = [
  "clinicalTaskFit",
  "childDomainFit",
  "safetyEquityEvidence",
  "commercialLegalFit",
  "deploymentFit",
  "interpretability",
  "maintenance",
] as const;
export type BakeoffDimension = (typeof bakeoffDimensions)[number];

export type RightsDisposition = "approved" | "restricted" | "unverified";

export interface AudioBakeoffCandidateManifest {
  readonly schemaVersion: "audio-bakeoff-candidate-v1";
  readonly candidateId: string;
  readonly version: string;
  readonly role: "primary-baseline" | "challenger" | "framework" | "reference";
  readonly strategy:
    | "frozen-open-encoder-owned-head"
    | "owned-engineered-feature-baseline"
    | "reference-only";
  readonly code: {
    readonly repository: string;
    readonly revision: string;
    readonly sha256: string;
    readonly licenseIdentifier: string;
  };
  readonly weights: {
    readonly artifactId: string;
    readonly revision: string;
    readonly sha256: string;
    readonly licenseIdentifier: string;
  };
  readonly trainingDataLineageSha256: string;
  readonly legalReviewEvidenceSha256: string;
  readonly rights: {
    readonly benchmarkUse: RightsDisposition;
    readonly commercialHealthInference: RightsDisposition;
    readonly derivativeTraining: RightsDisposition;
    readonly redistribution: RightsDisposition;
    readonly mobileBundling: RightsDisposition;
  };
  readonly interface: {
    readonly outputKind:
      | "phone-posteriors"
      | "aligned-embeddings"
      | "engineered-features"
      | "graphemes"
      | "transcript";
    readonly usesPromptAwareDecoder: boolean;
    readonly supportsConstrainedPhoneHead: boolean;
  };
  readonly releasePosture: "research-candidate-only";
  readonly learnerFeedbackEligible: false;
  readonly productionEligible: false;
  readonly sha256: string;
}

export interface AudioBakeoffCharter {
  readonly schemaVersion: "audio-bakeoff-charter-v1";
  readonly version: string;
  readonly lockedAt: string;
  readonly evaluationManifestSha256: string;
  readonly evaluationManifestEnvelopeSha256: string;
  readonly evaluationReferenceSha256: string;
  readonly stage: "frozen-encoder-owned-head";
  readonly requiredCandidateIds: readonly string[];
  readonly referenceCandidateIds: readonly string[];
  readonly candidateManifestSha256ById: Readonly<Record<string, string>>;
  readonly candidateRoleById: Readonly<Record<string, AudioBakeoffCandidateManifest["role"]>>;
  readonly subgroupKeys: readonly string[];
  readonly thresholdVersion: string;
  readonly thresholdsSha256: string;
  readonly lexiconVersion: string;
  readonly scoringPolicyVersion: string;
  readonly identicalHeadRecipeSha256: string;
  readonly calibrationRecipeSha256: string;
  readonly deploymentProtocolSha256: string;
  readonly labelPolicySha256: string;
  readonly scorecardRubricSha256: string;
  readonly scorecardAuthority: {
    readonly keyId: string;
    readonly publicKeyPem: string;
  };
  readonly runAuthority: {
    readonly keyId: string;
    readonly publicKeyPem: string;
  };
  readonly adaptationAuthority: {
    readonly keyId: string;
    readonly publicKeyPem: string;
  };
  readonly legalPolicyVersion: string;
  readonly minimumTestSamples: number;
  readonly minimumSubgroupSamples: number;
  readonly minimumSubgroupCorrectSamples: number;
  readonly minimumSubgroupErrorSamples: number;
  readonly gates: {
    readonly maximumFalsePassRate: number;
    readonly maximumFalseRejectRate: number;
    readonly maximumAbstentionRate: number;
    readonly maximumConditionalEce: number;
    readonly maximumSubgroupRateGap: number;
    readonly maximumP95LatencyMilliseconds: number;
    readonly maximumColdStartMilliseconds: number;
    readonly maximumAverageCostUsd: number;
    readonly maximumPeakMemoryBytes: number;
    readonly maximumModelBytes: number;
  };
  readonly weights: Readonly<Record<BakeoffDimension, number>>;
  readonly sha256: string;
}

export interface AudioBakeoffScorecard {
  readonly rubricSha256: string;
  readonly scorerKeyId: string;
  readonly scores: Readonly<Record<BakeoffDimension, number>>;
  readonly evidence: Readonly<Record<BakeoffDimension, string>>;
  readonly signatureBase64: string;
}

export interface AudioBakeoffMeasurements {
  readonly modelBytes: number;
  readonly peakMemoryBytes: number;
  readonly coldStartMilliseconds: number;
  readonly scorecard: AudioBakeoffScorecard;
}

export interface AudioBakeoffRunAttestation {
  readonly keyId: string;
  readonly algorithm: "Ed25519";
  readonly calibrationArtifactSha256: string;
  readonly calibrationManifestSha256: string;
  readonly calibrationRecipeSha256: string;
  readonly deploymentProtocolSha256: string;
  readonly signatureBase64: string;
}

export interface AudioBakeoffRunEvidence {
  readonly charterSha256: string;
  readonly candidateId: string;
  readonly candidateManifestSha256: string;
  readonly evaluationManifestSha256: string;
  readonly evaluationReferenceSha256: string;
  readonly sampleEvidenceSha256: string;
  readonly thresholdsSha256: string;
  readonly artifacts: EvaluationArtifactVersions;
  readonly measurements: AudioBakeoffMeasurements;
  readonly headRecipeSha256: string;
  readonly inferenceContainerSha256: string;
  readonly evaluatedAt: string;
}

export interface AudioBakeoffCandidateResult {
  readonly schemaVersion: "audio-bakeoff-candidate-result-v1";
  readonly charterSha256: string;
  readonly candidateId: string;
  readonly candidateManifestSha256: string;
  readonly evaluationManifestSha256: string;
  readonly sampleEvidenceSha256: string;
  readonly evaluationReportSha256: string;
  readonly evaluationReport: EvaluationReport;
  readonly evaluatedAt: string;
  readonly calibrationVersion: string;
  readonly calibrationArtifactSha256: string;
  readonly headRecipeSha256: string;
  readonly inferenceContainerSha256: string;
  readonly measurements: AudioBakeoffMeasurements;
  readonly runAttestation: AudioBakeoffRunAttestation;
  readonly maximumSubgroupRateGap: number;
  readonly hardGateFailures: readonly string[];
  readonly adaptationEligible: boolean;
  readonly weightedScore: number;
  readonly releasePosture: "research-comparison-only";
  readonly learnerFeedbackEligible: false;
  readonly productionEligible: false;
  readonly sha256: string;
}

export interface AudioBakeoffSelectionReport {
  readonly schemaVersion: "audio-bakeoff-selection-report-v1";
  readonly charterSha256: string;
  readonly evaluatedCandidateCount: number;
  readonly ranked: readonly {
    readonly candidateId: string;
    readonly candidateManifestSha256: string;
    readonly resultSha256: string;
    readonly rank: number | null;
    readonly weightedScore: number;
    readonly adaptationEligible: boolean;
    readonly hardGateFailures: readonly string[];
  }[];
  readonly recommendedTeacherCandidateId: string | null;
  readonly fallbackCandidateId: string | null;
  readonly selectionAuthority: "research-prioritization-only";
  readonly learnerFeedbackEligible: false;
  readonly productionEligible: false;
  readonly limitations: readonly string[];
  readonly sha256: string;
}

export interface OwnedAudioAdaptationManifest {
  readonly schemaVersion: "owned-audio-adaptation-manifest-v1";
  readonly version: string;
  readonly strategy: "owned-head" | "parameter-efficient" | "partial-fine-tune" | "distilled-student";
  readonly parentCandidateManifestSha256: string;
  readonly parentBakeoffResultSha256: string;
  readonly parentSelectionReportSha256: string;
  readonly trainingDatasetManifestSha256: string;
  readonly calibrationDatasetManifestSha256: string;
  readonly consentSnapshotSha256: string;
  readonly deletionLedgerSha256: string;
  readonly authorizationSha256: string;
  readonly labelPolicySha256: string;
  readonly trainingRecipeSha256: string;
  readonly trainingCodeSha256: string;
  readonly trainingContainerSha256: string;
  readonly outputCheckpointSha256: string;
  readonly randomSeeds: readonly number[];
  readonly trainedAt: string;
  readonly releasePosture: "research-adaptation-only";
  readonly learnerFeedbackEligible: false;
  readonly productionEligible: false;
  readonly sha256: string;
}

export interface AudioAdaptationDatasetManifestItem {
  readonly attemptId: string;
  readonly speakerHash: string;
  readonly householdHash: string;
  readonly deletionSubjectHash: string;
  readonly consentSnapshotHash: string;
}

export interface AudioAdaptationDatasetManifest {
  readonly schemaVersion: "audio-adaptation-dataset-manifest-v1";
  readonly version: string;
  readonly purpose: "training" | "calibration";
  readonly lockedAt: string;
  readonly labelPolicySha256: string;
  readonly consentSnapshotSha256: string;
  readonly deletionLedgerSha256: string;
  readonly items: readonly AudioAdaptationDatasetManifestItem[];
  readonly sha256: string;
}

export interface AudioAdaptationAuthorization {
  readonly schemaVersion: "audio-adaptation-authorization-v1";
  readonly keyId: string;
  readonly algorithm: "Ed25519";
  readonly parentSelectionReportSha256: string;
  readonly parentBakeoffResultSha256: string;
  readonly trainingDatasetManifestSha256: string;
  readonly calibrationDatasetManifestSha256: string;
  readonly consentSnapshotSha256: string;
  readonly deletionLedgerSha256: string;
  readonly labelPolicySha256: string;
  readonly authorizedAt: string;
  readonly expiresAt: string;
  readonly signatureBase64: string;
  readonly sha256: string;
}

const verifiedAdaptationMarker: unique symbol = Symbol("verified-owned-audio-adaptation");
const builtCandidateResults = new WeakSet<object>();
const builtSelectionReports = new WeakSet<object>();

export interface VerifiedOwnedAudioAdaptation {
  readonly manifest: OwnedAudioAdaptationManifest;
  readonly verifiedAt: string;
  readonly researchLineageStructurallyValid: true;
  readonly learnerFeedbackEligible: false;
  readonly productionEligible: false;
  readonly [verifiedAdaptationMarker]: true;
}

export function audioBakeoffCandidateManifestSha256(
  candidate: Omit<AudioBakeoffCandidateManifest, "sha256">,
): string {
  return digest(canonicalCandidate(candidate));
}

export function audioBakeoffCharterSha256(
  charter: Omit<AudioBakeoffCharter, "sha256">,
): string {
  return digest({
    schemaVersion: charter.schemaVersion,
    version: charter.version,
    lockedAt: charter.lockedAt,
    evaluationManifestSha256: charter.evaluationManifestSha256,
    evaluationManifestEnvelopeSha256: charter.evaluationManifestEnvelopeSha256,
    evaluationReferenceSha256: charter.evaluationReferenceSha256,
    stage: charter.stage,
    requiredCandidateIds: [...charter.requiredCandidateIds].sort(compareText),
    referenceCandidateIds: [...charter.referenceCandidateIds].sort(compareText),
    candidateManifestSha256ById: canonicalStringRecord(charter.candidateManifestSha256ById),
    candidateRoleById: canonicalStringRecord(charter.candidateRoleById),
    subgroupKeys: [...charter.subgroupKeys].sort(compareText),
    thresholdVersion: charter.thresholdVersion,
    thresholdsSha256: charter.thresholdsSha256,
    lexiconVersion: charter.lexiconVersion,
    scoringPolicyVersion: charter.scoringPolicyVersion,
    identicalHeadRecipeSha256: charter.identicalHeadRecipeSha256,
    calibrationRecipeSha256: charter.calibrationRecipeSha256,
    deploymentProtocolSha256: charter.deploymentProtocolSha256,
    labelPolicySha256: charter.labelPolicySha256,
    scorecardRubricSha256: charter.scorecardRubricSha256,
    scorecardAuthority: canonicalAuthority(charter.scorecardAuthority),
    runAuthority: canonicalAuthority(charter.runAuthority),
    adaptationAuthority: canonicalAuthority(charter.adaptationAuthority),
    legalPolicyVersion: charter.legalPolicyVersion,
    minimumTestSamples: charter.minimumTestSamples,
    minimumSubgroupSamples: charter.minimumSubgroupSamples,
    minimumSubgroupCorrectSamples: charter.minimumSubgroupCorrectSamples,
    minimumSubgroupErrorSamples: charter.minimumSubgroupErrorSamples,
    gates: canonicalGates(charter.gates),
    weights: canonicalDimensions(charter.weights),
  });
}

export function audioBakeoffCandidateResultSha256(
  result: Omit<AudioBakeoffCandidateResult, "sha256">,
): string {
  return digest({
    schemaVersion: result.schemaVersion,
    charterSha256: result.charterSha256,
    candidateId: result.candidateId,
    candidateManifestSha256: result.candidateManifestSha256,
    evaluationManifestSha256: result.evaluationManifestSha256,
    sampleEvidenceSha256: result.sampleEvidenceSha256,
    evaluationReportSha256: result.evaluationReportSha256,
    evaluationReport: canonicalEvaluationReport(result.evaluationReport),
    evaluatedAt: result.evaluatedAt,
    calibrationVersion: result.calibrationVersion,
    calibrationArtifactSha256: result.calibrationArtifactSha256,
    headRecipeSha256: result.headRecipeSha256,
    inferenceContainerSha256: result.inferenceContainerSha256,
    measurements: canonicalMeasurements(result.measurements),
    runAttestation: {
      ...canonicalRunAttestation(result.runAttestation),
      signatureBase64: result.runAttestation.signatureBase64,
    },
    maximumSubgroupRateGap: result.maximumSubgroupRateGap,
    hardGateFailures: [...result.hardGateFailures].sort(compareText),
    adaptationEligible: result.adaptationEligible,
    weightedScore: result.weightedScore,
    releasePosture: result.releasePosture,
    learnerFeedbackEligible: result.learnerFeedbackEligible,
    productionEligible: result.productionEligible,
  });
}

export function buildAudioBakeoffCandidateResult(
  candidate: AudioBakeoffCandidateManifest,
  charter: AudioBakeoffCharter,
  samples: readonly EvaluationSample[],
  thresholds: EvaluationThresholds,
  verifiedManifest: VerifiedEvaluationManifest,
  artifacts: EvaluationArtifactVersions,
  measurements: AudioBakeoffMeasurements,
  headRecipeSha256: string,
  inferenceContainerSha256: string,
  runAttestation: AudioBakeoffRunAttestation,
  evaluatedAt: string,
): AudioBakeoffCandidateResult {
  validateCandidate(candidate);
  validateCharter(charter);
  validateMeasurements(measurements, candidate.candidateId, charter);
  if (!exactKeys(thresholds, ["version", "passThreshold", "analysisThreshold"])
    || !exactKeys(artifacts, ["lexiconVersion", "calibrationVersion", "scoringPolicyVersion"])) {
    throw new TypeError("Bake-off threshold and artifact records must use the strict schema.");
  }
  requireCanonicalTimestamp(evaluatedAt, "evaluatedAt");
  validateBakeoffSamples(samples, charter);
  requireHash(inferenceContainerSha256, "inference container");
  requireHash(headRecipeSha256, "executed head recipe");
  if (verifiedManifest.sha256 !== charter.evaluationManifestSha256
    || lockedEvaluationManifestEnvelopeSha256(verifiedManifest.manifest)
      !== charter.evaluationManifestEnvelopeSha256
    || thresholds.version !== charter.thresholdVersion
    || evaluationThresholdsSha256(thresholds) !== charter.thresholdsSha256
    || evaluationReferenceSha256(samples) !== charter.evaluationReferenceSha256
    || candidate.sha256 !== charter.candidateManifestSha256ById[candidate.candidateId]
    || candidate.role !== charter.candidateRoleById[candidate.candidateId]
    || headRecipeSha256 !== charter.identicalHeadRecipeSha256
    || artifacts.lexiconVersion !== charter.lexiconVersion
    || artifacts.scoringPolicyVersion !== charter.scoringPolicyVersion) {
    throw new TypeError("Bake-off inputs do not match the locked charter.");
  }
  if (Date.parse(charter.lockedAt) < Date.parse(verifiedManifest.manifest.lockedAt)
    || !canonicalTimestamp(verifiedManifest.manifest.lockedAt)
    || Date.parse(evaluatedAt) < Date.parse(charter.lockedAt)) {
    throw new TypeError("The bake-off charter and evaluation chronology are invalid.");
  }
  validateRunAttestation(runAttestation, charter, {
    charterSha256: charter.sha256,
    candidateId: candidate.candidateId,
    candidateManifestSha256: candidate.sha256,
    evaluationManifestSha256: verifiedManifest.sha256,
    evaluationReferenceSha256: charter.evaluationReferenceSha256,
    sampleEvidenceSha256: evaluationSamplesSha256(samples),
    thresholdsSha256: evaluationThresholdsSha256(thresholds),
    artifacts,
    measurements,
    headRecipeSha256,
    inferenceContainerSha256,
    evaluatedAt,
  });
  const report = buildEvaluationReport(
    samples,
    thresholds,
    charter.subgroupKeys,
    verifiedManifest,
    artifacts,
  );
  const subgroupGap = maximumSubgroupRateGap(report);
  const failures = hardGateFailures(candidate, charter, report, subgroupGap, measurements);
  const adaptationEligible = failures.length === 0
    && candidate.role !== "reference"
    && candidate.strategy !== "reference-only";
  const base = {
    schemaVersion: "audio-bakeoff-candidate-result-v1" as const,
    charterSha256: charter.sha256,
    candidateId: candidate.candidateId,
    candidateManifestSha256: candidate.sha256,
    evaluationManifestSha256: verifiedManifest.sha256,
    sampleEvidenceSha256: evaluationSamplesSha256(samples),
    evaluationReportSha256: evaluationReportSha256(report),
    evaluationReport: report,
    evaluatedAt,
    calibrationVersion: artifacts.calibrationVersion,
    calibrationArtifactSha256: runAttestation.calibrationArtifactSha256,
    headRecipeSha256,
    inferenceContainerSha256,
    measurements,
    runAttestation,
    maximumSubgroupRateGap: subgroupGap,
    hardGateFailures: failures,
    adaptationEligible,
    weightedScore: weightedScore(measurements.scorecard.scores, charter.weights),
    releasePosture: "research-comparison-only" as const,
    learnerFeedbackEligible: false as const,
    productionEligible: false as const,
  };
  const result = Object.freeze({
    ...base,
    sha256: audioBakeoffCandidateResultSha256(base),
  });
  builtCandidateResults.add(result);
  return result;
}

export function selectAudioBakeoffCandidates(
  charter: AudioBakeoffCharter,
  candidates: readonly AudioBakeoffCandidateManifest[],
  results: readonly AudioBakeoffCandidateResult[],
): AudioBakeoffSelectionReport {
  validateCharter(charter);
  if (candidates.length !== results.length || candidates.length === 0) {
    throw new TypeError("Every bake-off candidate requires exactly one result.");
  }
  const candidateByID = new Map<string, AudioBakeoffCandidateManifest>();
  const charterCandidateIds = new Set([
    ...charter.requiredCandidateIds,
    ...charter.referenceCandidateIds,
  ]);
  if (candidates.length !== charterCandidateIds.size) {
    throw new TypeError("The candidate set must exactly match the locked charter.");
  }
  for (const candidate of candidates) {
    validateCandidate(candidate);
    if (candidateByID.has(candidate.candidateId)) {
      throw new TypeError("Bake-off candidate IDs must be unique.");
    }
    candidateByID.set(candidate.candidateId, candidate);
    if (!charterCandidateIds.has(candidate.candidateId)
      || charter.candidateManifestSha256ById[candidate.candidateId] !== candidate.sha256
      || charter.candidateRoleById[candidate.candidateId] !== candidate.role) {
      throw new TypeError("A candidate manifest or role was substituted after charter lock.");
    }
  }
  for (const required of charter.requiredCandidateIds) {
    if (!candidateByID.has(required)) {
      throw new TypeError("The bake-off is missing a charter-required candidate.");
    }
  }
  for (const reference of charter.referenceCandidateIds) {
    if (!candidateByID.has(reference)) {
      throw new TypeError("The bake-off is missing a charter-required reference candidate.");
    }
  }
  if (charter.referenceCandidateIds.some((id) =>
    candidateByID.get(id)?.role !== "reference")
    || charter.requiredCandidateIds.some((id) =>
      candidateByID.get(id)?.role === "reference")) {
    throw new TypeError("Candidate roles do not match the locked charter.");
  }
  const resultByID = new Map<string, AudioBakeoffCandidateResult>();
  for (const result of results) {
    if (!builtCandidateResults.has(result)) {
      throw new TypeError("Bake-off selection requires locally rebuilt candidate evidence.");
    }
    validateResult(result, charter);
    const candidate = candidateByID.get(result.candidateId);
    if (!candidate || result.candidateManifestSha256 !== candidate.sha256
      || resultByID.has(result.candidateId)) {
      throw new TypeError("A bake-off result is missing, duplicated, or substituted.");
    }
    resultByID.set(result.candidateId, result);
  }
  if (resultByID.size !== candidateByID.size) {
    throw new TypeError("Every candidate must have one exact bake-off result.");
  }
  const eligible = results.filter((result) => result.adaptationEligible)
    .sort((left, right) => right.weightedScore - left.weightedScore
      || compareText(left.candidateId, right.candidateId));
  const rankByID = new Map(eligible.map((result, index) =>
    [result.candidateId, index + 1]));
  const ranked = results.map((result) => ({
    candidateId: result.candidateId,
    candidateManifestSha256: result.candidateManifestSha256,
    resultSha256: result.sha256,
    rank: rankByID.get(result.candidateId) ?? null,
    weightedScore: result.weightedScore,
    adaptationEligible: result.adaptationEligible,
    hardGateFailures: result.hardGateFailures,
  })).sort((left, right) => (left.rank ?? Number.MAX_SAFE_INTEGER)
    - (right.rank ?? Number.MAX_SAFE_INTEGER)
    || compareText(left.candidateId, right.candidateId));
  const base = {
    schemaVersion: "audio-bakeoff-selection-report-v1" as const,
    charterSha256: charter.sha256,
    evaluatedCandidateCount: candidates.length,
    ranked,
    recommendedTeacherCandidateId: eligible[0]?.candidateId ?? null,
    fallbackCandidateId: eligible[1]?.candidateId ?? null,
    selectionAuthority: "research-prioritization-only" as const,
    learnerFeedbackEligible: false as const,
    productionEligible: false as const,
    limitations: [
      "A ranking prioritizes research adaptation only; it does not validate a clinical target or authorize deployment.",
      "License evidence must be authenticated by counsel and the platform before real model or data use.",
      "Synthetic fixtures cannot substitute for representative child/SSD evaluation or physical-device profiling.",
    ],
  };
  const report = Object.freeze({
    ...base,
    sha256: audioBakeoffSelectionReportSha256(base),
  });
  builtSelectionReports.add(report);
  return report;
}

export function audioBakeoffSelectionReportSha256(
  report: Omit<AudioBakeoffSelectionReport, "sha256">,
): string {
  return digest({
    schemaVersion: report.schemaVersion,
    charterSha256: report.charterSha256,
    evaluatedCandidateCount: report.evaluatedCandidateCount,
    ranked: report.ranked.map((item) => ({
      ...item,
      hardGateFailures: [...item.hardGateFailures].sort(compareText),
    })),
    recommendedTeacherCandidateId: report.recommendedTeacherCandidateId,
    fallbackCandidateId: report.fallbackCandidateId,
    selectionAuthority: report.selectionAuthority,
    learnerFeedbackEligible: report.learnerFeedbackEligible,
    productionEligible: report.productionEligible,
    limitations: [...report.limitations],
  });
}

export function ownedAudioAdaptationManifestSha256(
  manifest: Omit<OwnedAudioAdaptationManifest, "sha256">,
): string {
  return digest({
    schemaVersion: manifest.schemaVersion,
    version: manifest.version,
    strategy: manifest.strategy,
    parentCandidateManifestSha256: manifest.parentCandidateManifestSha256,
    parentBakeoffResultSha256: manifest.parentBakeoffResultSha256,
    parentSelectionReportSha256: manifest.parentSelectionReportSha256,
    trainingDatasetManifestSha256: manifest.trainingDatasetManifestSha256,
    calibrationDatasetManifestSha256: manifest.calibrationDatasetManifestSha256,
    consentSnapshotSha256: manifest.consentSnapshotSha256,
    deletionLedgerSha256: manifest.deletionLedgerSha256,
    authorizationSha256: manifest.authorizationSha256,
    labelPolicySha256: manifest.labelPolicySha256,
    trainingRecipeSha256: manifest.trainingRecipeSha256,
    trainingCodeSha256: manifest.trainingCodeSha256,
    trainingContainerSha256: manifest.trainingContainerSha256,
    outputCheckpointSha256: manifest.outputCheckpointSha256,
    randomSeeds: [...manifest.randomSeeds].sort((left, right) => left - right),
    trainedAt: manifest.trainedAt,
    releasePosture: manifest.releasePosture,
    learnerFeedbackEligible: manifest.learnerFeedbackEligible,
    productionEligible: manifest.productionEligible,
  });
}

export function evaluationThresholdsSha256(thresholds: EvaluationThresholds): string {
  return digest({
    version: thresholds.version,
    passThreshold: thresholds.passThreshold,
    analysisThreshold: thresholds.analysisThreshold,
  });
}

export function evaluationReferenceSha256(samples: readonly EvaluationSample[]): string {
  return digest([...samples]
    .sort((left, right) => compareText(left.attemptId, right.attemptId))
    .map((sample) => ({
      attemptId: sample.attemptId,
      label: sample.label,
      ambiguous: sample.ambiguous,
      subgroup: canonicalStringRecord(sample.subgroup),
    })));
}

export function scorecardAttestationPayload(
  candidateId: string,
  scorecard: Omit<AudioBakeoffScorecard, "signatureBase64">,
): string {
  return JSON.stringify({
    schemaVersion: "audio-bakeoff-scorecard-attestation-v1",
    candidateId,
    rubricSha256: scorecard.rubricSha256,
    scorerKeyId: scorecard.scorerKeyId,
    scores: canonicalDimensions(scorecard.scores),
    evidence: canonicalDimensions(scorecard.evidence),
  });
}

export function lockedEvaluationManifestEnvelopeSha256(
  manifest: LockedEvaluationManifest,
): string {
  return digest({
    version: manifest.version,
    sha256: manifest.sha256,
    lockedAt: manifest.lockedAt,
    items: [...manifest.items]
      .sort((left, right) => compareText(left.attemptId, right.attemptId))
      .map((item) => ({
        attemptId: item.attemptId,
        speakerHash: item.speakerHash,
        householdHash: item.householdHash,
        split: item.split,
        targetProtocolId: item.targetProtocolId,
      })),
  });
}

export function audioBakeoffRunAttestationPayload(
  evidence: AudioBakeoffRunEvidence,
  attestation: Omit<AudioBakeoffRunAttestation, "signatureBase64">,
): string {
  return JSON.stringify({
    schemaVersion: "audio-bakeoff-run-attestation-v1",
    charterSha256: evidence.charterSha256,
    candidateId: evidence.candidateId,
    candidateManifestSha256: evidence.candidateManifestSha256,
    evaluationManifestSha256: evidence.evaluationManifestSha256,
    evaluationReferenceSha256: evidence.evaluationReferenceSha256,
    sampleEvidenceSha256: evidence.sampleEvidenceSha256,
    thresholdsSha256: evidence.thresholdsSha256,
    artifacts: {
      lexiconVersion: evidence.artifacts.lexiconVersion,
      calibrationVersion: evidence.artifacts.calibrationVersion,
      scoringPolicyVersion: evidence.artifacts.scoringPolicyVersion,
    },
    measurements: canonicalMeasurements(evidence.measurements),
    headRecipeSha256: evidence.headRecipeSha256,
    inferenceContainerSha256: evidence.inferenceContainerSha256,
    evaluatedAt: evidence.evaluatedAt,
    attestation: canonicalRunAttestation(attestation),
  });
}

export function audioAdaptationDatasetManifestSha256(
  manifest: Omit<AudioAdaptationDatasetManifest, "sha256">,
): string {
  return digest({
    schemaVersion: manifest.schemaVersion,
    version: manifest.version,
    purpose: manifest.purpose,
    lockedAt: manifest.lockedAt,
    labelPolicySha256: manifest.labelPolicySha256,
    consentSnapshotSha256: manifest.consentSnapshotSha256,
    deletionLedgerSha256: manifest.deletionLedgerSha256,
    items: [...manifest.items]
      .sort((left, right) => compareText(left.attemptId, right.attemptId))
      .map(canonicalAdaptationDatasetItem),
  });
}

export function audioAdaptationAuthorizationPayload(
  authorization: Omit<AudioAdaptationAuthorization, "signatureBase64" | "sha256">,
): string {
  return JSON.stringify({
    schemaVersion: authorization.schemaVersion,
    keyId: authorization.keyId,
    algorithm: authorization.algorithm,
    parentSelectionReportSha256: authorization.parentSelectionReportSha256,
    parentBakeoffResultSha256: authorization.parentBakeoffResultSha256,
    trainingDatasetManifestSha256: authorization.trainingDatasetManifestSha256,
    calibrationDatasetManifestSha256: authorization.calibrationDatasetManifestSha256,
    consentSnapshotSha256: authorization.consentSnapshotSha256,
    deletionLedgerSha256: authorization.deletionLedgerSha256,
    labelPolicySha256: authorization.labelPolicySha256,
    authorizedAt: authorization.authorizedAt,
    expiresAt: authorization.expiresAt,
  });
}

export function audioAdaptationAuthorizationSha256(
  authorization: Omit<AudioAdaptationAuthorization, "sha256">,
): string {
  return digest({
    schemaVersion: authorization.schemaVersion,
    keyId: authorization.keyId,
    algorithm: authorization.algorithm,
    parentSelectionReportSha256: authorization.parentSelectionReportSha256,
    parentBakeoffResultSha256: authorization.parentBakeoffResultSha256,
    trainingDatasetManifestSha256: authorization.trainingDatasetManifestSha256,
    calibrationDatasetManifestSha256: authorization.calibrationDatasetManifestSha256,
    consentSnapshotSha256: authorization.consentSnapshotSha256,
    deletionLedgerSha256: authorization.deletionLedgerSha256,
    labelPolicySha256: authorization.labelPolicySha256,
    authorizedAt: authorization.authorizedAt,
    expiresAt: authorization.expiresAt,
    signatureBase64: authorization.signatureBase64,
  });
}

export function verifyOwnedAudioAdaptation(
  manifest: OwnedAudioAdaptationManifest,
  parent: AudioBakeoffCandidateManifest,
  parentResult: AudioBakeoffCandidateResult,
  selection: AudioBakeoffSelectionReport,
  charter: AudioBakeoffCharter,
  evaluationManifest: VerifiedEvaluationManifest,
  trainingDataset: AudioAdaptationDatasetManifest,
  calibrationDataset: AudioAdaptationDatasetManifest,
  authorization: AudioAdaptationAuthorization,
  verifiedAt: string,
): VerifiedOwnedAudioAdaptation {
  validateCandidate(parent);
  validateCharter(charter);
  validateResult(parentResult, charter);
  validateAdaptationDataset(trainingDataset, "training");
  validateAdaptationDataset(calibrationDataset, "calibration");
  requireCanonicalTimestamp(verifiedAt, "verifiedAt");
  if (!builtCandidateResults.has(parentResult) || !builtSelectionReports.has(selection)
    || audioBakeoffSelectionReportSha256(selection) !== selection.sha256
    || lockedEvaluationManifestEnvelopeSha256(evaluationManifest.manifest)
      !== charter.evaluationManifestEnvelopeSha256
    || !exactKeys(manifest, ["schemaVersion", "version", "strategy",
    "parentCandidateManifestSha256", "parentBakeoffResultSha256",
    "parentSelectionReportSha256", "trainingDatasetManifestSha256",
    "calibrationDatasetManifestSha256", "consentSnapshotSha256",
    "deletionLedgerSha256", "authorizationSha256", "labelPolicySha256", "trainingRecipeSha256",
    "trainingCodeSha256", "trainingContainerSha256", "outputCheckpointSha256",
    "randomSeeds", "trainedAt", "releasePosture", "learnerFeedbackEligible",
    "productionEligible", "sha256"])
    || manifest.schemaVersion !== "owned-audio-adaptation-manifest-v1"
    || !identifier(manifest.version)
    || !["owned-head", "parameter-efficient", "partial-fine-tune", "distilled-student"]
      .includes(manifest.strategy)
    || manifest.parentCandidateManifestSha256 !== parent.sha256
    || manifest.parentBakeoffResultSha256 !== parentResult.sha256
    || manifest.parentSelectionReportSha256 !== selection.sha256
    || selection.charterSha256 !== charter.sha256
    || evaluationManifest.sha256 !== charter.evaluationManifestSha256
    || !selection.ranked.some((item) => item.candidateId === parent.candidateId
      && item.resultSha256 === parentResult.sha256
      && item.candidateManifestSha256 === parent.sha256
      && item.rank !== null && item.rank <= 2)
    || !parentResult.adaptationEligible
    || parent.rights.derivativeTraining !== "approved"
    || manifest.trainingDatasetManifestSha256 !== trainingDataset.sha256
    || manifest.calibrationDatasetManifestSha256 !== calibrationDataset.sha256
    || manifest.trainingDatasetManifestSha256 === manifest.calibrationDatasetManifestSha256
    || manifest.labelPolicySha256 !== charter.labelPolicySha256
    || trainingDataset.labelPolicySha256 !== charter.labelPolicySha256
    || calibrationDataset.labelPolicySha256 !== charter.labelPolicySha256
    || manifest.consentSnapshotSha256 !== trainingDataset.consentSnapshotSha256
    || manifest.consentSnapshotSha256 !== calibrationDataset.consentSnapshotSha256
    || manifest.deletionLedgerSha256 !== trainingDataset.deletionLedgerSha256
    || manifest.deletionLedgerSha256 !== calibrationDataset.deletionLedgerSha256
    || manifest.authorizationSha256 !== authorization.sha256
    || !validAdaptationAuthorization(authorization, charter, manifest, selection, parentResult)
    || Date.parse(authorization.authorizedAt) < Date.parse(parentResult.evaluatedAt)
    || Date.parse(authorization.authorizedAt) < Date.parse(trainingDataset.lockedAt)
    || Date.parse(authorization.authorizedAt) < Date.parse(calibrationDataset.lockedAt)
    || !adaptationDatasetsAreDisjoint(trainingDataset, calibrationDataset,
      evaluationManifest.manifest)
    || !allHashes([manifest.trainingDatasetManifestSha256,
      manifest.calibrationDatasetManifestSha256, manifest.consentSnapshotSha256,
      manifest.deletionLedgerSha256, manifest.authorizationSha256, manifest.labelPolicySha256,
      manifest.trainingRecipeSha256, manifest.trainingCodeSha256,
      manifest.trainingContainerSha256, manifest.outputCheckpointSha256])
    || manifest.outputCheckpointSha256 === parent.weights.sha256
    || !Array.isArray(manifest.randomSeeds) || manifest.randomSeeds.length < 3
    || new Set(manifest.randomSeeds).size !== manifest.randomSeeds.length
    || manifest.randomSeeds.some((seed) => !Number.isSafeInteger(seed) || seed < 0)
    || !canonicalTimestamp(manifest.trainedAt)
    || Date.parse(manifest.trainedAt) < Date.parse(parentResult.evaluatedAt)
    || Date.parse(manifest.trainedAt) < Date.parse(trainingDataset.lockedAt)
    || Date.parse(manifest.trainedAt) < Date.parse(calibrationDataset.lockedAt)
    || Date.parse(manifest.trainedAt) < Date.parse(authorization.authorizedAt)
    || Date.parse(manifest.trainedAt) > Date.parse(authorization.expiresAt)
    || Date.parse(verifiedAt) < Date.parse(manifest.trainedAt)
    || manifest.releasePosture !== "research-adaptation-only"
    || manifest.learnerFeedbackEligible !== false
    || manifest.productionEligible !== false
    || ownedAudioAdaptationManifestSha256(manifest) !== manifest.sha256) {
    throw new TypeError("Owned adaptation lineage is incomplete or unsafe.");
  }
  return Object.freeze({
    manifest,
    verifiedAt,
    researchLineageStructurallyValid: true as const,
    learnerFeedbackEligible: false as const,
    productionEligible: false as const,
    [verifiedAdaptationMarker]: true as const,
  });
}

export function evaluationSamplesSha256(samples: readonly EvaluationSample[]): string {
  return digest([...samples]
    .sort((left, right) => compareText(left.attemptId, right.attemptId))
    .map((sample) => ({
      attemptId: sample.attemptId,
      label: sample.label,
      pCorrect: sample.pCorrect,
      pError: sample.pError,
      ambiguous: sample.ambiguous,
      latencyMilliseconds: sample.latencyMilliseconds,
      estimatedCostUsd: sample.estimatedCostUsd,
      subgroup: Object.fromEntries(Object.entries(sample.subgroup)
        .sort(([left], [right]) => compareText(left, right))),
    })));
}

export function evaluationReportSha256(report: EvaluationReport): string {
  return digest(canonicalEvaluationReport(report));
}

function validateAdaptationDataset(
  manifest: AudioAdaptationDatasetManifest,
  purpose: AudioAdaptationDatasetManifest["purpose"],
): void {
  if (!exactKeys(manifest, ["schemaVersion", "version", "purpose", "lockedAt",
    "labelPolicySha256", "consentSnapshotSha256", "deletionLedgerSha256", "items",
    "sha256"])
    || manifest.schemaVersion !== "audio-adaptation-dataset-manifest-v1"
    || !identifier(manifest.version) || manifest.purpose !== purpose
    || !canonicalTimestamp(manifest.lockedAt)
    || !allHashes([manifest.labelPolicySha256, manifest.consentSnapshotSha256,
      manifest.deletionLedgerSha256])
    || !Array.isArray(manifest.items) || manifest.items.length === 0
    || new Set(manifest.items.map((item) => item.attemptId)).size !== manifest.items.length
    || manifest.items.some((item) => !exactKeys(item, ["attemptId", "speakerHash",
      "householdHash", "deletionSubjectHash", "consentSnapshotHash"])
      || !identifier(item.attemptId)
      || !allHashes([item.speakerHash, item.householdHash, item.deletionSubjectHash,
        item.consentSnapshotHash]))
    || audioAdaptationDatasetManifestSha256(manifest) !== manifest.sha256) {
    throw new TypeError(`The ${purpose} dataset manifest is invalid.`);
  }
}

function validAdaptationAuthorization(
  authorization: AudioAdaptationAuthorization,
  charter: AudioBakeoffCharter,
  manifest: OwnedAudioAdaptationManifest,
  selection: AudioBakeoffSelectionReport,
  parentResult: AudioBakeoffCandidateResult,
): boolean {
  if (!exactKeys(authorization, ["schemaVersion", "keyId", "algorithm",
    "parentSelectionReportSha256", "parentBakeoffResultSha256",
    "trainingDatasetManifestSha256", "calibrationDatasetManifestSha256",
    "consentSnapshotSha256", "deletionLedgerSha256", "labelPolicySha256",
    "authorizedAt", "expiresAt", "signatureBase64", "sha256"])
    || authorization.schemaVersion !== "audio-adaptation-authorization-v1"
    || authorization.keyId !== charter.adaptationAuthority.keyId
    || authorization.algorithm !== "Ed25519"
    || authorization.parentSelectionReportSha256 !== selection.sha256
    || authorization.parentBakeoffResultSha256 !== parentResult.sha256
    || authorization.trainingDatasetManifestSha256 !== manifest.trainingDatasetManifestSha256
    || authorization.calibrationDatasetManifestSha256 !== manifest.calibrationDatasetManifestSha256
    || authorization.consentSnapshotSha256 !== manifest.consentSnapshotSha256
    || authorization.deletionLedgerSha256 !== manifest.deletionLedgerSha256
    || authorization.labelPolicySha256 !== charter.labelPolicySha256
    || !canonicalTimestamp(authorization.authorizedAt)
    || !canonicalTimestamp(authorization.expiresAt)
    || Date.parse(authorization.expiresAt) <= Date.parse(authorization.authorizedAt)
    || !validBase64(authorization.signatureBase64)
    || audioAdaptationAuthorizationSha256(authorization) !== authorization.sha256) return false;
  return verifyEd25519(
    charter.adaptationAuthority.publicKeyPem,
    audioAdaptationAuthorizationPayload(authorization),
    authorization.signatureBase64,
  );
}

function adaptationDatasetsAreDisjoint(
  training: AudioAdaptationDatasetManifest,
  calibration: AudioAdaptationDatasetManifest,
  evaluation: LockedEvaluationManifest,
): boolean {
  const groups = [training.items, calibration.items, evaluation.items];
  for (const key of ["speakerHash", "householdHash"] as const) {
    const seen = new Map<string, number>();
    for (const [groupIndex, items] of groups.entries()) {
      for (const item of items) {
        const prior = seen.get(item[key]);
        if (prior !== undefined && prior !== groupIndex) return false;
        seen.set(item[key], groupIndex);
      }
    }
  }
  return true;
}

function hardGateFailures(
  candidate: AudioBakeoffCandidateManifest,
  charter: AudioBakeoffCharter,
  report: EvaluationReport,
  subgroupGap: number,
  measurements: AudioBakeoffMeasurements,
): string[] {
  const failures: string[] = [];
  const overall = report.overall;
  const gate = charter.gates;
  if (overall.sampleCount < charter.minimumTestSamples) failures.push("minimum-test-samples");
  if (Object.values(report.subgroups).some((item) =>
    item.sampleCount < charter.minimumSubgroupSamples)) failures.push("minimum-subgroup-samples");
  if (Object.values(report.subgroups).some((item) =>
    item.correctCount < charter.minimumSubgroupCorrectSamples)) {
    failures.push("minimum-subgroup-correct-samples");
  }
  if (Object.values(report.subgroups).some((item) =>
    item.errorCount < charter.minimumSubgroupErrorSamples)) {
    failures.push("minimum-subgroup-error-samples");
  }
  if (Object.values(report.subgroups).some((item) =>
    item.falsePassRate === null || item.falseRejectRate === null)) {
    failures.push("subgroup-rate-unavailable");
  }
  if (overall.falsePassRate === null || overall.falsePassRate > gate.maximumFalsePassRate)
    failures.push("false-pass-rate");
  if (overall.falseRejectRate === null || overall.falseRejectRate > gate.maximumFalseRejectRate)
    failures.push("false-reject-rate");
  if (overall.abstentionRate > gate.maximumAbstentionRate) failures.push("abstention-rate");
  if (overall.conditionalExpectedCalibrationError === null
    || overall.conditionalExpectedCalibrationError > gate.maximumConditionalEce)
    failures.push("calibration-error");
  if (subgroupGap > gate.maximumSubgroupRateGap) failures.push("subgroup-rate-gap");
  if (overall.p95LatencyMilliseconds > gate.maximumP95LatencyMilliseconds)
    failures.push("latency");
  if (measurements.coldStartMilliseconds > gate.maximumColdStartMilliseconds)
    failures.push("cold-start");
  if (overall.averageCostUsd > gate.maximumAverageCostUsd) failures.push("cost");
  if (measurements.peakMemoryBytes > gate.maximumPeakMemoryBytes) failures.push("memory");
  if (measurements.modelBytes > gate.maximumModelBytes) failures.push("model-size");
  if (candidate.rights.benchmarkUse !== "approved") failures.push("benchmark-rights");
  if (candidate.rights.commercialHealthInference !== "approved")
    failures.push("commercial-health-rights");
  if (candidate.rights.derivativeTraining !== "approved") failures.push("derivative-rights");
  if (candidate.interface.usesPromptAwareDecoder) failures.push("prompt-aware-decoder");
  if (!candidate.interface.supportsConstrainedPhoneHead) failures.push("constrained-head-interface");
  if (candidate.interface.outputKind === "transcript" || candidate.interface.outputKind === "graphemes")
    failures.push("non-phone-output");
  return failures.sort(compareText);
}

function maximumSubgroupRateGap(report: EvaluationReport): number {
  const rates: (keyof Pick<EvaluationMetrics, "falsePassRate" | "falseRejectRate" | "abstentionRate">)[] = [
    "falsePassRate", "falseRejectRate", "abstentionRate",
  ];
  let maximum = 0;
  const byDimension = new Map<string, EvaluationMetrics[]>();
  for (const [name, subgroup] of Object.entries(report.subgroups)) {
    const dimension = name.slice(0, name.indexOf("="));
    const values = byDimension.get(dimension) ?? [];
    values.push(subgroup);
    byDimension.set(dimension, values);
  }
  for (const subgroups of byDimension.values()) {
    for (const key of rates) {
      const values = subgroups.map((subgroup) => subgroup[key]);
      if (values.some((value) => value === null)) return Number.POSITIVE_INFINITY;
      const measured = values as number[];
      maximum = Math.max(maximum, Math.max(...measured) - Math.min(...measured));
    }
  }
  return maximum;
}

function validateCandidate(candidate: AudioBakeoffCandidateManifest): void {
  if (!exactKeys(candidate, ["schemaVersion", "candidateId", "version", "role",
    "strategy", "code", "weights", "trainingDataLineageSha256",
    "legalReviewEvidenceSha256", "rights", "interface", "releasePosture",
    "learnerFeedbackEligible", "productionEligible", "sha256"])
    || candidate.schemaVersion !== "audio-bakeoff-candidate-v1"
    || !identifier(candidate.candidateId) || !identifier(candidate.version)
    || !["primary-baseline", "challenger", "framework", "reference"].includes(candidate.role)
    || !["frozen-open-encoder-owned-head", "owned-engineered-feature-baseline",
      "reference-only"].includes(candidate.strategy)
    || !validArtifact(candidate.code) || !validArtifact(candidate.weights)
    || !allHashes([candidate.trainingDataLineageSha256,
      candidate.legalReviewEvidenceSha256])
    || !validRights(candidate.rights) || !validInterface(candidate.interface)
    || candidate.releasePosture !== "research-candidate-only"
    || candidate.learnerFeedbackEligible !== false || candidate.productionEligible !== false
    || audioBakeoffCandidateManifestSha256(candidate) !== candidate.sha256) {
    throw new TypeError("Audio bake-off candidate provenance is invalid.");
  }
}

function validateCharter(charter: AudioBakeoffCharter): void {
  if (!exactKeys(charter, ["schemaVersion", "version", "lockedAt",
    "evaluationManifestSha256", "evaluationManifestEnvelopeSha256",
    "evaluationReferenceSha256", "stage", "requiredCandidateIds",
    "referenceCandidateIds", "candidateManifestSha256ById", "candidateRoleById",
    "subgroupKeys", "thresholdVersion", "thresholdsSha256", "lexiconVersion",
    "scoringPolicyVersion", "identicalHeadRecipeSha256", "calibrationRecipeSha256",
    "deploymentProtocolSha256", "labelPolicySha256", "scorecardRubricSha256",
    "scorecardAuthority", "runAuthority", "adaptationAuthority",
    "legalPolicyVersion", "minimumTestSamples", "minimumSubgroupSamples",
    "minimumSubgroupCorrectSamples", "minimumSubgroupErrorSamples", "gates",
    "weights", "sha256"])
    || charter.schemaVersion !== "audio-bakeoff-charter-v1"
    || !identifier(charter.version) || !canonicalTimestamp(charter.lockedAt)
    || !allHashes([charter.evaluationManifestSha256,
      charter.evaluationManifestEnvelopeSha256, charter.evaluationReferenceSha256,
      charter.thresholdsSha256, charter.scorecardRubricSha256])
    || charter.stage !== "frozen-encoder-owned-head"
    || !uniqueIdentifiers(charter.requiredCandidateIds, 3)
    || !uniqueIdentifiers(charter.referenceCandidateIds, 2)
    || charter.referenceCandidateIds.some((id) => charter.requiredCandidateIds.includes(id))
    || !validLockedCandidateRecords(charter)
    || !uniqueIdentifiers(charter.subgroupKeys, 1)
    || !identifier(charter.thresholdVersion) || !identifier(charter.lexiconVersion)
    || !identifier(charter.scoringPolicyVersion)
    || !allHashes([charter.identicalHeadRecipeSha256, charter.calibrationRecipeSha256,
      charter.deploymentProtocolSha256, charter.labelPolicySha256])
    || !validAuthority(charter.scorecardAuthority)
    || !validAuthority(charter.runAuthority)
    || !validAuthority(charter.adaptationAuthority)
    || !identifier(charter.legalPolicyVersion)
    || !positiveInteger(charter.minimumTestSamples)
    || !positiveInteger(charter.minimumSubgroupSamples)
    || !positiveInteger(charter.minimumSubgroupCorrectSamples)
    || !positiveInteger(charter.minimumSubgroupErrorSamples)
    || charter.minimumSubgroupCorrectSamples + charter.minimumSubgroupErrorSamples
      > charter.minimumSubgroupSamples
    || !validGates(charter.gates) || !validWeights(charter.weights)
    || audioBakeoffCharterSha256(charter) !== charter.sha256) {
    throw new TypeError("A strict predeclared audio bake-off charter is required.");
  }
}

function validateMeasurements(
  value: AudioBakeoffMeasurements,
  candidateId: string,
  charter: AudioBakeoffCharter,
): void {
  if (!exactKeys(value, ["modelBytes", "peakMemoryBytes", "coldStartMilliseconds", "scorecard"])
    || !positiveInteger(value.modelBytes) || !positiveInteger(value.peakMemoryBytes)
    || !nonnegative(value.coldStartMilliseconds)
    || !exactKeys(value.scorecard, ["rubricSha256", "scorerKeyId", "scores", "evidence",
      "signatureBase64"])
    || value.scorecard.rubricSha256 !== charter.scorecardRubricSha256
    || value.scorecard.scorerKeyId !== charter.scorecardAuthority.keyId
    || !exactKeys(value.scorecard.scores, bakeoffDimensions)
    || !exactKeys(value.scorecard.evidence, bakeoffDimensions)
    || bakeoffDimensions.some((dimension) =>
      !Number.isFinite(value.scorecard.scores[dimension])
      || value.scorecard.scores[dimension] < 0
      || value.scorecard.scores[dimension] > 100
      || !hash(value.scorecard.evidence[dimension]))
    || !validBase64(value.scorecard.signatureBase64)
    || !verifyEd25519(
      charter.scorecardAuthority.publicKeyPem,
      scorecardAttestationPayload(candidateId, value.scorecard),
      value.scorecard.signatureBase64,
    )) {
    throw new TypeError("Bake-off measurements and scorecard are invalid.");
  }
}

function validateRunAttestation(
  attestation: AudioBakeoffRunAttestation,
  charter: AudioBakeoffCharter,
  evidence: AudioBakeoffRunEvidence,
): void {
  if (!exactKeys(attestation, ["keyId", "algorithm", "calibrationArtifactSha256",
    "calibrationManifestSha256", "calibrationRecipeSha256", "deploymentProtocolSha256",
    "signatureBase64"])
    || attestation.keyId !== charter.runAuthority.keyId
    || attestation.algorithm !== "Ed25519"
    || !allHashes([attestation.calibrationArtifactSha256,
      attestation.calibrationManifestSha256, attestation.calibrationRecipeSha256,
      attestation.deploymentProtocolSha256])
    || attestation.calibrationManifestSha256 !== charter.evaluationManifestEnvelopeSha256
    || attestation.calibrationRecipeSha256 !== charter.calibrationRecipeSha256
    || attestation.deploymentProtocolSha256 !== charter.deploymentProtocolSha256
    || !validBase64(attestation.signatureBase64)
    || !verifyEd25519(
      charter.runAuthority.publicKeyPem,
      audioBakeoffRunAttestationPayload(evidence, attestation),
      attestation.signatureBase64,
    )) {
    throw new TypeError("A signed charter-authorized full-run attestation is required.");
  }
}

function validateBakeoffSamples(
  samples: readonly EvaluationSample[],
  charter: AudioBakeoffCharter,
): void {
  if (!Array.isArray(samples) || samples.length === 0
    || samples.some((sample) => !exactKeys(sample, ["attemptId", "label", "pCorrect",
      "pError", "ambiguous", "latencyMilliseconds", "estimatedCostUsd", "subgroup"])
      || !identifier(sample.attemptId)
      || !["correct", "error"].includes(sample.label)
      || !probability(sample.pCorrect) || !probability(sample.pError)
      || sample.pCorrect + sample.pError > 1 + 1e-9
      || typeof sample.ambiguous !== "boolean"
      || !nonnegative(sample.latencyMilliseconds)
      || !nonnegative(sample.estimatedCostUsd)
      || !exactKeys(sample.subgroup, charter.subgroupKeys)
      || Object.values(sample.subgroup).some((value) =>
        typeof value !== "string" || value.length < 1 || value.length > 80))) {
    throw new TypeError("Bake-off samples must use the strict charter-bound schema.");
  }
}

function validateResult(result: AudioBakeoffCandidateResult, charter: AudioBakeoffCharter): void {
  if (result.schemaVersion !== "audio-bakeoff-candidate-result-v1"
    || result.charterSha256 !== charter.sha256
    || result.evaluationManifestSha256 !== charter.evaluationManifestSha256
    || result.headRecipeSha256 !== charter.identicalHeadRecipeSha256
    || evaluationReportSha256(result.evaluationReport) !== result.evaluationReportSha256
    || audioBakeoffCandidateResultSha256(result) !== result.sha256
    || result.releasePosture !== "research-comparison-only"
    || result.learnerFeedbackEligible !== false || result.productionEligible !== false) {
    throw new TypeError("A bake-off result is invalid or not charter-bound.");
  }
}

function canonicalCandidate(candidate: Omit<AudioBakeoffCandidateManifest, "sha256">) {
  return {
    schemaVersion: candidate.schemaVersion,
    candidateId: candidate.candidateId,
    version: candidate.version,
    role: candidate.role,
    strategy: candidate.strategy,
    code: {
      repository: candidate.code.repository,
      revision: candidate.code.revision,
      sha256: candidate.code.sha256,
      licenseIdentifier: candidate.code.licenseIdentifier,
    },
    weights: {
      artifactId: candidate.weights.artifactId,
      revision: candidate.weights.revision,
      sha256: candidate.weights.sha256,
      licenseIdentifier: candidate.weights.licenseIdentifier,
    },
    trainingDataLineageSha256: candidate.trainingDataLineageSha256,
    legalReviewEvidenceSha256: candidate.legalReviewEvidenceSha256,
    rights: {
      benchmarkUse: candidate.rights.benchmarkUse,
      commercialHealthInference: candidate.rights.commercialHealthInference,
      derivativeTraining: candidate.rights.derivativeTraining,
      redistribution: candidate.rights.redistribution,
      mobileBundling: candidate.rights.mobileBundling,
    },
    interface: {
      outputKind: candidate.interface.outputKind,
      usesPromptAwareDecoder: candidate.interface.usesPromptAwareDecoder,
      supportsConstrainedPhoneHead: candidate.interface.supportsConstrainedPhoneHead,
    },
    releasePosture: candidate.releasePosture,
    learnerFeedbackEligible: candidate.learnerFeedbackEligible,
    productionEligible: candidate.productionEligible,
  };
}

function canonicalEvaluationReport(report: EvaluationReport) {
  return {
    manifestSha256: report.manifestSha256,
    thresholdVersion: report.thresholdVersion,
    lexiconVersion: report.lexiconVersion,
    calibrationVersion: report.calibrationVersion,
    scoringPolicyVersion: report.scoringPolicyVersion,
    overall: canonicalMetrics(report.overall),
    subgroups: Object.fromEntries(Object.entries(report.subgroups)
      .sort(([left], [right]) => compareText(left, right))
      .map(([key, value]) => [key, canonicalMetrics(value)])),
  };
}

function canonicalMetrics(value: EvaluationMetrics) {
  return {
    sampleCount: value.sampleCount,
    correctCount: value.correctCount,
    errorCount: value.errorCount,
    decidedCount: value.decidedCount,
    falsePassRate: value.falsePassRate,
    falseRejectRate: value.falseRejectRate,
    abstentionRate: value.abstentionRate,
    conditionalExpectedCalibrationError: value.conditionalExpectedCalibrationError,
    p95LatencyMilliseconds: value.p95LatencyMilliseconds,
    averageCostUsd: value.averageCostUsd,
  };
}

function canonicalMeasurements(value: AudioBakeoffMeasurements) {
  return {
    modelBytes: value.modelBytes,
    peakMemoryBytes: value.peakMemoryBytes,
    coldStartMilliseconds: value.coldStartMilliseconds,
    scorecard: {
      rubricSha256: value.scorecard.rubricSha256,
      scorerKeyId: value.scorecard.scorerKeyId,
      scores: canonicalDimensions(value.scorecard.scores),
      evidence: canonicalDimensions(value.scorecard.evidence),
      signatureBase64: value.scorecard.signatureBase64,
    },
  };
}

function canonicalRunAttestation(
  value: Omit<AudioBakeoffRunAttestation, "signatureBase64"> | AudioBakeoffRunAttestation,
) {
  return {
    keyId: value.keyId,
    algorithm: value.algorithm,
    calibrationArtifactSha256: value.calibrationArtifactSha256,
    calibrationManifestSha256: value.calibrationManifestSha256,
    calibrationRecipeSha256: value.calibrationRecipeSha256,
    deploymentProtocolSha256: value.deploymentProtocolSha256,
  };
}

function canonicalDimensions<T>(values: Readonly<Record<BakeoffDimension, T>>): Record<BakeoffDimension, T> {
  return Object.fromEntries(bakeoffDimensions.map((dimension) =>
    [dimension, values[dimension]])) as Record<BakeoffDimension, T>;
}

function canonicalStringRecord<T>(values: Readonly<Record<string, T>>): Record<string, T> {
  return Object.fromEntries(Object.entries(values).sort(([left], [right]) =>
    compareText(left, right)));
}

function canonicalAuthority(
  authority: AudioBakeoffCharter["scorecardAuthority"],
) {
  return { keyId: authority.keyId, publicKeyPem: authority.publicKeyPem };
}

function canonicalAdaptationDatasetItem(item: AudioAdaptationDatasetManifestItem) {
  return {
    attemptId: item.attemptId,
    speakerHash: item.speakerHash,
    householdHash: item.householdHash,
    deletionSubjectHash: item.deletionSubjectHash,
    consentSnapshotHash: item.consentSnapshotHash,
  };
}

function canonicalGates(gates: AudioBakeoffCharter["gates"]) {
  return {
    maximumFalsePassRate: gates.maximumFalsePassRate,
    maximumFalseRejectRate: gates.maximumFalseRejectRate,
    maximumAbstentionRate: gates.maximumAbstentionRate,
    maximumConditionalEce: gates.maximumConditionalEce,
    maximumSubgroupRateGap: gates.maximumSubgroupRateGap,
    maximumP95LatencyMilliseconds: gates.maximumP95LatencyMilliseconds,
    maximumColdStartMilliseconds: gates.maximumColdStartMilliseconds,
    maximumAverageCostUsd: gates.maximumAverageCostUsd,
    maximumPeakMemoryBytes: gates.maximumPeakMemoryBytes,
    maximumModelBytes: gates.maximumModelBytes,
  };
}

function validGates(gates: AudioBakeoffCharter["gates"]): boolean {
  return exactKeys(gates, ["maximumFalsePassRate", "maximumFalseRejectRate",
    "maximumAbstentionRate", "maximumConditionalEce", "maximumSubgroupRateGap",
    "maximumP95LatencyMilliseconds", "maximumColdStartMilliseconds", "maximumAverageCostUsd",
    "maximumPeakMemoryBytes", "maximumModelBytes"])
    && [gates.maximumFalsePassRate, gates.maximumFalseRejectRate,
      gates.maximumAbstentionRate, gates.maximumConditionalEce,
      gates.maximumSubgroupRateGap].every(probability)
    && nonnegative(gates.maximumP95LatencyMilliseconds)
    && nonnegative(gates.maximumColdStartMilliseconds)
    && nonnegative(gates.maximumAverageCostUsd)
    && positiveInteger(gates.maximumPeakMemoryBytes)
    && positiveInteger(gates.maximumModelBytes);
}

function validWeights(weights: Readonly<Record<BakeoffDimension, number>>): boolean {
  return exactKeys(weights, bakeoffDimensions)
    && bakeoffDimensions.every((dimension) => probability(weights[dimension]))
    && Math.abs(bakeoffDimensions.reduce((sum, dimension) =>
      sum + weights[dimension], 0) - 1) < 1e-9;
}

function validLockedCandidateRecords(charter: AudioBakeoffCharter): boolean {
  const ids = [...charter.requiredCandidateIds, ...charter.referenceCandidateIds].sort(compareText);
  if (!exactKeys(charter.candidateManifestSha256ById, ids)
    || !exactKeys(charter.candidateRoleById, ids)) return false;
  return ids.every((id) => hash(charter.candidateManifestSha256ById[id])
    && ["primary-baseline", "challenger", "framework", "reference"]
      .includes(charter.candidateRoleById[id]!))
    && charter.referenceCandidateIds.every((id) =>
      charter.candidateRoleById[id] === "reference")
    && charter.requiredCandidateIds.every((id) =>
      charter.candidateRoleById[id] !== "reference");
}

function validAuthority(authority: AudioBakeoffCharter["scorecardAuthority"]): boolean {
  if (!exactKeys(authority, ["keyId", "publicKeyPem"]) || !identifier(authority.keyId)
    || typeof authority.publicKeyPem !== "string") return false;
  try {
    return createPublicKey(authority.publicKeyPem).asymmetricKeyType === "ed25519";
  } catch {
    return false;
  }
}

function verifyEd25519(publicKeyPem: string, payload: string, signatureBase64: string): boolean {
  try {
    const key = createPublicKey(publicKeyPem);
    return key.asymmetricKeyType === "ed25519"
      && verifySignature(null, Buffer.from(payload, "utf8"), key,
        Buffer.from(signatureBase64, "base64"));
  } catch {
    return false;
  }
}

function validBase64(value: unknown): value is string {
  return typeof value === "string" && value.length > 0
    && Buffer.from(value, "base64").toString("base64") === value;
}

function weightedScore(
  scores: Readonly<Record<BakeoffDimension, number>>,
  weights: Readonly<Record<BakeoffDimension, number>>,
): number {
  return bakeoffDimensions.reduce((sum, dimension) =>
    sum + scores[dimension] * weights[dimension], 0);
}

function validArtifact(
  value: AudioBakeoffCandidateManifest["code"] | AudioBakeoffCandidateManifest["weights"],
): boolean {
  const locator = "repository" in value ? value.repository : value.artifactId;
  const locatorKey = "repository" in value ? "repository" : "artifactId";
  return exactKeys(value, [locatorKey, "revision", "sha256", "licenseIdentifier"])
    && typeof locator === "string" && locator.length >= 3
    && identifier(value.revision) && hash(value.sha256)
    && typeof value.licenseIdentifier === "string"
    && value.licenseIdentifier.length >= 2 && value.licenseIdentifier.length <= 80;
}

function validRights(value: AudioBakeoffCandidateManifest["rights"]): boolean {
  return exactKeys(value, ["benchmarkUse", "commercialHealthInference",
    "derivativeTraining", "redistribution", "mobileBundling"])
    && Object.values(value).every((item) =>
      ["approved", "restricted", "unverified"].includes(item));
}

function validInterface(value: AudioBakeoffCandidateManifest["interface"]): boolean {
  return exactKeys(value, ["outputKind", "usesPromptAwareDecoder",
    "supportsConstrainedPhoneHead"])
    && ["phone-posteriors", "aligned-embeddings", "engineered-features",
      "graphemes", "transcript"].includes(value.outputKind)
    && typeof value.usesPromptAwareDecoder === "boolean"
    && typeof value.supportsConstrainedPhoneHead === "boolean";
}

function uniqueIdentifiers(values: readonly string[], minimum: number): boolean {
  return Array.isArray(values) && values.length >= minimum
    && new Set(values).size === values.length && values.every(identifier);
}

function allHashes(values: readonly string[]): boolean {
  return values.every(hash);
}

function requireHash(value: unknown, label: string): asserts value is string {
  if (!hash(value)) throw new TypeError(`${label} SHA-256 is invalid.`);
}

function requireCanonicalTimestamp(value: unknown, label: string): asserts value is string {
  if (!canonicalTimestamp(value)) throw new TypeError(`${label} must be a canonical timestamp.`);
}

function canonicalTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString() === value;
}

function identifier(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/.test(value);
}

function hash(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

function probability(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

function nonnegative(value: number): boolean {
  return Number.isFinite(value) && value >= 0;
}

function positiveInteger(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0;
}

function exactKeys(value: unknown, expected: readonly string[]): boolean {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort(compareText);
  const wanted = [...expected].sort(compareText);
  return actual.length === wanted.length
    && actual.every((key, index) => key === wanted[index]);
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}
