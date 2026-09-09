import Combine
import Dispatch
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class DirectPracticeSessionTests: XCTestCase {
  func testRecordingInputPowerOnlyObservesCurrentRecording() async throws {
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    XCTAssertNil(session.recordingInputPower)
    XCTAssertEqual(capturer.powerReads, 0)
    capturer.holdsPermission = true
    let start = Task { await session.startRecording() }
    await capturer.waitForPermissionRequest()
    XCTAssertNil(session.recordingInputPower)
    XCTAssertEqual(capturer.powerReads, 0)
    capturer.resolvePermission(true)
    await start.value
    for power: Float in [-160, -36.5, 0] {
      capturer.power = power
      XCTAssertEqual(session.recordingInputPower, power)
    }
    for power: Float? in [nil, .nan, .infinity, -.infinity] {
      capturer.power = power
      XCTAssertNil(session.recordingInputPower)
    }
    XCTAssertEqual(capturer.powerReads, 7)
    session.stopRecording()
    XCTAssertNil(session.recordingInputPower)
    XCTAssertEqual(capturer.powerReads, 7)
    capturer.holdsPermission = false
    await session.recordAnotherTry()
    capturer.power = -12
    await capturer.finish(index: 0)
    XCTAssertEqual(session.phase, .recording)
    XCTAssertEqual(session.recordingInputPower, -12)
    session.appDidEnterBackground()
    XCTAssertNil(session.recordingInputPower)
    XCTAssertEqual(capturer.powerReads, 8)
    await settle(session)
    await session.end()
    XCTAssertNil(session.recordingInputPower)
    XCTAssertEqual(capturer.powerReads, 8)
  }

  func testRecordingInputPowerRejectsReentrantStopAndCleanupRevocation() async {
    for cleanupFails in [false, true] {
      let capturer = DirectPracticeCapturer()
      let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
      await session.startRecording()
      capturer.power = -24
      capturer.shouldFailHardwareCleanup = cleanupFails
      capturer.onPowerRead = {
        capturer.onPowerRead = nil
        session.stopRecording()
      }
      XCTAssertNil(session.recordingInputPower)
      await settle(session)
      XCTAssertNil(session.recordingInputPower)
      XCTAssertEqual(capturer.powerReads, 1)
      if cleanupFails {
        XCTAssertTrue(session.cleanupBlocked)
        capturer.shouldFailHardwareCleanup = false
        await session.retryCleanup()
      }
      await session.end()
      XCTAssertNil(session.recordingInputPower)
      XCTAssertEqual(capturer.powerReads, 1)
    }
  }

  func testCompletionRecordsOnceAfterAudioDiscardAndEachNewSessionGetsNewParticipation()
    async throws
  {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    let capturer = DirectPracticeCapturer(recordingDirectory: directory)
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(), history: history)
    for _ in 0..<session.totalWords {
      await session.startRecording()
      session.stopRecording()
      XCTAssertEqual(history.entries.count, 0)
      await session.continuePractice()
    }
    XCTAssertEqual(session.phase, .completed)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertEqual(history.entries.count, 1)
    XCTAssertEqual(history.entries.first?.soundID, "b")
    XCTAssertEqual(history.entries.first?.wordCount, 3)
    let firstAnnouncement = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    XCTAssertEqual(firstAnnouncement.message, "Practice complete.")
    XCTAssertEqual(firstAnnouncement.completion, session.participationCompletion)
    await session.continuePractice()
    await capturer.finish(index: 2)
    XCTAssertEqual(history.entries.count, 1)
    await session.restart()
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    for _ in 0..<session.totalWords {
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }
    let nextAnnouncement = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    XCTAssertNotEqual(nextAnnouncement.id, firstAnnouncement.id)
    XCTAssertNotEqual(nextAnnouncement.completion.id, firstAnnouncement.completion.id)
    await session.practiceMore()
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    for _ in 0..<session.totalWords {
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }
    XCTAssertEqual(history.entries.count, 3)
    XCTAssertEqual(Set(history.entries.map(\.id)).count, 3)
    XCTAssertEqual(PracticeParticipationStore(fileURL: file).entries, history.entries)
  }

  func testHistoryWriteFailureStillCompletesPracticeAndAllowsAnotherSession() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let session = DirectPracticeSession(
      capturer: DirectPracticeCapturer(), player: DirectPracticePlayer(), history: history)
    for _ in 0..<session.totalWords {
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(
      session.historyError,
      "Practice complete, but this session could not be saved to practice history.")
    XCTAssertTrue(history.entries.isEmpty)
    try FileManager.default.removeItem(at: file)
    await session.restart()
    XCTAssertNil(session.historyError)
    for _ in 0..<session.totalWords {
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }
    XCTAssertEqual(session.phase, .completed)
    XCTAssertNil(session.historyError)
    XCTAssertEqual(history.entries.count, 1)
  }

  func testPartialCancelledBackgroundAndFailedCleanupCannotSaveCompletedParticipation() async throws
  {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let history = PracticeParticipationStore(
      fileURL: directory.appendingPathComponent("participation.json"))
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(), history: history)
    await session.startRecording()
    session.stopRecording()
    await session.continuePractice()
    await session.startRecording()
    session.appDidEnterBackground()
    await settle(session)
    await capturer.finish(index: 1)
    XCTAssertEqual(session.phase, .ready)
    XCTAssertTrue(history.entries.isEmpty)
    await session.end()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertTrue(history.entries.isEmpty)
    await session.restart()
    for _ in 0..<session.totalWords - 1 {
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }
    await session.startRecording()
    session.stopRecording()
    capturer.shouldFailDiscard = true
    await session.continuePractice()
    guard case .failed = session.phase else {
      return XCTFail("Audio cleanup must finish before participation is saved.")
    }
    XCTAssertTrue(history.entries.isEmpty)
  }

  func testPermissionDenialDoesNotStartOrAdvanceAndCanBeRetried() async {
    let capturer = DirectPracticeCapturer()
    capturer.permissionGranted = false
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())

    XCTAssertTrue(session.canStartRecording)
    await session.startRecording()

    XCTAssertEqual(session.phase, .permissionDenied)
    XCTAssertTrue(session.canStartRecording)
    XCTAssertEqual(capturer.startCount, 0)
    XCTAssertEqual(session.completedWords, 0)
    capturer.permissionGranted = true
    await session.startRecording()
    XCTAssertEqual(session.phase, .recording)
    XCTAssertFalse(session.canStartRecording)
  }

  func testPermissionDialogInactivityStillAllowsRecording() async {
    let capturer = DirectPracticeCapturer()
    capturer.holdsPermission = true
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    let starting = Task { await session.startRecording() }
    await capturer.waitForPermissionRequest()

    session.appDidBecomeInactive()
    await settle(session)
    capturer.resolvePermission(true)
    await starting.value

    XCTAssertEqual(session.phase, .recording)
    XCTAssertEqual(capturer.startCount, 1)
  }

  func testBackgroundDuringPermissionCannotStartCaptureLater() async {
    for granted in [true, false] {
      let capturer = DirectPracticeCapturer()
      capturer.holdsPermission = true
      let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
      let starting = Task { await session.startRecording() }
      await capturer.waitForPermissionRequest()

      session.appDidEnterBackground()
      await settle(session)
      capturer.resolvePermission(granted)
      await starting.value

      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(capturer.startCount, 0)
    }
  }

  func testEndDuringPermissionCannotStartCaptureLater() async {
    let capturer = DirectPracticeCapturer()
    capturer.holdsPermission = true
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    let starting = Task { await session.startRecording() }
    await capturer.waitForPermissionRequest()

    await session.end()
    capturer.resolvePermission(true)
    await starting.value

    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(capturer.startCount, 0)
  }

  func testDuplicateRecordRequestsStartOnlyOneCapture() async {
    let capturer = DirectPracticeCapturer()
    capturer.holdsPermission = true
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    let starting = Task { await session.startRecording() }
    await capturer.waitForPermissionRequest()

    await session.startRecording()
    capturer.resolvePermission(true)
    await starting.value
    await session.startRecording()

    XCTAssertEqual(capturer.permissionRequestCount, 1)
    XCTAssertEqual(capturer.startCount, 1)
  }

  func testCaptureIsRetainedForReplayAndRetryDeletesItWithoutAdvancing() async {
    let capturer = DirectPracticeCapturer()
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()

    XCTAssertEqual(session.phase, .review(capturer.summary, .acceptable))
    XCTAssertEqual(capturer.discardCount, 0)
    await session.togglePlayback()
    XCTAssertEqual(player.playedURLs, [capturer.recordingURL])
    XCTAssertTrue(session.isPlaying)

    await session.retry()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertFalse(session.isPlaying)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 1)
  }

  func testAdvisoryQualityAllowsReplayAndContinueWithoutPronunciationResult() async {
    let capturer = DirectPracticeCapturer()
    capturer.summary = CaptureSummary(duration: 0.1, averagePower: -90)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()

    guard case .review(_, .retry(let coaching)) = session.phase else {
      return XCTFail("A quiet or short clip should remain available with recording advice.")
    }
    XCTAssertFalse(coaching.detail.contains("tone"))
    await session.togglePlayback()
    XCTAssertEqual(player.playedURLs.count, 1)
    await session.continuePractice()

    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(session.completedWords, 1)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(session.isPlaying)
  }

  func testThreeContinuedWordsCompleteAndRestartResetsProgress() async {
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    var words: [String] = []
    for _ in 0..<3 {
      words.append(session.currentPrompt.word)
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }

    XCTAssertEqual(words, ["ball", "boat", "bee"])
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(session.completedWords, 3)
    XCTAssertEqual(capturer.discardCount, 3)
    await session.continuePractice()
    await session.startRecording()
    XCTAssertEqual(session.completedWords, 3)
    XCTAssertEqual(capturer.startCount, 3)

    await session.restart()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(session.currentPrompt.word, "ball")
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 0)
  }

  func testPracticeMoreAdvancesWordsAndPreservesTemporaryAudioCleanup() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let capturer = DirectPracticeCapturer(recordingDirectory: directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    XCTAssertNil(session.nextPracticeSound)
    await session.practiceMore()
    XCTAssertEqual(session.currentPrompt.word, "ball")
    for _ in 0..<3 {
      await session.startRecording()
      session.stopRecording()
      await session.togglePlayback()
      await session.continuePractice()
    }
    let next = try XCTUnwrap(session.nextPracticeSound)
    XCTAssertTrue(Set(next.prompts.map(\.word)).isDisjoint(with: ["ball", "boat", "bee"]))
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    let cancellationCount = capturer.cancelCount
    await session.practiceMore()
    XCTAssertEqual(capturer.cancelCount, cancellationCount + 1)
    XCTAssertEqual(session.sound, next)
    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 0)
    XCTAssertFalse(session.isPlaying)
    player.finish(index: 2)
    player.deliverCapturedCompletion(index: 2)
    XCTAssertEqual(session.phase, .ready)
    XCTAssertFalse(session.isPlaying)
  }

  func testLastCatalogWordCompletesOneWordAndDoesNotWrapToStarter() async throws {
    let last = try XCTUnwrap(PracticeLibrary.entries(soundID: "b", position: .beginning).last)
    let sound = try XCTUnwrap(
      PracticeLibrary.session(soundID: "b", position: .beginning, startingAt: last.id))
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(
      sound: sound, capturer: capturer, player: DirectPracticePlayer())
    XCTAssertEqual(session.totalWords, 1)
    await session.startRecording()
    session.stopRecording()
    await session.continuePractice()
    XCTAssertEqual(session.phase, .completed)
    XCTAssertNil(session.nextPracticeSound)
    await session.practiceMore()
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(session.currentPrompt.word, last.prompt.word)
  }

  func testAutomaticRecorderCompletionAndStaleCompletionAreSafe() async {
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    await session.startRecording()
    await capturer.finish(index: 0)
    XCTAssertEqual(session.phase, .review(capturer.summary, .acceptable))
    await session.retry()
    await session.startRecording()

    await capturer.finish(index: 0)
    XCTAssertEqual(session.phase, .recording)
    XCTAssertEqual(capturer.stopCount, 1)
    await capturer.finish(index: 1)
    XCTAssertEqual(capturer.stopCount, 2)
  }

  func testFailedAutomaticCompletionCancelsAndAllowsRetry() async {
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    await session.startRecording()
    await capturer.finish(index: 0, successfully: false)

    guard case .failed = session.phase else { return XCTFail("Expected a recording error.") }
    XCTAssertEqual(capturer.cancelCount, 1)
    XCTAssertEqual(session.attemptCount, 0)
    await session.retry()
    XCTAssertEqual(session.phase, .ready)
  }

  func testRecorderStartFailureCanBeRetriedWithoutAdvancing() async {
    let capturer = DirectPracticeCapturer()
    capturer.shouldFailStart = true
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    await session.startRecording()

    guard case .failed = session.phase else { return XCTFail("Expected a microphone error.") }
    XCTAssertFalse(session.recordingStartupUnavailable)
    XCTAssertTrue(session.canRetry)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 0)
    await session.retry()
    capturer.shouldFailStart = false
    await session.startRecording()
    XCTAssertEqual(session.phase, .recording)
  }

  func testStartupCleanupUnavailableWithholdsRecordingAndRetryAcrossLifecycle() async {
    let capturer = DirectPracticeCapturer()
    capturer.startupAvailability = .cleanupFailed
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    XCTAssertTrue(session.recordingStartupUnavailable)
    XCTAssertFalse(session.canStartRecording)
    XCTAssertFalse(session.canRetry)
    XCTAssertFalse(
      session.actionsDisabled, "Safe navigation is independent of recording availability.")
    XCTAssertFalse(session.canRecordAnotherTry)
    await session.startRecording()
    await session.recordAnotherTry()
    await session.retry()
    session.appDidEnterBackground()
    await settle(session)
    session.appDidBecomeActive()
    await session.startRecording()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertTrue(session.recordingStartupUnavailable)
    XCTAssertFalse(session.canRetry)
    XCTAssertEqual(capturer.permissionRequestCount, 0)
    XCTAssertEqual(capturer.startCount, 0)
    XCTAssertTrue(session.tries.isEmpty)
    XCTAssertEqual(session.attemptCount, 0)
    XCTAssertEqual(session.completedWords, 0)
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
  }

  func testStartupUnavailableDoesNotBlockKeptTakePlaybackOrExplicitDiscard() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await h.session.startRecording()
    h.session.stopRecording()
    let kept = try XCTUnwrap(h.session.latestTry)
    h.capturer.startupAvailability = .cleanupFailed
    XCTAssertFalse(h.session.canRecordAnotherTry)
    XCTAssertTrue(h.session.canRetry, "An exact kept take can still be explicitly discarded.")
    await h.session.togglePlayback()
    XCTAssertEqual(h.player.playedURLs, [h.capturer.urls[0]])
    await h.session.togglePlayback()
    XCTAssertEqual(h.session.latestTry?.id, kept.id)
    XCTAssertEqual(h.session.phase, .review(kept.summary, kept.assessment))
    await h.session.retry()
    XCTAssertTrue(h.session.tries.isEmpty)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertFalse(FileManager.default.fileExists(atPath: h.capturer.urls[0].path))
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertFalse(h.session.canRetry)
    XCTAssertTrue(h.session.recordingStartupUnavailable)
    XCTAssertEqual(h.session.attemptCount, 1)
    XCTAssertTrue(h.history.entries.isEmpty)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
  }

  func testGuidedStartupUnavailablePreservesSkipFinishAndCloseWithoutParticipation()
    async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    h.capturer.startupAvailability = .cleanupFailed
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    XCTAssertFalse(h.session.canRetry)
    XCTAssertFalse(h.session.actionsDisabled)
    XCTAssertFalse(h.session.interactiveDismissDisabled)
    XCTAssertTrue(flow.playerPresentation.canSkip)
    XCTAssertTrue(flow.playerPresentation.canFinishStage)
    await h.session.startRecording()
    await flow.skipVisit()
    await flow.finishStageNow()
    XCTAssertEqual(flow.ledger?.stage, .choosingPractice)
    let selected = try XCTUnwrap(flow.ledger?.entries.first)
    flow.togglePracticeSelection(entryID: selected.id)
    await flow.startPractice()
    XCTAssertEqual(flow.ledger?.stage, .practice)
    XCTAssertFalse(flow.playerPresentation.canContinue)
    XCTAssertTrue(flow.playerPresentation.canSkip)
    XCTAssertTrue(flow.playerPresentation.canFinishStage)
    await h.session.startRecording()
    await flow.skipVisit()
    XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
    await flow.startRecheck()
    await flow.finishStageNow()
    XCTAssertEqual(flow.ledger?.stage, .completed)
    XCTAssertEqual(h.capturer.permissionRequests, 0)
    XCTAssertTrue(h.capturer.urls.isEmpty)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    let closed = await flow.close()
    XCTAssertTrue(closed)
    XCTAssertTrue(flow.isClosed)
  }

  func testUnreadableCaptureCleansUpAndDoesNotCountAnAttempt() async {
    let capturer = DirectPracticeCapturer()
    capturer.shouldFailStop = true
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    await session.startRecording()
    session.stopRecording()
    await settle(session)

    guard case .failed = session.phase else { return XCTFail("Expected a recording read error.") }
    XCTAssertEqual(capturer.cancelCount, 1)
    XCTAssertEqual(session.attemptCount, 0)
    XCTAssertEqual(session.completedWords, 0)
    await session.retry()
    XCTAssertEqual(session.phase, .ready)
  }

  func testPlaybackFailureLeavesRetryAndContinueAvailable() async {
    let player = DirectPracticePlayer()
    player.shouldFail = true
    let session = DirectPracticeSession(capturer: DirectPracticeCapturer(), player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()

    XCTAssertFalse(session.isPlaying)
    XCTAssertNotNil(session.playbackError)
    guard case .review = session.phase else {
      return XCTFail("Replay failure must preserve the clip.")
    }
    await session.continuePractice()
    XCTAssertEqual(session.completedWords, 1)
  }

  func testOldPlaybackCallbackCannotStopANewerReplay() async {
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: DirectPracticeCapturer(), player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    await session.togglePlayback()
    await session.togglePlayback()

    player.finish(index: 0, successfully: false)
    player.deliverCapturedCompletion(index: 0, successfully: false)
    XCTAssertTrue(session.isPlaying)
    XCTAssertNil(session.playbackError)
    player.finish(index: 1)
    await player.waitForIdle()
    XCTAssertFalse(session.isPlaying)
  }

  func testInterruptionCancelsActiveRecordingAndIgnoresItsCallback() async {
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer())
    await session.startRecording()
    session.audioWasInterrupted()
    await settle(session)
    await capturer.finish(index: 0)

    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(capturer.cancelCount, 1)
    XCTAssertEqual(capturer.stopCount, 0)
  }

  func testBackgroundDeletesRealTemporaryFileAndStopsReplay() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let capturer = DirectPracticeCapturer(recordingDirectory: directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))

    session.appDidEnterBackground()
    await settle(session)

    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertEqual(session.phase, .ready)
    XCTAssertFalse(session.isPlaying)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertTrue(session.canRetry)
    player.finish(index: 0)
    player.deliverCapturedCompletion(index: 0)
    XCTAssertEqual(session.phase, .ready)
  }

  func testEndDeletesReplayAndCannotBeRevivedByLifecycleEvents() async {
    let capturer = DirectPracticeCapturer()
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    await session.end()
    session.appDidBecomeInactive()
    await settle(session)
    session.appDidEnterBackground()
    await settle(session)
    session.audioWasInterrupted()
    await settle(session)
    player.finish(index: 0)

    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(session.isPlaying)
  }

  func testDeletionFailureStopsPlaybackAndPreventsFurtherRecordingOrAdvancement() async {
    let capturer = DirectPracticeCapturer()
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    capturer.shouldFailDiscard = true
    await session.continuePractice()

    XCTAssertEqual(
      session.phase,
      .failed(AudioCaptureError.couldNotDeleteTemporaryRecording.localizedDescription))
    XCTAssertFalse(session.canRetry)
    XCTAssertFalse(session.isPlaying)
    XCTAssertEqual(session.completedWords, 0)
    await session.retry()
    await session.restart()
    await session.startRecording()
    XCTAssertEqual(capturer.startCount, 1)
  }

  func testPreparationDoesNotClaimPlayingAndBackgroundRevokesBeforeCleanup() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files)
    player.holdPreparation = true
    player.holdCleanup = true
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    let starting = Task { await session.togglePlayback() }
    let queuedDriver = await player.driver(0)
    let driver = try XCTUnwrap(queuedDriver)
    defer { driver.releaseAll() }
    await entered(driver.prepared)
    XCTAssertFalse(session.isPlaying)
    XCTAssertEqual(session.playbackControlLabel, "Cancel playback")
    XCTAssertTrue(session.actionsDisabled)
    XCTAssertTrue(session.interactiveDismissDisabled)
    session.appDidEnterBackground()
    XCTAssertEqual(session.playbackControlLabel, "Stopping…")
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    await session.startRecording()
    XCTAssertEqual(capturer.startCount, 1)
    driver.releasePreparation()
    await entered(driver.cleaning)
    XCTAssertFalse(session.isPlaying)
    XCTAssertEqual(capturer.discardCount, 0)
    driver.releaseCleanup()
    await starting.value
    await settle(session)
    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testDuplicateCloseJoinsCleanupAndSupersedesHeldFinishWithoutHistory() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files)
    player.holdCleanup = true
    let history = PracticeParticipationStore(
      fileURL: fixture.directory.appendingPathComponent("history.json"))
    let session = DirectPracticeSession(
      sound: try oneWordSound(), capturer: capturer, player: player, history: history)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let queuedDriver = await player.driver(0)
    let driver = try XCTUnwrap(queuedDriver)
    defer { driver.releaseAll() }
    let next = Task { await session.continuePractice() }
    await entered(driver.cleaning)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertEqual(capturer.discardCount, 0)
    let closeRequested = XCTestExpectation(description: "Close intent is committed")
    var noted = false
    let closeObservation = session.$closeNote.sink { note in
      if note != nil && !noted {
        noted = true
        closeRequested.fulfill()
      }
    }
    defer { closeObservation.cancel() }
    let firstClose = Task { await session.end() }
    await entered(closeRequested)
    let secondCloseStarted = XCTestExpectation(
      description: "duplicate Close enters while cleanup is held")
    let secondClose = Task { @MainActor in
      secondCloseStarted.fulfill()
      return await session.end()
    }
    await entered(secondCloseStarted)
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertEqual(
      session.closeNote, "Stopping playback before closing. This screen closes once it has stopped."
    )
    driver.releaseCleanup()
    await next.value
    let firstEnded = await firstClose.value
    let secondEnded = await secondClose.value
    XCTAssertTrue(firstEnded)
    XCTAssertTrue(secondEnded)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertEqual(driver.stopCount, 1)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testBackgroundSupersedesHeldContinueAndCannotAdvanceOnLateRelease() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files)
    player.holdCleanup = true
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let queuedDriver = await player.driver(0)
    let driver = try XCTUnwrap(queuedDriver)
    defer { driver.releaseAll() }
    let next = Task { await session.continuePractice() }
    await entered(driver.cleaning)
    session.appDidEnterBackground()
    driver.releaseCleanup()
    await next.value
    await settle(session)
    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testFailedFinishRetainsExactFileAndRetryRequiresFreshFinishTap() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files)
    player.cleanupFailures = 1
    let history = PracticeParticipationStore(
      fileURL: fixture.directory.appendingPathComponent("history.json"))
    let session = DirectPracticeSession(
      sound: try oneWordSound(), capturer: capturer, player: player, history: history)
    await session.startRecording()
    session.stopRecording()
    let bytes = try Data(contentsOf: capturer.recordingURL)
    await session.togglePlayback()
    await session.continuePractice()
    XCTAssertTrue(session.hasPlaybackCleanupIssue)
    XCTAssertTrue(session.canRetryCleanup)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(capturer.discardCount, 0)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertEqual(try Data(contentsOf: capturer.recordingURL), bytes)
    await session.continuePractice()
    await session.startRecording()
    XCTAssertEqual(capturer.startCount, 1)
    await session.retryCleanup()
    XCTAssertFalse(session.cleanupBlocked)
    XCTAssertEqual(session.playbackState, .idle)
    XCTAssertEqual(session.phase, .review(capturer.summary, .acceptable))
    XCTAssertEqual(capturer.discardCount, 0)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertEqual(try Data(contentsOf: capturer.recordingURL), bytes)
    // Each new driver copies this configuration; fail only the first playback operation.
    // The original driver's negative receipt and genuine explicit retry remain unchanged.
    player.cleanupFailures = 0
    // A successful retry clears the exact active ID, despite the original negative receipt.
    await session.togglePlayback()
    XCTAssertTrue(session.isPlaying)
    await session.continuePractice()
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(history.entries.count, 1)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testBlockedCloseCannotEscapeAndExplicitRetryResumesAuthorizedClose() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let gate = AudioHardwareOwnership()
    let player = DirectPracticePlayer(files: files, gate: gate)
    player.cleanupFailures = 1
    let session = DirectPracticeSession(
      capturer: capturer, player: player,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let ended = await session.end()
    XCTAssertFalse(ended)
    let repeated = await session.end()
    XCTAssertFalse(repeated)
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertTrue(session.interactiveDismissDisabled)
    XCTAssertTrue(session.hasHardwareCleanupIssue)
    XCTAssertEqual(
      session.closeNote,
      "Playback hasn't confirmed it stopped, so this screen stays open. Use Retry stopping.")
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertEqual(capturer.cleanupState.fileBlockedOwnerIDs, files.pendingCleanupOwners)
    await session.retryCleanup()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertFalse(session.hasHardwareCleanupIssue)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testNaturalCompletionWaitsForCleanupAndStaleCallbackCannotMutateNewReplay() async throws {
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(files: files)
    let player = DirectPracticePlayer(files: files)
    player.holdCleanup = true
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let queuedDriver = await player.driver(0)
    let driver = try XCTUnwrap(queuedDriver)
    defer { driver.releaseAll() }
    driver.finish(true)
    await entered(driver.cleaning)
    XCTAssertFalse(session.isPlaying)
    XCTAssertEqual(session.playbackControlLabel, "Stopping…")
    XCTAssertEqual(capturer.discardCount, 0)
    driver.releaseCleanup()
    await player.waitForIdle()
    // Runtime completion is synchronous on MainActor after released idle; the waiter
    // resumes after that actor delivery returns, so a single yield is not a barrier.
    player.holdCleanup = false
    await session.togglePlayback()
    XCTAssertTrue(session.isPlaying)
    driver.finish(false)
    player.deliverCapturedCompletion(index: 0, successfully: false)
    XCTAssertTrue(session.isPlaying)
    XCTAssertNil(session.playbackError)
    _ = await session.end()
  }

  func testCaptureHardwareFailureRetainsFileAndCloseUntilExactRetry() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    capturer.shouldFailHardwareCleanup = true
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files))
    await session.startRecording()
    session.stopRecording()
    await settle(session)
    XCTAssertTrue(session.captureCleanupState.hasHardwareIssue)
    XCTAssertTrue(session.hasHardwareCleanupIssue)
    XCTAssertEqual(session.attemptCount, 0)
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    let ended = await session.end()
    let repeated = await session.end()
    XCTAssertFalse(ended)
    XCTAssertFalse(repeated)
    XCTAssertNotEqual(session.phase, .ended)
    capturer.shouldFailHardwareCleanup = false
    await session.retryCleanup()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testFileFailureRemainsDistinctAndExplicitRetryDeletesBeforeClose() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files))
    await session.startRecording()
    session.stopRecording()
    capturer.shouldFailDiscard = true
    let ended = await session.end()
    XCTAssertFalse(ended)
    XCTAssertFalse(session.hasHardwareCleanupIssue)
    XCTAssertTrue(session.captureCleanupState.hasFileIssue)
    XCTAssertTrue(session.canRetryCleanup)
    XCTAssertEqual(
      session.closeNote,
      "The recording couldn't be removed, so this screen stays open. Use Retry cleanup.")
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    let repeated = await session.end()
    XCTAssertFalse(repeated)
    capturer.shouldFailDiscard = false
    await session.retryCleanup()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    // The successful file-owner receipt is authoritative; no second unowned discard occurs.
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testDisappearanceRetainsSessionUntilItsOwnedCleanupFinishes() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files)
    player.holdCleanup = true
    var session: DirectPracticeSession? = DirectPracticeSession(capturer: capturer, player: player)
    await session?.startRecording()
    session?.stopRecording()
    await session?.togglePlayback()
    let queuedDriver = await player.driver(0)
    let driver = try XCTUnwrap(queuedDriver)
    defer { driver.releaseAll() }
    weak var owner = session
    session?.viewDidDisappear()
    session = nil
    await entered(driver.cleaning)
    XCTAssertNotNil(owner, "The lifecycle task must own the session through cleanup.")
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    driver.releaseCleanup()
    // Joining the retained Close also waits for file removal, beyond runtime idle.
    let ended = await owner?.end()
    XCTAssertEqual(ended, true)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testCloseOrBackgroundDuringPlaybackRecoveryRequiresDeletionBeforeTransition() async throws {
    for close in [true, false] {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files)
      player.cleanupFailures = 1
      player.holdRetryCleanup = true
      let session = DirectPracticeSession(capturer: capturer, player: player)
      await session.startRecording()
      session.stopRecording()
      await session.togglePlayback()
      await session.continuePractice()
      XCTAssertTrue(session.hasPlaybackCleanupIssue)
      let queuedDriver = await player.driver(0)
      let driver = try XCTUnwrap(queuedDriver)
      defer { driver.releaseAll() }
      let recovery = Task { await session.retryCleanup() }
      await entered(driver.retryCleaning)
      XCTAssertTrue(session.isRetryingPlaybackCleanup)
      XCTAssertFalse(session.captureCleanupState.hasHardwareIssue)
      XCTAssertFalse(session.captureCleanupState.hasFileIssue)
      let closing: Task<Bool, Never>?
      if close {
        let closeRequested = XCTestExpectation(description: "Close supersedes recovery")
        var noted = false
        let observation = session.$closeNote.sink { note in
          if note != nil && !noted {
            noted = true
            closeRequested.fulfill()
          }
        }
        closing = Task { await session.end() }
        await entered(closeRequested)
        observation.cancel()
      } else {
        closing = nil
        session.appDidEnterBackground()
      }
      XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      XCTAssertEqual(capturer.discardCount, 0)
      XCTAssertEqual(session.completedWords, 0)
      driver.releaseRetryCleanup()
      await recovery.value
      if let closing {
        let ended = await closing.value
        XCTAssertTrue(ended)
        XCTAssertEqual(session.phase, .ended)
      } else {
        await settle(session)
        XCTAssertEqual(session.phase, .ready)
      }
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      XCTAssertEqual(session.completedWords, 0)
    }
  }

  func testExplicitSecondFileClosePreservesReachableProducerRecoveryAfterViewLoss() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    var capturer: DirectPracticeCapturer? = DirectPracticeCapturer(
      recordingDirectory: fixture.directory, files: files)
    capturer?.shouldFailDiscard = true
    let url = try XCTUnwrap(capturer?.recordingURL)
    let player = DirectPracticePlayer(files: files, gate: gate)
    var session: DirectPracticeSession? = DirectPracticeSession(
      capturer: capturer, player: player,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session?.startRecording()
    session?.stopRecording()
    let first = await session?.end()
    XCTAssertEqual(first, false)
    XCTAssertEqual(
      session?.closeNote,
      "The recording couldn't be removed. Use Retry cleanup, or tap Close again to leave it pending."
    )
    let owner = try XCTUnwrap(capturer?.cleanupState.fileBlockedOwnerIDs.first)
    let bytes = try Data(contentsOf: url)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    XCTAssertNil(gate.currentLease)
    let second = await session?.end()
    XCTAssertEqual(second, true)
    XCTAssertEqual(session?.phase, .ended)
    XCTAssertEqual(session?.completedWords, 0)
    XCTAssertEqual(try Data(contentsOf: url), bytes)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    weak var heldProducer = capturer
    session = nil
    capturer = nil
    XCTAssertNotNil(heldProducer, "Real process recovery must hold the producer after leaving.")
    heldProducer?.shouldFailDiscard = false
    XCTAssertTrue(files.retryCleanup(owner: owner))
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
  }

  func testSecondFileCloseRefusesMissingRecoveryAndAnyRemainingHardwareLease() async throws {
    for recoverable in [false, true] {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      capturer.shouldFailDiscard = true
      capturer.registersFileRecovery = recoverable
      let session = DirectPracticeSession(
        capturer: capturer,
        player: DirectPracticePlayer(files: files, gate: gate),
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      await session.startRecording()
      session.stopRecording()
      let first = await session.end()
      XCTAssertFalse(first)
      let lease: AudioHardwareOwnership.Lease?
      if recoverable {
        lease = try gate.reserve(operationID: UUID(), owner: .capture)
      } else {
        lease = nil
      }
      defer { if let lease, gate.currentLease == lease { gate.release(lease) } }
      let second = await session.end()
      XCTAssertFalse(second)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertEqual(
        session.closeNote,
        "The recording couldn't be removed, so this screen stays open. Use Retry cleanup.")
      XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      XCTAssertEqual(capturer.discardCount, 1)
      if let lease { XCTAssertTrue(gate.release(lease)) }
      capturer.shouldFailDiscard = false
      await session.retryCleanup()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    }
  }

  func testExternalFileRecoveryClearsTakeBeforePendingCloseCanDiscardAgain() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    capturer.shouldFailDiscard = true
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files))
    await session.startRecording()
    session.stopRecording()
    let first = await session.end()
    XCTAssertFalse(first)
    let owner = try XCTUnwrap(capturer.cleanupState.fileBlockedOwnerIDs.first)
    capturer.shouldFailDiscard = false
    XCTAssertTrue(files.retryCleanup(owner: owner))
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testLifecycleNegativePlaybackRegistersExactBorrowRefusedFileRecoveryOnce() async throws {
    for manualStopFirst in [false, true] {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files, gate: gate)
      player.cleanupFailures = 1
      var session: DirectPracticeSession? = DirectPracticeSession(
        capturer: capturer, player: player,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      await session?.startRecording()
      session?.stopRecording()
      await session?.togglePlayback()
      let queuedDriver = await player.driver(0)
      let driver = try XCTUnwrap(queuedDriver)
      let bytes = try Data(contentsOf: capturer.recordingURL)
      if manualStopFirst {
        await session?.togglePlayback()
        XCTAssertTrue(capturer.cleanupState.fileBlockedOwnerIDs.isEmpty)
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
      }
      session?.viewDidDisappear()
      await settle(try XCTUnwrap(session))
      XCTAssertEqual(capturer.discardCount, 1)
      let owner = try XCTUnwrap(capturer.cleanupState.fileBlockedOwnerIDs.first)
      XCTAssertEqual(files.pendingCleanupOwners, [owner])
      XCTAssertNotNil(gate.currentLease)
      XCTAssertFalse(files.retryCleanup(owner: owner), "Borrow refusal must preserve the file.")
      XCTAssertEqual(try Data(contentsOf: capturer.recordingURL), bytes)
      let repeated = await session?.end()
      XCTAssertEqual(repeated, false)
      XCTAssertEqual(capturer.discardCount, 1)
      weak var lostView = session
      session = nil
      XCTAssertNil(lostView)
      let retry = try XCTUnwrap(player.retryCleanup(id: driver.operation.id))
      let receipt = await retry.value()
      XCTAssertEqual(receipt.result, .released)
      XCTAssertTrue(files.retryCleanup(owner: owner))
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
      XCTAssertNil(gate.currentLease)
    }
  }

  func testBusyPlaybackLeavesTakeAvailableAndReportsTheAnnouncementMessage() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files, gate: gate)
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    let bytes = try Data(contentsOf: capturer.recordingURL)
    let lease = try gate.reserve(operationID: UUID(), owner: .playback)
    defer { if gate.currentLease == lease { gate.release(lease) } }
    await session.togglePlayback()
    XCTAssertEqual(
      session.playbackError,
      "Audio from another screen is still stopping. Try again once it has stopped.")
    XCTAssertEqual(session.phase, .review(capturer.summary, .acceptable))
    XCTAssertFalse(session.isPlaying)
    XCTAssertTrue(player.playedURLs.isEmpty)
    XCTAssertEqual(try Data(contentsOf: capturer.recordingURL), bytes)
    XCTAssertTrue(gate.release(lease))
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testRetryStoppingFileFailureCountsAsFirstCloseAndKeepsRecoveryReachable() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files, gate: gate)
    player.cleanupFailures = 1
    let session = DirectPracticeSession(
      capturer: capturer, player: player,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let first = await session.end()
    XCTAssertFalse(first)
    XCTAssertTrue(session.hasHardwareCleanupIssue)
    let owner = try XCTUnwrap(capturer.cleanupState.fileBlockedOwnerIDs.first)
    capturer.shouldFailDiscard = true
    await session.retryCleanup()
    XCTAssertFalse(session.hasHardwareCleanupIssue)
    XCTAssertEqual(session.playbackState, .idle)
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(
      session.closeNote,
      "The recording couldn't be removed. Use Retry cleanup, or tap Close again to leave it pending."
    )
    let second = await session.end()
    XCTAssertTrue(second)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    capturer.shouldFailDiscard = false
    XCTAssertTrue(files.retryCleanup(owner: owner))
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testExternalCaptureOwnerReleaseRefreshesCloseNoteAndFinishesPendingClose() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    capturer.shouldFailHardwareCleanup = true
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files))
    await session.startRecording()
    session.stopRecording()
    await settle(session)
    let first = await session.end()
    XCTAssertFalse(first)
    XCTAssertEqual(
      session.closeNote,
      "Microphone cleanup is not confirmed, so this screen stays open. Use Retry cleanup.")
    let owner = try XCTUnwrap(capturer.cleanupState.hardwareBlockedOperationID)
    capturer.shouldFailHardwareCleanup = false
    let receipt = capturer.retryCleanup(operationID: owner)
    XCTAssertEqual(receipt.operationID, owner)
    XCTAssertEqual(receipt.result, .released)
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertNil(session.closeNote)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertEqual(capturer.discardCount, 0)
  }

  func testEarlierCaptureSubscriberRecoveryIsConfirmedAfterOriginalDiscardThrows() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
    capturer.removal.failures = 1
    var retriedOwner: UUID?
    // Register before the session: this observer recovers before the session sees failure.
    let firstObserver = capturer.cleanupStatePublisher.sink { state in
      MainActor.assumeIsolated {
        guard retriedOwner == nil, let owner = state.fileBlockedOwnerIDs.first else { return }
        retriedOwner = owner
        XCTAssertTrue(files.retryCleanup(owner: owner))
        XCTAssertEqual(capturer.completedFileCleanup(operationID: owner)?.result, .released)
      }
    }
    defer { firstObserver.cancel() }
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files, gate: gate),
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    let recording = try XCTUnwrap(capturer.returnedRecording)
    let owner = try XCTUnwrap(recording.cleanupOwnerID)
    XCTAssertNil(capturer.completedFileCleanup(operationID: owner))
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(retriedOwner, owner)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertFalse(session.cleanupBlocked)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertEqual(capturer.removal.attempts, 2)
    XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(capturer.completedFileCleanup(operationID: owner)?.operationID, owner)
    XCTAssertNil(capturer.completedFileCleanup(operationID: UUID()))
    XCTAssertEqual(session.completedWords, 0)
  }

  func testMissingCompletedFileReceiptCannotUseIdleOrOwnerDisappearanceAsRemovalProof()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    capturer.shouldFailDiscard = true
    capturer.exposesCompletedFileReceipts = false
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files, gate: gate),
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    let first = await session.end()
    XCTAssertFalse(first)
    let owner = try XCTUnwrap(capturer.cleanupState.fileBlockedOwnerIDs.first)
    capturer.shouldFailDiscard = false
    XCTAssertTrue(files.retryCleanup(owner: owner))
    XCTAssertEqual(capturer.cleanupState, .idle)
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertNil(capturer.completedFileCleanup(operationID: owner))
    let second = await session.end()
    XCTAssertFalse(second)
    XCTAssertTrue(session.cleanupBlocked)
    XCTAssertTrue(session.hasPendingFileCleanup)
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertEqual(session.completedWords, 0)
    capturer.exposesCompletedFileReceipts = true
    await session.retryCleanup()
    let confirmed = await session.end()
    XCTAssertTrue(confirmed)
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testEarlierPlaybackSubscriberRetryKeepsOriginalNegativeAndRequiresFreshContinue()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files, gate: gate)
    player.cleanupFailures = 1
    player.holdRetryCleanup = true
    var externalRetry: PracticePlaybackCleanup?
    let firstObserver = player.statePublisher.sink { state in
      MainActor.assumeIsolated {
        if case .cleanupBlocked(let operation) = state, externalRetry == nil {
          externalRetry = player.retryCleanup(id: operation.id)
        }
      }
    }
    defer { firstObserver.cancel() }
    let session = DirectPracticeSession(
      sound: try oneWordSound(), capturer: capturer, player: player)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let controlledDriver = await player.driver(0)
    let driver = try XCTUnwrap(controlledDriver)
    defer { driver.releaseAll() }
    await session.togglePlayback()
    let original = try XCTUnwrap(player.requestStop(id: driver.operation.id))
    let originalReceipt = await original.value()
    XCTAssertEqual(originalReceipt.result, .cleanupUnconfirmed)
    await entered(driver.retryCleaning)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(capturer.discardCount, 0)
    let retry = try XCTUnwrap(externalRetry)
    driver.releaseRetryCleanup()
    let retryReceipt = await retry.value()
    XCTAssertEqual(retryReceipt.result, .released)
    XCTAssertEqual(player.completedCleanupRetry(id: driver.operation.id), retryReceipt)
    let stillOriginal = await original.value()
    XCTAssertEqual(stillOriginal, originalReceipt)
    XCTAssertNil(player.retryCleanup(id: driver.operation.id))
    XCTAssertNil(player.completedCleanupRetry(id: UUID()))
    XCTAssertFalse(session.cleanupBlocked)
    XCTAssertEqual(session.playbackState, .idle)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(capturer.discardCount, 0)
    XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    await session.continuePractice()
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(session.completedWords, 1)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
  }

  func testExternallyCompletedPlaybackAndFileReceiptsFinishHeldCloseWithoutSecondDiscard()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files, gate: gate)
    player.cleanupFailures = 1
    let session = DirectPracticeSession(
      capturer: capturer, player: player,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let controlledDriver = await player.driver(0)
    let driver = try XCTUnwrap(controlledDriver)
    let first = await session.end()
    XCTAssertFalse(first)
    XCTAssertEqual(capturer.discardCount, 1)
    let owner = try XCTUnwrap(capturer.cleanupState.fileBlockedOwnerIDs.first)
    let original = try XCTUnwrap(player.requestStop(id: driver.operation.id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    let externalRetry = try XCTUnwrap(player.retryCleanup(id: driver.operation.id))
    let released = await externalRetry.value()
    XCTAssertEqual(released.result, .released)
    XCTAssertTrue(files.retryCleanup(owner: owner))
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertEqual(capturer.completedFileCleanup(operationID: owner)?.result, .released)
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    XCTAssertEqual(session.completedWords, 0)
  }

  func testMissingCompletedPlaybackReceiptCannotUseIdleAsReleaseProof() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    let player = DirectPracticePlayer(files: files, gate: gate)
    player.cleanupFailures = 1
    player.exposesCompletedPlaybackReceipts = false
    let session = DirectPracticeSession(
      capturer: capturer, player: player,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    await session.togglePlayback()
    let controlledDriver = await player.driver(0)
    let driver = try XCTUnwrap(controlledDriver)
    await session.togglePlayback()
    let externalRetry = try XCTUnwrap(player.retryCleanup(id: driver.operation.id))
    let receipt = await externalRetry.value()
    XCTAssertEqual(receipt.result, .released)
    XCTAssertEqual(player.state, .idle)
    XCTAssertNil(player.completedCleanupRetry(id: driver.operation.id))
    XCTAssertTrue(session.hasPlaybackCleanupIssue)
    let first = await session.end()
    let second = await session.end()
    XCTAssertFalse(first)
    XCTAssertFalse(second)
    XCTAssertTrue(session.cleanupBlocked)
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertEqual(session.completedWords, 0)
    // A successful producer discard cannot substitute playback release proof.
    XCTAssertEqual(capturer.discardCount, 1)
    player.exposesCompletedPlaybackReceipts = true
    await session.retryCleanup()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testMissingCaptureReceiptRetainsExactHardwareOwnerAfterExternalIdle() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    capturer.shouldFailHardwareCleanup = true
    capturer.exposesCompletedFileReceipts = false
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files))
    await session.startRecording()
    session.stopRecording()
    await settle(session)
    let first = await session.end()
    XCTAssertFalse(first)
    let owner = try XCTUnwrap(capturer.cleanupState.hardwareBlockedOperationID)
    capturer.shouldFailHardwareCleanup = false
    let external = capturer.retryCleanup(operationID: owner)
    XCTAssertEqual(external.result, .released)
    XCTAssertEqual(capturer.cleanupState, .idle)
    XCTAssertNil(capturer.completedFileCleanup(operationID: owner))
    let unconfirmed = await session.end()
    XCTAssertFalse(unconfirmed)
    XCTAssertTrue(session.hasHardwareCleanupIssue)
    XCTAssertTrue(session.hasPendingFileCleanup)
    XCTAssertEqual(
      session.closeNote,
      "Microphone cleanup is not confirmed, so this screen stays open. Use Retry cleanup.")
    capturer.exposesCompletedFileReceipts = true
    await session.retryCleanup()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertFalse(session.hasHardwareCleanupIssue)
    XCTAssertEqual(capturer.discardCount, 0)
  }

  func testEarlierCaptureSubscriberHardwareRetryRemainsProvableWhenStopThrows() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
    capturer.driver.stopFailures = 1
    var recoveredOwner: UUID?
    let firstObserver = capturer.cleanupStatePublisher.sink { state in
      MainActor.assumeIsolated {
        guard recoveredOwner == nil, let owner = state.hardwareBlockedOperationID else { return }
        recoveredOwner = owner
        let receipt = gate.retryCaptureCleanup(operationID: owner)
        XCTAssertEqual(receipt.operationID, owner)
        XCTAssertEqual(receipt.result, .released)
        XCTAssertEqual(capturer.completedFileCleanup(operationID: owner)?.result, .released)
      }
    }
    defer { firstObserver.cancel() }
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files, gate: gate))
    await session.startRecording()
    session.stopRecording()
    await settle(session)
    XCTAssertNotNil(recoveredOwner)
    XCTAssertNil(capturer.returnedRecording)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertFalse(session.hasHardwareCleanupIssue)
    XCTAssertFalse(session.cleanupBlocked)
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(capturer.discardCount, 0)
    XCTAssertEqual(capturer.removal.attempts, 1)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    XCTAssertEqual(session.completedWords, 0)
  }

  func testViewLossDuringHeldExternalRetryRegistersConcreteProducerDiscardBeforeDroppingAllViews()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    var capturer: DirectConcreteCapturer? = DirectConcreteCapturer(
      directory: fixture.directory, files: files, gate: gate)
    weak var producer = capturer?.retainedProducerForTest
    var player: DirectPracticePlayer? = DirectPracticePlayer(files: files, gate: gate)
    player?.cleanupFailures = 1
    player?.holdRetryCleanup = true
    var session: DirectPracticeSession? = DirectPracticeSession(capturer: capturer, player: player)
    weak var lostSession = session
    await session?.startRecording()
    session?.stopRecording()
    let recording = try XCTUnwrap(capturer?.returnedRecording)
    let owner = try XCTUnwrap(recording.cleanupOwnerID)
    let bytes = try Data(contentsOf: recording.url)
    await session?.togglePlayback()
    let controlledDriver = await player?.driver(0)
    let driver = try XCTUnwrap(controlledDriver)
    defer { driver.releaseAll() }
    await session?.togglePlayback()
    let original = try XCTUnwrap(player?.requestStop(id: driver.operation.id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    let externalRetry = try XCTUnwrap(gate.retryPlaybackCleanup())
    await entered(driver.retryCleaning)
    XCTAssertEqual(session?.playbackState, .stopping(driver.operation))
    session?.viewDidDisappear()
    // Handoff is synchronous, before lifecycle cleanup can join/return or release the view.
    XCTAssertEqual(capturer?.discardCount, 1)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    XCTAssertFalse(files.retryCleanup(owner: owner), "Held playback still borrows these bytes.")
    XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
    await settle(try XCTUnwrap(session))
    session = nil
    capturer = nil
    player = nil
    XCTAssertNil(lostSession)
    XCTAssertNotNil(producer, "The real process file callback must retain its producer.")
    driver.releaseRetryCleanup()
    let released = await externalRetry.value()
    XCTAssertEqual(released.result, .released)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(files.retryCleanup(owner: owner))
    XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
  }

  func testConcretePartialCaptureRetryReleasesHardwareAndPreservesFileOnlyCloseRecovery()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    var capturer: DirectConcreteCapturer? = DirectConcreteCapturer(
      directory: fixture.directory, files: files, gate: gate)
    capturer?.driver.stopFailures = 1
    capturer?.removal.failures = 2
    weak var producer = capturer?.retainedProducerForTest
    var session: DirectPracticeSession? = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files, gate: gate),
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session?.startRecording()
    let url = try XCTUnwrap(capturer?.driver.recordingURL)
    session?.stopRecording()
    await settle(try XCTUnwrap(session))
    let first = await session?.end()
    XCTAssertEqual(first, false)
    XCTAssertTrue(session?.hasHardwareCleanupIssue == true)
    let owner = try XCTUnwrap(gate.blockedCaptureOperationID)
    await session?.retryCleanup()
    XCTAssertNil(gate.currentLease)
    XCTAssertNil(gate.blockedCaptureOperationID)
    XCTAssertEqual(session?.captureCleanupState.hardwareBlockedOperationID, nil)
    XCTAssertEqual(session?.captureCleanupState.fileBlockedOwnerIDs, [owner])
    XCTAssertFalse(session?.hasHardwareCleanupIssue == true)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    XCTAssertEqual(
      session?.closeNote,
      "The recording couldn't be removed. Use Retry cleanup, or tap Close again to leave it pending."
    )
    let second = await session?.end()
    XCTAssertEqual(second, true)
    XCTAssertEqual(session?.phase, .ended)
    XCTAssertEqual(session?.completedWords, 0)
    session = nil
    capturer = nil
    XCTAssertNotNil(producer)
    XCTAssertFalse(files.retryCleanup(owner: owner))
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    // The remaining explicit retry succeeds only after the controlled removal failure clears.
    XCTAssertTrue(files.retryCleanup(owner: owner))
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
  }

  func testFailedContinueRequiresRetapAfterExternalRetryBeforeReceiptDecision()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
    let player = DirectPracticePlayer(files: files, gate: gate)
    player.cleanupFailures = 1
    let boundary = DirectReceiptBoundary()
    defer { boundary.release() }
    let historyURL = fixture.directory.appendingPathComponent("participation-\(UUID()).json")
    let history = PracticeParticipationStore(fileURL: historyURL)
    let session = DirectPracticeSession(
      sound: try oneWordSound(), capturer: capturer, player: player, history: history,
      playbackCleanupReceiptObserver: { await boundary.holdNegative($0) })
    await session.startRecording()
    session.stopRecording()
    let recording = try XCTUnwrap(capturer.returnedRecording)
    let originalPhase = session.phase
    let bytes = try Data(contentsOf: recording.url)
    await session.togglePlayback()
    let controlledDriver = await player.driver(0)
    let driver = try XCTUnwrap(controlledDriver)
    // This is the actual Continue path, not a manual Stop proxy.
    let continuing = Task { await session.continuePractice() }
    await entered(boundary.entered)
    let original = try XCTUnwrap(player.requestStop(id: driver.operation.id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertEqual(boundary.observed, negative)
    XCTAssertTrue(session.isTransitioning)
    let externalRetry = try XCTUnwrap(gate.retryPlaybackCleanup())
    let released = await externalRetry.value()
    XCTAssertEqual(released.result, .released)
    XCTAssertEqual(player.completedCleanupRetry(id: driver.operation.id), released)
    XCTAssertNil(gate.currentLease)
    // Real release is complete while the consumer's negative-receipt decision is held.
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: historyURL.path))
    XCTAssertEqual(capturer.discardCount, 0)
    XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
    boundary.release()
    await continuing.value
    XCTAssertEqual(session.phase, originalPhase)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertFalse(session.isTransitioning)
    XCTAssertFalse(session.cleanupBlocked)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: historyURL.path))
    XCTAssertEqual(capturer.discardCount, 0)
    XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
    await session.continuePractice()
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(session.completedWords, 1)
    XCTAssertEqual(history.entries.count, 1)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
  }

  private func entered(_ expectation: XCTestExpectation) async {
    let result = await XCTWaiter.fulfillment(of: [expectation], timeout: 2)
    XCTAssertEqual(result, .completed)
  }

  private func oneWordSound() throws -> PracticeSound {
    let last = try XCTUnwrap(PracticeLibrary.entries(soundID: "b", position: .beginning).last)
    return try XCTUnwrap(
      PracticeLibrary.session(soundID: "b", position: .beginning, startingAt: last.id))
  }

  private func settle(_ session: DirectPracticeSession) async {
    if !session.isTransitioning { return }
    let settled = XCTestExpectation(description: "session cleanup transition settles")
    var fulfilled = false
    let subscription = session.$isTransitioning.sink {
      if !$0 && !fulfilled {
        fulfilled = true
        settled.fulfill()
      }
    }
    defer { subscription.cancel() }
    let result = await XCTWaiter.fulfillment(of: [settled], timeout: 2)
    XCTAssertEqual(result, .completed)
  }

}

