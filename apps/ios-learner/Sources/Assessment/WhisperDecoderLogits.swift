import CoreML
import Foundation

/// Copies decoder scores without interpreting them. Selection still validates
/// every score, including suppressed values, after this copy finishes.
enum WhisperDecoderLogits {
    static func copy(_ scores: MLMultiArray,
                     checkCancellation: () throws -> Void) throws -> [Float] {
        guard scores.dataType == .float32,
              scores.shape.map(\.intValue) == [1, 51864],
              scores.count == 51864 else { throw WhisperProviderError.invalidTensor }
        var logits = [Float]()
        logits.reserveCapacity(51864)
        let copied = try scores.withUnsafeBufferPointer(ofType: Float.self) { buffer -> Bool in
            // Inspect layout inside the borrow: CoreML controls the scoped storage.
            guard scores.strides.map(\.intValue) == [51864, 1],
                  buffer.count >= 51864 else { return false }
            for index in 0..<51864 {
                if index % 1024 == 0 { try checkCancellation() }
                let value = buffer[index]
                // NSNumber indexing can change NaN payload/sign bits. Keep that
                // original conversion for NaNs; do not reject or replace a score.
                logits.append(value.isNaN
                    ? scores[[0, NSNumber(value: index)]].floatValue : value)
            }
            return true
        }
        guard !copied else { return logits }

        // Preserve logical indexed access for every other admitted layout.
        for index in 0..<51864 {
            if index % 1024 == 0 { try checkCancellation() }
            logits.append(scores[[0, NSNumber(value: index)]].floatValue)
        }
        return logits
    }
}
