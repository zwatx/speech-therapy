import Foundation
import XCTest

@testable import CadenceLearner

private final class RuntimeTrace: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String] = []
    func add(_ value: String) {
        lock.lock(); defer { lock.unlock() }
        values.append((Thread.isMainThread ? "main:" : "worker:") + value)
    }
    var events: [String] {
        lock.lock(); defer { lock.unlock() }
        return values
    }
}

/// Model stand-in; only the owner may construct/use/destroy it. No input retained.
private final class RuntimePairFixture {
    private let trace: RuntimeTrace
    init(_ trace: RuntimeTrace) { self.trace = trace; trace.add("load") }
    func use(_ request: String) { trace.add(request) }
    deinit { trace.add("dispose") }
}

private final class RuntimeHold: @unchecked Sendable {
    private let condition = NSCondition()
    private var released = false
    let entered = XCTestExpectation(description: "serial runtime entered")
    func wait() -> Bool {
        condition.lock(); defer { condition.unlock() }
        entered.fulfill()
        let end = Date(timeIntervalSinceNow: 5)
        while !released {
            if !condition.wait(until: end) { return false }
        }
        return true
    }
    func release() {
        condition.lock(); released = true; condition.broadcast(); condition.unlock()
    }
}

final class WhisperRuntimeOwnerTests: XCTestCase {
    private static func completion(_ success: Bool) -> WhisperWorkerCompletion {
        .init(status: success ? .matched : .unavailable, cleanupConfirmed: true, retainedHandle: nil)
    }

    func testSequentialRequestsReuseOnePairAndIdleEvictionForcesFreshLoad() async {
        let trace = RuntimeTrace(), owner = WhisperRuntimeOwner<RuntimePairFixture>()
        XCTAssertTrue(trace.events.isEmpty, "Creating a provider must remain lazy")
        for request in ["first", "second"] {
            let result = await Task.detached {
                owner.perform { slot in
                    do {
                        let pair = try slot.admittedPair(identity: "admitted-A") { RuntimePairFixture(trace) }
                        pair.use(request)
                        return Self.completion(true)
                    } catch { return Self.completion(false) }
                }
            }.value
            XCTAssertEqual(result.status, .matched)
        }
        XCTAssertEqual(trace.events, ["worker:load", "worker:first", "worker:second"])
        await owner.evictIdle()
        XCTAssertEqual(trace.events.last, "worker:dispose")
        let result = await Task.detached {
            owner.perform { slot in
                do {
                    let pair = try slot.admittedPair(identity: "admitted-A") { RuntimePairFixture(trace) }
                    pair.use("third")
                    return Self.completion(true)
                } catch { return Self.completion(false) }
            }
        }.value
        XCTAssertEqual(result.status, .matched)
        await owner.close()
        XCTAssertEqual(trace.events, ["worker:load", "worker:first", "worker:second",
            "worker:dispose", "worker:load", "worker:third", "worker:dispose"])
    }

    func testChangedIdentityRefusesRequestAndEvictsBeforeLaterExplicitLoad() async {
        let trace = RuntimeTrace(), owner = WhisperRuntimeOwner<RuntimePairFixture>()
        for (identity, expected) in [("A", true), ("B", false), ("B", true)] {
            let result = await Task.detached {
                owner.perform { slot in
                    do {
                        let pair = try slot.admittedPair(identity: identity) { RuntimePairFixture(trace) }
                        pair.use(identity)
                        return Self.completion(true)
                    } catch { return Self.completion(false) }
                }
            }.value
            XCTAssertEqual(result.status, expected ? .matched : .unavailable)
        }
        await owner.close()
        XCTAssertEqual(trace.events, ["worker:load", "worker:A", "worker:dispose",
            "worker:load", "worker:B", "worker:dispose"])
    }

    func testPartialLoadNeverPublishesAndClosedOwnerNeverReloads() async {
        let trace = RuntimeTrace(), owner = WhisperRuntimeOwner<RuntimePairFixture>()
        let failed = await Task.detached {
            owner.perform { slot in
                do {
                    _ = try slot.admittedPair(identity: "A") {
                        let partial = RuntimePairFixture(trace)
                        partial.use("partial")
                        throw WhisperProviderError.unavailable
                    }
                    return Self.completion(true)
                } catch { return Self.completion(false) }
            }
        }.value
        XCTAssertEqual(failed.status, .unavailable)
        XCTAssertEqual(trace.events, ["worker:load", "worker:partial", "worker:dispose"])
        await owner.close()
        let closed = await Task.detached {
            owner.perform { slot in
                do {
                    _ = try slot.admittedPair(identity: "A") { RuntimePairFixture(trace) }
                    return Self.completion(true)
                } catch { return Self.completion(false) }
            }
        }.value
        XCTAssertEqual(closed.status, .unavailable)
        XCTAssertEqual(trace.events.count, 3)
    }

    func testQueuedDisposalCannotUnloadHeldUse() async {
        let trace = RuntimeTrace(), owner = WhisperRuntimeOwner<RuntimePairFixture>()
        let hold = RuntimeHold(); defer { hold.release() }
        let work = Task.detached {
            owner.perform { slot in
                do {
                    let pair = try slot.admittedPair(identity: "A") { RuntimePairFixture(trace) }
                    pair.use("entered")
                    let released = hold.wait()
                    pair.use("returned")
                    return Self.completion(released)
                } catch { return Self.completion(false) }
            }
        }
        await fulfillment(of: [hold.entered], timeout: 2)
        let disposal = Task { await owner.close() }
        XCTAssertEqual(trace.events, ["worker:load", "worker:entered"])
        hold.release()
        let result = await work.value
        await disposal.value
        XCTAssertEqual(result.status, .matched)
        XCTAssertEqual(trace.events, ["worker:load", "worker:entered", "worker:returned", "worker:dispose"])
    }
}
