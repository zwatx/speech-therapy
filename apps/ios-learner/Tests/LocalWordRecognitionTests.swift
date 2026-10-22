import Foundation
import XCTest

@testable import CadenceLearner

final class LocalWordRecognitionTests: XCTestCase {
  private func segment(_ text: String, start: Double = 0, duration: Double = 1)
    -> LocalWordFinalSegment
  {
    .init(text: text, start: start, duration: duration)
  }

  private func compare(_ finals: [LocalWordFinalSegment]?, word: String = "ball")
    -> LocalWordRecognitionStatus
  {
    LocalWordComparison.compare(finals: finals, expectedWord: word, audioDuration: 4)
  }

  func testExactWordCaseAndSurroundingPunctuation() {
    XCTAssertEqual(compare([segment(" \n“BALL!”\t")]), .matched)
    XCTAssertEqual(compare([segment("boat")]), .notMatched)
    XCTAssertEqual(compare([segment("Ball")], word: "BALL"), .matched)
  }

  func testNoFinalOrMultipleTokensCannotMatch() {
    XCTAssertEqual(compare(nil), .uncertain)
    XCTAssertEqual(compare([]), .uncertain)
    XCTAssertEqual(compare([segment("")]), .uncertain)
    XCTAssertEqual(compare([segment("ball boat")]), .uncertain)
    XCTAssertEqual(compare([segment("ball", duration: 1), segment("ball", start: 2)]), .uncertain)
    XCTAssertEqual(compare([segment("ba-ll")]), .notMatched)
    XCTAssertEqual(compare([segment("báll")]), .uncertain)
    XCTAssertEqual(compare([segment("ball")], word: "ball boat"), .uncertain)
  }

  func testNoAliasesOrFuzzyRepair() {
    XCTAssertEqual(compare([segment("bawl")]), .notMatched)
    XCTAssertEqual(compare([segment("balls")]), .notMatched)
    XCTAssertEqual(compare([segment("BALL")], word: "báll"), .uncertain)
    XCTAssertEqual(compare([segment("Yo-Yo.")], word: "yo-yo"), .matched)
    XCTAssertEqual(compare([segment("yoyo")], word: "yo-yo"), .notMatched)
    XCTAssertEqual(compare([segment("yo--yo")], word: "yo-yo"), .uncertain)
  }

  func testExactDuplicateRangeIsDeduplicatedButConflictingOverlapIsUncertain() {
    let final = segment("ball")
    XCTAssertEqual(compare([final, final]), .matched)
    XCTAssertEqual(compare([final, segment("boat")]), .uncertain)
    XCTAssertEqual(compare([final, segment("ball", start: 0.5)]), .uncertain)
    XCTAssertEqual(compare([final, segment("BALL")]), .uncertain)
  }

  func testMalformedRangesAndUnboundedResultsCannotMatch() {
    for final in [
      segment("ball", start: -.infinity), segment("ball", start: .nan),
      segment("ball", start: -0.1), segment("ball", duration: .infinity),
      segment("ball", duration: .nan), segment("ball", duration: -1),
      segment("ball", duration: 0), segment("ball", start: 4, duration: 1),
    ] {
      XCTAssertEqual(compare([final]), .uncertain)
    }
    XCTAssertEqual(compare(Array(repeating: segment("ball"), count: 65)), .uncertain)
    XCTAssertEqual(compare([segment(String(repeating: "b", count: 1025))]), .uncertain)
    XCTAssertEqual(
      LocalWordComparison.compare(
        finals: [segment("ball")], expectedWord: "ball", audioDuration: .nan), .uncertain)
  }

