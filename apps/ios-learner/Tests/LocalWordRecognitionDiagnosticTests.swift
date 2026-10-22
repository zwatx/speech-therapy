import Foundation
import XCTest

@testable import CadenceLearner

final class LocalWordRecognitionDiagnosticTests: XCTestCase {
  private func segment(_ text: String, start: Double = 0, duration: Double = 1)
    -> LocalWordFinalSegment
  {
    .init(text: text, start: start, duration: duration)
  }
  func testClosedDiagnosticComparisonReasonsPreserveStatusAndDuplicateRules() {
    let cases:
      [(
        [LocalWordFinalSegment]?, String, Double,
        LocalWordRecognitionDiagnostic.Reason, LocalWordRecognitionStatus
      )] = [
        (nil, "ball", 4, .comparisonEmpty, .uncertain),
        ([], "ball", 4, .comparisonEmpty, .uncertain),
        (Array(repeating: segment("ball"), count: 65), "ball", 4, .boundedLimit, .uncertain),
        ([segment("ball")], "ball", .nan, .invalidAudioDuration, .uncertain),
        ([segment("ball")], "ball boat", 4, .invalidExpectedWord, .uncertain),
        ([segment(String(repeating: "b", count: 1025))], "ball", 4, .boundedLimit, .uncertain),
        ([segment("ball", start: -1)], "ball", 4, .comparisonRange, .uncertain),
        (
          [segment("ball"), segment("boat", start: 0.5)], "ball", 4,
          .comparisonOverlap, .uncertain
        ),
        ([segment("ball boat")], "ball", 4, .comparisonNonSingleWord, .uncertain),
        ([segment("boat")], "ball", 4, .comparisonMismatch, .notMatched),
        ([segment("BALL"), segment("BALL")], "ball", 4, .comparisonMatched, .matched),
      ]
    for (finals, word, duration, reason, status) in cases {
      let result = LocalWordComparison.diagnose(
        finals: finals, expectedWord: word, audioDuration: duration)
      XCTAssertEqual(result.reason, reason)
      XCTAssertEqual(result.status, status)
      XCTAssertEqual(
        LocalWordComparison.compare(finals: finals, expectedWord: word, audioDuration: duration),
        status)
    }
  }

  func testDiagnosticRecorderRejectsWrongOperationAndTryAndNewOperationStartsEmpty() {
    let operationID = UUID()
    let tryID = UUID()
    let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
    recorder.record(
      operationID: UUID(), tryID: tryID, stage: .analyzeReached,
      reason: .analysisFailed, speechFailure: .noModel)
    recorder.record(
      operationID: operationID, tryID: UUID(), stage: .analyzeReturned,
      reason: .comparisonMatched, speechFailure: .moduleOutputFailed)
    XCTAssertEqual(recorder.snapshot(), .init(operationID: operationID, tryID: tryID))
    recorder.record(
      operationID: operationID, tryID: tryID, stage: .fileOpened,
      reason: .formatRejected, speechFailure: .unexpectedAudioFormat)
    let recorded = recorder.snapshot()
    XCTAssertEqual(recorded.stages, [.fileOpened])
    XCTAssertEqual(recorded.reasons, [.formatRejected])
    XCTAssertEqual(recorded.speechFailures, [.unexpectedAudioFormat])
    let nextID = UUID()
    let next = LocalWordDiagnosticRecorder(operationID: nextID, tryID: tryID)
    next.record(operationID: operationID, tryID: tryID, reason: .deadline)
    XCTAssertEqual(next.snapshot(), .init(operationID: nextID, tryID: tryID))
    XCTAssertEqual(recorder.snapshot(), recorded)
  }
}
