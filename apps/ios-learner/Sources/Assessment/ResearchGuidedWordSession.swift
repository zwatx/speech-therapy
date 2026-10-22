#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation

  struct ResearchFeedbackAttemptIdentity: Equatable, Sendable {
    let workflowId: UUID?
    let attemptId: UUID
    let captureId: String
    let takeId: String
    let setupGeneration: Int
    let prompt: ResearchFeedbackPrompt
    let context: ResearchPracticeContext?
  }
  enum ResearchFeedbackAttemptTerminal: String, Equatable, Sendable {
    case permissionDenied, permissionCancelled, captureCancelled, captureFailed
    case recordedDiscarded, checkFailed, checkCancelled, invalidResponse
  }
  enum ResearchFeedbackLifecycleEvent: Equatable, Sendable {
    case started(ResearchFeedbackAttemptIdentity)
    case captured(ResearchFeedbackAttemptIdentity, audioSha256: String)
    case submitted(ResearchFeedbackAttemptIdentity)
    case requestStarted(ResearchFeedbackAttemptIdentity)
    case validated(ResearchFeedbackAttemptIdentity, RecordingFeedback)
    case terminal(ResearchFeedbackAttemptIdentity, ResearchFeedbackAttemptTerminal)
    case bindingRejected(ResearchFeedbackAttemptIdentity)
    case invalidated
  }
  enum ResearchGuidedWordPhase: Equatable {
    case setup, firstRound, summary, practicePlanChoice, practice, practicePlanSummary, recheck,
      comparison, ended
  }
  enum ResearchGuidedWordDisposition: String, CaseIterable, Equatable, Sendable {
    case modelMatched, modelNotMatched, recognitionUncertain, notSingleSupportedWord
    case speechNotDetected, recordingIssue, checkUnavailable, skipped, notReached
    var isLexicalObservation: Bool { self == .modelMatched || self == .modelNotMatched }
  }
  struct ResearchGuidedWordItem: Equatable, Identifiable, Sendable {
    var id: String { prompt.id }
    var word: String { prompt.word }
    let prompt: ResearchFeedbackPrompt
    let catalogPromptIds: [String]
  }
  struct ResearchGuidedWordRow: Equatable, Identifiable, Sendable {
    var id: String { item.id }
    var word: String { item.word }
    let item: ResearchGuidedWordItem
    var disposition: ResearchGuidedWordDisposition = .notReached
    var primaryAttemptId: UUID?
    var observation: RecordingFeedback?
    var reason: String?
    var audioSha256: String?
  }
  struct ResearchGuidedWordAttempt: Equatable, Identifiable, Sendable {
    enum Purpose: Equatable, Sendable { case first, practice, recheck }
    var id: UUID { identity.attemptId }
    let identity: ResearchFeedbackAttemptIdentity
    let purpose: Purpose
    let roundId: UUID?
    var practiceVisitId: UUID? = nil
    let itemId: String
    var audioSha256: String?
    var submitted = false
    var requestStarted = false
    var validated = false
    var terminal: ResearchFeedbackAttemptTerminal?
    var observation: RecordingFeedback?
    var isFinished: Bool { validated || terminal != nil }
  }
  struct ResearchGuidedWordSummary: Equatable, Sendable {
    let roundId: UUID
    let context: ResearchPracticeContext
    let fingerprint: String
    let rows: [ResearchGuidedWordRow]
    let attempts: [ResearchGuidedWordAttempt]
    var plannedCount: Int { rows.count }
    var attemptsStarted: Int { attempts.count }
    var submissions: Int { attempts.filter(\.submitted).count }
    /// Requests started, not bytes uploaded or server receipts.
    var transportStarts: Int { attempts.filter(\.requestStarted).count }
    var validatedResponses: Int { attempts.filter(\.validated).count }
    var lexicalObservations: Int { rows.filter { $0.disposition.isLexicalObservation }.count }
    var dispositionCounts: [ResearchGuidedWordDisposition: Int] {
      Dictionary(
        uniqueKeysWithValues: ResearchGuidedWordDisposition.allCases.map { kind in
          (kind, rows.filter { $0.disposition == kind }.count)
        })
    }
  }
  struct ResearchGuidedWordComparisonRow: Equatable, Identifiable, Sendable {
    var id: String { first.id }
    var word: String { first.word }
    let first: ResearchGuidedWordRow
    let recheck: ResearchGuidedWordRow
    var paired: Bool {
      first.disposition.isLexicalObservation && recheck.disposition.isLexicalObservation
    }
    var sameAudioWarning: Bool {
      first.audioSha256 != nil && first.audioSha256 == recheck.audioSha256
    }
  }
  struct ResearchGuidedWordComparison: Equatable, Sendable {
    let first: ResearchGuidedWordSummary
    let recheck: ResearchGuidedWordSummary
    let rows: [ResearchGuidedWordComparisonRow]
    var pairedCount: Int { rows.filter(\.paired).count }
  }

  enum ResearchGuidedPracticePlanDisposition: Equatable, Sendable {
    case pending, finishedSaved
    case finishedNotSaved(ResearchGuidedPracticeSaveError)
    case skipped, leftUnsaved
  }
  struct ResearchGuidedPracticePlanRow: Equatable, Identifiable, Sendable {
    var id: String { item.id }
    var word: String { item.word }
    let item: ResearchGuidedWordItem
    var visitID: UUID?
    var disposition: ResearchGuidedPracticePlanDisposition = .pending
    var completion: ResearchGuidedPracticeCompletion?
  }

  /// In-memory observation ledger. The supplied feedback session remains the only media owner.
  @MainActor
  final class ResearchGuidedWordSession: ObservableObject {
    let feedbackSession: ResearchFeedbackSession
    @Published var localProcessingEnabled = false {
      didSet {
        if oldValue != localProcessingEnabled,
          transitionToken != nil || phase != .setup && phase != .ended
        {
          invalidate()
        }
      }
    }
    @Published private(set) var phase: ResearchGuidedWordPhase = .setup
    @Published private(set) var childContext: ResearchPracticeContext?
    @Published private(set) var currentItem: ResearchGuidedWordItem?
    @Published private(set) var firstSummary: ResearchGuidedWordSummary?
    @Published private(set) var recheckSummary: ResearchGuidedWordSummary?
    @Published private(set) var comparison: ResearchGuidedWordComparison?
    @Published private(set) var attempts: [ResearchGuidedWordAttempt] = []
    @Published private(set) var rows: [ResearchGuidedWordRow] = []
    @Published private(set) var lastError: String?
    @Published private(set) var practiceVisit: ResearchGuidedPracticeVisit?
    @Published private(set) var selectedPlanItemIDs: [String] = []
    @Published private(set) var practicePlanRows: [ResearchGuidedPracticePlanRow] = []
    @Published private(set) var planPosition: Int?
    private var practicePlanID: UUID?
    private var planChoiceReturnPhase: ResearchGuidedWordPhase = .summary
    private let participationWriter: (any ResearchGuidedPracticeParticipationRecording)?
    private let now: @MainActor () -> Date
    private var practiceFinalizing = false
    @Published private(set) var transitionPending = false
    @Published private(set) var recoveryPending = false
    @Published private(set) var closeRequested = false
    @Published private(set) var cleanupReleased = false
    private var transitionToken: UUID?
    private var invalidating = false
    private var closedVisit: ResearchGuidedPracticeVisit?
    private var closedPlanIndex: Int?
    @MainActor private final class CloseCleanup {
      var result: Task<Bool, Never>?
    }
    private(set) var cleanupTask: Task<Bool, Never>?
    private var recoveryTask: Task<Bool, Never>?
    private var recoveryCleanupTask: Task<Bool, Never>?

    /// Coordinator state is frozen before cleanup; terminal attempt events may still settle.
    private struct TransitionSnapshot: Equatable {
      let workflow: UUID
      let phase: ResearchGuidedWordPhase
      let round: UUID?
      let index: Int
      let item: ResearchGuidedWordItem?
      let context: ResearchPracticeContext?
      let fingerprint: String
      let row: ResearchGuidedWordRow?
      let visit: ResearchGuidedPracticeVisit?
      let plan: UUID?
      let position: Int?
      let choices: [String]
      let planRows: [ResearchGuidedPracticePlanRow]
      let first: UUID?
      let recheck: UUID?
      let enabled: Bool
      let prompt: ResearchFeedbackPrompt?
      let feedbackContext: ResearchPracticeContext?
      let feedbackEnabled: Bool
      let mode: String
    }
    private func snapshot() -> TransitionSnapshot {
      .init(
        workflow: workflowId, phase: phase, round: roundId, index: index, item: currentItem,
        context: childContext, fingerprint: fingerprint, row: currentRow, visit: practiceVisit,
        plan: practicePlanID, position: planPosition, choices: selectedPlanItemIDs,
        planRows: practicePlanRows, first: firstSummary?.roundId, recheck: recheckSummary?.roundId,
        enabled: localProcessingEnabled, prompt: feedbackSession.selectedPrompt,
        feedbackContext: feedbackSession.practiceContext,
        feedbackEnabled: feedbackSession.localProcessingEnabled, mode: feedbackSession.practiceMode)
    }
    private func claimTransition(finalizing: Bool = false) -> UUID {
      let token = UUID()
      transitionToken = token
      practiceFinalizing = finalizing
      transitionPending = true
      if !current(token), transitionToken == nil {
        transitionPending = false
        practiceFinalizing = false
      }
      return token
    }
    private func current(_ token: UUID) -> Bool {
      transitionToken == token && !closeRequested && !invalidating && !Task.isCancelled
    }
    private func finishTransition(_ token: UUID) {
      guard transitionToken == token else { return }
      transitionToken = nil
      transitionPending = false
      practiceFinalizing = false
    }
    /// Preparation/loading may be cancelled by an admitted transition; an existing stop,
    /// permission request, recording, check, cleanup failure or inactive app cannot admit one.
    private var mediaTransitionEligible: Bool {
      if feedbackSession.canTransitionGuided { return true }
      guard !feedbackSession.closeRequested, !feedbackSession.isPermissionPending,
        !feedbackSession.hasLocalMediaCleanupIssue, !feedbackSession.isAudioCleanupPending,
        !feedbackSession.isProcessing, !feedbackSession.isPreparingAnotherTry,
        !feedbackSession.isFinalizingPractice,
        feedbackSession.phase != .recording && feedbackSession.phase != .requestingPermission,
        feedbackSession.phase != .ended
      else { return false }
      if case .preparing = feedbackSession.playbackState,
        let source = feedbackSession.activeReplaySource
      {
        return feedbackSession.canReplay(source)
      }
      return feedbackSession.exampleState == .loading && feedbackSession.canPlayExample
    }
    private let workflowId = UUID()
    private var roundId: UUID?
    private var index = 0
    private var fingerprint = ""
    private var adjusting = false
    private var practiceReturnPhase: ResearchGuidedWordPhase = .summary
    static let attemptLimit = 128
    static var roster: [ResearchGuidedWordItem] {
      var seen: Set<String> = []
      return ResearchFeedbackCatalog.prompts.compactMap { prompt in
        guard seen.insert(prompt.word).inserted else { return nil }
        return ResearchGuidedWordItem(
          prompt: prompt,
          catalogPromptIds: ResearchFeedbackCatalog.prompts.filter { $0.word == prompt.word }.map(
            \.id))
      }
    }
    init(
      feedbackSession: ResearchFeedbackSession = ResearchFeedbackSession(),
      participationWriter: (any ResearchGuidedPracticeParticipationRecording)? = nil,
      now: @escaping @MainActor () -> Date = { Date() }
    ) {
      self.feedbackSession = feedbackSession
      self.participationWriter = participationWriter
      self.now = now
    }
    var selectedPlanItems: [ResearchGuidedWordItem] {
      Self.roster.filter { selectedPlanItemIDs.contains($0.id) }
    }
    /// Optional suggestions require the original primary validated observation, not a row label.
    var suggestedPracticeItems: [ResearchGuidedWordItem] {
      guard planContextCurrent, let firstSummary else { return [] }
      return firstSummary.rows.compactMap { row in
        guard row.disposition == .modelNotMatched, let primary = row.primaryAttemptId,
          let observation = row.observation, observation.status == .observed,
          observation.word == .modelNotMatched,
          let attempt = firstSummary.attempts.first(where: { $0.id == primary }),
          attempt.purpose == .first, attempt.roundId == firstSummary.roundId,
          attempt.identity.workflowId == workflowId,
          attempt.identity.context == firstSummary.context,
          attempt.identity.prompt == row.item.prompt, attempt.itemId == row.id,
          attempt.submitted, attempt.requestStarted, attempt.validated, attempt.terminal == nil,
          attempt.observation == observation, attempt.audioSha256 != nil,
          attempt.audioSha256 == row.audioSha256, Self.roster.contains(row.item)
        else { return nil }
        return row.item
      }
    }
    var canBeginPlan: Bool {
      phase == .practicePlanChoice && recheckSummary == nil && planContextCurrent && canTransition
        && (1...3).contains(selectedPlanItemIDs.count)
        && Set(selectedPlanItemIDs).count == selectedPlanItemIDs.count
        && selectedPlanItems.count == selectedPlanItemIDs.count
    }
    var isPracticePlanActive: Bool { activePlanVisit }
    var canNextPlan: Bool {
      activePlanVisit && canTransition && practiceVisit?.completionState != .active
    }
    var canSkipPlan: Bool { activePlanVisit && canTransition && activePracticeVisit }
    private var activePlanVisit: Bool {
      phase == .practice && practicePlanID != nil && planPosition != nil
        && currentPlanRow?.visitID == practiceVisit?.id && practiceVisit != nil
        && currentPlanRow?.item == currentItem && validSetup
    }
    private var currentPlanIndex: Int? {
      guard let planPosition, practicePlanRows.indices.contains(planPosition - 1) else {
        return nil
      }
      return planPosition - 1
    }
    private var currentPlanRow: ResearchGuidedPracticePlanRow? {
      currentPlanIndex.map { practicePlanRows[$0] }
    }
    private var planContextCurrent: Bool {
      guard let firstSummary, let childContext else { return false }
      return localProcessingEnabled && feedbackSession.localProcessingEnabled
        && feedbackSession.practiceContext == childContext
        && feedbackSession.practiceMode == "guided"
        && firstSummary.context == childContext && firstSummary.fingerprint == fingerprint
        && fingerprint == Self.makeFingerprint(childContext) && Self.catalogValid
    }
    var canTransition: Bool {
      transitionToken == nil && !closeRequested && !invalidating && phase != .ended
        && !transitionPending && !recoveryPending && !practiceFinalizing
        && mediaTransitionEligible
    }
    var canFinishPractice: Bool {
      validSetup && phase == .practice && canTransition && activePracticeVisit
        && practiceVisit?.hasValidCapture == true
        && currentItem.flatMap {
          ResearchGuidedPracticeParticipationMapping.soundID(for: $0.prompt)
        } != nil
    }
    var canRetryPracticeSave: Bool {
      guard validSetup, phase == .practice, canTransition, participationWriter != nil,
        let visit = practiceVisit, visit.item == currentItem, visit.acknowledgedCompletion != nil,
        case .completedNotSaved = visit.completionState
      else { return false }
      return true
    }
    private var activePracticeVisit: Bool {
      phase == .practice && practiceVisit?.item == currentItem
        && practiceVisit?.completionState == .active
    }
    var canRecord: Bool {
      validSetup && !transitionPending && !practiceFinalizing && currentItem != nil
        && attempts.count < Self.attemptLimit
        && feedbackSession.canRecord
        && (activePracticeVisit
          || isRound && currentRow?.primaryAttemptId == nil
            && currentRow?.disposition == .notReached)
    }
    var canCheck: Bool {
      validSetup && !transitionPending && !practiceFinalizing && !activePlanVisit
        && feedbackSession.canCheck
        && (activePracticeVisit
          || isRound && currentRow?.primaryAttemptId == nil
            && currentRow?.disposition == .notReached)
    }
    var canNext: Bool { isRound && canTransition && currentRow?.disposition != .notReached }
    var canSkip: Bool { isRound && canTransition && currentRow?.disposition == .notReached }
    private func allowsOwnedAction(submit: Bool) -> Bool {
      if submit && activePlanVisit { return false }
      return !invalidating && !closeRequested && validSetup && !transitionPending
        && !practiceFinalizing && (submit || attempts.count < Self.attemptLimit)
        && (activePracticeVisit
          || isRound && currentRow?.primaryAttemptId == nil
            && currentRow?.disposition == .notReached)
    }
    private var isRound: Bool { phase == .firstRound || phase == .recheck }
    private var currentRow: ResearchGuidedWordRow? {
      rows.indices.contains(index) ? rows[index] : nil
    }
    private var validSetup: Bool {
      !closeRequested && !invalidating && !recoveryPending && (isRound || phase == .practice)
        && localProcessingEnabled
        && feedbackSession.localProcessingEnabled && feedbackSession.practiceContext == childContext
        && feedbackSession.selectedPrompt == currentItem?.prompt
        && feedbackSession.practiceMode == "guided"
    }
    @discardableResult func start(age: Int) async -> Bool {
      guard !Task.isCancelled, phase == .setup, canTransition, localProcessingEnabled,
        (6...12).contains(age), Self.catalogValid
      else {
        lastError = "Choose age 6–12, enable local checks, and finish media cleanup."
        return false
      }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return false }
      guard
        feedbackSession.installGuidedObserver(
          owner: workflowId, observer: { [weak self] event in self?.receive(event) },
          allowsAction: { [weak self] submit in self?.allowsOwnedAction(submit: submit) ?? false })
      else {
        if current(token) { lastError = "Recording session is already owned." }
        return false
      }
      let context = ResearchPracticeContext.child(ageYears: age)
      guard await select(Self.roster[0], context: context, token: token),
        current(token), phase == .setup, localProcessingEnabled, Self.catalogValid
      else {
        // A claimed lifecycle owner is permanent even if setup fails or is cancelled.
        _ = end()
        return false
      }
      childContext = context
      guard current(token) else { return false }
      fingerprint = Self.makeFingerprint(context)
      installRound(phase: .firstRound, token: token)
      return current(token) && phase == .firstRound
    }
    func record() async {
      guard canRecord else { return }
      await feedbackSession.startRecording()
    }
    func stop() {
      guard validSetup, !transitionPending, !practiceFinalizing else { return }
      feedbackSession.stopRecording()
    }
    func check() {
      guard canCheck else { return }
      feedbackSession.checkRecording()
    }
    @discardableResult func retake() -> Task<Bool, Never>? {
      guard validSetup, !transitionPending, !practiceFinalizing,
        phase != .practice || activePracticeVisit
      else { return nil }
      return feedbackSession.retake()
    }
    func next() async {
      guard !Task.isCancelled, canNext else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      if index + 1 == rows.count {
        finishRound(token: token)
      } else {
        guard await select(Self.roster[index + 1], context: childContext, token: token),
          current(token)
        else { return }
        index += 1
        currentItem = Self.roster[index]
      }
    }
    func skip() async {
      guard !Task.isCancelled, canSkip else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      if index + 1 < rows.count {
        guard await select(Self.roster[index + 1], context: childContext, token: token),
          current(token)
        else { return }
      }
      rows[index].disposition = .skipped
      guard current(token) else { return }
      if index + 1 == rows.count {
        finishRound(token: token)
      } else {
        index += 1
        currentItem = Self.roster[index]
      }
    }
    func finishEarly() async {
      guard !Task.isCancelled, isRound, canTransition else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      finishRound(token: token)
    }
    func practice(item itemId: String) async {
      guard !Task.isCancelled, [.summary, .comparison, .practice].contains(phase), canTransition,
        planContextCurrent, let item = Self.roster.first(where: { $0.id == itemId })
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before),
        await select(item, context: childContext, token: token), current(token)
      else { return }
      settlePlanVisitOnLeave(token: token)
      practicePlanID = nil
      guard current(token) else { return }
      planPosition = nil
      if phase != .practice { practiceReturnPhase = phase }
      guard current(token) else { return }
      practiceVisit = .init(id: UUID(), item: item)
      guard current(token) else { return }
      currentItem = item
      guard current(token) else { return }
      phase = .practice
    }
    func returnSummary() async {
      guard !Task.isCancelled,
        [.practice, .practicePlanChoice, .practicePlanSummary].contains(phase), canTransition
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      settlePlanVisitOnLeave(token: token)
      practicePlanID = nil
      guard current(token) else { return }
      planPosition = nil
      guard current(token) else { return }
      selectedPlanItemIDs = []
      guard current(token) else { return }
      practiceVisit = nil
      guard current(token) else { return }
      currentItem = nil
      guard current(token) else { return }
      phase = practiceReturnPhase
    }
    func startRecheck() async {
      guard !Task.isCancelled,
        [.summary, .practice, .practicePlanChoice, .practicePlanSummary].contains(phase),
        firstSummary != nil, recheckSummary == nil, canTransition, planContextCurrent,
        childContext != nil, Self.catalogValid
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before),
        await select(Self.roster[0], context: childContext, token: token), current(token)
      else { return }
      settlePlanVisitOnLeave(token: token)
      practicePlanID = nil
      guard current(token) else { return }
      planPosition = nil
      guard current(token) else { return }
      selectedPlanItemIDs = []
      guard current(token) else { return }
      practiceVisit = nil
      installRound(phase: .recheck, token: token)
    }
    /// Enter an empty chooser. Suggestions are never selected on the user's behalf.
    func openPracticePlan() async {
      guard !Task.isCancelled, [.summary, .practicePlanSummary].contains(phase),
        recheckSummary == nil, planContextCurrent, canTransition
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      if phase != .practicePlanSummary { practiceReturnPhase = phase }
      planChoiceReturnPhase = phase
      guard current(token) else { return }
      selectedPlanItemIDs = []
      practicePlanID = nil
      guard current(token) else { return }
      planPosition = nil
      guard current(token) else { return }
      practiceVisit = nil
      guard current(token) else { return }
      currentItem = nil
      guard current(token) else { return }
      phase = .practicePlanChoice
    }
    func togglePracticePlanItem(_ id: String) {
      guard phase == .practicePlanChoice, planContextCurrent, canTransition,
        Self.roster.contains(where: { $0.id == id })
      else { return }
      let token = claimTransition()
      defer { finishTransition(token) }
      guard current(token), phase == .practicePlanChoice, planContextCurrent else { return }
      var selection = Set(selectedPlanItemIDs)
      if selection.contains(id) {
        selection.remove(id)
      } else {
        guard selection.count < 3 else { return }
        selection.insert(id)
      }
      // Publish one canonical value. Synchronous subscribers cannot admit another choice
      // while this transition owns selection; Close can still revoke it immediately.
      selectedPlanItemIDs = Self.roster.filter { selection.contains($0.id) }.map(\.id)
    }
    func beginPracticePlan() async {
      guard !Task.isCancelled, canBeginPlan else { return }
      let before = snapshot()
      let items = selectedPlanItems
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before),
        await select(items[0], context: childContext, token: token), current(token)
      else { return }
      practicePlanID = UUID()
      guard current(token) else { return }
      practicePlanRows = items.map { .init(item: $0) }
      enterPlanItem(at: 0, token: token)
    }
    func cancelPracticePlanChoice() async {
      guard !Task.isCancelled, phase == .practicePlanChoice, canTransition else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      guard current(token) else { return }
      selectedPlanItemIDs = []
      guard current(token) else { return }
      phase = planChoiceReturnPhase
    }
    func skipPracticePlanItem() async {
      guard !Task.isCancelled, canSkipPlan, let index = currentPlanIndex else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before),
        await selectNextPlan(after: index, token: token),
        current(token)
      else { return }
      guard current(token) else { return }
      practicePlanRows[index].disposition = .skipped
      advancePlan(after: index, token: token)
    }
    /// Finish never advances. A failed save needs an explicit leave choice, or the existing retry.
    func nextPracticePlanItem(leaveWithoutSaving: Bool = false) async {
      guard !Task.isCancelled, canNextPlan, mayLeavePlanVisit(leaveWithoutSaving),
        let index = currentPlanIndex
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before),
        await selectNextPlan(after: index, token: token),
        current(token)
      else { return }
      updatePlanCompletion(token: token)
      advancePlan(after: index, token: token)
    }
    func endPracticePlan(leaveWithoutSaving: Bool = false) async {
      guard !Task.isCancelled, activePlanVisit, canTransition,
        mayLeavePlanVisit(leaveWithoutSaving)
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      settlePlanVisitOnLeave(token: token)
      guard current(token) else { return }
      practiceVisit = nil
      guard current(token) else { return }
      currentItem = nil
      guard current(token) else { return }
      planPosition = nil
      guard current(token) else { return }
      phase = .practicePlanSummary
    }
    /// Confirming edited choices creates a new sequence; the old report remains until then.
    func editPracticePlan(leaveWithoutSaving: Bool = false) async {
      guard !Task.isCancelled, activePlanVisit || phase == .practicePlanSummary,
        planContextCurrent, canTransition, mayLeavePlanVisit(leaveWithoutSaving)
      else { return }
      let before = snapshot()
      let token = claimTransition()
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before) else { return }
      settlePlanVisitOnLeave(token: token)
      guard current(token) else { return }
      practiceVisit = nil
      guard current(token) else { return }
      currentItem = nil
      guard current(token) else { return }
      planPosition = nil
      practicePlanID = nil
      planChoiceReturnPhase = .practicePlanSummary
      guard current(token) else { return }
      phase = .practicePlanChoice
    }
    private func selectNextPlan(after index: Int, token: UUID) async -> Bool {
      guard index + 1 < practicePlanRows.count else { return current(token) }
      return await select(practicePlanRows[index + 1].item, context: childContext, token: token)
    }
    private func mayLeavePlanVisit(_ explicitly: Bool) -> Bool {
      if let visit = practiceVisit, case .completedNotSaved = visit.completionState {
        return explicitly
      }
      return true
    }
    private func enterPlanItem(at index: Int, token: UUID) {
      guard current(token), practicePlanRows.indices.contains(index) else { return }
      let item = practicePlanRows[index].item
      let visit = ResearchGuidedPracticeVisit(id: UUID(), item: item)
      guard current(token) else { return }
      practicePlanRows[index].visitID = visit.id
      guard current(token) else { return }
      practiceVisit = visit
      guard current(token) else { return }
      planPosition = index + 1
      guard current(token) else { return }
      currentItem = item
      guard current(token) else { return }
      phase = .practice
    }
    private func advancePlan(after index: Int, token: UUID) {
      guard current(token) else { return }
      practiceVisit = nil
      guard current(token) else { return }
      currentItem = nil
      if index + 1 < practicePlanRows.count {
        enterPlanItem(at: index + 1, token: token)
      } else {
        guard current(token) else { return }
        planPosition = nil
        guard current(token) else { return }
        phase = .practicePlanSummary
      }
    }
    private func updatePlanCompletion(token: UUID) {
      guard current(token), let index = currentPlanIndex, let visit = practiceVisit,
        practicePlanRows[index].visitID == visit.id
      else { return }
      switch visit.completionState {
      case .active: break
      case .saved:
        guard current(token) else { return }
        practicePlanRows[index].disposition = .finishedSaved
        guard current(token) else { return }
        practicePlanRows[index].completion = visit.acknowledgedCompletion
      case .completedNotSaved(let error):
        guard current(token) else { return }
        practicePlanRows[index].disposition = .finishedNotSaved(error)
        guard current(token) else { return }
        practicePlanRows[index].completion = visit.acknowledgedCompletion
      }
    }
    private func settlePlanVisitOnLeave(token: UUID) {
      guard current(token), let index = currentPlanIndex, let visit = practiceVisit,
        practicePlanRows[index].visitID == visit.id
      else { return }
      if visit.completionState == .active {
        guard current(token) else { return }
        practicePlanRows[index].disposition = .leftUnsaved
      } else {
        updatePlanCompletion(token: token)
      }
    }
    func finishPractice() async {
      guard !Task.isCancelled, canFinishPractice, let visit = practiceVisit,
        let soundID = ResearchGuidedPracticeParticipationMapping.soundID(for: visit.item.prompt)
      else { return }
      let before = snapshot()
      let token = claimTransition(finalizing: true)
      defer { finishTransition(token) }
      let completion = ResearchGuidedPracticeCompletion(
        id: visit.id, completedAt: now(), soundID: soundID, wordCount: 1)
      // The injected clock may reenter. Revalidate before even requesting cleanup.
      guard current(token), snapshot() == before,
        await clearMedia(token, before: before), validSetup
      else { return }
      savePractice(completion, token: token)
    }
    func retryPracticeSave() async {
      guard !Task.isCancelled, canRetryPracticeSave,
        let completion = practiceVisit?.acknowledgedCompletion
      else { return }
      let before = snapshot()
      let token = claimTransition(finalizing: true)
      defer { finishTransition(token) }
      guard await clearMedia(token, before: before), validSetup else { return }
      savePractice(completion, token: token)
    }
    private func savePractice(_ completion: ResearchGuidedPracticeCompletion, token: UUID) {
      guard current(token), phase == .practice, practiceVisit?.id == completion.id, validSetup
      else {
        return
      }
      let state: ResearchGuidedPracticeCompletionState
      if let participationWriter {
        do {
          try participationWriter.record(
            sessionID: completion.id, completedAt: completion.completedAt,
            soundID: completion.soundID, wordCount: completion.wordCount)
          state = .saved
        } catch { state = .completedNotSaved(.writeFailed) }
      } else {
        state = .completedNotSaved(.storeUnavailable)
      }
      // An entered synchronous write may commit; it must never label a revoked visit Saved.
      guard current(token), phase == .practice, practiceVisit?.id == completion.id, validSetup
      else {
        return
      }
      guard current(token) else { return }
      practiceVisit?.acknowledgedCompletion = completion
      guard current(token) else { return }
      practiceVisit?.completionState = state
      updatePlanCompletion(token: token)
    }
    /// Revocation is synchronous even during permission, a check or another held transition.
    /// Retain this result before the parent releases the view; duplicate Close joins it.
    @discardableResult func end() -> Task<Bool, Never> {
      if let cleanupTask { return cleanupTask }
      let joined = CloseCleanup()
      let pendingRecovery = recoveryCleanupTask
      closedVisit = practiceVisit
      closedPlanIndex = currentPlanIndex
      // Install our joinable owner before any synchronous publisher/observer can reenter.
      let task = Task { [self, joined] in
        guard let result = joined.result else { return false }
        var released = await result.value
        if !released, let pendingRecovery, await pendingRecovery.value {
          // Close may arrive during an explicit retry. Join that released retry before
          // asking the terminal owner to finish; the original negative receipt stays negative.
          released = await feedbackSession.end().value
        }
        if released {
          settleClosedPlanVisit(closedVisit, at: closedPlanIndex)
          cleanupReleased = true
        }
        return released
      }
      cleanupTask = task
      invalidating = true
      transitionToken = nil
      closeRequested = true
      transitionPending = false
      practiceFinalizing = false
      if adjusting {
        // A setup publisher can Close inside willSet. Its subsequent didSet supersedes a
        // feedback Close, so revoke now and join terminal Close after that setter returns.
        let revocation = feedbackSession.retake()
        feedbackSession.removeGuidedObserver(owner: workflowId)
        joined.result = Task { [self] in
          _ = await revocation?.value
          return await feedbackSession.end().value
        }
      } else {
        joined.result = feedbackSession.end()
        feedbackSession.removeGuidedObserver(owner: workflowId)
      }
      practiceVisit = nil
      currentItem = nil
      roundId = nil
      phase = .ended
      invalidating = false
      return task
    }
    /// Explicit recovery can finish a held Close; failed navigation/finalization is never replayed.
    @discardableResult func retryAudioCleanup() -> Task<Bool, Never> {
      if let recoveryTask { return recoveryTask }
      let joined = CloseCleanup()
      let cleanup = Task {
        guard let result = joined.result else { return false }
        return await result.value
      }
      recoveryCleanupTask = cleanup
      let task = Task { [self] in
        defer {
          recoveryTask = nil
          recoveryCleanupTask = nil
          recoveryPending = false
        }
        guard await cleanup.value else { return false }
        if closeRequested {
          // Close joins the raw feedback recovery, not this coordinator task. Joining its
          // result here cannot cycle, and ensures terminal plan settlement before return.
          if let close = cleanupTask { _ = await close.value }
          guard feedbackSession.phase == .ended else { return false }
          if !cleanupReleased {
            settleClosedPlanVisit(closedVisit, at: closedPlanIndex)
            cleanupReleased = true
          }
        }
        return !closeRequested || cleanupReleased
      }
      recoveryTask = task
      recoveryPending = true
      joined.result = feedbackSession.retryAudioCleanup()
      return task
    }
    private func settleClosedPlanVisit(_ visit: ResearchGuidedPracticeVisit?, at index: Int?) {
      if let index, let visit, practicePlanRows.indices.contains(index),
        practicePlanRows[index].visitID == visit.id
      {
        switch visit.completionState {
        case .active: practicePlanRows[index].disposition = .leftUnsaved
        case .saved:
          practicePlanRows[index].disposition = .finishedSaved
          practicePlanRows[index].completion = visit.acknowledgedCompletion
        case .completedNotSaved(let error):
          practicePlanRows[index].disposition = .finishedNotSaved(error)
          practicePlanRows[index].completion = visit.acknowledgedCompletion
        }
      }
      practicePlanID = nil
      planPosition = nil
      selectedPlanItemIDs = []
    }
    /// The selected setup has already acknowledged cleanup before a round is installed.
    private func installRound(phase: ResearchGuidedWordPhase, token: UUID) {
      guard current(token) else { return }
      roundId = UUID()
      rows = Self.roster.map { ResearchGuidedWordRow(item: $0) }
      guard current(token) else { return }
      index = 0
      currentItem = Self.roster[0]
      guard current(token) else { return }
      self.phase = phase
    }
    private func select(
      _ item: ResearchGuidedWordItem, context: ResearchPracticeContext?, token: UUID
    ) async -> Bool {
      guard current(token) else { return false }
      // Ignore only our synchronous setup invalidations. External lifecycle invalidation
      // during the following await must revoke this token and own real cleanup.
      adjusting = true
      feedbackSession.practiceMode = "guided"
      if current(token) { feedbackSession.practiceContext = context }
      if current(token) { feedbackSession.localProcessingEnabled = true }
      if current(token) { feedbackSession.selectedPrompt = item.prompt }
      adjusting = false
      guard current(token), await feedbackSession.awaitPendingAudioCleanup(), current(token),
        await feedbackSession.clearGuidedMedia(), current(token),
        feedbackSession.practiceMode == "guided", feedbackSession.practiceContext == context,
        feedbackSession.localProcessingEnabled, feedbackSession.selectedPrompt == item.prompt,
        localProcessingEnabled, Self.catalogValid
      else {
        if current(token) { invalidate() }
        return false
      }
      return true
    }
    private func clearMedia(_ token: UUID, before: TransitionSnapshot) async -> Bool {
      guard current(token), snapshot() == before else { return false }
      if !feedbackSession.canTransitionGuided {
        // Preparation/loading needs synchronous revocation before the feedback clear can
        // be admitted. Join that owned cleanup; never retry its negative result implicitly.
        let cleanup = feedbackSession.retake()
        let removed = await cleanup?.value ?? false
        guard current(token), snapshot() == before else { return false }
        guard removed else {
          lastError = "Finish recording, permission, or media cleanup before continuing."
          return false
        }
      }
      // This acknowledgement also joins the exact retained control task. Idle alone, or
      // the local retake result, never authorizes ledger changes or the metadata writer.
      let cleared = await feedbackSession.clearGuidedMedia()
      guard current(token), snapshot() == before else { return false }
      guard cleared, feedbackSession.canTransitionGuided else {
        lastError = "Finish recording, permission, or media cleanup before continuing."
        return false
      }
      return true
    }
    private func finishRound(token: UUID) {
      guard current(token), let roundId, let childContext else { return }
      let summary = ResearchGuidedWordSummary(
        roundId: roundId, context: childContext,
        fingerprint: fingerprint, rows: rows, attempts: attempts.filter { $0.roundId == roundId })
      currentItem = nil
      guard current(token) else { return }
      self.roundId = nil
      if phase == .firstRound {
        firstSummary = summary
        guard current(token) else { return }
        phase = .summary
      } else if let firstSummary, firstSummary.context == summary.context,
        firstSummary.fingerprint == summary.fingerprint,
        firstSummary.rows.map(\.id) == summary.rows.map(\.id)
      {
        recheckSummary = summary
        guard current(token) else { return }
        comparison = ResearchGuidedWordComparison(
          first: firstSummary, recheck: summary,
          rows: zip(firstSummary.rows, summary.rows).map { .init(first: $0.0, recheck: $0.1) })
        guard current(token) else { return }
        phase = .comparison
      } else {
        invalidate()
      }
    }
    private func invalidate() {
      guard !invalidating, !closeRequested else { return }
      _ = end()
      lastError = "Guided context ended. Start a new flow to compare fresh rounds."
    }
    private func receive(_ event: ResearchFeedbackLifecycleEvent) {
      guard !adjusting, phase != .ended, phase != .setup else { return }
      if case .invalidated = event {
        invalidate()
        return
      }
      let identity: ResearchFeedbackAttemptIdentity
      switch event {
      case .started(let v), .captured(let v, _), .submitted(let v), .requestStarted(let v),
        .validated(let v, _), .terminal(let v, _), .bindingRejected(let v):
        identity = v
      case .invalidated: return
      }
      guard identity.workflowId == workflowId, identity.context == childContext,
        identity.prompt == currentItem?.prompt
      else { return }
      if case .started = event {
        guard validSetup, attempts.count < Self.attemptLimit,
          !attempts.contains(where: { $0.id == identity.attemptId }),
          !attempts.contains(where: { !$0.isFinished }),
          activePracticeVisit || isRound && currentRow?.primaryAttemptId == nil
        else { return }
        attempts.append(
          .init(
            identity: identity,
            purpose: phase == .practice ? .practice : phase == .firstRound ? .first : .recheck,
            roundId: phase == .practice ? nil : roundId,
            practiceVisitId: phase == .practice ? practiceVisit?.id : nil,
            itemId: identity.prompt.id))
        return
      }
      guard let a = attempts.firstIndex(where: { $0.identity == identity }), !attempts[a].isFinished
      else { return }
      switch event {
      case .captured(_, let hash):
        guard validSetup else { return }
        attempts[a].audioSha256 = hash
        if activePracticeVisit, attempts[a].purpose == .practice,
          attempts[a].practiceVisitId == practiceVisit?.id
        {
          practiceVisit?.capturedAttemptIds.insert(identity.attemptId)
        }
      case .submitted:
        guard validSetup, attempts[a].audioSha256 != nil, !attempts[a].submitted else { return }
        attempts[a].submitted = true
        if isRound, rows[index].primaryAttemptId == nil {
          rows[index].primaryAttemptId = identity.attemptId
          rows[index].disposition = .checkUnavailable
          rows[index].reason = "check_pending"
          rows[index].audioSha256 = attempts[a].audioSha256
        }
      case .requestStarted:
        guard validSetup, attempts[a].submitted, !attempts[a].requestStarted else { return }
        attempts[a].requestStarted = true
      case .validated(_, let value):
        guard validSetup, attempts[a].submitted, attempts[a].requestStarted else {
          settle(a, terminal: .invalidResponse)
          return
        }
        attempts[a].validated = true
        attempts[a].observation = value
        if isRound, rows[index].primaryAttemptId == identity.attemptId {
          rows[index].observation = value
          rows[index].reason = value.reason
          rows[index].disposition = Self.disposition(value)
        }
      case .terminal(_, let terminal): settle(a, terminal: terminal)
      case .bindingRejected:
        settle(a, terminal: .invalidResponse)
        invalidate()
      case .started, .invalidated: break
      }
    }
    private func settle(_ a: Int, terminal: ResearchFeedbackAttemptTerminal) {
      attempts[a].terminal = terminal
      if isRound, rows[index].primaryAttemptId == attempts[a].id {
        rows[index].disposition = .checkUnavailable
        rows[index].reason = terminal.rawValue
      }
    }
    private static func disposition(_ value: RecordingFeedback) -> ResearchGuidedWordDisposition {
      if ["silence", "clipping", "invalid_audio"].contains(value.reason ?? "") {
        return .recordingIssue
      }
      if value.status == .unavailable { return .checkUnavailable }
      switch value.word {
      case .modelMatched: return .modelMatched
      case .modelNotMatched: return .modelNotMatched
      case .uncertain: return .recognitionUncertain
      case .notSingleWord: return .notSingleSupportedWord
      case .notRun: return .speechNotDetected
      case .unavailable: return .checkUnavailable
      }
    }
    private static func makeFingerprint(_ context: ResearchPracticeContext) -> String {
      let encoder = FeedbackContract.encoder()
      // Context is validated on entry; every element is a fixed Encodable value.
      let data = (try? encoder.encode(context)) ?? Data()
      let bindings = FeedbackContract.pins.sorted { $0.key < $1.key }.map {
        "\($0.key):\($0.value)"
      }.joined(separator: "|")
      return FeedbackContract.sha(
        data + Data(bindings.utf8) + Data(canonicalHashes.joined(separator: "|").utf8))
    }
    static var catalogValid: Bool {
      let prompts = ResearchFeedbackCatalog.prompts
      guard prompts.count == canonicalHashes.count else { return false }
      return zip(prompts, canonicalHashes).allSatisfy { prompt, expected in
        guard let data = try? FeedbackContract.encoder().encode(prompt.requestPrompt) else {
          return false
        }
        return FeedbackContract.sha(data) == expected
      } && roster.count == 13
    }
    private static let canonicalHashes: [String] = [
      "85844397a23c2a18c9a92a428623c1facdf9282230c66994274c51c87a138ac8",
      "7910f87e3a252ae0b3a41dfa45649a122c461b7b1ca7fda67f6c309ab4c56383",
      "af488f0dd5b588d7fc99bfaa848911842108ca9f005c37d15fb8ba5e5c279ef2",
      "85b5d68283cab50ee5950f66d5cc2e63da5473cc4d33ab541cd6e0910e8e2054",
      "5474df711b0cf440d3909fcc6503573b52302e759500aa3d0971f6907e00da51",
      "ddf904bbec2f14c69082db3e59c1c45fcc017ce605b1a111f1f8a546cd8fc421",
      "f5f54cac611052db5cdf8c562b5ed917f0a40080b93ca5dac7d2b826ec3ed39e",
      "62f03ef1f1188d6e332865499593783e5508fbaef48e77c3664b092fe751fdb1",
      "f0c78e9754e628629ee36ae156a22be854f6d1414161efdc14e3e1f8ff715fbb",
      "955a86195ecb2ef2008e1ac1e7870c6fa6e12593fd36a4bac3db0c40a7f953d4",
      "c697644c9e5a1408c5c6b14fa342392d5c5a2b09a5290b1248f8899a0906303e",
      "e3f42848afc64fb0ec262bbf67fdfeacc99ab72d246e3595a2d9c0c115e07bbb",
      "770efea763c4e9a7bc8f5b4d3b6b86fd3b2c683dfafe66448ad94ec09f0a1e05",
      "f1f28ef21f563b6f99e6e8d2ce76a96c07cb8e79c64f7131f8ff90170f9a7b1d",
      "b65604125114d61043251741667162752d4c542feb788aff44a752057b0e05e7",
    ]
  }
#endif
