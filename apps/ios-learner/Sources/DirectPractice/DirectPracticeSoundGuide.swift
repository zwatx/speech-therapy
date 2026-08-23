/// General information about a selected target, never an observation of a recording.
struct DirectPracticeSoundGuide: Equatable, Sendable {
  enum Kind: Equatable, Sendable {
    case b
    case p
    case m
    case t
    case d
    case r
    case br
  }

  let kind: Kind
  let word: String
  let title: String
  let detail: String

  static func content(sound: PracticeSound, prompt: PracticePrompt) -> Self? {
    guard sound.prompts.contains(prompt),
      PracticeLibrary.entries(soundID: sound.id, position: sound.position)
        .contains(where: { $0.prompt == prompt })
    else { return nil }

    if sound.id == "b", sound.symbol == "b", sound.position == .beginning {
      return Self(
        kind: .b, word: prompt.word,
        title: "B at the start of “\(prompt.word)”",
        detail: "Bring your lips together, then open them as you say “\(prompt.word)”. Use your usual voice.")
    }

    if ["p", "m", "t", "d"].contains(sound.id) {
      let phone = sound.id.uppercased()
      guard sound.symbol == sound.id, sound.position == .beginning,
        prompt.phones.first == phone, !prompt.pronunciationVariants.isEmpty,
        prompt.pronunciationVariants.allSatisfy({ $0.first == phone })
      else { return nil }

      let kind: Kind
      let detail: String
      switch sound.id {
      case "p":
        kind = .p
        detail = "Bring your lips together, then let out a small puff of air as you start “\(prompt.word)”. Say the whole word comfortably."
      case "m":
        kind = .m
        detail = "Start “\(prompt.word)” with your lips together for a gentle “mmm”, letting air flow through your nose. Continue with the rest of the word comfortably."
      case "t":
        kind = .t
        detail = "Try touching the small ridge just behind your top front teeth with your tongue tip. Release a little air into “\(prompt.word)”. Say the whole word comfortably."
      default:
        kind = .d
        detail = "Try touching the small ridge just behind your top front teeth with your tongue tip. Release your tongue and use your voice as you say “\(prompt.word)”. Keep it comfortable."
      }
      return Self(kind: kind, word: prompt.word,
        title: "\(phone) at the start of “\(prompt.word)”", detail: detail)
    }

    guard sound.id == "r", sound.symbol == "ɹ", !prompt.pronunciationVariants.isEmpty
    else { return nil }

    switch sound.position {
    case .beginning:
      guard prompt.phones.first == "R",
        prompt.pronunciationVariants.allSatisfy({ $0.first == "R" })
      else { return nil }
      return Self(
        kind: .r, word: prompt.word,
        title: "R at the start of “\(prompt.word)”",
        detail: "Say “\(prompt.word)” as one whole word.")
    case .middle:
      guard prompt.phones.starts(with: ["B", "R"]),
        prompt.pronunciationVariants.allSatisfy({ $0.starts(with: ["B", "R"]) })
      else { return nil }
      return Self(
        kind: .br, word: prompt.word,
        title: "R in the BR of “\(prompt.word)”",
        detail: "Start with your lips together for B, then move straight into R as you say “\(prompt.word)”. Keep the sounds together in one whole word.")
    case .end:
      return nil
    }
  }
}
