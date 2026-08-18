import SwiftUI

struct DirectPracticeRootView: View {
  @State private var selectedSound: PracticeSound?
  @State private var showingAbout = false
  @State private var localGuidedRoute: LocalGuidedRoute?
  @State private var pendingGuidedDeparture: PendingGuidedDeparture?
  @State private var presentedGuidedRouteID: UUID?
  @State private var showingCACDemo = false

  private struct PendingGuidedDeparture {
    let routeID: UUID
    let handoff: LocalGuidedSummaryHandoff
  }
  #if DEBUG && targetEnvironment(simulator)
    private let savedWordsStore: SavedGuidedWordsStore?
  #else
    private let savedWordsStore: SavedGuidedWordsStore? = .shared
  #endif

  private struct LocalGuidedRoute: Identifiable {
    let id = UUID()
    let entryIDs: [String]?
    var startReview = false
  }
  #if DEBUG && targetEnvironment(simulator)
    private let controlledUI: ControlledUIConfiguration?
    private let controlledSoundResources: ResearchSoundUITestFixtures.RunResources?
    @ObservedObject private var history: PracticeParticipationStore

    init(
      controlledUI: ControlledUIConfiguration? = nil,
      controlledSoundResources: ResearchSoundUITestFixtures.RunResources? = nil
    ) {
      self.savedWordsStore =
        controlledUI == nil
          && ResearchRoute.launch(ProcessInfo.processInfo.arguments) == nil
          && ResearchGuidedWordUITestFixtures.selected() == nil
          && ResearchUnifiedFeedbackUITestFixtures.selected() == nil ? .shared : nil
      self.controlledUI = controlledUI
      self.controlledSoundResources = controlledSoundResources
      _history = ObservedObject(
        wrappedValue: Self.participationHistoryStore(controlledUI: controlledUI))
      _researchRoute = State(
        initialValue: controlledUI.map { ResearchRoute.fixtureRoute($0.fixture) }
          ?? ResearchRoute.launch(ProcessInfo.processInfo.arguments))
    }

    /// Home and generated free/guided writers borrow exactly the same isolated store.
    @MainActor static func participationHistoryStore(
      arguments: [String] = ProcessInfo.processInfo.arguments,
      controlledUI: ControlledUIConfiguration? = nil
    ) -> PracticeParticipationStore {
      if let controlledUI {
        switch controlledUI.fixture {
        case .sound:
          return ResearchSoundUITestFixtures.participationStore(runID: controlledUI.runID)
        case .guided(let testCase):
          return ResearchGuidedWordUITestFixtures.participationStore(for: testCase)
        case .feedback(let testCase):
          return ResearchUnifiedFeedbackUITestFixtures.participationStore(
            for: testCase, arguments: arguments)
        case .mirror:
          preconditionFailure("The generated mirror host has no home or history route")
        case .directTry:
          preconditionFailure("The generated direct-try host owns its isolated history")
        case .localGuided:
          preconditionFailure("The generated local-guided host owns its isolated history")
        case .history:
          preconditionFailure("The generated history host owns its isolated store")
        }
      }
      if let guided = ResearchGuidedWordUITestFixtures.selected(arguments) {
        return ResearchGuidedWordUITestFixtures.participationStore(for: guided)
      }
      if let free = ResearchUnifiedFeedbackUITestFixtures.selected(arguments) {
        return ResearchUnifiedFeedbackUITestFixtures.participationStore(
          for: free, arguments: arguments)
      }
      return PracticeParticipationStore.shared
    }
  #else
    @ObservedObject private var history = PracticeParticipationStore.shared
  #endif
  #if DEBUG && targetEnvironment(simulator)
    // One research destination at a time; Close (child dismiss) sets this back to nil.
    @State private var researchRoute: ResearchRoute?
  #endif
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  // Passive re-read of process cleanup; a no-op unless an ordinary recovery host is present.
  @Environment(\.refreshAudioCleanupRecovery) private var refreshCleanupRecovery
  @ScaledMetric(relativeTo: .largeTitle) private var titleSize = 48

