import XCTest

@testable import CadenceLearner

final class VisualCaptureQualityTests: XCTestCase {
  private let assessor = VisualCaptureQualityAssessor()

  func testOneCenteredObservableFaceProducesDerivedGeometryOnly() {
    let snapshot = assessor.assess([goodFace()])

    XCTAssertTrue(snapshot.isUsable)
    XCTAssertGreaterThan(snapshot.captureQualityScore, 0.85)
    XCTAssertEqual(snapshot.runtimeVersion, "apple-vision-landmarks-feasibility-v1")
    XCTAssertEqual(snapshot.faceCoverage ?? 0, 0.28, accuracy: 0.0001)
    XCTAssertEqual(snapshot.mouthWidthRatio ?? 0, 0.3, accuracy: 0.0001)
    XCTAssertEqual(snapshot.mouthApertureRatio ?? 0, 0.12, accuracy: 0.0001)
  }

  func testMissingAndMultipleFacesAreNotScoredAsUsable() {
    let missing = assessor.assess([])
    let multiple = assessor.assess([goodFace(), goodFace()])

    XCTAssertEqual(missing.issues, [.noFace])
    XCTAssertEqual(missing.captureQualityScore, 0)
    XCTAssertEqual(multiple.issues, [.multipleFaces])
    XCTAssertEqual(multiple.captureQualityScore, 0)
    XCTAssertEqual(assessor.coaching(for: missing)?.title, "Bring your face into view")
  }

  func testFramingAndPoseProblemsProduceCoachingInsteadOfArticulationClaims() {
    let face = VisualFaceObservation(
      bounds: NormalizedVisualRect(x: 0.01, y: 0.4, width: 0.25, height: 0.3),
      outerLip: goodLip,
      innerLip: [],
      yawRadians: 0.52,
      rollRadians: 0
    )

    let snapshot = assessor.assess([face])

    XCTAssertEqual(snapshot.issues, [.faceTooFar, .faceOffCenter, .headTurned])
    XCTAssertEqual(assessor.coaching(for: snapshot)?.title, "Move a little closer")
  }

  func testUnavailableMouthLandmarksAbstain() {
    let face = VisualFaceObservation(
      bounds: NormalizedVisualRect(x: 0.25, y: 0.2, width: 0.5, height: 0.56),
      outerLip: [],
      innerLip: [],
      yawRadians: 0,
      rollRadians: 0
    )

    let snapshot = assessor.assess([face])

    XCTAssertFalse(snapshot.isUsable)
    XCTAssertEqual(snapshot.issues, [.mouthLandmarksUnavailable])
    XCTAssertNil(snapshot.mouthWidthRatio)
    XCTAssertNil(snapshot.mouthApertureRatio)
    XCTAssertEqual(assessor.coaching(for: snapshot)?.title, "Make your mouth visible")
  }

  func testNonFiniteObservationsFailClosed() {
    let face = VisualFaceObservation(
      bounds: NormalizedVisualRect(x: .nan, y: 0.2, width: 0.5, height: 0.56),
      outerLip: goodLip,
      innerLip: [],
      yawRadians: 0,
      rollRadians: 0
    )

    let snapshot = assessor.assess([face])

    XCTAssertEqual(snapshot.captureQualityScore, 0)
    XCTAssertEqual(snapshot.issues, [.invalidObservation])
    XCTAssertNil(snapshot.faceCoverage)
  }

  func testMissingPoseAndNonFiniteLipGeometryFailClosed() {
    let missingPose = VisualFaceObservation(
      bounds: NormalizedVisualRect(x: 0.25, y: 0.2, width: 0.5, height: 0.56),
      outerLip: goodLip,
      innerLip: [],
      yawRadians: nil,
      rollRadians: nil
    )
    var corruptLip = goodLip
    corruptLip[3] = NormalizedVisualPoint(x: .nan, y: 0.4)
    let corruptGeometry = VisualFaceObservation(
      bounds: NormalizedVisualRect(x: 0.25, y: 0.2, width: 0.5, height: 0.56),
      outerLip: corruptLip,
      innerLip: [],
      yawRadians: 0,
      rollRadians: 0
    )

    XCTAssertEqual(assessor.assess([missingPose]).issues, [.poseUnavailable])
    XCTAssertEqual(
      assessor.assess([corruptGeometry]).issues,
      [.mouthLandmarksUnavailable]
    )
  }

  private var goodLip: [NormalizedVisualPoint] {
    [
      .init(x: 0.35, y: 0.45),
      .init(x: 0.42, y: 0.41),
      .init(x: 0.5, y: 0.4),
      .init(x: 0.58, y: 0.41),
      .init(x: 0.65, y: 0.45),
      .init(x: 0.58, y: 0.5),
      .init(x: 0.5, y: 0.52),
      .init(x: 0.42, y: 0.5),
    ]
  }

  private func goodFace() -> VisualFaceObservation {
    VisualFaceObservation(
      bounds: NormalizedVisualRect(x: 0.25, y: 0.2, width: 0.5, height: 0.56),
      outerLip: goodLip,
      innerLip: [],
      yawRadians: 0.04,
      rollRadians: -0.03
    )
  }
}
