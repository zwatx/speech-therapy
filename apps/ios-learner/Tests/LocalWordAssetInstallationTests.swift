// Explicitly authorized English model installation only; excluded from ordinary unit selections.
import Foundation
import Speech
import XCTest

@testable import CadenceLearner

@MainActor
final class LocalWordAssetInstallationTests: XCTestCase {
  private static var started = false

  private struct Receipt: Encodable {
    let schemaVersion = 1
    let mode = "fixedEnglishLearnerAssetSetup"
    let module = "DictationTranscriber/en-US/emptyHintsOptionsReportingAttributes"
    let analyzerCreations = 0
    let analysisCalls = 0
    let directReserveCalls = 0
    let releaseCalls = 0
    var hostMatches = false
    var osMajor = 0
    var osMinor = 0
    var resolvedLocale: String?
    var localeQueries = 0
    var statusQueries = 0
    var reservationQueries = 0
    var reservedBefore: Bool?
    var reservedAfter: Bool?
    var beforeStatus: String?
    var afterStatus: String?
    var requestCount = 0
    var downloadCount = 0
    var outcome = "notAttempted"
    var failure: String?
  }

  func testInstallOnlyFixedEnglishAssetsAndObserveFreshInstalledReadiness() async throws {
    let environment = ProcessInfo.processInfo.environment
    let names = ["CADENCE_NATIVE_ENGLISH_SETUP", "TEST_RUNNER_CADENCE_NATIVE_ENGLISH_SETUP"]
    let supplied = names.compactMap { environment[$0] }
    guard !supplied.isEmpty, supplied.allSatisfy({ $0 == "1" }) else {
      throw XCTSkip("Requires explicit authorized fixed-English asset setup admission.")
    }
    guard !Self.started else {
      return XCTFail("An installation was already admitted in this process.")
    }
    Self.started = true
    var fact = Receipt()
    func emit(_ stage: String) throws {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys]
      let bytes = try encoder.encode(fact)
      XCTAssertLessThanOrEqual(bytes.count, 4096)
      print("CADENCE_NATIVE_ENGLISH_SETUP_" + stage + ":" + String(decoding: bytes, as: UTF8.self))
    }
    fact.hostMatches = Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner"
    let version = ProcessInfo.processInfo.operatingSystemVersion
    fact.osMajor = version.majorVersion
    fact.osMinor = version.minorVersion
    guard fact.hostMatches, #available(iOS 26, *) else {
      fact.failure = "hostOrOSNotAdmitted"
      try emit("AFTER")
      return XCTFail("Fixed learner host and iOS 26 or newer are required.")
    }
    fact.localeQueries = 1
    let resolved = await DictationTranscriber.supportedLocale(
      equivalentTo: Locale(identifier: "en-US"))
    fact.resolvedLocale = resolved?.identifier(.bcp47)
    guard let locale = resolved, locale.language.languageCode == .english,
      fact.resolvedLocale == "en-US"
    else {
      fact.failure = "fixedEnglishLocaleNotSupported"
      try emit("AFTER")
      return XCTFail("The fixed English locale is not supported.")
    }
    let module = DictationTranscriber(
      locale: locale, contentHints: [], transcriptionOptions: [], reportingOptions: [],
      attributeOptions: [])
    fact.statusQueries = 1
    let before = await AssetInventory.status(forModules: [module])
    fact.beforeStatus = statusName(before)
    fact.reservationQueries = 1
    fact.reservedBefore = await AssetInventory.reservedLocales.contains {
      $0.identifier(.bcp47) == "en-US"
    }
    try emit("BEFORE")
    // A downloading or unsupported module is observed without another installation request.
    if before == .supported {
      fact.requestCount = 1
      try emit("REQUEST")
      do {
        // The official request may reserve this module's fixed locale automatically.
        // No direct reserve/release, other locale, analyzer, voice transfer or account change.
        if let request = try await AssetInventory.assetInstallationRequest(supporting: [module]) {
          fact.downloadCount = 1
          do {
            try await request.downloadAndInstall()
            fact.outcome = "downloadAndInstallCompleted"
          } catch {
            fact.outcome = "downloadAndInstallThrew"
            fact.failure = "officialDownloadFailed"
          }
        } else {
          fact.outcome = "requestReturnedNil"
        }
      } catch {
        fact.outcome = "requestThrew"
        fact.failure = "officialRequestFailed"
      }
    } else if before == .installed {
      fact.outcome = "alreadyInstalled"
    } else {
      fact.outcome = "statusNotEligibleForRequest"
    }
    // A completed download is not readiness: ask the actual module again after it settles.
    fact.statusQueries = 2
    let after = await AssetInventory.status(forModules: [module])
    fact.afterStatus = statusName(after)
    fact.reservationQueries = 2
    fact.reservedAfter = await AssetInventory.reservedLocales.contains {
      $0.identifier(.bcp47) == "en-US"
    }
    try emit("AFTER")
    XCTAssertNil(fact.failure, "The fixed English asset request did not complete successfully.")
    XCTAssertEqual(after, .installed, "Fresh fixed-module readiness is not installed.")
    XCTAssertLessThanOrEqual(fact.requestCount, 1)
    XCTAssertLessThanOrEqual(fact.downloadCount, 1)
  }

  @available(iOS 26, *)
  private func statusName(_ status: AssetInventory.Status) -> String {
    switch status {
    case .unsupported: "unsupported"
    case .supported: "supported"
    case .downloading: "downloading"
    case .installed: "installed"
    @unknown default: "unknownFutureStatus"
    }
  }
}
