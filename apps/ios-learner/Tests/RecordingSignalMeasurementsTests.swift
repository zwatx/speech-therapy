import AVFoundation
import XCTest

@testable import CadenceLearner

final class RecordingSignalMeasurementsTests: XCTestCase {
  private func measure(_ values: [Int16]) -> PCM16SignalMeasurements? {
    var accumulator = PCM16SignalMeasurements.Accumulator()
    for value in values { accumulator.append(value) }
    return accumulator.measurements()
  }

  func testBoundariesInvalidateOverflowInsteadOfKeepingPrefix() throws {
    XCTAssertNil(measure([]))
    let single = try XCTUnwrap(measure([0]))
    XCTAssertEqual(single.sampleCount, 1)
    XCTAssertTrue(single.isAllZero)
    XCTAssertEqual(single.peakNormalized, 0)
    XCTAssertEqual(measure(Array(repeating: 0, count: 64_000))?.zeroSampleCount, 64_000)
    XCTAssertNil(measure(Array(repeating: 0, count: 64_001)))
  }

  func testExactEndpointsNearEndpointsAndWidenedNegativeMagnitude() throws {
    let signal = try XCTUnwrap(measure([0, -32768, 32767, -32767, 32766, -1, 1, 0]))
    XCTAssertEqual(signal.sampleCount, 8)
    XCTAssertEqual(signal.zeroSampleCount, 2)
    XCTAssertEqual(signal.railSampleCount, 2)
    XCTAssertEqual(signal.peakMagnitude, 32768)
    XCTAssertEqual(signal.peakNormalized, 1)
    XCTAssertFalse(signal.isAllZero)
    let near = try XCTUnwrap(measure([-32767, 32766]))
    XCTAssertEqual(near.railSampleCount, 0)
    XCTAssertEqual(near.peakNormalized, 32767.0 / 32768)
  }

  func testChunkedAndReorderedAccumulationPreserveWholeClipFacts() throws {
    let values: [Int16] = [0, 1, -1, 0, 32767, -32768]
    var accumulator = PCM16SignalMeasurements.Accumulator()
    for chunk in [Array(values.prefix(2)), Array(values.dropFirst(2).prefix(3)), [values[5]]] {
      for value in chunk { XCTAssertTrue(accumulator.append(value)) }
    }
    XCTAssertEqual(accumulator.measurements(), measure(values))
    XCTAssertEqual(accumulator.measurements(), measure(Array(values.reversed())))
    let tail = try XCTUnwrap(measure(Array(repeating: 0, count: 63_999) + [-32768]))
    XCTAssertEqual(tail.zeroSampleCount, 63_999)
    XCTAssertEqual(tail.railSampleCount, 1)
  }

  func testFormatAndLatticeAdmissionRequiresActualIntegerEvidence() throws {
    let integer = try XCTUnwrap(
      AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true))
    let float = try XCTUnwrap(
      AVAudioFormat(
        commonFormat: .pcmFormatFloat32, sampleRate: 16_000, channels: 1, interleaved: false))
    let file = integer.streamDescription.pointee
    let processing = float.streamDescription.pointee
    XCTAssertTrue(PCM16CaptureAdmission.admits(file: file, processing: processing))
    for field in 0..<9 {
      var bad = file
      switch field {
      case 0: bad.mFormatFlags |= kAudioFormatFlagIsFloat
      case 1: bad.mFormatFlags |= kAudioFormatFlagIsBigEndian
      case 2: bad.mFormatFlags &= ~kAudioFormatFlagIsPacked
      case 3: bad.mFormatFlags &= ~kAudioFormatFlagIsSignedInteger
      case 4: bad.mSampleRate = 44_100
      case 5: bad.mChannelsPerFrame = 2
      case 6: bad.mBytesPerFrame = 4
      case 7: bad.mBytesPerPacket = 4
      default: bad.mFramesPerPacket = 2
      }
      XCTAssertFalse(PCM16CaptureAdmission.admits(file: bad, processing: processing))
    }
    XCTAssertFalse(PCM16CaptureAdmission.admits(file: file, processing: file))
    XCTAssertFalse(PCM16CaptureAdmission.admits(file: processing, processing: processing))
    let integers: [Int16] = [-32768, -32767, -1, 0, 1, 32766, 32767]
    for value in integers {
      XCTAssertEqual(PCM16CaptureAdmission.integerSample(Float(value) / 32768), value)
    }
    let nonLattice: [Float] = [.nan, .infinity, -.infinity, 1, -1.1, 0.1, 1.0 / 65536]
    for value in nonLattice {
      XCTAssertNil(PCM16CaptureAdmission.integerSample(value))
    }
  }
}
