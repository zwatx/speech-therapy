@preconcurrency import AVFoundation
import CadenceContracts
import Combine
import Foundation

enum PracticePhase: Equatable {
  case ready
  case requestingPermission
  case recording
  case captured(CaptureSummary)
  case submitting(CaptureSummary)
  case saved(LearnerAttemptReceipt)
  case retry(CaptureCoaching)
  case retryLimitReached
  case completed
  case permissionDenied
  case failed(String)
}

@MainActor
final class PracticeSessionModel: ObservableObject {
  @Published private(set) var phase: PracticePhase = .ready
  @Published private(set) var visualState: VisualCaptureState = .off
  @Published private(set) var currentRepetition = 1
  @Published private(set) var currentRetry = 0
  @Published private(set) var assignmentRefreshRequired = false

  let assignment: LearnerPracticeAssignment
  var promptWord: String { assignment.prompt }
  var targetLabel: String { assignment.targetLabel }
  var assignmentProgress: String {
    "\(min(currentRepetition, assignment.attemptTarget)) of \(assignment.attemptTarget)"
  }
  var cameraStatus: String {
    switch visualState {
    case .off:
      if finalizedVisualFeasibilityReportData != nil {
        "Camera off; feasibility report ready to export"
      } else {
        visualConfiguration.isEnabled
          ? "Optional camera framing is off"
          : "Camera off for this target"
      }
    case .requestingPermission:
      "Checking camera permission"
    case .checking:
      "Checking face and mouth framing on this device"
    case .ready:
      "Face and mouth framing ready"
    case .coaching(let coaching, _):
      coaching.title
    case .permissionDenied:
      "Camera off; audio practice is still available"
    case .unavailable:
      "Camera check unavailable; continuing without it"
    }
  }

  var cameraSystemImage: String {
    switch visualState {
    case .ready:
      "video.fill"
    case .checking, .requestingPermission, .coaching:
      "viewfinder"
    case .off, .permissionDenied, .unavailable:
      "video.slash.fill"
    }
  }

  var cameraPreviewSession: AVCaptureSession? {
    guard visualConfiguration.isEnabled else { return nil }
    return visualMonitor?.previewSession
  }

  var visualCaptureAvailable: Bool {
    visualConfiguration.isEnabled && finalizedVisualFeasibilityReportData == nil
  }

  var visualFeasibilityScenarioLabel: String? {
    visualConfiguration.feasibilityScenario?.rawValue
  }

  var visualFeasibilityReportAvailable: Bool {
    finalizedVisualFeasibilityReportData != nil
      || (visualFeasibilityAccumulator?.totalFrames ?? 0) > 0
  }

  var visualFeasibilityReportIsFinalized: Bool {
    finalizedVisualFeasibilityReportData != nil
  }

  func finalizeVisualFeasibilityReport() -> Data? {
    if let finalizedVisualFeasibilityReportData {
      return finalizedVisualFeasibilityReportData
    }
    guard (visualFeasibilityAccumulator?.totalFrames ?? 0) > 0 else { return nil }
    visualCaptureGeneration = nil
    visualCaptureActivated = false
    visualMonitor?.stop()
    visualState = .off
    guard let data = visualFeasibilityReportData() else { return nil }
    visualFeasibilityAccumulator = nil
    finalizedVisualFeasibilityReportData = data
    return data
  }

  func completeVisualFeasibilityExport() {
    finalizedVisualFeasibilityReportData = nil
  }

  private func visualFeasibilityReportData() -> Data? {
    guard
      let accumulator = visualFeasibilityAccumulator,
      let report = accumulator.report(
        endedAt: Date(),
        device: VisualFeasibilityDeviceMetadata.current()
      )
    else { return nil }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    return try? encoder.encode(report)
  }

  var showsCameraPreview: Bool {
    switch visualState {
    case .checking, .ready, .coaching:
      true
    case .off, .requestingPermission, .permissionDenied, .unavailable:
      false
    }
  }

