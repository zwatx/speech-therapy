import AVFoundation
import Accessibility
import SwiftUI
import UIKit

/// The app home with sound check and practice sessions over it. Recording and replay are real
/// and local; outcomes are scripted (see CACDemoModel.swift). The coordinator owns every media session;
/// child views call the session's own actions and never end or replace it.
struct CACDemoView: View {
  @StateObject private var coordinator: CACDemoCoordinator
  @Environment(\.dismiss) private var dismiss
  @Environment(\.scenePhase) private var scenePhase
  @Environment(\.refreshAudioCleanupRecovery) private var refreshCleanupRecovery
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  /// `.modal` for the legacy full-screen cover; `.root` when this is the app's first screen.
  init(placement: CACDemoCoordinator.Placement = .modal) {
    _coordinator = StateObject(wrappedValue: CACDemoCoordinator.standard(placement: placement))
  }

  init(coordinator: CACDemoCoordinator) {
    _coordinator = StateObject(wrappedValue: coordinator)
  }

  var body: some View {
    ZStack {
      CACHomeView(coordinator: coordinator, face: coordinator.facePreview)
        .accessibilityHidden(inSession)
      if inSession {
        session
          .transition(reduceMotion ? .opacity : .move(edge: .bottom))
          .zIndex(1)
      }
    }
    .animation(reduceMotion ? .easeInOut(duration: 0.2) : .smooth(duration: 0.4), value: inSession)
    .foregroundStyle(CACDemoStyle.ink)
    .overlay(alignment: .topLeading) { verificationMarker }
    // Exit is the only way out, so it can wait for the owner's own cleanup.
    .interactiveDismissDisabled(true)
    .onAppear { coordinator.forwardScene(scenePhase) }
    .onChange(of: scenePhase) { _, phase in coordinator.forwardScene(phase) }
    .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) {
      notification in
      if let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
        AVAudioSession.InterruptionType(rawValue: raw) == .began
      {
        coordinator.audioWasInterrupted()
      }
    }
    .onDisappear { coordinator.viewDisappeared() }
    // Passive re-read so a root-level recovery notice reflects any file a true exit left.
    .onChange(of: coordinator.stage) { _, _ in refreshCleanupRecovery() }
    .onChange(of: coordinator.finished) { _, finished in
      if finished { dismiss() }
    }
  }

  private var inSession: Bool { coordinator.stage == .word }

  /// Lets UI automation prove inert hardware is in use before it taps Record.
  @ViewBuilder
  private var verificationMarker: some View {
    #if CAC_FLOW_UI_VERIFICATION && targetEnvironment(simulator)
      if CACFlowVerification.isRequested {
        Color.clear
          .frame(width: 1, height: 1)
          .accessibilityElement()
          .accessibilityLabel("Verification host")
          .accessibilityIdentifier("cadence.cac-demo.verification-host")
      }
    #endif
  }

  /// A sound check or practice session, covering the home and its tab bar.
  private var session: some View {
    VStack(spacing: 0) {
      CACSessionHeader(coordinator: coordinator)
      if let session = coordinator.session, let word = coordinator.current {
        CACWordView(
          session: session, coordinator: coordinator, face: coordinator.facePreview, word: word
        )
        // Fresh announcement state per owner; the owner itself lives in the coordinator.
        .id(ObjectIdentifier(session))
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      } else {
        Spacer()
      }
    }
    .background(CACDemoStyle.background.ignoresSafeArea())
    .tint(CACDemoStyle.accent)
  }
}

// MARK: - Session header

/// Close, the session's name and its place in the session. Practice and its recheck are one
/// session; the sound check is another.
private struct CACSessionHeader: View {
  @ObservedObject var coordinator: CACDemoCoordinator
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  private var words: [CACScriptedWord] {
    guard let current = coordinator.current else { return [] }
    if current.part == .soundCheck { return coordinator.soundCheck }
    guard let plan = coordinator.plan else { return [current] }
    return plan.practice + [plan.recheck]
  }

  private var position: (index: Int, count: Int)? {
    guard let current = coordinator.current,
      let index = words.firstIndex(where: { $0.id == current.id })
    else { return nil }
    return (index + 1, words.count)
  }

  private var title: String {
    guard let current = coordinator.current else { return "" }
    if current.part == .soundCheck { return CACJourneyPart.soundCheck.title }
    return "\(coordinator.plan?.letter ?? current.letter) practice"
  }

