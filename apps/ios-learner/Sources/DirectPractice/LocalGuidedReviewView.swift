// The workflow view observes the single coordinator across media visits and summaries.
import AVFoundation
import Accessibility
import SwiftUI

@MainActor
struct LocalGuidedReviewView: View {
  // The presenter supplies one retained coordinator. Neither stage nor sheet creates an owner.
  @ObservedObject var session: LocalGuidedReviewSession
  var savedWordsStore: SavedGuidedWordsStore? = nil
  var onSummaryDeparture: ((LocalGuidedSummaryHandoff) -> Void)? = nil
  @Environment(\.dismiss) private var dismiss
  @Environment(\.scenePhase) private var scenePhase
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  @State private var editingSlot: EditingSlot?
  #if DEBUG && targetEnvironment(simulator)
    @State private var researchSelection: ResearchSelection?

    private struct ResearchSelection: Identifiable {
      let workflowID: UUID
      let entryID: String
      var id: String { workflowID.uuidString + ":" + entryID }
    }
  #endif

  private struct EditingSlot: Identifiable {
    let index: Int
    var id: Int { index }
  }

  var body: some View {
    Group {
      if let ledger = session.ledger {
        switch ledger.stage {
        case .initialReview, .practice, .recheck:
          // This child renders its existing scroll/media controls,
          // but does not own scene/disappear/dismiss or ordinary practice advancement.
          if preparedVisitMatches(ledger) {
            DirectPracticePlayerView(session: session.media, guided: session.playerPresentation)
          } else {
            page { pausedVisit }
          }
        case .choosingPractice:
          page { practiceSelection(ledger) }
        case .readyToRecheck:
          page { recheckIntroduction(ledger) }
        case .completed:
          page { pairedSummary(ledger) }
        }
      } else {
        page { setup }
      }
    }
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    .foregroundStyle(DirectPracticeStyle.ink)
    .tint(DirectPracticeStyle.ink)
    .safeAreaInset(edge: .top, spacing: 0) {
      // Keep this short. Long cleanup explanations belong at the top of the active scroll.
      VStack(spacing: 0) {
        Button {
          Task { if await session.close() { dismiss() } }
        } label: {
          Text("Close")
            .font(.subheadline)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!session.canClose)
        .accessibilityLabel("Close review and practice")
        .accessibilityIdentifier("cadence.guided.close")
        PracticeRule()
      }
      .padding(.horizontal, 24)
      .background(DirectPracticeStyle.canvas)
    }
    // Close is always explicit; the coordinator decides when cleanup permits dismissal.
    .interactiveDismissDisabled(true)
    .sheet(item: $editingSlot) { slot in
      LocalGuidedWordPicker(
        current: session.setupEntries[slot.index],
        otherWords: Set(
          session.setupEntries.enumerated().compactMap { index, entry in
            index == slot.index ? nil : Self.wordKey(entry.prompt.word)
          }),
        choose: { entry in session.replaceSetupEntry(at: slot.index, with: entry) }
      )
    }
    .onAppear { forwardScene(scenePhase) }
    .onChange(of: scenePhase) { _, phase in forwardScene(phase) }
    .onDisappear { session.disappeared() }
    .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) {
      notification in
      if let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
        AVAudioSession.InterruptionType(rawValue: raw) == .began
      {
        session.interrupted()
      }
    }
    .onChange(of: session.isClosed) { _, allowed in if allowed { dismiss() } }
    .onChange(of: session.ledger?.stage) { _, stage in
      let label: String? =
        switch stage {
        case .initialReview: "First review"
        case .choosingPractice: "Choose words to practice"
        case .practice: "Practice"
        case .readyToRecheck: "Ready to recheck"
        case .recheck: "Recheck"
        case .completed: "Your word observations"
        case nil: nil
        }
      if let label { AccessibilityNotification.Announcement(label).post() }
    }
  }

  private func preparedVisitMatches(_ ledger: LocalGuidedReviewLedger) -> Bool {
    let expected: GuidedMediaVisit
    switch ledger.stage {
    case .initialReview, .recheck:
      guard let visit = ledger.activeReviewVisit else { return false }
      expected = .review(visit)
    case .practice:
      guard let visit = ledger.activePracticeVisit else { return false }
      expected = .practice(visit)
    default: return false
    }
    return session.media.guidedMediaVisit == expected
      && session.media.currentPrompt.id == expected.entryID
  }

  private var pausedVisit: some View {
    VStack(alignment: .leading, spacing: 20) {
      title("Word paused")
      note(
        session.isTransitioning
          ? "Preparing the next word."
          : "This word is not ready yet. Cleanup must finish before it opens.")
      if !session.isTransitioning {
        Button("Try opening this word") { Task { await session.retryVisitPreparation() } }
          .buttonStyle(DirectPracticeButtonStyle())
          .disabled(!session.canClose)
          .accessibilityIdentifier("cadence.guided.retry-preparation")
      }
    }
    .accessibilityIdentifier("cadence.guided.preparation-paused")
  }

  private func forwardScene(_ phase: ScenePhase) {
    switch phase {
    case .active: session.sceneActive()
    case .inactive: session.sceneInactive()
    case .background: session.background()
    @unknown default: session.sceneInactive()
    }
  }

  private func page<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        if let note = session.statusNote {
          Text(note)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.guided.status")
        }
        content()
      }
      .padding(24)
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
    .accessibilityIdentifier("cadence.guided.scroll")
  }

  private var setup: some View {
    VStack(alignment: .leading, spacing: 24) {
      title("Review, practice, recheck")
      note(
        "Review five words, choose a few to practice, then revisit the same five. Checks listen for words, not individual sounds."
      )
      #if DEBUG && targetEnvironment(simulator)
        if session.researchModel != nil {
          researchSetup
        }
      #endif
      Button("Start first review") { Task { await session.startInitialReview() } }
        .buttonStyle(DirectPracticeButtonStyle())
        .disabled(!session.canStartInitial)
        .accessibilityIdentifier("cadence.guided.start")
      Text("Your five words").font(.headline).accessibilityAddTraits(.isHeader)
      note("A starting set you can change. Choose five different words.")
      VStack(spacing: 0) {
        ForEach(Array(session.setupEntries.enumerated()), id: \.offset) { index, entry in
          PracticeRule()
          Button {
            editingSlot = EditingSlot(index: index)
          } label: {
            VStack(alignment: .leading, spacing: 4) {
              Text("\(index + 1). \(entry.prompt.word)").font(.body)
              Text(targetDescription(entry)).font(.subheadline)
                .foregroundStyle(DirectPracticeStyle.muted)
              Text("Change word").font(.subheadline)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .disabled(session.isTransitioning)
          .accessibilityLabel(
            "Change word \(index + 1), \(entry.prompt.word), \(targetDescription(entry))"
          )
          .accessibilityIdentifier("cadence.guided.setup.\(index)")
        }
        PracticeRule()
      }
      if let savedWordsStore {
        SavedGuidedWordsSetupSection(session: session, store: savedWordsStore)
      }
      aboutChecks
    }
  }

  private func practiceSelection(_ ledger: LocalGuidedReviewLedger) -> some View {
    VStack(alignment: .leading, spacing: 24) {
      title("Choose words to practice")
      note("Choose 1–3 words. These are your first-check observations, not sound ratings.")
      Button("Practice selected words (\(session.practiceSelectionIDs.count))") {
        Task { await session.startPractice() }
      }
      .buttonStyle(DirectPracticeButtonStyle())
      .disabled(!session.canStartPractice)
      .accessibilityIdentifier("cadence.guided.practice.start")
      VStack(spacing: 0) {
        ForEach(ledger.initialRound.rows, id: \.entry.id) { row in
          PracticeRule()
          let selected = session.practiceSelectionIDs.contains(row.entry.id)
          Button {
            session.togglePracticeSelection(entryID: row.entry.id)
          } label: {
            VStack(alignment: .leading, spacing: 6) {
              Text(row.entry.prompt.word).font(.body.weight(.medium))
              Text(targetDescription(row.entry)).font(.subheadline)
                .foregroundStyle(DirectPracticeStyle.muted)
              Text("First review: \(observation(row.state))").font(.body)
              if let note = session.researchModelNote(for: row) {
                Text(note).font(.subheadline)
              }
              Label(
                selected ? "Selected" : "Select for practice",
                systemImage: selected ? "checkmark.circle.fill" : "circle"
              )
              .font(.subheadline)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
            .padding(.vertical, 16)
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .disabled(
            session.isTransitioning || (!selected && session.practiceSelectionIDs.count == 3)
          )
          .accessibilityValue(selected ? "Selected" : "Not selected")
          .accessibilityAddTraits(selected ? .isSelected : [])
          .accessibilityIdentifier("cadence.guided.select.\(row.entry.id)")
        }
        PracticeRule()
      }
      note(
        "Skipped means you moved past the word without a check. Not reached means the review ended before that word."
      )
    }
  }

  private func recheckIntroduction(_ ledger: LocalGuidedReviewLedger) -> some View {
    VStack(alignment: .leading, spacing: 24) {
      title("Revisit the same five")
      note("Use new recordings. Your first-review observations stay unchanged.")
      Button("Start recheck") { Task { await session.startRecheck() } }
        .buttonStyle(DirectPracticeButtonStyle())
        .disabled(!session.canStartRecheck)
        .accessibilityIdentifier("cadence.guided.recheck.start")
      Text("Practice visits").font(.headline).accessibilityAddTraits(.isHeader)
      VStack(spacing: 0) {
        ForEach(ledger.practiceRows, id: \.entry.id) { row in
          PracticeRule()
          VStack(alignment: .leading, spacing: 6) {
            Text(row.entry.prompt.word).font(.body.weight(.medium))
            Text(practiceDisposition(row.state)).font(.body)
          }
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.vertical, 16)
        }
        PracticeRule()
      }
      note("Practice visits describe participation only.")
    }
  }

  private func pairedSummary(_ ledger: LocalGuidedReviewLedger) -> some View {
    VStack(alignment: .leading, spacing: 24) {
      title("Your word observations")
      note(
        "Each row keeps the first check from each review. Word matches do not assess individual sounds."
      )
      Button("Done") { Task { if await session.close() { dismiss() } } }
        .buttonStyle(DirectPracticeButtonStyle())
        .accessibilityIdentifier("cadence.guided.done")
      Button("Review these five again") { Task { await session.repeatReview() } }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .disabled(!session.canRepeatReview)
        .accessibilityIdentifier("cadence.guided.repeat")
      note("Start a new review with the same words. These observations won’t carry over.")
      if session.media.canRetryCleanup {
        Button("Retry cleanup") { Task { await session.media.retryCleanup() } }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .disabled(session.isTransitioning)
          .accessibilityIdentifier("cadence.guided.repeat-cleanup")
      }
      VStack(spacing: 0) {
        ForEach(ledger.pairedRows, id: \.entry.id) { row in
          PracticeRule()
          VStack(alignment: .leading, spacing: 6) {
            Text(row.entry.prompt.word).font(.body.weight(.medium))
            Text(targetDescription(row.entry)).font(.subheadline)
              .foregroundStyle(DirectPracticeStyle.muted)
            Text("First review: \(observation(row.initial.state))")
            if let note = session.researchModelNote(for: row.initial) {
              Text("First model check: \(note)").font(.subheadline)
            }
            Text("Recheck: \(observation(row.recheck.state))")
            if let note = session.researchModelNote(for: row.recheck) {
              Text("Model recheck: \(note)").font(.subheadline)
            }
          }
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.vertical, 16)
          .accessibilityElement(children: .combine)
          .accessibilityIdentifier("cadence.guided.paired.\(row.entry.id)")
        }
        PracticeRule()
      }
      note(
        "Skipped: no check chosen. Not reached: the round ended before this word. Unavailable: no word check could be made."
      )
      note("These observations are kept only while this flow is open.")
    }
  }

  private var aboutChecks: some View {
    DisclosureGroup("About word checks") {
      Text(
        "Word recognition runs on this device using a bundled English model for short word recordings. It does not use an age or assess individual sounds. You can record and listen when checks are unavailable."
      )
      .font(.subheadline)
      .fixedSize(horizontal: false, vertical: true)
      .padding(.top, 8)
    }
    .frame(minHeight: 44)
    .accessibilityIdentifier("cadence.guided.about")
  }

  #if DEBUG && targetEnvironment(simulator)
    private var researchSetup: some View {
      VStack(alignment: .leading, spacing: 12) {
        Toggle(
          "Run the local research sound model",
          isOn: Binding(
            get: { session.researchModelEnabled },
            set: {
              _ = session.configureResearchModel(enabled: $0, ageYears: session.researchAgeYears)
            }
          )
        )
        .disabled(!session.canEditResearchSetup)
        .accessibilityIdentifier("cadence.guided.model-enabled")
        if session.researchModelEnabled {
          Picker(
            "Practicing child's age",
            selection: Binding(
              get: { session.researchAgeYears },
              set: { _ = session.configureResearchModel(enabled: true, ageYears: $0) }
            )
          ) {
            Text("Choose known age").tag(Int?.none)
            ForEach(6...12, id: \.self) { age in Text("\(age)").tag(Optional(age)) }
          }
          .disabled(!session.canEditResearchSetup)
          .accessibilityIdentifier("cadence.guided.model-age")
          note(
            "After you tap Check, a matched word's recording is processed on this Mac. Audio stays local and is temporary. Use only the child's known age, 6–12. The model is experimental: no sound-correctness judgment, score or correction is shown."
          )
        }
      }
    }
  #endif

  private func title(_ text: String) -> some View {
    Text(text).font(.system(.largeTitle, design: .serif))
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityAddTraits(.isHeader)
  }

  private func note(_ text: String) -> some View {
    Text(text).font(.body).foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
  }

  private func observation(_ state: LocalGuidedReviewRowState) -> String {
    switch state {
    case .notVisited: "Not reached"
    case .ready: "No check yet"
    case .pending: "Checking"
    case .cleanupBlocked: "Waiting for cleanup"
    case .finished(let disposition): disposition.wordObservation
    }
  }

  private func practiceDisposition(_ state: LocalGuidedPracticeRowState) -> String {
    switch state {
    case .notVisited: "Not reached"
    case .ready: "Not finished"
    case .finished(let disposition):
      switch disposition {
      case .finished: "Participation saved"
      case .saveUnconfirmed: "Practiced · history save unconfirmed"
      case .skipped: "Skipped"
      case .unreached: "Not reached"
      }
    }
  }

  fileprivate static func wordKey(_ word: String) -> String {
    word.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  }
}

private func targetDescription(_ entry: PracticeLibraryEntry) -> String {
  let name = PracticeLibrary.sounds.first { $0.id == entry.soundID }?.name ?? entry.soundID
  return "\(name) · \(entry.position.label)"
}

@MainActor
private struct LocalGuidedWordPicker: View {
  let current: PracticeLibraryEntry
  let otherWords: Set<String>
  let choose: (PracticeLibraryEntry) -> Bool
  @Environment(\.dismiss) private var dismiss
  @State private var query = ""
  @State private var soundID: String?
  @State private var position: PracticeTargetPosition?
  @FocusState private var searchFocused: Bool

  private var entries: [PracticeLibraryEntry] {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    return PracticeLibrary.entries(soundID: soundID, position: position, query: query).sorted {
      let leftExact = $0.prompt.word.localizedCaseInsensitiveCompare(trimmed) == .orderedSame
      let rightExact = $1.prompt.word.localizedCaseInsensitiveCompare(trimmed) == .orderedSame
      if leftExact != rightExact { return leftExact }
      if $0.prompt.word != $1.prompt.word { return $0.prompt.word < $1.prompt.word }
      return $0.id < $1.id
    }
  }

  var body: some View {
    let matchingEntries = entries
    NavigationStack {
      VStack(spacing: 0) {
        cancelHeader
        searchRow
          .padding(.horizontal, 24)
          .padding(.top, 24).padding(.bottom, 20)
          .frame(maxWidth: 680).frame(maxWidth: .infinity)
        List {
          VStack(alignment: .leading, spacing: 20) {
            // Vertical menus keep their full labels at accessibility text sizes.
            Menu {
              Picker("Sound", selection: $soundID) {
                Text("All sounds").tag(String?.none)
                ForEach(PracticeLibrary.sounds) { sound in
                  Text(sound.name).tag(Optional(sound.id))
                }
              }
            } label: {
              filterMenuLabel(selectedSoundName)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("cadence.guided.sound-filter")
            .accessibilityLabel("Sound").accessibilityValue(selectedSoundName)
            Menu {
              Picker("Position", selection: $position) {
                Text("All positions").tag(PracticeTargetPosition?.none)
                ForEach(PracticeTargetPosition.allCases, id: \.self) { value in
                  Text(value.label).tag(Optional(value))
                }
              }
            } label: {
              filterMenuLabel(position?.label ?? "All positions")
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("cadence.guided.position-filter")
            .accessibilityLabel("Position").accessibilityValue(position?.label ?? "All positions")
            Text("\(matchingEntries.count) entries · Words already chosen are unavailable.")
              .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
              .fixedSize(horizontal: false, vertical: true)
            if matchingEntries.isEmpty {
              Text("No matching words. Try fewer letters or another filter.")
                .fixedSize(horizontal: false, vertical: true)
            }
          }
          .listRowInsets(EdgeInsets(top: 0, leading: 24, bottom: 20, trailing: 24))
          .listRowSeparator(.hidden)
          .listRowBackground(DirectPracticeStyle.canvas)
          ForEach(matchingEntries) { entry in
            let duplicate = otherWords.contains(
              LocalGuidedReviewView.wordKey(entry.prompt.word))
            Button {
              if choose(entry) { dismiss() }
            } label: {
              VStack(spacing: 0) {
                PracticeRule()
                VStack(alignment: .leading, spacing: 4) {
                  Text(entry.prompt.word).font(.body)
                  Text(targetDescription(entry)).font(.subheadline)
                    .foregroundStyle(DirectPracticeStyle.muted)
                  if duplicate { Text("Already chosen").font(.subheadline) }
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
                .padding(.vertical, 8).contentShape(Rectangle())
                if entry.id == matchingEntries.last?.id { PracticeRule() }
              }
            }
            .disabled(duplicate)
            .accessibilityAddTraits(entry.id == current.id ? .isSelected : [])
            .accessibilityIdentifier("cadence.guided.pick.\(entry.id)")
            .listRowInsets(EdgeInsets(top: 0, leading: 24, bottom: 0, trailing: 24))
            .listRowSeparator(.hidden)
            .listRowBackground(DirectPracticeStyle.canvas)
          }
        }
        .listStyle(.plain)
        .listRowSpacing(0)
        .scrollContentBackground(.hidden)
        .contentMargins(.bottom, 24, for: .scrollContent)
        .frame(maxWidth: 680).frame(maxWidth: .infinity)
        .id(matchingEntries.map(\.id))
        .accessibilityIdentifier("cadence.guided.picker.scroll")
        .scrollDismissesKeyboard(.interactively)
      }
      .background(DirectPracticeStyle.canvas.ignoresSafeArea())
      .foregroundStyle(DirectPracticeStyle.ink).tint(DirectPracticeStyle.ink)
      .navigationTitle("Change word").navigationBarTitleDisplayMode(.inline)
      .toolbarBackground(DirectPracticeStyle.canvas, for: .navigationBar)
      .toolbarBackground(.visible, for: .navigationBar)
    }
  }

  private var searchRow: some View {
    HStack {
      Image(systemName: "magnifyingglass").accessibilityHidden(true)
      TextField("Search words", text: $query)
        .font(.body).frame(minHeight: 48)
        .textInputAutocapitalization(.never).autocorrectionDisabled()
        .submitLabel(.search).focused($searchFocused)
        .onSubmit { searchFocused = false }
        .onChange(of: query) { _, value in
          if value.contains(where: \.isNewline) {
            query = value.components(separatedBy: .newlines).joined(separator: " ")
            searchFocused = false
          }
        }
        .accessibilityLabel("Search all practice words")
        .accessibilityIdentifier("cadence.guided.search")
      if !query.isEmpty {
        Button {
          query = ""
        } label: {
          Image(systemName: "xmark").frame(width: 44, height: 44)
        }
        .buttonStyle(.plain).accessibilityLabel("Clear search")
      }
    }
  }

  private var cancelHeader: some View {
    VStack(spacing: 0) {
      Button {
        dismiss()
      } label: {
        HStack(spacing: 12) {
          Image(systemName: "xmark").font(.system(size: 17, weight: .semibold))
            .accessibilityHidden(true)
          Text("Cancel").font(.subheadline).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Cancel")
      .accessibilityIdentifier("cadence.guided.picker.cancel")
      PracticeRule()
    }
    .padding(.horizontal, 24)
    .background(DirectPracticeStyle.canvas)
  }

  private var selectedSoundName: String {
    PracticeLibrary.sounds.first { $0.id == soundID }?.name ?? "All sounds"
  }

  private func filterMenuLabel(_ value: String) -> some View {
    HStack(spacing: 12) {
      Text(value).font(.body).multilineTextAlignment(.leading)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      Image(systemName: "chevron.up.chevron.down")
        .font(.system(size: 17, weight: .semibold)).accessibilityHidden(true)
    }
    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
    .contentShape(Rectangle())
  }
}
