import CryptoKit
import Darwin
import Foundation
import XCTest

@testable import CadenceLearner

private final class HeldHiddenWorker: @unchecked Sendable {
  private let condition = NSCondition()
  private var released = false
  private let entered = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
  private let returned = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
  var wrongRequest = false
  var missingFeatures = false
  var completedFeatures = false
  var cleanupConfirmed = true
  var retainedHandle: FileHandle?

  func run(_ request: NativeHiddenRequest, _ stop: WhisperOperationStop)
    -> NativeHiddenWorkerCompletion
  {
    condition.lock()
    entered.continuation.yield(())
    while !released { condition.wait() }
    let handle = retainedHandle
    retainedHandle = nil
    condition.unlock()
    let returnedRequest =
      wrongRequest
      ? NativeHiddenRequest(
        operationID: UUID(), takeID: request.takeID, recording: request.recording) : request
    returned.continuation.yield(())
    var features: NativeHiddenFeatures?
    if completedFeatures {
      var file = stat()
      file.st_ino = 1
      file.st_mode = S_IFREG | 0o600
      file.st_uid = getuid()
      file.st_nlink = 1
      file.st_size = 3244
      features = NativeHiddenFeatures(
        identity: .init(
          request: returnedRequest, file: .init(file),
          wavSHA256: String(repeating: "a", count: 64),
          decodedSamplesSHA256: String(repeating: "b", count: 64),
          normalizedSamplesSHA256: String(repeating: "c", count: 64), sampleCount: 1600,
          validFrames: 4),
        hidden: Data(repeating: 0, count: 815104))
    }
    return .init(
      request: returnedRequest,
      status: missingFeatures || completedFeatures ? .completed : .unavailable,
      features: features, cleanupConfirmed: cleanupConfirmed, retainedHandle: handle)
  }
  func waitForEntry() async {
    var iterator = entered.stream.makeAsyncIterator()
    _ = await iterator.next()
  }
  func waitForReturn() async {
    var iterator = returned.stream.makeAsyncIterator()
    _ = await iterator.next()
  }
  func release() {
    condition.lock()
    released = true
    condition.broadcast()
    condition.unlock()
  }
}

private final class HeldHiddenTimer: @unchecked Sendable {
  private let lock = NSLock()
  private var continuation: CheckedContinuation<Void, Never>?
  private var released = false
  private var stop: WhisperOperationStop?
  private let entered = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))

  func run(_ control: WhisperOperationStop) async {
    await withCheckedContinuation { continuation in
      lock.lock()
      stop = control
      if released {
        lock.unlock()
        continuation.resume()
      } else {
        self.continuation = continuation
        lock.unlock()
      }
      entered.continuation.yield(())
    }
  }
  func waitForEntry() async {
    var iterator = entered.stream.makeAsyncIterator()
    _ = await iterator.next()
  }
  func release(deadline: Bool = false) {
    lock.lock()
    released = true
    let pending = continuation
    continuation = nil
    let control = stop
    lock.unlock()
    if deadline { control?.request(.deadline) }
    pending?.resume()
  }
}

final class NativeHiddenOperationTests: XCTestCase {
  @MainActor
  private func owned(_ ownership: ProcessAudioFileOwnership, operationID: UUID = UUID()) -> (
    UUID, NativeHiddenRequest
  ) {
    let owner = UUID()
    let recording = CapturedRecording(
      url: URL(fileURLWithPath: "/generated-hidden-unit/\(UUID()).wav"),
      summary: .init(duration: 0.1, averagePower: -20), cleanupOwnerID: owner)
    ownership.retain(recording.url, owner: owner)
    return (owner, .init(operationID: operationID, takeID: UUID(), recording: recording))
  }

  @MainActor
  func testCancellationAndOverlapRetainExactBorrowUntilActualWorkerReturn() async {
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    let gate = HeldHiddenWorker()
    defer { gate.release() }
    let operation = NativeHiddenOperation(ownership: registry, fixtureWorker: { gate.run($0, $1) })
    let task = Task { await operation.process(request) }
    await gate.waitForEntry()
    operation.cancel(operationID: request.operationID)
    XCTAssertFalse(registry.canRemove(request.recording.url, owner: owner))
    let overlap = await operation.process(request)
    XCTAssertEqual(overlap.status, .unavailable)
    XCTAssertFalse(overlap.cleanupConfirmed)
    gate.release()
    let receipt = await task.value
    XCTAssertEqual(receipt.request, request)
    XCTAssertEqual(receipt.status, .cancelled)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertNil(receipt.features)
    XCTAssertTrue(registry.canRemove(request.recording.url, owner: owner))
  }

