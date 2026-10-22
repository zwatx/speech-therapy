import AVFoundation
import Combine
import Foundation

enum CaptureStartupAvailability: Equatable {
  case available
  case cleanupFailed
}

@MainActor
protocol AudioCapturing: AnyObject {
  /// Read-only startup evidence; retrying a visit cannot clear a failed process scan.
  var startupAvailability: CaptureStartupAvailability { get }
  var cleanupState: CaptureCleanupState { get }
  /// Subscribe on MainActor. Initial delivery and mutations are synchronous there.
  /// Events are serialized; the authoritative getter may advance during reentrant delivery.
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> { get }
  func requestPermission() async -> Bool
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws
  /// Current mono average power in dBFS; unavailable outside active recording.
  func currentRecordingPower() -> Float?
  func stop() throws -> CapturedRecording
  func cancel() throws
  func discard(_ recording: CapturedRecording) throws
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt
  /// Read-only evidence of exact successful removal, including reentrant process recovery.
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt?
}

extension AudioCapturing {
  var startupAvailability: CaptureStartupAvailability { .available }
  func currentRecordingPower() -> Float? { nil }

  /// Producers without retained completion evidence conservatively report no receipt.
  /// This is never permission to clear ownership or substitute idle for removal.
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? { nil }
}

enum AudioCaptureError: LocalizedError, Equatable {
  case couldNotStart
  case couldNotReadRecording
  case couldNotDeleteTemporaryRecording
  case hardwareBusy
  case hardwareCleanupUnconfirmed
  case recordingNotOwned
  case recordingInUse

  var errorDescription: String? {
    switch self {
    case .couldNotStart:
      "The microphone could not start. Check that another app is not using it."
    case .couldNotReadRecording:
      "The recording could not be read. Please record the word again."
    case .couldNotDeleteTemporaryRecording:
      "A temporary recording could not be removed. Recording is disabled until cleanup finishes."
    case .hardwareBusy:
      "Audio is still in use. Finish its cleanup before recording."
    case .hardwareCleanupUnconfirmed:
      "Microphone cleanup is not confirmed. Retry cleanup before recording."
    case .recordingNotOwned:
      "This recording cannot be removed by this recording session."
    case .recordingInUse:
      "This recording is still in use. Finish audio cleanup before removing it."
    }
  }
}

