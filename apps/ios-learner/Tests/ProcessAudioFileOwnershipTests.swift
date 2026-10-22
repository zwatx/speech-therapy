import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class ProcessAudioFileOwnershipTests: XCTestCase {
  private func directory() throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-ownership-test-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: url) }
    return url
  }

  private func fixture(_ directory: URL, name: String) throws -> URL {
    let url = directory.appendingPathComponent(name)
    // File-retention fixture only; these bytes are never decoded or played.
    try Data("generated retention fixture".utf8).write(to: url)
    return url
  }

  func testSecondStartupPreservesRecordingCreatedAfterInitialScan() throws {
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    let store = TemporaryRecordingStore(directory: root)
    try registry.cleanStartupOnce(directory: root) {
      try store.removeStaleRecordings(excluding: $0)
    }
    let take = try fixture(root, name: "cadence-attempt-current.wav")
    try registry.cleanStartupOnce(directory: root) {
      try store.removeStaleRecordings(excluding: $0)
    }
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.path))
  }

  func testRecreatingConcreteCapturerDoesNotDeleteCurrentRouteTake() throws {
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    let store = TemporaryRecordingStore(directory: root)
    let stale = try fixture(root, name: "cadence-attempt-old.wav")
    let first = SystemAudioCapturer(recordingStore: store, fileOwnership: registry)
    XCTAssertFalse(FileManager.default.fileExists(atPath: stale.path))
    let take = try fixture(root, name: "cadence-attempt-current.wav")
    let second = SystemAudioCapturer(recordingStore: store, fileOwnership: registry)
    XCTAssertTrue(FileManager.default.fileExists(atPath: take.path))
    withExtendedLifetime((first, second)) {}
  }

  func testInitialScanExcludesRetainedIdleTakeAndBorrowedFile() throws {
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    let idle = try fixture(root, name: "cadence-attempt-idle.wav")
    let pending = try fixture(root, name: "cadence-attempt-pending.wav")
    let stale = try fixture(root, name: "cadence-attempt-stale.wav")
    registry.retain(idle, owner: UUID())
    registry.borrow(pending, operation: UUID())
    try registry.cleanStartupOnce(directory: root) {
      try TemporaryRecordingStore(directory: root).removeStaleRecordings(excluding: $0)
    }
    XCTAssertTrue(FileManager.default.fileExists(atPath: idle.path))
    XCTAssertTrue(FileManager.default.fileExists(atPath: pending.path))
    XCTAssertFalse(FileManager.default.fileExists(atPath: stale.path))
  }

  func testFileCannotBeDeletedBeforeBorrowAcknowledgement() throws {
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    let url = try fixture(root, name: "cadence-attempt-kept.wav")
    let owner = UUID()
    let operation = UUID()
    registry.retain(url, owner: owner)
    registry.borrow(url, operation: operation)
    XCTAssertFalse(registry.canRemove(url, owner: owner))
    registry.didRemove(url, owner: owner)  // Requested removal cannot erase a pending borrow.
    XCTAssertTrue(registry.protectedURLs.contains(url))
    registry.finishBorrowing(operation: UUID())  // A stale acknowledgement has no effect.
    XCTAssertFalse(registry.canRemove(url, owner: owner))
    registry.finishBorrowing(operation: operation)
    XCTAssertTrue(registry.canRemove(url, owner: owner))
    try TemporaryRecordingStore(directory: root).removeRecordingIfPresent(at: url)
    registry.didRemove(url, owner: owner)
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertFalse(registry.protectedURLs.contains(url))
  }

  func testWrongOwnerAndAnotherRetainingOwnerPreventRemoval() throws {
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    let url = try fixture(root, name: "cadence-attempt-shared.wav")
    let first = UUID()
    let second = UUID()
    registry.retain(url, owner: first)
    XCTAssertFalse(registry.canRemove(url, owner: second))
    registry.retain(url, owner: second)
    XCTAssertFalse(registry.canRemove(url, owner: first))
    XCTAssertFalse(registry.canRemove(url, owner: second))
    XCTAssertTrue(registry.protectedURLs.contains(url))
  }

  func testReentrantStartupCannotScanTwice() throws {
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    var calls = 0
    try registry.cleanStartupOnce(directory: root) { _ in
      calls += 1
      XCTAssertThrowsError(try registry.cleanStartupOnce(directory: root) { _ in calls += 1 })
    }
    try registry.cleanStartupOnce(directory: root) { _ in calls += 1 }
    XCTAssertEqual(calls, 1)
  }

  func testFailedStartupCleanupCannotBeBypassedByAnotherRoute() throws {
    enum Failure: Error { case removal }
    let root = try directory()
    let registry = ProcessAudioFileOwnership()
    var calls = 0
    XCTAssertThrowsError(
      try registry.cleanStartupOnce(directory: root) { _ in
        calls += 1
        throw Failure.removal
      })
    XCTAssertThrowsError(try registry.cleanStartupOnce(directory: root) { _ in calls += 1 })
    XCTAssertEqual(calls, 1)
  }

  func testFailedStartupReceiptSurvivesDirectoryCreationAndDirectoryURLAlias() throws {
    enum Failure: Error { case scan }
    let root = try directory()
    let missing = root.appendingPathComponent("missing-subdirectory")
    let registry = ProcessAudioFileOwnership()
    var scans = 0
    XCTAssertThrowsError(
      try registry.cleanStartupOnce(directory: missing) { _ in
        scans += 1
        throw Failure.scan
      })
    try FileManager.default.createDirectory(at: missing, withIntermediateDirectories: false)
    let alias = URL(fileURLWithPath: missing.path, isDirectory: true)
    for candidate in [missing, alias] {
      XCTAssertThrowsError(
        try registry.cleanStartupOnce(directory: candidate) { _ in scans += 1 })
    }
    XCTAssertEqual(scans, 1)
  }
}
