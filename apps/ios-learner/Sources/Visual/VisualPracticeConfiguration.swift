import Foundation

enum VisualFeasibilityScenario: String, Codable, CaseIterable, Equatable, Sendable {
  case protocolCompliant = "protocol-compliant"
  case lowLight = "low-light"
  case faceTooFar = "face-too-far"
  case faceTooClose = "face-too-close"
  case faceOffCenter = "face-off-center"
  case headTurned = "head-turned"
  case mouthCovered = "mouth-covered"
  case multipleFaces = "multiple-faces"
  case unstructured
}

struct VisualPracticeConfiguration: Equatable, Sendable {
  enum Mode: Equatable, Sendable {
    case disabled
    case localFeasibility
  }

  let mode: Mode
  let protocolID: String?
  let feasibilityScenario: VisualFeasibilityScenario?

  var isEnabled: Bool { mode == .localFeasibility }

  static let disabled = VisualPracticeConfiguration(
    mode: .disabled,
    protocolID: nil,
    feasibilityScenario: nil
  )

  #if DEBUG
    static let localBilabialFeasibility = VisualPracticeConfiguration(
      mode: .localFeasibility,
      protocolID: "bilabial-closure-v1",
      feasibilityScenario: .protocolCompliant
    )

    static func from(arguments: [String]) -> VisualPracticeConfiguration {
      guard arguments.contains("-CadenceVisualFeasibility") else { return .disabled }
      let scenario: VisualFeasibilityScenario
      if let flagIndex = arguments.firstIndex(of: "-CadenceVisualScenario"),
        arguments.indices.contains(flagIndex + 1),
        let selected = VisualFeasibilityScenario(rawValue: arguments[flagIndex + 1])
      {
        scenario = selected
      } else {
        scenario = .unstructured
      }
      return VisualPracticeConfiguration(
        mode: .localFeasibility,
        protocolID: "bilabial-closure-v1",
        feasibilityScenario: scenario
      )
    }
  #endif

  static var runtimeDefault: VisualPracticeConfiguration {
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("-CadenceVisualFeasibility") {
        return from(arguments: ProcessInfo.processInfo.arguments)
      }
    #endif
    return .disabled
  }
}

enum VisualCaptureState: Equatable {
  case off
  case requestingPermission
  case checking
  case ready(VisualQualitySnapshot)
  case coaching(VisualCaptureCoaching, VisualQualitySnapshot)
  case permissionDenied
  case unavailable(String)
}
