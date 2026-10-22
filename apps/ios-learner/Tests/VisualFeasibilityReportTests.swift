import XCTest

@testable import CadenceLearner

final class VisualFeasibilityReportTests: XCTestCase {
  #if DEBUG
    func testConfigurationRequiresTheDebugFlagAndRecordsScenario() {
      XCTAssertEqual(
        VisualPracticeConfiguration.from(arguments: ["CadenceLearner"]),
        .disabled
      )
      let configured = VisualPracticeConfiguration.from(
        arguments: [
          "CadenceLearner",
          "-CadenceVisualFeasibility",
          "-CadenceVisualScenario",
          "mouth-covered",
        ]
      )
      XCTAssertTrue(configured.isEnabled)
      XCTAssertEqual(configured.protocolID, "bilabial-closure-v1")
      XCTAssertEqual(configured.feasibilityScenario, .mouthCovered)

      let unknown = VisualPracticeConfiguration.from(
        arguments: [
          "CadenceLearner",
          "-CadenceVisualFeasibility",
          "-CadenceVisualScenario",
          "not-a-protocol-scenario",
        ]
      )
      XCTAssertEqual(unknown.feasibilityScenario, .unstructured)
    }
  #else
    func testRuntimeDefaultKeepsVisualFeasibilityDisabledInRelease() {
      XCTAssertEqual(VisualPracticeConfiguration.runtimeDefault, .disabled)
    }
  #endif

  func testReportContainsBoundedAggregateEvidenceWithoutRawGeometry() throws {
    var accumulator = VisualFeasibilityAccumulator(
      sessionID: UUID(uuidString: "00000000-0000-4000-8000-000000000001")!,
      protocolID: "bilabial-closure-v1",
      scenario: .protocolCompliant,
      startedAt: Date(timeIntervalSince1970: 0)
    )
    accumulator.record(
      snapshot(score: 0.95, issues: [], latency: 20),
      thermalState: .nominal,
      lowPowerMode: false
    )
    accumulator.record(
      snapshot(score: 0.88, issues: [], latency: 90),
      thermalState: .fair,
      lowPowerMode: false
    )
    accumulator.record(
      snapshot(score: 0, issues: [.noFace], latency: 150),
      thermalState: .serious,
      lowPowerMode: true
    )
    accumulator.recordExtractionFailure(
      thermalState: .fair,
      lowPowerMode: false
    )

    let report = try XCTUnwrap(
      accumulator.report(
        endedAt: Date(timeIntervalSince1970: 10),
        device: .init(
          hardwareIdentifier: "iPhone15,2",
          systemName: "iOS",
          systemVersion: "test",
          appVersion: "0.1.0",
          buildVersion: "1"
        )
      )
    )

    XCTAssertEqual(report.schemaVersion, "visual-feasibility-report-v1")
    XCTAssertEqual(report.frames.totalFrames, 4)
    XCTAssertEqual(report.frames.usableFrames, 2)
    XCTAssertEqual(report.frames.framesWithAnyIssue, 1)
    XCTAssertEqual(report.frames.challengeHitFrames, 0)
    XCTAssertEqual(report.frames.extractionFailures, 1)
    XCTAssertEqual(report.frames.usableFrameRate, 0.5, accuracy: 0.0001)
    XCTAssertEqual(report.frames.issueCounts, ["noFace": 1])
    XCTAssertEqual(report.latency.measuredFrames, 3)
    XCTAssertEqual(report.latency.p95Bucket, "le-200")
    XCTAssertEqual(report.runtime.maximumThermalState, "serious")
    XCTAssertTrue(report.runtime.lowPowerModeObserved)
    XCTAssertFalse(report.configuration.rawFramesRetained)
    XCTAssertFalse(report.configuration.rawLandmarksRetained)
    XCTAssertFalse(report.configuration.uploaded)

    let data = try JSONEncoder().encode(report)
    let json = try XCTUnwrap(String(data: data, encoding: .utf8))
    XCTAssertFalse(json.contains("mouthWidthRatio"))
    XCTAssertFalse(json.contains("mouthApertureRatio"))
    XCTAssertFalse(json.contains("faceCenterOffset"))
    XCTAssertFalse(json.contains("learner"))
    XCTAssertFalse(json.contains("token"))

    let fixtureData = try Data(contentsOf: canonicalFixtureURL())
    let encodedObject = try JSONSerialization.jsonObject(with: data) as? NSDictionary
    let fixtureObject = try JSONSerialization.jsonObject(with: fixtureData) as? NSDictionary
    XCTAssertEqual(encodedObject, fixtureObject)
  }

