import Foundation
import XCTest
@testable import VisualSpeechCore

final class CoreTests: XCTestCase {
    private let outer = [Point(-1, -1), Point(0, -0.5), Point(1, -1), Point(0, -1.5)]
    private let inner = [Point(-0.5, -1), Point(0, -0.8), Point(0.5, -1), Point(0, -1.2)]
    private let contour = [Point(-2, 0), Point(0, -3), Point(2, 0)]
    private func features(_ transform: (Point) -> Point = { $0 }) -> [String: Double]? {
        geometry(outer: outer.map(transform), inner: inner.map(transform), contour: contour.map(transform),
                 leftEye: [transform(Point(-1, 0))], rightEye: [transform(Point(1, 0))])
    }
    func testGeometryHasKnownDimensionsAndArea() throws {
        let value = try XCTUnwrap(features())
        XCTAssertEqual(value["outerLipWidth"], 1)
        XCTAssertEqual(value["outerLipHeight"], 0.5)
        XCTAssertEqual(value["innerLipHeight"]!, 0.2, accuracy: 1e-10)
        XCTAssertEqual(value["innerLipPolygonArea"]!, 0.05, accuracy: 1e-10)
        XCTAssertEqual(value["eyeLineToLowestContourProxy"], 1.5)
    }
    func testTranslationUniformScaleAndRollDoNotChangeFeatures() throws {
        let expected = try XCTUnwrap(features())
        let rotated = try XCTUnwrap(features { point in
            let angle = 0.35, scale = 31.0
            return Point(400 + scale * (point.x * cos(angle) - point.y * sin(angle)),
                         300 + scale * (point.x * sin(angle) + point.y * cos(angle)))
        })
        for key in expected.keys { XCTAssertEqual(rotated[key]!, expected[key]!, accuracy: 1e-10) }
    }
    func testMissingInvalidAndDegenerateGeometryIsUnavailable() {
        XCTAssertNil(geometry(outer: [], inner: inner, contour: contour,
                              leftEye: [Point(-1, 0)], rightEye: [Point(1, 0)]))
        XCTAssertNil(features { Point($0.x, .nan) })
        XCTAssertNil(features { _ in Point(0, 0) })
    }
    func testInvertedAndNearVerticalEyeLinesAreUnavailable() {
        for angle in [Double.pi, Double.pi / 2, -Double.pi / 2, 1.55, 1.7] {
            XCTAssertNil(features { point in
                Point(point.x * cos(angle) - point.y * sin(angle),
                      point.x * sin(angle) + point.y * cos(angle))
            }, "roll \(angle)")
        }
    }
    func testJawProxyRespondsToContourOnly() throws {
        let baseline = try XCTUnwrap(features())
        let changed = try XCTUnwrap(geometry(outer: outer, inner: inner,
            contour: [Point(-2, 0), Point(0, -4), Point(2, 0)],
            leftEye: [Point(-1, 0)], rightEye: [Point(1, 0)]))
        XCTAssertEqual(changed["outerLipWidth"], baseline["outerLipWidth"])
        XCTAssertEqual(changed["eyeLineToLowestContourProxy"], 2)
    }
    private func clock(offset: Double = -0.25) -> AudioTimebase {
        AudioTimebase(referenceID: "synthetic-audio", sampleRateHz: 16000, durationSeconds: 2,
                      videoPTSToAudioOffsetSeconds: offset, alignmentMethod: "synthetic-known-clock",
                      alignmentUncertaintySeconds: nil)
    }
    func testSignedOffsetAndExclusiveAudioEnd() throws {
        XCTAssertNil(try clock().align(videoPTS: 0).sampleIndex)
        XCTAssertEqual(try clock().align(videoPTS: 0.25).sampleIndex, 0)
        XCTAssertEqual(try clock().align(videoPTS: 1.25).sampleIndex, 16000)
        XCTAssertNil(try clock().align(videoPTS: 2.25).sampleIndex)
        XCTAssertThrowsError(try clock(offset: .infinity).validate())
        XCTAssertThrowsError(try clock().align(videoPTS: .nan))
    }
    func testVariableRateSamplingPreservesGapsAndRejectsNonMonotonicPTS() throws {
        var sampler = try FrameSampler(fps: 10)
        XCTAssertTrue(try sampler.shouldSelect(pts: 2))
        XCTAssertFalse(try sampler.shouldSelect(pts: 2.03))
        XCTAssertTrue(try sampler.shouldSelect(pts: 2.11))
        XCTAssertTrue(try sampler.shouldSelect(pts: 4))
        XCTAssertThrowsError(try sampler.shouldSelect(pts: 4))
        XCTAssertThrowsError(try FrameSampler(fps: .nan))
        XCTAssertThrowsError(try FrameSampler(fps: 0))
    }
    func testDomainAndPermissionCannotBecomeNormalLabels() throws {
        for domain in ["unknown", "adult", "child-6-12", "other"] {
            let provenance = Provenance(sourceID: "fixture", rightsReference: "test-only-generated",
                localProcessingPermitted: true, ageDomain: domain, dialect: "unknown", speechCorrectness: "unlabeled")
            XCTAssertNoThrow(try provenance.validate())
        }
        for (permission, domain, correctness) in [(false, "unknown", "unlabeled"),
                                                  (true, "normal-child", "unlabeled"),
                                                  (true, "child-6-12", "correct")] {
            XCTAssertThrowsError(try Provenance(sourceID: "fixture", rightsReference: "test-only",
                localProcessingPermitted: permission, ageDomain: domain, dialect: "unknown",
                speechCorrectness: correctness).validate())
        }
    }
}
