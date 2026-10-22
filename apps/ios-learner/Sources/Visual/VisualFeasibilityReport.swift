import Foundation
import UIKit

struct VisualFeasibilityReport: Codable, Equatable, Sendable {
  struct Configuration: Codable, Equatable, Sendable {
    let protocolID: String
    let scenario: VisualFeasibilityScenario
    let debugOnly: Bool
    let rawFramesRetained: Bool
    let rawLandmarksRetained: Bool
    let uploaded: Bool
  }

  struct Device: Codable, Equatable, Sendable {
    let hardwareIdentifier: String
    let systemName: String
    let systemVersion: String
    let appVersion: String
    let buildVersion: String
  }

  struct FrameSummary: Codable, Equatable, Sendable {
    let totalFrames: Int
    let usableFrames: Int
    let framesWithAnyIssue: Int
    let challengeHitFrames: Int
    let extractionFailures: Int
    let usableFrameRate: Double
    let meanQualityScore: Double
    let issueCounts: [String: Int]
  }

  struct LatencySummary: Codable, Equatable, Sendable {
    let measuredFrames: Int
    let meanMilliseconds: Double
    let maximumMilliseconds: Double
    let p95Bucket: String?
    let bucketCounts: [String: Int]
  }

  struct RuntimeSummary: Codable, Equatable, Sendable {
    let maximumThermalState: String
    let lowPowerModeObserved: Bool
  }

  let schemaVersion: String
  let sessionID: String
  let runtimeVersion: String
  let startedAt: String
  let endedAt: String
  let configuration: Configuration
  let device: Device
  let frames: FrameSummary
  let latency: LatencySummary
  let runtime: RuntimeSummary
}

struct VisualFeasibilityAccumulator {
  static let schemaVersion = "visual-feasibility-report-v1"

  let sessionID: UUID
  let runtimeVersion: String
  let protocolID: String
  let scenario: VisualFeasibilityScenario
  let startedAt: Date

  private(set) var observedFrames = 0
  private(set) var usableFrames = 0
  private(set) var framesWithAnyIssue = 0
  private(set) var challengeHitFrames = 0
  private(set) var extractionFailures = 0
  private(set) var qualityScoreTotal = 0.0
  private(set) var issueCounts: [String: Int] = [:]
  private(set) var latencyCount = 0
  private(set) var latencyTotal = 0.0
  private(set) var latencyMaximum = 0.0
  private(set) var latencyBuckets: [String: Int] = [:]
  private(set) var maximumThermalState = "nominal"
  private(set) var lowPowerModeObserved = false

  var totalFrames: Int { observedFrames + extractionFailures }

  init(
    sessionID: UUID = UUID(),
    runtimeVersion: String = VisualCaptureQualityAssessor.runtimeVersion,
    protocolID: String,
    scenario: VisualFeasibilityScenario,
    startedAt: Date = Date()
  ) {
    self.sessionID = sessionID
    self.runtimeVersion = runtimeVersion
    self.protocolID = protocolID
    self.scenario = scenario
    self.startedAt = startedAt
  }

  mutating func record(
    _ snapshot: VisualQualitySnapshot,
    thermalState: ProcessInfo.ThermalState,
    lowPowerMode: Bool
  ) {
    observedFrames += 1
    if snapshot.isUsable { usableFrames += 1 }
    if !snapshot.issues.isEmpty { framesWithAnyIssue += 1 }
    if isChallengeHit(snapshot) { challengeHitFrames += 1 }
    qualityScoreTotal += snapshot.captureQualityScore
    for issue in snapshot.issues {
      issueCounts[issue.rawValue, default: 0] += 1
    }
    if let latency = snapshot.processingLatencyMilliseconds,
      latency.isFinite,
      latency >= 0
    {
      latencyCount += 1
      latencyTotal += latency
      latencyMaximum = max(latencyMaximum, latency)
      latencyBuckets[latencyBucket(for: latency), default: 0] += 1
    }
    recordRuntime(thermalState: thermalState, lowPowerMode: lowPowerMode)
  }

  mutating func recordExtractionFailure(
    thermalState: ProcessInfo.ThermalState,
    lowPowerMode: Bool
  ) {
    extractionFailures += 1
    recordRuntime(thermalState: thermalState, lowPowerMode: lowPowerMode)
  }

