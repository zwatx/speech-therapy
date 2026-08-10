import SwiftUI

/// The app's home: Today, Sounds and Progress. Sound check and practice open as sessions
/// over it, and their results land back here. Everything shown comes from the coordinator's
/// in-memory results or the bundled word library; nothing here records or measures audio.
struct CACHomeView: View {
  @ObservedObject var coordinator: CACDemoCoordinator
  @ObservedObject var face: FaceGuideModel
  @State private var tab: Tab = .today

  private enum Tab: Hashable { case today, sounds, progress }

  var body: some View {
    TabView(selection: $tab) {
      NavigationStack {
        CACTodayView(coordinator: coordinator, face: face) { tab = .sounds }
      }
      .tabItem { Label("Today", systemImage: "sun.max") }
      .tag(Tab.today)
      NavigationStack { CACSoundsView(coordinator: coordinator) }
        .tabItem { Label("Sounds", systemImage: "waveform") }
        .tag(Tab.sounds)
      NavigationStack { CACProgressView(coordinator: coordinator) }
        .tabItem { Label("Progress", systemImage: "chart.bar") }
        .tag(Tab.progress)
    }
    .tint(CACDemoStyle.ink)
    // A finished or closed session always lands on Today, where its results are.
    .onChange(of: coordinator.stage) { old, _ in
      if old == .word { tab = .today }
    }
  }
}

// MARK: - Results

/// Read-only view of the coordinator's submitted results for the home.
@MainActor
struct CACHomeResults {
  let coordinator: CACDemoCoordinator

  var plan: CACPracticePlan? { coordinator.plan }
  var hasSoundCheck: Bool { coordinator.soundCheck.contains { outcome($0) != nil } }

  func outcome(_ word: CACScriptedWord) -> CACScriptedOutcome? {
    coordinator.submittedResult(for: word)?.outcome
  }

  var recheckOutcome: CACScriptedOutcome? { plan.flatMap { outcome($0.recheck) } }
  var practiced: [CACScriptedWord] { plan?.practice.filter { outcome($0) != nil } ?? [] }

  /// Latest known status of a library sound: a clear recheck replaces its first check.
  func status(soundID: String) -> CACScriptedOutcome? {
    if let plan, plan.focus.sound.id == soundID, let recheckOutcome { return recheckOutcome }
    return coordinator.soundCheck.first(where: { $0.sound.id == soundID }).flatMap(outcome)
  }

  /// Words in the current round, dated by when its sound check started.
  var wordsPracticed: Int { coordinator.submitted.count }
  var practicedOn: Date? { wordsPracticed > 0 ? coordinator.checkedAt : nil }
}

// MARK: - Today

private struct CACTodayView: View {
  @ObservedObject var coordinator: CACDemoCoordinator
  @ObservedObject var face: FaceGuideModel
  let showSounds: () -> Void
  @State private var showingAbout = false
  @ScaledMetric(relativeTo: .largeTitle) private var titleSize = 40

  private var results: CACHomeResults { CACHomeResults(coordinator: coordinator) }

  var body: some View {
    CACHomeScroll {
      header
      hero
      if coordinator.startBlocked {
        CACNotice(
          icon: "hourglass", title: "One moment",
          detail:
            "A recording from before is still being removed. Use Retry cleanup, then start again.")
      }
      CACCameraRecoveryNotice(coordinator: coordinator, face: face)
      if coordinator.stage == .plan, let plan = results.plan { planSection(plan) }
      if coordinator.stage == .recap, let plan = results.plan { practiceSection(plan) }
      if results.hasSoundCheck { soundCheckSection }
      librarySection
    }
    .sheet(isPresented: $showingAbout) { CACAboutView() }
  }

  // MARK: Header

