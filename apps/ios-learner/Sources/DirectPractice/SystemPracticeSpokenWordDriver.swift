import AVFoundation
import Foundation

/// Created and accessed only on the spoken runtime's serial queue. No SDK object crosses
/// that queue boundary, including the synthesizer (which the SDK marks non-Sendable).
nonisolated final class SystemPracticeSpokenWordDriver: PracticeSpokenWordDriver {
  private let operation: PracticeSpokenWordOperation
  private let event: @Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void
  private var synthesizer: AVSpeechSynthesizer?
  private var utterance: AVSpeechUtterance?
  private var delegate: SpokenWordDelegate?
  private var session: AVAudioSession?
  // Queue-confined metadata for exact selected-voice verification; no voice object escapes.
  private(set) var selectedVoiceIdentifier: String?

  init(
    operation: PracticeSpokenWordOperation,
    event: @escaping @Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void
  ) {
    self.operation = operation
    self.event = event
  }

  func prepare() throws {
    // Enumeration is explicit-tap-only. Identifier lookup must still find the installed
    // ordinary en-US voice; never request authorization, download or a language fallback.
    let voices = AVSpeechSynthesisVoice.speechVoices()
    // Let the system select its English voice. Alphabetical identifier order can
    // prefer a legacy fallback voice over the device's normal language voice.
    guard let preferred = AVSpeechSynthesisVoice(language: "en-US") else {
      throw PracticeSpokenWordError.unavailable
    }
    let identifier = preferred.identifier
    guard preferred.identifier.hasPrefix("com.apple."), preferred.language == "en-US",
      !preferred.voiceTraits.contains(.isPersonalVoice),
      !preferred.voiceTraits.contains(.isNoveltyVoice),
      voices.contains(where: { $0.identifier == identifier }),
      let voice = AVSpeechSynthesisVoice(identifier: identifier), voice.identifier == identifier,
      voice.identifier.hasPrefix("com.apple."), voice.language == "en-US",
      !voice.voiceTraits.contains(.isPersonalVoice), !voice.voiceTraits.contains(.isNoveltyVoice)
    else { throw PracticeSpokenWordError.unavailable }
    selectedVoiceIdentifier = identifier
    let session = AVAudioSession.sharedInstance()
    self.session = session
    try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
    try session.setActive(true)
    let synthesizer = AVSpeechSynthesizer()
    synthesizer.usesApplicationAudioSession = true
    let utterance = AVSpeechUtterance(string: operation.word)
    utterance.voice = voice
    let delegate = SpokenWordDelegate(
      operation: operation, synthesizerID: ObjectIdentifier(synthesizer),
      utteranceID: ObjectIdentifier(utterance), event: event)
    self.synthesizer = synthesizer
    self.utterance = utterance
    self.delegate = delegate
    synthesizer.delegate = delegate
  }

  func enqueue() {
    guard let synthesizer, let utterance else { return }
    synthesizer.speak(utterance)
  }

  func requestStop() { _ = synthesizer?.stopSpeaking(at: .immediate) }

  /// Runtime calls this only before enqueue or after the exact didFinish/didCancel event.
  func dispose() throws {
    synthesizer?.delegate = nil
    delegate = nil
    utterance = nil
    synthesizer = nil
  }

  func deactivate() throws {
    guard let session else { return }
    try session.setActive(false, options: .notifyOthersOnDeactivation)
    self.session = nil
  }
}

private nonisolated final class SpokenWordDelegate: NSObject, AVSpeechSynthesizerDelegate {
  private let operation: PracticeSpokenWordOperation
  private let synthesizerID: ObjectIdentifier
  private let utteranceID: ObjectIdentifier
  private let event: @Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void

  init(
    operation: PracticeSpokenWordOperation, synthesizerID: ObjectIdentifier,
    utteranceID: ObjectIdentifier,
    event: @escaping @Sendable (PracticeSpokenWordOperation, PracticeSpokenWordEvent) -> Void
  ) {
    self.operation = operation
    self.synthesizerID = synthesizerID
    self.utteranceID = utteranceID
    self.event = event
    super.init()
  }

  nonisolated func speechSynthesizer(
    _ synthesizer: AVSpeechSynthesizer, didStart utterance: AVSpeechUtterance
  ) { report(synthesizer, utterance, .started) }

  nonisolated func speechSynthesizer(
    _ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance
  ) { report(synthesizer, utterance, .finished) }

  nonisolated func speechSynthesizer(
    _ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance
  ) { report(synthesizer, utterance, .cancelled) }

  private nonisolated func report(
    _ synthesizer: AVSpeechSynthesizer, _ utterance: AVSpeechUtterance,
    _ value: PracticeSpokenWordEvent
  ) {
    guard ObjectIdentifier(synthesizer) == synthesizerID,
      ObjectIdentifier(utterance) == utteranceID
    else { return }
    event(operation, value)
  }
}
