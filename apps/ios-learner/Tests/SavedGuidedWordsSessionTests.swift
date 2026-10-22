#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor final class SavedGuidedWordsSessionTests: XCTestCase {
    private let ids = [
      "b-beginning-baby", "k-middle-backpack", "r-middle-bread", "d-beginning-door",
      "s-beginning-sky",
    ]
    private func assertInert(
      _ r: LocalGuidedGeneratedResources, file: StaticString = #filePath, line: UInt = #line
    ) {
      XCTAssertNil(r.session.ledger, file: file, line: line)
      XCTAssertEqual(r.capture.permissionRequests, 0, file: file, line: line)
      XCTAssertTrue(r.capture.createdURLs.isEmpty, file: file, line: line)
      XCTAssertTrue(r.recognizer.requests.isEmpty, file: file, line: line)
      XCTAssertTrue(r.history.entries.isEmpty, file: file, line: line)
    }
    func testInitializerSeedsOnceWithoutModelMediaHistoryOrImplicitRound() throws {
      for seed in [nil, ids, ["unknown"] + Array(ids.dropFirst())] as [[String]?] {
        let hardware = AudioHardwareOwnership()
        let files = ProcessAudioFileOwnership()
        let capture = LocalGuidedGeneratedCapture(hardware: hardware, files: files)
        let recognizer = LocalGuidedGeneratedRecognizer(files: files, holdsResult: false)
        let player = ResearchAcknowledgedPlaybackUITestFixture(
          completion: .explicitStop,
          ownership: hardware, fileOwnership: files)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
          "saved-seed-unit-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let history = PracticeParticipationStore(
          fileURL: directory.appendingPathComponent("history.json"))
        let media = DirectPracticeSession(
          capturer: capture, player: player, history: history,
          managedForGuided: true, wordRecognizer: recognizer,
          cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
        let session = LocalGuidedReviewSession(history: history, media: media, setupEntryIDs: seed)
        XCTAssertEqual(session.setupSeedFailed, seed?.first == "unknown")
        if seed == ids { XCTAssertEqual(session.setupEntries.map(\.id), ids) }
        XCTAssertTrue(session.media === media)
        XCTAssertNil(session.ledger)
        XCTAssertNil(session.researchModel)
        XCTAssertEqual(capture.permissionRequests, 0)
        XCTAssertTrue(capture.createdURLs.isEmpty)
        XCTAssertTrue(recognizer.requests.isEmpty)
        XCTAssertTrue(history.entries.isEmpty)
        XCTAssertEqual(player.state, .idle)
        XCTAssertNil(hardware.currentLease)
        XCTAssertTrue(files.protectedURLs.isEmpty)
      }
    }
    func testAtomicSeedReorderKeepsCoordinatorAndMediaAndStartsNothing() throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      let session = r.session
      let media = session.media
      XCTAssertTrue(session.canSaveSetupWords)
      XCTAssertTrue(session.configureSetup(entryIDs: ids))
      XCTAssertEqual(session.setupEntries.map(\.id), ids)
      XCTAssertTrue(session.configureSetup(entryIDs: Array(ids.reversed())))
      XCTAssertEqual(session.setupEntries.map(\.id), Array(ids.reversed()))
      XCTAssertTrue(r.session === session)
      XCTAssertTrue(session.media === media)
      assertInert(r)
    }
    func testInvalidSeedIsAtomicAndLeavesExistingSetupUsable() throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      XCTAssertTrue(r.session.configureSetup(entryIDs: ids))
      for bad in [
        Array(ids.prefix(4)), Array(repeating: ids[0], count: 5),
        ["unknown"] + Array(ids.dropFirst()),
      ] {
        XCTAssertFalse(r.session.configureSetup(entryIDs: bad))
        XCTAssertEqual(r.session.setupEntries.map(\.id), ids)
        XCTAssertTrue(r.session.canSaveSetupWords)
        assertInert(r)
      }
    }
    func testStoreSuccessAndFilesystemFailureDoNotChangeSetupOrSessionOwners() throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      XCTAssertTrue(r.session.configureSetup(entryIDs: ids))
      let session = r.session
      let media = session.media
      let root = FileManager.default.temporaryDirectory.appendingPathComponent(
        "saved-session-unit-\(UUID())")
      defer { try? FileManager.default.removeItem(at: root) }
      let url = root.appendingPathComponent("words.json")
      let store = SavedGuidedWordsStore(fileURL: url)
      try store.save(entryIDs: session.setupEntries.map(\.id))
      XCTAssertEqual(store.entryIDs, ids)
      try FileManager.default.removeItem(at: url)
      try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false)
      XCTAssertThrowsError(try store.save(entryIDs: Array(ids.reversed())))
      XCTAssertTrue(r.session === session)
      XCTAssertTrue(r.session.media === media)
      XCTAssertEqual(session.setupEntries.map(\.id), ids)
      XCTAssertTrue(session.canSaveSetupWords)
      assertInert(r)
    }
    func testOnlyExplicitStartCreatesLedgerAndRejectsLaterSetupSeeding() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      XCTAssertTrue(r.session.configureSetup(entryIDs: ids))
      assertInert(r)
      await r.session.startInitialReview()
      XCTAssertEqual(r.session.ledger?.entries.map(\.id), ids)
      XCTAssertEqual(r.session.media.currentPrompt.id, ids[0])
      XCTAssertNotNil(r.session.ledger)
      XCTAssertFalse(r.session.canSaveSetupWords)
      XCTAssertFalse(r.session.configureSetup(entryIDs: Array(ids.reversed())))
      XCTAssertEqual(r.session.setupEntries.map(\.id), ids)
      XCTAssertEqual(r.capture.permissionRequests, 0)
      XCTAssertTrue(r.capture.createdURLs.isEmpty)
      XCTAssertTrue(r.recognizer.requests.isEmpty)
      XCTAssertTrue(r.history.entries.isEmpty)
      _ = await r.session.close()
    }
    func testClosedSessionRejectsSetupSeedAndSaveAdmission() async throws {
      let r = LocalGuidedGeneratedResources(testCase: .setup, runID: UUID())
      let closed = await r.session.close()
      XCTAssertTrue(closed)
      XCTAssertFalse(r.session.canSaveSetupWords)
      XCTAssertFalse(r.session.configureSetup(entryIDs: ids))
      assertInert(r)
    }
  }
#endif
