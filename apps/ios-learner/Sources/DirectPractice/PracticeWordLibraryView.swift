import Accessibility
import SwiftUI

struct PracticeSoundLibraryView: View {
  let sound: PracticeSound
  private let history: PracticeParticipationStore
  @State private var position: PracticeTargetPosition
  @State private var selectedSession: PracticeSound?
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  @Environment(\.refreshAudioCleanupRecovery) private var refreshCleanupRecovery

  init(sound: PracticeSound, history: PracticeParticipationStore = .shared) {
    self.sound = sound
    self.history = history
    _position = State(initialValue: sound.position)
  }

  private var entries: [PracticeLibraryEntry] {
    PracticeLibrary.entries(soundID: sound.id, position: position)
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        Text(sound.name)
          .font(.system(.largeTitle, design: .serif))
          .accessibilityAddTraits(.isHeader)
        positionSelector
        if entries.isEmpty {
          Text("No \(sound.name.lowercased()) words at the \(position.rawValue) in this library.")
            .font(.body)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.library.empty")
          Text("Choose another position to see words you can practice.")
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
          Button("Practice \(sound.name.lowercased()) at the \(sound.position.rawValue)") {
            position = sound.position
          }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .accessibilityIdentifier("cadence.library.change-position")
        } else {
          Button {
            selectedSession = PracticeLibrary.session(soundID: sound.id, position: position)
          } label: {
            Text("Start practice")
          }
          .buttonStyle(DirectPracticeButtonStyle())
          .accessibilityHint(
            "Practices \(entries.prefix(3).map { $0.prompt.word }.joined(separator: ", "))"
          )
          .accessibilityIdentifier("cadence.library.start")
          Text("\(entries.count) words · Choose any word to start there.")
            .font(.subheadline)
            .foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
          LazyVStack(spacing: 0) {
            ForEach(entries) { entry in
              PracticeRule()
              Button {
                selectedSession = PracticeLibrary.session(
                  soundID: sound.id, position: position, startingAt: entry.id)
              } label: {
                Text(entry.prompt.word)
                  .font(.body)
                  .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
                  .contentShape(Rectangle())
              }
              .buttonStyle(.plain)
              .accessibilityHint(sessionHint(startingAt: entry.id))
              .accessibilityIdentifier("cadence.library.\(entry.id)")
            }
            PracticeRule()
          }
        }
      }
      .padding(24)
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    .foregroundStyle(DirectPracticeStyle.ink)
    .tint(DirectPracticeStyle.ink)
    .navigationTitle("Words to practice")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar(.visible, for: .navigationBar)
    // Large position labels must not show through a translucent bar behind the title.
    .toolbarBackground(DirectPracticeStyle.canvas, for: .navigationBar)
    .toolbarBackground(.visible, for: .navigationBar)
    .fullScreenCover(
      item: $selectedSession, onDismiss: { refreshCleanupRecovery() },
      content: { DirectPracticePlayerView(sound: $0, history: history) }
    )
  }

  private var positionSelector: some View {
    let layout =
      dynamicTypeSize.isAccessibilitySize
      ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
      : AnyLayout(HStackLayout(spacing: 8))
    return layout {
      ForEach(PracticeTargetPosition.allCases, id: \.self) { option in
        Button {
          position = option
        } label: {
          VStack(spacing: 6) {
            Text(option.label)
              .font(.body.weight(position == option ? .semibold : .regular))
              .fixedSize(horizontal: false, vertical: true)
            Rectangle()
              .fill(position == option ? DirectPracticeStyle.ink : Color.clear)
              .frame(height: 1)
              .accessibilityHidden(true)
          }
          .frame(maxWidth: .infinity, minHeight: 48)
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(option.label)
        .accessibilityValue(
          "\(PracticeLibrary.entries(soundID: sound.id, position: option).count) words"
        )
        .accessibilityAddTraits(position == option ? .isSelected : [])
        .accessibilityIdentifier("cadence.position.\(option.rawValue)")
      }
    }
  }

  private func sessionHint(startingAt id: String) -> String {
    let words =
      PracticeLibrary.session(
        soundID: sound.id, position: position, startingAt: id)?.prompts.map(\.word) ?? []
    return "Practices \(words.joined(separator: ", "))"
  }
}

struct PracticeWordSearchView: View {
  private let history: PracticeParticipationStore
  @State private var query = ""
  @State private var selectedSession: PracticeSound?
  @FocusState private var searchFocused: Bool
  @Environment(\.refreshAudioCleanupRecovery) private var refreshCleanupRecovery

  init(history: PracticeParticipationStore = .shared) {
    self.history = history
  }

  private var trimmedQuery: String { query.trimmingCharacters(in: .whitespacesAndNewlines) }

  private var matchingSounds: [PracticeSound] {
    guard !trimmedQuery.isEmpty else { return [] }
    return PracticeLibrary.sounds.filter {
      $0.id.compare(trimmedQuery, options: [.caseInsensitive, .diacriticInsensitive])
        == .orderedSame
        || $0.name.lowercased().hasPrefix(trimmedQuery.lowercased())
        || $0.symbol == trimmedQuery
        || (trimmedQuery.lowercased() == "th" && $0.id == "voiced-th")
    }
  }

