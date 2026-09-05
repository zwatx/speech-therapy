import Foundation

/// The plain mirror and face guide share one process camera reservation. Acquisition and
/// exact-owner release commit synchronously before either feature publishes UI state.
@MainActor
final class ProcessCameraLease {
  static let shared = ProcessCameraLease()
  private(set) var owner: UUID?

  @discardableResult
  func acquire(_ owner: UUID) -> Bool {
    guard self.owner == nil else { return false }
    self.owner = owner
    return true
  }

  @discardableResult
  func release(_ owner: UUID) -> Bool {
    guard self.owner == owner else { return false }
    self.owner = nil
    return true
  }
}
