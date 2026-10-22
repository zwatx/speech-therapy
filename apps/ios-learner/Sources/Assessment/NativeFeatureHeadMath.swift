import Foundation

// The retained bundle's feature transforms and equal mixture, without eligibility policy.
enum NativeFeatureHeadMath {
    enum Failure: Error { case constants, features, logits }
    struct Constants {
        let center: [Double]; let basis: [Double]
        let scalarMean: [Float]; let scalarStd: [Float]
        let compactMean: [Float]; let compactStd: [Float]

        func validate(tick: () throws -> Void) throws {
            try tick()
            guard center.count == 1024, basis.count == 1024 * 16,
                  scalarMean.count == 13, scalarStd.count == 13,
                  compactMean.count == 29, compactStd.count == 29,
                  center.allSatisfy(\.isFinite), basis.allSatisfy(\.isFinite),
                  scalarMean.allSatisfy(\.isFinite), compactMean.allSatisfy(\.isFinite),
                  scalarStd.allSatisfy({ $0.isFinite && $0 > 0 }),
                  compactStd.allSatisfy({ $0.isFinite && $0 > 0 }) else { throw Failure.constants }
            // Same saved-basis invariant as the actual bundle loader; never refit it.
            for left in 0..<16 {
                for right in 0..<16 {
                    try tick(); var dot = 0.0
                    for row in 0..<1024 { dot += basis[row * 16 + left] * basis[row * 16 + right] }
                    guard abs(dot - (left == right ? 1 : 0)) <= 1e-8 else { throw Failure.constants }
                }
            }
            try tick()
        }
    }
    struct Transformed {
        let projectionDouble: [Double]
        let projection: [Float]
        let scalars: [Float]
        let compact: [Float]
        let normalizedScalar: [Float]
        let normalizedCompact: [Float]
    }
    static func transform(_ features: [Float], constants: Constants,
                          tick: () throws -> Void) throws -> Transformed {
        try tick()
        guard features.count == 1037, features.allSatisfy(\.isFinite),
              constants.center.count == 1024, constants.basis.count == 16384,
              constants.scalarMean.count == 13, constants.scalarStd.count == 13,
              constants.compactMean.count == 29, constants.compactStd.count == 29 else { throw Failure.features }
        var projectionDouble = [Double](repeating:0,count:16)
        for column in 0..<16 {
            try tick(); var sum = 0.0
            for row in 0..<1024 {
                if row % 256 == 0 { try tick() }
                let centered = Double(features[row]) - constants.center[row]
                sum += centered * constants.basis[row * 16 + column]
            }
            guard sum.isFinite else { throw Failure.features }
            projectionDouble[column] = sum
        }
        let projection = projectionDouble.map(Float.init)
        let scalars = Array(features[1024..<1037]); let compact = projection + scalars
        func normalize(_ values: [Float], _ mean: [Float], _ std: [Float]) throws -> [Float] {
            var result = [Float](); result.reserveCapacity(values.count)
            for index in values.indices {
                try tick()
                guard mean[index].isFinite, std[index].isFinite, std[index] > 0 else { throw Failure.constants }
                let centered: Float = values[index] - mean[index]
                let normalized: Float = centered / std[index]
                guard normalized.isFinite else { throw Failure.features }
                result.append(normalized)
            }
            return result
        }
        guard projection.allSatisfy(\.isFinite) else { throw Failure.features }
        let normalizedScalar = try normalize(scalars,constants.scalarMean,constants.scalarStd)
        let normalizedCompact = try normalize(compact,constants.compactMean,constants.compactStd)
        try tick()
        return Transformed(projectionDouble:projectionDouble,projection:projection,scalars:scalars,
            compact:compact,normalizedScalar:normalizedScalar,normalizedCompact:normalizedCompact)
    }
    struct Mixture {
        let scalarLogProb: [Double]; let compactLogProb: [Double]
        let mixtureLogProb: [Double]; let probabilities: [Double]
    }
    static func mixture(scalar: [Float], compact: [Float],
                        tick: () throws -> Void) throws -> Mixture {
        try tick()
        func logSoftmax(_ values: [Float]) throws -> [Double] {
            guard values.count == 3, values.allSatisfy(\.isFinite) else { throw Failure.logits }
            let doubles = values.map(Double.init); let maximum = doubles.max()!
            var sum = 0.0
            for value in doubles { sum += exp(value - maximum) }
            let normalizer = maximum + log(sum)
            let result = doubles.map { $0 - normalizer }
            guard result.allSatisfy(\.isFinite) else { throw Failure.logits }
            return result
        }
        let left = try logSoftmax(scalar); let right = try logSoftmax(compact)
        var mixed = [Double](); var probabilities = [Double]()
        for index in 0..<3 {
            try tick()
            let maximum = max(left[index],right[index])
            let value = maximum + log1p(exp(-abs(left[index] - right[index]))) - log(2.0)
            let probability = exp(value)
            guard value.isFinite, probability.isFinite, probability >= 0, probability <= 1 else { throw Failure.logits }
            mixed.append(value); probabilities.append(probability)
        }
        guard abs(probabilities.reduce(0,+) - 1) <= 1e-12 else { throw Failure.logits }
        try tick()
        return Mixture(scalarLogProb:left,compactLogProb:right,mixtureLogProb:mixed,probabilities:probabilities)
    }
}
