#if DEBUG
  import Accessibility
  import AVFoundation
  import SwiftUI

  struct ResearchAssessmentLabView: View {
    @StateObject private var session: ResearchAssessmentSession
    init(admissionMode: Bool? = nil) {
      _session = StateObject(wrappedValue: ResearchAssessmentSession(admissionMode: admissionMode))
    }
    @State private var acknowledged = false
    @State private var practiceSound: PracticeSound?
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @AccessibilityFocusState private var stateFocused: Bool
    @ScaledMetric(relativeTo: .largeTitle) private var wordSize = 64

    private static let promptIDs = [
      "r-beginning-rabbit", "r-middle-bread", "r-end-door", "b-beginning-baby", "b-middle-baby",
      "n-middle-banana", "k-middle-backpack", "k-end-backpack", "s-beginning-sky",
      "v-beginning-vase", "y-beginning-yo-yo", "th-beginning-thumb",
      "voiced-th-middle-feather", "ng-end-ring", "zh-middle-treasure",
    ]
    static var entries: [PracticeLibraryEntry] {
      let all = PracticeLibrary.entries()
      return promptIDs.compactMap { id in all.first { $0.id == id } }
    }

    var body: some View {
      NavigationStack {
        ScrollView {
          VStack(alignment: .leading, spacing: 24) {
            Text(session.admissionMode ? "Speech admission lab" : "Speech check lab")
              .font(.system(.largeTitle, design: .serif))
              .accessibilityAddTraits(.isHeader)
            Text(
              "An internal experiment in the iOS simulator. Pronunciation results remain unavailable."
            )
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
            PracticeRule()
            if !acknowledged {
              consent
            } else {
              content
            }
          }
          .padding(24)
          .frame(maxWidth: 560, alignment: .leading)
          .frame(maxWidth: .infinity)
        }
        .background(DirectPracticeStyle.canvas.ignoresSafeArea())
        .foregroundStyle(DirectPracticeStyle.ink)
        .tint(DirectPracticeStyle.ink)
        .toolbar(.hidden, for: .navigationBar)
        .safeAreaInset(edge: .top, spacing: 0) {
          VStack(spacing: 0) {
            HStack {
              Button("Close") {
                if session.end() { dismiss() }
              }
              .font(.body)
              .buttonStyle(.plain)
              .frame(minWidth: 56, minHeight: 56)
              .contentShape(Rectangle())
              .accessibilityIdentifier("cadence.lab.close")
              Spacer()
            }
            .padding(.horizontal, 24)
            PracticeRule()
          }
          .background(DirectPracticeStyle.canvas)
        }
      }
      .fullScreenCover(item: $practiceSound, onDismiss: { session.resetSetup() }) { sound in
        DirectPracticePlayerView(sound: sound)
      }
      .onDisappear { session.viewDidDisappear() }
      .interactiveDismissDisabled(session.requiresCaptureCleanupBeforeDeparture)
      .onChange(of: scenePhase) { _, phase in
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
      .onChange(of: session.phase) { _, _ in
        stateFocused = true
        AccessibilityNotification.Announcement(stateHeading).post()
      }
    }

    private var consent: some View {
      VStack(alignment: .leading, spacing: 20) {
        heading("Before you start", id: "consent")
        Text(
          session.admissionMode
            ? "This optional lab sends a temporary recording to a research service on this computer. An independent speech detector and word recognizer run before the research model. Passing those checks is an engineering admission decision. It does not establish pronunciation correctness. Temporary audio is removed after bounded processing, but removal cannot be guaranteed if the service stops unexpectedly. Practice works without this lab."
            : "This lab sends a temporary recording to a research service running on this computer. The service removes temporary audio and sound features after processing. Results stay unavailable while the recording and model pipeline are being tested."
        )
        .fixedSize(horizontal: false, vertical: true)
        Text("Use only audio permitted for research. The word list is awaiting content review.")
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
        Button("I understand") { acknowledged = true }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("cadence.lab.consent.accept")
        Button("Not now") { if session.end() { dismiss() } }
          .frame(minHeight: 44)
          .buttonStyle(.plain)
      }
    }

    @ViewBuilder private var content: some View {
      switch session.phase {
      case .setup:
        setup
      case .ready:
        heading("Ready to record", id: "ready")
        word
        Text("Tap Record and say the word at your own pace.")
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
        Button("Record") { Task { await session.startRecording() } }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("cadence.lab.record")
        Button("Change word") { session.resetSetup() }
          .frame(minHeight: 44)
          .buttonStyle(.plain)
      case .requestingPermission:
        heading("Getting the microphone ready…", id: "permission")
        ProgressView().accessibilityLabel("Waiting for microphone permission")
      case .recording:
        heading("Recording", id: "recording")
        word
        Text("Say the word, then tap Stop.")
          .foregroundStyle(DirectPracticeStyle.muted)
        Button("Stop") { session.stopRecording() }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("cadence.lab.stop")
      case .processing:
        heading("Processing on this computer…", id: "processing")
        ProgressView().accessibilityLabel("Processing")
        Button("Cancel") { session.cancelProcessing() }
          .frame(minHeight: 56)
          .buttonStyle(.plain)
          .accessibilityIdentifier("cadence.lab.cancel")
      case .unavailable(let title, let detail):
        heading(title, id: "unavailable")
        Text(detail).fixedSize(horizontal: false, vertical: true)
        retryAndPractice
      case .permissionDenied:
        heading("Microphone access is off", id: "denied")
        Text("Allow microphone access in Settings to record.")
          .fixedSize(horizontal: false, vertical: true)
        Button("Open Settings") {
          if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
          }
        }
        .buttonStyle(DirectPracticeButtonStyle())
        Button("Try again") { session.retry() }
          .frame(minHeight: 44)
          .buttonStyle(.plain)
      case .cleanupBlocked:
        heading(
          session.captureCleanupState.hasHardwareIssue
            ? "Microphone cleanup needs attention" : "Recording cleanup needs attention",
          id: "cleanup")
        Text(session.captureCleanupDetail).fixedSize(horizontal: false, vertical: true)
        if !session.captureCleanupRetryIDs.isEmpty {
          Button("Retry cleanup") {
            for id in session.captureCleanupRetryIDs {
              session.retryCaptureCleanup(operationID: id)
            }
          }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("cadence.lab.retry-cleanup")
        }
      case .ended:
        heading("Speech check stopped", id: "ended")
        Button("Start again") { session.resetSetup() }
          .buttonStyle(DirectPracticeButtonStyle())
      }
    }

    private var setup: some View {
      VStack(alignment: .leading, spacing: 16) {
        heading("Choose a word", id: "setup")
        Text("Age in completed years").font(.body)
        Picker(
          "Age in completed years",
          selection: Binding(
            get: { session.ageYears ?? 0 }, set: { session.ageYears = $0 == 0 ? nil : $0 }
          )
        ) {
          Text("Choose").tag(0)
          ForEach(6...12, id: \.self) { Text("\($0)").tag($0) }
        }
        .pickerStyle(.menu)
        .frame(minHeight: 48)
        .accessibilityIdentifier("cadence.lab.age")
        Toggle("Process on this computer", isOn: $session.localProcessingEnabled)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.lab.optin")
        Text("Audio is sent only after you turn this on and tap Record.")
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
        PracticeRule()
        ForEach(Self.entries) { entry in
          Button {
            session.selectedEntry = entry
          } label: {
            HStack(spacing: 16) {
              VStack(alignment: .leading, spacing: 4) {
                Text(entry.prompt.word).font(.body.weight(.medium))
                Text("\(soundName(entry.soundID)) · \(entry.position.label.lowercased())")
                  .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
              }
              .fixedSize(horizontal: false, vertical: true)
              Spacer(minLength: 4)
              if session.selectedEntry?.id == entry.id {
                Image(systemName: "checkmark").accessibilityHidden(true)
              }
            }
            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .accessibilityLabel(
            "\(entry.prompt.word), \(soundName(entry.soundID)), \(entry.position.label)"
          )
          .accessibilityValue(session.selectedEntry?.id == entry.id ? "Selected" : "")
          .accessibilityIdentifier("cadence.lab.word.\(entry.id)")
          PracticeRule()
        }
        Text("Engineering word list. Uses dictionary pronunciations; content review is pending.")
          .font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
        if !canContinue {
          Text("Choose an age and a word, then turn on local processing above to continue.")
            .font(.footnote).foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
        }
        Button("Continue") { session.prepare() }
          .buttonStyle(.plain)
          .font(.body.weight(.medium))
          .padding(.horizontal, 20).padding(.vertical, 16)
          .frame(maxWidth: .infinity, minHeight: 56)
          .foregroundStyle(canContinue ? DirectPracticeStyle.canvas : DirectPracticeStyle.muted)
          .background(canContinue ? DirectPracticeStyle.ink : DirectPracticeStyle.canvas)
          .overlay {
            if !canContinue { Rectangle().stroke(DirectPracticeStyle.border, lineWidth: 1) }
          }
          .disabled(!canContinue)
          .accessibilityIdentifier("cadence.lab.continue")
      }
    }

    private var word: some View {
      Text(session.selectedEntry?.prompt.word ?? "")
        .font(.system(size: wordSize, design: .serif))
        .minimumScaleFactor(0.4).lineLimit(1)
        .accessibilityIdentifier("cadence.lab.prompt")
    }

    private var retryAndPractice: some View {
      VStack(alignment: .leading, spacing: 12) {
        if currentPromptSupported {
          Button("Try again") { session.retry() }
            .buttonStyle(DirectPracticeButtonStyle())
            .accessibilityIdentifier("cadence.lab.retry")
          PracticeRule()
        }
        Button("Change word") { session.resetSetup() }
          .buttonStyle(DirectPracticeButtonStyle(secondary: currentPromptSupported))
          .accessibilityIdentifier("cadence.lab.change-word")
        if let entry = session.selectedEntry,
          let sound = PracticeLibrary.session(
            soundID: entry.soundID, position: entry.position, startingAt: entry.id, limit: 1)
        {
          PracticeRule()
          Button("Practice \(entry.prompt.word)") {
            if !session.captureCleanupState.hasHardwareIssue,
              !session.captureCleanupState.hasFileIssue, session.end()
            {
              practiceSound = sound
            }
          }
          .frame(minHeight: 44)
          .buttonStyle(.plain)
          .accessibilityIdentifier("cadence.lab.practice")
        }
      }
    }

    private var canContinue: Bool {
      session.ageYears != nil && session.selectedEntry != nil && session.localProcessingEnabled
    }

    private var currentPromptSupported: Bool {
      guard let entry = session.selectedEntry else { return false }
      return (try? ResearchAssessmentClient.prompt(for: entry)) != nil
    }

    private func heading(_ title: String, id: String) -> some View {
      Text(title).font(.title2.weight(.medium))
        .accessibilityAddTraits(.isHeader)
        .accessibilityFocused($stateFocused)
        .accessibilityIdentifier("cadence.lab.state.\(id)")
        .fixedSize(horizontal: false, vertical: true)
    }

    private func soundName(_ id: String) -> String {
      PracticeLibrary.sounds.first { $0.id == id }?.name ?? id
    }

    private var stateHeading: String {
      switch session.phase {
      case .setup: "Choose a word"
      case .ready: "Ready to record"
      case .requestingPermission: "Getting the microphone ready"
      case .recording: "Recording"
      case .processing: "Processing on this computer"
      case .unavailable(let title, _): title
      case .permissionDenied: "Microphone access is off"
      case .cleanupBlocked: "A temporary recording could not be removed"
      case .ended: "Speech check stopped"
      }
    }
  }
#endif
