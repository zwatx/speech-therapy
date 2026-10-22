import Combine
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class AudioCleanupRecoveryModelTests: XCTestCase {
  private var completionCleanups: [@MainActor () async -> Void] = []
  override func tearDown() async throws {
    for cleanup in completionCleanups { await cleanup() }
    completionCleanups.removeAll()
    try await super.tearDown()
  }
  func testPassiveRefreshAndExplicitRetryIgnoreNormalActiveProducer() async throws {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let producer = try RecoveryFileProducer(directory: fixture.url, files: files)
    let lease = try gate.reserve(operationID: UUID(), owner: .capture)
    var captureCalls = 0
    gate.registerCaptureRecovery(lease) {
      captureCalls += 1
      return .init(operationID: lease.operationID, result: .refused)
    }
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    model.refresh()
    model.refresh()
    XCTAssertNil(model.snapshot.blockedCaptureOperationID)
    XCTAssertNil(model.snapshot.blockedPlaybackOperationID)
    XCTAssertEqual(model.snapshot.pendingFileOwnerIDs, [producer.owner])
    XCTAssertFalse(model.snapshot.canRetry)
    XCTAssertEqual(captureCalls, 0)
    XCTAssertEqual(producer.calls, 0)
    let result = await model.retry().value
    XCTAssertFalse(result)
    XCTAssertEqual(model.failure, .hardwareInUse(lease.operationID))
    XCTAssertEqual(captureCalls, 0)
    XCTAssertEqual(producer.calls, 0)
    XCTAssertTrue(gate.release(lease))
    model.refresh()
    XCTAssertTrue(model.snapshot.canRetry)
    let cleaned = await model.retry().value
    XCTAssertTrue(cleaned)
    XCTAssertEqual(producer.calls, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: producer.url.path))
    let activePlayback = try gate.reserve(operationID: UUID(), owner: .playback)
    var playbackCalls = 0
    gate.registerPlaybackRecovery(activePlayback) {
      playbackCalls += 1
      return nil
    }
    model.refresh()
    XCTAssertFalse(model.snapshot.canRetry)
    let ignoredPlayback = await model.retry().value
    XCTAssertFalse(ignoredPlayback)
    XCTAssertEqual(model.failure, .hardwareInUse(activePlayback.operationID))
    XCTAssertEqual(playbackCalls, 0)
    XCTAssertTrue(gate.release(activePlayback))
  }

  func testDroppedViewsAndModelKeepActualPlaybackAndCaptureFileRecoveryUntilJoinedRetryReleases()
    async throws
  {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let captureControl = RecoveryCaptureControl()
    var capture: SystemAudioCapturer? = makeCapture(fixture, gate, files, captureControl)
    weak var heldCapture = capture
    try capture?.start { _ in XCTFail("Controlled capture has no natural completion") }
    let recording = try XCTUnwrap(capture?.stop())
    let owner = try XCTUnwrap(recording.cleanupOwnerID)
    let bytes = try Data(contentsOf: recording.url)
    let playback = RecoveryPlaybackControl(cleanupFailures: 1, holdsRetry: true)
    var player: SystemAcknowledgedPracticeAudioPlayer? = makePlayer(gate, files, playback)
    let id = UUID()
    try await player?.play(id: id, url: recording.url) { _, _ in XCTFail("Stopped completion") }
    XCTAssertThrowsError(try capture?.discard(recording)) {
      XCTAssertEqual($0 as? AudioCaptureError, .recordingInUse)
    }
    let original = try XCTUnwrap(player?.requestStop(id: id))
    let negative = await original.value()
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertEqual(gate.blockedPlaybackOperationID, id)
    capture = nil
    player = nil
    XCTAssertNotNil(heldCapture)
    var model: AudioCleanupRecoveryModel? = AudioCleanupRecoveryModel(ownership: gate, files: files)
    weak var heldModel = model
    XCTAssertEqual(model?.snapshot.pendingFileOwnerIDs, [owner])
    var reentrantJoin: Task<Bool, Never>?
    let subscription = try XCTUnwrap(model).$isRetrying.sink { retrying in
      MainActor.assumeIsolated {
        if retrying { reentrantJoin = model?.retry() }
      }
    }
    let retry = try XCTUnwrap(model).retry()
    let duplicate = try XCTUnwrap(model).retry()
    await entered(playback.retryEntered)
    XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    XCTAssertEqual(gate.currentLease?.operationID, id)
    subscription.cancel()
    model = nil
    XCTAssertNotNil(heldModel, "The in-flight explicit task owns recovery after UI loss.")
    playback.releaseRetry()
    let result = await retry.value
    let joined = await duplicate.value
    let reentrantTask = try XCTUnwrap(reentrantJoin)
    let synchronousJoin = await reentrantTask.value
    XCTAssertTrue(result)
    XCTAssertTrue(joined)
    XCTAssertTrue(synchronousJoin)
    XCTAssertEqual(playback.deactivationAttempts, 2)
    XCTAssertNil(gate.currentLease)
    XCTAssertNil(gate.blockedPlaybackOperationID)
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
  }

  func testNegativePlaybackRetryKeepsOriginalReceiptBorrowAndFilesUntilNextExplicitRetry()
    async throws
  {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let producer = try RecoveryFileProducer(directory: fixture.url, files: files)
    let playback = RecoveryPlaybackControl(cleanupFailures: 2)
    let player = makePlayer(gate, files, playback)
    let id = UUID()
    try await player.play(id: id, url: producer.url) { _, _ in XCTFail("Stopped completion") }
    let original = try XCTUnwrap(player.requestStop(id: id))
    let negative = await original.value()
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    let first = await model.retry().value
    XCTAssertFalse(first)
    XCTAssertEqual(model.failure, .playbackCleanupUnconfirmed(id))
    XCTAssertEqual(model.snapshot.blockedPlaybackOperationID, id)
    XCTAssertEqual(producer.calls, 0)
    XCTAssertFalse(files.canRemove(producer.url, owner: producer.owner))
    XCTAssertTrue(FileManager.default.fileExists(atPath: producer.url.path))
    let second = await model.retry().value
    XCTAssertTrue(second)
    XCTAssertNil(model.failure)
    XCTAssertEqual(producer.calls, 1)
    XCTAssertFalse(FileManager.default.fileExists(atPath: producer.url.path))
    let stillNegative = await original.value()
    XCTAssertEqual(stillNegative, negative)
    XCTAssertEqual(playback.deactivationAttempts, 3)
  }

  func testCaptureHardwareReleaseWithNewFileFailureRequiresSeparateExplicitFileRetry()
    async throws
  {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let control = RecoveryCaptureControl(stopFailures: 1, fileFailures: 1)
    var capture: SystemAudioCapturer? = makeCapture(fixture, gate, files, control)
    weak var heldCapture = capture
    try capture?.start { _ in XCTFail("Controlled capture completion") }
    XCTAssertThrowsError(try capture?.stop()) {
      XCTAssertEqual($0 as? AudioCaptureError, .hardwareCleanupUnconfirmed)
    }
    let owner = try XCTUnwrap(gate.blockedCaptureOperationID)
    let url = try XCTUnwrap(control.url)
    capture = nil
    XCTAssertNotNil(heldCapture)
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    XCTAssertTrue(model.snapshot.pendingFileOwnerIDs.isEmpty)
    let first = await model.retry().value
    XCTAssertFalse(first)
    XCTAssertEqual(model.failure, .resourcesRemain)
    XCTAssertNil(gate.currentLease)
    XCTAssertNil(model.snapshot.blockedCaptureOperationID)
    XCTAssertEqual(model.snapshot.pendingFileOwnerIDs, [owner])
    XCTAssertEqual(control.fileRemovalAttempts, 1)
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    let second = await model.retry().value
    XCTAssertTrue(second)
    XCTAssertEqual(control.fileRemovalAttempts, 2)
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertFalse(model.snapshot.hasPendingCleanup)
  }

  func testCaptureNegativeRetryDoesNotRunPendingFileRecovery() async throws {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let control = RecoveryCaptureControl(stopFailures: 2)
    let capture = makeCapture(fixture, gate, files, control)
    try capture.start { _ in XCTFail("Controlled capture completion") }
    XCTAssertThrowsError(try capture.stop())
    let owner = try XCTUnwrap(gate.blockedCaptureOperationID)
    let producer = try RecoveryFileProducer(directory: fixture.url, files: files)
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    let first = await model.retry().value
    XCTAssertFalse(first)
    XCTAssertEqual(model.failure, .captureCleanupUnconfirmed(owner))
    XCTAssertEqual(model.snapshot.blockedCaptureOperationID, owner)
    XCTAssertEqual(producer.calls, 0)
    XCTAssertEqual(control.fileRemovalAttempts, 0)
    let second = await model.retry().value
    XCTAssertTrue(second)
    XCTAssertEqual(producer.calls, 1)
    XCTAssertNil(gate.currentLease)
  }

  func testReleaseSubscriberSuccessorPreventsAwaitingRetryFromDeletingOriginalFiles() async throws {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let producer = try RecoveryFileProducer(directory: fixture.url, files: files)
    let playback = RecoveryPlaybackControl(cleanupFailures: 1)
    let player = makePlayer(gate, files, playback)
    let id = UUID()
    try await player.play(id: id, url: producer.url) { _, _ in XCTFail("Stopped completion") }
    let original = try XCTUnwrap(player.requestStop(id: id))
    _ = await original.value()
    var successor: AudioHardwareOwnership.Lease?
    let subscription = player.statePublisher.sink { state in
      MainActor.assumeIsolated {
        guard state == .idle, successor == nil else { return }
        do { successor = try gate.reserve(operationID: UUID(), owner: .capture) } catch {
          XCTFail("Expected released lease before idle publication")
        }
      }
    }
    defer { subscription.cancel() }
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    let result = await model.retry().value
    XCTAssertFalse(result)
    XCTAssertEqual(model.failure, .operationChanged)
    XCTAssertEqual(gate.currentLease, successor)
    XCTAssertEqual(producer.calls, 0)
    XCTAssertTrue(FileManager.default.fileExists(atPath: producer.url.path))
    XCTAssertEqual(model.snapshot.pendingFileOwnerIDs, [producer.owner])
    XCTAssertTrue(gate.release(try XCTUnwrap(successor)))
    let cleaned = await model.retry().value
    XCTAssertTrue(cleaned)
    XCTAssertEqual(producer.calls, 1)
  }

  func testFileCallbacksUseSortedSnapshotAndAbortBeforeTouchingReentrantSuccessor() async throws {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let producers = try (0..<2).map { _ in
      try RecoveryFileProducer(directory: fixture.url, files: files)
    }.sorted { $0.owner.uuidString < $1.owner.uuidString }
    var successor: AudioHardwareOwnership.Lease?
    producers[0].afterRemoval = {
      successor = try? gate.reserve(operationID: UUID(), owner: .playback)
      XCTAssertNotNil(successor)
    }
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    XCTAssertEqual(model.snapshot.pendingFileOwnerIDs, producers.map(\.owner))
    let first = await model.retry().value
    XCTAssertFalse(first)
    XCTAssertEqual(model.failure, .operationChanged)
    XCTAssertEqual(producers[0].calls, 1)
    XCTAssertEqual(producers[1].calls, 0)
    XCTAssertFalse(FileManager.default.fileExists(atPath: producers[0].url.path))
    XCTAssertTrue(FileManager.default.fileExists(atPath: producers[1].url.path))
    XCTAssertTrue(gate.release(try XCTUnwrap(successor)))
    let second = await model.retry().value
    XCTAssertTrue(second)
    XCTAssertEqual(producers[1].calls, 1)
  }

  func testRefusedFileCallbackKeepsItsOwnerBytesAndFreshFailureSnapshot() async throws {
    let fixture = try RecoveryOwnedDirectory()
    defer { fixture.remove() }
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    var producer: RecoveryFileProducer? = try RecoveryFileProducer(
      directory: fixture.url, files: files)
    producer?.refusesRemoval = true
    let owner = try XCTUnwrap(producer?.owner)
    let url = try XCTUnwrap(producer?.url)
    weak var retained = producer
    producer = nil
    XCTAssertNotNil(retained)
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    let first = await model.retry().value
    XCTAssertFalse(first)
    XCTAssertEqual(model.failure, .fileCleanupUnconfirmed(owner))
    XCTAssertEqual(model.snapshot.pendingFileOwnerIDs, [owner])
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    retained?.refusesRemoval = false
    let second = await model.retry().value
    XCTAssertTrue(second)
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
  }

  func testSynchronousRetryPublicationCannotInvokeStaleCaptureOrItsSuccessor() async throws {
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let old = try gate.reserve(operationID: UUID(), owner: .capture)
    var oldCalls = 0
    gate.registerCaptureRecovery(old) {
      oldCalls += 1
      return .init(operationID: old.operationID, result: .refused)
    }
    gate.markCaptureCleanupBlocked(old)
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    var successor: AudioHardwareOwnership.Lease?
    let subscription = model.$isRetrying.sink { retrying in
      MainActor.assumeIsolated {
        guard retrying, successor == nil else { return }
        XCTAssertTrue(gate.release(old))
        successor = try? gate.reserve(operationID: UUID(), owner: .capture)
        if let successor {
          gate.registerCaptureRecovery(successor) {
            XCTFail("Normal successor capture must never be retried")
            return .init(operationID: successor.operationID, result: .refused)
          }
        }
      }
    }
    defer { subscription.cancel() }
    let result = await model.retry().value
    XCTAssertFalse(result)
    XCTAssertEqual(model.failure, .operationChanged)
    XCTAssertEqual(oldCalls, 0)
    XCTAssertEqual(model.snapshot.activeHardwareOperationID, successor?.operationID)
    XCTAssertNil(model.snapshot.blockedCaptureOperationID)
    XCTAssertTrue(gate.release(try XCTUnwrap(successor)))
  }

  func testReusedOperationIDOnNewLeaseCannotAuthorizeOldSelectedRecovery() async throws {
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let id = UUID()
    let old = try gate.reserve(operationID: id, owner: .capture)
    gate.registerCaptureRecovery(old) {
      XCTFail("Old selected capture was already released")
      return .init(operationID: id, result: .refused)
    }
    gate.markCaptureCleanupBlocked(old)
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    var successor: AudioHardwareOwnership.Lease?
    let subscription = model.$isRetrying.sink { retrying in
      MainActor.assumeIsolated {
        guard retrying, successor == nil else { return }
        XCTAssertTrue(gate.release(old))
        successor = try? gate.reserve(operationID: id, owner: .capture)
        if let successor {
          gate.registerCaptureRecovery(successor) {
            XCTFail("Same UUID on a different lease cannot substitute the selected owner")
            return .init(operationID: id, result: .refused)
          }
          gate.markCaptureCleanupBlocked(successor)
        }
      }
    }
    defer { subscription.cancel() }
    let result = await model.retry().value
    XCTAssertFalse(result)
    XCTAssertEqual(model.failure, .operationChanged)
    XCTAssertEqual(gate.currentLease, successor)
    XCTAssertEqual(model.snapshot.blockedCaptureOperationID, id)
    XCTAssertTrue(gate.release(try XCTUnwrap(successor)))
  }

  func testFinalRetryPublicationJoinsOriginalFailedAttemptWithoutImplicitFileRetry() async throws {
    let fixture = try RecoveryOwnedDirectory()
    let gate = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let captureControl = RecoveryCaptureControl(fileFailures: 1)
    let capture = makeCapture(fixture, gate, files, captureControl)
    let playback = RecoveryPlaybackControl(cleanupFailures: 1, holdsRetry: true)
    let player = makePlayer(gate, files, playback)
    var heldRecording: CapturedRecording?
    completionCleanups.append {
      playback.releaseRetry()
      captureControl.fileFailures = 0
      if let lease = gate.currentLease, lease.owner == .playback {
        if let stop = player.requestStop(id: lease.operationID) { _ = await stop.value() }
        if let retry = gate.retryPlaybackCleanup() { _ = await retry.value() }
      }
      if let id = gate.blockedCaptureOperationID { _ = gate.retryCaptureCleanup(operationID: id) }
      try? capture.cancel()
      if let recording = heldRecording, files.protectedURLs.contains(recording.url) {
        try? capture.discard(recording)
      }
      for owner in files.pendingCleanupOwners { _ = files.retryCleanup(owner: owner) }
      XCTAssertNil(gate.currentLease)
      XCTAssertTrue(files.protectedURLs.isEmpty)
      if gate.currentLease == nil, files.protectedURLs.isEmpty { fixture.remove() }
    }
    try capture.start { _ in XCTFail("Controlled capture has no natural completion") }
    let recording = try capture.stop()
    heldRecording = recording
    let owner = try XCTUnwrap(recording.cleanupOwnerID)
    let bytes = try Data(contentsOf: recording.url)
    let id = UUID()
    try await player.play(id: id, url: recording.url) { _, _ in XCTFail("Stopped completion") }
    XCTAssertThrowsError(try capture.discard(recording)) {
      XCTAssertEqual($0 as? AudioCaptureError, .recordingInUse)
    }
    let original = try XCTUnwrap(player.requestStop(id: id))
    let negative = await original.value()
    XCTAssertEqual(negative.operation.id, id)
    XCTAssertEqual(negative.result, .cleanupUnconfirmed)
    XCTAssertEqual(captureControl.fileRemovalAttempts, 0)
    let model = AudioCleanupRecoveryModel(ownership: gate, files: files)
    var began = false
    var finishedPublications = 0
    var joins: [Task<Bool, Never>] = []
    let observation = model.$isRetrying.sink { retrying in
      MainActor.assumeIsolated {
        if retrying {
          began = true
          return
        }
        guard began, finishedPublications == 0 else { return }
        finishedPublications += 1
        XCTAssertEqual(model.failure, .fileCleanupUnconfirmed(owner))
        XCTAssertEqual(model.snapshot.pendingFileOwnerIDs, [owner])
        XCTAssertEqual(captureControl.fileRemovalAttempts, 1)
        for _ in 0..<3 { joins.append(model.retry()) }
      }
    }
    defer { observation.cancel() }
    let retry = model.retry()
    await entered(playback.retryEntered)
    XCTAssertTrue(model.isRetrying)
    XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
    playback.releaseRetry()
    let result = await retry.value
    XCTAssertFalse(result)
    XCTAssertEqual(joins.count, 3)
    for join in joins {
      let joinedResult = await join.value
      XCTAssertFalse(joinedResult, "Completion subscribers join the original negative attempt")
    }
    XCTAssertEqual(finishedPublications, 1)
    XCTAssertFalse(model.isRetrying)
    XCTAssertEqual(model.failure, .fileCleanupUnconfirmed(owner))
    XCTAssertEqual(captureControl.fileRemovalAttempts, 1)
    XCTAssertEqual(try Data(contentsOf: recording.url), bytes)
    XCTAssertEqual(files.pendingCleanupOwners, [owner])
    XCTAssertNil(capture.completedFileCleanup(operationID: owner))
    XCTAssertNil(gate.currentLease)
    XCTAssertEqual(original.receipt, negative)
    observation.cancel()
    let explicitlyRetried = await model.retry().value
    XCTAssertTrue(explicitlyRetried)
    XCTAssertNil(model.failure)
    XCTAssertEqual(captureControl.fileRemovalAttempts, 2)
    XCTAssertEqual(capture.completedFileCleanup(operationID: owner)?.result, .released)
    XCTAssertFalse(FileManager.default.fileExists(atPath: recording.url.path))
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
    XCTAssertTrue(files.protectedURLs.isEmpty)
    XCTAssertEqual(original.receipt, negative)
    XCTAssertEqual(playback.deactivationAttempts, 2)
  }

  private func entered(_ expectation: XCTestExpectation) async {
    let result = await XCTWaiter.fulfillment(of: [expectation], timeout: 2)
    XCTAssertEqual(result, .completed)
  }

  private func makePlayer(
    _ gate: AudioHardwareOwnership, _ files: ProcessAudioFileOwnership,
    _ control: RecoveryPlaybackControl
  ) -> SystemAcknowledgedPracticeAudioPlayer {
    SystemAcknowledgedPracticeAudioPlayer(ownership: gate, fileOwnership: files) { _, _ in
      RecoveryControlledPlaybackDriver(control: control)
    }
  }

  private func makeCapture(
    _ fixture: RecoveryOwnedDirectory, _ gate: AudioHardwareOwnership,
    _ files: ProcessAudioFileOwnership, _ control: RecoveryCaptureControl
  ) -> SystemAudioCapturer {
    SystemAudioCapturer(
      recordingStore: TemporaryRecordingStore(directory: fixture.url),
      fileOwnership: files, hardwareOwnership: gate,
      driverFactory: { RecoveryControlledCaptureDriver(control: control) },
      summaryReader: { _ in .init(duration: 1, averagePower: -20) },
      removeFile: { try control.remove($0) })
  }
}