@MainActor
private final class DirectPracticeCapturer: AudioCapturing {
  var startupAvailability = CaptureStartupAvailability.available
  var permissionGranted = true
  var holdsPermission = false
  var shouldFailDiscard = false
  var shouldFailStart = false
  var shouldFailStop = false
  var shouldFailHardwareCleanup = false
  var registersFileRecovery = true
  var summary = CaptureSummary(duration: 1, averagePower: -20)
  var power: Float?
  private(set) var powerReads = 0
  var onPowerRead: (() -> Void)?
  func currentRecordingPower() -> Float? {
    powerReads += 1
    let value = power
    onPowerRead?()
    return value
  }
  private(set) var permissionRequestCount = 0
  private(set) var startCount = 0
  private(set) var stopCount = 0
  private(set) var cancelCount = 0
  private(set) var discardCount = 0
  private var permissionContinuation: CheckedContinuation<Bool, Never>?
  private let permissionRequested = XCTestExpectation(description: "permission request held")
  private var requestNoted = false
  private var callbacks: [@MainActor (Bool) async -> Void] = []
  private var isRecording = false
  private var ownsRecording = false
  private var ownerID = UUID()
  var exposesCompletedFileReceipts = true
  private var completedFileReceipts: [UUID: CaptureCleanupReceipt] = [:]
  private let recordingStore: TemporaryRecordingStore?
  private let files: ProcessAudioFileOwnership
  private let cleanupSubject = CurrentValueSubject<CaptureCleanupState, Never>(.idle)
  var cleanupState: CaptureCleanupState { cleanupSubject.value }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    cleanupSubject.eraseToAnyPublisher()
  }
  let recordingURL: URL

  init(
    recordingDirectory: URL? = nil, files: ProcessAudioFileOwnership = ProcessAudioFileOwnership()
  ) {
    self.files = files
    recordingStore = recordingDirectory.map { TemporaryRecordingStore(directory: $0) }
    recordingURL =
      recordingStore?.makeRecordingURL()
      ?? FileManager.default.temporaryDirectory.appendingPathComponent(
        "cadence-attempt-\(UUID()).wav")
  }

  func requestPermission() async -> Bool {
    permissionRequestCount += 1
    if holdsPermission {
      return await withCheckedContinuation {
        permissionContinuation = $0
        if !requestNoted {
          requestNoted = true
          permissionRequested.fulfill()
        }
      }
    }
    return permissionGranted
  }
  func waitForPermissionRequest() async {
    if permissionContinuation != nil { return }
    let result = await XCTWaiter.fulfillment(of: [permissionRequested], timeout: 2)
    XCTAssertEqual(result, .completed)
    XCTAssertNotNil(permissionContinuation)
  }
  func resolvePermission(_ granted: Bool) {
    permissionContinuation?.resume(returning: granted)
    permissionContinuation = nil
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    startCount += 1
    if shouldFailStart { throw AudioCaptureError.couldNotStart }
    guard cleanupState == .idle else { throw AudioCaptureError.hardwareCleanupUnconfirmed }
    ownerID = UUID()
    files.retain(recordingURL, owner: ownerID)
    isRecording = true
    ownsRecording = true
    callbacks.append(onFinish)
    if recordingStore != nil { try Data("temporary audio".utf8).write(to: recordingURL) }
  }
  func stop() throws -> CapturedRecording {
    stopCount += 1
    if shouldFailHardwareCleanup {
      cleanupSubject.send(.init(hardwareBlockedOperationID: ownerID, fileBlockedOwnerIDs: []))
      throw AudioCaptureError.hardwareCleanupUnconfirmed
    }
    if shouldFailStop { throw AudioCaptureError.couldNotReadRecording }
    isRecording = false
    return CapturedRecording(url: recordingURL, summary: summary, cleanupOwnerID: ownerID)
  }
  func cancel() throws {
    cancelCount += 1
    guard isRecording else { return }
    if shouldFailHardwareCleanup || cleanupState.hasHardwareIssue {
      cleanupSubject.send(.init(hardwareBlockedOperationID: ownerID, fileBlockedOwnerIDs: []))
      throw AudioCaptureError.hardwareCleanupUnconfirmed
    }
    try removeRecording()
    isRecording = false
  }
  func discard(_ recording: CapturedRecording) throws {
    discardCount += 1
    XCTAssertEqual(recording.url, recordingURL)
    if shouldFailDiscard || cleanupState.fileBlockedOwnerIDs.contains(ownerID) {
      markFilePending()
      throw AudioCaptureError.couldNotDeleteTemporaryRecording
    }
    try removeRecording()
  }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    guard operationID == ownerID,
      cleanupState.hasHardwareIssue || cleanupState.fileBlockedOwnerIDs.contains(operationID)
    else { return .init(operationID: operationID, result: .refused) }
    if shouldFailHardwareCleanup {
      return .init(operationID: operationID, result: .cleanupUnconfirmed)
    }
    if shouldFailDiscard {
      markFilePending()
      return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
    }
    do {
      try removeRecording()
      isRecording = false
      cleanupSubject.send(.idle)
      return .init(operationID: operationID, result: .released)
    } catch {
      return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
    }
  }
  private func removeRecording() throws {
    guard ownsRecording else { throw AudioCaptureError.recordingNotOwned }
    guard files.canRemove(recordingURL, owner: ownerID) else {
      markFilePending()
      throw AudioCaptureError.recordingInUse
    }
    try recordingStore?.removeRecordingIfPresent(at: recordingURL)
    files.didRemove(recordingURL, owner: ownerID)
    ownsRecording = false
    completedFileReceipts[ownerID] = .init(operationID: ownerID, result: .released)
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
    exposesCompletedFileReceipts ? completedFileReceipts[operationID] : nil
  }
  private func markFilePending() {
    let id = ownerID
    if registersFileRecovery {
      files.registerCleanupRecovery(owner: id) { [self] in
        retryCleanup(operationID: id).allRequestedFilesRemoved
      }
    }
    cleanupSubject.send(.init(hardwareBlockedOperationID: nil, fileBlockedOwnerIDs: [ownerID]))
  }
  func finish(index: Int, successfully: Bool = true) async {
    await callbacks[index](successfully)
  }
}

/// A test-controlled driver enters the actual production facade/runtime and intrinsic borrow.
@MainActor
private final class DirectPracticePlayer: AcknowledgedPracticeAudioPlaying {
  private let store: DirectDriverStore
  private let facade: SystemAcknowledgedPracticeAudioPlayer
  private var consumerCallbacks:
    [(PracticePlaybackOperation, @MainActor (PracticePlaybackOperation, Bool) -> Void)] = []
  var shouldFail: Bool {
    get { store.config.prepareFails }
    set { store.update { $0.prepareFails = newValue } }
  }
  var holdPreparation: Bool {
    get { store.config.holdPreparation }
    set { store.update { $0.holdPreparation = newValue } }
  }
  var holdCleanup: Bool {
    get { store.config.holdCleanup }
    set { store.update { $0.holdCleanup = newValue } }
  }
  var holdRetryCleanup: Bool {
    get { store.config.holdRetryCleanup }
    set { store.update { $0.holdRetryCleanup = newValue } }
  }
  var cleanupFailures: Int {
    get { store.config.cleanupFailures }
    set { store.update { $0.cleanupFailures = newValue } }
  }
  var playedURLs: [URL] { store.drivers.map { $0.operation.url } }
  var stopCount: Int { store.drivers.reduce(0) { $0 + $1.stopCount } }
  var exposesCompletedPlaybackReceipts = true
  var state: PracticePlaybackRuntimeState { facade.state }
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> { facade.statePublisher }

  init(
    files: ProcessAudioFileOwnership = ProcessAudioFileOwnership(),
    gate: AudioHardwareOwnership = AudioHardwareOwnership()
  ) {
    let store = DirectDriverStore()
    self.store = store
    facade = SystemAcknowledgedPracticeAudioPlayer(ownership: gate, fileOwnership: files) {
      operation, finished in store.make(operation: operation, finished: finished)
    }
  }
  func play(
    id: UUID, url: URL, onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws {
    consumerCallbacks.append((.init(id: id, url: url), onFinish))
    try await facade.play(id: id, url: url, onFinish: onFinish)
  }
  func requestStop(id: UUID) -> PracticePlaybackCleanup? { facade.requestStop(id: id) }
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { facade.retryCleanup(id: id) }
  func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
    exposesCompletedPlaybackReceipts ? facade.completedCleanupRetry(id: id) : nil
  }
  func deliverCapturedCompletion(index: Int, successfully: Bool = true) {
    let (operation, callback) = consumerCallbacks[index]
    callback(operation, successfully)
  }
  func finish(index: Int, successfully: Bool = true) { store.drivers[index].finish(successfully) }
  func driver(_ index: Int) async -> DirectControlledDriver? {
    if !store.drivers.indices.contains(index) {
      let result = await XCTWaiter.fulfillment(of: [store.created], timeout: 2)
      XCTAssertEqual(result, .completed)
    }
    let drivers = store.drivers
    guard drivers.indices.contains(index) else {
      XCTFail("Expected queued driver construction.")
      return nil
    }
    return drivers[index]
  }

  func waitForIdle() async {
    if state == .idle { return }
    let idle = XCTestExpectation(description: "playback releases to idle")
    var fulfilled = false
    let subscription = statePublisher.sink {
      if $0 == .idle && !fulfilled {
        fulfilled = true
        idle.fulfill()
      }
    }
    defer { subscription.cancel() }
    let result = await XCTWaiter.fulfillment(of: [idle], timeout: 2)
    XCTAssertEqual(result, .completed)
  }
}

private final class DirectDriverStore: @unchecked Sendable {
  struct Config {
    var prepareFails = false
    var holdPreparation = false
    var holdCleanup = false
    var holdRetryCleanup = false
    var cleanupFailures = 0
  }
  let created = XCTestExpectation(description: "queued driver constructed")
  private let lock = NSLock()
  private var settings = Config()
  private var ownedDrivers: [DirectControlledDriver] = []
  var config: Config { lock.withLock { settings } }
  var drivers: [DirectControlledDriver] { lock.withLock { ownedDrivers } }
  func update(_ body: (inout Config) -> Void) { lock.withLock { body(&settings) } }
  func make(
    operation: PracticePlaybackOperation,
    finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) -> DirectControlledDriver {
    let driver = DirectControlledDriver(operation: operation, config: config, finished: finished)
    let first = lock.withLock {
      ownedDrivers.append(driver)
      return ownedDrivers.count == 1
    }
    if first { created.fulfill() }
    return driver
  }
}

private final class DirectControlledDriver: PracticePlaybackDriver, @unchecked Sendable {
  enum Failure: Error { case testGateDeadline, cleanup }
  let operation: PracticePlaybackOperation
  let prepared = XCTestExpectation(description: "entered preparation")
  let cleaning = XCTestExpectation(description: "entered cleanup")
  let retryCleaning = XCTestExpectation(description: "entered explicit cleanup retry")
  private let config: DirectDriverStore.Config
  private let finished: @Sendable (PracticePlaybackOperation, Bool) -> Void
  private let prepareGate = DispatchSemaphore(value: 0)
  private let cleanupGate = DispatchSemaphore(value: 0)
  private let retryCleanupGate = DispatchSemaphore(value: 0)
  private let lock = NSLock()
  private var stops = 0
  private var cleanupAttempts = 0
  var stopCount: Int { lock.withLock { stops } }

  init(
    operation: PracticePlaybackOperation, config: DirectDriverStore.Config,
    finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) {
    self.operation = operation
    self.config = config
    self.finished = finished
  }
  func activate() throws {}
  func prepare() throws -> Bool {
    prepared.fulfill()
    if config.holdPreparation, prepareGate.wait(timeout: .now() + 8) != .success {
      throw Failure.testGateDeadline
    }
    return !config.prepareFails
  }
  func play() throws -> Bool { true }
  func stop() throws { lock.withLock { stops += 1 } }
  func releasePlaybackResources() throws {}
  func deactivate() throws {
    let attempt = lock.withLock {
      cleanupAttempts += 1
      return cleanupAttempts
    }
    if attempt == 1 {
      cleaning.fulfill()
      if config.holdCleanup, cleanupGate.wait(timeout: .now() + 8) != .success {
        throw Failure.testGateDeadline
      }
    }
    if attempt == 2 {
      retryCleaning.fulfill()
      if config.holdRetryCleanup, retryCleanupGate.wait(timeout: .now() + 8) != .success {
        throw Failure.testGateDeadline
      }
    }
    if attempt <= config.cleanupFailures { throw Failure.cleanup }
  }
  func releasePreparation() { prepareGate.signal() }
  func releaseCleanup() { cleanupGate.signal() }
  func releaseRetryCleanup() { retryCleanupGate.signal() }
  func releaseAll() {
    releasePreparation()
    releaseCleanup()
    releaseRetryCleanup()
  }
  func finish(_ success: Bool) { finished(operation, success) }
}

/// Holds only consumer receipt interpretation. The real original receipt and actual
/// runtime/driver continue unchanged; release is an explicit deterministic test signal.
@MainActor
private final class DirectReceiptBoundary {
  let entered = XCTestExpectation(description: "actual negative receipt handling held")
  private(set) var observed: PracticePlaybackCleanupReceipt?
  private var continuation: CheckedContinuation<Void, Never>?
  func holdNegative(_ receipt: PracticePlaybackCleanupReceipt) async {
    guard receipt.result == .cleanupUnconfirmed, observed == nil else { return }
    observed = receipt
    await withCheckedContinuation {
      continuation = $0
      entered.fulfill()
    }
  }
  func release() {
    continuation?.resume()
    continuation = nil
  }
}

/// Concrete capture cleanup and serialized publication with an inert controlled driver.
/// Only this test-owned directory is written; no permission or AVFoundation call is made.
@MainActor
private final class DirectConcreteCapturer: AudioCapturing {
  final class Removal {
    enum Failure: Error { case controlled }
    var failures = 0
    private(set) var attempts = 0
    func remove(_ url: URL) throws {
      attempts += 1
      if failures > 0 {
        failures -= 1
        throw Failure.controlled
      }
      if FileManager.default.fileExists(atPath: url.path) {
        try FileManager.default.removeItem(at: url)
      }
    }
  }
  let removal: Removal
  let driver: DirectInertCaptureDriver
  private let concrete: SystemAudioCapturer
  var retainedProducerForTest: SystemAudioCapturer { concrete }
  private(set) var returnedRecording: CapturedRecording?
  private(set) var discardCount = 0
  var cleanupState: CaptureCleanupState { concrete.cleanupState }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    concrete.cleanupStatePublisher
  }
  init(directory: URL, files: ProcessAudioFileOwnership, gate: AudioHardwareOwnership) {
    let removal = Removal()
    let driver = DirectInertCaptureDriver()
    self.removal = removal
    self.driver = driver
    concrete = SystemAudioCapturer(
      recordingStore: TemporaryRecordingStore(directory: directory),
      fileOwnership: files, hardwareOwnership: gate,
      driverFactory: { driver },
      summaryReader: { _ in CaptureSummary(duration: 1, averagePower: -20) },
      removeFile: { try removal.remove($0) })
  }
  func requestPermission() async -> Bool { true }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    try concrete.start(onFinish: onFinish)
  }
  func stop() throws -> CapturedRecording {
    let recording = try concrete.stop()
    returnedRecording = recording
    return recording
  }
  func cancel() throws { try concrete.cancel() }
  func discard(_ recording: CapturedRecording) throws {
    discardCount += 1
    try concrete.discard(recording)
  }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    concrete.retryCleanup(operationID: operationID)
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
    concrete.completedFileCleanup(operationID: operationID)
  }
}

@MainActor
private final class DirectInertCaptureDriver: CaptureHardwareDriver {
  enum Failure: Error { case controlled }
  var stopFailures = 0
  private(set) var recordingURL: URL?
  func configureActivate() throws {}
  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    recordingURL = url
    try Data("controlled capture bytes".utf8).write(to: url)
  }
  func prepare() throws -> Bool { true }
  func record() throws -> Bool { true }
  func stop() throws {
    if stopFailures > 0 {
      stopFailures -= 1
      throw Failure.controlled
    }
  }
  func detachRelease() throws {}
  func deactivate() throws {}
}

@MainActor
private struct DirectOwnedFixture {
  let directory: URL
  init() throws {
    directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
  }
  func removeDirectory() { try? FileManager.default.removeItem(at: directory) }
}

