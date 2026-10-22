#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchWordGuessServiceTests: XCTestCase {
    override func tearDown() {
      FeedbackProtocol.handler = nil
      super.tearDown()
    }
    func testClosedSoundSelectionRejectsForeignDeclarationAndPreparedBeforeTransport() async throws
    {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      FeedbackProtocol.handler = { _ in
        XCTFail("Foreign service object reached transport")
        throw RecordingFeedbackError.invalidResponse
      }
      let old = try SoundFixture.prepared()
      let newDeclaration = ResearchSoundDeclaration(
        serverNonce: SoundFixture.nonce,
        csrfToken: String(repeating: "f", count: 64), processingAvailable: true, service: .wordGuess
      )
      let new = try ResearchSoundContract.prepare(
        audio: FeedbackFixture.wav(), declaration: newDeclaration,
        context: SoundFixture.context, service: .wordGuess)
      for (service, foreign) in [(ResearchFeedbackService.currentUnified, new), (.wordGuess, old)] {
        let client = ResearchSoundClient(configuration: config, service: service)
        do {
          _ = try await client.observe(foreign)
          XCTFail("Foreign observe accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        do {
          try await client.cancel(foreign)
          XCTFail("Foreign cancel accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        do {
          try await client.reset(
            declaration: foreign.declaration, sessionId: "session", generation: 1)
          XCTFail("Foreign reset accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        XCTAssertThrowsError(
          try ResearchSoundContract.prepare(
            audio: FeedbackFixture.wav(),
            declaration: foreign.declaration, context: SoundFixture.context, service: service))
      }
      XCTAssertNotEqual(old.body, new.body)
      XCTAssertNotEqual(old.expected, new.expected)
      try ResearchSoundContract.validatePrepared(old, service: .currentUnified)
      try ResearchSoundContract.validatePrepared(new, service: .wordGuess)
    }
    func testNewSoundDeclarationAndEveryControlStayOnSuccessorOrigin() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      let declaration = ResearchSoundDeclaration(
        serverNonce: SoundFixture.nonce,
        csrfToken: String(repeating: "f", count: 64), processingAvailable: true, service: .wordGuess
      )
      let rawDeclaration = try ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "kind": .string(ResearchSoundContract.kind),
        "purpose": .string(ResearchSoundContract.purpose),
        "serverNonce": .string(declaration.serverNonce),
        "csrfToken": .string(declaration.csrfToken),
        "binding": ResearchFeedbackService.wordGuess.soundBinding,
        "policy": ResearchSoundContract.policy, "processingAvailable": .bool(true),
        "claimLimits": ResearchSoundContract.falseClaims,
      ]).canonical()
      XCTAssertThrowsError(try ResearchSoundContract.declaration(rawDeclaration))
      XCTAssertThrowsError(
        try ResearchSoundContract.declaration(SoundFixture.declarationData(), service: .wordGuess))
      let prepared = try ResearchSoundContract.prepare(
        audio: FeedbackFixture.wav(), declaration: declaration,
        context: SoundFixture.context, service: .wordGuess)
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.url?.host, "127.0.0.1")
        XCTAssertEqual(request.url?.port, 8795)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), ResearchWordGuessService.origin)
        let path = request.url!.path
        let bytes: Data
        if path == "/api/sound-declaration" {
          XCTAssertEqual(request.httpMethod, "GET")
          bytes = rawDeclaration
        } else {
          XCTAssertEqual(request.httpMethod, "POST")
          XCTAssertEqual(
            request.value(forHTTPHeaderField: "X-Consumer-CSRF"), declaration.csrfToken)
          let body = try FeedbackFixture.requestBody(request)
          if path == "/api/sound-observation" {
            XCTAssertEqual(body, prepared.body)
            bytes = try SoundFixture.response(prepared)
          } else {
            var fields = try JSONSerialization.jsonObject(with: body) as! [String: Any]
            if path == "/api/sound-cancel" {
              fields.removeValue(forKey: "ownership")
              fields["cancelAccepted"] = true
            } else {
              XCTAssertEqual(path, "/api/sound-reset")
              fields["resetAccepted"] = true
            }
            bytes = try FeedbackFixture.json(fields)
          }
        }
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, bytes
        )
      }
      let client = ResearchSoundClient(configuration: config, service: .wordGuess)
      let decoded = try await client.declaration()
      XCTAssertEqual(decoded, declaration)
      let observation = try await client.observe(prepared)
      XCTAssertEqual(observation.status, .inconclusive)
      try await client.cancel(prepared)
      try await client.reset(declaration: declaration, sessionId: "session", generation: 2)
    }
    func testLargestPermittedLocallyPreparedBodyRemainsValidForBothServices() throws {
      let audio = FeedbackFixture.wav(Array(repeating: 8192, count: 64000))
      for service in [ResearchFeedbackService.currentUnified, .wordGuess] {
        let declaration = ResearchSoundDeclaration(
          serverNonce: SoundFixture.nonce,
          csrfToken: String(repeating: "f", count: 64), processingAvailable: true, service: service)
        let prepared = try ResearchSoundContract.prepare(
          audio: audio, declaration: declaration,
          context: SoundFixture.context, service: service)
        XCTAssertGreaterThan(prepared.body.count, 16000)
        XCTAssertLessThanOrEqual(prepared.body.count, 200000)
        try ResearchSoundContract.validatePrepared(prepared, service: service)
      }
    }
    func testTamperedSameServiceExpectedOrBodyRefusesBeforeCancel() async throws {
      let old = try SoundFixture.prepared()
      let bad = ResearchSoundPrepared(
        body: old.body, privateRequest: old.privateRequest,
        expected: .object([:]), declaration: old.declaration, ownership: old.ownership,
        context: old.context)
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      FeedbackProtocol.handler = { _ in
        XCTFail("Tampered expected reached transport")
        throw RecordingFeedbackError.invalidResponse
      }
      do {
        try await ResearchSoundClient(configuration: config).cancel(bad)
        XCTFail("Tampered prepared accepted")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
    }
    func testExamplesUseClosedSuccessorOriginWithoutChangingAssets() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      let example = try XCTUnwrap(ResearchPracticeExamples.example(for: WordGuessFixture.prompt))
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(
          request.url?.absoluteString,
          ResearchWordGuessService.origin + "/api/public-references/" + example.sourceWord)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), ResearchWordGuessService.origin)
        XCTAssertEqual(request.httpMethod, "GET")
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 404, httpVersion: nil,
            headerFields: ["Content-Type": "audio/wav"])!, Data()
        )
      }
      let loader = ResearchPracticeExampleClient(configuration: config, service: .wordGuess)
      XCTAssertEqual(loader.example(for: WordGuessFixture.prompt), example)
      do {
        _ = try await loader.load(example: example)
        XCTFail("404 accepted")
      } catch { XCTAssertEqual(error as? ResearchPracticeExampleError, .invalidData) }
      XCTAssertEqual(ResearchPracticeExamples.all.count, 13)
      XCTAssertEqual(ResearchFeedbackService.currentUnified.origin, "http://127.0.0.1:8793")
    }
  }
#endif
