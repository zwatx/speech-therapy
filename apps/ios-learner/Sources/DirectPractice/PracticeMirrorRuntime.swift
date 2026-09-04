import Combine
import Dispatch
import Foundation

struct PracticeMirrorOwner: Hashable, Sendable {
  let id: UUID
}

enum PracticeMirrorRuntimeState: Equatable, Sendable {
  case idle
  case starting(PracticeMirrorOwner)
  case live(PracticeMirrorOwner)
  case stopping(PracticeMirrorOwner)
  case stopFailed(PracticeMirrorOwner)
}

struct PracticeMirrorCleanupReceipt: Equatable, Sendable {
  let owner: PracticeMirrorOwner
  let attemptID: UUID
  let result: Result
  enum Result: Equatable, Sendable { case released, cleanupUnconfirmed }
}

/// Stable original receipt; explicit retry gets a separate acknowledgement. Task cancellation
/// of a waiter cannot cancel the camera's independently retained cleanup.
@MainActor
final class PracticeMirrorCleanup {
  let owner: PracticeMirrorOwner
  let attemptID = UUID()
  private(set) var receipt: PracticeMirrorCleanupReceipt?
  private var waiters: [CheckedContinuation<PracticeMirrorCleanupReceipt, Never>] = []

  fileprivate init(owner: PracticeMirrorOwner) { self.owner = owner }

  func value() async -> PracticeMirrorCleanupReceipt {
    if let receipt { return receipt }
    return await withCheckedContinuation { waiters.append($0) }
  }

  func confirmsRelease(_ receipt: PracticeMirrorCleanupReceipt) -> Bool {
    receipt.owner == owner && receipt.attemptID == attemptID && receipt.result == .released
  }

  @discardableResult
  fileprivate func resolve(_ receipt: PracticeMirrorCleanupReceipt) -> Bool {
    guard self.receipt == nil, receipt.owner == owner, receipt.attemptID == attemptID else {
      return false
    }
    self.receipt = receipt
    let waiting = waiters
    waiters.removeAll()
    for waiter in waiting { waiter.resume(returning: receipt) }
    return true
  }
}

/// Plain preview only. No video-data output, frame callback, scoring, file, network or audio
/// session API belongs in this contract. Methods run on the runtime's serial worker queue.
/// Construction must be inert and nonthrowing: configure may leave partial resources, which
/// remain on this exact driver until stopAndReleasePreviewResources succeeds.
protocol PracticeMirrorDriver: AnyObject {
  func configure() throws
  func start() throws
  var previewSource: PracticeMirrorPreviewSource? { get }
  /// Return only after session stop and owned inputs/outputs/preview resources are released.
  func stopAndReleasePreviewResources() throws
}

extension PracticeMirrorDriver {
  var previewSource: PracticeMirrorPreviewSource? { nil }
}

typealias PracticeMirrorDriverFactory =
  @Sendable (PracticeMirrorOwner) -> any PracticeMirrorDriver

/// A single camera recovery slot, independent of audio ownership. A pending or failed owner
/// retains its runtime after screen/session destruction. No new camera can reserve this slot.
@MainActor
final class ProcessPracticeMirrorRecovery {
  static let shared = ProcessPracticeMirrorRecovery(cameraLease: .shared)
  private let cameraLease: ProcessCameraLease
  private(set) var owner: PracticeMirrorOwner?
  private(set) var runtime: PracticeMirrorRuntime?

  init(cameraLease: ProcessCameraLease = ProcessCameraLease()) {
    self.cameraLease = cameraLease
  }

  fileprivate func reserve(_ owner: PracticeMirrorOwner, runtime: PracticeMirrorRuntime) -> Bool {
    guard self.owner == nil, cameraLease.acquire(owner.id) else { return false }
    self.owner = owner
    self.runtime = runtime
    return true
  }

  fileprivate func release(_ owner: PracticeMirrorOwner, runtime: PracticeMirrorRuntime) -> Bool {
    guard self.owner == owner, self.runtime === runtime else { return false }
    self.owner = nil
    self.runtime = nil
    return true
  }

  /// Query/retry never constructs a driver or implicitly stops a live owner.
  func retryStop() -> PracticeMirrorCleanup? {
    guard let owner else { return nil }
    return runtime?.retryStop(owner: owner)
  }
}

private final class MirrorCancellation: @unchecked Sendable {
  private let lock = NSLock()
  private var revoked = false
  func revoke() { lock.withLock { revoked = true } }
  var isRevoked: Bool { lock.withLock { revoked } }
  /// Cancellation after this point cannot retract an already-entered synchronous start.
  func commitStart() -> Bool { lock.withLock { !revoked } }
}

private enum MirrorWorkerReport: Sendable {
  case started(PracticeMirrorOwner, PracticeMirrorPreviewSource?)
  case cleaned(PracticeMirrorCleanupReceipt, startFailed: Bool)
}

