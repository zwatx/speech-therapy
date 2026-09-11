import Combine
import Foundation
import UIKit
import XCTest

@testable import CadenceLearner

/// Generated permission/driver events only. These tests open no camera, ARKit session or
/// audio device, and use an isolated camera lease and recovery slot.
@MainActor
final class FaceGuideTests: XCTestCase {
  func testConstructionIsInertAndUnsupportedNeverPromptsOrStarts() {
    let supported = Context(permission: .notDetermined)
    XCTAssertEqual(supported.model.phase, .ready)
    XCTAssertEqual(supported.hardware.requests.count, 0)
    XCTAssertTrue(supported.hardware.drivers.isEmpty)
    XCTAssertNil(supported.lease.owner)
    XCTAssertFalse(supported.model.interactiveDismissDisabled)

    let unsupported = Context(permission: .authorized, supported: false)
    XCTAssertEqual(unsupported.model.phase, .unsupported)
    unsupported.model.start()
    XCTAssertEqual(unsupported.model.phase, .unsupported)
    XCTAssertEqual(unsupported.hardware.requests.count, 0)
    XCTAssertTrue(unsupported.hardware.drivers.isEmpty)
    XCTAssertNil(unsupported.lease.owner)
  }

  func testDeniedPermissionNeverStartsCamera() {
    let alreadyDenied = Context(permission: .denied)
    alreadyDenied.model.start()
    XCTAssertEqual(alreadyDenied.model.phase, .denied)
    XCTAssertEqual(alreadyDenied.hardware.requests.count, 0)
    XCTAssertTrue(alreadyDenied.hardware.drivers.isEmpty)

    let declined = Context(permission: .notDetermined)
    declined.model.start()
    XCTAssertEqual(declined.model.phase, .requestingPermission)
    XCTAssertTrue(declined.model.interactiveDismissDisabled)
    declined.hardware.complete(false)
    XCTAssertEqual(declined.model.phase, .denied)
    XCTAssertTrue(declined.hardware.drivers.isEmpty)
    XCTAssertNil(declined.lease.owner)
    XCTAssertFalse(declined.model.interactiveDismissDisabled)
  }

  func testReturningFromSettingsOffersStartWithoutStartingCamera() {
    let context = Context(permission: .denied)
    context.model.start()
    XCTAssertEqual(context.model.phase, .denied)
    context.model.sceneChanged(.background)
    context.hardware.permission = .authorized
    context.model.sceneChanged(.active)
    XCTAssertEqual(context.model.phase, .ready)
    XCTAssertTrue(context.hardware.drivers.isEmpty)
    XCTAssertTrue(context.hardware.requests.isEmpty)
    XCTAssertNil(context.lease.owner)
    context.model.start()
    XCTAssertEqual(context.hardware.drivers.count, 1)
    XCTAssertEqual(context.model.phase, .live(.waitingForCamera))
    XCTAssertTrue(context.model.close())
    XCTAssertNil(context.lease.owner)
  }

  func testCloseAndBackgroundBeforeGrantPreventLateStart() {
    for grantBeforeRevocation in [true, false] {
      let closed = Context(permission: .notDetermined)
      closed.model.start()
      closed.model.sceneChanged(.inactive)
      if grantBeforeRevocation { closed.hardware.complete(true) }
      XCTAssertTrue(closed.model.close())
      XCTAssertTrue(closed.model.readyToDismiss)
      XCTAssertFalse(closed.model.interactiveDismissDisabled)
      if !grantBeforeRevocation { closed.hardware.complete(true) }
      closed.model.sceneChanged(.active)
      closed.model.start()
      XCTAssertTrue(closed.hardware.drivers.isEmpty)
      XCTAssertNil(closed.lease.owner)

      let backgrounded = Context(permission: .notDetermined)
      backgrounded.model.start()
      backgrounded.model.sceneChanged(.inactive)
      if grantBeforeRevocation { backgrounded.hardware.complete(true) }
      backgrounded.model.sceneChanged(.background)
      XCTAssertEqual(backgrounded.model.phase, .paused)
      if !grantBeforeRevocation { backgrounded.hardware.complete(true) }
      backgrounded.model.sceneChanged(.active)
      XCTAssertEqual(backgrounded.model.phase, .paused)
      XCTAssertTrue(backgrounded.hardware.drivers.isEmpty)
      XCTAssertNil(backgrounded.lease.owner)
    }
  }

