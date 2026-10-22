import Darwin
import Foundation

struct NativeHiddenRequest: Equatable, Sendable {
  let operationID: UUID
  let takeID: UUID
  /// The exact stopped take already retained by the capture owner.
  let recording: CapturedRecording
}

enum NativeHiddenStatus: Equatable, Sendable {
  case completed, unavailable, rejectedInput, failed, cancelled, deadlineExceeded
}

/// A synchronous worker return acknowledges model scope return, not just a stop request.
struct NativeHiddenWorkerCompletion: @unchecked Sendable {
  let request: NativeHiddenRequest
  let status: NativeHiddenStatus
  let features: NativeHiddenFeatures?
  let cleanupConfirmed: Bool
  let retainedHandle: FileHandle?
}

struct NativeHiddenReceipt: Equatable, Sendable {
  let request: NativeHiddenRequest
  let status: NativeHiddenStatus
  let features: NativeHiddenFeatures?
  let cleanupConfirmed: Bool
}

/// Internal hidden-only operation. No product recognizer, history or feedback API is changed.
@MainActor
final class NativeHiddenOperation {
  typealias Worker =
    @Sendable (NativeHiddenRequest, WhisperOperationStop) -> NativeHiddenWorkerCompletion
  typealias Timer = @Sendable (WhisperOperationStop) async -> Void

  private final class Active {
    let request: NativeHiddenRequest
    let stop = WhisperOperationStop()
    var retainedHandle: FileHandle?
    init(_ request: NativeHiddenRequest) { self.request = request }
  }

  private let ownership: ProcessAudioFileOwnership
  private let worker: Worker
  private let timer: Timer
  private var active: Active?

  init(
    resources: NativeHiddenResources? = .bundled(), ownership: ProcessAudioFileOwnership = .shared,
    deadlineNanoseconds: UInt64 = 60_000_000_000
  ) {
    self.ownership = ownership
    worker = { request, stop in
      NativeHiddenCoreMLWorker.run(request: request, resources: resources, stop: stop)
    }
    timer = Self.deadlineTimer(deadlineNanoseconds)
  }

  /// Controllable worker/timer fixtures only; no runtime backend selection or fallback.
  init(
    ownership: ProcessAudioFileOwnership, fixtureWorker: @escaping Worker,
    fixtureTimer: @escaping Timer = NativeHiddenOperation.deadlineTimer(60_000_000_000)
  ) {
    self.ownership = ownership
    worker = fixtureWorker
    timer = fixtureTimer
  }

  private nonisolated static func deadlineTimer(_ nanoseconds: UInt64) -> Timer {
    { stop in
      do {
        try await Task.sleep(nanoseconds: nanoseconds)
        if !Task.isCancelled { stop.request(.deadline) }
      } catch {
        // The cancelled timer returns; only the operation settles its borrow.
      }
    }
  }

  func cancel(operationID: UUID) {
    guard let active, active.request.operationID == operationID else { return }
    active.stop.request(.cancellation)
  }

  func process(_ request: NativeHiddenRequest) async -> NativeHiddenReceipt {
    func receipt(_ status: NativeHiddenStatus, cleanup: Bool, features: NativeHiddenFeatures? = nil)
      -> NativeHiddenReceipt
    {
      .init(request: request, status: status, features: features, cleanupConfirmed: cleanup)
    }
    guard active == nil else { return receipt(.unavailable, cleanup: false) }
    guard !Task.isCancelled else { return receipt(.cancelled, cleanup: true) }
    let url = request.recording.url
    guard url.isFileURL, url == url.standardizedFileURL,
      request.recording.summary.duration.isFinite,
      (0.1...4).contains(request.recording.summary.duration),
      request.recording.summary.averagePower.isFinite,
      let owner = request.recording.cleanupOwnerID, ownership.canRemove(url, owner: owner),
      ownership.borrow(url, operation: request.operationID)
    else { return receipt(.unavailable, cleanup: true) }
    let current = Active(request)
    active = current  // Both ownership reservation and occupied slot precede detached work.
    let stop = current.stop
    let work = worker
    let wait = timer
    let deadline = Task { await wait(stop) }
    let actualWorker = Task.detached(priority: .userInitiated) { work(request, stop) }
    let completion = await withTaskCancellationHandler {
      await actualWorker.value
    } onCancel: {
      stop.request(.cancellation)
    }
    deadline.cancel()
    await deadline.value  // A held/cancelled timer is joined too.
    if Task.isCancelled { stop.request(.cancellation) }
    guard active === current, completion.request == request else {
      current.retainedHandle = completion.retainedHandle
      return receipt(.failed, cleanup: false)
    }
    let featuresMatch: Bool
    if let features = completion.features {
      let identity = features.identity
      featuresMatch =
        completion.status == .completed && identity.request == request
        && (1600...64000).contains(identity.sampleCount)
        && identity.validFrames == NativeHiddenCoreMLWorker.frames(identity.sampleCount)
        && request.recording.summary.duration == Double(identity.sampleCount) / 16000
        && identity.file.inode > 0 && identity.file.uid == getuid() && identity.file.links == 1
        && identity.file.mode & UInt32(S_IFMT) == UInt32(S_IFREG)
        && identity.file.size >= 44 && identity.file.size <= LocalWordWAVGate.maximumFileBytes
        && features.hidden.count == 199 * 1024 * 4
        && NativeHiddenFiles.validSHA(identity.wavSHA256)
        && NativeHiddenFiles.validSHA(identity.decodedSamplesSHA256)
        && NativeHiddenFiles.validSHA(identity.normalizedSamplesSHA256)
    } else {
      featuresMatch = completion.status != .completed
    }
    guard featuresMatch else {
      current.retainedHandle = completion.retainedHandle
      return receipt(.failed, cleanup: false)
    }
    let status: NativeHiddenStatus
    switch stop.current {
    case .cancellation: status = .cancelled
    case .deadline: status = .deadlineExceeded
    case nil: status = completion.status
    }
    let cleanup = completion.cleanupConfirmed && completion.retainedHandle == nil
    if cleanup {
      ownership.finishBorrowing(operation: current.request.operationID)
      active = nil
    } else {
      current.retainedHandle = completion.retainedHandle
      // Retain this exact handle and borrow. No automatic retry or next owner.
    }
    return receipt(
      status, cleanup: cleanup,
      features: cleanup && status == .completed ? completion.features : nil)
  }
}