  func report(
    endedAt: Date,
    device: VisualFeasibilityReport.Device
  ) -> VisualFeasibilityReport? {
    guard totalFrames > 0 else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return VisualFeasibilityReport(
      schemaVersion: Self.schemaVersion,
      sessionID: sessionID.uuidString.lowercased(),
      runtimeVersion: runtimeVersion,
      startedAt: formatter.string(from: startedAt),
      endedAt: formatter.string(from: endedAt),
      configuration: .init(
        protocolID: protocolID,
        scenario: scenario,
        debugOnly: true,
        rawFramesRetained: false,
        rawLandmarksRetained: false,
        uploaded: false
      ),
      device: device,
      frames: .init(
        totalFrames: totalFrames,
        usableFrames: usableFrames,
        framesWithAnyIssue: framesWithAnyIssue,
        challengeHitFrames: challengeHitFrames,
        extractionFailures: extractionFailures,
        usableFrameRate: Double(usableFrames) / Double(totalFrames),
        meanQualityScore: observedFrames == 0
          ? 0
          : qualityScoreTotal / Double(observedFrames),
        issueCounts: issueCounts
      ),
      latency: .init(
        measuredFrames: latencyCount,
        meanMilliseconds: latencyCount == 0 ? 0 : latencyTotal / Double(latencyCount),
        maximumMilliseconds: latencyMaximum,
        p95Bucket: p95Bucket(),
        bucketCounts: latencyBuckets
      ),
      runtime: .init(
        maximumThermalState: maximumThermalState,
        lowPowerModeObserved: lowPowerModeObserved
      )
    )
  }

  private mutating func recordRuntime(
    thermalState: ProcessInfo.ThermalState,
    lowPowerMode: Bool
  ) {
    let current = thermalLabel(thermalState)
    if thermalRank(current) > thermalRank(maximumThermalState) {
      maximumThermalState = current
    }
    lowPowerModeObserved = lowPowerModeObserved || lowPowerMode
  }

  private func isChallengeHit(_ snapshot: VisualQualitySnapshot) -> Bool {
    let expected: Set<VisualCaptureIssue>
    switch scenario {
    case .lowLight:
      expected = [
        .noFace,
        .mouthLandmarksUnavailable,
        .poseUnavailable,
        .invalidObservation,
      ]
    case .faceTooFar:
      expected = [.faceTooFar]
    case .faceTooClose:
      expected = [.faceTooClose]
    case .faceOffCenter:
      expected = [.faceOffCenter]
    case .headTurned:
      expected = [.headTurned]
    case .mouthCovered:
      expected = [.mouthLandmarksUnavailable]
    case .multipleFaces:
      expected = [.multipleFaces]
    case .protocolCompliant, .unstructured:
      expected = []
    }
    return !expected.isDisjoint(with: snapshot.issues)
  }

  private func latencyBucket(for milliseconds: Double) -> String {
    switch milliseconds {
    case ...25: "le-25"
    case ...50: "le-50"
    case ...100: "le-100"
    case ...200: "le-200"
    case ...500: "le-500"
    default: "gt-500"
    }
  }

  private func p95Bucket() -> String? {
    guard latencyCount > 0 else { return nil }
    let target = Int(ceil(Double(latencyCount) * 0.95))
    var cumulative = 0
    for bucket in ["le-25", "le-50", "le-100", "le-200", "le-500", "gt-500"] {
      cumulative += latencyBuckets[bucket, default: 0]
      if cumulative >= target { return bucket }
    }
    return nil
  }

  private func thermalLabel(_ state: ProcessInfo.ThermalState) -> String {
    switch state {
    case .nominal: "nominal"
    case .fair: "fair"
    case .serious: "serious"
    case .critical: "critical"
    @unknown default: "unknown"
    }
  }

  private func thermalRank(_ value: String) -> Int {
    switch value {
    case "nominal": 0
    case "fair": 1
    case "serious": 2
    case "critical": 3
    default: 4
    }
  }
}

@MainActor
enum VisualFeasibilityDeviceMetadata {
  static func current() -> VisualFeasibilityReport.Device {
    VisualFeasibilityReport.Device(
      hardwareIdentifier: hardwareIdentifier(),
      systemName: UIDevice.current.systemName,
      systemVersion: UIDevice.current.systemVersion,
      appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString")
        as? String ?? "unknown",
      buildVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion")
        as? String ?? "unknown"
    )
  }

  private static func hardwareIdentifier() -> String {
    var value = utsname()
    uname(&value)
    return withUnsafePointer(to: &value.machine) {
      $0.withMemoryRebound(to: CChar.self, capacity: 1) {
        String(cString: $0)
      }
    }
  }
}