// APPEND this whole draft to DirectPracticeSessionTests.swift; do not register it as a separate
// source file. Its extension intentionally reuses the existing file-private inert helpers.
// All methods below are unexecuted draft assertions. No sensor or output driver is constructed.
#if DEBUG
  @MainActor
  extension DirectPracticeSessionTests {
    func testMirrorAndAudioCloseWaitForBothExactOwnersInEitherCompletionOrder() async throws {
      for cameraFirst in [false, true] {
        let fixture = try DirectOwnedFixture()
        defer { fixture.removeDirectory() }
        let files = ProcessAudioFileOwnership()
        let audioGate = AudioHardwareOwnership()
        let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
        let player = DirectPracticePlayer(files: files, gate: audioGate)
        player.holdCleanup = true
        let camera = SessionMirrorFixture(holdsCleanup: true)
        defer { camera.driver.releaseAll() }
        let history = PracticeParticipationStore(
          fileURL: fixture.directory.appendingPathComponent("generated-history.json"))
        let session = DirectPracticeSession(
          capturer: capturer, player: player, mirror: camera.mirror,
          history: history, cleanupHardwareOwnership: audioGate, cleanupFileOwnership: files)
        session.appDidBecomeActive()
        await session.startRecording()
        session.stopRecording()
        session.showMirror()
        await mirrorWait {
          if case .live = camera.mirror.state { return true }
          return false
        }
        let cameraOwner = try XCTUnwrap(camera.runtime.currentOwner)
        let cameraOriginal = try XCTUnwrap(
          camera.runtime.cleanupAcknowledgement(owner: cameraOwner))
        await session.togglePlayback()
        let queued = await player.driver(0)
        let audioDriver = try XCTUnwrap(queued)
        defer { audioDriver.releaseAll() }
        let closing = Task { @MainActor in await session.end() }
        await entered(camera.driver.cleaning)
        await entered(audioDriver.cleaning)
        XCTAssertNotEqual(session.phase, .ended)
        XCTAssertEqual(capturer.discardCount, 0)
        XCTAssertTrue(session.actionsDisabled)
        XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
        if cameraFirst {
          camera.driver.releaseCleanup()
          let receipt = await cameraOriginal.value()
          XCTAssertEqual(receipt.result, .released)
          XCTAssertNil(camera.recovery.owner)
          XCTAssertNotNil(audioGate.currentLease)
          XCTAssertEqual(capturer.discardCount, 0)
          XCTAssertNotEqual(session.phase, .ended)
          audioDriver.releaseCleanup()
        } else {
          audioDriver.releaseCleanup()
          await mirrorWait { capturer.discardCount == 1 }
          XCTAssertNil(audioGate.currentLease)
          XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
          XCTAssertNotNil(camera.recovery.owner)
          XCTAssertNil(cameraOriginal.receipt)
          XCTAssertNotEqual(session.phase, .ended)
          camera.driver.releaseCleanup()
        }
        let ended = await closing.value
        XCTAssertTrue(ended)
        XCTAssertEqual(session.phase, .ended)
        XCTAssertEqual(capturer.discardCount, 1)
        XCTAssertEqual(audioDriver.stopCount, 1)
        XCTAssertEqual(camera.driver.cleanupCount, 1)
        XCTAssertEqual(session.completedWords, 0)
        XCTAssertTrue(history.entries.isEmpty)
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
        XCTAssertNil(camera.recovery.owner)
        XCTAssertNil(audioGate.currentLease)
      }
    }

    func testCameraFailedCloseDeletesAudioAndNeedsExplicitCameraRetryWithStickyEnd() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files)
      let camera = SessionMirrorFixture(cleanupFailures: 1)
      let session = DirectPracticeSession(capturer: capturer, player: player, mirror: camera.mirror)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let owner = try XCTUnwrap(camera.runtime.currentOwner)
      let original = try XCTUnwrap(camera.runtime.cleanupAcknowledgement(owner: owner))
      let ended = await session.end()
      XCTAssertFalse(ended)
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertFalse(session.cleanupBlocked)
      XCTAssertFalse(session.hasHardwareCleanupIssue)
      XCTAssertTrue(session.actionsDisabled)  // End remains sticky independently of audio flags.
      XCTAssertTrue(session.interactiveDismissDisabled)
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      let duplicate = await session.end()
      XCTAssertFalse(duplicate)
      XCTAssertEqual(camera.driver.cleanupCount, 1)
      await session.startRecording()
      XCTAssertEqual(capturer.startCount, 1)
      await session.retryMirrorStop()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(original.receipt, negative)
      XCTAssertEqual(camera.mirror.exactReleasedReceipt?.owner, owner)
      XCTAssertEqual(camera.mirror.exactReleasedReceipt?.result, .released)
      XCTAssertEqual(camera.driver.cleanupCount, 2)
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertEqual(session.completedWords, 0)
    }

    func testAudioFailedCloseReleasesCameraAndDirectAudioRetryCommitsExactEnd() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files, gate: gate)
      player.cleanupFailures = 1
      let camera = SessionMirrorFixture()
      let session = DirectPracticeSession(
        capturer: capturer, player: player, mirror: camera.mirror,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      await session.togglePlayback()
      let queued = await player.driver(0)
      let audioDriver = try XCTUnwrap(queued)
      defer { audioDriver.releaseAll() }
      let ended = await session.end()
      XCTAssertFalse(ended)
      let original = try XCTUnwrap(player.requestStop(id: audioDriver.operation.id))
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertTrue(session.hasPlaybackCleanupIssue)
      XCTAssertTrue(session.canRetryCleanup)
      XCTAssertTrue(camera.mirror.isReleasedForClose)
      XCTAssertNil(camera.recovery.owner)
      XCTAssertEqual(camera.driver.cleanupCount, 1)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      await session.retryCleanup()  // Actual session audio retry direct-commit path.
      XCTAssertEqual(session.phase, .ended)
      XCTAssertFalse(session.cleanupBlocked)
      XCTAssertNil(gate.currentLease)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      XCTAssertEqual(original.receipt, negative)
      XCTAssertEqual(camera.driver.cleanupCount, 1)
      XCTAssertEqual(session.completedWords, 0)
    }

    func testBothCloseFailuresRecoverInEitherExplicitRetryOrderWithoutImplicitRetry() async throws {
      for cameraRetryFirst in [false, true] {
        let fixture = try DirectOwnedFixture()
        defer { fixture.removeDirectory() }
        let files = ProcessAudioFileOwnership()
        let gate = AudioHardwareOwnership()
        let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
        let player = DirectPracticePlayer(files: files, gate: gate)
        player.cleanupFailures = 1
        let camera = SessionMirrorFixture(cleanupFailures: 1)
        let session = DirectPracticeSession(
          capturer: capturer, player: player, mirror: camera.mirror,
          cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
        session.appDidBecomeActive()
        await session.startRecording()
        session.stopRecording()
        session.showMirror()
        await mirrorWait {
          if case .live = camera.mirror.state { return true }
          return false
        }
        let cameraOwner = try XCTUnwrap(camera.runtime.currentOwner)
        let cameraOriginal = try XCTUnwrap(
          camera.runtime.cleanupAcknowledgement(owner: cameraOwner))
        await session.togglePlayback()
        let queued = await player.driver(0)
        let audioDriver = try XCTUnwrap(queued)
        defer { audioDriver.releaseAll() }
        let ended = await session.end()
        XCTAssertFalse(ended)
        let audioOriginal = try XCTUnwrap(player.requestStop(id: audioDriver.operation.id))
        let audioNegative = await audioOriginal.value()
        let cameraNegative = await cameraOriginal.value()
        XCTAssertEqual(audioNegative.result, .cleanupUnconfirmed)
        XCTAssertEqual(cameraNegative.result, .cleanupUnconfirmed)
        let duplicate = await session.end()
        XCTAssertFalse(duplicate)
        XCTAssertEqual(camera.driver.cleanupCount, 1)
        if cameraRetryFirst {
          await session.retryMirrorStop()
          XCTAssertTrue(camera.mirror.isReleasedForClose)
          XCTAssertTrue(session.cleanupBlocked)
          XCTAssertNotEqual(session.phase, .ended)
          await session.retryCleanup()
        } else {
          await session.retryCleanup()
          XCTAssertFalse(session.cleanupBlocked)
          XCTAssertFalse(camera.mirror.isReleasedForClose)
          XCTAssertTrue(session.actionsDisabled)
          XCTAssertNotEqual(session.phase, .ended)
          await session.retryMirrorStop()
        }
        XCTAssertEqual(session.phase, .ended)
        XCTAssertEqual(audioOriginal.receipt, audioNegative)
        XCTAssertEqual(cameraOriginal.receipt, cameraNegative)
        XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
        XCTAssertNil(gate.currentLease)
        XCTAssertNil(camera.recovery.owner)
      }
    }

    func testCameraRetryCannotCommitCloseWhileAudioCleanupIsStillHeld() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files, gate: gate)
      player.holdCleanup = true
      let camera = SessionMirrorFixture(cleanupFailures: 1)
      let session = DirectPracticeSession(
        capturer: capturer, player: player, mirror: camera.mirror,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let owner = try XCTUnwrap(camera.runtime.currentOwner)
      let cameraOriginal = try XCTUnwrap(camera.runtime.cleanupAcknowledgement(owner: owner))
      await session.togglePlayback()
      let queued = await player.driver(0)
      let audioDriver = try XCTUnwrap(queued)
      defer { audioDriver.releaseAll() }
      let closing = Task { @MainActor in await session.end() }
      await entered(audioDriver.cleaning)
      let negative = await cameraOriginal.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertFalse(session.cleanupBlocked)  // Not audio completion evidence.
      await session.retryMirrorStop()
      XCTAssertTrue(camera.mirror.isReleasedForClose)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertNotNil(gate.currentLease)
      XCTAssertEqual(capturer.discardCount, 0)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      audioDriver.releaseCleanup()
      let ended = await closing.value
      XCTAssertTrue(ended)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(cameraOriginal.receipt, negative)
      XCTAssertEqual(capturer.discardCount, 1)
    }

    func testDirectAudioRetryCannotBypassHeldCameraAndCameraReleaseFinishesStickyClose()
      async throws
    {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files, gate: gate)
      player.cleanupFailures = 1
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer { camera.driver.releaseAll() }
      let session = DirectPracticeSession(
        capturer: capturer, player: player, mirror: camera.mirror,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let owner = try XCTUnwrap(camera.runtime.currentOwner)
      let cameraOriginal = try XCTUnwrap(camera.runtime.cleanupAcknowledgement(owner: owner))
      await session.togglePlayback()
      let queued = await player.driver(0)
      let audioDriver = try XCTUnwrap(queued)
      defer { audioDriver.releaseAll() }
      let closing = Task { @MainActor in await session.end() }
      await entered(camera.driver.cleaning)
      await mirrorWait { session.canRetryCleanup }
      let audioOriginal = try XCTUnwrap(player.requestStop(id: audioDriver.operation.id))
      let negative = await audioOriginal.value()
      await session.retryCleanup()
      XCTAssertFalse(session.cleanupBlocked)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      XCTAssertTrue(session.actionsDisabled)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertNil(cameraOriginal.receipt)
      camera.driver.releaseCleanup()
      let ended = await closing.value
      XCTAssertTrue(ended)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(audioOriginal.receipt, negative)
    }

    func testCameraRetryDoesNotInventSecondCloseForExactRetainedFileOnlyRecovery() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
      capturer.removal.failures = 10
      let player = DirectPracticePlayer(files: files, gate: gate)
      let camera = SessionMirrorFixture(cleanupFailures: 1)
      let session = DirectPracticeSession(
        capturer: capturer, player: player, mirror: camera.mirror,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      let recording = try XCTUnwrap(capturer.returnedRecording)
      let bytes = try Data(contentsOf: recording.url)
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let first = await session.end()
      XCTAssertFalse(first)
      let owner = try XCTUnwrap(recording.cleanupOwnerID)
      XCTAssertEqual(files.pendingCleanupOwners, [owner])
      XCTAssertNil(gate.currentLease)
      XCTAssertTrue(session.captureCleanupState.hasFileIssue)
      await session.retryMirrorStop()
      XCTAssertTrue(camera.mirror.isReleasedForClose)
      XCTAssertNotEqual(session.phase, .ended)  // Camera retry is not an explicit second Close.
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
      let second = await session.end()
      XCTAssertTrue(second)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(files.pendingCleanupOwners, [owner])
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
      capturer.removal.failures = 0
      XCTAssertTrue(files.retryCleanup(owner: owner))
      XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    }

    func testAuthorizedSecondFileCloseRechecksCurrentHardwareProofAfterCameraRetry() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
      capturer.removal.failures = 10
      let player = DirectPracticePlayer(files: files, gate: gate)
      let camera = SessionMirrorFixture(cleanupFailures: 1)
      let session = DirectPracticeSession(
        capturer: capturer, player: player, mirror: camera.mirror,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      let recording = try XCTUnwrap(capturer.returnedRecording)
      let bytes = try Data(contentsOf: recording.url)
      let fileOwner = try XCTUnwrap(recording.cleanupOwnerID)
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let first = await session.end()
      XCTAssertFalse(first)
      let second = await session.end()  // Latches authorized file exit, still blocked by camera.
      XCTAssertFalse(second)
      let laterLease = try gate.reserve(operationID: UUID(), owner: .capture)
      defer { if gate.currentLease == laterLease { _ = gate.release(laterLease) } }
      await session.retryMirrorStop()
      XCTAssertTrue(camera.mirror.isReleasedForClose)
      XCTAssertNotEqual(session.phase, .ended)  // Current lease invalidates the earlier file proof.
      XCTAssertEqual(files.pendingCleanupOwners, [fileOwner])
      XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertTrue(gate.release(laterLease))
      let finalClose = await session.end()
      XCTAssertTrue(finalClose)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(files.pendingCleanupOwners, [fileOwner])
      XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
      capturer.removal.failures = 0
      XCTAssertTrue(files.retryCleanup(owner: fileOwner))
      XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    }

    func testSecondFileCloseWhileCameraPendingJoinsExactStopAndPreservesProducerRecovery()
      async throws
    {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let gate = AudioHardwareOwnership()
      let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
      capturer.removal.failures = 10
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer { camera.driver.releaseAll() }
      let session = DirectPracticeSession(
        capturer: capturer,
        player: DirectPracticePlayer(files: files, gate: gate), mirror: camera.mirror,
        cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      let recording = try XCTUnwrap(capturer.returnedRecording)
      let fileOwner = try XCTUnwrap(recording.cleanupOwnerID)
      let bytes = try Data(contentsOf: recording.url)
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let firstClose = Task { @MainActor in await session.end() }
      await entered(camera.driver.cleaning)
      await mirrorWait { session.closeNote?.contains("tap Close again") == true }
      XCTAssertEqual(files.pendingCleanupOwners, [fileOwner])
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertNil(gate.currentLease)
      let secondEntered = XCTestExpectation(description: "explicit second Close joins held camera")
      let secondClose = Task { @MainActor in
        secondEntered.fulfill()
        return await session.end()
      }
      await entered(secondEntered)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
      camera.driver.releaseCleanup()
      let firstEnded = await firstClose.value
      let secondEnded = await secondClose.value
      XCTAssertTrue(firstEnded)
      XCTAssertTrue(secondEnded)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(camera.driver.cleanupCount, 1)
      XCTAssertEqual(capturer.discardCount, 1)
      XCTAssertEqual(files.pendingCleanupOwners, [fileOwner])
      XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
      XCTAssertEqual(session.completedWords, 0)
      capturer.removal.failures = 0
      XCTAssertTrue(files.retryCleanup(owner: fileOwner))
      XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    }

    func testSessionPendingCameraPermissionGatesRecordAndPreservesReadyAcrossBothSceneOrders()
      async throws
    {
      for grantFirst in [false, true] {
        let fixture = try DirectOwnedFixture()
        defer { fixture.removeDirectory() }
        let files = ProcessAudioFileOwnership()
        let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
        let camera = SessionMirrorFixture(permission: .notDetermined)
        let session = DirectPracticeSession(
          capturer: capturer, player: DirectPracticePlayer(files: files),
          mirror: camera.mirror)
        session.appDidBecomeActive()
        session.showMirror()
        XCTAssertEqual(camera.permission.requests, 1)
        XCTAssertEqual(session.phase, .ready)
        XCTAssertFalse(session.canStartRecording)
        await session.startRecording()
        XCTAssertEqual(capturer.permissionRequestCount, 0)
        XCTAssertEqual(capturer.startCount, 0)
        XCTAssertEqual(session.phase, .ready)
        session.appDidBecomeInactive()
        XCTAssertEqual(capturer.cancelCount, 0)
        XCTAssertFalse(session.isTransitioning)
        if grantFirst {
          camera.permission.complete(true)
          guard case .awaitingActive = camera.mirror.state else {
            XCTFail("Session grant before active must retain pending attempt")
            continue
          }
          XCTAssertEqual(camera.driver.startCount, 0)
          session.appDidBecomeActive()
        } else {
          session.appDidBecomeActive()
          XCTAssertEqual(camera.driver.startCount, 0)
          camera.permission.complete(true)
        }
        await mirrorWait {
          if case .live = camera.mirror.state { return true }
          return false
        }
        XCTAssertFalse(camera.mirror.blocksRecordForCameraPermission)
        XCTAssertTrue(session.canStartRecording)
        XCTAssertEqual(capturer.permissionRequestCount, 0)
        let ended = await session.end()
        XCTAssertTrue(ended)
      }
    }

    func testFirstMicrophonePermissionStopsCameraAndAllowsExplicitAuthorizedShowDuringRecording()
      async throws
    {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      capturer.holdsPermission = true
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer {
        capturer.resolvePermission(false)
        camera.driver.releaseAll()
      }
      let session = DirectPracticeSession(
        capturer: capturer, player: DirectPracticePlayer(files: files),
        mirror: camera.mirror)
      session.appDidBecomeActive()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let owner = try XCTUnwrap(camera.runtime.currentOwner)
      let original = try XCTUnwrap(camera.runtime.cleanupAcknowledgement(owner: owner))
      let recording = Task { @MainActor in await session.startRecording() }
      await capturer.waitForPermissionRequest()
      await entered(camera.driver.cleaning)
      XCTAssertEqual(session.phase, .requestingPermission)
      XCTAssertEqual(camera.mirror.state, .stopping(owner))
      XCTAssertFalse(session.cleanupBlocked)
      session.appDidBecomeInactive()
      XCTAssertEqual(capturer.cancelCount, 0)
      camera.driver.releaseCleanup()
      let release = await original.value()
      XCTAssertEqual(release.result, .released)
      capturer.resolvePermission(true)
      await recording.value
      XCTAssertEqual(session.phase, .recording)
      session.appDidBecomeActive()
      XCTAssertEqual(camera.driver.factoryCount, 1)  // No automatic camera restart.
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      XCTAssertEqual(camera.driver.factoryCount, 2)
      XCTAssertEqual(camera.permission.requests, 0)
      session.stopRecording()
      guard case .review = session.phase else {
        return XCTFail("Held generated take must survive camera Show")
      }
      XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      let ended = await session.end()
      XCTAssertTrue(ended)
    }

    func testLateMicrophoneGrantAfterCloseCannotStartCaptureOrReviveCamera() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      capturer.holdsPermission = true
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer {
        capturer.resolvePermission(false)
        camera.driver.releaseAll()
      }
      let session = DirectPracticeSession(
        capturer: capturer, player: DirectPracticePlayer(files: files),
        mirror: camera.mirror)
      session.appDidBecomeActive()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let recording = Task { @MainActor in await session.startRecording() }
      await capturer.waitForPermissionRequest()
      await entered(camera.driver.cleaning)
      let closing = Task { @MainActor in await session.end() }
      await mirrorWait { session.closeNote != nil }
      XCTAssertNotEqual(session.phase, .ended)
      camera.driver.releaseCleanup()
      let ended = await closing.value
      XCTAssertTrue(ended)
      capturer.resolvePermission(true)
      await recording.value
      session.appDidBecomeActive()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(capturer.startCount, 0)
      XCTAssertEqual(camera.driver.factoryCount, 1)
      XCTAssertEqual(camera.driver.startCount, 1)
      XCTAssertNil(camera.recovery.owner)
    }

    func testBackgroundAndCloseRevokePendingCameraGrantAndUnknownReviewNeverPrompts() async throws {
      for close in [false, true] {
        let fixture = try DirectOwnedFixture()
        defer { fixture.removeDirectory() }
        let files = ProcessAudioFileOwnership()
        let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
        let camera = SessionMirrorFixture(permission: .notDetermined)
        let session = DirectPracticeSession(
          capturer: capturer, player: DirectPracticePlayer(files: files),
          mirror: camera.mirror)
        session.appDidBecomeActive()
        // Microphone first: a held review take may not trigger unknown camera permission.
        await session.startRecording()
        session.stopRecording()
        let takePhase = session.phase
        session.showMirror()
        XCTAssertEqual(camera.permission.requests, 0)
        XCTAssertEqual(session.phase, takePhase)
        XCTAssertTrue(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
        await session.retry()
        session.showMirror()
        XCTAssertEqual(camera.permission.requests, 1)
        if close {
          let ended = await session.end()  // Settles before OS camera callback exists.
          XCTAssertTrue(ended)
        } else {
          session.appDidEnterBackground()
          await settle(session)
          XCTAssertEqual(session.phase, .ready)
        }
        camera.permission.complete(true)
        session.appDidBecomeActive()
        XCTAssertEqual(camera.driver.factoryCount, 0)
        XCTAssertEqual(camera.mirror.state, .off)
        XCTAssertFalse(camera.mirror.blocksRecordForCameraPermission)
        XCTAssertEqual(capturer.permissionRequestCount, 1)
        if !close {
          let ended = await session.end()
          XCTAssertTrue(ended)
        }
      }
    }

    func testOrdinaryCameraStopFailurePreservesHeldTakeReplayAndNextAudioBehavior() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let player = DirectPracticePlayer(files: files)
      let camera = SessionMirrorFixture(cleanupFailures: 1)
      let session = DirectPracticeSession(capturer: capturer, player: player, mirror: camera.mirror)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      let takePhase = session.phase
      let bytes = try Data(contentsOf: capturer.recordingURL)
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      session.hideMirror()
      await mirrorWait {
        if case .stopFailed = camera.mirror.state { return true }
        return false
      }
      XCTAssertEqual(session.phase, takePhase)
      XCTAssertFalse(session.cleanupBlocked)
      XCTAssertFalse(session.actionsDisabled)
      XCTAssertTrue(session.interactiveDismissDisabled)
      XCTAssertEqual(try Data(contentsOf: capturer.recordingURL), bytes)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      await session.togglePlayback()
      XCTAssertFalse(session.isPlaying)
      XCTAssertEqual(session.phase, takePhase)
      XCTAssertEqual(try Data(contentsOf: capturer.recordingURL), bytes)
      await session.continuePractice()
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(session.completedWords, 1)
      XCTAssertFalse(session.cleanupBlocked)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capturer.recordingURL.path))
      await session.startRecording()
      XCTAssertEqual(session.phase, .recording)
      XCTAssertEqual(capturer.startCount, 2)
      XCTAssertEqual(camera.driver.factoryCount, 1)
      session.stopRecording()
      let ended = await session.end()
      XCTAssertFalse(ended)
      await session.retryMirrorStop()
      XCTAssertEqual(session.phase, .ended)
    }

    func testFinalCompletionRevokesCameraBeforeCountsAndHistoryWithoutWaitingForCameraRelease()
      async throws
    {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer { camera.driver.releaseAll() }
      let history = PracticeParticipationStore(
        fileURL: fixture.directory.appendingPathComponent("generated-history.json"))
      let session = DirectPracticeSession(
        sound: try oneWordSound(), capturer: capturer,
        player: DirectPracticePlayer(files: files), mirror: camera.mirror, history: history)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      let owner = try XCTUnwrap(camera.runtime.currentOwner)
      let original = try XCTUnwrap(camera.runtime.cleanupAcknowledgement(owner: owner))
      let before = session.phase
      var stopObservedBeforeCommit = false
      let subscription = camera.mirror.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .stopping = state {
            stopObservedBeforeCommit = true
            XCTAssertEqual(session.phase, before)
            XCTAssertEqual(session.completedWords, 0)
            XCTAssertTrue(history.entries.isEmpty)
          }
        }
      }
      defer { subscription.cancel() }
      await session.continuePractice()
      await entered(camera.driver.cleaning)
      XCTAssertTrue(stopObservedBeforeCommit)
      XCTAssertEqual(session.phase, .completed)
      XCTAssertEqual(session.completedWords, 1)
      XCTAssertEqual(history.entries.count, 1)
      XCTAssertEqual(history.entries.first?.wordCount, 1)
      XCTAssertNil(original.receipt)
      XCTAssertEqual(camera.recovery.owner, owner)
      XCTAssertFalse(session.cleanupBlocked)
      await session.restart()
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertEqual(history.entries.count, 1)
      XCTAssertEqual(camera.driver.factoryCount, 1)
      camera.driver.releaseCleanup()
      let released = await original.value()
      XCTAssertEqual(released.result, .released)
      let ended = await session.end()
      XCTAssertTrue(ended)
    }

    func testFinalCameraStopReentrantCloseSupersedesCompletionWithoutHistoryOrCount() async throws {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer { camera.driver.releaseAll() }
      let history = PracticeParticipationStore(
        fileURL: fixture.directory.appendingPathComponent("generated-history.json"))
      let session = DirectPracticeSession(
        sound: try oneWordSound(), capturer: capturer,
        player: DirectPracticePlayer(files: files), mirror: camera.mirror, history: history)
      session.appDidBecomeActive()
      await session.startRecording()
      session.stopRecording()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      var closeRequested = false
      let subscription = camera.mirror.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .stopping = state, !closeRequested {
            closeRequested = true
            session.viewDidDisappear()  // Synchronous end revocation inside stop publication.
          }
        }
      }
      defer { subscription.cancel() }
      await session.continuePractice()
      await entered(camera.driver.cleaning)
      XCTAssertTrue(closeRequested)
      XCTAssertNotEqual(session.phase, .completed)
      XCTAssertNotEqual(session.phase, .ended)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertTrue(history.entries.isEmpty)
      XCTAssertEqual(capturer.discardCount, 1)
      camera.driver.releaseCleanup()
      await mirrorWait { session.phase == .ended }
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertTrue(history.entries.isEmpty)
      XCTAssertEqual(camera.driver.cleanupCount, 1)
    }

    func testMicrophoneEligibilityCameraStopReentrantClosePreventsAnyPermissionAdmission()
      async throws
    {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
      let camera = SessionMirrorFixture(holdsCleanup: true)
      defer { camera.driver.releaseAll() }
      let session = DirectPracticeSession(
        capturer: capturer, player: DirectPracticePlayer(files: files),
        mirror: camera.mirror)
      session.appDidBecomeActive()
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      var closeRequested = false
      let subscription = camera.mirror.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .stopping = state, !closeRequested {
            closeRequested = true
            session.viewDidDisappear()
          }
        }
      }
      defer { subscription.cancel() }
      await session.startRecording()
      await entered(camera.driver.cleaning)
      XCTAssertTrue(closeRequested)
      XCTAssertEqual(capturer.permissionRequestCount, 0)
      XCTAssertEqual(capturer.startCount, 0)
      XCTAssertNotEqual(session.phase, .recording)
      camera.driver.releaseCleanup()
      await mirrorWait { session.phase == .ended }
      XCTAssertEqual(capturer.permissionRequestCount, 0)
      XCTAssertEqual(capturer.startCount, 0)
    }

    #if targetEnvironment(simulator)
      func testFirstLazyMirrorReadDoesNotPublishButFirstRealTransitionForwardsSynchronously() {
        // Explicit inert audio dependencies allocate no files or drivers. The default
        // simulator mirror is unsupported; its Show path cannot enter camera permission.
        let files = ProcessAudioFileOwnership()
        let hardware = AudioHardwareOwnership()
        let capturer = DirectPracticeCapturer(files: files)
        let player = DirectPracticePlayer(files: files, gate: hardware)
        let recognizer = DirectControlledWordRecognizer(files: files)
        XCTAssertNil(ProcessPracticeMirrorRecovery.shared.owner)
        XCTAssertNil(ProcessPracticeMirrorRecovery.shared.runtime)
        let session = DirectPracticeSession(
          capturer: capturer, player: player, wordRecognizer: recognizer,
          cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
        var notifications = 0
        let observation = session.objectWillChange.sink {
          MainActor.assumeIsolated { notifications += 1 }
        }
        defer { observation.cancel() }

        // Observe BEFORE the first getter. Against the old source this is the unwanted
        // publisher seed that fires during the player's first body evaluation.
        let mirror = session.mirror
        XCTAssertEqual(notifications, 0)
        XCTAssertTrue(session.mirror === mirror)
        XCTAssertEqual(notifications, 0)
        XCTAssertEqual(mirror.state, .off)
        XCTAssertFalse(session.interactiveDismissDisabled)
        session.appDidBecomeActive()
        XCTAssertEqual(notifications, 0)

        session.showMirror()
        XCTAssertEqual(mirror.state, .unavailable)
        XCTAssertEqual(
          notifications, 1, "The first real transition must arrive before Show returns")
        session.hideMirror()
        XCTAssertEqual(mirror.state, .off)
        XCTAssertEqual(notifications, 2, "Stop remains synchronous; no scheduler or task hop")
        XCTAssertEqual(session.phase, .ready)
        XCTAssertFalse(session.interactiveDismissDisabled)
        XCTAssertEqual(capturer.permissionRequestCount, 0)
        XCTAssertEqual(capturer.startCount, 0)
        XCTAssertEqual(capturer.stopCount, 0)
        XCTAssertEqual(capturer.cancelCount, 0)
        XCTAssertEqual(capturer.discardCount, 0)
        XCTAssertTrue(player.playedURLs.isEmpty)
        XCTAssertEqual(player.stopCount, 0)
        XCTAssertTrue(recognizer.requests.isEmpty)
        XCTAssertTrue(files.protectedURLs.isEmpty)
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
        XCTAssertNil(hardware.currentLease)
        XCTAssertNil(ProcessPracticeMirrorRecovery.shared.owner)
        XCTAssertNil(ProcessPracticeMirrorRecovery.shared.runtime)
      }
    #endif

    func testMirrorOnlyPublicationsRefreshParentRecordAndDismissGuardsThroughAllStates()
      async throws
    {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let files = ProcessAudioFileOwnership()
      let camera = SessionMirrorFixture(
        permission: .notDetermined, holdsCleanup: true, cleanupFailures: 1)
      defer { camera.driver.releaseAll() }
      let session = DirectPracticeSession(
        capturer: DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files),
        player: DirectPracticePlayer(files: files), mirror: camera.mirror)
      session.appDidBecomeActive()
      var snapshots: [(DirectPracticeMirrorState, Bool, Bool)] = []
      let subscription = session.objectWillChange.sink {
        MainActor.assumeIsolated {
          snapshots.append(
            (
              camera.mirror.state,
              !session.actionsDisabled && !camera.mirror.blocksRecordForCameraPermission,
              session.interactiveDismissDisabled
            ))
        }
      }
      defer { subscription.cancel() }
      session.showMirror()
      XCTAssertTrue(
        snapshots.contains {
          if case .permissionPending = $0.0 { return !$0.1 && $0.2 }
          return false
        })
      session.cancelMirrorPermission()
      XCTAssertTrue(snapshots.contains { $0.0 == .off && $0.1 && !$0.2 })
      camera.permission.status = .authorized
      session.showMirror()
      await mirrorWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      XCTAssertTrue(
        snapshots.contains {
          if case .starting = $0.0 { return $0.1 && $0.2 }
          return false
        })
      XCTAssertTrue(
        snapshots.contains {
          if case .live = $0.0 { return $0.1 && $0.2 }
          return false
        })
      session.hideMirror()
      await entered(camera.driver.cleaning)
      XCTAssertTrue(
        snapshots.contains {
          if case .stopping = $0.0 { return $0.1 && $0.2 }
          return false
        })
      camera.driver.releaseCleanup()
      await mirrorWait {
        if case .stopFailed = camera.mirror.state { return true }
        return false
      }
      XCTAssertTrue(
        snapshots.contains {
          if case .stopFailed = $0.0 { return $0.1 && $0.2 }
          return false
        })
      let beforeRetry = snapshots.count
      await session.retryMirrorStop()
      XCTAssertTrue(snapshots.dropFirst(beforeRetry).contains { $0.0 == .off && $0.1 && !$0.2 })
      XCTAssertEqual(session.phase, .ready)
      XCTAssertFalse(session.cleanupBlocked)
      let ended = await session.end()
      XCTAssertTrue(ended)
    }

    private func mirrorWait(_ predicate: @MainActor () -> Bool) async {
      let deadline = ContinuousClock.now + .seconds(2)
      while !predicate() && ContinuousClock.now < deadline { await Task.yield() }
      XCTAssertTrue(predicate())
    }
  }

  /// New isolated permission fake; callbacks cannot enter AVFoundation or microphone APIs.
  @MainActor
  private final class SessionMirrorPermission: PracticeMirrorPermissionProviding {
    let isSupported = true
    var status: PracticeMirrorPermission
    private(set) var requests = 0
    private var callback: (@MainActor (Bool) -> Void)?
    init(_ status: PracticeMirrorPermission) { self.status = status }
    func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
      requests += 1
      callback = completion
    }
    func complete(_ granted: Bool) {
      status = granted ? .authorized : .denied
      callback?(granted)
    }
  }

  @MainActor
  private final class SessionMirrorFixture {
    let recovery: ProcessPracticeMirrorRecovery
    let permission: SessionMirrorPermission
    let driver: SessionMirrorDriver
    let runtime: PracticeMirrorRuntime
    let mirror: DirectPracticeMirror
    init(
      permission status: PracticeMirrorPermission = .authorized,
      holdsCleanup: Bool = false, cleanupFailures: Int = 0
    ) {
      let recovery = ProcessPracticeMirrorRecovery()
      self.recovery = recovery
      permission = SessionMirrorPermission(status)
      driver = SessionMirrorDriver(holdsCleanup: holdsCleanup, cleanupFailures: cleanupFailures)
      let driver = self.driver
      runtime = PracticeMirrorRuntime(recovery: recovery) { _ in
        driver.make()
        return driver
      }
      mirror = DirectPracticeMirror(
        permission: permission, runtime: runtime, recovery: recovery,
        initialScene: .inactive)
    }
  }

  /// Only inert methods run on the actual serial camera queue; no preview source is provided.
  private final class SessionMirrorDriver: PracticeMirrorDriver, @unchecked Sendable {
    enum Failure: Error { case cleanup, gateDeadline }
    let cleaning = XCTestExpectation(description: "inert camera entered cleanup")
    private let gate = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private let holdsCleanup: Bool
    private let cleanupFailures: Int
    private var factories = 0
    private var starts = 0
    private var cleanups = 0
    var factoryCount: Int { lock.withLock { factories } }
    var startCount: Int { lock.withLock { starts } }
    var cleanupCount: Int { lock.withLock { cleanups } }
    init(holdsCleanup: Bool, cleanupFailures: Int) {
      self.holdsCleanup = holdsCleanup
      self.cleanupFailures = cleanupFailures
    }
    func make() { lock.withLock { factories += 1 } }
    func configure() throws {}
    func start() throws { lock.withLock { starts += 1 } }
    func stopAndReleasePreviewResources() throws {
      let attempt = lock.withLock {
        cleanups += 1
        return cleanups
      }
      if attempt == 1 {
        cleaning.fulfill()
        if holdsCleanup, gate.wait(timeout: .now() + 8) != .success { throw Failure.gateDeadline }
      }
      if attempt <= cleanupFailures { throw Failure.cleanup }
    }
    func releaseCleanup() { gate.signal() }
    func releaseAll() { releaseCleanup() }
  }
