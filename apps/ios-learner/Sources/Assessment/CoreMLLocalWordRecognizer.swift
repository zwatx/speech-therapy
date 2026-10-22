import Foundation

/// Thread-safe cooperative control only. A stop request never acknowledges cleanup.
final class WhisperOperationStop: @unchecked Sendable {
    enum Reason: Sendable { case cancellation, deadline }
    private let lock = NSLock()
    private var reason: Reason?

    func request(_ value: Reason) {
        lock.lock(); defer { lock.unlock() }
        // Explicit/parent cancellation has priority over a coincident deadline.
        if reason == nil || value == .cancellation { reason = value }
    }
    var current: Reason? {
        lock.lock(); defer { lock.unlock() }
        return reason
    }
    var isStopped: Bool { current != nil }
    func check() throws { if isStopped { throw CancellationError() } }
    var interruptedStatus: LocalWordRecognitionStatus? {
        switch current {
        case .cancellation: .cancelled
        case .deadline: .timedOut
        case nil: nil
        }
    }
}

/// A failed handle close transfers the inert strong reference to the occupied
/// provider. No caller may release its exact borrow or bypass that operation.
struct WhisperWorkerCompletion: @unchecked Sendable {
    let status: LocalWordRecognitionStatus
    let cleanupConfirmed: Bool
    let retainedHandle: FileHandle?
    let wordGuess: LocalWordGuess?

    init(status: LocalWordRecognitionStatus, cleanupConfirmed: Bool,
         retainedHandle: FileHandle?, wordGuess: LocalWordGuess? = nil) {
        self.status = status
        self.cleanupConfirmed = cleanupConfirmed
        self.retainedHandle = retainedHandle
        self.wordGuess = status == .notMatched && cleanupConfirmed && retainedHandle == nil
            ? wordGuess : nil
    }

    /// Final filtering after the real worker and timer have both returned.
    func receipt(request: LocalWordRecognitionRequest,
                 interruptedStatus: LocalWordRecognitionStatus?) -> LocalWordRecognitionReceipt {
        .init(request: request, status: interruptedStatus ?? status,
              cleanupConfirmed: cleanupConfirmed && retainedHandle == nil, wordGuess: wordGuess)
    }
}

@MainActor
final class CoreMLLocalWordRecognizer: LocalWordRecognizing, LocalWordRuntimeReleasing {
    private final class Operation {
        let request: LocalWordRecognitionRequest
        let stop = WhisperOperationStop()
        var retainedHandle: FileHandle?
        init(_ request: LocalWordRecognitionRequest) { self.request = request }
    }
    typealias Worker = @Sendable (LocalWordRecognitionRequest, WhisperOperationStop) -> WhisperWorkerCompletion
    private let ownership: ProcessAudioFileOwnership
    private let worker: Worker
    private let deadlineNanoseconds: UInt64
    private var operation: Operation?
    private let runtime: WhisperCoreMLWorker.ReusingWorker?
    private var runtimeRelease: Task<Void, Never>?
    private var runtimeUseGeneration = UUID()

    /// Inert by construction. Missing/unadmitted resources are unavailable; this
    /// provider never invokes Speech, downloads a model or chooses another backend.
    init(resources: WhisperBundledResources? = nil,
         ownership: ProcessAudioFileOwnership = .shared) {
        self.ownership = ownership
        deadlineNanoseconds = 15_000_000_000
        let runtime = WhisperCoreMLWorker.ReusingWorker()
        self.runtime = runtime
        worker = { request, stop in runtime.run(request: request, resources: resources, stop: stop) }
    }

    /// Internal copied-fixture seam; not a product backend selection/fallback API.
    init(ownership: ProcessAudioFileOwnership, deadlineNanoseconds: UInt64,
         fixtureWorker: @escaping Worker) {
        self.ownership = ownership
        self.deadlineNanoseconds = deadlineNanoseconds
        worker = fixtureWorker
        runtime = nil
    }

    func releaseWordRuntime() async -> Bool {
        // The caller first joins the check/receipt, which also joins its timer.
        // An occupied or sticky-failed operation cannot be bypassed by Close.
        guard operation == nil else { return false }
        let generation = runtimeUseGeneration
        if let runtimeRelease {
            await runtimeRelease.value
            // A newer accepted check may have run before this duplicate waiter resumes.
            return operation == nil && runtimeUseGeneration == generation
        }
        let runtime = runtime
        let release = Task<Void, Never> { if let runtime { await runtime.close() } }
        runtimeRelease = release // Refuse reentrant work while disposal completes.
        await release.value
        runtimeRelease = nil
        return true
    }

    func cancel(operationID: UUID) {
        guard let operation, operation.request.operationID == operationID else { return }
        operation.stop.request(.cancellation)
    }

    func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
        guard runtimeRelease == nil else {
            return .init(request: request, status: .unavailable, cleanupConfirmed: true)
        }
        guard operation == nil else {
            return .init(request: request, status: .unavailable, cleanupConfirmed: false)
        }
        guard !Task.isCancelled else {
            return .init(request: request, status: .cancelled, cleanupConfirmed: true)
        }
        guard request.fileURL.isFileURL, LocalWordComparison.singleWord(request.expectedWord) != nil else {
            return .init(request: request, status: .unavailable, cleanupConfirmed: true)
        }
        guard ownership.borrow(request.fileURL, operation: request.operationID) else {
            return .init(request: request, status: .unavailable, cleanupConfirmed: true)
        }
        let current = Operation(request)
        runtimeUseGeneration = UUID()
        operation = current // Occupied before any queued file/model work.
        let stop = current.stop
        let work = worker
        let deadline = Task {
            do {
                try await Task.sleep(nanoseconds: deadlineNanoseconds)
                if !Task.isCancelled { stop.request(.deadline) }
            } catch { /* Cancelled timer finishes; it never releases the borrow. */ }
        }
        let actualWorker = Task.detached(priority: .userInitiated) { work(request, stop) }
        let completion = await withTaskCancellationHandler {
            await actualWorker.value // A signal/deadline cannot bypass this actual return.
        } onCancel: {
            stop.request(.cancellation)
        }
        deadline.cancel()
        await deadline.value
        if Task.isCancelled { stop.request(.cancellation) }
        let interruptedStatus = stop.interruptedStatus
        let cleanup = completion.cleanupConfirmed && completion.retainedHandle == nil
        if cleanup {
            ownership.finishBorrowing(operation: request.operationID)
            operation = nil
        } else {
            current.retainedHandle = completion.retainedHandle
            // No automatic close retry, ownership release or replacement operation.
        }
        return completion.receipt(request: request, interruptedStatus: interruptedStatus)
    }
}
