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
      let closed = await r.session.close()
      XCTAssertTrue(closed)
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

    private func captureAndCheck(_ r: Resources) async throws {
      let modelCallsBeforeRecording = r.processor.calls.count
      let readinessBeforeRecording = r.processor.readinessCalls
      await r.session.media.startRecording()
      XCTAssertEqual(r.session.media.phase, .recording)
      r.session.media.stopRecording()
      _ = try XCTUnwrap(r.session.media.latestTry)
      XCTAssertEqual(r.processor.calls.count, modelCallsBeforeRecording)
      XCTAssertEqual(r.processor.readinessCalls, readinessBeforeRecording)
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.session.media.wordCheckState, .finished(.matched))
    }

    private final class Processor: ResearchAssessmentReadinessChecking {
      struct Call {
        let id: UUID
        let entry: PracticeLibraryEntry
        let age: Int
        let url: URL
      }
      var calls: [Call] = []
      var fail = false
      var result: ResearchAssessmentOutcome = .processedUnverified(milliseconds: 1)
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
