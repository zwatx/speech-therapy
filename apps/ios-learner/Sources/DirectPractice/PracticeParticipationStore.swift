import Combine
import Foundation

struct PracticeParticipation: Codable, Equatable, Identifiable {
  let id: UUID
  let completedAt: Date
  let soundID: String
  let wordCount: Int
}

/// Device-local participation metadata. Never contains audio or pronunciation judgments.
@MainActor
final class PracticeParticipationStore: ObservableObject {
  static let capacity = 100
  static let shared = PracticeParticipationStore(
    fileURL: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent("PracticeParticipation", isDirectory: true)
      .appendingPathComponent("participation.json"))

  @Published private(set) var entries: [PracticeParticipation] = []
  @Published private(set) var loadError: String?
  private let fileURL: URL

  init(fileURL: URL) {
    self.fileURL = fileURL
    guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
    do {
      let decoder = JSONDecoder()
      decoder.dateDecodingStrategy = .secondsSince1970
      let handle = try FileHandle(forReadingFrom: fileURL)
      defer { try? handle.close() }
      let data = try handle.read(upToCount: 128 * 1024 + 1) ?? Data()
      guard data.count <= 128 * 1024,
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        Set(json.keys) == ["schemaVersion", "entries"],
        let rawEntries = json["entries"] as? [[String: Any]],
        rawEntries.allSatisfy({ Set($0.keys) == ["id", "completedAt", "soundID", "wordCount"] })
      else { throw StoreError.unreadable }
      let document = try decoder.decode(Document.self, from: data)
      guard document.schemaVersion == 1,
        document.entries.count <= Self.capacity,
        Set(document.entries.map(\.id)).count == document.entries.count,
        document.entries.allSatisfy(Self.isValid)
      else { throw StoreError.unreadable }
      entries = Self.newestFirst(document.entries)
    } catch {
      loadError = "Saved practice history could not be read. Clear history to start again."
    }
  }

  func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws {
    guard loadError == nil else { throw StoreError.unreadable }
    guard !entries.contains(where: { $0.id == sessionID }) else { return }
    let entry = PracticeParticipation(
      id: sessionID,
      // Keep the same precision in memory as the numeric epoch date persisted below.
      completedAt: Date(timeIntervalSince1970: completedAt.timeIntervalSince1970),
      soundID: soundID, wordCount: wordCount)
    guard Self.isValid(entry) else { throw StoreError.invalidEntry }
    let updated = Array(Self.newestFirst([entry] + entries).prefix(Self.capacity))
    try persist(updated)
    entries = updated
  }

  func clear() throws {
    try persist([])
    entries = []
    loadError = nil
  }

  private static func newestFirst(_ entries: [PracticeParticipation]) -> [PracticeParticipation] {
    entries.sorted {
      if $0.completedAt == $1.completedAt { return $0.id.uuidString < $1.id.uuidString }
      return $0.completedAt > $1.completedAt
    }
  }

  private static func isValid(_ entry: PracticeParticipation) -> Bool {
    let timestamp = entry.completedAt.timeIntervalSince1970
    return timestamp.isFinite && (0...253_402_300_799).contains(timestamp)
      && (1...3).contains(entry.wordCount)
      && PracticeLibrary.sounds.contains(where: { $0.id == entry.soundID })
  }

  private func persist(_ entries: [PracticeParticipation]) throws {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .secondsSince1970
    let data = try encoder.encode(Document(schemaVersion: 1, entries: entries))
    var directory = fileURL.deletingLastPathComponent()
    try FileManager.default.createDirectory(
      at: directory, withIntermediateDirectories: true,
      attributes: [.protectionKey: FileProtectionType.complete])
    var resourceValues = URLResourceValues()
    resourceValues.isExcludedFromBackup = true
    // Exclude only this store's own directory; backup marking is best effort.
    try? directory.setResourceValues(resourceValues)
    try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
  }

  private struct Document: Codable {
    let schemaVersion: Int
    let entries: [PracticeParticipation]
  }

  enum StoreError: Error {
    case unreadable
    case invalidEntry
  }
}
