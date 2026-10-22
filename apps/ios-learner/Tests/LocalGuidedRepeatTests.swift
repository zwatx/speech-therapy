#if DEBUG && targetEnvironment(simulator)
  import Combine
  import XCTest
  @testable import CadenceLearner

  /// Generated dependencies exercise coordinator ownership, never sensors or real models.
  @MainActor
  final class LocalGuidedRepeatTests: XCTestCase {
    private let custom = [
      "b-beginning-baby", "k-middle-backpack", "r-middle-bread",
      "d-beginning-door", "s-beginning-sky",
    ]

    private func completed() async throws -> LocalGuidedGeneratedResources {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      for (index, entryID) in custom.enumerated() {
        let entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == entryID })
        XCTAssertTrue(r.session.replaceSetupEntry(at: index, with: entry))
      }
      await r.session.startInitialReview()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.checkCurrentWord()
      await r.session.finishStageNow()
      r.session.togglePracticeSelection(entryID: custom[2])
      await r.session.startPractice()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.advanceVisit()
      await r.session.startRecheck()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.checkCurrentWord()
      await r.session.finishStageNow()
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertEqual(r.history.entries.count, 1)
      return r
    }

    func testCustomFiveRepeatRetainsOwnerWorkflowButClearsObservationsAndStartsNoMedia()
      async throws
    {
      let r = try await completed()
      let media = r.session.media
      let previous = try XCTUnwrap(r.session.ledger)
      let requests = r.recognizer.requests.count
      let permission = r.capture.permissionRequests
      let files = r.capture.createdURLs
      let history = r.history.entries
      let old =
        previous.initialRound.rows.compactMap(\.firstSubmission)
        + (previous.recheckRound?.rows.compactMap(\.firstSubmission) ?? [])
      await r.session.repeatReview()
      let next = try XCTUnwrap(r.session.ledger)
      let visit = try XCTUnwrap(next.activeReviewVisit)
      XCTAssertTrue(r.session.media === media)
      XCTAssertEqual(next.workflowID, previous.workflowID)
      XCTAssertEqual(next.entries.map(\.id), custom)
      XCTAssertNotEqual(next.initialRound.id, previous.initialRound.id)
      XCTAssertNotEqual(next.initialRound.id, previous.recheckRound?.id)
      XCTAssertFalse(old.map(\.visit.visitID).contains(visit.visitID))
      XCTAssertEqual(next.stage, .initialReview)
      XCTAssertNil(next.recheckRound)
      XCTAssertTrue(next.practiceRows.isEmpty)
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      XCTAssertTrue(next.initialRound.rows.allSatisfy { $0.firstSubmission == nil })
      XCTAssertEqual(
        next.initialRound.rows.map(\.state), [.ready] + Array(repeating: .notVisited, count: 4))
      XCTAssertNil(r.session.media.latestTry)
      XCTAssertEqual(r.session.media.phase, .ready)
      XCTAssertEqual(r.session.media.playbackState, .idle)
      XCTAssertEqual(r.recognizer.requests.count, requests)
      XCTAssertEqual(r.capture.permissionRequests, permission)
      XCTAssertEqual(r.capture.createdURLs, files)
      XCTAssertEqual(r.history.entries, history)
      var receiving = next
      for identity in old {
        XCTAssertFalse(receiving.receive(.submitted(identity)))
        XCTAssertFalse(
          receiving.receive(
            .settled(
              identity: identity, status: .matched,
              resultEligible: true, cleanupConfirmed: true)))
      }
      // Fresh operation/take IDs arise only after this explicit subsequent user action.
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.checkCurrentWord()
      let fresh = try XCTUnwrap(r.recognizer.requests.last)
      XCTAssertFalse(old.map(\.operationID).contains(fresh.operationID))
      XCTAssertFalse(old.map(\.tryID).contains(fresh.tryID))
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testRepeatRejectsSetupAndUnfinishedReview() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      XCTAssertFalse(r.session.canRepeatReview)
      await r.session.repeatReview()
      XCTAssertNil(r.session.ledger)
      await r.session.startInitialReview()
      let round = r.session.ledger?.initialRound.id
      await r.session.repeatReview()
      XCTAssertEqual(r.session.ledger?.initialRound.id, round)
      XCTAssertEqual(r.capture.permissionRequests, 0)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testDuplicateCallsCreateOnlyOneFreshRound() async throws {
      let r = try await completed()
      let first = Task { await r.session.repeatReview() }
      let second = Task { await r.session.repeatReview() }
      await first.value
      let round = r.session.ledger?.initialRound.id
      await second.value
      XCTAssertEqual(r.session.ledger?.initialRound.id, round)
      XCTAssertEqual(r.session.ledger?.stage, .initialReview)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testTwoExplicitRepeatCyclesKeepTheirOwnFirstChecksAndFreshRoundIdentities() async throws {
      let r = try await completed()
      let workflow = r.session.ledger?.workflowID
      let history = r.history.entries
      var rounds: Set<UUID> = [try XCTUnwrap(r.session.ledger?.initialRound.id)]
      var visits: Set<UUID> = []
      var operations = Set(r.recognizer.requests.map(\.operationID))
      var takes = Set(r.recognizer.requests.map(\.tryID))
      for _ in 0..<2 {
        await r.session.repeatReview()
        let ledger = try XCTUnwrap(r.session.ledger)
        XCTAssertEqual(ledger.workflowID, workflow)
        XCTAssertTrue(rounds.insert(ledger.initialRound.id).inserted)
        XCTAssertTrue(visits.insert(try XCTUnwrap(ledger.activeReviewVisit?.visitID)).inserted)
        await r.session.media.startRecording()
        r.session.media.stopRecording()
        await r.session.checkCurrentWord()
        let request = try XCTUnwrap(r.recognizer.requests.last)
        XCTAssertTrue(operations.insert(request.operationID).inserted)
        XCTAssertTrue(takes.insert(request.tryID).inserted)
        await r.session.finishStageNow()
        r.session.togglePracticeSelection(entryID: custom[0])
        await r.session.startPractice()
        await r.session.skipVisit()
        await r.session.startRecheck()
        await r.session.finishStageNow()
        XCTAssertEqual(r.session.ledger?.stage, .completed)
        XCTAssertEqual(r.history.entries, history)
      }
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testCancellationAtReplacementPublicationRollsBackWithoutAutomaticRetry() async throws {
      let r = try await completed()
      let round = r.session.ledger?.initialRound.id
      let selection = r.session.practiceSelectionIDs
      var armed = false
      var repeatTask: Task<Void, Never>?
      let subscription = r.session.$ledger.sink { ledger in
        if armed && ledger?.stage == .initialReview { repeatTask?.cancel() }
      }
      armed = true
      repeatTask = Task { await r.session.repeatReview() }
      await repeatTask?.value
      subscription.cancel()
      XCTAssertEqual(r.session.ledger?.initialRound.id, round)
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.session.practiceSelectionIDs, selection)
      await r.session.repeatReview()
      XCTAssertEqual(r.session.ledger?.stage, .initialReview)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testReentrantBackgroundAtPreparationSelectionOrLedgerPreservesSummaryThenExplicitRetry()
      async throws
    {
      for point in 0..<3 {
        let r = try await completed()
        let previous = try XCTUnwrap(r.session.ledger)
        let selection = r.session.practiceSelectionIDs
        let history = r.history.entries
        var armed = false
        var fired = false
        let revoke = {
          if armed && !fired {
            fired = true
            r.session.background()
          }
        }
        var subscription: AnyCancellable?
        switch point {
        case 0:
          subscription = r.session.media.$phase.sink { if $0 == .ready { revoke() } }
        case 1:
          subscription = r.session.$practiceSelectionIDs.sink { if $0.isEmpty { revoke() } }
        default:
          subscription = r.session.$ledger.sink { if $0?.stage == .initialReview { revoke() } }
        }
        armed = true
        await r.session.repeatReview()
        subscription?.cancel()
        XCTAssertTrue(fired)
        XCTAssertEqual(r.session.ledger?.stage, .completed)
        XCTAssertEqual(r.session.ledger?.initialRound.id, previous.initialRound.id)
        XCTAssertEqual(r.session.practiceSelectionIDs, selection)
        XCTAssertEqual(r.history.entries, history)
        for _ in 0..<256 where r.session.media.isTransitioning { await Task.yield() }
        XCTAssertFalse(r.session.media.isTransitioning)
        await r.session.repeatReview()
        XCTAssertEqual(r.session.ledger?.stage, .initialReview)
        XCTAssertNotEqual(r.session.ledger?.initialRound.id, previous.initialRound.id)
        let closed = await r.session.close()
        XCTAssertTrue(closed)
      }
    }

    func testCloseWinningDuringPreparationNeverCommitsFreshRound() async throws {
      let r = try await completed()
      let round = r.session.ledger?.initialRound.id
      var armed = false
      var fired = false
      let subscription = r.session.media.$phase.sink { phase in
        if armed && !fired && phase == .ready {
          fired = true
          r.session.disappeared()  // Synchronously revokes and hands end to the same owner.
        }
      }
      armed = true
      await r.session.repeatReview()
      subscription.cancel()
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(r.session.ledger?.initialRound.id, round)
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      await r.session.repeatReview()
      XCTAssertEqual(r.session.ledger?.initialRound.id, round)
    }

    func testUnreleasedForeignVisitPreservesCompletedSummaryAndShowsRecoveryNote() async throws {
      let r = try await completed()
      let old = try XCTUnwrap(r.session.ledger)
      var competing = try LocalGuidedReviewLedger(entryIDs: custom, workflowID: old.workflowID)
      let visit = try XCTUnwrap(competing.beginReviewVisit(visitID: UUID()))
      let prepared = await r.session.media.prepareGuidedVisit(
        entry: competing.entries[0], visit: .review(visit))
      XCTAssertTrue(prepared)
      await r.session.repeatReview()
      XCTAssertEqual(r.session.ledger?.initialRound.id, old.initialRound.id)
      XCTAssertEqual(r.session.media.guidedMediaVisit, .review(visit))
      XCTAssertNotNil(r.session.statusNote)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testPendingRepeatExactReleaseRefusalPreservesSummaryWithoutReplacement() async throws {
      let r = try await completed()
      let oldRound = r.session.ledger?.initialRound.id
      var armed = false
      var task: Task<Void, Never>?
      let subscription = r.session.$ledger.sink { ledger in
        if armed && ledger?.stage == .initialReview { task?.cancel() }
      }
      armed = true
      task = Task { await r.session.repeatReview() }
      await task?.value
      subscription.cancel()
      let pending = try XCTUnwrap(r.session.media.guidedMediaVisit)
      let ended = await r.session.media.end()
      XCTAssertTrue(ended)
      let requests = r.recognizer.requests.count
      await r.session.repeatReview()
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.session.ledger?.initialRound.id, oldRound)
      XCTAssertEqual(r.session.media.guidedMediaVisit, pending)
      XCTAssertEqual(r.recognizer.requests.count, requests)
      XCTAssertNotNil(r.session.statusNote)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }
  }
#endif
