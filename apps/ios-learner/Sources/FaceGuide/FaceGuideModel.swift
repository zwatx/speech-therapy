import Combine
import Foundation
import UIKit

enum FaceGuidePermission: Equatable {
  case notDetermined, authorized, denied
}

enum FaceGuideScene: Equatable { case active, inactive, background }

/// Live detail. Depth stays pending until current frames actually carry TrueDepth data.
enum FaceGuideTracking: Equatable {
  case waitingForCamera, noFace, depthPending, tracking
}

enum FaceGuidePhase: Equatable {
  case ready, unsupported, requestingPermission, awaitingActive
  case live(FaceGuideTracking)
  case denied, cameraBusy, paused, interrupted, failed, stopFailed
}

/// One ARKit frame reduced to Sendable scalars. Raw coefficients are sanitized by the model.
struct FaceGuideFrame: Equatable, Sendable {
  let timestamp: TimeInterval
  let faceTracked: Bool
  let depthCaptured: Bool
  let jawOpen: Float?
  let mouthPucker: Float?
}

enum FaceGuideEvent: Equatable, Sendable {
  case frame(FaceGuideFrame)
  case interrupted, failed
}

/// Relative ARKit blend-shape coefficients for display only. Not a score, measurement in
/// millimetres or evidence about how a sound was produced.
struct FaceGuideMovement: Equatable, Sendable {
  let jawOpening: Double
  let lipRounding: Double

  init?(jawOpen: Float?, mouthPucker: Float?) {
    guard let jawOpening = Self.sanitized(jawOpen), let lipRounding = Self.sanitized(mouthPucker)
    else { return nil }
    self.jawOpening = jawOpening
    self.lipRounding = lipRounding
  }

  /// Missing or non-finite values are absent, never rendered as zero.
  static func sanitized(_ value: Float?) -> Double? {
    guard let value, value.isFinite else { return nil }
    return min(max(Double(value), 0), 1)
  }
}

@MainActor
protocol FaceGuideHardware: AnyObject {
  /// Face tracking with a front TrueDepth video format. Never prompts or opens a camera.
  var isSupported: Bool { get }
  var permission: FaceGuidePermission { get }
  /// Only the explicit Start action calls this. Completion may be synchronous.
  func requestPermission(completion: @escaping @MainActor (Bool) -> Void)
  /// Construction must be inert; one driver per Start.
  func makeDriver() -> any FaceGuideDriver
}

@MainActor
protocol FaceGuideDriver: AnyObject {
  /// Live camera and mesh surface; nil for generated drivers.
  var surface: UIView? { get }
  /// Runs the session. A throw leaves partial resources on this driver until stop succeeds.
  func start(events: @escaping @MainActor (FaceGuideEvent) -> Void) throws
  /// Pauses and detaches delegate, nodes and view. Throws if detachment can't be confirmed.
  /// Success is not a framework acknowledgement that camera hardware has powered down.
  func stop() throws
}

/// One process slot holding the model that owns the face guide's camera lease, from
/// reservation until confirmed teardown. A dismissed screen therefore cannot orphan the
/// lease, and reopening the guide reattaches the exact owner for Retry.
@MainActor
final class FaceGuideRecovery {
  static let shared = FaceGuideRecovery(cameraLease: .shared)
  private let cameraLease: ProcessCameraLease
  private(set) var model: FaceGuideModel?

  init(cameraLease: ProcessCameraLease = ProcessCameraLease()) {
    self.cameraLease = cameraLease
  }

  var cameraInUse: Bool { cameraLease.owner != nil }

  fileprivate func reserve(_ owner: UUID, model: FaceGuideModel) -> Bool {
    guard self.model == nil, cameraLease.acquire(owner) else { return false }
    self.model = model
    return true
  }

  fileprivate func release(_ owner: UUID, model: FaceGuideModel) -> Bool {
    guard self.model === model, cameraLease.release(owner) else { return false }
    self.model = nil
    return true
  }
}

/// Optional face guide lifecycle. Construction is inert: no permission request, session or
/// lease. It never records audio and never feeds the scripted sound feedback.
@MainActor
final class FaceGuideModel: ObservableObject {
  struct State: Equatable {
    var phase: FaceGuidePhase
    var movement: FaceGuideMovement?
    var readyToDismiss = false
  }

  @Published private var emittedState: State
  private var committedState: State
  private var publications: [State] = []
  private var isPublishing = false
  var phase: FaceGuidePhase { committedState.phase }
  var movement: FaceGuideMovement? { committedState.movement }
  var readyToDismiss: Bool { committedState.readyToDismiss }
  var statePublisher: AnyPublisher<State, Never> { $emittedState.eraseToAnyPublisher() }

  /// TrueDepth data arrives at a lower rate than color frames.
  static let depthWindow: TimeInterval = 0.5
  static let movementInterval: TimeInterval = 0.1

