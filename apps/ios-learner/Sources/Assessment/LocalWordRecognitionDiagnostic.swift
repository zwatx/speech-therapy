import Foundation

/// Fixed, ephemeral categories only: no transcript, file URL, error payload or audio values.
struct LocalWordRecognitionDiagnostic: Equatable, Sendable {
  enum Stage: String, CaseIterable, Sendable {
    case admitted, fileOpenReached, fileOpened, formatValidated
    case formatSelectionReached, formatSelected, conversionReached, conversionReturned
    case analyzeReached, analyzeReturned, finalizeReached, finalizeReturned
    case resultStreamFinished, comparisonReached, joined
  }
  enum Reason: String, CaseIterable, Sendable {
    case unsupportedPlatform, invalidRequest, unsupportedLocale, assetsNotInstalled
    case ownershipUnavailable, admissionCleanupUnconfirmed, admissionReadFailed
    case admissionRejected, fileOpenFailed, formatRejected, analysisFailed, finalizationFailed
    case formatUnavailable, conversionFailed
    case resultStreamFailed, boundedLimit, timing, comparisonEmpty, comparisonRange
    case comparisonOverlap, comparisonNonSingleWord, comparisonMismatch, comparisonMatched
    case invalidExpectedWord, invalidAudioDuration, deadline, cancellation
  }
  enum SpeechFailure: String, CaseIterable, Sendable {
    case unexpectedAudioFormat, incompatibleAudioFormats, noModel, assetLocaleNotAllocated
    case moduleOutputFailed, insufficientResources, cannotConfigureAudioSystem
    case internalServiceError, audioReadFailed, timeout, missingParameter
    case unmappedSpeechError, nonSpeechError
  }
  enum TerminalTrigger: String, CaseIterable, Sendable {
    case normal, analysisFailure, consumerFailure, deadline, explicitCancellation,
      parentCancellation
  }
  enum ReceiptOverride: String, CaseIterable, Sendable {
    case parentCancellation, explicitCancellation
  }
  let operationID: UUID
  let tryID: UUID
  var terminalTrigger: TerminalTrigger?
  var receiptOverride: ReceiptOverride?
  var stages: Set<Stage> = []
  var reasons: Set<Reason> = []
  var speechFailures: Set<SpeechFailure> = []
}

/// The worker and consumer can report concurrently. Identity checks reject stale callbacks;
/// sets are bounded by the closed enums and retain no ordered timing or numeric voice data.
final class LocalWordDiagnosticRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var diagnostic: LocalWordRecognitionDiagnostic
  init(operationID: UUID, tryID: UUID) {
    diagnostic = .init(operationID: operationID, tryID: tryID)
  }
  func record(
    operationID: UUID, tryID: UUID,
    stage: LocalWordRecognitionDiagnostic.Stage? = nil,
    reason: LocalWordRecognitionDiagnostic.Reason? = nil,
    speechFailure: LocalWordRecognitionDiagnostic.SpeechFailure? = nil,
    terminalTrigger: LocalWordRecognitionDiagnostic.TerminalTrigger? = nil,
    receiptOverride: LocalWordRecognitionDiagnostic.ReceiptOverride? = nil
  ) {
    lock.lock()
    defer { lock.unlock() }
    guard diagnostic.operationID == operationID, diagnostic.tryID == tryID else { return }
    if let terminalTrigger { diagnostic.terminalTrigger = terminalTrigger }
    if let receiptOverride { diagnostic.receiptOverride = receiptOverride }
    if let stage { diagnostic.stages.insert(stage) }
    if let reason { diagnostic.reasons.insert(reason) }
    if let speechFailure { diagnostic.speechFailures.insert(speechFailure) }
  }
  func snapshot() -> LocalWordRecognitionDiagnostic {
    lock.lock()
    defer { lock.unlock() }
    return diagnostic
  }
}

/// Shared by the real provider and deterministic worker tests. This adds no suspension
/// or cleanup decision; parent cancellation keeps the existing predicate's precedence.
enum LocalWordReceiptFinalization {
  static func complete(
    _ completion: LocalWordWorkerCompletion, parentCancelled: Bool,
    cancellationRequested: Bool, operationID: UUID, tryID: UUID,
    diagnostic: LocalWordDiagnosticRecorder
  ) -> LocalWordWorkerCompletion {
    let override: LocalWordRecognitionDiagnostic.ReceiptOverride? =
      parentCancelled
      ? .parentCancellation
      : cancellationRequested ? .explicitCancellation : nil
    if let override {
      diagnostic.record(operationID: operationID, tryID: tryID, receiptOverride: override)
    }
    var status = completion.status
    if parentCancelled || cancellationRequested {
      status = .cancelled
    } else if completion.status == .uncertain {
      let evidence = diagnostic.snapshot()
      let requiredStages: Set<LocalWordRecognitionDiagnostic.Stage> = [
        .admitted, .fileOpenReached, .fileOpened, .formatValidated, .formatSelectionReached,
        .joined,
      ]
      // A stream can finish during supervisor teardown; neither it nor cancellation alone
      // is evidence of failed voice matching. Require the exact pre-analysis failure path.
      let allowedStages = requiredStages.union([.resultStreamFinished])
      let allowedReasons: Set<LocalWordRecognitionDiagnostic.Reason> = [
        .formatUnavailable, .cancellation,
      ]
      if evidence.operationID == operationID, evidence.tryID == tryID,
        evidence.terminalTrigger == .analysisFailure, evidence.receiptOverride == nil,
        evidence.stages.isSuperset(of: requiredStages),
        evidence.stages.isSubset(of: allowedStages),
        evidence.reasons.contains(.formatUnavailable),
        evidence.reasons.isSubset(of: allowedReasons), evidence.speechFailures.isEmpty
      {
        status = .unavailable
      }
    }
    return .init(status: status, cleanupConfirmed: completion.cleanupConfirmed)
  }
}
