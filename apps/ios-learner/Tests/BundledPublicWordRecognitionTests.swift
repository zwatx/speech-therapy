import CryptoKit
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class BundledPublicWordRecognitionTests: XCTestCase {
    func testDefaultFactoryLicensedPublicWordWholeTakeAndExactCleanup() async throws {
        #if DEBUG && targetEnvironment(simulator)
        let environment = ProcessInfo.processInfo.environment
        guard environment["CADENCE_BUNDLED_PUBLIC_WORD"] == "1",
              environment["CADENCE_CONTROLLED_UNIT_HOST"] == "1",
              environment["SIMULATOR_UDID"] == "132DD629-A694-4D98-A0BB-B828676DD698",
              ControlledUnitTestHost.isEnabled,
              ControlledUnitTestHost.appInitializedWithInertRoot,
              Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner" else {
            throw XCTSkip("Explicit controlled bundled public-word case only.")
        }
        #else
        throw XCTSkip("Debug dedicated simulator unit host only.")
        #endif
        try await runLicensedPublicWordWholeTakeAndExactCleanup()
    }

    func testReleaseDefaultFactoryLicensedPublicWordWholeTakeAndExactCleanup() async throws {
        #if !DEBUG && targetEnvironment(simulator)
        let environment = ProcessInfo.processInfo.environment
        guard environment["CADENCE_BUNDLED_RELEASE_PUBLIC_WORD"] == "1",
              environment["SIMULATOR_UDID"] == "132DD629-A694-4D98-A0BB-B828676DD698",
              Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner" else {
            throw XCTSkip("Explicit Release bundled public-word case only.")
        }
        #else
        throw XCTSkip("Release dedicated simulator unit host only.")
        #endif
        try await runLicensedPublicWordWholeTakeAndExactCleanup()
    }

    private func runLicensedPublicWordWholeTakeAndExactCleanup() async throws {
        try requireImmutableMainAppMetadata()
        let testBundle = Bundle(for: BundledPublicWordRecognitionTests.self)
        guard testBundle.bundleIdentifier == "com.cadence.speechtherapy.learner.tests",
              testBundle.bundleURL.pathExtension == "xctest" else {
            XCTFail("Exact fixture test bundle unavailable."); return
        }
        let result = await BundledPublicWordCase.run(testBundle: testBundle)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        guard let data = try? encoder.encode(result), let aggregate = String(data: data, encoding: .utf8) else {
            XCTFail("Closed bundled aggregate encoding failed."); return
        }
        print("CADENCE_BUNDLED_WORD_V1=" + aggregate)
        XCTAssertTrue(result.actualDefaultFactory, "Production default factory was not used.")
        XCTAssertTrue(result.fixtureHashConfirmed && result.ownedCopyHashConfirmed, "Exact public fixture admission failed.")
        XCTAssertTrue(result.exactOperationReceipt && result.providerReceiptReceived && result.workerAndTimerReturned, "Exact provider return not established.")
        XCTAssertTrue(result.cleanupConfirmed && result.deletionConfirmed && result.ownershipEmpty, "Exact cleanup not established.")
        XCTAssertTrue(result.wordOutcome == .matched, "Bundled public word did not match.")
        XCTAssertTrue(result.elapsedMilliseconds >= 0, "Finite whole-case time not established.")
    }

    private func requireImmutableMainAppMetadata() throws {
        let app = Bundle.main.bundleURL
        guard let root = Bundle.main.resourceURL?.appendingPathComponent("WhisperResources", isDirectory: true),
              BundledLocalWordRecognizerFactory.isCanonicalAppResourceLocation(
                appURL: app, resourceURL: root, resolvedAppURL: app.resolvingSymlinksInPath(),
                resolvedResourceURL: root.resolvingSymlinksInPath(),
                bundleIdentifier: Bundle.main.bundleIdentifier),
              BundledLocalWordRecognizerFactory.isUnlinkedDirectory(app),
              BundledLocalWordRecognizerFactory.isUnlinkedDirectory(root),
              Bundle.main.object(forInfoDictionaryKey: "CFBundleExecutable") as? String == "CadenceLearner",
              Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String == "1",
              Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String == "0.1.0",
              Bundle.main.object(forInfoDictionaryKey: "DTPlatformName") as? String == "iphonesimulator",
              Bundle.main.object(forInfoDictionaryKey: "CFBundleSupportedPlatforms") as? [String] == ["iPhoneSimulator"] else {
            throw BundledPublicWordCaseAdmissionFailure.invalidMainAppMetadata
        }
        let manifest = root.appendingPathComponent("RESOURCE-MANIFEST-v1.json")
        let values = try manifest.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == 4067,
              manifest.resolvingSymlinksInPath() == manifest.standardizedFileURL else {
            throw BundledPublicWordCaseAdmissionFailure.invalidMainAppManifest
        }
        let bytes = try Data(contentsOf: manifest)
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        guard bytes.count == 4067, hash == "3a5685954ba13a09b6430ed360afbb8c871033e9d2e90388568ef51a90b64b3d" else {
            throw BundledPublicWordCaseAdmissionFailure.invalidMainAppManifest
        }
    }
}

private enum BundledPublicWordCaseAdmissionFailure: Error {
    case invalidMainAppMetadata, invalidMainAppManifest
}


