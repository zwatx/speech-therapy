import Foundation
import XCTest

@testable import CadenceLearner

final class BundledLocalWordRecognizerFactoryTests: XCTestCase {
  private let identifier = "com.cadence.speechtherapy.learner"
  private let app = URL(fileURLWithPath: "/canonical/Cadence.app", isDirectory: true)

  private func accepts(_ app: URL, _ root: URL, resolvedApp: URL? = nil,
                       resolvedRoot: URL? = nil, identifier: String? = "com.cadence.speechtherapy.learner") -> Bool {
    BundledLocalWordRecognizerFactory.isCanonicalAppResourceLocation(
      appURL: app, resourceURL: root, resolvedAppURL: resolvedApp ?? app,
      resolvedResourceURL: resolvedRoot ?? root, bundleIdentifier: identifier)
  }

  func testOnlyCanonicalAppWhisperResourcesPathIsEligible() {
    let root = app.appendingPathComponent("WhisperResources", isDirectory: true)
    XCTAssertTrue(accepts(app, root))
    XCTAssertFalse(accepts(app, app.appendingPathComponent("Resources", isDirectory: true)))
    XCTAssertFalse(accepts(app, URL(fileURLWithPath: "/canonical/cache/WhisperResources", isDirectory: true)))
    XCTAssertFalse(accepts(app, root, identifier: nil))
    XCTAssertFalse(accepts(app, root, identifier: "com.cadence.speechtherapy.learner.tests"))
  }

  func testTestAndWorkBundlesCannotBecomeAppResources() {
    for path in ["/canonical/Cadence.xctest", "/canonical/work", "/canonical/Cadence.bundle"] {
      let other = URL(fileURLWithPath: path, isDirectory: true)
      XCTAssertFalse(accepts(other, other.appendingPathComponent("WhisperResources", isDirectory: true)))
    }
    XCTAssertFalse(accepts(URL(string: "https://example.invalid/Cadence.app")!,
                           URL(string: "https://example.invalid/Cadence.app/WhisperResources")!))
  }

  func testChangedCanonicalResolutionRejectsAppAndResourceSymlinks() {
    let root = app.appendingPathComponent("WhisperResources", isDirectory: true)
    XCTAssertFalse(accepts(app, root, resolvedApp: URL(fileURLWithPath: "/other/Cadence.app", isDirectory: true)))
    XCTAssertFalse(accepts(app, root, resolvedRoot: URL(fileURLWithPath: "/other/WhisperResources", isDirectory: true)))
    XCTAssertFalse(accepts(app, app.appendingPathComponent("../WhisperResources", isDirectory: true)))
  }

  private func directory() throws -> URL {
    let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
      .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
    addTeardownBlock { try FileManager.default.removeItem(at: root) }
    return root
  }

  func testMissingAndLinkedDirectoriesFailClosed() throws {
    let root = try directory()
    XCTAssertTrue(BundledLocalWordRecognizerFactory.isUnlinkedDirectory(root))
    XCTAssertFalse(BundledLocalWordRecognizerFactory.isUnlinkedDirectory(root.appendingPathComponent("missing")))
    let link = root.appendingPathComponent("linked", isDirectory: true)
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: root)
    XCTAssertFalse(BundledLocalWordRecognizerFactory.isUnlinkedDirectory(link))
  }

  @MainActor
  func testUnadmittedManifestCannotOpenInputOrProduceObservation() async throws {
    let root = try directory()
    try Data("{}".utf8).write(to: root.appendingPathComponent("RESOURCE-MANIFEST-v1.json"))
    let ownership = ProcessAudioFileOwnership()
    let provider = CoreMLLocalWordRecognizer(
      resources: WhisperBundledResources(rootURL: root, manifestSHA256:
        "3a5685954ba13a09b6430ed360afbb8c871033e9d2e90388568ef51a90b64b3d"),
      ownership: ownership)
    let request = LocalWordRecognitionRequest(operationID: UUID(), tryID: UUID(),
      fileURL: root.appendingPathComponent("absent.wav"), expectedWord: "sample")
    let receipt = await provider.check(request: request)
    XCTAssertEqual(receipt.status, .unavailable)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertTrue(ownership.protectedURLs.isEmpty)
  }

  @MainActor
  func testFactoryInitializationDoesNotBorrowAudio() {
    let ownership = ProcessAudioFileOwnership()
    let provider = BundledLocalWordRecognizerFactory.make(ownership: ownership)
    XCTAssertTrue(ownership.protectedURLs.isEmpty)
    provider.cancel(operationID: UUID())
    XCTAssertTrue(ownership.protectedURLs.isEmpty)
    // No Check is issued: the byte-identical provider initializer stores a worker
    // closure; it opens no resources and constructs no CoreML model.
  }
}