  func testPermissionAlertInactivityPreservesAttemptInBothGrantOrders() {
    for grantFirst in [true, false] {
      let context = Context(permission: .notDetermined)
      context.model.start()
      context.model.sceneChanged(.inactive)
      XCTAssertEqual(context.model.phase, .requestingPermission)
      if grantFirst {
        context.hardware.complete(true)
        XCTAssertEqual(context.model.phase, .awaitingActive)
        XCTAssertTrue(context.hardware.drivers.isEmpty)
        XCTAssertNil(context.lease.owner)
        context.model.sceneChanged(.active)
      } else {
        context.model.sceneChanged(.active)
        XCTAssertTrue(context.hardware.drivers.isEmpty)
        context.hardware.complete(true)
      }
      XCTAssertEqual(context.model.phase, .live(.waitingForCamera))
      XCTAssertEqual(context.hardware.requests.count, 1)
      XCTAssertEqual(context.hardware.drivers.count, 1)
      XCTAssertNotNil(context.lease.owner)
      XCTAssertTrue(context.model.close())
      XCTAssertNil(context.lease.owner)
    }
  }

  func testExistingCameraOwnerBlocksStartAndLeaseGatesAreExactAndReciprocal() {
    let context = Context(permission: .authorized)
    let mirrorOwner = UUID()
    XCTAssertTrue(context.lease.acquire(mirrorOwner))
    context.model.start()
    XCTAssertEqual(context.model.phase, .cameraBusy)
    XCTAssertTrue(context.hardware.drivers.isEmpty)
    XCTAssertEqual(context.lease.owner, mirrorOwner)
    // Stop never releases a lease this model does not own.
    context.model.stop()
    XCTAssertEqual(context.lease.owner, mirrorOwner)

    // A camera owner that appears during the permission prompt still wins.
    let prompted = Context(permission: .notDetermined)
    prompted.model.start()
    XCTAssertTrue(prompted.lease.acquire(mirrorOwner))
    prompted.hardware.complete(true)
    XCTAssertEqual(prompted.model.phase, .cameraBusy)
    XCTAssertTrue(prompted.hardware.drivers.isEmpty)
    XCTAssertEqual(prompted.lease.owner, mirrorOwner)

    XCTAssertTrue(context.lease.release(mirrorOwner))
    context.model.start()
    guard case .live = context.model.phase else { return XCTFail("Expected live face guide") }
    let faceOwner = context.lease.owner
    XCTAssertNotNil(faceOwner)
    XCTAssertFalse(context.lease.acquire(UUID()))
    XCTAssertFalse(context.lease.release(mirrorOwner))
    let mirror = PracticeMirrorRuntime(
      recovery: ProcessPracticeMirrorRecovery(cameraLease: context.lease),
      factory: { _ in UnusedMirrorDriver() })
    XCTAssertFalse(mirror.start(owner: PracticeMirrorOwner(id: UUID())))
    XCTAssertEqual(context.lease.owner, faceOwner)

    context.model.stop()
    XCTAssertEqual(context.model.phase, .ready)
    XCTAssertNil(context.lease.owner)
  }

  func testRepeatStartKeepsOnePermissionRequestAndOneOperation() {
    let pending = Context(permission: .notDetermined)
    pending.model.start()
    pending.model.start()
    XCTAssertEqual(pending.hardware.requests.count, 1)

    let live = Context(permission: .authorized)
    live.model.start()
    let owner = live.lease.owner
    live.model.start()
    live.model.start()
    XCTAssertEqual(live.hardware.drivers.count, 1)
    XCTAssertEqual(live.hardware.drivers.first?.starts, 1)
    XCTAssertEqual(live.lease.owner, owner)
  }

  func testCloseCleanupFailureRetainsExactDriverAndOwnerUntilRetry() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    let owner = try XCTUnwrap(context.lease.owner)
    driver.stopFailures = 1

