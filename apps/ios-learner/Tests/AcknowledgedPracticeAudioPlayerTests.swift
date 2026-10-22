import Combine
import Dispatch
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class AcknowledgedPracticeAudioPlayerTests: XCTestCase {
  func testProductionFacadePublishesPreparingThenActualPlayAcknowledgementAndReleasedIdle()
    async throws
  {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(blocked: [.prepare])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    var states: [PracticePlaybackRuntimeState] = []
    let subscription = player.statePublisher.removeDuplicates().sink { state in
      MainActor.assertIsolated()
      states.append(state)
      if state == .preparing(operation) {
        XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
      }
      if state == .idle, states.count > 1 {
        XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
        XCTAssertNil(gate.currentLease)
      }
    }
    defer { subscription.cancel() }
    XCTAssertEqual(states, [.idle])
    let start = startResult(player, operation: operation)
    await entered(driver, .prepare)
    XCTAssertEqual(states, [.idle, .preparing(operation)])
    XCTAssertEqual(driver.count(.play), 0)
    XCTAssertNotNil(gate.currentLease)
    driver.release(.prepare)
    let error = await start.value
    XCTAssertNil(error)
    XCTAssertEqual(states, [.idle, .preparing(operation), .playing(operation)])
    XCTAssertEqual(driver.count(.play), 1)
    let ack = player.requestStop(id: operation.id)!
    let receipt = await ack.value()
    XCTAssertEqual(receipt.operation, operation)
    XCTAssertEqual(receipt.result, .released)
    XCTAssertEqual(
      states, [.idle, .preparing(operation), .playing(operation), .stopping(operation), .idle])
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
    XCTAssertEqual(try Data(contentsOf: fixture.url), fixture.bytes)
    XCTAssertFalse(driver.calledOnMainThread)
  }

  func testIntrinsicBorrowSurvivesHeldStopReleaseDeactivationAndFailedCleanupUntilExactRetry()
    async throws
  {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(
      blocked: [.stop, .releaseResources, .deactivate], deactivateFailures: 1)
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    try await player.play(id: operation.id, url: operation.url) { _, _ in }
    let lease = gate.currentLease
    let ack = player.requestStop(id: operation.id)!
    for stage in [AcknowledgedControlledDriver.Stage.stop, .releaseResources, .deactivate] {
      await entered(driver, stage)
      XCTAssertNil(ack.receipt)
      XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
      XCTAssertEqual(gate.currentLease, lease)
      XCTAssertEqual(try Data(contentsOf: fixture.url), fixture.bytes)
      driver.release(stage)
    }
    let negative = await ack.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertEqual(player.state, .cleanupBlocked(operation))
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    XCTAssertTrue(ack === player.requestStop(id: operation.id))
    XCTAssertNil(player.requestStop(id: UUID()))
    XCTAssertNil(player.retryCleanup(id: UUID()))
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    let retry = player.retryCleanup(id: operation.id)!
    let released = await retry.value()
    XCTAssertEqual(released.operation, operation)
    XCTAssertEqual(released.result, .released)
    XCTAssertEqual(ack.receipt, negative)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.releaseResources), 1)
    XCTAssertEqual(driver.count(.deactivate), 2)
    try fixture.removeOwnedFile(files: files)
    XCTAssertFalse(files.protectedURLs.contains(fixture.url.standardizedFileURL))
  }

  func testBusySecondFacadeCreatesNoDriverOrBorrowAndCanStartAfterRelease() async throws {
    let firstFixture = try AcknowledgedFileFixture()
    let secondFixture = try AcknowledgedFileFixture()
    defer {
      firstFixture.removeDirectory()
      secondFixture.removeDirectory()
    }
    let firstDriver = AcknowledgedControlledDriver(blocked: [.deactivate])
    let secondDriver = AcknowledgedControlledDriver()
    defer {
      firstDriver.releaseAll()
      secondDriver.releaseAll()
    }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(firstFixture.url, owner: firstFixture.ownerID)
    files.retain(secondFixture.url, owner: secondFixture.ownerID)
    let first = makePlayer(firstDriver, gate: gate, files: files)
    let second = makePlayer(secondDriver, gate: gate, files: files)
    let firstID = UUID()
    let secondID = UUID()
    try await first.play(id: firstID, url: firstFixture.url) { _, _ in }
    let ack = first.requestStop(id: firstID)!
    await entered(firstDriver, .deactivate)
    let error = await startResult(
      second, operation: .init(id: secondID, url: secondFixture.url)
    ).value
    XCTAssertEqual(error, .busy)
    XCTAssertEqual(secondDriver.count(.factory), 0)
    XCTAssertEqual(second.state, .idle)
    XCTAssertTrue(files.canRemove(secondFixture.url, owner: secondFixture.ownerID))
    XCTAssertFalse(files.canRemove(firstFixture.url, owner: firstFixture.ownerID))
    firstDriver.release(.deactivate)
    let receipt = await ack.value()
    XCTAssertEqual(receipt.result, .released)
    try await second.play(id: secondID, url: secondFixture.url) { _, _ in }
    XCTAssertEqual(secondDriver.count(.factory), 1)
    XCTAssertFalse(files.canRemove(secondFixture.url, owner: secondFixture.ownerID))
    let secondAck = second.requestStop(id: secondID)!
    let secondReceipt = await secondAck.value()
    XCTAssertEqual(secondReceipt.result, .released)
    XCTAssertTrue(files.canRemove(secondFixture.url, owner: secondFixture.ownerID))
  }

  func testFailedStartupReleasesBorrowOnlyWhenCleanupActuallySucceeds() async throws {
    for cleanupFails in [false, true] {
      let fixture = try AcknowledgedFileFixture()
      defer { fixture.removeDirectory() }
      let driver = AcknowledgedControlledDriver(
        prepareSucceeds: false, deactivateFailures: cleanupFails ? 1 : 0)
      defer { driver.releaseAll() }
      let gate = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      files.retain(fixture.url, owner: fixture.ownerID)
      let player = makePlayer(driver, gate: gate, files: files)
      let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
      let error = await startResult(player, operation: operation).value
      XCTAssertEqual(
        error, cleanupFails ? .cleanupUnconfirmed(operation) : .couldNotStart(operation))
      XCTAssertEqual(driver.count(.play), 0)
      XCTAssertEqual(files.canRemove(fixture.url, owner: fixture.ownerID), !cleanupFails)
      if cleanupFails {
        XCTAssertEqual(player.state, .cleanupBlocked(operation))
        XCTAssertNotNil(gate.currentLease)
        let retry = player.retryCleanup(id: operation.id)!
        let receipt = await retry.value()
        XCTAssertEqual(receipt.result, .released)
      }
      XCTAssertEqual(player.state, .idle)
      XCTAssertNil(gate.currentLease)
      XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
      XCTAssertEqual(try Data(contentsOf: fixture.url), fixture.bytes)
    }
  }

  func testConflictingBorrowRejectsBeforeQueueWorkAndPreservesExistingBorrow() async throws {
    let existingFixture = try AcknowledgedFileFixture()
    let proposedFixture = try AcknowledgedFileFixture()
    defer {
      existingFixture.removeDirectory()
      proposedFixture.removeDirectory()
    }
    let driver = AcknowledgedControlledDriver()
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(existingFixture.url, owner: existingFixture.ownerID)
    files.retain(proposedFixture.url, owner: proposedFixture.ownerID)
    let id = UUID()
    XCTAssertTrue(files.borrow(existingFixture.url, operation: id))
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: id, url: proposedFixture.url)
    let error = await startResult(player, operation: operation).value
    XCTAssertEqual(error, .couldNotStart(operation))
    XCTAssertEqual(driver.count(.factory), 0)
    XCTAssertNil(gate.currentLease)
    XCTAssertNil(gate.retryPlaybackCleanup())
    XCTAssertEqual(player.state, .idle)
    XCTAssertFalse(files.canRemove(existingFixture.url, owner: existingFixture.ownerID))
    XCTAssertTrue(files.canRemove(proposedFixture.url, owner: proposedFixture.ownerID))
    files.finishBorrowing(operation: id)
    XCTAssertTrue(files.canRemove(existingFixture.url, owner: existingFixture.ownerID))
    // A rejected request did not consume this ID or enqueue a delayed start.
    try await player.play(id: id, url: proposedFixture.url) { _, _ in }
    let ack = player.requestStop(id: id)!
    let receipt = await ack.value()
    XCTAssertEqual(receipt.result, .released)
  }

  func testSharedGateRecoveryAfterFacadeDisappearsReleasesIntrinsicBorrow() async throws {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(deactivateFailures: 2)
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    var player: SystemAcknowledgedPracticeAudioPlayer? = makePlayer(
      driver, gate: gate, files: files)
    weak var weakPlayer = player
    let id = UUID()
    try await player!.play(id: id, url: fixture.url) { _, _ in }
    let ack = player!.requestStop(id: id)!
    let negative = await ack.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    player = nil
    XCTAssertNil(weakPlayer)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    let retry1 = gate.retryPlaybackCleanup()!
    let negativeRetry = await retry1.value()
    XCTAssertEqual(negativeRetry.result, .cleanupUnconfirmed)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    let retry2 = gate.retryPlaybackCleanup()!
    let released = await retry2.value()
    XCTAssertEqual(released.operation, .init(id: id, url: fixture.url))
    XCTAssertEqual(released.result, .released)
    XCTAssertEqual(ack.receipt, negative)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
    XCTAssertNil(gate.currentLease)
    XCTAssertNil(gate.retryPlaybackCleanup())
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.releaseResources), 1)
    XCTAssertEqual(driver.count(.deactivate), 3)
    try fixture.removeOwnedFile(files: files)
  }

  func testNaturalFinishReleasesBorrowBeforeIdlePublicationAndFinishCallback() async throws {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(blocked: [.deactivate])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    let finished = expectation(description: "natural finish after intrinsic borrow release")
    var completionCount = 0
    var observedIdle = false
    let subscription = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      if state == .idle, driver.count(.factory) > 0 {
        observedIdle = true
        XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
        XCTAssertNil(gate.currentLease)
      }
    }
    defer { subscription.cancel() }
    try await player.play(id: operation.id, url: operation.url) { identity, success in
      completionCount += 1
      XCTAssertEqual(identity, operation)
      XCTAssertTrue(success)
      XCTAssertTrue(observedIdle)
      XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
      finished.fulfill()
    }
    driver.finish(success: true)
    driver.finish(success: false)
    await entered(driver, .deactivate)
    XCTAssertEqual(completionCount, 0)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    driver.release(.deactivate)
    let result = await XCTWaiter.fulfillment(of: [finished], timeout: 2)
    XCTAssertEqual(result, .completed)
    XCTAssertEqual(completionCount, 1)
    XCTAssertEqual(player.state, .idle)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
  }

  func testSynchronousPlayingSubscriberCancellationCannotAcknowledgeSuccessfulStart() async throws {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(blocked: [.stop])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    var acknowledgement: PracticePlaybackCleanup?
    let subscription = player.statePublisher.sink { state in
      if state == .playing(operation) { acknowledgement = player.requestStop(id: operation.id) }
    }
    defer { subscription.cancel() }
    let start = startResult(player, operation: operation)
    await entered(driver, .stop)
    XCTAssertNotNil(acknowledgement)
    XCTAssertNil(acknowledgement?.receipt)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    XCTAssertEqual(player.state, .stopping(operation))
    driver.release(.stop)
    let error = await start.value
    XCTAssertEqual(error, .cancelled(operation))
    XCTAssertEqual(acknowledgement?.receipt?.result, .released)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
  }

  func testSynchronousStoppingSubscriberDuplicateStopsJoinOneCleanupWithoutRepublishing()
    async throws
  {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(blocked: [.stop])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    var states: [PracticePlaybackRuntimeState] = []
    var joined: [PracticePlaybackCleanup] = []
    var stoppingCount = 0
    let subscription = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      states.append(state)
      guard state == .stopping(operation) else { return }
      stoppingCount += 1
      // Bound a broken recursive publisher so this regression fails instead of overflowing.
      guard stoppingCount <= 3 else {
        XCTFail("Duplicate stop recursively republishes stopping")
        return
      }
      if let ack = player.requestStop(id: operation.id) {
        joined.append(ack)
      } else {
        XCTFail("A reentrant stop must join the current acknowledgement")
      }
    }
    defer { subscription.cancel() }
    try await player.play(id: operation.id, url: operation.url) { _, _ in
      XCTFail("Stopped operation must suppress natural completion")
    }
    let original = player.requestStop(id: operation.id)!
    for _ in 0..<3 { XCTAssertTrue(player.requestStop(id: operation.id) === original) }
    await entered(driver, .stop)
    XCTAssertEqual(stoppingCount, 1)
    XCTAssertEqual(joined.count, 1)
    XCTAssertTrue(joined.allSatisfy { $0 === original })
    XCTAssertNil(original.receipt)
    XCTAssertNotNil(gate.currentLease)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    driver.release(.stop)
    let receipt = await original.value()
    XCTAssertEqual(receipt.result, .released)
    XCTAssertEqual(
      states, [.idle, .preparing(operation), .playing(operation), .stopping(operation), .idle])
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.releaseResources), 1)
    XCTAssertEqual(driver.count(.deactivate), 1)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
  }

  func testTwoSubscribersFinishPreparingDeliveryBeforeSynchronousCancellationPublishesStopping()
    async throws
  {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver()
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    var firstStates: [PracticePlaybackRuntimeState] = []
    var secondStates: [PracticePlaybackRuntimeState] = []
    var acknowledgement: PracticePlaybackCleanup?
    let first = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      firstStates.append(state)
      if state == .preparing(operation) {
        acknowledgement = player.requestStop(id: operation.id)
        XCTAssertNotNil(acknowledgement)
        XCTAssertNil(acknowledgement?.receipt)
        XCTAssertNotNil(gate.currentLease)
        XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
      }
    }
    let second = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      secondStates.append(state)
    }
    defer {
      first.cancel()
      second.cancel()
    }
    let error = await startResult(player, operation: operation).value
    XCTAssertEqual(error, .cancelled(operation))
    let receipt = await acknowledgement?.value()
    XCTAssertEqual(receipt?.result, .released)
    let expected: [PracticePlaybackRuntimeState] = [
      .idle, .preparing(operation), .stopping(operation), .idle,
    ]
    XCTAssertEqual(firstStates, expected)
    XCTAssertEqual(secondStates, expected)
    XCTAssertEqual(driver.count(.factory), 0)
    XCTAssertEqual(driver.count(.play), 0)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
  }

  func testTwoSubscribersFinishPlayingDeliveryBeforeSynchronousCancellationPublishesStopping()
    async throws
  {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(blocked: [.stop])
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    var firstStates: [PracticePlaybackRuntimeState] = []
    var secondStates: [PracticePlaybackRuntimeState] = []
    var acknowledgement: PracticePlaybackCleanup?
    let first = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      firstStates.append(state)
      if state == .playing(operation) { acknowledgement = player.requestStop(id: operation.id) }
    }
    let second = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      secondStates.append(state)
    }
    defer {
      first.cancel()
      second.cancel()
    }
    let start = startResult(player, operation: operation)
    await entered(driver, .stop)
    let pending: [PracticePlaybackRuntimeState] = [
      .idle, .preparing(operation), .playing(operation), .stopping(operation),
    ]
    XCTAssertEqual(firstStates, pending)
    XCTAssertEqual(secondStates, pending)
    XCTAssertEqual(player.state, .stopping(operation))
    XCTAssertNotNil(acknowledgement)
    XCTAssertNil(acknowledgement?.receipt)
    XCTAssertNotNil(gate.currentLease)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    driver.release(.stop)
    let error = await start.value
    XCTAssertEqual(error, .cancelled(operation))
    let receipt = await acknowledgement?.value()
    XCTAssertEqual(receipt?.result, .released)
    XCTAssertEqual(firstStates, pending + [.idle])
    XCTAssertEqual(secondStates, pending + [.idle])
    XCTAssertEqual(driver.count(.play), 1)
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.releaseResources), 1)
    XCTAssertEqual(driver.count(.deactivate), 1)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
  }

  func testCleanupBlockedSubscribersRetryEachCommittedFailureUntilGenuineRelease() async throws {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(blocked: [.stop], deactivateFailures: 2)
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    let releasedIdle = expectation(
      description: "two synchronous retries reach genuinely released idle")
    var states: [PracticePlaybackRuntimeState] = []
    var original: PracticePlaybackCleanup?
    var retries: [PracticePlaybackCleanup] = []
    var negatives: [PracticePlaybackCleanupReceipt] = []
    var lease: AudioHardwareOwnership.Lease?
    var blockedCount = 0
    let subscription = player.statePublisher.sink { state in
      MainActor.assertIsolated()
      states.append(state)
      if state == .playing(operation) {
        original = player.requestStop(id: operation.id)
      } else if state == .cleanupBlocked(operation) {
        blockedCount += 1
        guard blockedCount <= 2 else {
          XCTFail("Only the two injected failures may publish cleanupBlocked")
          return
        }
        guard let failedAttempt = retries.last ?? original else {
          XCTFail("The failed attempt must have an acknowledgement")
          return
        }
        let negative = PracticePlaybackCleanupReceipt(
          operation: operation, result: .cleanupUnconfirmed)
        XCTAssertEqual(failedAttempt.receipt, negative)
        negatives.append(negative)
        XCTAssertEqual(original?.receipt, negative)
        XCTAssertTrue(player.requestStop(id: operation.id) === original)
        XCTAssertEqual(gate.currentLease, lease)
        XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
        XCTAssertEqual(driver.count(.stop), 1)
        XCTAssertEqual(driver.count(.releaseResources), 1)
        XCTAssertEqual(driver.count(.deactivate), blockedCount)
        XCTAssertNil(player.retryCleanup(id: UUID()))
        guard let retry = player.retryCleanup(id: operation.id) else {
          XCTFail("A committed failure must permit synchronous explicit retry")
          return
        }
        XCTAssertFalse(retry === failedAttempt)
        XCTAssertFalse(retry === original)
        XCTAssertNil(retry.receipt)
        XCTAssertEqual(retry.operation, operation)
        XCTAssertTrue(player.retryCleanup(id: operation.id) === retry)
        retries.append(retry)
        // Installing the new attempt must never rewrite or resolve it with this older failure.
        XCTAssertEqual(failedAttempt.receipt, negative)
        XCTAssertNil(retry.receipt)
      } else if state == .idle, driver.count(.factory) > 0 {
        XCTAssertNil(gate.currentLease)
        XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
        releasedIdle.fulfill()
      }
    }
    defer { subscription.cancel() }
    let start = startResult(player, operation: operation)
    await entered(driver, .stop)
    lease = gate.currentLease
    XCTAssertEqual(lease?.operationID, operation.id)
    XCTAssertEqual(lease?.owner, .playback)
    XCTAssertNotNil(original)
    XCTAssertNil(original?.receipt)
    XCTAssertFalse(files.canRemove(fixture.url, owner: fixture.ownerID))
    // Late delegate completion cannot resurrect a callback after the synchronous stop.
    driver.finish(success: true)
    driver.finish(success: false)
    driver.release(.stop)
    let reachedIdle = await XCTWaiter.fulfillment(of: [releasedIdle], timeout: 2)
    XCTAssertEqual(reachedIdle, .completed)
    let error = await start.value
    XCTAssertEqual(error, .cleanupUnconfirmed(operation))
    XCTAssertEqual(blockedCount, 2)
    XCTAssertEqual(retries.count, 2)
    let negative = PracticePlaybackCleanupReceipt(
      operation: operation, result: .cleanupUnconfirmed)
    XCTAssertEqual(negatives, [negative, negative])
    XCTAssertEqual(original?.receipt, negative)
    if retries.count == 2 {
      XCTAssertEqual(retries[0].receipt, negative)
      XCTAssertEqual(
        retries[1].receipt,
        PracticePlaybackCleanupReceipt(operation: operation, result: .released))
      XCTAssertFalse(retries[0] === retries[1])
    }
    XCTAssertTrue(player.requestStop(id: operation.id) === original)
    XCTAssertNil(player.retryCleanup(id: operation.id))
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.canRemove(fixture.url, owner: fixture.ownerID))
    XCTAssertEqual(try Data(contentsOf: fixture.url), fixture.bytes)
    XCTAssertEqual(driver.count(.factory), 1)
    XCTAssertEqual(driver.count(.play), 1)
    XCTAssertEqual(driver.count(.stop), 1)
    XCTAssertEqual(driver.count(.releaseResources), 1)
    XCTAssertEqual(driver.count(.deactivate), 3)
    XCTAssertEqual(
      states,
      [
        .idle, .preparing(operation), .playing(operation), .stopping(operation),
        .cleanupBlocked(operation), .stopping(operation), .cleanupBlocked(operation),
        .stopping(operation), .idle,
      ])
  }

  func testCompletedGateRetryHasSeparateReadOnlyReceiptAfterCurrentOperationIsGone()
    async throws
  {
    let fixture = try AcknowledgedFileFixture()
    defer { fixture.removeDirectory() }
    let driver = AcknowledgedControlledDriver(deactivateFailures: 1)
    defer { driver.releaseAll() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    files.retain(fixture.url, owner: fixture.ownerID)
    let player = makePlayer(driver, gate: gate, files: files)
    let operation = PracticePlaybackOperation(id: UUID(), url: fixture.url)
    XCTAssertNil(player.completedCleanupRetry(id: operation.id))
    try await player.play(id: operation.id, url: operation.url) { _, _ in }
    let original = try XCTUnwrap(player.requestStop(id: operation.id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertNil(player.completedCleanupRetry(id: operation.id))
    let externalRetry = try XCTUnwrap(gate.retryPlaybackCleanup())
    let positive = await externalRetry.value()
    XCTAssertEqual(positive.result, .released)
    XCTAssertEqual(player.state, .idle)
    XCTAssertNil(gate.currentLease)
    XCTAssertNil(player.retryCleanup(id: operation.id))
    XCTAssertEqual(player.completedCleanupRetry(id: operation.id), positive)
    XCTAssertNil(player.completedCleanupRetry(id: UUID()))
    XCTAssertEqual(original.receipt, negative)
    XCTAssertTrue(player.requestStop(id: operation.id) === original)
    let calls = driver.count(.deactivate)
    XCTAssertEqual(player.completedCleanupRetry(id: operation.id), positive)
    XCTAssertEqual(driver.count(.deactivate), calls)
    try fixture.removeOwnedFile(files: files)
  }

  private func makePlayer(
    _ driver: AcknowledgedControlledDriver, gate: AudioHardwareOwnership,
    files: ProcessAudioFileOwnership
  ) -> SystemAcknowledgedPracticeAudioPlayer {
    SystemAcknowledgedPracticeAudioPlayer(ownership: gate, fileOwnership: files) {
      operation, finish in
      try driver.make(operation: operation, finished: finish)
      return driver
    }
  }

  private func startResult(
    _ player: SystemAcknowledgedPracticeAudioPlayer, operation: PracticePlaybackOperation
  ) -> Task<PracticePlaybackRuntimeError?, Never> {
    Task { @MainActor in
      do {
        try await player.play(id: operation.id, url: operation.url) { _, _ in
          XCTFail("Stopped/failed operation must not publish natural completion")
        }
        return nil
      } catch {
        guard let error = error as? PracticePlaybackRuntimeError else {
          XCTFail("Unexpected playback error: \(error)")
          return .couldNotStart(operation)
        }
        return error
      }
    }
  }

  private func entered(
    _ driver: AcknowledgedControlledDriver, _ stage: AcknowledgedControlledDriver.Stage
  ) async {
    let result = await XCTWaiter.fulfillment(of: [driver.entered(stage)], timeout: 2)
    XCTAssertEqual(result, .completed)
  }
}

/// Synchronization is limited to test controls. All driver work still enters the production runtime.
private final class AcknowledgedControlledDriver: PracticePlaybackDriver, @unchecked Sendable {
  enum Stage: CaseIterable, Hashable {
    case factory, activate, prepare, play, stop, releaseResources, deactivate
  }
  enum Failure: Error { case gateTimedOut, cleanup }
  private let lock = NSLock()
  private let blocked: Set<Stage>
  private let prepareSucceeds: Bool
  private let deactivateFailures: Int
  private let gates: [Stage: DispatchSemaphore]
  private let expectations: [Stage: XCTestExpectation]
  private var counts: [Stage: Int] = [:]
  private var observedMainThread = false
  private var operation: PracticePlaybackOperation?
  private var finished: (@Sendable (PracticePlaybackOperation, Bool) -> Void)?

  init(blocked: Set<Stage> = [], prepareSucceeds: Bool = true, deactivateFailures: Int = 0) {
    self.blocked = blocked
    self.prepareSucceeds = prepareSucceeds
    self.deactivateFailures = deactivateFailures
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
    finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) throws {
    try visit(.factory)
    lock.withLock {
      self.operation = operation
      self.finished = finished
    }
  }
  func activate() throws { try visit(.activate) }
  func prepare() throws -> Bool {
    try visit(.prepare)
    return prepareSucceeds
  }
  func play() throws -> Bool {
    try visit(.play)
    return true
  }
  func stop() throws { try visit(.stop) }
  func releasePlaybackResources() throws { try visit(.releaseResources) }
  func deactivate() throws {
    try visit(.deactivate)
    if count(.deactivate) <= deactivateFailures { throw Failure.cleanup }
  }

  func finish(success: Bool) {
    let values = lock.withLock { (operation, finished) }
    if let operation = values.0 { values.1?(operation, success) }
  }

  private func visit(_ stage: Stage) throws {
    let count = lock.withLock {
      counts[stage, default: 0] += 1
      observedMainThread = observedMainThread || Thread.isMainThread
      return counts[stage]!
    }
    if count == 1 { expectations[stage]!.fulfill() }
    if blocked.contains(stage), count == 1,
      gates[stage]!.wait(timeout: .now() + 8) != .success
    {
      throw Failure.gateTimedOut
    }
  }
}

/// Every file/directory is uniquely generated by the test, with no recording or hardware access.
@MainActor
private struct AcknowledgedFileFixture {
  let directory: URL
  let url: URL
  let ownerID = UUID()
  let bytes = Data([
    0x52, 0x49, 0x46, 0x46, 38, 0, 0, 0, 0x57, 0x41, 0x56, 0x45,
    0x66, 0x6D, 0x74, 0x20, 16, 0, 0, 0, 1, 0, 1, 0,
    0x80, 0x3E, 0, 0, 0, 0x7D, 0, 0, 2, 0, 16, 0,
    0x64, 0x61, 0x74, 0x61, 2, 0, 0, 0, 0, 0,
  ])

  init() throws {
    directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    url = directory.appendingPathComponent("cadence-attempt-\(UUID()).wav")
    try bytes.write(to: url)
  }

  func removeDirectory() { try? FileManager.default.removeItem(at: directory) }

  func removeOwnedFile(files: ProcessAudioFileOwnership) throws {
    XCTAssertTrue(files.canRemove(url, owner: ownerID))
    guard files.canRemove(url, owner: ownerID) else { return }
    try FileManager.default.removeItem(at: url)
    files.didRemove(url, owner: ownerID)
  }
}
