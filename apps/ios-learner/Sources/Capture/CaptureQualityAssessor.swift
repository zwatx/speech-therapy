import Foundation

struct CaptureSummary: Equatable, Sendable {
  let duration: TimeInterval
  let averagePower: Float
  let pcm16Signal: PCM16SignalMeasurements?

  init(duration: TimeInterval, averagePower: Float, pcm16Signal: PCM16SignalMeasurements? = nil) {
    self.duration = duration
    self.averagePower = averagePower
    self.pcm16Signal = pcm16Signal
  }
}

struct CapturedRecording: Equatable, Sendable {
  let url: URL
  let summary: CaptureSummary
  /// Exact producer identity; externally supplied parser inputs may have no capture owner.
  let cleanupOwnerID: UUID?

  init(url: URL, summary: CaptureSummary, cleanupOwnerID: UUID? = nil) {
    self.url = url
    self.summary = summary
    self.cleanupOwnerID = cleanupOwnerID
  }
}

struct CaptureCoaching: Equatable, Sendable {
  let title: String
  let detail: String
}

enum CaptureAssessment: Equatable, Sendable {
  case acceptable
  case retry(CaptureCoaching)
}

struct CaptureQualityAssessor: Sendable {
  static let quietCoaching = CaptureCoaching(
    title: "Move a little closer",
    detail: "Keep the phone about a hand away and use your comfortable voice.")
  let minimumDuration: TimeInterval
  let maximumDuration: TimeInterval
  let quietPowerFloor: Float

  init(
    minimumDuration: TimeInterval = 0.45,
    maximumDuration: TimeInterval = 4.0,
    quietPowerFloor: Float = -48
  ) {
    self.minimumDuration = minimumDuration
    self.maximumDuration = maximumDuration
    self.quietPowerFloor = quietPowerFloor
  }

  func assess(_ summary: CaptureSummary) -> CaptureAssessment {
    if summary.duration < minimumDuration {
      return .retry(
        CaptureCoaching(
          title: "Give the whole word a little more time",
          detail: "Wait for the tone, then say the word once at your usual pace."
        )
      )
    }

    if summary.duration > maximumDuration {
      return .retry(
        CaptureCoaching(
          title: "Try one short word",
          detail: "Say only the word on the card, then tap Stop."
        )
      )
    }

    if summary.averagePower < quietPowerFloor {
      return .retry(Self.quietCoaching)
    }

    return .acceptable
  }
}