/// Factory, driver and attempt bookkeeping stay exclusively on queue. Cancellation is locked;
/// reports are immutable Sendable values. Receiver hops to MainActor in explicit report order.
private final class MirrorWorker: @unchecked Sendable {
  private let queue = DispatchQueue(label: "com.cadence.practice-mirror", qos: .userInitiated)
  private let owner: PracticeMirrorOwner
  private let originalAttemptID: UUID
  private let cancellation: MirrorCancellation
  private let factory: PracticeMirrorDriverFactory
  private let receiver: @MainActor @Sendable (MirrorWorkerReport) -> Void
  private var driver: (any PracticeMirrorDriver)?
  private var attempted: Set<UUID> = []
  private var startFailed = false
  private var lastReport: Task<Void, Never>?

  init(
    owner: PracticeMirrorOwner, originalAttemptID: UUID, cancellation: MirrorCancellation,
    factory: @escaping PracticeMirrorDriverFactory,
    receiver: @escaping @MainActor @Sendable (MirrorWorkerReport) -> Void
  ) {
    self.owner = owner
    self.originalAttemptID = originalAttemptID
    self.cancellation = cancellation
    self.factory = factory
    self.receiver = receiver
  }

  func start() { queue.async { self.startOnQueue() } }
  func clean(attemptID: UUID) { queue.async { self.cleanOnQueue(attemptID: attemptID) } }

  private func report(_ report: MirrorWorkerReport) {
    let previous = lastReport
    let receiver = receiver
    lastReport = Task { @MainActor in
      await previous?.value
      receiver(report)
    }
  }

  private func startOnQueue() {
    // A reentrant Stop may enqueue cleanup before this start. Its cancellation is permanent.
    guard attempted.isEmpty else { return }
    guard !cancellation.isRevoked else { return cleanOnQueue(attemptID: originalAttemptID) }
    driver = factory(owner)
    do {
      guard !cancellation.isRevoked else { return cleanOnQueue(attemptID: originalAttemptID) }
      try driver?.configure()
      guard cancellation.commitStart() else { return cleanOnQueue(attemptID: originalAttemptID) }
      try driver?.start()
      guard !cancellation.isRevoked else { return cleanOnQueue(attemptID: originalAttemptID) }
      report(.started(owner, driver?.previewSource))
    } catch {
      startFailed = true
      cancellation.revoke()
      cleanOnQueue(attemptID: originalAttemptID)
    }
  }

  private func cleanOnQueue(attemptID: UUID) {
    guard attempted.insert(attemptID).inserted else { return }
    let result: PracticeMirrorCleanupReceipt.Result
    do {
      try driver?.stopAndReleasePreviewResources()
      driver = nil
      result = .released
    } catch {
      // The exact partially configured driver is retained; retry never makes a new driver.
      result = .cleanupUnconfirmed
    }
    report(
      .cleaned(
        .init(owner: owner, attemptID: attemptID, result: result),
        startFailed: startFailed))
  }
}

@MainActor
final class PracticeMirrorRuntime: ObservableObject {
  // Getter commits before synchronous publication, matching the audio runtime's reentry rule.
  @Published private var emittedState: PracticeMirrorRuntimeState = .idle
  private var committedState: PracticeMirrorRuntimeState = .idle
  var state: PracticeMirrorRuntimeState { committedState }
  var statePublisher: AnyPublisher<PracticeMirrorRuntimeState, Never> {
    $emittedState.eraseToAnyPublisher()
  }
  private var pendingStates: [PracticeMirrorRuntimeState] = []
  private var isPublishing = false
  private let recovery: ProcessPracticeMirrorRecovery
  private let factory: PracticeMirrorDriverFactory
  let presentation: PracticeMirrorPresentation?
  private var current: Operation?
  private var usedOwners: Set<UUID> = []
  private var lastReleasedCleanup: PracticeMirrorCleanup?
  private var lastCompletedRetry: PracticeMirrorCleanupReceipt?
  private(set) var failedStartOwner: PracticeMirrorOwner?

  @MainActor
  private final class Operation {
    let owner: PracticeMirrorOwner
    let cancellation = MirrorCancellation()
    let original: PracticeMirrorCleanup
    var retry: PracticeMirrorCleanup?
    var stopRequested = false
    var unavailableAfterCleanup = false
    var worker: MirrorWorker?
    init(owner: PracticeMirrorOwner) {
      self.owner = owner
      original = PracticeMirrorCleanup(owner: owner)
    }
  }

  init(
    recovery: ProcessPracticeMirrorRecovery = .shared,
    presentation: PracticeMirrorPresentation? = nil,
    factory: @escaping PracticeMirrorDriverFactory
  ) {
    self.recovery = recovery
    self.presentation = presentation
    self.factory = factory
  }

  var currentOwner: PracticeMirrorOwner? { current?.owner }

  /// Nonmutating recovery attachment: reading the original handle never revokes a live owner.
  func cleanupAcknowledgement(owner: PracticeMirrorOwner) -> PracticeMirrorCleanup? {
    if let operation = current, operation.owner == owner { return operation.original }
    return lastReleasedCleanup?.owner == owner ? lastReleasedCleanup : nil
  }

