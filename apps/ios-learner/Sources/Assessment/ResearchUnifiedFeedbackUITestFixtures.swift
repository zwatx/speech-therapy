#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  /// Explicit generated UI seam. PCM/results are invented; no sensor, socket or model calls.
  @MainActor
  enum ResearchUnifiedFeedbackUITestFixtures {
    enum Case: String {
      case combined, cleanup, listening, loadingExample, unavailableExample, cleanupExample
      case missingExample, listeningRing
      case twoTries, twoTryCleanup
      case freeCompletion, freeSaveFailure, freeDeniedReplacement, freeCleanup
      case historyContinuation
      case guessMatched, guessDifferent, guessUncertain
    }
    static func selected(_ arguments: [String] = ProcessInfo.processInfo.arguments) -> Case? {
      guard let index = arguments.firstIndex(of: "-CadenceUnifiedFeedbackUITestCase"),
        arguments.indices.contains(index + 1)
      else { return nil }
      return Case(rawValue: arguments[index + 1])
    }
    static func session(
      for testCase: Case, arguments: [String] = ProcessInfo.processInfo.arguments
    ) -> ResearchFeedbackSession {
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      let capturer: any AudioCapturing =
        [
          Case.twoTries, .twoTryCleanup, .freeCompletion, .freeSaveFailure,
          .freeDeniedReplacement, .freeCleanup, .guessMatched, .guessDifferent, .guessUncertain,
        ].contains(testCase)
        ? TwoTryCapture(
          failFirstDiscard: testCase == .twoTryCleanup || testCase == .freeCleanup,
          denyReplacement: testCase == .freeDeniedReplacement, hardware: hardware, files: files)
        : Capture(hardware: hardware, files: files)
      let session = ResearchFeedbackSession(
        capturer: capturer,
        player: ResearchAcknowledgedPlaybackUITestFixture(
          completion: .explicitStop, ownership: hardware, fileOwnership: files),
        processor: Word(testCase), soundProcessor: Sound(),
        exampleLoader: Examples(testCase),
        exampleStore: OnceFailedExampleStore(
          failFirst: testCase == .cleanupExample, files: files),
        participationWriter: participationWriter(for: testCase, arguments: arguments),
        wordGuessProcessor: [.guessMatched, .guessDifferent, .guessUncertain].contains(testCase)
          ? WordGuess(testCase) : nil)
      session.selectedPrompt =
        testCase == .listeningRing
        ? ResearchFeedbackCatalog.prompts.first { $0.id == "ng-end-ring" }
        : ResearchFeedbackCatalog.prompts[1]
      // The setter's strongly owned cleanup task gates canRecord/Start. Hosts that
      // need settled setup must await settleSetup(session), never infer idle.
      return session  // Context and all three processing consent controls remain unset/off.
    }
    @discardableResult
    static func settleSetup(_ session: ResearchFeedbackSession) async -> Bool {
      await session.awaitPendingAudioCleanup()
    }
    static func controlledSoundProcessor() -> any ResearchSoundProcessing { Sound() }

    /// Home and the free writer select exactly the same isolated real store.
    static func participationStore(
      for testCase: Case, arguments: [String] = ProcessInfo.processInfo.arguments
    ) -> PracticeParticipationStore {
      if let guided = ResearchGuidedWordUITestFixtures.selected(arguments) {
        return ResearchGuidedWordUITestFixtures.participationStore(for: guided)
      }
      if let store = participationStores[testCase] { return store }
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-free-participation-\(testCase.rawValue)-\(UUID().uuidString)",
        isDirectory: true)
      let store = PracticeParticipationStore(
        fileURL: directory.appendingPathComponent("participation.json"))
      if testCase == .historyContinuation {
        // Explicit metadata-only seed. Known library groups; never raw audio or owner history.
        let rows: [(String, TimeInterval, String)] = [
          ("00000000-0000-4000-8000-000000000301", 1_790_000_003, "r"),
          ("00000000-0000-4000-8000-000000000302", 1_790_000_002, "voiced-th"),
          ("00000000-0000-4000-8000-000000000303", 1_790_000_001, "zh"),
        ]
        do {
          for (id, timestamp, soundID) in rows {
            guard let uuid = UUID(uuidString: id) else {
              preconditionFailure("Invalid generated history UUID")
            }
            try store.record(
              sessionID: uuid, completedAt: Date(timeIntervalSince1970: timestamp),
              soundID: soundID, wordCount: 1)
          }
        } catch {
          // Do not silently substitute empty/shared history after a failed fixture write.
          preconditionFailure("Generated history continuation seed could not be written")
        }
      }
      participationStores[testCase] = store
      return store
    }

    static func participationWriter(
      for testCase: Case, arguments: [String] = ProcessInfo.processInfo.arguments
    ) -> (any ResearchGuidedPracticeParticipationRecording)? {
      let store = participationStore(for: testCase, arguments: arguments)
      guard testCase == .freeSaveFailure else { return store }
      let identity = ObjectIdentifier(store)
      if let writer = failingWriters[identity] { return writer }
      let writer = FirstSaveFailure(store: store)
      failingWriters[identity] = writer
      return writer
    }

    private static var participationStores: [Case: PracticeParticipationStore] = [:]
    private static var failingWriters: [ObjectIdentifier: FirstSaveFailure] = [:]
    private final class FirstSaveFailure: ResearchGuidedPracticeParticipationRecording {
      private let store: PracticeParticipationStore
      private var failedOnce = false
      init(store: PracticeParticipationStore) { self.store = store }
      func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
        if !failedOnce {
          failedOnce = true
          throw FixtureSaveError.firstWrite  // Before the real store writes anything.
        }
        try store.record(
          sessionID: sessionID, completedAt: completedAt,
          soundID: soundID, wordCount: wordCount)
      }
    }
    private enum FixtureSaveError: Error { case firstWrite }

    /// Distinct generated paths/PCM; only explicit Record creates a clip.
    private final class TwoTryCapture: AudioCapturing {
      private let ownership: ResearchGeneratedCaptureFileOwnership
      var cleanupState: CaptureCleanupState { ownership.cleanupState }
      /// Subscribe on MainActor; committed initial/mutation delivery is synchronous and serialized.
      var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
        ownership.cleanupStatePublisher
      }
      func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
        ownership.retryCleanup(operationID: operationID)
      }
      func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
        ownership.completedFileCleanup(operationID: operationID)
      }
      private let failFirstDiscard: Bool
      private var failedDiscard = false
      private var activeURL: URL?
      private var captures = 0
      private let denyReplacement: Bool
      private var permissionRequests = 0
      init(
        failFirstDiscard: Bool, denyReplacement: Bool = false,
        hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership
      ) {
        self.failFirstDiscard = failFirstDiscard
        self.denyReplacement = denyReplacement
        ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
      }
      func requestPermission() async -> Bool {
        permissionRequests += 1
        return !denyReplacement || permissionRequests == 1
      }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        guard activeURL == nil, ownership.retainedFileCount < 2, captures < 64 else {
          throw RecordingFeedbackError.invalidRecording
        }
        let file = ownership.directory.appendingPathComponent("generated-unified-try-\(UUID()).wav")
        try ownership.begin(file)
        captures += 1
        activeURL = file
        var bytes = Data()
        func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
        func word(_ value: Int, _ count: Int) {
          for offset in 0..<count { bytes.append(UInt8((value >> (offset * 8)) & 255)) }
        }
        text("RIFF")
        word(6436, 4)
        text("WAVEfmt ")
        word(16, 4)
        word(1, 2)
        word(1, 2)
        word(16000, 4)
        word(32000, 4)
        word(2, 2)
        word(16, 2)
        text("data")
        word(6400, 4)
        // Bounded positive PCM16 amplitudes distinguish every capture without clipping.
        for _ in 0..<3200 { word(8192 + 256 * captures, 2) }
        do {
          try bytes.write(to: file)
        } catch {
          activeURL = nil
          try? ownership.cancel(file)
          throw error
        }
      }
      func stop() throws -> CapturedRecording {
        guard let file = activeURL else { throw RecordingFeedbackError.invalidRecording }
        let id = try ownership.stop(file)
        activeURL = nil
        let power = Float(20 * log10(Double(8192 + 256 * captures) / 32768))
        return .init(
          url: file, summary: .init(duration: 0.2, averagePower: power), cleanupOwnerID: id)
      }
      func cancel() throws {
        guard let file = activeURL else { return }
        activeURL = nil
        try ownership.cancel(file)
      }
      func discard(_ recording: CapturedRecording) throws {
        guard ownership.owner(of: recording.url) != nil, activeURL != recording.url else {
          throw AudioCaptureError.recordingNotOwned
        }
        let fail = failFirstDiscard && !failedDiscard
        if fail { failedDiscard = true }
        try ownership.remove(
          recording.url, forcedError: fail ? .couldNotDeleteTemporaryRecording : nil)
      }
    }
    private final class Capture: AudioCapturing {
      private let ownership: ResearchGeneratedCaptureFileOwnership
      var cleanupState: CaptureCleanupState { ownership.cleanupState }
      /// Subscribe on MainActor; committed initial/mutation delivery is synchronous and serialized.
      var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
        ownership.cleanupStatePublisher
      }
      func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
        ownership.retryCleanup(operationID: operationID)
      }
      func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
        ownership.completedFileCleanup(operationID: operationID)
      }
      private let file: URL
      private var active = false
      init(hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership) {
        ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
        file = ownership.directory.appendingPathComponent("generated-unified-\(UUID()).wav")
      }
      func requestPermission() async -> Bool { true }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        guard !active else { throw AudioCaptureError.couldNotStart }
        try ownership.begin(file)
        var bytes = Data()
        func text(_ text: String) { bytes.append(contentsOf: text.utf8) }
        func word(_ value: Int, _ count: Int) {
          for offset in 0..<count { bytes.append(UInt8((value >> (offset * 8)) & 255)) }
        }
        text("RIFF")
        word(6436, 4)
        text("WAVEfmt ")
        word(16, 4)
        word(1, 2)
        word(1, 2)
        word(16000, 4)
        word(32000, 4)
        word(2, 2)
        word(16, 2)
        text("data")
        word(6400, 4)
        for _ in 0..<3200 { word(8192, 2) }
        do {
          try bytes.write(to: file)
        } catch {
          try? ownership.cancel(file)
          throw error
        }
        active = true
      }
      func stop() throws -> CapturedRecording {
        guard active else { throw AudioCaptureError.couldNotReadRecording }
        let id = try ownership.stop(file)
        active = false
        return .init(
          url: file, summary: .init(duration: 0.2, averagePower: -12), cleanupOwnerID: id)
      }
      func cancel() throws {
        guard active else { return }
        active = false
        try ownership.cancel(file)
      }
      func discard(_ recording: CapturedRecording) throws { try ownership.remove(recording.url) }
    }
    /// Distinct generated bytes and metadata, never a substitute under a licensed asset's hash.
    private final class Examples: ResearchPracticeExampleLoading {
      private let testCase: Case
      private let bytes: Data
      init(_ testCase: Case) {
        self.testCase = testCase
        var data = Data()
        func text(_ value: String) { data.append(contentsOf: value.utf8) }
        func word(_ value: Int, _ count: Int) {
          for offset in 0..<count { data.append(UInt8((value >> (offset * 8)) & 255)) }
        }
        text("RIFF")
        word(6436, 4)
        text("WAVEfmt ")
        word(16, 4)
        word(1, 2)
        word(1, 2)
        word(16000, 4)
        word(32000, 4)
        word(2, 2)
        word(16, 2)
        text("data")
        word(6400, 4)
        for index in 0..<3200 { word(index % 32 < 16 ? 4096 : 61440, 2) }
        bytes = data
      }
      func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
        guard testCase != .missingExample, ResearchFeedbackCatalog.prompts.contains(prompt)
        else { return nil }
        return .init(
          sourceWord: "generated-ui", author: "Generated UI fixture",
          licenseId: "Generated fixture",
          licenseURL: URL(string: "https://example.invalid/generated-fixture")!,
          sourceURL: URL(string: "https://example.invalid/generated-fixture")!,
          attribution: "Generated PCM for a sensor-free UI test. No human spoke this example.",
          changes: "Generated 3200-sample square wave; no licensed reference audio used.",
          speakerAgeKnown: false, clinicalReferenceApproved: false,
          wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
      }
      func load(example: ResearchPracticeExample) async throws -> Data {
        if testCase == .unavailableExample { throw ResearchPracticeExampleError.unavailable }
        if testCase == .loadingExample { try await Task.sleep(for: .seconds(30)) }
        try Task.checkCancellation()
        return bytes
      }
    }
    /// An explicit public-file removal failure, independent of microphone/service cleanup.
    private final class OnceFailedExampleStore: ResearchPracticeExampleStoring {
      private let store: ResearchPracticeExampleStore
      init(failFirst: Bool, files: ProcessAudioFileOwnership) {
        let removal = ResearchGeneratedExampleRemoval(failFirst: failFirst)
        store = ResearchPracticeExampleStore(
          fileOwnership: files, removeFile: { try removal.remove($0) })
      }
      var ownedURL: URL? { store.ownedURL }
      func write(_ data: Data) throws -> URL { try store.write(data) }
      func remove(_ url: URL) throws { try store.remove(url) }
    }
    private final class Word: ResearchFeedbackProcessing {
      private let testCase: Case
      init(_ testCase: Case) { self.testCase = testCase }
      func process(
        attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
        practiceContext: ResearchPracticeContext
      ) async throws -> RecordingFeedback {
        let audio = try FeedbackPCM.read(recording.url)
        let pcm = try FeedbackPCM.measure(audio)
        let body = try ResearchFeedbackClient.requestBody(
          attemptId: attemptId, audio: audio, prompt: prompt, practiceContext: practiceContext)
        let binding = FeedbackContract.pins.merging([
          "attemptId": attemptId.uuidString.lowercased(),
          "requestSha256": FeedbackContract.sha(body),
          "audioSha256": FeedbackContract.sha(audio),
          "promptSha256": FeedbackContract.sha(
            try FeedbackContract.encoder().encode(prompt.requestPrompt)),
        ]) { _, next in next }
        let paused = testCase == .cleanup
        let lexicalReason: String? =
          testCase == .guessDifferent
          ? "requested_word_not_matched"
          : (testCase == .guessUncertain ? "recognition_uncertain" : nil)
        let reason: Any =
          paused ? "cleanup_unconfirmed" : (lexicalReason.map { $0 as Any } ?? NSNull())
        var capture: [String: Any] = [
          "state": "observed", "reason": NSNull(), "sampleCount": pcm.sampleCount,
          "durationMilliseconds": pcm.durationMilliseconds, "rms": pcm.rms, "rmsDbfs": pcm.rmsDbfs,
          "peak": pcm.peak, "railSamples": pcm.railSamples, "clippedFraction": pcm.clippedFraction,
        ]
        if paused {
          capture = Dictionary(uniqueKeysWithValues: capture.keys.map { ($0, NSNull() as Any) })
          capture["state"] = "unavailable"
          capture["reason"] = reason
        }
        var expected: [String: Any] = binding
        expected["evidenceSha256"] = paused ? NSNull() : String(repeating: "e", count: 64)
        let response: [String: Any] = [
          "schemaVersion": 1, "kind": "recording_feedback",
          "status": paused ? "unavailable" : "observed",
          "reason": reason,
          "stages": [
            "capture": capture,
            "speech": [
              "state": paused ? "unavailable" : "model_detected",
              "reason": paused ? reason : NSNull(),
            ],
            "word": [
              "state": paused
                ? "unavailable"
                : (testCase == .guessDifferent
                  ? "model_not_matched"
                  : (testCase == .guessUncertain ? "uncertain" : "model_matched")),
              "reason": reason,
            ],
          ],
          "targetAssessment": [
            "state": prompt.targetUnsupported ? "unsupported" : "not_performed",
            "reason": prompt.targetUnsupported ? "unsupported_target" : "not_validated",
          ],
          "suggestionCodes": ["review_recording"], "binding": expected,
          "claimLimits": Dictionary(
            uniqueKeysWithValues: FeedbackContract.claims.map { ($0, false) }),
          "elapsedMilliseconds": 0,
        ]
        let data = try JSONSerialization.data(
          withJSONObject: response, options: [.sortedKeys, .withoutEscapingSlashes])
        return try FeedbackContract.decode(
          data, expectedBinding: binding, pcm: pcm, targetUnsupported: prompt.targetUnsupported)
      }
    }
    /// Synthetic lexical tokens paired with a real decoded generated base contract.
    /// This seam never invokes a recognizer or derives a guess from the requested prompt.
    private final class WordGuess: ResearchWordGuessProcessing {
      private let testCase: Case
      init(_ testCase: Case) { self.testCase = testCase }
      func process(
        attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
        practiceContext: ResearchPracticeContext,
        onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
      ) async throws -> ResearchWordGuessFeedback {
        let feedback = try await Word(testCase).process(
          attemptId: attemptId, recording: recording, prompt: prompt,
          practiceContext: practiceContext)
        let token: String? =
          testCase == .guessMatched
          ? "bread"
          : (testCase == .guessDifferent ? "red" : nil)
        return .init(
          feedback: feedback,
          wordGuess: token.map { ResearchRecognizerWordGuess(normalizedWord: $0) })
      }
    }
    private final class Sound: ResearchSoundProcessing {
      func declaration() async throws -> ResearchSoundDeclaration {
        .init(
          serverNonce: "33333333-3333-4333-8333-333333333333",
          csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
      }
      func prepare(
        recording: CapturedRecording, declaration: ResearchSoundDeclaration,
        context: ResearchSoundCheckContext
      ) async throws -> ResearchSoundPrepared {
        try ResearchSoundContract.prepare(
          audio: ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url)),
          declaration: declaration, context: context)
      }
      func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
        // Fabricated BW preference passes the public contract; no model produced it.
        let response = ResearchSoundJSON.object([
          "schemaVersion": .integer(1), "kind": .string(ResearchSoundContract.kind),
          "purpose": .string(ResearchSoundContract.purpose),
          "status": .string("observed_model_preference"),
          "reason": .string("model_preferred_candidate"), "modelPreference": .string("w_path"),
          "binding": prepared.expected, "claimLimits": ResearchSoundContract.falseClaims,
        ])
        return try ResearchSoundContract.observation(
          response.canonical(), expected: prepared.expected)
      }
      func cancel(_ prepared: ResearchSoundPrepared) async throws {}
      func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
        async throws
      {}
    }
  }
#endif
