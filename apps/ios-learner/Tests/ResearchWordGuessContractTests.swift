#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Fresh invented replies only; these are neither preserved model outputs nor word truth.
  enum WordGuessFixture {
    static let prompt = ResearchFeedbackCatalog.prompts[1]
    static func declaration() -> [String: Any] {
      [
        "schemaVersion": 2, "csrfToken": String(repeating: "f", count: 64),
        "pins": FeedbackContract.corePins,
        "feedbackPolicy": [
          "id": ResearchWordGuessService.policyID,
          "sha256": ResearchWordGuessService.pins["feedbackPolicySha256"]!,
        ],
        "feedbackSourceSha256": ResearchWordGuessService.pins["feedbackSourceSha256"]!,
        "wrapperSourceSha256": ResearchWordGuessService.pins["wrapperSourceSha256"]!,
        "contentSha256": ResearchWordGuessService.pins["contentSha256"]!,
        "processingAvailable": true,
      ]
    }
    static func binding(_ body: Data, audio: Data) throws -> [String: String] {
      try FeedbackFixture.binding(body, audio: audio).merging(ResearchWordGuessService.pins) {
        _, new in new
      }
    }
    static func response(
      _ body: Data, audio: Data, guess: String?, reason: String? = nil,
      prompt: ResearchFeedbackPrompt = prompt
    ) throws -> [String: Any] {
      var feedback = try FeedbackFixture.response(
        body, audio: audio, reason: reason,
        unsupported: prompt.targetUnsupported)
      var binding: [String: Any] = try self.binding(body, audio: audio)
      binding["evidenceSha256"] = (feedback["binding"] as! [String: Any])["evidenceSha256"]
      feedback["binding"] = binding
      return [
        "schemaVersion": 2, "kind": "recording_feedback_with_word_guess",
        "feedback": feedback, "wordGuess": guess as Any? ?? NSNull(),
      ]
    }
    static func decode(_ value: [String: Any], prompt: ResearchFeedbackPrompt = prompt) throws
      -> ResearchWordGuessFeedback
    {
      let audio = FeedbackFixture.wav()
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: FeedbackFixture.attempt,
        audio: audio, prompt: prompt, practiceContext: .adult)
      return try ResearchWordGuessContract.decode(
        FeedbackFixture.json(value),
        expectedBinding: binding(body, audio: audio), pcm: FeedbackPCM.measure(audio),
        prompt: prompt)
    }
    static func envelope(
      guess: String? = "bread", reason: String? = nil,
      prompt: ResearchFeedbackPrompt = prompt
    ) throws -> [String: Any] {
      let audio = FeedbackFixture.wav()
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: FeedbackFixture.attempt,
        audio: audio, prompt: prompt, practiceContext: .adult)
      return try response(body, audio: audio, guess: guess, reason: reason, prompt: prompt)
    }
  }

  final class ResearchWordGuessContractTests: XCTestCase {
    func testNewDeclarationAndEnvelopeRefuseHistoricalContracts() throws {
      _ = try ResearchWordGuessDeclaration.decode(
        FeedbackFixture.json(WordGuessFixture.declaration()))
      XCTAssertThrowsError(
        try ResearchWordGuessDeclaration.decode(FeedbackFixture.json(FeedbackFixture.declaration()))
      )
      XCTAssertThrowsError(
        try FeedbackDeclaration.decode(FeedbackFixture.json(WordGuessFixture.declaration())))
      let envelope = try WordGuessFixture.envelope()
      let result = try WordGuessFixture.decode(envelope)
      XCTAssertEqual(result.feedback.word, .modelMatched)
      XCTAssertEqual(result.wordGuess?.normalizedWord, "bread")
      XCTAssertFalse(result.feedback.pronunciationCorrectnessAssessed)
      XCTAssertThrowsError(try WordGuessFixture.decode(envelope["feedback"] as! [String: Any]))
    }
    func testEveryCompiledDeclarationBindingIsRequiredBeforeAvailability() throws {
      for key in ResearchWordGuessService.pins.keys {
        var value = WordGuessFixture.declaration()
        if FeedbackContract.corePins[key] != nil {
          var pins = value["pins"] as! [String: String]
          pins[key] = String(repeating: "0", count: 64)
          value["pins"] = pins
        } else if key == "feedbackPolicySha256" {
          value["feedbackPolicy"] = [
            "id": ResearchWordGuessService.policyID,
            "sha256": String(repeating: "0", count: 64),
          ]
        } else {
          value[key] = String(repeating: "0", count: 64)
        }
        XCTAssertThrowsError(try ResearchWordGuessDeclaration.decode(FeedbackFixture.json(value)))
      }
      var unavailable = WordGuessFixture.declaration()
      unavailable["processingAvailable"] = false
      XCTAssertThrowsError(
        try ResearchWordGuessDeclaration.decode(FeedbackFixture.json(unavailable))
      ) { error in
        XCTAssertEqual(error as? RecordingFeedbackError, .processingUnavailable)
      }
    }
    func testMatchMismatchAliasAndNullAreBoundToLexicalState() throws {
      let mismatch = try WordGuessFixture.decode(
        WordGuessFixture.envelope(guess: "red", reason: "requested_word_not_matched"))
      XCTAssertEqual(mismatch.feedback.word, .modelNotMatched)
      XCTAssertEqual(mismatch.wordGuess?.normalizedWord, "red")
      for (guess, reason) in [(nil, nil), ("red", nil), ("bread", "requested_word_not_matched")]
        as [(String?, String?)]
      {
        XCTAssertThrowsError(
          try WordGuessFixture.decode(WordGuessFixture.envelope(guess: guess, reason: reason)))
      }
      let yo = try XCTUnwrap(ResearchFeedbackCatalog.prompts.first { $0.word == "yo-yo" })
      XCTAssertEqual(
        try WordGuessFixture.decode(
          WordGuessFixture.envelope(guess: "yoyo", prompt: yo), prompt: yo
        ).wordGuess?.normalizedWord, "yoyo")
      XCTAssertThrowsError(
        try WordGuessFixture.decode(
          WordGuessFixture.envelope(guess: "yo-yo", prompt: yo), prompt: yo))
      for reason in [
        "recognition_uncertain", "recognition_incomplete", "single_word_required",
        "speech_not_detected", "busy", "cleanup_unconfirmed",
      ] {
        XCTAssertNil(
          try WordGuessFixture.decode(WordGuessFixture.envelope(guess: nil, reason: reason))
            .wordGuess)
        XCTAssertThrowsError(try WordGuessFixture.decode(WordGuessFixture.envelope(reason: reason)))
      }
    }
    func testUnnormalizedArbitraryOversizeAndUnicodeGuessesRefuse() throws {
      for guess in [
        "Bread", " bread", "bread ", "bread\n", "bread red", "<bread>", "bréad", "bread1", "",
        String(repeating: "b", count: 257),
      ] {
        XCTAssertThrowsError(try WordGuessFixture.decode(WordGuessFixture.envelope(guess: guess)))
      }
    }
    func testOriginalLexicalIntegersDuplicatesAndBooleansRefuseBeforeReencoding() throws {
      let valid = String(
        decoding: try FeedbackFixture.json(WordGuessFixture.envelope()), as: UTF8.self)
      for (needle, replacement) in [
        ("\"schemaVersion\":2", "\"schemaVersion\":2.0"),
        ("\"schemaVersion\":2", "\"schemaVersion\":true"),
        ("\"schemaVersion\":1", "\"schemaVersion\":1e0"),
        ("\"schemaVersion\":1", "\"schemaVersion\":1.0"),
        ("\"sampleCount\":3200", "\"sampleCount\":3200.0"),
        ("\"sampleCount\":3200", "\"sampleCount\":true"),
        ("\"sampleCount\":3200", "\"sampleCount\":3.2e3"),
        ("\"railSamples\":0", "\"railSamples\":0.0"),
        ("\"railSamples\":0", "\"railSamples\":0e0"),
        ("\"railSamples\":0", "\"railSamples\":false"),
        ("\"wordGuess\":\"bread\"", "\"wordGuess\":\"bread\",\"wordGuess\":null"),
      ] {
        XCTAssertTrue(valid.contains(needle))
        let audio = FeedbackFixture.wav()
        let body = try ResearchFeedbackClient.requestBody(
          attemptId: FeedbackFixture.attempt, audio: audio,
          prompt: WordGuessFixture.prompt, practiceContext: .adult)
        XCTAssertThrowsError(
          try ResearchWordGuessContract.decode(
            Data(valid.replacingOccurrences(of: needle, with: replacement).utf8),
            expectedBinding: WordGuessFixture.binding(body, audio: audio),
            pcm: FeedbackPCM.measure(audio), prompt: WordGuessFixture.prompt))
      }
    }
    func testNestedSourceClaimsAndExactEnvelopeShapeRemainClosed() throws {
      var value = try WordGuessFixture.envelope()
      value["extra"] = "transcript"
      XCTAssertThrowsError(try WordGuessFixture.decode(value))
      value = try WordGuessFixture.envelope()
      var feedback = value["feedback"] as! [String: Any]
      var binding = feedback["binding"] as! [String: Any]
      binding["requestSha256"] = String(repeating: "0", count: 64)
      feedback["binding"] = binding
      value["feedback"] = feedback
      XCTAssertThrowsError(try WordGuessFixture.decode(value))
      value = try WordGuessFixture.envelope()
      feedback = value["feedback"] as! [String: Any]
      var claims = feedback["claimLimits"] as! [String: Bool]
      claims["requestedWordVerified"] = true
      feedback["claimLimits"] = claims
      value["feedback"] = feedback
      XCTAssertThrowsError(try WordGuessFixture.decode(value))
    }
  }
#endif
