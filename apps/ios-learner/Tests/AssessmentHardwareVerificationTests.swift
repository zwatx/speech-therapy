import AVFoundation
import CryptoKit
import Foundation
import XCTest

@testable import CadenceLearner

/// Synthetic inputs only. Never requests microphone/camera access or touches shared history.
@MainActor
final class AssessmentHardwareVerificationTests: XCTestCase {
  func testParticipationRequestsCompleteProtectionOnPhysicalDevice() throws {
    #if targetEnvironment(simulator)
      throw XCTSkip("Complete file protection requires physical iOS data-protection metadata.")
    #else
      let root = try makeIsolatedRoot()
      defer { try? FileManager.default.removeItem(at: root) }
      let directory = root.appendingPathComponent("SyntheticParticipation", isDirectory: true)
      let file = directory.appendingPathComponent("participation.json")
      let store = PracticeParticipationStore(fileURL: file)
      let id = UUID(uuidString: "00000000-0000-4000-8000-000000000123")!
      let date = Date(timeIntervalSince1970: 1_700_000_000)

      try store.record(sessionID: id, completedAt: date, soundID: "b", wordCount: 1)

      XCTAssertEqual(PracticeParticipationStore(fileURL: file).entries, store.entries)
      XCTAssertEqual(store.entries.first?.id, id)
      for url in [directory, file] {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        let protection = try XCTUnwrap(
          attributes[.protectionKey],
          "Missing physical-device protection metadata: \(url.lastPathComponent)")
        XCTAssertEqual(String(describing: protection), FileProtectionType.complete.rawValue)
      }
      XCTAssertEqual(
        try directory.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup,
        true)

      try store.clear()
      let reopened = PracticeParticipationStore(fileURL: file)
      XCTAssertNil(reopened.loadError)
      XCTAssertTrue(reopened.entries.isEmpty)
      let document = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
      XCTAssertEqual(Set(document.keys), ["schemaVersion", "entries"])
      XCTAssertEqual((document["entries"] as? [[String: Any]])?.count, 0)
      XCTAssertEqual(
        try FileManager.default.contentsOfDirectory(atPath: directory.path), ["participation.json"])
      let clearedAttributes = try FileManager.default.attributesOfItem(atPath: file.path)
      XCTAssertEqual(
        String(describing: try XCTUnwrap(clearedAttributes[.protectionKey])),
        FileProtectionType.complete.rawValue)
    #endif
  }

  func testApplePCM16WaveUsesActualRecordedDurationAndPowerWithoutCapture() throws {
    let root = try makeIsolatedRoot()
    defer { try? FileManager.default.removeItem(at: root) }
    let capturer = SystemAudioCapturer(recordingStore: TemporaryRecordingStore(directory: root))
    let file = root.appendingPathComponent("synthetic.wav")
    try writeSyntheticPCM16Wave(to: file)
    try assertCanonicalPCM16Wave(Data(contentsOf: file))

    let summary = try capturer.recordedSummary(at: file)

    // One second of alternating +/-8192 PCM16 samples has RMS 0.25 (-12.0412 dBFS).
    XCTAssertEqual(summary.duration, 1, accuracy: 0.0001)
    XCTAssertEqual(summary.averagePower, -12.0412, accuracy: 0.001)
    try FileManager.default.removeItem(at: file)  // Fresh unique-root synthetic file; no capture owner.
    XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
  }

