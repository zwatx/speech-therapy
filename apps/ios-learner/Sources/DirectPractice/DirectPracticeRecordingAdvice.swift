/// Recording-only presentation; reading it never starts media or changes quality eligibility.
struct DirectPracticeRecordingAdvice: Equatable, Sendable {
  let title: String
  let detail: String

  static func observation(
    summary: CaptureSummary, assessment: CaptureAssessment
  ) -> Self? {
    guard let signal = summary.pcm16Signal else { return nil }
    if signal.isAllZero {
      return Self(
        title: "No sound was saved in this try",
        detail: "Make another try with the microphone uncovered.")
    }
    if signal.railSampleCount > 0 {
      return Self(
        title: "Recording reached its volume limit",
        detail: assessment == .acceptable
          ? "Try recording with the phone a little farther away, using your usual voice."
          : "Make another recording using your usual voice.")
    }
    return nil
  }

  /// Call with the actual latest take only. Earlier observations never replace its coaching.
  static func suppressesQuietTip(
    summary: CaptureSummary, assessment: CaptureAssessment
  ) -> Bool {
    summary.pcm16Signal?.isAllZero == true
      && assessment == .retry(CaptureQualityAssessor.quietCoaching)
  }
}
