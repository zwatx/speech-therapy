import CoreML
import Foundation

/// All MLModel construction, feature buffers and synchronous prediction belong
/// exclusively to one off-main serial owner (or the unchanged fresh worker route).
/// No model or sample state crosses to UI; only a bounded completed-word guess may leave.
enum WhisperCoreMLWorker {
    /// Inert lazy slot, retained by exactly one bundled provider.
    final class ReusingWorker: @unchecked Sendable {
        private let owner = WhisperRuntimeOwner<Runtime>()
        func run(request: LocalWordRecognitionRequest, resources: WhisperBundledResources?,
                 stop: WhisperOperationStop) -> WhisperWorkerCompletion {
            owner.perform { slot in
                WhisperCoreMLWorker.run(request: request, resources: resources, stop: stop,
                                        boundary: PredictionBoundary(), slot: slot)
            }
        }
        func close() async { await owner.evictIdle() }
    }
    private struct PredictionBoundary: Sendable {
        #if WORD_RECOGNITION_LIFECYCLE_VERIFICATION
        let returned: (@Sendable (Int) -> Void)?
        init(_ returned: (@Sendable (Int) -> Void)? = nil) { self.returned = returned }
        #else
        init() {}
        #endif
    }

    static func run(request: LocalWordRecognitionRequest, resources: WhisperBundledResources?,
                    stop: WhisperOperationStop) -> WhisperWorkerCompletion {
        run(request: request, resources: resources, stop: stop, boundary: PredictionBoundary())
    }

    #if WORD_RECOGNITION_LIFECYCLE_VERIFICATION
    /// Scalar verification event only; no provider, model or tensor crosses this callback.
    static func run(request: LocalWordRecognitionRequest, resources: WhisperBundledResources?,
                    stop: WhisperOperationStop,
                    predictionReturned: @escaping @Sendable (Int) -> Void) -> WhisperWorkerCompletion {
        run(request: request, resources: resources, stop: stop,
            boundary: PredictionBoundary(predictionReturned))
    }
    #endif

    private static func run(request: LocalWordRecognitionRequest, resources: WhisperBundledResources?,
                            stop: WhisperOperationStop, boundary: PredictionBoundary,
                            slot: WhisperRuntimeOwner<Runtime>.Slot? = nil) -> WhisperWorkerCompletion {
        func complete(_ status: LocalWordRecognitionStatus) -> WhisperWorkerCompletion {
            .init(status: stop.interruptedStatus ?? status, cleanupConfirmed: true, retainedHandle: nil)
        }
        return processingCompletion(stop: stop, evict: { slot?.evict() }) {
            try stop.check()
            guard let resources else { slot?.evict(); return complete(.unavailable) }
            let assets: WhisperResourceAdmission.Assets
            do { assets = try WhisperResourceAdmission.load(resources, stop: stop) }
            catch let cleanup as WhisperHandleCleanupFailure { slot?.evict(); throw cleanup }
            catch { slot?.evict(); return complete(.unavailable) }
            let identity = resources.rootURL.standardizedFileURL.path + "\n"
                + resources.manifestSHA256 + "\ncpuOnly"
            do { try slot?.validateIdentity(identity) }
            catch { slot?.evict(); return complete(.unavailable) }
            try stop.check()
            let read = try WhisperPCM16.read(request.fileURL, stop: stop)
            guard read.cleanupConfirmed else {
                slot?.evict()
                return .init(status: stop.interruptedStatus ?? .unavailable,
                             cleanupConfirmed: false, retainedHandle: read.retainedHandle)
            }
            try stop.check()
            guard let samples = read.samples else { return complete(.unavailable) }
            guard !samples.allSatisfy({ $0 == 0 }) else { return complete(.uncertain) }
            try stop.check()
            let features = try assets.features.extract(samples: samples, sampleRate: 16000,
                                                       isCancelled: { stop.isStopped })
            let runtime: Runtime
            do {
                if let slot {
                    // Full admission above verified the exact namespace and every byte.
                    // The immutable manifest binds model/tokenizer/preprocessing contents.
                    runtime = try slot.admittedPair(identity: identity) {
                        try Runtime(assets: assets, stop: stop)
                    }
                } else { runtime = try Runtime(assets: assets, stop: stop) }
            }
            catch { slot?.evict(); return complete(.unavailable) }
            guard let text = try runtime.recognize(features: features, tokenizer: assets.tokenizer,
                                                  stop: stop, boundary: boundary) else { return complete(.uncertain) }
            try stop.check()
            // Expected word first participates here, after EOS-completed independent
            // ASR. No invented timestamps or timed LocalWordFinalSegment objects.
            return completedRecognition(text: text, expectedWord: request.expectedWord, stop: stop)
        }
    }

