import Accessibility
import SwiftUI

/// Plain self-view below the audio controls. It supplies no speech or facial scores.
struct PracticeMirrorPanel: View {
  @ObservedObject var mirror: DirectPracticeMirror
  let eligibility: DirectPracticeMirrorEligibility
  let compact: Bool
  let practicePaused: Bool
  let show: () -> Void
  let hide: () -> Void
  let cancel: () -> Void
  let retry: () -> Void
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  @AccessibilityFocusState private var retryFocused: Bool

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      PracticeRule()
      Text("Mirror").font(.headline).accessibilityAddTraits(.isHeader)
      Text(status).font(.subheadline).foregroundStyle(DirectPracticeStyle.muted)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("cadence.mirror.status")
      if case .live(let owner) = mirror.state, let presentation = mirror.presentation {
        PracticeMirrorVisiblePreview(
          presentation: presentation, owner: owner,
          maximumHeight: compact || dynamicTypeSize.isAccessibilitySize ? 200 : 320)
      }
      VStack(spacing: 4) {
        switch mirror.state {
        case .off:
          if eligibility.permitsAuthorizedShow {
            Button("Show mirror", action: show)
              .accessibilityIdentifier("cadence.mirror.show")
          }
        case .permissionPending, .awaitingActive, .starting:
          Button("Cancel mirror", action: cancel)
            .accessibilityIdentifier("cadence.mirror.cancel")
        case .live:
          Button("Hide mirror", action: hide)
            .accessibilityIdentifier("cadence.mirror.hide")
        case .denied:
          Button("Open camera settings") {
            if let url = URL(string: UIApplication.openSettingsURLString) {
              UIApplication.shared.open(url)
            }
          }.accessibilityIdentifier("cadence.mirror.settings")
          Button("Hide", action: hide).accessibilityIdentifier("cadence.mirror.hide")
        case .unavailable:
          Button("Hide", action: hide).accessibilityIdentifier("cadence.mirror.hide")
        case .stopFailed:
          Button("Retry turning off camera", action: retry)
            .accessibilityIdentifier("cadence.mirror.retry-stop")
            .accessibilityFocused($retryFocused)
        case .stopping:
          EmptyView()
        }
      }.buttonStyle(DirectPracticeButtonStyle(secondary: true))
    }
    .onAppear {
      if case .stopFailed = mirror.state { retryFocused = true }
    }
    .onChange(of: mirror.state) { _, state in
      let announcement: String? =
        switch state {
        case .permissionPending, .starting: "Starting the camera."
        case .live: nil  // The installed preview announces real versus generated content.
        case .denied: "Camera access is off."
        case .unavailable: "Camera isn't available."
        case .stopping: "Turning off the camera."
        case .stopFailed: "Camera hasn't confirmed it stopped. Retry is available."
        case .off: "Mirror off."
        case .awaitingActive: nil
        }
      if let announcement { AccessibilityNotification.Announcement(announcement).post() }
      if case .stopFailed = state { retryFocused = true }
      if case .off = state { retryFocused = false }
    }
  }

  private var status: String {
    switch mirror.state {
    case .off:
      "See yourself while you practice. The camera stays on this phone; nothing is saved."
    case .permissionPending, .starting: "Starting the camera…"
    case .awaitingActive: "Camera access is allowed. Return to the app to show the mirror."
    case .live: "Mirror on. Shown flipped, like a mirror. Not recorded or saved."
    case .denied: "Camera access is off. You can keep practicing with sound."
    case .unavailable: "The camera isn't available right now. You can keep practicing with sound."
    case .stopping: "Turning off the camera…"
    case .stopFailed:
      practicePaused
        ? "The camera hasn't confirmed it turned off. Use Retry turning off camera."
        : "The camera hasn't confirmed it turned off. You can keep practicing with sound."
    }
  }
}

private struct PracticeMirrorVisiblePreview: View {
  @ObservedObject var presentation: PracticeMirrorPresentation
  let owner: PracticeMirrorOwner
  let maximumHeight: CGFloat

  var body: some View {
    Group {
      if presentation.owner == owner, let source = presentation.source {
        switch source {
        case .camera:
          previewFrame {
            PracticeMirrorCameraPreview(presentation: presentation, owner: owner)
          }
        case .sample:
          VStack(alignment: .leading, spacing: 10) {
            Text("Sample image for testing — not your camera.")
              .font(.subheadline).fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.mirror.sample-label")
            previewFrame {
              Image(systemName: "person.crop.rectangle")
                .resizable().scaledToFit().padding(40)
                .foregroundStyle(DirectPracticeStyle.muted)
            }
          }
        }
      }
    }
    // Preview publication follows Live; label generated content explicitly.
    .onAppear { announceInstalledPreview() }
    .onChange(of: presentation.owner) { _, _ in announceInstalledPreview() }
  }

  private func announceInstalledPreview() {
    guard presentation.owner == owner, let source = presentation.source else { return }
    let announcement =
      switch source {
      case .sample: "Sample mirror shown."
      case .camera: "Mirror on."
      }
    AccessibilityNotification.Announcement(announcement).post()
  }

  private func previewFrame<Content: View>(@ViewBuilder content: @escaping () -> Content)
    -> some View
  {
    GeometryReader { geometry in
      content().frame(width: geometry.size.width, height: geometry.size.height).clipped()
    }
    .frame(height: maximumHeight)
    .overlay(Rectangle().stroke(DirectPracticeStyle.border, lineWidth: 1))
    .accessibilityHidden(true)
    .accessibilityIdentifier("cadence.mirror.preview")
  }
}
