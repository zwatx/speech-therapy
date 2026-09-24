import CoreML
import XCTest

@testable import CadenceLearner

final class WhisperDecoderLogitsTests: XCTestCase {
    private let layouts = [[51864, 1], [51865, 1], [103728, 2]]

    func testPreservesOriginalIndexedSemanticsAcrossContiguousAndStridedLayouts() throws {
        for strides in layouts {
            let (scores, expected) = try fixture(strides: strides)
            XCTAssertEqual(scores.strides.map(\.intValue), strides)
            var checks = 0
            let copied = try WhisperDecoderLogits.copy(scores) { checks += 1 }
            XCTAssertEqual(copied.map(\.bitPattern), expected)
            XCTAssertEqual(checks, 51) // Indices 0, 1024, ... 51200.
        }
    }

    func testNoncanonicalSignedNaNPayloadsUseOriginalIndexedConversion() throws {
        let (scores, expected) = try fixture(patterns: [0x7fc12345, 0xffc12345])
        scores.withUnsafeBufferPointer(ofType: Float.self) { buffer in
            XCTAssertEqual(buffer[0].bitPattern, 0x7fc12345)
            XCTAssertEqual(buffer[1].bitPattern, 0xffc12345)
        }
        let copied = try WhisperDecoderLogits.copy(scores) {}
        XCTAssertTrue(copied.allSatisfy(\.isNaN))
        XCTAssertEqual(copied.map(\.bitPattern), expected)
    }

    func testInvalidMetadataFailsBeforeAnyCancellationOrCopy() throws {
        var arrays = [try MLMultiArray(shape: [1, 51864], dataType: .double)]
        for shape in [[51864], [2, 25932], [1, 1, 51864], [1, 51863]] {
            arrays.append(try MLMultiArray(shape: shape.map { NSNumber(value: $0) }, dataType: .float32))
        }
        for scores in arrays {
            var checks = 0
            XCTAssertThrowsError(try WhisperDecoderLogits.copy(scores) { checks += 1 }) { error in
                guard case WhisperProviderError.invalidTensor = error else {
                    return XCTFail("Unexpected metadata error: \(error)")
                }
            }
            XCTAssertEqual(checks, 0)
        }
    }

    func testCancellationStopsAtTheExactOriginalCopyBoundaryForEveryLayout() throws {
        for strides in layouts {
            let (scores, _) = try fixture(strides: strides)
            for cancellationCheck in [1, 2, 26, 51] {
                var checks = 0
                XCTAssertThrowsError(try WhisperDecoderLogits.copy(scores) {
                    checks += 1
                    if checks == cancellationCheck { throw CancellationError() }
                }) { error in
                    XCTAssertTrue(error is CancellationError)
                }
                XCTAssertEqual(checks, cancellationCheck)
            }
        }
    }

    func testPreviouslyCancelledOperationStopsAtTheFirstCopyBoundary() throws {
        let (scores, _) = try fixture()
        let stop = WhisperOperationStop()
        stop.request(.cancellation)
        var checks = 0
        XCTAssertThrowsError(try WhisperDecoderLogits.copy(scores) {
            checks += 1
            try stop.check()
        }) { error in
            XCTAssertTrue(error is CancellationError)
        }
        XCTAssertEqual(checks, 1)
    }

    func testNonfiniteScoresAreCopiedBeforeSelectionRejectsThem() throws {
        let (scores, _) = try fixture()
        var checks = 0
        let copied = try WhisperDecoderLogits.copy(scores) { checks += 1 }
        XCTAssertEqual(checks, 51)
        XCTAssertTrue(copied.contains { !$0.isFinite })
        XCTAssertThrowsError(try WhisperCoreMLWorker.maximum(
            logits: copied, stop: WhisperOperationStop(), isAllowed: { _ in true })
        ) { error in
            guard case WhisperProviderError.nonfiniteTensor = error else {
                return XCTFail("Nonfinite rejection moved or changed: \(error)")
            }
        }
    }

    /// Own generated storage independently of any model, file or production tensor.
    /// Padded columns contain a different NaN payload and must never enter the copy.
    private func fixture(strides: [Int] = [51864, 1], patterns: [UInt32] = [
            0x00000000, 0x80000000, 0x00000001, 0x80000001,
            0x7f7fffff, 0xff7fffff, 0x7f800000, 0xff800000,
            0x7fc12345, 0xffc12345, 0x3f800000,
        ]) throws -> (MLMultiArray, [UInt32]) {
        let storagePatterns = (0..<51864).map { patterns[$0 % patterns.count] }
        let capacity = 51863 * strides[1] + 1
        let storage = UnsafeMutablePointer<Float>.allocate(capacity: capacity)
        storage.initialize(repeating: Float(bitPattern: 0x7fc54321), count: capacity)
        for index in storagePatterns.indices {
            storage[index * strides[1]] = Float(bitPattern: storagePatterns[index])
        }
        do {
            let array = try MLMultiArray(dataPointer: UnsafeMutableRawPointer(storage),
                shape: [1, 51864], dataType: .float32,
                strides: strides.map { NSNumber(value: $0) }, deallocator: { raw in
                    let owned = raw.assumingMemoryBound(to: Float.self)
                    owned.deinitialize(count: capacity)
                    owned.deallocate()
                })
            // Reference the original production NSNumber read, not raw storage.
            let expected = (0..<51864).map {
                array[[0, NSNumber(value: $0)]].floatValue.bitPattern
            }
            return (array, expected)
        } catch {
            storage.deinitialize(count: capacity)
            storage.deallocate()
            throw error
        }
    }
}
