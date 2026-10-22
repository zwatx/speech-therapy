import Combine
import Dispatch
import Foundation

struct PracticeSpokenWordOperation: Equatable, Sendable {
  let id: UUID
  let word: String
}

enum PracticeSpokenWordState: Equatable, Sendable {
  case idle
  case preparing(PracticeSpokenWordOperation)
  case speaking(PracticeSpokenWordOperation)
  case stopping(PracticeSpokenWordOperation)
  case cleanupBlocked(PracticeSpokenWordOperation)
}

enum PracticeSpokenWordError: Error, Equatable, Sendable {
  case busy, reusedOperationID, unavailable, cancelled, cleanupUnconfirmed
}

enum PracticeSpokenWordEvent: Sendable { case started, finished, cancelled }

/// All methods and construction run on one owned serial queue. A throwing factory must
/// dispose its partial resources. Once enqueue is entered, only a matching terminal event
/// authorizes disposal; stop's return value is deliberately not an acknowledgement.
protocol PracticeSpokenWordDriver: AnyObject {
  func prepare() throws
  func enqueue()
  func requestStop()
  func dispose() throws
  func deactivate() throws
}

typealias PracticeSpokenWordDriverFactory =
  @Sendable (
    PracticeSpokenWordOperation,
    @escaping @Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void
  ) throws -> any PracticeSpokenWordDriver

struct PracticeSpokenWordReceipt: Equatable, Sendable {
  let operation: PracticeSpokenWordOperation
  let result: Result
  enum Result: Equatable, Sendable { case released, cleanupUnconfirmed }
}

@MainActor
final class PracticeSpokenWordCleanup {
  let operation: PracticeSpokenWordOperation
  private(set) var receipt: PracticeSpokenWordReceipt?
  private var waiters: [CheckedContinuation<PracticeSpokenWordReceipt, Never>] = []
  fileprivate init(_ operation: PracticeSpokenWordOperation) { self.operation = operation }
  func value() async -> PracticeSpokenWordReceipt {
    if let receipt { return receipt }
    return await withCheckedContinuation { waiters.append($0) }
  }
  fileprivate func resolve(_ receipt: PracticeSpokenWordReceipt) {
    guard self.receipt == nil else { return }
    self.receipt = receipt
    let waiting = waiters
    waiters.removeAll()
    for waiter in waiting { waiter.resume(returning: receipt) }
  }
}

@MainActor
protocol PracticeSpokenWordSpeaking: AnyObject {
  var state: PracticeSpokenWordState { get }
  var statePublisher: AnyPublisher<PracticeSpokenWordState, Never> { get }
  func start(_ operation: PracticeSpokenWordOperation) async throws
  func requestStop(id: UUID) -> PracticeSpokenWordCleanup?
  func retryCleanup(id: UUID) -> PracticeSpokenWordCleanup?
  func completedCleanupRetry(id: UUID) -> PracticeSpokenWordReceipt?
}

/// Only this revocation bit crosses queues; no lock spans a framework call or actor hop.
private final class SpokenWordCancellation: @unchecked Sendable {
  private let lock = NSLock()
  private var revoked = false
  func cancel() { lock.withLock { revoked = true } }
  var isCancelled: Bool { lock.withLock { revoked } }
  func commitEnqueue() -> Bool { lock.withLock { !revoked } }
}

private enum SpokenWordReport: Sendable {
  case started
  case stopping
  case cleaned(PracticeSpokenWordReceipt.Result, PracticeSpokenWordError?)
}

/// Queue confinement proof: driver and all mutable SDK bookkeeping stay on queue. Only
/// immutable reports and the independently locked cancellation bit cross the boundary.
/// Timers bound delegate-event waits once this queue can run, not synchronous SDK calls.
/// A blocked SDK return keeps resources/lease retained; Stop still revokes eligibility.
private final class SpokenWordWorker: @unchecked Sendable {
  private let queue = DispatchQueue(label: "com.cadence.spoken-word", qos: .userInitiated)
  private let operation: PracticeSpokenWordOperation
  private let cancellation: SpokenWordCancellation
  private let factory: PracticeSpokenWordDriverFactory
  private let startupWait: TimeInterval
  private let cleanupWait: TimeInterval
  private let receiver: @MainActor @Sendable (SpokenWordReport) -> Void
  private var driver: (any PracticeSpokenWordDriver)?
  private var enqueued = false
  private var terminal = false
  private var stopping = false
  private var disposed = false
  private var released = false
  private var attemptFinished = false
  private var startSeen = false
  private var failure: PracticeSpokenWordError?
  private var startupTimer: DispatchWorkItem?
  private var cleanupTimer: DispatchWorkItem?
  private var lastReport: Task<Void, Never>?

  init(
    operation: PracticeSpokenWordOperation, cancellation: SpokenWordCancellation,
    factory: @escaping PracticeSpokenWordDriverFactory,
    startupWait: TimeInterval, cleanupWait: TimeInterval,
    receiver: @escaping @MainActor @Sendable (SpokenWordReport) -> Void
  ) {
    self.operation = operation
    self.cancellation = cancellation
    self.factory = factory
    self.startupWait = startupWait
    self.cleanupWait = cleanupWait
    self.receiver = receiver
  }