#endif

// Append to DirectPracticeSessionTests.swift after its existing bytes, before the two-try
// appendix. Not a separately registered test source: it reuses that file's private inert
// audio helpers. Reviewed/repaired from the frozen Sol save-retry draft v1 (see
// IMPLEMENTATION.md for each delta). Draft assertions only; NOT compiled or executed.
@MainActor
extension DirectPracticeSessionTests {
  func testParticipationSaveRetryRestoresSameCompletionWithoutAudioOrCounterChanges()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player, history: history)
    await finishParticipationDraft(session)
    let original = try XCTUnwrap(session.participationCompletion)
    let counters = (session.completedWords, session.attemptCount)
    let audio = participationDraftAudioCounts(capturer, player)
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(original.soundID, session.sound.id)
    XCTAssertEqual(original.wordCount, session.totalWords)
    XCTAssertTrue(session.canRetryParticipationSave)
    XCTAssertEqual(
      session.historyError,
      "Practice complete, but this session could not be saved to practice history.")
    XCTAssertNil(session.historySavedNote)
    let initialAnnouncement = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    XCTAssertEqual(initialAnnouncement.completion, original)
    XCTAssertEqual(initialAnnouncement.message, session.historyError)
    XCTAssertTrue(history.entries.isEmpty)
    try FileManager.default.removeItem(at: file)

    session.retryParticipationSave()

    XCTAssertEqual(session.participationCompletion, original)
    assertSameParticipations(history.entries, [original])
    XCTAssertEqual(PracticeParticipationStore(fileURL: file).entries, history.entries)
    XCTAssertNil(session.historyError)
    XCTAssertEqual(session.historySavedNote, "Saved to practice history.")
    let successAnnouncement = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    XCTAssertEqual(successAnnouncement.completion, original)
    XCTAssertEqual(successAnnouncement.message, "Saved to practice history.")
    XCTAssertNotEqual(successAnnouncement.id, initialAnnouncement.id)
    XCTAssertFalse(session.canRetryParticipationSave)
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(session.completedWords, counters.0)
    XCTAssertEqual(session.attemptCount, counters.1)
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
    session.retryParticipationSave()
    XCTAssertEqual(session.currentParticipationSaveAnnouncement, successAnnouncement)
    XCTAssertEqual(history.entries.count, 1)
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
  }

  func testParticipationSaveRepeatFailureKeepsPayloadAndDeduplicatesEnteredSameID()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player, history: history)
    await finishParticipationDraft(session)
    let original = try XCTUnwrap(session.participationCompletion)
    let audio = participationDraftAudioCounts(capturer, player)
    let initial = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    session.retryParticipationSave()
    let firstRetry = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    session.retryParticipationSave()
    let secondRetry = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    XCTAssertEqual(Set([initial.id, firstRetry.id, secondRetry.id]).count, 3)
    XCTAssertEqual(firstRetry.message, secondRetry.message)
    XCTAssertEqual(firstRetry.completion, original)
    XCTAssertEqual(secondRetry.completion, original)
    XCTAssertEqual(session.participationCompletion, original)
    XCTAssertEqual(
      session.historyError,
      "Still not saved to practice history. You can try again or keep practicing.")
    XCTAssertNil(session.historySavedNote)
    XCTAssertTrue(session.canRetryParticipationSave)
    XCTAssertTrue(history.entries.isEmpty)
    try FileManager.default.removeItem(at: file)
    // An already committed exact completion, through the actual store's public API.
    try history.record(
      sessionID: original.id, completedAt: original.completedAt,
      soundID: original.soundID, wordCount: original.wordCount)
    var publications = 0
    let subscription = history.$entries.dropFirst().sink { _ in publications += 1 }
    defer { subscription.cancel() }

    session.retryParticipationSave()

    assertSameParticipations(history.entries, [original])
    XCTAssertEqual(PracticeParticipationStore(fileURL: file).entries, history.entries)
    XCTAssertEqual(publications, 0)
    XCTAssertNil(session.historyError)
    XCTAssertFalse(session.canRetryParticipationSave)
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
  }

  func testParticipationSaveUnavailableWriterNeverOffersRetryOrClaimsSave() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player)
    await finishParticipationDraft(session)
    let original = try XCTUnwrap(session.participationCompletion)
    let audio = participationDraftAudioCounts(capturer, player)
    XCTAssertEqual(session.phase, .completed)
    XCTAssertEqual(session.historyError, "Practice complete. Saving history is unavailable here.")
    XCTAssertFalse(session.canRetryParticipationSave)
    let unavailable = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
    XCTAssertEqual(unavailable.message, session.historyError)
    session.retryParticipationSave()
    XCTAssertEqual(session.currentParticipationSaveAnnouncement, unavailable)
    XCTAssertEqual(session.participationCompletion, original)
    XCTAssertEqual(session.historyError, "Practice complete. Saving history is unavailable here.")
    XCTAssertNil(session.historySavedNote)
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
    let ended = await session.end()
    XCTAssertTrue(ended)
  }

  func testParticipationSaveUnreadableHistoryRemainsProtectedAcrossRetry() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let protectedBytes = Data("not a participation document".utf8)
    try protectedBytes.write(to: file)
    let history = PracticeParticipationStore(fileURL: file)
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player, history: history)
    XCTAssertNotNil(history.loadError)
    await finishParticipationDraft(session)
    let original = try XCTUnwrap(session.participationCompletion)
    let audio = participationDraftAudioCounts(capturer, player)
    session.retryParticipationSave()
    XCTAssertEqual(try Data(contentsOf: file), protectedBytes)
    XCTAssertEqual(session.participationCompletion, original)
    XCTAssertEqual(
      session.historyError,
      "Still not saved to practice history. You can try again or keep practicing.")
    XCTAssertNil(session.historySavedNote)
    XCTAssertNotNil(history.loadError)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
  }

  func testParticipationSaveRestartInvalidatesOldRetryAndNewSessionStillSaves() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let session = DirectPracticeSession(
      capturer: DirectPracticeCapturer(recordingDirectory: fixture.directory),
      player: DirectPracticePlayer(), history: history)
    await finishParticipationDraft(session)
    let old = try XCTUnwrap(session.participationCompletion)
    try FileManager.default.removeItem(at: file)
    await session.restart()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertNil(session.participationCompletion)
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    XCTAssertNil(session.historyError)
    XCTAssertFalse(session.canRetryParticipationSave)
    session.retryParticipationSave()
    XCTAssertTrue(history.entries.isEmpty)
    await finishParticipationDraft(session)
    let new = try XCTUnwrap(session.participationCompletion)
    XCTAssertNotEqual(new.id, old.id)
    assertSameParticipations(history.entries, [new])
    XCTAssertNil(session.historyError)
    XCTAssertNil(session.historySavedNote)
    XCTAssertFalse(session.canRetryParticipationSave)
  }

  func testParticipationSaveMoreInvalidatesOldRetryWithoutRecapture() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player, history: history)
    await finishParticipationDraft(session)
    XCTAssertNotNil(session.participationCompletion)
    XCTAssertNotNil(session.nextPracticeSound)
    try FileManager.default.removeItem(at: file)
    let before = participationDraftAudioCounts(capturer, player)
    await session.practiceMore()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertNil(session.participationCompletion)
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    XCTAssertNil(session.historyError)
    XCTAssertFalse(session.canRetryParticipationSave)
    session.retryParticipationSave()
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 0)
    // More performs its existing idle cancel only; no permission, capture, discard or playback.
    var expected = before
    expected[3] += 1
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), expected)
  }

  func testParticipationSaveCloseRevokesOldRetryBeforeCloseSettles() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let session = DirectPracticeSession(
      capturer: DirectPracticeCapturer(recordingDirectory: fixture.directory),
      player: DirectPracticePlayer(), history: history)
    await finishParticipationDraft(session)
    try FileManager.default.removeItem(at: file)
    session.viewDidDisappear()
    XCTAssertNil(session.participationCompletion)
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    XCTAssertFalse(session.canRetryParticipationSave)
    session.retryParticipationSave()
    XCTAssertTrue(history.entries.isEmpty)
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertTrue(history.entries.isEmpty)
  }

  func testParticipationInitialStorePublicationCannotRestoreCompletedAfterReentrantClose()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    let session = DirectPracticeSession(
      capturer: DirectPracticeCapturer(recordingDirectory: fixture.directory),
      player: DirectPracticePlayer(), history: history)
    var enteredCompletion: PracticeParticipation?
    let subscription = history.$entries.sink { entries in
      MainActor.assumeIsolated {
        guard !entries.isEmpty, enteredCompletion == nil else { return }
        XCTAssertEqual(session.phase, .completed)
        enteredCompletion = session.participationCompletion
        session.viewDidDisappear()
        XCTAssertNil(session.participationCompletion)
        XCTAssertNil(session.currentParticipationSaveAnnouncement)
        XCTAssertFalse(session.canRetryParticipationSave)
      }
    }
    defer { subscription.cancel() }
    await finishParticipationDraft(session)
    let old = try XCTUnwrap(enteredCompletion)
    XCTAssertNil(session.historyError)
    XCTAssertNil(session.historySavedNote)
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertNil(session.participationCompletion)
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    assertSameParticipations(history.entries, [old])
    await session.restart()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 0)
    XCTAssertNil(session.historyError)
    session.retryParticipationSave()
    XCTAssertEqual(history.entries.count, 1)
  }

  func testParticipationRetryStorePublicationKeepsFailureAfterCloseAndRejectsNestedRetry()
    async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
    let player = DirectPracticePlayer()
    let session = DirectPracticeSession(capturer: capturer, player: player, history: history)
    await finishParticipationDraft(session)
    let old = try XCTUnwrap(session.participationCompletion)
    let failure = session.historyError
    try FileManager.default.removeItem(at: file)
    let audio = participationDraftAudioCounts(capturer, player)
    var publications = 0
    let subscription = history.$entries.dropFirst().sink { entries in
      MainActor.assumeIsolated {
        guard !entries.isEmpty else { return }
        publications += 1
        XCTAssertFalse(session.canRetryParticipationSave)
        session.retryParticipationSave()
        session.viewDidDisappear()
        XCTAssertNil(session.participationCompletion)
        XCTAssertNil(session.currentParticipationSaveAnnouncement)
      }
    }
    defer { subscription.cancel() }

    session.retryParticipationSave()

    XCTAssertEqual(publications, 1)
    assertSameParticipations(history.entries, [old])
    XCTAssertEqual(session.historyError, failure, "A revoked write is never labelled saved.")
    XCTAssertNil(session.historySavedNote)
    XCTAssertFalse(session.canRetryParticipationSave)
    XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
    let ended = await session.end()
    XCTAssertTrue(ended)
    await session.restart()
    XCTAssertEqual(session.phase, .ready)
    XCTAssertNil(session.historyError)
    XCTAssertNil(session.participationCompletion)
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 0)
    session.retryParticipationSave()
    XCTAssertEqual(history.entries.count, 1)
  }

  func testParticipationCompletionPublicationClosePreventsInitialWrite() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let file = fixture.directory.appendingPathComponent("participation.json")
    let history = PracticeParticipationStore(fileURL: file)
    let session = DirectPracticeSession(
      capturer: DirectPracticeCapturer(recordingDirectory: fixture.directory),
      player: DirectPracticePlayer(), history: history)
    var closeRequested = false
    let subscription = session.$phase.sink { phase in
      MainActor.assumeIsolated {
        guard phase == .completed, !closeRequested else { return }
        closeRequested = true
        XCTAssertNotNil(session.participationCompletion)
        session.viewDidDisappear()
      }
    }
    defer { subscription.cancel() }
    await finishParticipationDraft(session)
    XCTAssertTrue(closeRequested)
    // The winning Close restores the pre-advance counter; the final word is never counted.
    XCTAssertEqual(session.completedWords, session.totalWords - 1)
    XCTAssertNotEqual(session.phase, .completed)
    XCTAssertNil(session.participationCompletion)
    XCTAssertNil(session.currentParticipationSaveAnnouncement)
    XCTAssertFalse(session.canRetryParticipationSave)
    XCTAssertNil(session.historyError)
    XCTAssertTrue(history.entries.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertTrue(history.entries.isEmpty)
  }

  func testParticipationSaveAnnouncementRejectsReentrantNoteAndEventPublicationClose()
    async throws
  {
    for closeDuringEvent in [false, true] {
      let fixture = try DirectOwnedFixture()
      defer { fixture.removeDirectory() }
      let file = fixture.directory.appendingPathComponent("participation.json")
      let history = PracticeParticipationStore(fileURL: file)
      try FileManager.default.createDirectory(at: file, withIntermediateDirectories: true)
      let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory)
      let player = DirectPracticePlayer()
      let session = DirectPracticeSession(capturer: capturer, player: player, history: history)
      XCTAssertNil(session.currentParticipationSaveAnnouncement)
      session.retryParticipationSave()
      XCTAssertNil(session.currentParticipationSaveAnnouncement)
      await finishParticipationDraft(session)
      let completion = try XCTUnwrap(session.participationCompletion)
      let initial = try XCTUnwrap(session.currentParticipationSaveAnnouncement)
      let audio = participationDraftAudioCounts(capturer, player)
      try FileManager.default.removeItem(at: file)
      var revoked = false
      let subscription: AnyCancellable
      if closeDuringEvent {
        // The success note is stored immediately before event willSet. Revoking here
        // exercises the outer event assignment overwriting the nested silent clear.
        subscription = session.objectWillChange.sink {
          MainActor.assumeIsolated {
            guard !revoked, session.historySavedNote != nil else { return }
            revoked = true
            XCTAssertEqual(session.currentParticipationSaveAnnouncement, initial)
            session.viewDidDisappear()
          }
        }
      } else {
        subscription = session.$historySavedNote.sink { note in
          MainActor.assumeIsolated {
            guard !revoked, note != nil else { return }
            revoked = true
            session.viewDidDisappear()
          }
        }
      }
      defer { subscription.cancel() }
      session.retryParticipationSave()
      XCTAssertTrue(revoked)
      XCTAssertNil(session.participationCompletion)
      XCTAssertNil(session.currentParticipationSaveAnnouncement)
      assertSameParticipations(history.entries, [completion])
      XCTAssertEqual(participationDraftAudioCounts(capturer, player), audio)
      session.retryParticipationSave()
      XCTAssertNil(session.currentParticipationSaveAnnouncement)
      let ended = await session.end()
      XCTAssertTrue(ended)
    }
  }

  private func finishParticipationDraft(_ session: DirectPracticeSession) async {
    for _ in 0..<session.totalWords {
      await session.startRecording()
      session.stopRecording()
      await session.continuePractice()
    }
  }

  /// Frozen completion vs store-normalized entry only: the store rebuilds the date through
  /// epoch seconds (one Double offset round trip). Identity/sound/count stay exact; reloaded
  /// entries are compared exactly against the already-normalized visible entries instead.
  private func assertSameParticipations(
    _ actual: [PracticeParticipation], _ expected: [PracticeParticipation],
    file: StaticString = #filePath, line: UInt = #line
  ) {
    XCTAssertEqual(actual.map(\.id), expected.map(\.id), file: file, line: line)
    XCTAssertEqual(actual.map(\.soundID), expected.map(\.soundID), file: file, line: line)
    XCTAssertEqual(actual.map(\.wordCount), expected.map(\.wordCount), file: file, line: line)
    for (left, right) in zip(actual, expected) {
      XCTAssertEqual(
        left.completedAt.timeIntervalSince1970, right.completedAt.timeIntervalSince1970,
        accuracy: 0.000001, file: file, line: line)
    }
  }

  private func participationDraftAudioCounts(
    _ capturer: DirectPracticeCapturer, _ player: DirectPracticePlayer
  ) -> [Int] {
    [
      capturer.permissionRequestCount, capturer.startCount, capturer.stopCount,
      capturer.cancelCount, capturer.discardCount, player.playedURLs.count, player.stopCount,
    ]
  }
}

// Append to DirectPracticeSessionTests.swift after its existing bytes (and after the
// participation-save appendix). Not a separately registered test source: it reuses that
// file's private helpers (DirectPracticePlayer, DirectConcreteCapturer, DirectOwnedFixture,
// settle/entered, and the DEBUG mirror fixtures). Draft only; NOT compiled or executed.
// Only small generated files in an isolated temporary directory are written. No sensor,
// output driver, model, network or shared history is used.
@MainActor
extension DirectPracticeSessionTests {
  func testTwoTriesKeepDistinctFilesAndReplayEachThroughOnePlayerWithoutAdvancing()
    async throws
  {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let earlier = try XCTUnwrap(h.session.earlierTry)
    let latest = try XCTUnwrap(h.session.latestTry)
    XCTAssertEqual(h.session.tries.map(\.id), [earlier.id, latest.id])
    XCTAssertNotEqual(earlier.id, latest.id)
    XCTAssertEqual(earlier.summary.duration, 0.4)
    XCTAssertEqual(latest.summary.duration, 0.9)
    guard case .review(let summary, _) = h.session.phase else {
      return XCTFail("Two completed tries should land in review.")
    }
    XCTAssertEqual(summary.duration, 0.9, "The review summary describes the latest take.")
    XCTAssertEqual(h.capturer.urls.count, 2)
    XCTAssertNotEqual(h.capturer.urls[0], h.capturer.urls[1])
    XCTAssertTrue(h.capturer.urls.allSatisfy(twoTryExists))
    XCTAssertEqual(h.session.attemptCount, 2)
    XCTAssertEqual(h.session.completedWords, 0)
    XCTAssertTrue(h.player.playedURLs.isEmpty, "Nothing plays automatically after capture.")

    await h.session.togglePlayback(tryID: earlier.id)
    XCTAssertEqual(h.player.playedURLs, [h.capturer.urls[0]])
    XCTAssertEqual(h.session.playingTryID, earlier.id)
    XCTAssertTrue(h.session.isPlaying)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    // Same take stops it; playing Earlier never changes the latest summary.
    await h.session.togglePlayback(tryID: earlier.id)
    XCTAssertFalse(h.session.isPlaying)
    XCTAssertNil(h.session.playingTryID)
    XCTAssertEqual(h.session.phase, .review(latest.summary, latest.assessment))

    await h.session.togglePlayback(tryID: latest.id)
    XCTAssertEqual(h.player.playedURLs, h.capturer.urls)
    XCTAssertEqual(h.session.playingTryID, latest.id)
    await h.session.togglePlayback()  // Latest-compatible control stops the active take.
    XCTAssertFalse(h.session.isPlaying)

    await h.session.continuePractice()
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertEqual(h.session.completedWords, 1)
    XCTAssertEqual(h.session.attemptCount, 2)
    XCTAssertTrue(h.session.tries.isEmpty)
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    XCTAssertEqual(h.capturer.discardedIndices.sorted(), [0, 1])
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
    XCTAssertNil(h.gate.currentLease)
  }

