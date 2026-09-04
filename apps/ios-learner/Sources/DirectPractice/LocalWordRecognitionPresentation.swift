import Foundation

/// Recognition copy belongs to one kept take. It does not interpret the intended
/// sound, infer the speaker's age, or compare pronunciation across attempts.
enum LocalWordRecognitionPresentation {
  static let availabilityNote =
    "Word recognition runs on this device using a bundled English model for short word recordings. It does not use an age or assess individual sounds. Word checks are optional. Use the available controls to record or listen."

  static func retryActionLabel(
    _ status: LocalWordRecognitionStatus, checkedTryID: UUID?, latestTryID: UUID?,
    hasEarlierTry: Bool, canCheck: Bool
  ) -> String? {
    guard canCheck, let checkedTryID, let latestTryID, checkedTryID == latestTryID else { return nil }
    switch status {
    case .timedOut, .unavailable, .cancelled:
      return hasEarlierTry ? "Try word check again on latest try" : "Try word check again"
    case .matched, .notMatched, .uncertain:
      return nil
    }
  }

  static func checkActionLabel(
    customLabel: String?, state: LocalWordCheckState,
    checkedTryID: UUID?, latestTryID: UUID?, hasEarlierTry: Bool, canCheck: Bool
  ) -> String {
    if let customLabel { return customLabel }
    if case .finished(let status) = state,
      let retry = retryActionLabel(status, checkedTryID: checkedTryID, latestTryID: latestTryID,
        hasEarlierTry: hasEarlierTry, canCheck: canCheck)
    {
      return retry
    }
    return hasEarlierTry ? "Check words in latest try" : "Check words in this try"
  }

  static func wordGuess(_ guess: LocalWordGuess?, hasEarlierTry: Bool = false) -> String? {
    guard let guess else { return nil }
    let take = hasEarlierTry ? "the latest try" : "this try"
    return "Word guess for \(take): “\(guess.word)”. This may be wrong; individual sounds aren’t assessed."
  }

  static func observation(
    _ status: LocalWordRecognitionStatus, word: String,
    checkedTryID: UUID?, latestTryID: UUID?
  ) -> String? {
    guard let checkedTryID, let latestTryID, checkedTryID == latestTryID else { return nil }
    switch status {
    case .matched:
      return
        "“\(word)” matched in this try. Individual sounds aren’t assessed."
    case .notMatched:
      return
        "No match for “\(word)” in this try. No sound error is identified."
    case .uncertain:
      return
        "No clear match for “\(word)” in this try."
    case .timedOut:
      return "Word check took too long. Your recording is still here."
    case .unavailable:
      return
        "Word check unavailable. Your recording is still here."
    case .cancelled:
      return "Word check cancelled. No result kept."
    }
  }
}
