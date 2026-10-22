import Foundation

/// Deterministic research-feature math. Canonical tokens are supplied expectations,
/// and forced state occupancy is not an observation of a produced phone.
/// This kernel performs no inference, I/O, eligibility decision or UI action.
enum CanonicalCTCFeatures {
    static let vocabularySize = 392
    static let hiddenWidth = 1024
    static let maximumFrames = 199 // Current app's four-second capture boundary.
    static let scalarNames = [
        "targetMeanLogPosterior", "targetMeanPosterior", "targetMaxPosterior",
        "meanLogMarginVsBestOtherPhone", "meanLogFractionOfNonblankMass", "targetArgmaxFraction",
        "meanBlankPosterior", "meanSpecialPosterior", "meanFullVocabularyEntropy",
        "ctcTargetOccupancySeconds", "occupiedFrames", "utteranceViterbiLogProbabilityPerFrame",
        "greedyCanonicalTokenErrorRate"
    ]
    enum Failure: String, Error { case invalidMapping, invalidInput, invalidTargets, impossibleAlignment }
    struct Target: Equatable {
        let id: String
        let canonicalIndex: Int
        // Inventory index only:24 canonical IDs exist, but current heads support23.
        // This metadata does not admit a phone to a head or establish ID/phone correspondence.
        let modelTargetId: Int
    }
    struct Mapping: Equatable {
        let tokens: [String]
        let tokenIDs: [Int]
        let flags: [String]
    }
    struct Utterance {
        let viterbiLogProbabilityPerFrame: Double
        let greedyCanonicalTokenErrorRate: Double
        let greedyExactCanonicalSequence: Bool
        let canonicalTokens: Int
        let greedyTokens: Int
    }
    struct TargetResult {
        let target: Target
        let tokenID: Int
        let interval: Range<Int>
        let poolingWindow: Range<Int>
        let frameCenters: [Double]
        let scalars: [Double]
        let diagnosticFlags: [String]
        let pooled: [Float]
        let features: [Float] // Pooled1024 followed by the13 scalar casts.
    }
    struct Result {
        let statePath: [Int]
        let viterbiScore: Double
        let greedyTokens: [Int]
        let utterance: Utterance
        let targets: [TargetResult]
        let globalPooled: [Float]
    }

    // Exact arpabet-espeak-provisional-v1 recipe, not inferred pronunciation variants.
    static let consonants = ["B":"b", "P":"p", "M":"m", "T":"t", "D":"d", "N":"n", "K":"k", "G":"ɡ",
        "F":"f", "V":"v", "S":"s", "Z":"z", "SH":"ʃ", "CH":"tʃ", "JH":"dʒ", "L":"l", "R":"ɹ",
        "W":"w", "Y":"j", "HH":"h", "TH":"θ", "DH":"ð", "NG":"ŋ", "ZH":"ʒ"]
    static let vowels = ["AA":"ɑː", "AE":"æ", "AH":"ʌ", "AO":"ɔː", "AW":"aʊ", "AY":"aɪ", "EH":"ɛ",
        "ER":"ɚ", "EY":"eɪ", "IH":"ɪ", "IY":"iː", "OW":"oʊ", "OY":"ɔɪ", "UH":"ʊ", "UW":"uː"]
    static let stressOverrides = ["AH0":"ə"]

    // Vocabulary keys are exact UTF-8 bytes: Swift.String equality merges some distinct IPA tokens.
    static func mapCanonicalPhones(_ phones: [String], vocabulary: [Data: Int],
                                   tick: () throws -> Void = {}) throws -> Mapping {
        try tick()
        guard !phones.isEmpty, phones.count <= 512, vocabulary.count == vocabularySize,
              Set(vocabulary.values) == Set(0..<vocabularySize), !vocabulary.keys.contains(Data()),
              vocabulary[Data("<pad>".utf8)] == 0, vocabulary[Data("<s>".utf8)] == 1,
              vocabulary[Data("</s>".utf8)] == 2, vocabulary[Data("<unk>".utf8)] == 3 else { throw Failure.invalidMapping }
        var tokens = [String](); var ids = [Int](); var flags = Set<String>(); var previousBase: String?
        for phone in phones {
            try tick()
            let bytes = Array(phone.utf8)
            guard !bytes.isEmpty, bytes.count <= 64 else { throw Failure.invalidMapping }
            let stressed = (48...50).contains(bytes[bytes.count - 1])
            let letters = stressed ? bytes.dropLast() : bytes[...]
            guard !letters.isEmpty, letters.allSatisfy({ (65...90).contains($0) }) else { throw Failure.invalidMapping }
            let base = String(decoding: letters, as: UTF8.self)
            guard let token = stressOverrides[phone] ?? consonants[base] ?? vowels[base],
                  let id = vocabulary[Data(token.utf8)], id > 3 else { throw Failure.invalidMapping }
            tokens.append(token); ids.append(id)
            if vowels[base] != nil { flags.insert("provisional-vowel-length-dialect-stress-mapping") }
            if base == "T" || base == "D" { flags.insert("canonical-t-d-does-not-model-flap-variants") }
            if base == "L" { flags.insert("canonical-l-does-not-model-dark-or-syllabic-variants") }
            if base == "ER" { flags.insert("er-stress-collapsed-to-rhotic-schwa") }
            if base == "R", let previousBase, vowels[previousBase] != nil {
                flags.insert("postvocalic-r-may-compete-with-merged-rhotic-tokens")
            }
            previousBase = base
        }
        try tick(); return Mapping(tokens: tokens, tokenIDs: ids, flags: flags.sorted())
    }

