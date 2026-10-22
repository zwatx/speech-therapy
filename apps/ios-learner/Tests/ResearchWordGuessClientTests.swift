#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchWordGuessClientTests: XCTestCase {
    override func tearDown() {
      FeedbackProtocol.handler = nil
      super.tearDown()
    }
    func testActualClientUsesSuccessorOnlyAndRequestStartedPrecedesPOST() async throws {
      let audio = FeedbackFixture.wav()
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-guess-client-\(UUID()).wav")
      try audio.write(to: file)
      defer { try? FileManager.default.removeItem(at: file) }
      let trace = Trace()
      let prompt = WordGuessFixture.prompt
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: FeedbackFixture.attempt, audio: audio,
        prompt: prompt, practiceContext: .child(ageYears: 9))
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), ResearchWordGuessService.origin)
        if request.httpMethod == "GET" {
          trace.append("get")
          XCTAssertEqual(request.url, ResearchWordGuessClient.declarationEndpoint)
          XCTAssertEqual(request.timeoutInterval, 5)
          return (Self.http(request), try FeedbackFixture.json(WordGuessFixture.declaration()))
        }
        trace.append("post")
        XCTAssertEqual(request.url, ResearchWordGuessClient.endpoint)
        XCTAssertEqual(request.timeoutInterval, 100)
        XCTAssertEqual(try FeedbackFixture.requestBody(request), body)
        XCTAssertEqual(
          request.value(forHTTPHeaderField: "X-Consumer-CSRF"), String(repeating: "f", count: 64))
        return (
          Self.http(request),
          try FeedbackFixture.json(WordGuessFixture.response(body, audio: audio, guess: "bread"))
        )
      }
      let result = try await ResearchWordGuessClient(configuration: configuration()).process(
        attemptId: FeedbackFixture.attempt,
        recording: .init(url: file, summary: .init(duration: 0.2, averagePower: -12)),
        prompt: prompt, practiceContext: .child(ageYears: 9),
        onEvent: { event in
          XCTAssertEqual(event, .requestStarted)
          trace.append("started")
        })
      XCTAssertEqual(result.wordGuess?.normalizedWord, "bread")
      XCTAssertEqual(trace.values, ["get", "started", "post"])
    }
    func testDeclarationRefusalCapsMIMEAndRedirectStatusPreventPOST() async throws {
      let cases: [(Data, Int, String, URL?)] = [
        (try FeedbackFixture.json(FeedbackFixture.declaration()), 200, "application/json", nil),
        (Data(repeating: 32, count: 16001), 200, "application/json", nil),
        (Data(#"{"schemaVersion":2,"schemaVersion":2}"#.utf8), 200, "application/json", nil),
        (try FeedbackFixture.json(WordGuessFixture.declaration()), 302, "application/json", nil),
        (try FeedbackFixture.json(WordGuessFixture.declaration()), 200, "text/html", nil),
        (
          try FeedbackFixture.json(WordGuessFixture.declaration()), 200, "application/json",
          URL(string: "http://127.0.0.1:8793/api/feedback-declaration")
        ),
      ]
      for (bytes, status, mime, url) in cases {
        let trace = Trace()
        FeedbackProtocol.handler = { request in
          trace.append(request.httpMethod!)
          return (
            HTTPURLResponse(
              url: url ?? request.url!, statusCode: status, httpVersion: nil,
              headerFields: ["Content-Type": mime])!, bytes
          )
        }
        var events: [ResearchFeedbackProcessingEvent] = []
        do {
          _ = try await ResearchWordGuessClient(configuration: configuration()).process(
            attemptId: FeedbackFixture.attempt,
            recording: .init(
              url: URL(fileURLWithPath: "/does-not-exist"),
              summary: .init(duration: 1, averagePower: -20)),
            prompt: WordGuessFixture.prompt, practiceContext: .adult, onEvent: { events.append($0) }
          )
          XCTFail("Invalid declaration transport accepted")
        } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
        XCTAssertEqual(trace.values, ["GET"])
        XCTAssertFalse(events.contains(.requestStarted))
      }
    }
    func testWholePOSTEnvelopeResponseCapRejectsAfterOneExplicitRequestStart() async throws {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-guess-cap-\(UUID()).wav")
      try FeedbackFixture.wav().write(to: file)
      defer { try? FileManager.default.removeItem(at: file) }
      let trace = Trace()
      FeedbackProtocol.handler = { request in
        trace.append(request.httpMethod!)
        return (
          Self.http(request),
          request.httpMethod == "GET"
            ? try FeedbackFixture.json(WordGuessFixture.declaration())
            : Data(repeating: 32, count: 16001)
        )
      }
      var events: [ResearchFeedbackProcessingEvent] = []
      do {
        _ = try await ResearchWordGuessClient(configuration: configuration()).process(
          attemptId: FeedbackFixture.attempt,
          recording: .init(url: file, summary: .init(duration: 0.2, averagePower: -12)),
          prompt: WordGuessFixture.prompt, practiceContext: .adult, onEvent: { events.append($0) })
        XCTFail("Oversize envelope accepted")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
      XCTAssertEqual(trace.values, ["GET", "POST"])
      XCTAssertEqual(events, [.requestStarted])
    }
    func testInvalidContextAndCancellationSendNothing() async throws {
      FeedbackProtocol.handler = { _ in
        XCTFail("Unexpected transport")
        throw RecordingFeedbackError.invalidResponse
      }
      let client = ResearchWordGuessClient(configuration: configuration())
      do {
        _ = try await client.process(
          attemptId: FeedbackFixture.attempt,
          recording: .init(
            url: URL(fileURLWithPath: "/does-not-exist"),
            summary: .init(duration: 1, averagePower: -20)),
          prompt: WordGuessFixture.prompt, practiceContext: .child(ageYears: 5),
          onEvent: { _ in XCTFail("Unexpected event") })
        XCTFail("Invalid context accepted")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .unsupportedAge) }
      let task = Task { @MainActor in
        try Task.checkCancellation()
        return try await client.process(
          attemptId: FeedbackFixture.attempt,
          recording: .init(
            url: URL(fileURLWithPath: "/does-not-exist"),
            summary: .init(duration: 1, averagePower: -20)),
          prompt: WordGuessFixture.prompt, practiceContext: .adult,
          onEvent: { _ in XCTFail("Unexpected event") })
      }
      task.cancel()
      do {
        _ = try await task.value
        XCTFail("Cancelled operation accepted")
      } catch { XCTAssertTrue(error is CancellationError) }
    }
    private func configuration() -> URLSessionConfiguration {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [FeedbackProtocol.self]
      return config
    }
    private nonisolated static func http(_ request: URLRequest) -> HTTPURLResponse {
      HTTPURLResponse(
        url: request.url!, statusCode: 200, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])!
    }
    private final class Trace: @unchecked Sendable {
      private let lock = NSLock()
      private var items: [String] = []
      func append(_ item: String) {
        lock.lock()
        defer { lock.unlock() }
        items.append(item)
      }
      var values: [String] {
        lock.lock()
        defer { lock.unlock() }
        return items
      }
    }
  }
#endif
