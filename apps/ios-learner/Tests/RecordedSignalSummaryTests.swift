import AVFoundation
import XCTest

@testable import CadenceLearner

@MainActor
final class RecordedSignalSummaryTests: XCTestCase {
  private func wave(
    _ bits: [UInt32], float: Bool = false, rate: UInt32 = 16_000,
    channels: UInt16 = 1
  ) -> Data {
    let width = float ? 4 : 2
    var result = Data()
    func text(_ value: String) { result.append(contentsOf: value.utf8) }
    func little(_ value: UInt32, _ bytes: Int) {
      for shift in 0..<bytes { result.append(UInt8(truncatingIfNeeded: value >> (8 * shift))) }
    }
    text("RIFF")
    little(UInt32(36 + bits.count * width), 4)
    text("WAVEfmt ")
    little(16, 4)
    little(float ? 3 : 1, 2)
    little(UInt32(channels), 2)
    little(rate, 4)
    little(rate * UInt32(channels) * UInt32(width), 4)
    little(UInt32(channels) * UInt32(width), 2)
    little(UInt32(width * 8), 2)
    text("data")
    little(UInt32(bits.count * width), 4)
    for value in bits { little(value, width) }
    return result
  }

  private func pcm(_ values: [Int16]) -> Data {
    wave(values.map { UInt32(UInt16(bitPattern: $0)) })
  }

  private func withScanner(_ body: (SystemAudioCapturer, URL) throws -> Void) throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(
      at: directory, withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])
    defer { try? FileManager.default.removeItem(at: directory) }
    let files = ProcessAudioFileOwnership()
    let hardware = AudioHardwareOwnership()
    var factoryCalls = 0
    let scanner = SystemAudioCapturer(
      recordingStore: TemporaryRecordingStore(directory: directory),
      fileOwnership: files, hardwareOwnership: hardware,
      driverFactory: {
        factoryCalls += 1
        fatalError("Generated scan must never request a driver")
      })
    try body(scanner, directory)
    XCTAssertEqual(factoryCalls, 0)
    XCTAssertNil(hardware.currentLease)
    XCTAssertTrue(files.protectedURLs.isEmpty)
    XCTAssertTrue(files.pendingCleanupOwners.isEmpty)
  }

  func testActualPCM16ScanAdmitsZerosRailsNearRailsAndFinalFrames() throws {
    try withScanner { scanner, directory in
      let cases: [([Int16], Int, Int, Int, Float)] = [
        (Array(repeating: 0, count: 16_000), 16_000, 0, 0, -160),
        (
          [-32768, 32767], 0, 2, 32768,
          Float(10 * log10((1 + pow(32767.0 / 32768, 2)) / 2))
        ),
        (
          [-32767, 32766, 0], 1, 0, 32767,
          Float(10 * log10((pow(32767.0 / 32768, 2) + pow(32766.0 / 32768, 2)) / 3))
        ),
        (Array(repeating: 8192, count: 16_000), 0, 0, 8192, Float(10 * log10(0.0625))),
        (
          Array(repeating: 0, count: 63_998) + [-32768, 32767], 63_998, 2, 32768,
          Float(10 * log10((1 + pow(32767.0 / 32768, 2)) / 64_000))
        ),
      ]
      for (index, item) in cases.enumerated() {
        let url = directory.appendingPathComponent("generated-\(index).wav")
        try pcm(item.0).write(to: url)
        let summary = try scanner.recordedSummary(at: url)
        let signal = try XCTUnwrap(
          summary.pcm16Signal, "Actual PCM16 conversion is an admission gate")
        XCTAssertEqual(signal.sampleCount, item.0.count)
        XCTAssertEqual(signal.zeroSampleCount, item.1)
        XCTAssertEqual(signal.railSampleCount, item.2)
        XCTAssertEqual(signal.peakMagnitude, item.3)
        XCTAssertEqual(summary.duration, Double(item.0.count) / 16_000)
        XCTAssertEqual(summary.averagePower, item.4, accuracy: 0.0001)
        let legacy = CaptureSummary(duration: summary.duration, averagePower: summary.averagePower)
        XCTAssertEqual(
          CaptureQualityAssessor().assess(summary), CaptureQualityAssessor().assess(legacy))
        try FileManager.default.removeItem(at: url)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
      }
    }
  }

  func testActualFloatFileKeepsWholeTailRMSButNeverInventsPCM16Evidence() throws {
    try withScanner { scanner, directory in
      let url = directory.appendingPathComponent("generated-float.wav")
      var samples = Array(repeating: Float(0), count: 64_000)
      for index in 63_488..<64_000 { samples[index] = 0.5 }
      try wave(samples.map(\.bitPattern), float: true).write(to: url)
      let summary = try scanner.recordedSummary(at: url)
      XCTAssertNil(summary.pcm16Signal)
      XCTAssertEqual(summary.duration, 4)
      XCTAssertEqual(summary.averagePower, Float(10 * log10(512 * 0.25 / 64_000)), accuracy: 0.001)
      samples[63_999] = .nan
      try wave(samples.map(\.bitPattern), float: true).write(to: url)
      XCTAssertThrowsError(try scanner.recordedSummary(at: url))
    }
  }

  func testExistingRateChannelAndFrameBoundsStillReject() throws {
    try withScanner { scanner, directory in
      let invalid = [
        wave([0], rate: 44_100), wave([0, 0], channels: 2), pcm([]),
        pcm(Array(repeating: 0, count: 64_001)),
      ]
      for (index, bytes) in invalid.enumerated() {
        let url = directory.appendingPathComponent("invalid-\(index).wav")
        try bytes.write(to: url)
        XCTAssertThrowsError(try scanner.recordedSummary(at: url))
      }
    }
  }
}
