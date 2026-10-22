import Foundation

struct NormalizedVisualPoint: Equatable, Sendable {
  let x: Double
  let y: Double
}

struct NormalizedVisualRect: Equatable, Sendable {
  let x: Double
  let y: Double
  let width: Double
  let height: Double

  var area: Double { width * height }
  var centerX: Double { x + width / 2 }
  var centerY: Double { y + height / 2 }
}

struct VisualFaceObservation: Equatable, Sendable {
  let bounds: NormalizedVisualRect
  let outerLip: [NormalizedVisualPoint]
  let innerLip: [NormalizedVisualPoint]
  let yawRadians: Double?
  let rollRadians: Double?
}

enum VisualCaptureIssue: String, Equatable, Sendable {
  case noFace
  case multipleFaces
  case faceTooFar
  case faceTooClose
  case faceOffCenter
  case headTurned
  case mouthLandmarksUnavailable
  case poseUnavailable
  case invalidObservation
}

struct VisualQualitySnapshot: Equatable, Sendable {
  let runtimeVersion: String
  let captureQualityScore: Double
  let issues: [VisualCaptureIssue]
  let faceCoverage: Double?
  let faceCenterOffset: Double?
  let mouthWidthRatio: Double?
  let mouthApertureRatio: Double?
  let yawRadians: Double?
  let rollRadians: Double?
  let processingLatencyMilliseconds: Double?

  init(
    runtimeVersion: String,
    captureQualityScore: Double,
    issues: [VisualCaptureIssue],
    faceCoverage: Double?,
    faceCenterOffset: Double?,
    mouthWidthRatio: Double?,
    mouthApertureRatio: Double?,
    yawRadians: Double?,
    rollRadians: Double?,
    processingLatencyMilliseconds: Double? = nil
  ) {
    self.runtimeVersion = runtimeVersion
    self.captureQualityScore = captureQualityScore
    self.issues = issues
    self.faceCoverage = faceCoverage
    self.faceCenterOffset = faceCenterOffset
    self.mouthWidthRatio = mouthWidthRatio
    self.mouthApertureRatio = mouthApertureRatio
    self.yawRadians = yawRadians
    self.rollRadians = rollRadians
    self.processingLatencyMilliseconds = processingLatencyMilliseconds
  }

  var isUsable: Bool { issues.isEmpty && captureQualityScore >= 0.7 }

  func recordingProcessingLatency(_ milliseconds: Double) -> VisualQualitySnapshot {
    guard milliseconds.isFinite, milliseconds >= 0 else { return self }
    return VisualQualitySnapshot(
      runtimeVersion: runtimeVersion,
      captureQualityScore: captureQualityScore,
      issues: issues,
      faceCoverage: faceCoverage,
      faceCenterOffset: faceCenterOffset,
      mouthWidthRatio: mouthWidthRatio,
      mouthApertureRatio: mouthApertureRatio,
      yawRadians: yawRadians,
      rollRadians: rollRadians,
      processingLatencyMilliseconds: milliseconds
    )
  }
}

struct VisualCaptureCoaching: Equatable, Sendable {
  let title: String
  let detail: String
}

struct VisualCaptureQualityAssessor: Sendable {
  static let runtimeVersion = "apple-vision-landmarks-feasibility-v1"

