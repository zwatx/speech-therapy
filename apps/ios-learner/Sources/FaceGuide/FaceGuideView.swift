import Accessibility
import SwiftUI
import UIKit

/// Optional full-screen face guide. Opening is inert; the camera starts only from Start face
/// guide. Movement bars are relative ARKit coefficients and never feed sound feedback.
struct FaceGuideView: View {
  @StateObject private var model: FaceGuideModel
  @Environment(\.dismiss) private var dismiss
  @Environment(\.scenePhase) private var scenePhase
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  init() {
    _model = StateObject(wrappedValue: FaceGuideModel.standard())
  }

  init(model: @autoclosure @escaping () -> FaceGuideModel) {
    _model = StateObject(wrappedValue: model())
  }

  var body: some View {
    VStack(spacing: 0) {
      header
      FaceGuidePage(spacing: isLive && !dynamicTypeSize.isAccessibilitySize ? 12 : 20) {
        VStack(alignment: .leading, spacing: 6) {
          Text("Face guide")
            .font(.system(.title2, design: .rounded, weight: .bold))
            .accessibilityAddTraits(.isHeader)
          if !isLive {
            Text("See how your lips and jaw move while you practice.")
              .font(.body)
              .foregroundStyle(.secondary)
          }
        }
        .fixedSize(horizontal: false, vertical: true)
        if model.phase != .unsupported { cameraCard }
        if shouldShowStatus {
          Label {
            Text(status)
              .accessibilityIdentifier("cadence.face-guide.status")
          } icon: {
            if model.phase == .unsupported { Image(systemName: "face.dashed") }
          }
          .font(.subheadline)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
        }
        if case .live = model.phase {
          FaceGuideMovementCard(movement: model.movement)
        }
        Label("Camera stays on this phone. Nothing is saved.", systemImage: "lock")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      } actions: {
        actions
      }
    }
    .background(CACDemoStyle.background.ignoresSafeArea())
    .tint(CACDemoStyle.accent)
    .interactiveDismissDisabled(model.interactiveDismissDisabled)
    .onAppear { model.sceneChanged(FaceGuideScene(scenePhase)) }
    .onChange(of: scenePhase) { _, phase in model.sceneChanged(FaceGuideScene(phase)) }
    .onDisappear { model.viewDisappeared() }
    .onChange(of: model.readyToDismiss) { _, ready in
      if ready { dismiss() }
    }
    .onChange(of: model.phase) { old, phase in announce(old: old, phase: phase) }
  }

  private var isLive: Bool {
    if case .live = model.phase { return true }
    return false
  }

  private var shouldShowStatus: Bool {
    switch model.phase {
    case .live(.depthPending), .live(.tracking): false
    default: true
    }
  }

