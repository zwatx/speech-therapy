import Combine
import Foundation

/// Callers revalidate their own operation/route after awaiting play or cleanup. A request to
/// stop revokes eligibility immediately; only a released receipt permits owned media deletion.
@MainActor
protocol AcknowledgedPracticeAudioPlaying: AnyObject {
  var state: PracticePlaybackRuntimeState { get }
  /// Mutations originate on MainActor; subscribe there for synchronous initial delivery.
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> { get }
  func play(
    id: UUID, url: URL,
    onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws
  @discardableResult
  func requestStop(id: UUID) -> PracticePlaybackCleanup?
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup?
  /// A completed positive explicit retry is separate from the original stop acknowledgement.
  func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt?
}

extension AcknowledgedPracticeAudioPlaying {
  /// An implementation that retains no completed retry evidence cannot acknowledge release.
  func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? { nil }
}

/// Production facade for the acknowledged API. Construction and default factory formation
/// perform no framework/player/session work; the runtime invokes that factory on its queue.
@MainActor
final class SystemAcknowledgedPracticeAudioPlayer: AcknowledgedPracticeAudioPlaying {
  private let runtime: PracticePlaybackRuntime

  var state: PracticePlaybackRuntimeState { runtime.state }
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
    runtime.$state.eraseToAnyPublisher()
  }

  init(
    ownership: AudioHardwareOwnership = .shared,
    fileOwnership: ProcessAudioFileOwnership = .shared,
    factory: @escaping PracticePlaybackDriverFactory = { operation, finished in
      AVFoundationPracticePlaybackDriver(operation: operation, finished: finished)
    }
  ) {
    runtime = PracticePlaybackRuntime(
      ownership: ownership, fileOwnership: fileOwnership, factory: factory)
  }

  func play(
    id: UUID, url: URL,
    onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws {
    try await runtime.startPlayback(id: id, url: url, onFinished: onFinish)
  }

  @discardableResult
  func requestStop(id: UUID) -> PracticePlaybackCleanup? { runtime.requestStop(id: id) }

  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { runtime.retryCleanup(id: id) }

  func completedCleanupRetry(id: UUID) -> PracticePlaybackCleanupReceipt? {
    runtime.completedCleanupRetry(id: id)
  }
}