  private let capturer: AudioCapturing
  private let assessor: CaptureQualityAssessor
  private let submitter: (any AttemptSubmitting)?
  private let attemptContext: LearnerAttemptContext?
  private let visualConfiguration: VisualPracticeConfiguration
  private let visualMonitor: (any VisualCaptureMonitoring)?
  private let visualAssessor: VisualCaptureQualityAssessor
  @Published private var cleanupSnapshot = CaptureCleanupState.idle
  /// Authoritative committed state; notifications drain serially across explicit reentry.
  var captureCleanupState: CaptureCleanupState { captureCleanup.state }
  private var isRefreshingCleanup = false
  private var cleanupRefreshPending = false
  private var cleanupRetryRequested = false
  @Published private(set) var captureDisabledForVisit = false
  private let captureCleanup: CaptureVisitCleanup
  private var closed = false
  private var pendingRecording: CapturedRecording? { captureCleanup.recording }
  var captureCleanupRetryIDs: [UUID] { captureCleanup.retryIDs }
  var hasCaptureCleanupIssue: Bool { captureCleanup.hasIssue || captureDisabledForVisit }
  var canLeaveWithFileWarning: Bool { captureCleanup.canLeaveWithFileWarning }
  var requiresCaptureCleanupBeforeDeparture: Bool { captureCleanup.hasRequestedResources }
  var canRefreshAssignment: Bool {
    !captureCleanup.hasRequestedResources && pendingRecording == nil
      && phase != .recording && phase != .requestingPermission
  }
  var captureCleanupDetail: String {
    if captureCleanupState.hasHardwareIssue {
      return "Microphone cleanup is not confirmed. Retry cleanup before leaving or recording."
    }
    if captureCleanupState.hasFileIssue {
      return canLeaveWithFileWarning
        ? "A recording is still retained on this device. Retry cleanup, or choose Unlink again to leave with this warning."
        : "A recording could not be removed. Retry cleanup before continuing."
    }
    if captureCleanup.hasUnidentifiedFailure {
      return "Cleanup could not be confirmed. Keep this screen open while cleanup is resolved."
    }
    return "Recording is disabled for this visit. Close or refresh practice before trying again."
  }
  private var submissionGeneration: UUID?
  private var recordingGeneration: UUID?
  private var visualCaptureGeneration: UUID?
  private var visualCaptureActivated = false
  private var visualFeasibilityAccumulator: VisualFeasibilityAccumulator?
  private var finalizedVisualFeasibilityReportData: Data?

