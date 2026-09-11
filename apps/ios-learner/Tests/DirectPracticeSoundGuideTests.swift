import XCTest

@testable import CadenceLearner

final class DirectPracticeSoundGuideTests: XCTestCase {
  func testEveryCanonicalBeginningBUsesCurrentWordWithoutStaleStarterCopy() throws {
    let entries = PracticeLibrary.entries().filter {
      $0.soundID == "b" && $0.position == .beginning
    }
    XCTAssertTrue(Set(entries.map { $0.prompt.word }).isSuperset(of: ["ball", "boat", "bee"]))
    var details = Set<String>()
    for entry in entries {
      let sound = try XCTUnwrap(PracticeLibrary.session(
        soundID: entry.soundID, position: entry.position, startingAt: entry.id))
      let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: sound, prompt: entry.prompt))
      XCTAssertEqual(guide.title, "B at the start of “\(entry.prompt.word)”")
      XCTAssertEqual(guide.detail,
        "Bring your lips together, then open them as you say “\(entry.prompt.word)”. Use your usual voice.")
      details.insert(guide.detail)
    }
    XCTAssertEqual(details.count, entries.count, "Changing the word must change the learner's example.")
  }

  func testUnsupportedTargetsAndMismatchedCanonicalPromptHaveNoGuide() throws {
    let b = try XCTUnwrap(PracticeLibrary.session(soundID: "b", position: .beginning))
    let ball = try XCTUnwrap(b.prompts.first)
    for entry in PracticeLibrary.entries().filter({
      $0.soundID == "k" || ($0.soundID == "b" && $0.position != .beginning)
    }) {
      let sound = try XCTUnwrap(PracticeLibrary.session(
        soundID: entry.soundID, position: entry.position, startingAt: entry.id))
      XCTAssertNil(DirectPracticeSoundGuide.content(sound: sound, prompt: entry.prompt), entry.id)
      XCTAssertNil(DirectPracticeSoundGuide.content(sound: b, prompt: entry.prompt), entry.id)
    }
    for sound in [
      PracticeSound(id: "unknown", symbol: "b", name: "Unknown", position: .beginning, prompts: [ball]),
      PracticeSound(id: "b", symbol: "p", name: b.name, position: .beginning, prompts: [ball]),
    ] {
      XCTAssertNil(DirectPracticeSoundGuide.content(sound: sound, prompt: ball))
    }
    XCTAssertNil(DirectPracticeSoundGuide.content(sound: b, prompt: .init(
      id: "unknown-ball", word: ball.word, systemImage: ball.systemImage, phones: ball.phones)))
  }

  func testEveryCanonicalInitialPMTDUsesDistinctCurrentWordCopy() throws {
    let kinds: [String: DirectPracticeSoundGuide.Kind] = ["p": .p, "m": .m, "t": .t, "d": .d]
    for soundID in ["p", "m", "t", "d"] {
      let entries = PracticeLibrary.entries(soundID: soundID, position: .beginning)
      XCTAssertGreaterThan(entries.count, 3, "Cover the full catalog, including nonstarter words.")
      var details = Set<String>()
      for entry in entries {
        XCTAssertEqual(entry.prompt.phones.first, soundID.uppercased(), entry.id)
        XCTAssertFalse(entry.prompt.pronunciationVariants.isEmpty, entry.id)
        XCTAssertTrue(entry.prompt.pronunciationVariants.allSatisfy {
          $0.first == soundID.uppercased()
        }, entry.id)
        let sound = try XCTUnwrap(PracticeLibrary.session(
          soundID: soundID, position: .beginning, startingAt: entry.id))
        let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: sound, prompt: entry.prompt))
        XCTAssertEqual(guide.kind, kinds[soundID], entry.id)
        XCTAssertEqual(guide.word, entry.prompt.word)
        XCTAssertEqual(guide.title, "\(soundID.uppercased()) at the start of “\(entry.prompt.word)”")
        XCTAssertEqual(guide.detail, initialGuideDetail(soundID: soundID, word: entry.prompt.word))
        details.insert(guide.detail)
      }
      XCTAssertEqual(details.count, entries.count, "Every word must supply its own example.")
    }
  }

  func testAllFiveDefaultReviewWordsHaveGuides() throws {
    let defaultWords = ["ball", "pig", "moon", "tiger", "dog"]
    for (sound, word) in zip(PracticeLibrary.sounds.prefix(5), defaultWords) {
      let prompt = try XCTUnwrap(sound.prompts.first)
      XCTAssertEqual(prompt.word, word)
      let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt))
      XCTAssertEqual(guide.word, word)
      XCTAssertEqual(guide.title, "\(sound.id.uppercased()) at the start of “\(word)”")
    }
  }

  func testPMTDRejectForgedMetadataVariantsSoundSymbolPositionAndSession() throws {
    for soundID in ["p", "m", "t", "d"] {
      let sound = try XCTUnwrap(PracticeLibrary.session(soundID: soundID, position: .beginning))
      let original = try XCTUnwrap(sound.prompts.first)
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
          phones: ["K"], pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: [],
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants + [["K"]],
          pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: "unverified", sourceWord: original.sourceWord),
        .init(id: original.id, word: original.word, systemImage: original.systemImage,
          phones: original.phones, pronunciationVariants: original.pronunciationVariants,
          pronunciationSource: original.pronunciationSource, sourceWord: "forged"),
      ]
      for prompt in corruptions {
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt), soundID)
        let altered = PracticeSound(id: sound.id, symbol: sound.symbol, name: sound.name,
          position: sound.position, prompts: [prompt])
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: altered, prompt: prompt),
          "Matching a forged session copy cannot replace canonical equality: \(soundID)")
      }
      for altered in [
        PracticeSound(id: "unknown", symbol: sound.symbol, name: sound.name,
          position: .beginning, prompts: [original]),
        PracticeSound(id: soundID, symbol: "k", name: sound.name,
          position: .beginning, prompts: [original]),
        PracticeSound(id: soundID, symbol: sound.symbol, name: sound.name,
          position: .middle, prompts: [original]),
        PracticeSound(id: soundID, symbol: sound.symbol, name: sound.name,
          position: .end, prompts: [original]),
        PracticeSound(id: soundID, symbol: sound.symbol, name: sound.name,
          position: .beginning, prompts: Array(sound.prompts.dropFirst())),
      ] {
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: altered, prompt: original), soundID)
      }
      for entry in PracticeLibrary.entries(soundID: soundID) where entry.position != .beginning {
        let otherPosition = try XCTUnwrap(PracticeLibrary.session(
          soundID: soundID, position: entry.position, startingAt: entry.id))
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: otherPosition, prompt: entry.prompt), entry.id)
      }
    }
  }

  private func initialGuideDetail(soundID: String, word: String) -> String {
    switch soundID {
    case "p":
      return "Bring your lips together, then let out a small puff of air as you start “\(word)”. Say the whole word comfortably."
    case "m":
      return "Start “\(word)” with your lips together for a gentle “mmm”, letting air flow through your nose. Continue with the rest of the word comfortably."
    case "t":
      return "Try touching the small ridge just behind your top front teeth with your tongue tip. Release a little air into “\(word)”. Say the whole word comfortably."
    case "d":
      return "Try touching the small ridge just behind your top front teeth with your tongue tip. Release your tongue and use your voice as you say “\(word)”. Keep it comfortable."
    default:
      XCTFail("Unexpected sound: \(soundID)")
      return ""
    }
  }

  func testCanonicalIDCannotAdmitCorruptedWordOrPronunciationMetadata() throws {
    let sound = try XCTUnwrap(PracticeLibrary.session(soundID: "b", position: .beginning))
    let original = try XCTUnwrap(sound.prompts.first)
    let corruptions: [PracticePrompt] = [
      .init(id: original.id, word: "pig", systemImage: original.systemImage, phones: original.phones,
        pronunciationVariants: original.pronunciationVariants,
        pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
      .init(id: original.id, word: original.word, systemImage: original.systemImage, phones: ["P"],
        pronunciationVariants: original.pronunciationVariants,
        pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
      .init(id: original.id, word: original.word, systemImage: original.systemImage,
        phones: original.phones, pronunciationVariants: [["P"]],
        pronunciationSource: original.pronunciationSource, sourceWord: original.sourceWord),
      .init(id: original.id, word: original.word, systemImage: original.systemImage,
        phones: original.phones, pronunciationVariants: original.pronunciationVariants,
        pronunciationSource: "unverified", sourceWord: original.sourceWord),
    ]
    for prompt in corruptions {
      XCTAssertNil(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt))
      let alteredSound = PracticeSound(id: sound.id, symbol: sound.symbol, name: sound.name,
        position: sound.position, prompts: [prompt])
      XCTAssertNil(DirectPracticeSoundGuide.content(sound: alteredSound, prompt: prompt),
        "Matching an altered session copy must not replace the canonical library check.")
    }
  }

  func testEveryCanonicalInitialRUsesPhonesIncludingRhino() throws {
    let entries = PracticeLibrary.entries(soundID: "r", position: .beginning)
    XCTAssertTrue(entries.contains { $0.prompt.word == "rhino" })
    for entry in entries {
      XCTAssertEqual(entry.prompt.phones.first, "R", entry.id)
      XCTAssertFalse(entry.prompt.pronunciationVariants.isEmpty, entry.id)
      XCTAssertTrue(entry.prompt.pronunciationVariants.allSatisfy { $0.first == "R" }, entry.id)
      let sound = try XCTUnwrap(PracticeLibrary.session(
        soundID: "r", position: .beginning, startingAt: entry.id))
      let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: sound, prompt: entry.prompt))
      XCTAssertEqual(guide.kind, .r, entry.id)
      XCTAssertEqual(guide.title, "R at the start of “\(entry.prompt.word)”")
      XCTAssertEqual(guide.detail, "Say “\(entry.prompt.word)” as one whole word.")
    }
  }

  func testEveryCanonicalBRPrefixUsesBlendWhileOtherRContextsStayUnsupported() throws {
    var blendWords = Set<String>()
    for entry in PracticeLibrary.entries(soundID: "r") where entry.position != .beginning {
      let sound = try XCTUnwrap(PracticeLibrary.session(
        soundID: "r", position: entry.position, startingAt: entry.id))
      let guide = DirectPracticeSoundGuide.content(sound: sound, prompt: entry.prompt)
      if entry.position == .middle && Array(entry.prompt.phones.prefix(2)) == ["B", "R"] {
        blendWords.insert(entry.prompt.word)
        XCTAssertFalse(entry.prompt.pronunciationVariants.isEmpty, entry.id)
        XCTAssertTrue(entry.prompt.pronunciationVariants.allSatisfy {
          Array($0.prefix(2)) == ["B", "R"]
        }, entry.id)
        XCTAssertEqual(try XCTUnwrap(guide).kind, .br, entry.id)
        XCTAssertEqual(guide?.title, "R in the BR of “\(entry.prompt.word)”")
        XCTAssertEqual(guide?.detail,
          "Start with your lips together for B, then move straight into R as you say “\(entry.prompt.word)”. Keep the sounds together in one whole word.")
        if entry.prompt.word == "broccoli" {
          XCTAssertGreaterThan(entry.prompt.pronunciationVariants.count, 1)
        }
      } else {
        XCTAssertNil(guide, entry.id)
      }
    }
    XCTAssertTrue(blendWords.isSuperset(of: ["bread", "broccoli"]))
    let b = try XCTUnwrap(PracticeLibrary.session(
      soundID: "b", position: .beginning, startingAt: "b-beginning-bread"))
    let bread = try XCTUnwrap(b.prompts.first)
    let guide = try XCTUnwrap(DirectPracticeSoundGuide.content(sound: b, prompt: bread))
    XCTAssertEqual(guide.kind, .b)
    XCTAssertEqual(guide.title, "B at the start of “bread”")
    XCTAssertEqual(guide.detail,
      "Bring your lips together, then open them as you say “bread”. Use your usual voice.")
  }

  func testRRejectsForgedMetadataVariantsSessionSymbolAndPosition() throws {
    for (position, id) in [(PracticeTargetPosition.beginning, "r-beginning-rhino"),
                           (.middle, "r-middle-broccoli")] {
      let sound = try XCTUnwrap(PracticeLibrary.session(
        soundID: "r", position: position, startingAt: id))
      let original = try XCTUnwrap(sound.prompts.first)
      let corruptions: [PracticePrompt] = [
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
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: sound, prompt: prompt))
        let altered = PracticeSound(id: "r", symbol: "ɹ", name: sound.name,
          position: position, prompts: [prompt])
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: altered, prompt: prompt))
      }
      for altered in [
        PracticeSound(id: "r", symbol: "r", name: sound.name, position: position, prompts: [original]),
        PracticeSound(id: "w", symbol: "ɹ", name: sound.name, position: position, prompts: [original]),
        PracticeSound(id: "r", symbol: "ɹ", name: sound.name, position: position, prompts: []),
        PracticeSound(id: "r", symbol: "ɹ", name: sound.name, position: .end, prompts: [original]),
      ] {
        XCTAssertNil(DirectPracticeSoundGuide.content(sound: altered, prompt: original))
      }
    }
  }

}
