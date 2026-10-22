#if DEBUG && targetEnvironment(simulator)
  import Foundation

  @MainActor
  final class ResearchFeedbackClient: ResearchFeedbackProcessing {
    nonisolated static let origin = "http://127.0.0.1:8793"
    nonisolated static let declarationEndpoint = URL(string: origin + "/api/feedback-declaration")!
    nonisolated static let endpoint = URL(string: origin + "/api/feedback")!
    private let session: URLSession
    init(configuration: URLSessionConfiguration = .ephemeral) {
      configuration.urlCache = nil
      configuration.httpCookieStorage = nil
      configuration.httpShouldSetCookies = false
      configuration.timeoutIntervalForRequest = 100
      configuration.timeoutIntervalForResource = 105
      session = URLSession(
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
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) async throws -> RecordingFeedback {
      try await process(
        attemptId: attemptId, recording: recording, prompt: prompt,
        practiceContext: practiceContext, onEvent: { _ in })
    }
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> RecordingFeedback {
      guard practiceContext.isValid else { throw RecordingFeedbackError.unsupportedAge }
      guard ResearchFeedbackCatalog.prompts.contains(prompt) else {
        throw RecordingFeedbackError.unsupportedPrompt
      }
      try Task.checkCancellation()
      // A fresh declaration is checked for every Check; returned pins never establish trust.
      let declarationData = try await transfer(Self.declarationEndpoint)
      let declaration: FeedbackDeclaration
      do { declaration = try FeedbackDeclaration.decode(declarationData) } catch {
        if (error as? RecordingFeedbackError) == .invalidResponse { onEvent(.declarationRejected) }
        throw error
      }
      try Task.checkCancellation()
      let audio = try FeedbackPCM.read(recording.url)
      let pcm = try FeedbackPCM.measure(audio)
      let encoder = FeedbackContract.encoder()
      let id = attemptId.uuidString.lowercased()
      let body = try Self.requestBody(
        attemptId: attemptId, audio: audio, prompt: prompt, practiceContext: practiceContext)
      let result = try await transfer(
        Self.endpoint, body: body, csrf: declaration.csrfToken,
        onRequestStarted: { onEvent(.requestStarted) })
      try Task.checkCancellation()
      let binding = FeedbackContract.pins.merging([
        "attemptId": id, "requestSha256": FeedbackContract.sha(body),
        "audioSha256": FeedbackContract.sha(audio),
        "promptSha256": FeedbackContract.sha(try encoder.encode(prompt.requestPrompt)),
      ]) { _, new in new }
      return try FeedbackContract.decode(
        result, expectedBinding: binding, pcm: pcm, targetUnsupported: prompt.targetUnsupported)
    }
    /// Exact request serialization, also usable by explicitly generated contract fixtures.
    nonisolated static func requestBody(
      attemptId: UUID, audio: Data, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) throws -> Data {
      guard practiceContext.isValid else { throw RecordingFeedbackError.unsupportedAge }
      guard ResearchFeedbackCatalog.prompts.contains(prompt) else {
        throw RecordingFeedbackError.unsupportedPrompt
      }
      let body = try FeedbackContract.encoder().encode(
        Request(
          schemaVersion: 2, attemptId: attemptId.uuidString.lowercased(),
          practiceContext: practiceContext, prompt: prompt.requestPrompt,
          audioBase64: audio.base64EncodedString()))
      guard body.count <= 200_000 else { throw RecordingFeedbackError.invalidRecording }
      return body
    }
    private func transfer(
      _ endpoint: URL, body: Data? = nil, csrf: String? = nil,
      onRequestStarted: (@MainActor () -> Void)? = nil
    ) async throws
      -> Data
    {
      var request = URLRequest(url: endpoint)
      request.httpMethod = body == nil ? "GET" : "POST"
      request.timeoutInterval = body == nil ? 5 : 100
      request.httpBody = body
      request.setValue(Self.origin, forHTTPHeaderField: "Origin")
      request.setValue("application/json", forHTTPHeaderField: "Accept")
      if let body {
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(csrf, forHTTPHeaderField: "X-Consumer-CSRF")
        request.setValue(String(body.count), forHTTPHeaderField: "Content-Length")
      }
      do {
        try Task.checkCancellation()
        if body != nil { onRequestStarted?() }
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.url == endpoint, http.statusCode == 200,
          http.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?
            .trimmingCharacters(in: .whitespaces).lowercased() == "application/json"
        else { throw RecordingFeedbackError.invalidResponse }
        var data = Data()
        for try await byte in bytes {
          try Task.checkCancellation()
          guard data.count < 16_000 else { throw RecordingFeedbackError.invalidResponse }
          data.append(byte)
        }
        try Task.checkCancellation()
        return data
      } catch let error as URLError {
        if error.code == .cancelled { throw CancellationError() }
        if error.code == .timedOut { throw RecordingFeedbackError.timeout }
        throw RecordingFeedbackError.serviceUnavailable
      }
    }
    private struct Request: Encodable {
      let schemaVersion: Int
      let attemptId: String
      let practiceContext: ResearchPracticeContext
      let prompt: ResearchFeedbackPrompt.Prompt
      let audioBase64: String
    }
  }
#endif
