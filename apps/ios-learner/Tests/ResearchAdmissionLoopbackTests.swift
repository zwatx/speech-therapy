#if DEBUG && targetEnvironment(simulator)
  import AVFoundation
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Explicit integration tests require the separately started new8778 service.
  /// Apple generates WAV bytes; no permission, microphone, camera or playback occurs.
  @MainActor
  final class ResearchAdmissionLoopbackTests: XCTestCase {
    func testActualAppleSilenceIsBoundUnavailableWithoutCapture() async throws {
      let outcome = try await generated(tone: false)
      XCTAssertEqual(outcome, .unavailable(reason: "silence"))
    }

    func testActualAppleNonspeechIsRejectedBeforeResearchModel() async throws {
      let outcome = try await generated(tone: true)
      XCTAssertEqual(outcome, .unavailable(reason: "speech_not_detected"))
    }

    func testLicensedPublicBananaPassesAdmissionButRemainsResearchOnly() async throws {
      let file = try XCTUnwrap(
        Bundle(for: Self.self).url(forResource: "admission-banana", withExtension: "wav"))
      let raw = try Data(contentsOf: file)
      XCTAssertEqual(
        ResearchAssessmentClient.sha256(raw),
        "8a90981bb21ef4137d9a52dd4d9b38457bbda014ce684f12910303ea5eaf7054")
      let local = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString + ".wav")
      try raw.write(to: local)
      defer { try? FileManager.default.removeItem(at: local) }
      let fileReader = SystemAudioCapturer()
      let summary = try fileReader.recordedSummary(at: local)
      let outcome = try await ResearchAdmissionClient().process(
        attemptId: UUID(),
        recording: .init(url: local, summary: summary),
        entry: PracticeLibrary.entries().first { $0.id == "n-middle-banana" }!, ageYears: 9)
      guard case .admissionProcessed(let milliseconds) = outcome else {
        return XCTFail("Expected the pinned public engineering fixture to process: \(outcome)")
      }
      XCTAssertTrue(milliseconds.isFinite && milliseconds > 0)
      // Harness age9 is separate from the public speaker's unknown age.
    }

    private func generated(tone: Bool) async throws -> ResearchAssessmentOutcome {
      let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: root) }
      let capturer = SystemAudioCapturer(recordingStore: TemporaryRecordingStore(directory: root))
      let file = root.appendingPathComponent("invented.wav")
      let format = try XCTUnwrap(
        AVAudioFormat(
          commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true))
      let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16_000))
      buffer.frameLength = 16_000
      let samples = try XCTUnwrap(buffer.int16ChannelData?[0])
      for index in 0..<16_000 {
        samples[index] = tone ? Int16(1600 * sin(2 * .pi * 220 * Double(index) / 16_000)) : 0
      }
      try autoreleasepool {
        let output = try AVAudioFile(
          forWriting: file, settings: format.settings, commonFormat: .pcmFormatInt16,
          interleaved: true)
        try output.write(from: buffer)
        if #available(iOS 18.0, *) { output.close() }
      }
      let recording = CapturedRecording(url: file, summary: try capturer.recordedSummary(at: file))
      let outcome = try await ResearchAdmissionClient().process(
        attemptId: UUID(), recording: recording,
        entry: PracticeLibrary.entries().first { $0.id == "b-beginning-baby" }!, ageYears: 9)
      try FileManager.default.removeItem(at: file)  // Fresh unique-root synthetic file; no capture owner.
      XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
      return outcome
    }
  }
#endif
