#if DEBUG && targetEnvironment(simulator)
  import Accessibility
  import AVFoundation
  import SwiftUI

  /// Presentation of the actual sound session; no model inference or fixture route lives here.
  struct ResearchSoundPreviewView: View {
    private let isGeneratedUITest: Bool
    @StateObject private var session: ResearchSoundSession
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 64
    @AccessibilityFocusState private var statusFocused: Bool
    @AccessibilityFocusState private var retryFocused: Bool
    @State private var wasInterrupted = false
    @State private var wasCancelled = false

    init(session: ResearchSoundSession? = nil) {
      let fixture = ResearchSoundUITestFixtures.selected()
      isGeneratedUITest = fixture != nil
      _session = StateObject(
        wrappedValue: session ?? fixture.map { ResearchSoundUITestFixtures.session(for: $0) }
          ?? ResearchSoundSession())
    }
    private var presentation: ResearchSoundPresentation {
      if session.canRetryPlaybackCleanup {
        return .init(
          id: "playback-blocked", title: "Playback hasn't confirmed it stopped",
          detail:
            "Recording, checks and other audio stay paused until it does. Your recordings and any results are unchanged."
        )
      }
      if session.recordingUnavailable {
        return .init(
          id: "recording-unavailable", title: "Recording isn't available in this visit",
          detail: "Temporary-file cleanup could not finish. Close this screen and try again later.")
      }
      if session.captureHardwareBlocked {
        return .init(
          id: "capture-cleanup", title: "Microphone cleanup isn't confirmed",
          detail:
            "Recording and checks stay paused until cleanup finishes. Retry microphone cleanup.")
      }
      return .make(
        phase: session.phase, paused: session.sharedProcessingPaused, canCheck: session.canCheck,
        setupEnabled: session.adultConfirmed && session.processingOptIn,
        captureLimitReached: session.attemptsStarted >= 128,
        interrupted: wasInterrupted, cancelled: wasCancelled)
    }
    var body: some View {
      ScrollView {
        ScrollViewReader { proxy in
          VStack(alignment: .leading, spacing: 24) {
            if let note = session.closeNote {
              Text(note).font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
                .fixedSize(horizontal: false, vertical: true)
                .id("sound-close-note")
                .accessibilityIdentifier("sound-close-note")
            }
            Text("Sound preview")
              .font(.system(.largeTitle, design: .serif))
              .accessibilityAddTraits(.isHeader)
              .accessibilityIdentifier("sound-title")
            PracticeRule()
            Text("bread")
              .font(.system(size: wordSize, design: .serif))
              .lineLimit(1).minimumScaleFactor(0.4)
              .accessibilityIdentifier("sound-word")
            Text(
              "Adult engineering preview. Compares your whole recording of “bread” with four versions: BR, BW, BL, and B without the R."
            )
            .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("sound-scope")
            VStack(alignment: .leading, spacing: 8) {
              Text(presentation.title)
                .font(.title2.weight(.medium))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityLabel(presentation.spokenTitle)
                .accessibilityIdentifier("sound-state-" + presentation.id)
                .accessibilityFocused($statusFocused)
              if !presentation.detail.isEmpty {
                Text(presentation.detail).font(.body)
                  .fixedSize(horizontal: false, vertical: true)
                  .accessibilityIdentifier("sound-detail")
              }
            }
            if presentation.modelResult {
              Text(ResearchSoundPresentation.limitation).font(.body)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("sound-limit")
            }
            actions
            if presentation.modelResult {
              Text("To compare again, record a fresh take.").font(.body)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("sound-next")
            }
            PracticeRule()
            setup
            Text(
              "This simulator build compares sounds with the local service at 127.0.0.1:8793, the same service Speech practice uses for its word checks and sound comparisons. This screen keeps its own separate recording and session: nothing here is shared with Speech practice, and its results don't change word checks. Your current recording stays temporarily on this device so you can replay it, and is removed after replay stops, when you record again, change an option, close this screen or leave the app. Check sound sends the recording to the service, which makes its own temporary copy. If that copy can't be confirmed removed, it may remain on this computer, and checks from this screen pause. Nothing here is saved to practice history."
            )
            .font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("sound-note")
          }
          .padding(24)
          .frame(maxWidth: 560, alignment: .leading)
          .frame(maxWidth: .infinity)
          .onChange(of: session.closeNote) { _, note in
            guard let note else { return }
            proxy.scrollTo("sound-close-note", anchor: .top)
            AccessibilityNotification.Announcement(note).post()
          }
        }
      }
      .background(DirectPracticeStyle.canvas.ignoresSafeArea())
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
      .toolbar(.hidden, for: .navigationBar)
      .safeAreaInset(edge: .top, spacing: 0) {
        VStack(spacing: 0) {
          HStack {
            Button("Close") {
              let cleanup = session.end()
              Task { _ = await cleanup.value }
            }
            .font(.body).buttonStyle(.plain)
            .frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
            .accessibilityIdentifier("sound-close")
            Spacer()
          }.padding(.horizontal, 24)
          if isGeneratedUITest {
            Text("Generated UI test · no microphone or model")
              .font(.footnote).fixedSize(horizontal: false, vertical: true)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.horizontal, 24).padding(.bottom, 8)
              .accessibilityIdentifier("sound-ui-test-banner")
          }
          PracticeRule()
        }.background(DirectPracticeStyle.canvas)
      }
      .interactiveDismissDisabled(session.dismissalBlocked)
      .onDisappear { session.end() }
      .onChange(of: session.phase) { _, phase in
        if phase == .ended, session.pendingClose { dismiss() }
      }
      .onChange(of: session.isPlaying) { _, playing in
        if playing { AccessibilityNotification.Announcement("Playing.").post() }
      }
      .onChange(of: session.stoppedPlaybackEvents) { _, _ in
        AccessibilityNotification.Announcement("Playback stopped.").post()
      }
      .onChange(of: session.audioBusy) { _, busy in
        if busy {
          AccessibilityNotification.Announcement(
            "Audio from another screen is still stopping. Try again once it has stopped."
          ).post()
        }
      }
      .onChange(of: session.playbackState) { _, state in
        switch state {
        case .stopping:
          AccessibilityNotification.Announcement("Stopping playback.").post()
        case .cleanupBlocked:
          AccessibilityNotification.Announcement(
            "Playback hasn't confirmed it stopped. Retry stopping is available."
          ).post()
          retryFocused = true
        default: break
        }
      }
      .onChange(of: scenePhase) { _, value in
        if value == .active {
          session.appDidBecomeActive()
        } else {
          wasInterrupted = session.summary != nil || session.phase == .recording
          if value == .background {
            session.appDidEnterBackground()
          } else {
            session.appDidBecomeInactive()
          }
        }
      }
      .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification))
      { note in
        if let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
          AVAudioSession.InterruptionType(rawValue: raw) == .began
        {
          wasInterrupted = session.summary != nil || session.phase == .recording
          session.audioWasInterrupted()
        }
      }
      .onChange(of: presentation.title) { _, _ in
        AccessibilityNotification.Announcement(presentation.announcement).post()
        if presentation.modelResult { statusFocused = true }
      }
    }
    private var setupEditable: Bool {
      guard !session.actionsPaused else { return false }
      return switch session.phase {
      case .requestingPermission, .recording, .checking, .localCleanupBlocked, .ended: false
      default: true
      }
    }
    private var setup: some View {
      VStack(alignment: .leading, spacing: 12) {
        checkbox("I'm an adult trying out this app", id: "sound-adult", on: session.adultConfirmed)
        {
          session.adultConfirmed.toggle()
          settingsAnnouncement()
        }
        checkbox("Compare sounds on this computer", id: "sound-optin", on: session.processingOptIn)
        {
          session.processingOptIn.toggle()
          settingsAnnouncement()
        }
        .disabled(!session.adultConfirmed)
        .accessibilityHint(session.adultConfirmed ? "" : "Turn on the adult option first.")
        Text(
          "The adult option only describes who's trying this; it doesn't verify age or record consent. Changing either option clears the current recording. Word check settings are separate."
            + (!session.adultConfirmed
              ? " Turn on the adult option first."
              : !session.processingOptIn ? " Nothing is sent until you tap Check sound." : "")
        )
        .font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("sound-setup-note")
      }.disabled(!setupEditable)
    }
    private func settingsAnnouncement() {
      wasInterrupted = false
      wasCancelled = false
      AccessibilityNotification.Announcement(
        "Sound settings changed. Record a fresh take after turning on both options."
      ).post()
    }
    private func checkbox(_ title: String, id: String, on: Bool, action: @escaping () -> Void)
      -> some View
    {
      Button(action: action) {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
          Image(systemName: on ? "checkmark.square" : "square").accessibilityHidden(true)
          Text(title).fixedSize(horizontal: false, vertical: true).layoutPriority(1)
          Spacer(minLength: 0)
        }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
      }.buttonStyle(.plain)
        .accessibilityAddTraits(.isToggle).accessibilityValue(on ? "On" : "Off")
        .accessibilityIdentifier(id)
    }
    private var actions: some View {
      VStack(alignment: .leading, spacing: 12) {
        switch session.phase {
        case .requestingPermission:
          ProgressView("Waiting for microphone permission").accessibilityIdentifier(
            "sound-permission-progress")
        case .recording:
          primary("Stop", id: "sound-stop") { session.stopRecording() }
        case .checking:
          ProgressView("Comparing sounds").accessibilityIdentifier("sound-checking-progress")
          secondary("Cancel check", id: "sound-cancel") {
            session.cancelChecking()
            wasCancelled = true
          }
        case .localCleanupBlocked, .ended: EmptyView()
        default:
          if session.hasRecording, session.adultConfirmed, session.processingOptIn {
            primary("Check sound", id: "sound-check") {
              wasCancelled = false
              session.checkRecording()
            }.disabled(!session.canCheck)
          } else if session.hasRecording {
            primary("Retake", id: "sound-retake") { retake() }.disabled(session.actionsPaused)
          } else {
            primary("Record", id: "sound-record") {
              wasInterrupted = false
              wasCancelled = false
              Task { await session.startRecording() }
            }.disabled(!session.canRecord)
          }
        }
        if session.canRetryPlaybackCleanup {
          secondary("Retry stopping", id: "sound-replay-retry-stop") {
            Task { await session.retryPlaybackCleanup() }
          }.accessibilityHint("Asks playback to stop again.")
            .accessibilityFocused($retryFocused)
        } else if session.hasRecording {
          secondary(replayLabel, id: "sound-replay") {
            Task { await session.togglePlayback() }
          }.disabled(!session.playbackPending && !session.canReplay)
        }
        if session.hasRecording, session.adultConfirmed, session.processingOptIn {
          secondary("Retake", id: "sound-retake") { retake() }
            .disabled(session.actionsPaused)
        }
        if let status = playbackStatus {
          Text(status).font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("sound-replay-status")
        }
        if session.captureHardwareBlocked {
          Text("Microphone cleanup isn't confirmed. Recording and checks stay paused.")
            .font(.subheadline).fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("sound-capture-cleanup-status")
          secondary("Retry microphone cleanup", id: "sound-capture-retry-cleanup") {
            Task { await session.retryCaptureCleanup() }
          }
        } else if session.captureFileBlocked, !session.playbackPending {
          secondary("Retry recording cleanup", id: "sound-recording-retry-cleanup") {
            Task { await session.retryCaptureCleanup() }
          }
        }
        if session.playbackFailed {
          Text("Replay didn't work. You can record again.")
            .font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(
              "sound-replay-failed")
        }
        if session.phase == .permissionDenied {
          secondary("Open Settings", id: "sound-settings") {
            if let url = URL(string: UIApplication.openSettingsURLString) {
              UIApplication.shared.open(url)
            }
          }
        }
      }
    }
    private func retake() {
      wasInterrupted = false
      wasCancelled = false
      let cleanup = session.retake()
      Task { _ = await cleanup.value }
    }
    private var replayLabel: String {
      switch session.playbackState {
      case .preparing: "Cancel replay"
      case .playing: session.isPlaying ? "Stop replay" : "Cancel replay"
      case .stopping: "Stopping…"
      case .idle, .cleanupBlocked: "Replay"
      }
    }
    private var playbackStatus: String? {
      switch session.playbackState {
      case .preparing: "Starting playback…"
      case .stopping: "Stopping playback. Other actions return once it has stopped."
      case .cleanupBlocked:
        "Playback hasn't confirmed it stopped. Recording, checks and other audio stay paused until it does. Your recordings and any results are unchanged."
      default:
        session.audioBusy
          ? "Audio from another screen is still stopping. Try again once it has stopped." : nil
      }
    }
    private func primary(_ title: String, id: String, action: @escaping () -> Void) -> some View {
      Button(title, action: action).buttonStyle(DirectPracticeButtonStyle())
        .accessibilityIdentifier(id)
    }
    private func secondary(_ title: String, id: String, action: @escaping () -> Void) -> some View {
      Button(title, action: action).font(.body)
        .frame(maxWidth: .infinity, minHeight: 44).contentShape(Rectangle())
        .overlay(Rectangle().stroke(DirectPracticeStyle.border, lineWidth: 1))
        .buttonStyle(.plain).accessibilityIdentifier(id)
    }
  }

  /// Fixed presentation mapping shared by actual rendering and focused copy tests.
  struct ResearchSoundPresentation: Equatable {
    let id: String
    let title: String
    let detail: String
    var modelResult = false
    var spokenTitle: String {
      title.replacingOccurrences(of: ": BR", with: ": B R version").replacingOccurrences(
        of: ": BW", with: ": B W version")
    }
    var announcement: String {
      modelResult
        ? "Sound comparison: \(spokenTitle). This doesn't show whether bread was said correctly."
        : spokenTitle
    }
    static let limitation =
      "This compares the whole recording, not the R on its own. It doesn't show which sound you said or whether “bread” was said correctly. It hasn't been checked against real recordings independently confirmed to use W in place of R, and it isn't validated for children."
    static func make(
      phase: ResearchSoundPhase, paused: Bool, canCheck: Bool, setupEnabled: Bool = false,
      captureLimitReached: Bool = false,
      interrupted: Bool = false, cancelled: Bool = false
    ) -> Self {
      if phase == .localCleanupBlocked {
        return .init(
          id: "cleanup", title: "A recording on this device couldn't be removed",
          detail:
            "Recording on this device could not be confirmed removed. Recording and checks are paused. Retry recording cleanup. Close can leave on a second tap only after audio stops and file recovery is available."
        )
      }
      if phase == .ended { return .init(id: "ended", title: "Sound preview closed", detail: "") }
      if captureLimitReached && (phase == .ready || phase == .permissionDenied) {
        return .init(
          id: "recording-limit", title: "Sound preview recording limit reached",
          detail:
            "This preview cannot start more recordings. Replay is still available for a held recording. Close this screen when you're done."
        )
      }
      if paused && phase != .recording && phase != .requestingPermission {
        return .init(
          id: "paused", title: "Checks in the sound service are paused",
          detail:
            "The service on this computer can't process recordings safely right now. A temporary copy may remain there. Checks stay paused for the rest of this session. You can still record and replay."
        )
      }
      switch phase {
      case .ready:
        if cancelled {
          return .init(
            id: "ready-cancelled", title: "Comparison cancelled",
            detail:
              "No result will be shown for that recording. The computer may still finish the check in the background. Record a fresh take to compare again."
          )
        }
        if interrupted {
          return .init(
            id: "ready-cleared", title: "Recording removed",
            detail:
              "The app was interrupted, so your recording was removed. Tap Record to try again.")
        }
        return .init(
          id: "ready", title: "Ready to record",
          detail:
            "Tap Record and say “bread”. Recording stops after 4 seconds."
            + (setupEnabled ? "" : " To compare sounds, turn on both options below first.")
        )
      case .requestingPermission:
        return .init(id: "permission", title: "Getting the microphone ready…", detail: "")
      case .recording:
        return .init(
          id: "recording", title: "Recording",
          detail: "Say “bread”, then tap Stop. Recording stops on its own after 4 seconds.")
      case .review:
        return .init(
          id: canCheck ? "review" : "review-off", title: "Recording ready",
          detail: canCheck
            ? "Replay it, record again or tap Check sound. Each recording can be compared once."
            : "Replay it or record again. To compare sounds, turn on both options below, then record again."
        )
      case .checking:
        return .init(
          id: "checking", title: "Comparing sounds on this computer…",
          detail: "This usually takes a few seconds. You can cancel.")
      case .permissionDenied:
        return .init(
          id: "denied", title: "Microphone access is off",
          detail: "Allow microphone access in Settings, then try again.")
      case .observation(let observation):
        if observation.status == .inconclusive {
          return .init(
            id: "result-no-clear-pick", title: "No clear pick",
            detail:
              "The model couldn't tell the tested versions apart for this recording, or the recording didn't fit any of them well.",
            modelResult: true)
        }
        if observation.status == .observedModelPreference {
          switch observation.preference {
          case .rPath:
            return .init(
              id: "result-br", title: "Model's best fit: BR",
              detail:
                "Of the four tested versions, the experimental sound model fit this recording best to BR, as in “bread”.",
              modelResult: true)
          case .wPath:
            return .init(
              id: "result-bw", title: "Model's best fit: BW",
              detail:
                "Of the four tested versions, the experimental sound model fit this recording best to BW.",
              modelResult: true)
          case .otherPath:
            return .init(
              id: "result-other", title: "Model's best fit: another version",
              detail:
                "Of the four tested versions, the model fit this recording best to BL, or to B followed directly by the rest of the word.",
              modelResult: true)
          case nil: return error(.invalidResponse)
          }
        }
        if ["attempt_limit", "context_limit"].contains(observation.reason) {
          return .init(
            id: "error-limit", title: "Sound preview limit reached",
            detail:
              "The service cannot accept more checks in this preview. Recording and replay still work."
          )
        }
        if ["capture_already_checked", "attempt_already_checked"].contains(observation.reason) {
          return .init(
            id: "error-already-checked", title: "This recording was already checked",
            detail: "This recording was already checked. Record a fresh take.")
        }
        if observation.reason == "busy" {
          return .init(
            id: "error-busy", title: "No sound comparison result",
            detail:
              "The computer was busy with another check, so this recording wasn't compared. Record again to try another comparison."
          )
        }
        if observation.reason == "timeout" { return error(.timeout) }
        return .init(
          id: "error-unfinished", title: "No sound comparison result",
          detail: "The comparison didn't finish, so there's no result.")
      case .failed(let code): return error(code)
      case .localCleanupBlocked, .ended:
        return .init(id: "ended", title: "Sound preview closed", detail: "")
      }
    }
    private static func error(_ code: RecordingFeedbackError) -> Self {
      switch code {
      case .invalidResponse:
        .init(
          id: "error-unverified", title: "No sound comparison result",
          detail: "The reply couldn't be verified, so no result is shown.")
      case .serviceUnavailable:
        .init(
          id: "error-unreachable", title: "The sound service isn't reachable",
          detail: "Make sure it's running at 127.0.0.1:8793. Recording and replay still work.")
      case .timeout:
        .init(
          id: "error-timeout", title: "No sound comparison result",
          detail: "The comparison took too long and was stopped.")
      case .invalidRecording:
        .init(
          id: "error-recording", title: "This recording couldn't be used",
          detail: "Record “bread” again.")
      default:
        .init(
          id: "error-unfinished", title: "No sound comparison result",
          detail: "The comparison didn't finish, so there's no result.")
      }
    }
  }
#endif
