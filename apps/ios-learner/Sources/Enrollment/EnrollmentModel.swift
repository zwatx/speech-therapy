import Accessibility
import Combine
import Foundation

private struct StoredEnrollment: Codable {
  let baseURL: URL
  let deviceToken: String
}

enum EnrollmentPhase: Equatable {
  case disconnected
  case loading
  case noAssignment
  case ready
  case failed(String)
}

typealias LearnerClientFactory = @MainActor (URL) throws -> any LearnerPracticeServicing
typealias LearnerPracticeSessionFactory =
  @MainActor (
    LearnerPracticeAssignment, any LearnerPracticeServicing, LearnerAttemptContext
  ) throws -> PracticeSessionModel

@MainActor
final class EnrollmentModel: ObservableObject {
  @Published var serverAddress = ""
  @Published var deviceToken = ""
  @Published private(set) var practiceSession: PracticeSessionModel?
  @Published private(set) var errorMessage: String?
  @Published private(set) var departureError: String?
  @Published private(set) var phase: EnrollmentPhase = .disconnected

  private let store: any EnrollmentCredentialStoring
  private let clientFactory: LearnerClientFactory
  private let practiceSessionFactory: LearnerPracticeSessionFactory
  private var isTransitioning = false
  private weak var warnedDepartureSession: PracticeSessionModel?
  private var pendingEnrollment: StoredEnrollment?
  private var pendingRequiresPersistence = false
  private var loadGeneration: UUID?

  init(
    store: any EnrollmentCredentialStoring = KeychainEnrollmentCredentialStore(),
    practiceSessionFactory: @escaping LearnerPracticeSessionFactory = {
      assignment, client, context in
      PracticeSessionModel(
        assignment: assignment, submitter: client, attemptContext: context,
        visualConfiguration: .disabled)
    },
    clientFactory: @escaping LearnerClientFactory = { baseURL in
      try LearnerAttemptAPIClient(baseURL: baseURL)
    }
  ) {
    self.store = store
    self.clientFactory = clientFactory
    self.practiceSessionFactory = practiceSessionFactory
    restoreCredential()
  }

  func connect() async {
    guard !isTransitioning else { return }
    do {
      guard
        let baseURL = URL(
          string: serverAddress.trimmingCharacters(in: .whitespacesAndNewlines)
        )
      else {
        throw LearnerAttemptAPIError.invalidEnrollment
      }
      #if DEBUG
        let isLocalDevelopment = ["localhost", "127.0.0.1"].contains(baseURL.host())
      #else
        let isLocalDevelopment = false
      #endif
      guard baseURL.scheme == "https" || isLocalDevelopment else {
        throw LearnerAttemptAPIError.insecureEndpoint
      }
      let token = deviceToken.trimmingCharacters(in: .whitespacesAndNewlines)
      guard
        token.range(
          of: #"^[A-Za-z0-9_-]{43}$"#,
          options: .regularExpression
        ) != nil
      else {
        throw LearnerAttemptAPIError.invalidEnrollment
      }
      let enrollment = StoredEnrollment(baseURL: baseURL, deviceToken: token)
      await loadAssignment(enrollment, persistAfterAuthentication: true)
    } catch {
      fail(error)
    }
  }

  func loadStoredAssignment() async {
    guard !isTransitioning else { return }
    guard phase == .loading, let pendingEnrollment else { return }
    await loadAssignment(pendingEnrollment, persistAfterAuthentication: false)
  }

  func retryAssignmentLoad() async {
    guard !isTransitioning else { return }
    guard let pendingEnrollment else {
      phase = .disconnected
      return
    }
    await loadAssignment(pendingEnrollment, persistAfterAuthentication: false)
  }

  @discardableResult
  func disconnect() -> Bool {
    withTransition {
      guard authorizeSessionChange(allowFileWarningDeparture: true) else { return false }
      do {
        try store.remove()
        pendingEnrollment = nil
        pendingRequiresPersistence = false
        practiceSession = nil
        phase = .disconnected
        errorMessage = nil
        deviceToken = ""
        departureError = nil
        return true
      } catch {
        if practiceSession != nil {
          let message = "Practice is paused because unlinking could not be confirmed. Try again."
          departureError = message
          errorMessage = message
          phase = .failed(message)
          announce(message)
        } else {
          fail(error)
        }
        return false
      }
    }
  }

  #if DEBUG
    @discardableResult
    func configureAccessibilityPreview(_ previewPhase: EnrollmentPhase) -> Bool {
      withTransition {
        guard authorizeSessionChange(allowFileWarningDeparture: true) else { return false }
        pendingEnrollment = nil
        pendingRequiresPersistence = false
        practiceSession = nil
        phase = previewPhase
        if case .failed(let message) = previewPhase {
          errorMessage = message
        } else {
          errorMessage = nil
        }
        return true
      }
    }
  #endif

