import Combine
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class SystemAudioCapturerOwnershipTests: XCTestCase {
  func testRecordingPowerReadsOnlyFiniteCurrentLevels() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertEqual(fixture.driver.powerReads, 0)
    try fixture.start()
    let finiteLevels: [Float] = [-160, -36.5, 0]
    for level in finiteLevels {
      fixture.driver.power = level
      XCTAssertEqual(fixture.capturer!.currentRecordingPower(), level)
    }
    let unavailableLevels: [Float?] = [nil, .nan, .infinity, -.infinity]
    for level in unavailableLevels {
      fixture.driver.power = level
      XCTAssertNil(fixture.capturer!.currentRecordingPower())
    }
    XCTAssertEqual(fixture.driver.powerReads, 7)
    let take = try fixture.capturer!.stop()
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertEqual(fixture.driver.powerReads, 7)
    try fixture.capturer!.discard(take)
    try fixture.start()
    try fixture.capturer!.cancel()
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertEqual(fixture.driver.powerReads, 7)
  }

  func testRecordingPowerDoesNotPollDuringHardwareTransitionsOrCleanupFailure() throws {
    for failedStage in [Step.stop, .detach, .deactivate] {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      fixture.driver.checkBeforeCall = { _ in
        XCTAssertNil(fixture.capturer!.currentRecordingPower())
        XCTAssertEqual(fixture.driver.powerReads, 0)
      }
      try fixture.start()
      let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
      fixture.driver.failures[failedStage] = 1
      assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
      XCTAssertNil(fixture.capturer!.currentRecordingPower())
      XCTAssertEqual(fixture.driver.powerReads, 0)
      XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: owner).result, .released)
      XCTAssertNil(fixture.capturer!.currentRecordingPower())
      XCTAssertEqual(fixture.driver.powerReads, 0)
      fixture.driver.checkBeforeCall = nil
    }
  }

  func testRecordingPowerUnavailableInAutomaticStopGapAndAfterFinishCallback() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    fixture.driver.power = -24
    XCTAssertEqual(fixture.capturer!.currentRecordingPower(), -24)
    // The duration limit can stop hardware before the delegate hops to MainActor.
    fixture.driver.isRecording = false
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertEqual(fixture.driver.powerReads, 2)
    fixture.driver.completion?(try XCTUnwrap(fixture.driver.recorderID), true)
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertEqual(fixture.driver.powerReads, 2)
    try fixture.capturer!.cancel()
  }

  func testRecordingPowerRejectsReentrantStopCancelAndReplacement() throws {
    for action in 0..<3 {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      try fixture.start()
      fixture.driver.power = -24
      fixture.driver.onPowerRead = {
        fixture.driver.onPowerRead = nil
        do {
          if action == 0 {
            let take = try fixture.capturer!.stop()
            try fixture.capturer!.discard(take)
          } else {
            try fixture.capturer!.cancel()
          }
          if action == 2 {
            try fixture.start()
            fixture.driver.power = -12
          }
        } catch { XCTFail("Reentrant capture change failed: \(error)") }
      }
      XCTAssertNil(fixture.capturer!.currentRecordingPower())
      XCTAssertEqual(fixture.driver.powerReads, 1)
      if action == 2 {
        XCTAssertEqual(fixture.capturer!.currentRecordingPower(), -12)
        try fixture.capturer!.cancel()
      } else {
        XCTAssertNil(fixture.capturer!.currentRecordingPower())
        XCTAssertEqual(fixture.driver.powerReads, 1)
      }
    }
  }

  func testRecordingPowerRejectsReentrantFailedCleanup() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    fixture.driver.power = -24
    fixture.driver.failures[.stop] = 1
    fixture.driver.onPowerRead = {
      fixture.driver.onPowerRead = nil
      self.assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
    }
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertNil(fixture.capturer!.currentRecordingPower())
    XCTAssertEqual(fixture.driver.powerReads, 1)
    XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: owner).result, .released)
  }

  func testReturnedTakeCarriesExactOwnerAndCompletionQueryDoesNotRemoveIt() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let take = try fixture.capturer!.stop()
    let owner = try XCTUnwrap(take.cleanupOwnerID)
    XCTAssertNil(fixture.capturer!.completedFileCleanup(operationID: owner))
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    try fixture.capturer!.discard(take)
    XCTAssertEqual(
      fixture.capturer!.completedFileCleanup(operationID: owner),
      CaptureCleanupReceipt(operationID: owner, result: .released))
    XCTAssertNil(fixture.capturer!.completedFileCleanup(operationID: UUID()))
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
    let calls = fixture.removal.calls
    _ = fixture.capturer!.completedFileCleanup(operationID: owner)
    XCTAssertEqual(fixture.removal.calls, calls)
    assertError(.recordingNotOwned) { try fixture.capturer!.discard(take) }
  }

  func testExactFileReceiptSurvivesEarlierSynchronousSubscriberRecovery() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let take = try fixture.capturer!.stop()
    let owner = try XCTUnwrap(take.cleanupOwnerID)
    fixture.removal.failures = 1
    var positive: CaptureCleanupReceipt?
    let observer = fixture.capturer!.cleanupStatePublisher.sink { state in
      if state.fileBlockedOwnerIDs.contains(owner), positive == nil {
        positive = fixture.capturer!.retryCleanup(operationID: owner)
      }
    }
    defer { observer.cancel() }
    assertError(.couldNotDeleteTemporaryRecording) { try fixture.capturer!.discard(take) }
    let expected = CaptureCleanupReceipt(operationID: owner, result: .released)
    XCTAssertEqual(positive, expected)
    XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
    XCTAssertEqual(fixture.capturer!.completedFileCleanup(operationID: owner), expected)
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    XCTAssertEqual(fixture.removal.calls, 2)
  }

  func testFailedExplicitFileRetryCannotCreatePositiveCompletionReceipt() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let take = try fixture.capturer!.stop()
    let owner = try XCTUnwrap(take.cleanupOwnerID)
    fixture.removal.failures = 2
    assertError(.couldNotDeleteTemporaryRecording) { try fixture.capturer!.discard(take) }
    XCTAssertEqual(fixture.capturer!.startupAvailability, .available)
    XCTAssertNil(fixture.capturer!.completedFileCleanup(operationID: owner))
    XCTAssertEqual(
      fixture.capturer!.retryCleanup(operationID: owner).result,
      .hardwareReleasedFilesRetained)
    XCTAssertNil(fixture.capturer!.completedFileCleanup(operationID: owner))
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    let positive = fixture.capturer!.retryCleanup(operationID: owner)
    XCTAssertEqual(positive.result, .released)
    XCTAssertEqual(fixture.capturer!.completedFileCleanup(operationID: owner), positive)
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
  }

  func testBusyLeaseRefusesBeforeFactoryAndKnownURLAllocation() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    let playback = try fixture.hardware.reserve(operationID: UUID(), owner: .playback)
    assertError(.hardwareBusy) { try fixture.capturer!.start { _ in XCTFail("Busy capture") } }
    XCTAssertEqual(fixture.driver.factoryCalls, 0)
    XCTAssertTrue(fixture.driver.calls.isEmpty)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    XCTAssertTrue(
      try FileManager.default.contentsOfDirectory(atPath: fixture.directory.path).isEmpty)
    XCTAssertEqual(fixture.hardware.currentLease, playback)
    XCTAssertTrue(fixture.hardware.release(playback))
  }

  func testActiveCaptureBlocksPlaybackAndRefusesImplicitRecovery() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let lease = try XCTUnwrap(fixture.hardware.currentLease)
    XCTAssertEqual(lease.owner, .capture)
    XCTAssertThrowsError(try fixture.hardware.reserve(operationID: UUID(), owner: .playback))
    XCTAssertEqual(
      fixture.hardware.retryCaptureCleanup(operationID: lease.operationID).result, .refused)
    XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: lease.operationID).result, .refused)
    XCTAssertEqual(fixture.driver.count(.stop), 0)
    try fixture.capturer!.cancel()
    XCTAssertNil(fixture.hardware.currentLease)
  }

  func testEveryStartStageFailureDeletesOnlyAfterAcknowledgedHardwareCleanup() throws {
    for stage in [Step.configure, .create, .prepare, .record] {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      fixture.driver.failures[stage] = 1
      fixture.driver.checkBeforeCall = { _ in
        XCTAssertEqual(fixture.hardware.currentLease?.owner, .capture)
        XCTAssertEqual(fixture.files.protectedURLs.count, 1)
      }
      XCTAssertThrowsError(try fixture.start())
      XCTAssertNil(fixture.hardware.currentLease, "\(stage)")
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty, "\(stage)")
      XCTAssertEqual(fixture.driver.count(.stop), 1)
      XCTAssertEqual(fixture.driver.count(.detach), 1)
      XCTAssertEqual(fixture.driver.count(.deactivate), 1)
      XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
      XCTAssertTrue(
        try FileManager.default.contentsOfDirectory(atPath: fixture.directory.path).isEmpty)
      // Remove the fixture-capturing observation to avoid a test-only retain cycle.
      fixture.driver.checkBeforeCall = nil
    }
  }

  func testFalsePrepareAndRecordAreConcreteStartFailures() throws {
    for stage in [Step.prepare, .record] {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      fixture.driver.falseStage = stage
      assertError(.couldNotStart) { try fixture.start() }
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      if stage == .prepare { XCTAssertEqual(fixture.driver.count(.record), 0) }
    }
  }

  func testStartFailureWithCleanupFailureRetainsKnownURLAndHasNoLateTake() throws {
    for stage in [Step.configure, .create, .prepare, .record] {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      fixture.driver.failures[stage] = 1
      fixture.driver.failures[.deactivate] = 1
      assertError(.hardwareCleanupUnconfirmed) { try fixture.start() }
      let id = try XCTUnwrap(fixture.hardware.blockedCaptureOperationID)
      XCTAssertEqual(fixture.capturer!.cleanupState.hardwareBlockedOperationID, id)
      XCTAssertEqual(fixture.files.protectedURLs.count, 1)
      XCTAssertEqual(fixture.hardware.currentLease?.operationID, id)
      assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
      assertError(.hardwareCleanupUnconfirmed) { _ = try fixture.capturer!.stop() }
      XCTAssertEqual(fixture.driver.count(.deactivate), 1)
      let receipt = fixture.capturer!.retryCleanup(operationID: id)
      XCTAssertEqual(receipt.result, .released)
      XCTAssertEqual(fixture.driver.count(.stop), 1)
      XCTAssertEqual(fixture.driver.count(.detach), 1)
      XCTAssertEqual(fixture.driver.count(.deactivate), 2)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      assertError(.couldNotStart) { _ = try fixture.capturer!.stop() }
      XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: id).result, .refused)
    }
  }

  func testStopCleanupFailuresResumeOnlyFailedStageAndPreserveOriginalError() throws {
    for failed in [Step.stop, .detach, .deactivate] {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      try fixture.start()
      let url = try XCTUnwrap(fixture.driver.url)
      let id = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
      fixture.driver.failures[failed] = 1
      assertError(.hardwareCleanupUnconfirmed) { _ = try fixture.capturer!.stop() }
      let counts = fixture.driver.calls
      assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
      assertError(.hardwareCleanupUnconfirmed) { _ = try fixture.capturer!.stop() }
      assertError(.hardwareCleanupUnconfirmed) { try fixture.start() }
      XCTAssertEqual(fixture.driver.calls, counts)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertTrue(fixture.files.protectedURLs.contains(url))
      XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: UUID()).result, .refused)
      XCTAssertEqual(fixture.hardware.retryCaptureCleanup(operationID: UUID()).result, .refused)
      XCTAssertEqual(fixture.hardware.retryCaptureCleanup(operationID: id).result, .released)
      XCTAssertEqual(fixture.driver.count(.stop), failed == .stop ? 2 : 1)
      XCTAssertEqual(fixture.driver.count(.detach), failed == .detach ? 2 : 1)
      XCTAssertEqual(fixture.driver.count(.deactivate), failed == .deactivate ? 2 : 1)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
      assertError(.couldNotStart) { _ = try fixture.capturer!.stop() }
    }
  }

  func testCaptureLeaseRefusesActualPlaybackRuntimeBeforeItsFactoryRuns() async throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let runtime = PracticePlaybackRuntime(ownership: fixture.hardware, fileOwnership: fixture.files)
    { _, _ in
      XCTFail("Busy capture must reject before playback factory")
      throw ControlledFailure.injected
    }
    do {
      try await runtime.startPlayback(id: UUID(), url: try XCTUnwrap(fixture.driver.url)) { _, _ in
        XCTFail("Busy playback cannot complete")
      }
      XCTFail("Expected shared hardware busy")
    } catch {
      XCTAssertEqual(error as? PracticePlaybackRuntimeError, .busy)
    }
    XCTAssertEqual(fixture.hardware.currentLease?.owner, .capture)
    XCTAssertEqual(fixture.files.protectedURLs.count, 1)
    try fixture.capturer!.cancel()
  }

  func testDroppedCaptureOwnerRemainsReachableThroughHardwareFailure() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let id = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    fixture.driver.failures[.deactivate] = 1
    assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
    weak var retained = fixture.capturer
    fixture.capturer = nil
    XCTAssertNotNil(retained)
    XCTAssertEqual(fixture.hardware.retryCaptureCleanup(operationID: id).result, .released)
    XCTAssertNil(retained)
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertEqual(fixture.hardware.retryCaptureCleanup(operationID: id).result, .refused)
  }

  func testSuccessfulStopUsesUnchangedRealPCMParserAndRetainsIdleTake() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let take = try fixture.capturer!.stop()
    XCTAssertEqual(take.summary.duration, 0.1, accuracy: 0.000001)
    XCTAssertEqual(take.summary.averagePower, Float(20 * log10(0.25)), accuracy: 0.01)
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
    let reopened = SystemAudioCapturer(
      recordingStore: fixture.store, fileOwnership: fixture.files,
      hardwareOwnership: fixture.hardware, driverFactory: { fixture.driver })
    XCTAssertEqual(reopened.cleanupState, .idle)
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertTrue(fixture.files.protectedURLs.contains(take.url))
    try fixture.capturer!.cancel()
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    try fixture.capturer!.discard(take)
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
  }

  func testTwoReturnedTakesKeepDistinctOwnersWithoutActiveHardware() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let first = try fixture.capturer!.stop()
    try fixture.start()
    let second = try fixture.capturer!.stop()
    XCTAssertNotEqual(first.url, second.url)
    XCTAssertEqual(fixture.files.protectedURLs.count, 2)
    XCTAssertNil(fixture.hardware.currentLease)
    try fixture.capturer!.discard(first)
    XCTAssertEqual(fixture.files.protectedURLs, [second.url])
    try fixture.capturer!.cancel()
    XCTAssertTrue(FileManager.default.fileExists(atPath: second.url.path))
    try fixture.capturer!.discard(second)
  }

  func testSummaryFailureDeletesAfterHardwareReleaseAndNeverReturnsTake() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    fixture.driver.malformedRecording = true
    try fixture.start()
    XCTAssertThrowsError(try fixture.capturer!.stop())
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    XCTAssertTrue(
      try FileManager.default.contentsOfDirectory(atPath: fixture.directory.path).isEmpty)
  }

  func testPlaybackBorrowRefusesDeletionAndExplicitRecoveryWaitsForBorrowRelease() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    let take = try fixture.capturer!.stop()
    let playback = UUID()
    XCTAssertTrue(fixture.files.borrow(take.url, operation: playback))
    assertError(.recordingInUse) { try fixture.capturer!.discard(take) }
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertEqual(fixture.capturer!.cleanupState.fileBlockedOwnerIDs, [owner])
    XCTAssertFalse(fixture.files.retryCleanup(owner: owner))
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    assertError(.recordingInUse) { try fixture.start() }
    fixture.files.finishBorrowing(operation: UUID())
    XCTAssertFalse(fixture.files.canRemove(take.url, owner: owner))
    fixture.files.finishBorrowing(operation: playback)
    XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
  }

  func testUnknownRecordingRefusesWithoutDeletingFile() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    let url = fixture.directory.appendingPathComponent("unowned.wav")
    try Data([1, 2, 3]).write(to: url)
    let unknown = CapturedRecording(
      url: url, summary: CaptureSummary(duration: 1, averagePower: -20))
    assertError(.recordingNotOwned) { try fixture.capturer!.discard(unknown) }
    XCTAssertEqual(try Data(contentsOf: url), Data([1, 2, 3]))
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
  }

  func testFileDeletionFailureReleasesHardwareButRetainsProcessRecovery() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    let url = try XCTUnwrap(fixture.driver.url)
    fixture.removal.failures = 1
    assertError(.couldNotDeleteTemporaryRecording) { try fixture.capturer!.cancel() }
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertEqual(fixture.capturer!.cleanupState.hardwareBlockedOperationID, nil)
    XCTAssertEqual(fixture.capturer!.cleanupState.fileBlockedOwnerIDs, [owner])
    XCTAssertTrue(fixture.files.protectedURLs.contains(url))
    XCTAssertFalse(fixture.files.retryCleanup(owner: UUID()))
    weak var retained = fixture.capturer
    fixture.capturer = nil
    XCTAssertNotNil(retained)
    XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
    XCTAssertNil(retained)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
  }

  func testRepeatedDiscardAfterFilesystemFailureDoesNotRetryUntilExplicitOwnerRetry() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    let take = try fixture.capturer!.stop()
    fixture.removal.failures = 1
    assertError(.couldNotDeleteTemporaryRecording) { try fixture.capturer!.discard(take) }
    XCTAssertEqual(fixture.removal.calls, 1)
    XCTAssertEqual(fixture.files.pendingCleanupOwners, [owner])
    let blocked = fixture.capturer!.cleanupState
    assertError(.couldNotDeleteTemporaryRecording) { try fixture.capturer!.discard(take) }
    XCTAssertEqual(fixture.removal.calls, 1)
    XCTAssertEqual(fixture.capturer!.cleanupState, blocked)
    XCTAssertTrue(fixture.files.protectedURLs.contains(take.url))
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: owner).result, .released)
    XCTAssertEqual(fixture.removal.calls, 2)
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
  }

  func testRepeatedDiscardAfterBorrowReleasePreservesRefusalUntilExplicitOwnerRetry() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    let take = try fixture.capturer!.stop()
    let playback = UUID()
    XCTAssertTrue(fixture.files.borrow(take.url, operation: playback))
    assertError(.recordingInUse) { try fixture.capturer!.discard(take) }
    XCTAssertEqual(fixture.removal.calls, 0)
    fixture.files.finishBorrowing(operation: playback)
    let blocked = fixture.capturer!.cleanupState
    assertError(.recordingInUse) { try fixture.capturer!.discard(take) }
    XCTAssertEqual(fixture.removal.calls, 0)
    XCTAssertEqual(fixture.capturer!.cleanupState, blocked)
    XCTAssertEqual(fixture.files.pendingCleanupOwners, [owner])
    XCTAssertTrue(fixture.files.protectedURLs.contains(take.url))
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.url.path))
    XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: owner).result, .released)
    XCTAssertEqual(fixture.removal.calls, 1)
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: take.url.path))
  }

  func testHardwareAndEarlierFileFailureRemainVisibleTogether() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let firstOwner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    let first = try fixture.capturer!.stop()
    try fixture.start()
    let secondOwner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    fixture.removal.failures = 1
    assertError(.couldNotDeleteTemporaryRecording) { try fixture.capturer!.discard(first) }
    fixture.driver.failures[.stop] = 1
    assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
    XCTAssertEqual(fixture.capturer!.cleanupState.hardwareBlockedOperationID, secondOwner)
    XCTAssertEqual(fixture.capturer!.cleanupState.fileBlockedOwnerIDs, [firstOwner])
    XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: secondOwner).result, .released)
    XCTAssertEqual(fixture.capturer!.cleanupState.fileBlockedOwnerIDs, [firstOwner])
    XCTAssertTrue(fixture.files.retryCleanup(owner: firstOwner))
    XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
  }

  func testStaleCallbacksAndWrongRecorderIdentityDoNotCompleteSuccessor() async throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    var finishes = 0
    let currentFinished = expectation(description: "Current recorder completion")
    try fixture.capturer!.start { _ in finishes += 1 }
    let stale = try XCTUnwrap(fixture.driver.completion)
    let staleID = try XCTUnwrap(fixture.driver.recorderID)
    try fixture.capturer!.cancel()
    try fixture.capturer!.start { _ in
      finishes += 1
      currentFinished.fulfill()
    }
    stale(staleID, true)
    fixture.driver.completion?(UUID(), true)
    await Task.yield()
    XCTAssertEqual(finishes, 0)
    let correctID = try XCTUnwrap(fixture.driver.recorderID)
    fixture.driver.completion?(correctID, true)
    let result = await XCTWaiter.fulfillment(of: [currentFinished], timeout: 2)
    XCTAssertEqual(result, .completed)
    XCTAssertEqual(finishes, 1)
    fixture.driver.completion?(correctID, true)
    await Task.yield()
    XCTAssertEqual(finishes, 1)
    try fixture.capturer!.cancel()
  }

  func testQueuedFinishIsRevokedByCleanupBeforeHandlerRuns() async throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    var finishes = 0
    try fixture.capturer!.start { _ in finishes += 1 }
    fixture.driver.completion?(try XCTUnwrap(fixture.driver.recorderID), true)
    try fixture.capturer!.cancel()
    await Task.yield()
    XCTAssertEqual(finishes, 0)
  }

  func testPublisherAllowsCommittedReentrantRetryAndSerializesEveryObserver() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    try fixture.start()
    let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
    fixture.driver.failures[.deactivate] = 1
    var firstEvents: [CaptureCleanupState] = []
    var secondEvents: [CaptureCleanupState] = []
    var lateEvents: [CaptureCleanupState] = []
    var retryResult: CaptureCleanupReceipt.Result?
    var lateSubscriber: AnyCancellable?
    let first = fixture.capturer!.cleanupStatePublisher.dropFirst().sink { state in
      firstEvents.append(state)
      if state.hasHardwareIssue {
        XCTAssertEqual(fixture.hardware.blockedCaptureOperationID, owner)
        retryResult = fixture.capturer!.retryCleanup(operationID: owner).result
        XCTAssertEqual(retryResult, .released)
        XCTAssertEqual(fixture.capturer!.cleanupState, .idle)
        // The outer blocked event is still draining. A new subscriber must initially
        // see the committed idle state and must not regress to that older event.
        lateSubscriber = fixture.capturer!.cleanupStatePublisher.sink { lateEvents.append($0) }
        XCTAssertEqual(lateEvents, [.idle])
      }
    }
    let second = fixture.capturer!.cleanupStatePublisher.dropFirst().sink { state in
      secondEvents.append(state)
    }
    withExtendedLifetime((first, second)) {
      // The outer call preserves its original negative acknowledgement even though
      // this explicit subscriber retry has genuinely released hardware before it returns.
      assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
      let blocked = CaptureCleanupState(hardwareBlockedOperationID: owner, fileBlockedOwnerIDs: [])
      XCTAssertEqual(firstEvents, [blocked, .idle])
      XCTAssertEqual(secondEvents, [blocked, .idle])
      XCTAssertEqual(lateEvents, [.idle])
      XCTAssertEqual(fixture.driver.count(.deactivate), 2)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: owner).result, .refused)
    }
    withExtendedLifetime(lateSubscriber) {}
  }

  func testInitialSubscriptionCanRetryAndFailedRetryDoesNotDuplicateBlockedState() throws {
    for failures in [1, 2] {
      let fixture = try Fixture()
      defer { fixture.dispose() }
      try fixture.start()
      let owner = try XCTUnwrap(fixture.hardware.currentLease?.operationID)
      fixture.driver.failures[.deactivate] = failures
      assertError(.hardwareCleanupUnconfirmed) { try fixture.capturer!.cancel() }
      var events: [CaptureCleanupState] = []
      var retryResults: [CaptureCleanupReceipt.Result] = []
      let subscriber = fixture.capturer!.cleanupStatePublisher.sink { state in
        events.append(state)
        if state.hasHardwareIssue {
          retryResults.append(fixture.capturer!.retryCleanup(operationID: owner).result)
        }
      }
      withExtendedLifetime(subscriber) {
        XCTAssertEqual(retryResults, [failures == 1 ? .released : .cleanupUnconfirmed])
        if failures == 2 {
          XCTAssertEqual(events.count, 1)
          XCTAssertEqual(fixture.capturer!.retryCleanup(operationID: owner).result, .released)
        }
        let blocked = CaptureCleanupState(
          hardwareBlockedOperationID: owner, fileBlockedOwnerIDs: [])
        XCTAssertEqual(events, [blocked, .idle])
        XCTAssertNil(fixture.hardware.currentLease)
      }
    }
  }

  func testStartupFailureIsStickyAcrossNewCaptureOwners() throws {
    let fixture = try Fixture()
    defer { fixture.dispose() }
    let missing = fixture.directory.appendingPathComponent("missing-subdirectory")
    let store = TemporaryRecordingStore(directory: missing)
    for _ in 0..<2 {
      let capturer = SystemAudioCapturer(
        recordingStore: store, fileOwnership: fixture.files,
        hardwareOwnership: fixture.hardware, driverFactory: { fixture.driver })
      XCTAssertEqual(capturer.startupAvailability, .cleanupFailed)
      assertError(.couldNotDeleteTemporaryRecording) { try capturer.start { _ in } }
      XCTAssertEqual(capturer.retryCleanup(operationID: UUID()).result, .refused)
      if !FileManager.default.fileExists(atPath: missing.path) {
        try FileManager.default.createDirectory(at: missing, withIntermediateDirectories: true)
      }
      XCTAssertEqual(capturer.startupAvailability, .cleanupFailed)
    }
    XCTAssertEqual(fixture.driver.factoryCalls, 0)
    XCTAssertNil(fixture.hardware.currentLease)
  }

  func testWrongLeaseCannotInstallOrMarkOrReleaseCaptureRecovery() throws {
    let hardware = AudioHardwareOwnership()
    let lease = try hardware.reserve(operationID: UUID(), owner: .capture)
    let other = AudioHardwareOwnership()
    let wrong = try other.reserve(operationID: lease.operationID, owner: .capture)
    var recoveries = 0
    XCTAssertTrue(
      hardware.registerCaptureRecovery(lease) {
        recoveries += 1
        return CaptureCleanupReceipt(operationID: lease.operationID, result: .cleanupUnconfirmed)
      })
    XCTAssertFalse(
      hardware.registerCaptureRecovery(wrong) {
        XCTFail("Wrong lease")
        return CaptureCleanupReceipt(operationID: lease.operationID, result: .released)
      })
    XCTAssertFalse(hardware.markCaptureCleanupBlocked(wrong))
    XCTAssertFalse(hardware.release(wrong))
    XCTAssertEqual(hardware.retryCaptureCleanup(operationID: lease.operationID).result, .refused)
    XCTAssertTrue(hardware.markCaptureCleanupBlocked(lease))
    XCTAssertEqual(
      hardware.retryCaptureCleanup(operationID: lease.operationID).result, .cleanupUnconfirmed)
    XCTAssertEqual(recoveries, 1)
    XCTAssertTrue(hardware.release(lease))
    XCTAssertNil(hardware.blockedCaptureOperationID)
    XCTAssertEqual(hardware.retryCaptureCleanup(operationID: lease.operationID).result, .refused)
  }

  func testFileRecoveryCannotClaimReleaseOrBeReplacedWithoutActualRemoval() throws {
    let files = ProcessAudioFileOwnership()
    let owner = UUID()
    let url = URL(fileURLWithPath: "/controlled-registry/\(UUID()).wav")
    XCTAssertFalse(files.registerCleanupRecovery(owner: owner) { true })
    files.retain(url, owner: owner)
    XCTAssertTrue(files.registerCleanupRecovery(owner: owner) { true })
    XCTAssertFalse(
      files.registerCleanupRecovery(owner: owner) {
        XCTFail("Replacement")
        return true
      })
    XCTAssertFalse(files.retryCleanup(owner: owner))
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    files.didRemove(url, owner: owner)
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
  }

  private func assertError(_ expected: AudioCaptureError, _ operation: () throws -> Void) {
    XCTAssertThrowsError(try operation()) { error in
      guard let actual = error as? AudioCaptureError else {
        return XCTFail("Unexpected error: \(error)")
      }
      XCTAssertEqual(actual, expected)
    }
  }
}

