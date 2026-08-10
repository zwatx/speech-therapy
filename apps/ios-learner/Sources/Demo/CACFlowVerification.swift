#if CAC_FLOW_UI_VERIFICATION && targetEnvironment(simulator)
  import Combine
  import Foundation
  import UIKit

  /// Simulator UI verification only. Compiled solely when the build defines
  /// CAC_FLOW_UI_VERIFICATION (never set in project.yml), and active only with
  /// CADENCE_CAC_FLOW_VERIFICATION=1. Production capture ownership, temporary files and
  /// cleanup stay real; the microphone, permission prompt and speaker are never touched.
  @MainActor
  enum CACFlowVerification {
    struct Resources {
      let files: ProcessAudioFileOwnership
      let facePreview: FaceGuideModel
      let makeSession: @MainActor (PracticeSound) -> DirectPracticeSession
    }

    static var isRequested: Bool {
      ProcessInfo.processInfo.environment["CADENCE_CAC_FLOW_VERIFICATION"] == "1"
    }

    static func requested() -> Resources? {
      guard isRequested else { return nil }
      let files = ProcessAudioFileOwnership()
      let hardware = AudioHardwareOwnership()
      let directory = FileManager.default.temporaryDirectory
        .appendingPathComponent("cadence-cac-flow-\(UUID().uuidString)", isDirectory: true)
      try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      let store = TemporaryRecordingStore(directory: directory)
      let facePreview = FaceGuideModel(
        hardware: InertFaceHardware(), recovery: FaceGuideRecovery(), initialScene: .inactive)
      let quietAudio = ProcessInfo.processInfo.environment["CADENCE_CAC_QUIET_AUDIO"] == "1"
      return Resources(files: files, facePreview: facePreview) { sound in
        let capturer = SystemAudioCapturer(
          recordingStore: store, fileOwnership: files, hardwareOwnership: hardware,
          driverFactory: { InertDriver() },
          summaryReader: { _ in CaptureSummary(duration: 1, averagePower: quietAudio ? -70 : -20) })
        return DirectPracticeSession(
          sound: sound, capturer: PermissionGranted(capturer), player: SilentPlayer(),
          history: nil, wordRecognizer: CACDemoNoWordCheck(), spokenWord: SilentSpokenWord(),
          cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
      }
    }

    /// The real inline layout with inert camera ownership. The surface labels itself as
    /// verification content; no camera, ARSession, microphone or depth sensor is used here.
    @MainActor
    private final class InertFaceHardware: FaceGuideHardware {
      var isSupported: Bool { true }
      var permission: FaceGuidePermission { .authorized }
      func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
        completion(true)
      }
      func makeDriver() -> any FaceGuideDriver { InertFaceDriver() }
    }

    @MainActor
    private final class InertFaceDriver: FaceGuideDriver {
      private let preview = UIView()
      private var sampleTask: Task<Void, Never>?
      private var running = false

      init() {
        preview.backgroundColor = .darkGray
        preview.accessibilityLabel = "Camera-free layout verification"
        let label = UILabel()
        label.text = "Camera-free layout verification"
        label.textColor = .white
        label.font = .preferredFont(forTextStyle: .footnote)
        label.textAlignment = .center
        label.numberOfLines = 0
        label.translatesAutoresizingMaskIntoConstraints = false
        preview.addSubview(label)
        NSLayoutConstraint.activate([
          label.centerXAnchor.constraint(equalTo: preview.centerXAnchor),
          label.centerYAnchor.constraint(equalTo: preview.centerYAnchor),
          label.widthAnchor.constraint(lessThanOrEqualTo: preview.widthAnchor, constant: -24),
        ])
      }

      var surface: UIView? { preview }
      func start(events: @escaping @MainActor (FaceGuideEvent) -> Void) {
        running = true
        sampleTask = Task { @MainActor [weak self] in
          guard let self, self.running, !Task.isCancelled else { return }
          // Authored UI sample only, never evidence of live face tracking or pronunciation.
          events(
            .frame(
              FaceGuideFrame(
                timestamp: ProcessInfo.processInfo.systemUptime, faceTracked: true,
                depthCaptured: false, jawOpen: 0.2, mouthPucker: 0.1)))
        }
      }
      func stop() {
        running = false
        sampleTask?.cancel()
        sampleTask = nil
        preview.removeFromSuperview()
      }
    }

    @MainActor
    private final class PermissionGranted: AudioCapturing {
      let underlying: SystemAudioCapturer
      init(_ underlying: SystemAudioCapturer) { self.underlying = underlying }
      var startupAvailability: CaptureStartupAvailability { underlying.startupAvailability }
      var cleanupState: CaptureCleanupState { underlying.cleanupState }
      var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
        underlying.cleanupStatePublisher
      }
      func requestPermission() async -> Bool { true }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        try underlying.start(onFinish: onFinish)
      }
      func currentRecordingPower() -> Float? { underlying.currentRecordingPower() }
      func stop() throws -> CapturedRecording { try underlying.stop() }
      func cancel() throws { try underlying.cancel() }
      func discard(_ recording: CapturedRecording) throws { try underlying.discard(recording) }
      func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
        underlying.retryCleanup(operationID: operationID)
      }
      func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
        underlying.completedFileCleanup(operationID: operationID)
      }
    }

    /// Writes a placeholder file; no audio session or recorder is created.
    @MainActor
    private final class InertDriver: CaptureHardwareDriver {
      func configureActivate() throws {}
      func createRecorder(
        url: URL, recorderID: UUID,
        onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
      ) throws {
        try Data([1, 2, 3]).write(to: url)
      }
      func prepare() throws -> Bool { true }
      func record() throws -> Bool { true }
      func currentRecordingPower() -> Float? { -24 }
      func stop() throws {}
      func detachRelease() throws {}
      func deactivate() throws {}
    }

    /// Exposes the ordinary ready-state affordance without ever creating a speaker.
    /// Requests fail explicitly; verification never pretends audio was played.
    @MainActor
    private final class SilentSpokenWord: PracticeSpokenWordSpeaking {
      var state: PracticeSpokenWordState { .idle }
      var statePublisher: AnyPublisher<PracticeSpokenWordState, Never> {
        Just(.idle).eraseToAnyPublisher()
      }
      func start(_ operation: PracticeSpokenWordOperation) async throws {
        throw PracticeSpokenWordError.unavailable
      }
      func requestStop(id: UUID) -> PracticeSpokenWordCleanup? { nil }
      func retryCleanup(id: UUID) -> PracticeSpokenWordCleanup? { nil }
      func completedCleanupRetry(id: UUID) -> PracticeSpokenWordReceipt? { nil }
    }

    /// Replay is unavailable here; the session reports that like any playback failure.
    @MainActor
    private final class SilentPlayer: AcknowledgedPracticeAudioPlaying {
      enum Unavailable: LocalizedError {
        case playback
        var errorDescription: String? { "Playback isn’t available in this verification build." }
      }
      var state: PracticePlaybackRuntimeState { .idle }
      var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
        Just(.idle).eraseToAnyPublisher()
      }
      func play(
        id: UUID, url: URL,
        onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
      ) async throws {
        throw Unavailable.playback
      }
      func requestStop(id: UUID) -> PracticePlaybackCleanup? { nil }
      func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { nil }
    }
  }
#endif
