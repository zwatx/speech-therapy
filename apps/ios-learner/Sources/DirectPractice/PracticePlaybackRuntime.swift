import Combine
import Dispatch
import Foundation

struct PracticePlaybackOperation: Equatable, Sendable {
  let id: UUID
  let url: URL
}

/// A synchronous driver is used only on its runtime's dedicated queue. Construction must not
/// activate hardware; a throwing factory must discard all partially constructed resources.
/// The callback reports its captured operation identity and may arrive on any queue.
protocol PracticePlaybackDriver: AnyObject {
  func activate() throws
  func prepare() throws -> Bool
  func play() throws -> Bool
  func stop() throws
  /// Detach delegates and release every playback resource before returning successfully.
  func releasePlaybackResources() throws
  func deactivate() throws
}

typealias PracticePlaybackDriverFactory =
  @Sendable (
    PracticePlaybackOperation, @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) throws
  -> any PracticePlaybackDriver

@MainActor
final class AudioHardwareOwnership {
  static let shared = AudioHardwareOwnership()

  enum Owner: Equatable, Sendable { case playback, capture, spokenWord }

  struct Lease: Equatable, Sendable {
    fileprivate let token: UUID
    let operationID: UUID
    let owner: Owner
  }

  struct Busy: Error, Equatable, Sendable { let lease: Lease }

  private(set) var currentLease: Lease?
  private var playbackRecovery: (@MainActor () -> PracticePlaybackCleanup?)?
  private var captureRecovery: (@MainActor () -> CaptureCleanupReceipt)?
  private var spokenWordRecovery: (@MainActor () async -> PracticeSpokenWordReceipt?)?
  private(set) var blockedSpokenWordOperationID: UUID?
  private(set) var blockedCaptureOperationID: UUID?
  private(set) var blockedPlaybackOperationID: UUID?

  @discardableResult
  func registerCaptureRecovery(
    _ lease: Lease, retry: @escaping @MainActor () -> CaptureCleanupReceipt
  ) -> Bool {
    guard currentLease == lease, lease.owner == .capture, captureRecovery == nil else {
      return false
    }
    captureRecovery = retry
    return true
  }

  @discardableResult
  func markCaptureCleanupBlocked(_ lease: Lease) -> Bool {
    guard currentLease == lease, lease.owner == .capture else { return false }
    blockedCaptureOperationID = lease.operationID
    return true
  }

  /// Exact identity and a genuine failed-cleanup stage are required. This never implicitly
  /// stops an active recorder. The callback owns the retained resources until exact release.
  func retryCaptureCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    guard let lease = currentLease, lease.owner == .capture,
      lease.operationID == operationID, blockedCaptureOperationID == operationID,
      let captureRecovery
    else { return CaptureCleanupReceipt(operationID: operationID, result: .refused) }
    return captureRecovery()
  }

  /// Keep failed cleanup reachable even when the original view releases its facade.
  /// Register before queue work; the exact lease is the only authority for recovery.
  @discardableResult
  func registerPlaybackRecovery(
    _ lease: Lease, retry: @escaping @MainActor () -> PracticePlaybackCleanup?
  ) -> Bool {
    guard currentLease == lease, lease.owner == .playback else { return false }
    playbackRecovery = retry
    return true
  }

  @discardableResult
  func markPlaybackCleanupBlocked(_ lease: Lease) -> Bool {
    guard currentLease == lease, lease.owner == .playback else { return false }
    blockedPlaybackOperationID = lease.operationID
    return true
  }

  /// Explicit recovery only. Preparing/playing operations refuse this retry themselves.
  func retryPlaybackCleanup() -> PracticePlaybackCleanup? { playbackRecovery?() }

  @discardableResult
  func registerSpokenWordRecovery(
    _ lease: Lease, retry: @escaping @MainActor () async -> PracticeSpokenWordReceipt?
  ) -> Bool {
    guard currentLease == lease, lease.owner == .spokenWord else { return false }
    spokenWordRecovery = retry
    return true
  }

  @discardableResult
  func markSpokenWordCleanupBlocked(_ lease: Lease) -> Bool {
    guard currentLease == lease, lease.owner == .spokenWord else { return false }
    blockedSpokenWordOperationID = lease.operationID
    return true
  }

  func retrySpokenWordCleanup() async -> PracticeSpokenWordReceipt? { await spokenWordRecovery?() }

  func reserve(operationID: UUID, owner: Owner) throws -> Lease {
    if let currentLease { throw Busy(lease: currentLease) }
    let lease = Lease(token: UUID(), operationID: operationID, owner: owner)
    currentLease = lease
    return lease
  }

  /// Capture integration must call this only after stop, resource release and deactivation.
  @discardableResult
  func release(_ lease: Lease) -> Bool {
    guard currentLease == lease else { return false }
    currentLease = nil
    playbackRecovery = nil
    captureRecovery = nil
    spokenWordRecovery = nil
    blockedSpokenWordOperationID = nil
    blockedCaptureOperationID = nil
    blockedPlaybackOperationID = nil
    return true
  }
}

