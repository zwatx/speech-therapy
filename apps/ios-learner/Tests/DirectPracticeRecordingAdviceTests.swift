import XCTest

@testable import CadenceLearner

final class DirectPracticeRecordingAdviceTests: XCTestCase {
  private func summary(_ samples: [Int16]?, duration: Double = 1, power: Float = -20)
    -> CaptureSummary
  {
    var signal = PCM16SignalMeasurements.Accumulator()
    for sample in samples ?? [] { signal.append(sample) }
    return .init(duration: duration, averagePower: power, pcm16Signal: signal.measurements())
  }

  func testZeroAndRailCopyUsesActualAssessmentWithoutChangingIt() {
    let assessor = CaptureQualityAssessor()
    let zero = summary([0, 0], power: -160)
    let quiet = assessor.assess(zero)
    XCTAssertEqual(quiet, .retry(CaptureQualityAssessor.quietCoaching))
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.observation(summary: zero, assessment: quiet),
      .init(
        title: "No sound was saved in this try",
        detail: "For future recordings, keep the microphone uncovered."))
    let rail = summary([-32768, 0, 32767])
    XCTAssertEqual(assessor.assess(rail), .acceptable)
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.observation(summary: rail, assessment: .acceptable),
      .init(
        title: "Recording reached its volume limit",
        detail: "Try recording with the phone a little farther away, using your usual voice."))
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.observation(summary: rail, assessment: quiet)?.detail,
      "Make another recording using your usual voice.")
  }

  func testOnlyExactLatestZeroAndSemanticQuietCoachingSuppressRedundantTip() {
    let zero = summary([0], power: -160)
    let quiet = CaptureAssessment.retry(CaptureQualityAssessor.quietCoaching)
    XCTAssertTrue(
      DirectPracticeRecordingAdvice.suppressesQuietTip(summary: zero, assessment: quiet))
    let short = summary([0], duration: 0.1, power: -160)
    let long = summary([0], duration: 5, power: -160)
    let custom = CaptureAssessment.retry(.init(title: "Custom", detail: "Keep this recording tip."))
    for assessment in [
      CaptureQualityAssessor().assess(short), CaptureQualityAssessor().assess(long),
      custom, .acceptable,
    ] {
      XCTAssertFalse(
        DirectPracticeRecordingAdvice.suppressesQuietTip(
          summary: zero, assessment: assessment))
    }
    // Calling with latest, rather than an earlier zero, is the UI's only suppression input.
    for latest in [summary(nil, power: -160), summary([1], power: -160), summary([32767])] {
      XCTAssertFalse(
        DirectPracticeRecordingAdvice.suppressesQuietTip(
          summary: latest, assessment: quiet))
    }
  }

  func testUnknownAndNonEventEvidenceProduceNoNormalBadgeOrNewQualityRule() {
    for item in [summary(nil), summary([1, -1, 0]), summary([32766, -32767])] {
      XCTAssertNil(
        DirectPracticeRecordingAdvice.observation(summary: item, assessment: .acceptable))
      XCTAssertEqual(CaptureQualityAssessor().assess(item), .acceptable)
    }
    XCTAssertNil(CaptureSummary(duration: 1, averagePower: -20).pcm16Signal)
  }
}
