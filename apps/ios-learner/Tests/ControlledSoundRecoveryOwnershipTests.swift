#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ControlledSoundRecoveryOwnershipTests: XCTestCase {
    private var cleanups: [@MainActor () async -> Void] = []
    override func tearDown() async throws {
      for cleanup in cleanups { await cleanup() }
      cleanups.removeAll()
      try await super.tearDown()
    }
    private func settled(_ predicate: @escaping @MainActor () -> Bool) async {
      if predicate() { return }
      let done = expectation(description: "generated Sound owner settlement")
      let observation = Task { @MainActor in
        while !Task.isCancelled {
          if predicate() {
            done.fulfill()
            return
          }
          await Task.yield()
        }
      }
      defer { observation.cancel() }
      let result = await XCTWaiter.fulfillment(of: [done], timeout: 3)
      XCTAssertEqual(result, .completed)
    }

    func testRunResourceCacheReusesOnlyExactRunAndAllocatesNoMediaOrHistory() {
      let firstID = UUID()
      let secondID = UUID()
      let first = ResearchSoundUITestFixtures.resources(runID: firstID)
      let same = ResearchSoundUITestFixtures.resources(runID: firstID)
      let other = ResearchSoundUITestFixtures.resources(runID: secondID)
      XCTAssertTrue(first === same)
      XCTAssertFalse(first === other)
      XCTAssertEqual(first.runID, firstID)
      XCTAssertEqual(other.runID, secondID)
      XCTAssertTrue(first.hardware === same.hardware)
      XCTAssertTrue(first.files === same.files)
      XCTAssertFalse(first.hardware === other.hardware)
      XCTAssertFalse(first.files === other.files)
      XCTAssertNil(first.hardware.currentLease)
      XCTAssertNil(other.hardware.currentLease)
      XCTAssertTrue(first.files.protectedURLs.isEmpty)
      XCTAssertTrue(other.files.protectedURLs.isEmpty)
      XCTAssertTrue(first.files.pendingCleanupOwners.isEmpty)
      XCTAssertTrue(other.files.pendingCleanupOwners.isEmpty)
    }

    func testPersistentSoundFileRecoveryRemainsReachableAfterSecondCloseAndAllSessionLoss()
      async throws
    {
      let runID = UUID()
      let resources = ResearchSoundUITestFixtures.resources(runID: runID)
      var session: ResearchSoundSession? = ResearchSoundUITestFixtures.session(
        for: .cleanup, resources: resources)
      await session?.startRecording()
      let owner = try XCTUnwrap(resources.hardware.currentLease?.operationID)
      session?.stopRecording()
      XCTAssertEqual(session?.phase, .review)
      let url = try XCTUnwrap(resources.files.protectedURLs.first)
      let bytes = try Data(contentsOf: url)
      XCTAssertNoThrow(try FeedbackPCM.measure(bytes))
      XCTAssertNil(resources.hardware.currentLease)
      let originalClose = try XCTUnwrap(session).end()
      let failedClose = await originalClose.value
      XCTAssertFalse(failedClose)
      XCTAssertEqual(session?.captureCleanupState.fileBlockedOwnerIDs, [owner])
      XCTAssertEqual(resources.files.pendingCleanupOwners, [owner])
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      let secondClose = await session?.end().value
      XCTAssertEqual(secondClose, true)
      XCTAssertEqual(session?.phase, .ended)
      weak var departed = session
      session = nil
      await settled { departed == nil }
      XCTAssertEqual(
        ResearchSoundUITestFixtures.resources(runID: runID).files.pendingCleanupOwners, [owner])
      let recovery = AudioCleanupRecoveryModel(
        ownership: resources.hardware, files: resources.files)
      recovery.refresh()
      XCTAssertEqual(recovery.snapshot.pendingFileOwnerIDs, [owner])
      XCTAssertNil(recovery.snapshot.blockedCaptureOperationID)
      XCTAssertNil(recovery.snapshot.blockedPlaybackOperationID)
      XCTAssertTrue(recovery.snapshot.canRetry)
      let explicitlyRetried = await recovery.retry().value
      XCTAssertFalse(
        explicitlyRetried, "The generated cleanup case deliberately keeps its real removal failure")
      XCTAssertEqual(recovery.failure, .fileCleanupUnconfirmed(owner))
      XCTAssertEqual(recovery.snapshot.pendingFileOwnerIDs, [owner])
      XCTAssertEqual(resources.files.protectedURLs, [url])
      XCTAssertEqual(try Data(contentsOf: url), bytes)
      let stillNegative = await originalClose.value
      XCTAssertFalse(stillNegative)
      var reopened: ResearchSoundSession? = ResearchSoundUITestFixtures.session(
        for: .cleanup, resources: ResearchSoundUITestFixtures.resources(runID: runID))
      XCTAssertEqual(reopened?.phase, .ready)
      XCTAssertEqual(resources.files.pendingCleanupOwners, [owner])
      XCTAssertEqual(resources.files.protectedURLs, [url])
      let reopenedClosed = await reopened?.end().value
      XCTAssertEqual(reopenedClosed, true, "The new session owns none of the old recording")
      reopened = nil
      recovery.refresh()
      XCTAssertEqual(recovery.snapshot.pendingFileOwnerIDs, [owner])
      let unrelated = ResearchSoundUITestFixtures.resources(runID: UUID())
      XCTAssertTrue(unrelated.files.pendingCleanupOwners.isEmpty)
      XCTAssertTrue(unrelated.files.protectedURLs.isEmpty)
      // Keep the genuine persistent fixture failure process-owned. Never unlink its file
      // manually or invent a released receipt merely to make test teardown appear clean.
    }

    func testMatchingRunPlayerBorrowAndRealProducerRemovalReceiptRequireExplicitRecovery()
      async throws
    {
      let resources = ResearchSoundUITestFixtures.resources(runID: UUID())
      let producer = ResearchGeneratedCaptureFileOwnership(
        hardware: resources.hardware, files: resources.files)
      let player = ResearchAcknowledgedPlaybackUITestFixture(
        completion: .explicitStop, ownership: resources.hardware, fileOwnership: resources.files)
      let url = producer.directory.appendingPathComponent(UUID().uuidString + ".wav")
      var playbackID: UUID?
      cleanups.append {
        if let id = playbackID, let stop = player.requestStop(id: id) { _ = await stop.value() }
        for owner in resources.files.pendingCleanupOwners {
          _ = resources.files.retryCleanup(owner: owner)
        }
        try? producer.cancel(url)
        if resources.files.protectedURLs.contains(url) { try? producer.remove(url) }
        XCTAssertNil(resources.hardware.currentLease)
        XCTAssertTrue(resources.files.protectedURLs.isEmpty)
        if resources.hardware.currentLease == nil, resources.files.protectedURLs.isEmpty {
          try? FileManager.default.removeItem(at: producer.directory)
        }
      }
      try producer.begin(url)
      try pcm().write(to: url)
      let owner = try producer.stop(url)
      XCTAssertNil(resources.hardware.currentLease)
      let id = UUID()
      playbackID = id
      try await player.play(id: id, url: url) { _, _ in
        XCTFail("Explicitly stopped fixture has no natural completion")
      }
      XCTAssertEqual(resources.hardware.currentLease?.operationID, id)
      XCTAssertFalse(resources.files.canRemove(url, owner: owner))
      XCTAssertThrowsError(try producer.remove(url)) {
        XCTAssertEqual($0 as? AudioCaptureError, .recordingInUse)
      }
      XCTAssertNil(producer.completedFileCleanup(operationID: owner))
      XCTAssertEqual(resources.files.pendingCleanupOwners, [owner])
      let model = AudioCleanupRecoveryModel(ownership: resources.hardware, files: resources.files)
      let busy = await model.retry().value
      XCTAssertFalse(busy)
      XCTAssertEqual(model.failure, .hardwareInUse(id))
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      let stop = try XCTUnwrap(player.requestStop(id: id))
      let released = await stop.value()
      XCTAssertEqual(released.operation.id, id)
      XCTAssertEqual(released.result, .released)
      XCTAssertNil(resources.hardware.currentLease)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertNil(producer.completedFileCleanup(operationID: owner))
      let removed = await model.retry().value
      XCTAssertTrue(removed)
      XCTAssertEqual(producer.completedFileCleanup(operationID: owner)?.operationID, owner)
      XCTAssertEqual(producer.completedFileCleanup(operationID: owner)?.result, .released)
      XCTAssertNil(producer.completedFileCleanup(operationID: UUID()))
      XCTAssertTrue(resources.files.protectedURLs.isEmpty)
      XCTAssertTrue(resources.files.pendingCleanupOwners.isEmpty)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertEqual(stop.receipt, released)
    }

    private func pcm() -> Data {
      var bytes = Data()
      func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
      func word(_ value: Int, _ count: Int) {
        for i in 0..<count { bytes.append(UInt8((value >> (i * 8)) & 255)) }
      }
      text("RIFF")
      word(4836, 4)
      text("WAVEfmt ")
      word(16, 4)
      word(1, 2)
      word(1, 2)
      word(16000, 4)
      word(32000, 4)
      word(2, 2)
      word(16, 2)
      text("data")
      word(4800, 4)
      bytes.append(Data(repeating: 0, count: 4800))
      return bytes
    }
  }
#endif