  var body: some View {
    VStack(spacing: 12) {
      HStack(spacing: 12) {
        Button {
          Task { await coordinator.close() }
        } label: {
          Image(systemName: "xmark")
            .font(.body.weight(.semibold))
            .frame(width: 44, height: 44)
            .background(CACDemoStyle.surface, in: Circle())
            .overlay(Circle().strokeBorder(CACDemoStyle.separator))
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(CACDemoStyle.ink)
        .accessibilityLabel(coordinator.placement == .modal ? "Close" : "End session")
        .accessibilityIdentifier("cadence.cac-demo.close")
        Text(title)
          .font(.headline)
          .frame(maxWidth: .infinity)
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("cadence.cac-demo.session-title")
        Group {
          if let position {
            Text("\(position.index) of \(position.count)")
              .font(.subheadline.monospacedDigit())
              .foregroundStyle(CACDemoStyle.muted)
              .accessibilityLabel("Word \(position.index) of \(position.count)")
              .accessibilityIdentifier("cadence.cac-demo.counter")
          }
        }
        .frame(minWidth: 44, alignment: .trailing)
      }
      if let position, !dynamicTypeSize.isAccessibilitySize {
        CACSessionBar(index: position.index, count: position.count)
      }
    }
    .padding(.horizontal, 20)
    .padding(.top, 4)
    .padding(.bottom, 4)
    .frame(maxWidth: CACDemoStyle.maxWidth + 40)
    .frame(maxWidth: .infinity)
  }
}

/// One segment per word; finished and current words are filled.
private struct CACSessionBar: View {
  let index: Int
  let count: Int

  var body: some View {
    HStack(spacing: 4) {
      ForEach(1...max(count, 1), id: \.self) { step in
        Capsule()
          .fill(step <= index ? CACDemoStyle.accent : CACDemoStyle.separator)
          .frame(height: 4)
      }
    }
    .accessibilityHidden(true)
  }
}

// MARK: - Word

private struct CACWordView: View {
  @ObservedObject var session: DirectPracticeSession
  @ObservedObject var coordinator: CACDemoCoordinator
  @ObservedObject var face: FaceGuideModel
  let word: CACScriptedWord
  @Environment(\.scenePhase) private var scenePhase
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  private enum Display: Equatable {
    case unavailable, ready, preparing, recording
    case review(checkable: Bool)
    case result(CACScriptedResult)
    case denied
    case failed(String)
    case leaving, held
  }

  private var display: Display {
    if coordinator.pendingDeparture != nil, !coordinator.isLeaving { return .held }
    if coordinator.isLeaving { return .leaving }
    switch session.phase {
    case .ready where session.recordingStartupUnavailable && session.tries.isEmpty:
      return .unavailable
    case .ready: return .ready
    case .requestingPermission: return .preparing
    case .recording: return .recording
    case .review:
      if let result = coordinator.currentResult { return .result(result) }
      // The coordinator's own gate: quiet takes may continue; empty audio may not.
      return .review(checkable: coordinator.currentRecordingCanBeChecked)
    case .permissionDenied: return .denied
    case .failed(let detail): return .failed(detail)
    case .completed, .ended: return .leaving
    }
  }

  var body: some View {
    CACPage {
      VStack(spacing: usesCompactWord ? 12 : 16) {
        if usesCompactWord {
          // The camera is the main surface; the word stays readable in a compact header.
          CACWordHeader(
            session: session, coordinator: coordinator, word: word, outcome: shownOutcome)
          facePanel
        } else {
          CACWordCard(session: session, coordinator: coordinator, word: word, outcome: shownOutcome)
        }
        if !showsRecordDock {
          stateContent
            .frame(maxWidth: .infinity)
        }
        maintenance
        if !usesCompactWord { facePanel }
        if word.part != .soundCheck,
          let guide = DirectPracticeSoundGuide.content(sound: word.sound, prompt: word.prompt)
        {
          DirectPracticeSoundGuideView(guide: guide)
            .padding(.horizontal, 16)
            .cacSurface()
        }
      }
    } actions: {
      actions
    }
    .onChange(of: session.phase) { old, phase in
      if phase == .ended { Task { await coordinator.resumeAfterEnd() } }
      announce(old: old, phase: phase)
    }
    .onChange(of: coordinator.currentResult) { _, result in
      if result != nil {
        AccessibilityNotification.Announcement(word.feedback.title).post()
      }
    }
    .onChange(of: session.playbackError) { _, error in
      if let error { AccessibilityNotification.Announcement(error).post() }
    }
  }

