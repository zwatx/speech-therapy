#if DEBUG && targetEnvironment(simulator)
  import AVFoundation
  import Foundation
  import XCTest
  @testable import CadenceLearner

  enum SoundFixture {
    static let nonce = "00000000-0000-4000-8000-000000000456"
    static let context = ResearchSoundCheckContext(
      sessionId: "unit-session", generation: 3, setupGeneration: 2, roundId: "unit-round",
      takeId: "unit-take", captureId: "unit-capture",
      attemptId: "00000000-0000-4000-8000-000000000123")
    static var declaration: ResearchSoundDeclaration {
      .init(
        serverNonce: nonce, csrfToken: String(repeating: "f", count: 64), processingAvailable: true)
    }
    static func declarationData(_ declaration: ResearchSoundDeclaration = declaration) throws
      -> Data
    {
      try ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "kind": .string(ResearchSoundContract.kind),
        "purpose": .string(ResearchSoundContract.purpose),
        "serverNonce": .string(declaration.serverNonce),
        "csrfToken": .string(declaration.csrfToken), "binding": ResearchSoundContract.binding,
        "policy": ResearchSoundContract.policy,
        "processingAvailable": .bool(declaration.processingAvailable),
        "claimLimits": ResearchSoundContract.falseClaims,
      ]).canonical()
    }
    static func prepared() throws -> ResearchSoundPrepared {
      try ResearchSoundContract.prepare(
        audio: FeedbackFixture.wav(), declaration: declaration, context: context)
    }
    static func response(
      _ prepared: ResearchSoundPrepared, status: String = "inconclusive",
      reason: String = "uncovered_mass_dominates", preference: ResearchSoundJSON = .null
    ) throws -> Data {
      try ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "kind": .string(ResearchSoundContract.kind),
        "purpose": .string(ResearchSoundContract.purpose), "status": .string(status),
        "reason": .string(reason), "modelPreference": preference, "binding": prepared.expected,
        "claimLimits": ResearchSoundContract.falseClaims,
      ]).canonical()
    }
    static func replacing(_ raw: Data, path: [String], value: Any) throws -> Data {
      func change(_ input: [String: Any], _ path: ArraySlice<String>) -> [String: Any] {
        var fields = input
        if path.count == 1 {
          fields[path.first!] = value
        } else {
          fields[path.first!] = change(fields[path.first!] as! [String: Any], path.dropFirst())
        }
        return fields
      }
      return try FeedbackFixture.json(
        change(JSONSerialization.jsonObject(with: raw) as! [String: Any], path[...]))
    }
  }

  final class ResearchSoundContractTests: XCTestCase {
    func testPythonCanonicalGoldenPublicContextAndPrivateRequestHashes() throws {
      let prepared = try SoundFixture.prepared()
      let golden = try ResearchSoundJSON.parse(
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitExpected.utf8))
      XCTAssertEqual(prepared.expected, golden)
      XCTAssertEqual(
        prepared.body, Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitRequest.utf8))
      XCTAssertEqual(
        try prepared.privateRequest.canonical(),
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitPrivateRequest.utf8))
      let context = Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitContext.utf8)
      let ownership = try golden.fields([
        "attemptId", "requestSha256", "workerRequestSha256", "ownership", "audio", "source",
      ])["ownership"]!.fields([
        "sessionId", "generation", "roundId", "roundKind", "itemId", "takeId", "captureId",
        "contextSha256",
      ])
      XCTAssertEqual(ownership["contextSha256"]?.text, FeedbackContract.sha(context))
      XCTAssertEqual(
        try ResearchSoundContract.declaration(
          Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitDeclaration.utf8)),
        SoundFixture.declaration)
      XCTAssertEqual(
        prepared.requestSha256,
        try golden.fields([
          "attemptId", "requestSha256", "workerRequestSha256", "ownership", "audio", "source",
        ])["requestSha256"]?.text)
      let body = try JSONSerialization.jsonObject(with: prepared.body) as! [String: Any]
      XCTAssertEqual(body["adultConfirmed"] as? Bool, true)
      XCTAssertEqual(body["optIn"] as? Bool, true)
      XCTAssertTrue(body["selectedChildAge"] is NSNull)
      XCTAssertEqual(body["practiceMode"] as? String, "free")
      XCTAssertEqual(body["promptId"] as? String, "r-middle-bread")
    }
    func testUnifiedPythonContractSilenceGoldenByteEquality() throws {
      let declaration = try ResearchSoundContract.declaration(
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedSilenceDeclaration.utf8))
      let context = ResearchSoundCheckContext(
        sessionId: "native-golden-session", generation: 7, setupGeneration: 3,
        roundId: "native-golden-round", takeId: "native-golden-take",
        captureId: "native-golden-capture", attemptId: "22222222-2222-4222-8222-222222222222")
      let prepared = try ResearchSoundContract.prepare(
        audio: FeedbackFixture.wav(Array(repeating: 0, count: 2400)), declaration: declaration,
        context: context)
      XCTAssertEqual(
        prepared.body, Data(ResearchUnifiedSoundFixtureMetadata.unifiedSilenceRequest.utf8))
      XCTAssertEqual(
        try prepared.privateRequest.canonical(),
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedSilencePrivateRequest.utf8))
      XCTAssertEqual(
        try prepared.expected.canonical(),
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedSilenceExpected.utf8))
      let response = try ResearchSoundContract.observation(
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedSilenceResponse.utf8),
        expected: prepared.expected)
      XCTAssertEqual(response.status, .inconclusive)
      XCTAssertEqual(response.reason, "uncovered_mass_dominates")
    }
    func testInventedUnifiedObserverProjectionHasNoAccuracyMeaning() throws {
      // Python UnitObserver + closed projector generated this preference without a model call.
      let prepared = try SoundFixture.prepared()
      let observation = try ResearchSoundContract.observation(
        Data(ResearchUnifiedSoundFixtureMetadata.unifiedUnitInventedObserverResponse.utf8),
        expected: prepared.expected)
      XCTAssertEqual(observation.status, .observedModelPreference)
      XCTAssertEqual(observation.preference?.rawValue, "r_path")
    }
    func testNoncanonicalContainerPreservesEveryPCMSampleByte() throws {
      let canonical = FeedbackFixture.wav([Int16](repeating: -12345, count: 2400))
      var original = Data(canonical.prefix(12))
      original.append(canonical[12..<36])
      original[16] = 18
      original.append(contentsOf: [0, 0])  // valid fmt18
      // Odd JUNK payload plus its required pad.
      original.append(contentsOf: Array("JUNK".utf8) + [3, 0, 0, 0, 9, 8, 7, 0])
      original.append(canonical[36...])
      let length = original.count - 8
      for offset in 0..<4 { original[4 + offset] = UInt8((length >> (offset * 8)) & 255) }
      XCTAssertEqual(try ResearchSoundContract.canonicalize(original), canonical)
      XCTAssertEqual(try ResearchSoundContract.canonicalize(canonical), canonical)
      var duplicate = original
      duplicate.append(canonical[36...])
      let doubled = duplicate.count - 8
      for offset in 0..<4 { duplicate[4 + offset] = UInt8((doubled >> (offset * 8)) & 255) }
      XCTAssertThrowsError(try ResearchSoundContract.canonicalize(duplicate))
      var truncated = original
      truncated.removeLast()
      XCTAssertThrowsError(try ResearchSoundContract.canonicalize(truncated))
    }
    func testAppleGeneratedPCMContainerAcceptedWithoutSensors() throws {
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString + ".wav")
      defer { try? FileManager.default.removeItem(at: url) }
      let format = try XCTUnwrap(
        AVAudioFormat(
          commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true))
      let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 2400))
      buffer.frameLength = 2400
      let samples = try XCTUnwrap(buffer.int16ChannelData)
      for index in 0..<2400 { samples[0][index] = Int16(index - 1200) }
      try autoreleasepool {
        let output = try AVAudioFile(
          forWriting: url, settings: format.settings, commonFormat: .pcmFormatInt16,
          interleaved: true)
        try output.write(from: buffer)
      }
      let original = try FeedbackPCM.read(url)
      let normalized = try ResearchSoundContract.canonicalize(original)
      XCTAssertEqual(normalized, FeedbackFixture.wav((0..<2400).map { Int16($0 - 1200) }))
      XCTAssertEqual(try FeedbackPCM.measure(original), try FeedbackPCM.measure(normalized))
    }
    func testActualSavedGeneratedToneMetadataStaysInconclusive() throws {
      let data = Data(ResearchSoundFixtureMetadata.savedPublicResponse.utf8)
      let root = try ResearchSoundJSON.parse(data).fields([
        "schemaVersion", "kind", "purpose", "status", "reason", "modelPreference", "binding",
        "claimLimits",
      ])
      // The historical actual result stays unchanged; the successor refuses its old binding.
      XCTAssertEqual(root["status"], .string("inconclusive"))
      XCTAssertEqual(root["reason"], .string("uncovered_mass_dominates"))
      XCTAssertEqual(root["modelPreference"], .null)
      XCTAssertThrowsError(try ResearchSoundContract.validateExpected(root["binding"]!))
      XCTAssertThrowsError(
        try ResearchSoundContract.observation(data, expected: root["binding"]!))
      XCTAssertThrowsError(
        try ResearchSoundContract.observation(data, expected: SoundFixture.prepared().expected))
    }
    func testHistoricalDeclarationsExpectationsAndResponsesAreRejected() throws {
      XCTAssertThrowsError(
        try ResearchSoundContract.declaration(
          Data(ResearchSoundFixtureMetadata.rootGoldenDeclaration.utf8)))
      for raw in [
        ResearchSoundFixtureMetadata.goldenExpected,
        ResearchSoundFixtureMetadata.rootGoldenExpected,
        ResearchSoundSuccessorFixtureMetadata.successorUnitExpected,
        ResearchSoundSuccessorFixtureMetadata.successorSilenceExpected,
      ] {
        XCTAssertThrowsError(
          try ResearchSoundContract.validateExpected(ResearchSoundJSON.parse(Data(raw.utf8))))
      }
      let prepared = try SoundFixture.prepared()
      XCTAssertThrowsError(
        try ResearchSoundContract.observation(
          Data(ResearchSoundFixtureMetadata.rootGoldenResponse.utf8), expected: prepared.expected))
      for raw in [
        ResearchSoundSuccessorFixtureMetadata.successorUnitDeclaration,
        ResearchSoundSuccessorFixtureMetadata.successorSilenceDeclaration,
      ] {
        XCTAssertThrowsError(try ResearchSoundContract.declaration(Data(raw.utf8)))
      }
      for raw in [
        ResearchSoundSuccessorFixtureMetadata.successorUnitResponse,
        ResearchSoundSuccessorFixtureMetadata.successorSilenceResponse,
      ] {
        XCTAssertThrowsError(
          try ResearchSoundContract.observation(Data(raw.utf8), expected: prepared.expected))
      }
      // Also refuse the old feature when all other fields have the current binding.
      let successorFeature = "87930cdbdb4ca48cb19b1b7d08e5517a9f9ff79fda095133b83643d736eb12e5"
      XCTAssertThrowsError(
        try ResearchSoundContract.declaration(
          SoundFixture.replacing(
            SoundFixture.declarationData(), path: ["binding", "sources", "featureSourceSha256"],
            value: successorFeature)))
      let oldFeature = "6c643e35416caba6fe087191b500539f216afb0cd5cd345475e99a04c26cab8c"
      XCTAssertThrowsError(
        try ResearchSoundContract.declaration(
          SoundFixture.replacing(
            SoundFixture.declarationData(), path: ["binding", "sources", "featureSourceSha256"],
            value: oldFeature)))
      XCTAssertEqual(ResearchSoundContract.origin, "http://127.0.0.1:8793")
    }
    func testHistoricalWordBindingsAreRejectedWithCurrentSoundFeature() throws {
      for raw in [
        ResearchSoundFixtureMetadata.rootGoldenDeclaration,
        ResearchSoundSuccessorFixtureMetadata.successorUnitDeclaration,
      ] {
        let root = try JSONSerialization.jsonObject(with: Data(raw.utf8)) as! [String: Any]
        let oldWords = (root["binding"] as! [String: Any])["wordBinding"]!
        XCTAssertThrowsError(
          try ResearchSoundContract.declaration(
            SoundFixture.replacing(
              SoundFixture.declarationData(), path: ["binding", "wordBinding"], value: oldWords)))
      }
    }
    func testEverySoundAndWordPinMutationIsRejected() throws {
      let raw = try SoundFixture.declarationData()
      let binding = try JSONSerialization.jsonObject(with: raw) as! [String: Any]
      let sources = (binding["binding"] as! [String: Any])["sources"] as! [String: Any]
      for key in sources.keys {
        XCTAssertThrowsError(
          try ResearchSoundContract.declaration(
            SoundFixture.replacing(
              raw, path: ["binding", "sources", key], value: String(repeating: "0", count: 64))),
          key)
      }
      for key in FeedbackContract.corePins.keys {
        XCTAssertThrowsError(
          try ResearchSoundContract.declaration(
            SoundFixture.replacing(
              raw, path: ["binding", "wordBinding", "pins", key],
              value: String(repeating: "0", count: 64))), key)
      }
      for key in [
        "feedbackSourceSha256", "wrapperSourceSha256", "feedbackPolicySha256", "contentSha256",
      ] {
        XCTAssertThrowsError(
          try ResearchSoundContract.declaration(
            SoundFixture.replacing(
              raw, path: ["binding", "wordBinding", key], value: String(repeating: "0", count: 64))),
          key)
      }
    }
    func testClaimsPolicyNonceBooleanAndClosedShape() throws {
      let raw = try SoundFixture.declarationData()
      for key in ResearchSoundContract.claims {
        for flag in [true as Any, 0 as Any] {
          XCTAssertThrowsError(
            try ResearchSoundContract.declaration(
              SoundFixture.replacing(raw, path: ["claimLimits", key], value: flag)))
        }
      }
      for (path, value) in [
        (["policy", "maximumClaims"], 129 as Any), (["processingAvailable"], 0 as Any),
        (["serverNonce"], "not-a-v4-uuid" as Any), (["extra"], false as Any),
      ] {
        XCTAssertThrowsError(
          try ResearchSoundContract.declaration(
            SoundFixture.replacing(raw, path: path, value: value)))
      }
      let unavailable = try ResearchSoundContract.declaration(
        SoundFixture.declarationData(
          .init(
            serverNonce: SoundFixture.nonce, csrfToken: String(repeating: "e", count: 64),
            processingAvailable: false)))
      XCTAssertFalse(unavailable.processingAvailable)
    }
    func testAllStatusesAndReasonCoherenceWithFullExpectedBinding() throws {
      let prepared = try SoundFixture.prepared()
      for preference in ["r_path", "w_path", "other_path"] {
        XCTAssertEqual(
          try ResearchSoundContract.observation(
            SoundFixture.response(
              prepared, status: "observed_model_preference", reason: "model_preferred_candidate",
              preference: .string(preference)), expected: prepared.expected
          ).preference?.rawValue, preference)
      }
      for reason in ResearchSoundContract.inconclusive {
        XCTAssertEqual(
          try ResearchSoundContract.observation(
            SoundFixture.response(prepared, reason: reason), expected: prepared.expected
          ).status, .inconclusive)
      }
      for reason in ResearchSoundContract.unavailable {
        XCTAssertEqual(
          try ResearchSoundContract.observation(
            SoundFixture.response(prepared, status: "unavailable", reason: reason),
            expected: prepared.expected
          ).status, .unavailable)
      }
      XCTAssertEqual(
        try ResearchSoundContract.observation(
          SoundFixture.response(prepared, status: "unsupported", reason: "unsupported_prompt"),
          expected: prepared.expected
        ).status, .unsupported)
      for (status, reason, preference) in [
        ("observed_model_preference", "model_preferred_candidate", ResearchSoundJSON.null),
        ("inconclusive", "uncovered_mass_dominates", .string("r_path")),
        ("unavailable", "model_preferred_candidate", .null),
        ("observed_model_preference", "clipping", .string("w_path")),
      ] {
        XCTAssertThrowsError(
          try ResearchSoundContract.observation(
            SoundFixture.response(prepared, status: status, reason: reason, preference: preference),
            expected: prepared.expected))
      }
      let raw = try SoundFixture.response(prepared)
      for key in ["attemptId", "requestSha256", "workerRequestSha256"] {
        XCTAssertThrowsError(
          try ResearchSoundContract.observation(
            SoundFixture.replacing(
              raw, path: ["binding", key], value: String(repeating: "0", count: 64)),
            expected: prepared.expected))
      }
      for path in [["binding", "ownership", "generation"], ["binding", "audio", "sampleCount"]] {
        XCTAssertThrowsError(
          try ResearchSoundContract.observation(
            SoundFixture.replacing(raw, path: path, value: 1), expected: prepared.expected))
      }
    }
    func testMalformedDuplicateNonfiniteOversizeAndNoDiagnosticFields() throws {
      let prepared = try SoundFixture.prepared()
      let raw = try SoundFixture.response(prepared)
      for data in [
        Data("{\"schemaVersion\":1,\"schemaVersion\":1}".utf8), Data("{\"x\":NaN}".utf8),
        Data(repeating: 32, count: 12001), Data("[]".utf8),
      ] {
        XCTAssertThrowsError(
          try ResearchSoundContract.observation(data, expected: prepared.expected))
      }
      for key in ["score", "decodedPhones", "pid", "posterior"] {
        XCTAssertThrowsError(
          try ResearchSoundContract.observation(
            SoundFixture.replacing(raw, path: [key], value: 1), expected: prepared.expected))
      }
    }
    func testCanonicalPCMCountsAndChunkRefusal() throws {
      for count in [2400, 64000] {
        XCTAssertNoThrow(
          try ResearchSoundContract.descriptor(
            FeedbackFixture.wav(Array(repeating: 0, count: count))))
      }
      for count in [1, 1600, 2399, 64001] {
        XCTAssertThrowsError(
          try ResearchSoundContract.descriptor(
            FeedbackFixture.wav(Array(repeating: 0, count: count))))
      }
      var bad = FeedbackFixture.wav()
      bad[16] = 18
      XCTAssertThrowsError(try ResearchSoundContract.descriptor(bad))
      bad = FeedbackFixture.wav()
      bad[24] = 68
      XCTAssertThrowsError(try ResearchSoundContract.descriptor(bad))
    }
  }
#endif
