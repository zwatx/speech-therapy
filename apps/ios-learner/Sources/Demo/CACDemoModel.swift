import Combine
import Foundation
import SwiftUI

// Congressional App Challenge proof of concept.
//
// Recording, replay and cleanup are real and local (DirectPracticeSession). Every
// "clear" / "needs practice" outcome is AUTHORED in `CACScript` and attached to a real
// stopped take only so the journey feels like the finished product. Nothing here measures
// pronunciation, runs speech recognition, aligns audio, scores, or diagnoses. Results live
// in memory only and are never written to practice history or research/clinical data.

enum CACScriptedOutcome: Equatable, Sendable {
  case clear
  case needsPractice
}

/// Where a result came from. There is deliberately one case: no measured source exists.
enum CACFeedbackSource: Equatable, Sendable {
  /// Fixed by `CACScript`. Never derived from audio, ASR or a model.
  case scripted
}

enum CACJourneyPart: Equatable, Sendable {
  case soundCheck, practice, recheck

  var title: String {
    switch self {
    case .soundCheck: "Sound check"
    case .practice: "Practice"
    case .recheck: "Check again"
    }
  }
}

/// One word of the journey: an exact canonical library entry plus its scripted outcome.
struct CACScriptedWord: Identifiable, Equatable, Sendable {
  let part: CACJourneyPart
  let entryID: String
  /// Single-prompt session of the entry's own sound and position.
  let sound: PracticeSound
  /// Learner-facing sound name, e.g. "R".
  let letter: String
  /// The written letters the script talks about. Illustrative only, never an aligned timing.
  let grapheme: String
  let outcome: CACScriptedOutcome

  var id: String { "\(part)-\(entryID)" }
  var prompt: PracticePrompt { sound.prompts[0] }
  var word: String { prompt.word }

  /// Authored copy for this word's outcome.
  var feedback: (title: String, detail: String) {
    let place = DirectPracticeListeningFocus.place(sound.position)
    switch (part, outcome) {
    case (.soundCheck, .clear):
      return ("You got the \(letter) sound.", "The \(letter) \(place) of “\(word)” sounded clear.")
    case (.soundCheck, .needsPractice):
      return (
        "The \(letter) sound needs practice.",
        "The \(letter) \(place) of “\(word)” is the part to work on. We’ll practice it next."
      )
    case (.practice, .clear):
      return ("Nice \(letter) sound.", "The \(letter) \(place) of “\(word)” sounded clear.")
    case (.recheck, .clear):
      return (
        "“\(word.capitalized)” sounds clear now.",
        "Your \(letter) \(place) of “\(word)” came through this time."
      )
    case (_, .needsPractice):
      return ("Keep practicing the \(letter) sound.", "Try “\(word)” again slowly.")
    }
  }

  /// Exact canonical entry of this sound and position whose written word begins with the
  /// configured grapheme. Anything else is rejected rather than approximated.
  static func make(
    _ part: CACJourneyPart, entry: PracticeLibraryEntry, outcome: CACScriptedOutcome
  ) -> CACScriptedWord? {
    let grapheme = entry.soundID
    guard entry.position == .beginning, entry.prompt.word.hasPrefix(grapheme),
      let sound = PracticeLibrary.session(
        soundID: entry.soundID, position: entry.position, startingAt: entry.id, limit: 1),
      sound.prompts == [entry.prompt]
    else { return nil }
    return CACScriptedWord(
      part: part, entryID: entry.id, sound: sound, letter: grapheme.uppercased(),
      grapheme: grapheme, outcome: outcome)
  }
}

/// A scripted outcome bound to one exact real take of one exact journey word.
struct CACScriptedResult: Equatable, Sendable {
  let source: CACFeedbackSource
  let wordID: String
  let entryID: String
  let takeID: UUID
  let outcome: CACScriptedOutcome
}

/// Follow-up chosen from the submitted sound-check results, not by the learner.
struct CACPracticePlan: Equatable, Sendable {
  let focus: CACScriptedWord
  let practice: [CACScriptedWord]
  let recheck: CACScriptedWord

