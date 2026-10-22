import Foundation

/// Neutral self-listening guidance for a kept take, built only from the selected sound's
/// symbol, the selected position and the printed word. It describes where the intended
/// sound is meant to be; it never describes what was produced or heard.
///
/// Library positions mean the first, interior or last phone (clusters included), so the
/// wording names only that place. It never picks one occurrence of a repeated sound.
enum DirectPracticeListeningFocus {
  static func place(_ position: PracticeTargetPosition) -> String {
    switch position {
    case .beginning: "at the start"
    case .middle: "in the middle"
    case .end: "at the end"
    }
  }

  /// `twoTries` is true when an earlier and a latest take are both kept.
  static func text(sound: PracticeSound, word: String, twoTries: Bool) -> String {
    let target = "/\(sound.symbol)/ \(place(sound.position)) of “\(word)”"
    let replay = twoTries ? "Play the earlier try, then the latest." : "Play your try."
    return "\(replay) Listen for \(target)."
  }
}