  private var header: some View {
    VStack(spacing: 0) {
      HStack(spacing: 8) {
        Text(Date.now, format: .dateTime.weekday(.wide).month(.wide).day())
          .font(.subheadline)
          .foregroundStyle(CACDemoStyle.muted)
        Spacer(minLength: 8)
        Button {
          showingAbout = true
        } label: {
          Image(systemName: "info.circle")
            .font(.title3)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .foregroundStyle(CACDemoStyle.muted)
        .accessibilityLabel("About and dictionary license")
        .accessibilityIdentifier("cadence.cac-demo.about")
        if coordinator.placement == .modal {
          Button("Close") { Task { await coordinator.close() } }
            .frame(minHeight: 44)
            .foregroundStyle(CACDemoStyle.accent)
            .disabled(coordinator.isLeaving)
            .accessibilityIdentifier("cadence.cac-demo.home-close")
        }
      }
      PracticeRule()
    }
  }

  // MARK: Hero

  /// One headline and one action, chosen by where the learner is.
  @ViewBuilder
  private var hero: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text(heroCopy.title)
        .font(.system(size: titleSize, weight: .regular, design: .serif))
        .tracking(-1)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(heroCopy.id)
      Text(heroCopy.detail)
        .font(.body)
        .foregroundStyle(CACDemoStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
      heroAction
        .padding(.top, 6)
      if coordinator.stage == .welcome {
        Label(privacyNote, systemImage: "lock")
          .font(.footnote)
          .foregroundStyle(CACDemoStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, 2)
      }
    }
    .padding(.top, 8)
  }

  private var heroCopy: (title: String, detail: String, id: String) {
    switch (coordinator.stage, results.plan) {
    case (.plan, let plan?):
      let count = plan.practice.count
      return (
        "Today: your \(plan.letter) sound.",
        "Your sound check found the \(plan.letter) in “\(plan.focus.word)” needs work. Practice \(count) \(count == 1 ? "word" : "words"), then say “\(plan.recheck.word)” again.",
        "cadence.cac-demo.plan-title"
      )
    case (.recap, let plan?):
      return (
        "\(plan.letter) practice done.",
        results.recheckOutcome == .clear
          ? "“\(plan.recheck.word.capitalized)” sounded clear when you checked it again. A few minutes a day keeps it going."
          : "Keep practicing \(plan.letter) words a few minutes a day.",
        "cadence.cac-demo.recap-title"
      )
    case (.recap, nil):
      return (
        "Every sound came through clear.", "Run another sound check anytime.",
        "cadence.cac-demo.recap-title"
      )
    default:
      return (
        "Find the sound to work on.",
        "Say three short words. You’ll get a few practice words for any sound that needs work.",
        "cadence.cac-demo.welcome-title"
      )
    }
  }

  @ViewBuilder
  private var heroAction: some View {
    switch (coordinator.stage, results.plan) {
    case (.plan, _?):
      Button("Start practice") { Task { await coordinator.startPractice() } }
        .buttonStyle(CACPrimaryButtonStyle(icon: "arrow.right"))
        .disabled(coordinator.isLeaving || face.cleanupBlocked)
        .accessibilityIdentifier("cadence.cac-demo.start-practice")
    case (.recap, _?):
      Button("Practice again") { Task { await coordinator.practiceAgain() } }
        .buttonStyle(CACPrimaryButtonStyle(icon: "arrow.counterclockwise"))
        .disabled(coordinator.isLeaving || face.cleanupBlocked)
        .accessibilityIdentifier("cadence.cac-demo.practice-again")
    default:
      startButton(primary: true)
    }
  }

  private func startButton(primary: Bool) -> some View {
    Group {
      if primary {
        Button("Start sound check") { Task { await coordinator.start() } }
          .buttonStyle(CACPrimaryButtonStyle(icon: "arrow.right"))
      } else {
        Button {
          Task { await coordinator.start() }
        } label: {
          Label("New sound check", systemImage: "waveform")
        }
        .buttonStyle(CACSecondaryButtonStyle())
      }
    }
    .disabled(coordinator.isLeaving || face.cleanupBlocked)
    .accessibilityHint(
      hasFacePreview
        ? "Opens the first word and turns on the front camera. The microphone records only when you tap Record."
        : "Opens the first word. Recording starts only when you tap the microphone."
    )
    .accessibilityIdentifier("cadence.cac-demo.start")
  }

  private var privacyNote: String {
    hasFacePreview
      ? "The front camera turns on so you can watch your mouth. The mic records only when you tap Record. Recordings stay on this phone and are removed as you go; video is never saved."
      : "The mic records only when you tap Record. Recordings stay on this phone and are removed as you go."
  }

  private var hasFacePreview: Bool {
    face.phase != .unsupported && coordinator.facePreviewEnabled
  }

  // MARK: Sections

  private func planSection(_ plan: CACPracticePlan) -> some View {
    CACHomeSection(title: "Your practice") {
      ForEach(Array(plan.practice.enumerated()), id: \.element.id) { index, word in
        if index > 0 { PracticeRule() }
        CACResultRow(word: word, outcome: nil, caption: "Practice word")
      }
      PracticeRule()
      CACResultRow(word: plan.recheck, outcome: nil, caption: "Check again")
    }
  }