  func testEmptyAccumulatorDoesNotProduceAReport() {
    let accumulator = VisualFeasibilityAccumulator(
      protocolID: "bilabial-closure-v1",
      scenario: .unstructured
    )
    XCTAssertNil(
      accumulator.report(
        endedAt: Date(),
        device: .init(
          hardwareIdentifier: "test-device",
          systemName: "iOS",
          systemVersion: "test",
          appVersion: "0.1.0",
          buildVersion: "1"
        )
      )
    )
  }

  func testEveryScenarioCountsOnlyItsIntendedChallengeIssues() throws {
    let allIssues: [VisualCaptureIssue] = [
      .noFace,
      .multipleFaces,
      .faceTooFar,
      .faceTooClose,
      .faceOffCenter,
      .headTurned,
      .mouthLandmarksUnavailable,
      .poseUnavailable,
      .invalidObservation,
    ]
    let expectedByScenario: [(VisualFeasibilityScenario, [VisualCaptureIssue])] = [
      (.protocolCompliant, []),
      (
        .lowLight,
        [
          .noFace,
          .mouthLandmarksUnavailable,
          .poseUnavailable,
          .invalidObservation,
        ]
      ),
      (.faceTooFar, [.faceTooFar]),
      (.faceTooClose, [.faceTooClose]),
      (.faceOffCenter, [.faceOffCenter]),
      (.headTurned, [.headTurned]),
      (.mouthCovered, [.mouthLandmarksUnavailable]),
      (.multipleFaces, [.multipleFaces]),
      (.unstructured, []),
    ]

    for (scenario, expectedIssues) in expectedByScenario {
      for issue in allIssues {
        var accumulator = VisualFeasibilityAccumulator(
          protocolID: "bilabial-closure-v1",
          scenario: scenario
        )
        accumulator.record(
          snapshot(score: 0, issues: [issue], latency: 20),
          thermalState: .nominal,
          lowPowerMode: false
        )

        let report = try XCTUnwrap(
          accumulator.report(
            endedAt: Date(),
            device: testDevice
          )
        )
        XCTAssertEqual(
          report.frames.challengeHitFrames,
          expectedIssues.contains(issue) ? 1 : 0,
          "Unexpected challenge mapping for \(scenario.rawValue) and \(issue.rawValue)"
        )
      }
    }
  }

  private func snapshot(
    score: Double,
    issues: [VisualCaptureIssue],
    latency: Double
  ) -> VisualQualitySnapshot {
    VisualQualitySnapshot(
      runtimeVersion: VisualCaptureQualityAssessor.runtimeVersion,
      captureQualityScore: score,
      issues: issues,
      faceCoverage: nil,
      faceCenterOffset: nil,
      mouthWidthRatio: nil,
      mouthApertureRatio: nil,
      yawRadians: nil,
      rollRadians: nil,
      processingLatencyMilliseconds: latency
    )
  }

  private func canonicalFixtureURL() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appending(path: "packages/visual-evaluation/fixtures/visual-feasibility-report.valid.json")
  }

  private var testDevice: VisualFeasibilityReport.Device {
    .init(
      hardwareIdentifier: "iPhone15,2",
      systemName: "iOS",
      systemVersion: "test",
      appVersion: "0.1.0",
      buildVersion: "1"
    )
  }
}
