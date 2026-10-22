#if DEBUG && targetEnvironment(simulator)
  import Darwin
  import Foundation

  enum ResearchPracticeExampleError: Error, Equatable, Sendable {
    case unsupportedExample, unavailable, timeout, invalidData, playbackFailed, storageFailed,
      cleanupFailed
    var userMessage: String {
      switch self {
      case .cleanupFailed:
        "The example file could not be removed. Your own recording and replay still work."
      case .timeout:
        "The example took too long to load. You can still record and replay your own try."
      case .playbackFailed:
        "The example could not play. You can still record and replay your own try."
      default: "The example is unavailable. You can still record and replay your own try."
      }
    }
  }
  enum ResearchPracticeExampleState: Equatable {
    case idle, loading, playing
    case failed(ResearchPracticeExampleError)
  }
  @MainActor
  protocol ResearchPracticeExampleLoading: AnyObject {
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample?
    func load(example: ResearchPracticeExample) async throws -> Data
  }
  @MainActor
  protocol ResearchPracticeExampleStoring: AnyObject {
    // Retain ownership even after a partial write or failed removal.
    var ownedURL: URL? { get }
    func write(_ data: Data) throws -> URL
    func remove(_ url: URL) throws
  }

  @MainActor
  final class ResearchPracticeExampleClient: ResearchPracticeExampleLoading {
    private let session: URLSession
    private let deadline: Duration
    private let service: ResearchFeedbackService
    init(
      configuration: URLSessionConfiguration = .ephemeral, deadline: Duration = .seconds(10),
      service: ResearchFeedbackService = .currentUnified
    ) {
      self.service = service
      self.deadline = min(max(deadline, .milliseconds(1)), .seconds(10))
      configuration.urlCache = nil
      configuration.httpCookieStorage = nil
      configuration.httpShouldSetCookies = false
      configuration.timeoutIntervalForRequest = 10
      configuration.timeoutIntervalForResource = 10
      session = URLSession(
        configuration: configuration, delegate: NoRedirects(), delegateQueue: nil)
    }
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      ResearchPracticeExamples.example(for: prompt)
    }
    func load(example: ResearchPracticeExample) async throws -> Data {
      // Service-returned or caller-supplied metadata never establishes a trusted asset.
      guard ResearchPracticeExamples.all.contains(example) else {
        throw ResearchPracticeExampleError.unsupportedExample
      }
      do { try service.requireConfigured() } catch {
        throw ResearchPracticeExampleError.invalidData
      }
      try Task.checkCancellation()
      let endpoint = URL(
        string: service.origin + "/api/public-references/" + example.sourceWord)!
      let session = self.session
      let deadline = self.deadline
      let origin = service.origin
      return try await withThrowingTaskGroup(of: Data.self) { group in
        group.addTask {
          try await Self.transfer(
            session: session, endpoint: endpoint, example: example, origin: origin)
        }
        group.addTask {
          try await Task.sleep(for: deadline)
          throw ResearchPracticeExampleError.timeout
        }
        defer { group.cancelAll() }
        let bytes = try await group.next()!
        try Task.checkCancellation()
        return bytes
      }
    }
    nonisolated static func validate(_ data: Data, example: ResearchPracticeExample) throws {
      guard !data.isEmpty, data.count <= 132_096, FeedbackContract.sha(data) == example.wavSha256,
        let pcm = try? FeedbackPCM.measure(data), pcm.sampleCount == example.sampleCount
      else { throw ResearchPracticeExampleError.invalidData }
    }
    private nonisolated static func transfer(
      session: URLSession, endpoint: URL, example: ResearchPracticeExample, origin: String
    ) async throws -> Data {
      var request = URLRequest(url: endpoint)
      request.httpMethod = "GET"
      request.timeoutInterval = 10
      request.cachePolicy = .reloadIgnoringLocalCacheData
      request.setValue(origin, forHTTPHeaderField: "Origin")
      request.setValue("audio/wav", forHTTPHeaderField: "Accept")
      do {
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.url == endpoint, http.statusCode == 200,
          http.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?
            .trimmingCharacters(in: .whitespaces).lowercased() == "audio/wav"
        else { throw ResearchPracticeExampleError.invalidData }
        guard response.expectedContentLength <= 132_096 else {
          throw ResearchPracticeExampleError.invalidData
        }
        var data = Data()
        for try await byte in bytes {
          try Task.checkCancellation()
          guard data.count < 132_096 else { throw ResearchPracticeExampleError.invalidData }
          data.append(byte)
        }
        try Task.checkCancellation()
        try validate(data, example: example)
        return data
      } catch let error as URLError {
        if error.code == .cancelled { throw CancellationError() }
        if error.code == .timedOut { throw ResearchPracticeExampleError.timeout }
        throw ResearchPracticeExampleError.unavailable
      }
    }
    private final class NoRedirects: NSObject, URLSessionTaskDelegate {
      func urlSession(
        _ session: URLSession, task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
      ) { completionHandler(nil) }
    }
  }

  /// Owns at most one public example file; never touches the private recording namespace.
  @MainActor
  final class ResearchPracticeExampleStore: ResearchPracticeExampleStoring {
    private(set) var ownedURL: URL?
    private var fileOwnerID: UUID?
    private let directory: URL
    private let fileOwnership: ProcessAudioFileOwnership
    private let removeFile: (URL) throws -> Void
    init(
      directory: URL = FileManager.default.temporaryDirectory, fileManager: FileManager = .default,
      fileOwnership: ProcessAudioFileOwnership? = nil,
      removeFile: ((URL) throws -> Void)? = nil
    ) {
      self.directory = directory
      self.fileOwnership = fileOwnership ?? .shared
      self.removeFile =
        removeFile ?? {
          try TemporaryRecordingStore(fileManager: fileManager).removeRecordingIfPresent(at: $0)
        }
    }
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil, !data.isEmpty, data.count <= 132_096 else {
        throw ResearchPracticeExampleError.storageFailed
      }
      let url = directory.appendingPathComponent("cadence-public-example-" + UUID().uuidString)
        .appendingPathExtension("wav")
      let descriptor = Darwin.open(
        url.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
      guard descriptor >= 0 else { throw ResearchPracticeExampleError.storageFailed }
      ownedURL = url  // Only an exclusively created file establishes cleanup ownership.
      let owner = UUID()
      fileOwnerID = owner
      fileOwnership.retain(url, owner: owner)
      defer { Darwin.close(descriptor) }
      try data.withUnsafeBytes { buffer in
        guard let base = buffer.baseAddress else {
          throw ResearchPracticeExampleError.storageFailed
        }
        var offset = 0
        while offset < data.count {
          let written = Darwin.write(descriptor, base.advanced(by: offset), data.count - offset)
          guard written > 0 else { throw ResearchPracticeExampleError.storageFailed }
          offset += written
        }
      }
      return url
    }
    func remove(_ url: URL) throws {
      guard ownedURL == url, let owner = fileOwnerID else {
        throw ResearchPracticeExampleError.cleanupFailed
      }
      do {
        guard fileOwnership.canRemove(url, owner: owner) else {
          throw ResearchPracticeExampleError.cleanupFailed
        }
        try removeFile(url)
        fileOwnership.didRemove(url, owner: owner)
        ownedURL = nil
        fileOwnerID = nil
      } catch {
        // The process registry retains this producer until exact successful removal.
        // A borrowed example is protected even when its original view disappears.
        _ = fileOwnership.registerCleanupRecovery(owner: owner) { [self] in
          guard ownedURL == url, fileOwnerID == owner else { return false }
          do {
            try remove(url)
            return ownedURL == nil
          } catch { return false }
        }
        throw ResearchPracticeExampleError.cleanupFailed
      }
    }
  }
#endif
