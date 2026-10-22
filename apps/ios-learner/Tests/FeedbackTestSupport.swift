#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  enum FeedbackFixture {
    static let attempt = UUID(uuidString: "00000000-0000-4000-8000-000000000123")!
    static func wav(_ samples: [Int16] = Array(repeating: 8192, count: 3200)) -> Data {
      var data = Data()
      func text(_ value: String) { data.append(contentsOf: value.utf8) }
      func u16(_ value: UInt16) {
        data.append(UInt8(value & 255))
        data.append(UInt8(value >> 8))
      }
      func u32(_ value: UInt32) {
        u16(UInt16(value & 65535))
        u16(UInt16(value >> 16))
      }
      text("RIFF")
      u32(UInt32(36 + samples.count * 2))
      text("WAVEfmt ")
      u32(16)
      u16(1)
      u16(1)
      u32(16000)
      u32(32000)
      u16(2)
      u16(16)
      text("data")
      u32(UInt32(samples.count * 2))
      for sample in samples { u16(UInt16(bitPattern: sample)) }
      return data
    }
    static func declaration() -> [String: Any] {
      [
        "schemaVersion": 1, "csrfToken": String(repeating: "f", count: 64),
        "pins": FeedbackContract.corePins,
        "feedbackPolicy": [
          "id": "consumer-recording-feedback-v2",
          "sha256": FeedbackContract.pins["feedbackPolicySha256"]!,
        ],
        "feedbackSourceSha256": FeedbackContract.pins["feedbackSourceSha256"]!,
        "wrapperSourceSha256": FeedbackContract.pins["wrapperSourceSha256"]!,
        "contentSha256": FeedbackContract.pins["contentSha256"]!, "processingAvailable": true,
      ]
    }
    static func body(
      audio: Data, prompt: ResearchFeedbackPrompt = ResearchFeedbackCatalog.prompts[3],
      practiceContext: ResearchPracticeContext = .child(ageYears: 9)
    ) throws -> Data {
      let object = try JSONSerialization.jsonObject(
        with: FeedbackContract.encoder().encode(prompt.requestPrompt))
      let context = try JSONSerialization.jsonObject(
        with: FeedbackContract.encoder().encode(practiceContext))
      return try json([
        "schemaVersion": 2, "attemptId": attempt.uuidString.lowercased(), "practiceContext": context,
        "prompt": object, "audioBase64": audio.base64EncodedString(),
      ])
    }
    static func binding(_ body: Data, audio: Data) throws -> [String: String] {
      let request = try JSONSerialization.jsonObject(with: body) as! [String: Any]
      let prompt = try JSONSerialization.data(
        withJSONObject: request["prompt"]!, options: [.sortedKeys, .withoutEscapingSlashes])
      return FeedbackContract.pins.merging([
        "attemptId": request["attemptId"] as! String, "requestSha256": FeedbackContract.sha(body),
        "audioSha256": FeedbackContract.sha(audio), "promptSha256": FeedbackContract.sha(prompt),
      ]) { _, new in new }
    }
    static func response(
      _ body: Data, audio: Data, reason: String? = nil, unsupported: Bool = false
    ) throws -> [String: Any] {
      let metrics = try FeedbackPCM.measure(audio)
      var capture: [String: Any] = [
        "state": "observed", "reason": NSNull(), "sampleCount": metrics.sampleCount,
        "durationMilliseconds": metrics.durationMilliseconds, "rms": metrics.rms,
        "rmsDbfs": metrics.rmsDbfs,
        "peak": metrics.peak, "railSamples": metrics.railSamples,
        "clippedFraction": metrics.clippedFraction,
      ]
      var speech = "model_detected"
      var word = "model_matched"
      var status = "observed"
      var speechReason: Any = NSNull()
      var wordReason: Any = NSNull()
      var evidence: Any = String(repeating: "a", count: 64)
      if let reason {
        speechReason = reason
        wordReason = reason
        switch reason {
        case "requested_word_not_matched":
          word = "model_not_matched"
          speechReason = NSNull()
        case "recognition_uncertain", "recognition_incomplete":
          word = "uncertain"
          speechReason = NSNull()
        case "single_word_required":
          word = "not_single_word"
          speechReason = NSNull()
        case "speech_not_detected":
          speech = "model_not_detected"
          word = "not_run"
        case "silence", "clipping":
          speech = "not_run"
          word = "not_run"
        case "invalid_audio", "cleanup_unconfirmed":
          status = "unavailable"
          evidence = reason == "cleanup_unconfirmed" ? NSNull() : String(repeating: "a", count: 64)
          speech = reason == "invalid_audio" ? "not_run" : "unavailable"
          word = speech
          capture = Dictionary(uniqueKeysWithValues: capture.keys.map { ($0, NSNull() as Any) })
          capture["state"] = "unavailable"
          capture["reason"] = reason
        default:
          status = "unavailable"
          speech = "unavailable"
          word = "unavailable"
          evidence =
            FeedbackContract.modelFailures.contains(reason)
            ? String(repeating: "a", count: 64) : NSNull()
        }
      }
      var bindings: [String: Any] = try binding(body, audio: audio)
      bindings["evidenceSha256"] = evidence
      return [
        "schemaVersion": 1, "kind": "recording_feedback", "status": status,
        "reason": reason as Any? ?? NSNull(),
        "stages": [
          "capture": capture, "speech": ["state": speech, "reason": speechReason],
          "word": ["state": word, "reason": wordReason],
        ],
        "targetAssessment": [
          "state": unsupported ? "unsupported" : "not_performed",
          "reason": unsupported ? "unsupported_target" : "not_validated",
        ],
        "suggestionCodes": ["review_recording"], "binding": bindings,
        "claimLimits": Dictionary(
          uniqueKeysWithValues: FeedbackContract.claims.map { ($0, false) }),
        "elapsedMilliseconds": 200,
      ]
    }
    static func json(_ object: Any) throws -> Data {
      try JSONSerialization.data(
        withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    static func requestBody(_ request: URLRequest) throws -> Data {
      if let data = request.httpBody { return data }
      let stream = try XCTUnwrap(request.httpBodyStream)
      stream.open()
      defer { stream.close() }
      var result = Data()
      var buffer = [UInt8](repeating: 0, count: 4096)
      while stream.hasBytesAvailable {
        let n = stream.read(&buffer, maxLength: buffer.count)
        if n <= 0 { break }
        result.append(contentsOf: buffer.prefix(n))
      }
      return result
    }
  }

  final class FeedbackProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler:
      (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
      do {
        let (response, bytes) = try Self.handler!(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: bytes)
        client?.urlProtocolDidFinishLoading(self)
      } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
  }
#endif