/// Closed one-case receipt only. No recognized text, tokens, features, path or IDs.
private struct BundledPublicWordCaseReceipt: Codable {
    enum Outcome: String, Codable { case matched, notMatched, uncertain, unavailable, cancelled }
    let schema: String
    let wordOutcome: Outcome
    let actualDefaultFactory: Bool
    let fixtureHashConfirmed: Bool
    let ownedCopyHashConfirmed: Bool
    let exactOperationReceipt: Bool
    let providerReceiptReceived: Bool
    let workerAndTimerReturned: Bool
    let cleanupConfirmed: Bool
    let deletionConfirmed: Bool
    let ownershipEmpty: Bool
    let elapsedMilliseconds: Int
}

@MainActor
private enum BundledPublicWordCase {
    private struct Held {
        let ownership: ProcessAudioFileOwnership
        let recognizer: CoreMLLocalWordRecognizer
    }
    private static var held = [Held]()
    private static let fixtureSHA = "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f"
    private static let fixtureBytes = 17912

    static func run(testBundle: Bundle) async -> BundledPublicWordCaseReceipt {
        let manager = FileManager.default
        let ownership = ProcessAudioFileOwnership()
        let recognizer = BundledLocalWordRecognizerFactory.make(ownership: ownership) // Exact production default; unchanged15s policy.
        let actualDefaultFactory = true // Set only after the literal factory call above; no injected provider.
        let owner = UUID()
        let directory = manager.temporaryDirectory.appendingPathComponent("cadence-public-word-\(UUID().uuidString)", isDirectory: true)
        let store = TemporaryRecordingStore(directory: directory)
        let file = store.makeRecordingURL()
        var originalHash = false, copyHash = false, exact = false, received = false, joined = false
        var cleanup = false, deleted = false, retained = false
        var outcome = BundledPublicWordCaseReceipt.Outcome.unavailable
        let clock = ContinuousClock(); let started = clock.now
        do {
            guard let bundleRoot = testBundle.resourceURL else { throw WhisperProviderError.unavailable }
            let original = bundleRoot.appendingPathComponent("PublicFixture/public-example-bread.wav")
            let values = try original.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true,
                  values.fileSize == fixtureBytes,
                  original.resolvingSymlinksInPath() == original.standardizedFileURL else { throw WhisperProviderError.unavailable }
            let bytes = try Data(contentsOf: original)
            guard bytes.count == fixtureBytes, digest(bytes) == fixtureSHA,
                  LocalWordWAVGate.duration(bytes: bytes) != nil else { throw WhisperProviderError.unavailable }
            originalHash = true
            try manager.createDirectory(at: directory, withIntermediateDirectories: false,
                                        attributes: [.posixPermissions: 0o700])
            ownership.retain(file, owner: owner); retained = true
            try bytes.write(to: file, options: .withoutOverwriting)
            try manager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
            let copied = try Data(contentsOf: file)
            guard copied.count == fixtureBytes, digest(copied) == fixtureSHA else { throw WhisperProviderError.unavailable }
            copyHash = true
            let request = LocalWordRecognitionRequest(operationID: UUID(), tryID: UUID(), fileURL: file, expectedWord: "bread")
            // Exactly one full provider call. Expected word reaches comparison only
            // after independent EOS inside the frozen worker; no prompt hints.
            let receipt = await recognizer.check(request: request)
            received = true
            exact = receipt.request == request
            cleanup = exact && receipt.cleanupConfirmed
            // Only these exact post-EOS statuses plus cleanup acknowledgement
            // establish the frozen provider's actual worker/timer return path.
            joined = cleanup && (receipt.status == .matched || receipt.status == .notMatched)
            switch receipt.status {
            case .matched: outcome = .matched
            case .notMatched: outcome = .notMatched
            case .uncertain: outcome = .uncertain
            case .unavailable, .timedOut: outcome = .unavailable
            case .cancelled: outcome = .cancelled
            }
            if !exact { outcome = .unavailable }
            // Revalidate the immutable source and owned bytes without logging either.
            guard digest(try Data(contentsOf: original)) == fixtureSHA,
                  digest(try Data(contentsOf: file)) == fixtureSHA else {
                outcome = .unavailable
                throw WhisperProviderError.unavailable
            }
        } catch {
            // Preserve only closed status. Native/private error descriptions never leave.
            outcome = Task.isCancelled ? .cancelled : .unavailable
        }
        if outcome != .matched && outcome != .notMatched { joined = false }
        if retained && (!received || cleanup), ownership.canRemove(file, owner: owner) {
            do {
                try store.removeRecordingIfPresent(at: file)
                ownership.didRemove(file, owner: owner)
                try manager.removeItem(at: directory)
                deleted = !manager.fileExists(atPath: file.path) && !manager.fileExists(atPath: directory.path)
            } catch { deleted = false }
        }
        if retained && (!deleted || !ownership.protectedURLs.isEmpty) {
            // Strong references preserve an occupied provider/failed cleanup; no rescue.
            held.append(.init(ownership: ownership, recognizer: recognizer))
        }
        let elapsed = started.duration(to: clock.now).components
        let milliseconds = Double(elapsed.seconds) * 1000 + Double(elapsed.attoseconds) / 1e15
        let boundedTime = milliseconds.isFinite && milliseconds >= 0 && milliseconds < Double(Int.max)
        return .init(schema: "WhisperBundledPublicWordCaseV1", wordOutcome: outcome,
                     actualDefaultFactory: actualDefaultFactory,
                     fixtureHashConfirmed: originalHash, ownedCopyHashConfirmed: copyHash,
                     exactOperationReceipt: exact, providerReceiptReceived: received,
                     workerAndTimerReturned: joined, cleanupConfirmed: cleanup,
                     deletionConfirmed: deleted, ownershipEmpty: ownership.protectedURLs.isEmpty,
                     elapsedMilliseconds: boundedTime ? Int(milliseconds) : -1)
    }

    private static func digest(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }
}
