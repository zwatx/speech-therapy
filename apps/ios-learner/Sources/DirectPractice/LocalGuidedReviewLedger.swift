import Foundation

enum LocalGuidedReviewStage: Equatable, Sendable {
  case initialReview
  case choosingPractice
  case practice
  case readyToRecheck
  case recheck
  case completed
}

struct LocalGuidedReviewVisit: Equatable, Sendable {
  let workflowID: UUID
  let roundID: UUID
  let visitID: UUID
  let entryID: String
}

struct LocalGuidedCheckIdentity: Equatable, Sendable {
  let visit: LocalGuidedReviewVisit
  let operationID: UUID
  let tryID: UUID
}

enum LocalGuidedReviewDisposition: Equatable, Sendable {
  case matched
  case notMatched
  case uncertain
  case timedOut
  case unavailable
  case cancelled
  case skipped
  case unreached

  fileprivate init(_ status: LocalWordRecognitionStatus) {
    switch status {
    case .matched: self = .matched
    case .notMatched: self = .notMatched
    case .uncertain: self = .uncertain
    case .timedOut: self = .timedOut
    case .unavailable: self = .unavailable
    case .cancelled: self = .cancelled
    }
  }

  /// The same frozen word observation appears in the summary and practice context.
  var wordObservation: String {
    switch self {
    case .matched: "Word matched"
    case .notMatched: "No word match"
    case .uncertain: "No clear match"
    case .timedOut: "Word check took too long"
    case .unavailable: "Check unavailable"
    case .cancelled: "Check cancelled"
    case .skipped: "Skipped"
    case .unreached: "Not reached"
    }
  }
}

enum LocalGuidedReviewRowState: Equatable, Sendable {
  case notVisited
  case ready
  case pending
  case cleanupBlocked
  case finished(LocalGuidedReviewDisposition)
}

struct LocalGuidedReviewRow: Equatable, Sendable {
  let entry: PracticeLibraryEntry
  let visit: LocalGuidedReviewVisit?
  let firstSubmission: LocalGuidedCheckIdentity?
  let state: LocalGuidedReviewRowState
}

struct LocalGuidedReviewRound: Equatable, Sendable {
  let id: UUID
  let rows: [LocalGuidedReviewRow]
  let isFinished: Bool
}

enum LocalGuidedReviewEvent: Sendable {
  case submitted(LocalGuidedCheckIdentity)
  case settled(
    identity: LocalGuidedCheckIdentity, status: LocalWordRecognitionStatus,
    resultEligible: Bool, cleanupConfirmed: Bool)
}

struct LocalGuidedPracticeVisit: Equatable, Sendable {
  let workflowID: UUID
  let practiceID: UUID
  let visitID: UUID
  let entryID: String
}

enum LocalGuidedPracticeDisposition: Equatable, Sendable {
  case finished
  case saveUnconfirmed
  case skipped
  case unreached
}

enum LocalGuidedPracticeRowState: Equatable, Sendable {
  case notVisited
  case ready
  case finished(LocalGuidedPracticeDisposition)
}

/// Participation metadata only; review observations are never copied into practice rows.
struct LocalGuidedPracticeRow: Equatable, Sendable {
  let entry: PracticeLibraryEntry
  let visit: LocalGuidedPracticeVisit?
  let freshTryID: UUID?
  let state: LocalGuidedPracticeRowState
}

struct LocalGuidedPairedReviewRow: Equatable, Sendable {
  let entry: PracticeLibraryEntry
  let initial: LocalGuidedReviewRow
  /// Nil means this canonical entry was not selected for practice.
  let practice: LocalGuidedPracticeRow?
  let recheck: LocalGuidedReviewRow
}

/// Pure in-memory ledger. The coordinator supplies exact media-owner acknowledgements;
/// this value never infers cleanup, capture validity or a history write from screen state.
struct LocalGuidedReviewLedger: Sendable {
  enum PlanError: Error, Equatable {
    case requiresFiveWords
    case unknownCanonicalEntry
    case duplicatePrintedWord
    case reusedIdentity
  }

