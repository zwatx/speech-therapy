import SwiftUI

struct EnrollmentView: View {
  @ObservedObject var model: EnrollmentModel
  @State private var disconnectConfirmationPresented = false

  private let accent = CadencePalette.accent

  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 0) {
          header
          switch model.phase {
          case .disconnected:
            connectionForm
          case .loading:
            loadingSection
          case .noAssignment:
            statusSection(
              title: "No practice assignment yet",
              detail:
                "The device link is active. Ask the clinician to assign a practice dose, then check again."
            )
          case .failed(let message):
            statusSection(
              title: "Practice could not load",
              detail: message
            )
          case .ready:
            EmptyView()
          }
        }
        .frame(maxWidth: 560)
        .padding(.horizontal, 20)
        .padding(.top, 20)
        .padding(.bottom, 32)
        .frame(maxWidth: .infinity)
      }
      .scrollBounceBehavior(.basedOnSize)
      .background(CadencePalette.background)
      .foregroundStyle(CadencePalette.primary)
      .toolbar(.hidden, for: .navigationBar)
    }
    .tint(accent)
    .confirmationDialog(
      "Unlink this device?",
      isPresented: $disconnectConfirmationPresented,
      titleVisibility: .visible
    ) {
      Button("Unlink device", role: .destructive) { model.disconnect() }
      Button("Keep device linked", role: .cancel) {}
    } message: {
      Text(
        "This removes the saved practice link. A caregiver or clinician will need to link this device again."
      )
    }
  }

  private var header: some View {
    HStack(alignment: .firstTextBaseline, spacing: 12) {
      Text("Cadence")
        .font(.title2.weight(.semibold))
        .accessibilityAddTraits(.isHeader)
      Spacer(minLength: 8)
      Text("DEVICE SETUP")
        .font(.caption2.monospaced().weight(.semibold))
        .tracking(1.2)
        .foregroundStyle(CadencePalette.secondary)
    }
    .padding(.bottom, 16)
    .overlay(alignment: .bottom) { sectionRule }
  }

  private var connectionForm: some View {
    VStack(alignment: .leading, spacing: 0) {
      VStack(alignment: .leading, spacing: 10) {
        Text("Connect this device")
          .font(.title.weight(.semibold))
          .accessibilityAddTraits(.isHeader)
        Text("Use the details from your caregiver or clinician.")
          .font(.body)
          .foregroundStyle(CadencePalette.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(.top, 24)
      .padding(.bottom, 24)

      VStack(alignment: .leading, spacing: 4) {
        Text("Practice server address")
          .font(.caption.weight(.semibold))
          .foregroundStyle(CadencePalette.secondary)
        TextField("https://", text: $model.serverAddress)
          .accessibilityLabel("Practice server address")
          .textContentType(.URL)
          .textInputAutocapitalization(.never)
          .autocorrectionDisabled()
          .keyboardType(.URL)
          .font(.body)
          .padding(.vertical, 15)
      }
      .padding(.bottom, 8)
      .overlay(alignment: .bottom) { sectionRule }

      VStack(alignment: .leading, spacing: 4) {
        Text("Practice link code")
          .font(.caption.weight(.semibold))
          .foregroundStyle(CadencePalette.secondary)
        SecureField("Enter your link code", text: $model.deviceToken)
          .accessibilityLabel("Practice link code")
          .textContentType(.password)
          .textInputAutocapitalization(.never)
          .autocorrectionDisabled()
          .font(.body)
          .padding(.vertical, 15)
      }
      .padding(.top, 16)
      .padding(.bottom, 8)
      .overlay(alignment: .bottom) { sectionRule }

      if let message = model.errorMessage {
        Label(message, systemImage: "exclamationmark.triangle.fill")
          .font(.subheadline)
          .foregroundStyle(CadencePalette.destructive)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityLabel("Connection error. \(message)")
          .padding(.top, 18)
      }
      Button("Connect for practice") {
        Task { await model.connect() }
      }
      .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
      .padding(.top, 24)
      Text("Your code is stored securely after the practice service verifies it.")
        .font(.footnote)
        .foregroundStyle(CadencePalette.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.top, 16)
    }
  }

  private var loadingSection: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text("Opening practice")
        .font(.title.weight(.semibold))
        .accessibilityAddTraits(.isHeader)
      ProgressView("Loading practice assignment")
        .accessibilityLabel("Loading practice assignment")
    }
    .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
    .padding(.top, 24)
  }

  private func statusSection(title: String, detail: String) -> some View {
    VStack(alignment: .leading, spacing: 0) {
      VStack(alignment: .leading, spacing: 12) {
        Text(title)
          .font(.title.weight(.semibold))
          .accessibilityAddTraits(.isHeader)
        Text(detail)
          .foregroundStyle(CadencePalette.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(.bottom, 24)
      .overlay(alignment: .bottom) { sectionRule }
      Button {
        Task { await model.retryAssignmentLoad() }
      } label: {
        Text("Check again").fixedSize(horizontal: false, vertical: true)
      }
      .buttonStyle(PrimaryPracticeButtonStyle(color: accent))
      .padding(.top, 24)
      Button(role: .destructive) {
        disconnectConfirmationPresented = true
      } label: {
        Text("Unlink this device")
      }
      .font(.subheadline.weight(.semibold))
      .foregroundStyle(CadencePalette.primary)
      .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
      .buttonStyle(.plain)
      .padding(.top, 12)
    }
    .padding(.top, 24)
  }

  private var sectionRule: some View {
    Rectangle()
      .fill(CadencePalette.border)
      .frame(height: 1)
      .accessibilityHidden(true)
  }
}