  private enum RootTab: Hashable { case today, sounds, progress }
  @State private var tab: RootTab = .today

  var body: some View {
    TabView(selection: $tab) {
      NavigationStack { todayTab }
        .tabItem { Label("Today", systemImage: "sun.max") }
        .tag(RootTab.today)
      NavigationStack { soundsTab }
        .tabItem { Label("Sounds", systemImage: "waveform") }
        .tag(RootTab.sounds)
      NavigationStack {
        PracticeProgressView(history: history, allowsLiveRoutes: allowsLiveRoutes)
          // Also runs when a pushed library route pops back to Progress.
          .onAppear { refreshCleanupRecovery() }
      }
      .tabItem { Label("Progress", systemImage: "chart.bar") }
      .tag(RootTab.progress)
    }
    .tint(DirectPracticeStyle.ink)
    .fullScreenCover(item: $selectedSound, onDismiss: { refreshCleanupRecovery() }) { sound in
      if allowsLiveRoutes {
        DirectPracticePlayerView(sound: sound, history: history)
      } else {
        Color.clear
      }
    }
    .fullScreenCover(
      item: $localGuidedRoute, onDismiss: finishGuidedDismissal
    ) { route in
      if allowsLiveRoutes {
        LocalGuidedReviewPresenter(
          history: history, store: savedWordsStore, entryIDs: route.entryIDs,
          startReview: route.startReview,
          onSummaryDeparture: { handoff in
            guard localGuidedRoute?.id == route.id, presentedGuidedRouteID == route.id,
              pendingGuidedDeparture == nil,
              canPresentSummaryDestination, handoff.isCanonical
            else { return }
            pendingGuidedDeparture = .init(routeID: route.id, handoff: handoff)
          })
          .onAppear {
            if localGuidedRoute?.id == route.id { presentedGuidedRouteID = route.id }
          }
      } else {
        Color.clear
      }
    }
    .sheet(isPresented: $showingAbout, onDismiss: { refreshCleanupRecovery() }) {
      aboutPractice
    }
    // The demo dismisses itself only after its current media owner has ended.
    .fullScreenCover(isPresented: $showingCACDemo, onDismiss: { refreshCleanupRecovery() }) {
      if allowsLiveRoutes {
        CACDemoView()
      } else {
        Color.clear
      }
    }
    #if DEBUG && targetEnvironment(simulator)
      .fullScreenCover(item: $researchRoute, onDismiss: { refreshCleanupRecovery() }) { route in
        if allowsResearchRoute(route) {
          // Admission guarantees the default actual view selects this exact generated fixture.
          switch route {
          case .guidedWord: ResearchGuidedWordView()
          case .feedback: ResearchFeedbackView(participationWriter: history)
          case .soundPreview: soundPreviewContent
          case .assessment: ResearchAssessmentLabView()
          }
        } else {
          Color.clear
        }
      }
    #endif
  }

  private var todayTab: some View {
    VStack(spacing: 0) {
      todayHeader
      todayViewport
      // A visible lower boundary keeps the reading viewport above the system tab bar.
      PracticeRule()
        .padding(.horizontal, 24)
        .frame(maxWidth: 680)
        .frame(maxWidth: .infinity)
    }
    .modifier(PracticeTabSurface())
    // Also runs when a pushed history route pops back to Today.
    .onAppear { refreshCleanupRecovery() }
  }

  private var todayHeader: some View {
    VStack(spacing: 0) {
      if dynamicTypeSize.isAccessibilitySize {
        VStack(alignment: .leading, spacing: 4) {
          weekdayText
          HStack(spacing: 0) {
            Spacer(minLength: 0)
            aboutButton
          }
        }
      } else {
        HStack(spacing: 0) {
          weekdayText
          Spacer(minLength: 16)
          aboutButton
        }
      }
      PracticeRule()
    }
    .padding(.horizontal, 24)
    .padding(.top, 8)
    .frame(maxWidth: 680)
    .frame(maxWidth: .infinity)
  }

  private var weekdayText: some View {
    Text(Date.now, format: .dateTime.weekday(.wide))
      .font(.subheadline)
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityIdentifier("cadence.home.weekday")
  }

