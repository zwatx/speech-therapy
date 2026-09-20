#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class LocalGuidedPracticeHandoffTests: XCTestCase {
    func testGeneratedCaptureCleanupSubscriptionCanCancelOffMainActor() async {
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      let producer = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
      var values: [CaptureCleanupState] = []
      let box = OffMainCaptureCancellation(producer.cleanupStatePublisher.sink { values.append($0) })
      XCTAssertEqual(values, [.idle], "The actual producer must seed idle synchronously.")
      XCTAssertFalse(FileManager.default.fileExists(atPath: producer.directory.path))

      let cancelledOnMainThread = await Task.detached {
        box.cancel()
      }.value

      XCTAssertFalse(cancelledOnMainThread)
      withExtendedLifetime(producer) {
        XCTAssertEqual(values, [.idle], "Cancellation must not publish another cleanup state.")
        XCTAssertEqual(producer.cleanupState, .idle)
        XCTAssertEqual(producer.retainedFileCount, 0)
        XCTAssertNil(hardware.currentLease)
        XCTAssertTrue(files.protectedURLs.isEmpty)
        XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: producer.directory.path))
      }
    }

    private let custom = [
      "b-beginning-baby", "k-middle-backpack", "r-middle-bread",
      "d-beginning-door", "s-beginning-sky",
    ]

    private func complete(
      _ fixture: HandoffFixture, checked: Bool = false, entryIDs: [String]? = nil
    ) async throws {
      let ids = entryIDs ?? custom
      XCTAssertTrue(fixture.session.configureSetup(entryIDs: ids))
      await fixture.session.startInitialReview()
      if checked {
        for _ in 0..<5 {
          await fixture.media.startRecording()
          fixture.media.stopRecording()
          await fixture.session.checkCurrentWord()
          await fixture.session.advanceVisit()
        }
      } else {
        await fixture.session.finishStageNow()
      }
      fixture.session.togglePracticeSelection(entryID: ids[0])
      await fixture.session.startPractice()
      await fixture.session.skipVisit()
      await fixture.session.startRecheck()
      if checked {
        for _ in 0..<5 {
          await fixture.media.startRecording()
          fixture.media.stopRecording()
          await fixture.session.checkCurrentWord()
          await fixture.session.advanceVisit()
        }
      } else {
        await fixture.session.finishStageNow()
      }
      XCTAssertEqual(fixture.session.ledger?.stage, .completed)
      XCTAssertEqual(fixture.capture.retainedCount, 0)
    }

    func testEveryCompletedWordDispositionAdmitsEveryCanonicalPairedTarget() async throws {
      let statuses: [LocalWordRecognitionStatus] = [
        .matched, .notMatched, .uncertain, .timedOut, .unavailable, .cancelled,
      ]
      var observations = Set<String>()
      for status in statuses {
        let f = fixture(status: status)
        try await complete(f, checked: true)
        let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
        for row in try XCTUnwrap(f.session.ledger).pairedRows {
          if case .finished(let disposition) = row.initial.state {
            observations.insert(disposition.wordObservation)
          }
          XCTAssertTrue(f.session.canPracticeIndependently(entryID: row.entry.id, summary: summary))
        }
        let closed = await f.session.close()
        XCTAssertTrue(closed)
      }
      let skipped = fixture()
      try await complete(skipped)
      let summary = try XCTUnwrap(skipped.session.completedSummaryIdentity)
      for row in try XCTUnwrap(skipped.session.ledger).pairedRows {
        if case .finished(let disposition) = row.initial.state {
          observations.insert(disposition.wordObservation)
        }
        XCTAssertTrue(skipped.session.canPracticeIndependently(entryID: row.entry.id, summary: summary))
      }
      XCTAssertEqual(observations.count, 8, "Include skipped and unreached, without result filtering.")
      let closed = await skipped.session.close()
      XCTAssertTrue(closed)
    }

    func testHandoffContainsOnlyExactSingleCanonicalTargetAndIsConsumedOnce() async throws {
      for entryID in ["b-beginning-bread", "r-middle-bread"] {
        let f = fixture()
        var ids = custom
        ids[2] = entryID
        try await complete(f, entryIDs: ids)
        let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
        let permissions = f.capture.permissionRequests
        let files = f.capture.createdURLs
        let checks = f.recognizer.base.requests
        let history = f.history.entries
        await f.session.practiceIndependently(entryID: entryID, summary: summary)
        XCTAssertTrue(f.session.isClosed)
        XCTAssertTrue(f.media.hasFullyEndedCleanup)
        let handoff = try XCTUnwrap(f.session.consumeSummaryHandoff())
        XCTAssertEqual(handoff.summary, summary)
        guard case .independentPractice(let entry, let sound) = handoff.destination else {
          XCTFail("Expected independent practice")
          return
        }
        XCTAssertEqual(entry.id, entryID)
        XCTAssertEqual(sound.prompts, [entry.prompt])
        XCTAssertEqual(handoff.canonicalSound, sound)
        if entryID == custom[2] {
          XCTAssertEqual(sound.id, "r")
          XCTAssertEqual(sound.position, .middle)
          XCTAssertEqual(sound.prompts.first?.word, "bread")
          XCTAssertNotEqual(sound.id, "b")
        } else {
          XCTAssertEqual(sound.id, "b")
          XCTAssertEqual(sound.position, .beginning)
          XCTAssertEqual(sound.prompts.first?.word, "bread")
        }
        XCTAssertNil(f.session.consumeSummaryHandoff())
        await f.session.practiceIndependently(entryID: entryID, summary: summary)
        XCTAssertNil(f.session.consumeSummaryHandoff())
        XCTAssertEqual(f.capture.permissionRequests, permissions)
        XCTAssertEqual(f.capture.createdURLs, files)
        XCTAssertEqual(f.recognizer.base.requests, checks)
        XCTAssertEqual(f.history.entries, history)
        XCTAssertEqual(f.media.playbackState, .idle)
      }
    }

    func testPracticeParticipationDispositionsDoNotFilterIndependentActions() async throws {
      for failingHistory in [false, true] {
        let f = fixture(failingHistory: failingHistory)
        XCTAssertTrue(f.session.configureSetup(entryIDs: custom))
        await f.session.startInitialReview()
        await f.session.finishStageNow()
        for id in custom.prefix(3) { f.session.togglePracticeSelection(entryID: id) }
        await f.session.startPractice()
        await f.media.startRecording()
        f.media.stopRecording()
        await f.session.advanceVisit()
        if failingHistory { await f.session.advanceVisit() }
        await f.session.finishStageNow()
        await f.session.startRecheck()
        await f.session.finishStageNow()
        let ledger = try XCTUnwrap(f.session.ledger)
        let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
        XCTAssertEqual(ledger.practiceRows.map(\.state), [
          .finished(failingHistory ? .saveUnconfirmed : .finished),
          .finished(.skipped), .finished(.unreached),
        ])
        XCTAssertNil(ledger.pairedRows.last?.practice)
        for row in ledger.pairedRows {
          XCTAssertTrue(f.session.canPracticeIndependently(entryID: row.entry.id, summary: summary))
        }
        let closed = await f.session.close()
        XCTAssertTrue(closed)
      }
    }

    func testSetupUnfinishedWrongWorkflowMissingEntryAndStaleCompletedRoundsReject() async throws {
      let f = fixture()
      let invented = LocalGuidedCompletedSummaryIdentity(
        workflowID: UUID(), initialRoundID: UUID(), recheckRoundID: UUID())
      await f.session.practiceIndependently(entryID: custom[0], summary: invented)
      XCTAssertNil(f.session.ledger)
      XCTAssertFalse(f.session.isClosed)
      try await complete(f)
      let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
      let wrong = LocalGuidedCompletedSummaryIdentity(workflowID: UUID(),
        initialRoundID: summary.initialRoundID, recheckRoundID: summary.recheckRoundID)
      await f.session.practiceIndependently(entryID: custom[0], summary: wrong)
      await f.session.practiceIndependently(entryID: "b-beginning-bread", summary: summary)
      XCTAssertFalse(f.session.isClosed)
      await f.session.repeatReview()
      XCTAssertEqual(f.session.ledger?.workflowID, summary.workflowID)
      await f.session.practiceIndependently(entryID: custom[0], summary: summary)
      XCTAssertEqual(f.session.ledger?.stage, .initialReview)
      await f.session.finishStageNow()
      f.session.togglePracticeSelection(entryID: custom[0])
      await f.session.startPractice()
      await f.session.skipVisit()
      await f.session.startRecheck()
      await f.session.finishStageNow()
      let fresh = try XCTUnwrap(f.session.completedSummaryIdentity)
      XCTAssertNotEqual(fresh.initialRoundID, summary.initialRoundID)
      XCTAssertNotEqual(fresh.recheckRoundID, summary.recheckRoundID)
      await f.session.practiceIndependently(entryID: custom[0], summary: summary)
      XCTAssertFalse(f.session.isClosed)
      XCTAssertTrue(f.session.canPracticeIndependently(entryID: custom[0], summary: fresh))
      XCTAssertEqual(f.capture.permissionRequests, 0)
      let closed = await f.session.close()
      XCTAssertTrue(closed)
    }

    func testHeldRuntimeCleanupBlocksRouteAndDuplicateTapUntilExactRelease() async throws {
      let f = fixture()
      try await complete(f)
      let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
      f.recognizer.holdsRelease = true
      let first = Task { await f.session.practiceIndependently(entryID: custom[2], summary: summary) }
      await waitForRelease(f)
      await f.session.practiceIndependently(entryID: custom[0], summary: summary)
      XCTAssertFalse(f.session.isClosed)
      XCTAssertFalse(f.media.hasFullyEndedCleanup)
      XCTAssertNil(f.session.consumeSummaryHandoff())
      f.recognizer.finishRelease()
      await first.value
      XCTAssertEqual(f.recognizer.releaseCalls, 1)
      XCTAssertEqual(f.session.consumeSummaryHandoff()?.canonicalSound?.prompts.first?.id, custom[2])
      XCTAssertNil(f.session.consumeSummaryHandoff())
      XCTAssertEqual(f.capture.permissionRequests, 0)
      XCTAssertTrue(f.history.entries.isEmpty)
    }

    func testFailedCleanupRecoveryKeepsSummaryAndRequiresFreshPracticeTap() async throws {
      let f = fixture()
      try await complete(f)
      let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
      let borrow = try await retainBorrowedTake(f)
      await f.session.practiceIndependently(entryID: custom[2], summary: summary)
      XCTAssertFalse(f.session.isClosed)
      XCTAssertEqual(f.session.completedSummaryIdentity, summary)
      XCTAssertNil(f.session.consumeSummaryHandoff())
      XCTAssertEqual(f.session.statusNote,
        "Practice hasn’t opened. Retry cleanup, then tap Practice again.")
      f.files.finishBorrowing(operation: borrow)
      await f.media.retryCleanup()
      XCTAssertTrue(f.media.hasFullyEndedCleanup)
      XCTAssertFalse(f.session.isClosed)
      XCTAssertNil(f.session.consumeSummaryHandoff())
      XCTAssertEqual(f.session.statusNote, "Cleanup finished. Practice hasn’t opened. Tap Practice again.")
      await f.session.practiceIndependently(entryID: custom[2], summary: summary)
      XCTAssertEqual(f.session.consumeSummaryHandoff()?.canonicalSound?.prompts.first?.id, custom[2])
      XCTAssertNil(f.session.consumeSummaryHandoff())
      XCTAssertEqual(f.capture.permissionRequests, 1)
      XCTAssertTrue(f.recognizer.base.requests.isEmpty)
      XCTAssertTrue(f.history.entries.isEmpty)
    }

    func testFileOnlySecondCloseEscapeCannotAuthorizePractice() async throws {
      let f = fixture()
      try await complete(f)
      let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
      let borrow = try await retainBorrowedTake(f)
      await f.session.practiceIndependently(entryID: custom[2], summary: summary)
      await f.session.practiceIndependently(entryID: custom[2], summary: summary)
      XCTAssertEqual(f.media.phase, .ended, "The ordinary end API allows process-held file recovery.")
      XCTAssertFalse(f.media.hasFullyEndedCleanup)
      XCTAssertFalse(f.session.isClosed)
      XCTAssertNil(f.session.consumeSummaryHandoff())
      XCTAssertEqual(f.session.completedSummaryIdentity, summary)
      f.files.finishBorrowing(operation: borrow)
      await f.media.retryCleanup()
      let closed = await f.session.close()
      XCTAssertTrue(closed)
      XCTAssertEqual(f.capture.retainedCount, 0)
    }

    func testExceptionalRepeatAfterRecoveredHandoffUsesFreshOwnerAndSameFiveWithoutMedia() async throws {
      for fileOnlyEscape in [false, true] {
        let f = fixture()
        try await complete(f)
        let old = try XCTUnwrap(f.session.completedSummaryIdentity)
        let borrow = try await retainBorrowedTake(f)
        await f.session.practiceIndependently(entryID: custom[2], summary: old)
        XCTAssertNil(f.session.consumeSummaryHandoff())
        if fileOnlyEscape {
          await f.session.practiceIndependently(entryID: custom[2], summary: old)
          XCTAssertEqual(f.media.phase, .ended)
          XCTAssertFalse(f.media.hasFullyEndedCleanup)
        }
        f.files.finishBorrowing(operation: borrow)
        await f.media.retryCleanup()
        XCTAssertTrue(f.session.repeatRequiresSummaryDeparture)
        XCTAssertFalse(f.session.isClosed)
        XCTAssertNil(f.session.consumeSummaryHandoff(), "Recovery alone must not launch a review.")
        let permissions = f.capture.permissionRequests
        let files = f.capture.createdURLs
        await f.session.repeatReview()
        let handoff = try XCTUnwrap(f.session.consumeSummaryHandoff())
        XCTAssertEqual(handoff.summary, old)
        XCTAssertEqual(handoff.canonicalRepeatEntryIDs, custom)
        XCTAssertNil(handoff.canonicalSound)
        XCTAssertNil(f.session.consumeSummaryHandoff())
        XCTAssertEqual(f.media.phase, .ended, "Never resurrect the released mirror/media owner.")
        XCTAssertEqual(f.capture.permissionRequests, permissions)
        XCTAssertEqual(f.capture.createdURLs, files)

        let fresh = fixture()
        XCTAssertTrue(fresh.session.configureSetup(entryIDs: try XCTUnwrap(handoff.canonicalRepeatEntryIDs)))
        await fresh.session.startInitialReview()
        let ledger = try XCTUnwrap(fresh.session.ledger)
        XCTAssertNotEqual(ledger.workflowID, old.workflowID)
        XCTAssertNotEqual(ledger.initialRound.id, old.initialRoundID)
        XCTAssertEqual(ledger.entries.map(\.id), custom)
        XCTAssertEqual(ledger.stage, .initialReview)
        XCTAssertNil(ledger.recheckRound)
        XCTAssertTrue(ledger.initialRound.rows.allSatisfy { $0.firstSubmission == nil })
        XCTAssertTrue(ledger.practiceRows.isEmpty)
        XCTAssertEqual(fresh.capture.permissionRequests, 0)
        XCTAssertTrue(fresh.capture.createdURLs.isEmpty)
        XCTAssertTrue(fresh.recognizer.base.requests.isEmpty)
        XCTAssertTrue(fresh.history.entries.isEmpty)
      }
    }

    func testHealthyRepeatRetainsExistingOwnerAndDoesNotStageSummaryDeparture() async throws {
      let f = fixture()
      try await complete(f)
      let old = try XCTUnwrap(f.session.completedSummaryIdentity)
      let media = f.media
      XCTAssertFalse(f.session.repeatRequiresSummaryDeparture)
      await f.session.repeatReview()
      XCTAssertTrue(f.session.media === media)
      XCTAssertEqual(f.session.ledger?.workflowID, old.workflowID)
      XCTAssertEqual(f.session.ledger?.stage, .initialReview)
      XCTAssertFalse(f.session.isClosed)
      XCTAssertNil(f.session.consumeSummaryHandoff())
      XCTAssertEqual(f.capture.permissionRequests, 0)
    }

    func testCloseWinsWhileHandoffCleanupIsHeldWithoutLatePractice() async throws {
      let f = fixture()
      try await complete(f)
      let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
      f.recognizer.holdsRelease = true
      let handoff = Task { await f.session.practiceIndependently(entryID: custom[2], summary: summary) }
      await waitForRelease(f)
      var startedClose = false
      let close = Task { startedClose = true; return await f.session.close() }
      for _ in 0..<512 where !startedClose { await Task.yield() }
      XCTAssertTrue(startedClose)
      f.recognizer.finishRelease()
      await handoff.value
      let closed = await close.value
      XCTAssertTrue(closed)
      XCTAssertTrue(f.session.isClosed)
      XCTAssertNil(f.session.consumeSummaryHandoff())
    }

    func testLifecycleAndTaskCancellationWhileHeldNeverAuthorizeLateHandoff() async throws {
      for point in 0..<4 {
        let f = fixture()
        try await complete(f)
        let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
        f.recognizer.holdsRelease = true
        let action = Task { await f.session.practiceIndependently(entryID: custom[2], summary: summary) }
        await waitForRelease(f)
        switch point {
        case 0: f.session.background()
        case 1: f.session.interrupted()
        case 2: f.session.disappeared()
        default: action.cancel()
        }
        f.recognizer.finishRelease()
        await action.value
        XCTAssertFalse(f.session.isClosed)
        XCTAssertNil(f.session.consumeSummaryHandoff())
        XCTAssertEqual(f.session.completedSummaryIdentity, summary)
        let closed = await f.session.close()
        XCTAssertTrue(closed)
      }
    }

    func testReentrantClosedPublicationCannotConsumeOrLateAuthorizeRevokedHandoff() async throws {
      for cancelTask in [false, true] {
        let f = fixture()
        try await complete(f)
        let summary = try XCTUnwrap(f.session.completedSummaryIdentity)
        var fired = false
        var action: Task<Void, Never>?
        let subscription = f.session.$isClosed.sink { closing in
          guard closing, !fired else { return }
          fired = true
          XCTAssertNil(f.session.consumeSummaryHandoff(), "willSet is not actual closure.")
          if cancelTask { action?.cancel() } else { f.session.background() }
        }
        action = Task { await f.session.practiceIndependently(entryID: custom[2], summary: summary) }
        await action?.value
        subscription.cancel()
        XCTAssertTrue(fired)
        XCTAssertFalse(f.session.isClosed)
        XCTAssertNil(f.session.consumeSummaryHandoff())
        XCTAssertEqual(f.session.completedSummaryIdentity, summary)
        let closed = await f.session.close()
        XCTAssertTrue(closed)
      }
    }

    private func waitForRelease(_ f: HandoffFixture) async {
      for _ in 0..<512 where !f.recognizer.releasePending { await Task.yield() }
      let pending = f.recognizer.releasePending
      if !pending { f.recognizer.holdsRelease = false }
      XCTAssertTrue(pending)
    }

    private func retainBorrowedTake(_ f: HandoffFixture) async throws -> UUID {
      let ledger = try XCTUnwrap(f.session.ledger)
      let entry = ledger.entries[0]
      let visit = LocalGuidedReviewVisit(workflowID: ledger.workflowID, roundID: UUID(),
        visitID: UUID(), entryID: entry.id)
      let prepared = await f.media.prepareGuidedVisit(entry: entry, visit: .review(visit))
      XCTAssertTrue(prepared)
      await f.media.startRecording()
      f.media.stopRecording()
      let url = try XCTUnwrap(f.capture.returnedURLs.last)
      let borrow = UUID()
      XCTAssertTrue(f.borrow(url, operation: borrow))
      return borrow
    }

    private func fixture(
      status: LocalWordRecognitionStatus = .matched, failingHistory: Bool = false
    ) -> HandoffFixture {
      let f = HandoffFixture(status: status, failingHistory: failingHistory)
      addTeardownBlock { @MainActor in await f.cleanup() }
      return f
    }
  }

  /// Only the cancellation token crosses actors; its one-shot transfer is lock-protected.
  private final class OffMainCaptureCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private var token: AnyCancellable?

    init(_ token: AnyCancellable) { self.token = token }

    nonisolated func cancel() -> Bool {
      let taken = lock.withLock {
        let taken = token
        token = nil
        return taken
      }
      taken?.cancel()
      return Thread.isMainThread
    }
  }

  @MainActor
  private final class HandoffFixture {
    let files = ProcessAudioFileOwnership()
    let hardware = AudioHardwareOwnership()
    let capture: LocalGuidedGeneratedCapture
    let recognizer: HandoffRecognizer
    let history: PracticeParticipationStore
    let media: DirectPracticeSession
    let session: LocalGuidedReviewSession
    private let historyDirectory: URL
    private var borrows: Set<UUID> = []

    init(status: LocalWordRecognitionStatus = .matched, failingHistory: Bool = false) {
      capture = LocalGuidedGeneratedCapture(hardware: hardware, files: files)
      recognizer = HandoffRecognizer(files: files, status: status)
      let player = ResearchAcknowledgedPlaybackUITestFixture(
        completion: .explicitStop, ownership: hardware, fileOwnership: files)
      let recovery = ProcessPracticeMirrorRecovery()
      let runtime = PracticeMirrorRuntime(recovery: recovery) { _ in HandoffInertMirrorDriver() }
      let mirror = DirectPracticeMirror(
        permission: HandoffUnsupportedMirrorPermission(), runtime: runtime, recovery: recovery)
      historyDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-practice-handoff-\(UUID())", isDirectory: true)
      if failingHistory {
        // A fixture-owned directory at the store's file path forces its real save failure.
        do {
          try FileManager.default.createDirectory(
            at: historyDirectory.appendingPathComponent("history.json"), withIntermediateDirectories: true)
        } catch { XCTFail("Could not prepare the isolated history failure: \(error)") }
      }
      history = PracticeParticipationStore(fileURL: historyDirectory.appendingPathComponent("history.json"))
      media = DirectPracticeSession(capturer: capture, player: player, mirror: mirror,
        history: history, managedForGuided: true, wordRecognizer: recognizer,
        cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
      session = LocalGuidedReviewSession(history: history, media: media)
    }

    func borrow(_ url: URL, operation: UUID) -> Bool {
      guard files.borrow(url, operation: operation) else { return false }
      borrows.insert(operation)
      return true
    }

    func cleanup() async {
      recognizer.holdsRelease = false
      recognizer.finishRelease()
      for borrow in borrows { files.finishBorrowing(operation: borrow) }
      for _ in 0..<2 {
        if media.canRetryCleanup { await media.retryCleanup() }
        _ = await session.close()
      }
      XCTAssertNil(hardware.currentLease)
      XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
      XCTAssertTrue(files.protectedURLs.isEmpty)
      XCTAssertEqual(capture.retainedCount, 0)
      for directory in Set(capture.createdURLs.map { $0.deletingLastPathComponent() }) {
        try? FileManager.default.removeItem(at: directory)
      }
      try? FileManager.default.removeItem(at: historyDirectory)
    }
  }

  @MainActor
  private final class HandoffRecognizer: LocalWordRecognizing, LocalWordRuntimeReleasing {
    let base: LocalGuidedGeneratedRecognizer
    var holdsRelease = false
    private var release: CheckedContinuation<Bool, Never>?
    private(set) var releaseCalls = 0
    var releasePending: Bool { release != nil }

    init(files: ProcessAudioFileOwnership, status: LocalWordRecognitionStatus) {
      base = LocalGuidedGeneratedRecognizer(files: files, holdsResult: false, returnedStatus: status)
    }
    func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
      await base.check(request: request)
    }
    func cancel(operationID: UUID) { base.cancel(operationID: operationID) }
    func releaseWordRuntime() async -> Bool {
      releaseCalls += 1
      guard holdsRelease else { return true }
      return await withCheckedContinuation { release = $0 }
    }
    func finishRelease() {
      let pending = release
      release = nil
      pending?.resume(returning: true)
    }
  }

  @MainActor
  private final class HandoffUnsupportedMirrorPermission: PracticeMirrorPermissionProviding {
    var isSupported: Bool { false }
    var status: PracticeMirrorPermission { .denied }
    func requestPermission(completion: @escaping @MainActor (Bool) -> Void) { completion(false) }
  }

  private final class HandoffInertMirrorDriver: PracticeMirrorDriver, @unchecked Sendable {
    private enum Unavailable: Error { case generated }
    func configure() throws { throw Unavailable.generated }
    func start() throws { throw Unavailable.generated }
    var previewSource: PracticeMirrorPreviewSource? { nil }
    func stopAndReleasePreviewResources() throws {}
  }
#endif
