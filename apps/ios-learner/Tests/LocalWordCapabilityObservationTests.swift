// Opt-in same-module capability observation. No audio, analyzer instance or asset mutation.
import AVFAudio
import AudioToolbox
import Foundation
import Speech
import XCTest

@MainActor
final class LocalWordCapabilityObservationTests: XCTestCase {
  private enum Query: String, Encodable {
    case notCalled, reached, returnedNil, returnedNonNil
  }

  private enum Asset: String, Encodable {
    case notCalled, reached, unsupported, supported, downloading, installed, unknownFutureStatus
  }

  private enum Reservation: String, Encodable {
    case notCalled, reached, present, absent
  }

  private enum LocaleResult: String, Encodable {
    case notCalled, reached, unavailable, exactRequestedEnglish, equivalentEnglish, nonEnglish
  }

  private enum Formats: String, Encodable {
    case unqueried, empty, wildcard, concrete, mixedOrMalformed
  }

  private enum Outcome: String, Encodable {
    case incomplete, wrongHost, unsupportedOS, localeUnavailable, nonEnglishLocale
    case constructionUnavailable, cancelled, observed
  }

  private struct Observation: Encodable {
    let schema = "nativeWordCapabilityProbeV1"
    let order = "moduleFormatsThenNaturalThenNoPreference"
    // The installed SDK declares this API only on SpeechTranscriber, a different module.
    let directAvailabilityAPI = "absent"
    var hostMatches = false
    var supportedOS = false
    var locale = LocaleResult.notCalled
    var statusBefore = Asset.notCalled
    var reservationBefore = Reservation.notCalled
    var moduleFormatsReached = false
    var moduleFormatsReturned = false
    var moduleFormats = Formats.unqueried
    var construction = Query.notCalled
    var naturalSelection = Query.notCalled
    var noPreferenceSelection = Query.notCalled
    var statusAfter = Asset.notCalled
    var reservationAfter = Reservation.notCalled
    var cancellationBefore = false
    var cancellationAfter = false
    var queryCompleted = false
    var outcome = Outcome.incomplete
  }