  let workflowID: UUID
  let entries: [PracticeLibraryEntry]
  private(set) var stage: LocalGuidedReviewStage = .initialReview
  private(set) var initialRound: LocalGuidedReviewRound
  private(set) var recheckRound: LocalGuidedReviewRound?
  private(set) var practiceID: UUID?
  private(set) var practiceRows: [LocalGuidedPracticeRow] = []
  private(set) var activeReviewVisit: LocalGuidedReviewVisit?
  private(set) var activePracticeVisit: LocalGuidedPracticeVisit?
  private var reviewIndex = 0
  private var practiceIndex = 0
  private var usedIDs: Set<UUID>

  init(entryIDs: [String], workflowID: UUID = UUID(), initialRoundID: UUID = UUID()) throws {
    guard entryIDs.count == 5 else { throw PlanError.requiresFiveWords }
    guard workflowID != initialRoundID else { throw PlanError.reusedIdentity }
    let catalog = PracticeLibrary.entries()
    var frozen: [PracticeLibraryEntry] = []
    var words: Set<String> = []
    for id in entryIDs {
      guard let entry = catalog.first(where: { $0.id == id }) else {
        throw PlanError.unknownCanonicalEntry
      }
      let word = entry.prompt.word.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      guard words.insert(word).inserted else { throw PlanError.duplicatePrintedWord }
      frozen.append(entry)
    }
    self.workflowID = workflowID
    entries = frozen
    initialRound = Self.emptyRound(id: initialRoundID, entries: frozen)
    usedIDs = [workflowID, initialRoundID]
  }

  var activeRound: LocalGuidedReviewRound? {
    switch stage {
    case .initialReview: initialRound
    case .recheck: recheckRound
    default: nil
    }
  }

  var selectedPracticeEntryIDs: [String] { practiceRows.map { $0.entry.id } }

  var pairedRows: [LocalGuidedPairedReviewRow] {
    guard let recheckRound else { return [] }
    return entries.indices.map { index in
      .init(
        entry: entries[index], initial: initialRound.rows[index],
        practice: practiceRows.first(where: { $0.entry.id == entries[index].id }),
        recheck: recheckRound.rows[index])
    }
  }

  /// Opening a visit is explicit and does not submit a check or record participation.
  mutating func beginReviewVisit(visitID: UUID) -> LocalGuidedReviewVisit? {
    guard let round = activeRound, !round.isFinished, activeReviewVisit == nil,
      reviewIndex < entries.count, !usedIDs.contains(visitID)
    else { return nil }
    let visit = LocalGuidedReviewVisit(
      workflowID: workflowID, roundID: round.id, visitID: visitID, entryID: entries[reviewIndex].id)
    usedIDs.insert(visitID)
    activeReviewVisit = visit
    replaceReviewRow(
      .init(
        entry: entries[reviewIndex], visit: visit, firstSubmission: nil, state: .ready))
    return visit
  }

  @discardableResult
  mutating func receive(_ event: LocalGuidedReviewEvent) -> Bool {
    guard let round = activeRound, let visit = activeReviewVisit else { return false }
    let row = round.rows[reviewIndex]
    switch event {
    case .submitted(let identity):
      guard identity.visit == visit, row.state == .ready, row.firstSubmission == nil,
        identity.operationID != identity.tryID,
        !usedIDs.contains(identity.operationID), !usedIDs.contains(identity.tryID)
      else { return false }
      usedIDs.formUnion([identity.operationID, identity.tryID])
      replaceReviewRow(
        .init(
          entry: row.entry, visit: visit, firstSubmission: identity, state: .pending))
    case .settled(let identity, let status, let eligible, let cleanup):
      guard identity.visit == visit, row.firstSubmission == identity, row.state == .pending
      else { return false }
      let state: LocalGuidedReviewRowState =
        cleanup
        ? .finished(eligible ? .init(status) : .cancelled) : .cleanupBlocked
      replaceReviewRow(
        .init(
          entry: row.entry, visit: visit, firstSubmission: identity, state: state))
    }
    return true
  }

