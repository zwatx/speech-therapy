import CryptoKit
import Foundation
import XCTest

@testable import CadenceLearner

/// Explicit sensor-free framework verification; excluded from ordinary unit selections.
@MainActor
final class LocalWordRecognitionDiagnosticFrameworkTests: XCTestCase {
  func testObserveInstalledFrameworkBreadStagesAndExactCleanup() async throws {
    guard
      ProcessInfo.processInfo.environment["TEST_RUNNER_CADENCE_NATIVE_WORD_DIAGNOSTIC"] == "1"
        || ProcessInfo.processInfo.environment["CADENCE_NATIVE_WORD_DIAGNOSTIC"] == "1"
    else { throw XCTSkip("Explicit licensed local diagnostic verification only.") }
    guard
      let original = Bundle(for: Self.self).url(
        forResource: "public-example-bread", withExtension: "wav")
    else {
      XCTFail("Licensed reference resource missing.")
      return
    }
    let bytes: Data
    do { bytes = try Data(contentsOf: original) } catch {
      XCTFail("Licensed reference read failed.")
      return
    }
    let expectedHash = "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f"
    func digest(_ bytes: Data) -> String {
      SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }
    XCTAssertTrue(digest(bytes) == expectedHash, "Licensed reference hash mismatch.")
    guard digest(bytes) == expectedHash else { return }
    XCTAssertTrue(
      LocalWordWAVGate.duration(bytes: bytes) != nil, "Licensed reference admission failed.")

    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "cadence-local-word-diagnostic-\(UUID().uuidString)", isDirectory: true)
    let file = directory.appendingPathComponent("reference.wav")
    do {
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      try bytes.write(to: file, options: .atomic)
    } catch {
      // No framework operation or borrow exists yet; only this owned setup is removed.
      try? FileManager.default.removeItem(at: directory)
      XCTFail("Owned reference preparation failed.")
      return
    }
    let ownership = ProcessAudioFileOwnership()
    let owner = UUID()
    ownership.retain(file, owner: owner)
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: UUID(), fileURL: file, expectedWord: "bread")
    var observed: LocalWordRecognitionDiagnostic?
    let recognizer = SystemLocalWordRecognizer(
      ownership: ownership, fixtureDiagnosticSink: { observed = $0 })

    // Exactly one invocation: no readiness repair, asset download, retry or fallback.
    let receipt = await recognizer.check(request: request)
    let diagnostic = observed
    var ownedRemoved = false
    var directoryRemoved = false
    defer {
      // Diagnostic/hash/assertion failures must not discard an owned take or its
      // recognizer before exact acknowledged removal. This also covers throwing reads.
      if !ownedRemoved { Self.retained.append((ownership, recognizer)) }
      let status: String
      switch receipt.status {
      case .matched: status = "matched"
      case .notMatched: status = "notMatched"
      case .uncertain: status = "uncertain"
      case .timedOut: status = "timedOut"
      case .unavailable: status = "unavailable"
      case .cancelled: status = "cancelled"
      }
      let safe: [String: Any] = [
        "status": status,
        "diagnosticAvailable": diagnostic != nil,
        "exactReceipt": receipt.request == request,
        "exactDiagnosticIdentity": diagnostic?.operationID == request.operationID
          && diagnostic?.tryID == request.tryID,
        "snapshotMatchesSink": diagnostic != nil && recognizer.lastDiagnostic == diagnostic,
        "cleanupConfirmed": receipt.cleanupConfirmed,
        "ownedFileRemoved": ownedRemoved,
        "ownedDirectoryRemoved": directoryRemoved,
        "protectedURLsEmpty": ownership.protectedURLs.isEmpty,
        "stages": diagnostic?.stages.map(\.rawValue).sorted() ?? [],
        "reasons": diagnostic?.reasons.map(\.rawValue).sorted() ?? [],
        "speechFailures": diagnostic?.speechFailures.map(\.rawValue).sorted() ?? [],
        "terminalTrigger": diagnostic?.terminalTrigger?.rawValue ?? "none",
        "receiptOverride": diagnostic?.receiptOverride?.rawValue ?? "none",
      ]
      if let data = try? JSONSerialization.data(withJSONObject: safe, options: [.sortedKeys]),
        let line = String(data: data, encoding: .utf8)
      {
        print("CADENCE_NATIVE_WORD_DIAGNOSTIC_OBSERVATION:" + line)
      }
    }
    // Boolean assertions with fixed labels do not interpolate private request/snapshot
    // values into XCTest's separate failure-output channel.
    XCTAssertTrue(diagnostic != nil, "Diagnostic snapshot missing.")
    XCTAssertTrue(diagnostic?.operationID == request.operationID, "Diagnostic operation mismatch.")
    XCTAssertTrue(diagnostic?.tryID == request.tryID, "Diagnostic try mismatch.")
    XCTAssertTrue(recognizer.lastDiagnostic == diagnostic, "Diagnostic snapshot mismatch.")
    XCTAssertTrue(receipt.request == request, "Exact recognition receipt mismatch.")
    XCTAssertTrue(receipt.cleanupConfirmed, "Framework cleanup unconfirmed.")
    XCTAssertTrue(receipt.status == .matched, "Licensed reference word did not match.")
    do {
      let originalHash = digest(try Data(contentsOf: original))
      let ownedHash = digest(try Data(contentsOf: file))
      XCTAssertTrue(originalHash == expectedHash, "Original reference bytes changed.")
      XCTAssertTrue(ownedHash == expectedHash, "Owned reference bytes changed.")
    } catch {
      XCTFail("Post-call reference verification read failed.")
      return
    }
    guard receipt.request == request, receipt.cleanupConfirmed,
      ownership.canRemove(file, owner: owner)
    else {
      // Retain the owner and recognizer when exact cleanup is unknown.
      XCTFail("Framework cleanup did not permit exact reference-file removal.")
      return
    }
    do {
      try FileManager.default.removeItem(at: file)
      ownership.didRemove(file, owner: owner)
      ownedRemoved = !FileManager.default.fileExists(atPath: file.path)
      try FileManager.default.removeItem(at: directory)
      directoryRemoved = !FileManager.default.fileExists(atPath: directory.path)
    } catch {
      XCTFail("Owned reference removal failed.")
      return
    }
    XCTAssertTrue(ownership.protectedURLs.isEmpty, "Owned reference protection remained.")
    XCTAssertTrue(ownedRemoved, "Owned reference file remained.")
    XCTAssertTrue(directoryRemoved, "Owned reference directory remained.")
  }

  private static var retained: [(ProcessAudioFileOwnership, SystemLocalWordRecognizer)] = []
}
