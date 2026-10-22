import Combine
import CryptoKit
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class ReleaseGuidedPublicWordTests: XCTestCase {
  func testReleaseFiveWordReviewPracticeAndFreshRecheckWithActualBundledRecognizer() async throws {
    #if !DEBUG && targetEnvironment(simulator)
      let environment = ProcessInfo.processInfo.environment
      guard environment["CADENCE_RELEASE_GUIDED_PUBLIC_WORD"] == "1",
        environment["SIMULATOR_UDID"] == "132DD629-A694-4D98-A0BB-B828676DD698",
        Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner"
      else { throw XCTSkip("Explicit Release guided public-word case only.") }
    #else
      throw XCTSkip("Release dedicated simulator case only.")
    #endif
    let result = await ReleaseGuidedWordCase.run(bundle: Bundle(for: Self.self))
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    let data = try encoder.encode(result)
    guard let aggregate = String(data: data, encoding: .utf8) else {
      return XCTFail("Closed guided aggregate encoding failed.")
    }
    print("CADENCE_RELEASE_GUIDED_WORD_V1=" + aggregate)
    XCTAssertTrue(
      result.fixtureAdmitted && result.fixtureUnchanged, "Public fixture admission changed.")
    XCTAssertTrue(
      result.actualDefaultFactory && result.flowCompleted, "Guided public-word sequence failed.")
    XCTAssertTrue(
      result.captureCount == 12 && result.qualityPassedCount == 12, "Exact capture gates failed.")
    XCTAssertTrue(
      result.requestCount == 10 && result.receiptCount == 10, "Exact bounded checks failed.")
    XCTAssertTrue(
      result.matchedCount == 2 && result.notMatchedCount == 8, "Fixed word comparisons failed.")
    XCTAssertTrue(
      result.initialFrozen && result.freshIdentities && result.exactHistory,
      "Exact guided bindings failed.")
    XCTAssertTrue(
      result.cleanupConfirmed && result.deletionConfirmed && result.noPlayback,
      "Exact cleanup failed.")
    XCTAssertTrue(result.elapsedMilliseconds >= 0, "Finite whole-case time not established.")
  }
}

/// One known public word and four deliberate prompt mismatches, repeated in a fresh round.
/// Capture hardware/permission are doubled. No microphone, playback, UI or clinical claim.
private struct ReleaseGuidedWordReceipt: Encodable {
  let schema = "ReleaseGuidedPublicWordV1"
  let captureHardwareDoubled = true
  var fixtureAdmitted = false, fixtureUnchanged = false, actualDefaultFactory = false
  var flowCompleted = false, initialFrozen = false, freshIdentities = false, exactHistory = false
  var cleanupConfirmed = false, deletionConfirmed = false, noPlayback = false
  var captureCount = 0, qualityPassedCount = 0, requestCount = 0, receiptCount = 0
  var matchedCount = 0, notMatchedCount = 0, elapsedMilliseconds = -1
}

private enum ReleaseGuidedWordFailure: Error { case admission, sequence, unexpectedPlayback }