  func testExplicitSwitchWaitsForHeldStopThenPlaysOnlyRequestedTake() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let earlier = try XCTUnwrap(h.session.earlierTry)
    let latest = try XCTUnwrap(h.session.latestTry)
    h.player.holdCleanup = true
    await h.session.togglePlayback(tryID: earlier.id)
    let queued = await h.player.driver(0)
    let first = try XCTUnwrap(queued)
    defer { first.releaseAll() }
    let switching = Task { await h.session.togglePlayback(tryID: latest.id) }
    await entered(first.cleaning)
    XCTAssertEqual(h.player.playedURLs, [h.capturer.urls[0]])
    XCTAssertEqual(h.session.playingTryID, earlier.id)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    // A repeated tap while the exact stop settles cannot start anything.
    await h.session.togglePlayback(tryID: latest.id)
    XCTAssertEqual(h.player.playedURLs.count, 1)
    h.player.holdCleanup = false  // Applies only to drivers created after this point.
    first.releaseCleanup()
    await switching.value
    XCTAssertEqual(h.player.playedURLs, h.capturer.urls)
    XCTAssertEqual(h.session.playingTryID, latest.id)
    XCTAssertTrue(h.session.isPlaying)
    XCTAssertEqual(first.stopCount, 1)
    // The superseded operation's late completion cannot stop or fail the successor.
    h.player.deliverCapturedCompletion(index: 0, successfully: false)
    XCTAssertTrue(h.session.isPlaying)
    XCTAssertNil(h.session.playbackError)
    XCTAssertEqual(h.session.playingTryID, latest.id)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
  }

  func testSwitchDuringPreparationReleasesExactOperationBeforeOtherTakePlays() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let earlier = try XCTUnwrap(h.session.earlierTry)
    let latest = try XCTUnwrap(h.session.latestTry)
    h.player.holdPreparation = true
    let starting = Task { await h.session.togglePlayback(tryID: earlier.id) }
    let queued = await h.player.driver(0)
    let first = try XCTUnwrap(queued)
    defer { first.releaseAll() }
    await entered(first.prepared)
    XCTAssertFalse(h.session.isPlaying)
    h.player.holdPreparation = false
    let switching = Task { await h.session.togglePlayback(tryID: latest.id) }
    // The exact stop request is committed before preparation is allowed to finish.
    await twoTryWait {
      if case .stopping = h.session.playbackState { return true }
      return false
    }
    XCTAssertEqual(h.player.playedURLs.count, 1)
    first.releasePreparation()
    await starting.value
    await switching.value
    XCTAssertEqual(h.player.playedURLs, h.capturer.urls)
    XCTAssertEqual(h.session.playingTryID, latest.id)
    XCTAssertNil(h.session.playbackError)
    _ = await h.session.end()
  }

  func testNegativeSwitchStopNeverStartsOtherTakeAndExplicitRetryKeepsBoth() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let earlier = try XCTUnwrap(h.session.earlierTry)
    let latest = try XCTUnwrap(h.session.latestTry)
    h.player.cleanupFailures = 1
    await h.session.togglePlayback(tryID: earlier.id)
    let queued = await h.player.driver(0)
    let first = try XCTUnwrap(queued)
    defer { first.releaseAll() }
    await h.session.togglePlayback(tryID: latest.id)
    XCTAssertEqual(h.player.playedURLs, [h.capturer.urls[0]])
    XCTAssertTrue(h.session.hasPlaybackCleanupIssue)
    XCTAssertTrue(h.session.cleanupBlocked)
    XCTAssertEqual(h.session.tries.count, 2)
    let permissions = h.capturer.permissionRequests
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    let original = try XCTUnwrap(h.player.requestStop(id: first.operation.id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    h.player.cleanupFailures = 0
    await h.session.retryCleanup()
    XCTAssertFalse(h.session.cleanupBlocked)
    XCTAssertEqual(h.session.playbackState, .idle)
    XCTAssertEqual(h.session.tries.map(\.id), [earlier.id, latest.id])
    XCTAssertTrue(h.capturer.urls.allSatisfy(twoTryExists))
    XCTAssertEqual(h.player.playedURLs.count, 1, "Recovery never starts the requested take.")
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
    await h.session.togglePlayback(tryID: latest.id)
    XCTAssertEqual(h.player.playedURLs, h.capturer.urls)
    _ = await h.session.end()
  }

  func testCloseDuringHeldSwitchWinsAndRemovesBothWithoutPlayingOtherTake() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let earlier = try XCTUnwrap(h.session.earlierTry)
    let latest = try XCTUnwrap(h.session.latestTry)
    h.player.holdCleanup = true
    await h.session.togglePlayback(tryID: earlier.id)
    let queued = await h.player.driver(0)
    let first = try XCTUnwrap(queued)
    defer { first.releaseAll() }
    let switching = Task { await h.session.togglePlayback(tryID: latest.id) }
    await entered(first.cleaning)
    let closing = Task { await h.session.end() }
    await twoTryWait { h.session.closeNote != nil }
    first.releaseCleanup()
    await switching.value
    let ended = await closing.value
    XCTAssertTrue(ended)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertEqual(h.player.playedURLs, [h.capturer.urls[0]])
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    XCTAssertEqual(h.session.completedWords, 0)
  }

  func testThirdTryRemovesOldestBeforePermissionAndAllocationAndKeepsTwoFiles() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let latest = try XCTUnwrap(h.session.latestTry)
    let before = h.capturer.events.count
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.session.phase, .recording)
    let events = Array(h.capturer.events.dropFirst(before))
    let discard = try XCTUnwrap(events.firstIndex(of: .discard(0)))
    let permission = try XCTUnwrap(events.firstIndex(of: .permission))
    let start = try XCTUnwrap(events.firstIndex(of: .start(2)))
    XCTAssertLessThan(discard, permission)
    XCTAssertLessThan(permission, start)
    XCTAssertFalse(events.contains(.discard(1)))
    XCTAssertFalse(twoTryExists(h.capturer.urls[0]))
    XCTAssertEqual(h.capturer.urls.filter(twoTryExists).count, 2)
    h.session.stopRecording()
    XCTAssertEqual(h.session.tries.first?.id, latest.id)
    XCTAssertEqual(h.session.tries.map(\.summary.duration), [0.9, 1.3])
    XCTAssertEqual(h.session.attemptCount, 3)
    XCTAssertEqual(h.session.completedWords, 0)
    XCTAssertEqual(h.capturer.urls.filter(twoTryExists), Array(h.capturer.urls.suffix(2)))
    _ = await h.session.end()
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
  }

  func testThirdTryEvictionFailureBlocksAllocationAndExplicitRecoveryKeepsLatest()
    async throws
  {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    let latest = try XCTUnwrap(h.session.latestTry)
    let permissions = h.capturer.permissionRequests
    h.capturer.failDiscardIndices = [0]
    await h.session.recordAnotherTry()
    XCTAssertEqual(
      h.session.phase,
      .failed(AudioCaptureError.couldNotDeleteTemporaryRecording.localizedDescription))
    XCTAssertTrue(h.session.cleanupBlocked)
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    XCTAssertEqual(h.capturer.urls.count, 2, "No third file is allocated.")
    XCTAssertTrue(h.capturer.urls.allSatisfy(twoTryExists))
    XCTAssertFalse(h.session.canReturnToReview)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    await h.session.togglePlayback()
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    h.capturer.failDiscardIndices = []
    await h.session.retryCleanup()
    XCTAssertEqual(h.session.phase, .review(latest.summary, latest.assessment))
    XCTAssertEqual(h.session.tries.map(\.id), [latest.id])
    XCTAssertFalse(twoTryExists(h.capturer.urls[0]))
    XCTAssertTrue(twoTryExists(h.capturer.urls[1]))
    XCTAssertEqual(h.capturer.permissionRequests, permissions, "Recovery never resumes capture.")
    XCTAssertEqual(h.session.attemptCount, 2)
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    // Record another try stays unavailable while the kept take is playing.
    await h.session.togglePlayback()
    XCTAssertTrue(h.session.isPlaying)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    _ = await h.session.end()
  }

  func testDeniedAndFailedReplacementKeepSafeTakeUntilExplicitBack() async throws {
    enum Failure: CaseIterable { case denied, start, read }
    for failure in Failure.allCases {
      for prior in [1, 2] {
        let h = try TwoTryHarness()
        defer { h.fixture.removeDirectory() }
        if prior == 2 {
          await twoTryRecordBoth(h)
        } else {
          await h.session.startRecording()
          h.session.stopRecording()
        }
        let kept = try XCTUnwrap(h.session.latestTry)
        let keptURL = try XCTUnwrap(h.capturer.urls.last)
        XCTAssertFalse(h.session.canStartRecording)
        switch failure {
        case .denied: h.capturer.permissionGranted = false
        case .start: h.capturer.failStart = true
        case .read: h.capturer.failRead = true
        }
        await h.session.recordAnotherTry()
        if failure == .read {
          XCTAssertEqual(h.session.phase, .recording)
          h.session.stopRecording()
          await settle(h.session)
        }
        switch failure {
        case .denied: XCTAssertEqual(h.session.phase, .permissionDenied)
        case .start:
          XCTAssertEqual(
            h.session.phase, .failed(AudioCaptureError.couldNotStart.localizedDescription))
        case .read:
          XCTAssertEqual(
            h.session.phase, .failed(AudioCaptureError.couldNotReadRecording.localizedDescription))
          XCTAssertFalse(twoTryExists(try XCTUnwrap(h.capturer.urls.last)))
        }
        XCTAssertEqual(h.session.tries.map(\.id), [kept.id])
        XCTAssertFalse(h.session.canStartRecording)
        XCTAssertTrue(twoTryExists(keptURL))
        if prior == 2 { XCTAssertFalse(twoTryExists(h.capturer.urls[0])) }
        XCTAssertEqual(h.session.attemptCount, prior)
        XCTAssertEqual(h.session.completedWords, 0)
        XCTAssertFalse(h.session.cleanupBlocked)
        XCTAssertTrue(h.session.canReturnToReview)
        XCTAssertTrue(h.player.playedURLs.isEmpty)
        await h.session.continuePractice()  // Continue is unavailable until Back.
        XCTAssertEqual(h.session.completedWords, 0)
        h.session.returnToReview()
        XCTAssertEqual(h.session.phase, .review(kept.summary, kept.assessment))
        XCTAssertTrue(h.player.playedURLs.isEmpty, "Back never autoplays.")
        await h.session.togglePlayback()
        XCTAssertEqual(h.player.playedURLs, [keptURL])
        let ended = await h.session.end()
        XCTAssertTrue(ended)
        XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      }
    }
  }

  func testReplacementStopHardwareFailureBlocksUntilExactRecoveryRestoresSafeTake()
    async throws
  {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await h.session.startRecording()
    h.session.stopRecording()
    let kept = try XCTUnwrap(h.session.latestTry)
    await h.session.recordAnotherTry()
    h.capturer.failStopHardware = true
    h.session.stopRecording()
    await settle(h.session)
    XCTAssertTrue(h.session.cleanupBlocked)
    XCTAssertTrue(h.session.hasHardwareCleanupIssue)
    XCTAssertFalse(h.session.canReturnToReview)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    XCTAssertEqual(h.session.attemptCount, 1)
    XCTAssertTrue(twoTryExists(h.capturer.urls[0]))
    let events = h.capturer.events.count
    h.capturer.failStopHardware = false
    await h.session.retryCleanup()
    XCTAssertFalse(h.session.cleanupBlocked)
    XCTAssertEqual(h.session.phase, .review(kept.summary, kept.assessment))
    XCTAssertEqual(h.session.tries.map(\.id), [kept.id])
    XCTAssertTrue(twoTryExists(h.capturer.urls[0]))
    XCTAssertFalse(twoTryExists(h.capturer.urls[1]))
    XCTAssertFalse(h.capturer.events.dropFirst(events).contains(.permission))
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    _ = await h.session.end()
  }

  // In this fake a failed stop leaves its partial operation active and hardware-blocked; it
  // never returns a take, and its owner differs from the kept take's. Only the kept take's
  // failed discard registers process recovery; the failed operation stays producer-held.
  func testReplacementStopHardwareFailureThenCloseStaysBlockedUntilExplicitRetryEnds()
    async throws
  {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await h.session.startRecording()
    h.session.stopRecording()
    let kept = try XCTUnwrap(h.session.latestTry)
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.session.phase, .recording)
    let keptOwner = h.capturer.ownerIDs[0]
    let failedOwner = h.capturer.ownerIDs[1]
    XCTAssertNotEqual(keptOwner, failedOwner)
    let stopBase = h.capturer.events.count
    h.capturer.failStopHardware = true
    h.session.stopRecording()
    await settle(h.session)
    // The failed transition cancels only the in-progress operation; nothing is discarded.
    XCTAssertEqual(Array(h.capturer.events.dropFirst(stopBase)), [.stop(1), .cancel])
    XCTAssertEqual(
      h.session.phase, .failed(AudioCaptureError.hardwareCleanupUnconfirmed.localizedDescription))
    XCTAssertTrue(h.session.cleanupBlocked)
    XCTAssertTrue(h.session.hasHardwareCleanupIssue)
    XCTAssertEqual(h.session.tries.map(\.id), [kept.id])
    XCTAssertTrue(twoTryExists(h.capturer.urls[0]))
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
    XCTAssertEqual(h.session.attemptCount, 1)
    XCTAssertFalse(h.session.canReturnToReview)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    let permissions = h.capturer.permissionRequests
    await h.session.recordAnotherTry()
    await h.session.togglePlayback()
    await h.session.continuePractice()
    await h.session.retry()
    h.session.returnToReview()
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    XCTAssertEqual(h.capturer.events.count, stopBase + 2)
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    XCTAssertEqual(h.session.completedWords, 0)

    h.capturer.failStopHardware = false
    h.capturer.failDiscardIndices = [0]
    let closeBase = h.capturer.events.count
    let firstClose = await h.session.end()
    XCTAssertFalse(firstClose)
    // Close requests the kept take once; the hardware-blocked operation is never discarded.
    XCTAssertEqual(Array(h.capturer.events.dropFirst(closeBase)), [.discard(0)])
    XCTAssertEqual(h.files.pendingCleanupOwners, [keptOwner])
    XCTAssertEqual(
      h.capturer.cleanupState,
      CaptureCleanupState(hardwareBlockedOperationID: failedOwner, fileBlockedOwnerIDs: [keptOwner])
    )
    XCTAssertTrue(h.session.hasHardwareCleanupIssue)
    XCTAssertTrue(h.session.hasPendingFileCleanup)
    XCTAssertEqual(
      h.session.closeNote,
      "Microphone cleanup is not confirmed, so this screen stays open. Use Retry cleanup.")
    XCTAssertNotEqual(h.session.phase, .ended)
    // A fresh Close joins the sticky end and cannot bypass unconfirmed hardware.
    let secondClose = await h.session.end()
    XCTAssertFalse(secondClose)
    XCTAssertNotEqual(h.session.phase, .ended)
    XCTAssertEqual(h.capturer.events.count, closeBase + 1)
    XCTAssertTrue(h.capturer.urls.allSatisfy(twoTryExists))

    h.capturer.failDiscardIndices = []
    let retryBase = h.capturer.events.count
    await h.session.retryCleanup()
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertFalse(h.session.cleanupBlocked)
    XCTAssertFalse(h.session.hasHardwareCleanupIssue)
    // Exact producer retries release both owners; the trailing cancel is an idle no-op.
    XCTAssertEqual(Array(h.capturer.events.dropFirst(retryBase)), [.cancel])
    let failedReceipt = try XCTUnwrap(h.capturer.completedFileCleanup(operationID: failedOwner))
    XCTAssertTrue(failedReceipt.hardwareReleased)
    XCTAssertTrue(failedReceipt.allRequestedFilesRemoved)
    let keptReceipt = try XCTUnwrap(h.capturer.completedFileCleanup(operationID: keptOwner))
    XCTAssertTrue(keptReceipt.allRequestedFilesRemoved)
    XCTAssertEqual(h.capturer.discardedIndices, [0], "No take is discarded twice.")
    XCTAssertEqual(h.capturer.cleanupState, .idle)
    XCTAssertTrue(h.session.tries.isEmpty)
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    XCTAssertEqual(h.capturer.urls.count, 2)
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
    XCTAssertNil(h.gate.currentLease)
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    XCTAssertEqual(h.session.attemptCount, 1)
    XCTAssertEqual(h.session.completedWords, 0)
    XCTAssertTrue(h.history.entries.isEmpty)
  }

  func testReplacementPermissionDialogKeepsTakeButBackgroundUpgradesToFullCleanup()
    async throws
  {
    for background in [false, true] {
      let h = try TwoTryHarness()
      defer { h.fixture.removeDirectory() }
      await h.session.startRecording()
      h.session.stopRecording()
      h.capturer.holdsPermission = true
      let another = Task { await h.session.recordAnotherTry() }
      await twoTryWait { h.capturer.permissionHeld }
      if background {
        h.session.appDidEnterBackground()
      } else {
        h.session.appDidBecomeInactive()
      }
      await settle(h.session)
      h.capturer.resolvePermission(true)
      await another.value
      if background {
        XCTAssertEqual(h.session.phase, .ready)
        XCTAssertTrue(h.session.tries.isEmpty)
        XCTAssertFalse(twoTryExists(h.capturer.urls[0]))
        XCTAssertEqual(h.capturer.urls.count, 1, "A revoked grant cannot allocate.")
      } else {
        XCTAssertEqual(h.session.phase, .recording)
        XCTAssertTrue(twoTryExists(h.capturer.urls[0]))
        h.session.stopRecording()
        XCTAssertEqual(h.session.tries.count, 2)
      }
      _ = await h.session.end()
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    }
  }

  func testSelectiveEvictionFailureUpgradesOnCloseBackgroundAndDisappear() async throws {
    enum Exit: CaseIterable { case close, background, disappear }
    for exit in Exit.allCases {
      let h = try TwoTryHarness()
      defer { h.fixture.removeDirectory() }
      await twoTryRecordBoth(h)
      h.capturer.failDiscardIndices = [0]
      await h.session.recordAnotherTry()
      XCTAssertTrue(h.session.cleanupBlocked)
      XCTAssertTrue(twoTryExists(h.capturer.urls[1]))
      switch exit {
      case .close:
        let first = await h.session.end()
        XCTAssertFalse(first)
      case .background:
        h.session.appDidEnterBackground()
        await settle(h.session)
      case .disappear:
        h.session.viewDidDisappear()
        await settle(h.session)
      }
      // The full intent attempts the survivor even though the evicted file still fails.
      XCTAssertFalse(twoTryExists(h.capturer.urls[1]))
      XCTAssertTrue(twoTryExists(h.capturer.urls[0]))
      XCTAssertTrue(h.capturer.discardedIndices.contains(1))
      XCTAssertEqual(h.files.pendingCleanupOwners, [h.capturer.ownerIDs[0]])
      XCTAssertEqual(h.capturer.urls.count, 2)
      XCTAssertNotEqual(h.session.phase, .ended)
      h.capturer.failDiscardIndices = []
      await h.session.retryCleanup()
      if exit == .background {
        XCTAssertEqual(h.session.phase, .ready)
      } else {
        XCTAssertEqual(h.session.phase, .ended)
      }
      XCTAssertTrue(h.session.tries.isEmpty)
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
      XCTAssertEqual(h.session.completedWords, 0)
    }
  }

  func testNextAttemptsSecondDeletionAfterFirstFailsAndRecoveryNeverAdvances() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await twoTryRecordBoth(h)
    h.capturer.failDiscardIndices = [0]
    await h.session.continuePractice()
    XCTAssertEqual(
      h.session.phase,
      .failed(AudioCaptureError.couldNotDeleteTemporaryRecording.localizedDescription))
    XCTAssertEqual(h.session.completedWords, 0)
    XCTAssertEqual(h.capturer.discardedIndices.sorted(), [0, 1])
    XCTAssertTrue(twoTryExists(h.capturer.urls[0]))
    XCTAssertFalse(twoTryExists(h.capturer.urls[1]))
    h.capturer.failDiscardIndices = []
    await h.session.retryCleanup()
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertEqual(h.session.completedWords, 0, "Recovery never resumes a failed Continue.")
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    // The successful exact retry is authoritative; no second producer discard occurs.
    XCTAssertEqual(h.capturer.discardedIndices.filter { $0 == 0 }.count, 1)
  }

  func testBothTakesAreRemovedByNextFinishDestructiveRetryAndRestart() async throws {
    enum Action: CaseIterable { case next, finish, retry, restart }
    for action in Action.allCases {
      let h = try TwoTryHarness(oneWord: action == .finish)
      defer { h.fixture.removeDirectory() }
      await twoTryRecordBoth(h)
      switch action {
      case .next: await h.session.continuePractice()
      case .finish: await h.session.continuePractice()
      case .retry: await h.session.retry()
      case .restart: await h.session.restart()
      }
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      XCTAssertEqual(h.capturer.discardedIndices.sorted(), [0, 1])
      XCTAssertTrue(h.session.tries.isEmpty)
      XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
      switch action {
      case .next:
        XCTAssertEqual(h.session.phase, .ready)
        XCTAssertEqual(h.session.completedWords, 1)
      case .finish:
        XCTAssertEqual(h.session.phase, .completed)
        XCTAssertEqual(h.history.entries.count, 1)
        XCTAssertEqual(h.history.entries.first?.wordCount, 1)
      case .retry:
        XCTAssertEqual(h.session.phase, .ready)
        XCTAssertEqual(h.session.completedWords, 0)
        XCTAssertEqual(h.session.attemptCount, 2)
      case .restart:
        XCTAssertEqual(h.session.phase, .ready)
        XCTAssertEqual(h.session.attemptCount, 0)
      }
    }
  }

  func testTwoConcreteOwnersPermitExplicitSecondFileOnlyClose() async throws {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let gate = AudioHardwareOwnership()
    let capturer = DirectConcreteCapturer(directory: fixture.directory, files: files, gate: gate)
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files, gate: gate),
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session.startRecording()
    session.stopRecording()
    let first = try XCTUnwrap(capturer.returnedRecording)
    await session.recordAnotherTry()
    session.stopRecording()
    let second = try XCTUnwrap(capturer.returnedRecording)
    XCTAssertNotEqual(first.url, second.url)
    let owners = Set([first, second].compactMap(\.cleanupOwnerID))
    XCTAssertEqual(owners.count, 2)
    capturer.removal.failures = 2
    let firstClose = await session.end()
    XCTAssertFalse(firstClose)
    XCTAssertEqual(capturer.discardCount, 2, "The second file is attempted after the first fails.")
    XCTAssertEqual(files.pendingCleanupOwners, owners)
    XCTAssertEqual(
      session.closeNote,
      "The recording couldn't be removed. Use Retry cleanup, or tap Close again to leave it pending."
    )
    let secondClose = await session.end()
    XCTAssertTrue(secondClose)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(files.pendingCleanupOwners, owners)
    XCTAssertTrue(FileManager.default.fileExists(atPath: first.url.path))
    XCTAssertTrue(FileManager.default.fileExists(atPath: second.url.path))
    for owner in owners { XCTAssertTrue(files.retryCleanup(owner: owner)) }
    XCTAssertFalse(FileManager.default.fileExists(atPath: first.url.path))
    XCTAssertFalse(FileManager.default.fileExists(atPath: second.url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
  }

  func testSecondFileOnlyCloseRefusesUnregisteredOrNilOwnerSibling() async throws {
    for nilOwner in [false, true] {
      let h = try TwoTryHarness()
      defer { h.fixture.removeDirectory() }
      if nilOwner {
        h.capturer.nilOwnerIndices = [1]
      } else {
        h.capturer.unregisteredIndices = [1]
      }
      await twoTryRecordBoth(h)
      h.capturer.failDiscardIndices = [0, 1]
      let first = await h.session.end()
      XCTAssertFalse(first)
      // One file's registered recovery cannot stand in for its sibling.
      XCTAssertEqual(h.files.pendingCleanupOwners, [h.capturer.ownerIDs[0]])
      XCTAssertEqual(
        h.session.closeNote,
        "The recording couldn't be removed, so this screen stays open. Use Retry cleanup.")
      let second = await h.session.end()
      XCTAssertFalse(second)
      XCTAssertNotEqual(h.session.phase, .ended)
      XCTAssertTrue(h.capturer.urls.allSatisfy(twoTryExists))
      if !nilOwner {
        h.capturer.failDiscardIndices = []
        await h.session.retryCleanup()
        XCTAssertEqual(h.session.phase, .ended)
        XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      }
    }
  }

  func testCloseDuringStopReturnTracksTakeOnlyForCleanupWithoutCounting() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await h.session.startRecording()
    h.session.stopRecording()
    await h.session.recordAnotherTry()
    let session = h.session
    h.capturer.duringStop = { session.viewDidDisappear() }
    defer { h.capturer.duringStop = nil }
    session.stopRecording()
    XCTAssertEqual(session.attemptCount, 1)
    if case .review = session.phase { XCTFail("A superseded stop must not publish review.") }
    await settle(session)
    let ended = await session.end()  // Joins the winning Close.
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.attemptCount, 1)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(h.capturer.discardedIndices.sorted(), [0, 1])
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
  }

  func testReviewPublicationCloseRemovesBothTakes() async throws {
    let h = try TwoTryHarness()
    defer { h.fixture.removeDirectory() }
    await h.session.startRecording()
    h.session.stopRecording()
    await h.session.recordAnotherTry()
    let session = h.session
    var requested = false
    let observation = session.$phase.sink { phase in
      MainActor.assumeIsolated {
        guard !requested, case .review(let summary, _) = phase, summary.duration == 0.9 else {
          return
        }
        requested = true
        session.viewDidDisappear()
      }
    }
    defer { observation.cancel() }
    session.stopRecording()
    XCTAssertTrue(requested)
    XCTAssertEqual(session.attemptCount, 1, "The superseded second take is not counted.")
    await settle(session)
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertEqual(session.attemptCount, 1)
    XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
  }

  // @Published delivers the new value from willSet, before storage. These triggers read the
  // event argument (the getter still returns the old value) and fire once to avoid recursion.

  func testCloseInCompletedWordsPublicationRevokesIntermediateAndFinalAdvance() async throws {
    for oneWord in [false, true] {
      let h = try TwoTryHarness(oneWord: oneWord)
      defer { h.fixture.removeDirectory() }
      let session = h.session
      let word = session.currentPrompt.word
      await session.startRecording()
      session.stopRecording()
      let events = h.capturer.events.count
      var fired = false
      let observation = session.$completedWords.sink { value in
        MainActor.assumeIsolated {
          guard !fired, value == 1 else { return }
          fired = true
          session.viewDidDisappear()
        }
      }
      defer { observation.cancel() }
      await session.continuePractice()
      XCTAssertTrue(fired)
      XCTAssertEqual(session.completedWords, 0, "A revoked advance is never counted.")
      XCTAssertEqual(session.currentPrompt.word, word)
      XCTAssertNotEqual(session.phase, .completed)
      XCTAssertNotEqual(session.phase, .ready)
      XCTAssertNil(session.participationCompletion)
      let ended = await session.end()  // Joins the winning Close.
      XCTAssertTrue(ended)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertEqual(session.attemptCount, 1)
      XCTAssertNil(session.participationCompletion)
      XCTAssertNil(session.historyError)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(session.tries.isEmpty)
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
      XCTAssertNil(h.gate.currentLease)
      XCTAssertTrue(h.player.playedURLs.isEmpty)
      // Close never starts a successor capture.
      let later = h.capturer.events.dropFirst(events)
      XCTAssertFalse(later.contains(.permission))
      XCTAssertFalse(later.contains { if case .start = $0 { return true } else { return false } })
    }
  }

  func testBackgroundInCompletedWordsPublicationRevokesAdvanceAndNextPracticeFinishesExactly()
    async throws
  {
    for oneWord in [false, true] {
      let h = try TwoTryHarness(oneWord: oneWord)
      defer { h.fixture.removeDirectory() }
      let session = h.session
      let word = session.currentPrompt.word
      await session.startRecording()
      session.stopRecording()
      var fired = false
      let observation = session.$completedWords.sink { value in
        MainActor.assumeIsolated {
          guard !fired, value == 1 else { return }
          fired = true
          session.appDidEnterBackground()
        }
      }
      defer { observation.cancel() }
      await session.continuePractice()
      XCTAssertTrue(fired)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertNotEqual(session.phase, .completed)
      await settle(session)
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertEqual(session.currentPrompt.word, word, "No word is skipped.")
      XCTAssertNil(session.participationCompletion)
      XCTAssertNil(session.historyError)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(session.tries.isEmpty)
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
      XCTAssertEqual(h.capturer.permissionRequests, 1, "Background never recaptures.")
      XCTAssertTrue(h.player.playedURLs.isEmpty)

      // A fresh actual practice from Ready advances once per word and completes exactly.
      for expected in 1...session.totalWords {
        await session.startRecording()
        XCTAssertEqual(session.phase, .recording)
        session.stopRecording()
        await session.continuePractice()
        XCTAssertEqual(session.completedWords, expected)
      }
      XCTAssertEqual(session.phase, .completed)
      XCTAssertEqual(session.attemptCount, session.totalWords + 1)
      let completion = try XCTUnwrap(session.participationCompletion)
      XCTAssertEqual(completion.wordCount, session.totalWords)
      XCTAssertEqual(h.history.entries.map(\.id), [completion.id])
      XCTAssertEqual(h.history.entries.first?.wordCount, session.totalWords)
      let permissions = h.capturer.permissionRequests
      await session.continuePractice()
      await session.startRecording()
      XCTAssertEqual(session.completedWords, session.totalWords, "Never overshoots.")
      XCTAssertEqual(session.phase, .completed)
      XCTAssertEqual(h.capturer.permissionRequests, permissions)
      XCTAssertEqual(h.history.entries.count, 1)
      let ended = await session.end()
      XCTAssertTrue(ended)
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    }
  }

  func testLifecycleInAttemptCountPublicationCleansStoppedTakeWithoutCounting() async throws {
    for close in [false, true] {
      let h = try TwoTryHarness()
      defer { h.fixture.removeDirectory() }
      let session = h.session
      await session.startRecording()
      var fired = false
      let observation = session.$attemptCount.sink { value in
        MainActor.assumeIsolated {
          guard !fired, value == 1 else { return }
          fired = true
          if close { session.viewDidDisappear() } else { session.appDidEnterBackground() }
        }
      }
      defer { observation.cancel() }
      session.stopRecording()
      XCTAssertTrue(fired)
      XCTAssertEqual(session.attemptCount, 0, "A superseded stop is never counted.")
      if case .review = session.phase { XCTFail("A superseded stop must not publish review.") }
      if close {
        let ended = await session.end()
        XCTAssertTrue(ended)
        XCTAssertEqual(session.phase, .ended)
      } else {
        await settle(session)
        XCTAssertEqual(session.phase, .ready)
      }
      XCTAssertEqual(session.attemptCount, 0)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertTrue(session.tries.isEmpty)
      // The returned file and owner were tracked and removed exactly once.
      XCTAssertEqual(h.capturer.discardedIndices, [0])
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
      XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
      XCTAssertEqual(h.capturer.permissionRequests, 1)
      XCTAssertTrue(h.player.playedURLs.isEmpty)
      XCTAssertTrue(h.history.entries.isEmpty)
      guard !close else { continue }
      await session.startRecording()
      session.stopRecording()
      XCTAssertEqual(session.attemptCount, 1)
      XCTAssertEqual(session.tries.count, 1)
      await session.continuePractice()
      XCTAssertEqual(session.completedWords, 1)
      XCTAssertEqual(session.phase, .ready)
      _ = await session.end()
      XCTAssertFalse(h.capturer.urls.contains(where: twoTryExists))
    }
  }

  private func twoTryRecordBoth(_ h: TwoTryHarness) async {
    await h.session.startRecording()
    h.session.stopRecording()
    await h.session.recordAnotherTry()
    h.session.stopRecording()
  }

  private func twoTryExists(_ url: URL) -> Bool {
    FileManager.default.fileExists(atPath: url.path)
  }

  private func twoTryWait(_ predicate: @MainActor () -> Bool) async {
    let deadline = ContinuousClock.now + .seconds(2)
    while !predicate() && ContinuousClock.now < deadline { await Task.yield() }
    XCTAssertTrue(predicate())
  }
}

#if DEBUG
  @MainActor
  extension DirectPracticeSessionTests {
    func testTwoTakeFileOnlyCloseWithFailedCameraInBothRecoveryOrders() async throws {
      for cameraFirst in [false, true] {
        let fixture = try DirectOwnedFixture()
        defer { fixture.removeDirectory() }
        let files = ProcessAudioFileOwnership()
        let gate = AudioHardwareOwnership()
        let capturer = DirectConcreteCapturer(
          directory: fixture.directory, files: files, gate: gate)
        let camera = SessionMirrorFixture(cleanupFailures: 1)
        let session = DirectPracticeSession(
          capturer: capturer, player: DirectPracticePlayer(files: files, gate: gate),
          mirror: camera.mirror, cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
        session.appDidBecomeActive()
        await session.startRecording()
        session.stopRecording()
        let first = try XCTUnwrap(capturer.returnedRecording)
        await session.recordAnotherTry()
        session.stopRecording()
        let second = try XCTUnwrap(capturer.returnedRecording)
        let owners = Set([first, second].compactMap(\.cleanupOwnerID))
        XCTAssertEqual(owners.count, 2)
        session.showMirror()
        await twoTryWait {
          if case .live = camera.mirror.state { return true }
          return false
        }
        capturer.removal.failures = 10
        let firstClose = await session.end()
        XCTAssertFalse(firstClose)
        XCTAssertEqual(files.pendingCleanupOwners, owners)
        if cameraFirst {
          await session.retryMirrorStop()
          XCTAssertTrue(camera.mirror.isReleasedForClose)
          XCTAssertNotEqual(session.phase, .ended)  // Camera retry is not a second Close.
          let secondClose = await session.end()
          XCTAssertTrue(secondClose)
        } else {
          let secondClose = await session.end()  // Latched, still blocked by camera.
          XCTAssertFalse(secondClose)
          XCTAssertNotEqual(session.phase, .ended)
          await session.retryMirrorStop()
        }
        XCTAssertEqual(session.phase, .ended)
        XCTAssertEqual(files.pendingCleanupOwners, owners)
        XCTAssertTrue(FileManager.default.fileExists(atPath: first.url.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: second.url.path))
        XCTAssertEqual(session.completedWords, 0)
        capturer.removal.failures = 0
        for owner in owners { XCTAssertTrue(files.retryCleanup(owner: owner)) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: first.url.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: second.url.path))
      }
    }
  }
#endif

/// Owns an isolated directory, a process-ownership registry and one session per case.
@MainActor
private struct TwoTryHarness {
  let fixture: DirectOwnedFixture
  let files = ProcessAudioFileOwnership()
  let gate = AudioHardwareOwnership()
  let capturer: TwoTryCapturer
  let player: DirectPracticePlayer
  let history: PracticeParticipationStore
  let session: DirectPracticeSession

  init(oneWord: Bool = false) throws {
    fixture = try DirectOwnedFixture()
    capturer = TwoTryCapturer(directory: fixture.directory, files: files)
    player = DirectPracticePlayer(files: files, gate: gate)
    history = PracticeParticipationStore(
      fileURL: fixture.directory.appendingPathComponent("two-try-history.json"))
    var sound = PracticeLibrary.starterSound
    if oneWord {
      let last = try XCTUnwrap(PracticeLibrary.entries(soundID: "b", position: .beginning).last)
      sound = try XCTUnwrap(
        PracticeLibrary.session(soundID: "b", position: .beginning, startingAt: last.id))
    }
    session = DirectPracticeSession(
      sound: sound, capturer: capturer, player: player, history: history,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
  }
}

/// Multi-take controlled producer. Each start allocates a distinct small generated file with
/// its own owner in the isolated directory; actions are logged in order. Deletion is gated
/// by the shared process file registry, so a playback borrow refuses removal as in production.
@MainActor
private final class TwoTryCapturer: AudioCapturing {
  var startupAvailability = CaptureStartupAvailability.available
  enum Event: Equatable {
    case permission
    case start(Int)
    case stop(Int)
    case cancel
    case discard(Int)
  }
  var permissionGranted = true
  var holdsPermission = false
  var failStart = false
  var failRead = false
  var failStopHardware = false
  var failDiscardIndices: Set<Int> = []
  var nilOwnerIndices: Set<Int> = []
  var unregisteredIndices: Set<Int> = []
  // Synchronous reentry inside stop, after the file is complete and before it is returned.
  var duringStop: (@MainActor () -> Void)?
  var durations: [Double] = [0.4, 0.9, 1.3, 1.6, 1.8]
  var averagePower: Float = -20
  private(set) var events: [Event] = []
  private(set) var urls: [URL] = []
  private(set) var ownerIDs: [UUID] = []
  var permissionRequests: Int { events.filter { $0 == .permission }.count }
  var discardedIndices: [Int] {
    events.compactMap { event -> Int? in
      guard case .discard(let index) = event else { return nil }
      return index
    }
  }
  var permissionHeld: Bool { permissionContinuation != nil }
  private var permissionContinuation: CheckedContinuation<Bool, Never>?
  private var callbacks: [@MainActor (Bool) async -> Void] = []
  private var active: Int?
  private var hardwareBlocked: UUID?
  private var pendingFiles: Set<UUID> = []
  private var receipts: [UUID: CaptureCleanupReceipt] = [:]
  private let directory: URL
  private let files: ProcessAudioFileOwnership
  private let subject = CurrentValueSubject<CaptureCleanupState, Never>(.idle)
  var cleanupState: CaptureCleanupState { subject.value }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    subject.eraseToAnyPublisher()
  }

  init(directory: URL, files: ProcessAudioFileOwnership) {
    self.directory = directory
    self.files = files
  }

  func requestPermission() async -> Bool {
    events.append(.permission)
    guard holdsPermission else { return permissionGranted }
    return await withCheckedContinuation { permissionContinuation = $0 }
  }
  func resolvePermission(_ granted: Bool) {
    permissionContinuation?.resume(returning: granted)
    permissionContinuation = nil
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    if failStart { throw AudioCaptureError.couldNotStart }
    guard cleanupState == .idle, active == nil else { throw AudioCaptureError.hardwareBusy }
    let index = urls.count
    let url = directory.appendingPathComponent("two-try-\(index)-\(UUID().uuidString).wav")
    let owner = UUID()
    try Data("generated take \(index)".utf8).write(to: url)
    files.retain(url, owner: owner)
    urls.append(url)
    ownerIDs.append(owner)
    callbacks.append(onFinish)
    active = index
    events.append(.start(index))
  }
  func stop() throws -> CapturedRecording {
    guard let index = active else { throw AudioCaptureError.couldNotStart }
    events.append(.stop(index))
    if failStopHardware {
      hardwareBlocked = ownerIDs[index]
      publish()
      throw AudioCaptureError.hardwareCleanupUnconfirmed
    }
    active = nil
    if failRead {
      try? remove(index)
      throw AudioCaptureError.couldNotReadRecording
    }
    duringStop?()
    return CapturedRecording(
      url: urls[index],
      summary: CaptureSummary(duration: durations[index], averagePower: averagePower),
      cleanupOwnerID: nilOwnerIndices.contains(index) ? nil : ownerIDs[index])
  }
  func cancel() throws {
    events.append(.cancel)
    guard let index = active else { return }
    if hardwareBlocked != nil {
      publish()
      throw AudioCaptureError.hardwareCleanupUnconfirmed
    }
    active = nil
    try remove(index)
  }
  func discard(_ recording: CapturedRecording) throws {
    guard let index = urls.firstIndex(of: recording.url) else {
      throw AudioCaptureError.recordingNotOwned
    }
    events.append(.discard(index))
    guard index != active else { throw AudioCaptureError.recordingInUse }
    if failDiscardIndices.contains(index) {
      markPending(index)
      throw AudioCaptureError.couldNotDeleteTemporaryRecording
    }
    try remove(index)
  }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    guard let index = ownerIDs.firstIndex(of: operationID) else {
      return .init(operationID: operationID, result: .refused)
    }
    if hardwareBlocked == operationID {
      guard !failStopHardware else {
        return .init(operationID: operationID, result: .cleanupUnconfirmed)
      }
      hardwareBlocked = nil
      active = nil
      do { try remove(index) } catch {
        return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
      }
      return .init(operationID: operationID, result: .released)
    }
    guard pendingFiles.contains(operationID), !failDiscardIndices.contains(index) else {
      return .init(
        operationID: operationID,
        result: pendingFiles.contains(operationID) ? .hardwareReleasedFilesRetained : .refused)
    }
    do { try remove(index) } catch {
      return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
    }
    return .init(operationID: operationID, result: .released)
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? { receipts[operationID] }
  func finish(index: Int, successfully: Bool = true) async { await callbacks[index](successfully) }

  private func remove(_ index: Int) throws {
    let url = urls[index]
    let owner = ownerIDs[index]
    guard files.canRemove(url, owner: owner) else {
      markPending(index)
      throw AudioCaptureError.recordingInUse
    }
    if FileManager.default.fileExists(atPath: url.path) {
      try FileManager.default.removeItem(at: url)
    }
    files.didRemove(url, owner: owner)
    pendingFiles.remove(owner)
    // Commit the receipt before publishing, as the concrete producer does.
    receipts[owner] = .init(operationID: owner, result: .released)
    publish()
  }
  private func markPending(_ index: Int) {
    let owner = ownerIDs[index]
    pendingFiles.insert(owner)
    if !unregisteredIndices.contains(index), !nilOwnerIndices.contains(index),
      !files.pendingCleanupOwners.contains(owner)
    {
      _ = files.registerCleanupRecovery(owner: owner) { [self] in
        retryCleanup(operationID: owner).allRequestedFilesRemoved
      }
    }
    publish()
  }
  private func publish() {
    let next = CaptureCleanupState(
      hardwareBlockedOperationID: hardwareBlocked, fileBlockedOwnerIDs: pendingFiles)
    if subject.value != next { subject.send(next) }
  }
}

// Generated integration checks: the recognizer below uses continuations and exact process
// file borrows. It never constructs Speech, requests sensors, plays audio or calls a service.
@MainActor
extension DirectPracticeSessionTests {
  func testLocalWordCheckIsExplicitAndRecordingOrReplayNeverStartsIt() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    await h.session.startRecording()
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    h.session.stopRecording()
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    await h.session.togglePlayback()
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    await h.session.togglePlayback()
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertEqual(h.capturer.urls.count, 1)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
  }

  func testLocalWordCheckBindsOnlyLatestExactTakeAndPreservesBothRecordings() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let earlier = try XCTUnwrap(h.session.latestTry)
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    let latest = try XCTUnwrap(h.session.latestTry)
    let earlierBytes = try Data(contentsOf: h.capturer.urls[0])
    let latestBytes = try Data(contentsOf: h.capturer.urls[1])
    let events = h.capturer.events
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    XCTAssertEqual(request.tryID, latest.id)
    XCTAssertNotEqual(request.tryID, earlier.id)
    XCTAssertEqual(request.fileURL, h.capturer.urls[1])
    XCTAssertEqual(request.expectedWord, h.session.currentPrompt.word)
    XCTAssertEqual(h.session.checkedTryID, latest.id)
    XCTAssertEqual(h.session.wordCheckState, .checking)
    XCTAssertFalse(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[1]))
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.matched))
    XCTAssertEqual(h.session.checkedTryID, latest.id)
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    XCTAssertEqual(h.capturer.events, events)
    XCTAssertEqual(try Data(contentsOf: h.capturer.urls[0]), earlierBytes)
    XCTAssertEqual(try Data(contentsOf: h.capturer.urls[1]), latestBytes)
    XCTAssertEqual(h.session.completedWords, 0)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
  }

  func testLocalWordCheckPendingGatesDuplicateCaptureAndPlaybackRequests() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let take = try XCTUnwrap(h.session.latestTry)
    let events = h.capturer.events
    let checking = Task { await h.session.startWordCheck() }
    _ = try await h.recognizer.waitForRequest(index: 0)
    XCTAssertTrue(h.session.actionsDisabled)
    XCTAssertTrue(h.session.interactiveDismissDisabled)
    XCTAssertFalse(h.session.canRetry)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    await h.session.startWordCheck()
    await h.session.startRecording()
    await h.session.recordAnotherTry()
    await h.session.togglePlayback()
    await h.session.togglePlayback(tryID: take.id)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.capturer.events, events)
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    h.recognizer.resolve(index: 0, status: .uncertain)
    await checking.value
    XCTAssertFalse(h.session.actionsDisabled)
    XCTAssertEqual(h.session.wordCheckState, .finished(.uncertain))
    let ended = await h.session.end()
    XCTAssertTrue(ended)
  }

  func testTimedOutWordCheckKeepsExplicitReplayReplacementAndCloseAvailable() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let take = try XCTUnwrap(h.session.latestTry)
    let checking = Task { await h.session.startWordCheck() }
    let request = try await timeoutRequest(checking, recognizer: h.recognizer, index: 0)
    h.recognizer.resolve(index: 0, status: .timedOut)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.timedOut))
    XCTAssertEqual(h.session.checkedTryID, take.id)
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertEqual(h.recognizer.requests.count, 1, "Timeout must not start a retry.")
    let events = h.capturer.events
    let retry = Task { await h.session.startWordCheck() }
    let retryRequest = try await timeoutRequest(retry, recognizer: h.recognizer, index: 1)
    XCTAssertNotEqual(retryRequest.operationID, request.operationID)
    XCTAssertEqual(retryRequest.tryID, request.tryID)
    XCTAssertEqual(retryRequest.fileURL, request.fileURL)
    XCTAssertEqual(retryRequest.expectedWord, request.expectedWord)
    await h.session.startWordCheck()
    XCTAssertEqual(h.recognizer.requests.count, 2, "A held retry must not start a sibling.")
    h.recognizer.resolve(index: 1, status: .timedOut)
    await retry.value
    XCTAssertEqual(h.recognizer.requests.count, 2, "A second timeout must not start a third check.")
    XCTAssertEqual(h.session.wordCheckState, .finished(.timedOut))
    XCTAssertEqual(h.capturer.events, events)
    await h.session.togglePlayback()
    XCTAssertEqual(h.session.playingTryID, take.id)
    await h.session.togglePlayback()
    XCTAssertTrue(h.session.canRecordAnotherTry)
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    XCTAssertNotEqual(h.session.latestTry?.id, take.id)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertEqual(h.recognizer.requests.count, 2)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
  }

  func testLocalWordCancellationKeepsTakeProtectedUntilExactReceiptAndSuppressesLateMatch()
    async throws
  {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    h.session.cancelWordCheck()
    XCTAssertEqual(h.recognizer.cancellations, [request.operationID])
    XCTAssertEqual(h.session.wordCheckState, .cancelling)
    XCTAssertTrue(h.session.actionsDisabled)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertFalse(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[0]))
    await h.session.startWordCheck()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.cancelled))
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
    XCTAssertTrue(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[0]))
    let ended = await h.session.end()
    XCTAssertTrue(ended)
  }

  func testLocalWordCloseJoinsExactCleanupBeforeProducerDiscardAndNeverPublishesLateMatch()
    async throws
  {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    var closeReturned = false
    let closing = Task {
      let ended = await h.session.end()
      closeReturned = true
      return ended
    }
    await h.recognizer.waitForCancellation(index: 0)
    XCTAssertFalse(closeReturned)
    XCTAssertNotEqual(h.session.phase, .ended)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertTrue(h.session.interactiveDismissDisabled)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertFalse(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[0]))
    XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    let ended = await closing.value
    XCTAssertTrue(ended)
    XCTAssertTrue(closeReturned)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertFalse(FileManager.default.fileExists(atPath: request.fileURL.path))
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertEqual(h.session.completedWords, 0)
  }

  func testLocalWordSiblingReceiptCannotAuthorizeDeletionOrResetStickyCleanup() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let earlier = try XCTUnwrap(h.session.latestTry)
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    let sibling = LocalWordRecognitionRequest(
      operationID: request.operationID, tryID: earlier.id, fileURL: h.capturer.urls[0],
      expectedWord: request.expectedWord)
    h.recognizer.resolve(index: 0, status: .matched, receiptRequest: sibling)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
    XCTAssertTrue(h.session.cleanupBlocked)
    XCTAssertFalse(h.session.canRetryCleanup)
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    let firstClose = await h.session.end()
    let secondClose = await h.session.end()
    await h.session.retryCleanup()
    await h.session.restart()
    await h.session.startRecording()
    await h.session.startWordCheck()
    XCTAssertFalse(firstClose)
    XCTAssertFalse(secondClose)
    XCTAssertNotEqual(h.session.phase, .ended)
    XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertEqual(h.capturer.urls.count, 2)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertFalse(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[1]))
    for url in h.capturer.urls { XCTAssertTrue(FileManager.default.fileExists(atPath: url.path)) }
  }

  func testLocalWordUnconfirmedCleanupStaysBlockedAfterExternalBorrowRelease() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .cancelled, cleanupConfirmed: false)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
    XCTAssertTrue(h.session.cleanupBlocked)
    XCTAssertFalse(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[0]))
    // Physical release elsewhere is not an exact terminal receipt to this consumer.
    h.recognizer.releaseGeneratedBorrows()
    XCTAssertTrue(h.files.canRemove(request.fileURL, owner: h.capturer.ownerIDs[0]))
    await h.session.retryCleanup()
    await h.session.retry()
    await h.session.togglePlayback()
    await h.session.startWordCheck()
    let firstClose = await h.session.end()
    let secondClose = await h.session.end()
    XCTAssertFalse(firstClose)
    XCTAssertFalse(secondClose)
    XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
    XCTAssertTrue(h.session.interactiveDismissDisabled)
    XCTAssertFalse(h.session.canRetryCleanup)
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
  }

  func testLocalWordNewTakeClearsPriorResultAndNeedsAnotherExplicitCheck() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let firstCheck = Task { await h.session.startWordCheck() }
    let firstRequest = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .matched)
    await firstCheck.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.matched))
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.session.phase, .recording)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    h.session.stopRecording()
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    let secondCheck = Task { await h.session.startWordCheck() }
    let secondRequest = try await h.recognizer.waitForRequest(index: 1)
    XCTAssertNotEqual(secondRequest.operationID, firstRequest.operationID)
    XCTAssertNotEqual(secondRequest.tryID, firstRequest.tryID)
    XCTAssertNotEqual(secondRequest.fileURL, firstRequest.fileURL)
    XCTAssertEqual(secondRequest.fileURL, h.capturer.urls[1])
    h.recognizer.resolve(index: 1, status: .notMatched)
    await secondCheck.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.notMatched))
    XCTAssertEqual(h.session.checkedTryID, secondRequest.tryID)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
  }

  func testLocalWordCheckingPublicationReentrantCloseCancelsBeforeRecognizerWork() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    h.recognizer.honorsAlreadyCancelledTask = true
    await h.record()
    var requestedClose = false
    let subscription = h.session.$wordCheckState.sink { state in
      MainActor.assumeIsolated {
        guard state == .checking, !requestedClose else { return }
        requestedClose = true
        h.session.viewDidDisappear()
      }
    }
    defer { subscription.cancel() }
    await h.session.startWordCheck()
    await settle(h.session)
    XCTAssertTrue(requestedClose)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    let request = try XCTUnwrap(h.recognizer.requests.first)
    XCTAssertEqual(h.recognizer.cancellations.first, request.operationID)
    XCTAssertEqual(h.recognizer.workCount, 0)
    XCTAssertEqual(h.recognizer.alreadyCancelledCount, 1)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: request.fileURL.path))
  }
}