  private var shownOutcome: CACScriptedOutcome? {
    if case .result(let result) = display { return result.outcome }
    return nil
  }

  /// At ordinary text sizes, pin Record and Stop beside the word and camera.
  /// Accessibility text sizes use scrollable actions so larger labels stay reachable.
  private var showsRecordDock: Bool {
    switch display {
    case .ready, .preparing, .recording: true
    default: false
    }
  }

  // MARK: Face preview

  /// Compact word whenever the face panel can hold a camera or its recovery. Unsupported
  /// phones and a hidden, idle preview keep the large word card.
  private var usesCompactWord: Bool {
    guard face.phase != .unsupported else { return false }
    return coordinator.facePreviewEnabled || face.hasCameraOwner || face.permissionPending
      || face.cleanupBlocked
  }

  /// Camera and microphone stay independent: audio-only states still show camera recovery.
  private var facePanel: some View {
    FaceGuideInlinePreview(
      model: face,
      enabled: coordinator.facePreviewEnabled,
      canShow: coordinator.canShowFacePreview,
      compact: !liveWordLayout,
      show: { coordinator.showFacePreview() },
      hide: { coordinator.hideFacePreview() },
      retryStop: { retryCameraCleanup(coordinator) }
    )
  }

  /// Ready and recording keep the full camera; review and result give feedback the room.
  private var liveWordLayout: Bool {
    switch display {
    case .ready, .preparing, .recording, .unavailable, .denied: true
    case .review, .result, .failed, .leaving, .held: false
    }
  }

  // MARK: State content

  @ViewBuilder
  private var stateContent: some View {
    switch display {
    case .unavailable:
      CACNotice(
        icon: "exclamationmark.triangle",
        title: "Recording isn’t available",
        detail: "This phone’s saved recordings couldn’t be checked. Restart the app to try again.")
    case .ready, .preparing, .recording:
      EmptyView()
    case .review(let checkable):
      VStack(spacing: 14) {
        if !checkable {
          CACNotice(icon: "mic.badge.xmark", title: retryAdvice.title, detail: retryAdvice.detail)
            .accessibilityIdentifier("cadence.cac-demo.capture-retry")
        }
        playback
      }
    case .result(let result):
      VStack(spacing: 14) {
        CACFeedbackPanel(word: word, outcome: result.outcome)
        playback
      }
    case .denied:
      CACNotice(
        icon: "mic.slash",
        title: "Microphone access is off",
        detail: "Turn on the microphone for this app in Settings, then try again.")
    case .failed(let detail):
      CACNotice(icon: "exclamationmark.triangle", title: "That didn’t record", detail: detail)
    case .leaving:
      HStack(spacing: 10) {
        ProgressView().accessibilityHidden(true)
        Text("One moment…").foregroundStyle(CACDemoStyle.muted)
      }
      .frame(minHeight: 84)
    case .held:
      CACNotice(
        icon: "hourglass",
        title: "Finishing up",
        detail: session.closeNote ?? "This word’s recording hasn’t been removed yet. Try again."
      )
      .accessibilityIdentifier("cadence.cac-demo.close-note")
    }
  }

  private var retryAdvice: (title: String, detail: String) {
    if case .review(let summary, .retry(let coaching)) = session.phase {
      if DirectPracticeRecordingAdvice.suppressesQuietTip(
        summary: summary, assessment: .retry(coaching))
      {
        return ("No sound came through", "Keep the microphone uncovered and record again.")
      }
      return (coaching.title, coaching.detail)
    }
    return ("Let’s record that again", "Say the word clearly, then tap stop.")
  }

  @ViewBuilder
  private var playback: some View {
    if !session.hasPlaybackCleanupIssue, !session.isRetryingPlaybackCleanup,
      session.latestTry != nil
    {
      let idle = session.playbackState == .idle
      Button {
        Task { await session.togglePlayback() }
      } label: {
        Label(
          idle ? "Play your recording" : session.playbackControlLabel,
          systemImage: idle ? "play.fill" : "stop.fill")
      }
      .buttonStyle(CACCapsuleButtonStyle())
      // Stopping playback stays available; only starting it waits on the camera.
      .disabled(
        playbackIsStopping || session.spokenWordState != .idle
          || (session.isTransitioning && idle) || coordinator.isLeaving
          || (coordinator.recordingControlsBlockedForCamera && idle)
      )
      .accessibilityIdentifier("cadence.cac-demo.replay")
    }
  }

