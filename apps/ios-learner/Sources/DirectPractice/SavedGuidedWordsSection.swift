import Accessibility
import SwiftUI

@MainActor
struct SavedGuidedWordsSection: View {
  @ObservedObject var store: SavedGuidedWordsStore
  let allowsLiveRoutes: Bool
  let open: ([String]) -> Void
  @State private var confirmingClear = false
  @State private var clearError: String?

  var body: some View {
    Group {
      if store.entryIDs != nil || store.loadError != nil || clearError != nil {
        VStack(alignment: .leading, spacing: 12) {
          Text("Saved words").font(.title3.weight(.medium)).accessibilityAddTraits(.isHeader)
          if let entries = store.entries {
            Text(entries.map { $0.prompt.word }.joined(separator: ", "))
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.saved-words.words")
            Text("Your five words for review and practice. Saved on this device.")
              .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
              .fixedSize(horizontal: false, vertical: true)
            Button {
              guard allowsLiveRoutes, let ids = store.entryIDs,
                (try? SavedGuidedWordsValidation.entries(entryIDs: ids)) != nil
              else { return }
              open(ids)
            } label: {
              HStack {
                Text("Open saved words").fixedSize(horizontal: false, vertical: true)
                Spacer()
                Image(systemName: "chevron.right").accessibilityHidden(true)
              }.frame(maxWidth: .infinity, minHeight: 48).contentShape(Rectangle())
            }
            .buttonStyle(.plain).disabled(!allowsLiveRoutes)
            .accessibilityHint("Opens your five words so you can change them before starting.")
            .accessibilityIdentifier("cadence.saved-words.open")
          }
          if let error = store.loadError {
            Text(error).fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.saved-words.load-error")
          }
          if let clearError {
            Text(clearError).fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.saved-words.clear-error")
          }
          Button {
            confirmingClear = true
          } label: {
            Text("Clear saved words")
              .fixedSize(horizontal: false, vertical: true)
              .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain).disabled(!allowsLiveRoutes)
          .accessibilityIdentifier("cadence.saved-words.clear")
        }
        .padding(.bottom, 24)
      }
    }
    .sheet(isPresented: $confirmingClear) { clearConfirmation }
  }

  private var clearConfirmation: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Clear saved words?").font(.system(.largeTitle, design: .serif))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("cadence.saved-words.clear-confirmation-title")
        Text(
          "This removes your saved five-word set from this device. You can choose and save words again."
        )
        .accessibilityIdentifier("cadence.saved-words.clear-confirmation-message")
      }
      .fixedSize(horizontal: false, vertical: true).padding(24)
      .frame(maxWidth: 680).frame(maxWidth: .infinity)
    }
    .safeAreaInset(edge: .bottom) {
      VStack(spacing: 12) {
        Button("Cancel") { confirmingClear = false }
          .buttonStyle(DirectPracticeButtonStyle(secondary: true))
          .keyboardShortcut(.cancelAction)
          .accessibilityIdentifier("cadence.saved-words.clear-confirmation-cancel")
        Button("Clear saved words", role: .destructive) {
          guard allowsLiveRoutes else { return }
          do {
            try store.clear()
            clearError = nil
            confirmingClear = false
            AccessibilityNotification.Announcement("Saved words cleared.").post()
          } catch {
            let message = "Saved words could not be cleared. Try again."
            clearError = message
            confirmingClear = false
            AccessibilityNotification.Announcement(message).post()
          }
        }
        .buttonStyle(DirectPracticeButtonStyle(secondary: true))
        .accessibilityIdentifier("cadence.saved-words.clear-confirmation-confirm")
      }.padding(24).frame(maxWidth: 680).frame(maxWidth: .infinity)
        .background(DirectPracticeStyle.canvas)
    }
    .background(DirectPracticeStyle.canvas).foregroundStyle(DirectPracticeStyle.ink)
  }
}

@MainActor
struct SavedGuidedWordsSetupSection: View {
  @ObservedObject var session: LocalGuidedReviewSession
  @ObservedObject var store: SavedGuidedWordsStore
  @State private var saveError: String?
  private var ids: [String] { session.setupEntries.map(\.id) }
  private var saved: Bool { store.loadError == nil && store.entryIDs == ids }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text(
        "Keep these words on this device to open again from Home. Recordings and results are not saved with them."
      )
      .font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
      if store.entryIDs != nil && !saved {
        Text("Saving replaces your previously saved five words.").font(.subheadline)
      }
      if let error = store.loadError {
        Text("\(error) Return to Home to clear them.")
          .accessibilityIdentifier("cadence.guided.saved-words-status")
      } else if let saveError {
        Text(saveError).accessibilityIdentifier("cadence.guided.saved-words-status")
      } else if saved {
        Text("These five words are saved.").accessibilityIdentifier(
          "cadence.guided.saved-words-status")
      }
      Button {
        guard session.canSaveSetupWords, store.loadError == nil, !saved else { return }
        do {
          try store.save(entryIDs: ids)
          saveError = nil
          AccessibilityNotification.Announcement("These five words are saved.").post()
        } catch {
          let message = "These words could not be saved. Try again."
          saveError = message
          AccessibilityNotification.Announcement(message).post()
        }
      } label: {
        Text(saved ? "Five words saved" : "Save these five words")
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(!session.canSaveSetupWords || store.loadError != nil || saved)
      .accessibilityIdentifier("cadence.guided.save-words")
    }.fixedSize(horizontal: false, vertical: true)
      .onChange(of: ids) { _, _ in saveError = nil }
  }
}
