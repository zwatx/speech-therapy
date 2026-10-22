import CryptoKit
import Foundation
import XCTest

@testable import CadenceLearner

/// Explicit sensor-free framework verification; excluded from ordinary unit selections.
@MainActor
final class LocalWordRecognitionFrameworkTests: XCTestCase {
  func testInstalledFrameworkRecognizesLicensedBreadAndReleasesExactFile() async throws {
    guard
      ProcessInfo.processInfo.environment["TEST_RUNNER_CADENCE_NATIVE_WORD_FRAMEWORK"] == "1"
        || ProcessInfo.processInfo.environment["CADENCE_NATIVE_WORD_FRAMEWORK"] == "1"
    else { throw XCTSkip("Explicit local framework verification only.") }
    let original = try XCTUnwrap(
      Bundle(for: Self.self).url(forResource: "public-example-bread", withExtension: "wav"))
    let bytes = try Data(contentsOf: original)
    let expectedHash = "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f"
    func digest(_ bytes: Data) -> String {
      SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }
    XCTAssertEqual(digest(bytes), expectedHash)
    guard digest(bytes) == expectedHash else { return }
    XCTAssertNotNil(LocalWordWAVGate.duration(bytes: bytes))

    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "cadence-local-word-framework-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
    let file = directory.appendingPathComponent("reference.wav")
    try bytes.write(to: file, options: .atomic)
    let ownership = ProcessAudioFileOwnership()
    let owner = UUID()
    ownership.retain(file, owner: owner)
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: UUID(), fileURL: file, expectedWord: "bread")
    let recognizer = SystemLocalWordRecognizer(ownership: ownership)

    // Exactly one invocation: no readiness repair, asset download, retry or fallback.
    let receipt = await recognizer.check(request: request)
    XCTAssertEqual(receipt.request, request)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertEqual(receipt.status, .matched)
    XCTAssertEqual(digest(try Data(contentsOf: original)), expectedHash)
    XCTAssertEqual(digest(try Data(contentsOf: file)), expectedHash)
    guard receipt.request == request, receipt.cleanupConfirmed,
      ownership.canRemove(file, owner: owner)
    else {
      // Retain the owner and recognizer when exact cleanup is unknown.
      Self.retained.append((ownership, recognizer))
      XCTFail("Framework cleanup did not permit exact reference-file removal.")
      return
    }
    try FileManager.default.removeItem(at: file)
    ownership.didRemove(file, owner: owner)
    try FileManager.default.removeItem(at: directory)
    XCTAssertTrue(ownership.protectedURLs.isEmpty)
    XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
  }

  private static var retained: [(ProcessAudioFileOwnership, SystemLocalWordRecognizer)] = []
}
