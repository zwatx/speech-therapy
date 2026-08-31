// One coordinator retains exact visit intent across media cleanup and stage changes.
import Combine
import Foundation

/// Repeat preserves the workflow, so both completed rounds belong to the action.
struct LocalGuidedCompletedSummaryIdentity: Equatable, Sendable {
  let workflowID: UUID
  let initialRoundID: UUID
  let recheckRoundID: UUID

  init(workflowID: UUID, initialRoundID: UUID, recheckRoundID: UUID) {
    self.workflowID = workflowID
    self.initialRoundID = initialRoundID
    self.recheckRoundID = recheckRoundID
  }

  init?(ledger: LocalGuidedReviewLedger) {
    guard ledger.stage == .completed, ledger.initialRound.isFinished,
      let recheck = ledger.recheckRound, recheck.isFinished,
      ledger.activeReviewVisit == nil, ledger.activePracticeVisit == nil
    else { return nil }
    self.init(workflowID: ledger.workflowID, initialRoundID: ledger.initialRound.id,
      recheckRoundID: recheck.id)
  }
}

/// A canonical next destination; review observations and media are never transferred.
struct LocalGuidedSummaryHandoff: Equatable, Sendable {
  enum Destination: Equatable, Sendable {
    case independentPractice(entry: PracticeLibraryEntry, sound: PracticeSound)
    case repeatReview(entryIDs: [String])
  }

  let id: UUID
  let summary: LocalGuidedCompletedSummaryIdentity
  let destination: Destination

  var canonicalSound: PracticeSound? {
    guard case .independentPractice(let entry, let sound) = destination,
      PracticeLibrary.entries().contains(entry),
      let canonical = PracticeLibrary.session(soundID: entry.soundID, position: entry.position,
        startingAt: entry.id, limit: 1),
      canonical.prompts == [entry.prompt], canonical == sound
    else { return nil }
    return canonical
  }

  var canonicalRepeatEntryIDs: [String]? {
    guard case .repeatReview(let ids) = destination,
      let entries = try? SavedGuidedWordsValidation.entries(entryIDs: ids),
      entries.map(\.id) == ids
    else { return nil }
    return ids
  }

  var isCanonical: Bool { canonicalSound != nil || canonicalRepeatEntryIDs != nil }
}

@MainActor
final class LocalGuidedReviewSession: ObservableObject {
  @Published private(set) var ledger: LocalGuidedReviewLedger?
  @Published private(set) var setupEntries: [PracticeLibraryEntry]
  private(set) var setupSeedFailed = false
  @Published private(set) var practiceSelectionIDs: [String] = []
  var isTransitioning: Bool { actionID != nil || closeTask != nil }
  @Published private(set) var isClosed = false
  @Published private var actionNote: String?
  let media: DirectPracticeSession
  #if DEBUG && targetEnvironment(simulator)
    private(set) var researchModel: GuidedResearchModelRecognizer?
    @Published private(set) var researchModelEnabled = false
    @Published private(set) var researchAgeYears: Int?
  #endif
  private var subscriptions: Set<AnyCancellable> = []
  private var actionID: UUID?
  private enum DepartureAction { case advance, skip, finish }
  private struct PendingDeparture {
    let visit: GuidedMediaVisit
    let action: DepartureAction
  }
  private var pendingDeparture: PendingDeparture?
  // Preparation can succeed before a publication is synchronously revoked. Retain its
  // exact visit so a later explicit Repeat releases it through the same media owner.
  private var uncommittedRepeatVisit: GuidedMediaVisit?
  private var uncommittedRepeatPrepared = false
  private var closeIntent = false
  private var closeTask: Task<Bool, Never>?
  private var summaryHandoff: LocalGuidedSummaryHandoff?
  private var independentPracticeCleanupPending = false
  // A terminal mirror cannot be reopened. Only our own explicit end attempt may
  // offer a fresh-owner Repeat after recovery; unrelated ended owners stay refused.
  private var independentPracticeEndedOwner = false

