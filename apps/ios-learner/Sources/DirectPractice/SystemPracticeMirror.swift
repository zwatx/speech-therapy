@preconcurrency import AVFoundation
import Foundation

@MainActor
final class SystemPracticeMirrorPermission: PracticeMirrorPermissionProviding {
  var isSupported: Bool {
    #if targetEnvironment(simulator)
      false
    #else
      true
    #endif
  }

  var status: PracticeMirrorPermission {
    guard isSupported else { return .denied }
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized: return .authorized
    case .notDetermined: return .notDetermined
    default: return .denied
    }
  }

  func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
    guard isSupported else {
      completion(false)
      return
    }
    AVCaptureDevice.requestAccess(for: .video) { granted in
      Task { @MainActor in completion(granted) }
    }
  }
}

@MainActor
enum SystemPracticeMirror {
  @MainActor
  private final class Link {
    weak var runtime: PracticeMirrorRuntime?
  }

  /// Construction is inert. Neither permission nor a camera driver starts here.
  static func make() -> DirectPracticeMirror {
    let presentation = PracticeMirrorPresentation()
    let link = Link()
    let runtime = PracticeMirrorRuntime(presentation: presentation) { owner in
      SystemPracticeMirrorDriver {
        Task { @MainActor in link.runtime?.unavailableAndStop(owner: owner) }
      }
    }
    link.runtime = runtime
    return DirectPracticeMirror(permission: SystemPracticeMirrorPermission(), runtime: runtime)
  }
}

/// Preview only, owned by the runtime's serial worker. There are no video-data outputs,
/// microphone inputs, AVAudioSession calls, frame callbacks, files or network requests.
private final class SystemPracticeMirrorDriver: PracticeMirrorDriver {
  private enum Failure: Error {
    case noFrontCamera, inputUnavailable, startFailed, stopUnconfirmed
  }
  private let unexpectedStop: @Sendable () -> Void
  private let events = EventGate()
  private var session: AVCaptureSession?
  private var observers: [NSObjectProtocol] = []

  private final class EventGate: @unchecked Sendable {
    private let lock = NSLock()
    private var expectedStop = false
    func expectStop() { lock.withLock { expectedStop = true } }
    var acceptsUnexpectedStop: Bool { lock.withLock { !expectedStop } }
  }

  init(unexpectedStop: @escaping @Sendable () -> Void) {
    self.unexpectedStop = unexpectedStop
  }

  var previewSource: PracticeMirrorPreviewSource? {
    guard let session, session.isRunning else { return nil }
    return .camera(PracticeMirrorCameraReference(session: session))
  }

  func configure() throws {
    let session = AVCaptureSession()
    self.session = session  // Retain partial resources before any fallible configuration.
    session.automaticallyConfiguresApplicationAudioSession = false
    let events = events
    let unexpectedStop = unexpectedStop
    for name in [
      AVCaptureSession.runtimeErrorNotification,
      AVCaptureSession.wasInterruptedNotification,
      AVCaptureSession.didStopRunningNotification,
    ] {
      observers.append(
        NotificationCenter.default.addObserver(
          forName: name, object: session, queue: nil
        ) { _ in
          if events.acceptsUnexpectedStop { unexpectedStop() }
        })
    }
    guard
      let device = AVCaptureDevice.default(
        .builtInWideAngleCamera, for: .video, position: .front)
    else { throw Failure.noFrontCamera }
    let input = try AVCaptureDeviceInput(device: device)
    session.beginConfiguration()
    defer { session.commitConfiguration() }
    if session.canSetSessionPreset(.medium) { session.sessionPreset = .medium }
    guard session.canAddInput(input) else { throw Failure.inputUnavailable }
    session.addInput(input)
  }

  func start() throws {
    guard let session else { throw Failure.startFailed }
    session.startRunning()
    guard session.isRunning else { throw Failure.startFailed }
  }

  func stopAndReleasePreviewResources() throws {
    events.expectStop()
    if let session {
      if session.isRunning { session.stopRunning() }
      guard !session.isRunning else { throw Failure.stopUnconfirmed }
      session.beginConfiguration()
      for input in session.inputs { session.removeInput(input) }
      for output in session.outputs { session.removeOutput(output) }
      session.commitConfiguration()
      guard session.inputs.isEmpty, session.outputs.isEmpty else { throw Failure.stopUnconfirmed }
    }
    for observer in observers { NotificationCenter.default.removeObserver(observer) }
    observers.removeAll()
    session = nil
  }
}
