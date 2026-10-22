import CoreML
import CryptoKit
import Darwin
import Foundation

/// Hidden-only output. This is neither CTC posteriors nor a completed assessment.
struct NativeHiddenInputIdentity: Equatable, Sendable {
  let request: NativeHiddenRequest
  let file: NativeHiddenFileIdentity
  let wavSHA256: String
  let decodedSamplesSHA256: String
  let normalizedSamplesSHA256: String
  let sampleCount: Int
  let validFrames: Int
}

struct NativeHiddenFeatures: Equatable, Sendable {
  let identity: NativeHiddenInputIdentity
  /// Owned little-endian Float32 [1,199,1024], including unchanged invalid query rows.
  let hidden: Data
}

enum NativeHiddenCoreMLWorker {
  private struct PredictionBoundary: Sendable {
    #if NATIVE_HIDDEN_LIFECYCLE_VERIFICATION
      let returned: (@Sendable (Int) -> Void)?
      init(_ returned: (@Sendable (Int) -> Void)? = nil) { self.returned = returned }
    #else
      init() {}
    #endif
  }

  struct KernelOutput: Sendable {
    let projected: Data
    let maskedProjected: Data
    let positionEmbeddings: Data
    let hidden: Data
  }

  static func run(
    request: NativeHiddenRequest, resources: NativeHiddenResources?,
    stop: WhisperOperationStop
  ) -> NativeHiddenWorkerCompletion {
    run(request: request, resources: resources, stop: stop, boundary: PredictionBoundary())
  }

  #if NATIVE_HIDDEN_LIFECYCLE_VERIFICATION
    /// Scalar verification event only; no Core ML object or tensor crosses this callback.
    static func run(
      request: NativeHiddenRequest, resources: NativeHiddenResources?,
      stop: WhisperOperationStop, predictionReturned: (@Sendable (Int) -> Void)?
    ) -> NativeHiddenWorkerCompletion {
      run(
        request: request, resources: resources, stop: stop,
        boundary: PredictionBoundary(predictionReturned))
    }
  #endif

  private static func run(
    request: NativeHiddenRequest, resources: NativeHiddenResources?,
    stop: WhisperOperationStop, boundary: PredictionBoundary
  ) -> NativeHiddenWorkerCompletion {
    func complete(_ status: NativeHiddenStatus, _ features: NativeHiddenFeatures? = nil)
      -> NativeHiddenWorkerCompletion
    {
      .init(
        request: request, status: status, features: features, cleanupConfirmed: true,
        retainedHandle: nil)
    }
    do {
      try stop.check()
      guard let resources else { return complete(.unavailable) }
      let assets: NativeHiddenResourceAdmission.Assets
      do { assets = try NativeHiddenResourceAdmission.load(resources, stop: stop) } catch let
        cleanup as WhisperHandleCleanupFailure
      { throw cleanup } catch { return complete(.unavailable) }
      let input = try NativeHiddenFiles.read(
        request.recording.url, maximum: LocalWordWAVGate.maximumFileBytes,
        retain: true, stop: stop)
      guard input.identity.uid == getuid(), input.identity.links == 1 else {
        throw NativeHiddenFailure.rejectedInput
      }
      let samples = try WhisperPCM16.decode(input.data, stop: stop)
      guard request.recording.summary.duration.isFinite,
        request.recording.summary.duration == Double(samples.count) / 16000
      else { throw NativeHiddenFailure.rejectedInput }
      let normalized = try NativeCTCPreprocessing.normalize(samples, tick: { try stop.check() })
      let valid = frames(samples.count)
      let decodedBytes = try floatBytes(samples, stop: stop)
      let normalizedBytes = try floatBytes(normalized, stop: stop)
      var padded = normalizedBytes
      padded.append(Data(repeating: 0, count: (64000 - samples.count) * 4))
      let output = try infer(
        normalizedWaveform: padded, validSampleCount: samples.count, assets: assets, stop: stop,
        boundary: boundary)
      try stop.check()
      guard
        try NativeHiddenFiles.identity(request.recording.url, directory: false) == input.identity
      else {
        throw NativeHiddenFailure.rejectedInput
      }
      let identity = NativeHiddenInputIdentity(
        request: request, file: input.identity, wavSHA256: input.sha256,
        decodedSamplesSHA256: digest(decodedBytes),
        normalizedSamplesSHA256: digest(normalizedBytes),
        sampleCount: samples.count, validFrames: valid)
      return complete(.completed, NativeHiddenFeatures(identity: identity, hidden: output.hidden))
    } catch let cleanup as WhisperHandleCleanupFailure {
      return .init(
        request: request, status: .failed, features: nil, cleanupConfirmed: false,
        retainedHandle: cleanup.handle)
    } catch is CancellationError {
      return complete(.cancelled)
    } catch NativeHiddenFailure.rejectedInput {
      return complete(.rejectedInput)
    } catch WhisperProviderError.rejectedInput {
      return complete(.rejectedInput)
    } catch { return complete(.failed) }
  }

