import Foundation
import XCTest

@testable import CadenceLearner

final class NativeFeatureHeadMathTests: XCTestCase {
  func testUniformHeadsIgnoreLargeFiniteOffsets() throws {
    let offsets: [Float] = [
      0, 65_536, -65_536, 16_777_216, -16_777_216, 1e20, -1e20,
      .greatestFiniteMagnitude, -.greatestFiniteMagnitude,
    ]
    for scalarOffset in offsets {
      for compactOffset in offsets {
        let result = try NativeFeatureHeadMath.mixture(
          scalar: Array(repeating: scalarOffset, count: 3),
          compact: Array(repeating: compactOffset, count: 3), tick: {})
        for values in [result.scalarLogProb, result.compactLogProb, result.mixtureLogProb] {
          assertClose(values, Array(repeating: -log(3.0), count: 3))
        }
        assertClose(result.probabilities, Array(repeating: 1.0 / 3, count: 3))
      }
    }
  }

  func testIndependentHeadOffsetsPreserveRepresentableDifferences() throws {
    let scalar: [Float] = [0, 2, 4]
    let compact: [Float] = [4, 2, 0]
    let baseline = try NativeFeatureHeadMath.mixture(scalar: scalar, compact: compact, tick: {})
    let offsets: [Float] = [65_536, -65_536, 16_777_216, -16_777_216]
    for scalarOffset in offsets {
      for compactOffset in offsets {
        let shiftedScalar = scalar.map { $0 + scalarOffset }
        let shiftedCompact = compact.map { $0 + compactOffset }
        // Prove the Float inputs retain the intended differences before testing the helper.
        XCTAssertEqual(shiftedScalar.map { $0 - scalarOffset }, scalar)
        XCTAssertEqual(shiftedCompact.map { $0 - compactOffset }, compact)
        let result = try NativeFeatureHeadMath.mixture(
          scalar: shiftedScalar, compact: shiftedCompact, tick: {})
        assertClose(result.scalarLogProb, baseline.scalarLogProb)
        assertClose(result.compactLogProb, baseline.compactLogProb)
        assertClose(result.mixtureLogProb, baseline.mixtureLogProb)
        assertClose(result.probabilities, baseline.probabilities)
      }
    }
  }

  func testUnequalHeadsProduceAnalyticalEqualMixture() throws {
    let uniform: [Float] = [0, 0, 0]
    let weighted: [Float] = [0, Float(log(2.0)), Float(log(3.0))]
    // Expected probabilities use the actual Float-represented inputs, independently
    // normalized in the probability domain rather than the helper's log-domain formula.
    let weights = weighted.map { exp(Double($0)) }
    let sum = weights.reduce(0, +)
    let weightedProbabilities = weights.map { $0 / sum }
    let uniformProbabilities = Array(repeating: 1.0 / 3, count: 3)
    let expected = weightedProbabilities.map { 0.5 * (1.0 / 3 + $0) }
    for swapped in [false, true] {
      let result = try NativeFeatureHeadMath.mixture(
        scalar: swapped ? weighted : uniform, compact: swapped ? uniform : weighted, tick: {})
      assertClose(result.scalarLogProb,
        (swapped ? weightedProbabilities : uniformProbabilities).map { log($0) })
      assertClose(result.compactLogProb,
        (swapped ? uniformProbabilities : weightedProbabilities).map { log($0) })
      assertClose(result.probabilities, expected)
      assertClose(result.mixtureLogProb, expected.map { log($0) })
      XCTAssertEqual(result.probabilities.reduce(0, +), 1, accuracy: 1e-12)
      XCTAssertTrue(result.probabilities.allSatisfy { $0.isFinite && $0 >= 0 && $0 <= 1 })
      XCTAssertTrue((result.scalarLogProb + result.compactLogProb + result.mixtureLogProb)
        .allSatisfy(\.isFinite))
    }
  }

  func testMalformedLogitsAndCancellationRemainRejected() throws {
    let valid: [Float] = [0, 1, 2]
    let malformed: [[Float]] = [[], [0, 1], [0, 1, 2, 3],
      [.nan, 1, 2], [0, .infinity, 2], [0, 1, -.infinity]]
    for invalid in malformed {
      for invalidScalar in [false, true] {
        XCTAssertThrowsError(try NativeFeatureHeadMath.mixture(
          scalar: invalidScalar ? invalid : valid,
          compact: invalidScalar ? valid : invalid, tick: {})) { error in
          guard case NativeFeatureHeadMath.Failure.logits = error else {
            return XCTFail("Expected logits failure, received \(error)")
          }
        }
      }
    }
    enum Sentinel: Error { case cancelled }
    var ticks = 0
    XCTAssertThrowsError(try NativeFeatureHeadMath.mixture(scalar: valid, compact: valid) {
      ticks += 1
      if ticks == 2 { throw Sentinel.cancelled }
    }) { error in
      guard case Sentinel.cancelled = error else {
        return XCTFail("Cancellation must propagate unchanged, received \(error)")
      }
    }
    XCTAssertEqual(ticks, 2, "The interior callback must stop computation immediately.")
  }

  private func assertClose(
    _ actual: [Double], _ expected: [Double], file: StaticString = #filePath, line: UInt = #line
  ) {
    XCTAssertEqual(actual.count, expected.count, file: file, line: line)
    for (actualValue, expectedValue) in zip(actual, expected) {
      XCTAssertEqual(actualValue, expectedValue, accuracy: 1e-12, file: file, line: line)
    }
  }
}
