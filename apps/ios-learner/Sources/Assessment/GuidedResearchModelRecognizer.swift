#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  enum GuidedResearchModelOutcome: Equatable, Sendable {
    case processedUnverified(milliseconds: Double)
    case notRun(Reason)
    case unavailable(Reason)
    case cancelled

    enum Reason: Equatable, Sendable {
      case disabled, ageNotDeclared, unsupportedAge, missingEntry, wrongEntry, unsupportedPrompt
      case wordNotMatched, wordUncertain, wordUnavailable, wordCleanupUnconfirmed, wrongReceipt
      case busy, repeatedOperation, invalidRecording, localCleanupUnconfirmed
      case silentRecording, recordingAtDigitalLimit, recordingTooLong, unsupportedTarget
      case modelUnavailable, requestRejected, ageRejected
      case serviceUnavailable, serviceNotReady, serverCleanupUnknown, paused
    }
  }

  /// Session memory only: take-bound research distributions, no audio or learner findings.
  struct GuidedResearchModelObservation: Equatable, Sendable {
    let request: LocalWordRecognitionRequest
    let entryID: String?
    let outcome: GuidedResearchModelOutcome
    let researchResult: ResearchAssessmentResult?

    init(request: LocalWordRecognitionRequest, entryID: String?, outcome: GuidedResearchModelOutcome,
      researchResult: ResearchAssessmentResult? = nil)
    {
      self.request = request
      self.entryID = entryID
      self.outcome = outcome
      self.researchResult = researchResult
    }

    var note: String {
      switch outcome {
      case .processedUnverified:
        return "Research model processed this take. Sound accuracy remains unverified."
      case .cancelled: return "Research processing cancelled. No sound finding was recorded."
      case .notRun(.disabled): return "Research model is off."
      case .notRun(.ageNotDeclared): return "Declare the learner’s age before research processing."
      case .notRun(.unsupportedAge): return "Research processing supports declared ages 6–12 only."
      case .notRun(.wordNotMatched), .notRun(.wordUncertain), .notRun(.wordUnavailable):
        return "Research model did not run because this take did not confirm the prompted word."
      case .notRun(.paused), .unavailable(.serverCleanupUnknown):
        return
          "Research processing is paused: server cleanup could not be confirmed. Word checks remain available."
      case .notRun(.unsupportedPrompt): return "This prompt is unavailable for research processing."
      case .unavailable(.wordCleanupUnconfirmed), .unavailable(.wrongReceipt),
        .unavailable(.localCleanupUnconfirmed):
        return "Research processing did not run because recording cleanup could not be confirmed."
      case .unavailable(.silentRecording):
        return
          "No signal was recorded in this take. Check the microphone input before making another recording."
      case .unavailable(.recordingAtDigitalLimit):
        return
          "This take reached the recording’s digital level limit. Try moving a little farther from the microphone for another recording."
      case .unavailable(.invalidRecording):
        return
          "The research model could not read this recording. Make another recording for a later check."
      case .unavailable(.recordingTooLong):
        return
          "This recording exceeds the research model’s length limit. Say the displayed word once, then tap Stop."
      case .unavailable(.unsupportedTarget):
        return
          "This target is unavailable for the research model. You can continue manual practice."
      case .unavailable(.modelUnavailable):
        return "The research model is unavailable on this Mac. You can continue manual practice."
      case .unavailable(.busy):
        return
          "The research model is busy. You can continue manual practice and check a later recording."
      case .unavailable(.requestRejected):
        return "The research model could not accept this check. You can continue manual practice."
      case .unavailable(.ageRejected):
        return
          "The research model did not accept the declared age. This take received no sound assessment."
      case .unavailable(.serviceNotReady):
        return
          "The local research service could not be reached or confirmed. Start the service on this Mac before checking a later recording. You can continue manual practice."
      case .notRun: return "Research model did not run for this take."
      case .unavailable: return "Research processing is unavailable. No sound finding was recorded."
      }
    }
  }

  /// The loopback endpoint's cleanup uncertainty survives screen/session reconstruction.
  /// Production composition uses shared process lifetime; tests inject isolated instances.
  @MainActor
  final class GuidedResearchModelAvailability: ObservableObject {
    static let shared = GuidedResearchModelAvailability()
    @Published private(set) var modelCallsPaused = false

    func pauseForUnknownCleanup() {
      guard !modelCallsPaused else { return }
      modelCallsPaused = true
    }
  }

  /// A simulator-only composition. Ordinary word status never becomes sound correctness.
  @MainActor
  final class GuidedResearchModelRecognizer: ObservableObject, LocalWordCapturedContextRecognizing, LocalWordRuntimeReleasing {
    // A timed-out word retry must not newly admit this composition's research processing.
    var allowsTimedOutRetry: Bool { false }

    enum ProcessingState: Equatable {
      case idle
      case checkingWord(operationID: UUID)
      case checkingService(operationID: UUID)
      case processingModel(operationID: UUID)
      case cancelling(operationID: UUID)
    }

    @Published private(set) var processingState: ProcessingState = .idle
    @Published private(set) var observations: [UUID: GuidedResearchModelObservation] = [:]
    private(set) var latestObservationOperationID: UUID?
    var modelCallsPaused: Bool { availability.modelCallsPaused }
    private let wordRecognizer: any LocalWordRecognizing
    private let processor: any ResearchAssessmentProcessing
    private let ownership: ProcessAudioFileOwnership
    private let availability: GuidedResearchModelAvailability
    private var availabilitySubscription: AnyCancellable?
    private var enabled = false
    private var ageYears: Int?
    private var preparedEntry: PracticeLibraryEntry?
    private var activeID: UUID?
    private var revoked = false
    // A failed local close is not a cleanup acknowledgement. Keep its resource and borrow alive.
    private var unclosedHandles: [FileHandle] = []

    init(
      wordRecognizer: any LocalWordRecognizing,
      processor: any ResearchAssessmentProcessing = ResearchAssessmentClient(),
      ownership: ProcessAudioFileOwnership = .shared,
      availability: GuidedResearchModelAvailability = .shared
    ) {
      self.wordRecognizer = wordRecognizer
      self.processor = processor
      self.ownership = ownership
      self.availability = availability
      availabilitySubscription = availability.objectWillChange.sink { [weak self] _ in
        self?.objectWillChange.send()
      }
    }

    var statusNote: String? {
      switch processingState {
      case .checkingWord: return "Checking the prompted word on this device…"
      case .checkingService: return "Checking whether the local research service is available…"
      case .processingModel: return "Processing this take with the research model on this Mac…"
      case .cancelling: return "Waiting for this take’s processing resources to finish…"
      case .idle:
        return modelCallsPaused
          ? "Research processing is paused: server cleanup could not be confirmed. Word checks remain available."
          : nil
      }
    }

    @discardableResult
    func configure(ageYears: Int?, enabled: Bool) -> Bool {
      guard activeID == nil else { return false }
      self.ageYears = ageYears
      self.enabled = enabled
      // Opting out and back in cannot erase uncertain server cleanup.
      return true
    }

    @discardableResult
    func prepare(entry: PracticeLibraryEntry) -> Bool {
      guard activeID == nil else { return false }
      guard PracticeLibrary.entries().contains(entry) else {
        preparedEntry = nil
        return false
      }
      preparedEntry = entry
      return true
    }

    func cancel(operationID: UUID) {
      guard activeID == operationID, !revoked else { return }
      revoked = true
      wordRecognizer.cancel(operationID: operationID)
      processingState = .cancelling(operationID: operationID)
      // Never cancel the model task: its bounded response must settle before releasing audio.
    }

    func releaseWordRuntime() async -> Bool {
      guard activeID == nil else { return false }
      guard let runtime = wordRecognizer as? any LocalWordRuntimeReleasing else { return true }
      return await runtime.releaseWordRuntime()
    }

    func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
      guard !Task.isCancelled else {
        return .init(request: request, status: .cancelled, cleanupConfirmed: true)
      }
      guard activeID == nil else {
        return .init(request: request, status: .unavailable, cleanupConfirmed: true)
      }
      guard observations[request.operationID] == nil else {
        return .init(request: request, status: .unavailable, cleanupConfirmed: true)
      }
      let entry = preparedEntry
      let age = ageYears
      let optedIn = enabled
      let borrowID = UUID()  // Independent of the wrapped recognizer's own operation borrow.
      guard ownership.borrow(request.fileURL, operation: borrowID) else {
        return .init(request: request, status: .unavailable, cleanupConfirmed: true)
      }
      activeID = request.operationID
      revoked = Task.isCancelled
      var localResourcesReleased = true
      defer {
        if localResourcesReleased { ownership.finishBorrowing(operation: borrowID) }
        activeID = nil
        revoked = false
        processingState = .idle
      }
      processingState = .checkingWord(operationID: request.operationID)

      return await withTaskCancellationHandler {
        if revoked || Task.isCancelled {
          observe(request, entry: entry, outcome: .cancelled)
          return .init(request: request, status: .cancelled, cleanupConfirmed: true)
        }
        // Unstructured tasks are deliberately not cancelled with the caller. Cancellation
        // revokes eligibility and requests word cleanup; actual returns govern file release.
        let wordTask = Task { @MainActor [wordRecognizer] in
          await wordRecognizer.check(request: request)
        }
        let word = await wordTask.value
        if Task.isCancelled { cancel(operationID: request.operationID) }
        guard word.request == request else {
          observe(
            request, entry: entry, outcome: revoked ? .cancelled : .unavailable(.wrongReceipt))
          return .init(
            request: request, status: revoked ? .cancelled : .unavailable, cleanupConfirmed: false)
        }
        guard word.cleanupConfirmed else {
          observe(
            request, entry: entry,
            outcome: revoked ? .cancelled : .unavailable(.wordCleanupUnconfirmed))
          return .init(
            request: request, status: revoked ? .cancelled : word.status, cleanupConfirmed: false)
        }
        if revoked || word.status == .cancelled {
          observe(request, entry: entry, outcome: .cancelled)
          return .init(request: request, status: .cancelled, cleanupConfirmed: true)
        }
        if let reason = skipReason(
          word: word.status, optedIn: optedIn, age: age, entry: entry, request: request)
        {
          observe(request, entry: entry, outcome: .notRun(reason))
          return finalWordReceipt(word)
        }
        // skipReason proves a canonical frozen entry and a genuinely declared supported age.
        guard let entry, let age else { return finalWordReceipt(word) }
        let admission: LocalWordWAVGate.Admission
        do {
          admission = try LocalWordWAVGate.read(fileURL: request.fileURL)
        } catch {
          observe(request, entry: entry, outcome: .unavailable(.invalidRecording))
          return finalWordReceipt(word)
        }
        guard admission.cleanupConfirmed else {
          if let handle = admission.retainedHandle { unclosedHandles.append(handle) }
          localResourcesReleased = false
          observe(request, entry: entry, outcome: .unavailable(.localCleanupUnconfirmed))
          return .init(
            request: request, status: revoked ? .cancelled : word.status, cleanupConfirmed: false)
        }
        guard let duration = admission.duration else {
          observe(request, entry: entry, outcome: .unavailable(.invalidRecording))
          return finalWordReceipt(word)
        }
        if let readiness = processor as? any ResearchAssessmentReadinessChecking {
          processingState = .checkingService(operationID: request.operationID)
          if revoked || Task.isCancelled {
            observe(request, entry: entry, outcome: .cancelled)
            return finalWordReceipt(
              .init(request: request, status: .cancelled, cleanupConfirmed: true))
          }
          // Cancellation revokes the result, but this bounded no-audio request must
          // actually return before the recording's independent borrow is released.
          let readinessTask = Task { @MainActor in await readiness.checkReadiness() }
          let ready = await readinessTask.value
          if Task.isCancelled { cancel(operationID: request.operationID) }
          if revoked {
            observe(request, entry: entry, outcome: .cancelled)
            return finalWordReceipt(word)
          }
          if modelCallsPaused {
            observe(request, entry: entry, outcome: .notRun(.paused))
            return finalWordReceipt(word)
          }
          guard ready else {
            observe(request, entry: entry, outcome: .unavailable(.serviceNotReady))
            return finalWordReceipt(word)
          }
        }
        // The assessment client consumes only url. Power was not measured here; this
        // adapter summary is never passed to capture-quality assessment or learner UI.
        let recording = CapturedRecording(
          url: request.fileURL, summary: .init(duration: duration, averagePower: .nan))
        processingState = .processingModel(operationID: request.operationID)
        if revoked || Task.isCancelled {
          observe(request, entry: entry, outcome: .cancelled)
          return .init(request: request, status: .cancelled, cleanupConfirmed: true)
        }
        if modelCallsPaused {
          observe(request, entry: entry, outcome: .notRun(.paused))
          return finalWordReceipt(word)
        }
        let modelTask = Task<ResearchAssessmentOutcome?, Error> { @MainActor [self] in
          guard !revoked, !modelCallsPaused else { return nil }
          return try await processor.process(
            attemptId: request.operationID, recording: recording, entry: entry, ageYears: age)
        }
        let outcome: GuidedResearchModelOutcome
        do {
          switch try await modelTask.value {
          case nil:
            outcome = .notRun(.paused)
          case .some(.processedUnverified(let milliseconds))
          where milliseconds.isFinite && milliseconds >= 0:
            outcome = .processedUnverified(milliseconds: milliseconds)
          case .some(.unavailable(let code)):
            if let reason = Self.cleanupSafeReason(for: code) {
              outcome = .unavailable(reason)
            } else {
              availability.pauseForUnknownCleanup()
              outcome = .unavailable(.serverCleanupUnknown)
            }
          case .some(.admissionProcessed), .some(.processedUnverified):
            availability.pauseForUnknownCleanup()
            outcome = .unavailable(.serverCleanupUnknown)
          }
        } catch {
          availability.pauseForUnknownCleanup()
          outcome = .unavailable(.serverCleanupUnknown)
        }
        if Task.isCancelled { cancel(operationID: request.operationID) }
        observe(request, entry: entry, outcome: revoked ? .cancelled : outcome)
        return revoked ? .init(request: request, status: .cancelled, cleanupConfirmed: true) : word
      } onCancel: {
        Task { @MainActor [weak self] in self?.cancel(operationID: request.operationID) }
      }
    }

    private func skipReason(
      word: LocalWordRecognitionStatus, optedIn: Bool, age: Int?, entry: PracticeLibraryEntry?,
      request: LocalWordRecognitionRequest
    ) -> GuidedResearchModelOutcome.Reason? {
      guard optedIn else { return .disabled }
      guard let age else { return .ageNotDeclared }
      guard (6...12).contains(age) else { return .unsupportedAge }
      guard let entry else { return .missingEntry }
      guard entry.prompt.word == request.expectedWord, PracticeLibrary.entries().contains(entry)
      else {
        return .wrongEntry
      }
      guard (try? ResearchAssessmentClient.prompt(for: entry)) != nil else {
        return .unsupportedPrompt
      }
      guard !modelCallsPaused else { return .paused }
      switch word {
      case .matched: return nil
      case .notMatched: return .wordNotMatched
      case .uncertain: return .wordUncertain
      case .unavailable, .timedOut: return .wordUnavailable
      case .cancelled: return .wordUnavailable
      }
    }

    // These bridge rejections either precede scratch work or return after successful
    // scratch cleanup. Cleanup exceptions become inference_failed; timeout is also
    // conservatively excluded because it cannot establish worker/scratch release.
    private static func cleanupSafeReason(for code: String) -> GuidedResearchModelOutcome.Reason? {
      switch code {
      case "silence": return .silentRecording
      case "clipping": return .recordingAtDigitalLimit
      case "invalid_audio": return .invalidRecording
      case "audio_too_long": return .recordingTooLong
      case "unsupported_target": return .unsupportedTarget
      case "model_unavailable": return .modelUnavailable
      case "busy": return .busy
      case "invalid_request": return .requestRejected
      case "age_out_of_range": return .ageRejected
      default: return nil
      }
    }

    private func observe(
      _ request: LocalWordRecognitionRequest, entry: PracticeLibraryEntry?,
      outcome: GuidedResearchModelOutcome
    ) {
      latestObservationOperationID = request.operationID
      observations[request.operationID] = .init(
        request: request, entryID: entry?.id, outcome: outcome)
      // Published subscribers can synchronously request cancellation while seeing this
      // terminal observation. Revoke that result before the exact receipt is returned.
      if revoked, outcome != .cancelled {
        observations[request.operationID] = .init(
          request: request, entryID: entry?.id, outcome: .cancelled)
      }
    }

    private func finalWordReceipt(_ word: LocalWordRecognitionReceipt)
      -> LocalWordRecognitionReceipt
    {
      revoked
        ? .init(request: word.request, status: .cancelled, cleanupConfirmed: word.cleanupConfirmed)
        : word
    }
  }
#endif
