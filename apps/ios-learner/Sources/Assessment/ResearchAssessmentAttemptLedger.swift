#if DEBUG
  import Foundation

  enum ResearchAssessmentAttemptStartKind: String {
    case recordRequested = "record_requested"
    case preflightRejected = "preflight_rejected"
  }

  enum ResearchAssessmentTerminalOutcome: String, Hashable {
    case unavailable
    case processedUnverified = "processed_unverified"
    case admissionProcessed = "admission_processed"
  }

  enum ResearchAssessmentTerminalReason: String, Hashable {
    case permissionDenied = "permission_denied"
    case setupChanged = "setup_changed"
    case setupReset = "setup_reset"
    case sessionEnded = "session_ended"
    case cancelled
    case becameInactive = "became_inactive"
    case backgrounded
    case audioInterrupted = "audio_interrupted"
    case recordingInterrupted = "recording_interrupted"
    case microphoneUnavailable = "microphone_unavailable"
    case cleanupBlocked = "cleanup_blocked"
    case captureTooShort = "capture_too_short"
    case captureTooLong = "capture_too_long"
    case captureTooQuiet = "capture_too_quiet"
    case promptMatchUnverified = "prompt_match_unverified"
    case admissionProcessed = "admission_processed"
    case admissionRejected = "admission_rejected"
    case serviceCleanupUnconfirmed = "service_cleanup_unconfirmed"
    case invalidRequest = "invalid_request"
    case ageOutOfRange = "age_out_of_range"
    case unsupportedTarget = "unsupported_target"
    case invalidAudio = "invalid_audio"
    case audioTooLong = "audio_too_long"
    case silence
    case clipping
    case modelUnavailable = "model_unavailable"
    case inferenceFailed = "inference_failed"
    case timeout
    case busy
    case serviceUnavailable = "service_unavailable"
    case invalidResponse = "invalid_response"
  }

  /// Session-lifetime memory only; no prompt, age, identity, audio or prediction is retained.
  /// Evicting old rows does not change the all-attempt denominator or terminal/reason counts.
  struct ResearchAssessmentAttemptLedger {
    struct Row {
      let id: UUID
      let startKind: ResearchAssessmentAttemptStartKind
      let previousAttemptId: UUID?
      let retryIndex: Int
      var terminalOutcome: ResearchAssessmentTerminalOutcome?
      var terminalReason: ResearchAssessmentTerminalReason?
      var elapsedSeconds: Double?
      var learnerFindingEligible: Bool { false }
    }
    static let rowLimit = 100
    private(set) var rows: [Row] = []
    private(set) var droppedRowCount = 0
    private(set) var totalStarted = 0
    private(set) var totalTerminal = 0
    private(set) var outcomeCounts: [ResearchAssessmentTerminalOutcome: Int] = [:]
    private(set) var reasonCounts: [ResearchAssessmentTerminalReason: Int] = [:]
    private var retryParent: (id: UUID, index: Int)?
    private var activeStart: (id: UUID, instant: ContinuousClock.Instant)?

    mutating func start(id: UUID, kind: ResearchAssessmentAttemptStartKind = .recordRequested) {
      totalStarted += 1
      let index = retryParent.map { $0.index + 1 } ?? 0
      rows.append(
        Row(id: id, startKind: kind, previousAttemptId: retryParent?.id, retryIndex: index))
      if rows.count > Self.rowLimit {
        let dropped = rows.count - Self.rowLimit
        rows.removeFirst(dropped)
        droppedRowCount += dropped
      }
      retryParent = (id, index)
      activeStart = (id, .now)
    }

    mutating func resetRetryChain() { retryParent = nil }

    mutating func finish(
      id: UUID, reason: ResearchAssessmentTerminalReason,
      outcome: ResearchAssessmentTerminalOutcome = .unavailable
    ) {
      guard let activeStart, activeStart.id == id,
        let index = rows.firstIndex(where: { $0.id == id }),
        rows[index].terminalOutcome == nil
      else { return }
      let elapsed = activeStart.instant.duration(to: .now).components
      rows[index].terminalOutcome = outcome
      rows[index].terminalReason = reason
      rows[index].elapsedSeconds = Double(elapsed.seconds) + Double(elapsed.attoseconds) / 1e18
      totalTerminal += 1
      outcomeCounts[outcome, default: 0] += 1
      reasonCounts[reason, default: 0] += 1
      self.activeStart = nil
    }

    mutating func finishActive(
      reason: ResearchAssessmentTerminalReason,
      outcome: ResearchAssessmentTerminalOutcome = .unavailable
    ) {
      guard let activeStart else { return }
      finish(id: activeStart.id, reason: reason, outcome: outcome)
    }
  }
#endif