enum PracticePlaybackRuntimeState: Equatable, Sendable {
  case idle
  case preparing(PracticePlaybackOperation)
  case playing(PracticePlaybackOperation)
  case stopping(PracticePlaybackOperation)
  case cleanupBlocked(PracticePlaybackOperation)
}

enum PracticePlaybackRuntimeError: Error, Equatable, Sendable {
  case busy
  case reusedOperationID
  case cancelled(PracticePlaybackOperation)
  case couldNotStart(PracticePlaybackOperation)
  case cleanupUnconfirmed(PracticePlaybackOperation)
}

struct PracticePlaybackCleanupReceipt: Equatable, Sendable {
  let operation: PracticePlaybackOperation
  let result: Result
  enum Result: Equatable, Sendable { case released, cleanupUnconfirmed }
}

/// Identity-stable acknowledgement. Cancelling an awaiting task does not cancel owned cleanup.
@MainActor
final class PracticePlaybackCleanup {
  let operation: PracticePlaybackOperation
  private(set) var receipt: PracticePlaybackCleanupReceipt?
  private var waiters: [CheckedContinuation<PracticePlaybackCleanupReceipt, Never>] = []

  fileprivate init(operation: PracticePlaybackOperation) { self.operation = operation }

  func value() async -> PracticePlaybackCleanupReceipt {
    if let receipt { return receipt }
    return await withCheckedContinuation { waiters.append($0) }
  }

  fileprivate func resolve(_ receipt: PracticePlaybackCleanupReceipt) {
    guard self.receipt == nil else { return }
    self.receipt = receipt
    let waiting = waiters
    waiters.removeAll()
    for waiter in waiting { waiter.resume(returning: receipt) }
  }
}

/// Only this cancellation bit crosses queues. The lock is never held during a driver call or actor hop.
private final class PlaybackCancellation: @unchecked Sendable {
  private let lock = NSLock()
  private var revoked = false

  func cancel() { lock.withLock { revoked = true } }
  var isCancelled: Bool { lock.withLock { revoked } }

  /// The play linearization point: cancellation after this returns true may still allow sound.
  func commitPlay() -> Bool { lock.withLock { !revoked } }
}

private enum PlaybackWorkerReport: Sendable {
  case started
  case stopping
  case cleaned(PracticePlaybackCleanupReceipt.Result, PlaybackEnd)
}

private enum PlaybackEnd: Sendable {
  case cancelled
  case couldNotStart
  case finished(Bool)
}

