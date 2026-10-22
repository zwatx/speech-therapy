import type { TargetProtocolId } from "@speech-therapy/contracts";

export {
  captureReasonCodes,
  likelyErrorKinds,
  routingDecisionKinds,
  routingDecisionReasons,
  targetProtocolIds,
} from "@speech-therapy/contracts";
export type {
  AttemptEvaluationRequest,
  AttemptEvaluationResponse,
  AudioEvidence,
  CaptureQuality,
  CaptureReasonCode,
  ConsentSnapshot,
  LikelyError,
  RoutingDecision,
  RoutingDecisionKind,
  RoutingDecisionReason,
  TargetProtocolId,
} from "@speech-therapy/contracts";

export type TargetProtocolStatus =
  | "candidate"
  | "validated"
  | "research"
  | "audio-only";

export interface TargetProtocol {
  id: TargetProtocolId;
  label: string;
  phonemes: readonly string[];
  status: TargetProtocolStatus;
  visualCue:
    | "bilabial-closure"
    | "labiodental-contact"
    | "interdental-visibility"
    | "tongue-tip-lift"
    | null;
}

export interface TargetProtocolRegistry {
  version: string;
  protocols: Record<TargetProtocolId, TargetProtocol>;
}

export interface ThresholdPolicy {
  version: string;
  audioQualityFloor: number;
  videoQualityFloor: number;
  passThreshold: number;
  analysisThreshold: number;
}
