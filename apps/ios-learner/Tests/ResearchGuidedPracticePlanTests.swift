#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Controlled generated PCM and invented replies; no transport/model/learner evidence.
  @MainActor
  final class ResearchGuidedPracticePlanTests: XCTestCase {
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Controlled operation did not finish")
    }
    private func owner(
      _ capture: FeedbackCapturer, processor: PlanProcessor = PlanProcessor(),
      writer: PlanWriter? = nil, exampleStore: PlanExampleStore? = nil
    ) async -> ResearchGuidedWordSession {
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(), processor: processor,
        exampleLoader: PlanExampleLoader(), exampleStore: exampleStore)
      let value = ResearchGuidedWordSession(
        feedbackSession: feedback, participationWriter: writer,
        now: { Date(timeIntervalSince1970: 1_700_000_000) })
      value.localProcessingEnabled = true
      let started = await value.start(age: 9)
      XCTAssertTrue(started)
      return value
    }
    private func observe(_ owner: ResearchGuidedWordSession, silenceAt url: URL? = nil) async {
      await owner.record()
      if let url {
        do {
          try FeedbackFixture.wav(Array(repeating: 0, count: 3200)).write(to: url)
        } catch {
          XCTFail("Could not write controlled generated silence: \(error)")
          return
        }
      }
      owner.stop()
      owner.check()
      await wait { !owner.feedbackSession.isProcessing }
    }
    private func choose(_ owner: ResearchGuidedWordSession, _ ids: [String]) async {
      await owner.openPracticePlan()
      for id in ids { owner.togglePracticePlanItem(id) }
      await owner.beginPracticePlan()
      XCTAssertEqual(owner.phase, .practice)
    }
    private func capture(_ owner: ResearchGuidedWordSession) async {
      await owner.record()
      owner.stop()
      XCTAssertEqual(owner.feedbackSession.phase, .review)
    }
    func testAllNineDispositionsSuggestOnlyValidatedPrimaryUnmatchedAndKeepThirteenRows() async {
      let capture = FeedbackCapturer()
      let processor = PlanProcessor()
      processor.reasons = [
        nil, "requested_word_not_matched", "recognition_uncertain", "single_word_required",
        "speech_not_detected", "silence", "worker_crash",
      ]
      defer { capture.remove() }
      let guided = await owner(capture, processor: processor)
      for index in 0..<7 {
        await observe(guided, silenceAt: index == 5 ? capture.url : nil)
        await guided.next()
      }
      await guided.skip()
      await guided.finishEarly()
      let first = guided.firstSummary
      XCTAssertEqual(first?.plannedCount, 13)
      XCTAssertEqual(
        Set(first!.rows.map(\.disposition)), Set(ResearchGuidedWordDisposition.allCases))
      XCTAssertEqual(guided.suggestedPracticeItems.map(\.word), ["bread"])
      await guided.openPracticePlan()
      XCTAssertTrue(guided.selectedPlanItems.isEmpty)
      XCTAssertFalse(guided.canBeginPlan)
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertEqual(processor.calls, 7)
      await guided.returnSummary()
      _ = await guided.end().value
    }
    func testMissingRequestMarkerCannotSupplySuggestedUnmatchedObservation() async {
      let capture = FeedbackCapturer()
      let processor = PlanProcessor()
      processor.reasons = ["requested_word_not_matched"]
      processor.markRequest = false
      defer { capture.remove() }
      let guided = await owner(capture, processor: processor)
      await observe(guided)
      await guided.finishEarly()
      XCTAssertEqual(guided.firstSummary?.rows[0].disposition, .checkUnavailable)
      XCTAssertFalse(guided.attempts[0].validated)
      XCTAssertNil(guided.firstSummary?.rows[0].observation)
      XCTAssertTrue(guided.suggestedPracticeItems.isEmpty)
      await guided.openPracticePlan()
      guided.togglePracticePlanItem("r-beginning-rabbit")
      XCTAssertTrue(guided.canBeginPlan)
      await guided.returnSummary()
      _ = await guided.end().value
    }
    func testEmptyAllMatchedAndEarlySummaryAllowUserChoiceWithoutPreselection() async {
      for fullRound in [false, true] {
        let capture = FeedbackCapturer()
        defer { capture.remove() }
        let guided = await owner(capture)
        if fullRound {
          for _ in 0..<13 {
            await observe(guided)
            await guided.next()
          }
        } else {
          await guided.finishEarly()
        }
        XCTAssertEqual(guided.firstSummary?.plannedCount, 13)
        XCTAssertTrue(guided.suggestedPracticeItems.isEmpty)
        await guided.openPracticePlan()
        XCTAssertTrue(guided.selectedPlanItems.isEmpty)
        await guided.beginPracticePlan()
        XCTAssertEqual(guided.phase, .practicePlanChoice)
        guided.togglePracticePlanItem("zh-middle-treasure")
        await guided.beginPracticePlan()
        XCTAssertTrue(guided.currentItem!.prompt.targetUnsupported)
        XCTAssertEqual(guided.planPosition, 1)
        XCTAssertEqual(guided.feedbackSession.practiceContext, .child(ageYears: 9))
        XCTAssertFalse(guided.feedbackSession.canCheckSound)
        await guided.endPracticePlan()
        _ = await guided.end().value
      }
    }
    func testChooserRejectsAliasesForeignDuplicateAndFourthChoiceAndUsesRosterOrder() async {
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      let guided = await owner(capture)
      await guided.finishEarly()
      await guided.openPracticePlan()
      for id in ["b-middle-baby", "k-end-backpack", "foreign", ""] {
        guided.togglePracticePlanItem(id)
      }
      XCTAssertTrue(guided.selectedPlanItems.isEmpty)
      for id in ["s-beginning-sky", "r-end-door", "r-beginning-rabbit", "r-middle-bread"] {
        guided.togglePracticePlanItem(id)
      }
      XCTAssertEqual(guided.selectedPlanItems.map(\.word), ["rabbit", "door", "sky"])
      guided.togglePracticePlanItem("r-end-door")
      guided.togglePracticePlanItem("r-end-door")
      XCTAssertEqual(guided.selectedPlanItems.map(\.word), ["rabbit", "door", "sky"])
      await guided.cancelPracticePlanChoice()
      XCTAssertEqual(guided.phase, .summary)
      XCTAssertTrue(guided.selectedPlanItems.isEmpty)
      XCTAssertEqual(capture.starts, 0)
      _ = await guided.end().value
    }
    func testExplicitFinishThenNextAndSkipKeepFirstSummaryAndFullFreshRecheck() async {
      let capture = FeedbackCapturer()
      let processor = PlanProcessor()
      let writer = PlanWriter()
      defer { capture.remove() }
      let guided = await owner(capture, processor: processor, writer: writer)
      for _ in 0..<13 {
        await observe(guided)
        await guided.next()
      }
      let first = guided.firstSummary!
      await choose(guided, ["r-middle-bread", "r-end-door"])
      let visit = guided.practiceVisit!.id
      await guided.nextPracticePlanItem()
      XCTAssertEqual(guided.planPosition, 1)
      await guided.finishPractice()
      XCTAssertTrue(writer.calls.isEmpty)
      await self.capture(guided)
      XCTAssertFalse(guided.canCheck)
      guided.check()
      guided.feedbackSession.checkRecording()
      XCTAssertEqual(processor.calls, 13)
      await guided.finishPractice()
      XCTAssertEqual(guided.practicePlanRows[0].disposition, .finishedSaved)
      XCTAssertEqual(guided.planPosition, 1)
      XCTAssertEqual(writer.calls.count, 1)
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 1)
      await guided.nextPracticePlanItem()
      XCTAssertEqual(guided.planPosition, 2)
      XCTAssertNotEqual(guided.practiceVisit?.id, visit)
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      await guided.skipPracticePlanItem()
      XCTAssertEqual(guided.phase, .practicePlanSummary)
      XCTAssertEqual(guided.practicePlanRows.map(\.disposition), [.finishedSaved, .skipped])
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertEqual(guided.attempts.filter { $0.purpose == .practice }.count, 1)
      await guided.startRecheck()
      XCTAssertEqual(guided.phase, .recheck)
      XCTAssertEqual(guided.rows.count, 13)
      for _ in 0..<13 {
        await observe(guided)
        await guided.next()
      }
      XCTAssertEqual(guided.phase, .comparison)
      XCTAssertEqual(guided.comparison?.rows.count, 13)
      XCTAssertEqual(guided.comparison?.pairedCount, 13)
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertEqual(guided.recheckSummary?.attemptsStarted, 13)
      XCTAssertNotEqual(guided.recheckSummary?.roundId, first.roundId)
      XCTAssertTrue(
        Set(first.attempts.map(\.id)).isDisjoint(
          with: Set(guided.recheckSummary!.attempts.map(\.id))))
      XCTAssertTrue(guided.comparison!.rows.allSatisfy(\.sameAudioWarning))
      await guided.openPracticePlan()
      XCTAssertEqual(guided.phase, .comparison)
      _ = await guided.end().value
    }
    func testFailedSaveRetainsFrozenRetryAndExplicitLeaveWithoutSavingDoesNotWriteAgain() async {
      for retry in [false, true] {
        let capture = FeedbackCapturer()
        let writer = PlanWriter()
        writer.failures = 1
        defer { capture.remove() }
        let guided = await owner(capture, writer: writer)
        await guided.finishEarly()
        await choose(guided, ["r-beginning-rabbit", "r-middle-bread"])
        await self.capture(guided)
        await guided.finishPractice()
        let completion = guided.practiceVisit!.acknowledgedCompletion!
        XCTAssertEqual(guided.practicePlanRows[0].disposition, .finishedNotSaved(.writeFailed))
        XCTAssertTrue(guided.canRetryPracticeSave)
        await guided.nextPracticePlanItem()
        await guided.endPracticePlan()
        await guided.editPracticePlan()
        XCTAssertEqual(guided.planPosition, 1)
        XCTAssertEqual(writer.calls.count, 1)
        if retry {
          await guided.retryPracticeSave()
          XCTAssertEqual(writer.calls, [completion, completion])
          XCTAssertEqual(guided.practicePlanRows[0].completion, completion)
          await guided.nextPracticePlanItem()
          XCTAssertEqual(guided.practicePlanRows[0].disposition, .finishedSaved)
        } else {
          await guided.nextPracticePlanItem(leaveWithoutSaving: true)
          XCTAssertEqual(writer.calls.count, 1)
          XCTAssertEqual(guided.practicePlanRows[0].disposition, .finishedNotSaved(.writeFailed))
        }
        XCTAssertEqual(guided.planPosition, 2)
        await guided.endPracticePlan()
        XCTAssertEqual(guided.practicePlanRows[1].disposition, .leftUnsaved)
        _ = await guided.end().value
      }
    }
    func testNilWriterAndExplicitEndReportCompletionVersusSkippedAndFuturePending() async {
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      let guided = await owner(capture)
      await guided.finishEarly()
      await choose(guided, ["r-beginning-rabbit", "r-middle-bread", "r-end-door"])
      await self.capture(guided)
      await guided.finishPractice()
      XCTAssertEqual(guided.practicePlanRows[0].disposition, .finishedNotSaved(.storeUnavailable))
      await guided.nextPracticePlanItem(leaveWithoutSaving: true)
      await guided.endPracticePlan()
      XCTAssertEqual(guided.phase, .practicePlanSummary)
      XCTAssertEqual(
        guided.practicePlanRows.map(\.disposition),
        [.finishedNotSaved(.storeUnavailable), .leftUnsaved, .pending])
      XCTAssertNil(guided.practicePlanRows[2].visitID)
      await guided.returnSummary()
      XCTAssertEqual(guided.phase, .summary)
      XCTAssertEqual(guided.firstSummary?.plannedCount, 13)
      _ = await guided.end().value
    }
    func testEditKeepsReportUntilNewConfirmationAndReenteredWordGetsFreshVisit() async {
      let capture = FeedbackCapturer()
      let writer = PlanWriter()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await guided.finishEarly()
      await choose(guided, ["r-beginning-rabbit", "r-middle-bread"])
      await self.capture(guided)
      await guided.finishPractice()
      let oldID = guided.practiceVisit?.id
      await guided.nextPracticePlanItem()
      await guided.editPracticePlan()
      let report = guided.practicePlanRows
      XCTAssertEqual(report.map(\.disposition), [.finishedSaved, .leftUnsaved])
      await guided.cancelPracticePlanChoice()
      XCTAssertEqual(guided.phase, .practicePlanSummary)
      XCTAssertEqual(guided.practicePlanRows, report)
      await guided.editPracticePlan()
      guided.togglePracticePlanItem("r-beginning-rabbit")
      await guided.beginPracticePlan()
      XCTAssertEqual(guided.practicePlanRows.count, 1)
      XCTAssertEqual(guided.currentItem?.word, "rabbit")
      XCTAssertEqual(guided.practicePlanRows[0].disposition, .pending)
      XCTAssertNotEqual(guided.practiceVisit?.id, oldID)
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      XCTAssertEqual(writer.calls.count, 1)
      await guided.returnSummary()
      await guided.practice(item: "r-middle-bread")
      XCTAssertFalse(guided.isPracticePlanActive)
      XCTAssertEqual(guided.phase, .practice)
      await guided.returnSummary()
      _ = await guided.end().value
    }
    func testPendingPermissionAndFailedPrivateCleanupBlockPlanReplacementAndSave() async {
      let capture = FeedbackCapturer()
      let writer = PlanWriter()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await guided.finishEarly()
      await choose(guided, ["r-beginning-rabbit", "r-middle-bread"])
      let id = guided.practiceVisit?.id
      capture.delayPermission = true
      let task = Task { await guided.record() }
      await wait { capture.permission != nil }
      await guided.skipPracticePlanItem()
      await guided.editPracticePlan()
      await guided.endPracticePlan()
      await guided.returnSummary()
      XCTAssertEqual(guided.practiceVisit?.id, id)
      capture.permission?.resume(returning: false)
      capture.permission = nil
      await task.value
      XCTAssertFalse(guided.canFinishPractice)
      capture.delayPermission = false
      await self.capture(guided)
      capture.failDiscard = true
      await guided.finishPractice()
      XCTAssertTrue(writer.calls.isEmpty)
      XCTAssertNil(guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(guided.practicePlanRows[0].disposition, .pending)
      await guided.skipPracticePlanItem()
      XCTAssertEqual(guided.planPosition, 1)
      capture.failDiscard = false
      _ = await guided.retake()?.value
      await guided.skipPracticePlanItem()
      XCTAssertEqual(guided.planPosition, 1)
      XCTAssertEqual(guided.practiceVisit?.id, id)
      XCTAssertEqual(guided.practicePlanRows[0].disposition, .pending)
      XCTAssertEqual(guided.feedbackSession.phase, .cleanupBlocked)
      XCTAssertFalse(guided.canTransition)
      let starts = capture.starts
      await guided.record()
      await guided.finishPractice()
      XCTAssertEqual(capture.starts, starts)
      XCTAssertTrue(writer.calls.isEmpty)
      await guided.endPracticePlan()
      XCTAssertEqual(guided.phase, .practice)
      let closed = await guided.end().value
      XCTAssertFalse(closed)
      XCTAssertEqual(guided.phase, .ended)
      _ = await guided.feedbackSession.end().value
      XCTAssertEqual(guided.phase, .ended)
      XCTAssertTrue(guided.feedbackSession.hasLocalMediaCleanupIssue)
    }
    func testPublicCleanupBlocksPlanEndAndEditUntilExplicitRetry() async {
      let capture = FeedbackCapturer()
      let store = PlanExampleStore()
      defer {
        capture.remove()
        store.removeRemaining()
      }
      let guided = await owner(capture, exampleStore: store)
      await guided.finishEarly()
      await choose(guided, ["r-beginning-rabbit", "r-middle-bread"])
      guided.feedbackSession.toggleExample()
      await wait { store.ownedURL != nil }
      store.failRemove = true
      await guided.endPracticePlan()
      XCTAssertEqual(guided.phase, .practice)
      XCTAssertTrue(guided.feedbackSession.exampleCleanupBlocked)
      await guided.editPracticePlan()
      XCTAssertEqual(guided.planPosition, 1)
      store.failRemove = false
      _ = await guided.feedbackSession.retryExampleCleanup().value
      await guided.endPracticePlan()
      XCTAssertEqual(guided.phase, .practicePlanSummary)
      XCTAssertEqual(guided.practicePlanRows[0].disposition, .leftUnsaved)
      _ = await guided.end().value
    }
    func testStaleCaptureContextBackgroundAndReentrantWriterCannotAdvanceAnotherVisit() async {
      let capture = FeedbackCapturer()
      let writer = PlanWriter()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await guided.finishEarly()
      await choose(guided, ["r-beginning-rabbit", "r-middle-bread"])
      await self.capture(guided)
      let oldCallback = capture.finish
      var reentrantAttempt: Task<Void, Never>?
      writer.onRecord = {
        XCTAssertFalse(guided.canTransition)
        let attempt = Task {
          await guided.nextPracticePlanItem()
          await guided.skipPracticePlanItem()
          await guided.editPracticePlan()
          await guided.returnSummary()
          await guided.finishPractice()
        }
        attempt.cancel()
        reentrantAttempt = attempt
      }
      await guided.finishPractice()
      await reentrantAttempt?.value
      XCTAssertEqual(writer.calls.count, 1)
      XCTAssertEqual(guided.planPosition, 1)
      await guided.nextPracticePlanItem()
      let secondID = guided.practiceVisit?.id
      await guided.record()
      await oldCallback?(true)
      XCTAssertEqual(guided.practiceVisit?.id, secondID)
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      guided.stop()
      guided.feedbackSession.appDidEnterBackground()
      _ = await guided.cleanupTask?.value
      XCTAssertEqual(guided.phase, .ended)
      XCTAssertNil(guided.planPosition)
      XCTAssertTrue(guided.selectedPlanItems.isEmpty)
      XCTAssertFalse(guided.canBeginPlan)
      await guided.nextPracticePlanItem()
      await guided.beginPracticePlan()
      XCTAssertEqual(writer.calls.count, 1)
      XCTAssertEqual(guided.practicePlanRows[1].disposition, .leftUnsaved)
    }
    func testProcessingPauseSurvivesLocalPlanAndExplicitRecheckAndContextDriftEndsChooser() async {
      let capture = FeedbackCapturer()
      let processor = PlanProcessor()
      processor.reasons = ["cleanup_unconfirmed"]
      defer { capture.remove() }
      let guided = await owner(capture, processor: processor)
      await observe(guided)
      await guided.finishEarly()
      let first = guided.firstSummary
      await choose(guided, ["r-middle-bread"])
      await self.capture(guided)
      XCTAssertTrue(guided.feedbackSession.canReplay)
      XCTAssertFalse(guided.canCheck)
      XCTAssertTrue(guided.feedbackSession.sharedProcessingPaused)
      await guided.skipPracticePlanItem()
      await guided.startRecheck()
      XCTAssertEqual(guided.phase, .recheck)
      XCTAssertTrue(guided.feedbackSession.sharedProcessingPaused)
      XCTAssertEqual(guided.firstSummary, first)
      await guided.finishEarly()
      _ = await guided.end().value
      let other = await owner(capture)
      await other.finishEarly()
      await other.openPracticePlan()
      other.togglePracticePlanItem("r-middle-bread")
      other.feedbackSession.practiceContext = .adult
      XCTAssertEqual(other.phase, .ended)
      let cleanup = other.cleanupTask
      let cleanupReleased = await cleanup?.value
      XCTAssertEqual(cleanupReleased, true)
      XCTAssertTrue(other.selectedPlanItems.isEmpty)
      XCTAssertTrue(other.suggestedPracticeItems.isEmpty)
      XCTAssertFalse(other.canBeginPlan)
      other.feedbackSession.soundAdultConfirmed = true
      other.feedbackSession.soundProcessingEnabled = true
      XCTAssertFalse(other.feedbackSession.canCheckSound)
    }
  }

  @MainActor
  private final class PlanProcessor: ResearchFeedbackProcessing {
    var reasons: [String?] = []
    var calls = 0, markRequest = true
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
      let index = calls
      calls += 1
      let audio = try FeedbackPCM.read(recording.url)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attemptId, audio: audio, prompt: prompt, practiceContext: practiceContext)
      let reason = reasons.indices.contains(index) ? reasons[index] : nil
      let value = try FeedbackContract.decode(
        FeedbackFixture.json(
          FeedbackFixture.response(
            body, audio: audio, reason: reason, unsupported: prompt.targetUnsupported)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: prompt.targetUnsupported)
      if markRequest { onEvent(.requestStarted) }
      return value
    }
  }
  @MainActor
  private final class PlanWriter: ResearchGuidedPracticeParticipationRecording {
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
  private final class PlanExampleLoader: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated unit fixture", licenseId: "Generated",
        licenseURL: URL(string: "https://example.invalid/license")!,
        sourceURL: URL(string: "https://example.invalid/reference")!,
        attribution: "Generated PCM, no human reference", changes: "Generated",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data { bytes }
  }
  @MainActor
  private final class PlanExampleStore: ResearchPracticeExampleStoring {
    var ownedURL: URL?, failRemove = false
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-plan-example-\(UUID()).wav")
      ownedURL = url
      try data.write(to: url)
      return url
    }
    func remove(_ url: URL) throws {
      guard !failRemove, ownedURL == url else { throw ResearchPracticeExampleError.cleanupFailed }
      try FileManager.default.removeItem(at: url)
      ownedURL = nil
    }
    func removeRemaining() {
      if let ownedURL { try? FileManager.default.removeItem(at: ownedURL) }
      ownedURL = nil
    }
  }
#endif