/// Unchecked bridge proof: factory, driver, cleanup flags and report chain are accessed ONLY
/// on queue. The only cross-queue mutable object is PlaybackCancellation (independently locked).
/// Operation/report values are immutable Sendable; receiver is MainActor-isolated. No driver
/// or playback reference escapes. Enqueued work and receiver retain ownership through cleanup.
private final class PlaybackWorker: @unchecked Sendable {
  private let queue = DispatchQueue(label: "com.cadence.practice-playback", qos: .userInitiated)
  private let operation: PracticePlaybackOperation
  private let cancellation: PlaybackCancellation
  private let factory: PracticePlaybackDriverFactory
  private let receiver: @MainActor @Sendable (PlaybackWorkerReport) -> Void
  private var driver: (any PracticePlaybackDriver)?
  private var cleanupAttempted = false
  private var stopped = false
  private var resourcesReleased = false
  private var end: PlaybackEnd = .cancelled
  private var lastReport: Task<Void, Never>?

  init(
    operation: PracticePlaybackOperation, cancellation: PlaybackCancellation,
    factory: @escaping PracticePlaybackDriverFactory,
    receiver: @escaping @MainActor @Sendable (PlaybackWorkerReport) -> Void
  ) {
    self.operation = operation
    self.cancellation = cancellation
    self.factory = factory
    self.receiver = receiver
  }

  func start() { queue.async { self.startOnQueue() } }
  func requestStop() { queue.async { self.cleanOnQueue(retry: false) } }
  func retryCleanup() { queue.async { self.cleanOnQueue(retry: true) } }

  private func report(_ value: PlaybackWorkerReport) {
    // Explicit chaining preserves started -> stopping -> cleaned even if MainActor is busy.
    let previous = lastReport
    let receiver = receiver
    lastReport = Task { @MainActor in
      await previous?.value
      receiver(value)
    }
  }

  private func startOnQueue() {
    do {
      guard !cancellation.isCancelled else { return cleanOnQueue(retry: false) }
      driver = try factory(operation) { [weak self] reportedOperation, success in
        guard let self else { return }
        self.queue.async { self.finishOnQueue(operation: reportedOperation, success: success) }
      }
      guard !cancellation.isCancelled else { return cleanOnQueue(retry: false) }
      try driver?.activate()
      guard !cancellation.isCancelled else { return cleanOnQueue(retry: false) }
      guard try driver?.prepare() == true else { throw DriverStartFailure.failed }
      guard !cancellation.isCancelled, cancellation.commitPlay() else {
        return cleanOnQueue(retry: false)
      }
      guard try driver?.play() == true else { throw DriverStartFailure.failed }
      guard !cancellation.isCancelled else { return cleanOnQueue(retry: false) }
      report(.started)
    } catch {
      end = cancellation.isCancelled ? .cancelled : .couldNotStart
      cleanOnQueue(retry: false)
    }
  }

  private func finishOnQueue(operation: PracticePlaybackOperation, success: Bool) {
    guard operation == self.operation, !cleanupAttempted else { return }
    end = cancellation.isCancelled ? .cancelled : .finished(success)
    cleanOnQueue(retry: false)
  }

  private func cleanOnQueue(retry: Bool) {
    guard retry || !cleanupAttempted else { return }
    cleanupAttempted = true
    report(.stopping)
    do {
      if let driver {
        if !stopped {
          try driver.stop()
          stopped = true
        }
        if !resourcesReleased {
          try driver.releasePlaybackResources()
          resourcesReleased = true
        }
        try driver.deactivate()
      }
      driver = nil
      report(.cleaned(.released, end))
    } catch {
      report(.cleaned(.cleanupUnconfirmed, end))
    }
  }

  private enum DriverStartFailure: Error { case failed }
}

