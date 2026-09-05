import Accessibility
import SwiftUI
import UIKit

/// Live face preview on the word screen. It renders the model and forwards explicit taps only;
/// the coordinator owns every start, stop and scene change, so appearing or disappearing never
/// touches the camera. Movement bars are relative and never feed sound feedback.
struct FaceGuideInlinePreview: View {
  @ObservedObject var model: FaceGuideModel
  /// The learner's opt-in, remembered across words until Hide.
  let enabled: Bool
  let canShow: Bool
  /// Review and result give the feedback room: a shorter camera and no bars.
  let compact: Bool
  let show: @MainActor () -> Void
  let hide: @MainActor () -> Void
  let retryStop: @MainActor () -> Void
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  private enum Mode: Equatable {
    case unsupported, cleanup, live, waiting, denied, off
    case stopped(String)
  }

  private var mode: Mode {
    switch model.phase {
    case .unsupported: return .unsupported
    case .stopFailed: return .cleanup
    case .live: return .live
    case .requestingPermission, .awaitingActive: return .waiting
    case .denied: return enabled ? .denied : .off
    case .ready, .paused, .interrupted, .failed, .cameraBusy:
      return enabled ? .stopped(stoppedDetail) : .off
    }
  }

  var body: some View {
    content
      .frame(maxWidth: .infinity, alignment: .leading)
      .accessibilityElement(children: .contain)
      .accessibilityIdentifier("cadence.face-preview.panel")
      .onChange(of: model.phase) { old, phase in announce(old: old, phase: phase) }
  }

