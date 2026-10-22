import AVFoundation
import CoreMedia
import Foundation
import Speech
import XCTest

@testable import CadenceLearner

@MainActor
final class LocalWordAudioInputTests: XCTestCase {
  private func format(
    _ rate: Double, _ channels: AVAudioChannelCount = 1, interleaved: Bool = false
  )
    throws -> AVAudioFormat
  {
    try XCTUnwrap(
      AVAudioFormat(
        commonFormat: .pcmFormatFloat32, sampleRate: rate, channels: channels,
        interleaved: interleaved))
  }

  private func source(_ count: Int, sample: (Int) -> Int16) throws -> AVAudioPCMBuffer {
    let format = try XCTUnwrap(
      AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true))
    let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: UInt32(count)))
    buffer.frameLength = UInt32(count)
    let data = try XCTUnwrap(buffer.int16ChannelData?[0])
    for index in 0..<count { data[index] = sample(index) }
    return buffer
  }

  @available(iOS 26, *)
  private func samples(_ converted: LocalWordAudioInput.Prepared, channel: Int = 0) throws
    -> [Float]
  {
    var result: [Float] = []
    for buffer in converted.buffers {
      let data = try XCTUnwrap(buffer.floatChannelData)
      for index in 0..<Int(buffer.frameLength) {
        result.append(
          buffer.format.isInterleaved
            ? data[0][index * Int(buffer.format.channelCount) + channel] : data[channel][index])
      }
    }
    return result
  }

  func testActualPCM16ConversionPreservesSamplesAcrossFloatLayouts() throws {
    guard #available(iOS 26, *) else { return }
    let input = try source(4_097) { Int16(($0 % 101 - 50) * 400) }
    for interleaved in [false, true] {
      let target = try format(16_000, interleaved: interleaved)
      let result = try LocalWordAudioInput.convert(input, to: target)
      let output = try samples(result)
      XCTAssertEqual(output.count, 4_097)
      XCTAssertEqual(result.sourceFrames, 4_097)
      XCTAssertTrue(result.buffers.allSatisfy { $0.format == target })
      for index in output.indices {
        XCTAssertEqual(
          output[index], Float(input.int16ChannelData![0][index]) / 32_768,
          accuracy: 0.000_031)
      }
      XCTAssertEqual(Set(result.buffers.map { ObjectIdentifier($0) }).count, result.buffers.count)
    }
  }

  func testRealResamplingDrainsFiniteSourceAtBoundaryAndFractionalLengths() throws {
    guard #available(iOS 26, *) else { return }
    for count in [1_600, 1_601, 64_000] {
      let input = try source(count) { _ in 8_192 }
      for rate in [16_000.0, 44_100, 48_000] {
        for interleaved in [false, true] {
          let result = try LocalWordAudioInput.convert(
            input, to: format(rate, interleaved: interleaved))
          let output = try samples(result)
          XCTAssertLessThanOrEqual(abs(Double(output.count) - Double(count) * rate / 16_000), 1)
          XCTAssertEqual(output.count, result.outputFrames)
          XCTAssertTrue(output.allSatisfy { $0.isFinite })
          let center = output.dropFirst(128).dropLast(128)
          XCTAssertFalse(center.isEmpty)
          XCTAssertEqual(center.reduce(0, +) / Float(center.count), 0.25, accuracy: 0.002)
          XCTAssertEqual(
            Set(result.buffers.map { ObjectIdentifier($0) }).count, result.buffers.count)
        }
      }
    }
  }

  func testGeneratedSineAndBothEndImpulsesKeepTimeAndTail() throws {
    guard #available(iOS 26, *) else { return }
    let count = 8_000
    let sine = try source(count) {
      Int16((8_192 * sin(2 * .pi * 400 * Double($0) / 16_000)).rounded())
    }
    for rate in [44_100.0, 48_000] {
      let wave = try samples(LocalWordAudioInput.convert(sine, to: format(rate)))
      let indices = 256..<(wave.count - 256)
      let squared = indices.reduce(0.0) { sum, index in
        let difference = Double(wave[index]) - 0.25 * sin(2 * .pi * 400 * Double(index) / rate)
        return sum + difference * difference
      }
      XCTAssertLessThan(sqrt(squared / Double(indices.count)), 0.01)
      for location in [32, count - 33] {
        let pulse = try source(count) { $0 == location ? 16_384 : 0 }
        let output = try samples(LocalWordAudioInput.convert(pulse, to: format(rate)))
        let peak = try XCTUnwrap(output.indices.max { abs(output[$0]) < abs(output[$1]) })
        XCTAssertLessThanOrEqual(abs(Double(peak) - Double(location) * rate / 16_000), 2)
        XCTAssertGreaterThan(abs(output[peak]), 0.05)
      }
    }
  }

  func testRequestedFrameCursorNeverRepeatsAndReportsEndOfStreamRepeatedly() throws {
    guard #available(iOS 26, *) else { return }
    let input = try source(1_601) { Int16($0 - 800) }
    let feed = LocalWordAudioInput.Feed(input)
    var collected: [Int16] = []
    for request: UInt32 in [1, 7, 29, 1_000, 4_096] {
      var status: AVAudioConverterInputStatus = .noDataNow
      let chunk = try XCTUnwrap(feed.next(requested: request, status: &status))
      XCTAssertEqual(status, .haveData)
      XCTAssertLessThanOrEqual(chunk.frameLength, request)
      collected.append(
        contentsOf: UnsafeBufferPointer(
          start: chunk.int16ChannelData![0], count: Int(chunk.frameLength)))
    }
    XCTAssertEqual(collected, (0..<1_601).map { Int16($0 - 800) })
    for _ in 0..<2 {
      var status: AVAudioConverterInputStatus = .noDataNow
      XCTAssertNil(try feed.next(requested: 64, status: &status))
      XCTAssertEqual(status, .endOfStream)
      XCTAssertEqual(feed.cursor, 1_601)
    }
    XCTAssertTrue(feed.ended)
  }

  func testFiniteSequenceUsesCumulativeOutputFramesAndTerminates() async throws {
    guard #available(iOS 26, *) else { return }
    let input = try source(64_000) { _ in 0 }
    let result = try LocalWordAudioInput.convert(input, to: format(44_100))
    var iterator = try result.inputSequence().makeAsyncIterator()
    var frames: Int64 = 0
    var count = 0
    while let item = await iterator.next() {
      XCTAssertEqual(item.bufferStartTime, CMTime(value: frames, timescale: 44_100))
      frames += Int64(result.buffers[count].frameLength)
      count += 1
    }
    XCTAssertEqual(count, result.buffers.count)
    XCTAssertEqual(frames, Int64(result.outputFrames))
    let endAgain = await iterator.next()
    XCTAssertNil(endAgain)
    XCTAssertTrue(try samples(result).allSatisfy { $0 == 0 })
  }

  func testUnsupportedAndNonfiniteInputsFailWithoutPartialReturn() throws {
    guard #available(iOS 26, *) else { return }
    let input = try source(1_600) { _ in 1 }
    // More than two channels needs an explicit layout even for a valid PCM format.
    let layout = try XCTUnwrap(AVAudioChannelLayout(layoutTag: kAudioChannelLayoutTag_MPEG_3_0_A))
    let multichannel = AVAudioFormat(standardFormatWithSampleRate: 16_000, channelLayout: layout)
    for target in [try format(384_000), multichannel] {
      XCTAssertThrowsError(try LocalWordAudioInput.convert(input, to: target)) {
        XCTAssertEqual($0 as? LocalWordAudioInput.Failure, .unsupportedDestination)
      }
    }
    for count in [1_599, 64_001] {
      XCTAssertThrowsError(
        try LocalWordAudioInput.convert(source(count) { _ in 0 }, to: format(16_000))
      ) {
        XCTAssertEqual($0 as? LocalWordAudioInput.Failure, .invalidSource)
      }
    }
    let invalid = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format(16_000), frameCapacity: 1_600))
    invalid.frameLength = 1_600
    for index in 0..<1_600 { invalid.floatChannelData![0][index] = 0 }
    invalid.floatChannelData![0][32] = .nan
    XCTAssertThrowsError(try LocalWordAudioInput.convert(invalid, to: format(48_000))) {
      XCTAssertEqual($0 as? LocalWordAudioInput.Failure, .invalidSource)
    }
    var status: AVAudioConverterInputStatus = .noDataNow
    XCTAssertThrowsError(try LocalWordAudioInput.Feed(input).next(requested: 0, status: &status))
  }

  func testCancellationBeforeAndDuringConversionReturnsNoPreparedPrefix() async throws {
    guard #available(iOS 26, *) else { return }
    let task = Task { @MainActor in
      let input = try self.source(1_600) { _ in 0 }
      _ = try LocalWordAudioInput.convert(input, to: self.format(48_000))
      return true
    }
    task.cancel()
    do {
      _ = try await task.value
      XCTFail("Cancelled task returned converted input")
    } catch { XCTAssertTrue(error is CancellationError) }
    let input = try source(64_000) { Int16($0 % 128) }
    var boundaries = 0
    XCTAssertThrowsError(
      try LocalWordAudioInput.convert(
        input, to: format(48_000),
        checkCancellation: {
          boundaries += 1
          if boundaries == 6 { throw CancellationError() }
        })
    ) { XCTAssertTrue($0 is CancellationError) }
    XCTAssertEqual(boundaries, 6)
    XCTAssertEqual(input.int16ChannelData![0][63_999], Int16(63_999 % 128))
  }

  func testActualGeneratedWAVDecodeKeepsOriginalAdmissionAndBytes() throws {
    guard #available(iOS 26, *) else { return }
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: directory) }
    let url = directory.appendingPathComponent("generated.wav")
    let input = try source(4_000) { Int16($0 % 800 - 400) }
    let writer = try AVAudioFile(
      forWriting: url, settings: input.format.settings, commonFormat: .pcmFormatInt16,
      interleaved: true)
    try writer.write(from: input)
    writer.close()
    let bytes = try Data(contentsOf: url)
    let admission = try LocalWordWAVGate.read(fileURL: url)
    XCTAssertEqual(admission.duration, 0.25)
    XCTAssertTrue(admission.cleanupConfirmed)
    let reader = try AVAudioFile(forReading: url)
    defer { reader.close() }
    let decoded = try LocalWordAudioInput.read(reader, admittedDuration: 0.25)
    let output = try samples(LocalWordAudioInput.convert(decoded, to: format(16_000)))
    XCTAssertEqual(output.count, 4_000)
    for index in output.indices {
      XCTAssertEqual(
        output[index], Float(input.int16ChannelData![0][index]) / 32_768,
        accuracy: 0.000_031)
    }
    XCTAssertEqual(try Data(contentsOf: url), bytes)
  }
}