    XCTAssertFalse(context.model.close())
    XCTAssertEqual(context.model.phase, .stopFailed)
    XCTAssertFalse(context.model.readyToDismiss)
    XCTAssertTrue(context.model.interactiveDismissDisabled)
    XCTAssertEqual(context.lease.owner, owner)
    XCTAssertTrue(context.recovery.model === context.model)
    XCTAssertNil(context.model.cameraSurface)
    context.model.start()
    XCTAssertEqual(context.hardware.drivers.count, 1)

    XCTAssertTrue(context.model.retryStop())
    XCTAssertEqual(driver.stops, 2)
    XCTAssertEqual(context.hardware.drivers.count, 1)
    XCTAssertNil(context.lease.owner)
    XCTAssertNil(context.recovery.model)
    XCTAssertTrue(context.model.readyToDismiss)
    XCTAssertFalse(context.model.interactiveDismissDisabled)
  }

  func testDisappearedCleanupFailureIsRetainedAndRecoverableOnReopen() throws {
    let lease = ProcessCameraLease()
    let recovery = FaceGuideRecovery(cameraLease: lease)
    let hardware = FakeFaceGuideHardware(permission: .authorized)
    weak var original: FaceGuideModel?
    do {
      let model = FaceGuideModel(hardware: hardware, recovery: recovery, initialScene: .active)
      original = model
      model.start()
      hardware.drivers.first?.stopFailures = 1
      model.viewDisappeared()
      XCTAssertEqual(model.phase, .stopFailed)
      // Disappearance never retries implicitly.
      model.viewDisappeared()
      XCTAssertEqual(hardware.drivers.first?.stops, 1)
    }
    XCTAssertNotNil(original, "Recovery must strongly retain the unresolved owner")
    XCTAssertNotNil(lease.owner)

    let reopened = FaceGuideModel.make(
      hardware: FakeFaceGuideHardware(permission: .authorized), recovery: recovery)
    XCTAssertTrue(reopened === original)
    XCTAssertEqual(reopened.phase, .stopFailed)
    XCTAssertFalse(reopened.readyToDismiss)
    XCTAssertTrue(reopened.retryStop())
    XCTAssertEqual(reopened.phase, .ready)
    XCTAssertFalse(reopened.readyToDismiss)
    XCTAssertNil(lease.owner)
    XCTAssertNil(recovery.model)

    let fresh = FaceGuideModel.make(
      hardware: FakeFaceGuideHardware(permission: .authorized), recovery: recovery)
    XCTAssertFalse(fresh === reopened)
  }

  func testDisappearingWhileLiveStopsAndReleasesWithoutRetention() {
    let context = Context(permission: .authorized)
    context.model.start()
    context.model.viewDisappeared()
    XCTAssertEqual(context.hardware.drivers.first?.stops, 1)
    XCTAssertNil(context.lease.owner)
    XCTAssertNil(context.recovery.model)
    context.model.sceneChanged(.active)
    context.model.start()
    XCTAssertEqual(context.hardware.drivers.count, 1)
  }

  func testStaleGenerationCallbacksAreIgnored() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let stale = try XCTUnwrap(context.hardware.drivers.first?.events)
    context.model.stop()
    stale(.frame(frame(at: 1, depth: true, jaw: 0.4)))
    XCTAssertEqual(context.model.phase, .ready)
    XCTAssertNil(context.model.movement)

    context.model.start()
    let current = try XCTUnwrap(context.hardware.drivers.last)
    stale(.failed)
    stale(.interrupted)
    stale(.frame(frame(at: 2, depth: true, jaw: 0.4)))
    XCTAssertEqual(context.model.phase, .live(.waitingForCamera))
    XCTAssertNil(context.model.movement)
    XCTAssertEqual(current.stops, 0)
    XCTAssertNotNil(context.lease.owner)
  }

  func testDepthNeedsCurrentFrameEvidenceAndLostFaceClearsMovementAndDepth() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    XCTAssertEqual(context.model.phase, .live(.waitingForCamera))
    XCTAssertFalse(context.model.depthActive)

    driver.send(.frame(frame(at: 0, faceTracked: false)))
    XCTAssertEqual(context.model.phase, .live(.noFace))
    driver.send(.frame(frame(at: 0.1, depth: false, jaw: 0.3)))
    XCTAssertEqual(context.model.phase, .live(.depthPending))
    XCTAssertFalse(context.model.depthActive)
    XCTAssertEqual(context.model.movement?.jawOpening, Double(Float(0.3)))
    driver.send(.frame(frame(at: 0.2, depth: true, jaw: 0.3)))
    XCTAssertEqual(context.model.phase, .live(.tracking))
    XCTAssertTrue(context.model.depthActive)
    // Depth arrives at a lower rate; a recent depth frame still counts.
    driver.send(.frame(frame(at: 0.3, depth: false, jaw: 0.3)))
    XCTAssertTrue(context.model.depthActive)
    driver.send(.frame(frame(at: 0.9, depth: false, jaw: 0.3)))
    XCTAssertEqual(context.model.phase, .live(.depthPending))

    driver.send(.frame(frame(at: 1.0, depth: true, jaw: 0.3)))
    XCTAssertTrue(context.model.depthActive)
    driver.send(.frame(frame(at: 1.05, faceTracked: false)))
    XCTAssertEqual(context.model.phase, .live(.noFace))
    XCTAssertNil(context.model.movement)
    XCTAssertFalse(context.model.depthActive)
    // Depth evidence from before the loss does not carry over.
    driver.send(.frame(frame(at: 1.1, depth: false, jaw: 0.3)))
    XCTAssertEqual(context.model.phase, .live(.depthPending))
  }

  func testMovementUpdatesAreThrottledButLossIsImmediate() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    driver.send(.frame(frame(at: 10, depth: true, jaw: 0.2)))
    driver.send(.frame(frame(at: 10.05, depth: true, jaw: 0.6)))
    XCTAssertEqual(context.model.movement?.jawOpening, Double(Float(0.2)))
    driver.send(.frame(frame(at: 10.11, depth: true, jaw: 0.7)))
    XCTAssertEqual(context.model.movement?.jawOpening, Double(Float(0.7)))
    driver.send(.frame(frame(at: 10.12, faceTracked: false)))
    XCTAssertNil(context.model.movement)
    driver.send(.frame(frame(at: 10.13, depth: true, jaw: 0.5)))
    XCTAssertEqual(context.model.movement?.jawOpening, Double(Float(0.5)))
  }

  func testSceneLossStopsClearsAndForegroundNeverRestarts() throws {
    for scene in [FaceGuideScene.inactive, .background] {
      let context = Context(permission: .authorized)
      context.model.start()
      let driver = try XCTUnwrap(context.hardware.drivers.first)
      driver.send(.frame(frame(at: 0, depth: true, jaw: 0.5)))
      XCTAssertNotNil(context.model.movement)

      context.model.sceneChanged(scene)
      XCTAssertEqual(context.model.phase, .paused)
      XCTAssertNil(context.model.movement)
      XCTAssertFalse(context.model.depthActive)
      XCTAssertEqual(driver.stops, 1)
      XCTAssertNil(context.lease.owner)

      context.model.sceneChanged(.active)
      XCTAssertEqual(context.model.phase, .paused)
      XCTAssertEqual(context.hardware.drivers.count, 1)
      context.model.start()
      XCTAssertEqual(context.hardware.drivers.count, 2)
      XCTAssertTrue(context.model.close())
    }
  }

  func testDriverFailuresTearDownAndReleaseExactLease() throws {
    let startFailure = Context(permission: .authorized)
    startFailure.hardware.failNextStart = true
    startFailure.model.start()
    XCTAssertEqual(startFailure.model.phase, .failed)
    XCTAssertEqual(startFailure.hardware.drivers.first?.stops, 1)
    XCTAssertNil(startFailure.lease.owner)
    XCTAssertNil(startFailure.recovery.model)
    startFailure.model.start()
    XCTAssertEqual(startFailure.hardware.drivers.count, 2)
    guard case .live = startFailure.model.phase else { return XCTFail("Retry should start") }

    let failures: [(FaceGuideEvent, FaceGuidePhase)] = [
      (.failed, .failed), (.interrupted, .interrupted),
    ]
    for (event, expected) in failures {
      let context = Context(permission: .authorized)
      context.model.start()
      let driver = try XCTUnwrap(context.hardware.drivers.first)
      driver.send(.frame(frame(at: 0, depth: true, jaw: 0.5)))
      driver.send(event)
      XCTAssertEqual(context.model.phase, expected)
      XCTAssertNil(context.model.movement)
      XCTAssertEqual(driver.stops, 1)
      XCTAssertNil(context.lease.owner)
      // The framework's interruption ending never restarts the camera.
      driver.send(.frame(frame(at: 1, depth: true, jaw: 0.5)))
      XCTAssertEqual(context.model.phase, expected)
    }

    let unconfirmed = Context(permission: .authorized)
    unconfirmed.hardware.failNextStart = true
    unconfirmed.hardware.nextStopFailures = 1
    unconfirmed.model.start()
    XCTAssertEqual(unconfirmed.model.phase, .stopFailed)
    XCTAssertNotNil(unconfirmed.lease.owner)
    XCTAssertTrue(unconfirmed.model.retryStop())
    XCTAssertEqual(unconfirmed.hardware.drivers.count, 1)
    XCTAssertNil(unconfirmed.lease.owner)
  }

  func testCoefficientsAreFiniteAndClamped() throws {
    for value: Float? in [nil, .nan, .infinity, -.infinity] {
      XCTAssertNil(FaceGuideMovement.sanitized(value))
      XCTAssertNil(FaceGuideMovement(jawOpen: value, mouthPucker: 0.2))
      XCTAssertNil(FaceGuideMovement(jawOpen: 0.2, mouthPucker: value))
    }
    XCTAssertEqual(FaceGuideMovement.sanitized(-0.3), 0)
    XCTAssertEqual(FaceGuideMovement.sanitized(1.7), 1)
    XCTAssertEqual(FaceGuideMovement.sanitized(0.25), 0.25)

    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    driver.send(.frame(frame(at: 0, depth: true, jaw: 0.4)))
    XCTAssertNotNil(context.model.movement)
    driver.send(.frame(frame(at: 1, depth: true, jaw: .nan)))
    XCTAssertEqual(context.model.phase, .live(.tracking))
    XCTAssertNil(context.model.movement)
  }

  func testCloseFromPermissionPublicationDoesNotRequestPermission() {
    let context = Context(permission: .notDetermined)
    let subscription = context.model.statePublisher.dropFirst().sink { state in
      if state.phase == .requestingPermission { _ = context.model.close() }
    }
    context.model.start()
    XCTAssertTrue(context.hardware.requests.isEmpty)
    XCTAssertTrue(context.hardware.drivers.isEmpty)
    XCTAssertTrue(context.model.readyToDismiss)
    XCTAssertEqual(context.model.phase, .ready)
    withExtendedLifetime(subscription) {}
  }

  func testSynchronousStartupTerminalEventsCleanAfterStartReturns() {
    for (event, phase) in [
      (FaceGuideEvent.failed, FaceGuidePhase.failed),
      (.interrupted, .interrupted),
    ] {
      let context = Context(permission: .authorized)
      context.hardware.onStart = { driver in driver.send(event) }
      context.model.start()
      XCTAssertEqual(context.model.phase, phase)
      XCTAssertEqual(context.hardware.drivers.first?.stops, 1)
      XCTAssertEqual(context.hardware.drivers.first?.stoppedInsideStart, false)
      XCTAssertNil(context.lease.owner)
      XCTAssertNil(context.model.movement)
    }
  }

  func testCloseAndSceneDepartureInsideStartDeferTeardown() {
    for closing in [true, false] {
      let context = Context(permission: .authorized)
      context.hardware.onStart = { driver in
        if closing {
          XCTAssertFalse(context.model.close())
        } else {
          context.model.sceneChanged(.background)
        }
        XCTAssertEqual(driver.stops, 0)
        XCTAssertNotNil(context.lease.owner)
        XCTAssertFalse(context.model.readyToDismiss)
      }
      context.model.start()
      XCTAssertEqual(context.hardware.drivers.first?.stops, 1)
      XCTAssertEqual(context.hardware.drivers.first?.stoppedInsideStart, false)
      XCTAssertEqual(context.model.phase, closing ? .ready : .paused)
      XCTAssertEqual(context.model.readyToDismiss, closing)
      XCTAssertNil(context.lease.owner)
    }
  }

  func testCloseFromLivePublicationCannotResurrectSession() {
    let context = Context(permission: .authorized)
    let subscription = context.model.statePublisher.dropFirst().sink { state in
      if case .live = state.phase { _ = context.model.close() }
    }
    context.model.start()
    XCTAssertEqual(context.model.phase, .ready)
    XCTAssertTrue(context.model.readyToDismiss)
    XCTAssertNil(context.model.movement)
    XCTAssertNil(context.lease.owner)
    XCTAssertEqual(context.hardware.drivers.first?.stops, 1)
    withExtendedLifetime(subscription) {}
  }

  func testCloseFromReadingAndClearedReadingPublicationDoesNotRecurse() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    var publications = 0
    let subscription = context.model.statePublisher.dropFirst().sink { _ in
      publications += 1
      _ = context.model.close()
    }
    driver.send(.frame(frame(at: 1, depth: true, jaw: 0.5)))
    XCTAssertEqual(publications, 2, "One frame and one fully committed close")
    XCTAssertEqual(context.model.phase, .ready)
    XCTAssertNil(context.model.movement)
    XCTAssertTrue(context.model.readyToDismiss)
    XCTAssertEqual(driver.stops, 1)
    driver.send(.frame(frame(at: 2, depth: true, jaw: 0.8)))
    XCTAssertNil(context.model.movement)
    XCTAssertEqual(publications, 2)
    withExtendedLifetime(subscription) {}
  }

  func testReadySubscriberCanStartSuccessorWithoutOldTeardownOverwritingIt() {
    let context = Context(permission: .authorized)
    context.model.start()
    let first = context.hardware.drivers[0]
    let subscription = context.model.statePublisher.dropFirst().sink { state in
      if state.phase == .ready { context.model.start() }
    }
    context.model.stop()
    XCTAssertEqual(context.hardware.drivers.count, 2)
    XCTAssertEqual(context.model.phase, .live(.waitingForCamera))
    XCTAssertEqual(first.stops, 1)
    XCTAssertNotNil(context.lease.owner)
    XCTAssertTrue(context.model.close())
    XCTAssertEqual(context.hardware.drivers[1].stops, 1)
    withExtendedLifetime(subscription) {}
  }

  func testCloseInsideDriverStopDoesNotNestCleanup() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    driver.onStop = { XCTAssertFalse(context.model.close()) }
    context.model.stop()
    XCTAssertEqual(driver.stops, 1)
    XCTAssertNil(context.lease.owner)
    XCTAssertEqual(context.model.phase, .ready)
    XCTAssertTrue(context.model.readyToDismiss)
  }

  func testSceneDepartureNeverImplicitlyRetriesFailedCleanup() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    driver.stopFailures = 1
    context.model.stop()
    context.model.sceneChanged(.inactive)
    context.model.sceneChanged(.background)
    XCTAssertEqual(context.model.phase, .stopFailed)
    XCTAssertEqual(driver.stops, 1)
    XCTAssertNotNil(context.lease.owner)
    XCTAssertTrue(context.model.retryStop())
  }

  func testPracticeTransitionCancelsPermissionWithoutPermanentlyClosingModel() {
    let context = Context(permission: .notDetermined)
    context.model.start()
    XCTAssertTrue(context.model.permissionPending)
    XCTAssertTrue(context.model.stopForPracticeTransition())
    context.hardware.complete(true)
    XCTAssertFalse(context.model.hasCameraOwner)
    XCTAssertTrue(context.hardware.drivers.isEmpty)
    context.hardware.permission = .authorized
    context.model.start()
    XCTAssertTrue(context.model.hasCameraOwner)
    XCTAssertTrue(context.model.stopForPracticeTransition())
    context.model.start()
    XCTAssertEqual(context.hardware.drivers.count, 2)
    XCTAssertTrue(context.model.stopForPracticeTransition())
  }

  func testPracticeTransitionNeverRetriesFailedTeardown() throws {
    let context = Context(permission: .authorized)
    context.model.start()
    let driver = try XCTUnwrap(context.hardware.drivers.first)
    driver.stopFailures = 1
    XCTAssertFalse(context.model.stopForPracticeTransition())
    XCTAssertFalse(context.model.stopForPracticeTransition())
    XCTAssertTrue(context.model.cleanupBlocked)
    XCTAssertEqual(driver.stops, 1)
    XCTAssertTrue(context.model.retryStop())
    XCTAssertFalse(context.model.cleanupBlocked)
    XCTAssertFalse(context.model.hasCameraOwner)
    context.model.start()
    XCTAssertEqual(context.hardware.drivers.count, 2)
    XCTAssertTrue(context.model.stopForPracticeTransition())
  }

  private func frame(
    at timestamp: TimeInterval, faceTracked: Bool = true, depth: Bool = false,
    jaw: Float? = nil
  ) -> FaceGuideFrame {
    FaceGuideFrame(
      timestamp: timestamp, faceTracked: faceTracked, depthCaptured: depth,
      jawOpen: faceTracked ? jaw : nil, mouthPucker: faceTracked ? 0.2 : nil)
  }
}

