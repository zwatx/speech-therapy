#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Opt-in actual public GET and native file-player completion, never microphone/model/private data.
  @MainActor
  final class ResearchPracticeExampleLoopbackTests: XCTestCase {
    func testActualPublicBreadBytesAndNativePlayerCompletion() async throws {
      guard ProcessInfo.processInfo.environment["CADENCE_PUBLIC_EXAMPLE_LOOPBACK"] == "1" else {
        throw XCTSkip("Root-owned opt-in public service/player check")
      }
      let example = try XCTUnwrap(ResearchPracticeExamples.all.first { $0.sourceWord == "bread" })
      let data = try await ResearchPracticeExampleClient().load(example: example)
      XCTAssertEqual(
        FeedbackContract.sha(data),
        "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f")
      XCTAssertEqual(try FeedbackPCM.measure(data).sampleCount, 8917)
      let store = ResearchPracticeExampleStore()
      let file = try store.write(data)
      let player = SystemPracticeAudioPlayer()
      defer {
        player.stop()
        if let owned = store.ownedURL { try? store.remove(owned) }
      }
      var completed: Bool?
      try player.play(url: file) { successful in
        completed = successful
      }
      let deadline = ContinuousClock.now.advanced(by: .seconds(5))
      while completed == nil && ContinuousClock.now < deadline {
        try await Task.sleep(for: .milliseconds(10))
      }
      XCTAssertEqual(completed, true, "Actual AVAudioPlayer delegate must complete successfully")
      player.stop()
      try store.remove(file)
      XCTAssertNil(store.ownedURL)
      XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
      // Successful playback/delegate is execution evidence; no human audibility/accuracy claim.
    }
  }
#endif
