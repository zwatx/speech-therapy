// Generated from schema/attempt-evaluation.schema.json. Do not edit by hand.
import Foundation

public enum TargetProtocolID: String, Codable, CaseIterable, Sendable {
  case bilabialClosureV1 = "bilabial-closure-v1"
  case labiodentalContactV1 = "labiodental-contact-v1"
  case interdentalVisibilityV1 = "interdental-visibility-v1"
  case lTipLiftResearchV1 = "l-tip-lift-research-v1"
  case audioOnlyV1 = "audio-only-v1"
}

public enum CaptureReasonCode: String, Codable, CaseIterable, Sendable {
  case audioClipping = "audio-clipping"
  case audioTooQuiet = "audio-too-quiet"
  case utteranceTooShort = "utterance-too-short"
  case utteranceTooLong = "utterance-too-long"
  case backgroundNoise = "background-noise"
  case multipleSpeakers = "multiple-speakers"
  case faceOutOfFrame = "face-out-of-frame"
  case mouthOccluded = "mouth-occluded"
  case videoUnavailable = "video-unavailable"
}

public enum LikelyError: String, Codable, CaseIterable, Sendable {
  case substitution = "substitution"
  case omission = "omission"
  case distortion = "distortion"
  case timing = "timing"
}

public enum RoutingDecisionKind: String, Codable, CaseIterable, Sendable {
  case blockedConsent = "blocked-consent"
  case retryCapture = "retry-capture"
  case correct = "correct"
  case retryOrAbstain = "retry-or-abstain"
  case audioCueOrReview = "audio-cue-or-review"
  case needsDeepAnalysis = "needs-deep-analysis"
}

public enum RoutingDecisionReason: String, Codable, CaseIterable, Sendable {
  case audioProcessingNotConsented = "audio-processing-not-consented"
  case captureQualityBelowFloor = "capture-quality-below-floor"
  case confidentCorrect = "confident-correct"
  case audioEvidenceUncertain = "audio-evidence-uncertain"
  case visualProtocolNotEligible = "visual-protocol-not-eligible"
  case videoProcessingNotConsented = "video-processing-not-consented"
  case videoQualityBelowFloor = "video-quality-below-floor"
  case confidentMismatchOnSupportedTarget = "confident-mismatch-on-supported-target"
}

public enum LearnerAttemptStatus: String, Codable, CaseIterable, Sendable {
  case acceptedSilent = "accepted-silent"
  case retryCapture = "retry-capture"
}

public struct CaptureQuality: Codable, Equatable, Sendable {
  public let audioScore: Double
  public let videoScore: Double?
  public let reasonCodes: [CaptureReasonCode]

  public init(
    audioScore: Double,
    videoScore: Double?,
    reasonCodes: [CaptureReasonCode]
  ) {
    self.audioScore = audioScore
    self.videoScore = videoScore
    self.reasonCodes = reasonCodes
  }
}

public struct AudioEvidence: Codable, Equatable, Sendable {
  public let pCorrect: Double
  public let pError: Double
  public let calibrated: Bool
  public let ambiguous: Bool
  public let likelyError: LikelyError?

  public init(
    pCorrect: Double,
    pError: Double,
    calibrated: Bool,
    ambiguous: Bool,
    likelyError: LikelyError?
  ) {
    self.pCorrect = pCorrect
    self.pError = pError
    self.calibrated = calibrated
    self.ambiguous = ambiguous
    self.likelyError = likelyError
  }
}

public struct ConsentSnapshot: Codable, Equatable, Sendable {
  public let audioProcessing: Bool
  public let videoProcessing: Bool
  public let clinicianReview: Bool
  public let researchUse: Bool

  public init(
    audioProcessing: Bool,
    videoProcessing: Bool,
    clinicianReview: Bool,
    researchUse: Bool
  ) {
    self.audioProcessing = audioProcessing
    self.videoProcessing = videoProcessing
    self.clinicianReview = clinicianReview
    self.researchUse = researchUse
  }
}

public struct AttemptEvaluationRequest: Codable, Equatable, Sendable {
  public let attemptId: String
  public let protocolId: TargetProtocolID
  public let quality: CaptureQuality
  public let audio: AudioEvidence
  public let consent: ConsentSnapshot

  public init(
    attemptId: String,
    protocolId: TargetProtocolID,
    quality: CaptureQuality,
    audio: AudioEvidence,
    consent: ConsentSnapshot
  ) {
    self.attemptId = attemptId
    self.protocolId = protocolId
    self.quality = quality
    self.audio = audio
    self.consent = consent
  }
}

public struct RoutingDecision: Codable, Equatable, Sendable {
  public let kind: RoutingDecisionKind
  public let runDeepVision: Bool
  public let reason: RoutingDecisionReason
  public let protocolId: TargetProtocolID
  public let protocolRegistryVersion: String
  public let thresholdVersion: String
  public let clinicianReviewPermitted: Bool
  public let researchUsePermitted: Bool

  public init(
    kind: RoutingDecisionKind,
    runDeepVision: Bool,
    reason: RoutingDecisionReason,
    protocolId: TargetProtocolID,
    protocolRegistryVersion: String,
    thresholdVersion: String,
    clinicianReviewPermitted: Bool,
    researchUsePermitted: Bool
  ) {
    self.kind = kind
    self.runDeepVision = runDeepVision
    self.reason = reason
    self.protocolId = protocolId
    self.protocolRegistryVersion = protocolRegistryVersion
    self.thresholdVersion = thresholdVersion
    self.clinicianReviewPermitted = clinicianReviewPermitted
    self.researchUsePermitted = researchUsePermitted
  }
}

public struct AttemptEvaluationResponse: Codable, Equatable, Sendable {
  public let attemptId: String
  public let decision: RoutingDecision

  public init(
    attemptId: String,
    decision: RoutingDecision
  ) {
    self.attemptId = attemptId
    self.decision = decision
  }
}

public struct LearnerAttemptReceipt: Codable, Equatable, Sendable {
  public let attemptId: String
  public let status: LearnerAttemptStatus
  public let feedbackAvailable: Bool
  public let mediaRetained: Bool
  public let reasonCodes: [CaptureReasonCode]

  public init(
    attemptId: String,
    status: LearnerAttemptStatus,
    feedbackAvailable: Bool,
    mediaRetained: Bool,
    reasonCodes: [CaptureReasonCode]
  ) {
    self.attemptId = attemptId
    self.status = status
    self.feedbackAvailable = feedbackAvailable
    self.mediaRetained = mediaRetained
    self.reasonCodes = reasonCodes
  }
}