  func testReceiptKeepsExactRequestIdentityAndNoDerivedIdentity() {
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: UUID(), fileURL: URL(fileURLWithPath: "/generated/test.wav"),
      expectedWord: "Ball")
    let receipt = LocalWordRecognitionReceipt(
      request: request, status: .uncertain, cleanupConfirmed: false)
    XCTAssertEqual(receipt.request, request)
    XCTAssertEqual(receipt.operationID, request.operationID)
    XCTAssertEqual(receipt.tryID, request.tryID)
    XCTAssertEqual(receipt.fileURL, request.fileURL)
    XCTAssertEqual(receipt.expectedWord, "Ball")
    XCTAssertFalse(receipt.cleanupConfirmed)
    XCTAssertNil(receipt.wordGuess)
  }

  func testWordGuessNormalizesCompletedDifferentWordWithoutFuzzyRepair() {
    let guess = LocalWordGuess(completedText: " \n“WALL!”\t", expectedWord: " ‘BALL.’ ")
    XCTAssertEqual(guess?.word, "wall")
    XCTAssertEqual(guess?.expectedWord, "ball")
    XCTAssertEqual(LocalWordGuess(completedText: "Yo-Yo.", expectedWord: "ball")?.word, "yo-yo")
    for text in ["", "ball", "BALL!", "wall ball", "wáll", "🙂", "wa--ll", "wa2ll"] {
      XCTAssertNil(LocalWordGuess(completedText: text, expectedWord: "ball"), text)
    }
    XCTAssertNil(LocalWordGuess(completedText: "wall", expectedWord: "ball boat"))
  }

  func testWordGuessAccepts32ASCIIBytesButNeverTruncates33() {
    let boundary = String(repeating: "w", count: 32)
    XCTAssertEqual(LocalWordGuess(completedText: boundary, expectedWord: "ball")?.word, boundary)
    XCTAssertEqual(LocalWordGuess(completedText: "“\(boundary)!”", expectedWord: "ball")?.word, boundary)
    XCTAssertNil(LocalWordGuess(completedText: boundary + "w", expectedWord: "ball"))
    // The display limit withholds only the guess, never changes the existing match decision.
    XCTAssertEqual(compare([segment(boundary + "w")]), .notMatched)
  }

  func testReceiptRetainsGuessOnlyForCleanNonmatchBoundToNormalizedExpectedWord() throws {
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: UUID(), fileURL: URL(fileURLWithPath: "/generated/test.wav"),
      expectedWord: " BALL. ")
    let guess = try XCTUnwrap(LocalWordGuess(completedText: "wall", expectedWord: "ball"))
    let statuses: [LocalWordRecognitionStatus] = [
      .matched, .notMatched, .uncertain, .timedOut, .unavailable, .cancelled,
    ]
    for status in statuses {
      for cleanup in [false, true] {
        let receipt = LocalWordRecognitionReceipt(
          request: request, status: status, cleanupConfirmed: cleanup, wordGuess: guess)
        XCTAssertEqual(receipt.request, request)
        XCTAssertEqual(receipt.status, status)
        XCTAssertEqual(receipt.cleanupConfirmed, cleanup)
        XCTAssertEqual(receipt.wordGuess, cleanup && status == .notMatched ? guess : nil)
      }
    }
    let wrongExpected = try XCTUnwrap(LocalWordGuess(completedText: "wall", expectedWord: "boat"))
    XCTAssertNil(LocalWordRecognitionReceipt(
      request: request, status: .notMatched, cleanupConfirmed: true,
      wordGuess: wrongExpected).wordGuess)
    XCTAssertNil(LocalWordRecognitionReceipt(
      request: request, status: .notMatched, cleanupConfirmed: true).wordGuess)
  }

  func testWAVGateAcceptsBoundariesAndRejectsMalformedFormatAndSizes() {
    XCTAssertEqual(LocalWordWAVGate.duration(bytes: wav(samples: 1600)), 0.1)
    XCTAssertEqual(LocalWordWAVGate.duration(bytes: wav(samples: 64_000)), 4)
    XCTAssertNil(LocalWordWAVGate.duration(bytes: wav(samples: 1599)))
    XCTAssertNil(LocalWordWAVGate.duration(bytes: wav(samples: 64_001)))
    XCTAssertNil(LocalWordWAVGate.duration(bytes: wav(samples: 1600, channels: 2)))
    XCTAssertNil(LocalWordWAVGate.duration(bytes: wav(samples: 1600, rate: 44_100)))
    XCTAssertNil(LocalWordWAVGate.duration(bytes: wav(samples: 1600, bits: 32)))
    XCTAssertNil(LocalWordWAVGate.duration(bytes: Data("bad wav".utf8)))
    var truncated = wav(samples: 1600)
    truncated.removeLast()
    XCTAssertNil(LocalWordWAVGate.duration(bytes: truncated))
    var overflow = wav(samples: 1600)
    overflow.replaceSubrange(40..<44, with: [255, 255, 255, 255])
    XCTAssertNil(LocalWordWAVGate.duration(bytes: overflow))
    var extra = wav(samples: 1600)
    extra.append(0)
    XCTAssertNil(LocalWordWAVGate.duration(bytes: extra))
  }

  func testWAVGateRejectsDuplicateDataAndNonPCM() {
    var duplicate = wav(samples: 1600)
    duplicate.append(contentsOf: "data".utf8)
    duplicate.append(contentsOf: [0, 0, 0, 0])
    let size = duplicate.count - 8
    for index in 0..<4 { duplicate[4 + index] = UInt8((size >> (index * 8)) & 255) }
    XCTAssertNil(LocalWordWAVGate.duration(bytes: duplicate))
    var nonPCM = wav(samples: 1600)
    nonPCM[20] = 3
    XCTAssertNil(LocalWordWAVGate.duration(bytes: nonPCM))
  }

  func testBoundedFileAdmissionClosesHandleAndDoesNotChangeSourceBytes() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: directory) }
    let url = directory.appendingPathComponent("generated.wav")
    let original = wav(samples: 1600)
    try original.write(to: url)
    let admission = try LocalWordWAVGate.read(fileURL: url)
    XCTAssertEqual(admission.duration, 0.1)
    XCTAssertTrue(admission.cleanupConfirmed)
    XCTAssertNil(admission.retainedHandle)
    XCTAssertEqual(try Data(contentsOf: url), original)
    try Data(repeating: 0, count: LocalWordWAVGate.maximumFileBytes + 1).write(to: url)
    let oversized = try LocalWordWAVGate.read(fileURL: url)
    XCTAssertNil(oversized.duration)
    XCTAssertTrue(oversized.cleanupConfirmed)
  }

  @MainActor
  func testAlreadyCancelledCheckReturnsExactReceiptWithoutReadinessOrFileAccess() async {
    let ownership = ProcessAudioFileOwnership()
    let recognizer = SystemLocalWordRecognizer(ownership: ownership)
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: UUID(),
      fileURL: URL(fileURLWithPath: "/generated/missing-\(UUID()).wav"), expectedWord: "ball")
    let task = Task { @MainActor in
      // The task cannot enter check until this MainActor test suspends.
      await recognizer.check(request: request)
    }
    task.cancel()
    let receipt = await task.value
    XCTAssertEqual(receipt.request, request)
    XCTAssertEqual(receipt.status, .cancelled)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertTrue(ownership.protectedURLs.isEmpty)
  }

  private func wav(samples: Int, channels: Int = 1, rate: Int = 16_000, bits: Int = 16) -> Data {
    var bytes = Data()
    func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
    func little(_ value: Int, _ count: Int) {
      for index in 0..<count { bytes.append(UInt8((value >> (index * 8)) & 255)) }
    }
    text("RIFF")
    little(36 + samples * 2, 4)
    text("WAVEfmt ")
    little(16, 4)
    little(1, 2)
    little(channels, 2)
    little(rate, 4)
    little(rate * 2, 4)
    little(2, 2)
    little(bits, 2)
    text("data")
    little(samples * 2, 4)
    bytes.append(Data(repeating: 0, count: samples * 2))
    return bytes
  }
}