  private func practiceSection(_ plan: CACPracticePlan) -> some View {
    CACHomeSection(title: "Today’s practice") {
      CACBeforeAfterRow(
        word: plan.focus, before: results.outcome(plan.focus), after: results.recheckOutcome)
      ForEach(plan.practice) { word in
        PracticeRule()
        CACResultRow(word: word, outcome: results.outcome(word), caption: "Practice word")
      }
    }
    .accessibilityIdentifier("cadence.cac-demo.recap-results")
  }

  private var soundCheckSection: some View {
    CACHomeSection(title: "Latest sound check") {
      ForEach(Array(coordinator.soundCheck.enumerated()), id: \.element.id) { index, word in
        if index > 0 { PracticeRule() }
        CACResultRow(word: word, outcome: results.outcome(word))
      }
      if coordinator.stage != .welcome, results.plan != nil {
        PracticeRule()
        startButton(primary: false)
          .padding(.vertical, 4)
      }
    }
    .accessibilityIdentifier("cadence.cac-demo.plan-results")
  }

  private var librarySection: some View {
    CACHomeSection(title: "Word library") {
      Button(action: showSounds) {
        CACNavigationRow(
          symbol: "books.vertical",
          title: "\(PracticeLibrary.wordCount) practice words",
          detail: "\(PracticeLibrary.sounds.count) sounds, at the start, middle and end of words")
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("cadence.cac-demo.open-library")
    }
  }
}

// MARK: - Sounds

private struct CACSoundsView: View {
  @ObservedObject var coordinator: CACDemoCoordinator

  private var results: CACHomeResults { CACHomeResults(coordinator: coordinator) }

  var body: some View {
    CACHomeScroll {
      CACHomeTitle(
        title: "Sounds",
        detail:
          "\(PracticeLibrary.sounds.count) sounds and \(PracticeLibrary.wordCount) words to practice."
      )
      VStack(spacing: 0) {
        ForEach(Array(PracticeLibrary.sounds.enumerated()), id: \.element.id) { index, sound in
          if index > 0 { PracticeRule() }
          NavigationLink(value: sound.id) {
            CACSoundRow(sound: sound, status: results.status(soundID: sound.id))
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("cadence.cac-demo.sound.\(sound.id)")
        }
      }
    }
    .navigationDestination(for: String.self) { soundID in
      if let sound = PracticeLibrary.sounds.first(where: { $0.id == soundID }) {
        CACSoundDetailView(sound: sound, status: results.status(soundID: soundID))
      }
    }
  }
}

private struct CACSoundRow: View {
  let sound: PracticeSound
  let status: CACScriptedOutcome?
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  var body: some View {
    HStack(spacing: 14) {
      CACSoundTile(sound: sound, size: 40)
      VStack(alignment: .leading, spacing: 2) {
        Text(sound.name).font(.body.weight(.semibold))
        Text("/\(sound.symbol)/ · \(PracticeLibrary.entries(soundID: sound.id).count) words")
          .font(.subheadline)
          .foregroundStyle(CACDemoStyle.muted)
      }
      .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 8)
      if let status { CACStatusTag(outcome: status) }
      if !dynamicTypeSize.isAccessibilitySize {
        Image(systemName: "chevron.right")
          .font(.footnote.weight(.semibold))
          .foregroundStyle(CACDemoStyle.muted)
          .accessibilityHidden(true)
      }
    }
    .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
    .contentShape(Rectangle())
    .accessibilityElement(children: .combine)
  }
}

/// Read-only list of a sound's library words by position.
private struct CACSoundDetailView: View {
  let sound: PracticeSound
  let status: CACScriptedOutcome?

  var body: some View {
    CACHomeScroll(showsNavigationBar: true) {
      HStack(alignment: .center, spacing: 16) {
        CACSoundTile(sound: sound, size: 56)
        VStack(alignment: .leading, spacing: 4) {
          Text(sound.name)
            .font(.system(.largeTitle, design: .serif))
            .accessibilityAddTraits(.isHeader)
          if let status { CACStatusTag(outcome: status) }
        }
        .fixedSize(horizontal: false, vertical: true)
      }
      .padding(.top, 8)
      ForEach(PracticeTargetPosition.allCases, id: \.self) { position in
        let entries = PracticeLibrary.entries(soundID: sound.id, position: position)
        if !entries.isEmpty {
          CACHomeSection(title: "\(position.label) · \(entries.count)") {
            LazyVStack(spacing: 0) {
              ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                if index > 0 { PracticeRule() }
                CACLibraryWordRow(prompt: entry.prompt)
              }
            }
          }
        }
      }
    }
    .navigationBarTitleDisplayMode(.inline)
  }
}