  init(
    history: PracticeParticipationStore = .shared, media: DirectPracticeSession? = nil,
    setupEntryIDs: [String]? = nil
  ) {
    let catalog = PracticeLibrary.entries()
    let words = [("b", "ball"), ("p", "pig"), ("m", "moon"), ("t", "tiger"), ("d", "dog")]
    let defaults = words.map { soundID, word in
      catalog.first {
        $0.soundID == soundID && $0.position == .beginning && $0.prompt.word == word
      }!
    }
    let seededEntries = setupEntryIDs.flatMap {
      try? SavedGuidedWordsValidation.entries(entryIDs: $0)
    }
    setupSeedFailed = setupEntryIDs != nil && seededEntries == nil
    let entries = seededEntries ?? defaults
    setupEntries = entries
    #if DEBUG && targetEnvironment(simulator)
      let model =
        media == nil
        ? GuidedResearchModelRecognizer(
          wordRecognizer: BundledLocalWordRecognizerFactory.make(), ownership: .shared)
        : nil
      researchModel = model
      self.media =
        media
        ?? DirectPracticeSession(
          sound: Self.sound(for: entries[0]), history: history, managedForGuided: true,
          wordRecognizer: model)
    #else
      self.media =
        media
        ?? DirectPracticeSession(
          sound: Self.sound(for: entries[0]), history: history, managedForGuided: true)
    #endif
    precondition(self.media.managedForGuided)
    self.media.guidedReviewEvents.sink { [weak self] event in
      guard let self, var next = self.ledger, next.receive(event) else { return }
      self.ledger = next
    }.store(in: &subscriptions)
    self.media.objectWillChange.sink { [weak self] _ in
      self?.objectWillChange.send()
    }.store(in: &subscriptions)
    self.media.$phase.sink { [weak self] phase in
      guard phase == .ended, let self, self.closeIntent else { return }
      // Published emits before storage. Re-read later and ask the same owner for end permission.
      Task { @MainActor [self] in await confirmRecoveredClose() }
    }.store(in: &subscriptions)
    #if DEBUG && targetEnvironment(simulator)
      observeResearchModel()
    #endif
  }

  #if DEBUG && targetEnvironment(simulator)
    /// Explicit injected owner for generated integration checks; ordinary fixture
    /// sessions continue to construct no research processor.
    convenience init(
      history: PracticeParticipationStore, media: DirectPracticeSession,
      researchModel: GuidedResearchModelRecognizer
    ) {
      self.init(history: history, media: media)
      self.researchModel = researchModel
      observeResearchModel()
    }

    private func observeResearchModel() {
      researchModel?.objectWillChange.sink { [weak self] _ in
        self?.objectWillChange.send()
      }.store(in: &subscriptions)
    }

    var canEditResearchSetup: Bool { admitsAction && ledger == nil && researchModel != nil }

    @discardableResult
    func configureResearchModel(enabled: Bool, ageYears: Int?) -> Bool {
      guard canEditResearchSetup,
        researchModel?.configure(ageYears: ageYears, enabled: enabled) == true
      else { return false }
      researchAgeYears = ageYears
      researchModelEnabled = enabled
      return true
    }
  #endif

  /// The review ledger remains word-only. Research observations are ephemeral,
  /// separate, and keyed to the exact first submitted operation in each round.
  func researchModelNote(for row: LocalGuidedReviewRow) -> String? {
    #if DEBUG && targetEnvironment(simulator)
      guard researchModelEnabled, let identity = row.firstSubmission,
        let observation = researchModel?.observations[identity.operationID],
        observation.entryID == row.entry.id,
        observation.request.tryID == identity.tryID
      else { return nil }
      return observation.note
    #else
      return nil
    #endif
  }

  #if DEBUG && targetEnvironment(simulator)
    /// Resolve only the current workflow's canonical rows; opening details performs no work.
    func researchDetails(workflowID: UUID, entryID: String) -> GuidedResearchDetailsPresentation? {
      guard admitsAction, !isTransitioning, researchModelEnabled,
        let age = researchAgeYears, let model = researchModel, let ledger,
        ledger.workflowID == workflowID,
        ledger.stage == .choosingPractice || ledger.stage == .completed,
        ledger.initialRound.isFinished,
        let entry = ledger.entries.first(where: { $0.id == entryID }),
        ledger.initialRound.rows.filter({ $0.entry.id == entryID }).count == 1,
        let initial = ledger.initialRound.rows.first(where: { $0.entry.id == entryID })
      else { return nil }
      let recheck: LocalGuidedReviewRow?
      if ledger.stage == .completed {
        guard let round = ledger.recheckRound, round.isFinished,
          round.rows.filter({ $0.entry.id == entryID }).count == 1
        else { return nil }
        recheck = round.rows.first(where: { $0.entry.id == entryID })
      } else {
        recheck = nil
      }
      return .init(id: .init(workflowID: workflowID, entryID: entryID), word: entry.prompt.word,
        initial: .resolve(row: initial, workflowID: workflowID, roundID: ledger.initialRound.id,
          entry: entry, ageYears: age, observations: model.observations),
        recheck: .resolve(row: recheck, workflowID: workflowID, roundID: ledger.recheckRound?.id,
          entry: entry, ageYears: age, observations: model.observations))
    }
  #endif

  private var modelProcessingNote: String? {
    #if DEBUG && targetEnvironment(simulator)
      return researchModelEnabled ? researchModel?.statusNote : nil
    #else
      return nil
    #endif
  }

  private var modelCheckLabel: String? {
    #if DEBUG && targetEnvironment(simulator)
      return researchModelEnabled ? "Check word and run research model" : nil
    #else
      return nil
    #endif
  }

