import Foundation

public struct Point: Sendable {
    public let x: Double
    public let y: Double
    public init(_ x: Double, _ y: Double) { self.x = x; self.y = y }
}

public enum ResearchError: Error, CustomStringConvertible {
    case invalid(String)
    public var description: String {
        switch self { case .invalid(let message): message }
    }
}

/// Pixel coordinates, origin lower left. Scale and roll are removed using eye centers.
/// These are visible contour observations, never jaw articulation or correctness labels.
public func geometry(
    outer: [Point], inner: [Point], contour: [Point], leftEye: [Point], rightEye: [Point]
) -> [String: Double]? {
    let groups = [outer, inner, contour, leftEye, rightEye]
    guard outer.count >= 3, inner.count >= 3, contour.count >= 3,
          !leftEye.isEmpty, !rightEye.isEmpty,
          groups.joined().allSatisfy({ $0.x.isFinite && $0.y.isFinite }) else { return nil }
    func center(_ points: [Point]) -> Point {
        Point(points.map(\.x).reduce(0, +) / Double(points.count),
              points.map(\.y).reduce(0, +) / Double(points.count))
    }
    let a = center(leftEye), b = center(rightEye)
    // Pick image-left eye first; Vision's anatomical left/right naming is immaterial.
    let left = a.x <= b.x ? a : b, right = a.x <= b.x ? b : a
    let dx = right.x - left.x, dy = right.y - left.y
    let scale = hypot(dx, dy)
    // Near a vertical eye line, image-left ordering becomes unstable. This is a
    // geometric domain limit, not a speech or child-development quality label.
    guard scale.isFinite, scale > 1e-6, dx / scale > 0.1 else { return nil }
    let origin = Point((left.x + right.x) / 2, (left.y + right.y) / 2)
    func normalize(_ p: Point) -> Point {
        let x = p.x - origin.x, y = p.y - origin.y
        return Point((x * dx + y * dy) / (scale * scale),
                     (-x * dy + y * dx) / (scale * scale))
    }
    let lips = outer.map(normalize), opening = inner.map(normalize)
    let jaw = contour.map(normalize)
    guard center(lips).y < 0 else { return nil } // Inverted/over-rolled observations.
    func width(_ points: [Point]) -> Double { points.map(\.x).max()! - points.map(\.x).min()! }
    func height(_ points: [Point]) -> Double { points.map(\.y).max()! - points.map(\.y).min()! }
    func area(_ points: [Point]) -> Double {
        abs(points.indices.reduce(0) { sum, i in
            let next = points[(i + 1) % points.count]
            return sum + points[i].x * next.y - next.x * points[i].y
        }) / 2
    }
    let values = [
        "outerLipWidth": width(lips), "outerLipHeight": height(lips),
        "innerLipWidth": width(opening), "innerLipHeight": height(opening),
        "innerLipPolygonArea": area(opening),
        "eyeLineToLowestContourProxy": -(jaw.map(\.y).min()!),
        "outerLipCenterX": center(lips).x, "outerLipCenterY": center(lips).y
    ]
    guard values.values.allSatisfy(\.isFinite), width(lips) > 1e-6 else { return nil }
    return values
}

public struct AudioTimebase: Codable, Sendable {
    public let referenceID: String
    public let sampleRateHz: Double
    public let durationSeconds: Double
    public let videoPTSToAudioOffsetSeconds: Double
    public let alignmentMethod: String
    public let alignmentUncertaintySeconds: Double?

    public func validate() throws {
        guard !referenceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !alignmentMethod.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              sampleRateHz.isFinite, (1...384_000).contains(sampleRateHz),
              durationSeconds.isFinite, durationSeconds > 0,
              videoPTSToAudioOffsetSeconds.isFinite,
              durationSeconds * sampleRateHz < Double(Int64.max),
              alignmentUncertaintySeconds.map({ $0.isFinite && $0 >= 0 }) ?? true
        else { throw ResearchError.invalid("Invalid explicit audio timebase") }
    }

    public func align(videoPTS: Double) throws -> (seconds: Double, sampleIndex: Int64?) {
        try validate()
        let time = videoPTS + videoPTSToAudioOffsetSeconds
        guard videoPTS.isFinite, time.isFinite else {
            throw ResearchError.invalid("Nonfinite video/audio timestamp")
        }
        // Out-of-range timestamps remain visible; never clamp them to a valid sample.
        return (time, time >= 0 && time < durationSeconds
                ? Int64((time * sampleRateHz).rounded(.down)) : nil)
    }
}

public struct Provenance: Codable, Sendable {
    public let sourceID: String
    public let rightsReference: String
    public let localProcessingPermitted: Bool
    public let ageDomain: String
    public let dialect: String
    public let speechCorrectness: String

    public func validate() throws {
        guard !sourceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !rightsReference.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              localProcessingPermitted,
              ["unknown", "adult", "child-6-12", "other"].contains(ageDomain),
              !dialect.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              speechCorrectness == "unlabeled"
        else { throw ResearchError.invalid("Provenance requires permission, explicit domain, and unlabeled correctness") }
    }
}

/// Preserve actual PTS; thinning never fabricates constant-rate observations.
public struct FrameSampler {
    private let interval: Double
    private var previousPTS: Double?
    private var lastSelectedPTS: Double?
    public init(fps: Double) throws {
        guard fps.isFinite, fps > 0, fps <= 60 else {
            throw ResearchError.invalid("fps must be finite and in (0, 60]")
        }
        interval = 1 / fps
    }
    public mutating func shouldSelect(pts: Double) throws -> Bool {
        guard pts.isFinite, previousPTS.map({ pts > $0 }) ?? true else {
            throw ResearchError.invalid("Video presentation timestamps must be finite and strictly increasing")
        }
        previousPTS = pts
        guard lastSelectedPTS.map({ pts - $0 + 1e-9 >= interval }) ?? true else { return false }
        lastSelectedPTS = pts
        return true
    }
}
