#if DEBUG
  import Combine
  import Foundation

  enum ResearchAssessmentPhase: Equatable {
    case setup
    case ready
    case requestingPermission
    case recording
    case processing
    case unavailable(title: String, detail: String)
    case permissionDenied
    case cleanupBlocked
    case ended
  }

  /// A local research check never exposes a probability or a learner pronunciation finding.
  @MainActor
  final class ResearchAssessmentSession: ObservableObject {
    // Start/terminal bookkeeping commits before the corresponding published phase.
    // Publishing a mutable ledger in willSet would expose its previous active attempt to reentry.
    private(set) var attemptLedger = ResearchAssessmentAttemptLedger()
    @Published private(set) var phase: ResearchAssessmentPhase = .setup
    @Published var ageYears: Int? {
      didSet { if ageYears != oldValue { attemptLedger.resetRetryChain() } }
    }
    @Published var selectedEntry: PracticeLibraryEntry? {
      didSet { if selectedEntry != oldValue { attemptLedger.resetRetryChain() } }
    }
    @Published var localProcessingEnabled = false {
      didSet { if !localProcessingEnabled { attemptLedger.resetRetryChain() } }
    }

    let admissionMode: Bool

    private let capturer: any AudioCapturing
    private let processor: any ResearchAssessmentProcessing
    private let assessor = CaptureQualityAssessor()
    @Published private var cleanupSnapshot = CaptureCleanupState.idle
    /// Authoritative committed state; notifications drain serially across explicit reentry.
    var captureCleanupState: CaptureCleanupState { captureCleanup.state }
    private var isRefreshingCleanup = false
    private var cleanupRefreshPending = false
    private var cleanupRetryRequested = false
    @Published private(set) var captureDisabledForVisit = false
    private let captureCleanup: CaptureVisitCleanup
    private var pendingRecording: CapturedRecording? { captureCleanup.recording }
    var captureCleanupRetryIDs: [UUID] { captureCleanup.retryIDs }
    var canLeaveWithFileWarning: Bool { captureCleanup.canLeaveWithFileWarning }
    var requiresCaptureCleanupBeforeDeparture: Bool { captureCleanup.hasRequestedResources }
    var captureCleanupDetail: String {
      if captureCleanupState.hasHardwareIssue {
        return "Microphone cleanup is not confirmed. Retry cleanup before leaving or recording."
      }
      if captureCleanupState.hasFileIssue {
        return canLeaveWithFileWarning
          ? "A recording is still retained on this device. Retry cleanup, or choose Close again to leave with this warning."
          : "A recording could not be removed. Retry cleanup before continuing."
      }
      if captureCleanup.hasUnidentifiedFailure {
        return "Cleanup could not be confirmed. Keep this screen open while cleanup is resolved."
      }
      return "Recording is disabled for this visit. You can close this lab and reopen it."
    }
    private var recordingGeneration: UUID?
    private var processingGeneration: UUID?
    private var processTask: Task<Void, Never>?
    private var cleanupBlocked = false
    private var closeRequested = false
    private var didEnd = false
    private var attempt: (id: UUID, entry: PracticeLibraryEntry, age: Int)?

    init(
      capturer: (any AudioCapturing)? = nil,
      processor: (any ResearchAssessmentProcessing)? = nil,
      admissionMode: Bool? = nil,
      hardwareOwnership: AudioHardwareOwnership = .shared,
      fileOwnership: ProcessAudioFileOwnership = .shared
    ) {
      #if targetEnvironment(simulator)
        self.admissionMode =
          admissionMode ?? ProcessInfo.processInfo.arguments.contains("-CadenceAdmissionMode")
      #else
        self.admissionMode = false
      #endif
      let capturer =
        capturer
        ?? SystemAudioCapturer(
          fileOwnership: fileOwnership, hardwareOwnership: hardwareOwnership)
      self.capturer = capturer
      captureCleanup = CaptureVisitCleanup(
        capturer: capturer, hardware: hardwareOwnership, files: fileOwnership)
      #if targetEnvironment(simulator)
        self.processor =
          processor
          ?? (self.admissionMode
            ? ResearchAdmissionClient() : ResearchAssessmentClient())
      #else
        self.processor = processor ?? ResearchAssessmentClient()
      #endif
      captureCleanup.didChange = { [weak self] in self?.refreshCaptureCleanup() }
      refreshCaptureCleanup()
    }

    private func refreshCaptureCleanup() {
      cleanupRefreshPending = true
      guard !isRefreshingCleanup else { return }
      isRefreshingCleanup = true
      defer { isRefreshingCleanup = false }
      while cleanupRefreshPending {
        cleanupRefreshPending = false
        let restoreReady = cleanupRetryRequested
        cleanupRetryRequested = false
        let state = captureCleanup.state
        if cleanupSnapshot != state { cleanupSnapshot = state }
        if captureDisabledForVisit != captureCleanup.disabledForVisit {
          captureDisabledForVisit = captureCleanup.disabledForVisit
        }
        if didEnd {
          if phase != .ended { phase = .ended }
        } else if captureCleanup.hasIssue || captureCleanup.disabledForVisit {
          blockCleanup()
        } else if restoreReady, !closeRequested, phase != .ended, !captureCleanup.blocksRecording {
          cleanupBlocked = false
          phase = .setup
          prepare(accountForPreflightRejection: false, refreshCleanup: false)
        }
      }
    }

    func retryCaptureCleanup(operationID: UUID) {
      guard captureCleanup.canRetry(operationID: operationID) else { return }
      recordingGeneration = nil
      processingGeneration = nil
      attempt = nil
      processTask?.cancel()
      processTask = nil
      cleanupRetryRequested = true
      _ = captureCleanup.retry(operationID: operationID)
      refreshCaptureCleanup()
    }

    /// Explicit Continue can reject a complete, opted-in setup without starting audio.
    /// Internal readiness checks use the same validation without adding attempts.
    func prepare() { prepare(accountForPreflightRejection: true) }

    private func prepare(accountForPreflightRejection: Bool, refreshCleanup: Bool = true) {
      if refreshCleanup { refreshCaptureCleanup() }
      guard !closeRequested, !cleanupBlocked, !captureCleanup.blocksRecording, phase != .ended,
        phase != .recording,
        phase != .processing, phase != .requestingPermission
      else { return }
      guard let ageYears else {
        phase = .setup
        return
      }
      guard (6...12).contains(ageYears) else {
        recordPreflightRejection(.ageOutOfRange, enabled: accountForPreflightRejection)
        phase = .unavailable(
          title: "Age outside research scope",
          detail: "This local check supports declared ages 6–12. No recording was made.")
        return
      }
      guard let selectedEntry else {
        phase = .setup
        return
      }
      guard selectedEntry.targetPhone != "ZH",
        PracticeLibrary.entries().contains(selectedEntry),
        (try? ResearchAssessmentClient.prompt(for: selectedEntry)) != nil
      else {
        recordPreflightRejection(.unsupportedTarget, enabled: accountForPreflightRejection)
        phase = .unavailable(
          title: "Sound unavailable",
          detail:
            "This prompt is outside the local research model's supported targets. No recording was made."
        )
        return
      }
      guard localProcessingEnabled else {
        phase = .setup
        return
      }
      phase = .ready
    }

    private func recordPreflightRejection(
      _ reason: ResearchAssessmentTerminalReason, enabled: Bool
    ) {
      guard enabled, localProcessingEnabled, ageYears != nil, selectedEntry != nil else { return }
      let id = UUID()
      attemptLedger.start(id: id, kind: .preflightRejected)
      attemptLedger.finish(id: id, reason: reason)
    }

    func startRecording() async {
      refreshCaptureCleanup()
      guard !closeRequested, !cleanupBlocked, !captureCleanup.blocksRecording,
        phase == .ready || phase == .permissionDenied
      else { return }
      prepare(accountForPreflightRejection: false)
      guard phase == .ready, let entry = selectedEntry, let age = ageYears else { return }
      let generation = UUID()
      recordingGeneration = generation
      attemptLedger.start(id: generation)
      phase = .requestingPermission
      let granted = await capturer.requestPermission()
      guard recordingGeneration == generation, phase == .requestingPermission else { return }
      // A permission dialog can outlive the setup that requested it.
      guard localProcessingEnabled, selectedEntry == entry, ageYears == age else {
        recordingGeneration = nil
        attemptLedger.finish(id: generation, reason: .setupChanged)
        phase = .setup
        prepare(accountForPreflightRejection: false)
        return
      }
      guard granted else {
        attemptLedger.finish(id: generation, reason: .permissionDenied)
        recordingGeneration = nil
        phase = .permissionDenied
        return
      }
      do {
        captureCleanup.willStart()
        try capturer.start { [weak self] successfully in
          guard let self, self.recordingGeneration == generation, self.phase == .recording else {
            return
          }
          if successfully {
            self.stopRecording()
          } else if self.removeTemporaryAudio(reason: .recordingInterrupted) {
            self.phase = .unavailable(
              title: "Recording interrupted",
              detail:
                "Please record the word again. Nothing was sent, and the recording was deleted.")
          }
        }
        guard recordingGeneration == generation, !closeRequested, !captureCleanup.hasIssue,
          !captureCleanup.disabledForVisit
        else { return }
        attempt = (generation, entry, age)
        phase = .recording
      } catch {
        captureCleanup.failed(error, duringStart: true)
        if case AudioCaptureError.hardwareBusy = error {
          recordingGeneration = nil
          attemptLedger.finish(id: generation, reason: .microphoneUnavailable)
          phase = .unavailable(
            title: "Audio is in use",
            detail: "Try again after the other audio finishes. No recording was made.")
          return
        }
        refreshCaptureCleanup()
        if captureCleanup.hasIssue || captureCleanup.disabledForVisit {
          _ = removeTemporaryAudio(reason: .cleanupBlocked)
          blockCleanup()
        } else if removeTemporaryAudio(reason: .microphoneUnavailable) {
          phase = .unavailable(
            title: "Microphone unavailable",
            detail:
              "The microphone could not start. Nothing was sent, and any temporary recording was deleted."
          )
        }
      }
    }

    func stopRecording() {
      guard phase == .recording, let attempt else { return }
      recordingGeneration = nil
      do {
        let recording = try capturer.stop()
        captureCleanup.captured(recording)
        guard recording.summary.duration.isFinite, recording.summary.averagePower.isFinite else {
          if removeTemporaryAudio(reason: .invalidAudio) {
            phase = .unavailable(
              title: "Recording unavailable",
              detail:
                "The recording could not be measured. Nothing was sent, and the recording was deleted."
            )
          }
          return
        }
        if case .retry(let coaching) = assessor.assess(recording.summary) {
          let reason: ResearchAssessmentTerminalReason =
            recording.summary.duration < assessor.minimumDuration
            ? .captureTooShort
            : (recording.summary.duration > assessor.maximumDuration
              ? .captureTooLong : .captureTooQuiet)
          if removeTemporaryAudio(reason: reason) {
            let advice =
              recording.summary.duration < assessor.minimumDuration
              ? "Tap Record, say the word at your own pace, then tap Stop."
              : coaching.detail
            phase = .unavailable(
              title: coaching.title,
              detail: "\(advice) Nothing was sent, and the recording was deleted.")
          }
          return
        }
        beginProcessing(recording, entry: attempt.entry, age: attempt.age, attemptId: attempt.id)
      } catch {
        captureCleanup.failed(error)
        refreshCaptureCleanup()
        if captureCleanup.hasIssue || captureCleanup.disabledForVisit {
          _ = removeTemporaryAudio(reason: .cleanupBlocked)
          blockCleanup()
        } else if removeTemporaryAudio(reason: .invalidAudio) {
          phase = .unavailable(
            title: "Recording unavailable",
            detail:
              "The recording could not be read. Nothing was sent, and the recording was deleted.")
        }
      }
    }

    func retry() {
      guard !cleanupBlocked else { return }
      switch phase {
      case .unavailable, .permissionDenied:
        if removeTemporaryAudio() {
          phase = .setup
          prepare(accountForPreflightRejection: false)
        }
      default: break
      }
    }

    func cancelProcessing() {
      guard phase == .processing else { return }
      if removeTemporaryAudio(reason: .cancelled) {
        phase = .setup
        prepare(accountForPreflightRejection: false)
      }
    }

    func resetSetup() {
      if phase == .ended, !captureCleanup.blocksRecording {
        closeRequested = false
        didEnd = false
      }
      attemptLedger.resetRetryChain()
      localProcessingEnabled = false
      if removeTemporaryAudio(reason: .setupReset) { phase = .setup }
    }

    @discardableResult
    func end() -> Bool {
      closeRequested = true
      recordingGeneration = nil
      processingGeneration = nil
      attempt = nil
      processTask?.cancel()
      processTask = nil
      attemptLedger.resetRetryChain()
      let released = captureCleanup.requestClose()
      refreshCaptureCleanup()
      attemptLedger.finishActive(reason: released ? .sessionEnded : .cleanupBlocked)
      if released {
        didEnd = true
        if isRefreshingCleanup { cleanupRefreshPending = true } else { phase = .ended }
      }
      return released
    }

    func viewDidDisappear() { _ = end() }

    /// The microphone permission dialog makes iOS inactive without backgrounding it.
    func appDidBecomeInactive() {
      guard phase != .requestingPermission else { return }
      pauseAndDiscard(reason: .becameInactive)
    }

    func appDidEnterBackground() { pauseAndDiscard(reason: .backgrounded) }
    func audioWasInterrupted() { pauseAndDiscard(reason: .audioInterrupted) }

    private func pauseAndDiscard(reason: ResearchAssessmentTerminalReason) {
      guard phase != .ended, phase != .setup else { return }
      if removeTemporaryAudio(reason: reason) {
        phase = .setup
        prepare(accountForPreflightRejection: false)
      }
    }

    private func beginProcessing(
      _ recording: CapturedRecording, entry: PracticeLibraryEntry, age: Int, attemptId: UUID
    ) {
      let generation = UUID()
      processingGeneration = generation
      phase = .processing
      // Close inside the published phase must prevent the processor from being invoked.
      guard processingGeneration == generation, !closeRequested,
        pendingRecording?.url == recording.url, !captureCleanup.hasIssue
      else {
        refreshCaptureCleanup()
        return
      }
      let processor = self.processor
      processTask = Task { [weak self, cleanup = captureCleanup] in
        // Processing owns the original cleanup helper independently of the screen.
        // If the screen disappears without its lifecycle callback, cleanup still runs
        // and the producer registers exact retained-file recovery if removal fails.
        defer {
          if self == nil { _ = cleanup.removeRequestedMedia() }
        }
        do {
          try Task.checkCancellation()
          guard self?.processingGeneration == generation, self?.closeRequested == false else {
            return
          }
          let outcome = try await processor.process(
            attemptId: attemptId, recording: recording, entry: entry, ageYears: age)
          guard let self, self.processingGeneration == generation, self.phase == .processing else {
            return
          }
          self.processTask = nil
          let reason: ResearchAssessmentTerminalReason
          let terminalOutcome: ResearchAssessmentTerminalOutcome
          switch outcome {
          case .admissionProcessed:
            reason = .admissionProcessed
            terminalOutcome = .admissionProcessed
          case .processedUnverified, .processedResearch:
            reason = .promptMatchUnverified
            terminalOutcome = .processedUnverified
          case .unavailable(let serviceReason):
            #if targetEnvironment(simulator)
              if ResearchAdmissionClient.unavailableReasons.contains(serviceReason),
                !ResearchAssessmentClient.unavailableReasons.contains(serviceReason)
              {
                reason =
                  serviceReason == "cleanup_unconfirmed"
                  ? .serviceCleanupUnconfirmed : .admissionRejected
              } else {
                reason =
                  ResearchAssessmentClient.unavailableReasons.contains(serviceReason)
                  ? ResearchAssessmentTerminalReason(rawValue: serviceReason) ?? .invalidResponse
                  : .invalidResponse
              }
            #else
              reason =
                ResearchAssessmentClient.unavailableReasons.contains(serviceReason)
                ? ResearchAssessmentTerminalReason(rawValue: serviceReason) ?? .invalidResponse
                : .invalidResponse
            #endif
            terminalOutcome = .unavailable
          }
          if self.removeTemporaryAudio(reason: reason, outcome: terminalOutcome) {
            switch outcome {
            case .admissionProcessed:
              self.phase = .unavailable(
                title: "No result to show",
                detail:
                  "The recording passed the local speech and word admission checks, and the research pipeline ran. It produced no pronunciation finding. This does not indicate whether the word was said correctly or incorrectly. The recording was deleted."
              )
            case .processedUnverified:
              self.phase = .unavailable(
                title: "No result to show",
                detail:
                  "The local audio pipeline ran, but it cannot confirm that the prompted word was said. No pronunciation finding is available. The recording was deleted."
              )
            case .unavailable(let reason):
              self.phase = self.unavailablePhase(reason: reason)
            }
          }
        } catch {
          guard let self, self.processingGeneration == generation, self.phase == .processing else {
            return
          }
          self.processTask = nil
          if self.removeTemporaryAudio(reason: self.terminalReason(for: error)) {
            self.phase = self.errorPhase(error)
          }
        }
      }
    }

    /// Invalidate recorder/network callbacks before cancellation or deletion can call back.
    @discardableResult
    private func removeTemporaryAudio(
      reason: ResearchAssessmentTerminalReason = .cancelled,
      outcome: ResearchAssessmentTerminalOutcome = .unavailable
    ) -> Bool {
      recordingGeneration = nil
      processingGeneration = nil
      attempt = nil
      processTask?.cancel()
      processTask = nil
      let released = captureCleanup.removeRequestedMedia()
      refreshCaptureCleanup()
      if !released { blockCleanup() }
      attemptLedger.finishActive(reason: reason, outcome: outcome)
      return released && !cleanupBlocked
    }

    private func blockCleanup() {
      // An older failed cleanup result can resume after reentrant exact recovery and Close.
      // Preserve the committed terminal visit; the original negative result stays negative.
      guard !didEnd else { return }
      cleanupBlocked = true
      recordingGeneration = nil
      processingGeneration = nil
      processTask?.cancel()
      processTask = nil
      attemptLedger.finishActive(reason: .cleanupBlocked)
      if phase != .cleanupBlocked { phase = .cleanupBlocked }
    }

    private func unavailablePhase(reason: String) -> ResearchAssessmentPhase {
      let message: (String, String)
      switch reason {
      case "requested_word_not_matched", "single_word_required":
        message = (
          "Word check unavailable",
          "The local recognizer did not admit this recording for the requested word. This does not indicate a pronunciation problem. You can retry or continue ordinary practice."
        )
      case "speech_not_detected", "recognition_uncertain", "recognition_incomplete",
        "recognition_failed":
        message = (
          "Recording not admitted",
          "The local speech and word checks could not admit this recording for research processing. You can retry or continue ordinary practice."
        )
      case "cleanup_unconfirmed":
        message = (
          "Local service needs attention",
          "The local service could not confirm its worker cleanup and has blocked further checks. You can continue ordinary practice."
        )
      case "source_binding_failed":
        message = (
          "Local service changed",
          "The local service does not match the reviewed research sources. You can continue ordinary practice."
        )
      case "age_out_of_range":
        message = ("Age outside research scope", "This local check supports declared ages 6–12.")
      case "unsupported_target":
        message = ("Sound unavailable", "This target is outside the local model's research scope.")
      case "invalid_audio", "audio_too_long":
        message = (
          "Recording unavailable",
          "The local pipeline could not use this recording. Please record one short word again."
        )
      case "silence":
        message = (
          "Recording too quiet",
          "The local pipeline could not use the quiet recording. This is not a pronunciation finding."
        )
      case "clipping":
        message = (
          "Recording distorted",
          "The recording was too loud for the local check. Try a comfortable voice."
        )
      case "model_unavailable":
        message = (
          "Local model unavailable",
          "The local research model is not ready. You can continue manual practice."
        )
      case "timeout":
        message = (
          "Local check timed out",
          "The local service did not finish this check. Please try again later."
        )
      case "busy":
        message = (
          "Local service busy",
          "The local service is already processing another recording. Please try again later."
        )
      case "inference_failed":
        message = (
          "Local check unavailable", "The local audio pipeline could not complete this recording."
        )
      default:
        message = (
          "Local check unavailable", "The local service could not verify this request or response."
        )
      }
      return .unavailable(
        title: message.0,
        detail: "\(message.1) No pronunciation finding is available. The recording was deleted.")
    }

    private func terminalReason(for error: Error) -> ResearchAssessmentTerminalReason {
      switch error {
      case ResearchAssessmentError.timeout: return .timeout
      case ResearchAssessmentError.unsupportedAge: return .ageOutOfRange
      case ResearchAssessmentError.unsupportedPrompt: return .unsupportedTarget
      case ResearchAssessmentError.invalidRecording: return .invalidAudio
      case ResearchAssessmentError.serviceUnavailable: return .serviceUnavailable
      case is CancellationError: return .cancelled
      default: return .invalidResponse
      }
    }

    private func errorPhase(_ error: Error) -> ResearchAssessmentPhase {
      switch error {
      case ResearchAssessmentError.timeout: return unavailablePhase(reason: "timeout")
      case ResearchAssessmentError.unsupportedAge:
        return unavailablePhase(reason: "age_out_of_range")
      case ResearchAssessmentError.unsupportedPrompt:
        return unavailablePhase(reason: "unsupported_target")
      case ResearchAssessmentError.invalidRecording:
        return unavailablePhase(reason: "invalid_audio")
      case ResearchAssessmentError.serviceUnavailable:
        return .unavailable(
          title: "Local service unavailable",
          detail:
            "The local research service could not be reached. You can continue manual practice. No pronunciation finding is available. The recording was deleted."
        )
      default: return unavailablePhase(reason: "invalid_request")
      }
    }
  }
#endif
