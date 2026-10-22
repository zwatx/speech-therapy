// Opt-in metadata observation, excluded from ordinary unit selections.
// One learner-host observation; no audio analysis, sensors, output or asset modification.
import CryptoKit
import Darwin
import Foundation
import Speech
import XCTest

@testable import CadenceLearner

@MainActor
final class LocalWordReadinessObservationTests: XCTestCase {
  private static let expectedHash =
    "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f"
  private static var retainedHandles: [FileHandle] = []
  private static var retainedDirectories: [URL] = []
  private static var retainedInputs: [(ProcessAudioFileOwnership, URL)] = []

  private struct FileFact: Encodable {
    var isFileURL = false
    var isRegularFile: Bool?
    var isSymbolicLink: Bool?
    var size: Int?
    var directOpenAttempts = 0
    var directReadAttempts = 0
    var directBytesRead = 0
    var actualFileGateCalls = 0
    var sha256: String?
    var hashMatches = false
    var pureGateDuration: Double?
    var fileGateDuration: Double?
    var handlesClosed = true
    var stage = "notStarted"
  }

  private struct Observation: Encodable {
    let schemaVersion = 1
    let observation = "fixedTwoConfigurationReadinessNoAnalysis"
    var hostMatches = false
    var osMajor = 0
    var osMinor = 0
    var osPatch = 0
    var localeQueryCount = 0
    var statusQueryCount = 0
    var reservationQueryCount = 0
    var resolvedLocaleReservedForHost: Bool?
    var resolvedLocale: String?
    var englishEquivalent = false
    var currentEmptyReportingStatus: String?
    var historicalAlternativeReportingStatus: String?
    var original = FileFact()
    var ownedCopy = FileFact()
    var ownedCopyCreated = false
    var ownedCopyInspected = false
    var copyBorrowAcquired = false
    var copyBorrowReleased = false
    var ownedCopyRemoved = false
    var ownedDirectoryRemoved = false
    var queryCompleted = false
    var verdict = "notObserved"
    var stage = "preflight"
    let analyzerCreations = 0
    let analysisCalls = 0
    let assetOperations = 0
  }