    /// Executes inline on the existing worker owner; never transfers runtime objects
    /// or retries processing. A failed close keeps its exact handle for the provider.
    static func processingCompletion(stop: WhisperOperationStop, evict: () -> Void,
                                     processing: () throws -> WhisperWorkerCompletion) -> WhisperWorkerCompletion {
        do {
            return try processing()
        } catch let cleanup as WhisperHandleCleanupFailure {
            evict()
            return .init(status: stop.interruptedStatus ?? .unavailable,
                         cleanupConfirmed: false, retainedHandle: cleanup.handle)
        } catch let token as WhisperTokenError {
            evict()
            // Undecodable output is an abstention; broken decoder invariants are not
            // evidence about the recording. The actual stop reason overrides both.
            let status: LocalWordRecognitionStatus = switch token {
            case .malformedUTF8, .byteLimit: .uncertain
            default: .unavailable
            }
            return .init(status: stop.interruptedStatus ?? status,
                         cleanupConfirmed: true, retainedHandle: nil)
        } catch {
            slot?.evict() // Includes cancellation: no possibly failed runtime reused.
            return complete(.uncertain)
        } // No arbitrary error/log content or retries.
    }

    static func compareCompleted(text: String, expectedWord: String) -> LocalWordRecognitionStatus {
        guard let actual = LocalWordComparison.singleWord(text),
              let expected = LocalWordComparison.singleWord(expectedWord) else { return .uncertain }
        return actual == expected ? .matched : .notMatched
    }

    /// Called only after independent EOS completion, also usable with invented text in tests.
    static func completedRecognition(text: String, expectedWord: String,
                                     stop: WhisperOperationStop) -> WhisperWorkerCompletion {
        let status = compareCompleted(text: text, expectedWord: expectedWord)
        let guess = LocalWordGuess(completedText: text, expectedWord: expectedWord)
        return .init(status: stop.interruptedStatus ?? status,
                     cleanupConfirmed: true, retainedHandle: nil, wordGuess: guess)
    }

    /// Checks every score, including suppressed scores, before selecting the first
    /// maximum among eligible entries. No softmax confidence or silent NaN repair.
    static func select(logits: [Float], tokenizer: WhisperByteDecoder, generatedCount: Int,
                       stop: WhisperOperationStop) throws -> Int32 {
        try maximum(logits: logits, stop: stop) {
            try tokenizer.isAllowedNext($0, generatedCount: generatedCount, isCancelled: { stop.isStopped })
        }
    }

    static func maximum(logits: [Float], stop: WhisperOperationStop,
                        isAllowed: (Int32) throws -> Bool) throws -> Int32 {
        guard logits.count == WhisperByteDecoder.vocabularySize else { throw WhisperProviderError.invalidTensor }
        var selected: Int32?
        var maximum: Float = -.infinity
        for (index, score) in logits.enumerated() {
            if index % 1024 == 0 { try stop.check() }
            guard score.isFinite else { throw WhisperProviderError.nonfiniteTensor }
            let id = Int32(index)
            if try isAllowed(id),
               selected == nil || score > maximum {
                selected = id
                maximum = score
            }
        }
        try stop.check()
        guard let selected else { throw WhisperProviderError.noEligibleToken }
        return selected
    }

    private final class Runtime {
        private let encoder: MLModel
        private let decoder: MLModel

        init(assets: WhisperResourceAdmission.Assets, stop: WhisperOperationStop) throws {
            let configuration = MLModelConfiguration()
            configuration.computeUnits = .cpuOnly
            try stop.check()
            encoder = try MLModel(contentsOf: assets.encoderURL, configuration: configuration)
            try stop.check()
            decoder = try MLModel(contentsOf: assets.decoderURL, configuration: configuration)
            try stop.check()
            try Self.fixed(encoder.modelDescription.inputDescriptionsByName, name: "mel_features", shape: [1, 80, 3000], type: .float32)
            try Self.fixed(encoder.modelDescription.outputDescriptionsByName, name: "encoder_hidden_states", shape: [1, 1500, 512], type: .float32)
            guard Set(decoder.modelDescription.inputDescriptionsByName.keys) == ["decoder_input_ids", "encoder_hidden_states"],
                  let prefix = decoder.modelDescription.inputDescriptionsByName["decoder_input_ids"]?.multiArrayConstraint,
                  prefix.dataType == .int32, prefix.shape.map(\.intValue) == [1, 8],
                  prefix.shapeConstraint.type == .range,
                  prefix.shapeConstraint.sizeRangeForDimension.count == 2 else { throw WhisperProviderError.invalidTensor }
            let ranges = prefix.shapeConstraint.sizeRangeForDimension.map(\.rangeValue)
            guard ranges[0] == NSRange(location: 1, length: 1),
                  ranges[1] == NSRange(location: 1, length: 64) else { throw WhisperProviderError.invalidTensor }
            try Self.fixed(decoder.modelDescription.inputDescriptionsByName, name: "encoder_hidden_states", shape: [1, 1500, 512], type: .float32, sole: false)
            try Self.fixed(decoder.modelDescription.outputDescriptionsByName, name: "next_token_logits", shape: [1, 51864], type: .float32)
        }

