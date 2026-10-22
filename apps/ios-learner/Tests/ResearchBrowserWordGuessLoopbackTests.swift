#if DEBUG && targetEnvironment(simulator)
  import Darwin
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Explicit one-shot transport check using generated silence, never a sensor or audio output.
  @MainActor
  final class ResearchBrowserWordGuessLoopbackTests: XCTestCase {
    private static let runID = "native-browser-8803-20261007-v1"

    func testOwnedServiceMetadataPublicExampleAndOneSilentWordRequest() async throws {
      guard ProcessInfo.processInfo.environment["CADENCE_BROWSER_GUESS_LOOPBACK"] == Self.runID
      else { throw XCTSkip("Requires the separately reviewed, root-owned 8803 service") }
      XCTAssertEqual(ResearchFeedbackService.browserWordGuess.origin, "http://127.0.0.1:8803")
      let directory = FileManager.default.temporaryDirectory
      let marker = directory.appendingPathComponent("generated-" + Self.runID + ".started")
      let descriptor = Darwin.open(
        marker.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
      guard descriptor >= 0 else { throw RecordingFeedbackError.invalidRecording }
      Darwin.close(descriptor)
      // This marker is retained until root records the one-shot result; no automatic retry.
      var ledger: [String: Any] = [
        "runID": Self.runID, "origin": ResearchFeedbackService.browserWordGuess.origin,
        "plannedPosts": 1, "startedPosts": 0, "returnedPosts": 0,
        "completed": false, "input": "generated 3200-sample all-zero PCM16 WAV",
        "captureOrPlayback": false,
      ]
      defer {
        if let bytes = try? JSONSerialization.data(withJSONObject: ledger, options: [.sortedKeys]),
          let text = String(data: bytes, encoding: .utf8)
        {
          let attachment = XCTAttachment(string: text)
          attachment.name = "Owned native transport ledger"
          attachment.lifetime = .keepAlways
          add(attachment)
        }
      }
      let soundClient = ResearchSoundClient(service: .browserWordGuess)
      let soundDeclaration = try await soundClient.declaration()
      XCTAssertEqual(soundDeclaration.service, .browserWordGuess)
      XCTAssertTrue(soundDeclaration.processingAvailable)
      ledger["soundDeclarationAccepted"] = true
      let example = try XCTUnwrap(ResearchPracticeExamples.all.first { $0.sourceWord == "bread" })
      let bytes = try await ResearchPracticeExampleClient(service: .browserWordGuess)
        .load(example: example)
      XCTAssertEqual(FeedbackContract.sha(bytes), example.wavSha256)
      XCTAssertEqual(try FeedbackPCM.measure(bytes).sampleCount, 8917)
      ledger["publicExampleSha256"] = FeedbackContract.sha(bytes)

      let audio = FeedbackFixture.wav(Array(repeating: 0, count: 3200))
      let prompt = try XCTUnwrap(ResearchFeedbackCatalog.prompts.first { $0.word == "bread" })
      let attempt = UUID(uuidString: "bf16a084-3586-4f0d-9097-5e4bbb5b8803")!
      let request = try ResearchFeedbackClient.requestBody(
        attemptId: attempt, audio: audio, prompt: prompt, practiceContext: .adult)
      ledger["requestSha256"] = FeedbackContract.sha(request)
      ledger["audioSha256"] = FeedbackContract.sha(audio)
      ledger["attemptId"] = attempt.uuidString.lowercased()
      let file = directory.appendingPathComponent("generated-" + Self.runID + ".wav")
      guard !FileManager.default.fileExists(atPath: file.path) else {
        throw RecordingFeedbackError.invalidRecording
      }
      try audio.write(to: file, options: .withoutOverwriting)
      defer { try? FileManager.default.removeItem(at: file) }
      var events: [ResearchFeedbackProcessingEvent] = []
      let result = try await ResearchWordGuessClient(service: .browserWordGuess).process(
        attemptId: attempt,
        recording: .init(url: file, summary: .init(duration: 0.2, averagePower: -160)),
        prompt: prompt, practiceContext: .adult,
        onEvent: { event in
          events.append(event)
          if event == .requestStarted {
            ledger["startedPosts"] = (ledger["startedPosts"] as? Int ?? 0) + 1
          }
        })
      ledger["returnedPosts"] = 1
      XCTAssertEqual(events, [.requestStarted])
      XCTAssertEqual(result.feedback.reason, "silence")
      XCTAssertNil(result.feedback.captureReason)
      XCTAssertEqual(result.feedback.speechReason, "silence")
      XCTAssertEqual(result.feedback.wordReason, "silence")
      XCTAssertEqual(result.feedback.capture?.sampleCount, 3200)
      XCTAssertEqual(result.feedback.speech, .notRun)
      XCTAssertEqual(result.feedback.word, .notRun)
      XCTAssertNil(result.wordGuess)
      XCTAssertFalse(result.feedback.pronunciationCorrectnessAssessed)
      XCTAssertFalse(result.feedback.diagnosisProvided)
      // The unchanged closed decoder checks all eleven false claims and original request pins.
      let after = try await soundClient.declaration()
      XCTAssertEqual(after.service, .browserWordGuess)
      XCTAssertTrue(after.processingAvailable)
      try FileManager.default.removeItem(at: file)
      XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
      ledger["generatedFileRemoved"] = true
      ledger["afterProcessingAvailable"] = after.processingAvailable
      ledger["completed"] = true
      // Root separately verifies the owned safe outer process diagnostic and cleanup markers.
    }
  }
#endif
