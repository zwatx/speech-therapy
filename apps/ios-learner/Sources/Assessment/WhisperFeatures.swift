import Accelerate
import Foundation

enum WhisperFeatureError: Error {
    case invalidSampleRate
    case invalidSampleCount
    case nonfiniteSamples
    case invalidMelShape
    case invalidMelCoefficient
    case invalidWindowShape
    case nonfiniteComputation
    case cancelled
}

/// A deliberately simple 400-point, unnormalized, real-input DFT.
/// No FFT factorization or Accelerate transform packing convention is assumed.
struct WhisperDFT400 {
    static let size = 400
    static let bins = 201
    private let cosine: [Double]
    private let negativeSine: [Double]

    init(isCancelled: () -> Bool = { false }) throws {
        var real = [Double](repeating: 0, count: Self.bins * Self.size)
        var imaginary = real
        for bin in 0..<Self.bins {
            if isCancelled() { throw WhisperFeatureError.cancelled }
            for index in 0..<Self.size {
                let phase = 2 * Double.pi * Double(bin * index) / Double(Self.size)
                real[bin * Self.size + index] = cos(phase)
                imaginary[bin * Self.size + index] = -sin(phase)
            }
        }
        cosine = real
        negativeSine = imaginary
    }

    func power(of window: [Double], isCancelled: () -> Bool = { false }) throws -> [Double] {
        guard window.count == Self.size else { throw WhisperFeatureError.invalidWindowShape }
        guard window.allSatisfy(\.isFinite) else { throw WhisperFeatureError.nonfiniteSamples }
        var powers = [Double](repeating: 0, count: Self.bins)
        try window.withUnsafeBufferPointer { input in
            try cosine.withUnsafeBufferPointer { realBasis in
                try negativeSine.withUnsafeBufferPointer { imaginaryBasis in
                    // Counts checked above; each basis slice contains exactly 400 elements.
                    for bin in 0..<Self.bins {
                        if isCancelled() { throw WhisperFeatureError.cancelled }
                        var real = 0.0
                        var imaginary = 0.0
                        vDSP_dotprD(input.baseAddress!, 1,
                                    realBasis.baseAddress! + bin * Self.size, 1,
                                    &real, vDSP_Length(Self.size))
                        vDSP_dotprD(input.baseAddress!, 1,
                                    imaginaryBasis.baseAddress! + bin * Self.size, 1,
                                    &imaginary, vDSP_Length(Self.size))
                        let power = real * real + imaginary * imaginary
                        guard power.isFinite else { throw WhisperFeatureError.nonfiniteComputation }
                        powers[bin] = power
                    }
                }
            }
        }
        return powers
    }
}

/// No capture, file access, logging, decoding, tokenization, model or word hints.
/// The caller must separately authenticate the supplied pinned mel coefficients.
struct WhisperFeatureExtractor {
    static let sampleRate = 16_000
    static let minimumSamples = 1_600
    static let maximumSamples = 64_000
    static let paddedSamples = 480_000
    static let hop = 160
    static let melCount = 80
    static let frameCount = 3_000
    static let featureCount = melCount * frameCount

    private let mel: [Double] // Pinned row-major [80, 201], cast to Float32 before Double.
    private let hann: [Double]
    private let dft: WhisperDFT400

    init(melCoefficients: [[Float]], isCancelled: () -> Bool = { false }) throws {
        guard melCoefficients.count == Self.melCount,
              melCoefficients.allSatisfy({ $0.count == WhisperDFT400.bins }) else {
            throw WhisperFeatureError.invalidMelShape
        }
        var flattened = [Double]()
        flattened.reserveCapacity(Self.melCount * WhisperDFT400.bins)
        for row in melCoefficients {
            if isCancelled() { throw WhisperFeatureError.cancelled }
            for value in row {
                guard value.isFinite, value >= 0 else { throw WhisperFeatureError.invalidMelCoefficient }
                flattened.append(Double(value))
            }
        }
        mel = flattened
        // torch.hann_window(400) uses periodic=True. Double arithmetic is deliberate;
        // agreement with the Float32 Torch implementation requires measured parity.
        hann = (0..<WhisperDFT400.size).map {
            0.5 - 0.5 * cos(2 * Double.pi * Double($0) / Double(WhisperDFT400.size))
        }
        dft = try WhisperDFT400(isCancelled: isCancelled)
    }

