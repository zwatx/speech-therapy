#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  enum ResearchFeedbackPhase: Equatable {
    case ready, requestingPermission, recording, review, checking
    case feedback(RecordingFeedback)
    case permissionDenied
    case failed(RecordingFeedbackError)
    case cleanupBlocked, ended
  }

  enum ResearchFeedbackReplaySource: Equatable, Sendable { case earlier, latest }

  struct ResearchFeedbackReplayClip: Equatable, Identifiable, Sendable {
    let id: String
    let summary: CaptureSummary
    let isCurrentTake: Bool
  }

  /// Sole capture/player owner; checks borrow only the current validated temporary take.
  @MainActor
  final class ResearchFeedbackSession: ObservableObject {
    @Published private(set) var phase: ResearchFeedbackPhase = .ready
    @Published private(set) var soundPhase: ResearchSoundPhase = .ready
    @Published private(set) var recognizerWordGuess: ResearchRecognizerWordGuess?
    @Published private(set) var summary: CaptureSummary?
    @Published private(set) var isPlaying = false
    @Published private(set) var playbackFailed = false
    @Published private(set) var failedReplaySource: ResearchFeedbackReplaySource?
    @Published private(set) var isPreparingAnotherTry = false
    @Published private(set) var practiceCompletionState = ResearchFreePracticeCompletionState.active
    @Published private(set) var practiceCompletion: ResearchFreePracticeCompletion?
    @Published private(set) var isFinalizingPractice = false
    @Published private(set) var playbackState: PracticePlaybackRuntimeState = .idle
    @Published private(set) var isAudioCleanupPending = false
    @Published private(set) var playbackCleanupBlocked = false
    @Published private(set) var captureCleanupState: CaptureCleanupState = .idle
    @Published private(set) var closeRequested = false
    var hasLocalMediaCleanupIssue: Bool {
      cleanupBlocked || exampleCleanupBlocked || playbackCleanupBlocked
        || captureCleanupState.hasHardwareIssue || captureCleanupState.hasFileIssue
    }
    var audioTransitionPending: Bool {
      if isAudioCleanupPending || mediaCleanupTask != nil || recoveryTask != nil { return true }
      switch playbackState {
      case .preparing, .stopping: return true
      default: return exampleTask != nil
      }
    }
    var canRetryAudioCleanup: Bool {
      hasLocalMediaCleanupIssue && !isAudioCleanupPending && mediaCleanupTask == nil
        && recoveryTask == nil
        && !permissionPending
    }
    var earlierReplay: ResearchFeedbackReplayClip? {
      let clips = replayClips
      return clips.count == 2 ? replaySnapshot(clips[0]) : nil
    }
    var latestReplay: ResearchFeedbackReplayClip? { replayClips.last.flatMap(replaySnapshot) }
    var activeReplaySource: ResearchFeedbackReplaySource? {
      guard case .recording(let id) = playbackSource else { return nil }
      return earlierReplay?.id == id ? .earlier : latestReplay?.id == id ? .latest : nil
    }
    var playingReplaySource: ResearchFeedbackReplaySource? {
      isPlaying ? activeReplaySource : nil
    }
    @Published private(set) var exampleState: ResearchPracticeExampleState = .idle
    @Published private(set) var exampleCleanupBlocked = false
    var example: ResearchPracticeExample? {
      guard let selectedPrompt, ResearchFeedbackCatalog.prompts.contains(selectedPrompt) else {
        return nil
      }
      return exampleLoader.example(for: selectedPrompt)
    }
    var canPlayExample: Bool {
      if exampleTask != nil || playbackSource == .example {
        return appActive && !closeRequested && !isAudioCleanupPending && !playbackCleanupBlocked
      }
      return activePlaybackID == nil && appActive && !closeRequested && !audioTransitionPending
        && !hasLocalMediaCleanupIssue && !isPreparingAnotherTry && !isFinalizingPractice
        && !permissionPending
        && !isProcessing
        && phase != .recording && phase != .requestingPermission && phase != .ended
        && example != nil
    }
    @Published private(set) var attemptsStarted = 0
    @Published private(set) var attemptsFinished = 0
    @Published private(set) var checksClaimed = 0
    @Published private(set) var sharedProcessingPaused = false
    @Published private(set) var soundDeclaration: ResearchSoundDeclaration?
    @Published var selectedPrompt: ResearchFeedbackPrompt? {
      didSet { if selectedPrompt != oldValue { setupChanged(clearSoundConsent: true) } }
    }
    @Published var practiceContext: ResearchPracticeContext? {
      didSet { if practiceContext != oldValue { setupChanged(clearSoundConsent: true) } }
    }
    @Published var localProcessingEnabled = false {
      didSet { if localProcessingEnabled != oldValue { setupChanged(clearSoundConsent: true) } }
    }
    @Published var soundAdultConfirmed = false {
      didSet { if soundAdultConfirmed != oldValue { setupChanged(clearSoundConsent: false) } }
    }
    @Published var soundProcessingEnabled = false {
      didSet { if soundProcessingEnabled != oldValue { setupChanged(clearSoundConsent: false) } }
    }
    // Guided ownership also independently excludes sound, including programmatic settings.
    @Published var practiceMode = "free" {
      didSet { if practiceMode != oldValue { setupChanged(clearSoundConsent: true) } }
    }
    var isCheckingSound: Bool { soundPhase == .checking }
    var isProcessing: Bool { activeOperation != nil }
    var setupEditable: Bool {
      guidedOwner == nil && !closeRequested && !audioTransitionPending && !isProcessing
        && !permissionPending && !hasLocalMediaCleanupIssue
        && !isPreparingAnotherTry && !isFinalizingPractice
        && phase != .recording
        && phase != .requestingPermission && phase != .ended
    }
    var canRecord: Bool {
      appActive && !recordingUnavailable && !closeRequested && !audioTransitionPending
        && !hasLocalMediaCleanupIssue
        && !isPreparingAnotherTry
        && practiceCompletionState == .active && !isFinalizingPractice
        && !permissionPending && !isProcessing && ownedClips.isEmpty
        && (phase == .ready || phase == .permissionDenied || phase == .failed(.invalidRecording))
        && attemptsStarted < 128
        && soundGeneration < 2_147_483_647
    }
    var canReplay: Bool { canReplay(.latest) }
    func canReplay(_ source: ResearchFeedbackReplaySource) -> Bool {
      // The same source remains cancellable during prepare; a different source needs stop/retap.
      if playbackSource == replayClip(source).map({ .recording($0.take.takeId) }),
        activePlaybackID != nil, !isAudioCleanupPending, !playbackCleanupBlocked
      {
        return appActive && !closeRequested
      }
      return appActive && !closeRequested && !audioTransitionPending && activePlaybackID == nil
        && replayClip(source) != nil && !hasLocalMediaCleanupIssue
        && !isPreparingAnotherTry && !isFinalizingPractice && !permissionPending && !isProcessing
        && phase != .recording && phase != .requestingPermission && phase != .ended
    }
    var canRecordAnotherTry: Bool {
      guard guidedOwner == nil, practiceMode == "free", practiceCompletionState == .active,
        !isFinalizingPractice, let previous = replayClips.last,
        let selectedPrompt, ResearchFeedbackCatalog.prompts.contains(selectedPrompt)
      else { return false }
      return !recordingUnavailable && !closeRequested && !audioTransitionPending
        && previous.take.prompt == selectedPrompt
        && previous.take.context == practiceContext
        && previous.take.setupGeneration == setupGeneration && appActive
        && !hasLocalMediaCleanupIssue && !isPreparingAnotherTry && !permissionPending
        && !isProcessing && pendingRemoteControls == 0 && phase != .recording
        && phase != .requestingPermission && phase != .ended && attemptsStarted < 128
        && soundGeneration < 2_147_483_647
    }
    var canFinishPractice: Bool {
      guard practiceCompletionState == .active, !isFinalizingPractice,
        safeFreePracticeTransition, let visit = freePracticeVisit, matchesFreeVisit(visit),
        ResearchFreePracticeParticipationMapping.soundID(for: visit.prompt) != nil
      else { return false }
      return ownedClips.contains {
        $0.summary != nil && $0.audioSha256 != nil && $0.take.freePracticeVisitID == visit.id
          && $0.take.prompt == visit.prompt && $0.take.context == visit.context
          && $0.take.setupGeneration == visit.setupGeneration
      }
    }
    var canRetryPracticeSave: Bool {
      guard case .completedNotSaved(.writeUnconfirmed) = practiceCompletionState,
        participationWriter != nil, !isFinalizingPractice, safeFreePracticeTransition,
        let visit = freePracticeVisit, matchesFreeVisit(visit),
        practiceCompletion?.id == visit.id
      else { return false }
      return true
    }
    var canPracticeAgain: Bool {
      guard practiceCompletionState != .active, !isFinalizingPractice,
        safeFreePracticeTransition, let visit = freePracticeVisit, matchesFreeVisit(visit),
        practiceCompletion?.id == visit.id
      else { return false }
      return true
    }
    private var safeFreePracticeTransition: Bool {
      guidedOwner == nil && practiceMode == "free" && appActive && !closeRequested
        && !audioTransitionPending && !hasLocalMediaCleanupIssue
        && !permissionPending && !isPreparingAnotherTry && !isProcessing
        && pendingRemoteControls == 0 && phase != .recording
        && phase != .requestingPermission && phase != .ended
    }
    private func matchesFreeVisit(_ visit: FreePracticeVisit) -> Bool {
      guidedOwner == nil && practiceMode == "free" && freePracticeVisit == visit
        && selectedPrompt == visit.prompt && practiceContext == visit.context
        && setupGeneration == visit.setupGeneration
    }
    private func beginFreeVisit() {
      guard guidedOwner == nil, practiceMode == "free", let selectedPrompt,
        ResearchFeedbackCatalog.prompts.contains(selectedPrompt)
      else { return }
      freePracticeVisit = .init(
        id: UUID(), prompt: selectedPrompt, context: practiceContext,
        setupGeneration: setupGeneration)
    }
    private func invalidateFreePractice() {
      finalizationGeneration = nil
      isFinalizingPractice = false
      freePracticeVisit = nil
      practiceCompletion = nil
      practiceCompletionState = .active
    }
    private func beginFinalization() -> UUID {
      let token = UUID()
      finalizationGeneration = token
      isFinalizingPractice = true
      return token
    }
    private func finalizationCurrent(_ token: UUID, visit: FreePracticeVisit) -> Bool {
      finalizationGeneration == token && isFinalizingPractice && matchesFreeVisit(visit)
        && safeFreePracticeTransition && !Task.isCancelled
    }
    private func stopFinalization(_ token: UUID, invalidateVisit: Bool = false) {
      guard finalizationGeneration == token else { return }
      if invalidateVisit {
        invalidateFreePractice()
      } else {
        finalizationGeneration = nil
        isFinalizingPractice = false
      }
    }
    func finishPractice() async {
      guard !Task.isCancelled, canFinishPractice, let visit = freePracticeVisit,
        let soundID = ResearchFreePracticeParticipationMapping.soundID(for: visit.prompt)
      else { return }
      let token = beginFinalization()
      let completion = ResearchFreePracticeCompletion(
        id: visit.id, completedAt: now(), soundID: soundID, wordCount: 1)
      // An injected clock may reenter; never clear a successor's media after it invalidates us.
      guard finalizationCurrent(token, visit: visit) else {
        stopFinalization(token, invalidateVisit: true)
        return
      }
      let cleanup = await startMediaCleanup().value
      guard cleanup.removed else {
        // No acknowledgement survives initial cleanup failure, even if all valid clips are gone.
        stopFinalization(token, invalidateVisit: true)
        return
      }
      await cleanup.controls?.value
      guard finalizationCurrent(token, visit: visit) else {
        stopFinalization(token, invalidateVisit: true)
        return
      }
      saveFreePractice(completion, visit: visit, token: token)
    }
    func retryPracticeSave() async {
      guard !Task.isCancelled, canRetryPracticeSave, let visit = freePracticeVisit,
        let completion = practiceCompletion
      else { return }
      let token = beginFinalization()
      let cleanup = await startMediaCleanup().value
      guard cleanup.removed else {
        stopFinalization(token)
        return
      }
      await cleanup.controls?.value
      guard finalizationCurrent(token, visit: visit) else {
        stopFinalization(token)
        return
      }
      saveFreePractice(completion, visit: visit, token: token)
    }
    private func saveFreePractice(
      _ completion: ResearchFreePracticeCompletion, visit: FreePracticeVisit, token: UUID
    ) {
      guard finalizationCurrent(token, visit: visit) else {
        stopFinalization(token, invalidateVisit: practiceCompletion == nil)
        return
      }
      let state: ResearchFreePracticeCompletionState
      if let participationWriter {
        do {
          try participationWriter.record(
            sessionID: completion.id, completedAt: completion.completedAt,
            soundID: completion.soundID, wordCount: completion.wordCount)
          state = .saved
        } catch { state = .completedNotSaved(.writeUnconfirmed) }
      } else {
        state = .completedNotSaved(.storeUnavailable)
      }
      // A reentrant writer cannot label another setup/visit Saved. Its entered write may commit.
      guard finalizationCurrent(token, visit: visit) else {
        stopFinalization(token, invalidateVisit: practiceCompletion == nil)
        return
      }
      practiceCompletion = completion
      practiceCompletionState = state
      stopFinalization(token)
    }
    func practiceAgain() async {
      guard !Task.isCancelled, canPracticeAgain, let visit = freePracticeVisit else { return }
      let token = beginFinalization()
      let cleanup = await startMediaCleanup().value
      guard cleanup.removed else {
        stopFinalization(token)
        return
      }
      await cleanup.controls?.value
      guard finalizationCurrent(token, visit: visit) else {
        stopFinalization(token)
        return
      }
      invalidateFreePractice()
      beginFreeVisit()
    }
    var canCheck: Bool {
      guard let take = checkableTake, let context = take.context, context.isValid else {
        return false
      }
      return localProcessingEnabled && !wordClaimed && !sharedProcessingPaused
        && pendingRemoteControls == 0
    }
    var canCheckSound: Bool {
      guard let take = checkableTake, let bread = canonicalBread else { return false }
      return guidedOwner == nil && take.context == .adult && practiceContext == .adult
        && take.prompt == bread && selectedPrompt == bread && practiceMode == "free"
        && soundAdultConfirmed && soundProcessingEnabled && !sharedProcessingPaused
        && pendingRemoteControls == 0 && checksClaimed < 128
        && !claimedCaptures.contains(take.captureId)
    }

    private struct Take: Equatable {
      let captureToken: UUID
      let guidedOwner: UUID?
      let freePracticeVisitID: UUID?
      let context: ResearchPracticeContext?
      let prompt: ResearchFeedbackPrompt
      let setupGeneration: Int
      let soundGeneration: Int
      let takeId: String
      let captureId: String
    }
    private enum Operation: Equatable {
      case word(UUID)
      case sound(UUID)
    }
    private let capturer: any AudioCapturing
    private let player: any AcknowledgedPracticeAudioPlaying
    private let processor: any ResearchFeedbackProcessing
    private let wordGuessProcessor: (any ResearchWordGuessProcessing)?
    private let soundProcessor: any ResearchSoundProcessing
    private let exampleLoader: any ResearchPracticeExampleLoading
    private let exampleStore: any ResearchPracticeExampleStoring
    private let participationWriter: (any ResearchGuidedPracticeParticipationRecording)?
    private let now: @MainActor () -> Date
    private struct FreePracticeVisit: Equatable {
      let id: UUID
      let prompt: ResearchFeedbackPrompt
      let context: ResearchPracticeContext?
      let setupGeneration: Int
    }
    private var freePracticeVisit: FreePracticeVisit?
    private var finalizationGeneration: UUID?
    private var exampleTask: Task<Void, Never>?
    private var exampleGeneration: UUID?
    private enum PlaybackSource: Equatable {
      case recording(String)
      case example
    }
    private var playbackSource: PlaybackSource?
    private let sessionId = UUID().uuidString.lowercased()
    private var roundId = UUID().uuidString.lowercased()
    private var soundGeneration = 1
    private var setupGeneration = 0
    // Unvalidated stopped files remain owned until deletion, but are never replay/check sources.
    private struct OwnedClip {
      let recording: CapturedRecording
      let take: Take
      let summary: CaptureSummary?
      let audioSha256: String?
      var cleanupOwnerID: UUID? = nil
    }
    @Published private var ownedClips: [OwnedClip] = []
    private var replayClips: [OwnedClip] { ownedClips.filter { $0.summary != nil } }
    private var recording: CapturedRecording? {
      guard let take else { return nil }
      return ownedClips.first { $0.take == take && $0.summary != nil }?.recording
    }
    private var preparationGeneration: UUID?
    private var preservesPriorClip = false
    private var fullCleanupRequested = false
    private var pendingClipRemovalIDs: Set<String> = []
    private var deferredFullCleanup: AnyCancellable?
    private var captureCallOwners: Set<UUID>?
    private var pendingCaptureOwners: Set<UUID> = []
    private func replaySnapshot(_ clip: OwnedClip) -> ResearchFeedbackReplayClip? {
      guard let summary = clip.summary else { return nil }
      return .init(id: clip.take.takeId, summary: summary, isCurrentTake: clip.take == take)
    }
    private func replayClip(_ source: ResearchFeedbackReplaySource) -> OwnedClip? {
      let clips = replayClips
      return source == .earlier ? (clips.count == 2 ? clips[0] : nil) : clips.last
    }
    private var take: Take?
    private var generation = UUID()  // Capture callback ownership, not sound's wire generation.
    private var activeOperation: Operation?
    private var playbackGeneration: UUID?
    // This exact hardware/borrow identity survives callback, visit and setup revocation.
    private var activePlaybackID: UUID?
    private var retainedExampleURL: URL?
    private var playbackCleanupTask: Task<Bool, Never>?
    private var mediaCleanupTask: Task<(removed: Bool, controls: Task<Void, Never>?), Never>?
    private var recoveryTask: Task<Bool, Never>?
    @MainActor private final class CloseAttempt {
      let token = UUID()
      var cleanup: Task<(removed: Bool, controls: Task<Void, Never>?), Never>?
    }
    private var closeTask: Task<Bool, Never>?
    private var closeGeneration: UUID?
    private var transitionGeneration = UUID()
    private var observations: Set<AnyCancellable> = []
    private var processTask: Task<Void, Never>?
    private var soundTask: Task<Void, Never>?
    private var preparedSound: ResearchSoundPrepared?
    private var controlsTask: Task<Void, Never>?
    private var controlsGeneration: UUID?
    private var serverContextUsed = false
    private var claimedCaptures: Set<String> = []
    private var claimedAttempts: Set<String> = []
    @Published private var pendingRemoteControls = 0
    private var wordClaimed = false
    private var attemptId: UUID?
    private var attemptTerminal = false
    private var cleanupBlocked = false
    @Published private(set) var recordingUnavailable = false
    var audioCleanupMessage: String? {
      if recordingUnavailable {
        return "Recording is unavailable for this visit. Close and reopen after restarting the app."
      }
      if hasLocalMediaCleanupIssue {
        return "Audio cleanup is still pending. Retry cleanup before leaving."
      }
      return nil
    }
    private var exampleRemovalRequested = false
    private var appActive = true
    @Published private var permissionPending = false
    private var permissionWaiters: [CheckedContinuation<Void, Never>] = []
    private var grantedWhileInactive: UUID?
    private var changingSetup = false
    private var guidedOwner: UUID?
    private var guidedActions: (@MainActor (Bool) -> Bool)?
    private var lifecycleObserver: (@MainActor (ResearchFeedbackLifecycleEvent) -> Void)?
    private var lifecycleFinished = true
    var isPermissionPending: Bool { permissionPending }
    var canTransitionGuided: Bool {
      appActive && !closeRequested && !audioTransitionPending && !permissionPending
        && !hasLocalMediaCleanupIssue && !isPreparingAnotherTry
        && !isFinalizingPractice && practiceCompletionState == .active
        && !isProcessing && pendingRemoteControls == 0 && phase != .recording
        && phase != .requestingPermission && phase != .ended
    }
    @discardableResult func installGuidedObserver(
      owner: UUID,
      observer: @escaping @MainActor (ResearchFeedbackLifecycleEvent) -> Void,
      allowsAction: @escaping @MainActor (Bool) -> Bool
    ) -> Bool {
      guard guidedOwner == nil, canTransitionGuided else { return false }
      recognizerWordGuess = nil
      guidedOwner = owner
      lifecycleObserver = observer
      guidedActions = allowsAction
      return true
    }
    func removeGuidedObserver(owner: UUID) {
      guard guidedOwner == owner else { return }
      lifecycleObserver = nil
      // A session used for a guided flow remains ineligible for adult sound.
      guidedActions = { _ in false }
    }
    @discardableResult func clearGuidedMedia() async -> Bool {
      guard appActive, !closeRequested, !audioTransitionPending, !hasLocalMediaCleanupIssue,
        !permissionPending, !isPreparingAnotherTry, !isFinalizingPractice, !isProcessing,
        phase != .recording,
        phase != .requestingPermission, phase != .ended, pendingRemoteControls == 0
      else { return false }
      let setup = setupGeneration
      let transition = transitionGeneration
      invalidateFreePractice()
      let cleanup = await startMediaCleanup().value
      await cleanup.controls?.value
      return cleanup.removed && setupGeneration == setup && transitionGeneration == transition
        && pendingRemoteControls == 0 && !Task.isCancelled && appActive && !closeRequested
    }
    /// Join existing owned cleanup without implicitly retrying a negative acknowledgement.
    @discardableResult func awaitPendingAudioCleanup() async -> Bool {
      if let recoveryTask { return await recoveryTask.value }
      if let mediaCleanupTask { return await mediaCleanupTask.value.removed }
      if let playbackCleanupTask { return await playbackCleanupTask.value }
      return !hasLocalMediaCleanupIssue
    }
    private var lifecycleIdentity: ResearchFeedbackAttemptIdentity? {
      guard let take, let attemptId else { return nil }
      return .init(
        workflowId: take.guidedOwner, attemptId: attemptId,
        captureId: take.captureId, takeId: take.takeId, setupGeneration: take.setupGeneration,
        prompt: take.prompt, context: take.context)
    }
    private func terminal(_ reason: ResearchFeedbackAttemptTerminal) {
      guard !lifecycleFinished, let identity = lifecycleIdentity else { return }
      lifecycleFinished = true
      lifecycleObserver?(.terminal(identity, reason))
    }

    init(
      capturer: (any AudioCapturing)? = nil, player: (any AcknowledgedPracticeAudioPlaying)? = nil,
      processor: (any ResearchFeedbackProcessing)? = nil,
      soundProcessor: (any ResearchSoundProcessing)? = nil,
      exampleLoader: (any ResearchPracticeExampleLoading)? = nil,
      exampleStore: (any ResearchPracticeExampleStoring)? = nil,
      participationWriter: (any ResearchGuidedPracticeParticipationRecording)? = nil,
      now: @escaping @MainActor () -> Date = { Date() },
      wordGuessProcessor: (any ResearchWordGuessProcessing)? = nil
    ) {
      self.capturer = capturer ?? SystemAudioCapturer()
      self.player = player ?? SystemAcknowledgedPracticeAudioPlayer()
      self.processor = processor ?? ResearchFeedbackClient()
      self.wordGuessProcessor = wordGuessProcessor
      self.soundProcessor = soundProcessor ?? ResearchSoundClient()
      self.exampleLoader = exampleLoader ?? ResearchPracticeExampleClient()
      self.exampleStore = exampleStore ?? ResearchPracticeExampleStore()
      self.participationWriter = participationWriter
      self.now = now
      playbackState = self.player.state
      captureCleanupState = self.capturer.cleanupState
      self.player.statePublisher.sink { [weak self] state in
        MainActor.assertIsolated()
        self?.playbackChanged(state)
      }.store(in: &observations)
      self.capturer.cleanupStatePublisher.sink { [weak self] event in
        MainActor.assertIsolated()
        guard let self else { return }
        var owners = event.fileBlockedOwnerIDs
        if let id = event.hardwareBlockedOperationID { owners.insert(id) }
        self.captureCallOwners?.formUnion(owners)
        self.pendingCaptureOwners.formUnion(owners)
        self.captureCleanupState = self.capturer.cleanupState
        // A preceding subscriber may already have recovered this owner. Only its exact
        // positive file receipt can release the session's relationship to the returned take.
        self.reconcileCompletedCaptureFiles()
        if self.captureCleanupState.hasHardwareIssue || self.captureCleanupState.hasFileIssue {
          self.latchLocalCleanup()
        }
      }.store(in: &observations)
    }
    private var canonicalBread: ResearchFeedbackPrompt? {
      ResearchFeedbackCatalog.prompts.first { $0.id == ResearchSoundContract.promptId }
    }
    private var checkableTake: Take? {
      guard appActive, !closeRequested, !audioTransitionPending, !hasLocalMediaCleanupIssue,
        !isPreparingAnotherTry, !isFinalizingPractice,
        practiceCompletionState == .active,
        !isProcessing, !permissionPending, recording != nil,
        phase != .recording, phase != .requestingPermission, phase != .ended, let take,
        take.captureToken == generation, take.setupGeneration == setupGeneration,
        take.soundGeneration == soundGeneration, take.context == practiceContext,
        take.prompt == selectedPrompt
      else { return nil }
      return take
    }

    func startRecording() async {
      guard canRecord, guidedActions?(false) ?? true, let selectedPrompt,
        ResearchFeedbackCatalog.prompts.contains(selectedPrompt)
      else { return }
      let setup = setupGeneration
      let transition = transitionGeneration
      if let visit = freePracticeVisit, matchesFreeVisit(visit) {
        // A fresh explicit Practice again/denied-only visit has no retained media to invalidate.
        let controls = revokeTake()
        guard await stopPlayback().value else { return }
        await controls?.value
        guard !hasLocalMediaCleanupIssue else { return }
      } else {
        guard await discard().value, !Task.isCancelled, appActive, !closeRequested else { return }
      }
      guard setupGeneration == setup, transitionGeneration == transition,
        self.selectedPrompt == selectedPrompt, !Task.isCancelled, appActive, !closeRequested
      else { return }
      await requestCapture(preservingPrior: false)
    }
    func recordAnotherTry() async {
      guard canRecordAnotherTry, let selectedPrompt else { return }
      let token = UUID()
      let context = practiceContext
      let setup = setupGeneration
      preparationGeneration = token
      isPreparingAnotherTry = true
      // Revoke old check eligibility/results before any permission or control suspension.
      let controls = revokeTake()
      let playbackReleased = await stopPlayback().value
      guard preparationGeneration == token, playbackReleased, !Task.isCancelled,
        self.selectedPrompt == selectedPrompt, practiceContext == context,
        setupGeneration == setup, appActive, !closeRequested
      else {
        if preparationGeneration == token {
          preparationGeneration = nil
          isPreparingAnotherTry = false
        }
        return
      }
      if !hasLocalMediaCleanupIssue, ownedClips.count == 2 {
        removeOwnedClip(ownedClips[0].take.takeId)
      }
      if hasLocalMediaCleanupIssue {
        preparationGeneration = nil
        isPreparingAnotherTry = false
        return
      }
      // Controls retain exact old ownership even if this preparation is invalidated.
      await controls?.value
      guard preparationGeneration == token, !Task.isCancelled, appActive,
        guidedOwner == nil, practiceMode == "free", practiceCompletionState == .active,
        !isFinalizingPractice, self.selectedPrompt == selectedPrompt,
        practiceContext == context, setupGeneration == setup, !hasLocalMediaCleanupIssue,
        !permissionPending, !isProcessing, pendingRemoteControls == 0,
        phase != .ended, attemptsStarted < 128, soundGeneration < 2_147_483_647
      else {
        if preparationGeneration == token {
          preparationGeneration = nil
          isPreparingAnotherTry = false
        }
        return
      }
      preparationGeneration = nil
      isPreparingAnotherTry = false
      await requestCapture(preservingPrior: true)
    }
    private func requestCapture(preservingPrior: Bool) async {
      guard !closeRequested, !audioTransitionPending, activePlaybackID == nil,
        !hasLocalMediaCleanupIssue, !isFinalizingPractice, practiceCompletionState == .active,
        ownedClips.count < 2, let selectedPrompt
      else { return }
      if guidedOwner == nil, practiceMode == "free" {
        if freePracticeVisit.map(matchesFreeVisit) != true { beginFreeVisit() }
      }
      preservesPriorClip = preservingPrior
      let token = UUID()
      generation = token
      attemptId = token
      attemptTerminal = false
      take = Take(
        captureToken: token, guidedOwner: guidedOwner,
        freePracticeVisitID: guidedOwner == nil ? freePracticeVisit?.id : nil,
        context: practiceContext,
        prompt: selectedPrompt,
        setupGeneration: setupGeneration, soundGeneration: soundGeneration,
        takeId: UUID().uuidString.lowercased(), captureId: UUID().uuidString.lowercased())
      attemptsStarted += 1
      lifecycleFinished = false
      // Count before the first suspension, including denied or cancelled permission.
      phase = .requestingPermission
      permissionPending = true
      if let identity = lifecycleIdentity { lifecycleObserver?(.started(identity)) }
      // A lifecycle observer can synchronously invalidate the just-started visit.
      guard generation == token, phase == .requestingPermission, !closeRequested else {
        settlePermissionRequest()
        return
      }
      let granted = await capturer.requestPermission()
      settlePermissionRequest()
      // An invalidated permission request still owns the capturer until this return.
      // No replacement request can start and then be cancelled by this stale completion.
      guard generation == token, phase == .requestingPermission else {
        cancelCaptureWithEvidence()
        return
      }
      guard granted else {
        terminal(.permissionDenied)
        finishAttempt()
        if preservesPriorClip {
          _ = revokeTake()
          preservesPriorClip = false
        }
        phase = .permissionDenied
        return
      }
      if !appActive {
        grantedWhileInactive = token
        return
      }
      beginCapture(token)
    }
    private func beginCapture(_ token: UUID) {
      guard appActive, generation == token, phase == .requestingPermission else { return }
      grantedWhileInactive = nil
      let captureAttempt = withCaptureEvidence {
        try capturer.start { [weak self] successful in
          guard let self, self.generation == token, self.phase == .recording else { return }
          if successful {
            self.stopRecording()
          } else {
            self.captureFailed()
          }
        }
      }
      do {
        try captureAttempt.result.get()
        phase = .recording
      } catch {
        if !captureAttempt.owners.isEmpty
          || (error as? AudioCaptureError) == .couldNotDeleteTemporaryRecording
          || (error as? AudioCaptureError) == .hardwareCleanupUnconfirmed
        {
          latchCaptureCleanup(owners: captureAttempt.owners, startup: true)
        }
        captureFailed()
      }
    }
    func stopRecording() {
      guard phase == .recording else { return }
      let captureAttempt = withCaptureEvidence { try capturer.stop() }
      do {
        let clip = try captureAttempt.result.get()
        guard let take else { throw RecordingFeedbackError.invalidRecording }
        // Register the exact returned URL before admission; invalid files also consume a slot.
        ownedClips.append(
          .init(
            recording: clip, take: take, summary: nil, audioSha256: nil,
            cleanupOwnerID: clip.cleanupOwnerID))
        let bytes = try FeedbackPCM.read(clip.url)
        let pcm = try FeedbackPCM.measure(bytes)
        summary = CaptureSummary(
          duration: pcm.durationMilliseconds / 1000, averagePower: Float(pcm.rmsDbfs))
        let hash = FeedbackContract.sha(bytes)
        ownedClips[ownedClips.count - 1] = .init(
          recording: clip, take: take, summary: summary, audioSha256: hash,
          cleanupOwnerID: clip.cleanupOwnerID)
        preservesPriorClip = false
        finishAttempt()
        phase = .review
        if let identity = lifecycleIdentity {
          lifecycleObserver?(.captured(identity, audioSha256: hash))
        }
      } catch {
        if !captureAttempt.owners.isEmpty
          || (error as? AudioCaptureError) == .couldNotDeleteTemporaryRecording
          || (error as? AudioCaptureError) == .hardwareCleanupUnconfirmed
        {
          latchCaptureCleanup(owners: captureAttempt.owners)
        }
        captureFailed()
      }
    }
    private func captureFailed() {
      terminal(.captureFailed)
      if preservesPriorClip {
        let rejectedID = take?.takeId
        _ = revokeTake()
        cancelCaptureWithEvidence()
        if !capturer.cleanupState.hasHardwareIssue, let rejectedID { removeOwnedClip(rejectedID) }
        if !hasLocalMediaCleanupIssue { phase = .failed(.invalidRecording) }
      } else {
        let token = transitionGeneration
        let cleanup = discard()
        let revokedCapture = generation
        Task { [self] in
          if await cleanup.value, transitionGeneration == token, generation == revokedCapture,
            !closeRequested, phase == .ready
          {
            phase = .failed(.invalidRecording)
          }
        }
      }
    }
    func togglePlayback() async { await togglePlayback(.latest) }
    func togglePlayback(_ source: ResearchFeedbackReplaySource) async {
      if let playbackCleanupTask {
        _ = await playbackCleanupTask.value
        return
      }
      guard !Task.isCancelled, let clip = replayClip(source) else { return }
      if activePlaybackID != nil || exampleTask != nil {
        if playbackSource == .recording(clip.take.takeId) {
          _ = await stopPlayback().value
        }
        return
      }
      guard canReplay(source) else { return }
      let token = UUID()
      let id = UUID()
      let setup = setupGeneration
      let visit = transitionGeneration
      let captureGeneration = generation
      playbackGeneration = token
      activePlaybackID = id
      playbackSource = .recording(clip.take.takeId)
      playbackFailed = false
      failedReplaySource = nil
      do {
        try await player.play(id: id, url: clip.recording.url) { [weak self] operation, success in
          guard let self, self.activePlaybackID == operation.id,
            self.playbackGeneration == token, self.transitionGeneration == visit,
            self.setupGeneration == setup, self.generation == captureGeneration
          else { return }
          // The runtime calls completion only after genuine cleanup and borrow release.
          self.activePlaybackID = nil
          self.playbackGeneration = nil
          self.playbackSource = nil
          self.isPlaying = false
          self.playbackFailed = !success
          self.failedReplaySource = success ? nil : source
        }
        guard playbackGeneration == token, activePlaybackID == id,
          transitionGeneration == visit, setupGeneration == setup,
          generation == captureGeneration, !Task.isCancelled
        else {
          if activePlaybackID == id { _ = await stopPlayback().value }
          return
        }
        playbackChanged(player.state)
      } catch {
        guard activePlaybackID == id else { return }
        let eligible =
          playbackGeneration == token && transitionGeneration == visit
          && setupGeneration == setup && generation == captureGeneration && !Task.isCancelled
        _ = await stopPlayback().value
        guard eligible, transitionGeneration == visit, setupGeneration == setup,
          generation == captureGeneration, activePlaybackID == nil || activePlaybackID == id,
          playbackGeneration == nil, !closeRequested
        else { return }
        playbackFailed = true
        failedReplaySource = source
      }
    }
    /// Different sources never enqueue a switch; stop the active source and retap explicitly.
    func toggleExample() {
      if playbackCleanupTask != nil {
        _ = stopPlayback()
        return
      }
      if exampleTask != nil || playbackSource == .example {
        _ = stopPlayback()
        return
      }
      guard activePlaybackID == nil, canPlayExample, let selectedPrompt, let example else { return }
      let token = UUID()
      let setup = setupGeneration
      let visit = transitionGeneration
      let captureGeneration = generation
      exampleGeneration = token
      exampleState = .loading
      let loader = exampleLoader
      exampleTask = Task { [self] in
        do {
          let data = try await loader.load(example: example)
          try Task.checkCancellation()
          guard exampleCurrent(token, prompt: selectedPrompt, setup: setup),
            transitionGeneration == visit
          else { return }
          try ResearchPracticeExampleClient.validate(data, example: example)
          let url = try exampleStore.write(data)
          retainedExampleURL = url
          guard exampleCurrent(token, prompt: selectedPrompt, setup: setup),
            transitionGeneration == visit
          else {
            _ = stopPlayback()
            return
          }
          let id = UUID()
          exampleTask = nil
          playbackGeneration = token
          activePlaybackID = id
          playbackSource = .example
          try await player.play(id: id, url: url) { [weak self] operation, success in
            guard let self, self.activePlaybackID == operation.id,
              self.exampleGeneration == token, self.playbackGeneration == token,
              self.transitionGeneration == visit, self.setupGeneration == setup,
              self.generation == captureGeneration
            else { return }
            self.activePlaybackID = nil
            let cleanup = self.stopPlayback()
            Task { [self] in
              let released = await cleanup.value
              guard transitionGeneration == visit, setupGeneration == setup,
                generation == captureGeneration, !closeRequested, activePlaybackID == nil,
                exampleGeneration == nil,
                released, !success
              else { return }
              exampleState = .failed(.playbackFailed)
            }
          }
          guard exampleGeneration == token, activePlaybackID == id,
            transitionGeneration == visit, setupGeneration == setup, !Task.isCancelled
          else {
            if activePlaybackID == id { _ = await stopPlayback().value }
            return
          }
          playbackChanged(player.state)
        } catch {
          guard exampleGeneration == token, transitionGeneration == visit,
            setupGeneration == setup
          else { return }
          retainedExampleURL = retainedExampleURL ?? exampleStore.ownedURL
          let released = await stopPlayback().value
          guard transitionGeneration == visit, setupGeneration == setup, !closeRequested,
            generation == captureGeneration, activePlaybackID == nil, exampleGeneration == nil,
            released
          else { return }
          exampleState =
            error is CancellationError
            ? .idle
            : .failed((error as? ResearchPracticeExampleError) ?? .unavailable)
        }
      }
    }
    @discardableResult func retryExampleCleanup() -> Task<Bool, Never> {
      retryAudioCleanup()
    }
    private func exampleCurrent(_ token: UUID, prompt: ResearchFeedbackPrompt, setup: Int) -> Bool {
      exampleGeneration == token && selectedPrompt == prompt && setupGeneration == setup
        && appActive && !closeRequested && !hasLocalMediaCleanupIssue && !isPreparingAnotherTry
        && !isFinalizingPractice && !permissionPending
        && !isProcessing && phase != .recording && phase != .requestingPermission && phase != .ended
    }

    func checkRecording() {
      guard canCheck, guidedActions?(true) ?? true, let recording, let take,
        let context = take.context, let attemptId
      else {
        return
      }
      wordClaimed = true
      recognizerWordGuess = nil
      let cleanup = stopPlayback()
      let operation = Operation.word(UUID())
      activeOperation = operation
      phase = .checking
      if let identity = lifecycleIdentity { lifecycleObserver?(.submitted(identity)) }
      guard current(operation, take: take), localProcessingEnabled else { return }
      let processor = self.processor
      // Permanent guided ownership keeps its original processor and observation contract.
      let guessProcessor = guidedOwner == nil && practiceMode == "free" ? wordGuessProcessor : nil
      processTask = Task { [weak self] in
        do {
          guard await cleanup.value, let self, self.current(operation, take: take) else {
            if let self, self.activeOperation == operation {
              self.activeOperation = nil
              self.processTask = nil
              self.terminal(.checkCancelled)
            }
            return
          }
          try Task.checkCancellation()
          let onEvent: @MainActor (ResearchFeedbackProcessingEvent) -> Void = { [weak self] event in
            guard let self, self.current(operation, take: take),
              let identity = self.lifecycleIdentity
            else { return }
            switch event {
            case .requestStarted: self.lifecycleObserver?(.requestStarted(identity))
            case .declarationRejected:
              self.invalidateFreePractice()
              self.lifecycleObserver?(.bindingRejected(identity))
            }
          }
          let result: ResearchWordGuessFeedback
          if let guessProcessor {
            result = try await guessProcessor.process(
              attemptId: attemptId, recording: recording, prompt: take.prompt,
              practiceContext: context, onEvent: onEvent)
          } else {
            result = .init(
              feedback: try await processor.process(
                attemptId: attemptId, recording: recording, prompt: take.prompt,
                practiceContext: context, onEvent: onEvent), wordGuess: nil)
          }
          try Task.checkCancellation()
          guard self.current(operation, take: take), self.localProcessingEnabled else {
            return
          }
          self.processTask = nil
          self.lifecycleFinished = true
          let value = result.feedback
          if let identity = self.lifecycleIdentity {
            self.lifecycleObserver?(.validated(identity, value))
          }
          guard self.current(operation, take: take), self.localProcessingEnabled else { return }
          self.activeOperation = nil
          if value.reason == "cleanup_unconfirmed" || value.reason == "processing_unavailable" {
            self.sharedProcessingPaused = true
          }
          self.recognizerWordGuess = result.wordGuess
          self.phase = .feedback(value)
        } catch {
          guard let self, self.current(operation, take: take) else { return }
          self.processTask = nil
          self.activeOperation = nil
          self.recognizerWordGuess = nil
          let failure = (error as? RecordingFeedbackError) ?? .serviceUnavailable
          self.terminal(
            error is CancellationError
              ? .checkCancelled : failure == .invalidResponse ? .invalidResponse : .checkFailed)
          if failure == .processingUnavailable { self.sharedProcessingPaused = true }
          self.phase = .failed(failure)
        }
      }
    }
    func checkSound() {
      guard canCheckSound, let recording, let take else { return }
      let attempt = UUID().uuidString.lowercased()
      guard !claimedAttempts.contains(attempt) else { return }
      // Claim before declaration/preparation; every failure consumes this capture's sound check.
      claimedCaptures.insert(take.captureId)
      claimedAttempts.insert(attempt)
      checksClaimed += 1
      let cleanup = stopPlayback()
      let operation = Operation.sound(UUID())
      activeOperation = operation
      soundPhase = .checking
      let context = ResearchSoundCheckContext(
        sessionId: sessionId, generation: take.soundGeneration,
        setupGeneration: take.setupGeneration, roundId: roundId, takeId: take.takeId,
        captureId: take.captureId, attemptId: attempt)
      let previousDeclaration = soundDeclaration
      soundTask = Task { [weak self] in
        guard let self else { return }
        guard await cleanup.value, self.currentSound(operation, take: take) else {
          if self.activeOperation == operation {
            self.activeOperation = nil
            self.soundTask = nil
            self.terminal(.checkCancelled)
          }
          return
        }
        do {
          let fresh = try await self.soundProcessor.declaration()
          try Task.checkCancellation()
          guard self.currentSound(operation, take: take) else { return }
          if let previousDeclaration, previousDeclaration.identity != fresh.identity {
            let transition = self.transitionGeneration
            _ = await self.discard().value
            guard self.transitionGeneration == transition, self.phase != .ended,
              self.selectedPrompt == take.prompt, self.practiceContext == take.context,
              self.setupGeneration == take.setupGeneration
            else { return }
            self.soundDeclaration = fresh
            if !fresh.processingAvailable { self.sharedProcessingPaused = true }
            return
          }
          self.soundDeclaration = fresh
          guard self.currentSound(operation, take: take) else { return }
          guard fresh.processingAvailable else {
            self.sharedProcessingPaused = true
            self.soundPhase = .failed(.processingUnavailable)
            self.activeOperation = nil
            self.soundTask = nil
            return
          }
          let prepared = try await self.soundProcessor.prepare(
            recording: recording, declaration: fresh, context: context)
          try Task.checkCancellation()
          guard self.currentSound(operation, take: take) else { return }
          guard prepared.context == context, prepared.declaration == fresh else {
            throw RecordingFeedbackError.invalidResponse
          }
          self.preparedSound = prepared
          self.serverContextUsed = true
          let result = try await self.soundProcessor.observe(prepared)
          try Task.checkCancellation()
          guard self.currentSound(operation, take: take) else { return }
          self.preparedSound = nil
          self.soundTask = nil
          self.activeOperation = nil
          if result.reason == "cleanup_unconfirmed" || result.reason == "processing_unavailable" {
            self.sharedProcessingPaused = true
          }
          self.soundPhase = .observation(result)
        } catch {
          guard self.current(operation, take: take) else { return }
          // A transport error does not confirm remote cleanup; retain exact prepared
          // ownership so a later invalidation can send cancellation/reset.
          self.soundTask = nil
          self.activeOperation = nil
          let failure = (error as? RecordingFeedbackError) ?? .serviceUnavailable
          if failure == .processingUnavailable { self.sharedProcessingPaused = true }
          self.soundPhase = .failed(failure)
        }
      }
    }
    private func current(_ operation: Operation, take: Take) -> Bool {
      appActive && !cleanupBlocked && !isPreparingAnotherTry && !isFinalizingPractice
        && practiceCompletionState == .active && !sharedProcessingPaused
        && activeOperation == operation
        && self.take == take && recording != nil && generation == take.captureToken
        && setupGeneration == take.setupGeneration && soundGeneration == take.soundGeneration
        && practiceContext == take.context && selectedPrompt == take.prompt && phase != .ended
    }
    private func currentSound(_ operation: Operation, take: Take) -> Bool {
      guidedOwner == nil && current(operation, take: take) && take.context == .adult
        && practiceContext == .adult
        && take.prompt == canonicalBread && practiceMode == "free"
        && soundAdultConfirmed && soundProcessingEnabled
    }
    @discardableResult func cancelChecking() -> Task<Bool, Never>? {
      phase == .checking ? discard() : nil
    }
    @discardableResult func cancelSound() -> Task<Bool, Never>? {
      isCheckingSound ? discard() : nil
    }
    @discardableResult func retake() -> Task<Bool, Never>? {
      phase != .ended && !closeRequested ? discard() : nil
    }
    func reset() { if phase != .ended { setupChanged(clearSoundConsent: true) } }
    func advance() async {
      guard !Task.isCancelled, appActive, !audioTransitionPending, !hasLocalMediaCleanupIssue,
        !permissionPending, !isPreparingAnotherTry, !isFinalizingPractice, !isProcessing,
        phase != .ended, !closeRequested, let selectedPrompt,
        let index = ResearchFeedbackCatalog.prompts.firstIndex(of: selectedPrompt)
      else { return }
      let transition = UUID()
      transitionGeneration = transition
      let setup = setupGeneration
      invalidateFreePractice()
      let cleanup = await startMediaCleanup().value
      await cleanup.controls?.value
      guard cleanup.removed, !Task.isCancelled, transitionGeneration == transition,
        setupGeneration == setup, self.selectedPrompt == selectedPrompt, appActive,
        !closeRequested, phase != .ended
      else { return }
      self.selectedPrompt =
        ResearchFeedbackCatalog.prompts[(index + 1) % ResearchFeedbackCatalog.prompts.count]
    }
    /// Synchronous revocation plus a strongly owned task. Duplicate Close joins; failed Close
    /// remains authorized and only explicit recovery may resume its terminal transition.
    @discardableResult func end() -> Task<Bool, Never> {
      if let closeTask { return closeTask }
      if phase == .ended { return Task { true } }
      let attempt = CloseAttempt()
      let task = Task { [self, attempt] in
        // MainActor cannot run this task until the synchronous entry below has bound
        // the actual cleanup task. Reentrant callers already have this same handle.
        guard let cleanup = attempt.cleanup else {
          preconditionFailure("Close entry must bind its owned cleanup before returning")
        }
        let result = await cleanup.value
        await result.controls?.value
        await waitForPermissionSettlement()
        guard closeGeneration == attempt.token else { return false }
        defer { closeTask = nil }
        guard result.removed, !hasLocalMediaCleanupIssue, closeRequested, !permissionPending else {
          return false
        }
        phase = .ended
        soundPhase = .ended
        return true
      }
      // Store the exact owned attempt before any published or lifecycle callbacks.
      closeTask = task
      closeGeneration = attempt.token
      transitionGeneration = UUID()
      closeRequested = true
      invalidateFreePractice()
      // Eligibility/request revocation remains synchronous, before end returns.
      attempt.cleanup = startMediaCleanup()
      lifecycleObserver?(.invalidated)
      return task
    }
    private func settlePermissionRequest() {
      permissionPending = false
      let waiters = permissionWaiters
      permissionWaiters.removeAll()
      for waiter in waiters { waiter.resume() }
    }
    private func waitForPermissionSettlement() async {
      if permissionPending { await withCheckedContinuation { permissionWaiters.append($0) } }
    }
    func appDidBecomeActive() {
      appActive = true
      if let token = grantedWhileInactive { beginCapture(token) }
    }
    func appDidBecomeInactive() {
      appActive = false
      guard phase != .requestingPermission else { return }
      lifecycleCleanup()
    }
    func appDidEnterBackground() {
      appActive = false
      lifecycleCleanup()
    }
    func audioWasInterrupted() { lifecycleCleanup() }
    private func lifecycleCleanup() {
      transitionGeneration = UUID()
      _ = discard()
      lifecycleObserver?(.invalidated)
    }
    private func setupChanged(clearSoundConsent: Bool) {
      guard !changingSetup, phase != .ended else { return }
      changingSetup = true
      if clearSoundConsent { soundAdultConfirmed = false }
      if clearSoundConsent || !soundAdultConfirmed { soundProcessingEnabled = false }
      changingSetup = false
      guard setupGeneration < 2_147_483_647 else {
        _ = end()
        return
      }
      setupGeneration += 1
      // A new setup supersedes a held Close, but joins its resource cleanup.
      closeGeneration = nil
      closeTask = nil
      closeRequested = false
      transitionGeneration = UUID()
      _ = discard()
      soundDeclaration = nil
      lifecycleObserver?(.invalidated)
    }
    private func playbackChanged(_ state: PracticePlaybackRuntimeState) {
      playbackState = state
      isPlaying = false
      switch state {
      case .playing(let operation):
        guard activePlaybackID == operation.id, playbackGeneration != nil else { return }
        if playbackSource == .example { exampleState = .playing } else { isPlaying = true }
      case .preparing(let operation):
        if activePlaybackID == operation.id, playbackSource == .example { exampleState = .loading }
      case .cleanupBlocked(let operation):
        guard activePlaybackID == operation.id else { return }
        playbackCleanupBlocked = true
        latchLocalCleanup()
      case .stopping:
        if playbackSource == .example { exampleState = .idle }
      case .idle: break
      }
    }
    /// Revoke callbacks before obtaining the stable original receipt. Never replace that
    /// receipt with a retry implicitly, and never drop the exact active identity on failure.
    private func revokePlaybackEligibility() {
      playbackGeneration = nil
      playbackSource = nil
      exampleGeneration = nil
      exampleTask?.cancel()
      exampleTask = nil
      isPlaying = false
      if !exampleCleanupBlocked { exampleState = .idle }
    }
    @discardableResult private func stopPlayback() -> Task<Bool, Never> {
      revokePlaybackEligibility()
      retainedExampleURL = retainedExampleURL ?? exampleStore.ownedURL
      if let playbackCleanupTask { return playbackCleanupTask }
      let id = activePlaybackID
      let acknowledgement = id.flatMap { player.requestStop(id: $0) }
      isAudioCleanupPending = true
      let task = Task { [self] in
        defer {
          playbackCleanupTask = nil
          isAudioCleanupPending = false
        }
        if let id {
          guard let acknowledgement else {
            // A start rejected before runtime admission owns no hardware/borrow.
            guard player.state == .idle else {
              playbackCleanupBlocked = true
              return false
            }
            if activePlaybackID == id { activePlaybackID = nil }
            return removeExampleAfterRelease()
          }
          let receipt = await acknowledgement.value()
          guard activePlaybackID == id else {
            return activePlaybackID == nil && !playbackCleanupBlocked
          }
          guard receipt.operation.id == id, receipt.result == .released else {
            playbackCleanupBlocked = true
            latchLocalCleanup()
            return false
          }
          if activePlaybackID == id { activePlaybackID = nil }
        }
        playbackCleanupBlocked = false
        return removeExampleAfterRelease()
      }
      playbackCleanupTask = task
      return task
    }
    private func removeExampleAfterRelease(retrying: Bool = false) -> Bool {
      guard activePlaybackID == nil, !capturer.cleanupState.hasHardwareIssue else { return false }
      guard let url = retainedExampleURL ?? exampleStore.ownedURL else {
        exampleCleanupBlocked = false
        return true
      }
      retainedExampleURL = url
      if exampleStore.ownedURL == nil {
        // A conforming producer drops its URL only after actual removal, including process
        // recovery. Do not rediscard a file that producer has already relinquished.
        retainedExampleURL = nil
        exampleRemovalRequested = false
        exampleCleanupBlocked = false
        exampleState = .idle
        return true
      }
      guard !exampleRemovalRequested || retrying else { return false }
      exampleRemovalRequested = true
      do {
        try exampleStore.remove(url)
        // The producer remains authoritative; deletion must also relinquish its reference.
        guard exampleStore.ownedURL != url else { throw ResearchPracticeExampleError.cleanupFailed }
        retainedExampleURL = nil
        exampleRemovalRequested = false
        exampleCleanupBlocked = false
        exampleState = .idle
        return true
      } catch {
        exampleCleanupBlocked = true
        exampleState = .failed(.cleanupFailed)
        return false
      }
    }
    /// Explicit recovery: playback borrow first, exact capture hardware next, then each file
    /// owner. A released retry may already have deleted a take: never discard it a second time.
    @discardableResult func retryAudioCleanup() -> Task<Bool, Never> {
      if let recoveryTask { return recoveryTask }
      guard canRetryAudioCleanup else { return Task { false } }
      playbackGeneration = nil
      playbackSource = nil
      exampleGeneration = nil
      exampleTask?.cancel()
      exampleTask = nil
      isPlaying = false
      let task = Task { [self] in
        defer { recoveryTask = nil }
        if let id = activePlaybackID {
          guard playbackCleanupBlocked else { return false }
          let receipt: PracticePlaybackCleanupReceipt
          if let completed = player.completedCleanupRetry(id: id) {
            receipt = completed
          } else {
            guard let retry = player.retryCleanup(id: id) else { return false }
            isAudioCleanupPending = true
            receipt = await retry.value()
            isAudioCleanupPending = false
          }
          guard receipt.operation.id == id, receipt.result == .released else { return false }
          if activePlaybackID == id { activePlaybackID = nil }
          playbackCleanupBlocked = false
        }
        var attemptedHardwareOwner: UUID?
        var filesReleased = true
        if let id = capturer.cleanupState.hardwareBlockedOperationID {
          attemptedHardwareOwner = id
          let receipt = capturer.retryCleanup(operationID: id)
          guard receipt.operationID == id, receipt.hardwareReleased else { return false }
          if receipt.allRequestedFilesRemoved {
            confirmedCaptureFilesRemoved(owner: id)
          } else {
            filesReleased = false
          }
        }
        let fileOwners = capturer.cleanupState.fileBlockedOwnerIDs.union(pendingCaptureOwners)
        for id in fileOwners where id != attemptedHardwareOwner {
          let receipt =
            capturer.completedFileCleanup(operationID: id)
            ?? capturer.retryCleanup(operationID: id)
          if receipt.operationID == id, receipt.allRequestedFilesRemoved {
            // Commit each exact success now, even if a later owner in this recovery fails.
            confirmedCaptureFilesRemoved(owner: id)
          } else {
            filesReleased = false
          }
        }
        captureCleanupState = capturer.cleanupState
        reconcileCompletedCaptureFiles()
        guard !captureCleanupState.hasHardwareIssue else {
          return false
        }
        // This independent producer can finish its exact removal even if a private file's
        // removal still fails; no file is removed while hardware/borrow remains held.
        let exampleRemoved = removeExampleAfterRelease(retrying: true)
        guard filesReleased, !captureCleanupState.hasFileIssue else { return false }
        // Only prior authorized removals are retried. A failed replacement must retain the
        // unaffected earlier/latest evidence; full clear still owns every retained take.
        let requestedIDs =
          fullCleanupRequested
          ? ownedClips.map({ $0.take.takeId }) : Array(pendingClipRemovalIDs)
        for id in requestedIDs { removeOwnedClip(id) }
        guard exampleRemoved, pendingClipRemovalIDs.isEmpty,
          !fullCleanupRequested || ownedClips.isEmpty
        else { return false }
        fullCleanupRequested = false
        cleanupBlocked = false
        if !hasLocalMediaCleanupIssue, phase != .ended {
          // A public-only retry does not discard admitted private evidence. Restore its
          // review phase; full cleanup reaches ready only after every take is actually gone.
          let retainsEvidence = !replayClips.isEmpty
          phase = retainsEvidence ? .review : .ready
          soundPhase = retainsEvidence ? .review : .ready
        }
        // Publishing restored review can synchronously authorize full Close. Drain that
        // upgraded intent before this recovery and its joining Close settle.
        if fullCleanupRequested {
          requestFullRemovalIntent()
          reconcileCompletedCaptureFiles()
          guard ownedClips.isEmpty, pendingClipRemovalIDs.isEmpty,
            !exampleCleanupBlocked, !captureCleanupState.hasHardwareIssue,
            !captureCleanupState.hasFileIssue
          else { return false }
          fullCleanupRequested = false
          cleanupBlocked = false
        }
        if closeRequested, let closeToken = closeGeneration {
          // A newer Close joins this recovery and owns its own terminal token. Never await
          // media cleanup here: that task may itself be waiting for this recovery.
          await controlsTask?.value
          await waitForPermissionSettlement()
          guard closeRequested, closeGeneration == closeToken, !permissionPending,
            !hasLocalMediaCleanupIssue, ownedClips.isEmpty, activePlaybackID == nil
          else { return false }
          phase = .ended
          soundPhase = .ended
        }
        return !hasLocalMediaCleanupIssue
      }
      recoveryTask = task
      return task
    }
    private func confirmedCaptureFilesRemoved(owner: UUID) {
      pendingCaptureOwners.remove(owner)
      let ids = Set(ownedClips.filter { $0.cleanupOwnerID == owner }.map { $0.take.takeId })
      ownedClips.removeAll { ids.contains($0.take.takeId) }
      pendingClipRemovalIDs.subtract(ids)
    }
    private func finishAttempt() {
      if attemptId != nil && !attemptTerminal {
        attemptsFinished += 1
        attemptTerminal = true
      }
    }
    private func withCaptureEvidence<Value>(_ action: () throws -> Value)
      -> (result: Result<Value, Error>, owners: Set<UUID>)
    {
      let outer = captureCallOwners
      captureCallOwners = []
      let result = Result { try action() }
      let owners = captureCallOwners ?? []
      captureCallOwners = outer.map { $0.union(owners) }
      return (result, owners)
    }
    private func cancelCaptureWithEvidence() {
      let attempt = withCaptureEvidence { try capturer.cancel() }
      if case .failure = attempt.result { latchCaptureCleanup(owners: attempt.owners) }
    }
    private func latchCaptureCleanup(owners: Set<UUID> = [], startup: Bool = false) {
      let state = capturer.cleanupState
      captureCleanupState = state
      var exactOwners = owners.union(pendingCaptureOwners).union(state.fileBlockedOwnerIDs)
      if let owner = state.hardwareBlockedOperationID { exactOwners.insert(owner) }
      pendingCaptureOwners.formUnion(exactOwners)
      reconcileCompletedCaptureFiles()
      if !exactOwners.isEmpty, pendingCaptureOwners.isEmpty,
        !state.hasHardwareIssue, !state.hasFileIssue,
        exactOwners.allSatisfy({ owner in
          guard let receipt = capturer.completedFileCleanup(operationID: owner) else {
            return false
          }
          return receipt.operationID == owner && receipt.allRequestedFilesRemoved
        })
      {
        if !playbackCleanupBlocked, !exampleCleanupBlocked, pendingClipRemovalIDs.isEmpty {
          cleanupBlocked = false
        }
        return
      }
      if startup, exactOwners.isEmpty, !state.hasHardwareIssue, !state.hasFileIssue,
        ownedClips.isEmpty
      {
        // An identity-free startup scan failure has no operation to recover.
        recordingUnavailable = true
        return
      }
      latchLocalCleanup()
    }
    private func latchLocalCleanup() {
      cleanupBlocked = true
      phase = .cleanupBlocked
      soundPhase = .localCleanupBlocked
    }
    private func reconcileCompletedCaptureFiles() {
      let owners = Set(ownedClips.compactMap { $0.cleanupOwnerID }).union(pendingCaptureOwners)
      for owner in owners {
        if let receipt = capturer.completedFileCleanup(operationID: owner),
          receipt.operationID == owner, receipt.allRequestedFilesRemoved
        {
          confirmedCaptureFilesRemoved(owner: owner)
        }
      }
    }
    private func removeOwnedClip(_ id: String) {
      reconcileCompletedCaptureFiles()
      guard let clip = ownedClips.first(where: { $0.take.takeId == id }) else { return }
      // Issue each producer intent once, including while playback still borrows the file.
      // The producer refuses deletion and registers process-held recovery in that case.
      guard pendingClipRemovalIDs.insert(id).inserted else {
        latchLocalCleanup()
        return
      }
      do {
        try capturer.discard(clip.recording)
        ownedClips.removeAll { $0.take.takeId == id }
        pendingClipRemovalIDs.remove(id)
      } catch {
        // Identity was attached by stop(), before any failure notification. An earlier
        // subscriber's successful retry remains visible after this original throw.
        reconcileCompletedCaptureFiles()
        if ownedClips.contains(where: { $0.take.takeId == id }) {
          latchLocalCleanup()
        } else if let owner = clip.cleanupOwnerID {
          // A failure event may have latched before the reentrant exact retry completed.
          // Clear that latch only through the producer's retained positive receipt.
          latchCaptureCleanup(owners: [owner])
        }
      }
    }
    private func requestFullRemovalIntent() {
      guard !capturer.cleanupState.hasHardwareIssue else {
        retainFullCleanupUntilCaptureRelease()
        return
      }
      for id in ownedClips.map({ $0.take.takeId }) { removeOwnedClip(id) }
      guard let url = retainedExampleURL ?? exampleStore.ownedURL else { return }
      retainedExampleURL = url
      guard !exampleRemovalRequested else { return }
      exampleRemovalRequested = true
      do {
        try exampleStore.remove(url)
        guard exampleStore.ownedURL != url else { throw ResearchPracticeExampleError.cleanupFailed }
        retainedExampleURL = nil
        exampleRemovalRequested = false
        exampleCleanupBlocked = false
      } catch {
        exampleCleanupBlocked = true
        exampleState = .failed(.cleanupFailed)
      }
    }
    /// The producer's publisher keeps this authorized operation alive after view loss.
    /// Release transfers every retained file to actual producer removal/recovery once.
    private func retainFullCleanupUntilCaptureRelease() {
      guard fullCleanupRequested, deferredFullCleanup == nil,
        capturer.cleanupState.hasHardwareIssue
      else { return }
      deferredFullCleanup = capturer.cleanupStatePublisher.sink { [self] _ in
        MainActor.assertIsolated()
        guard !capturer.cleanupState.hasHardwareIssue else { return }
        deferredFullCleanup?.cancel()
        deferredFullCleanup = nil
        guard fullCleanupRequested, activePlaybackID == nil else { return }
        requestFullRemovalIntent()
        captureCleanupState = capturer.cleanupState
        reconcileCompletedCaptureFiles()
      }
    }
    @discardableResult private func discard() -> Task<Bool, Never> {
      invalidateFreePractice()
      let cleanup = startMediaCleanup()
      return Task {
        let result = await cleanup.value
        return result.removed
      }
    }
    /// All destructive entry points synchronously revoke before joining the strongly owned
    /// cleanup task. Failed hardware cleanup forbids every private/public file removal.
    private func startMediaCleanup() -> Task<(removed: Bool, controls: Task<Void, Never>?), Never> {
      preparationGeneration = nil
      isPreparingAnotherTry = false
      fullCleanupRequested = true
      let controls = revokeTake()
      let playback = stopPlayback()
      if let recoveryTask {
        // Upgrade removal intent synchronously; the existing retry processes it after
        // releasing the exact playback/capture resources. Close owns terminal settlement.
        return Task { [self] in
          _ = await recoveryTask.value
          return (
            !hasLocalMediaCleanupIssue && activePlaybackID == nil && ownedClips.isEmpty,
            controls
          )
        }
      }
      if let mediaCleanupTask { return mediaCleanupTask }
      let task: Task<(removed: Bool, controls: Task<Void, Never>?), Never> = Task { [self] in
        defer { mediaCleanupTask = nil }
        _ = await playback.value
        guard activePlaybackID == nil, !playbackCleanupBlocked else {
          requestFullRemovalIntent()
          return (false, controls)
        }
        cancelCaptureWithEvidence()
        captureCleanupState = capturer.cleanupState
        guard !captureCleanupState.hasHardwareIssue else {
          latchLocalCleanup()
          retainFullCleanupUntilCaptureRelease()
          return (false, controls)
        }
        // If capture hardware was blocked, the public file was held until this release too.
        if !exampleCleanupBlocked { _ = removeExampleAfterRelease() }
        for id in ownedClips.map({ $0.take.takeId }) { removeOwnedClip(id) }
        if !hasLocalMediaCleanupIssue {
          fullCleanupRequested = false
          if phase == .cleanupBlocked {
            phase = .ready
            soundPhase = .ready
          }
        }
        return (!hasLocalMediaCleanupIssue, controls)
      }
      mediaCleanupTask = task
      return task
    }
    /// Revoke request identity before control work. Retained clips never become eligible again.
    private func revokeTake() -> Task<Void, Never>? {
      // Keep the old take for its terminal event, but revoke async response/callback eligibility
      // before delivering any reentrant observer notification.
      generation = UUID()
      activeOperation = nil
      revokePlaybackEligibility()
      recognizerWordGuess = nil
      terminal(
        phase == .checking
          ? .checkCancelled
          : phase == .requestingPermission
            ? .permissionCancelled : phase == .recording ? .captureCancelled : .recordedDiscarded)
      let oldPrepared = preparedSound
      // Exhausted generations pause instead of sending a non-increasing reset.
      let oldDeclaration =
        serverContextUsed && soundGeneration < 2_147_483_647
        ? soundDeclaration : nil
      if soundGeneration < 2_147_483_647 {
        soundGeneration += 1
      } else {
        sharedProcessingPaused = true
      }
      roundId = UUID().uuidString.lowercased()
      grantedWhileInactive = nil
      processTask?.cancel()
      soundTask?.cancel()
      processTask = nil
      soundTask = nil
      preparedSound = nil
      serverContextUsed = false
      playbackFailed = false
      failedReplaySource = nil
      finishAttempt()
      summary = nil
      take = nil
      wordClaimed = false
      preservesPriorClip = false
      attemptId = nil
      if !cleanupBlocked, phase != .ended {
        phase = .ready
        soundPhase = .ready
      }
      if oldPrepared != nil || oldDeclaration != nil {
        pendingRemoteControls += 1
        let processor = soundProcessor
        let newer = soundGeneration
        let sessionId = self.sessionId
        let previous = controlsTask
        let token = UUID()
        controlsGeneration = token
        let task = Task { [self] in
          await previous?.value
          var failed = false
          if let oldPrepared {
            do { try await processor.cancel(oldPrepared) } catch { failed = true }
          }
          if let oldDeclaration {
            do {
              try await processor.reset(
                declaration: oldDeclaration, sessionId: sessionId, generation: newer)
            } catch { failed = true }
          }
          self.pendingRemoteControls -= 1
          if self.controlsGeneration == token {
            self.controlsTask = nil
            self.controlsGeneration = nil
          }
          // A failed control request never establishes confirmed remote cleanup.
          if failed { self.sharedProcessingPaused = true }
        }
        controlsTask = task
        return task
      }
      return controlsTask
    }
  }
#endif
