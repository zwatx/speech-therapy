import Dispatch
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class PracticePlaybackRuntimeTests: XCTestCase {
  func testBlockedFactoryActivationAndPreparationPermitMainActorCancellationBeforePlay() async {
    for stage in [ControlledPlaybackDriver.Stage.factory, .activate, .prepare] {
      let driver = ControlledPlaybackDriver(blocked: [stage, .stop, .deactivate])
      defer { driver.releaseAll() }
      let gate = AudioHardwareOwnership()
      let runtime = makeRuntime(driver, gate: gate)
      let id = UUID()
      let url = testURL()
      let start = startResult(runtime, id: id, url: url)
      await entered(driver, stage)
      var heartbeat = false
      await Task { @MainActor in heartbeat = true }.value
      XCTAssertTrue(heartbeat)
      XCTAssertEqual(runtime.state, .preparing(.init(id: id, url: url)))
      let ack = runtime.requestStop(id: id)!
      XCTAssertEqual(runtime.state, .stopping(.init(id: id, url: url)))
      XCTAssertTrue(ack === runtime.requestStop(id: id))
      driver.release(stage)
      await entered(driver, .stop)
      XCTAssertNotNil(gate.currentLease)
      XCTAssertNil(ack.receipt)
      XCTAssertEqual(driver.count(.play), 0)
      assertCaptureBusy(gate)
      driver.release(.stop)
      await entered(driver, .deactivate)
      XCTAssertNotNil(gate.currentLease)
      XCTAssertNil(ack.receipt)
      driver.release(.deactivate)
      let receipt = await ack.value()
      XCTAssertEqual(receipt.result, .released)
      XCTAssertEqual(receipt.operation.url, url)
      XCTAssertNil(gate.currentLease)
      let awaitedResult1 = await start.value
      XCTAssertEqual(awaitedResult1, .cancelled(.init(id: id, url: url)))
      XCTAssertEqual(runtime.state, .idle)
      XCTAssertFalse(driver.calledOnMainThread)
    }
  }

  func testCommittedPlayCancellationKeepsOwnershipUntilStopAndDeactivationReturn() async {
    let driver = ControlledPlaybackDriver(blocked: [.play, .stop, .deactivate])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let runtime = makeRuntime(driver, gate: gate)
    let id = UUID()
    let url = testURL()
    let start = startResult(runtime, id: id, url: url)
    await entered(driver, .play)
    let ack = runtime.requestStop(id: id)!
    XCTAssertEqual(runtime.state, .stopping(.init(id: id, url: url)))
    XCTAssertNil(ack.receipt)
    XCTAssertNotNil(gate.currentLease)
    // Play already entered: this proves pending cleanup, never absence of audible output.
    XCTAssertEqual(driver.count(.play), 1)
    driver.release(.play)
    await entered(driver, .stop)
    assertCaptureBusy(gate)
    let second = makeRuntime(ControlledPlaybackDriver(), gate: gate)
    let error = await startResult(second, id: UUID(), url: testURL()).value
    XCTAssertEqual(error, .busy)
    XCTAssertEqual(driver.count(.releaseResources), 0)
    driver.release(.stop)
    await entered(driver, .deactivate)
    XCTAssertEqual(driver.count(.releaseResources), 1)
    XCTAssertNil(ack.receipt)
    driver.release(.deactivate)
    let awaitedResult2 = (await ack.value()).result
    XCTAssertEqual(awaitedResult2, .released)
    let awaitedResult3 = await start.value
    XCTAssertEqual(awaitedResult3, .cancelled(.init(id: id, url: url)))
  }

  func testSuccessfulStartDuplicateStopWaitersAndStaleStopDoNotCancelSuccessor() async throws {
    let firstDriver = ControlledPlaybackDriver(blocked: [.stop])
    defer { firstDriver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let first = makeRuntime(firstDriver, gate: gate)
    let id = UUID()
    let url = testURL()
    var completions = 0
    try await first.startPlayback(id: id, url: url) { _, _ in completions += 1 }
    XCTAssertEqual(first.state, .playing(.init(id: id, url: url)))
    let ack = first.requestStop(id: id)!
    let duplicate = first.requestStop(id: id)!
    XCTAssertTrue(ack === duplicate)
    let waiter1 = Task { await ack.value() }
    let waiter2 = Task { await duplicate.value() }
    await entered(firstDriver, .stop)
    firstDriver.finish(success: true)
    firstDriver.finish(success: false)
    XCTAssertNil(ack.receipt)
    firstDriver.release(.stop)
    let receipt1 = await waiter1.value
    let receipt2 = await waiter2.value
    XCTAssertEqual(receipt1, receipt2)
    XCTAssertEqual(firstDriver.count(.stop), 1)
    XCTAssertEqual(completions, 0)
    let successorDriver = ControlledPlaybackDriver()
    defer { successorDriver.releaseAll() }
    let successor = makeRuntime(successorDriver, gate: gate)
    let successorID = UUID()
    let successorURL = testURL()
    try await successor.startPlayback(id: successorID, url: successorURL) { _, _ in }
    XCTAssertTrue(ack === first.requestStop(id: id))
    XCTAssertNil(successor.requestStop(id: id))
    // Releasing callbacks from the previous driver must not touch the successor's reservation.
    firstDriver.finish(success: true)
    XCTAssertEqual(gate.currentLease?.operationID, successorID)
    let successorAck = successor.requestStop(id: successorID)!
    let awaitedResult4 = (await successorAck.value()).result
    XCTAssertEqual(awaitedResult4, .released)
    XCTAssertEqual(successorDriver.count(.stop), 1)
  }

  func testFalsePrepareFalsePlayAndThrowingStagesAutomaticallyCleanBeforeStartFailure() async {
    for failure in [
      ControlledPlaybackDriver.Failure.falsePrepare, .falsePlay, .throwActivate,
      .throwPrepare, .throwPlay, .throwFactory,
    ] {
      let driver = ControlledPlaybackDriver(failure: failure)
      defer { driver.releaseAll() }
      let gate = AudioHardwareOwnership()
      let runtime = makeRuntime(driver, gate: gate)
      let id = UUID()
      let url = testURL()
      let error = await startResult(runtime, id: id, url: url).value
      XCTAssertEqual(error, .couldNotStart(.init(id: id, url: url)))
      XCTAssertEqual(runtime.state, .idle)
      XCTAssertNil(gate.currentLease)
      if failure != .throwFactory {
        XCTAssertEqual(driver.count(.stop), 1)
        XCTAssertEqual(driver.count(.releaseResources), 1)
        XCTAssertEqual(driver.count(.deactivate), 1)
      }
      if failure == .falsePrepare || failure == .throwPrepare || failure == .throwActivate {
        XCTAssertEqual(driver.count(.play), 0)
      }
    }
  }

  func testCleanupFailureRetainsExactLeaseAndDuplicateNegativeAckUntilExplicitRetry() async {
    for failedStage in [ControlledPlaybackDriver.Stage.stop, .releaseResources, .deactivate] {
      let driver = ControlledPlaybackDriver(failure: .cleanupOnce(failedStage))
      defer { driver.releaseAll() }
      let gate = AudioHardwareOwnership()
      let runtime = makeRuntime(driver, gate: gate)
      let id = UUID()
      let url = testURL()
      let awaitedResult5 = await startResult(runtime, id: id, url: url).value
      XCTAssertNil(awaitedResult5)
      let lease = gate.currentLease
      let original = runtime.requestStop(id: id)!
      let receipt = await original.value()
      XCTAssertEqual(receipt.result, .cleanupUnconfirmed)
      XCTAssertEqual(receipt.operation, .init(id: id, url: url))
      XCTAssertEqual(runtime.state, .cleanupBlocked(.init(id: id, url: url)))
      XCTAssertEqual(gate.currentLease, lease)
      XCTAssertTrue(original === runtime.requestStop(id: id))
      let awaitedResult6 = (await original.value()).result
      XCTAssertEqual(awaitedResult6, .cleanupUnconfirmed)
      XCTAssertEqual(driver.count(failedStage), 1)
      assertCaptureBusy(gate)
      let retry = runtime.retryCleanup(id: id)!
      XCTAssertTrue(retry === runtime.retryCleanup(id: id))
      XCTAssertTrue(original === runtime.requestStop(id: id))
      let awaitedResult7 = (await retry.value()).result
      XCTAssertEqual(awaitedResult7, .released)
      XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
      XCTAssertNil(gate.currentLease)
      XCTAssertEqual(driver.count(failedStage), 2)
      if failedStage == .deactivate {
        XCTAssertEqual(driver.count(.stop), 1)
        XCTAssertEqual(driver.count(.releaseResources), 1)
      }
    }
  }

  func testStartupCleanupFailureIsDistinctFromCouldNotStart() async {
    let driver = ControlledPlaybackDriver(failure: .falsePrepareAndDeactivateOnce)
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let runtime = makeRuntime(driver, gate: gate)
    let id = UUID()
    let url = testURL()
    let error = await startResult(runtime, id: id, url: url).value
    XCTAssertEqual(error, .cleanupUnconfirmed(.init(id: id, url: url)))
    XCTAssertNotNil(gate.currentLease)
    let ack = runtime.retryCleanup(id: id)!
    let awaitedResult8 = (await ack.value()).result
    XCTAssertEqual(awaitedResult8, .released)
    XCTAssertNil(gate.currentLease)
  }

  func testDelegateEndFailureAndDuplicateCallbacksCleanExactlyOnceBeforeCompletion() async throws {
    for success in [true, false] {
      let driver = ControlledPlaybackDriver(blocked: [.deactivate])
      defer { driver.releaseAll() }
      let gate = AudioHardwareOwnership()
      let runtime = makeRuntime(driver, gate: gate)
      let id = UUID()
      let url = testURL()
      let finished = expectation(description: "finished after deactivation")
      var completions: [(PracticePlaybackOperation, Bool)] = []
      try await runtime.startPlayback(id: id, url: url) { identity, result in
        completions.append((identity, result))
        XCTAssertNil(gate.currentLease)
        finished.fulfill()
      }
      driver.finish(success: success)
      driver.finish(success: !success)
      await entered(driver, .deactivate)
      XCTAssertTrue(completions.isEmpty)
      XCTAssertNotNil(gate.currentLease)
      driver.release(.deactivate)
      let awaitedResult9 = await XCTWaiter.fulfillment(of: [finished], timeout: 2)
      XCTAssertEqual(awaitedResult9, .completed)
      XCTAssertEqual(completions.count, 1)
      XCTAssertEqual(completions.first?.0, .init(id: id, url: url))
      XCTAssertEqual(completions.first?.1, success)
      XCTAssertEqual(driver.count(.stop), 1)
    }
  }

  func testFacadeDisappearanceAndCancelledAwaitingTaskKeepCleanupOwned() async throws {
    let driver = ControlledPlaybackDriver(blocked: [.stop, .deactivate])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    var runtime: PracticePlaybackRuntime? = makeRuntime(driver, gate: gate)
    weak var weakRuntime = runtime
    let id = UUID()
    let url = testURL()
    try await runtime!.startPlayback(id: id, url: url) { _, _ in }
    let ack = runtime!.requestStop(id: id)!
    let waiter = Task { await ack.value() }
    waiter.cancel()
    runtime = nil
    await entered(driver, .stop)
    XCTAssertNotNil(weakRuntime)
    assertCaptureBusy(gate)
    driver.release(.stop)
    await entered(driver, .deactivate)
    XCTAssertNil(ack.receipt)
    driver.release(.deactivate)
    let receipt = await waiter.value
    XCTAssertEqual(receipt.result, .released)
    XCTAssertNil(gate.currentLease)
  }

  func testTaskCancellationWhileActivationIsBlockedRevokesWithoutWaitingForQueue() async {
    let driver = ControlledPlaybackDriver(blocked: [.activate])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let runtime = makeRuntime(driver, gate: gate)
    let id = UUID()
    let url = testURL()
    let start = startResult(runtime, id: id, url: url)
    await entered(driver, .activate)
    start.cancel()
    let ack = runtime.requestStop(id: id)!
    XCTAssertNil(ack.receipt)
    driver.release(.activate)
    let receipt = await ack.value()
    let error = await start.value
    XCTAssertEqual(receipt.result, .released)
    XCTAssertEqual(error, .cancelled(.init(id: id, url: url)))
    XCTAssertEqual(driver.count(.prepare), 0)
    XCTAssertEqual(driver.count(.play), 0)
  }

  func testCaptureReservationPreventsFactoryAndWrongLeaseCannotRelease() async throws {
    let gate = AudioHardwareOwnership()
    let capture = try gate.reserve(operationID: UUID(), owner: .capture)
    let unrelatedGate = AudioHardwareOwnership()
    let unrelated = try unrelatedGate.reserve(operationID: capture.operationID, owner: .capture)
    XCTAssertFalse(gate.release(unrelated))
    let driver = ControlledPlaybackDriver()
    defer { driver.releaseAll() }
    let runtime = makeRuntime(driver, gate: gate)
    let awaitedResult10 = await startResult(runtime, id: UUID(), url: testURL()).value
    XCTAssertEqual(awaitedResult10, .busy)
    XCTAssertEqual(driver.count(.factory), 0)
    XCTAssertEqual(gate.currentLease, capture)
    XCTAssertTrue(gate.release(capture))
  }

  func testSameRuntimeSuccessorRejectsStaleStopAndOldCallback() async throws {
    let firstID = UUID()
    let successorID = UUID()
    let firstDriver = ControlledPlaybackDriver()
    let successorDriver = ControlledPlaybackDriver(blocked: [.stop])
    defer {
      firstDriver.releaseAll()
      successorDriver.releaseAll()
    }
    let gate = AudioHardwareOwnership()
    let drivers = [firstID: firstDriver, successorID: successorDriver]
    let runtime = PracticePlaybackRuntime(ownership: gate) { operation, finish in
      guard let driver = drivers[operation.id] else {
        throw ControlledPlaybackDriver.ControlledError.failure
      }
      try driver.make(operation: operation, finish: finish)
      return driver
    }
    let oldURL = testURL()
    try await runtime.startPlayback(id: firstID, url: oldURL) { _, _ in
      XCTFail("Stopped old operation must not finish the successor")
    }
    let oldAck = runtime.requestStop(id: firstID)!
    let oldReceipt = await oldAck.value()
    XCTAssertEqual(oldReceipt.result, .released)
    let successorURL = testURL()
    try await runtime.startPlayback(id: successorID, url: successorURL) { _, _ in
      XCTFail("Explicitly stopped successor must not publish completion")
    }
    let successorLease = gate.currentLease
    XCTAssertTrue(oldAck === runtime.requestStop(id: firstID))
    firstDriver.finish(success: true)
    firstDriver.finish(success: false)
    XCTAssertEqual(runtime.state, .playing(.init(id: successorID, url: successorURL)))
    XCTAssertEqual(gate.currentLease, successorLease)
    XCTAssertEqual(successorDriver.count(.stop), 0)
    let successorAck = runtime.requestStop(id: successorID)!
    await entered(successorDriver, .stop)
    XCTAssertEqual(gate.currentLease, successorLease)
    successorDriver.release(.stop)
    let successorReceipt = await successorAck.value()
    XCTAssertEqual(successorReceipt.result, .released)
    XCTAssertEqual(successorReceipt.operation.id, successorID)
    XCTAssertEqual(firstDriver.count(.stop), 1)
    XCTAssertEqual(successorDriver.count(.stop), 1)
  }

  func testHeldResourceReleasePreventsDeactivationAndLeaseRelease() async throws {
    let driver = ControlledPlaybackDriver(blocked: [.releaseResources])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let runtime = makeRuntime(driver, gate: gate)
    let id = UUID()
    let url = testURL()
    try await runtime.startPlayback(id: id, url: url) { _, _ in }
    let lease = gate.currentLease
    let ack = runtime.requestStop(id: id)!
    await entered(driver, .releaseResources)
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.deactivate), 0)
    XCTAssertNil(ack.receipt)
    XCTAssertEqual(gate.currentLease, lease)
    assertCaptureBusy(gate)
    driver.release(.releaseResources)
    let receipt = await ack.value()
    XCTAssertEqual(receipt.result, .released)
    XCTAssertEqual(driver.count(.deactivate), 1)
    XCTAssertNil(gate.currentLease)
  }

  func testNaturalFinishFailedCleanupRetryCompletesOnceUnlessExplicitStopRevokes() async throws {
    for stopBeforeRetry in [false, true] {
      let driver = ControlledPlaybackDriver(failure: .cleanupOnce(.deactivate))
      defer { driver.releaseAll() }
      let gate = AudioHardwareOwnership()
      let runtime = makeRuntime(driver, gate: gate)
      let id = UUID()
      let url = testURL()
      var completions: [(PracticePlaybackOperation, Bool)] = []
      try await runtime.startPlayback(id: id, url: url) { identity, success in
        completions.append((identity, success))
      }
      driver.finish(success: false)
      driver.finish(success: true)
      await waitForState(runtime, .cleanupBlocked(.init(id: id, url: url)))
      XCTAssertTrue(completions.isEmpty)
      XCTAssertNotNil(gate.currentLease)
      if stopBeforeRetry {
        let original = runtime.requestStop(id: id)!
        let negative = await original.value()
        XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      }
      let retry = runtime.retryCleanup(id: id)!
      let receipt = await retry.value()
      XCTAssertEqual(receipt.result, .released)
      XCTAssertNil(gate.currentLease)
      XCTAssertEqual(completions.count, stopBeforeRetry ? 0 : 1)
      if !stopBeforeRetry {
        XCTAssertEqual(completions.first?.0, .init(id: id, url: url))
        XCTAssertEqual(completions.first?.1, false)
      }
      driver.finish(success: true)
      let original = runtime.requestStop(id: id)!
      XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
      XCTAssertNil(runtime.retryCleanup(id: id))
      XCTAssertEqual(completions.count, stopBeforeRetry ? 0 : 1)
      XCTAssertEqual(driver.count(.stop), 1)
      XCTAssertEqual(driver.count(.releaseResources), 1)
      XCTAssertEqual(driver.count(.deactivate), 2)
    }
  }

  func testRepeatedExplicitCleanupFailuresKeepOriginalReceiptAndDistinctRetryReceipts() async throws
  {
    let driver = ControlledPlaybackDriver(failure: .cleanupAttempts(.deactivate, 3))
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let runtime = makeRuntime(driver, gate: gate)
    let id = UUID()
    let url = testURL()
    try await runtime.startPlayback(id: id, url: url) { _, _ in }
    let lease = gate.currentLease
    let original = runtime.requestStop(id: id)!
    let originalReceipt = await original.value()
    XCTAssertEqual(originalReceipt.result, .cleanupUnconfirmed)
    var previous = original
    for attempt in 2...4 {
      let retry = runtime.retryCleanup(id: id)!
      XCTAssertFalse(retry === previous)
      XCTAssertTrue(retry === runtime.retryCleanup(id: id))
      let receipt = await retry.value()
      XCTAssertEqual(receipt.result, attempt == 4 ? .released : .cleanupUnconfirmed)
      XCTAssertEqual(driver.count(.deactivate), attempt)
      XCTAssertEqual(original.receipt, originalReceipt)
      XCTAssertTrue(original === runtime.requestStop(id: id))
      if attempt < 4 {
        XCTAssertEqual(gate.currentLease, lease)
        XCTAssertEqual(runtime.state, .cleanupBlocked(.init(id: id, url: url)))
        assertCaptureBusy(gate)
      }
      previous = retry
    }
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(runtime.state, .idle)
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.releaseResources), 1)
  }

  func testTaskCancellationHandlerAloneStopsBlockedActivation() async {
    let driver = ControlledPlaybackDriver(blocked: [.activate, .stop])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let runtime = makeRuntime(driver, gate: gate)
    let id = UUID()
    let url = testURL()
    let start = startResult(runtime, id: id, url: url)
    await entered(driver, .activate)
    start.cancel()
    await waitForState(runtime, .stopping(.init(id: id, url: url)))
    XCTAssertNotNil(gate.currentLease)
    driver.release(.activate)
    await entered(driver, .stop)
    XCTAssertEqual(driver.count(.prepare), 0)
    XCTAssertEqual(driver.count(.play), 0)
    driver.release(.stop)
    let error = await start.value
    XCTAssertEqual(error, .cancelled(.init(id: id, url: url)))
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(runtime.state, .idle)
    // This test never calls requestStop: only the actual task-cancellation handler revoked it.
  }

  func testExactBorrowedFixtureSurvivesHeldAndFailedCleanupAndRouteStartupScan() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = TemporaryRecordingStore(directory: directory)
    let url = store.makeRecordingURL()
    let stale = store.makeRecordingURL()
    // Generated fixture bytes are never passed to AVFoundation or a physical audio renderer.
    let bytes = Data([
      0x52, 0x49, 0x46, 0x46, 38, 0, 0, 0, 0x57, 0x41, 0x56, 0x45,
      0x66, 0x6D, 0x74, 0x20, 16, 0, 0, 0, 1, 0, 1, 0,
      0x80, 0x3E, 0, 0, 0, 0x7D, 0, 0, 2, 0, 16, 0,
      0x64, 0x61, 0x74, 0x61, 2, 0, 0, 0, 0, 0,
    ])
    try bytes.write(to: url)
    try bytes.write(to: stale)
    let registry = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let driver = ControlledPlaybackDriver(
      blocked: [.stop, .releaseResources, .deactivate], failure: .cleanupOnce(.deactivate))
    defer { driver.releaseAll() }
    var runtime: PracticePlaybackRuntime? = makeRuntime(driver, gate: gate)
    let fixture = ControlledPlaybackFileOwner(url: url, runtime: runtime!, registry: registry)
    let start = startResult(runtime!, id: fixture.operationID, url: url)
    let startupError = await start.value
    XCTAssertNil(startupError)
    let ack = runtime!.requestStop(id: fixture.operationID)!
    runtime = nil
    await entered(driver, .stop)
    XCTAssertNil(ack.receipt)
    XCTAssertFalse(registry.canRemove(url, owner: fixture.ownerID))
    let unrelatedReceipt = PracticePlaybackCleanupReceipt(
      operation: .init(id: UUID(), url: url), result: .released)
    XCTAssertFalse(try fixture.removeAfterReleasedReceipt(unrelatedReceipt, store: store))
    XCTAssertFalse(registry.canRemove(url, owner: fixture.ownerID))
    XCTAssertTrue(registry.protectedURLs.contains(url.standardizedFileURL))
    var scans = 0
    try registry.cleanStartupOnce(directory: directory) { protected in
      scans += 1
      try store.removeStaleRecordings(excluding: protected)
    }
    XCTAssertEqual(try Data(contentsOf: url), bytes)
    XCTAssertFalse(FileManager.default.fileExists(atPath: stale.path))
    let recreatedDriver = ControlledPlaybackDriver()
    defer { recreatedDriver.releaseAll() }
    let recreatedRuntime = makeRuntime(recreatedDriver, gate: gate)
    let busy = await startResult(recreatedRuntime, id: UUID(), url: url).value
    XCTAssertEqual(busy, .busy)
    XCTAssertEqual(recreatedDriver.count(.factory), 0)
    try registry.cleanStartupOnce(directory: directory) { _ in
      scans += 1
      XCTFail("Route recreation must not repeat the process startup scan")
    }
    XCTAssertEqual(scans, 1)
    driver.release(.stop)
    await entered(driver, .releaseResources)
    XCTAssertNil(ack.receipt)
    XCTAssertEqual(driver.count(.deactivate), 0)
    XCTAssertEqual(try Data(contentsOf: url), bytes)
    XCTAssertFalse(registry.canRemove(url, owner: fixture.ownerID))
    driver.release(.releaseResources)
    await entered(driver, .deactivate)
    XCTAssertNil(ack.receipt)
    XCTAssertEqual(try Data(contentsOf: url), bytes)
    driver.release(.deactivate)
    let negative = await ack.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertFalse(try fixture.removeAfterReleasedReceipt(negative, store: store))
    XCTAssertFalse(registry.canRemove(url, owner: fixture.ownerID))
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    XCTAssertNotNil(gate.currentLease)
    // The fixture owner retains a reachable runtime/retry path after failed cleanup.
    let retry = fixture.runtime.retryCleanup(id: fixture.operationID)!
    let released = await retry.value()
    XCTAssertEqual(released.result, .released)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(try fixture.removeAfterReleasedReceipt(released, store: store))
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertFalse(registry.protectedURLs.contains(url.standardizedFileURL))
    XCTAssertEqual(ack.receipt, negative)
    XCTAssertFalse(try fixture.removeAfterReleasedReceipt(negative, store: store))
  }

  private func waitForState(
    _ runtime: PracticePlaybackRuntime, _ state: PracticePlaybackRuntimeState
  ) async {
    let deadline = ContinuousClock.now + .seconds(2)
    while runtime.state != state && ContinuousClock.now < deadline { await Task.yield() }
    XCTAssertEqual(runtime.state, state)
  }

  private func entered(_ driver: ControlledPlaybackDriver, _ stage: ControlledPlaybackDriver.Stage)
    async
  {
    let result = await XCTWaiter.fulfillment(of: [driver.entered(stage)], timeout: 2)
    XCTAssertEqual(result, .completed)
  }

  private func testURL() -> URL { URL(fileURLWithPath: "/controlled-test/\(UUID()).wav") }

  private func makeRuntime(_ driver: ControlledPlaybackDriver, gate: AudioHardwareOwnership)
    -> PracticePlaybackRuntime
  {
    PracticePlaybackRuntime(ownership: gate) { operation, finish in
      try driver.make(operation: operation, finish: finish)
      return driver
    }
  }

  private func startResult(_ runtime: PracticePlaybackRuntime, id: UUID, url: URL)
    -> Task<PracticePlaybackRuntimeError?, Never>
  {
    Task { @MainActor in
      do {
        try await runtime.startPlayback(id: id, url: url) { _, _ in
          XCTFail("Cancelled/failed startup must not publish completion")
        }
        return nil
      } catch {
        guard let expected = error as? PracticePlaybackRuntimeError else {
          XCTFail("Unexpected playback error type: \(type(of: error))")
          return nil
        }
        return expected
      }
    }
  }

  private func assertCaptureBusy(_ gate: AudioHardwareOwnership) {
    XCTAssertThrowsError(try gate.reserve(operationID: UUID(), owner: .capture)) { error in
      XCTAssertNotNil(error as? AudioHardwareOwnership.Busy)
    }
  }
}

