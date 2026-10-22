import AVFoundation
import Foundation

/// Synchronous MainActor boundary; construction is inert. The driver retains partial
/// resources before any throwing framework stage and releases them only during cleanup.
@MainActor
protocol CaptureHardwareDriver: AnyObject {
  func configureActivate() throws
  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws
  func prepare() throws -> Bool
  func record() throws -> Bool
  /// Current mono average power in dBFS; nil when recording is unavailable.
  func currentRecordingPower() -> Float?
  func stop() throws
  func detachRelease() throws
  func deactivate() throws
}

extension CaptureHardwareDriver {
  func currentRecordingPower() -> Float? { nil }
}

typealias CaptureHardwareDriverFactory = @MainActor () -> any CaptureHardwareDriver

@MainActor
final class AVFoundationCaptureHardwareDriver: CaptureHardwareDriver {
  private var session: AVAudioSession?
  private var recorder: AVAudioRecorder?
  private var completion: RecorderCompletion?

  func configureActivate() throws {
    let session = AVAudioSession.sharedInstance()
    self.session = session
    try session.setCategory(.playAndRecord, mode: .measurement)
    try session.setActive(true)
  }

  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    let settings: [String: Any] = [
      AVFormatIDKey: Int(kAudioFormatLinearPCM),
      AVSampleRateKey: 16_000,
      AVNumberOfChannelsKey: 1,
      AVLinearPCMBitDepthKey: 16,
      AVLinearPCMIsBigEndianKey: false,
      AVLinearPCMIsFloatKey: false,
    ]
    let recorder = try AVAudioRecorder(url: url, settings: settings)
    self.recorder = recorder
    recorder.isMeteringEnabled = true
    let completion = RecorderCompletion(
      expectedRecorder: ObjectIdentifier(recorder), recorderID: recorderID, onFinish: onFinish)
    self.completion = completion
    recorder.delegate = completion
  }

  func prepare() throws -> Bool { recorder?.prepareToRecord() == true }
  func record() throws -> Bool { recorder?.record(forDuration: 4.0) == true }
  func currentRecordingPower() -> Float? {
    guard let recorder, recorder.isRecording else { return nil }
    recorder.updateMeters()
    let power = recorder.averagePower(forChannel: 0)
    guard recorder.isRecording, power.isFinite else { return nil }
    return power
  }
  func stop() throws { recorder?.stop() }

  func detachRelease() throws {
    recorder?.delegate = nil
    recorder = nil
    completion = nil
  }

  func deactivate() throws {
    try session?.setActive(false, options: .notifyOthersOnDeactivation)
    session = nil
  }
}

/// Immutable callback identity survives queued delegate delivery. Mutable capturer/driver
/// state is accessed only after the MainActor hop, where the operation checks both IDs.
private final class RecorderCompletion: NSObject, AVAudioRecorderDelegate {
  let expectedRecorder: ObjectIdentifier
  let recorderID: UUID
  let onFinish: @MainActor @Sendable (UUID, Bool) -> Void

  init(
    expectedRecorder: ObjectIdentifier, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) {
    self.expectedRecorder = expectedRecorder
    self.recorderID = recorderID
    self.onFinish = onFinish
  }

  nonisolated func audioRecorderDidFinishRecording(
    _ recorder: AVAudioRecorder, successfully flag: Bool
  ) {
    guard ObjectIdentifier(recorder) == expectedRecorder else { return }
    let recorderID = recorderID
    let onFinish = onFinish
    Task { @MainActor in onFinish(recorderID, flag) }
  }
}