  func testObserveFixedDictationCapabilityWithoutAudio() async throws {
    guard
      ProcessInfo.processInfo.environment["CADENCE_NATIVE_WORD_CAPABILITY_PROBE"] == "1"
        || ProcessInfo.processInfo.environment["TEST_RUNNER_CADENCE_NATIVE_WORD_CAPABILITY_PROBE"]
          == "1"
    else { throw XCTSkip("One explicitly selected capability observation without audio.") }
    var fact = Observation()
    func emit() throws {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys]
      let bytes = try encoder.encode(fact)
      let json = try XCTUnwrap(String(data: bytes, encoding: .utf8))
      print("CADENCE_NATIVE_WORD_CAPABILITY_OBSERVATION:" + json)
      // Nil capability is evidence, not a failed recognition assertion or readiness claim.
      XCTAssertTrue(fact.queryCompleted, "The capability observation did not complete.")
    }
    func cancelled() -> Bool {
      fact.cancellationAfter = Task.isCancelled
      if fact.cancellationAfter { fact.outcome = .cancelled }
      return fact.cancellationAfter
    }
    fact.cancellationBefore = Task.isCancelled
    fact.hostMatches = Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner"
    guard fact.hostMatches else {
      fact.outcome = .wrongHost
      try emit()
      return
    }
    guard #available(iOS 26, *) else {
      fact.outcome = .unsupportedOS
      try emit()
      return
    }
    fact.supportedOS = true
    guard !cancelled() else {
      try emit()
      return
    }
    let requested = Locale(identifier: "en-US")
    fact.locale = .reached
    let resolved = await DictationTranscriber.supportedLocale(equivalentTo: requested)
    if let resolved {
      fact.locale =
        resolved.language.languageCode != .english
        ? .nonEnglish
        : resolved.identifier(.bcp47) == requested.identifier(.bcp47)
          ? .exactRequestedEnglish : .equivalentEnglish
    } else {
      fact.locale = .unavailable
    }
    guard !cancelled() else {
      try emit()
      return
    }
    guard let resolved else {
      fact.outcome = .localeUnavailable
      try emit()
      return
    }
    guard resolved.language.languageCode == .english else {
      fact.outcome = .nonEnglishLocale
      try emit()
      return
    }
    let module = DictationTranscriber(
      locale: resolved, contentHints: [], transcriptionOptions: [], reportingOptions: [],
      attributeOptions: [])
    fact.statusBefore = .reached
    fact.statusBefore = asset(await AssetInventory.status(forModules: [module]))
    guard !cancelled() else {
      try emit()
      return
    }
    fact.reservationBefore = .reached
    fact.reservationBefore =
      await AssetInventory.reservedLocales.contains {
        $0.identifier(.bcp47) == resolved.identifier(.bcp47)
      } ? .present : .absent
    guard !cancelled() else {
      try emit()
      return
    }
    fact.moduleFormatsReached = true
    let moduleFormats = await module.availableCompatibleAudioFormats
    fact.moduleFormatsReturned = true
    fact.moduleFormats = classify(moduleFormats)
    guard !cancelled() else {
      try emit()
      return
    }
    fact.construction = .reached
    let natural = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)
    fact.construction = natural == nil ? .returnedNil : .returnedNonNil
    guard let natural else {
      fact.outcome = .constructionUnavailable
      try emit()
      return
    }
    fact.naturalSelection = .reached
    let naturalResult = await SpeechAnalyzer.bestAvailableAudioFormat(
      compatibleWith: [module], considering: natural)
    fact.naturalSelection = naturalResult == nil ? .returnedNil : .returnedNonNil
    guard !cancelled() else {
      try emit()
      return
    }
    fact.noPreferenceSelection = .reached
    let noPreferenceResult = await SpeechAnalyzer.bestAvailableAudioFormat(
      compatibleWith: [module], considering: nil)
    fact.noPreferenceSelection = noPreferenceResult == nil ? .returnedNil : .returnedNonNil
    guard !cancelled() else {
      try emit()
      return
    }
    fact.statusAfter = .reached
    fact.statusAfter = asset(await AssetInventory.status(forModules: [module]))
    guard !cancelled() else {
      try emit()
      return
    }
    fact.reservationAfter = .reached
    fact.reservationAfter =
      await AssetInventory.reservedLocales.contains {
        $0.identifier(.bcp47) == resolved.identifier(.bcp47)
      } ? .present : .absent
    guard !cancelled() else {
      try emit()
      return
    }
    fact.queryCompleted = true
    fact.outcome = .observed
    try emit()
  }

  // Apple defines a wildcard as exactly one ASBD with any rate and every other field zero.
  // Concrete here describes a finite positive PCM shape, never converter eligibility.
  private func classify(_ formats: [AVAudioFormat]) -> Formats {
    guard !formats.isEmpty else { return .empty }
    func wildcard(_ format: AVAudioFormat) -> Bool {
      let d = format.streamDescription.pointee
      return d.mSampleRate == kAudioStreamAnyRate && d.mFormatID == 0 && d.mFormatFlags == 0
        && d.mBytesPerPacket == 0 && d.mFramesPerPacket == 0 && d.mBytesPerFrame == 0
        && d.mChannelsPerFrame == 0 && d.mBitsPerChannel == 0 && d.mReserved == 0
    }
    if formats.count == 1 && wildcard(formats[0]) { return .wildcard }
    let concrete = formats.allSatisfy { format in
      let d = format.streamDescription.pointee
      guard d.mSampleRate.isFinite && d.mSampleRate > 0 && d.mFormatID == kAudioFormatLinearPCM,
        d.mChannelsPerFrame > 0, d.mFramesPerPacket > 0, d.mBytesPerFrame > 0,
        d.mBytesPerPacket > 0, d.mBitsPerChannel > 0, d.mReserved == 0
      else { return false }
      return UInt64(d.mBytesPerFrame) * UInt64(d.mFramesPerPacket) == UInt64(d.mBytesPerPacket)
    }
    return concrete ? .concrete : .mixedOrMalformed
  }

  @available(iOS 26, *)
  private func asset(_ status: AssetInventory.Status) -> Asset {
    switch status {
    case .unsupported: .unsupported
    case .supported: .supported
    case .downloading: .downloading
    case .installed: .installed
    @unknown default: .unknownFutureStatus
    }
  }
}
