#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchGuidedPracticeParticipationTests: XCTestCase {
    private let breadId = "r-middle-bread"
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Generated ownership operation did not finish")
    }
    private func owner(
      _ capture: FeedbackCapturer,
      writer: (any ResearchGuidedPracticeParticipationRecording)? = nil,
      processor: HistoryWordProcessor = HistoryWordProcessor(),
      loader: HistoryExampleLoader? = nil, store: HistoryExampleStore? = nil,
      now: @escaping @MainActor () -> Date = { Date(timeIntervalSince1970: 1_700_000_000) }
    ) async -> ResearchGuidedWordSession {
      let feedback = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(),
        processor: processor, exampleLoader: loader, exampleStore: store)
      let owner = ResearchGuidedWordSession(
        feedbackSession: feedback, participationWriter: writer, now: now)
      owner.localProcessingEnabled = true
      let started = await owner.start(age: 9)
      XCTAssertTrue(started)
      return owner
    }
    private func practice(_ owner: ResearchGuidedWordSession, itemId: String = "r-middle-bread")
      async
    {
      await owner.finishEarly()
      await owner.practice(item: itemId)
      XCTAssertEqual(owner.phase, .practice)
    }
    private func capture(_ owner: ResearchGuidedWordSession) async {
      await owner.record()
      owner.stop()
      XCTAssertEqual(owner.feedbackSession.phase, .review)
    }
    func testClosedFullPromptMappingMatchesAllThirteenExistingAreasAndRejectsSpoofs() async {
      let roster = ResearchGuidedWordSession.roster
      XCTAssertEqual(
        roster.map { ResearchGuidedPracticeParticipationMapping.soundID(for: $0.prompt) },
        ["r", "r", "r", "b", "n", "k", "s", "v", "y", "th", "voiced-th", "ng", "zh"])
      XCTAssertTrue(roster.last!.prompt.targetUnsupported)
      for index in [4, 7] {
        XCTAssertNil(
          ResearchGuidedPracticeParticipationMapping.soundID(
            for: ResearchFeedbackCatalog.prompts[index]))
      }
      let canonical = roster[1].prompt
      let spoofs: [ResearchFeedbackPrompt] = [
        .init(
          id: canonical.id, word: "door", phones: canonical.phones, occurrenceIndex: 1,
          targetPhone: "R"),
        .init(
          id: canonical.id, word: canonical.word, phones: ["B", "W", "EH", "D"], occurrenceIndex: 1,
          targetPhone: "R"),
        .init(
          id: canonical.id, word: canonical.word, phones: canonical.phones, occurrenceIndex: 0,
          targetPhone: "R"),
        .init(
          id: canonical.id, word: canonical.word, phones: canonical.phones, occurrenceIndex: 1,
          targetPhone: "W"),
        .init(
          id: "unknown", word: canonical.word, phones: canonical.phones, occurrenceIndex: 1,
          targetPhone: "R"),
      ]
      for prompt in spoofs {
        XCTAssertNil(ResearchGuidedPracticeParticipationMapping.soundID(for: prompt))
      }
    }
    func testFirstRoundCaptureOpeningAndListeningAloneNeverQualifyOrSavePractice() async {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      let loader = HistoryExampleLoader()
      let store = HistoryExampleStore()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let guided = await owner(capture, writer: writer, loader: loader, store: store)
      await self.capture(guided)
      XCTAssertFalse(guided.canFinishPractice)
      await guided.finishPractice()
      await guided.finishEarly()
      let first = guided.firstSummary
      await guided.practice(item: breadId)
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      XCTAssertFalse(guided.canFinishPractice)
      await guided.finishPractice()
      guided.feedbackSession.toggleExample()
      await wait { guided.feedbackSession.exampleState == .playing }
      XCTAssertFalse(guided.canFinishPractice)
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 0)
      await guided.returnSummary()
      XCTAssertNil(guided.practiceVisit)
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertEqual(guided.firstSummary?.attemptsStarted, 1)
      _ = await guided.end().value
    }
    func testExplicitFinishCleansBeforeWritingOnceAndBlocksCompletedOwnerActions() async throws {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await practice(guided)
      let first = guided.firstSummary
      let visitID = try XCTUnwrap(guided.practiceVisit?.id)
      await self.capture(guided)
      XCTAssertEqual(writer.calls.count, 0)
      XCTAssertTrue(guided.canFinishPractice)
      writer.onRecord = {
        XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
        XCTAssertFalse(guided.feedbackSession.canReplay)
        XCTAssertFalse(guided.canTransition)
      }
      await guided.finishPractice()
      XCTAssertEqual(guided.practiceVisit?.completionState, .saved)
      XCTAssertEqual(writer.calls.count, 1)
      XCTAssertEqual(writer.calls[0].id, visitID)
      XCTAssertEqual(writer.calls[0].soundID, "r")
      XCTAssertEqual(writer.calls[0].wordCount, 1)
      XCTAssertFalse(guided.canRecord)
      XCTAssertFalse(guided.canCheck)
      XCTAssertFalse(guided.canFinishPractice)
      await guided.finishPractice()
      await guided.retryPracticeSave()
      _ = await guided.retake()?.value
      await guided.record()
      await guided.feedbackSession.startRecording()
      guided.feedbackSession.checkRecording()
      XCTAssertEqual(capture.permissions, 1)
      XCTAssertEqual(writer.calls.count, 1)
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertEqual(guided.attempts.first?.practiceVisitId, visitID)
      XCTAssertEqual(guided.attempts.first?.terminal, .recordedDiscarded)
      await guided.returnSummary()
      await guided.startRecheck()
      XCTAssertEqual(guided.rows.count, 13)
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertFalse(guided.feedbackSession.canCheckSound)
      await guided.finishEarly()
      _ = await guided.end().value
    }
    func testFailedWriteRetryUsesSameFrozenPayloadAndNewVisitNeedsNewCapture() async throws {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      writer.failuresRemaining = 1
      var clocks = 0
      defer { capture.remove() }
      let guided = await owner(
        capture, writer: writer,
        now: {
          clocks += 1
          return Date(timeIntervalSince1970: Double(1_700_000_000 + clocks))
        })
      await practice(guided)
      await self.capture(guided)
      await guided.finishPractice()
      let snapshot = try XCTUnwrap(guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(guided.practiceVisit?.completionState, .completedNotSaved(.writeFailed))
      XCTAssertTrue(guided.canRetryPracticeSave)
      XCTAssertFalse(guided.canRecord)
      await guided.finishPractice()
      await guided.retryPracticeSave()
      await guided.retryPracticeSave()
      XCTAssertEqual(guided.practiceVisit?.completionState, .saved)
      XCTAssertEqual(writer.calls, [snapshot, snapshot])
      XCTAssertEqual(clocks, 1)
      await guided.practice(item: breadId)
      let freshID = try XCTUnwrap(guided.practiceVisit?.id)
      XCTAssertNotEqual(freshID, snapshot.id)
      XCTAssertFalse(guided.canFinishPractice)
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 2)
      await self.capture(guided)
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 3)
      XCTAssertEqual(writer.calls.last?.id, freshID)
      XCTAssertEqual(clocks, 2)
      _ = await guided.end().value
    }
    func testNilWriterAcknowledgesButNeverClaimsSavedOrOffersRetry() async {
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      let guided = await owner(capture)
      await practice(guided)
      await self.capture(guided)
      await guided.finishPractice()
      XCTAssertEqual(guided.practiceVisit?.completionState, .completedNotSaved(.storeUnavailable))
      XCTAssertNotNil(guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertFalse(guided.canRetryPracticeSave)
      XCTAssertFalse(guided.canFinishPractice)
      XCTAssertFalse(guided.canRecord)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      await guided.retryPracticeSave()
      XCTAssertEqual(guided.practiceVisit?.completionState, .completedNotSaved(.storeUnavailable))
      _ = await guided.end().value
    }
    func testDeniedPermissionAndInvalidPCMDoNotQualifyAndPendingReplacementBlocksFinish() async {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      capture.delayPermission = true
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await practice(guided)
      let denied = Task { await guided.record() }
      await wait { capture.permission != nil }
      await guided.finishPractice()
      XCTAssertFalse(guided.canFinishPractice)
      capture.permission?.resume(returning: false)
      capture.permission = nil
      await denied.value
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      XCTAssertEqual(writer.calls.count, 0)
      capture.delayPermission = false
      await self.capture(guided)
      _ = await guided.retake()?.value
      XCTAssertTrue(guided.practiceVisit!.hasValidCapture)
      capture.delayPermission = true
      let pending = Task { await guided.record() }
      await wait { capture.permission != nil }
      XCTAssertFalse(guided.canFinishPractice)
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 0)
      _ = await guided.retake()?.value
      capture.permission?.resume(returning: true)
      capture.permission = nil
      await pending.value
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 1)
      _ = await guided.end().value

      let invalid = FeedbackCapturer(samples: [])
      defer { invalid.remove() }
      let invalidOwner = await owner(invalid, writer: HistoryWriter())
      await practice(invalidOwner)
      await invalidOwner.record()
      invalidOwner.stop()
      await wait { invalidOwner.feedbackSession.phase == .failed(.invalidRecording) }
      XCTAssertEqual(invalidOwner.feedbackSession.phase, .failed(.invalidRecording))
      XCTAssertFalse(invalidOwner.practiceVisit!.hasValidCapture)
      XCTAssertFalse(invalidOwner.canFinishPractice)
      await invalidOwner.finishPractice()
      _ = await invalidOwner.end().value
    }
    func testCheckOutcomeAndPausedServiceNeverInferCompletionAndPermitLocalAcknowledgement() async {
      for reason: String? in [
        nil, "requested_word_not_matched", "recognition_uncertain", "model_unavailable",
        "cleanup_unconfirmed",
      ] {
        let capture = FeedbackCapturer()
        let writer = HistoryWriter()
        let processor = HistoryWordProcessor()
        processor.reason = reason
        processor.delay = true
        defer { capture.remove() }
        let guided = await owner(capture, writer: writer, processor: processor)
        await practice(guided)
        await self.capture(guided)
        guided.check()
        await wait { processor.pending != nil }
        XCTAssertFalse(guided.canFinishPractice)
        await guided.finishPractice()
        XCTAssertEqual(writer.calls.count, 0)
        processor.release()
        await wait { !guided.feedbackSession.isProcessing }
        XCTAssertEqual(writer.calls.count, 0)
        XCTAssertTrue(guided.canFinishPractice)
        if reason == "cleanup_unconfirmed" {
          XCTAssertTrue(guided.feedbackSession.sharedProcessingPaused)
          XCTAssertTrue(guided.feedbackSession.canReplay)
        }
        await guided.finishPractice()
        XCTAssertEqual(guided.practiceVisit?.completionState, .saved)
        XCTAssertEqual(writer.calls.count, 1)
        _ = await guided.end().value
      }
    }
    func testPrivateAndPublicCleanupMustSucceedBeforeAcknowledgementOrWrite() async {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await practice(guided)
      await self.capture(guided)
      capture.failDiscard = true
      await guided.finishPractice()
      XCTAssertEqual(writer.calls.count, 0)
      XCTAssertNil(guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(guided.practiceVisit?.completionState, .active)
      XCTAssertEqual(guided.feedbackSession.phase, .cleanupBlocked)
      XCTAssertFalse(guided.canFinishPractice)
      capture.failDiscard = false
      _ = await guided.feedbackSession.end().value

      let otherCapture = FeedbackCapturer()
      let otherWriter = HistoryWriter()
      let loader = HistoryExampleLoader()
      let store = HistoryExampleStore()
      defer {
        otherCapture.remove()
        store.forceRemove()
      }
      let other = await owner(otherCapture, writer: otherWriter, loader: loader, store: store)
      await practice(other)
      await self.capture(other)
      other.feedbackSession.toggleExample()
      await wait { other.feedbackSession.exampleState == .playing }
      store.failRemove = true
      let held = store.ownedURL
      await other.finishPractice()
      XCTAssertTrue(other.feedbackSession.exampleCleanupBlocked)
      XCTAssertEqual(store.ownedURL, held)
      XCTAssertEqual(otherWriter.calls.count, 0)
      XCTAssertNil(other.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(other.practiceVisit?.completionState, .active)
      await other.finishPractice()
      XCTAssertEqual(otherWriter.calls.count, 0)
      store.failRemove = false
      _ = await other.feedbackSession.retryExampleCleanup().value
      otherWriter.onRecord = { XCTAssertNil(store.ownedURL) }
      await other.finishPractice()
      XCTAssertEqual(otherWriter.calls.count, 1)
      XCTAssertEqual(other.practiceVisit?.completionState, .saved)
      _ = await other.end().value
    }
    func testLeavingFailedSaveOrInvalidatingVisitRevokesRetryWithoutSaving() async {
      for action in 0..<6 {
        let capture = FeedbackCapturer()
        let writer = HistoryWriter()
        writer.failuresRemaining = 1
        defer { capture.remove() }
        let guided = await owner(capture, writer: writer)
        await practice(guided)
        await self.capture(guided)
        await guided.finishPractice()
        XCTAssertTrue(guided.canRetryPracticeSave)
        let oldID = guided.practiceVisit?.id
        switch action {
        case 0: await guided.returnSummary()
        case 1: await guided.startRecheck()
        case 2: await guided.practice(item: breadId)
        case 3: _ = await guided.end().value
        case 4: guided.feedbackSession.appDidEnterBackground()
        default: guided.feedbackSession.practiceContext = .adult
        }
        XCTAssertFalse(guided.canRetryPracticeSave)
        XCTAssertNotEqual(guided.practiceVisit?.id, oldID)
        await guided.retryPracticeSave()
        await guided.finishPractice()
        XCTAssertEqual(writer.calls.count, 1)
        XCTAssertFalse(guided.feedbackSession.canCheckSound)
        _ = await guided.end().value
      }
    }
    func testOldCaptureAndExampleCallbacksCannotQualifyNewVisitOrRestoreCompletedMedia() async {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      let loader = HistoryExampleLoader()
      let store = HistoryExampleStore()
      loader.delayed = true
      defer {
        capture.remove()
        store.forceRemove()
      }
      let guided = await owner(capture, writer: writer, loader: loader, store: store)
      await practice(guided)
      await self.capture(guided)
      let oldCapture = capture.finish
      guided.feedbackSession.toggleExample()
      await wait { loader.pending != nil }
      await guided.finishPractice()
      XCTAssertEqual(guided.practiceVisit?.completionState, .saved)
      await guided.practice(item: breadId)
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      await guided.record()
      await oldCapture?(true)
      XCTAssertFalse(guided.practiceVisit!.hasValidCapture)
      XCTAssertEqual(guided.feedbackSession.phase, .recording)
      loader.release()
      await wait { loader.returned }
      for _ in 0..<30 { await Task.yield() }
      XCTAssertEqual(store.writes, 0)
      XCTAssertNil(store.ownedURL)
      guided.stop()
      XCTAssertTrue(guided.canFinishPractice)
      XCTAssertEqual(writer.calls.count, 1)
      await guided.returnSummary()
      _ = await guided.end().value
    }
    func testSynchronousSaveCannotReenterDifferentVisitOrDuplicateFinish() async {
      let capture = FeedbackCapturer()
      let writer = HistoryWriter()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await practice(guided)
      await self.capture(guided)
      let id = guided.practiceVisit?.id
      var reentrantAttempt: Task<Void, Never>?
      writer.onRecord = {
        XCTAssertFalse(guided.canTransition)
        let attempt = Task {
          await guided.finishPractice()
          await guided.retryPracticeSave()
          await guided.practice(item: "r-beginning-rabbit")
          await guided.returnSummary()
          await guided.startRecheck()
        }
        attempt.cancel()
        reentrantAttempt = attempt
        XCTAssertEqual(guided.practiceVisit?.id, id)
        XCTAssertEqual(guided.currentItem?.id, self.breadId)
        XCTAssertFalse(guided.canRecord)
      }
      await guided.finishPractice()
      await reentrantAttempt?.value
      XCTAssertEqual(writer.calls.count, 1)
      XCTAssertEqual(guided.practiceVisit?.completionState, .saved)
      await guided.feedbackSession.startRecording()
      XCTAssertEqual(capture.permissions, 1)
      _ = await guided.end().value
    }
    func testRealUnchangedStoreRoundTripExactKeysAndPersistThenThrowRetryDeduplicates() async throws
    {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      defer { try? FileManager.default.removeItem(at: directory) }
      let file = directory.appendingPathComponent("participation.json")
      let store = PracticeParticipationStore(fileURL: file)
      let writer = PersistThenThrowWriter(store: store)
      let capture = FeedbackCapturer()
      defer { capture.remove() }
      let guided = await owner(capture, writer: writer)
      await practice(guided, itemId: "zh-middle-treasure")
      let first = guided.firstSummary
      await self.capture(guided)
      await guided.finishPractice()
      let snapshot = try XCTUnwrap(guided.practiceVisit?.acknowledgedCompletion)
      XCTAssertEqual(guided.practiceVisit?.completionState, .completedNotSaved(.writeFailed))
      XCTAssertEqual(store.entries.count, 1)
      await guided.retryPracticeSave()
      XCTAssertEqual(guided.practiceVisit?.completionState, .saved)
      XCTAssertEqual(store.entries.count, 1)
      XCTAssertEqual(store.entries[0].id, snapshot.id)
      XCTAssertEqual(store.entries[0].completedAt, snapshot.completedAt)
      XCTAssertEqual(store.entries[0].soundID, "zh")
      XCTAssertEqual(store.entries[0].wordCount, 1)
      let reopened = PracticeParticipationStore(fileURL: file)
      XCTAssertNil(reopened.loadError)
      XCTAssertEqual(reopened.entries, store.entries)
      let document = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
      XCTAssertEqual(Set(document.keys), ["schemaVersion", "entries"])
      XCTAssertEqual(document["schemaVersion"] as? Int, 1)
      let row = try XCTUnwrap((document["entries"] as? [[String: Any]])?.first)
      XCTAssertEqual(Set(row.keys), ["id", "completedAt", "soundID", "wordCount"])
      XCTAssertEqual(guided.firstSummary, first)
      await guided.returnSummary()
      await guided.startRecheck()
      await guided.finishEarly()
      XCTAssertEqual(guided.firstSummary, first)
      XCTAssertEqual(guided.comparison?.rows.count, 13)
      XCTAssertEqual(guided.comparison?.pairedCount, 0)
      _ = await guided.end().value
    }
  }

  @MainActor
  private final class HistoryWriter: ResearchGuidedPracticeParticipationRecording {
    var calls: [ResearchGuidedPracticeCompletion] = []
    var failuresRemaining = 0
    var onRecord: (@MainActor () -> Void)?
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
      calls.append(
        .init(id: sessionID, completedAt: completedAt, soundID: soundID, wordCount: wordCount))
      onRecord?()
      if failuresRemaining > 0 {
        failuresRemaining -= 1
        throw PracticeParticipationStore.StoreError.unreadable
      }
    }
  }
  @MainActor
  private final class PersistThenThrowWriter: ResearchGuidedPracticeParticipationRecording {
    let store: PracticeParticipationStore
    var first = true
    init(store: PracticeParticipationStore) { self.store = store }
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
      try store.record(
        sessionID: sessionID, completedAt: completedAt, soundID: soundID, wordCount: wordCount)
      if first {
        first = false
        throw PracticeParticipationStore.StoreError.unreadable
      }
    }
  }
  /// Generated local response controls; no transport, model or human outcomes.
  @MainActor
  private final class HistoryWordProcessor: ResearchFeedbackProcessing {
    var reason: String?, delay = false
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
      let audio = try FeedbackPCM.read(recording.url)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attemptId, audio: audio,
        prompt: prompt, practiceContext: practiceContext)
      let result = try FeedbackContract.decode(
        FeedbackFixture.json(
          FeedbackFixture.response(
            body, audio: audio, reason: reason, unsupported: prompt.targetUnsupported)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio),
        targetUnsupported: prompt.targetUnsupported)
      onEvent(.requestStarted)  // Explicit simulated request marker, never actual HTTP evidence.
      if delay { await withCheckedContinuation { pending = $0 } }
      return result
    }
    func release() {
      pending?.resume()
      pending = nil
    }
  }
  @MainActor
  private final class HistoryExampleLoader: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    var delayed = false, returned = false
    var pending: CheckedContinuation<Data, Never>?
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated unit fixture", licenseId: "Generated PCM",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated waveform, no human reference",
        changes: "Generated for unit ownership checks",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data {
      let data = delayed ? await withCheckedContinuation { pending = $0 } : bytes
      returned = true
      return data
    }
    func release() {
      pending?.resume(returning: bytes)
      pending = nil
    }
  }
  @MainActor
  private final class HistoryExampleStore: ResearchPracticeExampleStoring {
    var ownedURL: URL?, failRemove = false, writes = 0
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-history-example-" + UUID().uuidString + ".wav")
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
#endif
