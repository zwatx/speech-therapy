#if DEBUG
  import CryptoKit
  import Foundation

  enum ResearchAssessmentOutcome: Equatable, Sendable {
    case processedResearch(ResearchAssessmentResult)
    // Legacy admission/test stubs carry no validated research payload.
    case processedUnverified(milliseconds: Double)
    case admissionProcessed(milliseconds: Double)
    case unavailable(reason: String)
  }

  /// Debug research distribution, never a learner sound finding. No audio is retained.
  struct ResearchAssessmentResult: Equatable, Sendable {
    struct Context: Equatable, Sendable {
      let operationID: UUID
      let entryID: String
      let ageYears: Int
      let requestSHA256: String
      let audioSHA256: String
      let promptSHA256: String
    }
    let context: Context
    let model: ResearchAssessmentClient.Model
    let targets: [ResearchAssessmentClient.Prediction]
    let timingMilliseconds: ResearchAssessmentClient.Timing

    func isBound(to expected: Context, prompt: ResearchAssessmentClient.Prompt) -> Bool {
      guard context == expected, model.id == "ages-6-12-research-mixture",
        model.manifestSha256 == ResearchAssessmentClient.manifest,
        timingMilliseconds.total.isFinite, timingMilliseconds.total >= 0,
        timingMilliseconds.inference.isFinite, timingMilliseconds.inference >= 0,
        timingMilliseconds.inference <= timingMilliseconds.total,
        targets.count == prompt.targets.count else { return false }
      return zip(targets, prompt.targets).allSatisfy { actual, target in
          guard actual.id == target.id && actual.wordIndex == target.wordIndex
            && actual.phoneIndex == target.phoneIndex && actual.targetPhone == target.targetPhone
            && actual.subjectiveCorpusRatingProbabilities.count == 3
            else { return false }
          return actual.subjectiveCorpusRatingProbabilities.allSatisfy { $0.isFinite && (0...1).contains($0) }
            && abs(actual.subjectiveCorpusRatingProbabilities.reduce(0, +) - 1) < 0.00001
      }
    }
  }

  @MainActor
  protocol ResearchAssessmentProcessing {
    func process(
      attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
    )
      async throws
      -> ResearchAssessmentOutcome
  }

  #if targetEnvironment(simulator)
    @MainActor
    protocol ResearchAssessmentReadinessChecking: ResearchAssessmentProcessing {
      func checkReadiness() async -> Bool
    }
  #endif

  enum ResearchAssessmentError: Error, Equatable {
    case unsupportedAge
    case unsupportedPrompt
    case invalidRecording
    case invalidResponse
    case serviceUnavailable
    case timeout
  }

  /// A Debug-only, loopback-only client. No model result is a learner finding.
  @MainActor
  final class ResearchAssessmentClient: ResearchAssessmentProcessing {
    nonisolated static let endpoint = URL(string: "http://127.0.0.1:8765/v1/assessment")!
    nonisolated static let manifest =
      "bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf"
    private let session: URLSession

    init(configuration: URLSessionConfiguration = .ephemeral) {
      let configuration = configuration.copy() as! URLSessionConfiguration
      configuration.urlCache = nil
      configuration.httpCookieStorage = nil
      configuration.httpShouldSetCookies = false
      // Allow the Mac worker's bounded 90-second extraction plus response/cleanup time.
      configuration.timeoutIntervalForRequest = 100
      configuration.timeoutIntervalForResource = 105
      self.session = URLSession(
        configuration: configuration, delegate: LoopbackOnlyDelegate(), delegateQueue: nil)
    }

    private final class LoopbackOnlyDelegate: NSObject, URLSessionTaskDelegate {
      func urlSession(
        _ session: URLSession, task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
      ) {
        completionHandler(nil)
      }
    }

    func process(
      attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
    )
      async throws
      -> ResearchAssessmentOutcome
    {
      guard (6...12).contains(ageYears) else { throw ResearchAssessmentError.unsupportedAge }
      let prompt = try Self.prompt(for: entry)
      guard recording.url.isFileURL,
        let size = try FileManager.default.attributesOfItem(atPath: recording.url.path)[.size]
          as? Int,
        size > 0, size <= 140_000
      else { throw ResearchAssessmentError.invalidRecording }
      try Task.checkCancellation()
      let audio = try Data(contentsOf: recording.url)
      guard !audio.isEmpty, audio.count <= 140_000 else {
        throw ResearchAssessmentError.invalidRecording
      }
      let id = attemptId.uuidString.lowercased()
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
      let body = try encoder.encode(
        Request(
          schemaVersion: 1, attemptId: id, ageYears: ageYears, prompt: prompt,
          audioBase64: audio.base64EncodedString()))
      var request = URLRequest(url: Self.endpoint, timeoutInterval: 100)
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
          guard received.count < 256_000 else { throw ResearchAssessmentError.invalidResponse }
          received.append(byte)
        }
        data = received
      } catch let error as URLError {
        if error.code == .cancelled { throw CancellationError() }
        if error.code == .timedOut { throw ResearchAssessmentError.timeout }
        throw ResearchAssessmentError.serviceUnavailable
      }
      try Task.checkCancellation()
      guard let http = response as? HTTPURLResponse,
        http.url == Self.endpoint,
        [200, 400, 413, 429, 503, 504].contains(http.statusCode),
        http.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?
          .trimmingCharacters(in: .whitespaces).lowercased() == "application/json",
        data.count <= 256_000,
        let result = try? JSONDecoder().decode(Response.self, from: data),
        result.schemaVersion == 1, result.researchOnly,
        !result.learnerFeedbackEligible, !result.clinicalUseEligible,
        !result.productionUseEligible, result.promptMatch == "unverified",
        result.binding.attemptId == id,
        result.binding.requestSha256 == Self.sha256(body),
        result.binding.audioSha256 == Self.sha256(audio),
        result.binding.promptSha256 == Self.sha256(try encoder.encode(prompt)),
        result.timingMilliseconds.total.isFinite, result.timingMilliseconds.total >= 0,
        result.timingMilliseconds.inference.isFinite, result.timingMilliseconds.inference >= 0,
        result.timingMilliseconds.inference <= result.timingMilliseconds.total
      else { throw ResearchAssessmentError.invalidResponse }
      if result.outcome == "unavailable" {
        guard let reason = result.reason, Self.unavailableReasons.contains(reason),
          result.targets.isEmpty, result.model == nil
        else { throw ResearchAssessmentError.invalidResponse }
        return .unavailable(reason: reason)
      }
      guard http.statusCode == 200, result.outcome == "processed", result.reason == nil,
        result.model?.id == "ages-6-12-research-mixture",
        result.model?.manifestSha256 == Self.manifest,
        result.targets.count == prompt.targets.count
      else { throw ResearchAssessmentError.invalidResponse }
      for (actual, expected) in zip(result.targets, prompt.targets) {
        guard actual.id == expected.id, actual.wordIndex == expected.wordIndex,
          actual.phoneIndex == expected.phoneIndex, actual.targetPhone == expected.targetPhone,
          actual.subjectiveCorpusRatingProbabilities.count == 3,
          actual.subjectiveCorpusRatingProbabilities.allSatisfy({
            $0.isFinite && (0...1).contains($0)
          }),
          abs(actual.subjectiveCorpusRatingProbabilities.reduce(0, +) - 1) < 0.00001
        else { throw ResearchAssessmentError.invalidResponse }
      }
      return .processedUnverified(milliseconds: result.timingMilliseconds.total)
    }

    static func prompt(for entry: PracticeLibraryEntry, variantIndex: Int = 0) throws -> Prompt {
      guard entry.targetPhone != "ZH", !entry.targetPhone.isEmpty,
        entry.prompt.pronunciationVariants.indices.contains(variantIndex)
      else { throw ResearchAssessmentError.unsupportedPrompt }
      let phones = entry.prompt.pronunciationVariants[variantIndex]
      let indexes = phones.indices.filter { index in
        guard phones[index] == entry.targetPhone else { return false }
        switch entry.position {
        case .beginning: return index == 0
        case .middle: return index > 0 && index < phones.count - 1
        case .end: return index == phones.count - 1
        }
      }
      guard !indexes.isEmpty else { throw ResearchAssessmentError.unsupportedPrompt }
      return Prompt(
        schemaVersion: 2, language: "en", transcript: entry.prompt.word,
        words: [Word(text: entry.prompt.word, phones: phones)],
        targets: indexes.map {
          Target(
            id: "\(entry.id)-\($0)", wordIndex: 0, phoneIndex: $0, targetPhone: entry.targetPhone)
        })
    }

    nonisolated static func sha256(_ data: Data) -> String {
      SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    nonisolated static let unavailableReasons: Set<String> = [
      "invalid_request", "age_out_of_range", "unsupported_target", "invalid_audio",
      "audio_too_long",
      "silence", "clipping", "model_unavailable", "inference_failed", "timeout", "busy",
    ]

    struct Prompt: Codable, Equatable {
      let schemaVersion: Int
      let language: String
      let transcript: String
      let words: [Word]
      let targets: [Target]
    }
    struct Word: Codable, Equatable {
      let text: String
      let phones: [String]
    }
    struct Target: Codable, Equatable {
      let id: String
      let wordIndex: Int
      let phoneIndex: Int
      let targetPhone: String
    }
    private struct Request: Encodable {
      let schemaVersion: Int
      let attemptId: String
      let ageYears: Int
      let prompt: Prompt
      let audioBase64: String
    }
    private struct Response: Decodable {
      let schemaVersion: Int
      let researchOnly: Bool
      let learnerFeedbackEligible: Bool
      let clinicalUseEligible: Bool
      let productionUseEligible: Bool
      let promptMatch: String
      let binding: Binding
      let timingMilliseconds: Timing
      let outcome: String
      let reason: String?
      let targets: [Prediction]
      let model: Model?
    }
    private struct Binding: Decodable {
      let attemptId: String
      let requestSha256: String
      let audioSha256: String
      let promptSha256: String
    }
    private struct Timing: Decodable {
      let total: Double
      let inference: Double
    }
    private struct Prediction: Decodable {
      let id: String
      let wordIndex: Int
      let phoneIndex: Int
      let targetPhone: String
      let subjectiveCorpusRatingProbabilities: [Double]
    }
    private struct Model: Decodable {
      let id: String
      let manifestSha256: String
    }
  }

  #if targetEnvironment(simulator)
    extension ResearchAssessmentClient: ResearchAssessmentReadinessChecking {
      /// Confirms only the local service declaration; model availability is checked per take.
      func checkReadiness() async -> Bool {
        let endpoint = URL(string: "http://127.0.0.1:8765/health")!
        let configuration = session.configuration.copy() as! URLSessionConfiguration
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        configuration.httpShouldSetCookies = false
        configuration.httpAdditionalHeaders = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 4
        configuration.timeoutIntervalForResource = 5
        let readinessSession = URLSession(
          configuration: configuration, delegate: LoopbackOnlyDelegate(), delegateQueue: nil)
        defer { readinessSession.invalidateAndCancel() }
        var request = URLRequest(
          url: endpoint, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 4)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        do {
          let (bytes, response) = try await readinessSession.bytes(for: request)
          guard let http = response as? HTTPURLResponse, http.url == endpoint,
            http.statusCode == 200,
            http.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?
              .trimmingCharacters(in: .whitespaces).lowercased() == "application/json"
          else { return false }
          var data = Data()
          for try await byte in bytes {
            guard data.count < 1024 else { return false }
            data.append(byte)
          }
          let fields = try FeedbackJSON.parse(data).object([
            "available", "modelAvailability", "researchOnly", "learnerFeedbackEligible",
            "clinicalUseEligible", "productionUseEligible",
          ])
          return try fields["available"]!.boolean()
            && fields["modelAvailability"]!.string() == "checked_per_attempt"
            && fields["researchOnly"]!.boolean()
            && !fields["learnerFeedbackEligible"]!.boolean()
            && !fields["clinicalUseEligible"]!.boolean()
            && !fields["productionUseEligible"]!.boolean()
        } catch { return false }
      }
    }
  #endif
#endif
