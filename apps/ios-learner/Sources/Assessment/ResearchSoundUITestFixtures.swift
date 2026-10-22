#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  /// Explicitly labelled UI-test injection into the real view/session. No sensors or sockets.
  @MainActor
  enum ResearchSoundUITestFixtures {
    enum Case: String { case br, bw, other, inconclusive, paused, cleanup, cancelled }
    static func selected(_ arguments: [String] = ProcessInfo.processInfo.arguments) -> Case? {
      guard let index = arguments.firstIndex(of: "-CadenceSoundUITestCase"),
        arguments.indices.contains(index + 1)
      else { return nil }
      return Case(rawValue: arguments[index + 1])
    }
    /// Reachable only after the host admits an explicit generated Sound run. Construction
    /// creates isolated ownership in memory; it does not load history or create media.
    @MainActor final class RunResources {
      let runID: UUID
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      fileprivate init(runID: UUID) { self.runID = runID }
    }
    private static var runResources: [UUID: RunResources] = [:]
    static func resources(runID: UUID) -> RunResources {
      precondition(runID != UUID(uuidString: "00000000-0000-0000-0000-000000000000"))
      if let resources = runResources[runID] { return resources }
      let resources = RunResources(runID: runID)
      runResources[runID] = resources
      return resources
    }
    static func session(for testCase: Case) -> ResearchSoundSession {
      session(for: testCase, resources: RunResources(runID: UUID()))
    }
    /// Every reopening and the process recovery host must share this admitted run's pair.
    static func session(for testCase: Case, resources: RunResources) -> ResearchSoundSession {
      let hardware = resources.hardware
      let files = resources.files
      return ResearchSoundSession(
        capturer: Capture(failDiscard: testCase == .cleanup, hardware: hardware, files: files),
        player: ResearchAcknowledgedPlaybackUITestFixture(
          completion: .immediate, ownership: hardware, fileOwnership: files),
        processor: Processor(testCase), fileOwnership: files)
    }
    static func participationStore(runID: UUID) -> PracticeParticipationStore {
      precondition(runID != UUID(uuidString: "00000000-0000-0000-0000-000000000000"))
      if let store = participationStores[runID] { return store }
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-sound-participation-\(runID)-\(UUID())", isDirectory: true)
      let store = PracticeParticipationStore(
        fileURL: directory.appendingPathComponent("participation.json"))
      participationStores[runID] = store
      return store
    }
    private static var participationStores: [UUID: PracticeParticipationStore] = [:]

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
      private let failDiscard: Bool
      private var active = false
      init(failDiscard: Bool, hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership) {
        self.failDiscard = failDiscard
        ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
        file = ownership.directory.appendingPathComponent(UUID().uuidString + ".wav")
      }
      func requestPermission() async -> Bool { true }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        guard !active else { throw AudioCaptureError.couldNotStart }
        try ownership.begin(file)
        var bytes = Data()
        func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
        func word(_ value: Int, _ count: Int) {
          for i in 0..<count { bytes.append(UInt8((value >> (i * 8)) & 255)) }
        }
        text("RIFF")
        word(4836, 4)
        text("WAVEfmt ")
        word(16, 4)
        word(1, 2)
        word(1, 2)
        word(16000, 4)
        word(32000, 4)
        word(2, 2)
        word(16, 2)
        text("data")
        word(4800, 4)
        bytes.append(Data(repeating: 0, count: 4800))
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
          url: file, summary: .init(duration: 0.15, averagePower: -120), cleanupOwnerID: id)
      }
      func cancel() throws {
        guard active else { return }
        active = false
        try ownership.cancel(file)
      }
      func discard(_ recording: CapturedRecording) throws {
        guard recording.url == file else { throw AudioCaptureError.recordingNotOwned }
        try ownership.remove(
          recording.url, forcedError: failDiscard ? .couldNotDeleteTemporaryRecording : nil,
          persistentFailure: failDiscard)
      }
    }
    private final class Processor: ResearchSoundProcessing {
      private let testCase: Case
      init(_ testCase: Case) { self.testCase = testCase }
      func declaration() async throws -> ResearchSoundDeclaration {
        .init(
          serverNonce: "33333333-3333-4333-8333-333333333333",
          csrfToken: String(repeating: "a", count: 64), processingAvailable: true)
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
        if testCase == .cancelled { try await Task.sleep(for: .seconds(30)) }
        let status: String
        let reason: String
        let preference: ResearchSoundJSON
        switch testCase {
        case .br:
          status = "observed_model_preference"
          reason = "model_preferred_candidate"
          preference = .string("r_path")
        case .bw:
          status = "observed_model_preference"
          reason = "model_preferred_candidate"
          preference = .string("w_path")
        case .other:
          status = "observed_model_preference"
          reason = "model_preferred_candidate"
          preference = .string("other_path")
        case .paused:
          status = "unavailable"
          reason = "cleanup_unconfirmed"
          preference = .null
        default:
          status = "inconclusive"
          reason = "uncovered_mass_dominates"
          preference = .null
        }
        let response = ResearchSoundJSON.object([
          "schemaVersion": .integer(1), "kind": .string(ResearchSoundContract.kind),
          "purpose": .string(ResearchSoundContract.purpose), "status": .string(status),
          "reason": .string(reason), "modelPreference": preference, "binding": prepared.expected,
          "claimLimits": ResearchSoundContract.falseClaims,
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
