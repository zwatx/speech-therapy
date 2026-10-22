#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Explicit declaration-only transport check. No recording, upload or model request.
  @MainActor
  final class ResearchSoundSuccessorLoopbackTests: XCTestCase {
    func testActualUnifiedDeclarationUsesFrozenBinding() async throws {
      guard ProcessInfo.processInfo.environment["CADENCE_SOUND_UNIFIED_DECLARATION_LOOPBACK"] == "1"
      else {
        throw XCTSkip(
          "Explicitly enable with the frozen unified service running on8793; declaration GET only.")
      }
      XCTAssertEqual(ResearchSoundContract.origin, "http://127.0.0.1:8793")
      let sources = try ResearchSoundContract.sourcePins.fields([
        "featureSourceSha256", "workerSourceSha256", "workerReceiptSha256", "runtimePinsSha256",
        "contrastSpecSha256", "modelFileSha256", "vocabularyFileSha256", "promptSha256",
        "resourcePolicySha256",
      ])
      XCTAssertEqual(
        sources["featureSourceSha256"]?.text,
        "af0ebd33f9a17ab6860e50314433e50691db7299d100874991885945cccb9057")
      // The client enforces full declaration binding equality before returning.
      let declaration = try await ResearchSoundClient().declaration()
      XCTAssertTrue(ResearchSoundContract.uuid(declaration.serverNonce))
      XCTAssertTrue(FeedbackContract.isHash(declaration.csrfToken))
      // Availability can legitimately change while the owner is using the service.
      // This check establishes the real transport/version boundary only.
    }
  }
#endif