  static func frames(_ length: Int) -> Int {
    var result = length
    for (kernel, stride) in zip([10, 3, 3, 3, 3, 2, 2], [5, 2, 2, 2, 2, 2, 2]) {
      result = (result - kernel) / stride + 1
    }
    return result
  }

  static func floatBytes(_ values: [Float], stop: WhisperOperationStop) throws -> Data {
    var result = Data()
    result.reserveCapacity(values.count * 4)
    for (index, value) in values.enumerated() {
      if index % 256 == 0 { try stop.check() }
      guard value.isFinite else { throw NativeHiddenFailure.nonfiniteTensor }
      var bits = value.bitPattern.littleEndian
      withUnsafeBytes(of: &bits) { result.append(contentsOf: $0) }
    }
    return result
  }

  private static func digest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  /// Generated app-host controls enter here without pretending normalized controls are PCM16.
  /// The actual three-program CPU-only kernel is extracted from the admitted iOS worker.
  static func infer(
    normalizedWaveform: Data, validSampleCount: Int,
    assets: NativeHiddenResourceAdmission.Assets, stop: WhisperOperationStop
  ) throws -> KernelOutput {
    try infer(
      normalizedWaveform: normalizedWaveform, validSampleCount: validSampleCount,
      assets: assets, stop: stop, boundary: PredictionBoundary())
  }

  private static func infer(
    normalizedWaveform: Data, validSampleCount: Int,
    assets: NativeHiddenResourceAdmission.Assets, stop: WhisperOperationStop,
    boundary: PredictionBoundary
  ) throws -> KernelOutput {
    try stop.check()
    guard (1600...64000).contains(validSampleCount), normalizedWaveform.count == 256000 else {
      throw NativeHiddenFailure.invalidTensor
    }
    for index in 0..<64000 {
      if index % 256 == 0 { try stop.check() }
      let offset = index * 4
      let bits =
        UInt32(normalizedWaveform[offset]) | UInt32(normalizedWaveform[offset + 1]) << 8
        | UInt32(normalizedWaveform[offset + 2]) << 16 | UInt32(normalizedWaveform[offset + 3])
        << 24
      let value = Float(bitPattern: bits)
      guard value.isFinite, index < validSampleCount || value == 0 else {
        throw NativeHiddenFailure.invalidTensor
      }
    }
    try assets.checkCurrent(stop: stop)
    let held = Retained()  // Survives model teardown AND the inference autorelease-pool drain.
    defer { autoreleasepool { held.entries.removeAll() } }
    let output = try autoreleasepool {
      let configuration = MLModelConfiguration()
      configuration.computeUnits = .cpuOnly
      var frontend: MLModel?
      var positional: MLModel?
      var body: MLModel?
      defer {
        body = nil
        positional = nil
        frontend = nil
        withExtendedLifetime(held) {}
      }
      try stop.check()
      frontend = try MLModel(contentsOf: assets.frontendURL, configuration: configuration)
      try stop.check()
      positional = try MLModel(contentsOf: assets.positionalURL, configuration: configuration)
      try stop.check()
      body = try MLModel(contentsOf: assets.encoderBodyURL, configuration: configuration)
      try fixed(
        frontend!.modelDescription.inputDescriptionsByName,
        ["normalizedWaveform": ([1, 64000], .float32)])
      try fixed(
        frontend!.modelDescription.outputDescriptionsByName,
        [
          "features": ([1, 199, 512], .float32), "normalizedFeatures": ([1, 199, 512], .float32),
          "projected": ([1, 199, 1024], .float32),
        ])
      try fixed(
        positional!.modelDescription.inputDescriptionsByName,
        ["paddedChannels": ([1, 1024, 327], .float32)])
      try fixed(
        positional!.modelDescription.outputDescriptionsByName,
        [
          "convOutput": ([1, 200, 1024], .float32), "trimmed": ([1, 199, 1024], .float32),
          "activated": ([1, 199, 1024], .float32),
        ])
      try fixed(
        body!.modelDescription.inputDescriptionsByName,
        [
          "maskedProjected": ([1, 199, 1024], .float32),
          "positionEmbeddings": ([1, 199, 1024], .float32), "frameMask": ([1, 199], .int32),
        ])
      try fixed(
        body!.modelDescription.outputDescriptionsByName, ["hidden": ([1, 199, 1024], .float32)])
      let wave = try ownedArray(
        normalizedWaveform, shape: [1, 64000], strides: [64000, 1], type: .float32)
      let a = try predict(
        frontend!, arrays: ["normalizedWaveform": wave], bytes: [normalizedWaveform],
        outputs: [
          ("features", 199, 512), ("normalizedFeatures", 199, 512), ("projected", 199, 1024),
        ], held: held, stop: stop, boundary: boundary)
      let projected = a[2]
      let valid = frames(validSampleCount)
      let masked = try maskedProjection(projected, validFrames: valid)
      let padded = try paddedChannels(masked, stop: stop)
      let mask = try frameMask(valid)
      let maskedArray = try ownedArray(
        masked, shape: [1, 199, 1024], strides: [203776, 1024, 1], type: .float32)
      let paddedArray = try ownedArray(
        padded, shape: [1, 1024, 327], strides: [334848, 327, 1], type: .float32)
      let b = try predict(
        positional!, arrays: ["paddedChannels": paddedArray], bytes: [padded],
        outputs: [("convOutput", 200, 1024), ("trimmed", 199, 1024), ("activated", 199, 1024)],
        held: held, stop: stop, boundary: boundary)
      let position = b[2]  // All199 rows survive, including invalid queries.
      let positionArray = try ownedArray(
        position, shape: [1, 199, 1024], strides: [203776, 1024, 1], type: .float32)
      let maskArray = try ownedArray(mask, shape: [1, 199], strides: [199, 1], type: .int32)
      let c = try predict(
        body!,
        arrays: [
          "maskedProjected": maskedArray, "positionEmbeddings": positionArray,
          "frameMask": maskArray,
        ],
        bytes: [masked, position, mask], outputs: [("hidden", 199, 1024)], held: held, stop: stop,
        boundary: boundary)
      try stop.check()
      return KernelOutput(
        projected: projected, maskedProjected: masked, positionEmbeddings: position, hidden: c[0])
    }
    try assets.checkCurrent(stop: stop)
    try stop.check()
    return output
  }

