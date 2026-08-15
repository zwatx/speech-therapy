/// Recording-only presentation; reading it never starts media or changes quality eligibility.
struct DirectPracticeRecordingAdvice: Equatable, Sendable {
  let title: String
  let detail: String

  /// Explains the existing capture gate for finishing guided practice, independently
  /// of an optional word match. The caller supplies the exact latest take's assessment.
  static func practiceRequirement(
    summary: CaptureSummary, assessment: CaptureAssessment
  ) -> Self? {
    let title = "Record another try to finish this word"
    guard summary.duration.isFinite, summary.averagePower.isFinite else {
      return Self(
        title: title,
        detail: "This recording’s length or volume measurement is unavailable. You can also skip this word.")
    }
    guard case .retry(let coaching) = assessment else { return nil }
    return Self(
      title: title,
      detail: suppressesQuietTip(summary: summary, assessment: assessment)
        ? "Keep the microphone uncovered, then record another try. You can also skip this word."
        : "\(coaching.detail) You can also skip this word.")
  }

  static func observation(
    summary: CaptureSummary, assessment: CaptureAssessment
  ) -> Self? {
    guard let signal = summary.pcm16Signal else { return nil }
    if signal.isAllZero {
      return Self(
        title: "No sound was saved in this try",
        detail: "For future recordings, keep the microphone uncovered.")
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
