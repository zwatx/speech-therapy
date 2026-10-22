import Foundation
import XCTest

@testable import CadenceLearner

final class LocalWordAvailabilityFeedbackTests: XCTestCase {
  private let stages: Set<LocalWordRecognitionDiagnostic.Stage> = [
    .admitted, .fileOpenReached, .fileOpened, .formatValidated, .formatSelectionReached, .joined,
  ]

  private func recorder(
    operationID: UUID, tryID: UUID,
    stages: Set<LocalWordRecognitionDiagnostic.Stage>? = nil,
    reasons: Set<LocalWordRecognitionDiagnostic.Reason> = [.formatUnavailable, .cancellation],
    trigger: LocalWordRecognitionDiagnostic.TerminalTrigger = .analysisFailure,
    override: LocalWordRecognitionDiagnostic.ReceiptOverride? = nil,
    failure: LocalWordRecognitionDiagnostic.SpeechFailure? = nil
  ) -> LocalWordDiagnosticRecorder {
    let result = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
    for stage in stages ?? self.stages {
      result.record(operationID: operationID, tryID: tryID, stage: stage)
    }
    for reason in reasons {
      result.record(operationID: operationID, tryID: tryID, reason: reason)
    }
    result.record(
      operationID: operationID, tryID: tryID, speechFailure: failure, terminalTrigger: trigger,
      receiptOverride: override)
    return result
  }

  func testExactPreAnalysisFormatFailureIsUnavailableAndPreservesCleanupAndDiagnostic() {
    let reasonSets: [Set<LocalWordRecognitionDiagnostic.Reason>] = [
      [.formatUnavailable], [.formatUnavailable, .cancellation],
    ]
    for reasons in reasonSets {
      for cleanup in [false, true] {
        for streamFinished in [false, true] {
          let operationID = UUID()
          let tryID = UUID()
          let diagnostic = recorder(
            operationID: operationID, tryID: tryID,
            stages: streamFinished ? stages.union([.resultStreamFinished]) : stages,
            reasons: reasons)
          let before = diagnostic.snapshot()
          let receipt = LocalWordReceiptFinalization.complete(
            .init(status: .uncertain, cleanupConfirmed: cleanup), parentCancelled: false,
            cancellationRequested: false, operationID: operationID, tryID: tryID,
            diagnostic: diagnostic)
          XCTAssertEqual(receipt.status, .unavailable)
          XCTAssertEqual(receipt.cleanupConfirmed, cleanup)
          XCTAssertEqual(diagnostic.snapshot(), before)
        }
      }
    }
  }

  func testWrongOperationOrTryAndMissingOrPostAnalysisStagesCannotRemap() {
    let operationID = UUID()
    let tryID = UUID()
    let wrongIdentities = [
      recorder(operationID: UUID(), tryID: tryID),
      recorder(operationID: operationID, tryID: UUID()),
    ]
    let missing = stages.map {
      recorder(operationID: operationID, tryID: tryID, stages: stages.subtracting([$0]))
    }
    let prohibited: [LocalWordRecognitionDiagnostic.Stage] = [
      .formatSelected, .conversionReached, .conversionReturned, .analyzeReached,
      .analyzeReturned, .finalizeReached, .finalizeReturned, .comparisonReached,
    ]
    let extra = prohibited.map {
      recorder(operationID: operationID, tryID: tryID, stages: stages.union([$0]))
    }
    for diagnostic in wrongIdentities + missing + extra {
      let receipt = LocalWordReceiptFinalization.complete(
        .init(status: .uncertain, cleanupConfirmed: true), parentCancelled: false,
        cancellationRequested: false, operationID: operationID, tryID: tryID,
        diagnostic: diagnostic)
      XCTAssertEqual(receipt.status, .uncertain)
      XCTAssertTrue(receipt.cleanupConfirmed)
    }
  }

