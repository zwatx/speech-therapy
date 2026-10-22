#if DEBUG && targetEnvironment(simulator)
  import CryptoKit
  import Foundation

  enum RecordingFeedbackError: Error, Equatable {
    case unsupportedAge, unsupportedPrompt, invalidRecording, invalidResponse
    case serviceUnavailable, timeout, processingUnavailable
  }

  /// Self-declared practice context; never an imputed child age or clinical eligibility.
  enum ResearchPracticeContext: Equatable, Sendable, Encodable {
    case adult
    case child(ageYears: Int)

    var isValid: Bool {
      switch self {
      case .adult: true
      case .child(let age): (6...12).contains(age)
      }
    }
    private enum Key: String, CodingKey { case kind, ageYears }
    func encode(to encoder: any Encoder) throws {
      guard isValid else { throw RecordingFeedbackError.unsupportedAge }
      var fields = encoder.container(keyedBy: Key.self)
      switch self {
      case .adult: try fields.encode("adult", forKey: .kind)
      case .child(let age):
        try fields.encode("child", forKey: .kind)
        try fields.encode(age, forKey: .ageYears)
      }
    }
    static func decode(_ data: Data) throws -> Self {
      let value = try FeedbackJSON.parse(data)
      guard case .object(let fields) = value, let kind = fields["kind"] else {
        throw RecordingFeedbackError.invalidResponse
      }
      switch try kind.string() {
      case "adult":
        _ = try value.object(["kind"])
        return .adult
      case "child":
        let exact = try value.object(["kind", "ageYears"])
        let age = try exact["ageYears"]!.integer()
        guard (6...12).contains(age) else { throw RecordingFeedbackError.unsupportedAge }
        return .child(ageYears: age)
      default: throw RecordingFeedbackError.invalidResponse
      }
    }
  }

  enum ResearchFeedbackProcessingEvent: Equatable, Sendable {
    case requestStarted, declarationRejected
  }

  @MainActor
  protocol ResearchFeedbackProcessing {
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) async throws -> RecordingFeedback
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> RecordingFeedback
  }
  extension ResearchFeedbackProcessing {
    // Old injected processors remain compatible; they cannot invent a transport event.
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> RecordingFeedback {
      try await process(
        attemptId: attemptId, recording: recording, prompt: prompt,
        practiceContext: practiceContext)
    }
  }

  struct RecordingFeedback: Equatable, Sendable {
    enum Status: String, Sendable { case observed, unavailable }
    enum SpeechState: String, Sendable {
      case modelDetected = "model_detected"
      case modelNotDetected = "model_not_detected"
      case notRun = "not_run"
      case unavailable
    }
    enum WordState: String, Sendable {
      case modelMatched = "model_matched"
      case modelNotMatched = "model_not_matched"
      case uncertain
      case notSingleWord = "not_single_word"
      case notRun = "not_run"
      case unavailable
    }
    enum Suggestion: String, Sendable {
      case recordAgain = "record_again"
      case reviewRecording = "review_recording"
      case reduceRecordingLevel = "reduce_recording_level"
      case listenToExample = "listen_to_example"
      case sayOneWord = "say_one_word"
      case tryAgain = "try_again"
      case retryLater = "retry_later"
      case processingUnavailable = "processing_unavailable"
      case continuePractice = "continue_practice"
    }
    let status: Status
    let reason: String?
    let capture: FeedbackPCM?
    let captureReason: String?
    let speech: SpeechState
    let speechReason: String?
    let word: WordState
    let wordReason: String?
    let targetUnsupported: Bool
    let suggestions: [Suggestion]
    let elapsedMilliseconds: Double
    let evidenceSha256: String?
    var pronunciationCorrectnessAssessed: Bool { false }
    var diagnosisProvided: Bool { false }
  }

  struct FeedbackDeclaration: Equatable, Sendable {
    let csrfToken: String
    static func decode(_ data: Data) throws -> Self {
      let root = try FeedbackJSON.parse(data).object([
        "schemaVersion", "csrfToken", "pins", "feedbackPolicy", "feedbackSourceSha256",
        "wrapperSourceSha256", "contentSha256", "processingAvailable",
      ])
      guard try root["schemaVersion"]!.integer() == 1 else {
        throw RecordingFeedbackError.invalidResponse
      }
      let token = try root["csrfToken"]!.string()
      guard FeedbackContract.isHash(token) else { throw RecordingFeedbackError.invalidResponse }
      let pins = try root["pins"]!.object(Set(FeedbackContract.corePins.keys))
      for (key, value) in FeedbackContract.corePins {
        guard try pins[key]!.string() == value else { throw RecordingFeedbackError.invalidResponse }
      }
      let policy = try root["feedbackPolicy"]!.object(["id", "sha256"])
      guard try policy["id"]!.string() == "consumer-recording-feedback-v2",
        try policy["sha256"]!.string() == FeedbackContract.pins["feedbackPolicySha256"]
      else { throw RecordingFeedbackError.invalidResponse }
      for key in ["feedbackSourceSha256", "wrapperSourceSha256", "contentSha256"] {
        guard try root[key]!.string() == FeedbackContract.pins[key] else {
          throw RecordingFeedbackError.invalidResponse
        }
      }
      guard try root["processingAvailable"]!.boolean() else {
        throw RecordingFeedbackError.processingUnavailable
      }
      return Self(csrfToken: token)
    }
  }

  enum FeedbackContract {
    static let corePins = [
      "modelManifestSha256": "8a8054e4c434e9106e9bb625d27c3219089c7a6b643504ad893a531c3b4e6c37",
      "policySha256": "33b4a2598c1700d2d88ded58fbe369bed4bca71d63fbff6a1beb191cc6e9cf49",
      "admissionSourceSha256": "53468b070bbde40ca29f86caa67877e904175a67fdfd8ae2258cb218b5461b24",
      "bridgeSourceSha256": "e1a539570244c2f1ee28b29b98954e656561aa6605625458c0ebe966cd725b88",
      "serviceSourceSha256": "e950bf69352ba8d0995154b4ab7124a91fadb81ed81aaae5d1b2375a3809d349",
      "supervisorSourceSha256": "03f0f1ca5b7f7ef2cead5b683f644a25293c9fc2e260d3db00827b5e25e03bda",
    ]
    static let pins = corePins.merging([
      "feedbackSourceSha256": "a769aabd08412c35dd6f3fbcf306d74c27dea9febb39417c926786f891cf88a4",
      "wrapperSourceSha256": "efa00f73fffd4a58a73a5ece64602214951be679d8cc04644f9e8ed66dec1df8",
      "feedbackPolicySha256": "c21530e7c85575a1ac425036cc182707f63b76da4a07b74b1c32e6dea4fc1407",
      "contentSha256": "beafb00cbfe5578560549abd0ebd1fbbfba88218521f3c50cbab654d8a33ebd1",
    ]) { _, new in new }
    static let claims: Set<String> = [
      "speechPresenceVerified", "requestedWordVerified", "promptMatchingValidated",
      "intendedChildAccuracyEstablished", "qualifiedApprovalEstablished", "learnerFeedbackEligible",
      "clinicalUseEligible", "productionUseEligible", "authenticProvenanceEstablished",
      "diagnosisProvided", "pronunciationCorrectnessAssessed",
    ]
    static let reasons: Set<String> = ResearchAdmissionClient.unavailableReasons
    static let modelFailures: Set<String> = [
      "worker_timeout", "worker_crash", "model_unavailable", "recognition_failed",
    ]
    static let serviceFailures: Set<String> = [
      "invalid_evidence", "busy", "timeout", "source_binding_failed", "assessment_failed",
      "invalid_request", "cleanup_unconfirmed",
    ]
    static func isHash(_ value: String) -> Bool {
      value.count == 64
        && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    static func sha(_ data: Data) -> String {
      SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    static func encoder() -> JSONEncoder {
      let e = JSONEncoder()
      e.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
      return e
    }

    static func decode(
      _ data: Data, expectedBinding: [String: String], pcm: FeedbackPCM, targetUnsupported: Bool
    ) throws -> RecordingFeedback {
      func need(_ condition: Bool) throws {
        if !condition { throw RecordingFeedbackError.invalidResponse }
      }
      func reason(_ value: FeedbackJSON.Value) throws -> String? {
        let code = try value.nullableString()
        try need(code == nil || reasons.contains(code!))
        return code
      }
      let root = try FeedbackJSON.parse(data).object([
        "schemaVersion", "kind", "status", "reason", "stages", "targetAssessment",
        "suggestionCodes", "binding", "claimLimits", "elapsedMilliseconds",
      ])
      try need(
        root["schemaVersion"]!.integer() == 1 && root["kind"]!.string() == "recording_feedback")
      guard let status = try RecordingFeedback.Status(rawValue: root["status"]!.string()) else {
        throw RecordingFeedbackError.invalidResponse
      }
      let code = try reason(root["reason"]!)
      let elapsed = try root["elapsedMilliseconds"]!.number()
      try need((0...105_000).contains(elapsed))
      let claims = try root["claimLimits"]!.object(claims)
      for value in claims.values { try need(value.boolean() == false) }
      let binding = try root["binding"]!.object(Set(expectedBinding.keys).union(["evidenceSha256"]))
      for (key, value) in expectedBinding { try need(binding[key]!.string() == value) }
      let evidence = try binding["evidenceSha256"]!.nullableString()
      try need(evidence == nil || isHash(evidence!))
      let target = try root["targetAssessment"]!.object(["state", "reason"])
      try need(
        target["state"]!.string() == (targetUnsupported ? "unsupported" : "not_performed")
          && target["reason"]!.string()
            == (targetUnsupported ? "unsupported_target" : "not_validated")
      )
      let stages = try root["stages"]!.object(["capture", "speech", "word"])
      let capture = try stages["capture"]!.object([
        "state", "reason", "sampleCount", "durationMilliseconds", "rms", "rmsDbfs", "peak",
        "railSamples", "clippedFraction",
      ])
      let captureState = try capture["state"]!.string()
      let captureCode = try capture["reason"]!.nullableString()
      var metrics: FeedbackPCM?
      if captureState == "observed" {
        try need(pcm.modelCaptureValid && captureCode == nil)
        try need(
          capture["sampleCount"]!.integer() == pcm.sampleCount
            && capture["railSamples"]!.integer() == pcm.railSamples)
        for (key, expected) in [
          ("durationMilliseconds", pcm.durationMilliseconds), ("rms", pcm.rms),
          ("rmsDbfs", pcm.rmsDbfs), ("peak", pcm.peak), ("clippedFraction", pcm.clippedFraction),
        ] {
          let value = try capture[key]!.number()
          let range: ClosedRange<Double> =
            key == "rmsDbfs" ? -120...0 : (key == "durationMilliseconds" ? 0...4000 : 0...1)
          try need(range.contains(value))
          try need(abs(value - expected) <= (key == "rmsDbfs" ? 1e-9 : 1e-12))
        }
        metrics = pcm
      } else {
        try need(
          captureState == "unavailable"
            && ["invalid_audio", "cleanup_unconfirmed"].contains(captureCode ?? ""))
        if captureCode == "cleanup_unconfirmed" { try need(code == captureCode) }
        for key in capture.keys where key != "state" && key != "reason" {
          try need(capture[key]!.isNull)
        }
        if captureCode == "invalid_audio" { try need(!pcm.modelCaptureValid) }
      }
      let speechFields = try stages["speech"]!.object(["state", "reason"])
      let wordFields = try stages["word"]!.object(["state", "reason"])
      guard
        let speech = try RecordingFeedback.SpeechState(rawValue: speechFields["state"]!.string()),
        let word = try RecordingFeedback.WordState(rawValue: wordFields["state"]!.string())
      else { throw RecordingFeedbackError.invalidResponse }
      let speechCode = try reason(speechFields["reason"]!)
      let wordCode = try reason(wordFields["reason"]!)
      let lexical: [String: RecordingFeedback.WordState] = [
        "requested_word_not_matched": .modelNotMatched, "recognition_uncertain": .uncertain,
        "recognition_incomplete": .uncertain, "single_word_required": .notSingleWord,
      ]
      if code == nil || lexical[code!] != nil {
        try need(
          status == .observed && metrics != nil && evidence != nil && speech == .modelDetected
            && speechCode == nil && word == (code == nil ? .modelMatched : lexical[code!]!)
            && wordCode == code)
        try need(pcm.railSamples == 0 && pcm.rms >= 0.001)
      } else if code == "speech_not_detected" {
        try need(
          status == .observed && metrics != nil && evidence != nil && speech == .modelNotDetected
            && speechCode == code && word == .notRun && wordCode == code)
        try need(pcm.railSamples == 0 && pcm.rms >= 0.001)
      } else if code == "silence" || code == "clipping" {
        try need(
          status == .observed && metrics != nil && evidence != nil && speech == .notRun
            && word == .notRun && speechCode == code && wordCode == code)
        try need(code == "silence" ? pcm.railSamples == 0 && pcm.rms < 0.001 : pcm.railSamples > 0)
      } else if code == "invalid_audio" {
        try need(
          status == .unavailable && captureState == "unavailable" && captureCode == code
            && evidence != nil && speech == .notRun && word == .notRun && speechCode == code
            && wordCode == code)
      } else if modelFailures.contains(code!) {
        try need(
          status == .unavailable && metrics != nil && evidence != nil && pcm.railSamples == 0
            && pcm.rms >= 0.001 && speech == .unavailable && word == .unavailable
            && speechCode == code && wordCode == code)
      } else if serviceFailures.contains(code!) {
        try need(
          status == .unavailable && speech == .unavailable && word == .unavailable
            && speechCode == code && wordCode == code)
        try need(evidence == nil)
      } else {
        throw RecordingFeedbackError.invalidResponse
      }
      if code == "cleanup_unconfirmed" {
        try need(captureState == "unavailable" && captureCode == code && evidence == nil)
      }
      if ["busy", "timeout", "source_binding_failed", "assessment_failed", "invalid_evidence"]
        .contains(code ?? "")
      {
        try need(evidence == nil)
      }
      let codes = try root["suggestionCodes"]!.array().map { try $0.string() }
      try need(codes.count <= 3 && Set(codes).count == codes.count)
      let suggestions = try codes.map { code -> RecordingFeedback.Suggestion in
        guard let value = RecordingFeedback.Suggestion(rawValue: code) else {
          throw RecordingFeedbackError.invalidResponse
        }
        return value
      }
      for suggestion in suggestions {
        switch suggestion {
        case .continuePractice: try need(word == .modelMatched)
        case .reduceRecordingLevel: try need(code == "clipping")
        case .sayOneWord:
          try need(
            [RecordingFeedback.WordState.modelNotMatched, .notSingleWord, .uncertain].contains(word)
          )
        case .retryLater, .processingUnavailable: try need(status == .unavailable)
        default: break
        }
      }
      return .init(
        status: status, reason: code, capture: metrics, captureReason: captureCode, speech: speech,
        speechReason: speechCode, word: word, wordReason: wordCode,
        targetUnsupported: targetUnsupported, suggestions: suggestions,
        elapsedMilliseconds: elapsed, evidenceSha256: evidence)
    }
  }
#endif