  private var aboutButton: some View {
    Button {
      showingAbout = true
    } label: {
      Text("About")
        .font(.subheadline)
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityLabel("About practice and privacy")
    .accessibilityIdentifier("cadence.home.about")
  }

  @ViewBuilder
  private var todayViewport: some View {
    if #available(iOS 26.0, *) {
      // Keep the privacy footer legible as it passes the floating tab bar.
      todayScroll.clipped().scrollEdgeEffectHidden(true, for: .bottom)
    } else {
      todayScroll.clipped()
    }
  }

  private var todayScroll: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        #if DEBUG && targetEnvironment(simulator)
          if controlledUI != nil || ResearchGuidedWordUITestFixtures.selected() != nil
            || ResearchUnifiedFeedbackUITestFixtures.selected() != nil
          {
            Text("UI test: generated recordings and feedback. No real voice.")
              .font(.footnote)
              .foregroundStyle(DirectPracticeStyle.muted)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.top, 12)
              .accessibilityIdentifier("cadence.home.ui-test-banner")
          }
        #endif

        VStack(alignment: .leading, spacing: 18) {
          Text("Today’s practice.")
            .font(.system(size: titleSize, weight: .regular, design: .serif))
            .tracking(-1.6)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
          Text("Say a word, listen back, try again. A few minutes is plenty.")
            .font(.body)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
          Button {
            if allowsLiveRoutes { showingCACDemo = true }
          } label: {
            HStack {
              Text("Start a sound check")
              Spacer()
              Image(systemName: "arrow.right")
            }
          }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityIdentifier("cadence.cac-demo.open")
          .disabled(!allowsLiveRoutes)
          .padding(.top, 6)
        }
        .padding(.vertical, 36)

        PracticeRule()
        Button {
          if allowsLiveRoutes { selectedSound = PracticeLibrary.starterSound }
        } label: {
          HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
              Text("Free word practice").font(.body.weight(.medium))
              Text("Record, listen back, and try a few words.")
                .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            if !dynamicTypeSize.isAccessibilitySize {
              Image(systemName: "chevron.right")
                .font(.subheadline)
                .foregroundStyle(DirectPracticeStyle.muted)
                .accessibilityHidden(true)
            }
          }
          .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
          .contentShape(Rectangle())
          .accessibilityElement(children: .combine)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("cadence.start")
        .disabled(!allowsLiveRoutes)
        PracticeRule()
        Button {
          if allowsLiveRoutes { localGuidedRoute = LocalGuidedRoute(entryIDs: nil) }
        } label: {
          HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
              Text("Review, practice, recheck").font(.body.weight(.medium))
              Text("Five words, then a few to practice.")
                .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            if !dynamicTypeSize.isAccessibilitySize {
              Image(systemName: "chevron.right")
                .font(.subheadline)
                .foregroundStyle(DirectPracticeStyle.muted)
                .accessibilityHidden(true)
            }
          }
          .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
          .contentShape(Rectangle())
          .accessibilityElement(children: .combine)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("cadence.local-guided.open")
        .disabled(!allowsLiveRoutes)
        PracticeRule()
          .padding(.bottom, 32)

        if let savedWordsStore {
          SavedGuidedWordsSection(store: savedWordsStore, allowsLiveRoutes: allowsLiveRoutes) {
            ids in
            guard allowsLiveRoutes,
              (try? SavedGuidedWordsValidation.entries(entryIDs: ids)) != nil
            else { return }
            localGuidedRoute = LocalGuidedRoute(entryIDs: ids)
          }
        }

        #if DEBUG && targetEnvironment(simulator)
          wordChecks
        #endif

        PracticeParticipationHistorySection(history: history, allowsLiveRoutes: allowsLiveRoutes)

        Text(footerPrivacy)
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.vertical, 28)
      }
      .padding(.horizontal, 24)
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
  }

  private var soundsTab: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        Text("Sounds")
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .frame(minHeight: 44, alignment: .leading)
        PracticeRule()
        VStack(alignment: .leading, spacing: 12) {
          Text("Choose a sound.")
            .font(.system(size: titleSize * 0.84, weight: .regular, design: .serif))
            .tracking(-1.2)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
          Text("\(Self.libraryWordCount) words, grouped by where you hear the sound.")
            .font(.body)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 28)
        .padding(.bottom, 20)

        NavigationLink {
          if allowsLiveRoutes { PracticeWordSearchView(history: history) } else { Color.clear }
        } label: {
          Label("Search words", systemImage: "magnifyingglass")
            .font(.body)
            .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
            .padding(.horizontal, 14)
            .overlay(
              RoundedRectangle(cornerRadius: DirectPracticeStyle.cornerRadius, style: .continuous)
                .strokeBorder(DirectPracticeStyle.border))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("cadence.search.open")
        .disabled(!allowsLiveRoutes)
        .padding(.bottom, 20)

        PracticeRule()
        ForEach(PracticeLibrary.sounds) { sound in
          soundRow(sound)
          PracticeRule()
        }
      }
      .padding(.horizontal, 24)
      .padding(.top, 8)
      .padding(.bottom, 28)
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
    .modifier(PracticeTabSurface())
    // Also runs when a pushed library or search route pops back to Sounds.
    .onAppear { refreshCleanupRecovery() }
  }

  private static let libraryWordCount = Set(
    PracticeLibrary.sounds.flatMap { sound in
      PracticeLibrary.entries(soundID: sound.id).map { $0.prompt.word }
    }
  ).count

  private var allowsLiveRoutes: Bool {
    #if DEBUG && targetEnvironment(simulator)
      controlledUI == nil
    #else
      true
    #endif
  }

  private var canPresentSummaryDestination: Bool {
    guard allowsLiveRoutes, selectedSound == nil, !showingAbout, !showingCACDemo else {
      return false
    }
    #if DEBUG && targetEnvironment(simulator)
      guard researchRoute == nil else { return false }
    #endif
    return true
  }

  private func finishGuidedDismissal() {
    let pending = pendingGuidedDeparture
    let dismissedRouteID = presentedGuidedRouteID
    pendingGuidedDeparture = nil
    presentedGuidedRouteID = nil
    refreshCleanupRecovery()
    guard let pending, pending.routeID == dismissedRouteID,
      localGuidedRoute == nil, canPresentSummaryDestination, pending.handoff.isCanonical
    else { return }
    switch pending.handoff.destination {
    case .independentPractice:
      selectedSound = pending.handoff.canonicalSound
    case .repeatReview:
      guard let ids = pending.handoff.canonicalRepeatEntryIDs else { return }
      localGuidedRoute = LocalGuidedRoute(entryIDs: ids, startReview: true)
    }
  }

  #if DEBUG && targetEnvironment(simulator)
    @ViewBuilder private var soundPreviewContent: some View {
      if let controlledUI {
        if case .sound(let testCase) = controlledUI.fixture,
          let resources = controlledSoundResources,
          resources.runID == controlledUI.runID
        {
          ResearchSoundPreviewView(
            session: ResearchSoundUITestFixtures.session(for: testCase, resources: resources))
        } else {
          Color.clear
        }
      } else {
        ResearchSoundPreviewView()
      }
    }

    private func allowsResearchRoute(_ route: ResearchRoute) -> Bool {
      guard let controlledUI else { return true }
      // Process launch arguments cannot change after validated App admission. Keep an
      // additional exact match before any default view initializer can choose its fallback.
      guard
        ControlledAppLaunch.select(
          arguments: ProcessInfo.processInfo.arguments,
          environment: ProcessInfo.processInfo.environment,
          hasXCTestRuntime: NSClassFromString("XCTestCase") != nil) == .generated(controlledUI)
      else { return false }
      return controlledUI.admits(route.destination)
    }
  #endif

  private var footerPrivacy: String {
    #if DEBUG && targetEnvironment(simulator)
      "Practice recordings stay local and are cleared as you go. Review, practice, recheck uses a bundled on-device English word model. In the simulator, you can also opt in to research sound processing on this Mac after a word match; it gives no pronunciation judgment. The separate Word checks tools below use the check service on this computer only when you tap Check. Example recordings are requested only when you tap Play."
    #else
      "Practice recordings stay on your device and are cleared as you go. Word checks use a bundled on-device English word model."
    #endif
  }

  #if DEBUG && targetEnvironment(simulator)
    private var wordChecks: some View {
      VStack(alignment: .leading, spacing: 0) {
        Text("Word checks")
          .font(.title3.weight(.medium))
          .accessibilityAddTraits(.isHeader)
        Text(
          "A check listens for the whole word you meant to say. It is not a pronunciation score or a diagnosis. Nothing is sent until you choose options and tap Check."
        )
        .font(.subheadline)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.top, 8)
        .padding(.bottom, 12)
        PracticeRule()
        researchEntry(
          .guidedWord, title: "Guided word check",
          detail: "Ages 6–12, with a grown-up.",
          id: "cadence.guided-word.start")
        PracticeRule()
        researchEntry(
          .feedback, title: "Record with feedback",
          detail: "One word. Listen, then check if you like.",
          id: "cadence.feedback.start")
        PracticeRule()
      }
      .padding(.bottom, 24)
    }

    private func researchEntry(
      _ route: ResearchRoute, title: String, detail: String, id: String
    ) -> some View {
      Button {
        if allowsResearchRoute(route) { researchRoute = route }
      } label: {
        HStack(alignment: .center, spacing: 12) {
          VStack(alignment: .leading, spacing: 5) {
            Text(title)
              .font(.body.weight(.medium))
              .foregroundStyle(DirectPracticeStyle.ink)
            Text(detail)
              .font(.subheadline)
              .foregroundStyle(DirectPracticeStyle.muted)
          }
          .fixedSize(horizontal: false, vertical: true)
          Spacer(minLength: 4)
          // At accessibility sizes the chevron's column costs text width and row height.
          if !dynamicTypeSize.isAccessibilitySize {
            Image(systemName: "chevron.right")
              .font(.subheadline)
              .foregroundStyle(DirectPracticeStyle.muted)
              .accessibilityHidden(true)
          }
        }
        .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier(id)
      .disabled(!allowsResearchRoute(route))
    }
  #endif

  private func soundRow(_ sound: PracticeSound) -> some View {
    NavigationLink {
      if allowsLiveRoutes {
        PracticeSoundLibraryView(sound: sound, history: history)
      } else {
        Color.clear
      }
    } label: {
      HStack(alignment: .center, spacing: 20) {
        if !dynamicTypeSize.isAccessibilitySize {
          Text(sound.symbol)
            .font(.system(.title, design: .serif))
            .frame(width: 40, alignment: .leading)
            .accessibilityHidden(true)
        }
        VStack(alignment: .leading, spacing: 5) {
          Text(sound.name.lowercased())
            .font(.body.weight(.medium))
            .foregroundStyle(DirectPracticeStyle.ink)
          Text("\(wordCount(for: sound)) words to practice")
            .font(.subheadline)
            .foregroundStyle(DirectPracticeStyle.muted)
        }
        .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: 4)
        Image(systemName: "chevron.right")
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .accessibilityHidden(true)
      }
      .frame(maxWidth: .infinity, minHeight: 76, alignment: .leading)
      .padding(.vertical, 8)
      .contentShape(Rectangle())
      .accessibilityElement(children: .ignore)
      .accessibilityLabel(
        "\(sound.name), \(wordCount(for: sound)) words")
    }
    .buttonStyle(.plain)
    .accessibilityHint("Opens words grouped by sound position")
    .accessibilityIdentifier("cadence.sound.\(sound.id)")
    .disabled(!allowsLiveRoutes)
  }

  private var aboutPractice: some View {
    VStack(spacing: 0) {
      aboutDoneHeader
      aboutNavigation
    }
    .background(DirectPracticeStyle.canvas)
    .foregroundStyle(DirectPracticeStyle.ink)
  }

  private var aboutNavigation: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 28) {
          Text("About practice")
            .font(.system(.largeTitle, design: .serif))
            .accessibilityAddTraits(.isHeader)
          #if DEBUG && targetEnvironment(simulator)
            NavigationLink("Sound preview") {
              if allowsResearchRoute(.soundPreview) {
                soundPreviewContent
              } else {
                Color.clear
              }
            }
            .font(.body)
            .frame(minHeight: 48)
            .accessibilityIdentifier("cadence.sound-preview.open")
            .disabled(!allowsResearchRoute(.soundPreview))
          #endif
          aboutItem(
            "How words are chosen",
            "Words are grouped by where a sound occurs in a General American English pronunciation, rather than how the word is spelled. For example, phone starts with the F sound. The library includes single sounds and consonant blends."
          )
          aboutItem(
            "Practice together",
            "Younger children and new readers can practice with a grown-up nearby. Read the word together, then let the child choose when to record."
          )
          aboutItem(
            "Listen to your own voice",
            "Record, play it back, and try again whenever you like. Finishing a session celebrates taking part, not saying a sound correctly."
          )
          aboutItem(
            "Private, temporary recordings",
            "During ordinary practice, audio stays on this device. It is removed when you retry, move on, close practice, or leave the app. Practice does not upload audio."
          )
          aboutItem(
            "Saved words",
            "You can choose to save one set of five words on this device. Saved words contain only your choices, without recordings or results. Clear them from Saved words on Home."
          )
          aboutItem(
            "Recent practice",
            "Completed sessions save their date, sound group and word count on this device, up to 100 sessions. This records participation, not pronunciation or improvement. You can clear this history from the practice screen."
          )
          aboutItem(
            "An early practice demo",
            "This word library is awaiting speech-language pathologist review. Recording tips check volume and length only. Cadence does not yet judge pronunciation or recommend which sounds a child should work on."
          )
          VStack(alignment: .leading, spacing: 12) {
            Text("Pronunciation source")
              .font(.headline)
              .accessibilityAddTraits(.isHeader)
            Text(PracticeLibrary.sourceNotice)
              .font(.body)
              .foregroundStyle(DirectPracticeStyle.muted)
            DisclosureGroup("Dictionary license") {
              Text(PracticeLibrary.sourceLicense)
                .font(.footnote)
                .foregroundStyle(DirectPracticeStyle.muted)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
          #if DEBUG && targetEnvironment(simulator)
            aboutItem(
              "Word checks",
              "Guided word check and Record with feedback are on the home screen. They listen for whole words, not pronunciation. A take is sent to the check service on this computer only after you choose options and tap Check. Example recordings are public and are requested only when you tap Play. Recording and listening back without a check stays on this device."
            )
            NavigationLink("Speech check lab") {
              if allowsLiveRoutes {
                ResearchAssessmentLabView(admissionMode: false)
              } else {
                Color.clear
              }
            }
            .font(.body)
            .frame(minHeight: 48)
            .accessibilityIdentifier("cadence.lab.open")
            .disabled(!allowsLiveRoutes)
            NavigationLink("Speech admission lab") {
              if allowsLiveRoutes {
                ResearchAssessmentLabView(admissionMode: true)
              } else {
                Color.clear
              }
            }
            .font(.body)
            .frame(minHeight: 48)
            .accessibilityIdentifier("cadence.admission-lab.open")
            .disabled(!allowsLiveRoutes)
          #endif
          #if DEBUG && !targetEnvironment(simulator)
            if MouthMovementLabView.isAvailable {
              NavigationLink("Camera lab") { MouthMovementLabView() }
                .font(.body)
                .frame(minHeight: 44)
            }
          #endif
        }
        .padding(24)
      }
      .accessibilityIdentifier("cadence.about.scroll")
      .background(DirectPracticeStyle.canvas)
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
    }
  }

  private var aboutDoneHeader: some View {
    VStack(spacing: 0) {
      HStack(spacing: 0) {
        Spacer(minLength: 0)
        Button {
          showingAbout = false
        } label: {
          Text("Done")
            .font(.subheadline)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
      }
      PracticeRule()
    }
    .padding(.horizontal, 24)
    .padding(.top, 8)
    .background(DirectPracticeStyle.canvas)
    .foregroundStyle(DirectPracticeStyle.ink)
  }

  private func aboutItem(_ title: String, _ detail: String) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      Text(title)
        .font(.headline)
        .accessibilityAddTraits(.isHeader)
      Text(detail)
        .font(.body)
        .foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private func wordCount(for sound: PracticeSound) -> Int {
    Set(PracticeLibrary.entries(soundID: sound.id).map { $0.prompt.word }).count
  }
}

