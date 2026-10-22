#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// One generated file, injected processors, no sensors, sockets or model execution.
  @MainActor
  final class ResearchUnifiedSessionTests: XCTestCase {
    private var bread: ResearchFeedbackPrompt {
      ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
    }
    private func configured(
      _ capture: FeedbackCapturer, _ word: FeedbackProcessor, _ sound: UnifiedSoundProcessor
    ) -> ResearchFeedbackSession {
      let session = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(), processor: word, soundProcessor: sound)
      session.selectedPrompt = bread
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      session.soundAdultConfirmed = true
      session.soundProcessingEnabled = true
      return session
    }
    private func record(_ session: ResearchFeedbackSession) async {
      _ = await session.awaitPendingAudioCleanup()
      await session.startRecording()
      session.stopRecording()
      XCTAssertEqual(session.phase, .review)
    }
    private func wordResult(reason: String? = nil) throws -> RecordingFeedback {
      let audio = FeedbackFixture.wav()
      let body = try FeedbackFixture.body(audio: audio, prompt: bread, practiceContext: .adult)
      return try FeedbackContract.decode(
        FeedbackFixture.json(FeedbackFixture.response(body, audio: audio, reason: reason)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: false)
    }
    private func checkWord(_ session: ResearchFeedbackSession, _ word: FeedbackProcessor)
      async throws
    {
      session.checkRecording()
      await wait { word.pending }
      word.resolve(try wordResult())
      await wait { !session.isProcessing }
    }
    private func checkSound(_ session: ResearchFeedbackSession, _ sound: UnifiedSoundProcessor)
      async
    {
      session.checkSound()
      await wait { !session.isProcessing }
      guard case .observation = session.soundPhase else { return XCTFail("Expected sound result") }
    }
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Expected controlled transition")
    }
    func testSameOwnedFileSupportsBothCheckOrdersAndRetainsIndependentResults() async throws {
      for soundFirst in [false, true] {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        await record(session)
        if soundFirst {
          await checkSound(session, sound)
          XCTAssertTrue(session.canCheck)
          try await checkWord(session, word)
        } else {
          try await checkWord(session, word)
          XCTAssertTrue(session.canCheckSound)
          await checkSound(session, sound)
        }
        guard case .feedback(let value) = session.phase,
          case .observation(let preference) = session.soundPhase
        else { return XCTFail("Both independent results must remain visible") }
        XCTAssertEqual(value.word, .modelMatched)
        XCTAssertEqual(preference.preference, .wPath)
        XCTAssertEqual(word.recordings.map(\.url), [capture.url])
        XCTAssertEqual(sound.recordings.map(\.url), [capture.url])
        XCTAssertEqual(word.contexts, [.adult])
        XCTAssertEqual(capture.starts, 1)
        XCTAssertEqual(capture.discards, 0)
        XCTAssertEqual(session.attemptsStarted, 1)
        XCTAssertEqual(session.attemptsFinished, 1)
        XCTAssertEqual(session.checksClaimed, 1)
        XCTAssertFalse(session.canCheckSound)
        XCTAssertFalse(session.canCheck)
        XCTAssertTrue(session.canReplay)
        session.checkRecording()
        session.checkSound()
        XCTAssertEqual(word.calls, 1)
        XCTAssertEqual(sound.observations, 1)
        _ = await session.retake()?.value
        await wait { sound.resets.count == 1 }
        XCTAssertEqual(capture.discards, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      }
    }
    func testBothSoundConsentsAndAdultCapturedContextAreRequiredWithoutCouplingWordOptIn() async {
      for scenario in 0..<5 {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        switch scenario {
        case 0: session.practiceContext = nil
        case 1: session.practiceContext = .child(ageYears: 9)
        case 2: session.soundAdultConfirmed = false
        case 3: session.soundProcessingEnabled = false
        default:
          session.localProcessingEnabled = false
          session.soundAdultConfirmed = true
          session.soundProcessingEnabled = true
        }
        await record(session)
        if scenario == 4 {
          XCTAssertFalse(session.canCheck)
          XCTAssertTrue(session.canCheckSound)
          await checkSound(session, sound)
        } else {
          XCTAssertFalse(session.canCheckSound)
          session.checkSound()
          XCTAssertEqual(sound.declarations, 0)
        }
        _ = await session.end().value
      }
    }
    func testCanonicalBreadFullPromptAndFreeModeAreRequired() async {
      for scenario in 0..<3 {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        if scenario == 0 { session.selectedPrompt = ResearchFeedbackCatalog.prompts[2] }
        if scenario == 1 { session.practiceMode = "guided" }
        if scenario == 2 {
          session.selectedPrompt = .init(
            id: bread.id, word: "bread", phones: ["B", "W", "EH", "D"], occurrenceIndex: 1,
            targetPhone: "R")
        }
        session.soundAdultConfirmed = true
        session.soundProcessingEnabled = true
        _ = await session.awaitPendingAudioCleanup()
        await session.startRecording()
        if scenario == 2 {
          XCTAssertEqual(capture.starts, 0)
        } else {
          session.stopRecording()
          XCTAssertTrue(session.canCheck)
        }
        XCTAssertFalse(session.canCheckSound)
        session.checkSound()
        XCTAssertEqual(sound.declarations, 0)
        _ = await session.end().value
      }
    }
    func testWordAndSoundRequestsCannotRunConcurrentlyInEitherDirection() async throws {
      for soundFirst in [false, true] {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        await record(session)
        if soundFirst {
          sound.delayAt = .observation
          session.checkSound()
          await wait { sound.observationPending != nil }
          XCTAssertEqual(session.phase, .review)
          session.checkRecording()
          XCTAssertEqual(word.calls, 0)
          sound.releaseObservation()
          await wait { !session.isProcessing }
        } else {
          session.checkRecording()
          await wait { word.pending }
          session.checkSound()
          XCTAssertEqual(sound.declarations, 0)
          word.resolve(try wordResult())
          await wait { !session.isProcessing }
        }
        XCTAssertTrue(session.canReplay)
        _ = await session.end().value
      }
    }
    func testSoundBusyDisablesReplaySetupAndCaptureWithoutErasingWordResult() async throws {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      try await checkWord(session, word)
      let previous = session.phase
      sound.delayAt = .observation
      session.checkSound()
      await wait { sound.observationPending != nil }
      XCTAssertEqual(session.phase, previous)
      XCTAssertFalse(session.canReplay)
      XCTAssertFalse(session.setupEditable)
      await session.startRecording()
      XCTAssertEqual(capture.starts, 1)
      sound.releaseObservation()
      await wait { !session.isProcessing }
      XCTAssertEqual(session.phase, previous)
      _ = await session.end().value
    }
    func testLateSoundDeclarationPreparationAndResponseCannotResurrectChangedContext() async {
      for stage in UnifiedSoundProcessor.Stage.allCases where stage != .none {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        await record(session)
        sound.delayAt = stage
        session.checkSound()
        await wait { sound.isPending }
        let old = sound.prepared
        session.practiceContext = .child(ageYears: 9)
        XCTAssertFalse(session.soundAdultConfirmed)
        XCTAssertFalse(session.soundProcessingEnabled)
        sound.release()
        await wait { sound.returned }
        if stage != .observation {
          XCTAssertEqual(sound.observations, 0)
        } else {
          await wait { !sound.cancellations.isEmpty && !sound.resets.isEmpty }
          XCTAssertEqual(sound.cancellations.first, old)
          XCTAssertGreaterThan(sound.resets.first!.generation, old!.context.generation)
        }
        XCTAssertEqual(session.phase, .ready)
        XCTAssertEqual(session.soundPhase, .ready)
        XCTAssertFalse(session.canReplay)
        XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      }
    }
    func testPreparationFailureConsumesSoundClaimAndWordCheckRemainsAvailable() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      sound.prepareFailure = true
      session.checkSound()
      await wait { !session.isProcessing }
      XCTAssertEqual(session.soundPhase, .failed(.invalidRecording))
      XCTAssertEqual(session.checksClaimed, 1)
      XCTAssertFalse(session.canCheckSound)
      XCTAssertTrue(session.canCheck)
      XCTAssertTrue(session.canReplay)
      session.checkSound()
      XCTAssertEqual(sound.preparations, 1)
      XCTAssertEqual(sound.observations, 0)
      _ = await session.end().value
    }
    func testMismatchedPreparedOwnershipFailsWithoutLeavingSessionBusy() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      sound.mismatchPreparation = true
      session.checkSound()
      await wait { !session.isProcessing }
      XCTAssertEqual(session.soundPhase, .failed(.invalidResponse))
      XCTAssertEqual(sound.observations, 0)
      XCTAssertEqual(session.checksClaimed, 1)
      XCTAssertFalse(session.canCheckSound)
      XCTAssertTrue(session.canCheck)
      _ = await session.end().value
    }
    func testExactCancellationUsesPreparedOwnerAndStrictlyNewerResetSuppressingLateReply() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      sound.delayAt = .observation
      session.checkSound()
      await wait { sound.observationPending != nil }
      let owned = sound.prepared!
      _ = await session.cancelSound()?.value
      await wait { !sound.cancellations.isEmpty && !sound.resets.isEmpty }
      XCTAssertEqual(sound.cancellations.first, owned)
      XCTAssertEqual(sound.resets.first?.sessionId, owned.context.sessionId)
      XCTAssertGreaterThan(sound.resets.first!.generation, owned.context.generation)
      sound.releaseObservation()
      await wait { sound.returned }
      XCTAssertEqual(session.soundPhase, .ready)
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(capture.discards, 1)
      XCTAssertFalse(session.canReplay)
    }
    func testWordAndSoundCleanupUncertaintyPauseBothChecksButNotSafeLocalReplay() async throws {
      for soundPauses in [false, true] {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        await record(session)
        if soundPauses {
          sound.result = .init(status: .unavailable, reason: "cleanup_unconfirmed", preference: nil)
          session.checkSound()
          await wait { !session.isProcessing }
        } else {
          session.checkRecording()
          await wait { word.pending }
          word.resolve(try wordResult(reason: "cleanup_unconfirmed"))
          await wait { !session.isProcessing }
        }
        XCTAssertTrue(session.sharedProcessingPaused)
        XCTAssertFalse(session.canCheck)
        XCTAssertFalse(session.canCheckSound)
        XCTAssertTrue(session.canReplay)
        session.reset()
        _ = await session.awaitPendingAudioCleanup()
        XCTAssertTrue(session.sharedProcessingPaused)
        await record(session)
        XCTAssertTrue(session.canReplay)
        XCTAssertFalse(session.canCheck)
        session.soundAdultConfirmed = true
        session.soundProcessingEnabled = true
        XCTAssertTrue(session.sharedProcessingPaused)
        _ = await session.end().value
      }
    }
    func testUnavailableDeclarationOrWordErrorPausesBothChecks() async {
      for soundPauses in [false, true] {
        let capture = FeedbackCapturer()
        let word = FeedbackProcessor()
        let sound = UnifiedSoundProcessor()
        defer { capture.remove() }
        let session = configured(capture, word, sound)
        await record(session)
        if soundPauses {
          sound.declarationValue = .init(
            serverNonce: sound.declarationValue.serverNonce,
            csrfToken: sound.declarationValue.csrfToken, processingAvailable: false)
          session.checkSound()
        } else {
          word.failure = .processingUnavailable
          session.checkRecording()
        }
        await wait { !session.isProcessing }
        XCTAssertTrue(session.sharedProcessingPaused)
        XCTAssertTrue(session.canReplay)
        XCTAssertFalse(session.canCheck)
        XCTAssertFalse(session.canCheckSound)
        XCTAssertEqual(sound.observations, 0)
        _ = await session.end().value
      }
    }
    func testRemoteControlFailureRemainsPausedAndDoesNotClaimLocalDeletionFailed() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      await checkSound(session, sound)
      sound.controlFailure = true
      _ = await session.retake()?.value
      await wait { session.sharedProcessingPaused }
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(capture.discards, 1)
      await record(session)
      XCTAssertTrue(session.canReplay)
      XCTAssertFalse(session.canCheck)
      _ = await session.end().value
    }
    func testPermissionPendingSerializesReplacementUntilOldRequestReturns() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      capture.delayPermission = true
      let old = Task { await session.startRecording() }
      await wait { capture.permission != nil }
      _ = await session.retake()?.value
      await session.startRecording()
      XCTAssertEqual(capture.permissions, 1)
      XCTAssertEqual(capture.starts, 0)
      XCTAssertFalse(session.canRecord)
      capture.permission?.resume(returning: true)
      capture.permission = nil
      await old.value
      XCTAssertEqual(capture.starts, 0)
      XCTAssertTrue(session.canRecord)
      capture.delayPermission = false
      await record(session)
      XCTAssertEqual(capture.starts, 1)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      _ = await session.end().value
      XCTAssertEqual(session.attemptsStarted, 2)
      XCTAssertEqual(session.attemptsFinished, 2)
    }
    func testCSRFRotationPreservesTakeButNonceRotationRevokesItBeforeObservation() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      await checkSound(session, sound)
      _ = await session.retake()?.value
      await wait { sound.resets.count == 1 }
      await record(session)
      sound.declarationValue = .init(
        serverNonce: sound.declarationValue.serverNonce,
        csrfToken: String(repeating: "a", count: 64), processingAvailable: true)
      await checkSound(session, sound)
      XCTAssertTrue(session.canReplay)
      XCTAssertEqual(sound.observations, 2)
      _ = await session.retake()?.value
      await wait { sound.resets.count == 2 }
      await record(session)
      sound.declarationValue = .init(
        serverNonce: "44444444-4444-4444-8444-444444444444",
        csrfToken: String(repeating: "a", count: 64), processingAvailable: true)
      session.checkSound()
      await wait { !session.isProcessing }
      XCTAssertEqual(sound.observations, 2)
      XCTAssertFalse(session.canReplay)
      XCTAssertEqual(session.phase, .ready)
      _ = await session.end().value
    }
    func testLocalDeletionFailureDisablesMediaAndChecksWithoutConflatingRemotePause() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      capture.failDiscard = true
      _ = await session.retake()?.value
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertEqual(session.soundPhase, .localCleanupBlocked)
      XCTAssertFalse(session.sharedProcessingPaused)
      XCTAssertFalse(session.canReplay)
      XCTAssertFalse(session.canCheck)
      XCTAssertFalse(session.canCheckSound)
      XCTAssertFalse(session.canRecord)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
    }
    func testPendingRemoteResetBlocksBothUploadsWhileNewLocalTakeRemainsReplayable() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      await record(session)
      await checkSound(session, sound)
      sound.delayControl = true
      _ = await session.retake()?.value
      await wait { sound.controlPending != nil }
      await record(session)
      XCTAssertTrue(session.canReplay)
      XCTAssertFalse(session.canCheck)
      XCTAssertFalse(session.canCheckSound)
      session.checkRecording()
      session.checkSound()
      XCTAssertEqual(word.calls, 0)
      XCTAssertEqual(sound.observations, 1)
      sound.controlPending?.resume()
      sound.controlPending = nil
      await wait { session.canCheck && session.canCheckSound }
      _ = await session.end().value
    }
    func testBoundedCaptureAndSoundClaimsCannotBeReopenedByRetake() async {
      let capture = FeedbackCapturer()
      let word = FeedbackProcessor()
      let sound = UnifiedSoundProcessor()
      defer { capture.remove() }
      let session = configured(capture, word, sound)
      for index in 0..<128 {
        await record(session)
        await wait { session.canCheckSound }
        await checkSound(session, sound)
        XCTAssertEqual(session.checksClaimed, index + 1)
        _ = await session.retake()?.value
      }
      XCTAssertEqual(session.attemptsStarted, 128)
      XCTAssertEqual(session.attemptsFinished, 128)
      XCTAssertEqual(sound.observations, 128)
      XCTAssertFalse(session.canRecord)
      XCTAssertFalse(session.canCheckSound)
      await session.startRecording()
      XCTAssertEqual(capture.starts, 128)
      session.reset()
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertEqual(session.checksClaimed, 128)
      XCTAssertFalse(session.canRecord)
      _ = await session.end().value
    }
    func testGeneratedUIFixtureHasNoAutomaticCaptureOrConsentAndUsesOneTakeForResults() async {
      XCTAssertNil(ResearchUnifiedFeedbackUITestFixtures.selected([]))
      XCTAssertNil(
        ResearchUnifiedFeedbackUITestFixtures.selected([
          "-CadenceUnifiedFeedbackUITestCase", "unknown",
        ]))
      XCTAssertEqual(
        ResearchUnifiedFeedbackUITestFixtures.selected([
          "-CadenceUnifiedFeedbackUITestCase", "combined",
        ]), .combined)
      let session = ResearchUnifiedFeedbackUITestFixtures.session(for: .combined)
      XCTAssertEqual(session.phase, .ready)
      XCTAssertNil(session.summary)
      XCTAssertNil(session.practiceContext)
      XCTAssertFalse(session.localProcessingEnabled)
      XCTAssertFalse(session.soundAdultConfirmed)
      XCTAssertFalse(session.soundProcessingEnabled)
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      session.soundAdultConfirmed = true
      session.soundProcessingEnabled = true
      await record(session)
      session.checkRecording()
      await wait { !session.isProcessing }
      session.checkSound()
      await wait { !session.isProcessing }
      guard case .feedback(let word) = session.phase,
        case .observation(let sound) = session.soundPhase
      else {
        return XCTFail("Expected generated independent results")
      }
      XCTAssertEqual(word.word, .modelMatched)
      XCTAssertEqual(sound.preference, .wPath)
      XCTAssertEqual(session.attemptsStarted, 1)
      _ = await session.end().value
    }
  }

  @MainActor
  private final class UnifiedSoundProcessor: ResearchSoundProcessing {
    enum Stage: CaseIterable, Equatable { case none, declaration, preparation, observation }
    struct Reset {
      let sessionId: String
      let generation: Int
    }
    var delayAt = Stage.none
    var declarations = 0
    var preparations = 0
    var observations = 0
    var recordings: [CapturedRecording] = []
    var prepared: ResearchSoundPrepared?
    var cancellations: [ResearchSoundPrepared] = []
    var resets: [Reset] = []
    var returned = false
    var prepareFailure = false
    var mismatchPreparation = false
    var controlFailure = false
    var delayControl = false
    var controlPending: CheckedContinuation<Void, Never>?
    var declarationValue = ResearchSoundDeclaration(
      serverNonce: "33333333-3333-4333-8333-333333333333",
      csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    var result = ResearchSoundObservation(
      status: .observedModelPreference, reason: "model_preferred_candidate", preference: .wPath)
    var declarationPending: CheckedContinuation<ResearchSoundDeclaration, Never>?
    var preparePending: CheckedContinuation<ResearchSoundPrepared, Never>?
    var observationPending: CheckedContinuation<ResearchSoundObservation, Never>?
    var isPending: Bool {
      declarationPending != nil || preparePending != nil || observationPending != nil
    }
    func declaration() async throws -> ResearchSoundDeclaration {
      declarations += 1
      if delayAt == .declaration {
        let value = await withCheckedContinuation { declarationPending = $0 }
        returned = true
        return value
      }
      return declarationValue
    }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      preparations += 1
      recordings.append(recording)
      if prepareFailure { throw RecordingFeedbackError.invalidRecording }
      let value = try ResearchSoundContract.prepare(
        audio: ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url)),
        declaration: declaration, context: context)
      prepared = value
      if delayAt == .preparation {
        let pending = await withCheckedContinuation { preparePending = $0 }
        returned = true
        return pending
      }
      if mismatchPreparation {
        let altered = ResearchSoundCheckContext(
          sessionId: context.sessionId, generation: context.generation,
          setupGeneration: context.setupGeneration, roundId: context.roundId,
          takeId: context.takeId, captureId: "mismatched", attemptId: context.attemptId)
        return .init(
          body: value.body, privateRequest: value.privateRequest, expected: value.expected,
          declaration: declaration, ownership: value.ownership, context: altered)
      }
      return value
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      observations += 1
      if delayAt == .observation {
        let value = await withCheckedContinuation { observationPending = $0 }
        returned = true
        return value
      }
      return result
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws {
      cancellations.append(prepared)
      if controlFailure { throw RecordingFeedbackError.serviceUnavailable }
    }
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {
      resets.append(.init(sessionId: sessionId, generation: generation))
      if delayControl { await withCheckedContinuation { controlPending = $0 } }
      if controlFailure { throw RecordingFeedbackError.serviceUnavailable }
    }
    func releaseObservation() {
      observationPending?.resume(returning: result)
      observationPending = nil
    }
    func release() {
      declarationPending?.resume(returning: declarationValue)
      declarationPending = nil
      if let prepared { preparePending?.resume(returning: prepared) }
      preparePending = nil
      releaseObservation()
    }
  }
#endif
