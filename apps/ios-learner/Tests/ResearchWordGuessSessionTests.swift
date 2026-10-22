#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Generated PCM and injected hypotheses only; no sensors, service or ASR accuracy claim.
  @MainActor
  final class ResearchWordGuessSessionTests: XCTestCase {
    private var fixtures: [GuessHarness] = []
    override func tearDown() async throws {
      for fixture in fixtures { await fixture.remove() }
      fixtures.removeAll()
      try await super.tearDown()
    }
    private func fixture() throws -> GuessHarness {
      let value = try GuessHarness()
      fixtures.append(value)
      return value
    }
    func testExplicitFreeInjectionPublishesOneResultWithoutCallingLegacyProcessor() async throws {
      let h = try fixture()
      await h.recordAndCheck()
      XCTAssertEqual(h.guess.calls, 1)
      XCTAssertEqual(h.legacy.calls, 0)
      XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "bread")
      guard case .feedback(let value) = h.session.phase else { return XCTFail("Expected feedback") }
      XCTAssertEqual(value.word, .modelMatched)
      XCTAssertEqual(h.guess.recordings.map(\.url), [h.capture.urls[0]])
      XCTAssertFalse(h.session.canCheck)
      h.session.checkRecording()
      XCTAssertEqual(h.guess.calls, 1)
    }

    func testWordAndSoundBothOrdersRetainLatestGuessAndOneMediaOwner() async throws {
      for soundFirst in [false, true] {
        let h = try fixture()
        await h.record()
        if soundFirst { await h.soundCheck() }
        h.session.checkRecording()
        await h.wait { !h.session.isProcessing }
        if !soundFirst { await h.soundCheck() }
        XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "bread")
        XCTAssertEqual(h.guess.recordings.map(\.url), h.sound.recordings.map(\.url))
        XCTAssertEqual(h.capture.urls.count, 1)
        XCTAssertEqual(h.session.attemptsFinished, 1)
        XCTAssertEqual(h.session.checksClaimed, 1)
      }
    }

    func testEarlierReplayDoesNotRelabelLatestGuessAndReplacementClearsBeforePermission()
      async throws
    {
      let h = try fixture()
      await h.recordAndCheck()
      await h.session.recordAnotherTry()
      XCTAssertNil(h.session.recognizerWordGuess)
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      h.guess.token = "red"
      h.guess.reason = "requested_word_not_matched"
      h.session.checkRecording()
      await h.wait { !h.session.isProcessing }
      XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "red")
      XCTAssertNotNil(h.session.earlierReplay)
      await h.session.togglePlayback(.earlier)
      XCTAssertEqual(h.session.playingReplaySource, .earlier)
      XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "red")
      await h.session.togglePlayback(.latest)
      XCTAssertEqual(h.session.playingReplaySource, .earlier)
      await h.session.togglePlayback(.earlier)
      await h.session.togglePlayback(.latest)
      XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "red")
      h.capture.permissionGranted = false
      await h.session.recordAnotherTry()
      XCTAssertNil(h.session.recognizerWordGuess)
      XCTAssertEqual(h.session.phase, .permissionDenied)
      XCTAssertNotNil(h.session.latestReplay)
      XCTAssertFalse(h.session.latestReplay?.isCurrentTake ?? true)
    }

    func testExamplePlaybackKeepsLatestModelGuessAndUsesSeparatePublicFile() async throws {
      let h = try fixture()
      await h.recordAndCheck()
      let take = h.session.latestReplay?.id
      h.session.toggleExample()
      await h.wait { h.session.exampleState == .playing }
      XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "bread")
      XCTAssertEqual(h.session.latestReplay?.id, take)
      let exampleURL = try XCTUnwrap(h.examples.ownedURL)
      XCTAssertFalse(h.capture.urls.contains(exampleURL))
      h.session.toggleExample()
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.togglePlayback(.latest)
      XCTAssertNil(h.examples.ownedURL)
      XCTAssertEqual(h.session.recognizerWordGuess?.normalizedWord, "bread")
    }

    func testEveryRevocationClearsGuessIncludingStickyCleanupFailure() async throws {
      for action in 0..<9 {
        let h = try fixture()
        await h.recordAndCheck()
        XCTAssertNotNil(h.session.recognizerWordGuess)
        switch action {
        case 0: _ = await h.session.retake()?.value
        case 1: await h.session.advance()
        case 2: _ = await h.session.end().value
        case 3: h.session.appDidEnterBackground()
        case 4: h.session.audioWasInterrupted()
        case 5: h.session.practiceContext = .child(ageYears: 9)
        case 6: h.session.localProcessingEnabled = false
        case 7: h.session.practiceMode = "guided"
        default:
          h.capture.failDiscard = true
          _ = await h.session.retake()?.value
        }
        XCTAssertNil(h.session.recognizerWordGuess, "action \(action)")
        if action == 8 { XCTAssertTrue(h.session.hasLocalMediaCleanupIssue) }
      }
    }

    func testLateResultCannotResurrectGuessAfterCancelContextOrClose() async throws {
      for action in 0..<4 {
        let h = try fixture()
        h.guess.delayed = true
        await h.record()
        h.session.checkRecording()
        await h.wait { h.guess.pending != nil }
        switch action {
        case 0: _ = await h.session.cancelChecking()?.value
        case 1: h.session.practiceContext = .child(ageYears: 9)
        case 2: _ = await h.session.end().value
        default: h.session.appDidEnterBackground()
        }
        _ = await h.session.awaitPendingAudioCleanup()
        h.guess.release()
        await h.wait { h.guess.returned }
        for _ in 0..<30 { await Task.yield() }
        XCTAssertNil(h.session.recognizerWordGuess)
        XCTAssertNil(h.session.latestReplay)
        XCTAssertFalse(h.session.isProcessing)
        if case .feedback = h.session.phase { XCTFail("Stale feedback published") }
      }
    }

    func testPermanentGuidedOwnerUsesLegacyEvenWithInjectedGuessProcessor() async throws {
      let h = try fixture()
      let setupReleased = await h.session.awaitPendingAudioCleanup()
      XCTAssertTrue(setupReleased)
      let owner = UUID()
      XCTAssertTrue(
        h.session.installGuidedObserver(
          owner: owner, observer: { _ in }, allowsAction: { _ in true }))
      // Programmatic free/adult settings do not defeat permanent ownership.
      h.session.practiceMode = "free"
      _ = await h.session.awaitPendingAudioCleanup()
      await h.record()
      h.session.checkRecording()
      await h.wait { h.legacy.pending }
      XCTAssertEqual(h.guess.calls, 0)
      h.legacy.resolve(try h.guess.report(h.capture.urls[0]))
      await h.wait { !h.session.isProcessing }
      XCTAssertNil(h.session.recognizerWordGuess)
      h.session.removeGuidedObserver(owner: owner)
      _ = await h.session.retake()?.value
      await h.session.startRecording()
      XCTAssertEqual(h.guess.calls, 0)
      XCTAssertNil(h.session.recognizerWordGuess)
      XCTAssertEqual(h.capture.urls.count, 1)
    }

    func testInstallingGuidedOwnershipClearsAnExistingFreeGuess() async throws {
      let h = try fixture()
      await h.recordAndCheck()
      XCTAssertNotNil(h.session.recognizerWordGuess)
      XCTAssertTrue(
        h.session.installGuidedObserver(
          owner: UUID(), observer: { _ in }, allowsAction: { _ in true }))
      XCTAssertNil(h.session.recognizerWordGuess)
    }

    func testUncertainFailureAndDeclarationRejectionHaveNoGuess() async throws {
      for action in 0..<3 {
        let h = try fixture()
        if action == 0 {
          h.guess.reason = "recognition_uncertain"
          h.guess.token = nil
        } else {
          h.guess.failure = .invalidResponse
          h.guess.rejectDeclaration = action == 2
        }
        await h.recordAndCheck()
        XCTAssertNil(h.session.recognizerWordGuess)
        if action == 0 {
          guard case .feedback(let value) = h.session.phase else {
            return XCTFail("Expected uncertain feedback")
          }
          XCTAssertEqual(value.word, .uncertain)
        } else {
          XCTAssertEqual(h.session.phase, .failed(.invalidResponse))
          if action == 2 { XCTAssertFalse(h.session.canFinishPractice) }
        }
      }
    }

    func testFinishClearsTransientGuessAndWritesOnlyParticipationMetadata() async throws {
      let h = try fixture()
      await h.recordAndCheck()
      XCTAssertTrue(h.session.canFinishPractice)
      await h.session.finishPractice()
      XCTAssertNil(h.session.recognizerWordGuess)
      XCTAssertNil(h.session.latestReplay)
      XCTAssertEqual(h.writer.rows.count, 1)
      XCTAssertEqual(h.writer.rows.first?.soundID, "r")
      XCTAssertEqual(h.writer.rows.first?.wordCount, 1)
      XCTAssertEqual(h.session.practiceCompletionState, .saved)
    }
  }

  @MainActor
  private final class GuessHarness {
    let capture = GuessCapture()
    let guess = GuessProcessor()
    let legacy = FeedbackProcessor()
    let sound = GuessSound()
    let writer = GuessWriter()
    let examples = GuessExampleStore()
    let session: ResearchFeedbackSession
    init() throws {
      session = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(), processor: legacy, soundProcessor: sound,
        exampleLoader: GuessExamples(), exampleStore: examples, participationWriter: writer,
        wordGuessProcessor: guess)
      session.selectedPrompt = ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      session.soundAdultConfirmed = true
      session.soundProcessingEnabled = true
    }
    func record() async {
      _ = await session.awaitPendingAudioCleanup()
      await session.startRecording()
      session.stopRecording()
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertEqual(session.phase, .review)
    }
    func recordAndCheck() async {
      await record()
      session.checkRecording()
      await wait { !session.isProcessing }
    }
    func soundCheck() async {
      session.checkSound()
      await wait { !session.isProcessing }
      guard case .observation = session.soundPhase else { return XCTFail("Expected sound result") }
    }
    func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Expected controlled transition")
    }
    func remove() async {
      capture.failDiscard = false
      _ = await session.end().value
      if session.hasLocalMediaCleanupIssue { _ = await session.retryAudioCleanup().value }
      if !session.hasLocalMediaCleanupIssue {
        capture.remove()
        examples.removeOwnedFixture()
      }
    }
  }

  @MainActor
  private final class GuessProcessor: ResearchWordGuessProcessing {
    var calls = 0, recordings: [CapturedRecording] = []
    var token: String? = "bread", reason: String?, failure: RecordingFeedbackError?
    var delayed = false, rejectDeclaration = false, returned = false
    var pending: CheckedContinuation<ResearchWordGuessFeedback, Never>?
    private var result: ResearchWordGuessFeedback?
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> ResearchWordGuessFeedback {
      calls += 1
      recordings.append(recording)
      if rejectDeclaration { onEvent(.declarationRejected) }
      if let failure { throw failure }
      onEvent(.requestStarted)
      let value = ResearchWordGuessFeedback(
        feedback: try report(recording.url), wordGuess: token.map { .init(normalizedWord: $0) })
      result = value
      defer { returned = true }
      if delayed { return await withCheckedContinuation { pending = $0 } }
      return value
    }
    func report(_ url: URL) throws -> RecordingFeedback {
      let audio = try FeedbackPCM.read(url)
      let prompt = ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
      let body = try FeedbackFixture.body(audio: audio, prompt: prompt, practiceContext: .adult)
      return try FeedbackContract.decode(
        FeedbackFixture.json(FeedbackFixture.response(body, audio: audio, reason: reason)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: false)
    }
    func release() {
      if let result { pending?.resume(returning: result) }
      pending = nil
    }
  }

  @MainActor
  private final class GuessCapture: AudioCapturing {
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
    var urls: [URL] = [], active: URL?, permissionGranted = true, failDiscard = false
    func requestPermission() async -> Bool { permissionGranted }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-word-guess-unit-\(UUID().uuidString).wav")
      try FeedbackFixture.wav().write(to: url)
      ownership.retain(url)
      urls.append(url)
      active = url
    }
    func stop() throws -> CapturedRecording {
      guard let active else { throw AudioCaptureError.couldNotStart }
      self.active = nil
      return .init(
        url: active, summary: .init(duration: 0.2, averagePower: -12),
        cleanupOwnerID: ownership.owner(active))
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
      if failDiscard {
        ownership.failed(recording.url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      try FileManager.default.removeItem(at: recording.url)
      ownership.removed(recording.url)
    }
    func remove() { for url in urls { try? FileManager.default.removeItem(at: url) } }
  }

  @MainActor
  private final class GuessSound: ResearchSoundProcessing {
    var recordings: [CapturedRecording] = []
    let value = ResearchSoundDeclaration(
      serverNonce: "33333333-3333-4333-8333-333333333333",
      csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    func declaration() async throws -> ResearchSoundDeclaration { value }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      recordings.append(recording)
      return try ResearchSoundContract.prepare(
        audio: ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url)),
        declaration: declaration, context: context)
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      .init(
        status: .observedModelPreference, reason: "model_preferred_candidate", preference: .wPath)
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws {}
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {}
  }

  @MainActor
  private final class GuessExamples: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated control", licenseId: "Generated fixture",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated PCM, no human reference", changes: "Generated test only",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data { bytes }
  }

  @MainActor
  private final class GuessExampleStore: ResearchPracticeExampleStoring {
    var ownedURL: URL?
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-word-guess-public-unit-\(UUID().uuidString).wav")
      ownedURL = url
      try data.write(to: url)
      return url
    }
    func remove(_ url: URL) throws {
      guard ownedURL == url else { throw ResearchPracticeExampleError.cleanupFailed }
      try FileManager.default.removeItem(at: url)
      ownedURL = nil
    }
    func removeOwnedFixture() {
      if let ownedURL { try? FileManager.default.removeItem(at: ownedURL) }
    }
  }

  @MainActor
  private final class GuessWriter: ResearchGuidedPracticeParticipationRecording {
    struct Row {
      let id: UUID
      let date: Date
      let soundID: String
      let wordCount: Int
    }
    var rows: [Row] = []
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
      rows.append(.init(id: sessionID, date: completedAt, soundID: soundID, wordCount: wordCount))
    }
  }
#endif
