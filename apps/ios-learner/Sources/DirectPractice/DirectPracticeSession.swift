import Combine
import Foundation

enum DirectPracticePhase: Equatable {
  case ready
  case requestingPermission
  case recording
  case review(CaptureSummary, CaptureAssessment)
  case permissionDenied
  case failed(String)
  case completed
  case ended
}

/// Read-only view of one completed own take. Audio identity stays inside the session.
struct DirectPracticeTry: Equatable, Identifiable {
  let id: UUID
  let summary: CaptureSummary
  let assessment: CaptureAssessment
}

enum LocalWordCheckState: Equatable {
  case idle
  case checking
  case cancelling
  case cleanupBlocked
  case finished(LocalWordRecognitionStatus)
}

enum GuidedMediaVisit: Equatable, Sendable {
  case review(LocalGuidedReviewVisit)
  case practice(LocalGuidedPracticeVisit)

  var workflowID: UUID {
    switch self {
    case .review(let visit): visit.workflowID
    case .practice(let visit): visit.workflowID
    }
  }

  var visitID: UUID {
    switch self {
    case .review(let visit): visit.visitID
    case .practice(let visit): visit.visitID
    }
  }

  var entryID: String {
    switch self {
    case .review(let visit): visit.entryID
    case .practice(let visit): visit.entryID
    }
  }
}

/// Metadata from this exact practice visit; a missing completion ID is not completion.
struct GuidedPracticeFinishResult: Equatable, Sendable {
  let visit: LocalGuidedPracticeVisit
  let freshTryID: UUID?
  let cleanupConfirmed: Bool
  let saveConfirmed: Bool
  let completionID: UUID?
}

/// One accepted save outcome; identity distinguishes repeated identical failures.
struct ParticipationSaveAnnouncement: Equatable {
  let id = UUID()
  let completion: PracticeParticipation
  let message: String
}

/// A local session has no assignment, credentials, network client, or pronunciation scorer.
@MainActor
final class DirectPracticeSession: ObservableObject {
  @Published private(set) var phase: DirectPracticePhase = .ready {
    didSet {
      mirrorStorage?.eligibilityChanged(mirrorEligibility)
    }
  }
  @Published private(set) var playbackState: PracticePlaybackRuntimeState = .idle
  @Published private(set) var captureCleanupState = CaptureCleanupState.idle
  @Published private(set) var isPlaying = false
  @Published private(set) var stopAnnouncementRequested = false
  @Published private(set) var isRetryingPlaybackCleanup = false
  @Published private(set) var playbackError: String?
  @Published private(set) var historyError: String?
  @Published private(set) var historySavedNote: String?
  @Published private(set) var closeNote: String?
  @Published private(set) var isTransitioning = false
  @Published private(set) var cleanupBlocked = false
  @Published private(set) var completedWords = 0
  @Published private(set) var skippedWords = 0
  @Published private var promptIndex = 0
  @Published private(set) var attemptCount = 0
  @Published private(set) var sound: PracticeSound
  @Published private(set) var wordCheckState: LocalWordCheckState = .idle
  // Ephemeral request-bound text, deliberately excluded from every persisted ledger.
  private var wordGuess:
    (request: LocalWordRecognitionRequest, value: LocalWordGuess, guidedVisit: GuidedMediaVisit?)?
  var currentWordGuess: LocalWordGuess? {
    guard case .review = phase, transition == nil,
      !cleanupBlocked, !wordCleanupUnconfirmed, wordCheckOperation == nil,
      wordCheckState == .finished(.notMatched), let wordGuess,
      checkedTryID == wordGuess.request.tryID, takes.last?.id == wordGuess.request.tryID,
      takes.last?.removalRequested == false,
      currentPrompt.word == wordGuess.request.expectedWord,
      wordGuess.value.expectedWord == LocalWordComparison.singleWord(currentPrompt.word),
      wordGuessScopeIsCurrent(request: wordGuess.request, guidedVisit: wordGuess.guidedVisit)
    else { return nil }
    return wordGuess.value
  }

  /// Scope gates optional text only; first-review status and cleanup keep their own contract.
  private func wordGuessScopeIsCurrent(
    request: LocalWordRecognitionRequest, guidedVisit: GuidedMediaVisit?
  ) -> Bool {
    guard managedForGuided else { return guidedVisit == nil }
    guard let guidedVisit, guidedVisit == guidedMediaVisit else { return false }
    if case .review(let visit) = guidedVisit {
      return guidedReviewSubmission
        == LocalGuidedCheckIdentity(visit: visit, operationID: request.operationID, tryID: request.tryID)
    }
    return true
  }
  /// Status-only evidence belongs to its retained take, never to a guessed alternative.
  func wordObservation(for tryID: UUID) -> LocalWordRecognitionStatus? {
    guard case .review = phase, transition == nil, !isTransitioning,
      !cleanupBlocked, !wordCleanupUnconfirmed,
      let take = takes.first(where: { $0.id == tryID && !$0.removalRequested }),
      let observation = take.wordObservation,
      observation.request.tryID == take.id,
      observation.promptID == currentPrompt.id,
      observation.request.expectedWord == currentPrompt.word,
      wordGuessScopeIsCurrent(request: observation.request, guidedVisit: observation.guidedVisit)
    else { return nil }
    return observation.status
  }

  @Published private(set) var checkedTryID: UUID?
  @Published private(set) var spokenWordState: PracticeSpokenWordState = .idle
  @Published private var spokenWordError: String?

  let managedForGuided: Bool
  private(set) var guidedMediaVisit: GuidedMediaVisit?
  private(set) var guidedReleasedVisit: GuidedMediaVisit?
  private let guidedReviewSubject = PassthroughSubject<LocalGuidedReviewEvent, Never>()
  var guidedReviewEvents: AnyPublisher<LocalGuidedReviewEvent, Never> {
    guidedReviewSubject.eraseToAnyPublisher()
  }
  private var guidedWorkflowID: UUID?
  private var guidedVisitIDs: Set<UUID> = []
  private var guidedReviewSubmission: LocalGuidedCheckIdentity?
  private var guidedPracticeFreshTryID: UUID?

  var totalWords: Int { sound.prompts.count }
  var currentIndex: Int { min(promptIndex, totalWords - 1) }
  var currentPrompt: PracticePrompt { sound.prompts[currentIndex] }
  private var canUseSession: Bool {
    (!managedForGuided || guidedMediaVisit != nil)
      && !cleanupBlocked && !isTransitioning && playbackState == .idle && transition?.intent != .end
      && wordCheckOperation == nil && !wordCleanupUnconfirmed
      && spokenWordState == .idle && activeSpokenWord == nil
  }
  /// Startup failure blocks another recording, not safe navigation or exact-owner cleanup.
  var recordingStartupUnavailable: Bool { capturer.startupAvailability == .cleanupFailed }
  var canRetry: Bool {
    canUseSession && (!recordingStartupUnavailable || !takes.isEmpty)
  }
  var actionsDisabled: Bool { !canUseSession }
  /// An unrecorded ordinary visit may be left without granting permission or participation.
  var canSkipWord: Bool {
    guard !managedForGuided, !actionsDisabled, transition == nil, cleanupTask == nil,
      takes.isEmpty, !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
      pendingCaptureOwners.isEmpty, pendingCaptureHardwareOwners.isEmpty,
      mirrorStorage?.blocksRecordForCameraPermission != true
    else { return false }
    if let mirrorStorage {
      switch mirrorStorage.state {
      case .stopping, .stopFailed: return false
      default: break
      }
    }
    switch phase {
    case .ready, .permissionDenied, .failed: return true
    default: return false
    }
  }
  /// A kept take is only ever replaced through recordAnotherTry's eviction rules.
  var canStartRecording: Bool {
    guidedCaptureAllowed && !recordingStartupUnavailable && !actionsDisabled
      && (phase == .ready || phase == .permissionDenied) && takes.isEmpty
      && mirrorStorage?.blocksRecordForCameraPermission != true
  }
  var hasPlaybackCleanupIssue: Bool {
    if case .cleanupBlocked = playbackState { return true }
    return cleanupBlocked && activePlaybackID != nil && playbackState == .idle
  }
  var hasHardwareCleanupIssue: Bool {
    hasPlaybackCleanupIssue || hasSpokenWordCleanupIssue || captureCleanupState.hasHardwareIssue
      || !pendingCaptureHardwareOwners.isEmpty
  }
  var canRetryCleanup: Bool {
    cleanupBlocked && cleanupTask == nil && wordCheckOperation == nil && !wordCleanupUnconfirmed
  }
  var hasPendingFileCleanup: Bool {
    (takes.contains(where: \.removalRequested) && activePlaybackID == nil)
      || !pendingCaptureOwners.isEmpty
  }

  /// Stronger than ordinary Close: leaving files in process recovery cannot open
  /// another owner. Read the retained receipts and live gates, never phase alone.
  var hasFullyEndedCleanup: Bool {
    phase == .ended && endAudioCleanupConfirmed && !cleanupBlocked && !isTransitioning
      && !isRetryingPlaybackCleanup
      && transition == nil && cleanupTask == nil && cleanupTaskID == nil
      && takes.isEmpty && pendingCaptureOwners.isEmpty && pendingCaptureHardwareOwners.isEmpty
      && !captureCleanupState.hasHardwareIssue && !captureCleanupState.hasFileIssue
      && !capturer.cleanupState.hasHardwareIssue && !capturer.cleanupState.hasFileIssue
      && activePlaybackID == nil && playbackState == .idle && !isPlaying
      && activeSpokenWord == nil && spokenWordState == .idle && spokenWordGeneration == nil
      && recordingGeneration == nil && recordingWordCheckIntent == nil
      && wordCheckOperation == nil && !wordCleanupUnconfirmed && wordRuntimeRelease == nil
      && (!(wordRecognizer is any LocalWordRuntimeReleasing) || wordRuntimeReleased)
      && mirrorCloseStop != nil && mirrorStorage?.isReleasedForClose == true
      && !participationSaveInProgress
      && (cleanupOwnership == nil
        || (cleanupOwnership?.hardware.currentLease == nil
          && cleanupOwnership?.files.pendingCleanupOwners.isEmpty == true
          && cleanupOwnership?.files.protectedURLs.isEmpty == true))
  }

  /// At most two completed takes of the current word, oldest first.
  var tries: [DirectPracticeTry] {
    takes.map { .init(id: $0.id, summary: $0.recording.summary, assessment: $0.assessment) }
  }
  var earlierTry: DirectPracticeTry? { takes.count == 2 ? tries.first : nil }
  var latestTry: DirectPracticeTry? { tries.last }
  /// The take whose exact playback operation is preparing, playing or stopping.
  var playingTryID: UUID? { activePlaybackID == nil ? nil : activePlaybackTakeID }

