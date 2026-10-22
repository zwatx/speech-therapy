import CadenceContracts
import Foundation

struct LearnerAttemptContext: Equatable, Sendable {
  let deviceToken: String
  let assignmentID: String
  let exerciseID: String
  let repetitionIndex: Int
  let retryIndex: Int

  init(
    deviceToken: String,
    assignmentID: String,
    exerciseID: String,
    repetitionIndex: Int = 1,
    retryIndex: Int = 0
  ) throws {
    guard
      deviceToken.range(
        of: #"^[A-Za-z0-9_-]{43}$"#,
        options: .regularExpression
      ) != nil,
      exerciseID.range(
        of: #"^[A-Za-z0-9][A-Za-z0-9_.-]{3,79}$"#,
        options: .regularExpression
      ) != nil,
      assignmentID.range(
        of: #"^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$"#,
        options: .regularExpression
      ) != nil,
      (1...20).contains(repetitionIndex),
      (0...2).contains(retryIndex)
    else {
      throw LearnerAttemptAPIError.invalidEnrollment
    }
    self.deviceToken = deviceToken
    self.assignmentID = assignmentID
    self.exerciseID = exerciseID
    self.repetitionIndex = repetitionIndex
    self.retryIndex = retryIndex
  }

  func slot(repetitionIndex: Int, retryIndex: Int) throws -> Self {
    try LearnerAttemptContext(
      deviceToken: deviceToken,
      assignmentID: assignmentID,
      exerciseID: exerciseID,
      repetitionIndex: repetitionIndex,
      retryIndex: retryIndex
    )
  }
}

enum LearnerPracticeProgress: Equatable, Sendable {
  case ready(acceptedRepetitions: Int, repetitionIndex: Int, retryIndex: Int)
  case retryLimitReached(acceptedRepetitions: Int, repetitionIndex: Int)
  case completed(acceptedRepetitions: Int)
}

struct LearnerPracticeAssignment: Equatable, Sendable {
  let assignmentID: String
  let version: Int
  let exerciseRegistryVersion: String
  let exerciseDefinitionSHA256: String
  let exerciseID: String
  let protocolID: String
  let prompt: String
  let targetLabel: String
  let attemptTarget: Int
  let retryLimit: Int
  let progress: LearnerPracticeProgress

  init(
    assignmentID: String,
    version: Int,
    exerciseRegistryVersion: String,
    exerciseDefinitionSHA256: String,
    exerciseID: String,
    protocolID: String,
    prompt: String,
    targetLabel: String,
    attemptTarget: Int,
    retryLimit: Int,
    progress: LearnerPracticeProgress = .ready(
      acceptedRepetitions: 0,
      repetitionIndex: 1,
      retryIndex: 0
    )
  ) {
    self.assignmentID = assignmentID
    self.version = version
    self.exerciseRegistryVersion = exerciseRegistryVersion
    self.exerciseDefinitionSHA256 = exerciseDefinitionSHA256
    self.exerciseID = exerciseID
    self.protocolID = protocolID
    self.prompt = prompt
    self.targetLabel = targetLabel
    self.attemptTarget = attemptTarget
    self.retryLimit = retryLimit
    self.progress = progress
  }

  static let localPreview = LearnerPracticeAssignment(
    assignmentID: "assignment-local-preview",
    version: 1,
    exerciseRegistryVersion: "foundation-exercises-v1",
    exerciseDefinitionSHA256: String(repeating: "0", count: 64),
    exerciseID: "foundation-ball-initial-b-v1",
    protocolID: "bilabial-closure-v1",
    prompt: "ball",
    targetLabel: "Beginning /b/",
    attemptTarget: 5,
    retryLimit: 1
  )
}

enum LearnerAttemptAPIError: LocalizedError, Equatable {
  case insecureEndpoint
  case invalidEnrollment
  case invalidResponse
  case sessionExpired
  case rateLimited(retryAfterSeconds: Int)
  case rejected(status: Int)

  var errorDescription: String? {
    switch self {
    case .insecureEndpoint:
      return "Practice audio can only be sent over a secure connection."
    case .invalidEnrollment:
      return "This device needs a new practice link from the clinician."
    case .invalidResponse:
      return "The practice service returned an unreadable response."
    case .sessionExpired:
      return "This practice link has expired. Ask a caregiver or clinician for a new one."
    case .rateLimited(let retryAfterSeconds):
      let minutes = max(1, (retryAfterSeconds + 59) / 60)
      return
        "Practice is resting for a moment. Try again in about \(minutes) minute\(minutes == 1 ? "" : "s")."
    case .rejected(let status):
      return "The practice service could not complete this request (\(status))."
    }
  }
}