private struct ReleaseGuidedWordFixture {
  static let sha = "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f"
  let url: URL
  let bytes: Data
  init(bundle: Bundle) throws {
    let app = Bundle.main.bundleURL
    guard bundle.bundleIdentifier == "com.cadence.speechtherapy.learner.tests",
      bundle.bundleURL.pathExtension == "xctest", let root = bundle.resourceURL,
      let resources = Bundle.main.resourceURL?.appendingPathComponent(
        "WhisperResources", isDirectory: true),
      BundledLocalWordRecognizerFactory.isCanonicalAppResourceLocation(
        appURL: app, resourceURL: resources, resolvedAppURL: app.resolvingSymlinksInPath(),
        resolvedResourceURL: resources.resolvingSymlinksInPath(),
        bundleIdentifier: Bundle.main.bundleIdentifier),
      Bundle.main.object(forInfoDictionaryKey: "CFBundleExecutable") as? String == "CadenceLearner",
      Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String == "1",
      Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String == "0.1.0",
      Bundle.main.object(forInfoDictionaryKey: "DTPlatformName") as? String == "iphonesimulator",
      Bundle.main.object(forInfoDictionaryKey: "CFBundleSupportedPlatforms") as? [String] == [
        "iPhoneSimulator"
      ],
      BundledLocalWordRecognizerFactory.isUnlinkedDirectory(app),
      BundledLocalWordRecognizerFactory.isUnlinkedDirectory(resources)
    else { throw ReleaseGuidedWordFailure.admission }
    let manifest = resources.appendingPathComponent("RESOURCE-MANIFEST-v1.json")
    let metadata = try manifest.resourceValues(forKeys: [
      .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey,
    ])
    guard metadata.isRegularFile == true, metadata.isSymbolicLink != true,
      metadata.fileSize == 4067,
      manifest.resolvingSymlinksInPath() == manifest.standardizedFileURL
    else { throw ReleaseGuidedWordFailure.admission }
    let manifestBytes = try Data(contentsOf: manifest)
    guard manifestBytes.count == 4067,
      releaseGuidedWordDigest(manifestBytes)
        == "3a5685954ba13a09b6430ed360afbb8c871033e9d2e90388568ef51a90b64b3d"
    else { throw ReleaseGuidedWordFailure.admission }
    url = root.appendingPathComponent("PublicFixture/public-example-bread.wav")
    let values = try url.resourceValues(forKeys: [
      .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey,
    ])
    guard values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == 17912,
      url.resolvingSymlinksInPath() == url.standardizedFileURL
    else { throw ReleaseGuidedWordFailure.admission }
    bytes = try Data(contentsOf: url)
    guard bytes.count == 17912, releaseGuidedWordDigest(bytes) == Self.sha,
      LocalWordWAVGate.duration(bytes: bytes) != nil
    else { throw ReleaseGuidedWordFailure.admission }
  }
}

@MainActor
private enum ReleaseGuidedWordCase {
  // Unknown cleanup retains the actual owners. Teardown never releases a borrow by hand.
  private static var held: [ReleaseGuidedWordResources] = []
  static func run(bundle: Bundle) async -> ReleaseGuidedWordReceipt {
    var result = ReleaseGuidedWordReceipt()
    let clock = ContinuousClock()
    let started = clock.now
    var resources: ReleaseGuidedWordResources?
    do {
      let fixture = try ReleaseGuidedWordFixture(bundle: bundle)
      result.fixtureAdmitted = true
      let owner = try ReleaseGuidedWordResources(fixture: fixture)
      resources = owner
      result.actualDefaultFactory = true
      try await owner.exercise()
      result.flowCompleted = true
    } catch {
      // Only closed counters and acknowledgements leave this case.
    }
    if let owner = resources {
      let checksBeforeClose = owner.word.requests.count
      let closed = await owner.flow.close()
      result.captureCount = owner.capture.recordings.count
      result.qualityPassedCount = owner.qualityPassedCount
      result.requestCount = owner.word.requests.count
      result.receiptCount = owner.word.receipts.count
      result.matchedCount = owner.word.receipts.filter { $0.status == .matched }.count
      result.notMatchedCount = owner.word.receipts.filter { $0.status == .notMatched }.count
      result.initialFrozen = owner.initialFrozen
      result.freshIdentities = owner.freshIdentities
      result.exactHistory = owner.exactHistory
      result.noPlayback = owner.player.playCalls == 0
      result.fixtureUnchanged =
        (try? Data(contentsOf: owner.fixture.url)).map(releaseGuidedWordDigest)
        == ReleaseGuidedWordFixture.sha
      let removed = owner.capture.recordings.allSatisfy { recording in
        guard let id = recording.cleanupOwnerID else { return false }
        return owner.capture.completedFileCleanup(operationID: id)?.allRequestedFilesRemoved == true
          && !FileManager.default.fileExists(atPath: recording.url.path)
      }
      result.cleanupConfirmed =
        closed && owner.flow.media.phase == .ended && owner.flow.media.tries.isEmpty
        && owner.capture.cleanupState == .idle && owner.hardware.currentLease == nil
        && owner.player.state == .idle
        && owner.files.protectedURLs.isEmpty && owner.files.pendingCleanupOwners.isEmpty
        && owner.word.receipts.allSatisfy { $0.cleanupConfirmed }
        && owner.word.requests.count == checksBeforeClose
      if result.cleanupConfirmed && removed {
        do {
          let manager = FileManager.default
          let remaining = try manager.contentsOfDirectory(
            at: owner.directory, includingPropertiesForKeys: nil)
          let history = owner.directory.appendingPathComponent("history.json")
          guard remaining.allSatisfy({ $0.standardizedFileURL == history.standardizedFileURL }),
            owner.capture.driver.createdURLs.allSatisfy({ !manager.fileExists(atPath: $0.path) })
          else { throw ReleaseGuidedWordFailure.sequence }
          if manager.fileExists(atPath: history.path) { try manager.removeItem(at: history) }
          guard try manager.contentsOfDirectory(atPath: owner.directory.path).isEmpty else {
            throw ReleaseGuidedWordFailure.sequence
          }
          try FileManager.default.removeItem(at: owner.directory)
          result.deletionConfirmed = !FileManager.default.fileExists(atPath: owner.directory.path)
        } catch {
          // Preserve a failed deletion without retry.
        }
      }
      if !result.cleanupConfirmed || !result.deletionConfirmed { held.append(owner) }
    }
    let elapsed = started.duration(to: clock.now).components
    let milliseconds = Double(elapsed.seconds) * 1000 + Double(elapsed.attoseconds) / 1e15
    if milliseconds.isFinite, milliseconds >= 0, milliseconds < Double(Int.max) {
      result.elapsedMilliseconds = Int(milliseconds)
    }
    return result
  }
}