  private var playbackIsStopping: Bool {
    if case .stopping = session.playbackState { return true }
    return false
  }

  /// Recovery controls stay with the exact owner that needs them.
  @ViewBuilder
  private var maintenance: some View {
    if coordinator.pendingDeparture == nil {
      if session.hasPlaybackCleanupIssue || session.isRetryingPlaybackCleanup {
        CACMaintenanceRow(
          detail: session.playbackStatus ?? "Playback hasn’t confirmed it stopped.",
          action: "Retry stopping", enabled: session.canRetryCleanup
        ) { await session.retryCleanup() }
      } else if session.captureCleanupState.hasHardwareIssue
        || session.captureCleanupState.hasFileIssue || session.hasPendingFileCleanup
      {
        CACMaintenanceRow(
          detail: "A recording hasn’t been removed yet.", action: "Retry cleanup",
          enabled: session.canRetryCleanup
        ) { await session.retryCleanup() }
      }
      if let playbackError = session.playbackError {
        Text(playbackError)
          .font(.footnote)
          .foregroundStyle(CACDemoStyle.muted)
          .multilineTextAlignment(.center)
      }
    }
  }

  // MARK: Actions

  private var nextLabel: String {
    let last = coordinator.progress.map { $0.index == $0.count } ?? false
    guard last else { return "Next word" }
    switch word.part {
    case .soundCheck: return "See results"
    case .practice: return "Check “\(coordinator.plan?.recheck.word ?? word.word)” again"
    case .recheck: return "Finish"
    }
  }

  @ViewBuilder
  private var actions: some View {
    switch display {
    case .ready, .preparing:
      recordDock(
        title: display == .preparing ? "Getting the mic ready…" : "Tap to record",
        detail: display == .preparing
          ? nil
          : face.permissionPending
            ? "Choose whether to allow the camera first."
            : "Say “\(word.word)” once, then tap stop."
      ) {
        Button {
          Task { await coordinator.record() }
        } label: {
          Text("Record")
        }
        .buttonStyle(CACRecordButtonStyle(recording: false))
        .disabled(
          display == .preparing || !session.canStartRecording
            || coordinator.recordingControlsBlockedForCamera
        )
        .accessibilityLabel("Record")
        .accessibilityIdentifier("cadence.cac-demo.record")
      } level: {
        EmptyView()
      }
    case .recording:
      recordDock(title: "Listening…", detail: "Tap stop when you’re done.") {
        Button {
          session.stopRecording()
        } label: {
          Text("Stop")
        }
        .buttonStyle(CACRecordButtonStyle(recording: true))
        .accessibilityLabel("Stop recording")
        .accessibilityIdentifier("cadence.cac-demo.stop")
      } level: {
        TimelineView(.periodic(from: .now, by: 0.1)) { _ in
          CACLevelBar(power: scenePhase == .active ? session.recordingInputPower : nil)
        }
      }
    case .review(let checkable):
      if checkable {
        Button("Check pronunciation") { coordinator.check() }
          .buttonStyle(CACPrimaryButtonStyle(icon: "arrow.right"))
          .disabled(session.actionsDisabled || coordinator.recordingControlsBlockedForCamera)
          .accessibilityIdentifier("cadence.cac-demo.check")
        recordAgain(primary: false)
      } else {
        recordAgain(primary: true)
      }
    case .result:
      Button(nextLabel) { Task { await coordinator.next() } }
        .buttonStyle(CACPrimaryButtonStyle(icon: "arrow.right"))
        .disabled(coordinator.recordingControlsBlockedForCamera)
        .accessibilityIdentifier("cadence.cac-demo.next")
      recordAgain(primary: false)
    case .denied:
      Button("Open Settings") {
        if let url = URL(string: UIApplication.openSettingsURLString) {
          UIApplication.shared.open(url)
        }
      }
      .buttonStyle(CACPrimaryButtonStyle(icon: "arrow.up.forward"))
      Button {
        Task {
          if session.latestTry == nil {
            await coordinator.record()
          } else {
            await coordinator.recordAgain()
          }
        }
      } label: {
        Label("Try again", systemImage: "arrow.clockwise")
      }
      .buttonStyle(CACSecondaryButtonStyle())
      .disabled(
        (session.latestTry == nil ? !session.canStartRecording : !session.canRecordAnotherTry)
          || coordinator.recordingControlsBlockedForCamera)
    case .failed:
      Button {
        Task {
          if session.canReturnToReview {
            session.returnToReview()
          } else {
            await session.retry()
          }
        }
      } label: {
        Label("Try again", systemImage: "arrow.clockwise")
      }
      .buttonStyle(CACPrimaryButtonStyle())
      .disabled(!session.canReturnToReview && !session.canRetry)
    case .held:
      Button {
        Task { await coordinator.retryHeldDeparture() }
      } label: {
        Label("Try again", systemImage: "arrow.clockwise")
      }
      .buttonStyle(CACPrimaryButtonStyle())
      .accessibilityIdentifier("cadence.cac-demo.retry-held")
    case .unavailable, .leaving:
      EmptyView()
    }
  }

