#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  /// Legacy behavioral cases explicitly provide unused services instead of constructing
  /// production network clients or a shared file store. No media receipt is synthesized.
  @MainActor
  func makeControlledFeedbackSession(
    capturer: any AudioCapturing, player: any AcknowledgedPracticeAudioPlaying,
    processor: any ResearchFeedbackProcessing,
    soundProcessor: (any ResearchSoundProcessing)? = nil,
    exampleLoader: (any ResearchPracticeExampleLoading)? = nil,
    exampleStore: (any ResearchPracticeExampleStoring)? = nil,
    participationWriter: (any ResearchGuidedPracticeParticipationRecording)? = nil,
    now: @escaping @MainActor () -> Date = { Date() },
    wordGuessProcessor: (any ResearchWordGuessProcessing)? = nil
  ) -> ResearchFeedbackSession {
    ResearchFeedbackSession(
      capturer: capturer, player: player, processor: processor,
      soundProcessor: soundProcessor ?? UnusedFeedbackSoundService(),
      exampleLoader: exampleLoader ?? UnusedFeedbackExampleLoader(),
      exampleStore: exampleStore ?? UnusedFeedbackExampleStore(),
      participationWriter: participationWriter, now: now,
      wordGuessProcessor: wordGuessProcessor)
  }

  @MainActor
  private final class UnusedFeedbackSoundService: ResearchSoundProcessing {
    private func unavailable() -> RecordingFeedbackError {
      XCTFail("Unexpected sound-service call in a case that did not inject that service")
      return .processingUnavailable
    }
    func declaration() async throws -> ResearchSoundDeclaration { throw unavailable() }
    func prepare(
      recording: CapturedRecording, declaration: ResearchSoundDeclaration,
      context: ResearchSoundCheckContext
    ) async throws -> ResearchSoundPrepared { throw unavailable() }
    func observe(_ prepared: ResearchSoundPrepared) async throws -> ResearchSoundObservation {
      throw unavailable()
    }
    func cancel(_ prepared: ResearchSoundPrepared) async throws { throw unavailable() }
    func reset(declaration: ResearchSoundDeclaration, sessionId: String, generation: Int)
      async throws
    { throw unavailable() }
  }

  @MainActor
  private final class UnusedFeedbackExampleLoader: ResearchPracticeExampleLoading {
    func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      ResearchPracticeExamples.example(for: prompt)
    }
    func load(example: ResearchPracticeExample) async throws -> Data {
      XCTFail("Unexpected example load in a case that did not inject that service")
      throw ResearchPracticeExampleError.unavailable
    }
  }

  /// This unused store creates and owns no URL, and never acknowledges any removal.
  @MainActor
  private final class UnusedFeedbackExampleStore: ResearchPracticeExampleStoring {
    var ownedURL: URL? { nil }
    func write(_ data: Data) throws -> URL {
      XCTFail("Unexpected example write in a case that did not inject a store")
      throw ResearchPracticeExampleError.storageFailed
    }
    func remove(_ url: URL) throws {
      XCTFail("Unexpected example removal in a case that did not inject a store")
      throw ResearchPracticeExampleError.cleanupFailed
    }
  }
#endif
