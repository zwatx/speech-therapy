@preconcurrency import AVFoundation
import CadenceContracts
@preconcurrency import Combine
import XCTest

@testable import CadenceLearner

@MainActor
final class PracticeSessionModelTests: XCTestCase {
  private var localFeasibilityConfiguration: VisualPracticeConfiguration {
    VisualPracticeConfiguration(
      mode: .localFeasibility,
      protocolID: "bilabial-closure-v1",
      feasibilityScenario: .protocolCompliant
    )
  }

  func testWrongRetryWhileRecordingPreservesLeaseAndCannotAdmitSecondStart() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    let model = fixture.model()
    await model.startRecording()
    let lease = try XCTUnwrap(fixture.hardware.currentLease)
    model.retryCaptureCleanup(operationID: UUID())
    model.retryCaptureCleanup(operationID: lease.operationID)
    XCTAssertEqual(model.phase, .recording)
    XCTAssertTrue(model.requiresCaptureCleanupBeforeDeparture)
    XCTAssertFalse(model.canRefreshAssignment)
    await model.startRecording()
    XCTAssertEqual(fixture.hardware.currentLease, lease)
    XCTAssertEqual(fixture.control.factoryCalls, 1)
    XCTAssertEqual(fixture.driver.deactivations, 0)
    fixture.driver.failDeactivate = true
    XCTAssertFalse(model.requestClose())
    XCTAssertEqual(fixture.hardware.currentLease, lease)
    fixture.driver.failDeactivate = false
    model.retryCaptureCleanup(operationID: lease.operationID)
    XCTAssertTrue(model.requestClose())
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
  }

  func testReentrantFileOnlyCancelReceiptAllowsDepartureWithoutUnknownFailure() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    var recoveredID: UUID?
    let observation = fixture.capture.cleanupStatePublisher.sink { state in
      guard let id = state.fileBlockedOwnerIDs.first, recoveredID == nil else { return }
      XCTAssertFalse(state.hasHardwareIssue)
      XCTAssertNil(fixture.hardware.currentLease)
      recoveredID = id
      fixture.control.failRemoval = false
      XCTAssertTrue(fixture.files.retryCleanup(owner: id))
    }
    defer { observation.cancel() }
    let model = fixture.model()
    await model.startRecording()
    let lease = try XCTUnwrap(fixture.hardware.currentLease)
    fixture.control.failRemoval = true
    XCTAssertTrue(model.requestClose())
    XCTAssertEqual(recoveredID, lease.operationID)
    XCTAssertTrue(
      fixture.capture.completedFileCleanup(operationID: lease.operationID)?.allRequestedFilesRemoved
        == true)
    XCTAssertEqual(model.captureCleanupState, .idle)
    XCTAssertTrue(model.captureCleanupRetryIDs.isEmpty)
    XCTAssertFalse(model.requiresCaptureCleanupBeforeDeparture)
    XCTAssertTrue(model.captureDisabledForVisit)
    XCTAssertTrue(model.requestClose())
    XCTAssertEqual(fixture.driver.deactivations, 1)
    XCTAssertEqual(fixture.control.removals, 2)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: try XCTUnwrap(fixture.driver.url).path))
    model.retryCaptureCleanup(operationID: lease.operationID)
    XCTAssertEqual(fixture.control.removals, 2)
  }

  func testReentrantPositiveCancelReceiptAllowsCloseDespiteOriginalError() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    var recoveredID: UUID?
    let observation = fixture.capture.cleanupStatePublisher.sink { state in
      guard let id = state.hardwareBlockedOperationID, recoveredID == nil else { return }
      recoveredID = id
      fixture.driver.failDeactivate = false
      XCTAssertTrue(fixture.capture.retryCleanup(operationID: id).allRequestedFilesRemoved)
    }
    defer { observation.cancel() }
    let model = fixture.model()
    await model.startRecording()
    let lease = try XCTUnwrap(fixture.hardware.currentLease)
    fixture.driver.failDeactivate = true
    XCTAssertTrue(model.requestClose())
    XCTAssertEqual(recoveredID, lease.operationID)
    XCTAssertTrue(
      fixture.capture.completedFileCleanup(operationID: lease.operationID)?.allRequestedFilesRemoved
        == true)
    XCTAssertFalse(model.requiresCaptureCleanupBeforeDeparture)
    XCTAssertFalse(model.hasCaptureCleanupIssue)
    XCTAssertTrue(model.captureCleanupRetryIDs.isEmpty)
    XCTAssertTrue(model.requestClose())
    XCTAssertEqual(fixture.driver.deactivations, 2)
    XCTAssertEqual(fixture.control.removals, 1)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
  }

  func testCloseInsideSubmittingPublicationPreventsAnySubmitIncludingFileWarningDeparture()
    async throws
  {
    for failRemoval in [false, true] {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let submitter = CountingConsumerSubmitter()
      let context = try LearnerAttemptContext(
        deviceToken: String(repeating: "x", count: 43),
        assignmentID: LearnerPracticeAssignment.localPreview.assignmentID,
        exerciseID: LearnerPracticeAssignment.localPreview.exerciseID)
      let model = PracticeSessionModel(
        capturer: fixture.capture, submitter: submitter, attemptContext: context,
        hardwareOwnership: fixture.hardware, fileOwnership: fixture.files)
      var handled = false
      let observation = model.$phase.sink { phase in
        guard case .submitting = phase, !handled else { return }
        handled = true
        XCTAssertEqual(model.requestClose(), !failRemoval)
        if failRemoval { XCTAssertTrue(model.requestClose()) }
      }
      defer { observation.cancel() }
      await model.startRecording()
      fixture.control.failRemoval = failRemoval
      await model.stopRecording()
      let calls = await submitter.callCount()
      XCTAssertTrue(handled)
      XCTAssertEqual(calls, 0)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertEqual(fixture.control.removals, 1)
      if failRemoval {
        XCTAssertTrue(model.captureCleanupState.hasFileIssue)
        let id = try XCTUnwrap(model.captureCleanupRetryIDs.first)
        XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(id))
        fixture.control.failRemoval = false
        XCTAssertTrue(fixture.files.retryCleanup(owner: id))
      } else {
        XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      }
      XCTAssertEqual(model.currentRepetition, 1)
    }
  }

  func testHardwareFailureHoldsCloseUntilExactCleanupWithoutLateCapture() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    let model = fixture.model()
    await model.startRecording()
    fixture.driver.failDeactivate = true
    await model.stopRecording()
    let id = try XCTUnwrap(model.captureCleanupState.hardwareBlockedOperationID)
    XCTAssertFalse(model.requestClose())
    XCTAssertFalse(model.requestClose())
    XCTAssertEqual(fixture.driver.deactivations, 1)
    model.retryCaptureCleanup(operationID: UUID())
    XCTAssertEqual(fixture.driver.deactivations, 1)
    fixture.driver.failDeactivate = false
    model.retryCaptureCleanup(operationID: id)
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertFalse(model.captureCleanupState.hasHardwareIssue)
    XCTAssertTrue(model.requestClose())
    if case .captured = model.phase { XCTFail("Cleanup cannot restore a captured result") }
    XCTAssertEqual(model.currentRepetition, 1)
  }

  func testFileFailureRetainsMediaAndOnlyProcessHeldRecoveryPermitsSecondClose() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    let model = fixture.model()
    await model.startRecording()
    fixture.control.failRemoval = true
    await model.stopRecording()
    let id = try XCTUnwrap(model.captureCleanupState.fileBlockedOwnerIDs.first)
    let url = try XCTUnwrap(fixture.driver.url)
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(id))
    XCTAssertFalse(model.requestClose())
    XCTAssertTrue(model.requestClose())
    XCTAssertEqual(fixture.control.removals, 1)
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    fixture.control.failRemoval = false
    XCTAssertTrue(fixture.files.retryCleanup(owner: id))
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
  }

  func testFileRetryIsCleanupOnlyAndCannotBypassDisabledVisit() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    let model = fixture.model()
    await model.startRecording()
    fixture.control.failRemoval = true
    await model.stopRecording()
    let id = try XCTUnwrap(model.captureCleanupState.fileBlockedOwnerIDs.first)
    model.tryAgain()
    await model.startRecording()
    XCTAssertEqual(fixture.control.factoryCalls, 1)
    XCTAssertEqual(fixture.control.removals, 1)
    fixture.control.failRemoval = false
    model.retryCaptureCleanup(operationID: id)
    XCTAssertTrue(model.captureDisabledForVisit)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    model.tryAgain()
    await model.startRecording()
    XCTAssertEqual(fixture.control.factoryCalls, 1)
    XCTAssertTrue(model.requestClose())
  }

  func testStartupFailureHasNoImpossibleRetryAndSafeDeparture() async throws {
    let fixture = try ConsumerCaptureFixture(startupFailure: true)
    defer { fixture.dispose() }
    let model = fixture.model()
    await model.startRecording()
    XCTAssertTrue(model.captureDisabledForVisit)
    XCTAssertTrue(model.captureCleanupRetryIDs.isEmpty)
    XCTAssertFalse(model.requiresCaptureCleanupBeforeDeparture)
    XCTAssertEqual(fixture.control.factoryCalls, 0)
    model.tryAgain()
    await model.startRecording()
    XCTAssertEqual(fixture.control.factoryCalls, 0)
    XCTAssertTrue(model.requestClose())
  }

  func testNewVisitCanExplicitlyRecoverProcessHeldHardware() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    var old: PracticeSessionModel? = fixture.model()
    await old!.startRecording()
    fixture.driver.failDeactivate = true
    await old!.stopRecording()
    weak var oldVisit = old
    old = nil
    XCTAssertNil(oldVisit)
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      hardwareOwnership: fixture.hardware, fileOwnership: fixture.files)
    let id = try XCTUnwrap(model.captureCleanupState.hardwareBlockedOperationID)
    fixture.driver.failDeactivate = false
    model.retryCaptureCleanup(operationID: id)
    XCTAssertNil(fixture.hardware.currentLease)
    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(fixture.control.factoryCalls, 1)
  }

  func testCloseRevokesHeldPermissionBeforeGrant() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    fixture.capture.holdsPermission = true
    let model = fixture.model()
    let start = Task { await model.startRecording() }
    await waitForConsumerState { fixture.capture.permission != nil }
    XCTAssertTrue(model.requestClose())
    fixture.capture.grant()
    await start.value
    XCTAssertEqual(fixture.control.factoryCalls, 0)
    XCTAssertNotEqual(model.phase, .recording)
  }

  func testReceivedSaveWithDeletionFailureRetainsFileAndRequiresRefresh() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: LearnerPracticeAssignment.localPreview.assignmentID,
      exerciseID: LearnerPracticeAssignment.localPreview.exerciseID)
    let receipt = LearnerAttemptReceipt(
      attemptId: UUID().uuidString, status: .acceptedSilent,
      feedbackAvailable: false, mediaRetained: false, reasonCodes: [])
    let model = PracticeSessionModel(
      capturer: fixture.capture,
      submitter: SuccessfulSubmitter(receipt: receipt), attemptContext: context,
      hardwareOwnership: fixture.hardware, fileOwnership: fixture.files)
    await model.startRecording()
    fixture.control.failRemoval = true
    await model.stopRecording()
    XCTAssertTrue(model.assignmentRefreshRequired)
    XCTAssertTrue(FileManager.default.fileExists(atPath: try XCTUnwrap(fixture.driver.url).path))
    let id = try XCTUnwrap(model.captureCleanupRetryIDs.first)
    fixture.control.failRemoval = false
    model.retryCaptureCleanup(operationID: id)
    XCTAssertNotEqual(model.phase, .saved(receipt))
    XCTAssertEqual(model.currentRepetition, 1)
    model.tryAgain()
    await model.startRecording()
    XCTAssertEqual(fixture.control.factoryCalls, 1)
  }

  func testSynchronousProducerRetryReconcilesExactRemovalBeforeFailedDiscardReturns() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    var recoveredID: UUID?
    // Subscribe before the consumer: recovery advances the getter before its failed event arrives.
    let observation = fixture.capture.cleanupStatePublisher.sink { state in
      guard let id = state.fileBlockedOwnerIDs.first, recoveredID == nil else { return }
      recoveredID = id
      fixture.control.failRemoval = false
      XCTAssertTrue(fixture.capture.retryCleanup(operationID: id).allRequestedFilesRemoved)
    }
    defer { observation.cancel() }
    let model = fixture.model()
    await model.startRecording()
    fixture.control.failRemoval = true
    await model.stopRecording()
    let id = try XCTUnwrap(recoveredID)
    XCTAssertTrue(
      fixture.capture.completedFileCleanup(operationID: id)?.allRequestedFilesRemoved == true)
    XCTAssertEqual(fixture.control.removals, 2)
    XCTAssertTrue(model.captureDisabledForVisit)
    XCTAssertTrue(model.requestClose())
    XCTAssertFalse(FileManager.default.fileExists(atPath: try XCTUnwrap(fixture.driver.url).path))
    if case .captured = model.phase {
      XCTFail("Recovery during discard cannot grant a captured phase")
    }
    model.retryCaptureCleanup(operationID: id)
    XCTAssertEqual(fixture.control.removals, 2)
    XCTAssertEqual(model.currentRepetition, 1)
  }

  func testInactiveDuringSaveReleasesOnlyOwnedFileAndIgnoresLateReceipt() async throws {
    let fixture = try ConsumerCaptureFixture()
    defer { fixture.dispose() }
    let submitter = HeldConsumerSubmitter()
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: LearnerPracticeAssignment.localPreview.assignmentID,
      exerciseID: LearnerPracticeAssignment.localPreview.exerciseID)
    let model = PracticeSessionModel(
      capturer: fixture.capture, submitter: submitter,
      attemptContext: context, hardwareOwnership: fixture.hardware, fileOwnership: fixture.files)
    await model.startRecording()
    let stop = Task { await model.stopRecording() }
    await submitter.waitUntilStarted()
    fixture.control.failRemoval = true
    model.appDidBecomeInactive()
    XCTAssertTrue(model.assignmentRefreshRequired)
    XCTAssertTrue(model.captureCleanupState.hasFileIssue)
    let id = try XCTUnwrap(model.captureCleanupRetryIDs.first)
    let receipt = LearnerAttemptReceipt(
      attemptId: UUID().uuidString, status: .acceptedSilent,
      feedbackAvailable: false, mediaRetained: false, reasonCodes: [])
    await submitter.succeed(with: receipt)
    await stop.value
    XCTAssertNotEqual(model.phase, .saved(receipt))
    XCTAssertEqual(fixture.control.removals, 1)
    fixture.control.failRemoval = false
    model.retryCaptureCleanup(operationID: id)
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    XCTAssertTrue(model.assignmentRefreshRequired)
    XCTAssertEqual(model.currentRepetition, 1)
  }

  func testPermissionDenialNeverStartsCapture() async {
    let capturer = MockAudioCapturer(permissionGranted: false)
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())

    await model.startRecording()

    XCTAssertEqual(model.phase, .permissionDenied)
    XCTAssertEqual(capturer.startCount, 0)
  }

  func testLeavingDuringMicrophonePermissionCannotStartCaptureLater() async {
    for granted in [true, false] {
      let capturer = MockAudioCapturer(
        permissionGranted: granted,
        permissionDelay: .milliseconds(50)
      )
      let model = PracticeSessionModel(
        capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
        fileOwnership: ProcessAudioFileOwnership())
      let starting = Task { await model.startRecording() }
      await waitForConsumerState { capturer.permissionRequestCount > 0 }

      model.appDidBecomeInactive()
      await starting.value

      XCTAssertEqual(model.phase, .ready)
      XCTAssertEqual(capturer.startCount, 0)
      XCTAssertEqual(capturer.stopCount, 0)
    }
  }

  func testClearCaptureMovesToCapturedState() async {
    let summary = CaptureSummary(duration: 1.0, averagePower: -20)
    let capturer = MockAudioCapturer(
      permissionGranted: true,
      summary: summary
    )
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())

    await model.startRecording()
    XCTAssertEqual(model.phase, .recording)
    await model.stopRecording()

    XCTAssertEqual(model.phase, .captured(summary))
    XCTAssertEqual(capturer.stopCount, 1)
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testDurationLimitCompletesCaptureWithoutRequiringStop() async {
    let summary = CaptureSummary(duration: 4, averagePower: -20)
    let capturer = MockAudioCapturer(permissionGranted: true, summary: summary)
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())

    await model.startRecording()
    await capturer.finish()

    XCTAssertEqual(model.phase, .captured(summary))
    XCTAssertEqual(capturer.stopCount, 1)
    XCTAssertEqual(capturer.discardCount, 1)
    await model.stopRecording()
    await capturer.finish()
    XCTAssertEqual(capturer.stopCount, 1)
  }

  func testOldCompletionCannotStopANewRecording() async {
    let capturer = MockAudioCapturer(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())
    await model.startRecording()
    await model.stopRecording()
    model.tryAgain()
    await model.startRecording()

    await capturer.finish(recordingIndex: 0)

    XCTAssertEqual(model.phase, .recording)
    XCTAssertEqual(capturer.stopCount, 1)
    await capturer.finish(recordingIndex: 1)
    XCTAssertEqual(capturer.stopCount, 2)
  }

  func testFailedAutomaticCompletionCancelsInsteadOfSaving() async {
    let capturer = MockAudioCapturer(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())
    await model.startRecording()

    await capturer.finish(successfully: false)

    XCTAssertEqual(model.phase, .failed("The recording ended unexpectedly. Please try again."))
    XCTAssertEqual(capturer.cancelCount, 1)
    XCTAssertEqual(capturer.stopCount, 0)
  }

  func testCompletionAfterBackgroundCancellationDoesNotSave() async {
    let capturer = MockAudioCapturer(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())
    await model.startRecording()
    model.appDidBecomeInactive()

    await capturer.finish()

    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(capturer.cancelCount, 1)
    XCTAssertEqual(capturer.stopCount, 0)
  }

  func testFinishedWaveUsesRecordedDurationAndPower() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let hardware = AudioHardwareOwnership()
    let files = ProcessAudioFileOwnership()
    let driver = ConsumerCaptureDriver()
    var factoryCalls = 0
    let capturer = SystemAudioCapturer(
      recordingStore: TemporaryRecordingStore(directory: directory),
      fileOwnership: files, hardwareOwnership: hardware,
      driverFactory: {
        factoryCalls += 1
        return driver
      })
    let url = directory.appendingPathComponent("finished.wav")
    let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1))
    let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 64_000))
    buffer.frameLength = 64_000
    let samples = try XCTUnwrap(buffer.floatChannelData?[0])
    for index in 0..<64_000 { samples[index] = index.isMultiple(of: 2) ? 0.1 : -0.1 }
    try autoreleasepool {
      let file = try AVAudioFile(forWriting: url, settings: format.settings)
      try file.write(from: buffer)
      if #available(iOS 18.0, *) { file.close() }
    }

    let summary = try capturer.recordedSummary(at: url)

    XCTAssertEqual(summary.duration, 4, accuracy: 0.001)
    XCTAssertEqual(summary.averagePower, -20, accuracy: 0.01)
    XCTAssertEqual(CaptureQualityAssessor().assess(summary), .acceptable)

    let shortURL = directory.appendingPathComponent("short.wav")
    buffer.frameLength = 3_200
    try autoreleasepool {
      let file = try AVAudioFile(forWriting: shortURL, settings: format.settings)
      try file.write(from: buffer)
      if #available(iOS 18.0, *) { file.close() }
    }
    let shortSummary = try capturer.recordedSummary(at: shortURL)
    XCTAssertEqual(shortSummary.duration, 0.2, accuracy: 0.001)
    guard case .retry = CaptureQualityAssessor().assess(shortSummary) else {
      return XCTFail("Short recordings must still request another capture")
    }

    buffer.frameLength = 64_000
    let quietURL = directory.appendingPathComponent("quiet.wav")
    for index in 0..<64_000 { samples[index] = 0 }
    try autoreleasepool {
      let file = try AVAudioFile(forWriting: quietURL, settings: format.settings)
      try file.write(from: buffer)
      if #available(iOS 18.0, *) { file.close() }
    }
    let quietSummary = try capturer.recordedSummary(at: quietURL)
    XCTAssertEqual(quietSummary.averagePower, -160)
    guard case .retry = CaptureQualityAssessor().assess(quietSummary) else {
      return XCTFail("Automatic completion must not treat a silent clip as clear")
    }

    // Float32 WAV reads may return only 63,488 of these 64,000 frames initially.
    // Put all energy in the final 512 frames to verify later reads contribute too.
    let tailURL = directory.appendingPathComponent("tail.wav")
    for index in 63_488..<64_000 { samples[index] = 0.5 }
    try autoreleasepool {
      let file = try AVAudioFile(forWriting: tailURL, settings: format.settings)
      try file.write(from: buffer)
      if #available(iOS 18.0, *) { file.close() }
    }
    let tailSummary = try capturer.recordedSummary(at: tailURL)
    XCTAssertEqual(tailSummary.duration, 4, accuracy: 0.001)
    XCTAssertEqual(
      tailSummary.averagePower, Float(10 * log10(512 * 0.25 / 64_000)), accuracy: 0.001)

    samples[63_999] = .nan
    let invalidURL = directory.appendingPathComponent("invalid.wav")
    try autoreleasepool {
      let file = try AVAudioFile(forWriting: invalidURL, settings: format.settings)
      try file.write(from: buffer)
      if #available(iOS 18.0, *) { file.close() }
    }
    XCTAssertThrowsError(try capturer.recordedSummary(at: invalidURL))
    XCTAssertEqual(factoryCalls, 0)
    XCTAssertNil(hardware.currentLease)
    XCTAssertTrue(files.protectedURLs.isEmpty)
  }

  func testPoorCaptureMovesToRetryInsteadOfAClinicalResult() async {
    let capturer = MockAudioCapturer(
      permissionGranted: true,
      summary: CaptureSummary(duration: 0.1, averagePower: -20)
    )
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())

    await model.startRecording()
    await model.stopRecording()

    guard case .retry = model.phase else {
      return XCTFail("Expected capture coaching, not a score")
    }
    XCTAssertEqual(capturer.discardCount, 1)
    model.tryAgain()
    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(model.currentRepetition, 1)
    XCTAssertEqual(model.currentRetry, 0)
  }

  func testLeavingTheAppCancelsAnActiveRecording() async {
    let capturer = MockAudioCapturer(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: capturer, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership())

    await model.startRecording()
    model.appDidBecomeInactive()

    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(capturer.cancelCount, 1)
  }

  func testAutomaticCompletionUploadsSilentlyAndDeletesTheTemporaryFile() async throws {
    let capturer = MockAudioCapturer(
      permissionGranted: true,
      summary: CaptureSummary(duration: 1, averagePower: -20)
    )
    let receipt = LearnerAttemptReceipt(
      attemptId: "attempt-saved",
      status: .acceptedSilent,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes: []
    )
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: LearnerPracticeAssignment.localPreview.assignmentID,
      exerciseID: "foundation-ball-initial-b-v1"
    )
    let model = PracticeSessionModel(
      assignment: .localPreview,
      capturer: capturer,
      submitter: SuccessfulSubmitter(receipt: receipt),
      attemptContext: context, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )

    await model.startRecording()
    await capturer.finish()

    XCTAssertEqual(model.phase, .saved(receipt))
    XCTAssertEqual(capturer.discardCount, 1)
  }

  func testAssignmentDrivesDisplayDoseRetrySlotsAndCompletion() async throws {
    let assignment = LearnerPracticeAssignment(
      assignmentID: "assignment-dose-test",
      version: 1,
      exerciseRegistryVersion: "foundation-exercises-v1",
      exerciseDefinitionSHA256: String(repeating: "a", count: 64),
      exerciseID: "foundation-ball-initial-b-v1",
      protocolID: "bilabial-closure-v1",
      prompt: "custom ball",
      targetLabel: "Custom beginning target",
      attemptTarget: 2,
      retryLimit: 1
    )
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: assignment.assignmentID,
      exerciseID: assignment.exerciseID
    )
    let capturer = MockAudioCapturer(permissionGranted: true)
    let submitter = SequenceSubmitter(statuses: [
      .acceptedSilent,
      .retryCapture,
      .acceptedSilent,
    ])
    let model = PracticeSessionModel(
      assignment: assignment,
      capturer: capturer,
      submitter: submitter,
      attemptContext: context, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )

    XCTAssertEqual(model.promptWord, "custom ball")
    XCTAssertEqual(model.targetLabel, "Custom beginning target")
    XCTAssertEqual(model.assignmentProgress, "1 of 2")

    await model.startRecording()
    await model.stopRecording()
    model.tryAgain()
    XCTAssertEqual(model.assignmentProgress, "2 of 2")

    await model.startRecording()
    await model.stopRecording()
    model.tryAgain()
    XCTAssertEqual(model.currentRetry, 1)
    XCTAssertEqual(model.assignmentProgress, "2 of 2")

    await model.startRecording()
    await model.stopRecording()
    model.tryAgain()
    XCTAssertEqual(model.phase, .completed)

    let contexts = await submitter.contexts()
    XCTAssertEqual(
      contexts.map { [$0.repetitionIndex, $0.retryIndex] },
      [[1, 0], [2, 0], [2, 1]]
    )
    XCTAssertTrue(contexts.allSatisfy { $0.assignmentID == assignment.assignmentID })
  }

  func testAssignmentConflictRequiresRefreshInsteadOfBlindRetry() async throws {
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: LearnerPracticeAssignment.localPreview.assignmentID,
      exerciseID: LearnerPracticeAssignment.localPreview.exerciseID
    )
    let model = PracticeSessionModel(
      assignment: .localPreview,
      capturer: MockAudioCapturer(permissionGranted: true),
      submitter: RejectingSubmitter(error: .rejected(status: 409)),
      attemptContext: context, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )

    await model.startRecording()
    await model.stopRecording()

    XCTAssertTrue(model.assignmentRefreshRequired)
    XCTAssertEqual(
      model.phase,
      .failed(
        "The last save could not be confirmed. Refresh practice before recording again."
      )
    )
    model.tryAgain()
    XCTAssertTrue(model.assignmentRefreshRequired)
  }

  func testServerRetryExhaustionPausesWithoutCompletingARepetition() async throws {
    let assignment = LearnerPracticeAssignment(
      assignmentID: "assignment-retry-limit",
      version: 1,
      exerciseRegistryVersion: "foundation-exercises-v1",
      exerciseDefinitionSHA256: String(repeating: "a", count: 64),
      exerciseID: "foundation-ball-initial-b-v1",
      protocolID: "bilabial-closure-v1",
      prompt: "ball",
      targetLabel: "Beginning /b/",
      attemptTarget: 1,
      retryLimit: 1
    )
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: assignment.assignmentID,
      exerciseID: assignment.exerciseID
    )
    let model = PracticeSessionModel(
      assignment: assignment,
      capturer: MockAudioCapturer(permissionGranted: true),
      submitter: SequenceSubmitter(statuses: [.retryCapture, .retryCapture]),
      attemptContext: context, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )

    await model.startRecording()
    await model.stopRecording()
    model.tryAgain()
    XCTAssertEqual(model.currentRetry, 1)

    await model.startRecording()
    await model.stopRecording()
    model.tryAgain()

    XCTAssertEqual(model.phase, .retryLimitReached)
    XCTAssertEqual(model.currentRepetition, 1)
    XCTAssertNotEqual(model.phase, .completed)
  }

  func testLeavingDuringUploadDeletesMediaAndRequiresAssignmentRefresh() async throws {
    let capturer = MockAudioCapturer(
      permissionGranted: true,
      summary: CaptureSummary(duration: 1, averagePower: -20)
    )
    let context = try LearnerAttemptContext(
      deviceToken: String(repeating: "x", count: 43),
      assignmentID: LearnerPracticeAssignment.localPreview.assignmentID,
      exerciseID: "foundation-ball-initial-b-v1"
    )
    let submitter = SlowSubmitter()
    let model = PracticeSessionModel(
      assignment: .localPreview,
      capturer: capturer,
      submitter: submitter,
      attemptContext: context, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    await model.startRecording()

    let upload = Task { await model.stopRecording() }
    await submitter.waitUntilStarted()
    model.appDidBecomeInactive()
    await upload.value

    XCTAssertEqual(
      model.phase,
      .failed("The last save could not be confirmed. Refresh practice before recording again.")
    )
    XCTAssertTrue(model.assignmentRefreshRequired)
    XCTAssertEqual(capturer.discardCount, 1)
    XCTAssertEqual(model.currentRepetition, 1)
    model.tryAgain()
    await model.startRecording()
    XCTAssertEqual(capturer.startCount, 1)
    XCTAssertTrue(model.assignmentRefreshRequired)
  }

  func testVisualCaptureStaysOffUnlessTheResearchConfigurationIsEnabled() async {
    let visual = MockVisualCaptureMonitor(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true), visualMonitor: visual,
      hardwareOwnership: AudioHardwareOwnership(), fileOwnership: ProcessAudioFileOwnership())

    await model.prepareVisualCapture()

    XCTAssertEqual(model.visualState, .off)
    XCTAssertEqual(visual.permissionRequestCount, 0)
    XCTAssertEqual(visual.startCount, 0)
  }

  func testVisualPermissionDenialLeavesAudioPracticeAvailable() async {
    let visual = MockVisualCaptureMonitor(permissionGranted: false)
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )

    await model.prepareVisualCapture()

    XCTAssertEqual(model.visualState, .permissionDenied)
    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(visual.startCount, 0)
  }

  func testVisualQualityUpdatesOnlyFramingState() async {
    let visual = MockVisualCaptureMonitor(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    await model.prepareVisualCapture()
    XCTAssertEqual(model.visualState, .checking)

    visual.emit(.success(goodVisualSnapshot()))
    await Task.yield()

    guard case .ready(let snapshot) = model.visualState else {
      return XCTFail("Expected usable framing evidence")
    }
    XCTAssertTrue(snapshot.isUsable)
    XCTAssertEqual(model.phase, .ready)
    XCTAssertTrue(model.visualFeasibilityReportAvailable)
  }

  func testLeavingTheAppStopsAndClearsVisualCapture() async {
    let visual = MockVisualCaptureMonitor(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    await model.prepareVisualCapture()

    model.appDidBecomeInactive()

    XCTAssertEqual(model.visualState, .off)
    XCTAssertEqual(visual.stopCount, 1)
  }

  func testLeavingDuringCameraPermissionCannotStartCaptureLater() async {
    let visual = MockVisualCaptureMonitor(
      permissionGranted: true,
      permissionDelay: .milliseconds(50)
    )
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    let preparation = Task { await model.prepareVisualCapture() }
    await waitForConsumerState { visual.permissionRequestCount > 0 }

    model.appDidBecomeInactive()
    await preparation.value

    XCTAssertEqual(model.visualState, .off)
    XCTAssertEqual(visual.startCount, 0)
  }

  func testStaleVisualCallbackCannotRestoreCameraStateAfterLeaving() async {
    let visual = MockVisualCaptureMonitor(
      permissionGranted: true,
      clearsUpdateOnStop: false
    )
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    await model.prepareVisualCapture()

    model.appDidBecomeInactive()
    visual.emit(.success(goodVisualSnapshot()))
    await Task.yield()

    XCTAssertEqual(model.visualState, .off)
  }

  func testVisualExtractionFailureStopsCameraAndKeepsAudioReady() async {
    let visual = MockVisualCaptureMonitor(permissionGranted: true)
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    await model.prepareVisualCapture()

    visual.emit(.failure(VisualCaptureMonitorError.landmarkExtractionFailed))
    await Task.yield()

    guard case .unavailable = model.visualState else {
      return XCTFail("Expected camera-unavailable state")
    }
    XCTAssertEqual(visual.stopCount, 1)
    XCTAssertEqual(model.phase, .ready)
  }

  func testFinalizingAReportStopsCaptureAndRejectsStaleUpdates() async throws {
    let visual = MockVisualCaptureMonitor(
      permissionGranted: true,
      clearsUpdateOnStop: false
    )
    let model = PracticeSessionModel(
      capturer: MockAudioCapturer(permissionGranted: true),
      visualConfiguration: localFeasibilityConfiguration,
      visualMonitor: visual, hardwareOwnership: AudioHardwareOwnership(),
      fileOwnership: ProcessAudioFileOwnership()
    )
    await model.prepareVisualCapture()
    visual.emit(.success(goodVisualSnapshot()))
    await Task.yield()

    let data = try XCTUnwrap(model.finalizeVisualFeasibilityReport())
    visual.emit(.success(goodVisualSnapshot()))
    await Task.yield()
    let report = try JSONDecoder().decode(VisualFeasibilityReport.self, from: data)

    XCTAssertEqual(visual.stopCount, 1)
    XCTAssertEqual(model.visualState, .off)
    XCTAssertTrue(model.visualFeasibilityReportAvailable)
    XCTAssertTrue(model.visualFeasibilityReportIsFinalized)
    XCTAssertFalse(model.visualCaptureAvailable)
    XCTAssertEqual(report.frames.totalFrames, 1)
    XCTAssertEqual(model.finalizeVisualFeasibilityReport(), data)

    model.completeVisualFeasibilityExport()

    XCTAssertFalse(model.visualFeasibilityReportAvailable)
    XCTAssertTrue(model.visualCaptureAvailable)
  }
}

private actor SuccessfulSubmitter: AttemptSubmitting {
  let receipt: LearnerAttemptReceipt

  init(receipt: LearnerAttemptReceipt) {
    self.receipt = receipt
  }

  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt {
    receipt
  }
}

private actor SlowSubmitter: AttemptSubmitting {
  private var started = false

  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt {
    started = true
    try await Task.sleep(for: .milliseconds(50))
    return LearnerAttemptReceipt(
      attemptId: attemptID,
      status: .acceptedSilent,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes: []
    )
  }

  func waitUntilStarted() async {
    let deadline = ContinuousClock.now + .seconds(2)
    while !started, ContinuousClock.now < deadline { await Task.yield() }
    XCTAssertTrue(started)
  }
}

private actor SequenceSubmitter: AttemptSubmitting {
  private var statuses: [LearnerAttemptStatus]
  private var submittedContexts: [LearnerAttemptContext] = []

  init(statuses: [LearnerAttemptStatus]) {
    self.statuses = statuses
  }

  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt {
    submittedContexts.append(context)
    let status = statuses.removeFirst()
    return LearnerAttemptReceipt(
      attemptId: attemptID,
      status: status,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes: status == .retryCapture ? [.audioTooQuiet] : []
    )
  }

  func contexts() -> [LearnerAttemptContext] { submittedContexts }
}

private actor RejectingSubmitter: AttemptSubmitting {
  let error: LearnerAttemptAPIError

  init(error: LearnerAttemptAPIError) {
    self.error = error
  }

  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt {
    throw error
  }
}

@MainActor
private final class MockAudioCapturer: AudioCapturing {
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? { nil }
  let cleanupState = CaptureCleanupState.idle
  /// This counter-only mock never creates media or simulates cleanup failure.
  /// Subscribe on MainActor for synchronous initial delivery.
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    Just(cleanupState).eraseToAnyPublisher()
  }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    .init(operationID: operationID, result: .refused)
  }

  let permissionGranted: Bool
  let permissionDelay: Duration
  let summary: CaptureSummary
  private(set) var permissionRequestCount = 0
  private(set) var startCount = 0
  private(set) var stopCount = 0
  private(set) var cancelCount = 0
  private(set) var discardCount = 0
  private var finishCallbacks: [@MainActor (Bool) async -> Void] = []

  init(
    permissionGranted: Bool,
    permissionDelay: Duration = .zero,
    summary: CaptureSummary = CaptureSummary(
      duration: 1.0,
      averagePower: -20
    )
  ) {
    self.permissionGranted = permissionGranted
    self.permissionDelay = permissionDelay
    self.summary = summary
  }

  func requestPermission() async -> Bool {
    permissionRequestCount += 1
    if permissionDelay > .zero {
      try? await Task.sleep(for: permissionDelay)
    }
    return permissionGranted
  }

  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    startCount += 1
    finishCallbacks.append(onFinish)
  }

  func finish(recordingIndex: Int? = nil, successfully: Bool = true) async {
    let index = recordingIndex ?? (finishCallbacks.count - 1)
    await finishCallbacks[index](successfully)
  }

  func stop() throws -> CapturedRecording {
    stopCount += 1
    return CapturedRecording(
      url: FileManager.default.temporaryDirectory
        .appendingPathComponent("mock-attempt-\(UUID()).wav"),
      summary: summary
    )
  }

  func cancel() throws {
    cancelCount += 1
  }

  func discard(_ recording: CapturedRecording) throws {
    discardCount += 1
  }
}

