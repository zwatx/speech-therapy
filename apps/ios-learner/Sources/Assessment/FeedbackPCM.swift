#if DEBUG && targetEnvironment(simulator)
  import Darwin
  import Foundation

  struct FeedbackPCM: Equatable, Sendable {
    let sampleCount: Int
    let durationMilliseconds: Double
    let rms: Double
    let rmsDbfs: Double
    let peak: Double
    let railSamples: Int
    let clippedFraction: Double
    var modelCaptureValid: Bool { sampleCount >= 1600 }

    static func read(_ url: URL) throws -> Data {
      guard url.isFileURL else { throw RecordingFeedbackError.invalidRecording }
      try Task.checkCancellation()
      let fd = Darwin.open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
      guard fd >= 0 else { throw RecordingFeedbackError.invalidRecording }
      defer { Darwin.close(fd) }
      var info = stat()
      guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
        info.st_uid == getuid(), info.st_nlink == 1, info.st_size > 0, info.st_size <= 132_096
      else { throw RecordingFeedbackError.invalidRecording }
      var result = Data()
      var buffer = [UInt8](repeating: 0, count: 4096)
      while true {
        try Task.checkCancellation()
        let count = Darwin.read(fd, &buffer, buffer.count)
        guard count >= 0 else { throw RecordingFeedbackError.invalidRecording }
        if count == 0 { break }
        guard result.count + count <= 132_096 else { throw RecordingFeedbackError.invalidRecording }
        result.append(contentsOf: buffer.prefix(count))
      }
      var after = stat()
      guard fstat(fd, &after) == 0, result.count == info.st_size,
        after.st_size == info.st_size, after.st_mtimespec.tv_sec == info.st_mtimespec.tv_sec,
        after.st_mtimespec.tv_nsec == info.st_mtimespec.tv_nsec
      else { throw RecordingFeedbackError.invalidRecording }
      return result
    }

    static func measure(_ data: Data) throws -> Self {
      let bytes = Array(data)
      func u16(_ i: Int) -> Int { Int(bytes[i]) | Int(bytes[i + 1]) << 8 }
      func u32(_ i: Int) -> Int { u16(i) | u16(i + 2) << 16 }
      func tag(_ i: Int) -> String { String(decoding: bytes[i..<i + 4], as: UTF8.self) }
      guard bytes.count >= 44, bytes.count <= 132_096, tag(0) == "RIFF", tag(8) == "WAVE",
        u32(4) == bytes.count - 8
      else { throw RecordingFeedbackError.invalidRecording }
      var position = 12
      var format: Range<Int>?
      var samples: Range<Int>?
      while position + 8 <= bytes.count {
        let length = u32(position + 4)
        let start = position + 8
        guard length <= bytes.count - start else { throw RecordingFeedbackError.invalidRecording }
        switch tag(position) {
        case "fmt ":
          guard format == nil else { throw RecordingFeedbackError.invalidRecording }
          format = start..<start + length
        case "data":
          guard samples == nil else { throw RecordingFeedbackError.invalidRecording }
          samples = start..<start + length
        default: break
        }
        position = start + length + length % 2
      }
      guard position == bytes.count, let format, format.count >= 16, let samples,
        u16(format.lowerBound) == 1, u16(format.lowerBound + 2) == 1,
        u32(format.lowerBound + 4) == 16000, u32(format.lowerBound + 8) == 32000,
        u16(format.lowerBound + 12) == 2, u16(format.lowerBound + 14) == 16,
        samples.count % 2 == 0, (1...64000).contains(samples.count / 2)
      else { throw RecordingFeedbackError.invalidRecording }
      var sum: Int64 = 0
      var signal = PCM16SignalMeasurements.Accumulator()
      for index in stride(from: samples.lowerBound, to: samples.upperBound, by: 2) {
        let value = Int(Int16(bitPattern: UInt16(u16(index))))
        sum += Int64(value) * Int64(value)
        guard signal.append(Int16(value)) else { throw RecordingFeedbackError.invalidRecording }
      }
      let count = samples.count / 2
      guard let measurements = signal.measurements(), measurements.sampleCount == count else {
        throw RecordingFeedbackError.invalidRecording
      }
      let rms = sqrt(Double(sum) / Double(count)) / 32768
      return Self(
        sampleCount: count, durationMilliseconds: Double(count) / 16, rms: rms,
        rmsDbfs: rms > 0 ? max(-120, 20 * log10(rms)) : -120, peak: measurements.peakNormalized,
        railSamples: measurements.railSampleCount,
        clippedFraction: Double(measurements.railSampleCount) / Double(count))
    }
  }
#endif
