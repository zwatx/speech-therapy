import Accessibility
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct PracticeView: View {
  @ObservedObject var session: PracticeSessionModel
  let onDisconnect: (() -> Void)?
  let onRefreshAssignment: (() -> Void)?
  /// Set while a closed session's unlinking couldn't be confirmed; practice stays paused.
  let departureError: String?
  @State private var feasibilityDocument: VisualFeasibilityReportDocument?
  @State private var feasibilityExportPresented = false
  @State private var feasibilityExportMessage: String?
  @State private var disconnectConfirmationPresented = false
  @ScaledMetric(relativeTo: .largeTitle) private var promptWordSize: CGFloat = 64

  private let ink = CadencePalette.primary
  private let destructive = CadencePalette.destructive
  private let accent = CadencePalette.accent

  init(
    session: PracticeSessionModel,
    onDisconnect: (() -> Void)? = nil,
    onRefreshAssignment: (() -> Void)? = nil,
    departureError: String? = nil
  ) {
    self.session = session
    self.onDisconnect = onDisconnect
    self.onRefreshAssignment = onRefreshAssignment
    self.departureError = departureError
  }

  var body: some View {
    GeometryReader { geometry in
      ZStack {
        CadencePalette.background.ignoresSafeArea()
        ScrollView {
          VStack(spacing: 0) {
            header
            practiceHeading
            wordPrompt
            phaseControls
            if showsPassiveCameraStatus {
              cameraPanel
                .padding(.top, 28)
            }
          }
          .frame(maxWidth: 560)
          .padding(.horizontal, 20)
          .padding(.top, 20)
          .padding(.bottom, 32)
          .frame(maxWidth: .infinity, minHeight: geometry.size.height, alignment: .top)
        }
        .scrollBounceBehavior(.basedOnSize)
      }
    }
    .foregroundStyle(ink)
    .tint(accent)
    .onDisappear { session.viewDidDisappear() }
    .interactiveDismissDisabled(session.requiresCaptureCleanupBeforeDeparture)
    .onChange(of: session.phase) { _, phase in
      AccessibilityNotification.Announcement(phase.accessibilityAnnouncement).post()
    }
    .confirmationDialog(
      "Unlink this device?",
      isPresented: $disconnectConfirmationPresented,
      titleVisibility: .visible
    ) {
      Button("Unlink device", role: .destructive) { onDisconnect?() }
      Button("Keep device linked", role: .cancel) {}
    } message: {
      Text(
        "This removes the saved practice link. A caregiver or clinician will need to link this device again."
      )
    }
    .fileExporter(
      isPresented: $feasibilityExportPresented,
      document: feasibilityDocument,
      contentType: .json,
      defaultFilename: "cadence-visual-feasibility"
    ) { result in
      switch result {
      case .success:
        session.completeVisualFeasibilityExport()
        feasibilityDocument = nil
        feasibilityExportMessage = "Derived feasibility report exported."
      case .failure:
        feasibilityExportMessage =
          "The report was not exported. The frozen report remains ready to retry."
      }
    }
  }

  private var header: some View {
    HStack(spacing: 12) {
      Text("Practice")
        .font(.title2.weight(.semibold))
        .accessibilityAddTraits(.isHeader)
      Spacer(minLength: 8)
      if onDisconnect != nil {
        Button("Unlink") { disconnectConfirmationPresented = true }
          .font(.subheadline.weight(.semibold))
          .padding(.horizontal, 18)
          .frame(minHeight: 44)
          .accessibilityLabel("Unlink this device")
      }
    }
    .padding(.bottom, 16)
    .overlay(alignment: .bottom) {
      Rectangle()
        .fill(CadencePalette.border)
        .frame(height: 1)
        .accessibilityHidden(true)
    }
  }

  private var practiceHeading: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("WORD \(session.assignmentProgress)")
        .font(.caption.monospacedDigit().weight(.semibold))
        .tracking(1.4)
        .foregroundStyle(CadencePalette.secondary)
        .accessibilityLabel("Word \(session.assignmentProgress)")
      ProgressView(
        value: completedRepetitions,
        total: Double(session.assignment.attemptTarget)
      )
      .tint(accent)
      .accessibilityLabel("Completed practice repetitions")
      .accessibilityValue(
        "\(Int(completedRepetitions)) of \(session.assignment.attemptTarget) repetitions"
      )
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.top, 20)
  }

  private var completedRepetitions: Double {
    if case .completed = session.phase {
      return Double(session.assignment.attemptTarget)
    }
    return Double(max(0, min(session.currentRepetition - 1, session.assignment.attemptTarget)))
  }

  private var wordPrompt: some View {
    VStack(alignment: .leading, spacing: 24) {
      VStack(alignment: .leading, spacing: 12) {
        Text("Say this word")
          .font(.subheadline.weight(.medium))
          .foregroundStyle(CadencePalette.secondary)
        Text(session.promptWord)
          .font(.system(size: promptWordSize, weight: .semibold))
          .minimumScaleFactor(0.7)
          .multilineTextAlignment(.leading)
        Text(session.targetLabel)
          .font(.body)
          .foregroundStyle(CadencePalette.secondary)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.leading, 12)
          .overlay(alignment: .leading) {
            Rectangle()
              .fill(accent)
              .frame(width: 2)
              .accessibilityHidden(true)
          }
      }
      .accessibilityElement(children: .combine)
      .accessibilityLabel(
        "Word: \(session.promptWord). Target: \(session.targetLabel)."
      )
      if !showsPassiveCameraStatus {
        cameraPanel
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.top, 28)
    .padding(.bottom, 28)
  }

  private var showsPassiveCameraStatus: Bool {
    session.visualState == .off
      && !session.visualCaptureAvailable
      && !session.visualFeasibilityReportAvailable
  }

  @ViewBuilder
  private var cameraPanel: some View {
    if session.showsCameraPreview,
      let previewSession = session.cameraPreviewSession
    {
      VStack(spacing: 10) {
        ZStack {
          CameraPreview(session: previewSession)
            .accessibilityHidden(true)
          Ellipse()
            .stroke(Color.white.opacity(0.9), style: StrokeStyle(lineWidth: 3, dash: [8, 7]))
            .padding(.horizontal, 50)
            .padding(.vertical, 18)
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 220)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay {
          RoundedRectangle(cornerRadius: 10)
            .stroke(ink.opacity(0.18), lineWidth: 1)
        }

        Label(session.cameraStatus, systemImage: session.cameraSystemImage)
          .font(.footnote.weight(.semibold))
          .foregroundStyle(ink)

        switch session.visualState {
        case .coaching(let coaching, _):
          Text(coaching.detail)
            .font(.footnote)
            .foregroundStyle(CadencePalette.secondary)
            .multilineTextAlignment(.center)
        case .ready:
          Text("Framing only. Camera frames stay on this device and are not saved.")
            .font(.footnote)
            .foregroundStyle(CadencePalette.secondary)
            .multilineTextAlignment(.center)
        default:
          EmptyView()
        }
        feasibilityExport
      }
    } else {
      VStack(alignment: .leading, spacing: 7) {
        Label(session.cameraStatus, systemImage: session.cameraSystemImage)
          .font(.footnote.weight(.medium))
        switch session.visualState {
        case .off where session.visualCaptureAvailable:
          if let scenario = session.visualFeasibilityScenarioLabel {
            Text("Feasibility scenario: \(scenario)")
              .font(.caption.monospaced())
          }
          Text(
            "Optional research framing checks your face and mouth on this device. Frames are not saved or uploaded."
          )
          // A closed session refuses framing; don't offer it while practice is paused.
          if departureError == nil {
            Button {
              Task { await session.prepareVisualCapture() }
            } label: {
              Label("Turn on camera framing", systemImage: "video.fill")
            }
            .buttonStyle(SecondaryPracticeButtonStyle(color: ink))
            .accessibilityHint("Requests camera permission for local framing checks")
          }
        case .permissionDenied:
          Text("A caregiver can allow camera access in Settings. Nothing was recorded.")
        case .unavailable(let message):
          Text(message)
        default:
          EmptyView()
        }
        feasibilityExport
      }
      .foregroundStyle(CadencePalette.secondary)
      .multilineTextAlignment(.leading)
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(.top, 18)
      .overlay(alignment: .top) {
        Rectangle()
          .fill(CadencePalette.border)
          .frame(height: 1)
          .accessibilityHidden(true)
      }
    }
  }

  @ViewBuilder
  private var feasibilityExport: some View {
    #if DEBUG
      if session.visualFeasibilityReportAvailable {
        Button {
          if let data = session.finalizeVisualFeasibilityReport() {
            feasibilityDocument = VisualFeasibilityReportDocument(data: data)
            feasibilityExportPresented = true
          } else {
            feasibilityExportMessage =
              "The derived feasibility report could not be prepared."
          }
        } label: {
          Label(
            session.visualFeasibilityReportIsFinalized
              ? "Retry feasibility report export"
              : "Export derived feasibility report",
            systemImage: "square.and.arrow.up"
          )
        }
        .buttonStyle(SecondaryPracticeButtonStyle(color: ink))
        .accessibilityHint(
          "Exports aggregate device and capture-quality measurements without images or raw landmarks"
        )
        Text(
          "The report contains aggregate measurements only—never camera frames or raw landmarks."
        )
        .font(.caption)
        .foregroundStyle(CadencePalette.secondary)
      }
      if let feasibilityExportMessage {
        Text(feasibilityExportMessage)
          .font(.caption)
          .foregroundStyle(CadencePalette.secondary)
      }
    #endif
  }

  @ViewBuilder
  private var phaseControls: some View {
    if let departureError {
      departureControls(departureError)
    } else {
      practiceControls
    }
  }

  /// The session is already closed, so Record and assignment refresh would do nothing. Owed
  /// capture cleanup keeps its own retry; unlinking is retried only through the guarded owner.
  private func departureControls(_ message: String) -> some View {
    let cleanupRetry = session.hasCaptureCleanupIssue && !session.captureCleanupRetryIDs.isEmpty
    return VStack(spacing: 16) {
      statusPanel(icon: "pause.circle.fill", title: "Practice is paused", detail: message)
        .accessibilityIdentifier("cadence.practice.departure-paused")
      if session.hasCaptureCleanupIssue {
        Text(session.captureCleanupDetail).fixedSize(horizontal: false, vertical: true)
        if cleanupRetry {
          Button("Retry cleanup") {
            for id in session.captureCleanupRetryIDs {
              session.retryCaptureCleanup(operationID: id)
            }
          }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
          .accessibilityIdentifier("cadence.practice.retry-cleanup")
        }
      }
      if let onDisconnect {
        if cleanupRetry {
          Button("Retry unlinking") { onDisconnect() }
            .buttonStyle(SecondaryPracticeButtonStyle(color: ink))
            .accessibilityIdentifier("cadence.practice.retry-unlinking")
        } else {
          Button("Retry unlinking") { onDisconnect() }
            .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
            .accessibilityIdentifier("cadence.practice.retry-unlinking")
        }
      }
    }
  }

  @ViewBuilder
  private var practiceControls: some View {
    switch session.phase {
    case .ready:
      VStack(spacing: 16) {
        Text("When you’re ready, say the word once.")
          .font(.body)
          .frame(maxWidth: .infinity, alignment: .leading)
        Button {
          Task { await session.startRecording() }
        } label: {
          Label("Record", systemImage: "mic.fill")
            .frame(maxWidth: .infinity, minHeight: 60)
        }
        .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
        .accessibilityHint("Starts a short microphone recording")
      }

    case .requestingPermission:
      statusPanel(
        icon: "mic.badge.plus",
        title: "Checking the microphone",
        detail: "Cadence records only after permission is granted."
      )

    case .recording:
      VStack(spacing: 16) {
        statusPanel(
          icon: "waveform",
          title: "Listening now",
          detail: "Say “\(session.promptWord),” then tap Stop."
        )
        HStack(spacing: 12) {
          Button("Cancel") { session.cancelRecording() }
            .buttonStyle(SecondaryPracticeButtonStyle(color: ink))
          Button {
            Task { await session.stopRecording() }
          } label: {
            Label("Stop", systemImage: "stop.fill")
          }
          .buttonStyle(PrimaryPracticeButtonStyle(color: destructive))
        }
      }

    case .captured(let summary):
      VStack(spacing: 16) {
        statusPanel(
          icon: "checkmark.circle.fill",
          title: "Clear recording",
          detail: String(
            format: "Captured %.1f seconds. Scoring is not connected yet.",
            summary.duration
          )
        )
        Button("Record another practice word") { session.tryAgain() }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
      }

    case .submitting:
      statusPanel(
        icon: "arrow.up.circle.fill",
        title: "Saving this practice try",
        detail: "The short recording is being sent securely, then removed from this device."
      )

    case .saved(let receipt):
      VStack(spacing: 16) {
        statusPanel(
          icon: receipt.status == .retryCapture
            ? "arrow.counterclockwise.circle.fill"
            : "checkmark.circle.fill",
          title: receipt.status == .retryCapture
            ? "Let’s record that once more"
            : "Practice try saved",
          detail: receipt.status == .retryCapture
            ? "The recording was not clear enough. It was removed, so try the word again."
            : "No correction is shown during this silent practice stage. The recording was removed."
        )
        Button("Continue") { session.tryAgain() }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
      }

    case .retry(let coaching):
      VStack(spacing: 16) {
        statusPanel(
          icon: "arrow.counterclockwise.circle.fill",
          title: coaching.title,
          detail: coaching.detail
        )
        Button("Try again") { session.tryAgain() }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
      }

    case .retryLimitReached:
      VStack(spacing: 16) {
        statusPanel(
          icon: "hand.raised.fill",
          title: "Pause this practice word",
          detail:
            "The assigned capture retry limit was reached. No pronunciation result is shown. A caregiver or clinician can decide what comes next."
        )
        if let onRefreshAssignment {
          Button("Check for an updated assignment") {
            if session.canRefreshAssignment, session.requestClose() { onRefreshAssignment() }
          }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
        }
      }

    case .completed:
      VStack(spacing: 16) {
        statusPanel(
          icon: "checkmark.seal.fill",
          title: "Practice dose complete",
          detail:
            "All assigned repetitions are finished. Your device stays linked for the next assignment."
        )
        if let onRefreshAssignment {
          Button("Check for new practice") {
            if session.canRefreshAssignment, session.requestClose() { onRefreshAssignment() }
          }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
        }
      }

    case .permissionDenied:
      VStack(spacing: 16) {
        statusPanel(
          icon: "mic.slash.fill",
          title: "Microphone is off",
          detail: "A caregiver can allow microphone access in Settings. Nothing was recorded."
        )
        Button("Back") { session.tryAgain() }
          .buttonStyle(SecondaryPracticeButtonStyle(color: ink))
      }

    case .failed(let message):
      VStack(spacing: 16) {
        statusPanel(
          icon: "exclamationmark.triangle.fill",
          title: session.assignmentRefreshRequired
            ? "Check the last practice save"
            : "Practice could not continue",
          detail: message
        )
        if session.hasCaptureCleanupIssue {
          Text(session.captureCleanupDetail).fixedSize(horizontal: false, vertical: true)
          if !session.captureCleanupRetryIDs.isEmpty {
            Button("Retry cleanup") {
              for id in session.captureCleanupRetryIDs {
                session.retryCaptureCleanup(operationID: id)
              }
            }
            .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
            .accessibilityIdentifier("cadence.practice.retry-cleanup")
          } else if session.canRefreshAssignment, let onRefreshAssignment {
            Button("Refresh assignment") {
              if session.requestClose() { onRefreshAssignment() }
            }
            .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
          }
        } else if session.assignmentRefreshRequired, let onRefreshAssignment {
          Button("Refresh assignment") {
            if session.canRefreshAssignment, session.requestClose() { onRefreshAssignment() }
          }
          .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
        } else {
          Button("Try again") { session.tryAgain() }
            .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
        }
      }
    }
  }

  private func statusPanel(icon: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: 14) {
      Image(systemName: icon)
        .font(.title2)
        .foregroundStyle(accent)
        .frame(width: 30)
        .accessibilityHidden(true)
      VStack(alignment: .leading, spacing: 5) {
        Text(title).font(.headline)
        Text(detail)
          .font(.subheadline)
          .foregroundStyle(CadencePalette.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, 18)
    .accessibilityElement(children: .combine)
  }
}