@MainActor
final class SystemAudioCapturer: NSObject, AudioCapturing {
  private let recordingStore: TemporaryRecordingStore
  private let fileOwnership: ProcessAudioFileOwnership
  private let hardwareOwnership: AudioHardwareOwnership
  private let driverFactory: CaptureHardwareDriverFactory
  private let summaryReader: (@MainActor (URL) throws -> CaptureSummary)?
  private let removeFile: @MainActor (URL) throws -> Void
  private var startupCleanupFailed = false
  var startupAvailability: CaptureStartupAvailability {
    startupCleanupFailed ? .cleanupFailed : .available
  }
  private var active: Operation?
  private var ownedURLs: [URL: UUID] = [:]
  private var pendingFileOwners: Set<UUID> = []
  private var fileDeletionFailures: Set<UUID> = []
  private var completedFileCleanups: [UUID: CaptureCleanupReceipt] = [:]
  private var isTransitioning = false
  private let cleanupEvents = PassthroughSubject<(UInt64, CaptureCleanupState), Never>()
  private var cleanupRevision: UInt64 = 0
  private var pendingCleanupEvents: [(UInt64, CaptureCleanupState)] = []
  private var isPublishingCleanup = false
  private(set) var cleanupState = CaptureCleanupState.idle

  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    Deferred { [self] in
      // Register before initial delivery so a retry in the initial subscriber cannot be
      // missed. A late subscriber seeds the committed snapshot and ignores older events
      // still being drained to existing subscribers.
      let revision = cleanupRevision
      let subject = CurrentValueSubject<CaptureCleanupState, Never>(cleanupState)
      let observation = cleanupEvents.sink { eventRevision, state in
        if eventRevision > revision { subject.send(state) }
      }
      return subject.removeDuplicates()
        .handleEvents(receiveCancel: { observation.cancel() })
        .eraseToAnyPublisher()
    }.eraseToAnyPublisher()
  }

  @MainActor
  private final class Operation {
    let lease: AudioHardwareOwnership.Lease
    let url: URL
    let recorderID = UUID()
    var driver: (any CaptureHardwareDriver)?
    var onFinish: (@MainActor (Bool) async -> Void)?
    var cleanupRequested = false
    var originalCleanupError: AudioCaptureError?
    var stopped = false
    var detached = false
    var deactivated = false

    init(
      lease: AudioHardwareOwnership.Lease, url: URL,
      onFinish: @escaping @MainActor (Bool) async -> Void
    ) {
      self.lease = lease
      self.url = url
      self.onFinish = onFinish
    }
  }

  init(
    recordingStore: TemporaryRecordingStore = TemporaryRecordingStore(),
    fileOwnership: ProcessAudioFileOwnership = .shared,
    hardwareOwnership: AudioHardwareOwnership = .shared,
    driverFactory: @escaping CaptureHardwareDriverFactory = {
      AVFoundationCaptureHardwareDriver()
    },
    summaryReader: (@MainActor (URL) throws -> CaptureSummary)? = nil,
    removeFile: (@MainActor (URL) throws -> Void)? = nil
  ) {
    self.recordingStore = recordingStore
    self.fileOwnership = fileOwnership
    self.hardwareOwnership = hardwareOwnership
    self.driverFactory = driverFactory
    self.summaryReader = summaryReader
    self.removeFile = removeFile ?? { try recordingStore.removeRecordingIfPresent(at: $0) }
    super.init()
    do {
      try fileOwnership.cleanStartupOnce(directory: recordingStore.directory) {
        try recordingStore.removeStaleRecordings(excluding: $0)
      }
    } catch {
      startupCleanupFailed = true
    }
  }

  func requestPermission() async -> Bool {
    await withCheckedContinuation { continuation in
      AVAudioApplication.requestRecordPermission { granted in
        continuation.resume(returning: granted)
      }
    }
  }

  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    guard !isTransitioning else { throw AudioCaptureError.hardwareBusy }
    isTransitioning = true
    defer { finishTransition() }
    guard !startupCleanupFailed else {
      throw AudioCaptureError.couldNotDeleteTemporaryRecording
    }
    if let active {
      throw active.originalCleanupError ?? AudioCaptureError.hardwareBusy
    }
    guard pendingFileOwners.isEmpty else {
      throw fileDeletionFailures.isEmpty
        ? AudioCaptureError.recordingInUse : AudioCaptureError.couldNotDeleteTemporaryRecording
    }
    let id = UUID()
    let lease: AudioHardwareOwnership.Lease
    do { lease = try hardwareOwnership.reserve(operationID: id, owner: .capture) } catch {
      throw AudioCaptureError.hardwareBusy
    }
    // All factory/framework work and URL allocation follow the shared reservation.
    let url = recordingStore.makeRecordingURL().standardizedFileURL
    fileOwnership.retain(url, owner: id)
    ownedURLs[url] = id
    let operation = Operation(lease: lease, url: url, onFinish: onFinish)
    active = operation
    hardwareOwnership.registerCaptureRecovery(lease) { [self] in
      retryCleanup(operationID: id)
    }
    let driver = driverFactory()
    operation.driver = driver
    do {
      try driver.configureActivate()
      try driver.createRecorder(url: url, recorderID: operation.recorderID) {
        [weak self] recorderID, success in
        self?.finished(operationID: id, recorderID: recorderID, success: success)
      }
      guard try driver.prepare(), try driver.record() else { throw AudioCaptureError.couldNotStart }
    } catch {
      revoke(operation)
      guard cleanHardware(operation) else {
        throw operation.originalCleanupError ?? AudioCaptureError.hardwareCleanupUnconfirmed
      }
      try removeOwnedFile(url, owner: id)
      throw error
    }
  }

  func currentRecordingPower() -> Float? {
    guard !isTransitioning, let operation = active,
      !operation.cleanupRequested, operation.originalCleanupError == nil,
      !operation.stopped, !operation.detached, !operation.deactivated,
      operation.onFinish != nil, let driver = operation.driver
    else { return nil }
    let power = driver.currentRecordingPower()
    // A synchronous driver read can stop, revoke or replace this operation.
    guard !isTransitioning, active === operation,
      !operation.cleanupRequested, operation.originalCleanupError == nil,
      !operation.stopped, !operation.detached, !operation.deactivated,
      operation.onFinish != nil, let power, power.isFinite
    else { return nil }
    return power
  }

  func stop() throws -> CapturedRecording {
    guard !isTransitioning else { throw AudioCaptureError.hardwareBusy }
    isTransitioning = true
    defer { finishTransition() }
    guard let operation = active else { throw AudioCaptureError.couldNotStart }
    if let error = operation.originalCleanupError { throw error }
    revoke(operation)
    guard cleanHardware(operation) else {
      throw operation.originalCleanupError ?? AudioCaptureError.hardwareCleanupUnconfirmed
    }
    do {
      let summary = try summaryReader?(operation.url) ?? recordedSummary(at: operation.url)
      return CapturedRecording(
        url: operation.url, summary: summary, cleanupOwnerID: operation.lease.operationID)
    } catch {
      try removeOwnedFile(operation.url, owner: operation.lease.operationID)
      throw error
    }
  }

  func cancel() throws {
    guard !isTransitioning else { throw AudioCaptureError.hardwareBusy }
    isTransitioning = true
    defer { finishTransition() }
    // An idle cancel does not discard earlier returned takes.
    guard let operation = active else { return }
    if let error = operation.originalCleanupError { throw error }
    revoke(operation)
    guard cleanHardware(operation) else {
      throw operation.originalCleanupError ?? AudioCaptureError.hardwareCleanupUnconfirmed
    }
    try removeOwnedFile(operation.url, owner: operation.lease.operationID)
  }

  func discard(_ recording: CapturedRecording) throws {
    guard !isTransitioning else { throw AudioCaptureError.recordingInUse }
    isTransitioning = true
    defer { finishTransition() }
    let url = recording.url.standardizedFileURL
    guard let owner = ownedURLs[url] else { throw AudioCaptureError.recordingNotOwned }
    guard active?.lease.operationID != owner else {
      throw active?.originalCleanupError ?? AudioCaptureError.recordingInUse
    }
    // A repeated discard preserves the original negative acknowledgement. Only the
    // explicit exact-owner retry may revisit a failed deletion or borrow refusal.
    guard !pendingFileOwners.contains(owner) else {
      throw fileDeletionFailures.contains(owner)
        ? AudioCaptureError.couldNotDeleteTemporaryRecording : AudioCaptureError.recordingInUse
    }
    try removeOwnedFile(url, owner: owner)
  }

  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    guard !isTransitioning else { return receipt(operationID, .refused) }
    isTransitioning = true
    defer { finishTransition() }
    if let operation = active, operation.lease.operationID == operationID {
      guard operation.cleanupRequested, operation.originalCleanupError != nil else {
        return receipt(operationID, .refused)
      }
      guard cleanHardware(operation) else { return receipt(operationID, .cleanupUnconfirmed) }
      return retryFile(url: operation.url, owner: operationID)
    }
    guard pendingFileOwners.contains(operationID),
      let url = ownedURLs.first(where: { $0.value == operationID })?.key
    else { return receipt(operationID, .refused) }
    return retryFile(url: url, owner: operationID)
  }

  private func receipt(_ id: UUID, _ result: CaptureCleanupReceipt.Result) -> CaptureCleanupReceipt
  {
    CaptureCleanupReceipt(operationID: id, result: result)
  }

  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
    completedFileCleanups[operationID]
  }

  private func retryFile(url: URL, owner: UUID) -> CaptureCleanupReceipt {
    do {
      try removeOwnedFile(url, owner: owner)
      return receipt(owner, .released)
    } catch {
      return receipt(owner, .hardwareReleasedFilesRetained)
    }
  }

  private func revoke(_ operation: Operation) {
    operation.cleanupRequested = true
    operation.onFinish = nil
  }

  /// Flags commit only after a successful stage. A retry resumes at the failed stage.
  private func cleanHardware(_ operation: Operation) -> Bool {
    do {
      if !operation.stopped {
        try operation.driver?.stop()
        operation.stopped = true
      }
      if !operation.detached {
        try operation.driver?.detachRelease()
        operation.detached = true
      }
      if !operation.deactivated {
        try operation.driver?.deactivate()
        operation.deactivated = true
      }
      guard hardwareOwnership.release(operation.lease) else {
        throw AudioCaptureError.hardwareCleanupUnconfirmed
      }
      operation.driver = nil
      active = nil
      return true
    } catch {
      // Retain the first negative acknowledgement until exact release; no hidden retry.
      if operation.originalCleanupError == nil {
        operation.originalCleanupError = .hardwareCleanupUnconfirmed
      }
      hardwareOwnership.markCaptureCleanupBlocked(operation.lease)
      return false
    }
  }

  private func removeOwnedFile(_ url: URL, owner: UUID) throws {
    guard ownedURLs[url] == owner else { throw AudioCaptureError.recordingNotOwned }
    guard fileOwnership.canRemove(url, owner: owner) else {
      markFilePending(owner)
      throw AudioCaptureError.recordingInUse
    }
    do {
      try removeFile(url)
      // No suspension separates permission, deletion and committed ownership removal.
      fileOwnership.didRemove(url, owner: owner)
      ownedURLs.removeValue(forKey: url)
      pendingFileOwners.remove(owner)
      fileDeletionFailures.remove(owner)
      // Commit before finishTransition can publish a failure and an earlier observer retry.
      completedFileCleanups[owner] = receipt(owner, .released)
    } catch {
      fileDeletionFailures.insert(owner)
      markFilePending(owner)
      throw AudioCaptureError.couldNotDeleteTemporaryRecording
    }
  }

  private func markFilePending(_ owner: UUID) {
    pendingFileOwners.insert(owner)
    if !fileOwnership.pendingCleanupOwners.contains(owner) {
      fileOwnership.registerCleanupRecovery(owner: owner) { [self] in
        retryCleanup(operationID: owner).allRequestedFilesRemoved
      }
    }
  }

  private func finished(operationID: UUID, recorderID: UUID, success: Bool) {
    guard let operation = active, operation.lease.operationID == operationID,
      operation.recorderID == recorderID, !operation.cleanupRequested,
      let onFinish = operation.onFinish
    else { return }
    operation.onFinish = nil
    Task { @MainActor [weak self, weak operation] in
      guard let self, let operation, self.active === operation,
        !operation.cleanupRequested
      else { return }
      await onFinish(success)
    }
  }

  /// Commit bookkeeping and the authoritative snapshot before notifying. Reentrant
  /// explicit retry can act on that committed state; its notifications join this drain.
  private func finishTransition() {
    let next = CaptureCleanupState(
      hardwareBlockedOperationID: active?.originalCleanupError == nil
        ? nil : active?.lease.operationID,
      fileBlockedOwnerIDs: pendingFileOwners
    )
    if cleanupState != next {
      cleanupState = next
      cleanupRevision += 1
      pendingCleanupEvents.append((cleanupRevision, next))
    }
    isTransitioning = false
    guard !isPublishingCleanup else { return }
    isPublishingCleanup = true
    defer { isPublishingCleanup = false }
    while !pendingCleanupEvents.isEmpty {
      cleanupEvents.send(pendingCleanupEvents.removeFirst())
    }
  }

  // Live meter values are stale after the recorder's duration limit stops capture.
  // Read the bounded mono clip so manual and automatic completion use the same evidence.
  func recordedSummary(at url: URL) throws -> CaptureSummary {
    let file = try AVAudioFile(forReading: url)
    guard file.length > 0,
      file.length <= 64_000,
      file.processingFormat.channelCount == 1,
      file.processingFormat.sampleRate == 16_000,
      let buffer = AVAudioPCMBuffer(
        pcmFormat: file.processingFormat,
        frameCapacity: AVAudioFrameCount(file.length)
      )
    else { throw AudioCaptureError.couldNotReadRecording }
    let expectedCount = Int(file.length)
    var count = 0
    var squaredAmplitude = 0.0
    var signal: PCM16SignalMeasurements.Accumulator? =
      PCM16CaptureAdmission.admits(
        file: file.fileFormat.streamDescription.pointee,
        processing: file.processingFormat.streamDescription.pointee)
      ? PCM16SignalMeasurements.Accumulator() : nil
    // AVAudioFile can return a successful partial read, even for an uncompressed WAV.
    // Consume the remaining frames before calculating duration and whole-clip power.
    while count < expectedCount {
      let remaining = expectedCount - count
      try file.read(into: buffer, frameCount: AVAudioFrameCount(remaining))
      let readCount = Int(buffer.frameLength)
      guard let samples = buffer.floatChannelData?[0], readCount > 0, readCount <= remaining else {
        throw AudioCaptureError.couldNotReadRecording
      }
      for index in 0..<readCount {
        let sample = Double(samples[index])
        guard sample.isFinite else { throw AudioCaptureError.couldNotReadRecording }
        squaredAmplitude += sample * sample
        if signal != nil {
          if let integer = PCM16CaptureAdmission.integerSample(samples[index]) {
            if signal?.append(integer) != true { signal = nil }
          } else {
            // Keep the established finite RMS scan; unproven conversion is unknown evidence.
            signal = nil
          }
        }
      }
      count += readCount
    }
    let energy = squaredAmplitude / Double(count)
    return CaptureSummary(
      duration: Double(count) / file.processingFormat.sampleRate,
      averagePower: Float(10 * log10(max(energy, 1e-16))),
      pcm16Signal: signal?.measurements().flatMap { $0.sampleCount == count ? $0 : nil }
    )
  }

}

