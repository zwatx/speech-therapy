#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchPracticeExampleSessionTests: XCTestCase {
    private let bread = ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" }!
    private func configured(
      _ capture: FeedbackCapturer, _ player: ExamplePlayer, _ loader: ExampleLoader,
      _ store: ExampleStore, _ word: FeedbackProcessor = FeedbackProcessor(),
      _ sound: ExampleSound = ExampleSound()
    ) async -> ResearchFeedbackSession {
      store.files = player.files
      let session = makeControlledFeedbackSession(
        capturer: capture, player: player, processor: word, soundProcessor: sound,
        exampleLoader: loader, exampleStore: store)
      session.selectedPrompt = bread
      _ = await session.awaitPendingAudioCleanup()
      return session
    }
    private func wait(_ condition: @MainActor () -> Bool) async {
      let deadline = ContinuousClock.now + .seconds(3)
      while !condition(), ContinuousClock.now < deadline { await Task.yield() }
      XCTAssertTrue(condition(), "Expected controlled operation to complete")
    }
    private func stopExample(_ session: ResearchFeedbackSession) async {
      session.toggleExample()
      _ = await session.awaitPendingAudioCleanup()
    }
    private func playExample(_ session: ResearchFeedbackSession, player: ExamplePlayer) async {
      _ = await session.awaitPendingAudioCleanup()
      let previousStarts = player.completions.count
      session.toggleExample()
      // Runtime publishes playing before the injected facade resumes from play(). Join
      // registration before tests inspect URLs or invoke the exact completion callback.
      await wait {
        session.exampleState == .playing && player.completions.count == previousStarts + 1
      }
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
    func testNoAutomaticLoadAndListeningWithoutContextOrChecking() async {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store)
      XCTAssertEqual(loader.calls, 0)
      XCTAssertNil(session.practiceContext)
      XCTAssertFalse(session.localProcessingEnabled)
      XCTAssertTrue(session.canPlayExample)
      await playExample(session, player: player)
      XCTAssertEqual(loader.calls, 1)
      XCTAssertEqual(player.urls, [store.ownedURL!])
      XCTAssertFalse(session.isPlaying)
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(capture.permissions, 0)
      XCTAssertEqual(capture.starts, 0)
      await stopExample(session)
      XCTAssertEqual(session.exampleState, .idle)
      XCTAssertNil(store.ownedURL)
    }
    func testSamePlayerSwitchesBothSourcesAndLateCallbacksCannotStopCurrentPlayback() async {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store)
      await record(session)
      await session.togglePlayback()
      let ownCallback = player.completions.last!
      XCTAssertTrue(session.isPlaying)
      session.toggleExample()
      XCTAssertEqual(loader.calls, 0)
      await session.togglePlayback()  // Explicitly stop the current private source.
      await playExample(session, player: player)
      let exampleCallback = player.completions.last!
      ownCallback(false)
      XCTAssertEqual(session.exampleState, .playing)
      XCTAssertFalse(session.playbackFailed)
      player.completions.last?(true)
      await wait { player.state == .idle && store.ownedURL == nil }
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertFalse(session.playbackFailed)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      XCTAssertNil(store.ownedURL)
      exampleCallback(false)
      XCTAssertTrue(session.isPlaying)
      player.completions.last?(true)
      await wait { player.state == .idle && !session.isPlaying }
      XCTAssertFalse(session.playbackFailed)
      XCTAssertEqual(session.exampleState, .idle)
      XCTAssertEqual(player.urls[0], capture.url)
      XCTAssertEqual(player.urls[2], capture.url)
      XCTAssertEqual(capture.discards, 0)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      _ = await session.end().value
    }
    func testListeningPreservesBothIndependentResultsSameTakeAndConsumedClaims() async throws {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      let word = FeedbackProcessor()
      let sound = ExampleSound()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store, word, sound)
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      session.soundAdultConfirmed = true
      session.soundProcessingEnabled = true
      await record(session)
      session.checkRecording()
      await wait { word.pending }
      word.resolve(try wordResult())
      await wait { !session.isProcessing }
      session.checkSound()
      await wait { !session.isProcessing }
      let phase = session.phase
      let soundPhase = session.soundPhase
      await playExample(session, player: player)
      await stopExample(session)
      await session.togglePlayback()
      player.completions.last?(true)
      await wait { player.state == .idle && !session.isPlaying }
      XCTAssertEqual(session.phase, phase)
      XCTAssertEqual(session.soundPhase, soundPhase)
      XCTAssertEqual(session.attemptsStarted, 1)
      XCTAssertEqual(session.checksClaimed, 1)
      XCTAssertFalse(session.canCheck)
      XCTAssertFalse(session.canCheckSound)
      XCTAssertEqual(capture.discards, 0)
      XCTAssertEqual(sound.recordings.map(\.url), [capture.url])
      _ = await session.end().value
    }
    func testPendingLoadInvalidatedByEachLifecycleOrSetupActionHasNoFileOrPlayback() async {
      for action in 0..<8 {
        let capture = FeedbackCapturer()
        let player = ExamplePlayer()
        let loader = ExampleLoader()
        let store = ExampleStore()
        loader.delayed = true
        let session = await configured(capture, player, loader, store)
        session.toggleExample()
        await wait { loader.pending != nil }
        switch action {
        case 0: session.toggleExample()
        case 1: session.selectedPrompt = ResearchFeedbackCatalog.prompts[0]
        case 2: session.practiceContext = .child(ageYears: 9)
        case 3: session.reset()
        case 4: session.appDidBecomeInactive()
        case 5: session.appDidEnterBackground()
        case 6: session.audioWasInterrupted()
        default: _ = session.end()
        }
        loader.release()
        await wait { loader.returned }
        _ = await session.awaitPendingAudioCleanup()
        XCTAssertTrue(loader.cancelled)
        XCTAssertEqual(store.writes, 0)
        XCTAssertEqual(player.urls.count, 0)
        XCTAssertEqual(session.exampleState, .idle)
        XCTAssertNil(store.ownedURL)
        capture.remove()
        store.forceRemove()
        _ = await session.end().value
      }
    }
    func testOwnReplayCancelsPendingExampleAndLateLoadCannotReplaceIt() async {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      loader.delayed = true
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store)
      await record(session)
      session.toggleExample()
      await wait { loader.pending != nil }
      await session.togglePlayback()
      XCTAssertTrue(player.urls.isEmpty)
      session.toggleExample()  // Stop the loading source explicitly before the later replay tap.
      loader.release()
      await wait { loader.returned }
      _ = await session.awaitPendingAudioCleanup()
      // Cancellation is complete; replay is a fresh explicit tap, never queued by cancellation.
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      XCTAssertEqual(player.urls, [capture.url])
      XCTAssertEqual(store.writes, 0)
      _ = await session.end().value
    }
    func testRecordAndExplicitWordOrSoundChecksStopExamplesAndRefuseNewListeningWhileBusy()
      async throws
    {
      for action in 0..<3 {
        let capture = FeedbackCapturer()
        let player = ExamplePlayer()
        let loader = ExampleLoader()
        let store = ExampleStore()
        let word = FeedbackProcessor()
        let sound = ExampleSound()
        defer {
          capture.remove()
          store.forceRemove()
        }
        let session = await configured(capture, player, loader, store, word, sound)
        session.practiceContext = .adult
        session.localProcessingEnabled = true
        session.soundAdultConfirmed = true
        session.soundProcessingEnabled = true
        if action != 0 { await record(session) }
        await playExample(session, player: player)
        if action == 0 {
          await session.startRecording()
          XCTAssertEqual(session.phase, .recording)
        } else if action == 1 {
          session.checkRecording()
          await wait { word.pending }
        } else {
          sound.delayed = true
          session.checkSound()
          await wait { sound.pending != nil }
        }
        XCTAssertNil(store.ownedURL)
        XCTAssertEqual(session.exampleState, .idle)
        XCTAssertFalse(session.canPlayExample)
        session.toggleExample()
        XCTAssertEqual(loader.calls, 1)
        if action == 1 {
          word.resolve(try wordResult())
          await wait { !session.isProcessing }
        }
        if action == 2 {
          sound.release()
          await wait { !session.isProcessing }
        }
        _ = await session.end().value
      }
    }
    func testSharedServerPauseStillAllowsPublicExampleAndOwnReplay() async throws {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      let word = FeedbackProcessor()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store, word)
      session.practiceContext = .adult
      session.localProcessingEnabled = true
      await record(session)
      session.checkRecording()
      await wait { word.pending }
      word.resolve(try wordResult(reason: "cleanup_unconfirmed"))
      await wait { !session.isProcessing }
      let phase = session.phase
      XCTAssertTrue(session.sharedProcessingPaused)
      await playExample(session, player: player)
      await stopExample(session)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      XCTAssertEqual(session.phase, phase)
      XCTAssertTrue(session.sharedProcessingPaused)
      _ = await session.end().value
    }
    func testExampleRemovalFailureRetainsExactFileBlocksAccumulationAndAllowsOwnReplayThenRetry()
      async
    {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store)
      await record(session)
      await playExample(session, player: player)
      let held = store.ownedURL
      store.failRemove = true
      await stopExample(session)
      XCTAssertTrue(session.exampleCleanupBlocked)
      XCTAssertEqual(session.exampleState, .failed(.cleanupFailed))
      XCTAssertEqual(store.ownedURL, held)
      XCTAssertFalse(session.canPlayExample)
      session.toggleExample()
      XCTAssertEqual(loader.calls, 1)
      XCTAssertEqual(store.writes, 1)
      await session.togglePlayback()
      XCTAssertFalse(session.isPlaying)
      XCTAssertFalse(session.canReplay)
      store.failRemove = false
      _ = await session.retryExampleCleanup().value
      XCTAssertNil(store.ownedURL)
      XCTAssertFalse(session.exampleCleanupBlocked)
      XCTAssertTrue(session.canPlayExample)
      await session.togglePlayback()
      XCTAssertTrue(session.isPlaying)
      XCTAssertEqual(player.urls.last, capture.url)
      XCTAssertEqual(capture.discards, 0)
      XCTAssertEqual(session.phase, .review)
      await session.togglePlayback()
      await playExample(session, player: player)
      XCTAssertEqual(store.writes, 2)
      _ = await session.end().value
    }
    func testLoaderHashWriteAndPlaybackFailuresPreservePrivateTakeAndCleanupPublicFiles() async {
      for action in 0..<4 {
        let capture = FeedbackCapturer()
        let player = ExamplePlayer()
        let loader = ExampleLoader()
        let store = ExampleStore()
        defer {
          capture.remove()
          store.forceRemove()
        }
        let session = await configured(capture, player, loader, store)
        await record(session)
        if action == 0 { loader.failure = .unavailable }
        if action == 1 { loader.invalidData = true }
        if action == 2 { store.failAfterWrite = true }
        if action == 3 { player.fail = true }
        session.toggleExample()
        await wait {
          if case .failed = session.exampleState { return true }
          return false
        }
        XCTAssertNil(store.ownedURL)
        XCTAssertFalse(session.exampleCleanupBlocked)
        XCTAssertEqual(session.phase, .review)
        XCTAssertTrue(session.canReplay)
        XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
        XCTAssertEqual(capture.discards, 0)
        _ = await session.end().value
      }
    }
    func testPlaybackCompletionReleasesOnlyExampleAndStaleFailureCannotChangeNewLoad() async {
      let capture = FeedbackCapturer()
      let player = ExamplePlayer()
      let loader = ExampleLoader()
      let store = ExampleStore()
      defer {
        capture.remove()
        store.forceRemove()
      }
      let session = await configured(capture, player, loader, store)
      await record(session)
      await playExample(session, player: player)
      let old = player.completions.last!
      old(true)
      await wait { player.state == .idle && store.ownedURL == nil }
      _ = await session.awaitPendingAudioCleanup()
      XCTAssertNil(store.ownedURL)
      XCTAssertEqual(session.phase, .review)
      XCTAssertEqual(session.exampleState, .idle)
      await playExample(session, player: player)
      let current = store.ownedURL
      old(false)
      XCTAssertEqual(session.exampleState, .playing)
      XCTAssertEqual(store.ownedURL, current)
      player.completions.last?(false)
      await wait { session.exampleState == .failed(.playbackFailed) && store.ownedURL == nil }
      XCTAssertEqual(session.exampleState, .failed(.playbackFailed))
      XCTAssertNil(store.ownedURL)
      XCTAssertTrue(session.canReplay)
      _ = await session.end().value
    }
    func testRealPublicStoreOwnsOneExactFileAndRejectsForeignRemoval() throws {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      defer { try? FileManager.default.removeItem(at: directory) }
      let store = ResearchPracticeExampleStore(
        directory: directory, fileOwnership: ProcessAudioFileOwnership())
      let audio = FeedbackFixture.wav()
      let url = try store.write(audio)
      XCTAssertTrue(url.lastPathComponent.hasPrefix("cadence-public-example-"))
      XCTAssertEqual(try Data(contentsOf: url), audio)
      XCTAssertThrowsError(try store.write(audio))
      XCTAssertThrowsError(try store.remove(directory.appendingPathComponent("foreign.wav")))
      XCTAssertEqual(store.ownedURL, url)
      try store.remove(url)
      XCTAssertNil(store.ownedURL)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }
    func testPrivateCleanupBlockedAndPendingPermissionCannotStartExampleLoad() async {
      for permission in [false, true] {
        let capture = FeedbackCapturer()
        let player = ExamplePlayer()
        let loader = ExampleLoader()
        let store = ExampleStore()
        defer {
          capture.remove()
          store.forceRemove()
        }
        let session = await configured(capture, player, loader, store)
        if permission {
          capture.delayPermission = true
          let task = Task { await session.startRecording() }
          await wait { capture.permission != nil }
          session.toggleExample()
          XCTAssertEqual(loader.calls, 0)
          capture.permission?.resume(returning: false)
          capture.permission = nil
          await task.value
        } else {
          await record(session)
          capture.failDiscard = true
          _ = await session.retake()?.value
          XCTAssertEqual(session.phase, .cleanupBlocked)
          session.toggleExample()
          XCTAssertEqual(loader.calls, 0)
        }
        XCTAssertFalse(session.exampleCleanupBlocked)
        capture.failDiscard = false
        if session.hasLocalMediaCleanupIssue { _ = await session.retryAudioCleanup().value }
        _ = await session.end().value
      }
    }
  }

  @MainActor
  private final class ExampleLoader: ResearchPracticeExampleLoading {
    let bytes = FeedbackFixture.wav()
    var calls = 0, delayed = false, returned = false, cancelled = false, invalidData = false
    var failure: ResearchPracticeExampleError?
    var pending: CheckedContinuation<Data, Never>?
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      .init(
        sourceWord: prompt.word, author: "Generated test", licenseId: "Generated fixture",
        licenseURL: URL(string: "https://example.invalid/generated")!,
        sourceURL: URL(string: "https://example.invalid/generated")!,
        attribution: "Generated PCM; no licensed human reference", changes: "Generated test only",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: FeedbackContract.sha(bytes), sampleCount: 3200, isGeneratedFixture: true)
    }
    func load(example: ResearchPracticeExample) async throws -> Data {
      calls += 1
      if let failure { throw failure }
      let data = delayed ? await withCheckedContinuation { pending = $0 } : bytes
      cancelled = Task.isCancelled
      returned = true
      return invalidData ? Data() : data
    }
    func release() {
      pending?.resume(returning: bytes)
      pending = nil
    }
  }
  @MainActor
  private final class ExamplePlayer: AcknowledgedPracticeAudioPlaying {
    let files = ProcessAudioFileOwnership()
    private let gate = AudioHardwareOwnership()
    private let controls = ExampleDriverControls()
    private let runtime: SystemAcknowledgedPracticeAudioPlayer
    var urls: [URL] = [], completions: [@MainActor (Bool) -> Void] = []
    var fail = false
    var stops: Int { controls.stopCount }
    var state: PracticePlaybackRuntimeState { runtime.state }
    var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> { runtime.statePublisher }
    init() {
      let controls = self.controls
      runtime = SystemAcknowledgedPracticeAudioPlayer(ownership: gate, fileOwnership: files) {
        operation, finished in
        controls.make(operation.id) { finished(operation, $0) }
      }
    }
    func play(
      id: UUID, url: URL,
      onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
    ) async throws {
      controls.configure(id, fail: fail)
      try await runtime.play(id: id, url: url, onFinish: onFinish)
      urls.append(url)
      let controls = self.controls
      completions.append { controls.finish(id, success: $0) }
    }
    func requestStop(id: UUID) -> PracticePlaybackCleanup? { runtime.requestStop(id: id) }
    func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { runtime.retryCleanup(id: id) }
    func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
      runtime.completedCleanupRetry(id: id)
    }
  }
  private final class ExampleDriverControls: @unchecked Sendable {
    private let lock = NSLock()
    private var failures: [UUID: Bool] = [:]
    private var drivers: [UUID: ExampleInertDriver] = [:]
    var stopCount: Int { lock.withLock { drivers.values.reduce(0) { $0 + $1.stops } } }
    func configure(_ id: UUID, fail: Bool) { lock.withLock { failures[id] = fail } }
    func make(_ id: UUID, finished: @escaping @Sendable (Bool) -> Void) -> ExampleInertDriver {
      lock.withLock {
        let driver = ExampleInertDriver(fail: failures[id] == true, finished: finished)
        drivers[id] = driver
        return driver
      }
    }
    func finish(_ id: UUID, success: Bool) {
      let driver = lock.withLock { drivers[id] }
      driver?.finish(success)
    }
  }
  private final class ExampleInertDriver: PracticePlaybackDriver, @unchecked Sendable {
    private let lock = NSLock()
    private let fail: Bool
    private let finished: @Sendable (Bool) -> Void
    private var stopCalls = 0
    var stops: Int { lock.withLock { stopCalls } }
    init(fail: Bool, finished: @escaping @Sendable (Bool) -> Void) {
      self.fail = fail
      self.finished = finished
    }
    func finish(_ success: Bool) { finished(success) }
    func activate() throws {}
    func prepare() throws -> Bool { !fail }
    func play() throws -> Bool { true }
    func stop() throws { lock.withLock { stopCalls += 1 } }
    func releasePlaybackResources() throws {}
    func deactivate() throws {}
  }
  @MainActor
  private final class ExampleStore: ResearchPracticeExampleStoring {
    var files = ProcessAudioFileOwnership()
    private var owner: UUID?
    var ownedURL: URL?, writes = 0, failRemove = false, failAfterWrite = false
    func write(_ data: Data) throws -> URL {
      guard ownedURL == nil else { throw ResearchPracticeExampleError.storageFailed }
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-public-example-" + UUID().uuidString + ".wav")
      try data.write(to: url)
      ownedURL = url
      let owner = UUID()
      self.owner = owner
      files.retain(url, owner: owner)
      writes += 1
      if failAfterWrite { throw ResearchPracticeExampleError.storageFailed }
      return url
    }
    func remove(_ url: URL) throws {
      guard ownedURL == url, let owner else { throw ResearchPracticeExampleError.cleanupFailed }
      do {
        guard !failRemove, files.canRemove(url, owner: owner) else {
          throw ResearchPracticeExampleError.cleanupFailed
        }
        try FileManager.default.removeItem(at: url)
        files.didRemove(url, owner: owner)
        ownedURL = nil
        self.owner = nil
      } catch {
        files.registerCleanupRecovery(owner: owner) { [self] in
          do {
            try remove(url)
            return ownedURL == nil
          } catch { return false }
        }
        throw error
      }
    }
    func forceRemove() {
      if let ownedURL, let owner, files.canRemove(ownedURL, owner: owner) {
        do {
          try FileManager.default.removeItem(at: ownedURL)
          files.didRemove(ownedURL, owner: owner)
          self.ownedURL = nil
          self.owner = nil
        } catch {}
      }
    }
  }
  @MainActor
  private final class ExampleSound: ResearchSoundProcessing {
    var recordings: [CapturedRecording] = [], delayed = false
    var pending: CheckedContinuation<ResearchSoundObservation, Never>?
    let result = ResearchSoundObservation(
      status: .observedModelPreference, reason: "model_preferred_candidate", preference: .wPath)
    func declaration() async throws -> ResearchSoundDeclaration {
      .init(
        serverNonce: "33333333-3333-4333-8333-333333333333",
        csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    }
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
      if delayed { return await withCheckedContinuation { pending = $0 } }
      return result
    }
    func release() {
      pending?.resume(returning: result)
      pending = nil
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws {}
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    {}
  }
#endif