  init(
    assignment: LearnerPracticeAssignment = .localPreview,
    capturer: AudioCapturing? = nil,
    assessor: CaptureQualityAssessor = CaptureQualityAssessor(),
    submitter: (any AttemptSubmitting)? = nil,
    attemptContext: LearnerAttemptContext? = nil,
    visualConfiguration: VisualPracticeConfiguration = .disabled,
    visualMonitor: (any VisualCaptureMonitoring)? = nil,
    visualAssessor: VisualCaptureQualityAssessor = VisualCaptureQualityAssessor(),
    hardwareOwnership: AudioHardwareOwnership = .shared,
    fileOwnership: ProcessAudioFileOwnership = .shared
  ) {
    precondition(
      attemptContext == nil
        || (attemptContext?.assignmentID == assignment.assignmentID
          && attemptContext?.exerciseID == assignment.exerciseID),
      "Displayed assignment must match submitted attempt context."
    )
    self.assignment = assignment
    switch assignment.progress {
    case .ready(_, let repetitionIndex, let retryIndex):
      currentRepetition = repetitionIndex
      currentRetry = retryIndex
    case .retryLimitReached(_, let repetitionIndex):
      currentRepetition = repetitionIndex
      currentRetry = assignment.retryLimit
      phase = .retryLimitReached
    case .completed:
      currentRepetition = assignment.attemptTarget
      currentRetry = 0
      phase = .completed
    }
    let capturer =
      capturer
      ?? SystemAudioCapturer(
        fileOwnership: fileOwnership, hardwareOwnership: hardwareOwnership)
    self.capturer = capturer
    captureCleanup = CaptureVisitCleanup(
      capturer: capturer, hardware: hardwareOwnership, files: fileOwnership)
    self.assessor = assessor
    self.submitter = submitter
    self.attemptContext = attemptContext
    self.visualConfiguration = visualConfiguration
    self.visualMonitor =
      visualConfiguration.isEnabled
      ? (visualMonitor ?? SystemVisualCaptureMonitor())
      : nil
    self.visualAssessor = visualAssessor
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
      if captureCleanup.hasIssue || captureCleanup.disabledForVisit {
        recordingGeneration = nil
        submissionGeneration = nil
        let failedPhase = PracticePhase.failed(captureCleanupDetail)
        if phase != failedPhase { phase = failedPhase }
      } else if restoreReady, !captureCleanup.blocksRecording, !assignmentRefreshRequired, !closed {
        switch assignment.progress {
        case .completed: phase = .completed
        case .retryLimitReached: phase = .retryLimitReached
        case .ready: phase = .ready
        }
      }
    }
  }

  func retryCaptureCleanup(operationID: UUID) {
    guard captureCleanup.canRetry(operationID: operationID) else { return }
    recordingGeneration = nil
    submissionGeneration = nil
    cleanupRetryRequested = true
    _ = captureCleanup.retry(operationID: operationID)
    refreshCaptureCleanup()
  }

  @discardableResult
  func requestClose() -> Bool {
    closed = true
    recordingGeneration = nil
    if submissionGeneration != nil { assignmentRefreshRequired = true }
    submissionGeneration = nil
    visualCaptureGeneration = nil
    visualCaptureActivated = false
    visualMonitor?.stop()
    if visualConfiguration.isEnabled { visualState = .off }
    let released = captureCleanup.requestClose()
    refreshCaptureCleanup()
    return released
  }

  func viewDidDisappear() { _ = requestClose() }

  func prepareVisualCapture() async {
    guard !closed, visualCaptureAvailable, let visualMonitor else {
      visualState = .off
      return
    }
    visualCaptureActivated = true
    guard visualState == .off || visualState == .permissionDenied else { return }
    let generation = UUID()
    visualCaptureGeneration = generation
    visualState = .requestingPermission
    guard await visualMonitor.requestPermission() else {
      guard visualCaptureGeneration == generation else { return }
      visualCaptureGeneration = nil
      visualState = .permissionDenied
      return
    }
    guard visualCaptureGeneration == generation else { return }
    visualState = .checking
    do {
      try await visualMonitor.start { [weak self] result in
        Task { @MainActor [weak self] in
          self?.receiveVisualQuality(result, generation: generation)
        }
      }
    } catch {
      guard visualCaptureGeneration == generation else { return }
      visualCaptureGeneration = nil
      visualState = .unavailable(
        (error as? LocalizedError)?.errorDescription
          ?? "Face framing could not be checked."
      )
    }
  }

  func resumeVisualCaptureIfActivated() async {
    guard visualCaptureActivated else { return }
    await prepareVisualCapture()
  }

  func startRecording() async {
    refreshCaptureCleanup()
    guard !closed, !captureCleanup.blocksRecording, phase == .ready else { return }
    let generation = UUID()
    recordingGeneration = generation
    phase = .requestingPermission

    let granted = await capturer.requestPermission()
    guard recordingGeneration == generation, phase == .requestingPermission else { return }
    guard granted else {
      recordingGeneration = nil
      phase = .permissionDenied
      return
    }
    do {
      captureCleanup.willStart()
      try capturer.start { [weak self] successfully in
        guard let self, self.recordingGeneration == generation else { return }
        await self.recordingDidFinish(successfully: successfully)
      }
      guard recordingGeneration == generation, !closed, !captureCleanup.hasIssue,
        !captureCleanup.disabledForVisit
      else { return }
      phase = .recording
    } catch {
      recordingGeneration = nil
      captureCleanup.failed(error, duringStart: true)
      if case AudioCaptureError.hardwareBusy = error {
        phase = .failed("Audio is still in use. Try again after it finishes.")
        return
      }
      _ = captureCleanup.removeRequestedMedia()
      refreshCaptureCleanup()
      guard !hasCaptureCleanupIssue else { return }
      phase = .failed(
        (error as? LocalizedError)?.errorDescription
          ?? "The microphone could not start. Please try again."
      )
    }
  }

  private func recordingDidFinish(successfully: Bool) async {
    guard phase == .recording else { return }
    if successfully {
      await stopRecording()
    } else {
      cancelRecording()
      // Preserve a cleanup failure if cancel could not remove the temporary recording.
      if phase == .ready {
        phase = .failed("The recording ended unexpectedly. Please try again.")
      }
    }
  }

  func stopRecording() async {
    guard phase == .recording else { return }
    recordingGeneration = nil
    do {
      let recording = try capturer.stop()
      captureCleanup.captured(recording)
      switch assessor.assess(recording.summary) {
      case .acceptable:
        guard let submitter, let attemptContext else {
          guard captureCleanup.removeRequestedMedia(), !captureCleanup.disabledForVisit else {
            refreshCaptureCleanup()
            return
          }
          phase = .captured(recording.summary)
          return
        }
        let generation = UUID()
        submissionGeneration = generation
        phase = .submitting(recording.summary)
        // A synchronous phase observer can Close before any submission begins.
        guard submissionGeneration == generation, !closed,
          pendingRecording?.cleanupOwnerID == recording.cleanupOwnerID,
          pendingRecording?.url == recording.url, !captureCleanup.hasIssue
        else {
          refreshCaptureCleanup()
          return
        }
        let receipt: LearnerAttemptReceipt
        do {
          receipt = try await submitter.submit(
            recording: recording, attemptID: "attempt-\(UUID().uuidString)",
            context: try attemptContext.slot(
              repetitionIndex: currentRepetition, retryIndex: currentRetry))
        } catch {
          guard submissionGeneration == generation else { return }
          submissionGeneration = nil
          assignmentRefreshRequired = true
          if captureCleanup.removeRequestedMedia() {
            phase = .failed(
              "The last save could not be confirmed. Refresh practice before recording again.")
          } else {
            refreshCaptureCleanup()
          }
          return
        }
        guard submissionGeneration == generation else { return }
        submissionGeneration = nil
        guard captureCleanup.removeRequestedMedia(), !captureCleanup.disabledForVisit else {
          // A save may have committed, but cleanup-only recovery cannot grant a late saved phase.
          assignmentRefreshRequired = true
          refreshCaptureCleanup()
          return
        }
        phase = .saved(receipt)
      case .retry(let coaching):
        guard captureCleanup.removeRequestedMedia(), !captureCleanup.disabledForVisit else {
          refreshCaptureCleanup()
          return
        }
        phase = .retry(coaching)
      }
    } catch {
      captureCleanup.failed(error)
      _ = captureCleanup.removeRequestedMedia()
      refreshCaptureCleanup()
      if !hasCaptureCleanupIssue {
        phase = .failed(
          (error as? LocalizedError)?.errorDescription
            ?? "The temporary recording could not be removed.")
      }
    }
  }

  func tryAgain() {
    guard !closed, !captureCleanup.blocksRecording, phase != .recording, !assignmentRefreshRequired
    else { return }
    switch phase {
    case .saved(let receipt):
      if receipt.status == .acceptedSilent {
        advanceAcceptedRepetition()
      } else {
        advanceServerRetry()
      }
    case .retry:
      phase = .ready
    default:
      phase = .ready
    }
  }

  private func advanceServerRetry() {
    if currentRetry < assignment.retryLimit {
      currentRetry += 1
      phase = .ready
      return
    }
    phase = .retryLimitReached
  }

  private func advanceAcceptedRepetition() {
    currentRetry = 0
    currentRepetition += 1
    phase = currentRepetition > assignment.attemptTarget ? .completed : .ready
  }

  func cancelRecording() {
    guard phase == .recording else { return }
    recordingGeneration = nil
    if captureCleanup.removeRequestedMedia() && !captureCleanup.disabledForVisit { phase = .ready }
    refreshCaptureCleanup()
  }

  func appDidBecomeInactive() {
    visualCaptureGeneration = nil
    visualMonitor?.stop()
    if visualConfiguration.isEnabled { visualState = .off }
    recordingGeneration = nil
    if phase == .requestingPermission {
      phase = .ready
      return
    }
    if submissionGeneration != nil { assignmentRefreshRequired = true }
    submissionGeneration = nil
    let released = captureCleanup.removeRequestedMedia()
    refreshCaptureCleanup()
    if released && assignmentRefreshRequired {
      phase = .failed(
        "The last save could not be confirmed. Refresh practice before recording again.")
    } else if released && !captureCleanup.disabledForVisit && phase == .recording {
      phase = .ready
    }
  }

  private func receiveVisualQuality(
    _ result: Result<VisualQualitySnapshot, Error>,
    generation: UUID
  ) {
    guard
      visualConfiguration.isEnabled,
      visualCaptureGeneration == generation
    else { return }
    switch result {
    case .success(let snapshot):
      ensureVisualFeasibilityAccumulator(runtimeVersion: snapshot.runtimeVersion)
      visualFeasibilityAccumulator?.record(
        snapshot,
        thermalState: ProcessInfo.processInfo.thermalState,
        lowPowerMode: ProcessInfo.processInfo.isLowPowerModeEnabled
      )
      if let coaching = visualAssessor.coaching(for: snapshot) {
        visualState = .coaching(coaching, snapshot)
      } else {
        visualState = .ready(snapshot)
      }
    case .failure(let error):
      ensureVisualFeasibilityAccumulator(
        runtimeVersion: VisualCaptureQualityAssessor.runtimeVersion
      )
      visualFeasibilityAccumulator?.recordExtractionFailure(
        thermalState: ProcessInfo.processInfo.thermalState,
        lowPowerMode: ProcessInfo.processInfo.isLowPowerModeEnabled
      )
      visualCaptureGeneration = nil
      visualMonitor?.stop()
      visualState = .unavailable(
        (error as? LocalizedError)?.errorDescription
          ?? "Face framing could not be checked."
      )
    }
  }

  private func ensureVisualFeasibilityAccumulator(runtimeVersion: String) {
    guard visualFeasibilityAccumulator == nil else { return }
    visualFeasibilityAccumulator = VisualFeasibilityAccumulator(
      runtimeVersion: runtimeVersion,
      protocolID: visualConfiguration.protocolID ?? "unknown",
      scenario: visualConfiguration.feasibilityScenario ?? .unstructured
    )
  }
}

