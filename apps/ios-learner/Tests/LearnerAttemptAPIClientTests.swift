import CadenceContracts
import Foundation
import XCTest

@testable import CadenceLearner

final class LearnerAttemptAPIClientTests: XCTestCase {
  override func tearDown() {
    URLProtocolStub.requestHandler = nil
    super.tearDown()
  }

  func testRejectsPlaintextRemoteEndpoint() {
    XCTAssertThrowsError(
      try LearnerAttemptAPIClient(baseURL: URL(string: "http://example.com")!)
    ) { error in
      XCTAssertEqual(error as? LearnerAttemptAPIError, .insecureEndpoint)
    }
  }

  func testRejectsMalformedDeviceEnrollment() {
    XCTAssertThrowsError(
      try LearnerAttemptContext(
        deviceToken: "short",
        assignmentID: "assignment-v1",
        exerciseID: "exercise-v1"
      )
    ) { error in
      XCTAssertEqual(error as? LearnerAttemptAPIError, .invalidEnrollment)
    }
  }

  func testFetchesAndValidatesCurrentSilentAssignment() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [URLProtocolStub.self]
    let session = URLSession(configuration: configuration)
    URLProtocolStub.requestHandler = { request in
      XCTAssertEqual(request.httpMethod, "GET")
      XCTAssertEqual(request.url?.path, "/api/v1/learner-assignment")
      XCTAssertEqual(
        request.value(forHTTPHeaderField: "authorization"),
        "CadenceDevice \(String(repeating: "x", count: 43))"
      )
      let data = Data(
        #"{"schemaVersion":"learner-practice-assignment-v1","assignmentId":"assignment-native-test","version":2,"exerciseRegistryVersion":"foundation-exercises-v1","exerciseDefinitionSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","exerciseId":"foundation-ball-initial-b-v1","protocolId":"bilabial-closure-v1","prompt":"ball","targetLabel":"Beginning /b/","attemptTarget":5,"retryLimit":1,"progress":{"status":"ready","acceptedRepetitions":2,"repetitionIndex":3,"retryIndex":1},"visualProcessingEnabled":false,"feedbackAvailable":false,"releasePosture":"candidate-silent-only"}"#
          .utf8
      )
      return (
        HTTPURLResponse(
          url: request.url!,
          statusCode: 200,
          httpVersion: nil,
          headerFields: ["content-type": "application/json"]
        )!,
        data
      )
    }
    let client = try LearnerAttemptAPIClient(
      baseURL: URL(string: "https://api.example.test")!,
      session: session
    )

    let assignment = try await client.fetchCurrentAssignment(
      deviceToken: String(repeating: "x", count: 43)
    )

