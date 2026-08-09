import CoreML
import Foundation

/// Checks every logical encoder value without boxing contiguous Float storage.
/// The caller retains cancellation and runtime ownership; no tensor escapes here.
enum WhisperEncoderStateValidation {
    static func validate(_ states: MLMultiArray,
                         checkCancellation: () throws -> Void) throws {
        guard states.dataType == .float32,
              states.shape.map(\.intValue) == [1, 1500, 512],
              states.count == 768000 else { throw WhisperProviderError.invalidTensor }

        let scanned = try states.withUnsafeBufferPointer(ofType: Float.self) { buffer -> Bool in
            // Inspect the layout after acquiring the scoped buffer: CoreML owns it.
            guard states.strides.map(\.intValue) == [768000, 512, 1],
                  buffer.count >= 768000 else { return false }
            for frame in 0..<1500 {
                try checkCancellation()
                for channel in 0..<512 {
                    guard buffer[frame * 512 + channel].isFinite else {
                        throw WhisperProviderError.nonfiniteTensor
                    }
                }
            }
            return true
        }
        guard !scanned else { return }

        // Keep indexed access for layouts whose strides cannot use the fast path.
        for frame in 0..<1500 {
            try checkCancellation()
            for channel in 0..<512 {
                guard states[[0, NSNumber(value: frame), NSNumber(value: channel)]].floatValue.isFinite else {
                    throw WhisperProviderError.nonfiniteTensor
                }
            }
        }
    }
}
