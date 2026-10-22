#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchFeedbackSessionTests: XCTestCase {
    func testOneCurrentQuietClipReplayFeedbackAndRetakeCleanup() async throws {
      let capture = FeedbackCapturer(samples: Array(repeating: 0, count: 1600))
      let player = FeedbackPlayer()
      let processor = FeedbackProcessor()
      defer { capture.remove() }
      let session = await configured(capture, player, processor)
      await session.startRecording()
      session.stopRecording()
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertEqual(session.phase, .review)
      XCTAssertEqual(session.summary?.averagePower, -120)
      XCTAssertTrue(session.canReplay)
      XCTAssertTrue(session.canCheck)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      XCTAssertEqual(player.starts, 1)
      session.checkRecording()
      XCTAssertFalse(session.isPlaying)
      await wait { processor.pending }
      processor.resolve(
        try report(reason: "silence", audio: FeedbackFixture.wav(Array(repeating: 0, count: 1600))))
      await wait { session.phase != .checking }
      guard case .feedback(let feedback) = session.phase else {
        return XCTFail("Expected recording observation")
      }
      XCTAssertEqual(feedback.reason, "silence")
      XCTAssertTrue(session.canReplay)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertEqual(session.attemptsStarted, 1)
      XCTAssertEqual(session.attemptsFinished, 1)
      _ = await session.retake()?.value
      XCTAssertEqual(session.phase, .ready)
      XCTAssertFalse(session.canReplay)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertEqual(session.attemptsFinished, 1)
    }
    func testExplicitOptInAndContextNeededForCheckButLocalRecordingHasNoNetwork() async throws {
      let capture = FeedbackCapturer()
      let processor = FeedbackProcessor()
      defer { capture.remove() }
      let session = makeControlledFeedbackSession(
        capturer: capture, player: FeedbackPlayer(), processor: processor)
      session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
      _ = await session.awaitPendingAudioCleanup()
      await session.startRecording()
      session.stopRecording()
      _ = await session.awaitPendingAudioCleanup()
      session.checkRecording()
      XCTAssertEqual(session.phase, .review)
      XCTAssertEqual(processor.calls, 0)
      session.practiceContext = .child(ageYears: 5)
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertFalse(session.canReplay)  // Setup changes discard the old clip.
      session.localProcessingEnabled = true
      _ = await session.awaitPendingAudioCleanup()
      await session.startRecording()
      session.stopRecording()
      _ = await session.awaitPendingAudioCleanup()
      session.checkRecording()
      XCTAssertFalse(session.canCheck)
      XCTAssertEqual(processor.calls, 0)
      _ = await session.end().value
    }
    func testLatePermissionAfterRetakeOrBackgroundNeverStartsCapture() async {
      for background in [false, true] {
        let capture = FeedbackCapturer()
        capture.delayPermission = true
        defer { capture.remove() }
        let session = await configured(capture, FeedbackPlayer(), FeedbackProcessor())
        let request = Task { await session.startRecording() }
        await wait { capture.permission != nil }
        session.appDidBecomeInactive()
        XCTAssertEqual(session.phase, .requestingPermission)
        if background { session.appDidEnterBackground() } else { _ = await session.retake()?.value }
        capture.permission?.resume(returning: true)
        capture.permission = nil
        await request.value
        XCTAssertEqual(capture.starts, 0)
        XCTAssertEqual(session.phase, .ready)
        XCTAssertEqual(session.attemptsStarted, 1)
        XCTAssertEqual(session.attemptsFinished, 1)
      }
    }
    func testPermissionGrantWhileInactiveWaitsForExplicitActiveEvent() async {
      let capture = FeedbackCapturer()
      capture.delayPermission = true
      defer { capture.remove() }
      let session = await configured(capture, FeedbackPlayer(), FeedbackProcessor())
      let request = Task { await session.startRecording() }
      await wait { capture.permission != nil }
      session.appDidBecomeInactive()
      capture.permission?.resume(returning: true)
      capture.permission = nil
      await request.value
      XCTAssertEqual(capture.starts, 0)
      XCTAssertEqual(session.phase, .requestingPermission)
      session.appDidBecomeActive()
      XCTAssertEqual(capture.starts, 1)
      XCTAssertEqual(session.phase, .recording)
      _ = await session.end().value
      XCTAssertEqual(session.attemptsFinished, 1)
    }
    func testCancelBackgroundInterruptionAndSetupChangeIgnoreLateFeedback() async throws {
      for action in 0..<5 {
        let capture = FeedbackCapturer()
        let player = FeedbackPlayer()
        let processor = FeedbackProcessor()
        defer { capture.remove() }
        let session = await configured(capture, player, processor)
        await session.startRecording()
        session.stopRecording()
        _ = await session.awaitPendingAudioCleanup()
        session.checkRecording()
        await wait { processor.pending }
        switch action {
        case 0: _ = await session.cancelChecking()?.value
        case 1: session.appDidEnterBackground()
        case 2: session.audioWasInterrupted()
        case 3: session.selectedPrompt = ResearchFeedbackCatalog.prompts[1]
        default: session.localProcessingEnabled = false
        }
        _ = await session.awaitPendingAudioCleanup()
        processor.resolve(try report())
        await wait { processor.returned }
        XCTAssertEqual(session.phase, .ready)
        XCTAssertFalse(session.canReplay)
        XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
        XCTAssertEqual(session.attemptsFinished, 1)
      }
    }
    func testAutomaticRecordingCompletionAndReplayCallbackOwnership() async throws {
      let capture = FeedbackCapturer()
      let player = FeedbackPlayer()
      defer { capture.remove() }
      let session = await configured(capture, player, FeedbackProcessor())
      await session.startRecording()
      await capture.finish?(true)
      XCTAssertEqual(session.phase, .review)
      await session.togglePlayback()
      let stale = player.finish
      await session.advance()
      stale?(false)
      XCTAssertEqual(session.phase, .ready)
      XCTAssertFalse(session.isPlaying)
      XCTAssertFalse(session.playbackFailed)
      XCTAssertEqual(session.selectedPrompt, ResearchFeedbackCatalog.prompts[4])
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      _ = await session.end().value
      _ = await session.retake()?.value
      XCTAssertEqual(session.phase, .ended)
    }
    func testDeletionFailureBlocksNewCaptureAndClearsFeedbackWithoutDeletedClaim() async throws {
      let capture = FeedbackCapturer()
      let processor = FeedbackProcessor()
      defer { capture.remove() }
      let session = await configured(capture, FeedbackPlayer(), processor)
      await session.startRecording()
      session.stopRecording()
      _ = await session.awaitPendingAudioCleanup()
      session.checkRecording()
      await wait { processor.pending }
      processor.resolve(try report())
      await wait { session.phase != .checking }
      capture.failDiscard = true
      _ = await session.retake()?.value
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertNil(session.summary)
      XCTAssertFalse(session.canReplay)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      let starts = capture.starts
      await session.startRecording()
      XCTAssertEqual(capture.starts, starts)
      XCTAssertEqual(session.attemptsFinished, 1)
    }
    func testStopDeletionFailureLatchesEvenWhenCancelHasNoActiveRecorder() async {
      let capture = FeedbackCapturer()
      capture.failStopDeletion = true
      defer { capture.remove() }
      let session = await configured(capture, FeedbackPlayer(), FeedbackProcessor())
      await session.startRecording()
      session.stopRecording()
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      let starts = capture.starts
      _ = await session.retake()?.value
      await session.startRecording()
      XCTAssertEqual(capture.starts, starts)
      XCTAssertEqual(session.attemptsFinished, 1)
    }
    private func configured(
      _ capturer: FeedbackCapturer, _ player: FeedbackPlayer, _ processor: FeedbackProcessor
    ) async -> ResearchFeedbackSession {
      let session = makeControlledFeedbackSession(
        capturer: capturer, player: player, processor: processor)
      session.selectedPrompt = ResearchFeedbackCatalog.prompts[3]
      _ = await session.awaitPendingAudioCleanup()
      session.practiceContext = .child(ageYears: 9)
      _ = await session.awaitPendingAudioCleanup()
      session.localProcessingEnabled = true
      _ = await session.awaitPendingAudioCleanup()
      return session
    }
    private func report(reason: String? = nil, audio: Data = FeedbackFixture.wav()) throws
      -> RecordingFeedback
    {
      let body = try FeedbackFixture.body(audio: audio)
      return try FeedbackContract.decode(
        FeedbackFixture.json(FeedbackFixture.response(body, audio: audio, reason: reason)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: false)
    }
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<10000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Expected transition")
    }
  }

  @MainActor
  final class FeedbackCapturer: AudioCapturing {
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
    let url = FileManager.default.temporaryDirectory.appendingPathComponent(
      UUID().uuidString + ".wav")
    let samples: [Int16]
    var starts = 0
    var permissions = 0
    var discards = 0
    var active = false
    var failDiscard = false
    var delayPermission = false
    var failStopDeletion = false
    var permission: CheckedContinuation<Bool, Never>?
    var finish: (@MainActor (Bool) async -> Void)?
    init(samples: [Int16] = Array(repeating: 8192, count: 3200)) { self.samples = samples }
    func requestPermission() async -> Bool {
      permissions += 1
      if delayPermission { return await withCheckedContinuation { permission = $0 } }
      return true
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      starts += 1
      active = true
      finish = onFinish
      try FeedbackFixture.wav(samples).write(to: url)
      ownership.retain(url)
    }
    func stop() throws -> CapturedRecording {
      active = false
      if failStopDeletion {
        ownership.failed(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      return .init(
        url: url, summary: .init(duration: 1, averagePower: -20),
        cleanupOwnerID: ownership.owner(url))
    }
    func cancel() throws {
      if active {
        do {
          if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
          }
          ownership.removed(url)
        } catch {
          ownership.failed(url)
          throw error
        }
      }
      active = false
    }
    func discard(_ recording: CapturedRecording) throws {
      try ownership.require(recording.url)
      discards += 1
      if failDiscard {
        ownership.failed(recording.url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      try FileManager.default.removeItem(at: recording.url)
      ownership.removed(recording.url)
    }
    func remove() { try? FileManager.default.removeItem(at: url) }
  }

  @MainActor
  final class FeedbackProcessor: ResearchFeedbackProcessing {
    var calls = 0
    var recordings: [CapturedRecording] = []
    var attempts: [UUID] = []
    var prompts: [ResearchFeedbackPrompt] = []
    var contexts: [ResearchPracticeContext] = []
    var failure: RecordingFeedbackError?
    var returned = false
    var continuation: CheckedContinuation<RecordingFeedback, Never>?
    var pending: Bool { continuation != nil }
    func process(
      attemptId: UUID, recording: CapturedRecording, prompt: ResearchFeedbackPrompt,
      practiceContext: ResearchPracticeContext
    ) async throws -> RecordingFeedback {
      calls += 1
      recordings.append(recording)
      attempts.append(attemptId)
      prompts.append(prompt)
      contexts.append(practiceContext)
      if let failure { throw failure }
      defer { returned = true }
      return await withCheckedContinuation { continuation = $0 }
    }
    func resolve(_ value: RecordingFeedback) {
      continuation?.resume(returning: value)
      continuation = nil
    }
  }
#endif