  private let hardware: any FaceGuideHardware
  private let recovery: FaceGuideRecovery
  private var scene: FaceGuideScene
  private var closeRequested = false
  private var pendingPermission: PermissionAttempt?
  private var operation: Operation?
  private var liveGeneration: UUID?
  private var lastDepth: TimeInterval?
  private var lastMovement: TimeInterval?
  private var isStarting = false
  private var isStopping = false
  private var deferredEnd: FaceGuidePhase?

  private struct PermissionAttempt {
    let id = UUID()
    var granted = false
  }

  private struct Operation {
    let id: UUID
    let driver: any FaceGuideDriver
  }

  init(
    hardware: any FaceGuideHardware, recovery: FaceGuideRecovery,
    initialScene: FaceGuideScene = .inactive
  ) {
    self.hardware = hardware
    self.recovery = recovery
    scene = initialScene
    let initial = State(phase: hardware.isSupported ? .ready : .unsupported)
    committedState = initial
    emittedState = initial
  }

  static func standard() -> FaceGuideModel {
    make(hardware: SystemFaceGuideHardware(), recovery: .shared)
  }

  /// Reattaches a retained owner instead of creating a second one beside it.
  static func make(
    hardware: @autoclosure () -> any FaceGuideHardware, recovery: FaceGuideRecovery
  ) -> FaceGuideModel {
    if let retained = recovery.model {
      retained.closeRequested = false
      var state = retained.committedState
      state.readyToDismiss = false
      retained.publish(state)
      return retained
    }
    return FaceGuideModel(hardware: hardware(), recovery: recovery)
  }

  var permissionPending: Bool { pendingPermission != nil }
  var cameraAuthorized: Bool { hardware.permission == .authorized }
  var hasCameraOwner: Bool { operation != nil }
  var cleanupBlocked: Bool { phase == .stopFailed }
  var transitionPending: Bool { isStarting || isStopping }

  /// Cancels a pending permission/start and stops the preview without closing this model.
  /// Failed cleanup requires explicit retry; a word transition never retries it implicitly.
  @discardableResult
  func stopForPracticeTransition() -> Bool {
    guard !cleanupBlocked else { return false }
    return endSession(then: .ready)
  }

  var depthActive: Bool { phase == .live(.tracking) }
  var interactiveDismissDisabled: Bool { pendingPermission != nil || operation != nil }

  var cameraSurface: UIView? {
    guard case .live = phase else { return nil }
    return operation?.driver.surface
  }

  func start() {
    guard !closeRequested, scene == .active, operation == nil, pendingPermission == nil else {
      return
    }
    guard hardware.isSupported else {
      setPhase(.unsupported)
      return
    }
    // Never prompt while another feature holds the camera.
    guard !recovery.cameraInUse else {
      setPhase(.cameraBusy)
      return
    }
    switch hardware.permission {
    case .denied: setPhase(.denied)
    case .authorized: begin()
    case .notDetermined:
      let attempt = PermissionAttempt()
      pendingPermission = attempt
      setPhase(.requestingPermission)
      guard pendingPermission?.id == attempt.id, !closeRequested else { return }
      guard scene == .active else {
        pendingPermission = nil
        setPhase(.paused)
        return
      }
      hardware.requestPermission { [weak self] granted in
        self?.permissionCompleted(id: attempt.id, granted: granted)
      }
    }
  }

  func stop() {
    guard case .live = phase else { return }
    endSession(then: .ready)
  }

  /// True when the view may dismiss now. Otherwise the exact driver and lease stay retained.
  @discardableResult
  func close() -> Bool {
    closeRequested = true
    guard endSession(then: .ready) else { return false }
    return readyToDismiss
  }

  /// Explicit retry of the retained driver's teardown. Never constructs a new driver.
  @discardableResult
  func retryStop() -> Bool {
    guard phase == .stopFailed, let operation, teardown(operation, then: .ready) else {
      return false
    }
    return true
  }

  func sceneChanged(_ next: FaceGuideScene) {
    scene = next
    switch next {
    case .active:
      // Return never resumes a stopped session; only a granted pending Start continues.
      if pendingPermission?.granted == true {
        pendingPermission = nil
        begin()
      } else if phase == .denied, operation == nil, pendingPermission == nil,
        !closeRequested, hardware.permission == .authorized
      {
        // Settings can grant access while this view remains alive. Offer an explicit Start;
        // returning to the app never turns the camera on by itself.
        setPhase(.ready)
      }
    case .inactive:
      // Only this exact permission attempt survives the system alert's inactivity.
      if pendingPermission == nil { pauseForScene() }
    case .background:
      pauseForScene()
    }
  }

  /// A failed teardown stays retained in recovery; retry remains an explicit action.
  func viewDisappeared() {
    closeRequested = true
    guard phase != .stopFailed else { return }
    endSession(then: .ready)
  }

