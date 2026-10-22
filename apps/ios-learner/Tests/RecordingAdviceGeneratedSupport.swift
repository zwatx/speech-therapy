import Combine
import Foundation

@testable import CadenceLearner

/// Task-local generated component dependencies. Marker files are never decoded or played.
@MainActor
final class RecordingAdviceGeneratedCapture: AudioCapturing {
  let directory: URL
  let files: ProcessAudioFileOwnership
  var summaries: [CaptureSummary]
  var permissionGranted = true
  var failStart = false
  var duringStop: (@MainActor () -> Void)?
  private(set) var permissionCount = 0
  private(set) var startCount = 0
  private(set) var discardCount = 0
  private(set) var recordings: [CapturedRecording] = []
  private var active: CapturedRecording?
  private var receipts: [UUID: CaptureCleanupReceipt] = [:]
  private let state = CurrentValueSubject<CaptureCleanupState, Never>(.idle)
  var cleanupState: CaptureCleanupState { state.value }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    state.eraseToAnyPublisher()
  }

  init(directory: URL, files: ProcessAudioFileOwnership, summaries: [CaptureSummary]) {
    self.directory = directory
    self.files = files
    self.summaries = summaries
  }
  func requestPermission() async -> Bool {
    permissionCount += 1
    return permissionGranted
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    guard !failStart, active == nil, startCount < summaries.count else {
      throw AudioCaptureError.couldNotStart
    }
    let owner = UUID()
    let url = directory.appendingPathComponent("generated-\(owner.uuidString).wav")
    try Data("Generated marker, never audio input".utf8).write(to: url)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    files.retain(url, owner: owner)
    let recording = CapturedRecording(
      url: url, summary: summaries[startCount], cleanupOwnerID: owner)
    active = recording
    recordings.append(recording)
    startCount += 1
  }
  func stop() throws -> CapturedRecording {
    guard let recording = active else { throw AudioCaptureError.couldNotStart }
    active = nil
    duringStop?()
    return recording
  }
  func cancel() throws {
    guard let recording = active else { return }
    active = nil
    try discard(recording)
  }
  func discard(_ recording: CapturedRecording) throws {
    guard recordings.contains(recording), let owner = recording.cleanupOwnerID,
      files.canRemove(recording.url, owner: owner)
    else { throw AudioCaptureError.recordingNotOwned }
    if FileManager.default.fileExists(atPath: recording.url.path) {
      try FileManager.default.removeItem(at: recording.url)
      discardCount += 1
    }
    files.didRemove(recording.url, owner: owner)
    receipts[owner] = .init(operationID: owner, result: .released)
  }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    receipts[operationID] ?? .init(operationID: operationID, result: .refused)
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? { receipts[operationID] }
}

@MainActor
final class RecordingAdviceGeneratedRecognizer: LocalWordRecognizing {
  private(set) var checkCount = 0
  private(set) var cancelCount = 0
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    checkCount += 1
    return .init(request: request, status: .unavailable, cleanupConfirmed: true)
  }
  func cancel(operationID: UUID) { cancelCount += 1 }
}

@MainActor
final class RecordingAdviceGeneratedPlayer: AcknowledgedPracticeAudioPlaying {
  private let facade: SystemAcknowledgedPracticeAudioPlayer
  private(set) var playCount = 0
  var state: PracticePlaybackRuntimeState { facade.state }
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> { facade.statePublisher }
  init(files: ProcessAudioFileOwnership, hardware: AudioHardwareOwnership) {
    facade = SystemAcknowledgedPracticeAudioPlayer(ownership: hardware, fileOwnership: files) {
      operation, finished in RecordingAdviceSilentDriver(operation: operation, finished: finished)
    }
  }
  func play(
    id: UUID, url: URL,
    onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws {
    playCount += 1
    try await facade.play(id: id, url: url, onFinish: onFinish)
  }
  func requestStop(id: UUID) -> PracticePlaybackCleanup? { facade.requestStop(id: id) }
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { facade.retryCleanup(id: id) }
  func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
    facade.completedCleanupRetry(id: id)
  }
}

private final class RecordingAdviceSilentDriver: PracticePlaybackDriver {
  let operation: PracticePlaybackOperation
  let finished: @Sendable (PracticePlaybackOperation, Bool) -> Void
  init(
    operation: PracticePlaybackOperation,
    finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) {
    self.operation = operation
    self.finished = finished
  }
  func activate() throws {}
  func prepare() throws -> Bool { true }
  func play() throws -> Bool {
    finished(operation, true)
    return true
  }
  func stop() throws {}
  func releasePlaybackResources() throws {}
  func deactivate() throws {}
}

@MainActor
final class RecordingAdviceNoCameraPermission: PracticeMirrorPermissionProviding {
  let isSupported = false
  let status = PracticeMirrorPermission.denied
  private(set) var requests = 0
  func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
    requests += 1
    completion(false)
  }
}

@MainActor
final class RecordingAdviceGeneratedFixture {
  let directory: URL
  let files = ProcessAudioFileOwnership()
  let hardware = AudioHardwareOwnership()
  let cameraPermission = RecordingAdviceNoCameraPermission()
  let cameraRecovery = ProcessPracticeMirrorRecovery()
  let capture: RecordingAdviceGeneratedCapture
  let player: RecordingAdviceGeneratedPlayer
  let recognizer = RecordingAdviceGeneratedRecognizer()
  let history: PracticeParticipationStore
  let session: DirectPracticeSession

  static func summary(_ samples: [Int16]?, power: Float = -20, duration: Double = 1)
    -> CaptureSummary
  {
    var accumulator = PCM16SignalMeasurements.Accumulator()
    for sample in samples ?? [] { accumulator.append(sample) }
    return .init(duration: duration, averagePower: power, pcm16Signal: accumulator.measurements())
  }

  init(managedForGuided: Bool = false) throws {
    directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
      .appendingPathComponent("recording-advice-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(
      at: directory, withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])
    capture = RecordingAdviceGeneratedCapture(
      directory: directory, files: files,
      summaries: [
        Self.summary([0, 0], power: -160), Self.summary([-32768, 32767]),
        Self.summary(nil, power: -60), Self.summary([1, -1]),
      ])
    player = RecordingAdviceGeneratedPlayer(files: files, hardware: hardware)
    history = PracticeParticipationStore(fileURL: directory.appendingPathComponent("history.json"))
    let runtime = PracticeMirrorRuntime(recovery: cameraRecovery) { _ in
      fatalError("Generated component must never construct a camera driver")
    }
    let mirror = DirectPracticeMirror(
      permission: cameraPermission, runtime: runtime,
      recovery: cameraRecovery, initialScene: .active)
    session = DirectPracticeSession(
      capturer: capture, player: player, mirror: mirror,
      history: history, managedForGuided: managedForGuided, wordRecognizer: recognizer,
      cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
  }

  /// The positive end receipt and owned file state are required before removing this directory.
  func finish() async throws -> Bool {
    guard await session.end(), session.phase == .ended, files.protectedURLs.isEmpty,
      files.pendingCleanupOwners.isEmpty, hardware.currentLease == nil,
      cameraRecovery.owner == nil,
      !capture.recordings.contains(where: { FileManager.default.fileExists(atPath: $0.url.path) })
    else { return false }
    try FileManager.default.removeItem(at: directory)
    return !FileManager.default.fileExists(atPath: directory.path)
  }
}
