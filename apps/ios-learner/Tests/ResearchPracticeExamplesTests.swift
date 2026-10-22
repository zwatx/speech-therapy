#if DEBUG && targetEnvironment(simulator)
  import XCTest
  @testable import CadenceLearner

  final class ResearchPracticeExamplesTests: XCTestCase {
    func testClosedFifteenPromptsThirteenAssetsWithUnknownAgesAndCredits() throws {
      XCTAssertEqual(
        ResearchPracticeExamples.registrySha256,
        "01de20fb2759fc7605bcf20322749a9405961ce5f33f20acbbe73508f2e61564")
      XCTAssertEqual(ResearchPracticeExamples.all.count, 13)
      XCTAssertEqual(Set(ResearchPracticeExamples.all.map(\.sourceWord)).count, 13)
      XCTAssertEqual(ResearchFeedbackCatalog.prompts.count, 15)
      for prompt in ResearchFeedbackCatalog.prompts {
        let example = try XCTUnwrap(ResearchPracticeExamples.example(for: prompt))
        XCTAssertFalse(example.speakerAgeKnown)
        XCTAssertFalse(example.clinicalReferenceApproved)
        XCTAssertFalse(example.isGeneratedFixture)
        XCTAssertFalse(example.author.isEmpty)
        XCTAssertFalse(example.attribution.isEmpty)
        XCTAssertEqual(example.wavSha256.count, 64)
        XCTAssertEqual(example.licenseURL.scheme, "https")
        XCTAssertEqual(example.sourceURL.scheme, "https")
        XCTAssertFalse(example.declaredVariety.isEmpty)
      }
    }
    func testSourceWordMappingsAndSharedExamplesDoNotChangeRequestPrompts() throws {
      let prompts = ResearchFeedbackCatalog.prompts
      XCTAssertEqual(
        ResearchPracticeExamples.example(for: prompts[3]),
        ResearchPracticeExamples.example(for: prompts[4]))
      XCTAssertEqual(
        ResearchPracticeExamples.example(for: prompts[6]),
        ResearchPracticeExamples.example(for: prompts[7]))
      XCTAssertEqual(ResearchPracticeExamples.example(for: prompts[10])?.sourceWord, "yoyo")
      XCTAssertEqual(prompts[10].requestPrompt.transcript, "yo-yo")
      XCTAssertTrue(prompts[14].targetUnsupported)
      XCTAssertEqual(ResearchPracticeExamples.example(for: prompts[14])?.sourceWord, "treasure")
    }
    func testFullCanonicalBreadOnlyHasListeningCueAndSpoofedPromptIsRejected() throws {
      let bread = try XCTUnwrap(ResearchFeedbackCatalog.prompts.first { $0.id == "r-middle-bread" })
      let example = try XCTUnwrap(ResearchPracticeExamples.example(for: bread))
      XCTAssertNotNil(example.listeningCue)
      XCTAssertEqual(example.sourceWord, "bread")
      XCTAssertEqual(
        example.wavSha256, "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f")
      XCTAssertEqual(example.sampleCount, 8917)
      XCTAssertEqual(example.author, "Dvortygirl")
      XCTAssertEqual(example.licenseId, "CC-BY-SA-3.0")
      XCTAssertEqual(ResearchPracticeExamples.all.filter { $0.listeningCue != nil }.count, 1)
      XCTAssertNil(
        ResearchPracticeExamples.example(
          for: .init(
            id: bread.id, word: "bread", phones: ["B", "W", "EH", "D"], occurrenceIndex: 1,
            targetPhone: "R")))
    }
  }
#endif
