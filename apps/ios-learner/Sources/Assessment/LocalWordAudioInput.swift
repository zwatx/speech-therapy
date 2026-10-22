import AVFoundation
import CoreMedia
import Foundation
import Speech

/// Finite, worker-local conversion only. Does not broaden the original WAV admission.
@available(iOS 26, *)
enum LocalWordAudioInput {
  enum Failure: Error, Equatable {
    case invalidSource, unsupportedDestination, allocation, conversion, noProgress, bounds
    case duration, sequence
  }

  struct Prepared {
    // These buffers are never mutated after preparation or AnalyzerInput handoff.
    let buffers: [AVAudioPCMBuffer]
    let sourceFrames: AVAudioFrameCount
    let outputFrames: Int
    let sampleRate: Int32

    func inputSequence() throws -> AsyncStream<AnalyzerInput> {
      guard !buffers.isEmpty, buffers.count <= 256 else { throw Failure.sequence }
      let pair = AsyncStream<AnalyzerInput>.makeStream(
        bufferingPolicy: .bufferingOldest(buffers.count))
      defer { pair.continuation.finish() }
      var offset: Int64 = 0
      for buffer in buffers {
        try Task.checkCancellation()
        let input = AnalyzerInput(
          buffer: buffer, bufferStartTime: CMTime(value: offset, timescale: sampleRate))
        guard case .enqueued = pair.continuation.yield(input) else { throw Failure.sequence }
        offset += Int64(buffer.frameLength)
      }
      guard offset == outputFrames else { throw Failure.sequence }
      return pair.stream
    }
  }