  private var header: some View {
    HStack {
      Button {
        model.close()
      } label: {
        Text("Close")
          .font(.body)
          .frame(minWidth: 44, minHeight: 44, alignment: .leading)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .foregroundStyle(CACDemoStyle.accent)
      .accessibilityIdentifier("cadence.face-guide.close")
      Spacer()
    }
    .padding(.horizontal, 20)
    .padding(.top, 4)
    .frame(maxWidth: CACDemoStyle.maxWidth + 40)
    .frame(maxWidth: .infinity)
  }

  private var cameraCard: some View {
    ZStack(alignment: .topLeading) {
      if let surface = model.cameraSurface {
        Color.black
        FaceGuideCameraSurface(surface: surface)
      } else {
        CACDemoStyle.surface
        Image(systemName: model.phase == .stopFailed ? "exclamationmark.triangle" : "face.dashed")
          .font(.system(size: 56, weight: .light))
          .foregroundStyle(CACDemoStyle.accent)
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      if case .live(let tracking) = model.phase {
        FaceGuideStatusChip(tracking: tracking).padding(12)
      }
    }
    .frame(maxWidth: .infinity)
    .frame(height: dynamicTypeSize.isAccessibilitySize ? 300 : (isLive ? 280 : 160))
    .clipShape(RoundedRectangle(cornerRadius: CACDemoStyle.cornerRadius, style: .continuous))
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(cameraLabel)
    .accessibilityIdentifier("cadence.face-guide.camera")
  }

  private var cameraLabel: String {
    switch model.phase {
    case .live(.depthPending), .live(.tracking): "Camera view with a face mesh following your face"
    case .live: "Camera view"
    default: "Camera off"
    }
  }

  private var status: String {
    switch model.phase {
    case .ready:
      "Tap Start face guide to turn on the front camera."
    case .unsupported:
      "Face guide needs TrueDepth face tracking, which isn’t available on this device."
    case .requestingPermission:
      "Waiting for camera access…"
    case .awaitingActive:
      "Camera access is allowed. Return to the app to start."
    case .live(.waitingForCamera):
      "Starting the camera…"
    case .live(.noFace):
      "Hold the phone at eye level so your whole face is in view."
    case .live(.depthPending), .live(.tracking):
      "Watch the mesh follow your lips and jaw as you say your words."
    case .denied:
      "Camera access is off. Turn it on in Settings to use the face guide."
    case .cameraBusy:
      "The camera is in use right now. Try again in a moment."
    case .paused:
      "The face guide stopped when you left the app. Start it again when you’re ready."
    case .interrupted:
      "The camera was interrupted. Start the face guide again when you’re ready."
    case .failed:
      "Face tracking stopped. Start the face guide again to retry."
    case .stopFailed:
      "The face guide hasn’t finished turning off the camera. Use Retry turning off camera."
    }
  }

  @ViewBuilder
  private var actions: some View {
    switch model.phase {
    case .ready, .paused, .interrupted, .failed, .cameraBusy:
      startButton
    case .requestingPermission, .awaitingActive:
      startButton.disabled(true)
    case .live:
      Button("Stop face guide") { model.stop() }
        .buttonStyle(CACPrimaryButtonStyle())
        .accessibilityIdentifier("cadence.face-guide.stop")
    case .denied:
      Button("Open Settings") {
        if let url = URL(string: UIApplication.openSettingsURLString) {
          UIApplication.shared.open(url)
        }
      }
      .buttonStyle(CACPrimaryButtonStyle())
      .accessibilityIdentifier("cadence.face-guide.settings")
    case .stopFailed:
      Button("Retry turning off camera") { model.retryStop() }
        .buttonStyle(CACPrimaryButtonStyle())
        .accessibilityIdentifier("cadence.face-guide.retry-stop")
    case .unsupported:
      EmptyView()
    }
  }

  private var startButton: some View {
    Button("Start face guide") { model.start() }
      .buttonStyle(CACPrimaryButtonStyle())
      .accessibilityHint("Turns on the front camera. Sound isn’t recorded.")
      .accessibilityIdentifier("cadence.face-guide.start")
  }

  private func announce(old: FaceGuidePhase, phase: FaceGuidePhase) {
    var wasLive = false
    if case .live = old { wasLive = true }
    let announcement: String? =
      switch phase {
      case .live: wasLive ? nil : "Face guide on."
      case .ready, .paused: wasLive ? "Face guide off." : nil
      case .denied: "Camera access is off."
      case .cameraBusy: "The camera is in use."
      case .interrupted: "The camera was interrupted."
      case .failed: "Face tracking stopped."
      case .stopFailed: "The camera hasn’t finished turning off. Retry is available."
      case .unsupported, .requestingPermission, .awaitingActive: nil
      }
    if let announcement { AccessibilityNotification.Announcement(announcement).post() }
  }
}

extension FaceGuideScene {
  init(_ phase: ScenePhase) {
    switch phase {
    case .active: self = .active
    case .background: self = .background
    default: self = .inactive
    }
  }
}

/// Scrolling column with actions pinned below; inline at accessibility text sizes.
private struct FaceGuidePage<Content: View, Actions: View>: View {
  let spacing: CGFloat
  @ViewBuilder let content: Content
  @ViewBuilder let actions: Actions
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: spacing) {
        content
        if dynamicTypeSize.isAccessibilitySize {
          VStack(spacing: 6) { actions }
        }
      }
      .padding(.horizontal, 24)
      .padding(.top, 12)
      .padding(.bottom, 24)
      .frame(maxWidth: CACDemoStyle.maxWidth)
      .frame(maxWidth: .infinity)
    }
    .scrollBounceBehavior(.basedOnSize)
    .safeAreaInset(edge: .bottom, spacing: 0) {
      if !dynamicTypeSize.isAccessibilitySize {
        VStack(spacing: 6) { actions }
          .padding(.horizontal, 24)
          .padding(.vertical, 8)
          .frame(maxWidth: CACDemoStyle.maxWidth)
          .frame(maxWidth: .infinity)
          .background(CACDemoStyle.background)
      }
    }
  }
}

