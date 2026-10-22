import type { AudioEvidence } from "@speech-therapy/contracts";

export type PronunciationHypothesisKind =
  | "expected"
  | "acceptable-variant"
  | "omission"
  | "substitution"
  | "distortion-proxy"
  | "timing-proxy";

interface PronunciationHypothesisBase {
  readonly id: string;
  readonly phones: readonly string[];
}

export type PronunciationHypothesis =
  | (PronunciationHypothesisBase & {
      readonly kind: "expected" | "acceptable-variant";
      readonly likelyError?: never;
    })
  | (PronunciationHypothesisBase & {
      readonly kind: "omission";
      readonly likelyError: "omission";
    })
  | (PronunciationHypothesisBase & {
      readonly kind: "substitution";
      readonly likelyError: "substitution";
    })
  | (PronunciationHypothesisBase & {
      readonly kind: "distortion-proxy";
      readonly likelyError: "distortion";
    })
  | (PronunciationHypothesisBase & {
      readonly kind: "timing-proxy";
      readonly likelyError: "timing";
    });

export interface ClinicalLexiconEntry {
  readonly id: string;
  readonly version: string;
  readonly prompt: string;
  readonly targetPhone: string;
  readonly hypotheses: readonly PronunciationHypothesis[];
}

export type FramePosterior = Readonly<Record<string, number>>;

export interface CalibrationArtifact {
  readonly version: string;
  readonly datasetManifestHash: string;
  readonly temperature: number;
  readonly bias: number;
  readonly validated: boolean;
  readonly fitSplit: "calibration";
  readonly speakerIndependent: boolean;
  readonly householdIndependent: boolean;
}

export interface AudioScoringPolicy {
  readonly version: string;
  readonly blankToken: string;
  readonly minimumHypothesisCoverage: number;
  readonly ambiguityMargin: number;
}

export interface HypothesisScore {
  readonly id: string;
  readonly kind: PronunciationHypothesisKind;
  readonly logProbability: number;
}

export interface ConstrainedAudioScore {
  readonly evidence: AudioEvidence;
  readonly hypothesisCoverage: number;
  readonly conditionalCorrectProbability: number;
  readonly lexiconVersion: string;
  readonly calibrationVersion: string;
  readonly scoringPolicyVersion: string;
  readonly hypothesisScores: readonly HypothesisScore[];
}

export type DatasetSplit = "train" | "calibration" | "test";

export interface EvaluationManifestItem {
  readonly attemptId: string;
  readonly speakerHash: string;
  readonly householdHash: string;
  readonly split: DatasetSplit;
  readonly targetProtocolId: string;
}

export interface LockedEvaluationManifest {
  readonly version: string;
  readonly sha256: string;
  readonly lockedAt: string;
  readonly items: readonly EvaluationManifestItem[];
}

export type EvaluationLabel = "correct" | "error";

export interface EvaluationSample {
  readonly attemptId: string;
  readonly label: EvaluationLabel;
  readonly pCorrect: number;
  readonly pError: number;
  readonly ambiguous: boolean;
  readonly latencyMilliseconds: number;
  readonly estimatedCostUsd: number;
  readonly subgroup: Readonly<Record<string, string>>;
}

export interface EvaluationThresholds {
  readonly version: string;
  readonly passThreshold: number;
  readonly analysisThreshold: number;
}

export interface EvaluationMetrics {
  readonly sampleCount: number;
  readonly correctCount: number;
  readonly errorCount: number;
  readonly decidedCount: number;
  readonly falsePassRate: number | null;
  readonly falseRejectRate: number | null;
  readonly abstentionRate: number;
  readonly conditionalExpectedCalibrationError: number | null;
  readonly p95LatencyMilliseconds: number;
  readonly averageCostUsd: number;
}

export interface EvaluationReport {
  readonly manifestSha256: string;
  readonly thresholdVersion: string;
  readonly lexiconVersion: string;
  readonly calibrationVersion: string;
  readonly scoringPolicyVersion: string;
  readonly overall: EvaluationMetrics;
  readonly subgroups: Readonly<Record<string, EvaluationMetrics>>;
}

export interface EvaluationArtifactVersions {
  readonly lexiconVersion: string;
  readonly calibrationVersion: string;
  readonly scoringPolicyVersion: string;
}
