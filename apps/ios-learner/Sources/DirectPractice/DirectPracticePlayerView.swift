import AVFoundation
import Accessibility
import SwiftUI

struct DirectPracticePlayerView: View {
  @StateObject private var session: DirectPracticeSession
  private let guided: DirectPracticeGuidedPresentation?
  private let promptAnchor = "cadence.practice.prompt-anchor"
  private let recordingAnchor = "cadence.practice.recording-anchor"
  @State private var wordCheckDetailsExpanded = false
  @State private var practiceReminderExpanded = false
  @Environment(\.dismiss) private var dismiss
  @Environment(\.scenePhase) private var scenePhase
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  @AccessibilityFocusState private var retryStopFocused: Bool
  @AccessibilityFocusState private var spokenWordRetryFocused: Bool
  @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 72

  init(sound: PracticeSound, history: PracticeParticipationStore = .shared) {
    _session = StateObject(wrappedValue: DirectPracticeSession(sound: sound, history: history))
    guided = nil
  }

  // The guided presenter owns this same session for the entire workflow.
  init(session: DirectPracticeSession, guided: DirectPracticeGuidedPresentation) {
    _session = StateObject(wrappedValue: session)
    self.guided = guided
  }

  init(session: DirectPracticeSession) {
    _session = StateObject(wrappedValue: session)
    guided = nil
  }

