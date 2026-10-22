import Foundation
import Speech
import XCTest

@testable import CadenceLearner

final class LocalWordSpeechDiagnosticTests: XCTestCase {
  func testKnownSpeechCodesHaveOnlyClosedCategoriesAndNonSpeechErrorsStaySeparate() {
    guard #available(iOS 26, *) else { return }
    let cases: [(SFSpeechError.Code, LocalWordRecognitionDiagnostic.SpeechFailure)] = [
      (.unexpectedAudioFormat, .unexpectedAudioFormat),
      (.incompatibleAudioFormats, .incompatibleAudioFormats),
      (.noModel, .noModel), (.assetLocaleNotAllocated, .assetLocaleNotAllocated),
      (.moduleOutputFailed, .moduleOutputFailed), (.insufficientResources, .insufficientResources),
      (.internalServiceError, .internalServiceError), (.audioReadFailed, .audioReadFailed),
      (.timeout, .timeout), (.missingParameter, .missingParameter),
      (.undefinedTemplateClassName, .unmappedSpeechError),
    ]
    for (code, expected) in cases {
      XCTAssertEqual(LocalWordSpeechDiagnostic.category(code), expected)
    }
    XCTAssertEqual(
      LocalWordSpeechDiagnostic.category(NSError(domain: "generated", code: 1)), .nonSpeechError)
    if #available(iOS 27, *) {
      XCTAssertEqual(
        LocalWordSpeechDiagnostic.category(SFSpeechError.Code.cannotConfigureAudioSystem),
        .cannotConfigureAudioSystem)
    }
  }

  func testTypedSpeechErrorsThroughAnyErrorKeepClosedCategory() {
    guard #available(iOS 26, *) else { return }
    let cases: [(SFSpeechError.Code, LocalWordRecognitionDiagnostic.SpeechFailure)] = [
      (.internalServiceError, .internalServiceError), (.audioReadFailed, .audioReadFailed),
      (.timeout, .timeout), (.missingParameter, .missingParameter),
      (.unexpectedAudioFormat, .unexpectedAudioFormat),
      (.incompatibleAudioFormats, .incompatibleAudioFormats), (.noModel, .noModel),
      (.assetLocaleNotAllocated, .assetLocaleNotAllocated),
      (.moduleOutputFailed, .moduleOutputFailed), (.insufficientResources, .insufficientResources),
      (.undefinedTemplateClassName, .unmappedSpeechError),
    ]
    for (code, expected) in cases {
      let error: any Error = SFSpeechError(code)
      XCTAssertEqual(LocalWordSpeechDiagnostic.category(error), expected)
    }
    if #available(iOS 27, *) {
      let error: any Error = SFSpeechError(.cannotConfigureAudioSystem)
      XCTAssertEqual(LocalWordSpeechDiagnostic.category(error), .cannotConfigureAudioSystem)
    }
  }

  func testNSErrorBridgeUsesSpeechDomainAndDoesNotTreatMatchingForeignCodeAsSpeech() {
    guard #available(iOS 26, *) else { return }
    let speech: any Error = SFSpeechError(.audioReadFailed) as NSError
    XCTAssertEqual(LocalWordSpeechDiagnostic.category(speech), .audioReadFailed)
    let foreign: any Error = NSError(
      domain: "generated", code: SFSpeechError.Code.audioReadFailed.rawValue)
    XCTAssertEqual(LocalWordSpeechDiagnostic.category(foreign), .nonSpeechError)
  }
}