  /// The round control beside a short status. Stacks at accessibility text sizes.
  private func recordDock<Control: View, Level: View>(
    title: String, detail: String?,
    @ViewBuilder control: () -> Control, @ViewBuilder level: () -> Level
  ) -> some View {
    let stacked = dynamicTypeSize.isAccessibilitySize
    let layout =
      stacked ? AnyLayout(VStackLayout(spacing: 12)) : AnyLayout(HStackLayout(spacing: 16))
    return layout {
      control()
      VStack(alignment: stacked ? .center : .leading, spacing: 6) {
        Text(title).font(.headline)
        level()
        if let detail {
          Text(detail)
            .font(.subheadline)
            .foregroundStyle(CACDemoStyle.muted)
        }
      }
      .multilineTextAlignment(stacked ? .center : .leading)
      .fixedSize(horizontal: false, vertical: true)
      .frame(maxWidth: .infinity, alignment: stacked ? .center : .leading)
    }
    .padding(.vertical, 2)
  }

  @ViewBuilder
  private func recordAgain(primary: Bool) -> some View {
    let button = Button {
      Task { await coordinator.recordAgain() }
    } label: {
      Label("Record again", systemImage: "arrow.counterclockwise")
    }
    Group {
      if primary {
        button.buttonStyle(CACPrimaryButtonStyle())
      } else {
        button.buttonStyle(CACSecondaryButtonStyle())
      }
    }
    .disabled(
      !session.canRecordAnotherTry || coordinator.isLeaving
        || coordinator.recordingControlsBlockedForCamera
    )
    .accessibilityIdentifier("cadence.cac-demo.record-again")
  }

  private func announce(old: DirectPracticePhase, phase: DirectPracticePhase) {
    let announcement: String? =
      switch phase {
      case .recording: "Recording."
      case .review(let summary, let assessment):
        DirectPracticeRecordingAdvice.reviewAnnouncement(
          summary: summary, assessment: assessment, isNewRecording: old == .recording)
      case .permissionDenied: "Microphone access is off."
      case .failed(let message): message
      default: nil
      }
    if let announcement { AccessibilityNotification.Announcement(announcement).post() }
  }
}

/// What this word is for: the sound being checked, a practice word, or the recheck.
private struct CACStageLabel: View {
  let word: CACScriptedWord

  private var title: String {
    switch word.part {
    case .soundCheck: "\(word.letter) sound"
    case .practice: "Practice word"
    case .recheck: "Check again"
    }
  }

  var body: some View {
    Label(title, systemImage: CACDemoStyle.icon(word.part))
      .font(.subheadline.weight(.semibold))
      .foregroundStyle(CACDemoStyle.accent)
      .accessibilityAddTraits(.isHeader)
      .accessibilityIdentifier("cadence.cac-demo.stage")
  }
}

/// The word is the main visual. After a check, only the script's known letters are marked.
private struct CACWordCard: View {
  @ObservedObject var session: DirectPracticeSession
  @ObservedObject var coordinator: CACDemoCoordinator
  let word: CACScriptedWord
  let outcome: CACScriptedOutcome?
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 60