@MainActor
private final class Fixture {
  let directory: URL
  let store: TemporaryRecordingStore
  let hardware = AudioHardwareOwnership()
  let files = ProcessAudioFileOwnership()
  let driver = ControlledCaptureDriver()
  let removal = RemovalControl()
  var capturer: SystemAudioCapturer?

  init() throws {
    directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("capture-ownership-test-\(UUID())", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    store = TemporaryRecordingStore(directory: directory)
    let driver = driver
    let removal = removal
    let store = store
    capturer = SystemAudioCapturer(
      recordingStore: store, fileOwnership: files, hardwareOwnership: hardware,
      driverFactory: {
        driver.factoryCalls += 1
        return driver
      },
      removeFile: { url in
        removal.calls += 1
        if removal.failures > 0 {
          removal.failures -= 1
          throw ControlledFailure.injected
        }
        try store.removeRecordingIfPresent(at: url)
      })
  }

  func start() throws { try capturer!.start { _ in XCTFail("Unexpected finish") } }
  func dispose() { try? FileManager.default.removeItem(at: directory) }
}

private enum ControlledFailure: Error { case injected }
private enum Step: Equatable, Hashable {
  case configure, create, prepare, record, stop, detach, deactivate
}

@MainActor
private final class RemovalControl {
  var failures = 0
  var calls = 0
}

@MainActor
private final class ControlledCaptureDriver: CaptureHardwareDriver {
  var factoryCalls = 0
  var calls: [Step] = []
  var failures: [Step: Int] = [:]
  var falseStage: Step?
  var malformedRecording = false
  var url: URL?
  var recorderID: UUID?
  var completion: (@MainActor @Sendable (UUID, Bool) -> Void)?
  var checkBeforeCall: ((Step) -> Void)?
  var power: Float?
  var powerReads = 0
  var isRecording = false
  var onPowerRead: (() -> Void)?

