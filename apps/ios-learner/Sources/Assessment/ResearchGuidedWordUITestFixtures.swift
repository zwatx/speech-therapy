#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  /// Generated guided UI seam: no sensors, sockets, models, human speech or licensed examples.
  @MainActor
  enum ResearchGuidedWordUITestFixtures {
    enum Case: String {
      case mixed, denied, delayed, paused, cleanupExample, cleanupRecording, historySaveFailure
    }
    static let fixtureTag =
      "Generated guided UI fixture · No sensors, network or models · Request start is simulated"

    static func selected(_ arguments: [String] = ProcessInfo.processInfo.arguments) -> Case? {
      guard let index = arguments.firstIndex(of: "-CadenceGuidedWordUITestCase"),
        arguments.indices.contains(index + 1)
      else { return nil }
      return Case(rawValue: arguments[index + 1])
    }

    /// One feedback session owns the take. The caller constructs the guided coordinator.
    static func feedbackSession(for testCase: Case) -> ResearchFeedbackSession {
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      return ResearchFeedbackSession(
        capturer: Capture(
          permissionGranted: testCase != .denied,
          failFirstCancellation: testCase == .cleanupRecording, hardware: hardware, files: files),
        player: ResearchAcknowledgedPlaybackUITestFixture(
          completion: .explicitStop, ownership: hardware, fileOwnership: files),
        processor: Word(testCase),
        soundProcessor: ResearchUnifiedFeedbackUITestFixtures.controlledSoundProcessor(),
        exampleLoader: Examples(),
        exampleStore: ExampleStore(failFirstRemoval: testCase == .cleanupExample, files: files))
    }

    /// The existing history surface and guided writer borrow this same isolated real store.
    static func participationStore(for testCase: Case) -> PracticeParticipationStore {
      participationFixture(for: testCase).store
    }

    static func participationWriter(for testCase: Case)
      -> any ResearchGuidedPracticeParticipationRecording
    {
      participationFixture(for: testCase).writer
    }

    private static var participationFixtures: [Case: ParticipationFixture] = [:]
    private static func participationFixture(for testCase: Case) -> ParticipationFixture {
      if let fixture = participationFixtures[testCase] { return fixture }
      let fixture = ParticipationFixture(testCase)
      participationFixtures[testCase] = fixture
      return fixture
    }

    @MainActor
    private final class ParticipationFixture {
      let store: PracticeParticipationStore
      let writer: any ResearchGuidedPracticeParticipationRecording
      init(_ testCase: Case) {
        // Per-case/process UUID path; never uses shared/Application Support/owner history.
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "generated-guided-participation-\(testCase.rawValue)-\(UUID().uuidString)",
          isDirectory: true)
        let store = PracticeParticipationStore(
          fileURL: directory.appendingPathComponent("participation.json"))
        self.store = store
        if testCase == .historySaveFailure {
          writer = FirstSaveFailure(store: store)
        } else {
          writer = store
        }
      }
    }

    private final class FirstSaveFailure: ResearchGuidedPracticeParticipationRecording {
      private let store: PracticeParticipationStore
      private var failedOnce = false
      init(store: PracticeParticipationStore) { self.store = store }
      func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
        if !failedOnce {
          failedOnce = true
          // Deliberately before the real store's write; the same completion can be retried.
          throw FixtureHistoryWriteError.simulatedFirstWrite
        }
        try store.record(
          sessionID: sessionID, completedAt: completedAt, soundID: soundID, wordCount: wordCount)
      }
    }
    private enum FixtureHistoryWriteError: Error { case simulatedFirstWrite }

    private static func wav(_ sample: (Int) -> Int16) -> Data {
      var bytes = Data()
      func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
      func word(_ value: UInt32, _ count: Int) {
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
      for index in 0..<3200 { word(UInt32(UInt16(bitPattern: sample(index))), 2) }
      return bytes
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
      private let permissionGranted: Bool
      private var active = false
      private var captures = 0
      private var failFirstCancellation: Bool
      init(
        permissionGranted: Bool, failFirstCancellation: Bool = false,
        hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership
      ) {
        self.permissionGranted = permissionGranted
        self.failFirstCancellation = failFirstCancellation
        ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
        file = ownership.directory.appendingPathComponent("generated-guided-capture-\(UUID()).wav")
      }
      func requestPermission() async -> Bool { permissionGranted }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        guard permissionGranted, !active, captures < 1024 else {
          throw RecordingFeedbackError.invalidRecording
        }
        try ownership.begin(file)
        // Each finite capture has distinct PCM bytes/hash, even for the same prompt.
        captures += 1
        let sample = Int16(8192 + captures)
        do {
          try ResearchGuidedWordUITestFixtures.wav { _ in sample }.write(to: file)
        } catch {
          try? ownership.cancel(file)
          throw error
        }
        active = true
      }
      func stop() throws -> CapturedRecording {
        guard active else { throw RecordingFeedbackError.invalidRecording }
        let id = try ownership.stop(file)
        active = false
        return .init(
          url: file, summary: .init(duration: 0.2, averagePower: -12), cleanupOwnerID: id)
      }
      func cancel() throws {
        guard active else { return }
        active = false
        let failure = failFirstCancellation
        failFirstCancellation = false
        try ownership.cancel(file, forcedError: failure ? .couldNotDeleteTemporaryRecording : nil)
      }
      func discard(_ recording: CapturedRecording) throws {
        guard recording.url == file else { throw AudioCaptureError.recordingNotOwned }
        try ownership.remove(recording.url)
      }
    }

    private final class Examples: ResearchPracticeExampleLoading {
      private let bytes = ResearchGuidedWordUITestFixtures.wav { index in
        index % 32 < 16 ? 4096 : -4096
      }
      func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
        guard ResearchFeedbackCatalog.prompts.contains(prompt) else { return nil }
        return .init(
          sourceWord: "generated-guided-\(prompt.word)", author: "Generated guided UI fixture",
          licenseId: "Generated fixture; no licensed audio",
          licenseURL: URL(string: "https://example.invalid/generated-guided-fixture")!,
          sourceURL: URL(string: "https://example.invalid/generated-guided-fixture")!,
          attribution: "Generated PCM for a sensor-free UI test. No human spoke this example.",
          changes: "Generated 3200-sample square wave; no source recording used.",
          speakerAgeKnown: false, clinicalReferenceApproved: false,
          wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200,
          declaredVariety: "Generated waveform; no speech variety", isGeneratedFixture: true)
      }
      func load(example: ResearchPracticeExample) async throws -> Data {
        try Task.checkCancellation()
        guard example.isGeneratedFixture, example.wavSha256 == FeedbackContract.sha(bytes),
          example.sampleCount == 3200
        else { throw ResearchPracticeExampleError.unavailable }
        return bytes
      }
    }

    /// Fails the first owned public-file removal; retry delegates to the actual owned store.
    private final class ExampleStore: ResearchPracticeExampleStoring {
      private let store: ResearchPracticeExampleStore
      init(failFirstRemoval: Bool, files: ProcessAudioFileOwnership) {
        let removal = ResearchGeneratedExampleRemoval(failFirst: failFirstRemoval)
        store = ResearchPracticeExampleStore(
          fileOwnership: files, removeFile: { try removal.remove($0) })
      }
      var ownedURL: URL? { store.ownedURL }
      func write(_ data: Data) throws -> URL { try store.write(data) }
      func remove(_ url: URL) throws { try store.remove(url) }
    }

    private final class Word: ResearchFeedbackProcessing {
      private let testCase: Case
      private var calls = 0
      init(_ testCase: Case) { self.testCase = testCase }
      func process(
        attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
        practiceContext: ResearchPracticeContext
      ) async throws -> RecordingFeedback {
        // This compatibility method never manufactures an actual-transport start event.
        try await result(
          attemptId: attemptId, recording: recording, prompt: prompt,
          practiceContext: practiceContext, simulatedStart: nil)
      }

      func process(
        attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
        practiceContext: ResearchPracticeContext,
        onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
      ) async throws -> RecordingFeedback {
        try await result(
          attemptId: attemptId, recording: recording, prompt: prompt,
          practiceContext: practiceContext,
          simulatedStart: { onEvent(.requestStarted) })
      }

      private func result(
        attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
        practiceContext: ResearchPracticeContext, simulatedStart: (@MainActor () -> Void)?
      ) async throws -> RecordingFeedback {
        try Task.checkCancellation()
        guard calls < 4096 else { throw RecordingFeedbackError.processingUnavailable }
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
        let choice = calls % 4
        calls += 1
        simulatedStart?()  // Explicitly simulated request start; no URLSession/socket exists here.
        if testCase == .delayed { try await Task.sleep(for: .seconds(30)) }
        try Task.checkCancellation()
        let paused = testCase == .paused
        let reason: String? =
          paused
          ? "cleanup_unconfirmed"
          : [
            nil, "requested_word_not_matched", "recognition_uncertain", "model_unavailable",
          ][choice]
        let unavailable = paused || reason == "model_unavailable"
        let wordState =
          unavailable
          ? "unavailable"
          : [
            "model_matched", "model_not_matched", "uncertain", "unavailable",
          ][choice]
        var capture: [String: Any] = [
          "state": "observed", "reason": NSNull(), "sampleCount": pcm.sampleCount,
          "durationMilliseconds": pcm.durationMilliseconds, "rms": pcm.rms, "rmsDbfs": pcm.rmsDbfs,
          "peak": pcm.peak, "railSamples": pcm.railSamples, "clippedFraction": pcm.clippedFraction,
        ]
        if paused {
          capture = Dictionary(uniqueKeysWithValues: capture.keys.map { ($0, NSNull() as Any) })
          capture["state"] = "unavailable"
          capture["reason"] = "cleanup_unconfirmed"
        }
        var expected: [String: Any] = binding
        expected["evidenceSha256"] = paused ? NSNull() : String(repeating: "e", count: 64)
        let response: [String: Any] = [
          "schemaVersion": 1, "kind": "recording_feedback",
          "status": unavailable ? "unavailable" : "observed", "reason": reason as Any? ?? NSNull(),
          "stages": [
            "capture": capture,
            "speech": [
              "state": unavailable ? "unavailable" : "model_detected",
              "reason": unavailable ? reason as Any? ?? NSNull() : NSNull(),
            ],
            "word": ["state": wordState, "reason": reason as Any? ?? NSNull()],
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
  }
#endif
