#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Full coordinator/recording-owner integration with generated audio and model doubles.
  /// Actual acoustic inference and live microphone behavior are separate checks.
  @MainActor
  final class LocalGuidedResearchFlowTests: XCTestCase {
    func testOptInNeedsKnownAgeAndFreezesBeforeFirstRecording() async throws {
      let r = Resources()
      XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: nil))
      XCTAssertFalse(r.session.canStartInitial)
      await r.session.startInitialReview()
      XCTAssertNil(r.session.ledger)
      XCTAssertEqual(r.capture.permissionRequests, 0)
      XCTAssertTrue(r.processor.calls.isEmpty)
      XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 6))
      await r.session.startInitialReview()
      XCTAssertFalse(r.session.configureResearchModel(enabled: false, ageYears: nil))
      XCTAssertTrue(r.session.researchModelEnabled)
      XCTAssertEqual(r.session.researchAgeYears, 6)
      XCTAssertTrue(r.processor.calls.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testFiveSoundReviewChosenPracticeFreshRecheckKeepSeparateExactModelObservations()
      async throws
    {
      let r = Resources()
      XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 9))
      await r.session.startInitialReview()
      for _ in 0..<5 {
        try await captureAndCheck(r)
        await r.session.advanceVisit()
      }
      let first = try XCTUnwrap(r.session.ledger?.initialRound)
      XCTAssertEqual(
        Set(r.processor.calls.map(\.entry.targetPhone)), Set(["B", "P", "M", "T", "D"]))
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
      XCTAssertEqual(
        r.processor.calls.map(\.id), first.rows.compactMap(\.firstSubmission?.operationID))
      for row in first.rows {
        XCTAssertEqual(
          r.session.researchModelNote(for: row),
          "Research model processed this take. Sound accuracy remains unverified.")
      }
      let selected = first.rows[1].entry
      let firstLedger = try XCTUnwrap(r.session.ledger)
      let firstDetails = try XCTUnwrap(r.session.researchDetails(
        workflowID: firstLedger.workflowID, entryID: selected.id))
      let firstSnapshot = try available(firstDetails.initial)
      XCTAssertEqual(firstSnapshot.identity, first.rows[1].firstSubmission)
      XCTAssertEqual(firstSnapshot.result,
        r.model.observations[firstSnapshot.identity.operationID]?.researchResult)
      assertUnavailable(firstDetails.recheck)
      XCTAssertNil(r.session.researchDetails(workflowID: UUID(), entryID: selected.id))
      XCTAssertNil(r.session.researchDetails(workflowID: firstLedger.workflowID, entryID: "foreign-entry"))
      XCTAssertEqual(r.processor.calls.count, 5)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.history.entries.isEmpty)
      r.session.togglePracticeSelection(entryID: selected.id)
      await r.session.startPractice()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      let practiceTry = try XCTUnwrap(r.session.media.latestTry?.id)
      XCTAssertFalse(first.rows.compactMap(\.firstSubmission?.tryID).contains(practiceTry))
      await r.session.advanceVisit()
      XCTAssertEqual(r.session.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(r.history.entries.map(\.soundID), [selected.soundID])
      XCTAssertEqual(r.processor.calls.count, 5)  // Practice never checks automatically.
      await r.session.startRecheck()
      for _ in 0..<5 {
        try await captureAndCheck(r)
        await r.session.advanceVisit()
      }
      let ledger = try XCTUnwrap(r.session.ledger)
      XCTAssertEqual(ledger.stage, .completed)
      XCTAssertEqual(ledger.initialRound, first)
      XCTAssertEqual(r.processor.calls.count, 10)
      XCTAssertEqual(Set(r.processor.calls.map(\.id)).count, 10)
      XCTAssertEqual(Set(r.model.observations.values.map(\.request.tryID)).count, 10)
      for pair in ledger.pairedRows {
        XCTAssertNotEqual(
          pair.initial.firstSubmission?.operationID, pair.recheck.firstSubmission?.operationID)
        XCTAssertNotEqual(pair.initial.firstSubmission?.tryID, pair.recheck.firstSubmission?.tryID)
        XCTAssertNotNil(r.session.researchModelNote(for: pair.initial))
        XCTAssertNotNil(r.session.researchModelNote(for: pair.recheck))
      }
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.files.protectedURLs.isEmpty)
      XCTAssertEqual(r.history.entries.count, 1)  // No model output enters history.
      let permissions = r.capture.permissionRequests
      for pair in ledger.pairedRows {
        let details = try XCTUnwrap(r.session.researchDetails(
          workflowID: ledger.workflowID, entryID: pair.entry.id))
        let initial = try available(details.initial), recheck = try available(details.recheck)
        XCTAssertEqual(initial.identity, pair.initial.firstSubmission)
        XCTAssertEqual(recheck.identity, pair.recheck.firstSubmission)
        XCTAssertEqual(initial.result.targets,
          r.model.observations[initial.identity.operationID]?.researchResult?.targets)
        XCTAssertEqual(recheck.result.targets,
          r.model.observations[recheck.identity.operationID]?.researchResult?.targets)
        XCTAssertFalse(details.contractsDiffer)
      }
      XCTAssertEqual(r.processor.calls.count, 10)
      XCTAssertEqual(r.capture.permissionRequests, permissions)
      XCTAssertEqual(r.history.entries.count, 1)
      await r.session.repeatReview()
      XCTAssertEqual(r.session.ledger?.workflowID, ledger.workflowID)
      XCTAssertNotEqual(r.session.ledger?.initialRound.id, ledger.initialRound.id)
      XCTAssertNil(r.session.researchDetails(workflowID: ledger.workflowID, entryID: selected.id))
      await r.session.finishStageNow()
      let repeated = try XCTUnwrap(r.session.researchDetails(
        workflowID: ledger.workflowID, entryID: selected.id))
      assertUnavailable(repeated.initial)
      assertUnavailable(repeated.recheck)
      XCTAssertEqual(r.processor.calls.count, 10)
      XCTAssertEqual(r.history.entries.count, 1)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertNil(r.session.researchDetails(workflowID: ledger.workflowID, entryID: selected.id))
    }

    func testModelFailureDoesNotChangeWordResultChoosePracticeOrStopLocalRecheck() async throws {
      let r = Resources()
      r.processor.fail = true
      XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 12))
      await r.session.startInitialReview()
      try await captureAndCheck(r)
      XCTAssertEqual(r.session.ledger?.initialRound.rows[0].state, .finished(.matched))
      XCTAssertTrue(r.model.modelCallsPaused)
      await r.session.advanceVisit()
      try await captureAndCheck(r)
      XCTAssertEqual(r.processor.calls.count, 1)
      XCTAssertEqual(r.session.ledger?.initialRound.rows[1].state, .finished(.matched))
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      await r.session.finishStageNow()
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.history.entries.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testSpecificRejectionNotesStayBoundToFirstReviewAndFreshRecheck() async throws {
      let r = Resources()
      let firstNote =
        "No signal was recorded in this take. Check the microphone input before making another recording."
      let recheckNote =
        "This take reached the recording’s digital level limit. Try moving a little farther from the microphone for another recording."
      r.processor.result = .unavailable(reason: "silence")
      XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 9))
      await r.session.startInitialReview()
      try await captureAndCheck(r)
      let initialRow = try XCTUnwrap(r.session.ledger?.initialRound.rows.first)
      let initialIdentity = try XCTUnwrap(initialRow.firstSubmission)
      let initialObservation = try XCTUnwrap(r.model.observations[initialIdentity.operationID])
      XCTAssertEqual(initialRow.state, .finished(.matched))
      XCTAssertEqual(r.session.researchModelNote(for: initialRow), firstNote)
      XCTAssertEqual(r.session.playerPresentation.modelObservationNote, firstNote)
      XCTAssertFalse(r.session.media.canCheckWordsInLatestTry)
      XCTAssertFalse(r.session.playerPresentation.canCheckWords)
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.processor.calls.count, 1)
      XCTAssertFalse(r.model.modelCallsPaused)
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
      await r.session.finishStageNow()
      let firstRound = try XCTUnwrap(r.session.ledger?.initialRound)
      XCTAssertEqual(r.session.ledger?.stage, .choosingPractice)
      r.session.togglePracticeSelection(entryID: initialRow.entry.id)
      await r.session.startPractice()
      XCTAssertTrue(r.session.playerPresentation.firstObservationNote?.hasSuffix(firstNote) == true)
      XCTAssertNil(r.session.playerPresentation.modelObservationNote)
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      XCTAssertEqual(r.processor.calls.count, 1)
      await r.session.advanceVisit()
      XCTAssertEqual(r.session.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(r.history.entries.map(\.soundID), [initialRow.entry.soundID])
      await r.session.startRecheck()
      XCTAssertTrue(r.session.playerPresentation.firstObservationNote?.hasSuffix(firstNote) == true)
      XCTAssertNil(r.session.playerPresentation.modelObservationNote)
      r.processor.result = .unavailable(reason: "clipping")
      try await captureAndCheck(r)
      let recheckRow = try XCTUnwrap(r.session.ledger?.recheckRound?.rows.first)
      let recheckIdentity = try XCTUnwrap(recheckRow.firstSubmission)
      XCTAssertEqual(recheckRow.state, .finished(.matched))
      XCTAssertNotEqual(initialIdentity.operationID, recheckIdentity.operationID)
      XCTAssertNotEqual(initialIdentity.tryID, recheckIdentity.tryID)
      XCTAssertEqual(r.session.researchModelNote(for: recheckRow), recheckNote)
      XCTAssertEqual(r.session.playerPresentation.modelObservationNote, recheckNote)
      XCTAssertTrue(r.session.playerPresentation.firstObservationNote?.hasSuffix(firstNote) == true)
      XCTAssertFalse(r.session.media.canCheckWordsInLatestTry)
      XCTAssertFalse(r.session.playerPresentation.canCheckWords)
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.processor.calls.count, 2)
      XCTAssertFalse(r.model.modelCallsPaused)

      // Each round needs its exact entry, take and submitted operation. Another
      // real observation in this session must never fill an identity mismatch.
      for (row, identity, other) in [
        (initialRow, initialIdentity, recheckIdentity),
        (recheckRow, recheckIdentity, initialIdentity),
      ] {
        let wrongEntry = LocalGuidedReviewRow(
          entry: r.session.setupEntries[1], visit: row.visit,
          firstSubmission: identity, state: row.state)
        XCTAssertNil(r.session.researchModelNote(for: wrongEntry))
        for (operationID, tryID) in [
          (identity.operationID, other.tryID), (other.operationID, identity.tryID),
          (UUID(), identity.tryID),
        ] {
          let wrongIdentity = LocalGuidedCheckIdentity(
            visit: identity.visit, operationID: operationID, tryID: tryID)
          let wrongRow = LocalGuidedReviewRow(
            entry: row.entry, visit: row.visit, firstSubmission: wrongIdentity, state: row.state)
          XCTAssertNil(r.session.researchModelNote(for: wrongRow))
        }
      }
      await r.session.finishStageNow()
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.session.ledger?.initialRound, firstRound)
      XCTAssertEqual(r.model.observations[initialIdentity.operationID], initialObservation)
      XCTAssertEqual(r.session.researchModelNote(for: initialRow), firstNote)
      XCTAssertEqual(r.session.researchModelNote(for: recheckRow), recheckNote)
      XCTAssertEqual(
        r.processor.calls.map(\.id), [initialIdentity.operationID, recheckIdentity.operationID])
      XCTAssertEqual(r.model.observations.count, 2)
      XCTAssertEqual(r.history.entries.count, 1)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.files.protectedURLs.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testUnreachableServiceKeepsFirstNoteAndAllowsFreshRecheckAfterManualPractice()
      async throws
    {
      let r = Resources()
      let firstNote =
        "The local research service could not be reached or confirmed. Start the service on this Mac before checking a later recording. You can continue manual practice."
      let laterNote = "Research model processed this take. Sound accuracy remains unverified."
      r.processor.ready = false
      XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 9))
      await r.session.startInitialReview()
      try await captureAndCheck(r)
      let initial = try XCTUnwrap(r.session.ledger?.initialRound.rows.first)
      let firstIdentity = try XCTUnwrap(initial.firstSubmission)
      let firstObservation = try XCTUnwrap(r.model.observations[firstIdentity.operationID])
      XCTAssertEqual(initial.state, .finished(.matched))
      XCTAssertEqual(r.session.researchModelNote(for: initial), firstNote)
      XCTAssertEqual(r.session.playerPresentation.modelObservationNote, firstNote)
      XCTAssertFalse(r.session.playerPresentation.canCheckWords)
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.processor.readinessCalls, 1)
      XCTAssertTrue(r.processor.calls.isEmpty)
      XCTAssertFalse(r.model.modelCallsPaused)
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
      await r.session.finishStageNow()
      let firstRound = try XCTUnwrap(r.session.ledger?.initialRound)
      r.session.togglePracticeSelection(entryID: initial.entry.id)
      await r.session.startPractice()
      XCTAssertTrue(r.session.playerPresentation.firstObservationNote?.hasSuffix(firstNote) == true)
      XCTAssertNil(r.session.playerPresentation.modelObservationNote)
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.advanceVisit()
      XCTAssertEqual(r.session.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(r.processor.readinessCalls, 1)
      XCTAssertTrue(r.processor.calls.isEmpty)
      XCTAssertEqual(r.history.entries.map(\.soundID), [initial.entry.soundID])
      r.processor.ready = true
      await r.session.startRecheck()
      XCTAssertNil(r.session.playerPresentation.modelObservationNote)
      try await captureAndCheck(r)
      let recheck = try XCTUnwrap(r.session.ledger?.recheckRound?.rows.first)
      let recheckIdentity = try XCTUnwrap(recheck.firstSubmission)
      XCTAssertNotEqual(firstIdentity.tryID, recheckIdentity.tryID)
      XCTAssertNotEqual(firstIdentity.operationID, recheckIdentity.operationID)
      XCTAssertEqual(r.session.researchModelNote(for: initial), firstNote)
      XCTAssertEqual(r.session.researchModelNote(for: recheck), laterNote)
      XCTAssertEqual(r.session.playerPresentation.modelObservationNote, laterNote)
      XCTAssertTrue(r.session.playerPresentation.firstObservationNote?.hasSuffix(firstNote) == true)
      let mismatched = LocalGuidedReviewRow(
        entry: recheck.entry, visit: recheck.visit,
        firstSubmission: .init(
          visit: recheckIdentity.visit,
          operationID: recheckIdentity.operationID, tryID: firstIdentity.tryID),
        state: recheck.state)
      XCTAssertNil(r.session.researchModelNote(for: mismatched))
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.processor.readinessCalls, 2)
      XCTAssertEqual(r.processor.calls.map(\.id), [recheckIdentity.operationID])
      await r.session.finishStageNow()
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.session.ledger?.initialRound, firstRound)
      XCTAssertEqual(r.model.observations[firstIdentity.operationID], firstObservation)
      XCTAssertFalse(r.model.modelCallsPaused)
      XCTAssertEqual(r.history.entries.count, 1)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.files.protectedURLs.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testDetailsKeepRepeatedTargetOrderAndExactFixtureProbabilities() throws {
      let fixture = try DetailsFixture()
      let snapshot = try available(fixture.resolve())
      XCTAssertEqual(snapshot.result, fixture.result)
      XCTAssertEqual(snapshot.result.targets.map(\.phoneIndex),
        try ResearchAssessmentClient.prompt(for: fixture.entry).targets.map(\.phoneIndex))
      XCTAssertEqual(snapshot.result.targets.map(\.subjectiveCorpusRatingProbabilities),
        [[0.1, 0.2, 0.7], [0.7, 0.2, 0.1]])
    }

    func testDetailsUnavailableThroughCoordinatorForLegacyAndMissingResultWithoutExtraWork() async throws {
      for outcome in [ResearchAssessmentOutcome.processedUnverified(milliseconds: 1),
        .unavailable(reason: "silence")]
      {
        let r = Resources()
        r.processor.result = outcome
        XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 9))
        await r.session.startInitialReview()
        try await captureAndCheck(r)
        await r.session.finishStageNow()
        let ledger = try XCTUnwrap(r.session.ledger), entry = ledger.entries[0]
        let details = try XCTUnwrap(r.session.researchDetails(
          workflowID: ledger.workflowID, entryID: entry.id))
        assertUnavailable(details.initial)
        assertUnavailable(details.recheck)
        XCTAssertEqual(r.processor.calls.count, 1)
        XCTAssertEqual(r.capture.retainedCount, 0)
        XCTAssertTrue(r.history.entries.isEmpty)
        XCTAssertEqual(ledger.initialRound.rows[0].state, .finished(.matched))
        let closed = await r.session.close()
        XCTAssertTrue(closed)
      }
    }

    func testDetailsRemainAbsentWhenResearchIsDisabled() async throws {
      let r = Resources()
      await r.session.startInitialReview()
      await r.session.finishStageNow()
      let ledger = try XCTUnwrap(r.session.ledger)
      XCTAssertNil(r.session.researchDetails(workflowID: ledger.workflowID, entryID: ledger.entries[0].id))
      XCTAssertTrue(r.processor.calls.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testDifferingPresentationContractsAreExplicitlyNotComparable() throws {
      let f = try DetailsFixture(), first = try available(f.resolve()), c = f.result.context
      let different = ResearchAssessmentResult(context: .init(operationID: UUID(),
        entryID: c.entryID, ageYears: 10, requestSHA256: c.requestSHA256,
        audioSHA256: c.audioSHA256, promptSHA256: c.promptSHA256), model: f.result.model,
        targets: f.result.targets, timingMilliseconds: f.result.timingMilliseconds)
      // Defensive presentation contract only: the frozen-age coordinator cannot admit this pair.
      let details = GuidedResearchDetailsPresentation(
        id: .init(workflowID: f.identity.visit.workflowID, entryID: f.entry.id), word: f.entry.prompt.word,
        initial: .available(first), recheck: .available(.init(identity: f.identity, result: different)))
      XCTAssertTrue(details.contractsDiffer)
    }

    func testDetailsRejectForeignObservationKeysOperationTakeEntryAndWord() throws {
      let f = try DetailsFixture()
      assertUnavailable(f.resolve(observations: [UUID(): f.observation]))
      let requests: [LocalWordRecognitionRequest] = [
        .init(operationID: UUID(), tryID: f.identity.tryID, fileURL: f.request.fileURL,
          expectedWord: f.entry.prompt.word),
        .init(operationID: f.identity.operationID, tryID: UUID(), fileURL: f.request.fileURL,
          expectedWord: f.entry.prompt.word),
        .init(operationID: f.identity.operationID, tryID: f.identity.tryID, fileURL: f.request.fileURL,
          expectedWord: "another word"),
      ]
      for request in requests {
        assertUnavailable(f.resolve(observations: [f.identity.operationID:
          .init(request: request, entryID: f.entry.id, outcome: f.observation.outcome,
            researchResult: f.result)]))
      }
      assertUnavailable(f.resolve(observations: [f.identity.operationID:
        .init(request: f.request, entryID: "foreign-entry", outcome: f.observation.outcome,
          researchResult: f.result)]))
    }

    func testDetailsRejectForeignWorkflowRoundVisitAndUnsettledRow() throws {
      let f = try DetailsFixture()
      assertUnavailable(f.resolve(workflowID: UUID()))
      assertUnavailable(f.resolve(roundID: UUID()))
      let foreignVisit = LocalGuidedReviewVisit(workflowID: f.identity.visit.workflowID,
        roundID: f.identity.visit.roundID, visitID: UUID(), entryID: f.entry.id)
      assertUnavailable(f.resolve(row: .init(entry: f.entry, visit: foreignVisit,
        firstSubmission: f.identity, state: .finished(.matched))))
      for state in [LocalGuidedReviewRowState.cleanupBlocked, .pending, .finished(.cancelled)] {
        assertUnavailable(f.resolve(row: .init(entry: f.entry, visit: f.identity.visit,
          firstSubmission: f.identity, state: state)))
      }
    }

    func testDetailsNeverTurnLegacyMissingCancelledOrCleanupFailureIntoValues() throws {
      let f = try DetailsFixture()
      for outcome in [
        GuidedResearchModelOutcome.processedUnverified(milliseconds: 1), .cancelled,
        .unavailable(.serverCleanupUnknown), .unavailable(.localCleanupUnconfirmed),
        .unavailable(.wordCleanupUnconfirmed), .notRun(.paused),
      ] {
        let payload = outcome == .processedUnverified(milliseconds: 1) ? nil : f.result
        assertUnavailable(f.resolve(observations: [f.identity.operationID:
          .init(request: f.request, entryID: f.entry.id, outcome: outcome, researchResult: payload)]))
      }
      assertUnavailable(f.resolve(observations: [:]))
    }

    func testDetailsRecheckResultContextModelAndTargetGeometry() throws {
      let f = try DetailsFixture(), c = f.result.context
      let contexts: [ResearchAssessmentResult.Context] = [
        .init(operationID: UUID(), entryID: c.entryID, ageYears: c.ageYears,
          requestSHA256: c.requestSHA256, audioSHA256: c.audioSHA256, promptSHA256: c.promptSHA256),
        .init(operationID: c.operationID, entryID: "foreign-entry", ageYears: c.ageYears,
          requestSHA256: c.requestSHA256, audioSHA256: c.audioSHA256, promptSHA256: c.promptSHA256),
        .init(operationID: c.operationID, entryID: c.entryID, ageYears: 10,
          requestSHA256: c.requestSHA256, audioSHA256: c.audioSHA256, promptSHA256: c.promptSHA256),
      ]
      var invalid = contexts.map { ResearchAssessmentResult(context: $0, model: f.result.model,
        targets: f.result.targets, timingMilliseconds: f.result.timingMilliseconds) }
      invalid.append(.init(context: c, model: .init(id: f.result.model.id, manifestSha256: "foreign"),
        targets: f.result.targets, timingMilliseconds: f.result.timingMilliseconds))
      invalid.append(.init(context: c, model: f.result.model, targets: Array(f.result.targets.reversed()),
        timingMilliseconds: f.result.timingMilliseconds))
      for result in invalid {
        assertUnavailable(f.resolve(observations: [f.identity.operationID:
          .init(request: f.request, entryID: f.entry.id, outcome: f.observation.outcome,
            researchResult: result)]))
      }
    }

    private func available(_ side: GuidedResearchDetailsPresentation.Side,
      file: StaticString = #filePath, line: UInt = #line)
      throws -> GuidedResearchDetailsPresentation.Snapshot
    {
      guard case .available(let snapshot) = side else {
        XCTFail("Expected bound fixture distribution, got \(side)", file: file, line: line)
        throw ResearchAssessmentError.invalidResponse
      }
      return snapshot
    }

    private func assertUnavailable(_ side: GuidedResearchDetailsPresentation.Side,
      file: StaticString = #filePath, line: UInt = #line)
    {
      guard case .unavailable(let reason) = side else {
        return XCTFail("Unexpected research distribution", file: file, line: line)
      }
      XCTAssertFalse(reason.isEmpty, file: file, line: line)
    }

    @MainActor
    private struct DetailsFixture {
      let entry: PracticeLibraryEntry
      let identity: LocalGuidedCheckIdentity
      let request: LocalWordRecognitionRequest
      let result: ResearchAssessmentResult
      var observation: GuidedResearchModelObservation {
        .init(request: request, entryID: entry.id, outcome: .processedUnverified(milliseconds: 1),
          researchResult: result)
      }
      init() throws {
        entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == "n-middle-banana" })
        identity = .init(visit: .init(workflowID: UUID(), roundID: UUID(), visitID: UUID(),
          entryID: entry.id), operationID: UUID(), tryID: UUID())
        // This URL deliberately has no file: presentation must never reopen audio.
        request = .init(operationID: identity.operationID, tryID: identity.tryID,
          fileURL: URL(fileURLWithPath: "/unopened-generated-details-fixture.wav"),
          expectedWord: entry.prompt.word)
        let context = try ResearchAssessmentClient.context(attemptId: identity.operationID,
          audio: Data([1, 2, 3]), entry: entry, ageYears: 9)
        let prompt = try ResearchAssessmentClient.prompt(for: entry)
        result = .init(context: context,
          model: .init(id: "ages-6-12-research-mixture", manifestSha256: ResearchAssessmentClient.manifest),
          targets: prompt.targets.enumerated().map { index, target in
            .init(id: target.id, wordIndex: target.wordIndex, phoneIndex: target.phoneIndex,
              targetPhone: target.targetPhone,
              subjectiveCorpusRatingProbabilities: index == 0 ? [0.1, 0.2, 0.7] : [0.7, 0.2, 0.1])
          }, timingMilliseconds: .init(total: 1, inference: 1))
      }
      func resolve(row: LocalGuidedReviewRow? = nil, workflowID: UUID? = nil, roundID: UUID? = nil,
        observations: [UUID: GuidedResearchModelObservation]? = nil)
        -> GuidedResearchDetailsPresentation.Side
      {
        .resolve(row: row ?? .init(entry: entry, visit: identity.visit, firstSubmission: identity,
          state: .finished(.matched)), workflowID: workflowID ?? identity.visit.workflowID,
          roundID: roundID ?? identity.visit.roundID, entry: entry, ageYears: 9,
          observations: observations ?? [identity.operationID: observation])
      }
    }

    func testSynchronousModelHandoffCloseOrBackgroundStartsNoProcessorAndCleansOwnedTake() async throws {
      for close in [true, false] {
        let r = Resources()
        XCTAssertTrue(r.session.configureResearchModel(enabled: true, ageYears: 9))
        await r.session.startInitialReview()
        await r.session.media.startRecording()
        r.session.media.stopRecording()
        let take = try XCTUnwrap(r.session.media.latestTry)
        var revoked = false
        let subscription = r.model.$processingState.sink { state in
          MainActor.assumeIsolated {
            if case .processingModel = state, !revoked {
              revoked = true
              if close { r.session.media.viewDidDisappear() }
              else { r.session.media.appDidEnterBackground() }
            }
          }
        }
        await r.session.checkCurrentWord()
        let deadline = ContinuousClock.now.advanced(by: .seconds(2))
        while (!r.session.media.tries.isEmpty || r.session.media.isTransitioning),
          ContinuousClock.now < deadline { await Task.yield() }
        XCTAssertTrue(revoked)
        XCTAssertEqual(r.processor.readinessCalls, 1)
        XCTAssertTrue(r.processor.calls.isEmpty)
        XCTAssertEqual(r.capture.permissionRequests, 1)
        XCTAssertEqual(r.capture.returnedURLs.count, 1)
        XCTAssertTrue(r.session.media.tries.isEmpty)
        XCTAssertTrue(r.files.protectedURLs.isEmpty)
        XCTAssertFalse(r.model.observations.values.contains {
          $0.request.tryID == take.id && $0.researchResult != nil
        })
        XCTAssertTrue(r.history.entries.isEmpty)
        subscription.cancel()
        let closed = await r.session.close()
        XCTAssertTrue(closed)
      }
    }

    private func captureAndCheck(_ r: Resources) async throws {
      let modelCallsBeforeRecording = r.processor.calls.count
      let readinessBeforeRecording = r.processor.readinessCalls
      await r.session.media.startRecording()
      XCTAssertEqual(r.session.media.phase, .recording)
      r.session.media.stopRecording()
      let take = try XCTUnwrap(r.session.media.latestTry)
      XCTAssertEqual(r.processor.calls.count, modelCallsBeforeRecording)
      XCTAssertEqual(r.processor.readinessCalls, readinessBeforeRecording)
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.session.media.wordCheckState, .finished(.matched))
      if r.processor.calls.count == modelCallsBeforeRecording + 1 {
        let call = try XCTUnwrap(r.processor.calls.last)
        XCTAssertEqual(call.recording.summary, take.summary)
        XCTAssertEqual(call.recording.url, r.capture.returnedURLs.last)
        XCTAssertEqual(call.recording.summary.averagePower, -12)
        XCTAssertTrue(r.files.canRemove(call.recording.url,
          owner: try XCTUnwrap(call.recording.cleanupOwnerID)))
      }
    }

    private final class Processor: ResearchAssessmentReadinessChecking {
      struct Call {
        let id: UUID
        let entry: PracticeLibraryEntry
        let age: Int
        let url: URL
        let recording: CapturedRecording
      }
      var calls: [Call] = []
      var fail = false
      var files: ProcessAudioFileOwnership?
      var result: ResearchAssessmentOutcome?
      var ready = true
      var readinessCalls = 0
      func checkReadiness() async -> Bool {
        readinessCalls += 1
        return ready
      }
      func process(
        attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
      ) async throws -> ResearchAssessmentOutcome {
        XCTAssertTrue(FileManager.default.fileExists(atPath: recording.url.path))
        calls.append(.init(id: attemptId, entry: entry, age: ageYears, url: recording.url))
        if fail { throw ResearchAssessmentError.serviceUnavailable }
        return result
      }
    }

    @MainActor
    private final class Resources {
      let files = ProcessAudioFileOwnership()
      let history: PracticeParticipationStore
      let capture: LocalGuidedGeneratedCapture
      let processor = Processor()
      let model: GuidedResearchModelRecognizer
      let session: LocalGuidedReviewSession
      init() {
        let hardware = AudioHardwareOwnership()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "guided-model-flow-\(UUID())")
        history = PracticeParticipationStore(
          fileURL: directory.appendingPathComponent("history.json"))
        capture = LocalGuidedGeneratedCapture(hardware: hardware, files: files)
        let word = LocalGuidedGeneratedRecognizer(files: files, holdsResult: false)
        model = GuidedResearchModelRecognizer(
          wordRecognizer: word, processor: processor, ownership: files,
          availability: GuidedResearchModelAvailability())
        let player = ResearchAcknowledgedPlaybackUITestFixture(
          completion: .explicitStop, ownership: hardware, fileOwnership: files)
        let media = DirectPracticeSession(
          capturer: capture, player: player, history: history, managedForGuided: true,
          wordRecognizer: model, cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
        session = LocalGuidedReviewSession(history: history, media: media, researchModel: model)
      }
    }
  }
#endif
