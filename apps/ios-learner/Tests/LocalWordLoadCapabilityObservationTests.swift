// Opt-in resource preparation only. No audio, results consumer, asset mutation or inference.
import AVFAudio
import AudioToolbox
import Foundation
import Speech
import XCTest

@testable import CadenceLearner

@MainActor
final class LocalWordLoadCapabilityObservationTests: XCTestCase {
  private enum Query: String, Encodable { case notCalled, reached, returnedNil, returnedNonNil }
  private enum Asset: String, Encodable {
    case notCalled, reached, unsupported, supported, downloading, installed, unknownFutureStatus
  }
  private enum Reservation: String, Encodable { case notCalled, reached, present, absent }
  private enum LocaleResult: String, Encodable {
    case notCalled, reached, unavailable, exactRequestedEnglish, nonExactLocale
  }
  private enum Formats: String, Encodable {
    case unqueried, empty, wildcard, concrete, mixedOrMalformed
  }
  private enum Outcome: String, Encodable {
    case unknown, wrongHost, unsupportedOS, initialCancellation, localeUnavailable, nonExactLocale
    case assetsGateRejected, constructionUnavailable, baselineChanged, prepared, preparationFailed
    case changedAfter, cancelled
  }
  private struct Capability: Encodable, Equatable {
    var formatsReached = false
    var formatsReturned = false
    var formats = Formats.unqueried
    var naturalSelection = Query.notCalled
    var noPreferenceSelection = Query.notCalled
    var completed: Bool {
      formatsReturned
        && (naturalSelection == .returnedNil || naturalSelection == .returnedNonNil)
        && (noPreferenceSelection == .returnedNil || noPreferenceSelection == .returnedNonNil)
    }
    var originalBaseline: Bool {
      completed && formats == .empty && naturalSelection == .returnedNil
        && noPreferenceSelection == .returnedNil
    }
  }
  private struct Observation: Encodable {
    let schema = "nativeWordLoadCapabilityProbeV1"
    let order = "beforeThenPrepareNilThenAfterThenAwaitCleanup"
    var record = "final"
    var hostMatches = false
    var supportedOS = false
    var locale = LocaleResult.notCalled
    var statusBefore = Asset.notCalled
    var reservationBefore = Reservation.notCalled
    var construction = Query.notCalled
    var before = Capability()
    var analyzerConstructed = false
    var prepareReached = false
    var prepareReturned = false
    var prepareThrew = false
    var prepareCancelled = false
    var prepareError = "none"
    var statusAfter = Asset.notCalled
    var reservationAfter = Reservation.notCalled
    var after = Capability()
    var cleanupReached = false
    var cleanupAcknowledged = false
    var cancellationBefore = false
    var cancellationBeforePrepare = false
    var cancellationAfterPrepare = false
    var cancellationAfterQueries = false
    var cancellationAfterCleanup = false
    var observationComplete = false
    var outcome = Outcome.unknown
  }

