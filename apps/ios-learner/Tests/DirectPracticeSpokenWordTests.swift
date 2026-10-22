import Combine
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class DirectPracticeSpokenWordTests: XCTestCase {
  func testInjectedLegacyMediaDoesNotGainAnImplicitSpeechDriver() async {
    let capture = SpokenSessionCapturer()
    let session = DirectPracticeSession(capturer: capture, player: SpokenSessionPlayer())
    XCTAssertTrue(session.showsSpokenWordControls)
    XCTAssertFalse(session.canToggleSpokenWord)
    await session.toggleSpokenWord()
    XCTAssertEqual(capture.permissions, 0)
    XCTAssertEqual(session.spokenWordState, .idle)
    let ended = await session.end()
    XCTAssertTrue(ended)
  }

  func testHearKeepsTakeCheckAndHistoryUntouchedAndRequiresExplicitStopBeforeOtherMedia() async {
    let capture = SpokenSessionCapturer()
    let player = SpokenSessionPlayer()
    let recognizer = SpokenSessionRecognizer()
    let history = PracticeParticipationStore(
      fileURL: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString))
    let driver = SpokenWordDriverControl()
    let runtime = owner(driver)
    let session = DirectPracticeSession(
      capturer: capture, player: player, history: history, wordRecognizer: recognizer,
      spokenWord: runtime)
    await session.startRecording()
    session.stopRecording()
    let take = session.latestTry
    let phase = session.phase
    let hear = Task { await session.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    XCTAssertFalse(session.canCheckWordsInLatestTry)
    XCTAssertFalse(session.canRecordAnotherTry)
    await session.startWordCheck()
    await session.togglePlayback()
    await session.recordAnotherTry()
    XCTAssertEqual(recognizer.checks, 0)
    XCTAssertEqual(player.plays, 0)
    XCTAssertEqual(capture.starts, 1)
    XCTAssertEqual(session.latestTry, take)
    XCTAssertEqual(session.phase, phase)
    XCTAssertEqual(session.wordCheckState, .idle)
    XCTAssertEqual(session.attemptCount, 1)
    XCTAssertEqual(session.completedWords, 0)
    XCTAssertNil(session.participationCompletion)
    XCTAssertTrue(history.entries.isEmpty)
    let stop = Task { await session.toggleSpokenWord() }
    await observed(driver.stopped)
    XCTAssertEqual(capture.discards, 0)
    XCTAssertFalse(session.canCheckWordsInLatestTry)
    driver.send(.cancelled)
    await stop.value
    XCTAssertEqual(session.latestTry, take)
    XCTAssertTrue(session.canCheckWordsInLatestTry)
    XCTAssertEqual(recognizer.checks, 0)
    XCTAssertEqual(player.plays, 0)
    XCTAssertTrue(history.entries.isEmpty)
    _ = await session.end()
  }

  func testCloseJoinsHeldSpokenTerminalBeforeDiscardAndCannotStartQueuedRecording() async {
    let capture = SpokenSessionCapturer()
    let driver = SpokenWordDriverControl()
    let session = DirectPracticeSession(
      capturer: capture, player: SpokenSessionPlayer(), spokenWord: owner(driver))
    await session.startRecording()
    session.stopRecording()
    let hear = Task { await session.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    let close = Task { await session.end() }
    await observed(driver.stopped)
    XCTAssertTrue(session.closeRequested)
    XCTAssertNotEqual(session.phase, .ended)
    XCTAssertEqual(capture.discards, 0)
    XCTAssertNotNil(session.latestTry)
    XCTAssertTrue(session.showsSpokenWordControls)
    await session.startRecording()
    XCTAssertEqual(capture.starts, 1)
    driver.send(.cancelled)
    let ended = await close.value
    XCTAssertTrue(ended)
    XCTAssertEqual(session.phase, .ended)
    XCTAssertEqual(capture.discards, 1)
    XCTAssertNil(session.latestTry)
    XCTAssertEqual(capture.permissions, 1)
  }

  func testBackgroundStopsWithoutAutoResumeAndPreservesCleanupOrdering() async {
    let capture = SpokenSessionCapturer()
    let driver = SpokenWordDriverControl()
    let session = DirectPracticeSession(
      capturer: capture, player: SpokenSessionPlayer(), spokenWord: owner(driver))
    await session.startRecording()
    session.stopRecording()
    let hear = Task { await session.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    let ready = expectation(description: "background cleanup returned ready")
    let subscription = session.$phase.dropFirst().sink { phase in
      if phase == .ready { ready.fulfill() }
    }
    session.appDidEnterBackground()
    await observed(driver.stopped)
    XCTAssertEqual(capture.discards, 0)
    driver.send(.cancelled)
    await observed(ready)
    XCTAssertEqual(session.spokenWordState, .idle)
    XCTAssertEqual(capture.discards, 1)
    XCTAssertEqual(capture.starts, 1)
    XCTAssertEqual(driver.factoryCalls, 1)
    XCTAssertEqual(session.completedWords, 0)
    subscription.cancel()
    _ = await session.end()
  }

  func testFailedStopKeepsTakeAndProcessRetryReconcilesWithoutReplayingOrChecking() async {
    let capture = SpokenSessionCapturer()
    let driver = SpokenWordDriverControl(failDeactivationOnce: true)
    let gate = AudioHardwareOwnership()
    let runtime = owner(driver, gate: gate)
    let session = DirectPracticeSession(
      capturer: capture, player: SpokenSessionPlayer(), spokenWord: runtime)
    await session.startRecording()
    session.stopRecording()
    let take = session.latestTry
    let hear = Task { await session.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    let stop = Task { await session.toggleSpokenWord() }
    await observed(driver.stopped)
    driver.send(.cancelled)
    await stop.value
    XCTAssertTrue(session.canRetrySpokenWordStop)
    XCTAssertTrue(session.actionsDisabled)
    XCTAssertEqual(session.latestTry, take)
    XCTAssertEqual(capture.discards, 0)
    let process = AudioCleanupRecoveryModel(ownership: gate, files: ProcessAudioFileOwnership())
    let recovered = await process.retry().value
    XCTAssertTrue(recovered)
    XCTAssertFalse(session.canRetrySpokenWordStop)
    XCTAssertFalse(session.actionsDisabled)
    XCTAssertEqual(session.latestTry, take)
    XCTAssertEqual(capture.discards, 0)
    XCTAssertEqual(driver.factoryCalls, 1)
    _ = await session.end()
  }

  func testSynchronousDisappearDuringErrorPublicationRevokesBeforeRuntimeRegistration() async {
    let driver = SpokenWordDriverControl()
    let session = DirectPracticeSession(
      capturer: SpokenSessionCapturer(), player: SpokenSessionPlayer(), spokenWord: owner(driver))
    var revoked = false
    let subscription = session.objectWillChange.sink {
      MainActor.assumeIsolated {
        guard !revoked else { return }
        revoked = true
        session.viewDidDisappear()
      }
    }
    await session.toggleSpokenWord()
    let ended = await session.end()
    XCTAssertTrue(ended)
    XCTAssertTrue(revoked)
    XCTAssertEqual(driver.factoryCalls, 0)
    subscription.cancel()
  }

  func testDedicatedRetryJoinsExistingFailedCloseBeforeReturning() async {
    let capture = SpokenSessionCapturer()
    let driver = SpokenWordDriverControl(failDeactivationOnce: true)
    let session = DirectPracticeSession(
      capturer: capture, player: SpokenSessionPlayer(), spokenWord: owner(driver))
    await session.startRecording()
    session.stopRecording()
    let hear = Task { await session.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    let close = Task { await session.end() }
    await observed(driver.stopped)
    driver.send(.cancelled)
    let ended = await close.value
    XCTAssertFalse(ended)
    XCTAssertEqual(capture.discards, 0)
    XCTAssertTrue(session.closeRequested)
    await session.retrySpokenWordStop()
    XCTAssertEqual(session.phase, .ended)
    XCTAssertNil(session.latestTry)
    XCTAssertEqual(capture.discards, 1)
    XCTAssertEqual(driver.factoryCalls, 1)
  }

  func testFailedCloseRetainsRouteProducerUntilProcessRetryJoinsExactEnd() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let driver = SpokenWordDriverControl(failDeactivationOnce: true)
    let recognizer = HeldSpokenSessionRuntime()
    defer { recognizer.release() }
    var capture: SpokenSessionCapturer? = SpokenSessionCapturer(directory: directory, files: files)
    let url = capture!.url
    let discarded = expectation(description: "retained producer removed exact take")
    capture!.onDiscard = { discarded.fulfill() }
    var session: DirectPracticeSession? = DirectPracticeSession(
      capturer: capture!, player: SpokenSessionPlayer(), wordRecognizer: recognizer,
      spokenWord: owner(driver, gate: gate),
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    weak var weakSession = session
    weak var weakCapture = capture
    await session!.startRecording()
    session!.stopRecording()
    let hear = Task { @MainActor [weak session] in await session?.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    let close = Task { @MainActor [weak session] in await session?.end() }
    await observed(driver.stopped)
    driver.send(.cancelled)
    let ended = await close.value
    XCTAssertEqual(ended, false)
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    session = nil
    capture = nil
    // The exact process lease callback, not a retained view or this test, owns recovery.
    XCTAssertNotNil(weakSession)
    XCTAssertNotNil(weakCapture)
    XCTAssertEqual(weakCapture?.discards, 0)
    let recovery = AudioCleanupRecoveryModel(ownership: gate, files: files)
    let retry = recovery.retry()
    await observed(recognizer.entered)
    XCTAssertTrue(recovery.isRetrying)
    XCTAssertNotEqual(weakSession?.phase, .ended)
    XCTAssertEqual(recognizer.releases, 1)
    recognizer.release()
    let recovered = await retry.value
    XCTAssertTrue(recovered)
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    await observed(discarded)
    XCTAssertFalse(files.protectedURLs.contains(url))
    XCTAssertNil(gate.currentLease)
    if let retained = weakSession {
      let joined = await retained.end()
      XCTAssertTrue(joined)
      XCTAssertEqual(retained.phase, .ended)
    }
  }

  func testProcessSpokenRecoveryCannotHideEndFileCleanupFailure() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let driver = SpokenWordDriverControl(failDeactivationOnce: true)
    let capture = SpokenSessionCapturer(directory: directory, files: files)
    capture.failDiscard = true
    var session: DirectPracticeSession? = DirectPracticeSession(
      capturer: capture, player: SpokenSessionPlayer(), spokenWord: owner(driver, gate: gate),
      cleanupHardwareOwnership: gate, cleanupFileOwnership: files)
    await session!.startRecording()
    session!.stopRecording()
    let hear = Task { @MainActor [weak session] in await session?.toggleSpokenWord() }
    await observed(driver.enqueued)
    driver.send(.started)
    await hear.value
    let close = Task { @MainActor [weak session] in await session?.end() }
    await observed(driver.stopped)
    driver.send(.cancelled)
    _ = await close.value
    session = nil
    let recovery = AudioCleanupRecoveryModel(ownership: gate, files: files)
    let recovered = await recovery.retry().value
    XCTAssertFalse(recovered)
    XCTAssertNil(gate.currentLease)
    XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
    XCTAssertEqual(files.pendingCleanupOwners.count, 1)
    XCTAssertTrue(recovery.snapshot.hasPendingCleanup)
    capture.failDiscard = false
    let removed = await recovery.retry().value
    XCTAssertTrue(removed)
    XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
  }

  func testLateOldFailureCannotClearSuccessorOrOverwriteItsNote() async {
    let spoken = DelayedSpokenSessionOwner()
    let session = DirectPracticeSession(
      capturer: SpokenSessionCapturer(), player: SpokenSessionPlayer(), spokenWord: spoken)
    await session.startRecording()
    session.stopRecording()
    let oldWord = session.currentPrompt.word
    let old = Task { await session.toggleSpokenWord() }
    await observed(spoken.firstEntered)
    spoken.finishWithoutReturningFirstStart()
    await session.continuePractice()
    XCTAssertNotEqual(session.currentPrompt.word, oldWord)
    let next = Task { await session.toggleSpokenWord() }
    await observed(spoken.secondEntered)
    let nextState = session.spokenWordState
    spoken.returnOldFailure()
    await old.value
    XCTAssertEqual(session.spokenWordState, nextState)
    XCTAssertNil(session.spokenWordStatusNote?.range(of: "isn't available"))
    spoken.finishSecond()
    await next.value
    _ = await session.end()
  }

  private func owner(
    _ driver: SpokenWordDriverControl, gate: AudioHardwareOwnership = AudioHardwareOwnership()
  ) -> PracticeSpokenWordRuntime {
    PracticeSpokenWordRuntime(ownership: gate) { operation, event in driver.make(operation, event) }
  }
  private func observed(_ expectation: XCTestExpectation) async {
    let result = await XCTWaiter.fulfillment(of: [expectation], timeout: 2)
    XCTAssertEqual(result, .completed)
  }
}

@MainActor
private final class SpokenSessionCapturer: AudioCapturing {
  private let subject = CurrentValueSubject<CaptureCleanupState, Never>(.idle)
  var cleanupState: CaptureCleanupState { subject.value }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    subject.eraseToAnyPublisher()
  }
  var permissions = 0
  var starts = 0
  var discards = 0
  var failDiscard = false
  let url: URL
  var onDiscard: (@MainActor () -> Void)?
  private let files: ProcessAudioFileOwnership
  private let writesFile: Bool
  private var ownerID = UUID()
  init(directory: URL? = nil, files: ProcessAudioFileOwnership = ProcessAudioFileOwnership()) {
    self.files = files
    writesFile = directory != nil
    url = (directory ?? FileManager.default.temporaryDirectory).appendingPathComponent(
      UUID().uuidString)
  }
  func requestPermission() async -> Bool {
    permissions += 1
    return true
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    starts += 1
    ownerID = UUID()
    files.retain(url, owner: ownerID)
    if writesFile { try Data("controlled stopped take".utf8).write(to: url) }
  }
  func stop() throws -> CapturedRecording {
    .init(url: url, summary: .init(duration: 1, averagePower: -20), cleanupOwnerID: ownerID)
  }
  func cancel() throws {}
  func discard(_ recording: CapturedRecording) throws {
    guard recording.url == url, files.canRemove(url, owner: ownerID) else {
      throw AudioCaptureError.recordingNotOwned
    }
    if failDiscard {
      let id = ownerID
      files.registerCleanupRecovery(owner: id) { [self] in
        retryCleanup(operationID: id).allRequestedFilesRemoved
      }
      subject.send(.init(hardwareBlockedOperationID: nil, fileBlockedOwnerIDs: [id]))
      throw AudioCaptureError.couldNotDeleteTemporaryRecording
    }
    if writesFile { try FileManager.default.removeItem(at: url) }
    files.didRemove(url, owner: ownerID)
    discards += 1
    subject.send(.idle)
    onDiscard?()
  }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    guard operationID == ownerID else { return .init(operationID: operationID, result: .refused) }
    do {
      try discard(
        .init(url: url, summary: .init(duration: 1, averagePower: -20), cleanupOwnerID: ownerID))
      return .init(operationID: ownerID, result: .released)
    } catch { return .init(operationID: ownerID, result: .hardwareReleasedFilesRetained) }
  }
}

@MainActor
private final class HeldSpokenSessionRuntime: LocalWordRecognizing, LocalWordRuntimeReleasing {
  let entered = XCTestExpectation(description: "End model disposal held")
  private var continuation: CheckedContinuation<Bool, Never>?
  private var held = true
  private(set) var releases = 0
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
    continuation?.resume(returning: true)
    continuation = nil
  }
}

@MainActor
private final class SpokenSessionPlayer: AcknowledgedPracticeAudioPlaying {
  var state: PracticePlaybackRuntimeState { .idle }
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
    Just(.idle).eraseToAnyPublisher()
  }
  var plays = 0
  func play(
    id: UUID, url: URL, onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws { plays += 1 }
  func requestStop(id: UUID) -> PracticePlaybackCleanup? { nil }
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { nil }
}

@MainActor
private final class SpokenSessionRecognizer: LocalWordRecognizing {
  var checks = 0
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    checks += 1
    return .init(request: request, status: .unavailable, cleanupConfirmed: true)
  }
  func cancel(operationID: UUID) {}
}

