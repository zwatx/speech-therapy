import Foundation

enum LocalWordRecognitionStatus: Equatable, Sendable {
  case matched
  case notMatched
  case uncertain
  case timedOut
  case unavailable
  case cancelled
}

struct LocalWordRecognitionRequest: Equatable, Sendable {
  let operationID: UUID
  let tryID: UUID
  let fileURL: URL
  let expectedWord: String
}

/// Bounded ephemeral completed-word alternative, never a sound judgment or stored transcript.
struct LocalWordGuess: Equatable, Sendable {
  let word: String
  let expectedWord: String

  init?(completedText: String, expectedWord: String) {
    guard let actual = LocalWordComparison.singleWord(completedText), actual.utf8.count <= 32,
      let expected = LocalWordComparison.singleWord(expectedWord), actual != expected
    else { return nil }
    word = actual
    self.expectedWord = expected
  }
}

/// May carry a bounded ephemeral guess; never Codable, logged or persisted.
/// Cleanup is an acknowledgement, not a cancellation request.
struct LocalWordRecognitionReceipt: Equatable, Sendable {
  let request: LocalWordRecognitionRequest
  let status: LocalWordRecognitionStatus
  let cleanupConfirmed: Bool
  let wordGuess: LocalWordGuess?

  init(
    request: LocalWordRecognitionRequest, status: LocalWordRecognitionStatus,
    cleanupConfirmed: Bool, wordGuess: LocalWordGuess? = nil
  ) {
    self.request = request
    self.status = status
    self.cleanupConfirmed = cleanupConfirmed
    self.wordGuess = cleanupConfirmed && status == .notMatched
      && wordGuess?.expectedWord == LocalWordComparison.singleWord(request.expectedWord)
      ? wordGuess : nil
  }

  var operationID: UUID { request.operationID }
  var tryID: UUID { request.tryID }
  var fileURL: URL { request.fileURL }
  var expectedWord: String { request.expectedWord }
}

@MainActor
protocol LocalWordRecognizing: AnyObject {
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt
  func cancel(operationID: UUID)
}

/// Optional capability for providers with flow-scoped model resources. Ordinary
/// injected recognizers need no stub. False never authorizes dropping live work.
@MainActor
protocol LocalWordRuntimeReleasing: AnyObject {
  func releaseWordRuntime() async -> Bool
}

/// Ephemeral comparison input. Production instances live only in the result consumer.
struct LocalWordFinalSegment: Equatable, Sendable {
  let text: String
  let start: Double
  let duration: Double
}

enum LocalWordComparison {
  struct Comparison: Equatable, Sendable {
    let status: LocalWordRecognitionStatus
    let reason: LocalWordRecognitionDiagnostic.Reason
  }

  static func compare(
    finals: [LocalWordFinalSegment]?, expectedWord: String, audioDuration: Double
  ) -> LocalWordRecognitionStatus {
    diagnose(finals: finals, expectedWord: expectedWord, audioDuration: audioDuration).status
  }

  static func diagnose(
    finals: [LocalWordFinalSegment]?, expectedWord: String, audioDuration: Double
  ) -> Comparison {
    guard let finals, !finals.isEmpty else {
      return .init(status: .uncertain, reason: .comparisonEmpty)
    }
    guard finals.count <= 64 else { return .init(status: .uncertain, reason: .boundedLimit) }
    guard audioDuration.isFinite, audioDuration > 0 else {
      return .init(status: .uncertain, reason: .invalidAudioDuration)
    }
    guard let expected = singleWord(expectedWord) else {
      return .init(status: .uncertain, reason: .invalidExpectedWord)
    }
    var unique: [LocalWordFinalSegment] = []
    var characters = 0
    for segment in finals {
      characters += segment.text.count
      guard characters <= 1024 else { return .init(status: .uncertain, reason: .boundedLimit) }
      guard segment.start.isFinite, segment.duration.isFinite,
        segment.start >= 0, segment.duration > 0,
        (segment.start + segment.duration).isFinite,
        segment.start + segment.duration <= audioDuration + 0.05
      else { return .init(status: .uncertain, reason: .comparisonRange) }
      if !unique.contains(segment) { unique.append(segment) }
    }
    unique.sort { $0.start < $1.start }
    for index in unique.indices.dropFirst() {
      let previous = unique[index - 1]
      guard previous.start + previous.duration <= unique[index].start else {
        return .init(status: .uncertain, reason: .comparisonOverlap)
      }
    }
    guard let actual = singleWord(unique.map(\.text).joined(separator: " ")) else {
      return .init(status: .uncertain, reason: .comparisonNonSingleWord)
    }
    return actual == expected
      ? .init(status: .matched, reason: .comparisonMatched)
      : .init(status: .notMatched, reason: .comparisonMismatch)
  }