    /// Inputs are owned row-major FP32 arrays on the same valid frame grid.
    /// The caller separately admits checkpoint/vocabulary identity and canonical prompt policy.
    /// `tick` may throw cancellation/deadline errors; they propagate without translation.
    static func extract(logPosteriors: [Float], frames: Int, hidden: [Float],
                        targetTokenIDs: [Int], targets: [Target],
                        tick: () throws -> Void = {}) throws -> Result {
        try tick()
        guard frames > 0, frames <= maximumFrames,
              logPosteriors.count == frames * vocabularySize, hidden.count == frames * hiddenWidth else {
            throw Failure.invalidInput
        }
        guard !targetTokenIDs.isEmpty, targetTokenIDs.count <= 512,
              targetTokenIDs.allSatisfy({ (4..<vocabularySize).contains($0) }),
              !targets.isEmpty, targets.count <= 23,
              Set(targets.map(\.canonicalIndex)).count == targets.count,
              Set(targets.map(\.id)).count == targets.count,
              targets.allSatisfy({ !$0.id.isEmpty && $0.id.count <= 128
                  && !$0.id.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) })
                  && targetTokenIDs.indices.contains($0.canonicalIndex) && (0..<24).contains($0.modelTargetId) }) else {
            throw Failure.invalidTargets
        }
        var minimumFrames = targetTokenIDs.count
        for index in 1..<targetTokenIDs.count {
            if targetTokenIDs[index] == targetTokenIDs[index - 1] { minimumFrames += 1 }
        }
        guard minimumFrames <= frames else { throw Failure.impossibleAlignment }
        // Promote the serialized FP32 matrix once; never renormalize it.
        var values = [Double](); values.reserveCapacity(logPosteriors.count)
        var winners = [Int](); winners.reserveCapacity(frames)
        for frame in 0..<frames {
            try tick(); var sum = 0.0; var best = 0; var maximum = -Double.infinity
            for token in 0..<vocabularySize {
                let value = Double(logPosteriors[frame * vocabularySize + token])
                guard value.isFinite, value <= 1e-6 else { throw Failure.invalidInput }
                values.append(value); sum += exp(value)
                if value > maximum { maximum = value; best = token }
            }
            guard abs(sum - 1) <= 3e-5 else { throw Failure.invalidInput }
            winners.append(best) // Strict > preserves the first/lowest-ID maximum.
        }
        for index in hidden.indices {
            if index % hiddenWidth == 0 { try tick() }
            guard hidden[index].isFinite else { throw Failure.invalidInput }
        }
        try tick()
        let alignment = try viterbi(values, frames: frames, target: targetTokenIDs, tick: tick)
        var greedy = [Int](); var previousToken: Int?
        for token in winners {
            if token != previousToken && token != 0 { greedy.append(token) }
            previousToken = token // Special IDs1–3 remain in the greedy stream.
        }
        let distance = try editDistance(targetTokenIDs, greedy, tick: tick)
        let utterance = Utterance(viterbiLogProbabilityPerFrame: alignment.score / Double(frames),
            greedyCanonicalTokenErrorRate: Double(distance) / Double(targetTokenIDs.count),
            greedyExactCanonicalSequence: greedy == targetTokenIDs,
            canonicalTokens: targetTokenIDs.count, greedyTokens: greedy.count)
        var results = [TargetResult]()
        for target in targets {
            try tick()
            let state = 2 * target.canonicalIndex + 1
            let occupied = alignment.path.indices.filter { alignment.path[$0] == state }
            guard let start = occupied.first, let last = occupied.last,
                  occupied == Array(start...last) else { throw Failure.impossibleAlignment }
            let end = last + 1; let token = targetTokenIDs[target.canonicalIndex]
            var sums = [Double](repeating: 0, count: 9); var maximumPosterior = 0.0
            for frame in start..<end {
                try tick(); let offset = frame * vocabularySize
                let expected = values[offset + token]; let expectedProbability = exp(expected)
                var competitor = -Double.infinity; var nonblankMaximum = -Double.infinity
                var special = 0.0; var entropy = 0.0
                for column in 0..<vocabularySize {
                    let value = values[offset + column]; let probability = exp(value)
                    entropy -= probability * value
                    if column > 0 { nonblankMaximum = max(nonblankMaximum, value) }
                    if column >= 4 && column != token { competitor = max(competitor, value) }
                    if (1..<4).contains(column) { special += probability }
                }
                var nonblankSum = 0.0
                for column in 1..<vocabularySize { nonblankSum += exp(values[offset + column] - nonblankMaximum) }
                let logNonblank = nonblankMaximum + log(nonblankSum)
                sums[0] += expected; sums[1] += expectedProbability; maximumPosterior = max(maximumPosterior, expectedProbability)
                sums[3] += expected - competitor; sums[4] += expected - logNonblank
                sums[5] += winners[frame] == token ? 1 : 0
                sums[6] += exp(values[offset]); sums[7] += special; sums[8] += entropy
            }
            let count = Double(end - start)
            var scalars = sums.map { $0 / count }; scalars[2] = maximumPosterior
            scalars += [Double(end - start) * 0.02, count,
                utterance.viterbiLogProbabilityPerFrame, utterance.greedyCanonicalTokenErrorRate]
            guard scalars.count == scalarNames.count, scalars.allSatisfy(\.isFinite) else { throw Failure.invalidInput }
            let scalarFloats = scalars.map(Float.init)
            guard scalarFloats.allSatisfy(\.isFinite) else { throw Failure.invalidInput }
            let window = max(0, start - 2)..<min(frames, end + 2)
            let pooled = try pool(hidden, window: window, tick: tick)
            var flags = ["unverified-forced-canonical-location"]
            if end - start < 2 { flags.append("fewer-than-two-target-state-frames") }
            if scalars[5] < 0.5 { flags.append("target-is-not-argmax-on-most-occupied-frames") }
            results.append(TargetResult(target: target, tokenID: token, interval: start..<end,
                poolingWindow: window, frameCenters: [(Double(start) * 320 + 199.5) / 16000,
                    (Double(end - 1) * 320 + 199.5) / 16000], scalars: scalars,
                diagnosticFlags: flags, pooled: pooled, features: pooled + scalarFloats))
        }
        let global = try pool(hidden, window: 0..<frames, tick: tick)
        try tick()
        return Result(statePath: alignment.path, viterbiScore: alignment.score,
            greedyTokens: greedy, utterance: utterance, targets: results, globalPooled: global)
    }

    private static func viterbi(_ values: [Double], frames: Int, target: [Int],
                                tick: () throws -> Void) throws -> (path: [Int], score: Double) {
        var states = [0]
        for token in target { states += [token,0] }
        let count = states.count
        var previous = [Double](repeating: -.infinity, count: count)
        previous[0] = values[0]; previous[1] = values[target[0]]
        var back = [Int32](repeating: -1, count: frames * count)
        for frame in 1..<frames {
            try tick(); var current = [Double](repeating: -.infinity, count: count)
            for state in 0..<count {
                if state % 64 == 0 { try tick() }
                var winner = state // Ties: stay, then advance1, then legal advance2.
                if state > 0 && previous[state - 1] > previous[winner] { winner = state - 1 }
                if state >= 2 && states[state] != 0 && states[state] != states[state - 2]
                    && previous[state - 2] > previous[winner] { winner = state - 2 }
                if previous[winner].isFinite {
                    current[state] = previous[winner] + values[frame * vocabularySize + states[state]]
                    back[frame * count + state] = Int32(winner)
                }
            }
            previous = current
        }
        var state = previous[count - 2] >= previous[count - 1] ? count - 2 : count - 1
        let score = previous[state]
        guard score.isFinite else { throw Failure.impossibleAlignment }
        var path = [Int](repeating: 0, count: frames); path[frames - 1] = state
        if frames > 1 {
            for frame in stride(from: frames - 1, through: 1, by: -1) {
                try tick(); state = Int(back[frame * count + state])
                guard state >= 0 && state < count else { throw Failure.impossibleAlignment }
                path[frame - 1] = state
            }
        }
        return (path, score)
    }
    private static func editDistance(_ left: [Int], _ right: [Int], tick: () throws -> Void) throws -> Int {
        var previous = Array(0...right.count)
        for (index, a) in left.enumerated() {
            try tick(); var current = [index + 1]
            for (column, b) in right.enumerated() {
                current.append(min(current[column] + 1, previous[column + 1] + 1, previous[column] + (a == b ? 0 : 1)))
            }
            previous = current
        }
        return previous[right.count]
    }
    private static func pool(_ hidden: [Float], window: Range<Int>, tick: () throws -> Void) throws -> [Float] {
        var sum = [Double](repeating: 0, count: hiddenWidth)
        for frame in window {
            try tick()
            for column in 0..<hiddenWidth { sum[column] += Double(hidden[frame * hiddenWidth + column]) }
        }
        let result = sum.map { Float($0 / Double(window.count)) }
        guard result.allSatisfy(\.isFinite) else { throw Failure.invalidInput }; return result
    }
}
