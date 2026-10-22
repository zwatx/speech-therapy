import Combine
import Dispatch
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class SpokenWordRuntimeTests: XCTestCase {
  func testPreparingSubscriberCanCancelBeforeAnyDriverConstruction() async {
    let control = SpokenWordDriverControl()
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate)
    let operation = identity()
    var acknowledgement: PracticeSpokenWordCleanup?
    let subscription = runtime.statePublisher.sink { state in
      MainActor.assumeIsolated {
        if case .preparing = state { acknowledgement = runtime.requestStop(id: operation.id) }
      }
    }
    let result = await startResult(runtime, operation).value
    XCTAssertEqual(result, .cancelled)
    XCTAssertEqual(acknowledgement?.receipt?.result, .released)
    XCTAssertEqual(control.factoryCalls, 0)
    XCTAssertNil(gate.currentLease)
    subscription.cancel()
  }

  func testConstructionIsInertAndCancellationDuringPreparationNeverEnqueues() async {
    let control = SpokenWordDriverControl(holdPreparation: true)
    defer { control.releasePreparation() }
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate)
    XCTAssertEqual(control.factoryCalls, 0)
    let operation = identity()
    let start = startResult(runtime, operation)
    await observed(control.prepared)
    let acknowledgement = runtime.requestStop(id: operation.id)!
    XCTAssertTrue(acknowledgement === runtime.requestStop(id: operation.id))
    XCTAssertNotNil(gate.currentLease)
    control.releasePreparation()
    let receipt = await acknowledgement.value()
    XCTAssertEqual(receipt.result, .released)
    let result = await start.value
    XCTAssertEqual(result, .cancelled)
    XCTAssertEqual(control.enqueues, 0)
    XCTAssertEqual(control.disposals, 1)
    XCTAssertNil(gate.currentLease)
    XCTAssertFalse(control.calledOnMainThread)
  }

  func testOnlyMatchingDidStartAuthorizesSpeakingAndStopWaitsForTerminalEvent() async {
    let control = SpokenWordDriverControl()
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate)
    let operation = identity()
    let start = startResult(runtime, operation)
    await observed(control.enqueued)
    XCTAssertEqual(runtime.state, .preparing(operation))
    control.send(.started, operation: identity())
    control.send(.finished, operation: .init(id: operation.id, word: "pig"))
    control.send(.started)
    let error = await start.value
    XCTAssertNil(error)
    XCTAssertEqual(runtime.state, .speaking(operation))
    let acknowledgement = runtime.requestStop(id: operation.id)!
    await observed(control.stopped)
    control.send(.finished, operation: identity())
    XCTAssertNil(acknowledgement.receipt)
    XCTAssertEqual(gate.currentLease?.operationID, operation.id)
    XCTAssertEqual(control.disposals, 0)
    control.send(.cancelled)
    let receipt = await acknowledgement.value()
    XCTAssertEqual(receipt.result, .released)
    XCTAssertEqual(control.disposals, 1)
    XCTAssertEqual(control.deactivations, 1)
    XCTAssertNil(gate.currentLease)
  }

  func testMissingTerminalRetainsLeaseAndOriginalNegativeEvenAfterLateEventAndRetry() async {
    let control = SpokenWordDriverControl()
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate, cleanupWait: 0.05)
    let operation = identity()
    let start = startResult(runtime, operation)
    await observed(control.enqueued)
    control.send(.started)
    _ = await start.value
    let original = runtime.requestStop(id: operation.id)!
    let failed = await original.value()
    XCTAssertEqual(failed.result, .cleanupUnconfirmed)
    XCTAssertEqual(runtime.state, .cleanupBlocked(operation))
    XCTAssertEqual(gate.blockedSpokenWordOperationID, operation.id)
    XCTAssertEqual(control.disposals, 0)
    control.send(.cancelled)
    // Retry is queued after that exact terminal report; no fresh driver or utterance.
    let retry = runtime.retryCleanup(id: operation.id)!
    XCTAssertTrue(retry === runtime.retryCleanup(id: operation.id))
    let released = await retry.value()
    XCTAssertEqual(released.result, .released)
    XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
    XCTAssertTrue(original === runtime.requestStop(id: operation.id))
    XCTAssertEqual(control.factoryCalls, 1)
    XCTAssertNil(gate.currentLease)
  }

  func testMatchingNaturalFinishDisposesAndDeactivatesWithoutAStopRequest() async {
    let control = SpokenWordDriverControl()
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate)
    let operation = identity()
    let start = startResult(runtime, operation)
    await observed(control.enqueued)
    control.send(.started)
    _ = await start.value
    let finished = expectation(description: "natural finish released")
    let subscription = runtime.statePublisher.dropFirst().sink { state in
      if state == .idle { finished.fulfill() }
    }
    control.send(.finished)
    await observed(finished)
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(control.stopRequests, 0)
    XCTAssertEqual(control.disposals, 1)
    XCTAssertEqual(control.deactivations, 1)
    XCTAssertEqual(runtime.requestStop(id: operation.id)?.receipt?.result, .released)
    subscription.cancel()
  }

  func testDeactivationFailureStaysProcessRecoverableAndUsesSameResource() async {
    let control = SpokenWordDriverControl(failDeactivationOnce: true)
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate)
    let operation = identity()
    let start = startResult(runtime, operation)
    await observed(control.enqueued)
    control.send(.started)
    _ = await start.value
    let original = runtime.requestStop(id: operation.id)!
    control.send(.cancelled)
    _ = await original.value()
    let recovery = AudioCleanupRecoveryModel(ownership: gate, files: ProcessAudioFileOwnership())
    recovery.refresh()
    XCTAssertEqual(recovery.snapshot.blockedSpokenWordOperationID, operation.id)
    XCTAssertTrue(recovery.snapshot.canRetry)
    let succeeded = await recovery.retry().value
    XCTAssertTrue(succeeded)
    XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
    XCTAssertEqual(control.factoryCalls, 1)
    XCTAssertEqual(control.disposals, 1)
    XCTAssertEqual(control.deactivations, 2)
    XCTAssertNil(gate.currentLease)
  }

  func testStartupTimeoutRequestsStopButCannotInventTerminalRelease() async {
    let control = SpokenWordDriverControl()
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate, startupWait: 0.05, cleanupWait: 0.05)
    let operation = identity()
    let result = startResult(runtime, operation)
    await observed(control.enqueued)
    let error = await result.value
    XCTAssertEqual(error, .cleanupUnconfirmed)
    XCTAssertNotNil(gate.currentLease)
    XCTAssertEqual(control.disposals, 0)
    control.send(.cancelled)
    let retry = runtime.retryCleanup(id: operation.id)!
    _ = await retry.value()
    XCTAssertNil(gate.currentLease)
  }

  func testReentrantSpeakingStopCannotReportSuccessfulStartOrReleaseBeforeDelegate() async {
    let control = SpokenWordDriverControl()
    let gate = AudioHardwareOwnership()
    let runtime = make(control, gate)
    let operation = identity()
    var acknowledgement: PracticeSpokenWordCleanup?
    let subscription = runtime.statePublisher.sink { state in
      MainActor.assumeIsolated {
        if case .speaking = state { acknowledgement = runtime.requestStop(id: operation.id) }
      }
    }
    let start = startResult(runtime, operation)
    await observed(control.enqueued)
    control.send(.started)
    await observed(control.stopped)
    XCTAssertNotNil(acknowledgement)
    XCTAssertNil(acknowledgement?.receipt)
    control.send(.cancelled)
    let error = await start.value
    XCTAssertEqual(error, .cancelled)
    XCTAssertEqual(runtime.state, .idle)
    subscription.cancel()
  }

  func testOldCallbacksAndStaleStopCannotReleaseSuccessor() async {
    let gate = AudioHardwareOwnership()
    let old = SpokenWordDriverControl()
    let runtime = make(old, gate)
    let operation = identity()
    let start = startResult(runtime, operation)
    await observed(old.enqueued)
    old.send(.started)
    _ = await start.value
    let acknowledgement = runtime.requestStop(id: operation.id)!
    old.send(.cancelled)
    _ = await acknowledgement.value()
    let successor = SpokenWordDriverControl()
    let nextRuntime = make(successor, gate)
    let next = identity()
    let nextStart = startResult(nextRuntime, next)
    await observed(successor.enqueued)
    old.send(.finished)
    XCTAssertNil(nextRuntime.requestStop(id: operation.id))
    XCTAssertEqual(gate.currentLease?.operationID, next.id)
    successor.send(.started)
    _ = await nextStart.value
    let nextStop = nextRuntime.requestStop(id: next.id)!
    successor.send(.cancelled)
    _ = await nextStop.value()
  }

  func testOtherHardwareOwnerRefusesBeforeFactoryAndUnavailableVoiceReleasesSafely() async throws {
    let gate = AudioHardwareOwnership()
    let lease = try gate.reserve(operationID: UUID(), owner: .capture)
    let control = SpokenWordDriverControl(failPreparation: true)
    let runtime = make(control, gate)
    let busy = await startResult(runtime, identity()).value
    XCTAssertEqual(busy, .busy)
    XCTAssertEqual(control.factoryCalls, 0)
    gate.release(lease)
    let unavailable = await startResult(runtime, identity()).value
    XCTAssertEqual(unavailable, .unavailable)
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(control.enqueues, 0)
  }

  func testReusedIDRemainsRejectedAfterAnInterveningOperation() async {
    let control = SpokenWordDriverControl()
    let first = identity()
    let secondControl = SpokenWordDriverControl()
    let runtime = PracticeSpokenWordRuntime(ownership: AudioHardwareOwnership()) {
      operation, event in
      (operation.id == first.id ? control : secondControl).make(operation, event)
    }
    let start = startResult(runtime, first)
    await observed(control.enqueued)
    control.send(.started)
    _ = await start.value
    let stop = runtime.requestStop(id: first.id)!
    control.send(.cancelled)
    _ = await stop.value()
    let second = identity()
    let secondStart = startResult(runtime, second)
    await observed(secondControl.enqueued)
    secondControl.send(.started)
    _ = await secondStart.value
    let secondStop = runtime.requestStop(id: second.id)!
    secondControl.send(.cancelled)
    _ = await secondStop.value()
    let refused = await startResult(runtime, first).value
    XCTAssertEqual(refused, .reusedOperationID)
    XCTAssertEqual(control.factoryCalls + secondControl.factoryCalls, 2)
  }

  private func identity() -> PracticeSpokenWordOperation { .init(id: UUID(), word: "bread") }
  private func make(
    _ control: SpokenWordDriverControl, _ gate: AudioHardwareOwnership,
    startupWait: TimeInterval = 5, cleanupWait: TimeInterval = 3
  ) -> PracticeSpokenWordRuntime {
    PracticeSpokenWordRuntime(ownership: gate, startupWait: startupWait, cleanupWait: cleanupWait) {
      operation, event in control.make(operation, event)
    }
  }
  private func startResult(
    _ runtime: PracticeSpokenWordRuntime, _ operation: PracticeSpokenWordOperation
  ) -> Task<PracticeSpokenWordError?, Never> {
    Task { @MainActor in
      do {
        try await runtime.start(operation)
        return nil
      } catch {
        let typed = error as? PracticeSpokenWordError
        XCTAssertNotNil(typed, "Unexpected spoken start error type")
        return typed
      }
    }
  }
  private func observed(_ expectation: XCTestExpectation) async {
    let result = await XCTWaiter.fulfillment(of: [expectation], timeout: 2)
    XCTAssertEqual(result, .completed)
  }
}

