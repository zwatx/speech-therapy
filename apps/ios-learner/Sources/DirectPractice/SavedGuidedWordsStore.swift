import Combine
import Foundation

/// Canonical identity and order only; no round or media owner is created here.
enum SavedGuidedWordsValidation {
  static func entries(entryIDs: [String]) throws -> [PracticeLibraryEntry] {
    guard entryIDs.count == 5, Set(entryIDs).count == 5 else {
      throw SavedGuidedWordsStore.StoreError.invalidEntry
    }
    let library = PracticeLibrary.entries()
    let entries = try entryIDs.map { id in
      guard let entry = library.first(where: { $0.id == id }) else {
        throw SavedGuidedWordsStore.StoreError.invalidEntry
      }
      return entry
    }
    guard
      Set(
        entries.map { $0.prompt.word.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
      ).count == 5
    else {
      throw SavedGuidedWordsStore.StoreError.invalidEntry
    }
    return entries
  }
}

@MainActor
final class SavedGuidedWordsStore: ObservableObject {
  static let shared = SavedGuidedWordsStore(
    fileURL: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent("SavedGuidedWords", isDirectory: true).appendingPathComponent(
        "saved-words.json"))
  static let unreadableMessage = "Saved words could not be read. Clear them to save a new set."
  @Published private(set) var entryIDs: [String]?
  @Published private(set) var loadError: String?
  private let fileURL: URL
  var entries: [PracticeLibraryEntry]? {
    entryIDs.flatMap { try? SavedGuidedWordsValidation.entries(entryIDs: $0) }
  }

  init(fileURL: URL) {
    self.fileURL = fileURL
    let attributes: [FileAttributeKey: Any]
    do {
      attributes = try FileManager.default.attributesOfItem(atPath: fileURL.path)
    } catch {
      let failure = error as NSError
      // Only metadata can establish absence: FileHandle also reports missing-file for directories.
      if failure.domain == NSCocoaErrorDomain
        && (failure.code == NSFileNoSuchFileError || failure.code == NSFileReadNoSuchFileError)
      {
        return
      }
      loadError = Self.unreadableMessage
      return
    }
    guard attributes[.type] as? FileAttributeType == .typeRegular else {
      loadError = Self.unreadableMessage
      return
    }
    do {
      let handle = try FileHandle(forReadingFrom: fileURL)
      defer { try? handle.close() }
      let data = try handle.read(upToCount: 8193) ?? Data()
      guard data.count <= 8192 else { throw StoreError.unreadable }
      // JSONDecoder accepts integral floating-point values as Int; the envelope requires an integer.
      guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        let version = object["schemaVersion"] as? NSNumber,
        ["i", "s", "l", "q"].contains(String(cString: version.objCType)), version.intValue == 1
      else { throw StoreError.unreadable }
      let document = try JSONDecoder().decode(Document.self, from: data)
      if let ids = document.entryIDs { _ = try SavedGuidedWordsValidation.entries(entryIDs: ids) }
      entryIDs = document.entryIDs
    } catch {
      loadError = Self.unreadableMessage
    }
  }

  func save(entryIDs: [String]) throws {
    guard loadError == nil else { throw StoreError.unreadable }
    _ = try SavedGuidedWordsValidation.entries(entryIDs: entryIDs)
    try persist(entryIDs)
    self.entryIDs = entryIDs
  }

  func clear() throws {
    try persist(nil)
    entryIDs = nil
    loadError = nil
  }

  private func persist(_ ids: [String]?) throws {
    let data = try JSONEncoder().encode(Document(entryIDs: ids))
    var directory = fileURL.deletingLastPathComponent()
    try FileManager.default.createDirectory(
      at: directory, withIntermediateDirectories: true,
      attributes: [.protectionKey: FileProtectionType.complete])
    var values = URLResourceValues()
    values.isExcludedFromBackup = true
    try directory.setResourceValues(values)
    try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
  }

  private struct Document: Codable {
    let entryIDs: [String]?
    private enum Keys: String, CodingKey { case schemaVersion, entryIDs }
    private struct AnyKey: CodingKey {
      let stringValue: String
      let intValue: Int? = nil
      init?(stringValue: String) { self.stringValue = stringValue }
      init?(intValue: Int) { return nil }
    }
    init(entryIDs: [String]?) { self.entryIDs = entryIDs }
    init(from decoder: Decoder) throws {
      let all = try decoder.container(keyedBy: AnyKey.self)
      guard Set(all.allKeys.map(\.stringValue)) == Set(["schemaVersion", "entryIDs"]) else {
        throw StoreError.unreadable
      }
      let container = try decoder.container(keyedBy: Keys.self)
      guard try container.decode(Int.self, forKey: .schemaVersion) == 1 else {
        throw StoreError.unreadable
      }
      entryIDs = try container.decodeIfPresent([String].self, forKey: .entryIDs)
    }
    func encode(to encoder: Encoder) throws {
      var container = encoder.container(keyedBy: Keys.self)
      try container.encode(1, forKey: .schemaVersion)
      try container.encode(entryIDs, forKey: .entryIDs)
    }
  }
  enum StoreError: Error { case unreadable, invalidEntry }
}