/// Test-only synchronized controls; production driver calls still enter the actual queue wrapper.
private final class ControlledPlaybackDriver: PracticePlaybackDriver, @unchecked Sendable {
  enum Stage: CaseIterable, Hashable {
    case factory, activate, prepare, play, stop, releaseResources, deactivate
  }
  enum Failure: Equatable {
    case falsePrepare, falsePlay, throwFactory, throwActivate, throwPrepare, throwPlay
    case cleanupOnce(Stage)
    case cleanupAttempts(Stage, Int)
    case falsePrepareAndDeactivateOnce
  }
  enum ControlledError: Error { case failure, gateTimedOut }

  private let lock = NSLock()
  private let blocked: Set<Stage>
  private let failure: Failure?
  private let gates: [Stage: DispatchSemaphore]
  private let expectations: [Stage: XCTestExpectation]
  private var counts: [Stage: Int] = [:]
  private var observedMainThread = false
  private var callback: (@Sendable (PracticePlaybackOperation, Bool) -> Void)?
  private var identity: PracticePlaybackOperation?

  init(blocked: Set<Stage> = [], failure: Failure? = nil) {
    self.blocked = blocked
    self.failure = failure
    gates = Dictionary(
      uniqueKeysWithValues: Stage.allCases.map { ($0, DispatchSemaphore(value: 0)) })
    expectations = Dictionary(
      uniqueKeysWithValues: Stage.allCases.map {
        ($0, XCTestExpectation(description: "entered \($0)"))
      })
  }