  var letter: String { focus.letter }
}

enum CACScript {
  /// BOAT clear, RABBIT needs practice at the start, SUN clear.
  static let soundCheck: [CACScriptedWord] = {
    let script: [(soundID: String, word: String, outcome: CACScriptedOutcome)] = [
      ("b", "boat", .clear),
      ("r", "rabbit", .needsPractice),
      ("s", "sun", .clear),
    ]
    return script.compactMap { item in
      PracticeLibrary.entries(soundID: item.soundID, position: .beginning)
        .first(where: { $0.prompt.word == item.word })
        .flatMap { CACScriptedWord.make(.soundCheck, entry: $0, outcome: item.outcome) }
    }
  }()

  static let practiceWordCount = 2

  /// The first word marked needs-practice picks the sound. Practice uses other canonical
  /// words of that exact sound and position; the missed word is checked again last.
  static func plan(after results: [CACScriptedResult], in words: [CACScriptedWord])
    -> CACPracticePlan?
  {
    guard
      let missed = results.first(where: { $0.outcome == .needsPractice }),
      let focus = words.first(where: { $0.id == missed.wordID && $0.entryID == missed.entryID }),
      let recheck = PracticeLibrary.entries(
        soundID: focus.sound.id, position: focus.sound.position
      ).first(where: { $0.id == focus.entryID })
        .flatMap({ CACScriptedWord.make(.recheck, entry: $0, outcome: .clear) })
    else { return nil }
    let practice = PracticeLibrary.entries(soundID: focus.sound.id, position: focus.sound.position)
      .filter { $0.id != focus.entryID }
      .compactMap { CACScriptedWord.make(.practice, entry: $0, outcome: .clear) }
      .prefix(practiceWordCount)
    guard !practice.isEmpty else { return nil }
    return CACPracticePlan(focus: focus, practice: Array(practice), recheck: recheck)
  }
}

/// The prototype never runs a word or sound check. Injecting this keeps the bundled model unloaded.
@MainActor
final class CACDemoNoWordCheck: LocalWordRecognizing {
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    LocalWordRecognitionReceipt(request: request, status: .unavailable, cleanupConfirmed: true)
  }
  func cancel(operationID: UUID) {}
}

/// Owns at most one single-word media session at a time. A successor is created only after
/// the previous owner confirms full cleanup; only a true exit may leave process-held recovery.
@MainActor
final class CACDemoCoordinator: ObservableObject {
  enum Placement: Equatable {
    /// App root: exit returns to a fresh welcome.
    case root
    /// Legacy full-screen cover: exit sets `finished` so the presenter dismisses.
    case modal
  }

  /// `welcome`, `plan` and `recap` are states of the home; `word` is a session over it.
  enum Stage: Equatable {
    case welcome, word, plan, recap
  }

  enum Departure: Equatable {
    case start
    case advance(CACScriptedResult)
    case startPractice
    case practiceAgain
    case close
  }

  @Published private(set) var stage: Stage = .welcome
  @Published private(set) var current: CACScriptedWord?
  @Published private(set) var session: DirectPracticeSession?
  /// Unsubmitted result for `current`; see `currentResult` for the validated read.
  @Published private(set) var result: CACScriptedResult?
  @Published private(set) var submitted: [CACScriptedResult] = []
  @Published private(set) var plan: CACPracticePlan?
  /// When the current sound check started; results are dated by it.
  @Published private(set) var checkedAt: Date?
  @Published private(set) var isLeaving = false
  /// Retained after a refused end, so explicit recovery can finish the same departure.
  @Published private(set) var pendingDeparture: Departure?
  /// Modal placement only: set once every owned session has ended.
  @Published private(set) var finished = false
  /// Start was refused because an earlier recording is still held for process recovery.
  @Published private(set) var startBlocked = false

