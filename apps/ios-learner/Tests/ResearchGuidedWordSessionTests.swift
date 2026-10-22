#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchGuidedWordSessionTests: XCTestCase {
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Controlled generated operation did not finish")
    }
    private func make(
      _ capture: FeedbackCapturer, _ processor: GuidedWordProcessor = GuidedWordProcessor(),
      player: FeedbackPlayer = FeedbackPlayer()
    ) async -> ResearchGuidedWordSession {
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: player, processor: processor)
      let session = ResearchGuidedWordSession(feedbackSession: feedback)
      session.localProcessingEnabled = true
      let started = await session.start(age: 9)
      XCTAssertTrue(started)
      return session
    }
    private func observe(_ session: ResearchGuidedWordSession) async {
      await session.record()
      session.stop()
      session.check()
      await wait { !session.feedbackSession.isProcessing }
    }
    func testExactRosterFullCatalogAndChildEntryRequireExplicitOptIn() async {
      XCTAssertTrue(ResearchGuidedWordSession.catalogValid)
      let roster = ResearchGuidedWordSession.roster
      XCTAssertEqual(
        roster.map(\.word),
        [
          "rabbit", "bread", "door", "baby", "banana", "backpack", "sky", "vase", "yo-yo", "thumb",
          "feather", "ring", "treasure",
        ])
      XCTAssertEqual(roster[3].prompt.id, "b-beginning-baby")
      XCTAssertEqual(roster[3].catalogPromptIds, ["b-beginning-baby", "b-middle-baby"])
      XCTAssertEqual(roster[5].catalogPromptIds, ["k-middle-backpack", "k-end-backpack"])
      XCTAssertTrue(roster.last!.prompt.targetUnsupported)
      for age in [5, 6, 12, 13] {
        let capture = FeedbackCapturer()
        defer { capture.remove() }
        let session = ResearchGuidedWordSession(
          feedbackSession: makeControlledFeedbackSession(
            capturer: capture, player: FeedbackPlayer(), processor: GuidedWordProcessor()))
        let refused = await session.start(age: age)
        XCTAssertFalse(refused)
        session.localProcessingEnabled = true
        let started = await session.start(age: age)
        XCTAssertEqual(started, (6...12).contains(age))
        XCTAssertEqual(capture.permissions, 0)
        XCTAssertEqual(capture.starts, 0)
        _ = await session.end().value
      }
    }
    func testAttemptsSubmissionsAndSimulatedRequestsHaveSeparateExplicitBoundaries() async {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      defer { capture.remove() }
      let session = await make(capture, processor)
      XCTAssertEqual(session.attempts.count, 0)
      await session.record()
      XCTAssertEqual(session.attempts.count, 1)
      XCTAssertNil(session.attempts[0].audioSha256)
      XCTAssertEqual(processor.calls, 0)
      session.stop()
      XCTAssertNotNil(session.attempts[0].audioSha256)
      XCTAssertFalse(session.attempts[0].submitted)
      session.check()
      XCTAssertTrue(session.attempts[0].submitted)
      XCTAssertFalse(session.attempts[0].requestStarted)
      XCTAssertFalse(session.canNext)
      await wait { !session.feedbackSession.isProcessing }
      XCTAssertTrue(session.attempts[0].requestStarted)
      XCTAssertTrue(session.attempts[0].validated)
      XCTAssertEqual(session.rows[0].disposition, .modelMatched)
      await session.finishEarly()
      XCTAssertEqual(session.firstSummary?.plannedCount, 13)
      XCTAssertEqual(session.firstSummary?.attemptsStarted, 1)
      XCTAssertEqual(session.firstSummary?.submissions, 1)
      XCTAssertEqual(session.firstSummary?.transportStarts, 1)
      XCTAssertEqual(session.firstSummary?.validatedResponses, 1)
      XCTAssertEqual(session.firstSummary?.dispositionCounts.values.reduce(0, +), 13)
      _ = await session.end().value
    }
    func testPermissionDenialAndCancelledPermissionKeepAttemptsWithoutPrimarySubmission() async {
      let capture = FeedbackCapturer()
      capture.delayPermission = true
      defer { capture.remove() }
      let session = await make(capture)
      let record = Task { await session.record() }
      await wait { capture.permission != nil }
      XCTAssertEqual(session.attempts.count, 1)
      XCTAssertFalse(session.canTransition)
      await session.skip()
      await session.finishEarly()
      XCTAssertEqual(session.phase, .firstRound)
      capture.permission?.resume(returning: false)
      capture.permission = nil
      await record.value
      XCTAssertEqual(session.attempts[0].terminal, .permissionDenied)
      XCTAssertNil(session.rows[0].primaryAttemptId)
      let second = Task { await session.record() }
      await wait { capture.permission != nil }
      _ = await session.retake()?.value
      XCTAssertEqual(session.attempts[1].terminal, .permissionCancelled)
      await session.record()
      XCTAssertEqual(capture.permissions, 2)
      capture.permission?.resume(returning: true)
      capture.permission = nil
      await second.value
      XCTAssertEqual(capture.starts, 0)
      await session.skip()
      await session.finishEarly()
      XCTAssertEqual(session.firstSummary?.attemptsStarted, 2)
      XCTAssertEqual(session.firstSummary?.submissions, 0)
      XCTAssertEqual(session.firstSummary?.rows[0].disposition, .skipped)
      XCTAssertEqual(session.firstSummary?.dispositionCounts[.notReached], 12)
      _ = await session.end().value
    }
    func testPermissionSheetInactiveGrantResumesSameOwnerOnlyAfterActive() async {
      let capture = FeedbackCapturer()
      capture.delayPermission = true
      defer { capture.remove() }
      let session = await make(capture)
      let task = Task { await session.record() }
      await wait { capture.permission != nil }
      let identity = session.attempts[0].identity
      session.feedbackSession.appDidBecomeInactive()
      capture.permission?.resume(returning: true)
      capture.permission = nil
      await task.value
      XCTAssertEqual(session.phase, .firstRound)
      XCTAssertEqual(session.feedbackSession.phase, .requestingPermission)
      XCTAssertEqual(capture.starts, 0)
      XCTAssertFalse(session.canTransition)
      await session.record()
      XCTAssertEqual(capture.permissions, 1)
      session.feedbackSession.appDidBecomeActive()
      XCTAssertEqual(capture.starts, 1)
      XCTAssertEqual(session.attempts[0].identity, identity)
      session.stop()
      _ = await session.retake()?.value
      await session.finishEarly()
      XCTAssertEqual(session.firstSummary?.attemptsStarted, 1)
      _ = await session.end().value
    }
    func testCaptureFailureAndDiscardedRetryDoNotReplaceFirstSubmittedOutcome() async {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      processor.reasons = ["requested_word_not_matched"]
      defer { capture.remove() }
      let session = await make(capture, processor)
      await session.record()
      await capture.finish?(false)
      await wait { session.feedbackSession.phase == .failed(.invalidRecording) }
      XCTAssertEqual(session.attempts[0].terminal, .captureFailed)
      _ = await session.retake()?.value
      await session.record()
      session.stop()
      _ = await session.retake()?.value
      XCTAssertEqual(session.attempts[1].terminal, .recordedDiscarded)
      XCTAssertEqual(session.rows[0].disposition, .notReached)
      await observe(session)
      let primary = session.rows[0].primaryAttemptId
      XCTAssertEqual(session.rows[0].disposition, .modelNotMatched)
      _ = await session.retake()?.value
      await session.record()
      // Sole owner also refuses a programmatic retry.
      await session.feedbackSession.startRecording()
      XCTAssertEqual(capture.permissions, 3)
      XCTAssertEqual(session.rows[0].primaryAttemptId, primary)
      XCTAssertEqual(processor.calls, 1)
      await session.finishEarly()
      XCTAssertEqual(session.firstSummary?.attemptsStarted, 3)
      XCTAssertEqual(session.firstSummary?.submissions, 1)
      _ = await session.end().value
    }
    func testMissingRequestMarkerCannotBecomeValidatedPairedObservation() async {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      processor.markRequest = false
      defer { capture.remove() }
      let session = await make(capture, processor)
      await observe(session)
      XCTAssertFalse(session.attempts[0].validated)
      XCTAssertEqual(session.attempts[0].terminal, .invalidResponse)
      XCTAssertEqual(session.rows[0].disposition, .checkUnavailable)
      await session.finishEarly()
      XCTAssertEqual(session.firstSummary?.transportStarts, 0)
      XCTAssertEqual(session.firstSummary?.validatedResponses, 0)
      _ = await session.end().value
    }
    func testDeclarationRejectionEndsComparabilityBeforeSimulatedTransport() async {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      processor.rejectDeclaration = true
      defer { capture.remove() }
      let session = await make(capture, processor)
      await observe(session)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(session.attempts[0].terminal, .invalidResponse)
      XCTAssertFalse(session.attempts[0].requestStarted)
      XCTAssertFalse(session.attempts[0].validated)
      XCTAssertNil(session.comparison)
    }
    func testCancelledCheckAndOldCallbacksCannotAffectNextOwnedTake() async {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      processor.delay = true
      defer { capture.remove() }
      let session = await make(capture, processor)
      await session.record()
      session.stop()
      session.check()
      await wait { processor.pending != nil }
      let oldEvent = processor.events.last!
      _ = await session.retake()?.value
      XCTAssertEqual(session.attempts[0].terminal, .checkCancelled)
      await session.next()
      await session.record()
      session.stop()
      let nextIdentity = session.attempts[1].identity
      oldEvent(.requestStarted)
      processor.release()
      await wait { processor.returned }
      for _ in 0..<30 { await Task.yield() }
      XCTAssertFalse(session.attempts[0].validated)
      XCTAssertFalse(session.attempts[1].submitted)
      XCTAssertEqual(session.attempts[1].identity, nextIdentity)
      XCTAssertEqual(session.rows[0].disposition, .checkUnavailable)
      XCTAssertEqual(session.rows[1].disposition, .notReached)
      _ = await session.retake()?.value
      await session.finishEarly()
      _ = await session.end().value
    }
    func testCompleteMixedRoundsPracticeAndFreshIdsKeepFirstImmutableAndPairsLexicalOnly()
      async throws
    {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      let reasons: [String?] = [
        nil, "requested_word_not_matched", "recognition_uncertain", "single_word_required",
        "speech_not_detected", "model_unavailable", nil, nil, nil, nil, nil, nil, nil,
      ]
      processor.reasons = reasons + [nil] + reasons
      defer { capture.remove() }
      let session = await make(capture, processor)
      for _ in 0..<13 {
        await observe(session)
        await session.next()
      }
      let first = try XCTUnwrap(session.firstSummary)
      XCTAssertEqual(first.plannedCount, 13)
      XCTAssertEqual(first.attemptsStarted, 13)
      XCTAssertEqual(first.validatedResponses, 13)
      XCTAssertEqual(first.rows.last?.observation?.targetUnsupported, true)
      XCTAssertEqual(first.dispositionCounts[.recognitionUncertain], 1)
      XCTAssertEqual(first.dispositionCounts[.checkUnavailable], 1)
      await session.practice(item: first.rows[1].id)
      await observe(session)
      await session.feedbackSession.togglePlayback()
      XCTAssertTrue(session.feedbackSession.isPlaying)
      await session.returnSummary()
      XCTAssertEqual(session.firstSummary, first)
      XCTAssertEqual(session.attempts.filter { $0.purpose == .practice }.count, 1)
      await session.startRecheck()
      XCTAssertEqual(session.childContext, first.context)
      XCTAssertFalse(session.feedbackSession.canReplay)
      for _ in 0..<13 {
        await observe(session)
        await session.next()
      }
      let second = try XCTUnwrap(session.recheckSummary)
      let comparison = try XCTUnwrap(session.comparison)
      XCTAssertEqual(session.phase, .comparison)
      XCTAssertEqual(session.firstSummary, first)
      XCTAssertNotEqual(first.roundId, second.roundId)
      XCTAssertTrue(Set(first.attempts.map(\.id)).isDisjoint(with: Set(second.attempts.map(\.id))))
      XCTAssertTrue(
        Set(first.attempts.map { $0.identity.captureId }).isDisjoint(
          with: Set(second.attempts.map { $0.identity.captureId })))
      XCTAssertTrue(
        Set(first.attempts.map { $0.identity.takeId }).isDisjoint(
          with: Set(second.attempts.map { $0.identity.takeId })))
      XCTAssertEqual(comparison.pairedCount, 9)
      // Same generated bytes are only a warning.
      XCTAssertTrue(comparison.rows.allSatisfy(\.sameAudioWarning))
      XCTAssertEqual(processor.contexts, Array(repeating: .child(ageYears: 9), count: 27))
      XCTAssertEqual(processor.urls, Array(repeating: capture.url, count: 27))
      XCTAssertFalse(session.feedbackSession.canReplay)
      _ = await session.end().value
    }
    func testContextOptInPromptOrModeDriftInvalidatesAndAdultSoundRemainsExcluded() async {
      for mutation in 0..<4 {
        let capture = FeedbackCapturer()
        defer { capture.remove() }
        let session = await make(capture)
        await session.record()
        session.stop()
        switch mutation {
        case 0: session.feedbackSession.practiceContext = .adult
        case 1: session.feedbackSession.localProcessingEnabled = false
        case 2: session.feedbackSession.selectedPrompt = ResearchFeedbackCatalog.prompts[1]
        default: session.feedbackSession.practiceMode = "free"
        }
        _ = await session.cleanupTask?.value
        XCTAssertEqual(session.phase, .ended)
        XCTAssertEqual(session.attempts[0].terminal, .recordedDiscarded)
        session.feedbackSession.practiceContext = .adult
        session.feedbackSession.selectedPrompt = ResearchFeedbackCatalog.prompts[1]
        session.feedbackSession.practiceMode = "free"
        session.feedbackSession.soundAdultConfirmed = true
        session.feedbackSession.soundProcessingEnabled = true
        XCTAssertFalse(session.feedbackSession.canCheckSound)
        XCTAssertFalse(session.feedbackSession.setupEditable)
        XCTAssertFalse(session.feedbackSession.canRecord)
        XCTAssertNil(session.comparison)
      }
    }
    func testBackgroundAndReentrantEndTerminatePendingOwnerExactlyOnce() async {
      for background in [false, true] {
        let capture = FeedbackCapturer()
        capture.delayPermission = true
        defer { capture.remove() }
        let session = await make(capture)
        let pending = Task { await session.record() }
        await wait { capture.permission != nil }
        if background {
          session.feedbackSession.appDidEnterBackground()
        } else {
          _ = session.feedbackSession.end()
        }
        _ = session.feedbackSession.end()
        XCTAssertEqual(session.phase, .ended)
        XCTAssertEqual(session.attempts.count, 1)
        XCTAssertEqual(session.attempts[0].terminal, .permissionCancelled)
        XCTAssertFalse(session.canTransition)
        capture.permission?.resume(returning: true)
        capture.permission = nil
        await pending.value
        _ = await session.cleanupTask?.value
        XCTAssertEqual(capture.starts, 0)
        XCTAssertEqual(session.attempts.count, 1)
        XCTAssertEqual(session.attempts[0].terminal, .permissionCancelled)
        XCTAssertNil(session.comparison)
      }
    }
    func testPersistentServicePauseAllowsListeningReplayButSurvivesRoundTransitions() async {
      let capture = FeedbackCapturer()
      let processor = GuidedWordProcessor()
      processor.reasons = ["cleanup_unconfirmed"]
      defer { capture.remove() }
      let session = await make(capture, processor)
      await observe(session)
      XCTAssertTrue(session.feedbackSession.sharedProcessingPaused)
      XCTAssertTrue(session.feedbackSession.canReplay)
      await session.feedbackSession.togglePlayback()
      XCTAssertTrue(session.feedbackSession.isPlaying)
      await session.finishEarly()
      let first = session.firstSummary
      await session.practice(item: ResearchGuidedWordSession.roster[1].id)
      await session.record()
      session.stop()
      XCTAssertTrue(session.feedbackSession.canReplay)
      XCTAssertTrue(session.feedbackSession.canPlayExample)
      XCTAssertFalse(session.canCheck)
      XCTAssertTrue(session.feedbackSession.sharedProcessingPaused)
      await session.returnSummary()
      await session.startRecheck()
      XCTAssertEqual(session.phase, .recheck)
      XCTAssertEqual(session.firstSummary, first)
      XCTAssertTrue(session.feedbackSession.sharedProcessingPaused)
      await session.finishEarly()
      _ = await session.end().value
    }
    func testPrivateCleanupFailureBlocksNewStageAndKeepsThirteenRows() async {
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      let session = await make(capture)
      await observe(session)
      capture.failDiscard = true
      await session.next()
      XCTAssertEqual(session.phase, .firstRound)
      XCTAssertEqual(session.currentItem?.word, "rabbit")
      XCTAssertFalse(session.canTransition)
      XCTAssertEqual(session.rows.count, 13)
      XCTAssertEqual(session.feedbackSession.phase, .cleanupBlocked)
      await session.finishEarly()
      XCTAssertNil(session.firstSummary)
      capture.failDiscard = false
      // Exact file can be removed; sticky cleanup block still ends comparability.
      _ = await session.feedbackSession.end().value
      XCTAssertEqual(session.phase, .ended)
    }
    func testPublicExampleCleanupBlocksNextPracticeReturnAndRecheckUntilExactRetry() async {
      let capture = FeedbackCapturer()
      let loader = GuidedExampleLoader()
      let store = GuidedExampleStore()
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(),
        processor: GuidedWordProcessor(), exampleLoader: loader, exampleStore: store)
      let session = ResearchGuidedWordSession(feedbackSession: feedback)
      session.localProcessingEnabled = true
      let started = await session.start(age: 9)
      XCTAssertTrue(started)
      defer {
        capture.remove()
        store.forceRemove()
      }
      await observe(session)
      feedback.toggleExample()
      await wait { feedback.exampleState == .playing }
      store.failRemove = true
      await session.next()
      XCTAssertTrue(feedback.exampleCleanupBlocked)
      XCTAssertEqual(session.currentItem?.word, "rabbit")
      XCTAssertFalse(session.canTransition)
      await session.finishEarly()
      XCTAssertNil(session.firstSummary)
      store.failRemove = false
      _ = await feedback.retryExampleCleanup().value
      await session.finishEarly()
      let first = session.firstSummary
      await session.practice(item: ResearchGuidedWordSession.roster[1].id)
      feedback.toggleExample()
      await wait { feedback.exampleState == .playing }
      store.failRemove = true
      await session.returnSummary()
      XCTAssertEqual(session.phase, .practice)
      await session.startRecheck()
      XCTAssertEqual(session.phase, .practice)
      XCTAssertEqual(session.firstSummary, first)
      store.failRemove = false
      _ = await feedback.retryExampleCleanup().value
      await session.returnSummary()
      await session.startRecheck()
      XCTAssertEqual(session.phase, .recheck)
      XCTAssertNil(store.ownedURL)
      XCTAssertEqual(store.writes, 2)
      await session.finishEarly()
      _ = await session.end().value
    }
    func testPracticeReturnRevokesPendingExampleBeforeFreshRecheckAndLateLoad() async {
      let capture = FeedbackCapturer()
      let loader = GuidedExampleLoader()
      let store = GuidedExampleStore()
      let player = FeedbackPlayer()
      loader.delayed = true
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: player,
        processor: GuidedWordProcessor(), exampleLoader: loader, exampleStore: store)
      let session = ResearchGuidedWordSession(feedbackSession: feedback)
      session.localProcessingEnabled = true
      let started = await session.start(age: 9)
      XCTAssertTrue(started)
      defer {
        capture.remove()
        store.forceRemove()
      }
      await session.finishEarly()
      let first = session.firstSummary
      await session.practice(item: ResearchGuidedWordSession.roster[1].id)
      feedback.toggleExample()
      await wait { loader.pending != nil }
      await session.returnSummary()
      await session.startRecheck()
      loader.release()
      await wait { loader.returned }
      for _ in 0..<30 { await Task.yield() }
      XCTAssertEqual(session.phase, .recheck)
      XCTAssertEqual(feedback.exampleState, .idle)
      XCTAssertEqual(store.writes, 0)
      XCTAssertEqual(player.starts, 0)
      XCTAssertNil(store.ownedURL)
      XCTAssertEqual(session.firstSummary, first)
      await session.finishEarly()
      _ = await session.end().value
    }
    func testPendingExistingSoundResetBlocksEntryAndFailedControlPausePersists() async {
      let capture = FeedbackCapturer()
      let sound = GuidedPriorSoundProcessor()
      defer { capture.remove() }
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(),
        processor: GuidedWordProcessor(), soundProcessor: sound)
      feedback.selectedPrompt = ResearchFeedbackCatalog.prompts[1]
      feedback.practiceContext = .adult
      feedback.localProcessingEnabled = true
      feedback.soundAdultConfirmed = true
      feedback.soundProcessingEnabled = true
      _ = await feedback.awaitPendingAudioCleanup()
      await feedback.startRecording()
      feedback.stopRecording()
      feedback.checkSound()
      await wait { !feedback.isProcessing }
      _ = await feedback.retake()?.value
      await wait { sound.controlPending != nil }
      let session = ResearchGuidedWordSession(feedbackSession: feedback)
      session.localProcessingEnabled = true
      let refused = await session.start(age: 9)
      XCTAssertFalse(refused)
      XCTAssertEqual(session.phase, .setup)
      sound.release()
      await wait { feedback.sharedProcessingPaused }
      let started = await session.start(age: 9)
      XCTAssertTrue(started)
      XCTAssertTrue(feedback.sharedProcessingPaused)
      XCTAssertFalse(feedback.canCheckSound)
      XCTAssertEqual(sound.observations, 1)
      await session.finishEarly()
      _ = await session.end().value
    }
    func testBoundedAttemptLimitIncludesUnsubmittedPracticeAndNoAutomaticCapture() async {
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      let session = await make(capture)
      await session.finishEarly()
      await session.practice(item: ResearchGuidedWordSession.roster[0].id)
      for _ in 0..<128 {
        await session.record()
        session.stop()
        _ = await session.retake()?.value
      }
      XCTAssertEqual(session.attempts.count, 128)
      XCTAssertEqual(capture.permissions, 128)
      XCTAssertFalse(session.canRecord)
      await session.record()
      await session.feedbackSession.startRecording()
      XCTAssertEqual(capture.permissions, 128)
      XCTAssertEqual(session.firstSummary?.attemptsStarted, 0)
      await session.returnSummary()
      await session.startRecheck()
      XCTAssertEqual(session.phase, .recheck)
      XCTAssertFalse(session.canRecord)
      await session.finishEarly()
      _ = await session.end().value
    }
  }

  /// Generated processor only: explicit simulated requests, actual local serialization/decoder,
  /// no HTTP, models, human recording or accuracy evidence.
  @MainActor
  private final class GuidedWordProcessor: ResearchFeedbackProcessing {
    var reasons: [String?] = []
    var calls = 0, markRequest = true, rejectDeclaration = false, delay = false, returned = false
    var contexts: [ResearchPracticeContext] = [], urls: [URL] = []
    var events: [@MainActor (ResearchFeedbackProcessingEvent) -> Void] = []
    var pending: CheckedContinuation<Void, Never>?
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
      contexts.append(practiceContext)
      urls.append(recording.url)
      events.append(onEvent)
      if rejectDeclaration {
        onEvent(.declarationRejected)
        throw RecordingFeedbackError.invalidResponse
      }
      let audio = try FeedbackPCM.read(recording.url)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attemptId, audio: audio,
        prompt: prompt, practiceContext: practiceContext)
      let reason = reasons.indices.contains(index) ? reasons[index] : nil
      let value = try FeedbackContract.decode(
        FeedbackFixture.json(
          FeedbackFixture.response(
            body, audio: audio, reason: reason, unsupported: prompt.targetUnsupported)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio),
        targetUnsupported: prompt.targetUnsupported)
      if markRequest { onEvent(.requestStarted) }
      if delay { await withCheckedContinuation { pending = $0 } }
      returned = true
      return value
    }
    func release() {
      pending?.resume()
      pending = nil
    }
  }
  @MainActor
  private final class GuidedExampleLoader: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    var delayed = false, returned = false
    var pending: CheckedContinuation<Data, Never>?
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated test fixture", licenseId: "Generated PCM",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated unit waveform; no human reference",
        changes: "Generated locally for ownership tests",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data {
      let value = delayed ? await withCheckedContinuation { pending = $0 } : bytes
      returned = true
      return value
    }
    func release() {
      pending?.resume(returning: bytes)
      pending = nil
    }
  }
  @MainActor
  private final class GuidedExampleStore: ResearchPracticeExampleStoring {
    var ownedURL: URL?, failRemove = false, writes = 0
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-guided-example-" + UUID().uuidString + ".wav")
      try data.write(to: url)
      ownedURL = url
      writes += 1
      return url
    }
    func remove(_ url: URL) throws {
      guard !failRemove, ownedURL == url else { throw ResearchPracticeExampleError.cleanupFailed }
      try FileManager.default.removeItem(at: url)
      ownedURL = nil
    }
    func forceRemove() {
      if let ownedURL { try? FileManager.default.removeItem(at: ownedURL) }
      ownedURL = nil
    }
  }
  @MainActor
  private final class GuidedPriorSoundProcessor: ResearchSoundProcessing {
    var controlPending: CheckedContinuation<Void, Never>?
    var observations = 0
    func declaration() async throws -> ResearchSoundDeclaration {
      .init(
        serverNonce: "33333333-3333-4333-8333-333333333333",
        csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      try ResearchSoundContract.prepare(
        audio: ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url)),
        declaration: declaration, context: context)
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      observations += 1
      return .init(status: .inconclusive, reason: "model_unavailable", preference: nil)
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws {}
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {
      await withCheckedContinuation { controlPending = $0 }
      throw RecordingFeedbackError.serviceUnavailable
    }
    func release() {
      controlPending?.resume()
      controlPending = nil
    }
  }
#endif
