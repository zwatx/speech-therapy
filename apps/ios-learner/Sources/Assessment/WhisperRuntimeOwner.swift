import Dispatch
import Foundation

/// One model pair per provider, never a process-wide cache. The generic parameter
/// permits controlled model-lifetime tests; production uses only the Whisper pair.
/// Unchecked Sendable covers queue confinement, not thread safety of the pair.
final class WhisperRuntimeOwner<Pair: AnyObject>: @unchecked Sendable {
    final class Slot: @unchecked Sendable {
        private let queue: DispatchQueue
        private var pair: Pair?
        private var identity: String?
        private var closed = false

        fileprivate init(queue: DispatchQueue) { self.queue = queue }

        /// Call only after full admission of this request's complete resource set.
        /// A changed identity refuses this request, rather than silently substituting
        /// another model. A later explicit request may construct the admitted pair.
        func admittedPair(identity requested: String, load: () throws -> Pair) throws -> Pair {
            try validateIdentity(requested)
            if let pair { return pair }
            let loaded = try load() // Partial construction never reaches the slot.
            pair = loaded
            identity = requested
            return loaded
        }

        func validateIdentity(_ requested: String) throws {
            dispatchPrecondition(condition: .onQueue(queue))
            guard !closed else { throw WhisperProviderError.unavailable }
            if let identity, identity != requested {
                evict()
                throw WhisperProviderError.unavailable
            }
        }

        func evict() {
            dispatchPrecondition(condition: .onQueue(queue))
            pair = nil
            identity = nil
        }

        fileprivate func close() {
            dispatchPrecondition(condition: .onQueue(queue))
            closed = true
            evict()
        }
    }

    private let queue: DispatchQueue
    private let slot: Slot
    private let pressure: DispatchSourceMemoryPressure

    init() {
        let queue = DispatchQueue(label: "com.cadence.whisper.runtime", qos: .userInitiated)
        self.queue = queue
        let slot = Slot(queue: queue)
        self.slot = slot
        let pressure = DispatchSource.makeMemoryPressureSource(eventMask: [.warning, .critical], queue: queue)
        self.pressure = pressure
        // Delivery queues behind any synchronous prediction: never unload in use.
        pressure.setEventHandler { autoreleasepool { slot.evict() } }
        pressure.resume()
    }

    /// Called by the provider's detached worker. Nothing request-scoped is stored.
    func perform(_ body: @Sendable (Slot) -> WhisperWorkerCompletion) -> WhisperWorkerCompletion {
        dispatchPrecondition(condition: .notOnQueue(queue))
        return queue.sync { autoreleasepool { body(slot) } }
    }

    /// Queued disposal, joined by its caller. It cannot bypass active work; Core ML
    /// supplies no hard bound on prediction or model destruction.
    func close() async {
        await withCheckedContinuation { continuation in
            queue.async { [slot] in
                autoreleasepool { slot.close() }
                continuation.resume()
            }
        }
    }

    /// Internal deterministic memory-pressure seam; uses the same serial disposal.
    func evictIdle() async {
        await withCheckedContinuation { continuation in
            queue.async { [slot] in
                autoreleasepool { slot.evict() }
                continuation.resume()
            }
        }
    }

    deinit {
        pressure.cancel()
        // Even abandonment never releases the last pair reference on MainActor.
        // Explicit Close remains the acknowledged/joined product path.
        let slot = slot
        queue.async { autoreleasepool { slot.close() } }
    }
}
