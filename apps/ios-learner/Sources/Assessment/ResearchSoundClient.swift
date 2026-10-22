#if DEBUG && targetEnvironment(simulator)
  import Foundation

  @MainActor
  protocol ResearchSoundProcessing {
    func declaration() async throws -> ResearchSoundDeclaration
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation
    func cancel(_ prepared: ResearchSoundPrepared) async throws
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
  }

  /// Local-only bounded transport. Construction itself never starts a request.
  @MainActor
  final class ResearchSoundClient: ResearchSoundProcessing {
    private let session: URLSession
    private let service: ResearchFeedbackService
    private let redirects = NoRedirects()
    init(
      configuration: URLSessionConfiguration? = nil,
      service: ResearchFeedbackService = .currentUnified
    ) {
      self.service = service
      let config = configuration ?? .ephemeral
      config.urlCache = nil
      config.requestCachePolicy = .reloadIgnoringLocalCacheData
      config.httpCookieStorage = nil
      config.httpShouldSetCookies = false
      config.timeoutIntervalForRequest = 65
      config.timeoutIntervalForResource = 70
      session = URLSession(configuration: config, delegate: redirects, delegateQueue: nil)
    }
    func declaration() async throws -> ResearchSoundDeclaration {
      try ResearchSoundContract.declaration(
        await transfer(path: "/api/sound-declaration"), service: service)
    }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      try service.requireConfigured()
      try ResearchSoundContract.need(declaration.service == service)
      try Task.checkCancellation()
      let bytes = try ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url))
      try Task.checkCancellation()
      let prepared = try ResearchSoundContract.prepare(
        audio: bytes, declaration: declaration, context: context, service: service)
      try Task.checkCancellation()
      return prepared
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      try ResearchSoundContract.validatePrepared(prepared, service: service)
      try Task.checkCancellation()
      let bytes = try await transfer(
        path: "/api/sound-observation", body: prepared.body, csrf: prepared.declaration.csrfToken)
      try Task.checkCancellation()
      return try ResearchSoundContract.observation(
        bytes, expected: prepared.expected, service: service)
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws {
      try ResearchSoundContract.validatePrepared(prepared, service: service)
      let body = ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "serverNonce": .string(prepared.declaration.serverNonce),
        "attemptId": .string(prepared.context.attemptId),
        "requestSha256": .string(prepared.requestSha256), "ownership": prepared.ownership,
      ])
      let response = try ResearchSoundJSON.parse(
        await transfer(
          path: "/api/sound-cancel", body: body.canonical(), csrf: prepared.declaration.csrfToken))
      let fields = try response.fields([
        "schemaVersion", "serverNonce", "attemptId", "requestSha256", "cancelAccepted",
      ])
      try ResearchSoundContract.need(
        fields["schemaVersion"] == .integer(1)
          && fields["serverNonce"] == .string(prepared.declaration.serverNonce)
          && fields["attemptId"] == .string(prepared.context.attemptId)
          && fields["requestSha256"] == .string(prepared.requestSha256))
      guard case .bool = fields["cancelAccepted"] else {
        throw RecordingFeedbackError.invalidResponse
      }
    }
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {
      try service.requireConfigured()
      try ResearchSoundContract.need(declaration.service == service)
      try ResearchSoundContract.need(
        ResearchSoundContract.opaque(sessionId) && (1...2_147_483_647).contains(generation))
      let body = ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "serverNonce": .string(declaration.serverNonce),
        "sessionId": .string(sessionId), "generation": .integer(generation),
      ])
      let response = try ResearchSoundJSON.parse(
        await transfer(
          path: "/api/sound-reset", body: body.canonical(), csrf: declaration.csrfToken))
      let fields = try response.fields([
        "schemaVersion", "resetAccepted", "serverNonce", "sessionId", "generation",
      ])
      try ResearchSoundContract.need(
        fields["schemaVersion"] == .integer(1) && fields["resetAccepted"] == .bool(true)
          && fields["serverNonce"] == .string(declaration.serverNonce)
          && fields["sessionId"] == .string(sessionId)
          && fields["generation"] == .integer(generation))
    }
    private func transfer(path: String, body: Data? = nil, csrf: String? = nil) async throws -> Data
    {
      try service.requireConfigured()
      try Task.checkCancellation()
      let allowed: Set<String> = [
        "/api/sound-declaration", "/api/sound-observation", "/api/sound-cancel", "/api/sound-reset",
      ]
      guard allowed.contains(path), let endpoint = URL(string: service.origin + path),
        body == nil || body!.count <= 200000
      else { throw RecordingFeedbackError.invalidResponse }
      var request = URLRequest(
        url: endpoint, cachePolicy: .reloadIgnoringLocalCacheData,
        timeoutInterval: path == "/api/sound-observation" ? 65 : 5)
      request.httpMethod = body == nil ? "GET" : "POST"
      request.httpShouldHandleCookies = false
      request.httpBody = body
      request.setValue(service.origin, forHTTPHeaderField: "Origin")
      request.setValue("application/json", forHTTPHeaderField: "Accept")
      if let body {
        guard let csrf, FeedbackContract.isHash(csrf) else {
          throw RecordingFeedbackError.invalidResponse
        }
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(csrf, forHTTPHeaderField: "X-Consumer-CSRF")
        request.setValue(String(body.count), forHTTPHeaderField: "Content-Length")
      }
      do {
        let (stream, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.url == endpoint, http.statusCode == 200,
          http.value(forHTTPHeaderField: "Content-Type")?.lowercased().split(separator: ";").first?
            .trimmingCharacters(in: .whitespaces) == "application/json"
        else { throw RecordingFeedbackError.invalidResponse }
        var result = Data()
        for try await byte in stream {
          try Task.checkCancellation()
          guard result.count < 12000 else { throw RecordingFeedbackError.invalidResponse }
          result.append(byte)
        }
        try Task.checkCancellation()
        return result
      } catch let error as URLError {
        if error.code == .cancelled { throw CancellationError() }
        throw error.code == .timedOut ? RecordingFeedbackError.timeout : .serviceUnavailable
      }
    }
    private final class NoRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
      func urlSession(
        _ session: URLSession, task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
      ) { completionHandler(nil) }
    }
  }
#endif
