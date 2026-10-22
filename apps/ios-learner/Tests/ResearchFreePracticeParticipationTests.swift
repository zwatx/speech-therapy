#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Task-owned real files and generated PCM/invented observations; no sensors or network.
  @MainActor
  final class ResearchFreePracticeParticipationTests: XCTestCase {
    private var fixtures: [FreePracticeHarness] = []
    override func tearDown() async throws {
      for fixture in fixtures { await fixture.remove() }
      fixtures.removeAll()
      try await super.tearDown()
    }
    private func fixture(writerEnabled: Bool = true) throws -> FreePracticeHarness {
      let value = try FreePracticeHarness(writerEnabled: writerEnabled)
      fixtures.append(value)
      return value
    }
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Expected controlled transition")
    }
    private func capture(_ h: FreePracticeHarness, another: Bool = false) async {
      if another {
        await h.session.recordAnotherTry()
      } else {
        _ = await h.session.awaitPendingAudioCleanup()
        await h.session.startRecording()
      }
      h.session.stopRecording()
      _ = await h.session.awaitPendingAudioCleanup()
      XCTAssertEqual(h.session.phase, .review)
    }
    private func example(_ h: FreePracticeHarness) async {
      h.session.toggleExample()
      await wait { h.session.exampleState == .playing && h.player.urls.last == h.examples.ownedURL }
    }
    private func word(_ h: FreePracticeHarness) async {
      h.session.checkRecording()
      await wait { !h.session.isProcessing }
    }
    private func usedSound(_ h: FreePracticeHarness) async {
      // An invented transport failure retains the exact prepared request for cancellation.
      h.sound.observeFailure = true
      h.session.checkSound()
      await wait { !h.session.isProcessing }
      XCTAssertEqual(h.sound.prepared.count, 1)
    }

    func testAllFifteenFullMappingsIncludingRepeatedOccurrencesAndMutationRefusal() {
      let groups = [
        "r", "r", "r", "b", "b", "n", "k", "k", "s", "v", "y", "th",
        "voiced-th", "ng", "zh",
      ]
      XCTAssertEqual(ResearchFeedbackCatalog.prompts.count, 15)
      for (prompt, group) in zip(ResearchFeedbackCatalog.prompts, groups) {
        XCTAssertEqual(ResearchFreePracticeParticipationMapping.soundID(for: prompt), group)
        let mutations: [ResearchFeedbackPrompt] = [
          .init(
            id: "unknown", word: prompt.word, phones: prompt.phones,
            occurrenceIndex: prompt.occurrenceIndex, targetPhone: prompt.targetPhone),
          .init(
            id: prompt.id, word: "spoof", phones: prompt.phones,
            occurrenceIndex: prompt.occurrenceIndex, targetPhone: prompt.targetPhone),
          .init(
            id: prompt.id, word: prompt.word, phones: ["R"],
            occurrenceIndex: prompt.occurrenceIndex, targetPhone: prompt.targetPhone),
          .init(
            id: prompt.id, word: prompt.word, phones: prompt.phones,
            occurrenceIndex: -1, targetPhone: prompt.targetPhone),
          .init(
            id: prompt.id, word: prompt.word, phones: prompt.phones,
            occurrenceIndex: prompt.occurrenceIndex, targetPhone: "W"),
        ]
        for mutation in mutations {
          XCTAssertNil(ResearchFreePracticeParticipationMapping.soundID(for: mutation))
        }
      }
      let baby = PracticeLibrary.entries(soundID: "b", position: .middle)
      XCTAssertTrue(baby.contains { $0.id == "b-middle-baby" && $0.targetPhone == "B" })
      let backpack = PracticeLibrary.entries(soundID: "k", position: .end)
      XCTAssertTrue(backpack.contains { $0.id == "k-end-backpack" && $0.targetPhone == "K" })
    }

    func testOpeningListeningDenialAndInvalidOnlyNeverComplete() async throws {
      for failure in [0, 1, 2] {
        let h = try fixture()
        let setupReleased = await h.session.awaitPendingAudioCleanup()
        XCTAssertTrue(setupReleased)
        await example(h)
        XCTAssertFalse(h.session.canFinishPractice)
        await h.session.finishPractice()
        if failure == 1 { h.capture.permissionGranted = false }
        if failure == 2 { h.capture.failure = .invalidPCM }
        if failure != 0 {
          _ = await h.session.awaitPendingAudioCleanup()
          await h.session.startRecording()
          if h.session.phase == .recording { h.session.stopRecording() }
        }
        XCTAssertFalse(h.session.canFinishPractice)
        await h.session.finishPractice()
        XCTAssertNil(h.session.practiceCompletion)
        XCTAssertTrue(h.writer.calls.isEmpty)
        XCTAssertEqual(h.clock.samples, 0)
      }
    }

    func testTwoClipsAndPublicExampleRemovedBeforeRealMetadataOnlyStoreWriteAndReopen()
      async throws
    {
      let h = try fixture()
      await capture(h)
      await capture(h, another: true)
      await example(h)
      XCTAssertEqual(h.capture.files.count, 2)
      let publicURL = try XCTUnwrap(h.examples.ownedURL)
      h.writer.beforeWrite = {
        XCTAssertTrue(h.capture.files.isEmpty)
        XCTAssertNil(h.examples.ownedURL)
        XCTAssertFalse(FileManager.default.fileExists(atPath: publicURL.path))
        XCTAssertNil(h.session.summary)
        XCTAssertNil(h.session.latestReplay)
      }
      await h.session.finishPractice()
      let completion = try XCTUnwrap(h.session.practiceCompletion)
      XCTAssertEqual(h.session.practiceCompletionState, .saved)
      XCTAssertEqual(completion.wordCount, 1)
      XCTAssertEqual(completion.soundID, "r")
      XCTAssertEqual(h.clock.samples, 1)
      await h.session.finishPractice()
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertEqual(h.history.entries.count, 1)
      let reopened = PracticeParticipationStore(fileURL: h.historyURL)
      XCTAssertNil(reopened.loadError)
      XCTAssertEqual(reopened.entries, h.history.entries)
      let json = try XCTUnwrap(
        try JSONSerialization.jsonObject(
          with: Data(contentsOf: h.historyURL)) as? [String: Any])
      XCTAssertEqual(Set(json.keys), ["schemaVersion", "entries"])
      let rows = try XCTUnwrap(json["entries"] as? [[String: Any]])
      XCTAssertEqual(
        Set(try XCTUnwrap(rows.first).keys),
        ["id", "completedAt", "soundID", "wordCount"])
    }

    func testRetainedPriorAfterDeniedOrInvalidReplacementCanFinishWithoutCheckEligibility()
      async throws
    {
      for denied in [true, false] {
        let h = try fixture()
        await capture(h)
        let prior = h.session.latestReplay
        if denied { h.capture.permissionGranted = false } else { h.capture.failure = .invalidPCM }
        await h.session.recordAnotherTry()
        if h.session.phase == .recording { h.session.stopRecording() }
        XCTAssertEqual(h.session.latestReplay?.id, prior?.id)
        XCTAssertFalse(h.session.latestReplay?.isCurrentTake ?? true)
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        XCTAssertTrue(h.session.canFinishPractice)
        await h.session.finishPractice()
        XCTAssertEqual(h.session.practiceCompletionState, .saved)
        XCTAssertEqual(h.history.entries.first?.wordCount, 1)
      }
    }

    func testInitialPrivateCleanupFailureTriesEveryFileAndNeverAcknowledges() async throws {
      let h = try fixture()
      await capture(h)
      await capture(h, another: true)
      await example(h)
      h.capture.failDiscard.insert(h.capture.urls[0])
      await h.session.finishPractice()
      XCTAssertEqual(h.capture.files, [h.capture.urls[0]])
      XCTAssertTrue(h.capture.discarded.contains(h.capture.urls[1]))
      XCTAssertNil(h.examples.ownedURL)
      XCTAssertTrue(h.session.hasLocalMediaCleanupIssue)
      XCTAssertNil(h.session.practiceCompletion)
      XCTAssertEqual(h.session.practiceCompletionState, .active)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertFalse(h.session.canFinishPractice)
      await h.session.retryPracticeSave()
      XCTAssertTrue(h.writer.calls.isEmpty)
      // The Finish click sampled the clock; no acknowledgement or payload was retained.
      XCTAssertEqual(h.clock.samples, 1)
    }

    func testPublicCleanupRetryCannotAcknowledgeAfterPrivateEvidenceWasRemoved() async throws {
      let h = try fixture()
      await capture(h)
      await example(h)
      h.examples.failRemove = true
      await h.session.finishPractice()
      XCTAssertTrue(h.capture.files.isEmpty)
      XCTAssertNotNil(h.examples.ownedURL)
      XCTAssertNil(h.session.practiceCompletion)
      h.examples.failRemove = false
      _ = await h.session.retryExampleCleanup().value
      XCTAssertFalse(h.session.hasLocalMediaCleanupIssue)
      XCTAssertFalse(h.session.canFinishPractice)
      await h.session.finishPractice()
      await h.session.retryPracticeSave()
      XCTAssertTrue(h.writer.calls.isEmpty)
      await capture(h)
      await h.session.finishPractice()
      XCTAssertEqual(h.session.practiceCompletionState, .saved)
    }

    func testWriteFailureAndPersistThenThrowRetryExactPayloadWithoutClockResampling()
      async throws
    {
      for mode in [FreePracticeWriter.Mode.failBefore, .persistThenThrow] {
        let h = try fixture()
        h.writer.mode = mode
        await capture(h)
        await h.session.finishPractice()
        let completion = try XCTUnwrap(h.session.practiceCompletion)
        XCTAssertEqual(h.session.practiceCompletionState, .completedNotSaved(.writeUnconfirmed))
        XCTAssertEqual(h.history.entries.count, mode == .persistThenThrow ? 1 : 0)
        XCTAssertTrue(h.session.canRetryPracticeSave)
        XCTAssertFalse(h.session.canRecord)
        XCTAssertFalse(h.session.canRecordAnotherTry)
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        await example(h)
        h.writer.beforeWrite = { XCTAssertNil(h.examples.ownedURL) }
        await h.session.retryPracticeSave()
        XCTAssertEqual(h.session.practiceCompletion, completion)
        XCTAssertEqual(h.writer.calls, [completion, completion])
        XCTAssertEqual(h.clock.samples, 1)
        XCTAssertEqual(h.history.entries.count, 1)
        XCTAssertEqual(h.session.practiceCompletionState, .saved)
        await h.session.retryPracticeSave()
        XCTAssertEqual(h.writer.calls.count, 2)
      }
    }

    func testNilWriterAcknowledgesUnavailableAndPracticeAgainRequiresNewCapture() async throws {
      let h = try fixture(writerEnabled: false)
      h.session.practiceContext = nil
      _ = await h.session.awaitPendingAudioCleanup()
      h.session.localProcessingEnabled = false
      _ = await h.session.awaitPendingAudioCleanup()
      await capture(h)
      XCTAssertTrue(h.session.canFinishPractice)
      await h.session.finishPractice()
      let first = try XCTUnwrap(h.session.practiceCompletion)
      XCTAssertEqual(h.session.practiceCompletionState, .completedNotSaved(.storeUnavailable))
      XCTAssertFalse(h.session.canRetryPracticeSave)
      XCTAssertTrue(h.session.canPracticeAgain)
      let started = h.session.attemptsStarted
      await h.session.practiceAgain()
      XCTAssertEqual(h.session.practiceCompletionState, .active)
      XCTAssertNil(h.session.practiceCompletion)
      XCTAssertFalse(h.session.canFinishPractice)
      XCTAssertEqual(h.session.attemptsStarted, started)
      await capture(h)
      await h.session.finishPractice()
      XCTAssertNotEqual(h.session.practiceCompletion?.id, first.id)
      XCTAssertEqual(h.session.attemptsStarted, started + 1)
    }

    func testFinishAwaitsExactControlsAndBlocksReentrantActionsUntilSettlement() async throws {
      let h = try fixture()
      await capture(h)
      await usedSound(h)
      h.sound.delayReset = true
      let task = Task { await h.session.finishPractice() }
      await wait { h.sound.resetPending != nil }
      XCTAssertTrue(h.session.isFinalizingPractice)
      XCTAssertTrue(h.capture.files.isEmpty)
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertEqual(h.sound.cancelled, h.sound.prepared)
      XCTAssertEqual(h.sound.resets.first?.declaration, h.sound.declarationValue)
      XCTAssertFalse(h.session.canRecord)
      XCTAssertFalse(h.session.canRecordAnotherTry)
      XCTAssertFalse(h.session.canCheck)
      XCTAssertFalse(h.session.canFinishPractice)
      XCTAssertFalse(h.session.canPracticeAgain)
      XCTAssertFalse(h.session.canTransitionGuided)
      XCTAssertFalse(h.session.canPlayExample)
      await h.session.finishPractice()
      await h.session.practiceAgain()
      h.sound.releaseReset()
      await task.value
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertEqual(h.session.practiceCompletionState, .saved)
      XCTAssertFalse(h.session.isFinalizingPractice)
    }

    func testDelayedFinishInvalidationAllowsLocalCaptureButNotChecksOrStaleSave() async throws {
      for mutate in [0, 1, 2] {
        let h = try fixture()
        await capture(h)
        await usedSound(h)
        h.sound.delayReset = true
        let old = Task { await h.session.finishPractice() }
        await wait { h.sound.resetPending != nil }
        if mutate == 0 {
          h.session.appDidEnterBackground()
          h.session.appDidBecomeActive()
        } else if mutate == 1 {
          h.session.practiceContext = .child(ageYears: 9)
          _ = await h.session.awaitPendingAudioCleanup()
        } else {
          h.session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
          _ = await h.session.awaitPendingAudioCleanup()
        }
        _ = await h.session.awaitPendingAudioCleanup()
        XCTAssertTrue(h.session.canRecord)
        await capture(h)
        XCTAssertFalse(h.session.canCheck)
        XCTAssertFalse(h.session.canCheckSound)
        XCTAssertFalse(h.session.canFinishPractice)
        h.sound.releaseReset()
        await old.value
        XCTAssertNil(h.session.practiceCompletion)
        XCTAssertTrue(h.writer.calls.isEmpty)
        XCTAssertTrue(h.session.canFinishPractice)
        await h.session.finishPractice()
        XCTAssertEqual(h.session.practiceCompletionState, .saved)
      }
    }

    func testTaskCancellationBeforeAndDuringFinishCannotWriteOrLeaveBusy() async throws {
      let h = try fixture()
      await capture(h)
      let early = Task { await h.session.finishPractice() }
      early.cancel()
      await early.value
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertTrue(h.session.canFinishPractice)
      await usedSound(h)
      h.sound.delayReset = true
      let task = Task { await h.session.finishPractice() }
      await wait { h.sound.resetPending != nil }
      task.cancel()
      h.sound.releaseReset()
      await task.value
      XCTAssertTrue(h.writer.calls.isEmpty)
      XCTAssertNil(h.session.practiceCompletion)
      XCTAssertFalse(h.session.isFinalizingPractice)
      XCTAssertFalse(h.session.canFinishPractice)
    }

    func testReentrantWriterCannotLabelChangedSetupSavedAndCanOnlyEnterOnce() async throws {
      let h = try fixture()
      await capture(h)
      h.writer.beforeWrite = {
        XCTAssertFalse(h.session.canFinishPractice)
        XCTAssertFalse(h.session.canRecord)
        h.session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
      }
      await h.session.finishPractice()
      _ = await h.session.awaitPendingAudioCleanup()
      // An entered synchronous store call may commit; successor UI must never claim it.
      XCTAssertEqual(h.history.entries.count, 1)
      XCTAssertEqual(h.writer.calls.count, 1)
      XCTAssertNil(h.session.practiceCompletion)
      XCTAssertEqual(h.session.practiceCompletionState, .active)
      XCTAssertFalse(h.session.isFinalizingPractice)
      XCTAssertFalse(h.session.canFinishPractice)
    }

    func testAllDestructiveAndSetupClearPathsRevokeRetainedEligibilityAndRetry() async throws {
      let actions: [@MainActor (ResearchFeedbackSession) async -> Void] = [
        { _ = await $0.retake()?.value }, { $0.reset() }, { await $0.advance() },
        { _ = await $0.end().value },
        { $0.appDidBecomeInactive() }, { $0.appDidEnterBackground() },
        { $0.audioWasInterrupted() }, { $0.practiceContext = .child(ageYears: 9) },
        { $0.selectedPrompt = ResearchFeedbackCatalog.prompts[0] },
        { $0.localProcessingEnabled = false }, { $0.soundAdultConfirmed = false },
        { $0.soundProcessingEnabled = false }, { $0.practiceMode = "other" },
      ]
      for completed in [false, true] {
        for action in actions {
          let h = try fixture()
          await capture(h)
          await capture(h, another: true)
          await example(h)
          if completed {
            h.writer.mode = .failBefore
            await h.session.finishPractice()
            XCTAssertTrue(h.session.canRetryPracticeSave)
          }
          await action(h.session)
          _ = await h.session.awaitPendingAudioCleanup()
          XCTAssertTrue(h.capture.files.isEmpty)
          XCTAssertNil(h.examples.ownedURL)
          XCTAssertNil(h.session.practiceCompletion)
          XCTAssertFalse(h.session.canFinishPractice)
          XCTAssertFalse(h.session.canRetryPracticeSave)
          await h.session.finishPractice()
          await h.session.retryPracticeSave()
          XCTAssertEqual(h.writer.calls.count, completed ? 1 : 0)
        }
      }
    }

    func testSourceDeclarationRejectionRevokesVisitButOrdinaryNonmatchDoesNot() async throws {
      for rejected in [false, true] {
        let h = try fixture()
        await capture(h)
        h.word.rejectDeclaration = rejected
        h.word.reason = "requested_word_not_matched"
        await word(h)
        XCTAssertEqual(h.session.canFinishPractice, !rejected)
        await h.session.finishPractice()
        XCTAssertEqual(h.writer.calls.count, rejected ? 0 : 1)
      }
    }

    func testCommonPausePersistsThroughFinishAndNewVisitWithoutResettingCaps() async throws {
      let h = try fixture()
      await capture(h)
      h.word.reason = "cleanup_unconfirmed"
      await word(h)
      XCTAssertTrue(h.session.sharedProcessingPaused)
      await h.session.finishPractice()
      let firstID = h.session.practiceCompletion?.id
      await h.session.practiceAgain()
      XCTAssertTrue(h.session.sharedProcessingPaused)
      await capture(h)
      XCTAssertFalse(h.session.canCheck)
      XCTAssertFalse(h.session.canCheckSound)
      XCTAssertTrue(h.session.canFinishPractice)
      await h.session.finishPractice()
      XCTAssertNotEqual(h.session.practiceCompletion?.id, firstID)
      XCTAssertEqual(h.session.attemptsStarted, 2)
      XCTAssertEqual(h.session.attemptsFinished, 2)
      XCTAssertEqual(h.history.entries.count, 2)
    }

    func testPermanentGuidedOwnerRefusesAllFreeCompletionAPIs() async throws {
      let h = try fixture()
      let setupReleased = await h.session.awaitPendingAudioCleanup()
      XCTAssertTrue(setupReleased)
      let owner = UUID()
      XCTAssertTrue(
        h.session.installGuidedObserver(
          owner: owner, observer: { _ in },
          allowsAction: { _ in true }))
      await capture(h)
      XCTAssertFalse(h.session.canFinishPractice)
      await h.session.finishPractice()
      h.session.removeGuidedObserver(owner: owner)
      h.session.practiceMode = "free"
      _ = await h.session.awaitPendingAudioCleanup()
      h.session.practiceContext = .adult
      _ = await h.session.awaitPendingAudioCleanup()
      await h.session.finishPractice()
      await h.session.retryPracticeSave()
      await h.session.practiceAgain()
      XCTAssertFalse(h.session.canFinishPractice)
      XCTAssertFalse(h.session.canRetryPracticeSave)
      XCTAssertFalse(h.session.canPracticeAgain)
      XCTAssertTrue(h.writer.calls.isEmpty)
    }

    func testPendingPermissionRefusesFinishAndContextDriftCannotReusePriorClip() async throws {
      let h = try fixture()
      await capture(h)
      h.capture.delayPermission = true
      let task = Task { await h.session.recordAnotherTry() }
      await wait { h.capture.permission != nil }
      XCTAssertTrue(h.session.isPermissionPending)
      XCTAssertFalse(h.session.canFinishPractice)
      await h.session.finishPractice()
      XCTAssertTrue(h.writer.calls.isEmpty)
      h.session.practiceContext = .child(ageYears: 9)
      _ = await h.session.awaitPendingAudioCleanup()
      h.capture.releasePermission(true)
      await task.value
      XCTAssertTrue(h.capture.files.isEmpty)
      XCTAssertNil(h.session.latestReplay)
      XCTAssertFalse(h.session.canFinishPractice)
      XCTAssertTrue(h.writer.calls.isEmpty)
    }

    func testFixtureHomeAndWriterUseExactlyTheSelectedIsolatedStoreWithBothFlags() throws {
      for guided in [false, true] {
        var arguments = ["app", "-CadenceUnifiedFeedbackUITestCase", "freeCompletion"]
        if guided { arguments += ["-CadenceGuidedWordUITestCase", "mixed"] }
        let free = ResearchUnifiedFeedbackUITestFixtures.participationStore(
          for: .freeCompletion, arguments: arguments)
        let home = DirectPracticeRootView.participationHistoryStore(arguments: arguments)
        XCTAssertTrue(home === free)
        XCTAssertTrue(
          free
            === ResearchUnifiedFeedbackUITestFixtures.participationStore(
              for: .freeCompletion, arguments: arguments))
        if guided {
          XCTAssertTrue(home === ResearchGuidedWordUITestFixtures.participationStore(for: .mixed))
        }
        let writer = try XCTUnwrap(
          ResearchUnifiedFeedbackUITestFixtures.participationWriter(
            for: .freeCompletion, arguments: arguments))
        let id = UUID()
        try writer.record(
          sessionID: id, completedAt: Date(timeIntervalSince1970: 1_700_000_000),
          soundID: "b", wordCount: 1)
        XCTAssertTrue(
          home.entries.contains { $0.id == id && $0.soundID == "b" && $0.wordCount == 1 })
        try home.clear()  // Only the explicitly generated fixture's isolated store.
      }
    }
  }

  @MainActor
  private final class FreePracticeHarness {
    let capture: FreePracticeCapture
    let player = FreePracticePlayer()
    let word = FreePracticeWord()
    let sound = FreePracticeSound()
    let examples: FreePracticeExampleStore
    let historyURL: URL
    let history: PracticeParticipationStore
    let writer: FreePracticeWriter
    let clock = FreePracticeClock()
    let session: ResearchFeedbackSession
    init(writerEnabled: Bool = true) throws {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      capture = FreePracticeCapture(directory)
      examples = FreePracticeExampleStore(directory)
      historyURL = directory.appendingPathComponent("history/participation.json")
      history = PracticeParticipationStore(fileURL: historyURL)
      writer = FreePracticeWriter(history)
      let clock = self.clock
      session = makeControlledFeedbackSession(
        capturer: capture, player: player, processor: word,
        soundProcessor: sound, exampleLoader: FreePracticeExamples(), exampleStore: examples,
        participationWriter: writerEnabled ? writer : nil, now: { clock.sample() })
      session.selectedPrompt = ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      session.soundAdultConfirmed = true
      session.soundProcessingEnabled = true
    }
    func remove() async {
      capture.failDiscard = []
      capture.failure = nil
      examples.failRemove = false
      sound.releaseReset()
      _ = await session.end().value
      if session.hasLocalMediaCleanupIssue { _ = await session.retryAudioCleanup().value }
      if !session.hasLocalMediaCleanupIssue {
        try? FileManager.default.removeItem(at: capture.directory)
      }
    }
  }
  @MainActor
  private final class FreePracticeClock {
    var samples = 0
    func sample() -> Date {
      samples += 1
      return Date(timeIntervalSince1970: 1_700_000_000 + Double(samples))
    }
  }
  @MainActor
  private final class FreePracticeWriter: ResearchGuidedPracticeParticipationRecording {
    enum Mode: Equatable { case normal, failBefore, persistThenThrow }
    let store: PracticeParticipationStore
    var mode = Mode.normal
    var calls: [ResearchFreePracticeCompletion] = []
    var beforeWrite: (@MainActor () -> Void)?
    init(_ store: PracticeParticipationStore) { self.store = store }
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
      calls.append(
        .init(id: sessionID, completedAt: completedAt, soundID: soundID, wordCount: wordCount))
      beforeWrite?()
      if calls.count == 1 && mode == .failBefore {
        throw PracticeParticipationStore.StoreError.unreadable
      }
      try store.record(
        sessionID: sessionID, completedAt: completedAt, soundID: soundID, wordCount: wordCount)
      if calls.count == 1 && mode == .persistThenThrow {
        throw PracticeParticipationStore.StoreError.unreadable
      }
    }
  }
  @MainActor
  private final class FreePracticeCapture: AudioCapturing {
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
    enum Failure: CaseIterable, Equatable {
      case start, stop, invalidPCM, startDeletion, stopDeletion
    }
    let directory: URL
    var urls: [URL] = [], operations: [String] = [], discarded: [URL] = []
    var completions: [@MainActor (Bool) async -> Void] = []
    var active: URL?, failure: Failure?, permissionGranted = true, delayPermission = false
    var permission: CheckedContinuation<Bool, Never>?
    var permissions = 0, maximumFiles = 0
    var failDiscard: Set<URL> = []
    var files: [URL] { urls.filter { FileManager.default.fileExists(atPath: $0.path) } }
    init(_ directory: URL) { self.directory = directory }
    func requestPermission() async -> Bool {
      permissions += 1
      operations.append("permission")
      if delayPermission { return await withCheckedContinuation { permission = $0 } }
      return permissionGranted
    }
    func releasePermission(_ granted: Bool) {
      permission?.resume(returning: granted)
      permission = nil
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      if failure == .start { throw AudioCaptureError.couldNotStart }
      let url = directory.appendingPathComponent("generated-private-\(urls.count + 1).wav")
      urls.append(url)
      active = url
      operations.append("start:\(urls.count)")
      completions.append(onFinish)
      let samples = Array(
        repeating: Int16(4096 + (urls.count % 128) * 128), count: 3200 + urls.count)
      try (failure == .invalidPCM ? Data([1, 2]) : FeedbackFixture.wav(samples)).write(to: url)
      ownership.retain(url)
      maximumFiles = max(maximumFiles, files.count)
      if failure == .startDeletion {
        active = nil
        ownership.failed(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
    }
    func stop() throws -> CapturedRecording {
      guard let url = active else { throw AudioCaptureError.couldNotStart }
      active = nil
      if failure == .stopDeletion {
        ownership.failed(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      if failure == .stop {
        try FileManager.default.removeItem(at: url)
        ownership.removed(url)
        throw AudioCaptureError.couldNotReadRecording
      }
      return .init(
        url: url, summary: .init(duration: 4, averagePower: -20),
        cleanupOwnerID: ownership.owner(url))
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
      discarded.append(recording.url)
      let index = urls.firstIndex(of: recording.url)! + 1
      operations.append("discard:\(index)")
      if failDiscard.contains(recording.url) {
        ownership.failed(recording.url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      if FileManager.default.fileExists(atPath: recording.url.path) {
        try FileManager.default.removeItem(at: recording.url)
      }
      ownership.removed(recording.url)
    }
  }

  private typealias FreePracticePlayer = FeedbackPlayer

  @MainActor
  private final class FreePracticeWord: ResearchFeedbackProcessing {
    struct Call {
      let attempt: UUID
      let recording: CapturedRecording
      let prompt: ResearchFeedbackPrompt
      let context: ResearchPracticeContext
      let body: Data
    }
    var calls: [Call] = [], reason: String?, delayed = false, returned = false
    var pending: CheckedContinuation<RecordingFeedback, Never>?
    private var result: RecordingFeedback?
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) async throws -> RecordingFeedback {
      let audio = try FeedbackPCM.read(recording.url)
      let body = try ResearchFeedbackClient.requestBody(
        attemptId: attemptId, audio: audio, prompt: prompt, practiceContext: practiceContext)
      calls.append(
        .init(
          attempt: attemptId, recording: recording, prompt: prompt, context: practiceContext,
          body: body))
      let value = try FeedbackContract.decode(
        FeedbackFixture.json(FeedbackFixture.response(body, audio: audio, reason: reason)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: prompt.targetUnsupported)
      result = value
      defer { returned = true }
      if delayed { return await withCheckedContinuation { pending = $0 } }
      return value
    }
    var rejectDeclaration = false
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext,
      onEvent: @escaping @MainActor (ResearchFeedbackProcessingEvent) -> Void
    ) async throws -> RecordingFeedback {
      if rejectDeclaration {
        onEvent(.declarationRejected)
        throw RecordingFeedbackError.invalidResponse
      }
      return try await process(
        attemptId: attemptId, recording: recording, prompt: prompt,
        practiceContext: practiceContext)
    }
    func release() {
      if let result { pending?.resume(returning: result) }
      pending = nil
    }
  }

  @MainActor
  private final class FreePracticeSound: ResearchSoundProcessing {
    struct Reset {
      let declaration: ResearchSoundDeclaration
      let sessionId: String
      let generation: Int
    }
    let declarationValue = ResearchSoundDeclaration(
      serverNonce: "33333333-3333-4333-8333-333333333333",
      csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    let result = ResearchSoundObservation(
      status: .observedModelPreference, reason: "model_preferred_candidate", preference: .wPath)
    var prepared: [ResearchSoundPrepared] = [], cancelled: [ResearchSoundPrepared] = [],
      resets: [Reset] = []
    var observeFailure = false, delayReset = false, controlFailure = false
    var resetPending: CheckedContinuation<Void, Never>?
    func declaration() async throws -> ResearchSoundDeclaration { declarationValue }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared {
      let value = try ResearchSoundContract.prepare(
        audio: ResearchSoundContract.canonicalize(FeedbackPCM.read(recording.url)),
        declaration: declaration, context: context)
      prepared.append(value)
      return value
    }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      if observeFailure { throw RecordingFeedbackError.serviceUnavailable }
      return result
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws { cancelled.append(prepared) }
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {
      resets.append(.init(declaration: declaration, sessionId: sessionId, generation: generation))
      if delayReset { await withCheckedContinuation { resetPending = $0 } }
      if controlFailure { throw RecordingFeedbackError.serviceUnavailable }
    }
    func releaseReset() {
      resetPending?.resume()
      resetPending = nil
    }
  }

  @MainActor
  private final class FreePracticeExamples: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated control", licenseId: "Generated fixture",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated PCM, no human reference", changes: "Generated test only",
        speakerAgeKnown: false,
        clinicalReferenceApproved: false, wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200,
        isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data { bytes }
  }

  @MainActor
  private final class FreePracticeExampleStore: ResearchPracticeExampleStoring {
    let directory: URL
    var ownedURL: URL?, failRemove = false
    init(_ directory: URL) { self.directory = directory }
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = directory.appendingPathComponent("generated-public-\(UUID().uuidString).wav")
      try data.write(to: url)
      ownedURL = url
      return url
    }
    func remove(_ url: URL) throws {
      guard ownedURL == url, !failRemove else { throw ResearchPracticeExampleError.cleanupFailed }
      try FileManager.default.removeItem(at: url)
      ownedURL = nil
    }
  }
#endif