@MainActor
private struct LocalWordSessionHarness {
  let fixture: DirectOwnedFixture
  let files = ProcessAudioFileOwnership()
  let gate = AudioHardwareOwnership()
  let capturer: TwoTryCapturer
  let player: DirectPracticePlayer
  let recognizer: DirectControlledWordRecognizer
  let provider: any LocalWordRecognizing
  let history: PracticeParticipationStore?
  let session: DirectPracticeSession

  init(singleWord: Bool = false, allowsTimedOutRetry: Bool = true, recordHistory: Bool = false) throws {
    fixture = try DirectOwnedFixture()
    capturer = TwoTryCapturer(directory: fixture.directory, files: files)
    player = DirectPracticePlayer(files: files, gate: gate)
    recognizer = DirectControlledWordRecognizer(files: files)
    provider = allowsTimedOutRetry
      ? recognizer : TimedOutRetryExcludedRecognizer(base: recognizer)
    history = recordHistory
      ? PracticeParticipationStore(fileURL: fixture.directory.appendingPathComponent("word-history.json"))
      : nil
    let starter = PracticeLibrary.starterSound
    let sound = singleWord
      ? PracticeSound(id: starter.id, symbol: starter.symbol, name: starter.name,
          position: starter.position, prompts: Array(starter.prompts.prefix(1))) : starter
    session = DirectPracticeSession(
      sound: sound, capturer: capturer, player: player, history: history, wordRecognizer: provider,
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
  }

  func record() async {
    await session.startRecording()
    session.stopRecording()
  }

  func removeGeneratedFixture() {
    recognizer.releaseGeneratedBorrows()
    fixture.removeDirectory()
  }
}

@MainActor
private final class TimedOutRetryExcludedRecognizer: LocalWordRecognizing {
  let base: DirectControlledWordRecognizer
  var allowsTimedOutRetry: Bool { false }
  init(base: DirectControlledWordRecognizer) { self.base = base }
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    await base.check(request: request)
  }
  func cancel(operationID: UUID) { base.cancel(operationID: operationID) }
}

/// Test-only worker control. A cancel request deliberately cannot complete its receipt.
@MainActor
private final class DirectControlledWordRecognizer: LocalWordRecognizing {
  var honorsAlreadyCancelledTask = false
  private(set) var requests: [LocalWordRecognitionRequest] = []
  private(set) var cancellations: [UUID] = []
  private(set) var workCount = 0
  private(set) var alreadyCancelledCount = 0
  private let files: ProcessAudioFileOwnership
  private var stoppedForTeardown = false
  private var borrows: Set<UUID> = []
  private var pending: [Int: CheckedContinuation<LocalWordRecognitionReceipt, Never>] = [:]
  private var requestWaiters: [Int: XCTestExpectation] = [:]
  private var cancellationWaiters: [Int: XCTestExpectation] = [:]

  init(files: ProcessAudioFileOwnership) { self.files = files }

  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    guard !stoppedForTeardown else {
      return .init(request: request, status: .cancelled, cleanupConfirmed: true)
    }
    let index = requests.count
    requests.append(request)
    if honorsAlreadyCancelledTask, Task.isCancelled {
      alreadyCancelledCount += 1
      requestWaiters.removeValue(forKey: index)?.fulfill()
      return .init(request: request, status: .cancelled, cleanupConfirmed: true)
    }
    workCount += 1
    XCTAssertTrue(files.borrow(request.fileURL, operation: request.operationID))
    borrows.insert(request.operationID)
    return await withCheckedContinuation { continuation in
      pending[index] = continuation
      requestWaiters.removeValue(forKey: index)?.fulfill()
    }
  }

  func cancel(operationID: UUID) {
    let index = cancellations.count
    cancellations.append(operationID)
    cancellationWaiters.removeValue(forKey: index)?.fulfill()
  }

  func waitForRequest(index: Int) async throws -> LocalWordRecognitionRequest {
    if requests.count <= index {
      let entered = XCTestExpectation(description: "generated local word check \(index) entered")
      requestWaiters[index] = entered
      let result = await XCTWaiter.fulfillment(of: [entered], timeout: 2)
      XCTAssertEqual(result, .completed)
    }
    return try XCTUnwrap(requests.indices.contains(index) ? requests[index] : nil)
  }

  func waitForCancellation(index: Int) async {
    if cancellations.count > index { return }
    let entered = XCTestExpectation(
      description: "generated local word cancellation \(index) requested")
    cancellationWaiters[index] = entered
    let result = await XCTWaiter.fulfillment(of: [entered], timeout: 2)
    XCTAssertEqual(result, .completed)
  }

  func resolve(
    index: Int, status: LocalWordRecognitionStatus, cleanupConfirmed: Bool = true,
    receiptRequest: LocalWordRecognitionRequest? = nil, wordGuess: LocalWordGuess? = nil
  ) {
    guard requests.indices.contains(index), let continuation = pending.removeValue(forKey: index)
    else { return XCTFail("Generated check has no pending exact continuation") }
    let request = requests[index]
    let reported = receiptRequest ?? request
    if cleanupConfirmed, reported == request {
      files.finishBorrowing(operation: request.operationID)
      borrows.remove(request.operationID)
    }
    continuation.resume(
      returning: .init(
        request: reported, status: status, cleanupConfirmed: cleanupConfirmed, wordGuess: wordGuess))
  }

  /// Explicit generated-fixture teardown; never revises an already returned receipt.
  func releaseGeneratedBorrows() {
    for operation in borrows { files.finishBorrowing(operation: operation) }
    borrows.removeAll()
    // Release every test-controlled hold if an earlier throwing assertion aborts a case.
    let held = pending
    pending.removeAll()
    for (index, continuation) in held {
      continuation.resume(
        returning: .init(
          request: requests[index], status: .cancelled, cleanupConfirmed: true))
    }
  }

  /// Failed admission waits must also prevent a late task from entering a new hold.
  func stopAndDrainGeneratedChecks() {
    stoppedForTeardown = true
    releaseGeneratedBorrows()
  }
}

// Generated managed-owner cases. Reuse the existing controlled producer, playback runtime
// and exact borrowed-file recognizer; no Speech, microphone or camera is started.
@MainActor
extension DirectPracticeSessionTests {
  func testGuidedOwnerPreparationIsInertCanonicalAndCannotUseOrdinaryShortcuts() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    await h.session.startRecording()
    await h.session.restart()
    await h.session.practiceMore()
    XCTAssertTrue(h.capturer.events.isEmpty)
    XCTAssertTrue(h.session.actionsDisabled)
    let entry = try XCTUnwrap(PracticeLibrary.entries(soundID: "zh").first)
    let visit = h.review(entry)
    let wrong = PracticeLibraryEntry(soundID: "b", position: entry.position, prompt: entry.prompt)
    let wrongPrepared = await h.session.prepareGuidedVisit(entry: wrong, visit: .review(visit))
    XCTAssertFalse(wrongPrepared)
    let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .review(visit))
    XCTAssertTrue(prepared)
    XCTAssertEqual(h.session.guidedMediaVisit, .review(visit))
    XCTAssertEqual(h.session.sound.id, "zh")
    XCTAssertEqual(h.session.sound.symbol, PracticeLibrary.sounds.first { $0.id == "zh" }?.symbol)
    XCTAssertEqual(h.session.sound.position, entry.position)
    XCTAssertEqual(h.session.sound.prompts, [entry.prompt])
    XCTAssertEqual(h.session.totalWords, 1)
    XCTAssertTrue(h.capturer.events.isEmpty)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.player.playedURLs.isEmpty)
    await h.session.restart()
    await h.session.practiceMore()
    XCTAssertEqual(h.session.guidedMediaVisit, .review(visit))
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertNil(h.session.nextPracticeSound)
    assertGuidedTrue(await h.leave(visit))
    XCTAssertNotEqual(h.session.phase, .ended)
    assertGuidedFalse(await h.prepare(entry, visit))
    let otherWorkflow = LocalGuidedReviewVisit(
      workflowID: UUID(), roundID: UUID(), visitID: UUID(), entryID: entry.id)
    assertGuidedFalse(await h.prepare(entry, otherWorkflow))
  }

  func testGuidedReviewFirstSubmissionPrecedesCheckingAndUnavailableCannotBeRetried() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("p-beginning-pig")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    let observation = GuidedOwnerObservation()
    let events = h.session.guidedReviewEvents.sink { event in
      MainActor.assumeIsolated { observation.receive(event) }
    }
    var checkingSawSubmission = false
    let states = h.session.$wordCheckState.sink { state in
      MainActor.assumeIsolated {
        if state == .checking { checkingSawSubmission = observation.submitted.count == 1 }
      }
    }
    defer {
      events.cancel()
      states.cancel()
    }
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    XCTAssertTrue(checkingSawSubmission)
    XCTAssertEqual(request.expectedWord, "pig")
    XCTAssertEqual(observation.submitted.first?.visit, visit)
    XCTAssertEqual(observation.submitted.first?.tryID, request.tryID)
    XCTAssertEqual(observation.submitted.first?.operationID, request.operationID)
    h.recognizer.resolve(index: 0, status: .unavailable)
    await checking.value
    XCTAssertEqual(observation.settled.count, 1)
    XCTAssertEqual(observation.settled.first?.status, .unavailable)
    XCTAssertEqual(observation.settled.first?.eligible, true)
    XCTAssertEqual(observation.settled.first?.cleanup, true)
    let take = h.session.latestTry
    await h.session.startWordCheck()
    await h.session.recordAnotherTry()
    await h.session.retry()
    await h.session.continuePractice()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.session.latestTry, take)
    XCTAssertEqual(h.session.attemptCount, 1)
    XCTAssertEqual(h.session.completedWords, 0)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await h.leave(visit))
    XCTAssertEqual(observation.submitted.count, 1)
    XCTAssertEqual(observation.settled.count, 1)
  }

  func testGuidedExplicitCancelledFirstSubmissionCannotBeReplacedOrCheckedAgain() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    let observation = GuidedOwnerObservation()
    let subscription = h.session.guidedReviewEvents.sink { event in
      MainActor.assumeIsolated { observation.receive(event) }
    }
    defer { subscription.cancel() }
    let checking = Task { await h.session.startWordCheck() }
    _ = try await h.recognizer.waitForRequest(index: 0)
    h.session.cancelWordCheck()
    XCTAssertTrue(observation.settled.isEmpty)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    XCTAssertEqual(observation.settled.first?.status, .cancelled)
    XCTAssertEqual(observation.settled.first?.cleanup, true)
    await h.session.startWordCheck()
    await h.session.recordAnotherTry()
    await h.session.retry()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.capturer.urls.count, 1)
    XCTAssertEqual(observation.submitted.count, 1)
    XCTAssertEqual(observation.settled.count, 1)
    assertGuidedTrue(await h.leave(visit))
    XCTAssertTrue(h.history.entries.isEmpty)
  }

  func testGuidedDepartureWaitsForHeldCheckThenReportsExactCancelledBeforeDiscard() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    let observation = GuidedOwnerObservation()
    let events = h.session.guidedReviewEvents.sink { event in
      MainActor.assumeIsolated { observation.receive(event) }
    }
    defer { events.cancel() }
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    let leaving = Task { await h.leave(visit) }
    await h.recognizer.waitForCancellation(index: 0)
    XCTAssertEqual(h.session.guidedMediaVisit, .review(visit))
    XCTAssertTrue(observation.settled.isEmpty)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
    XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
    let nextEntry = try h.entry("p-beginning-pig")
    let next = h.review(nextEntry)
    assertGuidedFalse(await h.prepare(nextEntry, next))
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    assertGuidedTrue(await leaving.value)
    XCTAssertEqual(observation.settled.first?.identity, observation.submitted.first)
    XCTAssertEqual(observation.settled.first?.status, .cancelled)
    XCTAssertEqual(observation.settled.first?.eligible, false)
    XCTAssertEqual(observation.settled.first?.cleanup, true)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertNil(h.session.guidedMediaVisit)
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await h.prepare(nextEntry, next))
    assertGuidedFalse(await h.leave(visit))
    await h.record()
    XCTAssertNotEqual(h.session.latestTry?.id, request.tryID)
    assertGuidedTrue(await h.leave(next))
  }

  func testGuidedUnknownAndSiblingReceiptsCannotDepartResetOrCreateTerminalObservation()
    async throws
  {
    for sibling in [false, true] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let entry = try h.entry("b-beginning-ball")
      let visit = h.review(entry)
      assertGuidedTrue(await h.prepare(entry, visit))
      await h.record()
      let observation = GuidedOwnerObservation()
      let events = h.session.guidedReviewEvents.sink { event in
        MainActor.assumeIsolated { observation.receive(event) }
      }
      defer { events.cancel() }
      let checking = Task { await h.session.startWordCheck() }
      let request = try await h.recognizer.waitForRequest(index: 0)
      let wrong = LocalWordRecognitionRequest(
        operationID: UUID(), tryID: request.tryID, fileURL: request.fileURL,
        expectedWord: request.expectedWord)
      h.recognizer.resolve(
        index: 0, status: .matched, cleanupConfirmed: sibling,
        receiptRequest: sibling ? wrong : nil)
      await checking.value
      XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
      XCTAssertEqual(observation.settled.count, 1)
      XCTAssertEqual(observation.settled.first?.identity, observation.submitted.first)
      XCTAssertEqual(observation.settled.first?.cleanup, false)
      XCTAssertEqual(observation.settled.first?.eligible, false)
      assertGuidedFalse(await h.leave(visit))
      XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
      h.recognizer.releaseGeneratedBorrows()
      await h.session.retryCleanup()
      assertGuidedFalse(await h.leave(visit))
      assertGuidedFalse(await h.prepare(entry, h.review(entry)))
      assertGuidedFalse(await h.session.end())
      XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
      XCTAssertEqual(observation.settled.count, 1)
    }
  }

  func testGuidedDepartureWaitsForPlaybackReleaseAndIgnoresOldCompletionOnSuccessor() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    h.player.holdPreparation = true
    h.player.holdCleanup = true
    let starting = Task { await h.session.togglePlayback() }
    let queued = await h.player.driver(0)
    let driver = try XCTUnwrap(queued)
    defer { driver.releaseAll() }
    await entered(driver.prepared)
    let stopping = XCTestExpectation(description: "guided departure revoked queued playback")
    var noted = false
    let states = h.session.$playbackState.sink { state in
      if case .stopping = state, !noted {
        noted = true
        stopping.fulfill()
      }
    }
    defer { states.cancel() }
    let leaving = Task { await h.leave(visit) }
    await entered(stopping)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertEqual(h.session.guidedMediaVisit, .review(visit))
    driver.releasePreparation()
    await entered(driver.cleaning)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    assertGuidedFalse(await h.prepare(entry, h.review(entry)))
    driver.releaseCleanup()
    await starting.value
    assertGuidedTrue(await leaving.value)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertTrue(h.history.entries.isEmpty)
    let nextEntry = try h.entry("m-beginning-moon")
    let next = h.review(nextEntry)
    assertGuidedTrue(await h.prepare(nextEntry, next))
    await h.record()
    let kept = h.session.latestTry
    h.player.deliverCapturedCompletion(index: 0, successfully: false)
    XCTAssertEqual(h.session.latestTry, kept)
    XCTAssertNil(h.session.playbackError)
    assertGuidedTrue(await h.leave(next))
  }

  func testGuidedOldPermissionCannotStartCaptureAfterExactDepartureAndNewPreparation() async throws
  {
    let fixture = try DirectOwnedFixture()
    defer { fixture.removeDirectory() }
    let files = ProcessAudioFileOwnership()
    let capturer = DirectPracticeCapturer(recordingDirectory: fixture.directory, files: files)
    capturer.holdsPermission = true
    let recognizer = DirectControlledWordRecognizer(files: files)
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(files: files),
      managedForGuided: true, wordRecognizer: recognizer)
    let entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == "b-beginning-ball" })
    let workflow = UUID()
    let first = LocalGuidedReviewVisit(
      workflowID: workflow, roundID: UUID(), visitID: UUID(), entryID: entry.id)
    let firstPrepared = await session.prepareGuidedVisit(entry: entry, visit: .review(first))
    XCTAssertTrue(firstPrepared)
    let starting = Task { await session.startRecording() }
    await capturer.waitForPermissionRequest()
    let departed = await session.leaveGuidedVisit(.review(first))
    XCTAssertTrue(departed)
    let second = LocalGuidedReviewVisit(
      workflowID: workflow, roundID: first.roundID, visitID: UUID(), entryID: entry.id)
    let secondPrepared = await session.prepareGuidedVisit(entry: entry, visit: .review(second))
    XCTAssertTrue(secondPrepared)
    capturer.resolvePermission(true)
    await starting.value
    XCTAssertEqual(capturer.startCount, 0)
    XCTAssertEqual(session.guidedMediaVisit, .review(second))
    XCTAssertEqual(session.phase, .ready)
    XCTAssertTrue(session.tries.isEmpty)
    XCTAssertTrue(recognizer.requests.isEmpty)
    let ended = await session.end()
    XCTAssertTrue(ended)
  }

  func testGuidedCaptureCleanupFailureNeedsExactRecoveryBeforeDeparture() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.session.startRecording()
    h.capturer.failStopHardware = true
    h.session.stopRecording()
    await settle(h.session)
    XCTAssertTrue(h.session.captureCleanupState.hasHardwareIssue)
    assertGuidedFalse(await h.leave(visit))
    XCTAssertEqual(h.session.guidedMediaVisit, .review(visit))
    assertGuidedFalse(await h.prepare(entry, h.review(entry)))
    XCTAssertTrue(h.history.entries.isEmpty)
    h.capturer.failStopHardware = false
    await h.session.retryCleanup()
    XCTAssertFalse(h.session.cleanupBlocked)
    assertGuidedTrue(await h.leave(visit))
    XCTAssertNil(h.session.guidedMediaVisit)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
  }

  func testGuidedPracticeRequiresFreshAcceptableTakeAndSavesOnlyExactCanonicalVisit() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try XCTUnwrap(PracticeLibrary.entries(soundID: "zh").first)
    let visit = h.practice(entry)
    let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .practice(visit))
    XCTAssertTrue(prepared)
    let empty = await h.session.finishGuidedPractice(visit)
    XCTAssertNil(empty.completionID)
    await h.record()
    let tooShort = await h.session.finishGuidedPractice(visit)
    XCTAssertNil(tooShort.completionID)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    let fresh = try XCTUnwrap(h.session.latestTry?.id)
    // No manual check: ordinary practice participation remains independent of recognition.
    await h.session.continuePractice()
    await h.session.restart()
    await h.session.practiceMore()
    XCTAssertEqual(h.session.latestTry?.id, fresh)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    let result = await h.session.finishGuidedPractice(visit)
    XCTAssertEqual(result.visit, visit)
    XCTAssertEqual(result.freshTryID, fresh)
    XCTAssertTrue(result.cleanupConfirmed)
    XCTAssertTrue(result.saveConfirmed)
    XCTAssertEqual(result.completionID, visit.visitID)
    XCTAssertEqual(h.history.entries.count, 1)
    XCTAssertEqual(h.history.entries.first, h.session.participationCompletion)
    XCTAssertEqual(h.history.entries.first?.id, visit.visitID)
    XCTAssertEqual(h.history.entries.first?.soundID, "zh")
    XCTAssertEqual(h.history.entries.first?.wordCount, 1)
    XCTAssertEqual(h.capturer.discardedIndices, [0, 1])
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    let repeated = await h.session.finishGuidedPractice(visit)
    XCTAssertEqual(repeated, result)
    let wrong = h.practice(entry)
    let sibling = await h.session.finishGuidedPractice(wrong)
    XCTAssertNil(sibling.completionID)
    XCTAssertEqual(h.history.entries.count, 1)
    let left = await h.session.leaveGuidedVisit(.practice(visit))
    XCTAssertTrue(left)
    XCTAssertNotEqual(h.session.phase, .ended)
    let late = await h.session.finishGuidedPractice(visit)
    XCTAssertNil(late.completionID)
    XCTAssertEqual(h.history.entries.count, 1)
  }

  func testGuidedPracticeUnconfirmedSaveRetriesSameCompletionWithoutRecapture() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    try FileManager.default.createDirectory(at: h.historyURL, withIntermediateDirectories: true)
    let entry = try h.entry("t-beginning-tiger")
    let visit = h.practice(entry)
    let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .practice(visit))
    XCTAssertTrue(prepared)
    await h.recordValidPractice()
    let fresh = try XCTUnwrap(h.session.latestTry?.id)
    let unconfirmed = await h.session.finishGuidedPractice(visit)
    XCTAssertTrue(unconfirmed.cleanupConfirmed)
    XCTAssertFalse(unconfirmed.saveConfirmed)
    XCTAssertEqual(unconfirmed.completionID, visit.visitID)
    XCTAssertEqual(unconfirmed.freshTryID, fresh)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    let starts = h.capturer.urls.count
    try FileManager.default.removeItem(at: h.historyURL)
    h.session.retryParticipationSave()
    let saved = await h.session.finishGuidedPractice(visit)
    XCTAssertTrue(saved.saveConfirmed)
    XCTAssertEqual(saved.completionID, unconfirmed.completionID)
    XCTAssertEqual(saved.freshTryID, unconfirmed.freshTryID)
    XCTAssertEqual(h.capturer.urls.count, starts)
    XCTAssertEqual(h.history.entries.count, 1)
    XCTAssertEqual(h.history.entries.first, h.session.participationCompletion)
    h.session.retryParticipationSave()
    XCTAssertEqual(h.history.entries.count, 1)
    let left = await h.session.leaveGuidedVisit(.practice(visit))
    XCTAssertTrue(left)
    XCTAssertFalse(h.session.canRetryParticipationSave)
  }

  func testGuidedPreparationPublicationCloseWinsWithoutAllocatingAnyMedia() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("p-beginning-pig")
    let visit = h.review(entry)
    var closed = false
    let subscription = h.session.$sound.dropFirst().sink { _ in
      MainActor.assumeIsolated {
        guard !closed else { return }
        closed = true
        h.session.viewDidDisappear()
      }
    }
    defer { subscription.cancel() }
    assertGuidedFalse(await h.prepare(entry, visit))
    await settle(h.session)
    XCTAssertTrue(closed)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertNil(h.session.guidedMediaVisit)
    XCTAssertEqual(h.capturer.permissionRequests, 0)
    XCTAssertTrue(h.capturer.urls.isEmpty)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedFalse(await h.prepare(entry, h.review(entry)))
  }

  func testGuidedSubmittedPublicationCloseCancelsBeforeRecognizerWorkAndSettlesOnce() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    h.recognizer.honorsAlreadyCancelledTask = true
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    let observation = GuidedOwnerObservation()
    observation.onSubmission = { h.session.viewDidDisappear() }
    let subscription = h.session.guidedReviewEvents.sink { event in
      MainActor.assumeIsolated { observation.receive(event) }
    }
    defer { subscription.cancel() }
    await h.session.startWordCheck()
    await settle(h.session)
    XCTAssertEqual(observation.submitted.count, 1)
    XCTAssertEqual(observation.settled.count, 1)
    XCTAssertEqual(observation.settled.first?.identity, observation.submitted.first)
    XCTAssertEqual(observation.settled.first?.status, .cancelled)
    XCTAssertEqual(observation.settled.first?.eligible, false)
    XCTAssertEqual(observation.settled.first?.cleanup, true)
    XCTAssertEqual(h.recognizer.workCount, 0)
    XCTAssertEqual(h.recognizer.alreadyCancelledCount, 1)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
  }

  func testGuidedPracticeCompletionPublicationCloseCannotSaveOrReportFinishedVisit() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("d-beginning-dog")
    let visit = h.practice(entry)
    let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .practice(visit))
    XCTAssertTrue(prepared)
    await h.recordValidPractice()
    var closed = false
    let subscription = h.session.$completedWords.sink { count in
      MainActor.assumeIsolated {
        guard count > 0, !closed else { return }
        closed = true
        h.session.viewDidDisappear()
      }
    }
    defer { subscription.cancel() }
    let result = await h.session.finishGuidedPractice(visit)
    await settle(h.session)
    XCTAssertTrue(closed)
    XCTAssertNil(result.completionID)
    XCTAssertFalse(result.saveConfirmed)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
  }
  private func assertGuidedTrue(
    _ value: Bool, file: StaticString = #filePath, line: UInt = #line
  ) {
    XCTAssertTrue(value, file: file, line: line)
  }

  private func assertGuidedFalse(
    _ value: Bool, file: StaticString = #filePath, line: UInt = #line
  ) {
    XCTAssertFalse(value, file: file, line: line)
  }
}

@MainActor
private struct GuidedOwnerHarness {
  let fixture: DirectOwnedFixture
  let files = ProcessAudioFileOwnership()
  let gate = AudioHardwareOwnership()
  let workflowID = UUID()
  let capturer: TwoTryCapturer
  let player: DirectPracticePlayer
  let recognizer: DirectControlledWordRecognizer
  let provider: any LocalWordRecognizing
  let historyURL: URL
  let history: PracticeParticipationStore
  let session: DirectPracticeSession

  init(allowsTimedOutRetry: Bool = true) throws {
    fixture = try DirectOwnedFixture()
    historyURL = fixture.directory.appendingPathComponent("guided-participation.json")
    history = PracticeParticipationStore(fileURL: historyURL)
    capturer = TwoTryCapturer(directory: fixture.directory, files: files)
    player = DirectPracticePlayer(files: files, gate: gate)
    recognizer = DirectControlledWordRecognizer(files: files)
    provider = allowsTimedOutRetry
      ? recognizer : TimedOutRetryExcludedRecognizer(base: recognizer)
    session = DirectPracticeSession(
      capturer: capturer, player: player, history: history, managedForGuided: true,
      wordRecognizer: provider, cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
  }

  func entry(_ id: String) throws -> PracticeLibraryEntry {
    try XCTUnwrap(PracticeLibrary.entries().first { $0.id == id })
  }
  func review(_ entry: PracticeLibraryEntry) -> LocalGuidedReviewVisit {
    .init(workflowID: workflowID, roundID: UUID(), visitID: UUID(), entryID: entry.id)
  }
  func practice(_ entry: PracticeLibraryEntry) -> LocalGuidedPracticeVisit {
    .init(workflowID: workflowID, practiceID: UUID(), visitID: UUID(), entryID: entry.id)
  }
  func prepare(_ entry: PracticeLibraryEntry, _ visit: LocalGuidedReviewVisit) async -> Bool {
    await session.prepareGuidedVisit(entry: entry, visit: .review(visit))
  }
  func leave(_ visit: LocalGuidedReviewVisit) async -> Bool {
    await session.leaveGuidedVisit(.review(visit))
  }
  func record() async {
    await session.startRecording()
    session.stopRecording()
  }
  func recordValidPractice() async {
    await record()
    await session.recordAnotherTry()
    session.stopRecording()
  }
  func removeGeneratedFixture() {
    recognizer.releaseGeneratedBorrows()
    fixture.removeDirectory()
  }
}

@MainActor
private final class GuidedOwnerObservation {
  struct Settlement {
    let identity: LocalGuidedCheckIdentity
    let status: LocalWordRecognitionStatus
    let eligible: Bool
    let cleanup: Bool
  }
  private(set) var submitted: [LocalGuidedCheckIdentity] = []
  private(set) var settled: [Settlement] = []
  var onSubmission: (@MainActor () -> Void)?
  func receive(_ event: LocalGuidedReviewEvent) {
    switch event {
    case .submitted(let identity):
      submitted.append(identity)
      onSubmission?()
    case .settled(let identity, let status, let eligible, let cleanup):
      settled.append(
        .init(identity: identity, status: status, eligible: eligible, cleanup: cleanup))
    }
  }
}

// Generated coordinator cases exercise actual public actions across the shared owner.
@MainActor
extension DirectPracticeSessionTests {
  func testGuidedInterruptedPreparationRetriesExactVisitAfterAcknowledgedCleanup() async throws {
    for interruption in [false, true] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let entry = try h.entry("p-beginning-pig")
      let visit = h.review(entry)
      var revoked = false
      let subscription = h.session.$sound.dropFirst().sink { _ in
        MainActor.assumeIsolated {
          guard !revoked else { return }
          revoked = true
          if interruption {
            h.session.audioWasInterrupted()
          } else {
            h.session.appDidEnterBackground()
          }
        }
      }
      defer { subscription.cancel() }
      assertGuidedFalse(await h.prepare(entry, visit))
      await settle(h.session)
      XCTAssertTrue(revoked)
      XCTAssertNil(h.session.guidedMediaVisit)
      XCTAssertEqual(h.session.phase, .ready)
      XCTAssertEqual(h.capturer.permissionRequests, 0)
      XCTAssertTrue(h.capturer.urls.isEmpty)
      assertGuidedTrue(await h.prepare(entry, visit))
      XCTAssertEqual(h.session.guidedMediaVisit, .review(visit))
      XCTAssertEqual(h.session.currentPrompt, entry.prompt)
      XCTAssertEqual(h.session.totalWords, 1)
      XCTAssertEqual(h.capturer.permissionRequests, 0)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      XCTAssertTrue(h.player.playedURLs.isEmpty)
      XCTAssertTrue(h.history.entries.isEmpty)
      assertGuidedTrue(await h.leave(visit))
      // Successful preparation still consumes the identity, even with no media allocated.
      assertGuidedFalse(await h.prepare(entry, visit))
    }
  }