  @MainActor
  func testParentCancellationJoinsWorkerAndTimer() async {
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    let gate = HeldHiddenWorker()
    let timer = HeldHiddenTimer()
    gate.completedFeatures = true
    defer {
      gate.release()
      timer.release()
    }
    let operation = NativeHiddenOperation(
      ownership: registry, fixtureWorker: { gate.run($0, $1) },
      fixtureTimer: { await timer.run($0) })
    let task = Task { await operation.process(request) }
    await gate.waitForEntry()
    await timer.waitForEntry()
    task.cancel()
    gate.release()
    await gate.waitForReturn()
    XCTAssertFalse(registry.canRemove(request.recording.url, owner: owner))
    let occupied = await operation.process(request)
    XCTAssertFalse(occupied.cleanupConfirmed)
    timer.release()
    let receipt = await task.value
    XCTAssertEqual(receipt.status, .cancelled)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertTrue(registry.canRemove(request.recording.url, owner: owner))
  }

  @MainActor
  func testDeadlineRequestsStopButHeldPredictionMustReturn() async {
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    let gate = HeldHiddenWorker()
    let timer = HeldHiddenTimer()
    defer {
      gate.release()
      timer.release()
    }
    let operation = NativeHiddenOperation(
      ownership: registry, fixtureWorker: { gate.run($0, $1) },
      fixtureTimer: { await timer.run($0) })
    let task = Task { await operation.process(request) }
    await gate.waitForEntry()
    await timer.waitForEntry()
    timer.release(deadline: true)
    XCTAssertFalse(registry.canRemove(request.recording.url, owner: owner))
    gate.release()
    let receipt = await task.value
    XCTAssertEqual(receipt.status, .deadlineExceeded)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertTrue(registry.canRemove(request.recording.url, owner: owner))
  }

  @MainActor
  func testCancellationAfterWorkBeforePublicationStillDiscardsResult() async {
    let registry = ProcessAudioFileOwnership()
    let (_, request) = owned(registry)
    let gate = HeldHiddenWorker()
    let timer = HeldHiddenTimer()
    gate.completedFeatures = true
    defer {
      gate.release()
      timer.release()
    }
    let operation = NativeHiddenOperation(
      ownership: registry, fixtureWorker: { gate.run($0, $1) },
      fixtureTimer: { await timer.run($0) })
    let task = Task { await operation.process(request) }
    await gate.waitForEntry()
    await timer.waitForEntry()
    gate.release()
    await gate.waitForReturn()
    operation.cancel(operationID: request.operationID)
    timer.release()
    let receipt = await task.value
    XCTAssertEqual(receipt.status, .cancelled)
    XCTAssertNil(receipt.features)
    XCTAssertTrue(receipt.cleanupConfirmed)
  }

  @MainActor
  func testWrongReceiptAndUnconfirmedScopeCannotReleaseOrReplaceOwner() async {
    for failure in 0..<3 {
      let registry = ProcessAudioFileOwnership()
      let (owner, request) = owned(registry)
      let gate = HeldHiddenWorker()
      defer { gate.release() }
      gate.wrongRequest = failure == 0
      gate.missingFeatures = failure == 1
      gate.cleanupConfirmed = failure != 2
      let operation = NativeHiddenOperation(
        ownership: registry, fixtureWorker: { gate.run($0, $1) })
      let task = Task { await operation.process(request) }
      await gate.waitForEntry()
      gate.release()
      let receipt = await task.value
      XCTAssertFalse(receipt.cleanupConfirmed)
      XCTAssertNil(receipt.features)
      XCTAssertFalse(registry.canRemove(request.recording.url, owner: owner))
      let blocked = await operation.process(request)
      XCTAssertEqual(blocked.status, .unavailable)
      XCTAssertFalse(blocked.cleanupConfirmed)
    }
  }