  let facePreview: FaceGuideModel
  private var previewWanted = true
  var facePreviewEnabled: Bool { previewWanted }
  var recordingControlsBlockedForCamera: Bool {
    facePreview.permissionPending || facePreview.cleanupBlocked || facePreview.transitionPending
  }
  var cameraRecoveryBlocked: Bool { facePreview.cleanupBlocked }
  var canShowFacePreview: Bool {
    guard let owner = activeOwner, scene == .active, !recordingControlsBlockedForCamera,
      owner.latestTry == nil, owner.canStartRecording
    else { return false }
    return true
  }
  private var faceSubscription: AnyCancellable?
  private var recordingIntent: RecordingIntent?
  private struct RecordingIntent {
    let id = UUID()
    let owner: DirectPracticeSession
    var resumeCameraAfterPermission = false
  }

  let placement: Placement
  let soundCheck: [CACScriptedWord]
  private let files: ProcessAudioFileOwnership
  private let makeSession: @MainActor (PracticeSound) -> DirectPracticeSession
  private var scene: ScenePhase = .active
  private var closeRequested = false

  init(
    placement: Placement = .root,
    soundCheck: [CACScriptedWord] = CACScript.soundCheck,
    files: ProcessAudioFileOwnership = .shared,
    facePreview: FaceGuideModel? = nil,
    makeSession: (@MainActor (PracticeSound) -> DirectPracticeSession)? = nil
  ) {
    self.placement = placement
    self.soundCheck = soundCheck
    self.files = files
    self.facePreview = facePreview ?? FaceGuideModel.standard()
    self.makeSession = makeSession ?? { CACDemoCoordinator.liveSession($0) }
    faceSubscription = self.facePreview.statePublisher.dropFirst().sink { [weak self] state in
      guard let self else { return }
      if state.phase == .interrupted || state.phase == .failed { recordingIntent = nil }
      objectWillChange.send()
    }
  }

  /// The app's coordinator. A compile-gated simulator build may substitute inert hardware.
  static func standard(placement: Placement) -> CACDemoCoordinator {
    #if CAC_FLOW_UI_VERIFICATION && targetEnvironment(simulator)
      if let verification = CACFlowVerification.requested() {
        return CACDemoCoordinator(
          placement: placement, files: verification.files, facePreview: verification.facePreview,
          makeSession: verification.makeSession)
      }
    #endif
    return CACDemoCoordinator(placement: placement)
  }

  /// Ordinary local capture and replay; no history store, so prototype rounds never count.
  static func liveSession(_ sound: PracticeSound) -> DirectPracticeSession {
    DirectPracticeSession(sound: sound, history: nil, wordRecognizer: CACDemoNoWordCheck())
  }

  /// The result is shown only while its exact take is still the session's latest kept take.
  var currentResult: CACScriptedResult? {
    guard let result, let word = current, result.wordID == word.id,
      result.entryID == word.entryID, let owner = session,
      case .review = owner.phase, owner.latestTry?.id == result.takeID
    else { return nil }
    return result
  }

  /// Quiet recordings can continue through this authored walkthrough. The shared capture
  /// assessment stays unchanged for other flows; empty audio and other retries still cannot.
  var currentRecordingCanBeChecked: Bool {
    guard let owner = session,
      case .review(let summary, let assessment) = owner.phase,
      let take = owner.latestTry, take.summary == summary, take.assessment == assessment,
      summary.duration.isFinite, summary.averagePower.isFinite,
      summary.pcm16Signal?.isAllZero != true
    else { return false }
    return assessment == .acceptable || assessment == .retry(CaptureQualityAssessor.quietCoaching)
  }

  /// 1-based position within the current part, and that part's length.
  var progress: (index: Int, count: Int)? {
    guard let current else { return nil }
    let partWords = words(in: current.part)
    guard let index = partWords.firstIndex(where: { $0.id == current.id }) else { return nil }
    return (index + 1, partWords.count)
  }

  func submittedResult(for word: CACScriptedWord) -> CACScriptedResult? {
    submitted.first(where: { $0.wordID == word.id })
  }

