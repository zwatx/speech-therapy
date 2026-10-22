import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class PracticeParticipationStoreTests: XCTestCase {
  func testRepeatedSessionDoesNotReplaceOrDuplicateItsParticipation() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let store = PracticeParticipationStore(fileURL: file)
    let id = UUID()
    let completedAt = Date(timeIntervalSince1970: 1_700_000_000)
    try store.record(sessionID: id, completedAt: completedAt, soundID: "r", wordCount: 3)
    try store.record(
      sessionID: id, completedAt: completedAt.addingTimeInterval(100), soundID: "b", wordCount: 1)

    XCTAssertEqual(store.entries.count, 1)
    XCTAssertEqual(store.entries.first?.soundID, "r")
    XCTAssertEqual(store.entries.first?.completedAt, completedAt)
    XCTAssertEqual(PracticeParticipationStore(fileURL: file).entries, store.entries)
  }

  func testUnreadableHistoryIsRejectedAndPreservedUntilExplicitlyCleared() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let valid =
      "{\"id\":\"00000000-0000-0000-0000-000000000001\",\"completedAt\":1700000000,\"soundID\":\"r\",\"wordCount\":3}"
    let invalidDocuments = [
      "not json",
      "{\"schemaVersion\":2,\"entries\":[]}",
      "{\"schemaVersion\":1,\"entries\":[],\"audio\":\"private\"}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(of: "\"wordCount\":3", with: "\"wordCount\":0") + "]}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(of: "\"wordCount\":3", with: "\"wordCount\":4") + "]}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(of: "\"r\"", with: "\"unknown\"") + "]}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(of: "1700000000", with: "-1") + "]}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(of: "1700000000", with: "1e100") + "]}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(of: "\"wordCount\":3", with: "\"wordCount\":true") + "]}",
      "{\"schemaVersion\":1,\"entries\":["
        + valid.replacingOccurrences(
          of: "\"wordCount\":3", with: "\"wordCount\":3,\"name\":\"child\"") + "]}",
      "{\"schemaVersion\":1,\"entries\":[" + valid + "," + valid + "]}",
      String(repeating: " ", count: 128 * 1024) + "{\"schemaVersion\":1,\"entries\":[]}",
    ]
    for document in invalidDocuments {
      let data = Data(document.utf8)
      try data.write(to: file)
      let store = PracticeParticipationStore(fileURL: file)
      XCTAssertNotNil(store.loadError, document.prefix(100).description)
      XCTAssertTrue(store.entries.isEmpty)
      XCTAssertThrowsError(
        try store.record(sessionID: UUID(), completedAt: Date(), soundID: "r", wordCount: 1))
      XCTAssertEqual(try Data(contentsOf: file), data)
    }
  }

  func testClearRecoversUnreadableHistoryOnlyAfterSuccessfulWrite() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    try Data("unreadable".utf8).write(to: file)
    let store = PracticeParticipationStore(fileURL: file)
    try FileManager.default.removeItem(at: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: false)

    XCTAssertThrowsError(try store.clear())
    XCTAssertNotNil(store.loadError)
    try FileManager.default.removeItem(at: file)
    try store.clear()
    XCTAssertNil(store.loadError)
    XCTAssertTrue(PracticeParticipationStore(fileURL: file).entries.isEmpty)
    XCTAssertNil(PracticeParticipationStore(fileURL: file).loadError)
    try store.record(sessionID: UUID(), completedAt: Date(), soundID: "b", wordCount: 1)
    try store.clear()
    XCTAssertTrue(store.entries.isEmpty)
    XCTAssertTrue(PracticeParticipationStore(fileURL: file).entries.isEmpty)
  }

  func testHistoryKeepsOnlyNewestHundredSessionsWithDeterministicTies() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let store = PracticeParticipationStore(fileURL: file)
    let firstTie = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
    let secondTie = UUID(uuidString: "00000000-0000-0000-0000-000000000002")!
    let date = Date(timeIntervalSince1970: 1_700_000_000)
    try store.record(sessionID: secondTie, completedAt: date, soundID: "b", wordCount: 1)
    try store.record(sessionID: firstTie, completedAt: date, soundID: "b", wordCount: 2)
    for index in (1...99).reversed() {
      try store.record(
        sessionID: UUID(), completedAt: date.addingTimeInterval(Double(index)), soundID: "r",
        wordCount: 3)
    }

    XCTAssertEqual(store.entries.count, 100)
    XCTAssertEqual(store.entries.first?.completedAt, date.addingTimeInterval(99))
    XCTAssertEqual(store.entries.last?.id, firstTie)
    XCTAssertFalse(store.entries.contains(where: { $0.id == secondTie }))
    let reopened = PracticeParticipationStore(fileURL: file)
    XCTAssertEqual(reopened.entries, store.entries)
  }

  func testInvalidRecordInputCannotChangeSavedHistory() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let store = PracticeParticipationStore(fileURL: file)
    try store.record(sessionID: UUID(), completedAt: Date(), soundID: "b", wordCount: 1)
    let saved = store.entries
    let savedData = try Data(contentsOf: file)
    let invalidInputs: [(Date, String, Int)] = [
      (Date(), "", 1), (Date(), "unknown", 1), (Date(), "r", 0), (Date(), "r", 4),
      (Date(timeIntervalSince1970: -1), "r", 1),
      (Date(timeIntervalSince1970: .nan), "r", 1),
      (Date(timeIntervalSince1970: .infinity), "r", 1),
    ]
    for (date, soundID, count) in invalidInputs {
      XCTAssertThrowsError(
        try store.record(sessionID: UUID(), completedAt: date, soundID: soundID, wordCount: count))
      XCTAssertEqual(store.entries, saved)
      XCTAssertEqual(try Data(contentsOf: file), savedData)
    }
  }

  func testWriteFailurePreservesPreviouslyVisibleEntriesAndClearDoesNotClaimSuccess() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let store = PracticeParticipationStore(fileURL: file)
    try store.record(sessionID: UUID(), completedAt: Date(), soundID: "b", wordCount: 2)
    let saved = store.entries
    try FileManager.default.removeItem(at: file)
    try FileManager.default.createDirectory(at: file, withIntermediateDirectories: false)

    XCTAssertThrowsError(
      try store.record(sessionID: UUID(), completedAt: Date(), soundID: "r", wordCount: 1))
    XCTAssertEqual(store.entries, saved)
    XCTAssertThrowsError(try store.clear())
    XCTAssertEqual(store.entries, saved)
  }

  func testSavedParticipationExcludesItsOwnDirectoryFromBackup() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let store = PracticeParticipationStore(fileURL: file)
    try store.record(sessionID: UUID(), completedAt: Date(), soundID: "r", wordCount: 1)

    #if !targetEnvironment(simulator)
      // The simulator does not expose iOS data-protection metadata.
      let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
      XCTAssertEqual(
        String(describing: attributes[.protectionKey]!), FileProtectionType.complete.rawValue)
    #endif
    XCTAssertEqual(
      try directory.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
  }

  func testCompletedPracticePersistsAcrossStoreInstancesWithoutAudio() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("participation.json")
    let store = PracticeParticipationStore(fileURL: file)
    let id = UUID()
    let date = Date(timeIntervalSince1970: 1_700_000_000)

    try store.record(sessionID: id, completedAt: date, soundID: "r", wordCount: 3)

    let reopened = PracticeParticipationStore(fileURL: file)
    XCTAssertEqual(reopened.entries.count, 1)
    XCTAssertEqual(reopened.entries.first?.id, id)
    XCTAssertEqual(reopened.entries.first?.completedAt, date)
    XCTAssertEqual(reopened.entries.first?.wordCount, 3)
    let document = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
    XCTAssertEqual(Set(document.keys), ["schemaVersion", "entries"])
    let entries = try XCTUnwrap(document["entries"] as? [[String: Any]])
    XCTAssertEqual(
      Set(try XCTUnwrap(entries.first).keys), ["id", "completedAt", "soundID", "wordCount"])
  }
}
