import SwiftUI

/// One Clear owner shared by Home and the isolated generated component host.
@MainActor
struct PracticeParticipationHistorySection: View {
  @ObservedObject var history: PracticeParticipationStore
  let allowsLiveRoutes: Bool
  @State private var clearingHistory = false
  @State private var historyError: String?
  @State private var showingAllHistory = false

  var body: some View {
    Group {
      if !history.entries.isEmpty || history.loadError != nil || historyError != nil {
        VStack(alignment: .leading, spacing: 16) {
          Text("Recent practice").font(.title3.weight(.medium)).accessibilityAddTraits(.isHeader)
          Text("Sessions completed. This records taking part, not improvement.")
            .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
            .fixedSize(horizontal: false, vertical: true)
          ForEach(Array(history.entries.prefix(3))) { entry in
            PracticeRule()
            PracticeParticipationHistoryRow(
              entry: entry, history: history, allowsLiveRoutes: allowsLiveRoutes)
          }
          if history.entries.count > 3 {
            Button {
              showingAllHistory = true
            } label: {
              HStack(spacing: 12) {
                Text("View all practice (\(history.entries.count))")
                  .font(.body).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                Image(systemName: "chevron.right").font(.footnote).accessibilityHidden(true)
              }
              .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
              .contentShape(Rectangle())
            }
            .buttonStyle(.plain).accessibilityIdentifier("cadence.history.all")
          }
          if history.loadError != nil {
            Text("Saved practice history could not be read. Clear it to start a new history.")
              .font(.subheadline).fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.history.preview-load-error")
          }
          if let historyError {
            Text(historyError).font(.subheadline)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.history.clear-error")
          }
          Button {
            clearingHistory = true
          } label: {
            Text("Clear recent practice").frame(minHeight: 48).contentShape(Rectangle())
          }
          .buttonStyle(.plain).accessibilityIdentifier("cadence.history.clear")
        }
        .padding(.bottom, 32)
      }
    }
    // The presenter stays mounted after Clear removes the conditional preview/link.
    .navigationDestination(isPresented: $showingAllHistory) {
      PracticeParticipationHistoryView(history: history, allowsLiveRoutes: allowsLiveRoutes)
    }
    .sheet(isPresented: $clearingHistory) {
      PracticeHistoryClearConfirmation(
        onCancel: { clearingHistory = false },
        onClear: {
          clearingHistory = false
          do {
            try history.clear()
            historyError = nil
          } catch { historyError = "Recent practice could not be cleared. Try again." }
        }
      )
      .presentationDetents([.large])
    }
  }
}

/// Presentation only; the shared section remains the sole store and dismissal owner.
@MainActor
private struct PracticeHistoryClearConfirmation: View {
  let onCancel: () -> Void
  let onClear: () -> Void

  var body: some View {
    VStack(spacing: 0) {
      ScrollView {
        VStack(alignment: .leading, spacing: 16) {
          Text("Clear recent practice?")
            .font(.title2.weight(.semibold))
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier("cadence.history.clear-confirmation-title")
          Text("This removes all dates, sound groups and word counts saved on this device.")
            .font(.body)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.history.clear-confirmation-message")
        }
        .padding(24)
        .frame(maxWidth: 680, alignment: .leading)
        .frame(maxWidth: .infinity)
      }
      .scrollIndicators(.visible)
      .frame(maxHeight: .infinity)
      .accessibilityIdentifier("cadence.history.clear-confirmation-content")
      PracticeRule()
      VStack(spacing: 12) {
        Button(role: .cancel, action: onCancel) {
          Text("Cancel")
            .frame(maxWidth: .infinity, minHeight: 48)
            .contentShape(Rectangle())
        }
        .buttonStyle(.bordered)
        .tint(DirectPracticeStyle.ink)
        .keyboardShortcut(.cancelAction)
        .accessibilityIdentifier("cadence.history.clear-confirmation-cancel")
        Button(role: .destructive, action: onClear) {
          Text("Clear")
            .frame(maxWidth: .infinity, minHeight: 48)
            .contentShape(Rectangle())
        }
        .buttonStyle(.bordered)
        .tint(.red)
        .accessibilityLabel("Clear recent practice")
        .accessibilityIdentifier("cadence.history.clear-confirmation-confirm")
      }
      .font(.body)
      .padding(.horizontal, 24)
      .padding(.vertical, 16)
    }
    .foregroundStyle(DirectPracticeStyle.ink)
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
  }
}