/// Shared visit rules for the two capture-only owners. This retains the original producer,
/// never a second file owner; process recovery remains inside that producer/registry.
@MainActor
final class CaptureVisitCleanup {
  let capturer: any AudioCapturing
  private let hardware: AudioHardwareOwnership
  private let files: ProcessAudioFileOwnership
  private var observation: AnyCancellable?
  var didChange: (@MainActor () -> Void)?
  private(set) var recording: CapturedRecording?
  private var recordingCleanupOwner: UUID?
  private var recordingCleanupRequested = false
  private var hardwareCleanupOwner: UUID?
  private var cancellationFileOwners: Set<UUID> = []
  private var cancellingAfterFileOwners: Set<UUID>?
  private var mutationDepth = 0
  private var notificationPending = false
  private var isNotifying = false
  private var captureMayBeActive = false
  private var startWasAlreadyActive = false
  private var unidentifiedFailure = false
  private var closeWarningShown = false
  private(set) var disabledForVisit = false

  init(
    capturer: any AudioCapturing, hardware: AudioHardwareOwnership,
    files: ProcessAudioFileOwnership
  ) {
    self.capturer = capturer
    self.hardware = hardware
    self.files = files
    observation = capturer.cleanupStatePublisher.sink { [weak self] event in
      guard let self else { return }
      // Preserve exact event identity even if an earlier subscriber already recovered it.
      if let id = event.hardwareBlockedOperationID { self.hardwareCleanupOwner = id }
      if let before = self.cancellingAfterFileOwners {
        self.cancellationFileOwners.formUnion(event.fileBlockedOwnerIDs.subtracting(before))
      }
      if event.hasFileIssue { self.disabledForVisit = true }
      self.reconcileCompletedCleanup()
      self.notifyCommittedChange()
    }
  }