  var canRecordAnotherTry: Bool {
    guard guidedCaptureAllowed, !recordingStartupUnavailable, !actionsDisabled,
      activePlaybackID == nil, !takes.isEmpty,
      !takes.contains(where: \.removalRequested)
    else { return false }
    if mirrorStorage?.blocksRecordForCameraPermission == true { return false }
    switch phase {
    case .review, .permissionDenied: return true
    default: return false
    }
  }

  /// A denied or failed replacement keeps its truthful phase until this explicit action.
  var canReturnToReview: Bool {
    guard !actionsDisabled, activePlaybackID == nil, !takes.isEmpty,
      !takes.contains(where: \.removalRequested)
    else { return false }
    switch phase {
    case .permissionDenied, .failed: return true
    default: return false
    }
  }
  var interactiveDismissDisabled: Bool {
    if mirrorStorage?.interactiveDismissDisabled == true { return true }
    return playbackState != .idle || isTransitioning || cleanupBlocked || transition?.intent == .end
      || wordCheckOperation != nil || wordCleanupUnconfirmed || spokenWordState != .idle
  }
  var playbackControlLabel: String {
    switch playbackState {
    case .idle: hasPlaybackCleanupIssue ? "Retry stopping" : "Play recording"
    case .preparing: "Cancel playback"
    case .playing: "Stop playback"
    case .stopping: "Stopping…"
    case .cleanupBlocked: "Retry stopping"
    }
  }
  var playbackStatus: String? {
    switch playbackState {
    case .preparing: "Starting playback…"
    case .stopping: "Stopping playback. Other actions return once it has stopped."
    case .cleanupBlocked: "Playback hasn't confirmed it stopped"
    case .idle: hasPlaybackCleanupIssue ? "Playback hasn't confirmed it stopped" : nil
    case .playing: nil
    }
  }

  var nextPracticeSound: PracticeSound? {
    guard !managedForGuided, phase == .completed, !actionsDisabled,
      let lastWord = sound.prompts.last?.word,
      let lastEntry = PracticeLibrary.entries(soundID: sound.id, position: sound.position)
        .first(where: { $0.prompt.word == lastWord }),
      let nextID = PracticeLibrary.nextEntryID(
        after: lastEntry.id, soundID: sound.id, position: sound.position)
    else { return nil }
    return PracticeLibrary.session(
      soundID: sound.id, position: sound.position, startingAt: nextID)
  }

  private let capturer: any AudioCapturing
  private let player: any AcknowledgedPracticeAudioPlaying
  private let history: PracticeParticipationStore?
  private let assessor: CaptureQualityAssessor
  private let wordRecognizer: any LocalWordRecognizing
  private let spokenWord: (any PracticeSpokenWordSpeaking)?
  private struct SpokenWordVisit {
    let operation: PracticeSpokenWordOperation
    let sessionID: UUID
    let visit: GuidedMediaVisit?
  }
  private var activeSpokenWord: SpokenWordVisit?
  private var spokenWordGeneration: UUID?

  var hasSpokenWordCleanupIssue: Bool {
    if case .cleanupBlocked = spokenWordState { return true }
    return false
  }

  var showsSpokenWordControls: Bool {
    if spokenWordState != .idle { return true }
    switch phase {
    case .ready, .permissionDenied, .review, .failed: return true
    default: return false
    }
  }

  var spokenWordButtonTitle: String {
    switch spokenWordState {
    case .idle, .cleanupBlocked: "Hear word"
    case .preparing, .speaking: "Stop word"
    case .stopping: "Stopping…"
    }
  }

  var spokenWordStatusNote: String? {
    switch spokenWordState {
    case .idle:
      spokenWordError
        ?? (spokenWord == nil
          ? "Spoken words aren't available in this practice session. Use the available practice controls."
          : nil)
    case .preparing: "Starting the spoken word…"
    case .speaking: "Speaking the word."
    case .stopping: "Stopping the spoken word. Other actions wait until it has stopped."
    case .cleanupBlocked: "The spoken word hasn't confirmed it stopped. Use Retry stopping word."
    }
  }

  var canToggleSpokenWord: Bool {
    switch spokenWordState {
    case .preparing, .speaking: return true
    case .stopping, .cleanupBlocked: return false
    case .idle:
      return showsSpokenWordControls && canUseSession && spokenWord != nil
        && !captureCleanupState.hasHardwareIssue && !captureCleanupState.hasFileIssue
        && pendingCaptureOwners.isEmpty && !participationSaveInProgress
        && !takes.contains(where: \.removalRequested)
        && mirrorStorage?.blocksRecordForCameraPermission != true
    }
  }

  var canRetrySpokenWordStop: Bool { hasSpokenWordCleanupIssue }

  /// No action is queued behind speech: Record, replay and Check require an explicit later tap.
  func toggleSpokenWord() async {
    guard canToggleSpokenWord, let spokenWord else { return }
    if let active = activeSpokenWord {
      _ = await releaseSpokenWord(active, retrying: false)
      return
    }
    let captured = SpokenWordVisit(
      operation: .init(id: UUID(), word: currentPrompt.word), sessionID: sessionID,
      visit: guidedMediaVisit)
    let generation = UUID()
    spokenWordGeneration = generation
    spokenWordError = nil
    // Error publication can synchronously Close or change visits. Registration in the
    // runtime is the very next call after this guard, without another UI publication.
    guard spokenWordGeneration == generation, sessionID == captured.sessionID,
      guidedMediaVisit == captured.visit, currentPrompt.word == captured.operation.word,
      transition == nil, canToggleSpokenWord
    else { return }
    activeSpokenWord = captured
    do { try await spokenWord.start(captured.operation) } catch {
      guard spokenWordGeneration == generation, sessionID == captured.sessionID,
        guidedMediaVisit == captured.visit, currentPrompt.word == captured.operation.word,
        transition == nil,
        activeSpokenWord == nil || activeSpokenWord?.operation == captured.operation
      else { return }
      if spokenWord.state == .idle {
        activeSpokenWord = nil
        spokenWordError =
          (error as? PracticeSpokenWordError) == .busy
          ? "Audio is in use. Stop it before hearing the word."
          : "The spoken word isn't available right now. Use the available practice controls."
      }
    }
  }

  func retrySpokenWordStop() async {
    guard canRetrySpokenWordStop, let active = activeSpokenWord else { return }
    let end = transition?.intent == .end ? transition : nil
    guard await releaseSpokenWord(active, retrying: true) else { return }
    if let end, transition?.id == end.id, transition?.intent == .end {
      _ = await finishTransition(end)
      return
    }
    resumeConfirmedCleanupIfPossible()
    updateCloseNote()
  }

  private func releaseSpokenWord(_ active: SpokenWordVisit, retrying: Bool) async -> Bool {
    guard let spokenWord else { return false }
    let acknowledgement =
      retrying
      ? spokenWord.retryCleanup(id: active.operation.id)
      : spokenWord.requestStop(id: active.operation.id)
    let receipt = await acknowledgement?.value()
    let recovered = spokenWord.completedCleanupRetry(id: active.operation.id)
    guard
      (receipt?.operation == active.operation && receipt?.result == .released)
        || (recovered?.operation == active.operation && recovered?.result == .released)
    else {
      if activeSpokenWord?.operation == active.operation {
        cleanupBlocked = true
        updateCloseNote()
      }
      return false
    }
    if activeSpokenWord?.operation == active.operation { activeSpokenWord = nil }
    return true
  }

  private func receiveSpokenWordState(_ state: PracticeSpokenWordState) {
    // The owner publishes synchronously; bookkeeping precedes our own reentrant publications.
    if case .preparing(let operation) = state,
      activeSpokenWord?.operation == operation, let hardware = cleanupOwnership?.hardware,
      let lease = hardware.currentLease, lease.owner == .spokenWord,
      lease.operationID == operation.id
    {
      // A failed End must not lose its stopped-take producer when the route is released.
      // Only a known exact gate is authority to replace the standalone runtime callback.
      hardware.registerSpokenWordRecovery(lease) { [self] in
        let end = transition?.intent == .end ? transition : nil
        guard hardware.currentLease == lease, lease.owner == .spokenWord,
          lease.operationID == operation.id,
          let acknowledgement = spokenWord?.retryCleanup(id: operation.id),
          acknowledgement.operation == operation
        else { return nil }
        let receipt = await acknowledgement.value()
        guard receipt.operation == operation, receipt.result == .released else { return receipt }
        if let end, transition?.id == end.id, transition?.intent == .end {
          _ = await finishTransition(end)
        }
        // This is still only the genuine voice receipt. The process model separately
        // reads actual hardware/file recovery after the existing End has been joined.
        return receipt
      }
    }
    if case .cleanupBlocked = state {
      cleanupBlocked = true
      if let token = transition, token.intent == .advance { failedAdvanceTransitionID = token.id }
    }
    if state == .idle { activeSpokenWord = nil }
    spokenWordState = state
    if state == .idle { resumeConfirmedCleanupIfPossible() }
    updateCloseNote()
  }
  private final class WordCheckOperation {
    let request: LocalWordRecognitionRequest
    let task: Task<LocalWordRecognitionReceipt, Never>
    let promptID: String
    let guidedIdentity: LocalGuidedCheckIdentity?
    let guidedVisit: GuidedMediaVisit?
    var guidedSettlementSent = false
    var resultEligible = true
    var cancelRequested = false

    init(
      request: LocalWordRecognitionRequest, task: Task<LocalWordRecognitionReceipt, Never>,
      promptID: String, guidedIdentity: LocalGuidedCheckIdentity? = nil, guidedVisit: GuidedMediaVisit?
    ) {
      self.request = request
      self.promptID = promptID
      self.task = task
      self.guidedIdentity = guidedIdentity
      self.guidedVisit = guidedVisit
    }
  }
  private var wordCheckOperation: WordCheckOperation?
  private var wordCleanupUnconfirmed = false
  // Explicit internal test injection delays receipt handling without changing its evidence.
  private let playbackCleanupReceiptObserver:
    (@MainActor (PracticePlaybackCleanupReceipt) async -> Void)?
  private var subscriptions: Set<AnyCancellable> = []
  private var sessionID = UUID()
  /// Frozen metadata only. Retry never recaptures or changes participation counters.
  private(set) var participationCompletion: PracticeParticipation?
  @Published private var participationSaveAnnouncement: ParticipationSaveAnnouncement?
  var currentParticipationSaveAnnouncement: ParticipationSaveAnnouncement? {
    guard let event = participationSaveAnnouncement,
      participationCompletionIsCurrent(event.completion)
    else { return nil }
    return event
  }
  private var participationSaveInProgress = false
  private struct AdmittedWordObservation {
    let request: LocalWordRecognitionRequest
    let promptID: String
    let guidedVisit: GuidedMediaVisit?
    let status: LocalWordRecognitionStatus
  }