    XCTAssertEqual(assignment?.assignmentID, "assignment-native-test")
    XCTAssertEqual(assignment?.prompt, "ball")
    XCTAssertEqual(assignment?.attemptTarget, 5)
    XCTAssertEqual(assignment?.retryLimit, 1)
    XCTAssertEqual(
      assignment?.progress,
      .ready(acceptedRepetitions: 2, repetitionIndex: 3, retryIndex: 1)
    )
  }

  func testAssignmentFetchHandlesNoContentAndRejectsUnsafeClaims() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [URLProtocolStub.self]
    let session = URLSession(configuration: configuration)
    let client = try LearnerAttemptAPIClient(
      baseURL: URL(string: "https://api.example.test")!,
      session: session
    )
    URLProtocolStub.requestHandler = { request in
      (
        HTTPURLResponse(
          url: request.url!,
          statusCode: 204,
          httpVersion: nil,
          headerFields: nil
        )!,
        Data()
      )
    }
    let noAssignment = try await client.fetchCurrentAssignment(
      deviceToken: String(repeating: "x", count: 43)
    )
    XCTAssertNil(noAssignment)

    URLProtocolStub.requestHandler = { request in
      let data = Data(
        #"{"schemaVersion":"learner-practice-assignment-v1","assignmentId":"assignment-native-test","version":2,"exerciseRegistryVersion":"foundation-exercises-v1","exerciseDefinitionSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","exerciseId":"foundation-ball-initial-b-v1","protocolId":"bilabial-closure-v1","prompt":"ball","targetLabel":"Beginning /b/","attemptTarget":5,"retryLimit":1,"progress":{"status":"ready","acceptedRepetitions":0,"repetitionIndex":1,"retryIndex":0},"visualProcessingEnabled":true,"feedbackAvailable":false,"releasePosture":"candidate-silent-only"}"#
          .utf8
      )
      return (
        HTTPURLResponse(
          url: request.url!,
          statusCode: 200,
          httpVersion: nil,
          headerFields: ["content-type": "application/json"]
        )!,
        data
      )
    }
    do {
      _ = try await client.fetchCurrentAssignment(
        deviceToken: String(repeating: "x", count: 43)
      )
      XCTFail("Expected visual processing to fail closed")
    } catch {
      XCTAssertEqual(error as? LearnerAttemptAPIError, .invalidResponse)
    }
  }

  func testUploadsWaveWithScopedDeviceHeaders() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [URLProtocolStub.self]
    let session = URLSession(configuration: configuration)
    let expectedReceipt = LearnerAttemptReceipt(
      attemptId: "attempt-native-test",
      status: .acceptedSilent,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes: []
    )
    URLProtocolStub.requestHandler = { request in
      XCTAssertEqual(request.httpMethod, "POST")
      XCTAssertEqual(request.value(forHTTPHeaderField: "content-type"), "audio/wav")
      XCTAssertEqual(
        request.value(forHTTPHeaderField: "authorization"),
        "CadenceDevice \(String(repeating: "x", count: 43))"
      )
      XCTAssertEqual(
        request.value(forHTTPHeaderField: "x-cadence-assignment-id"),
        "assignment-native-test"
      )
      XCTAssertEqual(
        request.value(forHTTPHeaderField: "x-cadence-exercise-id"),
        "foundation-ball-initial-b-v1"
      )
      XCTAssertEqual(request.value(forHTTPHeaderField: "x-cadence-repetition-index"), "2")
      XCTAssertEqual(request.value(forHTTPHeaderField: "x-cadence-retry-index"), "1")
      let data = try JSONEncoder().encode(expectedReceipt)
      return (
        HTTPURLResponse(
          url: request.url!,
          statusCode: 201,
          httpVersion: nil,
          headerFields: ["content-type": "application/json"]
        )!,
        data
      )
    }
    let file = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-client-test-\(UUID().uuidString).wav")
    try Data(repeating: 0, count: 64).write(to: file)
    defer { try? FileManager.default.removeItem(at: file) }
    let client = try LearnerAttemptAPIClient(
      baseURL: URL(string: "https://api.example.test")!,
      session: session
    )
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: "assignment-native-test",
      exerciseID: "foundation-ball-initial-b-v1",
      repetitionIndex: 2,
      retryIndex: 1
    )

    let receipt = try await client.submit(
      recording: CapturedRecording(
        url: file,
        summary: CaptureSummary(duration: 1, averagePower: -20)
      ),
      attemptID: "attempt-native-test",
      context: context
    )

    XCTAssertEqual(receipt, expectedReceipt)
  }

  func testRateLimitedAssignmentAndUploadPreserveRetryAfter() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [URLProtocolStub.self]
    let session = URLSession(configuration: configuration)
    let client = try LearnerAttemptAPIClient(
      baseURL: URL(string: "https://api.example.test")!,
      session: session
    )
    URLProtocolStub.requestHandler = { request in
      (
        HTTPURLResponse(
          url: request.url!,
          statusCode: 429,
          httpVersion: nil,
          headerFields: ["Retry-After": "83"]
        )!,
        Data()
      )
    }

    do {
      _ = try await client.fetchCurrentAssignment(
        deviceToken: String(repeating: "x", count: 43)
      )
      XCTFail("Expected assignment fetch to be rate limited")
    } catch {
      XCTAssertEqual(
        error as? LearnerAttemptAPIError,
        .rateLimited(retryAfterSeconds: 83)
      )
    }

    let file = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-rate-limit-test-\(UUID().uuidString).wav")
    try Data(repeating: 0, count: 64).write(to: file)
    defer { try? FileManager.default.removeItem(at: file) }
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: "assignment-native-test",
      exerciseID: "foundation-ball-initial-b-v1"
    )
    do {
      _ = try await client.submit(
        recording: CapturedRecording(
          url: file,
          summary: CaptureSummary(duration: 1, averagePower: -20)
        ),
        attemptID: "attempt-native-test",
        context: context
      )
      XCTFail("Expected attempt upload to be rate limited")
    } catch {
      XCTAssertEqual(
        error as? LearnerAttemptAPIError,
        .rateLimited(retryAfterSeconds: 83)
      )
      XCTAssertEqual(
        (error as? LearnerAttemptAPIError)?.errorDescription,
        "Practice is resting for a moment. Try again in about 2 minutes."
      )
    }

    for retryAfter in [nil, "invalid", "0", "3601", "99999999999999999999"]
      as [String?]
    {
      URLProtocolStub.requestHandler = { request in
        (
          HTTPURLResponse(
            url: request.url!,
            statusCode: 429,
            httpVersion: nil,
            headerFields: retryAfter.map { ["Retry-After": $0] } ?? [:]
          )!,
          Data()
        )
      }
      do {
        _ = try await client.fetchCurrentAssignment(
          deviceToken: String(repeating: "x", count: 43)
        )
        XCTFail("Expected malformed Retry-After to remain a generic rejection")
      } catch {
        XCTAssertEqual(error as? LearnerAttemptAPIError, .rejected(status: 429))
      }
    }
  }

  func testRejectsReceiptThatClaimsMediaRetention() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [URLProtocolStub.self]
    let session = URLSession(configuration: configuration)
    URLProtocolStub.requestHandler = { request in
      let data = Data(
        #"{"attemptId":"attempt-native-test","status":"accepted-silent","feedbackAvailable":false,"mediaRetained":true,"reasonCodes":[]}"#
          .utf8
      )
      return (
        HTTPURLResponse(
          url: request.url!,
          statusCode: 201,
          httpVersion: nil,
          headerFields: ["content-type": "application/json"]
        )!,
        data
      )
    }
    let file = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-client-test-\(UUID().uuidString).wav")
    try Data(repeating: 0, count: 64).write(to: file)
    defer { try? FileManager.default.removeItem(at: file) }
    let client = try LearnerAttemptAPIClient(
      baseURL: URL(string: "https://api.example.test")!,
      session: session
    )
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: "assignment-native-test",
      exerciseID: "foundation-ball-initial-b-v1"
    )

    do {
      _ = try await client.submit(
        recording: CapturedRecording(
          url: file,
          summary: CaptureSummary(duration: 1, averagePower: -20)
        ),
        attemptID: "attempt-native-test",
        context: context
      )
      XCTFail("Expected a receipt that claims retained media to fail closed")
    } catch {
      XCTAssertEqual(error as? LearnerAttemptAPIError, .invalidResponse)
    }
  }
}

private final class URLProtocolStub: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var requestHandler:
    (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let handler = Self.requestHandler else {
      client?.urlProtocol(self, didFailWithError: LearnerAttemptAPIError.invalidResponse)
      return
    }
    do {
      let (response, data) = try handler(request)
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: data)
      client?.urlProtocolDidFinishLoading(self)
    } catch {
      client?.urlProtocol(self, didFailWithError: error)
    }
  }

  override func stopLoading() {}
}
