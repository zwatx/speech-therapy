import Combine
import Foundation

/// Process-owned callbacks keep failed cleanup reachable after its route disappears.
/// Refresh only reads ownership. Retry operates on the exact resource snapshot selected
/// by that explicit action and never stops an otherwise active producer.
@MainActor
final class AudioCleanupRecoveryModel: ObservableObject {
  struct Snapshot: Equatable {
    let blockedPlaybackOperationID: UUID?
    let blockedCaptureOperationID: UUID?
    let pendingFileOwnerIDs: [UUID]
    let activeHardwareOperationID: UUID?
    var blockedSpokenWordOperationID: UUID? = nil

    var hasPendingCleanup: Bool {
      blockedPlaybackOperationID != nil || blockedCaptureOperationID != nil
        || blockedSpokenWordOperationID != nil
        || !pendingFileOwnerIDs.isEmpty
    }
    var canRetry: Bool {
      blockedPlaybackOperationID != nil || blockedCaptureOperationID != nil
        || blockedSpokenWordOperationID != nil
        || (activeHardwareOperationID == nil && !pendingFileOwnerIDs.isEmpty)
    }
  }

  enum Failure: Equatable {
    case hardwareInUse(UUID)
    case operationChanged
    case playbackCleanupUnconfirmed(UUID)
    case captureCleanupUnconfirmed(UUID)
    case spokenWordCleanupUnconfirmed(UUID)
    case fileCleanupUnconfirmed(UUID)
    case resourcesRemain
  }

  @Published private(set) var snapshot: Snapshot
  @Published private(set) var isRetrying = false
  @Published private(set) var failure: Failure?
  private let ownership: AudioHardwareOwnership
  private let files: ProcessAudioFileOwnership
  private var retryTask: Task<Bool, Never>?

  init(
    ownership: AudioHardwareOwnership = .shared,
    files: ProcessAudioFileOwnership = .shared
  ) {
    self.ownership = ownership
    self.files = files
    snapshot = Self.readSnapshot(ownership: ownership, files: files)
  }

  /// Deliberately passive; appearance/route/scene callers choose when to refresh.
  func refresh() {
    snapshot = Self.readSnapshot(ownership: ownership, files: files)
  }

  /// Task storage precedes every publication, so synchronous subscribers join this attempt.
  /// Dropping the UI or cancelling a waiter does not abandon owned cleanup.
  @discardableResult
  func retry() -> Task<Bool, Never> {
    if let retryTask { return retryTask }
    let selected = Self.readSnapshot(ownership: ownership, files: files)
    let selectedLease = ownership.currentLease
    let task = Task { @MainActor [self] in
      defer {
        // Publish the fresh result while duplicates still join this exact task.
        refresh()
        isRetrying = false
        retryTask = nil
      }
      return await recover(selected, lease: selectedLease)
    }
    retryTask = task
    failure = nil
    isRetrying = true
    return task
  }

  private static func readSnapshot(
    ownership: AudioHardwareOwnership, files: ProcessAudioFileOwnership
  ) -> Snapshot {
    Snapshot(
      blockedPlaybackOperationID: ownership.blockedPlaybackOperationID,
      blockedCaptureOperationID: ownership.blockedCaptureOperationID,
      pendingFileOwnerIDs: files.pendingCleanupOwners.sorted {
        $0.uuidString < $1.uuidString
      },
      activeHardwareOperationID: ownership.currentLease?.operationID,
      blockedSpokenWordOperationID: ownership.blockedSpokenWordOperationID)
  }

  private func recover(
    _ selected: Snapshot, lease selectedLease: AudioHardwareOwnership.Lease?
  ) async -> Bool {
    if let id = selected.blockedPlaybackOperationID {
      guard let lease = ownership.currentLease, lease == selectedLease, lease.owner == .playback,
        lease.operationID == id, ownership.blockedPlaybackOperationID == id
      else { return fail(.operationChanged) }
      guard let acknowledgement = ownership.retryPlaybackCleanup(),
        acknowledgement.operation.id == id
      else { return fail(.playbackCleanupUnconfirmed(id)) }
      let receipt = await acknowledgement.value()
      guard receipt.operation.id == id, receipt.result == .released else {
        return fail(.playbackCleanupUnconfirmed(id))
      }
      // A release publication may synchronously reserve a successor before this resumes.
      guard ownership.currentLease == nil,
        ownership.blockedPlaybackOperationID == nil,
        ownership.blockedCaptureOperationID == nil
      else { return fail(.operationChanged) }
    } else if let id = selected.blockedCaptureOperationID {
      guard let lease = ownership.currentLease, lease == selectedLease, lease.owner == .capture,
        lease.operationID == id, ownership.blockedCaptureOperationID == id
      else { return fail(.operationChanged) }
      let receipt = ownership.retryCaptureCleanup(operationID: id)
      guard receipt.operationID == id, receipt.hardwareReleased else {
        return fail(.captureCleanupUnconfirmed(id))
      }
      guard ownership.currentLease == nil,
        ownership.blockedPlaybackOperationID == nil,
        ownership.blockedCaptureOperationID == nil
      else { return fail(.operationChanged) }
    } else if let id = selected.blockedSpokenWordOperationID {
      guard let lease = ownership.currentLease, lease == selectedLease, lease.owner == .spokenWord,
        lease.operationID == id, ownership.blockedSpokenWordOperationID == id
      else { return fail(.operationChanged) }
      guard let receipt = await ownership.retrySpokenWordCleanup(), receipt.operation.id == id
      else { return fail(.spokenWordCleanupUnconfirmed(id)) }
      guard receipt.operation.id == id, receipt.result == .released else {
        return fail(.spokenWordCleanupUnconfirmed(id))
      }
      guard ownership.currentLease == nil, ownership.blockedSpokenWordOperationID == nil,
        ownership.blockedPlaybackOperationID == nil, ownership.blockedCaptureOperationID == nil
      else { return fail(.operationChanged) }
    } else if let id = ownership.currentLease?.operationID {
      return fail(.hardwareInUse(id))
    }

    var fileFailure: UUID?
    for owner in selected.pendingFileOwnerIDs {
      // Every callback can synchronously reenter the actor and reserve a successor.
      guard ownership.currentLease == nil,
        ownership.blockedPlaybackOperationID == nil,
        ownership.blockedCaptureOperationID == nil
      else { return fail(.operationChanged) }
      // A stale owner is not authority to call an unknown or replacement recovery.
      guard files.pendingCleanupOwners.contains(owner) else {
        return fail(.operationChanged)
      }
      if !files.retryCleanup(owner: owner), fileFailure == nil { fileFailure = owner }
    }
    if let fileFailure { return fail(.fileCleanupUnconfirmed(fileFailure)) }
    let remaining = Self.readSnapshot(ownership: ownership, files: files)
    guard !remaining.hasPendingCleanup else { return fail(.resourcesRemain) }
    guard remaining.activeHardwareOperationID == nil else { return fail(.operationChanged) }
    return true
  }

  private func fail(_ reason: Failure) -> Bool {
    failure = reason
    return false
  }
}
