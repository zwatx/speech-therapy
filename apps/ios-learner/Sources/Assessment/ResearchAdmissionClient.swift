#if DEBUG && targetEnvironment(simulator)
  import Foundation

  /// Explicit simulator experiment. This projection contains no recognized text or predictions.
  @MainActor
  final class ResearchAdmissionClient: ResearchAssessmentProcessing {
    nonisolated static let endpoint = URL(string: "http://127.0.0.1:8778/v1/admission")!
    // Exact reviewed source/model/policy pins are generated after service verification.
    nonisolated static let pins: [String: String] = [
      "modelManifestSha256": "8a8054e4c434e9106e9bb625d27c3219089c7a6b643504ad893a531c3b4e6c37",
      "policySha256": "33b4a2598c1700d2d88ded58fbe369bed4bca71d63fbff6a1beb191cc6e9cf49",
      "admissionSourceSha256": "53468b070bbde40ca29f86caa67877e904175a67fdfd8ae2258cb218b5461b24",
      "bridgeSourceSha256": "e1a539570244c2f1ee28b29b98954e656561aa6605625458c0ebe966cd725b88",
      "serviceSourceSha256": "e950bf69352ba8d0995154b4ab7124a91fadb81ed81aaae5d1b2375a3809d349",
      "supervisorSourceSha256": "03f0f1ca5b7f7ef2cead5b683f644a25293c9fc2e260d3db00827b5e25e03bda",
    ]
    nonisolated static let claimKeys: Set<String> = [
      "speechPresenceVerified", "requestedWordVerified", "promptMatchingValidated",
      "intendedChildAccuracyEstablished", "qualifiedApprovalEstablished",
      "learnerFeedbackEligible", "clinicalUseEligible", "productionUseEligible",
      "authenticProvenanceEstablished",
    ]
    nonisolated static let unavailableReasons: Set<String> = [
      "invalid_request", "invalid_audio", "silence", "clipping", "unsupported_target",
      "invalid_prompt", "speech_not_detected", "worker_timeout", "worker_crash",
      "model_unavailable", "recognition_failed", "invalid_evidence", "recognition_incomplete",
      "recognition_uncertain", "single_word_required", "requested_word_not_matched",
      "recognition_binding_failed", "research_binding_failed", "research_unavailable",
      "assessment_failed", "timeout", "busy", "cleanup_unconfirmed", "source_binding_failed",
    ]
    private let session: URLSession

    init(configuration: URLSessionConfiguration = .ephemeral) {
      configuration.urlCache = nil
      configuration.httpCookieStorage = nil
      configuration.httpShouldSetCookies = false
      configuration.timeoutIntervalForRequest = 100
      configuration.timeoutIntervalForResource = 105
      self.session = URLSession(
        configuration: configuration, delegate: NoRedirects(), delegateQueue: nil)
    }

    private final class NoRedirects: NSObject, URLSessionTaskDelegate {
      func urlSession(
        _ session: URLSession, task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
      ) { completionHandler(nil) }
    }

    func process(
      attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
    ) async throws -> ResearchAssessmentOutcome {
      guard (6...12).contains(ageYears) else { throw ResearchAssessmentError.unsupportedAge }
      let prompt = try ResearchAssessmentClient.prompt(for: entry)
      guard recording.url.isFileURL,
        let size = try FileManager.default.attributesOfItem(atPath: recording.url.path)[.size]
          as? Int,
        size > 0, size <= 132_096
      else { throw ResearchAssessmentError.invalidRecording }
      try Task.checkCancellation()
      let audio = try Data(contentsOf: recording.url)
      guard !audio.isEmpty, audio.count <= 132_096 else {
        throw ResearchAssessmentError.invalidRecording
      }
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
      let id = attemptId.uuidString.lowercased()
      let body = try encoder.encode(
        Request(
          schemaVersion: 1, attemptId: id, ageYears: ageYears, prompt: prompt,
          audioBase64: audio.base64EncodedString()))
      guard body.count <= 200_000 else { throw ResearchAssessmentError.invalidRecording }
      var request = URLRequest(url: Self.endpoint)
      request.httpMethod = "POST"
      request.httpBody = body
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.setValue("application/json", forHTTPHeaderField: "Accept")
      let data: Data
      let response: URLResponse
      do {
        let (bytes, receivedResponse) = try await session.bytes(for: request)
        response = receivedResponse
        var received = Data()
        for try await byte in bytes {
          guard received.count < 16_000 else { throw ResearchAssessmentError.invalidResponse }
          received.append(byte)
        }
        data = received
      } catch let error as URLError {
        if error.code == .cancelled { throw CancellationError() }
        if error.code == .timedOut { throw ResearchAssessmentError.timeout }
        throw ResearchAssessmentError.serviceUnavailable
      }
      try Task.checkCancellation()
      guard let http = response as? HTTPURLResponse, http.url == Self.endpoint,
        http.statusCode == 200,
        http.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?
          .trimmingCharacters(in: .whitespaces).lowercased() == "application/json",
        Self.hasExactPublicShape(data),
        let result = try? JSONDecoder().decode(Response.self, from: data),
        result.schemaVersion == 1, result.researchOnly, result.bridgePromptMatch == "unverified",
        Set(result.claimLimits.keys) == Self.claimKeys,
        result.claimLimits.values.allSatisfy({ !$0 }),
        result.binding.attemptId == id,
        result.binding.requestSha256 == ResearchAssessmentClient.sha256(body),
        result.binding.audioSha256 == ResearchAssessmentClient.sha256(audio),
        result.binding.promptSha256 == ResearchAssessmentClient.sha256(try encoder.encode(prompt)),
        result.binding.pins == Self.pins,
        result.elapsedMilliseconds.isFinite, (0...90_000).contains(result.elapsedMilliseconds)
      else { throw ResearchAssessmentError.invalidResponse }
      if result.status == "unavailable" {
        guard let reason = result.reason, Self.unavailableReasons.contains(reason),
          !result.speechAdmissionPassed, !result.wordAdmissionPassed, !result.researchProcessed
        else { throw ResearchAssessmentError.invalidResponse }
        return .unavailable(reason: reason)
      }
      guard result.status == "processed", result.reason == nil,
        result.speechAdmissionPassed, result.wordAdmissionPassed, result.researchProcessed
      else { throw ResearchAssessmentError.invalidResponse }
      return .admissionProcessed(milliseconds: result.elapsedMilliseconds)
    }

    /// Codable ignores unknown keys; explicitly reject evidence-bearing or unexpected fields.
    private nonisolated static func hasExactPublicShape(_ data: Data) -> Bool {
      guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        Set(root.keys)
          == Set([
            "schemaVersion", "researchOnly", "status", "reason", "speechAdmissionPassed",
            "wordAdmissionPassed", "researchProcessed", "bridgePromptMatch", "claimLimits",
            "elapsedMilliseconds", "binding",
          ]),
        let binding = root["binding"] as? [String: Any],
        Set(binding.keys)
          == Set(pins.keys).union([
            "attemptId", "requestSha256", "audioSha256", "promptSha256",
          ]),
        let claims = root["claimLimits"] as? [String: Any], Set(claims.keys) == claimKeys
      else { return false }
      return true
    }

    private struct Request: Encodable {
      let schemaVersion: Int
      let attemptId: String
      let ageYears: Int
      let prompt: ResearchAssessmentClient.Prompt
      let audioBase64: String
    }
    private struct Response: Decodable {
      let schemaVersion: Int
      let researchOnly: Bool
      let status: String
      let reason: String?
      let speechAdmissionPassed: Bool
      let wordAdmissionPassed: Bool
      let researchProcessed: Bool
      let bridgePromptMatch: String
      let claimLimits: [String: Bool]
      let elapsedMilliseconds: Double
      let binding: Binding
    }
    private struct Binding: Decodable {
      let attemptId: String
      let requestSha256: String
      let audioSha256: String
      let promptSha256: String
      let modelManifestSha256: String
      let policySha256: String
      let admissionSourceSha256: String
      let bridgeSourceSha256: String
      let serviceSourceSha256: String
      let supervisorSourceSha256: String
      var pins: [String: String] {
        [
          "modelManifestSha256": modelManifestSha256, "policySha256": policySha256,
          "admissionSourceSha256": admissionSourceSha256, "bridgeSourceSha256": bridgeSourceSha256,
          "serviceSourceSha256": serviceSourceSha256,
          "supervisorSourceSha256": supervisorSourceSha256,
        ]
      }
    }
  }
#endif
