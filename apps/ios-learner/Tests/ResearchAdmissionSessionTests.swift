#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchAdmissionSessionTests: XCTestCase {
    func testAdmittedProcessingDeletesAudioAndStoresOnlyInternalTerminal() async throws {
      let capture = AdmissionCapturer()
      defer { capture.remove() }
      let processor = AdmissionProcessor()
      let session = configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      processor.resolve(.admissionProcessed(milliseconds: 1200))
      await wait { session.phase != .processing }
      guard case .unavailable(let title, let detail) = session.phase else {
        return XCTFail("Expected unavailable finding")
      }
      XCTAssertEqual(title, "No result to show")
      XCTAssertTrue(detail.contains("It produced no pronunciation finding."))
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
      XCTAssertEqual(session.attemptLedger.totalStarted, 1)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalOutcome, .admissionProcessed)
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalReason, .admissionProcessed)
      XCTAssertEqual(session.attemptLedger.rows.last?.learnerFindingEligible, false)
    }

    func testWordRejectionIsUnavailableAndRetryLinksOneDenominator() async throws {
      let capture = AdmissionCapturer()
      defer { capture.remove() }
      let processor = AdmissionProcessor()
      let session = configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      processor.resolve(.unavailable(reason: "requested_word_not_matched"))
      await wait { session.phase != .processing }
      guard case .unavailable(_, let detail) = session.phase else {
        return XCTFail("Expected unavailable")
      }
      XCTAssertTrue(detail.contains("This does not indicate a pronunciation problem."))
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalReason, .admissionRejected)
      let parent = session.attemptLedger.rows.last?.id
      session.retry()
      await session.startRecording()
      XCTAssertEqual(session.attemptLedger.totalStarted, 2)
      XCTAssertEqual(session.attemptLedger.rows.last?.previousAttemptId, parent)
      session.end()
      XCTAssertEqual(session.attemptLedger.totalTerminal, 2)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
    }

    func testCancelledAdmissionCannotReviveAttemptWithLateResult() async throws {
      let capture = AdmissionCapturer()
      defer { capture.remove() }
      let processor = AdmissionProcessor()
      let session = configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      session.cancelProcessing()
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalReason, .cancelled)
      processor.resolve(.admissionProcessed(milliseconds: 1200))
      await wait { processor.returned }
      XCTAssertEqual(session.phase, .ready)
      XCTAssertEqual(session.attemptLedger.totalTerminal, 1)
      XCTAssertFalse(FileManager.default.fileExists(atPath: capture.url.path))
    }

    func testFailedClientCleanupCannotClaimDeletedRecordingOrAdmission() async throws {
      let capture = AdmissionCapturer()
      defer { capture.remove() }
      let processor = AdmissionProcessor()
      let session = configured(capture, processor)
      await session.startRecording()
      session.stopRecording()
      await wait { processor.pending }
      capture.failDiscard = true
      processor.resolve(.admissionProcessed(milliseconds: 1200))
      await wait { session.phase != .processing }
      XCTAssertEqual(session.phase, .cleanupBlocked)
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalReason, .cleanupBlocked)
      XCTAssertEqual(session.attemptLedger.rows.last?.terminalOutcome, .unavailable)
      XCTAssertTrue(FileManager.default.fileExists(atPath: capture.url.path))
      let starts = capture.starts
      await session.startRecording()
      XCTAssertEqual(capture.starts, starts)
    }

    private func configured(_ capture: AdmissionCapturer, _ processor: AdmissionProcessor)
      -> ResearchAssessmentSession
    {
      let session = ResearchAssessmentSession(capturer: capture, processor: processor)
      session.ageYears = 9
      session.selectedEntry = PracticeLibrary.entries().first { $0.id == "n-middle-banana" }!
      session.localProcessingEnabled = true
      session.prepare()
      return session
    }
    private func wait(_ condition: @MainActor () -> Bool) async {
      for _ in 0..<1000 {
        if condition() { return }
        await Task.yield()
      }
      XCTFail("Expected state transition")
    }
  }

  @MainActor
  private final class AdmissionCapturer: AudioCapturing {
    private var fixtureOwners: [URL: UUID] = [:]
    private var pendingFixtureCleanup: [UUID: URL] = [:]
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
      if failDiscard {
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
        publishFixtureCleanup()
      } catch {
        markFixtureCleanup(url)
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
    }

    let url = FileManager.default.temporaryDirectory.appendingPathComponent(
      UUID().uuidString + ".wav")
    var active = false
    var failDiscard = false
    var starts = 0
    func requestPermission() async -> Bool { true }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      guard pendingFixtureCleanup.isEmpty else { throw AudioCaptureError.couldNotDeleteTemporaryRecording }
      starts += 1
      active = true
      retainFixtureFile(url)
      do {
        try Data("invented session bytes".utf8).write(to: url)
      } catch {
        active = false
        markFixtureCleanup(url)
        throw error
      }
    }
    func stop() throws -> CapturedRecording {
      active = false
      return .init(url: url, summary: .init(duration: 1, averagePower: -20))
    }
    func cancel() throws {
      let wasActive = active
      active = false
      if wasActive { try removeOwnedFixtureFile(url) }
    }
    func discard(_ recording: CapturedRecording) throws {
      guard let owner = fixtureOwners[recording.url] else { throw AudioCaptureError.recordingNotOwned }
      guard pendingFixtureCleanup[owner] == nil else {
        throw AudioCaptureError.couldNotDeleteTemporaryRecording
      }
      if failDiscard { markFixtureCleanup(recording.url); throw AudioCaptureError.couldNotDeleteTemporaryRecording }
      try removeOwnedFixtureFile(recording.url)
    }
    func remove() { try? FileManager.default.removeItem(at: url) }
  }

  @MainActor
  private final class AdmissionProcessor: ResearchAssessmentProcessing {
    var continuation: CheckedContinuation<ResearchAssessmentOutcome, Never>?
    var pending: Bool { continuation != nil }
    var returned = false
    func process(
      attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
    ) async throws -> ResearchAssessmentOutcome {
      defer { returned = true }
      return await withCheckedContinuation { continuation = $0 }
    }
    func resolve(_ result: ResearchAssessmentOutcome) {
      continuation?.resume(returning: result)
      continuation = nil
    }
  }
#endif