  var state: CaptureCleanupState {
    .init(
      hardwareBlockedOperationID: capturer.cleanupState.hardwareBlockedOperationID
        ?? hardware.blockedCaptureOperationID,
      fileBlockedOwnerIDs: capturer.cleanupState.fileBlockedOwnerIDs.union(
        files.pendingCleanupOwners))
  }
  var hasIssue: Bool { state.hasHardwareIssue || state.hasFileIssue || unidentifiedFailure }
  var hasUnidentifiedFailure: Bool { unidentifiedFailure }
  var hasRequestedResources: Bool { captureMayBeActive || recording != nil || hasIssue }
  var blocksRecording: Bool {
    captureMayBeActive || hasIssue || disabledForVisit || recording != nil
  }
  var retryIDs: [UUID] {
    let snapshot = state
    return Array(
      snapshot.fileBlockedOwnerIDs.union(
        snapshot.hardwareBlockedOperationID.map { [$0] } ?? [])
    )
    .sorted { $0.uuidString < $1.uuidString }
  }

  func willStart() {
    startWasAlreadyActive = captureMayBeActive
    hardwareCleanupOwner = nil
    cancellationFileOwners = []
    captureMayBeActive = true
  }

  func canRetry(operationID: UUID) -> Bool { retryIDs.contains(operationID) }
  func captured(_ recording: CapturedRecording) {
    captureMayBeActive = false
    self.recording = recording
    recordingCleanupOwner = recording.cleanupOwnerID
    recordingCleanupRequested = false
  }