  /// Synchronous registration precedes publication/configuration. A denied reservation does
  /// not configure any camera. Public caller must gate scene and permission before calling.
  @discardableResult
  func start(owner: PracticeMirrorOwner) -> Bool {
    guard current == nil, !usedOwners.contains(owner.id),
      recovery.reserve(owner, runtime: self)
    else { return false }
    let operation = Operation(owner: owner)
    current = operation
    usedOwners.insert(owner.id)
    failedStartOwner = nil
    let worker = MirrorWorker(
      owner: owner, originalAttemptID: operation.original.attemptID,
      cancellation: operation.cancellation, factory: factory
    ) {
      [self] report in receive(report, operation: operation)
    }
    operation.worker = worker
    presentation?.prepare(owner: owner)
    publish(.starting(owner))
    worker.start()
    return true
  }

  @discardableResult
  func requestStop(owner: PracticeMirrorOwner) -> PracticeMirrorCleanup? {
    guard let operation = current, operation.owner == owner else {
      return lastReleasedCleanup?.owner == owner ? lastReleasedCleanup : nil
    }
    operation.cancellation.revoke()
    if !operation.stopRequested, operation.original.receipt == nil {
      operation.stopRequested = true
      presentation?.revoke(owner: owner)
      publish(.stopping(owner))
      operation.worker?.clean(attemptID: operation.original.attemptID)
    }
    return operation.original
  }

  /// A framework interruption belongs only to its original driver. It cannot stop a
  /// successor or silently restart the camera after returning to the foreground.
  func unavailableAndStop(owner: PracticeMirrorOwner) {
    guard let operation = current, operation.owner == owner else { return }
    operation.unavailableAfterCleanup = true
    _ = requestStop(owner: owner)
  }

  /// Repeated ordinary stops keep the original negative receipt. Only explicit retry enters
  /// here, and concurrent callers share one pending new acknowledgement.
  func retryStop(owner: PracticeMirrorOwner) -> PracticeMirrorCleanup? {
    guard let operation = current, operation.owner == owner,
      operation.original.receipt?.result == .cleanupUnconfirmed
    else { return nil }
    if let retry = operation.retry, retry.receipt == nil { return retry }
    let retry = PracticeMirrorCleanup(owner: owner)
    operation.retry = retry
    publish(.stopping(owner))
    operation.worker?.clean(attemptID: retry.attemptID)
    return retry
  }

  /// Evidence query only. Idle state and missing handle never substitute for this receipt.
  func releasedReceipt(owner: PracticeMirrorOwner) -> PracticeMirrorCleanupReceipt? {
    if let retry = lastCompletedRetry, retry.owner == owner, retry.result == .released {
      return retry
    }
    guard let original = lastReleasedCleanup?.receipt,
      original.owner == owner, original.result == .released
    else { return nil }
    return original
  }

  private func receive(_ report: MirrorWorkerReport, operation: Operation) {
    guard current === operation else { return }
    switch report {
    case .started(let owner, let source):
      guard owner == operation.owner, !operation.cancellation.isRevoked else { return }
      publish(.live(owner))
      // Live subscribers may synchronously Hide/Close before preview installation.
      guard current === operation, !operation.cancellation.isRevoked else { return }
      presentation?.install(owner: owner, source: source)
    case .cleaned(let receipt, let startFailed):
      guard receipt.owner == operation.owner else { return }
      let acknowledgement: PracticeMirrorCleanup
      if receipt.attemptID == operation.original.attemptID {
        acknowledgement = operation.original
      } else if let retry = operation.retry, receipt.attemptID == retry.attemptID {
        acknowledgement = retry
      } else {
        return
      }
      guard acknowledgement.receipt == nil else { return }
      if receipt.result == .released {
        guard recovery.release(operation.owner, runtime: self) else { return }
        // Clear ownership before publishing: an idle subscriber may acquire a successor.
        current = nil
        operation.worker = nil
        lastReleasedCleanup = operation.original
        if acknowledgement !== operation.original { lastCompletedRetry = receipt }
        if startFailed || operation.unavailableAfterCleanup { failedStartOwner = operation.owner }
        acknowledgement.resolve(receipt)
        presentation?.revoke(owner: operation.owner)
        // Presentation subscribers may acquire a successor after exact release.
        if current == nil { publish(.idle) }
      } else {
        // Resolve this exact attempt before reentrant subscribers can install a retry.
        acknowledgement.resolve(receipt)
        publish(.stopFailed(operation.owner))
        presentation?.revoke(owner: operation.owner)
      }
    }
  }

  private func publish(_ next: PracticeMirrorRuntimeState) {
    guard committedState != next else { return }
    committedState = next
    pendingStates.append(next)
    guard !isPublishing else { return }
    isPublishing = true
    defer { isPublishing = false }
    while !pendingStates.isEmpty { emittedState = pendingStates.removeFirst() }
  }
}