/// Shared controlled driver for the two focused classes. It never calls AVFoundation.
final class SpokenWordDriverControl: @unchecked Sendable {
  let prepared = XCTestExpectation(description: "driver preparing")
  let enqueued = XCTestExpectation(description: "utterance enqueued")
  let stopped = XCTestExpectation(description: "stop requested")
  private let lock = NSLock()
  private let preparation = DispatchSemaphore(value: 0)
  private let holdPreparation: Bool
  private let failPreparation: Bool
  private var failDeactivationOnce: Bool
  private var callback: (@Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void)?
  private var operation: PracticeSpokenWordOperation?
  private var counts: [String: Int] = [:]
  private var mainThread = false
  var factoryCalls: Int { count("factory") }
  var enqueues: Int { count("enqueue") }
  var stopRequests: Int { count("stop") }
  var disposals: Int { count("dispose") }
  var deactivations: Int { count("deactivate") }
  var calledOnMainThread: Bool { lock.withLock { mainThread } }

  init(
    holdPreparation: Bool = false, failPreparation: Bool = false,
    failDeactivationOnce: Bool = false
  ) {
    self.holdPreparation = holdPreparation
    self.failPreparation = failPreparation
    self.failDeactivationOnce = failDeactivationOnce
  }
  func make(
    _ operation: PracticeSpokenWordOperation,
    _ callback: @escaping @Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void
  ) -> any PracticeSpokenWordDriver {
    note("factory")
    lock.withLock {
      self.operation = operation
      self.callback = callback
    }
    return Driver(self)
  }
  func send(_ event: PracticeSpokenWordEvent, operation: PracticeSpokenWordOperation? = nil) {
    let saved = lock.withLock { (callback, operation ?? self.operation) }
    if let callback = saved.0, let identity = saved.1 { callback(identity, event) }
  }
  func releasePreparation() { preparation.signal() }
  private func count(_ name: String) -> Int { lock.withLock { counts[name, default: 0] } }
  private func note(_ name: String) {
    lock.withLock {
      counts[name, default: 0] += 1
      mainThread = mainThread || Thread.isMainThread
    }
  }
  private final class Driver: PracticeSpokenWordDriver {
    let control: SpokenWordDriverControl
    init(_ control: SpokenWordDriverControl) { self.control = control }
    func prepare() throws {
      control.note("prepare")
      control.prepared.fulfill()
      if control.holdPreparation {
        guard control.preparation.wait(timeout: .now() + 2) == .success else {
          throw PracticeSpokenWordError.unavailable
        }
      }
      if control.failPreparation { throw PracticeSpokenWordError.unavailable }
    }
    func enqueue() {
      control.note("enqueue")
      control.enqueued.fulfill()
    }
    func requestStop() {
      control.note("stop")
      if control.count("stop") == 1 { control.stopped.fulfill() }
    }
    func dispose() throws { control.note("dispose") }
    func deactivate() throws {
      control.note("deactivate")
      let fails = control.lock.withLock {
        let fails = control.failDeactivationOnce
        control.failDeactivationOnce = false
        return fails
      }
      if fails { throw PracticeSpokenWordError.cleanupUnconfirmed }
    }
  }
}
