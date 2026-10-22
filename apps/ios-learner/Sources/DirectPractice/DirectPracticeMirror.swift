import Combine
import Foundation

enum PracticeMirrorPermission: Equatable {
  case notDetermined, authorized, denied
}

@MainActor
protocol PracticeMirrorPermissionProviding: AnyObject {
  var isSupported: Bool { get }
  var status: PracticeMirrorPermission { get }
  /// Only the explicit ready-screen Show action may call this. Completion can be synchronous;
  /// service must bridge callbacks to MainActor. Cancellation revokes UI identity, not OS UI.
  func requestPermission(completion: @escaping @MainActor (Bool) -> Void)
}

enum DirectPracticeMirrorEligibility: Equatable {
  case ready, microphonePermission, recording, review, unavailable
  var permitsAuthorizedShow: Bool { self == .ready || self == .recording || self == .review }
}

enum DirectPracticeMirrorScene: Equatable { case active, inactive, background }

enum DirectPracticeMirrorState: Equatable {
  case off
  case permissionPending(UUID)
  case awaitingActive(UUID)
  case starting(PracticeMirrorOwner)
  case live(PracticeMirrorOwner)
  case stopping(PracticeMirrorOwner)
  case stopFailed(PracticeMirrorOwner)
  case denied
  case unavailable
}

enum DirectPracticeMirrorStopReason: Equatable {
  case hide, cancel, close, disappeared, completion, inactive, background
}

/// Explicit no-owner evidence is different from an unknown missing cleanup handle.
enum DirectPracticeMirrorStop {
  case noCameraOwner
  case owned(PracticeMirrorCleanup)

  @MainActor
  func released() async -> Bool {
    switch self {
    case .noCameraOwner: return true
    case .owned(let acknowledgement):
      let receipt = await acknowledgement.value()
      return acknowledgement.confirmsRelease(receipt)
    }
  }
}

/// Plain local mirror controller. It cannot read a frame, write audio flags, prompt for a
/// microphone, score speech, save media or post anything. Construction is inert.
@MainActor
final class DirectPracticeMirror: ObservableObject {
  @Published private var emittedState: DirectPracticeMirrorState = .off
  private var committedState: DirectPracticeMirrorState = .off
  var state: DirectPracticeMirrorState { committedState }
  var statePublisher: AnyPublisher<DirectPracticeMirrorState, Never> {
    $emittedState.eraseToAnyPublisher()
  }
  private var pendingStates: [DirectPracticeMirrorState] = []
  private var isPublishing = false
  private let permission: any PracticeMirrorPermissionProviding
  private let runtime: PracticeMirrorRuntime
  private var subscription: AnyCancellable?
  private var scene: DirectPracticeMirrorScene
  private var eligibility: DirectPracticeMirrorEligibility = .unavailable
  private var closeRequested = false
  // A facade binds only at recovery attachment or its own explicit acquisition. Runtime
  // publication must never transfer a later screen's successor to a retired facade.
  private var boundOwner: PracticeMirrorOwner?
  private var originalCleanup: PracticeMirrorCleanup?
  private var boundReleasedReceipt: PracticeMirrorCleanupReceipt?
  private var pendingPermission: PermissionAttempt?

  private struct PermissionAttempt {
    let id = UUID()
    var granted: Bool?
  }

  init(
    permission: any PracticeMirrorPermissionProviding, runtime: PracticeMirrorRuntime,
    recovery: ProcessPracticeMirrorRecovery = .shared,
    initialScene: DirectPracticeMirrorScene = .inactive
  ) {
    self.permission = permission
    // Rebind the exact old runtime when another screen's pending/failed owner survives.
    self.runtime = recovery.runtime ?? runtime
    self.scene = initialScene
    boundOwner = self.runtime.currentOwner
    originalCleanup = boundOwner.flatMap { self.runtime.cleanupAcknowledgement(owner: $0) }
    subscription = self.runtime.statePublisher.sink { [weak self] _ in
      MainActor.assumeIsolated { self?.receiveRuntimeState() }
    }
  }

