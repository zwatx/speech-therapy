#if DEBUG && targetEnvironment(simulator)
  import Accessibility
  import AVFoundation
  import SwiftUI

  /// Guided 13-word whole-word recognition rounds. The coordinator drives the one feedback session;
  /// this view never constructs a second session or media owner.
  struct ResearchGuidedWordView: View {
    private let isGeneratedUITest: Bool
    @StateObject private var guided: ResearchGuidedWordSession

    init(guided: ResearchGuidedWordSession? = nil) {
      let fixture = ResearchGuidedWordUITestFixtures.selected()
      isGeneratedUITest = guided == nil && fixture != nil
      // Autoclosure: evaluated once for the view's lifetime. Generated fixtures get their own
      // isolated writer and never touch the shared history.
      _guided = StateObject(
        wrappedValue: guided
          ?? fixture.map {
            ResearchGuidedWordSession(
              feedbackSession: ResearchGuidedWordUITestFixtures.feedbackSession(for: $0),
              participationWriter: ResearchGuidedWordUITestFixtures.participationWriter(for: $0))
          }
          ?? ResearchGuidedWordSession(
            feedbackSession: ResearchFeedbackSession(),
            participationWriter: PracticeParticipationStore.shared))
    }

    var body: some View {
      GuidedContent(
        guided: guided, feedback: guided.feedbackSession, isGeneratedUITest: isGeneratedUITest)
    }
  }

  /// Observes both the coordinator and its own feedback session so nested media changes redraw.
  private struct GuidedContent: View {
    @ObservedObject var guided: ResearchGuidedWordSession
    @ObservedObject var feedback: ResearchFeedbackSession
    let isGeneratedUITest: Bool
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 64
    @AccessibilityFocusState private var statusFocused: Bool
    @AccessibilityFocusState private var recoveryFocused: Bool
    @State private var age: Int?
    @State private var showCounts = false
    @State private var confirmFinish = false
    @State private var closeAttempted = false
    @State private var closeFailed = false
    @State private var closeWaiter: UUID?
    @State private var closeRoute = CloseRoute()
    @State private var transitionWaiter: UUID?
    @State private var recoveryWaiter: UUID?
    @State private var recoveryFailed = false
    @State private var playbackTarget: PlaybackTarget?
    @State private var learnerStopped = false
    @State private var settledLayout = ActionLayout()

    private struct Status: Equatable {
      let title: String
      var detail: String? = nil
      var hint: String? = nil
    }

    /// Which control started the current playback. Every start here is a learner tap, so this
    /// names the stopping or blocked control after the session has revoked its own source.
    private enum PlaybackTarget: Equatable { case replay, example }

    private enum PlaybackControl { case idle, loading, preparing, playing, stopping, blocked }

    /// Guards that decide which buttons exist. Audio transitions briefly clear them; the last
    /// settled values keep those buttons in place, disabled, until playback has released.
    private struct ActionLayout: Equatable {
      var check = false
      var retrySave = false
    }

    /// One presentation's dismissal, shared with tasks that outlive this view value. Disappearing
    /// revokes it, so a late Close result never dismisses a later route, and it leaves only once.
    @MainActor private final class CloseRoute {
      private var active = true
      func revoke() { active = false }
      func leave(_ dismiss: DismissAction) {
        guard active else { return }
        active = false
        dismiss()
      }
    }

    private static let stoppingPlayback =
      "Stopping playback. Other actions return once it has stopped."

    var body: some View {
      ScrollViewReader { proxy in
        ScrollView {
          VStack(alignment: .leading, spacing: 24) {
            if isGeneratedUITest {
              Text(ResearchGuidedWordUITestFixtures.fixtureTag)
                .font(.footnote).fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier("guided-ui-test-fixture-note")
            }
            Text("Guided word check")
              .font(.system(.largeTitle, design: .serif))
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityAddTraits(.isHeader)
              .accessibilityIdentifier("guided-title")
              .id("guided-plan-top")
            PracticeRule()
            if let closeNote {
              Text(closeNote)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("guided-close-note")
            }
            if feedback.sharedProcessingPaused && guided.phase != .setup && guided.phase != .ended {
              Text(
                "Checks are paused. The service on this computer can't process recordings safely right now, and a temporary copy may remain there. Recording, replay and listening on this device still work."
              )
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("guided-paused")
            }
            if unifiedRecovery && !recoveryInStatus { blockedRecovery }
            switch guided.phase {
            case .setup: setup
            case .firstRound, .recheck: round
            case .practice: practice
            case .practicePlanChoice: practicePlanChoice
            case .practicePlanSummary: practicePlanSummary
            case .summary, .comparison: summaryScreen(interactive: true)
            case .ended: ended
            }
          }
          .padding(24)
          .frame(maxWidth: 560, alignment: .leading)
          .frame(maxWidth: .infinity)
        }
        .onChange(of: guided.phase) { old, new in
          if [.practicePlanChoice, .practicePlanSummary].contains(new)
            || old == .practicePlanChoice || old == .practicePlanSummary
          {
            proxy.scrollTo("guided-plan-top", anchor: .top)
          }
        }
        .onChange(of: guided.planPosition) { _, new in
          if new != nil { proxy.scrollTo("guided-plan-top", anchor: .top) }
        }
      }
      .background(DirectPracticeStyle.canvas.ignoresSafeArea())
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
      .toolbar(.hidden, for: .navigationBar)
      .interactiveDismissDisabled(closeHeld)
      .safeAreaInset(edge: .top, spacing: 0) { header }
      .alert("Finish round", isPresented: $confirmFinish) {
        Button("Finish round") { transition { _ = await guided.finishEarly() } }
        Button("Keep going", role: .cancel) {}
      } message: {
        Text("Words you haven't reached stay listed as not reached. Nothing is recorded or sent.")
      }
      .onAppear { settledLayout = liveLayout }
      .onDisappear {
        // Revoke the guided observer and every pending callback before this view is released.
        // The coordinator ends its one feedback session and owns the strong cleanup; this
        // view's later results can't dismiss.
        closeRoute.revoke()
        _ = guided.end()
      }
      .onChange(of: scenePhase) { _, phase in
        if phase == .active { feedback.appDidBecomeActive() }
        if phase == .background { feedback.appDidEnterBackground() }
        if phase == .inactive { feedback.appDidBecomeInactive() }
      }
      .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification))
      {
        notification in
        if let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
          AVAudioSession.InterruptionType(rawValue: raw) == .began
        {
          feedback.audioWasInterrupted()
        }
      }
      // onChange fires only when the title text changes, so each status is announced once.
      .onChange(of: status.title) { _, title in
        AccessibilityNotification.Announcement(
          feedback.phase == .cleanupBlocked && feedback.canRetryAudioCleanup
            ? "\(title). \(recoveryTitle) is available." : title
        ).post()
      }
      .onChange(of: guided.selectedPlanItems.count) { _, _ in
        if guided.phase == .practicePlanChoice {
          AccessibilityNotification.Announcement(planCountText).post()
        }
      }
      .onChange(of: feedback.playbackState) { _, state in announcePlayback(state) }
      .onChange(of: closeNote) { _, note in
        if let note { AccessibilityNotification.Announcement(note).post() }
      }
      .onChange(of: feedback.hasLocalMediaCleanupIssue) { _, blocked in
        recoveryFailed = false
        if blocked { recoveryFocused = true }
      }
      .onChange(of: guided.closeRequested) { _, requested in
        if !requested { closeAttempted = false }
      }
      .onChange(of: liveLayout) { _, live in
        if !audioHeld { settledLayout = live }
      }
      .onChange(of: audioHeld) { _, held in
        if !held { settledLayout = liveLayout }
      }
    }

    private var header: some View {
      VStack(spacing: 0) {
        HStack {
          Button("Close") { close() }
            .font(.body)
            .buttonStyle(.plain)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
            .accessibilityIdentifier("guided-close")
          Spacer()
        }
        .padding(.horizontal, 24)
        if isGeneratedUITest {
          Text("Generated test")
            .font(.footnote).fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24).padding(.bottom, 8)
            .accessibilityIdentifier("guided-ui-test-banner")
        }
        PracticeRule()
      }
      .background(DirectPracticeStyle.canvas)
    }

    // MARK: Close and recovery

    /// Playback, capture or a temporary file still needs cleanup, or a Close is waiting.
    private var closeHeld: Bool {
      feedback.audioTransitionPending || feedback.hasLocalMediaCleanupIssue
        || feedback.isPermissionPending || (guided.closeRequested && !guided.cleanupReleased)
    }

    /// The coordinator revokes itself and its one feedback session synchronously, before any
    /// wait, and owns that session's Close. Pending permission, preparation and stopping are
    /// waited out by the models; repeated taps join the coordinator's one Close task. A failed
    /// Close stays here until explicit recovery releases it.
    private func close() {
      closeAttempted = true
      closeFailed = false
      let cleanup = guided.end()
      guard closeWaiter == nil else { return }
      let token = UUID()
      closeWaiter = token
      let route = closeRoute
      Task { @MainActor in
        // A positive result has already settled the plan ledger and set cleanupReleased.
        _ = await cleanup.value
        if closeWaiter == token { closeWaiter = nil }
        if leaveAfterClose(route) { return }
        closeFailed = true
        if feedback.canRetryAudioCleanup { recoveryFocused = true }
      }
    }

    /// Leaves only after the learner's own Close, once the coordinator has released cleanup and
    /// settled its plan ledger. Neither session's logical end alone navigates.
    @discardableResult private func leaveAfterClose(_ route: CloseRoute) -> Bool {
      guard closeAttempted, guided.closeRequested, guided.cleanupReleased else { return false }
      route.leave(dismiss)
      return true
    }

    private var closeNote: String? {
      guard closeAttempted, guided.closeRequested, !guided.cleanupReleased else { return nil }
      if feedback.isPermissionPending {
        return
          "Waiting for the microphone permission answer. This screen closes once it's answered."
      }
      if feedback.playbackCleanupBlocked {
        return
          "Playback hasn't confirmed it stopped, so this screen stays open. Use Retry stopping."
      }
      if feedback.captureCleanupState.hasHardwareIssue {
        return
          "Recording hasn't confirmed it stopped, so this screen stays open. Use Retry stopping."
      }
      if feedback.hasLocalMediaCleanupIssue {
        return
          "A temporary file couldn't be removed, so this screen stays open. Use \(recoveryTitle). Until then it may remain on this device."
      }
      if feedback.audioTransitionPending || feedback.playbackState != .idle {
        return "Stopping playback before closing. This screen closes once it has stopped."
      }
      if closeWaiter != nil || guided.recoveryPending {
        return "Finishing current work before closing. This screen closes once it's done."
      }
      // Nothing here can be retried; say so rather than offering an action that can't help.
      return closeFailed ? "Closing couldn't be confirmed, so this screen stays open." : nil
    }

    /// Only a public example file failed and its practice section is showing its own retry.
    private var exampleOnlyCleanupIssue: Bool {
      feedback.exampleCleanupBlocked && feedback.phase != .cleanupBlocked
        && !feedback.playbackCleanupBlocked && feedback.captureCleanupState == .idle
        && guided.phase == .practice && feedback.example != nil
    }

    private var unifiedRecovery: Bool {
      feedback.hasLocalMediaCleanupIssue && !exampleOnlyCleanupIssue
    }

    /// Round and practice show the blocked status in place; other screens explain it above.
    private var recoveryInStatus: Bool {
      unifiedRecovery && feedback.phase == .cleanupBlocked
        && (guided.phase == .firstRound || guided.phase == .recheck
          || guided.phase == .practice && saveStatus == nil)
    }

    private var recoveryTitle: String {
      if exampleOnlyCleanupIssue { return "Retry example cleanup" }
      return feedback.playbackCleanupBlocked || feedback.captureCleanupState.hasHardwareIssue
        ? "Retry stopping" : "Retry cleanup"
    }

    private var recoveryNote: String? {
      if recoveryWaiter != nil {
        if feedback.playbackCleanupBlocked { return Self.stoppingPlayback }
        if feedback.captureCleanupState.hasHardwareIssue {
          return "Stopping recording. Other actions return once it has stopped."
        }
        return "Trying to remove it again…"
      }
      return recoveryFailed ? "Still not confirmed. You can try again." : nil
    }

    /// Held playback or capture hardware is never described as a file problem.
    private var cleanupStatus: Status {
      if feedback.playbackCleanupBlocked {
        return Status(
          title: "Playback hasn't confirmed it stopped",
          detail:
            "Recording, checks and other audio stay paused until it does. Your recordings and any results are unchanged."
        )
      }
      if feedback.captureCleanupState.hasHardwareIssue {
        return Status(
          title: "Recording hasn't confirmed it stopped",
          detail: "Recording, checks and other audio stay paused until it does.")
      }
      if feedback.exampleCleanupBlocked && feedback.phase != .cleanupBlocked
        && !feedback.captureCleanupState.hasFileIssue
      {
        return Status(
          title: "A temporary example couldn't be removed",
          detail:
            "Recording, replay and moving on wait until it's removed. Your recordings and results are unchanged."
        )
      }
      return Status(
        title: "A temporary recording couldn't be removed",
        detail:
          "Recording and checking are paused because removal could not be confirmed. Use Retry cleanup to try removing it again. Until then it may remain on this device."
      )
    }

    /// Explicit recovery through the coordinator, so a held Close settles its plan ledger and
    /// releases cleanup before this screen leaves. A repeated tap joins its one recovery task.
    private func retryCleanup() {
      let recovery = guided.retryAudioCleanup()
      recoveryFailed = false
      guard recoveryWaiter == nil else { return }
      let token = UUID()
      recoveryWaiter = token
      let route = closeRoute
      Task { @MainActor in
        let recovered = await recovery.value
        guard recoveryWaiter == token else { return }
        recoveryWaiter = nil
        if leaveAfterClose(route) {
          return
        } else if recovered && !feedback.hasLocalMediaCleanupIssue {
          statusFocused = true
        } else if feedback.hasLocalMediaCleanupIssue {
          recoveryFailed = true
          AccessibilityNotification.Announcement("Still not confirmed. You can try again.").post()
          recoveryFocused = true
        }
      }
    }

    private func recoveryControls(id: String) -> some View {
      VStack(alignment: .leading, spacing: 8) {
        secondary(recoveryTitle, id: id) { retryCleanup() }
          .disabled(!feedback.canRetryAudioCleanup || guided.recoveryPending)
          .accessibilityHint(
            feedback.playbackCleanupBlocked
              ? "Asks playback to stop again. Nothing plays."
              : feedback.captureCleanupState.hasHardwareIssue
                ? "Asks recording to stop again. Nothing is recorded."
                : "Tries removing the temporary file again. Nothing is recorded or sent."
          )
          .accessibilityFocused($recoveryFocused)
        if let note = recoveryNote {
          Text(note)
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-retry-audio-cleanup-note")
        }
      }
    }

    private var blockedRecovery: some View {
      let status = cleanupStatus
      return VStack(alignment: .leading, spacing: 12) {
        VStack(alignment: .leading, spacing: 4) {
          Text(status.title).font(.headline).accessibilityAddTraits(.isHeader)
          if let detail = status.detail { Text(detail) }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("guided-cleanup-status")
        recoveryControls(id: "guided-retry-audio-cleanup")
      }
    }

    // MARK: Transitions and playback

    private var transitionPending: Bool { transitionWaiter != nil }

    /// Runs one coordinator transition in a MainActor task. The coordinator owns its tokens and
    /// revalidation after cleanup; this only keeps its buttons disabled until it returns.
    private func transition(_ action: @escaping @MainActor () async -> Void) {
      let token = UUID()
      transitionWaiter = token
      Task { @MainActor in
        await action()
        if transitionWaiter == token { transitionWaiter = nil }
      }
    }

    /// Preparing, stopping or blocked audio, or cleanup that hasn't settled.
    private var audioHeld: Bool {
      feedback.audioTransitionPending || feedback.hasLocalMediaCleanupIssue
    }

    /// Startup capture cleanup failed with nothing retained, so this visit can't record again and
    /// there's nothing to retry. Retained playback, capture or files lead with their own recovery.
    private var recordingUnavailable: Bool {
      feedback.recordingUnavailable && !feedback.hasLocalMediaCleanupIssue
        && feedback.phase != .cleanupBlocked && feedback.phase != .ended
    }

    private var liveLayout: ActionLayout {
      ActionLayout(check: guided.canCheck, retrySave: guided.canRetryPracticeSave)
    }

    private var layout: ActionLayout { audioHeld ? settledLayout : liveLayout }

    private var playbackOwner: PlaybackTarget? {
      feedback.activeReplaySource != nil ? .replay : playbackTarget
    }

    /// Playing only after the session's own acknowledgement; otherwise the Cancel form stays.
    private func playbackControl(_ target: PlaybackTarget) -> PlaybackControl {
      let owned = playbackOwner == target
      switch feedback.playbackState {
      case .idle:
        return target == .example && feedback.exampleState == .loading ? .loading : .idle
      case .preparing:
        return owned ? .preparing : .idle
      case .playing:
        guard owned else { return .idle }
        let acknowledged =
          target == .replay
          ? feedback.playingReplaySource != nil : feedback.exampleState == .playing
        return acknowledged ? .playing : .preparing
      case .stopping:
        return owned ? .stopping : .idle
      case .cleanupBlocked:
        return owned ? .blocked : .idle
      }
    }

    /// Records the tapped control before the session acts; only a learner's stop is announced.
    private func notePlaybackTap(_ target: PlaybackTarget) {
      switch playbackControl(target) {
      case .preparing, .playing: learnerStopped = true
      case .loading: learnerStopped = false
      case .idle:
        playbackTarget = target
        learnerStopped = false
      case .stopping, .blocked: break
      }
    }

    private func announcePlayback(_ state: PracticePlaybackRuntimeState) {
      switch state {
      case .playing:
        if feedback.playingReplaySource != nil {
          AccessibilityNotification.Announcement("Playing.").post()
        }
      case .stopping:
        if learnerStopped { AccessibilityNotification.Announcement("Stopping playback.").post() }
      case .idle:
        if learnerStopped { AccessibilityNotification.Announcement("Playback stopped.").post() }
        learnerStopped = false
      case .cleanupBlocked:
        learnerStopped = false
      case .preparing:
        break
      }
    }

    /// One shared line while playback starts or stops; blocked playback leads the status above.
    private func playbackStatus(_ target: PlaybackTarget) -> String? {
      switch playbackControl(target) {
      case .preparing: target == .example ? "Starting example…" : "Starting playback…"
      case .stopping:
        transitionPending ? "Stopping playback before moving on." : Self.stoppingPlayback
      case .idle, .loading, .playing, .blocked: nil
      }
    }

    // MARK: Setup

    private var setup: some View {
      VStack(alignment: .leading, spacing: 16) {
        Text(
          "Record each of 13 words. A word is checked only when you tap Check, which sends that recording to one local service at 127.0.0.1:8793 for whole-word recognition. Results are recognizer observations, not a pronunciation score or diagnosis."
        )
        .fixedSize(horizontal: false, vertical: true)
        let layout =
          dynamicTypeSize.isAccessibilitySize
          ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8)) : AnyLayout(HStackLayout())
        layout {
          Text("Child's age").accessibilityHidden(true)
          if !dynamicTypeSize.isAccessibilitySize { Spacer(minLength: 12) }
          Menu {
            ForEach(6...12, id: \.self) { value in
              Button("\(value) years") { age = value }
            }
          } label: {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
              Text(age.map { "\($0) years" } ?? "Not set")
                .fixedSize(horizontal: false, vertical: true)
              Image(systemName: "chevron.up.chevron.down").imageScale(.small)
                .accessibilityHidden(true)
            }
            .font(.body)
            .frame(minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
          }
          .menuOrder(.fixed)
          .accessibilityLabel("Child's age")
          .accessibilityValue(age.map { "\($0) years" } ?? "Not set")
          .accessibilityIdentifier("guided-age-picker")
        }
        .frame(minHeight: 44)
        Button {
          guided.localProcessingEnabled.toggle()
        } label: {
          HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: guided.localProcessingEnabled ? "checkmark.square" : "square")
              .accessibilityHidden(true)
            Text("Allow word checks on this computer").fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
          }
          .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(guided.localProcessingEnabled ? "On" : "Off")
        .accessibilityIdentifier("guided-check-optin")
        Text(
          "Age is self-declared and isn't verified. Age and the check option can't be changed during the rounds. The model's accuracy for children hasn't been established. Free practice in Recording feedback is unchanged."
        )
        .font(.footnote)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        if let error = guided.lastError {
          Text(error).fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-error")
        }
        Button("Start first round") {
          if let age { transition { _ = await guided.start(age: age) } }
        }
        .buttonStyle(DirectPracticeButtonStyle())
        .disabled(age == nil || !guided.localProcessingEnabled || transitionPending)
        .accessibilityIdentifier("guided-start")
      }
    }

    private var contextLine: some View {
      Text(
        "\(guided.childContext.map(Self.label(for:)) ?? "") · Word checks on this computer"
      )
      .font(.subheadline)
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityIdentifier("guided-context")
    }

    private static func label(for context: ResearchPracticeContext) -> String {
      switch context {
      case .adult: "Adult (18+)"
      case .child(let age): "Child, age \(age)"
      }
    }

    // MARK: Round

    private var currentRow: ResearchGuidedWordRow? {
      guard let id = guided.currentItem?.id else { return nil }
      return guided.rows.first { $0.id == id }
    }

    private var currentIndex: Int? {
      guard let id = guided.currentItem?.id else { return nil }
      return guided.rows.firstIndex { $0.id == id }
    }

    private var primarySubmitted: Bool { currentRow?.primaryAttemptId != nil }

    private var round: some View {
      VStack(alignment: .leading, spacing: 20) {
        Text(guided.phase == .recheck ? "Recheck" : "First round")
          .font(.system(.title2, design: .serif))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-round-title")
        contextLine
        if let index = currentIndex {
          Text("Word \(index + 1) of \(guided.rows.count)")
            .font(.subheadline)
            .accessibilityIdentifier("guided-item-position")
        }
        word
        statusView
        roundActions
      }
    }

    private var word: some View {
      Text(guided.currentItem?.word ?? "")
        .font(.system(size: wordSize, design: .serif))
        .minimumScaleFactor(0.4).lineLimit(1)
        .accessibilityIdentifier("guided-word")
    }

    private var roundActions: some View {
      VStack(alignment: .leading, spacing: 12) {
        if recoveryInStatus { recoveryControls(id: "guided-retry-audio-cleanup") }
        if !primarySubmitted { recordControls }
        if feedback.phase == .review && !primarySubmitted && layout.check {
          Button("Check") { guided.check() }
            .buttonStyle(DirectPracticeButtonStyle())
            .disabled(!guided.canCheck)
            .accessibilityIdentifier("guided-check")
        }
        checking
        replay
        if !primarySubmitted { retake }
        settings
        if primarySubmitted {
          let last = (currentIndex ?? 0) + 1 == guided.rows.count
          Button(last ? "Show summary" : "Next word") { transition { _ = await guided.next() } }
            .buttonStyle(DirectPracticeButtonStyle())
            .disabled(!guided.canNext || transitionPending)
            .accessibilityHint(
              guided.canNext && !transitionPending
                ? ""
                : audioHeld || transitionPending
                  ? "Available once playback has stopped." : "Available when this check finishes."
            )
            .accessibilityIdentifier("guided-next")
        }
        if currentRow?.disposition == .notReached && !primarySubmitted {
          secondary("Skip this word", id: "guided-skip") { transition { _ = await guided.skip() } }
            .disabled(!guided.canSkip || transitionPending)
        }
        secondary("Finish round early", id: "guided-finish-early") { confirmFinish = true }
          .disabled(!guided.canTransition || transitionPending)
      }
    }

    @ViewBuilder private var recordControls: some View {
      switch feedback.phase {
      case .ready, .permissionDenied:
        // When recording is unavailable, the status explains Close instead of a dead Record.
        if !recordingUnavailable {
          Button("Record") { Task { await guided.record() } }
            .buttonStyle(DirectPracticeButtonStyle())
            .disabled(!guided.canRecord)
            .accessibilityIdentifier("guided-record")
        }
      case .requestingPermission:
        ProgressView()
          .frame(maxWidth: .infinity, minHeight: 44)
          .accessibilityLabel("Waiting for microphone permission")
      case .recording:
        Button("Stop") { guided.stop() }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("guided-stop")
      default:
        EmptyView()
      }
    }

    @ViewBuilder private var checking: some View {
      if feedback.phase == .checking {
        ProgressView()
          .frame(maxWidth: .infinity, minHeight: 44)
          .accessibilityLabel("Checking the word")
        // The coordinator has no cancel member; the owning feedback session cancels and reports it.
        Button("Cancel check") { feedback.cancelChecking() }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .disabled(feedback.audioTransitionPending)
          .accessibilityIdentifier("guided-cancel-check")
      }
    }

    private func replayTitle(_ control: PlaybackControl) -> String {
      switch control {
      case .loading, .preparing: "Cancel replay"
      case .playing: "Stop replay"
      case .stopping: "Stopping…"
      case .idle, .blocked: "Replay this try"
      }
    }

    @ViewBuilder private var replay: some View {
      let control = playbackControl(.replay)
      // Replay stays in place, disabled, while any playback is starting, playing or stopping.
      let audioBusy =
        feedback.audioTransitionPending
        || (feedback.playbackState != .idle && !feedback.playbackCleanupBlocked)
      if feedback.latestReplay != nil, control != .blocked, feedback.canReplay || audioBusy {
        secondary(replayTitle(control), id: "guided-replay") {
          notePlaybackTap(.replay)
          Task { @MainActor in await feedback.togglePlayback() }
        }
        .disabled(control == .stopping || !feedback.canReplay)
      }
      if let line = playbackStatus(.replay) {
        Text(line)
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("guided-playback-status")
      }
      if feedback.playbackFailed {
        Text(
          recordingUnavailable
            ? "Replay didn't work." : "Replay didn't work. You can record again."
        )
        .font(.subheadline)
        .fixedSize(horizontal: false, vertical: true)
      }
    }

    @ViewBuilder private var retake: some View {
      switch feedback.phase {
      case .review, .failed:
        if !recordingUnavailable {
          secondary("Retake", id: "guided-retake") { guided.retake() }
            .disabled(feedback.isProcessing || audioHeld)
        }
      default:
        EmptyView()
      }
    }

    @ViewBuilder private var settings: some View {
      if feedback.phase == .permissionDenied && !recordingUnavailable {
        secondary("Open Settings", id: "guided-settings") {
          if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
          }
        }
      }
    }

    // MARK: Status

    private var statusView: some View {
      let status = status
      return VStack(alignment: .leading, spacing: 8) {
        Text(status.title)
          .font(.title2.weight(.medium))
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityAddTraits(.isHeader)
          .accessibilityHint(status.hint ?? "")
          .accessibilityIdentifier("guided-status-title")
          .accessibilityFocused($statusFocused)
        if let detail = status.detail {
          Text(detail)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-status-detail")
        }
        if let hint = status.hint {
          Text(hint)
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
        }
      }
    }

    private var quotedWord: String { "“\(guided.currentItem?.word ?? "")”" }

    private var status: Status {
      let practicing = guided.phase == .practice
      if practicing, let save = saveStatus { return save }
      if recordingUnavailable, practicing || !primarySubmitted {
        switch feedback.phase {
        case .ready, .failed, .permissionDenied:
          return Status(
            title: "Recording isn't available",
            detail: feedback.audioCleanupMessage ?? "Recording is unavailable for this visit.")
        default: break
        }
      }
      switch feedback.phase {
      case .ready:
        if !practicing, let row = currentRow, row.primaryAttemptId != nil {
          return Status(
            title: Self.text(for: row.disposition),
            detail:
              "This word's check didn't finish, so it stays listed as check unavailable. Tap Next when you're ready."
          )
        }
        if guided.attempts.count >= ResearchGuidedWordSession.attemptLimit {
          return Status(
            title: "Recording limit reached", detail: "Finish the round to see the summary.")
        }
        return practicing
          ? Status(
            title: "Ready to practice",
            detail: "Record, replay or listen. Practice recordings aren't checked or sent.")
          : Status(
            title: "Ready to record",
            detail: "Tap Record and say \(quotedWord). Nothing is sent until you tap Check.")
      case .requestingPermission:
        return Status(title: "Getting the microphone ready…")
      case .recording:
        return Status(
          title: "Recording",
          detail: "Say \(quotedWord), then tap Stop. Recording stops on its own after 4 seconds.")
      case .review:
        if practicing {
          return Status(title: "Recording ready", detail: "Replay it or record again.")
        }
        if layout.check {
          return Status(
            title: "Recording ready",
            detail: "Replay it, retake it, or tap Check to send it for a whole-word check.")
        }
        return Status(
          title: "Recording ready",
          detail: feedback.sharedProcessingPaused
            ? "Checks are paused. You can replay it, retake it or skip this word."
            : "This recording can't be checked. You can replay it, retake it or skip this word.")
      case .checking:
        return Status(
          title: "Checking the word on this computer…", detail: "You can cancel the check.")
      case .feedback(let value):
        if !practicing, let row = currentRow, row.primaryAttemptId != nil {
          guard let observation = row.observation else {
            return Status(
              title: "Check unavailable",
              detail:
                "This check could not be verified for the round. Its first submitted outcome stays unchanged."
            )
          }
          return result(observation)
        }
        return result(value)
      case .permissionDenied:
        return Status(
          title: "Microphone access is off",
          detail: practicing
            ? "Allow microphone access in Settings, then record again."
            : "Allow microphone access in Settings, then record again, or skip this word.")
      case .failed(let error):
        if !practicing && primarySubmitted {
          return Status(
            title: "Check unavailable",
            detail: error == .invalidResponse
              ? "The service reply couldn't be verified, so no result is shown."
              : "The check couldn't finish. This word stays listed as check unavailable.")
        }
        return Status(title: "This recording couldn't be used", detail: "Retake to record again.")
      case .cleanupBlocked:
        return cleanupStatus
      case .ended:
        return Status(title: "Guided check ended")
      }
    }

    private func result(_ value: RecordingFeedback) -> Status {
      let limit = "Whole-word recognition only; it doesn't judge how the sounds were made."
      switch value.reason {
      case "silence":
        return Status(title: "The recording was very quiet", detail: "It was too quiet to check.")
      case "clipping":
        return Status(
          title: "The recording reached its numeric limit",
          detail: "It wasn't checked further. That alone doesn't show the sound was distorted.")
      case "invalid_audio":
        return Status(
          title: "This recording couldn't be checked", detail: "The service couldn't use it.")
      default: break
      }
      switch value.word {
      case .modelMatched:
        return Status(title: "Recognizer matched this word", hint: limit)
      case .modelNotMatched:
        return Status(title: "Recognizer did not match this word", hint: limit)
      case .uncertain:
        return Status(
          title: "Recognition was uncertain",
          detail: "The recognizer couldn't settle on one result.", hint: limit)
      case .notSingleWord:
        return Status(
          title: "Not a single supported word", detail: "Checking needs \(quotedWord) on its own.")
      case .notRun, .unavailable:
        break
      }
      if value.speech == .modelNotDetected {
        return Status(
          title: "Model did not detect speech",
          hint: "A detector observation, not a statement about the child's speech.")
      }
      if value.reason == "cleanup_unconfirmed" {
        return Status(
          title: "Check unavailable",
          detail:
            "The service couldn't confirm removing its temporary copy, so it may remain on this computer."
        )
      }
      return Status(
        title: "Check unavailable", detail: "The local service couldn't complete this check.")
    }

    private static func text(for disposition: ResearchGuidedWordDisposition) -> String {
      switch disposition {
      case .modelMatched: "Recognizer matched this word"
      case .modelNotMatched: "Recognizer did not match this word"
      case .recognitionUncertain: "Recognition uncertain"
      case .notSingleSupportedWord: "Not a single supported word"
      case .speechNotDetected: "Model did not detect speech"
      case .recordingIssue: "Recording issue"
      case .checkUnavailable: "Check unavailable"
      case .skipped: "Skipped"
      case .notReached: "Not reached"
      }
    }

    // MARK: Practice

    private var planCountText: String {
      let count = guided.selectedPlanItems.count
      return count == 3
        ? "3 of 3 chosen. Remove one to choose another." : "\(count) of 3 chosen"
    }

    private var planSuggestionText: String {
      let words = guided.suggestedPracticeItems.map(\.word)
      if words.count == 1, let word = words.first {
        return
          "The word check did not match this word: \(word). You can choose it, choose others, or skip practice and recheck."
      }
      if !words.isEmpty {
        return
          "The word check did not match these words: \(words.formatted(.list(type: .and))). You can choose them, choose others, or skip practice and recheck."
      }
      if let summary = guided.firstSummary,
        summary.rows.allSatisfy({ $0.disposition == .modelMatched })
      {
        return
          "The word check matched every word. There are no suggestions. You can still choose any word to practice."
      }
      return
        "No word has a not-matched result to suggest. Words without a result aren't suggested. You can still choose any word."
    }

    private var practicePlanIntroduction: some View {
      VStack(alignment: .leading, spacing: 12) {
        Text("Practice plan").font(.headline).accessibilityAddTraits(.isHeader)
        Text(
          "Choose 1 to 3 words to practice one after another. You choose the words; nothing is picked for you."
        )
        .fixedSize(horizontal: false, vertical: true)
        Text(planSuggestionText).fixedSize(horizontal: false, vertical: true)
        if guided.firstSummary?.rows.contains(where: { $0.disposition == .recordingIssue }) == true
        {
          Text(
            "Some recordings couldn't be checked. The word list explains the recording issue separately; those words aren't suggested because of it."
          )
          .fixedSize(horizontal: false, vertical: true)
        }
        Button("Choose words to practice") { transition { _ = await guided.openPracticePlan() } }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(!guided.canTransition || transitionPending)
          .accessibilityHint("Opens a list of all 13 words. Nothing is recorded.")
          .accessibilityIdentifier("guided-plan-open")
      }
    }

    private var practicePlanChoice: some View {
      VStack(alignment: .leading, spacing: 16) {
        Text("Choose words to practice")
          .font(.system(.title2, design: .serif)).accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-plan-choice-title")
        contextLine
        Text(
          "Pick up to 3. Practice recordings aren't checked or sent, and practice doesn't change the first-round results."
        )
        .fixedSize(horizontal: false, vertical: true)
        Text(planCountText).font(.subheadline).fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("guided-plan-count")
        Text(planSuggestionText).fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("guided-plan-suggestions")
        if !guided.practicePlanRows.isEmpty {
          Text(
            "Starting this sequence replaces the previous plan results on this screen. It does not save earlier visits again."
          )
          .font(.footnote).fixedSize(horizontal: false, vertical: true)
        }
        if let summary = guided.firstSummary {
          ForEach(summary.rows) { row in
            PracticeRule()
            practicePlanChoiceRow(row)
          }
        }
        PracticeRule()
        Button(
          guided.selectedPlanItems.isEmpty
            ? "Start practice"
            : "Start practice (\(guided.selectedPlanItems.count) \(guided.selectedPlanItems.count == 1 ? "word" : "words"))"
        ) { transition { _ = await guided.beginPracticePlan() } }
        .buttonStyle(DirectPracticeButtonStyle())
        .disabled(!guided.canBeginPlan || transitionPending)
        .accessibilityHint(
          guided.selectedPlanItems.first.map {
            "Starts with \($0.word). Nothing is recorded until you tap Record."
          } ?? "Choose at least 1 word first."
        )
        .accessibilityIdentifier("guided-plan-start")
        secondary(
          "Cancel choices",
          id: "guided-plan-cancel"
        ) { transition { _ = await guided.cancelPracticePlanChoice() } }
        .disabled(!guided.canTransition || transitionPending)
        Text("Your choices are kept only until you close this check.")
          .font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
      }
    }

    private func practicePlanChoiceRow(_ row: ResearchGuidedWordRow) -> some View {
      let chosen = guided.selectedPlanItems.contains(where: { $0.id == row.id })
      let suggested = guided.suggestedPracticeItems.contains(where: { $0.id == row.id })
      let full = !chosen && guided.selectedPlanItems.count >= 3
      let help = planHelp(row)
      return Toggle(
        isOn: Binding(
          get: { guided.selectedPlanItems.contains(where: { $0.id == row.id }) },
          set: { selected in
            let currentlySelected = guided.selectedPlanItems.contains(where: { $0.id == row.id })
            if selected != currentlySelected { guided.togglePracticePlanItem(row.id) }
          })
      ) {
        HStack(alignment: .top, spacing: 12) {
          Image(systemName: chosen ? "checkmark.square" : "square")
            .accessibilityHidden(true).foregroundStyle(
              full ? DirectPracticeStyle.muted : DirectPracticeStyle.ink)
          VStack(alignment: .leading, spacing: 4) {
            Text(row.word + (suggested ? " · Suggested" : "")).font(.headline)
            Text(help).font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
          }
          .fixedSize(horizontal: false, vertical: true)
          Spacer(minLength: 0)
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
      }
      .toggleStyle(.button).buttonStyle(.plain)
      .disabled(full || !guided.canTransition || transitionPending)
      .accessibilityLabel("\(row.word). \(suggested ? "Suggested. " : "")\(help)")
      .accessibilityValue(chosen ? "Chosen" : "Not chosen")
      .accessibilityHint(
        chosen
          ? "Removes this word from the practice plan."
          : full
            ? "Plan is full. Remove a word to choose this one."
            : "Adds this word to the practice plan."
      )
      .accessibilityIdentifier("guided-plan-row-\(row.id)")
    }

    private func planHelp(_ row: ResearchGuidedWordRow) -> String {
      switch row.disposition {
      case .modelNotMatched: return "The word check did not match this word."
      case .modelMatched: return "The word check matched this word. You can still choose it."
      case .recognitionUncertain:
        return "The check was uncertain, so there's no matched or not-matched result."
      case .notSingleSupportedWord:
        return "The check needed the word on its own, so there's no result."
      case .speechNotDetected: return "The model didn't detect speech, so there's no word result."
      case .recordingIssue:
        switch row.reason {
        case "silence":
          return
            "The recording was too quiet to check. Try a quiet place and a normal distance from the microphone. This is about the recording, not the word."
        case "clipping":
          return
            "The recording reached its numeric limit and wasn't checked. Try a little farther from the microphone. This is about the recording, not the word."
        default: return "The service couldn't use this recording, so there's no word result."
        }
      case .checkUnavailable: return "The check didn't finish, so there's no word result."
      case .skipped: return "Skipped in the first round, so there's no result."
      case .notReached: return "Not reached in the first round, so there's no result."
      }
    }

    @ViewBuilder private var practicePlanStepControls: some View {
      if let visit = guided.practiceVisit {
        switch visit.completionState {
        case .active:
          secondary("Skip this word", id: "guided-plan-skip") {
            transition { _ = await guided.skipPracticePlanItem() }
          }
          .disabled(!guided.canSkipPlan || transitionPending)
          .accessibilityHint("Moves on without saving practice for this word.")
        case .saved:
          Button(planNextTitle) { transition { _ = await guided.nextPracticePlanItem() } }
            .buttonStyle(DirectPracticeButtonStyle())
            .disabled(!guided.canNextPlan || transitionPending)
            .accessibilityHint("Continues the plan. Nothing is recorded.")
            .accessibilityIdentifier("guided-plan-next")
        case .completedNotSaved:
          Text(
            layout.retrySave
              ? "Saving could not be confirmed. You can retry above or continue with this visit listed as finished, save unconfirmed."
              : "Saving cannot be retried right now. This visit stays listed as finished, save unconfirmed if you continue."
          )
          .font(.footnote).fixedSize(horizontal: false, vertical: true)
          secondary("Continue without saving again", id: "guided-plan-next-unsaved") {
            transition { _ = await guided.nextPracticePlanItem(leaveWithoutSaving: true) }
          }
          .disabled(!guided.canTransition || transitionPending)
        }
      }
    }

    private var planNextTitle: String {
      guided.planPosition == guided.practicePlanRows.count ? "See plan results" : "Next word"
    }

    private var practicePlanLeavingControls: some View {
      let saveUnconfirmed: Bool = {
        if case .completedNotSaved = guided.practiceVisit?.completionState { return true }
        return false
      }()
      return VStack(alignment: .leading, spacing: 12) {
        Text("Editing leaves this visit. Confirming your choices starts a new sequence.")
          .font(.footnote).fixedSize(horizontal: false, vertical: true)
        secondary(
          saveUnconfirmed ? "Edit plan without saving again" : "Edit plan", id: "guided-plan-edit"
        ) { transition { _ = await guided.editPracticePlan(leaveWithoutSaving: saveUnconfirmed) } }
        .disabled(!guided.canTransition || transitionPending)
        secondary(
          saveUnconfirmed ? "End plan without saving again" : "End plan", id: "guided-plan-end"
        ) { transition { _ = await guided.endPracticePlan(leaveWithoutSaving: saveUnconfirmed) } }
        .disabled(!guided.canTransition || transitionPending)
      }
    }

    private var practicePlanSummary: some View {
      let finished = guided.practicePlanRows.filter { row in
        switch row.disposition {
        case .finishedSaved, .finishedNotSaved: true
        default: false
        }
      }.count
      return VStack(alignment: .leading, spacing: 16) {
        Text("Practice plan results").font(.system(.title2, design: .serif))
          .accessibilityAddTraits(.isHeader).accessibilityIdentifier("guided-plan-results-title")
        Text("Finished \(finished) of \(guided.practicePlanRows.count) words.")
          .fixedSize(horizontal: false, vertical: true)
        Text(
          "Finished means you tapped Finish practice after a new recording. It shows practice happened, not how the word was said."
        )
        .font(.footnote).fixedSize(horizontal: false, vertical: true)
        ForEach(guided.practicePlanRows) { row in
          PracticeRule()
          let result = planResultText(row)
          Text("\(row.item.word) · \(result)")
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(row.item.word), \(result)")
            .accessibilityIdentifier("guided-plan-result-\(row.id)")
          if case .finishedNotSaved = row.disposition {
            Text(
              "Saving to Recent practice could not be confirmed. This screen records the explicit finish; it does not save it again."
            )
            .font(.footnote).fixedSize(horizontal: false, vertical: true)
          }
        }
        startRecheck
        secondary("Choose another plan", id: "guided-plan-another") {
          transition { _ = await guided.openPracticePlan() }
        }
        .disabled(!guided.canTransition || transitionPending)
        secondary("Back to summary", id: "guided-plan-back-summary") {
          transition { _ = await guided.returnSummary() }
        }
        .disabled(!guided.canTransition || transitionPending)
      }
    }

    private func planResultText(_ row: ResearchGuidedPracticePlanRow) -> String {
      switch row.disposition {
      case .pending: "Not started"
      case .finishedSaved: "Finished and saved"
      case .finishedNotSaved: "Finished, save unconfirmed"
      case .skipped: "Skipped"
      case .leftUnsaved: "Left without finishing"
      }
    }

    private var practice: some View {
      VStack(alignment: .leading, spacing: 20) {
        Text(guided.planPosition != nil ? "Practice plan" : "Practice")
          .font(.system(.title2, design: .serif))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-practice-title")
        if let position = guided.planPosition {
          Text("Word \(position) of \(guided.practicePlanRows.count)")
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-plan-position")
        }
        word
        if let save = saveStatus {
          savedView(save)
        } else {
          statusView
          VStack(alignment: .leading, spacing: 12) {
            if recoveryInStatus { recoveryControls(id: "guided-retry-audio-cleanup") }
            recordControls
            replay
            retake
            settings
          }
        }
        if feedback.example != nil || listeningCue != nil { listening(feedback.example) }
        finishControls
        if guided.planPosition != nil { practicePlanStepControls }
        PracticeRule()
        VStack(alignment: .leading, spacing: 12) {
          if guided.practiceVisit?.completionState != .saved {
            Text(
              guided.planPosition != nil
                ? "Editing or ending the plan, or starting the recheck, leaves this visit without saving again."
                : "Going back or starting the recheck leaves this practice unsaved."
            )
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-leave-unsaved")
          }
          if guided.planPosition != nil {
            practicePlanLeavingControls
          } else {
            secondary("Back to summary", id: "guided-back-summary") {
              transition { _ = await guided.returnSummary() }
            }
            .disabled(!guided.canTransition || transitionPending)
          }
          startRecheck
        }
      }
    }

    /// Non-nil once this visit's practice was explicitly finished; replaces the record controls.
    private var saveStatus: Status? {
      guard let visit = guided.practiceVisit else { return nil }
      switch visit.completionState {
      case .active:
        return nil
      case .saved:
        return Status(
          title: "Saved to recent practice",
          detail:
            "Saved the date, the sound group and 1 word. No recording, check result or age was saved. Close to see it under Recent practice.",
          hint: "This shows that practice happened, not how the word was said.")
      case .completedNotSaved(.writeFailed):
        return Status(
          title: "Saving not confirmed",
          detail:
            "Practice finished, but saving to Recent practice could not be confirmed. Retry saving when it is available, or leave without saving again."
        )
      case .completedNotSaved(.storeUnavailable):
        return Status(
          title: "Practice not saved",
          detail: "Practice finished, but saving to Recent practice isn't available here.")
      }
    }

    private func savedView(_ save: Status) -> some View {
      VStack(alignment: .leading, spacing: 8) {
        Text(save.title)
          .font(.title2.weight(.medium))
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-practice-save-status")
        if let detail = save.detail {
          Text(detail)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-practice-save-detail")
        }
        if let hint = save.hint {
          Text(hint)
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
    }

    @ViewBuilder private var finishControls: some View {
      if let visit = guided.practiceVisit {
        switch visit.completionState {
        case .active:
          let copy =
            visit.hasValidCapture
            ? "Finish practice saves the date, sound group and 1 word to Recent practice after temporary-media cleanup succeeds. It records that you practiced, not that the word was said better."
            : recordingUnavailable
              ? "Finish practice needs a new recording, and recording is unavailable for this visit. Listening or skipping doesn't save anything."
              : "Make a new recording of this word, then tap Finish practice to save it to Recent practice. Listening or skipping doesn't save anything."
          VStack(alignment: .leading, spacing: 8) {
            Button("Finish practice") { transition { _ = await guided.finishPractice() } }
              .buttonStyle(DirectPracticeButtonStyle())
              .disabled(!guided.canFinishPractice || transitionPending)
              .accessibilityHint(
                guided.canFinishPractice
                  ? "Saves that this word was practiced. Not a pronunciation result."
                  : "Available after a new recording, once recording and checks have finished."
              )
              .accessibilityIdentifier("guided-finish-practice")
            Text(copy)
              .font(.footnote)
              .foregroundStyle(DirectPracticeStyle.muted)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("guided-finish-note")
          }
        case .completedNotSaved:
          if layout.retrySave {
            Button("Retry saving") { transition { _ = await guided.retryPracticeSave() } }
              .buttonStyle(DirectPracticeButtonStyle())
              .disabled(!guided.canRetryPracticeSave || transitionPending)
              .accessibilityHint("Tries once more to save this practice. Nothing is recorded.")
              .accessibilityIdentifier("guided-retry-practice-save")
          }
        case .saved:
          EmptyView()
        }
      }
    }

    @ViewBuilder private var startRecheck: some View {
      if guided.firstSummary != nil && guided.recheckSummary == nil {
        Button("Start recheck") { transition { _ = await guided.startRecheck() } }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(!guided.canTransition || transitionPending)
          .accessibilityHint("Records all 13 words again as a fresh round.")
          .accessibilityIdentifier("guided-start-recheck")
      }
    }

    private var listeningCue: String? {
      guard guided.phase == .practice, let prompt = guided.currentItem?.prompt,
        prompt == feedback.selectedPrompt
      else { return nil }
      return ResearchPracticeFocus.cue(for: prompt, exampleAvailable: feedback.example != nil)
    }

    private func exampleButtonTitle(_ control: PlaybackControl) -> String {
      switch control {
      case .loading, .preparing: "Cancel example"
      case .playing: "Stop example"
      case .stopping: "Stopping example…"
      case .idle, .blocked: "Play example"
      }
    }

    private func listening(_ example: ResearchPracticeExample?) -> some View {
      let control = playbackControl(.example)
      return VStack(alignment: .leading, spacing: 12) {
        Text("Listen and compare").font(.headline).accessibilityAddTraits(.isHeader)
        if example?.isGeneratedFixture == true {
          Text("Generated example for UI test")
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-example-generated")
        }
        if let cue = listeningCue {
          Text(cue)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-example-cue")
        }
        // Held playback is explained by the status above and recovered with Retry stopping.
        if example != nil {
          if control != .blocked {
            secondary(exampleButtonTitle(control), id: "guided-listen") {
              notePlaybackTap(.example)
              feedback.toggleExample()
            }
            .disabled(control == .stopping || !feedback.canPlayExample)
          }
          if control == .loading {
            ProgressView()
              .frame(maxWidth: .infinity, minHeight: 44)
              .accessibilityLabel("Loading example")
          }
        }
        if let line = playbackStatus(.example) {
          Text(line)
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-example-status")
        } else if feedback.exampleCleanupBlocked {
          Text(
            "A temporary example couldn't be removed. Recording, replay and moving on wait until it's removed. Your recordings and results are unchanged."
          )
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("guided-example-cleanup")
          if exampleOnlyCleanupIssue {
            recoveryControls(id: "guided-example-cleanup-retry")
          }
        } else if control == .playing {
          Text("Playing example")
            .font(.subheadline.weight(.medium))
            .accessibilityIdentifier("guided-example-playing")
        } else if case .failed(let error) = feedback.exampleState {
          Text("The example couldn't be played. \(error.userMessage)")
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-example-failed")
        }
        if let example {
          Text(
            example.isGeneratedFixture
              ? "This example is generated local test audio. No human spoke it, and it isn't loaded from the service. It's removed after playback has stopped."
              : "Play example requests a public recording from the service on this computer. Your recording isn't sent. It's removed after playback has stopped."
          )
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          exampleCredit(example)
        } else {
          Text("Example recording isn’t available for this word.")
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("guided-example-unavailable")
        }
      }
    }

    private func exampleCredit(_ example: ResearchPracticeExample) -> some View {
      DisclosureGroup {
        VStack(alignment: .leading, spacing: 8) {
          if example.isGeneratedFixture {
            Text("No human spoke this example. It was generated for UI testing.")
            Text(example.attribution)
            Text("Changes: \(example.changes)")
            Text("It isn't a licensed recording or a clinical reference.")
          } else {
            Text("By \(example.author)")
            Text(example.attribution)
            Text("Changes: \(example.changes)")
            Text("License: \(example.licenseId)")
            Text(
              "Source label: \(example.declaredVariety). Reported by the source, not a verified speaker variety."
            )
            Link("Source page", destination: example.sourceURL)
              .frame(minHeight: 44)
              .accessibilityLabel("Example source page")
            Link("License text", destination: example.licenseURL)
              .frame(minHeight: 44)
              .accessibilityLabel("Example license, \(example.licenseId)")
            Text(
              (example.speakerAgeKnown ? "" : "Speaker age is unknown. ")
                + (example.clinicalReferenceApproved
                  ? ""
                  : "Not approved as a clinical reference; it's one example, not the correct way to say the word.")
            )
          }
        }
        .font(.footnote)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      } label: {
        Text("Example source and license")
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .frame(minHeight: 44, alignment: .leading)
      }
      .accessibilityIdentifier("guided-example-credit")
    }

    // MARK: Summary

    private func summaryScreen(interactive: Bool) -> some View {
      VStack(alignment: .leading, spacing: 20) {
        Text(guided.comparison != nil ? "Both rounds" : "First round summary")
          .font(.system(.title2, design: .serif))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-summary-title")
        if guided.childContext != nil { contextLine }
        Text(
          "Whole-word recognizer observations for all 13 planned words, including skipped and not reached. Not a pronunciation score or diagnosis."
        )
        .font(.subheadline)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        if interactive && guided.recheckSummary == nil { practicePlanIntroduction }
        if let comparison = guided.comparison {
          Text(
            "Both rounds have a matched or unmatched word observation for \(comparison.pairedCount) of \(comparison.rows.count) words."
          )
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("guided-paired-count")
          Text(
            "Differences between rounds don't measure improvement. They compare whole-word recognition observations only."
          )
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("guided-comparison-limit")
          ForEach(comparison.rows) { row in
            PracticeRule()
            comparisonRow(row)
            if interactive { practiceButton(row.first.item) }
          }
        } else if let summary = guided.firstSummary {
          ForEach(summary.rows) { row in
            PracticeRule()
            Text("\(row.word) · \(Self.text(for: row.disposition))")
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityElement(children: .ignore)
              .accessibilityLabel("\(row.word), \(Self.text(for: row.disposition))")
              .accessibilityIdentifier("guided-row-\(row.id)")
            if interactive { practiceButton(row.item) }
          }
        }
        PracticeRule()
        counts
        if interactive { startRecheck }
      }
    }

    private func comparisonRow(_ row: ResearchGuidedWordComparisonRow) -> some View {
      let first = Self.text(for: row.first.disposition)
      let recheck = Self.text(for: row.recheck.disposition)
      let warning =
        "Recordings for both rounds have identical bytes. Independent acoustic evidence has not been established."
      return VStack(alignment: .leading, spacing: 4) {
        Text(row.word).font(.headline)
        Text("First: \(first)")
        Text("Recheck: \(recheck)")
        if row.sameAudioWarning {
          Text(warning).font(.footnote)
        }
      }
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityElement(children: .ignore)
      .accessibilityLabel(
        "\(row.word). First: \(first). Recheck: \(recheck)."
          + (row.sameAudioWarning ? " \(warning)" : "")
      )
      .accessibilityIdentifier("guided-row-\(row.id)")
    }

    private func practiceButton(_ item: ResearchGuidedWordItem) -> some View {
      secondary("Practice “\(item.word)”", id: "guided-practice-word-\(item.id)") {
        let itemID = item.id
        transition { _ = await guided.practice(item: itemID) }
      }
      .disabled(!guided.canTransition || transitionPending)
    }

    private var counts: some View {
      VStack(alignment: .leading, spacing: 12) {
        Button {
          showCounts.toggle()
        } label: {
          HStack {
            Text("Counts").fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Image(systemName: showCounts ? "chevron.up" : "chevron.down").accessibilityHidden(true)
          }
          .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityValue(showCounts ? "Shown" : "Hidden")
        .accessibilityIdentifier("guided-counts")
        if showCounts {
          if let first = guided.firstSummary {
            countText("First round", first, id: "guided-counts-first")
          }
          if let recheck = guided.recheckSummary {
            countText("Recheck", recheck, id: "guided-counts-recheck")
          }
          Text(
            "Requests started counts checks whose request began. It doesn't confirm the upload completed or that the service received it. Practice recordings aren't included."
              + (isGeneratedUITest
                ? " In this generated fixture, request starts are simulated." : "")
          )
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
        }
      }
    }

    private func countText(_ title: String, _ summary: ResearchGuidedWordSummary, id: String)
      -> some View
    {
      Text(
        """
        \(title)
        Planned words: \(summary.plannedCount)
        Recording attempts: \(summary.attemptsStarted)
        Submitted checks: \(summary.submissions)
        Requests started: \(summary.transportStarts)
        Validated responses: \(summary.validatedResponses)
        Recognizer observations: \(summary.lexicalObservations)
        """
      )
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityIdentifier(id)
    }

    // MARK: Ended

    private var ended: some View {
      VStack(alignment: .leading, spacing: 16) {
        Text("Guided check ended")
          .font(.title2.weight(.medium))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-ended")
        if let error = guided.lastError {
          Text(error).fixedSize(horizontal: false, vertical: true)
        }
        if guided.firstSummary != nil { summaryScreen(interactive: false) }
      }
    }

    private func secondary(_ title: String, id: String, action: @escaping @MainActor () -> Void)
      -> some View
    {
      Button(action: action) {
        Text(title)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.horizontal, 16)
          .padding(.vertical, 10)
          .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
          .contentShape(Rectangle())
          .overlay(Rectangle().strokeBorder(DirectPracticeStyle.muted, lineWidth: 1))
      }
      .font(.body)
      .buttonStyle(.plain)
      .accessibilityIdentifier(id)
    }
  }
#endif
