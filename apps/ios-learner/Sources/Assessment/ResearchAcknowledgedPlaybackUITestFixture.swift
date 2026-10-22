#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  /// Explicit generated UI injection only. Startup/cleanup acknowledgements come from the
  /// real runtime with a non-framework driver; they establish no physical audio output.
  @MainActor
  final class ResearchAcknowledgedPlaybackUITestFixture: AcknowledgedPracticeAudioPlaying {
    enum Completion: Sendable { case immediate, explicitStop }

    private let player: SystemAcknowledgedPracticeAudioPlayer

    var state: PracticePlaybackRuntimeState { player.state }
    var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
      player.statePublisher
    }

    init(
      completion: Completion, ownership: AudioHardwareOwnership,
      fileOwnership: ProcessAudioFileOwnership
    ) {
      let finishesOnPlay = completion == .immediate
      // The generated capturer and player use the same isolated ownership pair.
      player = SystemAcknowledgedPracticeAudioPlayer(
        ownership: ownership, fileOwnership: fileOwnership
      ) { operation, finished in
        ResearchGeneratedPlaybackDriver(
          operation: operation, finishesOnPlay: finishesOnPlay, finished: finished)
      }
    }

    func play(
      id: UUID, url: URL,
      onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
    ) async throws {
      try await player.play(id: id, url: url, onFinish: onFinish)
    }

    @discardableResult
    func requestStop(id: UUID) -> PracticePlaybackCleanup? { player.requestStop(id: id) }

    func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { player.retryCleanup(id: id) }

    func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
      player.completedCleanupRetry(id: id)
    }
  }

  /// Constructed/used only on the runtime's queue. All fields are immutable; the driver
  /// never opens the supplied URL, creates framework resources or invokes a sensor/model.
  private final class ResearchGeneratedPlaybackDriver: PracticePlaybackDriver {
    private let operation: PracticePlaybackOperation
    private let finishesOnPlay: Bool
    private let finished: @Sendable (PracticePlaybackOperation, Bool) -> Void

    init(
      operation: PracticePlaybackOperation, finishesOnPlay: Bool,
      finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
    ) {
      self.operation = operation
      self.finishesOnPlay = finishesOnPlay
      self.finished = finished
    }

    func activate() throws {}
    func prepare() throws -> Bool { true }
    func play() throws -> Bool {
      // The runtime queues this exact-identity event after its actual controlled start,
      // and delivers natural completion only after acknowledged resource cleanup.
      if finishesOnPlay { finished(operation, true) }
      return true
    }
    func stop() throws {}
    func releasePlaybackResources() throws {}
    func deactivate() throws {}
  }
  /// Exact generated-file producer shared by the fixture facades. No AV/session calls.
  /// A process-held failed cleanup callback retains this producer, never a second owner.
  @MainActor
  final class ResearchGeneratedCaptureFileOwnership {
    private let hardware: AudioHardwareOwnership
    private let files: ProcessAudioFileOwnership
    private let store: TemporaryRecordingStore
    private var owners: [URL: UUID] = [:]
    private var pending: [UUID: AudioCaptureError] = [:]
    private var persistentFailures: Set<UUID> = []
    private var completed: [UUID: CaptureCleanupReceipt] = [:]
    private var activeLease: AudioHardwareOwnership.Lease?
    private var activeURL: URL?
    private var hardwareCleanupRequested = false
    private let events = PassthroughSubject<(UInt64, CaptureCleanupState), Never>()
    private var revision: UInt64 = 0
    private var queue: [(UInt64, CaptureCleanupState)] = []
    private var publishing = false
    private(set) var cleanupState = CaptureCleanupState.idle
    let directory: URL

    init(hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership) {
      self.hardware = hardware
      self.files = files
      directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-capture-\(UUID())", isDirectory: true)
      store = TemporaryRecordingStore(directory: directory)
    }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      Deferred { [self] in
        let seededRevision = revision
        let subject = CurrentValueSubject<CaptureCleanupState, Never>(cleanupState)
        let observation = events.sink { eventRevision, state in
          if eventRevision > seededRevision { subject.send(state) }
        }
        return subject.removeDuplicates()
          .handleEvents(receiveCancel: { observation.cancel() }).eraseToAnyPublisher()
      }.eraseToAnyPublisher()
    }
    var retainedFileCount: Int { owners.count }
    func owner(of url: URL) -> UUID? { owners[url] }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      completed[operationID]
    }

    /// Reserve before file creation. The lease's immutable operation ID is the file owner.
    func begin(_ url: URL) throws {
      guard activeLease == nil, pending.isEmpty, owners[url] == nil else {
        throw AudioCaptureError.couldNotStart
      }
      let id = UUID()
      let lease: AudioHardwareOwnership.Lease
      do { lease = try hardware.reserve(operationID: id, owner: .capture) } catch {
        throw AudioCaptureError.hardwareBusy
      }
      activeLease = lease
      activeURL = url
      hardwareCleanupRequested = false
      owners[url] = id
      files.retain(url, owner: id)
      precondition(
        hardware.registerCaptureRecovery(lease) { [self] in retryCleanup(operationID: id) })
      do {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      } catch {
        try? cancel(url)
        throw error
      }
    }
    func stop(_ url: URL) throws -> UUID {
      guard activeURL == url, let owner = owners[url] else {
        throw AudioCaptureError.couldNotReadRecording
      }
      try releaseActiveHardware()
      return owner
    }
    func cancel(_ url: URL, forcedError: AudioCaptureError? = nil) throws {
      guard activeURL == url else { return }
      try releaseActiveHardware()
      try remove(url, forcedError: forcedError)
    }
    private func releaseActiveHardware() throws {
      guard let lease = activeLease else { return }
      hardwareCleanupRequested = true
      guard hardware.release(lease) else {
        _ = hardware.markCaptureCleanupBlocked(lease)
        publish()
        throw AudioCaptureError.hardwareCleanupUnconfirmed
      }
      activeLease = nil
      activeURL = nil
      hardwareCleanupRequested = false
    }

    /// Repeated discard is never a retry, including a borrow that has since finished.
    func remove(
      _ url: URL, forcedError: AudioCaptureError? = nil, persistentFailure: Bool = false
    ) throws {
      guard let owner = owners[url] else { throw AudioCaptureError.recordingNotOwned }
      guard activeURL != url else { throw AudioCaptureError.recordingInUse }
      if let error = pending[owner] { throw error }
      try attemptRemoval(
        url, owner: owner, forcedError: forcedError, persistentFailure: persistentFailure)
    }
    private func attemptRemoval(
      _ url: URL, owner: UUID, forcedError: AudioCaptureError? = nil,
      persistentFailure: Bool = false
    ) throws {
      let error: AudioCaptureError?
      if !files.canRemove(url, owner: owner) {
        error = .recordingInUse
      } else if let forcedError {
        error = forcedError
      } else if persistentFailures.contains(owner) {
        error = pending[owner] ?? .couldNotDeleteTemporaryRecording
      } else {
        do {
          try store.removeRecordingIfPresent(at: url)
          files.didRemove(url, owner: owner)
          owners.removeValue(forKey: url)
          pending.removeValue(forKey: owner)
          persistentFailures.remove(owner)
          completed[owner] = .init(operationID: owner, result: .released)
          // All completion evidence commits before synchronous state notification.
          publish()
          return
        } catch {
          let failure = AudioCaptureError.couldNotDeleteTemporaryRecording
          retainFailure(url, owner: owner, error: failure, persistent: false)
          throw failure
        }
      }
      let failure = error ?? .couldNotDeleteTemporaryRecording
      retainFailure(url, owner: owner, error: failure, persistent: persistentFailure)
      throw failure
    }
    private func retainFailure(_ url: URL, owner: UUID, error: AudioCaptureError, persistent: Bool)
    {
      pending[owner] = error
      if persistent { persistentFailures.insert(owner) }
      _ = files.registerCleanupRecovery(owner: owner) { [self] in
        retryCleanup(operationID: owner).allRequestedFilesRemoved
      }
      publish()
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      if let lease = activeLease, lease.operationID == operationID {
        guard hardwareCleanupRequested else {
          return .init(operationID: operationID, result: .refused)
        }
        let url = activeURL
        do {
          try releaseActiveHardware()
          if let url { try remove(url) }
        } catch {
          return .init(
            operationID: operationID,
            result: activeLease == nil ? .hardwareReleasedFilesRetained : .cleanupUnconfirmed)
        }
        return .init(operationID: operationID, result: .released)
      }
      guard pending[operationID] != nil,
        let url = owners.first(where: { $0.value == operationID })?.key
      else { return .init(operationID: operationID, result: .refused) }
      do {
        try attemptRemoval(url, owner: operationID)
        return .init(operationID: operationID, result: .released)
      } catch {
        return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
      }
    }
    private func publish() {
      let state = CaptureCleanupState(
        hardwareBlockedOperationID: hardwareCleanupRequested ? activeLease?.operationID : nil,
        fileBlockedOwnerIDs: Set(pending.keys))
      guard state != cleanupState else { return }
      cleanupState = state
      revision += 1
      queue.append((revision, state))
      guard !publishing else { return }
      publishing = true
      defer { publishing = false }
      while !queue.isEmpty {
        let event = queue.removeFirst()
        events.send(event)
      }
    }
  }

  @MainActor
  final class ResearchGeneratedExampleRemoval {
    private let failFirst: Bool
    private var failed = false
    init(failFirst: Bool) { self.failFirst = failFirst }
    func remove(_ url: URL) throws {
      if failFirst, !failed {
        failed = true
        throw ResearchPracticeExampleError.cleanupFailed
      }
      try TemporaryRecordingStore().removeRecordingIfPresent(at: url)
    }
  }
#endif