/// Hosts the driver's own ARSCNView. The driver detaches it during teardown.
struct FaceGuideCameraSurface: UIViewRepresentable {
  let surface: UIView

  func makeUIView(context: Context) -> UIView {
    let container = UIView()
    container.clipsToBounds = true
    container.isAccessibilityElement = false
    return container
  }

  func updateUIView(_ container: UIView, context: Context) {
    guard surface.superview !== container else { return }
    for subview in container.subviews { subview.removeFromSuperview() }
    surface.frame = container.bounds
    surface.autoresizingMask = [.flexibleWidth, .flexibleHeight]
    container.addSubview(surface)
  }

  static func dismantleUIView(_ container: UIView, coordinator: ()) {
    for subview in container.subviews { subview.removeFromSuperview() }
  }
}

struct FaceGuideStatusChip: View {
  let tracking: FaceGuideTracking
  var identifier = "cadence.face-guide.tracking"

  private var label: String {
    switch tracking {
    case .waitingForCamera: "Starting camera"
    case .noFace: "No face found"
    case .depthPending: "Face found"
    case .tracking: "Face found · Depth camera active"
    }
  }

  private var dot: Color {
    switch tracking {
    case .waitingForCamera, .noFace: Color(uiColor: .systemGray)
    case .depthPending: CACDemoStyle.accent
    case .tracking: Color(uiColor: .systemCyan)
    }
  }

  var body: some View {
    HStack(spacing: 6) {
      Circle().fill(dot).frame(width: 8, height: 8)
      Text(label)
        .font(.footnote.weight(.semibold))
        .lineLimit(1)
        .minimumScaleFactor(0.8)
    }
    .padding(.horizontal, 10)
    .padding(.vertical, 6)
    .background(.regularMaterial, in: Capsule())
    .accessibilityElement(children: .combine)
    .accessibilityIdentifier(identifier)
  }
}

/// `compact` puts the bars side by side for the word screen; the full card stacks them.
struct FaceGuideMovementCard: View {
  let movement: FaceGuideMovement?
  var compact = false
  var identifier = "cadence.face-guide.movement"
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  var body: some View {
    VStack(alignment: .leading, spacing: compact ? 8 : 10) {
      if compact && !dynamicTypeSize.isAccessibilitySize {
        HStack(spacing: 16) { bars }
      } else {
        bars
      }
      Text(note)
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(compact ? 10 : 12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      CACDemoStyle.surface,
      in: RoundedRectangle(cornerRadius: CACDemoStyle.cornerRadius, style: .continuous)
    )
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier(identifier)
  }

  @ViewBuilder
  private var bars: some View {
    FaceGuideBar(title: "Jaw opening", value: movement?.jawOpening, compact: compact)
    FaceGuideBar(title: "Lip rounding", value: movement?.lipRounding, compact: compact)
  }

  private var note: String {
    switch (movement == nil, compact) {
    case (true, _): "Bars appear when your face is in view."
    case (false, true): "Bars follow your movement. They aren’t a score."
    case (false, false): "Bars move with your face. They aren’t a score."
    }
  }
}

/// Relative fill only; no number, target or correctness marker.
struct FaceGuideBar: View {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  let title: String
  let value: Double?
  var compact = false

  var body: some View {
    VStack(alignment: .leading, spacing: compact ? 4 : 6) {
      Text(title).font((compact ? Font.footnote : .subheadline).weight(.semibold))
      GeometryReader { geometry in
        ZStack(alignment: .leading) {
          Capsule().fill(CACDemoStyle.separator.opacity(0.5))
          if let value {
            Capsule().fill(CACDemoStyle.accent)
              .frame(width: max(0, geometry.size.width * value))
          }
        }
      }
      .frame(height: compact ? 8 : 10)
      .animation(reduceMotion ? nil : .easeOut(duration: 0.1), value: value)
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(title)
    .accessibilityValue(spokenValue)
  }

  private var spokenValue: String {
    guard let value else { return "No reading" }
    if value < 0.15 { return "Little" }
    return value < 0.5 ? "Some" : "A lot"
  }
}
