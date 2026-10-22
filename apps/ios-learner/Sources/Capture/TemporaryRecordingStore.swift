import Foundation

struct TemporaryRecordingStore {
  static let filenamePrefix = "cadence-attempt-"

  let directory: URL
  private let fileManager: FileManager

  init(
    directory: URL = FileManager.default.temporaryDirectory,
    fileManager: FileManager = .default
  ) {
    self.directory = directory
    self.fileManager = fileManager
  }

  func makeRecordingURL() -> URL {
    directory
      .appendingPathComponent("\(Self.filenamePrefix)\(UUID().uuidString)")
      .appendingPathExtension("wav")
  }

  func removeStaleRecordings(excluding protectedURLs: Set<URL> = []) throws {
    let urls = try fileManager.contentsOfDirectory(
      at: directory,
      includingPropertiesForKeys: nil
    )
    for url in urls
    where url.lastPathComponent.hasPrefix(Self.filenamePrefix)
      && ["m4a", "wav"].contains(url.pathExtension.lowercased())
      && !protectedURLs.contains(url.standardizedFileURL)
    {
      try fileManager.removeItem(at: url)
    }
  }

  func removeRecordingIfPresent(at url: URL) throws {
    do { try fileManager.removeItem(at: url) } catch {
      // A boolean existence lookup also returns false for indeterminate access errors.
      // Only an explicit missing-file error can stand in for successful removal.
      let failure = error as NSError
      guard failure.domain == NSCocoaErrorDomain && failure.code == NSFileNoSuchFileError else {
        throw error
      }
    }
  }
}
