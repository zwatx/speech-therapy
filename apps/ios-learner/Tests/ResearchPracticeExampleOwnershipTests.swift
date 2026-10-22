#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchPracticeExampleOwnershipTests: XCTestCase {
    func testExactExampleRemovalReleasesItsOwner() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      let store = fixture.makeStore()
      let url = try store.write(Data([1, 2, 3]))
      XCTAssertEqual(store.ownedURL, url)
      XCTAssertEqual(fixture.files.protectedURLs, [url])
      XCTAssertEqual(try Data(contentsOf: url), Data([1, 2, 3]))
      try store.remove(url)
      XCTAssertNil(store.ownedURL)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testBorrowedExampleCannotBeDeletedAndExactRetryRemovesIt() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      let store = fixture.makeStore()
      let url = try store.write(Data([1]))
      let operation = UUID()
      XCTAssertTrue(fixture.files.borrow(url, operation: operation))
      XCTAssertThrowsError(try store.remove(url))
      let owner = try XCTUnwrap(fixture.files.pendingCleanupOwners.first)
      XCTAssertEqual(fixture.files.pendingCleanupOwners.count, 1)
      XCTAssertFalse(fixture.files.retryCleanup(owner: owner))
      XCTAssertEqual(store.ownedURL, url)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      fixture.files.finishBorrowing(operation: operation)
      XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
      XCTAssertNil(store.ownedURL)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    }

    func testRecoveryRetainsProducerAfterViewReferenceIsLost() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      var store: ResearchPracticeExampleStore? = fixture.makeStore()
      weak var retainedStore = store
      let url = try XCTUnwrap(store).write(Data([1]))
      let operation = UUID()
      XCTAssertTrue(fixture.files.borrow(url, operation: operation))
      XCTAssertThrowsError(try XCTUnwrap(store).remove(url))
      let owner = try XCTUnwrap(fixture.files.pendingCleanupOwners.first)
      store = nil
      XCTAssertNotNil(retainedStore)
      XCTAssertFalse(fixture.files.retryCleanup(owner: UUID()))
      XCTAssertNotNil(retainedStore)
      fixture.files.finishBorrowing(operation: operation)
      XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
      XCTAssertNil(retainedStore)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    }

    func testDeletionFailureKeepsExactOwnerUntilSuccessfulExplicitRetry() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      var refuseRemoval = true
      var removalCalls = 0
      let store = fixture.makeStore { url in
        removalCalls += 1
        if refuseRemoval { throw ResearchPracticeExampleError.cleanupFailed }
        try FileManager.default.removeItem(at: url)
      }
      let url = try store.write(Data([1]))
      XCTAssertThrowsError(try store.remove(url))
      let owner = try XCTUnwrap(fixture.files.pendingCleanupOwners.first)
      XCTAssertEqual(removalCalls, 1)
      XCTAssertFalse(fixture.files.retryCleanup(owner: owner))
      XCTAssertEqual(removalCalls, 2)
      XCTAssertEqual(store.ownedURL, url)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertEqual(fixture.files.pendingCleanupOwners, [owner])
      refuseRemoval = false
      XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
      XCTAssertEqual(removalCalls, 3)
      XCTAssertNil(store.ownedURL)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testUnknownURLNeverChangesOwnershipOrRegistersRecovery() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      let store = fixture.makeStore()
      let url = try store.write(Data([1]))
      let foreign = fixture.directory.appendingPathComponent("foreign.wav")
      try Data([9]).write(to: foreign)
      XCTAssertThrowsError(try store.remove(foreign))
      XCTAssertEqual(store.ownedURL, url)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
      XCTAssertEqual(try Data(contentsOf: foreign), Data([9]))
      try store.remove(url)
      try FileManager.default.removeItem(at: foreign)
    }

    func testEmptyWriteCreatesNoFileOrOwnership() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      let store = fixture.makeStore()
      XCTAssertThrowsError(try store.write(Data()))
      XCTAssertNil(store.ownedURL)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
      XCTAssertTrue(
        try FileManager.default.contentsOfDirectory(atPath: fixture.directory.path).isEmpty)
    }

    func testRemovalPermissionErrorRetainsProducerAndExactRetryCanLaterSucceed() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      var failPermission = true
      let store = fixture.makeStore { url in
        if failPermission { throw CocoaError(.fileWriteNoPermission) }
        try FileManager.default.removeItem(at: url)
      }
      let url = try store.write(Data([1]))
      XCTAssertThrowsError(try store.remove(url))
      let owner = try XCTUnwrap(fixture.files.pendingCleanupOwners.first)
      XCTAssertEqual(store.ownedURL, url)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertFalse(fixture.files.retryCleanup(owner: owner))
      XCTAssertEqual(store.ownedURL, url)
      failPermission = false
      XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
      XCTAssertNil(store.ownedURL)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testExternallyRemovedGeneratedFileCanConfirmAbsenceThroughDefaultRemoval() throws {
      let fixture = try Fixture()
      defer { fixture.removeDirectory() }
      let store = fixture.makeStore()
      let url = try store.write(Data([1]))
      try FileManager.default.removeItem(at: url)
      try store.remove(url)
      XCTAssertNil(store.ownedURL)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    }

    @MainActor
    private struct Fixture {
      let directory: URL
      let files = ProcessAudioFileOwnership()
      init() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "generated-example-ownership-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      }
      func makeStore(removeFile: ((URL) throws -> Void)? = nil) -> ResearchPracticeExampleStore {
        ResearchPracticeExampleStore(
          directory: directory, fileOwnership: files, removeFile: removeFile)
      }
      func removeDirectory() {
        do { try FileManager.default.removeItem(at: directory) } catch {
          XCTFail("Could not remove generated example directory: \(error)")
        }
      }
    }
  }
#endif