#if DEBUG && targetEnvironment(simulator)
  private enum ResearchRoute: String, Identifiable {
    case guidedWord, feedback, soundPreview, assessment
    var id: String { rawValue }

    var destination: ControlledUIConfiguration.Destination {
      switch self {
      case .guidedWord: .guided
      case .feedback: .feedback
      case .soundPreview: .sound
      case .assessment: .assessment
      }
    }

    static func fixtureRoute(_ fixture: ControlledUIConfiguration.Fixture) -> ResearchRoute {
      switch fixture {
      case .sound: .soundPreview
      case .feedback: .feedback
      case .guided: .guidedWord
      case .mirror: preconditionFailure("Mirror fixtures use their isolated host")
      case .directTry: preconditionFailure("Direct-try fixtures use their isolated host")
      case .localGuided: preconditionFailure("Local-guided fixtures use their isolated host")
      case .history: preconditionFailure("History fixtures use their isolated host")
      }
    }

    /// Launch flags for verification; if several are given, the first in this order wins.
    static func launch(_ arguments: [String]) -> ResearchRoute? {
      if arguments.contains("-CadenceGuidedWordMode") { return .guidedWord }
      if arguments.contains("-CadenceFeedbackMode") { return .feedback }
      if arguments.contains("-CadenceSoundMode") { return .soundPreview }
      if arguments.contains("-CadenceAssessmentMode") { return .assessment }
      return nil
    }
  }