  /// Narrow permission-alert inference. Keep an audio take only for this own ready-screen
  /// attempt, including grant-before-active ordering. Background always overrides it.
  var preservesAudioDuringCameraPermissionInactive: Bool { pendingPermission != nil }
  /// Serialize only this permission interval, never live/starting/failed camera cleanup.
  var blocksRecordForCameraPermission: Bool { pendingPermission != nil }
  var interactiveDismissDisabled: Bool {
    reconcileReleaseEvidence()
    return pendingPermission != nil || (boundOwner != nil && boundReleasedReceipt == nil)
  }
  var isReleasedForClose: Bool {
    reconcileReleaseEvidence()
    guard pendingPermission == nil else { return false }
    // Another facade's live successor cannot revoke this owner's exact positive evidence.
    return boundOwner == nil || boundReleasedReceipt != nil
  }
  var exactReleasedReceipt: PracticeMirrorCleanupReceipt? {
    reconcileReleaseEvidence()
    return boundReleasedReceipt
  }

  var presentation: PracticeMirrorPresentation? { runtime.presentation }

  /// Session calls before publishing microphone-permission phase. It never waits for camera
  /// release to request microphone permission; the independent owner still retains cleanup.
  func eligibilityChanged(_ next: DirectPracticeMirrorEligibility) {
    eligibility = next
    if next == .microphonePermission {
      _ = requestStop(reason: .inactive)
    }
  }

  func show(eligibility next: DirectPracticeMirrorEligibility) {
    eligibility = next
    guard !closeRequested, scene == .active, next.permitsAuthorizedShow,
      pendingPermission == nil, runtime.currentOwner == nil
    else { return }
    guard permission.isSupported else {
      publish(.unavailable)
      return
    }
    switch permission.status {
    case .authorized: startIfEligible()
    case .denied: publish(.denied)
    case .notDetermined:
      // Never show a camera permission prompt while recording or holding/replaying a take.
      guard next == .ready else { return }
      let attempt = PermissionAttempt()
      pendingPermission = attempt
      publish(.permissionPending(attempt.id))
      // State subscribers may synchronously Cancel, Close or change scenes/eligibility.
      guard pendingPermission?.id == attempt.id, scene == .active, eligibility == .ready,
        !closeRequested
      else {
        if pendingPermission?.id == attempt.id { _ = requestStop(reason: .cancel) }
        return
      }
      permission.requestPermission { [weak self] granted in
        self?.permissionCompleted(id: attempt.id, granted: granted)
      }
    }
  }

  func sceneChanged(_ next: DirectPracticeMirrorScene) {
    scene = next
    switch next {
    case .active:
      if pendingPermission?.granted == true { startGrantedAttemptIfEligible() }
    case .inactive:
      // Only this exact pending permission attempt survives alert inactivity. A live or
      // starting owner is always revoked, including a microphone permission dialog.
      if pendingPermission == nil { _ = requestStop(reason: .inactive) }
    case .background: _ = requestStop(reason: .background)
    }
  }

  @discardableResult
  func requestStop(reason: DirectPracticeMirrorStopReason) -> DirectPracticeMirrorStop {
    if reason == .close || reason == .disappeared { closeRequested = true }
    pendingPermission = nil  // Revoke before any publication, task or framework callback.
    reconcileReleaseEvidence()
    guard let owner = boundOwner else {
      publish(.off)
      return .noCameraOwner
    }
    // Keep the stable original even after a successful retry or runtime evidence rollover.
    // Ordinary duplicate Close must not silently substitute the explicit retry receipt.
    let acknowledgement =
      boundReleasedReceipt == nil
      ? runtime.requestStop(owner: owner) : originalCleanup
    guard let acknowledgement = acknowledgement ?? originalCleanup else {
      preconditionFailure("Bound mirror owner has no cleanup acknowledgement")
    }
    originalCleanup = acknowledgement
    if boundReleasedReceipt != nil { publish(.off) }
    return .owned(acknowledgement)
  }