private final class RecoveryPlaybackControl: @unchecked Sendable {
  enum Failure: Error { case controlled, deadline }
  let retryEntered = XCTestExpectation(description: "actual queued retry held")
  let cleanupFailures: Int
  let holdsRetry: Bool
  private let lock = NSLock()
  private var attempts = 0
  private let retryGate = DispatchSemaphore(value: 0)
  var deactivationAttempts: Int { lock.withLock { attempts } }
  init(cleanupFailures: Int, holdsRetry: Bool = false) {
    self.cleanupFailures = cleanupFailures
    self.holdsRetry = holdsRetry
  }
  func deactivate() throws {
    let count = lock.withLock {
      attempts += 1
      return attempts
    }
    if count == 2 {
      retryEntered.fulfill()
      if holdsRetry, retryGate.wait(timeout: .now() + 8) != .success { throw Failure.deadline }
    }
    if count <= cleanupFailures { throw Failure.controlled }
  }
  func releaseRetry() { retryGate.signal() }
}

private final class RecoveryControlledPlaybackDriver: PracticePlaybackDriver {
  let control: RecoveryPlaybackControl
  init(control: RecoveryPlaybackControl) { self.control = control }
  func activate() throws {}
  func prepare() throws -> Bool { true }
  func play() throws -> Bool { true }
  func stop() throws {}
  func releasePlaybackResources() throws {}
  func deactivate() throws { try control.deactivate() }
}