  private var currentModelObservationNote: String? {
    #if DEBUG && targetEnvironment(simulator)
      guard researchModelEnabled, let tryID = media.checkedTryID,
        tryID == media.latestTry?.id, let model = researchModel,
        model.processingState == .idle, let operationID = model.latestObservationOperationID,
        let observation = model.observations[operationID],
        observation.request.tryID == tryID, observation.entryID == media.currentPrompt.id
      else { return nil }
      return observation.note
    #else
      return nil
    #endif
  }

  private func firstReviewContextNote(entryID: String, ledger: LocalGuidedReviewLedger) -> String? {
    guard let wordNote = Self.firstReviewNote(for: entryID, in: ledger) else { return nil }
    guard let row = ledger.initialRound.rows.first(where: { $0.entry.id == entryID }),
      let modelNote = researchModelNote(for: row)
    else { return wordNote }
    return wordNote + " " + modelNote
  }

  private static func sound(for entry: PracticeLibraryEntry) -> PracticeSound {
    let sound = PracticeLibrary.sounds.first { $0.id == entry.soundID }!
    return .init(
      id: sound.id, symbol: sound.symbol, name: sound.name,
      position: entry.position, prompts: [entry.prompt])
  }

  var canClose: Bool { !isClosed }
  var statusNote: String? {
    if independentPracticeCleanupPending {
      if isTransitioning { return "Practice hasn’t opened. Waiting for cleanup to finish." }
      return media.hasFullyEndedCleanup
        ? "Cleanup finished. Practice hasn’t opened. Tap Practice again."
        : "Practice hasn’t opened. Retry cleanup, then tap Practice again."
    }
    return media.closeNote ?? actionNote
  }
  private var admitsAction: Bool { !isClosed && !closeIntent && actionID == nil }
  var canSaveSetupWords: Bool {
    admitsAction && ledger == nil && !isTransitioning && media.phase == .ready
      && media.guidedMediaVisit == nil
  }

  @discardableResult
  func configureSetup(entryIDs: [String]) -> Bool {
    guard canSaveSetupWords,
      let entries = try? SavedGuidedWordsValidation.entries(entryIDs: entryIDs)
    else { return false }
    setupEntries = entries
    return true
  }

  var canStartInitial: Bool {
    #if DEBUG && targetEnvironment(simulator)
      if researchModelEnabled, researchAgeYears.map({ (6...12).contains($0) }) != true {
        return false
      }
    #endif
    return admitsAction && ledger == nil && setupEntries.count == 5
  }
  var canStartPractice: Bool {
    admitsAction && ledger?.stage == .choosingPractice
      && (1...3).contains(practiceSelectionIDs.count)
  }
  var canStartRecheck: Bool { admitsAction && ledger?.stage == .readyToRecheck }

  @discardableResult
  func replaceSetupEntry(at index: Int, with entry: PracticeLibraryEntry) -> Bool {
    guard admitsAction, ledger == nil, setupEntries.indices.contains(index),
      PracticeLibrary.entries().contains(entry),
      !setupEntries.enumerated().contains(where: {
        $0.offset != index && $0.element.prompt.word.lowercased() == entry.prompt.word.lowercased()
      })
    else { return false }
    var entries = setupEntries
    entries[index] = entry
    setupEntries = entries
    return true
  }

  func togglePracticeSelection(entryID: String) {
    guard admitsAction, let ledger, ledger.stage == .choosingPractice,
      ledger.entries.contains(where: { $0.id == entryID })
    else { return }
    var selected = practiceSelectionIDs
    if let index = selected.firstIndex(of: entryID) {
      selected.remove(at: index)
    } else if selected.count < 3 {
      selected.append(entryID)
    }
    practiceSelectionIDs = selected
  }

  private func beginAction() -> UUID? {
    guard admitsAction else { return nil }
    let id = UUID()
    actionID = id
    independentPracticeCleanupPending = false
    objectWillChange.send()
    guard isCurrent(id) else { return nil }
    actionNote = nil
    return isCurrent(id) ? id : nil
  }

  private func isCurrent(_ id: UUID) -> Bool { actionID == id && !closeIntent && !isClosed }
  private func finishAction(_ id: UUID) {
    guard actionID == id else { return }
    actionID = nil
    objectWillChange.send()
  }

  func startInitialReview() async {
    guard canStartInitial, let id = beginAction() else { return }
    defer { finishAction(id) }
    guard let next = try? LocalGuidedReviewLedger(entryIDs: setupEntries.map(\.id)) else {
      actionNote = "Choose five different words from the library."
      return
    }
    ledger = next
    guard isCurrent(id) else { return }
    await prepareNextVisit(action: id)
  }

  var canRepeatReview: Bool {
    admitsAction && ledger?.stage == .completed
      && (!repeatRequiresSummaryDeparture || (!media.cleanupBlocked && !media.isTransitioning))
  }

  var repeatRequiresSummaryDeparture: Bool {
    independentPracticeEndedOwner
  }

  var completedSummaryIdentity: LocalGuidedCompletedSummaryIdentity? {
    ledger.flatMap(LocalGuidedCompletedSummaryIdentity.init(ledger:))
  }