  /// Source file stays local to the caller's analysis worker, which closes it before joining.
  static func read(_ file: AVAudioFile, admittedDuration: Double) throws -> AVAudioPCMBuffer {
    try Task.checkCancellation()
    guard file.fileFormat.sampleRate == 16_000, file.fileFormat.channelCount == 1,
      file.length >= 1_600, file.length <= 64_000,
      Double(file.length) / 16_000 == admittedDuration,
      file.processingFormat.sampleRate == 16_000, file.processingFormat.channelCount == 1,
      let buffer = AVAudioPCMBuffer(
        pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length))
    else { throw Failure.invalidSource }
    try file.read(into: buffer, frameCount: AVAudioFrameCount(file.length))
    try Task.checkCancellation()
    guard buffer.frameLength == file.length else { throw Failure.invalidSource }
    return buffer
  }

  static func convert(
    _ source: AVAudioPCMBuffer, to destination: AVAudioFormat,
    checkCancellation: () throws -> Void = { try Task.checkCancellation() }
  ) throws -> Prepared {
    try checkCancellation()
    guard source.format.sampleRate == 16_000, source.format.channelCount == 1,
      source.frameLength >= 1_600, source.frameLength <= 64_000,
      validPCM(source.format), finite(source)
    else { throw Failure.invalidSource }
    let rate = destination.sampleRate
    guard validPCM(destination), rate.isFinite, rate >= 1, rate <= 192_000,
      rate.rounded() == rate, destination.channelCount >= 1, destination.channelCount <= 2
    else { throw Failure.unsupportedDestination }
    let frameBytes =
      Int(destination.streamDescription.pointee.mBytesPerFrame)
      * (destination.isInterleaved ? 1 : Int(destination.channelCount))
    guard frameBytes > 0, frameBytes <= 16 else { throw Failure.unsupportedDestination }
    guard let converter = AVAudioConverter(from: source.format, to: destination) else {
      throw Failure.conversion
    }
    // Finite-file mode: no client pre-seek, no manual padding or latency correction.
    converter.primeMethod = .normal
    let feed = Feed(source)
    let expectedFrames = Double(source.frameLength) * rate / 16_000
    let maximumFrames = Int(ceil(expectedFrames)) + 1
    var output: [AVAudioPCMBuffer] = []
    var frames = 0
    var allocatedBytes = 0
    var zeroProgress = 0
    for _ in 0..<512 {
      try checkCancellation()
      guard let buffer = AVAudioPCMBuffer(pcmFormat: destination, frameCapacity: 4_096) else {
        throw Failure.allocation
      }
      var error: NSError?
      var callbackError: (any Error)?
      let before = feed.cursor
      let status = converter.convert(to: buffer, error: &error) { requested, inputStatus in
        do {
          try checkCancellation()
          return try feed.next(requested: requested, status: inputStatus)
        } catch {
          callbackError = error
          inputStatus.pointee = .endOfStream
          return nil
        }
      }
      if let callbackError { throw callbackError }
      try checkCancellation()
      guard status != .error, error == nil else { throw Failure.conversion }
      guard buffer.format == destination, finite(buffer) else { throw Failure.conversion }
      if buffer.frameLength > 0 {
        frames += Int(buffer.frameLength)
        allocatedBytes += Int(buffer.frameCapacity) * frameBytes
        guard frames <= maximumFrames, allocatedBytes <= 16 * 1_024 * 1_024,
          output.count < 256
        else { throw Failure.bounds }
        output.append(buffer)
      }
      switch status {
      case .endOfStream:
        guard feed.cursor == source.frameLength, feed.ended, frames > 0,
          abs(Double(frames) - expectedFrames) <= 1
        else { throw Failure.duration }
        return Prepared(
          buffers: output, sourceFrames: source.frameLength, outputFrames: frames,
          sampleRate: Int32(rate))
      case .haveData, .inputRanDry:
        zeroProgress = feed.cursor == before && buffer.frameLength == 0 ? zeroProgress + 1 : 0
        guard zeroProgress < 2 else { throw Failure.noProgress }
      case .error: throw Failure.conversion
      @unknown default: throw Failure.conversion
      }
    }
    throw Failure.bounds
  }

  /// Supplies each frame once, respects the converter's requested packet count, and retains
  /// each input slice until the next callback. PCM has one frame per packet.
  final class Feed {
    let source: AVAudioPCMBuffer
    private(set) var cursor: AVAudioFrameCount = 0
    private(set) var ended = false
    private var callbacks = 0
    private var retained: AVAudioPCMBuffer?

    init(_ source: AVAudioPCMBuffer) { self.source = source }

    func next(
      requested: AVAudioPacketCount, status: UnsafeMutablePointer<AVAudioConverterInputStatus>
    )
      throws -> AVAudioPCMBuffer?
    {
      callbacks += 1
      guard callbacks <= 512 else { throw Failure.bounds }
      guard cursor < source.frameLength else {
        ended = true
        retained = nil
        status.pointee = .endOfStream
        return nil
      }
      guard requested > 0 else { throw Failure.noProgress }
      let count = min(requested, source.frameLength - cursor)
      guard let slice = AVAudioPCMBuffer(pcmFormat: source.format, frameCapacity: count) else {
        throw Failure.allocation
      }
      slice.frameLength = count
      let input = UnsafeMutableAudioBufferListPointer(source.mutableAudioBufferList)
      let target = UnsafeMutableAudioBufferListPointer(slice.mutableAudioBufferList)
      let stride = Int(source.format.streamDescription.pointee.mBytesPerFrame)
      guard input.count == target.count, stride > 0 else { throw Failure.invalidSource }
      for index in input.indices {
        let start = Int(cursor) * stride
        let bytes = Int(count) * stride
        guard start + bytes <= input[index].mDataByteSize,
          bytes <= target[index].mDataByteSize,
          let sourceBytes = input[index].mData, let targetBytes = target[index].mData
        else { throw Failure.invalidSource }
        targetBytes.copyMemory(from: sourceBytes.advanced(by: start), byteCount: bytes)
      }
      cursor += count
      retained = slice
      status.pointee = .haveData
      return slice
    }
  }

  private static func validPCM(_ format: AVAudioFormat) -> Bool {
    let description = format.streamDescription.pointee
    return description.mFormatID == kAudioFormatLinearPCM && description.mFramesPerPacket == 1
      && [.pcmFormatInt16, .pcmFormatInt32, .pcmFormatFloat32, .pcmFormatFloat64].contains(
        format.commonFormat)
  }

  private static func finite(_ buffer: AVAudioPCMBuffer) -> Bool {
    let list = UnsafeMutableAudioBufferListPointer(buffer.mutableAudioBufferList)
    for item in list {
      let count = Int(buffer.frameLength) * Int(item.mNumberChannels)
      guard let data = item.mData else { return buffer.frameLength == 0 }
      switch buffer.format.commonFormat {
      case .pcmFormatFloat32:
        guard count * MemoryLayout<Float>.size <= item.mDataByteSize else { return false }
        if !UnsafeBufferPointer(start: data.assumingMemoryBound(to: Float.self), count: count)
          .allSatisfy({ $0.isFinite })
        {
          return false
        }
      case .pcmFormatFloat64:
        guard count * MemoryLayout<Double>.size <= item.mDataByteSize else { return false }
        if !UnsafeBufferPointer(start: data.assumingMemoryBound(to: Double.self), count: count)
          .allSatisfy({ $0.isFinite })
        {
          return false
        }
      case .pcmFormatInt16, .pcmFormatInt32: break
      default: return false
      }
    }
    return true
  }
}
