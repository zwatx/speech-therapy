#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Generated PCM/invented observations test ownership, not audible output or model accuracy.
  @MainActor
  final class ResearchFeedbackTwoTryTests: XCTestCase {
    private var fixtures: [TwoTryHarness] = []
    override func tearDown() async throws {
      for fixture in fixtures { await fixture.remove() }
      fixtures.removeAll()
      try await super.tearDown()
    }
    private func fixture() throws -> TwoTryHarness {
      let value = try TwoTryHarness()
      fixtures.append(value)
      return value
    }
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Expected controlled transition")
    }
    private func first(_ h: TwoTryHarness) async {
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.startRecording()
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.session.phase, .review)
    }
    private func another(_ h: TwoTryHarness) async {
      await h.session.recordAnotherTry()
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.session.phase, .review)
    }
    private func example(_ h: TwoTryHarness) async {
      h.session.toggleExample()
      await wait { h.session.exampleState == .playing && h.player.urls.last == h.store.ownedURL }
    }
    private func word(_ h: TwoTryHarness) async {
      h.session.checkRecording()
      await wait { !h.session.isProcessing }
    }
    private func sound(_ h: TwoTryHarness) async {
      h.session.checkSound()
      await wait { !h.session.isProcessing }
    }

    func testTwoDistinctFilesReplayThroughOnePlayerWithoutChangingLatestEligibility() async throws {
      let h = try fixture()
      await first(h)
      let firstID = h.session.latestReplay?.id
      await another(h)
      XCTAssertEqual(h.capture.files.count, 2)
      XCTAssertEqual(Set(h.capture.urls).count, 2)
      XCTAssertEqual(h.session.earlierReplay?.id, firstID)
      XCTAssertFalse(h.session.earlierReplay?.isCurrentTake ?? true)
      XCTAssertTrue(h.session.latestReplay?.isCurrentTake ?? false)
      let current = h.session.latestReplay
      await h.session.togglePlayback(.earlier)
      let earlierCallback = h.player.completions.last!
      XCTAssertEqual(h.player.urls.last, h.capture.urls[0])
      XCTAssertEqual(h.session.playingReplaySource, .earlier)
      await h.session.togglePlayback(.latest)
      XCTAssertEqual(h.session.playingReplaySource, .earlier)
      // Explicitly stop; the different source did not queue.
      await h.session.togglePlayback(.earlier)
      await h.session.togglePlayback(.latest)
      let latestCallback = h.player.completions.last!
      XCTAssertEqual(h.player.urls.last, h.capture.urls[1])
      earlierCallback(false)
      XCTAssertEqual(h.session.playingReplaySource, .latest)
      XCTAssertFalse(h.session.playbackFailed)
      await h.session.togglePlayback(.latest)
      await example(h)
      let publicCallback = h.player.completions.last!
      latestCallback(false)
      XCTAssertEqual(h.session.exampleState, .playing)
      h.session.toggleExample()  // Stop the active example before replaying a different source.
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.togglePlayback(.earlier)
      publicCallback(false)
      XCTAssertEqual(h.session.playingReplaySource, .earlier)
      XCTAssertNil(h.store.ownedURL)
      XCTAssertEqual(h.capture.files.count, 2)
      XCTAssertEqual(h.session.latestReplay, current)
      XCTAssertTrue(h.session.canCheck)
      XCTAssertTrue(h.session.canCheckSound)
      XCTAssertEqual(h.word.calls.count, 0)
      XCTAssertEqual(h.sound.prepared.count, 0)
      h.player.completions.last?(false)
      await wait { !h.session.isPlaying }
      XCTAssertEqual(h.session.failedReplaySource, .earlier)
      XCTAssertFalse(h.session.isPlaying)
      XCTAssertTrue(h.session.canCheck)
    }

    func testThirdCaptureEvictsOldestBeforePermissionAndNeverAllocatesThirdSlot() async throws {
      let h = try fixture()
      await first(h)
      await another(h)
      let survivor = h.session.latestReplay?.id
      let start = h.capture.operations.count
      await h.session.recordAnotherTry()
      XCTAssertEqual(
        Array(h.capture.operations.dropFirst(start).prefix(3)),
        ["discard:1", "permission", "start:3"])
      XCTAssertFalse(FileManager.default.fileExists(atPath: h.capture.urls[0].path))
      XCTAssertEqual(h.capture.files.count, 2)
      XCTAssertEqual(h.capture.maximumFiles, 2)
      XCTAssertEqual(h.session.latestReplay?.id, survivor)
      XCTAssertFalse(h.session.latestReplay?.isCurrentTake ?? true)
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.capture.files, Array(h.capture.urls.suffix(2)))
      XCTAssertEqual(h.session.earlierReplay?.id, survivor)
      XCTAssertEqual(h.session.attemptsStarted, 3)
      XCTAssertEqual(h.session.attemptsFinished, 3)
    }

    func testFailedOldestDeletionPreventsPermissionAndRetainsPreciseBlockedOwnership() async throws
    {
      let h = try fixture()
      await first(h)
      await another(h)
      h.capture.failDiscard.insert(h.capture.urls[0])
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.capture.permissions, 2)
      XCTAssertEqual(h.capture.urls.count, 2)
      XCTAssertEqual(h.capture.files.count, 2)
      XCTAssertEqual(h.session.phase, .cleanupBlocked)
      XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)
      XCTAssertFalse(h.session.isPreparingAnotherTry)
      XCTAssertFalse(h.session.canReplay)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      XCTAssertFalse(h.session.canCheck)
      XCTAssertFalse(h.session.canCheckSound)
      _ = await h.session.retake()?.value
      XCTAssertEqual(h.capture.files, [h.capture.urls[0]])
      XCTAssertTrue(h.capture.discarded.contains(h.capture.urls[1]))
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.startRecording()
      XCTAssertEqual(h.capture.permissions, 2)
    }

    func testDeniedReplacementKeepsOnlyPriorReplayWithoutOldResultsOrCheckClaims() async throws {
      for twoFiles in [false, true] {
        let h = try fixture()
        await first(h)
        if twoFiles { await another(h) }
        await word(h)
        await sound(h)
        let prior = h.session.latestReplay?.id
        h.capture.permissionGranted = false
        await h.session.recordAnotherTry()
        XCTAssertEqual(h.session.phase, .permissionDenied)
        XCTAssertEqual(h.session.latestReplay?.id, prior)
        XCTAssertFalse(h.session.latestReplay?.isCurrentTake ?? true)
        XCTAssertNil(h.session.earlierReplay)
        XCTAssertEqual(h.capture.files, [h.capture.urls.last!])
        XCTAssertNil(h.session.summary)
        XCTAssertEqual(h.session.soundPhase, .ready)
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        XCTAssertFalse(h.session.canRecord)
        XCTAssertTrue(h.session.canRecordAnotherTry)
        await h.session.togglePlayback()
        h.session.checkRecording()
        h.session.checkSound()
        XCTAssertEqual(h.word.calls.count, 1)
        XCTAssertEqual(h.sound.prepared.count, 1)
        XCTAssertEqual(h.session.attemptsStarted, twoFiles ? 3 : 2)
        XCTAssertEqual(h.session.attemptsFinished, h.session.attemptsStarted)
      }
    }

    func testFailedStartStopAndInvalidReturnedFilePreservePriorButCannotCheckIt() async throws {
      for failure in TwoTryCapture.Failure.allCases {
        let h = try fixture()
        await first(h)
        let prior = h.session.latestReplay?.id
        h.capture.failure = failure
        await h.session.recordAnotherTry()
        if h.session.phase == .recording { h.session.stopRecording() }
        XCTAssertEqual(h.session.latestReplay?.id, prior, "\(failure)")
        XCTAssertFalse(h.session.latestReplay?.isCurrentTake ?? true)
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        XCTAssertNil(h.session.summary)
        XCTAssertEqual(h.session.attemptsFinished, 2)
        if failure == .startDeletion || failure == .stopDeletion {
          XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)
          XCTAssertEqual(h.capture.files.count, 2)
          let starts = h.capture.urls.count
          await h.session.recordAnotherTry()
          _ = await h.session.awaitPendingAudioCleanup()
          await h.session.startRecording()
          XCTAssertEqual(h.capture.urls.count, starts)
        } else {
          XCTAssertEqual(h.session.phase, .failed(.invalidRecording))
          XCTAssertEqual(h.capture.files, [h.capture.urls[0]])
          XCTAssertTrue(h.session.canReplay)
          XCTAssertTrue(h.session.canRecordAnotherTry)
        }
      }
    }

    func testInvalidReturnedFileIsHeldUntilExactDeletionSucceedsAndFullClearTriesSurvivor()
      async throws
    {
      let h = try fixture()
      await first(h)
      h.capture.failure = .invalidPCM
      await h.session.recordAnotherTry()
      h.capture.failDiscard.insert(h.capture.urls[1])
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.capture.files.count, 2)
      XCTAssertEqual(h.session.phase, .cleanupBlocked)
      XCTAssertNil(h.session.earlierReplay)
      _ = await h.session.retake()?.value
      XCTAssertEqual(h.capture.files, [h.capture.urls[1]])
      XCTAssertNil(h.session.latestReplay)
      h.capture.failDiscard.removeAll()
      let owner = try XCTUnwrap(h.capture.cleanupState.fileBlockedOwnerIDs.first)
      XCTAssertEqual(h.capture.retryCleanup(operationID: owner).result, .released)
      _ = await h.session.retake()?.value
      XCTAssertTrue(h.capture.files.isEmpty)
      XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)  // Existing private block stays sticky.
    }

    func testPermissionSheetInactiveWaitsForActiveWithoutReplacingCaptureOwner() async throws {
      let h = try fixture()
      await first(h)
      h.capture.delayPermission = true
      let task = Task { await h.session.recordAnotherTry() }
      await wait { h.capture.permission != nil }
      XCTAssertEqual(h.session.attemptsStarted, 2)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.capture.permissions, 2)
      h.session.appDidBecomeInactive()
      h.capture.releasePermission(true)
      await task.value
      XCTAssertEqual(h.capture.urls.count, 1)
      XCTAssertEqual(h.session.phase, .requestingPermission)
      h.session.appDidBecomeActive()
      XCTAssertEqual(h.capture.urls.count, 2)
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.capture.files.count, 2)
    }

    func testBackgroundDuringPermissionAndOldCaptureCallbackCannotResurrectEitherFile() async throws
    {
      let h = try fixture()
      await first(h)
      let stale = h.capture.completions[0]
      h.capture.delayPermission = true
      let task = Task { await h.session.recordAnotherTry() }
      await wait { h.capture.permission != nil }
      h.session.appDidEnterBackground()
      h.session.appDidBecomeActive()
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.startRecording()
      XCTAssertEqual(h.capture.permissions, 2)
      h.capture.releasePermission(true)
      await task.value
      XCTAssertTrue(h.capture.files.isEmpty)
      h.capture.delayPermission = false
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.startRecording()
      await stale(false)
      XCTAssertEqual(h.session.phase, .recording)
      XCTAssertEqual(h.capture.files.count, 1)
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.session.attemptsStarted, 3)
      XCTAssertTrue(h.session.latestReplay?.isCurrentTake ?? false)
    }

    func testLatestActualRequestBytesAndSoundPreparationSupportBothOrdersAndKeepConsumedClaims()
      async throws
    {
      for wordFirst in [true, false] {
        let h = try fixture()
        await first(h)
        await word(h)
        await sound(h)
        let prior = h.session.latestReplay?.id
        await another(h)
        if wordFirst {
          await word(h)
          await sound(h)
        } else {
          await sound(h)
          await word(h)
        }
        let call = try XCTUnwrap(h.word.calls.last)
        let prepared = try XCTUnwrap(h.sound.prepared.last)
        let request = try XCTUnwrap(JSONSerialization.jsonObject(with: call.body) as? [String: Any])
        let audio = try Data(contentsOf: h.capture.urls[1])
        XCTAssertEqual(call.recording.url, h.capture.urls[1])
        XCTAssertEqual(call.prompt, h.bread)
        XCTAssertEqual(call.context, .adult)
        XCTAssertEqual(request["audioBase64"] as? String, audio.base64EncodedString())
        XCTAssertEqual(request["attemptId"] as? String, call.attempt.uuidString.lowercased())
        XCTAssertNotEqual(call.attempt, h.word.calls[0].attempt)
        XCTAssertEqual(prepared.context.takeId, h.session.latestReplay?.id)
        XCTAssertNotEqual(prepared.context.takeId, prior)
        XCTAssertNotEqual(prepared.context.captureId, h.sound.prepared[0].context.captureId)
        let expectedBinding = try prepared.expected.fields([
          "attemptId", "requestSha256", "workerRequestSha256", "ownership", "audio", "source",
        ])
        XCTAssertEqual(
          expectedBinding["requestSha256"], .string(FeedbackContract.sha(prepared.body)))
        XCTAssertEqual(expectedBinding["audio"], try ResearchSoundContract.descriptor(audio))
        let expected = try XCTUnwrap(
          JSONSerialization.jsonObject(with: prepared.body) as? [String: Any])
        XCTAssertEqual(expected["audioBase64"] as? String, audio.base64EncodedString())
        let phase = h.session.phase
        let soundPhase = h.session.soundPhase
        await h.session.togglePlayback(.earlier)
        await h.session.togglePlayback(.latest)
        h.session.checkRecording()
        h.session.checkSound()
        XCTAssertEqual(h.word.calls.count, 2)
        XCTAssertEqual(h.sound.prepared.count, 2)
        XCTAssertEqual(h.session.phase, phase)
        XCTAssertEqual(h.session.soundPhase, soundPhase)
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        XCTAssertEqual(h.session.checksClaimed, 2)
      }
    }

    func testExactOldSoundControlsFinishBeforeFreshPermissionAndFailureKeepsCommonPause()
      async throws
    {
      let h = try fixture()
      await first(h)
      h.sound.observeFailure = true
      await sound(h)
      let old = try XCTUnwrap(h.sound.prepared.last)
      h.sound.delayReset = true
      h.sound.controlFailure = true
      let task = Task { await h.session.recordAnotherTry() }
      await wait { h.sound.resetPending != nil }
      XCTAssertTrue(h.session.isPreparingAnotherTry)
      XCTAssertFalse(h.session.setupEditable)
      XCTAssertFalse(h.session.canReplay)
      XCTAssertFalse(h.session.canPlayExample)
      XCTAssertEqual(h.capture.permissions, 1)
      XCTAssertEqual(h.sound.cancelled, [old])
      XCTAssertEqual(h.sound.resets.last?.declaration, old.declaration)
      XCTAssertEqual(h.sound.resets.last?.sessionId, old.context.sessionId)
      XCTAssertGreaterThan(h.sound.resets.last!.generation, old.context.generation)
      await h.session.recordAnotherTry()
      h.sound.releaseReset()
      await task.value
      XCTAssertEqual(h.capture.permissions, 2)
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertTrue(h.session.sharedProcessingPaused)
      XCTAssertFalse(h.session.hasLocalMediaCleanupIssue)
      XCTAssertTrue(h.session.canReplay(.earlier))
      XCTAssertTrue(h.session.canReplay(.latest))
      XCTAssertFalse(h.session.canCheck)
      XCTAssertFalse(h.session.canCheckSound)
    }

    func testSetupDriftWhileWaitingForControlsRevokesPreparationWithoutCancellingExactControls()
      async throws
    {
      let h = try fixture()
      await first(h)
      await sound(h)
      h.sound.delayReset = true
      let task = Task { await h.session.recordAnotherTry() }
      await wait { h.sound.resetPending != nil }
      h.session.practiceContext = .child(ageYears: 9)
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertFalse(h.session.isPreparingAnotherTry)
      XCTAssertTrue(h.capture.files.isEmpty)
      h.sound.releaseReset()
      await task.value
      XCTAssertEqual(h.capture.permissions, 1)
      XCTAssertNil(h.session.latestReplay)
      XCTAssertEqual(h.sound.resets.count, 1)
      XCTAssertFalse(h.session.sharedProcessingPaused)
    }

    func testEveryFullClearPathDeletesBothPrivateFilesAndExactPublicExample() async throws {
      for action in 0..<13 {
        let h = try fixture()
        await first(h)
        await another(h)
        await example(h)
        let publicURL = try XCTUnwrap(h.store.ownedURL)
        switch action {
        case 0: _ = await h.session.retake()?.value
        case 1: h.session.reset()
        case 2: h.session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
        case 3: h.session.practiceContext = .child(ageYears: 9)
        case 4: h.session.localProcessingEnabled = false
        case 5: h.session.soundAdultConfirmed = false
        case 6: h.session.soundProcessingEnabled = false
        case 7: h.session.practiceMode = "guided"
        case 8: await h.session.advance()
        case 9: h.session.appDidBecomeInactive()
        case 10: h.session.appDidEnterBackground()
        case 11: h.session.audioWasInterrupted()
        default: _ = await h.session.end().value
        }
        _ = await h.session.awaitPendingAudioCleanup()
        XCTAssertTrue(h.capture.files.isEmpty, "action \(action)")
        XCTAssertEqual(Set(h.capture.discarded), Set(h.capture.urls))
        XCTAssertFalse(FileManager.default.fileExists(atPath: publicURL.path))
        XCTAssertNil(h.store.ownedURL)
        XCTAssertNil(h.session.earlierReplay)
        XCTAssertNil(h.session.latestReplay)
        XCTAssertFalse(h.session.hasLocalMediaCleanupIssue)
      }
    }

    func testFullClearAttemptsOtherFilesAfterFailureAndPublicRetryRestoresOnlySafeCaptureState()
      async throws
    {
      let h = try fixture()
      await first(h)
      await another(h)
      await example(h)
      let publicURL = try XCTUnwrap(h.store.ownedURL)
      h.capture.failDiscard.insert(h.capture.urls[0])
      h.store.failRemove = true
      _ = await h.session.end().value
      XCTAssertEqual(h.capture.files, [h.capture.urls[0]])
      XCTAssertEqual(h.store.ownedURL, publicURL)
      XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)
      XCTAssertTrue(h.session.exampleCleanupBlocked)
      XCTAssertEqual(h.session.phase, .cleanupBlocked)
      XCTAssertTrue(h.capture.discarded.contains(h.capture.urls[1]))
      h.store.failRemove = false
      _ = await h.session.retryExampleCleanup().value
      XCTAssertNil(h.store.ownedURL)
      XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)
      XCTAssertFalse(h.session.canRecord)
    }

    func testPublicCleanupFailureBlocksAudioAndCloseResumesAfterExplicitRecovery() async throws {
      let h = try fixture()
      await first(h)
      await example(h)
      h.store.failRemove = true
      await h.session.recordAnotherTry()
      XCTAssertTrue(h.session.exampleCleanupBlocked)
      XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)
      XCTAssertEqual(h.capture.permissions, 1)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      // Retained evidence survives; blocked audio cannot replay.
      XCTAssertNotNil(h.session.latestReplay)
      XCTAssertFalse(h.session.canReplay)
      await h.session.togglePlayback()
      XCTAssertFalse(h.session.isPlaying)
      _ = await h.session.end().value
      XCTAssertNotEqual(h.session.phase, .ended)
      XCTAssertTrue(h.capture.files.isEmpty)
      XCTAssertFalse(h.session.canRecord)
      h.store.failRemove = false
      _ = await h.session.retryExampleCleanup().value
      XCTAssertFalse(h.session.hasLocalMediaCleanupIssue)
      XCTAssertEqual(h.session.phase, .ended)  // Authorized Close survives cleanup failure.
      XCTAssertFalse(h.session.canRecord)
    }

    func testCancelledCheckAndStaleReplyClearBothFilesWithoutReopeningClaims() async throws {
      let h = try fixture()
      await first(h)
      await another(h)
      h.word.delayed = true
      h.session.checkRecording()
      await wait { h.word.pending != nil }
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.capture.permissions, 2)
      _ = await h.session.cancelChecking()?.value
      XCTAssertTrue(h.capture.files.isEmpty)
      h.word.release()
      await wait { h.word.returned }
      for _ in 0..<30 { await Task.yield() }
      XCTAssertNil(h.session.latestReplay)
      XCTAssertEqual(h.session.phase, .ready)
      XCTAssertFalse(h.session.canCheck)
      XCTAssertEqual(h.session.attemptsStarted, 2)
    }

    func testProcessingPauseSurvivesNewTryAndRetakeWhileRecordingLimitStaysClosed() async throws {
      let h = try fixture()
      await first(h)
      h.word.reason = "cleanup_unconfirmed"
      await word(h)
      XCTAssertTrue(h.session.sharedProcessingPaused)
      await another(h)
      XCTAssertTrue(h.session.sharedProcessingPaused)
      XCTAssertTrue(h.session.canReplay)
      XCTAssertFalse(h.session.canCheck)
      XCTAssertFalse(h.session.canCheckSound)
      for _ in 2..<128 { await another(h) }
      XCTAssertEqual(h.capture.maximumFiles, 2)
      XCTAssertEqual(h.session.attemptsStarted, 128)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.capture.permissions, 128)
      _ = await h.session.retake()?.value
      XCTAssertTrue(h.session.sharedProcessingPaused)
      XCTAssertFalse(h.session.canRecord)
      XCTAssertTrue(h.capture.files.isEmpty)
    }

    func testGuidedOwnerRefusesNewActionEvenAfterObserverRemovalAndProgrammaticFreeAdult()
      async throws
    {
      let h = try fixture()
      let setupReleased = await h.session.awaitPendingAudioCleanup()
      XCTAssertTrue(setupReleased)
      let owner = UUID()
      XCTAssertTrue(
        h.session.installGuidedObserver(
          owner: owner, observer: { _ in }, allowsAction: { _ in true }))
      await first(h)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.capture.permissions, 1)
      h.session.removeGuidedObserver(owner: owner)
      h.session.practiceMode = "free"
      _ = await h.session.awaitPendingAudioCleanup()
      h.session.practiceContext = .adult
      _ = await h.session.awaitPendingAudioCleanup()
      h.session.soundAdultConfirmed = true
      _ = await h.session.awaitPendingAudioCleanup()
      h.session.soundProcessingEnabled = true
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertFalse(h.session.canRecordAnotherTry)
      XCTAssertFalse(h.session.canCheckSound)
      await h.session.recordAnotherTry()
      XCTAssertEqual(h.capture.permissions, 1)
      _ = await h.session.retake()?.value
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.startRecording()
      XCTAssertEqual(h.capture.permissions, 1)
    }

    func testChildAndUnsetContextCanRepeatLocalCaptureWithoutAdultSoundEligibility() async throws {
      for context: ResearchPracticeContext? in [.child(ageYears: 9), nil] {
        let h = try fixture()
        h.session.practiceContext = context
        _ = await h.session.awaitPendingAudioCleanup()
        h.session.localProcessingEnabled = false
        _ = await h.session.awaitPendingAudioCleanup()
        await first(h)
        await another(h)
        XCTAssertEqual(h.capture.files.count, 2)
        XCTAssertTrue(h.session.canRecordAnotherTry)
        XCTAssertTrue(h.session.canReplay(.earlier))
        XCTAssertTrue(h.session.canReplay(.latest))
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        h.session.checkRecording()
        h.session.checkSound()
        XCTAssertTrue(h.word.calls.isEmpty)
        XCTAssertTrue(h.sound.prepared.isEmpty)
      }
    }
  }

  @MainActor
  private final class TwoTryHarness {
    let bread = ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
    let capture: TwoTryCapture
    let player = TwoTryPlayer()
    let word = TwoTryWord()
    let sound = TwoTrySound()
    let store: TwoTryExampleStore
    let session: ResearchFeedbackSession
    init() throws {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      capture = TwoTryCapture(directory)
      store = TwoTryExampleStore(directory)
      session = makeControlledFeedbackSession(
        capturer: capture, player: player, processor: word,
        soundProcessor: sound, exampleLoader: TwoTryExamples(), exampleStore: store)
      session.selectedPrompt = bread
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      session.soundAdultConfirmed = true
      session.soundProcessingEnabled = true
    }
    func remove() async {
      capture.failDiscard = []
      capture.failure = nil
      store.failRemove = false
      sound.releaseReset()
      _ = await session.end().value
      if session.hasLocalMediaCleanupIssue { _ = await session.retryAudioCleanup().value }
      if !session.hasLocalMediaCleanupIssue {
        try? FileManager.default.removeItem(at: capture.directory)
      }
    }
  }

  @MainActor
  private final class TwoTryCapture: AudioCapturing {
    private let ownership = FeedbackCaptureFiles()
    var cleanupState: CaptureCleanupState { ownership.state }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> { ownership.publisher }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      ownership.completed(operationID)
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      ownership.retry(operationID) { url in
        try discard(.init(url: url, summary: .init(duration: 0.2, averagePower: -18)))
      }
    }
    enum Failure: CaseIterable, Equatable {
      case start, stop, invalidPCM, startDeletion, stopDeletion
    }
    let directory: URL
    var urls: [URL] = [], operations: [String] = [], discarded: [URL] = []
    var completions: [@MainActor (Bool) async -> Void] = []
    var active: URL?, failure: Failure?, permissionGranted = true, delayPermission = false
    var permission: CheckedContinuation<Bool, Never>?
    var permissions = 0, maximumFiles = 0
    var failDiscard: Set<URL> = []
    var files: [URL] { urls.filter { FileManager.default.fileExists(atPath: $0.path) } }
    init(_ directory: URL) { self.directory = directory }
    func requestPermission() async -> Bool {
      permissions += 1
      operations.append("permission")
      if delayPermission { return await withCheckedContinuation { permission = $0 } }
      return permissionGranted
    }
    func releasePermission(_ granted: Bool) {
      permission?.resume(returning: granted)
      permission = nil
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      if failure == .start { throw AudioCaptureError.couldNotStart }
      let url = directory.appendingPathComponent("generated-private-\(urls.count + 1).wav")
      urls.append(url)
      active = url
      operations.append("start:\(urls.count)")
      completions.append(onFinish)
      let samples = Array(
        repeating: Int16(4096 + (urls.count % 128) * 128), count: 3200 + urls.count)
      try (failure == .invalidPCM ? Data([1, 2]) : FeedbackFixture.wav(samples)).write(to: url)
      ownership.retain(url)
      maximumFiles = max(maximumFiles, files.count)
      if failure == .startDeletion {
        active = nil
        ownership.failed(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
    }
    func stop() throws -> CapturedRecording {
      guard let url = active else { throw AudioCaptureError.couldNotStart }
      active = nil
      if failure == .stopDeletion {
        ownership.failed(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      if failure == .stop {
        try FileManager.default.removeItem(at: url)
        ownership.removed(url)
        throw AudioCaptureError.couldNotReadRecording
      }
      return .init(
        url: url, summary: .init(duration: 4, averagePower: -20),
        cleanupOwnerID: ownership.owner(url))
    }
    func cancel() throws {
      if let active {
        try FileManager.default.removeItem(at: active)
        ownership.removed(active)
      }
      active = nil
    }
    func discard(_ recording: CapturedRecording) throws {
      try ownership.require(recording.url)
      discarded.append(recording.url)
      let index = urls.firstIndex(of: recording.url)! + 1
      operations.append("discard:\(index)")
      if failDiscard.contains(recording.url) {
        ownership.failed(recording.url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      if FileManager.default.fileExists(atPath: recording.url.path) {
        try FileManager.default.removeItem(at: recording.url)
      }
      ownership.removed(recording.url)
    }
  }

  private typealias TwoTryPlayer = FeedbackPlayer

  @MainActor
  private final class TwoTryWord: ResearchFeedbackProcessing {
    struct Call {
      let attempt: UUID
      let recording: CapturedRecording
      let prompt: ResearchFeedbackPrompt
      let context: ResearchPracticeContext
      let body: Data
    }
    var calls: [Call] = [], reason: String?, delayed = false, returned = false
    var pending: CheckedContinuation<RecordingFeedback, Never>?
    private var result: RecordingFeedback?
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) async throws -> RecordingFeedback {
      let audio = try FeedbackPCM.read(recording.url)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attemptId, audio: audio, prompt: prompt, practiceContext: practiceContext)
      calls.append(
        .init(
          attempt: attemptId, recording: recording, prompt: prompt, context: practiceContext,
          body: body))
      let value = try FeedbackContract.decode(
        FeedbackFixture.json(FeedbackFixture.response(body, audio: audio, reason: reason)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: prompt.targetUnsupported)
      result = value
      defer { returned = true }
      if delayed { return await withCheckedContinuation { pending = $0 } }
      return value
    }
    func release() {
      if let result { pending?.resume(returning: result) }
      pending = nil
    }
  }

  @MainActor
  private final class TwoTrySound: ResearchSoundProcessing {
    struct Reset {
      let declaration: ResearchSoundDeclaration
      let sessionId: String
      let generation: Int
    }
    let declarationValue = ResearchSoundDeclaration(
      serverNonce: "33333333-3333-4333-8333-333333333333",
      csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    let result = ResearchSoundObservation(
      status: .observedModelPreference, reason: "model_preferred_candidate", preference: .wPath)
    var prepared: [ResearchSoundPrepared] = [], cancelled: [ResearchSoundPrepared] = [],
      resets: [Reset] = []
    var observeFailure = false, delayReset = false, controlFailure = false
    var resetPending: CheckedContinuation<Void, Never>?
    func declaration() async throws -> ResearchSoundDeclaration { declarationValue }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      let value = try ResearchSoundContract.prepare(
        audio: ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url)),
        declaration: declaration, context: context)
      prepared.append(value)
      return value
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      if observeFailure { throw RecordingFeedbackError.serviceUnavailable }
      return result
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws { cancelled.append(prepared) }
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {
      resets.append(.init(declaration: declaration, sessionId: sessionId, generation: generation))
      if delayReset { await withCheckedContinuation { resetPending = $0 } }
      if controlFailure { throw RecordingFeedbackError.serviceUnavailable }
    }
    func releaseReset() {
      resetPending?.resume()
      resetPending = nil
    }
  }

  @MainActor
  private final class TwoTryExamples: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated control", licenseId: "Generated fixture",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated PCM, no human reference", changes: "Generated test only",
        speakerAgeKnown: false,
        clinicalReferenceApproved: false, wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200,
        isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data { bytes }
  }

  @MainActor
  private final class TwoTryExampleStore: ResearchPracticeExampleStoring {
    let directory: URL
    var ownedURL: URL?, failRemove = false
    init(_ directory: URL) { self.directory = directory }
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = directory.appendingPathComponent("generated-public-\(UUID().uuidString).wav")
      try data.write(to: url)
      ownedURL = url
      return url
    }
    func remove(_ url: URL) throws {
      guard ownedURL == url, !failRemove else { throw ResearchPracticeExampleError.cleanupFailed }
      try FileManager.default.removeItem(at: url)
      ownedURL = nil
    }
  }
#endif