  var body: some View {
    VStack(spacing: 14) {
      CACStageLabel(word: word)
      if !dynamicTypeSize.isAccessibilitySize {
        CACWordPicture(word: word, size: 76)
      }
      CACMarkedWord.display(word, outcome: outcome)
        .font(.system(size: wordSize, weight: .medium, design: .serif))
        .tracking(-1)
        .lineLimit(1)
        .minimumScaleFactor(0.4)
        .accessibilityLabel(word.word)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier("cadence.cac-demo.word")
      if session.showsSpokenWordControls {
        CACHearItButton(session: session, coordinator: coordinator)
        CACSpokenWordStatus(session: session, alignment: .center)
      }
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 24)
    .padding(.horizontal, 20)
    .cacSurface()
  }
}

/// Compact word beside Hear it, used while the face preview is the main surface.
/// The word scales down rather than truncating, and stacks above Hear it at large text.
private struct CACWordHeader: View {
  @ObservedObject var session: DirectPracticeSession
  @ObservedObject var coordinator: CACDemoCoordinator
  let word: CACScriptedWord
  let outcome: CACScriptedOutcome?
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 40

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      if dynamicTypeSize.isAccessibilitySize {
        VStack(alignment: .leading, spacing: 8) {
          CACStageLabel(word: word)
          wordText
          hearIt
        }
      } else {
        HStack(spacing: 12) {
          CACWordPicture(word: word, size: 48)
          VStack(alignment: .leading, spacing: 0) {
            CACStageLabel(word: word)
            wordText
          }
          Spacer(minLength: 8)
          hearIt
        }
      }
      if session.showsSpokenWordControls {
        CACSpokenWordStatus(session: session, alignment: .leading)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.horizontal, 14)
    .padding(.vertical, 10)
    .cacSurface()
  }

  private var wordText: some View {
    CACMarkedWord.display(word, outcome: outcome)
      .font(.system(size: wordSize, weight: .medium, design: .serif))
      .tracking(-0.5)
      .lineLimit(1)
      .minimumScaleFactor(0.5)
      .accessibilityLabel(word.word)
      .accessibilityAddTraits(.isHeader)
      .accessibilityIdentifier("cadence.cac-demo.word")
  }

  @ViewBuilder
  private var hearIt: some View {
    if session.showsSpokenWordControls {
      CACHearItButton(
        session: session, coordinator: coordinator,
        iconOnly: !dynamicTypeSize.isAccessibilitySize)
    }
  }
}

/// The word's picture from the library, or its sound's letter when there is none.
struct CACWordPicture: View {
  let word: CACScriptedWord
  let size: CGFloat

  var body: some View {
    if let symbol = CACDemoStyle.picture(word) {
      CACIconTile(symbol: symbol, size: size)
    } else {
      Text(word.letter)
        .font(.system(size: size * 0.48, weight: .medium, design: .serif))
        .foregroundStyle(CACDemoStyle.accent)
        .frame(width: size, height: size)
        .background(CACDemoStyle.accentSoft, in: Circle())
        .accessibilityHidden(true)
    }
  }
}

/// Decorative symbol in a soft tomato circle.
struct CACIconTile: View {
  let symbol: String
  let size: CGFloat
  var tint = CACDemoStyle.accent
  var fill = CACDemoStyle.accentSoft

  var body: some View {
    Image(systemName: symbol)
      .font(.system(size: size * 0.44, weight: .medium))
      .foregroundStyle(tint)
      .frame(width: size, height: size)
      .background(fill, in: Circle())
      .accessibilityHidden(true)
  }
}

private struct CACHearItButton: View {
  @ObservedObject var session: DirectPracticeSession
  @ObservedObject var coordinator: CACDemoCoordinator
  /// The compact header shows only the speaker; the spoken label is unchanged.
  var iconOnly = false

  var body: some View {
    let idle = session.spokenWordState == .idle
    let title = idle ? "Hear it" : session.spokenWordButtonTitle
    let symbol = idle ? "speaker.wave.2.fill" : "stop.fill"
    Button {
      Task { await session.toggleSpokenWord() }
    } label: {
      if iconOnly {
        Image(systemName: symbol).frame(minWidth: 20)
      } else {
        Label(title, systemImage: symbol)
      }
    }
    .buttonStyle(CACCapsuleButtonStyle())
    // Stopping the spoken word stays available; only starting it waits on the camera.
    .disabled(
      !session.canToggleSpokenWord || coordinator.isLeaving
        || (idle && coordinator.recordingControlsBlockedForCamera)
    )
    .accessibilityLabel(title)
    .accessibilityIdentifier("cadence.cac-demo.hear-word")
  }
}

private struct CACSpokenWordStatus: View {
  @ObservedObject var session: DirectPracticeSession
  let alignment: TextAlignment

