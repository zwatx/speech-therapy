#if DEBUG && targetEnvironment(simulator)
  import AVFoundation
  import Combine
  import CryptoKit
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Opt-in inference over permitted child-speech fixtures. Capture is file-backed
  /// unless the separately authorized microphone-replay cases are explicitly selected.
  @MainActor
  final class GuidedResearchLiveIntegrationTests: XCTestCase {
    func testFirstDeclaredSoundThroughPracticeAndFreshRecheck() async throws {
      try await run(fixtureIndex: 0)
    }

    func testSecondDeclaredSoundThroughPracticeAndFreshRecheck() async throws {
      try await run(fixtureIndex: 1)
    }

    // Explicit boundary isolation: real client/model and lifecycle, invented word match.
    // These never replace or automatically rescue the native-recognition cases above.
    func testFirstDeclaredSoundRealModelWithWordRecognitionDoubled() async throws {
      try await run(fixtureIndex: 0, wordRecognitionDoubled: true)
    }

    func testSecondDeclaredSoundRealModelWithWordRecognitionDoubled() async throws {
      try await run(fixtureIndex: 1, wordRecognitionDoubled: true)
    }

    func testCompleteCanonicalWordSoundBThroughNativeModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 0, fixtureSet: .completeCanonical)
    }

    func testCompleteCanonicalWordSoundPThroughNativeModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 1, fixtureSet: .completeCanonical)
    }

    func testCompleteCanonicalWordSoundMThroughNativeModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 2, fixtureSet: .completeCanonical)
    }

    func testCompleteCanonicalWordSoundTThroughNativeModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 3, fixtureSet: .completeCanonical)
    }

    func testNativeWordThenCancelRealModelWaitsForCleanup() async throws {
      try await run(fixtureIndex: 1, fixtureSet: .completeCanonical, cancelFirstModel: true)
    }

    func testControlledMicrophoneSoundPThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 1, fixtureSet: .completeCanonical, microphoneReplay: true)
    }

    func testControlledMicrophoneSoundTThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 3, fixtureSet: .completeCanonical, microphoneReplay: true)
    }

    // Remaining sounds from the same fixed B/P/M/T plan, without replacement.
    func testControlledMicrophoneSoundBThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 0, fixtureSet: .completeCanonical, microphoneReplay: true)
    }

    func testControlledMicrophoneSoundMThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 2, fixtureSet: .completeCanonical, microphoneReplay: true)
    }

    func testControlledMicrophoneSoundNThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 0, fixtureSet: .additionalCanonical, microphoneReplay: true)
    }

    func testControlledMicrophoneSoundKThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 1, fixtureSet: .additionalCanonical, microphoneReplay: true)
    }

    func testControlledMicrophoneSoundLThroughModelPracticeAndRecheck() async throws {
      try await run(fixtureIndex: 2, fixtureSet: .additionalCanonical, microphoneReplay: true)
    }

    private func run(
      fixtureIndex: Int, wordRecognitionDoubled: Bool = false, fixtureSet: FixtureSet = .sparse,
      cancelFirstModel: Bool = false, microphoneReplay: Bool = false
    ) async throws {
      let env = ProcessInfo.processInfo.environment
      guard env["CADENCE_GUIDED_MODEL_LOOPBACK"] == "1",
        ControlledUnitTestHost.isEnabled,
        ControlledUnitTestHost.appInitializedWithInertRoot
      else { throw XCTSkip("Explicit controlled local-model integration only.") }
      if wordRecognitionDoubled && env["CADENCE_GUIDED_MODEL_BOUNDARY"] != "1" {
        throw XCTSkip("Explicit real-model boundary isolation only.")
      }
      if fixtureSet == .completeCanonical && env["CADENCE_GUIDED_COMPLETE_WORD"] != "1" {
        throw XCTSkip("Explicit complete-canonical-word native integration only.")
      }
      if fixtureSet == .additionalCanonical && env["CADENCE_GUIDED_ADDITIONAL_WORD"] != "1" {
        throw XCTSkip("Explicit additional-canonical-word native integration only.")
      }
      if microphoneReplay && env["CADENCE_GUIDED_MICROPHONE_REPLAY"] != "1" {
        throw XCTSkip("Explicit human-authorized controlled microphone replay only.")
      }
      guard !microphoneReplay || (!wordRecognitionDoubled && !cancelFirstModel) else {
        throw LiveFailure.pipelineIncomplete
      }
      let bundle = Bundle(for: Self.self)
      let base = try XCTUnwrap(bundle.resourceURL?.appendingPathComponent(fixtureSet.folderName))
      let manifestBytes = try Data(contentsOf: base.appendingPathComponent("manifest.json"))
      guard digest(manifestBytes) == fixtureSet.manifestSHA else {
        XCTFail("Declared fixture manifest changed.")
        throw LiveFailure.pipelineIncomplete
      }
      let all = try JSONDecoder().decode(FixtureManifest.self, from: manifestBytes)
      guard all.cases.indices.contains(fixtureIndex) else { throw LiveFailure.pipelineIncomplete }
      let manifest = all.cases[fixtureIndex]
      guard (6...12).contains(manifest.ageYears) else { throw LiveFailure.pipelineIncomplete }
      let fixtureURL = base.appendingPathComponent(manifest.fileName)
      let bytes = try Data(contentsOf: fixtureURL)
      guard digest(bytes) == manifest.audioSha256,
        let duration = LocalWordWAVGate.duration(bytes: bytes)
      else {
        XCTFail("Fixed real fixture binding failed.")
        return
      }
      let entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == manifest.entryID })
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      let capture: any CaptureProbe
      let stimulus: AVAudioPlayer?
      if microphoneReplay {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "controlled-microphone-\(UUID())")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        capture = SystemCaptureProbe(directory: directory, hardware: hardware, files: files)
        stimulus = try AVAudioPlayer(data: bytes)
      } else {
        capture = FileCapture(
          bytes: bytes, duration: duration, averagePower: manifest.averagePower, hardware: hardware,
          files: files)
        stimulus = nil
      }
      defer { stimulus?.stop() }
      let wordRecognizer: any LocalWordRecognizing =
        wordRecognitionDoubled
        ? LocalGuidedGeneratedRecognizer(files: files, holdsResult: false)
        : BundledLocalWordRecognizerFactory.make(ownership: files)
      let processor = ObservedRealProcessor()
      processor.expectedRecording = { capture.stoppedRecordings.last }
      processor.files = files
      let model = GuidedResearchModelRecognizer(
        wordRecognizer: wordRecognizer,
        processor: processor, ownership: files)
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "live-guided-history-\(UUID())")
      let history = PracticeParticipationStore(
        fileURL: directory.appendingPathComponent("history.json"))
      let player = ResearchAcknowledgedPlaybackUITestFixture(
        completion: .explicitStop, ownership: hardware, fileOwnership: files)
      let media = DirectPracticeSession(
        capturer: capture, player: player, history: history, managedForGuided: true,
        wordRecognizer: model, cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
      let session = LocalGuidedReviewSession(history: history, media: media, researchModel: model)
      addTeardownBlock { @MainActor in
        let closed = await session.close()
        if let system = capture as? SystemCaptureProbe {
          let diagnostic: [String: Any] = [
            "permissionGranted": system.permissionGranted,
            "completedRecordings": system.createdURLs.count,
            "recordingDurationsSeconds": system.summaries.map(\.duration),
            "recordingPowerDecibels": system.summaries.map(\.averagePower),
            "inputPortTypes": system.inputPortTypes,
            "outputPortTypes": system.outputPortTypes,
            "cleanupConfirmed": closed && files.protectedURLs.isEmpty
              && system.createdURLs.allSatisfy { !FileManager.default.fileExists(atPath: $0.path) },
          ]
          let attachment = XCTAttachment(
            data: try JSONSerialization.data(withJSONObject: diagnostic, options: [.sortedKeys]),
            uniformTypeIdentifier: "public.json")
          attachment.name = "controlled-microphone-diagnostic"
          attachment.lifetime = .keepAlways
          self.add(attachment)
        }
      }
      XCTAssertTrue(session.replaceSetupEntry(at: 0, with: entry))
      XCTAssertTrue(session.configureResearchModel(enabled: true, ageYears: manifest.ageYears))
      await session.startInitialReview()
      if cancelFirstModel {
        guard let capture = capture as? FileCapture else { throw LiveFailure.pipelineIncomplete }
        try await cancelRealModel(
          session, model: model, processor: processor, capture: capture, files: files,
          history: history)
        return
      }
      try await check(session, model: model, stimulus: stimulus)
      let first = try XCTUnwrap(session.ledger?.initialRound.rows[0])
      await session.advanceVisit()
      for _ in 0..<4 { await session.skipVisit() }
      XCTAssertEqual(session.ledger?.stage, .choosingPractice)
      XCTAssertEqual(model.observations.count, 1)
      session.togglePracticeSelection(entryID: entry.id)
      await session.startPractice()
      try await check(session, model: model, stimulus: stimulus)
      await session.advanceVisit()
      XCTAssertEqual(session.ledger?.stage, .readyToRecheck)
      XCTAssertEqual(history.entries.map(\.soundID), [entry.soundID])
      await session.startRecheck()
      try await check(session, model: model, stimulus: stimulus)
      await session.advanceVisit()
      for _ in 0..<4 { await session.skipVisit() }
      let ledger = try XCTUnwrap(session.ledger)
      XCTAssertEqual(ledger.stage, .completed)
      XCTAssertEqual(ledger.initialRound.rows[0], first)
      let recheck = try XCTUnwrap(ledger.recheckRound?.rows[0])
      XCTAssertNotEqual(first.firstSubmission?.tryID, recheck.firstSubmission?.tryID)
      XCTAssertNotEqual(first.firstSubmission?.operationID, recheck.firstSubmission?.operationID)
      XCTAssertNotNil(session.researchModelNote(for: first))
      XCTAssertNotNil(session.researchModelNote(for: recheck))
      XCTAssertEqual(model.observations.count, 3)
      XCTAssertTrue(files.protectedURLs.isEmpty)
      XCTAssertTrue(
        capture.createdURLs.allSatisfy { !FileManager.default.fileExists(atPath: $0.path) })
      let closed = await session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(
        digest(try Data(contentsOf: fixtureURL)),
        manifest.audioSha256)
      // Aggregate only: omit speech, probabilities, participant IDs and private paths.
      let processed = model.observations.values.filter {
        if case .processedUnverified = $0.outcome { return true }
        return false
      }
      let fresh =
        processed.count == 3 && Set(processed.map(\.request.tryID)).count == 3
        && Set(processed.map(\.request.operationID)).count == 3
      let cleanup =
        closed && files.protectedURLs.isEmpty
        && capture.createdURLs.allSatisfy { !FileManager.default.fileExists(atPath: $0.path) }
      let unchanged =
        digest(try Data(contentsOf: fixtureURL))
        == manifest.audioSha256
      let completed =
        processed.count == 3 && fresh && cleanup && unchanged
        && ledger.stage == .completed && ledger.initialRound.rows[0] == first
        && history.entries.count == 1
        && first.firstSubmission?.tryID != recheck.firstSubmission?.tryID
      let aggregate: [String: Any] = [
        "target": entry.targetPhone, "realModelCalls": processed.count,
        "freshTakeIDs": fresh, "sourceAudioReplay": true, "microphoneUsed": microphoneReplay,
        "systemRecorderUsed": microphoneReplay,
        "wordRecognitionDoubled": wordRecognitionDoubled,
        "fixtureSet": fixtureSet.folderName,
        "learnerJudgments": false, "cleanupConfirmed": cleanup,
        "sourceAudioUnchanged": unchanged, "completed": completed,
      ]
      let encoded = try JSONSerialization.data(withJSONObject: aggregate, options: [.sortedKeys])
      print("CADENCE_GUIDED_MODEL_LIVE=" + String(decoding: encoded, as: UTF8.self))
      let attachment = XCTAttachment(data: encoded, uniformTypeIdentifier: "public.json")
      attachment.name = "guided-model-lifecycle-aggregate"
      attachment.lifetime = .keepAlways
      add(attachment)
      guard completed else { throw LiveFailure.pipelineIncomplete }
    }

    private func check(
      _ session: LocalGuidedReviewSession, model: GuidedResearchModelRecognizer,
      stimulus: AVAudioPlayer?
    ) async throws {
      await session.media.startRecording()
      XCTAssertEqual(session.media.phase, .recording)
      guard session.media.phase == .recording else {
        throw LiveFailure.pipelineIncomplete
      }
      if let stimulus {
        // Bounded, explicitly authorized test input. Actual recorder/framework are untouched.
        try await Task.sleep(for: .milliseconds(250))
        stimulus.currentTime = 0
        guard stimulus.play() else { throw LiveFailure.pipelineIncomplete }
        try await Task.sleep(for: .milliseconds(Int(ceil((stimulus.duration + 0.35) * 1_000))))
        stimulus.stop()
      }
      session.media.stopRecording()
      let take = try XCTUnwrap(session.media.latestTry)
      await session.checkCurrentWord()
      guard session.media.wordCheckState == .finished(.matched),
        let observation = model.observations.values.first(where: { $0.request.tryID == take.id }),
        case .processedUnverified = observation.outcome
      else {
        let last = model.latestObservationOperationID.flatMap { model.observations[$0]?.outcome }
        XCTFail(
          "Real pipeline incomplete: word=\(session.media.wordCheckState), model=\(String(describing: last)), paused=\(model.modelCallsPaused)."
        )
        throw LiveFailure.pipelineIncomplete
      }
    }

    private func digest(_ data: Data) -> String {
      SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func cancelRealModel(
      _ session: LocalGuidedReviewSession, model: GuidedResearchModelRecognizer,
      processor: ObservedRealProcessor, capture: FileCapture, files: ProcessAudioFileOwnership,
      history: PracticeParticipationStore
    ) async throws {
      await session.media.startRecording()
      session.media.stopRecording()
      let take = try XCTUnwrap(session.media.latestTry)
      let url = try XCTUnwrap(capture.createdURLs.last)
      let owner = try XCTUnwrap(capture.ownership.owner(of: url))
      let checkTask = Task { @MainActor in await session.checkCurrentWord() }
      let deadline = ContinuousClock.now.advanced(by: .seconds(20))
      while processor.callCount == 0, ContinuousClock.now < deadline {
        try await Task.sleep(for: .milliseconds(10))
      }
      guard processor.callCount == 1 else {
        await checkTask.value
        XCTFail("Real model was not reached through native word admission.")
        throw LiveFailure.pipelineIncomplete
      }
      session.media.cancelWordCheck()
      let heldWhileCancelling =
        !files.canRemove(url, owner: owner)
        && FileManager.default.fileExists(atPath: url.path)
        && session.media.wordCheckState == .cancelling
        && processor.result == nil
      XCTAssertTrue(heldWhileCancelling)
      await checkTask.value
      guard let result = processor.result, case .processedResearch = result else {
        XCTFail("The real request did not finish model processing after cancellation.")
        throw LiveFailure.pipelineIncomplete
      }
      let cancelled =
        session.media.wordCheckState == .finished(.cancelled)
        && session.ledger?.initialRound.rows[0].state == .finished(.cancelled)
        && model.observations.values.contains {
          $0.request.tryID == take.id && $0.outcome == .cancelled
        }
      XCTAssertTrue(cancelled)
      XCTAssertFalse(model.modelCallsPaused)
      let releasedAfterResponse =
        files.canRemove(url, owner: owner)
        && FileManager.default.fileExists(atPath: url.path)
      XCTAssertTrue(releasedAfterResponse)
      XCTAssertTrue(history.entries.isEmpty)
      let closed = await session.close()
      let cleaned =
        closed && files.protectedURLs.isEmpty
        && capture.createdURLs.allSatisfy { !FileManager.default.fileExists(atPath: $0.path) }
      let completed =
        heldWhileCancelling && cancelled && releasedAfterResponse && cleaned
        && !model.modelCallsPaused && history.entries.isEmpty
      let aggregate: [String: Any] = [
        "completed": completed, "realModelCalls": processor.callCount,
        "wordRecognitionDoubled": false, "microphoneUsed": false,
        "sourceAudioReplay": true, "learnerJudgments": false,
        "heldWhileCancelling": heldWhileCancelling, "cancelledResult": cancelled,
        "borrowReleasedAfterResponse": releasedAfterResponse,
        "cleanupConfirmed": cleaned,
      ]
      let attachment = XCTAttachment(
        data: try JSONSerialization.data(withJSONObject: aggregate, options: [.sortedKeys]),
        uniformTypeIdentifier: "public.json")
      attachment.name = "real-model-cancellation-aggregate"
      attachment.lifetime = .keepAlways
      add(attachment)
      guard completed else { throw LiveFailure.pipelineIncomplete }
    }

    /// Observes only the existing client's bounded outcome; it does not invent a receipt.
    private final class ObservedRealProcessor: ResearchAssessmentProcessing {
      private(set) var callCount = 0
      private(set) var result: ResearchAssessmentOutcome?
      var expectedRecording: (() -> CapturedRecording?)?
      var files: ProcessAudioFileOwnership?
      func process(
        attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
      ) async throws -> ResearchAssessmentOutcome {
        callCount += 1
        XCTAssertEqual(recording, try XCTUnwrap(expectedRecording?()))
        let owner = try XCTUnwrap(recording.cleanupOwnerID)
        XCTAssertFalse(files?.canRemove(recording.url, owner: owner) ?? true)
        let outcome = try await ResearchAssessmentClient().process(
          attemptId: attemptId, recording: recording, entry: entry, ageYears: ageYears)
        result = outcome
        return outcome
      }
    }

    private enum LiveFailure: Error { case pipelineIncomplete }
    private enum FixtureSet: Equatable {
      case sparse, completeCanonical, additionalCanonical
      var folderName: String {
        switch self {
        case .sparse: "GuidedModelFixture"
        case .completeCanonical: "GuidedCompleteWordFixture"
        case .additionalCanonical: "GuidedAdditionalWordFixture"
        }
      }
      var manifestSHA: String {
        switch self {
        case .sparse: "5692ac418a2180eac1bc82fe0cdf5b968d4d3f3f2136f2717e883e15ac0e9f19"
        case .completeCanonical: "3bc44959834cfe73fdc4f94a5926905e726fcc8de786b2e234aa44b5a298b303"
        case .additionalCanonical: "db726303694ce467fb47fc3f3651efc6c8f84bf3c26d426ad74ede89c942743c"
        }
      }
    }
    private struct FixtureManifest: Decodable { let cases: [Fixture] }
    private struct Fixture: Decodable {
      let entryID: String
      let fileName: String
      let ageYears: Int
      let audioSha256: String
      let averagePower: Float
    }

    private protocol CaptureProbe: AudioCapturing {
      var createdURLs: [URL] { get }
    }

    /// Instrumentation only: delegates permission, driver, summary and cleanup unchanged.
    private final class SystemCaptureProbe: CaptureProbe {
      private let core: SystemAudioCapturer
      private(set) var permissionGranted = false
      private(set) var createdURLs: [URL] = []
      private(set) var summaries: [CaptureSummary] = []
      private(set) var inputPortTypes: [[String]] = []
      private(set) var outputPortTypes: [[String]] = []
      init(directory: URL, hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership) {
        core = SystemAudioCapturer(
          recordingStore: TemporaryRecordingStore(directory: directory),
          fileOwnership: files, hardwareOwnership: hardware)
      }
      var cleanupState: CaptureCleanupState { core.cleanupState }
      var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
        core.cleanupStatePublisher
      }
      func requestPermission() async -> Bool {
        permissionGranted = await core.requestPermission()
        return permissionGranted
      }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        try core.start(onFinish: onFinish)
        let route = AVAudioSession.sharedInstance().currentRoute
        inputPortTypes.append(route.inputs.map { $0.portType.rawValue })
        outputPortTypes.append(route.outputs.map { $0.portType.rawValue })
      }
      func stop() throws -> CapturedRecording {
        let recording = try core.stop()
        createdURLs.append(recording.url)
        summaries.append(recording.summary)
        return recording
      }
      func cancel() throws { try core.cancel() }
      func discard(_ recording: CapturedRecording) throws { try core.discard(recording) }
      func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
        core.retryCleanup(operationID: operationID)
      }
      func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
        core.completedFileCleanup(operationID: operationID)
      }
    }

    /// Actual temporary-file ownership and deletion; permission and capture are file-backed.
    private final class FileCapture: CaptureProbe {
      let ownership: ResearchGeneratedCaptureFileOwnership
      let bytes: Data
      let duration: Double
      let averagePower: Float
      var active: URL?
      var createdURLs: [URL] = []
      init(
        bytes: Data, duration: Double, averagePower: Float, hardware: AudioHardwareOwnership,
        files: ProcessAudioFileOwnership
      ) {
        self.bytes = bytes
        self.duration = duration
        self.averagePower = averagePower
        ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
      }
      var cleanupState: CaptureCleanupState { ownership.cleanupState }
      var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
        ownership.cleanupStatePublisher
      }
      func requestPermission() async -> Bool { true }
      func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
        guard active == nil else { throw AudioCaptureError.couldNotStart }
        let url = ownership.directory.appendingPathComponent("take-\(UUID()).wav")
        try ownership.begin(url)
        do { try bytes.write(to: url, options: .withoutOverwriting) } catch {
          try? ownership.cancel(url)
          throw error
        }
        createdURLs.append(url)
        active = url
      }
      func stop() throws -> CapturedRecording {
        guard let url = active else { throw AudioCaptureError.couldNotReadRecording }
        let owner = try ownership.stop(url)
        active = nil
        return .init(
          url: url, summary: .init(duration: duration, averagePower: averagePower),
          cleanupOwnerID: owner)
      }
      func cancel() throws {
        if let url = active {
          try ownership.cancel(url)
          active = nil
        }
      }
      func discard(_ recording: CapturedRecording) throws { try ownership.remove(recording.url) }
      func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
        ownership.retryCleanup(operationID: operationID)
      }
      func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
        ownership.completedFileCleanup(operationID: operationID)
      }
    }
  }
#endif
