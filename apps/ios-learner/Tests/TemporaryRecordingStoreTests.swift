import Foundation
import XCTest

@testable import CadenceLearner

final class TemporaryRecordingStoreTests: XCTestCase {
  func testRemovesOnlyCadenceTemporaryRecordings() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-store-test-\(UUID().uuidString)")
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true
    )
    defer { try? FileManager.default.removeItem(at: directory) }

    let recording = directory.appendingPathComponent("cadence-attempt-old.wav")
    let unrelated = directory.appendingPathComponent("caregiver-note.m4a")
    try Data("audio".utf8).write(to: recording)
    try Data("keep".utf8).write(to: unrelated)

    try TemporaryRecordingStore(directory: directory).removeStaleRecordings()

    XCTAssertFalse(FileManager.default.fileExists(atPath: recording.path))
    XCTAssertTrue(FileManager.default.fileExists(atPath: unrelated.path))
  }

  func testIndeterminateAbsenceCannotHideRemovalPermissionFailure() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("generated-store-uncertain-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("cadence-attempt-generated.wav")
    try Data([1]).write(to: file)
    let manager = IndeterminateRemovalFileManager()
    let store = TemporaryRecordingStore(directory: directory, fileManager: manager)
    XCTAssertThrowsError(try store.removeRecordingIfPresent(at: file)) { error in
      XCTAssertEqual((error as NSError).code, NSFileWriteNoPermissionError)
    }
    XCTAssertEqual(manager.removalCalls, 1)
    XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
    XCTAssertEqual(try Data(contentsOf: file), Data([1]))
  }

  func testRemoveIfPresentIsIdempotent() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-store-test-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let missing = directory.appendingPathComponent("cadence-attempt-missing.m4a")
    let store = TemporaryRecordingStore(directory: directory)
    XCTAssertNoThrow(try store.removeRecordingIfPresent(at: missing))
    XCTAssertNoThrow(try store.removeRecordingIfPresent(at: missing))
  }
}

private final class IndeterminateRemovalFileManager: FileManager, @unchecked Sendable {
  var removalCalls = 0
  override func fileExists(atPath path: String) -> Bool { false }
  override func removeItem(at URL: URL) throws {
    removalCalls += 1
    throw CocoaError(.fileWriteNoPermission)
  }
}
