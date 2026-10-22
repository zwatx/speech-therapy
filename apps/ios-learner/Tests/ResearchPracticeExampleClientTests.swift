#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchPracticeExampleClientTests: XCTestCase {
    private var bread: ResearchPracticeExample {
      ResearchPracticeExamples.all.first { $0.sourceWord == "bread" }!
    }
    private func publicWav() throws -> Data {
      let url = try XCTUnwrap(
        Bundle(for: Self.self).url(forResource: "public-example-bread", withExtension: "wav"))
      let data = try Data(contentsOf: url)
      XCTAssertEqual(FeedbackContract.sha(data), bread.wavSha256)
      return data
    }
    private func client(
      deadline: Duration = .seconds(10), protocols: [AnyClass] = [FeedbackProtocol.self]
    ) -> ResearchPracticeExampleClient {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = protocols
      return ResearchPracticeExampleClient(configuration: configuration, deadline: deadline)
    }
    private func serve(
      _ data: Data, status: Int = 200, mime: String = "audio/wav", url: URL? = nil,
      length: Int? = nil
    ) {
      FeedbackProtocol.handler = { request in
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertEqual(
          request.url?.absoluteString,
          ResearchFeedbackClient.origin + "/api/public-references/bread")
        XCTAssertNil(request.httpBody)
        XCTAssertNil(request.value(forHTTPHeaderField: "Range"))
        XCTAssertNil(request.value(forHTTPHeaderField: "X-Consumer-CSRF"))
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "audio/wav")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), ResearchFeedbackClient.origin)
        var headers = ["Content-Type": mime]
        if let length { headers["Content-Length"] = String(length) }
        return (
          HTTPURLResponse(
            url: url ?? request.url!, statusCode: status, httpVersion: nil, headerFields: headers)!,
          data
        )
      }
    }
    func testActualPublicLicensedFixturePassesFullGetHashAndRIFFValidation() async throws {
      let data = try publicWav()
      serve(data)
      defer { FeedbackProtocol.handler = nil }
      let received = try await client().load(example: bread)
      XCTAssertEqual(received, data)
      XCTAssertEqual(try FeedbackPCM.measure(data).sampleCount, 8917)
    }
    func testBadStatusMimeFinalURLRedirectStatusAndDeclaredOversizeFailClosed() async throws {
      let data = try publicWav()
      defer { FeedbackProtocol.handler = nil }
      for scenario in 0..<5 {
        serve(
          data, status: scenario == 0 ? 404 : scenario == 3 ? 302 : 200,
          mime: scenario == 1 ? "text/html" : "audio/wav",
          url: scenario == 2
            ? URL(string: "http://127.0.0.1:8789/api/public-references/bread") : nil,
          length: scenario == 4 ? 132097 : nil)
        do {
          _ = try await client().load(example: bread)
          XCTFail("Expected transport refusal")
        } catch { XCTAssertEqual(error as? ResearchPracticeExampleError, .invalidData) }
      }
    }
    func testStreamCapEmptyTruncationAndWrongHashAreRejected() async throws {
      let actual = try publicWav()
      defer { FeedbackProtocol.handler = nil }
      for data in [
        Data(), Data(actual.dropLast()), FeedbackFixture.wav(), Data(repeating: 0, count: 132097),
      ] {
        serve(data)
        do {
          _ = try await client().load(example: bread)
          XCTFail("Expected byte refusal")
        } catch { XCTAssertEqual(error as? ResearchPracticeExampleError, .invalidData) }
      }
    }
    func testGeneratedCallerMetadataNeverWidensProductionCatalogBeforeTransport() async {
      var changed = bread
      changed.isGeneratedFixture = true
      FeedbackProtocol.handler = { _ in
        XCTFail("Untrusted metadata reached transport")
        throw ResearchPracticeExampleError.unavailable
      }
      defer { FeedbackProtocol.handler = nil }
      do {
        _ = try await client().load(example: changed)
        XCTFail("Expected closed inventory refusal")
      } catch { XCTAssertEqual(error as? ResearchPracticeExampleError, .unsupportedExample) }
    }
    func testPCMValidatorRequiresBoundHashAndDeclaredSampleCount() throws {
      let data = FeedbackFixture.wav()
      let fixture = ResearchPracticeExample(
        sourceWord: "generated", author: "Generated test", licenseId: "Generated",
        licenseURL: URL(string: "https://example.invalid/license")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated data, no licensed recording", changes: "Generated",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(data), sampleCount: 3200, isGeneratedFixture: true)
      XCTAssertNoThrow(try ResearchPracticeExampleClient.validate(data, example: fixture))
      let wrong = ResearchPracticeExample(
        sourceWord: fixture.sourceWord, author: fixture.author, licenseId: fixture.licenseId,
        licenseURL: fixture.licenseURL, sourceURL: fixture.sourceURL,
        attribution: fixture.attribution, changes: fixture.changes, speakerAgeKnown: false,
        clinicalReferenceApproved: false, wavSha256: fixture.wavSha256, sampleCount: 2400,
        isGeneratedFixture: true)
      XCTAssertThrowsError(try ResearchPracticeExampleClient.validate(data, example: wrong))
      let malformed = Data(repeating: 0, count: 44)
      let badRIFF = ResearchPracticeExample(
        sourceWord: fixture.sourceWord, author: fixture.author, licenseId: fixture.licenseId,
        licenseURL: fixture.licenseURL, sourceURL: fixture.sourceURL,
        attribution: fixture.attribution, changes: fixture.changes, speakerAgeKnown: false,
        clinicalReferenceApproved: false, wavSha256: FeedbackContract.sha(malformed),
        sampleCount: 1, isGeneratedFixture: true)
      XCTAssertThrowsError(try ResearchPracticeExampleClient.validate(malformed, example: badRIFF))
    }
    func testCancellationStopsActualURLSessionTaskWithoutSensorOrServiceUse() async {
      ExampleHangingProtocol.reset()
      let loader = client(protocols: [ExampleHangingProtocol.self])
      let task = Task { try await loader.load(example: bread) }
      for _ in 0..<10000 {
        if ExampleHangingProtocol.started { break }
        await Task.yield()
      }
      XCTAssertTrue(ExampleHangingProtocol.started)
      task.cancel()
      do {
        _ = try await task.value
        XCTFail("Expected cancellation")
      } catch { XCTAssertTrue(error is CancellationError) }
      for _ in 0..<10000 {
        if ExampleHangingProtocol.stopped { break }
        await Task.yield()
      }
      XCTAssertTrue(ExampleHangingProtocol.stopped)
    }
    func testOverallDeadlineStopsHangingNativeTransfer() async {
      ExampleHangingProtocol.reset()
      do {
        _ = try await client(deadline: .milliseconds(100), protocols: [ExampleHangingProtocol.self])
          .load(example: bread)
        XCTFail("Expected deadline")
      } catch { XCTAssertEqual(error as? ResearchPracticeExampleError, .timeout) }
      XCTAssertTrue(ExampleHangingProtocol.started)
      for _ in 0..<10000 {
        if ExampleHangingProtocol.stopped { break }
        await Task.yield()
      }
      XCTAssertTrue(ExampleHangingProtocol.stopped)
    }
  }
  private final class ExampleHangingProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var didStart = false
    nonisolated(unsafe) private static var didStop = false
    static var started: Bool {
      lock.lock()
      defer { lock.unlock() }
      return didStart
    }
    static var stopped: Bool {
      lock.lock()
      defer { lock.unlock() }
      return didStop
    }
    static func reset() {
      lock.lock()
      defer { lock.unlock() }
      didStart = false
      didStop = false
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
      Self.lock.lock()
      Self.didStart = true
      Self.lock.unlock()
    }
    override func stopLoading() {
      Self.lock.lock()
      Self.didStop = true
      Self.lock.unlock()
    }
  }
#endif
