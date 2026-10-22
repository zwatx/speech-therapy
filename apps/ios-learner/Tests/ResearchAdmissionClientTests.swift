#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchAdmissionClientTests: XCTestCase {
    func testProcessedAdmissionExposesNoPronunciationFinding() async throws {
      let outcome = try await execute()
      XCTAssertEqual(outcome, .admissionProcessed(milliseconds: 1200))
    }

    func testEveryUnavailableReasonRetainsBoundDenominator() async throws {
      for reason in ResearchAdmissionClient.unavailableReasons {
        let result = try await execute { response in
          response["status"] = "unavailable"
          response["reason"] = reason
          response["speechAdmissionPassed"] = false
          response["wordAdmissionPassed"] = false
          response["researchProcessed"] = false
        }
        XCTAssertEqual(result, .unavailable(reason: reason))
      }
    }

    func testRejectsEveryChangedRequestSourceModelPolicyBinding() async {
      for key in Set(ResearchAdmissionClient.pins.keys).union([
        "attemptId", "requestSha256", "audioSha256", "promptSha256",
      ]) {
        await rejected { response in
          var binding = response["binding"] as! [String: Any]
          binding[key] = "changed"
          response["binding"] = binding
        }
      }
    }

    func testRejectsAnyDisabledClaimUpgradeOrMissingClaim() async {
      for key in ResearchAdmissionClient.claimKeys {
        await rejected { response in
          var claims = response["claimLimits"] as! [String: Bool]
          claims[key] = true
          response["claimLimits"] = claims
        }
        await rejected { response in
          var claims = response["claimLimits"] as! [String: Bool]
          claims.removeValue(forKey: key)
          response["claimLimits"] = claims
        }
      }
      await rejected { $0["researchOnly"] = false }
      await rejected { $0["bridgePromptMatch"] = "verified" }
    }

    func testRejectsEvidenceFieldsAndMalformedAdmissionStates() async {
      for key in ["transcript", "probabilities", "research", "recognition"] {
        await rejected { $0[key] = "private" }
      }
      await rejected { response in
        var binding = response["binding"] as! [String: Any]
        binding["transcript"] = "private"
        response["binding"] = binding
      }
      for key in ["speechAdmissionPassed", "wordAdmissionPassed", "researchProcessed"] {
        await rejected { $0[key] = false }
      }
      await rejected {
        $0["status"] = "unavailable"
        $0["reason"] = "silence"
      }
      await rejected { $0["reason"] = "silence" }
      await rejected { $0["elapsedMilliseconds"] = -1 }
      await rejected { $0["elapsedMilliseconds"] = 90_001 }
      await rejected { $0["schemaVersion"] = 2 }
    }

    func testRejectsOversizeStatusAndResponseDestination() async {
      await rejected { $0["padding"] = String(repeating: "x", count: 16_001) }
      for status in [302, 400, 503] {
        do {
          _ = try await execute(status: status)
          XCTFail("Expected refusal")
        } catch { XCTAssertEqual(error as? ResearchAssessmentError, .invalidResponse) }
      }
      do {
        _ = try await execute(responseURL: URL(string: "http://127.0.0.1:8765/v1/assessment")!)
        XCTFail("Expected destination refusal")
      } catch { XCTAssertEqual(error as? ResearchAssessmentError, .invalidResponse) }
    }

    func testInvalidFileAndAgeRefuseBeforeTransport() async throws {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      try Data(repeating: 0, count: 132_097).write(to: file)
      defer { try? FileManager.default.removeItem(at: file) }
      for age in [5, 9, 13] {
        do {
          _ = try await ResearchAdmissionClient().process(
            attemptId: UUID(),
            recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)),
            entry: entry, ageYears: age)
          XCTFail("Expected preflight refusal")
        } catch {
          XCTAssertEqual(
            error as? ResearchAssessmentError, age == 9 ? .invalidRecording : .unsupportedAge)
        }
      }
    }

    private var entry: PracticeLibraryEntry {
      PracticeLibrary.entries().first { $0.id == "n-middle-banana" }!
    }
    private func rejected(_ mutation: @escaping @Sendable (inout [String: Any]) -> Void) async {
      do {
        _ = try await execute(mutation: mutation)
        XCTFail("Expected response refusal")
      } catch { XCTAssertEqual(error as? ResearchAssessmentError, .invalidResponse) }
    }
    private func execute(
      status: Int = 200, responseURL: URL? = nil,
      mutation: @escaping @Sendable (inout [String: Any]) -> Void = { _ in }
    ) async throws -> ResearchAssessmentOutcome {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      let audio = Data("invented unit transport bytes".utf8)
      try audio.write(to: file)
      defer {
        try? FileManager.default.removeItem(at: file)
        AdmissionProtocol.handler = nil
      }
      let id = UUID()
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [AdmissionProtocol.self]
      AdmissionProtocol.handler = { request in
        XCTAssertEqual(request.url, ResearchAdmissionClient.endpoint)
        XCTAssertEqual(request.httpMethod, "POST")
        let body: Data
        if let data = request.httpBody {
          body = data
        } else {
          let stream = try XCTUnwrap(request.httpBodyStream)
          stream.open()
          defer { stream.close() }
          var data = Data()
          var buffer = [UInt8](repeating: 0, count: 4096)
          while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(contentsOf: buffer.prefix(count))
          }
          body = data
        }
        let req = try JSONSerialization.jsonObject(with: body) as! [String: Any]
        XCTAssertEqual(req["attemptId"] as? String, id.uuidString.lowercased())
        XCTAssertEqual(Data(base64Encoded: req["audioBase64"] as! String), audio)
        let prompt = try JSONSerialization.data(
          withJSONObject: req["prompt"]!, options: [.sortedKeys, .withoutEscapingSlashes])
        var binding: [String: Any] = ResearchAdmissionClient.pins
        binding.merge([
          "attemptId": id.uuidString.lowercased(),
          "requestSha256": ResearchAssessmentClient.sha256(body),
          "audioSha256": ResearchAssessmentClient.sha256(audio),
          "promptSha256": ResearchAssessmentClient.sha256(prompt),
        ]) { _, new in new }
        var response: [String: Any] = [
          "schemaVersion": 1, "researchOnly": true, "status": "processed", "reason": NSNull(),
          "speechAdmissionPassed": true, "wordAdmissionPassed": true, "researchProcessed": true,
          "bridgePromptMatch": "unverified", "elapsedMilliseconds": 1200, "binding": binding,
          "claimLimits": Dictionary(
            uniqueKeysWithValues: ResearchAdmissionClient.claimKeys.map { ($0, false) }),
        ]
        mutation(&response)
        return (
          HTTPURLResponse(
            url: responseURL ?? request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!,
          try JSONSerialization.data(withJSONObject: response)
        )
      }
      return try await ResearchAdmissionClient(configuration: configuration).process(
        attemptId: id, recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)),
        entry: entry, ageYears: 9)
    }
  }

  private final class AdmissionProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler:
      (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
      do {
        let (response, data) = try Self.handler!(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
      } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
  }
#endif
