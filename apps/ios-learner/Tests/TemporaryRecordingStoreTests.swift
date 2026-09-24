import Foundation
import XCTest

@testable import CadenceLearner

final class TemporaryRecordingStoreTests: XCTestCase {
  func testSymlinkedDirectoryKeepsAbsoluteRecordingIdentityAcrossCreationAndRemoval() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-store-alias-\(UUID())", isDirectory: true)
    let target = root.appendingPathComponent("target", isDirectory: true)
    let alias = root.appendingPathComponent("alias", isDirectory: true)
    try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: target)
    // Foundation can also supply a directory relative to a file URL base.
    let relativeAlias = try XCTUnwrap(URL(string: "alias/", relativeTo: root))
    let store = TemporaryRecordingStore(directory: relativeAlias)
    XCTAssertNil(store.directory.baseURL)
    XCTAssertEqual(store.directory.path, target.resolvingSymlinksInPath().standardizedFileURL.path)
    let file = store.makeRecordingURL().standardizedFileURL
    XCTAssertNil(file.baseURL)
    let identityBeforeCreation = file
    try Data([1, 2, 3]).write(to: file)
    XCTAssertEqual(file.standardizedFileURL, identityBeforeCreation)
    XCTAssertEqual(file.resolvingSymlinksInPath(), identityBeforeCreation)
    try store.removeRecordingIfPresent(at: file)
    XCTAssertEqual(file.standardizedFileURL, identityBeforeCreation)
    XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    XCTAssertNoThrow(try store.removeRecordingIfPresent(at: file))
  }

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