/// Delays only the caller's start error after publishing an idle operation. It exercises
/// old waiter/successor eligibility without replacing runtime cleanup acceptance tests.
@MainActor
private final class DelayedSpokenSessionOwner: PracticeSpokenWordSpeaking {
  private let subject = CurrentValueSubject<PracticeSpokenWordState, Never>(.idle)
  var state: PracticeSpokenWordState { subject.value }
  var statePublisher: AnyPublisher<PracticeSpokenWordState, Never> { subject.eraseToAnyPublisher() }
  let firstEntered = XCTestExpectation(description: "old start held")
  let secondEntered = XCTestExpectation(description: "successor start held")
  private var starts = 0
  private var first: CheckedContinuation<Void, Error>?
  private var second: CheckedContinuation<Void, Error>?
  func start(_ operation: PracticeSpokenWordOperation) async throws {
    starts += 1
    subject.send(.preparing(operation))
    try await withCheckedThrowingContinuation { continuation in
      if starts == 1 {
        first = continuation
        firstEntered.fulfill()
      } else {
        second = continuation
        secondEntered.fulfill()
      }
    }
  }
  func finishWithoutReturningFirstStart() { subject.send(.idle) }
  func returnOldFailure() {
    first?.resume(throwing: PracticeSpokenWordError.unavailable)
    first = nil
  }
  func finishSecond() {
    subject.send(.idle)
    second?.resume()
    second = nil
  }
  func requestStop(id: UUID) -> PracticeSpokenWordCleanup? { nil }
  func retryCleanup(id: UUID) -> PracticeSpokenWordCleanup? { nil }
  func completedCleanupRetry(id: UUID) -> PracticeSpokenWordReceipt? { nil }
}
