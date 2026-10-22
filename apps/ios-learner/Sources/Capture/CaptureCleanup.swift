import Foundation

/// Process-local acknowledgement. Hardware release and requested file removal are distinct.
struct CaptureCleanupState: Equatable, Sendable {
  let hardwareBlockedOperationID: UUID?
  let fileBlockedOwnerIDs: Set<UUID>

  static let idle = Self(hardwareBlockedOperationID: nil, fileBlockedOwnerIDs: [])
  var hasHardwareIssue: Bool { hardwareBlockedOperationID != nil }
  var hasFileIssue: Bool { !fileBlockedOwnerIDs.isEmpty }
}

struct CaptureCleanupReceipt: Equatable, Sendable {
  let operationID: UUID
  let result: Result

  enum Result: Equatable, Sendable {
    case refused
    case cleanupUnconfirmed
    case hardwareReleasedFilesRetained
    case released
  }

  var hardwareReleased: Bool {
    result == .hardwareReleasedFilesRetained || result == .released
  }
  var allRequestedFilesRemoved: Bool { result == .released }
}
