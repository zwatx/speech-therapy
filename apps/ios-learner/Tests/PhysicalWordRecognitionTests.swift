import CoreML
import CryptoKit
import Foundation
import XCTest

@testable import CadenceLearner

/// Explicit physical-device checks use only the licensed public fixture, never sensors.
@MainActor
final class PhysicalWordRecognitionTests: XCTestCase {
  private func requirePhysicalRun() throws {
    #if targetEnvironment(simulator)
      throw XCTSkip("Physical iPhone verification only.")
    #else
      let environment = ProcessInfo.processInfo.environment
      guard
        environment["CADENCE_PHYSICAL_CHECK"] == "1"
          || environment["TEST_RUNNER_CADENCE_PHYSICAL_CHECK"] == "1"
      else { throw XCTSkip("Explicit public-fixture physical check only.") }
    #endif
  }

  func testInstalledBundleResourceLocationIsAdmitted() throws {
    try requirePhysicalRun()
    let app = URL(
      fileURLWithPath: Bundle.main.bundleURL.resolvingSymlinksInPath().path,
      isDirectory: true
    ).standardizedFileURL
    let base = try XCTUnwrap(Bundle.main.resourceURL)
    let root = URL(
      fileURLWithPath: base.resolvingSymlinksInPath().path,
      isDirectory: true
    ).standardizedFileURL
      .appendingPathComponent("WhisperResources", isDirectory: true)
    print(
      "CAC_BUNDLE_METADATA appStandard=\(app == app.standardizedFileURL) appResolved=\(app == app.resolvingSymlinksInPath()) resourceStandard=\(root == root.standardizedFileURL) resourceResolved=\(root == root.resolvingSymlinksInPath())"
    )
    XCTAssertTrue(
      BundledLocalWordRecognizerFactory.isCanonicalAppResourceLocation(
        appURL: app, resourceURL: root,
        resolvedAppURL: app.resolvingSymlinksInPath(),
        resolvedResourceURL: root.resolvingSymlinksInPath(),
        bundleIdentifier: Bundle.main.bundleIdentifier))
    XCTAssertTrue(BundledLocalWordRecognizerFactory.isUnlinkedDirectory(app))
    XCTAssertTrue(BundledLocalWordRecognizerFactory.isUnlinkedDirectory(root))
  }

  func testBundledAssetsAndModelsLoadOnPhysicalPhone() throws {
    try requirePhysicalRun()
    let root = try XCTUnwrap(Bundle.main.resourceURL)
      .appendingPathComponent("WhisperResources", isDirectory: true)
    let assets = try WhisperResourceAdmission.load(
      .init(
        rootURL: root,
        manifestSHA256: "3a5685954ba13a09b6430ed360afbb8c871033e9d2e90388568ef51a90b64b3d"),
      stop: WhisperOperationStop())
    print("CAC_PHYSICAL_ASSETS admitted=true")
    let configuration = MLModelConfiguration()
    configuration.computeUnits = .cpuOnly
    let encoder = try MLModel(contentsOf: assets.encoderURL, configuration: configuration)
    print("CAC_PHYSICAL_MODEL encoderLoaded=true")
    let decoder = try MLModel(contentsOf: assets.decoderURL, configuration: configuration)
    print("CAC_PHYSICAL_MODEL decoderLoaded=true")
    XCTAssertNotNil(encoder.modelDescription.inputDescriptionsByName["mel_features"])
    XCTAssertNotNil(decoder.modelDescription.outputDescriptionsByName["next_token_logits"])
    let prefix = try XCTUnwrap(
      decoder.modelDescription.inputDescriptionsByName["decoder_input_ids"]?.multiArrayConstraint)
    XCTAssertEqual(prefix.shape.map(\.intValue), [1, 8], "Decoder prefix shape")
    XCTAssertEqual(prefix.dataType, .int32)
    XCTAssertEqual(prefix.shapeConstraint.type, .range)
    XCTAssertEqual(
      prefix.shapeConstraint.sizeRangeForDimension.map(\.rangeValue),
      [NSRange(location: 1, length: 1), NSRange(location: 1, length: 64)])
    let mel = try MLMultiArray(shape: [1, 80, 3000], dataType: .float32)
    XCTAssertEqual(mel.strides.map(\.intValue), [240000, 3000, 1], "Physical mel allocation")
    let ids = try MLMultiArray(shape: [1, 2], dataType: .int32)
    XCTAssertEqual(ids.strides.map(\.intValue), [2, 1], "Physical token allocation")
  }

  func testDefaultRecognizerMatchesPublicSpeechAndReleasesFile() async throws {
    try requirePhysicalRun()
    let fixture = try XCTUnwrap(Bundle(for: Self.self).resourceURL)
      .appendingPathComponent("PublicFixture/public-example-bread.wav")
    let bytes = try Data(contentsOf: fixture)
    XCTAssertEqual(
      SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(),
      "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f")
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("cadence-physical-check-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let store = TemporaryRecordingStore(directory: directory)
    // Match SystemAudioCapturer's allocation boundary rather than sending a raw URL.
    let file = store.makeRecordingURL().standardizedFileURL
    try bytes.write(to: file, options: .withoutOverwriting)
    XCTAssertEqual(file, file.standardizedFileURL)
    let files = ProcessAudioFileOwnership()
    let owner = UUID()
    files.retain(file, owner: owner)
    let recognizer = BundledLocalWordRecognizerFactory.make(ownership: files)
    let request = LocalWordRecognitionRequest(
      operationID: UUID(), tryID: UUID(),
      fileURL: file, expectedWord: "bread")
    let start = ContinuousClock.now
    let receipt = await recognizer.check(request: request)
    print(
      "CAC_PHYSICAL_WORD status=\(receipt.status) cleanup=\(receipt.cleanupConfirmed) elapsed=\(start.duration(to: .now))"
    )
    XCTAssertEqual(receipt.request, request)
    XCTAssertTrue(receipt.cleanupConfirmed)
    XCTAssertEqual(receipt.status, .matched)
    guard receipt.cleanupConfirmed, files.canRemove(file, owner: owner) else { return }
    try store.removeRecordingIfPresent(at: file)
    files.didRemove(file, owner: owner)
    XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    XCTAssertTrue(files.protectedURLs.isEmpty)
    let released = await recognizer.releaseWordRuntime()
    XCTAssertTrue(released)
    try FileManager.default.removeItem(at: directory)
  }

}
