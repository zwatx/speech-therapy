#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Optional actual HTTP check. The input is generated silence; no sensor or speech model is used.
  @MainActor
  final class ResearchFeedbackLoopbackTests: XCTestCase {
    func testActualNativeTransportBindsAndRefusesGeneratedSilence() async throws {
      guard ProcessInfo.processInfo.environment["CADENCE_FEEDBACK_LOOPBACK"] == "1" else {
        throw XCTSkip("Explicitly enable this check with the documented local service running.")
      }
      let file = FileManager.default.temporaryDirectory.appendingPathComponent(
        "feedback-silence-\(UUID().uuidString).wav")
      var audio = Data("RIFF".utf8)
      func append(_ value: UInt32) {
        var value = value.littleEndian
        withUnsafeBytes(of: &value) { audio.append(contentsOf: $0) }
      }
      append(32_036)
      audio.append(Data("WAVEfmt ".utf8))
      append(16)
      audio.append(contentsOf: [1, 0, 1, 0])
      append(16_000)
      append(32_000)
      audio.append(contentsOf: [2, 0, 16, 0])
      audio.append(Data("data".utf8))
      append(32_000)
      audio.append(Data(repeating: 0, count: 32_000))
      XCTAssertEqual(audio.count, 32_044)
      try audio.write(to: file)
      defer { try? FileManager.default.removeItem(at: file) }
      let result = try await ResearchFeedbackClient().process(
        attemptId: UUID(),
        recording: .init(url: file, summary: .init(duration: 1, averagePower: -120)),
        prompt: ResearchFeedbackCatalog.prompts[0], practiceContext: .child(ageYears: 9))
      XCTAssertEqual(result.status, .observed)
      XCTAssertEqual(result.reason, "silence")
      XCTAssertEqual(result.capture?.sampleCount, 16_000)
      XCTAssertEqual(result.capture?.rms, 0)
      XCTAssertEqual(result.speech, .notRun)
      XCTAssertEqual(result.word, .notRun)
      XCTAssertTrue(FeedbackContract.isHash(try XCTUnwrap(result.evidenceSha256)))
      XCTAssertFalse(result.pronunciationCorrectnessAssessed)
      XCTAssertFalse(result.diagnosisProvided)
      try FileManager.default.removeItem(at: file)
      XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    }
  }
#endif