  func canPracticeIndependently(
    entryID: String, summary: LocalGuidedCompletedSummaryIdentity
  ) -> Bool {
    admitsAction && closeTask == nil && summaryHandoff == nil
      && independentPracticeEntry(entryID: entryID, summary: summary) != nil
  }

  private func independentPracticeEntry(
    entryID: String, summary: LocalGuidedCompletedSummaryIdentity
  ) -> PracticeLibraryEntry? {
    guard completedSummaryIdentity == summary, let ledger,
      ledger.pairedRows.filter({ $0.entry.id == entryID }).count == 1,
      let row = ledger.pairedRows.first(where: { $0.entry.id == entryID }),
      row.initial.entry == row.entry, row.recheck.entry == row.entry,
      PracticeLibrary.entries().contains(row.entry)
    else { return nil }
    return row.entry
  }

  /// This cleanup intent never authorizes an automatic recovered Close or launch.
  /// Failure leaves the same completed ledger available for an explicit later tap.
  func practiceIndependently(
    entryID: String, summary: LocalGuidedCompletedSummaryIdentity
  ) async {
    guard !Task.isCancelled, canPracticeIndependently(entryID: entryID, summary: summary),
      let entry = independentPracticeEntry(entryID: entryID, summary: summary),
      let sound = PracticeLibrary.session(soundID: entry.soundID, position: entry.position,
        startingAt: entryID, limit: 1), sound.prompts == [entry.prompt],
      let id = beginAction()
    else { return }
    var committed = false
    defer { if !committed { finishAction(id) } }
    func eligible() -> Bool {
      actionID == id && !closeIntent && closeTask == nil && !Task.isCancelled
        && independentPracticeEntry(entryID: entryID, summary: summary) == entry
    }
    guard eligible(), !isClosed else { return }
    if media.phase != .ended, !media.closeRequested { independentPracticeEndedOwner = true }
    independentPracticeCleanupPending = true
    let ended = await media.end()
    guard eligible(), !isClosed else { return }
    guard ended, media.hasFullyEndedCleanup else {
      independentPracticeCleanupPending = true
      return
    }
    summaryHandoff = .init(id: id, summary: summary,
      destination: .independentPractice(entry: entry, sound: sound))
    // Stage before willSet, but consumption requires the committed getter. A synchronous
    // Close/lifecycle/cancellation observer can still revoke the token during publication.
    isClosed = true
    guard eligible(), media.hasFullyEndedCleanup,
      summaryHandoff?.id == id, isClosed
    else {
      summaryHandoff = nil
      if !closeIntent, isClosed { isClosed = false }
      return
    }
    committed = true
  }

  /// Called by the closed-state observer, never during willSet or a cleanup waiter.
  func consumeSummaryHandoff() -> LocalGuidedSummaryHandoff? {
    guard isClosed, let handoff = summaryHandoff else { return nil }
    guard !closeIntent, closeTask == nil, !Task.isCancelled, actionID == handoff.id,
      handoffMatchesSummary(handoff), media.hasFullyEndedCleanup
    else {
      if !closeIntent {
        summaryHandoff = nil
        actionID = nil
        independentPracticeCleanupPending = true
        isClosed = false
      }
      return nil
    }
    summaryHandoff = nil
    actionID = nil
    return handoff
  }

  private func handoffMatchesSummary(_ handoff: LocalGuidedSummaryHandoff) -> Bool {
    guard completedSummaryIdentity == handoff.summary, handoff.isCanonical else { return false }
    switch handoff.destination {
    case .independentPractice(let entry, _):
      return independentPracticeEntry(entryID: entry.id, summary: handoff.summary) == entry
    case .repeatReview(let ids):
      return independentPracticeEndedOwner && ledger?.entries.map(\.id) == ids
    }
  }

  private func handoffToFreshReview() async {
    guard repeatRequiresSummaryDeparture, canRepeatReview,
      let summary = completedSummaryIdentity, let ledger, let id = beginAction()
    else { return }
    var committed = false
    defer { if !committed { finishAction(id) } }
    func eligible() -> Bool {
      actionID == id && !closeIntent && closeTask == nil && !Task.isCancelled
        && completedSummaryIdentity == summary
    }
    guard eligible(), !isClosed else { return }
    // File-only recovery can publish ready even after the mirror's terminal Close.
    // Reconfirm end here; never prepare that released owner as a new review.
    let ended = await media.end()
    guard eligible(), !isClosed else { return }
    guard ended, media.hasFullyEndedCleanup else {
      independentPracticeCleanupPending = true
      return
    }
    summaryHandoff = .init(id: id, summary: summary,
      destination: .repeatReview(entryIDs: ledger.entries.map(\.id)))
    guard let handoff = summaryHandoff, handoffMatchesSummary(handoff) else { return }
    isClosed = true
    guard eligible(), media.hasFullyEndedCleanup, summaryHandoff?.id == id, isClosed else {
      summaryHandoff = nil
      if !closeIntent, isClosed { isClosed = false }
      return
    }
    committed = true
  }

