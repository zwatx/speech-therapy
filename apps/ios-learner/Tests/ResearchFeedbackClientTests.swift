#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchFeedbackClientTests: XCTestCase {
    func testEveryCatalogPromptHasExactFreshDeclarationCSRFBodyAndResponseBindings() async throws {
      for prompt in ResearchFeedbackCatalog.prompts {
        let result = try await execute(prompt: prompt)
        XCTAssertEqual(result.word, .modelMatched)
        XCTAssertEqual(result.targetUnsupported, prompt.targetPhone == "ZH")
        XCTAssertEqual(prompt.requestPrompt.targets.count, 1)
        XCTAssertEqual(prompt.requestPrompt.targets[0].id, prompt.id)
      }
      XCTAssertEqual(ResearchFeedbackCatalog.prompts.count, 15)
      XCTAssertEqual(
        ResearchFeedbackCatalog.prompts.first { $0.id == "n-middle-banana" }?.occurrenceIndex, 2)
    }
    func testAllTenDeclarationPinsAndDisabledAvailabilityRefuseBeforeUpload() async {
      for key in FeedbackContract.pins.keys {
        await rejected(declaration: { value in
          if FeedbackContract.corePins[key] != nil {
            var pins = value["pins"] as! [String: String]
            pins[key] = String(repeating: "0", count: 64)
            value["pins"] = pins
          } else if key == "feedbackPolicySha256" {
            value["feedbackPolicy"] = [
              "id": "consumer-recording-feedback-v2", "sha256": String(repeating: "0", count: 64),
            ]
          } else {
            value[key] = String(repeating: "0", count: 64)
          }
        })
      }
      await rejected(
        error: .processingUnavailable, declaration: { $0["processingAvailable"] = false })
      await rejected(declaration: { $0["csrfToken"] = "token" })
      await rejected(declaration: { $0["processingAvailable"] = 1 })
      await rejected(declaration: { $0["extra"] = "private" })
    }
    func testHistoricalWordDeclarationIsRejectedBeforeUpload() async throws {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [FeedbackProtocol.self]
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertEqual(request.url, ResearchFeedbackClient.declarationEndpoint)
        var declaration = FeedbackFixture.declaration()
        declaration["feedbackSourceSha256"] = "e60137e15cf6efe542456b4232b4e88c975c9fbead459985a0c6eca529ac314c"
        declaration["wrapperSourceSha256"] = "d05830fe9a0c84ac8c4a1db6f1658bae4fe8f1fde94790636c4466d85dad2b18"
        declaration["feedbackPolicy"] = ["id": "consumer-recording-feedback-v1", "sha256": "6936603a716e4c18bbf96d60c7f6babc906e23d397aff04b0955513618644a3f"]
        return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, try FeedbackFixture.json(declaration))
      }
      defer { FeedbackProtocol.handler = nil }
      do {
        _ = try await ResearchFeedbackClient(configuration: configuration).process(
          attemptId: UUID(), recording: .init(url: URL(fileURLWithPath: "/does-not-exist"), summary: .init(duration: 1, averagePower: -20)),
          prompt: ResearchFeedbackCatalog.prompts[0], practiceContext: .adult)
        XCTFail("Old declaration accepted")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
    }
    func testRedirectDestinationMIMEStatusOversizeAndMalformedTransportRefuse() async {
      for status in [302, 400, 503] { await rejected(status: status) }
      await rejected(url: URL(string: "http://127.0.0.1:8778/v1/admission")!)
      await rejected(mime: "text/html")
      await rejected(raw: Data(repeating: 32, count: 16001))
      await rejected(raw: Data(#"{"schemaVersion":1,"schemaVersion":1}"#.utf8))
      await rejected(raw: Data([0xff]))
    }
    func testInvalidChildContextAndUnknownPromptRefuseBeforeTransport() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      FeedbackProtocol.handler = { _ in
        XCTFail("preflight must not start transport")
        throw URLError(.badURL)
      }
      defer { FeedbackProtocol.handler = nil }
      let recording = CapturedRecording(
        url: URL(fileURLWithPath: "/does-not-exist"), summary: .init(duration: 1, averagePower: -20)
      )
      for age in [5, 13] {
        do {
          _ = try await ResearchFeedbackClient(configuration: config).process(
            attemptId: UUID(), recording: recording, prompt: ResearchFeedbackCatalog.prompts[0],
            practiceContext: .child(ageYears: age))
          XCTFail("age accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .unsupportedAge) }
      }
      let unknown = ResearchFeedbackPrompt(
        id: "arbitrary", word: "rabbit", phones: ["R"], occurrenceIndex: 0, targetPhone: "R")
      do {
        _ = try await ResearchFeedbackClient(configuration: config).process(
          attemptId: UUID(), recording: recording, prompt: unknown, practiceContext: .child(ageYears: 9))
        XCTFail("prompt accepted")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .unsupportedPrompt) }
    }
    func testInFlightDeclarationCancellationCancelsURLSessionAndCannotUpload() async {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackDelayedProtocol.self]
      FeedbackDelayedProtocol.started = false
      FeedbackDelayedProtocol.stopped = false
      let client = ResearchFeedbackClient(configuration: config)
      let task = Task {
        try await client.process(
          attemptId: UUID(),
          recording: .init(
            url: URL(fileURLWithPath: "/does-not-exist"),
            summary: .init(duration: 1, averagePower: -20)),
          prompt: ResearchFeedbackCatalog.prompts[0], practiceContext: .child(ageYears: 9))
      }
      for _ in 0..<10000 {
        if FeedbackDelayedProtocol.started { break }
        await Task.yield()
      }
      XCTAssertTrue(FeedbackDelayedProtocol.started)
      task.cancel()
      do {
        _ = try await task.value
        XCTFail("cancel accepted")
      } catch { XCTAssertTrue(error is CancellationError) }
      for _ in 0..<10000 {
        if FeedbackDelayedProtocol.stopped { break }
        await Task.yield()
      }
      XCTAssertTrue(FeedbackDelayedProtocol.stopped)
    }

    private func rejected(
      error: RecordingFeedbackError = .invalidResponse, status: Int = 200, url: URL? = nil,
      mime: String = "application/json", raw: Data? = nil,
      declaration: @escaping @Sendable (inout [String: Any]) -> Void = { _ in }
    ) async {
      do {
        _ = try await execute(
          status: status, url: url, mime: mime, raw: raw, declaration: declaration)
        XCTFail("Expected refusal")
      } catch let caught { XCTAssertEqual(caught as? RecordingFeedbackError, error) }
    }
    private func execute(
      prompt: ResearchFeedbackPrompt = ResearchFeedbackCatalog.prompts[3], status: Int = 200,
      url: URL? = nil, mime: String = "application/json", raw: Data? = nil,
      declaration: @escaping @Sendable (inout [String: Any]) -> Void = { _ in }
    ) async throws -> RecordingFeedback {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString + ".wav")
      let audio = FeedbackFixture.wav()
      try audio.write(to: file)
      defer {
        try? FileManager.default.removeItem(at: file)
        FeedbackProtocol.handler = nil
      }
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), ResearchFeedbackClient.origin)
        let data: Data
        if request.url == ResearchFeedbackClient.declarationEndpoint {
          XCTAssertEqual(request.httpMethod, "GET")
          var value = FeedbackFixture.declaration()
          declaration(&value)
          data = try FeedbackFixture.json(value)
        } else {
          XCTAssertEqual(request.url, ResearchFeedbackClient.endpoint)
          XCTAssertEqual(request.httpMethod, "POST")
          XCTAssertEqual(
            request.value(forHTTPHeaderField: "X-Consumer-CSRF"), String(repeating: "f", count: 64))
          let body = try FeedbackFixture.requestBody(request)
          let object = try JSONSerialization.jsonObject(with: body) as! [String: Any]
          XCTAssertEqual(
            Set(object.keys), ["schemaVersion", "attemptId", "practiceContext", "prompt", "audioBase64"])
          XCTAssertEqual(Data(base64Encoded: object["audioBase64"] as! String), audio)
          XCTAssertEqual(
            object["attemptId"] as? String, FeedbackFixture.attempt.uuidString.lowercased())
          XCTAssertEqual(object["schemaVersion"] as? Int, 2)
          let context = object["practiceContext"] as! [String: Any]
          XCTAssertEqual(Set(context.keys), ["kind", "ageYears"])
          XCTAssertEqual(context["kind"] as? String, "child")
          XCTAssertEqual(context["ageYears"] as? Int, 9)
          let actualPrompt = try JSONSerialization.data(
            withJSONObject: object["prompt"]!, options: [.sortedKeys, .withoutEscapingSlashes])
          XCTAssertEqual(actualPrompt, try FeedbackContract.encoder().encode(prompt.requestPrompt))
          data = try FeedbackFixture.json(
            FeedbackFixture.response(body, audio: audio, unsupported: prompt.targetUnsupported))
        }
        return (
          HTTPURLResponse(
            url: url ?? request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": mime])!, raw ?? data
        )
      }
      return try await ResearchFeedbackClient(configuration: config).process(
        attemptId: FeedbackFixture.attempt,
        recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)), prompt: prompt,
        practiceContext: .child(ageYears: 9))
    }
  }

  private final class FeedbackDelayedProtocol: URLProtocol, @unchecked Sendable {
    private static let state = DelayState()
    static var started: Bool {
      get { state.get(true) }
      set { state.set(true, newValue) }
    }
    static var stopped: Bool {
      get { state.get(false) }
      set { state.set(false, newValue) }
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { Self.started = true }
    override func stopLoading() { Self.stopped = true }
  }
  private final class DelayState: @unchecked Sendable {
    private let lock = NSLock()
    private var started = false
    private var stopped = false
    func get(_ start: Bool) -> Bool {
      lock.lock()
      defer { lock.unlock() }
      return start ? started : stopped
    }
    func set(_ start: Bool, _ value: Bool) {
      lock.lock()
      defer { lock.unlock() }
      if start { started = value } else { stopped = value }
    }
  }
#endif