  func start() { queue.async { self.startOnQueue() } }
  func stop() { queue.async { self.stopOnQueue(retry: false) } }
  func retry() { queue.async { self.stopOnQueue(retry: true) } }

  private func report(_ report: SpokenWordReport) {
    let previous = lastReport
    let receiver = receiver
    lastReport = Task { @MainActor in
      await previous?.value
      receiver(report)
    }
  }

  private func startOnQueue() {
    guard !released else { return }
    guard !cancellation.isCancelled else { return cleanOnQueue() }
    do {
      driver = try factory(operation) { [weak self] identity, event in
        guard let self else { return }
        self.queue.async { self.eventOnQueue(identity, event) }
      }
      guard !cancellation.isCancelled else { return cleanOnQueue() }
      try driver?.prepare()
      guard cancellation.commitEnqueue() else { return cleanOnQueue() }
      enqueued = true
      // Commit before the SDK call. Even cancellation immediately after this point must
      // await a real terminal delegate event, never infer silence from stopSpeaking's Bool.
      driver?.enqueue()
      let timer = DispatchWorkItem { [weak self] in
        guard let self, !self.startSeen, !self.released, !self.stopping else { return }
        self.failure = .unavailable
        self.cancellation.cancel()
        self.stopOnQueue(retry: false)
      }
      startupTimer = timer
      queue.asyncAfter(deadline: .now() + startupWait, execute: timer)
      if cancellation.isCancelled { stopOnQueue(retry: false) }
    } catch {
      failure = .unavailable
      cleanOnQueue()
    }
  }

  private func eventOnQueue(
    _ identity: PracticeSpokenWordOperation, _ event: PracticeSpokenWordEvent
  ) {
    guard identity == operation, enqueued, !released else { return }
    switch event {
    case .started:
      guard !startSeen, !terminal else { return }
      startSeen = true
      startupTimer?.cancel()
      startupTimer = nil
      if cancellation.isCancelled || stopping {
        stopOnQueue(retry: false)
      } else {
        report(.started)
      }
    case .finished, .cancelled:
      guard !terminal else { return }
      terminal = true
      startupTimer?.cancel()
      startupTimer = nil
      // A late event is useful evidence, but cannot silently revise a failed receipt.
      guard !attemptFinished else { return }
      cleanOnQueue()
    }
  }

  private func stopOnQueue(retry: Bool) {
    guard !released else { return }
    if retry { attemptFinished = false }
    guard !attemptFinished, !stopping || retry else { return }
    stopping = true
    startupTimer?.cancel()
    startupTimer = nil
    report(.stopping)
    if !enqueued || terminal { return cleanOnQueue() }
    driver?.requestStop()
    cleanupTimer?.cancel()
    let timer = DispatchWorkItem { [weak self] in
      guard let self, !self.released, !self.attemptFinished else { return }
      self.attemptFinished = true
      self.cleanupTimer = nil
      self.report(.cleaned(.cleanupUnconfirmed, .cleanupUnconfirmed))
    }
    cleanupTimer = timer
    queue.asyncAfter(deadline: .now() + cleanupWait, execute: timer)
  }

  private func cleanOnQueue() {
    guard !released, !attemptFinished, !enqueued || terminal else { return }
    startupTimer?.cancel()
    startupTimer = nil
    cleanupTimer?.cancel()
    cleanupTimer = nil
    report(.stopping)
    do {
      if !disposed {
        try driver?.dispose()
        disposed = true
      }
      try driver?.deactivate()
      driver = nil
      released = true
      attemptFinished = true
      report(.cleaned(.released, failure))
    } catch {
      attemptFinished = true
      report(.cleaned(.cleanupUnconfirmed, .cleanupUnconfirmed))
    }
  }
}

/// Inert MainActor owner: no synthesizer, voice enumeration or audio session until start.
@MainActor
final class PracticeSpokenWordRuntime: ObservableObject, PracticeSpokenWordSpeaking {
  @Published private(set) var state: PracticeSpokenWordState = .idle
  var statePublisher: AnyPublisher<PracticeSpokenWordState, Never> { $state.eraseToAnyPublisher() }
  private let ownership: AudioHardwareOwnership
  private let factory: PracticeSpokenWordDriverFactory
  private let startupWait: TimeInterval
  private let cleanupWait: TimeInterval
  private var current: Operation?
  private var usedIDs: Set<UUID> = []
  private var lastCleanup: PracticeSpokenWordCleanup?
  private var lastRetry: PracticeSpokenWordReceipt?
  private var pendingStates: [PracticeSpokenWordState] = []
  private var latestState: PracticeSpokenWordState = .idle
  private var publishing = false

