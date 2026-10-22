import UIKit
import XCTest

@testable import CadenceLearner

final class PracticeLibraryTests: XCTestCase {
  func testSoundAndPromptIdentifiersAreUniqueAndEveryStarterSessionHasThreeWords() {
    let sounds = PracticeLibrary.sounds
    let prompts = sounds.flatMap(\.prompts)
    XCTAssertEqual(sounds.count, 24)
    XCTAssertEqual(Set(sounds.map(\.id)).count, sounds.count)
    XCTAssertEqual(Set(prompts.map(\.id)).count, prompts.count)
    XCTAssertTrue(sounds.allSatisfy { $0.prompts.count == 3 })
    XCTAssertTrue(prompts.allSatisfy { !$0.word.isEmpty && !$0.systemImage.isEmpty })
  }

  func testOriginalStartersAndDefaultPositionsRemainStable() {
    let expected = [
      ["ball", "boat", "bee"], ["pig", "pear", "pie"], ["moon", "mouse", "milk"],
      ["tiger", "toe", "tent"], ["dog", "duck", "door"], ["nest", "nose", "net"],
      ["cat", "key", "kite"], ["goat", "gate", "gum"], ["fish", "fan", "feet"],
      ["van", "vase", "vest"], ["sun", "sock", "soap"], ["zebra", "zipper", "zoo"],
      ["ship", "shoe", "shell"], ["chair", "cheese", "chick"], ["juice", "jam", "jacket"],
      ["leaf", "lion", "lamp"], ["rabbit", "rain", "ring"], ["web", "wing", "wagon"],
      ["yarn", "yo-yo", "yogurt"], ["hat", "horse", "house"], ["thumb", "thorn", "thread"],
      ["feather", "weather", "mother"], ["ring", "wing", "king"],
      ["treasure", "measure", "television"],
    ]
    XCTAssertEqual(PracticeLibrary.sounds.map { $0.prompts.map(\.word) }, expected)
    for (index, sound) in PracticeLibrary.sounds.enumerated() {
      let expectedPosition: PracticeTargetPosition =
        index == 22 ? .end : index == 21 || index == 23 ? .middle : .beginning
      XCTAssertEqual(sound.position, expectedPosition)
      let entries = PracticeLibrary.entries(soundID: sound.id, position: sound.position)
      XCTAssertEqual(Array(entries.prefix(3).map(\.prompt)), sound.prompts)
      XCTAssertEqual(PracticeLibrary.session(soundID: sound.id, position: sound.position), sound)
    }
    XCTAssertEqual(PracticeLibrary.starterSound.id, "b")
  }

  func testExpandedCatalogHasStableUniqueEntriesAcrossAllSounds() {
    let entries = PracticeLibrary.entries()
    XCTAssertGreaterThanOrEqual(PracticeLibrary.wordCount, 500)
    XCTAssertGreaterThanOrEqual(PracticeLibrary.entryCount, 1_000)
    XCTAssertEqual(entries.count, PracticeLibrary.entryCount)
    XCTAssertEqual(Set(entries.map { $0.prompt.word }).count, PracticeLibrary.wordCount)
    XCTAssertEqual(Set(entries.map(\.id)).count, entries.count)
    XCTAssertEqual(Set(entries.map(\.soundID)), Set(PracticeLibrary.sounds.map(\.id)))
    XCTAssertEqual(entries, PracticeLibrary.entries())
    for entry in entries {
      XCTAssertEqual(entry.id, "\(entry.soundID)-\(entry.position.rawValue)-\(entry.prompt.word)")
    }
    for sound in PracticeLibrary.sounds {
      for position in PracticeTargetPosition.allCases {
        let matching = PracticeLibrary.entries(soundID: sound.id, position: position)
        XCTAssertEqual(Set(matching.map { $0.prompt.word }).count, matching.count)
        let starters = position == sound.position ? sound.prompts.map(\.word) : []
        let remaining = matching.map { $0.prompt.word }.filter { !starters.contains($0) }
        XCTAssertEqual(remaining, remaining.sorted())
      }
    }
  }

  func testEveryAdvertisedTargetOccursAtItsPositionInEverySourcePronunciation() {
    let expectedPhones = [
      "B", "P", "M", "T", "D", "N", "K", "G", "F", "V", "S", "Z",
      "SH", "CH", "JH", "L", "R", "W", "Y", "HH", "TH", "DH", "NG", "ZH",
    ]
    for (sound, phone) in zip(PracticeLibrary.sounds, expectedPhones) {
      for entry in PracticeLibrary.entries(soundID: sound.id) {
        XCTAssertEqual(entry.targetPhone, phone)
        XCTAssertFalse(entry.prompt.pronunciationVariants.isEmpty, entry.id)
        XCTAssertEqual(entry.prompt.phones, entry.prompt.pronunciationVariants.first, entry.id)
        XCTAssertEqual(
          entry.prompt.pronunciationSource,
          "cmudict:74790861f652b15e4ac49015a90074ad62a27690", entry.id)
        for phones in entry.prompt.pronunciationVariants {
          let containsTarget: Bool
          switch entry.position {
          case .beginning:
            containsTarget = phones.first == phone
          case .middle:
            containsTarget = phones.dropFirst().dropLast().contains(phone)
          case .end:
            containsTarget = phones.last == phone
          }
          XCTAssertTrue(containsTarget, "\(entry.id): \(phones)")
        }
      }
    }
  }