  #if DEBUG
    func testClientPreservesSyntheticAppleWaveAndBindsUnavailableResponseWithoutServer()
      async throws
    {
      let root = try makeIsolatedRoot()
      defer {
        try? FileManager.default.removeItem(at: root)
        SyntheticAssessmentProtocol.handler = nil
      }
      let capturer = SystemAudioCapturer(recordingStore: TemporaryRecordingStore(directory: root))
      let file = root.appendingPathComponent("synthetic.wav")
      try writeSyntheticPCM16Wave(to: file)
      let audio = try Data(contentsOf: file)
      try assertCanonicalPCM16Wave(audio)
      let summary = try capturer.recordedSummary(at: file)
      let attemptID = UUID(uuidString: "00000000-0000-4000-8000-000000000124")!
      let entry = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == "b-beginning-baby" })
      let configuration = URLSessionConfiguration.ephemeral
      // Intercept every request, including unexpected URLs: no network/server is needed.
      configuration.protocolClasses = [SyntheticAssessmentProtocol.self]
      SyntheticAssessmentProtocol.handler = { request in
        XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8765/v1/assessment")
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
        let body = try SyntheticAssessmentProtocol.body(of: request)
        let document = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(document["schemaVersion"] as? Int, 1)
        XCTAssertEqual(document["attemptId"] as? String, attemptID.uuidString.lowercased())
        XCTAssertEqual(document["ageYears"] as? Int, 6)
        let encodedAudio = try XCTUnwrap(document["audioBase64"] as? String)
        XCTAssertEqual(try XCTUnwrap(Data(base64Encoded: encodedAudio)), audio)
        let prompt = try XCTUnwrap(document["prompt"] as? [String: Any])
        let promptData = try JSONSerialization.data(
          withJSONObject: prompt, options: [.sortedKeys, .withoutEscapingSlashes])
        func digest(_ data: Data) -> String {
          SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        }
        let response: [String: Any] = [
          "schemaVersion": 1, "researchOnly": true, "learnerFeedbackEligible": false,
          "clinicalUseEligible": false, "productionUseEligible": false,
          "promptMatch": "unverified", "outcome": "unavailable", "reason": "model_unavailable",
          "binding": [
            "attemptId": attemptID.uuidString.lowercased(), "requestSha256": digest(body),
            "audioSha256": digest(audio), "promptSha256": digest(promptData),
          ],
          "timingMilliseconds": ["total": 1, "inference": 0],
          "captureMetrics": NSNull(),
          "targets": [], "model": NSNull(),
        ]
        return (
          try XCTUnwrap(
            HTTPURLResponse(
              url: try XCTUnwrap(request.url), statusCode: 503, httpVersion: nil,
              headerFields: ["Content-Type": "application/json"])),
          try JSONSerialization.data(withJSONObject: response)
        )
      }

      let outcome = try await ResearchAssessmentClient(configuration: configuration).process(
        attemptId: attemptID, recording: CapturedRecording(url: file, summary: summary),
        entry: entry, ageYears: 6)

      XCTAssertEqual(outcome, .unavailable(reason: "model_unavailable"))
      try FileManager.default.removeItem(at: file)  // Fresh unique-root synthetic file; no capture owner.
      XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
    }
  #endif

  private func writeSyntheticPCM16Wave(to url: URL) throws {
    let format = try XCTUnwrap(
      AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true))
    let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16_000))
    buffer.frameLength = 16_000
    let samples = try XCTUnwrap(buffer.int16ChannelData?[0])
    for index in 0..<16_000 { samples[index] = index.isMultiple(of: 2) ? 8192 : -8192 }
    try autoreleasepool {
      let output = try AVAudioFile(
        forWriting: url, settings: format.settings, commonFormat: .pcmFormatInt16, interleaved: true
      )
      try output.write(from: buffer)
      if #available(iOS 18.0, *) { output.close() }
    }
  }

  private func assertCanonicalPCM16Wave(_ audio: Data) throws {
    let bytes = [UInt8](audio)
    guard bytes.count >= 44 else { return XCTFail("WAV container must have a complete header") }
    func integer(at offset: Int, width: Int) -> Int {
      bytes[offset..<(offset + width)].enumerated().reduce(0) {
        $0 | (Int($1.element) << ($1.offset * 8))
      }
    }
    XCTAssertEqual(String(bytes: bytes[0..<4], encoding: .ascii), "RIFF")
    XCTAssertEqual(String(bytes: bytes[8..<12], encoding: .ascii), "WAVE")
    XCTAssertEqual(integer(at: 4, width: 4), bytes.count - 8)
    var position = 12
    var formatCount = 0
    var dataCount = 0
    while position + 8 <= bytes.count {
      let name = String(bytes: bytes[position..<(position + 4)], encoding: .ascii)
      let length = integer(at: position + 4, width: 4)
      let start = position + 8
      guard length <= bytes.count - start else { return XCTFail("Truncated WAV chunk") }
      if name == "fmt " {
        formatCount += 1
        guard length >= 16 else { return XCTFail("Incomplete PCM format") }
        // Independent RIFF/WAV PCM specification, not the writer's settings dictionary.
        XCTAssertEqual(integer(at: start, width: 2), 1)
        XCTAssertEqual(integer(at: start + 2, width: 2), 1)
        XCTAssertEqual(integer(at: start + 4, width: 4), 16_000)
        XCTAssertEqual(integer(at: start + 8, width: 4), 32_000)
        XCTAssertEqual(integer(at: start + 12, width: 2), 2)
        XCTAssertEqual(integer(at: start + 14, width: 2), 16)
      } else if name == "data" {
        dataCount += 1
        XCTAssertEqual(length, 32_000)
        guard length >= 4 else { return XCTFail("Missing synthetic sample payload") }
        XCTAssertEqual(Array(bytes[start..<(start + 4)]), [0, 32, 0, 224])
        XCTAssertEqual(Array(bytes[(start + length - 4)..<(start + length)]), [0, 32, 0, 224])
      }
      position = start + length + length % 2
    }
    XCTAssertEqual(position, bytes.count)
    XCTAssertEqual(formatCount, 1)
    XCTAssertEqual(dataCount, 1)
  }

  private func makeIsolatedRoot() throws -> URL {
    let support = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    let root = support.appendingPathComponent(
      "AssessmentHardwareVerification-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    return root
  }
}

#if DEBUG
  private final class SyntheticAssessmentProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler:
      (@Sendable (URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    static func body(of request: URLRequest) throws -> Data {
      if let body = request.httpBody { return body }
      let stream = try XCTUnwrap(request.httpBodyStream)
      stream.open()
      defer { stream.close() }
      var data = Data()
      var buffer = [UInt8](repeating: 0, count: 4096)
      while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: buffer.count)
        guard count >= 0 else { throw stream.streamError ?? URLError(.cannotDecodeRawData) }
        if count == 0 { break }
        data.append(contentsOf: buffer.prefix(count))
      }
      return data
    }

    override func startLoading() {
      do {
        let handler = try XCTUnwrap(Self.handler)
        let (response, data) = try handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
      } catch { client?.urlProtocol(self, didFailWithError: error) }
    }

    override func stopLoading() {}
  }
#endif
