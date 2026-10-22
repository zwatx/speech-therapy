import XCTest

@testable import CadenceLearner

final class DirectPracticeListeningFocusTests: XCTestCase {
  private func sound(_ soundID: String, _ position: PracticeTargetPosition) -> PracticeSound {
    guard let sound = PracticeLibrary.session(soundID: soundID, position: position) else {
      preconditionFailure("No library session for \(soundID) \(position)")
    }
    return sound
  }

  func testRepresentativeCopyForEachPositionAndTakeCount() {
    let b = sound("b", .beginning)
    XCTAssertEqual(
      DirectPracticeListeningFocus.text(sound: b, word: "ball", twoTries: false),
      "Play your try. Listen for /b/ at the start of “ball”."
    )
    XCTAssertEqual(
      DirectPracticeListeningFocus.text(sound: b, word: "ball", twoTries: true),
      "Play the earlier try, then the latest. Listen for /b/ at the start of “ball”."
    )
    XCTAssertEqual(
      DirectPracticeListeningFocus.text(
        sound: sound("voiced-th", .middle), word: "feather", twoTries: false),
      "Play your try. Listen for /ð/ in the middle of “feather”.")
    XCTAssertEqual(
      DirectPracticeListeningFocus.text(sound: sound("ng", .end), word: "king", twoTries: true),
      "Play the earlier try, then the latest. Listen for /ŋ/ at the end of “king”.")
  }

  /// Every actual library entry binds its own selected symbol, position and word; single and
  /// two-take guidance stay distinct, and only the two-take form names earlier and latest.
  func testEveryLibraryEntryBindsSelectedTargetAndTakeCount() {
    var combinations = Set<String>()
    for entry in PracticeLibrary.entries() {
      guard
        let session = PracticeLibrary.session(
          soundID: entry.soundID, position: entry.position, startingAt: entry.id)
      else {
        XCTFail("No session for \(entry.id)")
        continue
      }
      XCTAssertEqual(session.position, entry.position, entry.id)
      XCTAssertEqual(session.prompts.first, entry.prompt, entry.id)
      combinations.insert("\(entry.soundID):\(entry.position.rawValue)")
      let target =
        "/\(session.symbol)/ \(DirectPracticeListeningFocus.place(entry.position)) of “\(entry.prompt.word)”"
      let one = DirectPracticeListeningFocus.text(
        sound: session, word: entry.prompt.word, twoTries: false)
      let two = DirectPracticeListeningFocus.text(
        sound: session, word: entry.prompt.word, twoTries: true)
      XCTAssertEqual(one, "Play your try. Listen for \(target).", entry.id)
      XCTAssertEqual(two, "Play the earlier try, then the latest. Listen for \(target).", entry.id)
      XCTAssertFalse(one.contains("earlier"), entry.id)
      XCTAssertTrue(two.contains("earlier") && two.contains("latest"), entry.id)
    }
    // Every sound group has at least its default position; combinations come from data.
    XCTAssertEqual(
      Set(combinations.map { String($0.split(separator: ":")[0]) }),
      Set(PracticeLibrary.sounds.map(\.id)))
    for sound in PracticeLibrary.sounds {
      XCTAssertTrue(combinations.contains("\(sound.id):\(sound.position.rawValue)"), sound.id)
    }
  }

  func testPositionWordingIsDistinctAndNeverReadsAtTheMiddle() {
    let places = PracticeTargetPosition.allCases.map(DirectPracticeListeningFocus.place)
    XCTAssertEqual(places, ["at the start", "in the middle", "at the end"])
  }

  /// Positions are first/interior/last phone. A repeated target sound or a leading cluster
  /// changes nothing: the guidance is the same template, with no chosen occurrence.
  func testRepeatedSoundsAndClustersUseOnlyThePositionTemplate() {
    let vowels: Set = [
      "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW",
    ]
    let entries = PracticeLibrary.entries()
    let repeated = entries.filter { entry in
      entry.prompt.phones.filter { $0 == entry.targetPhone }.count > 1
    }
    let clusters = entries.filter { entry in
      entry.position == .beginning && entry.prompt.phones.count > 1
        && !vowels.contains(entry.prompt.phones[1])
    }
    XCTAssertFalse(repeated.isEmpty)
    XCTAssertFalse(clusters.isEmpty)
    for entry in repeated + clusters {
      guard
        let session = PracticeLibrary.session(
          soundID: entry.soundID, position: entry.position, startingAt: entry.id)
      else {
        XCTFail("No session for \(entry.id)")
        continue
      }
      for twoTries in [false, true] {
        let text = DirectPracticeListeningFocus.text(
          sound: session, word: entry.prompt.word, twoTries: twoTries)
        // Identical to a placeholder word in the same position: nothing occurrence-specific.
        let template = DirectPracticeListeningFocus.text(
          sound: session, word: "WORD", twoTries: twoTries)
        XCTAssertEqual(
          text, template.replacingOccurrences(of: "“WORD”", with: "“\(entry.prompt.word)”"),
          entry.id)
      }
    }
  }
}
