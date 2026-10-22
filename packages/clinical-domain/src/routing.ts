import { targetProtocolRegistry } from "./protocols.ts";
import type {
  AttemptEvaluationRequest,
  RoutingDecision,
  TargetProtocolRegistry,
  ThresholdPolicy,
} from "./types.ts";

export const defaultThresholdPolicy: ThresholdPolicy = {
  version: "foundation-v1",
  audioQualityFloor: 0.65,
  videoQualityFloor: 0.7,
  passThreshold: 0.88,
  analysisThreshold: 0.72,
};

const audioBlockingReasonCodes = new Set([
  "audio-clipping",
  "multiple-speakers",
]);

const videoBlockingReasonCodes = new Set([
  "face-out-of-frame",
  "mouth-occluded",
  "video-unavailable",
]);

const externallyObservableVisualCues = new Set([
  "bilabial-closure",
  "labiodental-contact",
  "interdental-visibility",
]);

export function routeAttempt(
  attempt: AttemptEvaluationRequest,
  thresholds: ThresholdPolicy = defaultThresholdPolicy,
  registry: TargetProtocolRegistry = targetProtocolRegistry,
): RoutingDecision {
  const base = {
    protocolId: attempt.protocolId,
    protocolRegistryVersion: registry.version,
    thresholdVersion: thresholds.version,
    clinicianReviewPermitted: attempt.consent.clinicianReview,
    researchUsePermitted: attempt.consent.researchUse,
  } as const;

  if (!attempt.consent.audioProcessing) {
    return {
      ...base,
      kind: "blocked-consent",
      runDeepVision: false,
      reason: "audio-processing-not-consented",
    };
  }

  if (
    attempt.quality.audioScore < thresholds.audioQualityFloor ||
    attempt.quality.reasonCodes.some((reason) =>
      audioBlockingReasonCodes.has(reason),
    )
  ) {
    return {
      ...base,
      kind: "retry-capture",
      runDeepVision: false,
      reason: "capture-quality-below-floor",
    };
  }

  if (
    attempt.audio.calibrated &&
    !attempt.audio.ambiguous &&
    attempt.audio.pCorrect >= thresholds.passThreshold
  ) {
    return {
      ...base,
      kind: "correct",
      runDeepVision: false,
      reason: "confident-correct",
    };
  }

  if (
    !attempt.audio.calibrated ||
    attempt.audio.ambiguous ||
    attempt.audio.pError < thresholds.analysisThreshold
  ) {
    return {
      ...base,
      kind: "retry-or-abstain",
      runDeepVision: false,
      reason: "audio-evidence-uncertain",
    };
  }

  const protocol = registry.protocols[attempt.protocolId];
  if (
    protocol.status !== "validated" ||
    protocol.visualCue === null ||
    !externallyObservableVisualCues.has(protocol.visualCue)
  ) {
    return {
      ...base,
      kind: "audio-cue-or-review",
      runDeepVision: false,
      reason: "visual-protocol-not-eligible",
    };
  }

  if (!attempt.consent.videoProcessing) {
    return {
      ...base,
      kind: "audio-cue-or-review",
      runDeepVision: false,
      reason: "video-processing-not-consented",
    };
  }

  if (
    attempt.quality.videoScore === undefined ||
    attempt.quality.videoScore < thresholds.videoQualityFloor ||
    attempt.quality.reasonCodes.some((reason) =>
      videoBlockingReasonCodes.has(reason),
    )
  ) {
    return {
      ...base,
      kind: "audio-cue-or-review",
      runDeepVision: false,
      reason: "video-quality-below-floor",
    };
  }

  return {
    ...base,
    kind: "needs-deep-analysis",
    runDeepVision: true,
    reason: "confident-mismatch-on-supported-target",
  };
}
