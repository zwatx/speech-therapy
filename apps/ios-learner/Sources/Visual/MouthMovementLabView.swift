#if DEBUG
  import SwiftUI

  struct MouthMovementLabView: View {
    static var isAvailable: Bool { MouthMovementCapabilities.current.supportsFaceTracking }

    @State private var model = MouthMovementLabModel()
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.openURL) private var openURL

    var body: some View {
      ScrollView {
        VStack(alignment: .leading, spacing: 24) {
          VStack(alignment: .leading, spacing: 12) {
            Text("See movement, live.")
              .font(.system(.largeTitle, design: .serif))
              .accessibilityAddTraits(.isHeader)
            Text(
              "Explore how the camera follows visible jaw and lip movement. These measurements do not judge speech."
            )
            .foregroundStyle(DirectPracticeStyle.muted)
          }

          VStack(alignment: .leading, spacing: 12) {
            Text(statusTitle)
              .font(.headline)
            Text(statusDetail)
              .foregroundStyle(DirectPracticeStyle.muted)
              .fixedSize(horizontal: false, vertical: true)
            if model.isRunning || model.state == .requestingPermission {
              Button(model.state == .requestingPermission ? "Cancel" : "Stop camera") {
                model.stop()
              }
              .buttonStyle(DirectPracticeButtonStyle(secondary: true))
            } else if model.state == .denied {
              Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
              }
              .buttonStyle(DirectPracticeButtonStyle())
            } else if model.capabilities.supportsFaceTracking {
              Button("Start camera") { Task { await model.start() } }
                .buttonStyle(DirectPracticeButtonStyle())
                .accessibilityIdentifier("cadence.camera-lab.start")
            }
          }

          PracticeRule()

          VStack(alignment: .leading, spacing: 20) {
            Text("Expression measurements")
              .font(.title3.weight(.medium))
              .accessibilityAddTraits(.isHeader)
            measurement("Jaw opening", value: model.measurements?.jawOpen)
            measurement("Lip closure", value: model.measurements?.mouthClose)
            measurement("Lip funnel", value: model.measurements?.mouthFunnel)
            measurement("Lip pucker", value: model.measurements?.mouthPucker)
            Text(
              "Each reading runs from 0 (neutral) to 1 (maximum expression). Higher is not better."
            )
            .font(.footnote)
            .foregroundStyle(DirectPracticeStyle.muted)
          }

          PracticeRule()

          VStack(alignment: .leading, spacing: 10) {
            Text("Only on this device")
              .font(.headline)
            Text(
              "Camera images and expression readings are not saved or uploaded. No audio is recorded here. Closing this screen stops the camera."
            )
            Text(
              model.capabilities.hasTrueDepthCamera
                ? "TrueDepth camera available. This experiment uses ARKit face tracking; it does not collect depth maps or access Face ID data."
                : "This device uses front-camera face tracking. TrueDepth depth capture is not available."
            )
          }
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
        }
        .padding(24)
        .frame(maxWidth: 600)
        .frame(maxWidth: .infinity)
      }
      .background(DirectPracticeStyle.canvas.ignoresSafeArea())
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
      .navigationTitle("Camera lab")
      .navigationBarTitleDisplayMode(.inline)
      .onChange(of: scenePhase) { _, phase in
        if phase == .background { model.stop() }
        if phase == .active, model.state == .denied { model.stop() }
      }
      .onDisappear { model.stop() }
    }

    private func measurement(_ title: String, value: Double?) -> some View {
      VStack(alignment: .leading, spacing: 8) {
        HStack {
          Text(title)
          Spacer()
          Text(value.map { $0.formatted(.number.precision(.fractionLength(2))) } ?? "—")
            .monospacedDigit()
        }
        ProgressView(value: value ?? 0)
          .tint(DirectPracticeStyle.ink)
          .opacity(value == nil ? 0.35 : 1)
      }
      .accessibilityElement(children: .ignore)
      .accessibilityLabel(title)
      .accessibilityValue(
        value.map {
          $0.formatted(.number.precision(.fractionLength(2))) + " out of 1"
        } ?? "No reading")
    }

    private var statusTitle: String {
      switch model.state {
      case .idle: "Camera is off"
      case .requestingPermission: "Waiting for camera permission"
      case .tracking: "Following visible movement"
      case .noFace: "Looking for a face"
      case .multipleFaces: "More than one face"
      case .unavailableReading: "Readings unavailable"
      case .denied: "Camera permission is off"
      case .unavailable: "Camera tracking is unavailable"
      case .interrupted: "Camera stopped"
      case .failed: "Camera could not continue"
      }
    }

    private var statusDetail: String {
      switch model.state {
      case .idle: "Start when you are ready. The camera stays off until you choose."
      case .requestingPermission:
        "Allow camera access to explore movement, or cancel to leave it off."
      case .tracking:
        "The bars follow the current camera observations. They are not pronunciation scores."
      case .noFace:
        "Keep your face in front of the screen. Readings appear when tracking is available."
      case .multipleFaces: "Try with one person in the camera view so readings belong to one face."
      case .unavailableReading:
        "The camera is running, but expression readings are not available right now."
      case .denied:
        "You can allow camera access in Settings. Ordinary practice works without the camera."
      case .unavailable: "Ordinary practice is still available without camera tracking."
      case .interrupted: "Another activity interrupted the camera. Start again when you are ready."
      case .failed: "No readings were saved. You can try starting the camera again."
      }
    }
  }
#endif