  func testGuidedCoordinatorFiveReviewSkipsChosenActualSoundsAndFreshSameFiveRecheck() async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    let originalEntries = flow.setupEntries
    XCTAssertTrue(flow.practiceSelectionIDs.isEmpty)
    await flow.startInitialReview()
    for entry in originalEntries {
      XCTAssertEqual(flow.ledger?.activeReviewVisit?.entryID, entry.id)
      XCTAssertEqual(flow.media.currentPrompt, entry.prompt)
      await flow.skipVisit()
    }
    let initial = try XCTUnwrap(flow.ledger?.initialRound)
    XCTAssertTrue(initial.isFinished)
    XCTAssertEqual(initial.rows.map(\.state), Array(repeating: .finished(.skipped), count: 5))
    XCTAssertTrue(initial.rows.allSatisfy { $0.firstSubmission == nil })
    XCTAssertEqual(flow.ledger?.stage, .choosingPractice)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.capturer.urls.isEmpty)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(flow.practiceSelectionIDs.isEmpty)
    let pig = try h.entry("p-beginning-pig")
    let dog = try h.entry("d-beginning-dog")
    flow.togglePracticeSelection(entryID: pig.id)
    flow.togglePracticeSelection(entryID: dog.id)
    XCTAssertEqual(flow.practiceSelectionIDs, [pig.id, dog.id])
    await flow.startPractice()
    var practiceVisits: [LocalGuidedPracticeVisit] = []
    var keptIDs: [UUID] = []
    for entry in [pig, dog] {
      let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
      practiceVisits.append(visit)
      XCTAssertEqual(visit.entryID, entry.id)
      XCTAssertEqual(flow.media.sound.id, entry.soundID)
      XCTAssertEqual(flow.media.sound.position, entry.position)
      XCTAssertEqual(flow.media.sound.prompts, [entry.prompt])
      XCTAssertTrue(flow.media === h.session)
      XCTAssertEqual(
        flow.playerPresentation.firstObservationNote,
        "First review: Skipped. Word checks cannot identify which sound was made.")
      await h.recordValidPractice()
      keptIDs.append(try XCTUnwrap(h.session.latestTry?.id))
      await flow.advanceVisit()
      XCTAssertEqual(flow.ledger?.initialRound, initial)
    }
    XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
    XCTAssertEqual(flow.ledger?.practiceRows.map { $0.entry.id }, [pig.id, dog.id])
    XCTAssertEqual(
      flow.ledger?.practiceRows.map(\.state), [.finished(.finished), .finished(.finished)])
    XCTAssertEqual(flow.ledger?.practiceRows.compactMap(\.freshTryID), keptIDs)
    XCTAssertEqual(Set(h.history.entries.map(\.id)), Set(practiceVisits.map(\.visitID)))
    XCTAssertEqual(Set(h.history.entries.map(\.soundID)), ["p", "d"])
    XCTAssertTrue(h.history.entries.allSatisfy { $0.wordCount == 1 })
    let saved = h.history.entries
    let captureCount = h.capturer.urls.count
    await flow.startRecheck()
    let recheckID = try XCTUnwrap(flow.ledger?.recheckRound?.id)
    XCTAssertNotEqual(recheckID, initial.id)
    var recheckVisits: [UUID] = []
    for entry in originalEntries {
      let visit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
      recheckVisits.append(visit.visitID)
      XCTAssertEqual(visit.roundID, recheckID)
      XCTAssertEqual(visit.entryID, entry.id)
      XCTAssertEqual(flow.media.currentPrompt, entry.prompt)
      XCTAssertEqual(
        flow.playerPresentation.firstObservationNote,
        "First review: Skipped. Word checks cannot identify which sound was made.")
      await flow.skipVisit()
    }
    XCTAssertEqual(flow.ledger?.stage, .completed)
    XCTAssertEqual(flow.ledger?.initialRound, initial)
    XCTAssertEqual(flow.ledger?.recheckRound?.rows.map { $0.entry.id }, originalEntries.map(\.id))
    XCTAssertEqual(flow.ledger?.pairedRows.map { $0.initial }, initial.rows)
    XCTAssertEqual(
      flow.ledger?.pairedRows.map { $0.recheck.state },
      Array(repeating: .finished(.skipped), count: 5))
    XCTAssertTrue(
      Set(recheckVisits).isDisjoint(with: initial.rows.compactMap { $0.visit?.visitID }))
    XCTAssertTrue(Set(recheckVisits).isDisjoint(with: practiceVisits.map(\.visitID)))
    XCTAssertEqual(h.history.entries, saved)
    XCTAssertEqual(h.capturer.urls.count, captureCount)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(flow.media === h.session)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedCoordinatorUnavailableFirstCheckIsFrozenAndNextUsesCanonicalSuccessor()
    async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    let firstVisit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
    await h.record()
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .unavailable)
    await checking.value
    let first = try XCTUnwrap(flow.ledger?.initialRound.rows.first)
    XCTAssertEqual(first.state, .finished(.unavailable))
    XCTAssertEqual(first.firstSubmission?.visit, firstVisit)
    XCTAssertEqual(first.firstSubmission?.operationID, request.operationID)
    await flow.checkCurrentWord()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    await flow.advanceVisit()
    let second = try XCTUnwrap(flow.ledger?.activeReviewVisit)
    XCTAssertEqual(second.entryID, "p-beginning-pig")
    XCTAssertNotEqual(second.visitID, firstVisit.visitID)
    XCTAssertEqual(second.roundID, firstVisit.roundID)
    XCTAssertEqual(flow.media.sound.id, "p")
    XCTAssertEqual(flow.media.currentPrompt.word, "pig")
    XCTAssertEqual(flow.media.totalWords, 1)
    XCTAssertEqual(flow.media.completedWords, 0)
    XCTAssertEqual(flow.media.attemptCount, 0)
    XCTAssertTrue(flow.media.tries.isEmpty)
    XCTAssertEqual(flow.ledger?.initialRound.rows.first, first)
    XCTAssertEqual(flow.ledger?.initialRound.rows[1].state, .ready)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedCoordinatorBackgroundJoinsFirstCheckThenRequiresNextBeforeRecording()
    async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    let firstVisit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
    XCTAssertTrue(h.session.canStartRecording)
    await h.record()
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    let submission = try XCTUnwrap(flow.ledger?.initialRound.rows.first?.firstSubmission)
    XCTAssertEqual(submission.visit, firstVisit)
    XCTAssertEqual(submission.operationID, request.operationID)
    XCTAssertEqual(submission.tryID, request.tryID)

    // Inactive can already cancel; background may repeat cancellation for this same operation.
    flow.sceneInactive()
    flow.background()
    flow.sceneActive()
    await h.recognizer.waitForCancellation(index: 0)
    XCTAssertTrue(h.session.isTransitioning)
    XCTAssertFalse(h.session.canStartRecording)
    XCTAssertEqual(h.session.wordCheckState, .cancelling)
    XCTAssertEqual(flow.ledger?.activeReviewVisit, firstVisit)
    XCTAssertEqual(flow.ledger?.initialRound.rows.first?.state, .pending)
    XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
    XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)

    // A late match cannot revive the cancelled first submission after its transition changed.
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    await settle(h.session)
    let first = try XCTUnwrap(flow.ledger?.initialRound.rows.first)
    XCTAssertEqual(first.state, .finished(.cancelled))
    XCTAssertEqual(first.firstSubmission, submission)
    XCTAssertEqual(flow.ledger?.activeReviewVisit, firstVisit)
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertTrue(h.session.tries.isEmpty)
    XCTAssertFalse(h.session.canStartRecording)
    XCTAssertFalse(flow.playerPresentation.canCheckWords)
    XCTAssertTrue(flow.playerPresentation.canContinue)
    XCTAssertFalse(flow.isClosed)
    XCTAssertFalse(h.session.closeRequested)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertFalse(FileManager.default.fileExists(atPath: request.fileURL.path))
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertFalse(h.recognizer.cancellations.isEmpty)
    XCTAssertTrue(h.recognizer.cancellations.allSatisfy { $0 == request.operationID })

    let permissions = h.capturer.permissionRequests
    let filesCreated = h.capturer.urls.count
    await h.session.startRecording()
    await flow.checkCurrentWord()
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    XCTAssertEqual(h.capturer.urls.count, filesCreated)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(flow.ledger?.initialRound.rows.first, first)

    await flow.advanceVisit()
    let next = try XCTUnwrap(flow.ledger?.activeReviewVisit)
    XCTAssertNotEqual(next.visitID, firstVisit.visitID)
    XCTAssertEqual(next.roundID, firstVisit.roundID)
    XCTAssertEqual(next.entryID, "p-beginning-pig")
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertTrue(h.session.canStartRecording)
    XCTAssertTrue(h.session.tries.isEmpty)
    XCTAssertEqual(flow.ledger?.initialRound.rows[1].state, .ready)
    XCTAssertEqual(flow.ledger?.initialRound.rows.first, first)
    XCTAssertEqual(h.capturer.permissionRequests, permissions)
    XCTAssertEqual(h.capturer.urls.count, filesCreated)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
  }

  func testGuidedCoordinatorTimedOutFirstCheckKeepsTakeAndAllowsManualProgress() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    await h.record()
    let take = try XCTUnwrap(h.session.latestTry)
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .timedOut)
    await checking.value
    let first = try XCTUnwrap(flow.ledger?.initialRound.rows.first)
    XCTAssertEqual(first.state, .finished(.timedOut))
    XCTAssertEqual(first.firstSubmission?.operationID, request.operationID)
    XCTAssertEqual(first.firstSubmission?.tryID, take.id)
    XCTAssertEqual(h.session.wordCheckState, .finished(.timedOut))
    XCTAssertEqual(h.session.checkedTryID, take.id)
    XCTAssertEqual(h.session.latestTry?.id, take.id)
    XCTAssertFalse(flow.playerPresentation.canCheckWords)
    XCTAssertTrue(flow.playerPresentation.canContinue)
    XCTAssertTrue(flow.playerPresentation.canFinishStage)
    await flow.checkCurrentWord()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    await h.session.togglePlayback()
    XCTAssertEqual(h.session.playingTryID, take.id)
    await h.session.togglePlayback()
    XCTAssertEqual(h.session.wordCheckState, .finished(.timedOut))
    XCTAssertEqual(h.recognizer.requests.count, 1)
    await flow.advanceVisit()
    XCTAssertEqual(flow.ledger?.initialRound.rows.first, first)
    XCTAssertEqual(flow.ledger?.activeReviewVisit?.entryID, "p-beginning-pig")
    XCTAssertTrue(flow.playerPresentation.canSkip)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertEqual(h.recognizer.requests.count, 1)
  }

  func testGuidedCoordinatorFinishPendingReviewWaitsThenKeepsCancelledAndUnreachedRows()
    async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    await h.record()
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    let finishing = Task { await flow.finishStageNow() }
    await h.recognizer.waitForCancellation(index: 0)
    XCTAssertTrue(flow.isTransitioning)
    XCTAssertEqual(flow.ledger?.stage, .initialReview)
    XCTAssertEqual(flow.ledger?.initialRound.rows.first?.state, .pending)
    XCTAssertEqual(flow.ledger?.initialRound.isFinished, false)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
    XCTAssertTrue(h.history.entries.isEmpty)
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    await finishing.value
    XCTAssertFalse(flow.isTransitioning)
    XCTAssertEqual(flow.ledger?.stage, .choosingPractice)
    XCTAssertEqual(flow.ledger?.initialRound.isFinished, true)
    XCTAssertEqual(
      flow.ledger?.initialRound.rows.map(\.state),
      [
        .finished(.cancelled), .finished(.unreached), .finished(.unreached),
        .finished(.unreached), .finished(.unreached),
      ])
    XCTAssertEqual(
      flow.ledger?.initialRound.rows.first?.firstSubmission?.operationID, request.operationID)
    XCTAssertNil(flow.ledger?.activeReviewVisit)
    XCTAssertTrue(flow.practiceSelectionIDs.isEmpty)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedCoordinatorDuplicateCloseJoinsHeldExactReceiptBeforeClosedPermission() async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    await h.record()
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    let firstClose = Task { await flow.close() }
    await h.recognizer.waitForCancellation(index: 0)
    let joined = XCTestExpectation(description: "second Close entered while exact receipt is held")
    let secondClose = Task {
      joined.fulfill()
      return await flow.close()
    }
    await entered(joined)
    XCTAssertFalse(flow.isClosed)
    XCTAssertTrue(flow.isTransitioning)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.recognizer.cancellations.count, 1)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
    XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
    XCTAssertTrue(h.history.entries.isEmpty)
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    assertGuidedTrue(await firstClose.value)
    assertGuidedTrue(await secondClose.value)
    XCTAssertTrue(flow.isClosed)
    XCTAssertFalse(flow.isTransitioning)
    XCTAssertEqual(flow.media.phase, .ended)
    XCTAssertEqual(flow.ledger?.initialRound.rows.first?.state, .finished(.cancelled))
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.capturer.discardedIndices, [0])
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
  }

  func testGuidedCoordinatorBackgroundAtUnopenedStageBoundariesRetriesFrozenNextWordInertly()
    async throws
  {
    enum Boundary { case initial, practice, recheck, nextWord }
    for boundary in [Boundary.initial, .practice, .recheck, .nextWord] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
      let original = flow.setupEntries
      let pig = try h.entry("p-beginning-pig")
      let expectedStage: LocalGuidedReviewStage
      let expectedEntry: PracticeLibraryEntry
      switch boundary {
      case .initial:
        expectedStage = .initialReview
        expectedEntry = original[0]
      case .practice:
        await flow.startInitialReview()
        await flow.finishStageNow()
        flow.togglePracticeSelection(entryID: pig.id)
        expectedStage = .practice
        expectedEntry = pig
      case .recheck:
        await flow.startInitialReview()
        await flow.finishStageNow()
        flow.togglePracticeSelection(entryID: pig.id)
        await flow.startPractice()
        await flow.skipVisit()
        expectedStage = .recheck
        expectedEntry = original[0]
      case .nextWord:
        await flow.startInitialReview()
        expectedStage = .initialReview
        expectedEntry = original[1]
      }
      let initialBefore = flow.ledger?.initialRound
      var revoked = false
      let subscription = flow.$ledger.dropFirst().sink { upcoming in
        MainActor.assumeIsolated {
          guard !revoked, let upcoming, upcoming.stage == expectedStage,
            upcoming.activeReviewVisit == nil, upcoming.activePracticeVisit == nil
          else { return }
          revoked = true
          flow.background()
        }
      }
      defer { subscription.cancel() }
      switch boundary {
      case .initial: await flow.startInitialReview()
      case .practice: await flow.startPractice()
      case .recheck: await flow.startRecheck()
      case .nextWord: await flow.skipVisit()
      }
      await settle(h.session)
      XCTAssertTrue(revoked)
      XCTAssertFalse(flow.isTransitioning)
      XCTAssertEqual(flow.ledger?.stage, expectedStage)
      XCTAssertNil(flow.ledger?.activeReviewVisit)
      XCTAssertNil(flow.ledger?.activePracticeVisit)
      XCTAssertNil(flow.media.guidedMediaVisit)
      XCTAssertEqual(flow.ledger?.entries, original)
      await flow.retryVisitPreparation()
      XCTAssertFalse(flow.isTransitioning)
      XCTAssertEqual(flow.ledger?.stage, expectedStage)
      let bound = try XCTUnwrap(flow.media.guidedMediaVisit)
      XCTAssertEqual(bound.entryID, expectedEntry.id)
      XCTAssertEqual(flow.media.sound.id, expectedEntry.soundID)
      XCTAssertEqual(flow.media.sound.position, expectedEntry.position)
      XCTAssertEqual(flow.media.sound.prompts, [expectedEntry.prompt])
      XCTAssertEqual(flow.media.totalWords, 1)
      if boundary == .practice {
        XCTAssertEqual(flow.ledger?.activePracticeVisit?.visitID, bound.visitID)
      } else {
        XCTAssertEqual(flow.ledger?.activeReviewVisit?.visitID, bound.visitID)
      }
      if boundary == .practice || boundary == .recheck {
        XCTAssertEqual(flow.ledger?.initialRound, initialBefore)
      }
      if boundary == .nextWord {
        XCTAssertEqual(flow.ledger?.initialRound.rows.first?.state, .finished(.skipped))
      }
      await flow.retryVisitPreparation()
      XCTAssertEqual(flow.media.guidedMediaVisit, bound)
      XCTAssertEqual(h.capturer.permissionRequests, 0)
      XCTAssertTrue(h.capturer.urls.isEmpty)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      XCTAssertTrue(h.player.playedURLs.isEmpty)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(flow.media === h.session)
      assertGuidedTrue(await flow.close())
    }
  }

  func testGuidedCoordinatorFileCleanupRecoveryAutomaticallyRejoinsClosePermission() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    await h.record()
    let file = try XCTUnwrap(h.capturer.urls.first)
    let owner = try XCTUnwrap(h.capturer.ownerIDs.first)
    h.capturer.failDiscardIndices = [0]
    assertGuidedFalse(await flow.close())
    XCTAssertFalse(flow.isClosed)
    XCTAssertNotEqual(flow.media.phase, .ended)
    XCTAssertTrue(flow.media.cleanupBlocked)
    XCTAssertTrue(h.files.pendingCleanupOwners.contains(owner))
    XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
    let closed = XCTestExpectation(
      description: "coordinator rejoined exact recovered end permission")
    var noted = false
    let subscription = flow.$isClosed.sink { value in
      if value, !noted {
        noted = true
        closed.fulfill()
      }
    }
    defer { subscription.cancel() }
    h.capturer.failDiscardIndices = []
    await flow.media.retryCleanup()
    await entered(closed)
    XCTAssertTrue(flow.isClosed)
    XCTAssertFalse(flow.isTransitioning)
    XCTAssertEqual(flow.media.phase, .ended)
    XCTAssertNil(flow.media.closeNote)
    XCTAssertFalse(flow.media.cleanupBlocked)
    XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertTrue(h.files.pendingCleanupOwners.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(flow.media === h.session)
  }
}

#if DEBUG
  @MainActor
  extension DirectPracticeSessionTests {
    func testGuidedMirrorRetryRejoinsExactDepartureOrFinishAndCloseWins() async throws {
      for practice in [false, true] {
        for close in [false, true] {
          let h = try GuidedOwnerHarness()
          defer { h.removeGeneratedFixture() }
          let camera = SessionMirrorFixture(cleanupFailures: 1)
          let session = DirectPracticeSession(
            capturer: h.capturer, player: h.player, mirror: camera.mirror,
            history: h.history, managedForGuided: true,
            wordRecognizer: h.recognizer, cleanupHardwareOwnership: h.gate,
            cleanupFileOwnership: h.files)
          let entry = try h.entry("p-beginning-pig")
          let reviewVisit = h.review(entry)
          let practiceVisit = h.practice(entry)
          let visit: GuidedMediaVisit = practice ? .practice(practiceVisit) : .review(reviewVisit)
          let prepared = await session.prepareGuidedVisit(entry: entry, visit: visit)
          XCTAssertTrue(prepared)
          session.appDidBecomeActive()
          await session.startRecording()
          session.stopRecording()
          if practice {
            await session.recordAnotherTry()
            session.stopRecording()
          }
          let fresh = try XCTUnwrap(session.latestTry?.id)
          let attempts = session.attemptCount
          session.showMirror()
          await twoTryWait {
            if case .live = camera.mirror.state { return true }
            return false
          }
          if practice {
            let failed = await session.finishGuidedPractice(practiceVisit)
            XCTAssertNil(failed.completionID)
          } else {
            let failed = await session.leaveGuidedVisit(visit)
            XCTAssertFalse(failed)
          }
          XCTAssertTrue(session.isTransitioning)
          XCTAssertTrue(session.tries.isEmpty)
          XCTAssertTrue(h.history.entries.isEmpty)
          XCTAssertFalse(camera.mirror.isReleasedForClose)
          XCTAssertTrue(h.files.protectedURLs.isEmpty)
          if close {
            _ = await session.end()
          }
          await session.retryMirrorStop()
          XCTAssertTrue(camera.mirror.isReleasedForClose)
          XCTAssertFalse(session.isTransitioning)
          XCTAssertTrue(h.recognizer.requests.isEmpty)
          if close {
            XCTAssertEqual(session.phase, .ended)
            XCTAssertTrue(h.history.entries.isEmpty)
            XCTAssertEqual(session.completedWords, 0)
          } else if practice {
            let result = await session.finishGuidedPractice(practiceVisit)
            XCTAssertEqual(result.visit, practiceVisit)
            XCTAssertEqual(result.freshTryID, fresh)
            XCTAssertEqual(result.completionID, practiceVisit.visitID)
            XCTAssertTrue(result.cleanupConfirmed)
            XCTAssertTrue(result.saveConfirmed)
            XCTAssertEqual(session.attemptCount, attempts)
            XCTAssertEqual(session.completedWords, 1)
            XCTAssertEqual(h.history.entries.count, 1)
            XCTAssertEqual(h.history.entries.first?.id, practiceVisit.visitID)
            await session.retryMirrorStop()
            let repeated = await session.finishGuidedPractice(practiceVisit)
            XCTAssertEqual(repeated, result)
            XCTAssertEqual(h.history.entries.count, 1)
          } else {
            XCTAssertEqual(session.phase, .ready)
            XCTAssertEqual(session.completedWords, 0)
            XCTAssertTrue(h.history.entries.isEmpty)
            let joinedDeparture = await session.leaveGuidedVisit(visit)
            XCTAssertTrue(joinedDeparture)
            let successor = h.review(entry)
            let successorPrepared = await session.prepareGuidedVisit(
              entry: entry, visit: .review(successor))
            XCTAssertTrue(successorPrepared)
            let staleDeparture = await session.leaveGuidedVisit(visit)
            XCTAssertFalse(staleDeparture)
            XCTAssertTrue(session.tries.isEmpty)
            XCTAssertEqual(session.attemptCount, 0)
          }
        }
      }
    }
  }
#endif

@MainActor
extension DirectPracticeSessionTests {
  func testGuidedInterruptedFinishReleasesAbandonedTakeAndAllowsExplicitFreshCapture()
    async throws
  {
    for interruption in [false, true] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let entry = try h.entry("p-beginning-pig")
      let visit = h.practice(entry)
      let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .practice(visit))
      XCTAssertTrue(prepared)
      h.session.appDidBecomeActive()
      await h.recordValidPractice()
      let abandoned = try XCTUnwrap(h.session.latestTry?.id)
      h.player.holdPreparation = true
      h.player.holdCleanup = true
      let starting = Task { await h.session.togglePlayback() }
      let queued = await h.player.driver(0)
      let driver = try XCTUnwrap(queued)
      defer { driver.releaseAll() }
      await entered(driver.prepared)
      let stopping = XCTestExpectation(description: "guided Finish stopped held playback")
      var noted = false
      let states = h.session.$playbackState.sink { state in
        if case .stopping = state, !noted {
          noted = true
          stopping.fulfill()
        }
      }
      defer { states.cancel() }
      let finishing = Task { await h.session.finishGuidedPractice(visit) }
      await entered(stopping)
      if interruption { h.session.audioWasInterrupted() } else { h.session.appDidEnterBackground() }
      driver.releasePreparation()
      await entered(driver.cleaning)
      XCTAssertTrue(h.history.entries.isEmpty)
      driver.releaseCleanup()
      await starting.value
      let revoked = await finishing.value
      XCTAssertNil(revoked.completionID)
      await settle(h.session)
      XCTAssertEqual(h.session.phase, .ready)
      XCTAssertTrue(h.session.tries.isEmpty)
      XCTAssertEqual(h.session.completedWords, 0)
      XCTAssertNil(h.session.participationCompletion)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertEqual(h.capturer.urls.count, 2)
      h.session.appDidBecomeActive()
      await h.record()
      let fresh = try XCTUnwrap(h.session.latestTry?.id)
      XCTAssertNotEqual(fresh, abandoned)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      let result = await h.session.finishGuidedPractice(visit)
      XCTAssertEqual(result.freshTryID, fresh)
      XCTAssertEqual(result.completionID, visit.visitID)
      XCTAssertTrue(result.saveConfirmed)
      XCTAssertEqual(h.history.entries.count, 1)
    }
  }
}

#if DEBUG
  @MainActor
  extension DirectPracticeSessionTests {
    func testGuidedCoordinatorMirrorRetryResumesExactReviewDepartureIntent() async throws {
      for action in ["advance", "skip", "finish"] {
        let h = try GuidedOwnerHarness()
        defer { h.removeGeneratedFixture() }
        let camera = SessionMirrorFixture(cleanupFailures: 1)
        let media = DirectPracticeSession(
          capturer: h.capturer, player: h.player, mirror: camera.mirror,
          history: h.history, managedForGuided: true, wordRecognizer: h.recognizer,
          cleanupHardwareOwnership: h.gate, cleanupFileOwnership: h.files)
        let flow = LocalGuidedReviewSession(history: h.history, media: media)
        await flow.startInitialReview()
        let original = try XCTUnwrap(flow.ledger?.activeReviewVisit)
        media.appDidBecomeActive()
        await media.startRecording()
        media.stopRecording()
        if action == "advance" {
          let checking = Task { await flow.checkCurrentWord() }
          _ = try await h.recognizer.waitForRequest(index: 0)
          h.recognizer.resolve(index: 0, status: .unavailable)
          await checking.value
        }
        let firstBefore = try XCTUnwrap(flow.ledger?.initialRound.rows.first)
        let captures = h.capturer.urls.count
        let requests = h.recognizer.requests.count
        media.showMirror()
        await twoTryWait {
          if case .live = camera.mirror.state { return true }
          return false
        }
        switch action {
        case "advance": await flow.advanceVisit()
        case "skip": await flow.skipVisit()
        default: await flow.finishStageNow()
        }
        XCTAssertEqual(flow.ledger?.activeReviewVisit, original)
        XCTAssertEqual(media.guidedMediaVisit, .review(original))
        XCTAssertTrue(media.isTransitioning)
        XCTAssertTrue(h.history.entries.isEmpty)
        await media.retryMirrorStop()
        XCTAssertNil(media.guidedMediaVisit)
        XCTAssertEqual(media.guidedReleasedVisit, .review(original))
        XCTAssertEqual(flow.ledger?.activeReviewVisit, original)
        await flow.retryVisitPreparation()
        XCTAssertFalse(flow.isTransitioning)
        if action == "finish" {
          XCTAssertEqual(flow.ledger?.stage, .choosingPractice)
          XCTAssertNil(flow.ledger?.activeReviewVisit)
          XCTAssertTrue(flow.ledger?.initialRound.isFinished == true)
          XCTAssertEqual(flow.ledger?.initialRound.rows.first?.state, .finished(.skipped))
          XCTAssertTrue(
            flow.ledger?.initialRound.rows.dropFirst().allSatisfy {
              $0.state == .finished(.unreached)
            } == true)
        } else {
          let successor = try XCTUnwrap(flow.ledger?.activeReviewVisit)
          XCTAssertNotEqual(successor.visitID, original.visitID)
          XCTAssertEqual(successor.roundID, original.roundID)
          XCTAssertEqual(successor.entryID, flow.setupEntries[1].id)
          XCTAssertEqual(media.guidedMediaVisit, .review(successor))
          XCTAssertNil(media.guidedReleasedVisit)
          if action == "advance" {
            XCTAssertEqual(flow.ledger?.initialRound.rows.first, firstBefore)
          } else {
            XCTAssertEqual(flow.ledger?.initialRound.rows.first?.state, .finished(.skipped))
          }
          await flow.retryVisitPreparation()
          XCTAssertEqual(flow.ledger?.activeReviewVisit, successor)
          XCTAssertEqual(media.guidedMediaVisit, .review(successor))
        }
        XCTAssertEqual(h.capturer.urls.count, captures)
        XCTAssertEqual(h.recognizer.requests.count, requests)
        XCTAssertTrue(h.history.entries.isEmpty)
        XCTAssertTrue(h.files.protectedURLs.isEmpty)
        let closed = await flow.close()
        XCTAssertTrue(closed)
      }
    }

    func testGuidedCoordinatorNextConsumesSamePracticeCompletionAfterMirrorRetry() async throws {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let camera = SessionMirrorFixture(cleanupFailures: 1)
      let media = DirectPracticeSession(
        capturer: h.capturer, player: h.player, mirror: camera.mirror,
        history: h.history, managedForGuided: true, wordRecognizer: h.recognizer,
        cleanupHardwareOwnership: h.gate, cleanupFileOwnership: h.files)
      let flow = LocalGuidedReviewSession(history: h.history, media: media)
      await flow.startInitialReview()
      await flow.finishStageNow()
      let pig = try h.entry("p-beginning-pig")
      flow.togglePracticeSelection(entryID: pig.id)
      await flow.startPractice()
      let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
      media.appDidBecomeActive()
      await media.startRecording()
      media.stopRecording()
      await media.recordAnotherTry()
      media.stopRecording()
      let fresh = try XCTUnwrap(media.latestTry?.id)
      let captures = h.capturer.urls.count
      media.showMirror()
      await twoTryWait {
        if case .live = camera.mirror.state { return true }
        return false
      }
      await flow.advanceVisit()
      XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
      XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .ready)
      XCTAssertTrue(h.history.entries.isEmpty)
      await media.retryMirrorStop()
      XCTAssertEqual(media.phase, .completed)
      XCTAssertEqual(media.participationCompletion?.id, visit.visitID)
      XCTAssertEqual(h.history.entries.count, 1)
      XCTAssertTrue(flow.playerPresentation.canContinue)
      await flow.advanceVisit()
      XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
      XCTAssertNil(flow.ledger?.activePracticeVisit)
      XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .finished(.finished))
      XCTAssertEqual(flow.ledger?.practiceRows.first?.freshTryID, fresh)
      XCTAssertEqual(h.history.entries.count, 1)
      XCTAssertEqual(h.history.entries.first?.id, visit.visitID)
      XCTAssertEqual(h.capturer.urls.count, captures)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      await flow.advanceVisit()
      await flow.retryVisitPreparation()
      XCTAssertEqual(h.history.entries.count, 1)
      XCTAssertEqual(h.capturer.urls.count, captures)
      let closed = await flow.close()
      XCTAssertTrue(closed)
    }
  }
#endif

// Optional practice checks use the existing controlled worker and exact media owner.
@MainActor
extension DirectPracticeSessionTests {
  private func readyWordCheckPractice(_ h: GuidedOwnerHarness) async throws
    -> LocalGuidedReviewSession
  {
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    await h.record()
    let first = Task { await flow.checkCurrentWord() }
    _ = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .matched)
    await first.value
    await flow.finishStageNow()
    flow.togglePracticeSelection(entryID: "p-beginning-pig")
    await flow.startPractice()
    XCTAssertEqual(flow.ledger?.stage, .practice)
    XCTAssertEqual(
      flow.playerPresentation.firstObservationNote,
      "First review: Not reached. Word checks cannot identify which sound was made.")
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    return flow
  }

  private func readyUnrecordedPractice(_ h: GuidedOwnerHarness) async -> LocalGuidedReviewSession {
    let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
    await flow.startInitialReview()
    await flow.finishStageNow()
    flow.togglePracticeSelection(entryID: "p-beginning-pig")
    await flow.startPractice()
    XCTAssertEqual(flow.ledger?.stage, .practice)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)
    return flow
  }

  func testGuidedPracticeNextWaitsForAcceptableLatestTakeAndSavesSameVisitWithoutWordCheck()
    async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = await readyUnrecordedPractice(h)
    let initial = try XCTUnwrap(flow.ledger?.initialRound)
    let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
    XCTAssertFalse(flow.playerPresentation.canContinue)
    await flow.advanceVisit()
    XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
    XCTAssertNil(flow.ledger?.practiceRows.first?.freshTryID)
    XCTAssertTrue(h.capturer.urls.isEmpty)
    XCTAssertTrue(h.history.entries.isEmpty)

    await h.record()
    let short = try XCTUnwrap(h.session.latestTry)
    XCTAssertNotEqual(short.assessment, .acceptable)
    XCTAssertFalse(flow.playerPresentation.canContinue)
    XCTAssertTrue(flow.playerPresentation.canSkip)
    XCTAssertTrue(flow.canClose)
    XCTAssertTrue(h.session.canRecordAnotherTry)
    let kept = h.session.tries
    await flow.advanceVisit()
    XCTAssertEqual(h.session.tries, kept)
    XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
    XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .ready)
    XCTAssertNil(flow.ledger?.practiceRows.first?.freshTryID)
    XCTAssertNil(h.session.participationCompletion)
    XCTAssertEqual(flow.ledger?.initialRound, initial)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    XCTAssertTrue(h.capturer.discardedIndices.isEmpty)

    await h.session.recordAnotherTry()
    h.session.stopRecording()
    let accepted = try XCTUnwrap(h.session.latestTry)
    XCTAssertNotEqual(accepted.id, short.id)
    XCTAssertEqual(accepted.assessment, .acceptable)
    XCTAssertTrue(flow.playerPresentation.canContinue)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    await flow.advanceVisit()
    XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
    XCTAssertEqual(flow.ledger?.initialRound, initial)
    XCTAssertEqual(flow.ledger?.practiceRows.first?.visit, visit)
    XCTAssertEqual(flow.ledger?.practiceRows.first?.freshTryID, accepted.id)
    XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .finished(.finished))
    XCTAssertEqual(h.history.entries.count, 1)
    XCTAssertEqual(h.history.entries.first?.id, visit.visitID)
    XCTAssertEqual(h.history.entries.first?.soundID, "p")
    XCTAssertEqual(h.history.entries.first?.wordCount, 1)
    XCTAssertEqual(PracticeParticipationStore(fileURL: h.historyURL).entries, h.history.entries)
    XCTAssertEqual(h.capturer.discardedIndices, [0, 1])
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    let saved = h.history.entries
    await flow.advanceVisit()
    XCTAssertEqual(h.history.entries, saved)
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedPracticeNextUsesLatestQualityAndRejectsNonfiniteDuration() async throws {
    for rejectedDuration in [0.4, Double.nan, Double.infinity] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [0.9, rejectedDuration, 0.9]
      let flow = await readyUnrecordedPractice(h)
      let initial = try XCTUnwrap(flow.ledger?.initialRound)
      let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
      await h.record()
      let earlier = try XCTUnwrap(h.session.latestTry)
      XCTAssertEqual(earlier.assessment, .acceptable)
      XCTAssertTrue(flow.playerPresentation.canContinue)
      await h.session.recordAnotherTry()
      h.session.stopRecording()
      let rejected = try XCTUnwrap(h.session.latestTry)
      XCTAssertEqual(h.session.earlierTry?.id, earlier.id)
      XCTAssertNotEqual(rejected.id, earlier.id)
      XCTAssertFalse(flow.playerPresentation.canContinue)
      await flow.advanceVisit()
      XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
      XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .ready)
      XCTAssertNil(flow.ledger?.practiceRows.first?.freshTryID)
      XCTAssertNil(h.session.participationCompletion)
      XCTAssertEqual(h.session.latestTry?.id, rejected.id)
      XCTAssertEqual(h.session.earlierTry?.id, earlier.id)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
      await h.session.recordAnotherTry()
      h.session.stopRecording()
      let fresh = try XCTUnwrap(h.session.latestTry)
      XCTAssertEqual(fresh.assessment, .acceptable)
      XCTAssertTrue(flow.playerPresentation.canContinue)
      await flow.advanceVisit()
      XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(flow.ledger?.initialRound, initial)
      XCTAssertEqual(flow.ledger?.practiceRows.first?.freshTryID, fresh.id)
      XCTAssertEqual(h.history.entries.count, 1)
      XCTAssertEqual(h.history.entries.first?.id, visit.visitID)
      XCTAssertEqual(h.capturer.discardedIndices, [0, 1, 2])
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      assertGuidedTrue(await flow.close())
    }
  }

  func testGuidedPracticeManualOutcomesStayCurrentTakeOnlyAndNeverGateParticipation() async throws {
    let statuses: [LocalWordRecognitionStatus] = [
      .matched, .notMatched, .uncertain, .timedOut, .unavailable, .cancelled,
    ]
    for status in statuses {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let flow = try await readyWordCheckPractice(h)
      let initial = try XCTUnwrap(flow.ledger?.initialRound)
      let selection = flow.practiceSelectionIDs
      let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
      let observer = GuidedOwnerObservation()
      let subscription = h.session.guidedReviewEvents.sink { event in
        MainActor.assumeIsolated { observer.receive(event) }
      }
      defer { subscription.cancel() }
      XCTAssertTrue(flow.playerPresentation.showsWordCheck)
      XCTAssertFalse(flow.playerPresentation.canCheckWords)
      await h.recordValidPractice()
      XCTAssertEqual(h.recognizer.requests.count, 1) // Never starts on Record/Stop.
      let take = try XCTUnwrap(h.session.latestTry)
      XCTAssertTrue(flow.playerPresentation.canCheckWords)
      let checking = Task { await flow.checkCurrentWord() }
      let request = try await timeoutRequest(checking, recognizer: h.recognizer, index: 1)
      XCTAssertEqual(request.tryID, take.id)
      XCTAssertEqual(request.fileURL, try XCTUnwrap(h.capturer.urls.last))
      XCTAssertEqual(request.expectedWord, "pig")
      await flow.checkCurrentWord() // Duplicate tap must not create a sibling worker.
      XCTAssertEqual(h.recognizer.requests.count, 2)
      h.recognizer.resolve(index: 1, status: status)
      await checking.value
      XCTAssertEqual(h.session.wordCheckState, .finished(status))
      XCTAssertEqual(h.session.checkedTryID, take.id)
      XCTAssertTrue(observer.submitted.isEmpty)
      XCTAssertTrue(observer.settled.isEmpty)
      XCTAssertEqual(flow.ledger?.initialRound, initial)
      XCTAssertNil(flow.ledger?.recheckRound)
      XCTAssertEqual(flow.practiceSelectionIDs, selection)
      XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .ready)
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertTrue(flow.playerPresentation.canContinue)
      if status == .unavailable || status == .cancelled {
        XCTAssertTrue(flow.playerPresentation.canCheckWords)
        let retry = Task { await flow.checkCurrentWord() }
        let retryRequest = try await h.recognizer.waitForRequest(index: 2)
        XCTAssertEqual(retryRequest.tryID, take.id)
        XCTAssertNotEqual(retryRequest.operationID, request.operationID)
        h.recognizer.resolve(index: 2, status: status)
        await retry.value
      } else {
        XCTAssertFalse(flow.playerPresentation.canCheckWords)
        await flow.checkCurrentWord()
        XCTAssertEqual(h.recognizer.requests.count, 2)
      }
      await flow.advanceVisit()
      XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(flow.ledger?.initialRound, initial)
      XCTAssertEqual(h.history.entries.count, 1)
      XCTAssertEqual(h.history.entries.first?.id, visit.visitID)
      XCTAssertEqual(h.history.entries.first?.soundID, "p")
      XCTAssertEqual(h.history.entries.first?.wordCount, 1)
      let saved = h.history.entries
      await flow.startRecheck()
      let recheck = try XCTUnwrap(flow.ledger?.recheckRound)
      let requests = h.recognizer.requests.count
      XCTAssertTrue(recheck.rows.allSatisfy { $0.firstSubmission == nil })
      await flow.finishStageNow()
      XCTAssertEqual(flow.ledger?.initialRound, initial)
      XCTAssertEqual(flow.ledger?.recheckRound?.rows.map(\.firstSubmission), recheck.rows.map(\.firstSubmission))
      XCTAssertEqual(h.history.entries, saved)
      XCTAssertEqual(h.recognizer.requests.count, requests)
      assertGuidedTrue(await flow.close())
    }
  }

  func testGuidedPracticeHeldCheckBlocksReplacementThenNewTakeClearsOnlyEphemeralResult() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = try await readyWordCheckPractice(h)
    let initial = try XCTUnwrap(flow.ledger?.initialRound)
    await h.recordValidPractice()
    let checking = Task { await flow.checkCurrentWord() }
    let first = try await h.recognizer.waitForRequest(index: 1)
    let captures = h.capturer.urls.count
    XCTAssertFalse(h.session.canRecordAnotherTry)
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.capturer.urls.count, captures)
    XCTAssertEqual(h.session.latestTry?.id, first.tryID)
    h.recognizer.resolve(index: 1, status: .notMatched)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.notMatched))
    await h.session.recordAnotherTry()
    XCTAssertEqual(h.session.phase, .recording)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    h.session.stopRecording()
    let replacement = try XCTUnwrap(h.session.latestTry)
    XCTAssertNotEqual(replacement.id, first.tryID)
    XCTAssertEqual(h.recognizer.requests.count, 2)
    let secondCheck = Task { await flow.checkCurrentWord() }
    let second = try await h.recognizer.waitForRequest(index: 2)
    XCTAssertEqual(second.tryID, replacement.id)
    XCTAssertNotEqual(second.fileURL, first.fileURL)
    h.recognizer.resolve(index: 2, status: .matched)
    await secondCheck.value
    XCTAssertEqual(h.session.checkedTryID, replacement.id)
    XCTAssertEqual(flow.ledger?.initialRound, initial)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedPracticeExplicitCancelWaitsForReceiptThenReplacementNeedsManualCheck() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = try await readyWordCheckPractice(h)
    await h.recordValidPractice()
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 1)
    h.session.cancelWordCheck()
    await h.recognizer.waitForCancellation(index: 0)
    XCTAssertEqual(h.session.wordCheckState, .cancelling)
    XCTAssertFalse(h.session.canRecordAnotherTry)
    XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
    h.recognizer.resolve(index: 1, status: .matched)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.cancelled))
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertNil(h.session.checkedTryID)
    XCTAssertNotEqual(h.session.latestTry?.id, request.tryID)
    XCTAssertEqual(h.recognizer.requests.count, 2)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedPracticeDepartureWaitsForExactBorrowAndSuppressesLateMatch() async throws {
    enum Departure { case next, skip, finish, close, background, interruption, disappearance }
    for departure in [Departure.next, .skip, .finish, .close, .background, .interruption, .disappearance] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let flow = try await readyWordCheckPractice(h)
      let initial = try XCTUnwrap(flow.ledger?.initialRound)
      let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
      await h.recordValidPractice()
      let checking = Task { await flow.checkCurrentWord() }
      let request = try await h.recognizer.waitForRequest(index: 1)
      let discarded = h.capturer.discardedIndices
      var returned = false
      let leaving = Task {
        switch departure {
        case .next: await flow.advanceVisit()
        case .skip: await flow.skipVisit()
        case .finish: await flow.finishStageNow()
        case .close: _ = await flow.close()
        case .background: flow.background(); await settle(h.session)
        case .interruption: flow.interrupted(); await settle(h.session)
        case .disappearance: flow.disappeared(); await settle(h.session)
        }
        returned = true
      }
      await h.recognizer.waitForCancellation(index: 0)
      XCTAssertFalse(returned)
      XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
      XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .ready)
      XCTAssertEqual(h.capturer.discardedIndices, discarded)
      XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
      XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertFalse(flow.playerPresentation.canCheckWords)
      h.recognizer.resolve(index: 1, status: .matched)
      await checking.value
      await leaving.value
      XCTAssertTrue(returned)
      XCTAssertEqual(h.session.wordCheckState, .idle)
      XCTAssertNil(h.session.checkedTryID)
      XCTAssertFalse(FileManager.default.fileExists(atPath: request.fileURL.path))
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      XCTAssertEqual(flow.ledger?.initialRound, initial)
      XCTAssertNil(flow.ledger?.recheckRound)
      XCTAssertEqual(h.recognizer.requests.count, 2)
      if departure == .next {
        XCTAssertEqual(flow.ledger?.stage, .readyToRecheck)
        XCTAssertEqual(h.history.entries.map(\.id), [visit.visitID])
        XCTAssertEqual(h.history.entries.first?.wordCount, 1)
      } else {
        XCTAssertTrue(h.history.entries.isEmpty)
      }
      assertGuidedTrue(await flow.close())
    }
  }

  func testGuidedPracticeInvalidReceiptRetainsBorrowAndBlocksDepartureAndHistory() async throws {
    for wrongRequest in [false, true] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      let flow = try await readyWordCheckPractice(h)
      let ledger = try XCTUnwrap(flow.ledger)
      await h.recordValidPractice()
      let checking = Task { await flow.checkCurrentWord() }
      let request = try await h.recognizer.waitForRequest(index: 1)
      let sibling = LocalWordRecognitionRequest(
        operationID: UUID(), tryID: request.tryID, fileURL: request.fileURL,
        expectedWord: request.expectedWord)
      let discarded = h.capturer.discardedIndices
      h.recognizer.resolve(
        index: 1, status: .matched, cleanupConfirmed: wrongRequest,
        receiptRequest: wrongRequest ? sibling : nil)
      await checking.value
      XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
      XCTAssertTrue(h.session.cleanupBlocked)
      XCTAssertFalse(flow.playerPresentation.canCheckWords)
      XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
      await flow.advanceVisit()
      await flow.skipVisit()
      await flow.finishStageNow()
      assertGuidedFalse(await flow.close())
      XCTAssertFalse(flow.isClosed)
      XCTAssertEqual(flow.ledger?.stage, ledger.stage)
      XCTAssertEqual(flow.ledger?.initialRound, ledger.initialRound)
      XCTAssertEqual(flow.ledger?.practiceRows, ledger.practiceRows)
      XCTAssertEqual(h.capturer.discardedIndices, discarded)
      XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
      XCTAssertTrue(h.history.entries.isEmpty)
      XCTAssertEqual(h.recognizer.requests.count, 2)
      // Teardown release is not a new receipt and must not repair this owner's decision.
      h.recognizer.releaseGeneratedBorrows()
      await h.session.retryCleanup()
      assertGuidedFalse(await flow.close())
      XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked)
      XCTAssertEqual(h.capturer.discardedIndices, discarded)
    }
  }

  func testGuidedPracticeWrongExactVisitRejectsEvenWhenOwnerHasEligibleTake() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = try await readyWordCheckPractice(h)
    let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
    let entry = try h.entry(visit.entryID)
    let left = await h.session.leaveGuidedVisit(.practice(visit))
    XCTAssertTrue(left)
    let sibling = LocalGuidedPracticeVisit(
      workflowID: visit.workflowID, practiceID: visit.practiceID,
      visitID: UUID(), entryID: visit.entryID)
    let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .practice(sibling))
    XCTAssertTrue(prepared)
    await h.recordValidPractice()
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    XCTAssertFalse(flow.playerPresentation.canCheckWords)
    await flow.checkCurrentWord()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await flow.close())
  }

  func testGuidedPracticeFrozenFinishAndUnconfirmedSaveRejectNewWordChecks() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = try await readyWordCheckPractice(h)
    try FileManager.default.createDirectory(at: h.historyURL, withIntermediateDirectories: true)
    await h.recordValidPractice()
    let visit = try XCTUnwrap(flow.ledger?.activePracticeVisit)
    let checking = Task { await flow.checkCurrentWord() }
    _ = try await h.recognizer.waitForRequest(index: 1)
    let finishing = Task { await flow.advanceVisit() }
    await h.recognizer.waitForCancellation(index: 0)
    XCTAssertFalse(flow.playerPresentation.canCheckWords)
    await flow.checkCurrentWord()
    XCTAssertEqual(h.recognizer.requests.count, 2)
    h.recognizer.resolve(index: 1, status: .matched)
    await checking.value
    await finishing.value
    XCTAssertEqual(flow.ledger?.practiceRows.first?.state, .finished(.saveUnconfirmed))
    XCTAssertEqual(flow.ledger?.activePracticeVisit, visit)
    XCTAssertFalse(flow.playerPresentation.canCheckWords)
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    await flow.checkCurrentWord()
    XCTAssertEqual(h.recognizer.requests.count, 2)
    XCTAssertTrue(h.history.entries.isEmpty)
    let completion = h.session.participationCompletion
    try FileManager.default.removeItem(at: h.historyURL)
    flow.retryPracticeSave()
    XCTAssertEqual(h.session.participationCompletion, completion)
    XCTAssertEqual(h.history.entries.count, 1)
    XCTAssertEqual(h.history.entries.first?.id, visit.visitID)
    await flow.checkCurrentWord()
    XCTAssertEqual(h.recognizer.requests.count, 2)
    assertGuidedTrue(await flow.close())
  }
}

