import Foundation
import XCTest

@testable import CadenceLearner

final class LocalGuidedReviewLedgerTests: XCTestCase {
  private let starters = [
    "b-beginning-ball", "p-beginning-pig", "m-beginning-moon",
    "t-beginning-tiger", "d-beginning-dog",
  ]

  func testFiveCanonicalWordsFreezeOrderAndTheirOwnSoundPosition() throws {
    let ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    XCTAssertEqual(ledger.entries.map(\.id), starters)
    XCTAssertEqual(ledger.entries.map { $0.prompt.word }, ["ball", "pig", "moon", "tiger", "dog"])
    XCTAssertEqual(ledger.entries.map(\.soundID), ["b", "p", "m", "t", "d"])
    XCTAssertTrue(ledger.entries.allSatisfy { $0.position == .beginning })
    XCTAssertEqual(ledger.initialRound.rows.map(\.state), Array(repeating: .notVisited, count: 5))
    XCTAssertFalse(ledger.initialRound.isFinished)
    XCTAssertNil(ledger.activeReviewVisit)
    XCTAssertTrue(ledger.selectedPracticeEntryIDs.isEmpty)
    XCTAssertNil(ledger.recheckRound)
  }

  func testPlanRejectsWrongCountUnknownEntryAndSamePrintedWordAcrossSoundEntries() throws {
    XCTAssertThrowsError(try LocalGuidedReviewLedger(entryIDs: Array(starters.prefix(4))))
    XCTAssertThrowsError(try LocalGuidedReviewLedger(entryIDs: starters + ["y-beginning-yo-yo"]))
    XCTAssertThrowsError(
      try LocalGuidedReviewLedger(entryIDs: ["missing"] + Array(starters.dropFirst())))
    let repeated = ["r-beginning-ring", "ng-end-ring"] + Array(starters.prefix(3))
    XCTAssertThrowsError(try LocalGuidedReviewLedger(entryIDs: repeated)) {
      XCTAssertEqual($0 as? LocalGuidedReviewLedger.PlanError, .duplicatePrintedWord)
    }
    let id = UUID()
    XCTAssertThrowsError(
      try LocalGuidedReviewLedger(
        entryIDs: starters, workflowID: id, initialRoundID: id))
  }

  func testEveryActualSoundGroupCanSupplyACanonicalReviewEntryIncludingZH() throws {
    for sound in PracticeLibrary.sounds {
      let entry = try XCTUnwrap(PracticeLibrary.entries(soundID: sound.id).first)
      let remainder = PracticeLibrary.entries().filter { $0.prompt.word != entry.prompt.word }
      var chosen = [entry]
      for candidate in remainder
      where !chosen.contains(where: { $0.prompt.word == candidate.prompt.word }) {
        chosen.append(candidate)
        if chosen.count == 5 { break }
      }
      let ledger = try LocalGuidedReviewLedger(entryIDs: chosen.map(\.id))
      XCTAssertEqual(ledger.entries.first, entry)
      XCTAssertEqual(ledger.entries.first?.soundID, sound.id)
      XCTAssertEqual(ledger.entries.first?.position, entry.position)
    }
  }