  func testObserveFixedReadinessAndPublicFileAdmissionWithoutAnalysis() async throws {
    guard
      ProcessInfo.processInfo.environment["TEST_RUNNER_CADENCE_NATIVE_WORD_READINESS"] == "1"
        || ProcessInfo.processInfo.environment["CADENCE_NATIVE_WORD_READINESS"] == "1"
    else { throw XCTSkip("One explicitly selected metadata-only readiness observation.") }
    var fact = Observation()
    func emitAndVerifyCompletion() throws {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys]
      let bytes = try encoder.encode(fact)
      let json = try XCTUnwrap(String(data: bytes, encoding: .utf8))
      print("CADENCE_NATIVE_WORD_READINESS_OBSERVATION:" + json)
      XCTAssertTrue(fact.queryCompleted, "The bounded readiness observation did not complete.")
      if fact.queryCompleted {
        XCTAssertEqual(fact.localeQueryCount, 1)
        XCTAssertEqual(fact.statusQueryCount, fact.englishEquivalent ? 2 : 0)
        XCTAssertEqual(fact.reservationQueryCount, fact.englishEquivalent ? 1 : 0)
        XCTAssertTrue(fact.original.hashMatches && fact.original.handlesClosed)
        XCTAssertTrue(fact.ownedCopyCreated && fact.ownedCopyInspected)
        XCTAssertTrue(fact.ownedCopy.hashMatches)
        XCTAssertNotNil(fact.ownedCopy.pureGateDuration)
        XCTAssertNotNil(fact.ownedCopy.fileGateDuration)
        XCTAssertEqual(fact.ownedCopy.actualFileGateCalls, 1)
        XCTAssertTrue(fact.ownedCopy.handlesClosed)
        XCTAssertTrue(fact.copyBorrowAcquired && fact.copyBorrowReleased)
        XCTAssertTrue(fact.ownedCopyRemoved && fact.ownedDirectoryRemoved)
      }
    }
    fact.hostMatches = Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner"
    guard fact.hostMatches else {
      fact.verdict = "wrongHostNoQuery"
      try emitAndVerifyCompletion()
      return
    }
    let version = ProcessInfo.processInfo.operatingSystemVersion
    fact.osMajor = version.majorVersion
    fact.osMinor = version.minorVersion
    fact.osPatch = version.patchVersion
    guard #available(iOS 26, *) else {
      fact.verdict = "unsupportedOSNoQuery"
      try emitAndVerifyCompletion()
      return
    }
    guard
      let original = Bundle(for: Self.self).url(
        forResource: "public-example-bread", withExtension: "wav")
    else {
      fact.verdict = "boundFixtureMissingNoQuery"
      try emitAndVerifyCompletion()
      return
    }
    let originalRead = inspect(original)
    fact.original = originalRead.fact
    guard let bytes = originalRead.bytes, fact.original.hashMatches,
      fact.original.handlesClosed, fact.original.pureGateDuration != nil,
      fact.original.fileGateDuration != nil
    else {
      fact.verdict = "boundFixtureAdmissionIncompleteNoQuery"
      try emitAndVerifyCompletion()
      return
    }

    fact.stage = "localeQuery"
    fact.localeQueryCount = 1
    let locale = await DictationTranscriber.supportedLocale(
      equivalentTo: Locale(identifier: "en-US"))
    fact.resolvedLocale = locale?.identifier(.bcp47)
    fact.englishEquivalent = locale?.language.languageCode == .english
    if let locale, fact.englishEquivalent {
      fact.stage = "reservationObservation"
      fact.reservationQueryCount = 1
      fact.resolvedLocaleReservedForHost = await AssetInventory.reservedLocales.contains {
        $0.identifier(.bcp47) == locale.identifier(.bcp47)
      }
      fact.stage = "currentStatusQuery"
      let current = DictationTranscriber(
        locale: locale, contentHints: [], transcriptionOptions: [], reportingOptions: [],
        attributeOptions: [])
      fact.statusQueryCount += 1
      fact.currentEmptyReportingStatus = statusName(
        await AssetInventory.status(forModules: [current]))
      fact.stage = "historicalStatusQuery"
      let historical = DictationTranscriber(
        locale: locale, contentHints: [], transcriptionOptions: [],
        reportingOptions: [.alternativeTranscriptions], attributeOptions: [])
      fact.statusQueryCount += 1
      fact.historicalAlternativeReportingStatus = statusName(
        await AssetInventory.status(forModules: [historical]))
      fact.verdict =
        fact.currentEmptyReportingStatus == "installed"
        ? "observedCurrentInstalledNoAnalysis" : "observedCurrentNotInstalledNoAnalysis"
      if fact.currentEmptyReportingStatus == "unknownFutureStatus" {
        fact.verdict = "observedUnknownCurrentStatusNoAnalysis"
      }
    } else {
      fact.verdict = "observedNoEnglishEquivalentNoAnalysis"
    }
    fact.queryCompleted = true

    // Distinct generated public copy; never a practice take or the deleted framework copy.
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "cadence-readiness-observation-\(UUID().uuidString)", isDirectory: true)
    let copy = directory.appendingPathComponent("public-reference.wav")
    enum ObservationFileError: Error {
      case emptyDirectoryRemovalFailed
      case borrowRefused
      case removalRefused
    }
    var directoryCreated = false
    let files = ProcessAudioFileOwnership()
    let owner = UUID()
    let operation = UUID()
    do {
      fact.stage = "ownedDirectoryCreate"
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
      directoryCreated = true
      fact.stage = "ownedCopyWrite"
      files.retain(copy, owner: owner)
      try bytes.write(to: copy, options: [.withoutOverwriting])
      fact.ownedCopyCreated = true
      fact.stage = "ownedCopyBorrow"
      fact.copyBorrowAcquired = files.borrow(copy, operation: operation)
      guard fact.copyBorrowAcquired else {
        throw ObservationFileError.borrowRefused
      }
      fact.ownedCopy = inspect(copy).fact
      fact.ownedCopyInspected = true
      if !fact.ownedCopy.handlesClosed {
        Self.retainedDirectories.append(directory)
        Self.retainedInputs.append((files, copy))
        fact.stage = "ownedCopyCloseUnconfirmedRetained"
      } else {
        files.finishBorrowing(operation: operation)
        fact.copyBorrowReleased = true
        guard files.canRemove(copy, owner: owner) else {
          throw ObservationFileError.removalRefused
        }
        fact.stage = "ownedCopyRemove"
        try FileManager.default.removeItem(at: copy)
        files.didRemove(copy, owner: owner)
        fact.ownedCopyRemoved = true
        fact.stage = "ownedEmptyDirectoryRemove"
        guard rmdir(directory.path) == 0 else {
          throw ObservationFileError.emptyDirectoryRemovalFailed
        }
        fact.ownedDirectoryRemoved = true
        fact.stage = "observationCompleted"
      }
    } catch {
      // No raw Error descriptions, filesystem paths, retry, or recursive recovery.
      if directoryCreated {
        Self.retainedDirectories.append(directory)
        Self.retainedInputs.append((files, copy))
      }
      fact.stage += "FailedRetained"
    }
    try emitAndVerifyCompletion()
  }

  private func inspect(_ url: URL) -> (fact: FileFact, bytes: Data?) {
    var fact = FileFact()
    fact.isFileURL = url.isFileURL
    let bytes: Data
    do {
      fact.stage = "metadata"
      let values = try url.resourceValues(forKeys: [
        .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey,
      ])
      fact.isRegularFile = values.isRegularFile
      fact.isSymbolicLink = values.isSymbolicLink
      fact.size = values.fileSize
      guard fact.isFileURL, fact.isRegularFile == true, fact.isSymbolicLink != true,
        let size = fact.size, size >= 44, size <= LocalWordWAVGate.maximumFileBytes
      else {
        fact.stage = "metadataRejected"
        return (fact, nil)
      }
      fact.stage = "boundedOpen"
      fact.directOpenAttempts += 1
      let handle = try FileHandle(forReadingFrom: url)
      do {
        fact.stage = "boundedRead"
        fact.directReadAttempts += 1
        bytes = try handle.read(upToCount: LocalWordWAVGate.maximumFileBytes) ?? Data()
        fact.directBytesRead = bytes.count
      } catch {
        fact.stage = "boundedReadFailed"
        do { try handle.close() } catch {
          fact.handlesClosed = false
          Self.retainedHandles.append(handle)
        }
        return (fact, nil)
      }
      fact.stage = "boundedClose"
      do { try handle.close() } catch {
        fact.handlesClosed = false
        Self.retainedHandles.append(handle)
        fact.stage = "boundedCloseUnconfirmed"
        return (fact, nil)
      }
      guard bytes.count == size else {
        fact.stage = "boundedReadSizeMismatch"
        return (fact, nil)
      }
      fact.sha256 = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
      fact.hashMatches = fact.sha256 == Self.expectedHash
      fact.pureGateDuration = LocalWordWAVGate.duration(bytes: bytes)
      fact.stage = "actualBoundedFileGate"
      // The actual gate does not expose internal open/read counts; do not fabricate them.
      fact.actualFileGateCalls = 1
      let admission = try LocalWordWAVGate.read(fileURL: url)
      fact.fileGateDuration = admission.duration
      fact.handlesClosed = admission.cleanupConfirmed
      if let retained = admission.retainedHandle { Self.retainedHandles.append(retained) }
      fact.stage = fact.handlesClosed ? "inspected" : "actualFileGateCloseUnconfirmed"
      return (fact, bytes)
    } catch {
      fact.stage += "Failed"
      return (fact, nil)
    }
  }

  @available(iOS 26, *)
  private func statusName(_ value: AssetInventory.Status) -> String {
    switch value {
    case .unsupported: return "unsupported"
    case .supported: return "supported"
    case .downloading: return "downloading"
    case .installed: return "installed"
    @unknown default: return "unknownFutureStatus"
    }
  }
}
