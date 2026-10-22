#if DEBUG && targetEnvironment(simulator)
  import Foundation

  struct ResearchRecognizerWordGuess: Equatable, Sendable {
    let normalizedWord: String
  }
  struct ResearchWordGuessFeedback: Equatable, Sendable {
    let feedback: RecordingFeedback
    let wordGuess: ResearchRecognizerWordGuess?
  }
  @MainActor
  protocol ResearchWordGuessProcessing {
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> ResearchWordGuessFeedback
  }
  struct ResearchWordGuessDeclaration: Equatable, Sendable {
    let csrfToken: String
    static func decode(
      _ data: Data, service: ResearchFeedbackService = .wordGuess
    ) throws -> Self {
      try service.requireWordGuessConfigured()
      let compiledPins = service.wordGuessPins!
      let root = try FeedbackJSON.parse(data).object([
        "schemaVersion", "csrfToken", "pins", "feedbackPolicy", "feedbackSourceSha256",
        "wrapperSourceSha256", "contentSha256", "processingAvailable",
      ])
      try ResearchSoundContract.need(root["schemaVersion"]!.integer() == 2)
      let token = try root["csrfToken"]!.string()
      try ResearchSoundContract.need(FeedbackContract.isHash(token))
      let pins = try root["pins"]!.object(Set(FeedbackContract.corePins.keys))
      for (key, value) in FeedbackContract.corePins {
        try ResearchSoundContract.need(pins[key]!.string() == value)
      }
      let policy = try root["feedbackPolicy"]!.object(["id", "sha256"])
      try ResearchSoundContract.need(
        policy["id"]!.string() == service.wordGuessPolicyID!
          && policy["sha256"]!.string() == compiledPins["feedbackPolicySha256"])
      for key in ["feedbackSourceSha256", "wrapperSourceSha256", "contentSha256"] {
        try ResearchSoundContract.need(root[key]!.string() == compiledPins[key])
      }
      guard try root["processingAvailable"]!.boolean() else {
        throw RecordingFeedbackError.processingUnavailable
      }
      return .init(csrfToken: token)
    }
  }

  enum ResearchWordGuessContract {
    static func decode(
      _ data: Data, expectedBinding: [String: String], pcm: FeedbackPCM,
      prompt: ResearchFeedbackPrompt, service: ResearchFeedbackService = .wordGuess
    ) throws -> ResearchWordGuessFeedback {
      try service.requireWordGuessConfigured()
      let compiledPins = service.wordGuessPins!
      // Strictly inspect the original JSON before Foundation can normalize number spellings.
      let root = try FeedbackJSON.parse(data).object([
        "schemaVersion", "kind", "feedback", "wordGuess",
      ])
      try ResearchSoundContract.need(root["schemaVersion"]!.integer() == 2)
      try ResearchSoundContract.need(root["kind"]!.string() == "recording_feedback_with_word_guess")
      let nested = try root["feedback"]!.object([
        "schemaVersion", "kind", "status", "reason", "stages", "targetAssessment",
        "suggestionCodes", "binding", "claimLimits", "elapsedMilliseconds",
      ])
      try ResearchSoundContract.need(nested["schemaVersion"]!.integer() == 1)
      let stages = try nested["stages"]!.object(["capture", "speech", "word"])
      let capture = try stages["capture"]!.object([
        "state", "reason", "sampleCount", "durationMilliseconds", "rms", "rmsDbfs", "peak",
        "railSamples", "clippedFraction",
      ])
      if try capture["state"]!.string() == "observed" {
        _ = try capture["sampleCount"]!.integer()
        _ = try capture["railSamples"]!.integer()
      }
      let expectedKeys = Set(compiledPins.keys).union([
        "attemptId", "requestSha256", "audioSha256", "promptSha256",
      ])
      try ResearchSoundContract.need(Set(expectedBinding.keys) == expectedKeys)
      for (key, value) in compiledPins {
        try ResearchSoundContract.need(expectedBinding[key] == value)
      }
      try ResearchSoundContract.need(ResearchFeedbackCatalog.prompts.contains(prompt))
      try ResearchSoundContract.need(
        expectedBinding["promptSha256"]
          == FeedbackContract.sha(
            try FeedbackContract.encoder().encode(prompt.requestPrompt)))
      let actualNested = try JSONSerialization.data(
        withJSONObject: foundation(root["feedback"]!),
        options: [.sortedKeys, .withoutEscapingSlashes])
      let feedback = try FeedbackContract.decode(
        actualNested, expectedBinding: expectedBinding,
        pcm: pcm, targetUnsupported: prompt.targetUnsupported)
      let token = try root["wordGuess"]!.nullableString()
      let guess: ResearchRecognizerWordGuess?
      switch feedback.word {
      case .modelMatched, .modelNotMatched:
        guard let token, normalizedToken(token), token != "yo-yo" else {
          throw RecordingFeedbackError.invalidResponse
        }
        let target = prompt.word == "yo-yo" ? "yoyo" : prompt.word
        try ResearchSoundContract.need((token == target) == (feedback.word == .modelMatched))
        guess = .init(normalizedWord: token)
      default:
        try ResearchSoundContract.need(token == nil)
        guess = nil
      }
      return .init(feedback: feedback, wordGuess: guess)
    }
    private static func normalizedToken(_ value: String) -> Bool {
      (1...256).contains(value.utf8.count)
        && value.utf8.allSatisfy { (97...122).contains($0) || $0 == 45 }
        && value.range(of: #"^[a-z]+(?:-[a-z]+)*$"#, options: .regularExpression) != nil
    }
    private static func foundation(_ value: FeedbackJSON.Value) -> Any {
      switch value {
      case .object(let fields): fields.mapValues(foundation)
      case .array(let items): items.map(foundation)
      case .string(let text): text
      case .number(let number, let integer):
        integer.map { NSNumber(value: $0) } ?? NSNumber(value: number)
      case .bool(let value): NSNumber(value: value)
      case .null: NSNull()
      }
    }
  }
#endif
