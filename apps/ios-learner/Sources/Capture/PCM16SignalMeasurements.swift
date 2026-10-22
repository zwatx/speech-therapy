/// Exact facts about a bounded PCM16 recording. No samples or recording identity are retained.
struct PCM16SignalMeasurements: Equatable, Sendable {
  let sampleCount: Int
  let zeroSampleCount: Int
  let railSampleCount: Int
  let peakMagnitude: Int

  var peakNormalized: Double { Double(peakMagnitude) / 32768 }
  var isAllZero: Bool { zeroSampleCount == sampleCount }

  private init(sampleCount: Int, zeroSampleCount: Int, railSampleCount: Int, peakMagnitude: Int) {
    self.sampleCount = sampleCount
    self.zeroSampleCount = zeroSampleCount
    self.railSampleCount = railSampleCount
    self.peakMagnitude = peakMagnitude
  }

  struct Accumulator: Sendable {
    private var count = 0
    private var zeros = 0
    private var rails = 0
    private var peak = 0
    private var exceededLimit = false

    /// Overflow invalidates the entire measurement, including its otherwise valid prefix.
    @discardableResult
    mutating func append(_ sample: Int16) -> Bool {
      guard !exceededLimit, count < 64_000 else {
        exceededLimit = true
        return false
      }
      let value = Int(sample)
      count += 1
      if value == 0 { zeros += 1 }
      if value == -32768 || value == 32767 { rails += 1 }
      peak = max(peak, abs(value))
      return true
    }

    func measurements() -> PCM16SignalMeasurements? {
      guard !exceededLimit, count > 0 else { return nil }
      return PCM16SignalMeasurements(
        sampleCount: count, zeroSampleCount: zeros, railSampleCount: rails, peakMagnitude: peak)
    }
  }
}