  /// ASCII case folding only. Punctuation can surround a word but cannot repair it.
  static func singleWord(_ text: String) -> String? {
    let edge = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters)
    let trimmed = text.trimmingCharacters(in: edge)
    guard !trimmed.isEmpty, trimmed.utf8.count <= 1024 else { return nil }
    var folded: [UInt8] = []
    for byte in trimmed.utf8 {
      switch byte {
      case 65...90: folded.append(byte + 32)
      case 97...122: folded.append(byte)
      case 45:
        guard let previous = folded.last, previous != 45 else { return nil }
        folded.append(byte)
      default: return nil
      }
    }
    guard folded.last != 45 else { return nil }
    return String(bytes: folded, encoding: .utf8)
  }
}

enum LocalWordWAVGate {
  static let maximumFileBytes = 132_096

  struct Admission {
    let duration: Double?
    let cleanupConfirmed: Bool
    let retainedHandle: FileHandle?
  }

  /// Bounded RIFF validation; no audio decoding or model work occurs here.
  static func duration(bytes: Data) -> Double? {
    guard bytes.count >= 44, bytes.count <= maximumFileBytes else { return nil }
    func tag(_ offset: Int, _ text: String) -> Bool {
      bytes[offset..<(offset + 4)].elementsEqual(text.utf8)
    }
    func little(_ offset: Int, _ count: Int) -> Int {
      (0..<count).reduce(0) { $0 | (Int(bytes[offset + $1]) << ($1 * 8)) }
    }
    guard tag(0, "RIFF"), tag(8, "WAVE"), little(4, 4) + 8 == bytes.count else { return nil }
    var offset = 12
    var formatSeen = false
    var samples: Int?
    while offset < bytes.count {
      guard bytes.count - offset >= 8 else { return nil }
      let size = little(offset + 4, 4)
      let content = offset + 8
      guard size <= bytes.count - content else { return nil }
      if tag(offset, "fmt ") {
        guard !formatSeen, size >= 16, little(content, 2) == 1,
          little(content + 2, 2) == 1, little(content + 4, 4) == 16_000,
          little(content + 8, 4) == 32_000, little(content + 12, 2) == 2,
          little(content + 14, 2) == 16
        else { return nil }
        formatSeen = true
      } else if tag(offset, "data") {
        guard samples == nil, size >= 3_200, size <= 128_000, size % 2 == 0 else { return nil }
        samples = size / 2
      }
      offset = content + size + size % 2
      guard offset <= bytes.count else { return nil }
    }
    guard formatSeen, let samples else { return nil }
    return Double(samples) / 16_000
  }

  /// Throws only before opening a handle. An unconfirmed close retains that handle.
  static func read(fileURL: URL) throws -> Admission {
    let metadata = try fileURL.resourceValues(forKeys: [
      .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey,
    ])
    guard metadata.isRegularFile == true, metadata.isSymbolicLink != true,
      let size = metadata.fileSize, size >= 44, size <= maximumFileBytes
    else { return .init(duration: nil, cleanupConfirmed: true, retainedHandle: nil) }
    let handle = try FileHandle(forReadingFrom: fileURL)
    let admitted: Double?
    do {
      let bytes = try handle.read(upToCount: maximumFileBytes) ?? Data()
      admitted = bytes.count == size ? duration(bytes: bytes) : nil
    } catch {
      admitted = nil
    }
    do {
      try handle.close()
      return .init(duration: admitted, cleanupConfirmed: true, retainedHandle: nil)
    } catch {
      return .init(duration: nil, cleanupConfirmed: false, retainedHandle: handle)
    }
  }
}
