#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Dispatch
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// These cases use the real acknowledged facade/runtime and capture cleanup implementation.
  /// All drivers and PCM are injected controls; no AV driver, permission request or endpoint runs.
  @MainActor
  final class ResearchFeedbackPlaybackOwnershipTests: XCTestCase {
    private var fixtures: [FeedbackOwnershipHarness] = []
    private var detachedCleanups: [@MainActor () async -> Void] = []
    private func ownDetachedCleanup(
      directory: URL, driver: FeedbackOwnershipDriver,
      gate: AudioHardwareOwnership, files: ProcessAudioFileOwnership,
      reset: @escaping @MainActor () -> Void = {}
    ) {
      detachedCleanups.append {
        reset()
        driver.releaseAll()
        if let captureID = gate.blockedCaptureOperationID {
          _ = gate.retryCaptureCleanup(operationID: captureID)
        }
        if let retry = gate.retryPlaybackCleanup() { _ = await retry.value() }
        for owner in files.pendingCleanupOwners { _ = files.retryCleanup(owner: owner) }
        XCTAssertNil(gate.currentLease)
        XCTAssertTrue(files.protectedURLs.isEmpty)
        if gate.currentLease == nil, files.protectedURLs.isEmpty {
          try? FileManager.default.removeItem(at: directory)
        }
      }
    }

    override func tearDown() async throws {
      for fixture in fixtures { await fixture.clean() }
      fixtures.removeAll()
      for cleanup in detachedCleanups { await cleanup() }
      detachedCleanups.removeAll()
      try await super.tearDown()
    }
    private func fixture(
      blocked: Set<FeedbackOwnershipDriver.Stage> = [], prepareSucceeds: Bool = true,
      cleanupFailures: Int = 0, startupScanFails: Bool = false,
      beforeSession: ((FeedbackOwnershipCapture, FeedbackOwnershipRemoval) -> Void)? = nil
    ) async throws -> FeedbackOwnershipHarness {
      let value = try FeedbackOwnershipHarness(
        blocked: blocked, prepareSucceeds: prepareSucceeds, cleanupFailures: cleanupFailures,
        startupScanFails: startupScanFails, beforeSession: beforeSession)
      fixtures.append(value)
      _ = await value.session.awaitPendingAudioCleanup()
      return value
    }
    private func wait(_ predicate: @MainActor () -> Bool) async {
      let deadline = ContinuousClock.now + .seconds(3)
      while !predicate(), ContinuousClock.now < deadline { await Task.yield() }
      XCTAssertTrue(predicate(), "Expected controlled transition")
    }

    func testStartedObserverCanCloseSynchronouslyWithoutRequestingPermission() async throws {
      let h = try await fixture()
      var close: Task<Bool, Never>?
      XCTAssertTrue(
        h.session.installGuidedObserver(
          owner: UUID(),
          observer: { event in
            if case .started = event { close = h.session.end() }
          }, allowsAction: { _ in true }))
      await h.session.startRecording()
      let result = await close?.value
      XCTAssertEqual(result, true)
      XCTAssertEqual(h.capture.permissions, 0)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      XCTAssertEqual(h.session.attemptsStarted, 1)
      XCTAssertEqual(h.session.attemptsFinished, 1)
      XCTAssertEqual(h.session.phase, .ended)
    }

    func testValidatedObserverSetupChangeCannotResurrectFeedbackAfterSynchronousRevocation()
      async throws
    {
      let h = try await fixture()
      XCTAssertTrue(
        h.session.installGuidedObserver(
          owner: UUID(),
          observer: { event in
            if case .validated = event {
              h.session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
            }
          }, allowsAction: { _ in true }))
      await h.record()
      h.session.checkRecording()
      await wait { h.word.pending }
      h.word.resolve(try h.feedback())
      await wait { h.word.returned && !h.session.isProcessing }
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.session.phase, .ready)
      XCTAssertNil(h.session.recognizerWordGuess)
      XCTAssertNil(h.session.latestReplay)
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertTrue(h.writer.entries.isEmpty)
    }

    func testHeldPrepareShowsPreparingAndRefusesRecordSwitchCheckAndGuidedTransition() async throws
    {
      let h = try await fixture(blocked: [.prepare])
      await h.record()
      let start = Task { await h.session.togglePlayback() }
      await wait { h.driver.count(.prepare) == 1 }
      guard case .preparing = h.session.playbackState else { return XCTFail("Preparing required") }
      XCTAssertFalse(h.session.isPlaying)
      XCTAssertFalse(h.session.canCheck)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      XCTAssertFalse(h.session.canTransitionGuided)
      XCTAssertTrue(h.session.canReplay)  // Same source can cancel.
      h.session.toggleExample()
      h.session.checkRecording()
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.captureDriver.created.count, 1)
      XCTAssertEqual(h.examples.loads, 0)
      XCTAssertEqual(h.word.calls, 0)
      let cancel = Task { await h.session.togglePlayback() }
      await wait { h.session.isAudioCleanupPending }
      XCTAssertTrue(h.captureFilesExist)
      h.driver.release(.prepare)
      await start.value
      await cancel.value
      XCTAssertFalse(h.session.isPlaying)
      XCTAssertEqual(h.driver.count(.play), 0)
      XCTAssertTrue(h.captureFilesExist)
    }

    func testHeldStopKeepsBothTakesAndBorrowUntilAcknowledgementBeforeThirdPermission() async throws
    {
      let h = try await fixture(blocked: [.stop])
      await h.record()
      await h.record(another: true)
      let urls = h.captureDriver.created
      await h.session.togglePlayback(.earlier)
      let replace = Task { await h.session.recordAnotherTry() }
      await wait { h.driver.count(.stop) == 1 }
      XCTAssertEqual(h.capture.permissions, 2)
      XCTAssertEqual(h.captureDriver.created, urls)
      XCTAssertTrue(urls.allSatisfy(h.exists))
      XCTAssertFalse(
        h.files.canRemove(urls[0], owner: try XCTUnwrap(h.captureDriver.owners[urls[0]])))
      XCTAssertFalse(h.session.isPlaying)
      XCTAssertTrue(h.session.audioTransitionPending)
      h.driver.release(.stop)
      await replace.value
      XCTAssertFalse(h.exists(urls[0]))
      XCTAssertTrue(h.exists(urls[1]))
      XCTAssertEqual(h.capture.permissions, 3)
      h.session.stopRecording()
      XCTAssertEqual(h.captureDriver.created.filter(h.exists).count, 2)
    }

    func testExamplePrepareCancellationRevokesLoadingImmediatelyButRetainsExactFile() async throws {
      let h = try await fixture(blocked: [.prepare])
      h.session.toggleExample()
      await wait { h.driver.count(.prepare) == 1 }
      let url = try XCTUnwrap(h.store.ownedURL)
      XCTAssertEqual(h.session.exampleState, .loading)
      XCTAssertTrue(h.session.canPlayExample)
      XCTAssertFalse(h.session.canRecord)
      h.session.toggleExample()
      XCTAssertEqual(h.session.exampleState, .idle)
      XCTAssertTrue(h.exists(url))
      XCTAssertTrue(h.session.audioTransitionPending)
      h.driver.release(.prepare)
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertNil(h.store.ownedURL)
      XCTAssertFalse(h.exists(url))
      XCTAssertEqual(h.driver.count(.play), 0)
    }

    func testLifecycleOwnsCleanupAfterViewLosesItsSession() async throws {
      var h: FeedbackOwnershipHarness? = try FeedbackOwnershipHarness(
        blocked: [.stop], prepareSucceeds: true, cleanupFailures: 0)
      let directory = try XCTUnwrap(h?.directory)
      let driver = try XCTUnwrap(h?.driver)
      let gate = try XCTUnwrap(h?.gate)
      let files = try XCTUnwrap(h?.files)
      let writer = try XCTUnwrap(h?.writer)
      ownDetachedCleanup(directory: directory, driver: driver, gate: gate, files: files)
      defer { driver.releaseAll() }
      await h?.record()
      await h?.session.togglePlayback()
      let url = try XCTUnwrap(h?.captureDriver.created.first)
      weak var session = h?.session
      weak var capture = h?.capture
      weak var store = h?.store
      weak var player = h?.player
      h?.session.appDidEnterBackground()
      h = nil
      await wait { driver.count(.stop) == 1 }
      XCTAssertNotNil(session)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      driver.release(.stop)
      await wait { session == nil && gate.currentLease == nil && files.protectedURLs.isEmpty }
      XCTAssertNil(capture)
      XCTAssertNil(store)
      XCTAssertNil(player)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertTrue(writer.entries.isEmpty)
    }

    func testDuplicateCloseDuringPermissionWaitsForSettlementWithoutStartingCapture() async throws {
      let h = try await fixture()
      h.capture.delayedPermission = true
      let start = Task { await h.session.startRecording() }
      await wait { h.capture.pendingPermission != nil }
      h.session.appDidBecomeInactive()
      XCTAssertEqual(h.session.phase, .requestingPermission)
      let first = h.session.end()
      let second = h.session.end()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertNotEqual(h.session.phase, .ended)
      h.capture.pendingPermission?.resume(returning: true)
      h.capture.pendingPermission = nil
      await start.value
      let firstResult = await first.value
      let secondResult = await second.value
      XCTAssertTrue(firstResult)
      XCTAssertTrue(secondResult)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      XCTAssertEqual(h.session.attemptsStarted, 1)
      XCTAssertEqual(h.session.attemptsFinished, 1)
      XCTAssertEqual(h.session.phase, .ended)
    }

    func testDifferentPlayingSourceRequiresExplicitStopAndRetap() async throws {
      let h = try await fixture()
      await h.record()
      await h.record(another: true)
      await h.session.togglePlayback(.earlier)
      await h.session.togglePlayback(.latest)
      h.session.toggleExample()
      XCTAssertEqual(h.driver.count(.play), 1)
      XCTAssertEqual(h.session.playingReplaySource, .earlier)
      await h.session.togglePlayback(.earlier)
      await h.session.togglePlayback(.latest)
      XCTAssertEqual(h.driver.count(.play), 2)
      XCTAssertEqual(h.session.playingReplaySource, .latest)
    }

    func testStartupFailureDoesNotPublishPlayingAndBlockedStartupRequiresExplicitRetry()
      async throws
    {
      for failsCleanup in [false, true] {
        let h = try await fixture(prepareSucceeds: false, cleanupFailures: failsCleanup ? 1 : 0)
        await h.record()
        var played = false
        let subscription = h.session.$isPlaying.sink { if $0 { played = true } }
        await h.session.togglePlayback()
        subscription.cancel()
        XCTAssertFalse(played)
        XCTAssertTrue(h.session.playbackFailed)
        XCTAssertEqual(h.driver.count(.play), 0)
        XCTAssertTrue(h.captureFilesExist)
        XCTAssertEqual(h.session.playbackCleanupBlocked, failsCleanup)
        if failsCleanup {
          XCTAssertFalse(h.session.canCheck)
          XCTAssertNotNil(h.gate.currentLease)
          let recovered = await h.session.retryAudioCleanup().value
          XCTAssertTrue(recovered)
          XCTAssertNil(h.gate.currentLease)
          XCTAssertTrue(h.session.canCheck)
        }
      }
    }

    func testOriginalNegativeStaysNegativeAndRetryClearsExactActiveIDForFreshPlayback() async throws
    {
      let h = try await fixture(cleanupFailures: 1)
      await h.record()
      await h.session.togglePlayback()
      guard case .playing(let operation) = h.player.state else {
        return XCTFail("Playing required")
      }
      let original = try XCTUnwrap(h.player.requestStop(id: operation.id))
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      _ = await h.session.retake()?.value
      XCTAssertTrue(h.captureFilesExist)
      XCTAssertTrue(h.session.playbackCleanupBlocked)
      let recovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertFalse(h.captureFilesExist)
      await h.record()
      await h.session.togglePlayback()
      XCTAssertTrue(h.session.isPlaying)
      XCTAssertEqual(h.driver.count(.play), 2)
    }

    func testNaturalExampleCompletionWaitsForReleaseAndStaleCallbackCannotRestoreState()
      async throws
    {
      let h = try await fixture(blocked: [.stop])
      h.session.toggleExample()
      await wait { h.session.exampleState == .playing }
      let url = try XCTUnwrap(h.store.ownedURL)
      guard case .playing(let operation) = h.player.state else {
        return XCTFail("Playing required")
      }
      h.driver.finish(true, operationID: operation.id)
      await wait { h.driver.count(.stop) == 1 && h.session.exampleState != .playing }
      XCTAssertTrue(h.exists(url))
      XCTAssertEqual(h.store.removals, [])
      XCTAssertNotEqual(h.session.exampleState, .playing)
      h.driver.release(.stop)
      await wait { h.store.ownedURL == nil }
      XCTAssertFalse(h.exists(url))
      h.driver.finish(false, operationID: operation.id)
      XCTAssertEqual(h.session.exampleState, .idle)
      XCTAssertFalse(h.session.playbackFailed)
    }

    func testCancelledStaleExampleLoadNeverWritesOrStartsPlayback() async throws {
      let h = try await fixture()
      h.examples.delayed = true
      h.session.toggleExample()
      await wait { h.examples.pending != nil }
      h.session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
      XCTAssertEqual(h.session.exampleState, .idle)
      _ = await h.session.awaitPendingAudioCleanup()
      h.examples.release()
      await wait { h.examples.returned }
      XCTAssertNil(h.store.ownedURL)
      XCTAssertEqual(h.driver.count(.prepare), 0)
      XCTAssertFalse(h.session.isPlaying)
    }

    func testDuplicateCloseJoinsHeldStopAndCannotNavigateBeforeRelease() async throws {
      let h = try await fixture(blocked: [.stop])
      await h.record()
      await h.session.togglePlayback()
      let first = h.session.end()
      let second = h.session.end()
      await wait { h.driver.count(.stop) == 1 }
      XCTAssertNotEqual(h.session.phase, .ended)
      XCTAssertTrue(h.session.closeRequested)
      XCTAssertTrue(h.captureFilesExist)
      h.driver.release(.stop)
      let firstResult = await first.value
      let secondResult = await second.value
      XCTAssertTrue(firstResult)
      XCTAssertTrue(secondResult)
      XCTAssertEqual(h.driver.count(.stop), 1)
      XCTAssertEqual(h.session.phase, .ended)
      XCTAssertFalse(h.captureFilesExist)
    }

    func testFailedCloseResumesOnlyAfterExplicitRetryAndSetupSupersedesHeldClose() async throws {
      let failed = try await fixture(cleanupFailures: 1)
      await failed.record()
      await failed.session.togglePlayback()
      let closed = await failed.session.end().value
      XCTAssertFalse(closed)
      XCTAssertNotEqual(failed.session.phase, .ended)
      XCTAssertTrue(failed.captureFilesExist)
      let recovered = await failed.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertEqual(failed.session.phase, .ended)
      let superseded = try await fixture(blocked: [.stop])
      await superseded.record()
      await superseded.session.togglePlayback()
      let held = superseded.session.end()
      await wait { superseded.driver.count(.stop) == 1 }
      superseded.session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
      superseded.driver.release(.stop)
      let stale = await held.value
      XCTAssertFalse(stale)
      _ = await superseded.session.awaitPendingAudioCleanup()
      XCTAssertFalse(superseded.session.closeRequested)
      XCTAssertNotEqual(superseded.session.phase, .ended)
      XCTAssertTrue(superseded.session.canRecord)
    }

    func testFinishDuringHeldStopCancelledByLifecycleOrCloseNeverWritesHistory() async throws {
      for close in [false, true] {
        let h = try await fixture(blocked: [.stop])
        await h.record()
        await h.session.togglePlayback()
        let finish = Task { await h.session.finishPractice() }
        await wait { h.driver.count(.stop) == 1 }
        XCTAssertTrue(h.writer.entries.isEmpty)
        XCTAssertTrue(h.captureFilesExist)
        let closeTask = close ? h.session.end() : nil
        if !close { h.session.appDidEnterBackground() }
        h.driver.release(.stop)
        await finish.value
        _ = await closeTask?.value
        _ = await h.session.awaitPendingAudioCleanup()
        XCTAssertTrue(h.writer.entries.isEmpty)
        XCTAssertNil(h.session.practiceCompletion)
        XCTAssertFalse(h.session.isFinalizingPractice)
      }
    }

    func testFailedNextIsNotReplayedAfterRecoveryAndLateProcessorResultCannotResurrectVisit()
      async throws
    {
      let h = try await fixture(cleanupFailures: 1)
      await h.record()
      let prompt = h.session.selectedPrompt
      await h.session.togglePlayback()
      await h.session.advance()
      XCTAssertEqual(h.session.selectedPrompt, prompt)
      let recovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertEqual(h.session.selectedPrompt, prompt)
      await h.record()
      h.session.checkRecording()
      await wait { h.word.pending }
      let close = h.session.end()
      h.word.resolve(try h.feedback())
      _ = await close.value
      await wait { h.word.returned }
      XCTAssertEqual(h.session.phase, .ended)
      XCTAssertNil(h.session.recognizerWordGuess)
      XCTAssertTrue(h.writer.entries.isEmpty)
    }

    func testExampleDeletionFailureAfterReleasedHardwareRetainsURLAndFailedFinishCannotSave()
      async throws
    {
      let h = try await fixture()
      await h.record()
      h.session.toggleExample()
      await wait { h.session.exampleState == .playing }
      let url = try XCTUnwrap(h.store.ownedURL)
      h.store.failRemove = true
      await h.session.finishPractice()
      XCTAssertNil(h.gate.currentLease)
      XCTAssertEqual(h.player.state, .idle)
      XCTAssertEqual(h.store.ownedURL, url)
      XCTAssertTrue(h.exists(url))
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertTrue(h.session.exampleCleanupBlocked)
      XCTAssertTrue(h.writer.entries.isEmpty)
      h.store.failRemove = false
      let recovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertNil(h.store.ownedURL)
      await h.session.finishPractice()  // Failed Finish requires a new eligible visit.
      XCTAssertTrue(h.writer.entries.isEmpty)
    }

    func testPublicOnlyCleanupRetryRestoresReviewAndPreservesEveryAdmittedPrivateTake()
      async throws
    {
      for clipCount in [1, 2] {
        let h = try await fixture()
        await h.record()
        if clipCount == 2 { await h.record(another: true) }
        let earlier = h.session.earlierReplay
        let latest = h.session.latestReplay
        let summary = h.session.summary
        let attempts = h.session.attemptsStarted
        h.session.toggleExample()
        await wait { h.session.exampleState == .playing }
        let publicURL = try XCTUnwrap(h.store.ownedURL)
        h.store.failRemove = true
        h.session.toggleExample()
        _ = await h.session.awaitPendingAudioCleanup()
        XCTAssertTrue(h.session.exampleCleanupBlocked)
        XCTAssertEqual(h.store.ownedURL, publicURL)
        XCTAssertEqual(h.session.phase, .review)
        XCTAssertEqual(h.captureDriver.created.filter(h.exists).count, clipCount)
        XCTAssertTrue(h.removal.calls.isEmpty)
        XCTAssertFalse(h.session.canReplay)
        h.store.failRemove = false
        let recovered = await h.session.retryExampleCleanup().value
        XCTAssertTrue(recovered)
        XCTAssertNil(h.store.ownedURL)
        XCTAssertFalse(h.exists(publicURL))
        XCTAssertEqual(h.session.phase, .review)
        XCTAssertEqual(h.session.soundPhase, .review)
        XCTAssertEqual(h.session.earlierReplay, earlier)
        XCTAssertEqual(h.session.latestReplay, latest)
        XCTAssertEqual(h.session.summary, summary)
        XCTAssertEqual(h.session.attemptsStarted, attempts)
        XCTAssertEqual(h.session.checksClaimed, 0)
        XCTAssertEqual(h.word.calls, 0)
        XCTAssertTrue(h.writer.entries.isEmpty)
        XCTAssertEqual(h.captureDriver.created.filter(h.exists).count, clipCount)
        XCTAssertTrue(h.removal.calls.isEmpty)
        XCTAssertTrue(h.session.canReplay)
        XCTAssertTrue(h.session.canCheck)
        await h.session.togglePlayback()
        XCTAssertTrue(h.session.isPlaying)
        XCTAssertEqual(h.session.phase, .review)
        XCTAssertEqual(h.captureDriver.created.filter(h.exists).count, clipCount)
        await h.session.togglePlayback()
        XCTAssertNil(h.gate.currentLease)
      }
    }

    func testProcessFileOwnerRetryAlreadyDeletesPendingTakeWithoutSessionRediscard() async throws {
      let h = try await fixture()
      await h.record()
      let url = h.captureDriver.created[0]
      h.removal.failURLs.insert(url)
      _ = await h.session.retake()?.value
      let owner = try XCTUnwrap(h.session.captureCleanupState.fileBlockedOwnerIDs.first)
      h.removal.failURLs = []
      XCTAssertTrue(h.files.retryCleanup(owner: owner))
      XCTAssertFalse(h.exists(url))
      XCTAssertNil(h.session.latestReplay)
      XCTAssertEqual(h.removal.calls.filter { $0 == url }.count, 2)
      let recovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertEqual(h.removal.calls.filter { $0 == url }.count, 2)
      XCTAssertTrue(h.session.canRecord)
    }

    func testPartialCaptureFileRecoveryCommitsEachSuccessBeforeAnotherOwnerFails() async throws {
      let h = try await fixture()
      await h.record()
      await h.record(another: true)
      let urls = h.captureDriver.created
      h.removal.failURLs = Set(urls)
      _ = await h.session.retake()?.value
      XCTAssertEqual(h.session.captureCleanupState.fileBlockedOwnerIDs.count, 2)
      XCTAssertTrue(urls.allSatisfy(h.exists))
      h.removal.failURLs = []
      h.removal.successBudget = 1
      let partial = await h.session.retryAudioCleanup().value
      XCTAssertFalse(partial)
      XCTAssertEqual(urls.filter(h.exists).count, 1)
      XCTAssertEqual(h.session.captureCleanupState.fileBlockedOwnerIDs.count, 1)
      XCTAssertNil(h.session.earlierReplay)
      let removed = try XCTUnwrap(urls.first { !h.exists($0) })
      h.removal.successBudget = nil
      let released = await h.session.retryAudioCleanup().value
      XCTAssertTrue(released)
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertNil(h.session.latestReplay)
      XCTAssertEqual(h.removal.calls.filter { $0 == removed }.count, 2)
    }

    func testCaptureRecoveryReleasesExactHardwareThenFilesWithoutRediscardingRecoveredTake()
      async throws
    {
      let h = try await fixture()
      await h.record()
      let first = h.captureDriver.created[0]
      h.removal.failURLs.insert(first)
      _ = await h.session.retake()?.value
      XCTAssertEqual(h.session.captureCleanupState.fileBlockedOwnerIDs.count, 1)
      XCTAssertNil(h.session.captureCleanupState.hardwareBlockedOperationID)
      h.removal.failURLs = []
      let fileRecovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(fileRecovered)
      // failure + exact owner retry
      XCTAssertEqual(h.removal.calls.filter { $0 == first }.count, 2)
      await h.record()
      await h.session.recordAnotherTry()
      h.captureDriver.deactivateFailures = 1
      h.removal.failURLs.insert(h.captureDriver.created.last!)
      h.session.stopRecording()
      XCTAssertNotNil(h.session.captureCleanupState.hardwareBlockedOperationID)
      XCTAssertTrue(h.captureFilesExist)
      let hardwareRecovered = await h.session.retryAudioCleanup().value
      XCTAssertFalse(hardwareRecovered)
      XCTAssertNil(h.session.captureCleanupState.hardwareBlockedOperationID)
      XCTAssertEqual(h.session.captureCleanupState.fileBlockedOwnerIDs.count, 1)
      XCTAssertFalse(h.session.canRecord)
      h.removal.failURLs = []
      let fullyRecovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(fullyRecovered)
      // The failed replacement's own pending file is removed; the prior admitted take survives.
      XCTAssertTrue(h.captureFilesExist)
      XCTAssertEqual(h.captureDriver.created.filter(h.exists).count, 1)
      XCTAssertTrue(h.session.canRecordAnotherTry)
      XCTAssertFalse(h.session.canRecord)
    }
    func testStartupScanFailureDisablesRecordWithoutInventingCleanupOrTrappingClose() async throws {
      let h = try await fixture(startupScanFails: true)
      await h.session.startRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      await wait { h.session.phase == .failed(.invalidRecording) }
      XCTAssertTrue(h.session.recordingUnavailable)
      XCTAssertNotNil(h.session.audioCleanupMessage)
      XCTAssertFalse(h.session.canRecord)
      XCTAssertFalse(h.session.canRetryAudioCleanup)
      XCTAssertFalse(h.session.hasLocalMediaCleanupIssue)
      XCTAssertEqual(h.capture.cleanupState, .idle)
      XCTAssertNil(h.gate.currentLease)
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      await h.session.startRecording()
      XCTAssertEqual(h.capture.permissions, 1)
      let closed = await h.session.end().value
      XCTAssertTrue(closed)
      XCTAssertEqual(h.session.phase, .ended)
    }

    func testNegativeCloseRegistersEveryProducerAndSurvivesLossOfAllViewReferences() async throws {
      for example in [false, true] {
        var h: FeedbackOwnershipHarness? = try FeedbackOwnershipHarness(
          blocked: [], prepareSucceeds: true, cleanupFailures: 1)
        let directory = try XCTUnwrap(h?.directory)
        let files = try XCTUnwrap(h?.files)
        let gate = try XCTUnwrap(h?.gate)
        let driver = try XCTUnwrap(h?.driver)
        ownDetachedCleanup(directory: directory, driver: driver, gate: gate, files: files)
        defer { driver.releaseAll() }
        await h?.record()
        if example {
          h?.session.toggleExample()
          await wait { h?.session.exampleState == .playing }
        } else {
          await h?.session.togglePlayback()
        }
        let url = try XCTUnwrap(example ? h?.store.ownedURL : h?.captureDriver.created.first)
        guard case .playing(let operation) = h?.player.state else {
          return XCTFail("Confirmed playback required")
        }
        let original = try XCTUnwrap(h?.player.requestStop(id: operation.id))
        let negative = await original.value()
        let closed = await h?.session.end().value
        XCTAssertEqual(closed, false)
        XCTAssertEqual(negative.result, .cleanupUnconfirmed)
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        XCTAssertEqual(files.pendingCleanupOwners.count, 1)
        weak var session = h?.session
        weak var capture = h?.capture
        weak var store = h?.store
        weak var player = h?.player
        h = nil
        await wait { session == nil }
        XCTAssertNil(capture)
        XCTAssertNil(player)
        if example { XCTAssertNotNil(store) } else { XCTAssertNil(store) }
        let retry = try XCTUnwrap(gate.retryPlaybackCleanup())
        let receipt = await retry.value()
        XCTAssertEqual(receipt.operation.id, operation.id)
        XCTAssertEqual(receipt.result, .released)
        XCTAssertEqual(original.receipt, negative)
        for owner in files.pendingCleanupOwners { XCTAssertTrue(files.retryCleanup(owner: owner)) }
        XCTAssertTrue(files.protectedURLs.isEmpty)
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
        await wait { store == nil }
      }
    }

    func testEarlierSynchronousCaptureSubscriberRecoveryKeepsExactRemovalReceipt() async throws {
      var observation: AnyCancellable?
      var recovered: CaptureCleanupReceipt?
      let h = try await fixture(beforeSession: { capture, removal in
        observation = capture.cleanupStatePublisher.sink { state in
          MainActor.assertIsolated()
          guard recovered == nil, let owner = state.fileBlockedOwnerIDs.first else { return }
          removal.failURLs = []
          recovered = capture.retryCleanup(operationID: owner)
        }
      })
      defer { observation?.cancel() }
      await h.record()
      let url = h.captureDriver.created[0]
      let owner = try XCTUnwrap(h.captureDriver.owners[url])
      h.removal.failURLs.insert(url)
      let cleared = await h.session.retake()?.value
      XCTAssertEqual(recovered?.operationID, owner)
      XCTAssertEqual(recovered?.result, .released)
      XCTAssertEqual(h.capture.completedFileCleanup(operationID: owner), recovered)
      XCTAssertEqual(cleared, true)
      XCTAssertNil(h.session.latestReplay)
      XCTAssertTrue(h.session.canRecord)
      XCTAssertFalse(h.exists(url))
      XCTAssertEqual(h.removal.calls.filter { $0 == url }.count, 2)
      _ = await h.session.retake()?.value
      XCTAssertEqual(h.removal.calls.filter { $0 == url }.count, 2)
    }

    func testExternalPlaybackRetryPositiveReceiptIsRequiredAndOriginalNegativeIsImmutable()
      async throws
    {
      let h = try await fixture(cleanupFailures: 1)
      await h.record()
      await h.session.togglePlayback()
      guard case .playing(let operation) = h.player.state else {
        return XCTFail("Playing required")
      }
      let original = try XCTUnwrap(h.player.requestStop(id: operation.id))
      let negative = await original.value()
      _ = await h.session.retake()?.value
      let retry = try XCTUnwrap(h.gate.retryPlaybackCleanup())
      let positive = await retry.value()
      XCTAssertEqual(positive.operation.id, operation.id)
      XCTAssertEqual(positive.result, .released)
      XCTAssertNil(h.player.retryCleanup(id: operation.id))
      XCTAssertEqual(h.player.completedCleanupRetry(id: operation.id), positive)
      XCTAssertNil(h.player.completedCleanupRetry(id: UUID()))
      let recovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertNil(h.gate.currentLease)
      XCTAssertTrue(h.session.canRecord)
      await h.record()
      await h.session.togglePlayback()
      XCTAssertTrue(h.session.isPlaying)
    }

    func testCloseDuringHeldPlaybackOnlyRetryJoinsLatestSettlement() async throws {
      let h = try await fixture(cleanupFailures: 1)
      await h.record()
      await h.session.togglePlayback()
      await h.session.togglePlayback()
      XCTAssertTrue(h.session.playbackCleanupBlocked)
      XCTAssertTrue(h.captureFilesExist)
      h.driver.hold(.deactivate)
      defer { h.driver.releaseAll() }
      let retry = h.session.retryAudioCleanup()
      await wait { h.driver.count(.deactivate) == 2 }
      let close = h.session.end()
      let duplicate = h.session.end()
      XCTAssertNotEqual(h.session.phase, .ended)
      XCTAssertTrue(h.captureFilesExist)
      h.driver.release(.deactivate)
      let recovered = await retry.value
      let closed = await close.value
      let duplicateClosed = await duplicate.value
      XCTAssertTrue(recovered)
      XCTAssertTrue(closed)
      XCTAssertTrue(duplicateClosed)
      XCTAssertEqual(h.session.phase, .ended)
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      XCTAssertNil(h.gate.currentLease)
    }

    func testOldOperationCallbackCannotCompleteNewConfirmedPlayback() async throws {
      let h = try await fixture()
      await h.record()
      await h.session.togglePlayback()
      guard case .playing(let first) = h.player.state else { return XCTFail("First play required") }
      await h.session.togglePlayback()
      await h.session.togglePlayback()
      guard case .playing(let second) = h.player.state else {
        return XCTFail("Second play required")
      }
      XCTAssertNotEqual(first.id, second.id)
      h.driver.finish(true, operationID: first.id)
      h.driver.finish(false, operationID: second.id)
      await wait { h.player.state == .idle && !h.session.isPlaying }
      XCTAssertTrue(h.session.playbackFailed)
      XCTAssertEqual(h.session.failedReplaySource, .latest)
      XCTAssertEqual(h.driver.count(.play), 2)
      XCTAssertTrue(h.captureFilesExist)
      XCTAssertNil(h.gate.currentLease)
    }

    private func boundedSettlement(_ predicate: @escaping @MainActor () -> Bool) async {
      if predicate() { return }
      let settled = expectation(description: "exact controlled owner settlement")
      let observer = Task { @MainActor in
        while !Task.isCancelled {
          if predicate() {
            settled.fulfill()
            return
          }
          await Task.yield()
        }
      }
      defer { observer.cancel() }
      let result = await XCTWaiter.fulfillment(of: [settled], timeout: 3)
      XCTAssertEqual(result, .completed)
    }

    func testFullCleanupAfterCaptureHardwareFailureSurvivesLossOfEveryProducerReference()
      async throws
    {
      for earlierFileFails in [false, true] {
        var h: FeedbackOwnershipHarness? = try FeedbackOwnershipHarness(
          blocked: [], prepareSucceeds: true, cleanupFailures: 0)
        let directory = try XCTUnwrap(h?.directory)
        let files = try XCTUnwrap(h?.files)
        let gate = try XCTUnwrap(h?.gate)
        let playbackDriver = try XCTUnwrap(h?.driver)
        let removal = try XCTUnwrap(h?.removal)
        ownDetachedCleanup(
          directory: directory, driver: playbackDriver, gate: gate, files: files,
          reset: { removal.failURLs = [] })
        await h?.record()
        let earlier = try XCTUnwrap(h?.captureDriver.created.first)
        let earlierOwner = try XCTUnwrap(h?.captureDriver.owners[earlier])
        await h?.session.recordAnotherTry()
        let active = try XCTUnwrap(h?.captureDriver.created.last)
        let operation = try XCTUnwrap(gate.currentLease?.operationID)
        h?.captureDriver.deactivateFailures = 1
        if earlierFileFails { removal.failURLs.insert(earlier) }
        let closed = await h?.session.end().value
        XCTAssertEqual(closed, false)
        XCTAssertEqual(gate.blockedCaptureOperationID, operation)
        XCTAssertEqual(h?.session.captureCleanupState.hardwareBlockedOperationID, operation)
        XCTAssertTrue(removal.calls.isEmpty, "Hardware failure forbids all file deletion")
        XCTAssertTrue(FileManager.default.fileExists(atPath: earlier.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: active.path))
        weak var session = h?.session
        weak var capture = h?.capture
        weak var system = h?.capture.system
        weak var player = h?.player
        weak var store = h?.store
        h = nil
        XCTAssertNotNil(session, "The pending authorized operation owns every retained take")
        XCTAssertNotNil(system)
        let released = gate.retryCaptureCleanup(operationID: operation)
        XCTAssertEqual(released.operationID, operation)
        XCTAssertEqual(released.result, .released)
        XCTAssertNil(gate.currentLease)
        XCTAssertFalse(FileManager.default.fileExists(atPath: active.path))
        await boundedSettlement {
          session == nil && capture == nil && player == nil && store == nil
        }
        XCTAssertEqual(removal.calls.filter { $0 == active }.count, 1)
        XCTAssertEqual(removal.calls.filter { $0 == earlier }.count, 1)
        if earlierFileFails {
          XCTAssertNotNil(system, "The actual producer owns pending file recovery")
          XCTAssertEqual(files.pendingCleanupOwners, [earlierOwner])
          XCTAssertTrue(FileManager.default.fileExists(atPath: earlier.path))
          removal.failURLs = []
          XCTAssertTrue(files.retryCleanup(owner: earlierOwner))
          XCTAssertEqual(removal.calls.filter { $0 == earlier }.count, 2)
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: earlier.path))
        XCTAssertTrue(files.protectedURLs.isEmpty)
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
        await boundedSettlement { system == nil }
      }
    }

    func testSynchronousCloseDuringPublicOnlyReviewRecoveryDrainsUpgradedPrivateRemovalIntent()
      async throws
    {
      for clipCount in [1, 2] {
        let h = try await fixture()
        await h.record()
        if clipCount == 2 { await h.record(another: true) }
        let privateURLs = h.captureDriver.created
        h.session.toggleExample()
        await boundedSettlement { h.session.exampleState == .playing }
        let publicURL = try XCTUnwrap(h.store.ownedURL)
        h.store.failRemove = true
        h.session.toggleExample()
        _ = await h.session.awaitPendingAudioCleanup()
        XCTAssertTrue(h.session.exampleCleanupBlocked)
        XCTAssertTrue(privateURLs.allSatisfy(h.exists))
        XCTAssertTrue(h.removal.calls.isEmpty)
        h.store.failRemove = false
        var armed = false
        var close: Task<Bool, Never>?
        let observation = h.session.$phase.sink { phase in
          MainActor.assertIsolated()
          guard armed, phase == .review else { return }
          armed = false
          close = h.session.end()
        }
        defer { observation.cancel() }
        armed = true
        let recovered = await h.session.retryAudioCleanup().value
        let joinedClose = await close?.value
        XCTAssertTrue(recovered)
        XCTAssertEqual(joinedClose, true)
        XCTAssertEqual(h.session.phase, .ended)
        XCTAssertEqual(h.session.soundPhase, .ended)
        XCTAssertNil(h.session.earlierReplay)
        XCTAssertNil(h.session.latestReplay)
        XCTAssertFalse(privateURLs.contains(where: h.exists))
        XCTAssertFalse(h.exists(publicURL))
        XCTAssertNil(h.store.ownedURL)
        XCTAssertTrue(h.files.protectedURLs.isEmpty)
        XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
        XCTAssertNil(h.gate.currentLease)
        XCTAssertFalse(h.session.canRetryAudioCleanup)
        XCTAssertEqual(h.captureDriver.created.count, clipCount)
        XCTAssertEqual(h.session.checksClaimed, 0)
        XCTAssertEqual(h.word.calls, 0)
        XCTAssertTrue(h.writer.entries.isEmpty)
        for url in privateURLs { XCTAssertEqual(h.removal.calls.filter { $0 == url }.count, 1) }
      }
    }

    func testSynchronousEarlierCaptureRecoveryDoesNotInventStartupFailureAfterCancelOrFailedStop()
      async throws
    {
      for failedStop in [false, true] {
        for hardwareFailure in [false, true] {
          var owner: UUID?
          var positive: CaptureCleanupReceipt?
          var observation: AnyCancellable?
          let h = try await fixture(beforeSession: { capture, removal in
            observation = capture.cleanupStatePublisher.sink { state in
              MainActor.assertIsolated()
              guard positive == nil, let owner,
                state.hardwareBlockedOperationID == owner
                  || state.fileBlockedOwnerIDs.contains(owner)
              else { return }
              removal.failURLs = []
              positive = capture.retryCleanup(operationID: owner)
            }
          })
          defer { observation?.cancel() }
          await h.session.startRecording()
          owner = try XCTUnwrap(h.gate.currentLease?.operationID)
          let url = try XCTUnwrap(h.captureDriver.created.last)
          h.captureDriver.deactivateFailures = hardwareFailure ? 1 : 0
          if !hardwareFailure { h.removal.failURLs.insert(url) }
          h.removal.summaryFails = failedStop && !hardwareFailure
          let originalError: AudioCaptureError =
            hardwareFailure
            ? .hardwareCleanupUnconfirmed : .couldNotDeleteTemporaryRecording
          if failedStop {
            h.session.stopRecording()
            _ = await h.session.awaitPendingAudioCleanup()
            await boundedSettlement { h.session.phase == .failed(.invalidRecording) }
            XCTAssertEqual(h.capture.lastStopError, originalError)
            XCTAssertTrue(h.session.canRecord)
          } else {
            let ended = await h.session.end().value
            XCTAssertTrue(ended)
            XCTAssertEqual(h.capture.lastCancelError, originalError)
            XCTAssertEqual(h.session.phase, .ended)
          }
          XCTAssertEqual(positive?.operationID, owner)
          XCTAssertEqual(positive?.result, .released)
          XCTAssertEqual(
            h.capture.completedFileCleanup(operationID: try XCTUnwrap(owner)), positive)
          XCTAssertFalse(h.session.recordingUnavailable)
          XCTAssertFalse(h.session.hasLocalMediaCleanupIssue)
          XCTAssertFalse(h.session.canRetryAudioCleanup)
          XCTAssertNil(h.gate.currentLease)
          XCTAssertTrue(h.files.protectedURLs.isEmpty)
          XCTAssertFalse(h.exists(url))
          XCTAssertEqual(h.captureDriver.created.count, 1)
          XCTAssertEqual(h.session.checksClaimed, 0)
          let closed = await h.session.end().value
          XCTAssertTrue(closed)
        }
      }
    }

    func testFailedAdvanceCannotResumeAfterExternalGateRetryAndRequiresExplicitRetap() async throws
    {
      let h = try await fixture(cleanupFailures: 1)
      await h.record()
      let prompt = h.session.selectedPrompt
      await h.session.togglePlayback()
      guard case .playing(let operation) = h.player.state else {
        return XCTFail("Playing required")
      }
      var gateRecovery: Task<PracticePlaybackCleanupReceipt, Never>?
      let observation = h.player.statePublisher.sink { state in
        MainActor.assertIsolated()
        guard case .cleanupBlocked(let failed) = state, failed.id == operation.id,
          gateRecovery == nil, let retry = h.gate.retryPlaybackCleanup()
        else { return }
        gateRecovery = Task { await retry.value() }
      }
      defer { observation.cancel() }
      await h.session.advance()
      let positive = await gateRecovery?.value
      XCTAssertEqual(positive?.operation.id, operation.id)
      XCTAssertEqual(positive?.result, .released)
      XCTAssertEqual(h.session.selectedPrompt, prompt)
      let original = try XCTUnwrap(h.player.requestStop(id: operation.id))
      let negative = try XCTUnwrap(original.receipt)
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      let recovered = await h.session.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertEqual(
        h.session.selectedPrompt, prompt, "A failed Advance requires a new explicit tap")
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertNil(h.gate.currentLease)
      XCTAssertTrue(h.writer.entries.isEmpty)
      XCTAssertEqual(h.captureDriver.created.count, 1)
      await h.session.advance()
      XCTAssertNotEqual(h.session.selectedPrompt, prompt)
      XCTAssertEqual(original.receipt, negative)
    }

    func testSynchronousCloseFlagDuplicatesJoinBeforeLatePermissionCanStartAnyRecorder()
      async throws
    {
      let h = try await fixture()
      h.capture.delayedPermission = true
      let captureRequest = Task { await h.session.startRecording() }
      await boundedSettlement { h.capture.pendingPermission != nil }
      var notifications = 0
      var joins: [Task<Bool, Never>] = []
      let observation = h.session.$closeRequested.sink { closing in
        MainActor.assertIsolated()
        guard closing, notifications < 3 else { return }
        // Bounded before reentry: the old implementation fails without overflowing the stack.
        notifications += 1
        for _ in 0..<3 { joins.append(h.session.end()) }
      }
      defer { observation.cancel() }
      let first = h.session.end()
      XCTAssertEqual(notifications, 1)
      XCTAssertEqual(joins.count, 3)
      XCTAssertTrue(h.session.closeRequested)
      XCTAssertTrue(h.session.isPermissionPending)
      XCTAssertFalse(h.session.canRecord)
      XCTAssertNotEqual(h.session.phase, .ended)
      XCTAssertEqual(h.capture.permissions, 1)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      h.capture.pendingPermission?.resume(returning: true)
      h.capture.pendingPermission = nil
      await captureRequest.value
      let firstResult = await first.value
      XCTAssertTrue(firstResult)
      for join in joins {
        let joinedResult = await join.value
        XCTAssertTrue(joinedResult)
      }
      XCTAssertEqual(h.session.phase, .ended)
      XCTAssertEqual(h.session.soundPhase, .ended)
      XCTAssertFalse(h.session.isPermissionPending)
      XCTAssertEqual(h.capture.permissions, 1)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      XCTAssertTrue(h.removal.calls.isEmpty)
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      XCTAssertNil(h.gate.currentLease)
      await h.session.startRecording()
      XCTAssertEqual(h.capture.permissions, 1)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
    }

    func testSynchronousPhaseAndControlCloseDuplicatesJoinHeldActualCleanupAndOriginalReceipt()
      async throws
    {
      for cleanupFailures in [0, 1] {
        let h = try await fixture(blocked: [.stop], cleanupFailures: cleanupFailures)
        defer { h.driver.release(.stop) }
        await h.record()
        let url = try XCTUnwrap(h.captureDriver.created.first)
        let owner = try XCTUnwrap(h.captureDriver.owners[url])
        await h.session.togglePlayback()
        guard case .playing(let operation) = h.player.state else {
          return XCTFail("Playing required")
        }
        let original = try XCTUnwrap(h.player.requestStop(id: operation.id))
        var phaseEntries = 0
        var controlEntries = 0
        var joins: [Task<Bool, Never>] = []
        let phaseObservation = h.session.$phase.sink { phase in
          MainActor.assertIsolated()
          guard phase == .ready, phaseEntries < 2 else { return }
          phaseEntries += 1
          joins.append(h.session.end())
        }
        let controlObservation = h.session.$isAudioCleanupPending.sink { pending in
          MainActor.assertIsolated()
          guard pending, controlEntries < 2 else { return }
          controlEntries += 1
          joins.append(h.session.end())
        }
        defer {
          phaseObservation.cancel()
          controlObservation.cancel()
        }
        let first = h.session.end()
        await boundedSettlement { h.driver.count(.stop) == 1 }
        XCTAssertGreaterThan(phaseEntries, 0)
        XCTAssertGreaterThan(controlEntries, 0)
        XCTAssertGreaterThanOrEqual(joins.count, 2)
        XCTAssertNil(original.receipt)
        XCTAssertTrue(h.player.requestStop(id: operation.id) === original)
        XCTAssertEqual(h.gate.currentLease?.operationID, operation.id)
        XCTAssertFalse(h.files.canRemove(url, owner: owner))
        XCTAssertTrue(h.exists(url))
        XCTAssertTrue(h.removal.calls.isEmpty)
        XCTAssertNotEqual(h.session.phase, .ended)
        h.driver.release(.stop)
        let firstResult = await first.value
        XCTAssertEqual(firstResult, cleanupFailures == 0)
        for join in joins {
          let joinedResult = await join.value
          XCTAssertEqual(joinedResult, firstResult)
        }
        phaseObservation.cancel()
        controlObservation.cancel()
        let originalReceipt = try XCTUnwrap(original.receipt)
        XCTAssertEqual(originalReceipt.operation.id, operation.id)
        XCTAssertEqual(
          originalReceipt.result, cleanupFailures == 0 ? .released : .cleanupUnconfirmed)
        XCTAssertEqual(h.driver.count(.stop), 1)
        XCTAssertEqual(h.captureDriver.created.count, 1)
        XCTAssertEqual(h.capture.permissions, 1)
        if cleanupFailures == 1 {
          XCTAssertNotEqual(h.session.phase, .ended)
          XCTAssertTrue(h.exists(url))
          XCTAssertTrue(h.files.pendingCleanupOwners.contains(owner))
          XCTAssertTrue(h.removal.calls.isEmpty)
          let recovered = await h.session.retryAudioCleanup().value
          XCTAssertTrue(recovered)
          XCTAssertEqual(original.receipt, originalReceipt)
        }
        XCTAssertEqual(h.session.phase, .ended)
        XCTAssertEqual(h.session.soundPhase, .ended)
        XCTAssertFalse(h.exists(url))
        XCTAssertEqual(h.removal.calls, [url])
        XCTAssertEqual(h.capture.completedFileCleanup(operationID: owner)?.result, .released)
        XCTAssertTrue(h.files.protectedURLs.isEmpty)
        XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
        XCTAssertNil(h.gate.currentLease)
        XCTAssertEqual(original.receipt, originalReceipt)
      }
    }

    func testLegacyFileFailureStaysStickyUntilExactOwnerRetry() throws {
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      try capture.start(onFinish: { _ in })
      let recording = try capture.stop()
      let owner = try XCTUnwrap(recording.cleanupOwnerID)
      capture.failDiscard = true
      XCTAssertThrowsError(try capture.discard(recording))
      capture.failDiscard = false
      XCTAssertThrowsError(try capture.discard(recording))
      XCTAssertEqual(capture.discards, 1)
      XCTAssertNil(capture.completedFileCleanup(operationID: owner))
      XCTAssertEqual(capture.retryCleanup(operationID: owner).result, .released)
      XCTAssertEqual(capture.completedFileCleanup(operationID: owner)?.result, .released)
      XCTAssertEqual(capture.discards, 2)
      XCTAssertThrowsError(try capture.discard(recording))
    }
  }

  /// Shared legacy test adapter: still preserves callback arrays for stale-callback assertions,
  /// but admission, state and receipts now come from the real runtime with inert drivers.
  @MainActor
  final class FeedbackPlayer: AcknowledgedPracticeAudioPlaying {
    private let callbacks = FeedbackPlaybackCallbacks()
    private let runtime: SystemAcknowledgedPracticeAudioPlayer
    var starts = 0
    var urls: [URL] = []
    var completions: [@MainActor (Bool) -> Void] = []
    var finish: (@MainActor (Bool) -> Void)? { completions.last }
    var state: PracticePlaybackRuntimeState { runtime.state }
    var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> { runtime.statePublisher }
    init() {
      let callbacks = self.callbacks
      runtime = SystemAcknowledgedPracticeAudioPlayer(
        ownership: AudioHardwareOwnership(), fileOwnership: ProcessAudioFileOwnership(),
        factory: { operation, finished in
          callbacks.install(operation.id) { finished(operation, $0) }
          return FeedbackInertPlaybackDriver()
        })
    }
    func play(
      id: UUID, url: URL,
      onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
    ) async throws {
      try await runtime.play(id: id, url: url, onFinish: onFinish)
      starts += 1
      urls.append(url)
      let callbacks = callbacks
      completions.append { callbacks.finish(id, success: $0) }
    }
    func requestStop(id: UUID) -> PracticePlaybackCleanup? { runtime.requestStop(id: id) }
    func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { runtime.retryCleanup(id: id) }
    func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
      runtime.completedCleanupRetry(id: id)
    }
  }
  private final class FeedbackInertPlaybackDriver: PracticePlaybackDriver {
    func activate() throws {}
    func prepare() throws -> Bool { true }
    func play() throws -> Bool { true }
    func stop() throws {}
    func releasePlaybackResources() throws {}
    func deactivate() throws {}
  }
  private final class FeedbackPlaybackCallbacks: @unchecked Sendable {
    private let lock = NSLock()
    private var callbacks: [UUID: @Sendable (Bool) -> Void] = [:]
    func install(_ id: UUID, callback: @escaping @Sendable (Bool) -> Void) {
      lock.withLock { callbacks[id] = callback }
    }
    func finish(_ id: UUID, success: Bool) {
      let callback = lock.withLock { callbacks[id] }
      callback?(success)
    }
  }

  /// Explicit file ownership for legacy capture mocks. No falsely idle protocol extension.
  @MainActor
  final class FeedbackCaptureFiles {
    private var owners: [URL: UUID] = [:]
    private var completedReceipts: [UUID: CaptureCleanupReceipt] = [:]
    private var retryingOwners: Set<UUID> = []
    func owner(_ url: URL) -> UUID? { owners[url] }
    func completed(_ id: UUID) -> CaptureCleanupReceipt? { completedReceipts[id] }
    private(set) var state = CaptureCleanupState.idle
    private let events = PassthroughSubject<(UInt64, CaptureCleanupState), Never>()
    private var revision: UInt64 = 0
    private var pendingEvents: [(UInt64, CaptureCleanupState)] = []
    private var publishing = false
    var publisher: AnyPublisher<CaptureCleanupState, Never> {
      Deferred { [self] in
        let initialRevision = revision
        let subject = CurrentValueSubject<CaptureCleanupState, Never>(state)
        let observation = events.sink { revision, state in
          if revision > initialRevision { subject.send(state) }
        }
        return subject.removeDuplicates()
          .handleEvents(receiveCancel: { observation.cancel() }).eraseToAnyPublisher()
      }.eraseToAnyPublisher()
    }
    private func publish(_ next: CaptureCleanupState) {
      guard state != next else { return }
      state = next
      revision += 1
      pendingEvents.append((revision, next))
      guard !publishing else { return }
      publishing = true
      defer { publishing = false }
      while !pendingEvents.isEmpty { events.send(pendingEvents.removeFirst()) }
    }
    func retain(_ url: URL) { owners[url] = UUID() }
    func require(_ url: URL) throws {
      guard let owner = owners[url] else { throw AudioCaptureError.recordingNotOwned }
      guard !state.fileBlockedOwnerIDs.contains(owner) || retryingOwners.contains(owner) else {
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
    }
    func failed(_ url: URL) {
      guard let id = owners[url] else { return }
      publish(
        .init(
          hardwareBlockedOperationID: nil,
          fileBlockedOwnerIDs: state.fileBlockedOwnerIDs.union([id])))
    }
    func removed(_ url: URL) {
      guard let id = owners.removeValue(forKey: url) else { return }
      completedReceipts[id] = .init(operationID: id, result: .released)
      publish(
        .init(
          hardwareBlockedOperationID: nil,
          fileBlockedOwnerIDs: state.fileBlockedOwnerIDs.subtracting([id])))
    }
    func retry(_ id: UUID, remove: (URL) throws -> Void) -> CaptureCleanupReceipt {
      guard state.fileBlockedOwnerIDs.contains(id),
        let url = owners.first(where: { $0.value == id })?.key
      else { return .init(operationID: id, result: .refused) }
      retryingOwners.insert(id)
      defer { retryingOwners.remove(id) }
      do {
        try remove(url)
        return completedReceipts[id] ?? .init(operationID: id, result: .refused)
      } catch { return .init(operationID: id, result: .hardwareReleasedFilesRetained) }
    }
  }

  private final class FeedbackOwnershipDriver: PracticePlaybackDriver, @unchecked Sendable {
    enum Stage: Hashable { case prepare, play, stop, releaseResources, deactivate }
    enum Failure: Error { case injected }
    private let condition = NSCondition()
    private var blocked: Set<Stage>
    private var counts: [Stage: Int] = [:]
    private var callbacks: [UUID: @Sendable (Bool) -> Void] = [:]
    private var cleanupFailures: Int
    private let prepareSucceeds: Bool
    init(blocked: Set<Stage>, prepareSucceeds: Bool, cleanupFailures: Int) {
      self.blocked = blocked
      self.prepareSucceeds = prepareSucceeds
      self.cleanupFailures = cleanupFailures
    }
    func bind(_ id: UUID, _ callback: @escaping @Sendable (Bool) -> Void) {
      condition.lock()
      callbacks[id] = callback
      condition.unlock()
    }
    func count(_ stage: Stage) -> Int {
      condition.lock()
      defer { condition.unlock() }
      return counts[stage, default: 0]
    }
    func hold(_ stage: Stage) {
      condition.lock()
      blocked.insert(stage)
      condition.unlock()
    }
    func release(_ stage: Stage) {
      condition.lock()
      blocked.remove(stage)
      condition.broadcast()
      condition.unlock()
    }
    func releaseAll() {
      condition.lock()
      blocked = []
      cleanupFailures = 0
      condition.broadcast()
      condition.unlock()
    }
    private func enter(_ stage: Stage) throws {
      condition.lock()
      defer { condition.unlock() }
      counts[stage, default: 0] += 1
      let deadline = Date().addingTimeInterval(3)
      while blocked.contains(stage) {
        guard condition.wait(until: deadline) || !blocked.contains(stage) else {
          throw Failure.injected
        }
      }
    }
    func finish(_ success: Bool, operationID: UUID) {
      condition.lock()
      let callback = callbacks[operationID]
      condition.unlock()
      callback?(success)
    }
    func activate() throws {}
    func prepare() throws -> Bool {
      try enter(.prepare)
      return prepareSucceeds
    }
    func play() throws -> Bool {
      try enter(.play)
      return true
    }
    func stop() throws { try enter(.stop) }
    func releasePlaybackResources() throws { try enter(.releaseResources) }
    func deactivate() throws {
      try enter(.deactivate)
      condition.lock()
      let fail = cleanupFailures > 0
      if fail { cleanupFailures -= 1 }
      condition.unlock()
      if fail { throw Failure.injected }
    }
  }
  @MainActor
  private final class FeedbackOwnershipCaptureDriver: CaptureHardwareDriver {
    var created: [URL] = []
    var deactivateFailures = 0
    var gate: AudioHardwareOwnership?
    var owners: [URL: UUID] = [:]
    func configureActivate() throws {}
    func createRecorder(
      url: URL, recorderID: UUID,
      onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
    ) throws {
      created.append(url)
      owners[url] = gate?.currentLease?.operationID
      try FeedbackFixture.wav(Array(repeating: Int16(4096 + created.count), count: 3200)).write(
        to: url)
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
  }
  @MainActor
  private final class FeedbackOwnershipCapture: AudioCapturing {
    let system: SystemAudioCapturer
    var permissions = 0
    var delayedPermission = false
    var pendingPermission: CheckedContinuation<Bool, Never>?
    init(_ system: SystemAudioCapturer) { self.system = system }
    var cleanupState: CaptureCleanupState { system.cleanupState }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      system.cleanupStatePublisher
    }
    func requestPermission() async -> Bool {
      permissions += 1
      if delayedPermission { return await withCheckedContinuation { pendingPermission = $0 } }
      return true
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      try system.start(onFinish: onFinish)
    }
    private(set) var lastStopError: AudioCaptureError?
    private(set) var lastCancelError: AudioCaptureError?
    func stop() throws -> CapturedRecording {
      do { return try system.stop() } catch {
        lastStopError = error as? AudioCaptureError
        throw error
      }
    }
    func cancel() throws {
      do { try system.cancel() } catch {
        lastCancelError = error as? AudioCaptureError
        throw error
      }
    }
    func discard(_ recording: CapturedRecording) throws { try system.discard(recording) }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      system.retryCleanup(operationID: operationID)
    }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      system.completedFileCleanup(operationID: operationID)
    }
  }
  @MainActor
  private final class FeedbackOwnershipRemoval {
    var failURLs: Set<URL> = []
    var calls: [URL] = []
    var successBudget: Int?
    var summaryFails = false
    func remove(_ url: URL) throws {
      calls.append(url)
      if let budget = successBudget {
        if budget == 0 { throw AudioCaptureError.couldNotDeleteTemporaryRecording }
        successBudget = budget - 1
      }
      if failURLs.contains(url) { throw AudioCaptureError.couldNotDeleteTemporaryRecording }
      if FileManager.default.fileExists(atPath: url.path) {
        try FileManager.default.removeItem(at: url)
      }
    }
  }
  @MainActor
  private final class FeedbackOwnershipExamples: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    var loads = 0, delayed = false, returned = false
    var pending: CheckedContinuation<Data, Never>?
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated control", licenseId: "Generated fixture",
        licenseURL: URL(string: "https://example.invalid/control")!,
        sourceURL: URL(string: "https://example.invalid/control")!, attribution: "Generated PCM",
        changes: "Test only", speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data {
      loads += 1
      defer { returned = true }
      if delayed { return await withCheckedContinuation { pending = $0 } }
      return bytes
    }
    func release() {
      pending?.resume(returning: bytes)
      pending = nil
    }
  }
  @MainActor
  private final class FeedbackOwnershipExampleStore: ResearchPracticeExampleStoring {
    let directory: URL
    let files: ProcessAudioFileOwnership
    let owner = UUID()
    var ownedURL: URL?, failRemove = false
    var removals: [URL] = []
    init(directory: URL, files: ProcessAudioFileOwnership) {
      self.directory = directory
      self.files = files
    }
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = directory.appendingPathComponent("generated-example-\(UUID().uuidString).wav")
      try data.write(to: url)
      ownedURL = url
      files.retain(url, owner: owner)
      return url
    }
    func remove(_ url: URL) throws {
      removals.append(url)
      guard ownedURL == url else { throw ResearchPracticeExampleError.cleanupFailed }
      do {
        guard !failRemove, files.canRemove(url, owner: owner) else {
          throw ResearchPracticeExampleError.cleanupFailed
        }
        try FileManager.default.removeItem(at: url)
        files.didRemove(url, owner: owner)
        ownedURL = nil
      } catch {
        files.registerCleanupRecovery(owner: owner) { [self] in
          do {
            try remove(url)
            return ownedURL == nil
          } catch { return false }
        }
        throw error
      }
    }
  }
  @MainActor
  private final class FeedbackOwnershipSound: ResearchSoundProcessing {
    func declaration() async throws -> ResearchSoundDeclaration {
      throw RecordingFeedbackError.serviceUnavailable
    }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared { throw RecordingFeedbackError.serviceUnavailable }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      throw RecordingFeedbackError.serviceUnavailable
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws {}
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {}
  }
  @MainActor
  private final class FeedbackOwnershipWriter: ResearchGuidedPracticeParticipationRecording {
    var entries: [UUID] = []
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
      entries.append(sessionID)
    }
  }
  @MainActor
  private final class FeedbackOwnershipHarness {
    let directory: URL
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let driver: FeedbackOwnershipDriver
    let captureDriver = FeedbackOwnershipCaptureDriver()
    let removal = FeedbackOwnershipRemoval()
    let capture: FeedbackOwnershipCapture
    let player: SystemAcknowledgedPracticeAudioPlayer
    let examples = FeedbackOwnershipExamples()
    let store: FeedbackOwnershipExampleStore
    let writer = FeedbackOwnershipWriter()
    let word = FeedbackProcessor()
    let session: ResearchFeedbackSession
    init(
      blocked: Set<FeedbackOwnershipDriver.Stage>, prepareSucceeds: Bool, cleanupFailures: Int,
      startupScanFails: Bool = false,
      beforeSession: ((FeedbackOwnershipCapture, FeedbackOwnershipRemoval) -> Void)? = nil
    )
      throws
    {
      directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "feedback-ownership-\(UUID().uuidString)")
      if !startupScanFails {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      }
      let captureDriver = self.captureDriver
      captureDriver.gate = gate
      let removal = self.removal
      capture = FeedbackOwnershipCapture(
        SystemAudioCapturer(
          recordingStore: TemporaryRecordingStore(directory: directory), fileOwnership: files,
          hardwareOwnership: gate, driverFactory: { captureDriver },
          summaryReader: { _ in
            if removal.summaryFails { throw AudioCaptureError.couldNotReadRecording }
            return .init(duration: 0.2, averagePower: -18)
          },
          removeFile: { try removal.remove($0) }))
      if startupScanFails {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      }
      beforeSession?(capture, removal)
      driver = FeedbackOwnershipDriver(
        blocked: blocked, prepareSucceeds: prepareSucceeds, cleanupFailures: cleanupFailures)
      let driver = self.driver
      player = SystemAcknowledgedPracticeAudioPlayer(ownership: gate, fileOwnership: files) {
        operation, finished in
        driver.bind(operation.id) { finished(operation, $0) }
        return driver
      }
      store = FeedbackOwnershipExampleStore(directory: directory, files: files)
      session = makeControlledFeedbackSession(
        capturer: capture, player: player, processor: word,
        soundProcessor: FeedbackOwnershipSound(),
        exampleLoader: examples, exampleStore: store, participationWriter: writer)
      session.selectedPrompt = ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
      session.practiceContext = .adult
      session.localProcessingEnabled = true
    }
    func exists(_ url: URL) -> Bool { FileManager.default.fileExists(atPath: url.path) }
    var captureFilesExist: Bool { captureDriver.created.contains(where: exists) }
    func record(another: Bool = false) async {
      _ = await session.awaitPendingAudioCleanup()
      if another { await session.recordAnotherTry() } else { await session.startRecording() }
      session.stopRecording()
      XCTAssertEqual(session.phase, .review)
    }
    func feedback() throws -> RecordingFeedback {
      let recording = try XCTUnwrap(word.recordings.last)
      let bytes = try FeedbackPCM.read(recording.url)
      let prompt = try XCTUnwrap(word.prompts.last)
      let attempt = try XCTUnwrap(word.attempts.last)
      let context = try XCTUnwrap(word.contexts.last)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attempt, audio: bytes, prompt: prompt, practiceContext: context)
      return try FeedbackContract.decode(
        FeedbackFixture.json(FeedbackFixture.response(body, audio: bytes)),
        expectedBinding: FeedbackFixture.binding(body, audio: bytes),
        pcm: FeedbackPCM.measure(bytes), targetUnsupported: false)
    }
    func clean() async {
      driver.releaseAll()
      captureDriver.deactivateFailures = 0
      removal.failURLs = []
      removal.successBudget = nil
      removal.summaryFails = false
      store.failRemove = false
      examples.release()
      capture.pendingPermission?.resume(returning: false)
      capture.pendingPermission = nil
      _ = await session.awaitPendingAudioCleanup()
      _ = await session.end().value
      if session.hasLocalMediaCleanupIssue { _ = await session.retryAudioCleanup().value }
      XCTAssertNil(gate.currentLease)
      XCTAssertNil(store.ownedURL)
      if gate.currentLease == nil, store.ownedURL == nil {
        try? FileManager.default.removeItem(at: directory)
      }
    }
  }
#endif
