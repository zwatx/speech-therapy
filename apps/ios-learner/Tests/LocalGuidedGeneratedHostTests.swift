#if DEBUG && targetEnvironment(simulator)
  import Combine
  import XCTest
  @testable import CadenceLearner

  /// Generated protocol/runtime integration only; no sensor or model execution.
  @MainActor
  final class LocalGuidedGeneratedHostTests: XCTestCase {
    func testGeneratedPracticeTimeoutRetrySeedsThenHoldsExactSameTakeWithoutModelWork()
      async throws
    {
      let r = LocalGuidedGeneratedResources(testCase: .practiceTimeoutRetry, runID: UUID())
      await r.prepareSeed()
      guard case .ready = r.seedState else {
        _ = await r.session.close()
        XCTFail("Timeout-retry seed must be ready")
        return
      }
      XCTAssertEqual(r.recognizer.requests.count, 5)
      XCTAssertFalse(r.recognizer.isPending)
      XCTAssertEqual(r.recognizer.borrowCount, 0)
      XCTAssertEqual(r.capture.createdURLs.count, 5)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertEqual(r.modelLine, "Generated model calls: 0")
      let initial = try XCTUnwrap(r.session.ledger?.initialRound)
      XCTAssertTrue(initial.rows.allSatisfy { $0.state == .finished(.matched) })
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      let pig = r.session.setupEntries[1].id
      r.session.togglePracticeSelection(entryID: pig)
      await r.session.startPractice()
      let visit = try XCTUnwrap(r.session.ledger?.activePracticeVisit)
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      let take = try XCTUnwrap(r.session.media.latestTry)
      let firstTask = Task { await r.session.checkCurrentWord() }
      guard await waitForTimeoutRetryPending(r.recognizer, count: 6) else {
        r.session.media.cancelWordCheck()
        r.recognizer.stopGeneratedChecks()
        await firstTask.value
        _ = await r.session.close()
        XCTFail("Generated first timeout request did not become pending")
        return
      }
      let firstRequest = r.recognizer.requests.last
      XCTAssertEqual(r.recognizer.requests.count, 6)
      XCTAssertEqual(r.recognizer.borrowCount, 1)
      r.recognizer.finish()
      await firstTask.value
      let first = try XCTUnwrap(firstRequest)
      XCTAssertEqual(r.session.media.wordCheckState, .finished(.timedOut))
      XCTAssertEqual(r.session.media.latestTry?.id, take.id)
      XCTAssertTrue(r.session.playerPresentation.canCheckWords)
      XCTAssertEqual(r.recognizer.requests.count, 6) // No automatic retry.
      let retryTask = Task { await r.session.checkCurrentWord() }
      guard await waitForTimeoutRetryPending(r.recognizer, count: 7) else {
        r.session.media.cancelWordCheck()
        r.recognizer.stopGeneratedChecks()
        await retryTask.value
        _ = await r.session.close()
        XCTFail("Generated retry request did not become pending")
        return
      }
      let retryRequest = r.recognizer.requests.last
      XCTAssertEqual(r.recognizer.requests.count, 7)
      XCTAssertFalse(r.session.playerPresentation.canCheckWords)
      await r.session.checkCurrentWord() // Duplicate while the exact borrow is held.
      XCTAssertEqual(r.recognizer.requests.count, 7)
      r.recognizer.finish()
      await retryTask.value
      let retry = try XCTUnwrap(retryRequest)
      XCTAssertEqual(retry.tryID, first.tryID)
      XCTAssertEqual(retry.fileURL, first.fileURL)
      XCTAssertEqual(retry.expectedWord, first.expectedWord)
      XCTAssertNotEqual(retry.operationID, first.operationID)
      XCTAssertEqual(r.session.ledger?.activePracticeVisit, visit)
      XCTAssertEqual(r.session.media.wordCheckState, .finished(.matched))
      XCTAssertEqual(r.session.media.wordObservation(for: take.id), .matched)
      XCTAssertFalse(r.session.media.canCheckWordsInLatestTry)
      XCTAssertEqual(r.recognizer.borrowCount, 0)
      XCTAssertEqual(r.retryBindingLine,
        "Generated retry binding: same take yes · new operation yes · latest yes")
      XCTAssertEqual(r.capture.createdURLs.count, 6)
      XCTAssertEqual(r.capture.permissionRequests, 6)
      XCTAssertEqual(r.filesLine,
        "Generated files: made 6, kept 1 · permission requests 6 · playback starts 0")
      XCTAssertTrue(r.history.entries.isEmpty)
      XCTAssertEqual(r.session.ledger?.initialRound, initial)
      await r.session.advanceVisit()
      XCTAssertEqual(r.history.entries.count, 1)
      XCTAssertEqual(r.history.entries.first?.id, visit.visitID)
      await r.session.startRecheck()
      XCTAssertTrue(r.session.ledger?.recheckRound?.rows.allSatisfy {
        $0.firstSubmission == nil && ($0.state == .notVisited || $0.state == .ready)
      } == true)
      XCTAssertNil(r.session.media.latestTry)
      XCTAssertEqual(r.session.ledger?.initialRound, initial)
      XCTAssertEqual(r.recognizer.requests.count, 7)
      XCTAssertEqual(r.modelLine, "Generated model calls: 0")
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.files.protectedURLs.isEmpty)
    }

    func testGeneratedRecognizerStopReleasesHeldAndRejectsLateChecksWithoutBorrow() async {
      let files = ProcessAudioFileOwnership()
      let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("generated-timeout-stop-\(UUID())/synthetic.wav")
      let owner = UUID()
      files.retain(url, owner: owner) // Metadata only; the fake never opens a file.
      let recognizer = LocalGuidedGeneratedRecognizer(files: files, holdsResult: true)
      let request = LocalWordRecognitionRequest(
        operationID: UUID(), tryID: UUID(), fileURL: url, expectedWord: "pig")
      let held = Task { await recognizer.check(request: request) }
      let becamePending = await waitForTimeoutRetryPending(recognizer, count: 1)
      if becamePending { XCTAssertFalse(files.canRemove(url, owner: owner)) }
      recognizer.stopGeneratedChecks()
      let receipt = await held.value
      XCTAssertTrue(becamePending)
      XCTAssertEqual(receipt.request, request)
      XCTAssertEqual(receipt.status, .cancelled)
      XCTAssertTrue(receipt.cleanupConfirmed)
      XCTAssertFalse(recognizer.isPending)
      XCTAssertEqual(recognizer.borrowCount, 0)
      XCTAssertTrue(files.canRemove(url, owner: owner))
      let late = LocalWordRecognitionRequest(
        operationID: UUID(), tryID: request.tryID, fileURL: url, expectedWord: "pig")
      let lateReceipt = await recognizer.check(request: late)
      XCTAssertEqual(lateReceipt.request, late)
      XCTAssertEqual(lateReceipt.status, .cancelled)
      XCTAssertTrue(lateReceipt.cleanupConfirmed)
      XCTAssertEqual(recognizer.requests.count, 1)
      XCTAssertFalse(recognizer.isPending)
      XCTAssertTrue(files.canRemove(url, owner: owner), "Late call must not borrow the input")
      files.didRemove(url, owner: owner)
      XCTAssertTrue(files.protectedURLs.isEmpty)
    }

    private func waitForTimeoutRetryPending(
      _ recognizer: LocalGuidedGeneratedRecognizer, count: Int
    ) async -> Bool {
      if recognizer.isPending, recognizer.requests.count == count { return true }
      let pending = XCTestExpectation(description: "Exact generated request \(count) held")
      let previousChanged = recognizer.changed
      var fulfilled = false
      recognizer.changed = {
        previousChanged?()
        if recognizer.isPending, recognizer.requests.count == count, !fulfilled {
          fulfilled = true
          pending.fulfill()
        }
      }
      defer { recognizer.changed = previousChanged }
      return await XCTWaiter.fulfillment(of: [pending], timeout: 2) == .completed
    }

    func testProductionProcessingFailureFreezesGuidedUnavailableWithoutForcingPractice() async throws {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent("guided-processing-\(UUID())", isDirectory: true)
      let history = PracticeParticipationStore(fileURL: directory.appendingPathComponent("history.json"))
      let files = ProcessAudioFileOwnership()
      let hardware = AudioHardwareOwnership()
      let capture = LocalGuidedGeneratedCapture(hardware: hardware, files: files)
      let player = ResearchAcknowledgedPlaybackUITestFixture(completion: .explicitStop, ownership: hardware, fileOwnership: files)
      var playbackStarts = Set<UUID>()
      let playbackObservation = player.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .playing(let operation) = state { playbackStarts.insert(operation.id) }
        }
      }
      defer { playbackObservation.cancel() }
      let recovery = ProcessPracticeMirrorRecovery()
      let mirror = DirectPracticeMirror(permission: ContinuationMirrorPermission(),
        runtime: PracticeMirrorRuntime(recovery: recovery, presentation: PracticeMirrorPresentation(),
          factory: { _ in ContinuationMirrorDriver() }), recovery: recovery)
      let requests = GuidedProcessingRequestLog()
      let recognizer = CoreMLLocalWordRecognizer(ownership: files, deadlineNanoseconds: 15_000_000_000,
        fixtureWorker: { request, stop in
          requests.append(request)
          return WhisperCoreMLWorker.processingCompletion(stop: stop, evict: {}) {
            _ = try WhisperCoreMLWorker.maximum(logits: [], stop: stop, isAllowed: { _ in true })
            return .init(status: .matched, cleanupConfirmed: true, retainedHandle: nil)
          }
        })
      let media = DirectPracticeSession(capturer: capture, player: player, mirror: mirror,
        history: history, managedForGuided: true, wordRecognizer: recognizer,
        cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
      let flow = LocalGuidedReviewSession(history: history, media: media)
      await flow.startInitialReview()
      let firstVisit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
      await media.startRecording()
      media.stopRecording()
      await flow.checkCurrentWord()
      XCTAssertEqual(media.wordCheckState, .finished(.unavailable))
      XCTAssertNil(media.currentWordGuess)
      let frozenRow = try XCTUnwrap(flow.ledger?.initialRound.rows.first)
      XCTAssertEqual(frozenRow.state, .finished(.unavailable))
      XCTAssertEqual(frozenRow.firstSubmission?.visit, firstVisit)
      XCTAssertEqual(frozenRow.firstSubmission?.operationID, requests.values.first?.operationID)
      XCTAssertEqual(frozenRow.firstSubmission?.tryID, media.latestTry?.id)
      XCTAssertFalse(media.canCheckWordsInLatestTry)
      XCTAssertFalse(media.canRecordAnotherTry)
      await flow.checkCurrentWord()
      await media.recordAnotherTry()
      XCTAssertEqual(requests.values.count, 1)
      XCTAssertEqual(capture.createdURLs.count, 1)
      XCTAssertEqual(capture.permissionRequests, 1)
      XCTAssertEqual(flow.ledger?.initialRound.rows.first, frozenRow)
      XCTAssertTrue(history.entries.isEmpty)
      await flow.advanceVisit()
      await flow.finishStageNow()
      XCTAssertEqual(flow.ledger?.initialRound.rows.first, frozenRow)
      XCTAssertEqual(capture.retainedCount, 0)
      XCTAssertEqual(requests.values.count, 1)
      XCTAssertTrue(history.entries.isEmpty)
      flow.togglePracticeSelection(entryID: firstVisit.entryID)
      await flow.startPractice()
      let practiceVisit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
      XCTAssertNil(media.currentWordGuess)
      XCTAssertEqual(requests.values.count, 1)
      XCTAssertEqual(capture.createdURLs.count, 1)
      await media.startRecording()
      media.stopRecording()
      XCTAssertEqual(requests.values.count, 1)
      await flow.advanceVisit()
      XCTAssertEqual(history.entries.count, 1)
      XCTAssertEqual(history.entries.first?.wordCount, 1)
      XCTAssertEqual(history.entries.first?.soundID, "b")
      XCTAssertEqual(history.entries.first?.id, practiceVisit.visitID)
      await flow.startRecheck()
      let recheckVisit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
      XCTAssertNotEqual(recheckVisit.visitID, firstVisit.visitID)
      await media.startRecording()
      media.stopRecording()
      await flow.checkCurrentWord()
      XCTAssertEqual(media.wordCheckState, .finished(.unavailable))
      XCTAssertFalse(media.canCheckWordsInLatestTry)
      XCTAssertEqual(requests.values.count, 2)
      XCTAssertNotEqual(requests.values.first?.tryID, requests.values.last?.tryID)
      XCTAssertEqual(flow.ledger?.recheckRound?.rows.first?.state, .finished(.unavailable))
      XCTAssertEqual(flow.ledger?.recheckRound?.rows.first?.firstSubmission?.visit, recheckVisit)
      XCTAssertEqual(flow.ledger?.recheckRound?.rows.first?.firstSubmission?.operationID, requests.values.last?.operationID)
      XCTAssertEqual(flow.ledger?.recheckRound?.rows.first?.firstSubmission?.tryID, media.latestTry?.id)
      XCTAssertEqual(flow.ledger?.initialRound.rows.first, frozenRow)
      XCTAssertEqual(history.entries.count, 1)
      let closed = await flow.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(capture.retainedCount, 0)
      XCTAssertEqual(capture.createdURLs.count, 3)
      XCTAssertEqual(capture.permissionRequests, 3)
      XCTAssertTrue(playbackStarts.isEmpty)
      XCTAssertTrue(files.protectedURLs.isEmpty)
      XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
      XCTAssertNil(hardware.currentLease)
      XCTAssertNil(recovery.owner)
      if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
    }
    func testInitialCheckStatusUsesFeedbackNoteAndFrozenContextRemainsInPracticeAndRecheck()
      async throws
    {
      let r = LocalGuidedGeneratedResources(testCase: .heldFinish, runID: UUID())
      defer { r.recognizer.finish() }
      await r.prepareSeed()
      await r.session.startInitialReview()
      let firstVisit = try XCTUnwrap(r.session.ledger?.activeReviewVisit)
      XCTAssertEqual(r.session.media.guidedMediaVisit, .review(firstVisit))
      XCTAssertNil(r.session.playerPresentation.firstObservationNote)
      XCTAssertNil(r.session.playerPresentation.firstCheckStatusNote)

      func waitForHeldRequest(count: Int) async {
        let pending = XCTestExpectation(description: "Exact generated request held")
        var fulfilled = false
        let observation = r.$checkLine.sink { _ in
          if r.recognizer.isPending, r.recognizer.requests.count == count, !fulfilled {
            fulfilled = true
            pending.fulfill()
          }
        }
        defer { observation.cancel() }
        let result = await XCTWaiter.fulfillment(of: [pending], timeout: 2)
        XCTAssertEqual(result, .completed)
      }

      await r.session.recordAndCheckCurrentWord()
      r.session.media.stopRecording()
      await waitForHeldRequest(count: 1)
      let firstRequest = try XCTUnwrap(r.recognizer.requests.first)
      XCTAssertEqual(firstRequest.tryID, r.session.media.latestTry?.id)
      XCTAssertEqual(firstRequest.fileURL, r.capture.returnedURLs.first)
      XCTAssertEqual(r.session.ledger?.initialRound.rows.first?.firstSubmission?.visit, firstVisit)
      XCTAssertEqual(r.session.ledger?.initialRound.rows.first?.state, .pending)
      XCTAssertNil(r.session.playerPresentation.firstObservationNote)
      XCTAssertEqual(r.session.playerPresentation.firstCheckStatusNote, "First check in progress.")
      r.recognizer.finish()
      await waitForFinishedCheck(r.session.media)
      XCTAssertEqual(r.session.ledger?.initialRound.rows.first?.state, .finished(.matched))
      XCTAssertNil(r.session.playerPresentation.firstObservationNote)
      XCTAssertEqual(
        r.session.playerPresentation.firstCheckStatusNote,
        "The first check is kept for this review.")
      XCTAssertEqual(r.recognizer.borrowCount, 0)

      await r.session.advanceVisit()
      XCTAssertNotEqual(r.session.ledger?.activeReviewVisit, firstVisit)
      XCTAssertNil(r.session.playerPresentation.firstObservationNote)
      XCTAssertNil(r.session.playerPresentation.firstCheckStatusNote)
      XCTAssertEqual(r.capture.retainedCount, 0)
      await r.session.finishStageNow()
      let initial = try XCTUnwrap(r.session.ledger?.initialRound)
      r.session.togglePracticeSelection(entryID: firstVisit.entryID)
      await r.session.startPractice()
      let practiceVisit = try XCTUnwrap(r.session.ledger?.activePracticeVisit)
      XCTAssertEqual(practiceVisit.entryID, firstVisit.entryID)
      XCTAssertEqual(r.session.media.guidedMediaVisit, .practice(practiceVisit))
      let frozen = "First review: Word matched. Word checks cannot identify which sound was made."
      XCTAssertEqual(r.session.playerPresentation.firstObservationNote, frozen)
      XCTAssertNil(r.session.playerPresentation.firstCheckStatusNote)
      await r.session.finishStageNow()
      await r.session.startRecheck()
      let recheckVisit = try XCTUnwrap(r.session.ledger?.activeReviewVisit)
      XCTAssertNotEqual(recheckVisit.roundID, firstVisit.roundID)
      XCTAssertNotEqual(recheckVisit.visitID, firstVisit.visitID)
      XCTAssertEqual(r.session.media.guidedMediaVisit, .review(recheckVisit))
      XCTAssertEqual(r.session.playerPresentation.firstObservationNote, frozen)
      XCTAssertNil(r.session.playerPresentation.firstCheckStatusNote)
      await r.session.recordAndCheckCurrentWord()
      r.session.media.stopRecording()
      await waitForHeldRequest(count: 2)
      XCTAssertEqual(
        r.session.ledger?.recheckRound?.rows.first?.firstSubmission?.visit, recheckVisit)
      XCTAssertEqual(r.session.playerPresentation.firstObservationNote, frozen)
      XCTAssertNil(r.session.playerPresentation.firstCheckStatusNote)
      r.recognizer.finish()
      await waitForFinishedCheck(r.session.media)
      XCTAssertEqual(r.session.ledger?.recheckRound?.rows.first?.state, .finished(.matched))
      XCTAssertEqual(r.session.playerPresentation.firstObservationNote, frozen)
      XCTAssertNil(r.session.playerPresentation.firstCheckStatusNote)
      XCTAssertEqual(r.session.ledger?.initialRound, initial)
      XCTAssertEqual(r.recognizer.requests.count, 2)
      XCTAssertEqual(r.recognizer.borrowCount, 0)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertEqual(r.capture.cleanupState, .idle)
      XCTAssertTrue(r.files.protectedURLs.isEmpty)
      XCTAssertTrue(r.files.pendingCleanupOwners.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
    }

    func testCombinedCoordinatorChecksAllFiveThenPracticeAndFreshFiveRecheck() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      await r.prepareSeed()
      await r.session.startInitialReview()
      var frozenInitial = r.session.ledger?.initialRound
      for round in 0..<2 {
        for (index, entry) in r.session.setupEntries.enumerated() {
          let visit = try XCTUnwrap(r.session.ledger?.activeReviewVisit)
          XCTAssertEqual(visit.entryID, entry.id)
          XCTAssertTrue(r.session.playerPresentation.canRecordAndCheck)
          await r.session.playerPresentation.recordAndCheck()
          r.session.media.stopRecording()
          await waitForFinishedCheck(r.session.media)
          let request = try XCTUnwrap(r.recognizer.requests.last)
          XCTAssertEqual(request.expectedWord, entry.prompt.word)
          XCTAssertEqual(request.tryID, r.session.media.latestTry?.id)
          XCTAssertEqual(request.fileURL, r.capture.returnedURLs.last)
          XCTAssertEqual(r.recognizer.requests.count, round * 5 + index + 1)
          let row = r.session.ledger?.activeRound?.rows[index]
          XCTAssertEqual(row?.firstSubmission?.visit, visit)
          XCTAssertEqual(row?.state, .finished(.matched))
          await r.session.advanceVisit()
        }
        if round == 0 {
          frozenInitial = r.session.ledger?.initialRound
          r.session.togglePracticeSelection(entryID: r.session.setupEntries[0].id)
          await r.session.startPractice()
          XCTAssertFalse(r.session.playerPresentation.showsRecordAndCheck)
          await r.session.media.startRecording()
          r.session.media.stopRecording()
          XCTAssertEqual(r.recognizer.requests.count, 5)
          await r.session.advanceVisit()
          XCTAssertEqual(r.history.entries.count, 1)
          await r.session.startRecheck()
        }
        XCTAssertEqual(r.session.ledger?.initialRound, frozenInitial)
      }
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(Set(r.recognizer.requests.map(\.operationID)).count, 10)
      XCTAssertEqual(Set(r.recognizer.requests.map(\.tryID)).count, 10)
      XCTAssertEqual(r.capture.createdURLs.count, 11)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertEqual(r.history.entries.map(\.wordCount), [1])
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testCombinedRetakeChecksOnlyReplacementInFirstReviewAndFreshRecheck() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .retake, runID: UUID())
      await r.prepareSeed()
      await r.session.startInitialReview()
      var frozenInitial: LocalGuidedReviewRound?
      for round in 0..<2 {
        let visit = try XCTUnwrap(r.session.ledger?.activeReviewVisit)
        XCTAssertTrue(r.session.playerPresentation.canRecordAndCheck)
        await r.session.playerPresentation.recordAndCheck()
        r.session.media.stopRecording()
        let rejected = try XCTUnwrap(r.session.media.latestTry)
        if case .retry = rejected.assessment {} else { XCTFail("Expected short capture") }
        XCTAssertEqual(r.recognizer.requests.count, round)
        XCTAssertEqual(r.session.ledger?.activeRound?.rows.first?.state, .ready)
        XCTAssertFalse(r.session.media.canStartRecordingAndCheckWord)
        XCTAssertTrue(r.session.playerPresentation.canRecordAndCheck)
        await r.session.playerPresentation.recordAndCheck()
        XCTAssertEqual(r.session.media.phase, .recording)
        XCTAssertEqual(r.recognizer.requests.count, round)
        r.session.media.stopRecording()
        await waitForFinishedCheck(r.session.media)
        let latest = try XCTUnwrap(r.session.media.latestTry)
        let request = try XCTUnwrap(r.recognizer.requests.last)
        XCTAssertNotEqual(latest.id, rejected.id)
        XCTAssertEqual(request.tryID, latest.id)
        XCTAssertEqual(request.fileURL, r.capture.returnedURLs.last)
        XCTAssertEqual(r.recognizer.requests.count, round + 1)
        XCTAssertEqual(r.session.ledger?.activeRound?.rows.first?.state, .finished(.matched))
        XCTAssertEqual(r.session.ledger?.activeRound?.rows.first?.firstSubmission?.visit, visit)
        XCTAssertFalse(r.session.playerPresentation.showsRecordAndCheck)
        XCTAssertFalse(r.session.playerPresentation.canRecordAndCheck)
        await r.session.playerPresentation.recordAndCheck()
        XCTAssertEqual(r.capture.createdURLs.count, (round + 1) * 2)
        XCTAssertTrue(r.history.entries.isEmpty)
        await r.session.finishStageNow()
        if round == 0 {
          frozenInitial = r.session.ledger?.initialRound
          r.session.togglePracticeSelection(entryID: visit.entryID)
          await r.session.startPractice()
          XCTAssertFalse(r.session.playerPresentation.showsRecordAndCheck)
          await r.session.finishStageNow()
          await r.session.startRecheck()
        }
        XCTAssertEqual(r.session.ledger?.initialRound, frozenInitial)
      }
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.files.protectedURLs.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
    }

    func testRecordOnlyKeepsFirstSubmissionOpenForChosenLatestTry() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      await r.prepareSeed()
      await r.session.startInitialReview()
      XCTAssertTrue(r.session.playerPresentation.showsRecordAndCheck)
      XCTAssertTrue(r.session.playerPresentation.canRecordAndCheck)
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      XCTAssertTrue(r.recognizer.requests.isEmpty)
      XCTAssertEqual(r.session.ledger?.initialRound.rows.first?.state, .ready)
      await r.session.media.recordAnotherTry()
      r.session.media.stopRecording()
      XCTAssertTrue(r.recognizer.requests.isEmpty)
      XCTAssertEqual(r.capture.createdURLs.count, 2)
      let latest = try XCTUnwrap(r.session.media.latestTry)
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.recognizer.requests.count, 1)
      XCTAssertEqual(r.recognizer.requests.first?.tryID, latest.id)
      XCTAssertEqual(r.recognizer.requests.first?.fileURL, r.capture.returnedURLs.last)
      XCTAssertFalse(r.session.playerPresentation.showsRecordAndCheck)
      XCTAssertTrue(r.session.playerPresentation.canContinue)
      XCTAssertTrue(r.history.entries.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(r.capture.retainedCount, 0)
    }

    func testCombinedActionExcludesEnabledResearchAndDisabledWrapperStaysWordOnly() async throws {
      for enabled in [false, true] {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let history = PracticeParticipationStore(
          fileURL: directory.appendingPathComponent("history.json"))
        let hardware = AudioHardwareOwnership()
        let files = ProcessAudioFileOwnership()
        let capture = LocalGuidedGeneratedCapture(hardware: hardware, files: files)
        let word = LocalGuidedGeneratedRecognizer(files: files, holdsResult: false)
        let processor = CombinedResearchProbe()
        let research = GuidedResearchModelRecognizer(
          wordRecognizer: word, processor: processor, ownership: files,
          availability: GuidedResearchModelAvailability())
        let recovery = ProcessPracticeMirrorRecovery()
        let mirror = DirectPracticeMirror(
          permission: ContinuationMirrorPermission(),
          runtime: PracticeMirrorRuntime(
            recovery: recovery, presentation: PracticeMirrorPresentation(),
            factory: { _ in ContinuationMirrorDriver() }), recovery: recovery)
        let media = DirectPracticeSession(
          capturer: capture,
          player: ResearchAcknowledgedPlaybackUITestFixture(
            completion: .explicitStop, ownership: hardware, fileOwnership: files),
          mirror: mirror, history: history, managedForGuided: true, wordRecognizer: research,
          cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
        let session = LocalGuidedReviewSession(
          history: history, media: media, researchModel: research)
        XCTAssertTrue(session.configureResearchModel(enabled: enabled, ageYears: enabled ? 9 : nil))
        await session.startInitialReview()
        XCTAssertEqual(session.playerPresentation.showsRecordAndCheck, !enabled)
        XCTAssertEqual(session.playerPresentation.canRecordAndCheck, !enabled)
        await session.playerPresentation.recordAndCheck()
        if enabled {
          XCTAssertEqual(media.phase, .ready)
          XCTAssertTrue(capture.createdURLs.isEmpty)
          XCTAssertTrue(word.requests.isEmpty)
          XCTAssertEqual(processor.calls, 0)
          await media.startRecording()
          media.stopRecording()
          XCTAssertTrue(word.requests.isEmpty)
          XCTAssertEqual(processor.calls, 0)
          await session.checkCurrentWord()
        } else {
          XCTAssertEqual(media.phase, .recording)
          media.stopRecording()
          await waitForFinishedCheck(media)
        }
        XCTAssertEqual(word.requests.count, 1)
        XCTAssertEqual(processor.calls, enabled ? 1 : 0)
        XCTAssertTrue(session.playerPresentation.canContinue)
        XCTAssertTrue(history.entries.isEmpty)
        let closed = await session.close()
        XCTAssertTrue(closed)
        XCTAssertEqual(capture.retainedCount, 0)
      }
    }

    private final class CombinedResearchProbe: ResearchAssessmentProcessing {
      var calls = 0
      func process(
        attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
      ) async throws -> ResearchAssessmentOutcome {
        calls += 1
        return .processedResearch(try ResearchAssessmentFixtures.result(attemptId: attemptId,
          recording: recording, entry: entry, ageYears: ageYears, milliseconds: 1))
      }
    }

    private func waitForFinishedCheck(_ media: DirectPracticeSession) async {
      let finished = XCTestExpectation(description: "Exact generated word check settled")
      var fulfilled = false
      let subscription = media.$wordCheckState.sink { state in
        if case .finished = state, !fulfilled {
          fulfilled = true
          finished.fulfill()
        }
      }
      defer { subscription.cancel() }
      let result = await XCTWaiter.fulfillment(of: [finished], timeout: 2)
      XCTAssertEqual(result, .completed)
    }

    func testFinalReviewAndRecheckContinuationsOpenTheirNamedStages() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      await r.prepareSeed()
      await r.session.startInitialReview()
      for _ in 0..<4 {
        XCTAssertEqual(r.session.playerPresentation.continueLabel, "Next word")
        await r.session.skipVisit()
      }
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.session.playerPresentation.positionLabel, "5 of 5")
      XCTAssertEqual(r.session.playerPresentation.continueLabel, "Choose practice words")
      XCTAssertTrue(r.session.playerPresentation.canContinue)
      await r.session.playerPresentation.continueVisit()
      XCTAssertEqual(r.session.ledger?.stage, .choosingPractice)
      r.session.togglePracticeSelection(entryID: r.session.setupEntries[4].id)
      await r.session.startPractice()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      XCTAssertEqual(r.session.playerPresentation.positionLabel, "1 of 1")
      XCTAssertEqual(r.session.playerPresentation.continueLabel, "Finish practice")
      XCTAssertTrue(r.session.playerPresentation.canContinue)
      await r.session.playerPresentation.continueVisit()
      XCTAssertEqual(r.session.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(r.history.entries.count, 1)
      await r.session.startRecheck()
      for _ in 0..<4 {
        XCTAssertEqual(r.session.playerPresentation.continueLabel, "Next word")
        await r.session.skipVisit()
      }
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.checkCurrentWord()
      XCTAssertEqual(r.session.playerPresentation.positionLabel, "5 of 5")
      XCTAssertEqual(r.session.playerPresentation.continueLabel, "View summary")
      XCTAssertTrue(r.session.playerPresentation.canContinue)
      await r.session.playerPresentation.continueVisit()
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.recognizer.requests.count, 2)
      XCTAssertEqual(r.capture.retainedCount, 0)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testPracticeContinuationUsesSelectedVisitCount() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .practice, runID: UUID())
      await r.prepareSeed()
      let selected = [0, 2, 4].map { r.session.setupEntries[$0] }
      for entry in selected { r.session.togglePracticeSelection(entryID: entry.id) }
      await r.session.startPractice()
      for (index, entry) in selected.enumerated() {
        XCTAssertEqual(r.session.media.currentPrompt.id, entry.id)
        XCTAssertEqual(r.session.playerPresentation.positionLabel, "\(index + 1) of 3")
        XCTAssertEqual(
          r.session.playerPresentation.continueLabel, index == 2 ? "Finish practice" : "Next word")
        await r.session.media.startRecording()
        r.session.media.stopRecording()
        XCTAssertTrue(r.session.playerPresentation.canContinue)
        await r.session.playerPresentation.continueVisit()
        XCTAssertEqual(r.session.ledger?.stage, index == 2 ? .readyToRecheck : .practice)
      }
      XCTAssertEqual(r.history.entries.count, 3)
      XCTAssertEqual(r.recognizer.requests.count, 5)
      XCTAssertEqual(r.capture.retainedCount, 0)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testFinalPracticeSaveFailureKeepsContinueWithoutSavingUntilRetry() async throws {
      for retry in [false, true] {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "guided-continuation-save-\(UUID())", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let historyURL = directory.appendingPathComponent("history.json")
        let history = PracticeParticipationStore(fileURL: historyURL)
        let hardware = AudioHardwareOwnership()
        let files = ProcessAudioFileOwnership()
        let capture = LocalGuidedGeneratedCapture(hardware: hardware, files: files)
        let recognizer = LocalGuidedGeneratedRecognizer(files: files, holdsResult: false)
        let player = ResearchAcknowledgedPlaybackUITestFixture(
          completion: .explicitStop, ownership: hardware, fileOwnership: files)
        let recovery = ProcessPracticeMirrorRecovery()
        let mirror = DirectPracticeMirror(
          permission: ContinuationMirrorPermission(),
          runtime: PracticeMirrorRuntime(
            recovery: recovery, presentation: PracticeMirrorPresentation(),
            factory: { _ in ContinuationMirrorDriver() }), recovery: recovery)
        let media = DirectPracticeSession(
          capturer: capture, player: player, mirror: mirror, history: history,
          managedForGuided: true, wordRecognizer: recognizer,
          cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
        let session = LocalGuidedReviewSession(history: history, media: media)
        await session.startInitialReview()
        await session.finishStageNow()
        session.togglePracticeSelection(entryID: session.setupEntries[0].id)
        await session.startPractice()
        let visit = try XCTUnwrap(session.ledger?.activePracticeVisit)
        try FileManager.default.createDirectory(at: historyURL, withIntermediateDirectories: true)
        await media.startRecording()
        media.stopRecording()
        XCTAssertEqual(session.playerPresentation.continueLabel, "Finish practice")
        await session.playerPresentation.continueVisit()
        XCTAssertEqual(session.ledger?.stage, .practice)
        XCTAssertEqual(session.ledger?.activePracticeVisit, visit)
        XCTAssertEqual(session.playerPresentation.continueLabel, "Continue without saving")
        XCTAssertTrue(session.playerPresentation.canContinue)
        XCTAssertTrue(session.playerPresentation.canRetrySave)
        XCTAssertTrue(history.entries.isEmpty)
        XCTAssertEqual(capture.retainedCount, 0)
        let failure = try XCTUnwrap(media.currentParticipationSaveAnnouncement)
        XCTAssertEqual(failure.completion.id, visit.visitID)
        XCTAssertEqual(failure.message, media.historyError)
        session.playerPresentation.retrySave()
        let firstRetry = try XCTUnwrap(media.currentParticipationSaveAnnouncement)
        session.playerPresentation.retrySave()
        let secondRetry = try XCTUnwrap(media.currentParticipationSaveAnnouncement)
        XCTAssertEqual(Set([failure.id, firstRetry.id, secondRetry.id]).count, 3)
        XCTAssertEqual(firstRetry.message, secondRetry.message)
        XCTAssertEqual(secondRetry.completion, failure.completion)
        if retry {
          try FileManager.default.removeItem(at: historyURL)
          session.playerPresentation.retrySave()
          XCTAssertEqual(session.playerPresentation.continueLabel, "Finish practice")
          XCTAssertEqual(history.entries.map(\.id), [visit.visitID])
          let saved = try XCTUnwrap(media.currentParticipationSaveAnnouncement)
          XCTAssertEqual(saved.message, "Saved to practice history.")
          XCTAssertEqual(saved.completion, failure.completion)
          session.playerPresentation.retrySave()
          XCTAssertEqual(media.currentParticipationSaveAnnouncement, saved)
        }
        await session.playerPresentation.continueVisit()
        XCTAssertNil(media.currentParticipationSaveAnnouncement)
        XCTAssertEqual(session.ledger?.stage, .readyToRecheck)
        XCTAssertEqual(history.entries.count, retry ? 1 : 0)
        XCTAssertEqual(capture.permissionRequests, 1)
        XCTAssertTrue(recognizer.requests.isEmpty)
        let closed = await session.close()
        XCTAssertTrue(closed)
      }
    }

    func testGuidedInitialParticipationSaveIsQuietForItsExactCurrentCompletion() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .practice, runID: UUID())
      await r.prepareSeed()
      let seededPermissionRequests = r.capture.permissionRequests
      XCTAssertEqual(seededPermissionRequests, 5)
      XCTAssertEqual(r.session.ledger?.stage, .choosingPractice)
      XCTAssertEqual(r.recognizer.requests.count, 5)
      r.session.togglePracticeSelection(entryID: r.session.setupEntries[0].id)
      await r.session.startPractice()
      let visit = try XCTUnwrap(r.session.ledger?.activePracticeVisit)
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      let result = await r.session.media.finishGuidedPractice(visit)
      XCTAssertTrue(result.saveConfirmed)
      XCTAssertEqual(r.session.media.phase, .completed)
      XCTAssertEqual(r.session.media.participationCompletion?.id, visit.visitID)
      XCTAssertNil(r.session.media.historyError)
      XCTAssertNil(r.session.media.historySavedNote)
      XCTAssertNil(r.session.media.currentParticipationSaveAnnouncement)
      XCTAssertEqual(r.history.entries.map(\.id), [visit.visitID])
      XCTAssertEqual(r.capture.permissionRequests, seededPermissionRequests + 1)
      XCTAssertEqual(r.recognizer.requests.count, 5)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertNil(r.session.media.currentParticipationSaveAnnouncement)
    }

    func testUnseededFixtureConstructionAndPreparationNeverStartMedia() async throws {
      let resources = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      XCTAssertNil(resources.session.ledger)
      XCTAssertEqual(resources.capture.permissionRequests, 0)
      XCTAssertTrue(resources.capture.createdURLs.isEmpty)
      XCTAssertTrue(resources.recognizer.requests.isEmpty)
      XCTAssertTrue(resources.history.entries.isEmpty)
      await resources.prepareSeed()
      await resources.prepareSeed()
      XCTAssertNil(resources.session.ledger)
      XCTAssertEqual(
        resources.filesLine,
        "Generated files: made 0, kept 0 · permission requests 0 · playback starts 0")
      XCTAssertEqual(resources.seedLine, "Generated stage: unseeded setup")
      let closed = await resources.session.close()
      XCTAssertTrue(closed)
    }

    func testPracticeSeedSettlesFiveActualFirstSubmissionsWithoutHistoryOrPreselection()
      async throws
    {
      let r = LocalGuidedGeneratedResources(testCase: .practice, runID: UUID())
      await r.prepareSeed()
      let ledger = try XCTUnwrap(r.session.ledger)
      XCTAssertEqual(ledger.stage, .choosingPractice)
      XCTAssertEqual(
        ledger.initialRound.rows.map(\.entry.prompt.word), ["ball", "pig", "moon", "tiger", "dog"])
      XCTAssertTrue(ledger.initialRound.rows.allSatisfy { $0.state == .finished(.matched) })
      let submitted = ledger.initialRound.rows.compactMap(\.firstSubmission)
      XCTAssertEqual(submitted.count, 5)
      XCTAssertEqual(Set(submitted.map(\.operationID)).count, 5)
      XCTAssertEqual(Set(submitted.map(\.tryID)).count, 5)
      XCTAssertEqual(r.recognizer.requests.map(\.operationID), submitted.map(\.operationID))
      XCTAssertEqual(r.recognizer.requests.map(\.fileURL), r.capture.returnedURLs)
      XCTAssertTrue(r.session.practiceSelectionIDs.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
      XCTAssertEqual(r.capture.retainedCount, 0)
      await r.prepareSeed()
      XCTAssertEqual(r.recognizer.requests.count, 5)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testUserChosenPigAndDogSaveExactVisitMetadataWithFreshTakesAndNoExtraWordChecks()
      async throws
    {
      let r = LocalGuidedGeneratedResources(testCase: .practice, runID: UUID())
      await r.prepareSeed()
      let initial = try XCTUnwrap(r.session.ledger).initialRound
      let chosen = [r.session.setupEntries[1], r.session.setupEntries[4]]
      for entry in chosen { r.session.togglePracticeSelection(entryID: entry.id) }
      await r.session.startPractice()
      for entry in chosen {
        XCTAssertEqual(r.session.media.currentPrompt.id, entry.id)
        let visit = try XCTUnwrap(r.session.ledger?.activePracticeVisit)
        XCTAssertNil(r.session.media.latestTry)
        await r.session.media.startRecording()
        r.session.media.stopRecording()
        let takeID = try XCTUnwrap(r.session.media.latestTry?.id)
        XCTAssertFalse(initial.rows.compactMap(\.firstSubmission).map(\.tryID).contains(takeID))
        await r.session.advanceVisit()
        XCTAssertTrue(
          r.history.entries.contains {
            $0.id == visit.visitID && $0.soundID == entry.soundID && $0.wordCount == 1
          })
      }
      XCTAssertEqual(r.session.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(r.session.ledger?.initialRound, initial)
      XCTAssertEqual(r.history.entries.count, 2)
      XCTAssertEqual(r.recognizer.requests.count, 5)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertEqual(r.receiptLine, "Generated practice receipts: 2 exact")
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testRecheckSeedUsesOneSavedPracticeAndFreshSameFiveRoundThenKeepsInitialImmutable()
      async throws
    {
      let r = LocalGuidedGeneratedResources(testCase: .recheck, runID: UUID())
      await r.prepareSeed()
      let initial = try XCTUnwrap(r.session.ledger).initialRound
      XCTAssertEqual(r.history.entries.map(\.soundID), ["p"])
      await r.session.startRecheck()
      let recheck = try XCTUnwrap(r.session.ledger?.recheckRound)
      XCTAssertNotEqual(recheck.id, initial.id)
      XCTAssertEqual(recheck.rows.map(\.entry), initial.rows.map(\.entry))
      XCTAssertTrue(recheck.rows.allSatisfy { $0.firstSubmission == nil })
      let visit = try XCTUnwrap(r.session.ledger?.activeReviewVisit)
      XCTAssertFalse(initial.rows.compactMap(\.visit).map(\.visitID).contains(visit.visitID))
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      await r.session.checkCurrentWord()
      let fresh = try XCTUnwrap(r.session.ledger?.recheckRound?.rows[0].firstSubmission)
      XCTAssertFalse(initial.rows.compactMap(\.firstSubmission).map(\.tryID).contains(fresh.tryID))
      XCTAssertFalse(
        initial.rows.compactMap(\.firstSubmission).map(\.operationID).contains(fresh.operationID))
      await r.session.finishStageNow()
      XCTAssertEqual(r.session.ledger?.stage, .completed)
      XCTAssertEqual(r.session.ledger?.initialRound, initial)
      XCTAssertEqual(r.session.ledger?.pairedRows.count, 5)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertEqual(r.history.entries.count, 1)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testHeldCancelRetainsExactBorrowUntilReleaseThenEarlyFinishMarksRemainingUnreached()
      async throws
    {
      let r = LocalGuidedGeneratedResources(testCase: .heldFinish, runID: UUID())
      await r.prepareSeed()
      await r.session.startInitialReview()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      let checking = Task { await r.session.checkCurrentWord() }
      defer { r.recognizer.finish() }
      await waitForPending(r)
      let request = try XCTUnwrap(r.recognizer.requests.last)
      r.recognizer.cancel(operationID: UUID())
      XCTAssertTrue(r.recognizer.cancellations.isEmpty)
      r.session.media.cancelWordCheck()
      XCTAssertEqual(r.recognizer.cancellations, [request.operationID])
      XCTAssertEqual(r.recognizer.borrowCount, 1)
      XCTAssertEqual(r.capture.retainedCount, 1)
      XCTAssertTrue(r.files.protectedURLs.contains(request.fileURL.standardizedFileURL))
      r.recognizer.finish()
      r.recognizer.finish()
      await checking.value
      XCTAssertEqual(r.session.ledger?.initialRound.rows[0].state, .finished(.cancelled))
      await r.session.finishStageNow()
      XCTAssertEqual(
        r.session.ledger?.initialRound.rows.dropFirst().map(\.state),
        Array(repeating: .finished(.unreached), count: 4))
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.history.entries.isEmpty)
      let closed = await r.session.close()
      XCTAssertTrue(closed)
    }

    func testDuplicateCloseJoinsHeldExactReceiptAndPreservesNoHistory() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .heldClose, runID: UUID())
      await r.prepareSeed()
      await r.session.startInitialReview()
      await r.session.media.startRecording()
      r.session.media.stopRecording()
      let checking = Task { await r.session.checkCurrentWord() }
      defer { r.recognizer.finish() }
      await waitForPending(r)
      let first = Task { await r.session.close() }
      let second = Task { await r.session.close() }
      for _ in 0..<128 where r.recognizer.cancellations.isEmpty { await Task.yield() }
      XCTAssertFalse(r.session.isClosed)
      XCTAssertEqual(r.recognizer.borrowCount, 1)
      XCTAssertEqual(r.capture.retainedCount, 1)
      r.recognizer.finish()
      await checking.value
      let endedFirst = await first.value
      let endedSecond = await second.value
      XCTAssertTrue(endedFirst && endedSecond)
      XCTAssertTrue(r.session.isClosed)
      XCTAssertEqual(r.recognizer.requests.count, 1)
      XCTAssertEqual(r.recognizer.cancellations.count, 1)
      XCTAssertEqual(r.capture.retainedCount, 0)
      XCTAssertTrue(r.history.entries.isEmpty)
    }

    private final class ContinuationMirrorPermission: PracticeMirrorPermissionProviding {
      var isSupported: Bool { false }
      var status: PracticeMirrorPermission { .denied }
      func requestPermission(completion: @escaping @MainActor (Bool) -> Void) { completion(false) }
    }

    private final class ContinuationMirrorDriver: PracticeMirrorDriver, @unchecked Sendable {
      private enum Unavailable: Error { case generated }
      func configure() throws { throw Unavailable.generated }
      func start() throws { throw Unavailable.generated }
      var previewSource: PracticeMirrorPreviewSource? { nil }
      func stopAndReleasePreviewResources() throws {}
    }

    private func waitForPending(_ r: LocalGuidedGeneratedResources) async {
      for _ in 0..<256 where !r.recognizer.isPending { await Task.yield() }
      XCTAssertTrue(r.recognizer.isPending)
    }
  }
#endif

#if DEBUG && targetEnvironment(simulator)
private final class GuidedProcessingRequestLog: @unchecked Sendable {
  private let lock = NSLock()
  private var requests: [LocalWordRecognitionRequest] = []
  func append(_ request: LocalWordRecognitionRequest) {
    lock.lock(); defer { lock.unlock() }; requests.append(request)
  }
  var values: [LocalWordRecognitionRequest] {
    lock.lock(); defer { lock.unlock() }; return requests
  }
}
#endif
