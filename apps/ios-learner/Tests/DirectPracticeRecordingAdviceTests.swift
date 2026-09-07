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
        detail: "For future recordings, try holding the phone a little farther away and use your usual voice."))
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.observation(summary: rail, assessment: quiet)?.detail,
      "For future recordings, use your usual voice.")
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
  func testPracticeRequirementPreservesSuppliedCoachingAndExactZeroQuietException() {
    let title = "Record another try to finish this word"
    let short = CaptureQualityAssessor().assess(summary([1], duration: 0.1))
    let quiet = CaptureAssessment.retry(CaptureQualityAssessor.quietCoaching)
    for (item, assessment) in [
      (summary([1], duration: 0.1), short),
      (summary([1], power: -90), quiet),
      (summary([0], duration: 0.1, power: -160), short),
      (summary([32767], power: -90), quiet),
    ] {
      guard case .retry(let coaching) = assessment else { return XCTFail("Expected retry coaching") }
      XCTAssertEqual(
        DirectPracticeRecordingAdvice.practiceRequirement(summary: item, assessment: assessment),
        .init(title: title, detail: coaching.detail + " You can also skip this word."))
    }
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.practiceRequirement(
        summary: summary([0], power: -160), assessment: quiet),
      .init(title: title,
        detail: "Keep the microphone uncovered, then record another try. You can also skip this word."))
    for item in [summary(nil), summary([1, -1]), summary([-32768, 32767])] {
      XCTAssertNil(DirectPracticeRecordingAdvice.practiceRequirement(summary: item, assessment: .acceptable))
    }
  }

  func testPracticeRequirementNonfiniteMeasurementsAlwaysUseUnavailableCopy() {
    let expected = DirectPracticeRecordingAdvice(
      title: "Record another try to finish this word",
      detail: "This recording’s length or volume measurement is unavailable. You can also skip this word.")
    for item in [
      summary([0], duration: .nan), summary([0], duration: .infinity),
      summary([0], power: .nan), summary([0], power: .infinity),
    ] {
      for assessment in [CaptureAssessment.acceptable, .retry(CaptureQualityAssessor.quietCoaching)] {
        XCTAssertEqual(
          DirectPracticeRecordingAdvice.practiceRequirement(summary: item, assessment: assessment),
          expected)
      }
    }
  }

  func testNewZeroRecordingAnnouncementIncludesExistingObservation() {
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.reviewAnnouncement(
        summary: summary([0, 0], power: -160),
        assessment: .retry(CaptureQualityAssessor.quietCoaching), isNewRecording: true),
      "Recording ready to play back. No sound was saved in this try. For future recordings, keep the microphone uncovered.")
  }

  func testNewRailRecordingAnnouncementPreservesSuppliedAssessmentAdvice() {
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.reviewAnnouncement(
        summary: summary([32767]), assessment: .acceptable, isNewRecording: true),
      "Recording ready to play back. Recording reached its volume limit. For future recordings, try holding the phone a little farther away and use your usual voice.")
    XCTAssertEqual(
      DirectPracticeRecordingAdvice.reviewAnnouncement(
        summary: summary([-32768]), assessment: .retry(CaptureQualityAssessor.quietCoaching),
        isNewRecording: true),
      "Recording ready to play back. Recording reached its volume limit. For future recordings, use your usual voice.")
  }

  func testNewRecordingAnnouncementUsesOnlyCurrentEvidence() {
    // Consecutive calls represent independent supplied evidence, not a session lifecycle.
    for samples: [Int16]? in [[0], nil, [1, -1], [32766, -32767], [0], nil] {
      let message = DirectPracticeRecordingAdvice.reviewAnnouncement(
        summary: summary(samples), assessment: .acceptable, isNewRecording: true)
      XCTAssertEqual(message, samples == [0]
        ? "Recording ready to play back. No sound was saved in this try. For future recordings, keep the microphone uncovered."
        : "Recording ready to play back.")
    }
  }

  func testReturningToKeptRecordingDoesNotRepeatRecordingAdvice() {
    for samples: [Int16]? in [[0], [32767], [-32768], nil, [1, -1]] {
      XCTAssertEqual(
        DirectPracticeRecordingAdvice.reviewAnnouncement(
          summary: summary(samples), assessment: .acceptable, isNewRecording: false),
        "Recording ready to play back.")
    }
  }

}