  // MARK: Actions

  /// Starts a fresh sound check from the home in any state; earlier results are replaced.
  func start() async {
    guard stage != .word, session == nil, !isLeaving, !finished, !soundCheck.isEmpty else {
      return
    }
    guard canOpenSession else { return }
    await depart(.start)
  }

  /// Every session opened from the home waits for camera recovery and for any file a
  /// true exit left for process recovery. Never open a successor over either.
  private var canOpenSession: Bool {
    guard !cameraRecoveryBlocked else { return false }
    guard files.pendingCleanupOwners.isEmpty, files.protectedURLs.isEmpty else {
      startBlocked = true
      return false
    }
    startBlocked = false
    return true
  }

  /// Attaches the scripted outcome to the exact latest eligible stopped take.
  /// A repeated check of the same take is frozen; only a new take can be checked again.
  func check() {
    guard stage == .word, !isLeaving, pendingDeparture == nil,
      !recordingControlsBlockedForCamera, let word = current,
      let owner = session, !owner.actionsDisabled,
      currentRecordingCanBeChecked, let take = owner.latestTry
    else { return }
    if let result, result.takeID == take.id, result.wordID == word.id { return }
    result = CACScriptedResult(
      source: .scripted, wordID: word.id, entryID: word.entryID, takeID: take.id,
      outcome: word.outcome)
  }

  func showFacePreview() {
    guard canShowFacePreview else { return }
    previewWanted = true
    objectWillChange.send()
    guard canShowFacePreview, previewWanted else { return }
    facePreview.sceneChanged(.active)
    facePreview.start()
  }

  func hideFacePreview() {
    previewWanted = false
    recordingIntent = nil
    _ = facePreview.stopForPracticeTransition()
    objectWillChange.send()
  }

  /// Recovery never starts the camera or a microphone; the next Show/Record is explicit.
  func retryFacePreviewCleanup() {
    guard pendingDeparture == nil, facePreview.cleanupBlocked else { return }
    _ = facePreview.retryStop()
  }

  func record() async {
    guard let owner = activeOwner, owner.canStartRecording,
      !recordingControlsBlockedForCamera, scene == .active
    else { return }
    await record(owner, replacing: false)
  }

  func recordAgain() async {
    guard let owner = activeOwner, owner.canRecordAnotherTry,
      !recordingControlsBlockedForCamera, scene == .active
    else { return }
    await record(owner, replacing: true)
  }

  private func record(_ owner: DirectPracticeSession, replacing: Bool) async {
    let intent = RecordingIntent(owner: owner)
    recordingIntent = intent
    // Record can restore an already-authorized preview, but can never open a camera prompt.
    if previewWanted, facePreview.cameraAuthorized, !facePreview.hasCameraOwner {
      facePreview.start()
    }
    guard recordingIntent?.id == intent.id, session === owner, !isLeaving,
      !recordingControlsBlockedForCamera, scene == .active
    else {
      if recordingIntent?.id == intent.id { recordingIntent = nil }
      return
    }
    result = nil
    guard recordingIntent?.id == intent.id, session === owner, !isLeaving else { return }
    if replacing { await owner.recordAnotherTry() } else { await owner.startRecording() }
    guard recordingIntent?.id == intent.id, session === owner else { return }
    if owner.phase != .recording {
      recordingIntent = nil
      return
    }
    resumeCameraForRecordingIfNeeded()
  }

  private func resumeCameraForRecordingIfNeeded() {
    guard let intent = recordingIntent, intent.resumeCameraAfterPermission,
      scene == .active, session === intent.owner, intent.owner.phase == .recording,
      stage == .word, !isLeaving, pendingDeparture == nil, previewWanted,
      facePreview.cameraAuthorized, !recordingControlsBlockedForCamera
    else { return }
    recordingIntent = nil
    facePreview.start()
  }

  /// Submits the shown result and moves on once the current owner has fully ended.
  func next() async {
    guard stage == .word, !facePreview.permissionPending, let result = currentResult else { return }
    await depart(.advance(result))
  }