  /// A new round within the same open workflow. Permanent media/workflow ownership and
  /// retired visit IDs remain intact; no sensor, playback or recognizer starts here.
  func repeatReview() async {
    if repeatRequiresSummaryDeparture {
      await handoffToFreshReview()
      return
    }
    guard canRepeatReview, let previous = ledger, let id = beginAction() else { return }
    defer { finishAction(id) }
    func eligible() -> Bool { isCurrent(id) && !Task.isCancelled }
    guard eligible() else { return }
    let selection = practiceSelectionIDs
    if let abandoned = uncommittedRepeatVisit {
      if media.guidedMediaVisit == abandoned {
        let released = await media.leaveGuidedVisit(abandoned)
        guard eligible() else { return }
        guard released else {
          actionNote =
            "The previous review is still stopping. Retry cleanup or Close before reviewing again."
          return
        }
      } else if uncommittedRepeatPrepared && media.guidedReleasedVisit != abandoned {
        actionNote =
          "The previous review is still stopping. Retry cleanup or Close before reviewing again."
        return
      }
      uncommittedRepeatVisit = nil
      uncommittedRepeatPrepared = false
    }
    guard media.guidedMediaVisit == nil,
      var next = try? LocalGuidedReviewLedger(
        entryIDs: previous.entries.map(\.id), workflowID: previous.workflowID),
      let visit = next.beginReviewVisit(visitID: UUID()),
      let entry = next.entries.first
    else {
      actionNote =
        "The previous review is not ready to restart. Retry cleanup or Close before reviewing again."
      return
    }
    uncommittedRepeatVisit = .review(visit)
    // The existing method admits only a fully clean owner and released preview. Keep
    // the completed summary visible until that exact preparation succeeds.
    let prepared = await media.prepareGuidedVisit(entry: entry, visit: .review(visit))
    guard uncommittedRepeatVisit == .review(visit) else { return }
    uncommittedRepeatPrepared = prepared
    guard eligible() else { return }
    guard prepared else {
      actionNote =
        "The previous review is not ready to restart. Retry cleanup or Close before reviewing again."
      return
    }
    practiceSelectionIDs = []
    guard eligible() else {
      practiceSelectionIDs = selection
      return
    }
    ledger = next
    // Published delivers in willSet. Close/background can revoke this action while
    // the outer assignment still stores; restore the completed summary in that case.
    guard eligible() else {
      ledger = previous
      practiceSelectionIDs = selection
      return
    }
    pendingDeparture = nil
    uncommittedRepeatVisit = nil
    uncommittedRepeatPrepared = false
  }

  func startPractice() async {
    guard canStartPractice, let id = beginAction(), var next = ledger else { return }
    defer { finishAction(id) }
    guard next.beginPractice(entryIDs: practiceSelectionIDs, practiceID: UUID()) else { return }
    ledger = next
    guard isCurrent(id) else { return }
    await prepareNextVisit(action: id)
  }

  func startRecheck() async {
    guard canStartRecheck, let id = beginAction(), var next = ledger else { return }
    defer { finishAction(id) }
    guard next.beginRecheck(roundID: UUID()) else { return }
    ledger = next
    guard isCurrent(id) else { return }
    await prepareNextVisit(action: id)
  }

  private func prepareNextVisit(action id: UUID) async {
    guard isCurrent(id), var next = ledger else { return }
    let visit: GuidedMediaVisit
    let entryID: String
    switch next.stage {
    case .initialReview, .recheck:
      guard let opened = next.beginReviewVisit(visitID: UUID()) else { return }
      visit = .review(opened)
      entryID = opened.entryID
    case .practice:
      guard let opened = next.beginPracticeVisit(visitID: UUID()) else { return }
      visit = .practice(opened)
      entryID = opened.entryID
    default: return
    }
    guard let entry = next.entries.first(where: { $0.id == entryID }) else { return }
    ledger = next
    guard isCurrent(id) else { return }
    let prepared = await media.prepareGuidedVisit(entry: entry, visit: visit)
    guard isCurrent(id) else { return }
    if !prepared { actionNote = "This word is paused until its recording cleanup is confirmed." }
  }