/// MainActor UI facade. It creates no default driver and performs no framework/audio work.
/// It borrows the exact media before queued work and releases that borrow only after actual
/// cleanup succeeds. Producers retain deletion ownership until their own confirmed removal.
@MainActor
final class PracticePlaybackRuntime: ObservableObject {
  @Published private(set) var state: PracticePlaybackRuntimeState = .idle
  private var pendingStates: [PracticePlaybackRuntimeState] = []
  private var latestState: PracticePlaybackRuntimeState = .idle
  private var isPublishingState = false
  private let ownership: AudioHardwareOwnership
  private let fileOwnership: ProcessAudioFileOwnership
  private let factory: PracticePlaybackDriverFactory
  private var usedIDs: Set<UUID> = []
  private var current: Operation?
  private var lastReleasedCleanup: PracticePlaybackCleanup?
  private var lastCompletedRetry: PracticePlaybackCleanupReceipt?

  @MainActor
  private final class Operation {
    let identity: PracticePlaybackOperation
    let lease: AudioHardwareOwnership.Lease
    let cancellation = PlaybackCancellation()
    let cleanup: PracticePlaybackCleanup
    var stopRequested = false
    var retry: PracticePlaybackCleanup?
    var worker: PlaybackWorker?
    var start: CheckedContinuation<Void, Error>?
    var onFinished: (@MainActor (PracticePlaybackOperation, Bool) -> Void)?

    init(identity: PracticePlaybackOperation, lease: AudioHardwareOwnership.Lease) {
      self.identity = identity
      self.lease = lease
      cleanup = PracticePlaybackCleanup(operation: identity)
    }
  }

  init(
    ownership: AudioHardwareOwnership = .shared,
    fileOwnership: ProcessAudioFileOwnership = .shared,
    factory: @escaping PracticePlaybackDriverFactory
  ) {
    self.ownership = ownership
    self.fileOwnership = fileOwnership
    self.factory = factory
  }

  /// Returns only after actual play succeeds and MainActor confirms this operation is current.
  /// A caller must revalidate its own route/generation after suspension before changing UI.
  func startPlayback(
    id: UUID, url: URL,
    onFinished: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws {
    guard current == nil else { throw PracticePlaybackRuntimeError.busy }
    guard !usedIDs.contains(id) else { throw PracticePlaybackRuntimeError.reusedOperationID }
    let lease: AudioHardwareOwnership.Lease
    do { lease = try ownership.reserve(operationID: id, owner: .playback) } catch {
      throw PracticePlaybackRuntimeError.busy
    }
    let identity = PracticePlaybackOperation(id: id, url: url)
    guard fileOwnership.borrow(url, operation: id) else {
      ownership.release(lease)
      throw PracticePlaybackRuntimeError.couldNotStart(identity)
    }
    let operation = Operation(identity: identity, lease: lease)
    usedIDs.insert(id)
    current = operation
    operation.onFinished = onFinished
    let worker = PlaybackWorker(
      operation: operation.identity, cancellation: operation.cancellation, factory: factory
    ) { [self] report in receive(report, operation: operation) }
    operation.worker = worker
    ownership.registerPlaybackRecovery(lease) { [self] in retryCleanup(id: id) }
    publish(.preparing(operation.identity))
    // Published subscribers run synchronously and may revoke this fully registered operation.
    if operation.cancellation.isCancelled { publish(.stopping(operation.identity)) }
    let cancellation = operation.cancellation
    try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { continuation in
        operation.start = continuation
        worker.start()
      }
    } onCancel: {
      cancellation.cancel()
      Task { @MainActor [self] in _ = requestStop(id: id) }
    }
  }

  /// Revokes start permission synchronously, even while the driver queue is blocked.
  /// Stale IDs do nothing. Duplicate stops always join the ORIGINAL acknowledgement, including
  /// its negative receipt; only explicit retryCleanup starts another cleanup attempt.
  @discardableResult
  func requestStop(id: UUID) -> PracticePlaybackCleanup? {
    guard let operation = current, operation.identity.id == id else {
      return lastReleasedCleanup?.operation.id == id ? lastReleasedCleanup : nil
    }
    operation.cancellation.cancel()
    operation.onFinished = nil
    if !operation.stopRequested, operation.cleanup.receipt == nil {
      // Commit before publication: Published delivers in willSet and subscribers can reenter.
      operation.stopRequested = true
      publish(.stopping(operation.identity))
      operation.worker?.requestStop()
    }
    return operation.cleanup
  }

