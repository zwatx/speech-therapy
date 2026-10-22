#if DEBUG && targetEnvironment(simulator)
  import Foundation

  enum ResearchFreePracticeSaveError: Error, Equatable, Sendable {
    case storeUnavailable, writeUnconfirmed
    var userMessage: String {
      switch self {
      case .storeUnavailable: "Practice finished. Saving history is unavailable here."
      case .writeUnconfirmed:
        "Practice finished, but saving history could not be confirmed. You can retry saving."
      }
    }
  }
  enum ResearchFreePracticeCompletionState: Equatable, Sendable {
    case active
    case completedNotSaved(ResearchFreePracticeSaveError)
    case saved
  }
  struct ResearchFreePracticeCompletion: Equatable, Identifiable, Sendable {
    let id: UUID
    let completedAt: Date
    let soundID: String
    let wordCount: Int
  }

  /// The selected practice area is metadata, never an inferred sound deficit.
  @MainActor
  enum ResearchFreePracticeParticipationMapping {
    static func soundID(for prompt: ResearchFeedbackPrompt) -> String? {
      guard ResearchFeedbackCatalog.prompts.contains(prompt),
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
      .init(id: "b-middle-baby", soundID: "b", position: .middle),
      .init(id: "n-middle-banana", soundID: "n", position: .middle),
      .init(id: "k-middle-backpack", soundID: "k", position: .middle),
      .init(id: "k-end-backpack", soundID: "k", position: .end),
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
