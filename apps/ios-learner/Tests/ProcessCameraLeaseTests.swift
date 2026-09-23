import Foundation
import XCTest

@testable import CadenceLearner

/// Exercises the real mirror runtime with inert drivers; never constructs camera hardware.
@MainActor
final class ProcessCameraLeaseTests: XCTestCase {
  func testExternalOwnerBlocksMirrorWithoutConstructingDriver() async {
    let lease = ProcessCameraLease()
    let external = UUID()
    let owner = PracticeMirrorOwner(id: UUID())
    let driver = LeaseTestDriver()
    let recovery = ProcessPracticeMirrorRecovery(cameraLease: lease)
    let runtime = makeRuntime(recovery: recovery, driver: driver)

    XCTAssertTrue(lease.acquire(external))
    XCTAssertFalse(runtime.start(owner: owner))
    XCTAssertEqual(runtime.state, .idle)
    XCTAssertNil(recovery.owner)
    XCTAssertNil(recovery.runtime)
    XCTAssertEqual(driver.factoryCalls, 0)
    XCTAssertEqual(lease.owner, external)

    XCTAssertTrue(lease.release(external))
    // A denied reservation must not consume the mirror's owner identity.
    XCTAssertTrue(runtime.start(owner: owner))
    await waitUntil { runtime.state == .live(owner) }
    XCTAssertEqual(driver.factoryCalls, 1)
    _ = runtime.requestStop(owner: owner)
    await waitUntil { runtime.releasedReceipt(owner: owner) != nil }
    XCTAssertNil(lease.owner)
  }

  func testMirrorRetainsLeaseThroughLiveStoppingAndFailedCleanupUntilRetry() async throws {
    let lease = ProcessCameraLease()
    let external = UUID()
    let owner = PracticeMirrorOwner(id: UUID())
    let driver = LeaseTestDriver(cleanupFailures: 1)
    let recovery = ProcessPracticeMirrorRecovery(cameraLease: lease)
    let runtime = makeRuntime(recovery: recovery, driver: driver)

    XCTAssertTrue(runtime.start(owner: owner))
    XCTAssertEqual(lease.owner, owner.id)
    XCTAssertFalse(lease.acquire(external))
    await waitUntil { runtime.state == .live(owner) }
    XCTAssertFalse(lease.acquire(external))

    let original = try XCTUnwrap(runtime.requestStop(owner: owner))
    XCTAssertEqual(runtime.state, .stopping(owner))
    XCTAssertFalse(lease.acquire(external))
    await waitUntil { runtime.state == .stopFailed(owner) }
    XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
    XCTAssertEqual(lease.owner, owner.id)
    XCTAssertEqual(recovery.owner, owner)
    XCTAssertTrue(recovery.runtime === runtime)
    XCTAssertFalse(lease.acquire(external))

    let retry = try XCTUnwrap(recovery.retryStop())
    XCTAssertFalse(lease.acquire(external))
    await waitUntil { retry.receipt != nil }
    XCTAssertEqual(retry.receipt?.result, .released)
    XCTAssertEqual(original.receipt?.result, .cleanupUnconfirmed)
    XCTAssertEqual(driver.factoryCalls, 1, "Recovery must retain the original driver")
    XCTAssertEqual(driver.stopCalls, 2)
    XCTAssertNil(recovery.owner)
    XCTAssertNil(recovery.runtime)
    XCTAssertNil(lease.owner)
    XCTAssertTrue(lease.acquire(external))
    XCTAssertTrue(lease.release(external))
  }

  func testWrongOrStaleReleaseCannotFreeSuccessor() {
    let lease = ProcessCameraLease()
    let first = UUID()
    let successor = UUID()
    XCTAssertTrue(lease.acquire(first))
    XCTAssertFalse(lease.acquire(first), "Acquisition is not reentrant")
    XCTAssertFalse(lease.release(successor))
    XCTAssertEqual(lease.owner, first)
    XCTAssertTrue(lease.release(first))
    XCTAssertTrue(lease.acquire(successor))
    XCTAssertFalse(lease.release(first))
    XCTAssertEqual(lease.owner, successor)
    XCTAssertFalse(lease.acquire(UUID()))
    XCTAssertTrue(lease.release(successor))
    XCTAssertNil(lease.owner)
  }

  func testDefaultTestRecoveriesHaveIndependentCameraLeases() async {
    let firstRecovery = ProcessPracticeMirrorRecovery()
    let secondRecovery = ProcessPracticeMirrorRecovery()
    let firstOwner = PracticeMirrorOwner(id: UUID())
    let secondOwner = PracticeMirrorOwner(id: UUID())
    let first = makeRuntime(recovery: firstRecovery, driver: LeaseTestDriver())
    let second = makeRuntime(recovery: secondRecovery, driver: LeaseTestDriver())

    XCTAssertTrue(first.start(owner: firstOwner))
    XCTAssertTrue(second.start(owner: secondOwner))
    await waitUntil { first.state == .live(firstOwner) && second.state == .live(secondOwner) }
    _ = first.requestStop(owner: firstOwner)
    await waitUntil { first.releasedReceipt(owner: firstOwner) != nil }
    XCTAssertEqual(second.state, .live(secondOwner))
    XCTAssertEqual(secondRecovery.owner, secondOwner)
    _ = second.requestStop(owner: secondOwner)
    await waitUntil { second.releasedReceipt(owner: secondOwner) != nil }
  }

  private func makeRuntime(
    recovery: ProcessPracticeMirrorRecovery, driver: LeaseTestDriver
  ) -> PracticeMirrorRuntime {
    PracticeMirrorRuntime(recovery: recovery) { _ in
      driver.didConstruct()
      return driver
    }
  }

  private func waitUntil(_ predicate: @MainActor () -> Bool) async {
    let deadline = ContinuousClock.now + .seconds(2)
    while !predicate() && ContinuousClock.now < deadline { await Task.yield() }
    XCTAssertTrue(predicate())
  }
}

/// The runtime's worker and main-actor assertions share only lock-protected counters.
private final class LeaseTestDriver: PracticeMirrorDriver, @unchecked Sendable {
  private enum Failure: Error { case cleanup }
  private let lock = NSLock()
  private var constructions = 0
  private var stops = 0
  private var failuresRemaining: Int

  init(cleanupFailures: Int = 0) { failuresRemaining = cleanupFailures }

  var factoryCalls: Int { lock.withLock { constructions } }
  var stopCalls: Int { lock.withLock { stops } }
  func didConstruct() { lock.withLock { constructions += 1 } }
  func configure() {}
  func start() {}
  func stopAndReleasePreviewResources() throws {
    try lock.withLock {
      stops += 1
      if failuresRemaining > 0 {
        failuresRemaining -= 1
        throw Failure.cleanup
      }
    }
  }
}
