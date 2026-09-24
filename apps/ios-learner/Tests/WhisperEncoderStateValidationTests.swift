import CoreML
import XCTest

@testable import CadenceLearner

final class WhisperEncoderStateValidationTests: XCTestCase {
    func testFiniteValuesPreserveEveryFrameCancellationCheck() throws {
        let states = try fixture()
        var checks = 0
        try WhisperEncoderStateValidation.validate(states) { checks += 1 }
        XCTAssertEqual(checks, 1500)
    }

    func testNonfiniteValuesFailAtFirstInteriorAndLastLogicalPositions() throws {
        let states = try fixture()
        for value in [Float.nan, .infinity, -.infinity] {
            for position in [0, 750 * 512 + 137, 768_000 - 1] {
                let index: [NSNumber] = [0, NSNumber(value: position / 512),
                                        NSNumber(value: position % 512)]
                let original = states[index]
                states[index] = NSNumber(value: value)
                var checks = 0
                assertFailure(.nonfiniteTensor) {
                    try WhisperEncoderStateValidation.validate(states) { checks += 1 }
                }
                XCTAssertEqual(checks, position / 512 + 1)
                states[index] = original
            }
        }
    }

    func testInvalidMetadataFailsBeforeAnyCancellationOrTypedScan() throws {
        let wrongType = try MLMultiArray(shape: [1, 1500, 512], dataType: .double)
        var arrays = [wrongType]
        for shape in [[1, 512, 1500], [1500, 512], [1, 1, 1500, 512], [1, 1500, 511]] {
            arrays.append(try MLMultiArray(shape: shape.map { NSNumber(value: $0) }, dataType: .float32))
        }
        for states in arrays {
            var checks = 0
            assertFailure(.invalidTensor) {
                try WhisperEncoderStateValidation.validate(states) { checks += 1 }
            }
            XCTAssertEqual(checks, 0)
        }
    }

    func testStridedLayoutsScanOnlyLogicalValues() throws {
        for strides in [[780000, 520, 1], [768000, 1, 1500]] {
            let states = try fixture(strides: strides)
            XCTAssertEqual(states.strides.map(\.intValue), strides)
            var checks = 0
            try WhisperEncoderStateValidation.validate(states) { checks += 1 }
            XCTAssertEqual(checks, 1500)
            // Row padding starts as NaN; a logical NaN must still fail.
            states[[0, 751, 123]] = NSNumber(value: Float.nan)
            checks = 0
            assertFailure(.nonfiniteTensor) {
                try WhisperEncoderStateValidation.validate(states) { checks += 1 }
            }
            XCTAssertEqual(checks, 752)
        }
    }

    func testCancellationStopsAtTheExactFrameCheck() throws {
        for strides in [[768000, 512, 1], [780000, 520, 1], [768000, 1, 1500]] {
            let states = try fixture(strides: strides)
            for cancellationCheck in [1, 2, 750, 1500] {
                var checks = 0
                XCTAssertThrowsError(try WhisperEncoderStateValidation.validate(states) {
                    checks += 1
                    if checks == cancellationCheck { throw CancellationError() }
                }) { error in
                    XCTAssertTrue(error is CancellationError)
                }
                XCTAssertEqual(checks, cancellationCheck)
            }
        }
    }

    func testPreviouslyCancelledOperationStopsAtTheFirstFrame() throws {
        let states = try fixture()
        let stop = WhisperOperationStop()
        stop.request(.cancellation)
        var checks = 0
        XCTAssertThrowsError(try WhisperEncoderStateValidation.validate(states) {
            checks += 1
            try stop.check()
        }) { error in
            XCTAssertTrue(error is CancellationError)
        }
        XCTAssertEqual(checks, 1)
    }

    private func assertFailure(_ expected: WhisperProviderError,
                               file: StaticString = #filePath, line: UInt = #line,
                               _ body: () throws -> Void) {
        XCTAssertThrowsError(try body(), file: file, line: line) { error in
            switch (error, expected) {
            case (WhisperProviderError.invalidTensor, .invalidTensor),
                 (WhisperProviderError.nonfiniteTensor, .nonfiniteTensor): break
            default: XCTFail("Unexpected error: \(error); expected \(expected)", file: file, line: line)
            }
        }
    }

    private func fixture(strides: [Int] = [768000, 512, 1]) throws -> MLMultiArray {
        let capacity = 1499 * strides[1] + 511 * strides[2] + 1
        let storage = UnsafeMutablePointer<Float>.allocate(capacity: capacity)
        storage.initialize(repeating: .nan, count: capacity)
        let values: [Float] = [0, -0.0, .leastNonzeroMagnitude, -.leastNonzeroMagnitude,
                               .greatestFiniteMagnitude, -.greatestFiniteMagnitude, -1]
        for frame in 0..<1500 {
            for channel in 0..<512 {
                storage[frame * strides[1] + channel * strides[2]] = values[(frame + channel) % values.count]
            }
        }
        do {
            return try MLMultiArray(dataPointer: UnsafeMutableRawPointer(storage),
                shape: [1, 1500, 512], dataType: .float32,
                strides: strides.map { NSNumber(value: $0) }, deallocator: { raw in
                    let owned = raw.assumingMemoryBound(to: Float.self)
                    owned.deinitialize(count: capacity)
                    owned.deallocate()
                })
        } catch {
            storage.deinitialize(count: capacity)
            storage.deallocate()
            throw error
        }
    }
}