#endif

/// Retains one owner across setup, media visits and summaries.
@MainActor
private struct LocalGuidedReviewPresenter: View {
  @StateObject private var session: LocalGuidedReviewSession

  private let store: SavedGuidedWordsStore?
  private let onSummaryDeparture: (LocalGuidedSummaryHandoff) -> Void
  private let startReview: Bool
  @Environment(\.dismiss) private var dismiss

  init(history: PracticeParticipationStore, store: SavedGuidedWordsStore?, entryIDs: [String]?,
    startReview: Bool,
    onSummaryDeparture: @escaping (LocalGuidedSummaryHandoff) -> Void)
  {
    self.store = store
    self.onSummaryDeparture = onSummaryDeparture
    self.startReview = startReview
    _session = StateObject(
      wrappedValue: LocalGuidedReviewSession(history: history, setupEntryIDs: entryIDs))
  }

  var body: some View {
    if session.setupSeedFailed {
      VStack(alignment: .leading, spacing: 24) {
        Text("Saved words could not be opened. Close and try again.")
          .fixedSize(horizontal: false, vertical: true)
        Button("Close") { Task { if await session.close() { dismiss() } } }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
      }.padding(24).interactiveDismissDisabled(true)
        .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    } else {
      LocalGuidedReviewView(session: session, savedWordsStore: store,
        onSummaryDeparture: onSummaryDeparture)
        .task {
          if startReview, !session.setupSeedFailed, session.ledger == nil {
            await session.startInitialReview()
          }
        }
    }
  }
}

/// Shared paper background, opaque status-bar strip and hidden bar for each tab root.
private struct PracticeTabSurface: ViewModifier {
  func body(content: Content) -> some View {
    content
      .background(DirectPracticeStyle.canvas.ignoresSafeArea())
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
      // Opaque strip behind the status bar so scrolled rows do not show through it.
      .safeAreaInset(edge: .top, spacing: 0) {
        Color.clear.frame(height: 0)
          .background(DirectPracticeStyle.canvas.ignoresSafeArea(edges: .top))
      }
      .toolbar(.hidden, for: .navigationBar)
  }
}