@MainActor
extension DirectPracticeSessionTests {
  func testGuidedPracticeCloseSupersedesHeldNextWithoutParticipationOrLateResult() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let flow = try await readyWordCheckPractice(h)
    let initial = try XCTUnwrap(flow.ledger?.initialRound)
    await h.recordValidPractice()
    let checking = Task { await flow.checkCurrentWord() }
    let request = try await h.recognizer.waitForRequest(index: 1)
    let advancing = Task { await flow.advanceVisit() }
    await h.recognizer.waitForCancellation(index: 0)
    let enteredClose = XCTestExpectation(description: "Close supersedes held practice Next")
    let closing = Task {
      enteredClose.fulfill()
      return await flow.close()
    }
    await entered(enteredClose)
    XCTAssertFalse(flow.isClosed)
    XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
    XCTAssertTrue(h.history.entries.isEmpty)
    h.recognizer.resolve(index: 1, status: .matched)
    await checking.value
    await advancing.value
    assertGuidedTrue(await closing.value)
    XCTAssertTrue(flow.isClosed)
    XCTAssertEqual(h.session.phase, .ended)
    XCTAssertEqual(h.session.wordCheckState, .idle)
    XCTAssertEqual(flow.ledger?.initialRound, initial)
    XCTAssertTrue(h.history.entries.isEmpty)
    XCTAssertTrue(h.files.protectedURLs.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: request.fileURL.path))
  }

  func testGuidedPracticeMatchedShortTakeDoesNotCreateParticipationOrFreezeFreshTake() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("p-beginning-pig")
    let visit = h.practice(entry)
    let prepared = await h.session.prepareGuidedVisit(entry: entry, visit: .practice(visit))
    XCTAssertTrue(prepared)
    await h.record() // Existing generated capture's first take is too short for participation.
    let checking = Task { await h.session.startWordCheck() }
    _ = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .matched)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.matched))
    let rejected = await h.session.finishGuidedPractice(visit)
    XCTAssertNil(rejected.freshTryID)
    XCTAssertNil(rejected.completionID)
    XCTAssertTrue(h.history.entries.isEmpty)
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertTrue(h.session.canCheckWordsInLatestTry)
    let accepted = await h.session.finishGuidedPractice(visit)
    XCTAssertTrue(accepted.cleanupConfirmed)
    XCTAssertTrue(accepted.saveConfirmed)
    XCTAssertEqual(accepted.completionID, visit.visitID)
    XCTAssertFalse(h.session.canCheckWordsInLatestTry)
    await h.session.startWordCheck()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    XCTAssertEqual(h.history.entries.count, 1)
    assertGuidedTrue(await h.session.end())
  }
}

@MainActor
private final class HeldRuntimeReleaseRecognizer: LocalWordRecognizing, LocalWordRuntimeReleasing {
  let entered = XCTestExpectation(description: "flow runtime disposal entered")
  private var continuation: CheckedContinuation<Bool, Never>?
  private(set) var releases = 0
  private var held = true
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    .init(request: request, status: .unavailable, cleanupConfirmed: true)
  }
  func cancel(operationID: UUID) {}
  func releaseWordRuntime() async -> Bool {
    releases += 1
    if !held { return true }
    return await withCheckedContinuation {
      continuation = $0
      entered.fulfill()
    }
  }
  func release() {
    held = false
    let pending = continuation
    continuation = nil
    pending?.resume(returning: true)
  }
}

@MainActor
extension DirectPracticeSessionTests {
  func testDuplicateEndJoinsRuntimeDisposalAndExplicitRestartUsesNewLifetime() async {
    let runtime = HeldRuntimeReleaseRecognizer(); defer { runtime.release() }
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(capturer: capturer, player: DirectPracticePlayer(), wordRecognizer: runtime)
    let first = Task { await session.end() }
    await fulfillment(of: [runtime.entered], timeout: 2)
    XCTAssertNotEqual(session.phase, .ended)
    let second = Task { await session.end() }
    runtime.release()
    let firstEnded = await first.value
    let secondEnded = await second.value
    XCTAssertTrue(firstEnded && secondEnded)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(runtime.releases, 1)
    XCTAssertEqual(capturer.permissionRequestCount, 0)
    await session.restart()
    XCTAssertEqual(session.phase, .ready)
    let endedAgain = await session.end()
    XCTAssertTrue(endedAgain)
    XCTAssertEqual(runtime.releases, 2)
  }

  func testDisappearanceEndAlsoWaitsForRuntimeDisposal() async {
    let runtime = HeldRuntimeReleaseRecognizer(); defer { runtime.release() }
    let session = DirectPracticeSession(capturer: DirectPracticeCapturer(),
      player: DirectPracticePlayer(), wordRecognizer: runtime)
    session.viewDidDisappear()
    await fulfillment(of: [runtime.entered], timeout: 2)
    XCTAssertNotEqual(session.phase, .ended)
    let ended = XCTestExpectation(description: "disappearance joins runtime disposal")
    let subscription = session.$phase.sink { if $0 == .ended { ended.fulfill() } }
    defer { subscription.cancel() }
    runtime.release()
    await fulfillment(of: [ended], timeout: 2)
    XCTAssertEqual(runtime.releases, 1)
    XCTAssertEqual(session.phase, .ended)
  }
}

@MainActor
extension DirectPracticeSessionTests {
  func testCleanupRetryAndDuplicateWaitForHeldRuntimeDisposal() async {
    let runtime = HeldRuntimeReleaseRecognizer()
    defer { runtime.release() }
    let capturer = DirectPracticeCapturer()
    let session = DirectPracticeSession(
      capturer: capturer, player: DirectPracticePlayer(), wordRecognizer: runtime)
    await session.startRecording()
    session.stopRecording()
    guard case .review = session.phase else {
      return XCTFail("A stopped owned take must reach review before cleanup fails.")
    }
    capturer.shouldFailDiscard = true
    let ended = await session.end()
    XCTAssertFalse(ended)
    XCTAssertTrue(session.canRetryCleanup)
    XCTAssertTrue(session.captureCleanupState.hasFileIssue)
    XCTAssertEqual(runtime.releases, 0)
    XCTAssertEqual(capturer.permissionRequestCount, 1)

    capturer.shouldFailDiscard = false
    var retryFinished = false
    let retry = Task { @MainActor in
      await session.retryCleanup()
      retryFinished = true
    }
    await fulfillment(of: [runtime.entered], timeout: 2)
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertFalse(retryFinished, "Retry must join actual runtime disposal, not just file cleanup.")
    XCTAssertEqual(runtime.releases, 1)
    XCTAssertFalse(session.canRetryCleanup)
    XCTAssertTrue(session.actionsDisabled)
    XCTAssertFalse(session.canStartRecording)
    XCTAssertFalse(session.canRecordAnotherTry)

    let duplicateEntered = XCTestExpectation(description: "duplicate cleanup retry entered")
    var duplicateFinished = false
    let duplicate = Task { @MainActor in
      duplicateEntered.fulfill()
      await session.retryCleanup()
      duplicateFinished = true
    }
    await fulfillment(of: [duplicateEntered], timeout: 2)
    XCTAssertFalse(retryFinished)
    XCTAssertFalse(duplicateFinished, "A duplicate retry must join even while canRetryCleanup is false.")
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertEqual(runtime.releases, 1)

    runtime.release()
    await retry.value
    await duplicate.value
    XCTAssertTrue(retryFinished)
    XCTAssertTrue(duplicateFinished)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(session.captureCleanupState, .idle)
    XCTAssertEqual(runtime.releases, 1)
    XCTAssertEqual(capturer.permissionRequestCount, 1)
    XCTAssertEqual(capturer.startCount, 1)
    XCTAssertEqual(capturer.stopCount, 1)
  }
}

@MainActor
extension DirectPracticeSessionTests {
  func testGuidedRecordAndCheckManualAndAutomaticCompletionBindFreshReviewAndRecheck() async throws
  {
    for automatic in [false, true] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [0.9, 0.9]
      let flow = LocalGuidedReviewSession(history: h.history, media: h.session)
      await flow.startInitialReview()
      let initialVisit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
      for index in 0..<2 {
        let visit = try XCTUnwrap(flow.ledger?.activeReviewVisit)
        XCTAssertTrue(h.session.canStartRecordingAndCheckWord)
        await h.session.startRecordingAndCheckWord()
        XCTAssertEqual(h.session.phase, .recording)
        XCTAssertEqual(h.recognizer.requests.count, index)
        if automatic { await h.capturer.finish(index: index) } else { h.session.stopRecording() }
        let take = try XCTUnwrap(h.session.latestTry)
        let request = try await h.recognizer.waitForRequest(index: index)
        XCTAssertEqual(request.tryID, take.id)
        XCTAssertEqual(request.fileURL, h.capturer.urls[index])
        XCTAssertEqual(request.expectedWord, h.session.currentPrompt.word)
        XCTAssertEqual(flow.ledger?.activeRound?.rows.first?.firstSubmission?.visit, visit)
        XCTAssertEqual(flow.ledger?.activeRound?.rows.first?.firstSubmission?.tryID, take.id)
        XCTAssertEqual(h.session.wordCheckState, .checking)
        h.session.stopRecording()
        await h.session.startWordCheck()
        await h.session.startRecordingAndCheckWord()
        XCTAssertEqual(h.recognizer.requests.count, index + 1)
        h.recognizer.resolve(index: index, status: .notMatched)
        await twoTryWait { h.session.wordCheckState == .finished(.notMatched) }
        XCTAssertEqual(flow.ledger?.activeRound?.rows.first?.state, .finished(.notMatched))
        XCTAssertTrue(h.history.entries.isEmpty)
        if index == 0 {
          await flow.finishStageNow()
          let initial = try XCTUnwrap(flow.ledger?.initialRound)
          flow.togglePracticeSelection(entryID: initialVisit.entryID)
          await flow.startPractice()
          XCTAssertFalse(h.session.canStartRecordingAndCheckWord)
          await flow.finishStageNow()
          await flow.startRecheck()
          XCTAssertEqual(flow.ledger?.initialRound, initial)
          XCTAssertNotEqual(flow.ledger?.activeReviewVisit?.visitID, initialVisit.visitID)
          XCTAssertNotEqual(flow.ledger?.activeReviewVisit?.roundID, initialVisit.roundID)
        }
      }
      XCTAssertNotEqual(h.recognizer.requests[0].tryID, h.recognizer.requests[1].tryID)
      XCTAssertNotEqual(h.recognizer.requests[0].operationID, h.recognizer.requests[1].operationID)
      assertGuidedTrue(await flow.close())
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
    }
  }

  func testGuidedRecordOnlyReplacementAndPracticeNeverAcquireCombinedIntent() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    h.capturer.durations = [0.9, 0.9, 0.9]
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    await h.session.recordAnotherTry()
    h.session.stopRecording()
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    let manual = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    XCTAssertEqual(request.tryID, h.session.latestTry?.id)
    h.recognizer.resolve(index: 0, status: .matched)
    await manual.value
    assertGuidedTrue(await h.leave(visit))
    let practice = h.practice(entry)
    assertGuidedTrue(await h.session.prepareGuidedVisit(entry: entry, visit: .practice(practice)))
    XCTAssertFalse(h.session.canStartRecordingAndCheckWord)
    await h.session.startRecordingAndCheckWord()
    XCTAssertEqual(h.capturer.urls.count, 2)
    await h.record()
    XCTAssertEqual(h.recognizer.requests.count, 1)
    _ = await h.session.end()
    let direct = try LocalWordSessionHarness()
    defer { direct.removeGeneratedFixture() }
    XCTAssertFalse(direct.session.canStartRecordingAndCheckWord)
    await direct.session.startRecordingAndCheckWord()
    XCTAssertTrue(direct.capturer.urls.isEmpty)
  }

  func testGuidedRecordAndCheckRejectsQualityAndNonfiniteEvidenceWithoutFreezingSubmission()
    async throws
  {
    for summary in [
      CaptureSummary(duration: 0.4, averagePower: -20),
      CaptureSummary(duration: 0.9, averagePower: -90),
      CaptureSummary(duration: .nan, averagePower: -20),
      CaptureSummary(duration: .infinity, averagePower: -20),
      CaptureSummary(duration: 0.9, averagePower: .nan),
      CaptureSummary(duration: 0.9, averagePower: .infinity),
    ] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [summary.duration]
      h.capturer.averagePower = summary.averagePower
      let entry = try h.entry("b-beginning-ball")
      assertGuidedTrue(await h.prepare(entry, h.review(entry)))
      await h.session.startRecordingAndCheckWord()
      h.session.stopRecording()
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      XCTAssertTrue(h.session.canCheckWordsInLatestTry)
      XCTAssertTrue(h.session.canRecordAnotherTry)
      XCTAssertEqual(h.session.wordCheckState, .idle)
      _ = await h.session.end()
    }
  }

  func testGuidedRecordAndCheckFailureRecoveryNeverSilentlySubmits() async throws {
    enum Failure: CaseIterable { case denied, start, stop, cleanup, interrupted }
    for failure in Failure.allCases {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [0.9, 0.9]
      let entry = try h.entry("b-beginning-ball")
      assertGuidedTrue(await h.prepare(entry, h.review(entry)))
      h.capturer.permissionGranted = failure != .denied
      h.capturer.failStart = failure == .start
      await h.session.startRecordingAndCheckWord()
      if failure == .stop || failure == .cleanup {
        h.capturer.failRead = failure == .stop
        h.capturer.failStopHardware = failure == .cleanup
        h.session.stopRecording()
      } else if failure == .interrupted {
        await h.capturer.finish(index: 0, successfully: false)
      }
      await settle(h.session)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      h.capturer.failStopHardware = false
      await h.session.retryCleanup()
      h.session.appDidBecomeActive()
      h.session.stopRecording()
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      _ = await h.session.end()
    }
  }

  func testGuidedRecordAndCheckStopPublicationRevocationPreventsSubmission() async throws {
    for boundary in 0..<3 {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [0.9, 0.9]
      let entry = try h.entry("b-beginning-ball")
      assertGuidedTrue(await h.prepare(entry, h.review(entry)))
      await h.session.startRecordingAndCheckWord()
      var revoked = false
      var observation: AnyCancellable?
      if boundary == 0 {
        h.capturer.duringStop = { h.session.appDidEnterBackground() }
      } else if boundary == 1 {
        observation = h.session.$attemptCount.sink { count in
          if count == 1, !revoked {
            revoked = true
            h.session.appDidEnterBackground()
          }
        }
      } else {
        observation = h.session.$phase.sink { phase in
          if case .review = phase, !revoked {
            revoked = true
            h.session.appDidEnterBackground()
          }
        }
      }
      h.session.stopRecording()
      observation?.cancel()
      await settle(h.session)
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      XCTAssertTrue(h.session.tries.isEmpty)
      h.session.appDidBecomeActive()
      await h.record()
      XCTAssertTrue(h.recognizer.requests.isEmpty)
      _ = await h.session.end()
    }
  }

  func testGuidedRecordAndCheckRevokesPermissionIntentAndStaleRecorderForSuccessor() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    h.capturer.durations = [0.9, 0.9]
    let entry = try h.entry("b-beginning-ball")
    let first = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, first))
    h.capturer.holdsPermission = true
    let starting = Task { await h.session.startRecordingAndCheckWord() }
    await twoTryWait { h.capturer.permissionHeld }
    assertGuidedTrue(await h.leave(first))
    let second = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, second))
    h.capturer.resolvePermission(true)
    await starting.value
    XCTAssertTrue(h.capturer.urls.isEmpty)
    h.capturer.holdsPermission = false
    await h.session.startRecordingAndCheckWord()
    h.session.appDidEnterBackground()
    await settle(h.session)
    h.session.appDidBecomeActive()
    await h.session.startRecording()
    await h.capturer.finish(index: 0)
    XCTAssertEqual(h.session.phase, .recording)
    h.session.stopRecording()
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    _ = await h.session.end()
  }

  func testGuidedRecordAndCheckCancelledPermissionRequestDoesNotCaptureOrLeaveIntent() async throws
  {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    h.capturer.durations = [0.9]
    let entry = try h.entry("b-beginning-ball")
    assertGuidedTrue(await h.prepare(entry, h.review(entry)))
    h.capturer.holdsPermission = true
    let starting = Task { await h.session.startRecordingAndCheckWord() }
    await twoTryWait { h.capturer.permissionHeld }
    starting.cancel()
    h.capturer.resolvePermission(true)
    await starting.value
    XCTAssertEqual(h.session.phase, .ready)
    XCTAssertTrue(h.capturer.urls.isEmpty)
    XCTAssertTrue(h.session.canStartRecordingAndCheckWord)
    h.capturer.holdsPermission = false
    await h.record()
    XCTAssertTrue(h.recognizer.requests.isEmpty)
    _ = await h.session.end()
  }

  func testGuidedRecordAndCheckDepartureAndBackgroundWaitForExactReceipt() async throws {
    for background in [false, true] {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [0.9, 0.9]
      let entry = try h.entry("b-beginning-ball")
      let visit = h.review(entry)
      assertGuidedTrue(await h.prepare(entry, visit))
      await h.session.startRecordingAndCheckWord()
      h.session.stopRecording()
      let request = try await h.recognizer.waitForRequest(index: 0)
      let departure: Task<Bool, Never>?
      if background {
        departure = nil
        h.session.appDidEnterBackground()
      } else {
        departure = Task { await h.leave(visit) }
      }
      await h.recognizer.waitForCancellation(index: 0)
      XCTAssertTrue(FileManager.default.fileExists(atPath: request.fileURL.path))
      XCTAssertTrue(h.capturer.discardedIndices.isEmpty)
      h.recognizer.resolve(index: 0, status: .matched)
      if let departure { assertGuidedTrue(await departure.value) }
      await settle(h.session)
      XCTAssertTrue(h.session.tries.isEmpty)
      XCTAssertTrue(h.files.protectedURLs.isEmpty)
      XCTAssertTrue(h.history.entries.isEmpty)
      if background { assertGuidedTrue(await h.leave(visit)) }
      let successor = h.review(entry)
      assertGuidedTrue(await h.prepare(entry, successor))
      h.session.appDidBecomeActive()
      await h.record()
      await h.capturer.finish(index: 0)
      XCTAssertEqual(h.recognizer.requests.count, 1)
      XCTAssertEqual(h.session.wordCheckState, .idle)
      _ = await h.session.end()
    }
  }

  func testGuidedRecordAndCheckTerminalCancellationAndInvalidReceiptRemainOwned() async throws {
    for mode in 0..<4 {
      let h = try GuidedOwnerHarness()
      defer { h.removeGeneratedFixture() }
      h.capturer.durations = [0.9]
      let entry = try h.entry("b-beginning-ball")
      let visit = h.review(entry)
      assertGuidedTrue(await h.prepare(entry, visit))
      await h.session.startRecordingAndCheckWord()
      h.session.stopRecording()
      let request = try await h.recognizer.waitForRequest(index: 0)
      if mode == 0 { h.session.cancelWordCheck() }
      let wrong = LocalWordRecognitionRequest(
        operationID: UUID(), tryID: request.tryID, fileURL: request.fileURL,
        expectedWord: request.expectedWord)
      h.recognizer.resolve(
        index: 0, status: mode == 1 ? .timedOut : .matched,
        cleanupConfirmed: mode != 2, receiptRequest: mode == 3 ? wrong : nil)
      if mode < 2 {
        let status: LocalWordRecognitionStatus = mode == 0 ? .cancelled : .timedOut
        await twoTryWait { h.session.wordCheckState == .finished(status) }
        await h.session.startWordCheck()
        await h.session.startRecordingAndCheckWord()
        XCTAssertEqual(h.recognizer.requests.count, 1)
        assertGuidedTrue(await h.leave(visit))
        let successor = h.review(entry)
        assertGuidedTrue(await h.prepare(entry, successor))
        await h.capturer.finish(index: 0)
        XCTAssertEqual(h.session.phase, .ready)
        XCTAssertTrue(h.session.tries.isEmpty)
        _ = await h.session.end()
      } else {
        await twoTryWait { h.session.wordCheckState == .cleanupBlocked }
        XCTAssertTrue(h.session.cleanupBlocked)
        XCTAssertTrue(h.files.protectedURLs.contains(request.fileURL))
        assertGuidedFalse(await h.leave(visit))
        await h.session.retryCleanup()
        XCTAssertEqual(h.recognizer.requests.count, 1)
        XCTAssertTrue(h.history.entries.isEmpty)
      }
    }
  }
}

// Invented alternatives only: no decoder/model or recognized text persistence.
@MainActor
extension DirectPracticeSessionTests {
  func testOrdinaryWordGuessBindsLatestTakeAndRetakeClearsWithoutAnotherCheck() async throws {
    let h = try LocalWordSessionHarness()
    defer { h.removeGeneratedFixture() }
    await h.record()
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    let guess = try XCTUnwrap(LocalWordGuess(completedText: "wall", expectedWord: request.expectedWord))
    h.recognizer.resolve(index: 0, status: .notMatched, wordGuess: guess)
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.notMatched))
    XCTAssertEqual(h.session.currentWordGuess, guess)
    XCTAssertEqual(h.session.checkedTryID, request.tryID)
    await h.session.togglePlayback()
    XCTAssertEqual(h.player.playedURLs.last, request.fileURL)
    await h.session.togglePlayback()
    XCTAssertEqual(h.session.currentWordGuess, guess)
    await h.session.recordAnotherTry()
    XCTAssertNil(h.session.currentWordGuess)
    h.session.stopRecording()
    XCTAssertNil(h.session.currentWordGuess)
    XCTAssertEqual(h.recognizer.requests.count, 1)
    let ended = await h.session.end()
    XCTAssertTrue(ended)
    XCTAssertNil(h.session.currentWordGuess)
  }

  func testOrdinaryWordGuessClearsOnBackgroundAndCompletion() async throws {
    for background in [false, true] {
      let h = try LocalWordSessionHarness(singleWord: true)
      defer { h.removeGeneratedFixture() }
      await h.record()
      let checking = Task { await h.session.startWordCheck() }
      let request = try await h.recognizer.waitForRequest(index: 0)
      h.recognizer.resolve(index: 0, status: .notMatched,
        wordGuess: LocalWordGuess(completedText: "wall", expectedWord: request.expectedWord))
      await checking.value
      XCTAssertNotNil(h.session.currentWordGuess)
      if background { h.session.appDidBecomeInactive(); await settle(h.session) }
      else {
        await h.session.continuePractice()
        XCTAssertEqual(h.session.phase, .completed)
      }
      XCTAssertNil(h.session.currentWordGuess)
      let ended = await h.session.end()
      XCTAssertTrue(ended)
    }
  }

  func testWordGuessRejectsNoneligibleStatusCancellationAndUnconfirmedCleanup() async throws {
    for mode in 0..<8 {
      let h = try LocalWordSessionHarness()
      defer { h.removeGeneratedFixture() }
      await h.record()
      let checking = Task { await h.session.startWordCheck() }
      let request = try await h.recognizer.waitForRequest(index: 0)
      if mode == 2 { h.session.cancelWordCheck() }
      let status: LocalWordRecognitionStatus = mode == 0 ? .uncertain
        : mode == 1 ? .unavailable : mode == 6 ? .timedOut : mode == 7 ? .matched : .notMatched
      let expected = mode == 4 ? "pig" : request.expectedWord
      h.recognizer.resolve(index: 0, status: status, cleanupConfirmed: mode != 3,
        wordGuess: mode == 5 ? nil : LocalWordGuess(completedText: "wall", expectedWord: expected))
      await checking.value
      XCTAssertNil(h.session.currentWordGuess)
      if mode != 3 { let ended = await h.session.end(); XCTAssertTrue(ended) }
    }
  }

  func testWordGuessSiblingReceiptAndReentrantSettlementCannotExposeText() async throws {
    for sibling in [false, true] {
      let h = try LocalWordSessionHarness()
      defer { h.removeGeneratedFixture() }
      await h.record()
      var revoked = false
      let subscription = h.session.$wordCheckState.sink { state in
        MainActor.assumeIsolated {
          if !sibling, state == .finished(.notMatched) {
            revoked = true
            h.session.viewDidDisappear()
          }
        }
      }
      defer { subscription.cancel() }
      let checking = Task { await h.session.startWordCheck() }
      let request = try await h.recognizer.waitForRequest(index: 0)
      let reported = sibling ? LocalWordRecognitionRequest(operationID: UUID(), tryID: request.tryID,
        fileURL: request.fileURL, expectedWord: request.expectedWord) : request
      h.recognizer.resolve(index: 0, status: .notMatched, receiptRequest: reported,
        wordGuess: LocalWordGuess(completedText: "wall", expectedWord: request.expectedWord))
      await checking.value
      XCTAssertNil(h.session.currentWordGuess)
      if sibling { XCTAssertEqual(h.session.wordCheckState, .cleanupBlocked) }
      else { XCTAssertTrue(revoked); await settle(h.session); XCTAssertEqual(h.session.phase, .ended) }
    }
  }

  func testGuidedWordGuessNeverEntersCurrentPresentationOrSettlement() async throws {
    let h = try GuidedOwnerHarness()
    defer { h.removeGeneratedFixture() }
    let entry = try h.entry("b-beginning-ball")
    let visit = h.review(entry)
    assertGuidedTrue(await h.prepare(entry, visit))
    await h.record()
    let observation = GuidedOwnerObservation()
    let events = h.session.guidedReviewEvents.sink { event in
      MainActor.assumeIsolated { observation.receive(event) }
    }
    defer { events.cancel() }
    let checking = Task { await h.session.startWordCheck() }
    let request = try await h.recognizer.waitForRequest(index: 0)
    h.recognizer.resolve(index: 0, status: .notMatched,
      wordGuess: LocalWordGuess(completedText: "wall", expectedWord: request.expectedWord))
    await checking.value
    XCTAssertEqual(h.session.wordCheckState, .finished(.notMatched))
    XCTAssertNil(h.session.currentWordGuess)
    XCTAssertEqual(observation.settled.first?.status, .notMatched)
    XCTAssertTrue(h.history.entries.isEmpty)
    assertGuidedTrue(await h.leave(visit))
  }
}
