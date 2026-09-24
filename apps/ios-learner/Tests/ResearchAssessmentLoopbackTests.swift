#if DEBUG
  import AVFoundation
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Optional integration check: start the documented loopback service on the host Mac.
  @MainActor
  final class ResearchAssessmentLoopbackTests: XCTestCase {
    func testActualAppleWaveAndModelPipelineRemainUnverifiedWithoutCapture() async throws {
      let root = FileManager.default.temporaryDirectory.appendingPathComponent(
        "SyntheticLoopback-\(UUID().uuidString)", isDirectory: true)
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: root) }
      let capturer = SystemAudioCapturer(recordingStore: TemporaryRecordingStore(directory: root))
      let file = root.appendingPathComponent("synthetic.wav")
      let format = try XCTUnwrap(
        AVAudioFormat(
          commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true))
      let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16_000))
      buffer.frameLength = 16_000
      let samples = try XCTUnwrap(buffer.int16ChannelData?[0])
      // Deliberate nonspeech tone, not a child utterance or the requested word.
      for index in 0..<16_000 { samples[index] = index.isMultiple(of: 2) ? 8192 : -8192 }
      try autoreleasepool {
        let output = try AVAudioFile(
          forWriting: file, settings: format.settings, commonFormat: .pcmFormatInt16,
          interleaved: true)
        try output.write(from: buffer)
        if #available(iOS 18.0, *) { output.close() }
      }
      let recording = CapturedRecording(url: file, summary: try capturer.recordedSummary(at: file))
      do {
        let outcome = try await ResearchAssessmentClient().process(
          attemptId: UUID(), recording: recording,
          entry: try XCTUnwrap(PracticeLibrary.entries().first { $0.id == "b-beginning-baby" }),
          ageYears: 6)
        guard case .processedResearch(let result) = outcome else {
          return XCTFail(
            "The available local model must process this engineering input: \(outcome)")
        }
        XCTAssertTrue(result.timingMilliseconds.total.isFinite && result.timingMilliseconds.total > 0)
        try FileManager.default.removeItem(at: file)  // Fresh unique-root synthetic file; no capture owner.
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
      } catch ResearchAssessmentError.serviceUnavailable {
        throw XCTSkip("Optional local model service absent; no model processing was verified.")
      }
    }

    func testRealIOSLoopbackRequestAndBoundUnavailableResponse() async throws {
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString + ".wav")
      // Real valid mono16kHz PCM16 one-second all-zero WAV; no participant recording.
      var audio = Data("RIFF".utf8)
      func append(_ value: UInt32) {
        var v = value.littleEndian
        withUnsafeBytes(of: &v) { audio.append(contentsOf: $0) }
      }
      append(32036)
      audio.append(Data("WAVEfmt ".utf8))
      append(16)
      audio.append(contentsOf: [1, 0, 1, 0])
      append(16000)
      append(32000)
      audio.append(contentsOf: [2, 0, 16, 0])
      audio.append(Data("data".utf8))
      append(32000)
      audio.append(Data(repeating: 0, count: 32000))
      try audio.write(to: file)
      defer { try? FileManager.default.removeItem(at: file) }
      do {
        let outcome = try await ResearchAssessmentClient().process(
          attemptId: UUID(),
          recording: .init(url: file, summary: .init(duration: 1, averagePower: -20)),
          entry: PracticeLibrary.entries().first { $0.id == "b-beginning-baby" }!, ageYears: 6)
        XCTAssertEqual(outcome, .unavailable(reason: "silence"))
      } catch ResearchAssessmentError.serviceUnavailable {
        throw XCTSkip(
          "Optional integration service absent. Start consumer_assessment.service on127.0.0.1:8765."
        )
      }
    }
  }
#endif