  func retryStop() -> PracticeMirrorCleanup? {
    reconcileReleaseEvidence()
    guard let owner = boundOwner, boundReleasedReceipt == nil,
      runtime.currentOwner == owner
    else { return nil }
    return runtime.retryStop(owner: owner)
  }

  private func permissionCompleted(id: UUID, granted: Bool) {
    guard var attempt = pendingPermission, attempt.id == id, !closeRequested else { return }
    guard granted else {
      pendingPermission = nil
      publish(.denied)
      return
    }
    attempt.granted = true
    pendingPermission = attempt
    if scene == .active { startGrantedAttemptIfEligible() } else { publish(.awaitingActive(id)) }
  }

  private func startGrantedAttemptIfEligible() {
    guard let attempt = pendingPermission, attempt.granted == true,
      scene == .active, !closeRequested, eligibility == .ready
    else { return }
    pendingPermission = nil
    startIfEligible()
  }

  private func startIfEligible() {
    guard scene == .active, !closeRequested, eligibility.permitsAuthorizedShow,
      pendingPermission == nil, runtime.currentOwner == nil
    else { return }
    reconcileReleaseEvidence()
    guard boundOwner == nil || boundReleasedReceipt != nil else { return }
    let previousOwner = boundOwner
    let previousOriginal = originalCleanup
    let previousReleased = boundReleasedReceipt
    let owner = PracticeMirrorOwner(id: UUID())
    boundOwner = owner
    originalCleanup = nil
    boundReleasedReceipt = nil
    // runtime.start registers the exact owner before any synchronous Starting subscriber.
    // receiveRuntimeState captures its original acknowledgement before publishing to the view.
    if !runtime.start(owner: owner) {
      boundOwner = previousOwner
      originalCleanup = previousOriginal
      boundReleasedReceipt = previousReleased
      publish(.unavailable)
    }
  }

  private func reconcileReleaseEvidence() {
    guard boundReleasedReceipt == nil, let owner = boundOwner else { return }
    // Original success is permanently queryable through the retained acknowledgement. An
    // explicit retry by either recovering facade is captured on the release publication, before
    // a successor's later completion may replace the runtime's bounded evidence cache.
    if let receipt = originalCleanup?.receipt, originalCleanup?.confirmsRelease(receipt) == true {
      boundReleasedReceipt = receipt
    } else if let receipt = runtime.releasedReceipt(owner: owner),
      receipt.owner == owner, receipt.result == .released
    {
      boundReleasedReceipt = receipt
    }
  }

  private func receiveRuntimeState() {
    reconcileReleaseEvidence()
    // A reentrant idle subscriber may already have installed a different owner before this
    // subscriber reads the committed getter. Settle our own release, then ignore that successor.
    if boundReleasedReceipt != nil, pendingPermission == nil {
      publish(runtime.failedStartOwner == boundOwner && boundOwner != nil ? .unavailable : .off)
    }
    // Use committed getter; Published event delivery may lag a reentrant revocation.
    switch runtime.state {
    case .idle:
      guard boundOwner == nil, pendingPermission == nil else { return }
      publish(.off)
    case .starting(let owner), .live(let owner), .stopping(let owner), .stopFailed(let owner):
      guard owner == boundOwner, boundReleasedReceipt == nil else { return }
      if originalCleanup == nil {
        originalCleanup = runtime.cleanupAcknowledgement(owner: owner)
      }
      switch runtime.state {
      case .starting: publish(.starting(owner))
      case .live: publish(.live(owner))
      case .stopping: publish(.stopping(owner))
      case .stopFailed: publish(.stopFailed(owner))
      case .idle: break
      }
    }
  }

  private func publish(_ next: DirectPracticeMirrorState) {
    guard committedState != next else { return }
    committedState = next
    pendingStates.append(next)
    guard !isPublishing else { return }
    isPublishing = true
    defer { isPublishing = false }
    while !pendingStates.isEmpty { emittedState = pendingStates.removeFirst() }
  }
}
