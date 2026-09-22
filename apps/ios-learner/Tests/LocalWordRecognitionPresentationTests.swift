import XCTest

@testable import CadenceLearner

final class LocalWordRecognitionPresentationTests: XCTestCase {
  private let statuses: [LocalWordRecognitionStatus] = [
    .matched, .notMatched, .uncertain, .timedOut, .unavailable, .cancelled,
  ]

  func testTechnicalRetryActionRequiresCurrentTakeAndAdmission() {
    let current = UUID()
    let otherTakes: [(UUID?, UUID?)] = [(nil, current), (current, nil), (current, UUID())]
    for status in [LocalWordRecognitionStatus.timedOut, .unavailable, .cancelled] {
      for hasEarlierTry in [false, true] {
        XCTAssertEqual(LocalWordRecognitionPresentation.retryActionLabel(status,
          checkedTryID: current, latestTryID: current, hasEarlierTry: hasEarlierTry, canCheck: true),
          hasEarlierTry ? "Try word check again on latest try" : "Try word check again")
        for (checked, latest) in otherTakes {
          XCTAssertNil(LocalWordRecognitionPresentation.retryActionLabel(status,
            checkedTryID: checked, latestTryID: latest, hasEarlierTry: hasEarlierTry, canCheck: true))
        }
        XCTAssertNil(LocalWordRecognitionPresentation.retryActionLabel(status,
          checkedTryID: current, latestTryID: current, hasEarlierTry: hasEarlierTry, canCheck: false))
      }
    }
  }

  func testSettledWordOutcomesNeverOfferTechnicalRetry() {
    let current = UUID()
    for status in [LocalWordRecognitionStatus.matched, .notMatched, .uncertain] {
      for hasEarlierTry in [false, true] {
        XCTAssertNil(LocalWordRecognitionPresentation.retryActionLabel(status,
          checkedTryID: current, latestTryID: current, hasEarlierTry: hasEarlierTry, canCheck: true))
      }
    }
  }

  func testCheckActionLabelPreservesCustomPrecedenceAndRejectsUnsettledRetryCopy() {
    let current = UUID()
    let custom = "Check word and run research model"
    for state in [LocalWordCheckState.idle, .checking, .cancelling, .cleanupBlocked,
                  .finished(.timedOut), .finished(.unavailable), .finished(.cancelled)] {
      XCTAssertEqual(LocalWordRecognitionPresentation.checkActionLabel(customLabel: custom,
        state: state, checkedTryID: current, latestTryID: current,
        hasEarlierTry: false, canCheck: true), custom)
      XCTAssertEqual(LocalWordRecognitionPresentation.checkActionLabel(customLabel: custom,
        state: state, checkedTryID: nil, latestTryID: UUID(),
        hasEarlierTry: true, canCheck: false), custom)
    }
    for state in [LocalWordCheckState.idle, .checking, .cancelling, .cleanupBlocked] {
      for earlier in [false, true] {
        XCTAssertEqual(LocalWordRecognitionPresentation.checkActionLabel(customLabel: nil,
          state: state, checkedTryID: current, latestTryID: current,
          hasEarlierTry: earlier, canCheck: true),
          earlier ? "Check words in latest try" : "Check words in this try")
      }
    }
    XCTAssertEqual(LocalWordRecognitionPresentation.checkActionLabel(customLabel: nil,
      state: .finished(.timedOut), checkedTryID: current, latestTryID: current,
      hasEarlierTry: true, canCheck: true), "Try word check again on latest try")
    let excluded: [(UUID?, UUID?, Bool)] = [(nil, current, true), (current, UUID(), true),
                                          (current, current, false)]
    for (checked, latest, admitted) in excluded {
      XCTAssertEqual(LocalWordRecognitionPresentation.checkActionLabel(customLabel: nil,
        state: .finished(.timedOut), checkedTryID: checked, latestTryID: latest,
        hasEarlierTry: false, canCheck: admitted), "Check words in this try")
    }
  }

  func testEveryObservationRequiresTheSameKeptTake() {
    let checked = UUID()
    let replacement = UUID()
    for status in statuses {
      XCTAssertNil(
        LocalWordRecognitionPresentation.observation(
          status, word: "ball", checkedTryID: checked, latestTryID: replacement))
      XCTAssertNil(
        LocalWordRecognitionPresentation.observation(
          status, word: "ball", checkedTryID: nil, latestTryID: checked))
      XCTAssertNil(
        LocalWordRecognitionPresentation.observation(
          status, word: "ball", checkedTryID: checked, latestTryID: nil))
      XCTAssertNotNil(
        LocalWordRecognitionPresentation.observation(
          status, word: "ball", checkedTryID: checked, latestTryID: checked))
    }
  }

  func testRecognitionNamesTheSelectedWordWithoutAProducedTranscript() {
    let take = UUID()
    for word in ["ball", "bread", "feather"] {
      for status in [LocalWordRecognitionStatus.matched, .notMatched, .uncertain] {
        let text = LocalWordRecognitionPresentation.observation(
          status, word: word, checkedTryID: take, latestTryID: take)
        XCTAssertTrue(text?.contains("“\(word)”") == true)
        XCTAssertTrue(text?.contains("this try") == true)
      }
    }
  }

  func testMatchedAndMismatchedWordsAreNotSoundJudgments() {
    let take = UUID()
    let matched = LocalWordRecognitionPresentation.observation(
      .matched, word: "ball", checkedTryID: take, latestTryID: take)
    let notMatched = LocalWordRecognitionPresentation.observation(
      .notMatched, word: "ball", checkedTryID: take, latestTryID: take)
    XCTAssertTrue(
      matched?.contains("Individual sounds aren’t assessed") == true)
    XCTAssertTrue(notMatched?.contains("No sound error is identified") == true)
  }

  func testTimeoutExplainsProcessingWithoutCallingTheWordUnclear() throws {
    let take = UUID()
    let timedOut = try XCTUnwrap(
      LocalWordRecognitionPresentation.observation(
        .timedOut, word: "ball", checkedTryID: take, latestTryID: take))
    let uncertain = LocalWordRecognitionPresentation.observation(
      .uncertain, word: "ball", checkedTryID: take, latestTryID: take)
    XCTAssertEqual(timedOut, "Word check took too long. Your recording is still here.")
    XCTAssertNotEqual(timedOut, uncertain)
    XCTAssertFalse(timedOut.contains("No clear match"))
    XCTAssertFalse(timedOut.contains("matched"))
  }

  func testAvailabilityExplainsOnDeviceRequirementsAndPreservesManualPractice() {
    let note = LocalWordRecognitionPresentation.availabilityNote
    XCTAssertTrue(note.contains("on this device"))
    XCTAssertTrue(note.contains("bundled English model"))
    XCTAssertTrue(note.contains("short word recordings"))
    XCTAssertTrue(note.contains("does not use an age"))
    XCTAssertTrue(note.contains("Word checks are optional"))
  }
  func testWordGuessCopyIsFallibleAndAbsentWithoutAnAuthenticatedAlternative() throws {
    XCTAssertNil(LocalWordRecognitionPresentation.wordGuess(nil))
    let guess = try XCTUnwrap(LocalWordGuess(completedText: "WALL", expectedWord: "ball"))
    XCTAssertEqual(LocalWordRecognitionPresentation.wordGuess(guess),
      "Word guess: “wall”. This may be wrong; individual sounds aren’t assessed.")
    XCTAssertNil(LocalWordGuess(completedText: "ball", expectedWord: "ball"))
    XCTAssertNil(LocalWordGuess(completedText: "two words", expectedWord: "ball"))
  }

}
