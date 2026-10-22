#if DEBUG
  import Combine
  import Foundation
  import XCTest

  @testable import CadenceLearner

  @MainActor
  final class ResearchAssessmentSessionTests: XCTestCase {
    func testWrongRetryWhileRecordingPreservesAttemptAndOriginalCaptureOwnership() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      let lease = try XCTUnwrap(fixture.hardware.currentLease)
      let ledger = session.attemptLedger
      session.retryCaptureCleanup(operationID: UUID())
      session.retryCaptureCleanup(operationID: lease.operationID)
      XCTAssertEqual(session.phase, .recording)
      XCTAssertEqual(session.attemptLedger.rows.map(\.id), ledger.rows.map(\.id))
      XCTAssertEqual(session.attemptLedger.totalStarted, ledger.totalStarted)
      XCTAssertEqual(session.attemptLedger.totalTerminal, ledger.totalTerminal)
      XCTAssertEqual(session.attemptLedger.reasonCounts, ledger.reasonCounts)
      XCTAssertEqual(session.attemptLedger.outcomeCounts, ledger.outcomeCounts)
      XCTAssertTrue(session.requiresCaptureCleanupBeforeDeparture)
      await session.startRecording()
      XCTAssertEqual(fixture.control.factoryCalls, 1)
      XCTAssertEqual(fixture.hardware.currentLease, lease)
      fixture.driver.failDeactivate = true
      XCTAssertFalse(session.end())
      XCTAssertEqual(fixture.hardware.currentLease, lease)
      fixture.driver.failDeactivate = false
      session.retryCaptureCleanup(operationID: lease.operationID)
      XCTAssertTrue(session.end())
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(processor.calls.isEmpty)
    }

    func testReentrantFileOnlyCancelReceiptEndsWithoutAnUnknownFailure() async throws {
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
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      let lease = try XCTUnwrap(fixture.hardware.currentLease)
      fixture.control.failRemoval = true
      XCTAssertTrue(session.end())
      XCTAssertEqual(recoveredID, lease.operationID)
      XCTAssertTrue(
        fixture.capture.completedFileCleanup(operationID: lease.operationID)?
          .allRequestedFilesRemoved
          == true)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(session.captureCleanupState, .idle)
      XCTAssertTrue(session.captureCleanupRetryIDs.isEmpty)
      XCTAssertFalse(session.requiresCaptureCleanupBeforeDeparture)
      XCTAssertTrue(session.captureDisabledForVisit)
      XCTAssertTrue(session.end())
      XCTAssertEqual(fixture.driver.deactivations, 1)
      XCTAssertEqual(fixture.control.removals, 2)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertFalse(FileManager.default.fileExists(atPath: try XCTUnwrap(fixture.driver.url).path))
      XCTAssertTrue(processor.calls.isEmpty)
      assertTerminal(session, reason: .cleanupBlocked)
      session.retryCaptureCleanup(operationID: lease.operationID)
      XCTAssertEqual(fixture.control.removals, 2)
    }

    func testReentrantPositiveCancelReceiptEndsWithoutAnUnidentifiedBlock() async throws {
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
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      let lease = try XCTUnwrap(fixture.hardware.currentLease)
      fixture.driver.failDeactivate = true
      XCTAssertTrue(session.end())
      XCTAssertEqual(recoveredID, lease.operationID)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertTrue(session.captureCleanupRetryIDs.isEmpty)
      XCTAssertFalse(session.requiresCaptureCleanupBeforeDeparture)
      XCTAssertTrue(session.end())
      XCTAssertEqual(fixture.driver.deactivations, 2)
      XCTAssertEqual(fixture.control.removals, 1)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertTrue(processor.calls.isEmpty)
      assertTerminal(session, reason: .sessionEnded)
    }

    func testCloseInsideProcessingPublicationPreventsProcessorLaunchAndReassertsEnded() async throws
    {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      var handled = false
      let observation = session.$phase.sink { phase in
        guard phase == .processing, !handled else { return }
        handled = true
        XCTAssertTrue(session.end())
      }
      defer { observation.cancel() }
      await session.startRecording()
      session.stopRecording()
      // The task would invoke process if it had been launched; yield once to expose it.
      await Task.yield()
      XCTAssertTrue(handled)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertTrue(processor.calls.isEmpty)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertEqual(fixture.control.removals, 1)
      assertTerminal(session, reason: .sessionEnded)
    }

    func testDroppingSessionDuringHeldProcessingRetainsIndependentProducerCleanup() async throws {
      for failRemoval in [false, true] {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "assessment-drop-\(UUID())")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let hardware = AudioHardwareOwnership()
        let files = ProcessAudioFileOwnership()
        let control = ConsumerCaptureControl()
        let driver = ConsumerCaptureDriver()
        let store = TemporaryRecordingStore(directory: directory)
        var producer: ConsumerPermissionCapture? = ConsumerPermissionCapture(
          SystemAudioCapturer(
            recordingStore: store, fileOwnership: files, hardwareOwnership: hardware,
            driverFactory: { driver },
            summaryReader: { _ in .init(duration: 1, averagePower: -20) },
            removeFile: { url in
              control.removals += 1
              if control.failRemoval { throw CocoaError(.fileWriteUnknown) }
              try store.removeRecordingIfPresent(at: url)
            }))
        weak var retainedProducer = producer?.concrete
        let processor = AssessmentSessionProcessor()
        processor.holdsCompletion = true
        var session: ResearchAssessmentSession? = ResearchAssessmentSession(
          capturer: producer, processor: processor,
          hardwareOwnership: hardware, fileOwnership: files)
        session!.ageYears = 9
        session!.selectedEntry = try entry("r-beginning-rabbit")
        session!.localProcessingEnabled = true
        session!.prepare()
        await session!.startRecording()
        session!.stopRecording()
        await wait { processor.pending }
        let call = try XCTUnwrap(processor.calls.first)
        let owner = try XCTUnwrap(call.recording.cleanupOwnerID)
        weak var droppedSession = session
        control.failRemoval = failRemoval
        session = nil
        producer = nil
        XCTAssertNil(droppedSession)
        XCTAssertNotNil(retainedProducer)
        XCTAssertNil(hardware.currentLease)
        XCTAssertTrue(files.protectedURLs.contains(call.recording.url))
        processor.resolve(.success(.processedUnverified(milliseconds: 12)))
        await wait { control.removals == 1 }
        if failRemoval {
          XCTAssertTrue(files.pendingCleanupOwners.contains(owner))
          XCTAssertTrue(FileManager.default.fileExists(atPath: call.recording.url.path))
          XCTAssertNotNil(retainedProducer)
          control.failRemoval = false
          XCTAssertTrue(files.retryCleanup(owner: owner))
          XCTAssertEqual(control.removals, 2)
        }
        XCTAssertTrue(files.protectedURLs.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: call.recording.url.path))
        await wait { retainedProducer == nil }
        XCTAssertEqual(processor.calls.count, 1)
      }
    }

    func testConcreteHardwareFailureHoldsCloseAndExactRetryDoesNotProcessLateAudio() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      fixture.driver.failDeactivate = true
      session.stopRecording()
      let id = try XCTUnwrap(session.captureCleanupState.hardwareBlockedOperationID)
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertFalse(session.end())
      XCTAssertFalse(session.end())
      session.retryCaptureCleanup(operationID: UUID())
      XCTAssertEqual(fixture.driver.deactivations, 1)
      fixture.driver.failDeactivate = false
      session.retryCaptureCleanup(operationID: id)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(session.end())
      XCTAssertEqual(session.phase, .ended)
      XCTAssertTrue(processor.calls.isEmpty)
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testConcreteConfigureFailureWithUnconfirmedCleanupRetainsExactLease() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      fixture.driver.failConfigure = true
      fixture.driver.failDeactivate = true
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      let id = try XCTUnwrap(session.captureCleanupState.hardwareBlockedOperationID)
      XCTAssertEqual(fixture.hardware.currentLease?.operationID, id)
      XCTAssertFalse(session.end())
      XCTAssertEqual(fixture.control.factoryCalls, 1)
      fixture.driver.failDeactivate = false
      session.retryCaptureCleanup(operationID: id)
      XCTAssertTrue(session.end())
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertTrue(processor.calls.isEmpty)
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testConcreteProcessingDeletionFailureNeverClaimsDeletedOrResurrectsOutcome() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      fixture.control.failRemoval = true
      session.stopRecording()
      await wait { session.phase == .cleanupBlocked }
      let id = try XCTUnwrap(session.captureCleanupState.fileBlockedOwnerIDs.first)
      let url = try XCTUnwrap(fixture.driver.url)
      XCTAssertEqual(processor.calls.count, 1)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(fixture.files.pendingCleanupOwners.contains(id))
      session.retry()
      session.prepare()
      await session.startRecording()
      XCTAssertEqual(fixture.control.factoryCalls, 1)
      XCTAssertEqual(fixture.control.removals, 1)
      fixture.control.failRemoval = false
      session.retryCaptureCleanup(operationID: id)
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertTrue(session.captureDisabledForVisit)
      XCTAssertEqual(processor.calls.count, 1)
      XCTAssertTrue(session.end())
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testConcreteFileOnlySecondCloseLeavesReachableOriginalProducer() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      processor.holdsCompletion = true
      let session = try configured(fixture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      fixture.control.failRemoval = true
      XCTAssertFalse(session.end())
      let id = try XCTUnwrap(session.captureCleanupState.fileBlockedOwnerIDs.first)
      let url = try XCTUnwrap(fixture.driver.url)
      XCTAssertTrue(session.canLeaveWithFileWarning)
      XCTAssertTrue(session.end())
      XCTAssertEqual(session.phase, .ended)
      XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
      XCTAssertEqual(fixture.control.removals, 1)
      processor.resolve(.success(.processedUnverified(milliseconds: 12)))
      await wait { processor.returnedCount == 1 }
      XCTAssertEqual(session.phase, .ended)
      fixture.control.failRemoval = false
      XCTAssertTrue(fixture.files.retryCleanup(owner: id))
      XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testLocalFailureWithoutProcessHeldRecoveryCannotLeaveOnSecondClose() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      processor.holdsCompletion = true
      let session = try configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      capture.failDiscard = true
      XCTAssertFalse(session.end())
      XCTAssertFalse(session.canLeaveWithFileWarning)
      XCTAssertFalse(session.end())
      XCTAssertEqual(capture.discardCount, 1)
      processor.resolve(.success(.processedUnverified(milliseconds: 12)))
      await wait { processor.returnedCount == 1 }
      capture.failDiscard = false
      session.retryCaptureCleanup(operationID: try XCTUnwrap(session.captureCleanupRetryIDs.first))
      XCTAssertTrue(session.end())
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testConcreteStartupFailureDisablesVisitWithoutInventingRecoveryIdentity() async throws {
      let fixture = try ConsumerCaptureFixture(startupFailure: true)
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertTrue(session.captureDisabledForVisit)
      XCTAssertTrue(session.captureCleanupRetryIDs.isEmpty)
      XCTAssertFalse(session.requiresCaptureCleanupBeforeDeparture)
      XCTAssertEqual(fixture.control.factoryCalls, 0)
      session.retry()
      await session.startRecording()
      XCTAssertEqual(fixture.control.factoryCalls, 0)
      XCTAssertTrue(session.end())
      XCTAssertTrue(processor.calls.isEmpty)
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testConcreteCloseRevokesHeldPermissionBeforeAnyFactoryWork() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      fixture.capture.holdsPermission = true
      let session = try configured(fixture, AssessmentSessionProcessor())
      let start = Task { await session.startRecording() }
      await wait { fixture.capture.permission != nil }
      session.appDidBecomeInactive()
      XCTAssertEqual(session.phase, .requestingPermission)
      XCTAssertTrue(session.end())
      fixture.capture.grant()
      await start.value
      XCTAssertEqual(fixture.control.factoryCalls, 0)
      XCTAssertEqual(session.phase, .ended)
      assertTerminal(session, reason: .sessionEnded)
    }

    func testNewAssessmentVisitCanRecoverOnlyTheProcessHeldCaptureIdentity() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      var old: ResearchAssessmentSession? = try configured(fixture, AssessmentSessionProcessor())
      await old!.startRecording()
      fixture.driver.failDeactivate = true
      old!.stopRecording()
      let id = try XCTUnwrap(fixture.hardware.blockedCaptureOperationID)
      weak var oldVisit = old
      old = nil
      XCTAssertNil(oldVisit)
      let freshCapture = try AssessmentSessionCapturer()
      defer { freshCapture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = ResearchAssessmentSession(
        capturer: freshCapture, processor: processor,
        hardwareOwnership: fixture.hardware, fileOwnership: fixture.files)
      XCTAssertEqual(session.captureCleanupState.hardwareBlockedOperationID, id)
      session.retryCaptureCleanup(operationID: UUID())
      XCTAssertEqual(fixture.driver.deactivations, 1)
      fixture.driver.failDeactivate = false
      session.retryCaptureCleanup(operationID: id)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertEqual(session.phase, .setup)
      XCTAssertEqual(session.attemptLedger.totalStarted, 0)
      XCTAssertTrue(processor.calls.isEmpty)
      XCTAssertEqual(freshCapture.startCount, 0)
    }

    func testSynchronousProducerRetryCannotLoseFileIdentityOrRestoreAssessmentResult() async throws
    {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      var recoveredID: UUID?
      let observation = fixture.capture.cleanupStatePublisher.sink { state in
        guard let id = state.fileBlockedOwnerIDs.first, recoveredID == nil else { return }
        recoveredID = id
        fixture.control.failRemoval = false
        XCTAssertTrue(fixture.capture.retryCleanup(operationID: id).allRequestedFilesRemoved)
      }
      defer { observation.cancel() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      await session.startRecording()
      fixture.control.failRemoval = true
      session.stopRecording()
      await wait { session.phase == .cleanupBlocked }
      let id = try XCTUnwrap(recoveredID)
      XCTAssertTrue(
        fixture.capture.completedFileCleanup(operationID: id)?.allRequestedFilesRemoved == true)
      XCTAssertTrue(session.captureDisabledForVisit)
      XCTAssertTrue(session.captureCleanupRetryIDs.isEmpty)
      XCTAssertTrue(session.end())
      XCTAssertEqual(session.phase, .ended)
      XCTAssertFalse(FileManager.default.fileExists(atPath: try XCTUnwrap(fixture.driver.url).path))
      XCTAssertEqual(fixture.control.removals, 2)
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testInterruptedCaptureCannotPublishStaleCleanupAfterSynchronousRecoveryAndEnd()
      async throws
    {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      var requested = false
      var originalOwner: UUID?
      var recoveredOwner: UUID?
      var firstEvents: [ResearchAssessmentPhase] = []
      var secondEvents: [ResearchAssessmentPhase] = []
      let first = session.$phase.sink { phase in
        firstEvents.append(phase)
        guard phase == .cleanupBlocked, !requested else { return }
        requested = true
        XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
        guard let id = session.captureCleanupRetryIDs.first else {
          return XCTFail("The failed original capture must retain its exact cleanup owner")
        }
        recoveredOwner = id
        XCTAssertEqual(id, originalOwner)
        fixture.control.failRemoval = false
        session.retryCaptureCleanup(operationID: id)
        XCTAssertTrue(
          fixture.capture.completedFileCleanup(operationID: id)?.allRequestedFilesRemoved == true)
        XCTAssertTrue(session.end())
      }
      let second = session.$phase.sink { secondEvents.append($0) }
      defer {
        first.cancel()
        second.cancel()
      }
      await session.startRecording()
      originalOwner = try XCTUnwrap(fixture.hardware.currentLease).operationID
      fixture.control.failRemoval = true
      // This path is synchronous after controlled permission; no processing task or wait.
      session.audioWasInterrupted()
      XCTAssertTrue(requested)
      XCTAssertEqual(recoveredOwner, originalOwner)
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(firstEvents, secondEvents)
      XCTAssertEqual(Array(firstEvents.suffix(2)), [.cleanupBlocked, .ended])
      XCTAssertTrue(session.captureCleanupRetryIDs.isEmpty)
      XCTAssertFalse(session.requiresCaptureCleanupBeforeDeparture)
      XCTAssertNil(fixture.hardware.currentLease)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertFalse(FileManager.default.fileExists(atPath: try XCTUnwrap(fixture.driver.url).path))
      XCTAssertEqual(fixture.control.removals, 2)
      XCTAssertEqual(fixture.driver.deactivations, 1)
      XCTAssertTrue(processor.calls.isEmpty)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      assertTerminal(session, reason: .cleanupBlocked)
      XCTAssertTrue(session.end())
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(fixture.control.removals, 2)
    }

    func testCleanupPhaseListenerCanRetryAndCloseWithoutLaterStateRegression() async throws {
      let fixture = try ConsumerCaptureFixture()
      defer { fixture.dispose() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(fixture, processor)
      var requested = false
      var firstEvents: [ResearchAssessmentPhase] = []
      var secondEvents: [ResearchAssessmentPhase] = []
      let first = session.$phase.sink { phase in
        firstEvents.append(phase)
        guard phase == .cleanupBlocked, !requested else { return }
        requested = true
        XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
        let id = session.captureCleanupRetryIDs.first
        XCTAssertNotNil(id)
        fixture.control.failRemoval = false
        if let id { session.retryCaptureCleanup(operationID: id) }
        XCTAssertTrue(session.end())
      }
      let second = session.$phase.sink { secondEvents.append($0) }
      defer {
        first.cancel()
        second.cancel()
      }
      await session.startRecording()
      fixture.control.failRemoval = true
      session.stopRecording()
      await wait { session.phase == .ended }
      XCTAssertTrue(requested)
      XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
      XCTAssertEqual(firstEvents, secondEvents)
      XCTAssertEqual(Array(firstEvents.suffix(2)), [.cleanupBlocked, .ended])
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      XCTAssertEqual(fixture.control.removals, 2)
    }

    func testPrepareRequiresExplicitScopePromptAndOptInWithoutStartingAnything() throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = ResearchAssessmentSession(
        capturer: capture, processor: processor, hardwareOwnership: AudioHardwareOwnership(),
        fileOwnership: ProcessAudioFileOwnership())
      session.prepare()
      XCTAssertEqual(session.phase, .setup)
      session.ageYears = 9
      session.prepare()
      XCTAssertEqual(session.phase, .setup)
      session.selectedEntry = try entry("r-beginning-rabbit")
      session.prepare()
      XCTAssertEqual(session.phase, .setup)
      session.localProcessingEnabled = true
      session.prepare()
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(capture.permissionRequests, 0)
      XCTAssertEqual(processor.calls.count, 0)
      XCTAssertEqual(session.attemptLedger.totalStarted, 0)
    }

    func testAgeBoundariesAndZHRemainExplicitlyUnsupported() async throws {
      for age in [5, 6, 12, 13] {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        let processor = AssessmentSessionProcessor()
        let session = try configured(capture, processor, age: age)
        if age == 6 || age == 12 {
          XCTAssertEqual(session.phase, .ready)
        } else {
          assertUnavailable(session)
          assertTerminal(session, reason: .ageOutOfRange)
          XCTAssertEqual(session.attemptLedger.rows.first?.startKind, .preflightRejected)
          await session.startRecording()
          XCTAssertEqual(capture.startCount, 0)
          XCTAssertEqual(session.attemptLedger.totalStarted, 1)
        }
      }
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(capture, processor)
      session.selectedEntry = try entry("zh-middle-treasure")
      session.prepare()
      assertUnavailable(session)
      await session.startRecording()
      XCTAssertEqual(capture.permissionRequests, 0)
      XCTAssertEqual(processor.calls.count, 0)
      assertTerminal(session, reason: .unsupportedTarget)
      XCTAssertEqual(session.attemptLedger.rows.first?.startKind, .preflightRejected)
    }

    func testPermissionDenialCanBeRetriedWithoutSendingAudio() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      capture.permissionGranted = false
      let processor = AssessmentSessionProcessor()
      let session = try configured(capture, processor)
      await session.startRecording()
      XCTAssertEqual(session.phase, .permissionDenied)
      XCTAssertEqual(session.attemptLedger.totalStarted, 1)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      XCTAssertEqual(session.attemptLedger.rows.first?.terminalReason, .permissionDenied)
      XCTAssertEqual(capture.startCount, 0)
      XCTAssertEqual(processor.calls.count, 0)
      session.retry()
      capture.permissionGranted = true
      await session.startRecording()
      XCTAssertEqual(session.phase, .recording)
      let first = try XCTUnwrap(session.attemptLedger.rows.first)
      let retry = try XCTUnwrap(session.attemptLedger.rows.last)
      XCTAssertNotEqual(retry.id, first.id)
      XCTAssertEqual(retry.previousAttemptId, first.id)
      XCTAssertEqual(retry.retryIndex, 1)
      XCTAssertNil(retry.terminalReason)
      XCTAssertEqual(session.attemptLedger.totalStarted, 2)
      session.end()
      XCTAssertEqual(session.attemptLedger.totalTerminal, 2)
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalReason, .sessionEnded)
      XCTAssertGreaterThanOrEqual(try XCTUnwrap(session.attemptLedger.rows.last?.elapsedSeconds), 0)
    }

    func testPermissionDialogInactivityPreservesRequestButBackgroundInvalidatesIt() async throws {
      for background in [false, true] {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        capture.holdsPermission = true
        let session = try configured(capture, AssessmentSessionProcessor())
        let starting = Task { await session.startRecording() }
        await wait { capture.permissionPending }
        session.appDidBecomeInactive()
        if background { session.appDidEnterBackground() }
        capture.resolvePermission(true)
        await starting.value
        XCTAssertEqual(session.phase, background ? .ready : .recording)
        XCTAssertEqual(capture.startCount, background ? 0 : 1)
        XCTAssertEqual(session.attemptLedger.totalStarted, 1)
        if background {
          assertTerminal(session, reason: .backgrounded)
        } else {
          XCTAssertEqual(session.attemptLedger.totalTerminal, 0)
        }
        session.end()
      }
    }

    func testChangedConfigurationWhilePermissionPendingCannotStartCapture() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      capture.holdsPermission = true
      let session = try configured(capture, AssessmentSessionProcessor())
      let starting = Task { await session.startRecording() }
      await wait { capture.permissionPending }
      session.localProcessingEnabled = false
      capture.resolvePermission(true)
      await starting.value
      XCTAssertEqual(session.phase, .setup)
      XCTAssertEqual(capture.startCount, 0)
      assertTerminal(session, reason: .setupChanged)
    }

    func testDuplicateRecordRequestsStartOnlyOneRecording() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      capture.holdsPermission = true
      let session = try configured(capture, AssessmentSessionProcessor())
      let starting = Task { await session.startRecording() }
      await wait { capture.permissionPending }
      await session.startRecording()
      capture.resolvePermission(true)
      await starting.value
      await session.startRecording()
      XCTAssertEqual(capture.permissionRequests, 1)
      XCTAssertEqual(capture.startCount, 1)
      XCTAssertEqual(session.attemptLedger.totalStarted, 1)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 0)
      session.end()
    }

    func testProcessedAudioIsDeletedAndNeverBecomesAPronunciationFinding() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(capture, processor)
      await session.startRecording()
      XCTAssertTrue(capture.fileExists)
      session.stopRecording()
      await wait { session.phase != .processing }
      XCTAssertEqual(
        session.phase,
        .unavailable(
          title: "No result to show",
          detail:
            "The local audio pipeline ran, but it cannot confirm that the prompted word was said. No pronunciation finding is available. The recording was deleted."
        ))
      XCTAssertFalse(capture.fileExists)
      XCTAssertEqual(capture.discardCount, 1)
      XCTAssertEqual(processor.calls.count, 1)
      XCTAssertEqual(processor.calls.first?.entry.id, "r-beginning-rabbit")
      XCTAssertEqual(processor.calls.first?.age, 9)
      XCTAssertEqual(processor.calls.first?.attemptId, session.attemptLedger.rows.first?.id)
      assertTerminal(session, reason: .promptMatchUnverified, outcome: .processedUnverified)
    }

    func testRejectedCaptureIsCountedAndDeletedWithoutProcessing() async throws {
      let cases: [(CaptureSummary, ResearchAssessmentTerminalReason)] = [
        (.init(duration: 0.1, averagePower: -20), .captureTooShort),
        (.init(duration: 1, averagePower: -90), .captureTooQuiet),
        (.init(duration: 5, averagePower: -20), .captureTooLong),
      ]
      for (summary, reason) in cases {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        capture.summary = summary
        let processor = AssessmentSessionProcessor()
        let session = try configured(capture, processor)
        await session.startRecording()
        session.stopRecording()
        assertUnavailable(session)
        guard case .unavailable(_, let detail) = session.phase else { return }
        XCTAssertTrue(detail.contains("Nothing was sent"))
        XCTAssertFalse(detail.contains("tone"))
        XCTAssertFalse(capture.fileExists)
        XCTAssertEqual(processor.calls.count, 0)
        assertTerminal(session, reason: reason)
      }
    }

    func testMalformedCaptureMeasurementsCannotBeSent() async throws {
      for summary in [
        CaptureSummary(duration: .nan, averagePower: -20),
        CaptureSummary(duration: 1, averagePower: .infinity),
      ] {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        capture.summary = summary
        let processor = AssessmentSessionProcessor()
        let session = try configured(capture, processor)
        await session.startRecording()
        session.stopRecording()
        assertUnavailable(session)
        XCTAssertFalse(capture.fileExists)
        XCTAssertEqual(processor.calls.count, 0)
        assertTerminal(session, reason: .invalidAudio)
      }
    }

    func testProcessingUsesFrozenAgeAndPrompt() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(capture, processor)
      await session.startRecording()
      session.ageYears = 12
      session.selectedEntry = try entry("n-middle-banana")
      session.stopRecording()
      await wait { !processor.calls.isEmpty }
      XCTAssertEqual(processor.calls.first?.age, 9)
      XCTAssertEqual(processor.calls.first?.entry.id, "r-beginning-rabbit")
      await wait { session.phase != .processing }
      XCTAssertFalse(capture.fileExists)
    }

    func testCancelledProcessingDeletesFileAndIgnoresLateSuccessDuringNewRecording() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      processor.holdsCompletion = true
      let session = try configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      session.cancelProcessing()
      XCTAssertEqual(session.phase, .ready)
      XCTAssertFalse(capture.fileExists)
      await session.startRecording()
      processor.resolve(.success(.processedUnverified(milliseconds: 12)))
      await wait { processor.returnedCount == 1 }
      await Task.yield()
      XCTAssertEqual(session.phase, .recording)
      XCTAssertTrue(capture.fileExists)
      XCTAssertTrue(processor.cancelledAtReturn)
      XCTAssertEqual(session.attemptLedger.totalStarted, 2)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      XCTAssertEqual(session.attemptLedger.rows.first?.terminalReason, .cancelled)
      XCTAssertNil(session.attemptLedger.rows.last?.terminalReason)
      session.end()
      XCTAssertEqual(session.attemptLedger.totalTerminal, 2)
    }

    func testEndAndLifecycleDuringProcessingDeleteAudioAndIgnoreLateCompletion() async throws {
      let reasons: [ResearchAssessmentTerminalReason] = [
        .sessionEnded, .becameInactive, .backgrounded, .audioInterrupted,
      ]
      for action in 0..<4 {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        let processor = AssessmentSessionProcessor()
        processor.holdsCompletion = true
        let session = try configured(capture, processor)
        await session.startRecording()
        session.stopRecording()
        await wait { processor.pending }
        switch action {
        case 0: session.end()
        case 1: session.appDidBecomeInactive()
        case 2: session.appDidEnterBackground()
        default: session.audioWasInterrupted()
        }
        XCTAssertFalse(capture.fileExists)
        assertTerminal(session, reason: reasons[action])
        let phase = session.phase
        processor.resolve(.success(.processedUnverified(milliseconds: 12)))
        await wait { processor.returnedCount == 1 }
        await Task.yield()
        XCTAssertEqual(session.phase, phase)
        assertTerminal(session, reason: reasons[action])
        session.end()
      }
    }

    func testInterruptionDeletesActiveRecordingAndIgnoresRecorderCallback() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(capture, processor)
      await session.startRecording()
      session.audioWasInterrupted()
      XCTAssertFalse(capture.fileExists)
      await capture.finish(index: 0)
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(capture.stopCount, 0)
      XCTAssertEqual(processor.calls.count, 0)
      assertTerminal(session, reason: .audioInterrupted)
    }

    func testAutomaticCompletionProcessesOnceAndOldCallbackCannotStopNewRecording() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      let session = try configured(capture, processor)
      await session.startRecording()
      await capture.finish(index: 0)
      await wait { session.phase != .processing }
      session.retry()
      await session.startRecording()
      await capture.finish(index: 0)
      XCTAssertEqual(session.phase, .recording)
      XCTAssertEqual(capture.stopCount, 1)
      XCTAssertEqual(session.attemptLedger.totalStarted, 2)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      session.end()
    }

    func testCaptureFailuresDeletePartialAudioAndPermitRetry() async throws {
      for failure in ["start", "stop", "finish"] {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        capture.failStart = failure == "start"
        capture.failStop = failure == "stop"
        let session = try configured(capture, AssessmentSessionProcessor())
        await session.startRecording()
        if failure == "stop" { session.stopRecording() }
        if failure == "finish" { await capture.finish(index: 0, successfully: false) }
        assertUnavailable(session)
        XCTAssertFalse(capture.fileExists)
        let reason: ResearchAssessmentTerminalReason =
          failure == "start"
          ? .microphoneUnavailable : (failure == "stop" ? .invalidAudio : .recordingInterrupted)
        assertTerminal(session, reason: reason)
        session.retry()
        XCTAssertEqual(session.phase, .ready)
      }
    }

    func testServiceErrorsAndUnavailableReasonsAreCalmAndDeleteAudio() async throws {
      let errors: [(ResearchAssessmentError, ResearchAssessmentTerminalReason)] = [
        (.serviceUnavailable, .serviceUnavailable), (.timeout, .timeout),
        (.invalidResponse, .invalidResponse), (.invalidRecording, .invalidAudio),
      ]
      for (error, reason) in errors {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        let processor = AssessmentSessionProcessor()
        processor.result = .failure(error)
        let session = try configured(capture, processor)
        await session.startRecording()
        session.stopRecording()
        await wait { session.phase != .processing }
        assertUnavailable(session)
        guard case .unavailable(_, let detail) = session.phase else { return }
        XCTAssertTrue(detail.contains("recording was deleted"))
        XCTAssertFalse(detail.contains(capture.url.path))
        XCTAssertFalse(capture.fileExists)
        assertTerminal(session, reason: reason)
      }
      for reason in ResearchAssessmentClient.unavailableReasons {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        let processor = AssessmentSessionProcessor()
        processor.result = .success(.unavailable(reason: reason))
        let session = try configured(capture, processor)
        await session.startRecording()
        session.stopRecording()
        await wait { session.phase != .processing }
        assertUnavailable(session)
        XCTAssertFalse(capture.fileExists)
        XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
        XCTAssertEqual(session.attemptLedger.rows.first?.terminalOutcome, .unavailable)
        XCTAssertEqual(session.attemptLedger.rows.first?.terminalReason?.rawValue, reason)
      }
    }

    func testDeletionFailureBlocksFurtherRecordingAndNeverClaimsDeletion() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let processor = AssessmentSessionProcessor()
      processor.holdsCompletion = true
      let session = try configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      capture.failDiscard = true
      session.cancelProcessing()
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertTrue(capture.fileExists)
      session.retry()
      session.prepare()
      await session.startRecording()
      XCTAssertEqual(capture.startCount, 1)
      processor.resolve(.success(.processedUnverified(milliseconds: 12)))
      await wait { processor.returnedCount == 1 }
      await Task.yield()
      XCTAssertEqual(session.phase, .cleanupBlocked)
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testCompletionCleanupFailureCannotClaimDeletedAudioOrAResult() async throws {
      let outcomes: [Result<ResearchAssessmentOutcome, Error>] = [
        .success(.processedUnverified(milliseconds: 12)),
        .failure(ResearchAssessmentError.serviceUnavailable),
      ]
      for result in outcomes {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        let processor = AssessmentSessionProcessor()
        processor.result = result
        let session = try configured(capture, processor)
        await session.startRecording()
        capture.failDiscard = true
        session.stopRecording()
        await wait { session.phase != .processing }
        XCTAssertEqual(session.phase, .cleanupBlocked)
        XCTAssertTrue(capture.fileExists)
        session.retry()
        await session.startRecording()
        XCTAssertEqual(capture.startCount, 1)
        assertTerminal(session, reason: .cleanupBlocked)
      }
    }

    func testRecorderCleanupFailureAlsoBlocksFurtherRecording() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      let session = try configured(capture, AssessmentSessionProcessor())
      await session.startRecording()
      capture.failCancel = true
      session.end()
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertTrue(capture.fileExists)
      session.resetSetup()
      await session.startRecording()
      XCTAssertEqual(capture.startCount, 1)
      assertTerminal(session, reason: .cleanupBlocked)
    }

    func testResetSetupDisablesOptInAndInvalidatesPermission() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      capture.holdsPermission = true
      let session = try configured(capture, AssessmentSessionProcessor())
      let starting = Task { await session.startRecording() }
      await wait { capture.permissionPending }
      session.resetSetup()
      capture.resolvePermission(true)
      await starting.value
      XCTAssertEqual(session.phase, .setup)
      XCTAssertFalse(session.localProcessingEnabled)
      XCTAssertEqual(capture.startCount, 0)
      assertTerminal(session, reason: .setupReset)
    }

    func testEndedSessionCannotBeRevivedByLatePermissionOrLifecycle() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      capture.holdsPermission = true
      let session = try configured(capture, AssessmentSessionProcessor())
      let starting = Task { await session.startRecording() }
      await wait { capture.permissionPending }
      session.end()
      capture.resolvePermission(true)
      await starting.value
      session.appDidBecomeInactive()
      session.appDidEnterBackground()
      session.audioWasInterrupted()
      session.retry()
      session.prepare()
      await session.startRecording()
      XCTAssertEqual(session.phase, .ended)
      XCTAssertEqual(capture.startCount, 0)
      assertTerminal(session, reason: .sessionEnded)
    }

    func testRetryChainBreaksWhenSetupChangesEvenIfItChangesBack() async throws {
      for change in 0..<3 {
        let capture = try AssessmentSessionCapturer()
        defer { capture.removeDirectory() }
        capture.permissionGranted = false
        let session = try configured(capture, AssessmentSessionProcessor())
        await session.startRecording()
        switch change {
        case 0:
          session.selectedEntry = try entry("n-middle-banana")
          session.selectedEntry = try entry("r-beginning-rabbit")
        case 1:
          session.ageYears = 12
          session.ageYears = 9
        default:
          session.resetSetup()
          XCTAssertFalse(session.localProcessingEnabled)
          session.localProcessingEnabled = true
        }
        session.retry()
        session.prepare()
        await session.startRecording()
        XCTAssertEqual(session.attemptLedger.totalStarted, 2)
        XCTAssertEqual(session.attemptLedger.totalTerminal, 2)
        XCTAssertNil(session.attemptLedger.rows.last?.previousAttemptId)
        XCTAssertEqual(session.attemptLedger.rows.last?.retryIndex, 0)
        XCTAssertEqual(session.attemptLedger.rows.last?.startKind, .recordRequested)
        session.end()
        await session.startRecording()
        XCTAssertEqual(session.attemptLedger.totalStarted, 2)
      }
    }

    func testRowCapPreservesAllAttemptTotalsAndKeepsActiveAttempt() async throws {
      let capture = try AssessmentSessionCapturer()
      defer { capture.removeDirectory() }
      capture.permissionGranted = false
      let session = try configured(capture, AssessmentSessionProcessor())
      for _ in 0..<101 { await session.startRecording() }
      XCTAssertEqual(session.attemptLedger.totalStarted, 101)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 101)
      XCTAssertEqual(session.attemptLedger.rows.count, 100)
      XCTAssertEqual(session.attemptLedger.droppedRowCount, 1)
      XCTAssertEqual(session.attemptLedger.reasonCounts[.permissionDenied], 101)
      XCTAssertEqual(session.attemptLedger.outcomeCounts[.unavailable], 101)
      let previous = try XCTUnwrap(session.attemptLedger.rows.last?.id)
      capture.permissionGranted = true
      await session.startRecording()
      XCTAssertEqual(session.phase, .recording)
      XCTAssertEqual(session.attemptLedger.totalStarted, 102)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 101)
      XCTAssertEqual(session.attemptLedger.rows.count, 100)
      XCTAssertEqual(session.attemptLedger.droppedRowCount, 2)
      XCTAssertEqual(session.attemptLedger.rows.last?.previousAttemptId, previous)
      XCTAssertEqual(session.attemptLedger.rows.last?.retryIndex, 101)
      XCTAssertNil(session.attemptLedger.rows.last?.terminalReason)
      XCTAssertNil(session.attemptLedger.rows.last?.elapsedSeconds)
      session.end()
      session.end()
      session.appDidEnterBackground()
      XCTAssertEqual(session.attemptLedger.totalStarted, 102)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 102)
      XCTAssertEqual(session.attemptLedger.reasonCounts[.permissionDenied], 101)
      XCTAssertEqual(session.attemptLedger.reasonCounts[.sessionEnded], 1)
      XCTAssertEqual(session.attemptLedger.outcomeCounts[.unavailable], 102)
      XCTAssertEqual(session.attemptLedger.rows.count, 100)
      XCTAssertEqual(session.attemptLedger.droppedRowCount, 2)
      XCTAssertFalse(capture.fileExists)
    }

    private func assertTerminal(
      _ session: ResearchAssessmentSession, reason: ResearchAssessmentTerminalReason,
      outcome: ResearchAssessmentTerminalOutcome = .unavailable,
      file: StaticString = #filePath, line: UInt = #line
    ) {
      XCTAssertEqual(session.attemptLedger.totalStarted, 1, file: file, line: line)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1, file: file, line: line)
      XCTAssertEqual(session.attemptLedger.reasonCounts[reason], 1, file: file, line: line)
      XCTAssertEqual(session.attemptLedger.outcomeCounts[outcome], 1, file: file, line: line)
      let row = session.attemptLedger.rows.first
      XCTAssertEqual(row?.terminalReason, reason, file: file, line: line)
      XCTAssertEqual(row?.terminalOutcome, outcome, file: file, line: line)
      XCTAssertEqual(row?.learnerFindingEligible, false, file: file, line: line)
      XCTAssertGreaterThanOrEqual(row?.elapsedSeconds ?? -1, 0, file: file, line: line)
    }

    private func entry(_ id: String) throws -> PracticeLibraryEntry {
      try XCTUnwrap(PracticeLibrary.entries().first { $0.id == id })
    }
    private func configured(
      _ fixture: ConsumerCaptureFixture, _ processor: AssessmentSessionProcessor
    ) throws -> ResearchAssessmentSession {
      let session = ResearchAssessmentSession(
        capturer: fixture.capture, processor: processor,
        hardwareOwnership: fixture.hardware, fileOwnership: fixture.files)
      session.ageYears = 9
      session.selectedEntry = try entry("r-beginning-rabbit")
      session.localProcessingEnabled = true
      session.prepare()
      return session
    }
    private func configured(
      _ capture: AssessmentSessionCapturer, _ processor: AssessmentSessionProcessor, age: Int = 9
    ) throws -> ResearchAssessmentSession {
      let session = ResearchAssessmentSession(
        capturer: capture, processor: processor, hardwareOwnership: AudioHardwareOwnership(),
        fileOwnership: ProcessAudioFileOwnership())
      session.ageYears = age
      session.selectedEntry = try entry("r-beginning-rabbit")
      session.localProcessingEnabled = true
      session.prepare()
      return session
    }
    private func assertUnavailable(
      _ session: ResearchAssessmentSession, file: StaticString = #filePath, line: UInt = #line
    ) {
      guard case .unavailable = session.phase else {
        return XCTFail(
          "Expected an unavailable result, got \(session.phase)", file: file, line: line)
      }
    }
    private func wait(
      _ condition: @MainActor () -> Bool, file: StaticString = #filePath, line: UInt = #line
    ) async {
      await waitForConsumerState(condition, file: file, line: line)
    }
  }

  @MainActor
  private final class AssessmentSessionCapturer: AudioCapturing {
    private var fixtureOwners: [URL: UUID] = [:]
    private var pendingFixtureCleanup: [UUID: URL] = [:]
    private var completedFixtureCleanup: [UUID: CaptureCleanupReceipt] = [:]
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      completedFixtureCleanup[operationID]
    }
    private let cleanupSubject = CurrentValueSubject<CaptureCleanupState, Never>(.idle)
    var cleanupState: CaptureCleanupState { cleanupSubject.value }
    /// Initial delivery and mutations are synchronous; subscribe on MainActor.
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      cleanupSubject.eraseToAnyPublisher()
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      guard let url = pendingFixtureCleanup[operationID] else {
        return .init(operationID: operationID, result: .refused)
      }
      if failDiscard || failCancel {
        return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
      }
      do {
        try removeOwnedFixtureFile(url)
        return .init(operationID: operationID, result: .released)
      } catch {
        return .init(operationID: operationID, result: .hardwareReleasedFilesRetained)
      }
    }
    private func retainFixtureFile(_ url: URL) { fixtureOwners[url] = UUID() }
    private func markFixtureCleanup(_ url: URL) {
      guard let owner = fixtureOwners[url] else { return }
      pendingFixtureCleanup[owner] = url
      publishFixtureCleanup()
    }
    private func publishFixtureCleanup() {
      let state = CaptureCleanupState(
        hardwareBlockedOperationID: nil, fileBlockedOwnerIDs: Set(pendingFixtureCleanup.keys))
      if cleanupSubject.value != state { cleanupSubject.send(state) }
    }
    private func removeOwnedFixtureFile(_ url: URL) throws {
      guard let owner = fixtureOwners[url] else { throw AudioCaptureError.recordingNotOwned }
      do {
        if FileManager.default.fileExists(atPath: url.path) {
          try FileManager.default.removeItem(at: url)
        }
        fixtureOwners.removeValue(forKey: url)
        pendingFixtureCleanup.removeValue(forKey: owner)
        completedFixtureCleanup[owner] = .init(operationID: owner, result: .released)
        publishFixtureCleanup()
      } catch {
        markFixtureCleanup(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
    }

    let directory: URL
    let url: URL
    var summary = CaptureSummary(duration: 1, averagePower: -20)
    var permissionGranted = true
    var holdsPermission = false
    var failStart = false
    var failStop = false
    var failDiscard = false
    var failCancel = false
    private(set) var permissionRequests = 0
    private(set) var startCount = 0
    private(set) var stopCount = 0
    private(set) var discardCount = 0
    private var active = false
    private var permission: CheckedContinuation<Bool, Never>?
    private var callbacks: [@MainActor (Bool) async -> Void] = []
    var permissionPending: Bool { permission != nil }
    var fileExists: Bool { FileManager.default.fileExists(atPath: url.path) }
    init() throws {
      directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      url = directory.appendingPathComponent("attempt.wav")
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }
    func requestPermission() async -> Bool {
      permissionRequests += 1
      if holdsPermission { return await withCheckedContinuation { permission = $0 } }
      return permissionGranted
    }
    func resolvePermission(_ granted: Bool) {
      permission?.resume(returning: granted)
      permission = nil
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      guard pendingFixtureCleanup.isEmpty else {
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      startCount += 1
      active = true
      retainFixtureFile(url)
      do {
        try Data("temporary audio".utf8).write(to: url)
      } catch {
        active = false
        markFixtureCleanup(url)
        throw error
      }
      if failStart { throw AudioCaptureError.couldNotStart }
      callbacks.append(onFinish)
    }
    func stop() throws -> CapturedRecording {
      stopCount += 1
      if failStop { throw AudioCaptureError.couldNotReadRecording }
      active = false
      return CapturedRecording(url: url, summary: summary, cleanupOwnerID: fixtureOwners[url])
    }
    func cancel() throws {
      if failCancel {
        active = false
        markFixtureCleanup(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      let wasActive = active
      active = false
      if wasActive { try removeOwnedFixtureFile(url) }
    }
    func discard(_ recording: CapturedRecording) throws {
      guard let owner = fixtureOwners[recording.url] else {
        throw AudioCaptureError.recordingNotOwned
      }
      guard pendingFixtureCleanup[owner] == nil else {
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      discardCount += 1
      if failDiscard {
        markFixtureCleanup(recording.url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      try removeOwnedFixtureFile(recording.url)
    }
    func finish(index: Int, successfully: Bool = true) async {
      await callbacks[index](successfully)
    }
    func removeDirectory() { try? FileManager.default.removeItem(at: directory) }
  }

  @MainActor
  private final class AssessmentSessionProcessor: ResearchAssessmentProcessing {
    struct Call {
      let attemptId: UUID
      let recording: CapturedRecording
      let entry: PracticeLibraryEntry
      let age: Int
    }
    private(set) var calls: [Call] = []
    var result: Result<ResearchAssessmentOutcome, Error> = .success(
      .processedUnverified(milliseconds: 12))
    var holdsCompletion = false
    private(set) var returnedCount = 0
    private(set) var cancelledAtReturn = false
    private var continuation: CheckedContinuation<ResearchAssessmentOutcome, Error>?
    var pending: Bool { continuation != nil }
    func process(
      attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
    )
      async throws -> ResearchAssessmentOutcome
    {
      calls.append(Call(attemptId: attemptId, recording: recording, entry: entry, age: ageYears))
      if holdsCompletion {
        defer {
          cancelledAtReturn = Task.isCancelled
          returnedCount += 1
        }
        return try await withCheckedThrowingContinuation { continuation = $0 }
      }
      returnedCount += 1
      return try result.get()
    }
    func resolve(_ result: Result<ResearchAssessmentOutcome, Error>) {
      continuation?.resume(with: result)
      continuation = nil
    }
  }
#endif
