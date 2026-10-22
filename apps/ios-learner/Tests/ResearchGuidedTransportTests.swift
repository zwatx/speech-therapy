#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Real client against generated URLProtocol replies; no service, model or audio device.
  @MainActor
  final class ResearchGuidedTransportTests: XCTestCase {
    func testRequestStartIsOnceAfterDeclarationAndBeforeTransport() async throws {
      let log = GuidedTransportLog()
      let result = try await run(log: log)
      XCTAssertEqual(log.events, ["GET", "requestStarted", "POST"])
      XCTAssertEqual(result.word, .modelMatched)
      XCTAssertFalse(result.pronunciationCorrectnessAssessed)
      XCTAssertFalse(result.diagnosisProvided)
    }

    func testBadSourceAndLocalAudioNeverStartRequest() async throws {
      for fault in [Fault.source, .audio] {
        let log = GuidedTransportLog()
        do {
          _ = try await run(log: log, fault: fault)
          XCTFail("Invalid input accepted")
        } catch {
          XCTAssertEqual(
            error as? RecordingFeedbackError,
            fault == .source ? .invalidResponse : .invalidRecording)
        }
        XCTAssertFalse(log.events.contains("requestStarted"))
        XCTAssertFalse(log.events.contains("POST"))
        XCTAssertEqual(log.events.filter { $0 == "GET" }.count, 1)
      }
    }

    func testTransportStartDoesNotEstablishValidResponseOrUploadCompletion() async throws {
      for fault in [Fault.response, .transport] {
        let log = GuidedTransportLog()
        do {
          _ = try await run(log: log, fault: fault)
          XCTFail("Failed response accepted")
        } catch {
          XCTAssertEqual(
            error as? RecordingFeedbackError,
            fault == .response ? .invalidResponse : .serviceUnavailable)
        }
        XCTAssertEqual(log.events, ["GET", "requestStarted", "POST"])
      }
    }

    private enum Fault: Sendable { case none, source, audio, response, transport }
    private func run(log: GuidedTransportLog, fault: Fault = .none) async throws
      -> RecordingFeedback
    {
      let audio = FeedbackFixture.wav()
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-guided-transport-\(UUID().uuidString).wav")
      try (fault == .audio ? Data([0]) : audio).write(to: file)
      defer {
        try? FileManager.default.removeItem(at: file)
        FeedbackProtocol.handler = nil
      }
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [FeedbackProtocol.self]
      FeedbackProtocol.handler = { request in
        let data: Data
        if request.url == ResearchFeedbackClient.declarationEndpoint {
          log.append("GET")
          var declaration = FeedbackFixture.declaration()
          if fault == .source { declaration["contentSha256"] = String(repeating: "0", count: 64) }
          data = try FeedbackFixture.json(declaration)
        } else {
          log.append("POST")
          XCTAssertEqual(request.httpMethod, "POST")
          XCTAssertEqual(request.url, ResearchFeedbackClient.endpoint)
          if fault == .transport { throw URLError(.cannotConnectToHost) }
          let body = try FeedbackFixture.requestBody(request)
          var response = try FeedbackFixture.response(body, audio: audio)
          if fault == .response {
            var binding = response["binding"] as! [String: Any]
            binding["audioSha256"] = String(repeating: "0", count: 64)
            response["binding"] = binding
          }
          data = try FeedbackFixture.json(response)
        }
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, data
        )
      }
      return try await ResearchFeedbackClient(configuration: configuration).process(
        attemptId: FeedbackFixture.attempt,
        recording: .init(url: file, summary: .init(duration: 0.2, averagePower: -12)),
        prompt: ResearchFeedbackCatalog.prompts[0], practiceContext: .child(ageYears: 9)
      ) { event in
        switch event {
        case .requestStarted: log.append("requestStarted")
        case .declarationRejected: log.append("declarationRejected")
        }
      }
    }
  }

  private final class GuidedTransportLog: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String] = []
    var events: [String] {
      lock.lock()
      defer { lock.unlock() }
      return storage
    }
    func append(_ event: String) {
      lock.lock()
      defer { lock.unlock() }
      storage.append(event)
    }
  }
#endif