  var body: some View {
    GeometryReader { geometry in
      ScrollViewReader { proxy in
        ScrollView {
          VStack(alignment: .leading, spacing: 0) {
            header
            if case .review = session.phase {
            } else if wordCheckBlocksPlayback {
              wordRecognition.padding(.top, 24)
            }
            if session.phase == .completed {
              completion
            } else {
              prompt(compact: geometry.size.height < 700)
                .padding(.vertical, geometry.size.height < 700 ? 24 : 40)
                .id(promptAnchor)
              Spacer(minLength: 24)
              controls
              if showsOrdinarySkip {
                Button("Skip word") { Task { await session.skipWord() } }
                  .buttonStyle(PracticeTextButtonStyle())
                  .accessibilityIdentifier("cadence.skip-word")
                  .accessibilityHint("Leaves this word without recording it.")
                  .disabled(!session.canSkipWord)
                  .padding(.top, 12)
              }
              if let guide = DirectPracticeSoundGuide.content(
                sound: session.sound, prompt: session.currentPrompt)
              {
                DirectPracticeSoundGuideView(
                  guide: guide,
                  showsDetail: instruction == nil
                    && !(practiceReminderExpanded && reminderInstruction != nil))
                  // Reset only this optional explanation when the word or visit changes.
                  // The session, scroll view and media owners keep their identities.
                  .id([
                    session.sound.id, session.sound.position.rawValue, session.currentPrompt.id,
                    session.guidedMediaVisit?.visitID.uuidString ?? "ordinary",
                  ])
                  .padding(.top, 28)
              }
              PracticeMirrorPanel(
                mirror: session.mirror, eligibility: session.mirrorEligibility,
                compact: geometry.size.height < 700,
                practicePaused: session.closeRequested,
                show: session.showMirror, hide: session.hideMirror,
                cancel: session.cancelMirrorPermission,
                retry: { Task { await session.retryMirrorStop() } }
              )
              .padding(.top, 28)
            }
          }
          .frame(minHeight: max(0, geometry.size.height - 48), alignment: .top)
          .padding(24)
          .frame(maxWidth: 560)
          .frame(maxWidth: .infinity)
        }
        .scrollBounceBehavior(.basedOnSize)
        .clipped()
        .onChange(of: practiceVisit, initial: true) { _, visit in
          practiceReminderExpanded = false
          if visit != nil { proxy.scrollTo(promptAnchor, anchor: .top) }
        }
        .onChange(of: session.latestTry?.id) { _, _ in
          practiceReminderExpanded = false
        }
        .onChange(of: session.phase) { _, phase in
          if case .review = phase {} else { practiceReminderExpanded = false }
          // Ready/review content can collapse above the active control, especially
          // at larger text sizes. Reveal Stop only when a new capture actually starts.
          if phase == .recording { proxy.scrollTo(recordingAnchor, anchor: .center) }
        }
      }
    }
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    .foregroundStyle(DirectPracticeStyle.ink)
    .tint(DirectPracticeStyle.ink)
    .interactiveDismissDisabled(guided != nil || session.interactiveDismissDisabled)
    .onAppear { if guided == nil { forwardScene(scenePhase) } }
    .onDisappear { if guided == nil { session.viewDidDisappear() } }
    .onChange(of: scenePhase) { _, phase in
      if guided == nil { forwardScene(phase) }
    }
    .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) {
      notification in
      if guided == nil,
        let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
        AVAudioSession.InterruptionType(rawValue: raw) == .began
      {
        session.audioWasInterrupted()
      }
    }
    .onChange(of: session.playbackState) { old, state in
      let announcement: String? =
        switch state {
        case .playing:
          session.earlierTry == nil
            ? "Playing."
            : session.playingTryID == session.earlierTry?.id
              ? "Playing earlier try." : "Playing latest try."
        case .stopping: "Stopping playback."
        case .cleanupBlocked:
          "Playback hasn't confirmed it stopped. Retry stopping is available."
        case .idle:
          old != .idle && session.stopAnnouncementRequested ? "Playback stopped." : nil
        case .preparing: nil
        }
      if let announcement { AccessibilityNotification.Announcement(announcement).post() }
      if case .cleanupBlocked = state { retryStopFocused = true }
      if state == .idle { retryStopFocused = false }
    }
    .onChange(of: session.wordCheckState) { _, state in
      let announcement: String? =
        switch state {
        case .idle: nil
        case .checking: "Checking words in this try on this device."
        case .cancelling: "Cancelling word check. Waiting for cleanup."
        case .cleanupBlocked:
          "Word check cleanup has not been confirmed. Recording, playback, and moving on are paused."
        case .finished(let status):
          LocalWordRecognitionPresentation.observation(
            status, word: session.currentPrompt.word,
            checkedTryID: session.checkedTryID, latestTryID: session.latestTry?.id)
        }
      if let announcement { AccessibilityNotification.Announcement(announcement).post() }
    }
    .onChange(of: session.playbackError) { _, error in
      if let error { AccessibilityNotification.Announcement(error).post() }
    }
    .onChange(of: session.spokenWordStatusNote) { _, note in
      if let note { AccessibilityNotification.Announcement(note).post() }
    }
    .onChange(of: session.canRetrySpokenWordStop) { _, canRetry in
      spokenWordRetryFocused = canRetry
    }
    .onChange(of: session.currentParticipationSaveAnnouncement) { _, event in
      if let event, event == session.currentParticipationSaveAnnouncement {
        AccessibilityNotification.Announcement(event.message).post()
      }
    }
    .onChange(of: session.phase) { oldPhase, phase in
      if guided == nil, phase == .ended { dismiss() }
      let announcement: String? =
        switch phase {
        case .recording: "Recording."
        case .review(let summary, let assessment):
          wordCheckBlocksPlayback ? nil : DirectPracticeRecordingAdvice.reviewAnnouncement(
            summary: summary, assessment: assessment, isNewRecording: oldPhase == .recording)
        case .permissionDenied: "Microphone access is off."
        case .failed(let message): message
        default: nil
        }
      if let announcement { AccessibilityNotification.Announcement(announcement).post() }
    }
  }

  @ViewBuilder
  private var header: some View {
    if let guided {
      VStack(alignment: .leading, spacing: 12) {
        Text("\(guided.stageTitle) · \(guided.positionLabel)")
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("cadence.guided.visit-heading")
        if let note = guided.statusNote {
          Text(note).font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.guided.status")
        }
        if let note = guided.firstObservationNote {
          Text(note).font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.guided.first-observation")
        }
        PracticeRule()
      }
    } else {
      ordinaryHeader
    }
  }

  private var ordinaryHeader: some View {
    VStack(spacing: 12) {
      HStack(alignment: .firstTextBaseline, spacing: 20) {
        Button {
          Task { if await session.end() { dismiss() } }
        } label: {
          Text("Close")
            .font(.subheadline)
            .frame(minWidth: 44, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Close practice")
        .accessibilityIdentifier("cadence.close")
        Spacer()
        Text(
          session.phase == .completed
            ? "\(session.totalWords) of \(session.totalWords)"
            : "\(session.currentIndex + 1) of \(session.totalWords)"
        )
        .font(.subheadline.monospacedDigit())
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityLabel(
          session.phase == .completed
            ? "All \(session.totalWords) \(session.totalWords == 1 ? "word" : "words") practiced"
            : "Word \(session.currentIndex + 1) of \(session.totalWords)")
      }
      if let note = session.closeNote {
        Text(note)
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.close-note")
      }
      PracticeRule()
    }
  }

  private var prompt: some View {
    VStack(spacing: 14) {
      if !dynamicTypeSize.isAccessibilitySize {
        if let picture = Self.pictures[session.currentPrompt.word] {
          Text(picture)
            .font(.system(size: 80))
            .padding(.bottom, 4)
            .accessibilityHidden(true)
        } else if session.currentPrompt.systemImage != "text.bubble.fill" {
          Image(systemName: session.currentPrompt.systemImage)
            .font(.system(size: 64, weight: .light))
            .frame(height: 86)
            .accessibilityHidden(true)
        }
      }
      Text(session.currentPrompt.word)
        .font(.system(size: wordSize, weight: .regular, design: .serif))
        .tracking(-2)
        .multilineTextAlignment(.center)
        .lineLimit(1)
        .minimumScaleFactor(0.25)
        .accessibilityIdentifier("cadence.word")
        .accessibilityAddTraits(.isHeader)
      practicePositionText(symbol: session.sound.symbol, position: session.sound.position)
      .font(.body)
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
      if session.showsSpokenWordControls {
        spokenWordControls
          .padding(.top, 4)
      }
    }
    .frame(maxWidth: .infinity)
  }

  private var spokenWordControls: some View {
    VStack(spacing: 10) {
      Button {
        Task { await session.toggleSpokenWord() }
      } label: {
        HStack(spacing: 8) {
          ZStack {
            Image(systemName: "speaker.wave.2").hidden()
            Image(systemName: "stop.fill").hidden()
            Image(systemName: session.spokenWordState == .idle ? "speaker.wave.2" : "stop.fill")
          }
          .accessibilityHidden(true)
          ZStack {
            // Measure the ordinary titles at the current text size, without exposing
            // duplicate labels to VoiceOver or changing the button when speech starts.
            ForEach(["Hear word", "Stop word", "Stopping…"], id: \.self) { title in
              Text(title).hidden().accessibilityHidden(true)
            }
            Text(session.spokenWordButtonTitle)
          }
          .fixedSize(horizontal: false, vertical: true)
        }
      }
      .buttonStyle(SpokenWordButtonStyle())
      .disabled(!session.canToggleSpokenWord)
      .accessibilityLabel(session.spokenWordButtonTitle)
      .accessibilityIdentifier("cadence.hear-word")

      Text("Synthetic voice. Word readings and accents can vary.")
        .font(.footnote)
        .foregroundStyle(DirectPracticeStyle.muted)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)

      if !usesReadySpokenWordStatus {
        spokenWordStatus()
      }
      if session.canRetrySpokenWordStop && !usesReadySpokenWordStatus {
        spokenWordRetry
      }
    }
    .accessibilityElement(children: .contain)
  }

  private var isSpokenWordStopping: Bool {
    if case .stopping = session.spokenWordState { return true }
    return false
  }

  private var usesReadySpokenWordStatus: Bool {
    session.phase == .ready && !(session.recordingStartupUnavailable && session.tries.isEmpty)
  }

  private var recordingHint: String {
    guided?.showsRecordAndCheck == true
      ? "Say the word. When recording stops, this device checks for it."
      : "Tap Record and say the word."
  }

  private var spokenWordRetry: some View {
    Button("Retry stopping word") {
      Task { await session.retrySpokenWordStop() }
    }
    .buttonStyle(DirectPracticeButtonStyle(secondary: true))
    .accessibilityIdentifier("cadence.spoken-word-retry")
    .accessibilityFocused($spokenWordRetryFocused)
  }

  private func spokenWordStatus(recordingHint: Bool = false) -> some View {
    ZStack {
      // Measure ordinary progress at the actual width and text size. Recovery notes
      // can grow naturally; they do not determine the empty region's minimum height.
      ForEach(
        ["Starting the spoken word…", "Speaking the word.", "Stopping the spoken word."],
        id: \.self
      ) { note in
        Text(note).hidden().accessibilityHidden(true)
      }
      if recordingHint {
        Text(self.recordingHint).hidden().accessibilityHidden(true)
      }
      if let note = session.spokenWordStatusNote {
        Text(isSpokenWordStopping ? "Stopping the spoken word." : note)
          .accessibilityLabel(note)
          .accessibilityIdentifier("cadence.spoken-word-status")
      } else if recordingHint && session.canStartRecording {
        Text(self.recordingHint)
      }
    }
    .font(.subheadline)
    .foregroundStyle(DirectPracticeStyle.muted)
    .multilineTextAlignment(.center)
    .fixedSize(horizontal: false, vertical: true)
  }

  @ViewBuilder
  private var controls: some View {
    if case .review = session.phase {
    } else {
      playbackFeedback
    }
    switch session.phase {
    case .ready where session.recordingStartupUnavailable && session.tries.isEmpty,
      .permissionDenied where session.recordingStartupUnavailable && session.tries.isEmpty,
      .failed where session.recordingStartupUnavailable && session.tries.isEmpty:
      message(
        "Recording is unavailable",
        detail: """
          Cadence couldn’t check its saved recordings. Restart the app to try the check again.
          """
      )
      .accessibilityIdentifier("cadence.recording-startup-unavailable")
    case .ready:
      VStack(spacing: 20) {
        spokenWordStatus(recordingHint: true)
        if session.canRetrySpokenWordStop { spokenWordRetry }
        if let guided, guided.showsRecordAndCheck {
          recordControl(caption: "Record and check") {
            Task { await guided.recordAndCheck() }
          }
          .accessibilityIdentifier("cadence.record-and-check")
          .accessibilityHint("Records a fresh try, then checks for the word on this device.")
          .disabled(!guided.canRecordAndCheck)
          Button {
            Task { await session.startRecording() }
          } label: {
            Label("Record only", systemImage: "mic")
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .accessibilityIdentifier("cadence.record")
          .disabled(!session.canStartRecording)
        } else {
          recordControl(caption: "Record") {
            Task { await session.startRecording() }
          }
          .accessibilityIdentifier("cadence.record")
          .disabled(!session.canStartRecording)
        }
      }
    case .requestingPermission:
      Text("Getting the microphone ready…")
        .font(.body)
        .foregroundStyle(DirectPracticeStyle.muted)
        .frame(maxWidth: .infinity, minHeight: 96)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
    case .recording:
      VStack(spacing: 20) {
        Text("Recording. Say the word, then tap Stop.")
          .foregroundStyle(DirectPracticeStyle.muted)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
        recordControl(caption: "Stop recording", recording: true) {
          session.stopRecording()
        }
        .accessibilityIdentifier("cadence.stop")
        TimelineView(.periodic(from: .now, by: 0.1)) { _ in
          RecordingInputLevelView(
            power: scenePhase == .active ? session.recordingInputPower : nil)
        }
      }
    case .review(let summary, let assessment):
      VStack(alignment: .leading, spacing: 18) {
        PracticeRule()
        if wordCheckBlocksPlayback || guided?.showsWordCheck != false {
          wordRecognition
          PracticeRule()
        }
        if !session.hasPlaybackCleanupIssue && !session.isRetryingPlaybackCleanup {
          if let earlier = session.earlierTry, let latest = session.latestTry {
            replayRow(earlier, name: "earlier", identifier: "cadence.replay-earlier")
            PracticeRule()
            replayRow(latest, name: "latest", identifier: "cadence.replay")
          } else if let only = session.latestTry {
            replayRow(only, name: nil, identifier: "cadence.replay")
          } else {
            // Defensive: review always has a kept take; keep the original single row shape.
            replayButton(
              label: session.playbackControlLabel, duration: summary.duration, active: true,
              identifier: "cadence.replay"
            ) { Task { await session.togglePlayback() } }
          }
        }
        PracticeRule()

        // It never stops playback for the learner; it waits until playback is idle.
        recordControl(caption: "Record another try") { Task { await session.recordAnotherTry() } }
          .accessibilityIdentifier("cadence.record-another")
          .disabled(!session.canRecordAnotherTry)
          .padding(.top, 6)
        if session.earlierTry != nil {
          Text("Replaces the earlier try.")
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .frame(maxWidth: .infinity, alignment: .center)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.replace-note")
        }

        playbackFeedback
        if let playbackError = session.playbackError {
          Text(playbackError)
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.playback-error")
        }
        if let guided {
          guidedActions(guided)
        } else {
          VStack(spacing: 4) {
            Button {
              Task { await session.continuePractice() }
            } label: {
              HStack {
                Text(
                  session.currentIndex + 1 == session.totalWords ? "Finish practice" : "Next word")
                Spacer()
                Image(systemName: "arrow.right")
              }
            }
            .buttonStyle(DirectPracticeButtonStyle())
            .accessibilityIdentifier("cadence.continue")
            .disabled(session.actionsDisabled)
            Button(
              session.earlierTry == nil
                ? "Delete recording and start over" : "Delete both tries and start over"
            ) { Task { await session.retry() } }
            .buttonStyle(PracticeTextButtonStyle())
            .accessibilityIdentifier("cadence.retry")
            .disabled(session.actionsDisabled)
          }
        }
        // Names the intended target only, while the learner's own replay is usable.
        // Static text: no announcement of its own, so playback changes stay quiet.
        if session.latestTry != nil, !session.cleanupBlocked, !session.hasPlaybackCleanupIssue,
          !session.isRetryingPlaybackCleanup, !isStopping(session.playbackState)
        {
          let focus = DirectPracticeListeningFocus.text(
            sound: session.sound, word: session.currentPrompt.word,
            twoTries: session.earlierTry != nil)
          // Word joiners keep "/b/" on one line; VoiceOver reads the unmodified text.
          let symbol = session.sound.symbol
          Text(focus.replacingOccurrences(of: "/\(symbol)/", with: "/\u{2060}\(symbol)\u{2060}/"))
            .font(.body)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityLabel(focus)
            .accessibilityIdentifier("cadence.listening-focus")
        }
        // Advice describes the latest successful take only; no comparison is made.
        if case .retry(let coaching) = assessment,
          !(session.latestTry.map({
            DirectPracticeRecordingAdvice.suppressesQuietTip(
              summary: $0.summary, assessment: $0.assessment)
          }) ?? false)
        {
          Text("Recording tip: \(coaching.detail)")
            .font(.subheadline)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
        }
        if session.earlierTry != nil, !session.hasPlaybackCleanupIssue,
          !isStopping(session.playbackState)
        {
          Text(
            "Play either try to listen back. Both are removed when you \(isLastWord ? "finish" : "go to the next word")."
          )
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.two-try-note")
        }
        Text("If you close while playback is stopping, your recordings are removed after it stops.")
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
      }
    case .permissionDenied:
      VStack(spacing: 20) {
        let kept = session.canReturnToReview
        message(
          "Microphone access is off",
          detail: kept
            ? "Allow microphone access in Settings to record another try. Your earlier recording of this word is still here."
            : "Allow microphone access in Settings, then come back when you’re ready.")
        VStack(spacing: 4) {
          if kept {
            Button("Back to your recording") { session.returnToReview() }
              .buttonStyle(DirectPracticeButtonStyle())
              .accessibilityIdentifier("cadence.back-to-review")
          }
          Button("Open Settings") {
            if let url = URL(string: UIApplication.openSettingsURLString) {
              UIApplication.shared.open(url)
            }
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: kept))
          Button("Try microphone again") {
            Task {
              if session.latestTry == nil {
                await session.startRecording()
              } else {
                await session.recordAnotherTry()
              }
            }
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        }
      }
    case .failed(let detail) where session.canReturnToReview:
      // A failed replacement: the error stays truthful; the kept take is one tap away.
      VStack(spacing: 20) {
        message("That try didn’t record", detail: "\(detail) Your earlier recording is still here.")
        VStack(spacing: 4) {
          Button("Back to your recording") { session.returnToReview() }
            .buttonStyle(DirectPracticeButtonStyle())
            .accessibilityIdentifier("cadence.back-to-review")
          Button("Delete recording and start over") { Task { await session.retry() } }
            .buttonStyle(DirectPracticeButtonStyle(secondary: true))
            .accessibilityIdentifier("cadence.retry")
            .disabled(session.actionsDisabled)
        }
      }
    case .failed(let detail):
      VStack(spacing: 20) {
        message("Let’s try that again", detail: detail)
        if session.canRetry {
          Button("Back to the word") { Task { await session.retry() } }
            .buttonStyle(DirectPracticeButtonStyle())
        } else if session.cleanupBlocked {
          // The specific retry action is supplied above; Close remains in the header
          // with a hardware/file-aware note explaining any retained screen.
          EmptyView()
        } else if guided == nil {
          Button("Close practice") {
            Task { if await session.end() { dismiss() } }
          }
          .buttonStyle(DirectPracticeButtonStyle())
        }
      }
    case .completed, .ended:
      EmptyView()
    }
    if let guided {
      switch session.phase {
      case .ready, .permissionDenied, .failed:
        guidedActions(guided).padding(.top, 24)
      default: EmptyView()
      }
    }
  }

  private var wordCheckBlocksPlayback: Bool {
    switch session.wordCheckState {
    case .checking, .cancelling, .cleanupBlocked: true
    case .idle, .finished: false
    }
  }

  private var wordRecognition: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Word check")
        .font(.headline)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier("cadence.word-check-heading")
      switch session.wordCheckState {
      case .checking:
        Text(guided?.checkProgressNote ?? "Checking words in this try on this device…")
          .font(.body)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.word-check-status")
        Button(guided?.checkLabel == nil ? "Cancel word check" : "Cancel check") {
          session.cancelWordCheck()
        }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .accessibilityIdentifier("cadence.word-check-cancel")
      case .cancelling:
        Text(
          guided?.checkProgressNote
            ?? "Cancelling word check. Waiting for the recognizer to finish cleanup…"
        )
        .font(.body)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("cadence.word-check-status")
      case .cleanupBlocked:
        Text(
          "Word check cleanup has not been confirmed. Recording, playback, and moving on are paused. Close also waits for cleanup."
        )
        .font(.body)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("cadence.word-check-status")
      case .idle, .finished:
        if guided?.showsWordCheck != false {
          if case .finished(let status) = session.wordCheckState,
            let observation = LocalWordRecognitionPresentation.observation(
              status, word: session.currentPrompt.word,
              checkedTryID: session.checkedTryID, latestTryID: session.latestTry?.id)
          {
            Text(observation)
              .font(.body)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.word-check-result")
            if guided == nil,
              let guess = LocalWordRecognitionPresentation.wordGuess(session.currentWordGuess)
            {
              Text(guess)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("cadence.word-check-guess")
            }
          }
          Button(
            guided?.checkLabel
              ?? (session.earlierTry == nil
                ? "Check words in this try" : "Check words in latest try")
          ) {
            Task {
              if let guided { await guided.check() } else { await session.startWordCheck() }
            }
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .disabled(!session.canCheckWordsInLatestTry || guided?.canCheckWords == false)
          .accessibilityIdentifier("cadence.word-check")
        }
      }
      if let note = guided?.firstCheckStatusNote {
        Text(note)
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.guided.first-check-status")
      }
      if !wordCheckBlocksPlayback, let note = guided?.modelObservationNote {
        Text(note)
          .font(.subheadline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.guided.model-observation")
      }
      if !wordCheckBlocksPlayback, guided?.showsWordCheck != false {
        DisclosureGroup(isExpanded: $wordCheckDetailsExpanded) {
          Text(LocalWordRecognitionPresentation.availabilityNote)
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.word-check-note")
        } label: {
          Text("About word checks")
            .font(.footnote)
            .frame(minHeight: 44, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityIdentifier("cadence.word-check-about")
      }
    }
    .accessibilityElement(children: .contain)
  }

  private var isLastWord: Bool { session.currentIndex + 1 == session.totalWords }

  private func isStopping(_ state: PracticePlaybackRuntimeState) -> Bool {
    switch state {
    case .stopping, .cleanupBlocked: true
    case .idle, .preparing, .playing: false
    }
  }

  /// `name` is nil for a single take, which keeps the original labels.
  private func replayRow(_ take: DirectPracticeTry, name: String?, identifier: String)
    -> some View
  {
    let active = session.playingTryID == take.id
    let label: String
    if let name {
      switch session.playbackState {
      case .preparing where active: label = "Cancel playback"
      case .playing where active: label = "Stop \(name) try"
      case .stopping where active: label = "Stopping…"
      default: label = "Play \(name) try"
      }
    } else {
      label = session.playbackControlLabel
    }
    return VStack(alignment: .leading, spacing: 10) {
      replayButton(
        label: label, duration: take.summary.duration, active: active || name == nil,
        identifier: identifier
      ) { Task { await session.togglePlayback(tryID: take.id) } }
      // With two rows, an exact stop must settle before either row acts again. The single
      // row keeps its original enabled Stopping… control.
      .disabled(
        (name != nil && isStopping(session.playbackState))
          || (session.isTransitioning && session.playbackState == .idle))
      if let advice = DirectPracticeRecordingAdvice.observation(
        summary: take.summary, assessment: take.assessment)
      {
        VStack(alignment: .leading, spacing: 6) {
          Text(name == "earlier" ? "Earlier try" : name == "latest" ? "Latest try" : "This try")
            .font(.subheadline)
          Text(advice.title).font(.subheadline)
          Text(advice.detail).font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("cadence.recording-advice.\(take.id.uuidString)")
      }
    }
  }

  /// Round record/stop control with its caption read as the button's label.
  private func recordControl(
    caption: String, recording: Bool = false, action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      Text(caption)
    }
    .buttonStyle(PracticeRecordControlStyle(recording: recording))
    .frame(maxWidth: .infinity)
    .accessibilityLabel(caption)
  }

  private func replayButton(
    label: String, duration: Double, active: Bool, identifier: String,
    action: @escaping () -> Void
  ) -> some View {
    let icon = active && session.playbackState != .idle ? "stop.circle.fill" : "play.circle.fill"
    let seconds = String(format: "%.1f s", duration)
    return Button(action: action) {
      Group {
        if dynamicTypeSize.isAccessibilitySize {
          // Largest sizes: the duration moves below so the label never breaks mid-word.
          HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: icon).font(.title2).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
              Text(label).font(.body.weight(.medium))
              Text(seconds)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(DirectPracticeStyle.muted)
            }
            Spacer(minLength: 0)
          }
          .fixedSize(horizontal: false, vertical: true)
        } else {
          HStack(spacing: 12) {
            Image(systemName: icon).font(.title2).accessibilityHidden(true)
            Text(label).font(.body.weight(.medium))
            Spacer(minLength: 8)
            Text(seconds)
              .font(.subheadline.monospacedDigit())
              .foregroundStyle(DirectPracticeStyle.muted)
          }
        }
      }
      .frame(maxWidth: .infinity, minHeight: 48)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityLabel(label)
    .accessibilityValue(String(format: "%.1f seconds", duration))
    .accessibilityIdentifier(identifier)
    .disabled(wordCheckBlocksPlayback || session.spokenWordState != .idle)
  }

  private func forwardScene(_ phase: ScenePhase) {
    switch phase {
    case .active: session.appDidBecomeActive()
    case .inactive: session.appDidBecomeInactive()
    case .background: session.appDidEnterBackground()
    @unknown default: session.appDidBecomeInactive()
    }
  }

  private var guidedNavigationBlocked: Bool {
    session.actionsDisabled || session.interactiveDismissDisabled
      || session.phase == .requestingPermission || session.phase == .recording
  }

  private func guidedActions(_ presentation: DirectPracticeGuidedPresentation) -> some View {
    VStack(spacing: 4) {
      Button(presentation.continueLabel) { Task { await presentation.continueVisit() } }
        .buttonStyle(DirectPracticeButtonStyle())
        .disabled(!presentation.canContinue || guidedNavigationBlocked)
        .accessibilityIdentifier("cadence.guided.continue")
      Button("Skip this word") { Task { await presentation.skip() } }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .disabled(!presentation.canSkip || guidedNavigationBlocked)
        .accessibilityIdentifier("cadence.guided.skip")
      Button(presentation.finishStageLabel) { Task { await presentation.finishStage() } }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .disabled(!presentation.canFinishStage || guidedNavigationBlocked)
        .accessibilityIdentifier("cadence.guided.finish-stage")
    }
  }

  private func guidedCompletion(_ presentation: DirectPracticeGuidedPresentation) -> some View {
    VStack(alignment: .leading, spacing: 24) {
      if case .stopping = session.mirror.state {
        completionMirrorRecovery
      } else if case .stopFailed = session.mirror.state {
        completionMirrorRecovery
      }
      playbackFeedback
      Text("Practice visit finished")
        .font(.system(.largeTitle, design: .serif))
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier("cadence.guided.practice-finished")
      if let error = session.historyError {
        Text(error).font(.body)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.guided.history-error")
        Button("Retry saving") { presentation.retrySave() }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .disabled(!presentation.canRetrySave || guidedNavigationBlocked)
          .accessibilityIdentifier("cadence.guided.history-retry")
      } else if let saved = session.historySavedNote {
        Text(saved).font(.body)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.guided.history-saved")
      }
      guidedActions(presentation)
    }
    .padding(.top, 24)
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  @ViewBuilder
  private var completion: some View {
    if let guided {
      guidedCompletion(guided)
    } else {
      ordinaryCompletion
    }
  }

  private var ordinaryCompletion: some View {
    VStack(alignment: .leading, spacing: 28) {
      if case .stopping = session.mirror.state {
        completionMirrorRecovery
      } else if case .stopFailed = session.mirror.state {
        completionMirrorRecovery
      }
      Image(systemName: "checkmark")
        .font(.title2.weight(.semibold))
        .foregroundStyle(DirectPracticeStyle.onAccent)
        .frame(width: 56, height: 56)
        .background(DirectPracticeStyle.accent, in: Circle())
        .accessibilityHidden(true)
      Text("Practice complete.")
        .font(.system(.largeTitle, design: .serif))
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityAddTraits(.isHeader)
      Text(
        "You practiced \(session.totalWords) \(session.totalWords == 1 ? "word" : "words"). Come back whenever you’re ready."
      )
      .font(.body)
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityIdentifier("cadence.complete")
      if let historyError = session.historyError {
        Text(historyError)
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.history-error")
        // Metadata-only: retries the same frozen completion, never audio or counts.
        if session.canRetryParticipationSave {
          Button("Try saving again") { session.retryParticipationSave() }
            .buttonStyle(DirectPracticeButtonStyle(secondary: true))
            .accessibilityIdentifier("cadence.history-retry")
        }
      } else if let saved = session.historySavedNote {
        Text(saved)
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.history-saved")
      }
      Text(session.sound.prompts.map(\.word).joined(separator: " · "))
        .font(.system(.title2, design: .serif))
        .fixedSize(horizontal: false, vertical: true)
      PracticeRule()
      if let next = session.nextPracticeSound {
        Text("Next: \(next.prompts.map(\.word).joined(separator: " · "))")
          .font(.body)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
      } else {
        Text(
          "That’s the end of this word list. Choose another sound or position to keep practicing."
        )
        .font(.body)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
      }
      VStack(spacing: 4) {
        if session.nextPracticeSound != nil {
          Button("Practice more") { Task { await session.practiceMore() } }
            .buttonStyle(DirectPracticeButtonStyle())
            .accessibilityIdentifier("cadence.more")
            .disabled(session.actionsDisabled)
        }
        Button("Practice these again") { Task { await session.restart() } }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        Button("Explore more sounds") {
          Task { if await session.end() { dismiss() } }
        }
        .buttonStyle(PracticeTextButtonStyle())
          .disabled(session.actionsDisabled)
      }
    }
    .padding(.top, 40)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
  }

  private var completionMirrorRecovery: some View {
    PracticeMirrorPanel(
      mirror: session.mirror, eligibility: .unavailable, compact: true,
      practicePaused: true,
      show: session.showMirror, hide: session.hideMirror,
      cancel: session.cancelMirrorPermission,
      retry: { Task { await session.retryMirrorStop() } })
  }

  @ViewBuilder
  private var playbackFeedback: some View {
    if let status = session.playbackStatus {
      VStack(alignment: .leading, spacing: 10) {
        Text(status).font(.subheadline)
        if session.hasPlaybackCleanupIssue {
          Text(
            "Recording, checks and other audio stay paused until it does. Your recordings and any results are unchanged."
          )
          .font(.subheadline)
        }
      }
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityElement(children: .combine)
      .accessibilityIdentifier("cadence.playback-status")
    }
    if session.hasPlaybackCleanupIssue || session.isRetryingPlaybackCleanup {
      Button("Retry stopping") { Task { await session.retryCleanup() } }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .accessibilityHint("Asks playback to stop again.")
        .accessibilityIdentifier("cadence.playback-retry-stop")
        .accessibilityFocused($retryStopFocused)
        .disabled(!session.canRetryCleanup)
    } else if session.captureCleanupState.hasHardwareIssue
      || session.captureCleanupState.hasFileIssue || session.hasPendingFileCleanup
    {
      Button("Retry cleanup") { Task { await session.retryCleanup() } }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .accessibilityIdentifier("cadence.capture-retry-cleanup")
        .disabled(!session.canRetryCleanup)
    }
  }

  private func message(_ title: String, detail: String) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      Text(title).font(.headline)
      Text(detail).font(.body).foregroundStyle(DirectPracticeStyle.muted)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .fixedSize(horizontal: false, vertical: true)
  }

  // Familiar pictures support early readers; color helps younger children recognize them.
  // The printed word remains the prompt; pictures are not pronunciation feedback.
  private static let pictures: [String: String] = [
    "ball": "🏀", "boat": "⛵️", "bee": "🐝", "pig": "🐷", "pear": "🍐", "pie": "🥧",
    "moon": "🌙", "mouse": "🐭", "milk": "🥛", "tiger": "🐯", "toe": "🦶", "tent": "⛺️",
    "dog": "🐶", "duck": "🦆", "door": "🚪", "nest": "🪺", "nose": "👃", "cat": "🐱",
    "key": "🔑", "kite": "🪁", "goat": "🐐", "fish": "🐟", "fan": "🪭", "feet": "👣",
    "van": "🚐", "vase": "🏺", "vest": "🦺", "sun": "☀️", "sock": "🧦", "soap": "🧼",
    "zebra": "🦓", "ship": "🚢", "shoe": "👟", "shell": "🐚", "chair": "🪑",
    "cheese": "🧀", "chick": "🐥", "juice": "🧃", "leaf": "🍃", "lion": "🦁",
    "rabbit": "🐰", "rain": "🌧️", "ring": "💍", "web": "🕸️", "wing": "🪽",
    "yarn": "🧶", "yo-yo": "🪀", "hat": "🎩", "horse": "🐴", "house": "🏠",
    "thumb": "👍", "thread": "🧵", "feather": "🪶", "weather": "🌤️", "king": "🤴",
    "measure": "📏", "television": "📺",
  ]
}

private struct SpokenWordButtonStyle: ButtonStyle {
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.body.weight(.medium))
      .multilineTextAlignment(.center)
      .padding(.horizontal, 16)
      .padding(.vertical, 10)
      .frame(minHeight: 44)
      .foregroundStyle(DirectPracticeStyle.ink)
      .padding(.horizontal, 4)
      .background(DirectPracticeStyle.ink.opacity(configuration.isPressed ? 0.10 : 0.035), in: Capsule())
      .overlay(Capsule().strokeBorder(DirectPracticeStyle.border))
      .contentShape(Capsule())
      .opacity(isEnabled ? 1 : 0.45)
  }
}
