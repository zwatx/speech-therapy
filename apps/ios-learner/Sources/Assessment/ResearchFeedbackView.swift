#if DEBUG && targetEnvironment(simulator)
  import Accessibility
  import AVFoundation
  import SwiftUI

  /// One temporary take with two separate explicit checks: whole-word recognition and, for an adult
  /// saying "bread", a sound comparison. Capture and replay work without either check.
  struct ResearchFeedbackView: View {
    private let isGeneratedUITest: Bool
    @StateObject private var session: ResearchFeedbackSession
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 64
    @AccessibilityFocusState private var soundStatusFocused: Bool
    @AccessibilityFocusState private var statusFocused: Bool
    @AccessibilityFocusState private var recoveryFocused: Bool
    @AccessibilityFocusState private var wordPickerFocused: Bool
    @State private var soundCancelled = false
    @State private var closeAttempted = false
    @State private var closeFailed = false
    @State private var closeWaiter: UUID?
    @State private var closeRoute = CloseRoute()
    @State private var recoveryWaiter: UUID?
    @State private var recoveryFailed = false
    @State private var playbackTarget: PlaybackTarget?
    @State private var learnerStopped = false
    @State private var settledLayout = ActionLayout()
    @State private var wordChoicesOpen = false

    init(
      session: ResearchFeedbackSession? = nil,
      participationWriter: (any ResearchGuidedPracticeParticipationRecording)? = nil
    ) {
      let fixture = ResearchUnifiedFeedbackUITestFixtures.selected()
      isGeneratedUITest = fixture != nil
      // Fixture sessions bring their own isolated history writer. The default actual session uses
      // the reviewed browser-successor contract on its separate native service instance.
      _session = StateObject(
        wrappedValue: session
          ?? fixture.map { ResearchUnifiedFeedbackUITestFixtures.session(for: $0) }
          ?? ResearchFeedbackSession(
            soundProcessor: ResearchSoundClient(service: .browserWordGuess),
            exampleLoader: ResearchPracticeExampleClient(service: .browserWordGuess),
            participationWriter: participationWriter,
            wordGuessProcessor: ResearchWordGuessClient(service: .browserWordGuess)))
    }

    private struct Status {
      let id: String
      let title: String
      var detail: String? = nil
      var identifier: String? = nil
    }

    /// Which control started the current playback. Every start here is a learner tap, so this
    /// names the stopping or blocked control after the session has revoked its own source.
    private enum PlaybackTarget: Equatable {
      case replay(ResearchFeedbackReplaySource)
      case example
    }

    private enum PlaybackControl { case idle, loading, preparing, playing, stopping, blocked }

    /// Guards that decide which buttons exist. Audio transitions briefly clear them; the last
    /// settled values keep those buttons in place, disabled, until playback has released.
    private struct ActionLayout: Equatable {
      var check = false
      var anotherTry = false
      var finish = false
      var retrySave = false
      var checkSound = false
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

    private static let soundNames = [
      "R": "r", "B": "b", "N": "n", "K": "k", "S": "s", "V": "v", "Y": "y",
      "TH": "th", "DH": "voiced th", "NG": "ng", "ZH": "zh",
    ]

    private static let contexts: [ResearchPracticeContext?] =
      [nil, .adult] + (6...12).map { Optional(ResearchPracticeContext.child(ageYears: $0)) }

    private static let stoppingPlayback =
      "Stopping playback. Other actions return once it has stopped."
    private static let playbackBlockedTitle = "Playback hasn't confirmed it stopped"
    private static let playbackBlockedDetail =
      "Recording, checks and other audio stay paused until it does. Your recordings and any results are unchanged."

    var body: some View {
      VStack(spacing: 0) {
        feedbackHeader
        ScrollView {
          VStack(alignment: .leading, spacing: 24) {
            Text("Speech practice")
              .font(.system(.largeTitle, design: .serif))
              .accessibilityAddTraits(.isHeader)
              .accessibilityIdentifier("feedback-title")
            PracticeRule()
            Text(prompt?.word ?? "")
              .font(.system(size: wordSize, design: .serif))
              .minimumScaleFactor(0.4).lineLimit(1)
              .accessibilityIdentifier("feedback-word")
            wordChooser
            Text(
              "Whole-word recognition and a separate sound comparison. Neither is a pronunciation score or diagnosis, and accuracy hasn't been established for adults or children."
            )
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-limits")
            status
            if session.sharedProcessingPaused && session.phase != .cleanupBlocked
              && session.phase != .ended
            {
              sharedPause
            }
            actions
            if !practiceClosing, case .feedback(let feedback) = session.phase {
              resultDetails(feedback)
            }
            if !practiceClosing, let summary = session.summary {
              observations(summary)
            }
            if session.example != nil || listeningCue != nil {
              listening(session.example)
            }
            PracticeRule()
            soundSection
            PracticeRule()
            setup
            Text(
              "This simulator build sends checks to one local service on this computer. Word checks and sound comparisons are separate requests, each sent only when you tap its Check button, and only for your latest try. Up to two of your tries stay temporarily on this device so you can listen back; another try replaces the earlier one first. They're removed when you retake, cancel a check, move on, change settings or leave. If a file on this device can't be removed, this screen says so and it may remain on this device. A check sends the clip to the service, which makes its own temporary copy; if that copy can't be confirmed removed, it may remain on this computer and both checks pause."
            )
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-note")
          }
          .padding(24)
          .frame(maxWidth: 560, alignment: .leading)
          .frame(maxWidth: .infinity)
        }
        // Give scrolling content a real boundary below the fixed Close header.
        .clipped()
      }
      .background(DirectPracticeStyle.canvas.ignoresSafeArea())
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
      .toolbar(.hidden, for: .navigationBar)
      .interactiveDismissDisabled(closeHeld)
      .safeAreaInset(edge: .top, spacing: 0) {
        VStack(spacing: 0) {
          HStack {
            Button("Close") { close() }
              .font(.body)
              .buttonStyle(.plain)
              .frame(minWidth: 44, minHeight: 44)
              .contentShape(Rectangle())
              .accessibilityIdentifier("feedback-close")
            Spacer()
          }
          .padding(.horizontal, 24)
          if let closeNote {
            Text(closeNote)
              .font(.subheadline).fixedSize(horizontal: false, vertical: true)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.horizontal, 24).padding(.bottom, 8)
              .accessibilityIdentifier("feedback-close-note")
          }
          if isGeneratedUITest {
            Text("Generated · no mic or model")
              .font(.footnote).fixedSize(horizontal: false, vertical: true)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.horizontal, 24).padding(.bottom, 8)
              .accessibilityIdentifier("feedback-ui-test-banner")
          }
          PracticeRule()
        }
        .background(DirectPracticeStyle.canvas)
      }
      .onAppear {
        if session.selectedPrompt == nil {
          session.selectedPrompt = ResearchFeedbackCatalog.prompts.first
        }
        settledLayout = liveLayout
      }
      .onDisappear {
        // The session owns the strong cleanup task; this view's later results can't dismiss.
        closeRoute.revoke()
        session.end()
      }
      .onChange(of: scenePhase) { _, phase in
        if phase == .active { session.appDidBecomeActive() }
        if phase == .background { session.appDidEnterBackground() }
        if phase == .inactive { session.appDidBecomeInactive() }
      }
      .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification))
      {
        notification in
        if let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
          AVAudioSession.InterruptionType(rawValue: raw) == .began
        {
          session.audioWasInterrupted()
        }
      }
      // onChange fires only when the heading text changes, so each result is announced once.
      .onChange(of: currentStatus.title) { _, title in
        AccessibilityNotification.Announcement(
          session.phase == .cleanupBlocked && session.canRetryAudioCleanup
            ? "\(title). \(recoveryTitle) is available." : title
        ).post()
      }
      // Only the sound check's own progress and outcome are spoken; eligibility changes are not.
      // A model result moves focus to its title, whose label carries the limitation, instead.
      .onChange(of: soundStatus.id) { _, _ in
        let status = soundStatus
        if status.modelResult {
          soundStatusFocused = true
        } else if soundCheckOutcome || status.id == "ready-cancelled" {
          AccessibilityNotification.Announcement("Sound comparison: \(status.spokenTitle)").post()
        }
      }
      // Example progress and outcomes are announced once per distinct state; focus doesn't move.
      // Starting is silent, stopping follows the learner's own stop and blocked leads the status.
      .onChange(of: exampleStatus?.id) { _, id in
        if let id, !["idle", "starting", "stopping", "playback-blocked"].contains(id),
          let status = exampleStatus
        {
          AccessibilityNotification.Announcement(status.title).post()
        }
      }
      .onChange(of: session.playbackState) { _, state in announcePlayback(state) }
      .onChange(of: closeNote) { _, note in
        if let note { AccessibilityNotification.Announcement(note).post() }
      }
      .onChange(of: session.hasLocalMediaCleanupIssue) { _, blocked in
        recoveryFailed = false
        if blocked { recoveryFocused = true }
      }
      .onChange(of: session.closeRequested) { _, requested in
        if !requested { closeAttempted = false }
      }
      .onChange(of: liveLayout) { _, live in
        if !audioHeld { settledLayout = live }
      }
      .onChange(of: audioHeld) { _, held in
        if !held { settledLayout = liveLayout }
      }
    }

    private var prompt: ResearchFeedbackPrompt? { session.selectedPrompt }

    private var quotedWord: String { "“\(prompt?.word ?? "")”" }

    /// The exact canonical bread prompt, not any prompt whose word is "bread".
    private var isBread: Bool {
      guard let prompt else { return false }
      return prompt
        == ResearchFeedbackCatalog.prompts.first(where: { $0.id == ResearchSoundContract.promptId })
    }

    private var phaseEditable: Bool {
      switch session.phase {
      case .ready, .review, .feedback, .failed, .permissionDenied: true
      case .requestingPermission, .recording, .checking, .cleanupBlocked, .ended: false
      }
    }

    private var setupEditable: Bool { session.setupEditable }

    private func retake() {
      soundCancelled = false
      session.retake()
    }

    private func recordAnotherTry() {
      soundCancelled = false
      Task { await session.recordAnotherTry() }
    }

    private func advance() {
      soundCancelled = false
      Task { @MainActor in await session.advance() }
    }

    // MARK: Close and recovery

    /// Playback, capture or a temporary file still needs cleanup, or a Close is waiting.
    private var closeHeld: Bool {
      session.audioTransitionPending || session.hasLocalMediaCleanupIssue
        || session.isPermissionPending || (session.closeRequested && session.phase != .ended)
    }

    /// Revoke synchronously, then wait for the session's own acknowledged end. A repeated tap
    /// joins the same owned Close task; a failed Close stays here until explicit recovery.
    private func close() {
      closeAttempted = true
      closeFailed = false
      let cleanup = session.end()
      guard closeWaiter == nil else { return }
      let token = UUID()
      closeWaiter = token
      let route = closeRoute
      Task { @MainActor in
        let ended = await cleanup.value
        if closeWaiter == token { closeWaiter = nil }
        if ended, leaveAfterClose(route) { return }
        closeFailed = true
        if session.canRetryAudioCleanup { recoveryFocused = true }
      }
    }

    /// Leaves only on a positive Close or recovery result, after the learner's own Close, once
    /// the session has acknowledged its end. The phase alone never navigates.
    @discardableResult private func leaveAfterClose(_ route: CloseRoute) -> Bool {
      guard closeAttempted, session.closeRequested, session.phase == .ended else { return false }
      route.leave(dismiss)
      return true
    }

    private var closeNote: String? {
      guard closeAttempted, session.closeRequested, session.phase != .ended else { return nil }
      if session.isPermissionPending {
        return
          "Waiting for the microphone permission answer. This screen closes once it's answered."
      }
      if session.playbackCleanupBlocked {
        return
          "Playback hasn't confirmed it stopped, so this screen stays open. Use Retry stopping."
      }
      if session.captureCleanupState.hasHardwareIssue {
        return
          "Recording hasn't confirmed it stopped, so this screen stays open. Use Retry stopping."
      }
      if session.hasLocalMediaCleanupIssue {
        return
          "A temporary file couldn't be removed, so this screen stays open. Use \(exampleOnlyCleanupIssue ? "Retry example cleanup" : "Retry cleanup"). Until then it may remain on this device."
      }
      if session.audioTransitionPending || session.playbackState != .idle {
        return "Stopping playback before closing. This screen closes once it has stopped."
      }
      if closeWaiter != nil {
        return "Finishing current work before closing. This screen closes once it's done."
      }
      // Nothing here can be retried; say so rather than offering an action that can't help.
      return closeFailed ? "Closing couldn't be confirmed, so this screen stays open." : nil
    }

    /// Only a public example file failed; its own section offers the retry.
    private var exampleOnlyCleanupIssue: Bool {
      session.exampleCleanupBlocked && session.phase != .cleanupBlocked
        && !session.playbackCleanupBlocked && session.captureCleanupState == .idle
        && session.example != nil
    }

    private var unifiedRecovery: Bool {
      session.hasLocalMediaCleanupIssue && !exampleOnlyCleanupIssue
    }

    /// Held playback or capture hardware needs stopping; otherwise a file needs removing.
    private var recoveryStops: Bool {
      session.playbackCleanupBlocked || session.captureCleanupState.hasHardwareIssue
    }

    private var recoveryTitle: String {
      exampleOnlyCleanupIssue
        ? "Retry example cleanup" : recoveryStops ? "Retry stopping" : "Retry cleanup"
    }

    private var recoveryNote: String? {
      if recoveryWaiter != nil {
        if session.playbackCleanupBlocked { return Self.stoppingPlayback }
        if session.captureCleanupState.hasHardwareIssue {
          return "Stopping recording. Other actions return once it has stopped."
        }
        return "Trying to remove it again…"
      }
      return recoveryFailed ? "Still not confirmed. You can try again." : nil
    }

    /// Explicit recovery only. A repeated tap joins the session's one owned recovery task.
    private func retryCleanup() {
      let recovery = session.retryAudioCleanup()
      recoveryFailed = false
      guard recoveryWaiter == nil else { return }
      let token = UUID()
      recoveryWaiter = token
      let route = closeRoute
      Task { @MainActor in
        let recovered = await recovery.value
        guard recoveryWaiter == token else { return }
        recoveryWaiter = nil
        // Recovery that completes a held Close has acknowledged the end; leave once.
        if recovered, leaveAfterClose(route) {
          return
        } else if recovered && !session.hasLocalMediaCleanupIssue {
          statusFocused = true
        } else if session.hasLocalMediaCleanupIssue {
          recoveryFailed = true
          AccessibilityNotification.Announcement("Still not confirmed. You can try again.").post()
          recoveryFocused = true
        }
      }
    }

    private func recoveryControls(id: String) -> some View {
      VStack(alignment: .leading, spacing: 8) {
        secondary(recoveryTitle, id: id) { retryCleanup() }
          .disabled(!session.canRetryAudioCleanup)
          .accessibilityHint(
            session.playbackCleanupBlocked
              ? "Asks playback to stop again. Nothing plays."
              : session.captureCleanupState.hasHardwareIssue
                ? "Asks recording to stop again. Nothing is recorded."
                : "Tries removing the temporary file again. Nothing is recorded or sent."
          )
          .accessibilityFocused($recoveryFocused)
        if let note = recoveryNote {
          Text(note)
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-retry-audio-cleanup-note")
        }
      }
    }

    // MARK: Playback controls

    /// Preparing, stopping or blocked audio, or cleanup that hasn't settled.
    private var audioHeld: Bool {
      session.audioTransitionPending || session.hasLocalMediaCleanupIssue
    }

    /// Startup capture cleanup failed with nothing retained, so this visit can't record again and
    /// there's nothing to retry. Retained playback, capture or files lead with their own recovery.
    private var recordingUnavailable: Bool {
      session.recordingUnavailable && !session.hasLocalMediaCleanupIssue
        && session.phase != .cleanupBlocked && session.phase != .ended
    }

    private var liveLayout: ActionLayout {
      ActionLayout(
        check: session.canCheck, anotherTry: session.canRecordAnotherTry,
        finish: session.canFinishPractice, retrySave: session.canRetryPracticeSave,
        checkSound: session.canCheckSound)
    }

    private var layout: ActionLayout { audioHeld ? settledLayout : liveLayout }

    private var playbackOwner: PlaybackTarget? {
      session.activeReplaySource.map(PlaybackTarget.replay) ?? playbackTarget
    }

    /// Playing only after the session's own acknowledgement; otherwise the Cancel form stays.
    private func playbackControl(_ target: PlaybackTarget) -> PlaybackControl {
      let owned = playbackOwner == target
      switch session.playbackState {
      case .idle:
        return target == .example && session.exampleState == .loading ? .loading : .idle
      case .preparing:
        return owned ? .preparing : .idle
      case .playing:
        guard owned else { return .idle }
        let acknowledged =
          switch target {
          case .replay(let source): session.playingReplaySource == source
          case .example: session.exampleState == .playing
          }
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
        if session.playingReplaySource != nil {
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

    // MARK: Setup

    private var setupRowLayout: AnyLayout {
      dynamicTypeSize.isAccessibilitySize
        ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
        : AnyLayout(HStackLayout())
    }

    /// Keep the selected word under its heading, with enough width for the full occurrence label.
    private var wordChooser: some View {
      VStack(alignment: .leading, spacing: 4) {
        Text("Word")
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .accessibilityHidden(true)
        if dynamicTypeSize.isAccessibilitySize {
          inlineWordChooser
        } else {
          setupMenu(
            "Word", value: prompt.map(label(for:)) ?? "", id: "feedback-word-picker", stacked: true
          ) {
            Picker(
              "Word",
              selection: Binding(
                get: { session.selectedPrompt?.id ?? "" },
                set: { id in
                  // A menu still on screen can outlive the phase that allowed it.
                  guard setupEditable, !session.isFinalizingPractice else { return }
                  session.selectedPrompt = ResearchFeedbackCatalog.prompts.first { $0.id == id }
                })
            ) {
              ForEach(ResearchFeedbackCatalog.prompts) { Text(label(for: $0)).tag($0.id) }
            }
          }
        }
      }
      .disabled(!setupEditable || session.isFinalizingPractice)
      .onChange(of: setupEditable) { _, editable in
        if !editable { closeWordChoices(returnFocus: false) }
      }
      .onChange(of: session.isFinalizingPractice) { _, finalizing in
        if finalizing { closeWordChoices(returnFocus: false) }
      }
      .onChange(of: session.selectedPrompt) { _, _ in
        if wordChoicesOpen { closeWordChoices(returnFocus: false) }
      }
      .onChange(of: dynamicTypeSize.isAccessibilitySize) { _, accessibilitySize in
        if !accessibilitySize { closeWordChoices(returnFocus: false) }
      }
    }

    /// Large text uses the page's existing scroll instead of a separate native popup.
    private var inlineWordChooser: some View {
      let value = prompt.map(label(for:)) ?? ""
      return VStack(alignment: .leading, spacing: 8) {
        Button {
          guard setupEditable, !session.isFinalizingPractice else { return }
          if wordChoicesOpen {
            closeWordChoices()
          } else {
            wordPickerFocused = false
            wordChoicesOpen = true
          }
        } label: {
          HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(value)
              .fixedSize(horizontal: false, vertical: true)
              .frame(maxWidth: .infinity, alignment: .leading)
            Image(systemName: wordChoicesOpen ? "chevron.up" : "chevron.down")
              .imageScale(.small)
              .accessibilityHidden(true)
          }
          .font(.body)
          .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Word")
        .accessibilityValue(value)
        .accessibilityHint(wordChoicesOpen ? "Hides the word choices." : "Shows the word choices.")
        .accessibilityIdentifier("feedback-word-picker")
        .accessibilityFocused($wordPickerFocused)
        if wordChoicesOpen {
          VStack(alignment: .leading, spacing: 8) {
            Text("Choose a word")
              .font(.headline)
              .accessibilityAddTraits(.isHeader)
            secondary("Keep current word", id: "feedback-word-choices-cancel") {
              closeWordChoices()
            }
            ForEach(ResearchFeedbackCatalog.prompts) { choice in
              let selected = choice == session.selectedPrompt
              Button {
                chooseWord(choice)
              } label: {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                  Image(systemName: "checkmark")
                    .opacity(selected ? 1 : 0)
                    .accessibilityHidden(true)
                  Text(label(for: choice))
                    .fixedSize(horizontal: false, vertical: true)
                  Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
              }
              .buttonStyle(.plain)
              .accessibilityLabel(label(for: choice))
              .accessibilityAddTraits(selected ? .isSelected : [])
            }
          }
          .accessibilityElement(children: .contain)
          .accessibilityIdentifier("feedback-word-choices")
        }
      }
    }

    private func chooseWord(_ choice: ResearchFeedbackPrompt) {
      guard setupEditable, !session.isFinalizingPractice,
        let canonical = ResearchFeedbackCatalog.prompts.first(where: { $0.id == choice.id }),
        canonical == choice
      else {
        closeWordChoices(returnFocus: false)
        return
      }
      if canonical != session.selectedPrompt { session.selectedPrompt = canonical }
      closeWordChoices()
    }

    private func closeWordChoices(returnFocus: Bool = true) {
      wordChoicesOpen = false
      // Selecting can synchronously start cleanup and disable Word; never focus that target.
      wordPickerFocused =
        returnFocus && setupEditable && !session.isFinalizingPractice
        && dynamicTypeSize.isAccessibilitySize
    }

    private var setup: some View {
      VStack(alignment: .leading, spacing: 12) {
        setupRowLayout {
          Text("Who is practicing?")
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
          if !dynamicTypeSize.isAccessibilitySize { Spacer(minLength: 12) }
          setupMenu(
            "Who is practicing?", value: Self.label(for: session.practiceContext),
            id: "feedback-context"
          ) {
            Picker(
              "Who is practicing?",
              selection: Binding(
                get: { Self.contexts.firstIndex { $0 == session.practiceContext } ?? 0 },
                set: { index in
                  if Self.contexts[index] != session.practiceContext {
                    soundCancelled = false
                    session.practiceContext = Self.contexts[index]
                  }
                })
            ) {
              ForEach(Self.contexts.indices, id: \.self) {
                Text(Self.label(for: Self.contexts[$0])).tag($0)
              }
            }
          }
        }
        .frame(minHeight: 44)
        checkbox(
          "Allow word checks on this computer", id: "feedback-opt-in",
          on: session.localProcessingEnabled
        ) {
          soundCancelled = false
          session.localProcessingEnabled.toggle()
        }
        Text(
          "Changing the word, who's practicing or a check option clears the current recording."
            + (session.localProcessingEnabled && session.practiceContext != nil
              ? ""
              : " Recording and replay work without these. To check the word, choose who's practicing and allow word checks.")
        )
        .font(.footnote)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("feedback-setup-note")
      }
      .disabled(!setupEditable || session.isFinalizingPractice)
    }

    /// A menu whose selected value wraps and grows; the native menu Picker label clips at large sizes.
    private func setupMenu<Choices: View>(
      _ title: String, value: String, id: String, stacked forceStacked: Bool = false,
      @ViewBuilder choices: () -> Choices
    ) -> some View {
      let stacked = forceStacked || dynamicTypeSize.isAccessibilitySize
      return Menu {
        choices().pickerStyle(.inline).labelsHidden()
      } label: {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
          Text(value)
            .multilineTextAlignment(stacked ? .leading : .trailing)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: forceStacked ? .infinity : nil, alignment: .leading)
          Image(systemName: "chevron.up.chevron.down")
            .imageScale(.small)
            .accessibilityHidden(true)
        }
        .font(.body)
        .frame(maxWidth: stacked ? .infinity : nil, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
      }
      .menuOrder(.fixed)
      .accessibilityLabel(title)
      .accessibilityValue(value)
      .accessibilityIdentifier(id)
    }

    private func checkbox(
      _ title: String, id: String, on: Bool, action: @escaping @MainActor () -> Void
    ) -> some View {
      Button(action: action) {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
          Image(systemName: on ? "checkmark.square" : "square")
            .accessibilityHidden(true)
          Text(title)
            .fixedSize(horizontal: false, vertical: true)
          Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityAddTraits(.isToggle)
      .accessibilityValue(on ? "On" : "Off")
      .accessibilityIdentifier(id)
    }

    private static func label(for context: ResearchPracticeContext?) -> String {
      switch context {
      case nil: "Not set"
      case .adult?: "Adult (18+)"
      case .child(let age)?: "Child, age \(age)"
      }
    }

    private func label(for prompt: ResearchFeedbackPrompt) -> String {
      let sound = Self.soundNames[prompt.targetPhone] ?? prompt.targetPhone.lowercased()
      let occurrences = prompt.phones.indices.filter { prompt.phones[$0] == prompt.targetPhone }
      let ordinals = ["first", "second", "third"]
      guard occurrences.count > 1, let n = occurrences.firstIndex(of: prompt.occurrenceIndex),
        n < ordinals.count
      else { return "\(prompt.word) · \(sound) sound" }
      return "\(prompt.word) · \(ordinals[n]) \(sound) sound"
    }

    // MARK: Status

    private var status: some View {
      VStack(alignment: .leading, spacing: 12) {
        Text(currentStatus.title)
          .font(.title2.weight(.medium))
          .accessibilityAddTraits(.isHeader)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier(currentStatus.identifier ?? "feedback-state-\(currentStatus.id)")
          .accessibilityFocused($statusFocused)
        if let detail = currentStatus.detail {
          Text(detail)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-detail")
        }
        if let guess = recognizerGuess {
          VStack(alignment: .leading, spacing: 4) {
            Text("Recognizer’s guess: \(guess)")
              .font(.system(.body, design: .serif).weight(.medium))
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityLabel("Recognizer’s guess: \(guess)")
              .accessibilityIdentifier("feedback-recognizer-guess")
            Text("A whole-word model guess, not a pronunciation score.")
              .font(.subheadline)
              .foregroundStyle(DirectPracticeStyle.muted)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("feedback-recognizer-guess-note")
          }
        }
      }
    }

    /// The model's single-word guess, only beside a final matched or different result.
    private var recognizerGuess: String? {
      guard !practiceClosing, !session.sharedProcessingPaused,
        case .feedback(let feedback) = session.phase
      else { return nil }
      switch feedback.word {
      case .modelMatched, .modelNotMatched: break
      default: return nil
      }
      guard let word = session.recognizerWordGuess?.normalizedWord, !word.isEmpty,
        word.count <= 256, word.utf8.allSatisfy({ $0 < 128 })
      else { return nil }
      return word
    }

    private var sharedPause: some View {
      VStack(alignment: .leading, spacing: 4) {
        Text("Checks are paused").font(.headline).accessibilityAddTraits(.isHeader)
        Text(
          "The service on this computer can't process recordings safely right now, and a temporary copy may remain there. Word and sound checks stay paused for the rest of this session. Recording and replay on this device still work."
        )
      }
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityIdentifier("feedback-shared-paused")
    }

    private func resultDetails(_ feedback: RecordingFeedback) -> some View {
      VStack(alignment: .leading, spacing: 12) {
        stages(feedback)
        if feedback.targetUnsupported {
          Text("Sound-level checks aren't supported for this word's target sound.")
            .font(.subheadline)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-target-unsupported")
        }
        if !feedback.suggestions.isEmpty {
          VStack(alignment: .leading, spacing: 6) {
            Text("Next steps").font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(feedback.suggestions, id: \.self) { suggestion in
              Text(text(for: suggestion)).fixedSize(horizontal: false, vertical: true)
            }
          }
          .accessibilityIdentifier("feedback-suggestions")
        }
      }
    }

    /// Finishing or a finished visit replaces the take, its results and its actions.
    private var practiceClosing: Bool {
      session.isFinalizingPractice || session.practiceCompletionState != .active
    }

    /// Cleanup and ended states still lead; otherwise finishing outranks every take status.
    private var completionStatus: Status? {
      if session.phase == .cleanupBlocked || session.phase == .ended { return nil }
      if session.isFinalizingPractice {
        return Status(
          id: "finishing-practice", title: "Finishing practice…",
          detail: "Removing your tries from this device, then saving.")
      }
      switch session.practiceCompletionState {
      case .active:
        return nil
      case .saved:
        return Status(
          id: "practice-saved", title: "Saved to recent practice",
          detail: "Your tries were removed from this device.",
          identifier: "feedback-practice-saved")
      case .completedNotSaved(let error):
        return Status(
          id: "practice-not-saved", title: "Practice finished, but saving wasn't confirmed",
          detail: "\(error.userMessage) Your tries were removed from this device.",
          identifier: "feedback-practice-not-saved")
      }
    }

    private var currentStatus: Status {
      if let status = completionStatus { return status }
      if session.isPreparingAnotherTry {
        return Status(
          id: "preparing-another", title: "Getting ready for another try…",
          detail: "Your most recent try is kept while this gets ready.")
      }
      if recordingUnavailable {
        switch session.phase {
        case .ready, .failed, .permissionDenied:
          return Status(
            id: "recording-unavailable", title: "Recording isn't available",
            detail: session.audioCleanupMessage ?? "Recording is unavailable for this visit.")
        default: break
        }
      }
      return switch session.phase {
      case .ready where session.attemptsStarted >= 128:
        Status(
          id: "recording-limit", title: "Recording limit reached for this session",
          detail: "Close and reopen this screen to start another local recording session.")
      case .ready:
        Status(
          id: "ready", title: "Ready to record",
          detail:
            "Tap Record and say the word. Recording stops after 4 seconds. Set who's practicing and the check options below first; changing them later clears the recording."
        )
      case .requestingPermission:
        Status(id: "permission", title: "Getting the microphone ready…")
      case .recording:
        Status(
          id: "recording", title: "Recording",
          detail: "Say \(quotedWord), then tap Stop. Recording stops on its own after 4 seconds.")
      case .review:
        Status(id: "review", title: "Recording ready", detail: reviewDetail)
      case .checking:
        Status(
          id: "checking", title: "Checking the word on this computer…",
          detail: "You can cancel at any time.")
      case .feedback(let feedback):
        result(feedback)
      case .permissionDenied:
        Status(
          id: "denied", title: "Microphone access is off",
          detail: "Allow microphone access in Settings, then try again.")
      case .failed(let error):
        failure(error)
      case .cleanupBlocked:
        cleanupStatus
      case .ended:
        Status(id: "ended", title: "Speech practice closed")
      }
    }

    /// Held playback or capture hardware is never described as a file problem.
    private var cleanupStatus: Status {
      if session.playbackCleanupBlocked {
        return Status(
          id: "playback-blocked", title: Self.playbackBlockedTitle,
          detail: Self.playbackBlockedDetail)
      }
      if session.captureCleanupState.hasHardwareIssue {
        return Status(
          id: "recording-blocked", title: "Recording hasn't confirmed it stopped",
          detail: "Recording, checks and other audio stay paused until it does.")
      }
      return Status(
        id: "cleanup", title: "A temporary recording couldn't be removed",
        detail:
          "Recording, checking, and replay are paused. Use Retry cleanup to try removing it again. Until then it may remain on this device."
      )
    }

    private var reviewDetail: String {
      if layout.check { return "Replay it, record again or tap Check word." }
      if session.isCheckingSound {
        return "Replay and the other actions return when the sound comparison below finishes."
      }
      if session.sharedProcessingPaused { return "Replay it or record again. Checks are paused." }
      return
        "Replay it or record again. To check the word, choose who's practicing and allow word checks below, then record again."
    }

    private func result(_ feedback: RecordingFeedback) -> Status {
      let limit = "Recognition doesn't judge how the sounds were made."
      switch feedback.word {
      case .modelMatched:
        return Status(
          id: "result-matched", title: "Recognition matched \(quotedWord)",
          detail: "The word recognizer identified the requested word. \(limit)")
      case .modelNotMatched:
        return Status(
          id: "result-mismatch", title: "Recognition didn't match \(quotedWord)",
          detail:
            "Speech was found, but the recognizer didn't identify it as \(quotedWord). \(limit)")
      case .uncertain:
        return Status(
          id: "result-uncertain", title: "Recognition was uncertain",
          detail: "The recognizer couldn't settle on a single result. \(limit)")
      case .notSingleWord:
        return Status(
          id: "result-extra-word", title: "Recognition was not a single supported word",
          detail: "Checking needs \(quotedWord) on its own.")
      case .notRun, .unavailable:
        break
      }
      if feedback.speech == .modelNotDetected {
        return Status(
          id: "result-no-speech", title: "No speech was found",
          detail: "The speech detector didn't find speech in this recording.")
      }
      switch feedback.reason {
      case "silence":
        return Status(
          id: "result-quiet", title: "The recording was very quiet",
          detail: "It was too quiet to check.")
      case "clipping":
        let count = feedback.capture?.railSamples ?? 0
        return Status(
          id: "result-numeric-limit", title: "The recording reached its numeric limit",
          detail:
            "\(count) \(count == 1 ? "sample" : "samples") hit the maximum recordable value, so it wasn't checked further. That alone doesn't show the sound was distorted."
        )
      case "invalid_audio":
        return Status(
          id: "result-invalid", title: "This recording couldn't be checked",
          detail: "The service couldn't use this recording. Record the word again.")
      case "busy":
        return Status(
          id: "result-busy", title: "The checking service is busy",
          detail: "Try again in a moment.")
      case "timeout", "worker_timeout":
        return Status(id: "result-timeout", title: "Checking took too long")
      case "cleanup_unconfirmed":
        return Status(
          id: "result-service-cleanup", title: "The service couldn't confirm removing its copy",
          detail:
            "Its temporary processing copy may remain on this computer, and further checks may pause."
        )
      default:
        return Status(
          id: "result-unavailable", title: "Checking couldn't finish",
          detail: "The local service couldn't complete this check. Recording and replay still work."
        )
      }
    }

    private func failure(_ error: RecordingFeedbackError) -> Status {
      switch error {
      case .unsupportedAge:
        Status(
          id: "failed-age", title: "Choose who's practicing to check",
          detail: "Word checks need Adult (18+) or a child aged 6 to 12.")
      case .unsupportedPrompt:
        Status(id: "failed-prompt", title: "This word can't be checked")
      case .invalidRecording:
        Status(
          id: "failed-recording", title: "This recording couldn't be used",
          detail: "Record the word again.")
      case .invalidResponse:
        Status(
          id: "failed-response", title: "The service reply couldn't be verified",
          detail: "No result is shown. Recording and replay still work.")
      case .serviceUnavailable:
        Status(
          id: "failed-service", title: "The local service isn't reachable",
          detail:
            "Make sure the local service on this computer is running. Recording and replay still work."
        )
      case .timeout:
        Status(id: "failed-timeout", title: "Checking took too long", detail: "Try again later.")
      case .processingUnavailable:
        Status(
          id: "failed-unavailable", title: "Checking isn't available right now",
          detail:
            "The local service reports it can't process recordings. Recording and replay still work."
        )
      }
    }

    private func stages(_ feedback: RecordingFeedback) -> some View {
      let speech =
        switch feedback.speech {
        case .modelDetected: "speech found"
        case .modelNotDetected: "no speech found"
        case .notRun: "not run"
        case .unavailable: "unavailable"
        }
      let word =
        switch feedback.word {
        case .modelMatched: "matched \(quotedWord)"
        case .modelNotMatched: "didn't match \(quotedWord)"
        case .uncertain: "uncertain"
        case .notSingleWord: "not a single supported word"
        case .notRun: "not run"
        case .unavailable: "unavailable"
        }
      return VStack(alignment: .leading, spacing: 4) {
        Text("Speech detector: \(speech)")
        Text("Word recognizer: \(word)")
      }
      .font(.subheadline)
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityElement(children: .combine)
      .accessibilityIdentifier("feedback-stages")
    }

    private func text(for suggestion: RecordingFeedback.Suggestion) -> String {
      switch suggestion {
      case .recordAgain: "Record the word again."
      case .reviewRecording: "Replay your recording."
      case .reduceRecordingLevel: "Try a little farther from the microphone."
      case .listenToExample: "Hear someone say \(quotedWord), then try again."
      case .sayOneWord: "Say just \(quotedWord) on its own."
      case .tryAgain: "Try again."
      case .retryLater: "Try checking again later."
      case .processingUnavailable:
        "Checking isn't available right now. Recording and replay still work."
      case .continuePractice: "Move on to the next word when you're ready."
      }
    }

    private func observations(_ summary: CaptureSummary) -> some View {
      let length = summary.duration.formatted(.number.precision(.fractionLength(1)))
      let level = Int(summary.averagePower.rounded())
      return VStack(alignment: .leading, spacing: 4) {
        Text("This recording").font(.headline).accessibilityAddTraits(.isHeader)
        Text("Length \(length) s · average level \(level) dBFS")
          .accessibilityLabel("Length \(length) seconds. Average level \(level) dBFS.")
        Text("These describe the recording, not the speech.")
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
      }
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityIdentifier("feedback-observations")
    }

    // MARK: Sound comparison

    private var soundCheckOutcome: Bool {
      switch session.soundPhase {
      case .checking, .observation, .failed: true
      default: false
      }
    }

    /// Check progress and outcomes use the shared sound presentation; the rest explains eligibility.
    private var soundStatus: ResearchSoundPresentation {
      if session.phase == .cleanupBlocked || session.phase == .ended
        || session.soundPhase == .localCleanupBlocked
      {
        return .init(id: "unavailable", title: "Sound comparison isn't available", detail: "")
      }
      if practiceClosing {
        return .init(
          id: "practice-finished", title: "Sound comparison isn't available",
          detail: "Tap Practice again to record a new try.")
      }
      if soundCheckOutcome {
        let made = ResearchSoundPresentation.make(
          phase: session.soundPhase, paused: false, canCheck: false)
        switch made.id {
        case "checking":
          return .init(
            id: made.id, title: made.title,
            detail: "This usually takes a few seconds. You can stop waiting.")
        case "error-unreachable":
          return .init(
            id: made.id, title: made.title,
            detail:
              "Make sure the local service on this computer is running. Recording and replay still work."
          )
        default:
          return made
        }
      }
      if recordingUnavailable && session.summary == nil {
        return .init(
          id: "recording-unavailable", title: "Sound comparison isn't available",
          detail: "It needs a new recording, and recording is unavailable for this visit.")
      }
      if soundCancelled {
        return .make(phase: .ready, paused: false, canCheck: false, cancelled: true)
      }
      if session.sharedProcessingPaused {
        return .init(
          id: "paused", title: "Sound checks are paused",
          detail: "Recording and replay still work.")
      }
      if session.checksClaimed >= 128 {
        return .init(
          id: "sound-limit", title: "No more sound checks in this session",
          detail: "Existing results and replay on this device remain.")
      }
      guard isBread else {
        return .init(
          id: "other-word", title: "Sound comparison uses “bread” only",
          detail: "Choose bread under Word to try it.")
      }
      guard session.practiceContext == .adult else {
        return .init(
          id: "adult-only", title: "Sound comparison is for adults",
          detail: session.practiceContext == nil
            ? "Choose Adult (18+) under Who is practicing? below to try it."
            : "It hasn't been validated for children, so it's off for child practice. Word checks are separate."
        )
      }
      guard session.soundAdultConfirmed && session.soundProcessingEnabled else {
        return .init(
          id: "setup", title: "Turn on both sound options",
          detail: "Turn them on before you record; changing them clears the current recording.")
      }
      if layout.checkSound {
        return .init(
          id: "ready", title: "Ready to compare sounds",
          detail: "Tap Check sound to send this recording. Each recording can be compared once.")
      }
      if session.summary == nil {
        return .init(
          id: "waiting", title: "Record “bread” to compare sounds",
          detail: "Check sound appears once you have a recording.")
      }
      if session.isProcessing {
        return .init(
          id: "waiting-word", title: "Waiting for the word check",
          detail: "Check sound returns when the word check finishes.")
      }
      return .init(
        id: "unavailable-take", title: "This recording can't be compared",
        detail: "Record “bread” again to compare sounds.")
    }

    private var soundSection: some View {
      let status = soundStatus
      return VStack(alignment: .leading, spacing: 16) {
        Text("Sound comparison")
          .font(.system(.title2, design: .serif))
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("feedback-sound-title")
        Text(
          "Separate from the word check, and only for an adult saying “bread”. An experimental, uncalibrated model compares the whole recording with four versions: BR, BW, BL, and B without the R. It isn't a pronunciation score or diagnosis."
        )
        .font(.subheadline)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("feedback-sound-scope")
        VStack(alignment: .leading, spacing: 8) {
          Text(status.title)
            .font(.title3.weight(.medium))
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
            .accessibilityLabel(status.modelResult ? status.announcement : status.spokenTitle)
            .accessibilityIdentifier("feedback-sound-state-" + status.id)
            .accessibilityFocused($soundStatusFocused)
          if !status.detail.isEmpty {
            Text(status.detail)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("feedback-sound-detail")
          }
        }
        if status.modelResult {
          Text(ResearchSoundPresentation.limitation)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-sound-limit")
        }
        if layout.checkSound {
          Button("Check sound") {
            soundCancelled = false
            session.checkSound()
          }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(!session.canCheckSound)
          .accessibilityIdentifier("feedback-check-sound")
        }
        if session.isCheckingSound {
          ProgressView()
            .frame(maxWidth: .infinity, minHeight: 44)
            .accessibilityLabel("Comparing sounds")
            .accessibilityIdentifier("feedback-sound-checking-progress")
          secondary("Stop waiting", id: "feedback-sound-cancel") {
            session.cancelSound()
            soundCancelled = true
          }
          .disabled(session.audioTransitionPending)
        }
        if status.modelResult {
          Text("To compare again, record a fresh take.")
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-sound-next")
        }
        if isBread && session.practiceContext == .adult && session.phase != .cleanupBlocked
          && session.phase != .ended
        {
          soundSetup
        }
      }
    }

    private var soundSetup: some View {
      VStack(alignment: .leading, spacing: 12) {
        checkbox(
          "I'm an adult trying out this app", id: "feedback-sound-adult",
          on: session.soundAdultConfirmed
        ) {
          soundCancelled = false
          session.soundAdultConfirmed.toggle()
        }
        checkbox(
          "Compare sounds on this computer", id: "feedback-sound-opt-in",
          on: session.soundProcessingEnabled
        ) {
          soundCancelled = false
          session.soundProcessingEnabled.toggle()
        }
        .disabled(!session.soundAdultConfirmed)
        .accessibilityHint(session.soundAdultConfirmed ? "" : "Turn on the adult option first.")
        Text(
          "The adult option only describes who's practicing; it doesn't verify age or record consent. Changing either option clears the current recording but keeps word check settings. Nothing is sent until you tap Check sound."
        )
        .font(.footnote)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("feedback-sound-setup-note")
      }
      .disabled(!setupEditable || session.isFinalizingPractice)
    }

    // MARK: Listening

    /// Example playback is independent of results; an owned cleanup issue stays visible without metadata.
    /// Held playback outranks a file failure; the two are never shown together.
    private var exampleStatus: Status? {
      guard session.example != nil || session.exampleCleanupBlocked else { return nil }
      switch playbackControl(.example) {
      case .blocked:
        return Status(
          id: "playback-blocked", title: Self.playbackBlockedTitle,
          detail: Self.playbackBlockedDetail)
      case .stopping:
        return Status(id: "stopping", title: Self.stoppingPlayback)
      case .preparing:
        return Status(id: "starting", title: "Starting example…")
      case .idle, .loading, .playing:
        break
      }
      if session.exampleCleanupBlocked {
        return Status(
          id: "cleanup", title: "A temporary example couldn't be removed",
          detail:
            "Recording, replay and more examples are paused until it's removed."
            + (exampleOnlyCleanupIssue ? " You can retry removing it below." : "")
            + " Your recording and any results are unchanged."
        )
      }
      switch session.exampleState {
      case .idle:
        return Status(id: "idle", title: "")
      case .loading:
        return Status(id: "loading", title: "Loading example…")
      case .playing:
        return Status(id: "playing", title: "Playing example")
      case .failed(let error):
        return Status(
          id: "failed", title: "The example couldn't be played",
          detail: "\(error.userMessage) Your recording and any results are unchanged.")
      }
    }

    private var listeningCue: String? {
      ResearchPracticeFocus.cue(for: prompt, exampleAvailable: session.example != nil)
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
            .accessibilityIdentifier("feedback-example-generated")
        }
        if let cue = listeningCue {
          Text(cue)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-example-cue")
        }
        if example != nil {
          if control != .blocked {
            secondary(exampleButtonTitle(control), id: "feedback-example") {
              notePlaybackTap(.example)
              session.toggleExample()
            }
            // Starting follows canPlayExample; cancelling or stopping stays available until the
            // stop is requested. Another source must finish stopping before a new tap.
            .disabled(control == .stopping || !session.canPlayExample)
          }
          if control == .loading {
            ProgressView()
              .frame(maxWidth: .infinity, minHeight: 44)
              .accessibilityLabel("Loading example")
              .accessibilityIdentifier("feedback-example-progress")
          }
        }
        if let status = exampleStatus, status.id != "idle", status.id != "loading" {
          VStack(alignment: .leading, spacing: 4) {
            Text(status.title).font(.subheadline.weight(.medium))
            if let detail = status.detail { Text(detail).font(.subheadline) }
          }
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityElement(children: .combine)
          .accessibilityIdentifier("feedback-example-state-\(status.id)")
        }
        if exampleOnlyCleanupIssue {
          recoveryControls(id: "feedback-example-cleanup")
        }
        if let example {
          Text(
            example.isGeneratedFixture
              ? "This example is generated local PCM test audio. No human spoke it, and it isn't loaded from the service. It plays from a short-lived file on this device, kept apart from your own recording. It's removed after playback has stopped."
              : "Play example loads a public recording from the service on this computer into a short-lived file on this device, kept apart from your own recording. Your recording isn't sent, and the check options aren't needed. It's removed after playback has stopped."
          )
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("feedback-example-note")
          exampleCredit(example)
        } else {
          Text("Example recording isn’t available for this word.")
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-example-unavailable")
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
      .accessibilityIdentifier("feedback-example-credit")
    }

    // MARK: Actions

    @ViewBuilder private var actions: some View {
      if unifiedRecovery {
        recoveryControls(id: "feedback-retry-audio-cleanup")
      }
      if completionStatus != nil {
        completionActions
      } else {
        takeActions
      }
    }

    /// Finishing has no take actions; Close stays available above.
    private var completionActions: some View {
      VStack(alignment: .leading, spacing: 12) {
        if session.isFinalizingPractice {
          ProgressView()
            .frame(maxWidth: .infinity, minHeight: 44)
            .accessibilityLabel("Finishing practice")
            .accessibilityIdentifier("feedback-finishing-practice")
        } else {
          if layout.retrySave {
            Button("Retry saving") { Task { await session.retryPracticeSave() } }
              .buttonStyle(DirectPracticeButtonStyle())
              .disabled(!session.canRetryPracticeSave)
              .accessibilityIdentifier("feedback-retry-saving")
          }
          Button("Practice again") {
            soundCancelled = false
            Task { await session.practiceAgain() }
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: layout.retrySave))
          .disabled(!session.canPracticeAgain)
          .accessibilityIdentifier("feedback-practice-again")
          if phaseEditable {
            secondary("Next word", id: "feedback-next") { advance() }
              .disabled(session.isProcessing || session.isPreparingAnotherTry || audioHeld)
          }
        }
        Text(
          "Recent practice keeps only the date, the sound and one practiced word, however many tries. No recordings or check results are kept. It counts practice, not how the word sounded."
        )
        .font(.subheadline)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("feedback-practice-completion-note")
      }
    }

    private var takeActions: some View {
      VStack(alignment: .leading, spacing: 12) {
        primary
        if session.phase == .review && layout.check && layout.anotherTry && !recordingUnavailable {
          secondary("Record another try", id: "feedback-record-another") { recordAnotherTry() }
            .disabled(!session.canRecordAnotherTry)
        }
        replays
        if let note = triesNote {
          Text(note)
            .font(.subheadline)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedback-tries-note")
        }
        // Explicit only; checks and replays never finish practice.
        if layout.finish {
          Button("Finish practice") {
            soundCancelled = false
            Task { await session.finishPractice() }
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .disabled(!session.canFinishPractice)
          .accessibilityIdentifier("feedback-finish-practice")
        }
        if ((session.phase == .review && layout.check) || retakeIsSecondary)
          && !recordingUnavailable
        {
          secondary(
            session.earlierReplay == nil ? "Retake" : "Clear both tries", id: "feedback-retake"
          ) { retake() }
          .disabled(session.isProcessing || session.isPreparingAnotherTry || audioHeld)
        }
        if session.phase == .permissionDenied && !recordingUnavailable {
          secondary("Open Settings", id: "feedback-settings") {
            if let url = URL(string: UIApplication.openSettingsURLString) {
              UIApplication.shared.open(url)
            }
          }
        }
        if phaseEditable {
          secondary("Next word", id: "feedback-next") { advance() }
            .disabled(session.isProcessing || session.isPreparingAnotherTry || audioHeld)
        }
      }
    }

    /// Another try leads once a try is retained, so the destructive Retake isn't the obvious tap.
    private var anotherTryLeads: Bool {
      session.isPreparingAnotherTry || layout.anotherTry
    }

    private var retakeIsSecondary: Bool {
      switch session.phase {
      case .review, .feedback, .failed: anotherTryLeads
      case .ready, .permissionDenied: session.latestReplay != nil && anotherTryLeads
      default: false
      }
    }

    @ViewBuilder private var anotherTry: some View {
      if session.isPreparingAnotherTry {
        ProgressView()
          .frame(maxWidth: .infinity, minHeight: 44)
          .accessibilityLabel("Getting ready for another try")
          .accessibilityIdentifier("feedback-another-try-progress")
      } else {
        Button("Record another try") { recordAnotherTry() }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(!session.canRecordAnotherTry)
          .accessibilityIdentifier("feedback-record-another")
      }
    }

    // MARK: Replay

    /// The retained recording names: "this try" for one fresh take, earlier/latest for two, and
    /// "previous recording" when a new try didn't produce a recording.
    private func replayName(_ source: ResearchFeedbackReplaySource) -> String {
      let latestIsCurrent = session.latestReplay?.isCurrentTake ?? false
      switch source {
      case .earlier: return "earlier try"
      case .latest where session.earlierReplay == nil:
        return latestIsCurrent ? "this try" : "previous recording"
      case .latest: return latestIsCurrent ? "latest try" : "most recent recording"
      }
    }

    private func replayVisible(_ source: ResearchFeedbackReplaySource) -> Bool {
      let clip = source == .earlier ? session.earlierReplay : session.latestReplay
      guard clip != nil, playbackControl(.replay(source)) != .blocked else { return false }
      // Replay stays in place, disabled, while a sound comparison borrows the take or any
      // playback is starting, playing or stopping.
      let audioBusy =
        session.audioTransitionPending
        || (session.playbackState != .idle && !session.playbackCleanupBlocked)
      return session.canReplay(source) || session.isCheckingSound || audioBusy
    }

    private func replayButton(_ source: ResearchFeedbackReplaySource) -> some View {
      let name = replayName(source)
      let control = playbackControl(.replay(source))
      let single = source == .latest && session.earlierReplay == nil
      let title =
        switch control {
        case .loading, .preparing: single ? "Cancel replay" : "Cancel \(name)"
        case .playing: single ? "Stop replay" : "Stop \(name)"
        case .stopping: "Stopping…"
        case .idle, .blocked: single ? "Replay \(name)" : "Play \(name)"
        }
      return secondary(
        title, id: source == .earlier ? "feedback-replay-earlier" : "feedback-replay"
      ) {
        notePlaybackTap(.replay(source))
        Task { @MainActor in await session.togglePlayback(source) }
      }
      .disabled(control == .stopping || !session.canReplay(source))
    }

    /// One shared line while a replay starts or stops; "Playing" waits for the acknowledgement.
    private var replayPlaybackStatus: String? {
      guard case .replay(let source) = playbackOwner else { return nil }
      switch playbackControl(.replay(source)) {
      case .loading, .preparing: return "Starting playback…"
      case .stopping: return Self.stoppingPlayback
      case .idle, .playing, .blocked: return nil
      }
    }

    @ViewBuilder private var replays: some View {
      if replayVisible(.earlier) { replayButton(.earlier) }
      if replayVisible(.latest) { replayButton(.latest) }
      if let status = replayPlaybackStatus {
        Text(status)
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("feedback-playback-status")
      } else if session.earlierReplay != nil, let source = session.playingReplaySource {
        Text("Playing \(replayName(source))")
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier(
            source == .earlier
              ? "feedback-replay-earlier-playing" : "feedback-replay-latest-playing")
      }
      if session.earlierReplay != nil, let source = session.failedReplaySource {
        Text("The \(replayName(source)) didn't play. Both recordings are still here.")
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier(
            source == .earlier ? "feedback-replay-earlier-failed" : "feedback-replay-latest-failed")
      } else if session.playbackFailed || session.failedReplaySource != nil {
        Text(
          recordingUnavailable
            ? "Replay didn't work." : "Replay didn't work. You can record again."
        )
        .font(.subheadline)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("feedback-replay-failed")
      }
    }

    /// Retention is for listening back only; tries aren't compared or ranked.
    private var triesNote: String? {
      guard let latest = session.latestReplay, !session.isPreparingAnotherTry,
        session.phase != .requestingPermission, session.phase != .recording,
        session.phase != .cleanupBlocked, session.phase != .ended
      else { return nil }
      switch session.playbackState {
      case .stopping, .cleanupBlocked: return nil
      case .idle, .preparing, .playing: break
      }
      if !latest.isCurrentTake {
        return
          "Your previous recording is kept for replay. It can't be checked again; checks need a new recording."
      }
      if session.earlierReplay != nil {
        return
          "Both tries stay on this device so you can listen back. Only the latest try can be checked. Recording another try replaces the earlier one."
      }
      return layout.anotherTry
        ? "Record another try to keep this one for listening back. Only the newest try can be checked."
        : nil
    }

    @ViewBuilder private var primary: some View {
      switch session.phase {
      // When recording is unavailable, the status explains Close instead of a dead Record/Retake.
      case .ready where recordingUnavailable, .permissionDenied where recordingUnavailable,
        .failed where recordingUnavailable:
        EmptyView()
      case .ready where session.latestReplay != nil && anotherTryLeads,
        .permissionDenied where session.latestReplay != nil && anotherTryLeads:
        anotherTry
      case .ready, .permissionDenied:
        Button("Record") {
          soundCancelled = false
          Task { await session.startRecording() }
        }
        .buttonStyle(DirectPracticeButtonStyle())
        .disabled(prompt == nil || !session.canRecord)
        .accessibilityIdentifier("feedback-record")
      case .requestingPermission:
        ProgressView()
          .frame(maxWidth: .infinity, minHeight: 44)
          .accessibilityLabel("Waiting for microphone permission")
          .accessibilityIdentifier("feedback-permission-progress")
      case .recording:
        Button("Stop") { session.stopRecording() }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("feedback-stop")
      case .review where layout.check:
        Button("Check word") { session.checkRecording() }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(!session.canCheck)
          .accessibilityIdentifier("feedback-check")
      case .review where anotherTryLeads, .feedback where anotherTryLeads,
        .failed where anotherTryLeads:
        anotherTry
      case .review, .feedback, .failed:
        Button("Retake") { retake() }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(session.isProcessing || audioHeld)
          .accessibilityIdentifier("feedback-retake")
      case .checking:
        ProgressView()
          .frame(maxWidth: .infinity, minHeight: 44)
          .accessibilityLabel("Checking the word")
          .accessibilityIdentifier("feedback-checking-progress")
        Button("Cancel check") { session.cancelChecking() }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .disabled(session.audioTransitionPending)
          .accessibilityIdentifier("feedback-cancel")
      case .cleanupBlocked, .ended:
        EmptyView()
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
