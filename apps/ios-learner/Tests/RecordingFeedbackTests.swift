#if DEBUG && targetEnvironment(simulator)
  import Darwin
  import Foundation
  import XCTest
  @testable import CadenceLearner

  final class RecordingFeedbackTests: XCTestCase {
    func testNativeEncodedCatalogMatchesIndependentCanonicalPackDigest() throws {
      // Computed from the actual joined backend catalog before implementation,
      // including its single selected banana occurrence and ZH prompt.
      let data = try FeedbackContract.encoder().encode(
        ResearchFeedbackCatalog.prompts.map(\.requestPrompt))
      XCTAssertEqual(
        FeedbackContract.sha(data),
        "efb9c4c2525d4839ddd878761a9ba2a93d670896b383de351eacee2f9fee9187")
    }
    func testIndependentKnownPCMVectorRailsAndSilenceFloor() throws {
      let constant = try FeedbackPCM.measure(FeedbackFixture.wav())
      XCTAssertEqual(constant.sampleCount, 3200)
      XCTAssertEqual(constant.durationMilliseconds, 200)
      XCTAssertEqual(constant.rms, 0.25)
      XCTAssertEqual(constant.peak, 0.25)
      XCTAssertEqual(constant.rmsDbfs, -12.041199826559248, accuracy: 1e-12)
      let silent = try FeedbackPCM.measure(FeedbackFixture.wav(Array(repeating: 0, count: 1600)))
      XCTAssertEqual(silent.rmsDbfs, -120)
      let rails = try FeedbackPCM.measure(FeedbackFixture.wav([-32768, 32767]))
      XCTAssertEqual(rails.railSamples, 2)
      XCTAssertEqual(rails.peak, 1)
      XCTAssertEqual(rails.clippedFraction, 1)
      XCTAssertFalse(rails.modelCaptureValid)
    }
    func testStrictPCMFramingAndBoundedOwnedFileRead() throws {
      for audio in [
        Data(), FeedbackFixture.wav([]), FeedbackFixture.wav(Array(repeating: 1, count: 64001)),
        FeedbackFixture.wav() + Data([0]),
      ] { XCTAssertThrowsError(try FeedbackPCM.measure(audio)) }
      var wrong = FeedbackFixture.wav()
      wrong[24] = 1
      XCTAssertThrowsError(try FeedbackPCM.measure(wrong))
      let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: root) }
      let file = root.appendingPathComponent("audio.wav")
      try FeedbackFixture.wav().write(to: file)
      XCTAssertEqual(try FeedbackPCM.read(file), FeedbackFixture.wav())
      let link = root.appendingPathComponent("link.wav")
      try FileManager.default.createSymbolicLink(at: link, withDestinationURL: file)
      XCTAssertThrowsError(try FeedbackPCM.read(link))
      let fifo = root.appendingPathComponent("fifo.wav")
      XCTAssertEqual(mkfifo(fifo.path, 0o600), 0)
      XCTAssertThrowsError(try FeedbackPCM.read(fifo))
      try Data(repeating: 1, count: 132097).write(to: file)
      XCTAssertThrowsError(try FeedbackPCM.read(file))
    }
    func testDuplicateEscapedKeyInvalidUTF8NumbersAndDepthRefuse() {
      for text in [
        #"{"a":1,"\u0061":2}"#, #"{"a":NaN}"#, #"{"a":1e999}"#, #"{"a":01}"#, #"{"a":1}x"#,
        #"{"a":"\uD800"}"#,
        String(repeating: "[", count: 18) + "0" + String(repeating: "]", count: 18),
      ] { XCTAssertThrowsError(try FeedbackJSON.parse(Data(text.utf8)), text) }
      XCTAssertThrowsError(try FeedbackJSON.parse(Data([0xff])))
      XCTAssertThrowsError(try FeedbackJSON.parse(Data(repeating: 32, count: 16001)))
    }
    func testCompleteStagesAndZHNeverUpgradeTargetCorrectness() throws {
      for reason in [
        nil, "requested_word_not_matched", "recognition_uncertain", "recognition_incomplete",
        "single_word_required", "speech_not_detected", "busy", "timeout", "source_binding_failed",
        "assessment_failed", "cleanup_unconfirmed",
      ] as [String?] {
        let result = try decoded(reason: reason, unsupported: true)
        XCTAssertTrue(result.targetUnsupported)
        XCTAssertFalse(result.pronunciationCorrectnessAssessed)
        XCTAssertFalse(result.diagnosisProvided)
      }
      XCTAssertEqual(
        try decoded(audio: FeedbackFixture.wav(Array(repeating: 0, count: 1600)), reason: "silence")
          .capture?.rmsDbfs, -120)
      XCTAssertEqual(
        try decoded(
          audio: FeedbackFixture.wav(Array(repeating: 32767, count: 1600)), reason: "clipping"
        ).capture?.railSamples, 1600)
      XCTAssertNil(try decoded(audio: FeedbackFixture.wav([1]), reason: "invalid_audio").capture)
    }
    func testEveryClaimBindingPrivateShapeAndMetricSpoofRefuses() throws {
      let audio = FeedbackFixture.wav()
      let body = try FeedbackFixture.body(audio: FeedbackFixture.wav())
      let baseline = try FeedbackFixture.response(body, audio: audio)
      func reject(_ change: (inout [String: Any]) -> Void) throws {
        var value = baseline
        change(&value)
        XCTAssertThrowsError(
          try FeedbackContract.decode(
            FeedbackFixture.json(value),
            expectedBinding: FeedbackFixture.binding(body, audio: audio),
            pcm: FeedbackPCM.measure(audio), targetUnsupported: false))
      }
      for key in FeedbackContract.claims {
        try reject {
          var claims = $0["claimLimits"] as! [String: Bool]
          claims[key] = true
          $0["claimLimits"] = claims
        }
        try reject {
          var claims = $0["claimLimits"] as! [String: Bool]
          claims.removeValue(forKey: key)
          $0["claimLimits"] = claims
        }
      }
      for key in Set(FeedbackContract.pins.keys).union([
        "attemptId", "requestSha256", "audioSha256", "promptSha256", "evidenceSha256",
      ]) {
        try reject {
          var binding = $0["binding"] as! [String: Any]
          binding[key] = NSNull()
          $0["binding"] = binding
        }
      }
      for key in ["transcript", "probabilities", "recognition", "audioBase64"] {
        try reject { $0[key] = "private" }
      }
      try reject {
        var stages = $0["stages"] as! [String: Any]
        var capture = stages["capture"] as! [String: Any]
        capture["rms"] = 0.5
        stages["capture"] = capture
        $0["stages"] = stages
      }
      try reject { $0["schemaVersion"] = true }
      try reject { $0["elapsedMilliseconds"] = -1 }
      try reject { $0["suggestionCodes"] = ["try_again", "try_again"] }
      try reject { $0["suggestionCodes"] = ["diagnosis"] }
      try reject {
        $0["targetAssessment"] = ["state": "unsupported", "reason": "unsupported_target"]
      }
      try reject { $0["reason"] = "timeout" }  // Cannot retain affirmative states for an operational reason.
      var empty = baseline
      empty["suggestionCodes"] = [String]()
      XCTAssertEqual(
        try FeedbackContract.decode(
          FeedbackFixture.json(empty), expectedBinding: FeedbackFixture.binding(body, audio: audio),
          pcm: FeedbackPCM.measure(audio), targetUnsupported: false
        ).suggestions.count, 0)
    }
    func testContradictoryAcousticPrerequisitesEvidenceFailuresAndSuggestionsRefuse() throws {
      for audio in [
        FeedbackFixture.wav(Array(repeating: 0, count: 3200)),
        FeedbackFixture.wav(Array(repeating: 32767, count: 3200)),
      ] {
        for reason in [nil, "speech_not_detected", "requested_word_not_matched", "worker_timeout"]
          as [String?]
        {
          XCTAssertThrowsError(try decoded(audio: audio, reason: reason))
        }
      }
      let audio = FeedbackFixture.wav()
      let body = try FeedbackFixture.body(audio: FeedbackFixture.wav())
      for reason in ["worker_timeout", "invalid_request"] {
        var value = try FeedbackFixture.response(body, audio: audio, reason: reason)
        var binding = value["binding"] as! [String: Any]
        binding["evidenceSha256"] =
          reason == "worker_timeout" ? NSNull() : String(repeating: "a", count: 64)
        value["binding"] = binding
        XCTAssertThrowsError(
          try FeedbackContract.decode(
            FeedbackFixture.json(value),
            expectedBinding: FeedbackFixture.binding(body, audio: audio),
            pcm: FeedbackPCM.measure(audio), targetUnsupported: false))
      }
      for (reason, suggestion) in [
        (nil, "reduce_recording_level"), (nil, "retry_later"), (nil, "say_one_word"),
        ("busy", "continue_practice"),
      ] as [(String?, String)] {
        var value = try FeedbackFixture.response(body, audio: audio, reason: reason)
        value["suggestionCodes"] = [suggestion]
        XCTAssertThrowsError(
          try FeedbackContract.decode(
            FeedbackFixture.json(value),
            expectedBinding: FeedbackFixture.binding(body, audio: audio),
            pcm: FeedbackPCM.measure(audio), targetUnsupported: false))
      }
    }
    private func decoded(
      audio: Data = FeedbackFixture.wav(), reason: String? = nil, unsupported: Bool = false
    ) throws -> RecordingFeedback {
      let body = try FeedbackFixture.body(audio: audio)
      return try FeedbackContract.decode(
        FeedbackFixture.json(
          FeedbackFixture.response(body, audio: audio, reason: reason, unsupported: unsupported)),
        expectedBinding: FeedbackFixture.binding(body, audio: audio),
        pcm: FeedbackPCM.measure(audio), targetUnsupported: unsupported)
    }
  }
#endif
