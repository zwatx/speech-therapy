/// General instructions for the selected canonical target, never a recording observation.
enum DirectPracticeInstruction {
  static func text(
    sound: PracticeSound, prompt: PracticePrompt, visit: GuidedMediaVisit?
  ) -> String? {
    guard case .practice(let practice)? = visit, practice.entryID == prompt.id,
      sound.prompts.contains(prompt),
      let canonicalSound = PracticeLibrary.sounds.first(where: { $0.id == sound.id }),
      canonicalSound.symbol == sound.symbol,
      PracticeLibrary.entries(soundID: sound.id, position: sound.position)
        .contains(where: { $0.prompt == prompt })
    else { return nil }

    return DirectPracticeSoundGuide.content(sound: sound, prompt: prompt)?.detail
      ?? "Say “\(prompt.word)” as one whole word. Record a try, then play it back."
  }
}