  @MainActor
  func testFailedHandleCloseRetainsStrongHandleAndBorrow() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent("held.txt")
    try Data([1]).write(to: file)
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    let gate = HeldHiddenWorker()
    gate.cleanupConfirmed = false
    gate.retainedHandle = try FileHandle(forReadingFrom: file)
    weak var observedHandle = gate.retainedHandle
    defer {
      gate.release()
      try? observedHandle?.close()
    }
    let operation = NativeHiddenOperation(ownership: registry, fixtureWorker: { gate.run($0, $1) })
    let task = Task { await operation.process(request) }
    await gate.waitForEntry()
    gate.release()
    let receipt = await task.value
    XCTAssertFalse(receipt.cleanupConfirmed)
    XCTAssertNotNil(observedHandle)
    XCTAssertFalse(registry.canRemove(request.recording.url, owner: owner))
  }

  @MainActor
  func testUnretainedOrConflictingBorrowNeverDispatches() async {
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    XCTAssertTrue(
      registry.borrow(URL(fileURLWithPath: "/other-owned.wav"), operation: request.operationID))
    let operation = NativeHiddenOperation(
      ownership: registry,
      fixtureWorker: { request, _ in
        XCTFail("A refused borrow dispatched work")
        return .init(
          request: request, status: .failed, features: nil, cleanupConfirmed: true,
          retainedHandle: nil)
      })
    let refused = await operation.process(request)
    XCTAssertEqual(refused.status, .unavailable)
    XCTAssertTrue(refused.cleanupConfirmed)
    XCTAssertTrue(registry.canRemove(request.recording.url, owner: owner))
    XCTAssertTrue(registry.protectedURLs.contains(URL(fileURLWithPath: "/other-owned.wav")))
    registry.finishBorrowing(operation: request.operationID)
    let unowned = NativeHiddenRequest(
      operationID: UUID(), takeID: UUID(),
      recording:
        .init(
          url: request.recording.url, summary: request.recording.summary, cleanupOwnerID: UUID()))
    let unretained = await operation.process(unowned)
    XCTAssertEqual(unretained.status, .unavailable)
    XCTAssertTrue(unretained.cleanupConfirmed)
  }

  @MainActor
  func testCancelledBeforeStartAndMissingResourcesDoNotOpenInput() async {
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    let operation = NativeHiddenOperation(resources: nil, ownership: registry)
    let cancelled = Task { await operation.process(request) }
    cancelled.cancel()
    let first = await cancelled.value
    XCTAssertEqual(first.status, .cancelled)
    XCTAssertTrue(first.cleanupConfirmed)
    let unavailable = await operation.process(request)
    XCTAssertEqual(unavailable.status, .unavailable)
    XCTAssertTrue(unavailable.cleanupConfirmed)
    XCTAssertTrue(registry.canRemove(request.recording.url, owner: owner))
  }

  @MainActor
  func testOldCancellationCannotAffectNextOperation() async {
    let registry = ProcessAudioFileOwnership()
    let (_, first) = owned(registry)
    let (owner, second) = owned(registry)
    let a = HeldHiddenWorker()
    let b = HeldHiddenWorker()
    defer {
      a.release()
      b.release()
    }
    let operation = NativeHiddenOperation(
      ownership: registry,
      fixtureWorker: { request, stop in
        request.operationID == first.operationID ? a.run(request, stop) : b.run(request, stop)
      })
    let firstTask = Task { await operation.process(first) }
    await a.waitForEntry()
    a.release()
    _ = await firstTask.value
    let nextTask = Task { await operation.process(second) }
    await b.waitForEntry()
    operation.cancel(operationID: first.operationID)
    XCTAssertFalse(registry.canRemove(second.recording.url, owner: owner))
    b.release()
    let receipt = await nextTask.value
    XCTAssertEqual(receipt.request, second)
    XCTAssertEqual(receipt.status, .unavailable)
    XCTAssertTrue(receipt.cleanupConfirmed)
  }

  @MainActor
  func testOwnedHiddenReceiptKeepsExactTakeAndFrameIdentity() async {
    let registry = ProcessAudioFileOwnership()
    let (owner, request) = owned(registry)
    let gate = HeldHiddenWorker()
    gate.completedFeatures = true
    defer { gate.release() }
    let operation = NativeHiddenOperation(ownership: registry, fixtureWorker: { gate.run($0, $1) })
    let task = Task { await operation.process(request) }
    await gate.waitForEntry()
    gate.release()
    let receipt = await task.value
    XCTAssertEqual(receipt.status, .completed)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertEqual(receipt.features?.identity.request, request)
    XCTAssertEqual(receipt.features?.identity.sampleCount, 1600)
    XCTAssertEqual(receipt.features?.identity.validFrames, 4)
    XCTAssertEqual(receipt.features?.hidden.count, 815104)
    XCTAssertTrue(registry.canRemove(request.recording.url, owner: owner))
  }

  #if DEBUG
    private func resourceFixture(_ root: URL) throws -> NativeHiddenResources {
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
      var models = [[String: Any]]()
      for (index, name) in NativeHiddenResourceAdmission.modelNames.enumerated() {
        let model = root.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: model, withIntermediateDirectories: false)
        let bytes = Data([UInt8(index + 1)])
        try bytes.write(to: model.appendingPathComponent("fixture.bin"))
        models.append([
          "piece": NativeHiddenResourceAdmission.pieces[index], "path": name,
          "files": [["path": name + "/fixture.bin", "bytes": 1, "sha256": hash(bytes)]],
        ])
      }
      let manifest = try JSONSerialization.data(
        withJSONObject: [
          "schema": "NativeHiddenBundledResourcesV1", "admitted": true,
          "finalAuditSHA256": NativeHiddenResourceAdmission.finalAuditSHA256, "models": models,
        ], options: [.sortedKeys])
      try manifest.write(to: root.appendingPathComponent("RESOURCE-MANIFEST-v1.json"))
      return .fixture(rootURL: root, manifestSHA256: hash(manifest))
    }

    private func hash(_ data: Data) -> String {
      SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    func testResourceAdmissionIsInertAndRejectsMissingExtraOrChangedFiles() throws {
      let base = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: base, withIntermediateDirectories: false)
      defer { try? FileManager.default.removeItem(at: base) }
      let missing = NativeHiddenResources.fixture(
        rootURL: base.appendingPathComponent("missing"),
        manifestSHA256: String(repeating: "a", count: 64))
      XCTAssertThrowsError(
        try NativeHiddenResourceAdmission.load(missing, stop: WhisperOperationStop()))
      for mutation in ["valid", "extra", "changed", "missing"] {
        let root = base.appendingPathComponent(mutation, isDirectory: true)
        let resources = try resourceFixture(root)
        if mutation == "extra" { try Data([9]).write(to: root.appendingPathComponent("extra.bin")) }
        let input = root.appendingPathComponent(
          NativeHiddenResourceAdmission.modelNames[0] + "/fixture.bin")
        if mutation == "changed" { try Data([7]).write(to: input) }
        if mutation == "missing" { try FileManager.default.removeItem(at: input) }
        if mutation == "valid" {
          _ = try NativeHiddenResourceAdmission.load(resources, stop: WhisperOperationStop())
        } else {
          XCTAssertThrowsError(
            try NativeHiddenResourceAdmission.load(resources, stop: WhisperOperationStop()))
        }
      }
    }

    func testMalformedOversizedAndWrongRateWAVFailBeforeModelLoading() throws {
      let base = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
      try FileManager.default.createDirectory(at: base, withIntermediateDirectories: false)
      defer { try? FileManager.default.removeItem(at: base) }
      let resources = try resourceFixture(
        base.appendingPathComponent("resources", isDirectory: true))
      func little(_ value: Int, _ count: Int) -> [UInt8] {
        (0..<count).map { UInt8(truncatingIfNeeded: value >> ($0 * 8)) }
      }
      var body = Array("WAVEfmt ".utf8) + little(16, 4) + little(1, 2) + little(1, 2)
      body += little(8000, 4) + little(16000, 4) + little(2, 2) + little(16, 2)
      body += Array("data".utf8) + little(3200, 4) + [UInt8](repeating: 0, count: 3200)
      let wrongRate = Data(Array("RIFF".utf8) + little(body.count, 4) + body)
      for (index, bytes) in [Data([0]), Data(repeating: 0, count: 132097), wrongRate].enumerated() {
        let file = base.appendingPathComponent("invalid-\(index).wav")
        try bytes.write(to: file)
        let request = NativeHiddenRequest(
          operationID: UUID(), takeID: UUID(),
          recording:
            .init(
              url: file, summary: .init(duration: 0.1, averagePower: -20), cleanupOwnerID: UUID()))
        let completion = NativeHiddenCoreMLWorker.run(
          request: request, resources: resources, stop: WhisperOperationStop())
        XCTAssertEqual(completion.status, .rejectedInput)
        XCTAssertTrue(completion.cleanupConfirmed)
        XCTAssertNil(completion.features)
      }
    }
  #endif

  func testMaskingAndPhysicalBordersPreserveValidSignedZeroBits() throws {
    var projected = Data(repeating: 0, count: 815104)
    projected[3] = 0x80  // Float32 negative zero at first valid coordinate.
    projected[4 * 1024] = 0xff  // Invalid frame is overwritten as positive zero bytes.
    let masked = try NativeHiddenCoreMLWorker.maskedProjection(projected, validFrames: 1)
    XCTAssertEqual(masked.prefix(4096), projected.prefix(4096))
    XCTAssertTrue(masked.dropFirst(4096).allSatisfy { $0 == 0 })
    let padded = try NativeHiddenCoreMLWorker.paddedChannels(masked, stop: WhisperOperationStop())
    XCTAssertEqual(padded[(64 * 4 + 3)], 0x80)
    XCTAssertTrue(padded.prefix(64 * 4).allSatisfy { $0 == 0 })
    let mask = try NativeHiddenCoreMLWorker.frameMask(1)
    XCTAssertEqual(Array(mask.prefix(4)), [1, 0, 0, 0])
    XCTAssertTrue(mask.dropFirst(4).allSatisfy { $0 == 0 })
    XCTAssertThrowsError(try NativeHiddenCoreMLWorker.frameMask(200))
  }
}