  /// A failed preparation keeps the same frozen visit and owner; never a replacement session.
  func retryVisitPreparation() async {
    // A released visit cannot be prepared a second time. Rejoin only the exact
    // departure intent already chosen, after the same owner confirms its receipt.
    if admitsAction, let pending = pendingDeparture,
      media.guidedReleasedVisit == pending.visit,
      pending.visit == ledger?.activeReviewVisit.map(GuidedMediaVisit.review)
        || pending.visit == ledger?.activePracticeVisit.map(GuidedMediaVisit.practice)
    {
      switch pending.action {
      case .advance: await advanceVisit()
      case .skip: await skipVisit()
      case .finish: await finishStageNow()
      }
      return
    }
    guard ledger != nil, let id = beginAction(), let snapshot = ledger else { return }
    defer { finishAction(id) }
    if snapshot.activeReviewVisit == nil && snapshot.activePracticeVisit == nil {
      await prepareNextVisit(action: id)
      return
    }
    let visit: GuidedMediaVisit
    let entryID: String
    if let active = snapshot.activeReviewVisit {
      visit = .review(active)
      entryID = active.entryID
    } else if let active = snapshot.activePracticeVisit {
      visit = .practice(active)
      entryID = active.entryID
    } else {
      return
    }
    guard media.guidedMediaVisit != visit,
      let entry = snapshot.entries.first(where: { $0.id == entryID })
    else { return }
    if media.canRetryCleanup {
      await media.retryCleanup()
      guard isCurrent(id) else { return }
    }
    let prepared = await media.prepareGuidedVisit(entry: entry, visit: visit)
    guard isCurrent(id) else { return }
    if !prepared { actionNote = "This word is paused until its recording cleanup is confirmed." }
  }

  private var activeReviewRow: LocalGuidedReviewRow? {
    guard let ledger, let visit = ledger.activeReviewVisit else { return nil }
    return ledger.activeRound?.rows.first { $0.visit == visit }
  }
  private var activePracticeRow: LocalGuidedPracticeRow? {
    guard let ledger, let visit = ledger.activePracticeVisit else { return nil }
    return ledger.practiceRows.first { $0.visit == visit }
  }

  private var canAdvance: Bool {
    guard admitsAction, !media.cleanupBlocked else { return false }
    if let row = activeReviewRow, case .finished = row.state { return true }
    if let row = activePracticeRow {
      if case .finished = row.state { return true }
      if row.state == .ready {
        if case .review = media.phase {
          guard let latest = media.latestTry, case .acceptable = latest.assessment else {
            return false
          }
          return latest.summary.duration.isFinite && latest.summary.averagePower.isFinite
        }
        // Explicit mirror retry can finish the same pending practice intent. Next
        // still reads its exact completion receipt before committing the ledger.
        if media.phase == .completed, let visit = row.visit {
          return media.participationCompletion?.id == visit.visitID
        }
      }
    }
    return false
  }
  private var practiceRecordingRequirement: DirectPracticeRecordingAdvice? {
    guard !isClosed, !closeIntent, !isTransitioning, !media.isTransitioning,
      !media.closeRequested, !media.cleanupBlocked,
      let ledger, ledger.stage == .practice,
      let row = activePracticeRow, row.state == .ready, let visit = row.visit,
      media.guidedMediaVisit == .practice(visit), media.currentPrompt.id == visit.entryID,
      case .review = media.phase, let latest = media.latestTry
    else { return nil }
    return DirectPracticeRecordingAdvice.practiceRequirement(
      summary: latest.summary, assessment: latest.assessment)
  }

  private var canSkip: Bool {
    guard admitsAction, !media.cleanupBlocked else { return false }
    return activeReviewRow?.state == .ready || activePracticeRow?.state == .ready
  }
  private var canFinishStage: Bool {
    guard admitsAction, !media.cleanupBlocked, let ledger else { return false }
    return ledger.activeReviewVisit != nil || ledger.activePracticeVisit != nil
  }

  private var hasReadyWordCheckVisit: Bool {
    if let row = activeReviewRow, row.state == .ready, let visit = row.visit {
      return media.guidedMediaVisit == .review(visit)
    }
    if let row = activePracticeRow, row.state == .ready, let visit = row.visit {
      return media.guidedMediaVisit == .practice(visit)
    }
    return false
  }

  private var showsRecordAndCheck: Bool {
    #if DEBUG && targetEnvironment(simulator)
      guard !researchModelEnabled else { return false }
    #endif
    guard !isClosed, let ledger,
      ledger.stage == .initialReview || ledger.stage == .recheck,
      let row = activeReviewRow, row.state == .ready, let visit = row.visit
    else { return false }
    return media.guidedMediaVisit == .review(visit)
  }

  func recordAndCheckCurrentWord() async {
    guard showsRecordAndCheck, admitsAction,
      media.canStartRecordingAndCheckWord || media.canRecordAnotherTryAndCheckWord
    else { return }
    #if DEBUG && targetEnvironment(simulator)
      if let researchModel {
        guard let entry = ledger?.entries.first(where: { $0.id == media.currentPrompt.id }),
          researchModel.prepare(entry: entry, visit: media.guidedMediaVisit)
        else { return }
      }
    #endif
    guard showsRecordAndCheck, admitsAction else { return }
    if media.latestTry == nil {
      await media.startRecordingAndCheckWord()
    } else {
      await media.recordAnotherTryAndCheckWord()
    }
  }