    /// Returns mel-major contiguous Float32 [1, 80, 3000].
    /// Cancellation is cooperative: checked during validation, every frame/bin,
    /// every mel row, and every 1024 values during final scaling.
    func extract(samples: [Float], sampleRate: Int,
                 isCancelled: () -> Bool = { false }) throws -> [Float] {
        if isCancelled() { throw WhisperFeatureError.cancelled }
        guard sampleRate == Self.sampleRate else { throw WhisperFeatureError.invalidSampleRate }
        guard (Self.minimumSamples...Self.maximumSamples).contains(samples.count) else {
            throw WhisperFeatureError.invalidSampleCount
        }
        for index in samples.indices {
            if index % 1024 == 0, isCancelled() { throw WhisperFeatureError.cancelled }
            guard samples[index].isFinite else { throw WhisperFeatureError.nonfiniteSamples }
        }
        var logs = [Float](repeating: -10, count: Self.featureCount)
        var globalMaximum: Float = -10
        var window = [Double](repeating: 0, count: WhisperDFT400.size)
        // center=True pads 200 reflected samples around the *480000-sample padded*
        // waveform, excluding the edge element. The source's final STFT frame
        // (index 3000) is removed, so only indices 0...2999 are evaluated here.
        for frame in 0..<Self.frameCount {
            if isCancelled() { throw WhisperFeatureError.cancelled }
            var exactlyZero = true
            for index in 0..<WhisperDFT400.size {
                let centered = frame * Self.hop - WhisperDFT400.size / 2 + index
                let reflected: Int
                if centered < 0 {
                    reflected = -centered
                } else if centered >= Self.paddedSamples {
                    reflected = 2 * (Self.paddedSamples - 1) - centered
                } else {
                    reflected = centered
                }
                let sample = reflected < samples.count ? Double(samples[reflected]) : 0
                window[index] = sample * hann[index]
                if window[index] != 0 { exactlyZero = false }
            }
            if exactlyZero { continue } // Exact zero power => floor => log10(1e-10) = -10.
            let power = try dft.power(of: window, isCancelled: isCancelled)
            try power.withUnsafeBufferPointer { powers in
                try mel.withUnsafeBufferPointer { coefficients in
                    for band in 0..<Self.melCount {
                        if isCancelled() { throw WhisperFeatureError.cancelled }
                        var energy = 0.0
                        vDSP_dotprD(powers.baseAddress!, 1,
                                    coefficients.baseAddress! + band * WhisperDFT400.bins, 1,
                                    &energy, vDSP_Length(WhisperDFT400.bins))
                        guard energy.isFinite, energy >= 0 else {
                            throw WhisperFeatureError.nonfiniteComputation
                        }
                        let value = Float(log10(max(energy, 1e-10)))
                        guard value.isFinite else { throw WhisperFeatureError.nonfiniteComputation }
                        logs[band * Self.frameCount + frame] = value
                        globalMaximum = max(globalMaximum, value)
                    }
                }
            }
        }
        // Global clamp must follow all frames, including analytically zero frames.
        let floor = globalMaximum - 8
        for index in logs.indices {
            if index % 1024 == 0, isCancelled() { throw WhisperFeatureError.cancelled }
            logs[index] = (max(logs[index], floor) + 4) / 4
            guard logs[index].isFinite else { throw WhisperFeatureError.nonfiniteComputation }
        }
        if isCancelled() { throw WhisperFeatureError.cancelled }
        return logs
    }
}