  @ViewBuilder
  private var content: some View {
    switch mode {
    case .unsupported:
      Label {
        Text("Face preview isn’t available on this phone. Recording works without it.")
          .accessibilityIdentifier("cadence.face-preview.status")
      } icon: {
        Image(systemName: "face.dashed")
      }
      .font(.footnote)
      .foregroundStyle(.secondary)
      .fixedSize(horizontal: false, vertical: true)
    case .cleanup:
      notice(
        icon: "exclamationmark.triangle",
        text: "The camera hasn’t finished turning off. Retry before recording again."
      ) {
        Button("Retry turning off camera") { retryStop() }
          .buttonStyle(CACCapsuleButtonStyle())
          .accessibilityIdentifier("cadence.face-preview.retry-stop")
      }
    case .live:
      VStack(alignment: .leading, spacing: 8) {
        camera
        if dynamicTypeSize.isAccessibilitySize { overlayControls }
        if !compact {
          FaceGuideMovementCard(
            movement: model.movement, compact: true,
            identifier: "cadence.face-preview.movement")
        }
      }
    case .waiting:
      notice(icon: nil, text: waitingDetail, progress: true) { EmptyView() }
    case .denied:
      notice(icon: "video.slash", text: "Camera access is off. Recording still works.") {
        Button("Open Settings") {
          if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
          }
        }
        .buttonStyle(CACCapsuleButtonStyle())
        showButton(title: "Try again")
        hideButton
      }
    case .off:
      notice(icon: "video.slash", text: "Face preview is off.") {
        showButton(title: "Show preview")
      }
    case .stopped(let detail):
      notice(icon: "video", text: detail) {
        showButton(title: "Show preview")
        hideButton
      }
    }
  }

  // MARK: Live camera

  /// Ready and recording keep the camera generous; review and result give feedback the room.
  private var cameraHeight: CGFloat { compact ? 140 : 252 }

  private var camera: some View {
    ZStack(alignment: .top) {
      Group {
        if let surface = model.cameraSurface {
          ZStack {
            Color.black
            FaceGuideCameraSurface(surface: surface)
          }
          .accessibilityElement(children: .ignore)
          .accessibilityLabel(cameraLabel(surface))
        } else {
          ZStack {
            CACDemoStyle.surface
            Image(systemName: "face.dashed")
              .font(.system(size: 40, weight: .light))
              .foregroundStyle(CACDemoStyle.muted)
          }
          .accessibilityElement(children: .ignore)
          .accessibilityLabel("Camera view not shown")
        }
      }
      .accessibilityIdentifier("cadence.face-preview.camera")
      if !dynamicTypeSize.isAccessibilitySize {
        overlayControls.padding(8)
      }
    }
    .frame(maxWidth: .infinity)
    .frame(height: cameraHeight)
    .clipShape(RoundedRectangle(cornerRadius: CACDemoStyle.cornerRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: CACDemoStyle.cornerRadius, style: .continuous)
        .strokeBorder(CACDemoStyle.separator)
        .allowsHitTesting(false)
        .accessibilityHidden(true))
  }

  /// An injected surface may describe itself; otherwise this is the real front camera.
  private func cameraLabel(_ surface: UIView) -> String {
    if let label = surface.accessibilityLabel, !label.isEmpty { return label }
    switch model.phase {
    case .live(.depthPending), .live(.tracking): return "Front camera with a face mesh"
    default: return "Front camera"
    }
  }

  private var overlayControls: some View {
    HStack(alignment: .top, spacing: 8) {
      if case .live(let tracking) = model.phase {
        FaceGuideStatusChip(tracking: tracking, identifier: "cadence.face-preview.status")
      }
      Spacer(minLength: 8)
      Button {
        hide()
      } label: {
        Label("Hide", systemImage: "eye.slash")
          .font(.footnote.weight(.semibold))
          .padding(.horizontal, 12)
          .padding(.vertical, 6)
          .background(.regularMaterial, in: Capsule())
          .frame(minWidth: 44, minHeight: 44, alignment: .topTrailing)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .foregroundStyle(CACDemoStyle.ink)
      .accessibilityLabel("Hide face preview")
      .accessibilityHint("Turns off the camera. Recording still works.")
      .accessibilityIdentifier("cadence.face-preview.hide")
    }
  }

  // MARK: Idle and recovery rows

  private func notice<Actions: View>(
    icon: String?, text: String, progress: Bool = false,
    @ViewBuilder actions: @escaping () -> Actions
  ) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(alignment: .firstTextBaseline, spacing: 10) {
        if progress {
          ProgressView().accessibilityHidden(true)
        } else if let icon {
          Image(systemName: icon)
            .foregroundStyle(CACDemoStyle.accent)
            .accessibilityHidden(true)
        }
        Text(text)
          .font(.subheadline)
          .foregroundStyle(CACDemoStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.face-preview.status")
      }
      if Actions.self != EmptyView.self {
        ViewThatFits(in: .horizontal) {
          HStack(spacing: 8) { actions() }
          VStack(alignment: .leading, spacing: 6) { actions() }
        }
      }
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .cacSurface()
  }

  private func showButton(title: String) -> some View {
    Button {
      show()
    } label: {
      Label(title, systemImage: "video")
    }
    .buttonStyle(CACCapsuleButtonStyle())
    .disabled(!canShow)
    .accessibilityHint("Turns on the front camera. Video isn’t saved.")
    .accessibilityIdentifier("cadence.face-preview.show")
  }

  private var hideButton: some View {
    Button("Hide") { hide() }
      .font(.subheadline.weight(.semibold))
      .foregroundStyle(CACDemoStyle.ink)
      .buttonStyle(.plain)
      .padding(.horizontal, 12)
      .frame(minHeight: 44)
      .contentShape(Rectangle())
      .accessibilityLabel("Hide face preview")
      .accessibilityIdentifier("cadence.face-preview.hide")
  }

  // MARK: Copy

  private var waitingDetail: String {
    model.phase == .awaitingActive
      ? "Camera access is allowed. Return to the app to start the preview."
      : "Waiting for camera access…"
  }

  private var stoppedDetail: String {
    let reason: String? =
      switch model.phase {
      case .paused: "The preview stopped when you left the app."
      case .interrupted: "The camera was interrupted."
      case .failed: "Face tracking stopped."
      case .cameraBusy: "The camera is in use right now."
      default: nil
      }
    if canShow {
      return reason ?? "Watch your lips and jaw while you say the word."
    }
    // Record restores an allowed preview; a new word can ask for access again.
    let resume =
      model.cameraAuthorized
      ? "The preview comes back when you record." : "The preview can start on the next word."
    return reason.map { "\($0) \(resume)" } ?? resume
  }

  private func announce(old: FaceGuidePhase, phase: FaceGuidePhase) {
    var wasLive = false
    if case .live = old { wasLive = true }
    let announcement: String? =
      switch phase {
      case .live: wasLive ? nil : "Face preview on."
      case .ready, .paused: wasLive ? "Face preview off." : nil
      case .denied: "Camera access is off. Recording still works."
      case .interrupted: "The camera was interrupted."
      case .failed: "Face tracking stopped."
      case .stopFailed: "The camera hasn’t finished turning off. Retry is available."
      case .unsupported, .requestingPermission, .awaitingActive, .cameraBusy: nil
      }
    if let announcement { AccessibilityNotification.Announcement(announcement).post() }
  }
}
