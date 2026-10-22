#if DEBUG && targetEnvironment(simulator)
  import XCTest
  import Foundation
  @testable import CadenceLearner

  @MainActor
  final class HistoryGeneratedHostTests: XCTestCase {
    private let runID = UUID(uuidString: "BAC12345-1234-4321-ABCD-0123456789AB")!
    private func arguments(_ value: String) -> [String] {
      [
        "CadenceLearner", "-CadenceHistoryMode", "-CadenceHistoryUITestCase", value,
        "-CadenceControlledUIRunID", runID.uuidString,
      ]
    }
    private func select(
      _ args: [String], _ env: [String: String] = ["CADENCE_CONTROLLED_UI_HOST": "1"],
      runtime: Bool = true
    ) -> ControlledAppLaunch.Selection {
      ControlledAppLaunch.select(arguments: args, environment: env, hasXCTestRuntime: runtime)
    }

    func testHistoryAdmissionRequiresEachExactCaseAndOnlyMetadataDestinations() {
      XCTAssertEqual(
        HistoryGeneratedCase.allCases.map(\.rawValue),
        ["historyfour", "hundred", "empty", "unreadable", "clearFailure"])
      for testCase in HistoryGeneratedCase.allCases {
        let args = arguments(testCase.rawValue)
        for env in [
          ["CADENCE_CONTROLLED_UI_HOST": "1"], ["TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"],
        ] {
          XCTAssertEqual(
            select(args, env), .generated(.init(fixture: .history(testCase), runID: runID)))
        }
        let configuration = ControlledUIConfiguration(fixture: .history(testCase), runID: runID)
        for destination in ControlledUIConfiguration.Destination.allCases {
          XCTAssertEqual(
            configuration.admits(destination),
            [.home, .historyRead, .historyClear].contains(destination))
        }
      }
    }

    func testHistoryMalformedMixedMissingAndDuplicateArgumentsStayInert() {
      let args = arguments("historyfour")
      for invalid in [
        arguments("unknown"), arguments("four"), args + ["-CadenceHistoryMode"],
        args + ["-CadenceHistoryUITestCase", "empty"], args + ["-CadenceSoundMode"],
        args + ["-CadenceClinicalMode"], args + ["-accessibility-practice-preview"],
        args + ["-CadenceControlledUIRunID", runID.uuidString], Array(args.dropLast(2)),
        [
          "CadenceLearner", "-CadenceHistoryMode", "-CadenceSoundUITestCase", "br",
          "-CadenceControlledUIRunID", runID.uuidString,
        ],
        [
          "CadenceLearner", "-CadenceSoundMode", "-CadenceHistoryUITestCase", "historyfour",
          "-CadenceControlledUIRunID", runID.uuidString,
        ],
      ] {
        XCTAssertEqual(select(invalid), .inert)
      }
      for value in [
        "", "not-a-uuid", "00000000-0000-0000-0000-000000000000", runID.uuidString + " ",
      ] {
        var invalid = args
        invalid[invalid.count - 1] = value
        XCTAssertEqual(select(invalid), .inert)
      }
    }

    func testHistoryNeedsExplicitOptInAndUnitOverrideAlwaysWins() {
      let args = arguments("hundred")
      for env in [
        [:], ["CADENCE_CONTROLLED_UI_HOST": "0"],
        ["CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "0"],
        ["CADENCE_CONTROLLED_UI_HOST": "1", "CADENCE_CONTROLLED_UNIT_HOST": "1"],
        ["CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST": "1"],
      ] {
        XCTAssertEqual(select(args, env), .inert)
      }
      for incomplete in [
        ["CadenceLearner", "-CadenceHistoryMode"],
        ["CadenceLearner", "-CadenceHistoryUITestCase"],
        ["CadenceLearner", "-CadenceHistoryMode", "-CadenceHistoryUITestCase"],
        arguments("historyfour"),
      ] {
        XCTAssertEqual(select(incomplete, [:], runtime: false), .inert)
      }
      XCTAssertEqual(
        select(["CadenceLearner", "-CadenceSoundMode"], [:], runtime: false), .development)
      XCTAssertEqual(
        select(["CadenceLearner", "-CadenceClinicalMode"], [:], runtime: false), .development)
    }

    func testFourAndHundredSeedOnceThroughRealStoreWithExactOrderReadbackAndPrivateCleanup() throws
    {
      for testCase in [HistoryGeneratedCase.historyfour, .hundred] {
        let r = HistoryGeneratedResources(testCase: testCase, runID: runID)
        defer { r.finish() }
        let history = try XCTUnwrap(r.history)
        XCTAssertFalse(r.initializationFailed)
        XCTAssertEqual(history.entries.count, testCase.seedCount)
        XCTAssertEqual(
          history.entries.map(\.id),
          (1..<(testCase.seedCount + 1)).map(HistoryGeneratedResources.id))
        XCTAssertEqual(
          history.entries.map(\.completedAt),
          (1..<(testCase.seedCount + 1)).map(HistoryGeneratedResources.date))
        XCTAssertTrue(r.receipt.seedOrderConfirmed && r.receipt.seedReadbackConfirmed)
        let initial = history.entries
        let hash = r.receipt.currentFileSHA256
        r.refreshEvidence()
        r.refreshEvidence()
        XCTAssertEqual(history.entries, initial)
        XCTAssertEqual(r.receipt.currentFileSHA256, hash)
        XCTAssertTrue(r.receipt.bytesUnchanged && r.receipt.reopenedMatches)
        r.finish()
        XCTAssertTrue(r.receipt.cleanupConfirmed)
        XCTAssertFalse(r.receipt.failed)
        XCTAssertFalse(FileManager.default.fileExists(atPath: r.directory.path))
      }
    }

    func testEmptyAndUnreadableAreDistinctAndUnreadableBytesPersistUntilRealClear() throws {
      for testCase in [HistoryGeneratedCase.empty, .unreadable] {
        let r = HistoryGeneratedResources(testCase: testCase, runID: runID)
        defer { r.finish() }
        let history = try XCTUnwrap(r.history)
        XCTAssertFalse(r.initializationFailed)
        XCTAssertTrue(history.entries.isEmpty)
        XCTAssertEqual(history.loadError != nil, testCase == .unreadable)
        XCTAssertTrue(r.receipt.bytesUnchanged)
        try history.clear()
        r.refreshEvidence()
        XCTAssertNil(history.loadError)
        XCTAssertTrue(r.receipt.reopenedMatches)
        XCTAssertEqual(r.receipt.reopenedCount, 0)
      }
    }

    func testGeneratedObstacleMakesActualClearFailThenExplicitRepairAndRealRetrySucceed() throws {
      let r = HistoryGeneratedResources(testCase: .clearFailure, runID: runID)
      defer { r.finish() }
      let history = try XCTUnwrap(r.history)
      let initial = history.entries
      XCTAssertTrue(r.receipt.obstaclePresent)
      XCTAssertThrowsError(try history.clear())
      XCTAssertEqual(history.entries, initial)
      r.refreshEvidence()
      XCTAssertTrue(r.receipt.obstaclePresent)
      r.repairObstacle()
      XCTAssertEqual(r.receipt.repairCount, 1)
      XCTAssertEqual(history.entries, initial)
      try history.clear()
      r.refreshEvidence()
      XCTAssertTrue(history.entries.isEmpty)
      XCTAssertTrue(r.receipt.reopenedMatches)
      XCTAssertEqual(r.receipt.reopenedCount, 0)
    }

    func testGeneratedObservationClearUpdatesSameStoreAndDoesNotReseed() throws {
      let r = HistoryGeneratedResources(testCase: .historyfour, runID: runID)
      defer { r.finish() }
      let history = try XCTUnwrap(r.history)
      r.clearForObservation()
      XCTAssertEqual(r.receipt.observationClearCount, 1)
      XCTAssertEqual(r.receipt.currentCount, 0)
      XCTAssertEqual(r.receipt.reopenedCount, 0)
      r.refreshEvidence()
      XCTAssertTrue(history.entries.isEmpty)
      XCTAssertTrue(r.receipt.reopenedMatches)
    }

    func testInvalidRunNeverConstructsStoreOrClaimsOwnedDirectoryCleanup() {
      let r = HistoryGeneratedResources(
        testCase: .historyfour,
        runID: UUID(uuidString: "00000000-0000-0000-0000-000000000000")!)
      XCTAssertNil(r.history)
      XCTAssertTrue(r.initializationFailed)
      XCTAssertFalse(r.receipt.ownedDirectoryCreated)
      r.finish()
      XCTAssertTrue(r.receipt.failed)
      XCTAssertFalse(r.receipt.cleanupAttempted)
      XCTAssertFalse(r.receipt.cleanupConfirmed)
    }
  }
#endif