  func checkCurrentWord() async {
    guard admitsAction, hasReadyWordCheckVisit else { return }
    #if DEBUG && targetEnvironment(simulator)
      if let researchModel {
        guard let entry = ledger?.entries.first(where: { $0.id == media.currentPrompt.id }),
          researchModel.prepare(entry: entry, visit: media.guidedMediaVisit)
        else { return }
      }
    #endif
    await media.startWordCheck()
  }

  func advanceVisit() async {
    guard canAdvance, let id = beginAction(), let snapshot = ledger else { return }
    defer { finishAction(id) }
    if let visit = snapshot.activeReviewVisit {
      pendingDeparture = .init(visit: .review(visit), action: .advance)
      let cleaned = await media.leaveGuidedVisit(.review(visit))
      guard isCurrent(id), var next = ledger,
        next.leaveReviewVisit(visit, cleanupConfirmed: cleaned)
      else { return }
      pendingDeparture = nil
      ledger = next
    } else if let visit = snapshot.activePracticeVisit {
      if activePracticeRow?.state == .ready {
        let result = await media.finishGuidedPractice(visit)
        guard isCurrent(id), result.visit == visit, result.cleanupConfirmed,
          result.completionID == visit.visitID, var next = ledger,
          next.finishPracticeVisit(
            visit, disposition: result.saveConfirmed ? .finished : .saveUnconfirmed,
            freshTryID: result.freshTryID, cleanupConfirmed: true)
        else { return }
        ledger = next
        // An unsaved completion stays reachable for an explicit retry or Continue without saving.
        if !result.saveConfirmed { return }
      }
      guard isCurrent(id) else { return }
      pendingDeparture = .init(visit: .practice(visit), action: .advance)
      let cleaned = await media.leaveGuidedVisit(.practice(visit))
      guard isCurrent(id), var next = ledger,
        next.leavePracticeVisit(visit, cleanupConfirmed: cleaned)
      else { return }
      pendingDeparture = nil
      ledger = next
    }
    guard isCurrent(id) else { return }
    await prepareNextVisit(action: id)
  }

  func skipVisit() async {
    guard canSkip, let id = beginAction(), let snapshot = ledger else { return }
    defer { finishAction(id) }
    if let visit = snapshot.activeReviewVisit {
      pendingDeparture = .init(visit: .review(visit), action: .skip)
      let cleaned = await media.leaveGuidedVisit(.review(visit))
      guard isCurrent(id), var next = ledger,
        next.skipReviewVisit(visit, cleanupConfirmed: cleaned)
      else { return }
      pendingDeparture = nil
      ledger = next
    } else if let visit = snapshot.activePracticeVisit {
      pendingDeparture = .init(visit: .practice(visit), action: .skip)
      let cleaned = await media.leaveGuidedVisit(.practice(visit))
      guard isCurrent(id), var next = ledger,
        next.finishPracticeVisit(
          visit, disposition: .skipped, freshTryID: nil, cleanupConfirmed: cleaned),
        next.leavePracticeVisit(visit, cleanupConfirmed: cleaned)
      else { return }
      pendingDeparture = nil
      ledger = next
    }
    guard isCurrent(id) else { return }
    await prepareNextVisit(action: id)
  }

  func finishStageNow() async {
    guard canFinishStage, let id = beginAction(), let snapshot = ledger else { return }
    defer { finishAction(id) }
    if let visit = snapshot.activeReviewVisit {
      pendingDeparture = .init(visit: .review(visit), action: .finish)
      let cleaned = await media.leaveGuidedVisit(.review(visit))
      guard isCurrent(id), var next = ledger,
        next.finishReviewNow(
          roundID: visit.roundID, visitID: visit.visitID, cleanupConfirmed: cleaned)
      else { return }
      pendingDeparture = nil
      ledger = next
    } else if let visit = snapshot.activePracticeVisit {
      pendingDeparture = .init(visit: .practice(visit), action: .finish)
      let cleaned = await media.leaveGuidedVisit(.practice(visit))
      guard isCurrent(id), var next = ledger,
        next.finishPracticeNow(
          practiceID: visit.practiceID, visitID: visit.visitID,
          cleanupConfirmed: cleaned)
      else { return }
      pendingDeparture = nil
      ledger = next
    }
  }

  func retryPracticeSave() {
    guard admitsAction, let visit = ledger?.activePracticeVisit,
      activePracticeRow?.state == .finished(.saveUnconfirmed)
    else { return }
    media.retryParticipationSave()
    guard admitsAction, media.participationCompletion?.id == visit.visitID,
      media.historyError == nil, var next = ledger,
      next.acknowledgePracticeSaved(visit, completionID: visit.visitID)
    else { return }
    ledger = next
  }

  func close() async -> Bool {
    if isClosed { return true }
    if let closeTask { return await closeTask.value }
    closeIntent = true
    actionID = UUID()
    objectWillChange.send()
    let task = Task { @MainActor [self] in
      let ended = await media.end()
      if ended { isClosed = true }
      objectWillChange.send()
      return ended
    }
    closeTask = task
    let ended = await task.value
    closeTask = nil
    actionID = nil
    objectWillChange.send()
    return ended
  }

