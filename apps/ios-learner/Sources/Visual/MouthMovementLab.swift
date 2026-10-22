#if DEBUG
  @preconcurrency import ARKit
  @preconcurrency import AVFoundation
  import Foundation
  import Observation

  struct MouthMovementCapabilities: Equatable, Sendable {
    let supportsFaceTracking: Bool
    let hasTrueDepthCamera: Bool

    static var current: Self {
      #if targetEnvironment(simulator)
        Self(supportsFaceTracking: false, hasTrueDepthCamera: false)
      #else
        Self(
          supportsFaceTracking: ARFaceTrackingConfiguration.isSupported,
          hasTrueDepthCamera: AVCaptureDevice.default(
            .builtInTrueDepthCamera, for: .video, position: .front
          ) != nil
        )
      #endif
    }
  }

  struct MouthMovementMeasurements: Equatable, Sendable {
    let jawOpen: Double
    let mouthClose: Double
    let mouthFunnel: Double
    let mouthPucker: Double

    init?(jawOpen: Double?, mouthClose: Double?, mouthFunnel: Double?, mouthPucker: Double?) {
      guard let jawOpen, let mouthClose, let mouthFunnel, let mouthPucker,
        [jawOpen, mouthClose, mouthFunnel, mouthPucker].allSatisfy({
          $0.isFinite && (0...1).contains($0)
        })
      else { return nil }
      self.jawOpen = jawOpen
      self.mouthClose = mouthClose
      self.mouthFunnel = mouthFunnel
      self.mouthPucker = mouthPucker
    }
  }

  enum MouthMovementEvent: Sendable {
    case reading(MouthMovementMeasurements)
    case noFace, multipleFaces, unavailableReading, interrupted, failed
  }

  @MainActor
  protocol MouthMovementTracking: AnyObject {
    var capabilities: MouthMovementCapabilities { get }
    func requestPermission() async -> Bool
    func start(onEvent: @escaping @MainActor @Sendable (MouthMovementEvent) -> Void)
    func stop()
  }

  @MainActor @Observable
  final class MouthMovementLabModel {
    enum State: Equatable {
      case idle, requestingPermission, tracking, noFace, multipleFaces
      case unavailableReading, denied, unavailable, interrupted, failed
    }

    private(set) var state: State = .idle
    private(set) var measurements: MouthMovementMeasurements?
    private(set) var isRunning = false
    let capabilities: MouthMovementCapabilities
    @ObservationIgnored private let tracker: any MouthMovementTracking
    @ObservationIgnored private var generation = UUID()

    init(tracker: any MouthMovementTracking = SystemMouthMovementTracker()) {
      self.tracker = tracker
      capabilities = tracker.capabilities
      if !capabilities.supportsFaceTracking { state = .unavailable }
    }

    func start() async {
      guard capabilities.supportsFaceTracking, !isRunning, state != .requestingPermission else {
        return
      }
      let request = UUID()
      generation = request
      state = .requestingPermission
      let granted = await tracker.requestPermission()
      guard generation == request else { return }
      guard granted else {
        state = .denied
        return
      }
      state = .noFace
      isRunning = true
      tracker.start { [weak self] event in
        guard let self, self.generation == request, self.isRunning else { return }
        self.receive(event)
      }
    }

    func stop() {
      finish(as: capabilities.supportsFaceTracking ? .idle : .unavailable)
    }

    private func receive(_ event: MouthMovementEvent) {
      measurements = nil
      switch event {
      case .reading(let reading):
        measurements = reading
        state = .tracking
      case .noFace: state = .noFace
      case .multipleFaces: state = .multipleFaces
      case .unavailableReading: state = .unavailableReading
      case .interrupted: finish(as: .interrupted)
      case .failed: finish(as: .failed)
      }
    }

    private func finish(as nextState: State) {
      generation = UUID()
      tracker.stop()
      isRunning = false
      measurements = nil
      state = nextState
    }
  }

  @MainActor
  private final class SystemMouthMovementTracker: MouthMovementTracking {
    let capabilities = MouthMovementCapabilities.current
    private var session: ARSession?
    private var delegate: MouthMovementSessionDelegate?

    func requestPermission() async -> Bool {
      switch AVCaptureDevice.authorizationStatus(for: .video) {
      case .authorized: true
      case .notDetermined: await AVCaptureDevice.requestAccess(for: .video)
      case .denied, .restricted: false
      @unknown default: false
      }
    }

    func start(onEvent: @escaping @MainActor @Sendable (MouthMovementEvent) -> Void) {
      guard capabilities.supportsFaceTracking else { return }
      stop()
      let session = ARSession()
      let delegate = MouthMovementSessionDelegate(onEvent: onEvent)
      session.delegateQueue = DispatchQueue(label: "com.cadence.mouth-movement-lab")
      session.delegate = delegate
      let configuration = ARFaceTrackingConfiguration()
      configuration.maximumNumberOfTrackedFaces = min(
        2, ARFaceTrackingConfiguration.supportedNumberOfTrackedFaces
      )
      configuration.isLightEstimationEnabled = false
      configuration.providesAudioData = false
      self.session = session
      self.delegate = delegate
      session.run(configuration, options: [.resetTracking, .removeExistingAnchors])
    }

    func stop() {
      session?.delegate = nil
      session?.pause()
      session = nil
      delegate = nil
    }
  }

  // ARKit objects stay on its serial delegate queue. Only these four scalar
  // measurements and explicit status events cross to the main actor.
  private final class MouthMovementSessionDelegate: NSObject, ARSessionDelegate {
    private let onEvent: @MainActor @Sendable (MouthMovementEvent) -> Void
    private var lastUpdate = -Double.infinity

    init(onEvent: @escaping @MainActor @Sendable (MouthMovementEvent) -> Void) {
      self.onEvent = onEvent
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
      guard frame.timestamp - lastUpdate >= 0.1 else { return }
      lastUpdate = frame.timestamp
      let faces = frame.anchors.compactMap { $0 as? ARFaceAnchor }.filter(\.isTracked)
      guard faces.count == 1, let face = faces.first else {
        send(faces.isEmpty ? .noFace : .multipleFaces)
        return
      }
      guard
        let reading = MouthMovementMeasurements(
          jawOpen: face.blendShapes[.jawOpen]?.doubleValue,
          mouthClose: face.blendShapes[.mouthClose]?.doubleValue,
          mouthFunnel: face.blendShapes[.mouthFunnel]?.doubleValue,
          mouthPucker: face.blendShapes[.mouthPucker]?.doubleValue
        )
      else {
        send(.unavailableReading)
        return
      }
      send(.reading(reading))
    }

    func sessionWasInterrupted(_ session: ARSession) { send(.interrupted) }

    func session(_ session: ARSession, didFailWithError error: any Error) { send(.failed) }

    private func send(_ event: MouthMovementEvent) {
      let callback = onEvent
      Task { @MainActor in callback(event) }
    }
  }
#endif
