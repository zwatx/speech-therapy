#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  enum ResearchSoundPhase: Equatable {
    case ready, requestingPermission, recording, review, checking, permissionDenied
    case observation(ResearchSoundObservation)
    case failed(RecordingFeedbackError)
    case localCleanupBlocked, ended
  }

  /// Explicit adult-development session, independent of word/guided feedback.
  @MainActor
  final class ResearchSoundSession: ObservableObject {
    @Published private(set) var phase: ResearchSoundPhase = .ready
    @Published private(set) var summary: CaptureSummary?
    @Published private(set) var declaration: ResearchSoundDeclaration?
    @Published private(set) var sharedProcessingPaused = false
    @Published private(set) var declarationLoading = false
    @Published private(set) var isPlaying = false
    @Published private(set) var playbackFailed = false
    @Published private(set) var attemptsStarted = 0
    @Published private(set) var attemptsFinished = 0
    @Published private(set) var checksClaimed = 0
    @Published var adultConfirmed = false {
      didSet {
        if oldValue != adultConfirmed {
          if !adultConfirmed { processingOptIn = false }
          setupChanged()
        }
      }
    }
    @Published var processingOptIn = false {
      didSet { if oldValue != processingOptIn { setupChanged() } }
    }
    @Published var selectedChildAge: Int? {
      didSet { if oldValue != selectedChildAge { setupChanged() } }
    }
    @Published var practiceMode = "free" {
      didSet { if oldValue != practiceMode { setupChanged() } }
    }
    @Published var selectedPromptId = ResearchSoundContract.promptId {
      didSet { if oldValue != selectedPromptId { setupChanged() } }
    }
    var canRecord: Bool {
      appActive && !recordingUnavailable && !actionsPaused && !permissionPending && phase != .ended
        && phase != .checking && phase != .recording && attemptsStarted < 128
        && generation < 2_147_483_647
    }
    var canReplay: Bool {
      recording != nil && !localCleanupFailed && phase != .recording && phase != .checking
        && phase != .ended && !pendingClose && !cleanupRequested && cleanupTask == nil
    }
    var canCheck: Bool {
      !actionsPaused && adultConfirmed && processingOptIn && selectedChildAge == nil
        && practiceMode == "free"
        && selectedPromptId == ResearchSoundContract.promptId && phase == .review
        && recording != nil && !sharedProcessingPaused && !declarationLoading && checksClaimed < 128
        && !claimedCaptures.contains(captureId ?? "")
    }
    private let capturer: any AudioCapturing
    private let player: any AcknowledgedPracticeAudioPlaying
    private let processor: any ResearchSoundProcessing
    private let fileOwnership: ProcessAudioFileOwnership
    private let sessionId = UUID().uuidString.lowercased()
    private var roundId = UUID().uuidString.lowercased()
    private var generation = 1
    private var setupGeneration = 0
    private var recording: CapturedRecording?
    private var captureId: String?
    private var takeId: String?
    private var terminal = true
    private var localCleanupFailed = false
    private var permissionPending = false
    private var appActive = true
    @Published private(set) var playbackState: PracticePlaybackRuntimeState = .idle
    @Published private(set) var captureCleanupState: CaptureCleanupState = .idle
    @Published private(set) var pendingClose = false
    @Published private(set) var audioBusy = false
    @Published private(set) var stoppedPlaybackEvents = 0
    @Published private(set) var activePlaybackID: UUID?
    private var lastPlaybackRequestID: UUID?
    private var announcedStopID: UUID?
    private var eligiblePlaybackID: UUID?
    private var subscriptions: Set<AnyCancellable> = []
    private var playbackStopTask: Task<Bool, Never>?
    private var playbackStopToken: UUID?
    private var cleanupTask: Task<Bool, Never>?
    private var cleanupRequested = false
    private var cleanupOutcome: ResearchSoundPhase = .ready
    @Published private(set) var recordingUnavailable = false
    private var pendingDiscardOwners: Set<UUID> = []
    private var pendingRecordingRecoveryAttempted = false
    private var cleanupFailureWithoutIdentity = false
    private var captureCallOwners: Set<UUID>?

    var playbackPending: Bool { activePlaybackID != nil }
    var canRetryPlaybackCleanup: Bool {
      guard let id = activePlaybackID else { return false }
      if case .cleanupBlocked(let operation) = playbackState, operation.id == id { return true }
      guard let receipt = player.completedCleanupRetry(id: id) else { return false }
      return receipt.operation.id == id && receipt.result == .released
    }
    var actionsPaused: Bool {
      playbackPending || cleanupTask != nil || localCleanupFailed || pendingClose
    }
    var hasRecording: Bool { recording != nil }
    var captureHardwareBlocked: Bool { captureCleanupState.hasHardwareIssue }
    var captureFileBlocked: Bool { captureCleanupState.hasFileIssue || localCleanupFailed }
    var dismissalBlocked: Bool {
      playbackPending || captureHardwareBlocked || pendingClose || permissionPending
    }
    var closeNote: String? {
      guard pendingClose else { return nil }
      if canRetryPlaybackCleanup {
        return
          "Playback hasn't confirmed it stopped, so this screen stays open. Use Retry stopping."
      }
      if playbackPending {
        return "Stopping playback before closing. This screen closes once it has stopped."
      }
      if captureHardwareBlocked {
        return "Microphone cleanup isn't confirmed. This screen stays open until cleanup finishes."
      }
      if captureFileBlocked {
        return canLeaveWithFileRecovery
          ? "The recording couldn't be removed. Retry recording cleanup, or tap Close again to leave. Its cleanup will remain pending."
          : "The recording couldn't be removed. Use Retry recording cleanup. This screen stays open until removal is confirmed."
      }
      return nil
    }
    private var canLeaveWithFileRecovery: Bool {
      let owners = captureCleanupState.fileBlockedOwnerIDs
      return activePlaybackID == nil && !captureHardwareBlocked && !permissionPending
        && !owners.isEmpty && fileOwnership.pendingCleanupOwners.isSuperset(of: owners)
        && owners.isSuperset(of: pendingDiscardOwners)
        && (recording == nil
          || recording?.cleanupOwnerID.map { owners.contains($0) } == true)
        && !cleanupFailureWithoutIdentity
    }
    private var operation: Task<Void, Never>?
    private var prepared: ResearchSoundPrepared?
    private var serverContextUsed = false
    private var claimedCaptures: Set<String> = []
    private var claimedAttempts: Set<String> = []
    private var declarationEpoch = 0

    init(
      capturer: (any AudioCapturing)? = nil, player: (any AcknowledgedPracticeAudioPlaying)? = nil,
      processor: (any ResearchSoundProcessing)? = nil,
      fileOwnership: ProcessAudioFileOwnership = .shared
    ) {
      self.capturer = capturer ?? SystemAudioCapturer()
      self.player = player ?? SystemAcknowledgedPracticeAudioPlayer()
      self.processor = processor ?? ResearchSoundClient()
      self.fileOwnership = fileOwnership
      // Both API contracts require initial and mutation delivery on MainActor. No scheduler hop.
      self.player.statePublisher.sink { [weak self] state in
        MainActor.assumeIsolated { self?.receivePlaybackState(state) }
      }.store(in: &subscriptions)
      self.capturer.cleanupStatePublisher.sink { [weak self] state in
        MainActor.assumeIsolated { self?.receiveCaptureState(state) }
      }.store(in: &subscriptions)
    }
    /// Explicit metadata fetch; it never records or processes a clip.
    func refreshDeclaration() async {
      guard phase != .ended, !pendingClose else { return }
      declarationEpoch += 1
      let epoch = declarationEpoch
      declarationLoading = true
      do {
        let fresh = try await processor.declaration()
        guard epoch == declarationEpoch, phase != .ended else { return }
        declarationLoading = false
        if let old = declaration, old.identity != fresh.identity { invalidate() }
        declaration = fresh
        if !fresh.processingAvailable {
          if phase == .checking { invalidate() }
          sharedProcessingPaused = true
        }
      } catch {
        guard epoch == declarationEpoch, phase != .ended else { return }
        declarationLoading = false
        declaration = nil
      }
    }
    func startRecording() async {
      guard canRecord else { return }
      let cleanup = invalidate()
      let ownedGeneration = generation
      guard await cleanup.value, generation == ownedGeneration, canRecord else { return }
      takeId = UUID().uuidString.lowercased()
      captureId = UUID().uuidString.lowercased()
      attemptsStarted += 1
      terminal = false
      phase = .requestingPermission
      permissionPending = true
      let granted = await capturer.requestPermission()
      permissionPending = false
      // No newer capture starts while permission is outstanding; closing this unused
      // capturer cannot cancel a newer recorder after an ownership change.
      guard ownedGeneration == generation, appActive, phase == .requestingPermission else {
        cancelCaptureWithEvidence()
        return
      }
      guard granted else {
        finishAttempt()
        phase = .permissionDenied
        return
      }
      let captureAttempt = withCaptureEvidence {
        try capturer.start { [weak self] success in
          guard let self, self.generation == ownedGeneration, self.phase == .recording else {
            return
          }
          if success {
            self.stopRecording()
          } else {
            self.invalidate()
            self.recordFailureOutcome()
          }
        }
      }
      do {
        try captureAttempt.result.get()
        phase = .recording
      } catch {
        let identityFreeStartupFailure =
          (error as? AudioCaptureError)
          == .couldNotDeleteTemporaryRecording && captureAttempt.owners.isEmpty
          && capturer.cleanupState == .idle && recording == nil
        if identityFreeStartupFailure {
          recordingUnavailable = true
        } else if !captureAttempt.owners.isEmpty
          || (error as? AudioCaptureError) == .couldNotDeleteTemporaryRecording
          || (error as? AudioCaptureError) == .hardwareCleanupUnconfirmed
        {
          latchLocalCleanup(owners: captureAttempt.owners)
        }
        invalidate()
        audioBusy = (error as? AudioCaptureError) == .hardwareBusy
        recordFailureOutcome()
      }
    }
    func stopRecording() {
      guard phase == .recording else { return }
      let captureAttempt = withCaptureEvidence { try capturer.stop() }
      do {
        let clip = try captureAttempt.result.get()
        recording = clip
        pendingRecordingRecoveryAttempted = false
        let bytes = try FeedbackPCM.read(clip.url)
        let pcm = try FeedbackPCM.measure(bytes)
        summary = .init(duration: pcm.durationMilliseconds / 1000, averagePower: Float(pcm.rmsDbfs))
        finishAttempt()
        phase = .review
      } catch {
        if !captureAttempt.owners.isEmpty
          || (error as? AudioCaptureError) == .couldNotDeleteTemporaryRecording
          || (error as? AudioCaptureError) == .hardwareCleanupUnconfirmed
        {
          latchLocalCleanup(owners: captureAttempt.owners)
        }
        invalidate()
        recordFailureOutcome()
      }
    }
    func togglePlayback() async {
      if activePlaybackID != nil {
        let id = activePlaybackID
        if await requestPlaybackStop().value, lastPlaybackRequestID == id, announcedStopID != id {
          announcedStopID = id
          stoppedPlaybackEvents += 1
        }
        return
      }
      guard canReplay, !actionsPaused, appActive, let recording else { return }
      let id = UUID()
      let visit = generation
      lastPlaybackRequestID = id
      activePlaybackID = id
      eligiblePlaybackID = id
      playbackFailed = false
      audioBusy = false
      do {
        try await player.play(id: id, url: recording.url) { [weak self] identity, success in
          guard let self, self.activePlaybackID == identity.id,
            self.eligiblePlaybackID == identity.id, self.generation == visit
          else { return }
          self.activePlaybackID = nil
          self.isPlaying = false
          self.eligiblePlaybackID = nil
          self.playbackFailed = !success
        }
        guard activePlaybackID == id, eligiblePlaybackID == id, generation == visit else { return }
        isPlaying = true
      } catch {
        guard activePlaybackID == id, eligiblePlaybackID == id, generation == visit else { return }
        isPlaying = false
        if let runtimeError = error as? PracticePlaybackRuntimeError,
          runtimeError == .busy || runtimeError == .reusedOperationID
        {
          activePlaybackID = nil
          eligiblePlaybackID = nil
          audioBusy = runtimeError == .busy
        } else {
          _ = await requestPlaybackStop().value
          guard lastPlaybackRequestID == id, generation == visit, !pendingClose else { return }
          playbackFailed = true
        }
      }
    }
    func checkRecording() {
      guard canCheck, let recording, let captureId, let takeId else { return }
      let capturedDeclaration = declaration
      let attempt = UUID().uuidString.lowercased()
      guard !claimedAttempts.contains(attempt) else { return }
      // Claim before the first suspension, including declaration/hash preparation failures.
      claimedCaptures.insert(captureId)
      claimedAttempts.insert(attempt)
      checksClaimed += 1
      let context = ResearchSoundCheckContext(
        sessionId: sessionId, generation: generation, setupGeneration: setupGeneration,
        roundId: roundId, takeId: takeId, captureId: captureId, attemptId: attempt)
      phase = .checking
      operation = Task { [weak self] in
        guard let self else { return }
        do {
          let fresh = try await self.processor.declaration()
          try Task.checkCancellation()
          guard self.current(context) else { return }
          if let capturedDeclaration, fresh.identity != capturedDeclaration.identity {
            self.invalidate()
            self.declaration = fresh
            if !fresh.processingAvailable { self.sharedProcessingPaused = true }
            return
          }
          self.declaration = fresh  // CSRF rotation does not revoke a take.
          guard fresh.processingAvailable, !self.sharedProcessingPaused else {
            self.sharedProcessingPaused = true
            self.phase = .failed(.processingUnavailable)
            self.operation = nil
            return
          }
          let value = try await self.processor.prepare(
            recording: recording, declaration: fresh, context: context)
          try Task.checkCancellation()
          guard self.current(context), value.context == context, value.declaration == fresh else {
            return
          }
          self.prepared = value
          self.serverContextUsed = true
          let result = try await self.processor.observe(value)
          try Task.checkCancellation()
          guard self.current(context) else { return }
          self.prepared = nil
          self.operation = nil
          if result.reason == "cleanup_unconfirmed" || result.reason == "processing_unavailable" {
            self.sharedProcessingPaused = true
          }
          self.phase = .observation(result)
        } catch {
          guard self.current(context) else { return }
          self.prepared = nil
          self.operation = nil
          self.phase = .failed((error as? RecordingFeedbackError) ?? .serviceUnavailable)
        }
      }
    }
    func cancelChecking() { if phase == .checking { invalidate() } }
    @discardableResult
    func retake() -> Task<Bool, Never> {
      guard phase != .ended else { return Task { false } }
      return invalidate()
    }
    @discardableResult
    func reset() -> Task<Bool, Never> {
      guard phase != .ended, !pendingClose else { return Task { false } }
      let cleanup = invalidate()
      adultConfirmed = false
      processingOptIn = false
      declarationEpoch += 1
      declarationLoading = false
      declaration = nil
      // Claims and sharedProcessingPaused deliberately survive ordinary reset.
      return cleanup
    }
    @discardableResult
    func end() -> Task<Bool, Never> {
      if phase == .ended { return Task { true } }
      if pendingClose, let cleanupTask { return cleanupTask }
      if pendingClose, canLeaveWithFileRecovery {
        phase = .ended
        return Task { true }
      }
      pendingClose = true
      return invalidate()
    }
    func appDidBecomeActive() { appActive = true }
    func appDidBecomeInactive() {
      appActive = false
      invalidate()
    }
    func appDidEnterBackground() {
      appActive = false
      invalidate()
    }
    func audioWasInterrupted() { invalidate() }
    private func current(_ context: ResearchSoundCheckContext) -> Bool {
      appActive && !sharedProcessingPaused && phase == .checking && generation == context.generation
        && setupGeneration == context.setupGeneration && captureId == context.captureId
        && takeId == context.takeId && adultConfirmed && processingOptIn && selectedChildAge == nil
        && practiceMode == "free" && selectedPromptId == ResearchSoundContract.promptId
    }
    private func setupChanged() {
      guard phase != .ended else { return }
      guard setupGeneration < 2_147_483_647 else {
        end()
        return
      }
      setupGeneration += 1
      invalidate()
      declaration = nil
    }
    private func finishAttempt() {
      if !terminal {
        terminal = true
        attemptsFinished += 1
      }
    }
    private func receivePlaybackState(_ state: PracticePlaybackRuntimeState) {
      switch state {
      case .idle:
        playbackState = .idle
        isPlaying = false
      case .preparing(let operation), .playing(let operation), .stopping(let operation),
        .cleanupBlocked(let operation):
        guard activePlaybackID == operation.id else { return }
        playbackState = state
        if state != .playing(operation) { isPlaying = false }
      }
    }
    private func receiveCaptureState(_ state: CaptureCleanupState) {
      // Earlier subscribers can explicitly recover during this notification. The committed
      // getter is current, while exact retained positive receipts remain removal authority.
      var reportedOwners = state.fileBlockedOwnerIDs
      if let owner = state.hardwareBlockedOperationID { reportedOwners.insert(owner) }
      captureCallOwners?.formUnion(reportedOwners)
      pendingDiscardOwners.formUnion(reportedOwners)
      captureCleanupState = capturer.cleanupState
      pendingDiscardOwners.formUnion(captureCleanupState.fileBlockedOwnerIDs)
      if let owner = captureCleanupState.hardwareBlockedOperationID {
        pendingDiscardOwners.insert(owner)
      }
      reconcileCompletedCaptureFiles()
      if captureCleanupState.hasHardwareIssue || captureCleanupState.hasFileIssue {
        localCleanupFailed = true
        phase = .localCleanupBlocked
      } else if pendingDiscardOwners.isEmpty, !cleanupFailureWithoutIdentity {
        localCleanupFailed = false
        if cleanupRequested { _ = scheduleCleanup() }
      }
    }
    private func reconcileCompletedCaptureFiles() {
      var owners = pendingDiscardOwners
      if let owner = recording?.cleanupOwnerID { owners.insert(owner) }
      for owner in owners {
        guard let receipt = capturer.completedFileCleanup(operationID: owner),
          receipt.operationID == owner, receipt.allRequestedFilesRemoved
        else { continue }
        pendingDiscardOwners.remove(owner)
        if recording?.cleanupOwnerID == owner { recording = nil }
      }
    }
    /// Revocation happens before task creation; duplicates share the same owned wait.
    private func requestPlaybackStop() -> Task<Bool, Never> {
      eligiblePlaybackID = nil
      isPlaying = false
      if let playbackStopTask { return playbackStopTask }
      guard let id = activePlaybackID else { return Task { true } }
      guard let acknowledgement = player.requestStop(id: id) else {
        // The runtime owns no such operation (for example, borrow admission was refused).
        if activePlaybackID == id { activePlaybackID = nil }
        return Task { true }
      }
      let token = UUID()
      playbackStopToken = token
      let task = Task { [self] in
        let receipt = await acknowledgement.value()
        let released = receipt.operation.id == id && receipt.result == .released
        if released, activePlaybackID == id { activePlaybackID = nil }
        if playbackStopToken == token {
          playbackStopTask = nil
          playbackStopToken = nil
        }
        return released
      }
      playbackStopTask = task
      return task
    }
    func retryPlaybackCleanup() async {
      guard let id = activePlaybackID else { return }
      let receipt: PracticePlaybackCleanupReceipt
      if let completed = player.completedCleanupRetry(id: id) {
        receipt = completed
      } else {
        guard case .cleanupBlocked = playbackState,
          let acknowledgement = player.retryCleanup(id: id)
        else { return }
        receipt = await acknowledgement.value()
      }
      guard activePlaybackID == id, receipt.operation.id == id, receipt.result == .released else {
        return
      }
      activePlaybackID = nil
      if cleanupRequested { _ = await scheduleCleanup().value }
    }
    func retryCaptureCleanup() async {
      guard activePlaybackID == nil else { return }
      reconcileCompletedCaptureFiles()
      let state = capturer.cleanupState
      var ids = state.fileBlockedOwnerIDs.union(pendingDiscardOwners)
      if let id = state.hardwareBlockedOperationID { ids.insert(id) }
      for id in ids {
        let receipt =
          capturer.completedFileCleanup(operationID: id)
          ?? capturer.retryCleanup(operationID: id)
        if receipt.operationID == id, receipt.allRequestedFilesRemoved {
          pendingDiscardOwners.remove(id)
          if recording?.cleanupOwnerID == id { recording = nil }
        }
      }
      captureCleanupState = capturer.cleanupState
      guard !captureCleanupState.hasHardwareIssue, !captureCleanupState.hasFileIssue,
        !cleanupFailureWithoutIdentity, pendingDiscardOwners.isEmpty
      else { return }
      localCleanupFailed = false
      if cleanupRequested { _ = await scheduleCleanup().value }
    }
    // Retain the failed notification's exact identity even when an earlier observer has
    // completed explicit recovery before the original synchronous call throws.
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
      if case .failure = attempt.result { latchLocalCleanup(owners: attempt.owners) }
    }
    private func latchLocalCleanup(owners reportedOwners: Set<UUID> = []) {
      let state = capturer.cleanupState
      captureCleanupState = state
      var exactOwners = reportedOwners.union(pendingDiscardOwners).union(state.fileBlockedOwnerIDs)
      if let id = state.hardwareBlockedOperationID { exactOwners.insert(id) }
      if let id = recording?.cleanupOwnerID { exactOwners.insert(id) }
      pendingDiscardOwners.formUnion(exactOwners)
      reconcileCompletedCaptureFiles()
      let allRemoved =
        !exactOwners.isEmpty
        && exactOwners.allSatisfy { owner in
          guard let receipt = capturer.completedFileCleanup(operationID: owner) else {
            return false
          }
          return receipt.operationID == owner && receipt.allRequestedFilesRemoved
        }
      if allRemoved, !state.hasHardwareIssue, !state.hasFileIssue,
        pendingDiscardOwners.isEmpty, !cleanupFailureWithoutIdentity
      {
        localCleanupFailed = false
        return
      }
      localCleanupFailed = true
      if exactOwners.isEmpty { cleanupFailureWithoutIdentity = true }
      phase = .localCleanupBlocked
    }
    /// Revoke check/visit eligibility and send exact request cancellation before any cleanup wait.
    @discardableResult
    private func invalidate() -> Task<Bool, Never> {
      cleanupOutcome = .ready
      declarationEpoch += 1
      declarationLoading = false
      let oldPrepared = prepared
      let oldDeclaration = serverContextUsed ? declaration : nil
      serverContextUsed = false
      if generation < 2_147_483_647 { generation += 1 } else { sharedProcessingPaused = true }
      roundId = UUID().uuidString.lowercased()
      operation?.cancel()
      operation = nil
      prepared = nil
      _ = requestPlaybackStop()
      playbackFailed = false
      audioBusy = false
      finishAttempt()
      summary = nil
      takeId = nil
      captureId = nil
      let processor = self.processor
      let sessionId = self.sessionId
      let newer = generation
      if let oldPrepared { Task { try? await processor.cancel(oldPrepared) } }
      if let oldDeclaration {
        Task {
          try? await processor.reset(
            declaration: oldDeclaration, sessionId: sessionId, generation: newer)
        }
      }
      cleanupRequested = true
      return scheduleCleanup()
    }
    func waitForCleanup() async -> Bool {
      if let cleanupTask { return await cleanupTask.value }
      return !cleanupRequested
    }
    private func recordFailureOutcome() {
      cleanupOutcome = .failed(.invalidRecording)
      if !localCleanupFailed { phase = cleanupOutcome }
    }
    /// A borrowed discard is a refusal plus a process-held recovery registration, not deletion.
    /// Only do this once for the held take; v2 capture preserves the original pending failure.
    private func registerHeldTakeRecovery() { discardRecordingOnce() }
    private func discardRecordingOnce() {
      reconcileCompletedCaptureFiles()
      guard let clip = recording, !pendingRecordingRecoveryAttempted else { return }
      pendingRecordingRecoveryAttempted = true
      // Record the producer relationship before its failure publication can reenter us.
      if let owner = clip.cleanupOwnerID { pendingDiscardOwners.insert(owner) }
      do {
        try capturer.discard(clip)
        if let owner = clip.cleanupOwnerID { pendingDiscardOwners.remove(owner) }
        recording = nil
      } catch {
        reconcileCompletedCaptureFiles()
        if recording != nil { latchLocalCleanup() }
      }
    }
    private func scheduleCleanup() -> Task<Bool, Never> {
      if let cleanupTask { return cleanupTask }
      let task = Task { [self] in
        let stoppedID = activePlaybackID
        _ = await requestPlaybackStop().value
        // An explicit retry may have released this exact ID while the original wait returned false.
        // A newer ID is never cleared or treated as the completed owner.
        guard activePlaybackID == nil else {
          if activePlaybackID == stoppedID { registerHeldTakeRecovery() }
          cleanupTask = nil
          return false
        }
        cancelCaptureWithEvidence()
        if recording != nil, !pendingRecordingRecoveryAttempted,
          !capturer.cleanupState.hasHardwareIssue
        {
          discardRecordingOnce()
        }
        reconcileCompletedCaptureFiles()
        let succeeded =
          !localCleanupFailed && !capturer.cleanupState.hasHardwareIssue
          && !capturer.cleanupState.hasFileIssue && pendingDiscardOwners.isEmpty && recording == nil
        cleanupTask = nil
        if succeeded {
          cleanupRequested = false
          phase = pendingClose ? .ended : cleanupOutcome
        }
        return succeeded
      }
      cleanupTask = task
      return task
    }
  }
#endif