  private func confirmRecoveredClose() async {
    if let closeTask { _ = await closeTask.value }
    guard closeIntent, !isClosed, media.phase == .ended else { return }
    let permitted = await media.end()
    guard permitted, closeIntent, media.phase == .ended else { return }
    actionID = nil
    isClosed = true
  }

  func sceneInactive() { media.appDidBecomeInactive() }
  func sceneActive() { media.appDidBecomeActive() }
  func background() {
    revokeAction()
    media.appDidEnterBackground()
  }
  func interrupted() {
    revokeAction()
    media.audioWasInterrupted()
  }
  func disappeared() {
    revokeAction()
    media.viewDidDisappear()
  }
  private func revokeAction() {
    actionID = nil
    objectWillChange.send()
  }

  /// The first round is frozen before practice begins. Match the exact library entry,
  /// since a printed word can occur under more than one intended sound.
  nonisolated static func firstReviewNote(for entryID: String, in ledger: LocalGuidedReviewLedger)
    -> String?
  {
    guard ledger.initialRound.isFinished,
      let row = ledger.initialRound.rows.first(where: { $0.entry.id == entryID }),
      case .finished(let disposition) = row.state
    else { return nil }
    return
      "First review: \(disposition.wordObservation). Word checks cannot identify which sound was made."
  }

  var playerPresentation: DirectPracticeGuidedPresentation {
    let stage = ledger?.stage
    let review = activeReviewRow
    let practice = activePracticeRow
    let title = stage == .recheck ? "Recheck" : stage == .practice ? "Practice" : "First review"
    let ordinal: Int = {
      if let visit = ledger?.activeReviewVisit,
        let index = ledger?.entries.firstIndex(where: { $0.id == visit.entryID })
      {
        return index + 1
      }
      if let visit = ledger?.activePracticeVisit,
        let index = ledger?.practiceRows.firstIndex(where: { $0.visit == visit })
      {
        return index + 1
      }
      return 1
    }()
    let count = stage == .practice ? ledger?.practiceRows.count ?? 0 : 5
    let continueLabel: String = {
      if practice?.state == .finished(.saveUnconfirmed) { return "Continue without saving" }
      guard ordinal == count else { return "Next word" }
      switch stage {
      case .initialReview: return "Choose practice words"
      case .practice: return "Finish practice"
      case .recheck: return "View summary"
      default: return "Next word"
      }
    }()
    let firstNote: String? = {
      if stage == .practice {
        guard let ledger, let visit = ledger.activePracticeVisit,
          media.guidedMediaVisit == .practice(visit), media.currentPrompt.id == visit.entryID
        else { return nil }
        return firstReviewContextNote(entryID: visit.entryID, ledger: ledger)
      }
      if stage == .recheck {
        guard let ledger, let visit = ledger.activeReviewVisit,
          media.guidedMediaVisit == .review(visit), media.currentPrompt.id == visit.entryID
        else { return nil }
        return firstReviewContextNote(entryID: visit.entryID, ledger: ledger)
      }
      return nil
    }()
    let firstCheckStatus: String? = {
      guard stage == .initialReview, let review, let visit = review.visit,
        media.guidedMediaVisit == .review(visit), media.currentPrompt.id == visit.entryID
      else { return nil }
      return switch review.state {
      case .pending: "First check in progress."
      case .cleanupBlocked: "First check cleanup has not been confirmed."
      case .finished: "The first check is kept for this review."
      default: nil
      }
    }()
    return .init(
      stageTitle: title, positionLabel: "\(ordinal) of \(count)", statusNote: statusNote,
      firstObservationNote: firstNote, firstCheckStatusNote: firstCheckStatus,
      showsRecordAndCheck: showsRecordAndCheck,
      canRecordAndCheck: showsRecordAndCheck && admitsAction && media.canStartRecordingAndCheckWord,
      recordAndCheck: { [self] in await recordAndCheckCurrentWord() },
      showsWordCheck: true,
      checkLabel: modelCheckLabel, checkProgressNote: modelProcessingNote,
      modelObservationNote: currentModelObservationNote,
      canCheckWords: admitsAction && hasReadyWordCheckVisit && media.canCheckWordsInLatestTry,
      check: { [self] in await checkCurrentWord() },
      continueLabel: continueLabel,
      canContinue: canAdvance, continueVisit: { [self] in await advanceVisit() },
      canSkip: canSkip, skip: { [self] in await skipVisit() },
      finishStageLabel: stage == .practice ? "Finish practice now" : "Finish this review now",
      canFinishStage: canFinishStage, finishStage: { [self] in await finishStageNow() },
      canRetrySave: admitsAction && practice?.state == .finished(.saveUnconfirmed)
        && media.canRetryParticipationSave,
      retrySave: { [self] in retryPracticeSave() })
  }
}
