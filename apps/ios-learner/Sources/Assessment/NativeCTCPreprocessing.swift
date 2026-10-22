import Foundation

/// The q8 processor's normalization of already-decoded Float32 samples.
/// PCM decoding, sample rate, and recording identity remain caller responsibilities.
public enum NativeCTCPreprocessing {
    public enum ValidationError: Error { case sampleCount, nonfiniteSample, nonfiniteResult }

    public static func normalize(
        _ samples: [Float],
        tick: () throws -> Void = {}
    ) throws -> [Float] {
        try tick()
        guard (1600...64000).contains(samples.count) else { throw ValidationError.sampleCount }
        var sum = 0.0
        for index in samples.indices {
            if index % 256 == 0 { try tick() }
            let sample = Double(samples[index])
            guard sample.isFinite else { throw ValidationError.nonfiniteSample }
            sum += sample
        }
        let count = Double(samples.count)
        let mean = sum / count
        try tick()
        var squaredDeviations = 0.0
        for index in samples.indices {
            if index % 256 == 0 { try tick() }
            let deviation = Double(samples[index]) - mean
            squaredDeviations += deviation * deviation
        }
        let variance = squaredDeviations / count
        let denominator = sqrt(variance + 1e-7)
        guard mean.isFinite, denominator.isFinite, denominator > 0 else {
            throw ValidationError.nonfiniteResult
        }
        try tick()
        var result = [Float](); result.reserveCapacity(samples.count)
        for index in samples.indices {
            if index % 256 == 0 { try tick() }
            let normalized = Float((Double(samples[index]) - mean) / denominator)
            guard normalized.isFinite else { throw ValidationError.nonfiniteResult }
            result.append(normalized)
        }
        try tick()
        return result
    }
}