  static func maskedProjection(_ projected: Data, validFrames: Int) throws -> Data {
    guard projected.count == 815104, (1...199).contains(validFrames) else {
      throw NativeHiddenFailure.invalidTensor
    }
    var masked = projected
    let firstInvalidByte = validFrames * 1024 * 4
    masked.resetBytes(in: firstInvalidByte..<815104)
    guard masked.prefix(firstInvalidByte) == projected.prefix(firstInvalidByte),
      masked[firstInvalidByte..<815104].allSatisfy({ $0 == 0 })
    else { throw NativeHiddenFailure.invalidTensor }
    return masked
  }

  static func paddedChannels(_ masked: Data, stop: WhisperOperationStop) throws -> Data {
    guard masked.count == 815104 else { throw NativeHiddenFailure.invalidTensor }
    var padded = Data(repeating: 0, count: 1_339_392)
    for channel in 0..<1024 {
      try stop.check()
      for frame in 0..<199 {
        let source = (frame * 1024 + channel) * 4
        let target = (channel * 327 + 64 + frame) * 4
        padded.replaceSubrange(target..<(target + 4), with: masked[source..<(source + 4)])
      }
      let row = channel * 327 * 4
      guard padded[row..<(row + 64 * 4)].allSatisfy({ $0 == 0 }),
        padded[(row + 263 * 4)..<(row + 327 * 4)].allSatisfy({ $0 == 0 })
      else { throw NativeHiddenFailure.invalidTensor }
    }
    var recovered = Data()
    recovered.reserveCapacity(815104)
    for frame in 0..<199 {
      try stop.check()
      for channel in 0..<1024 {
        let source = (channel * 327 + 64 + frame) * 4
        recovered.append(contentsOf: padded[source..<(source + 4)])
      }
    }
    guard padded.count == 1_339_392, recovered == masked else {
      throw NativeHiddenFailure.invalidTensor
    }
    return padded
  }

  static func frameMask(_ validFrames: Int) throws -> Data {
    guard (1...199).contains(validFrames) else { throw NativeHiddenFailure.invalidTensor }
    var data = Data(repeating: 0, count: 796)
    for frame in 0..<validFrames { data[frame * 4] = 1 }
    for frame in 0..<199 {
      let index = frame * 4
      guard data[index] == (frame < validFrames ? 1 : 0), data[index + 1] == 0,
        data[index + 2] == 0, data[index + 3] == 0
      else { throw NativeHiddenFailure.invalidTensor }
    }
    return data
  }