@MainActor
private final class ReleaseGuidedWordResources {
  let fixture: ReleaseGuidedWordFixture
  let directory: URL
  let files = ProcessAudioFileOwnership()
  let hardware = AudioHardwareOwnership()
  let capture: ReleaseGuidedWordCapture
  let player = ReleaseGuidedWordIdlePlayer()
  let word: ReleaseGuidedWordObserver
  let history: PracticeParticipationStore
  let flow: LocalGuidedReviewSession
  private(set) var qualityPassedCount = 0
  private(set) var initialFrozen = false, freshIdentities = false, exactHistory = false

  init(fixture: ReleaseGuidedWordFixture) throws {
    self.fixture = fixture
    directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(
      at: directory, withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])
    capture = ReleaseGuidedWordCapture(
      directory: directory, fixture: fixture.bytes,
      files: files, hardware: hardware)
    word = ReleaseGuidedWordObserver(files: files)
    history = PracticeParticipationStore(fileURL: directory.appendingPathComponent("history.json"))
    let media = DirectPracticeSession(
      capturer: capture, player: player, history: history,
      managedForGuided: true, wordRecognizer: word,
      cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
    flow = LocalGuidedReviewSession(history: history, media: media)
  }

  private func require(_ condition: Bool) throws {
    guard condition, !Task.isCancelled else { throw ReleaseGuidedWordFailure.sequence }
  }

  private func record() async throws -> UUID {
    let calls = word.requests.count
    await flow.media.startRecording()
    try require(flow.media.phase == .recording)
    flow.media.stopRecording()
    guard let take = flow.media.latestTry else { throw ReleaseGuidedWordFailure.sequence }
    try require(
      take.assessment == .acceptable && CaptureQualityAssessor().assess(take.summary) == .acceptable
        && take.summary.duration.isFinite && take.summary.averagePower.isFinite
        && word.requests.count == calls && player.playCalls == 0)
    qualityPassedCount += 1
    return take.id
  }