  /// Only the brief synchronous metadata/owner transaction is guarded. Fetch awaits outside
  /// it, so a later Close/connect can revoke its exact generation before any result commits.
  private func withTransition(_ body: () -> Bool) -> Bool {
    guard !isTransitioning else { return false }
    isTransitioning = true
    defer { isTransitioning = false }
    return body()
  }

  private func authorizeSessionChange(allowFileWarningDeparture: Bool) -> Bool {
    // A blocked newer action must also invalidate an older in-flight fetch.
    loadGeneration = nil
    guard let session = practiceSession else {
      warnedDepartureSession = nil
      departureError = nil
      return true
    }
    let closed = session.requestClose()
    if !session.requiresCaptureCleanupBeforeDeparture, closed {
      warnedDepartureSession = nil
      departureError = nil
      return true
    }
    if allowFileWarningDeparture, session.canLeaveWithFileWarning {
      let alreadyWarned = warnedDepartureSession === session
      warnedDepartureSession = session
      if closed, alreadyWarned { return true }
    } else if !session.canLeaveWithFileWarning {
      warnedDepartureSession = nil
    }
    errorMessage = session.captureCleanupDetail
    announce("Practice cleanup needs attention. \(session.captureCleanupDetail)")
    return false
  }

  private func loadAssignment(
    _ enrollment: StoredEnrollment,
    persistAfterAuthentication: Bool
  ) async {
    var newGeneration: UUID?
    guard
      withTransition({
        guard authorizeSessionChange(allowFileWarningDeparture: false) else { return false }
        // Do not overwrite the previous pending credential until its actual owner permits it.
        if persistAfterAuthentication {
          pendingEnrollment = enrollment
          pendingRequiresPersistence = true
        }
        let generation = UUID()
        newGeneration = generation
        loadGeneration = generation
        practiceSession = nil
        phase = .loading
        errorMessage = nil
        return true
      }), let generation = newGeneration
    else { return }
    do {
      let client = try clientFactory(enrollment.baseURL)
      guard loadGeneration == generation else { return }
      let assignment = try await client.fetchCurrentAssignment(deviceToken: enrollment.deviceToken)
      _ = withTransition {
        guard loadGeneration == generation else { return false }
        guard authorizeSessionChange(allowFileWarningDeparture: false) else { return false }
        do {
          if persistAfterAuthentication || pendingRequiresPersistence {
            try store.save(JSONEncoder().encode(enrollment))
            pendingRequiresPersistence = false
          }
          pendingEnrollment = enrollment
          serverAddress = enrollment.baseURL.absoluteString
          deviceToken = ""
          guard let assignment else {
            practiceSession = nil
            phase = .noAssignment
            announce("No practice assignment is available yet.")
            return true
          }
          let context = try LearnerAttemptContext(
            deviceToken: enrollment.deviceToken,
            assignmentID: assignment.assignmentID,
            exerciseID: assignment.exerciseID)
          practiceSession = try practiceSessionFactory(assignment, client, context)
          phase = .ready
          announce("Practice assignment loaded.")
          return true
        } catch {
          failLoad(error)
          return false
        }
      }
    } catch {
      _ = withTransition {
        guard loadGeneration == generation else { return false }
        guard authorizeSessionChange(allowFileWarningDeparture: false) else { return false }
        failLoad(error)
        return false
      }
    }
  }

  /// Called only within an authorized metadata transaction, after generation validation.
  private func failLoad(_ error: Error) {
    if error as? LearnerAttemptAPIError == .sessionExpired {
      try? store.remove()
      pendingEnrollment = nil
      pendingRequiresPersistence = false
      practiceSession = nil
      phase = .disconnected
    }
    fail(error)
  }

  private func restoreCredential() {
    do {
      guard let data = try store.load() else { return }
      let enrollment = try JSONDecoder().decode(StoredEnrollment.self, from: data)
      pendingEnrollment = enrollment
      pendingRequiresPersistence = false
      serverAddress = enrollment.baseURL.absoluteString
      phase = .loading
    } catch {
      try? store.remove()
      pendingEnrollment = nil
      pendingRequiresPersistence = false
      practiceSession = nil
      phase = .disconnected
      errorMessage = "The saved practice link was invalid and has been removed."
    }
  }

  private func fail(_ error: Error) {
    let message =
      (error as? LocalizedError)?.errorDescription
      ?? "The practice link could not be loaded."
    errorMessage = message
    if phase != .disconnected { phase = .failed(message) }
    announce("Practice connection error. \(message)")
  }

  private func announce(_ message: String) {
    AccessibilityNotification.Announcement(message).post()
  }
}