  /// Receipt queries do no work. Idle state alone never acknowledges removal.
  private func reconcileCompletedCleanup() {
    if let id = hardwareCleanupOwner,
      capturer.completedFileCleanup(operationID: id)?.allRequestedFilesRemoved == true
    {
      captureMayBeActive = false
      // Keep exact cancellation evidence until the next start. The original cancel
      // can still throw after an earlier subscriber completed an explicit retry.
    }
    if recordingCleanupRequested, let id = recordingCleanupOwner,
      capturer.completedFileCleanup(operationID: id)?.allRequestedFilesRemoved == true
    {
      recording = nil
      recordingCleanupOwner = nil
      recordingCleanupRequested = false
    }
  }

  private func notifyCommittedChange() {
    notificationPending = true
    guard mutationDepth == 0, !isNotifying else { return }
    isNotifying = true
    defer { isNotifying = false }
    while notificationPending {
      notificationPending = false
      didChange?()
    }
  }

  private func finishMutation() {
    mutationDepth -= 1
    if mutationDepth == 0, notificationPending { notifyCommittedChange() }
  }

  func failed(_ error: Error, duringStart: Bool = false) {
    let own = capturer.cleanupState
    if case AudioCaptureError.hardwareBusy = error {
      if duringStart, !startWasAlreadyActive { captureMayBeActive = false }
      return
    }
    if own.hasFileIssue {
      disabledForVisit = true
      if !own.hasHardwareIssue { captureMayBeActive = false }
    } else if duringStart, case AudioCaptureError.couldNotDeleteTemporaryRecording = error,
      !own.hasHardwareIssue
    {
      // Startup scan failure has no operation identity or owned capture resources.
      disabledForVisit = true
      captureMayBeActive = false
    }
  }