  private func reviewRound(frozenInitial: LocalGuidedReviewRound? = nil) async throws {
    let saved = history.entries
    for (index, entry) in flow.setupEntries.enumerated() {
      let expectedCalls = index + (frozenInitial == nil ? 0 : 5)
      try require(word.requests.count == expectedCalls && word.receipts.count == expectedCalls)
      if let frozenInitial { try require(flow.ledger?.initialRound == frozenInitial) }
      guard let visit = flow.ledger?.activeReviewVisit else {
        throw ReleaseGuidedWordFailure.sequence
      }
      try require(visit.entryID == entry.id && flow.media.currentPrompt == entry.prompt)
      let takeID = try await record()
      let before = word.requests.count
      try require(before < 10 && word.receipts.count == before)
      await flow.checkCurrentWord()
      guard word.requests.count == before + 1, word.receipts.count == before + 1,
        let request = word.requests.last, let receipt = word.receipts.last,
        let row = flow.ledger?.activeRound?.rows[index]
      else { throw ReleaseGuidedWordFailure.sequence }
      let expected: LocalWordRecognitionStatus = index == 0 ? .matched : .notMatched
      try require(
        receipt.request == request && receipt.cleanupConfirmed && receipt.status == expected
          && request.tryID == takeID && request.fileURL == capture.recordings.last?.url
          && request.expectedWord == entry.prompt.word && row.entry == entry
          && row.firstSubmission
            == .init(visit: visit, operationID: request.operationID, tryID: takeID)
          && row.state == .finished(index == 0 ? .matched : .notMatched)
          && flow.media.wordCheckState == .finished(expected)
          && !flow.media.canCheckWordsInLatestTry && !flow.playerPresentation.canCheckWords)
      try require(
        releaseGuidedWordDigest(try Data(contentsOf: request.fileURL))
          == ReleaseGuidedWordFixture.sha)
      await flow.checkCurrentWord()
      try require(word.requests.count == before + 1)
      await flow.advanceVisit()
      try require(
        !FileManager.default.fileExists(atPath: request.fileURL.path)
          && files.protectedURLs.isEmpty && hardware.currentLease == nil && history.entries == saved
          && word.requests.count == before + 1)
      if let frozenInitial { try require(flow.ledger?.initialRound == frozenInitial) }
    }
  }

  func exercise() async throws {
    guard let bread = PracticeLibrary.entries().first(where: { $0.id == "r-middle-bread" }) else {
      throw ReleaseGuidedWordFailure.admission
    }
    try require(flow.replaceSetupEntry(at: 0, with: bread))
    try require(
      flow.setupEntries.map(\.id) == [
        "r-middle-bread", "p-beginning-pig", "m-beginning-moon",
        "t-beginning-tiger", "d-beginning-dog",
      ])
    await flow.startInitialReview()
    try await reviewRound()
    guard let first = flow.ledger?.initialRound else { throw ReleaseGuidedWordFailure.sequence }
    try require(
      first.isFinished && flow.ledger?.stage == .choosingPractice
        && flow.practiceSelectionIDs.isEmpty && history.entries.isEmpty)
    let selected = [bread, flow.setupEntries[1]]
    for entry in selected { flow.togglePracticeSelection(entryID: entry.id) }
    try require(flow.practiceSelectionIDs == selected.map(\.id))
    await flow.startPractice()
    try require(word.requests.count == 5 && flow.ledger?.initialRound == first)
    var visits: [LocalGuidedPracticeVisit] = []
    var practiceTakes: [UUID] = []
    for entry in selected {
      guard let visit = flow.ledger?.activePracticeVisit else {
        throw ReleaseGuidedWordFailure.sequence
      }
      try require(
        visit.entryID == entry.id && flow.media.currentPrompt == entry.prompt
          && flow.playerPresentation.firstObservationNote != nil)
      visits.append(visit)
      practiceTakes.append(try await record())
      await flow.advanceVisit()
      try require(word.requests.count == 5 && flow.ledger?.initialRound == first)
    }
    try require(flow.ledger?.stage == .readyToRecheck && history.entries.count == 2)
    let saved = history.entries
    await flow.startRecheck()
    try require(word.requests.count == 5 && flow.ledger?.initialRound == first)
    try await reviewRound(frozenInitial: first)
    guard let ledger = flow.ledger, let recheck = ledger.recheckRound,
      let practiceID = ledger.practiceID
    else {
      throw ReleaseGuidedWordFailure.sequence
    }
    let checks = (first.rows + recheck.rows).compactMap(\.firstSubmission)
    let identities =
      checks.flatMap { [$0.visit.visitID, $0.operationID, $0.tryID] }
      + visits.map(\.visitID) + practiceTakes + [
        ledger.workflowID, first.id, recheck.id, practiceID,
      ]
    freshIdentities =
      checks.count == 10 && Set(identities).count == identities.count
      && ledger.practiceRows.compactMap(\.freshTryID) == practiceTakes
    initialFrozen = ledger.initialRound == first && ledger.pairedRows.map(\.initial) == first.rows
    exactHistory =
      history.entries == saved && history.entries.count == 2
      && Set(history.entries.map(\.id)) == Set(visits.map(\.visitID))
      && zip(visits, selected).allSatisfy { visit, entry in
        history.entries.contains {
          $0.id == visit.visitID && $0.soundID == entry.soundID && $0.wordCount == 1
        }
      }
      && PracticeParticipationStore(fileURL: directory.appendingPathComponent("history.json"))
        .entries == saved
    try require(
      ledger.stage == .completed && recheck.isFinished
        && recheck.rows.map(\.entry) == first.rows.map(\.entry)
        && initialFrozen && freshIdentities && exactHistory && capture.recordings.count == 12
        && Set(capture.recordings.map(\.url)).count == 12 && capture.permissionRequests == 12
        && capture.driver.createdURLs.count == 12 && capture.driver.allCopiesConfirmed
        && word.requests.count == 10 && word.receipts.count == 10 && word.cancellations == 0)
  }
}

