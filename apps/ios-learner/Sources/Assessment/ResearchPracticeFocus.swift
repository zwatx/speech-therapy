#if DEBUG && targetEnvironment(simulator)
  /// Neutral listening guidance for the exact selected intended target, independent of results.
  enum ResearchPracticeFocus {
    private static let focuses: [String: String] = [
      "r-beginning-rabbit": "Listen for the r sound at the start of rabbit.",
      "r-middle-bread": "Listen for b followed by r in bread.",
      "r-end-door": "Listen for the r sound at the end of door.",
      "b-beginning-baby": "Listen for the first b sound in baby, at the start.",
      "b-middle-baby": "Listen for the second b sound in baby, in the middle.",
      "n-middle-banana": "Listen for the first n sound in banana.",
      "k-middle-backpack": "Listen for the first k sound in backpack, at the end of “back”.",
      "k-end-backpack": "Listen for the last k sound in backpack, at the very end.",
      "s-beginning-sky": "Listen for the s sound at the start of sky.",
      "v-beginning-vase": "Listen for the v sound at the start of vase.",
      "y-beginning-yo-yo": "Listen for the first y sound in yo-yo, as in “yes”.",
      "th-beginning-thumb": "Listen for the th sound at the start of thumb, as in “think”.",
      "voiced-th-middle-feather": "Listen for the th sound in the middle of feather, as in “this”.",
      "ng-end-ring": "Listen for the ng sound at the end of ring. It is one sound, without a separate g.",
      "zh-middle-treasure": "Listen for the middle sound in treasure, as in “measure”.",
    ]

    static func cue(for prompt: ResearchFeedbackPrompt?, exampleAvailable: Bool) -> String? {
      guard let prompt, ResearchFeedbackCatalog.prompts.contains(prompt),
        let focus = focuses[prompt.id]
      else { return nil }
      let action =
        exampleAvailable
        ? "Listen to the whole example, say the whole word, then play your own try."
        : "Say the whole word, then replay your try and listen for that sound."
      return "\(focus) \(action)"
    }
  }
#endif