private final class MockVisualCaptureMonitor: VisualCaptureMonitoring, @unchecked Sendable {
  let permissionGranted: Bool
  let permissionDelay: Duration
  let clearsUpdateOnStop: Bool
  var previewSession: AVCaptureSession? { nil }
  private(set) var permissionRequestCount = 0
  private(set) var startCount = 0
  private(set) var stopCount = 0
  private var update: (@Sendable (Result<VisualQualitySnapshot, Error>) -> Void)?

  init(
    permissionGranted: Bool,
    permissionDelay: Duration = .zero,
    clearsUpdateOnStop: Bool = true
  ) {
    self.permissionGranted = permissionGranted
    self.permissionDelay = permissionDelay
    self.clearsUpdateOnStop = clearsUpdateOnStop
  }

  func requestPermission() async -> Bool {
    permissionRequestCount += 1
    if permissionDelay > .zero {
      try? await Task.sleep(for: permissionDelay)
    }
    return permissionGranted
  }

  func start(
    onUpdate: @escaping @Sendable (Result<VisualQualitySnapshot, Error>) -> Void
  ) async throws {
    startCount += 1
    update = onUpdate
  }

  func stop() {
    stopCount += 1
    if clearsUpdateOnStop { update = nil }
  }

  func emit(_ result: Result<VisualQualitySnapshot, Error>) {
    update?(result)
  }
}

