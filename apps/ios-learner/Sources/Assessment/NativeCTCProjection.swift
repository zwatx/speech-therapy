import Foundation

// Pure public-head arithmetic. This type carries no decoding or eligibility policy.
struct NativeCTCProjection: Sendable {
    static let hiddenWidth = 1024
    static let vocabularySize = 392
    static let maximumFrameCount = 199

    enum Failure: Error { case head, hidden, logits, logProbabilities }

    private let weight: [Float]
    private let bias: [Float]

    // Weight is vocabulary-major FP32[392,1024]; bias is FP32[392].
    init(weight: [Float], bias: [Float], tick: () throws -> Void) throws {
        try tick()
        guard weight.count == Self.vocabularySize * Self.hiddenWidth,
              bias.count == Self.vocabularySize else { throw Failure.head }
        for index in weight.indices {
            if index % 256 == 0 { try tick() }
            guard weight[index].isFinite else { throw Failure.head }
        }
        for index in bias.indices {
            if index % 256 == 0 { try tick() }
            guard bias[index].isFinite else { throw Failure.head }
        }
        try tick()
        self.weight = weight
        self.bias = bias
    }

    struct Output: Sendable {
        let frameCount: Int
        // Both arrays are row-major FP32[frameCount,392], including blank ID 0.
        let logits: [Float]
        let logProbabilities: [Float]
    }

    // All supplied rows survive, including padded query rows. The caller owns valid F.
    func project(hidden: [Float], frameCount: Int,
                 tick: () throws -> Void) throws -> Output {
        try tick()
        guard (1...Self.maximumFrameCount).contains(frameCount),
              hidden.count == frameCount * Self.hiddenWidth else { throw Failure.hidden }
        for index in hidden.indices {
            if index % 256 == 0 { try tick() }
            guard hidden[index].isFinite else { throw Failure.hidden }
        }
        let count = frameCount * Self.vocabularySize
        var logits = [Float](repeating: 0, count: count)
        var logProbabilities = [Float](repeating: 0, count: count)
        for frame in 0..<frameCount {
            try tick()
            let rowStart = frame * Self.vocabularySize
            for vocabulary in 0..<Self.vocabularySize {
                try tick()
                // Convert each exact FP32 operand to Double, multiply and accumulate
                // in channel order with the bias, then round the completed logit once.
                var sum = Double(bias[vocabulary])
                for channel in 0..<Self.hiddenWidth {
                    if channel % 256 == 0 { try tick() }
                    sum += Double(hidden[frame * Self.hiddenWidth + channel])
                        * Double(weight[vocabulary * Self.hiddenWidth + channel])
                }
                let value = Float(sum)
                guard sum.isFinite, value.isFinite else { throw Failure.logits }
                logits[rowStart + vocabulary] = value
            }
            var maximum = -Double.infinity
            for vocabulary in 0..<Self.vocabularySize {
                if vocabulary % 256 == 0 { try tick() }
                maximum = max(maximum, Double(logits[rowStart + vocabulary]))
            }
            var shiftedSum = 0.0
            for vocabulary in 0..<Self.vocabularySize {
                if vocabulary % 256 == 0 { try tick() }
                shiftedSum += exp(Double(logits[rowStart + vocabulary]) - maximum)
            }
            let logShiftedSum = log(shiftedSum)
            guard logShiftedSum.isFinite else { throw Failure.logProbabilities }
            for vocabulary in 0..<Self.vocabularySize {
                if vocabulary % 256 == 0 { try tick() }
                // Preserve the shift even when maximum is a huge common offset.
                let value = Float((Double(logits[rowStart + vocabulary]) - maximum)
                    - logShiftedSum)
                guard value.isFinite else { throw Failure.logProbabilities }
                logProbabilities[rowStart + vocabulary] = value
            }
        }
        try tick()
        return Output(frameCount: frameCount, logits: logits, logProbabilities: logProbabilities)
    }
}
