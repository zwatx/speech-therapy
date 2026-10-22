#if DEBUG
  import Combine
  import Dispatch
  import Foundation
  import XCTest

  @testable import CadenceLearner

  /// Generated permission/driver events only. These tests do not open a camera or audio device.
  @MainActor
  final class DirectPracticeMirrorTests: XCTestCase {
    func testConstructionAndEligibilityChangesAreInertAndSimulatorFallbackDoesNotPrompt() {
      let context = Context(permission: .notDetermined, supported: false)
      context.mirror.eligibilityChanged(.ready)
      context.mirror.eligibilityChanged(.recording)
      context.mirror.eligibilityChanged(.review)
      context.mirror.sceneChanged(.active)
      XCTAssertEqual(context.permission.requests, 0)
      XCTAssertEqual(context.driver.count(.factory), 0)
      context.mirror.show(eligibility: .ready)
      XCTAssertEqual(context.mirror.state, .unavailable)
      XCTAssertEqual(context.permission.requests, 0)
      XCTAssertFalse(context.mirror.blocksRecordForCameraPermission)
      XCTAssertFalse(context.mirror.interactiveDismissDisabled)
    }

    func testBothGrantAndActivationOrdersStartOnlyAfterBothGates() async {
      for grantFirst in [true, false] {
        let context = Context(permission: .notDetermined)
        context.mirror.show(eligibility: .ready)
        context.mirror.sceneChanged(.inactive)
        XCTAssertTrue(context.mirror.preservesAudioDuringCameraPermissionInactive)
        if grantFirst {
          context.permission.complete(true)
          guard case .awaitingActive = context.mirror.state else {
            XCTFail("Grant while inactive must wait")
            continue
          }
          XCTAssertEqual(context.driver.count(.factory), 0)
          context.mirror.sceneChanged(.active)
        } else {
          context.mirror.sceneChanged(.active)
          XCTAssertEqual(context.driver.count(.factory), 0)
          context.permission.complete(true)
        }
        await waitForLive(context.mirror)
        XCTAssertFalse(context.mirror.blocksRecordForCameraPermission)
        XCTAssertFalse(context.mirror.preservesAudioDuringCameraPermissionInactive)
        XCTAssertEqual(context.permission.requests, 1)
        let released = await context.mirror.requestStop(reason: .hide).released()
        XCTAssertTrue(released)
      }
    }

    func testActiveGrantAndDeniedPermissionDoNotKeepRecordPermissionGateBlocked() async {
      let denied = Context(permission: .notDetermined)
      denied.mirror.show(eligibility: .ready)
      denied.permission.complete(false)
      XCTAssertEqual(denied.mirror.state, .denied)
      XCTAssertFalse(denied.mirror.blocksRecordForCameraPermission)
      XCTAssertEqual(denied.driver.count(.factory), 0)
      XCTAssertTrue(denied.mirror.isReleasedForClose)
      let granted = Context(permission: .notDetermined)
      granted.mirror.show(eligibility: .ready)
      granted.permission.complete(true)
      await waitForLive(granted.mirror)
      let released = await granted.mirror.requestStop(reason: .close).released()
      XCTAssertTrue(released)
    }

    func testCancelCloseAndBackgroundInvalidateEveryPendingGrantOrdering() async {
      for reason in [DirectPracticeMirrorStopReason.cancel, .close, .background, .completion] {
        for grantBeforeRevocation in [true, false] {
          let context = Context(permission: .notDetermined)
          context.mirror.show(eligibility: .ready)
          context.mirror.sceneChanged(.inactive)
          if grantBeforeRevocation { context.permission.complete(true) }
          let stop = context.mirror.requestStop(reason: reason)
          // No driver: this settles even if the OS callback never arrives.
          let released = await stop.released()
          XCTAssertTrue(released)
          XCTAssertTrue(context.mirror.isReleasedForClose)
          XCTAssertFalse(context.mirror.blocksRecordForCameraPermission)
          if !grantBeforeRevocation { context.permission.complete(true) }
          context.mirror.sceneChanged(.active)
          XCTAssertEqual(context.mirror.state, .off)
          XCTAssertEqual(context.driver.count(.factory), 0)
        }
      }
    }

    func testLateFirstRequestCannotReplaceSecondRequest() async {
      let context = Context(permission: .notDetermined)
      context.mirror.show(eligibility: .ready)
      _ = context.mirror.requestStop(reason: .cancel)
      context.mirror.show(eligibility: .ready)
      XCTAssertEqual(context.permission.requests, 2)
      context.permission.complete(true, index: 0)
      guard case .permissionPending = context.mirror.state else {
        return XCTFail("Old grant must not resolve new request")
      }
      XCTAssertEqual(context.driver.count(.factory), 0)
      context.permission.complete(true, index: 1)
      await waitForLive(context.mirror)
      let released = await context.mirror.requestStop(reason: .hide).released()
      XCTAssertTrue(released)
    }

    func testSynchronousPermissionCompletionAndReentrantPermissionCancelAreSafe() async {
      let immediate = Context(permission: .notDetermined)
      immediate.permission.synchronousResult = true
      immediate.mirror.show(eligibility: .ready)
      await waitForLive(immediate.mirror)
      let released = await immediate.mirror.requestStop(reason: .hide).released()
      XCTAssertTrue(released)
      let cancelled = Context(permission: .notDetermined)
      let subscription = cancelled.mirror.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .permissionPending = state { _ = cancelled.mirror.requestStop(reason: .cancel) }
        }
      }
      cancelled.mirror.show(eligibility: .ready)
      XCTAssertEqual(cancelled.permission.requests, 0)
      XCTAssertEqual(cancelled.mirror.state, .off)
      XCTAssertFalse(cancelled.mirror.blocksRecordForCameraPermission)
      withExtendedLifetime(subscription) {}
    }

    func testMicrophonePermissionStopsLiveCameraAndAuthorizedShowWorksDuringRecordingAndReview()
      async
    {
      let context = Context(permission: .authorized)
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      context.mirror.eligibilityChanged(.microphonePermission)
      XCTAssertFalse(context.mirror.blocksRecordForCameraPermission)
      let release = context.mirror.requestStop(reason: .inactive)
      let released = await release.released()
      XCTAssertTrue(released)
      context.mirror.show(eligibility: .microphonePermission)
      XCTAssertEqual(context.driver.count(.factory), 1)
      for phase in [DirectPracticeMirrorEligibility.recording, .review] {
        context.mirror.show(eligibility: phase)
        await waitForLive(context.mirror)
        XCTAssertEqual(context.permission.requests, 0)
        let stopped = await context.mirror.requestStop(reason: .hide).released()
        XCTAssertTrue(stopped)
      }
      XCTAssertEqual(context.driver.count(.factory), 3)
    }

    func testUnknownCameraNeverPromptsDuringMicrophoneRecordingOrReview() {
      let context = Context(permission: .notDetermined)
      for phase in [DirectPracticeMirrorEligibility.microphonePermission, .recording, .review] {
        context.mirror.show(eligibility: phase)
      }
      XCTAssertEqual(context.permission.requests, 0)
      XCTAssertEqual(context.driver.count(.factory), 0)
      XCTAssertFalse(context.mirror.blocksRecordForCameraPermission)
    }

    func testInactiveLiveCameraStopsAndActiveDoesNotResumeIt() async {
      let context = Context(permission: .authorized)
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      context.mirror.sceneChanged(.inactive)
      let released = await context.mirror.requestStop(reason: .inactive).released()
      XCTAssertTrue(released)
      context.mirror.sceneChanged(.active)
      XCTAssertEqual(context.mirror.state, .off)
      XCTAssertEqual(context.driver.count(.factory), 1)
    }

    func testDuplicateShowCreatesOneOwnerAndCloseCannotReviveAfterRelease() async {
      let context = Context(permission: .authorized)
      context.mirror.show(eligibility: .ready)
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      XCTAssertEqual(context.driver.count(.factory), 1)
      let first = acknowledgement(context.mirror.requestStop(reason: .close))
      let second = acknowledgement(context.mirror.requestStop(reason: .close))
      XCTAssertTrue(first === second)
      let receipt = await first.value()
      XCTAssertTrue(first.confirmsRelease(receipt))
      XCTAssertTrue(context.mirror.isReleasedForClose)
      context.mirror.show(eligibility: .ready)
      XCTAssertEqual(context.driver.count(.factory), 1)
    }

    func testEveryHeldWorkerStageRevokesSynchronouslyAndRetainsOwnerUntilRelease() async {
      for held in [ControlledMirrorDriver.Stage.factory, .configure, .start] {
        for reason in [
          DirectPracticeMirrorStopReason.cancel, .hide, .inactive, .close, .background,
        ] {
          let context = Context(permission: .authorized, blocked: [held, .release])
          defer { context.driver.releaseAll() }
          context.mirror.show(eligibility: .ready)
          await entered(context.driver, held)
          let owner = context.runtime.currentOwner!
          let original = acknowledgement(context.mirror.requestStop(reason: reason))
          XCTAssertEqual(context.mirror.state, .stopping(owner))
          XCTAssertNotNil(context.recovery.runtime)
          XCTAssertNil(original.receipt)
          XCTAssertFalse(context.mirror.isReleasedForClose)
          XCTAssertFalse(context.mirror.blocksRecordForCameraPermission)
          context.driver.release(held)
          await entered(context.driver, .release)
          XCTAssertEqual(context.recovery.owner, owner)
          XCTAssertNil(original.receipt)
          if held != .start {
            XCTAssertEqual(context.driver.count(.start), 0)
          } else {
            XCTAssertEqual(context.driver.count(.start), 1)
          }  // Already entered, then stopped.
          context.driver.release(.release)
          let receipt = await original.value()
          XCTAssertTrue(original.confirmsRelease(receipt))
          XCTAssertNil(context.recovery.owner)
          XCTAssertFalse(context.driver.calledOnMainThread)
        }
      }
    }

    func testFailedStartCleansPartialResourcesAndFailedCleanupRequiresExplicitRetry() async {
      for failing in [ControlledMirrorDriver.Stage.configure, .start] {
        let context = Context(permission: .authorized, failStart: failing, cleanupFailures: 1)
        context.mirror.show(eligibility: .ready)
        await waitForFailure(context.mirror)
        let owner = context.runtime.currentOwner!
        let original = context.runtime.requestStop(owner: owner)!
        let negative = await original.value()
        XCTAssertEqual(negative.result, .cleanupUnconfirmed)
        XCTAssertTrue(original === context.runtime.requestStop(owner: owner))
        XCTAssertEqual(context.driver.count(.factory), 1)
        XCTAssertNotNil(context.recovery.runtime)
        let retry = context.mirror.retryStop()!
        let released = await retry.value()
        XCTAssertTrue(retry.confirmsRelease(released))
        XCTAssertEqual(original.receipt, negative)
        XCTAssertEqual(context.driver.count(.factory), 1)
        XCTAssertEqual(context.driver.count(.release), 2)
        XCTAssertNil(context.recovery.owner)
        XCTAssertEqual(context.mirror.state, .unavailable)
      }
      let cleanFailure = Context(permission: .authorized, failStart: .configure)
      cleanFailure.mirror.show(eligibility: .ready)
      await waitForState(cleanFailure.mirror, .unavailable)
      XCTAssertNil(cleanFailure.recovery.owner)
      XCTAssertEqual(cleanFailure.driver.count(.release), 1)
    }

    func testOriginalNegativeIsImmutableConcurrentExplicitRetriesShareNewAckAndMatchIdentity() async
    {
      let context = Context(permission: .authorized, blockedRetry: true, cleanupFailures: 1)
      defer { context.driver.releaseAll() }
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      let original = acknowledgement(context.mirror.requestStop(reason: .hide))
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      XCTAssertTrue(original === acknowledgement(context.mirror.requestStop(reason: .close)))
      XCTAssertEqual(context.driver.count(.release), 1)
      let retry = context.mirror.retryStop()!
      let duplicate = context.mirror.retryStop()!
      XCTAssertTrue(retry === duplicate)
      XCTAssertFalse(original === retry)
      await retryEntered(context.driver)
      XCTAssertNil(retry.receipt)
      XCTAssertNotNil(context.recovery.owner)
      context.driver.releaseRetry()
      let released = await retry.value()
      XCTAssertEqual(original.receipt, negative)
      XCTAssertTrue(retry.confirmsRelease(released))
      XCTAssertFalse(original.confirmsRelease(released))
      XCTAssertFalse(
        retry.confirmsRelease(
          .init(
            owner: .init(id: UUID()),
            attemptID: retry.attemptID, result: .released)))
      XCTAssertFalse(
        retry.confirmsRelease(
          .init(
            owner: retry.owner,
            attemptID: UUID(), result: .released)))
      XCTAssertEqual(context.runtime.releasedReceipt(owner: retry.owner), released)
      XCTAssertTrue(context.mirror.isReleasedForClose)
    }

    func testReentrantStartingStopRegistersBeforePublishingAndReentrantFailureRetryIsSafe() async {
      let cancelled = Context(permission: .authorized)
      var original: PracticeMirrorCleanup?
      let cancelSubscription = cancelled.mirror.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .starting = state {
            original = self.acknowledgement(cancelled.mirror.requestStop(reason: .cancel))
          }
        }
      }
      cancelled.mirror.show(eligibility: .ready)
      let receipt = await original!.value()
      XCTAssertEqual(receipt.result, .released)
      XCTAssertEqual(cancelled.driver.count(.factory), 0)
      XCTAssertEqual(cancelled.mirror.state, .off)
      withExtendedLifetime(cancelSubscription) {}

      let failure = Context(permission: .authorized, cleanupFailures: 1)
      failure.mirror.show(eligibility: .ready)
      await waitForLive(failure.mirror)
      var retry: PracticeMirrorCleanup?
      let retrySubscription = failure.mirror.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if case .stopFailed = state { retry = failure.mirror.retryStop() }
        }
      }
      let failedOriginal = acknowledgement(failure.mirror.requestStop(reason: .hide))
      let failedReceipt = await failedOriginal.value()
      await waitUntil { retry != nil }
      let retryReceipt = await retry!.value()
      XCTAssertEqual(failedOriginal.receipt, failedReceipt)
      XCTAssertEqual(failedReceipt.result, .cleanupUnconfirmed)
      XCTAssertEqual(retryReceipt.result, .released)
      XCTAssertEqual(failure.mirror.state, .off)
      withExtendedLifetime(retrySubscription) {}
    }

    func testFailedOwnerSurvivesDroppedScreenAndLaterSessionRetriesWithoutNewDriver() async {
      let recovery = ProcessPracticeMirrorRecovery()
      let driver = ControlledMirrorDriver(cleanupFailures: 1)
      var runtime: PracticeMirrorRuntime? = PracticeMirrorRuntime(recovery: recovery) {
        _ in
        driver.make()
        return driver
      }
      var mirror: DirectPracticeMirror? = DirectPracticeMirror(
        permission: ControlledMirrorPermission(.authorized),
        runtime: runtime!, recovery: recovery, initialScene: .active)
      mirror!.show(eligibility: .ready)
      await waitForLive(mirror!)
      let owner = runtime!.currentOwner!
      let original = acknowledgement(mirror!.requestStop(reason: .disappeared))
      weak var weakMirror = mirror
      weak var weakRuntime = runtime
      mirror = nil
      runtime = nil
      XCTAssertNil(weakMirror)
      XCTAssertNotNil(weakRuntime)  // Slot owns pending cleanup, not this screen/session.
      let failedReceipt = await original.value()
      XCTAssertNotNil(weakRuntime)  // Failed cleanup still retains the exact driver/runtime.
      XCTAssertEqual(failedReceipt.result, .cleanupUnconfirmed)
      XCTAssertEqual(recovery.owner, owner)
      let nextDriver = ControlledMirrorDriver()
      let nextRuntime = PracticeMirrorRuntime(recovery: recovery) { _ in
        nextDriver.make()
        return nextDriver
      }
      let next = DirectPracticeMirror(
        permission: ControlledMirrorPermission(.authorized),
        runtime: nextRuntime, recovery: recovery, initialScene: .active)
      XCTAssertEqual(next.state, .stopFailed(owner))
      next.show(eligibility: .ready)
      XCTAssertEqual(nextDriver.count(.factory), 0)
      XCTAssertFalse(nextRuntime.start(owner: .init(id: UUID())))
      let retry = next.retryStop()!
      let released = await retry.value()
      XCTAssertEqual(released.owner, owner)
      XCTAssertEqual(released.result, .released)
      XCTAssertNil(recovery.owner)
      XCTAssertEqual(driver.count(.factory), 1)
      XCTAssertEqual(nextDriver.count(.factory), 0)
      XCTAssertEqual(original.receipt, failedReceipt)
    }

    func testOldStopAndOldReceiptCannotClearSuccessorAndCompletionStopDoesNotAutoRestart() async {
      let context = Context(permission: .authorized)
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      let oldOwner = context.runtime.currentOwner!
      let old = acknowledgement(context.mirror.requestStop(reason: .completion))
      let released = await old.value()
      XCTAssertTrue(old.confirmsRelease(released))
      context.mirror.eligibilityChanged(.ready)  // Practice more/restart is inert.
      context.mirror.sceneChanged(.active)
      XCTAssertEqual(context.driver.count(.factory), 1)
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      let newOwner = context.runtime.currentOwner!
      XCTAssertNotEqual(newOwner, oldOwner)
      XCTAssertTrue(old === context.runtime.requestStop(owner: oldOwner))
      XCTAssertEqual(context.recovery.owner, newOwner)
      XCTAssertEqual(context.mirror.state, .live(newOwner))
      let next = acknowledgement(context.mirror.requestStop(reason: .hide))
      XCTAssertFalse(next.confirmsRelease(released))
      let stopped = await next.value()
      XCTAssertEqual(stopped.result, .released)
    }

    func testPendingDisappearanceRetainsRuntimeUntilHeldCleanupReleases() async {
      let recovery = ProcessPracticeMirrorRecovery()
      let driver = ControlledMirrorDriver(blocked: [.release])
      defer { driver.releaseAll() }
      var runtime: PracticeMirrorRuntime? = PracticeMirrorRuntime(recovery: recovery) {
        _ in
        driver.make()
        return driver
      }
      var mirror: DirectPracticeMirror? = DirectPracticeMirror(
        permission: ControlledMirrorPermission(.authorized), runtime: runtime!, recovery: recovery,
        initialScene: .active)
      mirror!.show(eligibility: .ready)
      await waitForLive(mirror!)
      let acknowledgement = acknowledgement(mirror!.requestStop(reason: .disappeared))
      weak var weakRuntime = runtime
      mirror = nil
      runtime = nil
      await entered(driver, .release)
      XCTAssertNotNil(weakRuntime)
      XCTAssertNotNil(recovery.owner)
      XCTAssertNil(acknowledgement.receipt)
      driver.release(.release)
      let receipt = await acknowledgement.value()
      XCTAssertEqual(receipt.result, .released)
      XCTAssertNil(recovery.owner)
    }

    func testReleasedPublicationMayCreateSuccessorWithoutOldCompletionClearingIt() async {
      let context = Context(permission: .authorized)
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      let oldOwner = context.runtime.currentOwner!
      let successor = PracticeMirrorOwner(id: UUID())
      var installed = false
      let subscription = context.runtime.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if state == .idle, !installed {
            installed = true
            XCTAssertTrue(context.runtime.start(owner: successor))
          }
        }
      }
      let original = context.runtime.requestStop(owner: oldOwner)!
      let receipt = await original.value()
      await waitUntil { context.runtime.state == .live(successor) }
      XCTAssertTrue(installed)
      XCTAssertEqual(context.recovery.owner, successor)
      XCTAssertEqual(receipt.owner, oldOwner)
      XCTAssertTrue(original === context.runtime.requestStop(owner: oldOwner))
      let released = await context.runtime.requestStop(owner: successor)!.value()
      XCTAssertEqual(released.owner, successor)
      withExtendedLifetime(subscription) {}
    }

    func testCancellingAnAwaiterDoesNotCancelRetainedCameraCleanup() async {
      let context = Context(permission: .authorized, blocked: [.release])
      defer { context.driver.releaseAll() }
      context.mirror.show(eligibility: .ready)
      await waitForLive(context.mirror)
      let original = acknowledgement(context.mirror.requestStop(reason: .hide))
      let waiter = Task { @MainActor in await original.value() }
      waiter.cancel()
      await entered(context.driver, .release)
      XCTAssertNil(original.receipt)
      XCTAssertNotNil(context.recovery.owner)
      context.driver.release(.release)
      let receipt = await waiter.value
      XCTAssertTrue(original.confirmsRelease(receipt))
      XCTAssertNil(context.recovery.owner)
    }

    func testRetiredFacadeCannotAdoptOrStopRecoveringFacadesSuccessorAfterHeldRelease() async {
      for reason in [DirectPracticeMirrorStopReason.close, .disappeared] {
        let context = Context(permission: .notDetermined, blocked: [.release])
        defer { context.driver.releaseAll() }
        let first = context.mirror
        first.show(eligibility: .ready)
        context.permission.complete(true)
        await waitForLive(first)
        let oldOwner = context.runtime.currentOwner!
        let original = acknowledgement(first.requestStop(reason: reason))
        await entered(context.driver, .release)
        let unusedDriver = ControlledMirrorDriver()
        let unusedRuntime = PracticeMirrorRuntime(recovery: context.recovery) {
          _ in
          unusedDriver.make()
          return unusedDriver
        }
        let recovering = DirectPracticeMirror(
          permission: ControlledMirrorPermission(.authorized),
          runtime: unusedRuntime, recovery: context.recovery, initialScene: .active)
        XCTAssertEqual(recovering.state, .stopping(oldOwner))
        XCTAssertFalse(first.isReleasedForClose)
        XCTAssertTrue(original === acknowledgement(first.requestStop(reason: .close)))
        context.driver.release(.release)
        let oldRelease = await original.value()
        XCTAssertEqual(oldRelease.result, .released)
        recovering.show(eligibility: .ready)
        await waitForLive(recovering)
        let successor = context.runtime.currentOwner!
        XCTAssertNotEqual(successor, oldOwner)
        XCTAssertEqual(first.state, .off)
        XCTAssertEqual(first.exactReleasedReceipt, oldRelease)
        XCTAssertTrue(first.isReleasedForClose)
        XCTAssertFalse(first.interactiveDismissDisabled)
        XCTAssertTrue(original === acknowledgement(first.requestStop(reason: .close)))
        first.sceneChanged(.inactive)
        first.sceneChanged(.background)
        _ = first.requestStop(reason: .disappeared)
        first.eligibilityChanged(.microphonePermission)
        context.permission.complete(true)  // Duplicate old OS callback is inert.
        first.sceneChanged(.active)
        first.show(eligibility: .ready)
        XCTAssertNil(first.retryStop())
        XCTAssertEqual(context.recovery.owner, successor)
        XCTAssertEqual(recovering.state, .live(successor))
        XCTAssertEqual(context.driver.count(.release), 1)
        XCTAssertEqual(context.driver.count(.factory), 2)
        XCTAssertEqual(unusedDriver.count(.factory), 0)
        let ownStop = acknowledgement(recovering.requestStop(reason: .hide))
        let successorRelease = await ownStop.value()
        XCTAssertEqual(successorRelease.owner, successor)
        XCTAssertEqual(successorRelease.result, .released)
        // Runtime's original-success cache has now rolled over to the successor.
        XCTAssertEqual(first.exactReleasedReceipt, oldRelease)
        XCTAssertTrue(first.isReleasedForClose)
        XCTAssertTrue(original === acknowledgement(first.requestStop(reason: .close)))
        XCTAssertEqual(context.driver.count(.release), 2)
      }
    }

    func testRetiredFacadeKeepsSuccessfulSharedRetryWhenSuccessorRetryReplacesRuntimeEvidence()
      async
    {
      let recovery = ProcessPracticeMirrorRecovery()
      let firstDriver = ControlledMirrorDriver(blockedRetry: true, cleanupFailures: 1)
      let successorDriver = ControlledMirrorDriver(cleanupFailures: 1)
      defer {
        firstDriver.releaseAll()
        successorDriver.releaseAll()
      }
      let factory = ControlledMirrorFactory([firstDriver, successorDriver])
      let runtime = PracticeMirrorRuntime(recovery: recovery) { _ in factory.make() }
      let first = DirectPracticeMirror(
        permission: ControlledMirrorPermission(.authorized),
        runtime: runtime, recovery: recovery, initialScene: .active)
      first.show(eligibility: .ready)
      await waitForLive(first)
      let oldOwner = runtime.currentOwner!
      let original = acknowledgement(first.requestStop(reason: .close))
      let negative = await original.value()
      XCTAssertEqual(negative.result, .cleanupUnconfirmed)
      let unusedDriver = ControlledMirrorDriver()
      let unusedRuntime = PracticeMirrorRuntime(recovery: recovery) { _ in
        unusedDriver.make()
        return unusedDriver
      }
      let recovering = DirectPracticeMirror(
        permission: ControlledMirrorPermission(.authorized),
        runtime: unusedRuntime, recovery: recovery, initialScene: .active)
      XCTAssertEqual(recovering.state, .stopFailed(oldOwner))
      let retry = recovering.retryStop()!
      XCTAssertTrue(retry === first.retryStop())
      await retryEntered(firstDriver)
      XCTAssertFalse(first.isReleasedForClose)
      firstDriver.releaseRetry()
      let oldRelease = await retry.value()
      XCTAssertEqual(oldRelease.owner, oldOwner)
      XCTAssertEqual(oldRelease.result, .released)
      XCTAssertEqual(original.receipt, negative)
      recovering.show(eligibility: .ready)
      await waitForLive(recovering)
      let successor = runtime.currentOwner!
      XCTAssertNotEqual(successor, oldOwner)
      XCTAssertEqual(first.exactReleasedReceipt, oldRelease)
      XCTAssertTrue(first.isReleasedForClose)
      XCTAssertFalse(first.interactiveDismissDisabled)
      XCTAssertTrue(original === acknowledgement(first.requestStop(reason: .close)))
      first.sceneChanged(.inactive)
      first.sceneChanged(.background)
      _ = first.requestStop(reason: .disappeared)
      XCTAssertNil(first.retryStop())
      XCTAssertEqual(recovery.owner, successor)
      XCTAssertEqual(successorDriver.count(.release), 0)
      let successorOriginal = acknowledgement(recovering.requestStop(reason: .hide))
      let successorNegative = await successorOriginal.value()
      XCTAssertEqual(successorNegative.result, .cleanupUnconfirmed)
      let successorRetry = recovering.retryStop()!
      let successorRelease = await successorRetry.value()
      XCTAssertEqual(successorRelease.owner, successor)
      XCTAssertEqual(successorRelease.result, .released)
      // Both bounded runtime caches rolled over.
      XCTAssertNil(runtime.releasedReceipt(owner: oldOwner))
      // Old facade still holds exact old proof.
      XCTAssertEqual(first.exactReleasedReceipt, oldRelease)
      XCTAssertTrue(first.isReleasedForClose)
      XCTAssertTrue(original === acknowledgement(first.requestStop(reason: .close)))
      XCTAssertEqual(original.receipt, negative)
      XCTAssertEqual(successorOriginal.receipt, successorNegative)
      XCTAssertEqual(firstDriver.count(.release), 2)
      XCTAssertEqual(successorDriver.count(.release), 2)
      XCTAssertEqual(unusedDriver.count(.factory), 0)
    }

    func testReentrantIdleAcquisitionByRecoveryFacadeCannotTransferSuccessorToRetiredFacade() async
    {
      for retryRequired in [false, true] {
        let recovery = ProcessPracticeMirrorRecovery()
        let driver = ControlledMirrorDriver(
          blocked: [.release], blockedRetry: retryRequired,
          cleanupFailures: retryRequired ? 1 : 0)
        defer { driver.releaseAll() }
        let runtime = PracticeMirrorRuntime(recovery: recovery) { _ in
          driver.make()
          return driver
        }
        var recovering: DirectPracticeMirror?
        var acquireOnIdle = false
        // Register BEFORE the original facade so acquisition occurs before its idle subscriber
        // reads the runtime getter. This exercises the shared-runtime reentry window directly.
        let subscription = runtime.statePublisher.sink { state in
          MainActor.assumeIsolated {
            if state == .idle, acquireOnIdle {
              acquireOnIdle = false
              recovering!.show(eligibility: .ready)
            }
          }
        }
        let first = DirectPracticeMirror(
          permission: ControlledMirrorPermission(.authorized),
          runtime: runtime, recovery: recovery, initialScene: .active)
        first.show(eligibility: .ready)
        await waitForLive(first)
        let oldOwner = runtime.currentOwner!
        let original = acknowledgement(first.requestStop(reason: .disappeared))
        await entered(driver, .release)
        let unusedDriver = ControlledMirrorDriver()
        let unusedRuntime = PracticeMirrorRuntime(recovery: recovery) { _ in
          unusedDriver.make()
          return unusedDriver
        }
        recovering = DirectPracticeMirror(
          permission: ControlledMirrorPermission(.authorized),
          runtime: unusedRuntime, recovery: recovery, initialScene: .active)
        acquireOnIdle = true
        driver.release(.release)
        let originalReceipt = await original.value()
        let oldRelease: PracticeMirrorCleanupReceipt
        if retryRequired {
          XCTAssertEqual(originalReceipt.result, .cleanupUnconfirmed)
          let retry = recovering!.retryStop()!
          XCTAssertTrue(retry === first.retryStop())
          await retryEntered(driver)
          driver.releaseRetry()
          oldRelease = await retry.value()
        } else {
          oldRelease = originalReceipt
        }
        await waitForLive(recovering!)
        XCTAssertFalse(acquireOnIdle)
        let successor = runtime.currentOwner!
        XCTAssertNotEqual(successor, oldOwner)
        XCTAssertEqual(first.state, .off)
        XCTAssertTrue(first.isReleasedForClose)
        XCTAssertEqual(first.exactReleasedReceipt, oldRelease)
        XCTAssertFalse(first.interactiveDismissDisabled)
        XCTAssertTrue(original === acknowledgement(first.requestStop(reason: .close)))
        first.sceneChanged(.inactive)
        first.sceneChanged(.background)
        _ = first.requestStop(reason: .disappeared)
        XCTAssertNil(first.retryStop())
        XCTAssertEqual(recovery.owner, successor)
        XCTAssertEqual(recovering!.state, .live(successor))
        XCTAssertEqual(driver.count(.release), retryRequired ? 2 : 1)
        XCTAssertEqual(original.receipt, originalReceipt)
        let successorStop = acknowledgement(recovering!.requestStop(reason: .hide))
        let successorRelease = await successorStop.value()
        XCTAssertEqual(successorRelease.owner, successor)
        XCTAssertEqual(successorRelease.result, .released)
        XCTAssertEqual(first.exactReleasedReceipt, oldRelease)
        XCTAssertTrue(first.isReleasedForClose)
        XCTAssertEqual(unusedDriver.count(.factory), 0)
        withExtendedLifetime(subscription) {}
      }
    }

    private func acknowledgement(_ stop: DirectPracticeMirrorStop) -> PracticeMirrorCleanup {
      guard case .owned(let acknowledgement) = stop else {
        fatalError("Test expected a registered camera owner")
      }
      return acknowledgement
    }

    private func entered(_ driver: ControlledMirrorDriver, _ stage: ControlledMirrorDriver.Stage)
      async
    {
      let result = await XCTWaiter.fulfillment(of: [driver.entered(stage)], timeout: 2)
      XCTAssertEqual(result, .completed)
    }
    private func retryEntered(_ driver: ControlledMirrorDriver) async {
      let result = await XCTWaiter.fulfillment(of: [driver.retryEntered], timeout: 2)
      XCTAssertEqual(result, .completed)
    }
    private func waitUntil(_ predicate: @MainActor () -> Bool) async {
      let deadline = ContinuousClock.now + .seconds(2)
      while !predicate() && ContinuousClock.now < deadline { await Task.yield() }
      XCTAssertTrue(predicate())
    }
    private func waitForLive(_ mirror: DirectPracticeMirror) async {
      await waitUntil {
        if case .live = mirror.state { return true }
        return false
      }
    }
    private func waitForFailure(_ mirror: DirectPracticeMirror) async {
      await waitUntil {
        if case .stopFailed = mirror.state { return true }
        return false
      }
    }
    private func waitForState(_ mirror: DirectPracticeMirror, _ state: DirectPracticeMirrorState)
      async
    {
      await waitUntil { mirror.state == state }
    }
  }

  @MainActor
  private final class Context {
    let recovery: ProcessPracticeMirrorRecovery
    let permission: ControlledMirrorPermission
    let driver: ControlledMirrorDriver
    let runtime: PracticeMirrorRuntime
    let mirror: DirectPracticeMirror
    init(
      permission status: PracticeMirrorPermission, supported: Bool = true,
      blocked: Set<ControlledMirrorDriver.Stage> = [], blockedRetry: Bool = false,
      failStart: ControlledMirrorDriver.Stage? = nil, cleanupFailures: Int = 0
    ) {
      let recovery = ProcessPracticeMirrorRecovery()
      self.recovery = recovery
      permission = ControlledMirrorPermission(status, supported: supported)
      driver = ControlledMirrorDriver(
        blocked: blocked, blockedRetry: blockedRetry,
        failStart: failStart, cleanupFailures: cleanupFailures)
      let driver = self.driver
      runtime = PracticeMirrorRuntime(recovery: recovery) { _ in
        driver.make()
        return driver
      }
      mirror = DirectPracticeMirror(
        permission: permission, runtime: runtime, recovery: recovery,
        initialScene: .active)
    }
  }

  @MainActor
  private final class ControlledMirrorPermission: PracticeMirrorPermissionProviding {
    let isSupported: Bool
    var status: PracticeMirrorPermission
    var synchronousResult: Bool?
    private(set) var requests = 0
    private var callbacks: [@MainActor (Bool) -> Void] = []
    init(_ status: PracticeMirrorPermission, supported: Bool = true) {
      self.status = status
      isSupported = supported
    }
    func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
      requests += 1
      callbacks.append(completion)
      if let synchronousResult { complete(synchronousResult, index: callbacks.count - 1) }
    }
    func complete(_ result: Bool, index: Int = 0) {
      status = result ? .authorized : .denied
      callbacks[index](result)
    }
  }

  /// Only injected fake methods run on the actual serial worker. Gates have finite failure caps;
  /// no sleep, physical capture, framework import, fixture image or prerecorded media is used.
  private final class ControlledMirrorDriver: PracticeMirrorDriver, @unchecked Sendable {
    enum Stage: CaseIterable, Hashable { case factory, configure, start, release }
    enum Failure: Error { case injected, gateTimedOut }
    private let lock = NSLock()
    private let blocked: Set<Stage>
    private let blockedRetry: Bool
    private let failStart: Stage?
    private let cleanupFailures: Int
    private let gates: [Stage: DispatchSemaphore]
    private let expectations: [Stage: XCTestExpectation]
    let retryEntered = XCTestExpectation(description: "entered explicit retry")
    private let retryGate = DispatchSemaphore(value: 0)
    private var counts: [Stage: Int] = [:]
    private var mainThread = false
    private var factoryTimedOut = false

    init(
      blocked: Set<Stage> = [], blockedRetry: Bool = false, failStart: Stage? = nil,
      cleanupFailures: Int = 0
    ) {
      self.blocked = blocked
      self.blockedRetry = blockedRetry
      self.failStart = failStart
      self.cleanupFailures = cleanupFailures
      gates = Dictionary(
        uniqueKeysWithValues: Stage.allCases.map { ($0, DispatchSemaphore(value: 0)) })
      expectations = Dictionary(
        uniqueKeysWithValues: Stage.allCases.map {
          ($0, XCTestExpectation(description: "entered \($0)"))
        })
    }
    func count(_ stage: Stage) -> Int { lock.withLock { counts[stage, default: 0] } }
    var calledOnMainThread: Bool { lock.withLock { mainThread } }
    func entered(_ stage: Stage) -> XCTestExpectation { expectations[stage]! }
    func release(_ stage: Stage) { gates[stage]!.signal() }
    func releaseRetry() { retryGate.signal() }
    func releaseAll() {
      for stage in Stage.allCases { release(stage) }
      releaseRetry()
    }
    func make() {
      do { try visit(.factory) } catch { lock.withLock { factoryTimedOut = true } }
    }
    func configure() throws {
      if lock.withLock({ factoryTimedOut }) { throw Failure.gateTimedOut }
      try visit(.configure)
    }
    func start() throws { try visit(.start) }
    func stopAndReleasePreviewResources() throws { try visit(.release) }

    private func visit(_ stage: Stage) throws {
      let count = lock.withLock {
        counts[stage, default: 0] += 1
        mainThread = mainThread || Thread.isMainThread
        return counts[stage]!
      }
      if count == 1 { expectations[stage]!.fulfill() }
      if blocked.contains(stage), count == 1,
        gates[stage]!.wait(timeout: .now() + 5) != .success
      {
        throw Failure.gateTimedOut
      }
      if stage == .release, count == 2 {
        retryEntered.fulfill()
        if blockedRetry, retryGate.wait(timeout: .now() + 5) != .success {
          throw Failure.gateTimedOut
        }
      }
      if stage == failStart || (stage == .release && count <= cleanupFailures) {
        throw Failure.injected
      }
    }
  }
#endif

#if DEBUG
  /// Test-only factory switches exact fake drivers between two owners; no framework work occurs.
  private final class ControlledMirrorFactory: @unchecked Sendable {
    private let lock = NSLock()
    private let drivers: [ControlledMirrorDriver]
    private var next = 0
    init(_ drivers: [ControlledMirrorDriver]) { self.drivers = drivers }
    func make() -> any PracticeMirrorDriver {
      let driver = lock.withLock {
        precondition(next < drivers.count, "Unexpected additional test camera owner")
        let driver = drivers[next]
        next += 1
        return driver
      }
      driver.make()
      return driver
    }
  }
#endif