  func testFirstSubmissionAndTerminalResultIgnoreWrongDuplicateAndLateIdentities() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let visit = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    let accepted = LocalGuidedCheckIdentity(visit: visit, operationID: UUID(), tryID: UUID())
    let wrong = wrongIdentities(for: accepted)
    for identity in wrong.prefix(4) {
      XCTAssertFalse(ledger.receive(.submitted(identity)))
      XCTAssertEqual(ledger.initialRound.rows[0].state, .ready)
    }
    XCTAssertTrue(ledger.receive(.submitted(accepted)))
    XCTAssertFalse(ledger.receive(.submitted(accepted)))
    XCTAssertFalse(
      ledger.receive(.submitted(.init(visit: visit, operationID: UUID(), tryID: UUID()))))
    for identity in wrong {
      XCTAssertFalse(
        ledger.receive(
          .settled(
            identity: identity, status: .matched, resultEligible: true, cleanupConfirmed: true)))
      XCTAssertEqual(ledger.initialRound.rows[0].state, .pending)
    }
    XCTAssertTrue(
      ledger.receive(
        .settled(
          identity: accepted, status: .notMatched, resultEligible: true, cleanupConfirmed: true)))
    let first = ledger.initialRound.rows[0]
    XCTAssertEqual(first.firstSubmission, accepted)
    XCTAssertEqual(first.state, .finished(.notMatched))
    XCTAssertFalse(
      ledger.receive(
        .settled(
          identity: accepted, status: .matched, resultEligible: true, cleanupConfirmed: true)))
    XCTAssertTrue(ledger.leaveReviewVisit(visit, cleanupConfirmed: true))
    _ = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    XCTAssertFalse(
      ledger.receive(
        .settled(
          identity: accepted, status: .matched, resultEligible: true, cleanupConfirmed: true)))
    XCTAssertEqual(ledger.initialRound.rows[0], first)
  }

  func testPendingAndUnknownCleanupCannotBecomeSummarySkipOrTerminalResult() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let visit = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    let identity = LocalGuidedCheckIdentity(visit: visit, operationID: UUID(), tryID: UUID())
    XCTAssertFalse(
      ledger.receive(
        .settled(
          identity: identity, status: .matched, resultEligible: true, cleanupConfirmed: true)))
    XCTAssertTrue(ledger.receive(.submitted(identity)))
    XCTAssertFalse(ledger.leaveReviewVisit(visit, cleanupConfirmed: true))
    XCTAssertFalse(ledger.skipReviewVisit(visit, cleanupConfirmed: true))
    XCTAssertFalse(
      ledger.finishReviewNow(
        roundID: visit.roundID, visitID: visit.visitID, cleanupConfirmed: true))
    XCTAssertTrue(
      ledger.receive(
        .settled(
          identity: identity, status: .unavailable, resultEligible: false, cleanupConfirmed: false))
    )
    XCTAssertEqual(ledger.initialRound.rows[0].state, .cleanupBlocked)
    XCTAssertEqual(ledger.initialRound.rows[0].firstSubmission, identity)
    XCTAssertFalse(
      ledger.receive(
        .settled(
          identity: identity, status: .matched, resultEligible: true, cleanupConfirmed: true)))
    XCTAssertFalse(
      ledger.finishReviewNow(
        roundID: visit.roundID, visitID: visit.visitID, cleanupConfirmed: true))
    XCTAssertNil(ledger.beginReviewVisit(visitID: UUID()))
    XCTAssertFalse(ledger.initialRound.isFinished)
    XCTAssertEqual(ledger.stage, .initialReview)
  }

  func testLostEligibilityBecomesCancelledOnlyAfterExactAcknowledgedSettlement() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let visit = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    let identity = LocalGuidedCheckIdentity(visit: visit, operationID: UUID(), tryID: UUID())
    XCTAssertTrue(ledger.receive(.submitted(identity)))
    XCTAssertFalse(ledger.leaveReviewVisit(visit, cleanupConfirmed: false))
    XCTAssertEqual(ledger.initialRound.rows[0].state, .pending)
    XCTAssertTrue(
      ledger.receive(
        .settled(
          identity: identity, status: .matched, resultEligible: false, cleanupConfirmed: true)))
    XCTAssertEqual(ledger.initialRound.rows[0].state, .finished(.cancelled))
    XCTAssertTrue(ledger.leaveReviewVisit(visit, cleanupConfirmed: true))
  }

  func testAllFiveFirstObservationsRemainDistinctWithoutAutomaticPracticeSelection() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    _ = try completeInitial(&ledger)
    XCTAssertEqual(
      ledger.initialRound.rows.map(\.state),
      [
        .finished(.matched), .finished(.notMatched), .finished(.uncertain),
        .finished(.unavailable), .finished(.cancelled),
      ])
    XCTAssertTrue(ledger.initialRound.isFinished)
    XCTAssertEqual(ledger.stage, .choosingPractice)
    XCTAssertTrue(ledger.practiceRows.isEmpty)
    XCTAssertNil(ledger.activeReviewVisit)
    XCTAssertNil(ledger.activePracticeVisit)
    XCTAssertFalse(ledger.beginRecheck(roundID: UUID()))
  }

  func testFirstReviewNoteUsesExactFrozenEntryAndNamesOnlyWordObservations() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    XCTAssertNil(LocalGuidedReviewSession.firstReviewNote(for: starters[0], in: ledger))
    _ = try completeInitial(&ledger)
    let expected = [
      "Word matched", "No word match", "No clear match", "Check unavailable",
      "Check cancelled",
    ]
    for (entryID, observation) in zip(starters, expected) {
      XCTAssertEqual(
        LocalGuidedReviewSession.firstReviewNote(for: entryID, in: ledger),
        "First review: \(observation). Word checks cannot identify which sound was made.")
    }
    XCTAssertNil(LocalGuidedReviewSession.firstReviewNote(for: "missing", in: ledger))
    XCTAssertNil(
      LocalGuidedReviewSession.firstReviewNote(for: "r-beginning-ring", in: ledger))

    var sharedWord = try LocalGuidedReviewLedger(
      entryIDs: ["r-beginning-ring"] + Array(starters.dropFirst()))
    let visit = try XCTUnwrap(sharedWord.beginReviewVisit(visitID: UUID()))
    XCTAssertTrue(sharedWord.skipReviewVisit(visit, cleanupConfirmed: true))
    let next = try XCTUnwrap(sharedWord.beginReviewVisit(visitID: UUID()))
    XCTAssertTrue(
      sharedWord.finishReviewNow(
        roundID: next.roundID, visitID: next.visitID, cleanupConfirmed: true))
    XCTAssertEqual(
      LocalGuidedReviewSession.firstReviewNote(for: "r-beginning-ring", in: sharedWord),
      "First review: Skipped. Word checks cannot identify which sound was made.")
    XCTAssertEqual(
      LocalGuidedReviewSession.firstReviewNote(for: starters[2], in: sharedWord),
      "First review: Not reached. Word checks cannot identify which sound was made.")
    XCTAssertNil(
      LocalGuidedReviewSession.firstReviewNote(for: "ng-end-ring", in: sharedWord))
  }

  func testTimedOutFirstReviewRemainsFrozenWhenFreshRecheckMatches() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let identity = try settleCurrent(&ledger, status: .timedOut)
    let first = ledger.initialRound.rows[0]
    XCTAssertEqual(first.state, .finished(.timedOut))
    XCTAssertEqual(first.firstSubmission, identity)
    XCTAssertEqual(LocalGuidedReviewDisposition.timedOut.wordObservation, "Word check took too long")
    XCTAssertFalse(
      ledger.receive(
        .settled(
          identity: identity, status: .matched, resultEligible: true, cleanupConfirmed: true)))
    XCTAssertTrue(ledger.leaveReviewVisit(identity.visit, cleanupConfirmed: true))
    let next = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    XCTAssertTrue(
      ledger.finishReviewNow(
        roundID: next.roundID, visitID: next.visitID, cleanupConfirmed: true))
    XCTAssertEqual(
      LocalGuidedReviewSession.firstReviewNote(for: starters[0], in: ledger),
      "First review: Word check took too long. Word checks cannot identify which sound was made.")
    XCTAssertTrue(ledger.selectedPracticeEntryIDs.isEmpty)
    _ = try skipOnePractice(&ledger)
    XCTAssertTrue(ledger.beginRecheck(roundID: UUID()))
    let recheck = try settleCurrent(&ledger, status: .matched)
    XCTAssertNotEqual(recheck.operationID, identity.operationID)
    XCTAssertNotEqual(recheck.tryID, identity.tryID)
    XCTAssertEqual(ledger.recheckRound?.rows[0].state, .finished(.matched))
    XCTAssertEqual(ledger.initialRound.rows[0], first)
  }

  func testEarlyReviewKeepsSettledPrefixMarksVisitedSkipAndUnvisitedSuffixUnreached() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let first = try settleCurrent(&ledger, status: .matched)
    XCTAssertTrue(ledger.leaveReviewVisit(first.visit, cleanupConfirmed: true))
    let second = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    XCTAssertFalse(
      ledger.finishReviewNow(
        roundID: UUID(), visitID: second.visitID, cleanupConfirmed: true))
    XCTAssertFalse(
      ledger.finishReviewNow(
        roundID: second.roundID, visitID: UUID(), cleanupConfirmed: true))
    XCTAssertFalse(
      ledger.finishReviewNow(
        roundID: second.roundID, visitID: second.visitID, cleanupConfirmed: false))
    XCTAssertTrue(
      ledger.finishReviewNow(
        roundID: second.roundID, visitID: second.visitID, cleanupConfirmed: true))
    XCTAssertEqual(
      ledger.initialRound.rows.map(\.state),
      [
        .finished(.matched), .finished(.skipped), .finished(.unreached),
        .finished(.unreached), .finished(.unreached),
      ])
    XCTAssertEqual(ledger.initialRound.rows[0].firstSubmission, first)
    XCTAssertEqual(ledger.initialRound.rows[1].visit, second)
    XCTAssertNil(ledger.initialRound.rows[2].visit)
    XCTAssertNil(ledger.initialRound.rows[2].firstSubmission)
    XCTAssertEqual(ledger.stage, .choosingPractice)
    var unopened = try LocalGuidedReviewLedger(entryIDs: starters)
    XCTAssertTrue(
      unopened.finishReviewNow(
        roundID: unopened.initialRound.id, visitID: nil, cleanupConfirmed: true))
    XCTAssertTrue(unopened.initialRound.rows.allSatisfy { $0.state == .finished(.unreached) })
  }

  func testPracticeRequiresOneToThreeUserChoicesAndKeepsTheirOrderRegardlessOfResults() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    XCTAssertFalse(ledger.beginPractice(entryIDs: [starters[0]], practiceID: UUID()))
    _ = try completeInitial(&ledger)
    for invalid in [[], Array(starters.prefix(4)), [starters[0], starters[0]], ["missing"]] {
      XCTAssertFalse(ledger.beginPractice(entryIDs: invalid, practiceID: UUID()))
      XCTAssertEqual(ledger.stage, .choosingPractice)
      XCTAssertTrue(ledger.selectedPracticeEntryIDs.isEmpty)
    }
    let initial = ledger.initialRound
    let chosen = [starters[4], starters[2], starters[1]]
    XCTAssertTrue(ledger.beginPractice(entryIDs: chosen, practiceID: UUID()))
    XCTAssertEqual(ledger.selectedPracticeEntryIDs, chosen)
    XCTAssertEqual(ledger.practiceRows.map { $0.entry.soundID }, ["d", "m", "p"])
    XCTAssertTrue(ledger.practiceRows.allSatisfy { $0.state == .notVisited })
    XCTAssertNil(ledger.activePracticeVisit)
    XCTAssertEqual(ledger.initialRound, initial)
  }

  func testPracticeCompletionNeedsFreshTakeAndCleanupAndSaveRetryKeepsExactVisit() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let initialChecks = try completeInitial(&ledger)
    let initial = ledger.initialRound
    XCTAssertTrue(ledger.beginPractice(entryIDs: [starters[3]], practiceID: UUID()))
    XCTAssertNil(ledger.beginPracticeVisit(visitID: initialChecks[0].visit.visitID))
    let visit = try XCTUnwrap(ledger.beginPracticeVisit(visitID: UUID()))
    XCTAssertFalse(
      ledger.finishPracticeVisit(
        visit, disposition: .finished, freshTryID: nil, cleanupConfirmed: true))
    XCTAssertFalse(
      ledger.finishPracticeVisit(
        visit, disposition: .finished, freshTryID: initialChecks[0].tryID, cleanupConfirmed: true))
    let freshTry = UUID()
    XCTAssertFalse(
      ledger.finishPracticeVisit(
        visit, disposition: .finished, freshTryID: freshTry, cleanupConfirmed: false))
    XCTAssertTrue(
      ledger.finishPracticeVisit(
        visit, disposition: .saveUnconfirmed, freshTryID: freshTry, cleanupConfirmed: true))
    XCTAssertEqual(ledger.practiceRows[0].state, .finished(.saveUnconfirmed))
    XCTAssertEqual(ledger.practiceRows[0].freshTryID, freshTry)
    XCTAssertFalse(ledger.acknowledgePracticeSaved(visit, completionID: UUID()))
    XCTAssertTrue(ledger.acknowledgePracticeSaved(visit, completionID: visit.visitID))
    XCTAssertFalse(ledger.acknowledgePracticeSaved(visit, completionID: visit.visitID))
    XCTAssertEqual(ledger.practiceRows[0].state, .finished(.finished))
    XCTAssertEqual(ledger.practiceRows[0].freshTryID, freshTry)
    XCTAssertEqual(ledger.practiceRows[0].entry.id, starters[3])
    XCTAssertFalse(ledger.leavePracticeVisit(visit, cleanupConfirmed: false))
    XCTAssertTrue(ledger.leavePracticeVisit(visit, cleanupConfirmed: true))
    XCTAssertFalse(ledger.acknowledgePracticeSaved(visit, completionID: visit.visitID))
    XCTAssertEqual(ledger.stage, .readyToRecheck)
    XCTAssertEqual(ledger.initialRound, initial)
  }

  func testEarlyPracticePreservesUnconfirmedSaveAndDistinguishesSkippedFromUnreached() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    _ = try completeInitial(&ledger)
    let initial = ledger.initialRound
    let practiceID = UUID()
    XCTAssertTrue(ledger.beginPractice(entryIDs: Array(starters.prefix(3)), practiceID: practiceID))
    let first = try XCTUnwrap(ledger.beginPracticeVisit(visitID: UUID()))
    XCTAssertTrue(
      ledger.finishPracticeVisit(
        first, disposition: .saveUnconfirmed, freshTryID: UUID(), cleanupConfirmed: true))
    XCTAssertTrue(ledger.leavePracticeVisit(first, cleanupConfirmed: true))
    let second = try XCTUnwrap(ledger.beginPracticeVisit(visitID: UUID()))
    XCTAssertFalse(ledger.acknowledgePracticeSaved(first, completionID: first.visitID))
    XCTAssertFalse(
      ledger.finishPracticeNow(
        practiceID: practiceID, visitID: second.visitID, cleanupConfirmed: false))
    XCTAssertFalse(
      ledger.finishPracticeNow(
        practiceID: UUID(), visitID: second.visitID, cleanupConfirmed: true))
    XCTAssertTrue(
      ledger.finishPracticeNow(
        practiceID: practiceID, visitID: second.visitID, cleanupConfirmed: true))
    XCTAssertEqual(
      ledger.practiceRows.map(\.state),
      [
        .finished(.saveUnconfirmed), .finished(.skipped), .finished(.unreached),
      ])
    XCTAssertEqual(ledger.practiceRows[0].visit, first)
    XCTAssertEqual(ledger.practiceRows[1].visit, second)
    XCTAssertNil(ledger.practiceRows[2].visit)
    XCTAssertNil(ledger.practiceRows[1].freshTryID)
    XCTAssertNil(ledger.practiceRows[2].freshTryID)
    XCTAssertEqual(ledger.initialRound, initial)
  }

  func testRecheckKeepsSameFiveOrderAndRejectsEveryReusedInitialIdentity() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    let initialChecks = try completeInitial(&ledger)
    let initial = ledger.initialRound
    let practiceID = try skipOnePractice(&ledger)
    for old in [ledger.workflowID, initial.id, practiceID, initialChecks[0].operationID] {
      XCTAssertFalse(ledger.beginRecheck(roundID: old))
    }
    let recheckID = UUID()
    XCTAssertTrue(ledger.beginRecheck(roundID: recheckID))
    XCTAssertEqual(ledger.recheckRound?.rows.map { $0.entry.id }, starters)
    for old in initialChecks.flatMap({ [$0.visit.visitID, $0.tryID, $0.operationID] }) {
      XCTAssertNil(ledger.beginReviewVisit(visitID: old))
    }
    let visit = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    XCTAssertEqual(visit.roundID, recheckID)
    XCTAssertFalse(
      ledger.receive(
        .submitted(
          .init(
            visit: visit, operationID: UUID(), tryID: initialChecks[0].tryID))))
    XCTAssertFalse(
      ledger.receive(
        .submitted(
          .init(
            visit: visit, operationID: initialChecks[0].operationID, tryID: UUID()))))
    let same = UUID()
    XCTAssertFalse(ledger.receive(.submitted(.init(visit: visit, operationID: same, tryID: same))))
    let check = LocalGuidedCheckIdentity(visit: visit, operationID: UUID(), tryID: UUID())
    XCTAssertTrue(ledger.receive(.submitted(check)))
    XCTAssertFalse(
      ledger.receive(
        .settled(
          identity: initialChecks[0], status: .matched, resultEligible: true, cleanupConfirmed: true
        )))
    XCTAssertEqual(ledger.recheckRound?.rows[0].state, .pending)
    XCTAssertEqual(ledger.initialRound, initial)
  }

  func testPairedPartialRecheckHasFiveIndependentRowsAndNeverChangesInitialRound() throws {
    var ledger = try LocalGuidedReviewLedger(entryIDs: starters)
    _ = try completeInitial(&ledger)
    let initial = ledger.initialRound
    _ = try skipOnePractice(&ledger)
    let roundID = UUID()
    XCTAssertTrue(ledger.beginRecheck(roundID: roundID))
    let first = try settleCurrent(&ledger, status: .unavailable)
    XCTAssertTrue(ledger.leaveReviewVisit(first.visit, cleanupConfirmed: true))
    let second = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    XCTAssertTrue(
      ledger.finishReviewNow(
        roundID: roundID, visitID: second.visitID, cleanupConfirmed: true))
    XCTAssertEqual(ledger.stage, .completed)
    XCTAssertEqual(ledger.initialRound, initial)
    XCTAssertEqual(ledger.pairedRows.map { $0.entry.id }, starters)
    XCTAssertEqual(ledger.pairedRows.map { $0.initial.state }, initial.rows.map(\.state))
    XCTAssertEqual(
      ledger.pairedRows.map { $0.recheck.state },
      [
        .finished(.unavailable), .finished(.skipped), .finished(.unreached),
        .finished(.unreached), .finished(.unreached),
      ])
    XCTAssertEqual(ledger.recheckRound?.rows[0].firstSubmission, first)
    XCTAssertFalse(ledger.beginRecheck(roundID: UUID()))
    XCTAssertNil(ledger.beginReviewVisit(visitID: UUID()))
  }

  private func completeInitial(_ ledger: inout LocalGuidedReviewLedger) throws
    -> [LocalGuidedCheckIdentity]
  {
    var checks: [LocalGuidedCheckIdentity] = []
    for status in [
      LocalWordRecognitionStatus.matched, .notMatched, .uncertain, .unavailable, .cancelled,
    ] {
      let check = try settleCurrent(&ledger, status: status)
      checks.append(check)
      XCTAssertTrue(ledger.leaveReviewVisit(check.visit, cleanupConfirmed: true))
    }
    return checks
  }

  private func settleCurrent(
    _ ledger: inout LocalGuidedReviewLedger, status: LocalWordRecognitionStatus
  ) throws -> LocalGuidedCheckIdentity {
    let visit = try XCTUnwrap(ledger.beginReviewVisit(visitID: UUID()))
    let check = LocalGuidedCheckIdentity(visit: visit, operationID: UUID(), tryID: UUID())
    XCTAssertTrue(ledger.receive(.submitted(check)))
    XCTAssertTrue(
      ledger.receive(
        .settled(
          identity: check, status: status, resultEligible: true, cleanupConfirmed: true)))
    return check
  }

  private func skipOnePractice(_ ledger: inout LocalGuidedReviewLedger) throws -> UUID {
    let id = UUID()
    XCTAssertTrue(ledger.beginPractice(entryIDs: [starters[0]], practiceID: id))
    let visit = try XCTUnwrap(ledger.beginPracticeVisit(visitID: UUID()))
    XCTAssertTrue(
      ledger.finishPracticeVisit(
        visit, disposition: .skipped, freshTryID: nil, cleanupConfirmed: true))
    XCTAssertTrue(ledger.leavePracticeVisit(visit, cleanupConfirmed: true))
    return id
  }

  private func wrongIdentities(for value: LocalGuidedCheckIdentity) -> [LocalGuidedCheckIdentity] {
    let visit = value.visit
    let visits = [
      LocalGuidedReviewVisit(
        workflowID: UUID(), roundID: visit.roundID, visitID: visit.visitID, entryID: visit.entryID),
      LocalGuidedReviewVisit(
        workflowID: visit.workflowID, roundID: UUID(), visitID: visit.visitID,
        entryID: visit.entryID),
      LocalGuidedReviewVisit(
        workflowID: visit.workflowID, roundID: visit.roundID, visitID: UUID(),
        entryID: visit.entryID),
      LocalGuidedReviewVisit(
        workflowID: visit.workflowID, roundID: visit.roundID, visitID: visit.visitID,
        entryID: starters[1]),
    ]
    return visits.map { .init(visit: $0, operationID: value.operationID, tryID: value.tryID) } + [
      .init(visit: visit, operationID: UUID(), tryID: value.tryID),
      .init(visit: visit, operationID: value.operationID, tryID: UUID()),
    ]
  }
}
