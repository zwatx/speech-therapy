#if DEBUG
  import Combine
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class PracticeMirrorPresentationTests: XCTestCase {
    func testLateInstallCannotRestoreRevokedPreview() {
      let presentation = PracticeMirrorPresentation()
      let owner = PracticeMirrorOwner(id: UUID())
      presentation.prepare(owner: owner)
      presentation.revoke(owner: owner)
      presentation.install(owner: owner, source: .sample)
      XCTAssertNil(presentation.owner)
      XCTAssertNil(presentation.source)
    }

    func testOldRevokeAndInstallCannotReplaceSuccessor() {
      let presentation = PracticeMirrorPresentation()
      let old = PracticeMirrorOwner(id: UUID())
      let next = PracticeMirrorOwner(id: UUID())
      presentation.prepare(owner: old)
      presentation.install(owner: old, source: .sample)
      presentation.revoke(owner: old)
      presentation.prepare(owner: next)
      presentation.install(owner: next, source: .sample)
      presentation.revoke(owner: old)
      presentation.install(owner: old, source: .sample)
      XCTAssertEqual(presentation.owner, next)
      guard case .sample = presentation.source else { return XCTFail("Successor sample lost") }
    }

    func testInstallPublicationReentrantRevokeStaysRevoked() {
      let presentation = PracticeMirrorPresentation()
      let owner = PracticeMirrorOwner(id: UUID())
      var calls = 0
      let observation = presentation.objectWillChange.sink {
        MainActor.assumeIsolated {
          calls += 1
          if presentation.owner == owner { presentation.revoke(owner: owner) }
        }
      }
      presentation.prepare(owner: owner)
      presentation.install(owner: owner, source: .sample)
      XCTAssertEqual(calls, 2)
      XCTAssertNil(presentation.owner)
      XCTAssertNil(presentation.source)
      withExtendedLifetime(observation) {}
    }

    func testLivePublicationReentrantStopPreventsPreviewInstallation() async {
      let recovery = ProcessPracticeMirrorRecovery()
      let presentation = PracticeMirrorPresentation()
      let runtime = PracticeMirrorRuntime(recovery: recovery, presentation: presentation) { _ in
        Driver()
      }
      let owner = PracticeMirrorOwner(id: UUID())
      let observation = runtime.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if state == .live(owner) { _ = runtime.requestStop(owner: owner) }
        }
      }
      XCTAssertTrue(runtime.start(owner: owner))
      let cleanup = runtime.cleanupAcknowledgement(owner: owner)!
      let receipt = await cleanup.value()
      XCTAssertTrue(cleanup.confirmsRelease(receipt))
      XCTAssertNil(presentation.owner)
      XCTAssertNil(presentation.source)
      XCTAssertNil(recovery.owner)
      withExtendedLifetime(observation) {}
    }

    func testReleasePublicationCanStartSuccessorAndOldInterruptionCannotStopIt() async {
      let recovery = ProcessPracticeMirrorRecovery()
      let presentation = PracticeMirrorPresentation()
      let runtime = PracticeMirrorRuntime(recovery: recovery, presentation: presentation) { _ in
        Driver()
      }
      let old = PracticeMirrorOwner(id: UUID())
      let next = PracticeMirrorOwner(id: UUID())
      XCTAssertTrue(runtime.start(owner: old))
      await waitForLive(runtime, owner: old)
      var startedNext = false
      let observation = runtime.statePublisher.sink { state in
        MainActor.assumeIsolated {
          if state == .idle, !startedNext {
            startedNext = true
            XCTAssertTrue(runtime.start(owner: next))
          }
        }
      }
      let cleanup = runtime.requestStop(owner: old)!
      let receipt = await cleanup.value()
      XCTAssertTrue(cleanup.confirmsRelease(receipt))
      await waitForLive(runtime, owner: next)
      XCTAssertEqual(presentation.owner, next)
      runtime.unavailableAndStop(owner: old)
      XCTAssertEqual(runtime.currentOwner, next)
      XCTAssertEqual(runtime.state, .live(next))
      let nextCleanup = runtime.requestStop(owner: next)!
      let nextReceipt = await nextCleanup.value()
      XCTAssertTrue(nextCleanup.confirmsRelease(nextReceipt))
      withExtendedLifetime(observation) {}
    }

    func testUnexpectedInterruptionRemovesPreviewWithoutAutomaticRestart() async {
      let recovery = ProcessPracticeMirrorRecovery()
      let presentation = PracticeMirrorPresentation()
      let runtime = PracticeMirrorRuntime(recovery: recovery, presentation: presentation) { _ in
        Driver()
      }
      let owner = PracticeMirrorOwner(id: UUID())
      XCTAssertTrue(runtime.start(owner: owner))
      await waitForLive(runtime, owner: owner)
      XCTAssertEqual(presentation.owner, owner)
      runtime.unavailableAndStop(owner: owner)
      XCTAssertNil(presentation.owner)
      let cleanup = runtime.cleanupAcknowledgement(owner: owner)!
      let receipt = await cleanup.value()
      XCTAssertTrue(cleanup.confirmsRelease(receipt))
      XCTAssertNil(recovery.owner)
      XCTAssertEqual(runtime.failedStartOwner, owner)
      XCTAssertEqual(runtime.state, .idle)
      XCTAssertFalse(runtime.start(owner: owner), "Owner identities cannot be reused")
    }

    #if targetEnvironment(simulator)
      func testNormalSimulatorPermissionIsUnsupportedWithoutPrompt() {
        let permission = SystemPracticeMirrorPermission()
        XCTAssertFalse(permission.isSupported)
        XCTAssertEqual(permission.status, .denied)
        var granted: Bool?
        permission.requestPermission { granted = $0 }
        XCTAssertEqual(granted, false)
      }
    #endif

    private func waitForLive(_ runtime: PracticeMirrorRuntime, owner: PracticeMirrorOwner) async {
      let deadline = ContinuousClock.now.advanced(by: .seconds(5))
      while runtime.state != .live(owner), ContinuousClock.now < deadline {
        await Task.yield()
      }
      XCTAssertEqual(runtime.state, .live(owner))
    }

    private final class Driver: PracticeMirrorDriver {
      func configure() throws {}
      func start() throws {}
      var previewSource: PracticeMirrorPreviewSource? { .sample }
      func stopAndReleasePreviewResources() throws {}
    }
  }
#endif
