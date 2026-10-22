import CryptoKit
import Foundation

enum WhisperTokenError: Error {
    case assetBinding
    case malformedAsset
    case invalidID
    case tokenLimit
    case unexpectedControl
    case suppressedToken
    case tokensAfterEOS
    case malformedUTF8
    case byteLimit
    case cancelled
}

/// Text is ephemeral and must never enter diagnostic receipts or logs.
enum WhisperDecodedResult {
    case completed(String)
    case incomplete
}

/// Decode only: no BPE encoder, file ownership, model, word hint or normalization.
struct WhisperByteDecoder {
    static let vocabularySize = 51_864
    static let maximumDecoderPrefix = 64
    static let maximumGeneratedDecisions = 63 // initial two controls + preceding decisions <=64
    static let maximumTextBytes = 16_384

    private enum Entry {
        case bytes([UInt8])
        case control
        case timestamp
    }
    private struct Tokenizer: Decodable {
        struct Model: Decodable { let type: String; let vocab: [String: Int] }
        struct Added: Decodable { let id: Int; let content: String; let special: Bool }
        struct Decoder: Decodable { let type: String }
        let model: Model
        let added_tokens: [Added]
        let decoder: Decoder
    }
    private struct Generation: Decodable {
        let is_multilingual: Bool
        let decoder_start_token_id: Int
        let eos_token_id: Int
        let no_timestamps_token_id: Int
        let forced_decoder_ids: [[Int]]
        let suppress_tokens: [Int]
        let begin_suppress_tokens: [Int]
        let return_timestamps: Bool
    }
    private struct ModelConfig: Decodable {
        let vocab_size: Int
        let decoder_start_token_id: Int
        let eos_token_id: Int
        let pad_token_id: Int
    }
    private struct SpecialMap: Decodable {
        struct Token: Decodable {
            let content: String
            private enum CodingKeys: String, CodingKey { case content }
            init(from decoder: Decoder) throws {
                if let string = try? decoder.singleValueContainer().decode(String.self) {
                    content = string
                } else {
                    content = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .content)
                }
            }
        }
        let additional_special_tokens: [String]
        let eos_token: Token
        let bos_token: Token
        let pad_token: Token
        let unk_token: Token
    }

    private let entries: [Entry]
    private let alwaysSuppressed: Set<Int32>
    private let firstSuppressed: Set<Int32>
    private let start: Int32
    private let noTimestamps: Int32
    private let eos: Int32

    /// Original public assets are passed as authenticated Data. No path/file access.
    init(tokenizerJSON: Data, generationConfigJSON: Data, modelConfigJSON: Data,
         specialTokensMapJSON: Data, isCancelled: () -> Bool = { false }) throws {
        if isCancelled() { throw WhisperTokenError.cancelled }
        try Self.bind(tokenizerJSON, bytes: 2_405_679,
                      sha: "5eb60cec1e77aeeb6869a2bb5a8e01a84c3fe5d072d75369343021fe6f5310d0")
        try Self.bind(generationConfigJSON, bytes: 1531,
                      sha: "c5750f05d94777579e00ce26ef65e5d87c108439f90e3ac519df2587b9d5d41f")
        try Self.bind(modelConfigJSON, bytes: 1937,
                      sha: "160c1df40a60d4ef5a6014d536fd845c33aabfd1f318458ac7f87cfe91ebbe76")
        try Self.bind(specialTokensMapJSON, bytes: 1830,
                      sha: "014f8f802366ed818919550be0ad9e35907327cb9e142e8aaa102420f460bda8")
        let tokenizer: Tokenizer
        let generation: Generation
        let config: ModelConfig
        let specialMap: SpecialMap
        do {
            tokenizer = try JSONDecoder().decode(Tokenizer.self, from: tokenizerJSON)
            generation = try JSONDecoder().decode(Generation.self, from: generationConfigJSON)
            config = try JSONDecoder().decode(ModelConfig.self, from: modelConfigJSON)
            specialMap = try JSONDecoder().decode(SpecialMap.self, from: specialTokensMapJSON)
        } catch { throw WhisperTokenError.malformedAsset }
        if isCancelled() { throw WhisperTokenError.cancelled }
        guard config.vocab_size == Self.vocabularySize, tokenizer.model.type == "BPE",
              tokenizer.decoder.type == "ByteLevel", tokenizer.model.vocab.count == 50_257,
              tokenizer.added_tokens.count == 1608, !generation.is_multilingual,
              !generation.return_timestamps else { throw WhisperTokenError.malformedAsset }

        var contentByID = [String?](repeating: nil, count: Self.vocabularySize)
        var addedByID = [Int: Tokenizer.Added]()
        var idByContent = tokenizer.model.vocab
        for (content, id) in tokenizer.model.vocab {
            if isCancelled() { throw WhisperTokenError.cancelled }
            guard (0..<Self.vocabularySize).contains(id), contentByID[id] == nil else {
                throw WhisperTokenError.malformedAsset
            }
            contentByID[id] = content
        }
        for added in tokenizer.added_tokens {
            if isCancelled() { throw WhisperTokenError.cancelled }
            guard (0..<Self.vocabularySize).contains(added.id), addedByID[added.id] == nil,
                  contentByID[added.id] == nil || contentByID[added.id] == added.content,
                  idByContent[added.content] == nil || idByContent[added.content] == added.id else {
                throw WhisperTokenError.malformedAsset
            }
            contentByID[added.id] = added.content
            idByContent[added.content] = added.id
            addedByID[added.id] = added
        }
        guard let startID = idByContent["<|startoftranscript|>"],
              let noTimestampID = idByContent["<|notimestamps|>"],
              let eosID = idByContent["<|endoftext|>"],
              let spaceID = idByContent["Ġ"],
              generation.decoder_start_token_id == startID,
              generation.eos_token_id == eosID,
              generation.no_timestamps_token_id == noTimestampID,
              generation.forced_decoder_ids == [[1, noTimestampID]],
              config.decoder_start_token_id == startID, config.eos_token_id == eosID,
              config.pad_token_id == eosID,
              Set(generation.begin_suppress_tokens) == Set([spaceID, eosID]),
              generation.suppress_tokens.count == 90,
              generation.suppress_tokens.allSatisfy({ (0..<Self.vocabularySize).contains($0) }) else {
            throw WhisperTokenError.malformedAsset
        }
        let specialContents = Set(tokenizer.added_tokens.filter(\.special).map(\.content))
        guard specialContents.count == 107,
              Set(specialMap.additional_special_tokens + [specialMap.eos_token.content]) == specialContents,
              specialMap.eos_token.content == "<|endoftext|>", specialMap.bos_token.content == specialMap.eos_token.content,
              specialMap.pad_token.content == specialMap.eos_token.content, specialMap.unk_token.content == specialMap.eos_token.content,
              addedByID[startID]?.special == true, addedByID[noTimestampID]?.special == true,
              addedByID[eosID]?.special == true else { throw WhisperTokenError.malformedAsset }

        let byteMap = Self.inverseByteAlphabet()
        var decoded = [Entry]()
        decoded.reserveCapacity(Self.vocabularySize)
        var timestampCount = 0
        for id in 0..<Self.vocabularySize {
            if isCancelled() { throw WhisperTokenError.cancelled }
            guard let content = contentByID[id] else { throw WhisperTokenError.malformedAsset }
            if let added = addedByID[id] {
                if added.special {
                    decoded.append(.control)
                } else {
                    // Pinned JSON contains only timestamps among non-special added tokens.
                    guard content.range(of: "^<\\|[0-9]+\\.[0-9]{2}\\|>$", options: .regularExpression) != nil else {
                        throw WhisperTokenError.malformedAsset
                    }
                    timestampCount += 1
                    decoded.append(.timestamp)
                }
            } else {
                var bytes = [UInt8]()
                for scalar in content.unicodeScalars {
                    guard let byte = byteMap[scalar.value] else { throw WhisperTokenError.malformedAsset }
                    bytes.append(byte)
                }
                guard !bytes.isEmpty, bytes.count <= 256 else { throw WhisperTokenError.malformedAsset }
                decoded.append(.bytes(bytes))
            }
        }
        guard timestampCount == 1501 else { throw WhisperTokenError.malformedAsset }
        entries = decoded
        start = Int32(startID)
        noTimestamps = Int32(noTimestampID)
        eos = Int32(eosID)
        alwaysSuppressed = Set(generation.suppress_tokens.map(Int32.init))
        firstSuppressed = Set(generation.begin_suppress_tokens.map(Int32.init))
    }

    /// Canonical cached English-only start + no-timestamps. No language/task hints.
    func initialPrefix(isCancelled: () -> Bool = { false }) throws -> [Int32] {
        if isCancelled() { throw WhisperTokenError.cancelled }
        return [start, noTimestamps]
    }

    /// For a future greedy selector: apply suppression *before* argmax. This is
    /// stricter than HF's 90-entry suppression by also excluding every generated
    /// control except EOS and all timestamps. Raw argmax is not the declared policy.
    func isAllowedNext(_ id: Int32, generatedCount: Int,
                       isCancelled: () -> Bool = { false }) throws -> Bool {
        if isCancelled() { throw WhisperTokenError.cancelled }
        guard (0..<Self.maximumGeneratedDecisions).contains(generatedCount) else {
            throw WhisperTokenError.tokenLimit
        }
        try validateID(id)
        if alwaysSuppressed.contains(id) || (generatedCount == 0 && firstSuppressed.contains(id)) { return false }
        if id == eos { return true }
        switch entries[Int(id)] {
        case .bytes: return true
        case .control, .timestamp: return false
        }
    }

    /// Accepts generated decisions only (not initial prefix). A valid completion
    /// needs EOS as its final decision. No non-EOS prefix is exposed as final text.
    func decodeGenerated(_ ids: [Int32], isCancelled: () -> Bool = { false }) throws -> WhisperDecodedResult {
        if isCancelled() { throw WhisperTokenError.cancelled }
        guard ids.count <= Self.maximumGeneratedDecisions else { throw WhisperTokenError.tokenLimit }
        var bytes = [UInt8]()
        var ended = false
        for (index, id) in ids.enumerated() {
            if isCancelled() { throw WhisperTokenError.cancelled }
            try validateID(id)
            if ended { throw WhisperTokenError.tokensAfterEOS }
            if id == eos {
                guard index != 0 else { throw WhisperTokenError.suppressedToken }
                ended = true
                continue // EOS is omitted; initial control tokens are never in this API's input.
            }
            switch entries[Int(id)] {
            case .control, .timestamp: throw WhisperTokenError.unexpectedControl
            case .bytes(let piece):
                guard try isAllowedNext(id, generatedCount: index, isCancelled: isCancelled) else {
                    throw WhisperTokenError.suppressedToken
                }
                guard bytes.count <= Self.maximumTextBytes - piece.count else { throw WhisperTokenError.byteLimit }
                bytes.append(contentsOf: piece)
            }
        }
        if isCancelled() { throw WhisperTokenError.cancelled }
        guard ended else { return .incomplete }
        // HF defaults to replacement for malformed byte sequences. The native
        // candidate deliberately abstains instead; never invent replacement text.
        guard let text = String(bytes: bytes, encoding: .utf8) else { throw WhisperTokenError.malformedUTF8 }
        return .completed(text) // Exact whitespace; no clean-up, casefold, spelling or language normalization.
    }

    private func validateID(_ id: Int32) throws {
        guard id >= 0, Int(id) < Self.vocabularySize else { throw WhisperTokenError.invalidID }
    }

    private static func bind(_ data: Data, bytes: Int, sha: String) throws {
        guard data.count == bytes,
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == sha else {
            throw WhisperTokenError.assetBinding
        }
    }

    /// Exact GPT-2/Whisper bytes_to_unicode inverse; values are UTF8 bytes, not model IDs.
    private static func inverseByteAlphabet() -> [UInt32: UInt8] {
        let visible = Array(33...126) + Array(161...172) + Array(174...255)
        let visibleSet = Set(visible)
        var map = [UInt32: UInt8]()
        for value in visible { map[UInt32(value)] = UInt8(value) }
        var extra = 0
        for value in 0...255 where !visibleSet.contains(value) {
            map[UInt32(256 + extra)] = UInt8(value)
            extra += 1
        }
        return map
    }
}
