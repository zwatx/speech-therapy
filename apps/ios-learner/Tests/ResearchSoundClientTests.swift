#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchSoundClientTests: XCTestCase {
    override func tearDown() {
      FeedbackProtocol.handler = nil
      super.tearDown()
    }
    private func client() -> ResearchSoundClient {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [FeedbackProtocol.self]
      return ResearchSoundClient(configuration: configuration)
    }
    func testExactLocalDeclarationAndObservationTransport() async throws {
      let prepared = try SoundFixture.prepared()
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.url?.host, "127.0.0.1")
        XCTAssertEqual(request.url?.port, 8793)
        XCTAssertEqual(request.url?.scheme, "http")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), "http://127.0.0.1:8793")
        XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
        XCTAssertFalse(request.httpShouldHandleCookies)
        let body: Data
        if request.url?.path == "/api/sound-declaration" {
          XCTAssertEqual(request.httpMethod, "GET")
          XCTAssertNil(request.value(forHTTPHeaderField: "X-Consumer-CSRF"))
          body = Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitDeclaration.utf8)
        } else {
          XCTAssertEqual(request.url?.path, "/api/sound-observation")
          XCTAssertEqual(request.httpMethod, "POST")
          XCTAssertEqual(
            request.value(forHTTPHeaderField: "X-Consumer-CSRF"), String(repeating: "f", count: 64))
          XCTAssertNil(request.value(forHTTPHeaderField: "X-Cadence-CSRF"))
          XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
          XCTAssertEqual(try FeedbackFixture.requestBody(request), prepared.body)
          body = Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitResponse.utf8)
        }
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json; charset=utf-8"])!, body
        )
      }
      let client = client()
      let declaration = try await client.declaration()
      XCTAssertEqual(declaration, SoundFixture.declaration)
      let result = try await client.observe(prepared)
      XCTAssertEqual(result.status, .inconclusive)
      XCTAssertNil(result.preference)
    }
    func testBoundCancelAndStrictNewerResetWire() async throws {
      let prepared = try SoundFixture.prepared()
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(
          request.value(forHTTPHeaderField: "X-Consumer-CSRF"), String(repeating: "f", count: 64))
        let body =
          try JSONSerialization.jsonObject(with: FeedbackFixture.requestBody(request))
          as! [String: Any]
        var response: [String: Any]
        if request.url?.path == "/api/sound-cancel" {
          XCTAssertEqual(
            Set(body.keys),
            ["schemaVersion", "serverNonce", "attemptId", "requestSha256", "ownership"])
          XCTAssertEqual(body["requestSha256"] as? String, prepared.requestSha256)
          XCTAssertEqual(body["attemptId"] as? String, SoundFixture.context.attemptId)
          XCTAssertEqual(
            try ResearchSoundJSON.parse(FeedbackFixture.json(body["ownership"]!)),
            prepared.ownership)
          response = body
          response.removeValue(forKey: "ownership")
          response["cancelAccepted"] = false
        } else {
          XCTAssertEqual(request.url?.path, "/api/sound-reset")
          XCTAssertEqual(
            Set(body.keys), ["schemaVersion", "serverNonce", "sessionId", "generation"])
          XCTAssertEqual(body["generation"] as? Int, 4)
          response = body
          response["resetAccepted"] = true
        }
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, try FeedbackFixture.json(response)
        )
      }
      let client = client()
      try await client.cancel(prepared)
      try await client.reset(
        declaration: SoundFixture.declaration, sessionId: "unit-session", generation: 4)
    }
    func testMIMEStatusDestinationOversizeAndTransportFailures() async throws {
      for mutation in 0..<10 {
        FeedbackProtocol.handler = { request in
          if mutation == 5 { throw URLError(.timedOut) }
          if mutation == 6 { throw URLError(.cancelled) }
          let url =
            mutation == 0
            ? URL(string: "https://127.0.0.1:8793/api/sound-declaration")!
            : mutation == 7
              ? URL(string: "http://127.0.0.1:8794/api/sound-declaration")!
              : mutation == 8
                ? URL(string: "http://127.0.0.1:8789/api/sound-declaration")!
                : mutation == 9
                  ? URL(string: "http://127.0.0.1:8788/api/sound-declaration")! : request.url!
          let status = mutation == 1 ? 302 : mutation == 2 ? 403 : 200
          let type = mutation == 3 ? "text/plain" : "application/json"
          let body =
            mutation == 4 ? Data(repeating: 32, count: 12001) : try SoundFixture.declarationData()
          return (
            HTTPURLResponse(
              url: url, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": type])!,
            body
          )
        }
        do {
          _ = try await client().declaration()
          XCTFail("Expected refusal \(mutation)")
        } catch {
          if mutation == 5 { XCTAssertEqual(error as? RecordingFeedbackError, .timeout) }
          if mutation == 6 { XCTAssertTrue(error is CancellationError) }
        }
      }
    }
    func testHistoricalDeclarationAndSavedToneReplyAreRejectedByUnifiedClient() async throws {
      FeedbackProtocol.handler = { request in
        let body =
          request.url?.path == "/api/sound-declaration"
          ? Data(ResearchSoundFixtureMetadata.rootGoldenDeclaration.utf8)
          : Data(ResearchSoundFixtureMetadata.savedPublicResponse.utf8)
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, body
        )
      }
      do {
        _ = try await client().declaration()
        XCTFail("Historical declaration accepted by unified client")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
      do {
        _ = try await client().observe(SoundFixture.prepared())
        XCTFail("Historical saved tone reply accepted by unified client")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
    }
    func testPrior8789DeclarationAndResponseAreRejectedByUnifiedClient() async throws {
      FeedbackProtocol.handler = { request in
        let body =
          request.url?.path == "/api/sound-declaration"
          ? Data(ResearchSoundSuccessorFixtureMetadata.successorUnitDeclaration.utf8)
          : Data(ResearchSoundSuccessorFixtureMetadata.successorUnitResponse.utf8)
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, body
        )
      }
      do {
        _ = try await client().declaration()
        XCTFail("Prior8789 declaration accepted by unified client")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
      do {
        _ = try await client().observe(SoundFixture.prepared())
        XCTFail("Prior8789 reply accepted by unified client")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidResponse) }
    }
    func testPrepareReadsOwnedGeneratedPCMAndRefusesSymlink() async throws {
      let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: root) }
      let file = root.appendingPathComponent("generated.wav")
      try FeedbackFixture.wav().write(to: file)
      let recording = CapturedRecording(url: file, summary: .init(duration: 0.2, averagePower: -20))
      let prepared = try await client().prepare(
        recording: recording, declaration: SoundFixture.declaration, context: SoundFixture.context)
      XCTAssertEqual(prepared, try SoundFixture.prepared())
      let link = root.appendingPathComponent("link.wav")
      try FileManager.default.createSymbolicLink(at: link, withDestinationURL: file)
      do {
        _ = try await client().prepare(
          recording: .init(url: link, summary: recording.summary),
          declaration: SoundFixture.declaration, context: SoundFixture.context)
        XCTFail("Symlink accepted")
      } catch { XCTAssertEqual(error as? RecordingFeedbackError, .invalidRecording) }
    }
  }
#endif