  var calledOnMainThread: Bool { lock.withLock { observedMainThread } }
  func count(_ stage: Stage) -> Int { lock.withLock { counts[stage, default: 0] } }
  func entered(_ stage: Stage) -> XCTestExpectation { expectations[stage]! }
  func release(_ stage: Stage) { gates[stage]!.signal() }
  func releaseAll() { for stage in Stage.allCases { release(stage) } }

  func make(
    operation: PracticePlaybackOperation,
    finish: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) throws {
    lock.withLock {
      identity = operation
      callback = finish
    }
    try visit(.factory)
    if failure == .throwFactory { throw ControlledError.failure }
  }
  func activate() throws {
    try visit(.activate)
    if failure == .throwActivate { throw ControlledError.failure }
  }
  func prepare() throws -> Bool {
    try visit(.prepare)
    if failure == .throwPrepare { throw ControlledError.failure }
    return failure != .falsePrepare && failure != .falsePrepareAndDeactivateOnce
  }
  func play() throws -> Bool {
    try visit(.play)
    if failure == .throwPlay { throw ControlledError.failure }
    return failure != .falsePlay
  }
  func stop() throws { try visit(.stop) }
  func releasePlaybackResources() throws { try visit(.releaseResources) }
  func deactivate() throws { try visit(.deactivate) }

