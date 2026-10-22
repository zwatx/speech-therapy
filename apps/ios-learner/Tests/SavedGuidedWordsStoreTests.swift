import Foundation
import XCTest

@testable import CadenceLearner

@MainActor final class SavedGuidedWordsStoreTests: XCTestCase {
  private let first = [
    "b-beginning-baby", "k-middle-backpack", "r-middle-bread", "d-beginning-door",
    "s-beginning-sky",
  ]
  private func location() throws -> URL {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "saved-words-unit-\(UUID())")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: root) }
    return root.appendingPathComponent("words.json")
  }
  private func envelope(_ ids: [String], version: Int = 1) throws -> Data {
    try JSONSerialization.data(withJSONObject: ["schemaVersion": version, "entryIDs": ids])
  }
  func testMissingRoundTripAndReplacementPreserveExactCanonicalOrder() throws {
    let existingParentURL = try location()
    let missingParentURL = existingParentURL.deletingLastPathComponent()
      .appendingPathComponent("not-created", isDirectory: true).appendingPathComponent("words.json")
    for url in [existingParentURL, missingParentURL] {
      let store = SavedGuidedWordsStore(fileURL: url)
      XCTAssertNil(store.entryIDs)
      XCTAssertNil(store.loadError)
      try store.save(entryIDs: first)
      let saved = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
      XCTAssertEqual(Set(saved.keys), Set(["schemaVersion", "entryIDs"]))
      XCTAssertEqual(saved["schemaVersion"] as? Int, 1)
      XCTAssertEqual(saved["entryIDs"] as? [String], first)
      XCTAssertEqual(
        try url.deletingLastPathComponent().resourceValues(forKeys: [.isExcludedFromBackupKey])
          .isExcludedFromBackup, true)
      let loaded = SavedGuidedWordsStore(fileURL: url)
      XCTAssertEqual(loaded.entryIDs, first)
      XCTAssertNil(loaded.loadError)
      let expected = first.map { id in PracticeLibrary.entries().first { $0.id == id }! }
      XCTAssertEqual(loaded.entries?.map(\.id), expected.map(\.id))
      XCTAssertEqual(loaded.entries?.map(\.soundID), expected.map(\.soundID))
      XCTAssertEqual(loaded.entries?.map(\.position), expected.map(\.position))
      let reversed = Array(first.reversed())
      try loaded.save(entryIDs: reversed)
      XCTAssertEqual(SavedGuidedWordsStore(fileURL: url).entryIDs, reversed)
      try loaded.clear()
      XCTAssertNil(loaded.entryIDs)
      XCTAssertNil(SavedGuidedWordsStore(fileURL: url).entryIDs)
    }
  }
  func testExplicitEmptyEnvelopeIsReadableWithoutInventingASet() throws {
    let url = try location()
    try Data("{\"schemaVersion\":1,\"entryIDs\":null}".utf8).write(to: url)
    let store = SavedGuidedWordsStore(fileURL: url)
    XCTAssertNil(store.entryIDs)
    XCTAssertNil(store.entries)
    XCTAssertNil(store.loadError)
  }
  func testInvalidSavesPreservePreviousMemoryAndDisk() throws {
    let url = try location()
    let store = SavedGuidedWordsStore(fileURL: url)
    try store.save(entryIDs: first)
    let bytes = try Data(contentsOf: url)
    let catalog = PracticeLibrary.entries()
    let grouped = Dictionary(grouping: catalog) {
      $0.prompt.word.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
    let duplicateWord = try XCTUnwrap(grouped.values.first { $0.count > 1 })
    var sameWord = [duplicateWord[0].id, duplicateWord[1].id]
    var words = Set([duplicateWord[0].prompt.word.lowercased()])
    for entry in catalog where sameWord.count < 5 {
      if words.insert(entry.prompt.word.lowercased()).inserted { sameWord.append(entry.id) }
    }
    for invalid in [
      Array(first.prefix(4)), first + ["b-beginning-boat"], Array(repeating: first[0], count: 5),
      ["unknown"] + Array(first.dropFirst()), sameWord,
    ] {
      XCTAssertThrowsError(try store.save(entryIDs: invalid))
      XCTAssertEqual(store.entryIDs, first)
      XCTAssertEqual(try Data(contentsOf: url), bytes)
    }
  }
  func testUnreadableDocumentsRemainUntouchedAndBlockSaveUntilExplicitClear() throws {
    let variants: [Data] = [
      Data("not json".utf8), try envelope(first, version: 2),
      try JSONSerialization.data(withJSONObject: [
        "schemaVersion": 1, "entryIDs": first, "extra": true,
      ]),
      try envelope(Array(first.prefix(4))), try envelope(Array(repeating: first[0], count: 5)),
      try envelope(["unknown"] + Array(first.dropFirst())),
      Data("{\"schemaVersion\":1}".utf8), Data("{\"schemaVersion\":1.5,\"entryIDs\":null}".utf8),
      Data("{\"schemaVersion\":1.0,\"entryIDs\":null}".utf8),
      Data("{\"schemaVersion\":1e0,\"entryIDs\":null}".utf8),
      Data(repeating: 32, count: 8193), Data("{\"schemaVersion\":true,\"entryIDs\":null}".utf8),
    ]
    for bytes in variants {
      let url = try location()
      try bytes.write(to: url)
      let store = SavedGuidedWordsStore(fileURL: url)
      XCTAssertNotNil(store.loadError)
      XCTAssertNil(store.entryIDs)
      XCTAssertThrowsError(try store.save(entryIDs: first))
      XCTAssertEqual(try Data(contentsOf: url), bytes)
      try store.clear()
      XCTAssertNil(store.loadError)
      XCTAssertNil(store.entryIDs)
      try store.save(entryIDs: first)
      XCTAssertEqual(SavedGuidedWordsStore(fileURL: url).entryIDs, first)
    }
  }
  func testActualFilesystemFailurePreservesPreviousStateForSaveAndClear() throws {
    let url = try location()
    let store = SavedGuidedWordsStore(fileURL: url)
    try store.save(entryIDs: first)
    let backup = url.appendingPathExtension("backup")
    try FileManager.default.moveItem(at: url, to: backup)
    let priorBytes = try Data(contentsOf: backup)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false)
    XCTAssertThrowsError(try store.save(entryIDs: Array(first.reversed())))
    XCTAssertEqual(store.entryIDs, first)
    XCTAssertThrowsError(try store.clear())
    XCTAssertEqual(store.entryIDs, first)
    XCTAssertEqual(try Data(contentsOf: backup), priorBytes)
    XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: url.path), [])
  }
  func testDirectoryReadFailureIsVisibleAndCannotBeSilentlySaved() throws {
    let url = try location()
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false)
    let store = SavedGuidedWordsStore(fileURL: url)
    XCTAssertNotNil(store.loadError)
    XCTAssertNil(store.entryIDs)
    XCTAssertThrowsError(try store.save(entryIDs: first))
    XCTAssertThrowsError(try store.clear())
    XCTAssertNotNil(store.loadError)

    let fileParent = try location()
    let obstacle = Data("A file cannot be a saved-store parent directory".utf8)
    try obstacle.write(to: fileParent)
    let blocked = SavedGuidedWordsStore(fileURL: fileParent.appendingPathComponent("words.json"))
    XCTAssertNotNil(blocked.loadError)
    XCTAssertNil(blocked.entryIDs)
    XCTAssertThrowsError(try blocked.save(entryIDs: first))
    XCTAssertThrowsError(try blocked.clear())
    XCTAssertEqual(try Data(contentsOf: fileParent), obstacle)
  }
}