  private struct Take {
    // Injected recordings may lack a producer owner; this local ID is the take identity.
    let id = UUID()
    let recording: CapturedRecording
    let assessment: CaptureAssessment
    // Set once before the producer discard; never cleared except by exact removal.
    var removalRequested = false
    var wordObservation: AdmittedWordObservation?
  }
  private var takes: [Take] = []
  private var recordingGeneration: UUID?
  private struct RecordingWordCheckIntent {
    let generation: UUID
    let visit: LocalGuidedReviewVisit
    let sessionID: UUID
  }
  private var recordingWordCheckIntent: RecordingWordCheckIntent?
  // Also the explicit switch request token: a newer tap, stop or transition replaces it.
  private var playbackGeneration: UUID?
  // Resource identity survives eligibility revocation and failed cleanup acknowledgements.
  private var activePlaybackID: UUID?
  private var activePlaybackTakeID: UUID?
  // Serialized events can describe an owner already recovered by an earlier subscriber.
  // Retain that exact identity until positive evidence, never just until an idle snapshot.
  private var pendingCaptureOwners: Set<UUID> = []
  private var pendingCaptureHardwareOwners: Set<UUID> = []
  private var fileCloseWarningIssued = false
  private let cleanupOwnership:
    (hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership)?
  private var cleanupTask: Task<Bool, Never>?
  private var cleanupTaskID: UUID?
  private var transition: Transition?
  private var failedAdvanceTransitionID: UUID?
  private var endAudioCleanupConfirmed = false
  private var wordRuntimeReleased = false
  private var wordRuntimeRelease: Task<Bool, Never>?
  private var fileRecoveryExitAuthorized = false
  private var mirrorStorage: DirectPracticeMirror?
  private var mirrorSubscription: AnyCancellable?
  private var mirrorCloseStop: DirectPracticeMirrorStop?
  private var microphonePermissionGranted = false

  /// Generated callers inject before first access; default construction remains inert.
  var mirror: DirectPracticeMirror {
    if let mirrorStorage { return mirrorStorage }
    let created = SystemPracticeMirror.make()
    mirrorStorage = created
    observeMirror(created)
    return created
  }

  var mirrorEligibility: DirectPracticeMirrorEligibility {
    if phase == .requestingPermission {
      // The first permission request may prompt. Later granted requests do not need
      // to stop a live preview; any actual inactive scene still revokes it.
      return microphonePermissionGranted ? .unavailable : .microphonePermission
    }
    guard !actionsDisabled, playbackState == .idle else { return .unavailable }
    switch phase {
    case .ready, .permissionDenied: return .ready
    case .recording: return .recording
    case .review: return .review
    default: return .unavailable
    }
  }

  var closeRequested: Bool { transition?.intent == .end }

  /// A live recorder observation, never saved evidence or a speech-quality decision.
  var recordingInputPower: Float? {
    guard phase == .recording, let generation = recordingGeneration,
      transition == nil, !isTransitioning, !cleanupBlocked
    else { return nil }
    let power = capturer.currentRecordingPower()
    // An injected capture can synchronously revoke or replace this exact recording.
    guard phase == .recording, recordingGeneration == generation,
      transition == nil, !isTransitioning, !cleanupBlocked,
      let power, power.isFinite
    else { return nil }
    return power
  }

  func showMirror() { mirror.show(eligibility: mirrorEligibility) }
  func hideMirror() { _ = mirror.requestStop(reason: .hide) }
  func cancelMirrorPermission() { _ = mirror.requestStop(reason: .cancel) }

  func retryMirrorStop() async {
    if let token = transition, token.intent == .end, wordRuntimeRelease != nil {
      _ = await finishEnd(token)
      return
    }
    let retained = transition
    let released: Bool
    if let acknowledgement = mirror.retryStop() {
      let receipt = await acknowledgement.value()
      released = acknowledgement.confirmsRelease(receipt)
    } else {
      released = false
    }
    // Close can supersede the retained action while the exact camera retry awaits.
    if let token = transition, token.intent == .end {
      _ = await finishEnd(token)
      updateCloseNote()
      return
    }
    guard released, managedForGuided, let retained,
      transition?.id == retained.id, mirror.isReleasedForClose
    else { return }
    switch retained.intent {
    case .guidedLeave, .advance:
      // Rejoin the already-authorized action with its original visit/take identity.
      // finishTransition rechecks audio cleanup and the winning token before commit.
      _ = await finishTransition(retained)
    default: break
    }
  }

  private func observeMirror(_ mirror: DirectPracticeMirror) {
    // The getter's initial render already reads this snapshot. Forward only later
    // transitions, synchronously, without publishing back into that view update.
    mirrorSubscription = mirror.statePublisher.dropFirst().sink { [weak self] _ in
      MainActor.assumeIsolated {
        guard let self else { return }
        // Record eligibility and interactive dismissal are rendered by the parent
        // session view, not only by the mirror panel. State is already committed.
        self.objectWillChange.send()
        guard let token = self.transition, token.intent == .end else { return }
        self.updateCloseNote()
        if self.endAudioCleanupConfirmed || self.fileRecoveryExitAuthorized {
          _ = self.commitEnd(token)
        }
      }
    }
  }

  private enum Intent: Equatable {
    case ready, recoverPlayback, advance, skip, restart
    // Explicit capture-cleanup recovery removes only takes whose removal was requested.
    case recoverCapture
    // Release playback and remove the oldest of two takes before any permission/allocation.
    case prepareTry(evicting: UUID?)
    case more(PracticeSound)
    case guidedPrepare
    case guidedLeave(GuidedMediaVisit)
    case end
    // A failed capture cleans its own operation; completed survivors stay unrequested.
    case failed(String)
  }
  private struct Transition {
    let id = UUID()
    let intent: Intent
  }

  init(
    sound: PracticeSound = PracticeLibrary.starterSound,
    capturer: (any AudioCapturing)? = nil,
    player: (any AcknowledgedPracticeAudioPlaying)? = nil,
    assessor: CaptureQualityAssessor = CaptureQualityAssessor(),
    history: PracticeParticipationStore? = nil,
    managedForGuided: Bool = false,
    wordRecognizer: (any LocalWordRecognizing)? = nil,
    spokenWord: (any PracticeSpokenWordSpeaking)? = nil,
    cleanupHardwareOwnership: AudioHardwareOwnership? = nil,
    cleanupFileOwnership: ProcessAudioFileOwnership? = nil,
    playbackCleanupReceiptObserver:
      (@MainActor (PracticePlaybackCleanupReceipt) async -> Void)? = nil
  ) {
    precondition(!sound.prompts.isEmpty, "A practice session needs at least one prompt.")
    self.sound = sound
    self.capturer = capturer ?? SystemAudioCapturer()
    self.player = player ?? SystemAcknowledgedPracticeAudioPlayer()
    self.assessor = assessor
    self.history = history
    self.managedForGuided = managedForGuided
    self.wordRecognizer =
      wordRecognizer
      ?? BundledLocalWordRecognizerFactory.make(ownership: cleanupFileOwnership ?? .shared)
    self.playbackCleanupReceiptObserver = playbackCleanupReceiptObserver
    if let spokenWord {
      self.spokenWord = spokenWord
    } else if capturer == nil, player == nil {
      // The default capturer and player above both own the process-shared hardware gate.
      self.spokenWord = PracticeSpokenWordRuntime()
    } else {
      // Unknown injected gates must not contend with a guessed process-shared owner.
      self.spokenWord = nil
    }
    if let hardware = cleanupHardwareOwnership, let files = cleanupFileOwnership {
      cleanupOwnership = (hardware, files)
    } else if capturer == nil, player == nil {
      cleanupOwnership = (.shared, .shared)
    } else {
      // An injected producer/player may use isolated gates. Do not infer process recovery.
      cleanupOwnership = nil
    }
    // Both contracts publish synchronously from MainActor. Preserve that delivery ordering;
    // hopping through a Task could apply an old state after a later stop/Close request.
    self.player.statePublisher.sink { [weak self] state in
      MainActor.assumeIsolated { self?.receivePlaybackState(state) }
    }.store(in: &subscriptions)
    self.capturer.cleanupStatePublisher.sink { [weak self] state in
      MainActor.assumeIsolated { self?.receiveCaptureState(state) }
    }.store(in: &subscriptions)
    self.spokenWord?.statePublisher.sink { [weak self] state in
      MainActor.assumeIsolated { self?.receiveSpokenWordState(state) }
    }.store(in: &subscriptions)
  }

  /// No production mirror/driver is constructed by the designated initializer above.
  convenience init(
    sound: PracticeSound = PracticeLibrary.starterSound,
    capturer: any AudioCapturing,
    player: any AcknowledgedPracticeAudioPlaying,
    mirror: DirectPracticeMirror,
    assessor: CaptureQualityAssessor = CaptureQualityAssessor(),
    history: PracticeParticipationStore? = nil,
    managedForGuided: Bool = false,
    wordRecognizer: (any LocalWordRecognizing)? = nil,
    spokenWord: (any PracticeSpokenWordSpeaking)? = nil,
    cleanupHardwareOwnership: AudioHardwareOwnership? = nil,
    cleanupFileOwnership: ProcessAudioFileOwnership? = nil,
    playbackCleanupReceiptObserver:
      (@MainActor (PracticePlaybackCleanupReceipt) async -> Void)? = nil
  ) {
    self.init(
      sound: sound, capturer: capturer, player: player, assessor: assessor, history: history,
      managedForGuided: managedForGuided,
      wordRecognizer: wordRecognizer,
      spokenWord: spokenWord,
      cleanupHardwareOwnership: cleanupHardwareOwnership,
      cleanupFileOwnership: cleanupFileOwnership,
      playbackCleanupReceiptObserver: playbackCleanupReceiptObserver)
    mirrorStorage = mirror
    observeMirror(mirror)
  }

  private var guidedCaptureAllowed: Bool {
    guard managedForGuided else { return true }
    switch guidedMediaVisit {
    case .review: return guidedReviewSubmission == nil
    case .practice: return guidedPracticeFreshTryID == nil
    case nil: return false
    }
  }