  func finish(success: Bool) {
    let values = lock.withLock { (identity, callback) }
    if let identity = values.0 { values.1?(identity, success) }
  }

  private func visit(_ stage: Stage) throws {
    let count = lock.withLock {
      counts[stage, default: 0] += 1
      observedMainThread = observedMainThread || Thread.isMainThread
      return counts[stage]!
    }
    if count == 1 { expectations[stage]!.fulfill() }
    if blocked.contains(stage), count == 1,
      gates[stage]!.wait(timeout: .now() + 5) != .success
    {
      throw ControlledError.gateTimedOut
    }
    if case .cleanupAttempts(let failedStage, let attempts)? = failure,
      stage == failedStage, count <= attempts
    {
      throw ControlledError.failure
    }
    if count == 1,
      failure == .cleanupOnce(stage)
        || (failure == .falsePrepareAndDeactivateOnce && stage == .deactivate)
    {
      throw ControlledError.failure
    }
  }
}

/// A controlled fixture owner, not an assertion that current production routes are integrated.
@MainActor
private final class ControlledPlaybackFileOwner {
  let ownerID = UUID()
  let operationID = UUID()
  let url: URL
  let runtime: PracticePlaybackRuntime
  private let registry: ProcessAudioFileOwnership

  init(url: URL, runtime: PracticePlaybackRuntime, registry: ProcessAudioFileOwnership) {
    self.url = url
    self.runtime = runtime
    self.registry = registry
    registry.retain(url, owner: ownerID)
    precondition(registry.borrow(url, operation: operationID))
  }

  func removeAfterReleasedReceipt(
    _ receipt: PracticePlaybackCleanupReceipt, store: TemporaryRecordingStore
  ) throws -> Bool {
    guard receipt.operation == PracticePlaybackOperation(id: operationID, url: url),
      receipt.result == .released
    else { return false }
    registry.finishBorrowing(operation: operationID)
    guard registry.canRemove(url, owner: ownerID) else { return false }
    try store.removeRecordingIfPresent(at: url)
    registry.didRemove(url, owner: ownerID)
    return true
  }
}
