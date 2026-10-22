import AVFoundation
import Foundation

/// Constructed and invoked only by PracticePlaybackRuntime's dedicated serial queue.
/// The initializer stores values; obtaining a session, creating a player and every potentially
/// blocking framework call are deferred to the corresponding queue-invoked methods.
nonisolated final class AVFoundationPracticePlaybackDriver: PracticePlaybackDriver {
  private let operation: PracticePlaybackOperation
  private let finished: @Sendable (PracticePlaybackOperation, Bool) -> Void
  private var session: AVAudioSession?
  private var player: AVAudioPlayer?
  private var delegate: PlaybackDelegate?

  init(
    operation: PracticePlaybackOperation,
    finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) {
    self.operation = operation
    self.finished = finished
  }

  func activate() throws {
    let session = AVAudioSession.sharedInstance()
    // Retain before the first throwing operation so failed activation can still deactivate.
    self.session = session
    try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
    try session.setActive(true)
  }

  func prepare() throws -> Bool {
    let player = try AVAudioPlayer(contentsOf: operation.url)
    let delegate = PlaybackDelegate(
      operation: operation, playerID: ObjectIdentifier(player), finished: finished)
    self.player = player
    self.delegate = delegate
    player.delegate = delegate
    return player.prepareToPlay()
  }

  func play() throws -> Bool { player?.play() ?? false }

  func stop() throws { player?.stop() }

  func releasePlaybackResources() throws {
    player?.delegate = nil
    player = nil
    delegate = nil
  }

  func deactivate() throws {
    guard let session else { return }
    try session.setActive(false, options: .notifyOthersOnDeactivation)
    self.session = nil
  }
}

/// The SDK marks AVAudioPlayerDelegate as UI-actor-isolated. This explicit nonisolated proxy
/// uses only immutable Sendable values, so it can receive framework callbacks on any thread
/// without hopping to MainActor or accessing the driver's queue-confined player/session.
private nonisolated final class PlaybackDelegate: NSObject, AVAudioPlayerDelegate {
  private let operation: PracticePlaybackOperation
  private let playerID: ObjectIdentifier
  private let finished: @Sendable (PracticePlaybackOperation, Bool) -> Void

  init(
    operation: PracticePlaybackOperation, playerID: ObjectIdentifier,
    finished: @escaping @Sendable (PracticePlaybackOperation, Bool) -> Void
  ) {
    self.operation = operation
    self.playerID = playerID
    self.finished = finished
    super.init()
  }

  nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    report(playerID: ObjectIdentifier(player), success: flag)
  }

  nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
    report(playerID: ObjectIdentifier(player), success: false)
  }

  private nonisolated func report(playerID: ObjectIdentifier, success: Bool) {
    guard playerID == self.playerID else { return }
    // The runtime callback enqueues this immutable report before consulting mutable state.
    // Already-entered callbacks can outlive delegate detachment; operation matching and
    // cleanup/cancellation checks in the runtime suppress their effects after release.
    finished(operation, success)
  }
}