  /// Canonical one-word configuration. Preparation never allocates media or starts it.
  /// The coordinator must leave the previous exact visit before preparing a successor.
  func prepareGuidedVisit(entry: PracticeLibraryEntry, visit: GuidedMediaVisit) async -> Bool {
    guard managedForGuided, !Task.isCancelled, guidedMediaVisit == nil,
      !guidedVisitIDs.contains(visit.visitID), visit.visitID != visit.workflowID,
      guidedWorkflowID == nil || guidedWorkflowID == visit.workflowID,
      entry.id == visit.entryID,
      PracticeLibrary.entries().contains(entry),
      let group = PracticeLibrary.sounds.first(where: { $0.id == entry.soundID }),
      phase == .ready || phase == .completed,
      transition == nil, cleanupTask == nil, !cleanupBlocked,
      wordCheckOperation == nil, !wordCleanupUnconfirmed, takes.isEmpty,
      activePlaybackID == nil, playbackState == .idle,
      !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
      pendingCaptureOwners.isEmpty, pendingCaptureHardwareOwners.isEmpty
    else { return false }
    guard mirrorStorage?.isReleasedForClose != false else { return false }
    let token = beginTransition(.guidedPrepare)
    guard transition?.id == token.id else { return false }
    guidedWorkflowID = visit.workflowID
    guidedReleasedVisit = nil
    guidedMediaVisit = visit
    guidedReviewSubmission = nil
    guidedPracticeFreshTryID = nil
    participationCompletion = nil
    sessionID = visit.visitID
    func isCurrent() -> Bool {
      transition?.id == token.id && guidedMediaVisit == visit && !Task.isCancelled
    }
    func revoked() -> Bool {
      if guidedMediaVisit == visit { guidedMediaVisit = nil }
      if transition?.id == token.id {
        transition = nil
        isTransitioning = false
      }
      if transition != nil, !isTransitioning { isTransitioning = true }
      return false
    }
    participationSaveAnnouncement = nil
    guard isCurrent() else { return revoked() }
    sound = PracticeSound(
      id: group.id, symbol: group.symbol, name: group.name,
      position: entry.position, prompts: [entry.prompt])
    guard isCurrent() else { return revoked() }
    completedWords = 0
    guard isCurrent() else { return revoked() }
    skippedWords = 0
    guard isCurrent() else { return revoked() }
    promptIndex = 0
    guard isCurrent() else { return revoked() }
    attemptCount = 0
    guard isCurrent() else { return revoked() }
    historyError = nil
    guard isCurrent() else { return revoked() }
    historySavedNote = nil
    guard isCurrent() else { return revoked() }
    playbackError = nil
    guard isCurrent() else { return revoked() }
    closeNote = nil
    guard isCurrent() else { return revoked() }
    phase = .ready
    guard isCurrent() else { return revoked() }
    isTransitioning = false
    guard isCurrent() else { return revoked() }
    // No resource was allocated. Commit uniqueness only after every publication has
    // retained eligibility, so an interrupted preparation can retry this exact ledger visit.
    guidedVisitIDs.insert(visit.visitID)
    transition = nil
    return true
  }

  /// Release every exact owner, including an in-flight first submission, without history
  /// or ending this shared owner. A Close/background that wins makes this return false.
  func leaveGuidedVisit(_ visit: GuidedMediaVisit) async -> Bool {
    // An explicit camera retry may have committed the retained departure after its
    // original caller returned false. Let that caller rejoin this exact receipt.
    if managedForGuided, guidedMediaVisit == nil, guidedReleasedVisit == visit,
      phase == .ready, transition == nil, !cleanupBlocked, !wordCleanupUnconfirmed
    {
      return true
    }
    guard managedForGuided, guidedMediaVisit == visit, phase != .ended,
      transition == nil || transition?.intent == .guidedLeave(visit)
    else { return false }
    let token = transition ?? beginTransition(.guidedLeave(visit))
    return await finishTransition(token)
  }

  /// The kept, valid take ID is frozen before cleanup/participation publication. Duplicate
  /// Finish joins that intent; reading a completed visit never creates another history row.
  func finishGuidedPractice(_ visit: LocalGuidedPracticeVisit) async -> GuidedPracticeFinishResult {
    guard managedForGuided, guidedMediaVisit == .practice(visit), phase != .ended else {
      return uncommittedGuidedPractice(visit)
    }
    if phase == .completed { return currentGuidedPracticeResult(visit) }
    if let token = transition, token.intent == .advance, guidedPracticeFreshTryID != nil {
      _ = await finishTransition(token)
      return currentGuidedPracticeResult(visit)
    }
    guard transition == nil, !cleanupBlocked, !wordCleanupUnconfirmed,
      case .review = phase, guidedPracticeFreshTryID == nil, let latest = takes.last,
      !latest.removalRequested, latest.assessment == .acceptable,
      latest.recording.summary.duration.isFinite, latest.recording.summary.averagePower.isFinite,
      !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
      pendingCaptureOwners.isEmpty
    else { return uncommittedGuidedPractice(visit) }
    guidedPracticeFreshTryID = latest.id
    let token = beginTransition(.advance)
    _ = await finishTransition(token)
    return currentGuidedPracticeResult(visit)
  }

  private func uncommittedGuidedPractice(_ visit: LocalGuidedPracticeVisit)
    -> GuidedPracticeFinishResult
  {
    .init(
      visit: visit, freshTryID: nil, cleanupConfirmed: false,
      saveConfirmed: false, completionID: nil)
  }

  private func currentGuidedPracticeResult(_ visit: LocalGuidedPracticeVisit)
    -> GuidedPracticeFinishResult
  {
    guard guidedMediaVisit == .practice(visit), phase == .completed, transition == nil,
      !cleanupBlocked, !wordCleanupUnconfirmed, wordCheckOperation == nil, takes.isEmpty,
      activePlaybackID == nil, playbackState == .idle, cleanupTask == nil,
      !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
      pendingCaptureOwners.isEmpty, pendingCaptureHardwareOwners.isEmpty,
      let freshTryID = guidedPracticeFreshTryID,
      let completion = participationCompletion, completion.id == visit.visitID,
      sessionID == visit.visitID, completion.wordCount == 1, completion.soundID == sound.id
    else { return uncommittedGuidedPractice(visit) }
    let saved = history?.entries.contains(completion) == true && historyError == nil
    return .init(
      visit: visit, freshTryID: freshTryID, cleanupConfirmed: true,
      saveConfirmed: saved, completionID: completion.id)
  }

  func startRecording() async {
    guard canStartRecording else { return }
    await captureTake()
  }

  var canStartRecordingAndCheckWord: Bool {
    guard managedForGuided, case .review = guidedMediaVisit,
      guidedReviewSubmission == nil
    else { return false }
    return canStartRecording
  }

  /// One explicit fresh recording, followed by its exact stopped take's word check.
  func startRecordingAndCheckWord() async {
    guard !Task.isCancelled, canStartRecordingAndCheckWord,
      case .review(let visit) = guidedMediaVisit
    else { return }
    await captureTake(checkingWordFor: visit)
  }

  /// Keeps the current take(s). With two, the earlier one is removed, with exact evidence,
  /// before microphone permission or any recording file is requested.
  func recordAnotherTry() async {
    guard canRecordAnotherTry else { return }
    await prepareAndRecordAnotherTry()
  }

  var canRecordAnotherTryAndCheckWord: Bool {
    guard managedForGuided, case .review = guidedMediaVisit,
      guidedReviewSubmission == nil
    else { return false }
    return canRecordAnotherTry
  }

  /// An explicit replacement checks only its own stopped take, before any submission.
  func recordAnotherTryAndCheckWord() async {
    guard !Task.isCancelled, canRecordAnotherTryAndCheckWord,
      case .review(let visit) = guidedMediaVisit
    else { return }
    await prepareAndRecordAnotherTry(checkingWordFor: visit)
  }

  private func prepareAndRecordAnotherTry(checkingWordFor visit: LocalGuidedReviewVisit? = nil)
    async
  {
    let preparingSessionID = sessionID
    let evicting = takes.count >= 2 ? takes.first?.id : nil
    let token = beginTransition(.prepareTry(evicting: evicting))
    _ = await finishTransition(token)
    // Commit publishes Requesting permission; any reentrant Close/background supersedes it.
    guard transition == nil, phase == .requestingPermission, !cleanupBlocked, takes.count < 2
    else { return }
    if let visit {
      guard sessionID == preparingSessionID, guidedMediaVisit == .review(visit),
        guidedReviewSubmission == nil
      else { return }
      if Task.isCancelled {
        if let latest = takes.last {
          phase = .review(latest.recording.summary, latest.assessment)
        }
        return
      }
    }
    await captureTake(checkingWordFor: visit)
  }

  /// Explicit return from a denied/failed replacement. Never starts playback or capture.
  func returnToReview() {
    guard canReturnToReview, let latest = takes.last else { return }
    playbackError = nil
    phase = .review(latest.recording.summary, latest.assessment)
  }

  var canCheckWordsInLatestTry: Bool {
    if managedForGuided {
      switch guidedMediaVisit {
      case .review:
        guard guidedReviewSubmission == nil else { return false }
      case .practice:
        guard guidedPracticeFreshTryID == nil else { return false }
      case nil:
        return false
      }
    }
    guard case .review = phase, canRetry, activePlaybackID == nil, cleanupTask == nil,
      !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
      pendingCaptureOwners.isEmpty, let latest = takes.last, !latest.removalRequested
    else { return false }
    if checkedTryID == latest.id, case .finished(let status) = wordCheckState {
      return status == .unavailable || status == .cancelled
        || (status == .timedOut && wordRecognizer.allowsTimedOutRetry)
    }
    return true
  }

  /// Reading a stopped take is explicit and never starts microphone capture or playback.
  func startWordCheck() async {
    guard let operation = beginWordCheck() else { return }
    _ = await operation.task.value
  }