private func goodVisualSnapshot() -> VisualQualitySnapshot {
  VisualQualitySnapshot(
    runtimeVersion: VisualCaptureQualityAssessor.runtimeVersion,
    captureQualityScore: 0.92,
    issues: [],
    faceCoverage: 0.28,
    faceCenterOffset: 0.02,
    mouthWidthRatio: 0.3,
    mouthApertureRatio: 0.12,
    yawRadians: 0.02,
    rollRadians: 0
  )
}

/// Real concrete capturer coordination with isolated generated files; permission is controlled.
/// Neither the production AV driver nor AV permission is invoked by these consumer tests.
@MainActor
final class ConsumerCaptureFixture {
  let directory: URL
  let hardware = AudioHardwareOwnership()
  let files = ProcessAudioFileOwnership()
  let control = ConsumerCaptureControl()
  let driver = ConsumerCaptureDriver()
  let capture: ConsumerPermissionCapture

  init(startupFailure: Bool = false) throws {
    directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "consumer-capture-\(UUID())")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let store = TemporaryRecordingStore(
      directory: startupFailure ? directory.appendingPathComponent("absent") : directory)
    let control = control
    let driver = driver
    capture = ConsumerPermissionCapture(
      SystemAudioCapturer(
        recordingStore: store, fileOwnership: files, hardwareOwnership: hardware,
        driverFactory: {
          control.factoryCalls += 1
          return driver
        },
        summaryReader: { _ in .init(duration: 1, averagePower: -20) },
        removeFile: { url in
          control.removals += 1
          if control.failRemoval { throw ConsumerCaptureFailure.controlled }
          try store.removeRecordingIfPresent(at: url)
        }))
  }
  func model() -> PracticeSessionModel {
    PracticeSessionModel(capturer: capture, hardwareOwnership: hardware, fileOwnership: files)
  }
  func dispose() {
    // Explicit recovery of only fixture-held pending IDs before exact fixture-directory removal.
    control.failRemoval = false
    driver.failDeactivate = false
    driver.failConfigure = false
    if let id = hardware.blockedCaptureOperationID {
      _ = hardware.retryCaptureCleanup(operationID: id)
    }
    for id in files.pendingCleanupOwners { _ = files.retryCleanup(owner: id) }
    try? FileManager.default.removeItem(at: directory)
  }
}