  /// Returns a shared retry acknowledgement while one retry is pending. No new player is made.
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? {
    guard let operation = current, operation.identity.id == id,
      operation.cleanup.receipt?.result == .cleanupUnconfirmed
    else { return nil }
    if let retry = operation.retry, retry.receipt == nil { return retry }
    let retry = PracticePlaybackCleanup(operation: operation.identity)
    operation.retry = retry
    publish(.stopping(operation.identity))
    operation.worker?.retryCleanup()
    return retry
  }

  /// Query only: never starts a retry and never substitutes the original negative receipt.
  func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
    guard lastCompletedRetry?.operation.id == id else { return nil }
    return lastCompletedRetry
  }

  private func receive(_ report: PlaybackWorkerReport, operation: Operation) {
    guard current === operation else { return }
    switch report {
    case .started:
      guard !operation.cancellation.isCancelled else {
        _ = requestStop(id: operation.identity.id)
        return
      }
      publish(.playing(operation.identity))
      // A state subscriber can synchronously requestStop while observing playing.
      guard !operation.cancellation.isCancelled else {
        _ = requestStop(id: operation.identity.id)
        return
      }
      let start = operation.start
      operation.start = nil
      start?.resume()
    case .stopping:
      // The worker already owns cleanup; a subscriber's stop only needs to revoke completion.
      operation.stopRequested = true
      publish(.stopping(operation.identity))
    case .cleaned(let result, let end):
      let receipt = PracticePlaybackCleanupReceipt(operation: operation.identity, result: result)
      let acknowledgement = operation.retry ?? operation.cleanup
      let start = operation.start
      operation.start = nil
      let completion = operation.onFinished
      if result == .released {
        operation.onFinished = nil
        fileOwnership.finishBorrowing(operation: operation.identity.id)
        ownership.release(operation.lease)
        lastReleasedCleanup = operation.cleanup
        if operation.retry != nil { lastCompletedRetry = receipt }
        current = nil
        operation.worker = nil
        publish(.idle)
        acknowledgement.resolve(receipt)
      } else {
        // Commit this exact failed attempt before subscribers can synchronously install a retry.
        // Lease/resources/borrow remain owned; the local acknowledgement cannot become that retry.
        ownership.markPlaybackCleanupBlocked(operation.lease)
        acknowledgement.resolve(receipt)
        publish(.cleanupBlocked(operation.identity))
      }
      if let start {
        let error: PracticePlaybackRuntimeError
        if result == .cleanupUnconfirmed {
          error = .cleanupUnconfirmed(operation.identity)
        } else if operation.cancellation.isCancelled {
          error = .cancelled(operation.identity)
        } else {
          switch end {
          case .couldNotStart: error = .couldNotStart(operation.identity)
          case .cancelled, .finished: error = .cancelled(operation.identity)
          }
        }
        start.resume(throwing: error)
      }
      if result == .released, !operation.cancellation.isCancelled,
        case .finished(let success) = end
      {
        completion?(operation.identity, success)
      }
    }
  }

  /// Finish an event's synchronous delivery to every subscriber before a reentrant transition.
  /// latestState commits ahead of willSet, so deduplication never consults its old stored value.
  /// Cancellation/operation bookkeeping remains immediate; only publication joins this drain.
  private func publish(_ nextState: PracticePlaybackRuntimeState) {
    guard latestState != nextState else { return }
    latestState = nextState
    pendingStates.append(nextState)
    guard !isPublishingState else { return }
    isPublishingState = true
    defer { isPublishingState = false }
    while !pendingStates.isEmpty {
      state = pendingStates.removeFirst()
    }
  }
}
