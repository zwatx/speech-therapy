// Generated from schema/attempt-evaluation.schema.json. Do not edit by hand.

export const targetProtocolIds = [
  "bilabial-closure-v1",
  "labiodental-contact-v1",
  "interdental-visibility-v1",
  "l-tip-lift-research-v1",
  "audio-only-v1"
] as const;
export type TargetProtocolId = (typeof targetProtocolIds)[number];

export const captureReasonCodes = [
  "audio-clipping",
  "audio-too-quiet",
  "utterance-too-short",
  "utterance-too-long",
  "background-noise",
  "multiple-speakers",
  "face-out-of-frame",
  "mouth-occluded",
  "video-unavailable"
] as const;
export type CaptureReasonCode = (typeof captureReasonCodes)[number];

export const likelyErrorKinds = [
  "substitution",
  "omission",
  "distortion",
  "timing"
] as const;
export type LikelyError = (typeof likelyErrorKinds)[number];

export const routingDecisionKinds = [
  "blocked-consent",
  "retry-capture",
  "correct",
  "retry-or-abstain",
  "audio-cue-or-review",
  "needs-deep-analysis"
] as const;
export type RoutingDecisionKind = (typeof routingDecisionKinds)[number];

export const routingDecisionReasons = [
  "audio-processing-not-consented",
  "capture-quality-below-floor",
  "confident-correct",
  "audio-evidence-uncertain",
  "visual-protocol-not-eligible",
  "video-processing-not-consented",
  "video-quality-below-floor",
  "confident-mismatch-on-supported-target"
] as const;
export type RoutingDecisionReason = (typeof routingDecisionReasons)[number];

export const learnerAttemptStatuses = [
  "accepted-silent",
  "retry-capture"
] as const;
export type LearnerAttemptStatus = (typeof learnerAttemptStatuses)[number];

export interface CaptureQuality {
  readonly audioScore: number;
  readonly videoScore?: number;
  readonly reasonCodes: readonly CaptureReasonCode[];
}

export interface AudioEvidence {
  readonly pCorrect: number;
  readonly pError: number;
  readonly calibrated: boolean;
  readonly ambiguous: boolean;
  readonly likelyError?: LikelyError;
}

export interface ConsentSnapshot {
  readonly audioProcessing: boolean;
  readonly videoProcessing: boolean;
  readonly clinicianReview: boolean;
  readonly researchUse: boolean;
}

export interface AttemptEvaluationRequest {
  readonly attemptId: string;
  readonly protocolId: TargetProtocolId;
  readonly quality: CaptureQuality;
  readonly audio: AudioEvidence;
  readonly consent: ConsentSnapshot;
}

export interface RoutingDecision {
  readonly kind: RoutingDecisionKind;
  readonly runDeepVision: boolean;
  readonly reason: RoutingDecisionReason;
  readonly protocolId: TargetProtocolId;
  readonly protocolRegistryVersion: string;
  readonly thresholdVersion: string;
  readonly clinicianReviewPermitted: boolean;
  readonly researchUsePermitted: boolean;
}

export interface AttemptEvaluationResponse {
  readonly attemptId: string;
  readonly decision: RoutingDecision;
}

export interface LearnerAttemptReceipt {
  readonly attemptId: string;
  readonly status: LearnerAttemptStatus;
  readonly feedbackAvailable: boolean;
  readonly mediaRetained: boolean;
  readonly reasonCodes: readonly CaptureReasonCode[];
}