  private func pauseForScene() {
    guard phase != .stopFailed else { return }
    if operation != nil {
      endSession(then: .paused)
      return
    }
    switch phase {
    case .live, .requestingPermission, .awaitingActive: endSession(then: .paused)
    default: break
    }
  }

  private func permissionCompleted(id: UUID, granted: Bool) {
    guard var attempt = pendingPermission, attempt.id == id, !closeRequested else { return }
    guard granted else {
      pendingPermission = nil
      setPhase(.denied)
      return
    }
    guard scene == .active else {
      attempt.granted = true
      pendingPermission = attempt
      setPhase(.awaitingActive)
      return
    }
    pendingPermission = nil
    begin()
  }

  private func begin() {
    guard !closeRequested, scene == .active, operation == nil else { return }
    let id = UUID()
    // Commit the exact lease before any camera work or live publication.
    guard recovery.reserve(id, model: self) else {
      setPhase(.cameraBusy)
      return
    }
    let operation = Operation(id: id, driver: hardware.makeDriver())
    self.operation = operation
    liveGeneration = id
    isStarting = true
    var startFailed = false
    do {
      try operation.driver.start { [weak self] event in
        self?.receive(event, generation: id)
      }
    } catch {
      startFailed = true
    }
    isStarting = false
    // A synchronous callback may have revoked Start. Stop only after start has returned,
    // so partial resources allocated later in the driver's start are also torn down.
    if let next = deferredEnd {
      deferredEnd = nil
      endSession(then: next)
      return
    }
    if startFailed {
      endSession(then: .failed)
      return
    }
    guard self.operation?.id == id, liveGeneration == id, !closeRequested,
      scene == .active
    else { return }
    clearTimestamps()
    publish(State(phase: .live(.waitingForCamera)))
  }

  /// Revokes callbacks before touching the driver. Startup and teardown cannot be nested.
  @discardableResult
  private func endSession(then next: FaceGuidePhase) -> Bool {
    pendingPermission = nil
    liveGeneration = nil
    clearTimestamps()
    if isStarting {
      if closeRequested || deferredEnd == nil { deferredEnd = closeRequested ? .ready : next }
      return false
    }
    guard !isStopping else { return false }
    guard let operation else {
      publish(State(phase: next, readyToDismiss: closeRequested))
      return true
    }
    return teardown(operation, then: next)
  }

  /// Release and bookkeeping commit before publication can start a successor.
  @discardableResult
  private func teardown(_ operation: Operation, then next: FaceGuidePhase) -> Bool {
    guard self.operation?.id == operation.id, !isStopping, !isStarting else { return false }
    liveGeneration = nil
    clearTimestamps()
    isStopping = true
    do {
      try operation.driver.stop()
    } catch {
      isStopping = false
      publish(State(phase: .stopFailed))
      return false
    }
    guard recovery.release(operation.id, model: self) else {
      isStopping = false
      publish(State(phase: .stopFailed))
      return false
    }
    self.operation = nil
    isStopping = false
    publish(State(phase: closeRequested ? .ready : next, readyToDismiss: closeRequested))
    return true
  }

  private func receive(_ event: FaceGuideEvent, generation: UUID) {
    guard generation == liveGeneration, operation?.id == generation else { return }
    switch event {
    case .frame(let frame):
      if !isStarting { apply(frame) }
    case .interrupted: endSession(then: .interrupted)
    case .failed: endSession(then: .failed)
    }
  }

  private func apply(_ frame: FaceGuideFrame) {
    guard frame.faceTracked else {
      clearTimestamps()
      publish(State(phase: .live(.noFace)))
      return
    }
    if frame.depthCaptured { lastDepth = frame.timestamp }
    let depthActive = lastDepth.map { (0...Self.depthWindow).contains(frame.timestamp - $0) }
    let faceWasTracked = phase == .live(.depthPending) || phase == .live(.tracking)
    var next = State(phase: .live(depthActive == true ? .tracking : .depthPending))
    if let reading = FaceGuideMovement(jawOpen: frame.jawOpen, mouthPucker: frame.mouthPucker) {
      // Geometry updates every frame; these relative movement indicators update at 10 Hz.
      if faceWasTracked, let movement, let lastMovement,
        frame.timestamp - lastMovement < Self.movementInterval
      {
        next.movement = movement
      } else {
        next.movement = reading
        lastMovement = frame.timestamp
      }
    } else {
      lastMovement = nil
    }
    // No writes after publication: a subscriber may synchronously close or start again.
    publish(next)
  }

  private func clearTimestamps() {
    lastMovement = nil
    lastDepth = nil
  }

  private func setPhase(_ next: FaceGuidePhase) {
    var state = committedState
    state.phase = next
    publish(state)
  }

  private func publish(_ next: State) {
    guard committedState != next else { return }
    committedState = next
    publications.append(next)
    guard !isPublishing else { return }
    isPublishing = true
    defer { isPublishing = false }
    while !publications.isEmpty { emittedState = publications.removeFirst() }
  }
}