private struct CACLibraryWordRow: View {
  let prompt: PracticePrompt

  var body: some View {
    HStack(spacing: 14) {
      Text(prompt.word)
        .font(.system(.title3, design: .serif, weight: .medium))
      Spacer(minLength: 0)
      if let symbol = CACDemoStyle.picture(prompt) {
        Image(systemName: symbol)
          .font(.title3)
          .foregroundStyle(CACDemoStyle.accent)
          .accessibilityHidden(true)
      }
    }
    .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
    .accessibilityElement(children: .combine)
  }
}

/// The sound's short name ("R", "SH") in the accent circle.
struct CACSoundTile: View {
  let sound: PracticeSound
  let size: CGFloat

  var body: some View {
    Text(sound.name.split(separator: " ").first.map(String.init) ?? sound.symbol)
      .font(.system(size: size * 0.42, weight: .medium, design: .serif))
      .lineLimit(1)
      .minimumScaleFactor(0.5)
      .foregroundStyle(CACDemoStyle.accent)
      .frame(width: size, height: size)
      .background(CACDemoStyle.accentSoft, in: Circle())
      .accessibilityHidden(true)
  }
}

// MARK: - Progress

private struct CACProgressView: View {
  @ObservedObject var coordinator: CACDemoCoordinator

  private var results: CACHomeResults { CACHomeResults(coordinator: coordinator) }