  func testTargetsThatVaryByPronunciationAreExcluded() throws {
    let vase = try XCTUnwrap(
      PracticeLibrary.entries(soundID: "v", position: .beginning).first {
        $0.prompt.word == "vase"
      })
    XCTAssertEqual(vase.prompt.pronunciationVariants, [["V", "EY", "S"], ["V", "AA", "Z"]])
    for soundID in ["s", "z"] {
      let endWords = PracticeLibrary.entries(soundID: soundID, position: .end).map {
        $0.prompt.word
      }
      XCTAssertFalse(endWords.contains("vase"))
      XCTAssertFalse(endWords.contains("close"))
    }
    // "usual" has W in only one source variant; ZH is stable in both.
    XCTAssertFalse(PracticeLibrary.entries(soundID: "w").contains { $0.prompt.word == "usual" })
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "zh", position: .middle).contains {
        $0.prompt.word == "usual"
      })
  }

  func testPhoneBasedPositionsHandleClustersAndConsonantalR() {
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "k", position: .middle).contains {
        $0.prompt.word == "sky"
      })
    XCTAssertFalse(
      PracticeLibrary.entries(soundID: "k", position: .beginning).contains {
        $0.prompt.word == "sky"
      })
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "r", position: .middle).contains {
        $0.prompt.word == "bread"
      })
    XCTAssertFalse(PracticeLibrary.entries(soundID: "r").contains { $0.prompt.word == "bird" })
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "r", position: .end).contains {
        $0.prompt.word == "door"
      })
  }

  func testRareSoundsHaveVerifiedPositionsWithoutInventedOnsetsOrEndings() {
    XCTAssertTrue(PracticeLibrary.entries(soundID: "ng", position: .beginning).isEmpty)
    XCTAssertTrue(PracticeLibrary.entries(soundID: "zh", position: .beginning).isEmpty)
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "zh", position: .end).contains {
        $0.prompt.word == "garage"
      })
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "voiced-th", position: .beginning).contains {
        $0.prompt.word == "this"
      })
    XCTAssertTrue(
      PracticeLibrary.entries(soundID: "voiced-th", position: .end).contains {
        $0.prompt.word == "breathe"
      })
    for soundID in ["w", "y", "h"] {
      XCTAssertTrue(PracticeLibrary.entries(soundID: soundID, position: .end).isEmpty)
      XCTAssertNil(PracticeLibrary.session(soundID: soundID, position: .end))
    }
  }

  func testSearchNormalizesCaseDiacriticsAndSurroundingWhitespace() {
    let rain = PracticeLibrary.entries(query: "rain")
    XCTAssertFalse(rain.isEmpty)
    XCTAssertEqual(PracticeLibrary.entries(query: " \n RÁIN\t "), rain)
    XCTAssertEqual(PracticeLibrary.entries(query: "ra\u{0301}in"), rain)
    XCTAssertTrue(rain.contains { $0.prompt.word == "raincoat" })
    XCTAssertEqual(PracticeLibrary.entries(query: " \n\t "), PracticeLibrary.entries())
    let middle = PracticeLibrary.entries(soundID: "r", position: .middle, query: "AIR")
    XCTAssertFalse(middle.isEmpty)
    XCTAssertTrue(
      middle.allSatisfy {
        $0.soundID == "r" && $0.position == .middle && $0.prompt.word.contains("air")
      })
  }

  func testEmptyAndUnknownQueriesReturnNoMatchesOrSession() {
    XCTAssertTrue(PracticeLibrary.entries(query: "no-such-word-123").isEmpty)
    XCTAssertTrue(PracticeLibrary.entries(soundID: "unknown").isEmpty)
    XCTAssertNil(PracticeLibrary.session(soundID: "unknown", position: .beginning))
    XCTAssertNil(PracticeLibrary.session(soundID: "b", position: .beginning, query: "123"))
    XCTAssertNil(PracticeLibrary.session(soundID: "ng", position: .beginning))
  }

  func testSearchMatchesDisplayAndNonliteralSourceSpelling() throws {
    let displayed = PracticeLibrary.entries(query: "yo-yo")
    XCTAssertFalse(displayed.isEmpty)
    XCTAssertEqual(PracticeLibrary.entries(query: "yoyo"), displayed)
    XCTAssertEqual(PracticeLibrary.entries(query: "  YÓYO\n"), displayed)
    XCTAssertTrue(
      displayed.allSatisfy { $0.prompt.word == "yo-yo" && $0.prompt.sourceWord == "yoyo" })
    let session = try XCTUnwrap(
      PracticeLibrary.session(
        soundID: "y", position: .beginning, query: "yoyo"))
    XCTAssertEqual(session.prompts.map(\.word), ["yo-yo"])
  }

  func testSelectedSessionStartsAtExactWordAndContinuesForward() throws {
    let matching = PracticeLibrary.entries(soundID: "b", position: .beginning)
    let selected = matching[7]
    let session = try XCTUnwrap(
      PracticeLibrary.session(
        soundID: "b", position: .beginning, startingAt: selected.id))
    XCTAssertEqual(session.prompts.map(\.id), Array(matching[7..<10].map(\.id)))
    XCTAssertEqual(session.prompts.first, selected.prompt)
    XCTAssertEqual(Set(session.prompts.map(\.word)).count, session.prompts.count)
    let next = try XCTUnwrap(
      PracticeLibrary.nextEntryID(
        after: session.prompts[2].id, soundID: "b", position: .beginning))
    XCTAssertEqual(next, matching[10].id)
    XCTAssertEqual(
      PracticeLibrary.session(
        soundID: "b", position: .beginning, startingAt: next)?.prompts.first, matching[10].prompt)
  }

  func testSessionsAtTailHaveOneOrTwoWordsAndNeverWrapOrBackfill() throws {
    for sound in PracticeLibrary.sounds {
      for position in PracticeTargetPosition.allCases {
        let matching = PracticeLibrary.entries(soundID: sound.id, position: position)
        guard let last = matching.last else { continue }
        let session = try XCTUnwrap(
          PracticeLibrary.session(
            soundID: sound.id, position: position, startingAt: last.id))
        XCTAssertEqual(session.prompts, [last.prompt])
        XCTAssertNil(
          PracticeLibrary.nextEntryID(
            after: last.id, soundID: sound.id, position: position))
        if matching.count >= 2 {
          let penultimate = matching[matching.count - 2]
          XCTAssertEqual(
            PracticeLibrary.session(
              soundID: sound.id, position: position, startingAt: penultimate.id)?.prompts,
            [penultimate.prompt, last.prompt])
        }
      }
    }
  }

  func testSessionLimitsAndInvalidSelectedIDs() throws {
    let matching = PracticeLibrary.entries(soundID: "b", position: .beginning)
    XCTAssertNil(PracticeLibrary.session(soundID: "b", position: .beginning, limit: 0))
    XCTAssertNil(PracticeLibrary.session(soundID: "b", position: .beginning, limit: -1))
    XCTAssertEqual(
      PracticeLibrary.session(soundID: "b", position: .beginning, limit: 1)?.prompts,
      [matching[0].prompt])
    XCTAssertEqual(
      PracticeLibrary.session(soundID: "b", position: .beginning, limit: Int.max)?.prompts.count,
      3)
    XCTAssertNil(PracticeLibrary.session(soundID: "b", position: .beginning, startingAt: "unknown"))
    XCTAssertNil(PracticeLibrary.session(soundID: "b", position: .end, startingAt: matching[0].id))
    XCTAssertNil(
      PracticeLibrary.session(soundID: "p", position: .beginning, startingAt: matching[0].id))
    XCTAssertNil(
      PracticeLibrary.nextEntryID(after: matching[0].id, soundID: "p", position: .beginning))
    XCTAssertNil(PracticeLibrary.nextEntryID(after: "unknown", soundID: "b", position: .beginning))
    let filtered = PracticeLibrary.entries(soundID: "b", position: .beginning, query: "bal")
    let selected = try XCTUnwrap(filtered.last)
    XCTAssertEqual(
      PracticeLibrary.session(
        soundID: "b", position: .beginning, query: "bal", startingAt: selected.id)?.prompts,
      [selected.prompt])
    XCTAssertNil(
      PracticeLibrary.session(
        soundID: "b", position: .beginning, query: "bal", startingAt: matching[2].id))
  }

  func testHyphenatedStarterUsesRealSourceSpellingAndLicenseIsRetained() throws {
    let yoyo = try XCTUnwrap(
      PracticeLibrary.entries(soundID: "y", position: .beginning).first {
        $0.prompt.word == "yo-yo"
      })
    XCTAssertEqual(yoyo.prompt.sourceWord, "yoyo")
    XCTAssertEqual(yoyo.prompt.phones, ["Y", "OW", "Y", "OW"])
    XCTAssertTrue(PracticeLibrary.sourceNotice.contains("CMUdict"))
    XCTAssertTrue(
      PracticeLibrary.sourceLicense.contains("Copyright (C) 1993-2015 Carnegie Mellon University"))
    XCTAssertTrue(
      PracticeLibrary.sourceLicense.contains("Redistribution and use in source and binary forms"))
    XCTAssertTrue(PracticeLibrary.sourceLicense.contains("THIS SOFTWARE IS PROVIDED"))
  }

  func testEveryFallbackSymbolExists() {
    for prompt in PracticeLibrary.entries().map(\.prompt) {
      XCTAssertNotNil(UIImage(systemName: prompt.systemImage), prompt.id)
    }
  }
}
