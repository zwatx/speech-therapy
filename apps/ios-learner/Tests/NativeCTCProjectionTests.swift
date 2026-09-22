import Foundation
import XCTest

@testable import CadenceLearner

final class NativeCTCProjectionTests: XCTestCase {
    private let width = 1024
    private let vocabulary = 392

    func testVocabularyMajorOrientationBiasAndEveryRowSurvive() throws {
        var weight = [Float](repeating: 0, count: vocabulary * width)
        weight[0] = 2; weight[1] = -3; weight[2] = 4
        weight[width] = -1; weight[width + 1] = 5; weight[width + 2] = 2
        var bias = [Float](repeating: 0, count: vocabulary)
        bias[0] = 7; bias[1] = -6
        let head = try NativeCTCProjection(weight: weight, bias: bias, tick: {})
        var hidden = [Float](repeating: 0, count: 2 * width)
        hidden[0] = 1; hidden[1] = 2; hidden[2] = 3
        hidden[width] = -2; hidden[width + 1] = 1; hidden[width + 2] = 0.5
        let result = try head.project(hidden: hidden, frameCount: 2, tick: {})
        XCTAssertEqual(result.frameCount, 2)
        XCTAssertEqual(result.logits.count, 2 * vocabulary)
        XCTAssertEqual(Array(result.logits[0..<2]), [15, 9])
        XCTAssertEqual(Array(result.logits[vocabulary..<vocabulary + 2]), [2, 2])
        XCTAssertTrue(result.logits[2..<vocabulary].allSatisfy { $0 == 0 })
        // Independent probability-domain normalizer includes blank and all 390 zeros.
        for (row, pair) in [[15.0, 9.0], [2.0, 2.0]].enumerated() {
            let denominator = exp(pair[0]) + exp(pair[1]) + 390
            XCTAssertEqual(Double(result.logProbabilities[row * vocabulary]),
                log(exp(pair[0]) / denominator), accuracy: 1e-6)
            XCTAssertEqual(Double(result.logProbabilities[row * vocabulary + 2]),
                log(1 / denominator), accuracy: 1e-6)
            let sum = result.logProbabilities[row * vocabulary..<(row + 1) * vocabulary]
                .reduce(0.0) { $0 + exp(Double($1)) }
            XCTAssertEqual(sum, 1, accuracy: 1e-6)
        }
    }

    func testEqualHugeLogitsKeepStableFullVocabularyNormalization() throws {
        for offset: Float in [0, -0.0, .greatestFiniteMagnitude, -.greatestFiniteMagnitude] {
            let head = try NativeCTCProjection(
                weight: Array(repeating: 0, count: vocabulary * width),
                bias: Array(repeating: offset, count: vocabulary), tick: {})
            let result = try head.project(hidden: Array(repeating: 0, count: width),
                frameCount: 1, tick: {})
            XCTAssertTrue(result.logits.allSatisfy { $0 == offset })
            for value in result.logProbabilities {
                XCTAssertEqual(Double(value), -log(392.0), accuracy: 1e-6)
            }
        }
    }

    func testRejectsMalformedShapesNonfiniteInputsAndOverflow() throws {
        let zeros = [Float](repeating: 0, count: vocabulary * width)
        let bias = [Float](repeating: 0, count: vocabulary)
        for badWeight in [Array(zeros.dropLast()), zeros + [0]] {
            XCTAssertThrowsError(try NativeCTCProjection(weight: badWeight, bias: bias, tick: {}))
        }
        XCTAssertThrowsError(try NativeCTCProjection(weight: zeros, bias: [], tick: {}))
        for nonfinite: Float in [.nan, .infinity, -.infinity] {
            var weight = zeros; weight[weight.count - 1] = nonfinite
            XCTAssertThrowsError(try NativeCTCProjection(weight: weight, bias: bias, tick: {}))
            var badBias = bias; badBias[0] = nonfinite
            XCTAssertThrowsError(try NativeCTCProjection(weight: zeros, bias: badBias, tick: {}))
        }
        let head = try NativeCTCProjection(weight: zeros, bias: bias, tick: {})
        for frames in [Int.min, 0, 200, Int.max] {
            XCTAssertThrowsError(try head.project(hidden: [], frameCount: frames, tick: {}))
        }
        XCTAssertThrowsError(try head.project(hidden: [0], frameCount: 1, tick: {}))
        var hidden = [Float](repeating: 0, count: width)
        for nonfinite: Float in [.nan, .infinity, -.infinity] {
            hidden[0] = nonfinite
            XCTAssertThrowsError(try head.project(hidden: hidden, frameCount: 1, tick: {}))
        }
        var weight = zeros; weight[0] = .greatestFiniteMagnitude
        let overflowing = try NativeCTCProjection(weight: weight, bias: bias, tick: {})
        hidden[0] = 2
        XCTAssertThrowsError(try overflowing.project(hidden: hidden, frameCount: 1, tick: {})) {
            guard case NativeCTCProjection.Failure.logits = $0 else { return XCTFail("Expected logits overflow") }
        }
        var extremeBias = bias
        extremeBias[0] = .greatestFiniteMagnitude
        extremeBias[1] = -.greatestFiniteMagnitude
        let extreme = try NativeCTCProjection(weight: zeros, bias: extremeBias, tick: {})
        XCTAssertThrowsError(try extreme.project(hidden: Array(repeating: 0, count: width), frameCount: 1, tick: {})) {
            guard case NativeCTCProjection.Failure.logProbabilities = $0 else { return XCTFail("Expected log-probability overflow") }
        }
    }

    func testCancellationPropagatesBeforeDuringAndAfterWorkWithoutOutput() throws {
        enum Sentinel: Error { case cancelled }
        let weight = [Float](repeating: 0, count: vocabulary * width)
        let bias = [Float](repeating: 0, count: vocabulary)
        XCTAssertThrowsError(try NativeCTCProjection(weight: weight, bias: bias) { throw Sentinel.cancelled })
        let head = try NativeCTCProjection(weight: weight, bias: bias, tick: {})
        let hidden = [Float](repeating: 0, count: width)
        var totalTicks = 0
        _ = try head.project(hidden: hidden, frameCount: 1) { totalTicks += 1 }
        for stop in [1, 10, totalTicks] {
            var ticks = 0
            var returnedOutput: NativeCTCProjection.Output?
            XCTAssertThrowsError(returnedOutput = try head.project(hidden: hidden, frameCount: 1) {
                ticks += 1
                if ticks == stop { throw Sentinel.cancelled }
            }) { error in
                guard case Sentinel.cancelled = error else { return XCTFail("Cancellation changed: \(error)") }
            }
            XCTAssertNil(returnedOutput)
            XCTAssertEqual(ticks, stop)
        }
    }
}
