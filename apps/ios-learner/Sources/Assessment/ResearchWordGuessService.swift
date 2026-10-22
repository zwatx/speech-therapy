#if DEBUG && targetEnvironment(simulator)
  import Foundation

  /// Closed compiled local contracts; replies cannot select origins or trusted source pins.
  enum ResearchFeedbackService: Equatable, Sendable {
    case currentUnified, wordGuess, browserWordGuess
    var origin: String {
      switch self {
      case .currentUnified: ResearchSoundContract.origin
      case .wordGuess: ResearchWordGuessService.origin
      case .browserWordGuess: ResearchBrowserWordGuessService.origin
      }
    }
    var soundBinding: ResearchSoundJSON {
      switch self {
      case .currentUnified: return ResearchSoundContract.binding
      case .wordGuess, .browserWordGuess:
        let pins = wordGuessPins!
        var sources = try! ResearchSoundContract.sourcePins.fields([
          "contrastSpecSha256", "featureSourceSha256", "modelFileSha256", "promptSha256",
          "resourcePolicySha256", "runtimePinsSha256", "vocabularyFileSha256",
          "workerReceiptSha256", "workerSourceSha256",
        ])
        sources["featureSourceSha256"] = .string(
          self == .wordGuess
            ? ResearchWordGuessService.featureSourceSha256
            : ResearchBrowserWordGuessService.featureSourceSha256)
        return .object([
          "sources": .object(sources),
          "wordBinding": .object([
            "pins": .object(FeedbackContract.corePins.mapValues { .string($0) }),
            "feedbackSourceSha256": .string(pins["feedbackSourceSha256"]!),
            "wrapperSourceSha256": .string(pins["wrapperSourceSha256"]!),
            "feedbackPolicySha256": .string(pins["feedbackPolicySha256"]!),
            "contentSha256": .string(pins["contentSha256"]!),
          ]),
        ])
      }
    }
    var wordGuessPins: [String: String]? {
      switch self {
      case .currentUnified: nil
      case .wordGuess: ResearchWordGuessService.pins
      case .browserWordGuess: ResearchBrowserWordGuessService.pins
      }
    }
    var wordGuessPolicyID: String? {
      switch self {
      case .currentUnified: nil
      case .wordGuess: ResearchWordGuessService.policyID
      case .browserWordGuess: ResearchBrowserWordGuessService.policyID
      }
    }
    func requireWordGuessConfigured() throws {
      guard wordGuessPins != nil else { throw RecordingFeedbackError.invalidResponse }
      try requireConfigured()
    }
    func requireConfigured() throws {
      switch self {
      case .currentUnified: break
      case .wordGuess: try ResearchWordGuessService.requireConfigured()
      case .browserWordGuess: try ResearchBrowserWordGuessService.requireConfigured()
      }
    }
  }

  enum ResearchWordGuessService {
    static let origin = "http://127.0.0.1:8795"
    static let policyID = "consumer-recording-feedback-word-guess-v1"
    // Independently checked against the exact eight-file API successor source closure.
    // Returned metadata never supplies or replaces these compiled pins.
    static let featureSourceSha256 =
      "28c3f011cdedc11f33f98eb14c6590a98ec1192a9793b7df99cc991d5de759e7"
    static let pins = FeedbackContract.corePins.merging([
      "feedbackSourceSha256": "28e27a68a77335c92aaac7ddd77e7a5be8b93262bca94abd761591d419cd0d64",
      "wrapperSourceSha256": "bde5a03814be01b4e90261068fb381a6aa03e9288112f9f2924f8d20ef1efe2e",
      "feedbackPolicySha256": "6cd0ef602f6ba526262cbade869d91b83555822a13e14a9acb87a43f8527239d",
      "contentSha256": FeedbackContract.pins["contentSha256"]!,
    ]) { _, new in new }
    static func requireConfigured() throws {
      guard pins.values.allSatisfy(FeedbackContract.isHash),
        FeedbackContract.isHash(featureSourceSha256)
      else { throw RecordingFeedbackError.invalidResponse }
    }
  }
#endif