  func testOtherReasonsFailuresAndTerminalTriggersCannotRemap() {
    let operationID = UUID()
    let tryID = UUID()
    var candidates: [LocalWordDiagnosticRecorder] = []
    for trigger in LocalWordRecognitionDiagnostic.TerminalTrigger.allCases
    where trigger != .analysisFailure {
      candidates.append(recorder(operationID: operationID, tryID: tryID, trigger: trigger))
    }
    for reason in LocalWordRecognitionDiagnostic.Reason.allCases
    where reason != .formatUnavailable && reason != .cancellation {
      candidates.append(
        recorder(operationID: operationID, tryID: tryID, reasons: [.formatUnavailable, reason]))
    }
    candidates.append(recorder(operationID: operationID, tryID: tryID, reasons: [.cancellation]))
    candidates.append(recorder(operationID: operationID, tryID: tryID, failure: .noModel))
    for override in LocalWordRecognitionDiagnostic.ReceiptOverride.allCases {
      candidates.append(recorder(operationID: operationID, tryID: tryID, override: override))
    }
    for diagnostic in candidates {
      XCTAssertEqual(
        LocalWordReceiptFinalization.complete(
          .init(status: .uncertain, cleanupConfirmed: false), parentCancelled: false,
          cancellationRequested: false, operationID: operationID, tryID: tryID,
          diagnostic: diagnostic
        ).status, .uncertain)
    }
  }

  func testFinalCancellationKeepsPrecedenceAndPreservesPrimaryTriggerAndCleanup() {
    for parentCancelled in [false, true] {
      for cancellationRequested in [false, true]
      where parentCancelled || cancellationRequested {
        for cleanup in [false, true] {
          let operationID = UUID()
          let tryID = UUID()
          let diagnostic = recorder(operationID: operationID, tryID: tryID)
          let receipt = LocalWordReceiptFinalization.complete(
            .init(status: .uncertain, cleanupConfirmed: cleanup),
            parentCancelled: parentCancelled, cancellationRequested: cancellationRequested,
            operationID: operationID, tryID: tryID, diagnostic: diagnostic)
          XCTAssertEqual(receipt.status, .cancelled)
          XCTAssertEqual(receipt.cleanupConfirmed, cleanup)
          XCTAssertEqual(diagnostic.snapshot().terminalTrigger, .analysisFailure)
          XCTAssertEqual(
            diagnostic.snapshot().receiptOverride,
            parentCancelled ? .parentCancellation : .explicitCancellation)
        }
      }
    }
  }

  func testCompletedComparisonStatusesAndOtherWorkerStatusesRemainUnchanged() {
    let comparisons: [([LocalWordFinalSegment]?, LocalWordRecognitionStatus)] = [
      (nil, .uncertain),
      ([.init(text: "ball", start: 0, duration: 1)], .matched),
      ([.init(text: "boat", start: 0, duration: 1)], .notMatched),
    ]
    for (segments, expected) in comparisons {
      let operationID = UUID()
      let tryID = UUID()
      let comparison = LocalWordComparison.diagnose(
        finals: segments, expectedWord: "ball", audioDuration: 2)
      XCTAssertEqual(comparison.status, expected)
      let diagnostic = recorder(
        operationID: operationID, tryID: tryID, stages: stages.union([.comparisonReached]),
        reasons: [comparison.reason], trigger: .normal)
      let receipt = LocalWordReceiptFinalization.complete(
        .init(status: comparison.status, cleanupConfirmed: true), parentCancelled: false,
        cancellationRequested: false, operationID: operationID, tryID: tryID,
        diagnostic: diagnostic)
      XCTAssertEqual(receipt.status, expected)
    }
    for status: LocalWordRecognitionStatus in [.matched, .notMatched, .unavailable, .cancelled] {
      let operationID = UUID()
      let tryID = UUID()
      let receipt = LocalWordReceiptFinalization.complete(
        .init(status: status, cleanupConfirmed: false), parentCancelled: false,
        cancellationRequested: false, operationID: operationID, tryID: tryID,
        diagnostic: recorder(operationID: operationID, tryID: tryID))
      XCTAssertEqual(receipt.status, status)
      XCTAssertFalse(receipt.cleanupConfirmed)
    }
  }
}