  var body: some View {
    if let note = session.spokenWordStatusNote {
      Text(note)
        .font(.footnote)
        .foregroundStyle(CACDemoStyle.muted)
        .multilineTextAlignment(alignment)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("cadence.cac-demo.spoken-word-status")
    }
    if session.canRetrySpokenWordStop {
      Button("Retry stopping word") { Task { await session.retrySpokenWordStop() } }
        .buttonStyle(CACSecondaryButtonStyle())
    }
  }
}

/// Illustrative marking of the scripted letters; not a measured position in the audio.
enum CACMarkedWord {
  /// The plain word, or the marked word once a result is shown.
  static func display(_ word: CACScriptedWord, outcome: CACScriptedOutcome?) -> Text {
    guard let outcome, word.word.hasPrefix(word.grapheme) else { return Text(word.word) }
    return text(word, outcome: outcome)
  }

  static func text(_ word: CACScriptedWord, outcome: CACScriptedOutcome) -> Text {
    let marked = String(word.word.prefix(word.grapheme.count))
    let rest = String(word.word.dropFirst(word.grapheme.count))
    return Text(marked).foregroundColor(CACDemoStyle.tint(outcome))
      .underline(true, color: CACDemoStyle.tint(outcome)) + Text(rest)
  }
}

private struct CACFeedbackPanel: View {
  let word: CACScriptedWord
  let outcome: CACScriptedOutcome

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 6) {
        Image(systemName: CACDemoStyle.icon(outcome))
          .accessibilityHidden(true)
        Text(CACDemoStyle.label(outcome))
          .accessibilityIdentifier(
            outcome == .clear
              ? "cadence.cac-demo.feedback.clear" : "cadence.cac-demo.feedback.needs-practice")
      }
      .font(.subheadline.weight(.semibold))
      .foregroundStyle(CACDemoStyle.tint(outcome))
      Text(word.feedback.title)
        .font(.system(.title3, design: .serif, weight: .semibold))
        .accessibilityIdentifier("cadence.cac-demo.feedback.title")
      Text(word.feedback.detail)
        .font(.subheadline)
        .foregroundStyle(CACDemoStyle.muted)
    }
    .fixedSize(horizontal: false, vertical: true)
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .cacSurface(CACDemoStyle.soft(outcome), edge: false)
    .accessibilityElement(children: .contain)
  }
}

/// Real recorder level only; no simulated waveform.
private struct CACLevelBar: View {
  let power: Float?

  private var amplitude: Double {
    guard let power, power.isFinite else { return 0 }
    return pow(10, Double(min(0, power)) / 20)
  }

  var body: some View {
    GeometryReader { geometry in
      ZStack(alignment: .leading) {
        Capsule().fill(CACDemoStyle.separator)
        Capsule().fill(CACDemoStyle.recording)
          .frame(width: max(6, geometry.size.width * amplitude))
      }
    }
    .frame(width: 140, height: 6)
    .accessibilityHidden(true)
  }
}

// MARK: - Shared pieces

/// Scrolling column with its actions pinned below; inline at accessibility text sizes.
private struct CACPage<Content: View, Actions: View>: View {
  @ViewBuilder let content: Content
  @ViewBuilder let actions: Actions
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        content
        if dynamicTypeSize.isAccessibilitySize {
          VStack(spacing: 6) { actions }
        }
      }
      .padding(.horizontal, 24)
      .padding(.top, 12)
      .padding(.bottom, 24)
      .frame(maxWidth: CACDemoStyle.maxWidth)
      .frame(maxWidth: .infinity)
    }
    .scrollBounceBehavior(.basedOnSize)
    .safeAreaInset(edge: .bottom, spacing: 0) {
      if !dynamicTypeSize.isAccessibilitySize {
        VStack(spacing: 6) { actions }
          .padding(.horizontal, 24)
          .padding(.top, 8)
          .padding(.bottom, 8)
          .frame(maxWidth: CACDemoStyle.maxWidth)
          .frame(maxWidth: .infinity)
          .background(CACDemoStyle.background)
      }
    }
  }
}

struct CACStatusTag: View {
  let outcome: CACScriptedOutcome

  var body: some View {
    Label(CACDemoStyle.label(outcome), systemImage: CACDemoStyle.icon(outcome))
      .font(.subheadline.weight(.semibold))
      .foregroundStyle(CACDemoStyle.tint(outcome))
  }
}

struct CACResultRow: View {
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  let word: CACScriptedWord
  let outcome: CACScriptedOutcome?
  var caption: String?