extension PracticePhase {
  fileprivate var accessibilityAnnouncement: String {
    switch self {
    case .ready:
      "Ready to record."
    case .requestingPermission:
      "Checking microphone permission."
    case .recording:
      "Recording started. Say the word, then select Stop."
    case .captured:
      "Clear recording captured."
    case .submitting:
      "Saving this practice try."
    case .saved(let receipt):
      receipt.status == .retryCapture
        ? "The recording was not clear enough. Please record it once more."
        : "Practice try saved."
    case .retry(let coaching):
      "Try again. \(coaching.title)."
    case .retryLimitReached:
      "The assigned retry limit was reached. Pause this practice word."
    case .completed:
      "Practice dose complete."
    case .permissionDenied:
      "Microphone permission is off."
    case .failed(let message):
      "Practice could not continue. \(message)"
    }
  }
}

struct PrimaryPracticeButtonStyle: ButtonStyle {
  let color: Color

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.headline)
      .foregroundStyle(Color.white)
      .frame(maxWidth: .infinity, minHeight: 52)
      .padding(.horizontal, 18)
      .background(color.opacity(configuration.isPressed ? 0.82 : 1))
      .clipShape(RoundedRectangle(cornerRadius: 10))
  }
}

struct SecondaryPracticeButtonStyle: ButtonStyle {
  let color: Color

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.headline)
      .foregroundStyle(color)
      .frame(maxWidth: .infinity, minHeight: 52)
      .padding(.horizontal, 18)
      .background(CadencePalette.control.opacity(configuration.isPressed ? 0.6 : 1))
      .clipShape(RoundedRectangle(cornerRadius: 10))
  }
}

#Preview {
  PracticeView(session: PracticeSessionModel(assignment: .localPreview))
}

// UIKit semantic colors adapt these SwiftUI surfaces to light, dark, and increased contrast.
enum CadencePalette {
  static let primary = Color(uiColor: .label)
  static let secondary = Color(uiColor: .secondaryLabel)
  static let background = Color(uiColor: .systemBackground)
  static let control = Color(uiColor: .secondarySystemBackground)
  static let accent = Color(uiColor: .systemBlue)
  static let border = Color(uiColor: .separator)
  static let destructive = Color(uiColor: .systemRed)
}