  @discardableResult
  func removeRequestedMedia() -> Bool {
    mutationDepth += 1
    defer { finishMutation() }
    reconcileCompletedCleanup()
    if captureMayBeActive {
      if capturer.cleanupState.hasHardwareIssue { return false }
      cancellationFileOwners = []
      cancellingAfterFileOwners = capturer.cleanupState.fileBlockedOwnerIDs
      defer { cancellingAfterFileOwners = nil }
      do {
        try capturer.cancel()
        captureMayBeActive = false
      } catch {
        failed(error)
        reconcileCompletedCleanup()
        var cancellationOwners = cancellationFileOwners
        if let hardwareCleanupOwner { cancellationOwners.insert(hardwareCleanupOwner) }
        let completedCancellation =
          !cancellationOwners.isEmpty
          && cancellationOwners.allSatisfy {
            capturer.completedFileCleanup(operationID: $0)?.allRequestedFilesRemoved == true
          }
        if completedCancellation { captureMayBeActive = false }
        if !completedCancellation, !capturer.cleanupState.hasHardwareIssue,
          !capturer.cleanupState.hasFileIssue
        {
          unidentifiedFailure = true
        }
      }
    }
    if let recording, !recordingCleanupRequested {
      let before = capturer.cleanupState.fileBlockedOwnerIDs
      recordingCleanupRequested = true
      // Concrete recordings bind their producer's identity before discard can notify/reenter.
      recordingCleanupOwner = recording.cleanupOwnerID
      do {
        try capturer.discard(recording)
        self.recording = nil
        recordingCleanupOwner = nil
        recordingCleanupRequested = false
      } catch {
        if recordingCleanupOwner == nil {
          let added = capturer.cleanupState.fileBlockedOwnerIDs.subtracting(before)
          if added.count == 1 { recordingCleanupOwner = added.first }
        }
        reconcileCompletedCleanup()
        if self.recording != nil {
          guard let id = recordingCleanupOwner,
            capturer.cleanupState.fileBlockedOwnerIDs.contains(id)
          else {
            unidentifiedFailure = true
            return false
          }
          failed(error)
        }
      }
    }
    return !captureMayBeActive && recording == nil && !hasIssue
  }

  func retry(operationID: UUID) -> CaptureCleanupReceipt {
    guard canRetry(operationID: operationID) else {
      return .init(operationID: operationID, result: .refused)
    }
    mutationDepth += 1
    defer { finishMutation() }
    reconcileCompletedCleanup()
    let own = capturer.cleanupState
    let wasOwnHardware = own.hardwareBlockedOperationID == operationID
    let receipt: CaptureCleanupReceipt
    if wasOwnHardware || own.fileBlockedOwnerIDs.contains(operationID) {
      receipt = capturer.retryCleanup(operationID: operationID)
    } else if hardware.blockedCaptureOperationID == operationID {
      receipt = hardware.retryCaptureCleanup(operationID: operationID)
    } else if files.pendingCleanupOwners.contains(operationID) {
      receipt = .init(
        operationID: operationID,
        result: files.retryCleanup(owner: operationID) ? .released : .hardwareReleasedFilesRetained)
    } else {
      return .init(operationID: operationID, result: .refused)
    }
    if receipt.hardwareReleased && wasOwnHardware { captureMayBeActive = false }
    if receipt.allRequestedFilesRemoved && recordingCleanupOwner == operationID {
      recording = nil
      recordingCleanupOwner = nil
      recordingCleanupRequested = false
    }
    if capturer.cleanupState.hasFileIssue { disabledForVisit = true }
    reconcileCompletedCleanup()
    notifyCommittedChange()
    return receipt
  }

  var canLeaveWithFileWarning: Bool {
    let snapshot = state
    guard !snapshot.hasHardwareIssue, hardware.currentLease == nil,
      !captureMayBeActive, !unidentifiedFailure, !snapshot.fileBlockedOwnerIDs.isEmpty,
      snapshot.fileBlockedOwnerIDs.isSubset(of: files.pendingCleanupOwners)
    else { return false }
    return recording == nil
      || recordingCleanupOwner.map {
        snapshot.fileBlockedOwnerIDs.contains($0)
      } == true
  }

  func requestClose() -> Bool {
    let alreadyWarned = closeWarningShown
    if removeRequestedMedia() { return true }
    closeWarningShown = true
    return alreadyWarned && canLeaveWithFileWarning
  }
}
