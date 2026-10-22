#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Real facade/runtime and SystemAudioCapturer with injected drivers and isolated registries.
  /// Generated PCM/replies establish control ordering only; no AV, permission or endpoint runs.
  @MainActor
  final class ResearchGuidedCoordinatorOwnershipTests: XCTestCase {
    private var fixtures: [GuidedOwnershipFixture] = []
    override func tearDown() async throws {
      for fixture in fixtures { await fixture.clean() }
      fixtures.removeAll()
      try await super.tearDown()
    }
    private func fixture(start: Bool = true) async throws -> GuidedOwnershipFixture {
      let value = try GuidedOwnershipFixture()
      fixtures.append(value)
      if start {
        let started = await value.guided.start(age: 9)
        XCTAssertTrue(started)
      }
      return value
    }
    private func reached(_ predicate: @MainActor () -> Bool) async {
      let deadline = ContinuousClock.now + .seconds(3)
      while !predicate(), ContinuousClock.now < deadline { await Task.yield() }
      XCTAssertTrue(predicate(), "Controlled milestone did not arrive before its deadline")
    }
    private func entered(_ barrier: GuidedOneShotBarrier) async {
      await reached { barrier.entered }
      XCTAssertFalse(barrier.expired)
    }
    private func settled(_ task: Task<Void, Never>, _ done: @MainActor () -> Bool) async {
      await reached(done)
      if done() { await task.value }
    }

    func testNextJoinsHeldPrepareAndStopBeforeMovingLedgerOrSelectingSuccessor() async throws {
      let h = try await fixture()
      await h.observe()
      let rows = h.guided.rows
      let prepare = h.driver.hold(.prepare)
      let stop = h.driver.hold(.stop)
      let replay = Task { await h.feedback.togglePlayback() }
      await entered(prepare)
      XCTAssertFalse(h.feedback.isPlaying)
      XCTAssertTrue(h.guided.canNext)
      var done = false
      let next = Task {
        await h.guided.next()
        done = true
      }
      await reached { h.guided.transitionPending && h.feedback.isAudioCleanupPending }
      XCTAssertFalse(done)
      XCTAssertEqual(h.guided.rows, rows)
      XCTAssertEqual(h.guided.currentItem?.word, "rabbit")
      XCTAssertTrue(h.captureFilesExist)
      XCTAssertFalse(h.guided.canRecord)
      prepare.release()
      await entered(stop)
      XCTAssertFalse(done)
      XCTAssertEqual(h.guided.rows, rows)
      XCTAssertTrue(h.captureFilesExist)
      stop.release()
      await settled(next, { done })
      await replay.value
      XCTAssertEqual(h.driver.count(.play), 0)
      XCTAssertEqual(h.guided.currentItem?.word, "bread")
      XCTAssertEqual(h.guided.rows, rows)
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertTrue(h.guided.canRecord)
    }

    func testSkipWaitsForHeldPreparationAndStopBeforeMarkingSkipped() async throws {
      let h = try await fixture()
      await h.record()
      let prepare = h.driver.hold(.prepare)
      let stop = h.driver.hold(.stop)
      let replay = Task { await h.feedback.togglePlayback() }
      await entered(prepare)
      var done = false
      let skip = Task {
        await h.guided.skip()
        done = true
      }
      await reached { h.guided.transitionPending }
      XCTAssertEqual(h.guided.rows[0].disposition, .notReached)
      prepare.release()
      await entered(stop)
      XCTAssertFalse(done)
      XCTAssertEqual(h.guided.rows[0].disposition, .notReached)
      XCTAssertTrue(h.captureFilesExist)
      stop.release()
      await settled(skip, { done })
      await replay.value
      XCTAssertEqual(h.guided.rows[0].disposition, .skipped)
      XCTAssertEqual(h.guided.currentItem?.word, "bread")
      XCTAssertEqual(h.guided.rows.count, 13)
    }

    func testFinishRoundFreezesFullThirteenOnlyAfterHeldStop() async throws {
      let h = try await fixture()
      await h.observe()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      let finish = Task {
        await h.guided.finishEarly()
        done = true
      }
      await entered(stop)
      XCTAssertNil(h.guided.firstSummary)
      XCTAssertEqual(h.guided.phase, .firstRound)
      XCTAssertTrue(h.captureFilesExist)
      stop.release()
      await settled(finish, { done })
      XCTAssertEqual(h.guided.firstSummary?.plannedCount, 13)
      XCTAssertEqual(h.guided.firstSummary?.validatedResponses, 1)
      XCTAssertEqual(h.guided.firstSummary?.dispositionCounts[.notReached], 12)
      XCTAssertEqual(h.guided.phase, .summary)
    }

    func testFinishPracticeHeldStopBlocksWriterAndKeepsFrozenFirstSummary() async throws {
      let h = try await fixture()
      await h.practice()
      let first = h.guided.firstSummary
      let visit = h.guided.practiceVisit?.id
      await h.record()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      let finish = Task {
        await h.guided.finishPractice()
        done = true
      }
      await entered(stop)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(h.guided.practiceVisit?.completionState, .active)
      XCTAssertFalse(h.guided.canTransition)
      XCTAssertTrue(h.captureFilesExist)
      h.writer.onRecord = {
        XCTAssertNil(h.gate.currentLease)
        XCTAssertFalse(h.captureFilesExist)
        XCTAssertFalse(h.guided.canTransition)
      }
      stop.release()
      await settled(finish, { done })
      XCTAssertEqual(h.writer.calls.map(\.id), [visit!])
      XCTAssertEqual(h.guided.practiceVisit?.completionState, .saved)
      XCTAssertEqual(h.guided.firstSummary, first)
    }

    func testFinishPracticeCannotWriteThroughHeldPrepareOrStop() async throws {
      let h = try await fixture()
      await h.practice()
      await h.record()
      let prepare = h.driver.hold(.prepare)
      let stop = h.driver.hold(.stop)
      let replay = Task { await h.feedback.togglePlayback() }
      await entered(prepare)
      var done = false
      let finish = Task {
        await h.guided.finishPractice()
        done = true
      }
      await reached { h.guided.transitionPending && h.feedback.isAudioCleanupPending }
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertTrue(h.captureFilesExist)
      prepare.release()
      await entered(stop)
      XCTAssertFalse(done)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit?.acknowledgedCompletion)
      stop.release()
      await settled(finish, { done })
      await replay.value
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertEqual(h.driver.count(.play), 0)
      XCTAssertFalse(h.captureFilesExist)
    }

    func testRetrySaveWaitsForExampleStopAndReusesExactCompletionWithoutNewClock() async throws {
      let h = try await fixture()
      await h.practice()
      await h.record()
      h.writer.failures = 1
      await h.guided.finishPractice()
      let completion = try XCTUnwrap(h.guided.practiceVisit?.acknowledgedCompletion)
      let stop = h.driver.hold(.stop)
      h.feedback.toggleExample()
      await reached { h.feedback.exampleState == .playing }
      var done = false
      let retry = Task {
        await h.guided.retryPracticeSave()
        done = true
      }
      await entered(stop)
      XCTAssertEqual(h.writer.calls, [completion])
      XCTAssertNotNil(h.store.ownedURL)
      stop.release()
      await settled(retry, { done })
      XCTAssertEqual(h.writer.calls, [completion, completion])
      XCTAssertEqual(h.clockCalls, 1)
      XCTAssertNil(h.store.ownedURL)
      XCTAssertEqual(h.guided.practiceVisit?.completionState, .saved)
    }

    func testCloseSupersedesSuspendedNextWithoutChangingRowsOrCreatingSummary() async throws {
      let h = try await fixture()
      await h.observe()
      let rows = h.guided.rows
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      let next = Task {
        await h.guided.next()
        done = true
      }
      await entered(stop)
      let close = h.guided.end()
      XCTAssertTrue(h.guided.closeRequested)
      XCTAssertFalse(h.guided.cleanupReleased)
      XCTAssertEqual(h.guided.phase, .ended)
      XCTAssertEqual(h.guided.rows, rows)
      XCTAssertTrue(h.captureFilesExist)
      stop.release()
      await settled(next, { done })
      let released = await close.value
      XCTAssertTrue(released)
      XCTAssertEqual(h.guided.rows, rows)
      XCTAssertNil(h.guided.firstSummary)
      XCTAssertNil(h.guided.currentItem)
      XCTAssertFalse(h.guided.transitionPending)
    }

    func testCloseSupersedesHeldPracticeFinishWithoutHistoryOrLateCompletion() async throws {
      let h = try await fixture()
      await h.practice()
      await h.record()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      let finish = Task {
        await h.guided.finishPractice()
        done = true
      }
      await entered(stop)
      let close = h.guided.end()
      stop.release()
      await settled(finish, { done })
      let released = await close.value
      XCTAssertTrue(released)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit)
      XCTAssertFalse(h.guided.canFinishPractice)
      XCTAssertFalse(h.guided.transitionPending)
    }

    func testDuplicateCloseJoinsStrongOwnerBeforeViewReferenceIsReleased() async throws {
      let h = try await fixture()
      await h.record()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var owner: ResearchGuidedWordSession? = h.detachGuided()
      weak var retained = owner
      let first = owner!.end()
      let second = owner!.end()
      owner = nil
      await entered(stop)
      XCTAssertNotNil(retained)
      XCTAssertFalse(retained!.cleanupReleased)
      XCTAssertTrue(h.captureFilesExist)
      XCTAssertEqual(h.driver.count(.stop), 1)
      stop.release()
      let a = await first.value
      let b = await second.value
      XCTAssertTrue(a)
      XCTAssertEqual(a, b)
      XCTAssertFalse(h.captureFilesExist)
      XCTAssertEqual(h.driver.count(.stop), 1)
    }

    func testFailedNextKeepsOriginalNegativeAndRequiresRetapAfterExplicitRecovery() async throws {
      let h = try await fixture()
      await h.observe()
      await h.feedback.togglePlayback()
      let id = try XCTUnwrap(h.gate.currentLease?.operationID)
      h.driver.failNextDeactivation()
      await h.guided.next()
      let original = try XCTUnwrap(h.player.requestStop(id: id))
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertEqual(h.guided.currentItem?.word, "rabbit")
      XCTAssertFalse(h.guided.canNext)
      XCTAssertTrue(h.captureFilesExist)
      let recovered = await h.guided.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      let unchanged = await original.value()
      XCTAssertEqual(unchanged, negative)
      XCTAssertEqual(h.guided.currentItem?.word, "rabbit")
      XCTAssertNil(h.guided.firstSummary)
      XCTAssertTrue(h.guided.canNext)
      await h.guided.next()
      XCTAssertEqual(h.guided.currentItem?.word, "bread")
    }

    func testFailedFinishDoesNotSaveDuringRecoveryAndNeedsFreshFinishTap() async throws {
      let h = try await fixture()
      await h.practice()
      await h.record()
      await h.feedback.togglePlayback()
      h.driver.failNextDeactivation()
      await h.guided.finishPractice()
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit?.acknowledgedCompletion)
      let recovered = await h.guided.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(h.guided.practiceVisit?.completionState, .active)
      await h.guided.finishPractice()
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertEqual(h.clockCalls, 2)
      XCTAssertEqual(h.guided.practiceVisit?.completionState, .saved)
    }

    func testHeldCloseCanResumeAfterExplicitRecoveryWithoutRewritingNegativeResult() async throws {
      let h = try await fixture()
      await h.record()
      await h.feedback.togglePlayback()
      h.driver.failNextDeactivation()
      let original = h.guided.end()
      let negative = await original.value
      XCTAssertFalse(negative)
      XCTAssertFalse(h.guided.cleanupReleased)
      XCTAssertTrue(h.guided.closeRequested)
      XCTAssertTrue(h.captureFilesExist)
      let recovered = await h.guided.retryAudioCleanup().value
      XCTAssertTrue(recovered)
      XCTAssertTrue(h.guided.cleanupReleased)
      XCTAssertEqual(h.feedback.phase, .ended)
      let stillNegative = await original.value
      XCTAssertFalse(stillNegative)
      XCTAssertTrue(h.writer.calls.isEmpty)
    }

    func testCloseArrivingDuringExplicitRetryJoinsReleasedRecoveryBeforeTerminalAcknowledgement()
      async throws
    {
      let h = try await fixture()
      await h.record()
      await h.feedback.togglePlayback()
      let id = try XCTUnwrap(h.gate.currentLease?.operationID)
      h.driver.failNextDeactivation()
      await h.guided.finishEarly()
      let original = try XCTUnwrap(h.player.requestStop(id: id))
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      let retryStage = h.driver.hold(.deactivate)
      let retry = h.guided.retryAudioCleanup()
      await entered(retryStage)
      let close = h.guided.end()
      XCTAssertFalse(h.guided.cleanupReleased)
      XCTAssertTrue(h.captureFilesExist)
      retryStage.release()
      let recovered = await retry.value
      XCTAssertTrue(recovered)
      XCTAssertTrue(h.guided.cleanupReleased)
      let released = await close.value
      XCTAssertTrue(released)
      XCTAssertTrue(h.guided.cleanupReleased)
      XCTAssertEqual(h.feedback.phase, .ended)
      let stillNegative = await original.value()
      XCTAssertEqual(stillNegative, negative)
      XCTAssertNil(h.guided.firstSummary)
      XCTAssertTrue(h.writer.calls.isEmpty)
    }

    func testFailedPlanCloseRetrySettlesLeaveDispositionBeforePositiveReturn() async throws {
      let h = try await fixture()
      await h.guided.finishEarly()
      let first = h.guided.firstSummary
      await h.guided.openPracticePlan()
      h.guided.togglePracticePlanItem("r-beginning-rabbit")
      h.guided.togglePracticePlanItem("r-middle-bread")
      await h.guided.beginPracticePlan()
      let visit = try XCTUnwrap(h.guided.practiceVisit?.id)
      await h.record()
      await h.feedback.togglePlayback()
      h.driver.failNextDeactivation()
      let original = h.guided.end()
      let negative = await original.value
      XCTAssertFalse(negative)
      XCTAssertFalse(h.guided.cleanupReleased)
      XCTAssertEqual(h.guided.practicePlanRows[0].visitID, visit)
      XCTAssertEqual(h.guided.practicePlanRows[0].disposition, .pending)
      XCTAssertTrue(h.captureFilesExist)
      let retryStage = h.driver.hold(.deactivate)
      let retry = h.guided.retryAudioCleanup()
      await entered(retryStage)
      XCTAssertTrue(h.guided.recoveryPending)
      XCTAssertFalse(h.guided.cleanupReleased)
      XCTAssertEqual(h.guided.practicePlanRows[0].disposition, .pending)
      retryStage.release()
      let recovered = await retry.value
      XCTAssertTrue(recovered)
      XCTAssertTrue(h.guided.cleanupReleased)
      XCTAssertFalse(h.guided.recoveryPending)
      XCTAssertEqual(h.guided.practicePlanRows[0].disposition, .leftUnsaved)
      XCTAssertEqual(h.guided.practicePlanRows[1].disposition, .pending)
      XCTAssertNil(h.guided.practicePlanRows[0].completion)
      XCTAssertNil(h.guided.planPosition)
      XCTAssertTrue(h.guided.selectedPlanItemIDs.isEmpty)
      XCTAssertNil(h.guided.practiceVisit)
      XCTAssertEqual(h.guided.firstSummary, first)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertFalse(h.captureFilesExist)
      let stillNegative = await original.value
      XCTAssertFalse(stillNegative)
    }

    func testRecheckWaitsForCleanupThenInstallsFreshFullThirteenAndFrozenFirst() async throws {
      let h = try await fixture()
      for _ in 0..<13 {
        await h.observe()
        await h.guided.next()
      }
      let first = try XCTUnwrap(h.guided.firstSummary)
      await h.guided.practice(item: first.rows[0].id)
      await h.record()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      let recheck = Task {
        await h.guided.startRecheck()
        done = true
      }
      await entered(stop)
      XCTAssertEqual(h.guided.phase, .practice)
      XCTAssertEqual(h.guided.firstSummary, first)
      XCTAssertNil(h.guided.recheckSummary)
      stop.release()
      await settled(recheck, { done })
      XCTAssertEqual(h.guided.phase, .recheck)
      XCTAssertEqual(h.guided.rows.count, 13)
      XCTAssertTrue(h.guided.rows.allSatisfy { $0.disposition == .notReached })
      for _ in 0..<13 {
        await h.observe()
        await h.guided.next()
      }
      let fresh = try XCTUnwrap(h.guided.recheckSummary)
      XCTAssertEqual(h.guided.firstSummary, first)
      XCTAssertEqual(fresh.plannedCount, 13)
      XCTAssertEqual(fresh.attemptsStarted, 13)
      XCTAssertNotEqual(first.roundId, fresh.roundId)
      XCTAssertTrue(Set(first.attempts.map(\.id)).isDisjoint(with: Set(fresh.attempts.map(\.id))))
      XCTAssertTrue(
        Set(first.attempts.map { $0.identity.captureId }).isDisjoint(
          with: Set(fresh.attempts.map { $0.identity.captureId })))
      XCTAssertTrue(
        Set(first.attempts.map { $0.identity.takeId }).isDisjoint(
          with: Set(fresh.attempts.map { $0.identity.takeId })))
      XCTAssertEqual(h.guided.comparison?.pairedCount, 13)
    }

    func testCancelledFinishCannotSaveLateAfterOwnedStopFinishes() async throws {
      let h = try await fixture()
      await h.practice()
      await h.record()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      let finish = Task {
        await h.guided.finishPractice()
        done = true
      }
      await entered(stop)
      finish.cancel()
      stop.release()
      await settled(finish, { done })
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(h.guided.practiceVisit?.completionState, .active)
      XCTAssertFalse(h.guided.transitionPending)
    }

    func testSetupObserverCloseCannotInstallStaleRoundOrAdmitRecording() async throws {
      let h = try await fixture(start: false)
      var cleanup: Task<Bool, Never>?
      let observation = h.feedback.$selectedPrompt.sink { prompt in
        if prompt != nil { cleanup = h.guided.end() }
      }
      let started = await h.guided.start(age: 9)
      let closed = await cleanup?.value
      withExtendedLifetime(observation) {}
      XCTAssertFalse(started)
      XCTAssertEqual(closed, true)
      XCTAssertEqual(h.guided.phase, .ended)
      XCTAssertTrue(h.guided.rows.isEmpty)
      XCTAssertNil(h.guided.currentItem)
      XCTAssertNil(h.guided.firstSummary)
      await h.guided.record()
      XCTAssertEqual(h.capture.permissions, 0)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      XCTAssertFalse(h.feedback.setupEditable)
      XCTAssertFalse(h.feedback.canCheckSound)
    }

    func testStartSnapshotDriftDuringHeldCleanupCannotInstallRoundOrLifecycleOwner()
      async throws
    {
      let h = try await fixture(start: false)
      h.feedback.selectedPrompt = ResearchGuidedWordSession.roster[1].prompt
      h.feedback.practiceContext = .adult
      h.feedback.localProcessingEnabled = true
      _ = await h.feedback.awaitPendingAudioCleanup()
      await h.feedback.startRecording()
      h.feedback.stopRecording()
      await h.feedback.togglePlayback()
      let stop = h.driver.hold(.stop)
      var done = false
      var started = true
      let start = Task {
        started = await h.guided.start(age: 9)
        done = true
      }
      await entered(stop)
      XCTAssertEqual(h.guided.phase, .setup)
      XCTAssertTrue(h.guided.rows.isEmpty)
      h.feedback.practiceContext = .child(ageYears: 10)
      stop.release()
      await settled(start, { done })
      _ = await h.feedback.awaitPendingAudioCleanup()
      XCTAssertFalse(started)
      XCTAssertTrue(h.guided.rows.isEmpty)
      XCTAssertNil(h.guided.currentItem)
      XCTAssertNil(h.guided.firstSummary)
      XCTAssertTrue(h.feedback.setupEditable)
      XCTAssertEqual(h.captureDriver.created.count, 1)
    }

    func testReentrantClockCloseRevokesFinishBeforeCleanupOrMetadataWrite() async throws {
      let h = try await fixture()
      await h.practice()
      await h.record()
      var close: Task<Bool, Never>?
      h.onNow = { close = h.guided.end() }
      await h.guided.finishPractice()
      let released = await close?.value
      XCTAssertEqual(released, true)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit)
      XCTAssertFalse(h.guided.transitionPending)
      XCTAssertTrue(h.guided.cleanupReleased)
    }

    func testSynchronousWriterCloseCannotLabelRevokedVisitSavedOrCreateAnotherWrite()
      async throws
    {
      let h = try await fixture()
      await h.practice()
      await h.record()
      var close: Task<Bool, Never>?
      h.writer.onRecord = {
        XCTAssertFalse(h.guided.canTransition)
        XCTAssertFalse(h.captureFilesExist)
        close = h.guided.end()
      }
      await h.guided.finishPractice()
      let released = await close?.value
      XCTAssertEqual(released, true)
      // The synchronous write was already entered; it is not described as cancelled.
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertNil(h.guided.practiceVisit)
      await h.guided.retryPracticeSave()
      await h.guided.finishPractice()
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertEqual(h.guided.phase, .ended)
    }

    func testOwnedSelectionBlocksActionsAndAnotherTransitionUntilSetupCleanupSettles()
      async throws
    {
      let h = try await fixture()
      await h.observe()
      var sawSelection = false
      let observation = h.feedback.$selectedPrompt.sink { prompt in
        if prompt?.word == "bread" {
          sawSelection = true
          XCTAssertTrue(h.guided.transitionPending)
          XCTAssertFalse(h.guided.canRecord)
          XCTAssertFalse(h.guided.canTransition)
          XCTAssertEqual(h.guided.currentItem?.word, "rabbit")
        }
      }
      await h.guided.next()
      withExtendedLifetime(observation) {}
      XCTAssertTrue(sawSelection)
      XCTAssertEqual(h.guided.currentItem?.word, "bread")
      XCTAssertTrue(h.guided.canRecord)
      XCTAssertFalse(h.feedback.audioTransitionPending)
    }

    func testCanonicalPlanSelectionPublishesOnceAndRejectsSynchronousReentry() async throws {
      let h = try await fixture()
      await h.guided.finishEarly()
      await h.guided.openPracticePlan()
      h.guided.togglePracticePlanItem("r-middle-bread")
      var publications: [[String]] = []
      let observation = h.guided.$selectedPlanItemIDs.dropFirst().sink { ids in
        publications.append(ids)
        XCTAssertTrue(h.guided.transitionPending)
        XCTAssertFalse(h.guided.canTransition)
        XCTAssertFalse(h.guided.canBeginPlan)
        h.guided.togglePracticePlanItem("r-middle-bread")
      }
      h.guided.togglePracticePlanItem("r-beginning-rabbit")
      withExtendedLifetime(observation) {}
      XCTAssertEqual(publications, [["r-beginning-rabbit", "r-middle-bread"]])
      XCTAssertEqual(h.guided.selectedPlanItemIDs, ["r-beginning-rabbit", "r-middle-bread"])
      XCTAssertFalse(h.guided.transitionPending)
      XCTAssertTrue(h.guided.canBeginPlan)
    }

    func testInstalledSelectionTokenRejectsReentryBeforePublishedPendingGetterCommits()
      async throws
    {
      let h = try await fixture()
      await h.guided.finishEarly()
      await h.guided.openPracticePlan()
      h.guided.togglePracticePlanItem("r-middle-bread")
      let first = h.guided.firstSummary
      XCTAssertTrue(h.guided.canTransition)
      XCTAssertTrue(h.guided.canBeginPlan)
      var publications: [[String]] = []
      var pendingPublications = 0
      var reentered = false
      let choices = h.guided.$selectedPlanItemIDs.dropFirst().sink { ids in
        publications.append(ids)
      }
      let pending = h.guided.$transitionPending.dropFirst().sink { value in
        guard value else { return }
        pendingPublications += 1
        guard !reentered else { return }
        reentered = true
        // willSet delivers true after claimTransition installs its token, while the
        // getter still reads false. Begin uses this exact synchronous admission gate.
        XCTAssertFalse(h.guided.transitionPending)
        XCTAssertFalse(h.guided.canTransition)
        XCTAssertFalse(h.guided.canBeginPlan)
        h.guided.togglePracticePlanItem("r-middle-bread")
        XCTAssertEqual(h.guided.selectedPlanItemIDs, ["r-middle-bread"])
        XCTAssertEqual(h.guided.phase, .practicePlanChoice)
        XCTAssertTrue(h.guided.practicePlanRows.isEmpty)
        XCTAssertTrue(h.writer.calls.isEmpty)
      }
      h.guided.togglePracticePlanItem("r-beginning-rabbit")
      choices.cancel()
      pending.cancel()
      XCTAssertTrue(reentered)
      XCTAssertEqual(pendingPublications, 1)
      XCTAssertEqual(publications, [["r-beginning-rabbit", "r-middle-bread"]])
      XCTAssertEqual(h.guided.selectedPlanItemIDs, ["r-beginning-rabbit", "r-middle-bread"])
      XCTAssertEqual(h.guided.phase, .practicePlanChoice)
      XCTAssertFalse(h.guided.transitionPending)
      XCTAssertTrue(h.guided.canBeginPlan)
      XCTAssertEqual(h.guided.firstSummary, first)
      XCTAssertTrue(h.writer.calls.isEmpty)
      // A fresh Begin after ownership ends remains a legitimate action.
      await h.guided.beginPracticePlan()
      XCTAssertEqual(h.guided.phase, .practice)
      XCTAssertEqual(
        h.guided.practicePlanRows.map(\.item.id), ["r-beginning-rabbit", "r-middle-bread"])
      XCTAssertEqual(h.guided.currentItem?.id, "r-beginning-rabbit")
      XCTAssertEqual(h.guided.firstSummary, first)
      XCTAssertTrue(h.writer.calls.isEmpty)
    }

    func testPlanSelectionRevokedBySynchronousCloseCannotPublishNewChoice() async throws {
      let h = try await fixture()
      await h.guided.finishEarly()
      await h.guided.openPracticePlan()
      var close: Task<Bool, Never>?
      let observation = h.guided.$transitionPending.dropFirst().sink { pending in
        if pending { close = h.guided.end() }
      }
      h.guided.togglePracticePlanItem("r-beginning-rabbit")
      XCTAssertTrue(h.guided.closeRequested)
      XCTAssertEqual(h.guided.phase, .ended)
      XCTAssertTrue(h.guided.selectedPlanItemIDs.isEmpty)
      XCTAssertFalse(h.guided.transitionPending)
      let released = await close?.value
      withExtendedLifetime(observation) {}
      XCTAssertEqual(released, true)
      XCTAssertTrue(h.guided.cleanupReleased)
      XCTAssertTrue(h.guided.selectedPlanItemIDs.isEmpty)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.guided.practiceVisit)
    }

    func testPlanSkipAndReplacementWaitForStopAndNeverQueueDuplicateChoice() async throws {
      let h = try await fixture()
      await h.guided.finishEarly()
      await h.guided.openPracticePlan()
      h.guided.togglePracticePlanItem("r-beginning-rabbit")
      h.guided.togglePracticePlanItem("r-middle-bread")
      await h.guided.beginPracticePlan()
      let visit = h.guided.practiceVisit?.id
      h.feedback.toggleExample()
      await reached { h.feedback.exampleState == .playing }
      let stop = h.driver.hold(.stop)
      var done = false
      let skip = Task {
        await h.guided.skipPracticePlanItem()
        done = true
      }
      await entered(stop)
      XCTAssertEqual(h.guided.practicePlanRows[0].disposition, .pending)
      XCTAssertEqual(h.guided.practiceVisit?.id, visit)
      await h.guided.editPracticePlan()
      await h.guided.endPracticePlan()
      await h.guided.nextPracticePlanItem()
      XCTAssertEqual(h.guided.planPosition, 1)
      stop.release()
      await settled(skip, { done })
      XCTAssertEqual(h.guided.planPosition, 2)
      XCTAssertEqual(h.guided.practicePlanRows[0].disposition, .skipped)
      XCTAssertNotEqual(h.guided.practiceVisit?.id, visit)
      XCTAssertFalse(h.guided.practiceVisit!.hasValidCapture)
    }

    func testPermissionInactivePreservesOwnerButActualCloseRevokesLateGrant() async throws {
      let h = try await fixture()
      h.capture.delayPermission = true
      var done = false
      let record = Task {
        await h.guided.record()
        done = true
      }
      await reached { h.capture.pending != nil }
      h.feedback.appDidBecomeInactive()
      XCTAssertEqual(h.guided.phase, .firstRound)
      XCTAssertFalse(h.guided.closeRequested)
      let close = h.guided.end()
      let duplicate = h.guided.end()
      XCTAssertFalse(h.guided.cleanupReleased)
      h.capture.resolvePermission(true)
      await settled(record, { done })
      let a = await close.value
      let b = await duplicate.value
      h.feedback.appDidBecomeActive()
      XCTAssertTrue(a)
      XCTAssertEqual(a, b)
      XCTAssertTrue(h.captureDriver.created.isEmpty)
      XCTAssertEqual(h.guided.attempts.count, 1)
      XCTAssertEqual(h.guided.attempts[0].terminal, .permissionCancelled)
      XCTAssertFalse(h.guided.canRecord)
    }
  }

  /// A bounded, single-use driver barrier. Expiry fails the driver; it never simulates release.
  private final class GuidedOneShotBarrier: @unchecked Sendable {
    private let condition = NSCondition()
    private var hasEntered = false
    private var released = false
    private var didExpire = false
    var entered: Bool { condition.withLock { hasEntered } }
    var expired: Bool { condition.withLock { didExpire } }
    func arrive() throws {
      condition.lock()
      defer { condition.unlock() }
      hasEntered = true
      let deadline = Date().addingTimeInterval(5)
      while !released {
        if !condition.wait(until: deadline), !released {
          didExpire = true
          throw GuidedOwnershipDriver.Failure.barrierExpired
        }
      }
    }
    func release() {
      condition.lock()
      released = true
      condition.broadcast()
      condition.unlock()
    }
  }
  private final class GuidedOwnershipDriver: PracticePlaybackDriver, @unchecked Sendable {
    enum Stage: Hashable { case prepare, play, stop, releaseResources, deactivate }
    enum Failure: Error { case injected, barrierExpired }
    private let lock = NSLock()
    private var barriers: [Stage: GuidedOneShotBarrier] = [:]
    private var allBarriers: [GuidedOneShotBarrier] = []
    private var counts: [Stage: Int] = [:]
    private var failDeactivation = false
    func hold(_ stage: Stage) -> GuidedOneShotBarrier {
      lock.withLock {
        let barrier = GuidedOneShotBarrier()
        barriers[stage] = barrier
        allBarriers.append(barrier)
        return barrier
      }
    }
    func count(_ stage: Stage) -> Int { lock.withLock { counts[stage, default: 0] } }
    func failNextDeactivation() { lock.withLock { failDeactivation = true } }
    func releaseAll() {
      let pending = lock.withLock {
        failDeactivation = false
        return allBarriers
      }
      for barrier in pending { barrier.release() }
    }
    private func enter(_ stage: Stage) throws {
      let barrier = lock.withLock {
        counts[stage, default: 0] += 1
        return barriers.removeValue(forKey: stage)
      }
      try barrier?.arrive()
    }
    func activate() throws {}
    func prepare() throws -> Bool {
      try enter(.prepare)
      return true
    }
    func play() throws -> Bool {
      try enter(.play)
      return true
    }
    func stop() throws { try enter(.stop) }
    func releasePlaybackResources() throws { try enter(.releaseResources) }
    func deactivate() throws {
      try enter(.deactivate)
      let fail = lock.withLock {
        let fail = failDeactivation
        failDeactivation = false
        return fail
      }
      if fail { throw Failure.injected }
    }
  }
  @MainActor
  private final class GuidedOwnershipCaptureDriver: CaptureHardwareDriver {
    var created: [URL] = []
    func configureActivate() throws {}
    func createRecorder(
      url: URL, recorderID: UUID,
      onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
    ) throws {
      created.append(url)
      try FeedbackFixture.wav(Array(repeating: Int16(4096 + created.count), count: 3200)).write(
        to: url)
    }
    func prepare() throws -> Bool { true }
    func record() throws -> Bool { true }
    func stop() throws {}
    func detachRelease() throws {}
    func deactivate() throws {}
  }
  @MainActor
  private final class GuidedOwnershipCapture: AudioCapturing {
    let system: SystemAudioCapturer
    var permissions = 0, delayPermission = false
    var pending: CheckedContinuation<Bool, Never>?
    init(_ system: SystemAudioCapturer) { self.system = system }
    var cleanupState: CaptureCleanupState { system.cleanupState }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      system.cleanupStatePublisher
    }
    func requestPermission() async -> Bool {
      permissions += 1
      return delayPermission ? await withCheckedContinuation { pending = $0 } : true
    }
    func resolvePermission(_ grant: Bool) {
      pending?.resume(returning: grant)
      pending = nil
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      try system.start(onFinish: onFinish)
    }
    func stop() throws -> CapturedRecording { try system.stop() }
    func cancel() throws { try system.cancel() }
    func discard(_ recording: CapturedRecording) throws { try system.discard(recording) }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      system.retryCleanup(operationID: operationID)
    }
  }
  @MainActor
  private final class GuidedOwnershipWord: ResearchFeedbackProcessing {
    var calls = 0
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) async throws -> RecordingFeedback {
      try await process(
        attemptId: attemptId, recording: recording, prompt: prompt,
        practiceContext: practiceContext, onEvent: { _ in })
    }
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> RecordingFeedback {
      calls += 1
      let audio = try FeedbackPCM.read(recording.url)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attemptId, audio: audio, prompt: prompt, practiceContext: practiceContext)
      onEvent(.requestStarted)
      return try FeedbackContract.decode(
        FeedbackFixture.json(
          FeedbackFixture.response(body, audio: audio, unsupported: prompt.targetUnsupported)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: prompt.targetUnsupported)
    }
  }
  @MainActor
  private final class GuidedOwnershipSound: ResearchSoundProcessing {
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
  private final class GuidedOwnershipExamples: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated test fixture", licenseId: "Generated PCM",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!, attribution: "Generated PCM",
        changes: "Test control only", speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data { bytes }
  }
  @MainActor
  private final class GuidedOwnershipStore: ResearchPracticeExampleStoring {
    let directory: URL
    let files: ProcessAudioFileOwnership
    private let owner = UUID()
    var ownedURL: URL?
    init(directory: URL, files: ProcessAudioFileOwnership) {
      self.directory = directory
      self.files = files
    }
    func write(_ data: Data) throws -> URL {
      let url = directory.appendingPathComponent("example-\(UUID().uuidString).wav")
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      ownedURL = url
      files.retain(url, owner: owner)
      try data.write(to: url, options: .withoutOverwriting)
      return url
    }
    func remove(_ url: URL) throws {
      guard ownedURL == url, files.canRemove(url, owner: owner) else {
        throw ResearchPracticeExampleError.cleanupFailed
      }
      try FileManager.default.removeItem(at: url)
      files.didRemove(url, owner: owner)
      ownedURL = nil
    }
  }
  @MainActor
  private final class GuidedOwnershipWriter: ResearchGuidedPracticeParticipationRecording {
    var calls: [ResearchGuidedPracticeCompletion] = []
    var failures = 0
    var onRecord: (@MainActor () -> Void)?
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
      calls.append(
        .init(id: sessionID, completedAt: completedAt, soundID: soundID, wordCount: wordCount))
      onRecord?()
      if failures > 0 {
        failures -= 1
        throw PracticeParticipationStore.StoreError.unreadable
      }
    }
  }
  @MainActor
  private final class GuidedOwnershipFixture {
    let directory: URL
    let gate: AudioHardwareOwnership
    let files: ProcessAudioFileOwnership
    let driver: GuidedOwnershipDriver
    let captureDriver: GuidedOwnershipCaptureDriver
    let capture: GuidedOwnershipCapture
    let player: SystemAcknowledgedPracticeAudioPlayer
    let writer: GuidedOwnershipWriter
    let word: GuidedOwnershipWord
    let store: GuidedOwnershipStore
    let feedback: ResearchFeedbackSession
    private var owner: ResearchGuidedWordSession?
    private let clock: GuidedOwnershipClock
    var clockCalls: Int { clock.calls }
    var onNow: (@MainActor () -> Void)? {
      get { clock.onNow }
      set { clock.onNow = newValue }
    }
    var guided: ResearchGuidedWordSession { owner! }
    init() throws {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "guided-ownership-\(UUID().uuidString)")
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      let gate = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      let captureDriver = GuidedOwnershipCaptureDriver()
      let driver = GuidedOwnershipDriver()
      let writer = GuidedOwnershipWriter()
      let word = GuidedOwnershipWord()
      let clock = GuidedOwnershipClock()
      let capture = GuidedOwnershipCapture(
        SystemAudioCapturer(
          recordingStore: TemporaryRecordingStore(directory: directory), fileOwnership: files,
          hardwareOwnership: gate, driverFactory: { captureDriver },
          summaryReader: { _ in .init(duration: 0.2, averagePower: -18) }))
      let player = SystemAcknowledgedPracticeAudioPlayer(
        ownership: gate, fileOwnership: files, factory: { _, _ in driver })
      let store = GuidedOwnershipStore(directory: directory, files: files)
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: player, processor: word, soundProcessor: GuidedOwnershipSound(),
        exampleLoader: GuidedOwnershipExamples(), exampleStore: store)
      let owner = ResearchGuidedWordSession(
        feedbackSession: feedback, participationWriter: writer, now: { clock.now() })
      owner.localProcessingEnabled = true
      self.directory = directory
      self.gate = gate
      self.files = files
      self.captureDriver = captureDriver
      self.driver = driver
      self.writer = writer
      self.word = word
      self.clock = clock
      self.capture = capture
      self.player = player
      self.store = store
      self.feedback = feedback
      self.owner = owner
    }
    func detachGuided() -> ResearchGuidedWordSession {
      let value = owner!
      owner = nil
      return value
    }
    var captureFilesExist: Bool {
      captureDriver.created.contains { FileManager.default.fileExists(atPath: $0.path) }
    }
    func record() async {
      await guided.record()
      guided.stop()
      XCTAssertEqual(feedback.phase, .review)
    }
    func observe() async {
      await record()
      guided.check()
      let deadline = ContinuousClock.now + .seconds(3)
      while feedback.isProcessing, ContinuousClock.now < deadline { await Task.yield() }
      XCTAssertFalse(feedback.isProcessing)
      XCTAssertTrue(guided.attempts.last?.validated == true)
    }
    func practice() async {
      await guided.finishEarly()
      await guided.practice(item: "r-middle-bread")
      XCTAssertEqual(guided.phase, .practice)
    }
    func clean() async {
      driver.releaseAll()
      capture.resolvePermission(false)
      writer.onRecord = nil
      onNow = nil
      if let owner {
        _ = await owner.end().value
        if feedback.hasLocalMediaCleanupIssue { _ = await owner.retryAudioCleanup().value }
      } else {
        _ = await feedback.end().value
        if feedback.hasLocalMediaCleanupIssue { _ = await feedback.retryAudioCleanup().value }
      }
      XCTAssertNil(gate.currentLease)
      XCTAssertNil(store.ownedURL)
      XCTAssertFalse(captureFilesExist)
      XCTAssertTrue(files.protectedURLs.isEmpty)
      if gate.currentLease == nil, files.protectedURLs.isEmpty {
        try? FileManager.default.removeItem(at: directory)
      }
    }
  }
  @MainActor
  private final class GuidedOwnershipClock {
    var calls = 0
    var onNow: (@MainActor () -> Void)?
    func now() -> Date {
      calls += 1
      onNow?()
      return Date(timeIntervalSince1970: Double(1_700_000_000 + calls))
    }
  }
#endif