  private var entries: [PracticeLibraryEntry] {
    guard !trimmedQuery.isEmpty else { return [] }
    return PracticeLibrary.entries(query: query).sorted { lhs, rhs in
      let leftExact =
        lhs.prompt.word.compare(trimmedQuery, options: [.caseInsensitive, .diacriticInsensitive])
        == .orderedSame
      let rightExact =
        rhs.prompt.word.compare(trimmedQuery, options: [.caseInsensitive, .diacriticInsensitive])
        == .orderedSame
      if leftExact != rightExact { return leftExact }
      if lhs.prompt.word != rhs.prompt.word { return lhs.prompt.word < rhs.prompt.word }
      return lhs.id < rhs.id
    }
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        HStack {
          Image(systemName: "magnifyingglass").accessibilityHidden(true)
          TextField("Search words", text: $query, axis: .vertical)
            .font(.body)
            .lineLimit(1...3)
            .frame(minHeight: 48)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .submitLabel(.search)
            .onSubmit { searchFocused = false }
            .onChange(of: query) { _, value in
              // The growing native input inserts a newline for Return. Treat it as Search.
              if value.contains(where: \.isNewline) {
                query = value.components(separatedBy: .newlines)
                  .joined(separator: " ").trimmingCharacters(in: .whitespaces)
                searchFocused = false
              }
            }
            .focused($searchFocused)
            .accessibilityLabel("Search words")
            .accessibilityIdentifier("cadence.search.field")
          if !query.isEmpty {
            Button {
              query = ""
            } label: {
              Image(systemName: "xmark")
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Clear search")
          }
        }
        .frame(minHeight: 48)
        PracticeRule()
        if trimmedQuery.isEmpty {
          Text("Find a word to practice.")
            .foregroundStyle(DirectPracticeStyle.muted)
        } else if entries.isEmpty && matchingSounds.isEmpty {
          VStack(alignment: .leading, spacing: 16) {
            Text("No words match “\(trimmedQuery)”.")
              .accessibilityIdentifier("cadence.search.empty")
            Text("Try fewer letters, or choose a sound from the home screen.")
              .foregroundStyle(DirectPracticeStyle.muted)
            Button("Clear search") { query = "" }
              .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          }
          .fixedSize(horizontal: false, vertical: true)
        } else {
          if !matchingSounds.isEmpty {
            Text("Sounds").font(.headline).accessibilityAddTraits(.isHeader)
            ForEach(matchingSounds) { sound in
              NavigationLink(sound.name) {
                PracticeSoundLibraryView(sound: sound, history: history)
              }
              .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
            }
          }
          if !entries.isEmpty {
            Text("Words").font(.headline).accessibilityAddTraits(.isHeader)
            LazyVStack(spacing: 0) {
              ForEach(entries) { entry in
                PracticeRule()
                Button {
                  searchFocused = false
                  selectedSession = PracticeLibrary.session(
                    soundID: entry.soundID, position: entry.position, startingAt: entry.id)
                } label: {
                  VStack(alignment: .leading, spacing: 4) {
                    Text(entry.prompt.word).font(.body)
                    Text(targetDescription(entry))
                      .font(.subheadline)
                      .foregroundStyle(DirectPracticeStyle.muted)
                  }
                  .fixedSize(horizontal: false, vertical: true)
                  .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
                  .padding(.vertical, 6)
                  .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(entry.prompt.word), \(targetDescription(entry))")
                .accessibilityHint("Starts a short practice with this word")
                .accessibilityIdentifier("cadence.search.result.\(entry.id)")
              }
              PracticeRule()
            }
          }
        }
      }
      .padding(24)
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    .foregroundStyle(DirectPracticeStyle.ink)
    .tint(DirectPracticeStyle.ink)
    .scrollDismissesKeyboard(.interactively)
    .navigationTitle("Search words")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar(.visible, for: .navigationBar)
    .onAppear { searchFocused = true }
    .task(id: query) {
      do { try await Task.sleep(for: .milliseconds(400)) } catch { return }
      guard !trimmedQuery.isEmpty else { return }
      let count = entries.count
      let soundCount = matchingSounds.count
      let results = [
        soundCount > 0 ? "\(soundCount) \(soundCount == 1 ? "sound group" : "sound groups")" : nil,
        count > 0 ? "\(count) practice \(count == 1 ? "entry" : "entries")" : nil,
      ].compactMap { $0 }
      AccessibilityNotification.Announcement(
        results.isEmpty ? "No words or sounds match" : results.joined(separator: ", ")
      ).post()
    }
    .fullScreenCover(
      item: $selectedSession, onDismiss: { refreshCleanupRecovery() },
      content: { DirectPracticePlayerView(sound: $0, history: history) }
    )
  }

  private func targetDescription(_ entry: PracticeLibraryEntry) -> String {
    let name = PracticeLibrary.sounds.first { $0.id == entry.soundID }?.name ?? entry.soundID
    let location = entry.position == .middle ? "in the middle" : "at the \(entry.position.rawValue)"
    return "\(name), \(location)"
  }
}