@MainActor
private final class ReleaseGuidedWordCapture: AudioCapturing {
  let driver: ReleaseGuidedWordFileDriver
  private let core: SystemAudioCapturer
  private(set) var permissionRequests = 0
  private(set) var recordings: [CapturedRecording] = []
  var cleanupState: CaptureCleanupState { core.cleanupState }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> { core.cleanupStatePublisher }
  init(
    directory: URL, fixture: Data, files: ProcessAudioFileOwnership,
    hardware: AudioHardwareOwnership
  ) {
    let driver = ReleaseGuidedWordFileDriver(bytes: fixture)
    self.driver = driver
    core = SystemAudioCapturer(
      recordingStore: TemporaryRecordingStore(directory: directory),
      fileOwnership: files, hardwareOwnership: hardware, driverFactory: { driver })
  }
  func requestPermission() async -> Bool {
    permissionRequests += 1
    return true
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    try core.start(onFinish: onFinish)
  }
  func stop() throws -> CapturedRecording {
    let recording = try core.stop()
    recordings.append(recording)
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

@MainActor
private final class ReleaseGuidedWordFileDriver: CaptureHardwareDriver {
  let bytes: Data
  private(set) var createdURLs: [URL] = []
  private(set) var allCopiesConfirmed = true
  init(bytes: Data) { self.bytes = bytes }
  func configureActivate() throws {}
  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    createdURLs.append(url)
    try bytes.write(to: url, options: .withoutOverwriting)
    let copied = try Data(contentsOf: url)
    allCopiesConfirmed =
      allCopiesConfirmed && copied.count == 17912
      && releaseGuidedWordDigest(copied) == ReleaseGuidedWordFixture.sha
    guard allCopiesConfirmed else { throw ReleaseGuidedWordFailure.admission }
  }
  func prepare() throws -> Bool { true }
  func record() throws -> Bool { true }
  func stop() throws {}
  func detachRelease() throws {}
  func deactivate() throws {}
}

@MainActor
private final class ReleaseGuidedWordObserver: LocalWordRecognizing {
  private let actual: CoreMLLocalWordRecognizer
  private(set) var requests: [LocalWordRecognitionRequest] = []
  private(set) var receipts: [LocalWordRecognitionReceipt] = []
  private(set) var cancellations = 0
  init(files: ProcessAudioFileOwnership) {
    actual = BundledLocalWordRecognizerFactory.make(ownership: files)
  }
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    requests.append(request)
    let receipt = await actual.check(request: request)
    receipts.append(receipt)
    return receipt
  }
  func cancel(operationID: UUID) {
    cancellations += 1
    actual.cancel(operationID: operationID)
  }
}

@MainActor
private final class ReleaseGuidedWordIdlePlayer: AcknowledgedPracticeAudioPlaying {
  private(set) var playCalls = 0
  var state: PracticePlaybackRuntimeState { .idle }
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
    Just(.idle).eraseToAnyPublisher()
  }
  func play(
    id: UUID, url: URL,
    onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws {
    playCalls += 1
    throw ReleaseGuidedWordFailure.unexpectedPlayback
  }
  func requestStop(id: UUID) -> PracticePlaybackCleanup? { nil }
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { nil }
}

private func releaseGuidedWordDigest(_ bytes: Data) -> String {
  SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
}
