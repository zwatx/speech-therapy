import Foundation

/// Retained files outlive both playback and the screen that requested cleanup.
/// This is process-local ownership, not evidence that a file survived an app crash.
@MainActor
final class ProcessAudioFileOwnership {
  static let shared = ProcessAudioFileOwnership()

  private var retained: [UUID: Set<URL>] = [:]
  private var borrowed: [UUID: URL] = [:]
  private var cleanupRecovery: [UUID: @MainActor () -> Bool] = [:]
  private var retryingOwners: Set<UUID> = []

  var pendingCleanupOwners: Set<UUID> { Set(cleanupRecovery.keys) }

  /// Only actual retained ownership can register recovery. An existing owner callback
  /// cannot be replaced; successful didRemove is the authority that clears it.
  @discardableResult
  func registerCleanupRecovery(owner: UUID, retry: @escaping @MainActor () -> Bool) -> Bool {
    guard retained[owner]?.isEmpty == false, cleanupRecovery[owner] == nil else { return false }
    cleanupRecovery[owner] = retry
    return true
  }

  func retryCleanup(owner: UUID) -> Bool {
    guard !retryingOwners.contains(owner), let retry = cleanupRecovery[owner] else { return false }
    retryingOwners.insert(owner)
    defer { retryingOwners.remove(owner) }
    let acknowledged = retry()
    return acknowledged && retained[owner] == nil && cleanupRecovery[owner] == nil
  }
  private enum StartupCleanup {
    case running
    case completed(Result<Void, Error>)
  }
  private enum CleanupError: Error { case alreadyRunning }
  private var startupCleanup: [String: StartupCleanup] = [:]

  private func key(_ url: URL) -> URL { url.standardizedFileURL }

  func retain(_ url: URL, owner: UUID) {
    retained[owner, default: []].insert(key(url))
  }

  /// Reserve a read before queued playback can access the file.
  @discardableResult
  func borrow(_ url: URL, operation: UUID) -> Bool {
    let url = key(url)
    if let existing = borrowed[operation] { return existing == url }
    borrowed[operation] = url
    return true
  }

  /// Call only after the exact operation acknowledges playback-resource cleanup.
  func finishBorrowing(operation: UUID) {
    borrowed.removeValue(forKey: operation)
  }

  func canRemove(_ url: URL, owner: UUID) -> Bool {
    let url = key(url)
    return retained[owner]?.contains(url) == true
      && !borrowed.values.contains(url)
      && !retained.contains { $0.key != owner && $0.value.contains(url) }
  }

  /// Failed deletion keeps the owner entry; requesting deletion is not removal.
  func didRemove(_ url: URL, owner: UUID) {
    let url = key(url)
    guard canRemove(url, owner: owner) else { return }
    retained[owner]?.remove(url)
    if retained[owner]?.isEmpty == true {
      retained.removeValue(forKey: owner)
      cleanupRecovery.removeValue(forKey: owner)
    }
  }

  var protectedURLs: Set<URL> {
    Set(retained.values.flatMap { $0 }).union(borrowed.values)
  }

  /// A second route cannot reinterpret this process's retained takes as stale.
  /// A failed initial scan remains failed until a fresh process, rather than being bypassed.
  func cleanStartupOnce(
    directory: URL,
    removeStale: (Set<URL>) throws -> Void
  ) throws {
    // URL directory flags can change when a missing directory is created. A filesystem
    // namespace must keep the same scan receipt before and after that change.
    let directory = key(directory).path
    if let state = startupCleanup[directory] {
      switch state {
      case .running: throw CleanupError.alreadyRunning
      case .completed(let result): try result.get()
      }
      return
    }
    startupCleanup[directory] = .running
    let result = Result { try removeStale(protectedURLs) }
    startupCleanup[directory] = .completed(result)
    try result.get()
  }
}