  func startPractice() async {
    guard stage == .plan, plan != nil, session == nil, !isLeaving, canOpenSession else { return }
    await depart(.startPractice)
  }

  func practiceAgain() async {
    guard stage == .recap, plan != nil, session == nil, !isLeaving, canOpenSession else { return }
    await depart(.practiceAgain)
  }

  /// Exit, Close and Done.
  func close() async { await depart(.close) }

  /// The owner ended after an explicit recovery; finish the departure it was holding.
  func resumeAfterEnd() async {
    guard let pending = pendingDeparture, session?.phase == .ended else { return }
    await depart(pending)
  }

  /// Explicit recovery for a held departure. A retry never authorizes another Close:
  /// resume only when recovery actually ended the owner.
  func retryHeldDeparture() async {
    guard let pending = pendingDeparture, !isLeaving else { return }
    if facePreview.cleanupBlocked { _ = facePreview.retryStop() }
    if let owner = session, owner.canRetryCleanup { await owner.retryCleanup() }
    guard pendingDeparture == pending, !recordingControlsBlockedForCamera,
      session == nil || session?.hasFullyEndedCleanup == true
    else { return }
    await depart(pending, isRecovery: true)
  }

  // MARK: Lifecycle forwarding

  func forwardScene(_ phase: ScenePhase) {
    let cameraPermissionInactive = phase == .inactive && facePreview.permissionPending
    if phase == .background {
      recordingIntent = nil
    } else if phase == .inactive, !cameraPermissionInactive {
      if var intent = recordingIntent, intent.owner === session,
        intent.owner.phase == .requestingPermission
      {
        intent.resumeCameraAfterPermission = previewWanted && facePreview.cameraAuthorized
        recordingIntent = intent
      } else {
        recordingIntent = nil
      }
    }
    scene = phase
    switch phase {
    case .active: facePreview.sceneChanged(.active)
    case .inactive: facePreview.sceneChanged(.inactive)
    case .background: facePreview.sceneChanged(.background)
    @unknown default: facePreview.sceneChanged(.inactive)
    }
    if facePreview.cleanupBlocked, session?.phase == .requestingPermission {
      // A failed camera stop must not let the pending microphone grant start a recorder.
      recordingIntent = nil
      session?.audioWasInterrupted()
    }
    // The camera alert belongs to a fresh ready word; preserve that inert audio owner.
    guard !cameraPermissionInactive else { return }
    if phase != .active, session?.phase != .requestingPermission { result = nil }
    if let session {
      switch phase {
      case .active: session.appDidBecomeActive()
      case .inactive: session.appDidBecomeInactive()
      case .background: session.appDidEnterBackground()
      @unknown default: session.appDidBecomeInactive()
      }
    }
    if phase == .active { resumeCameraForRecordingIfNeeded() }
  }

  func audioWasInterrupted() {
    recordingIntent = nil
    result = nil
    _ = facePreview.stopForPracticeTransition()
    session?.audioWasInterrupted()
  }

  func viewDisappeared() {
    recordingIntent = nil
    _ = facePreview.stopForPracticeTransition()
    session?.viewDidDisappear()
  }

  // MARK: Ownership

  private var activeOwner: DirectPracticeSession? {
    guard stage == .word, !isLeaving, pendingDeparture == nil, !finished else { return nil }
    return session
  }

  private func words(in part: CACJourneyPart) -> [CACScriptedWord] {
    switch part {
    case .soundCheck: soundCheck
    case .practice: plan?.practice ?? []
    case .recheck: plan.map { [$0.recheck] } ?? []
    }
  }