        func recognize(features: [Float], tokenizer: WhisperByteDecoder,
                       stop: WhisperOperationStop, boundary: PredictionBoundary) throws -> String? {
            try stop.check()
            let mel = try Self.floatInput(features, shape: [1, 80, 3000], stop: stop)
            let input = try MLDictionaryFeatureProvider(dictionary: ["mel_features": MLFeatureValue(multiArray: mel)])
            try stop.check()
            let encoded = try encoder.prediction(from: input)
            #if WORD_RECOGNITION_LIFECYCLE_VERIFICATION
            // Runtime retains both actual models; keep it and the returned provider alive
            // through the held verification boundary before the original stop check.
            withExtendedLifetime((self, encoded)) { boundary.returned?(0) }
            #endif
            try stop.check() // prediction is synchronous; a stop never interrupts it.
            guard let states = encoded.featureValue(for: "encoder_hidden_states")?.multiArrayValue else { throw WhisperProviderError.invalidTensor }
            try Self.validate(states, shape: [1, 1500, 512], type: .float32)
            for frame in 0..<1500 {
                try stop.check()
                for channel in 0..<512 {
                    guard states[[0, NSNumber(value: frame), NSNumber(value: channel)]].floatValue.isFinite else {
                        throw WhisperProviderError.nonfiniteTensor
                    }
                }
            }
            var prefix = try tokenizer.initialPrefix(isCancelled: { stop.isStopped })
            var generated = [Int32]()
            for step in 0..<WhisperByteDecoder.maximumGeneratedDecisions {
                try stop.check()
                guard (2...64).contains(prefix.count) else { throw WhisperProviderError.invalidTensor }
                let ids = try MLMultiArray(shape: [1, NSNumber(value: prefix.count)], dataType: .int32)
                guard ids.strides.map(\.intValue) == [prefix.count, 1] else { throw WhisperProviderError.invalidTensor }
                let pointer = ids.dataPointer.assumingMemoryBound(to: Int32.self)
                for index in prefix.indices { pointer[index] = prefix[index] }
                let decodeInput = try MLDictionaryFeatureProvider(dictionary: [
                    "decoder_input_ids": MLFeatureValue(multiArray: ids),
                    "encoder_hidden_states": MLFeatureValue(multiArray: states)])
                try stop.check()
                let decoded = try decoder.prediction(from: decodeInput)
                try stop.check()
                guard let scores = decoded.featureValue(for: "next_token_logits")?.multiArrayValue else { throw WhisperProviderError.invalidTensor }
                try Self.validate(scores, shape: [1, 51864], type: .float32)
                var logits = [Float]()
                logits.reserveCapacity(51864)
                for index in 0..<51864 {
                    if index % 1024 == 0 { try stop.check() }
                    logits.append(scores[[0, NSNumber(value: index)]].floatValue)
                }
                generated.append(try WhisperCoreMLWorker.select(logits: logits, tokenizer: tokenizer,
                                                               generatedCount: step, stop: stop))
                switch try tokenizer.decodeGenerated(generated, isCancelled: { stop.isStopped }) {
                case .completed(let text): return text
                case .incomplete:
                    if step + 1 == WhisperByteDecoder.maximumGeneratedDecisions { return nil }
                    prefix.append(generated.last!) // Never append the non-EOS final decision to a65-token input.
                }
            }
            return nil
        }

        private static func fixed(_ values: [String: MLFeatureDescription], name: String, shape: [Int],
                                  type: MLMultiArrayDataType, sole: Bool = true) throws {
            guard (!sole || values.count == 1), let constraint = values[name]?.multiArrayConstraint,
                  constraint.dataType == type, constraint.shape.map(\.intValue) == shape else { throw WhisperProviderError.invalidTensor }
        }
        private static func validate(_ array: MLMultiArray, shape: [Int], type: MLMultiArrayDataType) throws {
            guard array.dataType == type, array.shape.map(\.intValue) == shape,
                  array.count == shape.reduce(1, *) else { throw WhisperProviderError.invalidTensor }
        }
        private static func floatInput(_ values: [Float], shape: [Int], stop: WhisperOperationStop) throws -> MLMultiArray {
            guard values.count == shape.reduce(1, *) else { throw WhisperProviderError.invalidTensor }
            let array = try MLMultiArray(shape: shape.map(NSNumber.init(value:)), dataType: .float32)
            guard array.strides.map(\.intValue) == [240000, 3000, 1] else { throw WhisperProviderError.invalidTensor }
            let pointer = array.dataPointer.assumingMemoryBound(to: Float.self)
            for index in values.indices {
                if index % 1024 == 0 { try stop.check() }
                guard values[index].isFinite else { throw WhisperProviderError.nonfiniteTensor }
                pointer[index] = values[index]
            }
            return array
        }
    }
}