/// Actual saved-file and decoded-buffer admission, independent of requested recorder settings.
enum PCM16CaptureAdmission {
  static func admits(
    file: AudioStreamBasicDescription, processing: AudioStreamBasicDescription
  ) -> Bool {
    let required = kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked
    let excluded =
      kAudioFormatFlagIsFloat | kAudioFormatFlagIsBigEndian
      | kAudioFormatFlagIsAlignedHigh
    return file.mFormatID == kAudioFormatLinearPCM
      && file.mFormatFlags & required == required && file.mFormatFlags & excluded == 0
      && file.mSampleRate == 16_000 && file.mChannelsPerFrame == 1
      && file.mBitsPerChannel == 16 && file.mBytesPerFrame == 2
      && file.mBytesPerPacket == 2 && file.mFramesPerPacket == 1
      && processing.mFormatID == kAudioFormatLinearPCM
      && processing.mFormatFlags & kAudioFormatFlagIsFloat != 0
      && processing.mFormatFlags & kAudioFormatFlagIsBigEndian == 0
      && processing.mBitsPerChannel == 32 && processing.mSampleRate == 16_000
      && processing.mChannelsPerFrame == 1 && processing.mBytesPerFrame == 4
      && processing.mBytesPerPacket == 4 && processing.mFramesPerPacket == 1
  }

  static func integerSample(_ sample: Float) -> Int16? {
    let scaled = Double(sample) * 32768
    guard scaled.isFinite, scaled >= -32768, scaled <= 32767,
      scaled.rounded(.towardZero) == scaled
    else { return nil }
    let value = Int16(scaled)
    guard Float(value) / 32768 == sample else { return nil }
    return value
  }
}