  func count(_ step: Step) -> Int { calls.filter { $0 == step }.count }
  private func call(_ step: Step) throws {
    checkBeforeCall?(step)
    calls.append(step)
    if failures[step, default: 0] > 0 {
      failures[step, default: 0] -= 1
      throw ControlledFailure.injected
    }
  }

  func configureActivate() throws { try call(.configure) }
  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    self.url = url
    self.recorderID = recorderID
    completion = onFinish
    // Test-owned canonical PCM bytes exercise the real bounded AVAudioFile parser.
    // The file remains known and retained even if this creation stage then fails.
    try (malformedRecording ? Data([1, 2, 3]) : canonicalWAV()).write(to: url)
    try call(.create)
  }
  func prepare() throws -> Bool {
    try call(.prepare)
    return falseStage != .prepare
  }
  func record() throws -> Bool {
    try call(.record)
    isRecording = falseStage != .record
    return isRecording
  }
  func currentRecordingPower() -> Float? {
    powerReads += 1
    let result = isRecording ? power : nil
    onPowerRead?()
    return result
  }
  func stop() throws {
    try call(.stop)
    isRecording = false
  }
  func detachRelease() throws {
    try call(.detach)
    completion = nil
    recorderID = nil
  }
  func deactivate() throws { try call(.deactivate) }

  private func canonicalWAV() -> Data {
    let samples = 1_600
    var data = Data()
    func ascii(_ value: String) { data.append(contentsOf: value.utf8) }
    func little<T: FixedWidthInteger>(_ value: T) {
      var bytes = value.littleEndian
      withUnsafeBytes(of: &bytes) { data.append(contentsOf: $0) }
    }
    ascii("RIFF")
    little(UInt32(36 + samples * 2))
    ascii("WAVE")
    ascii("fmt ")
    little(UInt32(16))
    little(UInt16(1))
    little(UInt16(1))
    little(UInt32(16_000))
    little(UInt32(32_000))
    little(UInt16(2))
    little(UInt16(16))
    ascii("data")
    little(UInt32(samples * 2))
    for _ in 0..<samples { little(Int16(8_192)) }
    return data
  }
}