  var body: some View {
    HStack(spacing: 12) {
      if !dynamicTypeSize.isAccessibilitySize {
        CACWordPicture(word: word, size: 36)
      }
      ViewThatFits(in: .horizontal) {
        HStack(spacing: 12) {
          label
          Spacer(minLength: 8)
          tag
        }
        VStack(alignment: .leading, spacing: 6) {
          label
          tag
        }
      }
    }
    .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
    .padding(.vertical, 8)
    .accessibilityElement(children: .combine)
  }

  private var label: some View {
    VStack(alignment: .leading, spacing: 2) {
      (outcome.map { CACMarkedWord.text(word, outcome: $0) } ?? Text(word.word))
        .font(.system(.title3, design: .serif, weight: .medium))
      Text(caption ?? "\(word.letter) sound")
        .font(.footnote)
        .foregroundStyle(CACDemoStyle.muted)
    }
    .fixedSize(horizontal: false, vertical: true)
  }

  @ViewBuilder
  private var tag: some View {
    if let outcome { CACStatusTag(outcome: outcome) }
  }
}

struct CACBeforeAfterRow: View {
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  let word: CACScriptedWord
  let before: CACScriptedOutcome?
  let after: CACScriptedOutcome?

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 12) {
        if !dynamicTypeSize.isAccessibilitySize {
          CACWordPicture(word: word, size: 36)
        }
        (after.map { CACMarkedWord.text(word, outcome: $0) } ?? Text(word.word))
          .font(.system(.title3, design: .serif, weight: .medium))
      }
      if let before { comparison("First check", outcome: before) }
      if let after { comparison("After practice", outcome: after) }
    }
    .fixedSize(horizontal: false, vertical: true)
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, 14)
    .accessibilityElement(children: .combine)
  }

  @ViewBuilder
  private func comparison(_ title: String, outcome: CACScriptedOutcome) -> some View {
    if dynamicTypeSize.isAccessibilitySize {
      VStack(alignment: .leading, spacing: 4) {
        Text(title).font(.footnote).foregroundStyle(CACDemoStyle.muted)
        CACStatusTag(outcome: outcome)
      }
    } else {
      HStack(spacing: 8) {
        Text(title).font(.footnote).foregroundStyle(CACDemoStyle.muted)
        Spacer(minLength: 8)
        CACStatusTag(outcome: outcome)
      }
    }
  }
}

struct CACNotice: View {
  var icon: String? = nil
  let title: String
  let detail: String

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: 12) {
      if let icon {
        Image(systemName: icon)
          .foregroundStyle(CACDemoStyle.accent)
          .accessibilityHidden(true)
      }
      VStack(alignment: .leading, spacing: 4) {
        Text(title).font(.headline)
        Text(detail).font(.subheadline).foregroundStyle(CACDemoStyle.muted)
      }
      Spacer(minLength: 0)
    }
    .fixedSize(horizontal: false, vertical: true)
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .cacSurface()
    .accessibilityElement(children: .combine)
  }
}

/// A held departure retries camera and audio together; otherwise only the camera is retried.
@MainActor
private func retryCameraCleanup(_ coordinator: CACDemoCoordinator) {
  if coordinator.pendingDeparture != nil {
    Task { await coordinator.retryHeldDeparture() }
  } else {
    coordinator.retryFacePreviewCleanup()
  }
}

/// Off the word screen, a camera that hasn't confirmed it stopped blocks the next start.
struct CACCameraRecoveryNotice: View {
  @ObservedObject var coordinator: CACDemoCoordinator
  @ObservedObject var face: FaceGuideModel

  var body: some View {
    if face.cleanupBlocked {
      VStack(alignment: .leading, spacing: 10) {
        CACNotice(
          icon: "video.slash",
          title: "The camera is still turning off",
          detail: "Retry turning it off, then you can continue.")
        Button("Retry turning off camera") { retryCameraCleanup(coordinator) }
          .buttonStyle(CACCapsuleButtonStyle())
          .disabled(coordinator.isLeaving)
          .accessibilityIdentifier("cadence.face-preview.retry-stop")
      }
    }
  }
}

private struct CACMaintenanceRow: View {
  let detail: String
  let action: String
  let enabled: Bool
  let perform: @MainActor () async -> Void

  var body: some View {
    VStack(spacing: 4) {
      Text(detail)
        .font(.footnote)
        .foregroundStyle(CACDemoStyle.muted)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
      Button(action) { Task { await perform() } }
        .buttonStyle(CACSecondaryButtonStyle())
        .disabled(!enabled)
    }
  }
}