  @discardableResult
  mutating func leaveReviewVisit(_ visit: LocalGuidedReviewVisit, cleanupConfirmed: Bool) -> Bool {
    guard cleanupConfirmed, visit == activeReviewVisit, let round = activeRound,
      case .finished = round.rows[reviewIndex].state
    else { return false }
    activeReviewVisit = nil
    reviewIndex += 1
    if reviewIndex == entries.count { finishCurrentRound() }
    return true
  }

  @discardableResult
  mutating func skipReviewVisit(_ visit: LocalGuidedReviewVisit, cleanupConfirmed: Bool) -> Bool {
    guard cleanupConfirmed, visit == activeReviewVisit, let round = activeRound,
      round.rows[reviewIndex].state == .ready
    else { return false }
    replaceReviewRow(
      .init(
        entry: entries[reviewIndex], visit: visit, firstSubmission: nil, state: .finished(.skipped))
    )
    return leaveReviewVisit(visit, cleanupConfirmed: true)
  }

  /// No pending or unknown-cleanup check can become an early terminal summary.
  @discardableResult
  mutating func finishReviewNow(
    roundID: UUID, visitID: UUID?, cleanupConfirmed: Bool
  ) -> Bool {
    guard cleanupConfirmed, let round = activeRound, round.id == roundID,
      activeReviewVisit?.visitID == visitID
    else { return false }
    var rows = round.rows
    if let visit = activeReviewVisit {
      let row = rows[reviewIndex]
      switch row.state {
      case .ready:
        rows[reviewIndex] = .init(
          entry: row.entry, visit: visit, firstSubmission: nil, state: .finished(.skipped))
      case .finished: break
      case .notVisited, .pending, .cleanupBlocked: return false
      }
    }
    for index in rows.indices where rows[index].state == .notVisited {
      rows[index] = .init(
        entry: rows[index].entry, visit: nil, firstSubmission: nil, state: .finished(.unreached))
    }
    setCurrentRound(.init(id: round.id, rows: rows, isFinished: true))
    activeReviewVisit = nil
    completeReviewStage()
    return true
  }

  /// Only the user's supplied 1–3 entries/order are selected; no result-based defaults.
  @discardableResult
  mutating func beginPractice(entryIDs: [String], practiceID: UUID) -> Bool {
    guard stage == .choosingPractice, (1...3).contains(entryIDs.count),
      Set(entryIDs).count == entryIDs.count, !usedIDs.contains(practiceID)
    else { return false }
    var selected: [PracticeLibraryEntry] = []
    for id in entryIDs {
      guard let entry = entries.first(where: { $0.id == id }) else { return false }
      selected.append(entry)
    }
    usedIDs.insert(practiceID)
    self.practiceID = practiceID
    practiceRows = selected.map {
      .init(entry: $0, visit: nil, freshTryID: nil, state: .notVisited)
    }
    practiceIndex = 0
    stage = .practice
    return true
  }

  mutating func beginPracticeVisit(visitID: UUID) -> LocalGuidedPracticeVisit? {
    guard stage == .practice, let practiceID, activePracticeVisit == nil,
      practiceIndex < practiceRows.count, !usedIDs.contains(visitID)
    else { return nil }
    let entry = practiceRows[practiceIndex].entry
    let visit = LocalGuidedPracticeVisit(
      workflowID: workflowID, practiceID: practiceID, visitID: visitID, entryID: entry.id)
    usedIDs.insert(visitID)
    activePracticeVisit = visit
    practiceRows[practiceIndex] = .init(entry: entry, visit: visit, freshTryID: nil, state: .ready)
    return visit
  }

