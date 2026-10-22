#if DEBUG
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchAssessmentClientTests: XCTestCase {
    func testPromptBindsEverySelectedRepeatedOccurrence() throws {
      let entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == "n-middle-banana" })
      let prompt = try ResearchAssessmentClient.prompt(for: entry)
      let positions = entry.prompt.phones.indices.filter {
        entry.prompt.phones[$0] == "N" && $0 > 0 && $0 < entry.prompt.phones.count - 1
      }
      XCTAssertEqual(prompt.targets.map(\.phoneIndex), positions)
      XCTAssertEqual(prompt.targets.count, 2)
      XCTAssertEqual(Set(prompt.targets.map(\.id)).count, 2)
    }

    func testUnsupportedScopeAndUnavailableVariantAreRejected() throws {
      let zh = try XCTUnwrap(PracticeLibrary.entries(soundID: "zh").first)
      XCTAssertThrowsError(try ResearchAssessmentClient.prompt(for: zh))
      XCTAssertThrowsError(try ResearchAssessmentClient.prompt(for: entry, variantIndex: 999))
      XCTAssertEqual(ResearchAssessmentLabView.entries.count, 15)
    }

    func testProcessedResponseExposesOnlyUnverifiedOutcome() async throws {
      let callerId = UUID(uuidString: "00000000-0000-4000-8000-000000000123")!
      let result = try await execute(attemptId: callerId)
      XCTAssertEqual(result, .processedUnverified(milliseconds: 9000))
    }

    func testUnavailableResponseIsBoundToThisRecording() async throws {
      let result = try await execute { response in
        response["outcome"] = "unavailable"
        response["reason"] = "silence"
        response["targets"] = []
        response["model"] = NSNull()
      }
      XCTAssertEqual(result, .unavailable(reason: "silence"))
    }

    func testRejectsUnsafeEligibilityClaimsAndPromptMatch() async throws {
      for field in ["learnerFeedbackEligible", "clinicalUseEligible", "productionUseEligible"] {
        await rejected { $0[field] = true }
      }
      await rejected { $0["researchOnly"] = false }
      await rejected { $0["promptMatch"] = "verified" }
    }

    func testRejectsStaleRequestAudioPromptAndModelBindings() async throws {
      for field in ["attemptId", "requestSha256", "audioSha256", "promptSha256"] {
        await rejected { response in
          var binding = response["binding"] as! [String: Any]
          binding[field] = "incorrect"
          response["binding"] = binding
        }
      }
      await rejected {
        $0["model"] = ["id": "ages-6-12-research-mixture", "manifestSha256": "incorrect"]
      }
    }

    func testRejectsMissingTargetsAndInvalidProbabilities() async throws {
      await rejected { $0["targets"] = [] }
      await rejected { response in
        var targets = response["targets"] as! [[String: Any]]
        targets[0]["subjectiveCorpusRatingProbabilities"] = [0.1, 0.2, 0.2]
        response["targets"] = targets
      }
      await rejected { response in
        var targets = response["targets"] as! [[String: Any]]
        targets[0]["phoneIndex"] = 999
        response["targets"] = targets
      }
    }

    func testRejectsMalformedUnavailableAndFailureStatusWithPredictions() async throws {
      await rejected { response in
        response["outcome"] = "unavailable"
        response["reason"] = "silence"
      }
      await rejected { response in
        response["outcome"] = "unavailable"
        response["reason"] = "private error"
        response["targets"] = []
        response["model"] = NSNull()
      }
      do {
        _ = try await execute(status: 503)
        XCTFail("Expected status rejection")
      } catch { XCTAssertEqual(error as? ResearchAssessmentError, .invalidResponse) }
    }

    func testOversizedResponseIsRejected() async {
      await rejected { $0["padding"] = String(repeating: "x", count: 256001) }
    }

    func testAgeAndFileBoundsRejectBeforeTransport() async throws {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      try Data(repeating: 0, count: 140001).write(to: file)
      defer { try? FileManager.default.removeItem(at: file) }
      let client = ResearchAssessmentClient()
      for age in [5, 13] {
        do {
          _ = try await client.process(
            attemptId: UUID(),
            recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)),
            entry: entry, ageYears: age)
          XCTFail("Expected age rejection")
        } catch { XCTAssertEqual(error as? ResearchAssessmentError, .unsupportedAge) }
      }
      do {
        _ = try await client.process(
          attemptId: UUID(),
          recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)), entry: entry,
          ageYears: 6)
        XCTFail("Expected file rejection")
      } catch { XCTAssertEqual(error as? ResearchAssessmentError, .invalidRecording) }
    }

    #if targetEnvironment(simulator)
      private var serviceDeclaration: Data {
        Data(
          #"{"available":true,"modelAvailability":"checked_per_attempt","researchOnly":true,"learnerFeedbackEligible":false,"clinicalUseEligible":false,"productionUseEligible":false}"#
            .utf8)
      }

      func testReadinessSendsOnlyBoundedNoAudioGET() async {
        let ready = await readiness()
        XCTAssertTrue(ready)
      }

      func testReadinessAcceptsExactByteLimitAndRejectsOneByteMore() async {
        let atLimit =
          serviceDeclaration + Data(repeating: 32, count: 1024 - serviceDeclaration.count)
        let accepted = await readiness(body: atLimit)
        XCTAssertTrue(accepted)
        let rejected = await readiness(body: atLimit + Data([32]))
        XCTAssertFalse(rejected)
      }

      func testReadinessRequiresExactSixFieldDeclarationAndBooleanTypes() async throws {
        let declaration = try XCTUnwrap(
          JSONSerialization.jsonObject(with: serviceDeclaration) as? [String: Any])
        var invalid: [[String: Any]] = []
        for field in declaration.keys {
          var missing = declaration
          missing.removeValue(forKey: field)
          invalid.append(missing)
        }
        var extra = declaration
        extra["modelReady"] = true
        invalid.append(extra)
        for field in [
          "available", "researchOnly", "learnerFeedbackEligible",
          "clinicalUseEligible", "productionUseEligible",
        ] {
          for value in [0, 1, "false", NSNull()] as [Any] {
            var numeric = declaration
            numeric[field] = value
            invalid.append(numeric)
          }
          var unsafe = declaration
          unsafe[field] = !(declaration[field] as! Bool)
          invalid.append(unsafe)
        }
        for value in ["ready", "loaded", "checked_per_attempt "] {
          var wrongModelAvailability = declaration
          wrongModelAvailability["modelAvailability"] = value
          invalid.append(wrongModelAvailability)
        }
        for value in invalid {
          let ready = await readiness(body: try JSONSerialization.data(withJSONObject: value))
          XCTAssertFalse(ready)
        }
      }

      func testReadinessRejectsDuplicateMalformedAndOversizedDeclarations() async {
        let valid = String(decoding: serviceDeclaration, as: UTF8.self)
        for suffix in [#", "available":true}"#, #", "\u0061vailable":true}"#] {
          let duplicate = Data((String(valid.dropLast()) + suffix).utf8)
          let ready = await readiness(body: duplicate)
          XCTAssertFalse(ready)
        }
        for body in [
          Data(), Data("[]".utf8), Data("null".utf8),
          Data((valid + " trailing").utf8), serviceDeclaration + Data(repeating: 32, count: 1025),
        ] {
          let ready = await readiness(body: body)
          XCTAssertFalse(ready)
        }
      }

      func testReadinessRejectsWrongEndpointStatusMIMEAndTransportErrors() async {
        for url in [
          "http://localhost:8765/health", "http://127.0.0.1:8765/health?age=9",
          "http://127.0.0.1:8765/v1/assessment", "https://127.0.0.1:8765/health",
        ] {
          let ready = await readiness(url: URL(string: url)!)
          XCTAssertFalse(ready)
        }
        for status in [201, 301, 302, 400, 503] {
          let ready = await readiness(status: status)
          XCTAssertFalse(ready)
        }
        for mime in ["text/html", "text/plain", "application/problem+json", ""] {
          let ready = await readiness(contentType: mime)
          XCTAssertFalse(ready)
        }
        for error in [URLError.Code.cannotConnectToHost, .timedOut, .cancelled] {
          let ready = await readiness(error: error)
          XCTAssertFalse(ready)
        }
      }

      func testClientCopiesConfigurationAndReadinessPreservesProtocolInjection() async {
        let configuration = URLSessionConfiguration.ephemeral
        let cache = URLCache(memoryCapacity: 1024, diskCapacity: 0, diskPath: nil)
        configuration.urlCache = cache
        configuration.httpShouldSetCookies = true
        configuration.timeoutIntervalForRequest = 17
        configuration.timeoutIntervalForResource = 19
        configuration.protocolClasses = [ResearchProtocol.self]
        configuration.httpAdditionalHeaders = ["X-Recording-Context": "must-not-be-sent"]
        let body = serviceDeclaration
        ResearchProtocol.handler = { request in
          XCTAssertEqual(request.httpMethod, "GET")
          XCTAssertEqual(request.timeoutInterval, 4)
          XCTAssertNil(request.value(forHTTPHeaderField: "X-Recording-Context"))
          return (
            HTTPURLResponse(
              url: request.url!, statusCode: 200, httpVersion: nil,
              headerFields: ["Content-Type": "Application/JSON; charset=utf-8"])!, body
          )
        }
        defer { ResearchProtocol.handler = nil }
        let client = ResearchAssessmentClient(configuration: configuration)
        XCTAssertTrue(configuration.urlCache === cache)
        XCTAssertTrue(configuration.httpShouldSetCookies)
        XCTAssertEqual(configuration.timeoutIntervalForRequest, 17)
        XCTAssertEqual(configuration.timeoutIntervalForResource, 19)
        let ready = await client.checkReadiness()
        XCTAssertTrue(ready)
        XCTAssertTrue(configuration.urlCache === cache)
        XCTAssertTrue(configuration.httpShouldSetCookies)
        XCTAssertEqual(configuration.timeoutIntervalForRequest, 17)
        XCTAssertEqual(configuration.timeoutIntervalForResource, 19)
        XCTAssertEqual(configuration.protocolClasses?.count, 1)
      }

      private func readiness(
        body: Data? = nil, url: URL = URL(string: "http://127.0.0.1:8765/health")!,
        status: Int = 200, contentType: String = "application/json", error: URLError.Code? = nil
      ) async -> Bool {
        let responseBody = body ?? serviceDeclaration
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ResearchProtocol.self]
        ResearchProtocol.handler = { request in
          XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8765/health")
          XCTAssertEqual(request.httpMethod, "GET")
          XCTAssertNil(request.url?.query)
          XCTAssertNil(request.httpBody)
          XCTAssertNil(request.httpBodyStream)
          XCTAssertEqual(request.timeoutInterval, 4)
          XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
          XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
          XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
          if let error { throw URLError(error) }
          return (
            HTTPURLResponse(
              url: url, statusCode: status, httpVersion: nil,
              headerFields: ["Content-Type": contentType])!, responseBody
          )
        }
        defer { ResearchProtocol.handler = nil }
        return await ResearchAssessmentClient(configuration: configuration).checkReadiness()
      }
    #endif

    private var entry: PracticeLibraryEntry {
      PracticeLibrary.entries().first { $0.id == "b-beginning-baby" }!
    }

    private func rejected(_ mutation: @escaping @Sendable (inout [String: Any]) -> Void) async {
      do {
        _ = try await execute(mutation: mutation)
        XCTFail("Expected response rejection")
      } catch { XCTAssertEqual(error as? ResearchAssessmentError, .invalidResponse) }
    }

    private func execute(
      status: Int = 200, attemptId: UUID = UUID(),
      mutation: @escaping @Sendable (inout [String: Any]) -> Void = { _ in }
    ) async throws -> ResearchAssessmentOutcome {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      let audio = Data([82, 73, 70, 70])
      try audio.write(to: file)
      defer {
        try? FileManager.default.removeItem(at: file)
        ResearchProtocol.handler = nil
      }
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [ResearchProtocol.self]
      ResearchProtocol.handler = { request in
        XCTAssertEqual(request.url, ResearchAssessmentClient.endpoint)
        XCTAssertEqual(request.httpMethod, "POST")
        // The HTTP request must outlast the Mac worker's bounded processing budget.
        XCTAssertGreaterThan(request.timeoutInterval, 90)
        XCTAssertEqual(request.timeoutInterval, 100)
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
        let id = req["attemptId"] as! String
        XCTAssertEqual(id, attemptId.uuidString.lowercased())
        let prompt = req["prompt"] as! [String: Any]
        let promptData = try JSONSerialization.data(
          withJSONObject: prompt, options: [.sortedKeys, .withoutEscapingSlashes])
        var response: [String: Any] = [
          "schemaVersion": 1, "researchOnly": true, "learnerFeedbackEligible": false,
          "clinicalUseEligible": false, "productionUseEligible": false, "promptMatch": "unverified",
          "outcome": "processed", "reason": NSNull(),
          "binding": [
            "attemptId": id, "requestSha256": ResearchAssessmentClient.sha256(body),
            "audioSha256": ResearchAssessmentClient.sha256(audio),
            "promptSha256": ResearchAssessmentClient.sha256(promptData),
          ],
          "timingMilliseconds": ["total": 9000, "inference": 8999],
          "model": [
            "id": "ages-6-12-research-mixture", "manifestSha256": ResearchAssessmentClient.manifest,
          ],
          "targets": (prompt["targets"] as! [[String: Any]]).map { target in
            var t = target
            t["subjectiveCorpusRatingProbabilities"] = [0.1, 0.2, 0.7]
            return t
          },
        ]
        mutation(&response)
        return (
          HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!,
          try JSONSerialization.data(withJSONObject: response)
        )
      }
      return try await ResearchAssessmentClient(configuration: configuration).process(
        attemptId: attemptId,
        recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)), entry: entry,
        ageYears: 6)
    }
  }

  private final class ResearchProtocol: URLProtocol, @unchecked Sendable {
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
