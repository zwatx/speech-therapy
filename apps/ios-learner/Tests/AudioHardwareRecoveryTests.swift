import Combine
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class AudioHardwareRecoveryTests: XCTestCase {
  func testDroppedFacadeWithFailedCleanupRemainsReachableForExplicitRetry() async throws {
    let ownership = AudioHardwareOwnership()
    let driver = RecoveryPlaybackDriver()
    let files = ProcessAudioFileOwnership()
    var runtime: PracticePlaybackRuntime? = PracticePlaybackRuntime(
      ownership: ownership, fileOwnership: files
    ) { _, _ in
      driver
    }
    weak var retained = runtime
    let id = UUID()
    let url = URL(fileURLWithPath: "/controlled-recovery/\(id).wav")
    try await runtime!.startPlayback(id: id, url: url) { _, _ in
      XCTFail("Cancelled operation cannot complete")
    }
    XCTAssertNil(ownership.retryPlaybackCleanup())  // No implicit stop or retry while playing.
    let original = try XCTUnwrap(runtime!.requestStop(id: id))
    let failure = await original.value()
    XCTAssertEqual(failure.result, .cleanupUnconfirmed)
    runtime = nil
    XCTAssertNotNil(retained)
    XCTAssertEqual(ownership.currentLease?.operationID, id)
    let retry = try XCTUnwrap(ownership.retryPlaybackCleanup())
    let release = await retry.value()
    XCTAssertEqual(release.operation, failure.operation)
    XCTAssertEqual(release.result, .released)
    XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
    XCTAssertNil(ownership.currentLease)
    XCTAssertNil(ownership.retryPlaybackCleanup())
  }

  func testWrongLeaseCannotReplaceRegisteredRecovery() throws {
    let ownership = AudioHardwareOwnership()
    let lease = try ownership.reserve(operationID: UUID(), owner: .playback)
    let other = AudioHardwareOwnership()
    let wrong = try other.reserve(operationID: lease.operationID, owner: .playback)
    var genuineCalls = 0
    XCTAssertTrue(
      ownership.registerPlaybackRecovery(lease) {
        genuineCalls += 1
        return nil
      })
    XCTAssertFalse(
      ownership.registerPlaybackRecovery(wrong) {
        XCTFail("Stale recovery")
        return nil
      })
    XCTAssertNil(ownership.retryPlaybackCleanup())
    XCTAssertEqual(genuineCalls, 1)
    XCTAssertTrue(ownership.release(lease))
    XCTAssertNil(ownership.retryPlaybackCleanup())
    XCTAssertEqual(genuineCalls, 1)
  }

  func testPlaybackMarkerCommitsBeforeFailurePublicationAndClearsOnExactRelease() async throws {
    let ownership = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let driver = RecoveryPlaybackDriver()
    let runtime = PracticePlaybackRuntime(ownership: ownership, fileOwnership: files) { _, _ in
      driver
    }
    let id = UUID()
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID()).wav")
    var observedBlockedID: UUID?
    let subscription = runtime.$state.sink { state in
      MainActor.assumeIsolated {
        if case .cleanupBlocked(let operation) = state {
          XCTAssertEqual(operation.id, id)
          observedBlockedID = ownership.blockedPlaybackOperationID
        }
      }
    }
    defer { subscription.cancel() }
    try await runtime.startPlayback(id: id, url: url) { _, _ in XCTFail("Stopped completion") }
    XCTAssertNil(ownership.blockedPlaybackOperationID)
    let original = try XCTUnwrap(runtime.requestStop(id: id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertEqual(ownership.blockedPlaybackOperationID, id)
    XCTAssertEqual(observedBlockedID, id)
    let retry = try XCTUnwrap(ownership.retryPlaybackCleanup())
    let released = await retry.value()
    XCTAssertEqual(released.result, .released)
    XCTAssertNil(ownership.blockedPlaybackOperationID)
    XCTAssertNil(ownership.currentLease)
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
  }

  func testPlaybackMarkerRefusesWrongLeaseOwnerAndStaleRelease() throws {
    let ownership = AudioHardwareOwnership()
    let lease = try ownership.reserve(operationID: UUID(), owner: .playback)
    let other = AudioHardwareOwnership()
    let wrong = try other.reserve(operationID: lease.operationID, owner: .playback)
    XCTAssertFalse(ownership.markPlaybackCleanupBlocked(wrong))
    XCTAssertNil(ownership.blockedPlaybackOperationID)
    XCTAssertTrue(ownership.markPlaybackCleanupBlocked(lease))
    XCTAssertFalse(ownership.release(wrong))
    XCTAssertEqual(ownership.blockedPlaybackOperationID, lease.operationID)
    XCTAssertTrue(ownership.release(lease))
    XCTAssertNil(ownership.blockedPlaybackOperationID)
    let capture = try ownership.reserve(operationID: UUID(), owner: .capture)
    XCTAssertFalse(ownership.markPlaybackCleanupBlocked(capture))
    XCTAssertNil(ownership.blockedPlaybackOperationID)
    XCTAssertTrue(ownership.release(capture))
  }

}

/// Only the actual playback queue accesses mutable driver state. The factory captures this
/// test control as Sendable; no test/main-actor code reads or mutates its queue-confined state.
private final class RecoveryPlaybackDriver: PracticePlaybackDriver, @unchecked Sendable {
  private var deactivationAttempts = 0
  private enum Failure: Error { case deactivate }
  func activate() throws {}
  func prepare() throws -> Bool { true }
  func play() throws -> Bool { true }
  func stop() throws {}
  func releasePlaybackResources() throws {}
  func deactivate() throws {
    deactivationAttempts += 1
    if deactivationAttempts == 1 { throw Failure.deactivate }
  }
}
