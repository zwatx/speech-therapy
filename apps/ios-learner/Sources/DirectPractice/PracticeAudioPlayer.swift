import AVFoundation
import Foundation

@MainActor
protocol PracticeAudioPlaying: AnyObject {
  func play(url: URL, onFinish: @escaping @MainActor (Bool) -> Void) throws
  func stop()
}

enum PracticePlaybackError: LocalizedError {
  case couldNotPlay

  var errorDescription: String? {
    "This recording could not play. You can record it again or continue."
  }
}

@MainActor
final class SystemPracticeAudioPlayer: NSObject, PracticeAudioPlaying, AVAudioPlayerDelegate {
  private var player: AVAudioPlayer?
  private var onFinish: (@MainActor (Bool) -> Void)?

  func play(url: URL, onFinish: @escaping @MainActor (Bool) -> Void) throws {
    stop()
    let session = AVAudioSession.sharedInstance()
    do {
      try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
      try session.setActive(true)
      let player = try AVAudioPlayer(contentsOf: url)
      player.delegate = self
      guard player.prepareToPlay() else { throw PracticePlaybackError.couldNotPlay }
      guard player.play() else { throw PracticePlaybackError.couldNotPlay }
      self.player = player
      self.onFinish = onFinish
    } catch {
      try? session.setActive(false, options: .notifyOthersOnDeactivation)
      throw PracticePlaybackError.couldNotPlay
    }
  }

  func stop() {
    guard player != nil else { return }
    onFinish = nil
    player?.stop()
    player = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
  }

  nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    finish(playerID: ObjectIdentifier(player), successfully: flag)
  }

  nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
    finish(playerID: ObjectIdentifier(player), successfully: false)
  }

  private nonisolated func finish(playerID: ObjectIdentifier, successfully: Bool) {
    Task { @MainActor [weak self] in
      guard let self, let current = self.player,
        ObjectIdentifier(current) == playerID
      else { return }
      let completion = self.onFinish
      self.stop()
      completion?(successfully)
    }
  }
}