@MainActor
private struct Context {
  let lease: ProcessCameraLease
  let hardware: FakeFaceGuideHardware
  let recovery: FaceGuideRecovery
  let model: FaceGuideModel

  init(permission: FaceGuidePermission, supported: Bool = true) {
    lease = ProcessCameraLease()
    hardware = FakeFaceGuideHardware(permission: permission, supported: supported)
    recovery = FaceGuideRecovery(cameraLease: lease)
    model = FaceGuideModel(hardware: hardware, recovery: recovery, initialScene: .active)
  }
}

@MainActor
private final class FakeFaceGuideHardware: FaceGuideHardware {
  let isSupported: Bool
  var permission: FaceGuidePermission
  var failNextStart = false
  var nextStopFailures = 0
  var onStart: (@MainActor (FakeFaceGuideDriver) -> Void)?
  private(set) var requests: [@MainActor (Bool) -> Void] = []
  private(set) var drivers: [FakeFaceGuideDriver] = []

  init(permission: FaceGuidePermission, supported: Bool = true) {
    self.permission = permission
    isSupported = supported
  }

  func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
    requests.append(completion)
  }

  func complete(_ granted: Bool, index: Int = 0) { requests[index](granted) }

  func makeDriver() -> any FaceGuideDriver {
    let driver = FakeFaceGuideDriver(failStart: failNextStart, stopFailures: nextStopFailures)
    driver.onStart = onStart
    failNextStart = false
    nextStopFailures = 0
    drivers.append(driver)
    return driver
  }
}