@MainActor
struct PracticeParticipationHistoryView: View {
  @ObservedObject var history: PracticeParticipationStore
  let allowsLiveRoutes: Bool

  var body: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 16) {
        Text("Sessions completed. This records taking part, not improvement.")
          .font(.body).foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
        if history.loadError != nil {
          Text(
            "Saved practice history could not be read. Go back to clear saved history and start again."
          )
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.history.load-error")
        } else if history.entries.isEmpty {
          Text("No saved practice yet.")
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.history.empty")
        } else {
          Text("\(history.entries.count) saved sessions")
            .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
          ForEach(history.entries) { entry in
            PracticeRule()
            PracticeParticipationHistoryRow(
              entry: entry, history: history, allowsLiveRoutes: allowsLiveRoutes)
          }
          PracticeRule()
        }
      }
      .padding(24).frame(maxWidth: 680).frame(maxWidth: .infinity)
    }
    .accessibilityIdentifier("cadence.history.all-list")
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    .foregroundStyle(DirectPracticeStyle.ink).tint(DirectPracticeStyle.ink)
    .navigationTitle("Practice history").navigationBarTitleDisplayMode(.inline)
    .toolbar(.visible, for: .navigationBar)
    .toolbarBackground(DirectPracticeStyle.canvas, for: .navigationBar)
    .toolbarBackground(.visible, for: .navigationBar)
  }
}

@MainActor
private struct PracticeParticipationHistoryRow: View {
  let entry: PracticeParticipation
  let history: PracticeParticipationStore
  let allowsLiveRoutes: Bool
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  var body: some View {
    let sound = PracticeLibrary.sounds.first { $0.id == entry.soundID }
    let layout =
      dynamicTypeSize.isAccessibilitySize
      ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
      : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
    layout {
      VStack(alignment: .leading, spacing: 6) {
        Text(entry.completedAt, format: .dateTime.month(.abbreviated).day().hour().minute())
          .font(.body.weight(.medium))
        Text(
          "\(sound?.name ?? entry.soundID) · \(entry.wordCount) \(entry.wordCount == 1 ? "word" : "words")"
        )
        .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
      }
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityElement(children: .combine)
      .accessibilityIdentifier("cadence.history.entry-" + entry.id.uuidString)
      if let sound {
        if !dynamicTypeSize.isAccessibilitySize { Spacer(minLength: 4) }
        NavigationLink {
          if allowsLiveRoutes {
            PracticeSoundLibraryView(sound: sound, history: history)
          } else {
            Color.clear
          }
        } label: {
          HStack(spacing: 6) {
            Text("Practice again").font(.subheadline.weight(.medium))
              .fixedSize(horizontal: false, vertical: true)
            if !dynamicTypeSize.isAccessibilitySize {
              Image(systemName: "chevron.right").font(.footnote)
                .foregroundStyle(DirectPracticeStyle.muted).accessibilityHidden(true)
            }
          }
          .frame(minWidth: 44, minHeight: 44, alignment: .leading).contentShape(Rectangle())
        }
        .buttonStyle(.plain).accessibilityLabel("Practice \(sound.name) again")
        .accessibilityHint("Opens words for this sound")
        .accessibilityIdentifier("cadence.history.practice-" + entry.id.uuidString)
        .disabled(!allowsLiveRoutes)
      }
    }
  }
}