  func testObserveInstalledDictationPreparationAndFormatsWithoutAudio() async throws {
    guard
      ProcessInfo.processInfo.environment["CADENCE_NATIVE_WORD_LOAD_CAPABILITY_PROBE"] == "1"
        || ProcessInfo.processInfo.environment[
          "TEST_RUNNER_CADENCE_NATIVE_WORD_LOAD_CAPABILITY_PROBE"]
          == "1"
    else {
      throw XCTSkip("One explicitly selected resource-preparation observation without audio.")
    }
    var fact = Observation()
    func emit() {
      // Closed booleans/enums only; encoding failure must never bypass awaited cleanup.
      do {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let bytes = try encoder.encode(fact)
        guard let json = String(data: bytes, encoding: .utf8) else {
          XCTFail("Closed observation encoding failed.")
          return
        }
        print("CADENCE_NATIVE_WORD_LOAD_CAPABILITY_OBSERVATION:" + json)
        fflush(stdout)
      } catch { XCTFail("Closed observation encoding failed.") }
    }
    func finishEarly(_ outcome: Outcome) {
      fact.outcome = outcome
      emit()
      XCTFail("The preparation observation stopped at its closed preflight gate.")
    }
    fact.cancellationBefore = Task.isCancelled
    fact.hostMatches = Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner"
    guard fact.hostMatches else {
      finishEarly(.wrongHost)
      return
    }
    guard #available(iOS 26, *) else {
      finishEarly(.unsupportedOS)
      return
    }
    fact.supportedOS = true
    guard !fact.cancellationBefore else {
      finishEarly(.initialCancellation)
      return
    }
    let requested = Locale(identifier: "en-US")
    fact.locale = .reached
    let resolved = await DictationTranscriber.supportedLocale(equivalentTo: requested)
    fact.locale = resolved == nil ? .unavailable : .nonExactLocale
    if let resolved, resolved.language.languageCode == .english,
      resolved.identifier(.bcp47) == requested.identifier(.bcp47)
    {
      fact.locale = .exactRequestedEnglish
    }
    guard !Task.isCancelled else {
      fact.cancellationBeforePrepare = true
      finishEarly(.cancelled)
      return
    }
    guard let resolved else {
      finishEarly(.localeUnavailable)
      return
    }
    guard fact.locale == .exactRequestedEnglish else {
      finishEarly(.nonExactLocale)
      return
    }
    let module = DictationTranscriber(
      locale: resolved, contentHints: [], transcriptionOptions: [], reportingOptions: [],
      attributeOptions: [])
    fact.statusBefore = .reached
    fact.statusBefore = asset(await AssetInventory.status(forModules: [module]))
    guard !Task.isCancelled else {
      fact.cancellationBeforePrepare = true
      finishEarly(.cancelled)
      return
    }
    fact.reservationBefore = .reached
    fact.reservationBefore = await reservation(resolved)
    guard !Task.isCancelled else {
      fact.cancellationBeforePrepare = true
      finishEarly(.cancelled)
      return
    }
    guard fact.statusBefore == .installed, fact.reservationBefore == .present else {
      finishEarly(.assetsGateRejected)
      return
    }
    fact.construction = .reached
    let natural = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)
    fact.construction = natural == nil ? .returnedNil : .returnedNonNil
    guard let natural else {
      finishEarly(.constructionUnavailable)
      return
    }
    fact.before = await observeFormats(module, natural: natural)
    fact.cancellationBeforePrepare = Task.isCancelled
    guard !fact.cancellationBeforePrepare else {
      finishEarly(.cancelled)
      return
    }
    guard fact.before.originalBaseline else {
      finishEarly(.baselineChanged)
      return
    }

    let analyzer = SpeechAnalyzer(modules: [module])
    fact.analyzerConstructed = true
    fact.prepareReached = true
    fact.record = "begin"
    emit()
    // Exactly one resource-preparation call, with no anticipated format or audio input.
    do {
      try await analyzer.prepareToAnalyze(in: nil)
      fact.prepareReturned = true
    } catch {
      fact.prepareThrew = true
      fact.prepareCancelled = error is CancellationError
      fact.prepareError = LocalWordSpeechDiagnostic.category(error).rawValue
    }
    fact.cancellationAfterPrepare = Task.isCancelled
    if !fact.cancellationAfterPrepare && !fact.prepareCancelled {
      fact.statusAfter = .reached
      fact.statusAfter = asset(await AssetInventory.status(forModules: [module]))
      if !Task.isCancelled {
        fact.reservationAfter = .reached
        fact.reservationAfter = await reservation(resolved)
      }
      if !Task.isCancelled {
        fact.after = await observeFormats(module, natural: natural)
      }
    }
    fact.cancellationAfterQueries = Task.isCancelled
    // A thrown/cancelled prepare is not a cleanup receipt. No detached cleanup or timeout race.
    fact.cleanupReached = true
    await analyzer.cancelAndFinishNow()
    fact.cleanupAcknowledged = true
    fact.cancellationAfterCleanup = Task.isCancelled
    fact.record = "final"
    let cancelled =
      fact.prepareCancelled || fact.cancellationAfterPrepare
      || fact.cancellationAfterQueries || fact.cancellationAfterCleanup
    fact.observationComplete =
      !cancelled && fact.after.completed
      && fact.statusAfter != .notCalled && fact.statusAfter != .reached
      && fact.reservationAfter != .notCalled && fact.reservationAfter != .reached
    if cancelled {
      fact.outcome = .cancelled
    } else if fact.statusAfter != .installed || fact.reservationAfter != .present {
      fact.outcome = .changedAfter
    } else {
      fact.outcome = fact.prepareReturned ? .prepared : .preparationFailed
    }
    emit()
    // Failure to load resources is a completed observation, not working recognition.
    XCTAssertTrue(fact.observationComplete, "The preparation observation did not complete.")
    XCTAssertTrue(fact.cleanupAcknowledged, "The exact analyzer cleanup was not acknowledged.")
  }

  @available(iOS 26, *)
  private func observeFormats(_ module: DictationTranscriber, natural: AVAudioFormat) async
    -> Capability
  {
    var result = Capability()
    result.formatsReached = true
    result.formats = classify(await module.availableCompatibleAudioFormats)
    result.formatsReturned = true
    guard !Task.isCancelled else { return result }
    result.naturalSelection = .reached
    let preferred = await SpeechAnalyzer.bestAvailableAudioFormat(
      compatibleWith: [module], considering: natural)
    result.naturalSelection = preferred == nil ? .returnedNil : .returnedNonNil
    guard !Task.isCancelled else { return result }
    result.noPreferenceSelection = .reached
    let unpreferred = await SpeechAnalyzer.bestAvailableAudioFormat(
      compatibleWith: [module], considering: nil)
    result.noPreferenceSelection = unpreferred == nil ? .returnedNil : .returnedNonNil
    return result
  }

  // Byte-equivalent algorithm to the admitted capability test: shape, never eligibility.
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
  private func reservation(_ locale: Locale) async -> Reservation {
    await AssetInventory.reservedLocales.contains {
      $0.identifier(.bcp47) == locale.identifier(.bcp47)
    } ? .present : .absent
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
