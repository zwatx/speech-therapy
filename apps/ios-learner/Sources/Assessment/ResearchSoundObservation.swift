#if DEBUG && targetEnvironment(simulator)
  import Foundation

  /// Closed, integral JSON used only for this engineering wire contract.
  indirect enum ResearchSoundJSON: Equatable, Sendable, Encodable {
    case object([String: Self])
    case array([Self])
    case string(String)
    case integer(Int)
    case bool(Bool)
    case null
    init(_ value: FeedbackJSON.Value) throws {
      switch value {
      case .object(let fields): self = .object(try fields.mapValues(Self.init))
      case .array(let items): self = .array(try items.map(Self.init))
      case .string(let text): self = .string(text)
      case .number(_, let integer?): self = .integer(integer)
      case .bool(let flag): self = .bool(flag)
      case .null: self = .null
      default: throw RecordingFeedbackError.invalidResponse
      }
    }
    private struct Key: CodingKey {
      let stringValue: String
      var intValue: Int? { nil }
      init(_ value: String) { stringValue = value }
      init?(stringValue: String) { self.init(stringValue) }
      init?(intValue: Int) { return nil }
    }
    func encode(to encoder: any Encoder) throws {
      switch self {
      case .object(let fields):
        var out = encoder.container(keyedBy: Key.self)
        for (key, value) in fields { try out.encode(value, forKey: Key(key)) }
      case .array(let items):
        var out = encoder.unkeyedContainer()
        for item in items { try out.encode(item) }
      default:
        var out = encoder.singleValueContainer()
        switch self {
        case .string(let v): try out.encode(v)
        case .integer(let v): try out.encode(v)
        case .bool(let v): try out.encode(v)
        case .null: try out.encodeNil()
        default: break
        }
      }
    }
    func fields(_ keys: Set<String>) throws -> [String: Self] {
      guard case .object(let fields) = self, Set(fields.keys) == keys else {
        throw RecordingFeedbackError.invalidResponse
      }
      return fields
    }
    var text: String? {
      if case .string(let v) = self { return v }
      return nil
    }
    static func parse(_ data: Data) throws -> Self { try Self(FeedbackJSON.parse(data)) }
    func canonical() throws -> Data { try FeedbackContract.encoder().encode(self) }
  }

  struct ResearchSoundObservation: Equatable, Sendable {
    enum Status: String, Sendable {
      case observedModelPreference = "observed_model_preference"
      case inconclusive, unavailable, unsupported
    }
    enum Preference: String, Sendable {
      case rPath = "r_path"
      case wPath = "w_path"
      case otherPath = "other_path"
    }
    let status: Status
    let reason: String
    let preference: Preference?
    // This type deliberately has no score, posterior, decoded phones or correctness field.
  }

  struct ResearchSoundDeclaration: Equatable, Sendable {
    let serverNonce: String
    let csrfToken: String
    let processingAvailable: Bool
    let service: ResearchFeedbackService
    init(
      serverNonce: String, csrfToken: String, processingAvailable: Bool,
      service: ResearchFeedbackService = .currentUnified
    ) {
      self.serverNonce = serverNonce
      self.csrfToken = csrfToken
      self.processingAvailable = processingAvailable
      self.service = service
    }
    var identity: String { serverNonce }  // All source bytes are independently pinned by decoding.
  }

  struct ResearchSoundCheckContext: Equatable, Sendable {
    let sessionId: String
    let generation: Int
    let setupGeneration: Int
    let roundId: String
    let takeId: String
    let captureId: String
    let attemptId: String
  }

  struct ResearchSoundPrepared: Equatable, Sendable {
    let body: Data
    let privateRequest: ResearchSoundJSON
    let expected: ResearchSoundJSON
    let declaration: ResearchSoundDeclaration
    let ownership: ResearchSoundJSON
    let context: ResearchSoundCheckContext
    var requestSha256: String { FeedbackContract.sha(body) }
  }

  /// Exact reviewed source/runtime metadata; no runtime or model is loaded by the client.
  enum ResearchSoundContract {
    static let origin = "http://127.0.0.1:8793"
    static let kind = "engineering_sound_observation"
    static let purpose = "adult-development-preview"
    static let promptId = "r-middle-bread"
    static let claims: Set<String> = [
      "calibrationValidated", "pronunciationCorrectnessAssessed", "diagnosisProvided",
      "childAccuracyEstablished", "learnerFeedbackEligible", "clinicalUseEligible",
      "productionUseEligible",
    ]
    static let falseClaims = ResearchSoundJSON.object(
      Dictionary(uniqueKeysWithValues: claims.map { ($0, .bool(false)) }))
    static let sourcePins = ResearchSoundJSON.object([
      "contrastSpecSha256": .string(
        "3f49f4bee3664e42663af5b44bce86bab61d3593f63a72875973500b71849844"),
      "featureSourceSha256": .string(
        "af0ebd33f9a17ab6860e50314433e50691db7299d100874991885945cccb9057"),
      "modelFileSha256": .string(
        "3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120"),
      "promptSha256": .string("7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383"),
      "resourcePolicySha256": .string(
        "844dce27ead916bc51cf4909d70a33bec9e473ef174805d371196352f32085e4"),
      "runtimePinsSha256": .string(
        "908e50025533f9fa85bf1a4d3e89d30a9caa2b9f4883788b4188fedd5cb5751e"),
      "vocabularyFileSha256": .string(
        "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0"),
      "workerReceiptSha256": .string(
        "0c1762b9b6cab1499cb541663601bd261e03afba33e2e3453a6af35aebc50ca3"),
      "workerSourceSha256": .string(
        "e392c577e289dcb944551bc95c2ea1ad05a39d420f18b5a6eb3a08d668e7ba04"),
    ])
    static let contrast = ResearchSoundJSON.object([
      "checkpointId": .string("onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX"),
      "checkpointRevision": .string("c69750f5043e5e1f8a71ab95dd3b98338c280c92"),
      "configFileSha256": .string(
        "428b7781d080ad9463dca0e17e5066073cb691bfc14a178a85e76ac79c1f4a0f"),
      "contrastId": .string("bread-r-w-v1"),
      "contrastSpecSha256": .string(
        "3f49f4bee3664e42663af5b44bce86bab61d3593f63a72875973500b71849844"),
      "ctcSourceSha256": .string(
        "afaad92d487f2880e211c60232c5c9b94c9e05c40ce5c44d06a058159fab011b"),
      "manifestSourceSha256": .string(
        "1e07477079fa4425dacfbe271ba6c7ede472bf099d5f6914b8e4cc535053e148"),
      "modelFileSha256": .string(
        "3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120"),
      "phoneIndex": .integer(1),
      "posteriorSourceSha256": .string(
        "0c4672fb8d132437b3d120812a5785cd2a2858d365cbec016523c0b5f3a57087"),
      "preprocessorFileSha256": .string(
        "a2254a5b58f72cd4de3632f8eee64f3f098b7c1402128d2f419e7d00ae13e335"),
      "promptId": .string("r-middle-bread"),
      "promptSha256": .string("7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383"),
      "runtime": .string("@huggingface/transformers@4.2.0"),
      "targetPhone": .string("R"),
      "upstreamRevision": .string("ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4"),
      "vocabularyFileSha256": .string(
        "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0"),
      "wordIndex": .integer(0),
    ])
    static let wordBinding = ResearchSoundJSON.object([
      "pins": .object(FeedbackContract.corePins.mapValues { .string($0) }),
      "feedbackSourceSha256": .string(FeedbackContract.pins["feedbackSourceSha256"]!),
      "wrapperSourceSha256": .string(FeedbackContract.pins["wrapperSourceSha256"]!),
      "feedbackPolicySha256": .string(FeedbackContract.pins["feedbackPolicySha256"]!),
      "contentSha256": .string(FeedbackContract.pins["contentSha256"]!),
    ])
    static let binding = ResearchSoundJSON.object([
      "sources": sourcePins, "wordBinding": wordBinding,
    ])
    static let policy = ResearchSoundJSON.object([
      "id": .string("adult-development-sound-preview-v1"), "purpose": .string(purpose),
      "promptId": .string(promptId), "practiceMode": .string("free"),
      "minimumSamples": .integer(2400),
      "maximumSamples": .integer(64000), "maximumClaims": .integer(128),
      "maximumContexts": .integer(8),
      "encoderInput": .string("bytes-only"),
      "projection": .string("uncalibrated-model-preference-no-numeric-diagnostics"),
      "claimLimits": falseClaims,
    ])
    static let inconclusive: Set<String> = [
      "insufficient_frames", "zero_candidate_mass", "candidate_tie", "uncovered_mass_dominates",
      "greedy_tie", "decoded_context_outside_candidates", "decoded_path_disagreement",
    ]
    static let unavailable: Set<String> = [
      "busy", "cancelled", "timeout", "cleanup_unconfirmed", "source_binding_failed",
      "stale_ownership", "worker_unavailable", "invalid_evidence", "capture_already_checked",
      "attempt_already_checked", "attempt_limit", "context_limit", "processing_unavailable",
      "binding_mismatch", "invalid_frames", "frame_limit", "numerical_mass_invalid",
    ]
    static func need(_ condition: Bool) throws {
      guard condition else { throw RecordingFeedbackError.invalidResponse }
    }
    static func uuid(_ text: String) -> Bool {
      text.range(
        of: #"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$"#,
        options: .regularExpression) != nil
    }
    static func opaque(_ text: String) -> Bool {
      text.range(of: #"^[A-Za-z0-9_-]{1,64}$"#, options: .regularExpression) != nil
    }
    static func declaration(_ data: Data, service: ResearchFeedbackService = .currentUnified) throws
      -> ResearchSoundDeclaration
    {
      try service.requireConfigured()
      let binding = service.soundBinding
      try need(data.count <= 12000)
      let root = try ResearchSoundJSON.parse(data).fields([
        "schemaVersion", "kind", "purpose", "serverNonce", "csrfToken", "binding", "policy",
        "processingAvailable", "claimLimits",
      ])
      try need(
        root["schemaVersion"] == .integer(1) && root["kind"] == .string(kind)
          && root["purpose"] == .string(purpose))
      try need(
        root["binding"] == binding && root["policy"] == policy && root["claimLimits"] == falseClaims
      )
      guard let nonce = root["serverNonce"]?.text, let csrf = root["csrfToken"]?.text,
        case .bool(let available) = root["processingAvailable"]
      else { throw RecordingFeedbackError.invalidResponse }
      try need(uuid(nonce) && FeedbackContract.isHash(csrf))
      return .init(
        serverNonce: nonce, csrfToken: csrf, processingAvailable: available, service: service)
    }
    /// Preserve the single validated PCM payload; only normalize the WAV container.
    static func canonicalize(_ original: Data) throws -> Data {
      let pcm = try FeedbackPCM.measure(original)
      guard (2400...64000).contains(pcm.sampleCount) else {
        throw RecordingFeedbackError.invalidRecording
      }
      let bytes = Array(original)
      func u32(_ i: Int) -> Int { (0..<4).reduce(0) { $0 | Int(bytes[i + $1]) << ($1 * 8) } }
      var position = 12
      var payload = Data()
      while position + 8 <= bytes.count {
        let length = u32(position + 4)
        let start = position + 8
        if String(decoding: bytes[position..<position + 4], as: UTF8.self) == "data" {
          payload = Data(bytes[start..<start + length])
        }
        position = start + length + length % 2
      }
      guard payload.count == pcm.sampleCount * 2 else {
        throw RecordingFeedbackError.invalidRecording
      }
      var canonical = Data()
      func text(_ s: String) { canonical.append(contentsOf: s.utf8) }
      func word(_ value: Int, count: Int) {
        for offset in 0..<count { canonical.append(UInt8((value >> (offset * 8)) & 255)) }
      }
      text("RIFF")
      word(36 + payload.count, count: 4)
      text("WAVEfmt ")
      word(16, count: 4)
      word(1, count: 2)
      word(1, count: 2)
      word(16000, count: 4)
      word(32000, count: 4)
      word(2, count: 2)
      word(16, count: 2)
      text("data")
      word(payload.count, count: 4)
      canonical.append(payload)
      _ = try descriptor(canonical)
      return canonical
    }
    static func descriptor(_ data: Data) throws -> ResearchSoundJSON {
      let pcm = try FeedbackPCM.measure(data)
      // The reviewed byte worker accepts canonical PCM only, not arbitrary WAV chunks.
      let b = Array(data.prefix(44))
      func u16(_ i: Int) -> Int { Int(b[i]) | Int(b[i + 1]) << 8 }
      func u32(_ i: Int) -> Int { u16(i) | u16(i + 2) << 16 }
      guard data.count == 44 + pcm.sampleCount * 2, (2400...64000).contains(pcm.sampleCount),
        String(decoding: b[12..<16], as: UTF8.self) == "fmt ", u32(16) == 16,
        String(decoding: b[36..<40], as: UTF8.self) == "data", u32(40) == pcm.sampleCount * 2
      else { throw RecordingFeedbackError.invalidRecording }
      return .object([
        "sha256": .string(FeedbackContract.sha(data)), "bytes": .integer(data.count),
        "sampleCount": .integer(pcm.sampleCount), "sampleRateHertz": .integer(16000),
      ])
    }
    static func prepare(
      audio: Data, declaration: ResearchSoundDeclaration, context: ResearchSoundCheckContext,
      service: ResearchFeedbackService = .currentUnified
    ) throws -> ResearchSoundPrepared {
      try service.requireConfigured()
      try need(declaration.service == service)
      let binding = service.soundBinding
      try need(
        declaration.processingAvailable && uuid(context.attemptId) && uuid(declaration.serverNonce))
      try need(
        [context.sessionId, context.roundId, context.takeId, context.captureId].allSatisfy(opaque))
      try need(
        (1...2_147_483_647).contains(context.generation)
          && (0...2_147_483_647).contains(context.setupGeneration))
      let promptData = try FeedbackContract.encoder().encode(
        ResearchFeedbackCatalog.prompts[1].requestPrompt)
      let prompt = try ResearchSoundJSON.parse(promptData)
      try need(
        FeedbackContract.sha(promptData)
          == "7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383")
      let contextBody = ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "serverNonce": .string(declaration.serverNonce),
        "purpose": .string(purpose),
        "adultConfirmed": .bool(true), "optIn": .bool(true), "practiceMode": .string("free"),
        "selectedChildAge": .null,
        "setupGeneration": .integer(context.setupGeneration),
        "sessionId": .string(context.sessionId), "generation": .integer(context.generation),
        "promptId": .string(promptId), "promptSha256": .string(FeedbackContract.sha(promptData)),
        "binding": binding,
      ])
      let owner = ResearchSoundJSON.object([
        "sessionId": .string(context.sessionId), "generation": .integer(context.generation),
        "roundId": .string(context.roundId),
        "roundKind": .string("probe"), "itemId": .string(promptId),
        "takeId": .string(context.takeId), "captureId": .string(context.captureId),
        "contextSha256": .string(FeedbackContract.sha(try contextBody.canonical())),
      ])
      let audioDescriptor = try descriptor(audio)
      let body = try ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "attemptId": .string(context.attemptId),
        "purpose": .string(purpose), "adultConfirmed": .bool(true),
        "optIn": .bool(true), "practiceMode": .string("free"), "selectedChildAge": .null,
        "setupGeneration": .integer(context.setupGeneration),
        "serverNonce": .string(declaration.serverNonce), "promptId": .string(promptId),
        "prompt": prompt, "ownership": owner,
        "audio": audioDescriptor, "audioBase64": .string(audio.base64EncodedString()),
        "binding": binding,
      ]).canonical()
      try need(body.count <= 200000)
      var privateAudio = try audioDescriptor.fields([
        "sha256", "bytes", "sampleCount", "sampleRateHertz",
      ])
      privateAudio["file"] = .string("input.wav")
      let privateRequest = ResearchSoundJSON.object([
        "schemaVersion": .integer(1), "ownership": owner, "audio": .object(privateAudio),
        "contrast": contrast,
        "sourceSnapshotSha256": .string(
          "e392c577e289dcb944551bc95c2ea1ad05a39d420f18b5a6eb3a08d668e7ba04"),
      ])
      let expected = ResearchSoundJSON.object([
        "attemptId": .string(context.attemptId),
        "requestSha256": .string(FeedbackContract.sha(body)),
        "workerRequestSha256": .string(FeedbackContract.sha(try privateRequest.canonical())),
        "ownership": owner, "audio": audioDescriptor, "source": binding,
      ])
      return .init(
        body: body, privateRequest: privateRequest, expected: expected, declaration: declaration,
        ownership: owner, context: context)
    }
    static func observation(
      _ data: Data, expected: ResearchSoundJSON, service: ResearchFeedbackService = .currentUnified
    ) throws
      -> ResearchSoundObservation
    {
      try need(data.count <= 12000)
      try validateExpected(expected, service: service)
      let root = try ResearchSoundJSON.parse(data).fields([
        "schemaVersion", "kind", "purpose", "status", "reason", "modelPreference", "binding",
        "claimLimits",
      ])
      try need(
        root["schemaVersion"] == .integer(1) && root["kind"] == .string(kind)
          && root["purpose"] == .string(purpose) && root["binding"] == expected
          && root["claimLimits"] == falseClaims)
      guard let text = root["status"]?.text,
        let status = ResearchSoundObservation.Status(rawValue: text),
        let reason = root["reason"]?.text
      else { throw RecordingFeedbackError.invalidResponse }
      let preference = root["modelPreference"]?.text.flatMap(
        ResearchSoundObservation.Preference.init)
      switch status {
      case .observedModelPreference:
        try need(reason == "model_preferred_candidate" && preference != nil)
      case .inconclusive:
        try need(inconclusive.contains(reason) && root["modelPreference"] == .null)
      case .unavailable: try need(unavailable.contains(reason) && root["modelPreference"] == .null)
      case .unsupported:
        try need(reason == "unsupported_prompt" && root["modelPreference"] == .null)
      }
      return .init(status: status, reason: reason, preference: preference)
    }
    /// Reconstruct the exact compiled contract before observe/cancel can send any bytes.
    static func validatePrepared(
      _ prepared: ResearchSoundPrepared, service: ResearchFeedbackService
    ) throws {
      try service.requireConfigured()
      try need(prepared.declaration.service == service)
      try validateExpected(prepared.expected, service: service)
      // This is locally prepared request data (up to200k), not a transport response.
      // Rebuilding and byte equality below reject duplicate/extra/noncanonical fields.
      try need(prepared.body.count <= 200000)
      guard let fields = try? JSONSerialization.jsonObject(with: prepared.body) as? [String: Any],
        let text = fields["audioBase64"] as? String,
        let audio = Data(base64Encoded: text)
      else { throw RecordingFeedbackError.invalidResponse }
      let rebuilt = try prepare(
        audio: audio, declaration: prepared.declaration,
        context: prepared.context, service: service)
      try need(prepared == rebuilt)
    }
    static func validateExpected(
      _ value: ResearchSoundJSON, service: ResearchFeedbackService = .currentUnified
    ) throws {
      try service.requireConfigured()
      let binding = service.soundBinding
      let fields = try value.fields([
        "attemptId", "requestSha256", "workerRequestSha256", "ownership", "audio", "source",
      ])
      try need(fields["source"] == binding && uuid(fields["attemptId"]?.text ?? ""))
      for key in ["requestSha256", "workerRequestSha256"] {
        try need(FeedbackContract.isHash(fields[key]?.text ?? ""))
      }
      let owner = try fields["ownership"]!.fields([
        "sessionId", "generation", "roundId", "roundKind", "itemId", "takeId", "captureId",
        "contextSha256",
      ])
      for key in ["sessionId", "roundId", "takeId", "captureId"] {
        try need(opaque(owner[key]?.text ?? ""))
      }
      guard case .integer(let generation) = owner["generation"] else {
        throw RecordingFeedbackError.invalidResponse
      }
      try need(
        (1...2_147_483_647).contains(generation) && owner["roundKind"] == .string("probe")
          && owner["itemId"] == .string(promptId)
          && FeedbackContract.isHash(owner["contextSha256"]?.text ?? ""))
      let audio = try fields["audio"]!.fields(["sha256", "bytes", "sampleCount", "sampleRateHertz"])
      guard case .integer(let samples) = audio["sampleCount"] else {
        throw RecordingFeedbackError.invalidResponse
      }
      try need(
        (2400...64000).contains(samples) && audio["bytes"] == .integer(44 + samples * 2)
          && audio["sampleRateHertz"] == .integer(16000)
          && FeedbackContract.isHash(audio["sha256"]?.text ?? ""))
    }
  }
#endif