@MainActor
final class ConsumerPermissionCapture: AudioCapturing {
  let concrete: SystemAudioCapturer
  var holdsPermission = false
  var permission: CheckedContinuation<Bool, Never>?
  init(_ concrete: SystemAudioCapturer) { self.concrete = concrete }
  var cleanupState: CaptureCleanupState { concrete.cleanupState }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    concrete.cleanupStatePublisher
  }
  func requestPermission() async -> Bool {
    if holdsPermission { return await withCheckedContinuation { permission = $0 } }
    return true
  }
  func grant() {
    permission?.resume(returning: true)
    permission = nil
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    try concrete.start(onFinish: onFinish)
  }
  func stop() throws -> CapturedRecording { try concrete.stop() }
  func cancel() throws { try concrete.cancel() }
  func discard(_ recording: CapturedRecording) throws { try concrete.discard(recording) }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    concrete.retryCleanup(operationID: operationID)
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
    concrete.completedFileCleanup(operationID: operationID)
  }
}

@MainActor
final class ConsumerCaptureControl {
  var factoryCalls = 0
  var removals = 0
  var failRemoval = false
}

private enum ConsumerCaptureFailure: Error { case controlled }
@MainActor
final class ConsumerCaptureDriver: CaptureHardwareDriver {
  var failConfigure = false
  var failDeactivate = false
  var deactivations = 0
  var url: URL?
  func configureActivate() throws { if failConfigure { throw ConsumerCaptureFailure.controlled } }
  func createRecorder(
    url: URL, recorderID: UUID, onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    self.url = url
    // Unique generated bytes; controlled summary, not a recording claim.
    try Data([1, 2, 3]).write(to: url)
  }
  func prepare() throws -> Bool { true }
  func record() throws -> Bool { true }
  func stop() throws {}
  func detachRelease() throws {}
  func deactivate() throws {
    deactivations += 1
    if failDeactivate { throw ConsumerCaptureFailure.controlled }
  }
}

