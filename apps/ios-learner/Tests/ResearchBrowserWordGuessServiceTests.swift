#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Fresh invented envelopes/generated PCM. No saved human/model reply is rebound here.
  private enum BrowserGuessFixture {
    static var prompt: ResearchFeedbackPrompt { WordGuessFixture.prompt }
    static func declaration(_ service: ResearchFeedbackService = .browserWordGuess) -> [String: Any]
    {
      let pins = service.wordGuessPins!
      return [
        "schemaVersion": 2, "csrfToken": String(repeating: "f", count: 64),
        "pins": FeedbackContract.corePins,
        "feedbackPolicy": [
          "id": service.wordGuessPolicyID!, "sha256": pins["feedbackPolicySha256"]!,
        ],
        "feedbackSourceSha256": pins["feedbackSourceSha256"]!,
        "wrapperSourceSha256": pins["wrapperSourceSha256"]!,
        "contentSha256": pins["contentSha256"]!, "processingAvailable": true,
      ]
    }
    static func binding(
      _ body: Data, audio: Data, service: ResearchFeedbackService = .browserWordGuess
    ) throws -> [String: String] {
      try FeedbackFixture.binding(body, audio: audio).merging(service.wordGuessPins!) { _, new in
        new
      }
    }
    static func response(
      _ body: Data, audio: Data, service: ResearchFeedbackService = .browserWordGuess
    ) throws -> [String: Any] {
      var feedback = try FeedbackFixture.response(body, audio: audio)
      var binding: [String: Any] = try self.binding(body, audio: audio, service: service)
      binding["evidenceSha256"] = (feedback["binding"] as! [String: Any])["evidenceSha256"]
      feedback["binding"] = binding
      return [
        "schemaVersion": 2, "kind": "recording_feedback_with_word_guess", "feedback": feedback,
        "wordGuess": "bread",
      ]
    }
    static func soundDeclaration(_ service: ResearchFeedbackService) -> ResearchSoundDeclaration {
      .init(
        serverNonce: SoundFixture.nonce, csrfToken: String(repeating: "f", count: 64),
        processingAvailable: true, service: service)
    }
    static func soundData(_ service: ResearchFeedbackService) throws -> Data {
      let declaration = soundDeclaration(service)
      return try ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "kind": .string(ResearchSoundContract.kind),
        "purpose": .string(ResearchSoundContract.purpose),
        "serverNonce": .string(declaration.serverNonce),
        "csrfToken": .string(declaration.csrfToken), "binding": service.soundBinding,
        "policy": ResearchSoundContract.policy, "processingAvailable": .bool(true),
        "claimLimits": ResearchSoundContract.falseClaims,
      ]).canonical()
    }
    static func http(
      _ request: URLRequest, status: Int = 200, mime: String = "application/json", url: URL? = nil
    ) -> HTTPURLResponse {
      HTTPURLResponse(
        url: url ?? request.url!, statusCode: status, httpVersion: nil,
        headerFields: ["Content-Type": mime])!
    }
  }

  @MainActor
  final class ResearchBrowserWordGuessServiceTests: XCTestCase {
    override func tearDown() {
      FeedbackProtocol.handler = nil
      super.tearDown()
    }
    private func configuration() -> URLSessionConfiguration {
      let value = URLSessionConfiguration.ephemeral
      value.protocolClasses = [FeedbackProtocol.self]
      return value
    }
    private func recording(_ audio: Data = FeedbackFixture.wav()) throws -> CapturedRecording {
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-browser-guess-\(UUID()).wav")
      try audio.write(to: url)
      return .init(url: url, summary: .init(duration: 0.2, averagePower: -12))
    }
    func testCompiledProfileMatchesSavedBrowserBindingAndHistoricalProfilesRemainExact() throws {
      // Independent literals from backend/FROZEN_BINDING.json; never returned-service trust.
      let expected = [
        "modelManifestSha256": "8a8054e4c434e9106e9bb625d27c3219089c7a6b643504ad893a531c3b4e6c37",
        "policySha256": "33b4a2598c1700d2d88ded58fbe369bed4bca71d63fbff6a1beb191cc6e9cf49",
        "admissionSourceSha256": "53468b070bbde40ca29f86caa67877e904175a67fdfd8ae2258cb218b5461b24",
        "bridgeSourceSha256": "e1a539570244c2f1ee28b29b98954e656561aa6605625458c0ebe966cd725b88",
        "serviceSourceSha256": "e950bf69352ba8d0995154b4ab7124a91fadb81ed81aaae5d1b2375a3809d349",
        "supervisorSourceSha256":
          "03f0f1ca5b7f7ef2cead5b683f644a25293c9fc2e260d3db00827b5e25e03bda",
        "feedbackSourceSha256": "a593c3cac1af094d737638cb3bafa11d70cff7dc5d342f4efba6fbb21f7b2540",
        "wrapperSourceSha256": "a1b42b478b33e96a38cca4a449474ff5e4a844e9b4e95143ce8e7f7e39586f42",
        "feedbackPolicySha256": "6cd0ef602f6ba526262cbade869d91b83555822a13e14a9acb87a43f8527239d",
        "contentSha256": "beafb00cbfe5578560549abd0ebd1fbbfba88218521f3c50cbab654d8a33ebd1",
      ]
      XCTAssertEqual(ResearchBrowserWordGuessService.pins, expected)
      XCTAssertEqual(
        ResearchBrowserWordGuessService.featureSourceSha256,
        "f4c6b3931676c6d461d3efbe81a5942e467a9dc80ca769885dee1d54eb69f42e")
      XCTAssertEqual(ResearchFeedbackService.browserWordGuess.origin, "http://127.0.0.1:8803")
      XCTAssertEqual(
        ResearchFeedbackService.browserWordGuess.wordGuessPolicyID,
        "consumer-recording-feedback-word-guess-v1")
      XCTAssertEqual(ResearchWordGuessClient.origin, "http://127.0.0.1:8795")
      XCTAssertEqual(
        ResearchWordGuessClient.endpoint.absoluteString, "http://127.0.0.1:8795/api/feedback")
      XCTAssertEqual(
        ResearchWordGuessClient.declarationEndpoint.absoluteString,
        "http://127.0.0.1:8795/api/feedback-declaration")
      XCTAssertEqual(ResearchFeedbackService.currentUnified.origin, "http://127.0.0.1:8793")
      XCTAssertEqual(
        ResearchWordGuessService.featureSourceSha256,
        "28c3f011cdedc11f33f98eb14c6590a98ec1192a9793b7df99cc991d5de759e7")
      XCTAssertNil(ResearchFeedbackService.currentUnified.wordGuessPins)
      try ResearchFeedbackService.browserWordGuess.requireWordGuessConfigured()
      XCTAssertThrowsError(try ResearchFeedbackService.currentUnified.requireWordGuessConfigured())
      let sources = try ResearchFeedbackService.browserWordGuess.soundBinding.fields([
        "sources", "wordBinding",
      ])["sources"]!.fields([
        "contrastSpecSha256", "featureSourceSha256", "modelFileSha256", "promptSha256",
        "resourcePolicySha256", "runtimePinsSha256", "vocabularyFileSha256", "workerReceiptSha256",
        "workerSourceSha256",
      ])
      XCTAssertEqual(
        sources["featureSourceSha256"]?.text, ResearchBrowserWordGuessService.featureSourceSha256)
      XCTAssertEqual(
        sources["workerSourceSha256"]?.text,
        "e392c577e289dcb944551bc95c2ea1ad05a39d420f18b5a6eb3a08d668e7ba04")
    }
    func testDeclarationsAndEnvelopesRejectCrossProfileBindingsWithoutChangingOldDefault() throws {
      let audio = FeedbackFixture.wav()
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: FeedbackFixture.attempt, audio: audio, prompt: BrowserGuessFixture.prompt,
        practiceContext: .adult)
      for service in [ResearchFeedbackService.wordGuess, .browserWordGuess] {
        let foreign: ResearchFeedbackService =
          service == .wordGuess ? .browserWordGuess : .wordGuess
        let ownDeclaration = try FeedbackFixture.json(BrowserGuessFixture.declaration(service))
        _ = try ResearchWordGuessDeclaration.decode(ownDeclaration, service: service)
        XCTAssertThrowsError(
          try ResearchWordGuessDeclaration.decode(ownDeclaration, service: foreign))
        let response = try FeedbackFixture.json(
          BrowserGuessFixture.response(body, audio: audio, service: service))
        let ownBinding = try BrowserGuessFixture.binding(body, audio: audio, service: service)
        let result = try ResearchWordGuessContract.decode(
          response, expectedBinding: ownBinding, pcm: FeedbackPCM.measure(audio),
          prompt: BrowserGuessFixture.prompt, service: service)
        XCTAssertEqual(result.wordGuess?.normalizedWord, "bread")
        XCTAssertThrowsError(
          try ResearchWordGuessContract.decode(
            response, expectedBinding: ownBinding, pcm: FeedbackPCM.measure(audio),
            prompt: BrowserGuessFixture.prompt, service: foreign))
        XCTAssertThrowsError(
          try ResearchWordGuessContract.decode(
            response,
            expectedBinding: BrowserGuessFixture.binding(body, audio: audio, service: foreign),
            pcm: FeedbackPCM.measure(audio), prompt: BrowserGuessFixture.prompt, service: foreign))
      }
      _ = try ResearchWordGuessDeclaration.decode(
        FeedbackFixture.json(WordGuessFixture.declaration()))
      _ = try WordGuessFixture.decode(WordGuessFixture.envelope())
      XCTAssertThrowsError(
        try ResearchWordGuessDeclaration.decode(
          FeedbackFixture.json(FeedbackFixture.declaration()), service: .browserWordGuess))
      XCTAssertThrowsError(
        try ResearchWordGuessDeclaration.decode(
          FeedbackFixture.json(BrowserGuessFixture.declaration()), service: .currentUnified))
    }
    func testEveryNewDeclarationPinMutationRefusesAndCSRFOnlyRefreshRemainsAccepted() throws {
      for key in ResearchBrowserWordGuessService.pins.keys {
        var value = BrowserGuessFixture.declaration()
        if FeedbackContract.corePins[key] != nil {
          var pins = value["pins"] as! [String: String]
          pins[key] = String(repeating: "0", count: 64)
          value["pins"] = pins
        } else if key == "feedbackPolicySha256" {
          value["feedbackPolicy"] = [
            "id": ResearchBrowserWordGuessService.policyID,
            "sha256": String(repeating: "0", count: 64),
          ]
        } else {
          value[key] = String(repeating: "0", count: 64)
        }
        XCTAssertThrowsError(
          try ResearchWordGuessDeclaration.decode(
            FeedbackFixture.json(value), service: .browserWordGuess))
      }
      var refreshed = BrowserGuessFixture.declaration()
      refreshed["csrfToken"] = String(repeating: "a", count: 64)
      XCTAssertEqual(
        try ResearchWordGuessDeclaration.decode(
          FeedbackFixture.json(refreshed), service: .browserWordGuess
        ).csrfToken, String(repeating: "a", count: 64))
    }
    func testOriginalJSONDuplicateLexicalIntegersUTF8AndGuessConsistencyStillRefuse() throws {
      let declaration = String(
        data: try FeedbackFixture.json(BrowserGuessFixture.declaration()), encoding: .utf8)!
      for text in [
        declaration.replacingOccurrences(
          of: "\"schemaVersion\":2", with: "\"schemaVersion\":2,\"schema\\u0056ersion\":2"),
        declaration.replacingOccurrences(of: "\"schemaVersion\":2", with: "\"schemaVersion\":2.0"),
        declaration.replacingOccurrences(of: "\"schemaVersion\":2", with: "\"schemaVersion\":2e0"),
      ] {
        XCTAssertNotEqual(text, declaration)
        XCTAssertThrowsError(
          try ResearchWordGuessDeclaration.decode(Data(text.utf8), service: .browserWordGuess))
      }
      XCTAssertThrowsError(
        try ResearchWordGuessDeclaration.decode(Data([0xff]), service: .browserWordGuess))
      let audio = FeedbackFixture.wav()
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: FeedbackFixture.attempt, audio: audio, prompt: BrowserGuessFixture.prompt,
        practiceContext: .adult)
      let binding = try BrowserGuessFixture.binding(body, audio: audio)
      let response = String(
        data: try FeedbackFixture.json(BrowserGuessFixture.response(body, audio: audio)),
        encoding: .utf8)!
      for (old, new) in [
        ("\"schemaVersion\":2", "\"schemaVersion\":2e0"),
        ("\"schemaVersion\":1", "\"schemaVersion\":1.0"),
        ("\"sampleCount\":3200", "\"sampleCount\":3200e0"),
        ("\"railSamples\":0", "\"railSamples\":0.0"),
        ("\"wordGuess\":\"bread\"", "\"wordGuess\":\"bread\",\"word\\u0047uess\":null"),
        ("\"wordGuess\":\"bread\"", "\"wordGuess\":\"door\""),
        ("\"wordGuess\":\"bread\"", "\"wordGuess\":\"BREAD\""),
        ("\"wordGuess\":\"bread\"", "\"wordGuess\":null"),
      ] {
        let changed = response.replacingOccurrences(of: old, with: new)
        XCTAssertNotEqual(changed, response)
        XCTAssertThrowsError(
          try ResearchWordGuessContract.decode(
            Data(changed.utf8), expectedBinding: binding, pcm: FeedbackPCM.measure(audio),
            prompt: BrowserGuessFixture.prompt, service: .browserWordGuess))
      }
    }
    func testActualClientUses8803AndExactContextBodyWithRequestStartBeforePOST() async throws {
      let audio = FeedbackFixture.wav()
      let take = try recording(audio)
      defer { try? FileManager.default.removeItem(at: take.url) }
      for context in [
        ResearchPracticeContext.adult, .child(ageYears: 6), .child(ageYears: 9),
        .child(ageYears: 12),
      ] {
        let trace = Trace()
        let body = try ResearchFeedbackClient.requestBody(
          attemptId: FeedbackFixture.attempt, audio: audio, prompt: BrowserGuessFixture.prompt,
          practiceContext: context)
        FeedbackProtocol.handler = { request in
          XCTAssertEqual(request.url?.host, "127.0.0.1")
          XCTAssertEqual(request.url?.port, 8803)
          XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), "http://127.0.0.1:8803")
          XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
          trace.append(request.httpMethod!)
          let bytes: Data
          if request.httpMethod == "GET" {
            XCTAssertEqual(request.url?.path, "/api/feedback-declaration")
            XCTAssertEqual(request.timeoutInterval, 5)
            bytes = try FeedbackFixture.json(BrowserGuessFixture.declaration())
          } else {
            XCTAssertEqual(request.url?.path, "/api/feedback")
            XCTAssertEqual(request.timeoutInterval, 100)
            XCTAssertEqual(
              request.value(forHTTPHeaderField: "X-Consumer-CSRF"),
              String(repeating: "f", count: 64))
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            XCTAssertEqual(try FeedbackFixture.requestBody(request), body)
            bytes = try FeedbackFixture.json(BrowserGuessFixture.response(body, audio: audio))
          }
          return (BrowserGuessFixture.http(request), bytes)
        }
        let result = try await ResearchWordGuessClient(
          configuration: configuration(), service: .browserWordGuess
        ).process(
          attemptId: FeedbackFixture.attempt, recording: take, prompt: BrowserGuessFixture.prompt,
          practiceContext: context,
          onEvent: { trace.append($0 == .requestStarted ? "started" : "rejected") })
        XCTAssertEqual(result.wordGuess?.normalizedWord, "bread")
        XCTAssertEqual(trace.values, ["GET", "started", "POST"])
      }
    }
    func testCurrentUnifiedAndInvalidContextRefuseBeforeTransport() async throws {
      FeedbackProtocol.handler = { _ in
        XCTFail("Invalid guess profile/context reached transport")
        throw RecordingFeedbackError.invalidResponse
      }
      let take = CapturedRecording(
        url: URL(fileURLWithPath: "/does-not-exist"), summary: .init(duration: 1, averagePower: -20)
      )
      do {
        _ = try await ResearchWordGuessClient(
          configuration: configuration(), service: .currentUnified
        ).process(
          attemptId: FeedbackFixture.attempt, recording: take, prompt: BrowserGuessFixture.prompt,
          practiceContext: .adult, onEvent: { _ in XCTFail("Unexpected event") })
        XCTFail("Legacy profile accepted by guess client")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
      for age in [5, 13] {
        do {
          _ = try await ResearchWordGuessClient(
            configuration: configuration(), service: .browserWordGuess
          ).process(
            attemptId: FeedbackFixture.attempt, recording: take, prompt: BrowserGuessFixture.prompt,
            practiceContext: .child(ageYears: age), onEvent: { _ in XCTFail("Unexpected event") })
          XCTFail("Invalid context accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .unsupportedAge) }
      }
    }
    func testDeclarationTransportAndForeignBindingsPreventPOSTBeforeMediaRead() async throws {
      let valid = try FeedbackFixture.json(BrowserGuessFixture.declaration())
      let foreign = try FeedbackFixture.json(WordGuessFixture.declaration())
      let cases: [(Data, Int, String, URL?)] = [
        (foreign, 200, "application/json", nil),
        (Data(repeating: 32, count: 16001), 200, "application/json", nil),
        (Data([0xff]), 200, "application/json", nil),
        (valid, 200, "text/html", nil),
        (valid, 302, "application/json", nil),
        (
          valid, 200, "application/json",
          URL(string: ResearchWordGuessClient.declarationEndpoint.absoluteString)
        ),
      ]
      for (data, status, mime, url) in cases {
        let trace = Trace()
        FeedbackProtocol.handler = { request in
          trace.append(request.httpMethod!)
          return (BrowserGuessFixture.http(request, status: status, mime: mime, url: url), data)
        }
        do {
          _ = try await ResearchWordGuessClient(
            configuration: configuration(), service: .browserWordGuess
          ).process(
            attemptId: FeedbackFixture.attempt,
            recording: .init(
              url: URL(fileURLWithPath: "/does-not-exist"),
              summary: .init(duration: 1, averagePower: -20)), prompt: BrowserGuessFixture.prompt,
            practiceContext: .adult,
            onEvent: { event in trace.append(event == .requestStarted ? "started" : "rejected") })
          XCTFail("Invalid declaration accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        XCTAssertEqual(trace.values.first, "GET")
        XCTAssertFalse(trace.values.contains("POST"))
        XCTAssertFalse(trace.values.contains("started"))
      }
    }
    func testPOSTEnvelopeCapMIMEUTF8AndOldPinsRefuseAfterOneRequestStart() async throws {
      let audio = FeedbackFixture.wav()
      let take = try recording(audio)
      defer { try? FileManager.default.removeItem(at: take.url) }
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: FeedbackFixture.attempt, audio: audio, prompt: BrowserGuessFixture.prompt,
        practiceContext: .adult)
      let valid = try FeedbackFixture.json(BrowserGuessFixture.response(body, audio: audio))
      let old = try FeedbackFixture.json(
        BrowserGuessFixture.response(body, audio: audio, service: .wordGuess))
      for (data, mime) in [
        (Data(repeating: 32, count: 16001), "application/json"), (Data([0xff]), "application/json"),
        (valid, "text/html"), (old, "application/json"),
      ] {
        let trace = Trace()
        FeedbackProtocol.handler = { request in
          trace.append(request.httpMethod!)
          return request.httpMethod == "GET"
            ? (
              BrowserGuessFixture.http(request),
              try FeedbackFixture.json(BrowserGuessFixture.declaration())
            )
            : (BrowserGuessFixture.http(request, mime: mime), data)
        }
        do {
          _ = try await ResearchWordGuessClient(
            configuration: configuration(), service: .browserWordGuess
          ).process(
            attemptId: FeedbackFixture.attempt, recording: take, prompt: BrowserGuessFixture.prompt,
            practiceContext: .adult,
            onEvent: { event in trace.append(event == .requestStarted ? "started" : "rejected") })
          XCTFail("Invalid envelope accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        XCTAssertEqual(trace.values, ["GET", "started", "POST"])
      }
    }
    func testSoundCrossProfilePreparedAndControlInputsRefuseBeforeTransport() async throws {
      FeedbackProtocol.handler = { _ in
        XCTFail("Foreign prepared/control reached transport")
        throw RecordingFeedbackError.invalidResponse
      }
      for service in [ResearchFeedbackService.currentUnified, .wordGuess, .browserWordGuess] {
        for foreign in [ResearchFeedbackService.currentUnified, .wordGuess, .browserWordGuess]
        where foreign != service {
          let declaration = BrowserGuessFixture.soundDeclaration(foreign)
          let prepared = try ResearchSoundContract.prepare(
            audio: FeedbackFixture.wav(), declaration: declaration, context: SoundFixture.context,
            service: foreign)
          let client = ResearchSoundClient(configuration: configuration(), service: service)
          XCTAssertThrowsError(
            try ResearchSoundContract.declaration(
              BrowserGuessFixture.soundData(foreign), service: service))
          do {
            _ = try await client.observe(prepared)
            XCTFail("Foreign observe accepted")
          } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
          do {
            try await client.cancel(prepared)
            XCTFail("Foreign cancel accepted")
          } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
          do {
            try await client.reset(declaration: declaration, sessionId: "session", generation: 4)
            XCTFail("Foreign reset accepted")
          } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        }
      }
    }
    func testSoundDeclarationObserveCancelAndResetUse8803AndCompiledBinding() async throws {
      let declaration = BrowserGuessFixture.soundDeclaration(.browserWordGuess)
      let prepared = try ResearchSoundContract.prepare(
        audio: FeedbackFixture.wav(), declaration: declaration, context: SoundFixture.context,
        service: .browserWordGuess)
      let trace = Trace()
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.url?.port, 8803)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), "http://127.0.0.1:8803")
        let path = request.url!.path
        trace.append(path)
        let data: Data
        if path == "/api/sound-declaration" {
          XCTAssertEqual(request.httpMethod, "GET")
          data = try BrowserGuessFixture.soundData(.browserWordGuess)
        } else {
          XCTAssertEqual(request.httpMethod, "POST")
          XCTAssertEqual(
            request.value(forHTTPHeaderField: "X-Consumer-CSRF"), declaration.csrfToken)
          let body = try FeedbackFixture.requestBody(request)
          if path == "/api/sound-observation" {
            XCTAssertEqual(body, prepared.body)
            data = try SoundFixture.response(prepared)
          } else {
            var response = try JSONSerialization.jsonObject(with: body) as! [String: Any]
            if path == "/api/sound-cancel" {
              response.removeValue(forKey: "ownership")
              response["cancelAccepted"] = true
            } else {
              XCTAssertEqual(path, "/api/sound-reset")
              response["resetAccepted"] = true
            }
            data = try FeedbackFixture.json(response)
          }
        }
        return (BrowserGuessFixture.http(request), data)
      }
      let client = ResearchSoundClient(configuration: configuration(), service: .browserWordGuess)
      let received = try await client.declaration()
      XCTAssertEqual(received, declaration)
      let result = try await client.observe(prepared)
      XCTAssertEqual(result.status, .inconclusive)
      try await client.cancel(prepared)
      try await client.reset(declaration: declaration, sessionId: "session", generation: 4)
      XCTAssertEqual(
        trace.values,
        [
          "/api/sound-declaration", "/api/sound-observation", "/api/sound-cancel",
          "/api/sound-reset",
        ])
    }
    func testPublicLicensedExampleUses8803WithoutChangingMetadataOrBytes() async throws {
      let example = try XCTUnwrap(ResearchPracticeExamples.example(for: BrowserGuessFixture.prompt))
      let url = try XCTUnwrap(
        Bundle(for: Self.self).url(forResource: "public-example-bread", withExtension: "wav"))
      let bytes = try Data(contentsOf: url)
      XCTAssertEqual(FeedbackContract.sha(bytes), example.wavSha256)
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(
          request.url?.absoluteString, "http://127.0.0.1:8803/api/public-references/bread")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), "http://127.0.0.1:8803")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "audio/wav")
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Consumer-CSRF"))
        return (BrowserGuessFixture.http(request, mime: "audio/wav"), bytes)
      }
      let loader = ResearchPracticeExampleClient(
        configuration: configuration(), service: .browserWordGuess)
      XCTAssertEqual(loader.example(for: BrowserGuessFixture.prompt), example)
      let received = try await loader.load(example: example)
      XCTAssertEqual(received, bytes)
      XCTAssertEqual(try FeedbackPCM.measure(received).sampleCount, 8917)
    }
    private final class Trace: @unchecked Sendable {
      private let lock = NSLock()
      private var entries: [String] = []
      func append(_ item: String) {
        lock.lock()
        defer { lock.unlock() }
        entries.append(item)
      }
      var values: [String] {
        lock.lock()
        defer { lock.unlock() }
        return entries
      }
    }
  }
#endif