@MainActor
private final class RecoveryCaptureControl {
  enum Failure: Error { case controlled }
  var stopFailures: Int
  var fileFailures: Int
  var url: URL?
  private(set) var fileRemovalAttempts = 0
  init(stopFailures: Int = 0, fileFailures: Int = 0) {
    self.stopFailures = stopFailures
    self.fileFailures = fileFailures
  }
  func remove(_ url: URL) throws {
    fileRemovalAttempts += 1
    if fileFailures > 0 {
      fileFailures -= 1
      throw Failure.controlled
    }
    if FileManager.default.fileExists(atPath: url.path) {
      try FileManager.default.removeItem(at: url)
    }
  }
}

@MainActor
private final class RecoveryControlledCaptureDriver: CaptureHardwareDriver {
  let control: RecoveryCaptureControl
  init(control: RecoveryCaptureControl) { self.control = control }
  func configureActivate() throws {}
  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    control.url = url
    try Data("controlled process capture".utf8).write(to: url)
  }
  func prepare() throws -> Bool { true }
  func record() throws -> Bool { true }
  func stop() throws {
    if control.stopFailures > 0 {
      control.stopFailures -= 1
      throw RecoveryCaptureControl.Failure.controlled
    }
  }
  func detachRelease() throws {}
  func deactivate() throws {}
}

@MainActor
private final class RecoveryFileProducer {
  let owner = UUID()
  let url: URL
  var refusesRemoval = false
  var afterRemoval: (@MainActor () -> Void)?
  private(set) var calls = 0
  private let files: ProcessAudioFileOwnership
  init(directory: URL, files: ProcessAudioFileOwnership) throws {
    self.files = files
    url = directory.appendingPathComponent("\(UUID()).wav")
    try Data("owned process fixture".utf8).write(to: url)
    files.retain(url, owner: owner)
    files.registerCleanupRecovery(owner: owner) { [self] in
      calls += 1
      guard !refusesRemoval, files.canRemove(url, owner: owner) else { return false }
      do { try FileManager.default.removeItem(at: url) } catch { return false }
      files.didRemove(url, owner: owner)
      afterRemoval?()
      return true
    }
  }
}

private struct RecoveryOwnedDirectory {
  let url: URL
  init() throws {
    url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
  }
  func remove() { try? FileManager.default.removeItem(at: url) }
}
