import Foundation
import XCTest

@testable import CadenceLearner

final class DirectPracticeInstructionTests: XCTestCase {
  func testDefaultTargetsReuseTheirExistingInstruction() throws {
    var instructions = Set<String>()
    for id in ["b-beginning-ball", "p-beginning-pig", "m-beginning-moon",
               "t-beginning-tiger", "d-beginning-dog"] {
      let (sound, prompt) = try target(id)
      let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt))
      let instruction = try XCTUnwrap(DirectPracticeInstruction.text(
        sound: sound, prompt: prompt, visit: practiceVisit(prompt.id)))
      XCTAssertEqual(instruction, guide.detail, id)
      XCTAssertTrue(instruction.contains("“\(prompt.word)”"), id)
      XCTAssertEqual(sound.prompts, [prompt], "Prepared sessions may contain only one canonical word.")
      instructions.insert(instruction)
    }
    XCTAssertEqual(instructions.count, 5, "Each default target keeps its distinct existing guidance.")
  }

  func testRBeginningAndBRKeepExactSelectedTarget() throws {
    let cases: [(String, DirectPracticeSoundGuide.Kind)] = [
      ("r-beginning-rhino", .r), ("r-middle-bread", .br), ("b-beginning-bread", .b),
    ]
    var breadInstructions: [String: String] = [:]
    for (id, kind) in cases {
      let (sound, prompt) = try target(id)
      let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt))
      XCTAssertEqual(guide.kind, kind, id)
      let instruction = try XCTUnwrap(DirectPracticeInstruction.text(
        sound: sound, prompt: prompt, visit: practiceVisit(prompt.id)))
      XCTAssertEqual(instruction, guide.detail, id)
      if prompt.word == "bread" { breadInstructions[sound.id] = instruction }
      if kind == .br {
        XCTAssertEqual(sound.id, "r")
        XCTAssertEqual(sound.symbol, "ɹ")
        XCTAssertEqual(sound.position, .middle)
        XCTAssertTrue(instruction.contains("move straight into R"))
      }
    }
    XCTAssertNotEqual(try XCTUnwrap(breadInstructions["r"]), try XCTUnwrap(breadInstructions["b"]),
      "The same printed word must retain its selected sound and position.")
  }

  func testUnsupportedCanonicalTargetHasNeutralWholeWordInstruction() throws {
    let (sound, prompt) = try target("k-beginning-key")
    XCTAssertNil(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt))
    XCTAssertEqual(DirectPracticeInstruction.text(
      sound: sound, prompt: prompt, visit: practiceVisit(prompt.id)),
      "Say “key” as one whole word. Record a try, then play it back.")
  }

  func testReviewOrMissingVisitHasNoInstruction() throws {
    let (sound, prompt) = try target("p-beginning-pig")
    XCTAssertNil(DirectPracticeInstruction.text(sound: sound, prompt: prompt, visit: nil))
    let review = LocalGuidedReviewVisit(
      workflowID: UUID(), roundID: UUID(), visitID: UUID(), entryID: prompt.id)
    XCTAssertNil(DirectPracticeInstruction.text(sound: sound, prompt: prompt, visit: .review(review)))
  }

  func testMismatchedPracticeEntryHasNoInstruction() throws {
    for (id, otherID) in [
      ("p-beginning-pig", "p-beginning-pear"),
      ("r-middle-bread", "b-beginning-bread"),
    ] {
      let (sound, prompt) = try target(id)
      XCTAssertNil(DirectPracticeInstruction.text(
        sound: sound, prompt: prompt, visit: practiceVisit(otherID)), id)
      XCTAssertNil(DirectPracticeInstruction.text(
        sound: sound, prompt: prompt, visit: practiceVisit("missing-entry")), id)
    }
  }

  func testForgedPromptSymbolOrPositionHasNoInstruction() throws {
    // Exercise both the supported and fallback paths: neither may bypass canonical equality.
    for id in ["p-beginning-pig", "k-beginning-key"] {
      let (sound, original) = try target(id)
      let corruptions: [PracticePrompt] = [
        .init(id: "forged", word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: "forged", systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: "forged",
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: ["W"], pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: [],
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants + [["W"]],
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: "unverified", sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: "forged"),
      ]
      for prompt in corruptions {
        let visit = practiceVisit(prompt.id)
        XCTAssertNil(DirectPracticeInstruction.text(sound: sound, prompt: prompt, visit: visit), id)
        let altered = PracticeSound(id: sound.id, symbol: sound.symbol, name: sound.name,
          position: sound.position, prompts: [prompt])
        XCTAssertNil(DirectPracticeInstruction.text(sound: altered, prompt: prompt, visit: visit),
          "Even matching altered session metadata must not authorize an instruction: \(id)")
      }
      for altered in [
        PracticeSound(id: "unknown", symbol: sound.symbol, name: sound.name,
          position: sound.position, prompts: [original]),
        PracticeSound(id: sound.id, symbol: "forged", name: sound.name,
          position: sound.position, prompts: [original]),
        PracticeSound(id: sound.id, symbol: sound.symbol, name: sound.name,
          position: .middle, prompts: [original]),
        PracticeSound(id: sound.id, symbol: sound.symbol, name: sound.name,
          position: .end, prompts: [original]),
        PracticeSound(id: sound.id, symbol: sound.symbol, name: sound.name,
          position: sound.position, prompts: []),
      ] {
        XCTAssertNil(DirectPracticeInstruction.text(
          sound: altered, prompt: original, visit: practiceVisit(original.id)), id)
      }
    }
  }

  func testChangingWordsRecomputesInstructionWithoutPreviousWord() throws {
    for (firstID, nextID) in [
      ("b-beginning-ball", "b-beginning-boat"), ("p-beginning-pig", "p-beginning-pear"),
      ("m-beginning-moon", "m-beginning-mouse"), ("t-beginning-tiger", "t-beginning-toe"),
      ("d-beginning-dog", "d-beginning-duck"),
    ] {
      let (firstSound, firstPrompt) = try target(firstID)
      let first = try XCTUnwrap(DirectPracticeInstruction.text(
        sound: firstSound, prompt: firstPrompt, visit: practiceVisit(firstPrompt.id)))
      let (nextSound, nextPrompt) = try target(nextID)
      let next = try XCTUnwrap(DirectPracticeInstruction.text(
        sound: nextSound, prompt: nextPrompt, visit: practiceVisit(nextPrompt.id)))
      let nextGuide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: nextSound, prompt: nextPrompt))
      XCTAssertNotEqual(first, next, nextID)
      XCTAssertEqual(next, nextGuide.detail, nextID)
      XCTAssertTrue(next.contains("“\(nextPrompt.word)”"), nextID)
      XCTAssertFalse(next.contains("“\(firstPrompt.word)”"), nextID)
    }
  }

  private func target(_ id: String) throws -> (PracticeSound, PracticePrompt) {
    let entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == id })
    let sound = try XCTUnwrap(PracticeLibrary.session(
      soundID: entry.soundID, position: entry.position, startingAt: entry.id, limit: 1))
    return (sound, entry.prompt)
  }

  private func practiceVisit(_ entryID: String) -> GuidedMediaVisit {
    .practice(.init(workflowID: UUID(), practiceID: UUID(), visitID: UUID(), entryID: entryID))
  }
}
