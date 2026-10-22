#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Separate Python prepare/projector bytes with invented evidence; no acoustic/model execution.
  @MainActor
  final class ResearchWordGuessGoldenTests: XCTestCase {
    override func tearDown() {
      FeedbackProtocol.handler = nil
      super.tearDown()
    }

    func testPythonPreparedWordRequestsAndProjectedEnvelopesMatchActualNativeClient() async throws {
      let rows = try wordRows()
      let expectedIDs = Set(
        ["adult", "child6", "child9", "child12"].flatMap { context in
          ["match", "mismatch", "null"].map { context + "-" + $0 }
        } + ["adult-yo-yo-alias"])
      XCTAssertEqual(Set(rows.compactMap { $0["id"] as? String }), expectedIDs)
      for row in rows {
        let id = try string(row, "id")
        XCTAssertEqual(
          FeedbackContract.sha(Data(try string(row, "requestUTF8").utf8)),
          try string(row, "requestSha256"))
        XCTAssertEqual(
          FeedbackContract.sha(Data(try string(row, "responseUTF8").utf8)),
          try string(row, "responseSha256"))
        let expectedGuess: String? =
          id == "adult-yo-yo-alias"
          ? "yoyo"
          : (id.hasSuffix("-match") ? "bread" : (id.hasSuffix("-mismatch") ? "door" : nil))
        let response = try object(Data(try string(row, "responseUTF8").utf8))
        let base = try XCTUnwrap(response["feedback"] as? [String: Any])
        let claims = try XCTUnwrap(base["claimLimits"] as? [String: Bool])
        XCTAssertEqual(Set(claims.keys), Set(FeedbackContract.claims))
        XCTAssertTrue(claims.values.allSatisfy { !$0 })
        let stages = try XCTUnwrap(base["stages"] as? [String: Any])
        let stage = try XCTUnwrap(stages["word"] as? [String: Any])
        let result = try await execute(row)
        XCTAssertEqual(result.feedback.word.rawValue, try string(stage, "state"))
        XCTAssertEqual(result.wordGuess?.normalizedWord, response["wordGuess"] as? String)
        XCTAssertEqual(result.wordGuess?.normalizedWord, expectedGuess)
        XCTAssertFalse(result.feedback.pronunciationCorrectnessAssessed)
        XCTAssertFalse(result.feedback.diagnosisProvided)
      }
    }

    func testPythonWordReplyFromDifferentContextIsRejectedByActualNativeClient() async throws {
      let rows = try wordRows()
      let adult = try XCTUnwrap(rows.first { ($0["id"] as? String) == "adult-match" })
      let child = try XCTUnwrap(rows.first { ($0["id"] as? String) == "child9-match" })
      for (requestRow, responseRow) in [(adult, child), (child, adult)] {
        var swapped = requestRow
        swapped["responseUTF8"] = responseRow["responseUTF8"]
        do {
          _ = try await execute(swapped)
          XCTFail("Different-context Python response was accepted")
        } catch {
          XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse)
        }
      }
    }

    func testPythonSuccessorSoundPublicPrivateExpectedBytesAndContextHashMatchNative() throws {
      let metadata = try metadata()
      let declaration = try ResearchSoundContract.declaration(
        Data(try string(metadata, "soundDeclarationUTF8").utf8), service: .wordGuess)
      let soundRows = try XCTUnwrap(metadata["soundVectors"] as? [String: [String: Any]])
      XCTAssertEqual(Set(soundRows.keys), ["unit3200", "silence2400"])
      for row in soundRows.values {
        let hashes = try XCTUnwrap(row["hashes"] as? [String: Any])
        let requestData = Data(try string(row, "requestUTF8").utf8)
        XCTAssertEqual(FeedbackContract.sha(requestData), try string(hashes, "requestSha256"))
        let request = try object(requestData)
        let ownership = try XCTUnwrap(request["ownership"] as? [String: Any])
        let context = ResearchSoundCheckContext(
          sessionId: try string(ownership, "sessionId"),
          generation: try integer(ownership, "generation"),
          setupGeneration: try integer(request, "setupGeneration"),
          roundId: try string(ownership, "roundId"), takeId: try string(ownership, "takeId"),
          captureId: try string(ownership, "captureId"), attemptId: try string(request, "attemptId")
        )
        let audio = try XCTUnwrap(Data(base64Encoded: try string(request, "audioBase64")))
        let prepared = try ResearchSoundContract.prepare(
          audio: audio, declaration: declaration, context: context, service: .wordGuess)
        XCTAssertEqual(prepared.body, requestData)
        XCTAssertEqual(
          try prepared.privateRequest.canonical(),
          Data(try string(row, "privateRequestUTF8").utf8))
        let expectedData = Data(try string(row, "expectedUTF8").utf8)
        XCTAssertEqual(try prepared.expected.canonical(), expectedData)
        XCTAssertEqual(FeedbackContract.sha(expectedData), try string(hashes, "expectedSha256"))
        XCTAssertEqual(
          FeedbackContract.sha(try prepared.privateRequest.canonical()),
          try string(hashes, "privateRequestSha256"))
        XCTAssertEqual(
          FeedbackContract.sha(Data(try string(row, "contextUTF8").utf8)),
          try string(hashes, "contextSha256"))
        let expected = try object(expectedData)
        XCTAssertEqual(prepared.requestSha256, try string(expected, "requestSha256"))
        XCTAssertEqual(
          FeedbackContract.sha(try prepared.privateRequest.canonical()),
          try string(expected, "workerRequestSha256"))
        XCTAssertEqual(
          try string(ownership, "contextSha256"),
          FeedbackContract.sha(Data(try string(row, "contextUTF8").utf8)))
        try ResearchSoundContract.validatePrepared(prepared, service: .wordGuess)
      }
    }

    private func execute(_ row: [String: Any]) async throws -> ResearchWordGuessFeedback {
      let rawRequest = Data(try string(row, "requestUTF8").utf8)
      let request = try object(rawRequest)
      let requestContext = try XCTUnwrap(request["practiceContext"] as? [String: Any])
      let context: ResearchPracticeContext =
        try string(requestContext, "kind") == "adult"
        ? .adult : .child(ageYears: try integer(requestContext, "ageYears"))
      let requestPrompt = try XCTUnwrap(request["prompt"] as? [String: Any])
      let transcript = try string(requestPrompt, "transcript")
      let prompt = try XCTUnwrap(ResearchFeedbackCatalog.prompts.first { $0.word == transcript })
      let attempt = try XCTUnwrap(UUID(uuidString: try string(request, "attemptId")))
      let audio = try XCTUnwrap(Data(base64Encoded: try string(request, "audioBase64")))
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        "word-guess-python-golden-" + UUID().uuidString + ".wav")
      try audio.write(to: file)
      defer {
        try? FileManager.default.removeItem(at: file)
        FeedbackProtocol.handler = nil
      }
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [FeedbackProtocol.self]
      let declaration = Data(try string(try metadata(), "wordDeclarationUTF8").utf8)
      let response = Data(try string(row, "responseUTF8").utf8)
      FeedbackProtocol.handler = { actual in
        XCTAssertEqual(actual.url?.scheme, "http")
        XCTAssertEqual(actual.url?.host, "127.0.0.1")
        XCTAssertEqual(actual.url?.port, 8795)
        XCTAssertEqual(actual.value(forHTTPHeaderField: "Origin"), ResearchWordGuessClient.origin)
        let body: Data
        if actual.url?.path == "/api/feedback-declaration" {
          XCTAssertEqual(actual.httpMethod, "GET")
          body = declaration
        } else {
          XCTAssertEqual(actual.url?.path, "/api/feedback")
          XCTAssertEqual(actual.httpMethod, "POST")
          XCTAssertEqual(try FeedbackFixture.requestBody(actual), rawRequest)
          body = response
        }
        return (
          HTTPURLResponse(
            url: actual.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, body
        )
      }
      return try await ResearchWordGuessClient(configuration: configuration).process(
        attemptId: attempt,
        recording: .init(url: file, summary: .init(duration: 0.2, averagePower: -12)),
        prompt: prompt, practiceContext: context, onEvent: { _ in })
    }

    private func metadata() throws -> [String: Any] {
      try object(Data(ResearchWordGuessGoldenMetadata.json.utf8))
    }
    private func wordRows() throws -> [[String: Any]] {
      let vectors = try XCTUnwrap(try metadata()["wordVectors"] as? [String: [String: Any]])
      return vectors.keys.sorted().map { key in
        var row = vectors[key]!
        row["id"] = key
        return row
      }
    }
    private func object(_ data: Data) throws -> [String: Any] {
      try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
    private func string(_ value: [String: Any], _ key: String) throws -> String {
      try XCTUnwrap(value[key] as? String, key)
    }
    private func integer(_ value: [String: Any], _ key: String) throws -> Int {
      try XCTUnwrap(value[key] as? Int, key)
    }
  }
#endif
