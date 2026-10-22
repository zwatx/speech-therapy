#if DEBUG && targetEnvironment(simulator)
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchPracticeFocusTests: XCTestCase {
    private func prompt(_ id: String) throws -> ResearchFeedbackPrompt {
      try XCTUnwrap(ResearchFeedbackCatalog.prompts.first { $0.id == id })
    }
    private func cue(_ id: String, exampleAvailable: Bool = true) throws -> String {
      try XCTUnwrap(
        ResearchPracticeFocus.cue(for: prompt(id), exampleAvailable: exampleAvailable))
    }

    func testAllFifteenExactTargetsResolveWithoutChangingCatalogExamplesOrGuidedChoices() throws {
      let catalog = ResearchFeedbackCatalog.prompts
      let requests = catalog.map(\.requestPrompt)
      let examples = ResearchPracticeExamples.all
      let roster = ResearchGuidedWordSession.roster
      XCTAssertEqual(catalog.count, 15)
      XCTAssertEqual(examples.count, 13)
      for target in catalog {
        let text = try XCTUnwrap(
          ResearchPracticeFocus.cue(for: target, exampleAvailable: true), target.id)
        XCTAssertTrue(text.contains(target.word), target.id)
        XCTAssertFalse(text.isEmpty, target.id)
      }
      XCTAssertEqual(ResearchFeedbackCatalog.prompts, catalog)
      XCTAssertEqual(ResearchFeedbackCatalog.prompts.map(\.requestPrompt), requests)
      XCTAssertEqual(ResearchPracticeExamples.all, examples)
      XCTAssertEqual(ResearchGuidedWordSession.roster, roster)
      XCTAssertEqual(roster.count, 13)
      XCTAssertEqual(roster.first { $0.word == "baby" }?.prompt.id, "b-beginning-baby")
      XCTAssertEqual(roster.first { $0.word == "backpack" }?.prompt.id, "k-middle-backpack")
    }

    func testRepeatedBAndKTargetsKeepTheirSelectedOccurrencesDistinct() throws {
      let firstB = try cue("b-beginning-baby")
      let secondB = try cue("b-middle-baby")
      XCTAssertNotEqual(firstB, secondB)
      XCTAssertTrue(firstB.contains("first b"))
      XCTAssertTrue(firstB.contains("at the start"))
      XCTAssertTrue(secondB.contains("second b"))
      XCTAssertTrue(secondB.contains("in the middle"))
      let firstK = try cue("k-middle-backpack")
      let finalK = try cue("k-end-backpack")
      XCTAssertNotEqual(firstK, finalK)
      XCTAssertTrue(firstK.contains("first k sound in backpack"))
      XCTAssertTrue(firstK.contains("end of “back”"))
      XCTAssertTrue(finalK.contains("last k"))
      XCTAssertTrue(finalK.contains("at the very end"))
    }

    func testFirstNAndConsonantYKeepTheirWordAndAnchor() throws {
      XCTAssertTrue(try cue("n-middle-banana").contains("first n sound in banana"))
      let y = try cue("y-beginning-yo-yo")
      XCTAssertTrue(y.contains("first y sound in yo-yo"))
      XCTAssertTrue(y.contains("as in “yes”"))
    }

    func testDistinctTHAndDHAnchorsAndSingleNGAreSelectedContent() throws {
      let th = try cue("th-beginning-thumb")
      let dh = try cue("voiced-th-middle-feather")
      XCTAssertTrue(th.contains("start of thumb, as in “think”"))
      XCTAssertTrue(dh.contains("middle of feather, as in “this”"))
      XCTAssertFalse(th.contains("quiet"))
      XCTAssertFalse(dh.contains("buzzing"))
      let ng = try cue("ng-end-ring")
      XCTAssertTrue(ng.contains("ng sound at the end of ring"))
      XCTAssertTrue(ng.contains("one sound, without a separate g"))
    }

    func testUnsupportedTreasureStillHasNeutralManualFocus() throws {
      let treasure = try prompt("zh-middle-treasure")
      XCTAssertTrue(treasure.targetUnsupported)
      let text = try XCTUnwrap(
        ResearchPracticeFocus.cue(for: treasure, exampleAvailable: true))
      XCTAssertTrue(text.contains("middle sound in treasure, as in “measure”"))
      XCTAssertTrue(treasure.targetUnsupported)
    }

    func testFullIdentityMutationsCannotBorrowCanonicalTargetFocus() {
      for target in ResearchFeedbackCatalog.prompts {
        let mutations: [ResearchFeedbackPrompt] = [
          .init(id: "unknown", word: target.word, phones: target.phones,
            occurrenceIndex: target.occurrenceIndex, targetPhone: target.targetPhone),
          .init(id: target.id, word: target.word + "!", phones: target.phones,
            occurrenceIndex: target.occurrenceIndex, targetPhone: target.targetPhone),
          .init(id: target.id, word: target.word, phones: target.phones + ["AH"],
            occurrenceIndex: target.occurrenceIndex, targetPhone: target.targetPhone),
          .init(id: target.id, word: target.word, phones: target.phones,
            occurrenceIndex: target.occurrenceIndex + 1, targetPhone: target.targetPhone),
          .init(id: target.id, word: target.word, phones: target.phones,
            occurrenceIndex: target.occurrenceIndex, targetPhone: "UNKNOWN"),
        ]
        for mutation in mutations {
          for available in [true, false] {
            XCTAssertNil(
              ResearchPracticeFocus.cue(for: mutation, exampleAvailable: available), target.id)
          }
        }
      }
      XCTAssertNil(ResearchPracticeFocus.cue(for: nil, exampleAvailable: true))
      XCTAssertNil(ResearchPracticeFocus.cue(for: nil, exampleAvailable: false))
    }

    func testCanonicalIDWithAnotherRepeatedOccurrenceIsRefused() throws {
      for (id, otherIndex) in [("b-beginning-baby", 2), ("k-middle-backpack", 5)] {
        let target = try prompt(id)
        let other = ResearchFeedbackPrompt(
          id: id, word: target.word, phones: target.phones,
          occurrenceIndex: otherIndex, targetPhone: target.targetPhone)
        XCTAssertNil(ResearchPracticeFocus.cue(for: other, exampleAvailable: true))
      }
    }

    func testExampleAvailabilityChangesOnlyTheSharedAction() throws {
      let availableAction =
        "Listen to the whole example, say the whole word, then play your own try."
      let missingAction = "Say the whole word, then replay your try and listen for that sound."
      for target in ResearchFeedbackCatalog.prompts {
        let available = try XCTUnwrap(
          ResearchPracticeFocus.cue(for: target, exampleAvailable: true))
        let missing = try XCTUnwrap(
          ResearchPracticeFocus.cue(for: target, exampleAvailable: false))
        XCTAssertTrue(available.hasSuffix(availableAction), target.id)
        XCTAssertTrue(missing.hasSuffix(missingAction), target.id)
        XCTAssertEqual(
          available.dropLast(availableAction.count), missing.dropLast(missingAction.count), target.id)
      }
    }
  }
#endif