  /// For finished/saveUnconfirmed, the owner must prove a valid new kept capture and
  /// completed cleanup. The ledger additionally rejects previously submitted take IDs.
  @discardableResult
  mutating func finishPracticeVisit(
    _ visit: LocalGuidedPracticeVisit, disposition: LocalGuidedPracticeDisposition,
    freshTryID: UUID?, cleanupConfirmed: Bool
  ) -> Bool {
    guard stage == .practice, cleanupConfirmed, visit == activePracticeVisit,
      practiceRows[practiceIndex].state == .ready
    else { return false }
    switch disposition {
    case .finished, .saveUnconfirmed:
      guard let freshTryID, !usedIDs.contains(freshTryID) else { return false }
      usedIDs.insert(freshTryID)
    case .skipped:
      guard freshTryID == nil else { return false }
    case .unreached: return false
    }
    practiceRows[practiceIndex] = .init(
      entry: practiceRows[practiceIndex].entry, visit: visit, freshTryID: freshTryID,
      state: .finished(disposition))
    return true
  }

  /// A retry may acknowledge the same active visit's completion UUID (its visit ID).
  /// A late save after leaving that visit cannot revise the participation observation.
  @discardableResult
  mutating func acknowledgePracticeSaved(
    _ visit: LocalGuidedPracticeVisit, completionID: UUID
  ) -> Bool {
    guard stage == .practice, visit == activePracticeVisit, completionID == visit.visitID,
      practiceRows[practiceIndex].state == .finished(.saveUnconfirmed)
    else { return false }
    let row = practiceRows[practiceIndex]
    practiceRows[practiceIndex] = .init(
      entry: row.entry, visit: visit, freshTryID: row.freshTryID, state: .finished(.finished))
    return true
  }

  @discardableResult
  mutating func leavePracticeVisit(
    _ visit: LocalGuidedPracticeVisit, cleanupConfirmed: Bool
  ) -> Bool {
    guard stage == .practice, cleanupConfirmed, visit == activePracticeVisit,
      case .finished = practiceRows[practiceIndex].state
    else { return false }
    activePracticeVisit = nil
    practiceIndex += 1
    if practiceIndex == practiceRows.count { stage = .readyToRecheck }
    return true
  }

  @discardableResult
  mutating func finishPracticeNow(
    practiceID: UUID, visitID: UUID?, cleanupConfirmed: Bool
  ) -> Bool {
    guard stage == .practice, self.practiceID == practiceID, cleanupConfirmed,
      activePracticeVisit?.visitID == visitID
    else { return false }
    for index in practiceRows.indices {
      let row = practiceRows[index]
      let disposition: LocalGuidedPracticeDisposition
      switch row.state {
      case .notVisited: disposition = .unreached
      case .ready: disposition = .skipped
      case .finished: continue
      }
      practiceRows[index] = .init(
        entry: row.entry, visit: row.visit, freshTryID: nil, state: .finished(disposition))
    }
    activePracticeVisit = nil
    stage = .readyToRecheck
    return true
  }

  @discardableResult
  mutating func beginRecheck(roundID: UUID) -> Bool {
    guard stage == .readyToRecheck, !usedIDs.contains(roundID) else { return false }
    usedIDs.insert(roundID)
    recheckRound = Self.emptyRound(id: roundID, entries: entries)
    reviewIndex = 0
    stage = .recheck
    return true
  }

  private static func emptyRound(id: UUID, entries: [PracticeLibraryEntry])
    -> LocalGuidedReviewRound
  {
    .init(
      id: id,
      rows: entries.map {
        .init(entry: $0, visit: nil, firstSubmission: nil, state: .notVisited)
      }, isFinished: false)
  }

  private mutating func replaceReviewRow(_ row: LocalGuidedReviewRow) {
    guard let round = activeRound else { return }
    var rows = round.rows
    rows[reviewIndex] = row
    setCurrentRound(.init(id: round.id, rows: rows, isFinished: false))
  }

  private mutating func setCurrentRound(_ round: LocalGuidedReviewRound) {
    switch stage {
    case .initialReview: initialRound = round
    case .recheck: recheckRound = round
    default: break
    }
  }

  private mutating func finishCurrentRound() {
    guard let round = activeRound else { return }
    setCurrentRound(.init(id: round.id, rows: round.rows, isFinished: true))
    completeReviewStage()
  }

  private mutating func completeReviewStage() {
    stage = stage == .initialReview ? .choosingPractice : .completed
  }
}