  private static func fixed(
    _ descriptions: [String: MLFeatureDescription],
    _ expected: [String: ([Int], MLMultiArrayDataType)]
  ) throws {
    guard Set(descriptions.keys) == Set(expected.keys) else {
      throw NativeHiddenFailure.invalidTensor
    }
    for (name, (shape, type)) in expected {
      guard let description = descriptions[name], description.type == .multiArray,
        !description.isOptional,
        let constraint = description.multiArrayConstraint,
        constraint.shape.map(\.intValue) == shape,
        constraint.dataType == type
      else { throw NativeHiddenFailure.invalidTensor }
      switch constraint.shapeConstraint.type {
      case .unspecified: break
      case .enumerated:
        let allowed = constraint.shapeConstraint.enumeratedShapes
        guard allowed.count == 1, allowed[0].map(\.intValue) == shape else {
          throw NativeHiddenFailure.invalidTensor
        }
      default: throw NativeHiddenFailure.invalidTensor
      }
    }
  }

  private static func ownedArray(
    _ bytes: Data, shape: [Int], strides: [Int], type: MLMultiArrayDataType
  ) throws -> MLMultiArray {
    let array = try MLMultiArray(shape: shape.map(NSNumber.init(value:)), dataType: type)
    let count = shape.reduce(1, *)
    guard array.shape.map(\.intValue) == shape, array.strides.map(\.intValue) == strides,
      array.dataType == type, array.count == count, bytes.count == count * 4
    else { throw NativeHiddenFailure.invalidTensor }
    bytes.withUnsafeBytes {
      array.dataPointer.copyMemory(from: $0.baseAddress!, byteCount: $0.count)
    }
    guard Data(bytes: array.dataPointer, count: bytes.count) == bytes else {
      throw NativeHiddenFailure.invalidTensor
    }
    return array
  }

  private struct Entry {
    let provider: MLDictionaryFeatureProvider
    let arrays: [MLMultiArray]
    let bytes: [Data]
    var result: (any MLFeatureProvider)?
    var outputs = [MLMultiArray]()
    var copied = [Data]()
  }
  private final class Retained { var entries = [Entry]() }

  private static func predict(
    _ model: MLModel, arrays: [String: MLMultiArray], bytes: [Data],
    outputs: [(String, Int, Int)], held: Retained, stop: WhisperOperationStop,
    boundary: PredictionBoundary
  ) throws -> [Data] {
    try stop.check()
    let provider = try MLDictionaryFeatureProvider(
      dictionary: arrays.mapValues { MLFeatureValue(multiArray: $0) })
    let call = held.entries.count
    held.entries.append(Entry(provider: provider, arrays: Array(arrays.values), bytes: bytes))
    let result = try model.prediction(from: provider)
    held.entries[call].result = result
    #if NATIVE_HIDDEN_LIFECYCLE_VERIFICATION
      boundary.returned?(call)
    #endif
    try stop.check()  // This check is after the actual synchronous prediction return.
    guard result.featureNames == Set(outputs.map { $0.0 }) else {
      throw NativeHiddenFailure.invalidTensor
    }
    let returned = try outputs.map { spec -> MLMultiArray in
      guard let array = result.featureValue(for: spec.0)?.multiArrayValue else {
        throw NativeHiddenFailure.invalidTensor
      }
      return array
    }
    held.entries[call].outputs = returned
    var copied = [Data]()
    for (index, spec) in outputs.enumerated() {
      copied.append(
        try autoreleasepool {
          let array = returned[index]
          guard array.shape.map(\.intValue) == [1, spec.1, spec.2], array.dataType == .float32,
            array.count == spec.1 * spec.2, array.strides.count == 3,
            array.strides.allSatisfy({ $0.intValue > 0 })
          else { throw NativeHiddenFailure.invalidTensor }
          var data = Data()
          data.reserveCapacity(spec.1 * spec.2 * 4)
          for frame in 0..<spec.1 {
            try stop.check()
            for column in 0..<spec.2 {
              let value = array[[0, NSNumber(value: frame), NSNumber(value: column)]].floatValue
              guard value.isFinite else { throw NativeHiddenFailure.nonfiniteTensor }
              var bits = value.bitPattern.littleEndian
              withUnsafeBytes(of: &bits) { data.append(contentsOf: $0) }
            }
          }
          guard data.count == spec.1 * spec.2 * 4 else { throw NativeHiddenFailure.invalidTensor }
          return data
        })
    }
    held.entries[call].copied = copied
    return copied
  }
}
