import Foundation
import Speech

@available(iOS 26, *)
enum LocalWordSpeechDiagnostic {
  static func category(_ error: any Error) -> LocalWordRecognitionDiagnostic.SpeechFailure {
    guard let speech = error as? SFSpeechError else { return .nonSpeechError }
    return category(speech.code)
  }

  static func category(_ code: SFSpeechError.Code)
    -> LocalWordRecognitionDiagnostic.SpeechFailure
  {
    if #available(iOS 27, *), code == .cannotConfigureAudioSystem {
      return .cannotConfigureAudioSystem
    }
    switch code {
    case .internalServiceError: return .internalServiceError
    case .audioReadFailed: return .audioReadFailed
    case .timeout: return .timeout
    case .missingParameter: return .missingParameter
    case .unexpectedAudioFormat: return .unexpectedAudioFormat
    case .incompatibleAudioFormats: return .incompatibleAudioFormats
    case .noModel: return .noModel
    case .assetLocaleNotAllocated: return .assetLocaleNotAllocated
    case .moduleOutputFailed: return .moduleOutputFailed
    case .insufficientResources: return .insufficientResources
    default: return .unmappedSpeechError
    }
  }
}
