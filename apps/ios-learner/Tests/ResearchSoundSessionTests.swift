#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Dispatch
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchSoundSessionTests: XCTestCase {
    private var receiptFixtures: [SoundReceiptFixture] = []
    override func tearDown() async throws {
      for fixture in receiptFixtures { await fixture.clean() }
      receiptFixtures.removeAll()
      try await super.tearDown()
    }
    private func configured(
      _ capture: SoundCapturer, _ processing: SoundProcessor,
      _ player: (any AcknowledgedPracticeAudioPlaying)? = nil
    ) async -> ResearchSoundSession {
      let session = ResearchSoundSession(
        capturer: capture, player: player ?? SoundPlayer(files: capture.files),
        processor: processing, fileOwnership: capture.files)
      session.adultConfirmed = true
      session.processingOptIn = true
      await session.refreshDeclaration()
      await wait { !session.actionsPaused }
      return session
    }
    private func record(_ session: ResearchSoundSession) async {
      await wait { !session.actionsPaused }
      await session.startRecording()
      session.stopRecording()
    }
    private func wait(_ condition: @escaping @MainActor () -> Bool) async {
      if condition() { return }
      let changed = expectation(description: "bounded owned transition")
      let observation = Task { @MainActor in
        while !Task.isCancelled {
          if condition() {
            changed.fulfill()
            return
          }
          await Task.yield()
        }
      }
      defer { observation.cancel() }
      let result = await XCTWaiter.fulfillment(of: [changed], timeout: 2)
      XCTAssertEqual(result, .completed)
    }
    func testDefaultOffSeparateAdultFreeBreadAndFreshCaptureAfterSettings() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = ResearchSoundSession(
        capturer: capture, player: SoundPlayer(files: capture.files), processor: processor,
        fileOwnership: capture.files)
      XCTAssertFalse(session.adultConfirmed)
      XCTAssertFalse(session.processingOptIn)
      await record(session)
      session.checkRecording()
      XCTAssertFalse(session.canCheck)
      XCTAssertEqual(processor.posts, 0)
      session.adultConfirmed = true
      let settingsCleaned = await session.waitForCleanup()
      XCTAssertTrue(settingsCleaned)
      XCTAssertFalse(session.hasRecording)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertFalse(session.canReplay)
      session.processingOptIn = true
      await session.refreshDeclaration()
      for settings in 0..<3 {
        if settings == 0 { session.selectedChildAge = 12 }
        if settings == 1 {
          session.selectedChildAge = nil
          session.practiceMode = "guided"
        }
        if settings == 2 {
          session.practiceMode = "free"
          session.selectedPromptId = "r-end-door"
        }
        await record(session)
        session.checkRecording()
        XCTAssertEqual(processor.posts, 0)
      }
      session.selectedPromptId = ResearchSoundContract.promptId
      XCTAssertFalse(session.canReplay)
      await record(session)
      XCTAssertTrue(session.canCheck)
      _ = await session.end().value
    }
    func testOneExplicitCheckLatestTakeClaimBeforePrepareAndRetakeFreshIDs() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await record(session)
      processor.delayPrepare = true
      session.checkRecording()
      session.checkRecording()
      await wait { processor.preparing != nil }
      XCTAssertEqual(session.checksClaimed, 1)
      XCTAssertEqual(processor.posts, 0)
      processor.finishPreparation()
      await wait { processor.pending != nil }
      let first = processor.last!
      processor.resolve(
        .init(status: .inconclusive, reason: "uncovered_mass_dominates", preference: nil))
      await wait { session.phase != .checking }
      session.checkRecording()
      XCTAssertEqual(processor.posts, 1)
      _ = await session.retake().value
      processor.delayPrepare = false
      await record(session)
      session.checkRecording()
      await wait { processor.pending != nil }
      XCTAssertNotEqual(first.context.captureId, processor.last!.context.captureId)
      XCTAssertNotEqual(first.context.attemptId, processor.last!.context.attemptId)
      XCTAssertGreaterThan(processor.last!.context.generation, first.context.generation)
      processor.resolve(.init(status: .inconclusive, reason: "candidate_tie", preference: nil))
      await wait { session.phase != .checking }
      _ = await session.end().value
      XCTAssertEqual(session.attemptsStarted, 2)
      XCTAssertEqual(session.attemptsFinished, 2)
    }
    func testCancellationDuringPrepareNeverPostsAndClaimsSurviveReset() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await record(session)
      processor.delayPrepare = true
      session.checkRecording()
      await wait { processor.preparing != nil }
      session.cancelChecking()
      processor.finishPreparation()
      await wait { processor.prepareReturned }
      XCTAssertEqual(processor.posts, 0)
      XCTAssertEqual(session.checksClaimed, 1)
      _ = await session.reset().value
      XCTAssertEqual(session.checksClaimed, 1)
      XCTAssertFalse(session.canReplay)
      _ = await session.end().value
    }
    func testExactCancelLatePositiveSuppressedAfterResetBackgroundSetupAndEnd() async {
      for action in 0..<5 {
        let capture = SoundCapturer()
        let processor = SoundProcessor()
        defer { capture.remove() }
        let session = await configured(capture, processor)
        await record(session)
        session.checkRecording()
        await wait { processor.pending != nil }
        let owned = processor.last!
        switch action {
        case 0: session.cancelChecking()
        case 1: _ = await session.reset().value
        case 2: session.appDidEnterBackground()
        case 3: session.adultConfirmed = false
        default: _ = await session.end().value
        }
        await wait { !processor.cancelled.isEmpty }
        XCTAssertEqual(processor.cancelled.last, owned)
        await wait { processor.resets.contains { $0 > owned.context.generation } }
        XCTAssertGreaterThan(processor.resets.max()!, owned.context.generation)
        processor.resolve(
          .init(
            status: .observedModelPreference, reason: "model_preferred_candidate",
            preference: .rPath))
        await wait { processor.returned }
        if case .observation = session.phase { XCTFail("Stale result restored") }
        XCTAssertFalse(session.canReplay)
        XCTAssertEqual(session.checksClaimed, 1)
        _ = await session.end().value
      }
    }
    func testServiceCleanupPauseSurvivesResetAndAllowsRecordingReplay() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      let player = SoundPlayer(files: capture.files)
      defer { capture.remove() }
      let session = await configured(capture, processor, player)
      await record(session)
      session.checkRecording()
      await wait { processor.pending != nil }
      processor.resolve(.init(status: .unavailable, reason: "cleanup_unconfirmed", preference: nil))
      await wait { session.phase != .checking }
      XCTAssertTrue(session.sharedProcessingPaused)
      XCTAssertFalse(session.canCheck)
      XCTAssertTrue(session.canReplay)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      _ = await session.reset().value
      XCTAssertTrue(session.sharedProcessingPaused)
      session.adultConfirmed = true
      session.processingOptIn = true
      await session.refreshDeclaration()
      await record(session)
      XCTAssertTrue(session.canReplay)
      XCTAssertFalse(session.canCheck)
      await session.togglePlayback()
      XCTAssertEqual(player.starts, 2)
      _ = await session.end().value
    }
    func testLocalDeletionFailureBlocksCaptureWithoutClaimingDeleted() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await record(session)
      capture.failDiscard = true
      _ = await session.retake().value
      XCTAssertEqual(session.phase, .localCleanupBlocked)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertFalse(session.canRecord)
      XCTAssertFalse(session.canReplay)
      await session.startRecording()
      XCTAssertEqual(capture.starts, 1)
    }
    func testLatePermissionUnusedCaptureClosedAndSerialPermissionNoNewRecorder() async {
      for action in 0..<4 {
        let capture = SoundCapturer()
        let processor = SoundProcessor()
        capture.delayPermission = true
        defer { capture.remove() }
        let session = await configured(capture, processor)
        let task = Task { await session.startRecording() }
        await wait { capture.permission != nil }
        switch action {
        case 0: _ = await session.reset().value
        case 1: session.appDidBecomeInactive()
        case 2: session.processingOptIn = false
        default: _ = await session.end().value
        }
        XCTAssertFalse(session.canRecord)
        let cancels = capture.cancels
        capture.permission?.resume(returning: true)
        capture.permission = nil
        await task.value
        XCTAssertEqual(capture.starts, 0)
        XCTAssertGreaterThan(capture.cancels, cancels)
        XCTAssertEqual(session.attemptsStarted, 1)
        XCTAssertEqual(session.attemptsFinished, 1)
      }
    }
    func testNonceChangeRevokesTakeCSRFChangeRetainsAndLateDeclarationIgnored() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await record(session)
      processor.currentDeclaration = .init(
        serverNonce: SoundFixture.nonce, csrfToken: String(repeating: "e", count: 64),
        processingAvailable: true)
      await session.refreshDeclaration()
      XCTAssertTrue(session.canReplay)
      XCTAssertTrue(session.canCheck)
      processor.currentDeclaration = .init(
        serverNonce: "00000000-0000-4000-8000-000000000999",
        csrfToken: String(repeating: "e", count: 64), processingAvailable: true)
      await session.refreshDeclaration()
      XCTAssertFalse(session.canReplay)
      processor.delayDeclaration = true
      let task = Task { await session.refreshDeclaration() }
      await wait { processor.declPending != nil }
      _ = await session.reset().value
      processor.finishDeclaration()
      await task.value
      XCTAssertNil(session.declaration)
      XCTAssertFalse(session.declarationLoading)
      _ = await session.end().value
    }
    func testNonceChangeDuringCheckAndFailedTransportCannotReuseCapture() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await record(session)
      processor.currentDeclaration = .init(
        serverNonce: "00000000-0000-4000-8000-000000000999",
        csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
      session.checkRecording()
      await wait { session.phase != .checking }
      XCTAssertEqual(processor.posts, 0)
      XCTAssertFalse(session.canReplay)
      await record(session)
      session.checkRecording()
      await wait { processor.pending != nil }
      processor.reject()
      await wait { session.phase != .checking }
      session.checkRecording()
      XCTAssertEqual(processor.posts, 1)
      XCTAssertEqual(session.checksClaimed, 2)
      _ = await session.end().value
    }
    func testPermissionDeniedTerminalOnceReplayCallbacksAnd128CaptureCap() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      let player = SoundPlayer(files: capture.files)
      defer { capture.remove() }
      let session = await configured(capture, processor, player)
      capture.granted = false
      await session.startRecording()
      XCTAssertEqual(session.phase, .permissionDenied)
      XCTAssertEqual(session.attemptsFinished, 1)
      capture.granted = true
      await record(session)
      await session.togglePlayback()
      let staleID = session.activePlaybackID!
      _ = await session.retake().value
      await player.callbackBarrier(id: staleID, success: false)
      XCTAssertEqual(player.sessionCallbackDeliveries[staleID], 1)
      XCTAssertFalse(session.isPlaying)
      XCTAssertFalse(session.playbackFailed)
      for _ in 2..<128 {
        await record(session)
        _ = await session.retake().value
      }
      XCTAssertEqual(session.attemptsStarted, 128)
      XCTAssertEqual(session.attemptsFinished, 128)
      XCTAssertFalse(session.canRecord)
      await session.startRecording()
      XCTAssertEqual(session.attemptsStarted, 128)
      _ = await session.reset().value
      XCTAssertFalse(session.canRecord)
      _ = await session.end().value
    }
    func testDelayedPrepareRetakeThenDuplicateCloseJoinCleanupBeforeDiscard() async {
      let capture = SoundCapturer()
      let driver = SoundPlaybackDriver(blocked: [.prepare, .stop])
      let player = SoundPlayer(files: capture.files, driver: driver)
      let processor = SoundProcessor()
      defer {
        driver.releaseAll()
        capture.remove()
      }
      let session = await configured(capture, processor, player)
      await record(session)
      let playback = Task { await session.togglePlayback() }
      let preparing = await XCTWaiter.fulfillment(of: [driver.preparing], timeout: 2)
      XCTAssertEqual(preparing, .completed)
      let id = session.activePlaybackID
      XCTAssertNotNil(id)
      XCTAssertFalse(session.isPlaying)
      XCTAssertTrue(session.playbackPending)
      XCTAssertFalse(session.canCheck)
      session.checkRecording()
      XCTAssertEqual(processor.posts, 0)
      XCTAssertEqual(session.checksClaimed, 0)
      let retake = session.retake()
      let close = session.end()
      let duplicateClose = session.end()
      _ = session.reset()  // A newer reset cannot supersede the learner's pending Close.
      XCTAssertTrue(session.pendingClose)
      XCTAssertEqual(session.activePlaybackID, id)
      XCTAssertNotNil(player.gate.currentLease)
      XCTAssertEqual(capture.discards, 0)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      driver.releasePrepare()
      let stopping = await XCTWaiter.fulfillment(of: [driver.stopping], timeout: 2)
      XCTAssertEqual(stopping, .completed)
      XCTAssertEqual(driver.count(.play), 0)
      XCTAssertEqual(capture.discards, 0)
      await player.callbackBarrier(id: id!, success: true)
      XCTAssertEqual(session.activePlaybackID, id)
      driver.releaseStop()
      let retakeReleased = await retake.value
      let closeReleased = await close.value
      let duplicateReleased = await duplicateClose.value
      await playback.value
      XCTAssertTrue(retakeReleased)
      XCTAssertTrue(closeReleased)
      XCTAssertTrue(duplicateReleased)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertNil(session.activePlaybackID)
      XCTAssertNil(player.gate.currentLease)
      XCTAssertFalse(session.isPlaying)
      XCTAssertFalse(session.playbackFailed)
      XCTAssertEqual(driver.count(.stop), 1)
      XCTAssertEqual(driver.count(.release), 1)
      XCTAssertEqual(capture.discards, 1)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertEqual(processor.posts, 0)
    }

    func testFailedPlaybackThenFileCleanupRetriesKeepCloseOwnedUntilExactRemoval() async {
      let capture = SoundCapturer()
      let driver = SoundPlaybackDriver(failures: 1)
      let player = SoundPlayer(files: capture.files, driver: driver)
      let processor = SoundProcessor()
      defer {
        driver.releaseAll()
        capture.remove()
      }
      let session = await configured(capture, processor, player)
      await record(session)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      let id = session.activePlaybackID!
      let lease = player.gate.currentLease
      capture.failDiscard = true
      let closeReleased = await session.end().value
      XCTAssertFalse(closeReleased)
      let original = player.requestStop(id: id)!
      let negative = original.receipt
      XCTAssertEqual(negative?.result, .cleanupUnconfirmed)
      XCTAssertEqual(session.activePlaybackID, id)
      XCTAssertEqual(player.gate.currentLease, lease)
      XCTAssertEqual(capture.discards, 1)
      XCTAssertTrue(capture.files.pendingCleanupOwners.contains(capture.ownerID))
      XCTAssertFalse(capture.files.canRemove(capture.url, owner: capture.ownerID))
      await session.startRecording()
      session.checkRecording()
      XCTAssertEqual(capture.starts, 1)
      XCTAssertEqual(processor.posts, 0)
      await session.retryPlaybackCleanup()
      XCTAssertEqual(original.receipt, negative)
      XCTAssertNil(session.activePlaybackID)
      XCTAssertNil(player.gate.currentLease)
      XCTAssertEqual(session.phase, .localCleanupBlocked)
      XCTAssertEqual(session.captureCleanupState.fileBlockedOwnerIDs, [capture.ownerID])
      XCTAssertEqual(capture.discards, 1)
      XCTAssertTrue(session.pendingClose)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      capture.failDiscard = false
      await session.retryCaptureCleanup()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(capture.discards, 1, "A genuinely removed retry file is never discarded again")
      XCTAssertEqual(session.captureCleanupState, .idle)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertFalse(capture.files.protectedURLs.contains(capture.url.standardizedFileURL))
      XCTAssertEqual(driver.count(.deactivate), 2)
      XCTAssertEqual(driver.count(.stop), 1)
      await player.callbackBarrier(id: id, success: false)
      XCTAssertEqual(player.sessionCallbackDeliveries[id], 1)
      XCTAssertFalse(session.playbackFailed)
      XCTAssertFalse(session.isPlaying)
    }

    func testUnreadableStopRetainsFailedOutcomeAfterAsynchronousCleanupRemovesFile() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await session.startRecording()
      capture.invalidStop = true
      session.stopRecording()
      let cleaned = await session.waitForCleanup()
      XCTAssertTrue(cleaned)
      XCTAssertEqual(session.phase, .failed(.invalidRecording))
      XCTAssertEqual(capture.discards, 1)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertTrue(capture.files.protectedURLs.isEmpty)
      XCTAssertTrue(session.canRecord)
      XCTAssertFalse(session.canReplay)
      XCTAssertEqual(session.attemptsFinished, 1)
      XCTAssertEqual(processor.posts, 0)
      _ = await session.end().value
    }

    func testIdentityFreeStartupScanFailureDisablesRecordWithoutBlockingUnownedClose() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      capture.startupScanFailed = true
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await session.startRecording()
      let cleaned = await session.waitForCleanup()
      XCTAssertTrue(cleaned)
      XCTAssertEqual(session.phase, .failed(.invalidRecording))
      XCTAssertTrue(session.recordingUnavailable)
      XCTAssertFalse(session.canRecord)
      XCTAssertFalse(session.captureHardwareBlocked)
      XCTAssertFalse(session.captureFileBlocked)
      XCTAssertEqual(session.captureCleanupState, .idle)
      XCTAssertTrue(capture.files.protectedURLs.isEmpty)
      XCTAssertEqual(capture.starts, 1)
      await session.startRecording()
      XCTAssertEqual(capture.starts, 1, "The session refuses before another capturer call")
      let closed = await session.end().value
      XCTAssertTrue(closed)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(capture.discards, 0)
    }

    func testOldSessionCompletionCannotClearNewOperationAfterExactCallbackBarrier() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      let player = SoundPlayer(files: capture.files)
      defer { capture.remove() }
      let session = await configured(capture, processor, player)
      await record(session)
      await session.togglePlayback()
      let oldID = session.activePlaybackID!
      _ = await session.retake().value
      await record(session)
      await session.togglePlayback()
      let newID = session.activePlaybackID!
      XCTAssertNotEqual(oldID, newID)
      await player.callbackBarrier(id: oldID, success: false)
      XCTAssertEqual(player.sessionCallbackDeliveries[oldID], 1)
      XCTAssertEqual(session.activePlaybackID, newID)
      XCTAssertTrue(session.isPlaying)
      XCTAssertFalse(session.playbackFailed)
      XCTAssertEqual(player.starts, 2)
      XCTAssertEqual(player.gate.currentLease?.operationID, newID)
      _ = await session.end().value
    }

    func testNilStopHandleForRefusedStartClearsNonexistentOperationAndRetainsTake() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      let player = RefusedSoundPlayer()
      defer { capture.remove() }
      let session = await configured(capture, processor, player)
      await record(session)
      await session.togglePlayback()
      XCTAssertNil(session.activePlaybackID)
      XCTAssertFalse(session.playbackPending)
      XCTAssertTrue(session.playbackFailed)
      XCTAssertTrue(session.hasRecording)
      XCTAssertTrue(session.canReplay)
      XCTAssertEqual(player.starts, 1)
      _ = await session.end().value
    }

    func testConcreteBorrowRefusalRegistersRecoveryOnceAndFileOnlySecondClosePreservesIt()
      async throws
    {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: directory) }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let captureDriver = SoundOwnedCaptureDriver()
      let capture = SoundOwnedCapture(
        SystemAudioCapturer(
          recordingStore: TemporaryRecordingStore(directory: directory), fileOwnership: files,
          hardwareOwnership: gate, driverFactory: { captureDriver },
          summaryReader: { _ in .init(duration: 0.2, averagePower: -20) }))
      let playbackDriver = SoundPlaybackDriver(failures: 1)
      defer { playbackDriver.releaseAll() }
      let player = SoundPlayer(files: files, driver: playbackDriver, gate: gate)
      let processor = SoundProcessor()
      let session = ResearchSoundSession(
        capturer: capture, player: player, processor: processor, fileOwnership: files)
      await session.startRecording()
      session.stopRecording()
      let url = try XCTUnwrap(captureDriver.url)
      await session.togglePlayback()
      let id = try XCTUnwrap(session.activePlaybackID)
      let firstClose = await session.end().value
      XCTAssertFalse(firstClose)
      let original = try XCTUnwrap(player.requestStop(id: id))
      let negative = original.receipt
      XCTAssertEqual(negative?.result, .cleanupUnconfirmed)
      let owner = try XCTUnwrap(capture.cleanupState.fileBlockedOwnerIDs.first)
      XCTAssertEqual(capture.cleanupState.fileBlockedOwnerIDs, [owner])
      XCTAssertTrue(files.pendingCleanupOwners.contains(owner))
      XCTAssertFalse(files.canRemove(url, owner: owner))
      XCTAssertEqual(capture.discardCalls, 1)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      let hardwareBlockedClose = await session.end().value
      XCTAssertFalse(hardwareBlockedClose)
      XCTAssertEqual(capture.discardCalls, 1)
      XCTAssertEqual(gate.currentLease?.operationID, id)
      await session.startRecording()
      XCTAssertEqual(capture.startCalls, 1)
      await session.retryPlaybackCleanup()
      XCTAssertNil(session.activePlaybackID)
      XCTAssertNil(gate.currentLease)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertEqual(capture.discardCalls, 1)
      XCTAssertTrue(files.pendingCleanupOwners.contains(owner))
      let permittedFileOnlyClose = await session.end().value
      XCTAssertTrue(permittedFileOnlyClose)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertTrue(files.protectedURLs.contains(url.standardizedFileURL))
      XCTAssertTrue(files.retryCleanup(owner: owner))
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertFalse(files.pendingCleanupOwners.contains(owner))
      XCTAssertEqual(original.receipt, negative)
    }

    func testFileOnlySecondCloseRefusesWithoutProcessHeldRecoveryAndExplainsRetry() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await record(session)
      capture.failDiscard = true
      capture.registerRecovery = false
      let firstClose = await session.end().value
      XCTAssertFalse(firstClose)
      XCTAssertFalse(session.playbackPending)
      XCTAssertFalse(session.captureHardwareBlocked)
      XCTAssertEqual(session.captureCleanupState.fileBlockedOwnerIDs, [capture.ownerID])
      XCTAssertFalse(capture.files.pendingCleanupOwners.contains(capture.ownerID))
      XCTAssertTrue(session.closeNote?.contains("Use Retry recording cleanup") == true)
      let secondClose = await session.end().value
      XCTAssertFalse(secondClose)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      capture.failDiscard = false
      await session.retryCaptureCleanup()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
    }

    func testCaptureHardwareFailureDoesNotEscapeCloseAndRetriesExactVisibleIdentity() async {
      let capture = SoundCapturer()
      let processor = SoundProcessor()
      defer { capture.remove() }
      let session = await configured(capture, processor)
      await session.startRecording()
      capture.failCancelHardware = true
      let closeReleased = await session.end().value
      XCTAssertFalse(closeReleased)
      XCTAssertEqual(session.captureCleanupState.hardwareBlockedOperationID, capture.ownerID)
      XCTAssertTrue(session.dismissalBlocked)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      let secondClose = await session.end().value
      XCTAssertFalse(secondClose)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertFalse(session.canRecord)
      await session.retryCaptureCleanup()
      XCTAssertTrue(session.captureHardwareBlocked)
      capture.failCancelHardware = false
      await session.retryCaptureCleanup()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(session.captureCleanupState, .idle)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
    }
    func testEarlierSynchronousCaptureRetryKeepsExactCompletedFileReceiptAfterOriginalThrow()
      async throws
    {
      var observation: AnyCancellable?
      var recovered: CaptureCleanupReceipt?
      let fixture = try SoundReceiptFixture(beforeSession: { capture, removal in
        observation = capture.cleanupStatePublisher.sink { state in
          MainActor.assertIsolated()
          guard recovered == nil, let owner = state.fileBlockedOwnerIDs.first else { return }
          removal.fail = false
          recovered = capture.retryCleanup(operationID: owner)
        }
      })
      receiptFixtures.append(fixture)
      defer { observation?.cancel() }
      let session = fixture.session
      await session.startRecording()
      session.stopRecording()
      let recording = try XCTUnwrap(fixture.capture.lastStoppedRecording)
      let owner = try XCTUnwrap(recording.cleanupOwnerID)
      fixture.removal.fail = true
      let removed = await session.retake().value
      XCTAssertTrue(removed)
      XCTAssertEqual(fixture.capture.lastDiscardError, .couldNotDeleteTemporaryRecording)
      XCTAssertEqual(recovered?.operationID, owner)
      XCTAssertEqual(recovered?.result, .released)
      XCTAssertEqual(fixture.capture.completedFileCleanup(operationID: owner), recovered)
      XCTAssertNil(fixture.capture.completedFileCleanup(operationID: UUID()))
      XCTAssertEqual(session.captureCleanupState, .idle)
      XCTAssertFalse(session.hasRecording)
      XCTAssertFalse(session.captureFileBlocked)
      XCTAssertTrue(session.canRecord)
      XCTAssertNil(fixture.gate.currentLease)
      XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
      XCTAssertEqual(fixture.capture.discardCalls, 1)
      XCTAssertEqual(fixture.removal.calls, [recording.url, recording.url])
      _ = await session.retake().value
      XCTAssertEqual(fixture.capture.discardCalls, 1)
      XCTAssertEqual(fixture.removal.calls.count, 2)
    }

    func testCompletedExternalPlaybackRetryRequiresExactPositiveReceiptBeforeCaptureCleanup()
      async throws
    {
      let fixture = try SoundReceiptFixture(playbackFailures: 1)
      receiptFixtures.append(fixture)
      let session = fixture.session
      await session.startRecording()
      session.stopRecording()
      let recording = try XCTUnwrap(fixture.capture.lastStoppedRecording)
      let owner = try XCTUnwrap(recording.cleanupOwnerID)
      await session.togglePlayback()
      let id = try XCTUnwrap(session.activePlaybackID)
      let lease = fixture.gate.currentLease
      let firstClose = await session.end().value
      XCTAssertFalse(firstClose)
      let original = try XCTUnwrap(fixture.player.requestStop(id: id))
      let negative = try XCTUnwrap(original.receipt)
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertEqual(session.activePlaybackID, id)
      XCTAssertEqual(fixture.gate.currentLease, lease)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(owner))
      XCTAssertFalse(fixture.files.canRemove(recording.url, owner: owner))
      XCTAssertTrue(session.hasRecording)
      XCTAssertEqual(fixture.capture.discardCalls, 1)
      let gateRetry = try XCTUnwrap(fixture.gate.retryPlaybackCleanup())
      let positive = await gateRetry.value()
      XCTAssertEqual(positive.operation.id, id)
      XCTAssertEqual(positive.result, .released)
      XCTAssertNil(fixture.gate.currentLease)
      XCTAssertEqual(fixture.player.state, .idle)
      XCTAssertEqual(session.activePlaybackID, id, "Shared idle cannot release this consumer")
      XCTAssertTrue(session.canRetryPlaybackCleanup)
      XCTAssertTrue(session.hasRecording)
      XCTAssertNil(fixture.player.retryCleanup(id: id))
      XCTAssertEqual(fixture.player.completedCleanupRetry(id: id), positive)
      XCTAssertNil(fixture.player.completedCleanupRetry(id: UUID()))
      await session.retryPlaybackCleanup()
      XCTAssertNil(session.activePlaybackID)
      XCTAssertFalse(session.canRetryPlaybackCleanup)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertTrue(session.hasRecording)
      XCTAssertEqual(fixture.capture.discardCalls, 1)
      await session.retryCaptureCleanup()
      _ = await session.waitForCleanup()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertFalse(session.hasRecording)
      XCTAssertEqual(fixture.capture.completedFileCleanup(operationID: owner)?.result, .released)
      XCTAssertEqual(fixture.capture.discardCalls, 1)
      XCTAssertEqual(fixture.removal.calls, [recording.url])
      XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertEqual(fixture.playbackDriver.count(.stop), 1)
      XCTAssertEqual(fixture.playbackDriver.count(.deactivate), 2)
      await fixture.player.callbackBarrier(id: id, success: false)
      XCTAssertFalse(session.playbackFailed)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(original.receipt, negative)
    }

    func testEarlierSynchronousRecoveryPreservesCancelAndFailedStopOwnerEvidence() async throws {
      for failedStop in [false, true] {
        for hardwareFailure in [false, true] {
          var observation: AnyCancellable?
          var expectedOwner: UUID?
          var recovered: CaptureCleanupReceipt?
          let fixture = try SoundReceiptFixture(beforeSession: { capture, removal in
            observation = capture.cleanupStatePublisher.sink { state in
              MainActor.assertIsolated()
              guard recovered == nil, let owner = expectedOwner,
                state.hardwareBlockedOperationID == owner
                  || state.fileBlockedOwnerIDs.contains(owner)
              else { return }
              removal.fail = false
              recovered = capture.retryCleanup(operationID: owner)
            }
          })
          receiptFixtures.append(fixture)
          defer { observation?.cancel() }
          let session = fixture.session
          await session.startRecording()
          let owner = try XCTUnwrap(fixture.gate.currentLease?.operationID)
          let url = try XCTUnwrap(fixture.captureDriver.url)
          expectedOwner = owner
          fixture.captureDriver.deactivateFailures = hardwareFailure ? 1 : 0
          fixture.removal.fail = !hardwareFailure
          fixture.removal.failSummaryRead = failedStop && !hardwareFailure
          let expectedError: AudioCaptureError =
            hardwareFailure
            ? .hardwareCleanupUnconfirmed : .couldNotDeleteTemporaryRecording
          if failedStop {
            session.stopRecording()
            let cleaned = await session.waitForCleanup()
            XCTAssertTrue(cleaned)
            XCTAssertEqual(fixture.capture.lastStopError, expectedError)
            XCTAssertEqual(session.phase, .failed(.invalidRecording))
            XCTAssertTrue(session.canRecord)
          } else {
            let closed = await session.end().value
            XCTAssertTrue(closed)
            XCTAssertEqual(fixture.capture.lastCancelError, expectedError)
            XCTAssertEqual(session.phase, .ended)
          }
          XCTAssertEqual(recovered?.operationID, owner)
          XCTAssertEqual(recovered?.result, .released)
          XCTAssertEqual(fixture.capture.completedFileCleanup(operationID: owner), recovered)
          XCTAssertNil(fixture.capture.completedFileCleanup(operationID: UUID()))
          XCTAssertEqual(session.captureCleanupState, .idle)
          XCTAssertFalse(session.captureHardwareBlocked)
          XCTAssertFalse(session.captureFileBlocked)
          XCTAssertFalse(session.hasRecording)
          XCTAssertNil(fixture.gate.currentLease)
          XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
          XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
          XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
          XCTAssertEqual(fixture.capture.startCalls, 1)
          XCTAssertEqual(fixture.capture.discardCalls, 0)
          XCTAssertEqual(session.checksClaimed, 0)
          let ended = await session.end().value
          XCTAssertTrue(ended)
          fixture.captureDriver.sendCompletion(success: false)
          XCTAssertEqual(session.phase, .ended)
          XCTAssertEqual(fixture.capture.lastStopError, failedStop ? expectedError : nil)
          XCTAssertEqual(fixture.capture.lastCancelError, failedStop ? nil : expectedError)
          XCTAssertEqual(fixture.capture.startCalls, 1)
        }
      }
    }

    func testExternalPlaybackRetryThenRegistryRemovalKeepsRetryStoppingAvailableWithoutTake()
      async throws
    {
      let fixture = try SoundReceiptFixture(playbackFailures: 1)
      receiptFixtures.append(fixture)
      let session = fixture.session
      await session.startRecording()
      session.stopRecording()
      let recording = try XCTUnwrap(fixture.capture.lastStoppedRecording)
      let owner = try XCTUnwrap(recording.cleanupOwnerID)
      await session.togglePlayback()
      let id = try XCTUnwrap(session.activePlaybackID)
      let closed = await session.end().value
      XCTAssertFalse(closed)
      let original = try XCTUnwrap(fixture.player.requestStop(id: id))
      let negative = try XCTUnwrap(original.receipt)
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(owner))
      let gateRetry = try XCTUnwrap(fixture.gate.retryPlaybackCleanup())
      let positive = await gateRetry.value()
      XCTAssertEqual(positive.operation.id, id)
      XCTAssertEqual(positive.result, .released)
      XCTAssertEqual(session.activePlaybackID, id)
      XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
      XCTAssertEqual(fixture.capture.completedFileCleanup(operationID: owner)?.result, .released)
      XCTAssertFalse(session.hasRecording)
      XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      let originalWait = await session.waitForCleanup()
      XCTAssertFalse(originalWait, "File removal and shared idle cannot release the playback ID")
      XCTAssertEqual(session.activePlaybackID, id)
      XCTAssertTrue(
        session.canRetryPlaybackCleanup, "Retry stopping must remain visible without a take")
      XCTAssertEqual(original.receipt, negative)
      await session.retryPlaybackCleanup()
      let settled = await session.waitForCleanup()
      XCTAssertTrue(settled)
      XCTAssertNil(session.activePlaybackID)
      XCTAssertFalse(session.canRetryPlaybackCleanup)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertEqual(fixture.capture.discardCalls, 1)
      XCTAssertEqual(fixture.removal.calls, [recording.url])
      XCTAssertNil(fixture.gate.currentLease)
      await fixture.player.callbackBarrier(id: id, success: false)
      XCTAssertFalse(session.playbackFailed)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(fixture.capture.startCalls, 1)
    }

    func testCaptureHardwareReleaseWithRetainedFileAllowsOnlyProvenFileRecoveryClose() async throws
    {
      let fixture = try SoundReceiptFixture()
      receiptFixtures.append(fixture)
      let session = fixture.session
      await session.startRecording()
      let owner = try XCTUnwrap(fixture.gate.currentLease?.operationID)
      let url = try XCTUnwrap(fixture.captureDriver.url)
      fixture.captureDriver.deactivateFailures = 1
      let firstClose = await session.end().value
      XCTAssertFalse(firstClose)
      XCTAssertTrue(session.captureHardwareBlocked)
      XCTAssertEqual(session.captureCleanupState.hardwareBlockedOperationID, owner)
      fixture.removal.fail = true
      await session.retryCaptureCleanup()
      XCTAssertEqual(fixture.capture.lastRetryReceipt?.operationID, owner)
      XCTAssertEqual(fixture.capture.lastRetryReceipt?.result, .hardwareReleasedFilesRetained)
      XCTAssertNil(fixture.gate.currentLease)
      XCTAssertFalse(session.captureHardwareBlocked)
      XCTAssertTrue(session.captureFileBlocked)
      XCTAssertEqual(session.captureCleanupState.fileBlockedOwnerIDs, [owner])
      XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(owner))
      XCTAssertNil(fixture.capture.completedFileCleanup(operationID: owner))
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      let retained = await session.waitForCleanup()
      XCTAssertFalse(retained)
      let secondClose = await session.end().value
      XCTAssertTrue(secondClose)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(owner))
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      fixture.removal.fail = false
      XCTAssertTrue(fixture.files.retryCleanup(owner: owner))
      XCTAssertEqual(fixture.capture.completedFileCleanup(operationID: owner)?.result, .released)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      fixture.captureDriver.sendCompletion(success: false)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(fixture.capture.lastCancelError, .hardwareCleanupUnconfirmed)
      XCTAssertEqual(fixture.capture.startCalls, 1)
      XCTAssertEqual(fixture.capture.discardCalls, 0)
    }
  }

  @MainActor private final class SoundReceiptRemoval {
    var fail = false
    var failSummaryRead = false
    private(set) var calls: [URL] = []
    func remove(_ url: URL) throws {
      calls.append(url)
      if fail { throw AudioCaptureError.couldNotDeleteTemporaryRecording }
      try FileManager.default.removeItem(at: url)
    }
  }
  @MainActor private final class SoundReceiptFixture {
    let directory: URL
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let captureDriver = SoundOwnedCaptureDriver()
    let removal = SoundReceiptRemoval()
    let capture: SoundOwnedCapture
    let playbackDriver: SoundPlaybackDriver
    let player: SoundPlayer
    let session: ResearchSoundSession
    init(
      playbackFailures: Int = 0,
      beforeSession: ((SoundOwnedCapture, SoundReceiptRemoval) -> Void)? = nil
    ) throws {
      directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "sound-receipt-\(UUID().uuidString)")
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      let driver = captureDriver
      let removal = self.removal
      capture = SoundOwnedCapture(
        SystemAudioCapturer(
          recordingStore: TemporaryRecordingStore(directory: directory), fileOwnership: files,
          hardwareOwnership: gate, driverFactory: { driver },
          summaryReader: { _ in
            if removal.failSummaryRead { throw AudioCaptureError.couldNotReadRecording }
            return .init(duration: 0.2, averagePower: -20)
          },
          removeFile: { try removal.remove($0) }))
      playbackDriver = SoundPlaybackDriver(failures: playbackFailures)
      player = SoundPlayer(files: files, driver: playbackDriver, gate: gate)
      beforeSession?(capture, removal)
      session = ResearchSoundSession(
        capturer: capture, player: player,
        processor: SoundProcessor(), fileOwnership: files)
    }
    func clean() async {
      playbackDriver.releaseAll()
      removal.fail = false
      removal.failSummaryRead = false
      captureDriver.deactivateFailures = 0
      _ = await session.waitForCleanup()
      await session.retryPlaybackCleanup()
      await session.retryCaptureCleanup()
      _ = await session.end().value
      for owner in files.pendingCleanupOwners { _ = files.retryCleanup(owner: owner) }
      XCTAssertNil(gate.currentLease)
      XCTAssertTrue(files.protectedURLs.isEmpty)
      if gate.currentLease == nil, files.protectedURLs.isEmpty {
        try? FileManager.default.removeItem(at: directory)
      }
    }
  }
  @MainActor private final class RefusedSoundPlayer: AcknowledgedPracticeAudioPlaying {
    private let states = CurrentValueSubject<PracticePlaybackRuntimeState, Never>(.idle)
    var state: PracticePlaybackRuntimeState { .idle }
    var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
      states.eraseToAnyPublisher()
    }
    private(set) var starts = 0
    func play(
      id: UUID, url: URL,
      onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
    ) async throws {
      starts += 1
      throw PracticePlaybackRuntimeError.couldNotStart(.init(id: id, url: url))
    }
    func requestStop(id: UUID) -> PracticePlaybackCleanup? { nil }
    func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { nil }
    func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? { nil }
  }
  /// Permission is controlled; all ownership, discard and recovery are the concrete coordinator.
  @MainActor private final class SoundOwnedCapture: AudioCapturing {
    let actual: SystemAudioCapturer
    private(set) var startCalls = 0
    private(set) var discardCalls = 0
    private(set) var lastStoppedRecording: CapturedRecording?
    private(set) var lastDiscardError: AudioCaptureError?
    private(set) var lastStopError: AudioCaptureError?
    private(set) var lastCancelError: AudioCaptureError?
    private(set) var lastRetryReceipt: CaptureCleanupReceipt?
    init(_ actual: SystemAudioCapturer) { self.actual = actual }
    var cleanupState: CaptureCleanupState { actual.cleanupState }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      actual.cleanupStatePublisher
    }
    func requestPermission() async -> Bool { true }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      startCalls += 1
      try actual.start(onFinish: onFinish)
    }
    func stop() throws -> CapturedRecording {
      do {
        let recording = try actual.stop()
        lastStoppedRecording = recording
        return recording
      } catch {
        lastStopError = error as? AudioCaptureError
        throw error
      }
    }
    func cancel() throws {
      do { try actual.cancel() } catch {
        lastCancelError = error as? AudioCaptureError
        throw error
      }
    }
    func discard(_ recording: CapturedRecording) throws {
      discardCalls += 1
      do { try actual.discard(recording) } catch {
        lastDiscardError = error as? AudioCaptureError
        throw error
      }
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      let receipt = actual.retryCleanup(operationID: operationID)
      lastRetryReceipt = receipt
      return receipt
    }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      actual.completedFileCleanup(operationID: operationID)
    }
  }
  @MainActor private final class SoundOwnedCaptureDriver: CaptureHardwareDriver {
    private(set) var url: URL?
    var deactivateFailures = 0
    private var recorderID: UUID?
    private var completion: (@MainActor @Sendable (UUID, Bool) -> Void)?
    func configureActivate() throws {}
    func createRecorder(
      url: URL, recorderID: UUID,
      onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
    ) throws {
      self.url = url
      self.recorderID = recorderID
      completion = onFinish
      try FeedbackFixture.wav().write(to: url)
    }
    func prepare() throws -> Bool { true }
    func record() throws -> Bool { true }
    func stop() throws {}
    func detachRelease() throws {}
    func deactivate() throws {
      if deactivateFailures > 0 {
        deactivateFailures -= 1
        throw AudioCaptureError.hardwareCleanupUnconfirmed
      }
    }
    func sendCompletion(success: Bool) {
      if let recorderID { completion?(recorderID, success) }
    }
  }

  @MainActor private final class SoundCapturer: AudioCapturing {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    private(set) var ownerID = UUID()
    let files = ProcessAudioFileOwnership()
    var url: URL { directory.appendingPathComponent("cadence-attempt-sound.wav") }
    private var completedReceipts: [UUID: CaptureCleanupReceipt] = [:]
    private(set) var cleanupState = CaptureCleanupState.idle
    private let cleanupEvents = PassthroughSubject<(UInt64, CaptureCleanupState), Never>()
    private var revision: UInt64 = 0
    private var pendingEvents: [(UInt64, CaptureCleanupState)] = []
    private var publishing = false
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      Deferred { [self] in
        let initialRevision = revision
        let initial = CurrentValueSubject<CaptureCleanupState, Never>(cleanupState)
        let observation = cleanupEvents.sink { revision, state in
          if revision > initialRevision { initial.send(state) }
        }
        return initial.removeDuplicates()
          .handleEvents(receiveCancel: { observation.cancel() }).eraseToAnyPublisher()
      }.eraseToAnyPublisher()
    }
    private func publish(_ state: CaptureCleanupState) {
      guard cleanupState != state else { return }
      cleanupState = state
      revision += 1
      pendingEvents.append((revision, state))
      guard !publishing else { return }
      publishing = true
      defer { publishing = false }
      while !pendingEvents.isEmpty { cleanupEvents.send(pendingEvents.removeFirst()) }
    }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      completedReceipts[operationID]
    }
    var starts = 0, cancels = 0, discards = 0
    var granted = true, delayPermission = false, failDiscard = false, active = false
    var failCancelHardware = false, invalidStop = false, startupScanFailed = false
    var registerRecovery = true
    var permission: CheckedContinuation<Bool, Never>?
    func requestPermission() async -> Bool {
      if delayPermission { return await withCheckedContinuation { permission = $0 } }
      return granted
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      starts += 1
      if startupScanFailed { throw AudioCaptureError.couldNotDeleteTemporaryRecording }
      guard cleanupState == .idle else { throw AudioCaptureError.hardwareCleanupUnconfirmed }
      ownerID = UUID()
      active = true
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      try FeedbackFixture.wav().write(to: url)
      files.retain(url, owner: ownerID)
    }
    func stop() throws -> CapturedRecording {
      active = false
      if invalidStop { try Data([0]).write(to: url) }
      return .init(
        url: url, summary: .init(duration: 0.2, averagePower: -20), cleanupOwnerID: ownerID)
    }
    func cancel() throws {
      cancels += 1
      guard active else { return }
      guard !cleanupState.hasHardwareIssue else {
        throw AudioCaptureError.hardwareCleanupUnconfirmed
      }
      if failCancelHardware {
        publish(.init(hardwareBlockedOperationID: ownerID, fileBlockedOwnerIDs: []))
        throw AudioCaptureError.hardwareCleanupUnconfirmed
      }
      active = false
      try removeOwned()
    }
    func discard(_ recording: CapturedRecording) throws {
      guard !cleanupState.fileBlockedOwnerIDs.contains(ownerID) else {
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      discards += 1
      guard recording.url == url, files.protectedURLs.contains(url.standardizedFileURL) else {
        throw AudioCaptureError.recordingNotOwned
      }
      try removeOwned()
    }
    private func removeOwned() throws {
      guard files.canRemove(url, owner: ownerID), !failDiscard else {
        if registerRecovery {
          files.registerCleanupRecovery(owner: ownerID) { [self] in
            retryCleanup(operationID: ownerID).allRequestedFilesRemoved
          }
        }
        publish(.init(hardwareBlockedOperationID: nil, fileBlockedOwnerIDs: [ownerID]))
        throw failDiscard
          ? AudioCaptureError.couldNotDeleteTemporaryRecording
          : AudioCaptureError.recordingInUse
      }
      try FileManager.default.removeItem(at: url)
      files.didRemove(url, owner: ownerID)
      completedReceipts[ownerID] = .init(operationID: ownerID, result: .released)
      publish(.idle)
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      guard operationID == ownerID,
        cleanupState.hardwareBlockedOperationID == operationID
          || cleanupState.fileBlockedOwnerIDs.contains(operationID)
      else { return .init(operationID: operationID, result: .refused) }
      if cleanupState.hasHardwareIssue, failCancelHardware {
        return .init(operationID: operationID, result: .cleanupUnconfirmed)
      }
      active = false
      do {
        try removeOwned()
        return .init(operationID: operationID, result: .released)
      } catch {
        return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
      }
    }
    func remove() { try? FileManager.default.removeItem(at: directory) }
  }
  /// The production facade and runtime execute only this controlled synchronous queue driver.
  @MainActor private final class SoundPlayer: AcknowledgedPracticeAudioPlaying {
    let gate: AudioHardwareOwnership
    private let actual: SystemAcknowledgedPracticeAudioPlayer
    private let drivers: SoundDriverRegistry
    private var sessionCallbacks: [UUID: @MainActor (PracticePlaybackOperation, Bool) -> Void] = [:]
    private var operations: [UUID: PracticePlaybackOperation] = [:]
    private(set) var sessionCallbackDeliveries: [UUID: Int] = [:]
    var starts: Int { drivers.starts }
    var state: PracticePlaybackRuntimeState { actual.state }
    var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> { actual.statePublisher }
    init(
      files: ProcessAudioFileOwnership, driver: SoundPlaybackDriver? = nil,
      gate: AudioHardwareOwnership = AudioHardwareOwnership()
    ) {
      self.gate = gate
      let drivers = SoundDriverRegistry(first: driver)
      self.drivers = drivers
      actual = SystemAcknowledgedPracticeAudioPlayer(ownership: gate, fileOwnership: files) {
        operation, finish in drivers.make(operation: operation, finish: finish)
      }
    }
    func play(
      id: UUID, url: URL,
      onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
    ) async throws {
      operations[id] = .init(id: id, url: url)
      sessionCallbacks[id] = onFinish
      try await actual.play(id: id, url: url, onFinish: onFinish)
    }
    private func deliverSessionCompletion(id: UUID, success: Bool) {
      guard let operation = operations[id], let callback = sessionCallbacks[id] else {
        XCTFail("Exact saved session callback missing")
        return
      }
      sessionCallbackDeliveries[id, default: 0] += 1
      callback(operation, success)
    }
    // Deliberately bypass runtime filtering and wait for this exact saved callback to reach the
    // session, so assertions exercise its own eligibility guard rather than queue timing.
    func callbackBarrier(id: UUID, success: Bool) async {
      let delivered = XCTestExpectation(description: "exact saved session callback delivered")
      Task { @MainActor in
        deliverSessionCompletion(id: id, success: success)
        delivered.fulfill()
      }
      let result = await XCTWaiter.fulfillment(of: [delivered], timeout: 2)
      XCTAssertEqual(result, .completed)
    }
    func requestStop(id: UUID) -> PracticePlaybackCleanup? { actual.requestStop(id: id) }
    func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { actual.retryCleanup(id: id) }
    func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
      actual.completedCleanupRetry(id: id)
    }
  }
  private final class SoundDriverRegistry: @unchecked Sendable {
    private let lock = NSLock()
    private var first: SoundPlaybackDriver?
    private var drivers: [UUID: SoundPlaybackDriver] = [:]
    init(first: SoundPlaybackDriver?) { self.first = first }
    var starts: Int { lock.withLock { drivers.values.reduce(0) { $0 + $1.count(.play) } } }
    func make(
      operation: PracticePlaybackOperation,
      finish: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
    ) -> SoundPlaybackDriver {
      let driver = lock.withLock {
        let driver = first ?? SoundPlaybackDriver()
        first = nil
        drivers[operation.id] = driver
        return driver
      }
      driver.configure(operation: operation, finish: finish)
      return driver
    }
  }
  private final class SoundPlaybackDriver: PracticePlaybackDriver, @unchecked Sendable {
    enum Stage: Hashable { case prepare, play, stop, release, deactivate }
    enum Failure: Error { case gateExpired, cleanup }
    private let lock = NSLock()
    private let blocked: Set<Stage>
    private let failures: Int
    private let prepareGate = DispatchSemaphore(value: 0)
    private let stopGate = DispatchSemaphore(value: 0)
    let preparing = XCTestExpectation(description: "controlled playback prepare entered")
    let stopping = XCTestExpectation(description: "controlled playback stop entered")
    private var counts: [Stage: Int] = [:]
    private var operation: PracticePlaybackOperation?
    private var callback: (@Sendable (PracticePlaybackOperation, Bool) -> Void)?
    init(blocked: Set<Stage> = [], failures: Int = 0) {
      self.blocked = blocked
      self.failures = failures
    }
    func configure(
      operation: PracticePlaybackOperation,
      finish: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
    ) {
      lock.withLock {
        precondition(self.operation == nil, "One controlled driver belongs to one exact operation")
        self.operation = operation
        callback = finish
      }
    }
    func count(_ stage: Stage) -> Int { lock.withLock { counts[stage, default: 0] } }
    func activate() throws {}
    func prepare() throws -> Bool {
      try visit(.prepare)
      return true
    }
    func play() throws -> Bool {
      try visit(.play)
      return true
    }
    func stop() throws { try visit(.stop) }
    func releasePlaybackResources() throws { try visit(.release) }
    func deactivate() throws {
      try visit(.deactivate)
      if count(.deactivate) <= failures { throw Failure.cleanup }
    }
    func releasePrepare() { prepareGate.signal() }
    func releaseStop() { stopGate.signal() }
    func releaseAll() {
      releasePrepare()
      releaseStop()
    }
    func finish(success: Bool) {
      let captured = lock.withLock { (operation, callback) }
      if let operation = captured.0 { captured.1?(operation, success) }
    }
    private func visit(_ stage: Stage) throws {
      let count = lock.withLock {
        counts[stage, default: 0] += 1
        return counts[stage]!
      }
      if count == 1 {
        if stage == .prepare { preparing.fulfill() }
        if stage == .stop { stopping.fulfill() }
        if blocked.contains(stage) {
          let gate = stage == .prepare ? prepareGate : stopGate
          guard gate.wait(timeout: .now() + 8) == .success else { throw Failure.gateExpired }
        }
      }
    }
  }
  @MainActor private final class SoundProcessor: ResearchSoundProcessing {
    var currentDeclaration = SoundFixture.declaration
    var delayPrepare = false, delayDeclaration = false, prepareReturned = false, returned = false
    var preparing: CheckedContinuation<ResearchSoundPrepared, any Error>?
    var declPending: CheckedContinuation<ResearchSoundDeclaration, any Error>?
    var pending: CheckedContinuation<ResearchSoundObservation, any Error>?
    var preparedValue: ResearchSoundPrepared?
    var last: ResearchSoundPrepared?
    var posts = 0
    var cancelled: [ResearchSoundPrepared] = [], resets: [Int] = []
    func declaration() async throws -> ResearchSoundDeclaration {
      if delayDeclaration { return try await withCheckedThrowingContinuation { declPending = $0 } }
      return currentDeclaration
    }
    func finishDeclaration() {
      declPending?.resume(returning: currentDeclaration)
      declPending = nil
    }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      let value = try ResearchSoundContract.prepare(
        audio: FeedbackPCM.read(recording.url), declaration: declaration, context: context)
      preparedValue = value
      if delayPrepare {
        let value = try await withCheckedThrowingContinuation { preparing = $0 }
        prepareReturned = true
        return value
      }
      return value
    }
    func finishPreparation() {
      preparing?.resume(returning: preparedValue!)
      preparing = nil
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      posts += 1
      last = prepared
      returned = false
      let result = try await withCheckedThrowingContinuation { pending = $0 }
      returned = true
      return result
    }
    func resolve(_ value: ResearchSoundObservation) {
      pending?.resume(returning: value)
      pending = nil
    }
    func reject() {
      pending?.resume(throwing: RecordingFeedbackError.timeout)
      pending = nil
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws { cancelled.append(prepared) }
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    { resets.append(generation) }
  }
#endif