@MainActor
func waitForConsumerState(
  _ predicate: @MainActor () -> Bool, file: StaticString = #filePath, line: UInt = #line
) async {
  let deadline = ContinuousClock.now + .seconds(2)
  while !predicate(), ContinuousClock.now < deadline { await Task.yield() }
  XCTAssertTrue(predicate(), "Expected controlled state was not reached", file: file, line: line)
}

private actor HeldConsumerSubmitter: AttemptSubmitting {
  private var continuation: CheckedContinuation<LearnerAttemptReceipt, Never>?
  func submit(recording: CapturedRecording, attemptID: String, context: LearnerAttemptContext)
    async throws -> LearnerAttemptReceipt
  {
    await withCheckedContinuation { continuation = $0 }
  }
  func waitUntilStarted() async {
    let deadline = ContinuousClock.now + .seconds(2)
    while continuation == nil, ContinuousClock.now < deadline { await Task.yield() }
    XCTAssertNotNil(continuation)
  }
  func succeed(with receipt: LearnerAttemptReceipt) {
    continuation?.resume(returning: receipt)
    continuation = nil
  }
}

private actor CountingConsumerSubmitter: AttemptSubmitting {
  private var calls = 0
  func callCount() -> Int { calls }
  func submit(recording: CapturedRecording, attemptID: String, context: LearnerAttemptContext)
    async throws -> LearnerAttemptReceipt
  {
    calls += 1
    return .init(
      attemptId: attemptID, status: .acceptedSilent, feedbackAvailable: false,
      mediaRetained: false, reasonCodes: [])
  }
}