protocol AttemptSubmitting: Sendable {
  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt
}

protocol LearnerPracticeServicing: AttemptSubmitting {
  func fetchCurrentAssignment(
    deviceToken: String
  ) async throws -> LearnerPracticeAssignment?
}

actor LearnerAttemptAPIClient: LearnerPracticeServicing {
  private let attemptEndpoint: URL
  private let assignmentEndpoint: URL
  private let session: URLSession
  private let decoder = JSONDecoder()

  init(baseURL: URL, session: URLSession = .shared) throws {
    #if DEBUG
      let isLocalDevelopment = ["localhost", "127.0.0.1"].contains(baseURL.host())
    #else
      let isLocalDevelopment = false
    #endif
    guard baseURL.scheme == "https" || isLocalDevelopment else {
      throw LearnerAttemptAPIError.insecureEndpoint
    }
    attemptEndpoint = baseURL.appending(path: "api/v1/learner-attempts")
    assignmentEndpoint = baseURL.appending(path: "api/v1/learner-assignment")
    self.session = session
  }

  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt {
    guard
      attemptID.range(
        of: #"^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$"#,
        options: .regularExpression
      ) != nil
    else {
      throw LearnerAttemptAPIError.invalidResponse
    }
    var request = URLRequest(url: attemptEndpoint)
    request.httpMethod = "POST"
    request.setValue("audio/wav", forHTTPHeaderField: "content-type")
    request.setValue(
      "CadenceDevice \(context.deviceToken)",
      forHTTPHeaderField: "authorization"
    )
    request.setValue(attemptID, forHTTPHeaderField: "x-cadence-attempt-id")
    request.setValue(context.assignmentID, forHTTPHeaderField: "x-cadence-assignment-id")
    request.setValue(context.exerciseID, forHTTPHeaderField: "x-cadence-exercise-id")
    request.setValue(
      String(context.repetitionIndex),
      forHTTPHeaderField: "x-cadence-repetition-index"
    )
    request.setValue(
      String(context.retryIndex),
      forHTTPHeaderField: "x-cadence-retry-index"
    )

    let (data, response) = try await session.upload(for: request, fromFile: recording.url)
    guard let response = response as? HTTPURLResponse else {
      throw LearnerAttemptAPIError.invalidResponse
    }
    if response.statusCode == 401 {
      throw LearnerAttemptAPIError.sessionExpired
    }
    if response.statusCode == 429 {
      throw rateLimitError(response)
    }
    guard (200..<300).contains(response.statusCode) else {
      throw LearnerAttemptAPIError.rejected(status: response.statusCode)
    }
    do {
      let receipt = try decoder.decode(LearnerAttemptReceipt.self, from: data)
      guard receipt.feedbackAvailable == false, receipt.mediaRetained == false else {
        throw LearnerAttemptAPIError.invalidResponse
      }
      return receipt
    } catch {
      throw LearnerAttemptAPIError.invalidResponse
    }
  }

  func fetchCurrentAssignment(
    deviceToken: String
  ) async throws -> LearnerPracticeAssignment? {
    guard
      deviceToken.range(
        of: #"^[A-Za-z0-9_-]{43}$"#,
        options: .regularExpression
      ) != nil
    else {
      throw LearnerAttemptAPIError.invalidEnrollment
    }
    var request = URLRequest(url: assignmentEndpoint)
    request.httpMethod = "GET"
    request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
    request.setValue(
      "CadenceDevice \(deviceToken)",
      forHTTPHeaderField: "authorization"
    )
    let (data, response) = try await session.data(for: request)
    guard let response = response as? HTTPURLResponse else {
      throw LearnerAttemptAPIError.invalidResponse
    }
    if response.statusCode == 401 {
      throw LearnerAttemptAPIError.sessionExpired
    }
    if response.statusCode == 429 {
      throw rateLimitError(response)
    }
    if response.statusCode == 204 { return nil }
    guard response.statusCode == 200 else {
      throw LearnerAttemptAPIError.rejected(status: response.statusCode)
    }
    do {
      let payload = try decoder.decode(AssignmentPayload.self, from: data)
      return try payload.validated()
    } catch let error as LearnerAttemptAPIError {
      throw error
    } catch {
      throw LearnerAttemptAPIError.invalidResponse
    }
  }
}