  var body: some View {
    CACHomeScroll {
      CACHomeTitle(title: "Progress", detail: summary)
      CACWeekStrip(practicedOn: results.practicedOn)
      if results.hasSoundCheck {
        CACHomeSection(title: dayName) {
          CACActivityRow(
            symbol: CACDemoStyle.icon(.soundCheck), title: "Sound check",
            detail: soundCheckDetail)
          if let plan = results.plan, !results.practiced.isEmpty || results.recheckOutcome != nil {
            PracticeRule()
            CACActivityRow(
              symbol: CACDemoStyle.icon(.practice), title: "\(plan.letter) practice",
              detail: practiceDetail(plan))
          }
        }
        if let plan = results.plan, results.recheckOutcome != nil {
          CACHomeSection(title: "\(plan.letter) sound") {
            CACBeforeAfterRow(
              word: plan.focus, before: results.outcome(plan.focus),
              after: results.recheckOutcome)
          }
        }
      }
      Label("Results stay on this phone and clear when you close the app.", systemImage: "lock")
        .font(.footnote)
        .foregroundStyle(CACDemoStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var summary: String {
    let count = results.wordsPracticed
    guard count > 0 else { return "Nothing yet. Sound checks and practice show up here." }
    let words = "\(count) \(count == 1 ? "word" : "words") practiced"
    return dayName == "Today" ? "\(words) today." : "\(words) on \(dayName)."
  }

  /// "Today", or the weekday the current round started.
  private var dayName: String {
    guard let day = results.practicedOn, !Calendar.current.isDateInToday(day) else {
      return "Today"
    }
    return day.formatted(.dateTime.weekday(.wide))
  }

  private var soundCheckDetail: String {
    let checked = coordinator.soundCheck.filter { results.outcome($0) != nil }
    let missed = checked.filter { results.outcome($0) == .needsPractice }.map(\.letter)
    let words = "\(checked.count) \(checked.count == 1 ? "word" : "words")"
    return missed.isEmpty
      ? "\(words) · all clear"
      : "\(words) · \(missed.joined(separator: ", ")) needs practice"
  }

  private func practiceDetail(_ plan: CACPracticePlan) -> String {
    let count = results.practiced.count
    let words = "\(count) \(count == 1 ? "word" : "words")"
    return results.recheckOutcome == nil ? words : "\(words), then “\(plan.recheck.word)” again"
  }
}

/// This week, Monday first. Only the current round's day can be marked: nothing is saved
/// between launches.
private struct CACWeekStrip: View {
  let practicedOn: Date?

  private var days: [Date] {
    var calendar = Calendar.current
    calendar.firstWeekday = 2
    let today = calendar.startOfDay(for: .now)
    guard let week = calendar.dateInterval(of: .weekOfYear, for: today) else { return [today] }
    return (0..<7).compactMap { calendar.date(byAdding: .day, value: $0, to: week.start) }
  }

  var body: some View {
    HStack(spacing: 0) {
      ForEach(days, id: \.self) { day in
        let isToday = Calendar.current.isDateInToday(day)
        let practiced = practicedOn.map { Calendar.current.isDate($0, inSameDayAs: day) } ?? false
        VStack(spacing: 8) {
          Text(day, format: .dateTime.weekday(.narrow))
            .font(.footnote)
            .foregroundStyle(CACDemoStyle.muted)
          ZStack {
            if practiced {
              Circle().fill(CACDemoStyle.accent)
              Image(systemName: "checkmark")
                .font(.caption.weight(.bold))
                .foregroundStyle(CACDemoStyle.onAccent)
            } else {
              Circle().strokeBorder(
                isToday ? CACDemoStyle.ink : CACDemoStyle.separator, lineWidth: 1.5)
            }
          }
          .frame(width: 28, height: 28)
        }
        .frame(maxWidth: .infinity)
      }
    }
    .padding(.vertical, 4)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(accessibilitySummary)
  }

  private var accessibilitySummary: String {
    guard let practicedOn else { return "No practice yet this week" }
    return Calendar.current.isDateInToday(practicedOn)
      ? "Practiced today"
      : "Practiced on \(practicedOn.formatted(.dateTime.weekday(.wide)))"
  }
}

private struct CACActivityRow: View {
  let symbol: String
  let title: String
  let detail: String

  var body: some View {
    HStack(spacing: 14) {
      CACIconTile(symbol: symbol, size: 40)
      VStack(alignment: .leading, spacing: 2) {
        Text(title).font(.body.weight(.semibold))
        Text(detail).font(.subheadline).foregroundStyle(CACDemoStyle.muted)
      }
      .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
    .accessibilityElement(children: .combine)
  }
}

// MARK: - Shared home pieces

/// Paper column for a home tab.
private struct CACHomeScroll<Content: View>: View {
  /// Tabs draw their own titles; pushed screens keep the system bar for Back.
  var showsNavigationBar = false
  @ViewBuilder let content: Content

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 28) { content }
        .padding(.horizontal, 24)
        .padding(.top, 8)
        .padding(.bottom, 32)
        .frame(maxWidth: CACDemoStyle.maxWidth)
        .frame(maxWidth: .infinity)
    }
    .scrollBounceBehavior(.basedOnSize)
    .background(CACDemoStyle.background.ignoresSafeArea())
    .toolbar(showsNavigationBar ? .visible : .hidden, for: .navigationBar)
  }
}

private struct CACHomeTitle: View {
  let title: String
  let detail: String
  @ScaledMetric(relativeTo: .largeTitle) private var titleSize = 40

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text(title)
        .font(.system(size: titleSize, weight: .regular, design: .serif))
        .tracking(-1)
        .accessibilityAddTraits(.isHeader)
      Text(detail)
        .font(.body)
        .foregroundStyle(CACDemoStyle.muted)
    }
    .fixedSize(horizontal: false, vertical: true)
    .padding(.top, 12)
  }
}

/// A plain heading over ruled rows.
private struct CACHomeSection<Content: View>: View {
  let title: String
  @ViewBuilder let content: Content

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(title)
        .font(.system(.title3, design: .serif, weight: .semibold))
        .accessibilityAddTraits(.isHeader)
      PracticeRule().padding(.top, 6)
      VStack(spacing: 0) { content }
    }
    .accessibilityElement(children: .contain)
  }
}

private struct CACNavigationRow: View {
  let symbol: String
  let title: String
  let detail: String

  var body: some View {
    HStack(spacing: 14) {
      CACIconTile(symbol: symbol, size: 40)
      VStack(alignment: .leading, spacing: 2) {
        Text(title).font(.body.weight(.semibold))
        Text(detail).font(.subheadline).foregroundStyle(CACDemoStyle.muted)
      }
      .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 8)
      Image(systemName: "chevron.right")
        .font(.footnote.weight(.semibold))
        .foregroundStyle(CACDemoStyle.muted)
        .accessibilityHidden(true)
    }
    .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
    .contentShape(Rectangle())
    .accessibilityElement(children: .combine)
  }
}
