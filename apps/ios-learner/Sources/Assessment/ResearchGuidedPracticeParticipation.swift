#if DEBUG && targetEnvironment(simulator)
  import Foundation

  /// Only the existing participation fields cross this persistence boundary.
  @MainActor
  protocol ResearchGuidedPracticeParticipationRecording {
    func record(sessionID: UUID, completedAt: Date, soundID: String, wordCount: Int) throws
  }
  extension PracticeParticipationStore: ResearchGuidedPracticeParticipationRecording {}

  enum ResearchGuidedPracticeSaveError: Error, Equatable, Sendable {
    case storeUnavailable, writeFailed
    var userMessage: String {
      switch self {
      case .storeUnavailable: "Practice finished. Saving history is unavailable here."
      case .writeFailed:
        "Practice finished, but it could not be saved to history. Try saving again."
      }
    }
  }
  enum ResearchGuidedPracticeCompletionState: Equatable, Sendable {
    case active
    case completedNotSaved(ResearchGuidedPracticeSaveError)
    case saved
  }
  struct ResearchGuidedPracticeCompletion: Equatable, Sendable {
    let id: UUID
    let completedAt: Date
    let soundID: String
    let wordCount: Int
  }
  struct ResearchGuidedPracticeVisit: Equatable, Identifiable, Sendable {
    let id: UUID
    let item: ResearchGuidedWordItem
    var capturedAttemptIds: Set<UUID> = []
    var completionState: ResearchGuidedPracticeCompletionState = .active
    var acknowledgedCompletion: ResearchGuidedPracticeCompletion?
    var hasValidCapture: Bool { !capturedAttemptIds.isEmpty }
  }

  /// Chosen canonical practice area, never a recognizer-inferred sound deficit.
  @MainActor
  enum ResearchGuidedPracticeParticipationMapping {
    static func soundID(for prompt: ResearchFeedbackPrompt) -> String? {
      guard ResearchGuidedWordSession.catalogValid,
        ResearchGuidedWordSession.roster.contains(where: { $0.prompt == prompt }),
        let mapping = mappings.first(where: { $0.id == prompt.id }),
        prompt.phones.indices.contains(prompt.occurrenceIndex),
        prompt.phones[prompt.occurrenceIndex] == prompt.targetPhone,
        let entry = PracticeLibrary.entries(soundID: mapping.soundID, position: mapping.position)
          .first(where: { $0.id == prompt.id }),
        entry.prompt.word == prompt.word, entry.prompt.phones == prompt.phones,
        entry.targetPhone == prompt.targetPhone, position(of: prompt) == entry.position
      else { return nil }
      return entry.soundID
    }
    private static func position(of prompt: ResearchFeedbackPrompt) -> PracticeTargetPosition {
      if prompt.occurrenceIndex == 0 { return .beginning }
      return prompt.occurrenceIndex == prompt.phones.count - 1 ? .end : .middle
    }
    private struct Mapping {
      let id: String
      let soundID: String
      let position: PracticeTargetPosition
    }
    private static let mappings: [Mapping] = [
      .init(id: "r-beginning-rabbit", soundID: "r", position: .beginning),
      .init(id: "r-middle-bread", soundID: "r", position: .middle),
      .init(id: "r-end-door", soundID: "r", position: .end),
      .init(id: "b-beginning-baby", soundID: "b", position: .beginning),
      .init(id: "n-middle-banana", soundID: "n", position: .middle),
      .init(id: "k-middle-backpack", soundID: "k", position: .middle),
      .init(id: "s-beginning-sky", soundID: "s", position: .beginning),
      .init(id: "v-beginning-vase", soundID: "v", position: .beginning),
      .init(id: "y-beginning-yo-yo", soundID: "y", position: .beginning),
      .init(id: "th-beginning-thumb", soundID: "th", position: .beginning),
      .init(id: "voiced-th-middle-feather", soundID: "voiced-th", position: .middle),
      .init(id: "ng-end-ring", soundID: "ng", position: .end),
      .init(id: "zh-middle-treasure", soundID: "zh", position: .middle),
    ]
  }
#endif