  @MainActor
  private final class Operation {
    let identity: PracticeSpokenWordOperation
    let lease: AudioHardwareOwnership.Lease
    let cancellation = SpokenWordCancellation()
    let cleanup: PracticeSpokenWordCleanup
    var retry: PracticeSpokenWordCleanup?
    var worker: SpokenWordWorker?
    var start: CheckedContinuation<Void, Error>?
    var stopRequested = false
    init(_ identity: PracticeSpokenWordOperation, lease: AudioHardwareOwnership.Lease) {
      self.identity = identity
      self.lease = lease
      cleanup = PracticeSpokenWordCleanup(identity)
    }
  }

  init(
    ownership: AudioHardwareOwnership = .shared,
    startupWait: TimeInterval = 5, cleanupWait: TimeInterval = 3,
    factory: @escaping PracticeSpokenWordDriverFactory = { operation, event in
      SystemPracticeSpokenWordDriver(operation: operation, event: event)
    }
  ) {
    precondition(startupWait.isFinite && startupWait > 0 && cleanupWait.isFinite && cleanupWait > 0)
    self.ownership = ownership
    self.factory = factory
    self.startupWait = startupWait
    self.cleanupWait = cleanupWait
  }

  func start(_ identity: PracticeSpokenWordOperation) async throws {
    guard current == nil else { throw PracticeSpokenWordError.busy }
    guard !usedIDs.contains(identity.id) else { throw PracticeSpokenWordError.reusedOperationID }
    let lease: AudioHardwareOwnership.Lease
    do { lease = try ownership.reserve(operationID: identity.id, owner: .spokenWord) } catch {
      throw PracticeSpokenWordError.busy
    }
    let operation = Operation(identity, lease: lease)
    usedIDs.insert(identity.id)
    current = operation
    let worker = SpokenWordWorker(
      operation: identity, cancellation: operation.cancellation, factory: factory,
      startupWait: startupWait, cleanupWait: cleanupWait
    ) { [self] report in receive(report, operation: operation) }
    operation.worker = worker
    ownership.registerSpokenWordRecovery(lease) { [self] in
      guard let acknowledgement = retryCleanup(id: identity.id) else { return nil }
      return await acknowledgement.value()
    }
    publish(.preparing(identity))
    let cancellation = operation.cancellation
    try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { continuation in
        operation.start = continuation
        worker.start()
      }
    } onCancel: {
      cancellation.cancel()
      Task { @MainActor [self] in _ = requestStop(id: identity.id) }
    }
  }

  func requestStop(id: UUID) -> PracticeSpokenWordCleanup? {
    guard let operation = current, operation.identity.id == id else {
      return lastCleanup?.operation.id == id ? lastCleanup : nil
    }
    operation.cancellation.cancel()
    if !operation.stopRequested, operation.cleanup.receipt == nil {
      operation.stopRequested = true
      publish(.stopping(operation.identity))
      operation.worker?.stop()
    }
    return operation.cleanup
  }

  func retryCleanup(id: UUID) -> PracticeSpokenWordCleanup? {
    guard let operation = current, operation.identity.id == id,
      operation.cleanup.receipt?.result == .cleanupUnconfirmed
    else { return nil }
    if let retry = operation.retry, retry.receipt == nil { return retry }
    let retry = PracticeSpokenWordCleanup(operation.identity)
    operation.retry = retry
    publish(.stopping(operation.identity))
    operation.worker?.retry()
    return retry
  }

  func completedCleanupRetry(id: UUID) -> PracticeSpokenWordReceipt? {
    lastRetry?.operation.id == id ? lastRetry : nil
  }

  private func receive(_ report: SpokenWordReport, operation: Operation) {
    guard current === operation else { return }
    switch report {
    case .started:
      guard !operation.cancellation.isCancelled else {
        _ = requestStop(id: operation.identity.id)
        return
      }
      publish(.speaking(operation.identity))
      guard !operation.cancellation.isCancelled else { return }
      let start = operation.start
      operation.start = nil
      start?.resume()
    case .stopping:
      operation.stopRequested = true
      publish(.stopping(operation.identity))
    case .cleaned(let result, let error):
      let receipt = PracticeSpokenWordReceipt(operation: operation.identity, result: result)
      let acknowledgement = operation.retry ?? operation.cleanup
      let start = operation.start
      operation.start = nil
      if result == .released {
        ownership.release(operation.lease)
        lastCleanup = operation.cleanup
        if operation.retry != nil { lastRetry = receipt }
        current = nil
        operation.worker = nil
        acknowledgement.resolve(receipt)
        publish(.idle)
      } else {
        ownership.markSpokenWordCleanupBlocked(operation.lease)
        acknowledgement.resolve(receipt)
        publish(.cleanupBlocked(operation.identity))
      }
      if let start {
        start.resume(
          throwing: error ?? (operation.cancellation.isCancelled ? .cancelled : .unavailable))
      }
    }
  }

  private func publish(_ next: PracticeSpokenWordState) {
    guard latestState != next else { return }
    latestState = next
    pendingStates.append(next)
    guard !publishing else { return }
    publishing = true
    defer { publishing = false }
    while !pendingStates.isEmpty { state = pendingStates.removeFirst() }
  }
}
