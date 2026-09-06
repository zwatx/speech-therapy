import Foundation
import XCTest

@testable import CadenceLearner

/// Future copied unit fixture: no model or audio file. It holds the actual worker
/// return boundary, so cancellation signals cannot falsely authorize removal.
private final class HeldWhisperWorker: @unchecked Sendable {
    private let condition = NSCondition()
    private var released = false
    private var stop: WhisperOperationStop?
    private let entered = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
    let completion: WhisperWorkerCompletion
    private let producer: (@Sendable (LocalWordRecognitionRequest, WhisperOperationStop) -> WhisperWorkerCompletion)?
    init(cleanup: Bool = true, completion: WhisperWorkerCompletion? = nil,
         producer: (@Sendable (LocalWordRecognitionRequest, WhisperOperationStop) -> WhisperWorkerCompletion)? = nil) {
        self.completion = completion ?? .init(status: .matched, cleanupConfirmed: cleanup, retainedHandle: nil)
    }
    func run(_ request: LocalWordRecognitionRequest, _ stop: WhisperOperationStop) -> WhisperWorkerCompletion {
        condition.lock()
        self.stop = stop
        entered.continuation.yield(())
        while !released { condition.wait() }
        condition.unlock()
        return completion
    }
    func waitForEntry() async {
        var iterator = entered.stream.makeAsyncIterator()
        _ = await iterator.next()
    }
    func release() {
        condition.lock(); released = true; condition.broadcast(); condition.unlock()
    }
    func signalDeadline() {
        condition.lock(); let control = stop; condition.unlock()
        control?.request(.deadline)
    }
}

final class CoreMLLocalWordRecognizerTests: XCTestCase {
    @MainActor
    private func fixture(_ gate: HeldWhisperWorker) -> (CoreMLLocalWordRecognizer, ProcessAudioFileOwnership, UUID, LocalWordRecognitionRequest) {
        let ownership = ProcessAudioFileOwnership()
        let owner = UUID()
        let request = LocalWordRecognitionRequest(operationID: UUID(), tryID: UUID(),
            fileURL: URL(fileURLWithPath: "/generated-whisper-unit/owned.wav"), expectedWord: "sample")
        ownership.retain(request.fileURL, owner: owner)
        let provider = CoreMLLocalWordRecognizer(ownership: ownership, deadlineNanoseconds: 15_000_000_000,
                                               fixtureWorker: { gate.run($0, $1) })
        return (provider, ownership, owner, request)
    }