  func assess(_ faces: [VisualFaceObservation]) -> VisualQualitySnapshot {
    guard faces.count == 1, let face = faces.first else {
      let issue: VisualCaptureIssue = faces.isEmpty ? .noFace : .multipleFaces
      return VisualQualitySnapshot(
        runtimeVersion: Self.runtimeVersion,
        captureQualityScore: 0,
        issues: [issue],
        faceCoverage: nil,
        faceCenterOffset: nil,
        mouthWidthRatio: nil,
        mouthApertureRatio: nil,
        yawRadians: nil,
        rollRadians: nil
      )
    }
    guard isValid(face) else {
      return VisualQualitySnapshot(
        runtimeVersion: Self.runtimeVersion,
        captureQualityScore: 0,
        issues: [.invalidObservation],
        faceCoverage: nil,
        faceCenterOffset: nil,
        mouthWidthRatio: nil,
        mouthApertureRatio: nil,
        yawRadians: nil,
        rollRadians: nil
      )
    }

    let coverage = face.bounds.area
    let centerOffset = hypot(face.bounds.centerX - 0.5, face.bounds.centerY - 0.5)
    let lipPoints = face.outerLip + face.innerLip
    let mouthGeometry = geometry(for: lipPoints)
    var issues: [VisualCaptureIssue] = []

    if coverage < 0.1 { issues.append(.faceTooFar) }
    if coverage > 0.62 { issues.append(.faceTooClose) }
    if centerOffset > 0.18 { issues.append(.faceOffCenter) }
    if face.yawRadians == nil || face.rollRadians == nil {
      issues.append(.poseUnavailable)
    } else if abs(face.yawRadians ?? 0) > 0.38 || abs(face.rollRadians ?? 0) > 0.32 {
      issues.append(.headTurned)
    }
    if lipPoints.count < 8 || mouthGeometry == nil {
      issues.append(.mouthLandmarksUnavailable)
    }

    let sizeScore = rangeScore(value: coverage, ideal: 0.28, lower: 0.1, upper: 0.62)
    let centerScore = max(0, 1 - centerOffset / 0.6)
    let poseScore: Double
    if let yaw = face.yawRadians, let roll = face.rollRadians {
      poseScore = max(
        0,
        1 - max(abs(yaw) / 1.2667, abs(roll) / 1.0667)
      )
    } else {
      poseScore = 0
    }
    let landmarkScore = mouthGeometry == nil ? 0 : 1.0
    let quality = min(sizeScore, centerScore, poseScore, landmarkScore)

    return VisualQualitySnapshot(
      runtimeVersion: Self.runtimeVersion,
      captureQualityScore: quality.clamped(to: 0...1),
      issues: issues,
      faceCoverage: coverage,
      faceCenterOffset: centerOffset,
      mouthWidthRatio: mouthGeometry?.width,
      mouthApertureRatio: mouthGeometry?.height,
      yawRadians: face.yawRadians,
      rollRadians: face.rollRadians
    )
  }

  func coaching(for snapshot: VisualQualitySnapshot) -> VisualCaptureCoaching? {
    guard let issue = snapshot.issues.first else { return nil }
    switch issue {
    case .noFace:
      return VisualCaptureCoaching(
        title: "Bring your face into view",
        detail: "Center your face in the oval. The camera frames stay on this device."
      )
    case .multipleFaces:
      return VisualCaptureCoaching(
        title: "One person at a time",
        detail: "Ask anyone else in the camera view to step aside before practice."
      )
    case .faceTooFar:
      return VisualCaptureCoaching(
        title: "Move a little closer",
        detail: "Keep your whole face visible while making your mouth easier to see."
      )
    case .faceTooClose:
      return VisualCaptureCoaching(
        title: "Move a little farther back",
        detail: "Keep your face and mouth inside the guide."
      )
    case .faceOffCenter:
      return VisualCaptureCoaching(
        title: "Move toward the center",
        detail: "Place your face inside the oval before saying the word."
      )
    case .headTurned:
      return VisualCaptureCoaching(
        title: "Look toward the screen",
        detail: "Keep your face comfortably forward so the mouth remains observable."
      )
    case .mouthLandmarksUnavailable:
      return VisualCaptureCoaching(
        title: "Make your mouth visible",
        detail: "Check the lighting and move anything that is covering your mouth."
      )
    case .poseUnavailable:
      return VisualCaptureCoaching(
        title: "Camera check unavailable",
        detail: "Practice can continue without a visual framing result."
      )
    case .invalidObservation:
      return VisualCaptureCoaching(
        title: "Camera check unavailable",
        detail: "Practice can continue without the camera. No visual result was saved."
      )
    }
  }

  private func isValid(_ face: VisualFaceObservation) -> Bool {
    let bounds = face.bounds
    return bounds.x.isFinite && bounds.y.isFinite && bounds.width.isFinite
      && bounds.height.isFinite && bounds.width > 0 && bounds.height > 0
      && (face.yawRadians?.isFinite ?? true)
      && (face.rollRadians?.isFinite ?? true)
  }

  private func geometry(
    for points: [NormalizedVisualPoint]
  ) -> (width: Double, height: Double)? {
    guard
      let first = points.first,
      points.allSatisfy({ $0.x.isFinite && $0.y.isFinite })
    else { return nil }
    var minX = first.x
    var maxX = first.x
    var minY = first.y
    var maxY = first.y
    for point in points.dropFirst() {
      minX = min(minX, point.x)
      maxX = max(maxX, point.x)
      minY = min(minY, point.y)
      maxY = max(maxY, point.y)
    }
    let width = maxX - minX
    let height = maxY - minY
    guard width.isFinite, height.isFinite, width > 0, height > 0 else { return nil }
    return (width, height)
  }

  private func rangeScore(
    value: Double,
    ideal: Double,
    lower: Double,
    upper: Double
  ) -> Double {
    let span = value < ideal ? (ideal - lower) / 0.3 : (upper - ideal) / 0.3
    return max(0, 1 - abs(value - ideal) / span)
  }
}

extension Double {
  fileprivate func clamped(to range: ClosedRange<Double>) -> Double {
    min(max(self, range.lowerBound), range.upperBound)
  }
}