@MainActor
private final class FakeFaceGuideDriver: FaceGuideDriver {
  private struct Failure: Error {}
  private let failStart: Bool
  var stopFailures: Int
  private(set) var starts = 0
  private(set) var stops = 0
  private var insideStart = false
  private(set) var stoppedInsideStart = false
  var onStop: (@MainActor () -> Void)?
  var onStart: (@MainActor (FakeFaceGuideDriver) -> Void)?
  // Retained after stop so tests can deliver deliberately stale callbacks.
  private(set) var events: (@MainActor (FaceGuideEvent) -> Void)?

  init(failStart: Bool, stopFailures: Int) {
    self.failStart = failStart
    self.stopFailures = stopFailures
  }

  var surface: UIView? { nil }

  func start(events: @escaping @MainActor (FaceGuideEvent) -> Void) throws {
    starts += 1
    self.events = events
    insideStart = true
    defer { insideStart = false }
    onStart?(self)
    if failStart { throw Failure() }
  }

  func stop() throws {
    stoppedInsideStart = stoppedInsideStart || insideStart
    stops += 1
    let callback = onStop
    onStop = nil
    callback?()
    if stopFailures > 0 {
      stopFailures -= 1
      throw Failure()
    }
  }

  func send(_ event: FaceGuideEvent) { events?(event) }
}

private final class UnusedMirrorDriver: PracticeMirrorDriver {
  func configure() throws {}
  func start() throws {}
  func stopAndReleasePreviewResources() throws {}
}