  private func depart(_ departure: Departure, isRecovery: Bool = false) async {
    guard !finished else { return }
    recordingIntent = nil
    if departure == .close {
      closeRequested = true
      pendingDeparture = .close
      // Even a queued Close immediately revokes camera permission/start.
      _ = facePreview.stopForPracticeTransition()
    }
    guard !isLeaving else { return }
    let requested = closeRequested ? Departure.close : pendingDeparture ?? departure
    let alreadyPending = pendingDeparture != nil
    isLeaving = true
    defer { isLeaving = false }
    pendingDeparture = requested
    let keepCamera = !closeRequested && keepsCamera(for: requested)
    if !keepCamera { _ = facePreview.stopForPracticeTransition() }
    // Audio cleanup is always requested, including when camera teardown has failed.
    if let owner = session {
      let ended: Bool
      if alreadyPending && (requested != .close || isRecovery) {
        ended = owner.hasFullyEndedCleanup || (requested == .close && owner.phase == .ended)
      } else {
        ended = await owner.end()
      }
      guard ended, session === owner else { return }
      guard closeRequested || owner.hasFullyEndedCleanup else { return }
    }
    if closeRequested { _ = facePreview.stopForPracticeTransition() }
    guard !recordingControlsBlockedForCamera else { return }
    if !keepCamera || closeRequested { guard !facePreview.hasCameraOwner else { return } }
    let accepted = closeRequested ? Departure.close : pendingDeparture ?? requested
    session = nil
    pendingDeparture = nil
    closeRequested = false
    apply(accepted)
    // A synchronous preview subscriber may request Exit while the next word installs.
    isLeaving = false
    if closeRequested { await depart(.close) }
  }

  private func keepsCamera(for departure: Departure) -> Bool {
    guard case .advance = departure, let current else { return false }
    let partWords = words(in: current.part)
    if let index = partWords.firstIndex(where: { $0.id == current.id }), index + 1 < partWords.count
    {
      return true
    }
    return current.part == .practice && plan?.recheck != nil
  }

  private func apply(_ departure: Departure) {
    switch departure {
    case .start:
      submitted = []
      plan = nil
      checkedAt = .now
      if let first = soundCheck.first { install(first) }
    case .advance(let submittedResult):
      guard let word = current, submittedResult.wordID == word.id else { return }
      submitted.removeAll { $0.wordID == word.id }
      submitted.append(submittedResult)
      result = nil
      advance(after: word)
    case .startPractice, .practiceAgain:
      guard let first = plan?.practice.first else { return }
      // Practice again keeps the sound check; earlier practice results are replaced.
      submitted.removeAll { done in !soundCheck.contains(where: { $0.id == done.wordID }) }
      install(first)
    case .close:
      if placement == .modal {
        finished = true
      }
      // Leaving a practice session keeps the sound check and its plan on the home.
      let keepsPlan =
        placement == .root && stage == .word && plan != nil && current?.part != .soundCheck
      current = nil
      result = nil
      if keepsPlan {
        submitted.removeAll { done in !soundCheck.contains(where: { $0.id == done.wordID }) }
        stage = .plan
      } else {
        submitted = []
        plan = nil
        checkedAt = nil
        stage = .welcome
      }
    }
  }

  private func advance(after word: CACScriptedWord) {
    let partWords = words(in: word.part)
    if let index = partWords.firstIndex(where: { $0.id == word.id }), index + 1 < partWords.count {
      install(partWords[index + 1])
      return
    }
    current = nil
    switch word.part {
    case .soundCheck:
      plan = CACScript.plan(after: submitted, in: soundCheck)
      stage = plan == nil ? .recap : .plan
    case .practice:
      if let recheck = plan?.recheck { install(recheck) } else { stage = .recap }
    case .recheck:
      stage = .recap
    }
  }

  private func install(_ word: CACScriptedWord) {
    let owner = makeSession(word.sound)
    result = nil
    current = word
    session = owner
    stage = .word
    if scene == .active {
      owner.appDidBecomeActive()
      guard session === owner, !closeRequested, pendingDeparture == nil else { return }
      if previewWanted, !facePreview.hasCameraOwner, !recordingControlsBlockedForCamera {
        facePreview.sceneChanged(.active)
        facePreview.start()
      }
    }
  }
}