    @MainActor
    func testExplicitCancellationKeepsBorrowUntilWorkerReturns() async {
        let gate = HeldWhisperWorker(); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry()
        provider.cancel(operationID: request.operationID)
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        let occupied = await provider.check(request: request)
        XCTAssertTrue(occupied.status == .unavailable && !occupied.cleanupConfirmed)
        gate.release()
        let receipt = await task.value
        XCTAssertTrue(receipt.request == request && receipt.status == .cancelled && receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
    }

    @MainActor
    func testParentCancellationAlsoJoinsActualWorker() async {
        let gate = HeldWhisperWorker(); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry(); task.cancel()
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        gate.release()
        let receipt = await task.value
        XCTAssertTrue(receipt.status == .cancelled && receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
    }

    @MainActor
    func testDeadlineSignalDoesNotPromiseInterruptionOrCleanup() async {
        let gate = HeldWhisperWorker(); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry(); gate.signalDeadline()
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        let occupied = await provider.check(request: request)
        XCTAssertTrue(occupied.status == .unavailable && !occupied.cleanupConfirmed)
        gate.release()
        let receipt = await task.value
        XCTAssertEqual(receipt.request, request)
        XCTAssertTrue(receipt.status == .timedOut && receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
    }

    @MainActor
    func testExplicitCancellationAfterDeadlineStillDiscardsTheLateMatch() async {
        let gate = HeldWhisperWorker(); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry(); gate.signalDeadline()
        provider.cancel(operationID: request.operationID)
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        gate.release()
        let receipt = await task.value
        XCTAssertEqual(receipt.request, request)
        XCTAssertTrue(receipt.status == .cancelled && receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
    }

    @MainActor
    func testTimedOutWorkerWithUnconfirmedCleanupKeepsBorrowAndProviderOccupied() async {
        let gate = HeldWhisperWorker(cleanup: false); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry(); gate.signalDeadline(); gate.release()
        let receipt = await task.value
        XCTAssertEqual(receipt.request, request)
        XCTAssertTrue(receipt.status == .timedOut && !receipt.cleanupConfirmed)
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        let next = await provider.check(request: request)
        XCTAssertTrue(next.status == .unavailable && !next.cleanupConfirmed)
    }

    @MainActor
    func testUnconfirmedCleanupKeepsProviderAndBorrowOccupied() async {
        let gate = HeldWhisperWorker(cleanup: false); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry(); gate.release()
        let receipt = await task.value
        XCTAssertFalse(receipt.cleanupConfirmed)
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        let next = await provider.check(request: request)
        XCTAssertTrue(next.status == .unavailable && !next.cleanupConfirmed)
    }

    @MainActor
    func testSiblingCancellationDoesNotChangeMatchingOperation() async {
        let gate = HeldWhisperWorker(); defer { gate.release() }
        let (provider, _, _, request) = fixture(gate)
        let task = Task { await provider.check(request: request) }
        await gate.waitForEntry(); provider.cancel(operationID: UUID()); gate.release()
        let receipt = await task.value
        XCTAssertTrue(receipt.status == .matched && receipt.cleanupConfirmed)
    }

    @MainActor
    func testMissingResourcesAreUnavailableWithoutOpeningInput() async {
        let ownership = ProcessAudioFileOwnership()
        let provider = CoreMLLocalWordRecognizer(ownership: ownership)
        let request = LocalWordRecognitionRequest(operationID: UUID(), tryID: UUID(),
            fileURL: URL(fileURLWithPath: "/generated-whisper-unit/nonexistent.wav"), expectedWord: "sample")
        let receipt = await provider.check(request: request)
        XCTAssertTrue(receipt.status == .unavailable && receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    func testStopCancellationWinsDeadline() {
        let stop = WhisperOperationStop()
        stop.request(.deadline); stop.request(.cancellation); stop.request(.deadline)
        XCTAssertTrue(stop.interruptedStatus == .cancelled)
    }

    private func wav(_ samples: [Int16], rate: Int = 16000, extraOddChunk: Bool = false) -> Data {
        func le(_ value: Int, _ bytes: Int) -> [UInt8] {
            (0..<bytes).map { UInt8(truncatingIfNeeded: value >> ($0 * 8)) }
        }
        var body = Array("WAVEfmt ".utf8) + le(16, 4) + le(1, 2) + le(1, 2)
            + le(rate, 4) + le(rate * 2, 4) + le(2, 2) + le(16, 2)
        if extraOddChunk { body += Array("JUNK".utf8) + le(1, 4) + [0, 0] }
        body += Array("data".utf8) + le(samples.count * 2, 4)
        for value in samples { body += le(Int(UInt16(bitPattern: value)), 2) }
        return Data(Array("RIFF".utf8) + le(body.count, 4) + body)
    }

    func testPCM16ExactScaleAndOddChunk() throws {
        var input = [Int16](repeating: 0, count: 1600); input[0] = .min; input[1] = .max
        let samples = try WhisperPCM16.decode(wav(input, extraOddChunk: true), stop: WhisperOperationStop())
        XCTAssertTrue(samples.count == 1600 && samples[0] == -1 && samples[1] == Float(Int16.max) / 32768)
        XCTAssertTrue(samples.dropFirst(2).allSatisfy { $0 == 0 })
    }

    func testPCM16GateRejectsShortLongWrongRateAndMalformed() {
        for data in [wav(Array(repeating: 0, count: 1599)), wav(Array(repeating: 0, count: 64001)),
                     wav(Array(repeating: 0, count: 1600), rate: 8000), Data([0])] {
            do { _ = try WhisperPCM16.decode(data, stop: WhisperOperationStop()); XCTFail("Gate admitted an invalid generated fixture") }
            catch { XCTAssertTrue(error is WhisperProviderError) }
        }
    }

    func testMaximumChecksMaskedNonfiniteScores() {
        var logits = [Float](repeating: 0, count: 51864); logits[17] = .nan
        do { _ = try WhisperCoreMLWorker.maximum(logits: logits, stop: WhisperOperationStop(), isAllowed: { $0 == 1 }); XCTFail("Nonfinite score admitted") }
        catch { if case WhisperProviderError.nonfiniteTensor = error {} else { XCTFail("Wrong typed failure") } }
    }

    func testMaximumUsesEligibleLowestTieAndRejectsAllMasked() throws {
        var logits = [Float](repeating: -1, count: 51864); logits[2] = 3; logits[4] = 3; logits[7] = 100
        let choice = try WhisperCoreMLWorker.maximum(logits: logits, stop: WhisperOperationStop(), isAllowed: { $0 == 2 || $0 == 4 })
        XCTAssertTrue(choice == 2)
        do { _ = try WhisperCoreMLWorker.maximum(logits: logits, stop: WhisperOperationStop(), isAllowed: { _ in false }); XCTFail("All masked scores admitted") }
        catch { if case WhisperProviderError.noEligibleToken = error {} else { XCTFail("Wrong typed failure") } }
    }

    func testMaximumShapeAndCooperativeCancellation() {
        do { _ = try WhisperCoreMLWorker.maximum(logits: [], stop: WhisperOperationStop(), isAllowed: { _ in true }); XCTFail("Wrong shape admitted") }
        catch { if case WhisperProviderError.invalidTensor = error {} else { XCTFail("Wrong typed failure") } }
        let stop = WhisperOperationStop(); stop.request(.cancellation)
        do { _ = try WhisperCoreMLWorker.maximum(logits: Array(repeating: 0, count: 51864), stop: stop, isAllowed: { _ in true }); XCTFail("Cancellation ignored") }
        catch { XCTAssertTrue(error is CancellationError) }
    }

    func testWholeTakeSingleWordComparisonHasNoInventedTiming() {
        XCTAssertTrue(WhisperCoreMLWorker.compareCompleted(text: " Sample. ", expectedWord: "sample") == .matched)
        XCTAssertTrue(WhisperCoreMLWorker.compareCompleted(text: "different", expectedWord: "sample") == .notMatched)
        for text in ["", "sample extra", "🙂"] {
            XCTAssertTrue(WhisperCoreMLWorker.compareCompleted(text: text, expectedWord: "sample") == .uncertain)
        }
    }

    func testMelLittleEndianShapeFiniteAndCancellation() throws {
        func table(_ first: Float) -> Data {
            var bytes = [UInt8](repeating: 0, count: 80 * 201 * 4)
            for byte in 0..<4 { bytes[byte] = UInt8(truncatingIfNeeded: first.bitPattern >> (byte * 8)) }
            return Data(bytes)
        }
        let rows = try WhisperResourceAdmission.melCoefficients(table(0.5), stop: WhisperOperationStop())
        XCTAssertTrue(rows.count == 80 && rows.allSatisfy { $0.count == 201 })
        XCTAssertTrue(rows[0][0] == 0.5 && rows[79][200] == 0)
        for data in [Data(), table(-1), table(.nan), table(.infinity)] {
            do { _ = try WhisperResourceAdmission.melCoefficients(data, stop: WhisperOperationStop()); XCTFail("Invalid generated mel admitted") }
            catch { XCTAssertTrue(error is WhisperProviderError) }
        }
        let stop = WhisperOperationStop(); stop.request(.cancellation)
        do { _ = try WhisperResourceAdmission.melCoefficients(table(0), stop: stop); XCTFail("Mel cancellation ignored") }
        catch { XCTAssertTrue(error is CancellationError) }
    }
}

extension CoreMLLocalWordRecognizerTests {
    func testCompletedEOSStringSuppliesOnlyBoundedDifferentWordGuess() {
        let completed = WhisperCoreMLWorker.completedRecognition(
            text: " WALL. ", expectedWord: "ball", stop: WhisperOperationStop())
        XCTAssertEqual(completed.status, .notMatched)
        XCTAssertEqual(completed.wordGuess?.word, "wall")
        XCTAssertEqual(completed.wordGuess?.expectedWord, "ball")
        XCTAssertTrue(completed.cleanupConfirmed)
        XCTAssertNil(completed.retainedHandle)
        for text in ["ball", "", "wall ball", "🙂", String(repeating: "w", count: 33)] {
            let value = WhisperCoreMLWorker.completedRecognition(
                text: text, expectedWord: "ball", stop: WhisperOperationStop())
            XCTAssertEqual(value.status, WhisperCoreMLWorker.compareCompleted(text: text, expectedWord: "ball"))
            XCTAssertNil(value.wordGuess)
        }
    }

    func testCompletedEOSStringDiscardsGuessWhenAlreadyInterrupted() {
        let reasons: [WhisperOperationStop.Reason] = [.cancellation, .deadline]
        for reason in reasons {
            let stop = WhisperOperationStop()
            stop.request(reason)
            let completed = WhisperCoreMLWorker.completedRecognition(
                text: "wall", expectedWord: "ball", stop: stop)
            XCTAssertEqual(completed.status, stop.interruptedStatus)
            XCTAssertNil(completed.wordGuess)
        }
    }

    func testWorkerCompletionStripsGuessForOtherStatusesFailedCleanupOrRetainedHandle() throws {
        let guess = try XCTUnwrap(LocalWordGuess(completedText: "other", expectedWord: "sample"))
        let statuses: [LocalWordRecognitionStatus] = [
            .matched, .notMatched, .uncertain, .timedOut, .unavailable, .cancelled,
        ]
        for status in statuses {
            for cleanup in [false, true] {
                let completion = WhisperWorkerCompletion(
                    status: status, cleanupConfirmed: cleanup, retainedHandle: nil, wordGuess: guess)
                XCTAssertEqual(completion.status, status)
                XCTAssertEqual(completion.wordGuess, status == .notMatched && cleanup ? guess : nil)
            }
        }
        // An inert invalid descriptor creates no file, read or close operation.
        let retained = FileHandle(fileDescriptor: -1, closeOnDealloc: false)
        let completion = WhisperWorkerCompletion(
            status: .notMatched, cleanupConfirmed: true, retainedHandle: retained, wordGuess: guess)
        XCTAssertNil(completion.wordGuess)
    }

    func testFinalReceiptDiscardsCancellationArrivingAfterCompletedWorkerValue() {
        let request = LocalWordRecognitionRequest(operationID: UUID(), tryID: UUID(),
            fileURL: URL(fileURLWithPath: "/generated-whisper-unit/never-opened.wav"), expectedWord: "ball")
        let stop = WhisperOperationStop()
        let returned = WhisperCoreMLWorker.completedRecognition(text: "wall", expectedWord: "ball", stop: stop)
        XCTAssertEqual(returned.wordGuess?.word, "wall")
        // The real provider uses this same final filter after joining worker and timer.
        stop.request(.cancellation)
        let receipt = returned.receipt(request: request, interruptedStatus: stop.interruptedStatus)
        XCTAssertEqual(receipt.status, .cancelled)
        XCTAssertTrue(receipt.cleanupConfirmed)
        XCTAssertNil(receipt.wordGuess)
    }

    @MainActor
    func testInjectedCleanNonmatchForwardsGuessAndExactRequestAfterBorrowRelease() async throws {
        let guess = try XCTUnwrap(LocalWordGuess(completedText: "other", expectedWord: "sample"))
        let gate = HeldWhisperWorker(completion: .init(
            status: .notMatched, cleanupConfirmed: true, retainedHandle: nil, wordGuess: guess))
        defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let checking = Task { await provider.check(request: request) }
        await gate.waitForEntry()
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        gate.release()
        let receipt = await checking.value
        XCTAssertEqual(receipt.request, request)
        XCTAssertEqual(receipt.status, .notMatched)
        XCTAssertEqual(receipt.wordGuess, guess)
        XCTAssertTrue(receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
    }

    @MainActor
    func testInjectedNonmatchGuessIsDiscardedForCancellationAndDeadline() async throws {
        let guess = try XCTUnwrap(LocalWordGuess(completedText: "other", expectedWord: "sample"))
        for cancel in [false, true] {
            let gate = HeldWhisperWorker(completion: .init(
                status: .notMatched, cleanupConfirmed: true, retainedHandle: nil, wordGuess: guess))
            defer { gate.release() }
            let (provider, ownership, owner, request) = fixture(gate)
            let checking = Task { await provider.check(request: request) }
            await gate.waitForEntry()
            if cancel { provider.cancel(operationID: request.operationID) }
            else { gate.signalDeadline() }
            XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
            gate.release()
            let receipt = await checking.value
            XCTAssertEqual(receipt.status, cancel ? .cancelled : .timedOut)
            XCTAssertNil(receipt.wordGuess)
            XCTAssertTrue(receipt.cleanupConfirmed)
            XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
        }
    }

    @MainActor
    func testParentCancellationDiscardsInjectedGuessOnlyAfterWorkerJoins() async throws {
        let guess = try XCTUnwrap(LocalWordGuess(completedText: "other", expectedWord: "sample"))
        let gate = HeldWhisperWorker(completion: .init(
            status: .notMatched, cleanupConfirmed: true, retainedHandle: nil, wordGuess: guess))
        defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let checking = Task { await provider.check(request: request) }
        await gate.waitForEntry(); checking.cancel()
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        gate.release()
        let receipt = await checking.value
        XCTAssertEqual(receipt.status, .cancelled)
        XCTAssertNil(receipt.wordGuess)
        XCTAssertTrue(receipt.cleanupConfirmed)
        XCTAssertTrue(ownership.canRemove(request.fileURL, owner: owner))
    }

    @MainActor
    func testInjectedNonmatchGuessWithFailedCleanupKeepsBorrowAndOccupiedProvider() async throws {
        let guess = try XCTUnwrap(LocalWordGuess(completedText: "other", expectedWord: "sample"))
        let gate = HeldWhisperWorker(completion: .init(
            status: .notMatched, cleanupConfirmed: false, retainedHandle: nil, wordGuess: guess))
        defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let checking = Task { await provider.check(request: request) }
        await gate.waitForEntry(); gate.release()
        let receipt = await checking.value
        XCTAssertEqual(receipt.status, .notMatched)
        XCTAssertNil(receipt.wordGuess)
        XCTAssertFalse(receipt.cleanupConfirmed)
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        let next = await provider.check(request: request)
        XCTAssertEqual(next.status, .unavailable)
        XCTAssertFalse(next.cleanupConfirmed)
        XCTAssertNil(next.wordGuess)
    }

    @MainActor
    func testInjectedGuessBoundToDifferentExpectedWordCannotLeaveProvider() async throws {
        let wrong = try XCTUnwrap(LocalWordGuess(completedText: "other", expectedWord: "different"))
        let gate = HeldWhisperWorker(completion: .init(
            status: .notMatched, cleanupConfirmed: true, retainedHandle: nil, wordGuess: wrong))
        defer { gate.release() }
        let (provider, _, _, request) = fixture(gate)
        let checking = Task { await provider.check(request: request) }
        await gate.waitForEntry(); gate.release()
        let receipt = await checking.value
        XCTAssertEqual(receipt.request, request)
        XCTAssertEqual(receipt.status, .notMatched)
        XCTAssertTrue(receipt.cleanupConfirmed)
        XCTAssertNil(receipt.wordGuess)
    }

    @MainActor
    func testRuntimeReleaseRefusesOccupiedOrStickyCleanupAndAllowsExplicitNextCheck() async {
        let gate = HeldWhisperWorker(); defer { gate.release() }
        let (provider, ownership, owner, request) = fixture(gate)
        let checking = Task { await provider.check(request: request) }
        await gate.waitForEntry()
        let premature = await provider.releaseWordRuntime()
        XCTAssertFalse(premature)
        XCTAssertFalse(ownership.canRemove(request.fileURL, owner: owner))
        provider.cancel(operationID: request.operationID)
        gate.release()
        let receipt = await checking.value
        XCTAssertEqual(receipt.status, .cancelled)
        XCTAssertTrue(receipt.cleanupConfirmed)
        let released = await provider.releaseWordRuntime()
        XCTAssertTrue(released)
        let next = LocalWordRecognitionRequest(operationID: UUID(), tryID: UUID(),
            fileURL: request.fileURL, expectedWord: request.expectedWord)
        let nextReceipt = await provider.check(request: next)
        XCTAssertEqual(nextReceipt.request, next)
        XCTAssertEqual(nextReceipt.status, .matched, "No previous stop state leaks to an explicit reopened check")
        XCTAssertTrue(nextReceipt.cleanupConfirmed)

        let stickyGate = HeldWhisperWorker(cleanup: false); defer { stickyGate.release() }
        let (sticky, files, producer, original) = fixture(stickyGate)
        let failed = Task { await sticky.check(request: original) }
        await stickyGate.waitForEntry()
        stickyGate.release()
        let failedReceipt = await failed.value
        XCTAssertFalse(failedReceipt.cleanupConfirmed)
        let refused = await sticky.releaseWordRuntime()
        XCTAssertFalse(refused)
        XCTAssertFalse(files.canRemove(original.fileURL, owner: producer))
    }
}