private func rateLimitError(_ response: HTTPURLResponse) -> LearnerAttemptAPIError {
  guard
    let value = response.value(forHTTPHeaderField: "Retry-After"),
    let seconds = Int(value),
    (1...3600).contains(seconds)
  else {
    return .rejected(status: response.statusCode)
  }
  return .rateLimited(retryAfterSeconds: seconds)
}

private struct AssignmentPayload: Decodable {
  let schemaVersion: String
  let assignmentId: String
  let version: Int
  let exerciseRegistryVersion: String
  let exerciseDefinitionSha256: String
  let exerciseId: String
  let protocolId: String
  let prompt: String
  let targetLabel: String
  let attemptTarget: Int
  let retryLimit: Int
  let progress: ProgressPayload
  let visualProcessingEnabled: Bool
  let feedbackAvailable: Bool
  let releasePosture: String

  func validated() throws -> LearnerPracticeAssignment {
    let identifier = #"^[A-Za-z0-9][A-Za-z0-9_.-]{3,79}$"#
    guard
      schemaVersion == "learner-practice-assignment-v1",
      assignmentId.range(
        of: #"^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$"#,
        options: .regularExpression
      ) != nil,
      version > 0,
      exerciseRegistryVersion.range(
        of: identifier,
        options: .regularExpression
      ) != nil,
      exerciseDefinitionSha256.range(
        of: #"^[a-f0-9]{64}$"#,
        options: .regularExpression
      ) != nil,
      exerciseId.range(of: identifier, options: .regularExpression) != nil,
      protocolId.range(
        of: #"^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$"#,
        options: .regularExpression
      ) != nil,
      !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      prompt.count <= 80,
      !targetLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      targetLabel.count <= 120,
      (1...20).contains(attemptTarget),
      (0...2).contains(retryLimit),
      visualProcessingEnabled == false,
      feedbackAvailable == false,
      releasePosture == "candidate-silent-only"
    else {
      throw LearnerAttemptAPIError.invalidResponse
    }
    let validatedProgress = try progress.validated(
      attemptTarget: attemptTarget,
      retryLimit: retryLimit
    )
    return LearnerPracticeAssignment(
      assignmentID: assignmentId,
      version: version,
      exerciseRegistryVersion: exerciseRegistryVersion,
      exerciseDefinitionSHA256: exerciseDefinitionSha256,
      exerciseID: exerciseId,
      protocolID: protocolId,
      prompt: prompt,
      targetLabel: targetLabel,
      attemptTarget: attemptTarget,
      retryLimit: retryLimit,
      progress: validatedProgress
    )
  }
}

private struct ProgressPayload: Decodable {
  let status: String
  let acceptedRepetitions: Int
  let repetitionIndex: Int?
  let retryIndex: Int?

  func validated(
    attemptTarget: Int,
    retryLimit: Int
  ) throws -> LearnerPracticeProgress {
    guard (0...attemptTarget).contains(acceptedRepetitions) else {
      throw LearnerAttemptAPIError.invalidResponse
    }
    switch status {
    case "ready":
      guard
        let repetitionIndex,
        let retryIndex,
        repetitionIndex == acceptedRepetitions + 1,
        repetitionIndex <= attemptTarget,
        (0...retryLimit).contains(retryIndex)
      else {
        throw LearnerAttemptAPIError.invalidResponse
      }
      return .ready(
        acceptedRepetitions: acceptedRepetitions,
        repetitionIndex: repetitionIndex,
        retryIndex: retryIndex
      )
    case "retry-limit-reached":
      guard
        let repetitionIndex,
        retryIndex == nil,
        repetitionIndex == acceptedRepetitions + 1,
        repetitionIndex <= attemptTarget
      else {
        throw LearnerAttemptAPIError.invalidResponse
      }
      return .retryLimitReached(
        acceptedRepetitions: acceptedRepetitions,
        repetitionIndex: repetitionIndex
      )
    case "completed":
      guard
        acceptedRepetitions == attemptTarget,
        repetitionIndex == nil,
        retryIndex == nil
      else {
        throw LearnerAttemptAPIError.invalidResponse
      }
      return .completed(acceptedRepetitions: acceptedRepetitions)
    default:
      throw LearnerAttemptAPIError.invalidResponse
    }
  }
}