  private func beginWordCheck() -> WordCheckOperation? {
    guard canCheckWordsInLatestTry, let latest = takes.last else { return nil }
    wordGuess = nil
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: latest.id, fileURL: latest.recording.url,
      expectedWord: currentPrompt.word)
    let guidedIdentity: LocalGuidedCheckIdentity?
    if managedForGuided, case .review(let visit) = guidedMediaVisit {
      guidedIdentity = .init(visit: visit, operationID: request.operationID, tryID: request.tryID)
    } else {
      guidedIdentity = nil
    }
    let context = LocalWordCapturedContext(request: request, takeID: latest.id,
      recording: latest.recording, guidedVisit: guidedMediaVisit, entryID: currentPrompt.id)
    let task = Task { @MainActor [self, wordRecognizer] in
      let receipt: LocalWordRecognitionReceipt
      if let capturedRecognizer = wordRecognizer as? any LocalWordCapturedContextRecognizing {
        // Submitted/checking publications may synchronously revoke this exact handoff.
        guard !Task.isCancelled, let operation = wordCheckOperation, operation.request == request,
          operation.resultEligible, !operation.cancelRequested, transition == nil, takes.last?.removalRequested == false,
          takes.last?.id == context.takeID, currentPrompt.id == context.entryID,
          guidedMediaVisit == context.guidedVisit
        else {
          let receipt = LocalWordRecognitionReceipt(
            request: request, status: .cancelled, cleanupConfirmed: true)
          if let operation = wordCheckOperation, operation.request == request {
            _ = settleWordCheck(operation, receipt: receipt)
          }
          return receipt
        }
        receipt = await capturedRecognizer.check(context: context)
      } else {
        receipt = await wordRecognizer.check(request: request)
      }
      if let operation = wordCheckOperation, operation.request == request {
        _ = settleWordCheck(operation, receipt: receipt)
      }
      return receipt
    }
    let operation = WordCheckOperation(
      request: request, task: task, guidedIdentity: guidedIdentity)
    wordCheckOperation = operation
    // Freeze the first submission before any synchronous observer can request a retry,
    // cancellation or Close. The retained operation owns that same identity to settlement.
    if let guidedIdentity {
      guidedReviewSubmission = guidedIdentity
      guidedReviewSubject.send(.submitted(guidedIdentity))
    }
    if operation.resultEligible, transition == nil {
      checkedTryID = latest.id
      if !operation.resultEligible || transition != nil { checkedTryID = nil }
    }
    // Synchronous observation can request Close while a published property changes.
    if operation.resultEligible, transition == nil { wordCheckState = .checking }
    return operation
  }

  func cancelWordCheck() {
    guard let operation = wordCheckOperation else { return }
    let firstRequest = !operation.cancelRequested
    operation.cancelRequested = true
    operation.task.cancel()
    wordRecognizer.cancel(operationID: operation.request.operationID)
    if firstRequest, !wordCleanupUnconfirmed { wordCheckState = .cancelling }
  }

  private func invalidateWordCheck() {
    wordGuess = nil
    wordCheckOperation?.resultEligible = false
    cancelWordCheck()
    checkedTryID = nil
    if wordCheckOperation == nil, !wordCleanupUnconfirmed { wordCheckState = .idle }
  }

  private func settleWordCheckForCleanup() async -> Bool {
    guard let operation = wordCheckOperation else { return !wordCleanupUnconfirmed }
    let receipt = await operation.task.value
    return settleWordCheck(operation, receipt: receipt)
  }

  private func settleWordCheck(
    _ operation: WordCheckOperation, receipt: LocalWordRecognitionReceipt
  ) -> Bool {
    guard wordCheckOperation === operation else {
      return wordCheckOperation == nil && !wordCleanupUnconfirmed
    }
    // A receipt for a sibling take cannot authorize deletion of this borrowed input.
    guard receipt.request == operation.request, receipt.cleanupConfirmed,
      !wordCleanupUnconfirmed
    else {
      wordGuess = nil
      wordCleanupUnconfirmed = true
      emitGuidedSettlement(operation, status: .unavailable, eligible: false, cleanup: false)
      cleanupBlocked = true
      wordCheckState = .cleanupBlocked
      updateCloseNote()
      return false
    }
    let eligible =
      operation.resultEligible && transition == nil
      && checkedTryID == operation.request.tryID && takes.last?.id == operation.request.tryID
      && currentPrompt.word == operation.request.expectedWord
    let status: LocalWordRecognitionStatus = operation.cancelRequested ? .cancelled : receipt.status
    emitGuidedSettlement(operation, status: status, eligible: eligible, cleanup: true)
    wordCheckOperation = nil
    wordGuess = nil
    if eligible, operation.resultEligible, transition == nil {
      if !managedForGuided, status == .notMatched, let guess = receipt.wordGuess,
        guess.expectedWord == LocalWordComparison.singleWord(operation.request.expectedWord)
      {
        wordGuess = (operation.request, guess)
      }
      wordCheckState = .finished(status)
      // A published observation can synchronously revoke eligibility too.
      if transition != nil || checkedTryID != operation.request.tryID
        || takes.last?.id != operation.request.tryID
        || currentPrompt.word != operation.request.expectedWord
      {
        wordGuess = nil
        wordCheckState = .idle
      }
    } else {
      checkedTryID = nil
      wordCheckState = .idle
    }
    return true
  }

  private func emitGuidedSettlement(
    _ operation: WordCheckOperation, status: LocalWordRecognitionStatus,
    eligible: Bool, cleanup: Bool
  ) {
    guard let identity = operation.guidedIdentity, !operation.guidedSettlementSent else { return }
    operation.guidedSettlementSent = true
    guidedReviewSubject.send(
      .settled(
        identity: identity, status: status, resultEligible: eligible, cleanupConfirmed: cleanup))
  }

  private func captureTake(checkingWordFor visit: LocalGuidedReviewVisit? = nil) async {
    invalidateWordCheck()
    let generation = UUID()
    recordingGeneration = generation
    recordingWordCheckIntent = visit.map {
      RecordingWordCheckIntent(generation: generation, visit: $0, sessionID: sessionID)
    }
    defer {
      if recordingGeneration != generation || phase != .recording,
        recordingWordCheckIntent?.generation == generation
      {
        recordingWordCheckIntent = nil
      }
    }
    playbackError = nil
    phase = .requestingPermission
    // Mirror eligibility publication can synchronously request Close. Do not enter
    // microphone permission or capture after that end intent has revoked this generation.
    guard recordingGeneration == generation, phase == .requestingPermission,
      !cleanupBlocked, transition == nil
    else { return }
    let granted = await capturer.requestPermission()
    guard recordingGeneration == generation, phase == .requestingPermission,
      !cleanupBlocked, transition == nil
    else { return }
    if visit != nil, Task.isCancelled {
      recordingWordCheckIntent = nil
      recordingGeneration = nil
      phase = .ready
      return
    }
    guard granted else {
      recordingWordCheckIntent = nil
      recordingGeneration = nil
      phase = .permissionDenied
      return
    }
    microphonePermissionGranted = true
    do {
      try capturer.start { [weak self] successfully in
        guard let self, self.recordingGeneration == generation, self.phase == .recording else {
          return
        }
        if successfully {
          self.stopRecording()
        } else {
          await self.performTransition(
            .failed("The recording was interrupted. Please try the word again."))
        }
      }
      phase = .recording
    } catch {
      recordingWordCheckIntent = nil
      recordingGeneration = nil
      captureCleanupState = capturer.cleanupState
      cleanupBlocked = captureCleanupState.hasHardwareIssue || captureCleanupState.hasFileIssue
      phase = .failed(error.localizedDescription)
    }
  }

  func stopRecording() {
    guard phase == .recording, transition == nil else { return }
    let generation = recordingGeneration
    defer {
      if recordingWordCheckIntent?.generation == generation { recordingWordCheckIntent = nil }
    }
    recordingGeneration = nil
    do {
      let recording = try capturer.stop()
      // Track the returned file first. Stop's own publications may already have requested
      // Close/background; that winning intent removes this take without counting it.
      let take = Take(recording: recording, assessment: recordingAssessment(recording.summary))
      takes.append(take)
      guard transition == nil, phase == .recording else { return }
      // Each write publishes from willSet before storing. A winning intent owns this take's
      // cleanup only, so restore the counter and phase it saw instead of counting the take.
      let previousAttempts = attemptCount
      attemptCount = previousAttempts + 1
      guard transition == nil, phase == .recording else {
        if attemptCount != previousAttempts { attemptCount = previousAttempts }
        return
      }
      phase = .review(take.recording.summary, take.assessment)
      guard transition == nil else {
        if attemptCount != previousAttempts { attemptCount = previousAttempts }
        if case .review = phase { phase = .recording }
        return
      }
      guard let intent = recordingWordCheckIntent, intent.generation == generation,
        intent.sessionID == sessionID, guidedMediaVisit == .review(intent.visit),
        takes.last?.id == take.id, take.assessment == .acceptable,
        take.recording.summary.duration.isFinite, take.recording.summary.averagePower.isFinite,
        canCheckWordsInLatestTry
      else { return }
      recordingWordCheckIntent = nil
      _ = beginWordCheck()
    } catch {
      let token = beginTransition(.failed(error.localizedDescription))
      // Strong task owns the session until cleanup finishes, including lifecycle disappearance.
      Task { @MainActor [self] in _ = await finishTransition(token) }
    }
  }

  /// Latest-compatible single control: stops whichever take is active, else plays the latest.
  func togglePlayback() async {
    guard let target = playingTryID ?? takes.last?.id else { return }
    await togglePlayback(tryID: target)
  }

  /// Same take stops it. Another take, while one is preparing or playing, stops that exact
  /// operation and plays the requested take only after positive release evidence.
  func togglePlayback(tryID: UUID) async {
    guard case .review = phase, transition == nil, !cleanupBlocked,
      wordCheckOperation == nil, !wordCleanupUnconfirmed,
      spokenWordState == .idle, activeSpokenWord == nil,
      takes.contains(where: { $0.id == tryID && !$0.removalRequested })
    else { return }
    if let id = activePlaybackID {
      if activePlaybackTakeID == tryID {
        stopAnnouncementRequested = true
        playbackGeneration = nil
        let ack = player.requestStop(id: id)
        _ = await releasePlayback(id: id, acknowledgement: ack)
        return
      }
      switch playbackState {
      case .preparing, .playing: break
      default: return  // Both rows wait while an exact stop is still settling.
      }
      let request = UUID()
      playbackGeneration = request
      stopAnnouncementRequested = false
      let ack = player.requestStop(id: id)
      // A missing or negative acknowledgement is never permission to start other audio.
      guard await releasePlayback(id: id, acknowledgement: ack), playbackGeneration == request
      else {
        if playbackGeneration == request { playbackGeneration = nil }
        return
      }
      await startPlayback(tryID: tryID, generation: request)
      return
    }
    guard playbackState == .idle else { return }
    await startPlayback(tryID: tryID, generation: UUID())
  }

  private func startPlayback(tryID: UUID, generation: UUID) async {
    // Revalidate after any release await: same visit, phase, take and no newer request.
    guard case .review = phase, transition == nil, !cleanupBlocked, activePlaybackID == nil,
      playbackState == .idle, wordCheckOperation == nil, !wordCleanupUnconfirmed,
      let take = takes.first(where: { $0.id == tryID && !$0.removalRequested })
    else {
      if playbackGeneration == generation { playbackGeneration = nil }
      return
    }
    let url = take.recording.url
    let id = UUID()
    playbackGeneration = generation
    stopAnnouncementRequested = false
    activePlaybackID = id
    activePlaybackTakeID = tryID
    playbackError = nil
    do {
      try await player.play(id: id, url: url) { [weak self] operation, successfully in
        guard let self, self.activePlaybackID == operation.id,
          self.playbackGeneration == generation, operation.url == url,
          self.transition == nil, case .review = self.phase
        else { return }
        self.activePlaybackID = nil
        self.playbackGeneration = nil
        if !successfully {
          self.playbackError = self.playbackFailureMessage(tryID)
        }
      }
      // The publisher, rather than this return, controls Playing. Eligibility may have
      // changed while preparation awaited its queue; no completion UI follows a stale start.
      guard activePlaybackID == id, playbackGeneration == generation, transition == nil else {
        return
      }
    } catch {
      guard activePlaybackID == id, playbackGeneration == generation, transition == nil else {
        return
      }
      playbackGeneration = nil
      if case .cleanupBlocked(let operation) = playbackState, operation.id == id {
        cleanupBlocked = true
      } else {
        activePlaybackID = nil
        playbackError =
          (error as? PracticePlaybackRuntimeError) == .busy
          ? "Audio from another screen is still stopping. Try again once it has stopped."
          : playbackFailureMessage(tryID)
      }
    }
  }

  private func playbackFailureMessage(_ tryID: UUID) -> String {
    guard takes.count == 2 else { return PracticePlaybackError.couldNotPlay.localizedDescription }
    return takes.first?.id == tryID
      ? "The earlier try didn't play. Both recordings are still here."
      : "The latest try didn't play. Both recordings are still here."
  }

  /// Destructive: removes every kept take of this word and returns to Ready.
  func retry() async {
    guard guidedCaptureAllowed, !cleanupBlocked, transition == nil,
      !recordingStartupUnavailable || !takes.isEmpty
    else { return }
    switch phase {
    case .review, .permissionDenied, .failed: await performTransition(.ready)
    default: break
    }
  }

  func continuePractice() async {
    guard !managedForGuided, case .review = phase, !cleanupBlocked, transition == nil else {
      return
    }
    await performTransition(.advance)
  }

  var canRetryParticipationSave: Bool {
    guard history != nil, historyError != nil, !participationSaveInProgress,
      let completion = participationCompletion
    else { return false }
    return participationCompletionIsCurrent(completion)
  }

  /// Synchronous store writes need no new task or media-cleanup operation.
  func retryParticipationSave() {
    guard canRetryParticipationSave, let completion = participationCompletion else { return }
    saveParticipation(completion, retrying: true)
  }

  private func participationCompletionIsCurrent(_ completion: PracticeParticipation) -> Bool {
    let managedIdentityMatches: Bool
    if managedForGuided {
      if case .practice(let visit) = guidedMediaVisit {
        managedIdentityMatches = visit.visitID == completion.id
      } else {
        managedIdentityMatches = false
      }
    } else {
      managedIdentityMatches = true
    }
    return managedIdentityMatches && participationCompletion == completion
      && sessionID == completion.id
      && phase == .completed && transition == nil && !actionsDisabled
  }

  private func saveParticipation(_ completion: PracticeParticipation, retrying: Bool) {
    guard !participationSaveInProgress, participationCompletionIsCurrent(completion) else { return }
    guard let history else {
      let message = "Practice complete. Saving history is unavailable here."
      historyError = message
      announceParticipationSave(completion, message: message)
      return
    }
    participationSaveInProgress = true
    defer { participationSaveInProgress = false }
    do {
      try history.record(
        sessionID: completion.id, completedAt: completion.completedAt,
        soundID: completion.soundID, wordCount: completion.wordCount)
      // Entries publish synchronously. Close/new practice may revoke this completion
      // during the entered write; its own entry may commit, but no successor is labelled Saved.
      guard participationCompletionIsCurrent(completion) else { return }
      historyError = nil
      guard participationCompletionIsCurrent(completion) else { return }
      if retrying {
        historySavedNote = "Saved to practice history."
        announceParticipationSave(completion, message: "Saved to practice history.")
      } else if !managedForGuided {
        announceParticipationSave(completion, message: "Practice complete.")
      }
    } catch {
      guard participationCompletionIsCurrent(completion) else { return }
      let message =
        retrying
        ? "Still not saved to practice history. You can try again or keep practicing."
        : "Practice complete, but this session could not be saved to practice history."
      historyError = message
      announceParticipationSave(completion, message: message)
    }
  }

  private func announceParticipationSave(_ completion: PracticeParticipation, message: String) {
    guard participationCompletionIsCurrent(completion) else { return }
    participationSaveAnnouncement = .init(completion: completion, message: message)
  }

  func restart() async {
    guard !managedForGuided, !cleanupBlocked, transition == nil else { return }
    await performTransition(.restart)
  }

  func practiceMore() async {
    guard !managedForGuided, let next = nextPracticeSound, transition == nil else { return }
    await performTransition(.more(next))
  }

  /// Duplicate pending Close joins its intent/cleanup. A later explicit second Close may
  /// leave a file-only failure only when process-held producer recovery is proven.
  @discardableResult
  func end() async -> Bool {
    if phase == .ended { return true }
    if fileCloseWarningIssued, canLeavePendingFileRecovery {
      // Explicit second Close: hardware is released and every retained file has a
      // reachable process-held producer retry. Keep those owners and references intact.
      fileRecoveryExitAuthorized = true
      let token = beginTransition(.end)
      if let stop = mirrorCloseStop { _ = await stop.released() }
      guard transition?.id == token.id else { return phase == .ended }
      return await finishEnd(token)
    }
    if activePlaybackID != nil { stopAnnouncementRequested = true }
    let token = beginTransition(.end)
    return await finishTransition(token)
  }

  func viewDidDisappear() {
    _ = mirrorStorage?.requestStop(reason: .disappeared)
    guard phase != .ended else { return }
    let token = beginTransition(.end)
    Task { @MainActor [self] in _ = await finishTransition(token) }
  }

  /// iOS becomes inactive while its microphone permission dialog is open.
  func appDidBecomeInactive() {
    mirrorStorage?.sceneChanged(.inactive)
    if mirrorStorage?.preservesAudioDuringCameraPermissionInactive == true { return }
    guard phase != .requestingPermission else { return }
    pauseAndDiscard()
  }
  func appDidBecomeActive() {
    mirror.eligibilityChanged(mirrorEligibility)
    mirror.sceneChanged(.active)
  }
  func appDidEnterBackground() {
    mirrorStorage?.sceneChanged(.background)
    pauseAndDiscard()
  }
  func audioWasInterrupted() { pauseAndDiscard() }

  /// Explicit recovery never replays or resumes Continue. A prior Close remains authorized.
  func retryCleanup() async {
    if let token = transition, token.intent == .end, wordRuntimeRelease != nil {
      _ = await finishEnd(token)
      return
    }
    guard canRetryCleanup else { return }
    isRetryingPlaybackCleanup = hasPlaybackCleanupIssue
    defer { isRetryingPlaybackCleanup = false }
    let close = transition?.intent == .end
    let preserveTake =
      !close && hasPlaybackCleanupIssue
      && !captureCleanupState.hasHardwareIssue && !captureCleanupState.hasFileIssue
      && pendingCaptureOwners.isEmpty
    // Non-Close recovery keeps every take whose removal was never requested.
    let token =
      close ? transition! : beginTransition(preserveTake ? .recoverPlayback : .recoverCapture)
    let cleaned = await removeTemporaryAudio(retrying: true)
    guard transition?.id == token.id else { return }
    guard cleaned else {
      if !close { transition = nil }
      isTransitioning = false
      if close, !hasHardwareCleanupIssue {
        fileCloseWarningIssued = captureCleanupState.hasFileIssue
      }
      updateCloseNote()
      return
    }
    if !close, token.intent == .recoverPlayback, !takes.isEmpty, case .review = phase {
      // Playback recovery preserves the take and visit. Failed Continue needs a fresh tap.
      transition = nil
      isTransitioning = false
      playbackError = nil
    } else {
      if close {
        endAudioCleanupConfirmed = true
        _ = await finishEnd(token)
      } else {
        _ = commitTransition(token)
      }
    }
  }

  private func pauseAndDiscard() {
    guard phase != .completed, phase != .ended else { return }
    let token = beginTransition(transition?.intent == .end ? .end : .ready)
    Task { @MainActor [self] in _ = await finishTransition(token) }
  }

  private func performTransition(_ intent: Intent) async {
    let token = beginTransition(intent)
    _ = await finishTransition(token)
  }

  private func beginTransition(_ intent: Intent) -> Transition {
    spokenWordGeneration = nil
    switch intent {
    case .restart, .more, .end:
      participationCompletion = nil
      historySavedNote = nil
    default: break
    }
    if let transition, transition.intent == .end { return transition }
    if intent == .restart { wordRuntimeReleased = false }
    if case .more = intent { wordRuntimeReleased = false }
    if let transition, case .guidedLeave = intent, transition.intent == intent { return transition }
    let token = Transition(intent: intent)
    transition = token
    switch intent {
    case .restart, .more, .end:
      participationSaveAnnouncement = nil
      guard transition?.id == token.id else { return token }
    default: break
    }
    isTransitioning = true
    recordingGeneration = nil
    playbackGeneration = nil
    recordingWordCheckIntent = nil
    invalidateWordCheck()
    if intent == .end {
      endAudioCleanupConfirmed = false
      mirrorCloseStop = mirror.requestStop(reason: .close)
    }
    // Revoke preparation immediately, before any actor suspension or cleanup task scheduling.
    if let active = activeSpokenWord { _ = spokenWord?.requestStop(id: active.operation.id) }
    if let id = activePlaybackID { _ = player.requestStop(id: id) }
    if cleanupBlocked, cleanupTask == nil,
      spokenWordState == .idle, activeSpokenWord == nil,
      wordCheckOperation == nil, !wordCleanupUnconfirmed, registersProducerRecovery(intent)
    {
      // The existing owned cleanup task keeps the producer reachable until it settles.
      // A held external retry may publish Stopping. Ownership/deletion intent, rather
      // than the current UI phase, requires producer recovery before this route is lost.
      registerPendingDiscard()
    }
    updateCloseNote()
    return token
  }

  private func finishTransition(_ token: Transition) async -> Bool {
    var cleaned = await removeTemporaryAudio()
    // A Close/background intent may have superseded Continue during cleanup. Revalidate
    // before counters, history, prompt changes or navigation, even when cleanup succeeded.
    guard transition?.id == token.id else { return phase == .ended && token.intent == .end }
    if cleaned, !removalIDs(for: token.intent).isEmpty {
      // A Close/background may join a playback recovery or selective eviction just after it
      // preserved takes. Join release once, then require this intent's own deletion set.
      cleaned = await removeTemporaryAudio()
      guard transition?.id == token.id else { return phase == .ended && token.intent == .end }
    }
    if token.intent == .end {
      endAudioCleanupConfirmed = cleaned
      // Audio retry can remain reachable while camera cleanup is pending. The sticky
      // end token separately blocks ordinary practice and all central end commits.
      isTransitioning = false
      if !cleaned, !hasHardwareCleanupIssue {
        fileCloseWarningIssued = captureCleanupState.hasFileIssue
      }
      updateCloseNote()
      if let stop = mirrorCloseStop { _ = await stop.released() }
      guard transition?.id == token.id else { return phase == .ended }
      return await finishEnd(token)
    }
    guard cleaned else {
      if token.intent != .end { transition = nil }
      isTransitioning = false
      if failedAdvanceTransitionID == token.id, activePlaybackID == nil,
        wordCheckOperation == nil, !wordCleanupUnconfirmed,
        !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
        pendingCaptureOwners.isEmpty
      {
        // The failed action stays cancelled even if a separate exact retry released audio.
        cleanupBlocked = false
      }
      if token.intent == .end, !hasHardwareCleanupIssue {
        fileCloseWarningIssued = captureCleanupState.hasFileIssue
      }
      updateCloseNote()
      return false
    }
    if managedForGuided {
      switch token.intent {
      case .guidedLeave, .advance:
        guard await confirmGuidedMirrorRelease(token) else { return false }
      default: break
      }
    }
    return commitTransition(token)
  }

  private func confirmGuidedMirrorRelease(_ token: Transition) async -> Bool {
    if let mirrorStorage, !mirrorStorage.isReleasedForClose {
      let stop = mirrorStorage.requestStop(reason: .completion)
      guard await stop.released(), mirrorStorage.isReleasedForClose else { return false }
    }
    return transition?.id == token.id
  }

  private func commitTransition(_ token: Transition) -> Bool {
    if token.intent == .end { return commitEnd(token) }
    guard transition?.id == token.id, !cleanupBlocked,
      !(token.intent == .advance && failedAdvanceTransitionID == token.id)
    else { return false }
    if token.intent == .advance, completedWords + 1 == totalWords {
      _ = mirrorStorage?.requestStop(reason: .completion)
      // Camera subscribers can request Close or restart synchronously. Revalidate
      // before participation counters/history, not just before the stop request.
      guard transition?.id == token.id, !cleanupBlocked,
        failedAdvanceTransitionID != token.id
      else { return false }
    }
    if token.intent == .advance { return commitAdvance(token) }
    if case .guidedLeave(let visit) = token.intent {
      return commitGuidedDeparture(token, visit: visit)
    }
    transition = nil
    isTransitioning = false
    closeNote = nil
    fileCloseWarningIssued = false
    playbackError = nil
    switch token.intent {
    case .ready:
      if managedForGuided, case .practice = guidedMediaVisit, takes.isEmpty,
        participationCompletion == nil
      {
        // Background/interruption cancelled Finish; exact cleanup permits a fresh
        // explicit capture, without crediting the abandoned take or saving it.
        guidedPracticeFreshTryID = nil
      }
      phase = .ready
    case .recoverPlayback: break
    case .recoverCapture:
      // Exact cleanup succeeded; surviving unrequested takes are safe to review again.
      if let latest = takes.last {
        phase = .review(latest.recording.summary, latest.assessment)
      } else {
        if managedForGuided, case .practice = guidedMediaVisit, participationCompletion == nil {
          // Recovery cancels the failed Finish. A new explicit capture/Finish is required.
          guidedPracticeFreshTryID = nil
        }
        phase = .ready
      }
    case .prepareTry:
      // Eviction (if any) is confirmed. recordAnotherTry continues synchronously.
      phase = .requestingPermission
    case .failed(let message): phase = .failed(message)
    case .end, .advance, .guidedPrepare, .guidedLeave: break
    case .restart, .more:
      if case .more(let next) = token.intent { sound = next }
      sessionID = UUID()
      historyError = nil
      completedWords = 0
      attemptCount = 0
      phase = .ready
    }
    return token.intent == .end
  }

  private func commitGuidedDeparture(_ token: Transition, visit: GuidedMediaVisit) -> Bool {
    guard transition?.id == token.id, guidedMediaVisit == visit, !cleanupBlocked,
      !wordCleanupUnconfirmed, takes.isEmpty
    else { return false }
    // Retain the token until every publication has completed; a nested Close owns it.
    phase = .ready
    guard transition?.id == token.id else { return false }
    playbackError = nil
    guard transition?.id == token.id else { return false }
    closeNote = nil
    guard transition?.id == token.id else { return false }
    isTransitioning = false
    guard transition?.id == token.id else {
      if transition != nil, !isTransitioning { isTransitioning = true }
      return false
    }
    guidedReleasedVisit = visit
    guidedMediaVisit = nil
    guidedReviewSubmission = nil
    guidedPracticeFreshTryID = nil
    participationCompletion = nil
    participationSaveAnnouncement = nil
    guard transition?.id == token.id else { return false }
    transition = nil
    return true
  }

  /// @Published emits from willSet, before storage: a subscriber can begin Close/background
  /// and the outer write still stores afterwards. Hold this token through every published
  /// write and revalidate after each. A winning intent gets back exactly the pre-advance
  /// word, phase and completion it would have seen had it won during cleanup.
  private func commitAdvance(_ token: Transition) -> Bool {
    let advancedSessionID = sessionID
    let previousWords = completedWords
    let previousPhase = phase
    var completion: PracticeParticipation?
    func isCurrent() -> Bool { transition?.id == token.id && sessionID == advancedSessionID }
    func revoke() -> Bool {
      if sessionID == advancedSessionID {
        if let completion, participationCompletion == completion {
          participationCompletion = nil
          participationSaveAnnouncement = nil
          guard sessionID == advancedSessionID else { return false }
        }
        if completedWords != previousWords { completedWords = previousWords }
        if phase != previousPhase { phase = previousPhase }
      }
      // A begin nested inside an outer `isTransitioning = false` was overwritten on store.
      if transition != nil, !isTransitioning { isTransitioning = true }
      updateCloseNote()
      return false
    }
    completedWords = previousWords + 1
    guard isCurrent() else { return revoke() }
    // Still held: no action entry point admits while a transition token exists.
    closeNote = nil
    fileCloseWarningIssued = false
    playbackError = nil
    isTransitioning = false
    guard isCurrent() else { return revoke() }
    if completedWords == totalWords {
      // Match the numeric epoch precision used by the participation store, so its
      // exact saved row can acknowledge this completion without a false save failure.
      let committed = PracticeParticipation(
        id: advancedSessionID,
        completedAt: Date(timeIntervalSince1970: Date().timeIntervalSince1970),
        soundID: sound.id, wordCount: completedWords)
      completion = committed
      participationCompletion = committed
      phase = .completed
    } else {
      phase = .ready
    }
    guard isCurrent() else { return revoke() }
    // Unpublished release. The store write keeps its own revalidation; a Close during its
    // entry publication may let that entry commit but never labels a successor Saved.
    transition = nil
    if let completion { saveParticipation(completion, retrying: false) }
    return false
  }

  /// Async end/recovery APIs join the same disposal scheduled by synchronous
  /// observers. A pending or refused cleanup is never acknowledged as ended.
  private func finishEnd(_ token: Transition) async -> Bool {
    guard token.intent == .end, transition?.id == token.id else { return phase == .ended }
    let committed = commitEnd(token)
    if !committed, let pending = wordRuntimeRelease { _ = await pending.value }
    return phase == .ended
  }

  private func commitEnd(_ token: Transition) -> Bool {
    guard token.intent == .end, transition?.id == token.id,
      (endAudioCleanupConfirmed && !cleanupBlocked)
        || (fileRecoveryExitAuthorized && canLeavePendingFileRecovery)
    else { return false }
    guard mirrorCloseStop != nil, mirror.isReleasedForClose else {
      updateCloseNote()
      return false
    }
    // All end routes (including recovery callbacks) share this gate. File/timer
    // cleanup has already joined; phase.ended never acknowledges disposal early.
    if !wordRuntimeReleased, let runtime = wordRecognizer as? any LocalWordRuntimeReleasing {
      if wordRuntimeRelease == nil {
        wordRuntimeRelease = Task { @MainActor [self] in
          let released = await runtime.releaseWordRuntime()
          wordRuntimeRelease = nil
          guard released, transition?.id == token.id else { return false }
          wordRuntimeReleased = true
          return commitEnd(token)
        }
      }
      return false
    }
    transition = nil
    isTransitioning = false
    closeNote = nil
    fileCloseWarningIssued = false
    fileRecoveryExitAuthorized = false
    playbackError = nil
    phase = .ended
    return true
  }

  private func receivePlaybackState(_ state: PracticePlaybackRuntimeState) {
    switch state {
    case .idle: break
    case .preparing(let operation), .playing(let operation), .stopping(let operation),
      .cleanupBlocked(let operation):
      guard operation.id == activePlaybackID else { return }
    }
    playbackState = state
    if case .playing = state { isPlaying = true } else { isPlaying = false }
    if case .cleanupBlocked = state {
      cleanupBlocked = true
      if let token = transition, token.intent == .advance {
        // Synchronous negative publication precedes the awaiting consumer's resumption.
        // Later recovery can release resources, but cannot restore this Continue's intent.
        failedAdvanceTransitionID = token.id
      }
    }
    let recoveredPlayback = reconcileCompletedPlaybackRetry()
    if recoveredPlayback { resumeConfirmedCleanupIfPossible() }
    updateCloseNote()
  }

  private func updateCloseNote() {
    if transition?.intent == .end, spokenWordState != .idle {
      closeNote =
        hasSpokenWordCleanupIssue
        ? "The spoken word hasn't confirmed it stopped, so this screen stays open. Use Retry stopping word."
        : "Stopping the spoken word before closing. This screen closes once it has stopped."
      return
    }
    if transition?.intent == .end, wordCheckOperation != nil || wordCleanupUnconfirmed {
      closeNote =
        wordCleanupUnconfirmed
        ? "The local word check has not confirmed cleanup. Its recording remains protected."
        : "Stopping the local word check before closing. Its recording stays protected until cleanup finishes."
      return
    }
    guard transition?.intent == .end else {
      closeNote = nil
      return
    }
    if hasPlaybackCleanupIssue {
      closeNote =
        "Playback hasn't confirmed it stopped, so this screen stays open. Use Retry stopping."
    } else if captureCleanupState.hasHardwareIssue || !pendingCaptureHardwareOwners.isEmpty {
      closeNote =
        "Microphone cleanup is not confirmed, so this screen stays open. Use Retry cleanup."
    } else if playbackState != .idle {
      closeNote = "Stopping playback before closing. This screen closes once it has stopped."
    } else if cleanupBlocked {
      closeNote =
        canLeavePendingFileRecovery
        ? "The recording couldn't be removed. Use Retry cleanup, or tap Close again to leave it pending."
        : "The recording couldn't be removed, so this screen stays open. Use Retry cleanup."
    } else {
      if !mirror.isReleasedForClose {
        if case .stopFailed = mirror.state {
          closeNote =
            "The camera hasn't confirmed it turned off, so this screen stays open. Use Retry turning off camera."
        } else {
          closeNote = "Turning off the camera before closing. This screen closes once it has."
        }
      } else {
        closeNote = nil
      }
    }
  }

  private var canLeavePendingFileRecovery: Bool {
    guard fileCloseWarningIssued, !isTransitioning, cleanupTask == nil,
      spokenWordState == .idle, activeSpokenWord == nil,
      wordCheckOperation == nil, !wordCleanupUnconfirmed,
      playbackState == .idle, activePlaybackID == nil,
      !captureCleanupState.hasHardwareIssue, pendingCaptureHardwareOwners.isEmpty,
      let cleanupOwnership,
      cleanupOwnership.hardware.currentLease == nil,
      !captureCleanupState.fileBlockedOwnerIDs.isEmpty,
      // Every retained take needs its own requested, exact producer identity. One file's
      // registered recovery never stands in for a nil-owner or unrequested sibling.
      takes.allSatisfy({ $0.removalRequested && $0.recording.cleanupOwnerID != nil })
    else { return false }
    let owners = captureCleanupState.fileBlockedOwnerIDs.union(requestedTakeOwners)
      .union(pendingCaptureOwners)
    return owners.isSubset(of: cleanupOwnership.files.pendingCleanupOwners)
  }

  private var requestedTakeOwners: Set<UUID> {
    Set(takes.filter(\.removalRequested).compactMap(\.recording.cleanupOwnerID))
  }

  /// The takes an intent must remove, computed from the live intent at each discard step.
  /// Without an intent nothing is removed; every deleting caller holds its own token.
  private func removalIDs(for intent: Intent?) -> [UUID] {
    switch intent {
    case nil, .recoverPlayback?: return []
    case .recoverCapture?, .failed(_)?: return takes.filter(\.removalRequested).map(\.id)
    case .prepareTry(let evicting)?:
      return takes.filter { $0.removalRequested || $0.id == evicting }.map(\.id)
    case .ready?, .advance?, .restart?, .more(_)?, .end?, .guidedPrepare?, .guidedLeave?:
      return takes.map(\.id)
    }
  }

  /// Ownership/deletion intents that must hand their files to the real producer even when
  /// cleanup is already blocked. Continue, playback recovery and preparation never discard
  /// on a negative playback acknowledgement.
  private func registersProducerRecovery(_ intent: Intent?) -> Bool {
    switch intent {
    case nil, .advance?, .recoverPlayback?, .prepareTry(_)?: return false
    default: return true
    }
  }

  private func receiveCaptureState(_ event: CaptureCleanupState) {
    // State uses the committed getter; event identities remain useful during reentrancy.
    recordCaptureOwners(event)
    captureCleanupState = capturer.cleanupState
    recordCaptureOwners(captureCleanupState)
    let removedRecording = reconcileCompletedRecordingCleanup()
    let removedCaptureFiles = reconcileCompletedCaptureOwners()
    if removedRecording || removedCaptureFiles { resumeConfirmedCleanupIfPossible() }
    updateCloseNote()
  }

  private func recordCaptureOwners(_ state: CaptureCleanupState) {
    pendingCaptureOwners.formUnion(state.fileBlockedOwnerIDs)
    if let id = state.hardwareBlockedOperationID {
      pendingCaptureOwners.insert(id)
      pendingCaptureHardwareOwners.insert(id)
    }
  }

  @discardableResult
  private func reconcileCompletedCaptureOwners() -> Bool {
    var confirmed = false
    for owner in pendingCaptureOwners {
      guard let receipt = capturer.completedFileCleanup(operationID: owner),
        receipt.operationID == owner, receipt.allRequestedFilesRemoved
      else { continue }
      confirmCaptureOwnerRemoval(receipt)
      confirmed = true
    }
    return confirmed
  }

  private func confirmCaptureHardwareRelease(_ receipt: CaptureCleanupReceipt) {
    guard receipt.hardwareReleased else { return }
    pendingCaptureHardwareOwners.remove(receipt.operationID)
  }

  private func confirmCaptureOwnerRemoval(_ receipt: CaptureCleanupReceipt) {
    confirmCaptureHardwareRelease(receipt)
    guard receipt.allRequestedFilesRemoved else { return }
    pendingCaptureOwners.remove(receipt.operationID)
  }

  @discardableResult
  private func reconcileCompletedRecordingCleanup() -> Bool {
    var removed = false
    // Each retained positive receipt counts even while another owner still fails.
    for owner in takes.compactMap(\.recording.cleanupOwnerID) {
      guard let receipt = capturer.completedFileCleanup(operationID: owner),
        receipt.operationID == owner, receipt.allRequestedFilesRemoved
      else { continue }
      if confirmRecordingRemoval(receipt) { removed = true }
    }
    return removed
  }

  @discardableResult
  private func confirmRecordingRemoval(_ receipt: CaptureCleanupReceipt) -> Bool {
    confirmCaptureOwnerRemoval(receipt)
    guard receipt.allRequestedFilesRemoved,
      takes.contains(where: { $0.recording.cleanupOwnerID == receipt.operationID })
    else { return false }
    takes.removeAll { $0.recording.cleanupOwnerID == receipt.operationID }
    return true
  }

  @discardableResult
  private func reconcileCompletedPlaybackRetry(id requestedID: UUID? = nil) -> Bool {
    guard let id = requestedID ?? activePlaybackID,
      let receipt = player.completedCleanupRetry(id: id),
      receipt.operation.id == id, receipt.result == .released
    else { return false }
    if activePlaybackID == id { activePlaybackID = nil }
    return true
  }

  private func resumeConfirmedCleanupIfPossible() {
    guard wordCheckOperation == nil, !wordCleanupUnconfirmed,
      spokenWordState == .idle, activeSpokenWord == nil,
      activePlaybackID == nil, playbackState == .idle,
      !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
      pendingCaptureOwners.isEmpty,
      !takes.contains(where: \.removalRequested), cleanupTask == nil
    else { return }
    cleanupBlocked = false
    if let token = transition, token.intent == .end {
      Task { @MainActor [self] in _ = await finishTransition(token) }
    }
  }

  private func registerPendingDiscard() {
    guard takes.contains(where: { !$0.removalRequested }) else { return }
    _ = discardRequiredTakes()
    receiveCaptureState(capturer.cleanupState)
  }

  /// Attempts each take the live intent must remove, once per take. Returns false while any
  /// such take remains. A failed deletion never prevents the next independent file's attempt.
  private func discardRequiredTakes() -> Bool {
    let required = removalIDs(for: transition?.intent)
    let fresh = takes.filter { required.contains($0.id) && !$0.removalRequested }
    // Record every removal intent before any producer publication can reenter.
    for index in takes.indices where fresh.contains(where: { $0.id == takes[index].id }) {
      takes[index].removalRequested = true
    }
    for take in fresh {
      do {
        try capturer.discard(take.recording)
        takes.removeAll { $0.id == take.id }
      } catch {
        // An earlier synchronous observer may already have retried the exact failed owner.
        reconcileCompletedRecordingCleanup()
      }
    }
    // A missing exact positive receipt cannot authorize a second producer discard.
    return !takes.contains { required.contains($0.id) }
  }

  private func releasePlayback(id: UUID, acknowledgement: PracticePlaybackCleanup?) async -> Bool {
    guard let acknowledgement else {
      if reconcileCompletedPlaybackRetry(id: id) { return true }
      if activePlaybackID == id {
        cleanupBlocked = true
        return false
      }
      return true
    }
    let receipt = await acknowledgement.value()
    await playbackCleanupReceiptObserver?(receipt)
    guard receipt.operation.id == id, receipt.result == .released else {
      if reconcileCompletedPlaybackRetry(id: id) { return true }
      cleanupBlocked = true
      // Lifecycle/Close cleanup must remain reachable if the view itself is lost.
      // Borrow refusal registers producer recovery and cannot remove the in-use take.
      if registersProducerRecovery(transition?.intent) { registerPendingDiscard() }
      return false
    }
    // Clear using the acknowledgement we actually awaited, including a successful retry.
    // requestStop still returns its original cached negative receipt after such a retry.
    if activePlaybackID == id { activePlaybackID = nil }
    return true
  }

  private func removeTemporaryAudio(retrying: Bool = false) async -> Bool {
    // Speech owns the hardware lease until exact terminal/disposal/deactivation evidence.
    // Its failure cannot authorize deleting a retained take or entering model cleanup.
    if let active = activeSpokenWord {
      guard await releaseSpokenWord(active, retrying: retrying) else { return false }
    }
    // The analyzer's exact terminal receipt precedes every producer deletion.
    // Neither Close nor another cleanup route can release its borrowed take.
    guard await settleWordCheckForCleanup() else { return false }
    if let cleanupTask { return await cleanupTask.value }
    let removedRecording = reconcileCompletedRecordingCleanup()
    let removedCaptureFiles = reconcileCompletedCaptureOwners()
    let releasedPlayback = reconcileCompletedPlaybackRetry()
    if removedRecording || removedCaptureFiles || releasedPlayback {
      resumeConfirmedCleanupIfPossible()
    }
    if cleanupBlocked && !retrying {
      // A stop/natural completion may already have failed before disappearance/Close.
      // Even that later lifecycle intent must hand each take to its real producer once.
      if registersProducerRecovery(transition?.intent) { registerPendingDiscard() }
      return false
    }
    let taskID = UUID()
    cleanupTaskID = taskID
    let playbackID = activePlaybackID
    let ack = playbackID.flatMap {
      retrying && hasPlaybackCleanupIssue ? player.retryCleanup(id: $0) : player.requestStop(id: $0)
    }
    let task = Task { @MainActor [self] in
      defer {
        // A joining deletion intent must not reuse a completed preservation-only task.
        if cleanupTaskID == taskID {
          cleanupTask = nil
          cleanupTaskID = nil
        }
      }
      if let playbackID, !(await releasePlayback(id: playbackID, acknowledgement: ack)) {
        return false
      }
      if let token = transition, token.intent == .advance,
        failedAdvanceTransitionID == token.id
      {
        return false
      }
      var retained = false
      if retrying {
        let before = capturer.cleanupState
        var owners = before.fileBlockedOwnerIDs.union(requestedTakeOwners)
          .union(pendingCaptureOwners)
        if let id = before.hardwareBlockedOperationID { owners.insert(id) }
        // Retry every exact owner; one retained owner does not skip its siblings.
        for id in owners {
          let attempted = capturer.retryCleanup(operationID: id)
          if attempted.operationID == id { confirmCaptureHardwareRelease(attempted) }
          let receipt =
            attempted.operationID == id && attempted.allRequestedFilesRemoved
            ? attempted : capturer.completedFileCleanup(operationID: id)
          guard let receipt, receipt.operationID == id, receipt.allRequestedFilesRemoved else {
            retained = true
            continue
          }
          confirmRecordingRemoval(receipt)
        }
        reconcileCompletedRecordingCleanup()
      }
      // Only the in-progress operation is cancelled; earlier returned takes stay owned.
      do { try capturer.cancel() } catch { retained = true }
      // The original failure remains truthful, but later exact removal is sufficient.
      if !discardRequiredTakes() { retained = true }
      captureCleanupState = capturer.cleanupState
      guard !retained, !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
        pendingCaptureOwners.isEmpty
      else {
        failCaptureCleanup()
        return false
      }
      cleanupBlocked = false
      return true
    }
    cleanupTask = task
    let cleaned = await task.value
    if cleanupTaskID == taskID {
      cleanupTask = nil
      cleanupTaskID = nil
    }
    return cleaned
  }

  private func failCaptureCleanup() {
    cleanupBlocked = true
    phase = .failed(
      captureCleanupState.hasHardwareIssue
        ? AudioCaptureError.hardwareCleanupUnconfirmed.localizedDescription
        : AudioCaptureError.couldNotDeleteTemporaryRecording.localizedDescription)
  }

  private func recordingAssessment(_ summary: CaptureSummary) -> CaptureAssessment {
    switch assessor.assess(summary) {
    case .acceptable:
      return .acceptable
    case .retry(let coaching):
      // The clinical capture flow mentions a tone. This demo starts recording immediately.
      let detail =
        summary.duration < assessor.minimumDuration
        ? "Tap Record, say the word at your own pace, then tap Stop."
        : coaching.detail
      return .retry(CaptureCoaching(title: coaching.title, detail: detail))
    }
  }
}
