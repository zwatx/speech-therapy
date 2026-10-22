import XCTest

@testable import CadenceLearner

final class CaptureQualityAssessorTests: XCTestCase {
  private let assessor = CaptureQualityAssessor()

  func testAcceptsClearSingleWordCapture() {
    let result = assessor.assess(
      CaptureSummary(duration: 1.1, averagePower: -22)
    )

    XCTAssertEqual(result, .acceptable)
  }

  func testRejectsShortCaptureWithoutScoringIt() {
    let result = assessor.assess(
      CaptureSummary(duration: 0.2, averagePower: -18)
    )

    guard case .retry(let coaching) = result else {
      return XCTFail("Expected neutral retry coaching")
    }
    XCTAssertEqual(coaching.title, "Give the whole word a little more time")
  }

  func testRejectsQuietCaptureWithoutScoringIt() {
    let result = assessor.assess(
      CaptureSummary(duration: 1.0, averagePower: -70)
    )

    guard case .retry = result else {
      return XCTFail("Expected neutral retry coaching")
    }
  }
}
