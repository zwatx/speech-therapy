import SwiftUI

/// Keeps the existing dictionary attribution and local-recording information reachable
/// without bringing the legacy practice navigation into the main journey.
struct CACAboutView: View {
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    NavigationStack {
      Form {
        Section("Your recordings") {
          Text(
            "Recording and playback start only when you choose them. Audio stays on this device and is removed when you move on, exit, or leave the app. If removal cannot be confirmed, the app keeps cleanup controls available."
          )
        }
        Section("Face guide") {
          Text(
            "The word preview uses the camera after you start a sound check or choose Show preview. You can hide it while continuing with audio. It visualizes facial movement on this phone. Camera images, face meshes and movement values are not saved or sent. Movement indicators do not measure pronunciation correctness."
          )
        }
        Section("Pronunciation source") {
          Text(PracticeLibrary.sourceNotice)
          DisclosureGroup("Dictionary license") {
            Text(PracticeLibrary.sourceLicense)
              .font(.footnote)
              .textSelection(.enabled)
          }
        }
      }
      .navigationTitle("About")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .confirmationAction) {
          Button("Done") { dismiss() }
            .frame(minWidth: 44, minHeight: 44)
        }
      }
    }
    .tint(CACDemoStyle.accent)
  }
}
